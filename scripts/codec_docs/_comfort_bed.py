"""Comfort Bed command tables from its shipped enum86 profile."""

from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles.comfort_bed import (
    PROFILE,
    QUERIES,
    SAVES,
    SCAN_KEYWORDS,
    TEXT_LONG,
)
from scripts.codec_docs._common import _block, _hex, _table


def render() -> str:
    assert PROFILE.codes is not None and PROFILE.stop is not None
    commands = [
        *((action.removeprefix("deviceFunctionItem"), code, action) for action, code in QUERIES),
        *((key.replace("_", " "), code, "") for key, code in PROFILE.codes.items()),
        *(("save " + key.replace("_", " "), code, "") for key, code in SAVES.items()),
        *(
            (f"memory {slot} {kind}", code, "")
            for slot, pair in enumerate(PROFILE.memory, 1)
            for kind, code in zip(("recall", "save"), pair, strict=True)
        ),
        *((key + " (3s long)", code, "") for key, code in TEXT_LONG.items()),
        ("movement STOP", PROFILE.stop, ""),
    ]
    return _block(
        _table(
            ("App discovery candidates", "Motor refresh", "Text long press"),
            [
                (
                    "; ".join(f"`{k}`" for k in SCAN_KEYWORDS),
                    f"{PROFILE.motor_repeat_ms} ms",
                    "3000 ms",
                )
            ],
        ),
        _table(
            ("Route", "Service", "Write characteristic"),
            (
                (
                    key,
                    f"`{codec.TRANSPORTS[key].service_uuid}`",
                    f"`{codec.TRANSPORTS[key].write_uuid}`",
                )
                for key in PROFILE.transports
            ),
        ),
        _table(
            ("Action", "Nordic (side ignored)", "Framed left", "Framed right"),
            (
                (
                    label,
                    _hex(codec.function(code, action=action, single=True)),
                    _hex(codec.function(code, 0, action=action)),
                    _hex(codec.function(code, 1, action=action)),
                )
                for label, code, action in commands
            ),
        ),
    )
