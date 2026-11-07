"""Config flows under the loop-import guard, run by ``test_controller_imports``.

Pytest collects this module only when it is named on the command line, so it
runs in a fresh interpreter where nothing has imported the bed modules yet.
"""

import importlib.abc
import sys
import threading
import traceback
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_BLUETOOTH, SOURCE_USER
from homeassistant.const import CONF_ADDRESS

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.detection import get_bed_type_options
from tests.form_helpers import answer_app, complete, form_answers

_PACKAGE = "custom_components.adjustable_bed."


class _LoopImportRecorder(importlib.abc.MetaPathFinder):
    """Record each integration module first imported on the event loop's thread."""

    def __init__(self) -> None:
        self.loop_thread = threading.get_ident()
        self.imports: dict[str, str] = {}

    def find_spec(self, fullname, path=None, target=None):  # noqa: ANN001, ANN201
        if fullname.startswith(_PACKAGE) and threading.get_ident() == self.loop_thread:
            importer = next(
                (
                    f"{frame.filename.rpartition('/adjustable_bed/')[2]}:{frame.lineno}"
                    for frame in reversed(traceback.extract_stack())
                    if "/custom_components/adjustable_bed/" in frame.filename
                ),
                "?",
            )
            self.imports.setdefault(fullname.removeprefix(_PACKAGE), importer)
        return None


@contextmanager
def _loop_import_guard() -> Iterator[None]:
    """Fail when integration code imports one of its modules on the event loop.

    Recording instead of raising keeps a broad ``except`` from hiding an import.
    """
    recorder = _LoopImportRecorder()
    sys.meta_path.insert(0, recorder)
    try:
        with patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False):
            yield
    finally:
        sys.meta_path.remove(recorder)
    assert not recorder.imports, "\n".join(
        f"{module} <- {importer}" for module, importer in sorted(recorder.imports.items())
    )


async def _finish(hass, result) -> None:
    """Answer each setup form with its defaults, as far as they lead."""
    with suppress(AssertionError):
        await complete(hass, result)


async def _finish_options(hass, result) -> None:
    """Answer each Configure form with its defaults, as far as they lead."""
    for attempt in range(12):
        if result["type"] != "form":
            return
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], form_answers(result, attempt)
        )


async def _settle(hass) -> None:
    """Drop flows left waiting on a bed, then let entry setup finish."""
    for flow in hass.config_entries.flow.async_progress():
        hass.config_entries.flow.async_abort(flow["flow_id"])
    await hass.async_block_till_done()


async def _typed_setup(hass, choice: str) -> None:
    """Choose ``choice`` from the setup list, type an address and take the defaults."""
    with patch(
        "custom_components.adjustable_bed.config_flow.get_discovered_service_info",
        return_value=[],
    ):
        result = await hass.config_entries.flow.async_init(
            const.DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: "manual"}
        )
        result = await answer_app(hass, result, choice)
    if result.get("step_id") == "manual_entry":
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: "11:22:33:44:55:66"}
        )
    await _finish(hass, result)
    await _settle(hass)


async def _remove_entries(hass) -> None:
    for entry in hass.config_entries.async_entries(const.DOMAIN):
        await hass.config_entries.async_remove(entry.entry_id)


@pytest.fixture
def before_integration_setup() -> Iterator[None]:
    """Keep the integration and its entries from setting up, as on a new install."""
    integration = "custom_components.adjustable_bed"
    with (
        patch(f"{integration}.async_setup", AsyncMock(return_value=True)),
        patch(f"{integration}.async_setup_entry", AsyncMock(return_value=True)),
        patch(f"{integration}.async_unload_entry", AsyncMock(return_value=True)),
    ):
        yield


async def test_new_install_setup_of_every_listed_bed(
    hass, enable_custom_integrations, before_integration_setup
):
    """Set up each app or bed the setup list offers on a new install."""
    with _loop_import_guard():
        for option in get_bed_type_options():
            await _typed_setup(hass, option["value"])
            await _remove_entries(hass)


async def test_new_install_setup_of_discovered_beds(
    hass,
    enable_custom_integrations,
    before_integration_setup,
    mock_bluetooth_service_info,
    mock_bluetooth_service_info_richmat,
    mock_bluetooth_service_info_keeson,
    mock_bluetooth_service_info_octo,
    mock_bluetooth_service_info_svane,
    mock_bluetooth_service_info_malouf,
):
    """Set up a discovered bed of several families on a new install."""
    with _loop_import_guard():
        for info in (
            mock_bluetooth_service_info,
            mock_bluetooth_service_info_richmat,
            mock_bluetooth_service_info_keeson,
            mock_bluetooth_service_info_octo,
            mock_bluetooth_service_info_svane,
            mock_bluetooth_service_info_malouf,
        ):
            result = await hass.config_entries.flow.async_init(
                const.DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info
            )
            await _finish(hass, result)
            await _settle(hass)
            await _remove_entries(hass)


async def test_entry_setup_and_configure_of_every_listed_bed(hass, enable_custom_integrations):
    """Set up each listed app or bed and its entry, then save its Configure settings."""
    with _loop_import_guard():
        for option in get_bed_type_options():
            await _typed_setup(hass, option["value"])
            for entry in hass.config_entries.async_entries(const.DOMAIN):
                result = await hass.config_entries.options.async_init(entry.entry_id)
                if result["type"] == "menu":
                    result = await hass.config_entries.options.async_configure(
                        result["flow_id"], {"next_step_id": "settings"}
                    )
                    await _finish_options(hass, result)
            await _remove_entries(hass)
