"""Patch a module global that the coordinator and its mixin modules both read."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any
from unittest.mock import patch

from custom_components.adjustable_bed import (
    coordinator,
    coordinator_bonds,
    coordinator_connection,
    coordinator_positions,
)

# coordinator.py and the modules holding the rest of AdjustableBedCoordinator.
COORDINATOR_MODULES = (
    coordinator,
    coordinator_bonds,
    coordinator_connection,
    coordinator_positions,
)


@contextmanager
def patch_coordinator_global(name: str, *args: Any, **kwargs: Any) -> Iterator[Any]:
    """Patch ``name`` in every coordinator module that binds it, with one mock.

    Each module resolves its own binding, so one mock must replace all of them
    for a patch to reach every coordinator method that reads the name.
    """
    modules = [module for module in COORDINATOR_MODULES if hasattr(module, name)]
    assert modules, name
    first, *others = modules
    with patch.object(first, name, *args, **kwargs) as mock, ExitStack() as stack:
        for module in others:
            stack.enter_context(patch.object(module, name, mock))
        yield mock
