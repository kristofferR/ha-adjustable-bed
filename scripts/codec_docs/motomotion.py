"""Bedgear tables over the shared HHC codec, from its own app profile."""

from custom_components.adjustable_bed.codec import motomotion as codec
from custom_components.adjustable_bed.profiles.bedgear import BedgearProfile
from scripts.codec_docs._common import _block, _hex, _table

GUIDE = "docs/beds/motomotion.md"
PAIRS = ("15", "35", "E1", "81", "51", "44", "91", "13", "71", "61", "D1", "34", "23", "01", "97")


def profiles() -> str:
    rows = []
    for pair in PAIRS:
        p = BedgearProfile("HHC00000" + pair + "D00X")
        rows.append(
            (
                pair,
                p.panel,
                ", ".join(axis for axis, _, _ in p.axes),
                str(p.memory_slots),
                ", ".join(key for key, _ in p.presets),
            )
        )
    return _block(
        _table(
            (
                "Panel selector example (name[8:10])",
                "Layout",
                "Motor zones",
                "Memory slots",
                "Presets",
            ),
            rows,
        )
    )


def commands() -> str:
    controls = {}
    for pair in PAIRS:
        p = BedgearProfile("HHC00000" + pair + "D00X")
        for c in p.controls:
            controls[c.key, c.letter, c.release, c.held] = None
    return _block(
        _table(
            ("Control", "Plain bytes", "M-name bytes", "Press", "Release"),
            (
                (
                    key.replace("_", " "),
                    _hex(codec.letter_command(letter)),
                    _hex(codec.letter_command(letter, wrapped=True)),
                    "100 ms refresh" if held else "once",
                    release,
                )
                for key, letter, release, held in controls
            ),
        )
    )


def timing() -> str:
    p = BedgearProfile("HHC0000001D00X")
    return _block(
        _table(
            ("Behavior", "Value"),
            (
                ("First held tick and interval", f"{p.refresh_ms} ms, no immediate write"),
                ("Motor STOP", f"{p.stop_count} writes, {p.stop_interval_ms} ms apart"),
                (
                    "Short up, fewer than five ticks and no custom up",
                    f"{p.fallback_count} extra writes, {p.refresh_ms} ms apart",
                ),
            ),
        )
    )


BLOCKS = [
    (GUIDE, "bedgear-layouts", profiles),
    (GUIDE, "bedgear-controls", commands),
    (GUIDE, "bedgear-timing", timing),
]
