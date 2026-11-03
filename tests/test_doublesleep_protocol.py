"""Vectors from row107's independently accepted 1.2.24 artifact."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from custom_components.adjustable_bed import doublesleep_protocol as p
from custom_components.adjustable_bed.doublesleep_services import build_request
from custom_components.adjustable_bed.doublesleep_state import BinaryHistory, Notifications, Report

NOW = datetime(2026, 11, 3, 6, 30, 7, tzinfo=timezone(timedelta(hours=1)))
STATIC = json.loads((Path(__file__).parent / "fixtures/doublesleep_commands.json").read_text())


@pytest.mark.parametrize("text", ["NaN", "Infinity"])
def test_json_rejects_nonfinite_or_excessively_nested_input(text):
    from custom_components.adjustable_bed.doublesleep_state import decode_json

    with pytest.raises(ValueError):
        decode_json(text)


def test_json_recursion_error_is_a_recoverable_parser_error():
    from unittest.mock import patch

    from custom_components.adjustable_bed.doublesleep_state import decode_json

    with (
        patch(
            "custom_components.adjustable_bed.doublesleep_state.json.loads",
            side_effect=RecursionError,
        ),
        pytest.raises(ValueError, match="nested too deeply"),
    ):
        decode_json("[]")


@pytest.mark.parametrize("driver", ("p1", "p2", "p3"))
def test_sensor_version_is_an_independent_notification_observer(driver):
    parser = Notifications(driver, 3, p.Cache())
    if driver == "p3":
        # The independent version observer runs before P3's JSON parser rejects
        # this binary frame. Its mutation must survive the parser failure.
        with pytest.raises(ValueError):
            parser.feed(bytes.fromhex("2a00000881020102"), NOW)
    else:
        parser.feed(bytes.fromhex("2a00000881020102"), NOW)
    assert parser.state["sensor_version"] == "1.2"


@pytest.mark.parametrize("row", STATIC, ids=lambda r: f"{r['driver']}-{r['index']}")
def test_static_artifact_commands(row):
    assert p.binary_command(row["driver"], row["index"], (), p.Cache(), NOW).hex() == row[
        "expected"
    ].replace(" ", "")


@pytest.mark.parametrize(
    ("driver", "index", "values", "expected"),
    [
        ("p1", 47, (), "07047e0a0301061e07"),
        ("p2", 47, (), "aa00000301081a0b0302061e0701"),
        ("p1", 49, (6, 30, 2, 9, 128), "07058009061e00010102"),
        ("p2", 49, (6, 30, 2, 9, 128), "aa000003020801020901061e0080"),
        ("p1", 62, (7, 2), "020b070301"),
        ("p1", 62, (2, 3), "020b020601"),
        ("p2", 62, (2, 3, 4, 5), "aa00000701080202030104050000"),
        ("p2", 67, (2, 4, 3), "aa0000070403020403"),
        ("p2", 72, (0, 0, 2026, 11, 3), "2a00000784031a0b03"),
        ("p2", 72, (1, 1, 2026, 11, 3), "2a00000787021a0b"),
        ("p2", 57, (0,), "2a000005810900ffff00002225124b"),
    ],
)
def test_dynamic_artifact_vectors(driver, index, values, expected):
    assert p.binary_command(driver, index, values, p.Cache(), NOW).hex() == expected


def test_relative_cold_and_notification_owned_caches():
    cache = p.Cache()
    assert p.relative(36, cache).hex() == "aa000002010152"  # cold 0 ->3, not4
    assert p.relative(35, cache).hex() == "aa000002010150"
    assert cache.regular["head"] == 0  # no optimistic mutation
    cache.regular["head"] = 1
    assert p.relative(36, cache).hex() == "aa000002010153"
    cache.sonic["time"] = 3
    assert p.relative(85, cache).hex() == "aa0000060b06000357025702"
    cache.sonic["head"] = 2
    assert p.relative(79, cache).hex() == "aa0000060203000108"
    cache.regular["mode"] = 9
    assert p.relative(41, cache).hex() == "aa000002010149"  # decrement, no upper saturation


@pytest.mark.parametrize("mtu", (23, 64, 247, 497, 512))
def test_p3_frames_fit_att_and_one_byte_body_size(mtu):
    writer = p.JsonWriter(sequence=254)
    packets = writer.packets("s_sens", {"L": [1], "R": [2], "ret": 0}, mtu, send=True)
    assert (
        b"".join(frame[14:] for frame in packets)
        == b'{"id":255,"cmd":"s_sens","val":{"L":[1],"R":[2],"ret":0}}'
    )
    for index, frame in enumerate(packets):
        assert len(frame) <= mtu - 3
        assert frame[0] == 2 and frame[1] == index
        assert frame[2] == len(packets) and frame[3] == index
        assert frame[4] == len(frame) - 7
        assert frame[7:12] == bytes.fromhex("1103594459")
        assert int.from_bytes(frame[12:14], "little") == len(frame) - 14


def test_all_p3_commands_and_clock_truncation():
    for index in p.P3_SUPPORTED:
        values = (1, 0, 2026, 11, 3) if index == 72 else (3, 4) if index == 68 else ()
        packets = p.JsonWriter().command(index, values, NOW, 247)
        body = json.loads(b"".join(packet[14:] for packet in packets))
        assert body["id"] == 1
        expected = {
            53: ("q_antiSnore", {}),
            55: ("q_time", {}),
            59: ("q_realtime", {"time": 1}),
            60: ("q_realtime", {"time": 65535}),
            68: ("s_sens", {"L": [3], "R": [4], "ret": 0}),
            69: ("q_sens", {}),
            71: ("q_part", {}),
            73: ("s_init", 0),
            77: ("q_realtime", {"time": 65535}),
            78: ("q_report", {"allow": 1}),
        }
        if index in expected:
            assert (body["cmd"], body["val"]) == expected[index]
        assert packets[0][0] == (2 if index in (47, 68, 73) else 0)
        if index == 47:
            assert body["val"] == {"ts": int(NOW.timestamp()), "utc": 1}
        elif index == 72:
            assert body["val"] == {"part": 2, "type": 1, "y": 2026, "m": 11, "d": 3}
    assert (
        json.loads(
            b"".join(
                x[14:]
                for x in p.JsonWriter().command(
                    47, (), datetime(1969, 12, 31, 23, 59, 59, 999999, tzinfo=UTC), 247
                )
            )
        )["val"]["ts"]
        == 0
    )


@pytest.mark.parametrize(
    ("name", "data", "protocol", "model"),
    [
        ("sleepbt", bytes([1, 2, 3, 4, 5, 6, 134]), "p2", 10135),
        ("sleepbt", bytes([1, 2, 3, 4, 5, 6, 136]), "p2", 10137),
        ("sleepbt", bytes([1, 2, 3, 4, 5, 6, 2]), "p1", 3),
        ("osleepbt-123", b"", "p3", 11135),
        ("osleepbts-456", b"", "p3", 11136),
    ],
)
def test_driver_and_model_selectors(name, data, protocol, model):
    assert p.discover(name, {89: data})
    assert p.select_protocol(name, {89: data}) == protocol
    assert p.select_model(name, {89: data}) == model
    assert not p.discover(name, {90: data})


def test_identity_full_reverse_and_distinct_platform_name():
    assert p.real_mac("sleepbt", {89: bytes.fromhex("010203040506070809")}) == "080706050403"
    assert p.real_mac("OSleepBT-A-B", {89: b""}) == "A"
    assert p.select_protocol("sleepbt", {89: bytes(7)}) == "p1"
    assert p.select_model("osleepbts", {89: bytes(7)}) == 11136
    assert len(p.MODELS) == 10 and 67 not in p.DOUBLE_MODELS


@pytest.mark.parametrize("driver", ("p1", "p2"))
@pytest.mark.parametrize("opcode", (132, 133, 134, 135))
def test_history_daily_monthly_and_retained_completion(driver, opcode):
    parser = BinaryHistory(driver)
    text = b'{"day":"2026-11-03","arrayHR":[75],"extension":7}'
    payload = gzip.compress(text, mtime=0)
    assert (
        parser.feed(bytes([42, 0, 0, 7, opcode, 7, 1]) + len(payload).to_bytes(4, "little")) is None
    )
    assert parser.timer_pending == (driver == "p2")
    assert parser.feed(bytes([42, 0, 0, 7, opcode, 0, 2, 1]) + payload) is None
    result = parser.feed(bytes([42, 0, 0, 7, opcode, 0, 2, 0]) + payload)
    assert result == Report(
        "history" if opcode < 134 else "history_month",
        opcode % 2,
        0,
        json.loads(text) if opcode < 134 else text.decode(),
    )
    assert not parser.timer_pending
    assert parser.feed(bytes([42, 0, 0, 7, opcode, 0, 2, 200])) == result


@pytest.mark.parametrize("opcode", (132, 133, 134, 135))
def test_p2_cold_empty_wrong_index_and_header_then_data(opcode):
    cold = BinaryHistory("p2")
    assert cold.feed(bytes([42, 0, 0, 7, opcode, 0, 2, 9])) == Report("history", 0, 1, {})
    assert cold.index == 0
    cold.feed(bytes([42, 0, 0, 7, opcode, 7, 1, 0, 0, 0, 0]))
    assert cold.feed(bytes([42, 0, 0, 7, opcode, 0, 2, 0])) == Report("history", opcode % 2, 1, {})
    assert not cold.timer_pending
    assert BinaryHistory("p1").feed(bytes([42, 0, 0, 7, opcode, 0, 2, 0])) is None


@pytest.mark.parametrize("value", ([], [1], None, True, 123, "bad"))
def test_binary_daily_type_error_keeps_mutations_and_timeout(value):
    parser = BinaryHistory("p2")
    payload = gzip.compress(json.dumps(value).encode(), mtime=0)
    parser.feed(bytes.fromhex("2a000007840701") + len(payload).to_bytes(4, "little"))
    with pytest.raises(ValueError):
        parser.feed(bytes.fromhex("2a00000784000200") + payload)
    assert parser.index == 1 and bytes(parser.buffer) == payload and parser.timer_pending
    assert parser.timeout() == Report("history", 0, 2, {})


def test_p1_parameter_precedes_massage_and_short_massage():
    parser = Notifications("p1", 3, p.Cache())
    raw = bytes.fromhex("a50b0000580203f50600000000000102030600")
    parser.feed(raw, NOW)
    assert parser.state["privacy"] == 1 and parser.state["anti_mode"] == 2
    assert parser.state["massage_head"] == 4 and parser.state["massage_foot"] == 3
    short = Notifications("p1", 3, p.Cache())
    short.feed(raw[:9], NOW)
    assert "privacy" not in short.state and short.state["massage_time"] == 2
    with pytest.raises(IndexError):
        short.feed(raw[:8], NOW)


def test_p2_mfp_light_partial_mutation_and_regular_sonic_caches():
    parser = Notifications("p2", 10135, p.Cache())
    # Light mode mutation happens before the MFP-local function-list bounds failure.
    raw = bytearray.fromhex("2a000005810e00020307000002")
    parser.feed(bytes(raw), NOW)
    assert "parser_error" in parser.state
    assert parser.cache.light[0] == 2
    raw[8] = 1
    raw[9:11] = bytes([7, 0])
    parser.feed(bytes(raw), NOW)
    assert parser.ui.sonic_ui
    with pytest.raises(IndexError):
        parser.feed(bytes.fromhex("2a000004810602010a"), NOW)
    assert parser.cache.light[:3] == [2, 1, 10]
    raw = bytearray(17)
    raw[:5] = bytes.fromhex("2a00000281")
    raw[6] = 3
    raw[7] = 0x35
    raw[8:10] = bytes.fromhex("5802")
    raw[10] = 6
    raw[11:13] = bytes.fromhex("5802")
    parser.feed(bytes(raw), NOW)
    assert parser.cache.regular == {
        "mode": 3,
        "head": 2,
        "foot": 3,
        "time": 2,
        "running": 1,
    }


def json_notification(command, value):
    payload = json.dumps({"cmd": command, "val": value}, separators=(",", ":")).encode()
    return bytes([0, 0, 1, 0, 0, 0, 0, 17, 3, 89, 68, 89, 0, 0]) + payload


def test_p3_preserves_distinct_sides_and_privacy_histories():
    parser = Notifications("p3", 11135, p.Cache())
    parser.feed(
        json_notification(
            "q_realtime", {"L": [0, -3, 75, 14, 0, 0, 5], "R": [1, 1, 90, 19, 0, 0, 9]}
        ),
        NOW,
    )
    assert parser.state["left_heart_rate"] == 75 and parser.state["right_heart_rate"] == 90
    assert parser.state["left_history"] == [0] * 7 + [1]
    parser.privacy = True
    parser.feed(
        json_notification(
            "q_realtime", {"L": [0, -3, 75, 14, 0, 0, 5], "R": [1, 1, 90, 19, 0, 0, 9]}
        ),
        NOW,
    )
    assert parser.state["left_heart_rate"] == parser.state["right_heart_rate"] == 0
    assert parser.state["left_history"] == parser.state["right_history"] == [0] * 8
    parser.feed(json_notification("q_sens", {"L": [3], "R": [4]}), NOW)
    assert parser.state["left_sensitivity"] == 3 and parser.state["right_sensitivity"] == 4
    parser.feed(json_notification("q_part", 12), NOW)
    assert parser.state["use_side"] == 3
    parser.feed(json_notification("s_init", {"ver": "1.0.2"}), NOW)
    assert parser.state["sensor_version"] == "12"
    report, allow = parser.feed(json_notification("q_report", {"fsize": 23}), NOW)
    assert report is None and allow


def test_legacy_double_unpack_fields_and_calendar():
    parser = Notifications("p1", 3, p.Cache())
    # Shared first3, left4, right4, final5; d7 is intentionally both year and breath_pause.
    record = bytes([166, 48, 0, 75, 14, 6, 1, 80, 15, 3, 2, 126, 10, 3, 6, 30])
    assert parser.legacy_feed(record)
    report = parser.legacy_report()
    left, right = report["left"], report["right"]
    assert isinstance(left, list) and isinstance(right, list)
    left_record, right_record = left[0], right[0]
    assert isinstance(left_record, dict) and isinstance(right_record, dict)
    assert left_record["heart"] == 75 and right_record["heart"] == 80
    assert left_record["breath_pause"] == 126
    assert left_record["local_time"] == "2026-11-03T06:30:00"
    assert isinstance(left_record["time"], int)


@pytest.mark.parametrize(
    "data",
    [
        {"action": "report", "report_side": "left", "report_kind": "day", "date": "2026-02-30"},
        {"action": "alarm", "hour": True, "minute": 0, "days_mask": 0, "alarm_preset": 1},
        {"action": "save_preset", "preset": "flat"},
        {"action": "firmware"},
    ],
)
def test_services_reject_before_writing(data):
    with pytest.raises(ValueError):
        build_request(data)


@pytest.mark.parametrize(
    ("stamp", "expected"),
    [
        ("2026-11-07T07:00:00", 64),  # Saturday before selected time
        ("2026-11-07T09:00:00", 1),  # Saturday -> Sunday
        ("2026-11-08T07:00:00", 1),  # Sunday before selected time
        ("2026-11-08T09:00:00", 2),  # Sunday -> Monday, no byte overflow
    ],
)
def test_alarm_one_shot_uses_proven_sunday_first_day_bits(stamp, expected):
    assert p.alarm_days(datetime.fromisoformat(stamp), 8, 0, []) == expected
    assert p.alarm_days(datetime.fromisoformat(stamp), 8, 0, ["sun", "mon", "sat"]) == 195


def test_daily_and_monthly_consumers_preserve_raw_and_exact_defaults():
    from custom_components.adjustable_bed.doublesleep_state import daily_report, report_records

    value = {"day": "2026-11-03", "arrayHR": [75], "sporadicsleep": '{"nap":1}', "extension": 99}
    parsed = daily_report(value)
    assert parsed["arrayHR"] == [75] and parsed["arrayBR"] == []
    assert parsed["maxHR"] == 0 and parsed["device_id"] == ""
    assert parsed["sporadicsleep"] == {"nap": 1}
    report = Report("history", 1, 0, value)
    original = report.attributes()["data"]
    assert isinstance(original, dict) and original["extension"] == 99
    assert report_records(report) == parsed
    assert report_records(Report("history_month", 1, 0, json.dumps([value]))) == [parsed]
    assert report_records(Report("history_month", 1, 0, "[]")) is None
    with pytest.raises(ValueError, match="integers"):
        daily_report({"arrayHR": ["75"]})
    with pytest.raises(ValueError, match="objects"):
        report_records(Report("history_month", 0, 0, "[1]"))


@pytest.mark.parametrize("monthly", [False, True])
def test_report_null_fields_use_artifact_defaults_for_daily_and_monthly(monthly):
    from custom_components.adjustable_bed.doublesleep_state import daily_report, report_records

    expected = daily_report({})
    nulls = dict.fromkeys(expected)
    report = (
        Report("history_month", 1, 0, json.dumps([nulls]))
        if monthly
        else Report("history", 1, 0, nulls)
    )
    assert report_records(report) == ([expected] if monthly else expected)
    assert report.data == (json.dumps([nulls]) if monthly else nulls)


@pytest.mark.parametrize("invalid", [True, "7", [7], 7.0])
def test_report_scalars_require_artifact_integer_type(invalid):
    from custom_components.adjustable_bed.doublesleep_state import (
        REPORT_SCALARS,
        daily_report,
        report_records,
    )

    for key in REPORT_SCALARS:
        with pytest.raises(ValueError, match="must be an integer"):
            daily_report({key: invalid})
    with pytest.raises(ValueError, match="must be an integer"):
        report_records(Report("history_month", 0, 0, json.dumps([{"inbedTime": invalid}])))


def test_p3_compressed_and_retained_fragment_index_with_single_packet():
    from custom_components.adjustable_bed.doublesleep_state import JsonReader

    reader = JsonReader(side=1)
    payload = gzip.compress(b'{"day":"2026-11-03","arrayHR":[75]}', mtime=0)
    cut = len(payload) // 2
    prefix = bytes([0, 0, 2, 0, 0, 0, 0, 17, 3, 89, 68, 89, 0, 0])
    assert reader.feed(prefix + payload[:cut]) is None and reader.index == 1
    # A single packet clears the buffer, but deliberately retains the index.
    assert reader.feed(json_notification("q_time", {})) == {"cmd": "q_time", "val": {}}
    assert reader.index == 1 and reader.buffer == b""
    reader.index = 0
    assert reader.feed(prefix + payload[:cut]) is None
    final = bytearray(prefix)
    final[3] = 1
    assert reader.feed(bytes(final) + payload[cut:]) == Report(
        "history", 1, 0, {"day": "2026-11-03", "arrayHR": [75]}
    )
    assert reader.index == 0 and bytes(reader.buffer) == payload


def test_a61106_incomplete_side_is_retained_without_invented_fields():
    parser = Notifications("p1", 3, p.Cache())
    parser.feed(bytes.fromhex("a611064b0e060102"), NOW)
    assert parser.state["live_legacy_raw"] == [75, 14, 6, 1, 2]
    assert "left_heart_rate" not in parser.state
    assert "complete" in parser.state["parser_error"]


@pytest.mark.parametrize(
    ("index", "suffix"),
    [
        (31, "02010149"),
        (32, "0201014b"),
        (35, "02010150"),
        (36, "02010152"),
        (37, "02010154"),
        (38, "02010156"),
        (40, "02010142"),
        (41, "02010145"),
        (79, "060203000104"),
        (80, "060203000108"),
        (81, "060203000204"),
        (82, "060203000208"),
        (83, "0603020002"),
        (84, "0603020006"),
        (85, "060b06000357025702"),
        (86, "060b06000307070707"),
    ],
)
def test_every_relative_command_cold_artifact_vector(index, suffix):
    assert p.relative(index, p.Cache()).hex() == "aa0000" + suffix


def test_light_replay_and_independent_slow_observer_survive_mfp_local_failure():
    cache = p.Cache()
    cache.light = [2, 1, 1, 2, 3, 4]
    assert p.binary_command("p2", 58, (), cache, NOW).hex() == "aa0000040106020001020304"
    assert cache.light == [2, 1, 1, 2, 3, 4]
    parser = Notifications("p2", 10135, cache)
    parser.feed(bytes.fromhex("2a000005810e0001000001"), NOW)
    assert parser.ui.slow and parser.ui.pwm == 30 and parser.ui.timer == 10
    assert "parser_error" in parser.state
    assert cache.light[0] == 2
