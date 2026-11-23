"""Typed controller state shared by bed controllers and entities.

Controllers publish non-position state (light, massage, diagnostics) and
entities read it. Each value has one declared ``StateKey[T]``, so the writer and
every reader name the same key and agree on its type. The key is a ``str``
subclass whose text is the stored name, which keeps attribute names and stored
values identical to the plain-string keys it replaces.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar, overload


class AnyStateKey(str):
    """A declared state key, for readers that accept a value of any type."""

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class StateUpdate:
    """One value to publish under its declared key; build it with ``KEY(value)``."""

    key: AnyStateKey
    value: object


# Invariant, so a ``StateKey[bool]`` never passes for a ``StateKey[int]``.
_T = TypeVar("_T")


class StateKey(AnyStateKey, Generic[_T]):  # noqa: UP046
    """A declared state key whose value is a ``_T``."""

    __slots__ = ()

    def __call__(self, value: _T) -> StateUpdate:
        """Return a type-checked update for ``forward_controller_state_updates``."""
        return StateUpdate(self, value)


class ControllerState(dict[str, object]):
    """Controller state keyed by declared keys.

    A ``StateKey[T]`` read returns ``T``; any other key returns ``object``.
    """

    # Narrower than ``dict.get`` for declared keys, as ``HassDict`` does.
    @overload
    def get[T](self, key: StateKey[T], /) -> T | None: ...
    @overload
    def get[T, D](self, key: StateKey[T], default: D, /) -> T | D: ...
    @overload
    def get(self, key: str, default: object = None, /) -> object: ...
    def get(self, key: str, default: object = None, /) -> object:  # pyright: ignore[reportIncompatibleMethodOverride]
        return super().get(key, default)

    @overload
    def __getitem__[T](self, key: StateKey[T], /) -> T: ...
    @overload
    def __getitem__(self, key: str, /) -> object: ...
    def __getitem__(self, key: str, /) -> object:
        return super().__getitem__(key)


def sided[T](key: StateKey[T], side: str | None) -> StateKey[T]:
    """Return ``key`` scoped to one side (``<key>_<side>``), or ``key`` for none."""
    return key if side is None else StateKey[T](f"{key}_{side}")


def sided_updates[T](
    key: StateKey[T], side: str, value: T, *, unsided: bool
) -> tuple[StateUpdate, ...]:
    """Updates for ``side``'s copy of ``key``, plus ``key`` itself when ``unsided``."""
    return (sided(key, side)(value), *((key(value),) if unsided else ()))
