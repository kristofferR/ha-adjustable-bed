"""SILVERmotion reference tables from its shipped codec and Android profile."""

from custom_components.adjustable_bed.codec import silvermotion as codec
from custom_components.adjustable_bed.profiles import silvermotion as app

from ._common import Block, _block, _hex, _table

GUIDE = "docs/beds/silvermotion.md"


def bed_types() -> dict[str, tuple[str, ...]]:
    return {app.ANDROID.key: ("silvermotion",)}


def profiles() -> str:
    return _block(
        _table(
            ("Profile", "Bed type", "Sizes", "Startup"),
            (("Android", "silvermotion", ", ".join(app.SIZES.values()), "Subscribe only"),),
        )
    )


def transports() -> str:
    return _block(
        _table(
            ("Role", "Service", "Characteristic"),
            (
                (role, codec.SERVICE, codec.CHARACTERISTIC)
                for role in ("Write without response", "Notify")
            ),
        )
    )


def commands() -> str:
    return _block(
        _table(
            ("Action", "LDP input", "Repeat / delay", "Final frame"),
            (
                (
                    app.LABELS.get(key, key.replace("_", " ")),
                    _hex(payload),
                    f"{app.repeat_count(key)} / {app.ANDROID.delay}",
                    _hex(codec.encode(payload, app.repeat_count(key), app.ANDROID.delay)),
                )
                for key, payload in app.COMMANDS.items()
            ),
        )
    )


def timing() -> str:
    p = app.ANDROID
    return _block(
        _table(
            ("Operation", "Milliseconds"),
            (
                ("Movement refresh", str(p.refresh_ms)),
                ("Maximum movement", str(p.movement_ceiling_ms)),
                ("Chunk pacing", str(p.chunk_ms)),
                ("Response timeout", str(p.response_ms)),
                ("Recall enqueue gap", str(p.recall_gap_ms)),
            ),
        )
    )


BLOCKS: list[Block] = [
    (GUIDE, f"silvermotion-{key}", render)
    for key, render in (
        ("profiles", profiles),
        ("transports", transports),
        ("commands", commands),
        ("timing", timing),
    )
]
