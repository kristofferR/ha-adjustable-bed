"""Sleep-sensor envelope: frozen frames round-trip through ``codec/sleep_envelope.py``.

The literals are frames the sensor routes sent before the codec existed:
``casper`` from ``tests/fixtures/casper_base/builders.json``, ``hush`` from
``tests/fixtures/hush_sleep_commands.json``, ``gmmotor`` from the GM Control
sleep protocol test and the wire snapshot, and ``goodvibe`` from the wire
snapshot's Good Vibe sleep routes.
"""

from __future__ import annotations

import pytest

from custom_components.adjustable_bed.casper_base_protocol import Request
from custom_components.adjustable_bed.casper_sleep_protocol import command, envelope
from custom_components.adjustable_bed.codec import sleep_envelope
from custom_components.adjustable_bed.gmmotor_sleep_protocol import Requests
from custom_components.adjustable_bed.goodvibe_sleep import sleep_packet
from custom_components.adjustable_bed.hush_sleep_protocol import build

FRAMES: dict[str, frozenset[str]] = {
    "casper": frozenset(
        {
            "0001010029000011034355442200"
            "7b226964223a312c22636d64223a22735f70617274222c2276616c223a6e756c6c7d",
            "0001010029000011034355442200"
            "7b226964223a312c22636d64223a22715f70617274222c2276616c223a6e756c6c7d",
            "0001010026000011034355441f00"
            "7b226964223a312c22636d64223a22735f70617274222c2276616c223a327d",
            "0001010027000011034355442000"
            "7b226964223a312c22636d64223a22735f70617274222c2276616c223a31337d",
            "0001010049000011034355444200"
            "7b226964223a312c22636d64223a22735f74696d65222c2276616c223a7b227473223a313736323133373630302c22747a223a224575726f70652f4f736c6f227d7d",
            "000101003e000011034355443700"
            "7b226964223a312c22636d64223a22735f74696d65222c2276616c223a7b227473223a313736323133373630302c22757463223a317d7d",
            "000101003c000011034355443500"
            "7b226964223a312c22636d64223a22715f7265616c74696d65222c2276616c223a7b2274797065223a302c2274696d65223a317d7d",
            "0001010026000011034355441f00"
            "7b226964223a312c22636d64223a22735f696e6974222c2276616c223a307d",
            "0001010050000011034355444900"
            "7b226964223a312c22636d64223a22715f7265706f7274222c2276616c223a7b2270617274223a312c2274797065223a312c2279223a323032362c226d223a31312c2264223a337d7d",
            "000101005a000011034355445300"
            "7b226964223a312c22636d64223a22715f7265706f7274222c2276616c223a7b2270617274223a322c2274797065223a322c2279223a323032362c226d223a31312c2264223a312c22616c6c6f77223a317d7d",
            "0001010032000011034355442b00"
            "7b226964223a312c22636d64223a22715f7265706f7274222c2276616c223a7b22616c6c6f77223a317d7d",
        }
    ),
    "hush": frozenset(
        {
            "0001010049000011034355444200"
            "7b226964223a312c22636d64223a22735f74696d65222c2276616c223a7b227473223a313730303030303030302c22747a223a224575726f70652f4f736c6f227d7d",
            "0001010029000011034355442200"
            "7b226964223a312c22636d64223a22735f70617274222c2276616c223a6e756c6c7d",
            "0001010026000011034355441f00"
            "7b226964223a312c22636d64223a22735f70617274222c2276616c223a317d",
            "000101003c000011034355443500"
            "7b226964223a312c22636d64223a22715f7265616c74696d65222c2276616c223a7b2274797065223a302c2274696d65223a317d7d",
            "0001010050000011034355444900"
            "7b226964223a312c22636d64223a22715f7265706f7274222c2276616c223a7b2270617274223a312c2274797065223a312c2279223a323032362c226d223a31312c2264223a337d7d",
            "000101005a000011034355445300"
            "7b226964223a312c22636d64223a22715f7265706f7274222c2276616c223a7b2270617274223a322c2274797065223a322c2279223a323032362c226d223a31312c2264223a312c22616c6c6f77223a317d7d",
            "000101003e000011034355443700"
            "7b226964223a312c22636d64223a22735f74696d65222c2276616c223a7b227473223a313730303030303030302c22757463223a317d7d",
            "0001010029000011034355442200"
            "7b226964223a312c22636d64223a22715f74696d65222c2276616c223a6e756c6c7d",
            "0001010029000011034355442200"
            "7b226964223a312c22636d64223a22715f70617274222c2276616c223a6e756c6c7d",
            "0001010027000011034355442000"
            "7b226964223a312c22636d64223a22735f70617274222c2276616c223a31317d",
            "0001010032000011034355442b00"
            "7b226964223a312c22636d64223a22715f7265706f7274222c2276616c223a7b22616c6c6f77223a317d7d",
            "0001010026000011034355441f00"
            "7b226964223a312c22636d64223a22735f696e6974222c2276616c223a307d",
            "0001010029000011034355442200"
            "7b226964223a312c22636d64223a22715f73656e73222c2276616c223a6e756c6c7d",
            "000101002e000011034355442700"
            "7b226964223a312c22636d64223a22715f616e7469536e6f7265222c2276616c223a6e756c6c7d",
            "0001010043000011034355443c00"
            "7b226964223a312c22636d64223a22735f616e7469536e6f7265222c2276616c223a7b224c223a5b302c382c345d2c2252223a5b302c382c345d7d7d",
        }
    ),
    "gmmotor": frozenset(
        {
            "00070100090000110343554402007b7d",
            "0007010029000011034355442200"
            "7b226964223a372c22636d64223a22735f70617274222c2276616c223a6e756c6c7d",
            "0001010027000011034355442000"
            "7b226964223a312c22636d64223a22735f70617274222c2276616c223a31327d",
            "000201003e000011034355443700"
            "7b226964223a322c22636d64223a22735f74696d65222c2276616c223a7b227473223a313736373332333034352c22757463223a307d7d",
            "000301003e000011034355443700"
            "7b226964223a332c22636d64223a22735f74696d65222c2276616c223a7b227473223a313736373332333034352c22757463223a307d7d",
            "0004010029000011034355442200"
            "7b226964223a342c22636d64223a22715f70617274222c2276616c223a6e756c6c7d",
            "000501003c000011034355443500"
            "7b226964223a352c22636d64223a22715f7265616c74696d65222c2276616c223a7b2274797065223a302c2274696d65223a317d7d",
        }
    ),
    "goodvibe": frozenset(
        {
            "0001010027000011034355442000"
            "7b226964223a312c22636d64223a22735f70617274222c2276616c223a31327d",
            "000201003e000011034355443700"
            "7b226964223a322c22636d64223a22735f74696d65222c2276616c223a7b227473223a313736373332333034352c22757463223a307d7d",
            "000301003c000011034355443500"
            "7b226964223a332c22636d64223a22715f7265616c74696d65222c2276616c223a7b2274797065223a302c2274696d65223a317d7d",
            "0001010041000011034355443a00"
            "7b226964223a312c22636d64223a22735f74696d65222c2276616c223a7b227473223a313736373332333034352c22747a223a22555443227d7d",
            "000201003c000011034355443500"
            "7b226964223a322c22636d64223a22715f7265616c74696d65222c2276616c223a7b2274797065223a302c2274696d65223a317d7d",
        }
    ),
}
ALL_FRAMES = sorted(frozenset().union(*FRAMES.values()))


@pytest.mark.parametrize("literal", ALL_FRAMES)
def test_literal_round_trips(literal: str) -> None:
    packet = bytes.fromhex(literal)
    request_id, total, sequence = packet[1:4]
    body = packet[sleep_envelope.HEADER_SIZE :]
    assert sleep_envelope.frame(body, request_id, total=total, sequence=sequence) == packet
    assert sleep_envelope.response_size(packet[:13]) == len(packet)


def test_every_app_frames_one_message_identically() -> None:
    literal = bytes.fromhex(
        "000101003c000011034355443500"
        "7b226964223a312c22636d64223a22715f7265616c74696d65222c2276616c223a7b2274797065223a302c2274696d65223a317d7d"
    )
    request = Request("sensor_live")
    assert command("mm", "q_realtime", 1, request) == literal
    assert build("sxb", "q_realtime", 1, request, ts=0, zone=0) == literal
    assert Requests(sxb=False).build("q_realtime").packet == literal
    assert sleep_packet(1, "q_realtime", {"type": 0, "time": 1}) == literal
    assert literal.hex() in FRAMES["casper"]


def test_app_builders_send_frozen_frames() -> None:
    gm = Requests(sxb=True)
    gm.next_id = 4
    assert gm.build("q_part").packet.hex() in FRAMES["gmmotor"]
    disabled = Request("sensor_anti_snore", enabled=False)
    assert build("sxb", "s_antiSnore", 1, disabled, ts=0, zone=0).hex() in FRAMES["hush"]
    s_time = sleep_packet(1, "s_time", {"ts": 1767323045, "tz": "UTC"})
    assert s_time.hex() in FRAMES["goodvibe"]


def test_header_fields_keep_their_low_byte() -> None:
    header = sleep_envelope.frame(b"x" * 257, 511, total=258, sequence=256)[:14]
    assert header == bytes.fromhex("00ff020008000011034355440101")
    assert sleep_envelope.frame(b"", 7) == b""


def test_responses_are_sized_by_the_low_length_byte() -> None:
    packet = sleep_envelope.frame(b"a" * 257, 7)
    assert sleep_envelope.response_size(packet) == 1 + sleep_envelope.HEADER_SIZE
    assert sleep_envelope.response_size(packet[:12]) is None


def test_bodies_longer_than_the_length_field_are_rejected() -> None:
    assert len(sleep_envelope.frame(b"a" * 0xFFFF, 1)) == 0xFFFF + sleep_envelope.HEADER_SIZE
    with pytest.raises(ValueError, match="16-bit length"):
        sleep_envelope.frame(b"a" * 0x10000, 1)
    with pytest.raises(ValueError, match="16-bit length"):
        envelope({"x": "a" * 0x10000}, 1)
    with pytest.raises(ValueError, match="16-bit length"):
        sleep_packet(1, "s_time", "a" * 0x10000)
    # Good Vibe keeps its own sequence range.
    for sequence in (0, 255):
        with pytest.raises(ValueError, match="Sequence"):
            sleep_packet(sequence, "q_realtime", None)
