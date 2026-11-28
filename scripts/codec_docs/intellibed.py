"""Intellibed's implemented controls, grouped under their proven codecs."""

from custom_components.adjustable_bed.profiles.intellibed import PROFILES
from scripts.codec_docs._common import _block, _hex, _table


def controls(key: str) -> str:
    p = PROFILES[key]
    return _block(
        _table(
            ("Role", "Service", "Characteristic"),
            (
                ("Write (HA acknowledged path)", f"`{p.write_service}`", f"`{p.write_uuid}`"),
                ("Subscribe", f"`{p.notify_service}`", f"`{p.notify_uuid}`"),
                (
                    "App UI dispatch filter, not a subscription",
                    "Not applicable",
                    f"`{p.ui_notify_uuid}`",
                ),
            ),
        ),
        _table(
            ("Control", "Bytes", "Delay"),
            (
                (action.label, _hex(p.encode(action)), f"{action.delay_ms} ms, once")
                for action in p.actions.values()
            ),
        ),
    )


BLOCKS = [
    ("docs/beds/keeson.md", "intellibed-old", lambda: controls("old")),
    ("docs/beds/motomotion.md", "intellibed-hhc", lambda: controls("hhc")),
]
