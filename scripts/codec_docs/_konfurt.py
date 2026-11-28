"""KONFURT reference tables from its independent profile and Keeson codec."""

from custom_components.adjustable_bed.codec import keeson as codec
from custom_components.adjustable_bed.profiles import konfurt as app
from scripts.codec_docs._common import _hex, _table


def render() -> str:
    layouts = _table(("Layout", "Actuators", "Held controls", "Refresh", "Release offsets"), (
        (key, ", ".join(layout.axes), ", ".join(layout.controls),
         f"{app.REFRESH_MS} ms", "/".join(map(str, app.RELEASE_MS)) + " ms")
        for key, layout in app.LAYOUTS.items()
    ))
    rows = [(key, control, _hex(app.frame(control, layout)))
            for key, layout in app.LAYOUTS.items() for control in (*layout.controls, "stop")]
    commands = _table(("Layout", "Control", "Frame"), rows)
    gatt = _table(("Role", "Service", "Characteristic"), (
        ("Write", app.WRITE_SERVICE, app.WRITE),
        ("Notify", app.NOTIFY_SERVICE, app.NOTIFY),
    ))
    alarm = _table(("Alarm operation", "Frame", "Timing"), (
        ("Refresh", _hex(app.ALARM_QUERY), "/".join(map(str, app.QUERY_MS)) + " ms"),
        ("Clock", _hex(codec.clock_fields((126, 10, 27, 16, 21, 22))), "example 2026-11-27 16:21:22, before enable"),
        *((wake, _hex(app.alarm(7, 30, 32, kind)), f"clock +{app.ALARM_DELAY_MS} ms; example Friday 07:30")
          for wake, kind in app.ALARM_TYPES.items()),
        ("Disable", _hex(app.alarm(0, 0, 0, 0)), "once"),
    ))
    return "\n".join((*gatt, "", *layouts, "", *commands, "", *alarm))


BLOCKS = [("docs/beds/keeson.md", "keeson-konfurt", render)]
