"""Bed Tech's separate HJ_Bed intervention and local user-mode receiver."""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
from typing import TYPE_CHECKING

from homeassistant.util import dt as dt_util

from ...command_scheduler import current_command_context, note_frame_skipped
from ...errors import failed, invalid
from ..cancellation import settled
from ..entity_specs import ControllerStateBinarySensorSpec, ControllerStateSensorSpec
from ..richmat_mh.app_sleep import RichmatMHAppSleepController
from ..ruf_richmat.protocol import sleep_frame

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

_TRAFFIC: ContextVar[bool] = ContextVar("bedtech_auxiliary_traffic", default=False)


class BedTechSleepController(RichmatMHAppSleepController):
    """Reuse FA transport ownership, exposing only local bed settings."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator, app="bedtech_classic")

    @property
    def controller_state_sensor_specs(self) -> tuple[ControllerStateSensorSpec, ...]:
        # Heart/breath rates, occupancy and movement are excluded reporting.
        return ()

    @property
    def controller_state_binary_sensor_specs(self) -> tuple[ControllerStateBinarySensorSpec, ...]:
        return ()

    def validate_direct_user_mode(self, option: str) -> None:
        if option not in ("single", "double"):
            raise invalid("option_unavailable")

    async def direct_user_mode(self, option: str) -> None:
        self.validate_direct_user_mode(option)
        await self.write_command(sleep_frame(0x14, bytes((1, 3, 1 if option == "single" else 2))))

    def _apply_frame(self, frame: bytes) -> None:
        # Attributes and their ACK are local session traffic. Physiological
        # reports never create an HA state model for this app.
        if frame[3] in (5, 0x12, 0xA5):
            super()._apply_frame(frame)

    def _notify(self, sender: object, data: bytearray) -> None:
        if self._coordinator.controller is self and self.client is self._owner:
            super()._notify(sender, data)

    @property
    def supports_clock_sync(self) -> bool:
        return True

    async def sync_clock(self) -> None:
        digits = f"{int(dt_util.now().timestamp()):x}"
        if len(digits) % 2:
            raise invalid("option_unavailable")
        await self.write_command(sleep_frame(5, bytes.fromhex(digits)[::-1]))

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        owner, generation, char = self._owner, self._generation, self._char
        entry, entry_data = self._coordinator.entry, dict(self._coordinator.entry.data)
        epoch = self._coordinator.stop_epoch
        cancel = cancel_event or self._coordinator.cancel_command

        def validate(*, check_cancel: bool = True) -> None:
            if (
                owner is None
                or char is None
                or self.client is not owner
                or not owner.is_connected
                or generation != self._generation
                or self._coordinator.controller is not self
                or self._coordinator.entry is not entry
                or self._coordinator.entry.data != entry_data
                or self.command_side is not None
            ):
                raise failed("bed_changed")
            context = current_command_context()
            if check_cancel and (
                self._coordinator.stop_epoch != epoch
                or cancel.is_set()
                or context
                and context.cancel_event.is_set()
            ):
                note_frame_skipped()
                raise asyncio.CancelledError

        validate()
        assert char is not None and owner is not None
        for index in range(repeat_count):
            await self._wait_cancel(
                max(0, self._next_write - asyncio.get_running_loop().time()), cancel
            )

            def before_write() -> None:
                validate()
                self._next_write = asyncio.get_running_loop().time() + 0.3

            await settled(
                self._write_gatt_with_retry(
                    char.uuid,
                    command,
                    characteristic=char,
                    expected_client=owner,
                    response="write" in char.properties,
                    cancel_event=cancel_event,
                    before_write=before_write,
                    track_command_write=not _TRAFFIC.get(),
                )
            )
            validate(check_cancel=False)
            if index + 1 < repeat_count:
                await self._wait_cancel(repeat_delay_ms / 1000, cancel)

    @staticmethod
    async def _wait_cancel(delay: float, cancel: asyncio.Event) -> None:
        try:
            await asyncio.wait_for(cancel.wait(), delay)
        except TimeoutError:
            pass

    async def _serialized_write(self, frame: bytes) -> None:
        owner, generation = self._owner, self._generation
        entry, data = self._coordinator.entry, dict(self._coordinator.entry.data)
        epoch = self._coordinator.stop_epoch

        async def send(_controller: object) -> None:
            if (
                self.client is not owner
                or generation != self._generation
                or self._coordinator.entry is not entry
                or self._coordinator.entry.data != data
            ):
                raise failed("bed_changed")
            token = _TRAFFIC.set(True)
            try:
                await self.write_command(frame)
            finally:
                _TRAFFIC.reset(token)

        await self._coordinator.async_execute_controller_command(
            send,
            cancel_running=False,
            expected_stop_epoch=epoch,
        )
