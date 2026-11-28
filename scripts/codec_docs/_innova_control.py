"""Innova Control tables from its package-local catalog and shared encoders."""

from custom_components.adjustable_bed.beds.richmat_classic import protocol as p
from custom_components.adjustable_bed.beds.richmat_classic.profiles import load_catalog
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles import innova_control as profile
from scripts.codec_docs._common import _block, _hex, _table


def render() -> str:
    groups: dict[tuple[str, ...], list[str]] = {}
    for layout, model in load_catalog(profile.APP).models.items():
        if layout in profile.EXCLUDED_LAYOUTS:
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
            operands = (
                None if c.excluded_short else c.short,
                None if c.excluded_short else c.short_old,
                c.long if c.status == 3 and not c.excluded_long else None,
            )
            if any(operands):
                groups.setdefault(
                    (
                        c.label,
                        *(v or "none" for v in operands),
                        str(c.status),
                        str(c.threshold_ms),
                        c.alarm_clock or "none",
                    ),
                    [],
                ).append(f"{layout}:{c.node}")
    return _block(
        _table(
            ("Setting", "Value or frame"),
            [
                (
                    "Selectable bed layouts",
                    ", ".join(
                        code for code in profile.LAYOUTS if code not in profile.EXCLUDED_LAYOUTS
                    ),
                ),
                ("Aliases", "; ".join(f"{a}: {b}" for a, b in profile.ALIASES.items())),
                (
                    "Refresh, normal / TWRM and MLRM / raw 6BRM",
                    f"{p.TICK_MS} / {p.FAST_TICK_MS} / 170 ms",
                ),
                (
                    "Release, held / tapped",
                    f"{profile.PROFILE.held_release_ms} / {profile.PROFILE.tap_release_ms} ms",
                ),
                ("Default long threshold", f"{profile.PROFILE.long_press_ms} ms"),
                ("Initialization, after notification success", _hex(p.INITIALIZE)),
                (
                    "Alarm / light / aroma capability queries",
                    "; ".join(_hex(v) for v in (p.ALARM_QUERY, p.LAMP_QUERY, p.AROMA_QUERY)),
                ),
                ("Light timeout, 300 seconds", _hex(codec.light_timer(1, 44))),
                ("RGB 18, 52, 86 (one write)", _hex(codec.rgb(18, 52, 86))),
                (
                    "Alarm, 1440 minutes to TV",
                    "; ".join(_hex(v) for v in codec.countdown(1440, 0x58)),
                ),
                (
                    "Grouping / leave",
                    _hex(codec.local_group("1234")) + " / " + _hex(codec.local_group(None)),
                ),
            ],
        ),
        "\n<details><summary>Layout controls and operands</summary>\n\n",
        _table(
            (
                "Layout:node",
                "Resource",
                "Short",
                "Raw old short",
                "Long",
                "Status",
                "Long threshold ms",
                "Alarm operand",
            ),
            [(", ".join(bindings), *key) for key, bindings in sorted(groups.items())],
        ),
        "\n</details>\n",
    )
