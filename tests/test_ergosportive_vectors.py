"""A100 frozen literals first exercised against the existing AA codec."""

import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.codec import sleep_assistant as codec

VECTORS = json.loads((Path(__file__).parent / "fixtures/ergosportive/vectors.json").read_text())


@pytest.mark.parametrize(
    "row", [r for r in VECTORS if r["builder"] in ("instruct", "light")], ids=lambda r: r["id"]
)
def test_existing_codec_reproduces_selected_literals(row):
    actual = (
        codec.instruction(row["inputs"]["key"])
        if row["builder"] == "instruct"
        else codec.light(row["inputs"]["value"], False)
    )
    assert actual.hex() == row["expected_bytes"]


def test_corrected_secondary_release_and_recovered_ascii_builder():
    yoga = next(r for r in VECTORS if r["builder"] == "yoga_zero")
    assert codec.ergosportive_secondary_release().hex() == yoga["expected_bytes"]
    # Builder evidence only: no public RGB caller or chunk policy is authorized.
    for row in (r for r in VECTORS if r["builder"] == "rgb"):
        i = row["inputs"]
        body = "620D00000000" + bytes(255 - i[c] for c in ("r", "g", "b")).hex() + "0000010000"
        assert codec.ascii_frame(body).hex() == row["expected_bytes"]


def test_signed_normal_sensor_retention_absence_and_truncation():
    sensor = codec.ErgoSportiveNormalSensor()
    frame = bytearray(15)
    frame[0], frame[9], frame[10], frame[12] = 0x8A, 0xFE, 0x80, 1
    assert sensor.feed(frame)
    assert (sensor.heart, sensor.respiration, sensor.presence, sensor.twitch) == (-2, -128, True, 1)
    frame[14] = 7
    assert not sensor.feed(frame)
    assert sensor.heart == -2
    frame[14] = 1
    assert sensor.feed(frame)
    assert (sensor.heart, sensor.respiration, sensor.presence, sensor.twitch) == (
        None,
        None,
        False,
        0,
    )
    for length in range(15):
        assert not sensor.feed(frame[:length])
