"""Generated blocks of the JMC400 codec guide."""

from __future__ import annotations

from custom_components.adjustable_bed.beds.svane.state import svane_preferences
from custom_components.adjustable_bed.codec import jmc
from custom_components.adjustable_bed.const import (
    BED_TYPE_JENSEN,
    BED_TYPE_SVANE,
    SVANE_VARIANT_JMC,
)
from custom_components.adjustable_bed.profiles.jmc import PROFILES
from scripts.codec_docs._common import Block, _block, _hex, _table

GUIDE = "docs/beds/jmc.md"
_PROFILES = {
    "jensen": ("[Jensen Adjustable Sleep](#jensen-adjustable-sleep)", f"`{BED_TYPE_JENSEN}`"),
    "svane_remote": (
        "[Svane Remote](#svane-remote)",
        f"`{BED_TYPE_SVANE}`, variant `{SVANE_VARIANT_JMC}`; its lamp frames also on `auto`",
    ),
}


def _spelled(data: bytes) -> str:
    return data.hex(" ").upper()


def render_jmc_profiles() -> str:
    rows = []
    for key, (name, bed_type) in _PROFILES.items():
        profile = PROFILES[key]
        fan = "none" if profile.fan is None else f"`14 level {_spelled(profile.fan)}`"
        rows.append(
            (
                name,
                bed_type,
                f"`13 02 level {_spelled(profile.light_on)}`",
                _hex(jmc.light(0, profile.light_off)),
                fan,
            )
        )
    return _block(_table(("Profile", "Bed type", "Light level", "Light off", "Fan level"), rows))


def render_jmc_transports() -> str:
    return _block(
        _table(
            ("Role", "UUID"),
            (
                ("Service", f"`{jmc.SERVICE_UUID}`"),
                ("Commands and reports (write, notify)", f"`{jmc.CHAR_UUID}`"),
            ),
        )
    )


def render_jmc_commands() -> str:
    axes = {True: "up", False: "down"}
    motion = [(f"Head {axes[head]}", _hex(jmc.motion(head, None))) for head in axes] + [
        (f"Foot {axes[foot]}", _hex(jmc.motion(None, foot))) for foot in axes
    ]
    motion += [
        (f"Head {axes[head]}, foot {axes[foot]}", _hex(jmc.motion(head, foot)))
        for head in axes
        for foot in axes
    ]
    read, tv = svane_preferences(None)[1]
    rows = [
        ("STOP", _hex(jmc.command(jmc.STOP))),
        *motion,
        ("Flat", _hex(jmc.command(jmc.FLAT))),
        ("Save device memory", _hex(jmc.command(jmc.MEMORY_SAVE))),
        ("Recall device memory", _hex(jmc.command(jmc.MEMORY_RECALL))),
        ("Position query", _hex(jmc.command(jmc.POSITION_QUERY))),
        (
            "Go to position",
            f"`10 04` + four position bytes: {_hex(jmc.goto(jmc.position(30771, 30000)))}"
            f" is head 30771, foot 30000; {_hex(jmc.goto(read))} and {_hex(jmc.goto(tv))}"
            " are Svane Remote's Read and TV defaults",
        ),
        ("Config request", _hex(jmc.CONFIG_REQUEST)),
        (
            "Massage",
            f"`12 head foot wave 00 00`, levels 0-10: {_hex(jmc.massage(6, 0, 6))}"
            " is head 6, wave 6",
        ),
        ("Light", "`13 02 level` + the profile's three bytes"),
        ("Fan", "`14 level` + the profile's four bytes"),
        ("PIN", f"`1E` + one byte per digit: {_hex(jmc.pin('3060'))} is 3060"),
    ]
    return _block(_table(("Command", "Frame"), rows))


BLOCKS: list[Block] = [
    (GUIDE, "jmc-profiles", render_jmc_profiles),
    (GUIDE, "jmc-transports", render_jmc_transports),
    (GUIDE, "jmc-commands", render_jmc_commands),
]
