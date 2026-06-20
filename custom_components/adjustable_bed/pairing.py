"""Paired-bed (Dual Bed 4.0) data model helpers.

A *paired* config entry models one logical bed made of two sides. It carries a
synthetic :data:`~.const.CONF_PAIR_ID` plus an ordered list of two child
descriptors under :data:`~.const.CONF_PAIR_CHILDREN`. Ordinary single-bed
entries never carry ``CONF_PAIR_ID`` and are completely unaffected by anything
here.

This module is intentionally pure (no Home Assistant imports beyond the config
key constants): it transforms plain ``entry.data`` mappings so callers stay in
control of when to persist via ``hass.config_entries.async_update_entry``.

See ``docs/design/dual-bed-4.0-plan.md`` for the full design. As of Phase 0
nothing creates a paired entry yet; these helpers are the scaffolding the
pairing wizard (Phase 1) and the paired coordinator build on.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import Any, TypedDict, cast

from homeassistant.const import CONF_ADDRESS

from .const import (
    CONF_PAIR_CHILDREN,
    CONF_PAIR_ID,
    CONF_PAIR_MEMBER_ADDRESSES,
    CONF_SIDE,
    PAIR_SIDES,
)


class ChildDescriptor(TypedDict, total=False):
    """One side of a paired bed.

    ``total=False`` because the optional fields (PIN, adapter, provenance) only
    apply to some bed types / pairing routes. ``side`` and ``address`` are
    always present in practice.
    """

    side: str
    address: str
    name: str
    bed_type: str
    protocol_variant: str
    preferred_adapter: str
    octo_pin: str
    jensen_pin: str
    cb24_bed_selection: int
    capabilities: dict[str, Any]
    # Provenance, used to revert an opt-in conversion (unpair) losslessly.
    absorbed_entry_id: str
    origin_unique_id: str


def is_paired(entry_data: Mapping[str, Any]) -> bool:
    """Return whether ``entry_data`` describes a paired bed."""
    return bool(entry_data.get(CONF_PAIR_ID))


def make_pair_id(addresses: Iterable[str]) -> str:
    """Return a stable, deterministic ``pair_<hash>`` for a set of member MACs.

    Order-independent and idempotent: re-pairing the same two devices yields the
    same id, so ``_abort_if_unique_id_configured`` rejects an accidental
    duplicate pair. A synthetic id is required because Home Assistant enforces
    one entry per member MAC, so a pair cannot claim either MAC as its
    ``unique_id``.
    """
    normalized = sorted({addr.upper() for addr in addresses if addr})
    if not normalized:
        raise ValueError("make_pair_id requires at least one member address")
    digest = hashlib.sha1("|".join(normalized).encode()).hexdigest()
    return f"pair_{digest[:12]}"


def iter_children(entry_data: Mapping[str, Any]) -> list[ChildDescriptor]:
    """Return the child descriptors for a paired entry (empty if not paired)."""
    children = entry_data.get(CONF_PAIR_CHILDREN)
    if not isinstance(children, list):
        return []
    return cast(
        "list[ChildDescriptor]",
        [child for child in children if isinstance(child, dict)],
    )


def get_child(
    entry_data: Mapping[str, Any], side: str
) -> ChildDescriptor | None:
    """Return the child descriptor for ``side`` (``left``/``right``) or ``None``."""
    for child in iter_children(entry_data):
        if child.get(CONF_SIDE) == side:
            return child
    return None


def pair_member_addresses(entry_data: Mapping[str, Any]) -> list[str]:
    """Return the normalized member MACs of a paired entry, order-stable.

    Prefers the flat ``CONF_PAIR_MEMBER_ADDRESSES`` list (kept for discovery
    dedup) and falls back to deriving them from the child descriptors. Each
    address appears once; uppercased.
    """
    raw: list[str] = []
    flat = entry_data.get(CONF_PAIR_MEMBER_ADDRESSES)
    if isinstance(flat, (list, tuple)):
        raw.extend(addr for addr in flat if isinstance(addr, str))
    for child in iter_children(entry_data):
        addr = child.get(CONF_ADDRESS)
        if isinstance(addr, str):
            raw.append(addr)

    seen: set[str] = set()
    result: list[str] = []
    for addr in raw:
        upper = addr.upper()
        if upper and upper not in seen:
            seen.add(upper)
            result.append(upper)
    return result


def with_updated_child(
    entry_data: Mapping[str, Any], side: str, patch: Mapping[str, Any]
) -> dict[str, Any]:
    """Return a copy of ``entry.data`` with the ``side`` child merged with ``patch``.

    Pure: the caller persists the result with ``async_update_entry``. This is the
    single chokepoint for runtime per-side mutations (e.g. a bed-type/angle
    correction), so such updates always target the right descriptor instead of
    exploding into flat top-level keys.

    Raises ``ValueError`` for an unknown side or a non-paired entry, so a
    mistargeted update fails loudly rather than silently writing nothing.
    """
    if side not in PAIR_SIDES:
        raise ValueError(f"Unknown pair side {side!r}; expected one of {PAIR_SIDES}")

    children = iter_children(entry_data)
    if not children:
        raise ValueError("with_updated_child called on a non-paired entry")

    updated: list[ChildDescriptor] = []
    matched = False
    for child in children:
        if child.get(CONF_SIDE) == side:
            merged: ChildDescriptor = {**child, **patch}  # type: ignore[misc]
            updated.append(merged)
            matched = True
        else:
            updated.append({**child})

    if not matched:
        raise ValueError(f"Paired entry has no child for side {side!r}")

    new_data = dict(entry_data)
    new_data[CONF_PAIR_CHILDREN] = updated
    return new_data
