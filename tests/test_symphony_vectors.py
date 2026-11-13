"""All row133 literal constructions, including operation-specific size fields.

Symphony Sleep Sense 2.8.0 (194), accepted static report and audit002. Hardware
unverified. Excluded analytics literals establish encoding only, not an API.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from custom_components.adjustable_bed.codec import keeson, okin_nframe, okin_soundwave
from custom_components.adjustable_bed.profiles import symphony as app

LITERALS = json.loads((Path(__file__).parent / "fixtures/symphony/literals.json").read_text())


@pytest.mark.parametrize("vector", LITERALS, ids=lambda row: row["id"])
def test_frozen_literal_codec_fit(vector):
    module, builder = vector["builder"].split(".")
    codec = {"keeson": keeson, "okin_nframe": okin_nframe, "okin_soundwave": okin_soundwave}[module]
    inputs = vector["inputs"].copy()
    if builder == "checked":
        inputs["body"] = bytes.fromhex(inputs["body"])
    assert getattr(codec, builder)(**inputs).hex() == vector["expected"]


FRAMES = json.loads((Path(__file__).parent / "fixtures/symphony/frames.json").read_text())


@pytest.mark.parametrize("vector", FRAMES, ids=lambda row: row["id"])
def test_frozen_parameter_boundaries(vector):
    action, fields, wire = vector["action"], vector["inputs"], vector["protocol"]
    selector = {"P1": 4, "P2": 9, "P3": 3}[wire]
    if action in ("headUp", "headDown", "stop"):
        actual = app.encode_word(wire, {"headUp": 1, "headDown": 2, "stop": 0}[action])
    elif action.startswith("headUp_selector"):
        profile = app.SymphonyProfile(app.PRODUCTS["15" if wire == "P1" else "10"], selector)
        actual = app.movement(profile, "head", True, fields["selector"])
    elif action == "machinery5Up":
        actual = app.movement(
            app.SymphonyProfile(app.PRODUCTS["13"], selector), "elevation", True, 1
        )
    elif action.startswith("stop"):
        frames = app.stops(app.SymphonyProfile(app.PRODUCTS["0"], selector), 1)[1]
        actual = frames[0 if action == "stopDriver" else 1]
    elif action == "confirmation_query":
        actual = okin_soundwave.query(5, (1, 255, 255, 0, 0, 34, 37, 18, 75))
    elif action == "light":
        actual = app.light(**fields)
    elif action == "massageTimer":
        actual = app.sonic_timer(**fields)
    elif action == "massageStrength":
        actual = app.sonic_strength(**fields)
    elif action == "openAlarm":
        actual = app.soundwave_alarm(**fields)
    elif action.startswith("antiSnore"):
        actual = okin_soundwave.record(
            7, 1, (fields["enable"], 2, fields["strength"], fields["selector"], 0, 0, 0, 0)
        )
    elif action.startswith("setAlarm"):
        mode = {"m1": "memory_1", "m2": "memory_2", "zg": "zero_g", "vibration": "massage"}.get(
            fields["mode"], fields["mode"]
        )
        product = "15" if "cached" in action else "10" if "side" in action else "0"
        profile = app.SymphonyProfile(app.PRODUCTS[product], fields.get("protocol", selector))
        actual = app.alarm(
            profile,
            enabled=True,
            hour=fields["hour"],
            minute=fields["minute"],
            week=fields["week"],
            mode=mode,
            side=fields.get("side", 1),
            cache=bytes.fromhex(fields["cache"]) if "cache" in fields else None,
        )
    elif action == "calendar":
        year, month, day, _weekday, hour, minute, second = fields["parts"]
        actual = app.clock(fields["selector"], datetime(year, month, day, hour, minute, second))
    elif action == "snore":
        args = fields["args"].copy()
        version, model = args.pop("version"), args.pop("model")
        actual = app.anti_snore(
            app.SymphonyProfile(app.PRODUCTS[str(model)], 9 if version == 2 else 3),
            enabled=True,
            **args,
        )
    elif action.startswith("light_cache"):
        actual = app.light(
            fields.get("cached_color", fields["new"]),
            fields.get("cached_brightness", fields["new"]),
        )
    elif action.startswith("privacy"):
        actual = (
            okin_soundwave.record(7, 2, (int(fields["enabled"]),))
            if fields["selector"] == 9
            else okin_nframe.parameter_record(0xB2, (int(fields["enabled"]),))
        )
    else:
        assert action.startswith("close_split")
        actual = app.alarm(
            app.SymphonyProfile(app.PRODUCTS["15"], 4),
            enabled=False,
            hour=0,
            minute=0,
            week=0,
            mode="memory_1",
            side=fields["side"],
            cache=bytes.fromhex(fields["cache"]),
        )
    assert actual == bytes.fromhex(vector["expected_bytes"])
