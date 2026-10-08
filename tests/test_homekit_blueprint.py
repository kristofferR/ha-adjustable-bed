"""Exercise the imported scripts through real cover services and scheduling."""

from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# HA 2026.9 defines this here; 2026.10 re-exports it from const.
from homeassistant.components.cover import (
    DATA_COMPONENT,  # pyright: ignore[reportPrivateImportUsage]
)
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import COVER_DESCRIPTIONS, AdjustableBedCover

BLUEPRINT_PATH = "adjustable_bed/section_control.yaml"
BLUEPRINT_SOURCE = (
    Path(__file__).resolve().parents[1] / "blueprints/script" / BLUEPRINT_PATH
)


@pytest.fixture
def installed_blueprint(hass: HomeAssistant) -> None:
    """Install the shipped file where HA's blueprint loader will import it."""
    destination = Path(hass.config.path("blueprints/script", BLUEPRINT_PATH))
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Publish the complete blueprint before HA loads it.
    with tempfile.NamedTemporaryFile(
        "w", dir=destination.parent, suffix=".tmp", delete=False
    ) as staged:
        staged.write(BLUEPRINT_SOURCE.read_text())
    os.replace(staged.name, destination)


def script_config(section: str, action: str) -> dict:
    """Configure a script instance as the blueprint UI would."""
    return {
        "use_blueprint": {
            "path": BLUEPRINT_PATH,
            "input": {"section": f"cover.bed_{section}", "bed_action": action},
        }
    }


@pytest.fixture
async def bed_covers(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_coordinator_connected: None,
) -> AsyncIterator[AdjustableBedCoordinator]:
    """Use the real coordinator/scheduler, with the existing simulated BLE fixture."""
    coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
    assert await coordinator.async_connect()
    assert await async_setup_component(hass, "cover", {})
    entities = []
    for description in COVER_DESCRIPTIONS:
        if description.key in ("back", "legs"):
            entity = AdjustableBedCover(coordinator, description)
            entity.entity_id = f"cover.bed_{description.key}"
            entities.append(entity)
    await hass.data[DATA_COMPONENT].async_add_entities(entities)
    yield coordinator
    await coordinator.async_shutdown()


@pytest.mark.parametrize("section", ["back", "legs"])
@pytest.mark.parametrize(
    ("action", "direction"),
    [("open_cover", "up"), ("close_cover", "down"), ("stop_cover", "stop")],
)
async def test_blueprint_routes_only_to_selected_section(
    hass: HomeAssistant,
    installed_blueprint: None,
    bed_covers: AdjustableBedCoordinator,
    monkeypatch: pytest.MonkeyPatch,
    section: str,
    action: str,
    direction: str,
) -> None:
    """Resolve !input with HA, then dispatch through our actual cover and coordinator."""
    assert bed_covers.controller is not None
    methods = {}
    for axis in ("back", "legs"):
        for movement in ("up", "down", "stop"):
            method = f"move_{axis}_{movement}"
            methods[method] = AsyncMock()
            monkeypatch.setattr(bed_covers.controller, method, methods[method])

    assert await async_setup_component(
        hass, "script", {"script": {"bed_control": script_config(section, f"cover.{action}")}}
    )
    state = hass.states.get(f"cover.bed_{section}")
    assert state is not None
    assert state.attributes.get("current_position") is None

    await hass.services.async_call("script", "bed_control", blocking=True)

    for method, mock in methods.items():
        if method == f"move_{section}_{direction}":
            mock.assert_awaited_once_with()
        else:
            mock.assert_not_awaited()


async def test_blueprint_stop_preempts_movement_and_allows_another_adjustment(
    hass: HomeAssistant,
    installed_blueprint: None,
    bed_covers: AdjustableBedCoordinator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Separate stop scripts reach cancellation while duplicate raises are ignored."""
    assert bed_covers.controller is not None
    started = asyncio.Event()
    events: list[str] = []

    async def move() -> None:
        events.append("raise")
        started.set()
        try:
            await bed_covers.cancel_command.wait()
        finally:
            events.append("release")

    async def stop() -> None:
        events.append("stop")

    raise_back = AsyncMock(side_effect=move)
    monkeypatch.setattr(bed_covers.controller, "move_back_up", raise_back)
    monkeypatch.setattr(bed_covers.controller, "move_back_stop", stop)
    assert await async_setup_component(
        hass,
        "script",
        {
            "script": {
                "raise_back": script_config("back", "cover.open_cover"),
                "stop_back": script_config("back", "cover.stop_cover"),
            }
        },
    )

    async with asyncio.timeout(5):
        for _ in range(2):
            started.clear()
            moving = hass.async_create_task(
                hass.services.async_call("script", "raise_back", blocking=True)
            )
            await started.wait()
            await hass.services.async_call("script", "raise_back", blocking=True)
            await hass.services.async_call("script", "stop_back", blocking=True)
            await moving

    assert raise_back.await_count == 2
    assert events == ["raise", "release", "stop"] * 2
    for script in ("raise_back", "stop_back"):
        state = hass.states.get(f"script.{script}")
        assert state is not None
        assert state.state == "off"
