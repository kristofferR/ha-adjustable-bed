"""Generated protocol tables for the Vindö guide."""

from custom_components.adjustable_bed.codec.linak import control_frame
from custom_components.adjustable_bed.const import (
    LINAK_CONTROL_CHAR_UUID,
    LINAK_CONTROL_SERVICE_UUID,
    LINAK_POSITION_BACK_UUID,
    LINAK_POSITION_LEG_UUID,
    LINAK_POSITION_SERVICE_UUID,
)
from custom_components.adjustable_bed.profiles import vindo
from custom_components.adjustable_bed.profiles.vindo import Opcode

from ._common import Block, _block, _hex, _table


def transport() -> str:
    return _block(
        _table(
            ("Role", "UUID"),
            (
                ("Control service", f"`{LINAK_CONTROL_SERVICE_UUID}`"),
                ("Control characteristic", f"`{LINAK_CONTROL_CHAR_UUID}`"),
                ("Position service", f"`{LINAK_POSITION_SERVICE_UUID}`"),
                ("Legs position characteristic", f"`{LINAK_POSITION_LEG_UUID}`"),
                ("Back position characteristic", f"`{LINAK_POSITION_BACK_UUID}`"),
            ),
        )
    )


def commands() -> str:
    motion = (
        ("Back up", True, None),
        ("Back down", False, None),
        ("Legs up", None, True),
        ("Legs down", None, False),
        ("Back and legs up", True, True),
        ("Back up, legs down", True, False),
        ("Back down, legs up", False, True),
        ("Back and legs down", False, False),
        ("STOP", None, None),
    )
    massage = (
        ("Head intensity up", Opcode.MASSAGE_HEAD_UP),
        ("Head intensity down", Opcode.MASSAGE_HEAD_DOWN),
        ("Foot intensity up", Opcode.MASSAGE_FOOT_UP),
        ("Foot intensity down", Opcode.MASSAGE_FOOT_DOWN),
        ("Toggle", Opcode.MASSAGE_TOGGLE),
    )
    lights = (
        ("On", Opcode.LIGHT_ON),
        ("Off", Opcode.LIGHT_OFF),
        ("Toggle", Opcode.LIGHT_TOGGLE),
        ("Step up", Opcode.LIGHT_STEP_UP),
        ("Step down", Opcode.LIGHT_STEP_DOWN),
    )
    header = ("Command", "Bytes")
    return _block(
        "### Motor Control",
        _table(
            header,
            (
                *((name, _hex(vindo.motion(back, legs))) for name, back, legs in motion),
                ("Flat", _hex(control_frame(Opcode.FLAT))),
            ),
        ),
        "### Massage",
        _table(
            header,
            (
                *((name, _hex(control_frame(opcode))) for name, opcode in massage),
                *(
                    (name, " / ".join(map(_hex, vindo.massage_pattern(index))))
                    for index, name in enumerate(vindo.PATTERNS)
                ),
            ),
        ),
        "### Lights",
        _table(header, ((name, _hex(control_frame(opcode))) for name, opcode in lights)),
    )


def timing() -> str:
    return _block(
        _table(
            ("Operation", "Timing"),
            (
                ("Held motion", f"Refresh {vindo.REFRESH_MS} ms after acknowledgement"),
                ("Movement deadline", f"{vindo.HOLD_LIMIT_MS / 1000:g} s"),
                (
                    "Position recall",
                    f"Stop within ±{vindo.TARGET_DEADBAND} raw counts on both axes",
                ),
                ("Massage pattern", f"{vindo.MASSAGE_STEP_MS} ms between acknowledged writes"),
                (
                    "Identify device",
                    f"{vindo.IDENTIFY_ON_MS} ms on, {vindo.IDENTIFY_OFF_MS} ms off",
                ),
            ),
        )
    )


BLOCKS: list[Block] = [
    ("docs/beds/vindo.md", "vindo-transport", transport),
    ("docs/beds/vindo.md", "vindo-commands", commands),
    ("docs/beds/vindo.md", "vindo-timing", timing),
]
