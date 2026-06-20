"""Unit tests for the paired-bed (Dual Bed 4.0) data-model helpers."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_ADDRESS

from custom_components.adjustable_bed.const import (
    CONF_PAIR_CHILDREN,
    CONF_PAIR_ID,
    CONF_PAIR_MEMBER_ADDRESSES,
    CONF_SIDE,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.pairing import (
    build_pair_entry_data,
    get_child,
    is_paired,
    iter_children,
    make_pair_id,
    pair_member_addresses,
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
        assert make_pair_id([LEFT_ADDR, RIGHT_ADDR]) == make_pair_id(
            [RIGHT_ADDR, LEFT_ADDR]
        )

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
