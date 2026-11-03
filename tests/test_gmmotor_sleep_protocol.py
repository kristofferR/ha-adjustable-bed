"""GM Control 4.6.6 MM/SXB framing and live display source vectors."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.adjustable_bed.gmmotor_protocol import MalformedNotification
from custom_components.adjustable_bed.gmmotor_sleep_protocol import (
    LiveState,
    ReceiveBuffer,
    Requests,
    frame,
    new_day_layout,
    normal_live,
    response_command,
    sxb_live,
)


def test_frame_header_and_empty_payload() -> None:
    assert frame(b"{}", 7) == bytes.fromhex("00070100090000110343554402007b7d")
    payload = b"x" * 257
    assert frame(payload, 511, total=258, sequence=256)[:14] == bytes.fromhex(
        "00ff020008000011034355440101"
    )
    assert frame(b"", 7) == b""


def test_requests_preserve_nulls_order_and_mode_quirks() -> None:
    normal, sxb = Requests(sxb=False), Requests(sxb=True)
    normal.next_id = sxb.next_id = 7
    assert normal.build("q_part").packet == bytes.fromhex(
        "0007010029000011034355442200"
        "7b226964223a372c22636d64223a22735f70617274222c2276616c223a6e756c6c7d"
    )
    assert json.loads(sxb.build("q_part").packet[14:]) == {"id": 7, "cmd": "q_part", "val": None}
    # An empty normal selector still consumes its counter slot.
    assert normal.build("q_time").packet == b""
    assert normal.build("q_realtime").request_id == 9
    normal.next_id = 254
    assert normal.build("q_part").request_id == 254
    assert normal.build("q_part").request_id == 1


def test_report_parameters_are_distinct_and_allow_shapes_differ() -> None:
    normal, sxb = Requests(sxb=False), Requests(sxb=True)
    args = {"part": 1, "report_type": 2, "year": 2026, "month": 11, "day": 3}
    assert json.loads(normal.build("q_report_allow", **args).packet[14:]) == {
        "id": 1,
        "cmd": "q_report",
        "val": {"part": 1, "type": 2, "y": 2026, "m": 11, "d": 3, "allow": 1},
    }
    assert json.loads(sxb.build("q_report_allow", **args).packet[14:]) == {
        "id": 1,
        "cmd": "q_report",
        "val": {"allow": 1},
    }


def test_clock_modes_and_utf8_are_not_interchanged() -> None:
    now = datetime.fromtimestamp(1700000000, timezone(timedelta(hours=5, minutes=30)))
    assert json.loads(Requests(sxb=True).build("s_time", now=now).packet[14:])["val"] == {
        "ts": 1700000000,
        "utc": 5,
    }
    packet = Requests(sxb=False).build("s_time", now=now, zone="Øst").packet
    assert b"\xc3\x98" in packet
    assert json.loads(packet[14:])["val"] == {"ts": 1700000000, "tz": "Øst"}


def test_ordinary_receive_uses_low_length_and_preserves_overshoot() -> None:
    buffer = ReceiveBuffer(sxb=True)
    buffer.start("q_part")
    packet = frame(b"a" * 257, 7)
    assert buffer.feed(packet[:20]) == b"aaaaaa"
    assert not buffer.pending
    # The high length byte is ignored by the app, even when the whole packet arrives.
    assert buffer.feed(packet) == b"a" * 257


def test_report_receive_strips_each_sxb_chunk_only() -> None:
    sxb, normal = ReceiveBuffer(sxb=True), ReceiveBuffer(sxb=False)
    for buffer in (sxb, normal):
        buffer.report_size = 4
        buffer.start("q_report_allow")
    assert sxb.feed(b"0" * 14 + b"ab") is None
    assert sxb.feed(b"1" * 14 + b"cd") == b"abcd"
    assert normal.feed(b"0" * 14 + b"ab") == b"0" * 14 + b"ab"
    with pytest.raises(MalformedNotification):
        sxb.feed(b"ab")


def test_normal_start_and_sxb_start_have_distinct_buffer_lifetimes() -> None:
    normal, sxb = ReceiveBuffer(sxb=False), ReceiveBuffer(sxb=True)
    packet = frame(b"a" * 20, 7)
    for buffer in (normal, sxb):
        buffer.start("q_part")
        assert buffer.feed(packet[:15]) is None
        buffer.start("q_realtime")
    assert not normal.pending
    assert sxb.pending == packet[:15]
    sxb.clear()
    assert sxb.command is None and not sxb.pending
    assert sxb.feed(packet) is None


def test_response_selection_uses_whole_text_precedence() -> None:
    assert response_command('{"cmd":"q_part","text":"s_time"}', sxb=True, active=None) == "s_time"
    assert response_command("q_ota_ttl", sxb=True, active=None) == "q_ota"
    assert response_command("s_ota_crc", sxb=True, active=None) == "s_ota"
    assert response_command('{"cmd":"q_time"}', sxb=False, active="q_part") == "q_part"


@pytest.mark.parametrize(
    ("version", "uses_new"),
    [("0.0.3", True), ("0.0.2.9", False), ("1.99.99", False), ("2.0", True), ("0", False)],
)
def test_version_predicate(version: str, uses_new: bool) -> None:
    assert new_day_layout(version) is uses_new


def test_live_gates_preserve_missing_displays() -> None:
    assert normal_live("0-0-65-17-0-1-0-1-0") == LiveState(None, None, None, None, None, False)
    assert normal_live("0-0-65-17-1-1-0-1-0") == LiveState(None, None, False, True, True, True)
    assert sxb_live([0, -2, 65, 17, 1]) == LiveState("65", "17", True, True, True, True)
    assert sxb_live([0, 0, 65, 17, 0]) == LiveState(None, None, False, None, None, True)
    assert sxb_live([1]) is None
    with pytest.raises(MalformedNotification):
        sxb_live([0])
