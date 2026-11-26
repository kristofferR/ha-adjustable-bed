"""OkimattMotion profile tables from its command words and clock encoder."""

from datetime import datetime, time

from custom_components.adjustable_bed.profiles import okimattmotion as app
from scripts.codec_docs._common import _block, _hex, _table

GUIDE = "docs/beds/keeson.md"


def render_setup() -> str:
    return _block(
        "Android scan prefixes: " + ", ".join(f"`{prefix}`" for prefix in app.NAME_PREFIXES) + ".",
        _table(("App layout", "Available movement"), app.LAYOUTS.items()),
        _table(
            ("GATT role", "Service", "Characteristic"),
            (
                ("Write", f"`{app.WRITE_SERVICE}`", f"`{app.WRITE_CHAR}`"),
                (
                    "Android notification registration",
                    f"`{app.NOTIFY_SERVICE}`",
                    f"`{app.NOTIFY_CHAR}`",
                ),
            ),
        ),
    )


def render_controls() -> str:
    frame = app.control_frame
    directions = [
        (f"{label} {direction}", _hex(frame(word)))
        for (label, words) in zip(
            ("Back", "Legs", "Back and legs"), app.MOTORS.values(), strict=True
        )
        for direction, word in zip(("up", "down"), words, strict=True)
    ]
    presets = [
        (label, _hex(frame(recall)), _hex(frame(save)))
        for label, (recall, save) in zip(
            ("Zero Gravity", "Flat", "Quiet Sleep / Book", "Memory A", "Memory B"),
            app.PRESETS.values(),
            strict=True,
        )
    ]
    now = datetime(2026, 11, 26, 12, 34, 56)
    target = time(7, 45)
    return _block(
        _table(
            ("Movement", "Frame"),
            (
                *directions,
                ("Manual release", _hex(frame(app.MANUAL_STOP))),
                ("Preset STOP", _hex(frame(app.PRESET_STOP))),
            ),
        ),
        _table(("Position", "Recall", "Save"), presets),
        _table(
            ("Massage level", "Intensity frame", "Wave frame"),
            (
                (
                    str(level),
                    _hex(frame(app.MASSAGE_INTENSITY + level)),
                    _hex(frame(app.MASSAGE_WAVE + level)),
                )
                for level in (0, *app.MASSAGE_LEVELS)
            ),
        ),
        _table(
            ("Control", "Frame"),
            (
                *(
                    (f"Massage timer {minutes} min", _hex(frame(word)))
                    for minutes, word in app.MASSAGE_TIMERS.items()
                ),
                *(
                    ("Light on" if on else "Light off", _hex(frame(word)))
                    for on, word in app.LIGHT.items()
                ),
            ),
        ),
        "Example clock writes at 12:34:56 for a 07:45 alarm.",
        _table(
            ("Sleep timer", "Wake mode off", "Wake mode on"),
            (
                (
                    "Off" if minutes is None else f"{minutes} min",
                    *(_hex(app.alarm_frame(now, target, minutes, wake)) for wake in app.WAKE_MODES),
                )
                for minutes in app.SLEEP_TIMERS
            ),
        ),
        f"Cancel frame in the same example: {_hex(app.alarm_frame(now, None, None, 'none'))}.",
    )


def render_timing() -> str:
    return _block(
        _table(
            ("Operation", "Writes"),
            (
                (
                    "Movement",
                    f"Immediate, then every {app.REFRESH_MS} ms. Finite pulses or a renewable hold.",
                ),
                ("Manual release", f"{app.MANUAL_STOP_WRITES} consecutive manual STOP writes."),
                ("Preset, save, light or timer", "One write per action."),
                (
                    "Massage power",
                    f"Wave, {app.MASSAGE_POWER_DELAY_S * 1000:g} ms wait, then intensity. Power on then sends the 10 min timer.",
                ),
                ("Massage level change", "Intensity then wave in immediate succession."),
                (
                    "Set or cancel alarm",
                    f"{app.ALARM_WRITES} consecutive writes, sampling local time for each.",
                ),
            ),
        ),
    )


BLOCKS = [
    (GUIDE, "keeson-okimattmotion-setup", render_setup),
    (GUIDE, "keeson-okimattmotion-controls", render_controls),
    (GUIDE, "keeson-okimattmotion-timing", render_timing),
]
