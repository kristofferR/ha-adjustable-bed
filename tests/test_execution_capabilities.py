"""Every execution-capability declaration needs reviewed evidence (#483, #516).

``EVIDENCE`` maps each bed type or family profile that declares a capability
to the keys proving it, per declared field. Keys are defined in the
"Evidence keys" section of ``docs/design/execution-capabilities.md``. A
declaration without a row fails here, so adding a capability needs a reviewed
evidence row, and a row whose declaration is gone fails too.

Profiles are identified as ``"<ProfileClass>:<key>"``; standalone controllers
by bed type.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path

import pytest

from custom_components.adjustable_bed.const import SUPPORTED_BED_TYPES, VARIANT_AUTO
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.execution import (
    NO_EXECUTION_CAPABILITIES,
    ExecutionCapabilities,
)
from tests.codec_families import families
from tests.test_controller_contract import (
    _create_controller_for_bed_type,
    _FactoryCoordinator,
    _make_connected_client,
)

FAMILIES = families()
APP_ROUTES = {
    bed_type: route for family in FAMILIES.values() for bed_type, route in family.app_routes.items()
}
DESIGN = Path(__file__).parents[1] / "docs" / "design" / "execution-capabilities.md"

# Declaration -> declared field -> evidence keys from the design document.
EVIDENCE: dict[str, Mapping[str, tuple[str, ...]]] = {}


def _design_evidence_keys() -> frozenset[str]:
    """Keys of both tables in the design's "Evidence keys" section."""
    section = DESIGN.read_text().split("\n## Evidence keys\n", 1)[1]
    keys = {
        match.group(1)
        for line in section.splitlines()
        if (match := re.match(r"\|\s*([^|\s]+)\s*\|", line))
    }
    return frozenset(keys - {"Key", "---"})


def _instances(value: object, cls: type, depth: int = 0) -> Iterator[object]:
    if isinstance(value, cls):
        yield value
    elif depth < 2 and isinstance(value, Mapping):
        for item in value.values():
            yield from _instances(item, cls, depth + 1)
    elif depth < 2 and isinstance(value, (tuple, list, frozenset, set)):
        for item in value:
            yield from _instances(item, cls, depth + 1)


async def _family_profiles() -> dict[str, ExecutionCapabilities]:
    """Every reachable family profile's declaration, by identity.

    Static profiles are found in their modules; profiles built at runtime are
    reached through each bed type's and app route's controller.
    """
    registered = {cls for family in FAMILIES.values() for cls in family.profiles}
    profiles = [
        profile
        for cls in registered
        for value in vars(sys.modules[cls.__module__]).values()
        for profile in _instances(value, cls)
    ]
    for bed_type in SUPPORTED_BED_TYPES:
        profiles.append(getattr(await _create_controller_for_bed_type(bed_type), "profile", None))
    for bed_type, (config_key, choices) in APP_ROUTES.items():
        for choice in choices:
            coordinator = _FactoryCoordinator()
            coordinator.entry.data[config_key] = choice
            controller = await create_controller(
                coordinator, bed_type, VARIANT_AUTO, _make_connected_client()
            )
            profiles.append(getattr(controller, "profile", None))

    declared: dict[str, ExecutionCapabilities] = {}
    for profile in profiles:
        if type(profile) not in registered:
            continue
        execution = getattr(profile, "execution", None)
        assert isinstance(execution, ExecutionCapabilities), profile
        identity = _identity(profile)
        # One identity must not carry two different declarations.
        assert declared.setdefault(identity, execution) == execution, identity
    # Vectors are frozen per profile key, so the scan must reach every
    # profile that has them. Otherwise a declaration could hide.
    for name, family in FAMILIES.items():
        reached = {
            identity.split(":", 1)[1]
            for identity in declared
            if identity.split(":", 1)[0] in {cls.__name__ for cls in family.profiles}
        }
        frozen = {key for vectors in family.profiles.values() for key in vectors}
        assert frozen <= reached, (name, frozen - reached)
    return declared


def _identity(profile: object) -> str:
    return f"{type(profile).__name__}:{getattr(profile, 'key', None)}"


async def _declarations() -> dict[str, frozenset[str]]:
    return {
        identity: execution.declared
        for identity, execution in (await _family_profiles()).items()
        if execution.declared
    }


def test_evidence_keys_exist_in_design() -> None:
    known = _design_evidence_keys()
    assert {"p4", "useries", "clarity", "svane"} <= known
    for identity, fields in EVIDENCE.items():
        for name, keys in fields.items():
            assert keys, f"{identity}.{name} needs at least one evidence key"
            assert not set(keys) - known, (identity, name, set(keys) - known)


async def test_every_profile_declaration_has_evidence() -> None:
    for identity, declared in (await _declarations()).items():
        assert identity in EVIDENCE, f"{identity} declares {sorted(declared)} without evidence"
        assert set(EVIDENCE[identity]) == declared, (identity, sorted(declared))


@pytest.mark.parametrize("bed_type", SUPPORTED_BED_TYPES)
async def test_every_controller_declaration_has_evidence(bed_type: str) -> None:
    """A controller declares through its family profile, or has its own row."""
    controller = await _create_controller_for_bed_type(bed_type)
    execution = controller.execution
    assert isinstance(execution, ExecutionCapabilities)
    if not execution.declared:
        return
    profile = getattr(controller, "profile", None)
    registered = {cls for family in FAMILIES.values() for cls in family.profiles}
    if type(profile) in registered and getattr(profile, "execution", None) is execution:
        identity = _identity(profile)
    else:
        identity = bed_type
    assert identity in EVIDENCE, f"{identity} declares {sorted(execution.declared)}"
    assert set(EVIDENCE[identity]) == execution.declared, identity


async def test_evidence_rows_match_live_declarations() -> None:
    """A row whose declaration was removed must go too."""
    assert {identity for identity in EVIDENCE if ":" in identity} <= set(await _declarations())
    assert {identity for identity in EVIDENCE if ":" not in identity} <= set(
        SUPPORTED_BED_TYPES
    )


def test_default_declares_nothing() -> None:
    assert NO_EXECUTION_CAPABILITIES.declared == frozenset()
    assert ExecutionCapabilities(
        hold="stream", sustain_ms=217, concurrent=frozenset({"motor:back", "motor:legs"})
    ).declared == {"hold", "sustain_ms", "concurrent"}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"hold": "pulsed"},
        {"sustain_ms": 200},
        {"hold": "stream", "sustain_ms": 0},
        {"concurrent": frozenset({"motor:back"})},
        {"concurrent": frozenset({"motor:back", ""})},
    ],
)
def test_invalid_declarations_are_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ExecutionCapabilities(**kwargs)  # type: ignore[arg-type]
