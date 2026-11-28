"""Generate TSS Remote's package-owned setup, gestures and direct builders."""

from custom_components.adjustable_bed.beds.richmat_classic import protocol as p
from custom_components.adjustable_bed.beds.richmat_classic.caller import Selection
from custom_components.adjustable_bed.beds.richmat_classic.profiles import load_catalog
from custom_components.adjustable_bed.beds.richmat_classic.tss_remote_controls import name, plan
from custom_components.adjustable_bed.profiles import tss_remote as app

from ._common import Block, _block, _hex, _table

GUIDE = "docs/beds/richmat.md"


def setup() -> str:
    return _block(
        _table(("Alias in the app resolver", "Layout"), app.ALIASES.items()),
        _table(
            ("Chooser", "Configuration choices"),
            ((menu, ", ".join(layouts)) for menu, layouts in app.NAVIGATION.items()),
        ),
        _table(
            ("Rule", "Value"),
            (
                (
                    "Layouts with bed controls",
                    ", ".join(code for code in app.LAYOUTS if code not in app.NAVIGATION),
                ),
                ("Connection timeout", f"{app.CONNECTION_TIMEOUT_S:g} seconds"),
                ("Ordinary repeat", f"{app.poll_interval(None, raw=False)} ms"),
                ("Actual TWRM or MLRM name", f"{app.poll_interval('TWRM', raw=False)} ms"),
                ("Actual 6BRM name, Nordic", f"{app.poll_interval('6BRM', raw=True)} ms"),
                (
                    "Initialize",
                    f"{app.RUNTIME.startup_ms} ms after notification registration; framed only",
                ),
                ("Settings probes", f"{app.RUNTIME.query_spacing_ms} ms apart"),
                ("Split alarm", f"{app.RUNTIME.alarm_spacing_ms} ms apart"),
                ("RGB busy interval", f"{app.RUNTIME.rgb_spacing_ms} ms"),
            ),
        ),
    )


def controls() -> str:
    rows: dict[tuple[str, ...], set[str]] = {}
    for layout in app.LAYOUTS:
        for button in load_catalog(app.APP).models[layout].controls:
            selections = (
                (("Release", Selection(hold=False)), ("Hold", Selection(hold=True)))
                if button.hold_affected
                else (("", Selection()),)
            )
            if button.tag in ("51", "52"):
                selections = tuple(
                    (f"Stored selector {flag}", Selection(press_flag=flag))
                    for flag in ("53", "54", "55")
                )
            for condition, selected in selections:
                for long in (False, True):
                    for wire in ("RAW", "FRAMED"):
                        gesture = plan(button, layout, wire, selected, long=long)
                        if gesture is None:
                            continue
                        label = name(button, layout, long=long, raw=wire == "RAW")
                        label = label or "Diagnostic only: " + button.label
                        key = (
                            label,
                            condition or "Layout binding",
                            wire,
                            _hex(p.control(gesture.payload, wire)),
                            "Repeat" if gesture.held else "Long press" if long else "Once",
                            str(gesture.threshold_ms),
                            str(gesture.release_ms),
                        )
                        rows.setdefault(key, set()).add(layout)
    return _block(
        "Framed examples use mode zero. Other modes change the mode byte and checksum.",
        "<details><summary>Complete layout command table</summary>",
        _table(
            (
                "Control",
                "Selection",
                "Route",
                "Frame",
                "Gesture",
                "Nominal threshold (ms)",
                "END delay (ms)",
                "Layouts",
            ),
            ((*key, ", ".join(sorted(layouts))) for key, layouts in sorted(rows.items())),
        ),
        "</details>",
    )


def settings() -> str:
    timers: dict[tuple[str, tuple[int, ...]], list[str]] = {}
    for layout in app.LAYOUTS:
        for wire in ("RAW", "FRAMED"):
            minutes = {
                value for button in load_catalog(app.APP).models[layout].controls
                for long in (False, True)
                if (value := app.FIXED_MASSAGE_DURATIONS.get(name(button, layout, long=long, raw=wire == "RAW"))) is not None
                and plan(button, layout, wire, Selection(), long=long) is not None
            }
            if minutes:
                timers.setdefault((wire, tuple(sorted(minutes))), []).append(layout)
    return _block(
        _table(
            ("Fixed massage timer select (minutes)", "Route", "Layouts"),
            ((", ".join(map(str, minutes)), wire, ", ".join(layouts))
             for (wire, minutes), layouts in sorted(timers.items())),
        ),
        _table(
            ("Operation", "Frame or example", "Availability"),
            (
                ("Initialize", _hex(p.INITIALIZE), "Framed route, notifications enabled"),
                ("Probe alarm", _hex(p.ALARM_QUERY), "Layout contains alarm options"),
                ("Probe lighting", _hex(p.LAMP_QUERY), "Refresh bed features"),
                ("RGB (0,255,0)", _hex(p.rgb(0, 255, 0)), "Fresh lighting presence reply"),
                (
                    "Light timeout 300 seconds",
                    _hex(p.direct(0x0B, 1, 44)),
                    "Fresh lighting presence reply",
                ),
                (
                    "Cancel alarm",
                    " / ".join(map(_hex, p.alarm(0, 0))),
                    "Direct alarm control or fresh alarm reply",
                ),
                (
                    "Zero gravity, same minute tomorrow",
                    " / ".join(map(_hex, p.alarm(1440, 0x45))),
                    "Layout offers this alarm preset",
                ),
                *(
                    (
                        f"Popup: {minutes} min" if minutes else "Popup: toggle massage",
                        _hex(p.control(bytes((opcode,)), "FRAMED")),
                        "Y6RM",
                    )
                    for minutes, opcode in app.MASSAGE_POPUP.items()
                ),
                *(
                    (f"Slider: {minutes} min", _hex(p.massage_timer(layout, stop)), layout)
                    for layout in ("D1RM", "D9RM")
                    for minutes, stop in app.SLIDER_MINUTES.items()
                ),
            ),
        ),
        _table(
            ("Alarm preset", "With all massage", "With head massage", "With foot massage"),
            (
                (_hex(bytes((preset,))), *(_hex(bytes((code,))) for code in combos))
                for preset, combos in app.ALARM_COMBINATIONS.items()
            ),
        ),
    )


BLOCKS: list[Block] = [
    (GUIDE, "tss-remote-setup", setup),
    (GUIDE, "tss-remote-controls", controls),
    (GUIDE, "tss-remote-settings", settings),
]
