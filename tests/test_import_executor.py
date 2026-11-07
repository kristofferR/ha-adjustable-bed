"""Off-loop imports of the integration's own modules."""

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch

from custom_components.adjustable_bed.import_executor import async_import_modules

NAME = "custom_components.adjustable_bed.beds.example"


async def test_a_module_still_initializing_is_imported_in_the_executor():
    """Another thread's in-progress import must not let the caller import on the loop."""
    hass = SimpleNamespace(async_add_import_executor_job=AsyncMock())
    module = ModuleType(NAME)
    module.__spec__ = SimpleNamespace(_initializing=True)
    with patch.dict(sys.modules, {NAME: module}):
        await async_import_modules(hass, "beds.example")
        hass.async_add_import_executor_job.assert_awaited_once()

        hass.async_add_import_executor_job.reset_mock()
        module.__spec__._initializing = False
        await async_import_modules(hass, "beds.example")
        hass.async_add_import_executor_job.assert_not_awaited()
