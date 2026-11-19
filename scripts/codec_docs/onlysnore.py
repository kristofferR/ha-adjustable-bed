"""Render every code-owned Snore Monitor BED reference value."""

from custom_components.adjustable_bed.codec import onlysnore as codec
from custom_components.adjustable_bed.profiles import onlysnore as app

from ._common import Block, _block, _hex, _table

GUIDE = "docs/beds/onlysnore.md"


def bed_types() -> dict[str, tuple[str, ...]]:
    return {"onlysnore": ("onlysnore",)}


def profile() -> str:
    p = app.PROFILE
    return _block(
        _table(
            (
                "Profile",
                "Bed type",
                "Actuators (app order)",
                "Refresh / release / save threshold (ms)",
            ),
            (
                (
                    p.key,
                    "onlysnore",
                    ", ".join(app.AXES.values()),
                    f"{p.refresh_ms} / {p.release_ms} / {p.save_ms}",
                ),
            ),
        )
    )


def transports() -> str:
    return _block(
        _table(
            ("Role", "Service", "Characteristic", "Property"),
            (
                ("BED write", codec.SERVICE, codec.WRITE, "write-without-response"),
                ("BED notify", codec.SERVICE, codec.NOTIFY, "notify or indicate"),
                ("Firmware", "180A", codec.FIRMWARE, "read, optional"),
                ("Hardware", "180A", codec.HARDWARE, "read, optional"),
            ),
        )
    )


def commands() -> str:
    rows = list(app.PROFILE.frames.items())
    rows.extend((f"query_{code:02x}", codec.query(code)) for code in (160, 176, 192, 208, 224))
    rows.extend(
        (f"{name}_{value}", codec.setting(opcode, value))
        for name, opcode, values in (
            ("privacy", 178, (0, 1)),
            ("detection", 181, (0, 1)),
            ("management", 180, (1,)),
        )
        for value in values
    )
    rows.extend(
        (f"intervention_{level}", codec.intervention(1, level)) for level in app.INTERVENTION_LEVELS
    )
    rows.extend(
        (f"intervention_demo_{level}", codec.intervention(2, level))
        for level in app.INTERVENTION_LEVELS
    )
    rows.extend(
        (
            ("intervention_off", codec.intervention(0, 0)),
            ("intervention_stop", codec.INTERVENTION_STOP),
            ("single_alarm_close", codec.CLOSE_SINGLE),
        )
    )
    return _block(_table(("Action", "Frame"), ((name, _hex(frame)) for name, frame in rows)))


def parameters() -> str:
    return _block(
        _table(
            ("Field", "Values / encoding"),
            (
                ("Models", ", ".join(app.MODELS)),
                (
                    "Alarm UI index → wire action",
                    ", ".join(
                        f"{index} → {value:02X}" for index, value in enumerate(codec.ACTION_CODES)
                    ),
                ),
                ("Alarm slots", "1 by default; configuration byte 8 equal to 3 selects 3"),
                (
                    "Alarm repeat selection",
                    "Exact mask 0..255; 0 and 128 take the distinct one-time paths",
                ),
                (
                    "Clock",
                    "year minus 1900, month minus 1, day, ISO weekday minus 1, hour, minute, second; octet masked",
                ),
                (
                    "Startup",
                    "Clock +100 ms, status +400 ms, configuration +500 ms; optional information reads",
                ),
                ("After setting", "Status +300 ms; detection repeats +100 ms"),
                ("After alarm", "Slot query +300 ms; refresh enumerates slots 200 ms apart"),
            ),
        )
    )


BLOCKS: list[Block] = [
    (GUIDE, "onlysnore-profile", profile),
    (GUIDE, "onlysnore-transports", transports),
    (GUIDE, "onlysnore-commands", commands),
    (GUIDE, "onlysnore-parameters", parameters),
]
