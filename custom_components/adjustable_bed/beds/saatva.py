"""Saatva controls, with shared-foot split-top routing and no release frame."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ..codec import richmat as codec
from ..command_scheduler import note_frame_skipped
from ..const import SIDE_LEFT, SIDE_RIGHT
from ..errors import invalid
from ..profiles.saatva import (
    HEAD_CODES,
    LAYOUTS,
    MOTORS,
    PROFILES,
    REPEAT_MS,
    TEST_SECONDS,
    WRITE_UUID,
)
from ..state_keys import MASSAGE_TIMER_MINUTES
from .base import BedController
from .builder import BuildContext
from .cancellation import cancellable
from .catalog_buttons import Kind, catalog_button
from .entity_specs import ControllerButtonSpec, MotorControlSpec
from .richmat.controller import RichmatProfileController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator


async def _test_head(controller: BedController) -> None:
    assert isinstance(controller, SaatvaController)
    await controller.test_head()


class SaatvaController(RichmatProfileController):
    """An explicit app model; the advertisement never chooses capabilities."""

    def __init__(self, coordinator: AdjustableBedCoordinator, product: str) -> None:
        self.product = product
        self.layout = LAYOUTS[product]
        super().__init__(coordinator, PROFILES[product], char_uuid=WRITE_UUID)

    @property
    def supports_single_address_pairing(self) -> bool:
        return self.layout == "splitTop"

    @property
    def commands_share_timer(self) -> bool:
        return True

    @property
    def auto_stops_on_idle(self) -> bool:
        return True

    def motor_pulse_settings(self) -> tuple[int, int]:
        return self._coordinator.motor_pulse_count, REPEAT_MS

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return (
            MotorControlSpec(
                "back",
                "back",
                lambda c: c.move_back_up(),
                lambda c: c.move_back_down(),
                lambda c: c.move_back_stop(),
            ),
            MotorControlSpec(
                "legs",
                "legs",
                lambda c: c.move_legs_up(),
                lambda c: c.move_legs_down(),
                lambda c: c.move_legs_stop(),
                shared_across_sides=self.supports_single_address_pairing,
            ),
        )

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = REPEAT_MS,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        event = cancel_event or self._coordinator.cancel_command
        code = command[3]
        frames = (command,)
        if self.supports_single_address_pairing and code in HEAD_CODES:
            sides = (
                (0,)
                if self.command_side == SIDE_LEFT
                else (1,)
                if self.command_side == SIDE_RIGHT
                else (0, 1)
            )
            frames = tuple(codec.command(code, side) for side in sides)
        # Each head gets its own write, never an invented combined-head opcode.
        remaining_frames = repeat_count * len(frames)
        try:
            for index in range(repeat_count):
                started = asyncio.get_running_loop().time()
                for frame in frames:
                    await self._write_gatt_with_retry(
                        WRITE_UUID,
                        frame,
                        response=code not in MOTORS,
                        cancel_event=event,
                    )
                    remaining_frames -= 1
                    if event.is_set():
                        if remaining_frames:
                            note_frame_skipped()
                        return
                if index == repeat_count - 1:
                    return
                remaining = repeat_delay_ms / 1000 - (asyncio.get_running_loop().time() - started)
                if remaining > 0:
                    await cancellable(asyncio.sleep(remaining), event)
        except asyncio.CancelledError:
            if remaining_frames:
                note_frame_skipped()
            raise

    @property
    def controller_button_specs(self) -> tuple[ControllerButtonSpec, ...]:
        if self.supports_single_address_pairing and self.command_side == SIDE_RIGHT:
            return ()
        spec = catalog_button(
            "test_head",
            "Test head movement for 2 seconds",
            _test_head,
            kind=Kind.EXTRA,
            requires_confirmation=True,
            invalidates_position=True,
        )
        return (spec,) if spec is not None else ()

    async def test_head(self) -> None:
        if self.supports_single_address_pairing and self.command_side == SIDE_RIGHT:
            raise invalid("left_side_only")
        with self.side_scope(SIDE_LEFT):
            deadline = asyncio.timeout(TEST_SECONDS)
            try:
                async with deadline:
                    await self.write_command(codec.command(0x24), repeat_count=21)
            except TimeoutError:
                if not deadline.expired():
                    raise
            finally:
                await self._release()

    @property
    def supports_massage(self) -> bool:
        return "massage_toggle" in (self.profile.codes or {})

    @property
    def auto_enable_massage(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_off_control(self) -> bool:
        return False

    @property
    def supports_massage_toggle_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_head_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_foot_massage_toggle_control(self) -> bool:
        return False

    @property
    def supports_head_massage_intensity_step_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_foot_massage_intensity_step_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_massage_mode_step_control(self) -> bool:
        return self.supports_massage

    @property
    def supports_light_toggle_control(self) -> bool:
        return self.supports_lights

    @property
    def exposes_assumed_toggle_light(self) -> bool:
        # The two logical sides control one unreported light.
        return False

    async def massage_head_up(self) -> None:
        await self._send("massage_head_up")

    async def massage_head_down(self) -> None:
        await self._send("massage_head_down")

    async def massage_foot_up(self) -> None:
        await self._send("massage_foot_up")

    async def massage_foot_down(self) -> None:
        await self._send("massage_foot_down")

    @property
    def supports_massage_timer(self) -> bool:
        return self.supports_massage

    @property
    def massage_timer_options(self) -> list[int]:
        return [10, 20] if self.supports_massage else []

    @property
    def massage_timer_can_turn_off(self) -> bool:
        return False

    async def set_massage_timer(self, minutes: int) -> None:
        if minutes not in self.massage_timer_options:
            raise invalid(
                "choose_one_of", device_name=self._coordinator.name, options="10, 20 minutes"
            )
        with self.sent_state(MASSAGE_TIMER_MINUTES(minutes)):
            await self._send("massage_timer_10" if minutes == 10 else "massage_timer_20")


async def build_controller(ctx: BuildContext) -> SaatvaController:
    return SaatvaController(ctx.coordinator, ctx.variant or "")
