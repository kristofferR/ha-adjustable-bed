"""Sophie additions to the shared FFFF guide, generated from shipped profile data."""

from custom_components.adjustable_bed.profiles import sophie as app
from scripts.codec_docs._common import _block, _hex, _table


def render() -> str:
    rows = [
        ("Movement / massage header action", app.HEADER_ACTION),
        ("Synchronization off", app.SYNC_OFF),
        ("Synchronization on", app.SYNC_ON),
        ("Synchronization query", app.SYNC_QUERY),
    ]
    for key, code in zip(app.PRESET_KEYS, app.PRESET_CODES, strict=True):
        from custom_components.adjustable_bed.codec.ff_frame import control

        rows.extend(
            (
                (f"Save {key}", control(code, arg=(code << 4) & 255)),
                (f"Clear {key}", control(code, arg=((code << 4) | 15) & 255)),
                (f"Recall saved {key}", control(code, arg=((code << 4) | 1) & 255)),
            )
        )
    commands = _table(("Sophie action", "Frame"), ((label, _hex(frame)) for label, frame in rows))
    timing = _table(
        ("Startup action", "Offset"),
        (
            (
                "Saved preset queries",
                f"{app.QUERY_DELAY_MS} ms, then {app.QUERY_SPACING_MS} ms apart",
            ),
            ("Local clock", f"{app.CLOCK_DELAY_MS} ms"),
            ("Synchronization query", f"{app.CLOCK_DELAY_MS + app.SYNC_AFTER_CLOCK_MS} ms"),
            ("Brightness query", f"{app.LIGHT_QUERY_DELAY_MS} ms"),
            (
                "Android save / clear threshold",
                f"{app.PRESET_HOLD_MS} ms; HA uses confirmed explicit actions",
            ),
        ),
    )
    selectors = _table(
        ("Selector", "Result"),
        (
            (", ".join(app.NAME_TOKENS), "Raw case-sensitive substring discovery candidates"),
            (", ".join(app.NAMED_QUERY_TOKENS), "Named03 saved queries; fallback09 otherwise"),
            (
                ", ".join(app.SIDE_ALARM_TOKENS),
                "Side alarm modes; ordinary movement has no side byte",
            ),
            ("QMS2 (case-insensitive)", "No alarm massage control"),
        ),
    )
    return _block(commands, timing, selectors)


BLOCKS = [("docs/beds/ff_frame.md", "sophie", render)]
