"""Unit tests for the paired-bed (Dual Bed 4.0) data-model helpers."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_ADDRESS

from custom_components.adjustable_bed.const import (
    BED_TYPE_OKIN_CB24,
    BED_TYPE_RONDURE,
    BED_TYPE_SBI,
    BED_TYPE_SLEEP_NUMBER,
    CB24_BED_SELECTION_A,
    CB24_BED_SELECTION_B,
    CONF_BED_TYPE,
    CONF_CB24_BED_SELECTION,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_ID,
    CONF_PAIR_MEMBER_ADDRESSES,
    CONF_PAIR_MODE,
    CONF_PROTOCOL_VARIANT,
    CONF_SIDE,
    OKIN_CB24_VARIANT_NEW,
    PAIR_MODE_SINGLE_ADDRESS,
    RONDURE_VARIANT_SIDE_A,
    RONDURE_VARIANT_SIDE_B,
    SBI_VARIANT_SIDE_A,
    SBI_VARIANT_SIDE_B,
    SIDE_LEFT,
    SIDE_RIGHT,
    SLEEP_NUMBER_VARIANT_LEFT,
    SLEEP_NUMBER_VARIANT_RIGHT,
)
from custom_components.adjustable_bed.pairing import (
    build_pair_entry_data,
    build_single_address_pair_entry_data,
    get_child,
    is_paired,
    iter_children,
    make_pair_id,
    octo_snapshot_from_descriptor,
    pair_layout_from_descriptor,
    pair_member_addresses,
    single_data_from_child,
    single_options_from_child,
    supports_single_address_pairing,
    with_updated_child,
)

LEFT_ADDR = "AA:BB:CC:DD:EE:01"
RIGHT_ADDR = "AA:BB:CC:DD:EE:02"


def _paired_data() -> dict:
    """A minimal separate-address paired entry.data."""
    return {
        CONF_PAIR_ID: make_pair_id([LEFT_ADDR, RIGHT_ADDR]),
        CONF_PAIR_MEMBER_ADDRESSES: [LEFT_ADDR, RIGHT_ADDR],
        CONF_PAIR_CHILDREN: [
            {CONF_SIDE: SIDE_LEFT, CONF_ADDRESS: LEFT_ADDR, "octo_pin": "1111"},
            {CONF_SIDE: SIDE_RIGHT, CONF_ADDRESS: RIGHT_ADDR, "octo_pin": "2222"},
        ],
    }


class TestMakePairId:
    def test_deterministic_and_order_independent(self):
        assert make_pair_id([LEFT_ADDR, RIGHT_ADDR]) == make_pair_id([RIGHT_ADDR, LEFT_ADDR])

    def test_case_insensitive(self):
        assert make_pair_id([LEFT_ADDR.lower(), RIGHT_ADDR]) == make_pair_id(
            [LEFT_ADDR, RIGHT_ADDR]
        )

    def test_format(self):
        pair_id = make_pair_id([LEFT_ADDR, RIGHT_ADDR])
        assert pair_id.startswith("pair_")
        assert len(pair_id) == len("pair_") + 12

    def test_distinct_inputs_differ(self):
        assert make_pair_id([LEFT_ADDR, RIGHT_ADDR]) != make_pair_id(
            [LEFT_ADDR, "AA:BB:CC:DD:EE:03"]
        )

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            make_pair_id([])
        with pytest.raises(ValueError):
            make_pair_id(["", None])  # type: ignore[list-item]


class TestIsPaired:
    def test_paired(self):
        assert is_paired(_paired_data()) is True

    def test_single_bed(self):
        assert is_paired({CONF_ADDRESS: LEFT_ADDR}) is False

    def test_empty_pair_id_is_not_paired(self):
        assert is_paired({CONF_PAIR_ID: ""}) is False


class TestChildren:
    def test_iter_children(self):
        children = iter_children(_paired_data())
        assert [c[CONF_SIDE] for c in children] == [SIDE_LEFT, SIDE_RIGHT]

    def test_iter_children_single_bed(self):
        assert iter_children({CONF_ADDRESS: LEFT_ADDR}) == []

    def test_get_child(self):
        assert get_child(_paired_data(), SIDE_LEFT)[CONF_ADDRESS] == LEFT_ADDR
        assert get_child(_paired_data(), SIDE_RIGHT)[CONF_ADDRESS] == RIGHT_ADDR

    def test_get_child_missing(self):
        assert get_child(_paired_data(), "nonexistent") is None


class TestPairMemberAddresses:
    def test_from_flat_list(self):
        assert pair_member_addresses(_paired_data()) == [LEFT_ADDR, RIGHT_ADDR]

    def test_derived_from_children_when_no_flat_list(self):
        data = _paired_data()
        del data[CONF_PAIR_MEMBER_ADDRESSES]
        assert pair_member_addresses(data) == [LEFT_ADDR, RIGHT_ADDR]

    def test_normalized_and_deduplicated(self):
        data = {
            CONF_PAIR_MEMBER_ADDRESSES: [LEFT_ADDR.lower(), LEFT_ADDR],
            CONF_PAIR_CHILDREN: [{CONF_SIDE: SIDE_LEFT, CONF_ADDRESS: LEFT_ADDR}],
        }
        assert pair_member_addresses(data) == [LEFT_ADDR]

    def test_single_bed_has_no_members(self):
        assert pair_member_addresses({CONF_ADDRESS: LEFT_ADDR}) == []


class TestBuildPairEntryData:
    def test_builds_separate_address_pair(self):
        left = {
            "address": LEFT_ADDR,
            "name": "Seng",
            "bed_type": "linak",
            "motor_count": 2,
            "ble_bond_established": True,
        }
        right = {"address": RIGHT_ADDR, "name": "Bed 4587", "bed_type": "linak", "motor_count": 2}

        data = build_pair_entry_data(left, right, name="Master Bed")

        assert is_paired(data)
        assert data[CONF_PAIR_ID] == make_pair_id([LEFT_ADDR, RIGHT_ADDR])
        assert data["pair_mode"] == "separate_address"
        assert data["bed_type"] == "linak"
        assert data["name"] == "Master Bed"
        assert pair_member_addresses(data) == [LEFT_ADDR, RIGHT_ADDR]
        # children carry their full single-bed config + a side
        left_child = get_child(data, SIDE_LEFT)
        assert left_child[CONF_ADDRESS] == LEFT_ADDR
        assert left_child[CONF_SIDE] == SIDE_LEFT
        assert left_child["name"] == "Seng"
        assert left_child["ble_bond_established"] is True
        assert get_child(data, SIDE_RIGHT)[CONF_ADDRESS] == RIGHT_ADDR

    def test_descriptor_excludes_pair_only_keys(self):
        # If a source somehow carries pair keys, they must not leak into a child.
        left = {"address": LEFT_ADDR, "bed_type": "linak", CONF_PAIR_ID: "stale"}
        right = {"address": RIGHT_ADDR, "bed_type": "linak"}
        data = build_pair_entry_data(left, right, name="x")
        assert CONF_PAIR_ID not in get_child(data, SIDE_LEFT)

    def test_provenance_restores_exact_data_options_and_layout(self):
        original_data = {
            "address": LEFT_ADDR,
            "name": "Left",
            "bed_type": "legacy-original",
        }
        original_options = {"motor_count": 3, "back_max_angle": 55.0}
        layout = {"motor_count": 3, "motor_keys": ["back", "head", "legs"]}
        data = build_pair_entry_data(
            {**original_data, **original_options, "bed_type": "resolved-type"},
            {"address": RIGHT_ADDR, "bed_type": "resolved-type"},
            name="Master",
            left_layout_snapshot=layout,
            left_origin_data=original_data,
            left_origin_options=original_options,
        )
        child = get_child(data, SIDE_LEFT)
        assert single_data_from_child(child) == original_data
        assert single_options_from_child(child) == original_options
        assert pair_layout_from_descriptor(child) == layout


class TestBuildSingleAddressPairEntryData:
    @pytest.mark.parametrize(
        ("bed_type", "left_key", "left_value", "right_value"),
        [
            (
                BED_TYPE_SBI,
                CONF_PROTOCOL_VARIANT,
                SBI_VARIANT_SIDE_A,
                SBI_VARIANT_SIDE_B,
            ),
            (
                BED_TYPE_RONDURE,
                CONF_PROTOCOL_VARIANT,
                RONDURE_VARIANT_SIDE_A,
                RONDURE_VARIANT_SIDE_B,
            ),
            (
                BED_TYPE_OKIN_CB24,
                CONF_CB24_BED_SELECTION,
                CB24_BED_SELECTION_A,
                CB24_BED_SELECTION_B,
            ),
            (
                BED_TYPE_SLEEP_NUMBER,
                CONF_PROTOCOL_VARIANT,
                SLEEP_NUMBER_VARIANT_LEFT,
                SLEEP_NUMBER_VARIANT_RIGHT,
            ),
        ],
    )
    def test_builds_two_logical_sides_on_one_address(
        self, bed_type, left_key, left_value, right_value
    ):
        original = {
            CONF_ADDRESS: LEFT_ADDR,
            CONF_BED_TYPE: bed_type,
            "name": "One physical bed",
        }
        data = build_single_address_pair_entry_data(
            original, name="Master", origin_options={"motor_count": 2}
        )

        assert data[CONF_PAIR_MODE] == PAIR_MODE_SINGLE_ADDRESS
        assert pair_member_addresses(data) == [LEFT_ADDR]
        assert get_child(data, SIDE_LEFT)[CONF_ADDRESS] == LEFT_ADDR
        assert get_child(data, SIDE_RIGHT)[CONF_ADDRESS] == LEFT_ADDR
        assert get_child(data, SIDE_LEFT)[left_key] == left_value
        assert get_child(data, SIDE_RIGHT)[left_key] == right_value
        assert single_data_from_child(get_child(data, SIDE_LEFT)) == original

    def test_cbnew_is_refused(self):
        assert not supports_single_address_pairing(
            BED_TYPE_OKIN_CB24, OKIN_CB24_VARIANT_NEW
        )
        with pytest.raises(ValueError, match="does not support"):
            build_single_address_pair_entry_data(
                {
                    CONF_ADDRESS: LEFT_ADDR,
                    CONF_BED_TYPE: BED_TYPE_OKIN_CB24,
                    CONF_PROTOCOL_VARIANT: OKIN_CB24_VARIANT_NEW,
                },
                name="Unsupported",
            )


class TestWithUpdatedChild:
    def test_patches_correct_side_only(self):
        data = _paired_data()
        updated = with_updated_child(data, SIDE_LEFT, {"octo_pin": "9999"})

        assert get_child(updated, SIDE_LEFT)["octo_pin"] == "9999"
        # Right side untouched.
        assert get_child(updated, SIDE_RIGHT)["octo_pin"] == "2222"

    def test_does_not_mutate_input(self):
        data = _paired_data()
        with_updated_child(data, SIDE_LEFT, {"octo_pin": "9999"})
        # Original left child unchanged.
        assert data[CONF_PAIR_CHILDREN][0]["octo_pin"] == "1111"

    def test_adds_new_key(self):
        updated = with_updated_child(_paired_data(), SIDE_RIGHT, {"bed_type": "octo"})
        assert get_child(updated, SIDE_RIGHT)["bed_type"] == "octo"

    def test_unknown_side_raises(self):
        with pytest.raises(ValueError):
            with_updated_child(_paired_data(), "middle", {"x": 1})

    def test_non_paired_raises(self):
        with pytest.raises(ValueError):
            with_updated_child({CONF_ADDRESS: LEFT_ADDR}, SIDE_LEFT, {"x": 1})


class TestOctoSnapshotPlumbing:
    """Phase 2.5 C3 (commit 1): per-side Octo capability snapshots round-trip
    through the child descriptor's capabilities['octo']."""

    def test_snapshot_stored_and_read_per_side(self):
        snap = {"has_lights": True, "has_rgbwi": True, "memory_count": 4}
        data = build_pair_entry_data(
            {CONF_ADDRESS: "AA:BB:CC:DD:EE:01", "bed_type": "octo"},
            {CONF_ADDRESS: "AA:BB:CC:DD:EE:02", "bed_type": "octo"},
            name="Master",
            left_octo_snapshot=snap,
        )
        children = data["pair_children"]
        # Left carries the snapshot; right (no snapshot passed) has none.
        assert octo_snapshot_from_descriptor(children[0]) == snap
        assert octo_snapshot_from_descriptor(children[1]) is None

    def test_snapshot_none_for_old_or_empty_descriptors(self):
        assert octo_snapshot_from_descriptor(None) is None
        assert octo_snapshot_from_descriptor({}) is None
        assert octo_snapshot_from_descriptor({"capabilities": {}}) is None
        assert octo_snapshot_from_descriptor({"capabilities": {"octo": {}}}) == {}
