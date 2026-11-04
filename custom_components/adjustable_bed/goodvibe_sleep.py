"""Good Vibe Sleep type 1/type 2 receive state and report assembly."""

from __future__ import annotations

import json
import zlib
from dataclasses import dataclass, field
from typing import Never

from .goodvibe_schemas import parse_schema


def _invalid_constant(value: str) -> Never:
    raise ValueError(f"Invalid JSON number: {value}")


P3_ORDER = (
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
)
P2_ROUTES = {"s_time", "q_part", "s_part", "q_realtime", "q_report", "s_init"}
SCHEMA_ROUTES = {
    2: {
        "s_time": "0x6dff88",
        "q_part": "0x6dfdf0",
        "s_part": "0x6dfdf0",
        "q_realtime": "0x6dfa38",
        "q_report": "0x6df760",
    },
    3: {
        "s_time": "0x6d7e84",
        "q_time": "0x6d79f8",
        "q_part": "0x6d7858",
        "s_part": "0x6d7858",
        "q_realtime": "0x6d747c",
        "q_report": "0x6d7108",
        "q_sens": "0x6d6494",
        "q_antiSnore": "0x6d600c",
        "s_antiSnore": "0x6d600c",
    },
}


def new_day_schema(version: str) -> bool:
    parts = [int(x) for x in version.split(".")]
    if parts[0] == 1:
        return False
    other = [0, 0, 3, 0]
    length = max(len(parts), len(other))
    return parts + [0] * (length - len(parts)) >= other + [0] * (length - len(other))


@dataclass
class Realtime:
    heart: str = "--"
    respiration: str = "--"
    occupancy: str = "--"
    movement: str = "--"
    snore: str = "--"
    valid: bool = False

    def accept(self, kind: int, value: object) -> None:
        if kind == 2:
            if not isinstance(value, str):
                raise ValueError("Type 1 realtime requires a hyphen-separated string")
            data = [int(x) for x in value.split("-")]
            if len(data) < 8:
                raise ValueError("Truncated type 1 realtime")
            self.valid = data[4] > 0
            if not self.valid:
                self.heart = self.respiration = self.occupancy = self.movement = self.snore = "--"
                return
            self.occupancy = "On Bed" if data[0] > 0 else "Off Bed"
            self.heart, self.respiration = (
                (str(data[2]), str(data[3])) if data[0] > 0 else ("--", "--")
            )
            self.movement = "Body Move" if data[5] > 0 else "No Body Move"
            self.snore = "Snoring" if data[7] > 0 else "No Snoring"
            return
        if (
            not isinstance(value, list)
            or len(value) < 5
            or any(type(x) not in (int, float) for x in value)
        ):
            raise ValueError("Truncated or invalid type 2 realtime array")
        if value[0] != 0:
            return  # Invalid/reset marker retains the previous type 2 page state.
        status = value[1]
        self.valid = True
        self.occupancy = (
            "On Bed" if status in (1, -4, -2, -3) else "Off Bed" if status == 0 else "--"
        )
        self.movement = "Body Move" if status in (-2, -3) else "--"
        self.heart, self.respiration = (
            (str(value[2]), str(value[3])) if status != 0 else ("--", "--")
        )
        self.snore = "Snoring" if value[4] == 1 else "--"


@dataclass
class Receiver:
    kind: int
    last: str | None = None
    buffer: bytearray = field(default_factory=bytearray)
    target: int = 0
    report_size: int = 0
    report_type: int = 1
    rejection: str | None = None

    def clear(self) -> None:
        self.last = None
        self.buffer.clear()
        self.target = 0

    def begin(self, command: str) -> None:
        if self.kind == 2:
            self.clear()
        self.last = command

    def feed(self, data: bytes) -> tuple[str, dict[str, object]] | None:
        if not data:
            return None
        if self.last is None:
            self.buffer.clear()
            return None
        if self.last == "q_report_allow":
            if self.kind == 3:
                if len(data) < 14:
                    raise ValueError("Short report chunk")
                data = data[14:]
            self.buffer.extend(data)
            if len(self.buffer) < self.report_size:
                return None
            packed = bytes(self.buffer)
            self.buffer.clear()
            decoder = zlib.decompressobj(31)
            raw = decoder.decompress(packed, 2**20)
            if not decoder.eof or decoder.unconsumed_tail:
                raise ValueError("Oversized or incomplete gzip report")
            obj = json.loads(raw.decode("latin-1"), parse_constant=_invalid_constant)
            if self.report_type == 2:
                if not isinstance(obj, list):
                    raise ValueError("Month report must be a list")
                schema = "0x6e3860" if self.kind == 2 else "0x6ddeb0"
                return "report", {"records": [parse_schema(schema, row) for row in obj]}
            if self.report_type != 1:
                raise ValueError("Unknown sleep report type")
            if self.kind == 2:
                schema = "0x6e0bf0"
            else:
                if not isinstance(obj, dict):
                    raise ValueError("Day report must be an object")
                version = obj.get("algorithmVersion")
                schema = (
                    "0x6d8c0c"
                    if isinstance(version, str) and new_day_schema(version)
                    else "0x6dc034"
                )
            return "report", parse_schema(schema, obj)
        if not self.buffer:
            if len(data) < 13:
                raise ValueError("Short first sleep notification chunk")
            self.target = data[12] + 14
        self.buffer.extend(data)
        if len(self.buffer) > 2**20:
            raise ValueError("Oversized sleep notification")
        if len(self.buffer) < self.target:
            return None
        raw = bytes(self.buffer)
        self.buffer.clear()
        self.target = 0
        if len(raw) < 14:
            raise ValueError("Short assembled sleep notification")
        text = raw[14:].decode("latin-1")
        obj = json.loads(text, parse_constant=_invalid_constant)
        route = (
            next((cmd for cmd in P3_ORDER if cmd in text), None)
            if self.kind == 3
            else self.last
            if self.last in P2_ROUTES
            else None
        )
        if route is None or route not in SCHEMA_ROUTES[self.kind]:
            return None
        return route, parse_schema(SCHEMA_ROUTES[self.kind][route], obj)
