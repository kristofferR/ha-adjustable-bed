"""SUTA Smart Home bed controller implementation.

Protocol reverse-engineered from com.shuta.smart_home.

Bed-frame controllers use an ASCII AT command protocol over BLE:
- Service UUID: 0000fff0-0000-1000-8000-00805f9b34fb
- Notify characteristic: 0000fff1-0000-1000-8000-00805f9b34fb
- Write characteristic: 0000fff2-0000-1000-8000-00805f9b34fb
- Command format: b"AT+...\\r\\n" (UTF-8, CRLF-terminated)
- No checksum

The official app subscribes to notifications and requests MTU 250 before sending
commands.  Several motor commands exceed the default 20-byte ATT payload.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ..const import (
    SUTA_DEFAULT_WRITE_CHAR_UUID,
    SUTA_NOTIFY_CHAR_UUID,
    SUTA_SERVICE_UUID,
)
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

_SUTA_APP_REQUESTED_MTU = 250
# The longest currently implemented B202 command is 24 bytes including CRLF.
_SUTA_MIN_COMMAND_MTU = 27


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
        self._notify_char_uuid = SUTA_NOTIFY_CHAR_UUID
        self._write_with_response = False
        self._gatt_characteristics_initialized = False
        self._notifications_started = False
        self._light_state = False

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the command characteristic UUID."""
        return self._write_char_uuid

    @property
    def requires_notification_channel(self) -> bool:
        """Return True because the OEM app enables notifications before commands."""
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

    def _refresh_gatt_characteristics(self) -> None:
        """Resolve the bed-frame write/notify characteristics from FFF0."""
        if self._gatt_characteristics_initialized:
            return

        client = self.client
        if client is None or client.services is None:
            return

        service = client.services.get_service(SUTA_SERVICE_UUID)
        if service is None:
            _LOGGER.debug(
                "SUTA bed-frame service %s not found; using fallback chars write=%s notify=%s",
                SUTA_SERVICE_UUID,
                self._write_char_uuid,
                self._notify_char_uuid,
            )
            self._gatt_characteristics_initialized = True
            return

        write_candidate = None
        notify_candidate = None
        for char in service.characteristics:
            props = {prop.lower() for prop in char.properties}
            if "write" in props or "write-without-response" in props:
                if (
                    write_candidate is None
                    or str(char.uuid).lower() == SUTA_DEFAULT_WRITE_CHAR_UUID
                ):
                    write_candidate = char
            if "notify" in props or "indicate" in props:
                if notify_candidate is None or str(char.uuid).lower() == SUTA_NOTIFY_CHAR_UUID:
                    notify_candidate = char

        if write_candidate is not None:
            write_props = {prop.lower() for prop in write_candidate.properties}
            self._write_char_uuid = str(write_candidate.uuid)
            # Android uses the characteristic's advertised default write type.
            self._write_with_response = "write" in write_props
        else:
            _LOGGER.warning(
                "No writable characteristic found in SUTA service %s; using fallback %s",
                SUTA_SERVICE_UUID,
                self._write_char_uuid,
            )

        if notify_candidate is not None:
            self._notify_char_uuid = str(notify_candidate.uuid)
        else:
            _LOGGER.warning(
                "No notifiable characteristic found in SUTA service %s; using fallback %s",
                SUTA_SERVICE_UUID,
                self._notify_char_uuid,
            )

        self._gatt_characteristics_initialized = True
        _LOGGER.debug(
            "SUTA GATT resolved: service=%s write=%s response=%s notify=%s",
            SUTA_SERVICE_UUID,
            self._write_char_uuid,
            self._write_with_response,
            self._notify_char_uuid,
        )

    def _handle_notification(
        self,
        characteristic: BleakGATTCharacteristic,
        data: bytearray,
    ) -> None:
        """Forward and log SUTA AT responses received on FFF1."""
        payload = bytes(data)
        characteristic_uuid = str(getattr(characteristic, "uuid", characteristic))
        self.forward_raw_notification(characteristic_uuid, payload)
        _LOGGER.debug(
            "SUTA response on %s: %r",
            characteristic_uuid,
            payload.decode("utf-8", errors="replace"),
        )

    async def _acquire_command_mtu(self) -> None:
        """Acquire the negotiated MTU on backends that require an explicit request.

        Android requests MTU 250 after subscribing.  Bleak's BlueZ backend exposes
        MTU negotiation through a guarded private coroutine; other backends usually
        negotiate automatically and report their MTU through ``mtu_size``.
        """
        client = self.client
        if client is None or not client.is_connected:
            return

        backend = getattr(client, "_backend", None)
        acquire_mtu = getattr(backend, "_acquire_mtu", None)
        if callable(acquire_mtu):
            try:
                async with self._ble_lock:
                    await acquire_mtu()
            except (AssertionError, BleakError, OSError, TimeoutError) as err:
                _LOGGER.warning(
                    "Could not acquire SUTA command MTU (OEM app requests %d): %s",
                    _SUTA_APP_REQUESTED_MTU,
                    err,
                )

        mtu_size = getattr(client, "mtu_size", 23)
        if isinstance(mtu_size, int) and mtu_size < _SUTA_MIN_COMMAND_MTU:
            _LOGGER.warning(
                "SUTA negotiated MTU is %d; motor commands need at least %d. "
                "Writes longer than %d bytes may fail on this Bluetooth backend.",
                mtu_size,
                _SUTA_MIN_COMMAND_MTU,
                mtu_size - 3,
            )
        else:
            _LOGGER.debug(
                "SUTA command MTU ready: %s (OEM app requests %d)",
                mtu_size,
                _SUTA_APP_REQUESTED_MTU,
            )

    async def start_notify(self, callback: Callable[[str, float], None] | None = None) -> None:
        """Enable the FFF1 response channel and negotiate MTU before commands."""
        self._notify_callback = callback
        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Cannot start SUTA notifications: not connected")

        self._refresh_gatt_characteristics()
        if self._notifications_started:
            return

        try:
            async with self._ble_lock:
                await client.start_notify(self._notify_char_uuid, self._handle_notification)
        except BleakError:
            _LOGGER.warning(
                "Failed to enable required SUTA notification characteristic %s",
                self._notify_char_uuid,
                exc_info=True,
            )
            self.log_discovered_services(level=logging.INFO)
            raise

        self._notifications_started = True
        _LOGGER.debug("Enabled required SUTA notifications on %s", self._notify_char_uuid)
        await self._acquire_command_mtu()

    async def stop_notify(self) -> None:
        """Stop the SUTA response notification channel."""
        client = self.client
        if client is None or not client.is_connected:
            self._notifications_started = False
            self._notify_callback = None
            return
        if not self._notifications_started:
            self._notify_callback = None
            return

        try:
            async with self._ble_lock:
                await client.stop_notify(self._notify_char_uuid)
        except BleakError:
            _LOGGER.debug("Failed to stop SUTA notifications", exc_info=True)
        finally:
            self._notifications_started = False
            self._notify_callback = None

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a SUTA command packet."""
        self._refresh_gatt_characteristics()
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
