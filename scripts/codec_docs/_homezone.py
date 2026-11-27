"""Home Zone profile tables from its own catalog and the Richmat encoders."""

from custom_components.adjustable_bed.beds.richmat_classic import protocol as p
from custom_components.adjustable_bed.beds.richmat_classic.profiles import load_catalog
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles import homezone
from scripts.codec_docs._common import _block, _hex, _table


def render() -> str:
    models = load_catalog(homezone.APP).models
    groups: dict[tuple[str, ...], list[str]] = {}
    for layout, model in models.items():
        if layout in homezone.EXCLUDED_LAYOUTS:
            continue
        for c in model.controls:
            if (
                not c.rich_button
                or c.status not in (1, 2, 3)
                or c.view_id in ("btnRelease", "btnHold")
                or c.tag in ("61", "62", "65")
            ):
                continue
            if c.status == 2 and c.short is None and c.short_old is None:
                continue
            operands = [
                c.short if not c.excluded_short else None,
                c.short_old if not c.excluded_short else None,
                c.long if c.status == 3 and not c.excluded_long else None,
            ]
            if not any(operands):
                continue
            key = (c.label, *(v or "none" for v in operands), str(c.status), str(c.threshold_ms))
            groups.setdefault(key, []).append(f"{layout}:{c.node}")
    return _block(
        _table(
            ("Setting", "Frame"),
            [
                ("Initialization", _hex(p.INITIALIZE)),
                ("Alarm query", _hex(p.ALARM_QUERY)),
                ("Light query", _hex(p.LAMP_QUERY)),
                ("Aroma query", _hex(p.AROMA_QUERY)),
                ("Light timeout, 300 seconds", _hex(codec.light_timer(1, 44))),
                ("RGB, green", _hex(p.rgb(0, 255, 0))),
            ],
        ),
        "\n<details><summary>Layout controls and operands</summary>\n\n",
        _table(
            (
                "Layout:control",
                "Resource",
                "Short",
                "Raw old short",
                "Long",
                "Status",
                "Long threshold ms",
            ),
            [(", ".join(bindings), *key) for key, bindings in sorted(groups.items())],
        ),
        "\n</details>\n",
    )
