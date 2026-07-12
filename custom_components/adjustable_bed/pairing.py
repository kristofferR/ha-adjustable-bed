"""Paired-bed (Dual Bed 4.0) data model helpers.

A *paired* config entry models one logical bed made of two sides. It carries a
synthetic :data:`~.const.CONF_PAIR_ID` plus an ordered list of two child
descriptors under :data:`~.const.CONF_PAIR_CHILDREN`. Ordinary single-bed
entries never carry ``CONF_PAIR_ID`` and are completely unaffected by anything
here.

This module is intentionally pure (no Home Assistant imports beyond the config
key constants): it transforms plain ``entry.data`` mappings so callers stay in
control of when to persist via ``hass.config_entries.async_update_entry``.

See ``docs/design/dual-bed-4.0-plan.md`` for the full design. These helpers are
shared by the pairing wizard, paired coordinator, and lossless unpair path.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from typing import Any, Final, TypedDict, cast

from homeassistant.const import CONF_ADDRESS, CONF_NAME

from .const import (
    CONF_BED_TYPE,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_CONNECTION_MODE,
    CONF_PAIR_ID,
    CONF_PAIR_MEMBER_ADDRESSES,
    CONF_PAIR_MODE,
    CONF_PAIR_SCHEMA_VERSION,
    CONF_SIDE,
    PAIR_MODE_SEPARATE_ADDRESS,
    PAIR_SCHEMA_VERSION,
    PAIR_SIDES,
    SIDE_LEFT,
    SIDE_RIGHT,
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
    # Set once a BLE bond is established, so future connects skip pairing.
    ble_bond_established: bool
    # Provenance, used to revert an opt-in conversion (unpair) losslessly.
    absorbed_entry_id: str
    origin_unique_id: str
    origin_title: str
    origin_source: str
    origin_data: dict[str, Any]
    origin_options: dict[str, Any]


# Descriptor provenance keys (mirror the ``ChildDescriptor`` fields above).
# Recorded when two singles are combined so the pair's setup can re-home each
# original entry's registry rows in place (additive, history-preserving) and a
# unpair can recreate the single losslessly. Module constants keep the
# config-flow writer and the setup reader from drifting on a stringly-typed key.
KEY_ABSORBED_ENTRY_ID: Final = "absorbed_entry_id"
KEY_ORIGIN_UNIQUE_ID: Final = "origin_unique_id"
KEY_ORIGIN_TITLE: Final = "origin_title"
KEY_ORIGIN_SOURCE: Final = "origin_source"
KEY_ORIGIN_DATA: Final = "origin_data"
KEY_ORIGIN_OPTIONS: Final = "origin_options"
PAIR_LAYOUT_CAPABILITY_KEY: Final = "pair_layout"


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


def get_child(entry_data: Mapping[str, Any], side: str) -> ChildDescriptor | None:
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

    updated: list[dict[str, Any]] = []
    matched = False
    for child in children:
        if child.get(CONF_SIDE) == side:
            updated.append({**child, **patch})
            matched = True
        else:
            updated.append({**child})

    if not matched:
        raise ValueError(f"Paired entry has no child for side {side!r}")

    new_data = dict(entry_data)
    new_data[CONF_PAIR_CHILDREN] = updated
    return new_data


# Pair-only keys live on the parent and must never appear in a child descriptor
# built from a single-bed entry's data.
_PAIR_ONLY_DESCRIPTOR_KEYS = frozenset(
    {
        CONF_PAIR_ID,
        CONF_PAIR_MODE,
        CONF_PAIR_CHILDREN,
        CONF_PAIR_MEMBER_ADDRESSES,
        CONF_PAIR_SCHEMA_VERSION,
        CONF_PAIR_CONNECTION_MODE,
    }
)


def octo_snapshot_from_descriptor(
    descriptor: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Return a side's persisted Octo capability snapshot, or None.

    The snapshot lives under the descriptor's ``capabilities`` dict, namespaced
    by bed type (``capabilities['octo']``). Old pairs that predate the snapshot
    simply have no ``capabilities``/``octo`` key and fall back to None.
    """
    if not descriptor:
        return None
    caps = descriptor.get("capabilities") or {}
    octo = caps.get("octo")
    return dict(octo) if isinstance(octo, Mapping) else None


def pair_layout_from_descriptor(
    descriptor: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Return the persisted generic motor-layout snapshot for one side."""
    if not descriptor:
        return None
    caps = descriptor.get("capabilities") or {}
    layout = caps.get(PAIR_LAYOUT_CAPABILITY_KEY)
    return dict(layout) if isinstance(layout, Mapping) else None


def single_data_from_child(descriptor: Mapping[str, Any]) -> dict[str, Any]:
    """Reconstruct standalone entry data from a paired child descriptor.

    Pair-only routing/provenance and capability snapshots are removed. All
    ordinary bed configuration, including options folded into the descriptor at
    pairing time, is retained.
    """
    origin_data = descriptor.get(KEY_ORIGIN_DATA)
    if isinstance(origin_data, Mapping):
        return dict(origin_data)

    data = {
        key: value
        for key, value in descriptor.items()
        if key
        not in {
            CONF_SIDE,
            KEY_ABSORBED_ENTRY_ID,
            KEY_ORIGIN_UNIQUE_ID,
            KEY_ORIGIN_TITLE,
            KEY_ORIGIN_SOURCE,
            KEY_ORIGIN_DATA,
            KEY_ORIGIN_OPTIONS,
        }
    }
    capabilities = data.get("capabilities")
    if isinstance(capabilities, Mapping):
        remaining = {
            key: value
            for key, value in capabilities.items()
            if key not in {PAIR_LAYOUT_CAPABILITY_KEY, "octo"}
        }
        if remaining:
            data["capabilities"] = remaining
        else:
            data.pop("capabilities", None)
    return data


def single_options_from_child(descriptor: Mapping[str, Any]) -> dict[str, Any]:
    """Return the original standalone options when provenance is available."""
    origin_options = descriptor.get(KEY_ORIGIN_OPTIONS)
    return dict(origin_options) if isinstance(origin_options, Mapping) else {}


def _descriptor_from_single(
    data: Mapping[str, Any],
    side: str,
    octo_snapshot: Mapping[str, Any] | None = None,
    layout_snapshot: Mapping[str, Any] | None = None,
    *,
    absorbed_entry_id: str | None = None,
    origin_unique_id: str | None = None,
    origin_title: str | None = None,
    origin_source: str | None = None,
    origin_data: Mapping[str, Any] | None = None,
    origin_options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a child descriptor from a single-bed entry's data.

    ``octo_snapshot`` is an optional Octo capability snapshot captured from the
    live bed at pairing; it is stored under ``capabilities['octo']`` so an OFFLINE
    paired side can be minted with the right light/RGBW/memory/synchro entities.

    ``absorbed_entry_id`` / ``origin_unique_id`` are the original single entry's
    provenance, recorded so the pair's setup can re-home its registry rows in
    place (history-preserving conversion) and unpair can recreate it.
    """
    descriptor = {
        key: value for key, value in data.items() if key not in _PAIR_ONLY_DESCRIPTOR_KEYS
    }
    descriptor[CONF_SIDE] = side
    if octo_snapshot or layout_snapshot:
        capabilities = dict(descriptor.get("capabilities") or {})
        if octo_snapshot:
            capabilities["octo"] = dict(octo_snapshot)
        if layout_snapshot:
            capabilities[PAIR_LAYOUT_CAPABILITY_KEY] = dict(layout_snapshot)
        descriptor["capabilities"] = capabilities
    if absorbed_entry_id:
        descriptor[KEY_ABSORBED_ENTRY_ID] = absorbed_entry_id
    if origin_unique_id:
        descriptor[KEY_ORIGIN_UNIQUE_ID] = origin_unique_id
    if origin_title:
        descriptor[KEY_ORIGIN_TITLE] = origin_title
    if origin_source:
        descriptor[KEY_ORIGIN_SOURCE] = origin_source
    if origin_data is not None:
        descriptor[KEY_ORIGIN_DATA] = dict(origin_data)
    if origin_options is not None:
        descriptor[KEY_ORIGIN_OPTIONS] = dict(origin_options)
    return descriptor


def build_pair_entry_data(
    left_data: Mapping[str, Any],
    right_data: Mapping[str, Any],
    *,
    name: str,
    connection_mode: str | None = None,
    left_octo_snapshot: Mapping[str, Any] | None = None,
    right_octo_snapshot: Mapping[str, Any] | None = None,
    left_layout_snapshot: Mapping[str, Any] | None = None,
    right_layout_snapshot: Mapping[str, Any] | None = None,
    left_origin: tuple[str, str | None] | None = None,
    right_origin: tuple[str, str | None] | None = None,
    left_origin_title: str | None = None,
    right_origin_title: str | None = None,
    left_origin_source: str | None = None,
    right_origin_source: str | None = None,
    left_origin_data: Mapping[str, Any] | None = None,
    right_origin_data: Mapping[str, Any] | None = None,
    left_origin_options: Mapping[str, Any] | None = None,
    right_origin_options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a separate-address paired entry's data from two single-bed datas.

    Each single bed becomes a child descriptor (its full config, plus a ``side``).
    The shared family ``bed_type`` is taken from the left side. The synthetic
    ``pair_id`` is deterministic, so re-pairing the same two MACs is idempotent.

    ``left_octo_snapshot`` / ``right_octo_snapshot`` are optional per-side Octo
    capability snapshots captured from the live beds at pairing.

    ``left_origin`` / ``right_origin`` are each ``(entry_id, unique_id)`` for the
    original single entry being absorbed, recorded as descriptor provenance so the
    pair's setup re-homes that entry's registry rows in place instead of letting
    the platforms recreate them (preserving per-side history/customizations).
    """
    left_addr = left_data[CONF_ADDRESS]
    right_addr = right_data[CONF_ADDRESS]
    left_entry_id, left_unique_id = left_origin or (None, None)
    right_entry_id, right_unique_id = right_origin or (None, None)

    data: dict[str, Any] = {
        CONF_PAIR_ID: make_pair_id([left_addr, right_addr]),
        CONF_PAIR_MODE: PAIR_MODE_SEPARATE_ADDRESS,
        CONF_PAIR_SCHEMA_VERSION: PAIR_SCHEMA_VERSION,
        CONF_BED_TYPE: left_data.get(CONF_BED_TYPE),
        CONF_NAME: name,
        CONF_PAIR_MEMBER_ADDRESSES: [left_addr.upper(), right_addr.upper()],
        CONF_PAIR_CHILDREN: [
            _descriptor_from_single(
                left_data,
                SIDE_LEFT,
                left_octo_snapshot,
                left_layout_snapshot,
                absorbed_entry_id=left_entry_id,
                origin_unique_id=left_unique_id,
                origin_title=left_origin_title,
                origin_source=left_origin_source,
                origin_data=left_origin_data,
                origin_options=left_origin_options,
            ),
            _descriptor_from_single(
                right_data,
                SIDE_RIGHT,
                right_octo_snapshot,
                right_layout_snapshot,
                absorbed_entry_id=right_entry_id,
                origin_unique_id=right_unique_id,
                origin_title=right_origin_title,
                origin_source=right_origin_source,
                origin_data=right_origin_data,
                origin_options=right_origin_options,
            ),
        ],
    }
    if connection_mode is not None:
        data[CONF_PAIR_CONNECTION_MODE] = connection_mode
    return data
