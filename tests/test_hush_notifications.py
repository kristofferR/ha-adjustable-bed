"""Accepted receive vectors: complete event coverage and literal field proofs."""

from __future__ import annotations

import binascii
import json
from pathlib import Path

import pytest

from custom_components.adjustable_bed.codec.casper import extra
from custom_components.adjustable_bed.hush_protocol import HushMainReceive, decode

VECTORS = json.loads((Path(__file__).parent / "fixtures/hush_notifications.json").read_text())


@pytest.mark.parametrize(
    "vector", [x for x in VECTORS if not x["id"].startswith("ota-")], ids=lambda x: x["id"]
)
def test_all_accepted_direct_notification_branches(vector):
    frame = bytes.fromhex(vector["inputs"]["frame"])
    event = decode(frame)
    assert (event is not None) == bool(vector["expected_state"])
    if event is None:
        return
    payload = vector["expected_state"][0][1]
    if isinstance(payload, (bool, int)) and vector["id"] != "massage-strength-pairs":
        assert payload in event.values.values()
    if vector["id"].startswith("alarm-"):
        assert list(event.values.values()) == list(payload.values())
    if vector["id"].startswith("blanket-empty"):
        assert event.values == {}
    if vector["id"] == "legacy-massage":
        assert event.values == {"mode": 2, "zone1": 7, "zone2": 0, "zone3": 7}
    if vector["id"] == "rgb-color":
        assert event.values == {"rgb": [255, 0, 255]}
    if vector["id"] == "heat-time":
        assert event.values == {"position": 1, "type": 2, "time": 258}
    if vector["id"] == "motor-height-full":
        assert event.values["monitor_height"] == 60
    if vector["id"] == "desk27":
        assert event.values["monitor_inch"] == 152.5


def test_extended_integrity_fragmentation_and_nonprogress_rejection():
    rx = HushMainReceive()
    frame = bytes.fromhex("6e210a0f0102010200ae")
    assert rx.feed(frame[:5]) == []
    assert rx.feed(frame[5:]) == [frame]
    assert rx.feed(frame[:-1] + b"\x00") == []
    firmware = bytes.fromhex("6e40000a010202438efa")
    assert binascii.crc_hqx(firmware[:-2], 0) == int.from_bytes(firmware[-2:], "big")
    assert rx.feed(firmware) == [firmware]
    with pytest.raises(ValueError):
        rx.feed(bytes.fromhex("6e2100008f"))
    ordinary = bytes.fromhex("6e90396e00")
    assert HushMainReceive().feed(ordinary) == [ordinary]
    # Bad packet must not prevent the next well-framed callback from being read.
    assert decode(extra(17, 3, (1, 0, 45), operation=2)).values == {"position": 1, "value": 45}


@pytest.mark.parametrize(
    "ordinary",
    ["6e09010078", "6e900000062500", "6e00000102030405060708090a0b0c00"],
)
@pytest.mark.parametrize("split", [5, 10])
def test_hush_height_after_ordinary_frame(ordinary, split):
    first = bytes.fromhex(ordinary)
    height = bytes.fromhex("6e210a0f0102010200ae")
    rx = HushMainReceive()
    assert rx.feed(first + height[:split]) == ([first, height] if split == len(height) else [first])
    if split < len(height):
        assert rx.feed(height[split:]) == [height]
    assert not rx.pending
