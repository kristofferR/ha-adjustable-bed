"""Drive a real family controller through the coordinator's hold lease (#483).

Family lease tests build their controller on a real coordinator and scheduler
with a recording client, so renewal, expiry and STOP run the controller's own
loop and cleanup at its own timing.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import ExitStack, asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.command_scheduler import (
    CommandOutcome,
    HoldClaim,
    HoldLease,
)
from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

ADDRESS = "AA:BB:CC:DD:EE:83"
Move = Callable[[BedController], Coroutine[Any, Any, None]]


@asynccontextmanager
async def lease_coordinator(
    hass: HomeAssistant, bed_type: str, **data: object
) -> AsyncIterator[AdjustableBedCoordinator]:
    """A connected coordinator whose client records every write."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Lease bed",
        unique_id=ADDRESS,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Lease bed",
            CONF_BED_TYPE: bed_type,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_DISCONNECT_AFTER_COMMAND: False,
            **data,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    with ExitStack() as stack:
        stack.enter_context(
            patch.object(coordinator, "async_ensure_connected", AsyncMock(return_value=True))
        )
        stack.enter_context(
            patch.object(coordinator, "_async_refresh_controller_auth", AsyncMock())
        )
        try:
            yield coordinator
        finally:
            # The recording client has no link to tear down.
            coordinator._client = None
            await coordinator.async_shutdown()


def install(coordinator: AdjustableBedCoordinator, controller: BedController, client: Any) -> None:
    """Make ``controller`` the live controller over ``client``."""
    coordinator._client = client
    coordinator._controller = controller


def lease(duration_s: float, generation: int = 1, action: str = "up") -> HoldLease:
    return HoldLease(owner="card", generation=generation, action=action, duration_s=duration_s)


def start_hold(
    coordinator: AdjustableBedCoordinator, move: Move, held: HoldLease, resource: str
) -> asyncio.Task[None]:
    """Start a leased hold the way ``timed_move`` does, without waiting for it."""
    return asyncio.create_task(
        coordinator.async_execute_controller_command(move, resource=resource, lease=held)
    )


async def renew_for(
    coordinator: AdjustableBedCoordinator,
    held: HoldLease,
    resource: str,
    seconds: float,
    every: float,
) -> None:
    """Renew ``held`` every ``every`` seconds for ``seconds``, as the card does."""
    loop = asyncio.get_running_loop()
    end = loop.time() + seconds
    while loop.time() < end:
        await asyncio.sleep(every)
        assert coordinator.claim_hold_lease(held, resource=resource) is HoldClaim.RENEW


def last_outcome(coordinator: AdjustableBedCoordinator) -> CommandOutcome | None:
    return coordinator._command_scheduler.recent_records[-1].outcome
