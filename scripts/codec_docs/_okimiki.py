"""Okimiki 1.0.1's product and gesture tables."""

from custom_components.adjustable_bed.profiles.okimiki import (
    CONTROLS,
    LIGHT_DELAY_S,
    PRODUCTS,
    QUERY_S,
    SAVE_S,
    TICK_S,
)
from scripts.codec_docs._common import _block, _table


def products() -> str:
    return _block(
        _table(
            ("Product", "Axes", "Memory slots", "Alarm", "Light"),
            (
                (
                    key,
                    "head, foot",
                    str(row.memory_slots),
                    row.alarm,
                    "RGB/timer after capability reply",
                )
                for key, row in PRODUCTS.items()
            ),
        )
    )


def controls() -> str:
    return _block(
        _table(
            ("Control", "Recall byte", "Save byte", "Gesture"),
            (
                (
                    key,
                    f"`{row.opcode:02X}`",
                    f"`{row.save:02X}`" if row.save is not None else "none",
                    "100 ms held refresh, then STOP"
                    if row.held
                    else "save at 3 s, recall on early release"
                    if row.save is not None
                    else "flat on down, STOP on release",
                )
                for key, row in CONTROLS.items()
            ),
        )
    )


def timing() -> str:
    return _block(
        _table(
            ("Operation", "Interval"),
            (
                ("Held refresh and FIFO", f"{TICK_S * 1000:g} ms"),
                ("Save threshold", f"{SAVE_S:g} s"),
                ("Menu query spacing", f"{QUERY_S * 1000:g} ms"),
                ("Light duration delay", f"{LIGHT_DELAY_S * 1000:g} ms"),
            ),
        )
    )


BLOCKS = [
    ("docs/beds/richmat.md", "okimiki-products", products),
    ("docs/beds/richmat.md", "okimiki-controls", controls),
    ("docs/beds/richmat.md", "okimiki-timing", timing),
]
