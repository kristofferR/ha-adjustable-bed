"""Patch a module global that the coordinator and its mixin modules both read."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any
from unittest.mock import patch

from custom_components.adjustable_bed import coordinator_bonds

# Modules holding AdjustableBedCoordinator methods outside coordinator.py.
COORDINATOR_MIXIN_MODULES = (coordinator_bonds,)


@contextmanager
def patch_coordinator_global(name: str, *args: Any, **kwargs: Any) -> Iterator[Any]:
    """Patch ``name`` in ``coordinator`` and every mixin module that imports it.

    Each module resolves its own binding, so one mock must replace all of them
    for a patch to reach every coordinator method that reads the name.
    """
    with (
        patch(f"custom_components.adjustable_bed.coordinator.{name}", *args, **kwargs) as mock,
        ExitStack() as stack,
    ):
        for module in COORDINATOR_MIXIN_MODULES:
            if hasattr(module, name):
                stack.enter_context(patch.object(module, name, mock))
        yield mock
