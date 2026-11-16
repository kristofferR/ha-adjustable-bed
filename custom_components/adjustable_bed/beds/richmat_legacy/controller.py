"""One fenced physical session for the two fixed-ASCII legacy apps."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from math import floor
from time import monotonic
from typing import TYPE_CHECKING, Final

from ...card import CARD_LIGHTING, CARD_MASSAGE, CARD_PRESETS, CARD_UTILITY
from ...command_scheduler import current_command_context
from ...const import CONF_BED_TYPE, CONF_PROTOCOL_VARIANT
from ...controller_state import StateKey
from ...profiles.richmat_legacy import Action, LegacyProfile, profiles
from ..base import BedController, ProfileExecution
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerHoldSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
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

LOCAL: Final = StateKey[dict[str, object]]("richmat_legacy_local")
PROFILE: Final = StateKey[str]("richmat_legacy_profile")
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
        self._publish()

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

    def _publish(self) -> None:
        link = self._link
        if link is not None:
            self.forward_controller_state_updates(
                PROFILE(self.profile.key),
                LOCAL(
                    {
                        "axis": "head" if link.state.axis == 0 else "foot",
                        "mode": link.state.mode,
                        "light_request_flag": link.state.led,
                        "state_source": "local app choices, not bed feedback",
                    }
                ),
            )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        return (
            ControllerStateSensorSpec(
                "richmat_legacy_profile",
                "richmat_legacy_profile",
                PROFILE,
                "mdi:bed",
                attribute_keys=(LOCAL,),
            ),
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(a.key for a in self.profile.actions if a.motion or a.programmable)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs = []
        for action in self.profile.actions:
            for program in (False, True) if action.programmable else (False,):
                label = ("Save " if program else "") + action.label
                section = (
                    CARD_PRESETS
                    if action.programmable
                    else CARD_LIGHTING
                    if "light" in label.lower() and "release" not in label.lower()
                    else CARD_MASSAGE
                    if "massage" in label.lower()
                    else CARD_UTILITY
                )
                specs.append(
                    ControllerButtonSpec(
                        "richmat_legacy_" + action.key + ("_save" if program else ""),
                        label,
                        partial(_press, control=action.key, program=program),
                        translation_key="richmat_legacy_" + section.section.value,
                        translation_placeholders={"action": label},
                        hold=ControllerHoldSpec(action.key) if action.motion else None,
                        requires_confirmation=program or "factory reset" in label.lower(),
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
                    return False
                data = packet(literal)
                response = "write" in link.write.properties
                self._record_command_trace(
                    link.write.uuid, data, response=response, characteristic=link.write
                )
                async with asyncio.timeout(WRITE_TIMEOUT_S):
                    await link.client.write_gatt_char(link.write, data, response=response)
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
        phase = begin(action, link.state)
        self._publish()
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
            self._publish()
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
