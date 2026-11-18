"""Generate SUTA's selectors, complete command domains and panel timing."""

from custom_components.adjustable_bed.codec import suta as codec
from custom_components.adjustable_bed.profiles import suta as app

from ._common import Block, _block, _hex, _table

GUIDE = "docs/beds/suta.md"


def routes() -> str:
    return _block(_table(("Name route", "Controller"), ((key, value or "No controller") for key, value in app.ROUTES.items())))


def commands() -> str:
    rows = []
    for key, profile in app.PROFILES.items():
        for action, command in profile.commands.items():
            rows.extend((key, action + (" " + suffix if suffix else ""), _hex(codec.text(command.text + suffix))) for suffix in command.suffixes or ("",))
    rows.extend(("Shared text", action, _hex(codec.text(command.text))) for action, command in app.SHARED.items())
    for action in app.BINARY.values():
        rows.extend(("/".join(action.controllers), action.key + " " + p[6:].hex(" "), _hex(codec.from_prefix(p))) for p in action.prefixes)
    return _block(_table(("Panel", "Action / parameter", "Frame"), rows))


def timing() -> str:
    return _block(_table(
        ("Panel", "Refresh ms", "Save threshold s", "Action", "Count / initial / interval ms", "Source owner"),
        ((key, str(profile.refresh_ms), str(profile.threshold_s), action,
          f"{command.count} / {command.delay_ms} / {command.interval_ms}", command.source_scope)
         for key, profile in app.PROFILES.items() for action, command in profile.commands.items()),
    ))


BLOCKS: list[Block] = [
    (GUIDE, "suta-routes", routes),
    (GUIDE, "suta-commands", commands),
    (GUIDE, "suta-timing", timing),
]
