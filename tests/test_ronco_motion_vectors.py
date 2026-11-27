"""The accepted row175 literals, before any runtime/controller adaptation."""

from datetime import time

import pytest

from custom_components.adjustable_bed.beds.ronco_motion.protocol import (
    alarm_minutes,
    parse_notification,
)
from custom_components.adjustable_bed.codec import richmat as codec
from tests.ronco_motion_vectors import VECTORS


@pytest.mark.parametrize(
    "vector", [v for v in VECTORS if "notification" not in v["inputs"]], ids=lambda v: v["id"]
)
def test_existing_codec_reproduces_frozen_literals(vector):
    inputs = vector["inputs"]
    if "opcode" in inputs:
        frames = (codec.command(inputs["opcode"], inputs["selector"]),)
    elif "minutes" in inputs:
        frames = codec.countdown(inputs["minutes"], inputs["mode"])
    else:
        frames = (codec.frame(0x6E, inputs["kind"], inputs["a"], inputs["b"]),)
    assert " ; ".join(frame.hex() for frame in frames) == vector["expected_bytes"]


@pytest.mark.parametrize(
    "vector", [v for v in VECTORS if "notification" in v["inputs"]], ids=lambda v: v["id"]
)
def test_parser_vectors(vector):
    assert (
        parse_notification(bytes.fromhex(vector["inputs"]["notification"]))
        == vector["expected_parsed"]
    )


@pytest.mark.parametrize(
    "vector", [v for v in VECTORS if "now" in v["inputs"]], ids=lambda v: v["id"]
)
def test_alarm_rollover(vector):
    i = vector["inputs"]
    assert alarm_minutes(time(*i["now"]), time(*i["chosen"])) == i["minutes"]
