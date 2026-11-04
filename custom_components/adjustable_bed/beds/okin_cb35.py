"""DewertOkin CB35 Star (Sealy Posturematic): the ``okin_cb35`` profile.

Reverse-engineered from the Sealy Posturematic app (com.okin.sealy v1.1.1),
protocol CB.35.22.01 ("star code new protocol"). Ref #310.

Beyond the shared Okin 5A controller this keeps what profile data cannot
express, verified on a Sealy Element (2026-09):
- A preset key only arms the bed; the STOP x3 release commits the move. With the
  generic single STOP the bed sat armed for ~20 s before moving.
- A preset in flight ignores STOP entirely. Any motor key interrupts it, the
  same as pressing a button on the handset, so stop_all taps a motor key first
  while a preset may still be moving.
- Neck, hips (tilt surface), light brightness and color, separate head/foot
  massage strength, and massage status notifications.

See ``docs/beds/okin-5a.md``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from bleak.exc import BleakError

from ..profiles.okin_5a import OKIN_CB35
from .base import MotorControlSpec
from .okin_7byte import Okin7ByteController

if TYPE_CHECKING:
    from bleak.backends.characteristic import BleakGATTCharacteristic

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class OkinCB35Controller(Okin7ByteController):
    """The Okin 5A controller over the ``okin_cb35`` profile."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        super().__init__(coordinator, profile=OKIN_CB35)

    @property
    def _preset_started_at(self) -> float | None:
        """Keep the interrupt window across BLE reconnects on this physical bed."""
        return self._coordinator.okin_cb35_preset_started_at

    @_preset_started_at.setter
    def _preset_started_at(self, value: float | None) -> None:
        self._coordinator.okin_cb35_preset_started_at = value

    # ─── Presets and stop ─────────────────────────────────────────────
    # The CB35 protocol doc records the app's release as STOP sent three times
    # at 300 ms; the profile's recall and stop taps hold that timing.

    # Longer than any preset's full travel on the tested bed (~30 s).
    _PRESET_INTERRUPT_WINDOW_S = 45.0

    def _record_preset_write(self) -> None:
        """Remember a transmitted preset, including partially cancelled taps."""
        self._preset_started_at = asyncio.get_running_loop().time()

    def _record_motor_write(self) -> None:
        """A transmitted motor key supersedes the previous preset."""
        self._preset_started_at = None

    async def _preset_with_stop(
        self, command: bytes, repeat_count: int = 100, repeat_delay_ms: int = 300
    ) -> None:
        """Tap the preset key, then release it with STOP x3 to commit the move."""
        command_failed = False
        try:
            if self._coordinator.cancel_command.is_set():
                return
            await self.write_command(
                command,
                repeat_count=repeat_count,
                repeat_delay_ms=repeat_delay_ms,
                on_write=self._record_preset_write,
            )
        except BaseException:
            command_failed = True
            raise
        finally:
            try:
                await self._send_stop()
            except BleakError, ConnectionError:
                _LOGGER.debug("Failed to send preset release", exc_info=True)
                if not command_failed:
                    raise

    async def _move_with_stop(self, command: bytes) -> None:
        """Run a motor command and clear any preset it successfully interrupts."""
        try:
            pulse_count, pulse_delay = self.motor_pulse_settings()
            await self.write_command(
                command,
                repeat_count=pulse_count,
                repeat_delay_ms=pulse_delay,
                on_write=self._record_motor_write,
            )
        finally:
            try:
                await self._send_stop()
            except BleakError, ConnectionError:
                _LOGGER.debug("Failed to send STOP during cleanup", exc_info=True)

    async def stop_all(self) -> None:
        """Stop all movement.

        A preset that is still driving ignores STOP, so tap a motor key first
        while one may be in flight. Outside that window send STOP alone so an
        idle stop does not nudge the bed.
        """
        preset_started_at = self._preset_started_at
        if preset_started_at is None:
            await self._send_stop()
            return

        if asyncio.get_running_loop().time() - preset_started_at >= self._PRESET_INTERRUPT_WINDOW_S:
            self._preset_started_at = None
            await self._send_stop()
            return

        interrupt_succeeded = False
        try:
            await self.write_command(
                self.profile.frame("head_up"), repeat_count=1, cancel_event=asyncio.Event()
            )
            interrupt_succeeded = True
            self._preset_started_at = None
        finally:
            try:
                await self._send_stop()
            except BleakError, ConnectionError:
                _LOGGER.debug("Failed to send STOP after preset interrupt", exc_info=True)
                if interrupt_succeeded:
                    raise

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

    # ─── Neck motor ────────────────────────────────────────────────────

    async def move_neck_up(self) -> None:
        await self._move("neck_up")

    async def move_neck_down(self) -> None:
        await self._move("neck_down")

    async def move_neck_stop(self) -> None:
        await self._send_stop()

    # ─── Hips motor via tilt surface ───────────────────────────────────

    async def move_tilt_up(self) -> None:
        await self._move("hips_up")

    async def move_tilt_down(self) -> None:
        await self._move("hips_down")

    async def move_tilt_stop(self) -> None:
        await self._send_stop()

    # ─── Light brightness / color ─────────────────────────────────────

    async def light_brightness_up(self) -> None:
        """Increase light brightness."""
        await self._send("light_brightness_up")

    async def light_brightness_down(self) -> None:
        """Decrease light brightness."""
        await self._send("light_brightness_down")

    async def light_color_change(self) -> None:
        """Cycle light color."""
        await self._send("light_color")

    # ─── Massage: separate head/foot strength ─────────────────────────

    async def massage_head_up(self) -> None:
        """Increase head massage strength."""
        await self._send("massage_head_up")

    async def massage_head_down(self) -> None:
        """Decrease head massage strength."""
        await self._send("massage_head_down")

    async def massage_foot_up(self) -> None:
        """Increase foot massage strength."""
        await self._send("massage_foot_up")

    async def massage_foot_down(self) -> None:
        """Decrease foot massage strength."""
        await self._send("massage_foot_down")

    # ─── Notification handling ────────────────────────────────────────

    def _on_notification(self, characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
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
        client = self.client
        if client is None or not client.is_connected:
            return

        try:
            async with self._ble_lock:
                await client.start_notify(self.profile.notify_uuid, self._on_notification)
            _LOGGER.debug("Subscribed to CB35 notifications")
        except BleakError:
            _LOGGER.warning("Could not subscribe to CB35 notifications")

    async def stop_notify(self) -> None:
        """Stop listening for notifications."""
        client = self.client
        if client is not None and client.is_connected:
            try:
                async with self._ble_lock:
                    await client.stop_notify(self.profile.notify_uuid)
            except BleakError:
                pass
