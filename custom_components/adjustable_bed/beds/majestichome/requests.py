"""Immutable Majestic Home alarm forms, without importing the controller."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Request:
    operation: str
    number: int | None = None
    hour: int = 7
    minute: int = 30
    preset: str = "memory_1"
    weekdays: tuple[int, ...] = ()
    enabled: bool = True
