"""Validation and configuration helpers for Adjustable Bed integration."""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.core import HomeAssistant

from .const import (
    ADAPTER_AUTO,
    BED_TYPE_KEESON,
    BED_TYPE_LEGGETT_PLATT,
    BED_TYPE_OCTO,
    BED_TYPE_OKIMAT,
    BED_TYPE_OKIN_64BIT,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_RICHMAT,
    KEESON_VARIANTS,
    LEGGETT_VARIANTS,
    OCTO_VARIANTS,
    OKIMAT_VARIANTS,
    OKIN_64BIT_VARIANTS,
    RICHMAT_VARIANTS,
    VARIANT_AUTO,
)

_LOGGER = logging.getLogger(__name__)

# MAC address regex pattern (XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX)
MAC_ADDRESS_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")


def is_valid_mac_address(address: str) -> bool:
    """Validate a MAC address format."""
    return bool(MAC_ADDRESS_PATTERN.match(address))


def normalize_octo_pin(pin: Any | None) -> str:
    """Normalize Octo PIN input to a clean string."""
    if pin is None:
        return ""
    return str(pin).strip()


def is_valid_octo_pin(pin: str) -> bool:
    """Return True if PIN is empty or exactly 4 digits."""
    return pin == "" or (len(pin) == 4 and pin.isdigit())


# Single source of truth for bed types with variants
VARIANTS_BY_BED_TYPE: dict[str, dict[str, str]] = {
    BED_TYPE_KEESON: KEESON_VARIANTS,
    BED_TYPE_LEGGETT_PLATT: LEGGETT_VARIANTS,
    BED_TYPE_RICHMAT: RICHMAT_VARIANTS,
    BED_TYPE_OCTO: OCTO_VARIANTS,
    BED_TYPE_OKIMAT: OKIMAT_VARIANTS,
    BED_TYPE_OKIN_UUID: OKIMAT_VARIANTS,  # Same remote variants as Okimat
    BED_TYPE_OKIN_64BIT: OKIN_64BIT_VARIANTS,
}


def get_variants_for_bed_type(bed_type: str | None) -> dict[str, str] | None:
    """Get available protocol variants for a bed type, or None if no variants."""
    if bed_type is None:
        return None
    return VARIANTS_BY_BED_TYPE.get(bed_type)


def bed_type_has_variants(bed_type: str) -> bool:
    """Check if a bed type has multiple protocol variants."""
    return bed_type in VARIANTS_BY_BED_TYPE


def is_valid_variant_for_bed_type(bed_type: str, variant: str) -> bool:
    """Check if a protocol variant is valid for a given bed type."""
    if variant == VARIANT_AUTO:
        return True
    valid_variants = get_variants_for_bed_type(bed_type)
    return valid_variants is not None and variant in valid_variants


def get_available_adapters(hass: HomeAssistant) -> dict[str, str]:
    """Get available Bluetooth adapters/proxies."""
    adapters: dict[str, str] = {ADAPTER_AUTO: "Automatic (let Home Assistant choose)"}

    try:
        from homeassistant.components.bluetooth import async_current_scanners

        for scanner in async_current_scanners(hass):
            source = getattr(scanner, "source", None)
            name = getattr(scanner, "name", None)
            if not source:
                continue
            if source not in adapters:
                if name and name != source:
                    # Avoid duplicating MAC if it's already in the name
                    if source in name:
                        adapters[source] = name
                    else:
                        adapters[source] = f"{name} ({source})"
                elif ":" in source:
                    adapters[source] = f"Bluetooth Proxy ({source})"
                else:
                    adapters[source] = f"Local Adapter ({source})"
    except ImportError:
        _LOGGER.debug("async_current_scanners not available")
    except Exception as err:
        _LOGGER.debug("Could not get scanner names: %s", err)

    _LOGGER.debug("Available Bluetooth adapters: %s", adapters)
    return adapters
