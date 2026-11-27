"""Independent mapping of the BERUN report's literals onto existing codecs.

Unused helpers are encoded only here, never exposed as controller actions.
"""

from datetime import datetime

from custom_components.adjustable_bed.codec import keeson, okin_nframe, okin_ore

WORDS = {
    "HeadUp": 1,
    "HeadDown": 2,
    "Stop": 0,
    "FootUp": 4,
    "FootDown": 8,
    "HeadFootUp": 5,
    "HeadFootDown": 10,
    "NeckUp": 16,
    "NeckDown": 32,
    "WaistUp": 64,
    "WaistDown": 128,
    "Flat": 0x08000000,
    "MemoryZero": 0x1000,
    "MemoryPosition": 0x10000,
    "MemoryTv": 0x4000,
    "MemoryLounge": 0x2000,
    "MemoryAntiSnore": 0x8000,
    "Light": 0x20000,
    "MassageAll": 0x100,
    "MassageTime": 0x200,
    "MassageHeadPlus": 0x800,
    "MassageHeadMinus": 0x800000,
    "MassageFootPlus": 0x400,
    "MassageFootMinus": 0x1000000,
    "MassageWavePlus": 0x10000000,
    "MassageWaveMinus": 0x4000000,
}
OPCODES = {
    "HeadUp": 0x2001,
    "HeadDown": 0x2002,
    "Stop": 0x2000,
    "FootUp": 0x2003,
    "FootDown": 0x2004,
    "NeckUp": 0x2007,
    "NeckDown": 0x2008,
    "WaistUp": 0x2007,
    "WaistDown": 0x2008,
    "Flat": 0x2066,
    "MemoryZero": 0x2060,
    "MemoryPosition": 0x2064,
    "MemoryTv": 0x2062,
    "MemoryLounge": 0x2061,
    "MemoryAntiSnore": 0x2063,
    "Light": 0x2080,
    "MassageAll": 0x2081,
    "MassageHeadPlus": 0x2084,
    "MassageHeadMinus": 0x2021,
    "MassageFootPlus": 0x2085,
    "MassageFootMinus": 0x2031,
    "MassageWavePlus": 0x2070,
}


def encode(row):
    v = row["inputs"]["version"]
    action = row["action"]
    args = row["inputs"].get("arguments", [])
    now = datetime.fromisoformat(row["inputs"].get("clock", "2026-11-27T12:34:56+00:00"))
    if action in ("AlarmCalibration", "Dynamic calendar date boundary"):
        return (
            keeson.clock(now)
            if v < 8
            else okin_nframe.clock(
                (
                    now.year - 2000,
                    now.month,
                    now.day,
                    (now.weekday() + 1) % 7,
                    now.hour,
                    now.minute,
                    now.second,
                )
            )
        )
    if action == "AlarmClick":
        h, m, days, kind = args
        return (
            keeson.alarm_table(3, bytes(args))
            if v < 8
            else okin_nframe.alarm((days, kind, h, m, 0, int(bool(kind)), 0))
        )
    if action == "AlarmCheck":
        return keeson.ALARM_QUERY if v < 8 else okin_nframe.request(0xC0)
    if action == "MassageCheck":
        return keeson.frame(3, header=0xE6, side=0) if v < 8 else okin_nframe.request(0xB0)
    if v == 7:
        return okin_ore.frame(OPCODES[action])
    return (
        keeson.frame(WORDS[action], header=0xE6, side=0)
        if v == 6
        else okin_nframe.frame40(WORDS[action])
    )
