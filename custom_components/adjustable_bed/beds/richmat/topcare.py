"""TOP CARE's fixed motor screen over its artifact-selected Richmat encodings."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from ...errors import invalid
from ...profiles.richmat import TOPCARE, TOPCARE_INITIALIZATION, Button
from ..base import BedController
from ..entity_specs import ControllerMotorHoldSpec, MotorControlSpec, PositionNumberSpec
from .fixed import FixedRichmatAppController, select_fixed_link

if TYPE_CHECKING:
    from bleak import BleakClient

    from ...coordinator import AdjustableBedCoordinator
    from .fixed import _Link

# These are controls, including combined controls, not physical motor counts.
CONTROLS: tuple[tuple[str, Button, Button], ...] = (
    ("back", "head_up", "head_down"),
    ("legs", "feet_up", "feet_down"),
    ("head_feet", "head_feet_up", "head_feet_down"),
    ("lumbar_pillow", "lumbar_pillow_up", "lumbar_pillow_down"),
    ("tilt", "tilt_up", "tilt_down"),
)


def select_link(client: BleakClient) -> _Link:
    return select_fixed_link(client, TOPCARE, error_key="topcare_gatt", invert_encoding=True)


async def _move(controller: BedController, *, control: str) -> None:
    await controller.hold_control(control, 1000)


class TopcareController(FixedRichmatAppController):
    """Native controls with session-bound writes and renewable held movement."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(
            coordinator,
            TOPCARE,
            TOPCARE_INITIALIZATION,
            gatt_error_key="topcare_gatt",
            invert_encoding=True,
            immediate_timed_pulse=False,
        )

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        return ()

    @property
    def supports_preset_flat(self) -> bool:
        return False

    @property
    def requires_linked_live_readiness(self) -> bool:
        return True

    async def async_validate_linked_readiness(self) -> None:
        self._current_link()

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        return tuple(
            MotorControlSpec(
                key,
                key,
                partial(_move, control=up),
                partial(_move, control=down),
                lambda controller: controller.stop_all(),
                hold=ControllerMotorHoldSpec(up, down, stop_scope="side", press_is_native=True),
            )
            for key, up, down in CONTROLS
        )

    @property
    def held_control_options(self) -> tuple[str, ...]:
        return tuple(self.profile.codes or ())

    def validate_hold_control(self, control: str, duration_ms: int) -> None:
        if (
            control not in self.held_control_options
            or type(duration_ms) is not int
            or not 1 <= duration_ms <= 60000
        ):
            raise invalid("topcare_control")

    async def hold_control(self, control: str, duration_ms: int) -> None:
        self.validate_hold_control(control, duration_ms)
        # Resolve through typed keys, without treating a combined control as an axis.
        assert self.profile.codes is not None
        code = next(code for button, code in self.profile.codes.items() if button == control)
        await self._move_with_stop(code, duration_ms=duration_ms)
