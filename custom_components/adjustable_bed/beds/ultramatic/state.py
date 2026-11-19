"""Typed, connection-scoped Ultramatic reports, in app A/AB/B order."""

from dataclasses import dataclass
from typing import Final

from ...controller_state import StateKey


class SideState:
    """The typed key family for one physical-side namespace."""

    timer: StateKey[int | None]
    wave: StateKey[int | None]
    head: StateKey[int | None]
    foot: StateKey[int | None]
    alarm: StateKey[str | None]
    days: StateKey[int | None]
    wake_type: StateKey[str | None]
    position: StateKey[int | None]
    enabled: StateKey[bool | None]
    standalone: StateKey[bool | None]

    def __init__(self, side: str) -> None:
        prefix = f"ultramatic_{side.lower()}_"
        self.timer = StateKey[int | None](prefix + "timer")
        self.wave = StateKey[int | None](prefix + "wave")
        self.head = StateKey[int | None](prefix + "head")
        self.foot = StateKey[int | None](prefix + "foot")
        self.alarm = StateKey[str | None](prefix + "alarm")
        self.days = StateKey[int | None](prefix + "days")
        self.wake_type = StateKey[str | None](prefix + "wake_type")
        self.position = StateKey[int | None](prefix + "position")
        self.enabled = StateKey[bool | None](prefix + "enabled")
        self.standalone = StateKey[bool | None](prefix + "standalone")


SIDES: Final = {"A": SideState("a"), "AB": SideState("ab"), "B": SideState("b")}


@dataclass(frozen=True, slots=True)
class AlarmSettings:
    hour: int
    minute: int
    days: int
    type_code: int
    enabled: bool
