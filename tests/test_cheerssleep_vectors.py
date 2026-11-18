"""CheersSleep 2.7.0 literal frames and model catalog through the codec."""

import pytest

from custom_components.adjustable_bed.codec import cheerssleep as codec
from tests.cheerssleep_vectors import AUXILIARY, MODELS, NUMERIC, VECTORS, encode


@pytest.mark.parametrize("row", VECTORS + NUMERIC + AUXILIARY, ids=lambda row: row["id"])
def test_accepted_frame(row):
    assert encode(row).hex() == row["expected_bytes"]


def test_catalog_identity():
    assert len(VECTORS) == 23
    assert len(MODELS) == 36
    assert len({r["model_key"] for r in MODELS}) == 36
    assert {r["builder"] for r in NUMERIC} == {"p1", "normal", "setting", "query"}


def test_independent_counters_cache_and_rollover():
    counters = codec.Counters()
    assert counters.control(257, held=True).hex() == "0201010100000000"
    assert counters.control(257, held=True).hex() == "0201010100000000"
    assert counters.control(1281).hex() == "0301010500000000"
    assert counters.control(257, held=True).hex() == "0301010100000000"
    assert counters.configure(4353, 10).hex() == "010301110a000000"
    assert counters.mac_query().hex() == "0307000000000000"
    counters.command = 255
    assert counters.control(257).hex() == "0001010100000000"


def test_signed_sleep_fields_and_short_frames():
    assert codec.sleep_state(bytes.fromhex("01870f807fff010280")) == codec.SleepState(
        "left", 3, True, True, -128, 127, -1, 1, 2, -128
    )
    assert codec.sleep_state(bytes.fromhex("018800807fff010280")).heart == 0
    assert codec.sleep_state(bytes(8)) is None
    assert codec.sleep_mac(bytes.fromhex("0189112233445566")) == "112233445566"


def test_b0_light_precedes_side_and_mode_filter():
    frame = bytes.fromhex("eeb000aa000002020301")
    assert codec.basic_state(frame, massage=True, selected=2) == codec.BasicState(
        True, None, None, None
    )
    assert codec.basic_state(frame, massage=True, selected=1) == codec.BasicState(True, 1, 2, 3)
    assert codec.basic_state(
        bytes.fromhex("eeb000aa000009020301"), massage=True
    ) == codec.BasicState(True, None, None, None)
    assert codec.basic_state(frame[:9], massage=True) is None


def test_d0_offsets_nibbles_and_signed_clamp():
    frame = bytes.fromhex("eed00000112233ff010000ff2100000000")
    state = codec.shared_state(frame, selected=2)
    assert state.rgb == (17, 34, 51) and state.brightness == -1
    assert state.mode == 2 and state.level == 0 and not state.light and state.music
    assert codec.shared_state(frame, as_layout=True).light
    assert codec.shared_state(frame, selected=1).mode == 1
    assert codec.shared_state(frame[:16]) is None


def test_fresh_and_interrupted_burst_callback_count():
    burst = codec.Burst()
    assert [burst.step() for _ in range(6)] == [(True, False)] * 3 + [(False, False)] * 2 + [
        (False, True)
    ]
    assert burst.count == 0
    burst.step()
    burst.step()
    # Replacement doesn't reset the runnable. One command and four releases.
    assert [burst.step() for _ in range(4)] == [
        (True, False),
        (False, False),
        (False, False),
        (False, True),
    ]
    assert codec.rgb_parameter(17, 34, 51, 68) == 0x11223344


def test_original_constructed_parser_and_burst_fixtures():
    import json

    from tests.cheerssleep_vectors import ROOT

    fixtures = json.loads((ROOT / "behavior.json").read_text())
    for row in fixtures["b0"]:
        assert codec.basic_state(
            bytes.fromhex(row["frame"]), massage=True, selected=row["selected"]
        ) == codec.BasicState(row["light"], row["mode"], row["head"], row["foot"])
    row = fixtures["d0"]
    left = codec.shared_state(bytes.fromhex(row["frame"]), selected=1)
    assert left == codec.SharedState(
        tuple(row["rgb"]),
        row["brightness"],
        row["light"],
        row["music"],
        row["left_mode"],
        row["level"],
    )
    assert codec.shared_state(bytes.fromhex(row["frame"]), selected=2).mode == row["right_mode"]
    row = fixtures["sleep"]
    assert codec.sleep_state(bytes.fromhex(row["frame"])) == codec.SleepState(
        **{k: v for k, v in row.items() if k != "frame"}
    )
    for name in ("burst", "interrupted_burst"):
        row = fixtures[name]
        burst = codec.Burst(row["initial_count"])
        commands, releases, at = [], [], 0
        while True:
            command, final = burst.step()
            (commands if command else releases).append(at)
            if final:
                releases.append(at)
                break
            at += 100
        assert commands == row["command_ms"] and releases == row["release_ms"]
    row = fixtures["color_selection"]
    # HA's RGB picker supplies the selected RGB directly; no Android UI copy.
    assert codec.setting(5, *row["selected_rgb"]).hex() == row["frame"]
