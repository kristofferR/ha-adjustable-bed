"""Accepted Good Vibe Sleep 2.0.1 independent artifact vectors."""

import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.goodvibe_catalog import ACTIONS
from custom_components.adjustable_bed.goodvibe_discovery import name_product
from custom_components.adjustable_bed.goodvibe_receive import common, extended
from custom_components.adjustable_bed.goodvibe_schemas import SCHEMAS, parse_schema
from custom_components.adjustable_bed.goodvibe_sleep import Realtime

FIXTURES = Path(__file__).parent / "fixtures/goodvibe"


def fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def test_all_current_action_byte_alternatives():
    seen = set()
    for key, side, legacy, long, expected in fixture("actions"):
        assert ACTIONS[key].packet(side, legacy, long).hex() == expected, (key, side, legacy, long)
        seen.add(key)
    assert seen == set(ACTIONS)


def test_binary_leaf_vectors():
    for frame, expected in fixture("notifications"):
        assert json.loads(json.dumps(extended(frame))) == expected, frame
    for frame, expected in fixture("common"):
        assert json.loads(json.dumps(common(frame))) == expected, frame


def test_binary_bounds_are_explicit():
    for frame, expected in fixture("boundaries"):
        if isinstance(expected, dict) and "error" in expected:
            with pytest.raises((ValueError, IndexError, NotImplementedError)):
                extended(frame)
        else:
            assert json.loads(json.dumps(extended(frame))) == expected, frame


def test_all_62_json_constructors_accept_their_valid_artifact_fixtures():
    seen = set()
    for address, value in fixture("schemas"):
        result = parse_schema(address, value)
        assert result == value, address
        assert set(result) == {field.key for field in SCHEMAS[address]}
        seen.add(address)
    assert seen == set(SCHEMAS)


def test_realtime_consumers_match_artifact_page_state():
    for protocol, values, expected in fixture("realtime"):
        live = Realtime()
        live.accept(
            2 if protocol == "sleep-type1" else 3,
            "-".join(map(str, values)) if protocol == "sleep-type1" else values,
        )
        fields = (
            ("0x27", "0x2b", "0x2f", "0x33", "0x37", "0x3b")
            if protocol == "sleep-type1"
            else ("0x33", "0x37", "0x3b", "0x3f", "0x43", "0x47")
        )
        actual = (
            live.heart,
            live.respiration,
            live.occupancy,
            live.movement,
            live.snore,
            live.valid,
        )
        assert dict(zip(fields, actual, strict=True)) == {k: expected[k] for k in fields}, values


def test_all_advertisement_alias_vectors():
    for name, russian, expected in fixture("names"):
        if isinstance(expected, dict):
            with pytest.raises(ValueError):
                name_product(name, russian=russian)
        else:
            assert name_product(name, russian=russian) == expected


def test_all_product_current_getter_contracts():
    from dataclasses import asdict

    from custom_components.adjustable_bed.goodvibe_catalog import PRODUCTS

    seen = set()
    for key, expected in fixture("products"):
        assert json.loads(json.dumps(asdict(PRODUCTS[key]))) == expected, key
        seen.add(key)
    assert seen == set(PRODUCTS)


def test_dedicated_builders_and_independent_time_vectors():
    import math
    from datetime import datetime, timedelta, timezone

    from custom_components.adjustable_bed import goodvibe_protocol as p

    for row in fixture("advanced"):
        address, args = row["function"], row["args"]
        if address == "0x806ebc":
            actual = p.light_duration(args[0])
        elif address == "0x808980":
            actual = p.color(*(math.floor(x * 255 + 0.5) for x in args[0]))
        elif address == "0x7fb7f4":
            actual = p.clock(args[0], args[1])[1]
        elif address == "0x7fb948":
            actual = p.clock(args[0], 0)[0]
        elif address == "0x80eac0":
            actual = p.snore_config(args[0] == 65569, args[1])
        elif address == "0x80f84c":
            actual = p.snore_switch(args[0] == 65569)
        else:
            actual = p.QUERIES[
                {
                    "0x83bc4c": "snore_config",
                    "0x83be14": "snore_switch",
                    "0x74221c": "alarms",
                    "0x73e830": "sleep_name",
                }[address]
            ]
        assert list(actual) == row["expected"], address
    for row in fixture("time_sync"):
        now = datetime.fromtimestamp(
            row["unix_seconds"], timezone(timedelta(hours=row["utc_hours"]))
        )
        assert [list(frame) for frame in p.sync_time(now)] == row["frames"]
    for row in fixture("alarms"):
        values = row["input"]
        if row["action"].startswith("delete"):
            actual = p.delete_alarm(values["number"])
        else:
            actual = p.repeat_alarm(
                values["number"],
                values["hour"],
                values["minute"],
                values["selected_mode_opcode"],
                values["repeat_enable_mask"],
            )
        assert list(actual) == row["expected_bytes"]


def test_json_required_nested_maps_and_wrong_scalar_casts_are_rejected():
    from copy import deepcopy

    values = dict(fixture("schemas"))
    for address, fields in SCHEMAS.items():
        for field in fields:
            if field.cast.startswith("Map") and not field.cast.endswith("?"):
                invalid = deepcopy(values[address])
                invalid[field.key] = None
                with pytest.raises(ValueError):
                    parse_schema(address, invalid)
            if field.cast.removesuffix("?") in ("num", "int", "String", "bool"):
                invalid = deepcopy(values[address])
                invalid[field.key] = []
                with pytest.raises(ValueError):
                    parse_schema(address, invalid)
