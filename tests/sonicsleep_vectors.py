"""Accepted SonicSleep literals exercised against the production Richmat codec."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from custom_components.adjustable_bed.codec import richmat as codec

VECTORS = json.loads((Path(__file__).parent / "fixtures/sonicsleep/vectors.json").read_text())
CODES = {
    "head_up": 0x24, "head_down": 0x25, "foot_up": 0x26, "foot_down": 0x27,
    "both_up": 0x29, "both_down": 0x2A, "flat": 0x31,
    "zero_gravity": 0x45, "lounge": 0x59, "tv": 0x58, "anti_snore": 0x46,
    "memory_1": 0x2E, "memory_2": 0x2F,
    "save_zero_gravity": 0x66, "save_lounge": 0x65, "save_tv": 0x64,
    "save_anti_snore": 0x69, "save_memory_1": 0x2B, "save_memory_2": 0x2C,
    "exit_limit": 0, "query_clock": 1,
}


def encode(row):
    """Only adapt fixture inputs; never execute the analyst's oracle."""
    if row["kind"] == "cached_toggle":
        received = bytes.fromhex(row["received"])
        return codec.record(5, 1, 1, (*received[6:11], received[11] & 254 | int(row["enabled"])))
    p = row["inputs"]
    action = p["action"]
    if row["kind"] == "function":
        enum = {"exit_limit": "deviceFunctionItemExitLimit", "query_clock": "deviceFunctionItemCheckClock"}.get(action, "")
        return codec.function(CODES[action], action=enum, single=p["route"] == "Nordic")
    if action == "list_alarms":
        return codec.record(5, 1, 0, (0,))
    if action == "query_link_name":
        return codec.record(6, 3, 0, (0,))
    if action == "delete_alarm":
        return codec.record(5, 2, 1, (p["id"],))
    if action == "upsert_alarm":
        mask = sum(1 << (7 - d) for d in p["weekdays"]) | int(p["enabled"])
        return codec.record(5, 1, 1, (p["id"], 0, p["hour"], p["minute"], CODES[p["mode"]], mask))
    if action == "sync_epoch":
        now = datetime.fromtimestamp(p["epoch_seconds"], timezone(timedelta(minutes=p["zone_minutes"])))
        return codec.time_sync(now)[0]
    if action == "sync_calendar":
        return codec.calendar(datetime(**{k: v for k, v in p.items() if k != "action"}))
    raise AssertionError(action)
