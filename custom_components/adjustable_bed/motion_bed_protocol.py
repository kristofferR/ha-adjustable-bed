"""Typed packet construction for the Motion Bed application's BLE routes.

Field order and checksums come from com.sn.blackdianqi 1.24 (34). These
builders never write to Bluetooth or select a device/model. SOURCE_COMMANDS
retains source-callsite identity; the controller must gate each callsite by
its model, action and state predicate before sending it.
"""

from __future__ import annotations

import math
import re
import struct
from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import IntEnum, StrEnum
from types import MappingProxyType
from typing import Final


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


def additive_checksum(body: bytes) -> bytes:
    """Append minimal unsigned little-endian sum; zero has no suffix."""
    total = sum(body)
    return body + total.to_bytes((total.bit_length() + 7) // 8, "little")


def with_crc(body: bytes) -> bytes:
    """Append reflected MODBUS CRC over the entire body, including FF bytes."""
    crc = 0xFFFF
    for byte in body:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return body + crc.to_bytes(2, "little")


def _bcd(value: int) -> int:
    return (value // 10) * 16 + value % 10


def _time(hour: int, minute: int) -> bytes:
    return bytes((_bcd(_integer(hour, 0, 23, "hour")), _bcd(_integer(minute, 0, 59, "minute"))))


def _date(timestamp: datetime, weekday: int | None, *, thermal: bool) -> bytes:
    # DateBean uses year.substring(2,4), so years before 1000 cannot serialize.
    _integer(timestamp.year, 1000, 9999, "year")
    week = timestamp.isoweekday() if weekday is None else _integer(weekday, 1, 7, "weekday")
    date = bytes((_bcd(timestamp.year % 100), _bcd(timestamp.month), _bcd(timestamp.day)))
    time = _time(timestamp.hour, timestamp.minute) + bytes((_bcd(timestamp.second),))
    return date + time + bytes((week,)) if thermal else time + bytes((week,)) + date


def build_clock(timestamp: datetime, *, weekday: int | None = None) -> bytes:
    return additive_checksum(
        bytes.fromhex("FFFFFFFF01000111") + _date(timestamp, weekday, thermal=False)
    )


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
    return additive_checksum(
        bytes.fromhex("FFFFFFFF01000213")
        + bytes((code,))
        + _time(hour, minute)
        + bytes((0, mask, bool(weekdays), mode, massage, sound))
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
    return additive_checksum(bytes.fromhex("FFFFFFFF02001012") + bytes(values))


def build_sleep_calibration(flat: int, side: int) -> bytes:
    _integer(side, 0, (1 << 31) - 1, "side")
    return additive_checksum(
        bytes.fromhex("FFFFFFFF0200120C") + _number(flat, "flat") + _number(side // 2, "side / 2")
    )


def build_sleep_timer(slot: int, *, fall: bool = False) -> bytes:
    if not isinstance(fall, bool):
        raise ValueError("fall must be Boolean")
    _integer(slot, 0, 4 if fall else 8, "slot")
    prefix = "FFFFFFFF0200150B" if fall else "FFFFFFFF02000D0B"
    return additive_checksum(bytes.fromhex(prefix) + bytes((slot,)))


def build_sleep_report(kind: SleepReport, *, offset: int = 0) -> bytes:
    kind = SleepReport(kind)
    _integer(offset, 0, 29, "offset")
    bodies = {
        SleepReport.MONTH: "FFFFFFFF0200030B1E",
        SleepReport.CURRENT: "FFFFFFFF0200030B01",
        SleepReport.TIMER: "FFFFFFFF0200160B00",
    }
    if kind == SleepReport.DAY:
        return additive_checksum(bytes.fromhex("FFFFFFFF0200130B") + bytes((offset,)))
    return additive_checksum(bytes.fromhex(bodies[kind]))


def build_module_bind(module: ModuleType, address: str) -> bytes:
    module = _enum(ModuleType, module)
    if re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", address) is None:
        raise ValueError("module address must contain six colon-separated octets")
    return additive_checksum(
        bytes.fromhex("FFFFFFFF01002814")
        + bytes((module,))
        + bytes.fromhex(address.replace(":", ""))
        + bytes(3)
    )


def build_module_delete(module: ModuleType) -> bytes:
    return additive_checksum(
        bytes.fromhex("FFFFFFFF01002814")
        + bytes((_enum(ModuleType, module),))
        + bytes(7)
        + bytes((1, 0))
    )


def build_module_query() -> bytes:
    return additive_checksum(bytes.fromhex("FFFFFFFF010026140F000000000000000000"))


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
    return additive_checksum(
        bytes.fromhex("FFFFFFFF0100130B") + bytes((track + (0x80 if preview else 0),))
    )


def build_audio_volume(volume: int) -> bytes:
    return additive_checksum(
        bytes.fromhex("FFFFFFFF0100140B") + bytes((_integer(volume, 1, 5, "volume"),))
    )


def build_wifi_frames(
    ssid: str, password: str, longitude: float, latitude: float
) -> tuple[bytes, ...]:
    """Android UTF-8 bytes are truncated and FF padded, including mid-codepoint."""
    for value, bound, name in ((longitude, 180, "longitude"), (latitude, 90, "latitude")):
        if isinstance(value, bool) or not math.isfinite(value) or not -bound <= value <= bound:
            raise ValueError(f"{name} must be finite and within ±{bound}")
    network = ssid.encode("utf-8")[:32].ljust(32, b"\xff") + password.encode("utf-8")[:16].ljust(
        16, b"\xff"
    )
    chunks = [network[index : index + 8] for index in range(0, 48, 8)]
    chunks.append(struct.pack(">ff", longitude, latitude))
    return tuple(
        additive_checksum(bytes.fromhex("FFFFFFFF02001813") + bytes((index,)) + data)
        for index, data in enumerate(chunks, 1)
    )


SOURCE_COMMANDS: Final[Mapping[str, bytes]] = MappingProxyType(
    {
        "AlarmActivity:296": bytes.fromhex("FFFFFFFF0100130B819C04"),
        "AlarmActivity:300": bytes.fromhex("FFFFFFFF0100130B829D04"),
        "AlarmActivity:304": bytes.fromhex("FFFFFFFF0100130B839E04"),
        "AlarmActivity:306": bytes.fromhex("FFFFFFFF0100130B849F04"),
        "AlarmActivity:308": bytes.fromhex("FFFFFFFF0100130B85A004"),
        "AlarmActivity:314": bytes.fromhex("FFFFFFFF0100130B001B04"),
        "AnmoSetActivity:260": bytes.fromhex("FFFFFFFFFF0D02080003007FB2"),
        "ChangeDeviceActivity:96": bytes.fromhex("FFFFFFFF010026140F0000000000000000004604"),
        "ChangeDeviceActivity:213": bytes.fromhex("FFFFFFFF010028140A0000000000000001004404"),
        "ChangeDeviceActivity:219": bytes.fromhex("FFFFFFFF010028140C0000000000000001004604"),
        "ChangeDeviceActivity:225": bytes.fromhex("FFFFFFFF010028140B0000000000000001004504"),
        "ConnectMcuActivity:311": bytes.fromhex("FFFFFFFF010026140F0000000000000000004604"),
        "DianDongSetActivity:270": bytes.fromhex("FFFFFFFF050000001516CF"),
        "DianDongSetActivity:275": bytes.fromhex("FFFFFFFF0500000014D70F"),
        "DianDongSetActivity:281": bytes.fromhex("FFFFFFFF0500000011170C"),
        "DianDongSetActivity:286": bytes.fromhex("FFFFFFFF0500000010D6CC"),
        "DianDongSetActivity:292": bytes.fromhex("FFFFFFFF050000001396CD"),
        "DianDongSetActivity:297": bytes.fromhex("FFFFFFFF0500000012570D"),
        "DianDongSetActivity:385:level 0": bytes.fromhex("FFFFFFFF050000002396D9"),
        "DianDongSetActivity:385:level 1": bytes.fromhex("FFFFFFFF05000001239749"),
        "DianDongSetActivity:385:level 2": bytes.fromhex("FFFFFFFF050000022397B9"),
        "DianDongSetActivity:385:level 3": bytes.fromhex("FFFFFFFF05000003239629"),
        "DianDongSetActivity:385:level 4": bytes.fromhex("FFFFFFFF05000004239419"),
        "DianDongSetActivity:385:level 5": bytes.fromhex("FFFFFFFF05000005239589"),
        "DianDongSetActivity:385:level 6": bytes.fromhex("FFFFFFFF05000006239579"),
        "DianDongSetActivity:385:level 7": bytes.fromhex("FFFFFFFF050000072394E9"),
        "DianDongSetActivity:385:level 8": bytes.fromhex("FFFFFFFF05000008239119"),
        "DianDongSetActivity:385:level 9": bytes.fromhex("FFFFFFFF05000009239089"),
        "DianDongSetActivity:385:level 10": bytes.fromhex("FFFFFFFF0500000A239079"),
        "DianDongSetActivity:490": bytes.fromhex("FFFFFFFF0100130B819C04"),
        "DianDongSetActivity:494": bytes.fromhex("FFFFFFFF0100130B829D04"),
        "DianDongSetActivity:498": bytes.fromhex("FFFFFFFF0100130B839E04"),
        "DianDongSetActivity:500": bytes.fromhex("FFFFFFFF0100130B849F04"),
        "DianDongSetActivity:502": bytes.fromhex("FFFFFFFF0100130B85A004"),
        "DianDongSetActivity:508": bytes.fromhex("FFFFFFFF0100130B001B04"),
        "DianDongSetActivity:515": bytes.fromhex("FFFFFFFF01001C14010000000000000000002E04"),
        "DianDongSetActivity:522": bytes.fromhex("FFFFFFFF01001C14030000000000000000003004"),
        "DianDongSetActivity:525": bytes.fromhex("FFFFFFFF050000001916CA"),
        "DianDongSetActivity:535": bytes.fromhex("FFFFFFFF050000001B970B"),
        "DianDongSetActivity:545": bytes.fromhex("FFFFFFFF050000001A56CB"),
        "DianDongSetActivity:557": bytes.fromhex("FFFFFFFF050000001CD6C9"),
        "DianDongSetActivity:559": bytes.fromhex("FFFFFFFF050000001656CE"),
        "DianDongSetActivity:569": bytes.fromhex("FFFFFFFF050000001CD6C9"),
        "DianDongSetActivity:571": bytes.fromhex("FFFFFFFF0500000017970E"),
        "DianDongSetActivity:581": bytes.fromhex("FFFFFFFF050000001CD6C9"),
        "DianDongSetActivity:583": bytes.fromhex("FFFFFFFF0500000018D70A"),
        "DianDongSetActivity:629": bytes.fromhex("FFFFFFFF01001C14020000000000000000002F04"),
        "DianDongSetActivity:631": bytes.fromhex("FFFFFFFF01001C14040000000000000000003104"),
        "HomeActivity:142": bytes.fromhex("FFFFFFFF01000A0B0F2104"),
        "HomeActivity:311": bytes.fromhex("FFFFFFFF01000A0B0F2104"),
        "HomeActivity:321": bytes.fromhex("FFFFFFFF02000E0B001704"),
        "HomeActivity:455": bytes.fromhex("FFFFFFFF050005FF23C728"),
        "HomeActivity:463": bytes.fromhex("FFFFFFFF02000A0A1204"),
        "HomeActivity:465": bytes.fromhex("FFFFFFFF02000E0B001704"),
        "MainMcuActivity:182": bytes.fromhex("FFFFFFFF010026140F0000000000000000004604"),
        "NetworkActivity:333": bytes.fromhex("FFFFFFFF02000A0A1204"),
        "PressSetActivity:224": bytes.fromhex("FFFFFFFFFF0B020400AE30"),
        "Setting2Activity:238": bytes.fromhex("FFFFFFFF010026140F0000000000000000004604"),
        "SleepAdjustActivity:102": bytes.fromhex("FFFFFFFF02000A0A1204"),
        "SleepAdjustActivity:165": bytes.fromhex("FFFFFFFF0200100B001904"),
        "SleepAdjustActivity:243:caller line 188": bytes.fromhex("FFFFFFFF05000002039661"),
        "SleepAdjustActivity:243:caller line 204": bytes.fromhex("FFFFFFFF050000020117A0"),
        "SleepAdjustActivity:243:caller line 218": bytes.fromhex("FFFFFFFF05000002065662"),
        "SleepAdjustActivity:243:caller line 232": bytes.fromhex("FFFFFFFF050000020D17A5"),
        "SleepAdjustActivity:251": bytes.fromhex("FFFFFFFF0500000000D700"),
        "SleepAdjustActivity:255": bytes.fromhex("FFFFFFFF02000F0B001804"),
        "SleepAdjustActivity:261:caller line 181": bytes.fromhex("FFFFFFFF0500000204D7A3"),
        "SleepAdjustActivity:261:caller line 197": bytes.fromhex("FFFFFFFF050000020257A1"),
        "SleepAdjustActivity:261:caller line 211": bytes.fromhex("FFFFFFFF050000020797A2"),
        "SleepAdjustActivity:261:caller line 225": bytes.fromhex("FFFFFFFF050000020E57A4"),
        "SleepAdjustActivity:269": bytes.fromhex("FFFFFFFF0500000000D700"),
        "SleepAdjustActivity:273": bytes.fromhex("FFFFFFFF02000F0B001804"),
        "SleepAdjustActivity:281": bytes.fromhex("FFFFFFFF02000F0B001804"),
        "SleepAdjustActivity:289": bytes.fromhex("FFFFFFFF02000F0B001804"),
        "SleepAdjustActivity:411": bytes.fromhex("FFFFFFFF02000F0B001804"),
        "SleepDataEntryActivity:105": bytes.fromhex("FFFFFFFF02000A0A1204"),
        "SleepDataEntryActivity:126": bytes.fromhex("FFFFFFFF02000A0A1204"),
        "SleepDataEntryActivity:189": bytes.fromhex("FFFFFFFF0500000208D7A6"),
        "SleepDataEntryActivity:202": bytes.fromhex("FFFFFFFF02000A0A1204"),
        "SleepDataEntryActivity:248": bytes.fromhex("FFFFFFFF0200090D0100001504"),
        "SleepDataEntryActivity:253": bytes.fromhex("FFFFFFFF0200090D0200001604"),
        "SleepDataEntryActivity:268": bytes.fromhex("FFFFFFFF0200120C0A466C04"),
        "SleepDataEntryActivity:293": bytes.fromhex("FFFFFFFF0200090F03000000001904"),
        "SleepDayReportActivity:88": bytes.fromhex("FFFFFFFF02000A0A1204"),
        "XinLvDaiActivity:175": bytes.fromhex("FFFFFFFF02000A0A1204"),
        "AnmoFragment:88": bytes.fromhex("FFFFFFFF0100090B001104"),
        "AnmoFragment:90": bytes.fromhex("FFFFFFFF0100090B011204"),
        "AnmoFragment:100": bytes.fromhex("FFFFFFFF050000001516CF"),
        "AnmoFragment:105": bytes.fromhex("FFFFFFFF0500000014D70F"),
        "AnmoFragment:111": bytes.fromhex("FFFFFFFF0500000011170C"),
        "AnmoFragment:116": bytes.fromhex("FFFFFFFF0500000010D6CC"),
        "AnmoFragment:122": bytes.fromhex("FFFFFFFF050000001396CD"),
        "AnmoFragment:127": bytes.fromhex("FFFFFFFF0500000012570D"),
        "AnmoFragment:165": bytes.fromhex("FFFFFFFF050000001CD6C9"),
        "AnmoFragment:167": bytes.fromhex("FFFFFFFF050000001656CE"),
        "AnmoFragment:177": bytes.fromhex("FFFFFFFF050000001CD6C9"),
        "AnmoFragment:179": bytes.fromhex("FFFFFFFF0500000017970E"),
        "AnmoFragment:189": bytes.fromhex("FFFFFFFF050000001CD6C9"),
        "AnmoFragment:191": bytes.fromhex("FFFFFFFF0500000018D70A"),
        "DengguangFragment:99": bytes.fromhex("FFFFFFFF0100090B001104"),
        "DengguangFragment:101": bytes.fromhex("FFFFFFFF0100090B011204"),
        "DengguangFragment:176:level 0": bytes.fromhex("FFFFFFFF050000002396D9"),
        "DengguangFragment:176:level 1": bytes.fromhex("FFFFFFFF05000001239749"),
        "DengguangFragment:176:level 2": bytes.fromhex("FFFFFFFF050000022397B9"),
        "DengguangFragment:176:level 3": bytes.fromhex("FFFFFFFF05000003239629"),
        "DengguangFragment:176:level 4": bytes.fromhex("FFFFFFFF05000004239419"),
        "DengguangFragment:176:level 5": bytes.fromhex("FFFFFFFF05000005239589"),
        "DengguangFragment:176:level 6": bytes.fromhex("FFFFFFFF05000006239579"),
        "DengguangFragment:176:level 7": bytes.fromhex("FFFFFFFF050000072394E9"),
        "DengguangFragment:176:level 8": bytes.fromhex("FFFFFFFF05000008239119"),
        "DengguangFragment:176:level 9": bytes.fromhex("FFFFFFFF05000009239089"),
        "DengguangFragment:176:level 10": bytes.fromhex("FFFFFFFF0500000A239079"),
        "DengguangFragment:181": bytes.fromhex("FFFFFFFF050005FF23C728"),
        "DengguangFragment:208": bytes.fromhex("FFFFFFFF050000001916CA"),
        "DengguangFragment:218": bytes.fromhex("FFFFFFFF050000001B970B"),
        "DengguangFragment:228": bytes.fromhex("FFFFFFFF050000001A56CB"),
        "DiandongFragment:135": bytes.fromhex("FFFFFFFF01000C0B0F2304"),
        "DiandongFragment:319": bytes.fromhex("FFFFFFFF01002A14000000000000000000003B04"),
        "DiandongFragment:349": bytes.fromhex("FFFFFFFF0500000000D700"),
        "DiandongFragment:387": bytes.fromhex("FFFFFFFF0500000000D700"),
        "DiandongFragment:392": bytes.fromhex("FFFFFFFF0500000004D6C3"),
        "DiandongFragment:412": bytes.fromhex("FFFFFFFF0500000000D700"),
        "DiandongFragment:417": bytes.fromhex("FFFFFFFF050000000796C2"),
        "DiandongFragment:452": bytes.fromhex("FFFFFFFF050000004A56F7"),
        "DiandongFragment:454": bytes.fromhex("FFFFFFFF050000004B9737"),
        "DiandongFragment:464": bytes.fromhex("FFFFFFFF050000011CD759"),
        "DiandongFragment:466": bytes.fromhex("FFFFFFFF050000001CD6C9"),
        "DiandongFragment:566": bytes.fromhex("FFFFFFFF0500000008D6C6"),
        "DiandongFragment:578": bytes.fromhex("FFFFFFFF050000A10A2E97"),
        "DiandongFragment:580": bytes.fromhex("FFFFFFFF050000000A5707"),
        "DiandongFragment:594": bytes.fromhex("FFFFFFFF050000B10BE297"),
        "DiandongFragment:596": bytes.fromhex("FFFFFFFF050000000B96C7"),
        "DiandongFragment:610": bytes.fromhex("FFFFFFFF05000051052A93"),
        "DiandongFragment:612": bytes.fromhex("FFFFFFFF05000000051703"),
        "DiandongFragment:626": bytes.fromhex("FFFFFFFF05000091097A96"),
        "DiandongFragment:628": bytes.fromhex("FFFFFFFF05000000091706"),
        "DiandongFragment:636": bytes.fromhex("FFFFFFFF050000006A572F"),
        "DiandongFragment:648": bytes.fromhex("FFFFFFFF050000F10FD294"),
        "DiandongFragment:650": bytes.fromhex("FFFFFFFF050000000F9704"),
        "DiandongFragment:663": bytes.fromhex("FFFFFFFF0500009F097EF6"),
        "DiandongFragment:665": bytes.fromhex("FFFFFFFF05000090097B06"),
        "DiandongFragment:672": bytes.fromhex("FFFFFFFF050000FF0FD6F4"),
        "DiandongFragment:674": bytes.fromhex("FFFFFFFF050000F00FD304"),
        "DiandongFragment:681": bytes.fromhex("FFFFFFFF0500005F052EF3"),
        "DiandongFragment:683": bytes.fromhex("FFFFFFFF05000050052B03"),
        "DiandongFragment:690": bytes.fromhex("FFFFFFFF050000BF0BE6F7"),
        "DiandongFragment:692": bytes.fromhex("FFFFFFFF050000B00BE307"),
        "DiandongFragment:699": bytes.fromhex("FFFFFFFF050000AF0A2AF7"),
        "DiandongFragment:701": bytes.fromhex("FFFFFFFF050000A00A2F07"),
        "KuaijieK11Fragment:50": bytes.fromhex("FFFFFFFF0100090B001104"),
        "KuaijieK11Fragment:52": bytes.fromhex("FFFFFFFF0100090B011204"),
        "KuaijieK11Fragment:93": bytes.fromhex("FFFFFFFF0500000000D700"),
        "KuaijieK11Fragment:136": bytes.fromhex("FFFFFFFF050000BF0BE6F7"),
        "KuaijieK11Fragment:138": bytes.fromhex("FFFFFFFF050000B00BE307"),
        "KuaijieK11Fragment:145": bytes.fromhex("FFFFFFFF050000AF0A2AF7"),
        "KuaijieK11Fragment:147": bytes.fromhex("FFFFFFFF050000A00A2F07"),
        "KuaijieK11Fragment:203": bytes.fromhex("FFFFFFFF03002800091F0E"),
        "KuaijieK11Fragment:205": bytes.fromhex("FFFFFFFF0300310009CEC9"),
        "KuaijieK11Fragment:207": bytes.fromhex("FFFFFFFF03001600097EC2"),
        "KuaijieK11Fragment:209": bytes.fromhex("FFFFFFFF03001F0009AEC0"),
        "KuaijieK11Fragment:211": bytes.fromhex("FFFFFFFF03003A0009BF0B"),
        "KuaijieK11Fragment:226": bytes.fromhex("FFFFFFFF0500000008D6C6"),
        "KuaijieK11Fragment:232": bytes.fromhex("FFFFFFFF050000002916DE"),
        "KuaijieK11Fragment:243": bytes.fromhex("FFFFFFFF050000A10A2E97"),
        "KuaijieK11Fragment:255": bytes.fromhex("FFFFFFFF050000B10BE297"),
        "KuaijieK11Fragment:268": bytes.fromhex("FFFFFFFF05000051052A93"),
        "KuaijieK11Fragment:270": bytes.fromhex("FFFFFFFF05000000051703"),
        "KuaijieK11Fragment:285": bytes.fromhex("FFFFFFFF05000091097A96"),
        "KuaijieK11Fragment:287": bytes.fromhex("FFFFFFFF05000000091706"),
        "KuaijieK11Fragment:295": bytes.fromhex("FFFFFFFF0500000028D71E"),
        "KuaijieK11Fragment:301": bytes.fromhex("FFFFFFFF050000002A56DF"),
        "KuaijieK11Fragment:307": bytes.fromhex("FFFFFFFF05000000211718"),
        "KuaijieK11Fragment:313": bytes.fromhex("FFFFFFFF05000000225719"),
        "KuaijieK11Fragment:326": bytes.fromhex("FFFFFFFF050000F10FD294"),
        "KuaijieK11Fragment:328": bytes.fromhex("FFFFFFFF050000000F9704"),
        "KuaijieK11Fragment:341": bytes.fromhex("FFFFFFFF0500009F097EF6"),
        "KuaijieK11Fragment:343": bytes.fromhex("FFFFFFFF05000090097B06"),
        "KuaijieK11Fragment:350": bytes.fromhex("FFFFFFFF050000FF0FD6F4"),
        "KuaijieK11Fragment:352": bytes.fromhex("FFFFFFFF050000F00FD304"),
        "KuaijieK11Fragment:359": bytes.fromhex("FFFFFFFF0500005F052EF3"),
        "KuaijieK11Fragment:361": bytes.fromhex("FFFFFFFF05000050052B03"),
        "KuaijieK1Fragment:50": bytes.fromhex("FFFFFFFF0100090B001104"),
        "KuaijieK1Fragment:52": bytes.fromhex("FFFFFFFF0100090B011204"),
        "KuaijieK1Fragment:93": bytes.fromhex("FFFFFFFF0500000000D700"),
        "KuaijieK1Fragment:136": bytes.fromhex("FFFFFFFF050000BF0BE6F7"),
        "KuaijieK1Fragment:138": bytes.fromhex("FFFFFFFF050000B00BE307"),
        "KuaijieK1Fragment:145": bytes.fromhex("FFFFFFFF050000AF0A2AF7"),
        "KuaijieK1Fragment:147": bytes.fromhex("FFFFFFFF050000A00A2F07"),
        "KuaijieK1Fragment:203": bytes.fromhex("FFFFFFFF03002800091F0E"),
        "KuaijieK1Fragment:205": bytes.fromhex("FFFFFFFF0300310009CEC9"),
        "KuaijieK1Fragment:207": bytes.fromhex("FFFFFFFF03001600097EC2"),
        "KuaijieK1Fragment:209": bytes.fromhex("FFFFFFFF03001F0009AEC0"),
        "KuaijieK1Fragment:211": bytes.fromhex("FFFFFFFF03003A0009BF0B"),
        "KuaijieK1Fragment:226": bytes.fromhex("FFFFFFFF0500000008D6C6"),
        "KuaijieK1Fragment:237": bytes.fromhex("FFFFFFFF050000A10A2E97"),
        "KuaijieK1Fragment:249": bytes.fromhex("FFFFFFFF050000B10BE297"),
        "KuaijieK1Fragment:262": bytes.fromhex("FFFFFFFF05000051052A93"),
        "KuaijieK1Fragment:264": bytes.fromhex("FFFFFFFF05000000051703"),
        "KuaijieK1Fragment:279": bytes.fromhex("FFFFFFFF05000091097A96"),
        "KuaijieK1Fragment:281": bytes.fromhex("FFFFFFFF05000000091706"),
        "KuaijieK1Fragment:289": bytes.fromhex("FFFFFFFF05000500E4C74A"),
        "KuaijieK1Fragment:295": bytes.fromhex("FFFFFFFF0500000028D71E"),
        "KuaijieK1Fragment:301": bytes.fromhex("FFFFFFFF050000002916DE"),
        "KuaijieK1Fragment:307": bytes.fromhex("FFFFFFFF05000500E6468B"),
        "KuaijieK1Fragment:313": bytes.fromhex("FFFFFFFF050000004E5734"),
        "KuaijieK1Fragment:326": bytes.fromhex("FFFFFFFF050000F10FD294"),
        "KuaijieK1Fragment:328": bytes.fromhex("FFFFFFFF050000000F9704"),
        "KuaijieK1Fragment:341": bytes.fromhex("FFFFFFFF0500009F097EF6"),
        "KuaijieK1Fragment:343": bytes.fromhex("FFFFFFFF05000090097B06"),
        "KuaijieK1Fragment:350": bytes.fromhex("FFFFFFFF050000FF0FD6F4"),
        "KuaijieK1Fragment:352": bytes.fromhex("FFFFFFFF050000F00FD304"),
        "KuaijieK1Fragment:359": bytes.fromhex("FFFFFFFF0500005F052EF3"),
        "KuaijieK1Fragment:361": bytes.fromhex("FFFFFFFF05000050052B03"),
        "KuaijieK2Fragment:46": bytes.fromhex("FFFFFFFF0100090B001104"),
        "KuaijieK2Fragment:48": bytes.fromhex("FFFFFFFF0100090B011204"),
        "KuaijieK2Fragment:89": bytes.fromhex("FFFFFFFF0500000000D700"),
        "KuaijieK2Fragment:127": bytes.fromhex("FFFFFFFF050000BF0BE6F7"),
        "KuaijieK2Fragment:129": bytes.fromhex("FFFFFFFF050000B00BE307"),
        "KuaijieK2Fragment:136": bytes.fromhex("FFFFFFFF050000AF0A2AF7"),
        "KuaijieK2Fragment:138": bytes.fromhex("FFFFFFFF050000A00A2F07"),
        "KuaijieK2Fragment:213": bytes.fromhex("FFFFFFFF03002800039F09"),
        "KuaijieK2Fragment:215": bytes.fromhex("FFFFFFFF03003000031F0E"),
        "KuaijieK2Fragment:217": bytes.fromhex("FFFFFFFF03001800039F06"),
        "KuaijieK2Fragment:219": bytes.fromhex("FFFFFFFF03002000031ECB"),
        "KuaijieK2Fragment:221": bytes.fromhex("FFFFFFFF03003800039ECC"),
        "KuaijieK2Fragment:223": bytes.fromhex("FFFFFFFF03002800091F0E"),
        "KuaijieK2Fragment:225": bytes.fromhex("FFFFFFFF0300310009CEC9"),
        "KuaijieK2Fragment:227": bytes.fromhex("FFFFFFFF03001600097EC2"),
        "KuaijieK2Fragment:229": bytes.fromhex("FFFFFFFF03001F0009AEC0"),
        "KuaijieK2Fragment:231": bytes.fromhex("FFFFFFFF03003A0009BF0B"),
        "KuaijieK2Fragment:247": bytes.fromhex("FFFFFFFF0500000008D6C6"),
        "KuaijieK2Fragment:258": bytes.fromhex("FFFFFFFF050000A10A2E97"),
        "KuaijieK2Fragment:270": bytes.fromhex("FFFFFFFF050000B10BE297"),
        "KuaijieK2Fragment:283": bytes.fromhex("FFFFFFFF05000051052A93"),
        "KuaijieK2Fragment:285": bytes.fromhex("FFFFFFFF05000000051703"),
        "KuaijieK2Fragment:300": bytes.fromhex("FFFFFFFF05000091097A96"),
        "KuaijieK2Fragment:302": bytes.fromhex("FFFFFFFF05000000091706"),
        "KuaijieK2Fragment:317": bytes.fromhex("FFFFFFFF050000F10FD294"),
        "KuaijieK2Fragment:319": bytes.fromhex("FFFFFFFF050000000F9704"),
        "KuaijieK2Fragment:332": bytes.fromhex("FFFFFFFF0500009F097EF6"),
        "KuaijieK2Fragment:334": bytes.fromhex("FFFFFFFF05000090097B06"),
        "KuaijieK2Fragment:341": bytes.fromhex("FFFFFFFF050000FF0FD6F4"),
        "KuaijieK2Fragment:343": bytes.fromhex("FFFFFFFF050000F00FD304"),
        "KuaijieK2Fragment:350": bytes.fromhex("FFFFFFFF0500005F052EF3"),
        "KuaijieK2Fragment:352": bytes.fromhex("FFFFFFFF05000050052B03"),
        "KuaijieK2MFragment:64": bytes.fromhex("FFFFFFFF0100090B001104"),
        "KuaijieK2MFragment:66": bytes.fromhex("FFFFFFFF0100090B011204"),
        "KuaijieK2MFragment:107": bytes.fromhex("FFFFFFFF0500000000D700"),
        "KuaijieK2MFragment:166": bytes.fromhex("FFFFFFFF050000BF0BE6F7"),
        "KuaijieK2MFragment:168": bytes.fromhex("FFFFFFFF050000B00BE307"),
        "KuaijieK2MFragment:175": bytes.fromhex("FFFFFFFF050000AF0A2AF7"),
        "KuaijieK2MFragment:177": bytes.fromhex("FFFFFFFF050000A00A2F07"),
        "KuaijieK2MFragment:266": bytes.fromhex("FFFFFFFF03002800039F09"),
        "KuaijieK2MFragment:268": bytes.fromhex("FFFFFFFF03003000031F0E"),
        "KuaijieK2MFragment:270": bytes.fromhex("FFFFFFFF03001800039F06"),
        "KuaijieK2MFragment:272": bytes.fromhex("FFFFFFFF03002000031ECB"),
        "KuaijieK2MFragment:274": bytes.fromhex("FFFFFFFF03003800039ECC"),
        "KuaijieK2MFragment:276": bytes.fromhex("FFFFFFFF03002800091F0E"),
        "KuaijieK2MFragment:278": bytes.fromhex("FFFFFFFF0300310009CEC9"),
        "KuaijieK2MFragment:280": bytes.fromhex("FFFFFFFF03001600097EC2"),
        "KuaijieK2MFragment:282": bytes.fromhex("FFFFFFFF03001F0009AEC0"),
        "KuaijieK2MFragment:284": bytes.fromhex("FFFFFFFF03003A0009BF0B"),
        "KuaijieK2MFragment:300": bytes.fromhex("FFFFFFFF050000006A572F"),
        "KuaijieK2MFragment:306": bytes.fromhex("FFFFFFFF0500000008D6C6"),
        "KuaijieK2MFragment:317": bytes.fromhex("FFFFFFFF050000A10A2E97"),
        "KuaijieK2MFragment:329": bytes.fromhex("FFFFFFFF050000B10BE297"),
        "KuaijieK2MFragment:342": bytes.fromhex("FFFFFFFF05000051052A93"),
        "KuaijieK2MFragment:344": bytes.fromhex("FFFFFFFF05000000051703"),
        "KuaijieK2MFragment:359": bytes.fromhex("FFFFFFFF05000091097A96"),
        "KuaijieK2MFragment:361": bytes.fromhex("FFFFFFFF05000000091706"),
        "KuaijieK2MFragment:373": bytes.fromhex("FFFFFFFF0100130BFF1A05"),
        "KuaijieK2MFragment:375": bytes.fromhex("FFFFFFFF0100130B001B04"),
        "KuaijieK2MFragment:389": bytes.fromhex("FFFFFFFF050000F10FD294"),
        "KuaijieK2MFragment:391": bytes.fromhex("FFFFFFFF050000000F9704"),
        "KuaijieK2MFragment:404": bytes.fromhex("FFFFFFFF0500009F097EF6"),
        "KuaijieK2MFragment:406": bytes.fromhex("FFFFFFFF05000090097B06"),
        "KuaijieK2MFragment:413": bytes.fromhex("FFFFFFFF050000FF0FD6F4"),
        "KuaijieK2MFragment:415": bytes.fromhex("FFFFFFFF050000F00FD304"),
        "KuaijieK2MFragment:422": bytes.fromhex("FFFFFFFF0500005F052EF3"),
        "KuaijieK2MFragment:424": bytes.fromhex("FFFFFFFF05000050052B03"),
        "KuaijieK2MFragment:457": bytes.fromhex("FFFFFFFF0100130B001B04"),
        "KuaijieK2MFragment:466": bytes.fromhex("FFFFFFFF0100150B001D04"),
        "KuaijieK3Fragment:46": bytes.fromhex("FFFFFFFF0100090B001104"),
        "KuaijieK3Fragment:48": bytes.fromhex("FFFFFFFF0100090B011204"),
        "KuaijieK3Fragment:85": bytes.fromhex("FFFFFFFF0500000000D700"),
        "KuaijieK3Fragment:125": bytes.fromhex("FFFFFFFF050000BF0BE6F7"),
        "KuaijieK3Fragment:127": bytes.fromhex("FFFFFFFF050000B00BE307"),
        "KuaijieK3Fragment:134": bytes.fromhex("FFFFFFFF050000AF0A2AF7"),
        "KuaijieK3Fragment:136": bytes.fromhex("FFFFFFFF050000A00A2F07"),
        "KuaijieK3Fragment:183": bytes.fromhex("FFFFFFFF03002400035F0A"),
        "KuaijieK3Fragment:185": bytes.fromhex("FFFFFFFF03002C0003DEC8"),
        "KuaijieK3Fragment:187": bytes.fromhex("FFFFFFFF03001400035F05"),
        "KuaijieK3Fragment:189": bytes.fromhex("FFFFFFFF03001C0003DEC7"),
        "KuaijieK3Fragment:204": bytes.fromhex("FFFFFFFF050000002E571C"),
        "KuaijieK3Fragment:210": bytes.fromhex("FFFFFFFF050000F10FD294"),
        "KuaijieK3Fragment:221": bytes.fromhex("FFFFFFFF050000A10A2E97"),
        "KuaijieK3Fragment:233": bytes.fromhex("FFFFFFFF050000B10BE297"),
        "KuaijieK3Fragment:246": bytes.fromhex("FFFFFFFF05000051052A93"),
        "KuaijieK3Fragment:248": bytes.fromhex("FFFFFFFF05000000051703"),
        "KuaijieK3Fragment:263": bytes.fromhex("FFFFFFFF05000091097A96"),
        "KuaijieK3Fragment:265": bytes.fromhex("FFFFFFFF05000000091706"),
        "KuaijieK3Fragment:273": bytes.fromhex("FFFFFFFF050000000796C2"),
        "KuaijieK3Fragment:279": bytes.fromhex("FFFFFFFF05000000065702"),
        "KuaijieK3Fragment:290": bytes.fromhex("FFFFFFFF0500009F097EF6"),
        "KuaijieK3Fragment:292": bytes.fromhex("FFFFFFFF05000090097B06"),
        "KuaijieK3Fragment:299": bytes.fromhex("FFFFFFFF0500005F052EF3"),
        "KuaijieK3Fragment:301": bytes.fromhex("FFFFFFFF05000050052B03"),
        "KuaijieK4Fragment:55": bytes.fromhex("FFFFFFFF0100090B001104"),
        "KuaijieK4Fragment:57": bytes.fromhex("FFFFFFFF0100090B011204"),
        "KuaijieK4Fragment:99": bytes.fromhex("FFFFFFFF0500000000D700"),
        "KuaijieK4Fragment:182": bytes.fromhex("FFFFFFFF0300640009DED9"),
        "KuaijieK4Fragment:184": bytes.fromhex("FFFFFFFF03006D00090EDB"),
        "KuaijieK4Fragment:186": bytes.fromhex("FFFFFFFF03007600097EDC"),
        "KuaijieK4Fragment:188": bytes.fromhex("FFFFFFFF03007F0009AEDE"),
        "KuaijieK4Fragment:211": bytes.fromhex("FFFFFFFF05000000391712"),
        "KuaijieK4Fragment:217": bytes.fromhex("FFFFFFFF050000003A5713"),
        "KuaijieK4Fragment:229": bytes.fromhex("FFFFFFFF05000011311A84"),
        "KuaijieK4Fragment:231": bytes.fromhex("FFFFFFFF050000003116D4"),
        "KuaijieK4Fragment:245": bytes.fromhex("FFFFFFFF05000021324E85"),
        "KuaijieK4Fragment:247": bytes.fromhex("FFFFFFFF050000003256D5"),
        "KuaijieK4Fragment:261": bytes.fromhex("FFFFFFFF05000031338285"),
        "KuaijieK4Fragment:263": bytes.fromhex("FFFFFFFF05000000339715"),
        "KuaijieK4Fragment:277": bytes.fromhex("FFFFFFFF0500004134E687"),
        "KuaijieK4Fragment:279": bytes.fromhex("FFFFFFFF0500000034D6D7"),
        "KuaijieK4Fragment:295": bytes.fromhex("FFFFFFFF050000003B96D3"),
        "KuaijieK4Fragment:301": bytes.fromhex("FFFFFFFF050000003CD711"),
        "KuaijieK4Fragment:307": bytes.fromhex("FFFFFFFF050000003D16D1"),
        "KuaijieK4Fragment:332": bytes.fromhex("FFFFFFFF0500001F311EE4"),
        "KuaijieK4Fragment:334": bytes.fromhex("FFFFFFFF05000010311B14"),
        "KuaijieK4Fragment:341": bytes.fromhex("FFFFFFFF0500002F324AE5"),
        "KuaijieK4Fragment:343": bytes.fromhex("FFFFFFFF05000020324F15"),
        "KuaijieK4Fragment:350": bytes.fromhex("FFFFFFFF0500003F3386E5"),
        "KuaijieK4Fragment:352": bytes.fromhex("FFFFFFFF05000030338315"),
        "KuaijieK4Fragment:359": bytes.fromhex("FFFFFFFF0500004F34E2E7"),
        "KuaijieK4Fragment:361": bytes.fromhex("FFFFFFFF0500004034E717"),
        "KuaijieK5Fragment:57": bytes.fromhex("FFFFFFFF0100090B001104"),
        "KuaijieK5Fragment:59": bytes.fromhex("FFFFFFFF0100090B011204"),
        "KuaijieK5Fragment:107": bytes.fromhex("FFFFFFFF0500000000D700"),
        "KuaijieK5Fragment:170": bytes.fromhex("FFFFFFFF0300640009DED9"),
        "KuaijieK5Fragment:172": bytes.fromhex("FFFFFFFF03006D00090EDB"),
        "KuaijieK5Fragment:174": bytes.fromhex("FFFFFFFF03007600097EDC"),
        "KuaijieK5Fragment:176": bytes.fromhex("FFFFFFFF03007F0009AEDE"),
        "KuaijieK5Fragment:192": bytes.fromhex("FFFFFFFF0500000008D6C6"),
        "KuaijieK5Fragment:204": bytes.fromhex("FFFFFFFF05000031338285"),
        "KuaijieK5Fragment:216": bytes.fromhex("FFFFFFFF0500004134E687"),
        "KuaijieK5Fragment:229": bytes.fromhex("FFFFFFFF05000011311A84"),
        "KuaijieK5Fragment:231": bytes.fromhex("FFFFFFFF050000003116D4"),
        "KuaijieK5Fragment:245": bytes.fromhex("FFFFFFFF05000021324E85"),
        "KuaijieK5Fragment:247": bytes.fromhex("FFFFFFFF050000003256D5"),
        "KuaijieK5Fragment:261": bytes.fromhex("FFFFFFFF05000031338285"),
        "KuaijieK5Fragment:263": bytes.fromhex("FFFFFFFF05000000339715"),
        "KuaijieK5Fragment:277": bytes.fromhex("FFFFFFFF0500004134E687"),
        "KuaijieK5Fragment:279": bytes.fromhex("FFFFFFFF0500000034D6D7"),
        "KuaijieK5Fragment:289": bytes.fromhex("FFFFFFFF050000003B96D3"),
        "KuaijieK5Fragment:300": bytes.fromhex("FFFFFFFF05000031338285"),
        "KuaijieK5Fragment:312": bytes.fromhex("FFFFFFFF0500004134E687"),
        "KuaijieK5Fragment:319": bytes.fromhex("FFFFFFFF050005003E46D1"),
        "KuaijieK5Fragment:357": bytes.fromhex("FFFFFFFF0500001F311EE4"),
        "KuaijieK5Fragment:360": bytes.fromhex("FFFFFFFF05000010311B14"),
        "KuaijieK5Fragment:368": bytes.fromhex("FFFFFFFF0500002F324AE5"),
        "KuaijieK5Fragment:371": bytes.fromhex("FFFFFFFF05000020324F15"),
        "KuaijieK5Fragment:379": bytes.fromhex("FFFFFFFF0500003F3386E5"),
        "KuaijieK5Fragment:382": bytes.fromhex("FFFFFFFF05000030338315"),
        "KuaijieK5Fragment:390": bytes.fromhex("FFFFFFFF0500003F3386E5"),
        "KuaijieK5Fragment:393": bytes.fromhex("FFFFFFFF05000030338315"),
        "KuaijieK5Fragment:401": bytes.fromhex("FFFFFFFF0500004F34E2E7"),
        "KuaijieK5Fragment:404": bytes.fromhex("FFFFFFFF0500004034E717"),
        "KuaijieK5Fragment:412": bytes.fromhex("FFFFFFFF0500004F34E2E7"),
        "KuaijieK5Fragment:415": bytes.fromhex("FFFFFFFF0500004034E717"),
        "KuaijieK8Fragment:46": bytes.fromhex("FFFFFFFF0100090B001104"),
        "KuaijieK8Fragment:48": bytes.fromhex("FFFFFFFF0100090B011204"),
        "KuaijieK8Fragment:85": bytes.fromhex("FFFFFFFF0500000000D700"),
        "KuaijieK8Fragment:125": bytes.fromhex("FFFFFFFF050000BF0BE6F7"),
        "KuaijieK8Fragment:127": bytes.fromhex("FFFFFFFF050000B00BE307"),
        "KuaijieK8Fragment:134": bytes.fromhex("FFFFFFFF050000AF0A2AF7"),
        "KuaijieK8Fragment:136": bytes.fromhex("FFFFFFFF050000A00A2F07"),
        "KuaijieK8Fragment:183": bytes.fromhex("FFFFFFFF03002800039F09"),
        "KuaijieK8Fragment:185": bytes.fromhex("FFFFFFFF03003000031F0E"),
        "KuaijieK8Fragment:187": bytes.fromhex("FFFFFFFF03001800039F06"),
        "KuaijieK8Fragment:189": bytes.fromhex("FFFFFFFF03002000031ECB"),
        "KuaijieK8Fragment:191": bytes.fromhex("FFFFFFFF03003800039ECC"),
        "KuaijieK8Fragment:206": bytes.fromhex("FFFFFFFF0500000020D6D8"),
        "KuaijieK8Fragment:212": bytes.fromhex("FFFFFFFF0500000008D6C6"),
        "KuaijieK8Fragment:223": bytes.fromhex("FFFFFFFF050000A10A2E97"),
        "KuaijieK8Fragment:235": bytes.fromhex("FFFFFFFF050000B10BE297"),
        "KuaijieK8Fragment:248": bytes.fromhex("FFFFFFFF05000051052A93"),
        "KuaijieK8Fragment:250": bytes.fromhex("FFFFFFFF05000000051703"),
        "KuaijieK8Fragment:265": bytes.fromhex("FFFFFFFF05000091097A96"),
        "KuaijieK8Fragment:267": bytes.fromhex("FFFFFFFF05000000091706"),
        "KuaijieK8Fragment:275": bytes.fromhex("FFFFFFFF050000000E56C4"),
        "KuaijieK8Fragment:281": bytes.fromhex("FFFFFFFF050000000D16C5"),
        "KuaijieK8Fragment:292": bytes.fromhex("FFFFFFFF0500009F097EF6"),
        "KuaijieK8Fragment:294": bytes.fromhex("FFFFFFFF05000090097B06"),
        "KuaijieK8Fragment:301": bytes.fromhex("FFFFFFFF0500005F052EF3"),
        "KuaijieK8Fragment:303": bytes.fromhex("FFFFFFFF05000050052B03"),
        "KuaijieK9Fragment:47": bytes.fromhex("FFFFFFFF0100090B001104"),
        "KuaijieK9Fragment:49": bytes.fromhex("FFFFFFFF0100090B011204"),
        "KuaijieK9Fragment:86": bytes.fromhex("FFFFFFFF0500000000D700"),
        "KuaijieK9Fragment:126": bytes.fromhex("FFFFFFFF050000BF0BE6F7"),
        "KuaijieK9Fragment:128": bytes.fromhex("FFFFFFFF050000B00BE307"),
        "KuaijieK9Fragment:135": bytes.fromhex("FFFFFFFF050000AF0A2AF7"),
        "KuaijieK9Fragment:137": bytes.fromhex("FFFFFFFF050000A00A2F07"),
        "KuaijieK9Fragment:193": bytes.fromhex("FFFFFFFF03002800039F09"),
        "KuaijieK9Fragment:195": bytes.fromhex("FFFFFFFF03003000031F0E"),
        "KuaijieK9Fragment:197": bytes.fromhex("FFFFFFFF03001800039F06"),
        "KuaijieK9Fragment:199": bytes.fromhex("FFFFFFFF03002000031ECB"),
        "KuaijieK9Fragment:201": bytes.fromhex("FFFFFFFF03003800039ECC"),
        "KuaijieK9Fragment:216": bytes.fromhex("FFFFFFFF0500000008D6C6"),
        "KuaijieK9Fragment:227": bytes.fromhex("FFFFFFFF050000A10A2E97"),
        "KuaijieK9Fragment:239": bytes.fromhex("FFFFFFFF050000B10BE297"),
        "KuaijieK9Fragment:252": bytes.fromhex("FFFFFFFF05000051052A93"),
        "KuaijieK9Fragment:254": bytes.fromhex("FFFFFFFF05000000051703"),
        "KuaijieK9Fragment:269": bytes.fromhex("FFFFFFFF05000091097A96"),
        "KuaijieK9Fragment:271": bytes.fromhex("FFFFFFFF05000000091706"),
        "KuaijieK9Fragment:279": bytes.fromhex("FFFFFFFF050000000E56C4"),
        "KuaijieK9Fragment:285": bytes.fromhex("FFFFFFFF050000000D16C5"),
        "KuaijieK9Fragment:298": bytes.fromhex("FFFFFFFF050000F10FD294"),
        "KuaijieK9Fragment:300": bytes.fromhex("FFFFFFFF050000000F9704"),
        "KuaijieK9Fragment:313": bytes.fromhex("FFFFFFFF0500009F097EF6"),
        "KuaijieK9Fragment:315": bytes.fromhex("FFFFFFFF05000090097B06"),
        "KuaijieK9Fragment:322": bytes.fromhex("FFFFFFFF0500005F052EF3"),
        "KuaijieK9Fragment:324": bytes.fromhex("FFFFFFFF05000050052B03"),
        "LengnuanFragment:58": bytes.fromhex("FFFFFFFFFE1000010000000000AA5D4B"),
        "LengnuanFragment:183": bytes.fromhex("FFFFFFFFFE1000000000000000AA4D8B"),
        "LengnuanFragment:279:thermal slider table index 0": bytes.fromhex(
            "FFFFFFFFFE1000050000040000AA19BB"
        ),
        "LengnuanFragment:279:thermal slider table index 1": bytes.fromhex(
            "FFFFFFFFFE1000050000030000AA18CF"
        ),
        "LengnuanFragment:279:thermal slider table index 2": bytes.fromhex(
            "FFFFFFFFFE1000050000020000AA1933"
        ),
        "LengnuanFragment:279:thermal slider table index 3": bytes.fromhex(
            "FFFFFFFFFE1000050000010000AA1977"
        ),
        "LengnuanFragment:279:thermal slider table index 4": bytes.fromhex(
            "FFFFFFFFFE1000060000000000AA2B8B"
        ),
        "LengnuanFragment:279:thermal slider table index 5": bytes.fromhex(
            "FFFFFFFFFE1000040000010000AA09B7"
        ),
        "LengnuanFragment:279:thermal slider table index 6": bytes.fromhex(
            "FFFFFFFFFE1000040000020000AA09F3"
        ),
        "LengnuanFragment:279:thermal slider table index 7": bytes.fromhex(
            "FFFFFFFFFE1000040000030000AA080F"
        ),
        "LengnuanFragment:279:thermal slider table index 8": bytes.fromhex(
            "FFFFFFFFFE1000040000040000AA097B"
        ),
        "LengnuanFragment:294": bytes.fromhex("FFFFFFFFFE1000030000010000AA7F77"),
        "LengnuanFragment:296": bytes.fromhex("FFFFFFFFFE1000030000000000AA7E8B"),
        "QinangFragment:133": bytes.fromhex("FFFFFFFFFF14020900000000000000000000A640"),
        "QinangFragment:172": bytes.fromhex("FFFFFFFFFF0D030C0001004222"),
        "QinangFragment:174": bytes.fromhex("FFFFFFFFFF0D030C00000043B2"),
        "QinangFragment:184": bytes.fromhex("FFFFFFFFFF14030D000003000000000000000EA6"),
        "QinangFragment:186": bytes.fromhex("FFFFFFFFFF14030D000103000000000000000336"),
        "QinangFragment:193": bytes.fromhex("FFFFFFFFFF14030D00001200000000000000CE66"),
        "QinangFragment:195": bytes.fromhex("FFFFFFFFFF14030D00011200000000000000C3F6"),
        "QinangFragment:302": bytes.fromhex("FFFFFFFFFF0B0100005CF0"),
        "QinangFragment:313": bytes.fromhex("FFFFFFFFFF0B0112005050"),
        "QinangFragment:320": bytes.fromhex("FFFFFFFFFF0B0106005F50"),
        "QinangFragment:326": bytes.fromhex("FFFFFFFFFF0B0104005E30"),
        "QinangFragment:342": bytes.fromhex("FFFFFFFFFF0B0103005C00"),
        "QinangFragment:349": bytes.fromhex("FFFFFFFFFF0B0109005AA0"),
        "QinangFragment:355": bytes.fromhex("FFFFFFFFFF0B0105005FA0"),
        "QinangFragment:361": bytes.fromhex("FFFFFFFFFF0B010C0059F0"),
        "SmartSleepFragment:144": bytes.fromhex("FFFFFFFF050000F03FD310"),
        "SmartSleepFragment:147": bytes.fromhex("FFFFFFFF050000003F9710"),
        "SmartSleepFragment:156": bytes.fromhex("FFFFFFFF0200110B001A04"),
        "SmartSleepFragment:159": bytes.fromhex("FFFFFFFF0200110B011B04"),
        "WeitiaoW10Fragment:50": bytes.fromhex("FFFFFFFF0100090B001104"),
        "WeitiaoW10Fragment:52": bytes.fromhex("FFFFFFFF0100090B011204"),
        "WeitiaoW10Fragment:61": bytes.fromhex("FFFFFFFF05000000039701"),
        "WeitiaoW10Fragment:65": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW10Fragment:74": bytes.fromhex("FFFFFFFF0500000004D6C3"),
        "WeitiaoW10Fragment:78": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW10Fragment:88": bytes.fromhex("FFFFFFFF050000000116C0"),
        "WeitiaoW10Fragment:92": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW10Fragment:101": bytes.fromhex("FFFFFFFF050000000256C1"),
        "WeitiaoW10Fragment:105": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW10Fragment:115": bytes.fromhex("FFFFFFFF05000000065702"),
        "WeitiaoW10Fragment:119": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW10Fragment:128": bytes.fromhex("FFFFFFFF050000000796C2"),
        "WeitiaoW10Fragment:132": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW11Fragment:50": bytes.fromhex("FFFFFFFF0100090B001104"),
        "WeitiaoW11Fragment:52": bytes.fromhex("FFFFFFFF0100090B011204"),
        "WeitiaoW11Fragment:61": bytes.fromhex("FFFFFFFF05000000039701"),
        "WeitiaoW11Fragment:65": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW11Fragment:74": bytes.fromhex("FFFFFFFF0500000004D6C3"),
        "WeitiaoW11Fragment:78": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW11Fragment:88": bytes.fromhex("FFFFFFFF050000000D16C5"),
        "WeitiaoW11Fragment:92": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW11Fragment:101": bytes.fromhex("FFFFFFFF050000000E56C4"),
        "WeitiaoW11Fragment:105": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW11Fragment:115": bytes.fromhex("FFFFFFFF05000000065702"),
        "WeitiaoW11Fragment:119": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW11Fragment:128": bytes.fromhex("FFFFFFFF050000000796C2"),
        "WeitiaoW11Fragment:132": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW12Fragment:49": bytes.fromhex("FFFFFFFF0100090B001104"),
        "WeitiaoW12Fragment:51": bytes.fromhex("FFFFFFFF0100090B011204"),
        "WeitiaoW12Fragment:60": bytes.fromhex("FFFFFFFF05000000039701"),
        "WeitiaoW12Fragment:64": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW12Fragment:73": bytes.fromhex("FFFFFFFF0500000004D6C3"),
        "WeitiaoW12Fragment:77": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW12Fragment:87": bytes.fromhex("FFFFFFFF05000000065702"),
        "WeitiaoW12Fragment:91": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW12Fragment:100": bytes.fromhex("FFFFFFFF050000000796C2"),
        "WeitiaoW12Fragment:104": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW12Fragment:114": bytes.fromhex("FFFFFFFF05000000211718"),
        "WeitiaoW12Fragment:118": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW12Fragment:127": bytes.fromhex("FFFFFFFF05000000225719"),
        "WeitiaoW12Fragment:131": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW12Fragment:141": bytes.fromhex("FFFFFFFF0500000028D71E"),
        "WeitiaoW12Fragment:144": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW12Fragment:153": bytes.fromhex("FFFFFFFF050000002916DE"),
        "WeitiaoW12Fragment:156": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW13Fragment:80": bytes.fromhex("FFFFFFFF0100090B001104"),
        "WeitiaoW13Fragment:82": bytes.fromhex("FFFFFFFF0100090B011204"),
        "WeitiaoW13Fragment:96": bytes.fromhex("FFFFFFFF05000000039701"),
        "WeitiaoW13Fragment:100": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW13Fragment:109": bytes.fromhex("FFFFFFFF0500000004D6C3"),
        "WeitiaoW13Fragment:113": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW13Fragment:123": bytes.fromhex("FFFFFFFF050000000D16C5"),
        "WeitiaoW13Fragment:127": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW13Fragment:136": bytes.fromhex("FFFFFFFF050000000E56C4"),
        "WeitiaoW13Fragment:140": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW13Fragment:150": bytes.fromhex("FFFFFFFF050000000116C0"),
        "WeitiaoW13Fragment:154": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW13Fragment:163": bytes.fromhex("FFFFFFFF050000000256C1"),
        "WeitiaoW13Fragment:167": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW13Fragment:177": bytes.fromhex("FFFFFFFF05000000065702"),
        "WeitiaoW13Fragment:181": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW13Fragment:190": bytes.fromhex("FFFFFFFF050000000796C2"),
        "WeitiaoW13Fragment:194": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW13Fragment:204": bytes.fromhex("FFFFFFFF05000000211718"),
        "WeitiaoW13Fragment:208": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW13Fragment:217": bytes.fromhex("FFFFFFFF05000000225719"),
        "WeitiaoW13Fragment:221": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW13Fragment:231": bytes.fromhex("FFFFFFFF0500000028D71E"),
        "WeitiaoW13Fragment:234": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW13Fragment:243": bytes.fromhex("FFFFFFFF050000002916DE"),
        "WeitiaoW13Fragment:246": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW13Fragment:304": bytes.fromhex("FFFFFFFF05000500E4C74A"),
        "WeitiaoW13Fragment:310": bytes.fromhex("FFFFFFFF05000500E38688"),
        "WeitiaoW13Fragment:316": bytes.fromhex("FFFFFFFF05000500E5068A"),
        "WeitiaoW13Fragment:322": bytes.fromhex("FFFFFFFF05000500E6468B"),
        "WeitiaoW14Fragment:80": bytes.fromhex("FFFFFFFF0100090B001104"),
        "WeitiaoW14Fragment:82": bytes.fromhex("FFFFFFFF0100090B011204"),
        "WeitiaoW14Fragment:96": bytes.fromhex("FFFFFFFF05000000039701"),
        "WeitiaoW14Fragment:100": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW14Fragment:109": bytes.fromhex("FFFFFFFF0500000004D6C3"),
        "WeitiaoW14Fragment:113": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW14Fragment:123": bytes.fromhex("FFFFFFFF050000000D16C5"),
        "WeitiaoW14Fragment:127": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW14Fragment:136": bytes.fromhex("FFFFFFFF050000000E56C4"),
        "WeitiaoW14Fragment:140": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW14Fragment:150": bytes.fromhex("FFFFFFFF050000000116C0"),
        "WeitiaoW14Fragment:154": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW14Fragment:163": bytes.fromhex("FFFFFFFF050000000256C1"),
        "WeitiaoW14Fragment:167": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW14Fragment:177": bytes.fromhex("FFFFFFFF05000000065702"),
        "WeitiaoW14Fragment:181": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW14Fragment:190": bytes.fromhex("FFFFFFFF050000000796C2"),
        "WeitiaoW14Fragment:194": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW14Fragment:204": bytes.fromhex("FFFFFFFF05000000211718"),
        "WeitiaoW14Fragment:208": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW14Fragment:217": bytes.fromhex("FFFFFFFF05000000225719"),
        "WeitiaoW14Fragment:221": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW14Fragment:231": bytes.fromhex("FFFFFFFF0500000028D71E"),
        "WeitiaoW14Fragment:234": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW14Fragment:243": bytes.fromhex("FFFFFFFF050000002916DE"),
        "WeitiaoW14Fragment:246": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW14Fragment:304": bytes.fromhex("FFFFFFFF05000500E4C74A"),
        "WeitiaoW14Fragment:310": bytes.fromhex("FFFFFFFF05000500E38688"),
        "WeitiaoW14Fragment:316": bytes.fromhex("FFFFFFFF05000500E5068A"),
        "WeitiaoW14Fragment:322": bytes.fromhex("FFFFFFFF05000500E6468B"),
        "WeitiaoW18Fragment:78": bytes.fromhex("FFFFFFFF0100090B001104"),
        "WeitiaoW18Fragment:80": bytes.fromhex("FFFFFFFF0100090B011204"),
        "WeitiaoW18Fragment:94": bytes.fromhex("FFFFFFFF05000000039701"),
        "WeitiaoW18Fragment:98": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW18Fragment:107": bytes.fromhex("FFFFFFFF0500000004D6C3"),
        "WeitiaoW18Fragment:111": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW18Fragment:121": bytes.fromhex("FFFFFFFF050000000D16C5"),
        "WeitiaoW18Fragment:125": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW18Fragment:134": bytes.fromhex("FFFFFFFF050000000E56C4"),
        "WeitiaoW18Fragment:138": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW18Fragment:148": bytes.fromhex("FFFFFFFF050000000116C0"),
        "WeitiaoW18Fragment:152": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW18Fragment:161": bytes.fromhex("FFFFFFFF050000000256C1"),
        "WeitiaoW18Fragment:165": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW18Fragment:175": bytes.fromhex("FFFFFFFF05000000065702"),
        "WeitiaoW18Fragment:179": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW18Fragment:188": bytes.fromhex("FFFFFFFF050000000796C2"),
        "WeitiaoW18Fragment:192": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW18Fragment:250": bytes.fromhex("FFFFFFFF05000500E4C74A"),
        "WeitiaoW18Fragment:256": bytes.fromhex("FFFFFFFF05000500E38688"),
        "WeitiaoW18Fragment:262": bytes.fromhex("FFFFFFFF05000500E5068A"),
        "WeitiaoW18Fragment:268": bytes.fromhex("FFFFFFFF05000500E6468B"),
        "WeitiaoW1Fragment:78": bytes.fromhex("FFFFFFFF0100090B001104"),
        "WeitiaoW1Fragment:80": bytes.fromhex("FFFFFFFF0100090B011204"),
        "WeitiaoW1Fragment:94": bytes.fromhex("FFFFFFFF05000000039701"),
        "WeitiaoW1Fragment:98": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW1Fragment:107": bytes.fromhex("FFFFFFFF0500000004D6C3"),
        "WeitiaoW1Fragment:111": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW1Fragment:121": bytes.fromhex("FFFFFFFF050000000D16C5"),
        "WeitiaoW1Fragment:125": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW1Fragment:134": bytes.fromhex("FFFFFFFF050000000E56C4"),
        "WeitiaoW1Fragment:138": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW1Fragment:148": bytes.fromhex("FFFFFFFF050000000116C0"),
        "WeitiaoW1Fragment:152": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW1Fragment:161": bytes.fromhex("FFFFFFFF050000000256C1"),
        "WeitiaoW1Fragment:165": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW1Fragment:175": bytes.fromhex("FFFFFFFF05000000065702"),
        "WeitiaoW1Fragment:179": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW1Fragment:188": bytes.fromhex("FFFFFFFF050000000796C2"),
        "WeitiaoW1Fragment:192": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW1Fragment:250": bytes.fromhex("FFFFFFFF05000500E4C74A"),
        "WeitiaoW1Fragment:256": bytes.fromhex("FFFFFFFF05000500E38688"),
        "WeitiaoW1Fragment:262": bytes.fromhex("FFFFFFFF05000500E5068A"),
        "WeitiaoW1Fragment:268": bytes.fromhex("FFFFFFFF05000500E6468B"),
        "WeitiaoW2Fragment:78": bytes.fromhex("FFFFFFFF0100090B001104"),
        "WeitiaoW2Fragment:80": bytes.fromhex("FFFFFFFF0100090B011204"),
        "WeitiaoW2Fragment:94": bytes.fromhex("FFFFFFFF05000000039701"),
        "WeitiaoW2Fragment:98": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW2Fragment:107": bytes.fromhex("FFFFFFFF0500000004D6C3"),
        "WeitiaoW2Fragment:111": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW2Fragment:121": bytes.fromhex("FFFFFFFF050000000D16C5"),
        "WeitiaoW2Fragment:125": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW2Fragment:134": bytes.fromhex("FFFFFFFF050000000E56C4"),
        "WeitiaoW2Fragment:138": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW2Fragment:148": bytes.fromhex("FFFFFFFF050000000116C0"),
        "WeitiaoW2Fragment:152": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW2Fragment:161": bytes.fromhex("FFFFFFFF050000000256C1"),
        "WeitiaoW2Fragment:165": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW2Fragment:175": bytes.fromhex("FFFFFFFF05000000065702"),
        "WeitiaoW2Fragment:179": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW2Fragment:188": bytes.fromhex("FFFFFFFF050000000796C2"),
        "WeitiaoW2Fragment:192": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW2Fragment:250": bytes.fromhex("FFFFFFFF05000500E4C74A"),
        "WeitiaoW2Fragment:256": bytes.fromhex("FFFFFFFF05000500E38688"),
        "WeitiaoW2Fragment:262": bytes.fromhex("FFFFFFFF05000500E5068A"),
        "WeitiaoW2Fragment:268": bytes.fromhex("FFFFFFFF05000500E6468B"),
        "WeitiaoW3Fragment:78": bytes.fromhex("FFFFFFFF0100090B001104"),
        "WeitiaoW3Fragment:80": bytes.fromhex("FFFFFFFF0100090B011204"),
        "WeitiaoW3Fragment:94": bytes.fromhex("FFFFFFFF05000000039701"),
        "WeitiaoW3Fragment:98": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW3Fragment:107": bytes.fromhex("FFFFFFFF0500000004D6C3"),
        "WeitiaoW3Fragment:111": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW3Fragment:121": bytes.fromhex("FFFFFFFF050005002B871E"),
        "WeitiaoW3Fragment:125": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW3Fragment:134": bytes.fromhex("FFFFFFFF050005002CC6DC"),
        "WeitiaoW3Fragment:138": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW3Fragment:148": bytes.fromhex("FFFFFFFF050000000D16C5"),
        "WeitiaoW3Fragment:152": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW3Fragment:161": bytes.fromhex("FFFFFFFF050000000E56C4"),
        "WeitiaoW3Fragment:165": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW3Fragment:175": bytes.fromhex("FFFFFFFF05000000065702"),
        "WeitiaoW3Fragment:179": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW3Fragment:188": bytes.fromhex("FFFFFFFF050000000796C2"),
        "WeitiaoW3Fragment:192": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW3Fragment:249": bytes.fromhex("FFFFFFFF05000500E8C74F"),
        "WeitiaoW3Fragment:255": bytes.fromhex("FFFFFFFF05000500E4C74A"),
        "WeitiaoW3Fragment:261": bytes.fromhex("FFFFFFFF05000500E5068A"),
        "WeitiaoW3Fragment:267": bytes.fromhex("FFFFFFFF05000500E6468B"),
        "WeitiaoW4Fragment:47": bytes.fromhex("FFFFFFFF0100090B001104"),
        "WeitiaoW4Fragment:49": bytes.fromhex("FFFFFFFF0100090B011204"),
        "WeitiaoW4Fragment:58": bytes.fromhex("FFFFFFFF05000000039701"),
        "WeitiaoW4Fragment:62": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW4Fragment:71": bytes.fromhex("FFFFFFFF0500000004D6C3"),
        "WeitiaoW4Fragment:75": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW4Fragment:85": bytes.fromhex("FFFFFFFF05000000065702"),
        "WeitiaoW4Fragment:89": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW4Fragment:98": bytes.fromhex("FFFFFFFF050000000796C2"),
        "WeitiaoW4Fragment:102": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW6Fragment:47": bytes.fromhex("FFFFFFFF0100090B001104"),
        "WeitiaoW6Fragment:49": bytes.fromhex("FFFFFFFF0100090B011204"),
        "WeitiaoW6Fragment:58": bytes.fromhex("FFFFFFFF05000000039701"),
        "WeitiaoW6Fragment:62": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW6Fragment:71": bytes.fromhex("FFFFFFFF0500000004D6C3"),
        "WeitiaoW6Fragment:75": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW6Fragment:85": bytes.fromhex("FFFFFFFF05000000065702"),
        "WeitiaoW6Fragment:89": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW6Fragment:98": bytes.fromhex("FFFFFFFF050000000796C2"),
        "WeitiaoW6Fragment:102": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW7Fragment:76": bytes.fromhex("FFFFFFFF0100090B001104"),
        "WeitiaoW7Fragment:78": bytes.fromhex("FFFFFFFF0100090B011204"),
        "WeitiaoW7Fragment:89": bytes.fromhex("FFFFFFFF05000000039701"),
        "WeitiaoW7Fragment:93": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW7Fragment:102": bytes.fromhex("FFFFFFFF0500000004D6C3"),
        "WeitiaoW7Fragment:106": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW7Fragment:116": bytes.fromhex("FFFFFFFF050000000D16C5"),
        "WeitiaoW7Fragment:120": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW7Fragment:129": bytes.fromhex("FFFFFFFF050000000E56C4"),
        "WeitiaoW7Fragment:133": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW7Fragment:143": bytes.fromhex("FFFFFFFF050000000116C0"),
        "WeitiaoW7Fragment:147": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW7Fragment:156": bytes.fromhex("FFFFFFFF050000000256C1"),
        "WeitiaoW7Fragment:160": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW7Fragment:170": bytes.fromhex("FFFFFFFF05000000065702"),
        "WeitiaoW7Fragment:174": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW7Fragment:183": bytes.fromhex("FFFFFFFF050000000796C2"),
        "WeitiaoW7Fragment:187": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW7Fragment:197": bytes.fromhex("FFFFFFFF05000000351717"),
        "WeitiaoW7Fragment:201": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW7Fragment:210": bytes.fromhex("FFFFFFFF05000000365716"),
        "WeitiaoW7Fragment:214": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW7Fragment:224": bytes.fromhex("FFFFFFFF050000003796D6"),
        "WeitiaoW7Fragment:228": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW7Fragment:237": bytes.fromhex("FFFFFFFF0500000038D6D2"),
        "WeitiaoW7Fragment:241": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW8Fragment:75": bytes.fromhex("FFFFFFFF0100090B001104"),
        "WeitiaoW8Fragment:77": bytes.fromhex("FFFFFFFF0100090B011204"),
        "WeitiaoW8Fragment:88": bytes.fromhex("FFFFFFFF05000000039701"),
        "WeitiaoW8Fragment:92": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW8Fragment:101": bytes.fromhex("FFFFFFFF0500000004D6C3"),
        "WeitiaoW8Fragment:105": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW8Fragment:115": bytes.fromhex("FFFFFFFF050000000D16C5"),
        "WeitiaoW8Fragment:119": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW8Fragment:128": bytes.fromhex("FFFFFFFF050000000E56C4"),
        "WeitiaoW8Fragment:132": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW8Fragment:142": bytes.fromhex("FFFFFFFF05000000065702"),
        "WeitiaoW8Fragment:146": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW8Fragment:155": bytes.fromhex("FFFFFFFF050000000796C2"),
        "WeitiaoW8Fragment:159": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW8Fragment:169": bytes.fromhex("FFFFFFFF05000000351717"),
        "WeitiaoW8Fragment:173": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW8Fragment:182": bytes.fromhex("FFFFFFFF05000000365716"),
        "WeitiaoW8Fragment:186": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW8Fragment:196": bytes.fromhex("FFFFFFFF05000000065702"),
        "WeitiaoW8Fragment:200": bytes.fromhex("FFFFFFFF0500000000D700"),
        "WeitiaoW8Fragment:209": bytes.fromhex("FFFFFFFF050000000796C2"),
        "WeitiaoW8Fragment:213": bytes.fromhex("FFFFFFFF0500000000D700"),
    }
)
