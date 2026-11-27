"""Atlas Lift's ordinary Cama Lift controls on one unambiguous Richmat link."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from ...card import CARD_MASSAGE, CARD_PRESET_SAVE
from ...codec import richmat as codec
from ...command_scheduler import CommandContext, current_command_context, note_frame_skipped
from ...errors import BedNotConnectedError, failed
from ...profiles.richmat import ATLAS_LIFT, ATLAS_LIFT_INITIALIZATION, Button, RichmatProfile
from ..base import BedController
from ..cancellation import cancellable, settled
from ..entity_specs import ControllerButtonSpec, MotorControlSpec
from .controller import RichmatProfileController

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ...coordinator import AdjustableBedCoordinator
    from ..lifecycle import ControllerSession


@dataclass(frozen=True, slots=True)
class _Link:
    client: BleakClient
    tx: BleakGATTCharacteristic
    notify: BleakGATTCharacteristic | None
    single: bool


class _MotionWindowEnded(Exception):
    """The scheduled motion window ended before this frame could dispatch."""


def select_link(
    client: BleakClient, profile: RichmatProfile = ATLAS_LIFT, error_key: str = "atlas_lift_gatt"
) -> _Link:
    """Identify the same supported service and TX in setup and at runtime."""
    routes = {
        transport.service_uuid: transport
        for transport in (codec.TRANSPORTS[key] for key in profile.transports)
    }
    matches = [
        (service, routes[uuid])
        for service in client.services
        if (uuid := service.uuid.lower()) in routes
    ]
    # The app can select framing from a different service than its TX.
    # Require one supported service so the encoder always belongs to its TX.
    if len(matches) != 1:
        raise failed(error_key)
    service, route = matches[0]
    writes = [
        char
        for char in service.characteristics
        if char.uuid.lower() == route.write_uuid and "write" in char.properties
    ]
    if len(writes) != 1:
        raise failed(error_key)
    notify = next((char for char in service.characteristics if "notify" in char.properties), None)
    return _Link(client, writes[0], notify, route.single)


class RichmatSessionController(RichmatProfileController):
    """Fixed product controls with an encoder and characteristic tied to the connection."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        profile: RichmatProfile,
        initialization: tuple[tuple[str, int], ...],
        gatt_error_key: str,
    ) -> None:
        super().__init__(coordinator, profile, char_uuid="")
        self._initialization = initialization
        self._gatt_error_key = gatt_error_key
        self._link: _Link | None = None
        self._notifying = False
        self._cleanup_context: CommandContext | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        return self._link.tx.uuid if self._link is not None else ""

    @property
    def supports_single_address_pairing(self) -> bool:
        return False

    @property
    def reconnect_for_explicit_stop(self) -> bool:
        # A one-shot preset has no release frame when the pair drops its link.
        return True

    @property
    def requires_notification_channel(self) -> bool:
        return self._link is not None and self._link.notify is not None

    def _current_link(self, expected: _Link | None = None) -> _Link:
        link = self._link
        if (
            link is None
            or expected is not None
            and link is not expected
            or self.client is not link.client
            or not link.client.is_connected
        ):
            raise BedNotConnectedError
        return link

    async def async_on_connect(self, session: ControllerSession) -> None:
        client = session.client
        if client is None or not session.is_current():
            raise BedNotConnectedError
        self._link = link = select_link(client, self.profile, self._gatt_error_key)
        await session.async_start_notify()
        cancel = asyncio.Event()
        for action, code in self._initialization:
            await self._write_on(
                link,
                codec.function(code, action=action, single=link.single),
                cancel,
                track_command_write=False,
            )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        link = self._current_link()
        if link.notify is None:
            return

        def receive(sender: BleakGATTCharacteristic, data: bytearray) -> None:
            if self._link is link and self.client is link.client and self._notifying:
                self._receive_notification(sender.uuid, bytes(data))

        async with self.ble_lock:
            self._current_link(link)
            if not self._notifying:
                await link.client.start_notify(link.notify, receive)
                self._current_link(link)
                self._notifying = True

    def _receive_notification(self, sender: str, data: bytes) -> None:
        self.forward_raw_notification(sender, data)

    async def stop_notify(self) -> None:
        link = self._link
        if link is None or link.notify is None:
            return
        async with self.ble_lock:
            if self._link is link and self.client is link.client and self._notifying:
                self._notifying = False
                if link.client.is_connected:
                    await link.client.stop_notify(link.notify)

    def on_disconnect(self) -> None:
        self._link = None
        self._notifying = False
        self._cleanup_context = None

    def _build_command(self, command_byte: int) -> bytes:
        return codec.function(command_byte, single=self._current_link().single)

    async def _write_on(
        self,
        link: _Link,
        command: bytes,
        cancel: asyncio.Event,
        *,
        before_write: Callable[[], None] | None = None,
        track_command_write: bool = True,
    ) -> None:
        caller = asyncio.current_task()

        def verify() -> None:
            self._current_link(link)
            if caller is not None and caller.cancelling():
                note_frame_skipped()
                raise asyncio.CancelledError
            if before_write is not None:
                before_write()

        # Let an in-flight GATT write settle before the caller sends STOP.
        await settled(
            self._write_gatt_with_retry(
                link.tx.uuid,
                command,
                cancel_event=cancel,
                response="write-without-response" not in link.tx.properties,
                characteristic=link.tx,
                expected_client=link.client,
                before_write=verify,
                track_command_write=track_command_write,
            ),
            eager_start=True,
        )

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
            await self._write_on(link, command, cancel)

    def motor_pulse_settings(self) -> tuple[int, int]:
        repeat_ms = self.profile.motor_repeat_ms
        assert repeat_ms is not None
        return self._coordinator.motor_pulse_count, repeat_ms

    async def _move_with_stop(self, command_byte: int, *, duration_ms: int | None = None) -> None:
        link = self._current_link()
        cancel = self._coordinator.cancel_command
        count, repeat_ms = self.motor_pulse_settings()
        command = codec.function(command_byte, single=link.single)
        attempted = False
        loop = asyncio.get_running_loop()
        repeat_s = repeat_ms / 1000
        started = loop.time()
        leased_count = self.leased_hold_refreshes(repeat_ms)
        if leased_count is not None:
            duration_ms = None  # The scheduler owns the renewable hold deadline.
        deadline = started + duration_ms / 1000 if duration_ms is not None else None
        # A finite timed move starts with an immediate pulse. Ordinary cover
        # presses and renewable holds keep the app's first timer tick.
        next_pulse = started if deadline is not None else started + repeat_s
        context = current_command_context()
        if duration_ms is not None:
            count = (duration_ms + repeat_ms - 1) // repeat_ms

        def mark_attempt() -> None:
            nonlocal attempted, next_pulse
            expires = context.hold_deadline if leased_count is not None and context else deadline
            if expires is not None and loop.time() >= expires:
                note_frame_skipped()
                raise _MotionWindowEnded
            attempted = True
            next_pulse = loop.time() + repeat_s

        async def release() -> None:
            if attempted:
                await self._release_on(link)
                if context is not None:
                    context.cleanup_stop_sent = True
                    self._cleanup_context = context

        budget = asyncio.timeout_at(deadline)
        write_timed_out = False
        async with self.releasing(release):
            try:
                async with budget:
                    for _ in range(leased_count or count):
                        if deadline is not None and next_pulse >= deadline:
                            break
                        delay = next_pulse - loop.time()
                        if delay > 0:
                            await cancellable(asyncio.sleep(delay), cancel)
                        try:
                            await self._write_on(link, command, cancel, before_write=mark_attempt)
                        except TimeoutError:
                            write_timed_out = True
                            raise
                    if deadline is not None:
                        await cancellable(asyncio.sleep(max(0, deadline - loop.time())), cancel)
            except _MotionWindowEnded:
                return
            except TimeoutError:
                if write_timed_out or not budget.expired():
                    raise
                if not attempted:
                    note_frame_skipped()

    async def _release_on(self, link: _Link) -> None:
        assert self.profile.stop is not None
        await self._write_on(
            link,
            codec.function(self.profile.stop, single=link.single),
            asyncio.Event(),
            track_command_write=False,
        )

    async def _send_stop(self) -> None:
        link = self._current_link()
        context = current_command_context()
        released = self._cleanup_context
        if (
            context is not None
            and released is not None
            and released.cleanup_stop_sent
            and any(owner is released for owner in context.preempted_contexts)
        ):
            released.cleanup_stop_sent = False
            self._cleanup_context = None
            return
        await self._release_on(link)

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        # A generic motor count restored from a different app cannot add axes.
        back, legs = super().motor_control_specs[:2]
        return (
            replace(
                back,
                timed_move_fn=lambda controller, up, ms: _session(controller)._timed_motor(
                    "head_up" if up else "head_down", ms
                ),
            ),
            replace(
                legs,
                timed_move_fn=lambda controller, up, ms: _session(controller)._timed_motor(
                    "feet_up" if up else "feet_down", ms
                ),
            ),
        )

    async def _timed_motor(self, control: Button, duration_ms: int) -> None:
        await self._move_with_stop(self._code(control), duration_ms=duration_ms)


class AtlasLiftController(RichmatSessionController):
    """Cama Lift's fixed normal controls and app-specific buttons."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator, ATLAS_LIFT, ATLAS_LIFT_INITIALIZATION, "atlas_lift_gatt")

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def supports_light_toggle_control(self) -> bool:
        return False

    @property
    def auto_enable_massage(self) -> bool:
        return True

    @property
    def supports_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_head_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_foot_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return False

    async def massage_head_up(self) -> None:
        await self._send("massage_head_up")

    async def _save_zero_g(self) -> None:
        await self._send("save_zero_g")

    async def _save_anti_snore(self) -> None:
        await self._send("save_anti_snore")

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        return (
            ControllerButtonSpec(
                "atlas_lift_save_zero_g",
                "Save zero gravity",
                lambda controller: _atlas_lift(controller)._save_zero_g(),
                translation_key="catalog_save",
                translation_placeholders={"preset": "Zero gravity"},
                card=CARD_PRESET_SAVE,
                requires_confirmation=True,
                combine_sides=True,
            ),
            ControllerButtonSpec(
                "atlas_lift_save_anti_snore",
                "Save anti-snore",
                lambda controller: _atlas_lift(controller)._save_anti_snore(),
                translation_key="catalog_save",
                translation_placeholders={"preset": "Anti-snore"},
                card=CARD_PRESET_SAVE,
                requires_confirmation=True,
                combine_sides=True,
            ),
            ControllerButtonSpec(
                "massage_head_up",
                "Increase head massage",
                lambda controller: controller.massage_head_up(),
                translation_key="massage_head_up",
                icon="mdi:arrow-up",
                card=CARD_MASSAGE,
                combine_sides=True,
            ),
        )


def _atlas_lift(controller: BedController) -> AtlasLiftController:
    assert isinstance(controller, AtlasLiftController)
    return controller


def _session(controller: BedController) -> RichmatSessionController:
    assert isinstance(controller, RichmatSessionController)
    return controller
