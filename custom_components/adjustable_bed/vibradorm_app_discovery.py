"""Source-derived app discovery diagnostics, never product or target selection.

The shipped SDK selects the first manufacturer record in its raw AD list.
Home Assistant exposes a company-to-payload mapping, which cannot reconstruct
that ordering, duplicate company records, or the raw advertising Flags field.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, TypedDict

AppProfile = Literal["caresse", "werkmeister"]


class PublicVerdictDescription(TypedDict):
    status: Literal["accepted", "rejected", "unavailable"]
    reasons: list[str]


class ObservedManufacturerRecord(TypedDict):
    company_id: int
    company_accepted: bool
    payload_length: int | None
    identifier: int
    customer: int
    vib_flags: int
    sync_flag: bool
    init_flag: bool
    public_filter_if_this_were_sdk_selected: dict[AppProfile, PublicVerdictDescription]


class ManufacturerDiscoveryDiagnostics(TypedDict):
    observation_kind: str
    sdk_first_record: None
    sdk_first_record_equivalent: bool
    records: list[ObservedManufacturerRecord]
    limits: list[str]
    automatic_selection: str
    capability_inference: bool


@dataclass(frozen=True, slots=True)
class ManufacturerRecord:
    """One SDK record; payload excludes the little-endian company ID bytes."""

    company_id: int
    payload: bytes | None


@dataclass(frozen=True, slots=True)
class ManufacturerFields:
    company_id: int
    company_accepted: bool
    payload_length: int | None
    identifier: int
    customer: int
    flags: int
    sync_flag: bool
    init_flag: bool


@dataclass(frozen=True, slots=True)
class PublicFilterVerdict:
    """The public-state predicate, independent of first-target selection."""

    status: Literal["accepted", "rejected", "unavailable"]
    reasons: tuple[str, ...]


def sdk_first_manufacturer(records: Sequence[ManufacturerRecord]) -> ManufacturerRecord:
    """Select the first supplied SDK list record without sorting company IDs.

    With no records the SDK returns company -1 and an empty payload, which is
    distinct from the app parser's null-payload sentinel.
    """
    return records[0] if records else ManufacturerRecord(-1, b"")


def parse_manufacturer_record(record: ManufacturerRecord) -> ManufacturerFields:
    """Apply the exact shipped unsigned/length/high-nibble formulas."""
    payload = record.payload
    company = record.company_id & 0xFFFF
    if payload is None:
        customer = 0xFFFE
    elif len(payload) <= 6:
        customer = 0xFFFF
    elif len(payload) < 10:
        customer = 0xFFFE
    else:
        customer = int.from_bytes(payload[4:6], "big")
    identifier = (
        int.from_bytes(payload[:2], "big") if payload is not None and len(payload) >= 2 else 0
    )
    flags = (
        (payload[2] & 0xF0) | ((payload[3] & 0xF0) >> 4)
        if payload is not None and len(payload) >= 4
        else 0
    )
    return ManufacturerFields(
        company,
        company in (0x03B0, 0xFFFF),
        None if payload is None else len(payload),
        identifier,
        customer,
        flags,
        bool(flags & 0x10),
        bool(flags & 0x20),
    )


def public_filter_verdict(
    profile: AppProfile, fields: ManufacturerFields, advertising_flags: int | None
) -> PublicFilterVerdict:
    """Explain the app predicate without connecting or choosing an app/remote.

    VibFlags in manufacturer payload are not the raw AD Flags tested here.
    The Werkmeister customer gate is absent from the shipped Caresse flavor.
    """
    reasons: list[str] = []
    if not fields.company_accepted:
        reasons.append("company_not_03b0_or_ffff")
    if profile == "werkmeister" and fields.customer not in (0xFFFF, 0x0018, 0x0012):
        reasons.append("customer_not_ffff_0018_or_0012")
    if advertising_flags is not None and not advertising_flags & 1:
        reasons.append("advertising_flags_bit_01_clear")
    if reasons:
        return PublicFilterVerdict("rejected", tuple(reasons))
    if advertising_flags is None:
        return PublicFilterVerdict("unavailable", ("raw_advertising_flags_unavailable",))
    return PublicFilterVerdict("accepted", ())


def manufacturer_discovery_diagnostics(
    manufacturer_data: Mapping[int, bytes],
) -> ManufacturerDiscoveryDiagnostics:
    """Derive each observed host record, with no source-first equivalence claim."""
    records: list[ObservedManufacturerRecord] = []
    # Sorting only makes the diagnostic list stable; it does not select a record.
    for company, payload in sorted(manufacturer_data.items()):
        fields = parse_manufacturer_record(ManufacturerRecord(company, payload))
        verdicts: dict[AppProfile, PublicVerdictDescription] = {}
        for profile in ("caresse", "werkmeister"):
            verdict = public_filter_verdict(profile, fields, None)
            verdicts[profile] = {"status": verdict.status, "reasons": list(verdict.reasons)}
        records.append(
            {
                "company_id": fields.company_id,
                "company_accepted": fields.company_accepted,
                "payload_length": fields.payload_length,
                "identifier": fields.identifier,
                "customer": fields.customer,
                "vib_flags": fields.flags,
                "sync_flag": fields.sync_flag,
                "init_flag": fields.init_flag,
                "public_filter_if_this_were_sdk_selected": verdicts,
            }
        )
    return {
        "observation_kind": "ha_manufacturer_data_mapping",
        "sdk_first_record": None,
        "sdk_first_record_equivalent": False,
        "records": records,
        "limits": [
            "sdk_record_order_unavailable",
            "duplicate_company_records_not_preserved",
            "raw_advertising_flags_unavailable",
            "host_data_may_combine_advertising_and_scan_response",
        ],
        "automatic_selection": "excluded_explicit_target_and_app_profile_required",
        "capability_inference": False,
    }
