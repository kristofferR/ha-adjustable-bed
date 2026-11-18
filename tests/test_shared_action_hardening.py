"""The shared set_alarm checks every selected side before it writes any.

Real coordinators, schedulers and pair topologies; only the radio connection
and the controller's alarm frames are replaced.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import services
from custom_components.adjustable_bed.alarm import AlarmCapability, AlarmRequest
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from tests.hold_lease_wire import virtual_clock
from tests.test_controller_contract import _ContractController

ALARM = {"enabled": True, "time": "07:30:00"}
LIVE = AlarmCapability(live_check=True)


class AlarmController(_ContractController):
    """A bed whose alarm writes are recorded instead of framed."""

    def __init__(self, coordinator: Bed, capability: AlarmCapability) -> None:
        super().__init__(coordinator)  # type: ignore[arg-type]
        self._capability = capability
        self.bed = coordinator

    @property
    def alarm_capability(self) -> AlarmCapability:
        return self._capability

    async def check_alarm(self, alarm: AlarmRequest) -> None:
        self.bed.checks.append(self)
        await self.bed.on_check(self)

    async def configure_alarm(self, alarm: AlarmRequest) -> None:
        self.bed.writes.append(self)

    async def stop_all(self) -> None:
        self.bed.stops += 1


class Bed(AdjustableBedCoordinator):
    """A coordinator whose radio connection is simulated."""

    capability: AlarmCapability
    checks: list[AlarmController]
    writes: list[AlarmController]
    stops: int
    connect_ok: bool

    async def on_check(self, controller: AlarmController) -> None:
        del controller

    async def fake_connect(self, **_kwargs: Any) -> bool:
        if self._controller is not None and self.is_connected:
            return True
        if not self.connect_ok:
            return False
        client = MagicMock(is_connected=True)

        async def disconnect() -> None:
            client.is_connected = False

        client.disconnect = AsyncMock(side_effect=disconnect)
        self._client = client
        self._controller = AlarmController(self, self.capability)
        self._position_connection_generation += 1
        self._connection_creator_task = asyncio.current_task()
        return True


@dataclass
class Beds:
    hass: Any
    items: list[Bed] = field(default_factory=list)
    pair: PairedBedCoordinator | None = None


@asynccontextmanager
async def beds(hass, count=2, *, capability=LIVE, topology=None, connected=True):
    """Yield ``count`` beds, combined into one pair when ``topology`` is given."""
    await services.async_register_services(hass)
    made = Beds(hass)
    for index in range(1, count + 1):
        address = f"AA:BB:CC:DD:51:{index:02X}"
        entry = MockConfigEntry(
            domain=DOMAIN,
            version=5,
            title=f"Bed {index}",
            data={
                "address": address,
                "name": f"Bed {index}",
                "bed_type": "dewertokin",
                "disable_angle_sensing": True,
                "idle_disconnect_seconds": 0,
                "disconnect_after_command": False,
            },
        )
        entry.add_to_hass(hass)
        entry.mock_state(hass, ConfigEntryState.LOADED)
        bed = Bed(hass, entry)
        bed.capability, bed.checks, bed.writes, bed.stops = capability, [], [], 0
        bed.connect_ok = True
        bed.async_ensure_connected = AsyncMock(side_effect=bed.fake_connect)
        bed.async_connect = AsyncMock(side_effect=bed.fake_connect)
        bed._async_refresh_controller_auth = AsyncMock()
        bed._offline_controller = AlarmController(bed, capability)
        if connected:
            await bed.fake_connect()
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = bed
        made.items.append(bed)
    if topology is not None:
        entry = MockConfigEntry(domain=DOMAIN, version=5, data={"pair_id": "alarm-pair"})
        entry.add_to_hass(hass)
        made.pair = PairedBedCoordinator(
            hass, entry, {"left": made.items[0], "right": made.items[1]}, connection_mode=topology
        )
    try:
        yield made
    finally:
        for bed in made.items:
            await bed.async_shutdown()


async def set_alarm(hass, targets: list[tuple[Any, str]] | Callable[[], Any], **data: Any) -> None:
    resolve = targets if callable(targets) else (lambda *_: (list(targets), []))
    with patch.object(services, "_resolve_sided_targets", side_effect=resolve):
        await hass.services.async_call(
            DOMAIN, "set_alarm", {"device_id": "bed", **ALARM, **data}, blocking=True
        )


def gate(bed: Bed) -> tuple[asyncio.Event, asyncio.Event]:
    """Hold ``bed``'s next live check until released."""
    entered, release = asyncio.Event(), asyncio.Event()

    async def on_check(_controller: AlarmController) -> None:
        entered.set()
        await release.wait()

    bed.on_check = on_check  # type: ignore[method-assign]
    return entered, release


async def test_stop_during_a_later_check_writes_no_bed(hass) -> None:
    async with beds(hass) as made:
        first, second = made.items
        entered, release = gate(second)
        with virtual_clock():
            task = asyncio.create_task(
                set_alarm(hass, [(first, "both"), (second, "both")])
            )
            await entered.wait()
            await second.async_stop_command()
            release.set()
            await task
        assert first.checks and not first.writes
        assert not second.writes


async def test_stop_on_a_checked_bed_before_the_first_write_writes_none(hass) -> None:
    async with beds(hass) as made:
        first, second = made.items
        entered, release = gate(second)
        with virtual_clock():
            task = asyncio.create_task(set_alarm(hass, [(first, "both"), (second, "both")]))
            await entered.wait()
            await first.async_stop_command()
            release.set()
            await task
        assert first.writes == second.writes == []


async def test_bed_replaced_after_its_check_fails_before_any_write(hass) -> None:
    async with beds(hass, 3) as made:
        first, left, right = made.items
        pair = PairedBedCoordinator(
            hass,
            MockConfigEntry(domain=DOMAIN, version=5, data={"pair_id": "replaced"}),
            {"left": left, "right": right},
            connection_mode="concurrent",
        )
        entered, release = gate(right)
        with virtual_clock():
            task = asyncio.create_task(set_alarm(hass, [(first, "both"), (pair, "both")]))
            await entered.wait()
            pair._children["left"] = first
            release.set()
            with pytest.raises(ServiceValidationError) as raised:
                await task
        assert raised.value.translation_key == "bed_changed"
        assert first.writes == left.writes == right.writes == []


@pytest.mark.parametrize("drift", ["reconnect", "disconnect"])
async def test_bed_whose_link_changed_after_its_check_fails_before_any_write(
    hass, drift
) -> None:
    async with beds(hass) as made:
        first, second = made.items
        entered, release = gate(second)
        with virtual_clock():
            task = asyncio.create_task(set_alarm(hass, [(first, "both"), (second, "both")]))
            await entered.wait()
            await first.async_disconnect()
            if drift == "reconnect":
                await first.fake_connect()
            release.set()
            with pytest.raises(ServiceValidationError) as raised:
                await task
        assert raised.value.translation_key == "bed_changed"
        assert first.writes == second.writes == []


async def test_concurrent_pair_connects_both_sides_before_either_is_written(hass) -> None:
    async with beds(
        hass, capability=AlarmCapability(), topology="concurrent", connected=False
    ) as made:
        left, right = made.items
        right.connect_ok = False
        with virtual_clock(), pytest.raises(ServiceValidationError) as raised:
            await set_alarm(hass, [(made.pair, "both")])
        assert raised.value.translation_key == "bed_unavailable"
        assert left.writes == right.writes == []
        assert left.stops == right.stops == 0
        right.connect_ok = True
        with virtual_clock():
            await set_alarm(hass, [(made.pair, "both")])
        assert len(left.writes) == len(right.writes) == 1


async def test_failed_read_on_a_concurrent_pair_stops_no_side(hass) -> None:
    async with beds(hass, topology="concurrent") as made:
        left, right = made.items

        async def refuse(_controller: AlarmController) -> None:
            raise ValueError("The bed did not report its alarms; try again")

        right.on_check = refuse  # type: ignore[method-assign]
        with virtual_clock(), pytest.raises(ServiceValidationError) as raised:
            await set_alarm(hass, [(made.pair, "both")])
        # The side's own message, not the combined bed's side summary.
        assert "did not report its alarms" in str(raised.value)
        assert left.stops == right.stops == 0
        assert left.writes == right.writes == []


async def test_write_error_on_a_combined_bed_keeps_its_translation(hass) -> None:
    async with beds(hass, capability=AlarmCapability(), topology="concurrent") as made:
        left, right = made.items

        async def refuse(alarm: AlarmRequest) -> None:
            raise services.AlarmError("alarm_refresh_needed", "Refresh the alarm, then try again")

        right._controller.configure_alarm = refuse  # type: ignore[union-attr,method-assign]
        with virtual_clock(), pytest.raises(ServiceValidationError) as raised:
            await set_alarm(hass, [(made.pair, "both")])
        assert raised.value.translation_key == "alarm_refresh_needed"


async def test_checking_bed_that_interrupts_movement_still_writes_a_paired_side(hass) -> None:
    capability = AlarmCapability(live_check=True, cancel_running=True, resource=None)
    async with beds(hass, capability=capability, topology="concurrent") as made:
        left, right = made.items
        with virtual_clock():
            await set_alarm(hass, [(made.pair, "left")])
        assert len(left.checks) == len(left.writes) == 1
        assert right.writes == []


async def test_sequential_pair_writes_both_sides_after_their_planned_release(hass) -> None:
    async with beds(hass, topology="sequential", connected=False) as made:
        left, right = made.items
        with virtual_clock():
            await set_alarm(hass, [(made.pair, "both")])
        assert len(left.checks) == len(right.checks) == 1
        assert len(left.writes) == len(right.writes) == 1
        # Each side is written on the connection its own write opened.
        assert left.writes[0] is not left.checks[0]
        assert left.last_disconnect_reason == "sequential_switch"


async def test_sequential_side_reconnected_outside_the_call_is_not_written(hass) -> None:
    async with beds(hass, topology="sequential", connected=False) as made:
        left, right = made.items
        entered, release = gate(right)
        with virtual_clock():
            task = asyncio.create_task(set_alarm(hass, [(made.pair, "both")]))
            await entered.wait()
            # A diagnostic connect on the released left side, outside the call.
            await left.fake_connect()
            await left.async_disconnect("intentional")
            release.set()
            with pytest.raises(ServiceValidationError) as raised:
                await task
        assert raised.value.translation_key == "bed_changed"
        assert left.writes == right.writes == []
