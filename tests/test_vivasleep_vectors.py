"""Static VivaSleep 1.0.4 vectors; no captured hardware or complete bed contract."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from custom_components.adjustable_bed.codec import motomotion as codec
from custom_components.adjustable_bed.profiles import vivasleep as app

FIXTURES = Path(__file__).parent / "fixtures" / "vivasleep"
VECTORS = json.loads((FIXTURES / "vectors.json").read_text())
PARSER_VECTORS = json.loads((FIXTURES / "discovery-parser-vectors.json").read_text())


def _profile(*, wrapped: bool = False, selector: str = "15") -> app.VivaSleepProfile:
    return app.VivaSleepProfile(f"HHC00000{selector}0{'M' if wrapped else '0'}00")


@pytest.mark.parametrize("vector", VECTORS, ids=lambda row: row["id"])
def test_frozen_writer_and_numeric_bytes(vector) -> None:
    inputs = vector["inputs"]
    if vector["kind"] == "numeric":
        actual = codec.decimal_fields(inputs["command"], inputs["parameter"])
    else:
        actual = _profile(wrapped=inputs["enhanced"]).writer_bytes(inputs["command"])
    expected = vector["expected_bytes"]
    assert actual == (None if expected is None else bytes.fromhex(expected))


@pytest.mark.parametrize("vector", PARSER_VECTORS, ids=lambda row: row["id"])
def test_frozen_discovery_and_accumulated_parser(vector) -> None:
    if vector["kind"] == "discovery":
        assert app.accepts_name(vector["name"]) == vector["expected"]
    else:
        state = app.parse_accumulated(bytes.fromhex(vector["input_hex"]))
        # JSON arrays represent the immutable tuples returned by the parser.
        actual = {
            k: list(v) if isinstance(v, tuple) else v
            for k, v in asdict(state).items()
            if v is not None
        }
        assert actual == vector["expected"]


@pytest.mark.parametrize("wrapped", (False, True))
@pytest.mark.parametrize("field_b", (False, True))
def test_conditional_sync_is_one_frozen_frame(wrapped: bool, field_b: bool) -> None:
    profile = _profile(wrapped=wrapped)
    vector = VECTORS[0 if field_b else 1]
    frame = profile.sync_frame(field_7=True, field_b=field_b, field_13=0)
    assert frame == bytes.fromhex(vector["expected_bytes"])
    assert frame is not None
    assert profile.writer_bytes(frame.decode("ascii")) == frame
    assert profile.write_with_response is False


@pytest.mark.parametrize(("field_7", "field_13"), ((False, 0), (True, 1), (False, 1), (True, -1)))
def test_sync_visibility_gates(field_7: bool, field_13: int) -> None:
    assert _profile().sync_frame(field_7=field_7, field_b=True, field_13=field_13) is None


@pytest.mark.parametrize(
    ("selector", "panel"),
    (
        ("15", "PanelA"),
        ("A0", "PanelA"),
        ("35", "PanelD"),
        ("45", "PanelD"),
        ("85", "PanelD"),
        ("C0", "PanelD"),
        ("40", "PanelFour"),
        ("25", "PanelFour"),
        ("55", "PanelFour"),
        ("B0", "PanelFour"),
        ("95", "WR1140"),
        ("96", "WR1140"),
        ("97", "WR1140"),
        ("98", "WR1140"),
        ("30", "PanelThree"),
        ("65", "PanelThree"),
        ("75", "PanelThree"),
        ("00", "PanelZero"),
        ("10", "PanelOne"),
        ("20", "PanelTwo"),
        ("50", "PanelFive"),
        ("60", "PanelSix"),
        ("70", "PanelSeven"),
        ("80", "PanelEight"),
        ("90", "PanelNine"),
        ("D0", "PanelSixZG"),
        ("E0", "PanelE"),
        ("X0", "PanelOne"),
    ),
)
def test_primary_factory_selection_without_capability_inheritance(
    selector: str, panel: str
) -> None:
    assert _profile(selector=selector).panel == panel


def test_name_indices_use_dart_utf16_units() -> None:
    profile = app.VivaSleepProfile("😀HHC000150M00")
    assert profile.panel == "PanelA"
    assert profile.wrapped
    with pytest.raises(ValueError, match="14 UTF-16"):
        app.VivaSleepProfile("HHC-short")


@pytest.mark.parametrize(
    ("value", "service", "characteristic"),
    (
        ("0000ffe0-0000-1000-8000-00805f9b34fb", True, False),
        ("0000fFe1-0000-1000-8000-00805f9b34fb", False, True),
        ("prefixFFE0suffix", True, False),
        ("prefixFFE1suffix", False, True),
        ("FFE0FFE1", True, True),
        ("FFE2", False, False),
    ),
)
def test_gatt_substring_predicates(value: str, service: bool, characteristic: bool) -> None:
    assert app.matches_service(value) is service
    assert app.matches_characteristic(value) is characteristic


def test_shared_routine_schedules_do_not_imply_per_action_cleanup() -> None:
    assert app.REPEAT_INTERVAL_MS == 100
    assert app.SHORT_UP_THRESHOLD == 5
    assert app.SHORT_UP_OFFSETS_MS == (0, 100, 200)
    assert _profile().stop_schedule == tuple((i, b"$b") for i in (0, 30, 60, 90, 120))
    assert _profile(wrapped=True).stop_schedule == tuple(
        (i, b"$#$bR\r") for i in (0, 30, 60, 90, 120)
    )


def test_literal_space_filtering_and_bad_sync_token() -> None:
    assert codec.decimal_tokens(b"\xff$#1_2  3\t4R\r") == ("12", "", "34")
    fields = ["00000"] * 39
    fields[24] = ""  # Interior empty tokens survive filtering and literal splitting.
    with pytest.raises(ValueError, match="decimal sync token"):
        app.parse_accumulated(" ".join(fields).encode("ascii"))


@pytest.mark.parametrize(
    ("token", "expected"),
    (("9223372036854775807", 9223372036854775807), ("0" * 5000 + "1", 1), ("0" * 5000, 0)),
)
def test_sync_integer_matches_dart_decimal_limits(token: str, expected: int) -> None:
    fields = ["00000"] * 39
    fields[24] = token
    state = app.parse_accumulated(" ".join(fields).encode("ascii"))
    assert state.sync_type == expected
    assert state.stream_event == "OK"


def test_sync_integer_overflow_rejects_the_event() -> None:
    fields = ["00000"] * 39
    fields[24] = "9223372036854775808"
    with pytest.raises(ValueError, match="decimal sync token"):
        app.parse_accumulated(" ".join(fields).encode("ascii"))


@pytest.mark.parametrize("wrapped", (False, True))
@pytest.mark.parametrize(
    ("repeat", "count", "callback", "cancelled", "expected_offsets"),
    (
        (True, 0, False, False, (0, 100, 200)),
        (True, 4, False, False, (0, 100, 200)),
        (True, 5, False, False, ()),
        (False, 0, False, False, ()),
        (True, 0, True, False, ()),
        (True, 0, False, True, ()),
    ),
)
def test_short_up_fallback_gates(
    wrapped, repeat, count, callback, cancelled, expected_offsets
) -> None:
    profile = _profile(wrapped=wrapped)
    schedule = profile.short_up_schedule(
        "$K", repeat=repeat, count=count, has_up_callback=callback, cancelled=cancelled
    )
    expected_bytes = b"$#$KR\r" if wrapped else b"$K"
    assert schedule == tuple((offset, expected_bytes) for offset in expected_offsets)


def test_short_up_respects_writer_suppression() -> None:
    assert (
        _profile(wrapped=True).short_up_schedule(
            "$z", repeat=True, count=0, has_up_callback=False, cancelled=False
        )
        == ()
    )


@pytest.mark.parametrize("command", ("", "null"))
@pytest.mark.parametrize("wrapped", (False, True))
def test_empty_writer_suppression(command: str, wrapped: bool) -> None:
    assert _profile(wrapped=wrapped).writer_bytes(command) is None
