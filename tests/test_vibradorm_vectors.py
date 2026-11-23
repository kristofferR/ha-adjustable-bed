"""Every Vibradorm profile's frozen frames pass through the shared VMAT codec byte for byte."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.codec import vibradorm as codec
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.profiles import vibradorm as profiles
from custom_components.adjustable_bed.profiles import vmatbasic
from tests.test_controller_contract import _FactoryCoordinator, _make_connected_client
from tests.vibradorm_vectors import CBI, FROZEN, LIGHT, MOTOR, VALUE_FRAMES

TOGGLES = (0, codec.TOGGLE)


def _rebuild(role: str, frame: bytes) -> bytes:
    if role == MOTOR:
        assert len(frame) == 1
        return codec.motor(frame[0])
    if role == LIGHT:
        return codec.light(*codec.parse_light(frame))
    word = int.from_bytes(frame[:2], "big")
    return codec.command(word & ~codec.TOGGLE, frame[2:], word & codec.TOGGLE)


@pytest.mark.parametrize(
    ("role", "literal"),
    sorted(
        {
            *(
                (role, frame)
                for roles in FROZEN.values()
                for role, s in roles.items()
                for frame in s
            ),
            *((role, frame) for role, s in VALUE_FRAMES.items() for frame in s),
        }
    ),
)
def test_frozen_frame_round_trips_through_codec(role: str, literal: str) -> None:
    frame = bytes.fromhex(literal)
    assert _rebuild(role, frame) == frame


def _legacy() -> Iterator[tuple[str, bytes]]:
    p = profiles.LEGACY
    motors = (p.back_up, p.back_down, p.legs_up, p.legs_down, p.head_up, p.head_down)
    for code in (*motors, p.feet_up, p.feet_down, p.flat, *p.memory.values(), codec.STOP):
        yield MOTOR, codec.motor(code)
    yield LIGHT, codec.light(p.light_on, 0)
    yield LIGHT, codec.light(0, 0)
    words = [(p.store, b""), *((slot, b"") for slot in p.memory.values()), p.status_request]
    words += [(p.vibration, b"\x01"), (p.vibration, b"\x00")]
    for (word, parameters), toggle in ((w, t) for w in words for t in TOGGLES):
        yield CBI, codec.command(word, parameters, toggle)


def _app_layouts(app: str) -> Iterator[profiles.VibradormAppProfile]:
    if app == "vmat":
        for ordinal, r in profiles.VMAT_REMOTES.items():
            yield profiles.validate_vibradorm_app_profile(
                app,
                r.control_type,
                floor_light=r.floor_light,
                rgb=r.rgb,
                massage=r.massage,
                light_extension=r.light_extension,
                remote=ordinal,
            )
    elif app == "werkmeister":
        yield from (profiles.validate_vibradorm_app_profile(app, control) for control in (5, 7))
    else:
        for control in (-1, 0, 1, 2, 3, 4, 5, 6, 7, "other"):
            yield profiles.validate_vibradorm_app_profile(
                app, control, restored=True, floor_light=True, rgb=True, massage=True
            )


def _app(app: str) -> Iterator[tuple[str, bytes]]:
    """Held motors and memories, STOP, memory saves, sync, article, mood and massage-off."""
    for layout in _app_layouts(app):
        codes = [
            code
            for action, code in profiles.MOTORS.items()
            if action.startswith("all_")
            and layout.groups
            or action.rsplit("_", 1)[0] in layout.groups
        ] + list(profiles.MEMORY[: layout.memory_slots])
        if layout.basic:
            yield from ((MOTOR, codec.motor(code)) for code in (*codes, codec.STOP))
        else:
            yield from ((CBI, codec.command(code, toggle=t)) for code in codes for t in TOGGLES)
            yield CBI, codec.command(codec.STOP)
            if layout.memory_slots:
                yield from ((CBI, codec.command(profiles.STORE, toggle=t)) for t in TOGGLES)
                yield from ((CBI, codec.command(m)) for m in profiles.MEMORY[: layout.memory_slots])
        if layout.sync:
            replies = (profiles.SYNC_ACTIVE, profiles.SYNC_INACTIVE)
            yield from ((CBI, codec.command(*profiles.SYNC_REQUEST, t)) for t in TOGGLES)
            yield from ((CBI, codec.command(c, toggle=t)) for c in replies for t in TOGGLES)
        if layout.article_requests:
            yield CBI, profiles.ARTICLE_REQUEST
        if layout.rgb:
            word = profiles.MOOD if layout.basic else profiles.MOOD | profiles.EXTENSION
            palette = profiles.VMAT_MOOD_PALETTE if app == "vmat" else profiles.MOOD_PALETTE
            parameters = [b"\x01\x00" + bytes(color) for color in palette.values()]
            parameters += [bytes((8, index + 1)) for index in range(len(profiles.MOOD_EFFECTS))]
            yield from ((CBI, codec.command(word, p, t)) for p in parameters for t in TOGGLES)
            toggle_word = profiles.MOOD | profiles.EXTENSION
            yield from ((CBI, codec.command(toggle_word, toggle=t)) for t in TOGGLES)
        if layout.massage:
            word = (0 if layout.basic else profiles.EXTENSION) | profiles.MASSAGE_OFF
            yield from ((CBI, codec.command(word, b"\x00", t)) for t in TOGGLES)
    if app == "vmat":
        yield from ((CBI, stage[1]) for stage in profiles.VMAT_QUERY_STAGES)
        yield CBI, profiles.VMAT_CLOSE


def _vmatbasic(key: str) -> Iterator[tuple[str, bytes]]:
    """Held motors and STOP, the CBI floor-off frame and the XT-Box fixed commands."""
    for code in (*vmatbasic.MOTOR_ACTIONS.values(), codec.STOP):
        yield MOTOR, codec.motor(code)
    if key == "cbi":
        yield LIGHT, vmatbasic.floor(0, 0)
    if key == "xtbox":
        words = (vmatbasic.FLOOR, vmatbasic.MOOD, *vmatbasic.MASSAGE_ACTIONS.values())
        yield from ((CBI, codec.command(word)) for word in words)
        yield CBI, vmatbasic.rgb(0)
        yield from ((CBI, vmatbasic.effect(number)) for number in (1, 2, 3))


def _census(key: str) -> dict[str, frozenset[str]]:
    """Every fixed frame the profile can send, by role."""
    if key == profiles.LEGACY.key:
        frames = _legacy()
    elif key in vmatbasic.PROFILES:
        frames = _vmatbasic(key)
    else:
        frames = _app(key)
    by_role: dict[str, set[str]] = {}
    for role, frame in frames:
        by_role.setdefault(role, set()).add(frame.hex())
    return {role: frozenset(s) for role, s in by_role.items()}


@pytest.mark.parametrize("key", sorted(FROZEN))
def test_profile_sends_exactly_its_frozen_frames(key: str) -> None:
    assert _census(key) == FROZEN[key]


def test_profiles_cover_the_vectors() -> None:
    keys = {profiles.LEGACY.key, *vmatbasic.PROFILES, "caresse", "werkmeister", "vmat"}
    assert keys == set(FROZEN)


def test_vmatbasic_fixed_frames_are_its_artifact_vectors() -> None:
    packets = json.loads((Path(__file__).parent / "fixtures/vmatbasic-vectors.json").read_text())
    artifact = {p["expected"] for p in packets["packets"] if p["builder"] in ("motor", "literal")}
    fixed = {frame for key in vmatbasic.PROFILES for s in FROZEN[key].values() for frame in s}
    assert fixed == artifact


@pytest.mark.parametrize(
    ("frame", "expected"),
    [
        ("203f02000100020003000400", (0x02, bytes.fromhex("000100020003000400"))),
        ("3f40", (0x40, b"")),
        ("203f40", (0x40, b"")),
        ("203f", None),
        ("3f", None),
        ("20ef00", None),
        ("21a0c84142", None),
        ("", None),
    ],
)
def test_status_reply(frame: str, expected: tuple[int, bytes] | None) -> None:
    assert codec.status_reply(bytes.fromhex(frame)) == expected


def test_light_frame_and_its_status() -> None:
    assert codec.light(0xFF, 1439).hex() == "ff059f"
    assert codec.parse_light(bytes.fromhex("ff059f")) == (255, 1439)
    with pytest.raises(ValueError):
        codec.parse_light(b"\xff\x05")


@pytest.mark.parametrize(
    ("data", "text"),
    [
        (b"VMAT", "VMAT"),
        (b"A\xffB", "A\ufffdB"),
        (b"\xed\xa0\x80Z", "\ufffdZ"),
        (b" model \x00", " model \x00"),
    ],
)
def test_decode_text_matches_java_replacement(data: bytes, text: str) -> None:
    assert codec.decode_text(data) == text


async def test_vibradorm_drives_the_legacy_profile() -> None:
    controller = await create_controller(
        _FactoryCoordinator(), const.BED_TYPE_VIBRADORM, None, _make_connected_client()
    )
    assert getattr(controller, "profile", None) is profiles.LEGACY


@pytest.mark.parametrize(
    ("data", "key"),
    [
        (
            {const.CONF_VIBRADORM_APP_PROFILE: "caresse", const.CONF_VIBRADORM_CONTROL_TYPE: "2"},
            "caresse",
        ),
        (
            {
                const.CONF_VIBRADORM_APP_PROFILE: "werkmeister",
                const.CONF_VIBRADORM_CONTROL_TYPE: "7",
                const.CONF_VIBRADORM_FLOOR_LIGHT: True,
            },
            "werkmeister",
        ),
        (
            {
                const.CONF_VIBRADORM_APP_PROFILE: "vmat",
                const.CONF_VIBRADORM_CONTROL_TYPE: "8",
                const.CONF_VIBRADORM_VMAT_REMOTE: "07",
                const.CONF_VIBRADORM_FLOOR_LIGHT: True,
            },
            "vmat",
        ),
        *(({const.CONF_VMATBASIC_PROFILE: key}, key) for key in vmatbasic.PROFILES),
    ],
)
async def test_app_routes_drive_their_profile(data: dict[str, object], key: str) -> None:
    coordinator = _FactoryCoordinator()
    coordinator.entry.data.update(data)
    bed_type = (
        const.BED_TYPE_VMATBASIC
        if const.CONF_VMATBASIC_PROFILE in data
        else const.BED_TYPE_VIBRADORM_APP
    )
    controller = await create_controller(coordinator, bed_type, None, _make_connected_client())
    assert getattr(getattr(controller, "profile", None), "key", None) == key
