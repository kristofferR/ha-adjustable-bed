"""Validated AI Bed service requests, with no raw packet escape hatch."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Request:
    action: str
    enabled: bool = True
    hour: int = 0
    minute: int = 0
    weekdays: tuple[int, ...] = ()
    mode: int = 0
    head: int = 1
    foot: int = 1
    seconds: int = 5
    pin: str = ""
