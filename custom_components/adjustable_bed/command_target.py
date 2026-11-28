"""Capture app-local routing choices before a command waits for its wire lane."""

from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Protocol

from .bed_traits import bed_traits
from .beds.base import BedController
from .errors import invalid


class CommandTargetOwner(Protocol):
    @property
    def operation_identity(self) -> int: ...

    @property
    def capability_controller(self) -> BedController | None: ...


_targets: ContextVar[Mapping[int, str] | None] = ContextVar("bed_command_targets", default=None)


def command_targets_allowed(owners: Iterable[CommandTargetOwner]) -> bool:
    """Whether this physical selection satisfies every app's recipient limit."""
    owners = tuple(owners)
    identities = {getattr(owner, "operation_identity", id(owner)) for owner in owners}
    if len(identities) <= 1:
        return True
    for owner in owners:
        controller = owner.capability_controller
        if isinstance(controller, BedController):
            required = controller.requires_single_command_target
        else:
            data = getattr(getattr(owner, "entry", None), "data", {})
            required = bed_traits(getattr(owner, "bed_type", None), data.get("protocol_variant")).single_command_target
        if required is True:
            return False
    return True


def require_single_command_target(owners: Iterable[CommandTargetOwner]) -> None:
    """Apply an app's physical-recipient limit before any lane is preempted."""
    if not command_targets_allowed(owners):
        raise invalid("single_command_target_required")


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
