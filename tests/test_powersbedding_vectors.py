"""Frozen PowersBedding literals prove reuse of K1 and Okin N-frame codecs."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from custom_components.adjustable_bed.codec import okin_nframe
from custom_components.adjustable_bed.profiles import powersbedding as app

VECTORS = json.loads((Path(__file__).parent / "fixtures/powersbedding/vectors.json").read_text())


def date(fields):
    return datetime(**{k: v for k, v in fields.items() if k != "weekday"})


@pytest.mark.parametrize("v", VECTORS, ids=lambda v: v["id"])
def test_frozen_vectors(v):
    i = v["inputs"]
    route = v["id"][:2].lower() if i["kind"] == "literal" else f"p{i.get('route', 0) + 1}"
    kind = i["kind"]
    if kind == "command":
        actual = app.normal(route, i["word"])
        if route == "p3":
            assert actual == okin_nframe.frame40(i["word"] & 0xFFFFFFFF)
    elif kind == "current":
        actual = app.clock(route, date(i["now"]))
    elif kind == "alarm":
        actual = app.alarm_fields(
            route, i["hour"], i["minute"], i["week"], i["massage"], i["mode"], date(i["now"])
        )
    elif kind == "cancel":
        actual = app.cancel(route, date(i["now"]))
    elif kind == "literal":
        actual = app.alarm_query(route) if "alarm" in v["id"].lower() else okin_nframe.request(0xB0)
    elif kind == "weeks":
        assert (
            app.week_mask(i["selected"], date(i["now"]), i["hour"], i["minute"])
            == v["expected_week"]
        )
        return
    else:
        data = bytes.fromhex(v["expected_bytes"])
        parsed = (
            app.parse_massage(route, data)
            if i["domain"] == "massage"
            else app.parse_alarm(route, data)
        )
        expected = v["expected_state"]
        if expected is None or isinstance(expected, str):
            assert parsed is None  # Safe short-frame refusal replaces the app's exception.
        elif i["domain"] == "massage":
            assert parsed is not None
            assert (parsed.arc, parsed.wave, parsed.head, parsed.foot) == tuple(
                expected[k] for k in ("arc", "wave", "head", "foot")
            )
        else:
            assert parsed is not None
            assert (parsed.hour, parsed.minute, parsed.week, parsed.enabled) == tuple(
                expected[k] for k in ("hour", "minute", "week", "enabled")
            )
            if route == "p1":
                assert (parsed.massage, parsed.memory_a, parsed.memory_b) == tuple(
                    expected[k] for k in ("massage", "memory_a", "memory_b")
                )
            else:
                assert (parsed.massage, parsed.memory_a, parsed.memory_b) == tuple(
                    expected["selected_mode"] == k for k in ("massage", "memory_a", "memory_b")
                )
        return
    assert actual is not None and actual.hex() == v["expected_bytes"].replace(" ", "")
