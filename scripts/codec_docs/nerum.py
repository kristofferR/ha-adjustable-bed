"""Nerum app tables rendered from the profiles that drive existing codecs."""

from custom_components.adjustable_bed.profiles import nerum as app

from ._common import Block, _block, _hex, _table

GUIDE = "docs/beds/nerum.md"


def commands() -> str:
    return _block(
        _table(
            ("Protocol", "Control", "Frame"),
            (
                (key, name, _hex(frame))
                for key, profile in app.PROFILES.items()
                for name, frame in profile.frames.items()
            ),
        )
    )


def transports() -> str:
    return _block(
        _table(
            ("Protocol", "Write service / characteristic", "Notify service / characteristic"),
            (
                (key, f"{p.service} / {p.write}", f"{p.notify_service} / {p.notify}")
                for key, p in app.PROFILES.items()
            ),
        )
    )


def profiles() -> str:
    return _block(
        _table(
            (
                "Protocol",
                "Carrier",
                "Refresh ms",
                "Release offsets ms",
                "Memory recalls",
                "Clock / alarms",
            ),
            (
                (
                    key,
                    {
                        "p1": "Okin ORE",
                        "p2": "Keeson E6 little-endian",
                        "p3": "Okin N-frame 40-bit",
                    }[key],
                    str(p.refresh_ms),
                    ", ".join(map(str, p.release_ms)),
                    "1" if key == "p1" else "2",
                    "No" if key == "p1" else "Clock, three alarms",
                )
                for key, p in app.PROFILES.items()
            ),
        )
    )


BLOCKS: list[Block] = [
    (GUIDE, f"nerum-{name}", fn)
    for name, fn in (("commands", commands), ("transports", transports), ("profiles", profiles))
]
