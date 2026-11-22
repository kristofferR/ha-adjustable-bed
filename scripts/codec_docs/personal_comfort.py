"""Personal Comfort tables from the shipped route and encoder data."""

from custom_components.adjustable_bed.codec import personal_comfort as codec
from custom_components.adjustable_bed.codec.instant_comfort import channel_target
from custom_components.adjustable_bed.profiles.personal_comfort import MODELS, PROFILES, ROUTES
from scripts.codec_docs._common import Block, _block, _hex, _table

GUIDE = "docs/beds/personal-comfort.md"


def bed_types() -> dict[str, tuple[str, ...]]:
    return dict.fromkeys(PROFILES, ("personal_comfort",))


def profiles() -> str:
    return _block(
        _table(
            ("Route", "Controller", "Movement and release"),
            (
                (
                    key,
                    label,
                    "200 ms refresh; release ends refresh"
                    if key == "malouf"
                    else "One write; release to captured axis"
                    if key == "reverie_v2"
                    else "One write; global release"
                    if key == "reverie_v1"
                    else "Firmness target, no hardware STOP"
                    if key != "anm5"
                    else "Firmness target; pump-wide STOP",
                )
                for key, label in ROUTES.items()
            ),
        ),
        _table(
            ("Base model", "Pillow", "Massage"),
            (
                (
                    label,
                    "Yes on Malouf / V2" if key in ("pf4", "pf42") else "No",
                    "Yes" if key in ("pf3", "pf4", "other") else "No",
                )
                for key, label in MODELS.items()
            ),
        ),
    )


def transports() -> str:
    return _block(
        _table(
            ("Route", "Service", "Write", "Notify"),
            (
                (key, f"`{p.service}`", f"`{p.write}`", f"`{p.notify}`" if p.notify else "None")
                for key, p in PROFILES.items()
            ),
        )
    )


def commands() -> str:
    malouf = PROFILES["malouf"]
    return _block(
        "Malouf route (fixed side 0):",
        _table(
            ("Action", "Bytes"),
            (
                (action.replace("_", " "), _hex(malouf.frame(code)))
                for action, code in (malouf.codes or {}).items()
            ),
        ),
        _table(
            ("Memory", "Recall", "Save"),
            (
                (str(slot), _hex(malouf.frame(recall)), _hex(malouf.frame(save)))
                for slot, (recall, save) in enumerate(malouf.memory, 1)
            ),
        ),
        "Reverie base route:",
        _table(
            ("Action", "Bytes"),
            (
                (action.replace("_", " "), _hex(codec.base5(action)))
                for action in (*codec.BASE5, "light_toggle", "massage_mode", "stop")
            ),
        ),
        "Reverie base V2 route:",
        _table(
            ("Action", "Characteristic", "Bytes"),
            (
                (action.replace("_", " "), f"`{characteristic}`", _hex(packet))
                for action in (*codec.BASE6, "massage_mode")
                for characteristic, packet in (codec.base6(action),)
            ),
        ),
        "V2 lighting writes 100 for on and 0 for off to db8010a0. Each exposed motor releases with 0 to its own characteristic. Massage pattern cycles 1 through 5. V2 head and foot massage each write 50; neither exposes an absolute intensity or a decrement.",
    )


def instant_channels() -> str:
    return _block(_table(
        ("Layout", "Control", "Channel", "Target 5", "Target 50"),
        ((layout, control, str(channel), _hex(channel_target(channel, 5)), _hex(channel_target(channel, 50)))
         for layout, controls in (
             ("Two channels", (("Left", 0), ("Right", 1))),
             ("Four channels", (("Left main", 0), ("Left lumbar", 1), ("Right main", 2), ("Right lumbar", 3))),
         ) for control, channel in controls),
    ))


BLOCKS: tuple[Block, ...] = (
    (GUIDE, "instant-comfort-channels", instant_channels),
    (GUIDE, "personal-comfort-profiles", profiles),
    (GUIDE, "personal-comfort-transports", transports),
    (GUIDE, "personal-comfort-commands", commands),
)
