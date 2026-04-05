"""DewertOkin CB35 Star protocol bed controller implementation.

Reverse-engineered from the Sealy Posturematic app (com.okin.sealy v1.1.1).
Protocol version: CB.35.22.01 ("star code new protocol")

Known brands using this protocol:
- Sealy Posturematic (Element, Ascent, Apex)

BLE Name: Star*  (e.g., "Star352201011800")
Service: Nordic UART (6e400001-b5a3-f393-e0a9-e50e24dcca9e)
Write:   TX characteristic (6e400002), write-without-response
Notify:  RX characteristic (6e400003)

Uses the same 7-byte command frame as Okin Nordic:
    5A 01 03 10 30 [CMD] A5

Identical motor/preset/light/massage command bytes as Okin Nordic, but:
- Init sequence is only the wake command (5A 0B 00 A5), no Mattress Firm handshake
- Write-without-response required (Nordic uses write-with-response)
- Additional motors: neck (0x0A/0x0B), hips (0x08/0x09), head+foot simultaneous (0x0C/0x0D)
- Additional presets: TV/PC, Read, Inverse, Work, Incline, Extension
- Light brightness and color control
- Separate head/foot massage strength
- Massage status feedback via notifications

Protocol source: disassembly/output/com.okin.sealy/extracted/assets/flutter_assets/assets/protocol/35_22_01.json
Ref: https://github.com/kristofferR/ha-adjustable-bed/issues/310
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ..const import NORDIC_UART_WRITE_CHAR_UUID
from .base import MotorControlSpec
from .okin_7byte import Okin7ByteConfig, Okin7ByteController, _cmd

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


# CB35 configuration: same command bytes as Okin Nordic but without the
# Mattress Firm init handshake (09 05 0A 23 05 00 00).
# Only the wake command (5A 0B 00 A5) is needed.
OKIN_CB35_CONFIG = Okin7ByteConfig(
    char_uuid=NORDIC_UART_WRITE_CHAR_UUID,
    lumbar_up_byte=0x06,
    lounge_byte=0x17,
    tv_byte=0x11,
    memory_1_byte=0x1A,
    memory_2_byte=0x1B,
    init_commands=(
        bytes.fromhex("5A0B00A5"),  # Wake command only (no Mattress Firm handshake)
    ),
    has_incline=True,
    incline_byte=0x18,
    has_light_cycle=True,
    has_massage_intensity=True,
    massage_up_byte=0x60,
    massage_down_byte=0x61,
    extra_massage_modes=(0x52, 0x53, 0x54),
    massage_stop_byte=0x6F,
    lights_off_repeat=3,
    supports_tv=True,
)


class OkinCB35Controller(Okin7ByteController):
    """Controller for DewertOkin CB35 Star beds (Sealy Posturematic).

    Extends the Okin 7-byte protocol with:
    - Write-without-response (required by CB35 firmware)
    - Neck and hips motor control
    - Head+foot simultaneous movement
    - Light brightness and color control
    - Separate head/foot massage strength
    - Massage status feedback via Nordic UART notifications
    """

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the CB35 controller."""
        super().__init__(coordinator, config=OKIN_CB35_CONFIG)

    # ─── Write override: CB35 requires write-without-response ─────────

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a command using write-without-response."""
        if self.client is None or not self.client.is_connected:
            _LOGGER.error("Cannot write command: BLE client not connected")
            raise ConnectionError("Not connected to bed")

        effective_cancel = cancel_event or self._coordinator.cancel_command

        # Send init/wake on first command
        if not self._initialized:
            if effective_cancel is not None and effective_cancel.is_set():
                return
            _LOGGER.debug("Sending CB35 wake command before first command")
            try:
                for init_cmd in self._config.init_commands:
                    async with self._ble_lock:
                        await self.client.write_gatt_char(
                            self._config.char_uuid, init_cmd, response=False
                        )
                    await asyncio.sleep(0.1)
                self._initialized = True
            except BleakError:
                _LOGGER.exception("Failed to send CB35 wake sequence")
                raise

        await self._write_gatt_with_retry(
            self._config.char_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=False,
        )

    # ─── Extra capability properties ──────────────────────────────────

    @property
    def has_neck_support(self) -> bool:
        return True

    @property
    def has_tilt_support(self) -> bool:
        """Hips motor exposed via the tilt surface."""
        return True

    @property
    def supports_massage(self) -> bool:
        return True

    @property
    def motor_control_specs(self) -> tuple[MotorControlSpec, ...]:
        """Expose CB35 motors: head, feet, lumbar, neck, hips."""
        return (
            MotorControlSpec(
                key="head",
                translation_key="head",
                open_fn=lambda ctrl: ctrl.move_head_up(),
                close_fn=lambda ctrl: ctrl.move_head_down(),
                stop_fn=lambda ctrl: ctrl.move_head_stop(),
            ),
            MotorControlSpec(
                key="feet",
                translation_key="feet",
                open_fn=lambda ctrl: ctrl.move_feet_up(),
                close_fn=lambda ctrl: ctrl.move_feet_down(),
                stop_fn=lambda ctrl: ctrl.move_feet_stop(),
                max_angle=45,
            ),
            MotorControlSpec(
                key="lumbar",
                translation_key="lumbar",
                open_fn=lambda ctrl: ctrl.move_lumbar_up(),
                close_fn=lambda ctrl: ctrl.move_lumbar_down(),
                stop_fn=lambda ctrl: ctrl.move_lumbar_stop(),
            ),
            MotorControlSpec(
                key="neck",
                translation_key="neck",
                open_fn=lambda ctrl: ctrl.move_neck_up(),
                close_fn=lambda ctrl: ctrl.move_neck_down(),
                stop_fn=lambda ctrl: ctrl.move_neck_stop(),
                max_angle=30,
            ),
            MotorControlSpec(
                key="tilt",
                translation_key="head_end_tilt",
                open_fn=lambda ctrl: ctrl.move_tilt_up(),
                close_fn=lambda ctrl: ctrl.move_tilt_down(),
                stop_fn=lambda ctrl: ctrl.move_tilt_stop(),
                max_angle=45,
            ),
        )

    @property
    def stale_motor_entity_keys(self) -> frozenset[str]:
        """Remove standard back/legs entities replaced by motor_control_specs."""
        return frozenset({"back", "legs"})

    # ─── Neck motor (0x0A/0x0B) ───────────────────────────────────────

    async def move_neck_up(self) -> None:
        await self._move_with_stop(_cmd(0x0A))

    async def move_neck_down(self) -> None:
        await self._move_with_stop(_cmd(0x0B))

    async def move_neck_stop(self) -> None:
        await self._send_stop()

    # ─── Hips motor via tilt surface (0x08/0x09) ──────────────────────

    async def move_tilt_up(self) -> None:
        await self._move_with_stop(_cmd(0x08))

    async def move_tilt_down(self) -> None:
        await self._move_with_stop(_cmd(0x09))

    async def move_tilt_stop(self) -> None:
        await self._send_stop()

    # ─── Light brightness / color ─────────────────────────────────────

    async def light_brightness_up(self) -> None:
        """Increase light brightness."""
        await self.write_command(_cmd(0x80))

    async def light_brightness_down(self) -> None:
        """Decrease light brightness."""
        await self.write_command(_cmd(0x81))

    async def light_color_change(self) -> None:
        """Cycle light color."""
        await self.write_command(_cmd(0x70))

    # ─── Massage: override inherited intensity (parent uses 0x40 frame) ─

    async def massage_intensity_up(self) -> None:
        """Increase overall massage strength (CB35 uses 0x30 frame, not 0x40)."""
        await self.write_command(_cmd(0x60))

    async def massage_intensity_down(self) -> None:
        """Decrease overall massage strength (CB35 uses 0x30 frame, not 0x40)."""
        await self.write_command(_cmd(0x61))

    # ─── Massage: separate head/foot strength ─────────────────────────

    async def massage_head_up(self) -> None:
        """Increase head massage strength."""
        await self.write_command(_cmd(0x60))

    async def massage_head_down(self) -> None:
        """Decrease head massage strength."""
        await self.write_command(_cmd(0x61))

    async def massage_foot_up(self) -> None:
        """Increase foot massage strength."""
        await self.write_command(_cmd(0x62))

    async def massage_foot_down(self) -> None:
        """Decrease foot massage strength."""
        await self.write_command(_cmd(0x63))

    # ─── Notification handling ────────────────────────────────────────

    def _on_notification(
        self, characteristic: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Handle BLE notification data from the bed."""
        raw = bytes(data)
        self.forward_raw_notification(characteristic.uuid, raw)

        if len(raw) < 2:
            _LOGGER.debug("CB35 notification too short (%d bytes): %s", len(raw), raw.hex())
            return

        # Massage status: header A5 0B
        if raw[0] == 0xA5 and raw[1] == 0x0B and len(raw) >= 8:
            _LOGGER.debug("CB35 massage status: %s", raw.hex())

    async def start_notify(self, callback=None) -> None:  # noqa: ARG002
        """Start listening for notifications via Nordic UART RX."""
        from ..const import NORDIC_UART_READ_CHAR_UUID

        client = self.client
        if client is None or not client.is_connected:
            return

        try:
            await client.start_notify(NORDIC_UART_READ_CHAR_UUID, self._on_notification)
            _LOGGER.debug("Subscribed to CB35 notifications")
        except BleakError:
            _LOGGER.warning("Could not subscribe to CB35 notifications")

    async def stop_notify(self) -> None:
        """Stop listening for notifications."""
        from ..const import NORDIC_UART_READ_CHAR_UUID

        client = self.client
        if client is not None and client.is_connected:
            try:
                await client.stop_notify(NORDIC_UART_READ_CHAR_UUID)
            except BleakError:
                pass
