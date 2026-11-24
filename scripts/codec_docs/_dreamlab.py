"""Build Dreamlab Control's command tables from its selected layout and codec."""

from custom_components.adjustable_bed.beds.richmat_classic import protocol as frames
from custom_components.adjustable_bed.beds.richmat_classic.caller import Selection
from custom_components.adjustable_bed.beds.richmat_classic.dreamlab_controls import (
    action_name,
    gesture,
)
from custom_components.adjustable_bed.beds.richmat_classic.profiles import load_catalog
from custom_components.adjustable_bed.profiles import dreamlab as app

from ._common import Block, _block, _hex, _table

GUIDE = "docs/beds/richmat.md"


def render_setup() -> str:
    return _block(
        _table(("Advertised prefix or manual alias", "Layout"), app.ALIASES.items()),
        _table(
            ("Picker", "Configuration options"),
            ((name, ", ".join(choices)) for name, choices in app.LAYOUT_PICKERS.items()),
        ),
        _table(
            ("Layout mode", "Layout codes"),
            (("Left and Right", ", ".join(sorted(app.SIDE_LAYOUTS))),),
        ),
    )


def render_controls() -> str:
    catalog = load_catalog(app.APP)
    # Group the same named wire gesture across layouts. Model selectors,
    # program and long/hold conditions stay separate rows.
    rows: dict[tuple[str, ...], set[str]] = {}
    for layout in app.LAYOUTS:
        for control in catalog.models[layout].controls:
            selections = (
                (
                    ("Release selected", Selection(hold=False)),
                    ("Hold selected", Selection(hold=True)),
                )
                if control.hold_affected
                else (("Head selected", Selection()),)
                if control.tag == "63"
                else tuple(
                    (f"Motor {axis} selected", Selection(press_flag=flag))
                    for axis, flag in enumerate(("53", "54", "55"), 3)
                )
                if control.tag in ("51", "52")
                else (("", Selection()),)
            )
            for condition, selection in selections:
                for long in (False, True):
                    for wire in ("FRAMED", "RAW"):
                        plan = gesture(control, layout, wire, selection, long=long)
                        if plan is None:
                            continue
                        name = action_name(control, long=long, raw=wire == "RAW")
                        behavior = (
                            "Held"
                            if plan.held
                            else f"Long press, {plan.threshold_ms} ms nominal"
                            if plan.threshold_ms
                            else "Confirmed save"
                            if control.mem_special and long
                            else "One shot"
                        )
                        end = (
                            f"{plan.release_ms} ms"
                            if plan.release_ms is not None
                            else "No END on this gesture"
                        )
                        key = (
                            name,
                            condition or "Layout binding",
                            wire,
                            _hex(frames.control(plan.payload, wire)),
                            behavior,
                            end,
                        )
                        rows.setdefault(key, set()).add(layout)
    return _block(
        "Framed examples use mode zero. For another framed mode the mode and checksum bytes change.",
        "<details><summary>Layout command table</summary>",
        _table(
            ("Control", "Selector", "Wire", "Frame", "Gesture", "END delay", "Layouts"),
            ((*key, ", ".join(sorted(layouts))) for key, layouts in sorted(rows.items())),
        ),
        "</details>",
    )


def render_settings() -> str:
    return _block(
        _table(
            ("Operation", "Frame or example", "When it runs"),
            (
                (
                    "Initialize",
                    _hex(frames.INITIALIZE),
                    f"Framed, {frames.STARTUP_MS} ms after notification registration",
                ),
                ("Probe alarm", _hex(frames.ALARM_QUERY), "Layout has a raw alarm tag"),
                ("Probe light", _hex(frames.LAMP_QUERY), "Settings probe"),
                ("Probe aroma", _hex(frames.AROMA_QUERY), "Settings probe"),
                ("RGB 255,128,1", _hex(frames.rgb(255, 128, 1)), "Live LED capability; one write"),
                (
                    "Light timeout 300 s",
                    _hex(frames.direct(0x0B, 1, 44)),
                    "Live LED capability; 0 is automatic",
                ),
                (
                    "Cancel alarm",
                    " / ".join(map(_hex, frames.alarm(0, 0))),
                    "Live alarm capability",
                ),
                (
                    "TV at the same minute tomorrow",
                    " / ".join(map(_hex, frames.alarm(1440, 0x58))),
                    "TV alarm on the chosen layout",
                ),
                (
                    "Aroma 10 min, 60 min, 12 h",
                    " / ".join(
                        _hex(frames.aroma(op, value))
                        for op, value in ((0x1B, 10), (0x1C, 60), (0x1D, 12))
                    ),
                    "Live aroma capability",
                ),
                *(
                    (
                        f"Y6RM massage {'toggle' if not minutes else f'{minutes} min'}",
                        _hex(frames.control(bytes((op,)), "FRAMED")),
                        "Direct, both routes",
                    )
                    for minutes, op in app.MASSAGE_POPUP.items()
                ),
                *(
                    (
                        f"{layout} massage slider {index}",
                        _hex(frames.massage_timer(layout, index)),
                        "Direct, both routes",
                    )
                    for layout in ("D1RM", "D9RM")
                    for index in range(6)
                ),
            ),
        ),
        _table(
            ("Timing", "Interval"),
            (
                ("Default action refresh", f"{app.POLL_MS} ms"),
                ("TWRM and MLRM advertised prefix", f"{app.FAST_POLL_MS} ms"),
                ("6BRM advertised prefix on raw routes", f"{app.RAW_6BRM_POLL_MS} ms"),
                ("Between settings queries", f"{frames.QUERY_SPACING_MS} ms"),
                ("Between alarm frames", f"{frames.ALARM_SPACING_MS} ms"),
                ("Between aroma frames or after RGB preview", f"{frames.SETTINGS_SPACING_MS} ms"),
            ),
        ),
    )


BLOCKS: list[Block] = [
    (GUIDE, "dreamlab-setup", render_setup),
    (GUIDE, "dreamlab-controls", render_controls),
    (GUIDE, "dreamlab-settings", render_settings),
]
