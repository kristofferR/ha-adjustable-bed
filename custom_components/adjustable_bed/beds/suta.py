"""SUTA Smart Home bed controller implementation.

Protocol reverse-engineered from com.shuta.smart_home.

Bed-frame controllers use an ASCII AT command protocol over BLE:
- Service UUID: 0000fff0-0000-1000-8000-00805f9b34fb
- Command format: b"AT+...\\r\\n" (UTF-8, CRLF-terminated)
- No checksum

Characteristic UUIDs are discovered dynamically based on GATT properties.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

from bleak.exc import BleakError

from ..const import (
    SUTA_DEFAULT_NOTIFY_CHAR_UUID,
    SUTA_DEFAULT_WRITE_CHAR_UUID,
    SUTA_SERVICE_UUID,
)
from .base import BedController

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)


class SutaCommands:
    """SUTA AT command strings."""

    # Motor control
    HEAD_UP = "AT+CTRL=BOTH HEAD UP"
    HEAD_DOWN = "AT+CTRL=BOTH HEAD DOWN"
    BACK_UP = "AT+CTRL=BOTH BACK UP"
    BACK_DOWN = "AT+CTRL=BOTH BACK DOWN"
    FOOT_UP = "AT+CTRL=BOTH FOOT UP"
    FOOT_DOWN = "AT+CTRL=BOTH FOOT DOWN"
    TILT_LUMBAR_UP = "AT+CTRL=BOTH T/L UP"
    TILT_LUMBAR_DOWN = "AT+CTRL=BOTH T/L DOWN"
    STOP_ALL = "AT+CTRL=BOTH STOP"

    # Massage (timer, duty cycle, level per zone)
    # Timer: "AT+MASS=BOTH <ZONE> T<param>" e.g. "AT+MASS=BOTH HEAD T00M"
    MASSAGE_HEAD_TIMER = "AT+MASS=BOTH HEAD T"
    MASSAGE_FOOT_TIMER = "AT+MASS=BOTH FOOT T"
    # Duty cycle: values 00 (off), 20, 33, 50
    MASSAGE_HEAD_DT = "AT+MASS=BOTH HEAD DT"
    MASSAGE_FOOT_DT = "AT+MASS=BOTH FOOT DT"
    # Level: values 00 (off), 10, 20, 30
    MASSAGE_HEAD_LV = "AT+MASS=BOTH HEAD LV"
    MASSAGE_FOOT_LV = "AT+MASS=BOTH FOOT LV"

    # Presets (recall)
    PRESET_FLAT = "AT+MODE=BOTH FLAT"
    PRESET_ZERO_G = "AT+MODE=BOTH ZEROG"
    PRESET_ANTI_SNORE = "AT+MODE=BOTH SNORE"
    PRESET_TV = "AT+MODE=BOTH TV"
    PRESET_MEMORY_1 = "AT+MODE=BOTH M1"
    PRESET_MEMORY_2 = "AT+MODE=BOTH M2"
    PRESET_MEMORY_3 = "AT+MODE=BOTH M3"
    PRESET_MEMORY_4 = "AT+MODE=BOTH M4"

    # Presets (save)
    PROGRAM_MEMORY_1 = "AT+SETMODE=BOTH M1"
    PROGRAM_MEMORY_2 = "AT+SETMODE=BOTH M2"
    PROGRAM_MEMORY_3 = "AT+SETMODE=BOTH M3"
    PROGRAM_MEMORY_4 = "AT+SETMODE=BOTH M4"

    # Lights
    LIGHT_ON = "AT+ENABLE=LIGHT"
    LIGHT_OFF = "AT+DISABLE=LIGHT"

    # Sync (split king)
    SYNC_SLAVE_ON = "AT+SINSLAVE=ON"
    SYNC_SLAVE_OFF = "AT+SINSLAVE=OFF"


class SutaController(BedController):
    """Controller for SUTA Smart Home bed-frame devices."""

    def __init__(self, coordinator: AdjustableBedCoordinator) -> None:
        """Initialize the SUTA controller."""
        super().__init__(coordinator)
        self._write_char_uuid = SUTA_DEFAULT_WRITE_CHAR_UUID
        self._notify_char_uuid = SUTA_DEFAULT_NOTIFY_CHAR_UUID
        self._write_with_response = False
        self._chars_initialized = False
        self._notify_started = False
        self._light_state = False

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the command characteristic UUID."""
        return self._write_char_uuid

    @property
    def requires_notification_channel(self) -> bool:
        """Return True - SUTA firmware needs an active notify subscription.

        The SUTA app enables notifications on the FFF0 notify characteristic
        (FFF1) immediately after connecting, before it sends any command. On
        some transparent-UART controllers (e.g. the WLT8016 module in the
        Dreams Sleepmotion / SUTA-B202B, issue #345) the bed connects and beeps
        but silently ignores motor commands until that subscription is active,
        so the coordinator must call start_notify() even when angle sensing is
        disabled.
        """
        return True

    # Capability properties
    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
        return True

    @property
    def supports_preset_tv(self) -> bool:
        return True

    @property
    def supports_memory_presets(self) -> bool:
        return True

    @property
    def memory_slot_count(self) -> int:
        return 4

    @property
    def supports_memory_programming(self) -> bool:
        return True

    @property
    def supports_lights(self) -> bool:
        return True

    @property
    def supports_discrete_light_control(self) -> bool:
        return True

    @property
    def has_lumbar_support(self) -> bool:
        return True

    @property
    def supports_synchro(self) -> bool:
        """Return True - SUTA beds support split-king sync slave mode."""
        return True

    def _build_command(self, command: str) -> bytes:
        """Build a CRLF-terminated AT command packet."""
        return f"{command}\r\n".encode()

    def _refresh_characteristics(self) -> None:
        """Resolve write and notify characteristics from discovered services.

        SUTA devices expose their command and notify characteristics
        dynamically under SUTA_SERVICE_UUID, so we mirror the app: pick the
        first char with WRITE/WRITE_NO_RESPONSE as the command channel (FFF2)
        and the first char with NOTIFY/INDICATE as the notify channel (FFF1),
        instead of matching fixed UUIDs.
        """
        if self._chars_initialized:
            return

        client = self.client
        if client is None or client.services is None:
            return

        service = client.services.get_service(SUTA_SERVICE_UUID)
        if service is None:
            _LOGGER.debug(
                "SUTA service %s not found, using fallback write=%s notify=%s",
                SUTA_SERVICE_UUID,
                self._write_char_uuid,
                self._notify_char_uuid,
            )
            self._chars_initialized = True
            return

        write_found = False
        notify_found = False
        for char in service.characteristics:
            props = {prop.lower() for prop in char.properties}
            if not write_found and ("write" in props or "write-without-response" in props):
                self._write_char_uuid = str(char.uuid)
                # Prefer write-with-response when available for acknowledgements;
                # otherwise fall back to write-without-response.
                self._write_with_response = "write" in props
                write_found = True
            if not notify_found and ("notify" in props or "indicate" in props):
                self._notify_char_uuid = str(char.uuid)
                notify_found = True

        if not write_found:
            _LOGGER.debug(
                "No writable characteristic found in SUTA service %s, using fallback %s",
                SUTA_SERVICE_UUID,
                self._write_char_uuid,
            )
        self._chars_initialized = True
        _LOGGER.debug(
            "SUTA characteristics resolved: write=%s (response=%s) notify=%s",
            self._write_char_uuid,
            self._write_with_response,
            self._notify_char_uuid,
        )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Subscribe to the FFF0 notify characteristic (FFF1).

        SUTA firmware requires an active notify subscription before it accepts
        commands (see requires_notification_channel). The position callback is
        unused - SUTA reports no motor angle - but the subscription itself is
        what unblocks command handling on the WLT8016 and similar modules.
        """
        self._notify_callback = callback

        client = self.client
        if client is None or not client.is_connected:
            _LOGGER.warning("Cannot start SUTA notifications: not connected")
            return

        self._refresh_characteristics()
        if self._notify_started:
            return

        try:
            async with self._ble_lock:
                await client.start_notify(self._notify_char_uuid, self._handle_notification)
            self._notify_started = True
            _LOGGER.debug(
                "Started SUTA notifications on %s for %s",
                self._notify_char_uuid,
                self._coordinator.address,
            )
        except BleakError as err:
            _LOGGER.warning("Failed to start SUTA notifications: %s", err)
            self.log_discovered_services(level=logging.INFO)

    async def stop_notify(self) -> None:
        """Unsubscribe from the FFF0 notify characteristic."""
        self._notify_callback = None
        client = self.client
        if client is not None and client.is_connected and self._notify_started:
            with contextlib.suppress(BleakError):
                async with self._ble_lock:
                    await client.stop_notify(self._notify_char_uuid)
        self._notify_started = False

    def _handle_notification(self, _sender: Any, data: bytearray) -> None:
        """Forward raw SUTA notifications for diagnostics capture.

        SUTA exposes no motor-position feedback, so there is nothing to parse
        into an angle - the notification channel exists only to unblock command
        handling and to surface +OK/+ERR responses in diagnostic captures.
        """
        self.forward_raw_notification(self._notify_char_uuid, bytes(data))

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a SUTA command packet."""
        self._refresh_characteristics()
        await self._write_gatt_with_retry(
            self._write_char_uuid,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=self._write_with_response,
        )

    async def _send_stop(self) -> None:
        """Send stop command with a fresh cancel event."""
        await self.write_command(
            self._build_command(SutaCommands.STOP_ALL),
            repeat_count=2,
            repeat_delay_ms=100,
            cancel_event=asyncio.Event(),
        )

    # Motor control methods
    async def move_head_up(self) -> None:
        """Move head/upper section up."""
        await self._move_with_stop(self._build_command(SutaCommands.HEAD_UP))

    async def move_head_down(self) -> None:
        """Move head/upper section down."""
        await self._move_with_stop(self._build_command(SutaCommands.HEAD_DOWN))

    async def move_head_stop(self) -> None:
        """Stop head/back motor movement."""
        await self._send_stop()

    async def move_back_up(self) -> None:
        """Move back motor up."""
        await self._move_with_stop(self._build_command(SutaCommands.BACK_UP))

    async def move_back_down(self) -> None:
        """Move back motor down."""
        await self._move_with_stop(self._build_command(SutaCommands.BACK_DOWN))

    async def move_back_stop(self) -> None:
        """Stop back motor movement."""
        await self._send_stop()

    async def move_legs_up(self) -> None:
        """Move legs motor up."""
        await self._move_with_stop(self._build_command(SutaCommands.FOOT_UP))

    async def move_legs_down(self) -> None:
        """Move legs motor down."""
        await self._move_with_stop(self._build_command(SutaCommands.FOOT_DOWN))

    async def move_legs_stop(self) -> None:
        """Stop legs motor movement."""
        await self._send_stop()

    async def move_feet_up(self) -> None:
        """Move feet motor up (same command as legs)."""
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        """Move feet motor down (same command as legs)."""
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        """Stop feet motor movement."""
        await self._send_stop()

    async def move_lumbar_up(self) -> None:
        """Move tilt/lumbar motor up."""
        await self._move_with_stop(self._build_command(SutaCommands.TILT_LUMBAR_UP))

    async def move_lumbar_down(self) -> None:
        """Move tilt/lumbar motor down."""
        await self._move_with_stop(self._build_command(SutaCommands.TILT_LUMBAR_DOWN))

    async def move_lumbar_stop(self) -> None:
        """Stop tilt/lumbar motor movement."""
        await self._send_stop()

    async def stop_all(self) -> None:
        """Stop all motor movement."""
        await self._send_stop()

    async def _send_preset_recall(self, command: str) -> None:
        """Send a preset recall command once.

        SUTA firmware handles the full movement to the target preset after a
        single MODE command; repeating the command or forcing STOP causes
        choppy movement.
        """
        await self.write_command(self._build_command(command))

    # Preset methods
    async def preset_flat(self) -> None:
        """Go to flat position."""
        await self._send_preset_recall(SutaCommands.PRESET_FLAT)

    async def preset_memory(self, memory_num: int) -> None:
        """Go to memory preset."""
        commands = {
            1: SutaCommands.PRESET_MEMORY_1,
            2: SutaCommands.PRESET_MEMORY_2,
            3: SutaCommands.PRESET_MEMORY_3,
            4: SutaCommands.PRESET_MEMORY_4,
        }
        if command := commands.get(memory_num):
            await self._send_preset_recall(command)
        else:
            _LOGGER.warning("SUTA supports memory presets 1-4 only")

    async def program_memory(self, memory_num: int) -> None:
        """Program current position to memory."""
        commands = {
            1: SutaCommands.PROGRAM_MEMORY_1,
            2: SutaCommands.PROGRAM_MEMORY_2,
            3: SutaCommands.PROGRAM_MEMORY_3,
            4: SutaCommands.PROGRAM_MEMORY_4,
        }
        if command := commands.get(memory_num):
            await self.write_command(
                self._build_command(command),
                repeat_count=5,
                repeat_delay_ms=150,
            )
        else:
            _LOGGER.warning("SUTA supports memory presets 1-4 only")

    async def preset_zero_g(self) -> None:
        """Go to zero-g preset."""
        await self._send_preset_recall(SutaCommands.PRESET_ZERO_G)

    async def preset_anti_snore(self) -> None:
        """Go to anti-snore preset."""
        await self._send_preset_recall(SutaCommands.PRESET_ANTI_SNORE)

    async def preset_tv(self) -> None:
        """Go to TV preset."""
        await self._send_preset_recall(SutaCommands.PRESET_TV)

    # Light methods
    async def lights_on(self) -> None:
        """Turn on under-bed light and update local light-state tracking."""
        await self.write_command(self._build_command(SutaCommands.LIGHT_ON))
        self._light_state = True

    async def lights_off(self) -> None:
        """Turn off under-bed light and update local light-state tracking."""
        await self.write_command(self._build_command(SutaCommands.LIGHT_OFF))
        self._light_state = False

    async def lights_toggle(self) -> None:
        """Toggle under-bed light using the integration's local light-state flag."""
        if self._light_state:
            await self.lights_off()
        else:
            await self.lights_on()

    # Massage methods
    # SUTA massage uses three parameters per zone: Timer (T), Duty Cycle (DT),
    # and Level (LV). DT cycles: 00->20->33->50->00. LV cycles: 00->10->20->30->00.
    async def massage_head_toggle(self) -> None:
        """Cycle head massage duty cycle (00->20->33->50->00)."""
        await self.write_command(
            self._build_command(SutaCommands.MASSAGE_HEAD_DT + "20"),
            repeat_count=2,
            repeat_delay_ms=100,
        )

    async def massage_foot_toggle(self) -> None:
        """Cycle foot massage duty cycle (00->20->33->50->00)."""
        await self.write_command(
            self._build_command(SutaCommands.MASSAGE_FOOT_DT + "20"),
            repeat_count=2,
            repeat_delay_ms=100,
        )

    async def massage_toggle(self) -> None:
        """Toggle head massage timer (convenience alias)."""
        await self.write_command(
            self._build_command(SutaCommands.MASSAGE_HEAD_TIMER + "00M"),
            repeat_count=2,
            repeat_delay_ms=100,
        )

    async def massage_off(self) -> None:
        """Turn off all massage by setting both zones to DT00."""
        await self.write_command(
            self._build_command(SutaCommands.MASSAGE_HEAD_DT + "00"),
            repeat_count=2,
            repeat_delay_ms=100,
        )
        await self.write_command(
            self._build_command(SutaCommands.MASSAGE_FOOT_DT + "00"),
            repeat_count=2,
            repeat_delay_ms=100,
        )

    # Sync mode (split king)
    async def set_synchro(self, enabled: bool) -> None:
        """Enable or disable split-king sync slave mode.

        When enabled, this side mirrors the other side's movements.
        Sends AT+SINSLAVE=ON or AT+SINSLAVE=OFF.
        """
        cmd = SutaCommands.SYNC_SLAVE_ON if enabled else SutaCommands.SYNC_SLAVE_OFF
        await self.write_command(self._build_command(cmd))
