"""AVEK Ergo System 2.0.2 / 210722202, one fixed Shoulder/Hip panel."""

from dataclasses import dataclass
from typing import Final

from ..codec.avek import control
from ..execution import ExecutionCapabilities


@dataclass(frozen=True, slots=True)
class Action:
    key: str
    label: str
    word: int

    @property
    def frame(self) -> bytes:
        return control(self.word)


@dataclass(frozen=True, slots=True)
class AvekProfile:
    key: str = "avek"
    name_prefixes: tuple[str, ...] = ("TBA3", "TBA4", "TBA-AK")
    refresh_ms: int = 90
    initial_check_ms: int = 100
    initial_checks: int = 100
    initial_endpoint: int = 10000
    # HA independently bounds Initial; the app's waiter only conditionally cancels.
    initial_limit_ms: int = 10000
    # HA readiness bound, independent of the app's dialog or movement timers.
    identity_timeout_s: float = 5
    actions: tuple[Action, ...] = (
        Action("shoulder_hard", "Shoulder hard", 0x0020),
        Action("shoulder_soft", "Shoulder soft", 0x0010),
        Action("hip_hard", "Hip hard", 0x0008),
        Action("hip_soft", "Hip soft", 0x0004),
        Action("a", "A", 0x0200),
        Action("b", "B", 0x0100),
        Action("c", "C", 0x0002),
        Action("d", "D", 0x0001),
        Action("save", "Save", 0x0400),
        Action("initial", "Initial", 0x0800),
    )
    execution: ExecutionCapabilities = ExecutionCapabilities(
        hold="stream",
        hold_controls=frozenset(
            {"shoulder_hard", "shoulder_soft", "hip_hard", "hip_soft", "a", "b", "c", "d"}
        ),
    )

    def action(self, key: str) -> Action:
        return next(action for action in self.actions if action.key == key)


AVEK: Final = AvekProfile()
