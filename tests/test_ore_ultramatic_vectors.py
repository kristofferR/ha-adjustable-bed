"""ORE Ultramatic 1.0.5 frames, state fixtures and parser observations."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pytest

from custom_components.adjustable_bed.codec import keeson as codec
from custom_components.adjustable_bed.profiles import keeson as profiles
from custom_components.adjustable_bed.profiles import ore_ultramatic as app

_FIXTURES = Path(__file__).parent / "fixtures/ore_ultramatic"
VECTORS = json.loads((_FIXTURES / "vectors.json").read_text())
REPAIR = json.loads((_FIXTURES / "repair.json").read_text())["observations"]


def encode(builder: str, p: dict) -> bytes:
    route = p.get("protocol", "P2")
    if builder == "control":
        return profiles.encode(app.profile(route), p["key"])
    if builder == "current_time":
        return codec.clock(
            datetime(p["year"], p["month"] + 1, p["day"], p["hour"], p["minute"], p["second"])
        )
    now = datetime(2026, 11, 15 + p["weekday"], p["hour"], p["minute"], p["second"])
    if builder == "query":
        return app.query(route, now)
    return app.alarm(
        route,
        now,
        enabled=p["enabled"],
        hour=p["alarm_hour"],
        minute=p["alarm_minute"],
        repeat=p["repeat"],
        kind=p["alarm_type"],
    )


@pytest.mark.parametrize("row", VECTORS, ids=lambda v: v["id"])
def test_accepted_vectors(row):
    if row["inputs"]["builder"] != "notification":
        assert encode(row["inputs"]["builder"], row["inputs"]["parameters"]) == bytes.fromhex(
            row["expected_bytes"]
        )
        return
    parser = codec.UltramaticParser()
    callback_total = 0
    for fragment in row["inputs"].get("seed_fragments", ()):
        callback_total += len(parser.feed(bytes.fromhex(fragment)))
    for index, fragment in enumerate(row["inputs"]["fragments"]):
        callbacks = parser.feed(bytes.fromhex(fragment))
        callback_total += len(callbacks)
        if "expected_observations" in row:
            expected = row["expected_observations"][index]
            observed = asdict(parser.state)
            assert {key: observed[key] for key in expected["state"]} == expected["state"]
            assert parser.pending == (
                bytes.fromhex(expected["cache"]) if expected["cache"] else None
            )
            assert list(callbacks) == expected["callbacks"]
            assert callback_total == expected["callback_total"]
    observed = asdict(parser.state)
    assert {key: observed[key] for key in row["expected_state"]} == row["expected_state"]


@pytest.mark.parametrize("row", REPAIR, ids=lambda r: r["case"])
def test_ultra_a001_observations(row):
    parser = codec.UltramaticParser()
    parser.state = codec.UltramaticState(**row["state_before"])
    fragment = bytes.fromhex(row["input"])
    if row["cache"] and not fragment.startswith(codec.JALON_PREFIX):
        parser.pending = bytes.fromhex(row["cache"])
    assert list(parser.feed(fragment)) == row["callbacks"]
    assert asdict(parser.state) == row["state_after"]
    assert parser.pending == (bytes.fromhex(row["cache"]) if row["cache"] else None)


def test_bounds_safe_difference_and_cache_retention():
    parser = codec.UltramaticParser()
    parser.feed(bytes.fromhex("e2fe1600"))  # Android would index past the end.
    parser.feed(bytes.fromhex("ed8003071e"))  # Correct preflight returns unchanged.
    assert asdict(parser.state) == asdict(codec.UltramaticState())
    parser.feed(bytes.fromhex("f4fe1600"))
    cached = parser.pending
    parser.feed(bytes(10))
    parser.feed(bytes(16))
    parser.feed(bytes(21))
    assert parser.pending == cached
    assert parser.feed(bytes(3)) == ("massage",)
    assert parser.pending == cached
