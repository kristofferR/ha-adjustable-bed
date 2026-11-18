"""One fenced physical session for the two fixed-ASCII legacy apps."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from math import floor
from time import monotonic
from typing import TYPE_CHECKING, Final

from ...card import CARD_LIGHTING, CARD_MASSAGE, CARD_PRESET_SAVE, CARD_PRESETS, CARD_UTILITY
from ...command_scheduler import current_command_context, note_frame_skipped, note_frame_written
from ...const import CONF_BED_TYPE, CONF_PROTOCOL_VARIANT
from ...profiles.richmat_legacy import Action, LegacyProfile, profiles
from ..base import BedController, ProfileExecution
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    MotorControlSpec,
)
from .protocol import LocalState, Phases, begin, packet

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator
    from ..builder import BuildContext
    from ..lifecycle import ControllerSession

from ...codec.richmat import TRANSPORTS

# Button names for the apps' button text and artwork descriptions.
_NAMES: Final = {
    "head up pictogram": "Head Up", "head down pictogram": "Head Down",
    "foot up pictogram": "Foot Up", "foot down pictogram": "Foot Down",
    "head and foot up pictogram": "Head and foot up",
    "head and foot down pictogram": "Head and foot down",
    "double up arrows": "Head and foot up", "double down arrows": "Head and foot down",
    "upper-bed segment up pictogram": "Upper Section Up",
    "upper-bed segment down pictogram": "Upper Section Down",
    "lower-bed segment up pictogram": "Lower Section Up",
    "lower-bed segment down pictogram": "Lower Section Down",
    "whole-bed tilt up pictogram": "Tilt Up", "whole-bed tilt down pictogram": "Tilt Down",
    "head up": "Head Up", "head down": "Head Down", "foot up": "Foot Up", "foot down": "Foot Down",
    "lumbar up": "Lumbar Up", "lumbar down": "Lumbar Down",
    "tilt up": "Tilt Up", "tilt down": "Tilt Down",
    "zg up": "Zero Gravity Up", "zg down": "Zero Gravity Down",
    "head rest up": "Head Rest Up", "head rest down": "Head Rest Down",
    "additional up arrow": "Extra Up", "additional down arrow": "Extra Down",
    "compound posture pictogram hufu": "Head Up Foot Up",
    "compound posture pictogram hufd": "Head Up Foot Down",
    "compound posture pictogram hdfu": "Head Down Foot Up",
    "flat": "Flat", "lounge": "Lounge", "tv": "TV", "read tv": "Read/TV", "relax": "Relax",
    "zg": "Zero Gravity", "zero/g": "Zero Gravity", "zero gravity": "Zero Gravity", "0 gravity": "Zero Gravity",
    "anti snore": "Anti-Snore", "snore": "Anti-Snore",
    "m": "Memory", "mem": "Memory", "m1": "Memory 1", "m2": "Memory 2", "m3": "Memory 3",
    "p1": "Memory 1", "p2": "Memory 2",
    "post1": "Position 1", "post2": "Position 2", "post3": "Position 3", "set": "Set",
    "under-bed light pictogram": "Toggle Light", "ubl": "Toggle Light", "bed light": "Toggle Light",
    "led": "Toggle Light",
    "factory reset": "Factory Reset", "stop": "Stop", "prohibited / off pictogram": "All Off",
    "head massage on/off": "Massage: Head Toggle", "foot massage on/off": "Massage: Foot Toggle",
    "bed/massage on/off pictogram": "Massage: Toggle", "on/off": "Massage: Toggle",
    "massage off": "Massage: Off", "all off": "Massage: Off",
    "timer / all off": "Massage: Timer / Off", "mode / all on": "Massage: Mode / On",
    "mode massage": "Massage: Mode", "mode": "Massage: Mode",
    "massage mode pictogram": "Massage: Mode",
    "pulse": "Massage: Pulse", "wave": "Massage: Wave", "constant": "Massage: Constant",
    "10min": "Massage: Timer 10 Minutes", "15min": "Massage: Timer 15 Minutes",
    "20min": "Massage: Timer 20 Minutes", "30min": "Massage: Timer 30 Minutes",
    "intensity up": "Massage: Intensity Up", "intensity down": "Massage: Intensity Down",
    "intensity +": "Massage: Intensity Up", "intensity −": "Massage: Intensity Down",
    "speed up": "Massage: Speed Up", "speed down": "Massage: Speed Down",
    "speed +": "Massage: Speed Up", "speed −": "Massage: Speed Down",
    "gentle touch +": "Massage: Gentle Touch Up", "gentle touch −": "Massage: Gentle Touch Down",
    "head massage +": "Massage: Head Up", "head massage −": "Massage: Head Down",
    "foot massage +": "Massage: Foot Up", "foot massage −": "Massage: Foot Down",
    "head massage increase pictogram": "Massage: Head Up",
    "head massage decrease pictogram": "Massage: Head Down",
    "foot massage increase pictogram": "Massage: Foot Up",
    "foot massage decrease pictogram": "Massage: Foot Down",
    "three intensity arcs": "Massage: Intensity Level 3",
    "one intensity arc": "Massage: Intensity Level 1",
}
# Labels whose meaning depends on the screen: name them by the command they send.
_BY_COMMAND: Final = {
    "2": "Massage: Head Toggle", "3": "Massage: Foot Toggle",
    "4": "Massage: Intensity Up", "5": "Massage: Intensity Down",
    "L": "Massage: Head Up", "M": "Massage: Head Down",
    "N": "Massage: Foot Up", "O": "Massage: Foot Down",
}
# Buttons that pick what a shared control acts on get one button per choice.
_CHOICE_NAMES: Final = {
    "axis": {0: "Head", 1: "Foot"},
    "mode": {1: "Lumbar", 2: "Tilt", 3: "Lounge"},
}
_VARIANT_NAMES: Final = {
    "+": "Massage: {} Up", "−": "Massage: {} Down",
    "massage power pictogram": "Massage: {} Toggle",
    "pos up": "{} Up", "pos down": "{} Down",
    "selected axis up": "{} Up", "selected axis down": "{} Down",
}
# The same controls on the Richmat MH apps read this way.
_MH_WORDING: Final = {
    "Massage: Head Toggle": "Head On/Off",
    "Massage: Foot Toggle": "Foot On/Off",
    "Massage: Toggle": "Massage on/off",
    "Massage: Off": "All Off",
    "Massage: Mode": "Massage mode",
    "Massage: Pulse": "Pulse",
    "Massage: Wave": "Wave",
    "Massage: Constant": "Constant",
    "Massage: Intensity Level 1": "Intensity 1",
    "Massage: Intensity Level 3": "Intensity 3",
}
_PRESET_NAMES: Final = frozenset({
    "Flat", "Lounge", "TV", "Read/TV", "Relax", "Zero Gravity", "Anti-Snore",
    "Memory", "Memory 1", "Memory 2", "Memory 3", "Position 1", "Position 2", "Position 3",
})


def _button_name(action: Action, variant: int | None = None) -> str:
    label = action.label.lower()
    if variant is not None and action.select:
        return _VARIANT_NAMES[label].format(_CHOICE_NAMES[action.select][variant])
    if label == "set" and action.programmable and "E" in action.short:
        return "Zero Gravity"  # T3's SET recalls and saves the zero-gravity preset.
    if label in _NAMES:
        return _NAMES[label]
    sent = (*action.down, *(w for _, b in action.branches for w in b.writes))
    command = next((c for c in sent if c not in ("m", "n")), None)
    if command in _BY_COMMAND:
        return _BY_COMMAND[command]
    return action.label


def _variants(action: Action) -> tuple[int | None, ...]:
    return action.choices or (None,)


def _control_id(key: str, variant: int | None) -> str:
    return key if variant is None else f"{key}@{variant}"


def _choice(control: str) -> int | None:
    _, sep, choice = control.partition("@")
    return int(choice) if sep else None


WRITE_TIMEOUT_S: Final = 5.0


@dataclass(slots=True, eq=False)
class Link:
    client: BleakClient
    write: BleakGATTCharacteristic
    owner: AdjustableBedCoordinator
    state: LocalState
    epochs: dict[str, float]
    counters: dict[str, int] = field(default_factory=dict)


async def _press(controller: BedController, *, control: str, program: bool = False) -> None:
    if not isinstance(controller, RichmatLegacyController):
        raise TypeError("Select the fixed ASCII app controller")
    await controller.action(control, program=program)


async def _pause(seconds: float, cancel: asyncio.Event) -> bool:
    if cancel.is_set():
        return True
    if seconds <= 0:
        await asyncio.sleep(0)
        return cancel.is_set()
    try:
        await asyncio.wait_for(cancel.wait(), seconds)
    except TimeoutError:
        return False
    return True


class RichmatLegacyController(ProfileExecution[LegacyProfile], BedController):
    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        app: str | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        app = app or str(coordinator.entry.data[CONF_BED_TYPE])
        code = code or str(coordinator.entry.data[CONF_PROTOCOL_VARIANT])
        try:
            self.profile = profiles()[f"{app}:{code}"]
        except KeyError as error:
            raise ValueError(
                "Choose an explicit app and its reachable case-sensitive prefix"
            ) from error
        self._link: Link | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        return TRANSPORTS["n1"].write_uuid

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def supports_motor_control(self) -> bool:
        return bool(self.motor_control_specs)

    @property
    def supports_memory_presets(self) -> bool:
        return False

    @property
    def memory_slot_count(self) -> int:
        """No generic numeric slot namespace; the catalog owns displayed slots."""
        return 0

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def position_number_specs(self) -> tuple[()]:
        return ()

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        return True

    async def async_on_connect(self, session: ControllerSession) -> None:
        # No application subscription, query, authentication or startup packet.
        await self.start_notify()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("The bed is disconnected")
        route = TRANSPORTS["n1"]
        write = next(
            (
                c
                for service in client.services
                if service.uuid.lower() == route.service_uuid
                for c in service.characteristics
                if c.uuid.lower() == route.write_uuid
                and ("write" in c.properties or "write-without-response" in c.properties)
            ),
            None,
        )
        if write is None:
            raise ValueError("The selected app needs the Nordic UART write characteristic")
        now = monotonic()
        self._link = Link(
            client,
            write,
            self._coordinator,
            LocalState(axis=int(self.profile.app == "sleep_evolution")),
            {screen: now for screen, _, _ in self.profile.schedules},
        )

    async def stop_notify(self) -> None:
        self.on_disconnect()

    def on_disconnect(self) -> None:
        self._link = None

    def _live(self, link: Link | None = None) -> Link:
        current = self._link
        if (
            current is None
            or (link is not None and current is not link)
            or self._coordinator is not current.owner
            or self._coordinator.controller is not self
            or self.client is not current.client
            or not current.client.is_connected
        ):
            raise ConnectionError("The physical bed session changed")
        if self.command_side is not None:
            raise ValueError("This app has no single-address bed-side field")
        return current

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(
            c for a in self.profile.actions if a.motion or a.programmable for c in a.control_ids()
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        covered = {
            key
            for spec in self.motor_control_specs
            if spec.hold is not None
            for key in (spec.hold.up_control, spec.hold.down_control)
        }
        specs = []
        for action in self.profile.actions:
            # Covers own their directions. Local-only pickers (axis/mode choice,
            # cancelling the app's refresh) and controls that only send the
            # wake/release gesture (e.g. the phone-torch handler) are not buttons.
            sent = {
                *action.down, *action.short, *(w for _, b in action.branches for w in b.writes)
            }
            if (
                action.key in covered
                or not sent - {"m", "n"}
                or action.label == "Tilt ZG selector (mode 2)"
            ):
                continue
            for variant in _variants(action):
                control = _control_id(action.key, variant)
                name = _button_name(action, variant)
                shown = _MH_WORDING.get(name, name)
                for program in (False, True) if action.programmable else (False,):
                    label = shown
                    if program:
                        label = ("Save to " if name.startswith("Memory") else "Save ") + shown
                    section = (
                        CARD_PRESET_SAVE
                        if program
                        else CARD_PRESETS
                        if action.programmable or name in _PRESET_NAMES
                        else CARD_LIGHTING
                        if label == "Toggle Light"
                        else CARD_MASSAGE
                        if name.startswith("Massage")
                        else CARD_UTILITY
                    )
                    specs.append(
                        ControllerButtonSpec(
                            "richmat_legacy_"
                            + control.replace("@", "_")
                            + ("_save" if program else ""),
                            label,
                            partial(_press, control=control, program=program),
                            translation_key="richmat_legacy_"
                            + ("save" if program else section.section.value),
                            translation_placeholders={"action": label},
                            hold=ControllerHoldSpec(control) if action.motion else None,
                            requires_confirmation=program or label == "Factory Reset",
                            invalidates_position=action.motion,
                            scheduler_resource="*",
                            card=section,
                        )
                    )
        return tuple(specs)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        # Only proven paired direction artwork, with no inferred motor count.
        pairs = {}
        for a in self.profile.actions:
            label = a.label.lower().replace(" pictogram", "")
            for axis, names in (
                ("back", ("head up", "head down")),
                ("legs", ("foot up", "foot down")),
            ):
                if a.motion and label in names:
                    pairs.setdefault(axis, {})[label == names[0]] = a.key
        return tuple(
            MotorControlSpec(
                axis,
                axis,
                partial(_press, control=keys[True]),
                partial(_press, control=keys[False]),
                lambda c: c.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    keys[True], keys[False], press_is_native=True, stop_scope="side"
                ),
            )
            for axis, keys in pairs.items()
            if True in keys and False in keys
        )

    def validate_request(self, control: str, duration_ms: int, program: bool = False) -> Action:
        action = self.profile.action(control)
        if type(duration_ms) is not int or not 1 <= duration_ms <= 60000:
            raise ValueError("Choose a duration of 1 to 60000 ms")
        if program and not action.programmable:
            raise ValueError("This control has no proven save event")
        if self.command_side is not None:
            raise ValueError("This app has no single-address bed-side field")
        context = current_command_context()
        if context is not None and context.lease is not None and (program or not action.motion):
            raise ValueError("Only proven motion controls support renewable holds")
        return action

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_request(control, duration_ms)
        if control not in self.held_control_options:
            raise ValueError("This control has no held gesture")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self.action(control, duration_ms=duration_ms)

    async def _send(
        self, link: Link, literal: str, cancel: asyncio.Event, deadline: float | None = None
    ) -> bool:
        self._live(link)

        async def write() -> bool:
            async with self._ble_lock:
                self._live(link)
                if cancel.is_set() or deadline is not None and monotonic() >= deadline:
                    note_frame_skipped()
                    return False
                data = packet(literal)
                response = "write" in link.write.properties
                self._record_command_trace(
                    link.write.uuid, data, response=response, characteristic=link.write
                )
                async with asyncio.timeout(WRITE_TIMEOUT_S):
                    await link.client.write_gatt_char(link.write, data, response=response)
                    note_frame_written()
                return True

        # Drain submitted GATT work before cleanup or releasing ownership.
        task = asyncio.create_task(write())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        sent = task.result()
        if cancelled:
            raise asyncio.CancelledError
        return sent

    async def _release(self, link: Link, phase: Phases, count: int, *, recall: bool) -> None:
        cleanup = asyncio.Event()
        short = (
            phase.short
            if recall and phase.short_guard is not None and count < phase.short_guard
            else ()
        )

        async def release_frames() -> None:
            try:
                for literal in short:
                    await self._send(link, literal, cleanup)
            finally:
                for literal in phase.cleanup:
                    await self._send(link, literal, cleanup)

        task = asyncio.create_task(release_frames())
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        task.result()
        if cancelled:
            raise asyncio.CancelledError

    async def action(self, control: str, *, duration_ms: int = 1000, program: bool = False) -> None:
        action = self.validate_request(control, duration_ms, program)
        link = self._live()
        cancel = self._coordinator.cancel_command
        if cancel.is_set():
            return
        variant = _choice(control)
        if variant is not None and action.select is not None:
            # A per-axis/per-mode button makes the app's choice, then presses.
            setattr(link.state, action.select, variant)
        phase = begin(action, link.state)
        _, initial, period = next(s for s in self.profile.schedules if s[0] == action.screen)
        period_s = period / 1000
        epoch = link.epochs[action.screen] + initial / 1000
        now = monotonic()
        tick_at = (
            epoch if now <= epoch else epoch + (floor((now - epoch) / period_s) + 1) * period_s
        )
        # A short motion press whose starter is only m waits for its first
        # actual refresh, then gets its requested elapsed movement window.
        starter_moves = action.motion and any(v not in ("m", "n") for v in phase.down)
        start = now if not action.motion or starter_moves or phase.branch is None else tick_at
        window = self.leased_hold_ms(duration_ms) if action.motion else duration_ms
        deadline = start + window / 1000
        first_motion_tick = action.motion and not starter_moves and phase.branch is not None
        if first_motion_tick:
            deadline = max(now, tick_at) + WRITE_TIMEOUT_S
        # Programming stops at the first *completed* save event. This bounded
        # operation tolerates ordinary GATT latency without a nominal+1ms race.
        if program:
            threshold = phase.branch.threshold if phase.branch else None
            assert threshold is not None
            deadline = max(now, tick_at) + (threshold + 2) * period_s + WRITE_TIMEOUT_S
        count = link.counters.get(action.screen, 0)
        completed = False
        try:
            for literal in phase.down:
                if not await self._send(link, literal, cancel, deadline if action.motion else None):
                    return
            if phase.branch is not None:
                while monotonic() < deadline and not cancel.is_set():
                    if await _pause(
                        min(max(0, tick_at - monotonic()), max(0, deadline - monotonic())), cancel
                    ):
                        break
                    if monotonic() >= deadline:
                        break
                    if first_motion_tick:
                        deadline = monotonic() + window / 1000
                        first_motion_tick = False
                    writes, count = phase.tick(count)
                    link.counters[action.screen] = count
                    for literal in writes:
                        if not await self._send(link, literal, cancel, deadline):
                            return
                    if program and writes:
                        completed = True
                        break
                    # Skip missed intervals; never backfill stale motion.
                    tick_at = max(
                        tick_at + period_s,
                        epoch + (floor((monotonic() - epoch) / period_s) + 1) * period_s,
                    )
            elif phase.down or phase.cleanup:
                await _pause(max(0, deadline - monotonic()), cancel)
            if not program:
                completed = not cancel.is_set()
        finally:
            # Fresh cancellation-independent cleanup, on the captured link only.
            # Dedicated save cancellation must never turn into short recall.
            if action.reset_counter:
                link.counters[action.screen] = 0
            try:
                self._live(link)
            except ConnectionError, ValueError:
                pass
            else:
                await self._release(link, phase, count, recall=not program)
        if program and not completed and not cancel.is_set():
            raise TimeoutError("The bounded operation ended before a save write completed")

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        raise NotImplementedError("Use a declared app control")

    async def stop_all(self) -> None:
        await self._send(self._live(), "n", asyncio.Event())

    move_head_stop = move_back_stop = move_legs_stop = move_feet_stop = stop_all

    async def _axis(self, axis: str, up: bool) -> None:
        spec = next((s for s in self.motor_control_specs if s.key == axis), None)
        if spec is None:
            raise NotImplementedError("This profile has no matching direction control")
        await (spec.open_fn(self) if up else spec.close_fn(self))

    async def move_back_up(self) -> None:
        await self._axis("back", True)

    async def move_back_down(self) -> None:
        await self._axis("back", False)

    move_head_up = move_back_up
    move_head_down = move_back_down

    async def move_legs_up(self) -> None:
        await self._axis("legs", True)

    async def move_legs_down(self) -> None:
        await self._axis("legs", False)

    move_feet_up = move_legs_up
    move_feet_down = move_legs_down

    async def preset_flat(self) -> None:
        raise NotImplementedError("Use the exact app-labelled control")

    async def preset_memory(self, memory_num: int) -> None:
        raise NotImplementedError("Use the displayed slot's app-labelled control")

    async def program_memory(self, memory_num: int) -> None:
        raise NotImplementedError("Use the displayed slot's dedicated Save control")


async def build_controller(ctx: BuildContext) -> RichmatLegacyController:
    return RichmatLegacyController(
        ctx.coordinator,
        app=ctx.bed_type,
        code=ctx.variant
        if ctx.variant not in (None, "auto")
        else str(ctx.data.get(CONF_PROTOCOL_VARIANT, "")),
    )
