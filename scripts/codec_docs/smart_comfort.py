"""Generated Smart Comfort codec/profile reference tables."""

from custom_components.adjustable_bed.codec import smart_comfort as codec
from custom_components.adjustable_bed.profiles.smart_comfort import PROFILES

from ._common import Block, _block, _hex, _table

GUIDE = "docs/beds/smart-comfort.md"


def bed_types() -> dict[str, tuple[str, ...]]:
    return {key: (f"smart_comfort_{key}",) for key in PROFILES}


def profiles() -> str:
    return _block(
        _table(
            (
                "Profile / bed type",
                "App version",
                "Refresh / release (ms)",
                "Notify delay (ms)",
                "System timeout (ms)",
                "Startup",
            ),
            (
                (
                    f"`{p.key}` / `smart_comfort_{p.key}`",
                    p.version,
                    f"{p.refresh_ms} / {p.release_ms}",
                    str(p.notify_delay_ms)
                    if p.notify_delay_ms is not None
                    else "Unproven; no added delay",
                    str(p.system_timeout_ms),
                    "Subscribe, system query, device query",
                )
                for p in PROFILES.values()
            ),
        )
    )


def transports() -> str:
    return _block(
        _table(
            ("Role", "Service UUID", "Characteristic UUID"),
            (
                ("Control / query", f"`{codec.SERVICE_UUID}`", f"`{codec.WRITE_UUID}`"),
                ("Notifications", f"`{codec.NOTIFY_SERVICE_UUID}`", f"`{codec.NOTIFY_UUID}`"),
                ("Raw rename", f"`{codec.NAME_SERVICE_UUID}`", f"`{codec.NAME_UUID}`"),
            ),
        )
    )


def commands() -> str:
    actions = (
        *codec.MOTORS,
        *codec.ACCESSORIES,
        "base_brightness",
        "read_brightness",
        "color",
        "query_system",
        "query_device",
    )
    return _block(
        _table(
            ("Action", "Seat 0 frame", "Execution"),
            (
                (
                    action,
                    _hex(codec.command(action)),
                    "Held"
                    if action
                    in (
                        "head_up",
                        "head_down",
                        "reclining_up",
                        "reclining_down",
                        "lumbar_up",
                        "lumbar_down",
                        "home",
                    )
                    else "Release"
                    if action == "stop"
                    else "Once",
                )
                for action in actions
            ),
        )
    )


def models() -> str:
    return _block(
        _table(
            ("Code", "Layout", "Reported motors", "Stored addresses", "Selectable addresses"),
            (
                (f"`{code:02X}`", layout, str(motors), str(stored), str(selected))
                for code, (layout, motors, stored, selected) in codec.MODELS.items()
            ),
        )
    )


BLOCKS: list[Block] = [
    (GUIDE, "smart-comfort-profiles", profiles),
    (GUIDE, "smart-comfort-transports", transports),
    (GUIDE, "smart-comfort-commands", commands),
    (GUIDE, "smart-comfort-models", models),
]
