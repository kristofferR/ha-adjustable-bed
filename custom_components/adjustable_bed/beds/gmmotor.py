"""GM Control 4.6.6 explicit P1 product/controller session.

No legacy Richmat profile is selected or changed by this controller. Primary
control admission and state transitions come from the generated GM catalog.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Final

from homeassistant.util import dt as dt_util

from ..card import CARD_UTILITY
from ..const import CONF_GMMOTOR_SIDE, CONF_PRODUCT_TYPE
from ..controller_state import StateKey
from ..gmmotor_catalog_types import Phase
from ..gmmotor_notifications import Event, Value, common, desk21, extra
from ..gmmotor_profiles import Action, load_profile
from ..gmmotor_protocol import (
    FrameBuffer,
    MalformedNotification,
    Material,
    clock_frames,
    countdown_frames,
    countdown_minutes,
    delete_alarm,
    light_color,
    light_timeout,
    query_alarm,
    query_sleep_name,
    query_snore,
    repeating_alarm,
    snore_config,
    snore_enabled,
    stop_packet,
)
from ..gmmotor_requests import Request
from ..gmmotor_sessions import product_ui_states
from ..gmmotor_transport import Transport, native_write_lock, select_p1
from .base import (
    BedController,
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerStateSensorSpec,
    MotorControlSpec,
)
from .builder import BuildContext

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)
_WRITE_INTERVAL = 0.1
_MENU_INTERVAL = 0.3
_REMAINDER_TIMEOUT = 0.5
# HA action-readiness bound, not a protocol command interval.
_CAPABILITY_TIMEOUT = 5.0


def _label(action: Action) -> str:
    text = action.material.name.removeprefix("deviceFunctionItem").removeprefix(
        "deviceFunctionVersionOne"
    )
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)


PROFILE: Final = StateKey[str]("gmmotor_profile")
ALARM_CHOICES: Final = StateKey[dict[str, object]]("gmmotor_alarm_choices")
UI_STATE: Final = StateKey[object]("gmmotor_ui_state")
EVENT: Final = StateKey[str]("gmmotor_event")
EVENTS: Final = StateKey[dict[str, Value]]("gmmotor_events")
ALARMS: Final = StateKey[list[dict[str, Value]]]("gmmotor_alarms")
SLEEP_NAME: Final = StateKey[str]("gmmotor_sleep_name")
INVALID_NOTIFICATIONS: Final = StateKey[int]("gmmotor_invalid_notifications")


class GmmotorController(BedController):
    """One physical P1 session with an explicitly selected app product."""

    def __init__(
        self, coordinator: AdjustableBedCoordinator, *, profile: str, side: str = "left"
    ) -> None:
        super().__init__(coordinator)
        self.profile = load_profile(profile)
        if side not in ("left", "right", "both"):
            raise ValueError("Invalid GM Control bed side")
        self._side = side
        self._ui_states = product_ui_states(
            coordinator.hass, str(coordinator.address), self.profile.key
        )
        self._transport: Transport | None = None
        self._subscribed = False
        self._last_write: float | None = None
        self._buffer = FrameBuffer()
        self._remainder_timer: asyncio.TimerHandle | None = None
        self._events: dict[str, Value] = {}
        self._capability_changed = asyncio.Event()
        self._alarms: list[dict[str, Value]] = []
        self._invalid_notifications = 0
        self._write_lock = native_write_lock(coordinator.hass)
        self.forward_controller_state_updates(
            PROFILE(self.profile.key),
            ALARM_CHOICES(dict(self.profile.alarm_choices)),
            UI_STATE(self._ui_state),
        )

    @property
    def control_characteristic_uuid(self) -> str:
        return self._transport.write.uuid if self._transport else ""

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_motor_control(self) -> bool:
        # Physical axes are not inferred from catalog button names. Every app
        # control is exposed by the generic held/button contract instead.
        return False

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return ()

    @property
    def supports_single_address_pairing(self) -> bool:
        return 1 in self.profile.sides

    @property
    def memory_slot_count(self) -> int:
        return 0

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def supports_stop_all(self) -> bool:
        return True

    @property
    def supports_gmmotor_controls(self) -> bool:
        return True

    @property
    def _side_value(self) -> int:
        return {"left": 0, "right": 1, "both": 2}[self.command_side or self._side]

    @property
    def _ui_state(self) -> int:
        return self._ui_states.get(self._side_value, self.profile.initial_state)

    @_ui_state.setter
    def _ui_state(self, state: int) -> None:
        self._ui_states[self._side_value] = state

    @property
    def _single(self) -> bool:
        return self._transport.single if self._transport else False

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(f"gm_{i}" for i, a in enumerate(self.profile.controls) if not a.phone_only)

    def _control(self, control: str) -> Action:
        if control not in self.held_control_options:
            raise ValueError("This GM Control action is not in the selected product")
        return self.profile.controls[int(control.removeprefix("gm_"))]

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        action = self._control(control)
        if type(duration_ms) is not int or not 0 <= duration_ms <= 60000:
            raise ValueError("GM Control holds must be between 0 and 60000ms")
        phase = "long" if action.gesture in (2, 3, 4) and duration_ms >= 3000 else "normal"
        if action.gesture == 2 and duration_ms < 3000:
            return  # The source releases a long-only control without sending.
        action.apply(self._ui_state, phase, side=self._side_value, single=self._single)

    def controller_button_available(self, key: str) -> bool:
        control = key.removesuffix("_long")
        try:
            action = self._control(control)
        except ValueError:
            return False
        phase: Phase = "long" if key.endswith("_long") or action.gesture == 2 else "normal"
        return any(row[0] == self._ui_state and row[1] == phase for row in action.transitions)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs = []
        for i, action in enumerate(self.profile.controls):
            if action.phone_only:
                continue
            control = f"gm_{i}"
            duration = 1000 if action.gesture == 1 else 3000 if action.gesture == 2 else 0
            specs.append(
                ControllerButtonSpec(
                    key=control,
                    name=_label(action),
                    press_fn=lambda ctrl, c=control, d=duration: ctrl.hold_control(c, d),
                    hold=ControllerHoldSpec(control, 100, 0) if action.gesture == 1 else None,
                )
            )
            if action.gesture in (3, 4) and "long" in action.phases:
                specs.append(
                    ControllerButtonSpec(
                        key=control + "_long",
                        name=_label(action) + " (long press)",
                        press_fn=lambda ctrl, c=control: ctrl.hold_control(c, 3000),
                    )
                )
        return tuple(specs)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                key="gmmotor_state",
                translation_key="gmmotor_state",
                state_key=EVENT,
                icon="mdi:bed",
                attribute_keys=(
                    EVENTS,
                    ALARMS,
                    UI_STATE,
                    PROFILE,
                    ALARM_CHOICES,
                    SLEEP_NAME,
                    INVALID_NOTIFICATIONS,
                ),
                card=CARD_UTILITY,
            ),
        )

    async def _pause(self, seconds: float, cancel: asyncio.Event) -> bool:
        if cancel.is_set():
            return False
        try:
            async with asyncio.timeout(max(0, seconds)):
                await cancel.wait()
        except TimeoutError:
            return True
        return False

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        transport, client = self._transport, self.client
        if transport is None or client is None or not client.is_connected:
            raise ConnectionError("GM Control session is not ready")
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        # Native rejects oversize P1 writes, rather than silently fragmenting.
        if len(command) > min(client.mtu_size - 3, 512):
            raise ValueError("GM Control command exceeds this connection's ATT payload")
        for index in range(repeat_count):
            if cancel.is_set():
                return
            now = asyncio.get_running_loop().time()
            if self._last_write is not None:
                interval = (
                    _WRITE_INTERVAL if index == 0 else max(_WRITE_INTERVAL, repeat_delay_ms / 1000)
                )
                if not await self._pause(max(0, self._last_write + interval - now), cancel):
                    return
            async with self._write_lock:
                self._last_write = asyncio.get_running_loop().time()
                async with asyncio.timeout(15):
                    # The base helper does not retry failed writes. It retains
                    # production tracing and checks cancellation after its lane.
                    await self._write_gatt_with_retry(
                        transport.write.uuid,
                        command,
                        cancel_event=cancel,
                        response=transport.response,
                        characteristic=transport.write,
                    )

    async def _phase(self, action: Action, phase: Phase, cancel: asyncio.Event) -> None:
        state, packet = action.apply(
            self._ui_state, phase, side=self._side_value, single=self._single
        )
        self._ui_state = state
        self.forward_controller_state_update(UI_STATE, state)
        if packet:
            await self.write_command(packet, cancel_event=cancel)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        action = self._control(control)
        cancel = self._coordinator.cancel_command
        sent = False
        try:
            if action.gesture == 1:
                # Sustain first fires at 100ms, then every 100ms. A sub-tick
                # release emits neither the command nor its bound release.
                for _ in range(duration_ms // 100):
                    if not await self._pause(_WRITE_INTERVAL, cancel):
                        return
                    sent = True
                    await self._phase(action, "normal", cancel)
            elif action.gesture in (2, 3, 4) and duration_ms >= 3000:
                if await self._pause(3, cancel):
                    await self._phase(action, "long", cancel)
                    if duration_ms > 3000:
                        await self._pause((duration_ms - 3000) / 1000, cancel)
            elif action.gesture != 2:
                if action.gesture in (3, 4) and duration_ms:
                    if not await self._pause(duration_ms / 1000, cancel):
                        return
                sent = True
                await self._phase(action, "normal", cancel)
                if action.gesture == 0 and duration_ms:
                    await self._pause(duration_ms / 1000, cancel)
        finally:
            if sent and action.gesture in (0, 1) and "release" in action.phases:
                await self._phase(action, "release", asyncio.Event())

    async def stop_all(self) -> None:
        await self.write_command(
            stop_packet(side=self._side_value, single=self._single), cancel_event=asyncio.Event()
        )

    def _expire_remainder(self) -> None:
        self._remainder_timer = None
        self._buffer.clear()

    def _cancel_remainder(self) -> None:
        if self._remainder_timer:
            self._remainder_timer.cancel()
            self._remainder_timer = None

    def _receive(self, sender: BleakGATTCharacteristic, data: bytearray) -> None:
        self.forward_raw_notification(sender.uuid, bytes(data))
        self._cancel_remainder()
        try:
            for kind, frame in self._buffer.extract(bytes(data)):
                if kind == 64:
                    continue  # OTA payload excluded; shared extraction/CRC retained.
                for event in (
                    extra(frame) if kind == 32 else desk21(frame) if kind == 33 else common(frame)
                ):
                    self._accept(event)
        except MalformedNotification:
            self._invalid_notifications += 1
            self._buffer.clear()
            self.forward_controller_state_update(INVALID_NOTIFICATIONS, self._invalid_notifications)
            _LOGGER.debug("Rejected malformed GM Control notification", exc_info=True)
        finally:
            # HA intentionally guarantees cleanup after malformed input, unlike
            # the source's stalled extraction/aborted async-handler paths.
            if self._buffer.pending:
                self._remainder_timer = asyncio.get_running_loop().call_later(
                    _REMAINDER_TIMEOUT, self._expire_remainder
                )

    def _accept(self, event: Event) -> None:
        self._events[event.name] = event.value
        if event.name in ("clock_capability", "light_capability"):
            self._capability_changed.set()
        if (
            event.name == "sleep_name"
            and isinstance(event.value, list)
            and all(type(value) is int and 0 <= value <= 255 for value in event.value)
        ):
            # String.fromCharCodes of the source's List<int>, not UTF-8 decode.
            self.forward_controller_state_update(
                SLEEP_NAME, "".join(chr(value) for value in event.value if isinstance(value, int))
            )
        if event.name == "alarm_list" and isinstance(event.value, dict):
            if event.value not in self._alarms:
                self._alarms.append(event.value)
        if event.name == "alarm_escalation" and isinstance(event.value, dict):
            for index, record in enumerate(self._alarms):
                if record.get("id") == event.value.get("id"):
                    self._alarms[index] = event.value
                    break
        self.forward_controller_state_updates(
            EVENT(event.name), EVENTS(dict(self._events)), ALARMS(list(self._alarms))
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if self._subscribed:
            return
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to GM Control")
        self._transport = select_p1(client.services)
        notify = self._transport.notifications[0]
        self._buffer.clear()
        self._cancel_remainder()
        try:
            async with self.ble_lock:
                await client.start_notify(notify, self._receive)
            self._subscribed = True
            # HA's configured product is the concrete setup context. The source
            # context guard is not an authentication/model capability flag.
            await self.write_command(
                Material("deviceFunctionItemExitLimit", 0).packet(
                    side=self._side_value, single=self._single
                )
            )
            await self._setup_menu()
        except BaseException:
            await self.stop_notify()
            raise

    async def _setup_menu(self) -> None:
        if self.profile.alarm_choices:
            for packet in clock_frames(dt_util.now()):
                await self.write_command(packet)
        if self.profile.sleep_kind == "ble":
            await self.write_command(query_sleep_name())
        for name in ("deviceFunctionItemCheckClock", "deviceFunctionItemCheckLight"):
            await self._pause(_MENU_INTERVAL, self._coordinator.cancel_command)
            await self.write_command(
                Material(name, 1).packet(side=self._side_value, single=self._single)
            )

    async def stop_notify(self) -> None:
        transport, subscribed = self._transport, self._subscribed
        self.on_disconnect()
        client = self.client
        if subscribed and transport is not None and client is not None and client.is_connected:
            async with self.ble_lock:
                await client.stop_notify(transport.notifications[0])

    def on_disconnect(self) -> None:
        self._cancel_remainder()
        self._buffer.clear()
        self._transport = None
        self._subscribed = False
        self._last_write = None
        for name in ("clock_capability", "light_capability"):
            self._events.pop(name, None)
        self._capability_changed.set()

    def validate_gmmotor_request(self, request: Request) -> None:
        """Preflight product/input gates without trusting a cached session's ACKs."""
        op = request.operation
        if op.startswith(("sensor_", "desk_")):
            raise ValueError("This action requires an independent GM Control sleep module")
        if op == "massage_timer" and (
            not self.profile.massage_timer or request.value not in range(4)
        ):
            raise ValueError("This product has no matching bottom massage timer choice")
        if op in ("alarm", "alarm_at", "repeat_alarm") and request.mode not in dict(
            self.profile.alarm_choices
        ):
            raise ValueError("Alarm action is absent from this exact product's alarm catalog")
        if op.startswith("repeat_") and not self.profile.repeat_alarm:
            raise ValueError("Selected product does not admit repeat alarms")
        if op in ("alarm", "alarm_at", "alarm_cancel") and self.profile.repeat_alarm:
            raise ValueError("This product opens the repeat-alarm page instead of a countdown")
        if (
            op in ("alarm", "alarm_at", "alarm_cancel", "clock_sync")
            and not self.profile.alarm_choices
        ):
            raise ValueError("Selected product has no alarm catalog")
        if op.startswith("light_") and not self.profile.has_light:
            raise ValueError("Light menu is not admitted by this product")
        if op == "light_timeout" and request.value > 900:
            raise ValueError("Light timeout is outside the source's 0 to 900 second slider")
        if op == "light_color" and self.profile.eight_colors:
            from ..gmmotor_profiles import EIGHT_COLORS

            if request.rgb not in EIGHT_COLORS:
                raise ValueError("Choose a color from this product's eight-color palette")
        if op.startswith("snore_") and self.profile.key not in (
            "HNRN",
            "HQRN",
            "HSRN",
            "HURN",
            "M7RN",
            "MJRN",
        ):
            # isShowSleepSnoreSettingWidget (0x817ec4) selects this page by
            # product. Its status listener updates the switch after admission.
            raise ValueError("This exact product has no anti-snore settings page")
        if (op == "snore_time" and request.value not in range(5, 31)) or (
            op == "snore_count" and request.value not in range(1, 31)
        ):
            raise ValueError("Anti-snore value is outside the source slider range")
        if op == "sleep_name" and self.profile.sleep_kind != "ble":
            raise ValueError("This selected product does not admit a BLE sleep module")

    async def async_execute_gmmotor_request(self, request: Request) -> None:
        self.validate_gmmotor_request(request)
        op = request.operation
        capability = (
            "light_capability"
            if op.startswith("light_")
            else "clock_capability"
            if op.startswith("repeat_") or op in ("alarm", "alarm_at", "alarm_cancel")
            else None
        )
        if capability is not None:
            # Startup sends the queries, but BLE replies can arrive after it
            # returns. Only the executing connection can admit this action.
            try:
                async with asyncio.timeout(_CAPABILITY_TIMEOUT):
                    while capability not in self._events and self._subscribed:
                        self._capability_changed.clear()
                        await self._capability_changed.wait()
            except TimeoutError:
                pass
            if capability not in self._events:
                raise ValueError(f"GM Control action requires a live {capability} reply")
        packets: tuple[bytes, ...]
        if op == "clock_sync":
            packets = clock_frames(dt_util.now())
        elif op in ("alarm", "alarm_at", "alarm_cancel"):
            now = dt_util.now()
            minutes = (
                countdown_minutes(now.replace(hour=request.hour, minute=request.minute), now)
                if op == "alarm_at"
                else request.value
            )
            packets = (
                countdown_frames(minutes, dict(self.profile.alarm_choices)[request.mode])
                if op != "alarm_cancel"
                else countdown_frames(0, 0)
            )
        elif op == "repeat_alarm":
            packets = (
                repeating_alarm(
                    (
                        request.slot,
                        request.repeat,
                        request.hour,
                        request.minute,
                        dict(self.profile.alarm_choices)[request.mode],
                        request.status,
                    )
                ),
            )
        elif op == "repeat_delete":
            packets = (delete_alarm(request.slot),)
        elif op == "repeat_query":
            self._alarms.clear()
            self.forward_controller_state_update(ALARMS, [])
            packets = (query_alarm(),)
        elif op == "light_color":
            packets = (light_color(request.rgb),)
        elif op == "light_timeout":
            packets = (light_timeout(request.value),)
        elif op == "light_off":
            packets = (
                Material("deviceFunctionItemBedLightClose", 117).packet(
                    side=self._side_value, single=self._single
                ),
            )
        elif op == "massage_timer":
            codes = (139 if self.profile.key == "D9RM" else 94, 95, 99, 97)
            packets = (
                Material("deviceFunctionItemMassageModeAllOff", codes[request.value]).packet(
                    side=self._side_value, single=self._single
                ),
            )
        elif op == "snore_enabled":
            packets = (snore_enabled(request.enabled),)
        elif op in ("snore_count", "snore_time"):
            packets = (snore_config("count" if op == "snore_count" else "time", request.value),)
        elif op == "snore_query":
            packets = (query_snore(), query_snore(configuration=True))
        elif op == "sleep_name":
            packets = (query_sleep_name(),)
        elif op == "refresh":
            packets = tuple(
                Material(name, 1).packet(side=self._side_value, single=self._single)
                for name in ("deviceFunctionItemCheckClock", "deviceFunctionItemCheckLight")
            )
        else:
            raise ValueError("Unknown GM Control operation")
        for packet in packets:
            await self.write_command(packet)

    async def _unmapped_axis(self) -> None:
        raise NotImplementedError("Use this product's named GM Control actions")

    move_head_up = move_head_down = move_back_up = move_back_down = _unmapped_axis
    move_legs_up = move_legs_down = move_feet_up = move_feet_down = _unmapped_axis
    move_head_stop = move_back_stop = move_legs_stop = move_feet_stop = stop_all
    preset_flat = _unmapped_axis

    async def preset_memory(self, memory_num: int) -> None:
        raise NotImplementedError("Use this product's named GM Control memory action")

    async def program_memory(self, memory_num: int) -> None:
        raise NotImplementedError("Use this product's named GM Control long-press action")


async def build_controller(ctx: BuildContext) -> BedController:
    """Build the bed or desk controller for the stored GMmotor profile."""
    from ..gmmotor_profiles import profile_choices

    profile = ctx.data.get(CONF_PRODUCT_TYPE, "")
    if profile not in profile_choices():
        profile = ""  # Source factory's unsupported-selector fallback.
    if profile in ("FWRM", "WFRM"):
        await ctx.preload("gmmotor_desk")
        from .gmmotor_desk import GmmotorDeskController

        return GmmotorDeskController(ctx.coordinator, profile=profile)
    return GmmotorController(
        ctx.coordinator, profile=profile, side=ctx.data.get(CONF_GMMOTOR_SIDE, "left")
    )
