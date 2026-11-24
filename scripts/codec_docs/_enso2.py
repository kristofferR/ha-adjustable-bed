"""Render the ENSO Sleep Control profile in the Richmat guide."""

from collections import defaultdict

from custom_components.adjustable_bed.codec import richmat
from custom_components.adjustable_bed.profiles import enso2 as app
from scripts.codec_docs._common import _block, _hex, _table


def render() -> str:
    controls: dict[app.Control, list[str]] = defaultdict(list)
    for layout in app.LAYOUTS.values():
        for control in dict.fromkeys(layout.controls.values()):
            controls[control].append(layout.name)

    def frame(key: int | None, *, raw: bool = False) -> str:
        return _hex(app.key_frame(key, 0, raw=raw)) if key is not None else "—"

    def timing(control: app.Control) -> str:
        if control.behavior == "armed":
            return "Held recall or explicit save; END after 50 ms"
        if control.behavior == "selectable":
            return "Follows Press and hold / Press and release"
        if control.status == 1:
            return "Held; END after 50 ms"
        if control.status == 3:
            return f"Recall or {control.threshold_ms} ms alternate"
        return "Once; END after 150 ms"

    return _block(
        _table(
            ("Priority", "Service", "Write", "Notify", "Keys"),
            (
                *(
                    (
                        str(i),
                        f"`{route.service_uuid}`",
                        f"`{route.write_uuid}`",
                        f"`{route.notify_uuid}`",
                        "Raw" if route.single else "Framed",
                    )
                    for i, route in enumerate(app.TRANSPORTS, 1)
                ),
                (
                    "5",
                    "Third service, opt-in",
                    "Last writable",
                    "Last readable or notifiable",
                    "Raw",
                ),
            ),
        ),
        _table(
            ("Advertised alias", "Layout"),
            ((f"`{name}`", f"`{code}`") for name, code in app.ALIASES.items()),
        ),
        _table(
            (
                "Control (mode 1 frames)",
                "Framed",
                "Raw",
                "Alternate framed / raw",
                "Timing",
                "Layouts",
            ),
            (
                (
                    control.label
                    if control.raw_label is None
                    else f"{control.label} / {control.raw_label} (raw)",
                    frame(control.framed),
                    frame(control.raw, raw=True),
                    f"{frame(control.alternate)} / {frame(control.alternate, raw=True)}"
                    if control.alternate is not None
                    else "—",
                    timing(control),
                    ", ".join(layouts),
                )
                for control, layouts in controls.items()
            ),
        ),
        _table(
            ("Setting", "Example frames", "Gate"),
            (
                ("Startup", _hex(app.INIT), "Framed receiver only, 300 ms after subscription"),
                ("Alarm query", _hex(app.ALARM_QUERY), "Current layout has alarm tags"),
                ("LED query", _hex(app.LED_QUERY), "Every layout"),
                ("Aroma query", _hex(app.AROMA_QUERY), "Every layout"),
                ("LED color #123456", _hex(richmat.rgb(0x12, 0x34, 0x56)), "LED reply"),
                ("LED auto-off, 300 seconds", _hex(richmat.light_timer(1, 44)), "LED reply"),
                (
                    "Aroma times 60 min, 1 min, 12 h",
                    " / ".join(map(_hex, app.aroma_frames(60, 1, 12))),
                    "Aroma reply",
                ),
                (
                    "Alarm countdown, 1440 minutes, zero gravity",
                    " / ".join(map(_hex, richmat.countdown(1440, 0x45))),
                    "Alarm menu and layout choice",
                ),
                *(
                    (
                        f"{layout} timer",
                        " / ".join(_hex(app.massage_timer_frame(layout, item)) for item in values),
                        "Layout",
                    )
                    for layout, values in (
                        ("Y6RM", (0, 15, 30, 45)),
                        ("D1RM", range(6)),
                        ("D9RM", range(6)),
                    )
                ),
            ),
        ),
        _table(
            ("Alarm action", "Key", "With both / head / foot massage", "Layouts"),
            (
                (
                    action,
                    f"`{key:02X}`",
                    " / ".join(f"`{code:02X}`" for code in app.ALARM_COMBINED.get(key, ())) or "—",
                    ", ".join(
                        layout.name for layout in app.LAYOUTS.values() if key in layout.alarm_tags
                    ),
                )
                for action, key in {**app.ALARM_ACTIONS, **app.ALARM_MASSAGE}.items()
            ),
        ),
    )
