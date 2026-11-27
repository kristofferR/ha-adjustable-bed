"""Connection-bound Alya controls, with the app's 300 ms press/release cadence."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from ...alarm import AlarmCapability
from ...card import CARD_HIDDEN
from ...command_scheduler import current_command_context, note_frame_skipped, note_frame_written
from ...const import CONF_CB24_BED_SELECTION, CONF_HAS_MASSAGE, CONF_PROTOCOL_VARIANT
from ...errors import invalid
from ...profiles.alya import PROFILES, AlyaProfile
from ...state_keys import UNDER_BED_LIGHTS_ON
from ..base import CONTROLLER_GESTURE_RELEASE, BedController, ProfileExecution
from ..builder import BuildContext
from ..cancellation import settled
from ..catalog_buttons import Kind, catalog_button, unique_buttons
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    MotorCommandCallable,
    MotorControlSpec,
)
from .protocol import TRANSPORTS, alarm_frame, alarm_types, clock_frame, parse, query, require_roles

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...command_scheduler import CommandContext
    from ...coordinator import AdjustableBedCoordinator

_AXIS: Final = {"back": "head", "legs": "foot", "head": "headtilt", "lumbar": "lumbar"}
_WITHHELD_CONTROLS: Final = frozenset({"hpsup", "hpsdown"})


@dataclass(frozen=True)
class Session:
    client: BleakClient
    write: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic
    address: str
    response: bool


@dataclass
class Operation:
    session: Session
    side: int
    started: bool = False


def action(name: str) -> MotorCommandCallable:
    async def execute(controller: BedController) -> None:
        if not isinstance(controller, AlyaController):
            raise TypeError("This control requires Alya Smart Furnishing")
        await controller.execute(name)

    return execute


class AlyaController(ProfileExecution[AlyaProfile], BedController):
    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        profile: str,
        side: int = 0,
        has_massage: bool = True,
    ) -> None:
        super().__init__(coordinator)
        self.profile = PROFILES[profile]
        if side not in (0, 1, 2) or (side and not self.profile.side_controls):
            raise ValueError("Side selection requires Alya DACHENG five-motor layout")
        self._selection_valid = True
        self._side = side
        self._has_massage = has_massage or not self.profile.key.startswith("bluetooth_")
        self._session: Session | None = None
        self._notifying = False
        self._observed: dict[str, int | bool] = {}
        self._fragment = b""
        self._fragment_deadline = 0.0
        self._last_release: tuple[CommandContext, Session, int] | None = None

    def _unavailable(self, reason: str) -> ServiceValidationError:
        return invalid("alya_control_invalid", reason=reason)

    @property
    def control_characteristic_uuid(self) -> str:
        return TRANSPORTS[self.profile.protocol].write

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def supports_single_address_pairing(self) -> bool:
        return self.profile.side_controls

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "app": "com.okin.bedding.alya",
            "layout": self.profile.key,
            "protocol": self.profile.protocol,
            "hardware_verified": False,
            "received": dict(self._observed),
        }

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis,
                axis,
                action(_AXIS[axis] + "up"),
                action(_AXIS[axis] + "down"),
                action("stop"),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    _AXIS[axis] + "up",
                    _AXIS[axis] + "down",
                    release_button_key="alya_release",
                    stop_scope="side",
                    press_is_native=True,
                ),
            )
            for axis in self.profile.axes
        )

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, self.profile.refresh_ms

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_lounge(self) -> bool:
        return "lounge" in self.profile.commands

    @property
    def supports_preset_tv(self) -> bool:
        return "tv" in self.profile.commands

    @property
    def memory_slot_count(self) -> int:
        return 2 if "m2" in self.profile.commands else 1

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return False

    @property
    def supports_lights(self) -> bool:
        return "light" in self.profile.commands

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.supports_lights

    @property
    def supports_light_state_feedback(self) -> bool:
        return self.supports_lights and self.profile.protocol == "P1"

    @property
    def supports_clock_alarm(self) -> bool:
        return self.profile.protocol != "P1" and self.profile.key != "dacheng_2"

    @property
    def alarm_capability(self) -> AlarmCapability | None:
        if not self.supports_clock_alarm:
            return None
        return AlarmCapability(
            wake_actions=self.clock_alarm_preset_options,
            weekdays=True,
            cancel_running=True,
            resource=None,
        )

    @property
    def supports_clock_sync(self) -> bool:
        return self.supports_clock_alarm

    @property
    def clock_alarm_preset_options(self) -> tuple[str, ...]:
        return tuple(alarm_types(self.profile)) if self.supports_clock_alarm else ()

    def _massage_control(self, control: str) -> bool:
        return "intensity" in control or control.startswith(("massage-", "wave", "time"))

    @property
    def auto_enable_massage(self) -> bool:
        return self._has_massage

    @property
    def supports_massage(self) -> bool:
        return self._has_massage

    @property
    def supports_massage_timer(self) -> bool:
        return self._has_massage and bool(self.massage_timer_options)

    @property
    def massage_timer_options(self) -> list[int]:
        return [minutes for minutes in (10, 20, 30) if f"time{minutes}" in self.profile.commands]

    @property
    def massage_timer_can_turn_off(self) -> bool:
        return False

    async def set_massage_timer(self, minutes: int) -> None:
        if type(minutes) is not int or minutes not in self.massage_timer_options:
            raise self._unavailable("Unsupported massage timer")
        await self.execute(f"time{minutes}")

    @property
    def supports_massage_intensity_control(self) -> bool:
        return self._has_massage and bool(self.massage_intensity_zones)

    @property
    def massage_intensity_zones(self) -> list[str]:
        return [
            zone
            for zone, prefix in (("all", ""), ("head", "head"), ("foot", "foot"))
            if all(f"{prefix}intensity{level}" in self.profile.commands for level in (1, 2, 3))
        ]

    @property
    def massage_intensity_max(self) -> int:
        return 3

    def massage_intensity_min(self, zone: str) -> int:
        return 1

    async def set_massage_intensity(self, zone: str, level: int) -> None:
        if (
            zone not in self.massage_intensity_zones
            or type(level) is not int
            or not 1 <= level <= 3
        ):
            raise self._unavailable("Unsupported massage zone or level")
        await self.execute(f"{'' if zone == 'all' else zone}intensity{level}")

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(
            k
            for k in self.profile.commands
            if k != "stop"
            and k not in _WITHHELD_CONTROLS
            and not k.startswith("query-")
            and (self._has_massage or not self._massage_control(k))
        )

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        control = {"preset_zero_g": "zg", "preset_anti_snore": "anti"}.get(
            key, key.removeprefix("preset_")
        )
        if key.startswith("preset_memory_"):
            control = f"m{key.rsplit('_', 1)[-1]}" if "m2" in self.profile.commands else "memory"
        return (
            ControllerHoldSpec(control, release_button_key="alya_release")
            if control in self.held_control_options
            else None
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        skip = {
            *_WITHHELD_CONTROLS,
            "stop",
            "flat",
            "zg",
            "anti",
            "lounge",
            "tv",
            "memory",
            "m1",
            "m2",
            *(f"time{minutes}" for minutes in self.massage_timer_options),
            *(
                f"{prefix}intensity{level}"
                for prefix in ("", "head", "foot")
                for level in (1, 2, 3)
            ),
            *(prefix + direction for prefix in _AXIS.values() for direction in ("up", "down")),
        }
        names = {
            k: k.replace("-", " ")
            .replace("intensity", " intensity ")
            .replace("increase", " increase")
            .replace("decrease", " decrease")
            .replace("wave", "Wave ")
            .replace("time", "Timer ")
            for k in self.profile.commands
            if k not in skip and (self._has_massage or not self._massage_control(k))
        }
        names = {key: value.strip().capitalize() for key, value in names.items()}
        for key, name in {
            "unionup": "All motors up",
            "uniondown": "All motors down",
            "timer": "Massage timer cycle",
        }.items():
            if key in names:
                names[key] = name
        if self.profile.protocol != "P1":
            names["massage-on"] = "Massage toggle (app On)"
            names["massage-off"] = "Massage toggle (app Off)"
        if self._has_massage:
            names["query-massage"] = "Refresh massage report"
        if self.supports_clock_alarm:
            names["query-alarm"] = "Refresh alarm report"
        specs: list[ControllerButtonSpec] = []
        for k, name in names.items():
            spec = catalog_button(
                "alya_" + k,
                name,
                action(k),
                kind=Kind.EXTRA
                if k.startswith("query-")
                else Kind.MASSAGE
                if self._massage_control(k)
                else None,
                enabled=not k.startswith("query-"),
                diagnostic=k.startswith("query-"),
                hold=ControllerHoldSpec(k, release_button_key="alya_release")
                if k in self.held_control_options
                else None,
            )
            if spec is not None:
                specs.append(spec)
        specs.append(
            ControllerButtonSpec(
                "alya_release",
                "Release",
                action("stop"),
                translation_key="alya_release",
                release_only=True,
                card=CARD_HIDDEN,
            )
        )
        return unique_buttons(specs)

    def _side_now(self) -> int:
        side = self.command_side
        if side is not None and side not in ("both", "left", "right"):
            raise self._unavailable("Unknown logical side")
        if side in ("left", "right") and not self.profile.side_controls:
            raise self._unavailable("This layout has no independent side controls")
        return {"both": 0, "left": 1, "right": 2}.get(side, self._side) if side else self._side

    def _live(self, expected: Session | None = None) -> Session:
        session = self._session
        if (
            session is None
            or (expected is not None and expected is not session)
            or self.client is not session.client
            or not session.client.is_connected
            or self._coordinator.address != session.address
        ):
            raise ConnectionError("Alya Bluetooth session changed or disconnected")
        return session

    async def async_discover_capabilities(self) -> None:
        if not self._selection_valid:
            raise self._unavailable("Select the exact BLE type and motor layout in setup")
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Alya is disconnected")
        if self._session is not None and self._session.client is client:
            return
        write, notify = require_roles(client, self.profile.protocol)
        self.on_disconnect()
        self._session = Session(
            client, write, notify, self._coordinator.address, "write" in write.properties
        )

    def on_disconnect(self) -> None:
        self._session = None
        self._notifying = False
        self._observed.clear()
        self._fragment = b""
        self._fragment_deadline = 0.0
        self._last_release = None
        self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(None))

    @staticmethod
    async def _pause(seconds: float, cancel: asyncio.Event) -> bool:
        if cancel.is_set():
            return True
        try:
            await asyncio.wait_for(cancel.wait(), seconds)
        except TimeoutError:
            return False
        return True

    async def _send(self, operation: Operation, frame: bytes, cancel: asyncio.Event) -> None:
        async with self._ble_lock:
            self._live(operation.session)
            if cancel.is_set():
                note_frame_skipped()
                raise asyncio.CancelledError
            operation.started = True
            self._record_command_trace(
                operation.session.write.uuid,
                frame,
                response=operation.session.response,
                characteristic=operation.session.write,
            )

            async def deliver() -> None:
                async with asyncio.timeout(5):
                    await operation.session.client.write_gatt_char(
                        operation.session.write, frame, response=operation.session.response
                    )
                    note_frame_written(cancel)

            await settled(deliver(), eager_start=True)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 300,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        op = Operation(self._live(), self._side_now())
        cancel = cancel_event if cancel_event is not None else self._coordinator.cancel_command
        for i in range(repeat_count):
            if i and await self._pause(repeat_delay_ms / 1000, cancel):
                note_frame_skipped()
                return
            await self._send(op, command, cancel)

    async def _release(self, op: Operation, count: int) -> None:
        async def cleanup() -> None:
            for _ in range(count):
                await self._pause(self.profile.release_ms / 1000, asyncio.Event())
                # A release is owned by the admitted link, never its replacement.
                if (
                    self._session is not op.session
                    or self.client is not op.session.client
                    or not op.session.client.is_connected
                ):
                    return
                await self._send(
                    op,
                    self.profile.commands["stop"].encode(self.profile.protocol, op.side),
                    asyncio.Event(),
                )
            if (context := current_command_context()) is not None:
                context.cleanup_stop_sent = True
                self._last_release = (context, op.session, op.side)

        await settled(cleanup())

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self._notify_callback = callback
        session = self._live()
        if self._notifying:
            return

        def receive(sender: BleakGATTCharacteristic, raw: bytearray) -> None:
            if (
                self._session is not session
                or self.client is not session.client
                or not session.client.is_connected
            ):
                return
            data = bytes(raw)
            self.forward_raw_notification(sender.uuid, data)
            # Only the app's one known F4 FE16 split; a consumed prefix cannot
            # contaminate a later device, report or connection.
            if self.profile.device_type == "CB" or self.profile.key == "dacheng_2":
                if data.startswith(b"\xf4\xfe\x16") and len(data) <= 20:
                    self._fragment = data
                    self._fragment_deadline = asyncio.get_running_loop().time() + 1
                    return
                if asyncio.get_running_loop().time() > self._fragment_deadline:
                    self._fragment = b""
                if self._fragment and len(data) not in (10, 16):
                    data, self._fragment = self._fragment + data, b""
                    if len(data) != 23:
                        return
                else:
                    self._fragment = b""
            result = parse(self.profile, data)
            if not result:
                return
            self._observed.update(result)
            if "light" in result:
                self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(bool(result["light"])))

        await session.client.start_notify(session.notify, receive)
        self._notifying = True

    async def stop_notify(self) -> None:
        session, notifying = self._session, self._notifying
        self.on_disconnect()
        if session is not None and notifying and session.client.is_connected:
            await session.client.stop_notify(session.notify)
        self._notify_callback = None

    def _check(self, control: str) -> None:
        if control not in self.held_control_options:
            raise self._unavailable("The selected layout does not expose this control")
        if control.startswith(("time", "wave")) or "intensity" in control:
            if not (self._observed.get("head", 0) > 0 or self._observed.get("foot", 0) > 0):
                raise self._unavailable(
                    "Refresh massage state and enable massage before changing its settings"
                )

    async def _hold(self, control: str, duration_ms: int) -> None:
        self._check(control)
        op = Operation(self._live(), self._side_now())
        cancel = self._coordinator.cancel_command
        frame = self.profile.commands[control].encode(self.profile.protocol, op.side)
        count = (duration_ms + self.profile.refresh_ms - 1) // self.profile.refresh_ms
        loop = asyncio.get_running_loop()
        deadline = loop.time() + duration_ms / 1000
        axis = control in {p + d for p in (*_AXIS.values(), "union") for d in ("up", "down")}
        try:
            for i in range(count):
                if cancel.is_set() or loop.time() >= deadline:
                    note_frame_skipped()
                    break
                try:
                    await self._send(op, frame, cancel)
                except asyncio.CancelledError:
                    if i < count - 1:
                        note_frame_skipped()
                    raise
                if await self._pause(
                    min(self.profile.refresh_ms / 1000, max(0, deadline - loop.time())),
                    cancel,
                ):
                    if i < count - 1:
                        note_frame_skipped()
                    break
        finally:
            if op.started:
                try:
                    await self._release(op, 2 if axis else 1)
                finally:
                    if self._session is op.session:
                        if control == "light":
                            self._observed.pop("light", None)
                            self.forward_controller_state_updates(UNDER_BED_LIGHTS_ON(None))
                        elif self._massage_control(control):
                            for key in ("head", "foot", "massage", "minutes", "wave"):
                                self._observed.pop(key, None)
        if (
            "intensity" in control or control.startswith(("massage-", "time", "wave"))
        ) and self.profile.protocol in ("P3", "P4"):
            if not await self._pause(0.5, cancel):
                await self._send(op, query(self.profile.protocol), cancel)

    async def execute(self, control: str) -> None:
        if control == "stop":
            await self.stop_all()
        elif control.startswith("query-"):
            if control == "query-massage" and not self._has_massage:
                raise self._unavailable("This layout has no massage page")
            if control == "query-alarm" and not self.supports_clock_alarm:
                raise self._unavailable("This layout has no alarm")
            await self.write_command(query(self.profile.protocol, control == "query-alarm"))
        else:
            count, delay = self.motor_pulse_settings()
            await self._hold(control, self.leased_hold_ms(count * delay))

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        self._check(control)
        if type(duration_ms) is not int or not 0 < duration_ms <= 30000:
            raise self._unavailable("Hold duration must be 1 to 30000 ms")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self._hold(control, self.leased_hold_ms(duration_ms))

    async def stop_all(self) -> None:
        if CONTROLLER_GESTURE_RELEASE.get():
            return
        op = Operation(self._live(), self._side_now())
        context = current_command_context()
        if context is not None and self._last_release is not None:
            released, session, side = self._last_release
            # A side-only cleanup cannot acknowledge a wider or opposite STOP.
            if (
                released.cleanup_stop_sent
                and session is op.session
                and side in (0, op.side)
                and (released is context or any(c is released for c in context.preempted_contexts))
            ):
                if released is not context:
                    released.cleanup_stop_sent = False
                return
        await self._release(op, 1)

    async def sync_clock(self) -> None:
        if not self.supports_clock_sync:
            raise self._unavailable("This layout has no clock")
        await self.write_command(clock_frame(self.profile.protocol, dt_util.now()))

    async def configure_clock_alarm(
        self,
        *,
        enabled: bool,
        weekdays: Sequence[int],
        hour: int,
        minute: int,
        preset: str,
        head_level: int = 0,
        foot_level: int = 0,
    ) -> None:
        if (
            not self.supports_clock_alarm
            or preset not in self.clock_alarm_preset_options
            or type(hour) is not int
            or not 0 <= hour < 24
            or type(minute) is not int
            or not 0 <= minute < 60
            or any(type(d) is not int or not 0 <= d < 7 for d in weekdays)
            or head_level
            or foot_level
        ):
            raise self._unavailable("Choose a supported Alya alarm action and weekly schedule")
        repeat = sum(1 << ((d + 1) % 7) for d in set(weekdays)) | 128
        if self.profile.device_type == "DACHENG" and repeat == 128:
            repeat = 0
        op = Operation(self._live(), self._side_now())
        frame = alarm_frame(
            self.profile.protocol,
            hour if enabled else 0,
            minute if enabled else 0,
            repeat if enabled else 0,
            alarm_types(self.profile)[preset] if enabled else 0,
            op.side,
        )
        cancel = self._coordinator.cancel_command
        if enabled:
            await self._send(op, clock_frame(self.profile.protocol, dt_util.now()), cancel)
            if await self._pause(0.3, cancel):
                note_frame_skipped()
                return
        op.started = False
        try:
            await self._send(op, frame, cancel)
        finally:
            if op.started and self._session is op.session:
                for key in tuple(self._observed):
                    if key.startswith("alarm_"):
                        self._observed.pop(key)
        if enabled and not await self._pause(0.3, cancel):
            await self._send(op, query(self.profile.protocol, True), cancel)

    async def lights_toggle(self) -> None:
        await self.execute("light")

    async def lights_on(self) -> None:
        if "light" not in self._observed:
            raise self._unavailable("Refresh the light report before turn_on; use toggle otherwise")
        if not self._observed["light"]:
            await self.lights_toggle()

    async def lights_off(self) -> None:
        if "light" not in self._observed:
            raise self._unavailable(
                "Refresh the light report before turn_off; use toggle otherwise"
            )
        if self._observed["light"]:
            await self.lights_toggle()

    async def move_back_up(self) -> None:
        await self.execute("headup")

    async def move_back_down(self) -> None:
        await self.execute("headdown")

    async def move_back_stop(self) -> None:
        await self.stop_all()

    async def move_legs_up(self) -> None:
        await self.execute("footup")

    async def move_legs_down(self) -> None:
        await self.execute("footdown")

    async def move_legs_stop(self) -> None:
        await self.stop_all()

    async def move_head_up(self) -> None:
        await self.execute("headtiltup")

    async def move_head_down(self) -> None:
        await self.execute("headtiltdown")

    async def move_head_stop(self) -> None:
        await self.stop_all()

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        await self.stop_all()

    async def move_lumbar_up(self) -> None:
        await self.execute("lumbarup")

    async def move_lumbar_down(self) -> None:
        await self.execute("lumbardown")

    async def move_lumbar_stop(self) -> None:
        await self.stop_all()

    async def preset_flat(self) -> None:
        await self.execute("flat")

    async def preset_zero_g(self) -> None:
        await self.execute("zg")

    async def preset_anti_snore(self) -> None:
        await self.execute("anti")

    async def preset_lounge(self) -> None:
        await self.execute("lounge")

    async def preset_tv(self) -> None:
        await self.execute("tv")

    async def preset_memory(self, memory_num: int) -> None:
        if type(memory_num) is not int or not 1 <= memory_num <= self.memory_slot_count:
            raise self._unavailable("Unsupported memory slot")
        await self.execute(f"m{memory_num}" if "m2" in self.profile.commands else "memory")

    async def program_memory(self, memory_num: int) -> None:
        raise self._unavailable("The Alya app has no memory save command")

    async def recall_memory(self, slot: int, *, hold_ms: int) -> None:
        self.validate_memory_recall(slot)
        control = f"m{slot}" if "m2" in self.profile.commands else "memory"
        self.validate_hold_control(control, hold_ms)
        await self._hold(control, self.leased_hold_ms(hold_ms))


async def build_controller(ctx: BuildContext) -> AlyaController:
    data = {**ctx.data, **ctx.coordinator.entry.options}
    profile = ctx.variant if ctx.variant in PROFILES else data.get(CONF_PROTOCOL_VARIANT)
    if profile not in PROFILES:
        # Offline discovery and generic factory inspection keep a fixed safe
        # two-axis view; setup requires an explicit app layout before saving.
        profile = "bluetooth_2"
    side = {0xAA: 1, 0xBB: 2, 0: 0}.get(
        data.get(CONF_CB24_BED_SELECTION, 0xAA if PROFILES[profile].side_controls else 0), 0
    )
    controller = AlyaController(
        ctx.coordinator,
        profile=profile,
        side=side if PROFILES[profile].side_controls else 0,
        has_massage=data.get(CONF_HAS_MASSAGE, True),
    )
    controller._selection_valid = (
        ctx.variant in PROFILES or data.get(CONF_PROTOCOL_VARIANT) in PROFILES
    )
    return controller
