"""Exact app selectors and command lookup from accepted row018 evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError, astuple

import pytest

from custom_components.adjustable_bed.richmat_profiles import (
    RICHMAT_PRODUCT_CODES,
    get_product_profile,
)

DETAILS = "get _ detailsPageDisplayList"


def test_catalog_matches_every_accepted_ordered_field() -> None:
    """Fingerprint independently derived from the frozen source table pair.

    This includes all selectors, empty products, getters, occurrence positions,
    action identities, effective bytes, gestures, buttons, and nullable overrides.
    It catches missing, reordered, accidentally collapsed, or altered mappings.
    """
    catalog = []
    for code in RICHMAT_PRODUCT_CODES:
        profile = get_product_profile(code)
        assert profile is not None
        catalog.append([code, [astuple(action) for action in profile.actions]])
    digest = hashlib.sha256(json.dumps(catalog, separators=(",", ":")).encode()).hexdigest()
    assert digest == "22e002a77916758ba3be729faeb98ed8a8ac3a4d1bee84e2ea5df326771c8fc4"
    assert len(catalog) == 1167
    assert sum(len(item[1]) for item in catalog) == 16578


def test_exact_selector_not_legacy_remote_inference() -> None:
    assert get_product_profile("A0RM") == get_product_profile("a0rm")
    assert get_product_profile("A0RM").code == "A0RM"
    assert get_product_profile("hja3") is None
    assert get_product_profile("RMDeviceProductA0RM") is None
    assert get_product_profile("A0RM ") is None
    assert get_product_profile("") is None
    assert get_product_profile("auto") is None
    assert get_product_profile("ßrm") is None


def test_concrete_empty_selector_does_not_inherit_any_other_catalog() -> None:
    profile = get_product_profile("A3RN")
    assert profile is not None
    assert profile.actions == ()
    assert profile.getter_names == ()
    assert profile.resolve_action("deviceFunctionItemHeadUp") is None


def test_repaired_allocation_does_not_become_list_length_override() -> None:
    profile = get_product_profile("A0RM")
    foot = profile.resolve_action("deviceFunctionItemFootUp")
    pillow = profile.resolve_action("deviceFunctionItemPillowUp")
    assert foot.short_opcode == 0x26
    assert foot.short_override is None
    assert pillow.short_opcode == 0x3F
    assert pillow.short_override == 0x3F
    assert foot.operate == "sustainPress"


def test_explicit_zero_is_not_lost_to_fallback() -> None:
    action = get_product_profile("E3RM").resolve_action("deviceFunctionItemMemory")
    assert action.short_override == 0
    assert action.short_opcode == 0
    assert action.long_override is None


def test_conflicting_nordic_commands_require_getter_context() -> None:
    profile = get_product_profile("A3RM")
    name = "deviceFunctionItemZeroGravity"
    assert profile.resolve_action(name) is None
    matches = profile.find_actions(name)
    assert len(matches) == 2
    assert [item.nordic_short_opcode for item in matches] == [0x34, 0x45]
    assert profile.resolve_action(name, getter=DETAILS).nordic_short_opcode == 0x34
    assert profile.resolve_action(name, getter="get _ memoryList").nordic_short_opcode == 0x45
    assert profile.find_actions(name, getter="not a getter") == ()
    assert profile.resolve_action(name, getter="not a getter") is None


def test_equal_bytes_with_conflicting_gestures_are_ambiguous() -> None:
    profile = get_product_profile("A4RN")
    name = "deviceFunctionItemTVPosition"
    assert profile.resolve_action(name) is None
    assert profile.resolve_action(name, getter=DETAILS).operate == "shortAndLongPress"
    assert profile.resolve_action(name, getter="get _ alarmList").operate == "shortPress"


def test_equal_duplicates_keep_their_positions_and_resolve_safely() -> None:
    profile = get_product_profile("APRM")
    name = "deviceFunctionItemZeroGravity"
    duplicates = profile.find_actions(name, getter=DETAILS)
    assert [item.occurrence for item in duplicates] == [7, 8]
    assert duplicates[0].command_signature == duplicates[1].command_signature
    assert profile.resolve_action(name, getter=DETAILS) == duplicates[0]
    assert profile.getter_names == ("get _ motorList", DETAILS, "get _ massageList")


def test_profiles_are_immutable_and_cached() -> None:
    profile = get_product_profile("A0RM")
    assert get_product_profile("A0RM") is profile
    with pytest.raises(FrozenInstanceError):
        profile.code = "different"
    with pytest.raises(FrozenInstanceError):
        profile.actions[0].short_opcode = 1
    assert get_product_profile.cache_info().maxsize == 64


def test_scalar_metadata_matches_every_frozen_cell() -> None:
    """Fingerprint independently derived from the scalar report, excluding default selector."""
    values = sorted(
        [code, list(get_product_profile(code).settings)] for code in RICHMAT_PRODUCT_CODES
    )
    digest = hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()
    assert digest == "38517924de0b0526b532143fd139a5e932e5458f11b56d02029e6067d7be13a0"
    assert (
        sum(
            get_product_profile(code).settings.is_support_repeat_alarm
            for code in RICHMAT_PRODUCT_CODES
        )
        == 32
    )
    assert (
        sum(
            get_product_profile(code).settings.is_richmat_support_repeat_alarm
            for code in RICHMAT_PRODUCT_CODES
        )
        == 152
    )


def test_similarly_named_factory_settings_are_not_interchangeable() -> None:
    baseline = get_product_profile("A0RM").settings
    assert baseline.is_have_light_strip
    assert not baseline.is_richmat_have_light_strip
    assert not baseline.is_support_repeat_alarm
    assert get_product_profile("HNRN").settings.is_support_repeat_alarm
    assert (
        get_product_profile("PARN").settings.bed_light_display_type
        == "deviceBedLightDisplayCircleEightColorValue"
    )
    assert (
        get_product_profile("ETRN").settings.rmc_sleep_monitoring_type == "deviceSleepMonitoringBle"
    )
