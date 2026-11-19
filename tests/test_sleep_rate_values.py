"""Heart and breathing rates the apps show as text become whole numbers."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from custom_components.adjustable_bed.beds.casper_sleep.controller import _typed_live
from custom_components.adjustable_bed.beds.casper_sleep.protocol import Live
from custom_components.adjustable_bed.beds.entity_specs import sleep_rate_value
from custom_components.adjustable_bed.beds.gmmotor.sleep_protocol import normal_live, sxb_live
from custom_components.adjustable_bed.beds.goodvibe.sleep import Realtime


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("72", 72),
        ("72.0", 72),
        ("72.6", 73),
        ("0x48", 72),
        (" 14 ", 14),
        (72.0, 72),
        (15, 15),
        ("--", None),
        ("", None),
        ("nan", None),
        ("inf", None),
        ("-5", None),
        (True, None),
        (None, None),
    ],
)
def test_rate_text_is_a_whole_number_or_unknown(value: object, expected: int | None) -> None:
    assert sleep_rate_value(value) == expected


def _casper(reading: list[int | float]) -> int | None:
    live = Live("sxb")
    live.feed({"L": reading, "R": []})
    return _typed_live("heart", live.state["L"]["heart"])


def _goodvibe(reading: list[int | float]) -> int | None:
    realtime = Realtime()
    realtime.accept(3, reading)
    return realtime.typed()["heart"]


def _gmmotor_sxb(reading: list[int | float]) -> int | None:
    state = sxb_live(reading)
    assert state is not None
    return sleep_rate_value(state.first_value)


def _gmmotor_mm(reading: list[int | float]) -> int | None:
    online = "-".join(str(int(x)) for x in (1, 0, reading[2], reading[3], 1, 0, 0, 0))
    return sleep_rate_value(normal_live(online).first_value)


@pytest.mark.parametrize("parse", [_casper, _goodvibe, _gmmotor_sxb, _gmmotor_mm])
@pytest.mark.parametrize(("heart", "expected"), [(72, 72), (72.0, 72), (72.6, 73)])
def test_each_bed_shows_a_reported_rate(
    parse: Callable[[list[int | float]], int | None], heart: float, expected: int
) -> None:
    """An integer or decimal reading in an array shows as the same whole number it read."""
    if parse is _gmmotor_mm and heart != int(heart):
        pytest.skip("The MM record is integer text")
    assert parse([0, 1, heart, 14, 0]) == expected
