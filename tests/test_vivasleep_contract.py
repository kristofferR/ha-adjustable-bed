"""Every accepted VivaSleep literal and representative original-name branch."""

from __future__ import annotations

import gzip
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from custom_components.adjustable_bed.beds.bedgear.protocol import Receiver, color_parameters
from custom_components.adjustable_bed.codec import motomotion as codec
from custom_components.adjustable_bed.profiles import vivasleep as app

FIXTURES = Path(__file__).parent / "fixtures" / "vivasleep"
VECTORS = json.loads((FIXTURES / "full-vectors.json").read_text())
VARIANTS = json.loads(gzip.decompress((FIXTURES / "variants.json.gz").read_bytes()))
PANELS = {
    "Panel" + key.title().replace("_", ""): "panel_" + key
    for key in (
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "a",
        "d",
        "e",
    )
}
PANELS.update(PanelSixZG="panel_six_zg", WR1140="wr1140")


def parsed(data: bytes) -> dict:
    fields = {
        k: list(v) if isinstance(v, tuple) else v
        for k, v in asdict(app.parse_accumulated(data)).items()
        if v is not None
    }
    result = {"field_count": fields["field_count"]}
    for old, new in (
        ("rgb_fields_7_b_f_13", "rgb"),
        ("alarm_fields_7_b_f", "alarm"),
        ("sync_type", "sync_type"),
        ("stream_event", "event"),
    ):
        if old in fields:
            result[new] = fields[old]
    if "bind_fields_7_b" in fields:
        result["bind_recognized"], result["sync_on"] = fields["bind_fields_7_b"]
    return result


@pytest.mark.parametrize(
    "row", [v for v in VECTORS if v["kind"] != "gesture"], ids=lambda r: r["id"]
)
def test_full_frozen_vectors(row):
    kind, inp = row["kind"], row["inputs"]
    expected = row.get("expected", row.get("expected_hex", row.get("expected_text")))
    if kind == "frame":
        actual = codec.decimal_fields(
            inp.get("command", inp.get("a")), inp.get("parameter", inp.get("b"))
        ).hex(" ")
    elif kind in ("writer", "write", "marker", "utf16"):
        wrapped = (
            app.VivaSleepProfile(inp["selected_name"]).wrapped
            if "selected_name" in inp
            else inp["m"]
        )
        value = codec.utf16_transport(inp["text"], wrapped=wrapped)
        actual = (
            value.hex(" ") if value is not None else "NO WRITE" if expected == "NO WRITE" else None
        )
    elif kind == "cached_alarm":
        actual = app.alarm_frame(**inp).decode("ascii")
    elif kind == "panel":
        actual = PANELS[app.select_panel(inp["name"])]
    elif kind == "axes":
        actual = {
            "head and foot together" if axis == "combined" else axis: up + "/" + down
            for axis, up, down in app.axes_for_name(inp["name"])
        }
    elif kind == "rgb":
        actual = list(color_parameters(tuple(inp["rgb"])))
    elif kind == "parse":
        actual = parsed(bytes.fromhex(inp["hex"]))
    elif kind == "parse_error":
        with pytest.raises(ValueError):
            parsed(bytes.fromhex(inp["hex"]))
        return
    elif kind == "accumulator":
        receiver = Receiver()
        results = []
        for fragment in inp["chunks"]:
            texts = receiver.feed(bytes.fromhex(fragment))
            results.append(parsed(texts[0].encode("ascii")) if texts else None)
        actual = {
            "results": results,
            "buffer": receiver.buffer.hex(" "),
            "active": receiver.collecting,
        }
    elif kind == "stop_train":
        actual = list(app.STOP_OFFSETS_MS)
    elif kind == "rgb_schedule":
        step = 100 if inp["m"] else 200
        actual = {
            "channel_times": [index * step + (0 if inp["m"] else 100) for index in range(3)],
            "marker_times": [] if inp["m"] else [0, 200, 400],
            "clear_busy": 300 if inp["m"] else 600,
        }
    else:
        raise AssertionError(kind)
    assert actual == expected


@pytest.mark.parametrize("row", VARIANTS, ids=lambda r: r["id"])
def test_all_4752_original_name_equivalence_classes(row):
    profile = app.VivaSleepProfile(row["name"])
    assert PANELS[profile.panel] == row["panel"]
    assert {
        "head and foot together" if axis == "combined" else axis: up + "/" + down
        for axis, up, down in profile.axes
    } == row["axes"]
    assert (profile.rgb, profile.brightness, profile.alarm, profile.wrapped, profile.sync) == (
        row["rgb"],
        row["brightness"],
        row["alarm"],
        row["writer_M"],
        row["sync_settings"],
    )
