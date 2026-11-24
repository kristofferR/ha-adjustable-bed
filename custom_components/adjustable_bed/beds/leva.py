"""Leva's three command routes, exact GATT admission and session-owned release."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from homeassistant.util import dt as dt_util

from ..card import CARD_HIDDEN, CARD_MASSAGE, CARD_MASSAGE_TIMER, CARD_PRESETS
from ..command_scheduler import CommandContext, current_command_context
from ..const import CONF_PRODUCT_TYPE, NORDIC_UART_READ_CHAR_UUID
from ..errors import BedNotConnectedError, invalid
from ..profiles import leva as app
from .base import CONTROLLER_GESTURE_RELEASE, BedController, ProfileExecution, require_controller
from .builder import BuildContext
from .cancellation import settled
from .entity_specs import ControllerButtonSpec, ControllerMotorHoldSpec, MotorControlSpec

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator
    from .lifecycle import ControllerSession

_LOGGER = logging.getLogger(__name__)
_RELEASE_KEY = "leva_release"


@dataclass(slots=True)
class _Link:
    client: BleakClient
    writes: dict[app.Route, BleakGATTCharacteristic]
    notify: BleakGATTCharacteristic | None
    listener: object | None = None
    clock_ready: bool = False
    released_hold: CommandContext | None = None


def resolve_gatt(client: BleakClient, profile: app.LevaProfile, name: str) -> _Link:
    """Bind one verified receiver to its exact GATT roles, without writing."""

    def receiver_error() -> BedNotConnectedError:
        return BedNotConnectedError(
            "leva_receiver_mismatch", receiver=app.RECEIVERS[profile.receiver]
        )

    evolution, okin = app.TRANSPORTS["evolution"], app.TRANSPORTS["okin"]
    nordic_writes: list[BleakGATTCharacteristic] = []
    okin_writes: list[BleakGATTCharacteristic] = []
    nordic_notifies: list[BleakGATTCharacteristic] = []
    okin_service_present = False
    for service in client.services or ():
        if service.uuid.lower() == evolution.service:
            nordic_writes.extend(
                c for c in service.characteristics if c.uuid.lower() == evolution.write
            )
            nordic_notifies.extend(
                c for c in service.characteristics if c.uuid.lower() == NORDIC_UART_READ_CHAR_UUID
            )
        elif service.uuid.lower() == okin.service:
            okin_service_present = True
            okin_writes.extend(c for c in service.characteristics if c.uuid.lower() == okin.write)

    # A name or a service UUID alone can select the wrong app route. Require
    # exact, unambiguous service/characteristic pairs and reject that conflict.
    live_receiver = (
        "dual"
        if nordic_writes and okin_writes
        else "okin"
        if okin_writes
        else "nordic"
        if nordic_writes and not (okin_service_present or app.okin_name(name))
        else None
    )
    if live_receiver != profile.receiver or len(nordic_writes) > 1 or len(okin_writes) > 1:
        raise receiver_error()

    writes: dict[app.Route, BleakGATTCharacteristic] = {}
    for route in profile.routes:
        transport = app.TRANSPORTS[route]
        char = (okin_writes if route == "okin" else nordic_writes)[0]
        required = "write" if transport.response else "write-without-response"
        if required not in char.properties:
            raise receiver_error()
        writes[route] = char

    notify = None
    if profile.receiver == "nordic" and len(nordic_notifies) == 1:
        incoming = nordic_notifies[0]
        if {"notify", "indicate"}.intersection(incoming.properties):
            notify = incoming
    return _Link(client, writes, notify)


class _HoldElapsed(Exception):
    """The admitted pulse expired while waiting for the BLE write lane."""


async def _pause(event: asyncio.Event, seconds: float) -> None:
    if seconds > 0:
        try:
            async with asyncio.timeout(seconds):
                await event.wait()
        except TimeoutError:
            pass


class LevaController(ProfileExecution[app.LevaProfile], BedController):
    """Control one explicitly selected model and receiver."""

    def __init__(
        self, coordinator: AdjustableBedCoordinator, profile: app.LevaProfile, name: str
    ) -> None:
        super().__init__(coordinator)
        self.profile = profile
        self._device_name = name
        self._link: _Link | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        return app.TRANSPORTS[self.profile.remote or self.profile.home].write

    @property
    def requires_notification_channel(self) -> bool:
        return self.profile.receiver == "nordic"

    @property
    def supports_motor_control(self) -> bool:
        return bool(self.profile.axes)

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def commands_share_timer(self) -> bool:
        return True

    async def async_read_device_info(self, session: ControllerSession) -> bool:
        return True

    async def async_discover_capabilities(self) -> None:
        self.on_disconnect()
        client = self.client
        if client is None or not client.is_connected:
            raise BedNotConnectedError()

        self._link = resolve_gatt(client, self.profile, self._device_name)

    def _is_live(self, link: _Link) -> bool:
        return self._link is link and self.client is link.client and link.client.is_connected

    def _live(self) -> _Link:
        if self._link is None or not self._is_live(self._link):
            raise BedNotConnectedError()
        return self._link

    async def async_on_connect(self, session: ControllerSession) -> None:
        link = self._live()
        await session.async_start_notify()
        await asyncio.sleep(app.SETUP_SECONDS)
        if not self._is_live(link) or not session.is_current():
            raise BedNotConnectedError()

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._live()
        char = link.notify
        if char is None or link.listener is not None:
            return
        listener = object()
        link.listener = listener

        def received(_sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if self._is_live(link) and link.listener is listener:
                self.forward_raw_notification(char.uuid, bytes(data))

        try:
            # Bleak manages the characteristic's CCCD and local event routing.
            await link.client.start_notify(char, received)
        except BleakError, TimeoutError:
            link.listener = None
            _LOGGER.debug("Leva Nordic notification subscription failed", exc_info=True)

    async def stop_notify(self) -> None:
        link = self._link
        if link is not None and link.listener is not None:
            link.listener = None
            if link.notify is not None and self._is_live(link):
                await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self._link = None

    async def _write(
        self,
        link: _Link,
        route: app.Route,
        frame: bytes,
        cancel: asyncio.Event,
        *,
        deadline: float | None = None,
        clock: bool = False,
        track: bool = True,
    ) -> None:
        transport = app.TRANSPORTS[route]
        char = link.writes[route]

        def validate() -> None:
            if not self._is_live(link):
                raise BedNotConnectedError()
            if deadline is not None and round(deadline - asyncio.get_running_loop().time(), 9) <= 0:
                raise _HoldElapsed

        for attempt, delay in enumerate((0.0, *transport.retry_gaps)):
            await _pause(cancel, delay)
            try:
                # Drain an in-flight backend write before releasing the scheduler lane.
                await settled(
                    self._write_gatt_with_retry(
                        char.uuid,
                        frame,
                        cancel_event=cancel,
                        response=transport.response,
                        characteristic=char,
                        expected_client=link.client,
                        before_write=validate,
                        command_factory=(lambda: app.clock_frame(dt_util.now())) if clock else None,
                        track_command_write=track,
                        log_errors=False,
                    )
                )
                return
            except BleakError, TimeoutError:
                if attempt == len(transport.retry_gaps):
                    raise

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        link = self._live()
        cancel = cancel_event or self._coordinator.cancel_command
        route = self.profile.remote or self.profile.home
        for index in range(repeat_count):
            if index:
                await _pause(cancel, repeat_delay_ms / 1000)
            if cancel.is_set():
                return
            await self._write(link, route, command, cancel)

    async def _clock(self, link: _Link, cancel: asyncio.Event, *, explicit: bool = False) -> None:
        link.clock_ready = False
        try:
            for index in range(app.CLOCK_COPIES):
                if index:
                    await _pause(cancel, app.CLOCK_GAP_SECONDS)
                if cancel.is_set():
                    return
                await self._write(link, "ascent", b"", cancel, clock=True, track=explicit)
        except BleakError, TimeoutError:
            if explicit:
                raise
            _LOGGER.debug("Leva clock initialization failed", exc_info=True)
            await _pause(cancel, app.CLOCK_SETTLE_SECONDS)
            return
        await _pause(cancel, app.CLOCK_SETTLE_SECONDS)
        link.clock_ready = self._is_live(link) and not cancel.is_set()

    async def _prepare(self, link: _Link, route: app.Route, cancel: asyncio.Event) -> None:
        if app.TRANSPORTS[route].clock_init and not link.clock_ready:
            await self._clock(link, cancel)

    async def _release(self, link: _Link, route: app.Route) -> bool:
        if not self._is_live(link):
            return False
        transport = app.TRANSPORTS[route]
        if transport.clock_init:
            link.clock_ready = False
        cancel = asyncio.Event()
        frame = transport.frame("stop")
        last_error: BleakError | TimeoutError | None = None
        sent = False
        loop = asyncio.get_running_loop()
        started = loop.time()
        for index in range(transport.stop_copies):
            if index:
                # P3 kicks off copies at fixed offsets. P1 waits after each
                # write (and any retries) before starting the next copy.
                delay = transport.stop_gap
                if route == "okin":
                    delay = started + index * transport.stop_gap - loop.time()
                await _pause(cancel, delay)
            if not self._is_live(link):
                break
            try:
                await self._write(link, route, frame, cancel, track=False)
            except (BleakError, TimeoutError) as err:
                last_error = err
            else:
                sent = True
        if not sent and last_error is not None:
            raise last_error
        return last_error is None and self._is_live(link)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key=axis,
                translation_key=axis,
                open_fn=lambda ctrl, a=axis: require_controller(ctrl, LevaController)._move(
                    a, "up"
                ),
                close_fn=lambda ctrl, a=axis: require_controller(ctrl, LevaController)._move(
                    a, "down"
                ),
                stop_fn=lambda ctrl: ctrl.stop_all(),
                scheduler_resource="*",
                hold=ControllerMotorHoldSpec(
                    f"{axis}_up",
                    f"{axis}_down",
                    stop_scope="side",
                    press_hold_ms=None,
                    press_is_native=True,
                    release_button_key=_RELEASE_KEY,
                ),
            )
            for axis in self.profile.axes
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(
            f"{axis}_{direction}" for axis in self.profile.axes for direction in ("up", "down")
        )

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if control not in self.held_control_options:
            raise self.not_supported(control)
        if (
            isinstance(duration_ms, bool)
            or not isinstance(duration_ms, int)
            or not 1 <= duration_ms <= 60_000
        ):
            raise invalid("leva_hold_duration")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        route = self.profile.remote
        assert route is not None
        cancel = self._coordinator.cancel_command
        if cancel.is_set():
            return
        link = self._live()
        frame = app.TRANSPORTS[route].frame(app.DIRECTIONS[control])
        loop = asyncio.get_running_loop()
        context = current_command_context()

        async def release_hold() -> None:
            if await self._release(link, route) and context is not None:
                context.cleanup_stop_sent = True
                link.released_hold = context

        async with self.releasing(release_hold):
            await self._prepare(link, route, cancel)
            deadline = loop.time() + self.leased_hold_ms(duration_ms) / 1000
            while not cancel.is_set() and round(deadline - loop.time(), 9) > 0:
                started = loop.time()
                try:
                    await self._write(link, route, frame, cancel, deadline=deadline)
                except _HoldElapsed:
                    break
                await _pause(cancel, min(started + app.REFRESH_MS / 1000, deadline) - loop.time())

    async def _move(self, axis: str, direction: str) -> None:
        duration = min(self._coordinator.motor_pulse_count * app.REFRESH_MS, 60_000)
        await self.hold_control(f"{axis}_{direction}", duration)

    async def move_head_up(self) -> None:
        await self._move("back", "up")

    async def move_head_down(self) -> None:
        await self._move("back", "down")

    move_back_up = move_head_up
    move_back_down = move_head_down

    async def move_feet_up(self) -> None:
        await self._move("legs", "up")

    async def move_feet_down(self) -> None:
        await self._move("legs", "down")

    move_legs_up = move_feet_up
    move_legs_down = move_feet_down

    async def move_pillow_up(self) -> None:
        await self._move("pillow", "up")

    async def move_pillow_down(self) -> None:
        await self._move("pillow", "down")

    async def move_lumbar_up(self) -> None:
        await self._move("lumbar", "up")

    async def move_lumbar_down(self) -> None:
        await self._move("lumbar", "down")

    async def stop_all(self) -> None:
        if CONTROLLER_GESTURE_RELEASE.get():
            return
        link = self._live()
        first, *additional = self.profile.routes
        previous = link.released_hold
        context = current_command_context()
        try:
            if (
                previous is not None
                and previous.cleanup_stop_sent
                and context is not None
                and any(owner is previous for owner in context.preempted_contexts)
            ):
                previous.cleanup_stop_sent = False
            else:
                await self._release(link, first)
        finally:
            for route in additional:
                await self._release(link, route)

    move_head_stop = move_back_stop = move_legs_stop = move_feet_stop = stop_all
    move_pillow_stop = move_lumbar_stop = stop_all

    async def _tap(self, action: str, *, home: bool = False) -> None:
        route = self.profile.home if home else self.profile.remote
        if route is None or not self.profile.allows_tap(action, home=home):
            raise invalid("leva_control_unavailable")
        link = self._live()
        cancel = self._coordinator.cancel_command
        await self._prepare(link, route, cancel)
        if not cancel.is_set():
            await self._write(link, route, app.TRANSPORTS[route].frame(action), cancel)

    async def preset_flat(self) -> None:
        await self._tap("flat", home=self.profile.remote is None)

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    async def preset_zero_g(self) -> None:
        await self._tap("zeroG", home=self.profile.remote is None)

    @property
    def supports_preset_anti_snore(self) -> bool:
        return self.profile.model.expanded

    async def preset_anti_snore(self) -> None:
        if not self.supports_preset_anti_snore:
            raise self.not_supported("anti-snore")
        await self._tap("antiSnore", home=self.profile.remote is None)

    @property
    def supports_preset_tv(self) -> bool:
        return self.profile.model.expanded

    async def preset_tv(self) -> None:
        if not self.supports_preset_tv:
            raise self.not_supported("TV")
        await self._tap("tv", home=self.profile.remote is None)

    @property
    def supports_memory_presets(self) -> bool:
        return self.memory_slot_count > 0

    @property
    def memory_slot_count(self) -> int:
        return self.profile.memory_slots

    @property
    def supports_memory_programming(self) -> bool:
        return False

    async def preset_memory(self, memory_num: int) -> None:
        self.validate_memory_recall(memory_num)
        await self._tap(f"memory{memory_num}")

    async def program_memory(self, memory_num: int) -> None:
        raise self.not_supported("save memory preset")

    @property
    def supports_lights(self) -> bool:
        return self.profile.expanded_remote

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.supports_lights

    async def lights_toggle(self) -> None:
        if not self.supports_lights:
            raise self.not_supported("light")
        await self._tap("underBedLight" if self.profile.remote == "evolution" else "light")

    @property
    def supports_massage(self) -> bool:
        return self.profile.expanded_remote

    @property
    def auto_enable_massage(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return self.supports_massage and self.profile.remote != "evolution"

    async def massage_mode_step(self) -> None:
        if not self.supports_massage_mode_step_control:
            raise self.not_supported("cycle massage mode")
        await self._tap("massageMode")

    @property
    def supports_clock_sync(self) -> bool:
        return self.profile.remote == "ascent"

    async def sync_clock(self) -> None:
        if not self.supports_clock_sync:
            raise self.not_supported("set bed clock")
        await self._clock(self._live(), self._coordinator.cancel_command, explicit=True)

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        buttons: list[ControllerButtonSpec] = []
        if self.profile.axes:
            buttons.append(
                ControllerButtonSpec(
                    _RELEASE_KEY,
                    "Release motion control",
                    lambda ctrl: ctrl.stop_all(),
                    translation_key=_RELEASE_KEY,
                    release_only=True,
                    card=CARD_HIDDEN,
                )
            )
        if self.supports_massage:
            for action, key, name in (
                ("massageHeadPlus", "head", "Cycle head massage"),
                ("massageFeetPlus", "foot", "Cycle feet massage"),
                ("massageTimer", "timer", "Cycle massage timer"),
            ):
                buttons.append(
                    ControllerButtonSpec(
                        f"leva_massage_{key}",
                        name,
                        lambda ctrl, a=action: require_controller(ctrl, LevaController)._tap(a),
                        translation_key=f"leva_massage_{key}",
                        cancel_movement=False,
                        card=CARD_MASSAGE_TIMER if key == "timer" else CARD_MASSAGE,
                    )
                )
        if self.profile.remote is not None and self.profile.remote != self.profile.home:
            for action, key, name in (
                ("flat", "flat", "Home quick flat"),
                ("zeroG", "zero_g", "Home quick zero gravity"),
                ("antiSnore", "anti_snore", "Home quick anti-snore"),
                ("tv", "tv", "Home quick TV"),
            ):
                if action in self.profile.home_presets:
                    buttons.append(
                        ControllerButtonSpec(
                            f"leva_home_{key}",
                            name,
                            lambda ctrl, a=action: require_controller(ctrl, LevaController)._tap(
                                a, home=True
                            ),
                            translation_key=f"leva_home_{key}",
                            invalidates_position=True,
                            card=CARD_PRESETS,
                        )
                    )
        return tuple(buttons)


async def build_controller(ctx: BuildContext) -> LevaController:
    """Keep the selected receiver and per-side app model as offline capability data."""
    profile = app.selected_profile(ctx.data.get(CONF_PRODUCT_TYPE), ctx.variant)
    if profile is None:
        raise invalid("leva_profile_required")
    return LevaController(ctx.coordinator, profile, ctx.live_device_name or "")
