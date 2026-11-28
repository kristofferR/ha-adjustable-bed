"""ErgoSportive tables from its explicit subset profile over the AA codec."""

from custom_components.adjustable_bed.codec import sleep_assistant as codec
from custom_components.adjustable_bed.profiles import ergosportive as app

from ._common import _block, _hex, _table

GUIDE = "docs/beds/sleep-assistant.md"


def profiles() -> str:
    return _block(
        _table(
            ("Release selection", "Bed type", "Movement refresh", "Release", "Optional sensor"),
            (
                (
                    label,
                    "ergosportive",
                    f"{app.REFRESH_MS} ms",
                    f"{app.RELEASE_MS} ms neutral"
                    + (f", {app.SECONDARY_MS} ms secondary" if key == "hardware221" else ""),
                    app.SENSORS["old_dsp_normal"],
                )
                for key, label in app.VARIANTS.items()
            ),
        )
    )


def commands() -> str:
    rows = [
        (app.CONTROLS.get(name, name), _hex(codec.instruction(word)))
        for name, word in app.WORDS.items()
    ]
    rows += [
        ("Neutral release", _hex(codec.instruction(0))),
        ("Hardware221 secondary release", _hex(codec.ergosportive_secondary_release())),
    ]
    rows += [
        (f"Lamp brightness {level}", _hex(codec.light(level, False)))
        for level in (1, app.BRIGHTNESS_MAX)
    ]
    return _block(_table(("Action", "Frame"), rows))


BLOCKS = [(GUIDE, "ergosportive-profiles", profiles), (GUIDE, "ergosportive-commands", commands)]
