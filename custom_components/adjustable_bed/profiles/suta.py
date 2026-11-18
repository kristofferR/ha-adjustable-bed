"""Typed SUTA app catalog and independent UI/full-name transport selectors.

Source: accepted com.shuta.smart_home 3.20.0 (80). Hardware unverified.
The frozen July delivery does not attest to a later app version.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal

from ..codec import suta as codec
from ..execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities

Kind = Literal["tap", "motion", "save", "dt", "lv", "fan", "stop", "clock"]


@dataclass(frozen=True, slots=True)
class Command:
    text: str
    kind: Kind
    count: int
    delay_ms: int
    interval_ms: int
    suffixes: tuple[str, ...]
    source_scope: str


@dataclass(frozen=True, slots=True)
class SutaProfile:
    key: str
    commands: dict[str, Command]
    threshold_s: int
    refresh_ms: int
    layout: str | None

    execution: ExecutionCapabilities = field(default=NO_EXECUTION_CAPABILITIES, init=False)

    def __post_init__(self) -> None:
        # Only motor refreshes may be renewed; countdowns remain finite.
        controls = frozenset(k for k, c in self.commands.items() if c.kind == "motion")
        if controls:
            object.__setattr__(self, "execution", ExecutionCapabilities(hold="stream", hold_controls=controls))


@dataclass(frozen=True, slots=True)
class BinaryAction:
    key: str
    label: str
    controllers: tuple[str, ...]
    prefixes: tuple[bytes, ...]


with gzip.open(Path(__file__).parent.parent / "beds/suta/catalog.json.gz", "rt") as _file:
    _catalog = json.load(_file)


def _commands(rows: dict) -> dict[str, Command]:
    return {
        key: Command(row["text"], row["kind"], row["count"], row["delay_ms"],
                     row["interval_ms"], tuple(row["suffixes"]), row["source_scope"])
        for key, row in rows.items()
    }


PROFILES: Final = {
    key: SutaProfile(key, _commands(row["commands"]), row["threshold_s"], row["refresh_ms"], row["layout"])
    for key, row in _catalog["profiles"].items()
}
SNORE_EFFECT: Final = Command("AT+MODE=BOTH SNORE", "tap", 3, 100, 100, (), "VM event")
FLAT_EFFECT: Final = Command("AT+MODE=BOTH FLAT", "tap", 3, 100, 100, (), "VM event")
SHORT_NAME: Final = SutaProfile("short-name", {}, 0, 0, None)
SHARED: Final = _commands(_catalog["shared"])
ROUTES: Final[dict[str, str | None]] = {row["id"]: row["controller"] for row in _catalog["routes"]}
BINARY: Final = {
    row["label"].replace(" ", "_"): BinaryAction(
        row["label"].replace(" ", "_"), row["label"], tuple(row["controller"].split("/")),
        tuple(bytes.fromhex(p) for p in row["prefixes"]),
    )
    for row in _catalog["binary"]
}
FFE0: Final = "0000ffe0-0000-1000-8000-00805f9b34fb"
FFF0: Final = "0000fff0-0000-1000-8000-00805f9b34fb"
_FFE_NAMES: Final = ("MOON", "TEMP", "RBHC", "DRAWER", "STORAGE", "SOFA", "YOGABED", "ROLLSOFA")


def service_for_name(name: str) -> str:
    return FFE0 if any(name.startswith("SUTA-" + suffix) for suffix in _FFE_NAMES) else FFF0


def route_for_name(name: str) -> str:
    """Keep the disjoint nine-character UI partition, including its exits."""
    if len(name) < 9:
        return "short-name"
    prefix = name[:9]
    if prefix == "SUTA-M510":
        return "SUTA-M510D*" if name.startswith("SUTA-M510D") else "SUTA-M510* except D"
    if prefix == "SUTA-B202":
        return "SUTA-B202D*" if name.startswith("SUTA-B202D") else "SUTA-B202* except D"
    if prefix == "SUTA-B206":
        for suffix in ("A", "H"):
            if name.startswith("SUTA-B206" + suffix):
                return "SUTA-B206" + suffix + "*"
        return "SUTA-B206* except A,H"
    candidate = prefix + "*"
    return candidate if candidate in ROUTES else "fallback"


def profile_for_name(name: str) -> SutaProfile | None:
    key = ROUTES[route_for_name(name)]
    return PROFILES[key] if key else None


def binary_frames(family: str) -> dict[str, bytes]:
    return {
        action.key + "_" + p[6:].hex(): codec.from_prefix(p)
        for action in BINARY.values() if family in action.controllers for p in action.prefixes
    }
