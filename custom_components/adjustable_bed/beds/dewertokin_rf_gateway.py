"""DewertOkin Bluetooth RF-Gateway controller."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..const import DEWERTOKIN_RF_GATEWAY_WRITE_CHAR_UUID
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
