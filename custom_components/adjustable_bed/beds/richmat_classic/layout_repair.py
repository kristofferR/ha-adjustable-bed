"""Beds a v5 beta saved with a factory-test layout, which v5 no longer builds.

The TEST and RMCS layouts held only a factory motor test and a motor
programming form, no ordinary bed controls. Nothing tells which layout the bed
really uses, so such a bed loads without controls or a connection, and a repair
asks for its layout in Configure. The repair goes once a bed layout is saved.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import TYPE_CHECKING, Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_refresh_issues,
)

from ...const import (
    BED_TYPE_RICHMAT_CLASSIC_APPS,
    CONF_BED_TYPE,
    CONF_PRODUCT_TYPE,
    DOMAIN,
    PAIR_SIDES,
)
from ...pairing import effective_child_data, get_child, is_paired

if TYPE_CHECKING:
    from ...coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

REMOVED_LAYOUTS: Final = frozenset({"TEST", "RMCS"})
ISSUE_PREFIX: Final = "richmat_classic_layout_"


def removed_layout(data: Mapping[str, Any]) -> str | None:
    """The removed layout a bed's saved setup names, if any."""
    if data.get(CONF_BED_TYPE) != BED_TYPE_RICHMAT_CLASSIC_APPS:
        return None
    layout = str(data.get(CONF_PRODUCT_TYPE, "")).strip().upper()
    return layout if layout in REMOVED_LAYOUTS else None


def _issue_id(entry_id: str, side: str | None) -> str:
    return f"{ISSUE_PREFIX}{entry_id}_{side or 'standalone'}"


@callback
def async_refresh_removed_layout_issues(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Raise the repair for each bed or side on a removed layout; clear the rest."""
    targets = (
        [
            (side, effective_child_data(entry.data, side, entry.options))
            for side in PAIR_SIDES
            if get_child(entry.data, side) is not None
        ]
        if is_paired(entry.data)
        else [(None, dict(entry.data))]
    )
    issue_ids = [_issue_id(entry.entry_id, side) for side in (None, *PAIR_SIDES)]
    with async_refresh_issues(hass, DOMAIN, issue_ids=issue_ids):
        for side, data in targets:
            if (layout := removed_layout(data)) is None:
                continue
            async_create_issue(
                hass,
                DOMAIN,
                _issue_id(entry.entry_id, side),
                config_entry_id=entry.entry_id,
                is_fixable=False,
                severity=IssueSeverity.WARNING,
                translation_key="richmat_classic_layout",
                translation_placeholders={
                    "name": entry.title if side is None else f"{entry.title} ({side})",
                    "layout": layout,
                },
            )


async def async_load_removed_layout_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    coordinator: AdjustableBedCoordinator,
    finish: Callable[[], Awaitable[None]],
) -> bool:
    """Load a standalone bed on a removed layout without connecting to it."""
    del hass, coordinator
    if (layout := removed_layout(entry.data)) is None:
        return False
    _LOGGER.warning(
        "%s was set up with the %s layout, which ran a factory test and is no longer "
        "offered. It loads without controls until a layout is chosen in Configure.",
        entry.title,
        layout,
    )
    await finish()
    return True
