"""Source vectors for the independent GM Control 4.6.6 app profile."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.gmmotor_notifications import Event, common, desk21, extra
from custom_components.adjustable_bed.gmmotor_protocol import (
    FrameBuffer,
    MalformedNotification,
    Material,
    clock_frames,
    countdown_frames,
    countdown_minutes,
    crc16,
    delete_alarm,
    desk_packet,
    light_color,
    light_timeout,
    query_alarm,
    query_sleep_name,
    query_snore,
    repeating_alarm,
    snore_config,
    snore_enabled,
    stop_packet,
)


def test_material_overrides_do_not_cross_wire_modes() -> None:
    material = Material("deviceFunctionItemHeadUp", 36, 102, 17, 0, 57)
    assert material.packet(side=1, single=False) == bytes.fromhex("6e01011181")
    assert material.packet(side=2, single=True) == b"\x39"
    assert material.packet(side=1, single=False, long=True) == bytes.fromhex("6e01010070")
    assert material.packet(side=2, single=True, long=True) == b"\x00"
    # Integers are narrowed at the native boundary, including the checksum.
    assert Material("", 511).packet(side=0, single=False) == bytes.fromhex("6e0100ff6e")


def test_special_prefix_is_independent_of_side() -> None:
    query = Material("deviceFunctionItemCheckLight", 1)
    assert query.packet(side=2, single=False) == bytes.fromhex("6e0a000179")
    assert query.packet(side=2, single=True) == b"\x01"
    assert stop_packet(side=1, single=False) == bytes.fromhex("6e01016ede")
    assert stop_packet(side=2, single=True) == b"\x6e"


def test_calendar_and_timezone_order() -> None:
    local = datetime(2023, 11, 14, 12, 34, 56, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    epoch, calendar = clock_frames(local)
    assert epoch == codec.frame(110, 12, 32, 8, 2, 1, *int(local.timestamp()).to_bytes(4, "big"), 5)
    assert calendar == bytes.fromhex("6e0d20080301350b0e0c22385b")
    negative = local.replace(tzinfo=timezone(timedelta(hours=-9, minutes=-30)))
    assert clock_frames(negative)[0][-2] == 247
    assert clock_frames(datetime(2023, 1, 1, tzinfo=UTC))[0][-2] == 0
    with pytest.raises(ValueError):
        clock_frames(local.replace(tzinfo=None))


def test_single_alarm_reconstructs_minutes_and_rolls_nonpositive_by_24_hours() -> None:
    now = datetime(2026, 11, 3, 20, 30, 59, tzinfo=UTC)
    assert countdown_minutes(now.replace(hour=21, minute=0, second=1), now) == 30
    assert countdown_minutes(now.replace(second=0), now) == 1440
    assert countdown_minutes(now.replace(hour=20, minute=29), now) == 1439
    # The source compares epoch seconds, not wall-time timedelta arithmetic.
    target = datetime(2026, 10, 25, 3, 30, tzinfo=timezone(timedelta(hours=1)))
    before = datetime(2026, 10, 25, 1, 30, tzinfo=timezone(timedelta(hours=2)))
    assert countdown_minutes(target, before) == 180


def test_specialized_command_vectors() -> None:
    assert countdown_frames(1000, 7) == (bytes.fromhex("6e05e8005b"), bytes.fromhex("6e0603077e"))
    assert countdown_frames(0, 0) == (bytes.fromhex("6e05000073"), bytes.fromhex("6e06000074"))
    assert light_timeout(0) == bytes.fromhex("6e0bffff77")
    assert light_color((64, 128, 191)) == bytes.fromhex("6e0cff40b96e0d80bfba")
    assert query_sleep_name() == bytes.fromhex("6e0820060300009f")
    assert query_alarm() == bytes.fromhex("6e0820050100009c")
    assert delete_alarm(5) == bytes.fromhex("6e082005020105a3")
    assert repeating_alarm((3, 127, 6, 45, 2, 1)) == bytes.fromhex("6e0d20050101037f062d02015a")
    assert snore_enabled(True) == bytes.fromhex("6e09200601010001a0")
    assert snore_config("time", 7) == bytes.fromhex("6e0a20060501020007ad")
    assert query_snore(configuration=True) == bytes.fromhex("6e09200605000000a2")


def test_desk_is_a_distinct_builder() -> None:
    material = Material("deviceFunctionItemDeskSetHeight", 0)
    assert desk_packet(material, height=1234.9) == bytes.fromhex("6e880c2224")
    assert desk_packet(Material("deviceFunctionItemDeskReset", 3)) == bytes.fromhex("6e95000306")
    assert desk_packet(Material("deviceFunctionItemDeskUnitChange", 1)) == bytes.fromhex(
        "6e91000100"
    )


def test_extended_fragmentation_and_checksum_order() -> None:
    frame = bytes.fromhex("6e200a010302010203a4")
    buffer = FrameBuffer()
    assert buffer.extract(frame[:3]) == ()
    assert buffer.extract(frame[3:] + b"\x6e") == ((32, frame),)
    assert buffer.pending == b"\x6e"
    assert extra(frame) == (Event("motor_angle", {"position": 1, "angle": 3}),)
    buffer.clear()
    assert buffer.extract(frame[:-1] + b"\x00") == ()


@pytest.mark.parametrize("prefix", [b"\x6e\x20\x00", b"\x6e\x21\x00", b"\x6e\x40\x00\x00"])
def test_non_progressing_lengths_drop_entire_batch(prefix: bytes) -> None:
    buffer = FrameBuffer()
    # Extraction precedes dispatch, so an earlier clock ACK must not be credited.
    with pytest.raises(MalformedNotification, match="Non-progressing"):
        buffer.extract(bytes.fromhex("6e09010078") + prefix)
    assert not buffer.pending
    assert buffer.extract(bytes.fromhex("6e09010078")) == ((0, bytes.fromhex("6e09010078")),)


def test_legacy_length_and_checksum_are_not_invented() -> None:
    buffer = FrameBuffer()
    # Source common parsing accepts this even though its last byte is not sum8.
    frame = bytes.fromhex("6e90300100")
    assert buffer.extract(frame) == ((0, frame),)
    assert common(frame) == (Event("motor_angle", {"no": 0, "status": 0, "angle": 1}),)
    # A literal 6e inside a legacy record is a boundary, unlike extended payloads.
    assert buffer.extract(bytes.fromhex("6e09016e")) == ((0, bytes.fromhex("6e0901")),)
    assert buffer.pending == b"\x6e"


def test_three_byte_crc_header_is_safely_retained() -> None:
    buffer = FrameBuffer()
    assert buffer.extract(bytes.fromhex("6e4000")) == ()
    body = bytes.fromhex("6e400006")
    frame = body + crc16(body).to_bytes(2, "big")
    assert buffer.extract(frame[3:]) == ((64, frame),)
    assert crc16(b"123456789") == 0x31C3


def test_required_fields_fail_without_synthetic_app_defaults() -> None:
    with pytest.raises(MalformedNotification):
        extra(bytes.fromhex("6e200492"))
    with pytest.raises(MalformedNotification):
        extra(bytes.fromhex("6e20050194"))
    # Category 10 ignores the ordinary status gate and preserves the full frame.
    frame = bytes.fromhex("6e20070a0100a0")
    assert extra(frame) == (Event("check", [1, list(frame)]),)


def test_common_music_bitfields_and_detection_defaults() -> None:
    assert common(bytes.fromhex("6e90b1e000")) == (
        Event("music_usb", True),
        Event("music_play", True),
        Event("music_shake", True),
        Event("music_ble", True),
    )
    assert common(bytes.fromhex("6e90c2f000")) == (Event("detection_status", "start"),)
    assert common(bytes.fromhex("6e90c30100")) == (Event("detection_message", {}),)


def test_alarm_and_light_timer_fields_keep_source_semantics() -> None:
    alarm = codec.frame(110, 32, 13, 5, 1, 2, 3, 127, 6, 45, 2, 1)
    assert extra(alarm) == (
        Event(
            "alarm_list", {"id": 3, "repeat": 127, "hour": 6, "minute": 45, "mode": 2, "status": 1}
        ),
    )
    timer = codec.frame(110, 32, 10, 4, 2, 2, 0, 2, 15)
    assert extra(timer) == (Event("rgb_timer", 135),)
    # The sender's timeout is BE16 seconds; the response uses minute/second pairs.
    assert light_timeout(135) == bytes.fromhex("6e0b008700")


def test_empty_blanket_dto_and_end_relative_desk_fields() -> None:
    blanket = codec.frame(110, 32, 9, 13, 1, 2, 0, 1)
    assert extra(blanket) == (Event("blanket_power", {}),)
    desk = codec.frame(110, 33, 12, 15, 6, 2, 1, 2, 3, 4, 5)
    assert desk21(desk) == (
        Event(
            "desk_pair",
            {
                "online": False,
                "height": 846.0,
                "sedentary_setting": 3846,
                "sedentary_countdown": 513,
                "desk_code": 0x02030405,
            },
        ),
    )
