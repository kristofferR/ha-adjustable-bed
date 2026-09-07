"""RMControl 21.3.7 packet primitives, independent of BLE and HA state.

Source trails and interpretation corrections are documented in
docs/apk-analysis/row018-rmcontrol-specialized-evidence.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from time import monotonic
from typing import Literal

_ACTION_PREFIXES = {
    "deviceFunctionItemExitLimit": bytes.fromhex("6e0201"),
    "deviceFunctionItemCheckClock": bytes.fromhex("6e0801"),
    "deviceFunctionItemCheckLight": bytes.fromhex("6e0a00"),
    "deviceFunctionItemCheckMusic": bytes.fromhex("6e1501"),
    "deviceFunctionItemCheckAroma": bytes.fromhex("6e1a00"),
    "deviceFunctionItemCheckMattress": bytes.fromhex("5e1a00"),
    "deviceFunctionItemCheckSnore": bytes.fromhex("6e2100"),
    "deviceFunctionItemCheckSpeech": bytes.fromhex("6e2200"),
    "deviceFunctionItemCheckDetection": bytes.fromhex("6e9ac0"),
    "deviceFunctionItemSendStartDetection": bytes.fromhex("6e88c2"),
    "deviceFunctionItemQueryVersion": bytes.fromhex("6e9a00"),
    "deviceFunctionVersionOneBedCurrentMode": bytes.fromhex("6e9a10"),
    "deviceFunctionVersionOneMotor1CurrentAngle": bytes.fromhex("6e9a30"),
    "deviceFunctionVersionOneMotor2CurrentAngle": bytes.fromhex("6e9a30"),
    "deviceFunctionVersionOneMotor3CurrentAngle": bytes.fromhex("6e9a30"),
    "deviceFunctionVersionOneMotor4CurrentAngle": bytes.fromhex("6e9a30"),
    "deviceFunctionVersionOneCurrentMassageMode": bytes.fromhex("6e9aa0"),
    "deviceFunctionVersionOneCurrentBedLightStatus": bytes.fromhex("6e9ab0"),
}


def _integer(value: int, name: str, maximum: int = 255, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
    return value


def _checksum(body: bytes) -> bytes:
    return body + bytes((sum(body) & 0xFF,))


def _extended(domain: int, command: int, operation: int, data: bytes) -> bytes:
    # Outbound extended frames place length before 0x20. Notifications do not.
    return _checksum(bytes((0x6E, len(data) + 7, 0x20, domain, command, operation)) + data)


def build_action(command: int, *, side: int = 0, nordic: bool = False, action: str = "") -> bytes:
    """Build a resolved detail command; profile/gesture selection belongs to the caller."""
    _integer(command, "command")
    _integer(side, "side", 2)
    if nordic:
        return bytes((command,))
    prefix = _ACTION_PREFIXES.get(action, bytes((0x6E, 1, side)))
    return _checksum(prefix + bytes((command,)))


def build_light_timer(seconds: int) -> bytes:
    """Build the 16-bit seconds command, with zero meaning no timeout."""
    _integer(seconds, "seconds", 65535)
    value = seconds if seconds else 65535
    return _checksum(bytes((0x6E, 0x0B, value >> 8, value & 255)))


def build_light_color(rgb: tuple[int, int, int]) -> bytes:
    """Build the two concatenated legacy RGB frames."""
    if len(rgb) != 3:
        raise ValueError("RGB requires exactly three components")
    red, green, blue = (_integer(value, "RGB component") for value in rgb)
    return _checksum(bytes((0x6E, 0x0C, 255, red))) + _checksum(bytes((0x6E, 0x0D, green, blue)))


def build_single_alarm(minutes: int, command: int) -> tuple[bytes, bytes]:
    """Build the ordered countdown/action frames; (0, 0) cancels the alarm."""
    _integer(minutes, "minutes", 65535)
    _integer(command, "command")
    return (
        _checksum(bytes((0x6E, 5, minutes & 255, 0))),
        _checksum(bytes((0x6E, 6, minutes >> 8, command))),
    )


@dataclass(frozen=True, slots=True)
class RepeatAlarm:
    """Device repeating-alarm fields; repeat_mask bit 7 is Monday, bit 1 Sunday."""

    alarm_id: int
    hour: int
    minute: int
    command: int
    repeat_mask: int

    def __post_init__(self) -> None:
        _integer(self.alarm_id, "alarm_id", 7, 1)
        _integer(self.hour, "hour", 23)
        _integer(self.minute, "minute", 59)
        _integer(self.command, "command")
        _integer(self.repeat_mask, "repeat_mask")


def build_repeat_alarm(alarm: RepeatAlarm) -> bytes:
    """Create/update an alarm; the app writes zero in the second bean field."""
    return _extended(
        5,
        1,
        1,
        bytes(
            (
                alarm.alarm_id,
                0,
                alarm.hour,
                alarm.minute,
                alarm.command,
                alarm.repeat_mask,
            )
        ),
    )


def delete_repeat_alarm(alarm_id: int) -> bytes:
    """Delete the selected device alarm slot."""
    return _extended(5, 2, 1, bytes((_integer(alarm_id, "alarm_id", 7, 1),)))


def query_repeat_alarms() -> bytes:
    """Request device alarm records."""
    return _extended(5, 1, 0, b"\x00")


def build_alarm_time_sync(now: datetime) -> tuple[bytes, bytes]:
    """Build Unix time/zone then local calendar frames in the app's order.

    The artifact truncates timezone offsets to whole hours toward zero. Aware
    datetime input makes that limitation explicit instead of using host timezone.
    """
    offset = now.utcoffset()
    if offset is None:
        raise ValueError("Alarm time synchronization requires an aware datetime")
    timestamp = int(now.timestamp())
    _integer(timestamp, "Unix timestamp", 0xFFFFFFFF)
    _integer(now.year - 1970, "year offset", 255)
    zone = int(offset.total_seconds() / 3600) & 255
    return (
        _extended(8, 2, 1, timestamp.to_bytes(4, "big") + bytes((zone,))),
        _extended(
            8, 3, 1, bytes((now.year - 1970, now.month, now.day, now.hour, now.minute, now.second))
        ),
    )


def build_anti_snore_config(mode: Literal["count", "time"], value: int) -> bytes:
    """Set intervention count or duration value; this is not an enable switch."""
    if mode not in ("count", "time"):
        raise ValueError("Anti-snore configuration mode must be count or time")
    return _extended(6, 5, 1, bytes((1 if mode == "count" else 2, 0, _integer(value, "value"))))


def build_anti_snore_switch(enabled: bool) -> bytes:
    """Enable/disable snore detection."""
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be a boolean")
    return _extended(6, 1, 1, bytes((0, int(enabled))))


def query_anti_snore_config() -> bytes:
    """Request intervention configuration."""
    return _extended(6, 5, 0, b"\x00\x00")


def query_anti_snore_switch() -> bytes:
    """Request snore detection state."""
    return _extended(6, 1, 0, b"\x00")


def query_sleep_advertisement() -> bytes:
    """Request the sleep device name, only for a proven BLE-sleep product."""
    return _extended(6, 3, 0, b"\x00")


type StateValue = bool | int | float | str | tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Notification:
    """One source-defined semantic update; absence of a field means no update."""

    kind: str
    values: dict[str, StateValue]


_CAPABILITIES = {
    bytes.fromhex("6e09010078"): "alarm",
    bytes.fromhex("6e0e00037f"): "light",
    bytes.fromhex("6e1a000189"): "aroma",
    bytes.fromhex("6e16010186"): "music",
    bytes.fromhex("6e90c101c0"): "detection",
    bytes.fromhex("6e2100008f"): "anti_snore",
}


def _decode_common(frame: bytes) -> Notification | None:
    if capability := _CAPABILITIES.get(frame):
        return Notification("capability", {capability: True})
    if frame in (bytes.fromhex("6e07010177"), bytes.fromhex("6e07010278")):
        return Notification("single_alarm", {"result": "added" if frame[3] == 1 else "cancelled"})
    if frame in (bytes.fromhex("6e23018416"), bytes.fromhex("6e23008415")):
        return Notification("lock", {"locked": frame[2] == 1})
    if frame == bytes.fromhex("6e23a06e9f"):
        return Notification("anti_snore", {"stop_music": True})
    if frame[1] != 0x90:
        return None
    selector, value = frame[2:4]
    group, part = selector >> 4, selector & 15
    if selector == 0:
        return Notification("protocol", {"version": value})
    if group == 1:
        return Notification("bed_mode", {"mode": part})
    if group == 3:
        return Notification(
            "motor", {"motor": (selector >> 2) & 3, "status": selector & 3, "angle": value}
        )
    if group == 10:
        packed = (part << 8) | value
        return Notification(
            "massage",
            {
                "mode": (packed >> 9) & 7,
                "strength_1": packed & 7,
                "strength_2": (packed >> 3) & 7,
                "strength_3": (packed >> 6) & 7,
            },
        )
    if group == 11:
        return Notification(
            "music",
            {
                "usb_source": bool(selector & 1),
                "playing": bool(value & 128),
                "shake": bool(value & 64),
                "bluetooth_enabled": bool(value & 32),
            },
        )
    if group == 13 and part in (1, 2):
        return Notification("music", {"volume" if part == 1 else "vibration_gear": value})
    if group == 12 and part == 2:
        status = {1: "start", 2: "stop", 3: "pause", 4: "repeat"}.get(value >> 4)
        return Notification("detection", {"status": status}) if status else None
    if group == 12 and part in (3, 4, 5, 6):
        status = {
            0: "abnormal",
            1: "normal",
            2: "control_box_malfunction",
            3: "not_plugged_in",
        }.get(value & 15)
        if status is not None:
            return Notification(
                "diagnostic",
                {
                    "channel": {3: "motor", 4: "massage", 5: "white_light", 6: "usb"}[part],
                    "selector": value >> 4,
                    "status": status,
                },
            )
    return None


def _decode_extra(frame: bytes) -> Notification | None:
    domain, command, operation = frame[3:6]
    payload = frame[6:-1]
    if domain == 10 and command in range(1, 7):
        # The app emits a channel and the full frame, not decoded fault bits.
        channel = {
            1: "motor",
            2: "massage",
            3: "white_light",
            4: "rgb",
            5: "c65",
            6: "music_vibrator",
        }[command]
        return Notification("diagnostic", {"channel": channel, "payload": tuple(payload)})
    if operation not in (2, 3):
        return None
    # Payload lengths exclude the checksum, including for permissive app checks.
    if domain == 5 and command == 1 and len(payload) >= 6:
        return Notification(
            "repeat_alarm",
            dict(
                zip(
                    ("alarm_id", "record_flag", "hour", "minute", "command", "repeat_mask"),
                    payload[:6],
                    strict=True,
                )
            ),
        )
    if domain == 6:
        if command in (1, 2) and len(payload) >= 2:
            return Notification(
                "anti_snore",
                {"enabled" if command == 1 else "get_off_bed_enabled": payload[1] == 1},
            )
        if command == 3 and len(payload) >= 1:
            return Notification("anti_snore", {"sleep_advertisement": tuple(payload[1:])})
        if command == 4 and len(payload) >= 3:
            return Notification(
                "anti_snore",
                {
                    "in_bed_status": payload[1],
                    "sleep_status": payload[2],
                    "stop_music": payload[1] == payload[2] == 1,
                },
            )
        if command == 5 and len(payload) >= 3 and payload[1] in (1, 2):
            return Notification(
                "anti_snore",
                {"intervention_count" if payload[1] == 1 else "intervention_time": payload[2]},
            )
    if domain == 4:
        if command == 1 and len(payload) >= 4:
            return Notification("rgb", {"rgb": tuple(payload[1:4])})
        if command == 2 and len(payload) >= 3:
            return Notification("light_timer", {"seconds": int.from_bytes(payload[1:3], "big")})
        if command in (3, 4) and len(payload) >= 2:
            return Notification(
                "rgb", {"motion_enabled" if command == 3 else "on": payload[1] == 1}
            )
    if domain == 3 and command == 1 and len(payload) >= 2:
        return Notification("white_light", {"on": payload[1] == 1})
    if domain == 7 and command == 2 and len(payload) >= 2:
        return Notification("lock", {"locked": payload[1] == 1})
    if domain == 9 and len(payload) >= 2:
        if command in (1, 3, 4):
            return Notification(
                "music",
                {{1: "playing", 3: "bluetooth_enabled", 4: "usb_source"}[command]: payload[1] == 1},
            )
        if command == 2 and payload[0] in (2, 3):
            return Notification(
                "music", {"volume" if payload[0] == 2 else "volume_silent": payload[1]}
            )
    if domain == 11 and len(payload) >= 2:
        if command == 1:
            return Notification("press_mode", {"mode": payload[1]})
        if command == 2:
            return Notification("press_mode", {"standard_and_split_control": payload[1] == 2})
        if command == 4:
            return Notification("press_mode", {"same_and_split_mode": payload[1]})
    if domain == 14 and command == 1 and len(payload) >= 2:
        return Notification("fan", {"gear": payload[1]})
    if domain == 16:
        if command == 1 and len(payload) >= 2:
            return Notification("aroma", {"open_status": payload[1]})
        if command == 2 and len(payload) >= 3:
            return Notification("aroma", {"timer_value": payload[2]})
    if domain == 17:
        if command == 2 and len(payload) >= 3:
            timer = int.from_bytes(payload[1:3], "big")
            return Notification(
                "heating",
                {
                    "position": payload[0],
                    "timer_mode": "off"
                    if timer == 0
                    else "unlimited"
                    if timer == 65535
                    else "timed",
                    "timer_value": 0 if timer in (0, 65535) else timer,
                },
            )
        if command == 3 and len(payload) >= 3:
            return Notification("heating", {"position": payload[0], "temperature": payload[2]})
        if command == 5 and payload:
            return Notification("heating", {"model": payload[0]})
    if domain == 2:
        if command == 1 and len(payload) % 2 == 0:
            values: dict[str, StateValue] = {}
            for index in range(0, len(payload), 2):
                if payload[index] in (1, 2):
                    values["head_strength" if payload[index] == 1 else "foot_strength"] = payload[
                        index + 1
                    ]
            return Notification("massage", values) if values else None
        if command in (2, 4, 5, 6) and len(payload) >= 2:
            key = {2: "mode", 4: "frequency", 5: "shake_strength", 6: "on"}[command]
            return Notification("massage", {key: payload[1] == 1 if command == 6 else payload[1]})
    if domain == 1:
        if command == 2 and len(payload) >= 4:
            values = {"height": int.from_bytes(payload[1:3], "big") / 10, "type": payload[3]}
            if len(payload) >= 5:
                values["angle"] = payload[4]
            if len(payload) >= 7:
                values["monitor_height"] = int.from_bytes(payload[5:7], "big") / 10
            return Notification("motor_travel", values)
        if command == 3 and len(payload) >= 3:
            return Notification("motor_angle", {"position": payload[0], "angle": payload[2]})
    return None


def decode_notification(frame: bytes) -> Notification | None:
    """Decode a complete checksum-valid frame; unknown/malformed frames have no effect."""
    if len(frame) < 5 or frame[0] != 0x6E or sum(frame[:-1]) & 255 != frame[-1]:
        return None
    if frame[1] == 0x20:
        if len(frame) < 7 or frame[2] != len(frame):
            return None
        return _decode_extra(frame)
    return _decode_common(frame) if len(frame) == 5 else None


class NotificationBuffer:
    """Assemble fragmented/coalesced notifications without treating payload as headers."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._last_data_at = 0.0

    def clear(self) -> None:
        """Discard an incomplete previous connection's frame."""
        self._buffer.clear()

    def feed(self, data: bytes) -> tuple[Notification, ...]:
        """Consume bytes; retain at most one incomplete, length-bounded frame."""
        now = monotonic()
        # Source Timer(Duration(500000 microseconds)) expires partial frames.
        if now - self._last_data_at >= 0.5:
            self.clear()
        self._last_data_at = now
        self._buffer.extend(data)
        result: list[Notification] = []
        while self._buffer:
            if self._buffer[0] != 0x6E:
                del self._buffer[0]
                continue
            if len(self._buffer) < 3:
                break
            length = self._buffer[2] if self._buffer[1] == 0x20 else 5
            if length < 7 and self._buffer[1] == 0x20:
                del self._buffer[0]
                continue
            if len(self._buffer) < length:
                break
            frame = bytes(self._buffer[:length])
            if sum(frame[:-1]) & 255 != frame[-1]:
                del self._buffer[0]
                continue
            del self._buffer[:length]
            if notification := decode_notification(frame):
                result.append(notification)
        return tuple(result)
