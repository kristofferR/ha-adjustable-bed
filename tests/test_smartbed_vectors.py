"""Literal builders and profile parsers from SmartBed 2.4.2, without hardware claims."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from custom_components.adjustable_bed.beds.smartbed.receive import Parser
from custom_components.adjustable_bed.profiles.smartbed import packet
from tests.smartbed_vectors import CATALOG_LITERALS


@pytest.mark.parametrize(("function", "sub", "data", "expected"), CATALOG_LITERALS)
def test_documented_ui_payloads(function, sub, data, expected):
    assert packet(5, function, sub, data).hex() == expected


FIXTURES = Path(__file__).parent / "fixtures" / "smartbed"
BUILDERS = json.loads((FIXTURES / "builders.json").read_text())
PARSERS = json.loads((FIXTURES / "parsers.json").read_text())


@pytest.mark.parametrize("vector", BUILDERS)
def test_existing_codecs_reproduce_every_frozen_builder(vector):
    i = vector["inputs"]
    assert (
        packet(
            i["p"],
            i["f"],
            i["s"],
            None if i["data"] is None else bytes(i["data"]),
            side=i["side"],
            ab=i["ab"],
            clock=tuple(i["clock"]),
        ).hex()
        == vector["expected_bytes"]
    )


@pytest.mark.parametrize("vector", PARSERS)
def test_profile_parser_preserves_valid_fields_and_rejects_unsafe_short_replies(vector):
    parser = Parser(vector["profile"])
    initial = asdict(parser.state)
    consumed = parser.profile_only(bytes.fromhex(vector["input_bytes"]), vector["side"])
    expected = vector["expected"]
    if "error" in expected:
        assert not consumed
        assert asdict(parser.state) == initial
    else:
        assert {
            "return": str(consumed).lower(),
            "page": parser.next_page,
            "state": asdict(parser.state),
        } == expected


def test_fragment_cache_and_manager_fallback_are_connection_owned():
    parser = Parser("cb")
    frame = bytes.fromhex("f4fe160000000000000000060400000000000003000400")
    parser.feed(frame[:20])
    parser.feed(frame[20:])
    assert (
        parser.state.massage_time,
        parser.state.head_intensity,
        parser.state.foot_intensity,
        parser.state.massage_wave,
    ) == (30, 3, 2, 3)
    assert parser.fragments.first == frame[:20]
    fresh = Parser("cb")
    assert not fresh.feed(frame[20:])
    parser = Parser("cb27new")
    reply = bytes.fromhex("2a000002810000365802030000000000")
    parser.feed(reply)
    assert (
        parser.state.head_intensity,
        parser.state.foot_intensity,
        parser.state.massage_wave,
        parser.state.massage_time,
    ) == (3, 0, 0, 0)


def test_p4_uses_cb24_receive_semantics_and_invalid_intensity_retains_previous():
    parser = Parser("cb24")
    parser.state.head_intensity = 2
    parser.feed(bytes.fromhex("a50b00000600030206000000000000000000000000"))
    assert parser.state.head_intensity == 2
    parser.feed(bytes.fromhex("a50c00008101233000010000000000000000000000"))
    assert parser.state.alarm_hour == 0x23
    assert parser.state.alarm_min == 0x30
