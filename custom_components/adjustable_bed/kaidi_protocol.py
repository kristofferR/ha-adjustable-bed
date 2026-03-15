"""Helpers for Kaidi's custom mesh-over-GATT bed protocol.

The Rize/Floyd/ISleep Android apps use a proprietary transport layered on top
of normal BLE GATT characteristics instead of the Bluetooth Mesh SIG profile.
Home Assistant only needs a subset of that logic:
- Parse the manufacturer data blob to recover the room/home ID and, when
  available, the bed's virtual address.
- Format node addresses reported in ping responses.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

KAIDI_ADV_MARKER = b"\xff\xff\xc0\xff"
KAIDI_STRIPPED_ADV_MARKER = b"\xc0\xff"

KAIDI_ADV_TYPE_SINGLE = 0x01
KAIDI_ADV_TYPE_BROADCAST = 0x02
KAIDI_ADV_TYPE_DISCOVERABLE = 0x09

KAIDI_INTERNAL_COMPANY_ID = 0x4B44


@dataclass(frozen=True)
class KaidiAdvertisement:
    """Parsed Kaidi advertisement payload."""

    adv_type: int
    room_id: int | None = None
    vaddr: int | None = None
    sofa_type: int | None = None
    company_id: int | None = None


def _le_u16(data: bytes) -> int:
    """Parse a little-endian 16-bit integer."""
    return int.from_bytes(data[:2], "little")


def _le_u32(data: bytes) -> int:
    """Parse a little-endian 32-bit integer."""
    return int.from_bytes(data[:4], "little")


def normalize_kaidi_manufacturer_payload(payload: bytes) -> bytes | None:
    """Normalize a Kaidi manufacturer payload to include the company ID prefix.

    Home Assistant exposes manufacturer data values without the BLE Company ID,
    while the Android app receives the full manufacturer-specific AD structure
    payload including the leading `0xFFFF` Company ID. Accept both forms so the
    parser can be reused in tests, detection, and the controller.
    """

    if payload.startswith(KAIDI_ADV_MARKER):
        return payload
    if payload.startswith(KAIDI_STRIPPED_ADV_MARKER):
        return b"\xff\xff" + payload
    return None


def is_kaidi_manufacturer_payload(payload: bytes) -> bool:
    """Return True when the payload matches Kaidi's manufacturer blob."""
    return normalize_kaidi_manufacturer_payload(payload) is not None


def parse_kaidi_manufacturer_payload(payload: bytes) -> KaidiAdvertisement | None:
    """Parse a Kaidi manufacturer payload from BLE advertisements."""
    normalized = normalize_kaidi_manufacturer_payload(payload)
    if normalized is None or len(normalized) < 5:
        return None

    adv_type = normalized[4]

    if adv_type == KAIDI_ADV_TYPE_SINGLE:
        if len(normalized) < 18:
            return None
        return KaidiAdvertisement(
            adv_type=adv_type,
            room_id=_le_u32(normalized[5:9]),
            sofa_type=normalized[9],
        )

    if adv_type == KAIDI_ADV_TYPE_BROADCAST:
        if len(normalized) < 25:
            return None

        sofa_type: int | None = None
        if len(normalized) >= 21 and normalized[20] in (0xA0, 0xA1):
            sofa_type = normalized[17]
        elif len(normalized) >= 28:
            sofa_type = normalized[25]

        return KaidiAdvertisement(
            adv_type=adv_type,
            room_id=_le_u32(normalized[5:9]),
            vaddr=_le_u32(normalized[21:25]),
            sofa_type=sofa_type,
        )

    if adv_type == KAIDI_ADV_TYPE_DISCOVERABLE:
        if len(normalized) < 18:
            return None
        return KaidiAdvertisement(
            adv_type=adv_type,
            company_id=_le_u16(normalized[11:13]),
            sofa_type=normalized[15],
        )

    return KaidiAdvertisement(adv_type=adv_type)


def extract_kaidi_advertisement(
    manufacturer_data: dict[int, bytes] | None,
) -> KaidiAdvertisement | None:
    """Extract the first Kaidi advertisement payload from manufacturer data."""
    if not manufacturer_data:
        return None

    for payload in manufacturer_data.values():
        parsed = parse_kaidi_manufacturer_payload(bytes(payload))
        if parsed is not None:
            return parsed
    return None


def _kaidi_adv_rank(adv_type: int) -> int:
    """Rank advertisement types by how much session metadata they carry."""
    if adv_type == KAIDI_ADV_TYPE_BROADCAST:
        return 3
    if adv_type == KAIDI_ADV_TYPE_SINGLE:
        return 2
    if adv_type == KAIDI_ADV_TYPE_DISCOVERABLE:
        return 1
    return 0


def merge_kaidi_advertisements(
    advertisements: Iterable[KaidiAdvertisement | None],
) -> KaidiAdvertisement | None:
    """Merge multiple Kaidi advertisement snapshots into the best available state."""
    merged: KaidiAdvertisement | None = None

    for advertisement in advertisements:
        if advertisement is None:
            continue
        if merged is None:
            merged = advertisement
            continue

        adv_type = (
            advertisement.adv_type
            if _kaidi_adv_rank(advertisement.adv_type) > _kaidi_adv_rank(merged.adv_type)
            else merged.adv_type
        )
        merged = KaidiAdvertisement(
            adv_type=adv_type,
            room_id=merged.room_id if merged.room_id is not None else advertisement.room_id,
            vaddr=merged.vaddr if merged.vaddr is not None else advertisement.vaddr,
            sofa_type=merged.sofa_type if merged.sofa_type is not None else advertisement.sofa_type,
            company_id=(
                merged.company_id
                if merged.company_id is not None
                else advertisement.company_id
            ),
        )

    return merged


def extract_best_kaidi_advertisement(
    manufacturer_data_sets: Iterable[dict[int, bytes] | None],
) -> KaidiAdvertisement | None:
    """Parse and merge multiple manufacturer-data snapshots for one Kaidi device."""
    return merge_kaidi_advertisements(
        extract_kaidi_advertisement(manufacturer_data)
        for manufacturer_data in manufacturer_data_sets
    )


def format_kaidi_node_address(node_bytes: bytes) -> str:
    """Format a 6-byte Kaidi node address as an upper-case MAC string."""
    if len(node_bytes) != 6:
        raise ValueError(f"Kaidi node address must be 6 bytes, got {len(node_bytes)}")
    return ":".join(f"{byte:02X}" for byte in reversed(node_bytes))
