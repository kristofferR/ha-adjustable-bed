"""Ultramatic's reference tables, rendered from shipped encoders and profile."""

from custom_components.adjustable_bed.profiles import ultramatic as app
from scripts.codec_docs._common import Block, _block, _hex, _table


def render() -> str:
    return _block(
        _table(
            ("Role", "UUID", "Mode"),
            (
                ("Service", f"`{app.SERVICE_UUID}`", "exact UUID"),
                ("Write", f"`{app.WRITE_UUID}`", "without response"),
                ("Status", f"`{app.NOTIFY_UUID}`", "notify preferred, indicate accepted"),
            ),
        ),
        _table(
            ("Action", "A", "AB", "B"),
            (
                (action, *(_hex(app.control(action, side)) for side in app.SELECTORS))
                for action in app.PROFILE.keys
            ),
        ),
        _table(
            ("Request", "Bytes"),
            (
                ("Massage status", _hex(app.QUERY_MASSAGE)),
                ("Alarm status", _hex(app.QUERY_ALARM)),
            ),
        ),
        _table(
            ("Gesture", "Policy"),
            (
                (
                    "Movement and recall",
                    f"Immediate, then {app.PROFILE.hold.repeat_ms} ms while held",
                ),
                ("Release", f"Global AB STOP after {app.PROFILE.hold.release_after_ms} ms"),
                (
                    "Save ZG / ANTI / M1 / M2; FLAT+ZG",
                    f"Same held frame for {app.SAVE_HOLD_MS} ms; no hardware acknowledgement",
                ),
                (
                    "Massage",
                    "One control, then status queries at "
                    + " / ".join(map(str, app.MASSAGE_QUERIES))
                    + " ms",
                ),
                ("Light", "One toggle, then ordinary release"),
                *(
                    (label, ", ".join(f"{kind} +{ms} ms" for ms, kind in schedule))
                    for label, schedule in (
                        ("Startup", app.STARTUP),
                        ("Explicit clock sync", app.CLOCK_SYNC),
                        ("Alarm set", app.ALARM_SET),
                        ("Alarm query", app.ALARM_QUERY),
                    )
                ),
                ("Notification retry", f"Once after {app.NOTIFY_RETRY_MS} ms"),
            ),
        ),
    )


BLOCKS: list[Block] = [("docs/beds/okin-nframe.md", "ultramatic-controls", render)]
