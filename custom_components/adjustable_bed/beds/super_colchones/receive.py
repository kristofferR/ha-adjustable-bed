"""Super Colchones's native event fields, without inferred product capabilities.

Malformed app accesses are bounded at HA's notification boundary. Alarm fields
retain their recovered storage names, and diagnostic details remain fieldless.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from ...codec import richmat as codec
from ...profiles.super_colchones import RESIDUAL_EXPIRY_S


@dataclass(frozen=True, slots=True)
class Event:
    name: str
    value: object = None

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {"event": self.name}
        if self.value is not None:
            result["value"] = self.value
        return result


_FIXED = {
    "6e09010078": "deviceCharacteristicsSubscriptionClockEvent",
    "6e0e00037f": "deviceCharacteristicsSubscriptionLightEvent",
    "6e1a000189": "deviceCharacteristicsSubscriptionAromatherapyEvent",
    "6e07010177": "deviceAddAlarmSuccessEvent",
    "6e07010278": "deviceCancelAlarmSuccessEvent",
    "6e90c101c0": "deviceCharacteristicsSubscriptionDetectionEvent",
    "6e2100008f": "deviceCharacteristicsSubscriptionSnoreEvent",
    "6e23018416": "deviceCharacteristicsSubscriptionBoxLockEvent",
    "6e23008415": "deviceCharacteristicsSubscriptionCancelBoxLockEvent",
}


def decode(b: bytes) -> list[Event]:
    """Decode one extracted frame. Excluded music/non-bed/OTA domains emit nothing."""
    try:
        return _decode(b)
    except (IndexError, ValueError):
        # The Android implementation may throw on malformed fields. Never let
        # an unchecked payload escape HA's BLE callback or synthesize a value.
        return []


def _decode(b: bytes) -> list[Event]:
    n = len(b)
    if n == 5:
        if name := _FIXED.get(b.hex()):
            return [Event(name)]
        if b[:2] != b"\x6e\x90":
            return []
        high, low, value = b[2] >> 4, b[2] & 15, b[3]
        if b[2] == 0:
            return [Event("deviceProtocolVersionEvent", value)]
        if high == 1:
            return [Event("deviceVersionOneBedModeEvent", low)]
        if high == 3:
            return [Event("deviceVersionOneMotorAngleEvent", {"no": b[2] >> 2 & 3, "status": b[2] & 3, "angle": value})]
        if high == 10:
            bits = low << 8 | value
            return [Event("deviceVersionOneMassageEvent", dict(zip(("mode", "massage1", "massage2", "massage3"), (bits >> shift & 7 for shift in (9, 6, 3, 0)), strict=True)))]
        if high == 12 and low == 1:
            return [Event("deviceDetectionStatusEvent", {1: "start", 2: "stop", 3: "pause", 4: "repeat"}.get(value >> 4, "start"))]
        if high == 12 and low in (3, 4, 5, 6):
            return [Event("deviceDetectionMessageEvent", {"class": "RMDeviceDetectionDataDetails", "fields": {}})]
        return []
    if n < 7 or b[:2] != b"\x6e\x20" or b[2] != n or not codec.is_valid(b):
        return []
    domain, prop, typ = b[3:6]
    if domain == 10:
        return [Event("deviceCheckEvent", [prop, list(b)])] if prop in range(1, 7) else []
    if domain == 5 and prop == 1:
        values = {key: b[i] for i, key in enumerate(("field_7", "field_f", "field_17", "field_1f", "field_27", "field_2f"), 6)}
        if typ in (2, 3):
            return [Event("deviceRepeatAlarmListStatusEvent" if typ == 2 else "deviceRepeatAlarmListEscalationStatusEvent", values)]
        return []
    if typ not in (2, 3):
        return []
    if domain == 1:
        if prop == 2 and n > 9:
            return [Event("deviceMotorCurrentHeightStatusEvent", {"height": int.from_bytes(b[7:9], "big") / 10, "type": b[9], "angle": b[10] if n > 11 else -1, "monitorHeight": int.from_bytes(b[11:13], "big") / 10 if n > 13 else 0})]
        if prop == 3 and n > 8:
            return [Event("deviceVersionOneMotorAngleEvent", {"position": b[6], "angle": b[8]})]
    if domain == 2:
        if prop == 1 and (n - 7) % 2 == 0:
            return [Event("deviceMassageHeadStrengthStatusEvent" if b[i] == 1 else "deviceMassageFootStrengthStatusEvent", b[i+1]) for i in range(6, n-1, 2) if b[i] in (1, 2)]
        if prop in (2, 4, 5, 6) and n > 7:
            name = {2: "deviceMassageModeStatusEvent", 4: "deviceMassageFrequencStatusEvent", 5: "deviceMusicShakeStatusEvent", 6: "deviceMassagePowerStatusEvent"}[prop]
            return [Event(name, b[7] == 1 if prop == 6 else b[7])]
    if domain == 3 and prop == 1 and n > 7:
        return [Event("deviceWhiteLedStatusEvent", b[7] == 1)]
    if domain == 4:
        if prop == 1 and n > 9:
            return [Event("deviceRGBStripColorStatusEvent", {"rgb": list(b[7:10]), "alpha": 1, "space": "sRGB"})]
        if prop == 2 and n > 8:
            return [Event("deviceRGBStripTimerStatusEvent", 60*b[7]+b[8])]
        if prop in (3, 4) and n > 7:
            return [Event("deviceRGBStripMotionStatusEvent" if prop == 3 else "deviceRGBStripStatusEvent", b[7] == 1)]
    if domain == 6:
        if prop in (1, 2) and n > 7:
            return [Event("deviceAntiSnoreEvent" if prop == 1 else "deviceGetOffBedStatusEvent", b[7] == 1)]
        if prop == 3:
            if n-1 < 7:
                raise ValueError("Invalid source sublist")
            return [Event("deviceSleepAdvNameEvent", list(b[7:-1]))]
        # Property 4 is an excluded audio playback event.
        if prop == 5 and n > 7 and b[7] in (1, 2):
            return [Event("deviceAntiSnoreConfigCountEvent" if b[7] == 1 else "deviceAntiSnoreConfigTimeEvent", b[8])]
    if domain == 7 and prop == 2 and n > 7:
        return [Event("deviceCharacteristicsSubscriptionBoxLockEvent" if b[7] == 1 else "deviceCharacteristicsSubscriptionCancelBoxLockEvent")]
    if domain == 11 and prop in (1, 2, 4):
        return [Event({1: "devicePressModeEvent", 2: "deviceStrandardAndSplitControlEvent", 4: "deviceSameAndSplitControlEvent"}[prop], b[7] == 2 if prop == 2 else b[7])]
    return []


@dataclass
class Receiver:
    pending: bytearray = field(default_factory=bytearray)
    _expiry: asyncio.TimerHandle | None = None

    def close(self) -> None:
        if self._expiry is not None:
            self._expiry.cancel()
            self._expiry = None
        self.pending.clear()

    def feed(self, chunk: bytes) -> list[bytes]:
        if self._expiry is not None:
            # A due timer may still be queued behind this notification. Expired
            # data is already dead even if its clear callback has not run yet.
            if self._expiry.when() <= asyncio.get_running_loop().time():
                self.pending.clear()
            self._expiry.cancel()
            self._expiry = None
        self.pending.extend(chunk)
        if len(self.pending) > 4096:
            self.pending.clear()
            return []
        frames: list[bytes] = []
        while self.pending:
            try:
                start = self.pending.index(0x6E)
            except ValueError:
                self.pending.clear()
                break
            del self.pending[:start]
            if len(self.pending) < 3:
                break
            kind = self.pending[1]
            if kind in (0x20, 0x21):
                size = self.pending[2]
                if size == 0:  # Bound the source's zero-progress loop.
                    break
            elif kind == 0x40:
                if len(self.pending) < 4:
                    break
                size = int.from_bytes(self.pending[2:4], "big")
                if size == 0:
                    break
            else:
                try:
                    size = self.pending.index(0x6E, 1)
                except ValueError:
                    size = len(self.pending)
            if len(self.pending) < size:
                break
            b = bytes(self.pending[:size])
            del self.pending[:size]
            if kind not in (0x20, 0x21, 0x40) or kind != 0x40 and codec.is_valid(b):
                frames.append(b)
        if self.pending:
            # Clear only: never retry the parser at expiry. New input owns a
            # replacement deadline even when the previous deadline is pending.
            self._expiry = asyncio.get_running_loop().call_later(RESIDUAL_EXPIRY_S, self.pending.clear)
        return frames
