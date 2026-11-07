"""The frozen JMC400 frames pass through the codec byte for byte."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.jensen import JensenController
from custom_components.adjustable_bed.codec import jmc
from custom_components.adjustable_bed.profiles.jmc import JENSEN, PROFILES, SVANE_REMOTE, JmcProfile
from custom_components.adjustable_bed.svane_state import svane_preferences
from tests.jmc_vectors import FROZEN_FRAMES, FROZEN_REPORTS
from tests.test_controller_contract import _create_controller_for_bed_type

ROOT = Path(__file__).parents[1]
assert JENSEN.fan is not None
JENSEN_FAN: bytes = JENSEN.fan


def _rebuild(frame: bytes, profile: JmcProfile) -> bytes:
    """Decode one frame by its opcode and encode it again with the profile's bytes."""
    opcode, rest = frame[0], frame[1:]
    if frame == jmc.CONFIG_REQUEST:
        return jmc.CONFIG_REQUEST
    if opcode == jmc.PIN:
        return jmc.pin("".join(str(digit) for digit in rest))
    if opcode == jmc.MOTION and rest[0] == jmc.GOTO:
        return jmc.goto(rest[1:])
    if opcode == jmc.MOTION:
        return jmc.command(rest[0])
    if opcode == jmc.MASSAGE:
        return jmc.massage(*rest[:3])
    if opcode == jmc.LIGHT:
        off = rest[1] == 0 and rest[2:] == profile.light_off
        return jmc.light(rest[1], profile.light_off if off else profile.light_on)
    if opcode == jmc.FAN and profile.fan is not None:
        return jmc.fan(rest[0], profile.fan)
    raise AssertionError(f"{profile.key} froze an unknown frame {frame.hex()}")


@pytest.mark.parametrize(
    ("key", "literal"),
    [(key, literal) for key, frames in FROZEN_FRAMES.items() for literal in sorted(frames)],
)
def test_frozen_frame_round_trips_through_codec(key: str, literal: str) -> None:
    frame = bytes.fromhex(literal)
    assert _rebuild(frame, PROFILES[key]) == frame


def test_the_vectors_cover_every_profile() -> None:
    assert FROZEN_FRAMES.keys() == PROFILES.keys()


def _fixed_frames(key: str) -> set[bytes]:
    """Every frame the profile's controller sends without a runtime value."""
    profile = PROFILES[key]
    axes = (True, False, None)
    frames = {jmc.motion(head, foot) for head in axes for foot in axes}
    frames |= {jmc.command(jmc.FLAT), jmc.light(0, profile.light_off)}
    if profile is JENSEN:
        frames |= {
            jmc.CONFIG_REQUEST,
            jmc.pin(JensenController.DEFAULT_PIN),
            jmc.command(jmc.POSITION_QUERY),
            jmc.command(jmc.MEMORY_SAVE),
            jmc.command(jmc.MEMORY_RECALL),
            jmc.massage(0, 0, 0),
            # Levels clamp to 0-10, so every light and fan frame is fixed.
            *(jmc.light(level, profile.light_on) for level in range(1, 11)),
            *(jmc.fan(level, JENSEN_FAN) for level in range(11)),
        }
    else:
        # The Read and TV slots before a save.
        frames |= {jmc.goto(slot) for slot in svane_preferences(None)[1]}
    return frames


@pytest.mark.parametrize("key", sorted(PROFILES))
def test_each_profile_sends_only_frozen_fixed_frames(key: str) -> None:
    sent = {frame.hex() for frame in _fixed_frames(key)}
    assert sent <= FROZEN_FRAMES[key], sorted(sent - FROZEN_FRAMES[key])


@pytest.mark.parametrize(
    ("bed_type", "key", "lamp"),
    [
        (const.BED_TYPE_JENSEN, "jensen", False),
        # Both Svane Remote routes send the profile's lamp frames.
        (const.BED_TYPE_SVANE, "svane_remote", True),
    ],
)
def test_the_snapshot_routes_send_only_frozen_frames(bed_type: str, key: str, lamp: bool) -> None:
    """Every JMC400 write the wire snapshot records is a frozen frame of its profile."""
    scenarios = json.loads((ROOT / "tests/fixtures/wire_snapshot.json").read_text())["scenarios"]
    writes = {
        write[3]
        for sid, scenario in scenarios.items()
        if sid.split(":")[0] == bed_type and not sid.endswith(":jensen_linon")
        for command in scenario["commands"].values()
        for write in command.get("writes", ())
        if write[3] and (write[1] == "00001111" or (lamp and write[3].startswith("1302")))
    }
    assert writes and writes <= FROZEN_FRAMES[key], sorted(writes - FROZEN_FRAMES[key])


# Frames of the pre-v5 tests, from the inputs that built them.
@pytest.mark.parametrize(
    ("frame", "expected"),
    [
        (jmc.pin("3060"), "1e03000600"),
        (jmc.CONFIG_REQUEST, "0a00000000"),
        (jmc.command(jmc.STOP), "100000000000"),
        (jmc.motion(None, None), "100000000000"),
        (jmc.motion(True, None), "100100000000"),
        (jmc.motion(False, None), "100200000000"),
        (jmc.motion(None, True), "101000000000"),
        (jmc.motion(None, False), "102000000000"),
        (jmc.motion(True, True), "101100000000"),
        (jmc.motion(True, False), "102100000000"),
        (jmc.motion(False, True), "101200000000"),
        (jmc.motion(False, False), "102200000000"),
        (jmc.command(jmc.FLAT), "108100000000"),
        (jmc.command(jmc.MEMORY_SAVE), "104000000000"),
        (jmc.command(jmc.MEMORY_RECALL), "108000000000"),
        # The #631 capture's Memory 1 recall: head 30771, foot 30000.
        (jmc.goto(jmc.position(30771, 30000)), "100433783075"),
        # The #631 capture's massage sweep: head 6, wave 6.
        (jmc.massage(6, 0, 6), "120600060000"),
        (jmc.massage(0, 0, 0), "120000000000"),
        (jmc.light(4, JENSEN.light_on), "130204000000"),
        # 2.0.37 vector TV078.
        (jmc.light(0, JENSEN.light_off), "130200000032"),
        (jmc.fan(4, JENSEN_FAN), "140400000050"),
        (jmc.fan(0, JENSEN_FAN), "140000000050"),
        (jmc.goto(bytes.fromhex("81388113")), "100481388113"),
        (jmc.light(90, SVANE_REMOTE.light_on), "13025a010064"),
        (jmc.light(0, SVANE_REMOTE.light_off), "130200000000"),
    ],
)
def test_frame_is_built_from_its_inputs(frame: bytes, expected: str) -> None:
    assert frame.hex() == expected


def test_motion_rejects_a_non_boolean_axis() -> None:
    with pytest.raises(ValueError, match="boolean"):
        jmc.motion(1, None)  # type: ignore[arg-type]


def test_goto_needs_four_position_bytes() -> None:
    with pytest.raises(ValueError, match="four bytes"):
        jmc.goto(b"\x81\x38")


@pytest.mark.parametrize("literal", sorted(FROZEN_REPORTS))
def test_frozen_report_decodes(literal: str) -> None:
    """A position report keeps its state and four bytes; a config report is not one."""
    data = bytes.fromhex(literal)
    report = jmc.position_report(data)
    if data[0] == jmc.CONFIG:
        assert report is None
    else:
        assert report == jmc.PositionReport(data[1], data[2:6])


def test_position_bytes_read_as_head_and_foot() -> None:
    assert jmc.head_foot(bytes.fromhex("30753075")) == (30000, 30000)
    assert jmc.position(*jmc.head_foot(bytes.fromhex("33783075"))) == bytes.fromhex("33783075")


@pytest.mark.parametrize("data", ["", "10ff307530", "0a0503080175", "1e01"])
def test_other_notifications_are_not_position_reports(data: str) -> None:
    assert jmc.position_report(bytes.fromhex(data)) is None


@pytest.mark.parametrize("module", ["jensen", "svane"])
def test_the_controllers_build_no_jmc_frame_of_their_own(module: str) -> None:
    source = (ROOT / f"custom_components/adjustable_bed/beds/{module}.py").read_text()
    assert not re.search(r"bytes\(\s*[\[(]\s*0x(?:0a|1[0-4e])\b", source, re.I)
    assert not re.search(r"""["'](?:0a|1[0-4e])[0-9a-f]{8,10}["']""", source, re.I)


async def test_jensen_drives_its_profile() -> None:
    controller = await _create_controller_for_bed_type(const.BED_TYPE_JENSEN)
    assert getattr(controller, "profile", None) is JENSEN
