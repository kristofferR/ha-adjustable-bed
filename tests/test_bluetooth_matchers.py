"""The manifest's Bluetooth matchers are generated from the declared discovery hints."""

from __future__ import annotations

import json
from itertools import count
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from homeassistant.components.bluetooth.match import IntegrationMatcher

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.discovery_hints import (
    HINTS_BY_FAMILY,
    first_pass,
    manifest_matchers,
)
from custom_components.adjustable_bed.discovery_hints._hints import (
    Hint,
    ManufacturerHint,
    NameHint,
    ServiceHint,
)
from custom_components.adjustable_bed.profiles.richmat_mh_apps import SURFACE_IDS
from scripts import generate_bluetooth_matchers as generator

MANIFEST = Path(__file__).parents[1] / "custom_components" / "adjustable_bed" / "manifest.json"
HINTS = [(family, hint) for family, hints in HINTS_BY_FAMILY.items() for hint in hints]
_addresses = count()


def _manifest_matchers() -> list[dict]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["bluetooth"]


def _key(matcher: dict) -> str:
    return json.dumps(matcher, sort_keys=True)


def _info(name: str = "", service_uuids: tuple[str, ...] = (), manufacturer_data=None) -> MagicMock:
    info = MagicMock()
    info.name = name
    # The gate remembers matched addresses, so every advertisement gets its own.
    info.address = f"AA:BB:CC:{next(_addresses):06X}"
    info.connectable = True
    info.service_uuids = list(service_uuids)
    info.service_data = {}
    info.manufacturer_data = manufacturer_data or {}
    return info


def _gate() -> IntegrationMatcher:
    gate = IntegrationMatcher([{"domain": DOMAIN, **matcher} for matcher in _manifest_matchers()])
    gate.async_setup()
    return gate


def _advertisements(hint: Hint) -> list[MagicMock]:
    """Advertisements that each carry exactly one of the hint's signals."""
    match hint:
        case ServiceHint():
            return [_info(service_uuids=(hint.uuid,))]
        case ManufacturerHint():
            return [_info(manufacturer_data={hint.company_id: hint.data_start + b"\x00"})]
        case NameHint():
            return [_info(name=glob.replace("*", "x")) for glob in hint.globs]
    raise AssertionError(hint)


def test_manifest_matchers_equal_the_declared_hints() -> None:
    """The manifest holds exactly the hints' matchers, apart from order."""
    generated = {_key(matcher) for matcher in manifest_matchers()}
    manifest = {_key(matcher) for matcher in _manifest_matchers()}
    assert generated - manifest == set(), "declared but not in the manifest"
    assert manifest - generated == set(), "in the manifest but not declared"
    assert len(_manifest_matchers()) == len(manifest), "the manifest repeats a matcher"


def test_manifest_is_current() -> None:
    assert generator.main(["--check"]) == 0, (
        "Run `uv run --no-sync python scripts/generate_bluetooth_matchers.py` and commit"
    )


def test_every_manifest_matcher_maps_to_a_declared_hint() -> None:
    declared = {_key(matcher) for _, hint in HINTS for matcher in hint.matchers()}
    assert [m for m in _manifest_matchers() if _key(m) not in declared] == []


@pytest.mark.parametrize(
    ("family", "hint"), HINTS, ids=[f"{family}-{index}" for index, (family, _) in enumerate(HINTS)]
)
def test_every_hint_is_reachable_through_a_matcher(family: str, hint: Hint) -> None:
    """Home Assistant's gate admits each hint's signal, and the first pass sees it."""
    gate = _gate()
    for info in _advertisements(hint):
        assert DOMAIN in gate.match_domains(info), (family, info.name)
        assert hint in first_pass(info).hints, (family, info.name)


def test_hints_lead_to_known_bed_types() -> None:
    known = {
        value
        for name, value in vars(const).items()
        if name.startswith("BED_TYPE_") and isinstance(value, str)
    }
    assert {
        family: sorted(hint.bed_types - known) for family, hint in HINTS if hint.bed_types - known
    } == {}


def test_name_hints_spell_only_case_variants() -> None:
    """Spellings exist for the case-sensitive gate; they never widen a pattern."""
    for family, hint in HINTS:
        if isinstance(hint, NameHint):
            folded = {pattern.lower() + "*" for pattern in hint.patterns}
            assert {glob.lower() for glob in hint.globs} == folded, family


def test_anywhere_names_match_after_the_start_but_the_gate_needs_a_prefix() -> None:
    """GM Control's scan accepts a keyword anywhere, case-sensitively."""
    assert first_pass(_info(name="X6BRM123")).name(const.BED_TYPE_GMMOTOR)
    assert not first_pass(_info(name="x6brm123")).name(const.BED_TYPE_GMMOTOR)
    assert first_pass(_info(name="6BRM123")).name(const.BED_TYPE_GMMOTOR)


def test_matcher_count_stays_bounded() -> None:
    """Each pattern is spelled at most twice, so no hint expands into case permutations."""
    for family, hint in HINTS:
        if isinstance(hint, NameHint):
            assert len(hint.matchers()) <= 2 * len(hint.patterns), family
    assert len(manifest_matchers()) <= 2000


@pytest.mark.parametrize(
    "name",
    [
        "Firmware Update", "WarmTouch 12", "Wormhole", "Warmup4ie", "Terminal",
        "Sleep Sound", "SleepPhones", "Okinawa", "sTaRlInK",
    ],
)
def test_unrelated_names_do_not_reach_discovery(name: str) -> None:
    """Apps that read a name in any case still admit only the spellings beds advertise."""
    assert DOMAIN not in _gate().match_domains(_info(name=name))
    assert first_pass(_info(name=name)).hints == ()


@pytest.mark.parametrize("model", sorted(model for model in SURFACE_IDS if len(model) == 4))
def test_nisco_and_mlily_supreme_models_are_discovered_as_advertised(model: str) -> None:
    """The app reads its four-character model ID in any case; beds advertise it in upper case."""
    info = _info(name=f"{model.upper()}0001")
    assert DOMAIN in _gate().match_domains(info)
    assert detect_bed_type_detailed(info).bed_type is not None
