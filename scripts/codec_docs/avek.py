"""AVEK reference tables from its codec and fixed app profile."""

from custom_components.adjustable_bed.codec import avek as codec
from custom_components.adjustable_bed.profiles.avek import AVEK
from scripts.codec_docs._common import Block, _block, _hex, _table

GUIDE = "docs/beds/avek.md"


def transports() -> str:
    return _block(
        _table(
            ("Role", "UUID"),
            (
                ("Service", f"`{codec.SERVICE_UUID}`"),
                ("Write", f"`{codec.WRITE_UUID}`"),
                ("Notify", f"`{codec.NOTIFY_UUID}`"),
            ),
        )
    )


def profiles() -> str:
    return _block(
        _table(
            (
                "Profile / bed type",
                "Name prefixes (case-sensitive)",
                "Refresh",
                "App Initial waiter",
                "HA Initial limit",
                "HA identity wait",
                "Initial endpoint (raw count)",
            ),
            (
                (
                    f"`{AVEK.key}`",
                    ", ".join(f"`{p}*`" for p in AVEK.name_prefixes),
                    f"{AVEK.refresh_ms} ms",
                    f"{AVEK.initial_checks} × {AVEK.initial_check_ms} ms, conditional cancellation",
                    f"{AVEK.initial_limit_ms} ms",
                    f"{AVEK.identity_timeout_s:g} s",
                    str(AVEK.initial_endpoint),
                ),
            ),
        )
    )


def commands() -> str:
    return _block(
        _table(
            ("Control", "Word", "Bytes"),
            ((a.label, f"`{a.word:04X}`", _hex(a.frame)) for a in AVEK.actions),
        ),
        _table(
            ("Identity", "Bytes"),
            (
                ("Exact device challenge", _hex(codec.IDENTITY_REQUEST)),
                (
                    "Example reply, app ID 001122334455",
                    _hex(codec.identity(bytes.fromhex("001122334455"))),
                ),
            ),
        ),
    )


BLOCKS: list[Block] = [
    (GUIDE, "avek-transports", transports),
    (GUIDE, "avek-profiles", profiles),
    (GUIDE, "avek-commands", commands),
]
