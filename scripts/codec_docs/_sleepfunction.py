"""SleepFunction's shipped layout and direct-utility tables."""

from custom_components.adjustable_bed.beds.richmat.labels import resource_label
from custom_components.adjustable_bed.beds.richmat_classic import protocol as frames
from custom_components.adjustable_bed.beds.richmat_classic.caller import Selection, selected_operand
from custom_components.adjustable_bed.beds.richmat_classic.profiles import load_catalog
from custom_components.adjustable_bed.beds.richmat_classic.sleepfunction_settings import Settings
from custom_components.adjustable_bed.profiles.sleepfunction import (
    EXCLUDED_LAYOUTS,
    EXCLUDED_MEDIA_RESOURCES,
)
from scripts.codec_docs._common import _block, _hex, _table


def render() -> str:
    groups: dict[tuple[str, str, str, str], set[str]] = {}
    for layout, model in load_catalog("sleepfunction").models.items():
        if layout in EXCLUDED_LAYOUTS:
            continue
        for c in model.controls:
            if (
                c.status not in (1, 2, 3)
                or not c.rich_button
                or (layout, c.node) in (("FRRM", 11), ("F4RM", 4))
            ):
                continue
            if c.label.lower().endswith("rbstart"):
                continue
            if not c.short and not c.short_old and not c.long:
                continue
            short_excluded = c.resource_keys.get("press_short") in EXCLUDED_MEDIA_RESOURCES
            long_excluded = c.resource_keys.get("press_long") in EXCLUDED_MEDIA_RESOURCES
            if short_excluded and (long_excluded or c.status != 3 or not c.long):
                continue
            key = (
                resource_label(
                    c.resource_keys.get("press_long", c.label)
                    .removeprefix("@string/")
                    .replace("_", " ")
                )
                if short_excluded
                else resource_label(c.label),
                c.short or "none" if not short_excluded else "none",
                c.short_old or "none" if not short_excluded else "none",
                c.long if c.status == 3 and c.long and not long_excluded else "none",
            )
            groups.setdefault(key, set()).add(layout)
    arrows = []
    for c in load_catalog("sleepfunction").models["U3RM"].controls:
        if c.tag not in ("51", "52"):
            continue
        for motor, flag in enumerate(("53", "54", "55"), 3):
            value = selected_operand(c, "FRAMED", 1, Selection(press_flag=flag))
            assert isinstance(value, bytes)
            arrows.append(
                (
                    f"Motor {motor} {'up' if c.tag == '51' else 'down'}",
                    _hex(frames.control(value, "RAW")),
                    _hex(frames.control(value, "FRAMED")),
                )
            )
    return _block(
        _table(
            ("Control", "Framed operand", "Raw override", "Long operand", "Layouts"),
            (
                (label, short, old, long, ", ".join(sorted(layouts)))
                for (label, short, old, long), layouts in sorted(groups.items())
            ),
        ),
        _table(("U3RM control", "Raw", "Framed mode 0"), arrows),
        _table(
            ("Direct utility", "Bytes"),
            (
                ("Initialize after notifications", _hex(frames.INITIALIZE)),
                ("Release, raw", _hex(frames.release("RAW"))),
                ("Release, framed mode 0", _hex(frames.release("FRAMED"))),
                ("Alarm query", _hex(frames.ALARM_QUERY)),
                ("LED query", _hex(frames.LAMP_QUERY)),
                ("Aroma query", _hex(frames.AROMA_QUERY)),
                ("Cancel alarm", " / ".join(_hex(v) for v in frames.alarm(0, 0))),
                ("RGB green, one write", _hex(frames.rgb(0, 255, 0))),
                ("Light timeout, 300 seconds", _hex(frames.direct(11, 1, 44))),
                (
                    "Head fan, 2 hours at 40 percent",
                    " / ".join(_hex(v) for v in Settings("head_fan", hours=2, speed=40).frames()),
                ),
                (
                    "Foot fan, 40 percent",
                    " / ".join(_hex(v) for v in Settings("foot_fan", hours=2, speed=40).frames()),
                ),
            ),
        ),
    )


BLOCKS = [("docs/beds/richmat.md", "sleepfunction-commands", render)]
