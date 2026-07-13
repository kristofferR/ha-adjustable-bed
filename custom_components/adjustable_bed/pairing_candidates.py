"""Find standalone bed entries eligible for the Dual Bed pairing flow."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import DOMAIN
from .pairing import is_paired, pair_member_addresses

CONF_PAIR_SELECTION = "pair_selection"


def active_pairing_candidates(hass: HomeAssistant) -> list[ConfigEntry]:
    """Return loaded standalone beds not already claimed by a paired entry.

    Compatibility is deliberately validated later by the pairing flow. Keeping
    this helper limited to entry lifecycle and ownership makes it suitable for
    both the Add Integration picker and the Repairs suggestion.
    """
    entries = hass.config_entries.async_entries(DOMAIN)
    absorbed_addresses = {
        address
        for entry in entries
        if is_paired(entry.data)
        for address in pair_member_addresses(entry.data)
    }

    return [
        entry
        for entry in entries
        if entry.state is ConfigEntryState.LOADED
        and not is_paired(entry.data)
        and isinstance((address := entry.data.get(CONF_ADDRESS)), str)
        and address.upper() not in absorbed_addresses
    ]


def encode_pair_selection(left_entry_id: str, right_entry_id: str) -> str:
    """Encode an ordered pair as an opaque selector value."""
    return json.dumps([left_entry_id, right_entry_id], separators=(",", ":"))


def decode_pair_selection(value: object) -> tuple[str, str] | None:
    """Decode an ordered-pair selector value, returning None when malformed."""
    if not isinstance(value, str):
        return None
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return None
    if (
        not isinstance(decoded, list)
        or len(decoded) != 2
        or not all(isinstance(entry_id, str) for entry_id in decoded)
    ):
        return None
    return decoded[0], decoded[1]


def ordered_pair_options(entries: list[ConfigEntry]) -> list[SelectOptionDict]:
    """Build every valid Left/Right assignment without same-bed choices."""
    return [
        SelectOptionDict(
            value=encode_pair_selection(left.entry_id, right.entry_id),
            label=(
                f"Left: {left.title or left.entry_id} / "
                f"Right: {right.title or right.entry_id}"
            ),
        )
        for left in entries
        for right in entries
        if left.entry_id != right.entry_id
    ]


def build_pair_selection_schema(entries: list[ConfigEntry]) -> vol.Schema:
    """Build the shared ordered-pair picker used by config and repair flows."""
    options = ordered_pair_options(entries)
    pair_selector = SelectSelector(
        SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
    )
    return vol.Schema(
        {
            vol.Required(
                CONF_PAIR_SELECTION,
                default=options[0]["value"],
            ): pair_selector,
            vol.Optional(CONF_NAME): str,
        }
    )


def selected_pair_ids(user_input: Mapping[str, Any]) -> tuple[str, str] | None:
    """Read the ordered selector value, with legacy field support for safety."""
    if CONF_PAIR_SELECTION in user_input:
        return decode_pair_selection(user_input[CONF_PAIR_SELECTION])

    left_entry_id = user_input.get("left_entry")
    right_entry_id = user_input.get("right_entry")
    if isinstance(left_entry_id, str) and isinstance(right_entry_id, str):
        return left_entry_id, right_entry_id
    return None
