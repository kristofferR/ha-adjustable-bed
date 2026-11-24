"""The Sinca app's frozen transmit and receive literals through production codecs."""

from datetime import datetime
from typing import cast

import pytest

from custom_components.adjustable_bed.codec import mline as wire
from custom_components.adjustable_bed.codec import sinca_comfort as codec
from custom_components.adjustable_bed.profiles import sinca_comfort as app


# Expected bytes are copied from the frozen Sinca literals.
@pytest.mark.parametrize(
    ("action", "basic", "extended"),
    [
        ("back_up", "05 02 00 00 00 01 00", "e6 fe 16 01 00 00 00 00 04"),
        ("back_down", "05 02 00 00 00 02 00", "e6 fe 16 02 00 00 00 00 03"),
        ("legs_up", "05 02 00 00 00 04 00", "e6 fe 16 04 00 00 00 00 01"),
        ("legs_down", "05 02 00 00 00 08 00", "e6 fe 16 08 00 00 00 00 fd"),
        ("neck_up", "05 02 00 00 00 10 00", "e6 fe 16 10 00 00 00 00 f5"),
        ("neck_down", "05 02 00 00 00 20 00", "e6 fe 16 20 00 00 00 00 e5"),
        ("flat", "05 02 08 00 00 00 00", "e6 fe 16 00 00 00 08 00 fd"),
        ("reading", "05 02 00 00 20 00 00", "e6 fe 16 00 20 00 00 00 e5"),
        ("anti_snore", "05 02 00 00 80 00 00", "e6 fe 16 00 80 00 00 00 85"),
        ("tv", "05 02 00 00 40 00 00", "e6 fe 16 00 40 00 00 00 c5"),
        ("zero_g", "05 02 00 00 10 00 00", "e6 fe 16 00 10 00 00 00 f5"),
        ("memory_1", "05 02 00 01 00 00 00", "e6 fe 16 00 00 01 00 00 04"),
        ("memory_2", "05 02 00 04 00 00 00", "e6 fe 16 00 00 04 00 00 01"),
        ("light", "05 02 00 02 00 00 00", "e6 fe 16 00 00 02 00 00 03"),
        ("massage_toggle", "05 02 00 00 01 00 00", "e6 fe 16 00 01 00 00 00 04"),
        ("massage_wave", "05 02 10 00 00 00 00", "e6 fe 16 00 00 00 10 00 f5"),
        ("massage_timer", "05 02 00 00 02 00 00", "e6 fe 16 00 02 00 00 00 03"),
        ("massage_foot", "05 02 00 00 04 00 00", "e6 fe 16 00 04 00 00 00 01"),
        ("massage_head", "05 02 00 00 08 00 00", "e6 fe 16 00 08 00 00 00 fd"),
        ("stop", "05 02 00 00 00 00 00", "e6 fe 16 00 00 00 00 00 05"),
    ],
)
def test_control_frames(action: str, basic: str, extended: str) -> None:
    words = {
        **{
            f"{axis}_{direction}": word
            for axis, sides in app.MOTORS.items()
            for direction, word in zip(("up", "down"), sides, strict=True)
        },
        **app.PRESETS,
        **{f"massage_{key}": word for key, word in app.MASSAGE.items()},
        "light": app.LIGHT,
        "stop": 0,
    }
    assert app.PROFILES["sleep"].control(words[action]) == bytes.fromhex(basic)
    assert app.PROFILES["okin"].control(words[action]) == bytes.fromhex(extended)


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ("status", "00 b0"),
        ("okin_status", "e6 fe 16 00 00 00 00 00 05"),
        ("alarm_query", "00 c0"),
        ("okin_alarm_query", "e1 80 03 9b"),
        ("alarm_disable", "07 05 00 00 00 00 00 00 00"),
        ("okin_alarm_disable", "ed 80 03 00 00 00 00 00 00 00 00 00 00 00 00 8f"),
        ("gainNewHistoricalData", "01 b1 02"),
        ("gainAllHistoricalData", "01 b1 01"),
        ("confirmGainHistoryData", "01 b3 01"),
        ("openPrivacyMode", "01 b2 01"),
        ("closePrivacyMode", "01 b2 00"),
        ("checkOpenBlemanage", "01 b4 01"),
        ("okin_clock", "e7 80 01 7e 0a 18 0d 25 2a 9b"),
        ("smartsainuo_clock", "07 04 26 11 24 02 13 37 42"),
        ("sleep_clock", "07 04 7e 0a 18 01 0d 25 2a"),
        ("unknown_clock", "07 04 1a 0a 18 02 0d 25 2a"),
        ("off", "04 0b 00 00 00"),
        ("elevation_high", "04 0b 01 02 06"),
        ("head_medium", "04 0b 01 01 03"),
        ("elevation_low", "04 0b 01 02 01"),
        ("demo_head", "04 0b 02 01 01"),
        ("demo_elevation", "04 0b 02 01 02"),
    ],
)
def test_settings_frames(action: str, expected: str) -> None:
    legacy, extended = app.PROFILES["sleep"], app.PROFILES["okin"]
    when = datetime(2026, 11, 24, 13, 37, 42)
    frames = {
        **wire.AUXILIARY,
        "status": legacy.status,
        "okin_status": extended.status,
        "alarm_query": legacy.alarm_frame(),
        "okin_alarm_query": extended.alarm_frame(),
        "alarm_disable": legacy.alarm_frame(disable=True),
        "okin_alarm_disable": extended.alarm_frame(disable=True),
        **{f"{key}_clock": wire.clock(key, when) for key in app.PROFILES},
        "off": wire.anti_snore(False, 1, 1),
        "elevation_high": codec.anti_snore(2, 6),
        "head_medium": codec.anti_snore(1, 3),
        "elevation_low": codec.anti_snore(2, 1),
        "demo_head": wire.anti_snore(True, 1, 1, demo=True),
        "demo_elevation": wire.anti_snore(True, 1, 2, demo=True),
    }
    assert frames[action] == bytes.fromhex(expected)


@pytest.mark.parametrize(
    ("selector", "packet", "expected"),
    [
        ("smart", "ed fe 16 01 02 03 04 03 06 09 0a 0b 0c 0d 42 0f 10 11 12 13", (4, 3, 2, 3, 2)),
        ("smart", "ed fe 16 00 00 00 00 ff 01 00 00 00 00 00 03", (0, 1, 0, 1, 3)),
        ("sleep", "a5 0b 00 00 58 02 03 15 07", (3, 4, 4, 4, 2)),
        ("smart", "a5 0b 00 00 58 02 03 15 07", (3, 4, 4, 4, 38)),
        (
            "okin",
            "f4 fe 16 00 00 00 00 00 00 00 00 a5 07 00 00 00 00 00 00 04 00 05",
            (0, 4, 3, 4, 4),
        ),
    ],
)
def test_massage_replies(selector: str, packet: str, expected: tuple[int, ...]) -> None:
    result = codec.massage(bytes.fromhex(packet), cast(wire.Protocol, selector))
    assert result is not None
    assert (result.wave, result.intensity, result.head, result.foot, result.timer) == expected


@pytest.mark.parametrize(
    ("packet", "expected"),
    [
        ("a5 0c 0e 00 00 00 00 00 00 01", (0, 0, 0, 0, 0)),
        ("a5 0c 0e 00 05 03 07 25 00 01", (5, 3, 7, 37, 1)),
        ("ed 80 03 07 25 05 0d", (5, 13, 7, 37, 1)),
        ("a5 0c 00", (0, 0, 0, 0, 0)),
    ],
)
def test_alarm_replies(packet: str, expected: tuple[int, ...]) -> None:
    result = codec.alarm(bytes.fromhex(packet))
    assert result is not None
    assert (result.week, result.mode, result.hour, result.minute, result.enabled) == expected


@pytest.mark.parametrize("tail", ["14 15 16", "14 15 16 17"])
def test_fragment_replacement_and_short_interleaving(tail: str) -> None:
    join = wire.Assembler()
    fragment = bytes.fromhex("ed fe 16 01 02 03 04 03 06 09 0a 0b 0c 0d 42 0f 10 11 12 13")
    assert join.feed(b"\0" + fragment[1:]) is None
    assert join.feed(fragment) is None
    assert join.feed(b"\0") is None
    assert join.feed(bytes.fromhex(tail)) == fragment + bytes.fromhex(tail)


def test_independent_sensor_fields_and_alarm_ui_rules() -> None:
    pkt = bytes.fromhex("a50b000000000000000000000000000106000002")
    assert codec.anti_snore_state(pkt) == (True, "high")
    assert codec.anti_snore_state(pkt[:17]) == (True, "high")
    assert codec.privacy_state(pkt[:17], False) is None
    assert codec.privacy_state(pkt, False) is False
    assert codec.privacy_state(pkt, True) is True
    assert codec.anti_snore_state(bytes.fromhex("a50b000000000000000000000000000006")) == (
        False,
        "low",
    )
    assert codec.newer_sensor("SENSOR_VOICE", "1.0.9") is False
    assert codec.newer_sensor("SENSOR_VOICE", "1.1") is True
    assert codec.newer_sensor("SENSOR_VOICE", "2.invalid") is True
    assert codec.newer_sensor("SENSOR_VOICE", "1.invalid") is None
    assert codec.newer_sensor("SENSOR_VOICE", "1.") is None
    assert codec.newer_sensor("sensor_voice", "2") is False
    assert codec.alarm(b"\xa5\x0c\x0e") is None
    assert codec.alarm(b"\xed\x80\x03") is None
    assert codec.AlarmState(5, 3, 7, 37, 1).action("sleep") == "tv"
    alarm = codec.AlarmState(133, 16, 7, 37, 2)
    assert alarm.action("okin") == "anti_snore" and alarm.repeat == 133
