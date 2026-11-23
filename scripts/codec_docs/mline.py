"""Generated M Line reference, from the production codec and app profile."""

from custom_components.adjustable_bed.codec import mline as codec
from custom_components.adjustable_bed.profiles import mline as app

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


BLOCKS: list[Block] = [
    (GUIDE, "mline-profiles", profiles),
    (GUIDE, "mline-layouts", layouts),
    (GUIDE, "mline-transports", transports),
    (GUIDE, "mline-commands", commands),
    (GUIDE, "mline-auxiliary", auxiliary),
]
