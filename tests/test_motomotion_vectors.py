"""The MotoMotion report's frozen frames pass through its codec byte for byte."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.codec import motomotion as codec
from custom_components.adjustable_bed.const import VARIANT_AUTO
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.profiles.motomotion import PROFILE_KEY, Profile
from tests.motomotion_vectors import FROZEN_FRAMES, REPORT_VECTORS
from tests.test_controller_contract import _FactoryCoordinator, _make_connected_client

_ASCII = re.compile(rb"\$#(\d{5})(\d{5})\d{5}R\r")
_MUSIC = re.compile(rb"\$#([MTBV])(\d{2})\r")


def _rebuild(frame: bytes) -> bytes:
    """Decode one frame by its form and encode it again through the codec."""
    if (match := _ASCII.fullmatch(frame)) is not None:
        return codec.ascii_command(int(match[1]), int(match[2]))
    if (match := _MUSIC.fullmatch(frame)) is not None:
        return codec.music_command(match[1].decode(), int(match[2]))
    if frame.startswith(b"$#") and frame.endswith(b"A\r") and len(frame) == 9:
        return codec.binary_command(
            int.from_bytes(frame[2:4], "big"), int.from_bytes(frame[4:6], "big")
        )
    if frame.startswith(b"AIOK") and frame.endswith(b"R\r") and len(frame) == 16:
        head, lumbar, back, base, tilt = (
            int.from_bytes(frame[i : i + 2], "big") for i in range(4, 14, 2)
        )
        return codec.Position(head=head, base=base, back=back, lumbar=lumbar, tilt=tilt).to_bytes()
    return codec.binding_code(frame)


@pytest.mark.parametrize("literal", sorted(FROZEN_FRAMES[PROFILE_KEY]))
def test_frozen_frame_round_trips_through_codec(literal):
    frame = bytes.fromhex(literal)
    assert _rebuild(frame) == frame


# The report vectors whose inputs are the frame's own fields.
@pytest.mark.parametrize(
    ("vector", "frames"),
    [
        ("a-left", (codec.ascii_command(1, 0),)),
        ("a-right-save", (codec.ascii_command(263, 10000),)),
        ("a-unpair", (codec.UNPAIR,)),
        ("a-right-red", (codec.ascii_command(315, 10120),)),
        ("b-save", (codec.binary_command(33050, 0),)),
        ("b-vol", (codec.binary_command(9, 63),)),
        ("b-treble", (codec.binary_command(1, 31),)),
        (
            "c-mode",
            tuple(
                codec.music_command(letter, v)
                for letter, v in zip("MTBV", (8, 10, 5, 5), strict=True)
            ),
        ),
        ("d-order", (codec.Position(head=1, base=2, back=3, lumbar=4, tilt=5).to_bytes(),)),
        (
            "d-clamp",
            (codec.Position(head=-1, base=65536, back=0, lumbar=65535, tilt=0).to_bytes(),),
        ),
        ("e-bind", (codec.binding_code((0, 1, 2, 3, 127, 128, 253, 254)),)),
    ],
)
def test_report_vector_is_built_from_its_inputs(vector, frames):
    assert tuple(frame.hex() for frame in frames) == REPORT_VECTORS[vector]


def test_binding_codes_stay_in_the_apps_range():
    with pytest.raises(ValueError):
        codec.binding_code((0, 1, 2, 3, 4, 5, 6, 255))
    with pytest.raises(ValueError):
        codec.binding_code((0, 1, 2))


def test_the_controller_builds_no_frame_of_its_own():
    source = (
        Path(__file__).parents[1] / "custom_components/adjustable_bed/beds/motomotion.py"
    ).read_text()
    assert not re.search(r"""b["'](\$|AIOK)""", source)


async def test_the_route_drives_its_profile():
    coordinator = _FactoryCoordinator()
    # The stored exact name selects the panel; panel One here.
    coordinator.entry.data[const.CONF_BLE_DEVICE_NAME] = "SOFA000001MC00H"
    controller = await create_controller(
        coordinator, const.BED_TYPE_MOTOMOTION, VARIANT_AUTO, _make_connected_client()
    )
    profile = getattr(controller, "profile", None)
    assert isinstance(profile, Profile) and profile.key == PROFILE_KEY
