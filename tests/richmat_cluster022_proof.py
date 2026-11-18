"""Standalone accepted-literal proof using production builders, without HA startup.

The fixtures are frozen app evidence. Parser scenarios and the raw LONG-worker
defect are counted separately. Nisco's current UI attachment for that worker is
not established; MLILY explicitly has no attached current RvText longCode.
Run this only within the coordinator's explicitly granted validation lane.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from types import ModuleType


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    # Avoid integration __init__ and HA setup; execute the actual production
    # modules with their normal relative imports and constants intact.
    for name in (
        "custom_components", "custom_components.adjustable_bed",
        "custom_components.adjustable_bed.codec", "custom_components.adjustable_bed.profiles",
        "custom_components.adjustable_bed.beds",
        "custom_components.adjustable_bed.beds.richmat_mh",
        "custom_components.adjustable_bed.beds.ruf_richmat",
    ):
        package = ModuleType(name)
        package.__path__ = [str(root.joinpath(*name.split(".")))]
        sys.modules[name] = package

    from custom_components.adjustable_bed.beds.richmat_mh import protocol as mh
    from custom_components.adjustable_bed.beds.ruf_richmat.protocol import sleep_frame
    from custom_components.adjustable_bed.codec import richmat as codec

    for app in ("nisco", "mlily_supreme"):
        counts: Counter[str] = Counter()
        rows = json.loads((root / "tests/fixtures/richmat_cluster022" / f"{app}_vectors.json").read_text())
        for row in rows:
            builder, values = row["builder"], row["inputs"]
            if builder.startswith("parse_"):
                counts["parser_separate"] += 1
                continue
            if builder == "queue_long_at_threshold":
                counts["raw_worker_separate"] += 1
                continue
            if app == "nisco":
                match builder:
                    case "normal":
                        actual = codec.command(values["opcode"], values["mode"])
                    case "motor_angle":
                        actual = mh.angle_frame(values["axis"], values["angle"])
                    case "massage":
                        actual = mh.massage_intensity_frame(values["head"], values["foot"])
                    case "fa":
                        actual = sleep_frame(values["message"], bytes(values["content"]))
                    case "color":
                        actual = codec.rgb(*values["rgb"])
                    case "summed":
                        actual = codec.frame(*values["prefix"])
                    case "snore":
                        actual = mh.snore_frame(values["opcode"], values["tx_mode"])
                    case _:
                        raise AssertionError((app, row["id"], builder))
            else:
                args = values["args"]
                match builder:
                    case "remote":
                        actual = codec.command(*args)
                    case "bed_alarm":
                        actual = mh.alarm_frames(*args)
                    case "summed":
                        actual = codec.frame(*args[0])
                    case "motor_angle":
                        actual = mh.angle_frame(*args)
                    case "motor_mode":
                        actual = mh.motor_mode_frame(*args)
                    case "massage":
                        actual = mh.massage_intensity_frame(*args)
                    case "led_rgb":
                        actual = codec.rgb(*args)
                    case "led_timeout":
                        actual = mh.light_timer_frame(*args)
                    case "mattress":
                        actual = mh.mattress_frame(*args)
                    case "mattress_alarm":
                        actual = mh.mattress_frame(args[0], 0x0B, *args[1:])
                    case "waist_alarm":
                        actual = mh.waist_alarm_frame(args[1], args[0], *args[2:])
                    case "p2":
                        actual = sleep_frame(args[0], bytes(args[1]))
                    case "p2_time":
                        actual = sleep_frame(5, bytes.fromhex(f"{args[0]:x}")[::-1])
                    case "snore":
                        actual = mh.snore_frame(*args)
                    case _:
                        raise AssertionError((app, row["id"], builder))
            observed = " | ".join(frame.hex() for frame in actual) if isinstance(actual, tuple) else actual.hex()
            assert observed == row["expected_bytes"], (app, row["id"], observed, row["expected_bytes"])
            counts["outbound_pass"] += 1
        print(app, dict(counts))


if __name__ == "__main__":
    main()
