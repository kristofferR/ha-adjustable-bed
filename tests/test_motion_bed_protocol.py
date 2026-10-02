"""Motion Bed accepted artifact vectors and pre-I/O domain validation."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import NotRequired, TypedDict, cast

import pytest

from custom_components.adjustable_bed import motion_bed_protocol as protocol


class VectorInputs(TypedDict):
    s: NotRequired[str]
    n: NotRequired[int]
    index: NotRequired[int]
    value: NotRequired[int]
    values: NotRequired[list[int]]
    mode: NotRequired[str]
    level: NotRequired[int]
    timer: NotRequired[str]
    module: NotRequired[str]
    address: NotRequired[str]
    year: NotRequired[int]
    month: NotRequired[int]
    day: NotRequired[int]
    hour: NotRequired[int]
    minute: NotRequired[int]
    second: NotRequired[int]
    weekday: NotRequired[int]
    page_type: NotRequired[str]
    flat: NotRequired[int | list[int]]
    side: NotRequired[int | list[int]]
    slot: NotRequired[int]
    fall: NotRequired[bool]
    kind: NotRequired[str]
    offset: NotRequired[int]
    enabled: NotRequired[bool]
    week_map: NotRequired[dict[str, bool]]
    massage: NotRequired[bool]
    music: NotRequired[str]
    gear: NotRequired[int]


class Vector(TypedDict):
    id: str
    function: str
    inputs: VectorInputs
    expected: str | list[str] | None


class Fixture(TypedDict):
    vectors: list[Vector]
    literal_commands: dict[str, str]


_FIXTURE = cast(
    Fixture,
    json.loads(
        Path(__file__)
        .with_name("fixtures")
        .joinpath("motion_bed_protocol_vectors.json")
        .read_text()
    ),
)


def _run(vector: Vector) -> str | list[str] | None:
    inputs = vector["inputs"]
    function = vector["function"]
    if function == "hx":
        return protocol.source_integer_hex(inputs["n"])
    if function == "hex_decode":
        decoded = protocol.decode_source_hex(inputs["s"])
        return decoded.hex().upper() if decoded is not None else None
    if function in ("addsum", "addcrc"):
        checksum = protocol.additive_checksum if function == "addsum" else protocol.with_crc
        result = checksum(bytes.fromhex(inputs["s"]))
    elif function == "pressure_live":
        result = protocol.build_pressure_live(inputs["index"], inputs["value"])
    elif function == "pressure_save":
        result = protocol.build_pressure_save(inputs["values"])
    elif function == "air_query":
        result = protocol.build_air_query(protocol.AirMode(int(inputs["mode"], 16)))
    elif function == "air_save":
        timer = protocol.AirTimer(int(inputs["timer"], 16)) if inputs["timer"] else None
        result = protocol.build_air_save(
            protocol.AirMode(int(inputs["mode"], 16)), inputs["level"], timer
        )
    elif function == "bind_module":
        result = protocol.build_module_bind(
            protocol.ModuleType(int(inputs["module"], 16)), inputs["address"]
        )
    elif function in ("clock", "thermal_clock"):
        timestamp = datetime(
            inputs["year"],
            inputs["month"],
            inputs["day"],
            inputs["hour"],
            inputs["minute"],
            inputs["second"],
        )
        clock = protocol.build_clock if function == "clock" else protocol.build_thermal_clock
        result = clock(timestamp, weekday=inputs["weekday"])
    elif function == "sleep_angles":
        result = protocol.build_sleep_angles(
            protocol.SleepPage(int(inputs["page_type"], 16)),
            cast(list[int], inputs["flat"]),
            cast(list[int], inputs["side"]),
        )
    elif function == "sleep_calibration":
        result = protocol.build_sleep_calibration(
            cast(int, inputs["flat"]), cast(int, inputs["side"])
        )
    elif function == "sleep_timer":
        result = protocol.build_sleep_timer(inputs["slot"], fall=inputs["fall"])
    elif function == "sleep_report":
        result = protocol.build_sleep_report(
            protocol.SleepReport(inputs["kind"]), offset=inputs["offset"]
        )
    elif function == "alarm":
        result = protocol.build_alarm(
            enabled=inputs["enabled"],
            hour=inputs["hour"],
            minute=inputs["minute"],
            weekdays={int(day): selected for day, selected in inputs["week_map"].items()},
            mode=protocol.AlarmMode(int(inputs["mode"], 16)),
            massage=inputs["massage"],
            sound=protocol.AlarmSound(int(inputs["music"], 16)),
            audio=True,
        )
    elif function == "thermal_timer":
        result = protocol.build_thermal_schedule(
            inputs["hour"],
            inputs["minute"],
            protocol.ThermalMode(int(inputs["mode"], 16)),
            inputs["gear"],
        )
    else:
        pytest.fail(f"Unbound accepted packet vector: {vector['id']}")
    return result.hex().upper()


@pytest.mark.parametrize("vector", _FIXTURE["vectors"], ids=lambda vector: vector["id"])
def test_accepted_packet_vector(vector: Vector) -> None:
    assert _run(vector) == vector["expected"]


@pytest.mark.parametrize("source_id, expected", _FIXTURE["literal_commands"].items())
def test_every_literal_source_callsite(source_id: str, expected: str) -> None:
    assert protocol.SOURCE_COMMANDS[source_id] == bytes.fromhex(expected)


def test_literal_catalogue_is_complete_and_immutable() -> None:
    assert len(protocol.SOURCE_COMMANDS) == 714
    assert set(protocol.SOURCE_COMMANDS) == set(_FIXTURE["literal_commands"])
    with pytest.raises(TypeError):
        protocol.SOURCE_COMMANDS["injected"] = b""  # type: ignore[index]


def test_checksums_preserve_minimal_width_and_full_crc_header() -> None:
    assert protocol.additive_checksum(b"\x00") == b"\x00"
    assert protocol.additive_checksum(b"\x01") == b"\x01\x01"
    assert protocol.additive_checksum(b"\xff\x01") == b"\xff\x01\x00\x01"
    assert protocol.with_crc(b"") == b"\xff\xff"
    assert protocol.with_crc(b"123456789")[-2:] == bytes.fromhex("374B")


@pytest.mark.parametrize("mode", list(protocol.AlarmMode))
@pytest.mark.parametrize("switch", list(protocol.AlarmSwitch))
def test_alarm_all_six_modes_and_uninitialized_modular_switch(
    mode: protocol.AlarmMode, switch: protocol.AlarmSwitch
) -> None:
    frame = protocol.build_alarm(
        enabled=False, hour=0, minute=0, weekdays={1: False}, mode=mode, switch=switch
    )
    assert frame[:8] == bytes.fromhex("FFFFFFFF01000213")
    assert frame[8:17] == bytes((switch, 0, 0, 0, 0, 1, mode, 0, 0))
    assert frame == protocol.additive_checksum(frame[:17])


@pytest.mark.parametrize(
    "module, source_id",
    [
        (protocol.ModuleType.MOTOR, "ChangeDeviceActivity:213"),
        (protocol.ModuleType.THERMAL, "ChangeDeviceActivity:219"),
        (protocol.ModuleType.AIR, "ChangeDeviceActivity:225"),
    ],
)
def test_module_delete_exact_source(module: protocol.ModuleType, source_id: str) -> None:
    assert protocol.build_module_delete(module) == protocol.SOURCE_COMMANDS[source_id]
    assert protocol.build_module_query() == protocol.SOURCE_COMMANDS["ChangeDeviceActivity:96"]


@pytest.mark.parametrize("index", range(9))
def test_thermal_slider_matches_every_source_entry(index: int) -> None:
    source_id = f"LengnuanFragment:279:thermal slider table index {index}"
    assert protocol.build_thermal_gear(index) == protocol.SOURCE_COMMANDS[source_id]


@pytest.mark.parametrize(
    "enabled, source_id", [(True, "LengnuanFragment:294"), (False, "LengnuanFragment:296")]
)
def test_thermal_timer_switch_matches_source(enabled: bool, source_id: str) -> None:
    assert protocol.build_thermal_timer_enabled(enabled) == protocol.SOURCE_COMMANDS[source_id]


@pytest.mark.parametrize(
    "track, checksum", [(1, "1C04"), (2, "1D04"), (3, "1E04"), (4, "1F04"), (5, "2004")]
)
def test_dynamic_audio_track(track: int, checksum: str) -> None:
    assert protocol.build_audio_track(track).hex().upper() == f"FFFFFFFF0100130B0{track}{checksum}"


@pytest.mark.parametrize(
    "volume, checksum", [(1, "1D04"), (2, "1E04"), (3, "1F04"), (4, "2004"), (5, "2104")]
)
def test_dynamic_audio_volume(volume: int, checksum: str) -> None:
    assert (
        protocol.build_audio_volume(volume).hex().upper() == f"FFFFFFFF0100140B0{volume}{checksum}"
    )


@pytest.mark.parametrize(
    "track, source_id",
    [
        (1, "AlarmActivity:296"),
        (2, "AlarmActivity:300"),
        (3, "AlarmActivity:304"),
        (4, "AlarmActivity:306"),
        (5, "AlarmActivity:308"),
    ],
)
def test_audio_previews_match_source(track: int, source_id: str) -> None:
    assert protocol.build_audio_track(track, preview=True) == protocol.SOURCE_COMMANDS[source_id]


def test_clock_derives_iso_weekday_and_keeps_thermal_order_separate() -> None:
    timestamp = datetime(2026, 10, 4, 23, 59, 58)
    assert protocol.build_clock(timestamp)[8:15] == bytes.fromhex("23595807261004")
    assert protocol.build_thermal_clock(timestamp)[10:17] == bytes.fromhex("26100423595807")
    with pytest.raises(ValueError, match="year"):
        protocol.build_clock(datetime(999, 1, 1))


def test_calibration_does_not_mask_or_pad_widened_numeric_fields() -> None:
    assert protocol.build_sleep_calibration(4096, 8193)[8:12] == bytes.fromhex("10001000")
    for flat, side in ((-1, 2), (256, 2), (1, -1), (1, 512)):
        with pytest.raises(ValueError):
            protocol.build_sleep_calibration(flat, side)


@pytest.mark.parametrize("channel, value", [(-1, 1), (12, 1), (1, -1), (1, 10), (True, 1)])
def test_pressure_invalid_domain_is_rejected(channel: int, value: int) -> None:
    with pytest.raises(ValueError):
        protocol.build_pressure_live(channel, value)


def test_pressure_whole_save_requires_all_twelve_channels() -> None:
    assert len(protocol.build_pressure_save([9] * 12)) == 47
    for values in ([0] * 11, [0] * 13, [10] * 12):
        with pytest.raises(ValueError):
            protocol.build_pressure_save(values)


def test_air_unset_timer_keeps_short_frame() -> None:
    assert len(protocol.build_air_save(protocol.AirMode.FULL, 1, None)) == 19
    assert (
        len(protocol.build_air_save(protocol.AirMode.FULL, 1, protocol.AirTimer.TEN_MINUTES)) == 20
    )
    for gear in (0, 9):
        with pytest.raises(ValueError):
            protocol.build_air_save(protocol.AirMode.FULL, gear, None)


def test_alarm_sound_requires_the_matching_audio_capability() -> None:
    for sound, audio in ((protocol.AlarmSound.MUSIC_1, False), (protocol.AlarmSound.BUZZER, True)):
        with pytest.raises(ValueError):
            protocol.build_alarm(
                enabled=True, hour=7, minute=0, weekdays={}, sound=sound, audio=audio
            )
    with pytest.raises(ValueError):
        protocol.build_alarm(enabled=True, hour=7, minute=0, weekdays={0: True})




@pytest.mark.parametrize(
    "build",
    [
        lambda: protocol.build_clock(datetime(2026, 1, 1), weekday=0),
        lambda: protocol.build_alarm(enabled=True, hour=24, minute=0, weekdays={}),
        lambda: protocol.build_alarm(enabled=True, hour=0, minute=60, weekdays={}),
        lambda: protocol.build_alarm(enabled=True, hour=0, minute=0, weekdays={}, mode=True),
        lambda: protocol.build_sleep_angles(protocol.SleepPage.FOUR_AXIS, [0] * 3, [0] * 4),
        lambda: protocol.build_sleep_angles(protocol.SleepPage.FOUR_AXIS, [256] * 4, [0] * 4),
        lambda: protocol.build_sleep_timer(9),
        lambda: protocol.build_sleep_timer(5, fall=True),
        lambda: protocol.build_sleep_report(protocol.SleepReport.DAY, offset=30),
        lambda: protocol.build_module_bind(protocol.ModuleType.MOTOR, "0123456789AB"),
        lambda: protocol.build_module_bind(protocol.ModuleType.MOTOR, "01:23:45:67:89:GG"),
        lambda: protocol.build_air_save(protocol.AirMode.FULL, 1, True),
        lambda: protocol.build_thermal_schedule(0, 0, protocol.ThermalMode.HEAT, 0),
        lambda: protocol.build_thermal_schedule(0, 0, protocol.ThermalMode.COOL, 5),
        lambda: protocol.build_thermal_gear(9),
        lambda: protocol.build_audio_track(0),
        lambda: protocol.build_audio_track(6),
        lambda: protocol.build_audio_volume(0),
        lambda: protocol.build_audio_volume(6),
    ],
)
def test_invalid_builder_domains_are_rejected_before_io(build: Callable[[], bytes]) -> None:
    with pytest.raises(ValueError):
        build()


@pytest.mark.parametrize("vector", [v for v in _FIXTURE["vectors"] if v["function"] == "addsum"], ids=lambda vector: vector["id"])
def test_existing_additive_helper_matches_all_accepted_vectors(vector: Vector) -> None:
    from custom_components.adjustable_bed.beds.solace import _with_additive_checksum
    assert _with_additive_checksum(bytes.fromhex(vector["inputs"]["s"])) == bytes.fromhex(vector["expected"])
