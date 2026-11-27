"""Atlas Lift's ordinary Cama Lift controls on one unambiguous Richmat link."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from ...card import CARD_MASSAGE, CARD_PRESET_SAVE
from ...profiles.richmat import ATLAS_LIFT, ATLAS_LIFT_INITIALIZATION, Button, RichmatProfile
from ..base import BedController
from ..entity_specs import ControllerButtonSpec, MotorControlSpec
from .fixed import FixedRichmatAppController, _Link, select_fixed_link

if TYPE_CHECKING:
    from bleak import BleakClient

    from ...coordinator import AdjustableBedCoordinator


def select_link(client: BleakClient) -> _Link:
    return select_fixed_link(client, ATLAS_LIFT, error_key="atlas_lift_gatt")


class RichmatSessionController(FixedRichmatAppController):
    """Keep the accepted profile-specific startup and timed motor controls."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        profile: RichmatProfile,
        initialization: tuple[tuple[str, int], ...],
        gatt_error_key: str,
    ) -> None:
        super().__init__(coordinator, profile, initialization, gatt_error_key=gatt_error_key)

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


class AtlasLiftController(FixedRichmatAppController):
    """Cama Lift's fixed controls over the shared held app session."""

    def __init__(
        self, coordinator: AdjustableBedCoordinator, *, profile: RichmatProfile = ATLAS_LIFT
    ) -> None:
        super().__init__(
            coordinator, profile, ATLAS_LIFT_INITIALIZATION, gatt_error_key="atlas_lift_gatt"
        )

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        # A generic motor count restored from a different app cannot add axes.
        back, legs = super().motor_control_specs[:2]
        return (
            replace(
                back,
                timed_move_fn=lambda controller, up, ms: _atlas_lift(controller)._timed_motor(
                    "head_up" if up else "head_down", ms
                ),
            ),
            replace(
                legs,
                timed_move_fn=lambda controller, up, ms: _atlas_lift(controller)._timed_motor(
                    "feet_up" if up else "feet_down", ms
                ),
            ),
        )

    async def _timed_motor(self, control: Button, duration_ms: int) -> None:
        await self._move_with_stop(self._code(control), duration_ms=duration_ms)

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
