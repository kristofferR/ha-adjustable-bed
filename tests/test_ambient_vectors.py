"""M3 Ambient frames from the sealed 1.1.11 write and parser vectors."""

import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.codec import ambient as p1
from custom_components.adjustable_bed.codec import ambient_climate as p2
from custom_components.adjustable_bed.profiles import ambient as app

FIXTURES = Path(__file__).parent / "fixtures/ambient"

_FIXED = {
    "fixed-lyingFlat": p1.HOME_FLAT,
    "fixed-ledOn": p1.LIGHT_ON,
    "fixed-ledOff": p1.LIGHT_OFF,
    "fixed-checkStatusOfPowerBase": p1.BED_STATE_QUERY,
    "fixed-offHeadMassage": p1.massage("shoulder", 0),
    "fixed-headMassageGear1": p1.massage("shoulder", 1),
    "fixed-headMassageGear2": p1.massage("shoulder", 2),
    "fixed-headMassageGear3": p1.massage("shoulder", 3),
    "fixed-offFootMassage": p1.massage("feet", 0),
    "fixed-footMassageGear1": p1.massage("feet", 1),
    "fixed-footMassageGear2": p1.massage("feet", 2),
    "fixed-footMassageGear3": p1.massage("feet", 3),
}


@pytest.mark.parametrize(
    "row", json.loads((FIXTURES / "writes.json").read_text()), ids=lambda row: row["id"]
)
def test_frozen_write_vector(row):
    values = row["inputs"].copy()
    builder = values.pop("builder")
    if builder == "fixed":
        actual = _FIXED[row["id"]]
    elif builder == "position":
        side = p1.Side(values.pop("side")) if "side" in values else None
        template = bytes.fromhex(values.pop("template")) if "template" in values else None
        actual = p1.position(p1.Coordinates(**values), side, template=template)
    elif builder == "heat":
        actual = p2.heat(tuple(values["zones"]))
    elif builder == "fan":
        actual = p2.fan(p2.Query(values["code"]), values["level"])
    elif builder in ("query", "heat_timer"):
        actual = getattr(p2, builder)(**values)
    else:
        assert builder == "rgb"
        actual = p1.rgb(**values)
    assert actual == bytes.fromhex(row["expected_bytes"])


@pytest.mark.parametrize(("frame", "expected"), json.loads((FIXTURES / "state.json").read_text()))
def test_frozen_parser_vector(frame, expected):
    data = bytes.fromhex(frame)
    if data.startswith(b"\x51\x9f"):
        state = p2.parse(data)
        if isinstance(state, p2.Fan):
            assert [state.code, state.raw, state.level] == expected
        else:
            assert isinstance(state, p2.Heat)
            assert list(state.zones) == expected
            assert p2.parse(data[:-1] + b"\x00") is None
        return
    state = p1.parse_bed_state(data)
    if isinstance(state, p1.BedState):
        assert (state.shoulder, state.feet_massage, state.rgb) == (1, 1, (0, 83, 106))
        state = state.position
    assert isinstance(state, p1.Position)
    values = [state.coordinates.head, state.coordinates.feet, state.coordinates.neck, state.lumbar]
    if state.side is not None:
        values.insert(0, p1.signed(state.side))
    assert values == expected


@pytest.mark.parametrize(
    ("channel", "component", "frame"),
    (
        ("red", 255, "24 23 80 E8 00 78 10 41 0D"),
        ("green", 128, "24 23 80 E9 00 3C 55 41 0D"),
        ("blue", 1, "24 23 80 EA 00 00 6A 41 0D"),
    ),
)
def test_picker_mapping(channel, component, frame):
    assert p1.rgb(channel, app.picker_value(component)) == bytes.fromhex(frame)


@pytest.mark.parametrize(
    ("zone", "frame"),
    (
        ("shoulder", "242382790015ee410d"),
        ("feet", "2423827a0017ef410d"),
    ),
)
def test_massage_requires_a_full_exact_echo(zone, frame):
    data = bytes.fromhex(frame)
    assert p1.parse_massage_echo(data) == (zone, 1)
    assert p1.parse_massage_echo(data[:-1] + b"\x0a") is None
    assert p1.parse_massage_echo(data[:6] + bytes((data[6] ^ 1,)) + data[7:]) is None
