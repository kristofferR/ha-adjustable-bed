"""Accepted P1 literals through production builders, without the audit oracle."""

import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.codec import ergobq as codec
from custom_components.adjustable_bed.codec import ff_frame, keeson, richmat

VECTORS = json.loads((Path(__file__).parent / "fixtures/ergobq/vectors.json").read_text())


@pytest.mark.parametrize("row", VECTORS, ids=lambda row: row["id"])
def test_frozen_p1_literals(row):
    args = row["inputs"]
    packet = codec.frame(args["command"], bytes.fromhex(args["payload_hex"]))
    assert packet.hex() == row["expected_bytes"]
    parsed = codec.parse_frame(packet)
    assert parsed == codec.Frame(args["command"], bytes.fromhex(args["payload_hex"]))
    if args["command"] == 4:
        values = codec.parse_dps(parsed.payload)
        # Rebuild typed values too, not just a frame containing the literal body.
        entries = []
        for id, value in values.items():
            if type(value) is bool:
                entries.append(codec.boolean(id, value))
            elif type(value) is int:
                entries.append(
                    codec.enumeration(id, value) if id in (6, 9, 10) else codec.number(id, value)
                )
            else:
                assert isinstance(value, bytes)
                entries.append(codec.raw(id, value))
        assert codec.publish(entries) == packet


def test_existing_carriers_do_not_reproduce_the_stop_literal():
    stop = bytes.fromhex(VECTORS[0]["expected_bytes"])
    # Existing variable-length checksummed carriers do not implement this envelope.
    assert richmat.frame(*stop[:-1]) != stop
    assert ff_frame.with_crc(stop[:-2]) != stop
    assert keeson.frame(5) != stop


def test_structured_live_builders_match_frozen_frames():
    expected = {row["id"]: bytes.fromhex(row["expected_bytes"]) for row in VECTORS}
    assert codec.auth(" 12 ") == expected["p1-auth-example"]
    assert codec.publish(codec.force_sync(1)) == expected["P1-force-sync"]
    assert (
        codec.publish(reversed(codec.force_sync(1))).hex() == "55aa0004000a0a0400010109040001022d1a"
    )
    assert (
        codec.publish((codec.raw(12, codec.Massage(True, 3, 0, 15).encode()),))
        == expected["p1-massage"]
    )
    light = codec.Light(True, 50, 255, 0, 16, 5)
    assert codec.publish((codec.raw(54, light.encode()),)) == expected["P1-packed-light"]
    record = codec.custom_schedule(1, 2, 0, 7, 30, light=codec.Light(False, 50, 255, 0, 16, 5))
    assert codec.publish((codec.raw(41, record),)) == expected["P1-schedule-custom"]
    assert (
        codec.publish((codec.raw(41, codec.diy_schedule(2, 1, 2, 6, 45, 11)),))
        == expected["P1-schedule-diy-mode"]
    )
    assert codec.publish(codec.run_diy(11)) == expected["P1-diy-run11"]
    assert codec.publish(codec.run_diy(3)) == expected["P1-diy-terminate"]


def test_parser_boundaries_and_stream_recovery():
    assert codec.parse_dps(bytes.fromhex("01020004ffffffff05010001013d0000040b000001")) == {
        1: -1,
        5: True,
        61: bytes.fromhex("0b000001"),
    }
    assert codec.parse_dps(bytes.fromhex("09040001020904000101")) == {9: 1}
    for value in ("01", "01020004ff"):
        with pytest.raises(ValueError):
            codec.parse_dps(bytes.fromhex(value))
    assert codec.parse_info(bytes.fromhex("0101014103025631030158")) == {1: b"A", 3: b"X"}
    packet = codec.frame(5, codec.number(1, 15).encode())
    receiver = codec.Receiver()
    assert receiver.feed(b"\x55") == []  # The app drops initial callbacks shorter than magic.
    assert receiver.feed(packet[:9]) == []
    assert receiver.feed(packet[9:] + packet) == [codec.parse_frame(packet)] * 2
    damaged = packet[:-1] + bytes([packet[-1] ^ 1])
    assert receiver.feed(damaged + packet) == [codec.parse_frame(packet)]
    assert receiver.feed(b"\x55\xaa\x00\x05\x0f\xff" + packet) == [codec.parse_frame(packet)]
    assert codec.parse_frame(packet[:-1]) is None


def test_diy_optional_fields_length_and_schedule_validation():
    fixed = bytes.fromhex("0b01000a070001020304050600000132112233445500000a")
    tlv = bytes.fromhex("0b01000a8001010203aabbcc")
    assert codec.diy_length(fixed) == 24
    assert codec.diy_length(tlv) == 12
    parsed = codec.parse_diy(fixed)
    assert parsed is not None and parsed[0] == 11
    segment = parsed[1][0]
    assert segment.motor == codec.ProgramMotor(1, 2, 3, (4, 5, 6))
    assert segment.vibration == codec.ProgramVibration(1, 3, 2)
    assert segment.light == codec.ProgramLight(1, 1, 34, 51, (68, 85, 0), 10)
    assert codec.parse_diy(tlv) is None  # Length alone does not give TLV field semantics.
    assert len(codec.run_diy(11)) == 1
    assert [dp.id for dp in codec.run_diy(11, fixed)] == [61, 60]
    for value in (fixed[:-1], fixed + b"\x00", tlv[:-1]):
        with pytest.raises(ValueError):
            codec.diy_program(value)
    for repeat in (1, 255):
        with pytest.raises(ValueError):
            codec.custom_schedule(1, 2, repeat, 7, 30)
    with pytest.raises(ValueError):
        codec.custom_schedule(1, 2, 0, 7, 30, sync=True, head=codec.Massage(True))
    assert len(codec.custom_schedule(1, 0, 0, 7, 30)) == 24  # Delete is a complete outgoing record.
    with pytest.raises(ValueError):
        codec.frame(4, bytes(513))
