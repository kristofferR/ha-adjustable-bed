"""Capture app-local routing choices before a command waits for its wire lane."""

from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Protocol

from .beds.base import BedController


class CommandTargetOwner(Protocol):
    @property
    def operation_identity(self) -> int: ...

    @property
    def capability_controller(self) -> BedController | None: ...


_targets: ContextVar[Mapping[int, str] | None] = ContextVar("bed_command_targets", default=None)


def capture_command_targets(owners: Iterable[CommandTargetOwner]) -> dict[int, str]:
    """Keep an earlier admission through pair reservations and reconnects."""
    captured = _targets.get() or {}
    result: dict[int, str] = {}
    for owner in owners:
        identity = getattr(owner, "operation_identity", id(owner))
        target = captured.get(identity)
        if target is None:
            controller = getattr(owner, "capability_controller", None)
            target = (
                controller.selected_command_target
                if isinstance(controller, BedController)
                else None
            )
        if target is not None:
            result[identity] = target
    return result


def admitted_command_target(owner: CommandTargetOwner) -> str | None:
    return (_targets.get() or {}).get(getattr(owner, "operation_identity", id(owner)))


@contextmanager
def command_target_scope(targets: Mapping[int, str] | None) -> Iterator[None]:
    if targets is None:
        yield
        return
    token = _targets.set(targets)
    try:
        yield
    finally:
        _targets.reset(token)
