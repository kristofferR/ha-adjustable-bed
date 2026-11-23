"""Q-Plus Adjustable Remote direct-BLE app profile (com.sbi.costco).

The P1 layouts (H, M1, M2, M3) report head and foot positions as pulse counts,
converted to degrees with the app's lookup tables. MX is the app's P2 remote:
its status frames were never read for positions, so it reports none.
"""

from __future__ import annotations

import bisect
from dataclasses import replace
from typing import TYPE_CHECKING

from ..const import (
    CONF_PRODUCT_TYPE,
    QPLUS_FOOT_MAX_ANGLE,
    QPLUS_HEAD_MAX_ANGLE,
    QPLUS_VARIANT_BOTH,
    QPLUS_VARIANTS,
)
from ..profiles.keeson import app_profile
from .builder import BuildContext
from .entity_specs import (
    POSITION_UNIT_DEGREES,
    MotorControlSpec,
    PositionNumberSpec,
    build_position_number_spec,
)
from .keeson.layout_app import AppController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

# Position feedback lookup tables from the APK: pulse counts by degree (index = degrees).
HEAD_PULSE_TABLE: list[int] = [
    0, 327, 577, 855, 1148, 1676, 2083, 2401, 2711, 3020, 3402, 3679, 4019, 4529,
    4864, 5262, 5633, 6024, 6453, 6826, 7239, 7611, 8015, 8423, 8862, 9240, 9632,
    10029, 10404, 10840, 11245, 11640, 11976, 12351, 12752, 13106, 13511, 13819,
    14169, 14518, 14901, 15217, 15556, 15856, 16177, 16530, 16788, 17118, 17389,
    17700, 18000, 18268, 18481, 18767, 19035, 19260, 19487, 19757, 19970, 20164, 20413,
]  # 61 values for 0-60 degrees

FOOT_PULSE_TABLE: list[int] = [
    0, 570, 784, 968, 1150, 1372, 1653, 1837, 2062, 2283, 2494, 2755, 3015, 3290,
    3578, 3819, 4039, 4261, 4544, 4895, 5170, 5461, 5723, 6020, 6334, 6631, 6922,
    7243, 7546, 7810, 8174, 8546, 8718,
]  # 33 values for 0-32 degrees

# The 16-byte frame that carries the massage timer's seconds where the others
# carry the head pulse count.
_TIMER_PREFIX = b"\xa5\x0b\x0d"


def pulse_to_angle(pulse: int, table: list[int]) -> int:
    """Convert a pulse count to degrees (0-60 for head, 0-32 for foot)."""
    # Values of 32768 and above are inverted.
    if pulse >= 32768:
        pulse = 65535 - pulse
    return min(bisect.bisect_left(table, pulse), len(table) - 1)


class QPlusAppController(AppController):
    """Explicit Q-Plus Adjustable Remote app profile; physical effects remain unverified."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        layout: str | None = None,
        side: str = QPLUS_VARIANT_BOTH,
    ) -> None:
        super().__init__(coordinator, app_profile("qplus_app", layout), side=side)

    @property
    def supports_position_feedback(self) -> bool:
        # Only the P1 layouts were ever read for positions; MX (P2) reports none.
        return not self._mx

    @property
    def position_number_specs(self) -> tuple[PositionNumberSpec, ...]:
        """Return the head and foot angles the notifications report, as back and legs."""
        if not self.supports_position_feedback:
            return ()
        return (
            build_position_number_spec(
                "back", max_value=QPLUS_HEAD_MAX_ANGLE, unit=POSITION_UNIT_DEGREES
            ),
            build_position_number_spec(
                "legs", max_value=QPLUS_FOOT_MAX_ANGLE, unit=POSITION_UNIT_DEGREES
            ),
        )

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        # The covers travel as far as the pulse tables reach.
        limits = self.motor_max_angles
        return tuple(
            replace(spec, max_angle=limits.get(spec.key, spec.max_angle))
            for spec in super().motor_control_specs
        )

    def _parse_notification(self, data: bytes | None) -> None:
        """Read the head and foot pulse counts (bytes 3-4 and 5-6, little-endian)."""
        super()._parse_notification(data)
        if (
            not data
            or len(data) < 7
            or not self.supports_position_feedback
            or (len(data) == 16 and data[:3] == _TIMER_PREFIX)
        ):
            return
        head = pulse_to_angle(int.from_bytes(data[3:5], "little"), HEAD_PULSE_TABLE)
        foot = pulse_to_angle(int.from_bytes(data[5:7], "little"), FOOT_PULSE_TABLE)
        if self._notify_callback is not None:
            self._notify_callback("back", float(head))
            self._notify_callback("legs", float(foot))


async def build_controller(ctx: BuildContext) -> QPlusAppController:
    """Build the controller for the stored layout and selected side."""
    return QPlusAppController(
        ctx.coordinator,
        layout=ctx.data.get(CONF_PRODUCT_TYPE),
        side=ctx.variant if ctx.variant in QPLUS_VARIANTS else QPLUS_VARIANT_BOTH,
    )
