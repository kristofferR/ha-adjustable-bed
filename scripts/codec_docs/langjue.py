"""Generate the Langjue P1 guide tables from the codec and profile."""

from datetime import datetime

from custom_components.adjustable_bed.codec import langjue as codec
from custom_components.adjustable_bed.codec.langjue import Op
from custom_components.adjustable_bed.profiles import langjue as app

from ._common import Block, _block, _table

GUIDE = "docs/beds/langjue.md"


def _commands(rows: list[tuple[str, bytes, str]]) -> str:
    return _block(
        _table(
            ("Command", "Bytes", "Write mode"),
            [(label, f"`{frame.hex(' ')}`", mode) for label, frame, mode in rows],
        )
    )


def render_transport() -> str:
    return _block(
        _table(
            ("Role", "Selector"),
            [
                ("Service UUID", f"`{app.SERVICE}`"),
                ("Write characteristic", "Write and Write Without Response"),
                ("Notify characteristic", "Notify, outside the Write branch"),
            ],
        )
    )


def render_motion() -> str:
    return _commands(
        [
            ("Back up", codec.motion(2, 0, up=True), "Without response"),
            ("Back down", codec.motion(2, 0), "Without response"),
            ("Legs up", codec.motion(2, 1, up=True), "Without response"),
            ("Legs down", codec.motion(2, 1), "Without response"),
            ("STOP (two motors)", codec.motion(2), "Without response"),
        ]
    )


def render_presets() -> str:
    labels = {
        "flat": "Flat",
        "zero_g": "Zero G",
        "reading": "Reading",
        "anti_snore": "Anti-Snoring",
        **app.EXTRA_PRESETS,
    }
    return _commands(
        [
            *(
                (labels[key], codec.preset(mode), "Without response")
                for key, mode in app.PRESETS.items()
            ),
            *(
                (f"Recall memory {slot}", codec.preset(mode), "Without response")
                for slot, mode in enumerate(app.MEMORY_MODES, 1)
            ),
            *(
                (f"Save memory {slot}", codec.preset(mode, save=True), "Without response")
                for slot, mode in enumerate(app.MEMORY_MODES, 1)
            ),
        ]
    )


def render_accessories() -> str:
    return _commands(
        [
            ("Light on", codec.light(True), "Without response"),
            ("Light off", codec.light(False), "Without response"),
            ("Head massage (level 1)", codec.massage_level(1, 1), "With response"),
            ("Foot massage (level 1)", codec.massage_level(2, 1), "With response"),
            ("Head massage off", codec.massage_level(1, 0), "With response"),
            ("Foot massage off", codec.massage_level(2, 0), "With response"),
            *(
                (
                    f"Massage Type {pattern}",
                    codec.frame(Op.MASSAGE_PATTERN, 2, bytes((0, pattern))),
                    "With response",
                )
                for pattern in app.MASSAGE_PATTERNS
            ),
            *(
                (
                    f"Massage timer ({minutes} min)",
                    codec.frame(Op.MASSAGE_TIMER, 2, bytes((0, code))),
                    "With response",
                )
                for minutes, code in app.MASSAGE_TIMERS.items()
            ),
            (
                "Read head massage level",
                codec.frame(Op.READ_MASSAGE_LEVEL, 1, b"\x01"),
                "With response",
            ),
            (
                "Read foot massage level",
                codec.frame(Op.READ_MASSAGE_LEVEL, 1, b"\x02"),
                "With response",
            ),
            ("Read massage time", codec.frame(Op.READ_MASSAGE_TIME), "With response"),
            ("Read massage status", codec.frame(Op.READ_MASSAGE_STATE), "With response"),
        ]
    )


def render_alarm() -> str:
    return _commands(
        [
            ("Read alarm", codec.frame(Op.READ_ALARM, 1, b"\x00"), "With response"),
            (
                "Clock sync (Friday at 07:08:09)",
                codec.clock(datetime(2026, 1, 2, 7, 8, 9)),
                "With response",
            ),
            *(
                (
                    f"Alarm at 08:00, {key.replace('_', ' ')}",
                    codec.alarm(action, (), 8, 0),
                    "With response",
                )
                for key, action in app.ALARM_ACTIONS.items()
            ),
            (
                "Zero G on Monday and Sunday at 06:30",
                codec.alarm(4, (0, 6), 6, 30),
                "With response",
            ),
            (
                "Disable the stored Flat alarm at 08:00",
                codec.alarm_enabled(codec.alarm(3, (), 8, 0)[6:], False),
                "With response",
            ),
        ]
    )


def render_timing() -> str:
    timing = _block(
        _table(
            ("Event", "Timing"),
            [
                ("Handshake", f"{app.HANDSHAKE_DELAY_MS} ms after role setup"),
                (
                    "Directional refresh",
                    f"Immediate, then every {app.MOTOR_REFRESH_MS} ms while held",
                ),
                (
                    "Massage start",
                    ", ".join(
                        f"{setting} at {offset} ms" for offset, setting, _ in app.MASSAGE_START
                    ),
                ),
                (
                    "Massage off",
                    ", ".join(
                        f"{setting} at {offset} ms" for offset, setting, _ in app.MASSAGE_STOP
                    ),
                ),
            ],
        )
    )
    return (
        timing
        + "\n\n"
        + _commands(
            [
                ("Handshake", codec.handshake(), "With response"),
                ("Read control-box version", codec.frame(Op.VERSION), "With response"),
                ("Read release date", codec.frame(Op.RELEASE_DATE), "With response"),
                ("Read light state", codec.frame(Op.READ_LIGHT, 8), "With response"),
            ]
        )
    )


BLOCKS: list[Block] = [
    (GUIDE, f"langjue-{name}", renderer)
    for name, renderer in (
        ("transport", render_transport),
        ("motion", render_motion),
        ("presets", render_presets),
        ("accessories", render_accessories),
        ("alarm", render_alarm),
        ("timing", render_timing),
    )
]
