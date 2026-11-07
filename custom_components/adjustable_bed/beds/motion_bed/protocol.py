"""Typed packet construction for the Motion Bed application's BLE routes.

Field order and checksums come from com.sn.blackdianqi 1.24 (34). These
builders never write to Bluetooth or select a device/model. SOURCE_COMMANDS
retains source-callsite identity; the controller must gate each callsite by
its model, action and state predicate before sending it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import IntEnum, StrEnum
from types import MappingProxyType
from typing import Final

from ...codec.ff_frame import HEADER, alarm, bcd, clock, control, query, summed, with_crc, with_sum


class AlarmMode(IntEnum):
    """All six mode bytes understood by the application's alarm state."""

    ZERO_GRAVITY = 1
    MEMORY_1 = 2
    NO_ACTION = 3
    LEFT_ZERO_GRAVITY = 4
    RIGHT_ZERO_GRAVITY = 5
    COUPLED_ZERO_GRAVITY = 6


class AlarmSwitch(IntEnum):
    """The modular alarm starts at UNINITIALIZED until a state is loaded."""

    UNINITIALIZED = 0
    ENABLED = 1
    DISABLED = 0xA1


class AlarmSound(IntEnum):
    NONE = 0
    BUZZER = 1
    MUSIC_1 = 0x11
    MUSIC_2 = 0x12
    MUSIC_3 = 0x13
    MUSIC_4 = 0x14
    MUSIC_5 = 0x15


class ModuleType(IntEnum):
    MOTOR = 0x0A
    AIR = 0x0B
    THERMAL = 0x0C


class AirMode(IntEnum):
    FULL = 0x03
    BACK = 0x12
    NECK = 0x04
    WAIST = 0x05
    YOGA = 0x0C


class AirTimer(IntEnum):
    TEN_MINUTES = 0
    TWENTY_MINUTES = 1
    THIRTY_MINUTES = 2


class SleepPage(IntEnum):
    TWO_AXIS = 2
    THREE_AXIS = 3
    FOUR_AXIS = 4


class SleepReport(StrEnum):
    MONTH = "month"
    CURRENT = "real"
    TIMER = "timer"
    DAY = "day"


class ThermalMode(IntEnum):
    HEAT = 1
    COOL = 2


def _integer(value: int, minimum: int, maximum: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{field} must be an integer from {minimum} to {maximum}")
    return value


def _enum[E: IntEnum](enum_type: type[E], value: int) -> E:
    _integer(value, 0, 255, enum_type.__name__)
    return enum_type(value)


def source_integer_hex(value: int) -> str:
    """Reproduce covert10TO16, including its signed-Java-int conversion.

    This is an encoding reference, not a payload validator. Live builders reject
    negative domains and odd-width fields rather than masking or padding them.
    """
    _integer(value, -(1 << 31), (1 << 31) - 1, "value")
    if value == 0:
        return "00"
    digits: list[str] = []
    while value:
        quotient = abs(value) // 16 * (1 if value > 0 else -1)
        digit = value - quotient * 16
        digits.append(chr(digit + 48) if 0 <= digit < 10 else chr(digit + 55))
        value = quotient
    encoded = "".join(reversed(digits))
    return encoded.zfill(2)


def decode_source_hex(value: str) -> bytes | None:
    """StringToBytes accepts Java outer trim, but not internal whitespace."""
    value = value.upper().strip("".join(chr(i) for i in range(33)))
    if len(value) % 2 or re.fullmatch(r"[0-9A-F]*", value) is None:
        return None
    return bytes.fromhex(value)


def _number(value: int, field: str) -> bytes:
    _integer(value, 0, (1 << 31) - 1, field)
    encoded = decode_source_hex(source_integer_hex(value))
    if encoded is None:
        raise ValueError(f"{field} has an odd-width source encoding")
    return encoded


def _module(body: str) -> bytes:
    """A kind-FE/FF module frame from its hex body after the header."""
    return with_crc(HEADER + bytes.fromhex(body))


def _time(hour: int, minute: int) -> bytes:
    return bytes((bcd(_integer(hour, 0, 23, "hour")), bcd(_integer(minute, 0, 59, "minute"))))


def _date(timestamp: datetime, weekday: int | None, *, thermal: bool) -> bytes:
    # DateBean uses year.substring(2,4), so years before 1000 cannot serialize.
    _integer(timestamp.year, 1000, 9999, "year")
    week = timestamp.isoweekday() if weekday is None else _integer(weekday, 1, 7, "weekday")
    date = bytes((bcd(timestamp.year % 100), bcd(timestamp.month), bcd(timestamp.day)))
    time = _time(timestamp.hour, timestamp.minute) + bytes((bcd(timestamp.second),))
    return date + time + bytes((week,)) if thermal else time + bytes((week,)) + date


def build_clock(timestamp: datetime, *, weekday: int | None = None) -> bytes:
    _integer(timestamp.year, 1000, 9999, "year")
    week = timestamp.isoweekday() if weekday is None else _integer(weekday, 1, 7, "weekday")
    return clock(timestamp, week)


def build_alarm(
    *,
    enabled: bool,
    hour: int,
    minute: int,
    weekdays: Mapping[int, bool],
    mode: AlarmMode = AlarmMode.NO_ACTION,
    massage: bool = False,
    sound: AlarmSound = AlarmSound.NONE,
    switch: AlarmSwitch | None = None,
    audio: bool = False,
) -> bytes:
    """Preserve map presence as repeat even when every weekday is disabled."""
    if not all(isinstance(value, bool) for value in (enabled, massage, audio)):
        raise ValueError("alarm switches must be Boolean")
    mask = 0
    for day, selected in weekdays.items():
        _integer(day, 1, 7, "weekday")
        if not isinstance(selected, bool):
            raise ValueError("weekday selections must be Boolean")
        if selected:
            mask |= 1 << day
    mode = _enum(AlarmMode, mode)
    sound = _enum(AlarmSound, sound)
    if audio and sound == AlarmSound.BUZZER or not audio and sound.value >= 0x11:
        raise ValueError("alarm sound is unavailable for this audio capability")
    code = (
        _enum(AlarmSwitch, switch)
        if switch is not None
        else AlarmSwitch.ENABLED
        if enabled
        else AlarmSwitch.DISABLED
    )
    _integer(hour, 0, 23, "hour")
    _integer(minute, 0, 59, "minute")
    return alarm(
        switch=code,
        hour=hour,
        minute=minute,
        weekday_mask=mask,
        repeat=bool(weekdays),
        mode=mode,
        massage=massage,
        sound=sound,
    )


def build_sleep_angles(page: SleepPage, flat: Sequence[int], side: Sequence[int]) -> bytes:
    page = _enum(SleepPage, page)
    if len(flat) != 4 or len(side) != 4:
        raise ValueError("flat and side require four raw position values")
    values = [_integer(value, 0, 255, "raw position") for value in (*flat, *side)]
    if page == SleepPage.TWO_AXIS:
        for index in (0, 3, 4, 7):
            values[index] = 0
    elif page == SleepPage.THREE_AXIS:
        values[0] = values[4] = 0
    return with_sum(bytes.fromhex("FFFFFFFF02001012") + bytes(values))


def build_sleep_calibration(flat: int, side: int) -> bytes:
    _integer(side, 0, (1 << 31) - 1, "side")
    return with_sum(
        bytes.fromhex("FFFFFFFF0200120C") + _number(flat, "flat") + _number(side // 2, "side / 2")
    )


def build_sleep_timer(slot: int, *, fall: bool = False) -> bytes:
    if not isinstance(fall, bool):
        raise ValueError("fall must be Boolean")
    _integer(slot, 0, 4 if fall else 8, "slot")
    prefix = "FFFFFFFF0200150B" if fall else "FFFFFFFF02000D0B"
    return with_sum(bytes.fromhex(prefix) + bytes((slot,)))


def build_sleep_report(kind: SleepReport, *, offset: int = 0) -> bytes:
    kind = SleepReport(kind)
    _integer(offset, 0, 29, "offset")
    bodies = {
        SleepReport.MONTH: "FFFFFFFF0200030B1E",
        SleepReport.CURRENT: "FFFFFFFF0200030B01",
        SleepReport.TIMER: "FFFFFFFF0200160B00",
    }
    if kind == SleepReport.DAY:
        return with_sum(bytes.fromhex("FFFFFFFF0200130B") + bytes((offset,)))
    return with_sum(bytes.fromhex(bodies[kind]))


def build_module_bind(module: ModuleType, address: str) -> bytes:
    module = _enum(ModuleType, module)
    if re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", address) is None:
        raise ValueError("module address must contain six colon-separated octets")
    return with_sum(
        bytes.fromhex("FFFFFFFF01002814")
        + bytes((module,))
        + bytes.fromhex(address.replace(":", ""))
        + bytes(3)
    )


def build_module_delete(module: ModuleType) -> bytes:
    return with_sum(
        bytes.fromhex("FFFFFFFF01002814")
        + bytes((_enum(ModuleType, module),))
        + bytes(7)
        + bytes((1, 0))
    )


def build_module_query() -> bytes:
    return with_sum(bytes.fromhex("FFFFFFFF010026140F000000000000000000"))


def build_pressure_live(channel: int, value: int) -> bytes:
    _integer(channel, 0, 11, "channel")
    _integer(value, 0, 9, "pressure")
    return with_crc(
        bytes.fromhex("FFFFFFFFFF0F0117")
        + (1 << channel).to_bytes(2, "little")
        + bytes((value * 10, 0, 0))
    )


def build_pressure_save(values: Sequence[int]) -> bytes:
    if len(values) != 12:
        raise ValueError("pressure save requires twelve channels")
    body = bytearray.fromhex("FFFFFFFFFF2F030500")
    for value in values:
        body.extend((1, _integer(value, 0, 9, "pressure") * 10, 0))
    return with_crc(bytes(body))


def build_air_query(mode: AirMode) -> bytes:
    return with_crc(bytes.fromhex("FFFFFFFFFF0D020800") + bytes((_enum(AirMode, mode), 0)))


def build_air_save(mode: AirMode, gear: int, timer: AirTimer | None) -> bytes:
    _integer(gear, 1, 8, "air gear")
    timer_bytes = b"" if timer is None else bytes((_enum(AirTimer, timer),))
    return with_crc(
        bytes.fromhex("FFFFFFFFFF14030E00")
        + bytes((_enum(AirMode, mode), gear * 10, 0, 0, 0))
        + timer_bytes
        + bytes(3)
    )


def build_thermal_clock(timestamp: datetime, *, weekday: int | None = None) -> bytes:
    return with_crc(
        bytes.fromhex("FFFFFFFFFE1400070000") + _date(timestamp, weekday, thermal=True) + b"\x00"
    )


def build_thermal_schedule(hour: int, minute: int, mode: ThermalMode, gear: int) -> bytes:
    _integer(gear, 1, 4, "thermal gear")
    return with_crc(
        bytes.fromhex("FFFFFFFFFE1400020000")
        + _time(hour, minute)
        + bytes((0, _enum(ThermalMode, mode), gear, 0, 0, 0))
    )


def build_thermal_gear(index: int) -> bytes:
    """Nine source slider entries: cool4..1, off, heat1..4 (not degrees)."""
    _integer(index, 0, 8, "thermal index")
    command = 5 if index < 4 else 6 if index == 4 else 4
    gear = 4 - index if index < 4 else 0 if index == 4 else index - 4
    return with_crc(bytes.fromhex("FFFFFFFFFE1000") + bytes((command, 0, 0, gear, 0, 0, 0xAA)))


def build_thermal_timer_enabled(enabled: bool) -> bytes:
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be Boolean")
    return with_crc(bytes.fromhex("FFFFFFFFFE1000030000") + bytes((enabled, 0, 0, 0xAA)))


def build_audio_track(track: int, *, preview: bool = False) -> bytes:
    _integer(track, 1, 5, "track")
    if not isinstance(preview, bool):
        raise ValueError("preview must be Boolean")
    return summed(0x01, 0x13, bytes((track + (0x80 if preview else 0),)))


def build_audio_volume(volume: int) -> bytes:
    return summed(0x01, 0x14, bytes((_integer(volume, 1, 5, "volume"),)))




SOURCE_COMMANDS: Final[Mapping[str, bytes]] = MappingProxyType(
    {
        "AlarmActivity:296": summed(0x01, 0x13, bytes.fromhex("81")),
        "AlarmActivity:300": summed(0x01, 0x13, bytes.fromhex("82")),
        "AlarmActivity:304": summed(0x01, 0x13, bytes.fromhex("83")),
        "AlarmActivity:306": summed(0x01, 0x13, bytes.fromhex("84")),
        "AlarmActivity:308": summed(0x01, 0x13, bytes.fromhex("85")),
        "AlarmActivity:314": summed(0x01, 0x13, bytes.fromhex("00")),
        "AnmoSetActivity:260": _module("FF0D0208000300"),
        "ChangeDeviceActivity:96": summed(0x01, 0x26, bytes.fromhex("0F000000000000000000")),
        "ChangeDeviceActivity:213": summed(0x01, 0x28, bytes.fromhex("0A000000000000000100")),
        "ChangeDeviceActivity:219": summed(0x01, 0x28, bytes.fromhex("0C000000000000000100")),
        "ChangeDeviceActivity:225": summed(0x01, 0x28, bytes.fromhex("0B000000000000000100")),
        "ConnectMcuActivity:311": summed(0x01, 0x26, bytes.fromhex("0F000000000000000000")),
        "DianDongSetActivity:270": control(0x15),
        "DianDongSetActivity:275": control(0x14),
        "DianDongSetActivity:281": control(0x11),
        "DianDongSetActivity:286": control(0x10),
        "DianDongSetActivity:292": control(0x13),
        "DianDongSetActivity:297": control(0x12),
        "DianDongSetActivity:385:level 0": control(0x23),
        "DianDongSetActivity:385:level 1": control(0x23, arg=0x01),
        "DianDongSetActivity:385:level 2": control(0x23, arg=0x02),
        "DianDongSetActivity:385:level 3": control(0x23, arg=0x03),
        "DianDongSetActivity:385:level 4": control(0x23, arg=0x04),
        "DianDongSetActivity:385:level 5": control(0x23, arg=0x05),
        "DianDongSetActivity:385:level 6": control(0x23, arg=0x06),
        "DianDongSetActivity:385:level 7": control(0x23, arg=0x07),
        "DianDongSetActivity:385:level 8": control(0x23, arg=0x08),
        "DianDongSetActivity:385:level 9": control(0x23, arg=0x09),
        "DianDongSetActivity:385:level 10": control(0x23, arg=0x0A),
        "DianDongSetActivity:490": summed(0x01, 0x13, bytes.fromhex("81")),
        "DianDongSetActivity:494": summed(0x01, 0x13, bytes.fromhex("82")),
        "DianDongSetActivity:498": summed(0x01, 0x13, bytes.fromhex("83")),
        "DianDongSetActivity:500": summed(0x01, 0x13, bytes.fromhex("84")),
        "DianDongSetActivity:502": summed(0x01, 0x13, bytes.fromhex("85")),
        "DianDongSetActivity:508": summed(0x01, 0x13, bytes.fromhex("00")),
        "DianDongSetActivity:515": summed(0x01, 0x1C, bytes.fromhex("01000000000000000000")),
        "DianDongSetActivity:522": summed(0x01, 0x1C, bytes.fromhex("03000000000000000000")),
        "DianDongSetActivity:525": control(0x19),
        "DianDongSetActivity:535": control(0x1B),
        "DianDongSetActivity:545": control(0x1A),
        "DianDongSetActivity:557": control(0x1C),
        "DianDongSetActivity:559": control(0x16),
        "DianDongSetActivity:569": control(0x1C),
        "DianDongSetActivity:571": control(0x17),
        "DianDongSetActivity:581": control(0x1C),
        "DianDongSetActivity:583": control(0x18),
        "DianDongSetActivity:629": summed(0x01, 0x1C, bytes.fromhex("02000000000000000000")),
        "DianDongSetActivity:631": summed(0x01, 0x1C, bytes.fromhex("04000000000000000000")),
        "HomeActivity:142": summed(0x01, 0x0A, bytes.fromhex("0F")),
        "HomeActivity:311": summed(0x01, 0x0A, bytes.fromhex("0F")),
        "HomeActivity:321": summed(0x02, 0x0E, bytes.fromhex("00")),
        "HomeActivity:455": control(0x23, arg=0xFF, group=0x05),
        "HomeActivity:463": summed(0x02, 0x0A),
        "HomeActivity:465": summed(0x02, 0x0E, bytes.fromhex("00")),
        "MainMcuActivity:182": summed(0x01, 0x26, bytes.fromhex("0F000000000000000000")),
        "PressSetActivity:224": _module("FF0B020400"),
        "Setting2Activity:238": summed(0x01, 0x26, bytes.fromhex("0F000000000000000000")),
        "SleepAdjustActivity:102": summed(0x02, 0x0A),
        "SleepAdjustActivity:165": summed(0x02, 0x10, bytes.fromhex("00")),
        "SleepAdjustActivity:243:caller line 188": control(0x03, arg=0x02),
        "SleepAdjustActivity:243:caller line 204": control(0x01, arg=0x02),
        "SleepAdjustActivity:243:caller line 218": control(0x06, arg=0x02),
        "SleepAdjustActivity:243:caller line 232": control(0x0D, arg=0x02),
        "SleepAdjustActivity:251": control(0x00),
        "SleepAdjustActivity:255": summed(0x02, 0x0F, bytes.fromhex("00")),
        "SleepAdjustActivity:261:caller line 181": control(0x04, arg=0x02),
        "SleepAdjustActivity:261:caller line 197": control(0x02, arg=0x02),
        "SleepAdjustActivity:261:caller line 211": control(0x07, arg=0x02),
        "SleepAdjustActivity:261:caller line 225": control(0x0E, arg=0x02),
        "SleepAdjustActivity:269": control(0x00),
        "SleepAdjustActivity:273": summed(0x02, 0x0F, bytes.fromhex("00")),
        "SleepAdjustActivity:281": summed(0x02, 0x0F, bytes.fromhex("00")),
        "SleepAdjustActivity:289": summed(0x02, 0x0F, bytes.fromhex("00")),
        "SleepAdjustActivity:411": summed(0x02, 0x0F, bytes.fromhex("00")),
        "SleepDataEntryActivity:105": summed(0x02, 0x0A),
        "SleepDataEntryActivity:126": summed(0x02, 0x0A),
        "SleepDataEntryActivity:189": control(0x08, arg=0x02),
        "SleepDataEntryActivity:202": summed(0x02, 0x0A),
        "SleepDataEntryActivity:248": summed(0x02, 0x09, bytes.fromhex("010000")),
        "SleepDataEntryActivity:253": summed(0x02, 0x09, bytes.fromhex("020000")),
        "SleepDataEntryActivity:268": summed(0x02, 0x12, bytes.fromhex("0A46")),
        "SleepDataEntryActivity:293": summed(0x02, 0x09, bytes.fromhex("0300000000")),
        "SleepDayReportActivity:88": summed(0x02, 0x0A),
        "AnmoFragment:88": summed(0x01, 0x09, bytes.fromhex("00")),
        "AnmoFragment:90": summed(0x01, 0x09, bytes.fromhex("01")),
        "AnmoFragment:100": control(0x15),
        "AnmoFragment:105": control(0x14),
        "AnmoFragment:111": control(0x11),
        "AnmoFragment:116": control(0x10),
        "AnmoFragment:122": control(0x13),
        "AnmoFragment:127": control(0x12),
        "AnmoFragment:165": control(0x1C),
        "AnmoFragment:167": control(0x16),
        "AnmoFragment:177": control(0x1C),
        "AnmoFragment:179": control(0x17),
        "AnmoFragment:189": control(0x1C),
        "AnmoFragment:191": control(0x18),
        "DengguangFragment:99": summed(0x01, 0x09, bytes.fromhex("00")),
        "DengguangFragment:101": summed(0x01, 0x09, bytes.fromhex("01")),
        "DengguangFragment:176:level 0": control(0x23),
        "DengguangFragment:176:level 1": control(0x23, arg=0x01),
        "DengguangFragment:176:level 2": control(0x23, arg=0x02),
        "DengguangFragment:176:level 3": control(0x23, arg=0x03),
        "DengguangFragment:176:level 4": control(0x23, arg=0x04),
        "DengguangFragment:176:level 5": control(0x23, arg=0x05),
        "DengguangFragment:176:level 6": control(0x23, arg=0x06),
        "DengguangFragment:176:level 7": control(0x23, arg=0x07),
        "DengguangFragment:176:level 8": control(0x23, arg=0x08),
        "DengguangFragment:176:level 9": control(0x23, arg=0x09),
        "DengguangFragment:176:level 10": control(0x23, arg=0x0A),
        "DengguangFragment:181": control(0x23, arg=0xFF, group=0x05),
        "DengguangFragment:208": control(0x19),
        "DengguangFragment:218": control(0x1B),
        "DengguangFragment:228": control(0x1A),
        "DiandongFragment:135": summed(0x01, 0x0C, bytes.fromhex("0F")),
        "DiandongFragment:319": summed(0x01, 0x2A, bytes.fromhex("00000000000000000000")),
        "DiandongFragment:349": control(0x00),
        "DiandongFragment:387": control(0x00),
        "DiandongFragment:392": control(0x04),
        "DiandongFragment:412": control(0x00),
        "DiandongFragment:417": control(0x07),
        "DiandongFragment:452": control(0x4A),
        "DiandongFragment:454": control(0x4B),
        "DiandongFragment:464": control(0x1C, arg=0x01),
        "DiandongFragment:466": control(0x1C),
        "DiandongFragment:566": control(0x08),
        "DiandongFragment:578": control(0x0A, arg=0xA1),
        "DiandongFragment:580": control(0x0A),
        "DiandongFragment:594": control(0x0B, arg=0xB1),
        "DiandongFragment:596": control(0x0B),
        "DiandongFragment:610": control(0x05, arg=0x51),
        "DiandongFragment:612": control(0x05),
        "DiandongFragment:626": control(0x09, arg=0x91),
        "DiandongFragment:628": control(0x09),
        "DiandongFragment:636": control(0x6A),
        "DiandongFragment:648": control(0x0F, arg=0xF1),
        "DiandongFragment:650": control(0x0F),
        "DiandongFragment:663": control(0x09, arg=0x9F),
        "DiandongFragment:665": control(0x09, arg=0x90),
        "DiandongFragment:672": control(0x0F, arg=0xFF),
        "DiandongFragment:674": control(0x0F, arg=0xF0),
        "DiandongFragment:681": control(0x05, arg=0x5F),
        "DiandongFragment:683": control(0x05, arg=0x50),
        "DiandongFragment:690": control(0x0B, arg=0xBF),
        "DiandongFragment:692": control(0x0B, arg=0xB0),
        "DiandongFragment:699": control(0x0A, arg=0xAF),
        "DiandongFragment:701": control(0x0A, arg=0xA0),
        "KuaijieK11Fragment:50": summed(0x01, 0x09, bytes.fromhex("00")),
        "KuaijieK11Fragment:52": summed(0x01, 0x09, bytes.fromhex("01")),
        "KuaijieK11Fragment:93": control(0x00),
        "KuaijieK11Fragment:136": control(0x0B, arg=0xBF),
        "KuaijieK11Fragment:138": control(0x0B, arg=0xB0),
        "KuaijieK11Fragment:145": control(0x0A, arg=0xAF),
        "KuaijieK11Fragment:147": control(0x0A, arg=0xA0),
        "KuaijieK11Fragment:203": query(0x28, 0x09),
        "KuaijieK11Fragment:205": query(0x31, 0x09),
        "KuaijieK11Fragment:207": query(0x16, 0x09),
        "KuaijieK11Fragment:209": query(0x1F, 0x09),
        "KuaijieK11Fragment:211": query(0x3A, 0x09),
        "KuaijieK11Fragment:226": control(0x08),
        "KuaijieK11Fragment:232": control(0x29),
        "KuaijieK11Fragment:243": control(0x0A, arg=0xA1),
        "KuaijieK11Fragment:255": control(0x0B, arg=0xB1),
        "KuaijieK11Fragment:268": control(0x05, arg=0x51),
        "KuaijieK11Fragment:270": control(0x05),
        "KuaijieK11Fragment:285": control(0x09, arg=0x91),
        "KuaijieK11Fragment:287": control(0x09),
        "KuaijieK11Fragment:295": control(0x28),
        "KuaijieK11Fragment:301": control(0x2A),
        "KuaijieK11Fragment:307": control(0x21),
        "KuaijieK11Fragment:313": control(0x22),
        "KuaijieK11Fragment:326": control(0x0F, arg=0xF1),
        "KuaijieK11Fragment:328": control(0x0F),
        "KuaijieK11Fragment:341": control(0x09, arg=0x9F),
        "KuaijieK11Fragment:343": control(0x09, arg=0x90),
        "KuaijieK11Fragment:350": control(0x0F, arg=0xFF),
        "KuaijieK11Fragment:352": control(0x0F, arg=0xF0),
        "KuaijieK11Fragment:359": control(0x05, arg=0x5F),
        "KuaijieK11Fragment:361": control(0x05, arg=0x50),
        "KuaijieK1Fragment:50": summed(0x01, 0x09, bytes.fromhex("00")),
        "KuaijieK1Fragment:52": summed(0x01, 0x09, bytes.fromhex("01")),
        "KuaijieK1Fragment:93": control(0x00),
        "KuaijieK1Fragment:136": control(0x0B, arg=0xBF),
        "KuaijieK1Fragment:138": control(0x0B, arg=0xB0),
        "KuaijieK1Fragment:145": control(0x0A, arg=0xAF),
        "KuaijieK1Fragment:147": control(0x0A, arg=0xA0),
        "KuaijieK1Fragment:203": query(0x28, 0x09),
        "KuaijieK1Fragment:205": query(0x31, 0x09),
        "KuaijieK1Fragment:207": query(0x16, 0x09),
        "KuaijieK1Fragment:209": query(0x1F, 0x09),
        "KuaijieK1Fragment:211": query(0x3A, 0x09),
        "KuaijieK1Fragment:226": control(0x08),
        "KuaijieK1Fragment:237": control(0x0A, arg=0xA1),
        "KuaijieK1Fragment:249": control(0x0B, arg=0xB1),
        "KuaijieK1Fragment:262": control(0x05, arg=0x51),
        "KuaijieK1Fragment:264": control(0x05),
        "KuaijieK1Fragment:279": control(0x09, arg=0x91),
        "KuaijieK1Fragment:281": control(0x09),
        "KuaijieK1Fragment:289": control(0xE4, group=0x05),
        "KuaijieK1Fragment:295": control(0x28),
        "KuaijieK1Fragment:301": control(0x29),
        "KuaijieK1Fragment:307": control(0xE6, group=0x05),
        "KuaijieK1Fragment:313": control(0x4E),
        "KuaijieK1Fragment:326": control(0x0F, arg=0xF1),
        "KuaijieK1Fragment:328": control(0x0F),
        "KuaijieK1Fragment:341": control(0x09, arg=0x9F),
        "KuaijieK1Fragment:343": control(0x09, arg=0x90),
        "KuaijieK1Fragment:350": control(0x0F, arg=0xFF),
        "KuaijieK1Fragment:352": control(0x0F, arg=0xF0),
        "KuaijieK1Fragment:359": control(0x05, arg=0x5F),
        "KuaijieK1Fragment:361": control(0x05, arg=0x50),
        "KuaijieK2Fragment:46": summed(0x01, 0x09, bytes.fromhex("00")),
        "KuaijieK2Fragment:48": summed(0x01, 0x09, bytes.fromhex("01")),
        "KuaijieK2Fragment:89": control(0x00),
        "KuaijieK2Fragment:127": control(0x0B, arg=0xBF),
        "KuaijieK2Fragment:129": control(0x0B, arg=0xB0),
        "KuaijieK2Fragment:136": control(0x0A, arg=0xAF),
        "KuaijieK2Fragment:138": control(0x0A, arg=0xA0),
        "KuaijieK2Fragment:213": query(0x28, 0x03),
        "KuaijieK2Fragment:215": query(0x30, 0x03),
        "KuaijieK2Fragment:217": query(0x18, 0x03),
        "KuaijieK2Fragment:219": query(0x20, 0x03),
        "KuaijieK2Fragment:221": query(0x38, 0x03),
        "KuaijieK2Fragment:223": query(0x28, 0x09),
        "KuaijieK2Fragment:225": query(0x31, 0x09),
        "KuaijieK2Fragment:227": query(0x16, 0x09),
        "KuaijieK2Fragment:229": query(0x1F, 0x09),
        "KuaijieK2Fragment:231": query(0x3A, 0x09),
        "KuaijieK2Fragment:247": control(0x08),
        "KuaijieK2Fragment:258": control(0x0A, arg=0xA1),
        "KuaijieK2Fragment:270": control(0x0B, arg=0xB1),
        "KuaijieK2Fragment:283": control(0x05, arg=0x51),
        "KuaijieK2Fragment:285": control(0x05),
        "KuaijieK2Fragment:300": control(0x09, arg=0x91),
        "KuaijieK2Fragment:302": control(0x09),
        "KuaijieK2Fragment:317": control(0x0F, arg=0xF1),
        "KuaijieK2Fragment:319": control(0x0F),
        "KuaijieK2Fragment:332": control(0x09, arg=0x9F),
        "KuaijieK2Fragment:334": control(0x09, arg=0x90),
        "KuaijieK2Fragment:341": control(0x0F, arg=0xFF),
        "KuaijieK2Fragment:343": control(0x0F, arg=0xF0),
        "KuaijieK2Fragment:350": control(0x05, arg=0x5F),
        "KuaijieK2Fragment:352": control(0x05, arg=0x50),
        "KuaijieK2MFragment:64": summed(0x01, 0x09, bytes.fromhex("00")),
        "KuaijieK2MFragment:66": summed(0x01, 0x09, bytes.fromhex("01")),
        "KuaijieK2MFragment:107": control(0x00),
        "KuaijieK2MFragment:166": control(0x0B, arg=0xBF),
        "KuaijieK2MFragment:168": control(0x0B, arg=0xB0),
        "KuaijieK2MFragment:175": control(0x0A, arg=0xAF),
        "KuaijieK2MFragment:177": control(0x0A, arg=0xA0),
        "KuaijieK2MFragment:266": query(0x28, 0x03),
        "KuaijieK2MFragment:268": query(0x30, 0x03),
        "KuaijieK2MFragment:270": query(0x18, 0x03),
        "KuaijieK2MFragment:272": query(0x20, 0x03),
        "KuaijieK2MFragment:274": query(0x38, 0x03),
        "KuaijieK2MFragment:276": query(0x28, 0x09),
        "KuaijieK2MFragment:278": query(0x31, 0x09),
        "KuaijieK2MFragment:280": query(0x16, 0x09),
        "KuaijieK2MFragment:282": query(0x1F, 0x09),
        "KuaijieK2MFragment:284": query(0x3A, 0x09),
        "KuaijieK2MFragment:300": control(0x6A),
        "KuaijieK2MFragment:306": control(0x08),
        "KuaijieK2MFragment:317": control(0x0A, arg=0xA1),
        "KuaijieK2MFragment:329": control(0x0B, arg=0xB1),
        "KuaijieK2MFragment:342": control(0x05, arg=0x51),
        "KuaijieK2MFragment:344": control(0x05),
        "KuaijieK2MFragment:359": control(0x09, arg=0x91),
        "KuaijieK2MFragment:361": control(0x09),
        "KuaijieK2MFragment:373": summed(0x01, 0x13, bytes.fromhex("FF")),
        "KuaijieK2MFragment:375": summed(0x01, 0x13, bytes.fromhex("00")),
        "KuaijieK2MFragment:389": control(0x0F, arg=0xF1),
        "KuaijieK2MFragment:391": control(0x0F),
        "KuaijieK2MFragment:404": control(0x09, arg=0x9F),
        "KuaijieK2MFragment:406": control(0x09, arg=0x90),
        "KuaijieK2MFragment:413": control(0x0F, arg=0xFF),
        "KuaijieK2MFragment:415": control(0x0F, arg=0xF0),
        "KuaijieK2MFragment:422": control(0x05, arg=0x5F),
        "KuaijieK2MFragment:424": control(0x05, arg=0x50),
        "KuaijieK2MFragment:457": summed(0x01, 0x13, bytes.fromhex("00")),
        "KuaijieK2MFragment:466": summed(0x01, 0x15, bytes.fromhex("00")),
        "KuaijieK3Fragment:46": summed(0x01, 0x09, bytes.fromhex("00")),
        "KuaijieK3Fragment:48": summed(0x01, 0x09, bytes.fromhex("01")),
        "KuaijieK3Fragment:85": control(0x00),
        "KuaijieK3Fragment:125": control(0x0B, arg=0xBF),
        "KuaijieK3Fragment:127": control(0x0B, arg=0xB0),
        "KuaijieK3Fragment:134": control(0x0A, arg=0xAF),
        "KuaijieK3Fragment:136": control(0x0A, arg=0xA0),
        "KuaijieK3Fragment:183": query(0x24, 0x03),
        "KuaijieK3Fragment:185": query(0x2C, 0x03),
        "KuaijieK3Fragment:187": query(0x14, 0x03),
        "KuaijieK3Fragment:189": query(0x1C, 0x03),
        "KuaijieK3Fragment:204": control(0x2E),
        "KuaijieK3Fragment:210": control(0x0F, arg=0xF1),
        "KuaijieK3Fragment:221": control(0x0A, arg=0xA1),
        "KuaijieK3Fragment:233": control(0x0B, arg=0xB1),
        "KuaijieK3Fragment:246": control(0x05, arg=0x51),
        "KuaijieK3Fragment:248": control(0x05),
        "KuaijieK3Fragment:263": control(0x09, arg=0x91),
        "KuaijieK3Fragment:265": control(0x09),
        "KuaijieK3Fragment:273": control(0x07),
        "KuaijieK3Fragment:279": control(0x06),
        "KuaijieK3Fragment:290": control(0x09, arg=0x9F),
        "KuaijieK3Fragment:292": control(0x09, arg=0x90),
        "KuaijieK3Fragment:299": control(0x05, arg=0x5F),
        "KuaijieK3Fragment:301": control(0x05, arg=0x50),
        "KuaijieK4Fragment:55": summed(0x01, 0x09, bytes.fromhex("00")),
        "KuaijieK4Fragment:57": summed(0x01, 0x09, bytes.fromhex("01")),
        "KuaijieK4Fragment:99": control(0x00),
        "KuaijieK4Fragment:182": query(0x64, 0x09),
        "KuaijieK4Fragment:184": query(0x6D, 0x09),
        "KuaijieK4Fragment:186": query(0x76, 0x09),
        "KuaijieK4Fragment:188": query(0x7F, 0x09),
        "KuaijieK4Fragment:211": control(0x39),
        "KuaijieK4Fragment:217": control(0x3A),
        "KuaijieK4Fragment:229": control(0x31, arg=0x11),
        "KuaijieK4Fragment:231": control(0x31),
        "KuaijieK4Fragment:245": control(0x32, arg=0x21),
        "KuaijieK4Fragment:247": control(0x32),
        "KuaijieK4Fragment:261": control(0x33, arg=0x31),
        "KuaijieK4Fragment:263": control(0x33),
        "KuaijieK4Fragment:277": control(0x34, arg=0x41),
        "KuaijieK4Fragment:279": control(0x34),
        "KuaijieK4Fragment:295": control(0x3B),
        "KuaijieK4Fragment:301": control(0x3C),
        "KuaijieK4Fragment:307": control(0x3D),
        "KuaijieK4Fragment:332": control(0x31, arg=0x1F),
        "KuaijieK4Fragment:334": control(0x31, arg=0x10),
        "KuaijieK4Fragment:341": control(0x32, arg=0x2F),
        "KuaijieK4Fragment:343": control(0x32, arg=0x20),
        "KuaijieK4Fragment:350": control(0x33, arg=0x3F),
        "KuaijieK4Fragment:352": control(0x33, arg=0x30),
        "KuaijieK4Fragment:359": control(0x34, arg=0x4F),
        "KuaijieK4Fragment:361": control(0x34, arg=0x40),
        "KuaijieK5Fragment:57": summed(0x01, 0x09, bytes.fromhex("00")),
        "KuaijieK5Fragment:59": summed(0x01, 0x09, bytes.fromhex("01")),
        "KuaijieK5Fragment:107": control(0x00),
        "KuaijieK5Fragment:170": query(0x64, 0x09),
        "KuaijieK5Fragment:172": query(0x6D, 0x09),
        "KuaijieK5Fragment:174": query(0x76, 0x09),
        "KuaijieK5Fragment:176": query(0x7F, 0x09),
        "KuaijieK5Fragment:192": control(0x08),
        "KuaijieK5Fragment:204": control(0x33, arg=0x31),
        "KuaijieK5Fragment:216": control(0x34, arg=0x41),
        "KuaijieK5Fragment:229": control(0x31, arg=0x11),
        "KuaijieK5Fragment:231": control(0x31),
        "KuaijieK5Fragment:245": control(0x32, arg=0x21),
        "KuaijieK5Fragment:247": control(0x32),
        "KuaijieK5Fragment:261": control(0x33, arg=0x31),
        "KuaijieK5Fragment:263": control(0x33),
        "KuaijieK5Fragment:277": control(0x34, arg=0x41),
        "KuaijieK5Fragment:279": control(0x34),
        "KuaijieK5Fragment:289": control(0x3B),
        "KuaijieK5Fragment:300": control(0x33, arg=0x31),
        "KuaijieK5Fragment:312": control(0x34, arg=0x41),
        "KuaijieK5Fragment:319": control(0x3E, group=0x05),
        "KuaijieK5Fragment:357": control(0x31, arg=0x1F),
        "KuaijieK5Fragment:360": control(0x31, arg=0x10),
        "KuaijieK5Fragment:368": control(0x32, arg=0x2F),
        "KuaijieK5Fragment:371": control(0x32, arg=0x20),
        "KuaijieK5Fragment:379": control(0x33, arg=0x3F),
        "KuaijieK5Fragment:382": control(0x33, arg=0x30),
        "KuaijieK5Fragment:390": control(0x33, arg=0x3F),
        "KuaijieK5Fragment:393": control(0x33, arg=0x30),
        "KuaijieK5Fragment:401": control(0x34, arg=0x4F),
        "KuaijieK5Fragment:404": control(0x34, arg=0x40),
        "KuaijieK5Fragment:412": control(0x34, arg=0x4F),
        "KuaijieK5Fragment:415": control(0x34, arg=0x40),
        "KuaijieK8Fragment:46": summed(0x01, 0x09, bytes.fromhex("00")),
        "KuaijieK8Fragment:48": summed(0x01, 0x09, bytes.fromhex("01")),
        "KuaijieK8Fragment:85": control(0x00),
        "KuaijieK8Fragment:125": control(0x0B, arg=0xBF),
        "KuaijieK8Fragment:127": control(0x0B, arg=0xB0),
        "KuaijieK8Fragment:134": control(0x0A, arg=0xAF),
        "KuaijieK8Fragment:136": control(0x0A, arg=0xA0),
        "KuaijieK8Fragment:183": query(0x28, 0x03),
        "KuaijieK8Fragment:185": query(0x30, 0x03),
        "KuaijieK8Fragment:187": query(0x18, 0x03),
        "KuaijieK8Fragment:189": query(0x20, 0x03),
        "KuaijieK8Fragment:191": query(0x38, 0x03),
        "KuaijieK8Fragment:206": control(0x20),
        "KuaijieK8Fragment:212": control(0x08),
        "KuaijieK8Fragment:223": control(0x0A, arg=0xA1),
        "KuaijieK8Fragment:235": control(0x0B, arg=0xB1),
        "KuaijieK8Fragment:248": control(0x05, arg=0x51),
        "KuaijieK8Fragment:250": control(0x05),
        "KuaijieK8Fragment:265": control(0x09, arg=0x91),
        "KuaijieK8Fragment:267": control(0x09),
        "KuaijieK8Fragment:275": control(0x0E),
        "KuaijieK8Fragment:281": control(0x0D),
        "KuaijieK8Fragment:292": control(0x09, arg=0x9F),
        "KuaijieK8Fragment:294": control(0x09, arg=0x90),
        "KuaijieK8Fragment:301": control(0x05, arg=0x5F),
        "KuaijieK8Fragment:303": control(0x05, arg=0x50),
        "KuaijieK9Fragment:47": summed(0x01, 0x09, bytes.fromhex("00")),
        "KuaijieK9Fragment:49": summed(0x01, 0x09, bytes.fromhex("01")),
        "KuaijieK9Fragment:86": control(0x00),
        "KuaijieK9Fragment:126": control(0x0B, arg=0xBF),
        "KuaijieK9Fragment:128": control(0x0B, arg=0xB0),
        "KuaijieK9Fragment:135": control(0x0A, arg=0xAF),
        "KuaijieK9Fragment:137": control(0x0A, arg=0xA0),
        "KuaijieK9Fragment:193": query(0x28, 0x03),
        "KuaijieK9Fragment:195": query(0x30, 0x03),
        "KuaijieK9Fragment:197": query(0x18, 0x03),
        "KuaijieK9Fragment:199": query(0x20, 0x03),
        "KuaijieK9Fragment:201": query(0x38, 0x03),
        "KuaijieK9Fragment:216": control(0x08),
        "KuaijieK9Fragment:227": control(0x0A, arg=0xA1),
        "KuaijieK9Fragment:239": control(0x0B, arg=0xB1),
        "KuaijieK9Fragment:252": control(0x05, arg=0x51),
        "KuaijieK9Fragment:254": control(0x05),
        "KuaijieK9Fragment:269": control(0x09, arg=0x91),
        "KuaijieK9Fragment:271": control(0x09),
        "KuaijieK9Fragment:279": control(0x0E),
        "KuaijieK9Fragment:285": control(0x0D),
        "KuaijieK9Fragment:298": control(0x0F, arg=0xF1),
        "KuaijieK9Fragment:300": control(0x0F),
        "KuaijieK9Fragment:313": control(0x09, arg=0x9F),
        "KuaijieK9Fragment:315": control(0x09, arg=0x90),
        "KuaijieK9Fragment:322": control(0x05, arg=0x5F),
        "KuaijieK9Fragment:324": control(0x05, arg=0x50),
        "LengnuanFragment:58": _module("FE1000010000000000AA"),
        "LengnuanFragment:183": _module("FE1000000000000000AA"),
        "LengnuanFragment:279:thermal slider table index 0": _module("FE1000050000040000AA"),
        "LengnuanFragment:279:thermal slider table index 1": _module("FE1000050000030000AA"),
        "LengnuanFragment:279:thermal slider table index 2": _module("FE1000050000020000AA"),
        "LengnuanFragment:279:thermal slider table index 3": _module("FE1000050000010000AA"),
        "LengnuanFragment:279:thermal slider table index 4": _module("FE1000060000000000AA"),
        "LengnuanFragment:279:thermal slider table index 5": _module("FE1000040000010000AA"),
        "LengnuanFragment:279:thermal slider table index 6": _module("FE1000040000020000AA"),
        "LengnuanFragment:279:thermal slider table index 7": _module("FE1000040000030000AA"),
        "LengnuanFragment:279:thermal slider table index 8": _module("FE1000040000040000AA"),
        "LengnuanFragment:294": _module("FE1000030000010000AA"),
        "LengnuanFragment:296": _module("FE1000030000000000AA"),
        "QinangFragment:133": _module("FF14020900000000000000000000"),
        "QinangFragment:172": _module("FF0D030C000100"),
        "QinangFragment:174": _module("FF0D030C000000"),
        "QinangFragment:184": _module("FF14030D00000300000000000000"),
        "QinangFragment:186": _module("FF14030D00010300000000000000"),
        "QinangFragment:193": _module("FF14030D00001200000000000000"),
        "QinangFragment:195": _module("FF14030D00011200000000000000"),
        "QinangFragment:302": _module("FF0B010000"),
        "QinangFragment:313": _module("FF0B011200"),
        "QinangFragment:320": _module("FF0B010600"),
        "QinangFragment:326": _module("FF0B010400"),
        "QinangFragment:342": _module("FF0B010300"),
        "QinangFragment:349": _module("FF0B010900"),
        "QinangFragment:355": _module("FF0B010500"),
        "QinangFragment:361": _module("FF0B010C00"),
        "SmartSleepFragment:144": control(0x3F, arg=0xF0),
        "SmartSleepFragment:147": control(0x3F),
        "SmartSleepFragment:156": summed(0x02, 0x11, bytes.fromhex("00")),
        "SmartSleepFragment:159": summed(0x02, 0x11, bytes.fromhex("01")),
        "WeitiaoW10Fragment:50": summed(0x01, 0x09, bytes.fromhex("00")),
        "WeitiaoW10Fragment:52": summed(0x01, 0x09, bytes.fromhex("01")),
        "WeitiaoW10Fragment:61": control(0x03),
        "WeitiaoW10Fragment:65": control(0x00),
        "WeitiaoW10Fragment:74": control(0x04),
        "WeitiaoW10Fragment:78": control(0x00),
        "WeitiaoW10Fragment:88": control(0x01),
        "WeitiaoW10Fragment:92": control(0x00),
        "WeitiaoW10Fragment:101": control(0x02),
        "WeitiaoW10Fragment:105": control(0x00),
        "WeitiaoW10Fragment:115": control(0x06),
        "WeitiaoW10Fragment:119": control(0x00),
        "WeitiaoW10Fragment:128": control(0x07),
        "WeitiaoW10Fragment:132": control(0x00),
        "WeitiaoW11Fragment:50": summed(0x01, 0x09, bytes.fromhex("00")),
        "WeitiaoW11Fragment:52": summed(0x01, 0x09, bytes.fromhex("01")),
        "WeitiaoW11Fragment:61": control(0x03),
        "WeitiaoW11Fragment:65": control(0x00),
        "WeitiaoW11Fragment:74": control(0x04),
        "WeitiaoW11Fragment:78": control(0x00),
        "WeitiaoW11Fragment:88": control(0x0D),
        "WeitiaoW11Fragment:92": control(0x00),
        "WeitiaoW11Fragment:101": control(0x0E),
        "WeitiaoW11Fragment:105": control(0x00),
        "WeitiaoW11Fragment:115": control(0x06),
        "WeitiaoW11Fragment:119": control(0x00),
        "WeitiaoW11Fragment:128": control(0x07),
        "WeitiaoW11Fragment:132": control(0x00),
        "WeitiaoW12Fragment:49": summed(0x01, 0x09, bytes.fromhex("00")),
        "WeitiaoW12Fragment:51": summed(0x01, 0x09, bytes.fromhex("01")),
        "WeitiaoW12Fragment:60": control(0x03),
        "WeitiaoW12Fragment:64": control(0x00),
        "WeitiaoW12Fragment:73": control(0x04),
        "WeitiaoW12Fragment:77": control(0x00),
        "WeitiaoW12Fragment:87": control(0x06),
        "WeitiaoW12Fragment:91": control(0x00),
        "WeitiaoW12Fragment:100": control(0x07),
        "WeitiaoW12Fragment:104": control(0x00),
        "WeitiaoW12Fragment:114": control(0x21),
        "WeitiaoW12Fragment:118": control(0x00),
        "WeitiaoW12Fragment:127": control(0x22),
        "WeitiaoW12Fragment:131": control(0x00),
        "WeitiaoW12Fragment:141": control(0x28),
        "WeitiaoW12Fragment:144": control(0x00),
        "WeitiaoW12Fragment:153": control(0x29),
        "WeitiaoW12Fragment:156": control(0x00),
        "WeitiaoW13Fragment:80": summed(0x01, 0x09, bytes.fromhex("00")),
        "WeitiaoW13Fragment:82": summed(0x01, 0x09, bytes.fromhex("01")),
        "WeitiaoW13Fragment:96": control(0x03),
        "WeitiaoW13Fragment:100": control(0x00),
        "WeitiaoW13Fragment:109": control(0x04),
        "WeitiaoW13Fragment:113": control(0x00),
        "WeitiaoW13Fragment:123": control(0x0D),
        "WeitiaoW13Fragment:127": control(0x00),
        "WeitiaoW13Fragment:136": control(0x0E),
        "WeitiaoW13Fragment:140": control(0x00),
        "WeitiaoW13Fragment:150": control(0x01),
        "WeitiaoW13Fragment:154": control(0x00),
        "WeitiaoW13Fragment:163": control(0x02),
        "WeitiaoW13Fragment:167": control(0x00),
        "WeitiaoW13Fragment:177": control(0x06),
        "WeitiaoW13Fragment:181": control(0x00),
        "WeitiaoW13Fragment:190": control(0x07),
        "WeitiaoW13Fragment:194": control(0x00),
        "WeitiaoW13Fragment:204": control(0x21),
        "WeitiaoW13Fragment:208": control(0x00),
        "WeitiaoW13Fragment:217": control(0x22),
        "WeitiaoW13Fragment:221": control(0x00),
        "WeitiaoW13Fragment:231": control(0x28),
        "WeitiaoW13Fragment:234": control(0x00),
        "WeitiaoW13Fragment:243": control(0x29),
        "WeitiaoW13Fragment:246": control(0x00),
        "WeitiaoW13Fragment:304": control(0xE4, group=0x05),
        "WeitiaoW13Fragment:310": control(0xE3, group=0x05),
        "WeitiaoW13Fragment:316": control(0xE5, group=0x05),
        "WeitiaoW13Fragment:322": control(0xE6, group=0x05),
        "WeitiaoW14Fragment:80": summed(0x01, 0x09, bytes.fromhex("00")),
        "WeitiaoW14Fragment:82": summed(0x01, 0x09, bytes.fromhex("01")),
        "WeitiaoW14Fragment:96": control(0x03),
        "WeitiaoW14Fragment:100": control(0x00),
        "WeitiaoW14Fragment:109": control(0x04),
        "WeitiaoW14Fragment:113": control(0x00),
        "WeitiaoW14Fragment:123": control(0x0D),
        "WeitiaoW14Fragment:127": control(0x00),
        "WeitiaoW14Fragment:136": control(0x0E),
        "WeitiaoW14Fragment:140": control(0x00),
        "WeitiaoW14Fragment:150": control(0x01),
        "WeitiaoW14Fragment:154": control(0x00),
        "WeitiaoW14Fragment:163": control(0x02),
        "WeitiaoW14Fragment:167": control(0x00),
        "WeitiaoW14Fragment:177": control(0x06),
        "WeitiaoW14Fragment:181": control(0x00),
        "WeitiaoW14Fragment:190": control(0x07),
        "WeitiaoW14Fragment:194": control(0x00),
        "WeitiaoW14Fragment:204": control(0x21),
        "WeitiaoW14Fragment:208": control(0x00),
        "WeitiaoW14Fragment:217": control(0x22),
        "WeitiaoW14Fragment:221": control(0x00),
        "WeitiaoW14Fragment:231": control(0x28),
        "WeitiaoW14Fragment:234": control(0x00),
        "WeitiaoW14Fragment:243": control(0x29),
        "WeitiaoW14Fragment:246": control(0x00),
        "WeitiaoW14Fragment:304": control(0xE4, group=0x05),
        "WeitiaoW14Fragment:310": control(0xE3, group=0x05),
        "WeitiaoW14Fragment:316": control(0xE5, group=0x05),
        "WeitiaoW14Fragment:322": control(0xE6, group=0x05),
        "WeitiaoW18Fragment:78": summed(0x01, 0x09, bytes.fromhex("00")),
        "WeitiaoW18Fragment:80": summed(0x01, 0x09, bytes.fromhex("01")),
        "WeitiaoW18Fragment:94": control(0x03),
        "WeitiaoW18Fragment:98": control(0x00),
        "WeitiaoW18Fragment:107": control(0x04),
        "WeitiaoW18Fragment:111": control(0x00),
        "WeitiaoW18Fragment:121": control(0x0D),
        "WeitiaoW18Fragment:125": control(0x00),
        "WeitiaoW18Fragment:134": control(0x0E),
        "WeitiaoW18Fragment:138": control(0x00),
        "WeitiaoW18Fragment:148": control(0x01),
        "WeitiaoW18Fragment:152": control(0x00),
        "WeitiaoW18Fragment:161": control(0x02),
        "WeitiaoW18Fragment:165": control(0x00),
        "WeitiaoW18Fragment:175": control(0x06),
        "WeitiaoW18Fragment:179": control(0x00),
        "WeitiaoW18Fragment:188": control(0x07),
        "WeitiaoW18Fragment:192": control(0x00),
        "WeitiaoW18Fragment:250": control(0xE4, group=0x05),
        "WeitiaoW18Fragment:256": control(0xE3, group=0x05),
        "WeitiaoW18Fragment:262": control(0xE5, group=0x05),
        "WeitiaoW18Fragment:268": control(0xE6, group=0x05),
        "WeitiaoW1Fragment:78": summed(0x01, 0x09, bytes.fromhex("00")),
        "WeitiaoW1Fragment:80": summed(0x01, 0x09, bytes.fromhex("01")),
        "WeitiaoW1Fragment:94": control(0x03),
        "WeitiaoW1Fragment:98": control(0x00),
        "WeitiaoW1Fragment:107": control(0x04),
        "WeitiaoW1Fragment:111": control(0x00),
        "WeitiaoW1Fragment:121": control(0x0D),
        "WeitiaoW1Fragment:125": control(0x00),
        "WeitiaoW1Fragment:134": control(0x0E),
        "WeitiaoW1Fragment:138": control(0x00),
        "WeitiaoW1Fragment:148": control(0x01),
        "WeitiaoW1Fragment:152": control(0x00),
        "WeitiaoW1Fragment:161": control(0x02),
        "WeitiaoW1Fragment:165": control(0x00),
        "WeitiaoW1Fragment:175": control(0x06),
        "WeitiaoW1Fragment:179": control(0x00),
        "WeitiaoW1Fragment:188": control(0x07),
        "WeitiaoW1Fragment:192": control(0x00),
        "WeitiaoW1Fragment:250": control(0xE4, group=0x05),
        "WeitiaoW1Fragment:256": control(0xE3, group=0x05),
        "WeitiaoW1Fragment:262": control(0xE5, group=0x05),
        "WeitiaoW1Fragment:268": control(0xE6, group=0x05),
        "WeitiaoW2Fragment:78": summed(0x01, 0x09, bytes.fromhex("00")),
        "WeitiaoW2Fragment:80": summed(0x01, 0x09, bytes.fromhex("01")),
        "WeitiaoW2Fragment:94": control(0x03),
        "WeitiaoW2Fragment:98": control(0x00),
        "WeitiaoW2Fragment:107": control(0x04),
        "WeitiaoW2Fragment:111": control(0x00),
        "WeitiaoW2Fragment:121": control(0x0D),
        "WeitiaoW2Fragment:125": control(0x00),
        "WeitiaoW2Fragment:134": control(0x0E),
        "WeitiaoW2Fragment:138": control(0x00),
        "WeitiaoW2Fragment:148": control(0x01),
        "WeitiaoW2Fragment:152": control(0x00),
        "WeitiaoW2Fragment:161": control(0x02),
        "WeitiaoW2Fragment:165": control(0x00),
        "WeitiaoW2Fragment:175": control(0x06),
        "WeitiaoW2Fragment:179": control(0x00),
        "WeitiaoW2Fragment:188": control(0x07),
        "WeitiaoW2Fragment:192": control(0x00),
        "WeitiaoW2Fragment:250": control(0xE4, group=0x05),
        "WeitiaoW2Fragment:256": control(0xE3, group=0x05),
        "WeitiaoW2Fragment:262": control(0xE5, group=0x05),
        "WeitiaoW2Fragment:268": control(0xE6, group=0x05),
        "WeitiaoW3Fragment:78": summed(0x01, 0x09, bytes.fromhex("00")),
        "WeitiaoW3Fragment:80": summed(0x01, 0x09, bytes.fromhex("01")),
        "WeitiaoW3Fragment:94": control(0x03),
        "WeitiaoW3Fragment:98": control(0x00),
        "WeitiaoW3Fragment:107": control(0x04),
        "WeitiaoW3Fragment:111": control(0x00),
        "WeitiaoW3Fragment:121": control(0x2B, group=0x05),
        "WeitiaoW3Fragment:125": control(0x00),
        "WeitiaoW3Fragment:134": control(0x2C, group=0x05),
        "WeitiaoW3Fragment:138": control(0x00),
        "WeitiaoW3Fragment:148": control(0x0D),
        "WeitiaoW3Fragment:152": control(0x00),
        "WeitiaoW3Fragment:161": control(0x0E),
        "WeitiaoW3Fragment:165": control(0x00),
        "WeitiaoW3Fragment:175": control(0x06),
        "WeitiaoW3Fragment:179": control(0x00),
        "WeitiaoW3Fragment:188": control(0x07),
        "WeitiaoW3Fragment:192": control(0x00),
        "WeitiaoW3Fragment:249": control(0xE8, group=0x05),
        "WeitiaoW3Fragment:255": control(0xE4, group=0x05),
        "WeitiaoW3Fragment:261": control(0xE5, group=0x05),
        "WeitiaoW3Fragment:267": control(0xE6, group=0x05),
        "WeitiaoW4Fragment:47": summed(0x01, 0x09, bytes.fromhex("00")),
        "WeitiaoW4Fragment:49": summed(0x01, 0x09, bytes.fromhex("01")),
        "WeitiaoW4Fragment:58": control(0x03),
        "WeitiaoW4Fragment:62": control(0x00),
        "WeitiaoW4Fragment:71": control(0x04),
        "WeitiaoW4Fragment:75": control(0x00),
        "WeitiaoW4Fragment:85": control(0x06),
        "WeitiaoW4Fragment:89": control(0x00),
        "WeitiaoW4Fragment:98": control(0x07),
        "WeitiaoW4Fragment:102": control(0x00),
        "WeitiaoW6Fragment:47": summed(0x01, 0x09, bytes.fromhex("00")),
        "WeitiaoW6Fragment:49": summed(0x01, 0x09, bytes.fromhex("01")),
        "WeitiaoW6Fragment:58": control(0x03),
        "WeitiaoW6Fragment:62": control(0x00),
        "WeitiaoW6Fragment:71": control(0x04),
        "WeitiaoW6Fragment:75": control(0x00),
        "WeitiaoW6Fragment:85": control(0x06),
        "WeitiaoW6Fragment:89": control(0x00),
        "WeitiaoW6Fragment:98": control(0x07),
        "WeitiaoW6Fragment:102": control(0x00),
        "WeitiaoW7Fragment:76": summed(0x01, 0x09, bytes.fromhex("00")),
        "WeitiaoW7Fragment:78": summed(0x01, 0x09, bytes.fromhex("01")),
        "WeitiaoW7Fragment:89": control(0x03),
        "WeitiaoW7Fragment:93": control(0x00),
        "WeitiaoW7Fragment:102": control(0x04),
        "WeitiaoW7Fragment:106": control(0x00),
        "WeitiaoW7Fragment:116": control(0x0D),
        "WeitiaoW7Fragment:120": control(0x00),
        "WeitiaoW7Fragment:129": control(0x0E),
        "WeitiaoW7Fragment:133": control(0x00),
        "WeitiaoW7Fragment:143": control(0x01),
        "WeitiaoW7Fragment:147": control(0x00),
        "WeitiaoW7Fragment:156": control(0x02),
        "WeitiaoW7Fragment:160": control(0x00),
        "WeitiaoW7Fragment:170": control(0x06),
        "WeitiaoW7Fragment:174": control(0x00),
        "WeitiaoW7Fragment:183": control(0x07),
        "WeitiaoW7Fragment:187": control(0x00),
        "WeitiaoW7Fragment:197": control(0x35),
        "WeitiaoW7Fragment:201": control(0x00),
        "WeitiaoW7Fragment:210": control(0x36),
        "WeitiaoW7Fragment:214": control(0x00),
        "WeitiaoW7Fragment:224": control(0x37),
        "WeitiaoW7Fragment:228": control(0x00),
        "WeitiaoW7Fragment:237": control(0x38),
        "WeitiaoW7Fragment:241": control(0x00),
        "WeitiaoW8Fragment:75": summed(0x01, 0x09, bytes.fromhex("00")),
        "WeitiaoW8Fragment:77": summed(0x01, 0x09, bytes.fromhex("01")),
        "WeitiaoW8Fragment:88": control(0x03),
        "WeitiaoW8Fragment:92": control(0x00),
        "WeitiaoW8Fragment:101": control(0x04),
        "WeitiaoW8Fragment:105": control(0x00),
        "WeitiaoW8Fragment:115": control(0x0D),
        "WeitiaoW8Fragment:119": control(0x00),
        "WeitiaoW8Fragment:128": control(0x0E),
        "WeitiaoW8Fragment:132": control(0x00),
        "WeitiaoW8Fragment:142": control(0x06),
        "WeitiaoW8Fragment:146": control(0x00),
        "WeitiaoW8Fragment:155": control(0x07),
        "WeitiaoW8Fragment:159": control(0x00),
        "WeitiaoW8Fragment:169": control(0x35),
        "WeitiaoW8Fragment:173": control(0x00),
        "WeitiaoW8Fragment:182": control(0x36),
        "WeitiaoW8Fragment:186": control(0x00),
        "WeitiaoW8Fragment:196": control(0x06),
        "WeitiaoW8Fragment:200": control(0x00),
        "WeitiaoW8Fragment:209": control(0x07),
        "WeitiaoW8Fragment:213": control(0x00),

    }
)
