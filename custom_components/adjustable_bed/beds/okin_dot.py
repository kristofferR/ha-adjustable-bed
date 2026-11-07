"""DewertOkin "DOT PROTOCOL" bed controller implementation.

Protocol reverse-engineered from the FurniMove app (com.okin.okinsmartcomfort):

- The handset remote codes (RF1058/RF34/RF6707: 90167, 91983, 93558, 97450,
  97544, 98035) resolve through the same FurniMove backend as the Okimat
  remotes, so the per-remote keycode table ``OKIN_UUID_REMOTES`` is shared
  (entries flagged ``dot=True``). 90167, 91983 and 93558 are derived from the
  pinned FurniMove catalog; new setups of those three use the FurniMove app
  profile, and this controller keeps existing entries working.
- The receiver box exposes the Nordic UART service instead of the Okin
  62741523 service. FurniMove flags a connection as DOT when it finds the
  Nordic UART write characteristic 6E400002 (named ``CB24_WRITE_CHARACTERISTIC``
  in the app). The earlier analysis this controller came from also recorded an
  ASCII ``affirm`` write there; the accepted 2.2.0 audit has no such write, and
  it stays here only so released entries keep their behavior.
- Commands are 40-bit Okin N-frames ``[0x05, 0x02, <keycode BE>, 0x00]``
  (``HexValueConverter.toByteArray`` with ``isDOTProtocol=true``) instead of
  the standard Okin 6-byte ``[0x04, 0x02, <keycode BE>]``. Memory keys are
  tap-to-recall, hold-to-save, so the ``OKIN_DOT`` profile recalls them with
  one press and a STOP: streaming the Okimat recall would overwrite them.
- Held buttons are re-sent ~every 100ms; release sends keycode 0
  (``DisobeyStandbyTime``), which is the same stop the base controller sends.

Unlike the Okimat boxes, DOT boxes do not require BLE pairing and expose no
known position-feedback characteristic.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ..codec import okin_nframe as codec
from ..const import NORDIC_UART_WRITE_CHAR_UUID, VARIANT_AUTO
from ..profiles.okin_nframe import OKIN_DOT
from .builder import BuildContext
from .okin_uuid.controller import OKIN_UUID_REMOTES, OkinUuidController
from .okin_uuid.remotes import DEFAULT_OKIN_DOT_REMOTE

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

# FurniMove writes this ASCII marker to the write characteristic as soon as it
# discovers a DOT box; mirror it once per connection before the first command.
_AFFIRM_HANDSHAKE = b"affirm"


class OkinDotController(OkinUuidController):
    """Controller for DewertOkin DOT PROTOCOL boxes (RF1058/RF34/RF6707).

    Reuses the Okin UUID per-remote keycode table and command flows; only the
    transport differs: Nordic UART, 7-byte ``05 02`` frames, an ``affirm``
    handshake, and no pairing or position feedback.
    """

    _write_with_response = False
    _route_profile = OKIN_DOT

    def __init__(self, coordinator: AdjustableBedCoordinator, variant: str = VARIANT_AUTO) -> None:
        """Initialize the DOT controller with a DOT remote variant.

        Only ``dot=True`` remote configs are accepted: DOT frames must never
        carry standard Okimat keycodes (Okimat Flat ``0x100000AA`` and the
        memory values mean different things in the DOT layout). A rescued
        Okimat entry whose saved variant is a standard code falls back to the
        default DOT remote — the motor, flat, and light keycodes are identical
        across all DOT codes, so movement stays safe until the user picks
        their printed code.
        """
        remote = OKIN_UUID_REMOTES.get(variant)
        if remote is None or not remote.dot:
            if remote is not None and variant != VARIANT_AUTO:
                _LOGGER.warning(
                    "Remote %s is not a DOT PROTOCOL code; using default DOT "
                    "remote %s — select your printed DOT remote code in the "
                    "options for memory/massage support",
                    variant,
                    DEFAULT_OKIN_DOT_REMOTE,
                )
            variant = DEFAULT_OKIN_DOT_REMOTE
        super().__init__(coordinator, variant=variant)
        self._affirmed_client: object | None = None

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the Nordic UART write characteristic used by DOT boxes."""
        return NORDIC_UART_WRITE_CHAR_UUID

    def _build_command(self, command_value: int) -> bytes:
        """Build a DOT frame: [0x05, 0x02, <4-byte keycode big-endian>, 0x00]."""
        return codec.frame40(command_value)

    async def _ensure_affirmed(self) -> None:
        """Send the FurniMove "affirm" handshake once per connection."""
        client = self.client
        if client is None or client is self._affirmed_client:
            return
        # Mark first so a failing handshake doesn't retry on every command;
        # a reconnect produces a new client object and a fresh attempt.
        self._affirmed_client = client
        self._record_command_trace(NORDIC_UART_WRITE_CHAR_UUID, _AFFIRM_HANDSHAKE, response=False)
        try:
            async with self._ble_lock:
                await client.write_gatt_char(
                    NORDIC_UART_WRITE_CHAR_UUID, _AFFIRM_HANDSHAKE, response=False
                )
            _LOGGER.debug("Sent DOT affirm handshake to %s", self._coordinator.address)
        except BleakError:
            _LOGGER.debug("DOT affirm handshake failed", exc_info=True)

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a DOT frame, affirming the connection first."""
        await self._ensure_affirmed()
        await super().write_command(
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
        )

    # DOT boxes expose no known position-feedback characteristic; the Okimat
    # FFE4 notify/read paths do not exist on them.
    async def start_notify(
        self, callback: Callable[[str, float], None] | None = None
    ) -> None:
        """Position notifications are not available on DOT boxes."""
        self._notify_callback = callback
        _LOGGER.debug("DOT boxes do not support position notifications")

    async def stop_notify(self) -> None:
        """Nothing to stop; notifications are never started."""

    async def read_positions(self, motor_count: int = 2) -> None:  # noqa: ARG002
        """Position reads are not available on DOT boxes."""


async def build_controller(ctx: BuildContext) -> OkinDotController:
    """Build the controller for the configured remote variant."""
    variant = ctx.variant or VARIANT_AUTO
    _LOGGER.debug("Using Okin DOT variant: %s", variant)
    return OkinDotController(ctx.coordinator, variant=variant)
