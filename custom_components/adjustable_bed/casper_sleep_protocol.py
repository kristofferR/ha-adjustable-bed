"""Casper Base package-local MM/SXB sensor wire and mutable display contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal, cast

from .casper_base_protocol import Request, SensorKind
from .casper_sleep_schema import SCHEMAS

type Json = None | bool | int | float | str | list[Json] | dict[str, Json]
type Display = None | bool | str
DISPLAY_FIELDS = ("on_bed", "heart", "breath", "body_move", "snoring")
SERVICES = ("0000e0ff-3c17-d293-8e48-14fe2e4da212", "2320567c-05cf-6eb4-c341-772851827e1b")
WRITE = "00000002-3c17-d293-8e48-14fe2e4da212"
NOTIFY = "00000003-3c17-d293-8e48-14fe2e4da212"


def envelope(payload: dict[str, Json], sequence: int) -> bytes:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    size = format(len(body), "x").rjust(4, "0")
    return (
        bytes(
            (
                0,
                sequence & 255,
                1,
                0,
                (len(body) + 7) & 255,
                0,
                0,
                17,
                3,
                67,
                85,
                68,
                int(size[2:4], 16),
                int(size[:2], 16),
            )
        )
        + body
    )


def command(
    kind: SensorKind,
    action: str,
    sequence: int,
    request: Request,
    *,
    ts: int = 0,
    zone: str | int = 0,
) -> bytes:
    wire_command = action
    val: Json = None
    if action == "s_time":
        val = {"ts": ts, "tz" if kind == "mm" else "utc": zone}
    elif action == "q_part" and kind == "mm":
        wire_command = "s_part"
    elif action == "s_part":
        val = request.part
    elif action == "q_realtime":
        val = {"type": 0, "time": 1}
    elif action in ("q_report", "q_report_allow"):
        wire_command = "q_report"
        val = {
            "part": request.part,
            "type": request.report_type,
            "y": request.year,
            "m": request.month,
            "d": request.day,
        }
        if action == "q_report_allow":
            if kind == "sxb":
                val = {"allow": 1}
            else:
                val["allow"] = 1
    elif action == "s_init":
        val = 0
    return envelope({"id": sequence, "cmd": wire_command, "val": val}, sequence)


class Receive:
    """Per-device parser state; preserve wire decoding without shared-device races."""

    def __init__(self, kind: SensorKind) -> None:
        self.kind = kind
        self.action: str | None = None
        self.pending = bytearray()
        self.expected = 0
        self.report_size = 0

    def reset(self, action: str | None) -> None:
        self.action = action
        self.pending.clear()
        self.expected = 0

    def feed(self, chunk: bytes) -> Json:
        if not chunk or self.action is None:
            self.pending.clear()
            return None
        if self.action == "q_report_allow":
            if self.kind == "sxb":
                if len(chunk) < 14:
                    raise ValueError("Truncated SXB report fragment")
                chunk = chunk[14:]
            self.pending.extend(chunk)
            if len(self.pending) < self.report_size:
                return None
            payload = bytes(self.pending)
            self.pending.clear()
            # Bound corrupt/hostile compressed input. No medical interpretation.
            import zlib

            decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
            decoded = decoder.decompress(payload, 4 * 1024 * 1024 + 1)
            if len(decoded) > 4 * 1024 * 1024 or not decoder.eof:
                raise ValueError("Invalid or oversized sensor report")
            return cast(Json, json.loads(decoded.decode("latin1")))
        if not self.pending:
            if len(chunk) < 13:
                raise ValueError("Truncated sensor envelope")
            self.expected = chunk[12] + 14
        self.pending.extend(chunk)
        if len(self.pending) < self.expected:
            return None
        payload = bytes(self.pending[14:])
        self.pending.clear()
        return cast(Json, json.loads(payload.decode("latin1")))


def mapping(value: Json) -> dict[str, Json]:
    if not isinstance(value, dict):
        raise ValueError("Expected object")
    return value


def nullable(
    value: Json, kind: Literal["int", "num", "str"], name: str, *, required: bool = False
) -> Json:
    if value is None and not required:
        return None
    good = (
        type(value) is int
        if kind == "int"
        else type(value) in (int, float)
        if kind == "num"
        else type(value) is str
    )
    if not good:
        raise ValueError("Invalid " + name)
    return value


def numeric(value: Json, *, integer: bool = True) -> Json:
    nullable(value, "num", "numeric field")
    if value is None:
        return None
    assert isinstance(value, (int, float))
    return int(value) if integer else float(value)


def live_typed(
    value: Json, kind: SensorKind
) -> tuple[str | list[int | float], str | list[int | float]]:
    val = mapping(value)
    result: list[str | list[int | float]] = []
    for side in ("L", "R"):
        item = val.get(side)
        if kind == "mm":
            if not isinstance(item, str):
                raise ValueError("Expected live " + side + " String")
            result.append(item)
        else:
            if item is None:
                item = []
            if not isinstance(item, list) or any(type(x) not in (int, float) for x in item):
                raise ValueError("Expected live " + side + " numeric list")
            result.append(cast(list[int | float], item))
    return result[0], result[1]


def decode_bean(name: str, value: Json) -> dict[str, Json]:
    """Validate known fields in artifact evaluation order; preserve nulls and numbers."""
    obj = mapping(value)
    out: dict[str, Json] = {}
    for key, (kind, child) in SCHEMAS[name].items():
        val = obj.get(key)
        if kind == "dynamic":
            out[key] = val
        elif val is None and (kind.endswith("?") or kind == "nums"):
            out[key] = [] if kind == "nums" else None
        elif kind.startswith("object"):
            out[key] = decode_bean(child, val)
        elif kind.startswith(("list", "ints", "nums")):
            if not isinstance(val, list):
                raise ValueError("Invalid list " + key)
            if child:
                out[key] = [decode_bean(child, item) for item in val]
            elif kind.startswith(("ints", "nums")):
                for item in val:
                    nullable(item, "num", key, required=True)
                out[key] = [numeric(item) for item in val] if kind.startswith("ints") else val
            else:
                out[key] = val
        elif kind.startswith(("to_int", "to_float")):
            nullable(val, "num", key, required=not kind.endswith("?"))
            out[key] = numeric(val, integer=kind.startswith("to_int"))
        else:
            out[key] = nullable(
                val,
                cast(Literal["int", "num", "str"], kind.rstrip("?")),
                key,
                required=not kind.endswith("?"),
            )
    return out


@dataclass(slots=True)
class Live:
    """Sequential app display merger, including partial mutation before errors."""

    kind: SensorKind
    state: dict[str, dict[str, Display]] = field(
        default_factory=lambda: {side: dict.fromkeys(DISPLAY_FIELDS) for side in ("L", "R")}
    )
    valid: dict[str, bool] = field(default_factory=lambda: {"L": False, "R": False})

    def feed(self, val: Json) -> None:
        left, right = live_typed(val, self.kind)  # Both typed before any mutation.
        self.valid = dict.fromkeys(("L", "R"), self.kind == "sxb")
        for side, raw in (("L", left), ("R", right)):
            out = self.state[side]
            if isinstance(raw, str):
                off_bed, seen_second = True, False
                for index, text in enumerate(raw.split("-")):
                    number = (
                        int(text, 0)
                        if text.strip().lower().startswith(("0x", "+0x", "-0x"))
                        else int(text)
                    )
                    if index == 0:
                        off_bed = number <= 0
                        out["on_bed"] = not off_bed
                    elif index == 1:
                        seen_second = True
                    elif index == 2:
                        out["heart"] = text
                    elif index == 3:
                        out["breath"] = text
                    elif index == 4:
                        self.valid[side] = number > 0
                    elif index == 5:
                        out["body_move"] = number > 0
                    elif index == 7:
                        out["snoring"] = number > 0
                if not self.valid[side]:
                    out.update(dict.fromkeys(DISPLAY_FIELDS, "--"))
                if off_bed or not seen_second:
                    out["heart"] = out["breath"] = "--"
            elif raw and raw[0] == 0:
                status = raw[1]  # Before body clear; errors retain earlier mutations.
                out["body_move"] = "--"
                if status in (1, -4):
                    out["on_bed"] = True
                    out["heart"] = str(raw[2])
                    out["breath"] = str(raw[3])
                    out["snoring"] = True if raw[4] == 1 else "--"
                elif status == 0:
                    out["on_bed"] = out["heart"] = out["breath"] = "--"
                elif status in (-2, -3):
                    out["body_move"] = True
