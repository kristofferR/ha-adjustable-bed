"""Accepted row101 packet, receive, and sequential consumer vectors."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed import casper_base_protocol as bed
from custom_components.adjustable_bed import casper_sleep_protocol as sleep

FIXTURES = Path(__file__).parent / "fixtures/casper_base"


def fixtures(name):
    return json.loads((FIXTURES / name).read_text())


@pytest.mark.parametrize("v", fixtures("builders.json"), ids=lambda v: v["id"])
def test_builders(v):
    inputs = v["inputs"]
    if "opcode" in inputs:
        actual = bed.control(
            inputs["opcode"], single=inputs.get("transport") == 0, side=inputs.get("side", 0)
        )
    elif v.get("builder") == "special":
        name = inputs["name"].removeprefix("query_")
        actual = bed.special(name, single=inputs.get("transport") == 0)
    elif v.get("builder") == "light_seconds":
        actual = bed.light_seconds(inputs["seconds"])
    elif v.get("builder") == "light_rgb":
        actual = bed.light_rgb((inputs["red"], inputs["green"], inputs["blue"]))
    elif v["protocol"] in ("P3", "P4"):
        r = bed.Request(
            "sensor",
            part=inputs.get("part", 1),
            report_type=inputs.get("type", 1),
            year=inputs.get("y", 2026),
            month=inputs.get("m", 1),
            day=inputs.get("d", 1),
        )
        actual = sleep.command(
            "mm" if v["protocol"] == "P3" else "sxb",
            v["action"],
            1,
            r,
            ts=inputs.get("ts", 0),
            zone=inputs.get("zone", 0),
        )
    else:
        advanced = {
            "continuation-0": bed.extra(4, 2, (0, 1, 44)),
            "continuation-1": bed.extra(4, 4, (0, 1)),
            "continuation-2": bed.extra(4, 1, (0, 1, 2, 3)),
            "continuation-3": bed.extra(5, 1, (1, 0, 7, 30, 0x45, 0x81)),
            "continuation-4": bed.extra(5, 1, (0,), operation=0),
            "continuation-5": bed.extra(6, 3, (0,), operation=0),
        }
        if v["id"] in advanced:
            assert advanced[v["id"]].hex() == v["expected_bytes"]
            return
        # Automatic detector frames are covered by the controller lifecycle tests.
        assert "result_sequence" in inputs
        return
    assert actual.hex() == v["expected_bytes"]


def normalize(event):
    if event is None:
        return None
    values = dict(event.values)
    name = event.name
    if name == "motor":
        values["no"] = values.pop("index")
    if name == "massage":
        for i in range(1, 4):
            values["massage" + str(i)] = values.pop("zone" + str(i))
    if name == "desk":
        name = "desk_height" if len(values) == 2 else "desk_bounds"
    if name == "detection_details":
        values["value"] = values.pop("details")
        values["logged_status"] = {
            "not_plugged_in": "notPluggedIn",
            "control_box_malfunction": "controlBoxMalfunction",
        }.get(values["logged_status"], values["logged_status"])
    if name == "sleep_name":
        name = "sleep_name_bytes"
        values["value"] = list(values["value"].encode("latin1"))
    if name == "check":
        values["raw"] = list(bytes.fromhex(values["raw"]))
    if name == "massage_pairs":
        name = "massage_strength_pairs"
    return {"event": name, **values}


@pytest.mark.parametrize("v", fixtures("receive.json"), ids=lambda v: v["id"])
def test_receive(v):
    fn = bed.decode_extra if v["parser"] == "extra" else bed.decode_main
    if v.get("raises") or v.get("error"):
        with pytest.raises((ValueError, IndexError)):
            fn(bytes.fromhex(v["bytes"]))
    else:
        assert normalize(fn(bytes.fromhex(v["bytes"]))) == v["expected"]


@pytest.mark.parametrize("v", fixtures("state.json"), ids=lambda v: v["id"])
def test_sequential_state(v):
    if v["kind"] in ("live", "typed_live"):
        m = sleep.Live("mm" if v["protocol"] == "P3" else "sxb")
        if "prior" in v:
            m.state = {s: copy.deepcopy(v["prior"][s]) for s in ("L", "R")}
            m.valid = v["prior"]["valid"].copy()
        snapshots = []
        error = False
        for update in v["updates"]:
            try:
                m.feed(update)
            except ValueError, IndexError:
                error = True
            snapshots.append({**copy.deepcopy(m.state), "valid": m.valid.copy()})
            if error:
                break
        assert snapshots == v["expected"]["states"]
        assert error == (v["expected"]["error"] is not None)
    elif v["kind"] == "init":
        if v["expected"]["error"] is not None:
            with pytest.raises(ValueError):
                sleep.decode_bean("sxb_init", v["input"])
        else:
            assert sleep.decode_bean("sxb_init", v["input"]) == v["expected"]["bean"]
    else:
        if v["expected"]["error"] is not None:
            with pytest.raises(ValueError):
                sleep.nullable(v["input"], "num", "num", required=True)
                sleep.numeric(v["input"])
        else:
            assert sleep.numeric(v["input"]) == v["expected"]["result"]


def test_framing_and_malformed_cleanup():
    p = bytes.fromhex("6e200c01020300012c022af9")
    receiver = bed.MainReceive()
    assert receiver.feed(p[:4]) == []
    assert receiver.feed(p[4:]) == [p]
    assert receiver.feed(p[:-1] + b"\0") == []
    with pytest.raises(ValueError):
        receiver.feed(bytes.fromhex("6e2000"))
    assert receiver.feed(p) == [p]
    # Ordinary checksum is deliberately not enforced by the artifact.
    assert bed.decode_main(bytes.fromhex("6e90352a00")).name == "motor"


@pytest.mark.parametrize(
    "packet",
    [bytes.fromhex("6e90b06e00"), bytes.fromhex("6e90b0c06e")]
    + [
        packet[:index] + b"\x6e" + packet[index + 1 :]
        for packet in (
            bytes.fromhex("6e900000062500"),
            bytes.fromhex("6e00000102030405060708090a0b0c00"),
        )
        for index in range(2, len(packet))
    ],
)
def test_ordinary_marker_bytes_preserve_supported_notification_lengths(packet):
    receiver = bed.MainReceive()
    assert receiver.feed(packet) == [packet]
    assert bed.decode_main(packet) is not None
    assert not receiver.pending


@pytest.mark.parametrize("split", range(1, 5))
def test_ordinary_fragment_and_coalesced_boundaries(split):
    first = bytes.fromhex("6e90b0c06e")
    second = bytes.fromhex("6e90352a00")
    receiver = bed.MainReceive()
    assert receiver.feed(first[:split]) == []
    assert receiver.feed(first[split:] + second) == [first, second]
    short_desk = bytes.fromhex("6e900000062500")
    long_desk = bytes.fromhex("6e00000102030405060708090a0b0c00")
    assert receiver.feed(short_desk + second) == [short_desk, second]
    assert receiver.feed(long_desk + second) == [long_desk, second]
    with pytest.raises(ValueError, match="ordinary frame boundary"):
        receiver.feed(b"\x6e" + bytes(16))
    assert receiver.feed(second) == [second]


@pytest.mark.parametrize("kind", ["mm", "sxb"])
def test_full_report_typed_shapes(kind):
    day = {
        "day": "2026-11-03",
        "score": 80.75,
        "heart_beat_avg": 65.25,
        "breath_avg": 15.75,
        "awake": {"value": 10.5, "percentage": 2.5},
        "deep": {"value": 30, "percentage": 40},
        "light": {"value": 35, "percentage": 45},
        "rem": {"value": 15, "percentage": 15},
        "time_start": 123.5,
        "time_end": 456.5,
        "report_state": "ready",
    }
    if kind == "mm":
        day.update(
            heart_beat={"num": [61.5, 62], "time": [1.9, 2]},
            breath={"num": [15.9], "time": [1.9]},
            body_move=[{"time": 1.9, "value": 2.9}],
            body_revolve=[{"time": 3, "value": 4}],
            snore=[{"time": 5, "value": 6}],
            snore_count=[{"time": 7, "value": 8}],
            sleep_data=[{"start": 1.9, "end": 2.9, "status": 3.9}],
            sporadicsleep=[{"start": 1.9, "end": 2.9, "minute": 3.9}],
        )
    else:
        day.update(
            algorithmVersion="v1",
            everFellAsleep=1.5,
            sleepEfficiency=85.5,
            sleep_onset_latency=7.5,
            sleep_duration=300.5,
            micro_awake={"value": 3.5, "percentage": 1.25},
            outbed={"value": 10.5, "percentage": 2.5},
            heart_beat={"num": [61.5, 62], "time": [1.9, 2]},
            breath={"num": [15.9], "time": [1.9]},
            body_move={"time": [1.9], "value": [2.9]},
            snore={"time": [3.9], "value": [4.9]},
            sporadicsleep={"start": [1.9], "end": [2.9], "minute": [3.9]},
            sleep_data=[{"start": 1.9, "end": 2.9, "status": 3.9}],
        )
    decoded = sleep.decode_bean(kind + "_day", day)
    assert decoded["score"] == (80 if kind == "mm" else 80.75)
    assert sleep.mapping(decoded["awake"])["value"] == (10 if kind == "mm" else 10.5)
    assert sleep.mapping(decoded["heart_beat"])["num"] == ([61, 62] if kind == "mm" else [61.5, 62])
    assert decoded["sporadicsleep"] == (
        [{"start": 1.9, "end": 2.9, "minute": 3.9}]
        if kind == "mm"
        else {"start": [1.9], "end": [2.9], "minute": [3.9]}
    )
    assert decoded["sleep_data"] == [
        {
            "start": 1 if kind == "mm" else 1.9,
            "end": 2 if kind == "mm" else 2.9,
            "status": 3 if kind == "mm" else 3.9,
        }
    ]
    month = sleep.decode_bean(kind + "_month", day)
    assert month["day"] == "2026-11-03"
    assert month["breath_avg"] == (15 if kind == "mm" else 15.75)
    for invalid in (
        {"awake": {"value": True}},
        {"day": 123},
        {"heart_beat": {"num": ["61"]}},
        {"sleep_data": [{"status": "1"}]},
    ):
        with pytest.raises(ValueError):
            sleep.decode_bean(kind + "_day", invalid)
