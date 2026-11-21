"""VMAT advertisement parsing and precision limits, never app selection."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class VmatManufacturer:
    company: int = -1
    identifier: int = -1
    revision: int = -1
    flags: int = -1
    is_vib_device: bool = False
    teach_mode: bool = False
    gid: int = -1
    sgid: int = -1
    customer: int = -1


def parse_vmat_manufacturer(payload: bytes | None) -> VmatManufacturer:
    """Decode the complete source manufacturer payload, including company ID."""
    customer = -1 if payload is None else (
        0xFFFF if len(payload) < 10 else int.from_bytes(payload[8:10], "big")
    )
    if payload is None or len(payload) < 2:
        return VmatManufacturer(customer=customer)
    company = int.from_bytes(payload[:2], "little")
    if len(payload) < 6:
        return VmatManufacturer(company=company, is_vib_device=company == 0x03B0, customer=customer)
    raw_identifier = int.from_bytes(payload[2:4], "big")
    identifier = raw_identifier if raw_identifier == 0xBABE else payload[2] >> 4
    is_vib_device = company == 0x03B0 or company == 0xFFFF and identifier == 0xBABE
    if company in (0x03B0, 0xFFFF) and identifier == 0xBABE:
        revision = 3
        flags = (payload[4] & 0xF0) | ((payload[5] & 0xF0) >> 4)
        sgid = payload[5] & 0x0F
    elif company == 0x03B0 and identifier in (0, 1):
        revision = 4 + identifier
        flags = ((payload[2] & 0x0F) << 12) | (payload[3] << 4) | (payload[4] >> 4)
        sgid = payload[5] - 256 if payload[5] >= 128 else payload[5]
    else:
        return VmatManufacturer(
            company=company, identifier=identifier, is_vib_device=is_vib_device,
            gid=payload[4] & 0x0F if is_vib_device else -1, customer=customer,
        )
    return VmatManufacturer(
        company, identifier, revision, flags, True,
        revision >= 4 and bool(flags & 8), payload[4] & 0x0F, sgid, customer,
    )


def vmat_manufacturer_diagnostics(manufacturer_data: Mapping[int, bytes]) -> dict[str, object]:
    return {
        "observation_kind": "ha_manufacturer_data_mapping",
        "records": [
            asdict(parse_vmat_manufacturer(company.to_bytes(2, "little") + payload))
            for company, payload in sorted(manufacturer_data.items())
        ],
        "raw_teach_input_available": False,
        "limits": [
            "raw_advertising_flags_unavailable", "source_record_order_unavailable",
            "duplicate_company_records_not_preserved",
            "host_data_may_combine_advertising_and_scan_response",
        ],
        "automatic_selection": "explicit_address_and_app_remote_required",
        "capability_inference": False,
    }
