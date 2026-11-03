"""HJBed receive leaves, preserving ordered event effects and exact guards.

Malformed-leaf IndexError is caught by the controller after prior event effects.
Desk/firmware-only leaves are excluded in the durable row121 ledger.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import cast

type Value = str | int | float | bool | None | list[Value] | dict[str, Value]
type Event = tuple[str, Value]
type EventSink = Callable[[str, Value], None]


def sum8(values: list[int]) -> int:
    return sum(values) & 255


STATIC = [
    {
        "frame": "6e09010078",
        "line": 5244,
        "event": "deviceCharacteristicsSubscriptionClockEvent",
        "logs": ["RMBlueToothUtil 有闹钟功能"],
        "checksum_valid": True,
    },
    {
        "frame": "6e0e00037f",
        "line": 5280,
        "event": "deviceCharacteristicsSubscriptionLightEvent",
        "logs": ["RMBlueToothUtil 有灯光功能"],
        "checksum_valid": True,
    },
    {
        "frame": "6e1a000189",
        "line": 5316,
        "event": "deviceCharacteristicsSubscriptionAromatherapyEvent",
        "logs": ["RMBlueToothUtil 有香薰功能"],
        "checksum_valid": True,
    },
    {
        "frame": "6e07010177",
        "line": 5352,
        "event": "deviceAddAlarmSuccessEvent",
        "logs": ["RMBlueToothUtil 添加闹钟成功"],
        "checksum_valid": True,
    },
    {
        "frame": "6e07010278",
        "line": 5388,
        "event": "deviceCancelAlarmSuccessEvent",
        "logs": ["RMBlueToothUtil 取消闹钟成功"],
        "checksum_valid": True,
    },
    {
        "frame": "6e16010186",
        "line": 5424,
        "event": "deviceCharacteristicsSubscriptionMusicEvent",
        "logs": ["RMBlueToothUtil 有音乐振子功能"],
        "checksum_valid": True,
    },
    {
        "frame": "6e90c101c0",
        "line": 5460,
        "event": "deviceCharacteristicsSubscriptionDetectionEvent",
        "logs": ["RMBlueToothUtil 有异常检测功能"],
        "checksum_valid": True,
    },
    {
        "frame": "6e2100008f",
        "line": 5496,
        "event": "deviceCharacteristicsSubscriptionSnoreEvent",
        "logs": ["RMBlueToothUtil 有打鼾干预功能"],
        "checksum_valid": True,
    },
    {
        "frame": "6e23018416",
        "line": 5532,
        "event": "deviceCharacteristicsSubscriptionBoxLockEvent",
        "logs": ["RMBlueToothUtil 有控制盒锁定功能"],
        "checksum_valid": True,
    },
    {
        "frame": "6e23008415",
        "line": 5568,
        "event": "deviceCharacteristicsSubscriptionCancelBoxLockEvent",
        "logs": ["RMBlueToothUtil 有控制盒锁定解除功能"],
        "checksum_valid": True,
    },
    {
        "frame": "6e23a06e9f",
        "line": 5604,
        "event": "deviceCharacteristicsSubscriptionSnoreStopPlayMusicEvent",
        "logs": ["RMBlueToothUtil 有打鼾干预页面，收到回传停止播放音乐功能"],
        "checksum_valid": True,
    },
]


def be(f: list[int], i: int) -> int:
    return (f[i] << 8) | f[i + 1]


def base100(f: list[int], i: int) -> float:
    return (100 * f[i] + f[i + 1]) / 10


def parse_frame(
    values: Sequence[int], check_integrity: bool = True, _event_sink: EventSink | None = None
) -> list[Event]:
    """f is one frame already delimited by the app's stream handler."""
    f = list(values)
    out: list[Event] = []
    n = len(f)

    def emit(e: str, v: Value = None) -> None:
        out.append((e, v))
        if _event_sink:
            _event_sink(e, v)

    if len(f) < 2:
        return out
    if f[1] in (0x20, 0x21):
        if check_integrity and sum8(f[:-1]) != f[-1]:
            return out
        if f[2] != n:
            return out
        group = f[3]
        sel = f[4]
        op = f[5]  # source7027d4/7027fc/702824 unchecked ordered indexing
        if f[1] == 0x21:
            return out
        if group == 10:
            if sel in range(1, 7):
                emit("deviceCheckEvent", [sel, cast(list[Value], list(f))])
            return out
        if group == 5:
            if sel == 1 and n >= 13:
                data = f[12:-1] if n > 13 and (f[7] == 1 or (f[7] == 0 and f[10] == 255)) else []
                bean = {
                    "number": f[6],
                    "kind": f[7],
                    "hour": f[8],
                    "minute": f[9],
                    "code": f[10],
                    "repeat": f[11],
                    "data": data,
                }
                if op == 2:
                    emit("deviceRepeatAlarmListStatusEvent", bean)
                if op == 3:
                    emit("deviceRepeatAlarmListEscalationStatusEvent", bean)
            return out
        if op not in (2, 3):
            return out
        if group == 1:
            if sel == 2:
                if f[6] != 0:
                    if n - 7 >= 3 and (n - 7) % 3 == 0:
                        emit(
                            "deviceMotorCurrentTravelStatusEvent",
                            [
                                {"position": f[i], "travel": be(f, i + 1)}
                                for i in range(6, n - 1, 3)
                            ],
                        )
                elif n > 9:
                    emit(
                        "deviceMotorCurrentHeightStatusEvent",
                        {
                            "height": be(f, 7) / 10,
                            "type": f[9],
                            "angle": f[10] if n > 11 else -1,
                            "monitorHeight": be(f, 11) / 10 if n > 13 else 0,
                        },
                    )
            if sel == 3 and n - 7 >= 3 and (n - 7) % 3 == 0:
                emit(
                    "deviceMotorCurrentAngleStatusEvent",
                    [{"position": f[i], "angle": be(f, i + 1)} for i in range(6, n - 1, 3)],
                )
        elif group == 2:
            if sel == 1 and (f[2] - 7) % 2 == 0:
                for i in range(6, f[2] - 1, 2):
                    if f[i] == 1:
                        emit("deviceMassageHeadStrengthStatusEvent", f[i + 1])
                    if f[i] == 2:
                        emit("deviceMassageFootStrengthStatusEvent", f[i + 1])
            if f[2] > 7:
                es = {
                    2: "deviceMassageModeStatusEvent",
                    4: "deviceMassageFrequencStatusEvent",
                    5: "deviceMusicShakeStatusEvent",
                    6: "deviceMassagePowerStatusEvent",
                }
                if sel in es:
                    emit(es[sel], f[7] == 1 if sel == 6 else f[7])
        elif group == 3:
            if sel == 1 and n > 7:
                emit("deviceWhiteLedStatusEvent", f[7] == 1)
        elif group == 4:
            if sel == 1 and n > 9:
                emit(
                    "deviceRGBStripColorStatusEvent",
                    {
                        "alpha": 1,
                        "r": (f[7] & 255) / 255,
                        "g": (f[8] & 255) / 255,
                        "b": (f[9] & 255) / 255,
                    },
                )
            if sel == 2 and n > 8:
                emit("deviceRGBStripTimerStatusEvent", f[7] * 60 + f[8])
            if sel == 3 and n > 7:
                emit("deviceRGBStripMotionStatusEvent", f[7] == 1)
            if sel == 4 and n > 7:
                emit("deviceRGBStripStatusEvent", f[7] == 1)
        elif group == 6:
            if sel == 1 and n > 7:
                emit("deviceAntiSnoreEvent", f[7] == 1)
            if sel == 2 and n > 7:
                emit("deviceGetOffBedStatusEvent", f[7] == 1)
            if sel == 3:
                emit("deviceSleepAdvNameEvent", cast(list[Value], list(f[7:-1])))
            if sel == 4 and n > 8 and f[7] == 1 and f[8] == 1:
                emit("deviceCharacteristicsSubscriptionSnoreStopPlayMusicEvent")
            if sel == 5 and n > 7:
                if f[7] == 1:
                    emit("deviceAntiSnoreConfigCountEvent", f[8])
                if f[7] == 2:
                    emit("deviceAntiSnoreConfigTimeEvent", f[8])
        elif group == 7:
            if sel == 2 and n > 7:
                emit(
                    "deviceCharacteristicsSubscriptionBoxLockEvent"
                    if f[7] == 1
                    else "deviceCharacteristicsSubscriptionCancelBoxLockEvent"
                )
        elif group == 9 and f[2] > 7:
            if sel == 1:
                emit("deviceMusicPlayStatusEvent", f[7] == 1)
            if sel == 2 and f[6] == 2:
                emit("deviceMusicVolumeStatusEvent", f[7])
            if sel == 2 and f[6] == 3:
                emit("deviceMusicVolumeSilentStatusEvent", f[7])
            if sel == 3:
                emit("deviceMusicBleStatusEvent", f[7] == 1)
            if sel == 4:
                emit("deviceMusicUsbStatusEvent", f[7] == 1)
        elif group == 11:
            if sel == 1:
                emit("devicePressModeEvent", f[7])
            if sel == 2:
                emit("deviceStrandardAndSplitControlEvent", f[7] == 2)
            if sel == 4:
                emit("deviceSameAndSplitControlEvent", f[7])
        elif group == 13:
            guards = {1: 7, 2: 9, 5: 9, 6: 7, 7: 20, 8: 7, 9: 11}
            names = {
                1: "Power",
                2: "Delay",
                5: "Mode",
                6: "MiteRemoval",
                7: "Sleep",
                8: "Setting",
                9: "Live",
            }
            if sel in guards and n > guards[sel]:
                emit("deviceBlacket" + names[sel] + "StatusEvent", {})
        elif group == 14:
            if sel == 1 and f[2] > 7:
                emit("deviceFanGearStatusEvent", f[7])
        elif group == 15:
            if n < 20:
                m = n - 7
                if sel == 1 and m >= 2 and m % 2 == 0:
                    emit(
                        "deviceCoaxingSleepRunningStatusEvent",
                        [{"number": f[i], "enabled": f[i + 1] == 1} for i in range(6, n - 1, 2)],
                    )
                if sel == 2 and m >= 4 and m % 4 == 0:
                    emit(
                        "deviceCoaxingSleepTimerStatusEvent",
                        [{"number": f[i], "minute": be(f, i + 2)} for i in range(6, n - 1, 4)],
                    )
        elif group == 16:
            if sel == 1 and f[2] > 7:
                emit("deviceAtomizationOpenStatusEvent", f[7])
            if sel == 2 and f[2] > 8:
                emit("deviceAtomizationTimeStatusEvent", f[8])
        elif group == 17:
            if sel == 2 and f[2] > 8:
                v = be(f, 7)
                typ = 0 if v == 0 else 1 if v == 65535 else 2
                emit(
                    "deviceHeatingTimeChangeStatusEvent",
                    {"position": f[6], "type": typ, "timeSum": v if typ == 2 else 0},
                )
            if sel == 3 and f[2] > 8:
                emit(
                    "deviceHeatingTemperatureChangeStatusEvent",
                    {"position": f[6], "temperature": f[8]},
                )
            if sel == 5 and f[2] > 6:
                emit("deviceHeatingPadModelStatusEvent", f[6])
        return out
    if f[1] == 0x40:
        return out
    return parse_common(f, _event_sink=_event_sink)


def parse_common(values: Sequence[int], _event_sink: EventSink | None = None) -> list[Event]:
    """Direct common handler, separately callable from stream dispatch for shadow tests."""
    f = list(values)
    n = len(f)
    out: list[Event] = []

    def emit(e: str, v: Value = None) -> None:
        out.append((e, v))
        if _event_sink:
            _event_sink(e, v)

    # Common handler has no generic integrity check.
    if n == 5:
        for row in STATIC:
            raw = row.get("bytes", row.get("frame"))
            if isinstance(raw, str):
                raw = list(bytes.fromhex(raw))
            if f == raw:
                for e in row.get("events", [row.get("event")]):
                    if e:
                        emit(e)
        if f[:2] == [0x6E, 0x90]:
            b, v = f[2:4]
            hi = b >> 4
            if b == 0:
                emit("deviceControlBoxProtocolVersionEvent", v)
            if hi == 1:
                emit("deviceVersionOneBedModeEvent", b & 15)
            if hi == 3:
                emit(
                    "deviceMotorCurrentAngleStatusEvent",
                    [{"no": (b >> 2) & 3, "status": b & 3, "angle": v}],
                )
            if hi == 10:
                z = ((b & 15) << 8) | v
                emit(
                    "deviceVersionOneMassageModeEvent",
                    {
                        "mode": (z >> 9) & 7,
                        "massage1": z & 7,
                        "massage2": (z >> 3) & 7,
                        "massage3": (z >> 6) & 7,
                    },
                )
            if hi == 11:
                for e, val in [
                    ("deviceMusicUsbStatusEvent", bool(b & 1)),
                    ("deviceMusicPlayStatusEvent", bool(v & 128)),
                    ("deviceMusicShakeStatusEvent", bool(v & 64)),
                    ("deviceMusicBleStatusEvent", bool(v & 32)),
                ]:
                    emit(e, val)
            if hi == 12 and (b & 15) == 2:
                emit(
                    "deviceDetectionStatusEvent",
                    {1: "start", 2: "stop", 3: "pause", 4: "repeat"}.get(v >> 4, "start"),
                )
            if hi == 12 and b & 15 in (3, 4, 5, 6):
                emit("deviceDetectionMessageEvent", {})
            if b == 0xD1:
                emit("deviceMusicVolumeStatusEvent", v)
            if b == 0xD2:
                emit("deviceMusicShakeGearStatusEvent", v)
    return out
