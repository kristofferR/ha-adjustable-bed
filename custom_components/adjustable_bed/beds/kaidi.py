"""Kaidi bed controller implementation.

Protocol family used by Rize, Floyd, and ISleep Android apps from the same
developer (`com.kaidi_test4.*`).

The transport is a custom packet format over BLE GATT:
- Write char:  `9e5d1e47-5c13-43a0-8635-82adffc1386f`
- Notify char: `9e5d1e47-5c13-43a0-8635-82adffc2386f`

The mobile app performs a lightweight "join" against a room/home ID carried in
the advertisement payload, then sends motor/preset commands as 4-byte control
payloads wrapped in a mesh-style frame.

All three OEM apps (Rize 1.3.0, ISleep 1.6.3, Floyd 1.0.7) use exclusively
SEAT_* command values (1-167).  The BED_* constants (71-115) found in
PLDataTrans.java are legacy/enterprise firmware values and are NOT used by any
consumer mobile app.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bleak.backends.characteristic import BleakGATTCharacteristic

from ..const import (
    CONF_KAIDI_PRODUCT_ID,
    CONF_KAIDI_ROOM_ID,
    CONF_KAIDI_SOFA_ACU_NO,
    CONF_KAIDI_TARGET_VADDR,
    KAIDI_BROADCAST_VADDR,
    KAIDI_JOIN_PASSWORD,
    KAIDI_NOTIFY_CHAR_UUID,
    KAIDI_VARIANT_SEAT_1,
    KAIDI_VARIANT_SEAT_1_2,
    KAIDI_VARIANT_SEAT_2,
    KAIDI_VARIANT_SEAT_3,
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
    """Legacy aliases for the Kaidi Seat 1 command bytes."""

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


@dataclass(frozen=True, slots=True)
class KaidiCommandProfile:
    """Command mapping for one Kaidi variant family.

    All values come from the SEAT_* instruction tables found in the de-minified
    JS bundles of the Rize, ISleep, and Floyd Android apps.
    """

    variant: str
    # Core motors (all beds)
    head_up: int
    head_down: int
    head_stop: int
    foot_up: int
    foot_down: int
    foot_stop: int
    stop_all: int | None = None
    # Memory presets
    memory_save: dict[int, int] = field(default_factory=dict)
    memory_recall: dict[int, int] = field(default_factory=dict)
    # Standard presets
    preset_flat: int | None = None
    preset_zero_g: int | None = None
    preset_anti_snore: int | None = None
    # Extended motors (3+ motor beds)
    back_up: int | None = None
    back_down: int | None = None
    back_stop: int | None = None
    waist_up: int | None = None
    waist_down: int | None = None
    waist_stop: int | None = None
    neck_up: int | None = None
    neck_down: int | None = None
    neck_stop: int | None = None
    all_up: int | None = None
    all_down: int | None = None
    all_stop: int | None = None
    new_all_up: int | None = None
    new_all_down: int | None = None
    new_all_stop: int | None = None
    # Lights
    light_on: int | None = None
    light_off: int | None = None
    # Extended presets
    preset_book: int | None = None
    preset_leisure: int | None = None
    # Massage
    massage_mode_1: int | None = None
    massage_mode_2: int | None = None
    massage_mode_3: int | None = None


# ---------------------------------------------------------------------------
# Product family metadata
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class KaidiProductFamily:
    """Capabilities for a product ID, derived from the OEM app's bedUI mapping."""

    bed_ui: int
    has_back: bool = False
    has_waist: bool = False
    has_neck: bool = False
    has_all: bool = False
    has_lights: bool = False
    has_massage: bool = False
    has_book: bool = False
    has_leisure: bool = False


# Product ID → capability set.  Derived from the Rize/Floyd/ISleep JS bundles.
# bedUI 2: head + foot only
# bedUI 3: back + foot + all
# bedUI 4: back + foot + waist + all
# bedUI 5-6: back + foot + waist + all + book + leisure presets
# bedUI 7-8: back + foot + waist + all + leisure preset (+ neck for bedUI 8)
KAIDI_PRODUCT_FAMILIES: dict[int, KaidiProductFamily] = {
    129: KaidiProductFamily(bed_ui=2),
    130: KaidiProductFamily(bed_ui=2),
    131: KaidiProductFamily(bed_ui=3, has_back=True, has_all=True),
    132: KaidiProductFamily(bed_ui=4, has_back=True, has_waist=True, has_all=True),
    133: KaidiProductFamily(bed_ui=3, has_back=True, has_all=True),
    134: KaidiProductFamily(bed_ui=4, has_back=True, has_waist=True, has_all=True),
    135: KaidiProductFamily(
        bed_ui=5, has_back=True, has_waist=True, has_all=True,
        has_lights=True, has_massage=True, has_book=True, has_leisure=True,
    ),
    136: KaidiProductFamily(
        bed_ui=6, has_back=True, has_waist=True, has_all=True,
        has_lights=True, has_massage=True, has_book=True, has_leisure=True,
    ),
    137: KaidiProductFamily(
        bed_ui=7, has_back=True, has_waist=True, has_all=True,
        has_lights=True, has_massage=True, has_leisure=True,
    ),
    138: KaidiProductFamily(
        bed_ui=8, has_back=True, has_waist=True, has_neck=True, has_all=True,
        has_lights=True, has_massage=True, has_leisure=True,
    ),
    139: KaidiProductFamily(bed_ui=2),
    142: KaidiProductFamily(
        bed_ui=5, has_back=True, has_waist=True, has_all=True,
        has_lights=True, has_massage=True, has_book=True, has_leisure=True,
    ),
    143: KaidiProductFamily(bed_ui=2),
}

# Default for beds without a known product ID.
_DEFAULT_PRODUCT_FAMILY = KaidiProductFamily(bed_ui=2)


# ---------------------------------------------------------------------------
# Command profiles
# ---------------------------------------------------------------------------

KAIDI_COMMAND_PROFILES: dict[str, KaidiCommandProfile] = {
    KAIDI_VARIANT_SEAT_1: KaidiCommandProfile(
        variant=KAIDI_VARIANT_SEAT_1,
        head_up=0x01,
        head_down=0x02,
        head_stop=0x03,
        foot_up=0x04,
        foot_down=0x05,
        foot_stop=0x06,
        stop_all=0x1C,
        memory_save={1: 0x25, 2: 0x26, 3: 0x27, 4: 0x28},
        memory_recall={1: 0x29, 2: 0x2A, 3: 0x2B, 4: 0x2C},
        preset_zero_g=0x62,
        preset_anti_snore=0x65,
        preset_flat=0x68,
        # Extended motors
        back_up=0x7A,     # SEAT_1_BACK_UP = 122
        back_down=0x7B,   # SEAT_1_BACK_DOWN = 123
        back_stop=0x7C,   # SEAT_1_BACK_STOP = 124
        waist_up=0x83,    # SEAT_1_WAIST_UP = 131
        waist_down=0x84,  # SEAT_1_WAIST_DOWN = 132
        waist_stop=0x85,  # SEAT_1_WAIST_STOP = 133
        neck_up=0x8C,     # SEAT_1_NECK_UP = 140
        neck_down=0x8D,   # SEAT_1_NECK_DOWN = 141
        neck_stop=0x8E,   # SEAT_1_NECK_STOP = 142
        all_up=0x07,      # SEAT_1_ALL_UP = 7
        all_down=0x08,    # SEAT_1_ALL_DOWN = 8
        all_stop=0x09,    # SEAT_1_ALL_STOP = 9
        new_all_up=0x95,  # SEAT_1_NEW_ALL_UP = 149
        new_all_down=0x96,  # SEAT_1_NEW_ALL_DOWN = 150
        new_all_stop=0x97,  # SEAT_1_NEW_ALL_STOP = 151
        # Lights
        light_on=0x5C,    # SEAT_1_BED_LIGHT_ON = 92
        light_off=0x5D,   # SEAT_1_BED_LIGHT_OFF = 93
        # Extended presets
        preset_book=0x9E,    # SEAT_1_BOOK = 158
        preset_leisure=0xA1,  # SEAT_1_LEISURE = 161
        # Massage
        massage_mode_1=0x6B,  # SEAT_1_MASSAGE_MODE1 = 107
        massage_mode_2=0x6E,  # SEAT_1_MASSAGE_MODE2 = 110
        massage_mode_3=0x71,  # SEAT_1_MASSAGE_MODE3 = 113
    ),
    KAIDI_VARIANT_SEAT_2: KaidiCommandProfile(
        variant=KAIDI_VARIANT_SEAT_2,
        head_up=0x0A,
        head_down=0x0B,
        head_stop=0x0C,
        foot_up=0x0D,
        foot_down=0x0E,
        foot_stop=0x0F,
        stop_all=0x1D,
        memory_save={1: 0x2D, 2: 0x2E, 3: 0x2F, 4: 0x30},
        memory_recall={1: 0x31, 2: 0x32, 3: 0x33, 4: 0x34},
        preset_zero_g=0x63,
        preset_anti_snore=0x66,
        preset_flat=0x69,
        # Extended motors
        back_up=0x7D,     # SEAT_2_BACK_UP = 125
        back_down=0x7E,   # SEAT_2_BACK_DOWN = 126
        back_stop=0x7F,   # SEAT_2_BACK_STOP = 127
        waist_up=0x86,    # SEAT_2_WAIST_UP = 134
        waist_down=0x87,  # SEAT_2_WAIST_DOWN = 135
        waist_stop=0x88,  # SEAT_2_WAIST_STOP = 136
        neck_up=0x8F,     # SEAT_2_NECK_UP = 143
        neck_down=0x90,   # SEAT_2_NECK_DOWN = 144
        neck_stop=0x91,   # SEAT_2_NECK_STOP = 145
        new_all_up=0x98,  # SEAT_2_NEW_ALL_UP = 152
        new_all_down=0x99,  # SEAT_2_NEW_ALL_DOWN = 153
        new_all_stop=0x9A,  # SEAT_2_NEW_ALL_STOP = 154
        # Lights
        light_on=0x5E,    # SEAT_2_BED_LIGHT_ON = 94
        light_off=0x5F,   # SEAT_2_BED_LIGHT_OFF = 95
        # Extended presets
        preset_book=0x9F,    # SEAT_2_BOOK = 159
        preset_leisure=0xA2,  # SEAT_2_LEISURE = 162
        # Massage
        massage_mode_1=0x6C,  # SEAT_2_MASSAGE_MODE1 = 108
        massage_mode_2=0x6F,  # SEAT_2_MASSAGE_MODE2 = 111
        massage_mode_3=0x72,  # SEAT_2_MASSAGE_MODE3 = 114
    ),
    KAIDI_VARIANT_SEAT_3: KaidiCommandProfile(
        variant=KAIDI_VARIANT_SEAT_3,
        head_up=0x13,
        head_down=0x14,
        head_stop=0x15,
        foot_up=0x16,
        foot_down=0x17,
        foot_stop=0x18,
        memory_save={1: 0x35, 2: 0x36, 3: 0x37, 4: 0x38},
        memory_recall={1: 0x39, 2: 0x3A, 3: 0x3B, 4: 0x3C},
        # Seat 3 has limited extended commands
        neck_up=0x92,     # SEAT_3_NECK_UP = 146
        neck_down=0x93,   # SEAT_3_NECK_DOWN = 147
        neck_stop=0x94,   # SEAT_3_NECK_STOP = 148
        new_all_up=0x9B,  # SEAT_3_NEW_ALL_UP = 155
        new_all_down=0x9C,  # SEAT_3_NEW_ALL_DOWN = 156
        new_all_stop=0x9D,  # SEAT_3_NEW_ALL_STOP = 157
        # Lights
        light_on=0x60,    # SEAT_3_BED_LIGHT_ON = 96
        light_off=0x61,   # SEAT_3_BED_LIGHT_OFF = 97
        # Extended presets
        preset_book=0xA0,    # SEAT_3_BOOK = 160
        preset_leisure=0xA3,  # SEAT_3_LEISURE = 163
        # Massage
        massage_mode_1=0x6D,  # SEAT_3_MASSAGE_MODE1 = 109
        massage_mode_2=0x70,  # SEAT_3_MASSAGE_MODE2 = 112
        massage_mode_3=0x73,  # SEAT_3_MASSAGE_MODE3 = 115
    ),
}

# seat_1_2 uses seat_1 as primary — dual-bed sending is handled by the controller
KAIDI_COMMAND_PROFILES[KAIDI_VARIANT_SEAT_1_2] = KaidiCommandProfile(
    variant=KAIDI_VARIANT_SEAT_1_2,
    **{
        f.name: getattr(KAIDI_COMMAND_PROFILES[KAIDI_VARIANT_SEAT_1], f.name)
        for f in KaidiCommandProfile.__dataclass_fields__.values()
        if f.name != "variant"
    },
)

# Scalar command fields used to build the dual-bed command map.
_PROFILE_SCALAR_FIELDS: tuple[str, ...] = (
    "head_up", "head_down", "head_stop",
    "foot_up", "foot_down", "foot_stop",
    "stop_all",
    "preset_flat", "preset_zero_g", "preset_anti_snore",
    "back_up", "back_down", "back_stop",
    "waist_up", "waist_down", "waist_stop",
    "neck_up", "neck_down", "neck_stop",
    "all_up", "all_down", "all_stop",
    "new_all_up", "new_all_down", "new_all_stop",
    "light_on", "light_off",
    "preset_book", "preset_leisure",
    "massage_mode_1", "massage_mode_2", "massage_mode_3",
)


def _build_dual_command_map(
    primary: KaidiCommandProfile,
    secondary: KaidiCommandProfile,
) -> dict[int, int]:
    """Build a mapping from primary command IDs to secondary command IDs.

    Used by seat_1_2 to also send the seat_2 equivalent of every seat_1 command
    so that both sides of a split/dual bed move together.
    """
    mapping: dict[int, int] = {}
    for field_name in _PROFILE_SCALAR_FIELDS:
        p = getattr(primary, field_name, None)
        s = getattr(secondary, field_name, None)
        if p is not None and s is not None:
            mapping[p] = s
    for slot, p_cmd in primary.memory_save.items():
        s_cmd = secondary.memory_save.get(slot)
        if s_cmd is not None:
            mapping[p_cmd] = s_cmd
    for slot, p_cmd in primary.memory_recall.items():
        s_cmd = secondary.memory_recall.get(slot)
        if s_cmd is not None:
            mapping[p_cmd] = s_cmd
    return mapping


class KaidiController(BedController):
    """Controller for Kaidi custom mesh-over-GATT beds."""

    def __init__(
        self,
        coordinator: AdjustableBedCoordinator,
        *,
        device_name: str | None = None,
        manufacturer_data: dict[int, bytes] | None = None,
        variant: str = KAIDI_VARIANT_SEAT_1,
        variant_source: str = "legacy_fallback",
    ) -> None:
        """Initialize the Kaidi controller."""
        super().__init__(coordinator)
        self._device_name = device_name
        self._manufacturer_data = dict(manufacturer_data or {})
        self._variant = variant
        self._variant_source = variant_source
        profile = KAIDI_COMMAND_PROFILES.get(variant)
        if profile is None:
            raise ValueError(
                f"Unsupported Kaidi variant '{variant}'. "
                f"Expected one of: {', '.join(sorted(KAIDI_COMMAND_PROFILES))}"
            )
        self._command_profile = profile

        # For dual beds (seat_1_2), build a map from seat_1 → seat_2 commands
        if variant == KAIDI_VARIANT_SEAT_1_2:
            self._dual_map = _build_dual_command_map(
                KAIDI_COMMAND_PROFILES[KAIDI_VARIANT_SEAT_1],
                KAIDI_COMMAND_PROFILES[KAIDI_VARIANT_SEAT_2],
            )
        else:
            self._dual_map: dict[int, int] = {}

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
        self._product_id: int | None = None
        self._sofa_acu_no: int | None = None

        entry_data = getattr(getattr(self._coordinator, "entry", None), "data", {})
        cached_room_id = entry_data.get(CONF_KAIDI_ROOM_ID)
        cached_target_vaddr = entry_data.get(CONF_KAIDI_TARGET_VADDR)
        cached_product_id = entry_data.get(CONF_KAIDI_PRODUCT_ID)
        cached_sofa_acu_no = entry_data.get(CONF_KAIDI_SOFA_ACU_NO)
        if isinstance(cached_room_id, int):
            self._room_id = cached_room_id
            _LOGGER.debug("Loaded cached room_id=%s from entry data", cached_room_id)
        if isinstance(cached_target_vaddr, int):
            self._target_vaddr = cached_target_vaddr
            _LOGGER.debug("Loaded cached target_vaddr=%s from entry data", cached_target_vaddr)
        if isinstance(cached_product_id, int):
            self._product_id = cached_product_id
        if isinstance(cached_sofa_acu_no, int):
            self._sofa_acu_no = cached_sofa_acu_no

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
                "Parsed Kaidi advertisement: type=%s room_id=%s vaddr=%s product_id=%s sofa_acu_no=%s variant=%s (%s)",
                advertisement.adv_type,
                advertisement.room_id,
                advertisement.vaddr,
                advertisement.product_id,
                advertisement.sofa_acu_no,
                self._variant,
                self._variant_source,
            )
            if advertisement.room_id is not None:
                self._room_id = advertisement.room_id
            if advertisement.vaddr is not None:
                self._target_vaddr = advertisement.vaddr
            if advertisement.product_id is not None:
                self._product_id = advertisement.product_id
            if advertisement.sofa_acu_no is not None:
                self._sofa_acu_no = advertisement.sofa_acu_no
        elif self._manufacturer_data:
            _LOGGER.warning(
                "Manufacturer data present but not recognized as Kaidi advertisement "
                "for %s - room ID cannot be extracted",
                self._coordinator.address,
            )

    # ------------------------------------------------------------------
    # Product family helpers
    # ------------------------------------------------------------------

    @property
    def _product_family(self) -> KaidiProductFamily:
        """Return the capability set for this bed's product ID."""
        if self._product_id is not None:
            return KAIDI_PRODUCT_FAMILIES.get(self._product_id, _DEFAULT_PRODUCT_FAMILY)
        return _DEFAULT_PRODUCT_FAMILY

    # ------------------------------------------------------------------
    # Capability properties
    # ------------------------------------------------------------------

    @property
    def control_characteristic_uuid(self) -> str:
        """Return the UUID of the control characteristic."""
        return KAIDI_WRITE_CHAR_UUID

    @property
    def supports_preset_flat(self) -> bool:
        return self._command_profile.preset_flat is not None

    @property
    def supports_preset_zero_g(self) -> bool:
        return self._command_profile.preset_zero_g is not None

    @property
    def supports_preset_anti_snore(self) -> bool:
        return self._command_profile.preset_anti_snore is not None

    @property
    def supports_memory_presets(self) -> bool:
        return bool(self._command_profile.memory_recall)

    @property
    def memory_slot_count(self) -> int:
        return len(self._command_profile.memory_recall)

    @property
    def supports_memory_programming(self) -> bool:
        return bool(self._command_profile.memory_save)

    @property
    def supports_lights(self) -> bool:
        return (
            self._command_profile.light_on is not None
            and self._product_family.has_lights
        )

    # ------------------------------------------------------------------
    # BLE transport
    # ------------------------------------------------------------------

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
                if advertisement.product_id is not None:
                    self._product_id = advertisement.product_id
                if advertisement.sofa_acu_no is not None:
                    self._sofa_acu_no = advertisement.sofa_acu_no
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

    # ------------------------------------------------------------------
    # Command helpers
    # ------------------------------------------------------------------

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
        """Build and send a Kaidi control command.

        For dual-bed variants (seat_1_2), also sends the seat_2 equivalent so
        both sides of a split bed move together.
        """
        await self._ensure_session_ready()
        await self._write_gatt_with_retry(
            KAIDI_WRITE_CHAR_UUID,
            self._build_control_packet(command_id, param=param),
            repeat_count=repeat_count,
            repeat_delay_ms=repeat_delay_ms,
            cancel_event=cancel_event,
            response=self._write_with_response,
        )
        secondary_id = self._dual_map.get(command_id)
        if secondary_id is not None:
            await self._write_gatt_with_retry(
                KAIDI_WRITE_CHAR_UUID,
                self._build_control_packet(secondary_id, param=param),
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

    # ------------------------------------------------------------------
    # Movement helpers
    # ------------------------------------------------------------------

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

    def _require_memory_command(self, command_map: dict[int, int], memory_num: int) -> int:
        """Resolve a Kaidi memory command or raise a helpful error."""
        if not command_map:
            raise NotImplementedError(
                f"Kaidi variant {self._variant} does not expose memory presets"
            )
        try:
            return command_map[memory_num]
        except KeyError as err:
            raise ValueError(f"Invalid Kaidi memory slot {memory_num}") from err

    async def _write_optional_control_command(self, command_id: int | None, label: str) -> None:
        """Send a variant-specific command that may not exist on all profiles."""
        if command_id is None:
            raise NotImplementedError(
                f"Kaidi variant {self._variant} does not support {label}"
            )
        await self._write_control_command(command_id)

    # ------------------------------------------------------------------
    # Core motor methods (all beds)
    # ------------------------------------------------------------------

    async def move_head_up(self) -> None:
        await self._move_with_stop_command(
            self._command_profile.head_up,
            self._command_profile.head_stop,
        )

    async def move_head_down(self) -> None:
        await self._move_with_stop_command(
            self._command_profile.head_down,
            self._command_profile.head_stop,
        )

    async def move_head_stop(self) -> None:
        await self._write_control_command(
            self._command_profile.head_stop,
            cancel_event=asyncio.Event(),
        )

    async def move_back_up(self) -> None:
        p = self._command_profile
        if p.back_up is not None and self._product_family.has_back:
            await self._move_with_stop_command(p.back_up, p.back_stop)
        else:
            await self.move_head_up()

    async def move_back_down(self) -> None:
        p = self._command_profile
        if p.back_down is not None and self._product_family.has_back:
            await self._move_with_stop_command(p.back_down, p.back_stop)
        else:
            await self.move_head_down()

    async def move_back_stop(self) -> None:
        p = self._command_profile
        if p.back_stop is not None and self._product_family.has_back:
            await self._write_control_command(p.back_stop, cancel_event=asyncio.Event())
        else:
            await self.move_head_stop()

    async def move_legs_up(self) -> None:
        await self._move_with_stop_command(
            self._command_profile.foot_up,
            self._command_profile.foot_stop,
        )

    async def move_legs_down(self) -> None:
        await self._move_with_stop_command(
            self._command_profile.foot_down,
            self._command_profile.foot_stop,
        )

    async def move_legs_stop(self) -> None:
        await self._write_control_command(
            self._command_profile.foot_stop,
            cancel_event=asyncio.Event(),
        )

    async def move_feet_up(self) -> None:
        await self.move_legs_up()

    async def move_feet_down(self) -> None:
        await self.move_legs_down()

    async def move_feet_stop(self) -> None:
        await self.move_legs_stop()

    async def stop_all(self) -> None:
        if self._command_profile.stop_all is not None:
            await self._write_control_command(
                self._command_profile.stop_all,
                cancel_event=asyncio.Event(),
            )
            return

        await self.move_head_stop()
        await self.move_legs_stop()

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------

    async def preset_flat(self) -> None:
        await self._write_optional_control_command(
            self._command_profile.preset_flat,
            "the flat preset",
        )

    async def preset_zero_g(self) -> None:
        await self._write_optional_control_command(
            self._command_profile.preset_zero_g,
            "the Zero-G preset",
        )

    async def preset_anti_snore(self) -> None:
        await self._write_optional_control_command(
            self._command_profile.preset_anti_snore,
            "the anti-snore preset",
        )

    async def preset_memory(self, memory_num: int) -> None:
        command_id = self._require_memory_command(
            self._command_profile.memory_recall,
            memory_num,
        )
        await self._write_control_command(command_id)

    async def program_memory(self, memory_num: int) -> None:
        command_id = self._require_memory_command(
            self._command_profile.memory_save,
            memory_num,
        )
        await self._write_control_command(command_id)

    # ------------------------------------------------------------------
    # Lights
    # ------------------------------------------------------------------

    async def lights_on(self) -> None:
        await self._write_optional_control_command(
            self._command_profile.light_on,
            "lights",
        )

    async def lights_off(self) -> None:
        await self._write_optional_control_command(
            self._command_profile.light_off,
            "lights",
        )

    # ------------------------------------------------------------------
    # Massage
    # ------------------------------------------------------------------

    async def massage_toggle(self) -> None:
        """Cycle through massage modes (mode 1 → 2 → 3 → off)."""
        if self._command_profile.massage_mode_1 is not None:
            await self._write_control_command(self._command_profile.massage_mode_1)
