"""Alya app tables over the existing ORE, Keeson and N-frame codecs."""

from custom_components.adjustable_bed.beds.alya.protocol import TRANSPORTS, alarm_types
from custom_components.adjustable_bed.profiles.alya import PROFILES
from scripts.codec_docs._common import _block, _hex, _table

GUIDE = "docs/beds/alya.md"


def bed_types() -> dict[str, tuple[str, ...]]:
    return dict.fromkeys(PROFILES, ("alya",))


def transports() -> str:
    return _block(
        _table(
            (
                "Route",
                "Write service",
                "Write characteristic",
                "Notify service",
                "Notify characteristic",
            ),
            (
                (
                    key,
                    f"`{t.write_service}`",
                    f"`{t.write}`",
                    f"`{t.notify_service}`",
                    f"`{t.notify}`",
                )
                for key, t in TRANSPORTS.items()
            ),
        )
    )


def layouts() -> str:
    return _block(
        _table(
            (
                "Profile",
                "Route",
                "Axes (HA)",
                "Memory recalls",
                "Side controls",
                "Refresh / each release delay (ms)",
                "Alarm wake modes",
            ),
            (
                (
                    f"`{p.key}`",
                    p.protocol,
                    ", ".join(p.axes) + (", HPS buttons" if p.motors == 5 else ""),
                    "2" if "m2" in p.commands else "1",
                    "A / B / both" if p.side_controls else "Both",
                    f"{p.refresh_ms} / {p.release_ms}",
                    ", ".join(alarm_types(p))
                    if p.protocol != "P1" and p.key != "dacheng_2"
                    else "None",
                )
                for p in PROFILES.values()
            ),
        )
    )


def commands() -> str:
    parts: list[str | list[str]] = []
    for p in PROFILES.values():
        parts.extend(
            (
                f"### {p.name}",
                _table(
                    ("App action", "Frame (side 0)", "Kind"),
                    (
                        (
                            key,
                            _hex(cmd.encode(p.protocol)),
                            "One public STOP" if key == "stop" else "Held / released",
                        )
                        for key, cmd in p.commands.items()
                    ),
                ),
            )
        )
    return _block(*parts)


def settings() -> str:
    from datetime import datetime

    from custom_components.adjustable_bed.beds.alya.protocol import alarm_frame, clock_frame, query

    now = datetime.fromisoformat("2026-11-27T12:34:56+00:00")
    rows: list[tuple[str, ...]] = []
    for p in PROFILES.values():
        rows.append((p.key, "Query massage", _hex(query(p.protocol))))
        if p.protocol != "P1" and p.key != "dacheng_2":
            rows.extend(
                (
                    (p.key, "Query alarm", _hex(query(p.protocol, True))),
                    (
                        p.key,
                        "Clock (2026-11-27 12:34:56, local)",
                        _hex(clock_frame(p.protocol, now)),
                    ),
                    (
                        p.key,
                        "Alarm (06:45, repeat 0x80, ZG, side 0)",
                        _hex(alarm_frame(p.protocol, 6, 45, -128, 13, 0)),
                    ),
                )
            )
    return _block(_table(("Profile", "Setting example", "Frame"), rows))


BLOCKS = [
    (GUIDE, "alya-transports", transports),
    (GUIDE, "alya-layouts", layouts),
    (GUIDE, "alya-commands", commands),
    (GUIDE, "alya-settings", settings),
]
