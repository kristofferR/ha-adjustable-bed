"""BedSmart tables from its package-local profile and wire encoders."""

from custom_components.adjustable_bed.beds.richmat.labels import resource_label
from custom_components.adjustable_bed.beds.richmat_classic.profiles import load_catalog
from custom_components.adjustable_bed.beds.richmat_classic.protocol import (
    ALARM_QUERY,
    AROMA_QUERY,
    INITIALIZE,
    LAMP_QUERY,
    control,
    release,
)
from custom_components.adjustable_bed.codec import richmat
from custom_components.adjustable_bed.profiles.bedsmart import (
    ALARM_COMBINATIONS,
    ALIASES,
    DIAGNOSTIC_CYCLE,
    EXCLUDED_LAYOUTS,
    MODE_LABELS,
)
from scripts.codec_docs._common import _block, _table


def render() -> str:
    catalog = load_catalog("bedsmart")
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
            for layout, m in catalog.models.items()
            if layout not in EXCLUDED_LAYOUTS
            for c in m.controls
            if c.status in (1, 2, 3)
            and not c.excluded_short
            and not c.excluded_long
            and (c.short or c.short_old or c.long)
        }
    )
    return _block(
        _table(
            ("App choice", "Transport order", "Held refresh", "Long press", "Startup"),
            (
                (
                    "BedSmart / X-Series",
                    " → ".join(("w1", "w2", "n1", "w4")),
                    "150 ms; raw 6BRM 170 ms; TWRM/MLRM 110 ms",
                    "3000 ms or node threshold",
                    "Framed only, 300 ms after notifications",
                ),
            ),
        ),
        _table(("Name alias", "Layout"), sorted(ALIASES.items())),
        _table(
            ("Layout", "App selector labels, in byte order"),
            ((layout, ", ".join(labels)) for layout, labels in MODE_LABELS.items()),
        ),
        _table(
            ("Function", "Frame"),
            (
                ("Initialize", INITIALIZE.hex().upper()),
                ("Alarm query", ALARM_QUERY.hex().upper()),
                ("Light query", LAMP_QUERY.hex().upper()),
                ("Aroma query", AROMA_QUERY.hex().upper()),
                ("Raw release", release("RAW").hex().upper()),
                ("Framed release, mode 0", release("FRAMED").hex().upper()),
                ("RGB red, one write", richmat.rgb(255, 0, 0).hex().upper()),
                ("Light timeout 300 seconds", richmat.light_timer(1, 44).hex().upper()),
            ),
        ),
        _table(
            ("Alarm preset operand", "All massage", "Head massage", "Foot massage"),
            (
                (
                    f"{preset:02X}",
                    *(f"{value:02X}" if value is not None else "No write" for value in values),
                )
                for preset, values in ALARM_COMBINATIONS.items()
            ),
        ),
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
                    control(bytes.fromhex(short), "FRAMED").hex().upper() if short else "none",
                    raw or short or "none",
                    long or "none",
                    str(threshold) if status == 3 else "",
                )
                for label, status, short, raw, long, threshold in commands
            ),
        ),
        _table(
            ("Layout", "Control IDs", "Mode bytes"),
            (
                (
                    layout,
                    ", ".join(
                        str(c.node)
                        for c in model.controls
                        if c.status in (1, 2, 3) and not c.excluded_short
                    ),
                    ", ".join(map(str, model.modes)),
                )
                for layout, model in catalog.models.items()
                if layout not in EXCLUDED_LAYOUTS
            ),
        ),
        _table(
            ("Movement-test phase", "Operand", "Run, seconds", "Rest, seconds"),
            (
                (str(i), f"{code:02X}", str(seconds), "5")
                for i, (code, seconds) in enumerate(DIAGNOSTIC_CYCLE, 1)
            ),
        ),
    )


BLOCKS = [("docs/beds/richmat.md", "bedsmart-controls", render)]
