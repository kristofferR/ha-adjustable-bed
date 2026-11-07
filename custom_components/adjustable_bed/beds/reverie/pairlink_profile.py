"""Evidence-backed Pairlink manufacturer advertisement parsing."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ...discovery_hints.reverie import PAIRLINK_MANUFACTURER_IDS, PAIRLINK_MANUFACTURER_PREFIX
from .pairlink_protocol import (
    PAIRLINK_LOW_POWER_NOTIFY_UUID,
    PAIRLINK_LOW_POWER_SERVICE_UUID,
    PAIRLINK_LOW_POWER_WRITE_UUID,
)
from .pairlink_transport import (
    AdapterTransport,
    PairlinkAdvertisementProfile,
    PairlinkGattFlag,
    PairlinkGattPermission,
    PairlinkHostAdapterInventoryEntry,
    PairlinkPeripheralProfile,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

PAIRLINK_BED_TYPES = {
    144: "R510L",
    145: "Harmoniq Upgrade",
}


@dataclass(frozen=True, slots=True)
class PairlinkAdvertisement:
    """Fields the accepted P4 advertisement parser actually exposes."""

    advertisement_type: int
    bed_type: int
    model_id: str
    mesh_id: int | None = None
    head_position: int | None = None
    foot_position: int | None = None
    device_address: str | None = None
    position_12: int | None = None
    position_1: int | None = None
    position_2: int | None = None


def parse_pairlink_manufacturer_data(
    manufacturer_data: dict[int, bytes] | None,
) -> PairlinkAdvertisement | None:
    """Parse only the accepted FFFF/B905 C0 manufacturer profiles."""
    if not manufacturer_data:
        return None

    for company_id, payload in manufacturer_data.items():
        if company_id not in PAIRLINK_MANUFACTURER_IDS or not payload.startswith(
            PAIRLINK_MANUFACTURER_PREFIX
        ):
            continue
        # HA separates the little-endian company ID from Android's raw block.
        parsed = _parse_profile(company_id.to_bytes(2, "little") + payload)
        if parsed is not None:
            return parsed
    return None


def build_pairlink_peripheral_profile(
    *, home_id: int, local_join_bt_mac: bytes
) -> PairlinkPeripheralProfile:
    """Build the accepted Pairlink GATT and source-owned advertisement profile."""
    if isinstance(home_id, bool) or not isinstance(home_id, int) or not 0 <= home_id <= 0xFFFFFFFF:
        raise ValueError("Pairlink local HomeID must fit four bytes")
    if (
        type(local_join_bt_mac) is not bytes
        or len(local_join_bt_mac) != 6
        or any(octet > 0xFE for octet in local_join_bt_mac)
    ):
        raise ValueError("Pairlink local join address must contain six source-range octets")
    advertisement_payload = (
        b"\xc0\xff\x05"
        + home_id.to_bytes(4, "little")
        + local_join_bt_mac
    )
    return PairlinkPeripheralProfile(
        service_uuid=PAIRLINK_LOW_POWER_SERVICE_UUID,
        write_characteristic_uuid=PAIRLINK_LOW_POWER_WRITE_UUID,
        notify_characteristic_uuid=PAIRLINK_LOW_POWER_NOTIFY_UUID,
        write_flags=(PairlinkGattFlag.READ, PairlinkGattFlag.WRITE),
        notify_flags=(PairlinkGattFlag.READ, PairlinkGattFlag.NOTIFY),
        advertisement=PairlinkAdvertisementProfile(
            advertisement_type="peripheral",
            service_uuids=(),
            local_name=None,
            includes=(),
            manufacturer_data=((0, advertisement_payload),),
            start_delay_ms=100,
            timeout_seconds=0,
            minimum_interval_ms=100,
            maximum_interval_ms=100,
            tx_power_dbm=1,
            source_advertise_mode=2,
            source_tx_power_level=3,
            source_include_tx_power=False,
        ),
        write_read_value=b"\x44",
        notify_read_value=b"\x66",
        write_permissions=(PairlinkGattPermission.READ, PairlinkGattPermission.WRITE),
        notify_permissions=(PairlinkGattPermission.READ, PairlinkGattPermission.WRITE),
    )


def generate_pairlink_local_join_bt_mac() -> bytes:
    """Generate the source-defined six-octet local join address (00 through FE)."""
    return bytes(int(random.random() * 255) for _ in range(6))


def pairlink_host_adapter_inventory(
    hass: HomeAssistant,
) -> tuple[PairlinkHostAdapterInventoryEntry, ...]:
    """Snapshot active HA scanners with their existing transport classification."""
    from homeassistant.components import bluetooth

    from ...bluetooth_transport import TransportClass, classify_scanner

    try:
        scanners = bluetooth.async_current_scanners(hass)
    except Exception:  # noqa: BLE001 - missing inventory fails closed at selection
        return ()

    inventory: list[PairlinkHostAdapterInventoryEntry] = []
    for scanner in scanners:
        source = getattr(scanner, "source", None)
        adapter = getattr(scanner, "adapter", None)
        if not isinstance(source, str) or not source:
            continue
        match classify_scanner(scanner):
            case TransportClass.LOCAL:
                transport: AdapterTransport = "local"
            case TransportClass.PROXY:
                transport = "proxy"
            case TransportClass.UNKNOWN:
                transport = "unknown"
        inventory.append(
            PairlinkHostAdapterInventoryEntry(
                source=source,
                transport=transport,
                adapter=adapter if isinstance(adapter, str) else "",
                active=True,
            )
        )
    return tuple(inventory)


def resolve_pairlink_model(
    advertisement: PairlinkAdvertisement | None,
    foundation_name: str | None,
    selected_model: str | None = None,
) -> str:
    """Use advertisement, then the explicit profile, then the name fallback."""
    if advertisement is not None:
        return advertisement.model_id
    if selected_model in (*PAIRLINK_BED_TYPES.values(), "Other"):
        return selected_model

    normalized = (foundation_name or "").upper()
    if "R510L" in normalized:
        return "R510L"
    if "R450-HARMONIQ" in normalized or "HARMONIQ UPGRADE" in normalized:
        return "Harmoniq Upgrade"
    return "Other"


def _parse_profile(payload: bytes) -> PairlinkAdvertisement | None:
    if len(payload) < 5:
        return None

    profile_type = payload[4]
    if profile_type == 1:
        if len(payload) != 18 or payload[9] not in PAIRLINK_BED_TYPES:
            return None
        position_12 = payload[10] & 0x07
        position_1 = payload[11] & 0x0F
        position_2 = (payload[11] >> 4) & 0x0F
        if any(position > 5 for position in (position_12, position_1, position_2)):
            return None
        return PairlinkAdvertisement(
            advertisement_type=profile_type,
            bed_type=payload[9],
            model_id=PAIRLINK_BED_TYPES[payload[9]],
            mesh_id=int.from_bytes(payload[5:9], "little"),
            position_12=position_12,
            position_1=position_1,
            position_2=position_2,
            device_address=":".join(f"{value:02x}" for value in payload[12:18]),
        )

    if profile_type == 2:
        if len(payload) == 25:
            bed_type = payload[17]
            if payload[20] not in (0xA0, 0xA1):
                return None
        elif len(payload) > 25:
            bed_type = payload[25]
        else:
            return None
        if bed_type not in PAIRLINK_BED_TYPES:
            return None
        position_12 = payload[18] & 0x07
        position_1 = payload[19] & 0x0F
        position_2 = (payload[19] >> 4) & 0x0F
        if any(position > 5 for position in (position_12, position_1, position_2)):
            return None
        return PairlinkAdvertisement(
            advertisement_type=profile_type,
            bed_type=bed_type,
            model_id=PAIRLINK_BED_TYPES[bed_type],
            mesh_id=int.from_bytes(payload[5:9], "little"),
            position_12=position_12,
            position_1=position_1,
            position_2=position_2,
        )

    if profile_type == 9:
        if (
            len(payload) != 18
            or int.from_bytes(payload[11:13], "little") != 19268
            or payload[15] not in PAIRLINK_BED_TYPES
        ):
            return None
        position_12 = payload[16] & 0x07
        position_1 = payload[17] & 0x0F
        position_2 = (payload[17] >> 4) & 0x0F
        if any(position > 5 for position in (position_12, position_1, position_2)):
            return None
        return PairlinkAdvertisement(
            advertisement_type=profile_type,
            bed_type=payload[15],
            model_id=PAIRLINK_BED_TYPES[payload[15]],
            position_12=position_12,
            position_1=position_1,
            position_2=position_2,
        )

    return None
