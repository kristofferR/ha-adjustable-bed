"""Generated M Line reference, from the production codec and app profile."""

from datetime import datetime

from custom_components.adjustable_bed.codec import mline as codec
from custom_components.adjustable_bed.codec import sinca_comfort as sinca_codec
from custom_components.adjustable_bed.profiles import mline as app
from custom_components.adjustable_bed.profiles import sinca_comfort as sinca

from ._common import Block, _block, _hex, _table

GUIDE = "docs/beds/mline.md"


def bed_types() -> dict[str, tuple[str, ...]]:
    return dict.fromkeys(app.PROFILES, ("mline",))


def profiles() -> str:
    return _block(
        _table(
            (
                "Protocol selector",
                "Bed type",
                "Refresh / release (ms)",
                "Status resend (ms)",
                "Startup",
            ),
            (
                (
                    p.key,
                    "mline",
                    f"{p.refresh_ms} / {p.release_ms}",
                    str(p.status_retry_ms) if p.status_retry_ms else "Skipped",
                    "Subscribe; read firmware/protocol; sync clock; check state",
                )
                for p in app.PROFILES.values()
            ),
        )
    )


def layouts() -> str:
    return _block(
        _table(
            ("Saved layout", "Controls"), ((key, label) for key, label in app.LAYOUT_LABELS.items())
        )
    )


def transports() -> str:
    return _block(
        _table(
            ("Role", "Service", "Characteristic"),
            (
                ("Write without response", codec.NORDIC_SERVICE, codec.NORDIC_WRITE),
                ("Notify", codec.NORDIC_SERVICE, codec.NORDIC_NOTIFY),
                ("Write without response", codec.FFE_SERVICE, codec.FFE_WRITE),
                ("Notify", codec.FFE_NOTIFY_SERVICE, codec.FFE_NOTIFY),
                ("Firmware string", codec.INFO_SERVICE, codec.FIRMWARE),
                ("Protocol string", codec.INFO_SERVICE, codec.PROTOCOL_STRING),
            ),
        )
    )


def commands() -> str:
    return _block(
        _table(
            ("Action", "P1", "P2"),
            (
                (name, _hex(codec.control(name, "sleep")), _hex(codec.control(name, "okin")))
                for name in codec.WORDS
            ),
        )
    )


def auxiliary() -> str:
    return _block(
        _table(
            ("Auxiliary action", "Frame"),
            ((name, _hex(data)) for name, data in codec.AUXILIARY.items()),
        )
    )


def sinca_profiles() -> str:
    return _block(
        _table(
            ("Receiver", "Release (ms)", "Status resend (ms)", "Clock writes"),
            (
                (
                    sinca.PROTOCOL_LABELS[p.key],
                    str(p.release_ms),
                    str(p.status_repeat_ms),
                    str(p.clock_count),
                )
                for p in sinca.PROFILES.values()
            ),
        )
    )


def sinca_layouts() -> str:
    return _block(_table(("Saved layout", "Controls"), sinca.LAYOUT_LABELS.items()))


def sinca_commands() -> str:
    legacy, extended = sinca.PROFILES["sleep"], sinca.PROFILES["okin"]
    motors = {
        f"{axis} {direction}": word
        for axis, words in sinca.MOTORS.items()
        for direction, word in zip(("up", "down"), words, strict=True)
    }
    commands = {
        **motors,
        **sinca.PRESETS,
        **{f"massage {name}": word for name, word in sinca.MASSAGE.items()},
        "light toggle": sinca.LIGHT,
        "STOP": 0,
    }
    return _block(
        _table(
            ("Control", "Basic frame", "Extended frame"),
            (
                (key, _hex(legacy.control(word)), _hex(extended.control(word)))
                for key, word in commands.items()
            ),
        )
    )


def sinca_settings() -> str:
    legacy, extended = sinca.PROFILES["sleep"], sinca.PROFILES["okin"]
    when = datetime(2026, 11, 24, 13, 37, 42)
    settings = (
        ("Settings entry", codec.AUXILIARY["checkState"]),
        ("Basic status", legacy.status),
        ("Extended status", extended.status),
        ("Basic alarm query", legacy.alarm_frame()),
        ("Extended alarm query", extended.alarm_frame()),
        ("Basic alarm disable", legacy.alarm_frame(disable=True)),
        ("Extended alarm disable", extended.alarm_frame(disable=True)),
        *((f"{key} clock (example)", codec.clock(key, when)) for key in sinca.PROFILES),
        ("Turn privacy on", codec.AUXILIARY["openPrivacyMode"]),
        ("Turn privacy off", codec.AUXILIARY["closePrivacyMode"]),
        ("Read new history", codec.AUXILIARY["gainNewHistoricalData"]),
        ("Read all history", codec.AUXILIARY["gainAllHistoricalData"]),
        ("Acknowledge history", codec.AUXILIARY["confirmGainHistoryData"]),
        ("Disable automatic anti-snore", codec.anti_snore(False, 1, 1)),
        ("Enable automatic anti-snore (head, medium)", sinca_codec.anti_snore(1, 3)),
        ("Demonstrate anti-snore (elevation)", codec.anti_snore(True, 1, 2, demo=True)),
    )
    return _block(_table(("Setting", "Frame"), ((label, _hex(frame)) for label, frame in settings)))


BLOCKS: list[Block] = [
    (GUIDE, "mline-profiles", profiles),
    (GUIDE, "mline-layouts", layouts),
    (GUIDE, "mline-transports", transports),
    (GUIDE, "mline-commands", commands),
    (GUIDE, "mline-auxiliary", auxiliary),
    (GUIDE, "sinca-profiles", sinca_profiles),
    (GUIDE, "sinca-layouts", sinca_layouts),
    (GUIDE, "sinca-commands", sinca_commands),
    (GUIDE, "sinca-settings", sinca_settings),
]
