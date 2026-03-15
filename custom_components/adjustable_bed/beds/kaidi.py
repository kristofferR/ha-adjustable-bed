"""Kaidi bed controller implementation.

Protocol family used by Rize, Floyd, and ISleep Android apps from the same
developer (`com.kaidi_test4.*`).

The transport is a custom packet format over BLE GATT:
- Write char:  `9e5d1e47-5c13-43a0-8635-82adffc1386f`
- Notify char: `9e5d1e47-5c13-43a0-8635-82adffc2386f`

The mobile app performs a lightweight "join" against a room/home ID carried in
the advertisement payload, then sends motor/preset commands as 4-byte control
payloads wrapped in a mesh-style frame.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from bleak.backends.characteristic import BleakGATTCharacteristic

from ..const import (
    CONF_KAIDI_ROOM_ID,
    CONF_KAIDI_TARGET_VADDR,
    KAIDI_BROADCAST_VADDR,
    KAIDI_JOIN_PASSWORD,
    KAIDI_NOTIFY_CHAR_UUID,
    KAIDI_WRITE_CHAR_UUID,
)
from ..kaidi_protocol import extract_kaidi_advertisement, format_kaidi_node_address
from .base import BedController

if TYPE_CHECKING:
    from ..coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

KAIDI_CONTROL_CHANNEL = 0x20
KAIDI_PING_CHANNEL = 0xFF


class KaidiCommands:
    """Kaidi command bytes for single-bed control."""

    HEAD_UP = 0x01
    HEAD_DOWN = 0x02
    HEAD_STOP = 0x03
    FOOT_UP = 0x04
    FOOT_DOWN = 0x05
    FOOT_STOP = 0x06
    STOP_ALL = 0x1C

    MEMORY_SAVE_1 = 0x25
    MEMORY_SAVE_2 = 0x26
    MEMORY_SAVE_3 = 0x27
    MEMORY_SAVE_4 = 0x28

    MEMORY_RECALL_1 = 0x29
    MEMORY_RECALL_2 = 0x2A
    MEMORY_RECALL_3 = 0x2B
    MEMORY_RECALL_4 = 0x2C

    PRESET_ZERO_G = 0x62
    PRESET_ANTI_SNORE = 0x65
    PRESET_FLAT = 0x68


class KaidiController(BedController):
    """Controller for Kaidi custom mesh-over-GATT beds."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        device_name: str | None = None,
        manufacturer_data: dict[int, bytes] | None = None,
    ) -> None:
        """Initialize the Kaidi controller."""
        super().__init__(coordinator)
        self._device_name = device_name
        self._manufacturer_data = dict(manufacturer_data or {})

        self._notify_started = False
        self._session_ready = False
        self._session_lock = asyncio.Lock()

        self._join_event = asyncio.Event()
        self._own_vaddr_event = asyncio.Event()
        self._target_vaddr_event = asyncio.Event()

        self._join_status: int | None = None
        self._room_id: int | None = None
        self._own_vaddr: int | None = None
        self._target_vaddr: int | None = None
        self._write_with_response = True

        entry_data = getattr(getattr(self._coordinator, "entry", None), "data", {})
        cached_room_id = entry_data.get(CONF_KAIDI_ROOM_ID)
        cached_target_vaddr = entry_data.get(CONF_KAIDI_TARGET_VADDR)
        if isinstance(cached_room_id, int):
            self._room_id = cached_room_id
            _LOGGER.debug("Loaded cached room_id=%s from entry data", cached_room_id)
        if isinstance(cached_target_vaddr, int):
            self._target_vaddr = cached_target_vaddr
            _LOGGER.debug("Loaded cached target_vaddr=%s from entry data", cached_target_vaddr)

        if self._manufacturer_data:
            _LOGGER.debug(
                "Kaidi init manufacturer_data keys=%s, payload_lengths=%s",
                list(self._manufacturer_data.keys()),
                {k: len(v) for k, v in self._manufacturer_data.items()},
            )
            for company_id, payload in self._manufacturer_data.items():
                _LOGGER.debug(
                    "  company_id=%d (0x%04X): %s",
                    company_id, company_id, payload.hex(),
                )
        else:
            _LOGGER.debug("Kaidi init: no manufacturer_data available")

        advertisement = extract_kaidi_advertisement(self._manufacturer_data)
        if advertisement is not None:
            _LOGGER.debug(
                "Parsed Kaidi advertisement: type=%s room_id=%s vaddr=%s",
                advertisement.adv_type, advertisement.room_id, advertisement.vaddr,
            )
            if advertisement.room_id is not None:
                self._room_id = advertisement.room_id
            if advertisement.vaddr is not None:
                self._target_vaddr = advertisement.vaddr
        elif self._manufacturer_data:
            _LOGGER.warning(
                "Manufacturer data present but not recognized as Kaidi advertisement "
                "for %s - room ID cannot be extracted",
                self._coordinator.address,
            )

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return KAIDI_WRITE_CHAR_UUID

    @property
    def supports_preset_zero_g(self) -> bool:
        return True

    @property
    def supports_preset_anti_snore(self) -> bool:
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

    def _refresh_write_mode(self) -> None:
        """Refresh write mode from discovered GATT characteristics when available."""
        client = self.client
        services = getattr(client, "services", None)
        if client is None or services is None:
            return

        try:
            iterable = list(services)
        except TypeError:
            return

        for service in iterable:
            for char in getattr(service, "characteristics", []):
                if str(char.uuid).lower() != KAIDI_WRITE_CHAR_UUID:
                    continue
                properties = {prop.lower() for prop in getattr(char, "properties", [])}
                self._write_with_response = "write" in properties
                if not self._write_with_response and "write-without-response" in properties:
                    self._write_with_response = False
                return

    def _build_join_packet(self, room_id: int) -> bytes:
        """Build the Kaidi join packet."""
        return bytes([0x01, 0x16, 0x01]) + room_id.to_bytes(4, "little") + KAIDI_JOIN_PASSWORD

    def _build_ping_packet(self) -> bytes:
        """Build a ping-all packet used to discover this bed's virtual address."""
        source_vaddr = (self._own_vaddr if self._own_vaddr is not None else KAIDI_BROADCAST_VADDR)
        return (
            bytes([0x03])
            + KAIDI_BROADCAST_VADDR.to_bytes(4, "little")
            + bytes([0xFE])
            + source_vaddr.to_bytes(4, "little")
        )

    def _build_control_packet(self, command_id: int, param: int = 0) -> bytes:
        """Build a framed Kaidi control packet."""
        if self._target_vaddr is None:
            raise RuntimeError("Kaidi target virtual address not initialized")

        source_vaddr = self._own_vaddr if self._own_vaddr is not None else KAIDI_BROADCAST_VADDR
        sofa_packet = bytes([0x01, command_id & 0xFF, param & 0xFF, 0x00])
        return (
            bytes([0x03])
            + self._target_vaddr.to_bytes(4, "little")
            + bytes([KAIDI_CONTROL_CHANNEL])
            + source_vaddr.to_bytes(4, "little")
            + sofa_packet
        )

    def _handle_notification(
        self,
        _sender: BleakGATTCharacteristic,
        data: bytearray,
    ) -> None:
        """Handle Kaidi notifications."""
        payload = bytes(data)
        self.forward_raw_notification(KAIDI_NOTIFY_CHAR_UUID, payload)

        if len(payload) < 2:
            return

        # Join/check-password response
        if payload[0] == 0x02 and payload[1] == 0x16:
            self._join_status = payload[2] if len(payload) > 2 else None
            self._join_event.set()
            return

        # Own virtual address command
        if payload[0] == 0x01 and payload[1] == 0x0A and len(payload) >= 6:
            own_vaddr = int.from_bytes(payload[2:6], "little")
            self._own_vaddr = own_vaddr or KAIDI_BROADCAST_VADDR
            self._own_vaddr_event.set()
            return

        # Ping/device data response
        if payload[0] != 0x03 or len(payload) < 16:
            return

        channel = payload[5]
        if channel != KAIDI_PING_CHANNEL:
            return

        node_address = format_kaidi_node_address(payload[6:12])
        if node_address != self._coordinator.address.upper():
            return

        self._target_vaddr = int.from_bytes(payload[12:16], "little")
        self._target_vaddr_event.set()

    async def _ensure_notify_started(self) -> None:
        """Ensure protocol notifications are active."""
        if self._notify_started:
            return

        client = self.client
        if client is None or not client.is_connected:
            raise ConnectionError("Not connected to Kaidi bed")

        self._refresh_write_mode()
        await client.start_notify(KAIDI_NOTIFY_CHAR_UUID, self._handle_notification)
        self._notify_started = True

    async def _wait_for_event(self, event: asyncio.Event, timeout: float, name: str) -> None:
        """Wait for an asyncio.Event with a labeled timeout."""
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except TimeoutError as err:
            raise TimeoutError(f"Timed out waiting for Kaidi {name}") from err

    def _try_resolve_room_id_from_ha(self) -> None:
        """Attempt to resolve room ID from Home Assistant's Bluetooth scanner."""
        hass = getattr(self._coordinator, "hass", None)
        if hass is None:
            return
        try:
            from ..kaidi_metadata import resolve_kaidi_advertisement
            advertisement = resolve_kaidi_advertisement(
                hass,
                self._coordinator.address,
                manufacturer_data=(self._manufacturer_data or None),
            )
            if advertisement is not None:
                if advertisement.room_id is not None:
                    self._room_id = advertisement.room_id
                    _LOGGER.info(
                        "Resolved Kaidi room ID %s from HA Bluetooth scanner for %s",
                        self._room_id,
                        self._coordinator.address,
                    )
                if advertisement.vaddr is not None and self._target_vaddr is None:
                    self._target_vaddr = advertisement.vaddr
                    _LOGGER.info(
                        "Resolved Kaidi target vaddr %s from HA Bluetooth scanner for %s",
                        self._target_vaddr,
                        self._coordinator.address,
                    )
        except Exception:
            _LOGGER.debug(
                "Could not resolve Kaidi metadata from HA scanner for %s",
                self._coordinator.address,
                exc_info=True,
            )

    async def _ensure_session_ready(self) -> None:
        """Ensure the Kaidi join sequence has completed."""
        if self._session_ready and self._target_vaddr is not None:
            return

        async with self._session_lock:
            if self._session_ready and self._target_vaddr is not None:
                return

            if self._room_id is None:
                advertisement = extract_kaidi_advertisement(self._manufacturer_data)
                if advertisement is not None:
                    self._room_id = advertisement.room_id
                    if self._target_vaddr is None:
                        self._target_vaddr = advertisement.vaddr

            # Last resort: try to get manufacturer data from HA's Bluetooth scanner
            if self._room_id is None:
                _LOGGER.debug(
                    "No Kaidi room ID from constructor data for %s, "
                    "trying HA Bluetooth scanner...",
                    self._coordinator.address,
                )
                self._try_resolve_room_id_from_ha()

            if self._room_id is None:
                raise RuntimeError(
                    "Kaidi room/home ID not found in advertisement data for "
                    f"{self._coordinator.address}. Ensure the bed is powered on and "
                    "has been provisioned in the official Rize/Floyd/ISleep app. "
                    "The bed must be broadcasting its mesh advertisement for the "
                    "integration to extract the room ID."
                )

            await self._ensure_notify_started()

            join_packet = self._build_join_packet(self._room_id)
            _LOGGER.debug(
                "Sending Kaidi join packet for %s: room_id=%s, write_with_response=%s, "
                "packet=%s",
                self._coordinator.address,
                self._room_id,
                self._write_with_response,
                join_packet.hex(),
            )
            self._join_event.clear()
            self._join_status = None
            await self._write_gatt_with_retry(
                KAIDI_WRITE_CHAR_UUID,
                join_packet,
                response=self._write_with_response,
            )
            await self._wait_for_event(self._join_event, timeout=5.0, name="join response")

            _LOGGER.debug(
                "Kaidi join response for %s: status=%s",
                self._coordinator.address,
                self._join_status,
            )
            if self._join_status != 0:
                raise RuntimeError(f"Kaidi join rejected with status {self._join_status}")

            if self._own_vaddr is None:
                self._own_vaddr_event.clear()
                try:
                    await asyncio.wait_for(self._own_vaddr_event.wait(), timeout=1.0)
                except TimeoutError:
                    pass

            if self._own_vaddr is None:
                self._own_vaddr = KAIDI_BROADCAST_VADDR

            if self._target_vaddr is None:
                self._target_vaddr_event.clear()
                await self._write_gatt_with_retry(
                    KAIDI_WRITE_CHAR_UUID,
                    self._build_ping_packet(),
                    response=self._write_with_response,
                )
                await self._wait_for_event(
                    self._target_vaddr_event,
                    timeout=5.0,
                    name="target virtual address",
                )

            self._session_ready = self._target_vaddr is not None
            _LOGGER.debug(
                "Kaidi session ready for %s (room_id=%s, own_vaddr=%s, target_vaddr=%s)",
                self._coordinator.address,
                self._room_id,
                self._own_vaddr,
                self._target_vaddr,
            )

    async def write_command(
        self,
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Write a fully framed Kaidi packet."""
        await self._ensure_session_ready()
        await self._write_gatt_with_retry(
            KAIDI_WRITE_CHAR_UUID,
            command,
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=self._write_with_response,
        )

    async def _write_control_command(
        self,
        command_id: int,
        *,
        param: int = 0,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        """Build and send a Kaidi control command."""
        await self._ensure_session_ready()
        await self._write_gatt_with_retry(
            KAIDI_WRITE_CHAR_UUID,
            self._build_control_packet(command_id, param=param),
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=self._write_with_response,
        )

    async def start_notify(
        self,
        callback: Callable[[str, float], None] | None = None,
    ) -> None:
        """Start protocol notifications.

        Kaidi notifications are used for protocol session management rather than
        position feedback, so the callback is stored but not populated with motor
        angles.
        """
        self._notify_callback = callback
        await self._ensure_notify_started()

    async def stop_notify(self) -> None:
        """Stop Kaidi notifications."""
        self._notify_callback = None
        if not self._notify_started or self.client is None or not self.client.is_connected:
            return
        await self.client.stop_notify(KAIDI_NOTIFY_CHAR_UUID)
        self._notify_started = False

    async def _move_with_stop_command(self, move_command: int, stop_command: int) -> None:
        """Send a movement command, then stop that motor."""
        try:
            await self._write_control_command(
                move_command,
                repeat_count=self._coordinator.motor_pulse_count,
                repeat_delay_ms=self._coordinator.motor_pulse_delay_ms,
            )
        finally:
            try:
                await self._write_control_command(
                    stop_command,
                    cancel_event=asyncio.Event(),
                )
            except ConnectionError:
                _LOGGER.debug("Kaidi cleanup stop skipped because device disconnected")

    async def move_head_up(self) -> None:
        await self._move_with_stop_command(KaidiCommands.HEAD_UP, KaidiCommands.HEAD_STOP)

    async def move_head_down(self) -> None:
        await self._move_with_stop_command(KaidiCommands.HEAD_DOWN, KaidiCommands.HEAD_STOP)

    async def move_head_stop(self) -> None:
        await self._write_control_command(
            KaidiCommands.HEAD_STOP,
            cancel_event=asyncio.Event(),
        )

    async def move_back_up(self) -> None:
        await self.move_head_up()

    async def move_back_down(self) -> None:
        await self.move_head_down()

    async def move_back_stop(self) -> None:
        await self.move_head_stop()

    async def move_legs_up(self) -> None:
        await self._move_with_stop_command(KaidiCommands.FOOT_UP, KaidiCommands.FOOT_STOP)

    async def move_legs_down(self) -> None:
        await self._move_with_stop_command(KaidiCommands.FOOT_DOWN, KaidiCommands.FOOT_STOP)

    async def move_legs_stop(self) -> None:
        await self._write_control_command(
            KaidiCommands.FOOT_STOP,
            cancel_event=asyncio.Event(),
        )

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        await self.move_legs_stop()

    async def stop_all(self) -> None:
        await self._write_control_command(
            KaidiCommands.STOP_ALL,
            cancel_event=asyncio.Event(),
        )

    async def preset_flat(self) -> None:
        await self._write_control_command(KaidiCommands.PRESET_FLAT)

    async def preset_zero_g(self) -> None:
        await self._write_control_command(KaidiCommands.PRESET_ZERO_G)

    async def preset_anti_snore(self) -> None:
        await self._write_control_command(KaidiCommands.PRESET_ANTI_SNORE)

    async def preset_memory(self, memory_num: int) -> None:
        command_map = {
            1: KaidiCommands.MEMORY_RECALL_1,
            2: KaidiCommands.MEMORY_RECALL_2,
            3: KaidiCommands.MEMORY_RECALL_3,
            4: KaidiCommands.MEMORY_RECALL_4,
        }
        try:
            command_id = command_map[memory_num]
        except KeyError as err:
            raise ValueError(f"Invalid Kaidi memory preset {memory_num}") from err
        await self._write_control_command(command_id)

    async def program_memory(self, memory_num: int) -> None:
        command_map = {
            1: KaidiCommands.MEMORY_SAVE_1,
            2: KaidiCommands.MEMORY_SAVE_2,
            3: KaidiCommands.MEMORY_SAVE_3,
            4: KaidiCommands.MEMORY_SAVE_4,
        }
        try:
            command_id = command_map[memory_num]
        except KeyError as err:
            raise ValueError(f"Invalid Kaidi memory slot {memory_num}") from err
        await self._write_control_command(command_id)
