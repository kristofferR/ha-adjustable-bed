"""Durable, physical-bed profile decisions shared by Repairs and support exports."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Final, Literal, TypedDict

from homeassistant.core import HomeAssistant

from .app_state_store import PROFILE_DECISIONS_SLOT, app_state_store
from .const import (
    CONF_BED_TYPE,
    CONF_MALOUF_LAYOUT,
    CONF_PRODUCT_TYPE,
    CONF_PROTOCOL_VARIANT,
    CONF_RICHMAT_REMOTE,
    CONF_RMCONTROL_PRODUCT,
    CONF_STARCODE_M5X5_PROFILE,
    CONF_VMATBASIC_PROFILE,
    VARIANT_AUTO,
)

_HISTORY: Final = "history"


class ProfileDecision(TypedDict):
    """Store selector values, not names, authentication state or full entry data."""

    decided_at: str
    decision: Literal["accepted", "dismissed"]
    source: Literal["keep", "ignore", "configure"]
    rule: str
    current: str
    suggested: str | None
    choices: list[str]
    previous_profile: dict[str, str]
    selected_profile: dict[str, str]


def profile_selection(data: Mapping[str, object]) -> dict[str, str]:
    """Copy only profile selectors, excluding PINs and unrelated configuration."""
    selection = {
        CONF_BED_TYPE: str(data.get(CONF_BED_TYPE) or ""),
        CONF_PROTOCOL_VARIANT: str(data.get(CONF_PROTOCOL_VARIANT) or VARIANT_AUTO),
    }
    for key, value in data.items():
        if isinstance(value, str) and (
            key
            in {
                CONF_RICHMAT_REMOTE,
                CONF_PRODUCT_TYPE,
                CONF_MALOUF_LAYOUT,
                CONF_RMCONTROL_PRODUCT,
                CONF_STARCODE_M5X5_PROFILE,
                CONF_VMATBASIC_PROFILE,
            }
            or key.endswith(("_app_profile", "_app_layout"))
        ):
            selection[key] = value
    return selection


async def async_record_profile_decision(
    hass: HomeAssistant,
    address: str,
    decision: ProfileDecision,
    confirmed_rules: Iterable[str],
) -> dict[str, Any]:
    """Save history and suppression flags together before confirming the action."""
    rules = tuple(confirmed_rules)

    def update(stored: dict[str, Any]) -> dict[str, Any]:
        history = list(stored.get(_HISTORY, []))
        return {
            **stored,
            **dict.fromkeys(rules, True),
            _HISTORY: [*history, deepcopy(decision)],
        }

    return await app_state_store(hass, address).async_update(PROFILE_DECISIONS_SLOT, update)


async def async_profile_decision_history(hass: HomeAssistant, address: str) -> dict[str, Any]:
    """Export this address only, including old flags whose details were never stored."""
    stored = await app_state_store(hass, address).async_slot(PROFILE_DECISIONS_SLOT)
    history = stored.get(_HISTORY, [])
    recorded_rules = {record["rule"] for record in history}
    return {
        "history": deepcopy(history),
        "legacy_dismissed_rules": sorted(
            rule
            for rule, decision in stored.items()
            if decision is True
            and rule not in recorded_rules
            and not rule.startswith("upgrade_review_")
        ),
    }


def decision_timestamp() -> str:
    """Use an absolute UTC timestamp in every support export."""
    return datetime.now(UTC).isoformat()
