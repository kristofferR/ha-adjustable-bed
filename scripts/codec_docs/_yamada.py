"""アシステック profile tables, generated from the shipped encoders and data."""

from datetime import datetime

from custom_components.adjustable_bed.profiles import yamada as app
from custom_components.adjustable_bed.profiles.keeson import encode
from scripts.codec_docs._common import _block, _hex, _table


def render_yamada() -> str:
    profiles = tuple(app.PROFILES.values())
    return _block(
        "#### Controls",
        _table(
            ("Control", "P1", "P2"),
            (
                (name, *(_hex(encode(p, word)) for p in profiles))
                for name, word in app.WORDS.items()
            ),
        ),
        _table(
            ("Alarm position", "P1 key", "P2 key"),
            (
                (
                    name,
                    str(app.POSITIONS[profiles[0].key][name]),
                    str(app.POSITIONS[profiles[1].key][name]),
                )
                for name in app.POSITIONS[profiles[0].key]
            ),
        ),
        _table(
            ("Role", "Service OR set", "Characteristic OR set"),
            (
                (
                    "Write",
                    ", ".join(f"`{u}`" for u in sorted(app.WRITE_SERVICES)),
                    ", ".join(f"`{u}`" for u in sorted(app.WRITE_CHARS)),
                ),
                (
                    "Notify",
                    ", ".join(f"`{u}`" for u in sorted(app.NOTIFY_SERVICES)),
                    ", ".join(f"`{u}`" for u in sorted(app.NOTIFY_CHARS)),
                ),
            ),
        ),
        _table(
            ("Example", "P1", "P2"),
            (
                (
                    "Clock: 2026-11-12 06:30:45",
                    *(_hex(app.clock(p, datetime(2026, 11, 12, 6, 30, 45))) for p in profiles),
                ),
                (
                    "One query round",
                    *(
                        "; ".join(f"+{ms} ms: {_hex(frame)}" for ms, frame in app.queries(p))
                        for p in profiles
                    ),
                ),
            ),
        ),
        "#### Timing",
        _table(
            ("Operation", "Policy"),
            (
                (
                    "Ordinary configured pulses",
                    "Configured count × interval, bounded by elapsed time; defaults in Configuration",
                ),
                (
                    "App holds and renewable card leases",
                    f"Immediate, then every {app.REFRESH_MS} ms until duration/release/expiry",
                ),
                ("Release/cancel", "Captured zero word at +100/+400 ms, fresh cancellation event"),
                (
                    "Explicit STOP",
                    "Zero word at +100 ms; consumes this command's completed cleanup when preempting",
                ),
                (
                    "Personal M gesture",
                    f"Same recall word held {app.SAVE_CONFIRMATION_MS} ms; local UI confirmation only",
                ),
                ("Refresh alarms", ", ".join(f"+{ms} ms round" for ms in app.PAGE_ROUNDS_MS)),
                ("After alarm write", f"One manager round after {app.REFRESH_MS} ms"),
                ("Notification retry", f"Once after {app.NOTIFY_RETRY_MS} ms"),
                ("Clock", "Once on connection, overlapping asynchronous notification setup"),
            ),
        ),
    )


BLOCKS = [("docs/beds/keeson.md", "keeson-yamada", render_yamada)]
