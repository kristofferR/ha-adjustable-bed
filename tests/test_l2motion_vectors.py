"""Prove Leon's L2Motion carrier fit without deriving expected bytes from code."""

import pytest

from custom_components.adjustable_bed.codec.motomotion import (
    decimal_fields,
    music_command,
    short_transport,
)
from tests.l2motion_vectors import VECTORS


@pytest.mark.parametrize("inputs,expected", VECTORS)
def test_literal_carrier_fit(inputs, expected):
    if "command" in inputs:
        frame = short_transport(inputs["command"], wrapped=inputs["m_route"])
    elif "first" in inputs:
        frame = decimal_fields(inputs["first"], inputs["second"])
    elif "letter" in inputs:
        frame = music_command(inputs["letter"], inputs["value"])
    else:
        aggregate = b"".join(
            music_command(k, v) for k, v in zip("MTBV", inputs["values"], strict=True)
        )
        frame = short_transport(aggregate.decode(), wrapped=inputs["m_route"])
    assert frame is not None and frame.hex() == expected


def test_wrapper_suppresses_only_query_and_preserves_complete_frames():
    assert short_transport("$z", wrapped=True) is None
    assert short_transport("", wrapped=False) is None
    assert short_transport("null", wrapped=False) is None
    assert short_transport("$#003150012000004R\r", wrapped=True) == b"$#003150012000004R\r"
