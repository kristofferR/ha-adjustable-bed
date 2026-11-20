"""Bed Tech's effective controls and typed ranges, from its own catalog."""

from custom_components.adjustable_bed.beds.richmat_mh.app_catalog import catalog
from custom_components.adjustable_bed.codec.richmat import command

from ._common import _block, _table


def render() -> str:
    records = catalog("bedtech_classic")
    controls = sorted(
        {
            (c.route, c.kind, c.label, c.code, c.keep_ms)
            for model in records.values()
            for c in model.controls
        }
    )
    return _block(
        f"{len(records)} selectable surfaces. Controls below are offered only by surfaces that declare them; entity pages require the receiver's version and initialization replies.",
        _table(
            ("Page", "Control", "Gesture", "Mode 0 bytes", "Refresh ms"),
            [
                (
                    "Entity" if route == "C" else "Button light" if route == "B" else "Generic",
                    label,
                    kind,
                    command(code).hex(" ").upper(),
                    str(interval) if interval else "once",
                )
                for route, kind, label, code, interval in controls
            ],
        ),
        _table(
            ("Model", "Angle controls", "Massage levels"),
            [
                (
                    name.upper(),
                    "; ".join(
                        f"{label}: {low}..{high}° (display offset {offset})"
                        for _, label, low, high, offset in model.features.angles
                    ),
                    "; ".join(
                        f"{label}: {low}..{high}"
                        for _, label, low, high in model.features.intensity
                    ),
                )
                for name, model in records.items()
                if model.features.angles or model.features.intensity
            ],
        ),
    )


BLOCKS = [("docs/beds/richmat.md", "bedtech-classic-controls", render)]
