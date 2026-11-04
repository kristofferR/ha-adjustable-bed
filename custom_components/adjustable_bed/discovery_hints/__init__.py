"""Bluetooth discovery hints, one module per family (#780).

Each public module declares ``HINTS``: the advertised service UUIDs, local
names and manufacturer records that lead to its bed types. Parallel family PRs
edit only their own module; this package discovers them.

The hints are the one source for both discovery steps:

- ``scripts/generate_bluetooth_matchers.py`` writes the manifest's
  ``bluetooth`` list from ``manifest_matchers()``, and its ``--check`` mode
  fails CI when the manifest drifts.
- Detection's first pass, ``first_pass()``, matches an advertisement against
  the same hints. Refinement from names, GATT, model or device info stays in
  ``detection.py``.

``_excluded.py`` holds the non-bed name fragments detection rejects.
"""

from __future__ import annotations

import importlib
import json
import pkgutil
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ._excluded import EXCLUDED_DEVICE_PATTERNS, GENERIC_SHARED_SERVICE_UUIDS
from ._hints import (
    Advertisement,
    Hint,
    ManufacturerHint,
    Matcher,
    NameHint,
    ServiceHint,
)

if TYPE_CHECKING:
    from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

__all__ = [
    "EXCLUDED_DEVICE_PATTERNS",
    "GENERIC_SHARED_SERVICE_UUIDS",
    "HINTS_BY_FAMILY",
    "FirstPass",
    "Hint",
    "first_pass",
    "manifest_matchers",
]


def _families() -> dict[str, tuple[Hint, ...]]:
    return {
        info.name: importlib.import_module(f"{__name__}.{info.name}").HINTS
        for info in pkgutil.iter_modules(__path__)
        if not info.name.startswith("_")
    }


# Loaded with detection, which Home Assistant imports in its executor.
HINTS_BY_FAMILY: Mapping[str, tuple[Hint, ...]] = _families()
_ALL_HINTS: tuple[Hint, ...] = tuple(hint for hints in HINTS_BY_FAMILY.values() for hint in hints)

# Manifest order: service UUIDs, then manufacturer records, then local names.
_KIND_ORDER = ("service_uuid", "manufacturer_id", "local_name")


def _identity(matcher: Matcher) -> tuple[int, str, int | str, str]:
    """What a matcher matches, ignoring ``connectable``, as its sort key."""
    kind = next(key for key in _KIND_ORDER if key in matcher)
    value = matcher[kind]
    assert isinstance(value, int | str)
    rest = {key: value for key, value in matcher.items() if key != "connectable"}
    return _KIND_ORDER.index(kind), kind, value, json.dumps(rest, sort_keys=True)


def manifest_matchers() -> list[Matcher]:
    """The manifest's ``bluetooth`` list, deduplicated in a stable order.

    Families may declare the same signal. They must then agree on
    ``connectable``, so the list never holds two spellings of one matcher.
    """
    merged: dict[tuple[int, str, int | str, str], Matcher] = {}
    for hint in _ALL_HINTS:
        for matcher in hint.matchers():
            identity = _identity(matcher)
            known = merged.setdefault(identity, matcher)
            if known != matcher:
                raise ValueError(f"conflicting discovery hints: {known} and {matcher}")
    return [merged[identity] for identity in sorted(merged)]


@dataclass(frozen=True, slots=True)
class FirstPass:
    """The hints an advertisement matched."""

    hints: tuple[Hint, ...]

    @property
    def bed_types(self) -> frozenset[str]:
        """Every bed type a matched hint leads to."""
        return frozenset(bed_type for hint in self.hints for bed_type in hint.bed_types)

    def name(self, bed_type: str) -> bool:
        """Whether a name hint for this bed type matched."""
        return self._matched(NameHint, bed_type)

    def service(self, bed_type: str) -> bool:
        """Whether a service UUID hint for this bed type matched."""
        return self._matched(ServiceHint, bed_type)

    def manufacturer(self, bed_type: str) -> bool:
        """Whether a manufacturer data hint for this bed type matched."""
        return self._matched(ManufacturerHint, bed_type)

    def _matched(self, kind: type[Hint], bed_type: str) -> bool:
        return any(isinstance(hint, kind) and bed_type in hint.bed_types for hint in self.hints)


def advertisement(service_info: BluetoothServiceInfoBleak) -> Advertisement:
    """Normalize the advertisement fields that hints match."""
    return Advertisement(
        name=service_info.name or "",
        service_uuids=frozenset(str(uuid).lower() for uuid in service_info.service_uuids or ()),
        manufacturer_data=service_info.manufacturer_data or {},
    )


def first_pass(service_info: BluetoothServiceInfoBleak) -> FirstPass:
    """Match an advertisement against every declared hint.

    Matching follows Home Assistant's gate, except that ``connectable`` is the
    gate's concern and ``anywhere`` name hints also match after the start.
    """
    adv = advertisement(service_info)
    return FirstPass(tuple(hint for hint in _ALL_HINTS if hint.matches(adv)))
