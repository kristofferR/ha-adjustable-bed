"""Legacy L&P catalog boundaries that differ from generic Richmat commands."""

from collections import Counter
from dataclasses import FrozenInstanceError

import pytest

from custom_components.adjustable_bed.lp_legacy_profiles import (
    LP_LEGACY_PROFILE_CODES,
    LpLegacyControl,
    get_lp_legacy_profile,
)


def control(code: str, key: str) -> LpLegacyControl:
    return next(item for item in get_lp_legacy_profile(code).controls if item.key == key)


def test_catalog_accounts_for_every_accepted_transport_event() -> None:
    """Every app control keeps its own completion, including unusual state-4 pairs."""
    profiles = [get_lp_legacy_profile(code) for code in LP_LEGACY_PROFILE_CODES]
    controls = [item for profile in profiles for item in profile.controls]
    assert len(profiles) == 122
    assert len(controls) == 1715
    assert (
        len({event.source_id for item in controls for event in (item.press, item.release)}) == 3430
    )
    assert Counter((item.press.state, item.release.state) for item in controls) == {
        (1, 2): 1245,
        (1, 4): 250,
        (3, 4): 90,
        (5, 2): 130,
    }
    assert get_lp_legacy_profile("I0RM").controls == ()
    for profile in profiles:
        assert len({item.key for item in profile.controls}) == len(profile.controls)


@pytest.mark.parametrize(
    ("code", "key", "legacy", "framed"),
    [
        ("6BRM", "btn1", "34", "6e01002493"),
        ("6BRM", "btn2", "37", "6e01002594"),
        ("6BRM", "btn4", "41", "6e01002796"),
        ("V8RM", "skinfmxbutton13", "58", "6e010053c2"),
        ("V8RM", "skinfmxbutton23", "61", "6e010062d1"),
    ],
)
def test_packet_mode_preserves_different_opcode(
    code: str, key: str, legacy: str, framed: str
) -> None:
    item = control(code, key)
    assert item.press.legacy == bytes.fromhex(legacy)
    assert item.press.framed == bytes.fromhex(framed)


def test_memory_long_press_does_not_invent_program_opcode() -> None:
    memory = control("A7RM", "skinfmxbutton2")
    assert memory.label == "MEM"
    assert memory.press.state == 3
    assert memory.release.state == 4
    assert memory.press.framed == memory.release.framed == bytes.fromhex("6e01002e9d")


def test_empty_token_is_distinct_from_undefined_packet_mode() -> None:
    empty_controls = [
        item
        for code in LP_LEGACY_PROFILE_CODES
        for item in get_lp_legacy_profile(code).controls
        if item.press.token == ""
    ]
    assert len(empty_controls) == 10
    assert Counter(item.press.state for item in empty_controls) == {1: 4, 5: 6}
    for item in empty_controls:
        assert item.press.legacy == b""
        assert item.press.framed == bytes.fromhex("6e0100006f")
        assert item.release.legacy == b"\x6e"
    legacy_only = control("V9RM", "skinfmxbutton11")
    assert legacy_only.press.legacy == b"\x4e"
    assert legacy_only.press.framed is None
    assert legacy_only.release.legacy == b"\x6e"
    assert legacy_only.release.framed is None


def test_catalog_frames_have_valid_checksum_and_keep_uncertain_labels() -> None:
    for code in LP_LEGACY_PROFILE_CODES:
        for item in get_lp_legacy_profile(code).controls:
            assert item.confidence in {"INFERRED", "TENTATIVE", "UNKNOWN"}
            for action in (item.press, item.release):
                assert action.legacy is None or len(action.legacy) <= 1
                if action.framed is not None:
                    assert len(action.framed) == 5
                    assert action.framed[:2] == b"\x6e\x01"
                    assert action.framed[-1] == sum(action.framed[:-1]) & 0xFF


def test_profiles_are_immutable_and_unknown_codes_never_fall_back() -> None:
    profile = get_lp_legacy_profile(" a7rm ")
    assert profile is get_lp_legacy_profile("A7RM")
    with pytest.raises(FrozenInstanceError):
        profile.code = "6BRM"  # type: ignore[misc]
    for code in ("auto", "QRRM", "LP-QRRM", "A7RM-more"):
        with pytest.raises(ValueError, match="Unknown legacy L&P profile"):
            get_lp_legacy_profile(code)
