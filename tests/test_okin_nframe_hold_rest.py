"""Renewable holds (#483) on the remaining stream-supported Okin N-frame rows.

Each route runs its real controller, built by the factory on the wire
snapshot's stored GATT layout, through the coordinator's scheduler and the
``timed_move`` service. A lease streams the motor's held frame until it
expires or STOP arrives, then the profile's own release follows.
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import sys
from collections import Counter
from collections.abc import AsyncIterator
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.command_scheduler import CommandKind, CommandOutcome
from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_PROTOCOL_VARIANT,
    CONF_STARCODE_COMMAND_SELECTOR,
    DOMAIN,
    ZSERIES_VARIANT_Z280,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from tests.okin_nframe_vectors import FIELD_FRAMES, FROZEN_FRAMES
from tests.sleepys_box25_star_vectors import BOX25_STAR_FRAMES
from tests.starcode_abm5_4_vectors import BUILDER_VECTORS

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "wire_snapshot.py"
_spec = importlib.util.spec_from_file_location("wire_snapshot_for_holds", SCRIPT)
assert _spec is not None and _spec.loader is not None
ws = sys.modules.setdefault(_spec.name, importlib.util.module_from_spec(_spec))
_spec.loader.exec_module(ws)
LAYOUTS: dict[str, Any] = json.loads(ws.LAYOUTS_PATH.read_text())
SCENARIOS = {scenario.id: scenario for scenario in ws.build_scenarios()}
ADDRESS = "AA:BB:CC:DD:EE:FF"

# Route -> (wire snapshot scenario, the motor a lease holds, entry data overrides).
ROUTES: dict[str, tuple[str, str, dict[str, Any]]] = {
    **{
        f"okin_cst:cst_{product}": (f"okin_cst:cst_{product}", "head", {})
        for product in (
            "sanctuary",
            "resident",
            "aviada",
            "bob",
            "contempo",
            "carefree",
            "clarity",
            "mf900",
            "support",
            "nectar_move",
        )
    },
    "serenity": ("serenity", "head", {}),
    "tranquil": ("tranquil", "head", {}),
    "customatic_zseries:z230": ("customatic_zseries", "head", {}),
    "customatic_zseries:z280": (
        "customatic_zseries",
        "feet",
        {CONF_PROTOCOL_VARIANT: ZSERIES_VARIANT_Z280},
    ),
    "adjustable_lumbar:adjustable_lumbar_okin": (
        "adjustable_lumbar:adjustable_lumbar_okin",
        "head",
        {},
    ),
    "adjustable_lumbar:adjustable_lumbar_star": (
        "adjustable_lumbar:adjustable_lumbar_star",
        "lumbar",
        {},
    ),
    "simmons:simmons_okin": ("simmons:simmons_okin", "back", {}),
    "simmons:simmons_smartbed": ("simmons:simmons_smartbed", "legs", {}),
    **{
        f"starcode_abm5_4:{selector}": (
            "starcode_abm5_4",
            "back",
            {CONF_STARCODE_COMMAND_SELECTOR: selector},
        )
        for selector in ("none", "BOX3633", "BOX25", "BOX15", "BOX1220")
    },
    "sleepys_box25:box25_star": ("sleepys_box25:box25_star", "head", {}),
    "sleepys_box25:box25_legacy": ("sleepys_box25:box25_legacy", "feet", {}),
}


def _frozen(controller: Any) -> frozenset[str]:
    """The route's own frozen literals: its profile's, or the BOX25_STAR report's."""
    profile = getattr(controller, "profile", None)
    if profile is None:
        return BOX25_STAR_FRAMES
    frozen = FROZEN_FRAMES[profile.key] | FIELD_FRAMES.get(profile.key, frozenset())
    if profile.key.startswith("starcode_abm5_4"):
        # BOX15 and BOX1220 move with their own frames from the same report.
        selector = controller._coordinator.entry.data[CONF_STARCODE_COMMAND_SELECTOR]
        frozen |= {
            vector.lower() for row_selector, *_, vector in BUILDER_VECTORS if row_selector == selector
        }
    return frozen


@dataclass
class Route:
    hass: HomeAssistant
    coordinator: AdjustableBedCoordinator
    motor: str
    frames: list[str]
    frozen: frozenset[str]


class _Recorder:
    def __init__(self, frames: list[str]) -> None:
        self._frames = frames

    def add(self, _char: Any, kind: Any, data: Any = b"") -> None:
        if kind in (True, False, None):
            self._frames.append(bytes(data).hex())


@pytest.fixture(params=sorted(ROUTES))
async def route(hass: HomeAssistant, request: pytest.FixtureRequest) -> AsyncIterator[Route]:
    scenario_id, motor, overrides = ROUTES[request.param]
    scenario = SCENARIOS[scenario_id]
    data = {
        **ws._base_entry_data(),
        **scenario.entry_data,
        **overrides,
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "Okin hold bed",
        CONF_BED_TYPE: scenario.bed_type,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_DISCONNECT_AFTER_COMMAND: False,
    }
    variant = data.setdefault(CONF_PROTOCOL_VARIANT, scenario.protocol_variant or "auto")
    entry = MockConfigEntry(domain=DOMAIN, title="Okin hold bed", unique_id=ADDRESS, data=data)
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    frames: list[str] = []
    client = ws.FakeClient(
        _Recorder(frames), LAYOUTS[scenario.layout_id or scenario.id], scenario.replies
    )
    coordinator._client = client  # type: ignore[assignment]
    coordinator._controller = await create_controller(
        coordinator,
        scenario.bed_type,
        variant,
        client,  # type: ignore[arg-type]
        **scenario.factory_kwargs,
    )
    # The coordinator's post-connect hooks resolve each route's write role.
    controller = coordinator._controller
    discovery = controller.async_discover_capabilities()
    if inspect.isawaitable(discovery):
        await discovery
    await controller.start_notify(lambda *_: None)
    frames.clear()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    from custom_components.adjustable_bed.services import async_register_services

    await async_register_services(hass)
    with ExitStack() as stack:
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
        yield Route(hass, coordinator, motor, frames, _frozen(controller))
    await coordinator.async_shutdown()


async def _hold(route: Route, generation: int, duration_ms: int = 900) -> None:
    await route.hass.services.async_call(
        DOMAIN,
        "timed_move",
        {
            "device_id": ["bed"],
            "motor": route.motor,
            "direction": "up",
            "duration_ms": duration_ms,
            "hold_owner": "card",
            "hold_generation": generation,
        },
        blocking=True,
    )


def _held(frames: list[str]) -> str:
    return Counter(frames).most_common(1)[0][0]


async def _streaming(route: Route, count: int = 2) -> str:
    async with asyncio.timeout(3):
        while not route.frames or Counter(route.frames).most_common(1)[0][1] < count:
            await asyncio.sleep(0.01)
    return _held(route.frames)


def _assert_released(route: Route, held: str) -> None:
    """The held frame streams, then only frozen release frames follow."""
    frames = route.frames
    assert held in route.frozen
    last_held = len(frames) - 1 - frames[::-1].index(held)
    assert set(frames[: last_held + 1]) == {held}
    release = frames[last_held + 1 :]
    assert release, "the profile's release must follow the hold"
    assert set(release) <= route.frozen
    # One STOP frame, repeated as the profile's release and the timed move's
    # cleanup. AdjustableM5X4 then queries its massage state, as after any move.
    stop = release[0]
    assert set(release) - {stop} <= {"00b0"}
    profile = getattr(route.coordinator.controller, "profile", None)
    if profile is not None:
        assert release.count(stop) >= profile.hold.releases


async def test_renewal_keeps_streaming_then_expiry_releases(route: Route) -> None:
    loop = asyncio.get_running_loop()
    start = asyncio.create_task(_hold(route, 1))
    held = await _streaming(route)
    began = loop.time()
    for _ in range(4):
        await asyncio.sleep(0.3)
        before = Counter(route.frames)
        await asyncio.wait_for(_hold(route, 1), 0.2)
        # A renewal writes nothing new beyond the ongoing refresh.
        assert set(Counter(route.frames) - before) <= {held}
        assert not start.done()
    await asyncio.wait_for(start, 5)
    assert loop.time() - began >= 1.2
    _assert_released(route, held)
    record = route.coordinator._command_scheduler.recent_records[-1]
    assert record.kind is CommandKind.HOLD
    assert record.outcome is CommandOutcome.EXPIRED


async def test_stop_preempts_and_refuses_renewal(route: Route) -> None:
    start = asyncio.create_task(_hold(route, 2, duration_ms=5000))
    held = await _streaming(route)
    await route.coordinator.async_stop_command()
    await asyncio.wait_for(start, 3)
    _assert_released(route, held)
    count = len(route.frames)
    with pytest.raises(ServiceValidationError, match="has ended"):
        await _hold(route, 2)
    await asyncio.sleep(0.3)
    assert route.frames[count:] == []
