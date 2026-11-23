"""Controller-state doubles for controller tests."""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
from typing import Any

from custom_components.adjustable_bed.controller_state import StateUpdate
from custom_components.adjustable_bed.state_keys import massage_intensity


def state_writer(state: MutableMapping[str, object]) -> Callable[..., None]:
    """A ``handle_controller_state_updates`` double that stores into ``state``."""

    def write(*updates: StateUpdate) -> None:
        state.update((update.key, update.value) for update in updates)

    return write


def published(*updates: StateUpdate) -> dict[str, Any]:
    """The name-to-value mapping of ``updates``, for asserting on a publish call."""
    return {update.key: update.value for update in updates}


def massage_levels(state: Mapping[str, object], *zones: str) -> dict[str, object]:
    """Each zone's published massage intensity, keyed by zone."""
    return {zone: state.get(massage_intensity(zone)) for zone in zones}
