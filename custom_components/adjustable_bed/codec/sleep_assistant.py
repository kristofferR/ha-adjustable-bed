"""Sleep Assistant 2.5.5: binary AA controls and uppercase ASCII settings.

Linx's AA frame has an extra reserved byte and different preset handling;
Keeson's E5/P2 carriers also fail the frozen literals. Notifications remain
binary and complete per callback, without an invented checksum or assembler.
"""

from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from datetime import datetime
from typing import Final

SERVICE: Final = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
WRITE: Final = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
NOTIFY: Final = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
INSTRUCTIONS: Final = frozenset(
    {
        0,
        1,
        2,
        4,
        8,
        16,
        32,
        64,
        128,
        256,
        512,
        1024,
        2048,
        4096,
        8192,
        16384,
        32768,
        65536,
        131072,
        8388608,
        16777216,
        33554432,
        134217728,
        536870912,
        1073741824,
        -2147483648,
    }
)


def instruction(value: int) -> bytes:
    value = ((value + 2**31) % 2**32) - 2**31
    return aa_key(value if value in INSTRUCTIONS else 0)


def aa_key(value: int) -> bytes:
    """The shared fourteen-byte AA carrier, before an app's sparse-key gate."""
    body = b"\xaa\x03\x00\x0a\x00\x04\x01" + (value & 0xFFFFFFFF).to_bytes(4, "little")
    return body + bytes((~sum(body[5:11]) & 255, 0xF3, 0x55))


def rgb(mode: int, value: int, red: int = 0, green: int = 0, blue: int = 0) -> bytes:
    body = b"\xaa\x01\x00\x10\x00\x0a\x01\x00\x00\x00\x00" + bytes(
        (mode & 255, value & 255, 0xBB, red & 255, green & 255, blue & 255)
    )
    body += bytes((~sum(body[5:17]) & 255,))
    return body + bytes((~sum(body[1:18]) & 255, 0x55))


def scaled_rgb(color: tuple[int, int, int], level: float) -> tuple[int, int, int]:
    """Java float32 multiplication, then truncation, of the inverted channels."""

    def channel(value: int) -> int:
        return int(
            struct.unpack(
                "f",
                struct.pack("f", (255 - value) * struct.unpack("f", struct.pack("f", level))[0]),
            )[0]
        )

    red, green, blue = color
    return channel(red), channel(green), channel(blue)


def rgb_channels(red: int, green: int, blue: int, level: float) -> bytes:
    return rgb(1, 1, *scaled_rgb((red, green, blue), level))


def light(value: int = 0, query: bool = True) -> bytes:
    body = bytes((0xAA, 1, 0, 9, int(query), 0x21, 0, 0, 2, 0, value & 255))
    return body + bytes((~sum(body[1:11]) & 255, 0x55))


def ascii_frame(body_hex: str) -> bytes:
    return (body_hex.upper() + f"{~sum(bytes.fromhex(body_hex)) & 255:02X}").encode("ascii")


def serial_identity(serial: str) -> bytes:
    if len(serial) != 8 or not serial.isascii() or not serial.isdecimal():
        raise ValueError("The selected BLE identity needs eight decimal digits")
    pairs = [int(serial[i : i + 2]) for i in range(0, 8, 2)]
    return (
        "7D0E00"
        + "".join(f"{v:02X}" for v in reversed(pairs))
        + "AB54"
        + f"{117 - sum(pairs) & 255:02X}"
    ).encode("ascii")


def clock(fields: list[int] | tuple[int, ...]) -> bytes:
    return ascii_frame("7308" + bytes(fields).hex())


def local_clock(now: datetime) -> bytes:
    return clock(
        (
            now.year // 100,
            now.year % 100,
            now.month,
            now.day,
            now.isoweekday() % 7,
            now.hour,
            now.minute,
            now.second,
        )
    )


def alarm(slot: int, hour: int, minute: int, position: str, week_mask: int, enabled: bool) -> bytes:
    pos = "10" if position == "0" else "80" if position == "2" else "03"
    return ascii_frame(
        f"7B07{slot:02d}{hour:02X}{minute:02X}00{pos}{week_mask:02X}{int(enabled):02X}"
    )


def clear_alarm(slot: int) -> bytes:
    return ascii_frame(f"7B07{slot:02d}" + "00" * 6)


ALARM_QUERY: Final = b"7102060680"
ANTI_SNORE_QUERY: Final = b"79031602016A"


def anti_snore(level: int, intensity: int, package: int, period: int, movement: int) -> bytes:
    mapped = 4 - level if level in (1, 2, 3) else 0
    parts = [0] * 14
    if mapped:
        for start, value in ((0, intensity), (3, package), (6, movement)):
            parts[start + 3 - mapped] = value
        parts[12] = period
    body = "7815" + ("0" + str(level))[:2] + bytes(parts).hex().upper()
    crc = 114 - level - intensity - package - period - movement if mapped else 114
    return (body + f"{crc & 255:02X}").encode("ascii")


def anti_hours(begin: int = 6, end: int = 21) -> bytes:
    b, e = (48 if v == -1 else v for v in (begin, end))
    crc = 31 if -1 in (begin, end) else 127 - begin - end
    return f"7A06{b:02X}0000{e:02X}0000{crc:02X}".encode("ascii")


def storage(enabled: int) -> bytes:
    return ascii_frame("600473653D" + ("00" if enabled == 0 else "01"))


def storage_query() -> bytes:
    return ascii_frame("610473653D3F")


def gain(side: str, value_hex: str) -> bytes:
    """The source overwrites both ports irrespective of side."""
    value = value_hex.upper()[:2]
    return ascii_frame("7504" + value + "00" + value + "00")


def out_of_bed(queue: str, king: str) -> bytes:
    return ascii_frame("7D13" + queue.upper() + king.upper())


def bed_calibration(lift_time: int, lift_speed: int, down_time: int, down_speed: int) -> bytes:
    body = (
        b"\xaa\x05\x01\x09\x00"
        + lift_time.to_bytes(2, "little")
        + bytes((lift_speed & 255,))
        + down_time.to_bytes(2, "little")
        + bytes((down_speed & 255,))
    )
    return body + bytes((~sum(body[1:11]) & 255, 0x55))


def split_notifications(data: bytes) -> list[bytes]:
    if len(data) > 2 and data[:2] != b"\xdd\xee":
        return [data]
    frames: list[bytes] = []
    current = bytearray()
    active = False
    for i, value in enumerate(data):
        last = i == len(data) - 1
        following = value if last else data[i + 1]
        if value == 0xDD and not last and following == 0xEE and not active:
            current = bytearray((value,))
            active = True
        elif value == 0xEE and not last and following == 0xDD and active:
            current.extend((value, following))
            frames.append(bytes(current))
            active = False
        elif active:
            current.append(value)
    return frames or [data]


def signed(value: int) -> int:
    return value - 256 if value >= 128 else value


def remote_fields(data: str, hw218: bool = False) -> dict[str, object]:
    b = bytes.fromhex(data)
    n = len(b)
    if n < 4:
        return {}
    out: dict[str, object] = {}

    def timer(value: int) -> None:
        if value in (255, 1, 2, 3):
            out["timer"] = {255: -1, 1: 0, 2: 1, 3: 2}[value]

    if b[:4] == b"\xdd\xee\x09\xa1" and n > 6:
        out["palette"] = b[6]
    if n > 22:
        if b[2:4] == b"\x10\x9c" or b[13:15] == b"\x10\x9c":
            nibble = b[28] >> 4 if b[13:15] == b"\x10\x9c" and n > 30 else b[17] >> 4
            if nibble > 5:
                out["one_key"] = True
        if n > 44 and b[23:25] == b"\xdd\xee" and b[26] == 1:
            out["massage"] = True
            timer(b[39])
    if b[2:4] == b"\x04\x9d" and n > 32:
        out["massage"] = True
        timer(b[27])
    if b[:4] == b"\xdd\xee\x14\x94" and n > 19:
        out["brightness_logged"] = b[19]
        if hw218:
            out["light"] = signed(b[15]) >> 6 > 0
    if n == 19 and b[0] == 0xDD:
        out["light"] = signed(b[14]) >> 6 > 0
    elif n == 22 and b[0] == 0xDD:
        out["light"] = signed(b[15]) >> 6 > 0
    if n == 19:
        timer(b[15])
    if b[:2] == b"\xdd\xee" and b[3] == 1:
        if n in (22, 33):
            timer(b[16])
        if n == 32:
            timer(b[21])
            out["light"] = signed(b[19]) >> 6 > 0
        if hw218:
            out["massage"] = True
            if n in (19, 22):
                out["light"] = signed(b[14 if n == 19 else 15]) >> 6 > 0
    return out


def corrected_float(text: str) -> float | None:
    try:
        return float(text)
    except ValueError:
        fixed = text.replace(",", ".")
        for char in "abcdef":
            fixed = fixed.replace(char, "0")
        try:
            number = float(fixed)
            return number + 1 if number < 1 else number
        except ValueError:
            return None


def version_fields(data: str, kind: int) -> str | None:
    b = bytes.fromhex(data)
    if kind not in (1, 2, 3):
        return "00"
    major, minor = {1: (3, 4), 2: (9, 10), 3: (7, 8)}[kind]
    if len(b) <= max(major, minor):
        return None
    number = corrected_float(
        str(signed(b[major])) + "." + format(signed(b[minor]) & 0xFFFFFFFF, "x").zfill(2)
    )
    return f"{number:.2f}" if number is not None else None


def dsp_fields(data: str) -> str | None:
    b = bytes.fromhex(data)
    if len(b) < 15:
        return None
    text = "".join(chr(signed(b[i]) & 0xFFFF) for i in range(3, 15) if b[i] != 46 or i == 4)
    number = corrected_float(text)
    return f"{number:.2f}" if number is not None else None


def raw_fields(data: str, bt: float = 3.0) -> dict[str, object]:
    b = bytes.fromhex(data)
    if not b:
        return {}
    if b[0] == 0x8D and len(b) == 22:
        return {
            "gain_queue": b[3],
            "gain_king": b[4],
            "queue": (b[5:9][::-1] + b[9:13][::-1]).hex(),
            "king": (b[13:17][::-1] + b[17:21][::-1]).hex(),
        }
    if b[0] == 0x90 and len(b) == 7:
        return {"storage": b[5] != 0}
    if b[0] == 0x8A and len(b) >= 16 and b[15] in (0, 1) and b[14] in (0, 1):
        out: dict[str, object] = {"side": "left" if b[15] == 1 else "right", "absent": b[14] == 1}
        if b[14] == 0:
            out.update(
                heart=signed(b[9]),
                breathing=signed(b[10 if bt < 3 else 11]),
                movement=signed(b[12 if bt < 3 else 13]),
            )
            out["increment_twitch"] = out["movement"] != 0
        else:
            out.update(heart="--", breathing="--", twitch_reset=0)
        return out
    return {}


def scalar_fields(data: str) -> dict[str, object]:
    b = bytes.fromhex(data)
    if not b:
        return {}
    if b[0] == 0x84 and len(b) == 18:
        level = b[2]
        pair = (b[5 + level], b[8 + level]) if level in (1, 2, 3) else (0, 0)
        return {
            "level": {1: "HIGH", 2: "MID", 3: "LOW"}.get(level, "OFF"),
            "trigger": [b[15], pair[0], pair[1], level],
        }
    if b[0] == 0x83 and len(b) == 10:
        if b[6] == 0:
            return {"time": "", "position": "", "state": "", "week": ""}
        week = (
            "Alarm"
            if b[7] == 0
            else ", ".join(
                name
                for bit, name in (
                    (1, "Mon"),
                    (2, "Tue"),
                    (3, "Wed"),
                    (4, "Thur"),
                    (5, "Fri"),
                    (6, "Sat"),
                    (0, "Sun"),
                )
                if b[7] & (1 << bit)
            )
        )
        return {
            "time": f"{b[3]:02d}:{b[4]:02d}",
            "position": "Zero G" if b[6] == 16 else "Massage",
            "state": "open" if b[8] == 1 else "close",
            "week": week,
        }
    return {}


def ergosportive_secondary_release() -> bytes:
    """A100 Hardware221: signed sums, terminator assigned after both checksums."""
    frame = bytearray.fromhex("aa07000c000405010000000000000000")
    frame[13] = (448 - sum(signed(value) for value in frame)) & 255
    frame[14] = (425 - sum(signed(value) for value in frame)) & 255
    frame[15] = 0x55
    return bytes(frame)


@dataclass(slots=True)
class ErgoSportiveNormalSensor:
    """Only an explicitly selected OldDSP normal stream, never auto DSP/side inference.

    Refuse truncated data safely. The app has no checksum/length gate here;
    presence values other than 0/1 retain prior readings, including signed rates.
    """
    heart: int | None = None
    respiration: int | None = None
    presence: bool | None = None
    twitch: int = 0

    def feed(self, data: bytes) -> bool:
        if len(data) < 15 or data[0] != 0x8A:
            return False
        if data[14] == 0:
            self.heart, self.respiration = signed(data[9]), signed(data[10])
            self.presence = True
            self.twitch += bool(data[12])
            return True
        if data[14] == 1:
            self.heart = self.respiration = None
            self.presence, self.twitch = False, 0
            return True
        return False


# Softide 1.2.4's auxiliary records are frozen literals, not an inferred
# parameter/checksum family. The AA carrier above reproduces all its key frames.
SOFTIDE_LITERALS: Final = {
    "query": bytes.fromhex("AA100009000303020708E8E755"),
    "relaxation": bytes.fromhex("AA0B001000100A040404040000EE0A0000DDE555"),
    "lumbar_relaxation": bytes.fromhex("AA0B001000100A030303030000EE0E0000DDE555"),
    "sleep_relaxation": bytes.fromhex("AA0B001000100A020202020000EE090000E6E555"),
    "prepare_program": bytes.fromhex("AA07000C00040501B00400000045E955"),
    "disable_uploads": bytes.fromhex("AA100009000303000000F9E755"),
    "prepare_frequency": bytes.fromhex("AA0B001000100A000000000000EE040000F3E555"),
}


@dataclass(frozen=True, slots=True)
class SoftideData:
    bm: int = 0
    br: int = 0
    hr: int = 0
    lb: int = 0
    si: int = 0
    sn: int = 0

    @property
    def rates(self) -> tuple[int, int]:
        return (self.hr, self.br) if self.lb == 0 else (0, 0)


@dataclass(frozen=True, slots=True)
class SoftideFunction:
    Ftype: int = 0
    FuncF: int = 0
    Tim: int = 0
    Tmasg: int = 0
    fmasg: int = 0
    hmasg: int = 0

    @property
    def timer_minutes(self) -> int | None:
        if self.Ftype != 0:
            return None
        # Java integer division truncates toward zero, including negative input.
        return (abs(self.Tim) // 6000 * (-1 if self.Tim < 0 else 1) + 1
                if self.FuncF == 1 else 0)


@dataclass(frozen=True, slots=True)
class SoftideNotification:
    device: str | None
    timestamp: str | None
    data: SoftideData | SoftideFunction


def softide_notification(packet: bytes) -> SoftideNotification | None:
    """Whole-callback Gson records, exact field case and signed-byte-to-char.

    Null/truncated/malformed records are ignored safely. There is no stream
    assembler, checksum, response opcode or command acknowledgement.
    """
    try:
        obj = json.loads("".join(chr(b if b < 128 else b + 0xFF00) for b in packet))
        if not isinstance(obj, dict) or not isinstance(obj.get("data"), dict):
            return None
        code = obj.get("code", 0)
        cls = SoftideData if code == 1 else SoftideFunction if code == 3 else None
        if cls is None:
            return None
        fields = {}
        for key in cls.__dataclass_fields__:
            value = obj["data"].get(key, 0)
            if value is None:
                value = 0
            if type(value) is not int or not -(2**31) <= value < 2**31:
                return None
            fields[key] = value
        return SoftideNotification(
            obj.get("dvid") if isinstance(obj.get("dvid"), str) else None,
            obj.get("ts") if isinstance(obj.get("ts"), str) else None,
            cls(**fields),
        )
    except (ValueError, UnicodeError):
        return None
