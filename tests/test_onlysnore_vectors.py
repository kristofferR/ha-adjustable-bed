"""Production-code proof against copied frozen literals, never analyst code."""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pytest

from custom_components.adjustable_bed.codec import onlysnore as codec
from custom_components.adjustable_bed.profiles.onlysnore import PROFILE

FIXTURES = Path(__file__).parent / "fixtures" / "onlysnore"
COMMANDS = json.loads((FIXTURES / "commands.json").read_text())
PARSERS = json.loads((FIXTURES / "parsers.json").read_text())
ALARMS = json.loads((FIXTURES / "alarms.json").read_text())


@pytest.mark.parametrize("row", COMMANDS, ids=lambda row: row["id"])
def test_commands(row):
    args = row["inputs"]
    match row["kind"]:
        case "control":
            frame = PROFILE.frames[row["id"]]
        case "query":
            frame = codec.query(args["opcode"])
        case "setting":
            frame = codec.setting(**args)
        case "intervention":
            frame = codec.intervention(**args)
        case "intervention_stop":
            frame = codec.INTERVENTION_STOP
        case "clock":
            frame = codec.clock(datetime.fromisoformat(args["datetime"]))
        case "alarm":
            frame = codec.single_alarm(**args)
        case "alarm_close":
            frame = codec.CLOSE_SINGLE
        case "alarm3":
            frame = codec.triple_alarm(
                **{("opened" if k == "open" else k): v for k, v in args.items()}
            )
        case _:
            pytest.fail(row["kind"])
    assert frame == bytes.fromhex(row["expected_bytes"])


@pytest.mark.parametrize("row", ALARMS, ids=lambda row: row["id"])
def test_alarm_preprocessing(row):
    args = row["inputs"]
    model = codec.AlarmModel(
        **{("opened" if k == "open" else k): v for k, v in args["model"].items()}
    )
    now = datetime.fromisoformat(args["now_local"])
    frame, week = (
        codec.open_single(model, now)
        if row["route"] == "single"
        else codec.set_triple(model, now, now)
    )
    assert frame == bytes.fromhex(row["expected_bytes"])
    assert week == row["expected_week_before_octet_mask"]
    assert model.week == row["expected_model_week"]


@pytest.mark.parametrize("row", PARSERS[:6], ids=lambda row: row["id"])
def test_bed_parsers(row):
    data = bytes.fromhex(row["input_hex"])
    if row["parser"] == "manufacturer":
        mac, model = codec.manufacturer(data)
        assert {"mac": mac, "model": model} == row["expected"]
    else:
        result = codec.parse(data)
        assert isinstance(result, codec.Status | codec.Alarm)
        parsed = asdict(result)
        if isinstance(result, codec.Alarm):
            parsed["open"] = parsed.pop("opened")
        assert parsed == row["expected"]


def test_excluded_sensing_vectors_are_retained():
    # These raw sensing/history records have no BED actuator state consumer.
    assert [row["id"] for row in PARSERS[6:]] == [
        "history_date",
        "history_two_records",
        "history_short_rejected",
    ]
    assert all(codec.parse(bytes.fromhex(row["input_hex"])) is None for row in PARSERS[6:])


def test_octet_mask_and_independent_triple_clock():
    assert codec.setting(-1, 257) == b"\x01\xff\x01"
    model = codec.AlarmModel(0, 7, 30)
    _, week = codec.set_triple(model, datetime(2026, 11, 21, 23, 59), datetime(2026, 11, 22))
    assert week == 256 and model.week == 0
