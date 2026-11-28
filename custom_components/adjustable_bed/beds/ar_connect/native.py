"""AR Connect's native bed route, with HA-owned awaited readiness and release."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Collection
from dataclasses import replace
from typing import TYPE_CHECKING, cast

from ...card import CardRole, motor_card
from ...codec.linak import control_frame, parse_ar_diagnostic, parse_native_reference
from ...command_scheduler import note_frame_skipped
from ...controller_state import StateKey
from ...errors import BedNotConnectedError, invalid
from ...execution import STREAM_HOLD
from ...profiles import ar_connect as app
from ..base import require_controller
from ..catalog_buttons import Kind, catalog_button
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    ControllerSwitchSpec,
    MotorControlSpec,
)
from ..lifecycle import CapabilitySnapshotPolicy, ControllerSession
from .session import ArSessionController, Link

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator


class _HoldEnded(Exception):
    """The admitted hold ended while waiting for the concrete GATT lane."""


SILENT = StateKey[bool]("ar_connect_silent")
POSITION_KEYS = {
    axis: StateKey[float | None](f"ar_connect_{axis}_position") for axis in app.AR_CONNECT.axes
}


class NativeController(ArSessionController):
    def __init__(self, coordinator: AdjustableBedCoordinator, layout: str = "back_legs") -> None:
        super().__init__(coordinator)
        if layout not in app.LAYOUTS:
            raise invalid("ar_connect_layout")
        self.layout = layout
        self.axes = app.LAYOUTS[layout]
        self.mask = 0
        self.model = "standard"
        self.positions: dict[str, float] = {}
        self._reference_events = 0
        self._last_reference_at: float | None = None
        self._motion: object | None = None
        self._motion_link: Link | None = None
        self._gesture_ended = asyncio.Event()
        self._initialized = False
        self._admit_after = 0.0
        if SILENT not in coordinator.controller_state:
            self.forward_controller_state_updates(SILENT(False))

    @property
    def control_characteristic_uuid(self) -> str:
        return app.AR_CONNECT.command_characteristic

    @property
    def execution(self):
        return STREAM_HOLD

    @property
    def reconnect_for_explicit_stop(self) -> bool:
        return False

    @property
    def requires_single_command_target(self) -> bool:
        return True

    def command_start_allowed(self, resources: Collection[str]) -> bool:
        if "*" not in resources and not any(
            resource.startswith("motor:") for resource in resources
        ):
            return True
        return asyncio.get_running_loop().time() >= self._admit_after

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def exposes_assumed_toggle_light(self) -> bool:
        return False

    async def async_discover_capabilities(self) -> None:
        link = self.bind()
        char = self.role(
            link, "command", app.AR_CONNECT.control_service, self.control_characteristic_uuid
        )
        if not {"write", "write-without-response"}.intersection(char.properties):
            raise BedNotConnectedError()
        # Discovery reads follow bond admission in async_on_connect. No inherited
        # Bed Control handshake, calibration, alarm editor or degree conversion.

    async def async_on_connect(self, session: ControllerSession) -> None:
        link = self.link
        if link is None:
            raise BedNotConnectedError()
        link.generation = self._coordinator.connection_generation
        await session.async_require_native_bond()
        self.live(link, ready=False)
        svc = link.client.services.get_service(app.AR_CONNECT.reference_service)
        self.model = "standard"
        self.mask = 0
        if svc is not None:
            self.role(
                link,
                "mask",
                app.AR_CONNECT.reference_service,
                app.AR_CONNECT.reference_mask,
                "read",
            )
            raw = await self.read(link, "mask")
            if not raw:
                raise invalid("ar_connect_empty_mask")
            self.mask = raw[0]
            self.model = "advanced" if self.mask else "td3"
            if self.mask and link.client.services.get_service(app.TIMER_SERVICE) is not None:
                self.model = "advanced_with_alarm"
                self.role(link, "timer", app.TIMER_SERVICE, app.TIMER_EVENT, "notify")
                await self.subscribe(link, "timer", lambda data: None)
        name = link.client.services.get_characteristic(app.NAME_CHARACTERISTIC)
        if name is None or "read" not in name.properties:
            raise BedNotConnectedError()
        link.roles["name"] = name
        await self.read(link, "name")
        await session.async_start_notify()
        # The app dispatches this through a void wrapper. HA awaits and reports
        # real GATT completion; absent configuration service is not an app gate.
        config = link.client.services.get_service(app.AR_CONNECT.configuration_service)
        if config is not None:
            self.role(
                link,
                "configuration",
                app.AR_CONNECT.configuration_service,
                app.AR_CONNECT.configuration_characteristic,
            )
            await asyncio.sleep(app.STARTUP_DELAY_S)
            self.live(link, ready=False)
            for _, frame in app.AR_CONNECT.custom_speed(
                app.STARTUP_SPEED_UP, app.STARTUP_ACCELERATION_UP
            ):
                await self.frame(link, "configuration", frame, startup=True, cancel=asyncio.Event())
                await asyncio.sleep(app.AR_CONNECT.custom_speed_post_write_ms / 1000)
                self.live(link, ready=False)
        link.ready = True
        self._initialized = True
        await self.read_positions()
        session.persist_capability_snapshot()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self.live(ready=False)
        if not self.mask:
            return
        refs = dict(app.NATIVE_REFERENCES)
        for axis in app.NATIVE_SUBSCRIBE_ORDER:
            self.role(link, axis, app.AR_CONNECT.reference_service, refs[axis], "notify", "read")
            await self.subscribe(link, axis, lambda data, axis=axis: self._reference(axis, data))
            self._reference(axis, await self.read(link, axis))
        self.role(
            link,
            "error",
            app.AR_CONNECT.control_service,
            app.AR_CONNECT.error_characteristic,
            "notify",
            "read",
        )
        await self.subscribe(link, "error", self._diagnostic)
        self._diagnostic(await self.read(link, "error"))

    def _reference(self, axis: str, data: bytes) -> None:
        if not data:
            return
        bit = {"back": 7, "legs": 6, "head": 5, "feet": 4, "base": 3}[axis]
        if not self.mask & (1 << bit):
            return
        self._reference_events += 1
        self._last_reference_at = asyncio.get_running_loop().time()
        state = parse_native_reference(data)
        self.positions[axis] = state.position_export
        if axis in POSITION_KEYS:
            self.forward_controller_state_updates(POSITION_KEYS[axis](state.position_export))

    def _diagnostic(self, data: bytes) -> None:
        # The native error state is omitted by the app's Flutter export. Retain
        # bytes in protocol diagnostics, not a guessed battery/error entity.
        self._error = data.hex()
        try:
            parse_ar_diagnostic(data)
        except ValueError:
            self._error = "invalid:" + data.hex()

    async def read_positions(self, motor_count: int = 2) -> None:
        link = self.live()
        for axis, bit in (("back", 7), ("legs", 6), ("head", 5), ("feet", 4), ("base", 3)):
            if self.mask & (1 << bit):
                self._reference(axis, await self.read(link, axis))
        if "error" in link.roles:
            self._diagnostic(await self.read(link, "error"))

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 400,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self.live()
        for i in range(repeat_count):
            if i and await self._pause(repeat_delay_ms / 1000):
                return
            await self.frame(link, "command", command, cancel=cancel_event)

    async def _pause(self, seconds: float) -> bool:
        cancel = self._coordinator.cancel_command
        if cancel.is_set() or self._gesture_ended.is_set():
            return True
        a = asyncio.create_task(cancel.wait())
        b = asyncio.create_task(self._gesture_ended.wait())
        try:
            done, _ = await asyncio.wait(
                (a, b), timeout=max(0, seconds), return_when=asyncio.FIRST_COMPLETED
            )
            return bool(done)
        finally:
            a.cancel()
            b.cancel()
            await asyncio.gather(a, b, return_exceptions=True)

    async def _release(self, link: Link, owner: object) -> None:
        if self._motion is not owner:
            return
        # Consume before awaiting, so queued explicit STOP does not duplicate it.
        self._motion = None
        self._motion_link = None
        await self.frame(
            link, "command", control_frame(app.AR_CONNECT.stop_bed_opcode), cancel=asyncio.Event()
        )

    async def _held(
        self, frame: Callable[[], bytes | None], duration_ms: int, *, watchdog: bool = False
    ) -> None:
        link = self.live()
        if self._coordinator.cancel_command.is_set():
            note_frame_skipped()
            return
        if self._motion is not None:
            raise invalid("ar_connect_motion_busy")
        if asyncio.get_running_loop().time() < self._admit_after:
            note_frame_skipped()
            return
        owner = object()
        self._motion, self._motion_link = owner, link
        self._gesture_ended = asyncio.Event()
        loop = asyncio.get_running_loop()
        start, end = loop.time(), loop.time() + duration_ms / 1000
        self._admit_after = start + app.DEBOUNCE_MS / 1000
        next_tick = start + app.REFRESH_MS / 1000
        async with self.releasing(lambda owner=owner: self._release(link, owner)):
            while loop.time() < end:
                idle_at = (
                    (
                        start + app.IDLE_INITIAL_MS / 1000
                        if self._last_reference_at is None or self._last_reference_at < start
                        else self._last_reference_at + app.IDLE_AFTER_REFERENCE_MS / 1000
                    )
                    if watchdog
                    else end
                )
                if await self._pause(min(next_tick, end, idle_at) - loop.time()):
                    return
                self.live(link)
                if loop.time() >= end:
                    return
                if watchdog:
                    idle_at = (
                        start + app.IDLE_INITIAL_MS / 1000
                        if self._last_reference_at is None or self._last_reference_at < start
                        else self._last_reference_at + app.IDLE_AFTER_REFERENCE_MS / 1000
                    )
                    if loop.time() >= idle_at:
                        return
                value = frame()
                if value is None:
                    return

                def before_write() -> None:
                    if (
                        self._motion is not owner
                        or self._gesture_ended.is_set()
                        or loop.time() >= end
                    ):
                        note_frame_skipped()
                        raise _HoldEnded

                try:
                    await self.frame(link, "command", value, before_write=before_write)
                except _HoldEnded:
                    return
                next_tick += app.REFRESH_MS / 1000
                next_tick = max(next_tick, loop.time())

    async def _move(self, axis: app.Axis, up: bool) -> None:
        if axis not in self.axes:
            raise self.not_supported(axis)
        duration = self.leased_hold_ms((self._coordinator.motor_pulse_count + 1) * app.REFRESH_MS)
        await self._held(lambda: app.AR_CONNECT.movement({axis: up}, slow=self.silent), duration)

    async def move_back_up(self):
        await self._move("back", True)

    async def move_back_down(self):
        await self._move("back", False)

    async def move_legs_up(self):
        await self._move("legs", True)

    async def move_legs_down(self):
        await self._move("legs", False)

    async def move_head_up(self):
        await self._move("head", True)

    async def move_head_down(self):
        await self._move("head", False)

    async def move_feet_up(self):
        await self._move("feet", True)

    async def move_feet_down(self):
        await self._move("feet", False)

    async def stop_all(self) -> None:
        self.on_gesture_release()
        owner, link = self._motion, self._motion_link
        if owner is not None and link is not None:
            await self._release(link, owner)

    move_head_stop = move_back_stop = move_legs_stop = move_feet_stop = stop_all

    def on_gesture_release(self) -> None:
        self._gesture_ended.set()

    def on_connection_release(self, reason: str) -> None:
        self.on_gesture_release()

    async def preset_flat(self) -> None:
        await self._held(
            lambda: app.AR_CONNECT.movement(
                dict.fromkeys(app.AR_CONNECT.axes, False), slow=self.silent
            ),
            self.leased_hold_ms(30000),
            watchdog=True,
        )

    async def recall(self, name: str, duration_ms: int = 30000) -> None:
        if name not in app.PRESETS:
            raise self.not_supported(name)
        index = app.PRESETS[name]
        await self._held(
            lambda: control_frame(app.AR_CONNECT.recall_opcodes[index], slow=self.silent),
            self.leased_hold_ms(duration_ms),
            watchdog=True,
        )

    async def preset_zero_g(self):
        await self.recall("zero_g")

    async def preset_tv(self):
        await self.recall("television")

    async def preset_reading(self):
        await self.recall("reading")

    @property
    def memory_slot_count(self) -> int:
        return 4

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return True

    @property
    def supports_preset_reading(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def memory_slot_names(self) -> tuple[str, ...]:
        return ("Television", "Zero gravity", "Reading", "Favorite")

    def is_memory_slot_programmable(self, memory_num: int) -> bool:
        return memory_num in (1, 3, 4)

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self.recall(tuple(app.PRESETS)[memory_num - 1])

    @property
    def supports_held_memory_recall(self) -> bool:
        return True

    async def recall_memory(self, slot: int, *, hold_ms: int) -> None:
        self.validate_memory_recall(slot)
        if type(hold_ms) is not int or not 1 <= hold_ms <= 60000:
            raise invalid("ar_connect_hold")
        await self.recall(tuple(app.PRESETS)[slot - 1], hold_ms)

    @property
    def supports_preset_hold(self) -> bool:
        return True

    @property
    def held_preset_options(self) -> tuple[str, ...]:
        return (
            "flat",
            "zero_g",
            "tv",
            "reading",
            "favorite",
            *(("peaceful_night",) if self.mask else ()),
        )

    async def hold_preset(self, preset: str, duration_ms: int) -> None:
        if preset not in self.held_preset_options:
            raise self.not_supported(preset)
        await self.hold_control(
            {"tv": "television", "peaceful_night": "peaceful"}.get(preset, preset), duration_ms
        )

    async def program_memory(self, memory_num: int) -> None:
        if type(memory_num) is not int or not self.is_memory_slot_programmable(memory_num):
            raise self.not_supported("saving this preset")
        await self.write_command(control_frame(app.AR_CONNECT.save_opcodes[memory_num - 1]))

    @property
    def memory_slots_recalled_by_presets(self) -> frozenset[int]:
        return frozenset({1, 2, 3, 4})

    @property
    def memory_slots_programmed_by_presets(self) -> frozenset[int]:
        return frozenset({1, 3, 4})

    async def peaceful(self, duration_ms: int = 30000) -> None:
        if not self.mask:
            raise self.not_supported("Peaceful night without position feedback")
        await self.read_positions()

        def frame() -> bytes | None:
            directions = app.peaceful_directions(self.positions)
            return app.AR_CONNECT.movement(directions, slow=self.silent) if directions else None

        await self._held(frame, self.leased_hold_ms(duration_ms), watchdog=True)

    async def lights_toggle(self) -> None:
        await self.write_command(control_frame(app.AR_CONNECT.light_toggle_opcode))

    @property
    def silent(self) -> bool:
        return self._coordinator.controller_state.get(SILENT) is True

    def set_silent(self, value: bool) -> None:
        self.forward_controller_state_updates(SILENT(value))

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        return (
            ControllerSwitchSpec(
                "ar_connect_silent",
                "ar_connect_silent",
                lambda c, v: require_controller(c, NativeController)._silent_command(v),
                SILENT,
                local_set_fn=self.set_silent,
            ),
        )

    async def _silent_command(self, value: bool) -> None:
        self.set_silent(value)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        base = super().motor_control_specs
        # Explicit app options can include feet without head.
        all_specs = {spec.key: spec for spec in base}
        if "head" in self.axes and "head" not in all_specs:
            all_specs["head"] = MotorControlSpec(
                "head",
                "head",
                lambda c: c.move_head_up(),
                lambda c: c.move_head_down(),
                lambda c: c.move_head_stop(),
            )
        if "feet" in self.axes and "feet" not in all_specs:
            all_specs["feet"] = MotorControlSpec(
                "feet",
                "feet",
                lambda c: c.move_feet_up(),
                lambda c: c.move_feet_down(),
                lambda c: c.move_feet_stop(),
            )
        return tuple(
            replace(
                all_specs[axis],
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    f"{axis}_up", f"{axis}_down", stop_scope="side", press_hold_ms=None
                ),
            )
            for axis in self.axes
            if axis in all_specs
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return (
            *(f"{axis}_{d}" for axis in self.axes for d in ("up", "down")),
            "flat",
            *app.PRESETS,
            *(("peaceful",) if self.mask else ()),
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or type(duration_ms) is not int
            or not 1 <= duration_ms <= 60000
        ):
            raise invalid("ar_connect_hold")

    async def move_sections(self, directions: dict[app.Axis, bool], duration_ms: int) -> None:
        if (
            not directions
            or set(directions).difference(self.axes)
            or type(duration_ms) is not int
            or not 1 <= duration_ms <= 60000
        ):
            raise invalid("ar_connect_hold")
        await self._held(lambda: app.AR_CONNECT.movement(directions, slow=self.silent), duration_ms)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        duration = self.leased_hold_ms(duration_ms)
        if control == "flat":
            await self._held(
                lambda: app.AR_CONNECT.movement(
                    dict.fromkeys(app.AR_CONNECT.axes, False), slow=self.silent
                ),
                duration,
                watchdog=True,
            )
        elif control == "peaceful":
            await self.peaceful(duration)
        elif control in app.PRESETS:
            await self.recall(control, duration)
        else:
            axis, direction = control.rsplit("_", 1)
            await self._held(
                lambda: app.AR_CONNECT.movement(
                    {cast(app.Axis, axis): direction == "up"}, slow=self.silent
                ),
                duration,
            )

    async def probe_options(self) -> None:
        """Confirmed setup motion, preserving the app's address-wide event-count quirk."""
        link = self.live()
        self._gesture_ended = asyncio.Event()
        found = set(self.axes)
        for axis in ("head", "feet"):
            for up in (True, False):
                self._reference_events = 0
                owner = object()
                self._motion, self._motion_link = owner, link
                async with self.releasing(lambda owner=owner: self._release(link, owner)):
                    await self.frame(link, "command", app.AR_CONNECT.movement({axis: up}))
                    if await self._pause(app.PROBE_DIRECTION_S):
                        return
                    if self._reference_events >= 10:
                        found.add(axis)
        self.axes = tuple(axis for axis in app.AR_CONNECT.axes if axis in found)

    async def identify_side(self) -> None:
        link = self.live()
        self._gesture_ended = asyncio.Event()
        for up in (True, False):
            owner = object()
            self._motion, self._motion_link = owner, link
            async with self.releasing(lambda owner=owner: self._release(link, owner)):
                await self.frame(link, "command", app.AR_CONNECT.movement({"back": up}))
                if await self._pause(app.SIDE_DIRECTION_S):
                    return
            if up and await self._pause(app.SIDE_GAP_S):
                return

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs = []
        for name, label in (("favorite", "Favorite"), ("peaceful", "Peaceful night")):
            fn = (
                (lambda c: require_controller(c, NativeController).peaceful())
                if name == "peaceful"
                else (lambda c: require_controller(c, NativeController).recall("favorite"))
            )
            spec = catalog_button(
                f"ar_connect_{name}", label, fn, kind=Kind.PRESET, hold=ControllerHoldSpec(name)
            )
            if spec is not None and (name != "peaceful" or self.mask):
                specs.append(spec)
        for index, label in ((1, "Television"), (3, "Reading"), (4, "Favorite")):
            spec = catalog_button(
                f"ar_connect_save_{index}",
                f"Save {label}",
                lambda c, index=index: c.program_memory(index),
                kind=Kind.SAVE,
                requires_confirmation=True,
            )
            if spec is not None:
                specs.append(spec)
        for key, label, fn in (
            (
                "probe",
                "Check available sections",
                lambda c: require_controller(c, NativeController).probe_options(),
            ),
            (
                "identify",
                "Identify bed side",
                lambda c: require_controller(c, NativeController).identify_side(),
            ),
        ):
            specs.append(
                ControllerButtonSpec(
                    f"ar_connect_{key}",
                    label,
                    fn,
                    requires_confirmation=True,
                    entity_registry_enabled_default=False,
                )
            )
        return tuple(specs)

    def standard_button_hold_spec(self, key: str) -> ControllerHoldSpec | None:
        control = {
            "preset_flat": "flat",
            "preset_zero_g": "zero_g",
            "preset_tv": "television",
            "preset_reading": "reading",
        }.get(key)
        return ControllerHoldSpec(control) if control is not None else None

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return tuple(
            ControllerStateSensorSpec(
                f"ar_connect_{axis}_position",
                f"ar_connect_{axis}_position",
                POSITION_KEYS[axis],
                "mdi:arrow-expand-vertical",
                card=motor_card(axis, CardRole.POSITION),
            )
            for axis in self.axes
            if self.mask & (1 << {"back": 7, "legs": 6, "head": 5, "feet": 4}[axis])
        )

    @property
    def capability_snapshot_policy(self) -> CapabilitySnapshotPolicy:
        return CapabilitySnapshotPolicy(
            deferred_reload=True, reconcile_on_persistent_link=True, after_operations=True
        )

    @property
    def has_dynamic_controller_entities(self) -> bool:
        return True

    @property
    def has_dynamic_buttons(self) -> bool:
        return True

    def capability_snapshot(self) -> dict[str, object]:
        return {
            "layout": self.layout,
            "mask": self.mask,
            "axes": list(self.axes),
            "model": self.model,
        }

    @property
    def protocol_diagnostics(self) -> dict[str, object]:
        return {
            "route": "native",
            "model": self.model,
            "mask": self.mask,
            "positions": dict(self.positions),
            "error_record": getattr(self, "_error", None),
            "hardware": "UNVERIFIED",
        }

    def on_disconnect(self) -> None:
        super().on_disconnect()
        if hasattr(self, "_gesture_ended"):
            self.on_gesture_release()
        self._motion = self._motion_link = None
        self.positions = {}
        if self._coordinator.controller is self:
            for key in POSITION_KEYS.values():
                self.forward_controller_state_updates(key(None))


# Compatibility export follows the repository's lazy controller inventory.
ArConnectController = NativeController
