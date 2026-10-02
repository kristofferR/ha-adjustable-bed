"""Resolve the Remacro model selector from Home Assistant's advertisement history."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)

from .beds.remacro_protocol import APP_LABELS, ModelProblem, app_for_variant, model_problem
from .const import BED_TYPE_REMACRO, CONF_PROTOCOL_VARIANT, CONF_REMACRO_MODEL, DOMAIN
from .entity_runtime import EntityRuntime


def remacro_manufacturer_data(
    hass: HomeAssistant, address: str, manufacturer_data: Mapping[int, bytes] | None = None
) -> dict[int, bytes] | None:
    """Return the given records, else the connectable or non-connectable history."""
    if manufacturer_data:
        return dict(manufacturer_data)
    for connectable in (True, False):
        info = bluetooth.async_last_service_info(hass, address, connectable=connectable)
        if info is not None and info.manufacturer_data:
            return dict(info.manufacturer_data)
    return None


def remacro_entry_problem(
    entry_data: Mapping[str, Any], manufacturer_data: Mapping[int, bytes] | None
) -> tuple[ModelProblem | None, dict[str, str]]:
    """Classify an entry's model for its app, with message placeholders."""
    app = app_for_variant(entry_data.get(CONF_PROTOCOL_VARIANT))
    problem, company_id = model_problem(app, manufacturer_data, entry_data.get(CONF_REMACRO_MODEL))
    return problem, {"company_id": str(company_id), "app": APP_LABELS[app]}


def remacro_issue_id(address: str) -> str:
    """Return the Repairs issue ID for one physical Remacro bed."""
    return f"remacro_model_{address.upper()}"


def clear_remacro_model_issues(hass: HomeAssistant, addresses: Iterable[str]) -> None:
    """Delete the Remacro model issues for beds no remaining entry owns."""
    for address in addresses:
        async_delete_issue(hass, DOMAIN, remacro_issue_id(address))


def update_remacro_model_issue(
    hass: HomeAssistant,
    address: str,
    name: str,
    problem: ModelProblem | None,
    placeholders: Mapping[str, str],
) -> None:
    """Raise or clear the Repairs issue for a model the selected app refuses."""
    issue_id = remacro_issue_id(address)
    if problem not in ("unmapped", "not_in_app"):
        async_delete_issue(hass, DOMAIN, issue_id)
        return
    async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=IssueSeverity.ERROR,
        translation_key=f"remacro_model_{problem}",
        translation_placeholders={**placeholders, "name": name, "address": address},
    )


def remacro_side_lacks_global_stop(runtime: EntityRuntime) -> bool:
    """Whether a known Remacro side's screen defines no global STOP (NineActivity)."""
    # Checked first so other bed types (and minimal test runtimes) are untouched.
    if getattr(runtime, "bed_type", None) != BED_TYPE_REMACRO:
        return False
    controller = runtime.capability_controller
    return controller is not None and not controller.supports_stop_all
