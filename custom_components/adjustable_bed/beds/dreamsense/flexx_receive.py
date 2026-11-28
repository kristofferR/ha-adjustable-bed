"""Connection-local Flexx receive policy, separate from defective APK framing."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ...codec import richmat as codec
from ...profiles.flexx_motion import BOX_SPLIT, BOX_STANDARD
from .muuegm_receive import Alarm, MuuegmReceive


def decode(frame: bytes) -> tuple[str, object] | None:
    """Decode bounded direct-bed fields; channel numbers remain diagnostics."""
    if not codec.is_valid(frame):
        return None
    if len(frame) == 5:
        fixed = {
            "6e09010078": ("clock", True),
            "6e0e00037f": ("light", True),
            "6e07010177": ("alarm_added", True),
            "6e07010278": ("alarm_cancelled", True),
            "6e90c101c0": ("detection_available", True),
            "6e23018416": ("locked", True),
            "6e23008415": ("locked", False),
        }
        if event := fixed.get(frame.hex()):
            return event
        if frame[:2] != b"\x6e\x90":
            return None
        selector, value = frame[2:4]
        if selector == 0:
            return "protocol_version", value
        if selector >> 4 == 1:
            return "bed_mode", selector & 15
        if selector >> 4 == 3:
            return "motor_channel", {
                "number": (selector >> 2) & 3,
                "status": selector & 3,
                "angle": value,
            }
        if selector >> 4 == 10:
            packed = ((selector & 15) << 8) | value
            return "massage_channels", {
                "mode": packed >> 9,
                "massage3": (packed >> 6) & 7,
                "massage2": (packed >> 3) & 7,
                "massage1": packed & 7,
            }
        if selector == 0xC2:
            return "detection_status", {1: "start", 2: "stop", 3: "pause", 4: "repeat"}.get(
                value >> 4, "start"
            )
        if selector in (0xC3, 0xC4, 0xC5, 0xC6):
            return "detection_message", {}  # The app's constructed object has no fields.
        return None
    if len(frame) < 7 or frame[:2] != b"\x6e\x20" or frame[2] != len(frame):
        return None
    group, sub, op = frame[3:6]
    size = len(frame)
    if group == 10 and sub in range(1, 7):
        return "check", {"subcode": sub, "frame": frame.hex()}
    if op not in (2, 3):
        return None
    if group == 1:
        if sub == 2 and size >= 11:
            return "height_record", {
                "height": int.from_bytes(frame[7:9], "big") / 10,
                "type": frame[9],
                "angle": frame[10] if size >= 12 else -1,
                "monitor_height": int.from_bytes(frame[11:13], "big") / 10 if size >= 14 else 0,
            }
        if sub == 3 and size >= 10:
            return "position_record", {"position": frame[6], "angle": frame[8]}
    if group == 2:
        if sub == 1 and (size - 7) % 2 == 0:
            return "massage_strength", {
                str(frame[i]): frame[i + 1] for i in range(6, size - 1, 2) if frame[i] in (1, 2)
            }
        if sub in (2, 4, 6) and size >= 9:
            return {2: "massage_mode", 4: "massage_frequency", 6: "massage_power"}[sub], frame[
                7
            ] == 1 if sub == 6 else frame[7]
    if group == 3 and sub == 1 and size >= 9:
        return "white_light", frame[7] == 1
    if group == 4:
        if sub == 1 and size >= 11:
            return "rgb", tuple(frame[7:10])
        if sub == 2 and size >= 10:
            return "light_seconds", frame[7] * 60 + frame[8]
        if sub in (3, 4) and size >= 9:
            return "light_motion" if sub == 3 else "light_power", frame[7] == 1
    if group == 5 and sub == 1 and size >= 13:
        return "alarm_list" if op == 2 else "alarm_update", Alarm(*frame[6:12])
    if group == 6:
        if sub in (1, 2) and size >= 9:
            return "snore_detection" if sub == 1 else "out_of_bed_setting", frame[7] == 1
        if sub == 3 and size >= 8:
            return "sleep_band_name_bytes", list(frame[7:-1])
        if sub == 5 and size >= 10 and frame[7] in (1, 2):
            return "snore_count" if frame[7] == 1 else "snore_time_raw", frame[8]
    if group == 7 and sub == 2 and size >= 9:
        return "locked", frame[7] == 1
    if group == 11 and size >= 9:
        if sub == 1:
            return "press_mode_raw", frame[7]
        if sub == 2:
            return "box_mode_raw", frame[7]
        if sub == 4:
            return "same_movement_raw", frame[7]
    return None


@dataclass(slots=True)
class FlexxReceive(MuuegmReceive):
    """Wait for complete checked records; never manufacture state from an APK fault."""

    completed: dict[str, object] = field(default_factory=dict)

    def feed(self, data: bytes) -> None:
        self.completed.clear()
        self.acknowledgements.clear()
        self.pending.extend(data)
        while self.pending:
            start = self.pending.find(codec.BED)
            if start < 0:
                self.pending.clear()
                break
            del self.pending[:start]
            if len(self.pending) < 3:
                break
            kind = self.pending[1]
            if kind in (0x20, 0x21):
                size = self.pending[2]
                minimum = 7
            elif kind == 0x40:
                if len(self.pending) < 4:
                    break
                size = int.from_bytes(self.pending[2:4], "big")
                minimum = 6
            else:
                size = minimum = 5
            if size < minimum:
                del self.pending[0]  # Progress instead of the app's zero-length loop.
                continue
            if len(self.pending) < size:
                break
            frame = bytes(self.pending[:size])
            del self.pending[:size]
            excluded = (
                kind in (0x21, 0x40)
                or kind == 0x20
                and (frame[3] in (9, 13, 14, 16, 17) or frame[3:5] in (b"\x02\x05", b"\x06\x04"))
            )
            valid = kind != 0x40 and codec.is_valid(frame)
            self.frames.append(
                {
                    "frame": frame.hex(),
                    "dispatch": "excluded"
                    if excluded
                    else "accepted"
                    if valid
                    else "checksum_rejected",
                }
            )
            del self.frames[:-32]
            if excluded or not valid:
                continue
            event = decode(frame)
            if event is None:
                continue
            name, value = event
            if isinstance(value, Alarm):
                if not (1 <= value.id <= 7 and 0 <= value.hour <= 23 and 0 <= value.minute <= 59):
                    self.events["unusable_alarm"] = asdict(value)
                    continue
                if name == "alarm_list":
                    if value not in self.records:
                        self.records.append(value)
                        del self.records[:-64]
                        self.revision += 1
                else:
                    index = next(
                        (i for i, old in enumerate(self.records) if old.id == value.id), None
                    )
                    if index is not None:
                        self.records[index] = value
                        self.revision += 1
            else:
                self.events[name] = value
                self.completed[name] = value
            if name in ("clock", "light"):
                self.capabilities.add(name)
            elif name in ("alarm_added", "alarm_cancelled"):
                self.last_ack = name
                self.acknowledgements.append(name)
            elif name == "box_mode_raw" and value in (BOX_SPLIT, BOX_STANDARD):
                self.split = value == BOX_SPLIT
                self.completed["split"] = self.split
