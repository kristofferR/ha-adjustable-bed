"""VivaSleep's unregistered subset over the shared MotoMotion codec."""

from custom_components.adjustable_bed.codec import motomotion as codec
from custom_components.adjustable_bed.profiles import vivasleep as app
from scripts.codec_docs._common import _block, _hex, _table

GUIDE = "docs/beds/motomotion.md"


def setup() -> str:
    return _block(
        _table(
            ("Property", "Value"),
            (
                (
                    "App scan predicate",
                    f"Case-sensitive HHC anywhere, exactly {app.NAME_LENGTH} UTF-16 units",
                ),
                ("Service predicate", f"Uppercase runtime UUID contains `{app.SERVICE_MARKER}`"),
                (
                    "Write/notify predicate",
                    f"Uppercase runtime UUID contains `{app.CHARACTERISTIC_MARKER}`, within a matching service",
                ),
                ("Write response", str(app.VivaSleepProfile.write_with_response)),
                (
                    "Writer branch",
                    "UTF-16 name[11] equals uppercase M: suppress exact $z, add missing $# prefix and R\\r suffix",
                ),
            ),
        )
    )


def panels() -> str:
    selectors = (
        "15",
        "A0",
        "35",
        "45",
        "85",
        "C0",
        "40",
        "25",
        "55",
        "B0",
        "95",
        "96",
        "97",
        "98",
        "30",
        "65",
        "75",
        "00",
        "10",
        "20",
        "50",
        "60",
        "70",
        "80",
        "90",
        "D0",
        "E0",
        "X0",
    )
    return _block(
        _table(
            ("name[8:10] example", "Primary factory target (no controls inferred)"),
            (
                (selector, app.VivaSleepProfile(f"HHC00000{selector}0000").panel)
                for selector in selectors
            ),
        )
    )


def commands() -> str:
    return _block(
        _table(
            ("Toolbar branch", "Decimal command / parameter", "Writer bytes", "Schedule"),
            (
                (
                    f"field_b={field_b}",
                    f"`{command}` / `{app.SYNC_PARAMETER}`",
                    _hex(codec.decimal_fields(command, app.SYNC_PARAMETER)),
                    "One invocation, no callback release timer",
                )
                for field_b, command in app.SYNC_COMMANDS.items()
            ),
        )
    )


def timing() -> str:
    profile = app.VivaSleepProfile("HHC00000150000")
    return _block(
        _table(
            ("Shared routine", "Nominal schedule"),
            (
                (
                    "ImageButton repeat",
                    f"First tick and interval {app.REPEAT_INTERVAL_MS} ms; up/cancel cancels timer",
                ),
                (
                    "Short up, repeat enabled, no up callback",
                    f"Count below {app.SHORT_UP_THRESHOLD}: extra copies at {app.SHORT_UP_OFFSETS_MS} ms; no cancel fallback",
                ),
                (
                    "sendStopCMD",
                    ", ".join(
                        f"{offset} ms: {_hex(frame)}" for offset, frame in profile.stop_schedule
                    ),
                ),
                (
                    "sendStopCMD, M writer",
                    ", ".join(
                        f"{offset} ms: {_hex(frame)}"
                        for offset, frame in app.VivaSleepProfile("HHC00000150M00").stop_schedule
                    ),
                ),
            ),
        )
    )


def notifications() -> str:
    rows = [
        (str(count), "RGB object fields 7/b/f/13", str(indices))
        for count, indices in app.RGB_FIELD_INDICES.items()
    ]
    rows.extend(
        (
            ("75", "Alarm object fields 7/b/f", str(app.ALARM_FIELD_INDICES)),
            (
                "39",
                "Bind object fields 7/b",
                f"Token {app.BIND_FIELD_INDEX}: in {{00065, 00066}} / equals 00065",
            ),
            ("39", "syncType / app stream event", f"Decimal token {app.SYNC_TYPE_INDEX} / OK"),
        )
    )
    return _block(
        _table(("Token count", "Neutral destination", "Zero-based token indices or rule"), rows)
    )


BLOCKS = [
    (GUIDE, "vivasleep-setup", setup),
    (GUIDE, "vivasleep-panels", panels),
    (GUIDE, "vivasleep-commands", commands),
    (GUIDE, "vivasleep-timing", timing),
    (GUIDE, "vivasleep-notifications", notifications),
]
