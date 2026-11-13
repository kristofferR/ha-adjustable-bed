"""All 158 accepted row179 command literals, not an artifact re-audit."""

import pytest

from custom_components.adjustable_bed.beds.sonicsleep.protocol import Receiver, decode, parse_alarm

from .sonicsleep_vectors import VECTORS, encode


@pytest.mark.parametrize("row", VECTORS["commands"] + VECTORS["alarm_repair"], ids=lambda r: r["id"])
def test_existing_codec_reproduces_all_commands(row):
    assert encode(row).hex() == row["expected_bytes"]


@pytest.mark.parametrize("row", VECTORS["notifications"], ids=lambda r: r["id"])
def test_received_state(row):
    expected = {k: v for k, v in row["expected"].items() if not k.endswith("_EXCLUDED")}
    assert decode(bytes.fromhex(row["bytes"])) == expected


@pytest.mark.parametrize("row", VECTORS["streams"], ids=lambda r: r["id"])
def test_stream_contract(row):
    receiver = Receiver()
    frames = [frame.hex() for chunk in row["chunks"] for frame in receiver.feed(bytes.fromhex(chunk))]
    assert frames == row["frames"]
    assert receiver.pending.hex() == row["remaining"]


@pytest.mark.parametrize("row", [r for r in VECTORS["alarm_repair"] if r["kind"] == "cached_toggle"], ids=lambda r: r["id"])
def test_production_alarm_opaque_toggle(row):
    alarm = parse_alarm(bytes.fromhex(row["received"]))
    assert alarm is not None
    assert alarm.opaque == row["expected_cached"]["reserved"]
    assert alarm.toggle(row["enabled"]).packet().hex() == row["expected_bytes"]
