"""Kaidi variant selection helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .const import (
    CONF_KAIDI_PRODUCT_ID,
    CONF_KAIDI_SOFA_ACU_NO,
    CONF_PROTOCOL_VARIANT,
    KAIDI_VARIANT_BED_1,
    KAIDI_VARIANT_BED_12,
    KAIDI_VARIANT_BED_2,
    KAIDI_VARIANT_SEAT_1,
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
        KAIDI_VARIANT_BED_1,
        KAIDI_VARIANT_BED_2,
        KAIDI_VARIANT_BED_12,
    }
)

# Product IDs exposed by the OEM APKs as explicit bed types.
# `MainActivity.getProductId()` only returns these IDs directly for the Kaidi
# bed family; everything else is either a sofa-style type (100-102) or `0`.
KAIDI_SINGLE_PRODUCT_IDS: frozenset[int] = frozenset({129, 131, 132, 142})
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
            variant=KAIDI_VARIANT_BED_12,
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
