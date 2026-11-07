"""The Casper Base report's frozen frames pass through the Richmat codec byte for byte."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.profiles import casper as library
from custom_components.adjustable_bed.profiles.casper import ACTIONS, PROFILES, CasperProfile
from tests import casper_base_vectors, hush_vectors
from tests.casper_base_vectors import FROZEN_FRAMES, SHARED_FRAMES
from tests.casper_frames import rebuild
from tests.test_controller_contract import _FactoryCoordinator, _make_connected_client

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests/fixtures/casper_base"
ALL_FRAMES = SHARED_FRAMES.union(*FROZEN_FRAMES.values())


def _report_frames() -> tuple[set[str], set[int]]:
    """The report's sent bed frames, and the opcodes of its per-side command template."""
    builders = json.loads((FIXTURES / "builders.json").read_text())
    literals = {v["expected_bytes"] for v in builders if v["protocol"] in ("P1", "P2")}
    templated: set[int] = set()
    for entry in json.loads((FIXTURES / "ledger.json").read_text())["entries"]:
        if entry["domain"] != "command" or entry["evidence"]["protocol"] not in ("P1", "P2"):
            continue
        text = entry["behavior"]["bytes"]
        if re.fullmatch(r"(?:[0-9a-f]{2} ?)+", text):
            literals.add(text.replace(" ", ""))
        elif match := re.fullmatch(r"6e 01 s ([0-9a-f]{2}) sum8\(6e,01,s,\1\)", text):
            templated.add(int(match[1], 16))
    return literals, templated


@pytest.mark.parametrize("literal", sorted(ALL_FRAMES))
def test_frozen_frame_round_trips_through_codec(literal):
    frame = bytes.fromhex(literal)
    assert rebuild(frame) == frame


def test_the_vectors_are_the_reports_sent_frames():
    """Every report literal is frozen; the rest are its side-0 command template."""
    literals, templated = _report_frames()
    assert literals <= ALL_FRAMES, sorted(literals - ALL_FRAMES)
    for literal in ALL_FRAMES - literals:
        head, side, opcode = bytes.fromhex(literal)[:2], literal[4:6], int(literal[6:8], 16)
        assert head == b"\x6e\x01" and side == "00" and opcode in templated, literal
        assert literal == bytes((0x6E, 1, 0, opcode, (0x6F + opcode) & 255)).hex()


def test_the_vectors_cover_the_apps_own_products():
    assert set(FROZEN_FRAMES) == {key for key, profile in PROFILES.items() if profile.current}


@pytest.mark.parametrize("key", sorted(FROZEN_FRAMES))
def test_each_product_sends_its_catalog_opcodes(key):
    """STOP and every short or long opcode of the product's controls, on both transports."""
    row = PROFILES[key].row
    opcodes = {codec.STOP} | {
        opcode
        for group in row[1:6]
        for index in group
        for opcode in ACTIONS[index][1:]
        if opcode is not None
    }
    commands = {
        codec.function(op, single=single).hex() for op in opcodes for single in (True, False)
    }
    queries = {
        codec.function(code, action=action, single=single).hex()
        for action, code in library.QUERIES
        for single in (True, False)
    }
    sent = commands | queries
    assert sent <= FROZEN_FRAMES[key], sorted(sent - FROZEN_FRAMES[key])


@pytest.mark.parametrize("vectors", [casper_base_vectors, hush_vectors], ids=["casper", "hush"])
@pytest.mark.parametrize(
    "opcode", [codec.STOP, library.LIGHT_OFF, library.ANTI_SNORE, library.MUSIC_BLUETOOTH]
)
def test_the_librarys_fixed_commands_are_frozen_in_both_apps(vectors, opcode):
    frozen = vectors.SHARED_FRAMES.union(*vectors.FROZEN_FRAMES.values())
    for single in (True, False):
        assert codec.function(opcode, single=single).hex() in frozen


def test_the_snapshot_route_sends_only_its_products_frames():
    """Every write the wire snapshot records for the default PRO route is frozen."""
    scenarios = json.loads((ROOT / "tests/fixtures/wire_snapshot.json").read_text())["scenarios"]
    writes = {
        write[3]
        for sid, scenario in scenarios.items()
        if sid.split(":")[0] == const.BED_TYPE_CASPER_BASE
        for command in scenario["commands"].values()
        for write in command.get("writes", ())
        if write[3]
    }
    assert writes and writes <= FROZEN_FRAMES["casperpro"], sorted(
        writes - FROZEN_FRAMES["casperpro"]
    )


def test_the_controller_builds_no_frame_of_its_own():
    source = (ROOT / "custom_components/adjustable_bed/beds/casper_base/controller.py").read_text()
    assert not re.search(r"""b["']\\x6e|bytes\(\(0x6E""", source, re.I)


async def test_the_route_drives_its_profile():
    controller = await create_controller(
        _FactoryCoordinator(), const.BED_TYPE_CASPER_BASE, "casperpro", _make_connected_client()
    )
    profile = getattr(controller, "profile", None)
    assert isinstance(profile, CasperProfile) and profile is PROFILES["casperpro"]
