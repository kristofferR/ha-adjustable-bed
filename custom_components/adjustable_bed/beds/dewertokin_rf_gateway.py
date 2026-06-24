"""DewertOkin Bluetooth RF-Gateway controller."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..const import DEWERTOKIN_RF_GATEWAY_WRITE_CHAR_UUID
from .base import MotorControlSpec
from .keeson import KeesonController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class DewertOkinRfGatewayController(KeesonController):
    """Controller for DewertOkin Bluetooth RF-Gateway receivers.

    The receiver exposes the normal DewertOkin/Okin UUID service, but motor
    commands are sent to the RF-Gateway service as Keeson-style 8-byte packets.
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the DewertOkin RF-Gateway controller."""
        super().__init__(
            coordinator,
            variant="base",
            char_uuid=DEWERTOKIN_RF_GATEWAY_WRITE_CHAR_UUID,
        )
        _LOGGER.debug("DewertOkinRfGatewayController initialized")

    @property
    def supports_stop_all(self) -> bool:
        """Return True because the RF-Gateway protocol has a stop packet."""
        return True

    @property
    def motor_translation_keys(self) -> dict[str, str] | None:
        """Use standard DewertOkin motor labels instead of Keeson labels."""
        return None

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        """Return standard DewertOkin motor keys backed by RF-Gateway commands."""
        specs = [
            MotorControlSpec(
                key="back",
                translation_key="back",
                open_fn=lambda ctrl: ctrl.move_back_up(),
                close_fn=lambda ctrl: ctrl.move_back_down(),
                stop_fn=lambda ctrl: ctrl.move_back_stop(),
                position_key="back",
            ),
            MotorControlSpec(
                key="legs",
                translation_key="legs",
                open_fn=lambda ctrl: ctrl.move_legs_up(),
                close_fn=lambda ctrl: ctrl.move_legs_down(),
                stop_fn=lambda ctrl: ctrl.move_legs_stop(),
                position_key="legs",
                max_angle=45,
            ),
        ]

        if self._coordinator.motor_count >= 3:
            specs.append(
                MotorControlSpec(
                    key="head",
                    translation_key="head",
                    open_fn=lambda ctrl: ctrl.move_head_up(),
                    close_fn=lambda ctrl: ctrl.move_head_down(),
                    stop_fn=lambda ctrl: ctrl.move_head_stop(),
                )
            )

        if self._coordinator.motor_count >= 4:
            specs.append(
                MotorControlSpec(
                    key="feet",
                    translation_key="feet",
                    open_fn=lambda ctrl: ctrl.move_feet_up(),
                    close_fn=lambda ctrl: ctrl.move_feet_down(),
                    stop_fn=lambda ctrl: ctrl.move_feet_stop(),
                    max_angle=45,
                )
            )

        return tuple(specs)
