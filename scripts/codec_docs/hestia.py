"""Hestia's app-specific key and schedule data over the Keeson codec."""

from custom_components.adjustable_bed.profiles import hestia as app
from custom_components.adjustable_bed.profiles.keeson import encode
from scripts.codec_docs._common import _block, _hex, _table


def render() -> str:
    p = app.PROFILE
    assert p.memory_save is not None
    words = {
        **{
            f"{axis} {direction}": pair[index]
            for axis, pair in app.AXES.items()
            for index, direction in enumerate(("up", "down"))
        },
        "Movement release": 0,
        "Preset cancel": app.PRESET_CANCEL,
        **p.presets,
        **{f"Memory {slot} recall": word for slot, word in p.memory.items()},
        **{f"Memory {slot} save": word for slot, word in p.memory_save.words.items()},
        **{f"Light {'on' if on else 'off'}": word for on, word in app.LIGHTS.items()},
        **{
            f"Massage {kind} {level}": base + level
            for kind, base in (("intensity", app.INTENSITY), ("wave", app.WAVE))
            for level in range(4)
        },
        **{f"Massage timer {minutes} min": word for minutes, word in app.TIMERS.items()},
    }
    return _block(
        _table(
            ("Control", "Frame"), ((name, _hex(encode(p, word))) for name, word in words.items())
        ),
        _table(
            ("Operation", "Schedule"),
            (
                ("Movement", f"Immediate, then {p.refresh_ms} ms after each completed write"),
                (
                    "Movement release / explicit STOP",
                    f"{p.release.steps[0][0]} ms delay; one zero key",
                ),
                (
                    "Presets / save / light / massage",
                    f"{p.tap_wait_ms} ms before each key; one write",
                ),
                ("Massage On", "Wave, then intensity; Off is a single intensity-zero key"),
                ("Alarm enable / disable", "One EA FE 16 frame, no added delay or release"),
            ),
        ),
        _table(
            ("Local setting", "Choices", "HA initial choice"),
            (
                (name, ", ".join(options), app.DEFAULTS[name])
                for name, options in app.CHOICES.items()
            ),
        ),
    )


BLOCKS = [("docs/beds/keeson.md", "keeson-hestia", render)]
