"""Typed catalogs for the Flutter Richmat apps, over the Richmat wire codec."""

from __future__ import annotations

from dataclasses import dataclass


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
