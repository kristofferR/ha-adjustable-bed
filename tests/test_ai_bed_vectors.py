"""Frozen AI Bed 5.7.9 subset; these vectors are source derived, not captures."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from custom_components.adjustable_bed.codec import ai_bed as aa
from custom_components.adjustable_bed.codec import ai_bed_adaptive as adaptive
from custom_components.adjustable_bed.codec import limoss, paramount, richmat

V = json.loads((Path(__file__).parent / "fixtures/ai_bed_vectors.json").read_text())


@pytest.mark.parametrize("row", V["limos-vectors"], ids=lambda row: row["action"])
def test_limos_matches_existing_codec(row):
    plain = bytes.fromhex(row["plaintext"])
    assert limoss.frame(plain[1:6], plain[6]).hex() == row["bytes"]
    assert limoss.encrypt(plain).hex() == row["bytes"][2:-2]


@pytest.mark.parametrize("row", V["hj-vectors"], ids=lambda row: row["id"])
def test_hj_matches_existing_codec(row):
    expected = bytes.fromhex(row["expected_bytes"])
    data = row["inputs"].get("data", list(expected[:-1]))
    assert richmat.frame(*data) == expected
    assert richmat.command(expected[3]) == expected


@pytest.mark.parametrize(
    "row", V["primary-305-vectors"] + V["qc-extra-vectors"], ids=lambda row: row["action"]
)
def test_primary_frames(row):
    expected = bytes.fromhex(row["bytes"])
    assert aa.frame(expected[2], expected[3:-1]) == expected
    # The other existing XOR codec has a different header/field order.
    assert paramount.frame(expected[2], expected[3:-1]) != expected
    x = row.get("inputs", {})
    action = row["action"]
    if action.startswith("MCU clock"):
        assert (
            aa.clock(datetime(x["year"], x["month"], x["day"], x["hour"], x["minute"], x["second"]))
            == expected
        )
    elif action.startswith("Privacy"):
        assert aa.privacy(x["pin"]) == expected
    elif action == "Vibration single":
        assert aa.vibration(**x) == expected
    elif action.startswith("Vibration both"):
        assert aa.vibration_both(x["mode"], x["headLevel"], x["footLevel"], x["flag"]) == expected
    elif action.startswith("Query packages"):
        assert aa.query(x["packages"]) == expected
    elif "schedule" in action or action in ("Wake disabled", "Inflation disabled"):
        assert (
            aa.schedule(
                expected[2], *(int(x[key], 16) for key in ("hour_hex", "minute_hex", "week_hex"))
            )
            == expected
        )
    elif action.startswith("Sleep timer"):
        assert aa.schedule(0x2F, **{k: x[k] for k in ("hour", "minute", "week")}) == expected


@pytest.mark.parametrize(
    "row",
    V["primary-state-vectors"],
    ids=lambda row: row["action"] if "action" in row else str(row["inputs"]),
)
def test_waist_cache(row):
    frame, cache, reset = aa.waist_state(**row["inputs"])
    assert frame.hex() == row["bytes"]
    assert list(cache) == row["next_cache"]
    assert list(reset) == row["reset_provider"]


@pytest.mark.parametrize("row", V["qc-parser-vectors"])
def test_qc_parsers(row):
    parser = {"qc_sample": aa.qc_sample, "qc_stm32": aa.qc_stm32, "qc_wave": aa.qc_wave}[
        row["decoder"]
    ]
    raw = bytes.fromhex(row["bytes"])
    assert parser(raw) == row["expected"]
    assert parser(raw[:-1] + bytes((raw[-1] ^ 1,))) is None


def test_adaptive_crypto_and_all_crc_entries():
    v = V["adaptive-heart-vector"]
    assert (
        adaptive.frame(bytes.fromhex(v["plaintext"]), bytes.fromhex("aa1015")).hex() == v["frame"]
    )
    assert list(adaptive.HIGH) == V["crypto-tables"]["high"]
    assert list(adaptive.LOW) == V["crypto-tables"]["low"]
    assert adaptive.crc_bytes(1) == b"\x01"
    with pytest.raises(ValueError):
        adaptive.crc_bytes(255)


def test_malformed_state_is_safe_and_2305_quirk_preserved():
    assert aa.parse_state(bytes.fromhex("bb002305")) is None
    data = bytes([0xBB, 20, 0x23, 5, *range(15), 255])
    state = aa.parse_state(data)
    assert state is not None and state["headGear"] == 3 and state["sleepMode"] == 14


def test_route_action_tables_reproduce_frozen_ui_literals():
    from custom_components.adjustable_bed.profiles.ai_bed import PROFILES

    for route, rows in (
        ("305", V["primary-305-vectors"][:16]),
        ("limos", V["limos-vectors"]),
        ("hj001", V["hj-vectors"][:17]),
    ):
        for row in rows:
            key = row["action"].lower().split(" (")[0].replace(" ", "_").replace("-", "_")
            expected = bytes.fromhex(row["bytes"] if "bytes" in row else row["expected_bytes"])
            profile = PROFILES[route]
            assert profile.encode(profile.actions[key]) == expected
