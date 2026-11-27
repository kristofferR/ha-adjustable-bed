"""Frozen unit140 literals, compared against existing codecs before profile work."""

import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.codec import keeson, okin_nframe

VECTORS = json.loads((Path(__file__).parent / "fixtures/meisemobell/vectors.json").read_text())


@pytest.mark.parametrize(
    "row", [row for row in VECTORS if "parser" not in row["id"]], ids=lambda row: row["id"]
)
def test_existing_codec_reproduces_frozen_literal(row):
    literal = bytes.fromhex(row["expected_bytes"])
    if row["protocol"] == "P1":
        if literal[:3] == b"\xe6\xfe\x16":
            actual = keeson.frame(int.from_bytes(literal[3:7], "little"), header=0xE6, side=0)
        elif literal[:3] == b"\xed\x80\x03":
            actual = keeson.alarm_table(keeson.ALARM_WEEKLY, literal[3:11])
        else:
            actual = keeson.clock_fields(literal[3:9])
    elif literal[:2] == b"\x05\x02":
        actual = okin_nframe.frame40(int.from_bytes(literal[2:6], "big"))
    else:
        actual = okin_nframe.record(literal[1], literal[2:])
    assert actual == literal


ALIASES = {
    "stop": "stop",
    "lighting": "light",
    "headUp": "head_up",
    "headDown": "head_down",
    "footUp": "foot_up",
    "footDown": "foot_down",
    "memoryAntiSnore": "anti_snore",
    "memory1M5": "memory_1",
    "memory2M6": "memory_2",
    "memoryTvpc": "tv",
    "memoryZero": "zero_g",
    "memoryFlat": "flat",
}


@pytest.mark.parametrize("row", VECTORS, ids=lambda row: row["id"])
def test_app_profile_matches_frozen_literal(row):
    from datetime import datetime

    from custom_components.adjustable_bed.profiles import meisemobell as p

    route = "15_22_15a" if row["protocol"] == "P1" else "24_xx_xx"
    literal = bytes.fromhex(row["expected_bytes"])
    args = row["inputs"]
    if row["action"] in ALIASES:
        assert p.control(route, ALIASES[row["action"]]) == literal
    elif row["id"].endswith("clock"):
        assert (
            p.clock(route, datetime(**{k: v for k, v in args.items() if k != "weekday"})) == literal
        )
    elif row["id"] in ("P1-alarm-dynamic", "P1-disable-alarms"):
        assert (
            p.alarm_pair(
                *(
                    p.Alarm(
                        args[key][0], args[key][1], args[key][2], args[key][3], args[key][2] != 0
                    )
                    for key in ("first", "second")
                )
            )
            == literal
        )
    elif row["id"] == "P2-alarm-dynamic":
        assert (
            p.alarm_slot(
                args["slot"] + 1,
                p.Alarm(args["hour"], args["minute"], args["week"], args["kind"], True),
            )
            == literal
        )
    else:
        reports = p.parse_alarms(route, literal)
        if route == "15_22_15a":
            assert [
                (a.hour, a.minute, a.week, a.kind, int(a.enabled), slot - 1) for slot, a in reports
            ] == [tuple(row["expected_state"][key]) for key in ("first", "second")]
        else:
            assert reports == ((1, p.Alarm(6, 30, 130, 5, True)),)
