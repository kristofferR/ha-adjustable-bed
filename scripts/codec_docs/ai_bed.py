"""AI Bed reference tables rendered through their proved codecs."""

from custom_components.adjustable_bed.beds.ai_bed.controller import FIXED, FIXED_LABELS
from custom_components.adjustable_bed.codec import ai_bed as codec
from custom_components.adjustable_bed.profiles.ai_bed import PROFILES

from ._common import Block, _block, _hex, _table


def route_commands(route: str) -> list[str]:
    profile = PROFILES[route]
    return _table(
        ("Action", "Frame", "Gesture"),
        (
            (
                action.label,
                _hex(profile.encode(action)),
                "Held" if action.motion else "Save" if action.save else "Recall",
            )
            for action in profile.actions.values()
        ),
    )


def primary() -> str:
    return _block(
        [
            *route_commands("305"),
            "",
            *_table(
                ("Action", "Frame"),
                (
                    (FIXED_LABELS[key], _hex(codec.frame(opcode, params)))
                    for key, (opcode, params) in FIXED.items()
                ),
            ),
        ]
    )


def routes() -> str:
    return _block(
        _table(
            ("Profile", "Service", "Write", "Notify", "Refresh ms", "Release frames"),
            (
                (p.key, p.service, p.write, p.notify, str(p.refresh_ms), str(p.release_count))
                for p in PROFILES.values()
                if p.key != "unselected"
            ),
        )
    )


BLOCKS: list[Block] = [
    ("docs/beds/ai_bed.md", "ai-bed-routes", routes),
    ("docs/beds/ai_bed.md", "ai-bed-primary", primary),
    ("docs/beds/limoss.md", "ai-bed-limos", lambda: _block(route_commands("limos"))),
    ("docs/beds/richmat.md", "ai-bed-hj001", lambda: _block(route_commands("hj001"))),
    ("docs/beds/richmat.md", "ai-bed-qrrm", lambda: _block(route_commands("qrrm"))),
]
