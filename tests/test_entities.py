"""Tests for Adjustable Bed entities."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from custom_components.adjustable_bed import async_setup_entry
from custom_components.adjustable_bed.const import DOMAIN

from .conftest import TEST_ADDRESS


class TestCoverEntities:
    """Test cover entities."""

    async def test_cover_entities_created(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Test cover entities are created based on motor count."""
        await async_setup_entry(hass, mock_config_entry)
        await hass.async_block_till_done()

        # With 2 motors, should have back and legs covers
        back_state = hass.states.get(f"cover.{TEST_ADDRESS.replace(':', '_').lower()}_back")
        legs_state = hass.states.get(f"cover.{TEST_ADDRESS.replace(':', '_').lower()}_legs")

        # Note: Entity names may be different based on translation
        # Check we have the expected number of cover entities
        cover_states = [
            state
            for state in hass.states.async_all()
            if state.entity_id.startswith("cover.")
        ]
        assert len(cover_states) == 2  # back and legs for 2-motor bed

    async def test_cover_open_close(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test cover open and close commands."""
        await async_setup_entry(hass, mock_config_entry)
        await hass.async_block_till_done()

        # Get a cover entity
        cover_entities = [
            state.entity_id
            for state in hass.states.async_all()
            if state.entity_id.startswith("cover.")
        ]
        assert len(cover_entities) > 0

        entity_id = cover_entities[0]

        # Test open
        await hass.services.async_call(
            "cover",
            "open_cover",
            {"entity_id": entity_id},
            blocking=True,
        )

        # Verify command was sent
        assert mock_bleak_client.write_gatt_char.call_count >= 1
        mock_bleak_client.write_gatt_char.reset_mock()

        # Test close
        await hass.services.async_call(
            "cover",
            "close_cover",
            {"entity_id": entity_id},
            blocking=True,
        )

        assert mock_bleak_client.write_gatt_char.call_count >= 1

    async def test_cover_stop(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test cover stop command."""
        await async_setup_entry(hass, mock_config_entry)
        await hass.async_block_till_done()

        cover_entities = [
            state.entity_id
            for state in hass.states.async_all()
            if state.entity_id.startswith("cover.")
        ]
        entity_id = cover_entities[0]

        await hass.services.async_call(
            "cover",
            "stop_cover",
            {"entity_id": entity_id},
            blocking=True,
        )

        mock_bleak_client.write_gatt_char.assert_called()


class TestButtonEntities:
    """Test button entities."""

    async def test_button_entities_created(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Test button entities are created."""
        await async_setup_entry(hass, mock_config_entry)
        await hass.async_block_till_done()

        button_states = [
            state
            for state in hass.states.async_all()
            if state.entity_id.startswith("button.")
        ]

        # Should have preset buttons (4), program buttons (4), and stop button
        # Massage buttons are excluded because has_massage=False
        assert len(button_states) == 9

    async def test_button_entities_with_massage(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict,
        mock_coordinator_connected,
    ):
        """Test massage button entities are created when has_massage=True."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        # Create entry with massage enabled
        mock_config_entry_data["has_massage"] = True
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Bed",
            data=mock_config_entry_data,
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id="massage_entry_id",
        )
        entry.add_to_hass(hass)

        await async_setup_entry(hass, entry)
        await hass.async_block_till_done()

        button_states = [
            state
            for state in hass.states.async_all()
            if state.entity_id.startswith("button.")
        ]

        # Should have preset (4) + program (4) + stop (1) + massage buttons (11)
        assert len(button_states) == 20

    async def test_preset_button_press(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test pressing a preset button sends command."""
        await async_setup_entry(hass, mock_config_entry)
        await hass.async_block_till_done()

        # Find a preset button
        button_entities = [
            state.entity_id
            for state in hass.states.async_all()
            if state.entity_id.startswith("button.") and "memory_1" in state.entity_id
        ]
        assert len(button_entities) > 0

        entity_id = button_entities[0]

        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": entity_id},
            blocking=True,
        )

        mock_bleak_client.write_gatt_char.assert_called()


class TestSwitchEntities:
    """Test switch entities."""

    async def test_switch_entities_created(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Test switch entities are created."""
        await async_setup_entry(hass, mock_config_entry)
        await hass.async_block_till_done()

        switch_states = [
            state
            for state in hass.states.async_all()
            if state.entity_id.startswith("switch.")
        ]

        # Should have under-bed lights switch
        assert len(switch_states) == 1

    async def test_switch_turn_on_off(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test turning switch on and off."""
        await async_setup_entry(hass, mock_config_entry)
        await hass.async_block_till_done()

        switch_entities = [
            state.entity_id
            for state in hass.states.async_all()
            if state.entity_id.startswith("switch.")
        ]
        entity_id = switch_entities[0]

        # Turn on
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": entity_id},
            blocking=True,
        )

        assert mock_bleak_client.write_gatt_char.call_count >= 1
        mock_bleak_client.write_gatt_char.reset_mock()

        # Turn off
        await hass.services.async_call(
            "switch",
            "turn_off",
            {"entity_id": entity_id},
            blocking=True,
        )

        assert mock_bleak_client.write_gatt_char.call_count >= 1


class TestSensorEntities:
    """Test sensor entities."""

    async def test_sensor_entities_skipped_when_disabled(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
    ):
        """Test sensor entities are not created when angle sensing is disabled."""
        # Default config has disable_angle_sensing=True
        await async_setup_entry(hass, mock_config_entry)
        await hass.async_block_till_done()

        sensor_states = [
            state
            for state in hass.states.async_all()
            if state.entity_id.startswith("sensor.") and "angle" in state.entity_id
        ]

        assert len(sensor_states) == 0

    async def test_sensor_entities_created_when_enabled(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict,
        mock_coordinator_connected,
    ):
        """Test sensor entities are created when angle sensing is enabled."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        # Create entry with angle sensing enabled
        mock_config_entry_data["disable_angle_sensing"] = False
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Bed",
            data=mock_config_entry_data,
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id="sensor_entry_id",
        )
        entry.add_to_hass(hass)

        await async_setup_entry(hass, entry)
        await hass.async_block_till_done()

        sensor_states = [
            state
            for state in hass.states.async_all()
            if state.entity_id.startswith("sensor.") and "angle" in state.entity_id
        ]

        # With 2 motors, should have back_angle and legs_angle sensors
        assert len(sensor_states) == 2


class TestEntityAvailability:
    """Test entity availability."""

    async def test_entity_unavailable_when_disconnected(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test entities report unavailable when disconnected."""
        await async_setup_entry(hass, mock_config_entry)
        await hass.async_block_till_done()

        # Simulate disconnection
        mock_bleak_client.is_connected = False

        # Force state update
        await hass.async_block_till_done()

        # Entities should now be unavailable
        cover_entities = [
            state
            for state in hass.states.async_all()
            if state.entity_id.startswith("cover.")
        ]

        for state in cover_entities:
            # Re-fetch state after simulating disconnect
            current_state = hass.states.get(state.entity_id)
            assert current_state.state == STATE_UNAVAILABLE
