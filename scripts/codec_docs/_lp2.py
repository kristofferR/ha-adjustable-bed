"""L&P Adjustable Base command and layout tables from its shipped catalog."""

from custom_components.adjustable_bed.beds.richmat.labels import resource_label
from custom_components.adjustable_bed.beds.richmat_classic.profiles import load_catalog
from custom_components.adjustable_bed.beds.richmat_classic.protocol import control
from custom_components.adjustable_bed.profiles.lp2 import (
    ALARM_COMBINATIONS,
    ALIASES,
)
from scripts.codec_docs._common import _block, _table


def render() -> str:
    catalog = load_catalog("lp2")
    commands = sorted(
        {
            (
                resource_label(c.label),
                c.status,
                c.short or "",
                c.short_old or "",
                c.long or "",
                c.threshold_ms,
            )
            for m in catalog.models.values()
            for c in m.controls
            if c.status in (1, 2, 3) and (c.short or c.short_old or c.long)
        }
    )
    return _block(
        _table(("Name / alias", "Layout"), sorted(ALIASES.items())),
        _table(("Alarm preset operand", "All massage", "Head massage", "Foot massage"), (
            (f"`{preset:02X}`", *(f"`{value:02X}`" for value in values))
            for preset, values in ALARM_COMBINATIONS.items()
        )),
        _table(
            (
                "Control",
                "Press status",
                "Framed short, mode 0",
                "Raw short",
                "Long operand",
                "Long threshold, ms",
            ),
            (
                (
                    label,
                    str(status),
                    f"`{control(bytes.fromhex(short), 'FRAMED').hex().upper()}`"
                    if short
                    else "none",
                    f"`{raw or short}`" if raw or short else "none",
                    f"`{long}`" if long else "none",
                    str(threshold) if status == 3 else "",
                )
                for label, status, short, raw, long, threshold in commands
            ),
        ),
        _table(
            ("Layout", "Control IDs", "Available modes"),
            (
                (
                    layout,
                    ", ".join(str(c.node) for c in model.controls if c.status in (1, 2, 3)),
                    ", ".join(map(str, model.modes)),
                )
                for layout, model in catalog.models.items()
            ),
        ),
    )


BLOCKS = [("docs/beds/richmat.md", "lp2-controls", render)]
