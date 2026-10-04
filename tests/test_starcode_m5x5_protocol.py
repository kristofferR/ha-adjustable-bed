"""Literal oracles from accepted AdjustableM5X5 1.2.3 packet/receive fixtures.

Expected fields are transcribed independently of the implementation. The app's
short-frame exceptions are intentionally hardened; raw non-byte Dart Lists are
outside the bytes notification contract. No private report path is required.
"""

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.adjustable_bed.beds.starcode_m5x5_protocol import (
    StateValue,
    clock_packet,
    extended_packet,
    long_normal_packet,
    manufacturer_dialect,
    normal_packet,
    parse_notification,
    query_packet,
)

NORMAL_VECTORS: list[tuple[str, int, str, str]] = [
    ("V01", 1, "legacy", "05 02 00 00 00 01 00"),
    ("V02", 2, "legacy", "05 02 00 00 00 02 00"),
    ("V03", 51392512, "star", "5a 01 03 10 30 00 a5"),
    ("V04", 51392513, "star", "5a 01 03 10 30 01 a5"),
    ("V05", 134217728, "legacy", "05 02 08 00 00 00 00"),
    ("V06", 51392528, "star", "5a 01 03 10 30 10 a5"),
    ("V07", 65536, "legacy", "05 02 00 01 00 00 00"),
    ("V08", 51392538, "star", "5a 01 03 10 30 1a a5"),
    ("V09", 134479872, "legacy", "05 02 08 04 00 00 00"),
    ("V10", 51392661, "star", "5a 01 03 10 30 95 a5"),
    ("V15", 51392580, "star", "5a 01 03 10 30 44 a5"),
    ("V22", 51392576, "star", "5a 01 03 10 30 40 a5"),
    ("V23", 51392577, "star", "5a 01 03 10 30 41 a5"),
    ("V24", 51392578, "star", "5a 01 03 10 30 42 a5"),
    ("V25", 51392579, "star", "5a 01 03 10 30 43 a5"),
    ("V26", 51392582, "star", "5a 01 03 10 30 46 a5"),
]

SUBCLASS_VECTORS: list[tuple[str, str, tuple[str, ...], dict[str, StateValue]]] = [
    (
        "S01",
        "a5 0b 00 00 00 00 30 00 01 01 2c 42 05 00 00 00 00 00 00 00",
        ("cb25", "f23", "kneading"),
        {
            "sonic_head_level": 2,
            "sonic_foot_level": 4,
            "sonic_active": True,
            "sonic_frequency": 30,
            "sonic_time_raw": 300,
            "sonic_mode": 1,
            "sonic_massage_type": 3,
        },
    ),
    (
        "S02",
        "a5 0b 00 00 00 00 10 00 00 12 34 04 09 00 00 00 00 00 00 00",
        ("cb25", "f23", "kneading"),
        {
            "sonic_head_level": 4,
            "sonic_foot_level": 0,
            "sonic_active": False,
            "sonic_frequency": 40,
            "sonic_time_raw": 4660,
            "sonic_mode": 0,
            "sonic_massage_type": 1,
        },
    ),
    (
        "S03",
        "a5 0b 00 00 00 00 00 00 0f 00 64 10 ff 00 00 00 00 00 00 00",
        ("cb25", "f23", "kneading"),
        {
            "sonic_head_level": 0,
            "sonic_foot_level": 1,
            "sonic_active": False,
            "sonic_frequency": 50,
            "sonic_time_raw": 100,
            "sonic_mode": 1,
            "sonic_massage_type": 0,
        },
    ),
    (
        "S04",
        "a5 0b 00 00 00 00 f0 00 00 ff ff 00 05 00 00 00 00 00 00 00",
        ("cb25", "f23", "kneading"),
        {
            "sonic_head_level": 0,
            "sonic_foot_level": 0,
            "sonic_active": False,
            "sonic_frequency": 0,
            "sonic_time_raw": 0,
            "sonic_mode": 0,
            "sonic_massage_type": 15,
        },
    ),
    ("S05", "a5 0b", ("cb25", "f23", "kneading"), {}),
    (
        "K01",
        "a5 0f 00 01 01 01 01 2c",
        ("kneading",),
        {"kneading_on": True, "kneading_demo": True, "kneading_mode": 1, "kneading_time_raw": 300},
    ),
    (
        "K02",
        "a5 0f 00 00 02 ff 12 34",
        ("kneading",),
        {
            "kneading_on": False,
            "kneading_demo": False,
            "kneading_mode": 2,
            "kneading_time_raw": 4660,
        },
    ),
    (
        "K03",
        "a5 0f 00 02 00 00 00 00",
        ("kneading",),
        {"kneading_on": False, "kneading_demo": False, "kneading_mode": 0, "kneading_time_raw": 0},
    ),
    ("K04", "a5 0f 00 01 01", ("kneading",), {}),
    ("K05", "a5 0f 00 01 01 02", ("kneading",), {}),
    ("K06", "a5 0f 00 01 01 02 00", ("kneading",), {}),
]

ALARM_VECTORS: list[tuple[str, str, str, str, dict[str, StateValue]]] = [
    (
        "R01",
        "a5 0c 00 00 7f 01 17 3b dd 01 00 55 09 06 1e ee 00",
        "cb25",
        "legacy",
        {
            "alarm_0": True,
            "alarm_0_details": {
                "index": 0,
                "hour": 23,
                "minute": 59,
                "isOn": True,
                "repeat_raw": 127,
                "wake": "zg",
            },
        },
    ),
    (
        "R02",
        "a5 0c 00 00 7f 01 17 3b dd 01 00 55 09 06 1e ee 00",
        "cb25",
        "star",
        {
            "alarm_0": True,
            "alarm_0_details": {
                "index": 0,
                "hour": 23,
                "minute": 59,
                "isOn": True,
                "repeat_raw": 127,
                "wake": "zg",
            },
            "alarm_1": False,
            "alarm_1_details": {
                "index": 1,
                "hour": 6,
                "minute": 30,
                "isOn": False,
                "repeat_raw": 85,
                "wake": "flat",
            },
        },
    ),
    (
        "R03",
        "a5 0c 00 00 00 ff ff ff 00 00 00 00 00 00 00 00 00",
        "cb25",
        "legacy",
        {
            "alarm_0": False,
            "alarm_0_details": {
                "index": 0,
                "hour": 255,
                "minute": 255,
                "isOn": False,
                "repeat_raw": 0,
                "wake": "none",
            },
        },
    ),
    (
        "R04",
        "a5 0c 00 7f 06 07 06 00 03 03 dd 17 3b 01 55 ff ff ff 63 ff ff fe fd ee 02",
        "f23",
        "legacy",
        {
            "alarm_0": True,
            "alarm_0_details": {
                "index": 0,
                "hour": 23,
                "minute": 59,
                "isOn": True,
                "repeat_raw": 127,
                "preset": "m2",
                "light": "purple",
                "sonic": "sonic3",
                "music": "random",
                "massage": "intensity3",
                "duration": "duration30Min",
            },
            "alarm_1": True,
            "alarm_1_details": {
                "index": 1,
                "hour": 254,
                "minute": 253,
                "isOn": True,
                "repeat_raw": 85,
                "preset": "none",
                "light": "none",
                "sonic": "none",
                "music": "none",
                "massage": "none",
                "duration": "duration10Min",
            },
        },
    ),
    (
        "R05",
        "a5 0c 00 00 00 00 00 07 00 00 00 00 00 00 00 01 01 01 2a 01 01 01 02 00 00",
        "f23",
        "legacy",
        {
            "alarm_0": False,
            "alarm_0_details": {
                "index": 0,
                "hour": 0,
                "minute": 0,
                "isOn": False,
                "repeat_raw": 0,
                "preset": "flat",
                "light": "off",
                "sonic": "none",
                "music": {"music": 7},
                "massage": "off",
                "duration": "duration10Min",
            },
            "alarm_1": False,
            "alarm_1_details": {
                "index": 1,
                "hour": 1,
                "minute": 2,
                "isOn": False,
                "repeat_raw": 0,
                "preset": "zg",
                "light": "onOrWhite",
                "sonic": "normal1",
                "music": {"music": 42},
                "massage": "intensity1",
                "duration": "duration10Min",
            },
        },
    ),
]

EQ_VECTORS: list[tuple[str, str, dict[str, StateValue]]] = [
    (
        "R06",
        "a5 0e 00 00 00 00 00 00 00 00 00 02 00 a5 21 43 65 f0 81 a7 c8 02",
        {
            "usb_on": True,
            "eq_band_0": 1,
            "eq_band_1": -2,
            "eq_band_2": 3,
            "eq_band_3": -4,
            "eq_band_4": -5,
            "eq_band_5": 6,
            "eq_band_6": 0,
            "eq_band_7": 15,
            "eq_low_frequency": 7,
            "eq_high_frequency": 10,
            "eq_volume": 200,
            "eq_preset": "Classical",
        },
    ),
    (
        "R07",
        "a5 0e 00 00 00 00 00 00 00 00 00 00 00 00 ff ff ff ff 00 ff ff ff",
        {
            "usb_on": False,
            "eq_band_0": -15,
            "eq_band_1": -15,
            "eq_band_2": -15,
            "eq_band_3": -15,
            "eq_band_4": -15,
            "eq_band_5": -15,
            "eq_band_6": -15,
            "eq_band_7": -15,
            "eq_low_frequency": -15,
            "eq_high_frequency": -15,
            "eq_volume": 255,
            "eq_preset": "None",
        },
    ),
]

SHORT_VECTORS: list[tuple[str, str, str]] = [
    ("R08", "a5 0c 00 00 7f 01 17 3b dd 01 00 55 09 06 1e", "cb25"),
    ("R09", "a5 0c 00 00 7f 01 17 3b dd 01 00 55 09 06 1e ee", "cb25"),
    ("R10", "a5 0c 00 7f 06 07 06 00 03 03 dd 17 3b 01 55 ff ff ff 63 ff ff fe fd ee", "f23"),
    ("R11", "a5 0e 00 00 00 00 00 00 00 00 00 02 00 a5 21 43 65 f0 81 a7 c8", "f23"),
]


@pytest.mark.parametrize(("vector_id", "key", "dialect", "expected"), NORMAL_VECTORS)
def test_accepted_normal_packet_vectors(
    vector_id: str, key: int, dialect: str, expected: str
) -> None:
    assert normal_packet(key, dialect) == bytes.fromhex(expected), vector_id


@pytest.mark.parametrize(
    ("key", "value", "dialect", "expected"),
    [
        (0, 6, "legacy", "04 e0 00 06 00 00"),
        (0, 6, "star", "5a e0 04 00 06 00 00 a5"),
        (7, 3, "star", "5a e0 04 07 03 00 00 a5"),
        (-1, 256, "legacy", "04 e0 ff 00 00 00"),
        (256, -1, "star", "5a e0 04 00 ff 00 00 a5"),
    ],
)
def test_extended_packet_masks_source_bytes(
    key: int, value: int, dialect: str, expected: str
) -> None:
    assert extended_packet(key, value, dialect) == bytes.fromhex(expected)


@pytest.mark.parametrize(
    ("dialect", "expected"),
    [
        ("legacy", "05 02 ff ff ff ff 00"),
        ("star", "5a 01 ff ff ff ff a5"),
    ],
)
def test_normal_key_preserves_low_32_bits(dialect: str, expected: str) -> None:
    assert normal_packet(-1, dialect) == bytes.fromhex(expected)
    assert normal_packet(0x1FFFFFFFF, dialect) == bytes.fromhex(expected)


def test_accepted_long_light_and_query_vectors() -> None:
    assert long_normal_packet(128) == bytes.fromhex("08 02 00 00 00 00 00 00 00 80")
    assert long_normal_packet(64) == bytes.fromhex("08 02 00 00 00 00 00 00 00 40")
    assert query_packet("legacy") == bytes.fromhex("00 b0")
    assert query_packet("star") == bytes.fromhex("5a b0 00 a5")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (b"star", "star"),
        (b"STAR", "star"),
        (b"StAr", "star"),
        (b"", "legacy"),
        (b" star", "legacy"),
        (b"star\0", "legacy"),
        (b"STARCODE", "legacy"),
        (b"notstar", "legacy"),
        (b"\xffstar", "legacy"),
    ],
)
def test_manufacturer_exact_character_code_selector(raw: bytes, expected: str) -> None:
    assert manufacturer_dialect(raw) == expected


def test_accepted_clock_vector_keeps_local_components() -> None:
    local = datetime(2026, 9, 30, 13, 14, 15, tzinfo=timezone(timedelta(hours=9)))
    assert clock_packet(local) == bytes.fromhex("5a 14 07 1a 09 1e 0d 0e 0f 03 a5")
    monday = datetime(2026, 9, 28, 23, 59, 58)
    sunday = datetime(2026, 10, 4, 0, 0, 0)
    assert clock_packet(monday)[9] == 1
    assert clock_packet(sunday)[9] == 7


@pytest.mark.parametrize("profile", ("cb25", "f23", "kneading"))
@pytest.mark.parametrize("dialect", ("legacy", "star"))
def test_base_motor_literal_offsets_and_clamp(profile: str, dialect: str) -> None:
    data = bytes.fromhex("a5 0d 00 00 01 05 02 06 03 00 04 00 00 00 00 00 00 00")
    assert parse_notification(data, profile=profile, dialect=dialect) == {
        "back": 1,
        "legs": 2,
        "lumbar": 3,
        "motor_part4": 4,
        "motor_part5": 5,
        "motor_part6": 6,
        "motor_stopped": True,
    }
    saturated = bytearray(data)
    for offset in (4, 5, 6, 7, 8, 10):
        saturated[offset] = 255
    saturated[17] = 2
    result = parse_notification(bytes(saturated), profile=profile, dialect=dialect)
    assert all(
        result[key] == 100
        for key in ("back", "legs", "lumbar", "motor_part4", "motor_part5", "motor_part6")
    )
    assert result["motor_stopped"] is False


@pytest.mark.parametrize("profile", ("cb25", "f23", "kneading"))
@pytest.mark.parametrize("dialect", ("legacy", "star"))
def test_base_normal_massage_light_literal(profile: str, dialect: str) -> None:
    data = bytes.fromhex("a5 0b 00 00 01 2c 02 43 00 00 00 00 00 00 51 10 00 00 00 00")
    result = parse_notification(data, profile=profile, dialect=dialect)
    assert {
        k: result[k]
        for k in (
            "massage_time_raw",
            "massage_mode",
            "massage_head_level",
            "massage_foot_level",
            "massage_active",
            "light_mode",
            "light_brightness",
            "light_on",
            "light_color_index",
            "light_rgb",
            "light_rgb_mode",
        )
    } == {
        "massage_time_raw": 300,
        "massage_mode": 2,
        "massage_head_level": 2,
        "massage_foot_level": 3,
        "massage_active": True,
        "light_mode": 1,
        "light_brightness": 5,
        "light_on": True,
        "light_color_index": 1,
        "light_rgb": 0xFFFFFF,
        "light_rgb_mode": 0,
    }


@pytest.mark.parametrize(("vector_id", "raw", "profiles", "expected"), SUBCLASS_VECTORS)
@pytest.mark.parametrize("dialect", ("legacy", "star"))
def test_all_accepted_subclass_receive_vectors(
    vector_id: str,
    raw: str,
    profiles: tuple[str, ...],
    expected: dict[str, StateValue],
    dialect: str,
) -> None:
    for profile in profiles:
        result = parse_notification(bytes.fromhex(raw), profile=profile, dialect=dialect)
        if expected:
            assert {k: result[k] for k in expected} == expected, (vector_id, profile)
        else:
            assert result == {}, (vector_id, profile)


@pytest.mark.parametrize(("vector_id", "raw", "profile", "dialect", "expected"), ALARM_VECTORS)
def test_all_accepted_alarm_receive_vectors(
    vector_id: str,
    raw: str,
    profile: str,
    dialect: str,
    expected: dict[str, StateValue],
) -> None:
    assert parse_notification(bytes.fromhex(raw), profile=profile, dialect=dialect) == expected, (
        vector_id
    )
    if profile == "f23":
        assert (
            parse_notification(bytes.fromhex(raw), profile="kneading", dialect="star") == expected
        )


@pytest.mark.parametrize(("vector_id", "raw", "expected"), EQ_VECTORS)
@pytest.mark.parametrize("profile", ("f23", "kneading"))
@pytest.mark.parametrize("dialect", ("legacy", "star"))
def test_all_accepted_eq_receive_vectors(
    vector_id: str,
    raw: str,
    expected: dict[str, StateValue],
    profile: str,
    dialect: str,
) -> None:
    assert parse_notification(bytes.fromhex(raw), profile=profile, dialect=dialect) == expected, (
        vector_id
    )


@pytest.mark.parametrize(("vector_id", "raw", "profile"), SHORT_VECTORS)
def test_accepted_short_receive_vectors_hardened(vector_id: str, raw: str, profile: str) -> None:
    assert parse_notification(bytes.fromhex(raw), profile=profile, dialect="star") == {}, vector_id


@pytest.mark.parametrize(
    ("profile", "raw", "safe_length"),
    [
        ("cb25", "a5 0d 00 00 01 05 02 06 03 00 04 00 00 00 00 00 00 00", 18),
        ("f23", "a5 0b 00 00 01 2c 02 43 00 00 00 00 00 00 51 10 00 00 00 00", 20),
        ("cb25", "a5 0c 00 00 7f 01 17 3b dd 01 00 55 09 06 1e ee 00", 17),
        ("f23", "a5 0c 00 7f 06 07 06 00 03 03 dd 17 3b 01 55 ff ff ff 63 ff ff fe fd ee 02", 25),
        ("kneading", "a5 0e 00 00 00 00 00 00 00 00 00 02 00 a5 21 43 65 f0 81 a7 c8 02", 22),
        ("kneading", "a5 0f 00 01 01 01 01 2c", 8),
    ],
)
def test_every_frame_prefix_safe_without_partial_domain_update(
    profile: str, raw: str, safe_length: int
) -> None:
    complete = bytes.fromhex(raw)
    prior: dict[str, StateValue] = {"sonic_active": True, "alarm_1": True}
    for length in range(safe_length):
        assert (
            parse_notification(complete[:length], profile=profile, dialect="star", previous=prior)
            == {}
        )
        assert prior == {"sonic_active": True, "alarm_1": True}
    assert parse_notification(complete, profile=profile, dialect="star")


@pytest.mark.parametrize("profile", ("cb25", "f23", "kneading"))
def test_wrong_header_and_unknown_frame_do_not_publish(profile: str) -> None:
    for raw in (b"", b"\xa5", b"\xa4\x0d" + bytes(30), b"\xa5\xff" + bytes(30)):
        assert parse_notification(raw, profile=profile, dialect="star") == {}


def test_elevate_is_not_an_app_bed_class() -> None:
    """ELEVATE lifts use star_elevate, which assigns no semantic notification fields."""
    with pytest.raises(ValueError, match="Unknown AdjustableM5X5 profile"):
        parse_notification(bytes.fromhex("a50d") + bytes(16), profile="elevate", dialect="star")


def test_main_alarm_legacy_retains_previous_second_slot_and_unrelated_state() -> None:
    data = bytes.fromhex(ALARM_VECTORS[0][1])
    prior: dict[str, StateValue] = {
        "alarm_1": True,
        "alarm_1_details": {"hour": 18},
        "sonic_active": True,
    }
    updates = parse_notification(data, profile="cb25", dialect="legacy", previous=prior)
    assert "alarm_1" not in updates and "alarm_1_details" not in updates
    merged = {**prior, **updates}
    assert merged["alarm_1_details"] == {"hour": 18} and merged["sonic_active"] is True
    assert prior == {"alarm_1": True, "alarm_1_details": {"hour": 18}, "sonic_active": True}


def test_eq_updates_usb_preserving_other_sonic_fields_and_alarm_domains() -> None:
    prior: dict[str, StateValue] = {
        "sonic_active": True,
        "sonic_head_level": 9,
        "sonic_time_raw": 42,
        "alarm_0": False,
    }
    updates = parse_notification(
        bytes.fromhex(EQ_VECTORS[0][1]), profile="f23", dialect="legacy", previous=prior
    )
    assert not set(prior).intersection(updates)
    assert {**prior, **updates}["sonic_time_raw"] == 42
    assert updates["usb_on"] is True


def test_f23_advanced_alarm_rejects_main_shape_and_cb25_rejects_eq_kneading() -> None:
    assert (
        parse_notification(bytes.fromhex(ALARM_VECTORS[0][1]), profile="f23", dialect="star") == {}
    )
    assert parse_notification(bytes.fromhex(EQ_VECTORS[0][1]), profile="cb25", dialect="star") == {}
    assert (
        parse_notification(bytes.fromhex("a5 0f 00 01 01 01 01 2c"), profile="f23", dialect="star")
        == {}
    )


def test_changed_and_identical_frames_are_processed_without_debounce_drop() -> None:
    first = bytearray.fromhex("a5 0d 00 00 01 05 02 06 03 00 04 00 00 00 00 00 00 00")
    previous = parse_notification(bytes(first), profile="cb25", dialect="legacy")
    first[4] = 75
    changed = parse_notification(bytes(first), profile="cb25", dialect="legacy", previous=previous)
    assert changed["back"] == 75
    assert (
        parse_notification(bytes(first), profile="cb25", dialect="legacy", previous=changed)
        == changed
    )


@pytest.mark.parametrize(
    ("nibble", "rgb", "index"),
    [
        (0, 0xFFFFFF, 0),
        (1, 0xFFFFFF, 1),
        (2, 0xFF0000, 2),
        (3, 0xFFA500, 3),
        (4, 0xFFFF00, 4),
        (5, 0x00FF00, 5),
        (6, 0x0000FF, 6),
        (7, 0x800080, 7),
        (8, 0x800080, 7),
        (15, 0xFF0000, 2),
        (9, 0xFFFFFF, 1),
    ],
)
def test_palette_wire_index_and_direct_color_nearest_index(
    nibble: int, rgb: int, index: int
) -> None:
    data = bytearray.fromhex("a5 0b 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00")
    data[14] = nibble
    data[16:19] = rgb.to_bytes(3, "big")
    result = parse_notification(bytes(data), profile="cb25", dialect="star")
    assert (result["light_color_index"], result["light_rgb"], result["light_on"]) == (
        index,
        rgb,
        nibble > 0,
    )
    assert result["light_rgb_mode"] == int(nibble > 7)


def test_normal_or_vs_sonic_and_active_and_raw_extreme_levels() -> None:
    data = bytearray.fromhex("a5 0b 00 00 ff ff ff ff 0f ff ff 0f ff 00 ff ff 01 02 03 00")
    result = parse_notification(bytes(data), profile="kneading", dialect="legacy")
    assert result["massage_active"] is True and result["sonic_active"] is False
    assert (
        result["massage_head_level"],
        result["massage_foot_level"],
        result["massage_time_raw"],
    ) == (14, 14, 65535)
    assert (
        result["sonic_head_level"],
        result["sonic_foot_level"],
        result["sonic_frequency"],
        result["sonic_time_raw"],
    ) == (15, 0, 50, 65535)
    data[11] = 0
    result = parse_notification(bytes(data), profile="kneading", dialect="legacy")
    assert result["sonic_time_raw"] == 0 and result["sonic_frequency"] == 0


def test_all_raw_main_wake_enum_bytes_no_hour_or_repeat_clamps() -> None:
    raw = bytearray.fromhex("a5 0c 00 00 ff 00 ff ff 00 ff 00 ff 00 ff ff 00 ff")
    wake = {
        1: "zg",
        2: "lounge",
        3: "tv",
        4: "antisnore",
        5: "m1",
        6: "m2",
        7: "light",
        8: "massage",
        9: "flat",
    }
    for value in range(256):
        raw[5] = raw[12] = value
        result = parse_notification(bytes(raw), profile="cb25", dialect="star")
        for slot in (0, 1):
            assert result[f"alarm_{slot}_details"] == {
                "index": slot,
                "repeat_raw": 255,
                "wake": wake.get(value, "none"),
                "hour": 255,
                "minute": 255,
                "isOn": True,
            }


@pytest.mark.parametrize(
    ("field", "offset0", "offset1", "known", "fallback"),
    [
        (
            "preset",
            4,
            15,
            {0: "flat", 1: "zg", 2: "lounge", 3: "tv", 4: "antisnore", 5: "m1", 6: "m2"},
            "none",
        ),
        (
            "light",
            5,
            16,
            {
                0: "off",
                1: "onOrWhite",
                2: "red",
                3: "orange",
                4: "yellow",
                5: "green",
                6: "blue",
                7: "purple",
            },
            "none",
        ),
        (
            "sonic",
            6,
            17,
            {1: "normal1", 2: "normal2", 3: "normal3", 4: "sonic1", 5: "sonic2", 6: "sonic3"},
            "none",
        ),
        ("massage", 8, 19, {0: "off", 1: "intensity1", 2: "intensity2", 3: "intensity3"}, "none"),
        (
            "duration",
            9,
            20,
            {1: "duration10Min", 2: "duration20Min", 3: "duration30Min"},
            "duration10Min",
        ),
    ],
)
def test_all_raw_advanced_enum_bytes(
    field: str,
    offset0: int,
    offset1: int,
    known: dict[int, str],
    fallback: str,
) -> None:
    raw = bytearray(25)
    raw[:2] = b"\xa5\x0c"
    for value in range(256):
        raw[offset0] = raw[offset1] = value
        result = parse_notification(bytes(raw), profile="f23", dialect="legacy")
        for slot in (0, 1):
            details = result[f"alarm_{slot}_details"]
            assert isinstance(details, dict)
            assert details[field] == known.get(value, fallback)


def test_all_raw_music_eq_preset_frequency_and_sign_branches() -> None:
    alarm = bytearray(25)
    alarm[:2] = b"\xa5\x0c"
    eq = bytearray.fromhex(EQ_VECTORS[0][1])
    sonic = bytearray.fromhex(SUBCLASS_VECTORS[0][1])
    for value in range(256):
        alarm[7] = alarm[18] = value
        result = parse_notification(bytes(alarm), profile="f23", dialect="star")
        expected: StateValue = (
            "random" if value == 0 else "none" if value == 99 else {"music": value}
        )
        for slot in (0, 1):
            details = result[f"alarm_{slot}_details"]
            assert isinstance(details, dict)
            assert details["music"] == expected
        eq[13] = eq[18] = eq[21] = value
        eq_result = parse_notification(bytes(eq), profile="kneading", dialect="legacy")
        assert eq_result["eq_preset"] == {1: "Pop", 2: "Classical", 3: "Jazz"}.get(value, "None")
        for i, magnitude in enumerate((1, 2, 3, 4, 5, 6, 0, 15)):
            assert eq_result[f"eq_band_{i}"] == (magnitude if value & (1 << i) else -magnitude)
        assert eq_result["eq_low_frequency"] == (7 if value & 1 else -7)
        assert eq_result["eq_high_frequency"] == (10 if value & 128 else -10)
        sonic[12] = value
        sonic_result = parse_notification(bytes(sonic), profile="cb25", dialect="legacy")
        assert sonic_result["sonic_frequency"] == (30 if value == 5 else 40 if value == 9 else 50)


def test_invalid_profile_and_dialect_fail_instead_of_inferred_transport() -> None:
    with pytest.raises(ValueError, match="profile"):
        parse_notification(b"\xa5\x0b", profile="unknown", dialect="star")
    with pytest.raises(ValueError, match="dialect"):
        normal_packet(1, "unknown")


def test_all_raw_kneading_flags_and_usb_bit_have_distinct_boolean_rules() -> None:
    kneading = bytearray.fromhex("a5 0f 00 00 00 00 00 00")
    eq = bytearray.fromhex(EQ_VECTORS[0][1])
    for value in range(256):
        kneading[3] = kneading[4] = kneading[5] = value
        result = parse_notification(bytes(kneading), profile="kneading", dialect="legacy")
        assert result["kneading_on"] == (value == 1)
        assert result["kneading_demo"] == (value == 1)
        assert result["kneading_mode"] == min(value, 2)
        eq[11] = value
        assert parse_notification(bytes(eq), profile="f23", dialect="star")["usb_on"] == (
            (value & 2) == 2
        )
