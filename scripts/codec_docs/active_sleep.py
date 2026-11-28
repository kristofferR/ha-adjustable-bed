"""Active Sleep reference tables from its codec and shipped profile."""

from custom_components.adjustable_bed.codec import active_sleep as codec
from custom_components.adjustable_bed.profiles.active_sleep import (
    ACTIVE_SLEEP,
    BED_TEMPLATES,
    MATTRESS_TEMPLATES,
)
from scripts.codec_docs._common import Block, _block, _hex, _table

GUIDE = "docs/beds/active-sleep.md"


def profiles() -> str:
    p = ACTIVE_SLEEP
    return _block(
        _table(
            (
                "Profile",
                "Bed type",
                "Repeat",
                "Manual start",
                "Held preset start",
                "Movement reply",
            ),
            (
                (
                    p.key,
                    "`active_sleep`",
                    f"{p.interval_ms} ms",
                    f"{p.manual_delay_ms} ms",
                    f"{p.preset_delay_ms} ms",
                    f"{p.response_timeout_ms} ms",
                ),
            ),
        )
    )


def transports() -> str:
    return _block(
        _table(
            ("Role", "UUID"),
            (
                ("Service", f"`{codec.SERVICE_UUID}`"),
                ("Write with response / notify", f"`{codec.CHAR_UUID}`"),
            ),
        )
    )


def commands() -> str:
    return _block(
        _table(
            ("Control", "Bytes"),
            (
                (name.replace("_", " "), _hex(codec.arrow(code)))
                for name, code in codec.OPERATIONS.items()
            ),
        ),
        _table(
            ("Query", "Bytes"),
            (
                (name, _hex(codec.frame(code)))
                for name, code in (
                    ("Serial", 0x81),
                    ("Spec", 0x82),
                    ("Bed limits", 0xB1),
                    ("Bed position", 0xB2),
                    ("Mattress", 0xC1),
                    ("Realtime", 0xA2),
                )
            ),
        ),
        _table(
            ("App bed template", "Head / legs / height / tilt", "Bytes"),
            (
                (str(i), " / ".join(map(str, posture)), _hex(codec.preset(*posture)))
                for i, posture in enumerate(BED_TEMPLATES, 1)
            ),
        ),
        _table(
            (
                "Mattress template",
                "Head / shoulder / hip / thigh / calf / feet",
                "Mode",
                "Bytes, flags off",
            ),
            (
                (
                    str(i),
                    " / ".join(map(str, zones)),
                    str(mode),
                    _hex(codec.mattress(*zones, mode=mode)),
                )
                for i, (zones, mode) in enumerate(MATTRESS_TEMPLATES, 1)
            ),
        ),
        "Settings: `B3 03 lock_mask 00 fast xor`. Mattress: `C2 04 shoulder/head thigh/hip feet/calf flags/mode xor`. Authentication: `84 10 existing_ID_bytes xor`. No credential default is shipped.",
    )


BLOCKS: tuple[Block, ...] = (
    (GUIDE, "active-sleep-profiles", profiles),
    (GUIDE, "active-sleep-transports", transports),
    (GUIDE, "active-sleep-commands", commands),
)
