"""Relax Motion's model, app-route and timing gates. No model is selected by default."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from ..beds.relax_motion.catalog import CHEERS, RELAX, Model
from ..codec.relax_motion import SERVICE
from ..execution import STREAM_HOLD, ExecutionCapabilities

ROUTES: Final = {
    "relax": "Relax Motion",
    "cheers_zh": "Cheers alternative page, Chinese labels",
    "cheers_en": "Cheers alternative page, English labels",
    "legacy": "Older motor page",
}
P1_AXES: Final = {"back": 0x103, "legs": 0x107, "lumbar": 0x10B}
EDITOR_STOPS: Final = {"back": 0x100, "legs": 0x104, "lumbar": 0x108}
P2_AXES: Final = {"back": (1, 2), "legs": (4, 8), "lumbar": (16, 32)}
PRESETS: Final = {"flat": 0x111, "anti_snore": 0x301, "tv": 0x302, "zero_g": 0x303}


@dataclass(frozen=True, slots=True)
class RelaxMotionProfile:
    key: str
    execution: ExecutionCapabilities
    dispatch_ms: int = 200
    refresh_ms: int = 100
    release_ms: tuple[int, ...] = (100, 200)


PROFILES: Final = {
    "p1": RelaxMotionProfile("p1", ExecutionCapabilities(hold="latched")),
    "p2": RelaxMotionProfile("p2", STREAM_HOLD),
}


def model(number: int, route: str) -> Model:
    catalog = CHEERS if route.startswith("cheers_") else RELAX
    if number in catalog:
        return catalog[number]
    # These are the app's two explicit complement branches, using the supplied
    # numeric identity, rather than guessing a model when identity is absent.
    return Model(
        number,
        str(number),
        "two_back_foot",
        False,
        False,
        False,
        False,
        2 if route.startswith("cheers_") else 0,
        False,
        route.startswith("cheers_"),
        False,
        False,
    )


def axes(selected: Model) -> tuple[str, ...]:
    if selected.layout in ("bed_one", "bed_store"):
        return ("all_motors",)
    if selected.layout.startswith("three_"):
        return ("back", "lumbar", "legs")
    return ("back", "legs")


def advertisement(manufacturer: dict[int, bytes], *, legacy: bool = False) -> int | None:
    """Rebuild Under21's company-prefixed, company-sorted manufacturer bytes."""
    raw = b"".join(
        company.to_bytes(2, "little") + value for company, value in sorted(manufacturer.items())
    )
    if not raw:
        return None
    return raw[0] if legacy or raw[0] != 89 or len(raw) <= 4 else raw[0] + raw[2] + raw[3] + raw[4]


# Command tables shared by controller and the generated reference.
MEMORY: Final = {slot: (0x30F + 2 * slot, 0x30E + 2 * slot) for slot in range(1, 6)}
MASSAGE: Final = {
    "head": (0x123, 0x201, 0x202, 0x203),
    "foot": (0x124, 0x204, 0x205, 0x206),
}
STRENGTH: Final = {"head": (0x220, 0x221, 0x222), "foot": (0x228, 0x229, 0x22A)}
RHYTHM: Final = (0x200, 0x230, 0x231)
SETTINGS: Final = {"light_time": 0x1101, "interval": 0x1105, "snore": 0x1103}


def model_number(value: object) -> int | None:
    """Accept canonicalizable non-negative ASCII decimal identities only."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    raw = str(value)
    if not raw or not raw.isascii() or not raw.isdecimal():
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def route_name(value: object) -> str:
    return "relax" if value is None or value == "auto" else str(value)


def discovery_matches(name: str | None, services: Sequence[str], *, route: str = "relax") -> bool:
    if not isinstance(name, str) or not name:
        return False
    if route == "legacy":
        return True
    return not name.startswith("ZKYL-") and bool(services) and services[0].lower() == SERVICE
