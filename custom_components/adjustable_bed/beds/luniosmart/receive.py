"""Lunio Smart+ receive fields, with bounded malformed-input handling.

Fields retain artifact event names and anonymous alarm offsets. No event enables
an outbound setter, adds an axis, or supplies a physical calibration.
"""

from dataclasses import dataclass, field

from ...codec import richmat as codec

type Value = str | int | float | bool | None | list[Value] | dict[str, Value]
type Event = tuple[str, Value]

LITERALS = {
    "6e09010078": "deviceCharacteristicsSubscriptionClockEvent",
    "6e0e00037f": "deviceCharacteristicsSubscriptionLightEvent",
    "6e07010177": "deviceAddAlarmSuccessEvent",
    "6e07010278": "deviceCancelAlarmSuccessEvent",
    "6e90c101c0": "deviceCharacteristicsSubscriptionDetectionEvent",
    "6e2100008f": "deviceCharacteristicsSubscriptionSnoreEvent",
    "6e23018416": "deviceCharacteristicsSubscriptionBoxLockEvent",
    "6e23008415": "deviceCharacteristicsSubscriptionCancelBoxLockEvent",
}


def event(name: str, value: Value = None) -> Event:
    return name, value


def decode(packet: bytes) -> list[Event]:
    if name := LITERALS.get(packet.hex()):
        return [event(name)]
    if len(packet) < 5:
        return []
    if packet[1] == 0x20 and len(packet) < 6:
        return []
    try:
        return _fields(packet)
    except IndexError:
        # Recovered weak guards throw here. HA rejects instead of propagating
        # a BLE callback error; no partial event or guessed field is published.
        return []


def _fields(b: bytes) -> list[Event]:
    """Exact app BED masks, including checksum aliases in weak guards."""
    n = len(b)
    if n == 5 and b[:2] == b"\x6e\x90":
        tag, value = b[2], b[3]
        if tag == 0:
            return [event("deviceControlBoxProtocolVersionEvent", value)]
        if tag >> 4 == 1:
            return [event("deviceVersionOneBedModeEvent", tag & 15)]
        if tag >> 4 == 3:
            return [
                event(
                    "deviceVersionOneMotorAngleEvent",
                    {"no": (tag >> 2) & 3, "status": tag & 3, "angle": value},
                )
            ]
        if tag >> 4 == 10:
            bits = ((tag & 15) << 8) | value
            return [
                event(
                    "deviceVersionOneMassageModeEvent",
                    {
                        "mode": bits >> 9,
                        "massage1": bits & 7,
                        "massage2": (bits >> 3) & 7,
                        "massage3": (bits >> 6) & 7,
                    },
                )
            ]
        if tag >> 4 == 12:
            sub = tag & 15
            if sub == 2:
                return [
                    event(
                        "deviceDetectionStatusEvent",
                        {1: "start", 2: "stop", 3: "pause", 4: "repeat"}.get(value >> 4, "start"),
                    )
                ]
            if sub in (3, 4, 5):
                # index/status parsed for logging, then discarded in the shipped AOT:
                # RMDeviceDetectionDataDetails is an empty size-8 object.
                return [event("deviceDetectionMessageEvent", {})]
        return []
    if n <= 2 or b[1] != 0x20:
        return []
    if (sum(b[:-1]) & 255) != b[-1]:
        return []
    if n != b[2]:
        return []
    cat, sub, op = b[3], b[4], b[5]  # artifact has no general minimum guard
    if cat == 10:
        if sub in (1, 2, 3, 4, 5):
            return [event("deviceCheckEvent", [sub, list(b)])]
        return []  # audio subcommand 6 excluded
    if cat == 5 and sub == 1:
        vals = [b[i] for i in range(6, 12)]
        bean: dict[str, Value] = dict(
            zip(
                ("field_7", "field_f", "field_17", "field_1f", "field_27", "field_2f"),
                vals,
                strict=True,
            )
        )
        if op in (2, 3):
            name = (
                "deviceRepeatAlarmListStatusEvent"
                if op == 2
                else "deviceRepeatAlarmListEscalationStatusEvent"
            )
            return [event(name, bean)]
        return []
    if op not in (2, 3):
        return []
    if cat == 1:
        if sub == 2 and n > 9:
            return [
                event(
                    "deviceMotorCurrentHeightStatusEvent",
                    {
                        "height": (b[7] * 256 + b[8]) / 10,
                        "type": b[9],
                        "angle": b[10] if n > 11 else -1,
                        "monitorHeight": (b[11] * 256 + b[12]) / 10 if n > 13 else 0.0,
                    },
                )
            ]
        if sub == 3 and n > 8:
            _discarded = b[7]
            return [event("deviceVersionOneMotorAngleEvent", {"position": b[6], "angle": b[8]})]
    if cat == 2:
        if sub == 1 and (b[2] - 7) % 2 == 0:
            out: list[Event] = []
            for i in range(6, b[2] - 1, 2):
                if b[i] in (1, 2):
                    name = (
                        "deviceMassageHeadStrengthStatusEvent"
                        if b[i] == 1
                        else "deviceMassageFootStrengthStatusEvent"
                    )
                    out.append(event(name, b[i + 1]))
            return out
        if n > 7 and sub in (2, 4, 6):
            name = {
                2: "deviceMassageModeStatusEvent",
                4: "deviceMassageFrequencStatusEvent",
                6: "deviceMassagePowerStatusEvent",
            }[sub]
            return [event(name, b[7] == 1 if sub == 6 else b[7])]
    if cat == 3 and sub == 1 and n > 7:
        return [event("deviceWhiteLedStatusEvent", b[7] == 1)]
    if cat == 4:
        if sub == 1 and n > 9:
            return [
                event(
                    "deviceRGBStripColorStatusEvent",
                    {
                        "alpha": 1.0,
                        "red": (b[7] & 255) / 255,
                        "green": (b[8] & 255) / 255,
                        "blue": (b[9] & 255) / 255,
                    },
                )
            ]
        if sub == 2 and n > 8:
            return [event("deviceRGBStripTimerStatusEvent", b[7] * 60 + b[8])]
        if sub in (3, 4) and n > 7:
            return [
                event(
                    "deviceRGBStripMotionStatusEvent" if sub == 3 else "deviceRGBStripStatusEvent",
                    b[7] == 1,
                )
            ]
    if cat == 6:
        if sub in (1, 2) and n > 7:
            return [
                event(
                    "deviceAntiSnoreEvent" if sub == 1 else "deviceGetOffBedStatusEvent", b[7] == 1
                )
            ]
        # Subcommands 3 (accessory name) and 4 (audio-only event) are EXCLUDED.
        if sub == 5 and n > 7:
            selector, value = b[7], b[8]  # weak guard reads checksum at n=9; n=8 raises
            if selector in (1, 2):
                return [
                    event(
                        "deviceAntiSnoreConfigCountEvent"
                        if selector == 1
                        else "deviceAntiSnoreConfigTimeEvent",
                        value,
                    )
                ]
    if cat == 7 and sub == 2 and n > 7:
        return [
            event(
                "deviceCharacteristicsSubscriptionBoxLockEvent"
                if b[7] == 1
                else "deviceCharacteristicsSubscriptionCancelBoxLockEvent"
            )
        ]
    if cat == 11 and sub in (1, 2, 4):
        return [
            event(
                {
                    1: "devicePressModeEvent",
                    2: "deviceStrandardAndSplitControlEvent",
                    4: "deviceSameAndSplitControlEvent",
                }[sub],
                b[7] == 2 if sub == 2 else b[7],
            )
        ]
    return []


@dataclass
class Receiver:
    pending: bytearray = field(default_factory=bytearray)

    def feed(self, chunk: bytes) -> list[bytes]:
        self.pending.extend(chunk)
        if len(self.pending) > 4096:
            self.pending.clear()
            return []
        frames: list[bytes] = []
        while len(self.pending) >= 3:
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
            elif kind == 0x40:
                if len(self.pending) < 4:
                    break
                size = int.from_bytes(self.pending[2:4], "big")
            else:
                try:
                    size = self.pending.index(0x6E, 1)
                except ValueError:
                    size = len(self.pending)
            if not size or size > 4096:
                self.pending.clear()
                break
            if len(self.pending) < size:
                break
            packet = bytes(self.pending[:size])
            del self.pending[:size]
            # Desk/OTA framing affects shared boundaries, never BED state.
            if kind == 0x20:
                if codec.is_valid(packet):
                    frames.append(packet)
            elif kind not in (0x21, 0x40):
                frames.append(packet)
        return frames
