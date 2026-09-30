"""Resolve legacy receiver-based classifications without guessing a handset."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.repairs import RepairsFlow
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)

from .const import (
    BED_TYPE_FURNIMOVE,
    BED_TYPE_OKIN_RF_ECO_BT,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_FURNIMOVE_REMOTE,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    PAIR_SIDES,
    RUNTIME_BOND_KEYS,
)
from .furnimove_profiles import FURNIMOVE_PROFILES, get_furnimove_profile
from .pairing import effective_child_data, get_child, is_paired, with_updated_child
from .unsupported import delete_pairing_required_issue

ISSUE_PREFIX = "furnimove_layout_"
CONF_STAIRCASE_LAYOUT_CONFIRMED = "rf_eco_staircase_confirmed"


def _issue_id(entry_id: str, side: str | None) -> str:
    return f"{ISSUE_PREFIX}{entry_id}_{side or 'standalone'}"


def _needs_layout(data: dict[str, Any]) -> bool:
    if data.get(CONF_BED_TYPE) == BED_TYPE_FURNIMOVE:
        return data.get(CONF_FURNIMOVE_REMOTE) not in FURNIMOVE_PROFILES
    return (
        data.get(CONF_BED_TYPE) == BED_TYPE_OKIN_RF_ECO_BT
        and not data.get(CONF_STAIRCASE_LAYOUT_CONFIRMED, False)
    )


@callback
def async_refresh_furnimove_layout_issues(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Offer the repair before connecting, including for offline legacy entries."""
    for side in (None, *PAIR_SIDES):
        issue_id = _issue_id(entry.entry_id, side)
        if is_paired(entry.data):
            if side is None or get_child(entry.data, side) is None:
                async_delete_issue(hass, DOMAIN, issue_id)
                continue
            data = effective_child_data(entry.data, side, entry.options)
        else:
            if side is not None:
                async_delete_issue(hass, DOMAIN, issue_id)
                continue
            data = dict(entry.data)
        if not _needs_layout(data):
            async_delete_issue(hass, DOMAIN, issue_id)
            continue
        async_create_issue(
            hass, DOMAIN, issue_id,
            is_fixable=True,
            is_persistent=True,
            severity=IssueSeverity.WARNING,
            translation_key="furnimove_layout",
            translation_placeholders={"name": entry.title if side is None else f"{entry.title} ({side})"},
            data={"entry_id": entry.entry_id, "side": side},
        )


@callback
def async_clear_furnimove_layout_issues(hass: HomeAssistant, entry_id: str) -> None:
    """Remove repairs when their config entry is removed."""
    for side in (None, *PAIR_SIDES):
        async_delete_issue(hass, DOMAIN, _issue_id(entry_id, side))


class FurniMoveLayoutRepairFlow(RepairsFlow):
    """Keep registry ownership while correcting one physical bed's layout."""

    def __init__(self, entry_id: str, side: str | None) -> None:
        self._entry_id = entry_id
        self._side = side

    def _entry(self) -> ConfigEntry | None:
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            return None
        if self._side is None:
            return entry if not is_paired(entry.data) else None
        if self._side not in PAIR_SIDES or get_child(entry.data, self._side) is None:
            return None
        return entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        entry = self._entry()
        if entry is None:
            return self.async_abort(reason="entry_missing")
        if user_input is not None and "layout" in user_input:
            if user_input["layout"] == "furnimove":
                return await self.async_step_handset()
            if user_input["layout"] == "staircase":
                return await self._save({
                    CONF_BED_TYPE: BED_TYPE_OKIN_RF_ECO_BT,
                    CONF_MOTOR_COUNT: 1,
                    CONF_STAIRCASE_LAYOUT_CONFIRMED: True,
                    CONF_HAS_MASSAGE: False,
                    CONF_DISABLE_ANGLE_SENSING: True,
                })
        return self.async_show_form(
            step_id="init",
            description_placeholders={"name": entry.title},
            data_schema=vol.Schema({vol.Required("layout"): selector.SelectSelector(
                selector.SelectSelectorConfig(options=[
                    selector.SelectOptionDict(value="furnimove", label="FurniMove adjustable bed"),
                    selector.SelectOptionDict(value="staircase", label="Single-actuator staircase"),
                ], mode=selector.SelectSelectorMode.DROPDOWN)
            )}),
        )

    async def async_step_handset(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if self._entry() is None:
            return self.async_abort(reason="entry_missing")
        errors: dict[str, str] = {}
        if user_input is not None:
            handset_id = user_input.get(CONF_FURNIMOVE_REMOTE)
            if isinstance(handset_id, str) and handset_id in FURNIMOVE_PROFILES:
                profile = get_furnimove_profile(handset_id)
                return await self._save({
                    CONF_BED_TYPE: BED_TYPE_FURNIMOVE,
                    CONF_FURNIMOVE_REMOTE: handset_id,
                    CONF_MOTOR_COUNT: profile.motor_count,
                    CONF_HAS_MASSAGE: bool(profile.by_type("massage-function")),
                    CONF_DISABLE_ANGLE_SENSING: True,
                })
            errors[CONF_FURNIMOVE_REMOTE] = "handset_required"
        return self.async_show_form(
            step_id="handset", errors=errors,
            data_schema=vol.Schema({vol.Required(CONF_FURNIMOVE_REMOTE): selector.SelectSelector(
                selector.SelectSelectorConfig(options=[
                    selector.SelectOptionDict(value=key, label=f"{key}: {profile.description or profile.product_type}")
                    for key, profile in FURNIMOVE_PROFILES.items()
                ], mode=selector.SelectSelectorMode.DROPDOWN)
            )}),
        )

    async def _save(self, patch: dict[str, Any]) -> FlowResult:
        entry = self._entry()
        if entry is None:
            return self.async_abort(reason="entry_missing")
        remove = {CONF_PROTOCOL_VARIANT, CONF_FURNIMOVE_REMOTE, CONF_STAIRCASE_LAYOUT_CONFIRMED} - patch.keys()
        if patch[CONF_BED_TYPE] == BED_TYPE_FURNIMOVE:
            remove.update(RUNTIME_BOND_KEYS)
        options = dict(entry.options)
        if self._side is None:
            data = {key: value for key, value in entry.data.items() if key not in remove}
            data.update(patch)
            for key in {*remove, *patch}:
                options.pop(key, None)
        else:
            # Parent options override descriptors. Materialize those overrides on
            # both sides before removing them, preserving the other side's state.
            data = dict(entry.data)
            for side in PAIR_SIDES:
                if get_child(entry.data, side) is None:
                    continue
                effective = effective_child_data(entry.data, side, entry.options)
                inherited = {key: effective[key] for key in {*remove, *patch} if key in options and key in effective}
                data = with_updated_child(data, side, inherited)
            for key in {*remove, *patch}:
                options.pop(key, None)
            data = with_updated_child(data, self._side, patch, remove=remove)
        if patch[CONF_BED_TYPE] == BED_TYPE_FURNIMOVE:
            target = dict(entry.data) if self._side is None else effective_child_data(entry.data, self._side, entry.options)
            address = target.get(CONF_ADDRESS)
            if isinstance(address, str):
                await delete_pairing_required_issue(self.hass, address)
        self.hass.config_entries.async_update_entry(entry, data=data, options=options)
        async_refresh_furnimove_layout_issues(self.hass, entry)
        # Loaded entries reload through the normal update listener; offline
        # entries retry setup with this same identity and the corrected data.
        return self.async_create_entry(title="", data={})
