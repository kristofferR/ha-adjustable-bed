"""SleepEase notification decoding and bounded, connection-owned assemblers."""

from __future__ import annotations

import json
import zlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo
from typing import cast

from .doublesleep_protocol import Cache, Json, Protocol, UIState

MAX_REPORT_BYTES = 4 * 1024 * 1024


def decode_json(text: str) -> Json:
    def reject_constant(value: str) -> None:
        raise ValueError(f"Invalid SleepEase JSON constant: {value}")

    try:
        return cast(Json, json.loads(text, parse_constant=reject_constant))
    except RecursionError as err:
        raise ValueError("SleepEase JSON is nested too deeply") from err


def inflate(data: bytes) -> str:
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        result = decoder.decompress(data, MAX_REPORT_BYTES + 1)
    except zlib.error as err:
        raise ValueError("Invalid SleepEase gzip report") from err
    if len(result) > MAX_REPORT_BYTES or decoder.unconsumed_tail or not decoder.eof:
        raise ValueError("Invalid or oversized SleepEase gzip report")
    return result.decode("utf-8")


def le(data: bytes, offset: int, size: int = 2) -> int:
    if len(data) < offset + size:
        raise ValueError("Truncated SleepEase notification")
    return int.from_bytes(data[offset : offset + size], "little")


def massage(data: bytes, *, p1: bool = False, sonic: bool = False) -> dict[str, int]:
    if p1:
        time = le(data, 4)

        def level(n):
            return n // 3 + n % 3 + int(n > 1)

        head, foot = level(data[7] & 15), level(data[8])
        return {
            "mode": data[6] if time else 0,
            "head": head,
            "foot": foot,
            "strength": max(head, foot),
            "time": 0 if time == 0 else time // 600 + 1,
            "running": int(time != 0),
        }
    if sonic:
        head, foot = data[7] & 15, data[8] & 15
        head, foot = head // 2 - 1 if head else 0, foot // 2 - 1 if foot else 0
        a, b, mode = le(data, 13) - 1, le(data, 15) - 1, data[11]
    else:
        head, foot = data[7] & 15, data[10] & 15
        head, foot = head // 3 + 1 if head else 0, foot // 3 + 1 if foot else 0
        a, b, mode = le(data, 8), le(data, 11), max(data[7] >> 4, data[10] >> 4)
    time = max(a // 600 + 1 if a > 0 else 0, b // 600 + 1 if b > 0 else 0)
    active = bool((head > 0 or foot > 0) and time)
    result = {
        "mode": mode if active else 0,
        "strength": max(head, foot) if active else 0,
        "head": head if active else 0,
        "foot": foot if active else 0,
        "time": time if active else 0,
        "running": int(active),
    }
    if sonic:
        result["source"] = data[9] & 15
    return result


def alarm(data: bytes, protocol: Protocol, now: datetime) -> dict[str, int]:
    if protocol == "p1":
        enabled = data[9]
        if enabled == 1 and data[4:8] == bytes(4):
            enabled = 0
        if enabled == 0:
            return {
                "hour": now.hour,
                "minute": now.minute,
                "days": 0,
                "preset": 0,
                "enabled": 0,
                "massage": 0,
            }
        hour, minute, days, preset, vibration = data[6], data[7], data[4], data[5], data[10]
    else:
        days, preset, enabled, hour, minute, vibration = data[7:13]
    return {
        "hour": hour,
        "minute": minute,
        "days": days if days >= 128 else 0,
        "preset": {1: 0, 9: 1, 5: 2, 6: 3, 8: 4}.get(preset, 0),
        "enabled": enabled,
        "massage": vibration,
    }


@dataclass
class Report:
    channel: str
    side: int
    status: int
    data: Json

    def attributes(self) -> dict[str, Json]:
        return {
            "channel": self.channel,
            "side": self.side,
            "status": self.status,
            "data": self.data,
        }


@dataclass
class BinaryHistory:
    protocol: Protocol
    buffer: bytearray = field(default_factory=bytearray)
    index: int = 0
    total: int = 0
    side: int = 0
    monthly: bool = False
    timer_generation: int = 0
    timer_pending: bool = False

    def feed(self, data: bytes) -> Report | None:
        if not data.startswith(b"\x2a\x00\x00\x07") or data[4] not in (132, 133, 134, 135):
            return None
        if data[5] in (7, 8) and data[6] == 1:
            self.total = le(data, len(data) - 4, 4)
            if self.total > MAX_REPORT_BYTES:
                raise ValueError("SleepEase report exceeds assembly limit")
            self.side = int(data[4] in (133, 135))
            self.monthly = data[4] in (134, 135)
            self.buffer.clear()
            self.index = 0
            self.timer_generation += 1
            self.timer_pending = self.protocol == "p2"
            if self.total == 0:
                self.timer_pending = False
                return Report("history", self.side, 1, {})
        elif data[6] == 2:
            if data[7] == self.index:
                if len(self.buffer) + len(data) - 8 > MAX_REPORT_BYTES:
                    raise ValueError("SleepEase report exceeds assembly limit")
                self.buffer.extend(data[8:])
                self.index += 1
            complete = (
                len(self.buffer) >= self.total
                if self.protocol == "p2"
                else len(self.buffer) == self.total
            )
            if not complete or not self.buffer and self.protocol == "p1":
                return None
            if not self.buffer:
                self.timer_pending = False
                return Report("history", self.side, 1, {})
            text = inflate(bytes(self.buffer))
            value = text if self.monthly else decode_json(text)
            if not isinstance(value, (str if self.monthly else dict)):
                raise ValueError("SleepEase daily report must be a JSON object")
            self.timer_pending = False
            return Report("history_month" if self.monthly else "history", self.side, 0, value)
        return None

    def timeout(self) -> Report | None:
        if not self.timer_pending:
            return None
        self.timer_pending = False
        return Report("history", self.side, 2, {})


@dataclass
class JsonReader:
    buffer: bytearray = field(default_factory=bytearray)
    index: int = 0
    side: int = 0

    def feed(self, data: bytes) -> dict[str, Json] | Report | None:
        if len(data) < 6:
            return None
        if data[2] <= 1:
            self.buffer.clear()
            # Shipped single-message decoding uses char codes, unlike gzip UTF-8.
            result = decode_json(data[14:].decode("latin1"))
            return result if isinstance(result, dict) else None
        if data[3] == self.index:
            if len(self.buffer) + len(data) - 14 > MAX_REPORT_BYTES:
                raise ValueError("SleepEase JSON report exceeds assembly limit")
            self.buffer.extend(data[14:])
            self.index += 1
        if data[2] == data[3] + 1:
            self.index = 0
            if not self.buffer:
                return None
            text = inflate(bytes(self.buffer))
            value = decode_json(text)
            if isinstance(value, dict):
                return Report("history", self.side, 0, value)
            if isinstance(value, list):
                return Report("history_month", self.side, 0, text)
        return None


def live(values: list[int], history: Sequence[Json], *, p3: bool = False) -> dict[str, Json]:
    if p3:
        status = {-4: 5, -3: 6, -2: 6, 0: 4, 1: 3}.get(values[1], 4)
        heart, breath = values[2:4]
        flag1 = values[0] != 0
        flag2 = values[0] == 0 and values[1] == 0 and values[6] < 8000000
    else:
        heart, breath, status = values[:3]
        flag1, flag2 = values[4] == 1, values[4] == 2
    return {
        "heart_rate": heart,
        "breath_rate": breath,
        "status": status,
        "flag1": flag1,
        "flag2": flag2,
        "history": [*history[1:], int(status == 6)],
        "raw": list(values),
    }


@dataclass
class Notifications:
    """One parser registration; retained Cache is owned by its physical address."""

    protocol: Protocol
    model: int
    cache: Cache
    ui: UIState = field(default_factory=UIState)
    state: dict[str, Json] = field(default_factory=dict)
    binary: BinaryHistory = field(init=False)
    json_reader: JsonReader = field(default_factory=JsonReader)
    privacy: bool = False
    legacy: list[bytes] = field(default_factory=list)
    legacy_count: int = 0
    legacy_expected: int = 0
    legacy_date_offsets: tuple[int, ...] = (7, 8, 9, 10, 11)

    def __post_init__(self) -> None:
        self.binary = BinaryHistory(self.protocol)
        for side in ("left", "right"):
            self.state[side + "_history"] = [0] * 8

    def _massage(self, data: bytes, *, sonic: bool = False) -> None:
        result = massage(data, p1=self.protocol == "p1", sonic=sonic)
        if self.protocol == "p2":
            target = self.cache.sonic if sonic else self.cache.regular
            target.update({key: result[key] for key in target})
        self.state.update({("sonic_" if sonic else "massage_") + k: v for k, v in result.items()})

    def _live(self, side: str, values: list[int], *, p3: bool = False) -> None:
        if self.privacy:
            values = [0] * (7 if p3 else 5)
            if p3:
                self.state["left_history"] = [0] * 8
                self.state["right_history"] = [0] * 8
        history = self.state.get(side + "_history", [0] * 8)
        if not isinstance(history, list):
            history = [0] * 8
        self.state.update({side + "_" + k: v for k, v in live(values, history, p3=p3).items()})

    def _json(self, value: dict[str, Json]) -> tuple[Report | None, bool]:
        command, val = value.get("cmd"), value.get("val")
        if command == "q_sens" and isinstance(val, dict):
            for wire, side in (("L", "left"), ("R", "right")):
                items = val[wire]
                if not isinstance(items, list) or not items or type(items[0]) is not int:
                    raise ValueError("Invalid SleepEase sensitivity")
                self.state[side + "_sensitivity"] = items[0]
            self.state["sensitivity_raw"] = val
        elif command == "q_part":
            if type(val) is int:
                self.state["use_side"] = {11: 1, 12: 3, 13: 2}.get(val, 0)
        elif command == "s_init" and isinstance(val, dict) and isinstance(val.get("ver"), str):
            version = val["ver"]
            if isinstance(version, str):
                condensed = "".join(part for part in version.split(".") if part != "0")
                if len(condensed) < 2:
                    raise ValueError("Short SleepEase sensor version")
                self.state["sensor_version"] = condensed[:2]
                self.state["sensor_version_raw"] = version
        elif command == "q_realtime" and isinstance(val, dict):
            # Correct the app's reuse of the first map value across both sides.
            for wire, side in (("L", "left"), ("R", "right")):
                if wire in val:
                    items = val[wire]
                    if (
                        not isinstance(items, list)
                        or len(items) < 7
                        or any(type(v) is not int for v in items)
                    ):
                        raise ValueError("Invalid SleepEase realtime data")
                    self._live(side, cast(list[int], items), p3=True)
        elif command == "q_report" and isinstance(val, dict) and type(val.get("fsize")) is int:
            if val["fsize"] == 0:
                return Report("history", self.json_reader.side, 1, {}), False
            return None, True
        self.state["last_json"] = value
        return None, False

    def feed(self, data: bytes, now: datetime) -> tuple[Report | None, bool]:
        if len(data) < 3:
            return None, False
        self.state["last_notification"] = data.hex()
        if data.startswith(bytes.fromhex("2a0000088102")):
            self.state["sensor_version"] = f"{data[6]}.{data[7]}"
        if data.startswith(bytes.fromhex("ea000007")):
            if data[4] == 1:
                self._live("left", list(data[6:11]))
            elif data[4] == 2:
                self._live("left", list(data[6:11]))
                self._live("right", list(data[11:]))
        elif data.startswith(bytes.fromhex("a61106")):
            trimmed = data[3:]
            # The shipped split passes only three values to a five-value
            # consumer. Preserve evidence without inventing missing fields.
            self.state["live_legacy_raw"] = list(trimmed)
            self.state["parser_error"] = "A61106 does not provide a complete five-field side"
        # This UI raw observer is independent of the concrete driver's MFP
        # parser and its local catch. A malformed function list must not hide a
        # complete slow-capability observation.
        if data.startswith(bytes.fromhex("2a000005810e")) and data[7] == 1:
            self.ui.slow = bool(data[10] & 1)
            self.ui.pwm = 30 if self.ui.slow else 0
            self.ui.timer = 10
            self.state["slow_anti_snore"] = self.ui.slow
        if self.protocol == "p3":
            result = self.json_reader.feed(data)
            return self._json(result) if isinstance(result, dict) else (result, False)
        if data.startswith(bytes.fromhex("2a000007")) and data[4] in (132, 133, 134, 135):
            return self.binary.feed(data), False
        if self.protocol == "p1":
            if data.startswith(b"\xa5\x0b"):
                if len(data) >= 19:
                    self.state.update(
                        privacy=data[14],
                        anti_state=data[15],
                        anti_mode={3: 2, 6: 3}.get(data[16], 1),
                        left_sensitivity=0,
                        right_sensitivity=0,
                        use_side=0,
                    )
                    self.privacy = data[14] != 0
                self._massage(data)
            elif data.startswith(b"\xa5\x0c"):
                self.state["alarm"] = alarm(data, self.protocol, now)
            return None, False
        if data.startswith(bytes.fromhex("2a000005810e")):
            try:
                if data[12]:
                    self.cache.light[0] = 0 if data[12] == 1 else 2
                if data[7] == 2:
                    functions = [le(data, 9 + i * 2) for i in range(data[8])]
                    self.ui.sonic_ui = 7 in functions
                    self.state["functions"] = functions
            except (ValueError, IndexError) as err:
                self.state["parser_error"] = str(err)
        elif data.startswith(bytes.fromhex("2a0000078109")):
            self.state.update(
                privacy=data[11],
                anti_state=data[6],
                anti_mode=data[8],
                left_sensitivity=data[13] & 15,
                right_sensitivity=data[13] >> 4,
                use_side=data[14],
            )
            self.privacy = data[11] != 0
            if self.ui.slow:
                self.ui.pwm = data[9]
        elif data.startswith(bytes.fromhex("2a0000048106")):
            if data[6] in (0, 2):
                self.cache.light[0] = data[6]
            for i in range(1, 6):
                self.cache.light[i] = data[i + 6]
            self.state["light"] = list(self.cache.light)
        elif data.startswith(bytes.fromhex("2a00000281")) and data[6] == 3:
            self._massage(data)
        elif data.startswith(bytes.fromhex("2a000006810b")):
            self._massage(data, sonic=True)
        elif data.startswith(bytes.fromhex("2a0000038108")) and data[6] == 1:
            self.state["alarm"] = alarm(data, self.protocol, now)
        return None, False

    @property
    def legacy_size(self) -> int:
        return 16 if self.model == 3 else 18 if self.model == 67 else 12

    def legacy_feed(self, data: bytes) -> bool:
        if data.startswith(bytes.fromhex("a60102")):
            self.legacy_expected = le(data, 3) // self.legacy_size
            return True
        if not data.startswith((b"\xa6\x30", b"\xa6\x31", b"\xa6\x3f\x02")):
            return False
        if len(data) % self.legacy_size:
            raise ValueError("Partial SleepEase legacy record packet")
        if len(self.legacy) * self.legacy_size + len(data) > MAX_REPORT_BYTES:
            raise ValueError("SleepEase legacy history exceeds assembly limit")
        self.legacy.extend(
            data[i : i + self.legacy_size] for i in range(0, len(data), self.legacy_size)
        )
        self.legacy_count += 1
        if self.legacy_count > self.legacy_expected:
            self.legacy_expected += 10
        return True

    def legacy_report(self, zone: tzinfo | None = None) -> dict[str, Json]:
        raw: list[Json] = [list(record) for record in self.legacy]
        records: dict[str, dict[str, Json]] = {"left": {}, "right": {}}
        if self.model == 67:
            self.legacy_date_offsets = (8, 9, 10, 11, 12)
        for record in self.legacy:
            sides = (("left", record),)
            if self.model == 3:
                sides = (
                    ("left", record[:3] + record[3:7] + record[-5:]),
                    ("right", record[:3] + record[7:11] + record[-5:]),
                )
            for side, data in sides:
                if not (3 <= data[5] <= 6 and data[5] != 4 and (data[6] & 16 or 1 <= data[6] <= 5)):
                    continue
                year, month, day, hour, minute = (data[i] for i in self.legacy_date_offsets)
                if year + 1900 <= 1970:
                    continue
                # Dart DateTime normalizes overflowing components.
                base_year, base_month = divmod((year + 1900) * 12 + month, 12)
                timestamp = datetime(base_year, base_month + 1, 1, tzinfo=zone) + timedelta(
                    days=day - 1, hours=hour, minutes=minute
                )
                records[side][timestamp.isoformat()] = {
                    "time": int(timestamp.timestamp() * 1000),
                    "local_time": timestamp.isoformat(),
                    "bedtype": 0 if side == "left" else 1,
                    "heart": data[3],
                    "breath": data[4],
                    "state": data[5],
                    "sleepState": data[6],
                    "breath_pause": data[7],
                    "raw": list(data),
                }
        return {
            "raw": raw,
            "left": [records["left"][k] for k in sorted(records["left"])],
            "right": [records["right"][k] for k in sorted(records["right"])],
            "notifications": self.legacy_count,
            "expected": self.legacy_expected,
        }


REPORT_SCALARS = (
    "sleepQualityScore",
    "inbedTime",
    "asleepTime",
    "awakeTime",
    "outbedTime",
    "inbedDuration",
    "sleepDuration",
    "soberDuration",
    "dreamDuration",
    "lightSleepDuration",
    "deepSleepDuration",
    "outbedDuration",
    "microAwakeningDuration",
    "soberPercent",
    "dreamPercent",
    "lightSleepPercent",
    "deepSleepPercent",
    "outbedPercent",
    "microAwakeningPercent",
    "standardHR",
    "maxHR",
    "minHR",
    "standardBR",
    "maxBR",
    "minBR",
    "snoreDuration",
    "movementDuration",
    "bedtype",
)


def daily_report(value: dict[str, Json]) -> dict[str, Json]:
    """The app's daily consumer, retaining all wire fields separately."""
    parsed: dict[str, Json] = {}
    for key in REPORT_SCALARS:
        item = value.get(key)
        if item is None:
            item = 0
        if type(item) is not int:
            raise ValueError(f"SleepEase report {key} must be an integer")
        parsed[key] = item
    for key in ("day", "device_id"):
        item = value.get(key)
        if item is None:
            item = ""
        if not isinstance(item, str):
            raise ValueError(f"SleepEase report {key} must be text")
        parsed[key] = item
    for key in ("sleepStage", "arrayHR", "arrayBR", "arrayBodyState"):
        items = value.get(key)
        if items is None:
            items = []
        if not isinstance(items, list) or any(type(v) is not int for v in items):
            raise ValueError(f"SleepEase report {key} must contain integers")
        parsed[key] = items
    sporadic = value.get("sporadicsleep")
    parsed["sporadicsleep"] = (
        decode_json(sporadic)
        if isinstance(sporadic, str)
        else sporadic
        if isinstance(sporadic, dict)
        else {}
    )
    return parsed


def report_records(report: Report) -> Json:
    if report.status != 0:
        return None
    if report.channel == "history" and isinstance(report.data, dict):
        return daily_report(report.data)
    if report.channel == "history_month" and isinstance(report.data, str):
        values = decode_json(report.data)
        if not isinstance(values, list):
            raise ValueError("SleepEase monthly report must contain objects")
        records: list[Json] = []
        for item in values:
            if not isinstance(item, dict):
                raise ValueError("SleepEase monthly report must contain objects")
            records.append(daily_report(item))
        return records if values and values[0] else None
    raise ValueError("Invalid SleepEase report consumer input")
