"""VivaSleep tables from its shipped typed profile and shared HHC codec."""

from custom_components.adjustable_bed.codec import motomotion as codec
from custom_components.adjustable_bed.profiles import vivasleep as app
from scripts.codec_docs._common import _block, _hex, _table

GUIDE = "docs/beds/motomotion.md"


def setup() -> str:
    return _block(
        _table(
            ("Setting", "Selection"),
            (
                ("App", app.VivaSleepProfile.key),
                (
                    "Original Bluetooth name",
                    f"Exactly {app.NAME_LENGTH} UTF-16 units, case-sensitive HHC anywhere",
                ),
                (
                    "Service / write and notify role",
                    f"Uppercase runtime UUID contains {app.SERVICE_MARKER} / {app.CHARACTERISTIC_MARKER}; retain discovered UUIDs",
                ),
                ("Write response", str(app.VivaSleepProfile.write_with_response)),
                ("RGB and light timer", "Name[10] is not B"),
                ("Brightness", "Name[10] is D"),
                ("Alarm", "Name[11] is E"),
                ("Wrapped writer", "Name[11] is M; exact $z is suppressed"),
                ("Wired/wireless synchronization mode", "Name[13] is X; explicit confirmation"),
                (
                    "Synchronization on/off",
                    "Only after recognized live bed synchronization feedback",
                ),
            ),
        )
    )


def panels() -> str:
    return _block(
        _table(
            (
                "Name[8:10] example",
                "Layout",
                "Motor controls",
                "Presets",
                "Memory slots",
                "Massage",
                "Light toggle",
            ),
            (
                (
                    selector,
                    profile.panel,
                    ", ".join(
                        axis.replace("combined", "head and feet together")
                        for axis, _, _ in profile.axes
                    ),
                    ", ".join(key.replace("_", " ") for key, _ in profile.presets),
                    str(profile.memory_slots),
                    ", ".join(
                        c.key.removeprefix("massage_").replace("_", " ")
                        for c in profile.controls
                        if c.key.startswith("massage_")
                    ),
                    "Yes" if profile.light else "No",
                )
                for selector in app.LAYOUT_EXAMPLES
                for profile in (app.VivaSleepProfile(f"HHC00000{selector}D00X"),)
            ),
        )
    )


def commands() -> str:
    controls = {}
    for selector in app.LAYOUT_EXAMPLES:
        for flag in ("H", "X"):
            profile = app.VivaSleepProfile(f"HHC00000{selector}D00{flag}")
            for control in profile.controls:
                controls.setdefault(control, set()).add(profile.panel)
    rows = [
        (
            c.key.replace("_", " "),
            _hex(codec.letter_command(c.letter)),
            _hex(codec.letter_command(c.letter, wrapped=True)),
            f"Periodic {app.REPEAT_INTERVAL_MS} ms"
            if c.held
            else "Once on release"
            if c.tap_up_write
            else "Once",
            c.release,
            ", ".join(sorted(panels)),
        )
        for c, panels in controls.items()
    ]
    rows.extend(
        (
            f"Save memory {slot}",
            _hex(codec.letter_command(letter)),
            _hex(codec.letter_command(letter, wrapped=True)),
            "Once",
            "none",
            "Layouts with numbered memory",
        )
        for slot, letter in enumerate("Za", 1)
    )
    rows.append(
        (
            "Save anti-snore position",
            _hex(codec.letter_command("W")),
            _hex(codec.letter_command("W", wrapped=True)),
            "Once",
            "none",
            "PanelE",
        )
    )
    return _block(
        _table(
            ("Control", "Plain bytes", "M writer bytes", "Press", "Release policy", "Layouts"), rows
        )
    )


def settings() -> str:
    rows = [
        (
            f"RGB channel {index + 1}",
            _hex(codec.ascii_command(command, value)),
            f"Example channel value {value}/120",
        )
        for index, (command, value) in enumerate(zip(app.COLOR_COMMANDS, (120, 60, 0), strict=True))
    ]
    rows.extend(
        (
            (
                "Light timer",
                _hex(codec.ascii_command(app.TIMER_COMMAND, 10)),
                f"Example 10 min; Off or 1 through {app.TIMER_MAX_MINUTES} min",
            ),
            (
                "Alarm",
                _hex(app.alarm_frame("07", "30", 2)),
                "07:30, strength 2 example; strengths 0 (off), 1 and 2",
            ),
            (
                "Synchronization on",
                _hex(codec.ascii_command(12)),
                "One write after recognized feedback",
            ),
            (
                "Synchronization off",
                _hex(codec.ascii_command(15)),
                "One write after recognized feedback",
            ),
            (
                "Wireless synchronization",
                _hex(codec.ascii_command(33049, 0)),
                "Send confirmed action with confirmed: true, one receiver",
            ),
            (
                "Wired synchronization",
                _hex(codec.ascii_command(33049, 1)),
                "Send confirmed action with confirmed: true, one receiver",
            ),
        )
    )
    return _block(_table(("Setting", "Example bytes", "Range / admission"), rows))


def timing() -> str:
    return _block(
        _table(
            ("Behavior", "Schedule"),
            (
                (
                    "Held control",
                    f"First emission at {app.REPEAT_INTERVAL_MS} ms, then the same interval",
                ),
                ("stop release", f"Fresh cancellation token; offsets {app.STOP_OFFSETS_MS} ms"),
                (
                    "fallback release",
                    f"Fewer than {app.SHORT_UP_THRESHOLD} ticks: same-command tail at {app.SHORT_UP_OFFSETS_MS} ms on normal release; none on cancellation",
                ),
                ("none release", "End refresh without another frame"),
                (
                    "Normal RGB",
                    "Markers at 0/200/400 ms; red/green/blue at 100/300/500 ms; finish 600 ms",
                ),
                (
                    "M writer RGB",
                    "Markers suppressed; red/green/blue at 0/100/200 ms; finish 300 ms",
                ),
                (
                    "Timer / alarm",
                    f"Marker then one combined setting frame after {app.SETTINGS_DELAY_MS} ms",
                ),
            ),
        )
    )


def notifications() -> str:
    rows = [
        (str(count), "RGB channels / light timer in minutes", str(indices))
        for count, indices in app.RGB_FIELD_INDICES.items()
    ]
    rows.extend(
        (
            ("75", "Alarm hour / minute / strength", str(app.ALARM_FIELD_INDICES)),
            (
                "39",
                "Synchronization available / enabled",
                f"Token {app.BIND_FIELD_INDEX}: 00065 = on, 00066 = off; otherwise unavailable",
            ),
            (
                "39",
                "Synchronization mode",
                f"Decimal token {app.SYNC_TYPE_INDEX}: 0 wireless, 1 wired; app event OK follows valid parsing",
            ),
        )
    )
    return _block(_table(("Token count", "Consumed state", "Zero-based indices or rule"), rows))


BLOCKS = [
    (GUIDE, "vivasleep-" + name, renderer)
    for name, renderer in (
        ("setup", setup),
        ("panels", panels),
        ("commands", commands),
        ("settings", settings),
        ("timing", timing),
        ("notifications", notifications),
    )
]
