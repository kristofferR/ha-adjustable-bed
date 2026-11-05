"""Tests for the separate DewertOkin ELEVATE StarCode controller."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.star_elevate import (
    StarElevateCommands,
    StarElevateController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_STAR_ELEVATE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    NORDIC_UART_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


@pytest.fixture
def mock_star_elevate_config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return an ELEVATE config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="ELEVATE Test",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:46",
            CONF_NAME: "ELEVATE Test",
            CONF_BED_TYPE: BED_TYPE_STAR_ELEVATE,
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id="AA:BB:CC:DD:EE:46",
        entry_id="star_elevate_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestStarElevateController:
    """Test exact ELEVATE discovery-independent controller behavior."""

    async def test_factory_creates_separate_controller_and_motor_surface(
        self,
        hass: HomeAssistant,
        mock_star_elevate_config_entry,
        mock_coordinator_connected,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_star_elevate_config_entry)
        await coordinator.async_connect()

        assert isinstance(coordinator.controller, StarElevateController)
        assert coordinator.controller.control_characteristic_uuid == NORDIC_UART_WRITE_CHAR_UUID
        assert [spec.key for spec in coordinator.controller.motor_control_specs] == [
            "elevate_actuator_1",
            "elevate_actuator_2",
            "elevate_both",
        ]

    async def test_lazy_session_wake_and_commands_use_write_without_response(
        self,
        hass: HomeAssistant,
        mock_star_elevate_config_entry,
        mock_coordinator_connected,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_star_elevate_config_entry)
        await coordinator.async_connect()
        controller = coordinator.controller
        # Connection setup has already enabled RX and sent wake. Reset the flag
        # to exercise the same lazy fallback used after a missed initialization.
        controller._initialized = False
        both_up = bytes.fromhex("5A 01 03 10 30 44 A5")

        with patch.object(controller, "_write_gatt_with_retry", AsyncMock()) as mock_write:
            await controller.write_command(both_up)

        assert [call.args[1] for call in mock_write.await_args_list] == [
            bytes.fromhex("5A 0B 00 A5"),
            both_up,
        ]
        assert [call.kwargs["response"] for call in mock_write.await_args_list] == [False, False]

# AdjustableM5X5 1.2.3 drives ELEVATE lifts with these frozen P3 vectors.
M5X5_ELEVATE_VECTORS = [
    case
    for case in json.loads(
        Path(__file__).with_name("fixtures").joinpath("starcode_m5x5_commands.json").read_text()
    )
    if case["profile"] == "elevate"
]


@pytest.mark.parametrize("case", M5X5_ELEVATE_VECTORS, ids=lambda case: case["id"])
async def test_adjustable_m5x5_elevate_vectors(
    hass: HomeAssistant,
    mock_star_elevate_config_entry,
    mock_coordinator_connected,
    case: dict[str, object],
) -> None:
    """Every AdjustableM5X5 ELEVATE frame is the star_elevate frame for that action."""
    coordinator = AdjustableBedCoordinator(hass, mock_star_elevate_config_entry)
    await coordinator.async_connect()
    controller = coordinator.controller
    assert isinstance(controller, StarElevateController)
    controller._initialized = case["action"] != "initialize"
    methods = {
        "union_up": controller.move_both_up,
        "union_down": controller.move_both_down,
        "head_up": controller.move_head_up,
        "head_down": controller.move_head_down,
        "foot_up": controller.move_feet_up,
        "foot_down": controller.move_feet_down,
        "flat": controller.preset_flat,
        "stop": controller.stop_all,
        "interrupt": controller.interrupt,
        "initialize": controller.start_notify,
    }
    with patch.object(controller, "_write_gatt_with_retry", AsyncMock()) as mock_write:
        await methods[str(case["action"])]()
    frames = [call.args[1] for call in mock_write.await_args_list]
    expected = bytes.fromhex(str(case["vector"]))
    if case["source_count"] == -1:
        # Held until release, then the shared STOP; flat sends no STOP.
        assert frames == [expected, StarElevateCommands.STOP]
        assert mock_write.await_args_list[0].kwargs["repeat_count"] >= 1
    else:
        assert frames == [expected]


async def test_elevate_main_or_lift_interrupts_its_group_peers(
    hass: HomeAssistant,
    mock_star_elevate_config_entry,
    mock_coordinator_connected,
) -> None:
    """Individual ELEVATE motion and flat interrupt a configured group first."""
    coordinator = AdjustableBedCoordinator(hass, mock_star_elevate_config_entry)
    await coordinator.async_connect()
    controller = coordinator.controller
    assert isinstance(controller, StarElevateController)
    with (
        patch(
            "custom_components.adjustable_bed.starcode_accessory_group.interrupt_conflicting_group",
            AsyncMock(),
        ) as interrupt,
        patch.object(controller, "write_command", AsyncMock()),
    ):
        await controller.move_head_up()
        await controller.preset_flat()
    assert interrupt.await_count == 2
    assert controller.ready is True
