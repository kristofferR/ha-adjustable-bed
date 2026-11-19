"""Enso command/layout tables generated from its profiles and the Keeson codec."""

from custom_components.adjustable_bed.profiles import enso as app
from custom_components.adjustable_bed.profiles.keeson import encode
from scripts.codec_docs._common import _block, _hex, _table


def render_enso() -> str:
    profile = app.PROFILES["2"]
    words = {
        "Release": 0,
        "Flat": profile.presets["flat"],
        "Zero Gravity": profile.presets["zero_g"],
        "Light button": 0x20000,
        **app.MASSAGE_WORDS,
        **app.HELD_WORDS,
    }
    for motor, (up, down) in app.MOTOR_WORDS.items():
        label = {"head": "Back", "feet": "Foot", "tilt": "Waist", "lumbar": "Lumbar", "both": "Back and foot"}[motor]
        words[f"{label} up"] = up
        words[f"{label} down"] = down
    return _block(
        _table(
            ("Layout", "Controls", "Refresh"),
            ((key, ", ".join(p.motors), f"{app.REFRESH_MS} ms") for key, p in app.PROFILES.items()),
        ),
        _table(
            ("Control", "Frame"),
            ((name, _hex(encode(profile, word))) for name, word in words.items()),
        ),
        _table(
            ("Role", "Characteristic", "Service"),
            (
                ("Write", app.WRITE_UUID, "Discovered at runtime"),
                ("Notify", app.NOTIFY_UUID, "Discovered at runtime"),
            ),
        ),
    )


BLOCKS = [("docs/beds/keeson.md", "keeson-enso", render_enso)]
