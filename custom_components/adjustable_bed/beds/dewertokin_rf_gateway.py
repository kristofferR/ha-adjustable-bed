"""DewertOkin Bluetooth RF-Gateway controllers.

FurniMove identifies RF-Gateway devices by the gateway name characteristic but
still writes commands to the normal Okin write characteristic. The only
difference is the 8-byte envelope (``codec.gateway_frame``) around the same
32-bit command word.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ..codec import okin_nframe as codec
from ..const import (
    DEWERTOKIN_RF_GATEWAY_DEVICE_NAME_CHAR_UUID,
    DEWERTOKIN_RF_GATEWAY_MODEL,
    DEWERTOKIN_RF_GATEWAY_SERVICE_UUID,
)
from .builder import BuildContext
from .okin_handle import OkinHandleController
from .okin_nframe import OkinNFrameController
from .okin_uuid import OkinUuidController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class _DewertOkinRfGatewayFrame(OkinNFrameController):
    """Re-frame every plain 32-bit frame as an RF-Gateway envelope."""

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write an Okin command using DewertOkin RF-Gateway framing."""
        await super().write_command(
            codec.gateway_frame(codec.word_of(command)),
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
        )


class DewertOkinRfGatewayController(_DewertOkinRfGatewayFrame, OkinHandleController):
    """Controller for DewertOkin Bluetooth RF-Gateway receivers."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the DewertOkin RF-Gateway controller."""
        super().__init__(coordinator)
        _LOGGER.debug("DewertOkinRfGatewayController initialized")


class DewertOkinUuidRfGatewayController(_DewertOkinRfGatewayFrame, OkinUuidController):
    """RF-Gateway wrapper for Okin UUID remotes with configured variants."""

    def __init__(self, coordinator: AdjustableBedCoordinator, variant: str) -> None:
        """Initialize the DewertOkin RF-Gateway controller for an Okin UUID remote."""
        super().__init__(coordinator, variant=variant)
        _LOGGER.debug(
            "DewertOkinUuidRfGatewayController initialized with variant %s", self._variant
        )


def is_rf_gateway(ctx: BuildContext) -> bool:
    """Return True when a DewertOkin/Okin entry is the RF-Gateway command variant."""
    if ctx.ble_model is not None and ctx.ble_model.strip().lower() == DEWERTOKIN_RF_GATEWAY_MODEL.lower():
        return True
    return ctx.has_characteristic(
        DEWERTOKIN_RF_GATEWAY_SERVICE_UUID, DEWERTOKIN_RF_GATEWAY_DEVICE_NAME_CHAR_UUID
    )
