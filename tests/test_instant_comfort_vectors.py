"""All live Instant Comfort literal builders and channel parser boundaries."""

import pytest

from custom_components.adjustable_bed.codec import instant_comfort as pressure
from custom_components.adjustable_bed.codec import personal_comfort as codec
from custom_components.adjustable_bed.profiles.instant_comfort import MALOUF as PROFILE
from tests.instant_comfort_vectors import ANM3, MALOUF, REVERIE, V2, WAVES


@pytest.mark.parametrize(("args", "expected"), ANM3)
def test_anm3(args, expected):
    assert codec.anm3(*args).hex() == expected


@pytest.mark.parametrize(("action", "expected"), MALOUF.items())
def test_malouf(action, expected):
    code = (
        PROFILE.memory[int(action[-1]) - 1][int(action.startswith("save_"))]
        if action.startswith(("memory_", "save_"))
        else PROFILE.codes[action]
    )
    assert PROFILE.frame(code).hex() == expected


@pytest.mark.parametrize(("action", "expected"), REVERIE.items())
def test_reverie(action, expected):
    assert codec.base5(action).hex() == expected


@pytest.mark.parametrize(("action", "destination"), V2.items())
def test_v2(action, destination):
    prefix, expected = destination
    char, frame = codec.base6(action)
    assert char == codec.reverie_uuid(prefix)
    assert frame.hex() == expected


@pytest.mark.parametrize(("wave", "expected"), enumerate(WAVES, 1))
def test_waves(wave, expected):
    assert codec.base5("massage_mode", wave=wave).hex() == expected
    assert codec.base6("massage_mode", wave=wave) == (codec.reverie_uuid("db801080"), bytes([wave]))


def test_channel_and_air_frames():
    assert pressure.channel_target(0, 5).hex() == "433e534554503e303e300a"
    assert pressure.channel_target(3, 50).hex() == "433e534554503e333e36360a"
    assert codec.anm5("select").hex() == "433e545043483e300a"
    assert codec.anm5("query").hex() == "523e53500a"
    assert codec.anm5("stop").hex() == "433e53544f504e0a"
    assert codec.ra(5).hex() == "0a0f0f"
    assert codec.ra(50).hex() == "640f0f"
    assert codec.base6("light", light_on=True)[1].hex() == "64"
    assert codec.base6("light", light_on=False)[1].hex() == "00"
    for axis in ("pillow", "head", "feet"):
        assert codec.release_axis(axis) == (codec.reverie_uuid(codec.AXES[axis]), b"\0")


def test_channel_layout_parsing():
    two = pressure.parse_pressure(b"RET>SP>0000000042")
    assert two == pressure.PressureReply(0, (5, 50))
    four = pressure.parse_pressure(b"RBD>SP>00000000102142")
    assert four == pressure.PressureReply(0, (5, 15, 27, 50))
    assert four.main == codec.AirReply(0, 5, 27)
    assert pressure.parse_pressure(b"RET>SP>00000000102142" + b" " * 8) == four
    for packet in (b"RBD>SP>00", b"RET>SP>000000zz42", b"OTHER>SP>0000000042"):
        assert pressure.parse_pressure(packet) is None


@pytest.mark.parametrize(
    ("channel", "target", "expected"),
    [
        (0, 5, "433e534554503e303e300a"),
        (0, 50, "433e534554503e303e36360a"),
        (1, 5, "433e534554503e313e300a"),
        (1, 50, "433e534554503e313e36360a"),
        (2, 5, "433e534554503e323e300a"),
        (2, 50, "433e534554503e323e36360a"),
        (3, 5, "433e534554503e333e300a"),
        (3, 50, "433e534554503e333e36360a"),
    ],
)
def test_all_channel_boundaries(channel, target, expected):
    assert pressure.channel_target(channel, target).hex() == expected
