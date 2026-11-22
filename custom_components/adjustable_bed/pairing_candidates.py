"""Find standalone bed entries eligible for the Dual Bed pairing flow."""

from __future__ import annotations

import json
from collections import Counter
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

from .const import (
    CONF_BED_TYPE,
    CONF_PROTOCOL_VARIANT,
    CONF_STARCODE_LIFT_ENTRIES,
    DOMAIN,
    STARCODE_GROUP_BED_TYPES,
    resolve_explicit_bed_type,
)
from .pairing import is_paired, pair_member_addresses
from .profiles.saatva import TWO_RECEIVER_PROFILES as SAATVA_TWO_RECEIVER_PROFILES

CONF_PAIR_SELECTION = "pair_selection"


def active_pairing_candidates(hass: HomeAssistant) -> list[ConfigEntry]:
    """Return loaded standalone beds that another standalone bed could pair with.

    Beds already claimed by a pair, StarCode lift groups and beds with no other
    bed of the same protocol are left out. The pairing flow still validates
    the chosen two in full (motor layout, capabilities and so on).
    """
    entries = hass.config_entries.async_entries(DOMAIN)
    absorbed_addresses = {
        address
        for entry in entries
        if is_paired(entry.data)
        for address in pair_member_addresses(entry.data)
    }

    # Absorbing either a main or one of its lifts would invalidate stored entry
    # references. Release the group selection before changing registry ownership.
    group_members: set[str] = set()
    for entry in entries:
        lifts = entry.data.get(CONF_STARCODE_LIFT_ENTRIES)
        if (
            entry.data.get(CONF_BED_TYPE) in STARCODE_GROUP_BED_TYPES
            and isinstance(lifts, (tuple, list))
            and lifts
        ):
            group_members.add(entry.entry_id)
            group_members.update(lift for lift in lifts if isinstance(lift, str))

    standalone = [
        entry
        for entry in entries
        if entry.state is ConfigEntryState.LOADED
        and not is_paired(entry.data)
        and entry.data.get(CONF_BED_TYPE) != "sleep_assistant"
        and not (entry.data.get(CONF_BED_TYPE) == "personal_comfort"
                 and (entry.data.get(CONF_PROTOCOL_VARIANT) not in {"malouf", "reverie_v1", "reverie_v2"}
                      or entry.data.get("product_type") == "none"))
        and not (entry.data.get(CONF_BED_TYPE) == "saatva"
                 and entry.data.get(CONF_PROTOCOL_VARIANT) not in SAATVA_TWO_RECEIVER_PROFILES)
        and entry.entry_id not in group_members
        and isinstance((address := entry.data.get(CONF_ADDRESS)), str)
        and address.upper() not in absorbed_addresses
    ]
    # Only beds of one protocol can become two sides of one bed, so a bed with
    # no partner of its own type is never offered (or suggested in Repairs).
    protocols = Counter(_protocol(entry) for entry in standalone)
    return [entry for entry in standalone if protocols[_protocol(entry)] >= 2]


def _protocol(entry: ConfigEntry) -> str | None:
    """Return the concrete protocol the pairing flow compares, as it resolves it."""
    return resolve_explicit_bed_type(
        entry.data.get(CONF_BED_TYPE), entry.data.get(CONF_PROTOCOL_VARIANT)
    )


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
    """Build every Left/Right assignment of two beds of one protocol."""
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
        if left.entry_id != right.entry_id and _protocol(left) == _protocol(right)
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
