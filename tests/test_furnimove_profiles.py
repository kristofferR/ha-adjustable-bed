"""Pinned production tables and the artifact's generic JSON parser contract."""

import hashlib
import json

import pytest

from custom_components.adjustable_bed.beds.furnimove import build_furnimove_command
from custom_components.adjustable_bed.furnimove_profiles import (
    FURNIMOVE_PRODUCTION_IDS,
    FURNIMOVE_PROFILES,
    get_furnimove_profile,
    parse_furnimove_profile,
)


def test_all_production_rows_match_frozen_encoder_vectors() -> None:
    assert len(FURNIMOVE_PRODUCTION_IDS) == 87
    assert len({FURNIMOVE_PROFILES[key].actions for key in FURNIMOVE_PRODUCTION_IDS}) == 39
    vectors = [
        [
            key,
            index,
            build_furnimove_command(row.keycode).hex(),
            build_furnimove_command(row.keycode, old=True, dot=True).hex(),
            build_furnimove_command(row.keycode, dot=True).hex(),
        ]
        for key in sorted(FURNIMOVE_PRODUCTION_IDS)
        for index, row in enumerate(FURNIMOVE_PROFILES[key].actions)
    ]
    assert len(vectors) == 1092
    # Independently frozen runtime-command-ledger.json frame_candidates, all rows.
    assert (
        hashlib.sha256(json.dumps(vectors, separators=(",", ":")).encode()).hexdigest()
        == "910ddf3ffaa9bd914c3ecf9b6871b97b2a60d0e281a54d28b07a272847e5552a"
    )
    semantic = [
        [
            key,
            index,
            row.action,
            row.type,
            row.keycode,
            row.duration_ms,
            row.frequency_ms,
            row.intensity,
        ]
        for key in sorted(FURNIMOVE_PRODUCTION_IDS)
        for index, row in enumerate(FURNIMOVE_PROFILES[key].actions)
    ]
    # Frozen raw-table replay also pins timing, type and intensity carry.
    assert (
        hashlib.sha256(json.dumps(semantic, separators=(",", ":")).encode()).hexdigest()
        == "b2d5a1ae05cee7a7ac6330bd4e037771d8497001fad61568a9fd0aaff265df34"
    )
    for key in FURNIMOVE_PRODUCTION_IDS:
        profile = FURNIMOVE_PROFILES[key]
        assert profile.source == "production"
        assert len(profile.object_sha256) == len(profile.button_sha256) == 64


def test_local_tables_and_no_unknown_id_fallback() -> None:
    assert len(FURNIMOVE_PROFILES) == 90
    offline = get_furnimove_profile("00000")
    assert len(offline.actions) == 5
    assert offline.first("DisobeyStandbyTime") is None
    assert offline.first("Flat").keycode == "0x10000000"
    first = get_furnimove_profile("280702")
    alias = get_furnimove_profile("280703")
    assert first.actions is alias.actions
    assert len(first.actions) == 9
    assert first.first("Flat").keycode == "0x08000000"
    for key in ("unknown", "82417 ", "01", "9898989898989898"):
        with pytest.raises(ValueError):
            get_furnimove_profile(key)


def test_generic_parser_first_object_order_duplicates_defaults_and_carried_intensity() -> None:
    buttons = [
        {
            "action": "First custom slot",
            "type": "memory",
            "keycode": "0x00001000",
            "frequency": 999,
        },
        {
            "action": "MassagerHeadPlus",
            "type": "massage-function",
            "keycode": "0x00000800",
            "intensity": "3.8",
        },
        {
            "action": "First custom slot",
            "type": "memory",
            "keycode": "0x00002000",
            "duration": 23.8,
            "frequency": "4",
        },
        {"action": "Quiet Sleep independently", "type": "memory-preset", "keycode": "0x00004000"},
        {"action": "M1Out", "type": "future-category", "keycode": "0x00000010"},
        {"action": "M2In", "type": "actuator", "keycode": "0x00000002"},
    ]
    profile = parse_furnimove_profile("aNonNumericID", [{"PK": "01"}, {"PK": "bad"}], buttons)
    assert profile.handset_id == "aNonNumericID"
    assert profile.brand_id == 1
    assert profile.product_type == "bed"
    assert profile.description is None
    assert profile.actions[0].duration_ms == profile.actions[0].frequency_ms == 0
    assert profile.actions[0].intensity is None
    assert [row.intensity for row in profile.actions[1:]] == [3] * 5
    assert [row.keycode for row in profile.by_type("memory")] == ["0x00001000", "0x00002000"]
    assert profile.first("First custom slot") is profile.actions[0]
    assert profile.actions[2].duration_ms == 23
    assert profile.actions[2].frequency_ms == 4
    assert profile.motor_count == 0  # One actuator row, not highest axis/name.
    assert profile.first("M1Out").type == "future-category"


@pytest.mark.parametrize("pk", ["", "1.0", " 1", "2147483648", None])
def test_parser_rejects_invalid_pk_instead_of_repairing(pk) -> None:
    with pytest.raises(ValueError):
        parse_furnimove_profile("id", [{"PK": pk}], [])


@pytest.mark.parametrize("keycode", ["0400000000", "0x0", "0xGG", "0x0000000000", None])
def test_parser_rejects_unsafe_custom_keycode(keycode) -> None:
    with pytest.raises(ValueError):
        parse_furnimove_profile(
            "id", [{"PK": 1}], [{"action": "Flat", "type": "actuator-init", "keycode": keycode}]
        )


def test_parser_duration_requires_frequency_and_massage_requires_intensity() -> None:
    for button in (
        {"action": "Sync", "type": "utility", "keycode": "0x10000000", "duration": 1000},
        {"action": "MassagerHeadPlus", "type": "massage-function", "keycode": "0x00000800"},
        {
            "action": "DisobeyStandbyTime",
            "type": "utility",
            "keycode": "0x00000000",
            "duration": "",
            "frequency": "",
        },
    ):
        with pytest.raises(ValueError):
            parse_furnimove_profile("id", [{"PK": 1}], [button])


def test_parser_category_and_optional_metadata() -> None:
    profile = parse_furnimove_profile(
        "id",
        [
            {
                "PK": "+8",
                "description": "A chair",
                "type": "chair",
                "last_modified": "2026-09-30T00:00:00",
            }
        ],
        [],
    )
    assert profile.description == "A chair"
    assert profile.product_type == "chair"
    assert profile.last_modified == "2026-09-30T00:00:00"
    assert (
        parse_furnimove_profile("id", [{"PK": 1, "type": "TABLE"}], []).product_type == "undefined"
    )
    with pytest.raises(ValueError):
        parse_furnimove_profile("id", [{"PK": 1, "last_modified": "not-a-date"}], [])
