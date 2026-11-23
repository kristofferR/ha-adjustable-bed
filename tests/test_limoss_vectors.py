"""Every Limoss profile's frozen frames pass through the shared codec byte for byte."""

from __future__ import annotations

import pytest

from custom_components.adjustable_bed.codec import limoss as codec
from custom_components.adjustable_bed.profiles import limoss as profiles
from tests.limoss_vectors import FROZEN_BODIES, REMOTE_LAYOUTS, WIRE_FRAMES

_ZERO_FLAGS = (False, False, False, False)


def _census(profile: profiles.LimossProfile) -> set[str]:
    """Every fixed body the profile can send, with dynamic fields at zero."""
    bodies = {codec.release(profile.stop.opcode, _ZERO_FLAGS)}
    for index in range(1, 5):
        bodies |= {codec.ask_position(index), codec.set_position(index, 0)}
    if profile is profiles.LEGACY:
        bodies |= {codec.body(codec.motor(i, up)) for i in range(1, 5) for up in (True, False)}
        bodies |= {codec.body(op) for op in (codec.FLAT, codec.LIGHT, *codec.MASSAGE_ZONES)}
        bodies.add(codec.query(codec.QUERY_CAPABILITIES))
        return {item.hex() for item in bodies}
    for layout in profile.layouts.values():
        bodies |= {codec.flagged(op, _ZERO_FLAGS) for op in layout if op is not None}
    bodies |= {
        codec.query(op)
        for op in (codec.QUERY_HARDWARE, codec.QUERY_SOFTWARE, codec.QUERY_CAPABILITIES)
    }
    if profile.recall_release is not None:
        bodies.add(codec.release(profile.recall_release.opcode, _ZERO_FLAGS))
    if profile.calibration is not None:
        bodies.add(codec.flagged(codec.CALIBRATE, _ZERO_FLAGS))
        if profile.calibration.release is not None:
            bodies.add(codec.release(profile.calibration.release.opcode, _ZERO_FLAGS))
    if profile.feature_off_frames:
        bodies |= {codec.body(codec.LIGHT_OFF), codec.body(codec.MASSAGE_OFF)}
    return {item.hex() for item in bodies}


@pytest.mark.parametrize(
    ("body", "counter", "wire"),
    [row for rows in WIRE_FRAMES.values() for row in rows],
)
def test_frozen_frame_round_trips_through_codec(body, counter, wire):
    data, packet = bytes.fromhex(body), bytes.fromhex(wire)
    assert codec.frame(data, counter) == packet
    assert codec.decode(packet) == data
    assert codec.StreamParser(verify=False).feed(packet) == [data]
    assert codec.StreamParser(verify=True).feed(packet) == [data]


@pytest.mark.parametrize("key", sorted(profiles.PROFILES))
def test_profile_sends_only_frozen_bodies(key):
    census = _census(profiles.PROFILES[key])
    assert census <= FROZEN_BODIES[key]
    if key == "legacy":
        # Without a report, the pre-v5 controller's bodies are the complete set.
        assert census == FROZEN_BODIES[key]


@pytest.mark.parametrize(
    ("built", "literal"),
    [
        # Reversal flags and raw positions land in the parameter bytes.
        (codec.flagged(0x13, (True, False, False, False)), "1301000000"),
        (codec.flagged(codec.CALIBRATE, (True, False, True, False)), "0501000100"),
        (codec.flagged(0x12, (True, True, False, False)), "1201010000"),
        (codec.set_position(2, 0x12345678), "2112345678"),
        (codec.set_position(1, -(2**31)), "1180000000"),
        (codec.set_position(1, 0x3E80, signed=False), "1100003e80"),
        (codec.set_position(4, 0xFFFFFFFF, signed=False), "41ffffffff"),
    ],
)
def test_dynamic_fields_match_frozen_vectors(built, literal):
    assert built.hex() == literal
    assert any(row[0] == literal for rows in WIRE_FRAMES.values() for row in rows)


def test_remote_layouts_match_the_independent_fixture():
    assert profiles.LIMOSS_REMOTE.layouts == REMOTE_LAYOUTS


def test_invalid_frames_are_rejected_only_when_verified():
    body, _counter, wire = WIRE_FRAMES["fsm_relax"][0]
    packet = bytearray.fromhex(wire)
    packet[-1] ^= 0xFF
    assert codec.decode(bytes(packet)) is None
    assert codec.StreamParser(verify=True).feed(bytes(packet)) == []
    # Limoss Remote checks neither checksum.
    assert codec.StreamParser(verify=False).feed(bytes(packet)) == [bytes.fromhex(body)]
