"""Typed catalogs for the Flutter Richmat apps, over the Richmat wire codec."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .richmat import RichmatProfile


@dataclass(frozen=True, slots=True)
class Action:
    label: str
    gesture: str
    local: bool
    force_long: bool
    memory_toggle: bool
    flagged: bool
    short: int
    long: int
    legacy_short: int
    hidden: bool = False
    interactive: bool = True
    recovered_short: int | None = None


@dataclass(frozen=True, slots=True)
class Product:
    label: str
    actions: tuple[str, ...]
    alarms: tuple[str, ...]
    sides: tuple[int, ...]
    light: bool
    light_display: str
    repeat_alarm: bool
    sleep: str
    massage_timer: bool


@dataclass(frozen=True, slots=True)
class AppCatalog:
    profile: RichmatProfile
    actions: Mapping[str, Action]
    products: Mapping[str, Product]
    expansions: Mapping[str, tuple[str, ...]]
    # MLILY's accepted row159 corrects these app-specific runtime rules.
    reply_gated_menus: bool = False
    mask_when_release: bool = False
    release_initially: bool = True
    startup: tuple[tuple[str, int], ...] = (
        ("deviceFunctionItemExitLimit", 0),
        ("deviceFunctionItemCheckClock", 1),
        ("deviceFunctionItemCheckLight", 1),
    )
