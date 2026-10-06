"""Import the wake-up blueprint through HA and exercise its scheduled action paths."""

from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.adjustable_bed import services

BLUEPRINT_PATH = "adjustable_bed/wake_up.yaml"
BLUEPRINT_SOURCE = Path(__file__).resolve().parents[1] / "blueprints/automation" / BLUEPRINT_PATH


@pytest.fixture
async def installed_blueprint(hass: HomeAssistant) -> AsyncIterator[None]:
    """Let HA load the shipped YAML, including selectors, defaults and !input tags."""
    destination = Path(hass.config.path("blueprints/automation", BLUEPRINT_PATH))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=destination.parent, suffix=".tmp", delete=False
    ) as staged:
        staged.write(BLUEPRINT_SOURCE.read_text())
    os.replace(staged.name, destination)
    yield
    if hass.services.has_service("automation", "turn_off"):
        await hass.services.async_call(
            "automation", "turn_off", {"entity_id": "automation.bed_wake_up"}, blocking=True
        )


@pytest.fixture
async def bed_actions(hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    """Retain the real public action schemas, replacing only hardware handlers."""
    handlers = {"timed_move": AsyncMock(), "goto_preset": AsyncMock()}
    for name, handler in handlers.items():
        monkeypatch.setattr(services, f"handle_{name}", handler)
    await services.async_register_services(hass)
    return handlers


async def setup_wake_up(hass: HomeAssistant, **inputs: object) -> None:
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": [
                {
                    "id": "bed_wake_up",
                    "alias": "Bed wake up",
                    "use_blueprint": {
                        "path": BLUEPRINT_PATH,
                        "input": {"bed_device": "selected_bed", **inputs},
                    },
                }
            ]
        },
    )
    assert hass.states.get("automation.bed_wake_up") is not None


async def run_actions(hass: HomeAssistant) -> None:
    await hass.services.async_call(
        "automation", "trigger", {"entity_id": "automation.bed_wake_up"}, blocking=True
    )
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("date", "weekdays", "expected_calls"),
    [
        ("2026-10-05", ["mon"], 1),
        ("2026-10-06", ["mon"], 0),
        ("2026-10-05", [], 0),
    ],
)
async def test_scheduled_local_time_and_weekdays(
    hass: HomeAssistant,
    installed_blueprint: None,
    bed_actions: dict[str, AsyncMock],
    freezer: FrozenDateTimeFactory,
    date: str,
    weekdays: list[str],
    expected_calls: int,
) -> None:
    """The actual time trigger runs once at 06:30 Oslo time, only on selected days."""
    await hass.config.async_set_time_zone("Europe/Oslo")
    freezer.move_to(f"{date} 04:29:58+00:00")
    await setup_wake_up(hass, wake_time="06:30:00", weekdays=weekdays)
    await hass.async_block_till_done()

    freezer.tick(timedelta(seconds=1))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    bed_actions["timed_move"].assert_not_awaited()

    freezer.tick(timedelta(seconds=1))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert bed_actions["timed_move"].await_count == expected_calls
    bed_actions["goto_preset"].assert_not_awaited()


@pytest.mark.parametrize("side", ["auto", "left", "right", "both"])
@pytest.mark.parametrize(("motor", "duration"), [("back", 100), ("head", 30000)])
async def test_timed_raise_preserves_device_side_and_duration(
    hass: HomeAssistant,
    installed_blueprint: None,
    bed_actions: dict[str, AsyncMock],
    side: str,
    motor: str,
    duration: int,
) -> None:
    await setup_wake_up(hass, bed_side=side, raise_motor=motor, raise_duration_ms=duration)
    await run_actions(hass)
    call: ServiceCall = bed_actions["timed_move"].await_args.args[0]
    expected = {
        "device_id": ["selected_bed"],
        "motor": motor,
        "direction": "up",
        "duration_ms": duration,
    }
    if side != "auto":
        expected["side"] = side
    assert call.data == expected
    bed_actions["timed_move"].assert_awaited_once()
    bed_actions["goto_preset"].assert_not_awaited()


async def test_memory_recall_does_not_apply_raise_duration(
    hass: HomeAssistant, installed_blueprint: None, bed_actions: dict[str, AsyncMock]
) -> None:
    await setup_wake_up(hass, wake_action="memory", memory_slot=2, bed_side="right")
    await run_actions(hass)
    call: ServiceCall = bed_actions["goto_preset"].await_args.args[0]
    assert call.data == {"device_id": ["selected_bed"], "side": "right", "preset": 2}
    bed_actions["goto_preset"].assert_awaited_once()
    bed_actions["timed_move"].assert_not_awaited()


async def test_only_known_off_light_and_switch_lighting_runs_after_movement(
    hass: HomeAssistant, installed_blueprint: None, bed_actions: dict[str, AsyncMock]
) -> None:
    lights = []
    calls = {}
    for domain in ("light", "switch"):
        for state in ("off", "on", "unknown", "unavailable"):
            entity_id = f"{domain}.bed_{state}"
            hass.states.async_set(entity_id, state)
            lights.append(entity_id)
        lights.append(f"{domain}.bed_missing")
        calls[domain] = async_mock_service(hass, domain, "turn_on")

    async def move(call: ServiceCall) -> None:
        assert all(domain_calls == [] for domain_calls in calls.values())

    bed_actions["timed_move"].side_effect = move
    await setup_wake_up(hass, bed_lights=lights)
    await run_actions(hass)
    for domain, domain_calls in calls.items():
        assert [call.data for call in domain_calls] == [{"entity_id": [f"{domain}.bed_off"]}]
    bed_actions["timed_move"].assert_awaited_once()


@pytest.mark.parametrize("failure", ["bed", "service"])
async def test_failed_movement_stops_without_lights_or_retry(
    hass: HomeAssistant,
    installed_blueprint: None,
    bed_actions: dict[str, AsyncMock],
    caplog: pytest.LogCaptureFixture,
    failure: str,
) -> None:
    lighting = ["light.bed", "switch.bed_lights"]
    for entity_id in lighting:
        hass.states.async_set(entity_id, "off")
    light_calls = async_mock_service(hass, "light", "turn_on")
    switch_calls = async_mock_service(hass, "switch", "turn_on")
    if failure == "bed":
        bed_actions["timed_move"].side_effect = HomeAssistantError("Bed unavailable")
    else:
        hass.services.async_remove("adjustable_bed", "timed_move")
    await setup_wake_up(hass, bed_lights=lighting)
    await run_actions(hass)
    assert light_calls == []
    assert switch_calls == []
    assert bed_actions["timed_move"].await_count == (1 if failure == "bed" else 0)
    assert "Error" in caplog.text


@pytest.mark.parametrize("domain", ["light", "switch"])
@pytest.mark.parametrize("failure", ["action", "missing_service"])
async def test_lighting_failure_remains_an_error_without_retry(
    hass: HomeAssistant,
    installed_blueprint: None,
    bed_actions: dict[str, AsyncMock],
    caplog: pytest.LogCaptureFixture,
    domain: str,
    failure: str,
) -> None:
    """Domain dispatch must preserve failures, including a missing turn-on action."""
    next_domain = "switch" if domain == "light" else "light"
    lighting = [f"{domain}.bed_lights", f"{next_domain}.other_bed_lights"]
    for entity_id in lighting:
        hass.states.async_set(entity_id, "off")
    failed_calls = async_mock_service(
        hass, domain, "turn_on", raise_exception=HomeAssistantError("Lighting unavailable")
    )
    next_calls = async_mock_service(hass, next_domain, "turn_on")
    if failure == "missing_service":
        hass.services.async_remove(domain, "turn_on")
    await setup_wake_up(hass, bed_lights=lighting)
    await run_actions(hass)
    assert len(failed_calls) == (1 if failure == "action" else 0)
    assert next_calls == []
    bed_actions["timed_move"].assert_awaited_once()
    assert "Error" in caplog.text


async def test_duplicate_trigger_does_not_queue_another_movement(
    hass: HomeAssistant, installed_blueprint: None, bed_actions: dict[str, AsyncMock]
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def move(call: ServiceCall) -> None:
        started.set()
        await release.wait()

    bed_actions["timed_move"].side_effect = move
    await setup_wake_up(hass)
    async with asyncio.timeout(5):
        first = hass.async_create_task(
            hass.services.async_call(
                "automation", "trigger", {"entity_id": "automation.bed_wake_up"}, blocking=True
            )
        )
        await started.wait()
        await hass.services.async_call(
            "automation", "trigger", {"entity_id": "automation.bed_wake_up"}, blocking=True
        )
        release.set()
        await first
        await hass.async_block_till_done()
    bed_actions["timed_move"].assert_awaited_once()
