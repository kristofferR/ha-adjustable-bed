"""BERUN catalogs over the existing Keeson, ORE and Okin N-frame codecs."""

from custom_components.adjustable_bed.profiles import berun as app

from ._common import Block, _block, _hex, _table

GUIDE = "docs/beds/berun.md"


def commands() -> str:
    return _block(
        _table(
            ("Version", "Control", "Frame"),
            (
                (key, action.key, _hex(profile.frame(action.mask)))
                for key, profile in app.PROFILES.items()
                for action in profile.actions
            ),
        )
    )


def transports() -> str:
    return _block(_table(("Service", "Write", "Notify service", "Notify"), app.ROLES))


BLOCKS: list[Block] = [(GUIDE, "berun-commands", commands), (GUIDE, "berun-transports", transports)]
