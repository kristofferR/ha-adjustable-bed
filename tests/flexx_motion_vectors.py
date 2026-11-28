"""Independent frozen Flexx Motion vectors, with no report dependency at test time."""

import gzip
import json
from datetime import datetime
from pathlib import Path

from custom_components.adjustable_bed.codec import richmat as c

FULL = json.loads(
    gzip.decompress((Path(__file__).parent / "fixtures/flexx_motion/full.json.gz").read_bytes())
)
C = FULL["controls"]


def encode(r):
    i = r["inputs"]
    kind = i.get("builder", r.get("kind"))
    n = r["source_id"]
    if kind == "function":
        t = C[i["template"]]
        code = (t["long_opcode"] or 0) if i["press"] == "long" else t["effective_short_opcode"]
        return c.function(code, i["side"], single=i["nordic"])
    if kind == "startup":
        return c.function(
            0 if i["kind"] == "exit_limit" else 1,
            single=i["nordic"],
            action={
                "exit_limit": "deviceFunctionItemExitLimit",
                "clock": "deviceFunctionItemCheckClock",
                "light": "deviceFunctionItemCheckLight",
                "music": "deviceFunctionItemCheckMusic",
            }[i["kind"]],
        )
    if "opcode" in i and n.startswith("stop-"):
        return c.function(i["opcode"], i.get("side", 0), single=i.get("nordic", False))
    if kind == "box":
        return (
            c.record_20_len(11, 2, 0, (0,))
            if i["mode"] is None
            else c.record_20_len(11, 2, 1, (0, i["mode"]))
        )
    if kind == "clock_sync":
        seconds = i["microseconds"] // 1000000
        return c.record_20_len(
            8, 2, 1, (*seconds.to_bytes(4, "big"), int(i["offset_microseconds"] / 3600000000))
        ) + c.calendar(datetime(*i["calendar"]), build=c.record_20_len)
    if kind == "timer":
        return (
            c.light_timer(255, 255)
            if not i["seconds"]
            else c.light_timer(i["seconds"] >> 8, i["seconds"])
        )
    if kind == "clock":
        return b"".join(c.countdown(i["minutes"], i["opcode"]))
    if kind == "repeat_add":
        return c.record_20_len(
            5, 1, 1, (i["number"], 0, i["hour"], i["minute"], i["opcode"], i["mask"])
        )
    if kind == "repeat_delete":
        return c.record_20_len(5, 2, 1, (i["number"],))
    if kind == "color":
        return c.rgb(*i["components"])
    if "RGB" in i:
        return c.rgb(*i["RGB"])
    fixed = {
        "repeat-list": lambda: c.record_20_len(5, 1, 0, (0,)),
        "repeat-delete-slot1": lambda: c.record_20_len(5, 2, 1, (1,)),
        "repeat-add-1-0630-mode1-weekdays-enabled": lambda: c.record_20_len(
            5, 1, 1, (1, 0, 6, 30, 1, 249)
        ),
        "box-control-query": lambda: c.record_20_len(11, 2, 0, (0,)),
        "box-control-set-mode2": lambda: c.record_20_len(11, 2, 1, (0, 2)),
        "countdown-300-mode1": lambda: b"".join(c.countdown(300, 1)),
        "countdown-cancel": lambda: b"".join(c.countdown(0, 0)),
        "light-timer-60": lambda: c.light_timer(0, 60),
        "light-timer-zero": lambda: c.light_timer(255, 255),
        "light-rgb-12-34-56": lambda: c.rgb(18, 52, 86),
        "clock-sync-calendar-and-epoch": lambda: b"".join(
            c.time_sync(datetime.fromisoformat(i["now"]), build=c.record_20_len, first_hex=True)
        ),
    }
    return fixed[n]()
