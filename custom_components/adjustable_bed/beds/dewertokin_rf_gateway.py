"""DewertOkin Bluetooth RF-Gateway controller."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from .okin_handle import OkinHandleController
from .okin_uuid import OkinUuidController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class _DewertOkinRfGatewayFrame:
    """RF-Gateway frame helper for Okin 6-byte command controllers.

    FurniMove identifies RF-Gateway devices by the gateway name characteristic
    but still writes commands to the normal Okin write characteristic. The only
    protocol difference is the 8-byte RF frame around the same Okin payload.
    """

    _RF_GATEWAY_HEADER = bytes((0xE5, 0xFE, 0x16))

    @classmethod
    def _wrap_rf_gateway_frame(cls, command: bytes) -> bytes:
        """Wrap a 6-byte Okin command as an RF-Gateway frame."""
        if len(command) != 6 or command[:2] != b"\x04\x02":
            raise ValueError("DewertOkin RF-Gateway expects a 6-byte Okin command")

        frame = cls._RF_GATEWAY_HEADER + command[2:]
        checksum = (~sum(frame)) & 0xFF
        return frame + bytes((checksum,))


class DewertOkinRfGatewayController(_DewertOkinRfGatewayFrame, OkinHandleController):
    """Controller for DewertOkin Bluetooth RF-Gateway receivers."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the DewertOkin RF-Gateway controller."""
        super().__init__(coordinator)
        _LOGGER.debug("DewertOkinRfGatewayController initialized")

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write an Okin command using DewertOkin RF-Gateway framing."""
        rf_command = self._wrap_rf_gateway_frame(command)
        await super().write_command(
            rf_command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
        )


class DewertOkinUuidRfGatewayController(_DewertOkinRfGatewayFrame, OkinUuidController):
    """RF-Gateway wrapper for Okin UUID remotes with configured variants."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        variant: str,
    ) -> None:
        """Initialize the DewertOkin RF-Gateway controller for an Okin UUID remote."""
        super().__init__(coordinator, variant=variant)
        _LOGGER.debug(
            "DewertOkinUuidRfGatewayController initialized with variant %s",
            self._variant,
        )

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write an Okin UUID command using DewertOkin RF-Gateway framing."""
        rf_command = self._wrap_rf_gateway_frame(command)
        await super().write_command(
            rf_command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
        )
