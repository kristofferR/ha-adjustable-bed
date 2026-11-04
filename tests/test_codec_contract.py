"""Every bed type is a profile over a wire codec, or a listed exception (#742, #746).

Each codec family registers itself in its own module under
``tests/codec_families/``: its profile classes with their frozen vectors, the
bed types that are profiles over its codec, its app routes and the bed types
still pending migration onto it. ``tests/codec_families/_standalone.py`` lists
the bed types that stay standalone controllers. Every supported bed type must
appear exactly once across them.

A bed type is codec-backed when its controller's ``profile`` is a registered
profile class with frozen vectors for its key. Profile keys are scoped to their
profile class, so two families may share one (Jiecang and Limoss both call
their pre-v5 route ``legacy``). Migrating a bed type moves it from ``pending``
to ``bed_types`` in its family module; the test fails until you do.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from types import SimpleNamespace

import pytest

from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.const import SUPPORTED_BED_TYPES, VARIANT_AUTO
from custom_components.adjustable_bed.controller_factory import create_controller
from tests.codec_families import CodecFamily, families
from tests.codec_families._standalone import STANDALONE
from tests.test_controller_contract import (
    _create_controller_for_bed_type,
    _FactoryCoordinator,
    _make_connected_client,
)

FAMILIES: dict[str, CodecFamily] = families()
# Bed type -> the family whose codec backs it.
CODEC_BACKED: dict[str, str] = {
    bed_type: name for name, family in FAMILIES.items() for bed_type in family.bed_types
}
APP_ROUTES: dict[str, tuple[str, tuple[str, ...]]] = {
    bed_type: route for family in FAMILIES.values() for bed_type, route in family.app_routes.items()
}


def _codec_profile(
    controller: BedController, profiles: Mapping[type, Mapping[str, frozenset[str]]]
) -> str | None:
    """Return the profile key when the controller is a profile over one of these codecs."""
    profile = getattr(controller, "profile", None)
    vectors = profiles.get(type(profile))
    key = getattr(profile, "key", None)
    return key if vectors is not None and key in vectors else None


def _all_profiles() -> dict[type, Mapping[str, frozenset[str]]]:
    return {
        cls: vectors for family in FAMILIES.values() for cls, vectors in family.profiles.items()
    }


def test_every_bed_type_is_listed_exactly_once() -> None:
    listed = Counter(
        [
            *(bed_type for family in FAMILIES.values() for bed_type in family.bed_types),
            *(bed_type for family in FAMILIES.values() for bed_type in family.pending),
            *STANDALONE,
        ]
    )
    assert not {bed_type for bed_type, count in listed.items() if count > 1}, "listed twice"
    assert not set(listed) - set(SUPPORTED_BED_TYPES), "listed but not supported"
    assert not set(SUPPORTED_BED_TYPES) - set(listed), (
        "add these to a family's bed_types or pending, or to _standalone.py"
    )


def test_registrations_are_explained() -> None:
    profile_classes = Counter(cls for family in FAMILIES.values() for cls in family.profiles)
    assert not {cls for cls, count in profile_classes.items() if count > 1}
    for name, family in FAMILIES.items():
        assert family.profiles and family.bed_types, name
        assert set(family.app_routes) <= family.bed_types, name
        for bed_type, item in family.pending.items():
            assert item.startswith("#745 "), (name, bed_type)
    assert all(STANDALONE.values())


def test_profile_keys_are_scoped_to_their_class() -> None:
    """A profile key alone never counts: lookups go through the profile class."""
    for vectors in _all_profiles().values():
        for key in vectors:
            impostor = SimpleNamespace(profile=SimpleNamespace(key=key))
            assert _codec_profile(impostor, _all_profiles()) is None


@pytest.mark.parametrize("bed_type", SUPPORTED_BED_TYPES)
async def test_bed_type_is_a_profile_over_its_codec_or_listed(bed_type: str) -> None:
    controller = await _create_controller_for_bed_type(bed_type)
    if bed_type in CODEC_BACKED:
        family = FAMILIES[CODEC_BACKED[bed_type]]
        assert _codec_profile(controller, family.profiles) is not None, (
            f"{bed_type} needs a {CODEC_BACKED[bed_type]} profile with frozen vectors"
        )
    else:
        assert _codec_profile(controller, _all_profiles()) is None, (
            f"{bed_type} uses a codec profile; move it to its family's bed_types"
        )


@pytest.mark.parametrize(
    ("bed_type", "choice"),
    [(bed_type, choice) for bed_type, (_, choices) in APP_ROUTES.items() for choice in choices],
)
async def test_every_app_choice_is_a_profile_over_its_codec(bed_type: str, choice: str) -> None:
    coordinator = _FactoryCoordinator()
    coordinator.entry.data[APP_ROUTES[bed_type][0]] = choice
    controller = await create_controller(
        coordinator, bed_type, VARIANT_AUTO, _make_connected_client()
    )
    family = FAMILIES[CODEC_BACKED[bed_type]]
    assert _codec_profile(controller, family.profiles) == choice
