"""Portable command/formula literals from accepted row094, not hardware captures.

Report pin d47425720850f2b0d44f77c4bca0c4f7d0bdd28ed891c13483d2665f44192c32.
All126 original vector IDs, inputs and bytes retained. Four out-of-scope
history/diagnostic writes remain evidence only and are never bed controls.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Literal, TypedDict

from custom_components.adjustable_bed.codec import smart_sleep as codec


class Vector(TypedDict):
    id: str
    protocol: Literal["P1", "P2"]
    action: str
    inputs: dict
    expected_bytes: str


VECTORS: list[Vector] = json.loads(
    (Path(__file__).parent / "fixtures/smart_sleep_vectors.json").read_text()
)
EXCLUDED = frozenset({"V007", "V008", "V009", "V010"})
PRESET_NAMES = {
    "flatPosition": "flat",
    "memory6_M2": "memory_2",
    "memory5_M1": "memory_1",
    "openAIZero": "ai_zero",
    "antiSnore": "anti_snore",
    "zeroGravity": "zero_g",
    "memory3_TV": "tv",
    "memory2_Read": "read",
    "memory_tv": "tv",
    "memory_read": "read",
    "saveMemory6_M2": "memory_2",
    "saveMemory5_M1": "memory_1",
    "saveAntiSnore": "anti_snore",
    "saveZeroGravity": "zero_g",
    "saveTv": "tv",
    "saveRead": "read",
}
MASSAGE_NAMES = {
    "massageAll": "massage_all",
    "massageStopAll": "massage_off",
    "waveAdd": "wave",
    "timerSwitch": "timer",
    "footStrengthAdd": "foot_strength",
    "headStrengthAdd": "head_strength",
}


def encode(row: Vector) -> bytes:
    fmt: codec.Format = "p1" if row["protocol"] == "P1" else "p2"
    action, args = row["action"], row["inputs"]
    if args:
        if action.startswith("motor "):
            return codec.motion(fmt, args["axis"], args["direction"] == "up")
        if action in ("head strength", "foot strength", "timer"):
            return codec.massage(fmt, action.replace(" ", "_"), args["index"])
        if action == "wave cycle":
            return codec.wave_cycle(args["current_index"])
        if action in ("set alarm", "alarm UI ordinal"):
            wire = (
                [1, 9, 5, 6, 8][args["mode_index"]]
                if fmt == "p1"
                else args.get("ui_ordinal", args.get("action"))
            )
            return codec.alarm(
                fmt,
                enabled=True,
                week=args["week"],
                action=wire,
                hour=args["hour"],
                minute=args["minute"],
                flexible=bool(args.get("flexible_wake", 0)),
            )
        if action == "disable alarm":
            return codec.alarm(
                fmt,
                enabled=False,
                week=0,
                action=0,
                hour=0,
                minute=0,
                flexible=bool(args["flexible_wake"]),
            )
        if action == "set antisnore":
            return codec.antisnore(args["enabled"], args["value"])
        if action == "set sensitivity":
            return codec.sensitivity(args["level"])
        if action == "set clock":
            return codec.clock(fmt, datetime.fromisoformat(args["local_datetime"]))
        raise AssertionError(action)
    match = re.search(r"_ (\w+)\(", action)
    method = match[1] if match else action
    if method in PRESET_NAMES:
        return codec.preset(fmt, PRESET_NAMES[method], save=method.startswith("save"))
    if method in MASSAGE_NAMES:
        return codec.massage(fmt, MASSAGE_NAMES[method])
    motor = re.fullmatch(r"(head|foot|machinery[345])(Up|Down)", method)
    if motor:
        axis = {"head": 1, "foot": 2, "machinery3": 3, "machinery4": 4, "machinery5": 5}[motor[1]]
        return codec.motion(fmt, axis, motor[2] == "Up")
    if method in ("stopCommand", "stopDriver"):
        return codec.stop(fmt, motor=method == "stopDriver")
    if method == "connectResult":
        return codec.INITIALIZE
    if method in ("checkAlarm", "checkState", "checkMassage"):
        return codec.query(
            fmt,
            {"checkAlarm": "alarm", "checkState": "settings", "checkMassage": "massage"}[method],
        )
    if method in ("light", "openLight", "closeLight"):
        return codec.light(fmt, method != "closeLight")
    if method == "closeAlarm":
        return codec.alarm(fmt, enabled=False, week=0, action=0, hour=0, minute=0)
    if method == "setDemoAntiSnoring":
        return codec.antisnore(True, 6, demo=True)
    if method in ("openPrivacyMode", "closePrivacyMode"):
        return codec.privacy(method == "openPrivacyMode")
    raise AssertionError(method)


# Interior catalog members absent from the original boundary-only126 vectors.
# Accepted finite catalogs, frozen independently of the encoder.
CATALOG_VECTORS = (
    ("wave", 1, "aa000002010142"),
    ("wave", 2, "aa000002010143"),
    ("wave", 3, "aa000002010144"),
    ("wave", 4, "aa000002010145"),
    ("head_strength", 1, "aa000002010150"),
    ("head_strength", 2, "aa000002010151"),
    ("head_strength", 3, "aa000002010152"),
    ("head_strength", 4, "aa000002010153"),
    ("foot_strength", 1, "aa000002010154"),
    ("foot_strength", 2, "aa000002010155"),
    ("foot_strength", 3, "aa000002010156"),
    ("foot_strength", 4, "aa000002010157"),
    ("timer", 1, "aa000002010149"),
    ("timer", 2, "aa00000201014a"),
    ("timer", 3, "aa00000201014b"),
)
