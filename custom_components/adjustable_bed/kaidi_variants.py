"""Kaidi variant selection helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .const import (
    CONF_KAIDI_PRODUCT_ID,
    CONF_KAIDI_SOFA_ACU_NO,
    CONF_PROTOCOL_VARIANT,
    KAIDI_VARIANT_SEAT_1,
    KAIDI_VARIANT_SEAT_1_2,
    KAIDI_VARIANT_SEAT_2,
    KAIDI_VARIANT_SEAT_3,
    VARIANT_AUTO,
)
from .kaidi_protocol import KaidiSeatBars, decode_kaidi_sofa_acu_no

KAIDI_MANUAL_VARIANTS: frozenset[str] = frozenset(
    {
        KAIDI_VARIANT_SEAT_1,
        KAIDI_VARIANT_SEAT_2,
        KAIDI_VARIANT_SEAT_3,
        KAIDI_VARIANT_SEAT_1_2,
    }
)

# Product IDs from the OEM APKs (Rize 1.3.0, ISleep 1.6.3, Floyd 1.0.7).
# All three apps use ONLY SEAT_* commands.  Single-base products use seat_1,
# dual-base products use seat_1 + seat_2 (seat_1_2).
#
# IDs 140-141 do not appear in any of the three APK versions and are
# intentionally omitted.  Devices with unmapped IDs fall through to the
# sofa_acu_no seat-bar heuristic or resolve to "unresolved_metadata".
#
# ID  | Name              | App         | bedUI | Classification
# ----|-------------------|-------------|-------|---------------
# 129 | BED_TYPE_SINGLE   | All         | 2     | seat_1
# 130 | BED_TYPE_DOUBLE2_4| All         | 2     | seat_1_2
# 131 | BED_TYPE_SINGLE3  | All         | 3     | seat_1
# 132 | BED_TYPE_SINGLE4  | All         | 4     | seat_1
# 133 | BED_TYPE_DOUBLE3  | All         | 3     | seat_1_2
# 134 | BED_TYPE_DOUBLE4  | All         | 4     | seat_1_2
# 135 | REMEDY_3          | Rize/Floyd  | 5     | seat_1
# 136 | REMEDY_4          | Rize/Floyd  | 6     | seat_1
# 137 | CONTEMPORARY_4    | Rize/Floyd  | 7     | seat_1
# 138 | CONTEMPORARY_5    | Rize/Floyd  | 8     | seat_1
# 139 | TRANQUILITY_II    | Floyd       | —     | seat_1
# 142 | BED_TYPE_SINGLE5  | ISleep      | 5     | seat_1
# 143 | BED_TYPE_DOUBLE_NEW | ISleep    | —     | seat_1_2
KAIDI_SINGLE_PRODUCT_IDS: frozenset[int] = frozenset(
    {129, 131, 132, 135, 136, 137, 138, 139, 142}
)
KAIDI_DOUBLE_PRODUCT_IDS: frozenset[int] = frozenset({130, 133, 134, 143})


@dataclass(frozen=True, slots=True)
class KaidiVariantResolution:
    """Result of resolving a Kaidi profile variant."""

    variant: str | None
    source: str
    product_id: int | None
    sofa_acu_no: int | None
    seat_bars: KaidiSeatBars | None


def _coerce_int(value: Any) -> int | None:
    """Return an integer value when the input is already int-like."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def resolve_kaidi_variant(
    protocol_variant: str | None,
    *,
    product_id: int | None = None,
    sofa_acu_no: int | None = None,
) -> KaidiVariantResolution:
    """Resolve the effective Kaidi command family."""
    seat_bars = decode_kaidi_sofa_acu_no(sofa_acu_no)

    if protocol_variant in KAIDI_MANUAL_VARIANTS:
        return KaidiVariantResolution(
            variant=protocol_variant,
            source="manual_override",
            product_id=product_id,
            sofa_acu_no=sofa_acu_no,
            seat_bars=seat_bars,
        )

    if product_id in KAIDI_SINGLE_PRODUCT_IDS:
        return KaidiVariantResolution(
            variant=KAIDI_VARIANT_SEAT_1,
            source="product_id",
            product_id=product_id,
            sofa_acu_no=sofa_acu_no,
            seat_bars=seat_bars,
        )

    if product_id in KAIDI_DOUBLE_PRODUCT_IDS:
        return KaidiVariantResolution(
            variant=KAIDI_VARIANT_SEAT_1_2,
            source="product_id",
            product_id=product_id,
            sofa_acu_no=sofa_acu_no,
            seat_bars=seat_bars,
        )

    if seat_bars is not None and len(seat_bars.populated_seats) == 1:
        seat_variant = {
            1: KAIDI_VARIANT_SEAT_1,
            2: KAIDI_VARIANT_SEAT_2,
            3: KAIDI_VARIANT_SEAT_3,
        }[seat_bars.populated_seats[0]]
        return KaidiVariantResolution(
            variant=seat_variant,
            source="sofa_acu_no",
            product_id=product_id,
            sofa_acu_no=sofa_acu_no,
            seat_bars=seat_bars,
        )

    if product_id is not None or sofa_acu_no is not None:
        return KaidiVariantResolution(
            variant=None,
            source="unresolved_metadata",
            product_id=product_id,
            sofa_acu_no=sofa_acu_no,
            seat_bars=seat_bars,
        )

    return KaidiVariantResolution(
        variant=KAIDI_VARIANT_SEAT_1,
        source="legacy_fallback",
        product_id=None,
        sofa_acu_no=None,
        seat_bars=None,
    )


def resolve_kaidi_variant_from_entry_data(
    entry_data: Mapping[str, Any],
    protocol_variant: str | None = None,
) -> KaidiVariantResolution:
    """Resolve a Kaidi variant from config-entry metadata."""
    return resolve_kaidi_variant(
        protocol_variant or entry_data.get(CONF_PROTOCOL_VARIANT, VARIANT_AUTO),
        product_id=_coerce_int(entry_data.get(CONF_KAIDI_PRODUCT_ID)),
        sofa_acu_no=_coerce_int(entry_data.get(CONF_KAIDI_SOFA_ACU_NO)),
    )
