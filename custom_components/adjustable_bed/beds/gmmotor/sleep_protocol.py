"""GM Control 4.6.6 sleep-module requests and receive assembly (accepted row102 protocol P2).

The MM and SXB branches are distinct from the P1 bed transport; their frames are
the sleep-sensor JSON envelope (``codec/sleep_envelope.py``). Their receive
quirks are preserved; malformed-input errors are safe HA rejections.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .codec import sleep_envelope
from .gmmotor_notifications import Value
from .gmmotor_protocol import MalformedNotification

type SleepCommand = Literal[
    "s_time", "q_time", "q_part", "s_part", "q_realtime", "q_report", "q_report_allow", "q_sens"
]


@dataclass(frozen=True, slots=True)
class Request:
    """One admitted logical command and its framed bytes."""

    command: SleepCommand
    request_id: int
    packet: bytes


class Requests:
    """Session request counter, including the source's empty-selector increment."""

    def __init__(self, *, sxb: bool) -> None:
        self.sxb = sxb
        self.next_id = 1

    def build(
        self,
        command: SleepCommand,
        *,
        now: datetime | None = None,
        zone: str = "",
        part: int = 12,
        report_type: int = 1,
        year: int = 1970,
        month: int = 1,
        day: int = 1,
    ) -> Request:
        """Build only the fourteen host-reachable builders, never OTA/provisioning."""
        request_id = self.next_id if self.next_id < 255 else 1
        self.next_id = request_id + 1
        name = command
        value: Value
        if command == "s_time":
            if now is None or now.utcoffset() is None:
                raise ValueError("Sleep clock requires an aware datetime")
            offset = now.utcoffset()
            assert offset is not None
            value = (
                {"ts": int(now.timestamp()), "utc": int(offset.total_seconds() / 3600)}
                if self.sxb
                else {"ts": int(now.timestamp()), "tz": zone}
            )
        elif command == "q_time":
            if not self.sxb:
                return Request(command, request_id, b"")
            value = None
        elif command == "q_part":
            name = "q_part" if self.sxb else "s_part"
            value = None
        elif command == "s_part":
            value = part
        elif command == "q_realtime":
            value = {"type": 0, "time": 1}
        elif command in ("q_report", "q_report_allow"):
            name = "q_report"
            if command == "q_report_allow" and self.sxb:
                value = {"allow": 1}
            else:
                value = {"part": part, "type": report_type, "y": year, "m": month, "d": day}
                if command == "q_report_allow":
                    value["allow"] = 1
        elif command == "q_sens" and self.sxb:
            value = None
        else:
            raise ValueError("This sleep command is not reachable in the selected app mode")
        payload = json.dumps(
            {"id": request_id, "cmd": name, "val": value}, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return Request(command, request_id, sleep_envelope.frame(payload, request_id))


class ReceiveBuffer:
    """One command's P2 receive assembly, with source chunk boundaries retained."""

    def __init__(self, *, sxb: bool) -> None:
        self.sxb = sxb
        self.command: SleepCommand | None = None
        self.report_size = 0
        self.pending = bytearray()
        self._threshold = 0

    def clear(self) -> None:
        """Local stop/disconnect emits no wire STOP."""
        self.pending.clear()
        self._threshold = 0
        self.command = None

    def start(self, command: SleepCommand) -> None:
        """Normal command start clears assembly; SXB preserves it."""
        if not self.sxb:
            self.clear()
        self.command = command

    def feed(self, chunk: bytes) -> bytes | None:
        """Return the entire accumulated payload when the source threshold passes.

        Ordinary responses use ONLY the low length byte. SXB report transfer
        strips fourteen bytes from every notification, not just its first one.
        Header and request ID are not validated by the app.
        """
        if self.command is None:
            self.pending.clear()
            return None
        if self.command == "q_report_allow":
            if self.sxb:
                if len(chunk) < sleep_envelope.HEADER_SIZE:
                    raise MalformedNotification("SXB report chunk lacks its 14-byte prefix")
                chunk = chunk[sleep_envelope.HEADER_SIZE :]
            self.pending.extend(chunk)
            if len(self.pending) < self.report_size:
                return None
            result = bytes(self.pending)
            self.pending.clear()
            return result
        if not self.pending:
            if (size := sleep_envelope.response_size(chunk)) is None:
                raise MalformedNotification("Sleep response lacks its length byte")
            self._threshold = size
        self.pending.extend(chunk)
        if len(self.pending) < self._threshold:
            return None
        result = bytes(self.pending)
        self.pending.clear()
        self._threshold = 0
        if len(result) < sleep_envelope.HEADER_SIZE:
            raise MalformedNotification("Sleep response lacks its payload prefix")
        return result[sleep_envelope.HEADER_SIZE :]


def response_command(text: str, *, sxb: bool, active: str | None) -> str | None:
    """SXB checks whole-text substrings in order; MM uses the active command."""
    if not sxb:
        return active
    # Keep the source precedence, including the shadowed OTA suffix selectors.
    for name in (
        "s_time",
        "q_time",
        "q_part",
        "s_part",
        "q_realtime",
        "q_report",
        "s_init",
        "q_ota",
        "q_ota_ttl",
        "q_ota_ttl",
        "s_ota",
        "s_ota_crc",
        "q_sens",
        "s_sens",
        "q_antiSnore",
        "s_antiSnore",
    ):
        if name in text:
            return name
    return None


def new_day_layout(version: str) -> bool:
    """The source version predicate, including its explicit major-one exception."""
    parts = [int(value) for value in version.split(".")]
    if parts[0] == 1:
        return False
    target = [0, 0, 3, 0]
    size = max(len(parts), len(target))
    return parts + [0] * (size - len(parts)) >= target + [0] * (size - len(target))


@dataclass(frozen=True, slots=True)
class LiveState:
    """App display fields. Their labels do not establish medical accuracy."""

    first_value: str | None
    second_value: str | None
    on_bed: bool | None
    moving: bool | None
    snoring: bool | None
    online: bool


def normal_live(text: str) -> LiveState:
    """Decode the MM hyphen-delimited display record with its validity gates."""
    parts = text.split("-")
    try:
        values = [int(part) for part in parts]
        online, on_bed = values[4] > 0, values[0] > 0
        return LiveState(
            parts[2] if online and on_bed else None,
            parts[3] if online and on_bed else None,
            on_bed if online else None,
            values[5] > 0 if online else None,
            values[7] > 0 if online else None,
            online,
        )
    except (ValueError, IndexError) as err:
        raise MalformedNotification("Invalid MM live record") from err


def sxb_live(values: list[int | float]) -> LiveState | None:
    """A nonzero SXB header leaves prior display state unchanged."""
    if not values or values[0] != 0:
        return None
    if len(values) < 5:
        raise MalformedNotification("SXB live record lacks required fields")
    status = values[1]
    on_bed = True if status in (1, -4, -2, -3) else False if status == 0 else None
    return LiveState(
        str(values[2]) if status != 0 else None,
        str(values[3]) if status != 0 else None,
        on_bed,
        True if status in (-2, -3) else None,
        True if values[4] == 1 else None,
        True,
    )
