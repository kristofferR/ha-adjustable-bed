"""A renewed hold ends at its ceiling on the clock, whatever each write takes (#483).

The scheduler bounds every leased hold from the moment its controller operation
starts: 30 s for a stream hold, 10 s for a latched one. Real family controllers
run here through the registered services and the real coordinator, on their
wire-snapshot GATT layouts, with slow acknowledged writes and virtual time. The
first call leases 30 s and a renewal 5 s later asks for 30 s more, so only the
ceiling can end the hold.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.command_scheduler import CommandOutcome
from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.execution import HOLD_CEILING_MS, LATCHED_HOLD_CEILING_MS
from custom_components.adjustable_bed.services import async_register_services
from tests.hold_lease_wire import _tool, virtual_clock

# Added to the stub's own 7 ms: an acknowledged write through a proxy.
SLOW_WRITE_S = 0.025


@dataclass
class Bed:
    hass: HomeAssistant
    coordinator: AdjustableBedCoordinator
    controller: Any
    clock: Any
    writes: list[tuple[float, bytes]]

    async def lease(self, service: str, fields: dict[str, Any], *, renew: bool = True) -> int:
        """Start a 30 s lease, renew it at 5 s, and return when the hold began (ms)."""
        data = {"device_id": ["bed"], **fields, "hold_owner": "card", "hold_generation": 1}
        data |= {"duration_ms": 30_000} if service == "timed_move" else {"duration": 30}
        began = self.clock.time()
        start = asyncio.create_task(
            self.hass.services.async_call(DOMAIN, service, data, blocking=True)
        )
        if renew:
            await asyncio.sleep(5)
            await asyncio.wait_for(
                self.hass.services.async_call(DOMAIN, service, data, blocking=True), 1
            )
        await asyncio.wait_for(start, 60)
        # The ended generation cannot be renewed.
        with pytest.raises(ServiceValidationError, match="has ended"):
            await self.hass.services.async_call(DOMAIN, service, data, blocking=True)
        return round(began * 1000)

    def frames(self, began_ms: int) -> list[tuple[int, str]]:
        return [(round(at * 1000) - began_ms, data.hex()) for at, data in self.writes]


@pytest.fixture
async def bed(hass: HomeAssistant, request: pytest.FixtureRequest) -> AsyncIterator[Bed]:
    tool = _tool()
    scenario = {s.id: s for s in tool.build_scenarios()}[request.param]
    layout = json.loads(tool.LAYOUTS_PATH.read_text())[scenario.layout_id or scenario.id]
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:30",
            CONF_NAME: "Ceiling bed",
            CONF_BED_TYPE: scenario.bed_type,
            CONF_PROTOCOL_VARIANT: scenario.protocol_variant,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_DISCONNECT_AFTER_COMMAND: False,
            **scenario.entry_data,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    await async_register_services(hass)
    with virtual_clock() as clock, ExitStack() as stack:
        client = tool.FakeClient(tool.Recorder(clock), layout, scenario.replies)
        writes: list[tuple[float, bytes]] = []
        stub_write = client.write_gatt_char

        async def slow_write(char: Any, data: Any, response: bool | None = None) -> None:
            writes.append((asyncio.get_running_loop().time(), bytes(data)))
            await stub_write(char, data, response)
            await asyncio.sleep(SLOW_WRITE_S)

        client.write_gatt_char = slow_write
        coordinator._client = client
        controller = await create_controller(
            coordinator,
            scenario.bed_type,
            scenario.protocol_variant,
            client,
            **scenario.factory_kwargs,
        )
        coordinator._controller = controller
        # The coordinator's post-connect step; Ergomotion 4.0 needs its session.
        await controller.start_notify(lambda *_: None)
        writes.clear()
        stack.enter_context(
            patch.object(coordinator, "async_ensure_connected", AsyncMock(return_value=True))
        )
        stack.enter_context(
            patch.object(coordinator, "_async_refresh_controller_auth", AsyncMock())
        )
        stack.enter_context(
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(coordinator, "both")], []),
            )
        )
        yield Bed(hass, coordinator, controller, clock, writes)
        await coordinator.async_shutdown()


@pytest.mark.parametrize(
    "bed",
    [
        "glideaway_motion",
        "ergomotion_4",
        # Restonic, INNOVA and the OKIN apps count their refreshes (#819).
        "keeson:restonic_a",
        "keeson:innova",
        "keeson:simon_li",
        # Good Vibe Sleep's sustained press counts 100 ms ticks (#860).
        "goodvibe:selector-0004",
        # The classic Richmat apps' keep buttons count worker ticks (row066).
        "richmat_classic_apps",
    ],
    indirect=True,
)
async def test_a_renewed_stream_hold_control_stops_at_30_s(bed: Bed) -> None:
    assert bed.controller.execution.hold == "stream"
    control = bed.controller.held_control_options[0]
    began = await bed.lease("hold_control", {"control": control})
    frames = bed.frames(began)
    held = max({data for _at, data in frames}, key=[data for _at, data in frames].count)

    # The refresh ran up to the ceiling, not to the renewed 35 s lease.
    last_held = max(at for at, data in frames if data == held)
    assert HOLD_CEILING_MS - 1000 < last_held <= HOLD_CEILING_MS
    # The controller's release still followed.
    assert frames[-1][1] != held
    assert bed.coordinator._command_scheduler.recent_records[-1].outcome is CommandOutcome.EXPIRED


@pytest.mark.parametrize("bed", ["reverie"], indirect=True)
@pytest.mark.parametrize(
    ("service", "fields"),
    [
        ("timed_move", {"motor": "back", "direction": "up"}),
        ("hold_control", {"control": "back_up"}),
    ],
)
async def test_a_renewed_latched_hold_stops_at_10_s(
    bed: Bed, service: str, fields: dict[str, Any]
) -> None:
    assert bed.controller.execution.hold == "latched"
    began = await bed.lease(service, fields)
    frames = bed.frames(began)

    # One start frame, then the STOP at the ceiling, not after the start's write.
    assert len(frames) == 2
    assert frames[0][0] == 0
    assert frames[1][0] == LATCHED_HOLD_CEILING_MS
