"""Renewable holds (#483) on the Jiecang codec: the Dream apps and LOGICDATA.

Only the profiles whose accepted reports stream a held frame until release
declare ``hold="stream"``. Their leased hold refreshes the app's own motion
frame at the app's own cadence and ends with the app's own release schedule.
The lease tests run each real controller on virtual time.
"""

from __future__ import annotations

import asyncio
from dataclasses import astuple
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.beds.jiecang_app import JiecangAppController
from custom_components.adjustable_bed.beds.logicdata_app import LogicdataAppController
from custom_components.adjustable_bed.codec.jiecang import TRANSPORTS
from custom_components.adjustable_bed.execution import STREAM_HOLD
from custom_components.adjustable_bed.profiles import jiecang, logicdata
from tests.hold_lease_wire import intervals, leased_hold
from tests.jiecang_vectors import FROZEN_FRAMES as JIECANG_FRAMES
from tests.logicdata_vectors import FROZEN_FRAMES as LOGICDATA_FRAMES

JIECANG_STREAM = ("dreamask", "dreamotion", "dreamhd")
LOGICDATA_STREAM = ("phone", "tablet", "sleep_smart")
CASES = [("jiecang", key) for key in JIECANG_STREAM] + [
    ("logicdata", key) for key in LOGICDATA_STREAM
]
# Back up in the standard two-motor layout, on every declared profile.
HELD = "f1f1010101037e"
END_AFTER_S = 5


def test_only_the_stream_rows_declare_a_hold() -> None:
    """Comfort Motion (report PARTIAL) and the legacy route stay finite."""
    jiecang_profiles = {"legacy": jiecang.LEGACY, **jiecang.APP_PROFILES}
    assert {key for key, p in jiecang_profiles.items() if p.execution.hold} == set(JIECANG_STREAM)
    assert {key for key, p in logicdata.APP_PROFILES.items() if p.execution.hold} == set(
        LOGICDATA_STREAM
    )
    for profile in (*jiecang.APP_PROFILES.values(), *logicdata.APP_PROFILES.values()):
        assert profile.execution in (STREAM_HOLD, jiecang.LEGACY.execution)


@pytest.mark.parametrize("key", JIECANG_STREAM)
def test_jiecang_held_and_release_frames_are_frozen(key: str) -> None:
    profile = jiecang.APP_PROFILES[key]
    held = {
        jiecang.motion_command(profile, layout, axis, up).hex()
        for layout, axes in profile.layouts.items()
        for axis in axes
        for up in (True, False)
    }
    releases = {command.hex() for _, command in profile.hold.releases}
    assert held | releases <= JIECANG_FRAMES[key]


@pytest.mark.parametrize("key", LOGICDATA_STREAM)
def test_logicdata_held_and_release_frames_are_frozen(key: str) -> None:
    profile = logicdata.APP_PROFILES[key]
    held = set()
    for family in logicdata.FAMILIES:
        for layout, axes in profile.layouts.items():
            try:
                logicdata.validate_setup(profile, family, layout)
            except ValueError:
                continue
            held |= {
                logicdata.motion_command(profile, family, layout, axis, up).hex()
                for axis in axes
                for up in (True, False)
            }
    releases = {command.hex() for _, command in profile.touch_release}
    assert held and held | releases <= LOGICDATA_FRAMES[key]


class _Services(SimpleNamespace):
    """A GATT service collection: lookups by UUID, iteration over services."""

    def __init__(self, services: list[SimpleNamespace], **lookups: object) -> None:
        super().__init__(**lookups)
        self._services = services

    def __iter__(self):
        return iter(self._services)


def _jiecang(coordinator: Any, key: str) -> tuple[BedController, Any, bytes, list[bytes]]:
    service_uuid, write, notify, name = astuple(TRANSPORTS["g1"])
    members = {
        uuid: SimpleNamespace(uuid=uuid, properties=["write", "notify"])
        for uuid in (write, notify, name)
        if uuid
    }
    service = SimpleNamespace(
        uuid=service_uuid, characteristics=list(members.values()), get_characteristic=members.get
    )
    client = SimpleNamespace(
        is_connected=True,
        services=_Services(
            [service], get_service={service_uuid: service}.get, get_characteristic=members.get
        ),
        write_gatt_char=AsyncMock(),
    )
    controller = JiecangAppController(coordinator, profile=key, layout="standard_2")
    profile = jiecang.APP_PROFILES[key]
    held = jiecang.motion_command(profile, "standard_2", "back", True)
    return controller, client, held, [command for _, command in profile.hold.releases]


def _logicdata(coordinator: Any, key: str) -> tuple[BedController, Any, bytes, list[bytes]]:
    client = MagicMock()
    client.is_connected = True
    client.write_gatt_char = AsyncMock()
    transport = logicdata.TRANSPORTS["t1"]
    chars = {
        uuid: MagicMock(uuid=uuid, properties=["write", "notify"])
        for uuid in {transport.write_uuid, transport.notify_uuid, transport.name_uuid} - {None}
    }
    client.services.get_characteristic.side_effect = chars.get
    controller = LogicdataAppController(
        coordinator,
        profile=key,
        command_family="p1",
        layout="standard_2",
        transport="t1",
        has_light=False,
        has_massage=False,
    )
    profile = logicdata.APP_PROFILES[key]
    held = logicdata.motion_command(profile, "p1", "standard_2", "back", True)
    return controller, client, held, [command for _, command in profile.touch_release]


SCENARIOS = {
    **{key: f"jiecang_app:{key}:standard_2:g1" for key in JIECANG_STREAM},
    **{key: f"logicdata_app:{key}:p1:standard_2:t1" for key in LOGICDATA_STREAM},
}


def _release_schedule(family: str, key: str) -> list[tuple[int, str]]:
    """The profile's release frames at their offsets from the end of the hold."""
    if family == "jiecang":
        schedule = jiecang.APP_PROFILES[key].hold.releases
    else:
        schedule = logicdata.APP_PROFILES[key].touch_release
    return [(offset, command.hex()) for offset, command in schedule]


async def _back_up(controller: Any) -> None:
    await controller.move_back_up()


@pytest.mark.parametrize(("family", "key"), CASES)
async def test_lease_streams_at_the_app_cadence_then_expiry_releases(family: str, key: str) -> None:
    """Virtual time: the refresh outlives the configured pulses until the lease ends."""
    wire = await leased_hold(SCENARIOS[key], _back_up, end_after_s=END_AFTER_S, end="expire")

    assert {write.data.hex() for write in wire.held} == {HELD}
    # The apps refresh every 100 ms until release, whatever the pulse settings.
    assert wire.pulse_count * 100 < END_AFTER_S * 1000
    assert len(wire.held) == END_AFTER_S * 1000 // 100
    assert intervals(wire.held) == {100}
    # Expiry runs the profile's own release schedule, and no final motion frame.
    assert [(w.at_ms - wire.ended_ms, w.data.hex()) for w in wire.after] == _release_schedule(
        family, key
    )


@pytest.mark.parametrize(("family", "key"), CASES)
async def test_stop_preempts_the_lease_and_releases(family: str, key: str) -> None:
    wire = await leased_hold(SCENARIOS[key], _back_up, end_after_s=1, end="stop")
    after = [write.data.hex() for write in wire.after]
    releases = [frame for _offset, frame in _release_schedule(family, key)]
    assert {write.data.hex() for write in wire.held} == {HELD}
    # The hold's own release, then the STOP's; motion never resumes.
    assert after[: len(releases)] == releases
    assert HELD not in after


@pytest.mark.parametrize(("family", "key"), CASES)
async def test_finite_pulses_are_unchanged_without_a_lease(family: str, key: str) -> None:
    wire = await leased_hold(
        SCENARIOS[key], _back_up, end_after_s=END_AFTER_S, end="expire", leased=False
    )
    frames = [write.data.hex() for write in (*wire.held, *wire.after)]
    if family == "jiecang":
        final = jiecang.APP_PROFILES[key].hold.final_frame
        motion = wire.pulse_count + final
    else:
        # The configured pulses, then the touch-up terminal repeat.
        motion = wire.pulse_count + 1
    releases = [frame for _offset, frame in _release_schedule(family, key)]
    assert frames == [HELD] * motion + releases


@pytest.mark.parametrize(("family", "key"), CASES)
def test_motor_covers_advertise_the_stream_hold(family: str, key: str) -> None:
    """The card reads ``hold_lease_mode`` from each declared motor cover."""
    from custom_components.adjustable_bed.entity import hold_lease_attributes

    coordinator = MagicMock()
    coordinator.cancel_command = asyncio.Event()
    controller, *_ = (_jiecang if family == "jiecang" else _logicdata)(coordinator, key)
    specs = controller.motor_control_specs
    assert specs
    for spec in specs:
        assert hold_lease_attributes([controller], spec.key)["hold_lease_mode"] == "stream"
    assert hold_lease_attributes([controller], "back") == {
        "hold_lease_mode": "stream",
        "hold_lease_motor": "back",
    }


def test_comfort_motion_covers_advertise_no_hold() -> None:
    from custom_components.adjustable_bed.beds.jiecang import JiecangProfileController
    from custom_components.adjustable_bed.entity import hold_lease_attributes

    controller = JiecangProfileController(
        MagicMock(), jiecang.COMFORT_MOTION, "standard_2"
    )
    assert hold_lease_attributes([controller], "back") == {}
