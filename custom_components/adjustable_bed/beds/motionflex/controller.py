"""MotionFlex's explicit Motion products and exact-client BLE sessions."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, replace
from functools import partial
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability, AlarmRequest
from ...card import CARD_LIGHT_TOGGLE, CARD_LIGHTING
from ...codec import richmat as codec
from ...command_scheduler import note_frame_written
from ...controller_state import StateKey
from ...errors import invalid
from ...profiles.motionflex import LIGHT_DELAY_S, MENU_DELAY_S, PRODUCTS, REFRESH_MS
from ...profiles.richmat import Button
from ...state_keys import LIGHT_TIMER_OPTION, MASSAGE_TIMER_MINUTES, UNDER_BED_LIGHTS_RGB
from ..base import BedController, require_controller
from ..builder import BuildContext
from ..cancellation import settled
from ..catalog_buttons import as_save, catalog_button
from ..entity_specs import (
    ControllerButtonSpec,
    MotorControlSpec,
    PositionNumberSpec,
)
from ..lifecycle import ControllerSession
from ..richmat.controller import RichmatProfileController
from .receive import Stream, Value, parse

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator

ALARM = StateKey[dict[str, object] | None]("motionflex_alarm")


@dataclass(frozen=True)
class Link:
    client: BleakClient
    tx: BleakGATTCharacteristic
    rx: BleakGATTCharacteristic
    compact: bool
    generation: int


def select_link(client: BleakClient, generation: int) -> Link:
    """First write/notify handles and last matching service's encoding are independent."""
    tx = rx = None
    compact = False
    transports = {
        codec.TRANSPORTS[k].service_uuid.lower(): codec.TRANSPORTS[k]
        for k in PRODUCTS["sn300"].wire.transports
    }
    for service in client.services:
        transport = transports.get(service.uuid.lower())
        if transport is None:
            continue
        compact = transport.single
        for char in service.characteristics:
            if (
                tx is None
                and char.uuid.lower() == transport.write_uuid.lower()
                and "write" in char.properties
            ):
                tx = char
            if rx is None and "notify" in char.properties:
                rx = char
    if tx is None or rx is None:
        raise ValueError("MotionFlex requires a supported write and notification endpoint")
    return Link(client, tx, rx, compact, generation)


async def _save(controller: BedController, *, code: int) -> None:
    await require_controller(controller, MotionFlexController).save_preset(code)


class MotionFlexController(RichmatProfileController):
    """Shared fixed-table actions with app-specific gating and pinned cleanup."""

    def __init__(self, coordinator: AdjustableBedCoordinator, *, product: str) -> None:
        if product not in PRODUCTS:
            raise ValueError("Choose MotionFlex SN300, SN500 or HC800")
        self.product = PRODUCTS[product]
        self.model = product
        super().__init__(
            coordinator, self.product.wire, char_uuid=codec.TRANSPORTS["w1"].write_uuid
        )
        self._link: Link | None = None
        self._resume_link: Link | None = None
        self._notifying = False
        self._stream = Stream()
        self._events: dict[str, object] = {}
        self._last_event: str | None = None
        self._alarm: dict[str, object] | None = None
        self._pending_alarm: dict[str, object] | None = None
        self._alarm_ack: str | None = None
        self._alarm_complete = False
        self._alarm_ack_armed = False
        self._next_write = 0.0

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return True

    @property
    def has_dynamic_buttons(self) -> bool:
        return True

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        link = self._link
        return {
            "app": "com.richmat.motionflex",
            "model": self.model,
            "encoding": "nordic" if link and link.compact else "wilinke",
            "write_handle": link.tx.handle if link else None,
            "notify_handle": link.rx.handle if link else None,
            "last_event": self._last_event,
            "alarm": deepcopy(self._alarm),
            "observed": deepcopy(self._events),
        }

    def _owns_state(self) -> bool:
        owner = self._coordinator.controller
        return not isinstance(owner, BedController) or owner is self

    def _publish(self) -> None:
        if not self._owns_state():
            return
        self.forward_controller_state_updates(ALARM(deepcopy(self._alarm)))

    def _clear(self) -> None:
        self._events.clear()
        self._stream = Stream()
        self._last_event = None
        self._pending_alarm = self._alarm = None
        self._alarm_ack = None
        self._alarm_complete = False
        self._alarm_ack_armed = False
        self._publish()
        if self._owns_state():
            self.forward_controller_state_updates(
                LIGHT_TIMER_OPTION(None), MASSAGE_TIMER_MINUTES(None), UNDER_BED_LIGHTS_RGB(None)
            )

    async def async_discover_capabilities(self) -> None:
        if self._link is not None:
            await self.stop_notify()
        self._link = None
        self._resume_link = None
        self._notifying = False
        self._clear()
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("MotionFlex is not connected")
        self._link = select_link(client, self._coordinator.connection_generation)
        self._char_uuid = self._link.tx.uuid
        self._next_write = 0

    async def async_on_connect(self, session: ControllerSession) -> None:
        # HA creates its connection generation after capability discovery.
        link = self._link
        if link is None or self.client is not link.client or not session.is_current():
            raise ConnectionError("MotionFlex startup session changed")
        self._link = replace(link, generation=self._coordinator.connection_generation)
        await session.async_start_notify()

    def _current(self) -> Link:
        link = self._link
        if link is None:
            raise ConnectionError("MotionFlex session is not ready")
        self._check(link)
        if self.command_side not in (None, "both"):
            raise ValueError("MotionFlex's selected products do not expose split-side controls")
        return link

    def _check(self, link: Link, *, cleanup: bool = False) -> None:
        if not link.client.is_connected:
            raise ConnectionError("MotionFlex client disconnected")
        if not cleanup and (
            self._link is not link
            or self.client is not link.client
            or self._coordinator.connection_generation != link.generation
            or isinstance(self._coordinator.controller, BedController)
            and self._coordinator.controller is not self
        ):
            raise ConnectionError("MotionFlex session changed")

    async def _write(
        self,
        link: Link,
        packet: bytes,
        *,
        cleanup: bool = False,
        cancel: asyncio.Event | None = None,
        dispatch: Callable[[], None] | None = None,
    ) -> None:
        cancel = cancel if cancel is not None else self._coordinator.cancel_command
        async with self._ble_lock:
            self._check(link, cleanup=cleanup)
            if not cleanup and cancel.is_set():
                raise asyncio.CancelledError
            await asyncio.sleep(max(0, self._next_write - asyncio.get_running_loop().time()))
            self._check(link, cleanup=cleanup)
            if not cleanup and cancel.is_set():
                raise asyncio.CancelledError
            if dispatch is not None:
                dispatch()
            response = "write-without-response" not in link.tx.properties
            self._record_command_trace(
                link.tx.uuid, packet, response=response, characteristic=link.tx
            )

            async def write_and_record() -> None:
                self._next_write = asyncio.get_running_loop().time() + REFRESH_MS / 1000
                await link.client.write_gatt_char(link.tx, packet, response=response)
                note_frame_written(asyncio.Event() if cleanup else cancel)

            # Never hand the command lane to STOP while this write is in flight.
            await settled(write_and_record(), eager_start=True)
            self._check(link, cleanup=cleanup)
            if not cleanup and cancel.is_set():
                raise asyncio.CancelledError

    def _frame(self, link: Link, code: int) -> bytes:
        return codec.function(code, single=link.compact)

    async def _release(self, link: Link) -> None:
        if link.client.is_connected:
            await settled(self._write(link, self._frame(link, codec.STOP), cleanup=True))

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = REFRESH_MS,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._current()
        for index in range(repeat_count):
            if index:
                await asyncio.sleep(repeat_delay_ms / 1000)
            await self._write(link, command, cancel=cancel_event)

    def _build_command(self, command_byte: int) -> bytes:
        return self._frame(self._current(), command_byte)

    async def _send(self, button: Button) -> None:
        link = self._current()
        packet = self._frame(link, self._code(button))
        # Massage and the basic-light callbacks release with STOP. Advanced
        # close is a distinct one-shot, as are preset recall and Save.
        release = button == "light_toggle" or button.startswith("massage_")
        try:
            await self._write(link, packet)
        finally:
            if release:
                await self._release(link)

    async def _move_with_stop(self, command_byte: int) -> None:
        link = self._current()
        count = self.leased_hold_refreshes(REFRESH_MS) or self._coordinator.motor_pulse_count
        try:
            for _ in range(count):
                await self._write(link, self._frame(link, command_byte))
        finally:
            await self._release(link)

    async def _send_stop(self) -> None:
        await self._release(self._current())

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self.leased_hold_refreshes(
            REFRESH_MS
        ) or self._coordinator.motor_pulse_count, REFRESH_MS

    async def preset_memory(self, memory_num: int) -> None:
        if type(memory_num) is not int or not 1 <= memory_num <= self.memory_slot_count:
            raise ValueError("This MotionFlex model has no such memory")
        await super().preset_memory(memory_num)

    async def program_memory(self, memory_num: int) -> None:
        if type(memory_num) is not int or not 1 <= memory_num <= self.memory_slot_count:
            raise ValueError("This MotionFlex model has no such memory")
        await super().program_memory(memory_num)

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(key for key in self.profile.codes or {} if key.endswith(("_up", "_down")))

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or type(duration_ms) is not int
            or not 0 < duration_ms <= 60000
        ):
            raise ValueError("Choose a supported MotionFlex motor and 1..60000 ms")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        link = self._current()
        code = next(code for key, code in (self.profile.codes or {}).items() if key == control)
        deadline = asyncio.get_running_loop().time() + duration_ms / 1000
        try:
            while asyncio.get_running_loop().time() < deadline:
                await self._write(link, self._frame(link, code))
        finally:
            await self._release(link)

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if self._link is None and self._resume_link is not None:
            previous, self._resume_link = self._resume_link, None
            if (
                self.client is not previous.client
                or not previous.client.is_connected
                or self._coordinator.connection_generation != previous.generation
                or not self._owns_state()
            ):
                raise ConnectionError("MotionFlex retained session changed")
            # Never reactivate an identity captured by a retired callback.
            self._link = replace(previous)
        link = self._current()
        if self._notifying:
            return
        self._notify_callback = callback

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if (
                self._link is not link
                or self.client is not link.client
                or not link.client.is_connected
                or self._coordinator.connection_generation != link.generation
                or isinstance(self._coordinator.controller, BedController)
                and self._coordinator.controller is not self
            ):
                return
            self.forward_raw_notification(sender.uuid, bytes(data))
            for packet in self._stream.feed(bytes(data)):
                values = parse(packet)
                if values is not None:
                    self._received(values)

        try:
            async with self._ble_lock:
                self._notifying = True
                await settled(link.client.start_notify(link.rx, receive))
            self._check(link)
            self._notifying = True
            await self._write(
                link, codec.function(0, action="deviceFunctionItemExitLimit", single=link.compact)
            )
            await self._sync(link)
            for action in ("deviceFunctionItemCheckClock", "deviceFunctionItemCheckLight"):
                await asyncio.sleep(MENU_DELAY_S)
                await self._write(link, codec.function(1, action=action, single=link.compact))
        except BaseException:
            await self._retire(link, notifying=True)
            raise

    def on_disconnect(self) -> None:
        self._link = None
        self._resume_link = None
        self._notifying = False
        self._notify_callback = None
        self._clear()

    async def stop_notify(self) -> None:
        link = self._link
        if link is not None:
            await self._retire(link, notifying=self._notifying)

    async def _retire(self, link: Link, *, notifying: bool) -> None:
        # Fence callbacks before awaiting the old subscription's removal.
        if self._link is link:
            resumable = (
                self.client is link.client
                and link.client.is_connected
                and self._coordinator.connection_generation == link.generation
                and self._owns_state()
            )
            self.on_disconnect()
            if resumable:
                self._resume_link = link
        if notifying and link.client.is_connected:
            async with self._ble_lock:
                await settled(link.client.stop_notify(link.rx))

    def _received(self, values: dict[str, Value]) -> None:
        event = values.get("event")
        if isinstance(event, str):
            self._last_event = event
            self._events[event] = True
            if (
                event in ("alarm_add_success", "alarm_cancel_success")
                and self._pending_alarm is not None
                and self._alarm_ack_armed
            ):
                self._alarm_ack = event
                self._ack_alarm()
        else:
            # Do not assign synthetic motor indexes to physical positions.
            self._events.update(values)
            self._last_event = "selected_reply"
        color = values.get("rgb")
        if isinstance(color, list) and len(color) == 3:
            self.forward_controller_state_updates(
                UNDER_BED_LIGHTS_RGB((color[0], color[1], color[2]))
            )
        self._publish()

    def _ack_alarm(self) -> None:
        pending = self._pending_alarm
        if (
            pending is not None
            and self._alarm_complete
            and self._alarm_ack
            == ("alarm_add_success" if pending["enabled"] else "alarm_cancel_success")
        ):
            self._alarm = pending
            self._pending_alarm = None

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return ()

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        axes = [("back", "head_up", "head_down"), ("legs", "feet_up", "feet_down")]
        if self.has_lumbar_support:
            axes.append(("lumbar", "lumbar_up", "lumbar_down"))
        if self.has_pillow_support:
            axes.append(("pillow", "pillow_up", "pillow_down"))
        if self.model == "sn300":
            axes.append(("head_feet", "head_feet_up", "head_feet_down"))

        def move(key: str):
            async def run(controller: BedController) -> None:
                target = require_controller(controller, MotionFlexController)
                code = next(
                    code for name, code in (target.profile.codes or {}).items() if name == key
                )
                await target._move_with_stop(code)

            return run

        return tuple(
            MotorControlSpec(
                key,
                key,
                move(up),
                move(down),
                lambda c: c.stop_all(),
                scheduler_resource="*",
                stop_scope="side",
            )
            for key, up, down in axes
        )

    async def move_head_feet_up(self) -> None:
        await self._move("head_feet_up")

    async def move_head_feet_down(self) -> None:
        await self._move("head_feet_down")

    async def preset_flat(self) -> None:
        link = self._current()
        try:
            await self._write(link, self._frame(link, self._code("flat")))
        finally:
            await self._release(link)

    async def save_preset(self, code: int) -> None:
        if code not in dict(self.product.saves).values():
            raise ValueError("This MotionFlex model has no such preset Save")
        await self.write_command(self._build_command(code))

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        # Keep the existing basic-toggle identity out of the RGB power path.
        toggle = catalog_button("toggle_light", "Toggle under-bed light", lambda c: c.lights_toggle())
        assert toggle is not None
        specs = [replace(
            toggle, translation_key="toggle_light", translation_placeholders=None,
            card=CARD_LIGHT_TOGGLE, icon="mdi:lightbulb",
        )]
        for name, code in self.product.saves:
            spec = catalog_button(
                "motionflex_save_" + name,
                "Save " + name.replace("_", " "),
                partial(_save, code=code),
            )
            assert spec is not None
            specs.append(as_save(spec))
        if self.supports_light_color_control:

            async def close(controller: BedController) -> None:
                await require_controller(controller, MotionFlexController).lights_off()

            specs.append(
                ControllerButtonSpec(
                    "motionflex_light_off", "Turn light off", close, card=CARD_LIGHTING
                )
            )
        return tuple(specs)

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def auto_enable_massage(self) -> bool:
        return True

    @property
    def supports_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_massage_timer(self) -> bool:
        return True

    @property
    def massage_timer_options(self) -> list[int]:
        return [10, 20, 30]

    async def massage_off(self) -> None:
        await self._send("massage_off")

    async def set_massage_timer(self, minutes: int) -> None:
        buttons: dict[int, Button] = {
            0: "massage_off",
            10: "massage_timer_10",
            20: "massage_timer_20",
            30: "massage_timer_30",
        }
        if type(minutes) is not int or minutes not in buttons:
            raise ValueError("Choose Off, 10, 20 or 30 minutes")
        link = self._current()
        with self.sent_state(
            MASSAGE_TIMER_MINUTES(minutes),
            is_current=lambda: self._link is link and self._owns_state(),
        ):
            await self._send(buttons[minutes])

    def _light_ready(self) -> None:
        if not self._events.get("light_capability"):
            raise invalid("motionflex_light_not_reported")

    @property
    def supports_discrete_light_control(self) -> bool:
        # The RGB entity uses the verified close; authorization stays reply-gated.
        return self.supports_light_color_control

    @property
    def supports_explicit_light_on_control(self) -> bool:
        return False

    @property
    def supports_light_toggle_control(self) -> bool:
        # A retained RGB entity must not fall back to toggle on capability loss.
        return False

    @property
    def supports_light_color_control(self) -> bool:
        return bool(self._events.get("light_capability"))

    @property
    def supports_light_timer(self) -> bool:
        return self.supports_light_color_control

    @property
    def light_timer_options(self) -> list[str]:
        return ["Always On", *(f"{m} min" for m in range(1, 16))]

    async def lights_off(self) -> None:
        self._light_ready()
        await self._send("light_off")

    async def set_light_color(self, rgb_color: tuple[int, int, int]) -> None:
        self._light_ready()
        if len(rgb_color) != 3 or any(type(v) is not int or not 0 <= v <= 255 for v in rgb_color):
            raise invalid("motionflex_light_color")
        link = self._current()
        with self.sent_state(
            UNDER_BED_LIGHTS_RGB(rgb_color),
            is_current=lambda: self._link is link
            and self.client is link.client
            and link.client.is_connected
            and self._coordinator.connection_generation == link.generation
            and self._owns_state(),
        ):
            await self._write(link, codec.rgb(*rgb_color))

    async def set_light_timer(self, timer_option: str) -> None:
        self._light_ready()
        if timer_option not in self.light_timer_options:
            raise invalid("motionflex_light_timer")
        seconds = 0 if timer_option == "Always On" else int(timer_option.split()[0]) * 60
        link = self._current()
        await asyncio.sleep(LIGHT_DELAY_S)
        encoded = seconds or 65535
        with self.sent_state(
            LIGHT_TIMER_OPTION(timer_option),
            is_current=lambda: self._link is link and self._owns_state(),
        ):
            await self._write(link, codec.light_timer(encoded >> 8, encoded & 255))

    @property
    def supports_clock_sync(self) -> bool:
        return True

    async def _sync(self, link: Link) -> None:
        packets = codec.time_sync(dt_util.now(), build=codec.record_20_len, first_hex=True)
        for packet in packets:
            await self._write(link, packet)

    async def sync_clock(self) -> None:
        await self._sync(self._current())

    @property
    def alarm_capability(self) -> AlarmCapability:
        return AlarmCapability(
            wake_actions=tuple(
                k for k in ("zero_g", "anti_snore", "tv") if k in (self.profile.codes or {})
            )
            + (("memory_1",) if self.profile.memory else ()),
            requires_wake_action=True,
        )

    def validate_alarm(self, alarm: AlarmRequest) -> None:
        unused: dict[str, object] = {
            "weekdays": (),
            "slot": 1,
            "massage": False,
            "head_massage_level": 0,
            "foot_massage_level": 0,
            "massage_intensity": 1,
            "massage_duration": None,
            "sleep_timer": None,
            "massage_zone": None,
            "mattress_side": None,
            "sound": "none",
            "light": False,
            "confirm_custom_position": False,
            "record_identity": None,
        }
        if any(
            type(getattr(alarm, key)) is not type(value) or getattr(alarm, key) != value
            for key, value in unused.items()
        ):
            raise ValueError("Unsupported MotionFlex alarm field")
        if (
            type(alarm.enabled) is not bool
            or type(alarm.hour) is not int
            or not 0 <= alarm.hour <= 23
            or type(alarm.minute) is not int
            or not 0 <= alarm.minute <= 59
            or alarm.reference_time.utcoffset() is None
            or alarm.enabled
            and (
                not alarm.time_provided
                or alarm.wake_action not in self.alarm_capability.wake_actions
            )
            or not alarm.enabled
            and alarm.wake_action not in ("none", *self.alarm_capability.wake_actions)
        ):
            raise ValueError(
                "MotionFlex accepts one local alarm with a model-supported wake preset"
            )
        self._alarm_packets(alarm)

    def _alarm_packets(self, alarm: AlarmRequest) -> tuple[bytes, bytes]:
        if not alarm.enabled:
            return codec.countdown(0, 0)
        # Use the service's selected occurrence but reject a stale queued request.
        # Never clamp a negative helper result into a different wire operation.
        start = dt_util.now().replace(second=0, microsecond=0)
        minutes = int((alarm.occurrence().timestamp() - start.timestamp()) / 60)
        if type(minutes) is not int or not 1 <= minutes <= 65535:
            raise ValueError("MotionFlex alarm countdown must be 1..65535 minutes")
        code = (
            self.profile.memory[0][0]
            if alarm.wake_action == "memory_1"
            else next(
                code for key, code in (self.profile.codes or {}).items() if key == alarm.wake_action
            )
        )
        return codec.countdown(minutes, code)

    def _arm_alarm_ack(self) -> None:
        self._alarm_ack_armed = True

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        self.validate_alarm(alarm)
        link = self._current()
        packets = self._alarm_packets(alarm)
        self._pending_alarm = {
            "enabled": alarm.enabled,
            "hour": alarm.hour,
            "minute": alarm.minute,
            "wake_action": alarm.wake_action,
        }
        self._alarm_complete = False
        self._alarm_ack_armed = False
        self._alarm_ack = None
        try:
            for index, packet in enumerate(packets):
                await self._write(
                    link, packet, dispatch=self._arm_alarm_ack if index == 1 else None
                )
            self._alarm_complete = True
            self._ack_alarm()
            self._publish()
        except BaseException:
            self._pending_alarm = self._alarm = None
            self._alarm_complete = False
            self._alarm_ack_armed = False
            self._alarm_ack = None
            self._publish()
            raise


async def build_controller(ctx: BuildContext) -> MotionFlexController:
    return MotionFlexController(ctx.coordinator, product=ctx.variant or "")
