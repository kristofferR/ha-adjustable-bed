"""GM Control 4.6.6 binary BLE primitives (accepted row102, protocol P1).

These are independent of the older RMControl app profile. Source identities,
wire vectors and intentional malformed-input handling are documented in the
row102 disposition ledger. Integers are masked only at the native byte boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

# The names here are artifact selector identities, not inferred hardware families.
_PREFIXES = {
    "deviceFunctionItemExitLimit": (110, 2, 1),
    "deviceFunctionItemCheckClock": (110, 8, 1),
    "deviceFunctionItemCheckLight": (110, 10, 0),
    "deviceFunctionItemCheckMusic": (110, 21, 1),
    "deviceFunctionItemCheckAroma": (110, 26, 0),
    "deviceFunctionItemCheckMattress": (94, 26, 0),
    "deviceFunctionItemCheckSnore": (110, 33, 0),
    "deviceFunctionItemCheckSpeech": (110, 34, 0),
    "deviceFunctionItemCheckDetection": (110, 154, 192),
    "deviceFunctionItemSendStartDetection": (110, 136, 194),
    "deviceFunctionItemQueryVersion": (110, 154, 0),
    "deviceFunctionVersionOneBedCurrentMode": (110, 154, 16),
    "deviceFunctionVersionOneMotor1CurrentAngle": (110, 154, 48),
    "deviceFunctionVersionOneMotor2CurrentAngle": (110, 154, 48),
    "deviceFunctionVersionOneMotor3CurrentAngle": (110, 154, 48),
    "deviceFunctionVersionOneMotor4CurrentAngle": (110, 154, 48),
    "deviceFunctionVersionOneCurrentMassageMode": (110, 154, 160),
    "deviceFunctionVersionOneCurrentBedLightStatus": (110, 154, 176),
}


def sum_frame(values: tuple[int, ...] | list[int]) -> bytes:
    """Append the app's sum8, then apply the native integer-to-byte conversion."""
    return bytes(v & 255 for v in (*values, sum(values)))


@dataclass(frozen=True, slots=True)
class Material:
    """The resolved, product-specific command overrides of one app control."""

    name: str
    opcode: int
    long_opcode: int | None = None
    short_override: int | None = None
    long_override: int | None = None
    single_override: int | None = None

    def packet(self, *, side: int, single: bool, long: bool = False) -> bytes:
        """Build a common command after caller/gesture admission."""
        if side not in (0, 1, 2):
            raise ValueError("GM Control side must be left, right or both")
        if long:
            code = self.long_override if self.long_override is not None else self.long_opcode or 0
        else:
            code = self.short_override if self.short_override is not None else self.opcode
            if single and self.single_override is not None:
                code = self.single_override
        if single:
            return bytes((code & 255,))
        return sum_frame((*_PREFIXES.get(self.name, (110, 1, side)), code))


def stop_packet(*, side: int, single: bool) -> bytes:
    """The artifact's side-scoped release, with no inherited remote overrides."""
    return Material("deviceFunctionItemStop", 110).packet(side=side, single=single)


def clock_frames(now: datetime) -> tuple[bytes, bytes]:
    """Unix seconds/whole-hour zone, followed by the local calendar record."""
    offset = now.utcoffset()
    if offset is None:
        raise ValueError("GM Control clock requires an aware datetime")
    timestamp = int(now.timestamp())
    if not 0 <= timestamp <= 0xFFFFFFFF or not 1970 <= now.year <= 2225:
        raise ValueError("Date is outside the GM Control wire range")
    return (
        sum_frame(
            (
                110,
                12,
                32,
                8,
                2,
                1,
                *timestamp.to_bytes(4, "big"),
                int(offset.total_seconds() / 3600),
            )
        ),
        sum_frame(
            (
                110,
                13,
                32,
                8,
                3,
                1,
                now.year - 1970,
                now.month,
                now.day,
                now.hour,
                now.minute,
                now.second,
            )
        ),
    )


def countdown_frames(minutes: int, opcode: int) -> tuple[bytes, bytes]:
    """The minute countdown and action frames; zero/zero cancels."""
    if not 0 <= minutes <= 65535 or not 0 <= opcode <= 255:
        raise ValueError("Countdown fields are outside their wire ranges")
    return (sum_frame((110, 5, minutes & 255, 0)), sum_frame((110, 6, minutes // 256, opcode)))


def countdown_minutes(target: datetime, now: datetime) -> int:
    """Source 0x777d30: local minute records, then one fixed 86400s rollover.

    It compares epoch seconds after reconstructing both local date records with
    zero seconds. The nonpositive branch adds 24 hours, including across DST;
    it does not advance the local calendar to its next date.
    """
    if target.utcoffset() is None or now.utcoffset() is None:
        raise ValueError("Alarm times require an explicit timezone")
    seconds = int(target.replace(second=0, microsecond=0).timestamp()) - int(
        now.replace(second=0, microsecond=0).timestamp()
    )
    minutes = int(seconds / 60)
    return minutes if minutes > 0 else int((seconds + 86400) / 60)


def repeating_alarm(fields: tuple[int, int, int, int, int, int]) -> bytes:
    """Encode all six source bean fields, including its distinct record flag."""
    if any(not 0 <= x <= 255 for x in fields):
        raise ValueError("Alarm fields must fit in bytes")
    return sum_frame((110, 13, 32, 5, 1, 1, *fields))


def delete_alarm(slot: int) -> bytes:
    """Delete one selected repeat alarm."""
    if not 0 <= slot <= 255:
        raise ValueError("Alarm slot must fit in one byte")
    return sum_frame((110, 8, 32, 5, 2, 1, slot))


def query_alarm() -> bytes:
    """Request the repeat alarm table."""
    return sum_frame((110, 8, 32, 5, 1, 0, 0))


def light_timeout(seconds: int) -> bytes:
    """Zero selects the source's unlimited 65535 sentinel."""
    if not 0 <= seconds <= 65535:
        raise ValueError("Light timeout is outside the 16-bit wire range")
    seconds = seconds or 65535
    return sum_frame((110, 11, seconds >> 8, seconds & 255))


def light_color(rgb: tuple[int, int, int]) -> bytes:
    """Return the two concatenated RGB packets, in their original order."""
    if any(not 0 <= x <= 255 for x in rgb):
        raise ValueError("RGB components must fit in one byte")
    red, green, blue = rgb
    return sum_frame((110, 12, 255, red)) + sum_frame((110, 13, green, blue))


def snore_config(mode: Literal["count", "time"], value: int) -> bytes:
    """Configure the intervention quantity; separate from the enable command."""
    if mode not in ("count", "time") or not 0 <= value <= 255:
        raise ValueError("Invalid anti-snore setting")
    return sum_frame((110, 10, 32, 6, 5, 1, 1 if mode == "count" else 2, 0, value))


def snore_enabled(enabled: bool) -> bytes:
    """Enable/disable the source's anti-snore intervention."""
    return sum_frame((110, 9, 32, 6, 1, 1, 0, int(enabled)))


def query_snore(*, configuration: bool = False) -> bytes:
    """Read the intervention enable flag or its configuration."""
    return sum_frame((110, 9, 32, 6, 5, 0, 0, 0) if configuration else (110, 8, 32, 6, 1, 0, 0))


def query_sleep_name() -> bytes:
    """The BLE sleep-module advertisement-name query, not Wi-Fi provisioning."""
    return sum_frame((110, 8, 32, 6, 3, 0, 0))


def desk_packet(material: Material, *, height: float = 0) -> bytes:
    """Dedicated desk builder; independent of the common command side/mode."""
    name = material.name
    code = material.short_override if material.short_override is not None else material.opcode
    if name.endswith("SetHeight"):
        if not 0 <= height <= 25599.99:
            raise ValueError("Height exceeds the two decimal-pair wire fields")
        return sum_frame((110, 136, int(height / 100), int(height % 100)))
    prefix = (
        149
        if name.endswith("Reset")
        else 145
        if "Change" in name
        else (148 if name.endswith("RequestData") else 1)
    )
    return sum_frame((110, prefix, 0, code))


def crc16(data: bytes) -> int:
    """Source CRC16 XMODEM: init zero, polynomial 1021, no reflection/xor."""
    crc = 0
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 65535
    return crc


class MalformedNotification(ValueError):
    """HA rejection of malformed app input, not an artifact-defined exception."""


class FrameBuffer:
    """P1 extraction before dispatch, with bounded safe handling of invalid lengths.

    The controller owns the real 500ms expiry timer. Legacy frames deliberately
    use the next 6e, or the current chunk end; they have no fixed length/checksum.
    Unlike the app's unbounded zero-length loop, HA drops the entire batch.
    """

    def __init__(self) -> None:
        self.pending = bytearray()

    def clear(self) -> None:
        self.pending.clear()

    def extract(self, data: bytes) -> tuple[tuple[int, bytes], ...]:
        """Extract all candidates, then validate their dispatch checksums."""
        self.pending.extend(data)
        frames: list[tuple[int, bytes]] = []
        while len(self.pending) >= 3:
            try:
                start = self.pending.index(110)
            except ValueError:
                self.clear()
                break
            del self.pending[:start]
            if len(self.pending) < 3:
                break
            kind = self.pending[1]
            if kind in (32, 33, 64):
                if kind == 64 and len(self.pending) < 4:
                    # The source throws here. HA safely keeps the partial header.
                    break
                length = int.from_bytes(self.pending[2:4], "big") if kind == 64 else self.pending[2]
                if length == 0:
                    self.clear()
                    raise MalformedNotification("Non-progressing zero-length notification")
                if len(self.pending) < length:
                    break
            else:
                try:
                    length = self.pending.index(110, 1)
                except ValueError:
                    length = len(self.pending)
            frame = bytes(self.pending[:length])
            del self.pending[:length]
            frames.append((kind, frame))
        accepted: list[tuple[int, bytes]] = []
        for kind, frame in frames:
            if len(frame) > 2 and kind in (32, 33):
                if sum(frame[:-1]) & 255 == frame[-1]:
                    accepted.append((kind, frame))
            elif len(frame) > 3 and kind == 64:
                if crc16(frame[:-2]) == int.from_bytes(frame[-2:], "big"):
                    accepted.append((kind, frame))
            else:
                accepted.append((0, frame))
        return tuple(accepted)
