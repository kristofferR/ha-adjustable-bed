"""Render the Sleeptime profile's controls and wire timings."""

from datetime import datetime

from custom_components.adjustable_bed.codec import okin_nframe as codec
from custom_components.adjustable_bed.const import (
    NORDIC_UART_READ_CHAR_UUID,
    NORDIC_UART_SERVICE_UUID,
    NORDIC_UART_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.profiles import sleeptime as app
from scripts.codec_docs._common import _block, _hex, _table


def render() -> str:
    return _block(
        _table(
            ("Role", "UUID", "Operation"),
            (
                ("Service", f"`{NORDIC_UART_SERVICE_UUID}`", "Exact GATT lookup"),
                ("Write", f"`{NORDIC_UART_WRITE_CHAR_UUID}`", "Write without response"),
                ("Status", f"`{NORDIC_UART_READ_CHAR_UUID}`", "Notify or indicate"),
            ),
        ),
        _table(
            ("Name prefix", "Movement", "Position presets", "Alarm modes"),
            (
                (
                    app.SELECTORS[selector],
                    ", ".join(layout.axes),
                    ", ".join(layout.presets),
                    ", ".join(f"{name} ({app.WAKE_MODES[name]})" for name in layout.wake_actions),
                )
                for selector, layout in app.LAYOUTS.items()
            ),
        ),
        _table(
            ("Action", "Frame"),
            (
                *(
                    (action, _hex(codec.frame40(word, 1)))
                    for action, word in app.PROFILE.keys.items()
                ),
                ("Light toggle", _hex(app.LIGHT)),
                ("Release", _hex(app.STOP)),
                ("Flat + Zero-G reset", _hex(app.RESET)),
                *((action, _hex(codec.frame40(word))) for action, (word, _) in app.MASSAGE.items()),
                ("Massage query", _hex(app.MASSAGE_QUERY)),
                ("Alarm query", _hex(app.ALARM_QUERY)),
                (
                    "Clock example (2026-11-26 21:42:57)",
                    _hex(app.clock(datetime(2026, 11, 26, 21, 42, 57))),
                ),
                ("Vibration alarm example (daily at 06:30)", _hex(app.alarm(8, 255, 6, 30, True))),
            ),
        ),
        _table(
            ("Gesture", "Timing"),
            (
                ("Motor/preset hold", f"Immediate, then every {app.REFRESH_MS} ms"),
                ("Release", f"STOP {app.RELEASE_MS} ms after release or cancellation"),
                (
                    "Memory and named save gesture",
                    f"{app.SAVE_MS} ms including time to the first repeat",
                ),
                ("Light", "One toggle"),
                ("Massage timer", f"One write, query after {app.MASSAGE['massage_timer'][1]} ms"),
                (
                    "Other massage actions",
                    f"One write, query after {app.MASSAGE['massage_toggle'][1]} ms",
                ),
                ("Clock", f"On connect and manual sync, immediate plus {app.CLOCK_REPEAT_MS} ms"),
                ("Alarm setting", ", ".join(f"{kind} +{ms} ms" for ms, kind in app.ALARM_WRITES)),
                ("Subscription failure", f"One retry after {app.NOTIFY_RETRY_MS} ms"),
            ),
        ),
    )
