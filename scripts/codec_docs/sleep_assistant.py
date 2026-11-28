"""Render the Sleep Assistant codec reference from shipped data."""

from custom_components.adjustable_bed.codec import sleep_assistant as codec
from custom_components.adjustable_bed.profiles import sleep_assistant as app

from . import _ergosportive
from ._common import _block, _hex, _table

GUIDE = "docs/beds/sleep-assistant.md"


def bed_types() -> dict[str, tuple[str, ...]]:
    return {"sleep_assistant": ("sleep_assistant",), "ergosportive": ("ergosportive:remote", "ergosportive:hardware221")}


def profile() -> str:
    return _block(
        _table(
            ("Profile", "Bed type", "Refresh", "Optional controls"),
            [
                (
                    "sleep_assistant",
                    "sleep_assistant",
                    "200 ms",
                    ", ".join(app.MASSAGE_KEYS.values()),
                )
            ],
        )
    )


def transports() -> str:
    return _block(
        _table(
            ("Role", "Service", "Characteristic"),
            [("Write", codec.SERVICE, codec.WRITE), ("Notify", codec.SERVICE, codec.NOTIFY)],
        )
    )


def commands() -> str:
    return _block(
        _table(
            ("Action", "Frame"),
            ((name, _hex(codec.instruction(word))) for name, word in app.WORDS.items()),
        )
    )


def settings() -> str:
    rows = [
        ("Alarm query", codec.ALARM_QUERY),
        ("Anti-snore query", codec.ANTI_SNORE_QUERY),
        ("Anti-snore hours (6, 21)", codec.anti_hours()),
        ("Storage query", codec.storage_query()),
        ("Light query", codec.light()),
    ]
    rows += [(f"Clear alarm {slot}", codec.clear_alarm(slot)) for slot in range(1, 7)]
    rows += [(f"Local storage {value}", codec.storage(value)) for value in (0, 1)]
    rows += [(f"Light palette {value}", codec.rgb(0, value)) for value in range(7)]
    return _block(_table(("Setting", "Frame"), ((name, _hex(frame)) for name, frame in rows)))


BLOCKS = [
    (GUIDE, "sleep-assistant-" + name, renderer)
    for name, renderer in (
        ("profiles", profile),
        ("transports", transports),
        ("commands", commands),
        ("settings", settings),
    )
]

BLOCKS.extend(_ergosportive.BLOCKS)
