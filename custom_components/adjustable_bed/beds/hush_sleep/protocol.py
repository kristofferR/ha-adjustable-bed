"""Hush sleep JSON, report selection and direct configuration contracts."""

from __future__ import annotations

import json
import math
import zlib

from ...codec import sleep_envelope
from ..casper_base.protocol import Request, SensorKind
from ..casper_sleep.protocol import Json, Receive, command, envelope, mapping
from .schema import SCHEMAS


def integer(value: Json) -> int:
    if type(value) not in (int, float):
        raise ValueError("Expected numeric value")
    assert isinstance(value, (int, float))
    if not math.isfinite(value):
        raise ValueError("Nonfinite integer")
    return max(-(2**63), min(2**63 - 1, int(value)))


def parse(schema: str, value: Json) -> dict[str, Json]:
    """Validate source fields in order, without inventing physical units."""
    obj = mapping(value)
    out: dict[str, Json] = {}
    for key, typ, nullable, default, mode, conversion, nested, element in SCHEMAS[schema]:
        v: Json = obj.get(key)
        if v is None:
            if mode == "lazy_num_list":
                out[key] = []
            elif nullable:
                out[key] = default
            else:
                raise ValueError("Missing " + key)
            continue
        if mode == "bean":
            assert nested is not None
            v = parse(nested, v)
        elif mode in ("eager_bean_list", "eager_int_list", "lazy_num_list"):
            if not isinstance(v, list):
                raise ValueError("Expected list " + key)
            if mode == "eager_bean_list":
                assert element is not None
                v = [parse(element, x) for x in v]
            elif mode == "eager_int_list":
                v = [integer(x) for x in v]
            # Lazy numeric arrays remain raw until a consumer accesses them.
        elif typ.startswith("String") and not isinstance(v, str):
            raise ValueError("Expected string " + key)
        elif typ.startswith("int") and type(v) is not int:
            raise ValueError("Expected integer " + key)
        elif typ.startswith("num") and type(v) not in (int, float):
            raise ValueError("Expected number " + key)
        if conversion == "to_int":
            v = integer(v)
        elif conversion == "to_double":
            if type(v) not in (int, float):
                raise ValueError("Expected number " + key)
            assert isinstance(v, (int, float))
            v = float(v)
        out[key] = v
    return out


def new_day_layout(version: str) -> bool:
    try:
        parts = [int(x) for x in version.split(".")]
    except ValueError as err:
        raise ValueError("Invalid report algorithm version") from err
    if parts[0] == 1:
        return False
    reference = [0, 0, 3, 0]
    length = max(len(parts), len(reference))
    return parts + [0] * (length - len(parts)) >= reference + [0] * (length - 4)


def report(data: Json, *, kind: SensorKind, monthly: bool) -> Json:
    if monthly:
        if not isinstance(data, list):
            raise ValueError("Expected monthly report list")
        return [parse("0x7b1840" if kind == "mm" else "0x7abc50", x) for x in data]
    old = parse("0x7aedb0" if kind == "mm" else "0x7a7e3c", data)
    if kind == "mm":
        return old
    version = old["algorithmVersion"]
    if not isinstance(version, str):
        raise ValueError("Missing algorithm version")
    parsed = parse("0x7a4a14", data) if new_day_layout(version) else old
    return parsed if old["day"] is not None else None


def build(
    kind: SensorKind, action: str, sequence: int, request: Request, *, ts: int, zone: str | int
) -> bytes:
    if action in ("q_time", "q_sens", "q_antiSnore", "s_antiSnore"):
        if kind != "sxb":
            raise ValueError("SXB command required")
        val: Json = None
        if action == "s_antiSnore":
            val = {"L": [int(request.enabled), 8, 4], "R": [int(request.enabled), 8, 4]}
        return envelope({"id": sequence, "cmd": action, "val": val}, sequence)
    return command(kind, action, sequence, request, ts=ts, zone=zone)


class HushReceive(Receive):
    """Retain normal framing; accept both proven compression wrappers."""

    def feed(self, chunk: bytes) -> Json:
        if self.action != "q_report_allow":
            return super().feed(chunk)
        if not chunk:
            self.pending.clear()
            return None
        if self.kind == "sxb":
            if len(chunk) < sleep_envelope.HEADER_SIZE:
                raise ValueError("Truncated SXB report fragment")
            chunk = chunk[sleep_envelope.HEADER_SIZE :]
        self.pending.extend(chunk)
        if len(self.pending) < self.report_size:
            return None
        payload = bytes(self.pending)
        self.pending.clear()
        decoder = zlib.decompressobj(47)
        try:
            decoded = decoder.decompress(payload, 4 * 1024 * 1024 + 1)
        except zlib.error as err:
            raise ValueError("Invalid compressed report") from err
        if len(decoded) > 4 * 1024 * 1024 or not decoder.eof:
            raise ValueError("Invalid or oversized report")
        return json.loads(decoded.decode("latin1"))
