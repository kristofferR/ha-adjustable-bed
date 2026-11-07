"""Eshine 1.0.1 receive grammar, from accepted row106 artifact evidence.

Common frames retain the app's notification-boundary delimiter behavior.
Malformed lengths/ranges are discarded instead of reproducing Dart exceptions
or nonprogress. No outbound query or physical motor mapping is inferred.
Outbound frames come from ``codec/richmat.py``.
"""

from __future__ import annotations

from typing import Final

from ...codec import richmat as codec

type Value = bool | int | float | str | None | list[int] | dict[str, int | float]
type Event = tuple[str, Value]

EXACT_COMMON: Final = {
    "6e09010078": "clock_capability",
    "6e0e00037f": "light_capability",
    "6e1a000189": "aromatherapy_capability",
    "6e07010177": "alarm_add_success",
    "6e07010278": "alarm_cancel_success",
    "6e16010186": "music_capability",
    "6e90c101c0": "detection_capability",
    "6e2100008f": "snore_capability",
    "6e23018416": "box_lock",
    "6e23008415": "box_unlock",
    # 6e23a06e9f is unreachable: the stream splits its embedded 6e.
}


def parse_common(data: bytes) -> list[Event]:
    if len(data) != 5:
        return []  # Desk data is outside the bed integration boundary.
    exact = EXACT_COMMON.get(data.hex())
    if exact:
        return [(exact, True)]
    if data[:2] != b"\x6e\x90":
        return []
    hi, lo, value = data[2] >> 4, data[2] & 15, data[3]
    if hi == 0 and lo == 0:
        return [("protocol_version", value)]
    if hi == 1:
        return [("bed_mode", lo)]
    if hi == 3:
        return [("motor_angle", {"no": lo >> 2, "status": lo & 3, "angle": value})]
    if hi == 10:
        packed = (lo << 8) | value
        return [
            (
                "massage_state",
                {
                    "mode": packed >> 9,
                    "massage1": packed & 7,
                    "massage2": (packed >> 3) & 7,
                    "massage3": (packed >> 6) & 7,
                },
            )
        ]
    if hi == 11:
        return [
            ("music_usb", bool(lo & 1)),
            ("music_play", bool(value & 128)),
            ("music_shake", bool(value & 64)),
            ("music_ble", bool(value & 32)),
        ]
    if hi == 12 and lo == 2:
        return [
            (
                "detection_status",
                {1: "start", 2: "stop", 3: "pause", 4: "repeat"}.get(value >> 4, "start"),
            )
        ]
    if hi == 13 and lo in (1, 2):
        return [("music_volume" if lo == 1 else "music_shake_gear", value)]
    return []  # Diagnostic models whose fields were pruned contain no state.


def parse_extended(data: bytes) -> list[Event]:
    n = len(data)
    if n < 7 or data[2] != n:
        return []
    domain, sub, operation = data[3:6]
    if domain == 10 and sub in range(1, 7):
        return [(f"component_check_{sub}", list(data))]
    if operation not in (2, 3):
        return []
    if domain == 5 and sub == 1:
        if n < 12:
            return []
        return [("alarm_list" if operation == 2 else "alarm_report", list(data[6:12]))]
    if domain == 1 and sub == 2 and n > 9:
        return [
            (
                "motor_height",
                {
                    "height": int.from_bytes(data[7:9]) / 10,
                    "type": data[9],
                    "angle": data[10] if n > 11 else -1,
                    "monitorHeight": int.from_bytes(data[11:13]) / 10 if n > 13 else 0,
                },
            )
        ]
    if domain == 2:
        if sub == 1 and (n - 7) % 2 == 0:
            return [
                ("massage_head_strength" if data[i] == 1 else "massage_foot_strength", data[i + 1])
                for i in range(6, n - 1, 2)
                if data[i] in (1, 2)
            ]
        if n > 7 and sub in (2, 4, 5, 6):
            return [
                (
                    {2: "massage_mode", 4: "massage_frequency", 5: "music_shake", 6: "massage_on"}[
                        sub
                    ],
                    data[7] == 1 if sub == 6 else data[7],
                )
            ]
    if domain == 3 and sub == 1 and n > 7:
        return [("white_led", data[7] == 1)]
    if domain == 4:
        if sub == 1 and n > 9:
            return [
                (
                    "rgb_color",
                    {"r": data[7] / 255, "g": data[8] / 255, "b": data[9] / 255, "alpha": 1},
                )
            ]
        if sub == 2 and n > 8:
            return [("rgb_timer", data[7] * 60 + data[8])]
        if sub in (3, 4) and n > 7:
            return [("rgb_motion" if sub == 3 else "rgb_on", data[7] == 1)]
    if domain == 6:
        if sub in (1, 2) and n > 7:
            return [("anti_snore" if sub == 1 else "off_bed", data[7] == 1)]
        if sub == 3 and n >= 8:
            return [("sleep_adv_name", list(data[7:-1]))]
        if sub == 4 and n > 8 and data[7] == 1 and data[8] == 1:
            return [("snore_stop_music", True)]
        if sub == 5 and n > 8 and data[7] in (1, 2):
            return [("anti_snore_count" if data[7] == 1 else "anti_snore_time", data[8])]
    if domain == 7 and sub == 2 and n > 7:
        return [("box_lock" if data[7] == 1 else "box_unlock", True)]
    if domain == 9 and sub in (1, 3, 4) and n > 7:
        return [({1: "music_play", 3: "music_ble", 4: "music_usb"}[sub], data[7] == 1)]
    if domain == 11 and sub in (1, 2, 4) and n > 7:
        return [
            (
                {1: "press_mode", 2: "standard_split", 4: "same_split"}[sub],
                data[7] == 2 if sub == 2 else data[7],
            )
        ]
    return []


class NotificationStream:
    """Bounded, session-local stream. Extended frames span notifications.

    OTA frames are skipped by their length, without interpreting firmware data.
    Common frames retain notification boundaries and embedded-header splitting.
    """

    def __init__(self) -> None:
        self.buffer = bytearray()

    def feed(self, data: bytes) -> list[Event]:
        self.buffer.extend(data)
        events: list[Event] = []
        # Integration safety bound, not a protocol maximum/MTU.
        if len(self.buffer) > 65535:
            self.buffer.clear()
            return events
        while len(self.buffer) >= 3:
            try:
                start = self.buffer.index(0x6E)
            except ValueError:
                self.buffer.clear()
                break
            del self.buffer[:start]
            if len(self.buffer) < 3:
                break
            kind = self.buffer[1]
            if kind == 0x20:
                size = self.buffer[2]
                if size < 7:
                    self.buffer.clear()
                    break
            elif kind == 0x40:
                if len(self.buffer) < 4:
                    break
                size = int.from_bytes(self.buffer[2:4])
                if size < 9:
                    self.buffer.clear()
                    break
            else:
                try:
                    size = self.buffer.index(0x6E, 1)
                except ValueError:
                    size = len(self.buffer)
            if len(self.buffer) < size:
                break
            frame = bytes(self.buffer[:size])
            del self.buffer[:size]
            if kind == 0x20:
                if codec.is_valid(frame):
                    events.extend(parse_extended(frame))
            elif kind != 0x40:
                events.extend(parse_common(frame))
        return events
