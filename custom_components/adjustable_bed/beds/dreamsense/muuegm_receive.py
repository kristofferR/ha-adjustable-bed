"""MUUEGM's bounded notification grammar and repeat-alarm consumers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Final

from ...codec import richmat as codec
from .receive import Receive

LITERALS: Final = {
    "6e09010078": ("deviceCharacteristicsSubscriptionClockEvent", "IN_SCOPE"),
    "6e0e00037f": ("deviceCharacteristicsSubscriptionLightEvent", "IN_SCOPE"),
    "6e1a000189": ("deviceCharacteristicsSubscriptionAromatherapyEvent", "IN_SCOPE"),
    "6e07010177": ("deviceAddAlarmSuccessEvent", "IN_SCOPE"),
    "6e07010278": ("deviceCancelAlarmSuccessEvent", "IN_SCOPE"),
    "6e16010186": ("deviceCharacteristicsSubscriptionMusicEvent", "EXCLUDED"),
    "6e90c101c0": ("deviceCharacteristicsSubscriptionDetectionEvent", "IN_SCOPE"),
    "6e2100008f": ("deviceCharacteristicsSubscriptionSnoreEvent", "IN_SCOPE"),
}


def decode(data: bytes) -> dict[str, object] | None:
    if literal := LITERALS.get(data.hex()):
        return {"event": literal[0], "scope": literal[1]}
    if len(data) == 5 and data[:2] == b"\x6e\x90":
        subtype, low = data[2] >> 4, data[2] & 15
        if subtype == 0 and low == 0:
            return {"event": "deviceControlBoxProtocolVersionEvent", "value": data[3]}
        if subtype == 1:
            return {"event": "deviceVersionOneBedModeEvent", "value": low}
        if subtype == 3:
            return {
                "event": "deviceVersionOneMotorAngleEvent",
                "value": {"no": (data[2] >> 2) & 3, "status": data[2] & 3, "angle": data[3]},
            }
        if subtype == 10:
            value = (low << 8) | data[3]
            return {
                "event": "deviceVersionOneMassageModeEvent",
                "value": {
                    "mode": (value >> 9) & 7,
                    "massage3": (value >> 6) & 7,
                    "massage2": (value >> 3) & 7,
                    "massage1": value & 7,
                },
            }
    if len(data) < 7 or data[:2] != b"\x6e\x20" or len(data) != data[2] or not codec.is_valid(data):
        return None
    if data[3] == 1 and data[4] == 2 and data[5] in (2, 3) and len(data) > 9:
        return {
            "event": "deviceMotorCurrentHeightStatusEvent",
            "value": {
                "height": int.from_bytes(data[7:9], "big") / 10,
                "type": data[9],
                "angle": data[10] if len(data) > 11 else -1,
                "monitorHeight": int.from_bytes(data[11:13], "big") / 10 if len(data) > 13 else 0,
            },
        }
    if data[3] == 5 and data[4] == 1 and data[5] in (2, 3) and len(data) >= 13:
        return {
            "event": "deviceRepeatAlarmListStatusEvent"
            if data[5] == 2
            else "deviceRepeatAlarmListEscalationStatusEvent",
            "value": asdict(Alarm(*data[6:12])),
        }
    if data[3] == 3 and data[4] == 1 and data[5] in (2, 3) and len(data) > 7:
        return {"event": "deviceWhiteLedStatusEvent", "value": data[7] == 1}
    return None


@dataclass(frozen=True, slots=True)
class Alarm:
    id: int
    reserved: int
    hour: int
    minute: int
    mode: int
    repeat_mask: int

    def frame(self) -> bytes:
        return codec.record_20_len(
            5, 1, 1, (self.id, self.reserved, self.hour, self.minute, self.mode, self.repeat_mask)
        )


@dataclass(slots=True)
class MuuegmReceive(Receive):
    records: list[Alarm] = field(default_factory=list)
    events: dict[str, object] = field(default_factory=dict)
    frames: list[dict[str, str]] = field(default_factory=list)
    acknowledgements: list[str] = field(default_factory=list)
    revision: int = 0

    def feed(self, data: bytes) -> None:
        self.frames.clear()
        self.acknowledgements.clear()
        self.pending.extend(data)
        while len(self.pending) >= 3:
            start = self.pending.find(0x6E)
            if start < 0:
                self.pending.clear()
                break
            del self.pending[:start]
            if len(self.pending) < 3:
                break
            extra = self.pending[1] == 0x20
            if extra:
                size = self.pending[2]
                # Reject nonprogressing/short frames rather than copying an app crash.
                if size < 3:
                    self.pending.clear()
                    break
                if len(self.pending) < size:
                    break
            else:
                size = self.pending.find(0x6E, 1)
                size = len(self.pending) if size < 0 else size
            frame = bytes(self.pending[:size])
            del self.pending[:size]
            dispatch = "extra" if extra else "common"
            if extra and not codec.is_valid(frame):
                dispatch = "drop_checksum"
            self.frames.append({"frame": frame.hex(" "), "dispatch": dispatch})
            if dispatch == "drop_checksum":
                continue
            event = decode(frame)
            if event is None or event.get("scope") == "EXCLUDED":
                continue
            name = str(event["event"])
            self.events[name] = event.get("value", True)
            if name == "deviceCharacteristicsSubscriptionClockEvent":
                self.capabilities.add("clock")
            elif name == "deviceCharacteristicsSubscriptionLightEvent":
                self.capabilities.add("light")
            elif name == "deviceAddAlarmSuccessEvent":
                self.last_ack = "alarm_added"
                self.acknowledgements.append(self.last_ack)
            elif name == "deviceCancelAlarmSuccessEvent":
                self.last_ack = "alarm_cancelled"
                self.acknowledgements.append(self.last_ack)
            elif name in (
                "deviceRepeatAlarmListStatusEvent",
                "deviceRepeatAlarmListEscalationStatusEvent",
            ):
                alarm = Alarm(*frame[6:12])
                if frame[5] == 2:
                    if alarm not in self.records:
                        self.records.append(alarm)
                        self.revision += 1
                else:
                    index = next(
                        (i for i, old in enumerate(self.records) if old.id == alarm.id), None
                    )
                    if index is not None:
                        self.records[index] = alarm
                        self.revision += 1
