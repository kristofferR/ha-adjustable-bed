"""Resolve the Remacro model selector from Home Assistant's advertisement history."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant

from .beds.remacro_protocol import APP_LABELS, ModelProblem, app_for_variant, model_problem
from .const import CONF_PROTOCOL_VARIANT, CONF_REMACRO_MODEL


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
