"""This package's sleep JSON field contracts, indexed by shipped constructor RVA."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast


@dataclass(frozen=True, slots=True)
class Field:
    key: str
    cast: str
    nested: str | None = None
    array: bool = False


SCHEMAS: dict[str, tuple[Field, ...]] = {
    "0x6dfdf0": (
        Field("id", "num", None, False),
        Field("cmd", "String", None, False),
        Field("val", "dynamic", None, False),
    ),
    "0x6dfa38": (
        Field("id", "num?", None, False),
        Field("cmd", "String?", None, False),
        Field("val", "Map<String, dynamic>", "0x6dfcf4", False),
    ),
    "0x6dfcf4": (
        Field("L", "String", None, False),
        Field("R", "String", None, False),
    ),
    "0x6df760": (
        Field("id", "num?", None, False),
        Field("cmd", "String?", None, False),
        Field("val", "Map<String, dynamic>", "0x6df96c", False),
    ),
    "0x6df96c": (Field("fsize", "num?", None, False),),
    "0x6e0bf0": (
        Field("awake", "Map<String, dynamic>", "0x6e2a64", False),
        Field("body_move", "List?", "0x6e36dc", True),
        Field("body_revolve", "List?", "0x6e34d4", True),
        Field("breath", "Map<String, dynamic>", "0x6e26f4", False),
        Field("breath_avg", "num?", None, False),
        Field("day", "String?", None, False),
        Field("deep", "Map<String, dynamic>", "0x6e257c", False),
        Field("go_to_bed_time", "num?", None, False),
        Field("heart_beat", "Map<String, dynamic>", "0x6e220c", False),
        Field("heart_beat_avg", "num?", None, False),
        Field("light", "Map<String, dynamic>", "0x6e2094", False),
        Field("rem", "Map<String, dynamic>", "0x6e1f1c", False),
        Field("report_state", "String?", None, False),
        Field("score", "num?", None, False),
        Field("sleep_data", "List?", "0x6e322c", True),
        Field("snore", "List?", "0x6e2f50", True),
        Field("snore_count", "List?", "0x6e2f50", True),
        Field("sporadicsleep", "List?", "0x6e2cf8", True),
        Field("time_start", "num?", None, False),
        Field("time_end", "num?", None, False),
        Field("wake_up_time", "num?", None, False),
    ),
    "0x6e1f1c": (
        Field("percentage", "num?", None, False),
        Field("value", "num?", None, False),
    ),
    "0x6e2094": (
        Field("percentage", "num?", None, False),
        Field("value", "num?", None, False),
    ),
    "0x6e220c": (
        Field("num", "List?", None, False),
        Field("time", "List?", None, False),
    ),
    "0x6e257c": (
        Field("percentage", "num?", None, False),
        Field("value", "num?", None, False),
    ),
    "0x6e26f4": (
        Field("num", "List?", None, False),
        Field("time", "List?", None, False),
    ),
    "0x6e2a64": (
        Field("percentage", "num?", None, False),
        Field("value", "num?", None, False),
    ),
    "0x6e2cf8": (
        Field("start", "num?", None, False),
        Field("end", "num?", None, False),
        Field("minute", "num?", None, False),
    ),
    "0x6e2f50": (
        Field("time", "num?", None, False),
        Field("value", "num?", None, False),
    ),
    "0x6e322c": (
        Field("start", "num?", None, False),
        Field("end", "num?", None, False),
        Field("status", "num?", None, False),
    ),
    "0x6e34d4": (
        Field("time", "num?", None, False),
        Field("value", "num?", None, False),
    ),
    "0x6e36dc": (
        Field("time", "num?", None, False),
        Field("value", "num?", None, False),
    ),
    "0x6e3860": (
        Field("day", "String?", None, False),
        Field("score", "num?", None, False),
        Field("go_to_bed_time", "num?", None, False),
        Field("time_start", "num?", None, False),
        Field("wake_up_time", "num?", None, False),
        Field("time_end", "num?", None, False),
        Field("awake", "Map<String, dynamic>", "0x6e2a64", False),
        Field("deep", "Map<String, dynamic>", "0x6e257c", False),
        Field("light", "Map<String, dynamic>", "0x6e2094", False),
        Field("rem", "Map<String, dynamic>", "0x6e1f1c", False),
        Field("heart_beat_avg", "num?", None, False),
        Field("breath_avg", "num?", None, False),
        Field("body_move_size", "num?", None, False),
        Field("body_revolve_size", "num?", None, False),
        Field("snore_size", "num?", None, False),
        Field("snore_count_size", "num?", None, False),
        Field("report_state", "String?", None, False),
    ),
    "0x6dff88": (
        Field("id", "num", None, False),
        Field("cmd", "String", None, False),
        Field("val", "Map<String, dynamic>", "0x6e0220", False),
    ),
    "0x6e0220": (
        Field("error", "num", None, False),
        Field("ver", "String", None, False),
    ),
    "0x6d6204": (
        Field("L", "List<num>?", None, False),
        Field("R", "List<num>?", None, False),
    ),
    "0x6d600c": (
        Field("id", "int?", None, False),
        Field("cmd", "String?", None, False),
        Field("val", "dynamic", "0x6d6204", False),
    ),
    "0x6db1f8": (
        Field("value", "num?", None, False),
        Field("percentage", "num?", None, False),
    ),
    "0x6db070": (
        Field("value", "num?", None, False),
        Field("percentage", "num?", None, False),
    ),
    "0x6daee8": (
        Field("value", "num?", None, False),
        Field("percentage", "num?", None, False),
    ),
    "0x6dada8": (
        Field("value", "num?", None, False),
        Field("percentage", "num?", None, False),
    ),
    "0x6dac20": (
        Field("value", "num?", None, False),
        Field("percentage", "num?", None, False),
    ),
    "0x6daa98": (
        Field("value", "num?", None, False),
        Field("percentage", "num?", None, False),
    ),
    "0x6db7c8": (
        Field("start", "num?", None, False),
        Field("end", "num?", None, False),
        Field("status", "num?", None, False),
    ),
    "0x6db464": (
        Field("session_id", "num?", None, False),
        Field("time_start", "num?", None, False),
        Field("time_end", "num?", None, False),
        Field("stage", "dynamic", "0x6db7c8", True),
    ),
    "0x6d9e6c": (
        Field("start", "List<num>?", None, False),
        Field("end", "List<num>?", None, False),
        Field("minute", "List<num>?", None, False),
    ),
    "0x6d8c0c": (
        Field("algorithmVersion", "String?", None, False),
        Field("day", "String?", None, False),
        Field("everFellAsleep", "num?", None, False),
        Field("score", "num?", None, False),
        Field("go_to_bed_time", "num?", None, False),
        Field("time_start", "num?", None, False),
        Field("wake_up_time", "num?", None, False),
        Field("time_end", "num?", None, False),
        Field("sleep_onset_latency", "num?", None, False),
        Field("sleep_duration", "num?", None, False),
        Field("sleepEfficiency", "num?", None, False),
        Field("awake", "dynamic", "0x6db1f8", False),
        Field("deep", "dynamic", "0x6db070", False),
        Field("light", "dynamic", "0x6daee8", False),
        Field("rem", "dynamic", "0x6dada8", False),
        Field("outbed", "dynamic", "0x6dac20", False),
        Field("micro_awake", "dynamic", "0x6daa98", False),
        Field("out_of_bed_count", "num?", None, False),
        Field("sleep_data", "dynamic", "0x6db464", True),
        Field("sleep_duration_whole", "num?", None, False),
        Field("body_move", "dynamic", "0x6da7ac", False),
        Field("snore", "dynamic", "0x6da508", False),
        Field("heart_beat_avg", "num?", None, False),
        Field("heart_beat", "dynamic", "0x6da2e8", False),
        Field("breath_avg", "num?", None, False),
        Field("breath", "dynamic", "0x6da110", False),
        Field("sporadicsleep", "dynamic", "0x6d9e6c", False),
        Field("report_state", "String?", None, False),
        Field("situp_time_arr", "List<num>?", None, False),
        Field("calib_time_arr", "List<num>?", None, False),
    ),
    "0x6d7d38": (
        Field("ts", "num?", None, False),
        Field("utc", "String?", None, False),
    ),
    "0x6d79f8": (
        Field("id", "num?", None, False),
        Field("cmd", "String?", None, False),
        Field("val", "dynamic", "0x6d7d38", False),
    ),
    "0x6d6e84": (
        Field("error", "int?", None, False),
        Field("ver", "String?", None, False),
        Field("type", "String?", None, False),
    ),
    "0x6d6cd4": (
        Field("id", "int?", None, False),
        Field("cmd", "String?", None, False),
        Field("val", "Map<String, dynamic>", "0x6d6e84", False),
    ),
    "0x6d6a5c": (
        Field("rdy", "int?", None, False),
        Field("cont", "int?", None, False),
        Field("suc", "int?", None, False),
    ),
    "0x6d68ac": (
        Field("id", "int?", None, False),
        Field("cmd", "String?", None, False),
        Field("val", "Map<String, dynamic>", "0x6d6a5c", False),
    ),
    "0x6d7858": (
        Field("id", "num", None, False),
        Field("cmd", "String", None, False),
        Field("val", "dynamic", None, False),
    ),
    "0x6d7674": (
        Field("L", "List<num>?", None, False),
        Field("R", "List<num>?", None, False),
    ),
    "0x6d747c": (
        Field("id", "num?", None, False),
        Field("cmd", "String?", None, False),
        Field("val", "dynamic", "0x6d7674", False),
    ),
    "0x6d7108": (
        Field("id", "num?", None, False),
        Field("cmd", "String?", None, False),
        Field("val", "Map<String, dynamic>", "0x6d73b0", False),
    ),
    "0x6d73b0": (Field("fsize", "num?", None, False),),
    "0x6ddcd8": (
        Field("start", "num?", None, False),
        Field("end", "num?", None, False),
        Field("status", "num?", None, False),
    ),
    "0x6da7ac": (
        Field("time", "List<num>?", None, False),
        Field("value", "List<num>?", None, False),
        Field("dur", "List<num>?", None, False),
    ),
    "0x6da508": (
        Field("time", "List<num>?", None, False),
        Field("value", "List<num>?", None, False),
        Field("dur", "List<num>?", None, False),
    ),
    "0x6da2e8": (
        Field("time", "List<num>?", None, False),
        Field("num", "List<num>?", None, False),
    ),
    "0x6da110": (
        Field("time", "List<num>?", None, False),
        Field("num", "List<num>?", None, False),
    ),
    "0x6dcfd8": (
        Field("start", "List<num>?", None, False),
        Field("end", "List<num>?", None, False),
        Field("minute", "List<num>?", None, False),
    ),
    "0x6dc034": (
        Field("algorithmVersion", "String?", None, False),
        Field("day", "String?", None, False),
        Field("everFellAsleep", "num?", None, False),
        Field("score", "num?", None, False),
        Field("go_to_bed_time", "num?", None, False),
        Field("time_start", "num?", None, False),
        Field("wake_up_time", "num?", None, False),
        Field("time_end", "num?", None, False),
        Field("sleep_onset_latency", "num?", None, False),
        Field("sleep_duration", "num?", None, False),
        Field("sleepEfficiency", "num?", None, False),
        Field("awake", "dynamic", "0x6dda6c", False),
        Field("deep", "dynamic", "0x6dd8e4", False),
        Field("light", "dynamic", "0x6dd75c", False),
        Field("rem", "dynamic", "0x6dd5d4", False),
        Field("outbed", "dynamic", "0x6dd44c", False),
        Field("micro_awake", "dynamic", "0x6dd2c4", False),
        Field("sleep_data", "dynamic", "0x6ddcd8", True),
        Field("body_move", "dynamic", "0x6da7ac", False),
        Field("snore", "dynamic", "0x6da508", False),
        Field("heart_beat_avg", "num?", None, False),
        Field("heart_beat", "dynamic", "0x6da2e8", False),
        Field("breath_avg", "num?", None, False),
        Field("breath", "dynamic", "0x6da110", False),
        Field("sporadicsleep", "dynamic", "0x6dcfd8", False),
        Field("report_state", "String?", None, False),
    ),
    "0x6dda6c": (
        Field("value", "num?", None, False),
        Field("percentage", "num?", None, False),
    ),
    "0x6dd8e4": (
        Field("value", "num?", None, False),
        Field("percentage", "num?", None, False),
    ),
    "0x6dd75c": (
        Field("value", "num?", None, False),
        Field("percentage", "num?", None, False),
    ),
    "0x6dd5d4": (
        Field("value", "num?", None, False),
        Field("percentage", "num?", None, False),
    ),
    "0x6dd44c": (
        Field("value", "num?", None, False),
        Field("percentage", "num?", None, False),
    ),
    "0x6dd2c4": (
        Field("value", "num?", None, False),
        Field("percentage", "num?", None, False),
    ),
    "0x6ddeb0": (
        Field("algorithmVersion", "String?", None, False),
        Field("day", "String?", None, False),
        Field("everFellAsleep", "num?", None, False),
        Field("score", "num?", None, False),
        Field("go_to_bed_time", "num?", None, False),
        Field("time_start", "num?", None, False),
        Field("wake_up_time", "num?", None, False),
        Field("time_end", "num?", None, False),
        Field("sleep_onset_latency", "num?", None, False),
        Field("sleep_duration", "num?", None, False),
        Field("sleepEfficiency", "num?", None, False),
        Field("awake", "dynamic", "0x6dda6c", False),
        Field("deep", "dynamic", "0x6dd8e4", False),
        Field("light", "dynamic", "0x6dd75c", False),
        Field("rem", "dynamic", "0x6dd5d4", False),
        Field("outbed", "dynamic", "0x6dd44c", False),
        Field("micro_awake", "dynamic", "0x6dd2c4", False),
        Field("body_move_size", "num?", None, False),
        Field("snore_size", "num?", None, False),
        Field("body_move_count", "num?", None, False),
        Field("snore_duration", "num?", None, False),
        Field("sleep_duration_whole", "num?", None, False),
        Field("heart_beat_avg", "num?", None, False),
        Field("breath_avg", "num?", None, False),
        Field("report_state", "String?", None, False),
    ),
    "0x6d668c": (
        Field("L", "List<num>?", None, False),
        Field("R", "List<num>?", None, False),
    ),
    "0x6d6494": (
        Field("id", "int?", None, False),
        Field("cmd", "String?", None, False),
        Field("val", "dynamic", "0x6d668c", False),
    ),
    "0x6d7e84": (
        Field("id", "num?", None, False),
        Field("cmd", "String?", None, False),
        Field("val", "Map<String, dynamic>", "0x6d8154", False),
    ),
    "0x6d8154": (
        Field("error", "num?", None, False),
        Field("ver", "String?", None, False),
        Field("type", "String?", None, False),
    ),
    "0x6ecce8": (
        Field("firewareUrl", "String?", None, False),
        Field("firewareVersion", "String?", None, False),
        Field("type", "String?", None, False),
        Field("isLatest", "bool?", None, False),
    ),
}


def parse_schema(address: str, value: object) -> dict[str, object]:
    """Validate before publishing; preserve the shipped key and nested-field names."""
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise ValueError("Sleep JSON requires a string-keyed object")
    result: dict[str, object] = {}
    for field in SCHEMAS[address]:
        item = value.get(field.key)
        kind = field.cast.removesuffix("?")
        if item is None:
            if kind != "dynamic" and not field.cast.endswith("?"):
                raise ValueError(f"Missing required {field.key}")
            result[field.key] = None
            continue
        valid = True
        if kind in ("num", "int"):
            valid = type(item) in ((int, float) if kind == "num" else (int,))
        elif kind == "String":
            valid = isinstance(item, str)
        elif kind == "bool":
            valid = type(item) is bool
        elif kind.startswith("List") or field.array:
            valid = isinstance(item, list)
            if valid and kind == "List<num>":
                valid = all(type(v) in (int, float) for v in item)
        elif kind.startswith("Map"):
            valid = isinstance(item, dict)
        if not valid:
            raise ValueError(f"Invalid {field.key}: expected {field.cast}")
        if field.nested is not None:
            if field.array:
                item = [parse_schema(field.nested, v) for v in cast(list[object], item)]
            else:
                item = parse_schema(field.nested, item)
        result[field.key] = item
    return result
