"""Pure action phases. Each string is a separate Nordic one-byte write."""

from dataclasses import dataclass

from ...codec.richmat import encode
from ...profiles.richmat_legacy import Action, Branch


def packet(literal: str) -> bytes:
    if len(literal) != 1 or not literal.isascii():
        raise ValueError("Expected one fixed ASCII character")
    return encode("nordic", ord(literal))


@dataclass(slots=True)
class LocalState:
    axis: int
    mode: int = 0
    led: int = 0


@dataclass(frozen=True, slots=True)
class Phases:
    down: tuple[str, ...]
    branch: Branch | None
    short: tuple[str, ...]
    short_guard: int | None
    cleanup: tuple[str, ...]

    def tick(self, count: int) -> tuple[tuple[str, ...], int]:
        if self.branch is None:
            return (), count
        threshold = self.branch.threshold
        if threshold is not None and count < threshold:
            return (), count + 1
        return self.branch.writes, count

    def release(self, count: int, *, recall: bool = True) -> tuple[str, ...]:
        short = (
            self.short
            if recall and self.short_guard is not None and count < self.short_guard
            else ()
        )
        return short + self.cleanup


def begin(action: Action, state: LocalState) -> Phases:
    selected = (
        {"axis": state.axis, "mode": state.mode, "led": state.led}[action.select]
        if action.select
        else 0
    )
    down = action.down_by_selection[selected] if action.down_by_selection else action.down
    index = selected if action.select in ("axis", "mode") else 0
    arm = action.states[index] if action.states else None
    branch = dict(action.branches).get(arm) if arm else None
    if action.axis_value is not None:
        state.axis = action.axis_value
    if action.selected_value is not None:
        state.mode = action.selected_value
    if action.select == "led":
        state.led = 1 - state.led
    return Phases(down, branch, action.short, action.short_guard, action.release)
