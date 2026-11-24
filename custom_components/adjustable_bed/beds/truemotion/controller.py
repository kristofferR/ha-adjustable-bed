"""trueMotion controls over the SUTA text codec."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from contextlib import suppress
from dataclasses import dataclass, field
from functools import partial
from inspect import isawaitable
from typing import TYPE_CHECKING, Final

from bleak.exc import BleakError

from ...app_session import app_session
from ...card import CARD_HIDDEN, CARD_MASSAGE_TIMER
from ...codec.suta import text
from ...command_scheduler import current_command_context, note_frame_skipped, note_frame_written
from ...const import CONF_BLE_DEVICE_NAME, SIDE_LEFT
from ...controller_state import StateKey
from ...coordinator import ChildEntryView
from ...errors import BedNotConnectedError, invalid
from ...profiles import truemotion as app
from ..base import CONTROLLER_GESTURE_RELEASE, BedController, ProfileExecution, require_controller
from ..cancellation import cancellable, settled
from ..catalog_buttons import Kind, catalog_button, massage_button, save_button
from ..entity_specs import (
    ControllerButtonSpec,
    ControllerMotorHoldSpec,
    ControllerStateSensorSpec,
    ControllerSwitchSpec,
    MotorControlSpec,
)
from .receive import Observations, Receiver

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator
    from ..builder import BuildContext

FIRMWARE: Final = StateKey[str | None]("truemotion_firmware")
_PRESETS: Final = {"M8": "M8", "SWING": "Swing", "PILATES": "Pilates"}
_SAVE_PRESETS: Final = {
    "SNORE": "Save anti-snore position",
    "TV": "Save TV position",
    "ZEROG": "Save zero-gravity position",
}
ZONES: Final[tuple[app.Zone, ...]] = ("HEAD", "FOOT")


@dataclass(slots=True)
class AppState:
    observations: Observations = field(default_factory=Observations)
    timers: dict[app.Zone, str] = field(default_factory=lambda: dict.fromkeys(ZONES, "00"))
    level: str | None = None


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    tx: BleakGATTCharacteristic
    rx: BleakGATTCharacteristic
    receiver: Receiver


@dataclass(frozen=True, slots=True)
class Burst:
    command: str
    count: int = 1
    offset_ms: int = 0
    interval_ms: int = app.REPEAT_MS
    on_write: Callable[[], None] | None = None


class TrueMotionController(ProfileExecution[app.Profile], BedController):
    def __init__(self, coordinator: AdjustableBedCoordinator, profile: app.Profile) -> None:
        super().__init__(coordinator)
        self.profile = profile
        self._controls = profile.controls
        self._link: Link | None = None
        self._cleanup_context = None
        self._state = app_session(
            coordinator.hass,
            coordinator.address,
            ("truemotion", profile.model, profile.split),
            AppState,
        )

    @property
    def requires_notification_channel(self) -> bool:
        return True

    @property
    def requires_linked_live_readiness(self) -> bool:
        return True

    async def async_validate_linked_readiness(self) -> None:
        self._current_link()

    @property
    def control_characteristic_uuid(self) -> str:
        return self._link.tx.uuid if self._link is not None else ""

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def reconnect_for_explicit_stop(self) -> bool:
        return True

    def _link_is_current(self, link: Link) -> bool:
        return (
            self._link is link
            and self.client is link.client
            and link.client.is_connected
            and self._coordinator.controller is self
        )

    def _current_link(self) -> Link:
        if (link := self._link) is None or not self._link_is_current(link):
            raise BedNotConnectedError
        return link

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        if self._link is not None and self._link_is_current(self._link):
            return
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError
        roles = app.gatt_roles(client.services)
        if roles is None:
            raise invalid("truemotion_gatt")
        tx, rx = roles

        link = self._link = Link(client, tx, rx, Receiver(self._state.observations))

        def receive(sender: BleakGATTCharacteristic, value: bytearray) -> None:
            if self._link_is_current(link):
                packet = bytes(value)
                self.forward_raw_notification(sender.uuid, packet)
                if (version := link.receiver.feed(packet)) is not None:
                    self.forward_controller_state_updates(FIRMWARE(version[:255]))

        try:
            # BlueZ only discovers its write MTU on demand. Other transports
            # negotiate it themselves. The app's MTU request is best effort.
            acquire = getattr(getattr(client, "_backend", None), "_acquire_mtu", None)
            if callable(acquire):
                with suppress(AssertionError, BleakError, OSError, TimeoutError):
                    result = acquire()
                    if isawaitable(result):
                        await result
            self._current_link()
            await client.start_notify(rx, receive)
            self._current_link()
            version = self._state.observations.version
            if version is not None:
                self.forward_controller_state_updates(FIRMWARE(version[:255]))
        except BaseException:
            if self._link is link:
                self.on_disconnect()
            raise

    def on_disconnect(self) -> None:
        self._link = None
        self._cleanup_context = None

    def on_connection_release(self, reason: str) -> None:
        # Unexpected loss fences writes immediately and retains the observations.
        # Explicit teardown clears GA. The app does not remove GD on this path.
        self._state.observations.ga.clear()

    async def stop_notify(self) -> None:
        link = self._link
        self.on_disconnect()
        if link is not None and link.client.is_connected:
            await link.client.stop_notify(link.rx)

    async def _send(
        self,
        link: Link,
        command: bytes,
        cancel: asyncio.Event,
        on_write: Callable[[], None] | None = None,
        *,
        deadline: float | None = None,
        on_submit: Callable[[], None] | None = None,
    ) -> bool:
        async def write() -> None:
            self._record_command_trace(
                link.tx.uuid, command, response=False, characteristic=link.tx
            )
            async with asyncio.timeout(5):
                await link.client.write_gatt_char(link.tx, command, response=False)
            note_frame_written(cancel)
            if on_write is not None:
                on_write()

        # Waiting for the lane is cancellable. Only an admitted GATT write
        # must settle before the motion's finally block can send its release.
        async with self._ble_lock:
            if (
                cancel.is_set()
                or deadline is not None
                and asyncio.get_running_loop().time() > deadline
            ):
                note_frame_skipped()
                return False
            if not self._link_is_current(link):
                raise BedNotConnectedError
            if on_submit is not None:
                on_submit()
            await settled(write(), eager_start=True)
            return True

    async def _sequence(
        self,
        link: Link,
        bursts: Iterable[Burst],
        cancel: asyncio.Event,
        *,
        complete_release: bool = False,
    ) -> None:
        # Merge overlapping bursts into the one wire lane. Same-offset requests
        # keep their dispatch order. A slow write never spawns background work.
        frames = [
            (burst.offset_ms + index * burst.interval_ms, text(burst.command), burst.on_write)
            for burst in bursts
            for index in range(burst.count)
        ]
        loop = asyncio.get_running_loop()
        start = loop.time()
        first_error: BleakError | TimeoutError | None = None
        for offset, packet, callback in sorted(frames, key=lambda frame: frame[0]):
            delay = start + offset / 1000 - loop.time()
            try:
                if delay > 0:
                    await cancellable(asyncio.sleep(delay), cancel)
            except asyncio.CancelledError:
                note_frame_skipped()
                raise
            try:
                if first_error is not None and not self._link_is_current(link):
                    break
                if not await self._send(link, packet, cancel, callback):
                    break
            except BedNotConnectedError:
                if first_error is None:
                    raise
                break
            except (BleakError, TimeoutError) as err:
                if not complete_release:
                    raise
                if first_error is None:
                    first_error = err
                if not self._link_is_current(link):
                    break
        if first_error is not None:
            raise first_error

    async def _run(self, *bursts: Burst) -> None:
        await self._sequence(self._current_link(), bursts, self._coordinator.cancel_command)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._current_link()
        cancel = cancel_event or self._coordinator.cancel_command
        for index in range(repeat_count):
            if index:
                await cancellable(asyncio.sleep(repeat_delay_ms / 1000), cancel)
            if not await self._send(link, command, cancel):
                break

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(self._controls)

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self._controls or not 1 <= duration_ms <= 60000:
            raise invalid("truemotion_control", control=control)

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        await self._motion(control, self.leased_hold_ms(duration_ms))

    async def _motion(self, control: str, duration_ms: int | None = None) -> None:
        if control not in self._controls:
            raise invalid("truemotion_control", control=control)
        axis, direction = self._controls[control]
        link = self._current_link()
        cancel = self._coordinator.cancel_command
        frame = text(axis.text(direction))
        submitted = False

        def submitting() -> None:
            nonlocal submitted
            submitted = True

        try:
            if duration_ms is None or duration_ms <= axis.interval_ms:
                # A finite press shorter than its first refresh is a tap.
                await self._send(link, frame, cancel, on_submit=submitting)
            else:
                loop = asyncio.get_running_loop()
                started = loop.time()
                end = started + duration_ms / 1000
                interval = axis.interval_ms / 1000
                for tick in range(1, app.HOLD_TICKS + 1):
                    now = loop.time()
                    scheduled = started + tick * interval
                    if scheduled > end or now >= end:
                        await cancellable(asyncio.sleep(max(0, end - now)), cancel)
                        break
                    # A delayed BLE write may overrun a refresh slot. Skip it
                    # instead of backfilling motion at the end of the hold.
                    if scheduled < now:
                        continue
                    await cancellable(asyncio.sleep(scheduled - now), cancel)
                    if not await self._send(
                        link,
                        frame,
                        cancel,
                        deadline=end,
                        on_submit=submitting,
                    ):
                        break
        finally:
            if submitted and self._link_is_current(link):
                await settled(self._finish_movement(link))

    async def _release(self, link: Link) -> None:
        await self._sequence(
            link,
            (Burst(app.STOP, 3, app.REPEAT_MS),),
            asyncio.Event(),
            complete_release=True,
        )

    async def _finish_movement(self, link: Link) -> None:
        try:
            await self._release(link)
        except BedNotConnectedError:
            if self._link_is_current(link):
                raise
            return
        if (context := current_command_context()) is not None:
            context.cleanup_stop_sent = True
            self._cleanup_context = context

    async def _motor_stop(self) -> None:
        context = current_command_context()
        if context is not None and any(
            previous is self._cleanup_context and previous.cleanup_stop_sent
            for previous in context.preempted_contexts
        ):
            return
        # Explicit motor STOP has its own uncancelled event, including when
        # requested while cancelling an earlier movement.
        await settled(self._release(self._current_link()))

    @property
    def paired_cleanup_stop(self) -> Callable[[], Awaitable[None]]:
        return self._motor_stop

    async def stop_all(self) -> None:
        if CONTROLLER_GESTURE_RELEASE.get():
            return
        if not self.profile.dedicated_stop:
            await self._motor_stop()
            return
        link = self._current_link()
        await settled(
            self._sequence(
                link,
                (
                    Burst(app.STOP),
                    Burst(
                        app.massage("HEAD", "DT", "00"),
                        2,
                        150,
                        on_write=partial(self._set_timer, "HEAD", "00"),
                    ),
                    Burst(
                        app.massage("FOOT", "DT", "00"),
                        2,
                        200,
                        on_write=partial(self._set_timer, "FOOT", "00"),
                    ),
                ),
                asyncio.Event(),
            )
        )
        self._state.level = "00"

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                axis.key,
                f"truemotion_{axis.key}" if axis.key in ("combined", "tl") else axis.key,
                partial(_move, control=f"{axis.key}_up"),
                partial(_move, control=f"{axis.key}_down"),
                _motor_stop,
                scheduler_resource=f"motor:{axis.key}",
                hold=ControllerMotorHoldSpec(
                    f"{axis.key}_up",
                    f"{axis.key}_down",
                    release_button_key="truemotion_release",
                    stop_scope="side",
                    press_hold_ms=None,
                ),
            )
            for axis in self.profile.axes
        )

    async def move_back_up(self) -> None:
        await self._motion("back_up")

    async def move_back_down(self) -> None:
        await self._motion("back_down")

    async def move_head_up(self) -> None:
        await self._motion("head_up")

    async def move_head_down(self) -> None:
        await self._motion("head_down")

    async def move_legs_up(self) -> None:
        await self._motion("legs_up")

    async def move_legs_down(self) -> None:
        await self._motion("legs_down")

    move_feet_up = move_legs_up
    move_feet_down = move_legs_down
    move_head_stop = move_back_stop = move_legs_stop = move_feet_stop = _motor_stop

    @property
    def supports_memory_presets(self) -> bool:
        return self.memory_slot_count > 0

    @property
    def memory_slot_count(self) -> int:
        return sum(mode in self.profile.presets for mode in ("M1", "M2"))

    @property
    def supports_memory_programming(self) -> bool:
        return "M1" in self.profile.saves

    def is_memory_slot_programmable(self, memory_num: int) -> bool:
        return f"M{memory_num}" in self.profile.saves and 1 <= memory_num <= self.memory_slot_count

    def validate_memory_recall(self, memory_num: int) -> None:
        if not 1 <= memory_num <= self.memory_slot_count:
            raise invalid("truemotion_control", control=f"M{memory_num}")

    @property
    def supports_preset_flat(self) -> bool:
        return "FLAT" in self.profile.presets

    @property
    def supports_preset_zero_g(self) -> bool:
        return "ZEROG" in self.profile.presets

    @property
    def supports_preset_anti_snore(self) -> bool:
        return "SNORE" in self.profile.presets

    @property
    def supports_preset_tv(self) -> bool:
        return "TV" in self.profile.presets

    async def _preset(self, mode: str, *, save: bool = False) -> None:
        if mode not in (self.profile.saves if save else self.profile.presets):
            raise invalid("truemotion_control", control=mode)
        await self._run(
            Burst(
                app.preset(mode, save=save),
                2 if self.profile.split else 3,
                app.SAVE_DELAY_MS + app.REPEAT_MS,
            )
            if save
            else Burst(app.preset(mode))
        )

    async def preset_flat(self) -> None:
        await self._preset("FLAT")

    async def preset_zero_g(self) -> None:
        await self._preset("ZEROG")

    async def preset_anti_snore(self) -> None:
        await self._preset("SNORE")

    async def preset_tv(self) -> None:
        await self._preset("TV")

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._preset(f"M{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        if not self.is_memory_slot_programmable(memory_num):
            raise invalid("truemotion_control", control=f"M{memory_num}")
        await self._preset(f"M{memory_num}", save=True)

    @property
    def supports_lights(self) -> bool:
        return self.profile.light

    @property
    def supports_discrete_light_control(self) -> bool:
        return self.profile.light

    async def lights_on(self) -> None:
        await self._light(True)

    async def lights_off(self) -> None:
        await self._light(False)

    async def _light(self, enabled: bool) -> None:
        if not self.profile.light:
            raise invalid("truemotion_control", control="light")
        await self._run(Burst(app.light(enabled), 3, app.REPEAT_MS))

    async def set_lock(self, enabled: bool) -> None:
        if not self.profile.lock:
            raise invalid("truemotion_control", control="lock")
        await self._run(Burst(app.lock(enabled), 3, app.REPEAT_MS))

    def _set_timer(self, zone: app.Zone, code: str) -> None:
        self._state.timers[zone] = code
        if self.profile.massage_schedule == "b603":
            if not any(value != "00" for value in self._state.timers.values()):
                self._state.level = None
        elif code != "00" and self._state.level is None:
            self._state.level = "00"

    async def massage_timer_next(self, zone: app.Zone) -> None:
        if self.profile.massage_schedule is None:
            raise invalid("truemotion_control", control="massage timer")
        code = _next(self._state.timers[zone], app.TIMERS)
        await self._run(
            Burst(
                app.massage(zone, "DT", code),
                3,
                app.REPEAT_MS,
                on_write=partial(self._set_timer, zone, code),
            )
        )

    async def massage_level_next(self) -> None:
        schedule = self.profile.massage_schedule
        head_on, foot_on = (self._state.timers[zone] != "00" for zone in ZONES)
        if schedule is None or (schedule != "b202" and not (head_on or foot_on)):
            raise invalid("truemotion_massage_off")
        level = _next(self._state.level, app.LEVELS)

        def record_level() -> None:
            self._state.level = level

        head = app.massage("HEAD", "LV", level)
        foot = app.massage("FOOT", "LV", level)
        if schedule == "b202":
            await self._run(
                Burst(head, 3, 100, on_write=record_level),
                Burst(
                    foot if foot_on else app.massage("FOOT", "DT", "00"),
                    3,
                    100,
                    on_write=record_level,
                ),
            )
        elif schedule == "b603":
            await self._run(
                *(
                    burst
                    for active, burst in (
                        (head_on, Burst(head, 3, 100, on_write=record_level)),
                        (foot_on, Burst(foot, 3, 150 if head_on else 100, on_write=record_level)),
                    )
                    if active
                )
            )
        else:
            await self._run(
                *(
                    burst
                    for active, burst in (
                        (head_on, Burst(head, on_write=record_level)),
                        (foot_on, Burst(foot, offset_ms=150, on_write=record_level)),
                    )
                    if active
                )
            )

    @property
    def controller_switch_specs(self) -> tuple[ControllerSwitchSpec, ...]:
        if not self.profile.lock:
            return ()
        return (
            ControllerSwitchSpec(
                "truemotion_lock", "truemotion_lock", _lock, assumed_state=True, icon="mdi:lock"
            ),
        )

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        if self.profile.split:
            return ()
        return (
            ControllerStateSensorSpec(
                "truemotion_firmware",
                "truemotion_firmware",
                FIRMWARE,
                "mdi:chip",
                entity_registry_enabled_default=True,
            ),
        )

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        specs = [
            ControllerButtonSpec(
                "truemotion_release",
                "Release motion",
                _motor_stop,
                release_only=True,
                card=CARD_HIDDEN,
                translation_key="truemotion_release",
            ),
        ]
        if not self.profile.split:
            specs.append(
                ControllerButtonSpec(
                    "truemotion_version",
                    "Read firmware version",
                    _version,
                    diagnostic=True,
                    translation_key="truemotion_version",
                )
            )
        if self.profile.has_beep:
            specs.append(
                ControllerButtonSpec(
                    "truemotion_beep", "Enable beep", _beep, translation_key="truemotion_beep"
                )
            )
        for mode, label in _PRESETS.items():
            if mode in self.profile.presets:
                spec = catalog_button(
                    f"truemotion_{mode.lower()}",
                    label,
                    partial(_preset, mode=mode),
                    kind=Kind.PRESET,
                    invalidates_position=True,
                )
                assert spec is not None
                specs.append(spec)
        for mode, label in _SAVE_PRESETS.items():
            if mode in self.profile.saves:
                specs.append(
                    save_button(
                        f"truemotion_save_{mode.lower()}",
                        label,
                        partial(_preset, mode=mode, save=True),
                    )
                )
        if self.profile.massage_schedule is not None:
            for zone in ZONES:
                label = f"{zone.title()} massage timer"
                specs.append(
                    ControllerButtonSpec(
                        f"truemotion_timer_{zone.lower()}",
                        label,
                        partial(_timer, zone=zone),
                        card=CARD_MASSAGE_TIMER,
                        cancel_movement=False,
                        translation_key=f"truemotion_timer_{zone.lower()}",
                    )
                )
            specs.append(
                massage_button(
                    "truemotion_level", "Next massage level", _level, cancel_movement=False
                )
            )
        return tuple(specs)


def _next(value: str | None, choices: tuple[str, ...]) -> str:
    return choices[0] if value is None else choices[(choices.index(value) + 1) % len(choices)]


async def _move(controller: BedController, *, control: str) -> None:
    await require_controller(controller, TrueMotionController)._motion(control)


async def _motor_stop(controller: BedController) -> None:
    await require_controller(controller, TrueMotionController)._motor_stop()


async def _lock(controller: BedController, enabled: bool) -> None:
    await require_controller(controller, TrueMotionController).set_lock(enabled)


async def _preset(controller: BedController, *, mode: str, save: bool = False) -> None:
    await require_controller(controller, TrueMotionController)._preset(mode, save=save)


async def _timer(controller: BedController, *, zone: app.Zone) -> None:
    await require_controller(controller, TrueMotionController).massage_timer_next(zone)


async def _level(controller: BedController) -> None:
    await require_controller(controller, TrueMotionController).massage_level_next()


async def _version(controller: BedController) -> None:
    await require_controller(controller, TrueMotionController)._run(Burst(app.VERSION))


async def _beep(controller: BedController) -> None:
    ctrl = require_controller(controller, TrueMotionController)
    if not ctrl.profile.has_beep:
        raise invalid("truemotion_control", control="beep")
    await ctrl._run(Burst(app.BEEP))


async def build_controller(ctx: BuildContext) -> TrueMotionController:
    entry = ctx.coordinator.entry
    observed = ctx.advertisement_name or ctx.live_device_name
    stored_name = ctx.data.get(CONF_BLE_DEVICE_NAME)
    name = stored_name if isinstance(stored_name, str) else observed
    if not isinstance(name, str) or not app.name_matches(name):
        raise invalid("truemotion_name")
    if isinstance(entry, ChildEntryView):
        primary = entry.paired_child(SIDE_LEFT)
        primary_name = primary.get(CONF_BLE_DEVICE_NAME) if primary is not None else None
        if not isinstance(primary_name, str) or not app.supports_pair_primary(primary_name):
            raise invalid("truemotion_pair")
        return TrueMotionController(ctx.coordinator, app.profile_for_name(primary_name, split=True))
    return TrueMotionController(ctx.coordinator, app.profile_for_name(name))
