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


def l2motion_layouts() -> str:
    from custom_components.adjustable_bed.profiles.l2motion import LAYOUT_EXAMPLES, L2MotionProfile

    return _block(
        _table(
            ("Name selector example", "Layout", "Motor zones", "Memory slots", "Presets"),
            (
                (
                    pair,
                    p.panel,
                    ", ".join(axis for axis, _, _ in p.axes),
                    str(p.memory_slots),
                    ", ".join(key for key, _ in p.presets),
                )
                for pair in LAYOUT_EXAMPLES
                for p in (L2MotionProfile("HHC00000" + pair + "D00X"),)
            ),
        )
    )


def l2motion_controls() -> str:
    from custom_components.adjustable_bed.profiles.l2motion import LAYOUT_EXAMPLES, L2MotionProfile

    controls = dict.fromkeys(
        c for pair in LAYOUT_EXAMPLES for c in L2MotionProfile("HHC00000" + pair + "D00X").controls
    )
    return _block(
        _table(
            ("Control", "Plain bytes", "M-name bytes", "Press", "Release"),
            (
                (
                    c.key.replace("_", " "),
                    _hex(codec.letter_command(c.letter)),
                    _hex(codec.letter_command(c.letter, wrapped=True)),
                    "Periodic"
                    if c.held
                    else "Completed tap"
                    if c.key == "light_toggle"
                    else "Once on press",
                    c.release,
                )
                for c in controls
            ),
        )
    )


def l2motion_auxiliary() -> str:
    from custom_components.adjustable_bed.beds.bedgear.music import MODES, Music
    from custom_components.adjustable_bed.profiles.l2motion import L2MotionProfile

    p = L2MotionProfile("HHC0000015DE0X")
    return _block(
        _table(
            ("Setting", "Value or frame"),
            (
                ("First periodic tick and interval", f"{p.refresh_ms} ms"),
                ("Motor release", f"{p.stop_count} writes, {p.stop_interval_ms} ms apart"),
                ("Short normal-UP filler", f"{p.fallback_count} writes, {p.refresh_ms} ms apart"),
                (
                    "Red / green / blue at full scale",
                    "; ".join(_hex(codec.ascii_command(c, 120)) for c in (315, 316, 317)),
                ),
                ("Light timer, 10 minutes", _hex(codec.ascii_command(319, 10))),
                (
                    "Synchronization on / off",
                    "; ".join(_hex(codec.ascii_command(c)) for c in (12, 15)),
                ),
                (
                    "Wireless / wired synchronization",
                    "; ".join(_hex(codec.ascii_command(33049, v)) for v in (0, 1)),
                ),
                (
                    "Alarm 06:30, strengths off / 1 / 2",
                    "; ".join(
                        _hex(codec.decimal_fields("063000", v)) for v in ("0017", "0118", "0219")
                    ),
                ),
                *(
                    (f"Initial {mode} sound, volume 11", _hex(Music().aggregate(mode)))
                    for mode in MODES
                ),
            ),
        )
    )


BLOCKS.extend(
    [
        (GUIDE, "l2motion-layouts", l2motion_layouts),
        (GUIDE, "l2motion-controls", l2motion_controls),
        (GUIDE, "l2motion-auxiliary", l2motion_auxiliary),
    ]
)
