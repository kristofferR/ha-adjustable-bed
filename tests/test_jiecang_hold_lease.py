"""Renewable holds (#483) on the Jiecang codec: the Dream apps and LOGICDATA.

Only the profiles whose accepted reports stream a held frame until release
declare ``hold="stream"``. Their leased hold refreshes the app's own motion
frame at the app's own cadence and ends with the app's own release schedule.
"""

from __future__ import annotations

import asyncio
from dataclasses import astuple
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.beds.jiecang_app import JiecangAppController
from custom_components.adjustable_bed.beds.logicdata_app import LogicdataAppController
from custom_components.adjustable_bed.codec.jiecang import TRANSPORTS
from custom_components.adjustable_bed.command_scheduler import (
    CommandKind,
    CommandOutcome,
    HoldClaim,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_JIECANG_APP,
    BED_TYPE_LOGICDATA_APP,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
)
from custom_components.adjustable_bed.execution import STREAM_HOLD
from custom_components.adjustable_bed.profiles import jiecang, logicdata
from tests.hold_lease_harness import (
    install,
    last_outcome,
    lease,
    lease_coordinator,
    renew_for,
    start_hold,
)
from tests.jiecang_vectors import FROZEN_FRAMES as JIECANG_FRAMES
from tests.logicdata_vectors import FROZEN_FRAMES as LOGICDATA_FRAMES

JIECANG_STREAM = ("dreamask", "dreamotion", "dreamhd")
LOGICDATA_STREAM = ("phone", "tablet", "sleep_smart")
CASES = [("jiecang", key) for key in JIECANG_STREAM] + [
    ("logicdata", key) for key in LOGICDATA_STREAM
]
# The user's pulse settings would end a finite move after two frames.
PULSES = {CONF_MOTOR_PULSE_COUNT: 2, CONF_MOTOR_PULSE_DELAY_MS: 20}
BACK = "motor:back"


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


def _build(coordinator: Any, family: str, key: str):
    controller, client, held, releases = (_jiecang if family == "jiecang" else _logicdata)(
        coordinator, key
    )
    install(coordinator, controller, client)
    return controller, client, held, releases


def _frames(client: Any) -> list[bytes]:
    return [bytes(call.args[1]) for call in client.write_gatt_char.await_args_list]


def _bed_type(family: str) -> str:
    return BED_TYPE_JIECANG_APP if family == "jiecang" else BED_TYPE_LOGICDATA_APP


async def _back_up(controller: BedController) -> None:
    await controller.move_back_up()


@pytest.mark.parametrize(("family", "key"), CASES)
async def test_renewal_keeps_streaming_then_expiry_releases(
    hass: HomeAssistant, family: str, key: str
) -> None:
    async with lease_coordinator(hass, _bed_type(family), **PULSES) as coordinator:
        _controller, client, held_frame, releases = _build(coordinator, family, key)
        held = lease(0.4)
        loop = asyncio.get_running_loop()
        began = loop.time()
        task = start_hold(coordinator, _back_up, held, BACK)
        await renew_for(coordinator, held, BACK, seconds=0.6, every=0.1)
        streamed = loop.time() - began

        # Renewals outlived both the first lease and the two configured pulses.
        frames = _frames(client)
        assert not task.done()
        assert len(frames) >= 4
        assert set(frames) == {held_frame}
        # The app's 100 ms cadence, not the configured 20 ms pulse delay.
        assert len(frames) <= streamed / 0.1 + 2

        await asyncio.wait_for(task, 3)
        assert last_outcome(coordinator) is CommandOutcome.EXPIRED
        frames = _frames(client)

        first_release = frames.index(releases[0])
        assert set(frames[:first_release]) == {held_frame}
        assert frames[first_release:] == releases
        assert coordinator.claim_hold_lease(held, resource=BACK) is HoldClaim.STALE


@pytest.mark.parametrize(("family", "key"), CASES)
async def test_stop_preempts_the_lease_and_releases(
    hass: HomeAssistant, family: str, key: str
) -> None:
    async with lease_coordinator(hass, _bed_type(family), **PULSES) as coordinator:
        _controller, client, held_frame, releases = _build(coordinator, family, key)
        held = lease(5)
        task = start_hold(coordinator, _back_up, held, BACK)
        while len(_frames(client)) < 2:
            await asyncio.sleep(0.01)

        await coordinator.async_stop_command()
        await asyncio.wait_for(task, 3)

        record = next(
            r
            for r in reversed(coordinator._command_scheduler.recent_records)
            if r.kind is CommandKind.HOLD
        )
        assert record.outcome is CommandOutcome.STOPPED
        frames = _frames(client)
        first_release = frames.index(releases[0])
        assert set(frames[:first_release]) == {held_frame}
        # The hold's own release, then the STOP's; motion never resumes.
        assert frames[first_release : first_release + len(releases)] == releases
        assert held_frame not in frames[first_release:]
        assert coordinator.claim_hold_lease(held, resource=BACK) is HoldClaim.STALE


@pytest.mark.parametrize(("family", "key"), CASES)
async def test_finite_pulses_are_unchanged_without_a_lease(
    hass: HomeAssistant, family: str, key: str
) -> None:
    async with lease_coordinator(hass, _bed_type(family), **PULSES) as coordinator:
        _controller, client, held_frame, releases = _build(coordinator, family, key)
        await coordinator.async_execute_controller_command(_back_up, resource=BACK)

        if family == "jiecang":
            final = jiecang.APP_PROFILES[key].hold.final_frame
            expected = [held_frame] * (2 + final) + releases
        else:
            # Two configured pulses, the touch-up terminal repeat, then release.
            expected = [held_frame] * 3 + releases
        assert _frames(client) == expected
        assert last_outcome(coordinator) is CommandOutcome.COMPLETED
