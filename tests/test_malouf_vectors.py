"""Every Malouf profile's frozen frames pass through the shared codec byte for byte."""

from __future__ import annotations

from datetime import datetime

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.codec import malouf as codec
from custom_components.adjustable_bed.const import VARIANT_AUTO
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.profiles.malouf import (
    APP_PROFILES,
    NEW_OKIN,
    MaloufAppProfile,
    MaloufRouteProfile,
    SaveWords,
)
from tests.malouf_vectors import FROZEN_FRAMES
from tests.test_controller_contract import _FactoryCoordinator, _make_connected_client

PROFILES: dict[str, MaloufAppProfile | MaloufRouteProfile] = {
    NEW_OKIN.key: NEW_OKIN,
    **APP_PROFILES,
}


def _decode(data: bytes) -> tuple[codec.TransportKey, int, int]:
    """The transport, value and selector a frame's layout implies."""
    if len(data) == 1:
        return "richmat_single", data[0], 0
    if len(data) == 5 and data[:2] == b"\x6e\x01":
        return "richmat_framed", data[3], data[2]
    if len(data) == 9 and data[:3] == b"\xe6\xfe\x16":
        return "okin_legacy", int.from_bytes(data[3:7], "little"), 0
    if len(data) == 10 and data[:2] == b"\x04\x02":
        return "okin_custom", int.from_bytes(data[2:6], "big"), 0
    if len(data) == 8 and data[:2] == b"\x05\x02":
        return "okin_new", int.from_bytes(data[2:6], "big"), 0
    raise AssertionError(f"no Malouf frame layout matches {data.hex()}")


@pytest.mark.parametrize(
    ("profile", "literal"),
    [(profile, literal) for profile, frames in FROZEN_FRAMES.items() for literal in sorted(frames)],
)
def test_frozen_frame_round_trips_through_codec(profile: str, literal: str) -> None:
    data = bytes.fromhex(literal)
    if data == codec.STATUS_QUERY:
        return
    transport, value, selector = _decode(data)
    assert codec.command(transport, value, selector=selector) == data


def _save_words(words: SaveWords) -> set[int]:
    return {*words.slots.values(), words.smartbed238_slot_1}


def _census(profile: MaloufAppProfile | MaloufRouteProfile) -> set[str]:
    if isinstance(profile, MaloufRouteProfile):
        words = {*profile.words.values(), *_save_words(profile.save_words)}
        return {codec.command(profile.transport, word).hex() for word in words}
    census: set[str] = set()
    for transport, route in profile.routes.items():
        if codec.TRANSPORTS[transport].family == "richmat":
            for action, code in profile.richmat.items():
                selectors = (0, 1) if action in profile.selector_actions else (0,)
                census |= {codec.command(transport, code, selector=s).hex() for s in selectors}
            continue
        words = {*profile.okin.values(), *_save_words(profile.save_words)}
        census |= {codec.command(transport, word).hex() for word in words}
        if route.status_query:
            census.add(codec.STATUS_QUERY.hex())
    return census


@pytest.mark.parametrize("key", sorted(PROFILES))
def test_profile_sends_exactly_its_frozen_frames(key: str) -> None:
    # Every reachable report literal is sendable, and the pre-v5 route is complete.
    assert _census(PROFILES[key]) == FROZEN_FRAMES[key]


def test_profiles_cover_the_vectors() -> None:
    assert set(PROFILES) == set(FROZEN_FRAMES)


# Parameterized frames from the reports' test vectors not already in the app tests:
# Lucid Base 1.3.3 p1-legacy-alarm, p1-new-alarm and p1-legacy-current-time.
@pytest.mark.parametrize(
    ("frame", "expected"),
    [
        (codec.alarm("okin_legacy", 7, 30, 13, 0x3E), "ed8003071e3e0d00000000000000001f"),
        (codec.alarm("okin_new", 7, 30, 16, 0x82), "07050304071e000100"),
        (codec.clock("okin_legacy", datetime(2026, 8, 27, 12, 34, 56)), "e780017e071b0c223891"),
    ],
)
def test_lucid_parameterized_vectors(frame: bytes, expected: str) -> None:
    assert frame.hex() == expected


async def test_new_okin_route_drives_its_profile() -> None:
    controller = await create_controller(
        _FactoryCoordinator(),
        const.BED_TYPE_MALOUF_NEW_OKIN,
        VARIANT_AUTO,
        _make_connected_client(),
    )
    assert getattr(controller, "profile", None) is NEW_OKIN
