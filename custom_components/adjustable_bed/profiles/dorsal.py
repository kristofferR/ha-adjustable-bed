"""Dorsal's exact product layouts and Roomi's fixed-frame controls."""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Final, Literal, cast

from ..const import DORSAL_ROUTES

ROUTES: Final = DORSAL_ROUTES
PROFILE_PROBES: Final = (
    ("deviceFunctionItemExitLimit", 0),
    ("deviceFunctionItemCheckClock", 1),
    ("deviceFunctionItemCheckLight", 1),
)
REFRESH_SECONDS: Final = 0.1
PROBE_SECONDS: Final = 0.3
type Opcode = tuple[int, int]
type Release = Literal["none", "stop_if_ticked", "short_if_before_hold", "stop_always"]


@dataclass(frozen=True, slots=True)
class Control:
    key: str
    action: str
    short: Opcode | None
    sustain: Opcode | None
    long: Opcode | None
    release: Release
    fixed: bool = False


@dataclass(frozen=True, slots=True)
class Product:
    controls: tuple[Control, ...]
    alarm_modes: dict[str, int]


type ActionRow = tuple[str, Opcode | None, Opcode | None, Opcode | None, Release]
type ProfileRow = tuple[str, dict[str, int]]


@cache
def products() -> dict[str, Product]:
    """Read compact shared layouts once, away from the Bluetooth receive path."""
    path = Path(__file__).with_name("data") / "dorsal.json.gz"
    with gzip.open(path, "rt", encoding="utf-8") as source:
        catalog = json.load(source)
    controls = {
        key: Control(
            key,
            action,
            (short[0], short[1]) if short is not None else None,
            (sustain[0], sustain[1]) if sustain is not None else None,
            (long[0], long[1]) if long is not None else None,
            release,
        )
        for key, (action, short, sustain, long, release) in cast(
            "dict[str, ActionRow]", catalog["actions"]
        ).items()
    }
    layouts = {
        layout: tuple(controls[key] for key in keys)
        for layout, keys in cast("dict[str, list[str]]", catalog["layouts"]).items()
    }
    return {
        code: Product(layouts[layout], modes)
        for code, (layout, modes) in cast("dict[str, ProfileRow]", catalog["profiles"]).items()
    }


# The profile module is preloaded by the factory and setup in HA’s import executor.
products()


def code_for(route: object, exact: object) -> str | None:
    if route in ("cprn", "corn"):
        return str(route).upper()
    if route in ("restored", "roomi") and isinstance(exact, str) and exact in products():
        return exact
    return None


def _roomi(action: str, code: int, *, sustain: bool = False, save: int | None = None) -> Control:
    wire = (code, code)
    return Control(
        f"roomi_{action}",
        f"deviceFunctionItem{action}",
        None if sustain else wire,
        wire if sustain else None,
        (save, save) if save is not None else None,
        "stop_always",
        fixed=True,
    )


ROOMI: Final = (
    _roomi("HeadUp", 0x24, sustain=True),
    _roomi("HeadDown", 0x25, sustain=True),
    _roomi("FootUp", 0x26, sustain=True),
    _roomi("FootDown", 0x27, sustain=True),
    _roomi("LumberUp", 0x3F, sustain=True),
    _roomi("LumberDown", 0x40, sustain=True),
    _roomi("PillowUp", 0x41, sustain=True),
    _roomi("PillowDown", 0x42, sustain=True),
    _roomi("MotorReset", 0x31),
    _roomi("BedLight", 0x3C),
    _roomi("MemoryPosition1", 0x2E, save=0x2B),
    _roomi("MemoryPosition2", 0x2F, save=0x2C),
    _roomi("AntiSnoring", 0x46, save=0x69),
    _roomi("RelaxPosition", 0x59, save=0x65),
    _roomi("ReadingPosition", 0x58, save=0x64),
    _roomi("ZeroGravity", 0x45, save=0x66),
    _roomi("Massage10MinuteTimer", 0x5F),
    _roomi("Massage20MinuteTimer", 0x63),
    _roomi("Massage30MinuteTimer", 0x61),
    _roomi("MassageSwitch", 0x5E),
    _roomi("MassageModeChange", 0x48),
    _roomi("MassageHeadInstensityStrengthen", 0x4C),
    _roomi("MassageFootInstensityStrengthen", 0x4E),
)
ROOMI_SNORE: Final = Control(
    "roomi_snore_trigger", "deviceFunctionItemAntiSnoring", (0x46, 0x46), None, None, "none"
)
