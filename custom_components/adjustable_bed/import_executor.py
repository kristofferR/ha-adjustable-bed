"""Load integration modules without blocking the event loop (issue #368)."""

from __future__ import annotations

import sys
from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


def _loaded(name: str) -> bool:
    """Whether ``name`` is fully imported, not still initializing in another thread.

    The import system flags a module whose import is in progress the same way.
    """
    module = sys.modules.get(name)
    return module is not None and not getattr(module.__spec__, "_initializing", False)


def _import_modules(names: tuple[str, ...]) -> None:
    for name in names:
        import_module(name)


async def async_import_modules(hass: HomeAssistant, *names: str) -> None:
    """Import modules of this package, such as ``beds.svane.controller``, in the import executor.

    A function-level import of a loaded module is a ``sys.modules`` lookup, so
    code that loads a controller or a large table on demand calls this first.
    Fully imported modules cost no executor job.
    """
    missing = tuple(
        module for module in (f"{__package__}.{name}" for name in names) if not _loaded(module)
    )
    if missing:
        await hass.async_add_import_executor_job(_import_modules, missing)
