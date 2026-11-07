"""Every Kaidi profile's frozen frames pass through the shared mesh codec byte for byte."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import fields

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.codec import kaidi as codec
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.profiles import kaidi as profiles
from tests.kaidi_vectors import FROZEN_PAYLOADS, NOTIFICATIONS, SESSION_FRAMES
from tests.test_controller_contract import _FactoryCoordinator, _make_connected_client

BUILDERS: dict[str, Callable[..., bytes]] = {
    "join": codec.join,
    "enroll": codec.enroll,
    "ping": codec.ping,
    "control": codec.control,
}


@pytest.mark.parametrize(
    ("key", "literal"),
    [(key, literal) for key, frames in FROZEN_PAYLOADS.items() for literal in sorted(frames)],
)
def test_frozen_payload_round_trips_through_codec(key: str, literal: str) -> None:
    data = bytes.fromhex(literal)
    assert codec.payload(data[1], data[2]) == data
    assert codec.control(0x01020304, codec.BROADCAST, data[1], data[2])[10:] == data


@pytest.mark.parametrize(("builder", "args", "frame"), SESSION_FRAMES)
def test_session_frames(builder: str, args: tuple[int, ...], frame: str) -> None:
    assert BUILDERS[builder](*args).hex() == frame


def test_signed_addresses_are_java_ints() -> None:
    # Floyd keeps a ping's signed address; tests/test_floyd.py sends to -3.
    assert codec.control(-3, 0, 0x1C)[1:5] == bytes.fromhex("fdffffff")
    with pytest.raises(OverflowError):
        codec.control(1 << 32, 0, 0x1C)


def _seat_census(profile: profiles.KaidiCommandProfile) -> set[int]:
    values = {*profile.memory_save.values(), *profile.memory_recall.values()}
    for f in fields(profiles.KaidiCommandProfile):
        if isinstance(value := getattr(profile, f.name), int):
            values.add(value)
    return values


def _census(key: str) -> set[str]:
    """Every fixed payload the profile can send, with dynamic parameters at zero."""
    if key == profiles.FLOYD.key:
        floyd = profiles.FLOYD
        commands = _seat_census(floyd) | {floyd.confirm_add}
        commands |= {code for pair in floyd.holds.values() for code in pair}
        commands |= {code for side in floyd.presets.values() for code in side.values()}
        payloads = {codec.payload(code) for code in commands}
        payloads |= {codec.payload(floyd.save_preset, p) for p in floyd.save_parameters.values()}
        return {payload.hex() for payload in payloads}
    if key == profiles.IsleepProfile.key:
        commands = {code for lanes in profiles.ISLEEP_COMMANDS.values() for code in lanes}
        commands.add(profiles.IsleepProfile.enroll_ack)
    else:
        commands = _seat_census(profiles.SEAT_PROFILES[key])
    return {codec.payload(code).hex() for code in commands}


@pytest.mark.parametrize("key", sorted(FROZEN_PAYLOADS))
def test_profile_sends_exactly_its_frozen_payloads(key: str) -> None:
    assert _census(key) == FROZEN_PAYLOADS[key]


def test_profiles_cover_the_vectors() -> None:
    keys = {*profiles.SEAT_PROFILES, profiles.FLOYD.key, profiles.IsleepProfile.key}
    assert keys == set(FROZEN_PAYLOADS)


def test_seat_1_2_sends_seat_1_then_seat_2() -> None:
    primary = {codec.payload(code).hex() for code in profiles.SEAT_1_2_SECONDARY}
    secondary = {codec.payload(code).hex() for code in profiles.SEAT_1_2_SECONDARY.values()}
    assert primary <= FROZEN_PAYLOADS["seat_1_2"]
    assert secondary <= FROZEN_PAYLOADS["seat_2"]


@pytest.mark.parametrize(
    ("frame", "expected"),
    [
        ("021600", codec.JoinReply(0)),
        ("021601", codec.JoinReply(1)),
        ("0216", codec.JoinReply(None)),
        ("020300", codec.EnrollReply(0)),
        ("010a01000000", codec.OwnAddress(1)),
        ("010a00000000", codec.OwnAddress(0)),
        ("010aefcdab90", codec.OwnAddress(0x90ABCDEF)),
        ("01020000000000000100", codec.RosterChange(1)),
        ("0300000000ffffeeddccbbaa04030201", codec.PingReply("AA:BB:CC:DD:EE:FF", 0x01020304)),
        ("0300000000ffffeeddccbbaafdffffff", codec.PingReply("AA:BB:CC:DD:EE:FF", 0xFFFFFFFD)),
        ("0300000000ff00112233445501000000", codec.PingReply("55:44:33:22:11:00", 1)),
        ("0300000000200403020101a60100", codec.ControlReply(0xA6, 1)),
        ("0300000000200403020101a60000", codec.ControlReply(0xA6, 0)),
        ("0203", None),
        ("010a000000", None),
        ("010200000000000001", None),
        ("0300000000ffffeeddccbbaa040302", None),
        ("0300000000200403020101a601", None),
    ],
)
def test_notifications(frame: str, expected: codec.Notification | None) -> None:
    assert codec.parse_notification(bytes.fromhex(frame)) == expected


def test_notification_vectors_are_parsed() -> None:
    assert all(codec.parse_notification(bytes.fromhex(frame)) for frame in NOTIFICATIONS)
    assert codec.PingReply("", 0xFFFFFFFD).signed_vaddr == -3


@pytest.mark.parametrize(
    ("variant", "profile"),
    [
        *((key, profile) for key, profile in profiles.SEAT_PROFILES.items()),
        (const.KAIDI_VARIANT_FLOYD, profiles.FLOYD),
    ],
)
async def test_kaidi_routes_drive_their_profile(
    variant: str, profile: profiles.KaidiCommandProfile
) -> None:
    controller = await create_controller(
        _FactoryCoordinator(), const.BED_TYPE_KAIDI, variant, _make_connected_client()
    )
    assert getattr(controller, "profile", None) is profile


async def test_isleep_drives_its_profile() -> None:
    coordinator = _FactoryCoordinator()
    coordinator.entry.data.update({const.CONF_PRODUCT_TYPE: 143, const.CONF_KAIDI_ROOM_ID: -1})
    controller = await create_controller(
        coordinator, const.BED_TYPE_ISLEEP, None, _make_connected_client()
    )
    assert getattr(controller, "profile", None) == profiles.IsleepProfile(143, -1, 2)
