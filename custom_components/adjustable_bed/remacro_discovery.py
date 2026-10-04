"""Resolve the Remacro model selector from Home Assistant's advertisement history."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.components import bluetooth
from homeassistant.components.repairs import RepairsFlow
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)

from .beds.remacro_protocol import (
    APP_LABELS,
    ModelProblem,
    RemacroApp,
    app_for_variant,
    apps_listing,
    model_problem,
)
from .const import (
    BED_TYPE_REMACRO,
    CONF_PROTOCOL_VARIANT,
    CONF_REMACRO_MODEL,
    DOMAIN,
    PAIR_SIDES,
)
from .entity_runtime import EntityRuntime
from .pairing import get_child, is_paired, with_updated_child

if TYPE_CHECKING:
    from .coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

ISSUE_PREFIX = "remacro_model_"


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
    return problem, {
        "company_id": str(company_id),
        "app": APP_LABELS[app],
        "apps": " or ".join(APP_LABELS[listing] for listing in apps_listing(company_id)),
    }


def remacro_issue_id(address: str) -> str:
    """Return the Repairs issue ID for one physical Remacro bed."""
    return f"{ISSUE_PREFIX}{address.upper()}"


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
    *,
    entry_id: str,
    side: str | None = None,
) -> None:
    """Raise or clear the warning for a bed running on the fallback controls.

    A model not seen yet gets no issue: it is usually only out of range, and the
    entry reloads with the model's controls once it advertises.
    """
    issue_id = remacro_issue_id(address)
    if problem not in ("unmapped", "not_in_app"):
        async_delete_issue(hass, DOMAIN, issue_id)
        return
    # The Repairs issue is the user-facing warning; this only marks it in the log.
    _LOGGER.info(
        "Remacro bed %s (%s) advertises company ID %s, which the %s app does not list; "
        "using the limited fallback controls",
        name,
        address,
        placeholders.get("company_id"),
        placeholders.get("app"),
    )
    async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        # Another app lists the model, so switching the profile fixes it.
        is_fixable=problem == "not_in_app",
        severity=IssueSeverity.WARNING,
        translation_key=f"remacro_model_{problem}",
        translation_placeholders={**placeholders, "name": name, "address": address},
        data={"entry_id": entry_id, "side": side, "company_id": placeholders.get("company_id")},
    )


@callback
def async_watch_remacro_fallback(
    hass: HomeAssistant, entry: ConfigEntry, coordinators: Iterable[AdjustableBedCoordinator]
) -> None:
    """Reload the entry once a bed on the fallback controls advertises a listed model.

    That covers a model not seen at setup (for example after an upgrade, before
    the bed advertised) and a bed whose advertisement changes to a listed one.
    """
    reload_requested = False

    for coordinator in coordinators:
        if coordinator.bed_type != BED_TYPE_REMACRO:
            continue
        # A Remacro controller exists, so its lazily imported module is loaded.
        from .beds.remacro import RemacroController

        controller = coordinator.capability_controller
        if not isinstance(controller, RemacroController) or controller.model.recognized:
            continue
        app = controller.app

        @callback
        def _seen(
            service_info: bluetooth.BluetoothServiceInfoBleak,
            _change: bluetooth.BluetoothChange,
            app: RemacroApp = app,
        ) -> None:
            nonlocal reload_requested
            if reload_requested or model_problem(app, service_info.manufacturer_data, None)[0]:
                return
            reload_requested = True
            _LOGGER.info(
                "Remacro bed %s advertised a listed model; reloading %s for its controls",
                service_info.address,
                entry.title,
            )
            hass.config_entries.async_schedule_reload(entry.entry_id)

        entry.async_on_unload(
            bluetooth.async_register_callback(
                hass,
                _seen,
                bluetooth.BluetoothCallbackMatcher(address=coordinator.address),
                bluetooth.BluetoothScanningMode.PASSIVE,
            )
        )


def remacro_side_lacks_global_stop(runtime: EntityRuntime) -> bool:
    """Whether a Remacro side's screen defines no global STOP frame (NineActivity)."""
    # Checked first so other bed types (and minimal test runtimes) are untouched.
    if getattr(runtime, "bed_type", None) != BED_TYPE_REMACRO:
        return False
    controller = runtime.capability_controller
    return controller is not None and not controller.supports_stop_all


class RemacroAppRepairFlow(RepairsFlow):
    """Switch a bed to an app that lists its model."""

    def __init__(self, entry_id: str, side: str | None, company_id: object) -> None:
        self._entry_id = entry_id
        self._side = side
        model_id = int(company_id) if isinstance(company_id, str) and company_id.isdigit() else None
        self._apps = apps_listing(model_id)

    def _entry(self) -> ConfigEntry | None:
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None or is_paired(entry.data) != (self._side is not None):
            return None
        if self._side is not None and get_child(entry.data, self._side) is None:
            return None
        return entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        entry = self._entry()
        if entry is None or not self._apps:
            return self.async_abort(reason="entry_missing")
        if user_input is not None:
            variant = user_input[CONF_PROTOCOL_VARIANT]
            options = dict(entry.options)
            if self._side is None:
                data = {**entry.data, CONF_PROTOCOL_VARIANT: variant}
            else:
                data = dict(entry.data)
                # A parent option would override every side: keep it on the others.
                if (shared := options.pop(CONF_PROTOCOL_VARIANT, None)) is not None:
                    for other in PAIR_SIDES:
                        if other != self._side and get_child(data, other) is not None:
                            data = with_updated_child(data, other, {CONF_PROTOCOL_VARIANT: shared})
                data = with_updated_child(data, self._side, {CONF_PROTOCOL_VARIANT: variant})
            # Loaded entries reload through their update listener.
            self.hass.config_entries.async_update_entry(entry, data=data, options=options)
            return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PROTOCOL_VARIANT, default=self._apps[0]): vol.In(
                        {app: APP_LABELS[app] for app in self._apps}
                    )
                }
            ),
            description_placeholders={
                "name": entry.title,
                "apps": " or ".join(APP_LABELS[app] for app in self._apps),
            },
        )
