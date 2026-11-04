"""Generated blocks of ``docs/CONFIGURATION.md``, which spans every family.

The driver adds these ``BLOCKS`` to the family modules' blocks; the module is
private so the codec docs tests do not treat it as a family.
"""

from __future__ import annotations

from custom_components.adjustable_bed.const import (
    DEFAULT_MOTOR_PULSE_COUNT,
    DEFAULT_MOTOR_PULSE_DELAY_MS,
    SUPPORTED_BED_TYPES,
    get_motor_pulse_defaults,
)
from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES
from custom_components.adjustable_bed.validators import get_variants_for_bed_type
from scripts.codec_docs._common import Block, _block, _table

GUIDE = "docs/CONFIGURATION.md"


def _rows() -> list[tuple[str, str, str, str]]:
    """Every bed type, or protocol variant, whose pulse defaults are not the shared ones."""
    shared = (DEFAULT_MOTOR_PULSE_COUNT, DEFAULT_MOTOR_PULSE_DELAY_MS)
    rows = []
    for bed_type in SUPPORTED_BED_TYPES:
        name = BED_TYPE_DISPLAY_NAMES.get(bed_type, bed_type)
        defaults = get_motor_pulse_defaults(bed_type)
        if defaults != shared:
            rows.append((name, f"`{bed_type}`", *defaults))
        for variant, label in (get_variants_for_bed_type(bed_type) or {}).items():
            if (variant_defaults := get_motor_pulse_defaults(bed_type, variant)) != defaults:
                rows.append((f"{name}: {label}", f"`{bed_type}` `{variant}`", *variant_defaults))
    return [
        (name, key, str(count), f"{delay} ms")
        for name, key, count, delay in sorted(rows, key=lambda row: row[0].casefold())
    ]


def pulse_defaults() -> str:
    return _block(
        _table(("Bed type", "Key", "Pulse count", "Pulse delay"), _rows()),
        f"Every other bed type defaults to {DEFAULT_MOTOR_PULSE_COUNT} pulses"
        f" {DEFAULT_MOTOR_PULSE_DELAY_MS} ms apart.",
    )


BLOCKS: list[Block] = [(GUIDE, "pulse-defaults", pulse_defaults)]
