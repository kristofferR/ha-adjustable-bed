"""SIMMONS app (com.okin.simmons 1.12.9) frames, alarm rules and reply parsing.

Every value here comes from the accepted row049 clean-room report. The app
chooses the packet format from the Bluetooth name and, independently, the GATT
destination from the discovered services. Hardware acceptance is unverified.
Control masks and timing are the ``SIMMONS_PROFILES`` data: SmartBed names send
40-bit Okin N-frames, OKIN names the same masks in a Keeson E6 frame.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final, Literal

from ..codec import keeson, okin_nframe
from ..profiles.okin_nframe import SIMMONS_PROFILES

Protocol = Literal["okin", "smartbed"]
AlarmMode = Literal["custom_mode", "flat", "anti_snore"]

# GATT roles. The app compares upper-cased UUID strings and keeps scanning, so
# the last matching write and notify roles win independently of the protocol.
NUS_SERVICE: Final = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
NUS_WRITE: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NUS_NOTIFY: Final = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
FFE5_SERVICE: Final = "0000ffe5-0000-1000-8000-00805f9b34fb"
FFE9_WRITE: Final = "0000ffe9-0000-1000-8000-00805f9b34fb"
FFE0_SERVICE: Final = "0000ffe0-0000-1000-8000-00805f9b34fb"
FFE4_NOTIFY: Final = "0000ffe4-0000-1000-8000-00805f9b34fb"

# The inclined builders never check the protocol: they always emit the
# SmartBed frame, even when the OKIN response write mode is selected.
INCLINED_ACTIONS: Final = SIMMONS_PROFILES["okin"].plain_keys

ALARM_MODES: Final[tuple[AlarmMode, ...]] = ("custom_mode", "flat", "anti_snore")
_ALARM_TYPES: Final[dict[Protocol, tuple[int, int, int]]] = {
    "okin": (17, 28, 16),
    "smartbed": (5, 9, 4),
}
ONCE: Final = 128  # Weekday UI mask meaning "once"; bit 7 marks a repeat mask.

P1_ALARM_HEADER: Final = bytes((0xED, 0x80, 0x03))
P2_ALARM_HEADERS: Final = {bytes((0xA5, 0x0C, 0x0E)): 1, bytes((0xA5, 0x0D, 0x0E)): 2}


def resolve_protocol(name: str | None) -> Protocol:
    """Apply the app's lowercase prefix rule; an unmatched name aliases SmartBed."""
    lowered = (name or "").lower()
    if lowered.startswith("smartbed"):
        return "smartbed"
    if lowered.startswith("okin"):
        return "okin"
    return "smartbed"


def wire(values: Iterable[int]) -> bytes:
    """Mask every integer to one byte, like the app's hex bridge."""
    return bytes(value & 0xFF for value in values)


def checked(values: list[int]) -> bytes:
    """Mask every value to a byte, then append the Keeson complement checksum."""
    return keeson.checked(wire(values))


def control_frame(protocol: Protocol, action: str) -> bytes:
    """Return the control frame for an app action; ``stop`` is the zero word."""
    word = 0 if action == "stop" else SIMMONS_PROFILES["smartbed"].keys[action]
    if protocol == "okin" and action not in INCLINED_ACTIONS:
        return keeson.frame(word, header=0xE6, side=0)
    return okin_nframe.frame40(word)


def clock_frame(protocol: Protocol, now: datetime) -> bytes:
    """Return the local clock sync frame sent when the control page links."""
    fields = [now.year - 1900, now.month - 1, now.day, now.hour, now.minute, now.second]
    if protocol == "okin":
        return checked([0xE7, 0x80, 0x01, *fields])
    # Dart DateTime.weekday: Monday 1 through Sunday 7.
    return okin_nframe.clock(wire([*fields, now.isoweekday()]))


def query_frames(protocol: Protocol) -> tuple[bytes, ...]:
    """Return one manager query: both records (OKIN) or slot 1 then slot 2."""
    if protocol == "okin":
        return (checked([0xE1, 0x80, 0x03]),)
    return (okin_nframe.request(0xC0), okin_nframe.request(0xD0))


def alarm_type(protocol: Protocol, mode: str) -> int:
    """Map the app's custom/flat/anti-snore choice to the protocol wire type."""
    if mode not in ALARM_MODES:
        raise ValueError(f"Unknown SIMMONS alarm mode '{mode}'")
    return _ALARM_TYPES[protocol][ALARM_MODES.index(mode)]


def alarm_mode(protocol: Protocol, wire_type: int) -> AlarmMode | None:
    """Return the app label for a wire type, if it has one."""
    types = _ALARM_TYPES[protocol]
    return ALARM_MODES[types.index(wire_type)] if wire_type in types else None


def repeat_mask(weekdays: Iterable[int]) -> int:
    """Build the UI mask from Monday=0..Sunday=6 days; empty means once."""
    mask = ONCE
    for day in weekdays:
        mask |= 1 << ((day + 1) % 7)  # Sunday is bit 0, Saturday bit 6.
    return mask


def gain_weekday(mask: int, hour: int, minute: int, now: datetime) -> int:
    """Encode the wire weekday: repeat masks pass through, once picks the next day."""
    if mask > ONCE:
        return mask
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    delta = _absolute(target) - _absolute(now)
    micros = (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds
    # Whole milliseconds truncated toward zero; a past time adds an absolute
    # 24 hours, so a DST change can move the local hour or day.
    if micros <= -1000:
        target = (
            target + timedelta(hours=24)
            if target.tzinfo is None
            else (_absolute(target) + timedelta(hours=24)).astimezone(target.tzinfo)
        )
    return 1 << ((target.weekday() + 1) % 7)


def _absolute(value: datetime) -> datetime:
    """Compare aware times by elapsed time, as Dart's DateTime.difference does."""
    return value if value.tzinfo is None else value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class AlarmSlot:
    """The app's local record for one alarm slot."""

    hour: int
    minute: int
    weekday: int
    type: int
    enabled: bool

    def peer_record(self) -> list[int]:
        """Preserve another slot's record; a disabled slot sends weekday 0."""
        return [self.hour, self.minute, self.weekday if self.enabled else 0, self.type]


def p1_alarm_frame(slot1: list[int], slot2: list[int]) -> bytes:
    """Program both OKIN records: hour, minute, weekday, type for each slot."""
    return keeson.alarm_table(keeson.ALARM_WEEKLY, wire([*slot1, *slot2]))


def p2_alarm_frame(slot: int, weekday: int, wire_type: int, hour: int, minute: int) -> bytes:
    """Program one SmartBed record."""
    return okin_nframe.alarm(wire([weekday, wire_type, hour, minute, 0x00, 0x01, 0x01]), slot)


def p2_disable_frame(slot: int) -> bytes:
    """Disable one SmartBed record."""
    return okin_nframe.alarm(bytes(7), slot)


@dataclass(frozen=True, slots=True)
class AlarmReport:
    """Raw fields of one reported alarm record, before local overlays."""

    slot: int
    hour: int
    minute: int
    weekday: int
    type: int
    enabled: bool
    p1_record: bytes | None = None


def parse_p1_alarm(data: bytes) -> tuple[AlarmReport, AlarmReport] | None:
    """Decode an ED 80 03 reply; a record is enabled unless its weekday is 0 or 128."""
    if len(data) < 11 or data[:3] != P1_ALARM_HEADER:
        return None
    reports = tuple(
        AlarmReport(
            slot,
            data[offset],
            data[offset + 1],
            data[offset + 2],
            data[offset + 3],
            data[offset + 2] not in (0, ONCE),
            bytes(data[3:11]),
        )
        for slot, offset in ((1, 3), (2, 7))
    )
    return reports[0], reports[1]


def parse_p2_alarm(data: bytes) -> AlarmReport | None:
    """Decode an A5 0C/0D 0E reply; open=1 with all fields zero means disabled."""
    slot = P2_ALARM_HEADERS.get(bytes(data[:3]))
    if slot is None or len(data) < 10:
        return None
    weekday, wire_type, hour, minute = data[4], data[5], data[6], data[7]
    opened = data[9]
    if opened == 1 and not any((weekday, wire_type, hour, minute)):
        opened = 0
    return AlarmReport(slot, hour, minute, weekday, wire_type, opened >= 1)


def apply_report(
    report: AlarmReport, local: AlarmSlot | None, protocol_reply: Protocol
) -> AlarmSlot:
    """Apply the app's overlay: OKIN keeps the local weekday of an enabled record,
    SmartBed keeps local hour/minute/weekday of a disabled one. Without a local
    record (first reply in this HA run) the reported fields are used as-is."""
    hour, minute, weekday = report.hour, report.minute, report.weekday
    if local is not None:
        if protocol_reply == "okin" and report.enabled:
            weekday = local.weekday
        elif protocol_reply == "smartbed" and not report.enabled:
            hour, minute, weekday = local.hour, local.minute, local.weekday
    return AlarmSlot(hour, minute, weekday, report.type, report.enabled)


class NotificationAssembler:
    """The app's dispatcher: 20-byte FE 16 fragments are joined with the next input."""

    def __init__(self) -> None:
        self._fragment: bytes | None = None

    def feed(self, incoming: bytes) -> bytes | None:
        """Return a complete message to dispatch, or None while buffering/ignoring."""
        if len(incoming) < 3:
            return None
        data = self._fragment + incoming if self._fragment is not None else incoming
        self._fragment = None
        if len(incoming) == 20 and incoming[1:3] == b"\xfe\x16":
            self._fragment = bytes(incoming)
            return None
        return data
