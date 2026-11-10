"""Good Vibe Sleep binary leaf parsers, transcribed from this package only.

Source 733bb4/737f54 and accepted formula vectors are bound in the row116 ledger.
Malformed artifact bounds errors are rejected; no invented state fills a missing field.
"""

from __future__ import annotations

from collections.abc import Callable

from ...codec import richmat as codec

Event = tuple[str, object]


def extended(b: list[int], *, mlily: bool = False, timer_pair: bool = False) -> list[Event]:
    if b[2] != len(b):
        return []
    domain, sub, op = b[3:6]
    if mlily and (
        domain not in (1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 13)
        or domain == 1 and sub != 2
        or domain == 6 and sub == 5
    ):
        return []
    if domain not in (10, 15) and op not in (2, 3):
        return []
    result = []
    if domain == 1:
        if sub == 2 and len(b) > 9:
            result.append(
                (
                    "deviceMotorCurrentHeightStatusEvent",
                    {
                        "height": ((b[7] << 8) + b[8]) / 10,
                        "type": b[9],
                        "angle": b[10] if len(b) > 11 else -1,
                        "monitorHeight": ((b[11] << 8) + b[12]) / 10 if len(b) > 13 else 0.0,
                    },
                )
            )
        if sub == 3 and len(b) > 8:
            result.append(("deviceVersionOneMotorAngleEvent", {"position": b[6], "angle": b[8]}))
    elif domain == 2:
        if sub == 1 and (b[2] - 7) % 2 == 0:
            for i in range(6, b[2] - 1, 2):
                event = {
                    1: "deviceMassageHeadStrengthStatusEvent",
                    2: "deviceMassageFootStrengthStatusEvent",
                }.get(b[i])
                if event:
                    result.append((event, b[i + 1]))
        event = {
            2: "deviceMassageModeStatusEvent",
            4: "deviceMassageFrequencStatusEvent",
            5: "deviceMusicShakeStatusEvent",
            6: "deviceMassagePowerStatusEvent",
        }.get(sub)
        if event and b[2] > 7:
            result.append((event, b[7] == 1 if sub == 6 else b[7]))
    elif domain == 3:
        if sub == 1 and len(b) > 7:
            result.append(("deviceWhiteLedStatusEvent", b[7] == 1))
    elif domain == 14:
        if sub == 1 and b[2] > 7:
            result.append(("deviceFanGearStatusEvent", b[7]))
    elif domain == 4:
        if sub == 1 and len(b) > 9:
            result.append(
                (
                    "deviceRGBStripColorStatusEvent",
                    {"rgba_bytes": [b[7] & 255, b[8] & 255, b[9] & 255, 255]},
                )
            )
        if sub == 2 and len(b) > 8:
            result.append(("deviceRGBStripTimerStatusEvent", b[7] * 60 + b[8]))
        if sub == 3 and len(b) > 7:
            result.append(("deviceRGBStripMotionStatusEvent", b[7] == 1))
        if sub == 4 and len(b) > 7:
            result.append(("deviceRGBStripStatusEvent", b[7] == 1))
    elif domain == 5:
        if sub == 1:
            bean = {"alarm_fields": b[6:12]}
            if len(bean["alarm_fields"]) != 6:
                raise IndexError("artifact reads six alarm fields without length guard")
            result.append(
                (
                    "deviceRepeatAlarmListStatusEvent"
                    if op == 2
                    else "deviceRepeatAlarmListEscalationStatusEvent",
                    bean,
                )
            )
    elif domain == 6:
        if sub == 1 and len(b) > 7:
            result.append(("deviceAntiSnoreEvent", b[7] == 1))
        if sub == 2 and len(b) > 7:
            result.append(("deviceGetOffBedStatusEvent", b[7] == 1))
        if sub == 3:
            if len(b) < 8:
                raise IndexError("artifact sublist7..length-1 range")
            result.append(("deviceSleepAdvNameEvent", b[7:-1]))
        if sub == 4 and len(b) > 8 and (b[7] == 1) and (b[8] == 1):
            result.append(("deviceCharacteristicsSubscriptionSnoreStopPlayMusicEvent", None))
        if sub == 5 and len(b) > 7:
            _ = b[8]
            if b[7] == 1:
                result.append(("deviceAntiSnoreConfigCountEvent", b[8]))
            if b[7] == 2:
                result.append(("deviceAntiSnoreConfigTimeEvent", b[8]))
    elif domain == 7:
        if sub == 2 and len(b) > 7:
            result.append(
                (
                    "deviceCharacteristicsSubscriptionBoxLockEvent"
                    if b[7] == 1
                    else "deviceCharacteristicsSubscriptionCancelBoxLockEvent",
                    None,
                )
            )
    elif domain == 9:
        event = {
            1: "deviceMusicPlayStatusEvent",
            3: "deviceMusicBleStatusEvent",
            4: "deviceMusicUsbStatusEvent",
        }.get(sub)
        if event and b[2] > 7:
            result.append((event, b[7] == 1))
        if sub == 2 and b[2] > 7:
            if b[6] == 2:
                result.append(("deviceMusicVolumeStatusEvent", b[7]))
            if b[6] == 3:
                result.append(("deviceMusicVolumeSilentStatusEvent", b[7]))
    elif domain == 10:
        if sub in range(1, 7):
            result.append(("deviceCheckEvent", [sub, b]))
    elif domain == 11:
        if sub == 1:
            result.append(("devicePressModeEvent", b[7]))
        if sub == 2:
            result.append(("deviceStrandardAndSplitControlEvent", b[7] == 2))
        if sub == 4:
            result.append(("deviceSameAndSplitControlEvent", b[7]))
    elif domain == 16:
        if sub == 1 and b[2] > 7:
            result.append(("deviceAtomizationOpenStatusEvent", b[7]))
        if sub == 2 and b[2] > 8:
            result.append(("deviceAtomizationTimeStatusEvent", b[7:9] if timer_pair else b[8]))
    elif domain == 17:
        if sub == 2 and b[2] > 8:
            raw = b[7] << 8 | b[8]
            typ, total = (0, 0) if raw == 0 else (1, 0) if raw == 65535 else (2, raw)
            result.append(
                (
                    "deviceHeatingTimeChangeStatusEvent",
                    {"position": b[6], "type": typ, "timeSum": total},
                )
            )
        if sub == 3 and b[2] > 8:
            result.append(
                (
                    "deviceHeatingTemperatureChangeStatusEvent",
                    {"position": b[6], "temperature": b[8]},
                )
            )
        if sub == 5 and b[2] > 6:
            result.append(("deviceHeatingPadModelStatusEvent", b[6]))
    elif domain == 13:
        row = {
            1: ("Power", 7),
            2: ("Delay", 9),
            5: ("Mode", 9),
            6: ("MiteRemoval", 7),
            7: ("Sleep", 20),
            8: ("Setting", 7),
            9: ("Live", 11),
        }.get(sub)
        if row and len(b) > row[1]:
            result.append(
                (
                    "deviceBlacket" + row[0] + "StatusEvent",
                    {"type": "RMDeviceBlacketDetailsModel", "fields": {}},
                )
            )
    elif domain == 15:
        pass  # Standalone desk state has no bed consumer; keep stream progress.
    else:
        raise NotImplementedError(f"domain {domain} not yet transcribed")
    return result


ACKS: dict[tuple[int, ...], str] = {
    (110, 9, 1, 0, 120): "deviceCharacteristicsSubscriptionClockEvent",
    (110, 14, 0, 3, 127): "deviceCharacteristicsSubscriptionLightEvent",
    (110, 26, 0, 1, 137): "deviceCharacteristicsSubscriptionAromatherapyEvent",
    (110, 7, 1, 1, 119): "deviceAddAlarmSuccessEvent",
    (110, 7, 1, 2, 120): "deviceCancelAlarmSuccessEvent",
    (110, 22, 1, 1, 134): "deviceCharacteristicsSubscriptionMusicEvent",
    (110, 144, 193, 1, 192): "deviceCharacteristicsSubscriptionDetectionEvent",
    (110, 33, 0, 0, 143): "deviceCharacteristicsSubscriptionSnoreEvent",
    (110, 35, 1, 132, 22): "deviceCharacteristicsSubscriptionBoxLockEvent",
    (110, 35, 0, 132, 21): "deviceCharacteristicsSubscriptionCancelBoxLockEvent",
    (110, 35, 160, 110, 159): "deviceCharacteristicsSubscriptionSnoreStopPlayMusicEvent",
}


def common(b: list[int]) -> list[Event]:
    out: list[Event] = [(ACKS[tuple(b)], None)] if tuple(b) in ACKS else []
    if len(b) == 5 and b[:2] == [110, 144]:
        s, v = b[2:4]
        hi, lo = (s >> 4, s & 15)
        if s == 0:
            out.append(("deviceControlBoxProtocolVersionEvent", v))
        if hi == 1:
            out.append(("deviceVersionOneBedModeEvent", lo))
        if hi == 3:
            out.append(
                ("deviceVersionOneMotorAngleEvent", {"no": lo >> 2, "status": lo & 3, "angle": v})
            )
        if hi == 10:
            out.append(
                (
                    "deviceVersionOneMassageModeEvent",
                    {
                        "mode": lo >> 1,
                        "massage1": v & 7,
                        "massage2": v >> 3 & 7,
                        "massage3": (lo & 1) * 4 + (v >> 6),
                    },
                )
            )
        if hi == 11:
            out.extend(
                (
                    (name, val)
                    for name, val in zip(
                        (
                            "deviceMusicUsbStatusEvent",
                            "deviceMusicPlayStatusEvent",
                            "deviceMusicShakeStatusEvent",
                            "deviceMusicBleStatusEvent",
                        ),
                        (bool(lo & 1), bool(v & 128), bool(v & 64), bool(v & 32)),
                        strict=True,
                    )
                )
            )
        if hi == 12:
            if lo == 2:
                out.append(
                    (
                        "deviceDetectionStatusEvent",
                        {0: "start", 1: "start", 2: "stop", 3: "pause", 4: "repeat"}.get(
                            v >> 4, "start"
                        ),
                    )
                )
            if lo in (3, 4, 5, 6):
                out.append(
                    (
                        "deviceDetectionMessageEvent",
                        {"type": "RMDeviceDetectionDataDetails", "fields": {}},
                    )
                )
        if hi == 13 and lo in (1, 2):
            out.append(
                (
                    "deviceMusicVolumeStatusEvent"
                    if lo == 1
                    else "deviceMusicShakeGearStatusEvent",
                    v,
                )
            )
    return out


class Notifications:
    """Retained framing with the shipped 500 ms partial-record expiry."""

    def __init__(self, emit: Callable[[str, object], None], *, mlily: bool = False, timer_pair: bool = False) -> None:
        self.emit = emit
        self.mlily = mlily
        self.timer_pair = timer_pair
        self.buffer = bytearray()
        self.rejection: str | None = None

    def clear(self) -> None:
        self.buffer.clear()

    def feed(self, data: bytes) -> None:
        self.buffer.extend(data)
        try:
            while len(self.buffer) >= 3:
                try:
                    start = self.buffer.index(0x6E)
                except ValueError:
                    self.clear()
                    break
                del self.buffer[:start]
                if len(self.buffer) < 3:
                    break
                code = self.buffer[1]
                if code == 0x20 or code == 0x21 and not self.mlily:
                    length = self.buffer[2]
                elif code == 0x40:
                    if len(self.buffer) < 4:
                        break
                    length = int.from_bytes(self.buffer[2:4], "big")
                else:
                    try:
                        length = self.buffer.index(0x6E, 1)
                    except ValueError:
                        length = len(self.buffer)
                if length == 0:
                    raise ValueError("Zero-length notification cannot make progress")
                if len(self.buffer) < length:
                    break
                frame = list(self.buffer[:length])
                del self.buffer[:length]
                # Desk/firmware records remain framed but have no bed-state consumer.
                if code == 0x40 or code == 0x21 and not self.mlily:
                    continue
                if code == 0x20:
                    if len(frame) < 7 or not codec.is_valid(bytes(frame)):
                        continue
                    events = extended(frame, mlily=self.mlily, timer_pair=self.timer_pair)
                else:
                    events = common(frame)
                for event, value in events:
                    self.emit(event, value)
            self.rejection = None
        except (ValueError, IndexError, NotImplementedError) as err:
            self.rejection = str(err)
            self.clear()
