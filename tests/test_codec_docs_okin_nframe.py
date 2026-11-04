"""Okin N-frame guide checks the generic docs tests cannot express.

Some profiles are reached through entry data, not a protocol variant: the
AdjustableM5X4 command selector and the SleepEase saved app model. So this
family checks its guide's bed types here instead of through ``bed_types()``.
"""

from __future__ import annotations

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.profiles.okin_nframe import STARCODE_ABM5_4_PROFILES
from scripts.codec_docs import okin_nframe as docs
from tests.codec_families.okin_nframe import FAMILY
from tests.test_controller_contract import _FactoryCoordinator, _make_connected_client


async def test_every_profile_is_listed_and_built_for_its_bed_types() -> None:
    """The profile summary lists every frozen profile, and each bed type builds it."""
    profiles = docs._okin_profiles()
    assert {p.key for p in profiles} == {k for v in FAMILY.profiles.values() for k in v}
    assert FAMILY.guide is not None
    selectors = {p.key: s for s, p in reversed(list(STARCODE_ABM5_4_PROFILES.items()))}
    for profile in profiles:
        assert profile.bed_types, profile.key
        for bed_type in profile.bed_types:
            coordinator = _FactoryCoordinator()
            coordinator.entry.options = {}
            coordinator.entry.data[const.CONF_LEGGETT_APP_PROFILE] = profile.key
            if selector := selectors.get(profile.key):
                coordinator.entry.data[const.CONF_STARCODE_COMMAND_SELECTOR] = selector
            if bed_type == const.BED_TYPE_DOUBLESLEEP:
                coordinator.entry.data[const.CONF_PRODUCT_TYPE] = 3  # a saved app model
            variant = FAMILY.guide.variant(profile.key, bed_type)
            controller = await create_controller(
                coordinator, bed_type, variant, _make_connected_client()
            )
            assert getattr(controller, "profile", None) is profile, (profile.key, bed_type)
