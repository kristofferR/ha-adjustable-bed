"""SmartBed controls with connection-owned GATT, callbacks and release cleanup."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, cast

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_MASSAGE, CARD_MASSAGE_TIMER
from ...command_scheduler import CommandOutcome, Delivery, current_command_context, delivered
from ...const import (
    CONF_BLE_DEVICE_NAME,
    CONF_CB24_BED_SELECTION,
    CONF_MOTOR_COUNT,
    CONF_PAIR_MODE,
    PAIR_MODE_SINGLE_ADDRESS,
)
from ...controller_state import AnyStateKey, StateKey, StateUpdate, sided
from ...errors import failed, invalid
from ...execution import ExecutionCapabilities
from ...profiles import smartbed as app
from ...profiles.smartbed import Function as F
from ...state_keys import MASSAGE_TIMER_MINUTES, UNDER_BED_LIGHTS_ON, massage_intensity
from ..base import BedController
from ..builder import BuildContext
from ..cancellation import cancellable, settled
from ..catalog_buttons import Kind, catalog_button, save_button, unique_buttons
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerNumberSpec,
    ControllerSelectSpec,
    ControllerStateBinarySensorSpec,
    ControllerStateSensorSpec,
    ControllerSwitchSpec,
    MotorCommandCallable,
    MotorControlSpec,
)
from ..lifecycle import CapabilitySnapshotPolicy, ControllerSession
from .discovery import select_profile
from .receive import Parser
from .setup import receiver_variant
from .state_keys import (
    ALARM_ACTION,
    ALARM_ON,
    ALARM_REPEAT,
    ALARM_TIME,
    ALL,
    MASSAGE,
    SONIC,
    SONIC_FOOT,
    SONIC_HEAD,
    SONIC_MODE,
    SONIC_TIMER,
    SONIC_WAVE,
    WAVE,
)

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    response: bool
    profile: app.SmartBedProfile
    protocol: app.Protocol


def _range(value: float, minimum: int, maximum: int) -> int:
    if not minimum <= value <= maximum or int(value) != value:
        raise invalid("value_out_of_range", min=minimum, max=maximum, step=1)
    return int(value)


class _HoldEnded(Exception):
    """A queued refresh outlived the held gesture, so it must not dispatch."""


class OkinCB24Controller(BedController):
    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        bed_selection: int = 0,
        protocol_variant: str = "cb24",
        *,
        motors: int | None = None,
        massage: bool = True,
        light: bool = True,
        massage_count: int = 2,
        snapshot: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.profile = app.PROFILES[app.ALIASES.get(protocol_variant, protocol_variant)]
        self._bed_selection = {0xAA: 1, 0xBB: 2}.get(bed_selection, bed_selection)
        configured = motors if motors is not None else coordinator.motor_count
        self._motors = configured if type(configured) is int else 2
        self._massage, self._light, self._massage_count = massage, light, massage_count
        self._sonic, self._rgb = False, False
        if self.protocol == 5 and snapshot and snapshot.get("profile") == self.profile.key:
            for field, attr in (("motors", "_motors"), ("massage_count", "_massage_count")):
                value = snapshot.get(field)
                if type(value) is int and 0 <= value <= 8:
                    setattr(self, attr, value)
            for field, attr in (
                ("massage", "_massage"),
                ("light", "_light"),
                ("sonic", "_sonic"),
                ("rgb", "_rgb"),
            ):
                value = snapshot.get(field)
                if type(value) is bool:
                    setattr(self, attr, value)
        self._feedback_side = (
            0
            if coordinator.entry.data.get(CONF_PAIR_MODE) == PAIR_MODE_SINGLE_ADDRESS
            else self._bed_selection
        )
        self._parsers = {side: Parser(self.profile.key) for side in (0, 1, 2)}
        self._link: Link | None = None
        self._notifying = False
        self._tasks: set[asyncio.Task[None]] = set()
        self._session: ControllerSession | None = None
        self._configuration_active = False
        self._light_received = asyncio.Event()

    @property
    def control_characteristic_uuid(self) -> str:
        return self.profile.transport[1]

    @property
    def protocol(self) -> app.Protocol:
        return self.profile.protocol(self._motors)

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def execution(self) -> ExecutionCapabilities:
        return self.profile.execution

    @property
    def supports_single_address_pairing(self) -> bool:
        return self.profile.key == "cb24_ab"

    def _side(self) -> int:
        return {"left": 1, "right": 2, "both": 0}.get(self.command_side or "", self._bed_selection)

    def _selector(self) -> int:
        side = self._side()
        if side and not self.supports_single_address_pairing:
            raise invalid("single_address_pair_unsupported")
        return side

    def _parser(self) -> Parser:
        return self._parsers[self._side() if self.profile.key in ("cb24_ab", "dacheng") else 0]

    def _frame(self, function: int, subfunction: int = 0, data: bytes | None = None) -> bytes:
        return self.profile.encode(
            function, subfunction, data, motors=self._motors, side=self._selector()
        )

    def _capture_link(self) -> Link:
        if self._link is not None:
            self._check_link(self._link)
            return self._link
        client = self.client
        if client is None or not client.is_connected or client.services is None:
            raise failed("bed_not_connected")
        ws, wu, ns, nu = self.profile.transport

        def characteristic(service_uuid: str, uuid: str) -> BleakGATTCharacteristic | None:
            for service in client.services:
                if str(service.uuid).lower() == service_uuid:
                    for char in service.characteristics:
                        if str(char.uuid).lower() == uuid:
                            return char
            return None

        write, notify = characteristic(ws, wu), characteristic(ns, nu)
        if (
            write is None
            or notify is None
            or not {"write", "write-without-response"}.intersection(write.properties)
            or "notify" not in notify.properties
        ):
            raise failed("bed_missing_service")
        # The APK leaves write type untouched. Resolve from this exact live
        # characteristic, preferring acknowledged writes when both are offered.
        self._link = Link(
            client, write, notify, "write" in write.properties, self.profile, self.protocol
        )
        return self._link

    def _check_link(self, link: Link) -> None:
        if (
            self._link is not link
            or self.client is not link.client
            or not link.client.is_connected
            or self.profile is not link.profile
            or self.protocol != link.protocol
        ):
            raise failed("smartbed_session_changed")

    async def _write(
        self,
        link: Link,
        command: bytes,
        *,
        cleanup: bool = False,
        preparation: bool = False,
        cancel_event: asyncio.Event | None = None,
        before_dispatch: Callable[[], None] | None = None,
    ) -> bool:
        self._check_link(link)
        if not command:
            raise invalid("option_unavailable")
        written = False

        def sent() -> None:
            nonlocal written
            written = True

        def validate() -> None:
            self._check_link(link)
            if before_dispatch is not None:
                before_dispatch()

        await self._write_gatt_with_retry(
            str(link.write.uuid),
            command,
            characteristic=link.write,
            expected_client=link.client,
            response=link.response,
            cancel_event=asyncio.Event() if cleanup else cancel_event,
            before_write=validate,
            on_write=sent,
            track_command_write=not (cleanup or preparation),
        )
        return written

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 300,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._capture_link()
        for index in range(repeat_count):
            if not await self._write(link, command, cancel_event=cancel_event):
                return
            if index + 1 < repeat_count:
                await asyncio.sleep(repeat_delay_ms / 1000)

    async def _release(self, link: Link, frame: bytes, *, released_at: float | None = None) -> None:
        due = (
            asyncio.get_running_loop().time() if released_at is None else released_at
        ) + self.profile.release_ms / 1000

        async def release() -> None:
            await asyncio.sleep(max(0, due - asyncio.get_running_loop().time()))
            # Cleanup may never migrate to a replacement connection.
            if self._link is link and self.client is link.client and link.client.is_connected:
                await self._write(link, frame, cleanup=True)

        await settled(release())

    async def _hold(
        self, function: F, subfunction: int = 0, *, duration_ms: int = 1000
    ) -> float | None:
        link, frame, stop = (
            self._capture_link(),
            self._frame(function, subfunction),
            self._frame(F.STOP),
        )
        loop, context = asyncio.get_running_loop(), current_command_context()
        end: float | None = None
        armed = False
        deadline: float | None = None
        tick = loop.time()
        released_at: float | None = None

        def arm_release() -> None:
            nonlocal armed, end, deadline, tick
            tick = loop.time()
            deadline = (
                context.hold_deadline if context and context.hold_deadline is not None else end
            )
            if deadline is not None and tick >= deadline:
                raise _HoldEnded
            if not armed:
                end = tick + duration_ms / 1000
            armed = True
            deadline = (
                context.hold_deadline if context and context.hold_deadline is not None else end
            )

        try:
            while not self._coordinator.cancel_command.is_set():
                deadline = (
                    context.hold_deadline if context and context.hold_deadline is not None else end
                )
                if deadline is not None and loop.time() >= deadline:
                    break
                try:
                    if not await self._write(link, frame, before_dispatch=arm_release):
                        break
                except _HoldEnded:
                    break
                assert deadline is not None
                await asyncio.sleep(
                    max(0, min(tick + self.profile.refresh_ms / 1000, deadline) - loop.time())
                )
        finally:
            if armed:
                released_at = min(loop.time(), deadline) if deadline is not None else loop.time()
                await self._release(link, stop, released_at=released_at)
        return released_at

    async def _massage_readback(self, link: Link, released_at: float | None) -> None:
        if released_at is None:
            return
        context = current_command_context()
        event = self._coordinator.cancel_command

        expired = context is not None and context.cancel_reason is CommandOutcome.EXPIRED
        if event.is_set() and not expired:
            return
        cancel = event
        if expired:
            assert context is not None
            cancel = context.cancel_event_after(context.cancel_generation)

        async def readback() -> None:
            await asyncio.sleep(max(0, released_at + 0.5 - asyncio.get_running_loop().time()))

            def still_readable() -> None:
                if cancel.is_set():
                    raise asyncio.CancelledError

            await self._write(
                link, self._frame(F.MASSAGE, 5), preparation=True,
                cancel_event=cancel, before_dispatch=still_readable,
            )

        await cancellable(readback(), cancel)

    async def _one(
        self,
        function: F,
        subfunction: int = 0,
        data: bytes | None = None,
        *,
        query: F | None = None,
        delay_ms: int = 200,
        updates: tuple[StateUpdate, ...] = (),
    ) -> None:
        link = self._capture_link()

        def show(delivery: Delivery) -> None:
            if (
                self._link is not link
                or self.client is not link.client
                or not link.client.is_connected
            ):
                return
            if delivery is Delivery.SENT:
                self.forward_controller_state_updates(*updates)
            elif delivery is Delivery.PARTIAL:
                self.forward_controller_state_updates(
                    *(StateUpdate(update.key, None) for update in updates)
                )

        started = 0.0

        def dispatched() -> None:
            nonlocal started
            started = asyncio.get_running_loop().time()

        with delivered(show):
            sent = await self._write(
                link, self._frame(function, subfunction, data), before_dispatch=dispatched
            )
        if not sent:
            return
        if query is not None:
            await asyncio.sleep(
                max(0, started + delay_ms / 1000 - asyncio.get_running_loop().time())
            )
            await self._write(link, self._frame(query, 5), preparation=True)

    async def _old_control(self, function: F, subfunction: int = 0) -> None:
        link = self._capture_link()
        released_at = await self._hold(function, subfunction, duration_ms=1)
        if function in (F.HEAD_MASSAGE, F.FOOT_MASSAGE, F.WAVE, F.MASSAGE, F.TIMER, F.INTENSITY):
            await self._massage_readback(link, released_at)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        if self.profile.key.startswith("headboard"):
            axes = (
                ("headboard_left", "smartbed_left", F.HEAD),
                ("headboard_right", "smartbed_right", F.FOOT),
            )
        else:
            axes = (("head", "head", F.HEAD), ("feet", "feet", F.FOOT), ("both", "both", F.BOTH))
            if self._motors in (3, 4, 5):
                axes += (("head_tilt", "head_tilt", F.TILT),)
            if self._motors in (4, 5):
                axes += (("lumbar", "lumbar", F.LUMBAR),)
            if self._motors == 5 and self.protocol != 2:
                axes += (("hip", "hip", F.HIPS),)
        return tuple(
            MotorControlSpec(
                key,
                label,
                _move(function, 1),
                _move(function, 2),
                lambda c: c._send_stop(),
                hold=ControllerMotorHoldSpec(
                    f"{key}_up",
                    f"{key}_down",
                    release_delay_ms=self.profile.release_ms,
                    stop_scope="side",
                    press_is_native=True,
                ),
            )
            for key, label, function in axes
        )

    def _held_actions(self) -> dict[str, tuple[F, int]]:
        actions: dict[str, tuple[F, int]] = {}
        if self.protocol != 5 and self.supports_lights:
            actions["light_toggle"] = (F.LIGHT, 3)
        if self.supports_massage:
            if self.protocol != 5:
                for label, function in (
                    ("head", F.HEAD_MASSAGE),
                    ("foot", F.FOOT_MASSAGE),
                    ("all", F.INTENSITY),
                ):
                    if (
                        label in ("head", "foot")
                        and self.protocol == 1
                        or label == "all"
                        and self.profile.key.startswith("headboard")
                    ):
                        continue
                    for direction, sub in (("up", 8), ("down", 9)):
                        actions[f"massage_{label}_{direction}"] = function, sub
                actions["massage_toggle"] = F.MASSAGE, 3
                actions["smartbed_wave_up"] = F.WAVE, 8
                actions["smartbed_wave_down"] = F.WAVE, 9
            if self.supports_massage_timer and self.protocol in (3, 4):
                actions["smartbed_timer_up"] = F.TIMER, 8
                actions["smartbed_timer_down"] = F.TIMER, 9
        return actions

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (
            *tuple(
                f"{spec.key}_{direction}"
                for spec in self.motor_control_specs
                for direction in ("up", "down")
            ),
            *self._held_actions(),
        )

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        action = "massage_toggle" if key == "massage_all_toggle" else key
        if action in self._held_actions():
            return ControllerHoldSpec(action, release_delay_ms=self.profile.release_ms)
        return None

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise invalid("option_unavailable")
        _range(duration_ms, 1, 30000)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        action = self._held_actions().get(control)
        if action is not None:
            link = self._capture_link()
            released_at = await self._hold(*action, duration_ms=duration_ms)
            if action[0] != F.LIGHT:
                await self._massage_readback(link, released_at)
            return
        key, direction = control.rsplit("_", 1)
        function = {
            "head": F.HEAD,
            "feet": F.FOOT,
            "both": F.BOTH,
            "head_tilt": F.TILT,
            "lumbar": F.LUMBAR,
            "hip": F.HIPS,
            "headboard_left": F.HEAD,
            "headboard_right": F.FOOT,
        }[key]
        await self._hold(function, 1 if direction == "up" else 2, duration_ms=duration_ms)

    async def move_head_up(self) -> None:
        await self._hold(F.HEAD, 1)

    async def move_head_down(self) -> None:
        await self._hold(F.HEAD, 2)

    async def move_head_stop(self) -> None:
        await self._send_stop()

    async def move_feet_up(self) -> None:
        await self._hold(F.FOOT, 1)

    async def move_feet_down(self) -> None:
        await self._hold(F.FOOT, 2)

    async def move_feet_stop(self) -> None:
        await self._send_stop()

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self._send_stop()

    async def move_legs_up(self) -> None:
        await self.move_feet_up()

    async def move_legs_down(self) -> None:
        await self.move_feet_down()

    async def move_legs_stop(self) -> None:
        await self._send_stop()

    async def _send_stop(self) -> None:
        await self._write(self._capture_link(), self._frame(F.STOP), cleanup=True)

    async def stop_all(self) -> None:
        await self._send_stop()

    @property
    def _presets(self) -> tuple[str, ...]:
        return tuple(
            name
            for name in self.profile.preset_names
            if self.protocol != 4 or name not in ("lounge", "tv")
        )

    @property
    def supports_preset_flat(self) -> bool:
        return "flat" in self._presets

    @property
    def supports_preset_zero_g(self) -> bool:
        return "zero_g" in self._presets

    @property
    def supports_preset_anti_snore(self) -> bool:
        return "anti_snore" in self._presets

    @property
    def supports_preset_lounge(self) -> bool:
        return "lounge" in self._presets

    @property
    def supports_preset_tv(self) -> bool:
        return "tv" in self._presets

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return sum(name.startswith("memory_") for name in self._presets)

    @property
    def supports_memory_programming(self) -> bool:
        return self.protocol == 5

    @property
    def memory_slot_names(self) -> tuple[str, ...]:
        return tuple(f"M{n}" for n in range(1, self.memory_slot_count + 1))

    async def recall(self, name: str) -> None:
        if name not in self._presets:
            raise invalid("option_unavailable")
        function = app.PRESETS[name]
        if self.protocol == 5:
            await self._one(function)
        else:
            # A tap never crosses the app's destructive long-hold threshold.
            await self._hold(function, duration_ms=1)

    async def preset_flat(self) -> None:
        await self.recall("flat")

    async def preset_zero_g(self) -> None:
        await self.recall("zero_g")

    async def preset_lounge(self) -> None:
        await self.recall("lounge")

    async def preset_tv(self) -> None:
        await self.recall("tv")

    async def preset_anti_snore(self) -> None:
        await self.recall("anti_snore")

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self.recall(f"memory_{memory_num}")

    async def save(self, name: str) -> None:
        if (
            name not in self._presets
            or name == "flat"
            or name == "memory_2"
            and self.memory_slot_count < 2
        ):
            raise invalid("option_unavailable")
        if self.protocol == 5:
            await self._one(app.PRESETS[name], 7)
        else:
            await self._hold(app.PRESETS[name], duration_ms=self.profile.save_ms)

    async def program_memory(self, memory_num: int) -> None:
        if not self.supports_memory_programming or memory_num not in range(
            1, self.memory_slot_count + 1
        ):
            raise invalid("option_unavailable")
        await self.save(f"memory_{memory_num}")

    @property
    def supports_lights(self) -> bool:
        return self._light and self.profile.has_light

    @property
    def supports_discrete_light_control(self) -> bool:
        return self.protocol == 5 and self._light

    @property
    def supports_light_state_feedback(self) -> bool:
        return self.protocol == 5 and self.supports_lights

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.supports_lights

    async def _set_light(self, enabled: bool) -> None:
        if not self.supports_discrete_light_control:
            raise invalid("option_unavailable")
        if self._rgb:
            await self._one(F.LIGHT, 6, bytes((2, int(enabled))), query=F.LIGHT, delay_ms=100)
        else:
            await self._one(F.LIGHT, 3 if enabled else 4, query=F.LIGHT, delay_ms=100)

    async def lights_on(self) -> None:
        await self._set_light(True)

    async def lights_off(self) -> None:
        await self._set_light(False)

    async def lights_toggle(self) -> None:
        if not self.supports_lights:
            raise invalid("option_unavailable")
        if self.protocol == 5:
            state = self._coordinator.controller_state.get(UNDER_BED_LIGHTS_ON)
            if not isinstance(state, bool):
                link = self._capture_link()
                self._light_received.clear()
                await self._write(link, self._frame(F.LIGHT, 5), preparation=True)
                try:
                    async with asyncio.timeout(1):
                        await self._light_received.wait()
                except TimeoutError:
                    raise invalid("light_state_unknown") from None
                self._check_link(link)
                state = self._coordinator.controller_state.get(UNDER_BED_LIGHTS_ON)
                if not isinstance(state, bool):
                    raise invalid("light_state_unknown")
            await self._set_light(not state)
        else:
            await self._old_control(F.LIGHT)

    @property
    def supports_massage(self) -> bool:
        return self._massage and self.profile.has_massage

    @property
    def auto_enable_massage(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_toggle_control(self) -> bool:
        return self.supports_massage and self.protocol not in (1, 5)

    @property
    def supports_massage_off_control(self) -> bool:
        return False  # Discrete on/off belongs to the massage switch.

    @property
    def supports_massage_intensity_control(self) -> bool:
        return self.supports_massage and self.profile.key != "headboard265"

    @property
    def massage_intensity_zones(self) -> list[str]:
        return ["all"] if self.protocol in (1, 2) else ["head", "foot"][: self._massage_count]

    @property
    def massage_intensity_max(self) -> int:
        return 3

    def massage_intensity_min(self, zone: str) -> int:
        return 0 if self.protocol == 5 else 1

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        if zone not in self.massage_intensity_zones:
            raise invalid("option_unavailable")
        level = _range(level, self.massage_intensity_min(zone), 3)
        f = {"head": F.HEAD_MASSAGE, "foot": F.FOOT_MASSAGE, "all": F.INTENSITY}[zone]
        sub = 4 if level == 0 else level + 9
        if self.protocol == 5:
            await self._one(f, sub, query=F.MASSAGE)
        else:
            await self._old_control(f, sub)

    async def _arrow(self, function: F, increase: bool) -> None:
        if not self.supports_massage:
            raise invalid("option_unavailable")
        if self.protocol == 5:
            s = self._parser().state
            previous = {
                F.HEAD_MASSAGE: s.head_intensity,
                F.FOOT_MASSAGE: s.foot_intensity,
                F.WAVE: s.massage_wave,
            }[function]
            minimum, maximum = app.ARROW_RANGES[function]
            value = min(previous + 1, maximum) if increase else max(previous - 1, minimum)
            # Source setters do not mutate the receive cache optimistically.
            await self._one(function, 4 if value == 0 else value + 9, query=F.MASSAGE)
        else:
            await self._old_control(function, 8 if increase else 9)

    @property
    def supports_head_massage_intensity_step_control(self) -> bool:
        return (
            self.supports_massage
            and self.protocol != 1
            and self._massage_count >= 1
            and self.profile.key != "headboard265"
        )

    @property
    def supports_foot_massage_intensity_step_control(self) -> bool:
        return (
            self.supports_massage
            and self.protocol != 1
            and self._massage_count >= 2
            and self.profile.key != "headboard265"
        )

    async def massage_head_up(self) -> None:
        await self._arrow(F.HEAD_MASSAGE, True)

    async def massage_head_down(self) -> None:
        await self._arrow(F.HEAD_MASSAGE, False)

    async def massage_foot_up(self) -> None:
        await self._arrow(F.FOOT_MASSAGE, True)

    async def massage_foot_down(self) -> None:
        await self._arrow(F.FOOT_MASSAGE, False)

    async def massage_intensity_up(self) -> None:
        if self.protocol == 5:
            raise invalid("option_unavailable")
        await self._old_control(F.INTENSITY, 8)

    async def massage_intensity_down(self) -> None:
        if self.protocol == 5:
            raise invalid("option_unavailable")
        await self._old_control(F.INTENSITY, 9)

    @property
    def supports_massage_intensity_step_control(self) -> bool:
        return self.supports_massage and self.protocol in (1, 2)

    async def massage_toggle(self) -> None:
        if not self.supports_massage_toggle_control:
            raise invalid("option_unavailable")
        await self._old_control(F.MASSAGE, 3)

    async def set_massage(self, enabled: bool) -> None:
        if self.protocol not in (1, 5) or not self.supports_massage:
            raise invalid("option_unavailable")
        if self.protocol == 5:
            await self._one(
                F.MASSAGE, 3 if enabled else 4, query=F.MASSAGE, updates=(MASSAGE(enabled),)
            )
        else:
            await self._old_control(F.MASSAGE, 3 if enabled else 4)

    async def massage_off(self) -> None:
        await self.set_massage(False)

    @property
    def supports_massage_timer(self) -> bool:
        return self.supports_massage and self.profile.massage_timer

    @property
    def massage_timer_options(self) -> list[int]:
        return [10, 20, 30]

    @property
    def massage_timer_can_turn_off(self) -> bool:
        return False

    async def set_massage_timer(self, minutes: int) -> None:
        if not self.supports_massage_timer or minutes not in self.massage_timer_options:
            raise invalid("option_unavailable")
        if self.protocol == 5:
            await self._one(F.TIMER, minutes // 10 + 9, query=F.MASSAGE)
        else:
            await self._old_control(F.TIMER, minutes // 10 + 9)

    async def change_timer(self, increase: bool) -> None:
        if not self.supports_massage_timer or self.protocol not in (3, 4, 5):
            raise invalid("option_unavailable")
        if self.protocol == 5:
            await self._one(F.TIMER, 8 if increase else 9, query=F.MASSAGE)
        else:
            await self._old_control(F.TIMER, 8 if increase else 9)

    @property
    def _wave_max(self) -> int:
        return 3 if self.protocol == 2 else self.profile.wave_max

    def _state_key[T](self, key: StateKey[T]) -> StateKey[T]:
        return (
            sided(key, self.command_side)
            if self.profile.key == "cb24_ab" and self.command_side in ("left", "right")
            else key
        )

    async def set_wave(self, value: float) -> None:
        value = _range(value, 1, self._wave_max)
        if self.protocol == 5:
            await self._one(F.WAVE, value + 9, query=F.MASSAGE)
        else:
            await self._old_control(F.WAVE, value + 9)

    @property
    def supports_clock_sync(self) -> bool:
        return self.protocol != 1

    async def sync_clock(self) -> None:
        if not self.supports_clock_sync:
            raise invalid("option_unavailable")
        await self._write(
            self._capture_link(),
            self.profile.encode(F.CLOCK, motors=self._motors, now=dt_util.now()),
        )

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        if self.protocol == 1 or self.profile.key.startswith("headboard"):
            return None
        choices = app.P4_WAKE_ACTIONS if self.protocol == 4 else app.WAKE_ACTIONS
        choices = {
            name: code
            for name, code in choices.items()
            if name != "memory_2" or self.memory_slot_count >= 2
        }
        return AlarmCapability(
            wake_actions=tuple(choices), weekdays=True, requires_wake_action=True, resource="*"
        )

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        capability = self.alarm_capability
        if capability is None or alarm.enabled and alarm.wake_action not in capability.wake_actions:
            raise invalid("option_unavailable")
        _range(alarm.hour, 0, 23)
        _range(alarm.minute, 0, 59)
        repeat = 128 | sum(1 << ((day + 1) % 7) for day in alarm.weekdays)
        kinds = app.P4_WAKE_ACTIONS if self.protocol == 4 else app.WAKE_ACTIONS
        payload = (
            bytes((alarm.hour, alarm.minute, repeat, kinds[alarm.wake_action]))
            if alarm.enabled
            else None
        )
        frame = self._frame(F.ALARM, 3 if alarm.enabled else 4, payload)
        link = self._capture_link()
        if alarm.enabled:
            started = 0.0

            def dispatched() -> None:
                nonlocal started
                started = asyncio.get_running_loop().time()

            clock = self.profile.encode(
                F.CLOCK, motors=self._motors, side=self._selector(), now=alarm.reference_time
            )
            if not await self._write(link, clock, preparation=True, before_dispatch=dispatched):
                return
            await asyncio.sleep(max(0, started + 0.3 - asyncio.get_running_loop().time()))
        if await self._write(link, frame):
            await self._write(link, self._frame(F.ALARM, 5), preparation=True)

    async def query_alarm(self) -> None:
        if self.alarm_capability is None:
            raise invalid("option_unavailable")
        await self._write(self._capture_link(), self._frame(F.ALARM, 5))

    async def _sonic_action(
        self,
        function: F,
        sub: int = 0,
        data: bytes | None = None,
        *,
        updates: tuple[StateUpdate, ...] = (),
    ) -> None:
        if not self._sonic or self.protocol != 5:
            raise invalid("option_unavailable")
        await self._one(function, sub, data, query=F.SONIC, updates=updates)

    async def set_sonic(self, enabled: bool) -> None:
        await self._sonic_action(F.SONIC, 3 if enabled else 4, updates=(SONIC(enabled),))

    async def set_sonic_level(self, zone: str, level: float) -> None:
        value = _range(level, 0, 3)
        s = self._parser().state
        head, foot = (value, s.foot_intensity) if zone == "head" else (s.head_intensity, value)
        _range(head, 0, 3)
        _range(foot, 0, 3)
        await self._sonic_action(
            F.SONIC_INTENSITY, data=bytes((0, 4, 6, 8)[v] for v in (head, foot))
        )

    async def set_sonic_wave(self, value: float) -> None:
        await self._sonic_action(F.SONIC_WAVE, data=bytes((_range(value, 0, 6),)))

    async def set_sonic_mode(self, option: str) -> None:
        if option not in ("normal", "acoustic"):
            raise invalid("option_unavailable")
        await self._sonic_action(F.SONIC_MODE, 6, bytes((int(option == "acoustic"),)))

    async def set_sonic_timer(self, option: str) -> None:
        if option not in ("10", "20", "30"):
            raise invalid("option_unavailable")
        await self._sonic_action(F.SONIC_TIMER, int(option) // 10 + 9)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        buttons = [
            catalog_button(f"smartbed_save_{name}", f"Save {label}", _save(name), kind=Kind.SAVE)
            for name, label in (
                ("zero_g", "zero gravity"),
                ("lounge", "lounge"),
                ("tv", "TV"),
                ("anti_snore", "anti-snore"),
            )
            if self.supports_preset_zero_g and (self.protocol != 4 or name not in ("tv", "lounge"))
        ]
        # Old long recall is the app's only save gesture. Expose it with
        # confirmation, never as a card hold that could save accidentally.
        if self.protocol != 5:
            buttons.extend(
                save_button(
                    f"smartbed_save_memory_{n}",
                    f"Save M{n}",
                    _save(f"memory_{n}"),
                )
                for n in range(1, self.memory_slot_count + 1)
            )
        if self.supports_massage:
            buttons.extend(
                catalog_button(
                    f"smartbed_wave_{direction}",
                    f"{label} massage wave",
                    _wave_arrow(increase),
                    kind=Kind.MASSAGE,
                    hold=ControllerHoldSpec(
                        f"smartbed_wave_{direction}", release_delay_ms=self.profile.release_ms
                    )
                    if self.protocol != 5
                    else None,
                )
                for direction, label, increase in (
                    ("up", "Increase", True),
                    ("down", "Decrease", False),
                )
            )
        if self.supports_massage_timer and self.protocol in (3, 4, 5):
            buttons.extend(
                catalog_button(
                    f"smartbed_timer_{direction}",
                    f"{label} massage timer",
                    _timer_arrow(increase),
                    kind=Kind.MASSAGE,
                    hold=ControllerHoldSpec(
                        f"smartbed_timer_{direction}", release_delay_ms=self.profile.release_ms
                    )
                    if self.protocol != 5
                    else None,
                )
                for direction, label, increase in (
                    ("up", "Increase", True),
                    ("down", "Decrease", False),
                )
            )
        if self.profile.key == "headboard265":
            for side, function, control in (
                ("left", F.HEAD_MASSAGE, "head"),
                ("right", F.FOOT_MASSAGE, "foot"),
            ):
                for direction, increase in (("up", True), ("down", False)):
                    buttons.append(
                        catalog_button(
                            f"smartbed_{side}_massage_{direction}",
                            f"{'Increase' if increase else 'Decrease'} {side} massage",
                            _massage_arrow(function, increase),
                            kind=Kind.MASSAGE,
                            hold=ControllerHoldSpec(
                                f"massage_{control}_{direction}",
                                release_delay_ms=self.profile.release_ms,
                            ),
                        )
                    )
        if self.alarm_capability is not None:
            buttons.append(
                ControllerButtonSpec(
                    "smartbed_alarm_refresh",
                    "Refresh alarm",
                    lambda c: cast(OkinCB24Controller, c).query_alarm(),
                    "mdi:alarm",
                    translation_key="smartbed_alarm_refresh",
                    diagnostic=True,
                )
            )
        return unique_buttons(buttons)

    @property
    def controller_number_specs(self) -> tuple[ControllerNumberSpec, ...]:
        result: list[ControllerNumberSpec] = []
        if self.supports_massage:
            result.append(
                ControllerNumberSpec(
                    "smartbed_wave",
                    "smartbed_wave",
                    self._state_key(WAVE),
                    1,
                    self._wave_max,
                    1,
                    lambda c, v: cast(OkinCB24Controller, c).set_wave(v),
                    card=CARD_MASSAGE,
                )
            )
        if self.profile.key == "headboard265":
            result.extend(
                (
                    ControllerNumberSpec(
                        "smartbed_left_massage",
                        "smartbed_left_massage",
                        massage_intensity("head"),
                        1,
                        3,
                        1,
                        lambda c, v: cast(OkinCB24Controller, c).set_massage_intensity(
                            "head", int(v)
                        ),
                        card=CARD_MASSAGE,
                    ),
                    ControllerNumberSpec(
                        "smartbed_right_massage",
                        "smartbed_right_massage",
                        massage_intensity("foot"),
                        1,
                        3,
                        1,
                        lambda c, v: cast(OkinCB24Controller, c).set_massage_intensity(
                            "foot", int(v)
                        ),
                        card=CARD_MASSAGE,
                    ),
                )
            )
        if self._sonic:
            result.extend(
                (
                    ControllerNumberSpec(
                        "smartbed_sonic_head",
                        "smartbed_sonic_head",
                        SONIC_HEAD,
                        0,
                        3,
                        1,
                        lambda c, v: cast(OkinCB24Controller, c).set_sonic_level("head", v),
                        card=CARD_MASSAGE,
                    ),
                    ControllerNumberSpec(
                        "smartbed_sonic_foot",
                        "smartbed_sonic_foot",
                        SONIC_FOOT,
                        0,
                        3,
                        1,
                        lambda c, v: cast(OkinCB24Controller, c).set_sonic_level("foot", v),
                        card=CARD_MASSAGE,
                    ),
                    ControllerNumberSpec(
                        "smartbed_sonic_wave",
                        "smartbed_sonic_wave",
                        SONIC_WAVE,
                        0,
                        6,
                        1,
                        lambda c, v: cast(OkinCB24Controller, c).set_sonic_wave(v),
                        card=CARD_MASSAGE,
                    ),

                )
            )
        return tuple(result)

    @property
    def controller_select_specs(self) -> tuple[ControllerSelectSpec, ...]:
        if not self._sonic:
            return ()
        return (
            ControllerSelectSpec(
                "smartbed_sonic_mode",
                "smartbed_sonic_mode",
                SONIC_MODE,
                ("normal", "acoustic"),
                lambda c, v: cast(OkinCB24Controller, c).set_sonic_mode(v),
                card=CARD_MASSAGE,
            ),
            ControllerSelectSpec(
                "smartbed_sonic_timer",
                "smartbed_sonic_timer",
                SONIC_TIMER,
                ("10", "20", "30"),
                lambda c, v: cast(OkinCB24Controller, c).set_sonic_timer(v),
                card=CARD_MASSAGE_TIMER,
            ),
        )

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        specs: list[ControllerSwitchSpec] = []
        if self.supports_massage and self.protocol in (1, 5):
            specs.append(
                ControllerSwitchSpec(
                    "smartbed_massage",
                    "smartbed_massage",
                    lambda c, v: cast(OkinCB24Controller, c).set_massage(v),
                    MASSAGE,
                    assumed_state=self.protocol == 5,
                    card=CARD_MASSAGE,
                )
            )
        if self._sonic:
            specs.extend(
                (
                    ControllerSwitchSpec(
                        "smartbed_sonic",
                        "smartbed_sonic",
                        lambda c, v: cast(OkinCB24Controller, c).set_sonic(v),
                        SONIC,
                        assumed_state=True,
                        card=CARD_MASSAGE,
                    ),

                )
            )
        return tuple(specs)

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            (
                ControllerStateSensorSpec(
                    "smartbed_alarm_time",
                    "smartbed_alarm_time",
                    self._state_key(ALARM_TIME),
                    "mdi:alarm",
                    attribute_keys=(self._state_key(ALARM_ACTION), self._state_key(ALARM_REPEAT)),
                ),
            )
            if self.alarm_capability
            else ()
        )

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return (
            (
                ControllerStateBinarySensorSpec(
                    "smartbed_alarm_on", "smartbed_alarm_on", self._state_key(ALARM_ON), "mdi:alarm"
                ),
            )
            if self.alarm_capability
            else ()
        )

    def _publish(self, parser: Parser, side: int) -> None:
        s, changed = parser.state, parser.changed
        logical_side = {1: "left", 2: "right"}.get(side)

        # Keep each side's native state independent on the single receiver.
        def send(update: StateUpdate) -> None:
            key = AnyStateKey(f"{update.key}_{logical_side}") if logical_side else update.key
            if logical_side is not None or self._feedback_side == 0:
                self.forward_controller_state_updates(StateUpdate(key, update.value))
            if side == self._feedback_side and logical_side is not None:
                self.forward_controller_state_updates(update)

        if self.protocol in (1, 2) and changed.intersection(("head_intensity", "foot_intensity")):
            send(
                massage_intensity("all")(
                    s.head_intensity if s.head_intensity == s.foot_intensity else None
                )
            )
        if "head_intensity" in changed:
            send(massage_intensity("head")(s.head_intensity))
        if "foot_intensity" in changed:
            send(massage_intensity("foot")(s.foot_intensity))
        if "massage_time" in changed:
            send(
                MASSAGE_TIMER_MINUTES(
                    s.massage_time * 10
                    if self.protocol == 5 and s.massage_time in (1, 2, 3)
                    else s.massage_time
                )
            )
        if "massage_wave" in changed:
            send(
                WAVE(
                    (s.massage_wave + 1 if self.protocol in (2, 3, 4) else s.massage_wave)
                    if 1
                    <= (s.massage_wave + 1 if self.protocol in (2, 3, 4) else s.massage_wave)
                    <= self._wave_max
                    else None
                )
            )
        if "massage_on" in changed:
            send(MASSAGE(s.massage_on))
        if "light_on" in changed:
            send(UNDER_BED_LIGHTS_ON(s.light_on))
        if changed.intersection(
            ("alarm_hour", "alarm_min", "alarm_on", "alarm_repeat", "alarm_type")
        ):
            send(
                ALARM_TIME(
                    f"{s.alarm_hour:02d}:{s.alarm_min:02d}"
                    if 0 <= s.alarm_hour <= 23 and 0 <= s.alarm_min <= 59
                    else None
                )
            )
            send(ALARM_ON(s.alarm_on))
            send(ALARM_REPEAT(s.alarm_repeat))
            send(
                ALARM_ACTION(
                    next((k for k, v in app.WAKE_ACTIONS.items() if v == s.alarm_type), None)
                )
            )
        if self._sonic and parser.sonic_received:
            send(SONIC_HEAD(s.head_intensity))
            send(SONIC_FOOT(s.foot_intensity))
            send(SONIC_WAVE(s.massage_wave))
            send(SONIC_MODE({0: "normal", 1: "acoustic"}.get(s.sonic_massage_mode)))
            send(SONIC_TIMER(str(s.massage_time * 10) if s.massage_time in (1, 2, 3) else None))

    async def _query_page(self, link: Link, page: int) -> None:
        self._check_link(link)
        self._configuration_active = True
        self._parsers[0].state.has_sonic_massage = False
        await self._write(link, self._frame(F.CONFIGURATION, data=bytes((page,))), preparation=True)

    def _schedule_page(self, link: Link, page: int) -> None:
        task = asyncio.create_task(self._query_page(link, page))
        self._tasks.add(task)

        def done(completed: asyncio.Task[None]) -> None:
            self._tasks.discard(completed)
            if not completed.cancelled():
                completed.exception()  # A stale-link error must not escape an old callback.

        task.add_done_callback(done)

    @property
    def requires_notification_channel(self) -> bool:
        return True

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._capture_link()
        if self._notifying:
            return

        def received(_sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (
                self._link is not link
                or self.client is not link.client
                or not link.client.is_connected
            ):
                return
            raw = bytes(data)
            self.forward_raw_notification(str(link.notify.uuid), raw)
            for side, parser in self._parsers.items():
                if side and self.profile.key not in ("cb24_ab", "dacheng"):
                    continue
                parser.feed(raw, side)
                self._publish(parser, side)
                if "light_on" in parser.changed:
                    self._light_received.set()
            parser = self._parsers[0]
            if (
                self.protocol == 5
                and len(raw) >= 10
                and raw[3:5] == b"\x05\x81"
                and parser.configuration_received
            ):
                s = parser.state
                if parser.next_page >= 0:
                    self._schedule_page(link, parser.next_page)
                else:
                    self._motors, self._massage_count, self._light, self._rgb, self._sonic = (
                        s.motor_number, s.massage_num, s.have_light,
                        s.is_rgb_light, s.has_sonic_massage,
                    )
                    self._massage = self._massage_count > 0
                    self._configuration_active = False
                    if self._session is not None and self._session.is_current():
                        self._session.persist_capability_snapshot()

        async with self._ble_lock:
            self._check_link(link)
            await link.client.start_notify(link.notify, received)
        self._check_link(link)
        self._notifying = True

    async def async_discover_capabilities(self) -> None:
        self._capture_link()

    async def async_on_connect(self, session: ControllerSession) -> None:
        self._session = session
        await self.start_notify()
        link = self._capture_link()
        await asyncio.sleep(0.2)
        if self.protocol == 5:
            await self._query_page(link, 0)
            await self._write(link, self._frame(F.LIGHT, 5), preparation=True)
        else:
            session.persist_capability_snapshot()

    @property
    def capability_snapshot_policy(self) -> CapabilitySnapshotPolicy:
        return CapabilitySnapshotPolicy(deferred_reload=True)

    def capability_snapshot(self) -> dict[str, object]:
        return {
            "profile": self.profile.key,
            "motors": self._motors,
            "massage": self._massage,
            "massage_count": self._massage_count,
            "light": self._light,
            "rgb": self._rgb,
            "sonic": self._sonic,
        }

    async def stop_notify(self) -> None:
        link, notifying, tasks = self._link, self._notifying, tuple(self._tasks)
        self.on_disconnect()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if link and notifying and link.client.is_connected:
            async with self._ble_lock:
                await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self._link, self._notifying, self._session = None, False, None
        self._configuration_active = False
        self._light_received.clear()
        for task in self._tasks:
            task.cancel()
        self._parsers = {side: Parser(self.profile.key) for side in (0, 1, 2)}
        all_keys: tuple[AnyStateKey, ...] = (
            *ALL,
            UNDER_BED_LIGHTS_ON,
            MASSAGE_TIMER_MINUTES,
            massage_intensity("head"),
            massage_intensity("foot"),
            massage_intensity("all"),
        )
        for side in (None, "left", "right"):
            self.forward_controller_state_updates(
                *(
                    StateUpdate(AnyStateKey(f"{key}_{side}" if side else key), None)
                    for key in all_keys
                )
            )

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "profile": self.profile.key,
            "protocol": self.protocol,
            "hardware": "UNVERIFIED",
            "write_mode": "discovered GATT properties",
            "capabilities": self.capability_snapshot(),
            "state": asdict(self._parser().state),
            "malformed_replies": self._parser().malformed,
        }


def _move(function: F, subfunction: int) -> MotorCommandCallable:
    async def run(controller: BedController) -> None:
        await cast(OkinCB24Controller, controller)._hold(function, subfunction)

    return run


def _save(name: str) -> MotorCommandCallable:
    async def run(controller: BedController) -> None:
        await cast(OkinCB24Controller, controller).save(name)

    return run


def _massage_arrow(function: F, increase: bool) -> MotorCommandCallable:
    async def run(controller: BedController) -> None:
        await cast(OkinCB24Controller, controller)._arrow(function, increase)

    return run


def _wave_arrow(increase: bool) -> MotorCommandCallable:
    async def run(controller: BedController) -> None:
        await cast(OkinCB24Controller, controller)._arrow(F.WAVE, increase)

    return run


def _timer_arrow(increase: bool) -> MotorCommandCallable:
    async def run(controller: BedController) -> None:
        await cast(OkinCB24Controller, controller).change_timer(increase)

    return run



async def build_controller(ctx: BuildContext) -> OkinCB24Controller:
    snapshot = ctx.stored_capabilities("okin_cb24")
    variant = receiver_variant(ctx.data, ctx.variant)
    selected = select_profile(
        variant or "auto",
        ctx.data.get(CONF_BLE_DEVICE_NAME, ctx.device_name),
        motors=ctx.data.get(CONF_MOTOR_COUNT, ctx.coordinator.motor_count),
    )
    return OkinCB24Controller(
        ctx.coordinator,
        ctx.data.get(CONF_CB24_BED_SELECTION, 0),
        selected.profile,
        motors=selected.motors,
        massage=selected.massage,
        light=selected.light,
        massage_count=selected.massage_count,
        snapshot=snapshot,
    )
