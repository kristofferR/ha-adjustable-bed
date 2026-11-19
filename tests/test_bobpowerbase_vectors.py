"""Power Bob Base 1.0.9 frozen literals against production Richmat builders.

Parser inputs are synthetic artifact cases, not hardware captures. Excluded
builders remain proof fixtures and do not enable their product features.
"""

import json
from pathlib import Path
from typing import cast

import pytest

from custom_components.adjustable_bed.beds.goodvibe import protocol as p
from custom_components.adjustable_bed.beds.goodvibe.receive import common, extended
from custom_components.adjustable_bed.beds.richmat_app.protocol import repeat_mask
from custom_components.adjustable_bed.codec import richmat as codec

VECTORS = json.loads(
    (Path(__file__).parent / "fixtures/bobpowerbase/vectors.json").read_text()
)
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "once")


def test_frozen_gatt_and_common_literals():
    directory = Path(__file__).parent / "fixtures/bobpowerbase"
    for row in json.loads((directory / "gatt.json").read_text()):
        route = next(t for t in codec.TRANSPORTS.values() if t.service_uuid == row["service"])
        assert (route.write_uuid, route.notify_uuid) == (row["write"], row["notify"])
    for row in json.loads((directory / "acks.json").read_text()):
        assert (row["event"], None) in common(list(bytes.fromhex(row["bytes"])))


@pytest.mark.parametrize("v", VECTORS, ids=lambda v: v["id"])
def test_frozen_literal(v):
    q, kind = v["inputs"], v["builder"]
    if kind == "clock":
        assert p.clock(q["minutes"], q["mode"]) == tuple(
            bytes.fromhex(part) for part in v["expected_bytes"].split(" / ")
        )
        return
    expected = bytes.fromhex(v["expected_bytes"])
    if kind == "command":
        actual = codec.function(q["code"], q["side"], single=q["nordic"], action=v["action"])
    elif kind == "query":
        actual = codec.function(q["prefix"][-1], action=v["action"])
    elif kind == "light_seconds":
        actual = p.light_duration(q["seconds"])
    elif kind == "light_rgb":
        actual = codec.rgb(q["red"], q["green"], q["blue"])
    elif kind == "extra":
        actual = codec.record_20_len(q["group"], q["sub"], q["operation"], q["payload"])
    elif kind == "repeat_code":
        actual = bytes((repeat_mask(tuple(DAYS.index(day) for day in q["days"]), q["enabled"]),))
    elif kind == "crc16":
        assert codec.is_valid_crc(bytes.fromhex(q["hex"]) + expected)
        return
    elif kind == "parse_common_motor":
        assert dict(common(list(expected)))["deviceVersionOneMotorAngleEvent"] == v["expected_state"]
        return
    elif kind == "parse_extended":
        events = dict(extended(list(expected)))
        state = v["expected_state"]
        if "intensities" in state:
            actual_state = {"intensities": {
                "1": events["deviceMassageHeadStrengthStatusEvent"],
                "2": events["deviceMassageFootStrengthStatusEvent"],
            }}
        elif "position" in state:
            actual_state = events["deviceVersionOneMotorAngleEvent"]
        elif "rgb" in state:
            color = cast(dict[str, list[int]], events["deviceRGBStripColorStatusEvent"])
            actual_state = {"rgb": color["rgba_bytes"][:3]}
        else:
            key = next(iter(state))
            event = {
                "rgb_seconds": "deviceRGBStripTimerStatusEvent",
                "rgb_groove": "deviceRGBStripMotionStatusEvent",
                "rgb_power": "deviceRGBStripStatusEvent",
                "snore_detection": "deviceAntiSnoreEvent",
                "off_bed_detection": "deviceGetOffBedStatusEvent",
                "snore_stop_event": "deviceCharacteristicsSubscriptionSnoreStopPlayMusicEvent",
            }[key]
            actual_state = {key: event in events if key == "snore_stop_event" else events[event]}
        assert actual_state == state
        assert codec.is_valid(expected)
        return
    else:
        raise AssertionError(kind)
    assert actual == expected
