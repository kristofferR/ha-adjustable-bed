"""Conditional app scan predicates without reconstructing lost raw AD ordering."""

from collections.abc import Mapping
from typing import TypedDict

from .beds.vmatbasic_protocol import manufacturer_payload_matches


class ConditionalManufacturerRecord(TypedDict):
    company_id: int
    payload_length: int
    matches_if_source_selected_this_record: bool


class ManufacturerDiagnostics(TypedDict):
    representation: str
    source_first_manufacturer_known: bool
    source_filter_result: None
    profile_inference: bool
    limitation: str
    conditional_records: list[ConditionalManufacturerRecord]


def manufacturer_diagnostics(records: Mapping[int, bytes]) -> ManufacturerDiagnostics:
    return {
        "representation": "Home Assistant manufacturer map, excluding company bytes",
        "source_first_manufacturer_known": False,
        "source_filter_result": None,
        "profile_inference": False,
        "limitation": "AD order, duplicate records and declared lengths are unavailable, including when the map contains one company",
        "conditional_records": [
            {
                "company_id": company,
                "payload_length": len(payload),
                "matches_if_source_selected_this_record": manufacturer_payload_matches(payload),
            }
            for company, payload in records.items()
        ],
    }
