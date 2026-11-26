"""The ABM10 and no-product fallback in Likimio 1.0.2."""

from dataclasses import replace
from typing import Final

from ..const import VARIANT_AUTO
from . import dreamsense

ABM10: Final = "ABM10"
NO_PRODUCT: Final = "no_product"
SCAN_WORDS: Final = ("QRRM", "COOL", "MPE_", "209A", "BED-")

# The frozen Likimio vectors match this ABM10 control catalog on all six routes.
PROFILES: Final = {
    ABM10: replace(dreamsense.PROFILES[ABM10], normal=True),
    NO_PRODUCT: replace(
        dreamsense.PROFILES[ABM10], product=NO_PRODUCT, remote="", controls=(), light=False
    ),
}
CHOICES: Final = {ABM10: ABM10, NO_PRODUCT: "No product (cancel alarm only)"}


def product_for_variant(variant: str | None) -> str:
    """An unspecified HA entry uses Likimio's sole normal product."""
    return ABM10 if variant is None or variant == VARIANT_AUTO else variant
