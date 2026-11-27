"""Alya's GATT roles, clock/alarm fields and bounded report parsing (row090)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Final

from ...codec import keeson, okin_nframe
from ...profiles.alya import AlyaProfile, Protocol

if TYPE_CHECKING:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic


@dataclass(frozen=True)
class Transport:
    write_service: str
    write: str
    notify_service: str
    notify: str


TRANSPORTS: Final = {
    "P1": Transport(
        "00001000-0000-1000-8000-00805f9b34fb",
        "00001001-0000-1000-8000-00805f9b34fb",
        "00001000-0000-1000-8000-00805f9b34fb",
        "00001002-0000-1000-8000-00805f9b34fb",
    ),
    "P2": Transport(
        "0000ffe5-0000-1000-8000-00805f9b34fb",
        "0000ffe9-0000-1000-8000-00805f9b34fb",
        "0000ffe0-0000-1000-8000-00805f9b34fb",
        "0000ffe4-0000-1000-8000-00805f9b34fb",
    ),
    **dict.fromkeys(
        ("P3", "P4"),
        Transport(
            "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
            "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
            "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
            "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
        ),
    ),
}


def require_roles(
    client: BleakClient, protocol: Protocol
) -> tuple[BleakGATTCharacteristic, BleakGATTCharacteristic]:
    """Select exact service/characteristic objects, shared by setup and runtime."""
    route = TRANSPORTS[protocol]
    write = notify = None
    for service in client.services:
        for char in service.characteristics:
            if (
                service.uuid.lower() == route.write_service
                and char.uuid.lower() == route.write
                and {"write", "write-without-response"}.intersection(char.properties)
            ):
                write = char
            if (
                service.uuid.lower() == route.notify_service
                and char.uuid.lower() == route.notify
                and "notify" in char.properties
            ):
                notify = char
    if write is None or notify is None:
        raise ValueError("Selected Alya layout is missing its exact write/notify GATT roles")
    return write, notify


def bcd(value: int) -> int:
    return value // 10 * 16 + value % 10


def clock_frame(protocol: Protocol, now: datetime) -> bytes:
    if protocol == "P1":
        raise ValueError("This Alya layout has no clock")
    if protocol == "P2":
        return keeson.checked(
            bytes(
                (
                    0xE7,
                    0x80,
                    1,
                    (now.year - 1900) & 255,
                    now.month - 1,
                    now.day,
                    now.hour,
                    now.minute,
                    now.second,
                )
            )
        )
    fields = (
        now.year - 2000,
        now.month,
        now.day,
        (now.weekday() + 1) % 7,
        now.hour,
        now.minute,
        now.second,
    )
    return okin_nframe.clock(tuple(bcd(v) if protocol == "P4" else v for v in fields))


def alarm_types(profile: AlyaProfile) -> dict[str, int]:
    if profile.protocol == "P4":
        return {"memory_1": 20, "zero_g": 13, "massage": 9}
    result = {"none": 0, "zero_g": 13, "anti_snore": 16, "massage": 9}
    if profile.protocol == "P2" or profile.motors == 4:
        result.update(memory_1=17, lounge=14, tv=15)
    else:
        result.update(memory_1=20, memory_2=19)
    if profile.device_type != "CB1221":
        result["light"] = 18
    if profile.protocol == "P3":
        result["flat"] = 21
    return result


def alarm_frame(
    protocol: Protocol, hour: int, minute: int, repeat: int, kind: int, side: int = 0
) -> bytes:
    """Encode all four caller fields, without reading cached UI defaults."""
    if protocol == "P1":
        raise ValueError("This Alya layout has no alarm")
    if protocol == "P2":
        return keeson.checked(bytes((0xED, 0x80, 3, hour, minute, repeat & 255, kind)) + bytes(8))
    if protocol == "P4":
        code = {9: 1, 13: 2, 20: 3}.get(kind, 0)
        fields = (
            repeat & 255,
            bcd(code),
            bcd(hour),
            bcd(minute),
            0,
            int(any((hour, minute, repeat, kind))),
            bcd(side),
        )
    else:
        code = {13: 1, 14: 2, 15: 3, 16: 4, 17: 5, 20: 5, 19: 6, 18: 7, 9: 8, 21: 9}.get(kind, 0)
        fields = (
            0 if repeat in (-128, 128) else repeat & 255,
            code,
            hour,
            minute,
            0,
            int(any((hour, minute, repeat, kind))),
            side,
        )
    return okin_nframe.alarm(fields)


def query(protocol: Protocol, alarm: bool = False) -> bytes:
    if protocol == "P1":
        from ...codec import okin_ore

        return okin_ore.frame(0x2050)
    if protocol == "P2":
        return (
            keeson.checked(bytes((0xE2, 0x80, 3, 0)))
            if alarm
            else keeson.frame(3, header=0xE6, side=0)
        )
    return okin_nframe.request(0xC0 if alarm else 0xB0)


def signed(value: int) -> int:
    return value if value < 128 else value - 256


def parse(profile: AlyaProfile, data: bytes) -> dict[str, int | bool]:
    """Complete deliveries only. Preserve signed values and actual parser routing.

    Reject the app's weak ORE header and out-of-bounds reads. No checksum or ACK
    correlation is invented. Missing fields never become placeholder zeroes.
    """
    if profile.protocol == "P1":
        if len(data) < 7 or data[:2] != b"\xa5\x5a":
            return {}
        op = (signed(data[5]) << 8) + signed(data[6])
        if op == 0x2050 and len(data) >= 14:
            return {
                "head": signed(data[8]),
                "foot": signed(data[9]),
                "minutes": {1: 10, 2: 20, 3: 30}.get(data[10], 0),
                "wave": signed(data[11]),
                "light": signed(data[12]) > 0,
                "massage": signed(data[13]) > 0,
            }
        key = {
            0x2080: "light",
            0x2081: "massage",
            0x2082: "minutes",
            0x2083: "wave",
            0x2084: "head",
            0x2085: "foot",
            0x2090: "wave",
            0x2091: "wave",
            0x2092: "head",
            0x2093: "head",
            0x2094: "foot",
            0x2095: "foot",
        }.get(op)
        if key and len(data) >= 9:
            return {key: signed(data[8]) > 0 if key in ("light", "massage") else signed(data[8])}
        ack = {0x2060: 5, 0x2061: 3, 0x2062: 6, 0x2063: 2, 0x2064: 4}.get(op)
        return {"ack": ack} if ack is not None else {}
    if profile.device_type in ("CB24", "CB1221") or profile.protocol == "P4":
        if len(data) < 10:
            return {}
        if data[1] == 0xB:
            timer = signed(data[4])
            result: dict[str, int | bool] = {
                "minutes": 30 if timer > 4 else 20 if timer > 2 else 10 if timer > 0 else 0,
                "massage": timer > 0,
                "wave": signed(data[6]) - 1,
            }
            for key, index in (("head", 7), ("foot", 8)):
                raw = signed(data[index])
                value = raw if profile.protocol == "P4" else {0: 0, 1: 1, 3: 2, 6: 3}.get(raw)
                if value is not None:
                    result[key] = value
            return result
        if data[1] == 0xC:
            hour, minute = signed(data[6]), signed(data[7])
            types = (
                {1: 9, 2: 13, 3: 20}
                if profile.protocol == "P4"
                else {1: 13, 2: 14, 3: 15, 4: 16, 5: 20, 6: 19, 7: 18, 8: 9, 9: 21}
            )
            if profile.protocol == "P4":
                hour, minute = hour // 16 * 10 + hour % 16, minute // 16 * 10 + minute % 16
            return {
                "alarm_repeat": signed(data[4]),
                "alarm_kind": types.get(signed(data[5]), 0),
                "alarm_hour": hour,
                "alarm_minute": minute,
                "alarm_enabled": data[9] == 1,
            }
        return {}
    # DACHENG two-motor is deliberately Sino inbound, despite its P3 outbound.
    if data[:2] == b"\xed\x80" and len(data) >= 7:
        h, m, r, k = (signed(data[i]) for i in (3, 4, 5, 6))
        return {
            "alarm_hour": h,
            "alarm_minute": m,
            "alarm_repeat": r,
            "alarm_kind": k,
            "alarm_enabled": any((h, m, r, k)),
        }
    if len(data) == 23:
        t, h, f, w = data[19], data[11] & 15, data[12], data[21]
    elif len(data) == 16:
        t, h, f, w = data[14] & 15, data[7] & 15, data[8] & 15, data[14] >> 4
    elif len(data) == 10:
        t, h, f, w = data[8], 0, 0, 0
    else:
        return {}

    def level(value: int) -> int:
        return 1 if value in (1, 2) else 2 if value in (3, 4) else 3 if value in (5, 6) else 0

    return {
        "minutes": {1: 10, 2: 20, 3: 30}.get(t, 0),
        "head": level(h),
        "foot": level(f),
        "wave": {1: 0, 2: 1, 3: 2, 4: 3}.get(w, 0),
    }
