"""Task-local app service fencing, without importing HA service registration."""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from .betterliving2 import BetterLiving2Controller


class SelectionGuard(Protocol):
    active: bool

    def check(self, controller: BetterLiving2Controller | None = None) -> None: ...

    def connected(self, controller: BetterLiving2Controller) -> None: ...

    def releasing(self, controller: BetterLiving2Controller, reason: str) -> None: ...


SELECTION: ContextVar[SelectionGuard | None] = ContextVar("betterliving2_selection", default=None)


def current_selection() -> SelectionGuard | None:
    selected = SELECTION.get()
    return selected if selected is not None and selected.active else None
