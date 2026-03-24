"""Tests for Adjustable Bed entities."""

from __future__ import annotations

from unittest.mock import MagicMock, call

from homeassistant.const import CONF_ADDRESS, CONF_NAME, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.richmat import RichmatCommands
from custom_components.adjustable_bed.button import BUTTON_DESCRIPTIONS
from custom_components.adjustable_bed.const import (
    BED_TYPE_KAIDI,
    BED_TYPE_MALOUF_LEGACY_OKIN,
    BED_TYPE_MALOUF_NEW_OKIN,
    BED_TYPE_RICHMAT,
    BED_TYPE_SLEEPYS_BOX25,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_KAIDI_PRODUCT_ID,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    CONF_RICHMAT_REMOTE,
    DOMAIN,
    KAIDI_VARIANT_SEAT_1,
)


class TestCoverEntities:
    """Test cover entities."""

    async def test_cover_entities_created(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Test cover entities are created based on motor count."""
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        # Note: Entity names may be different based on translation
        # Check we have the expected number of cover entities
        cover_states = [
            state for state in hass.states.async_all() if state.entity_id.startswith("cover.")
        ]
        assert len(cover_states) == 2  # back and legs for 2-motor bed

    async def test_malouf_hilo_cover_entities_created(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Malouf Hi-Lo beds should expose back/legs/tilt/lumbar/bed_height only."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Malouf Hi-Lo Bed",
            data={
                "address": "AA:BB:CC:DD:EE:01",
                "name": "Malouf Hi-Lo Bed",
                CONF_BED_TYPE: BED_TYPE_MALOUF_NEW_OKIN,
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: True,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:01",
            entry_id="malouf_hilo_cover_entry",
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(hass)
        active_keys = ("back", "legs", "tilt", "lumbar", "bed_height")

        for key in active_keys:
            assert registry.async_get_entity_id(
                "cover", DOMAIN, f"AA:BB:CC:DD:EE:01_{key}"
            ) is not None

        assert registry.async_get_entity_id("cover", DOMAIN, "AA:BB:CC:DD:EE:01_head") is None
        assert registry.async_get_entity_id("cover", DOMAIN, "AA:BB:CC:DD:EE:01_feet") is None

    async def test_malouf_hilo_cover_setup_removes_stale_head_and_feet(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Malouf Hi-Lo setup should remove stale duplicate head/feet cover entities."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Legacy Malouf Hi-Lo Bed",
            data={
                "address": "AA:BB:CC:DD:EE:02",
                "name": "Legacy Malouf Hi-Lo Bed",
                CONF_BED_TYPE: BED_TYPE_MALOUF_LEGACY_OKIN,
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: True,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:02",
            entry_id="legacy_malouf_hilo_cover_entry",
        )
        entry.add_to_hass(hass)

        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(hass)
        registry.async_get_or_create(
            "cover",
            DOMAIN,
            "AA:BB:CC:DD:EE:02_head",
            config_entry=entry,
            suggested_object_id="legacy_malouf_hi_lo_bed_head",
        )
        registry.async_get_or_create(
            "cover",
            DOMAIN,
            "AA:BB:CC:DD:EE:02_feet",
            config_entry=entry,
            suggested_object_id="legacy_malouf_hi_lo_bed_feet",
        )

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert registry.async_get_entity_id("cover", DOMAIN, "AA:BB:CC:DD:EE:02_head") is None
        assert registry.async_get_entity_id("cover", DOMAIN, "AA:BB:CC:DD:EE:02_feet") is None

    async def test_box25_cover_entities_use_box25_layout(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """BOX25 should expose head/feet/lumbar/tilt covers, not back/legs."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Sleepy's BOX25 Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:25",
                CONF_NAME: "Sleepy's BOX25 Bed",
                CONF_BED_TYPE: BED_TYPE_SLEEPYS_BOX25,
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: False,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:25",
            entry_id="sleepys_box25_cover_entry",
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(hass)
        for key in ("head", "feet", "lumbar", "tilt"):
            assert registry.async_get_entity_id(
                "cover", DOMAIN, f"AA:BB:CC:DD:EE:25_{key}"
            ) is not None

        assert registry.async_get_entity_id("cover", DOMAIN, "AA:BB:CC:DD:EE:25_back") is None
        assert registry.async_get_entity_id("cover", DOMAIN, "AA:BB:CC:DD:EE:25_legs") is None

    async def test_box25_cover_setup_removes_stale_back_and_legs(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """BOX25 setup should remove stale back/legs cover entities."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Legacy Sleepy's BOX25 Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:26",
                CONF_NAME: "Legacy Sleepy's BOX25 Bed",
                CONF_BED_TYPE: BED_TYPE_SLEEPYS_BOX25,
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: False,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:26",
            entry_id="sleepys_box25_stale_cover_entry",
        )
        entry.add_to_hass(hass)

        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(hass)
        registry.async_get_or_create(
            "cover",
            DOMAIN,
            "AA:BB:CC:DD:EE:26_back",
            config_entry=entry,
            suggested_object_id="legacy_sleepys_box25_back",
        )
        registry.async_get_or_create(
            "cover",
            DOMAIN,
            "AA:BB:CC:DD:EE:26_legs",
            config_entry=entry,
            suggested_object_id="legacy_sleepys_box25_legs",
        )

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert registry.async_get_entity_id("cover", DOMAIN, "AA:BB:CC:DD:EE:26_back") is None
        assert registry.async_get_entity_id("cover", DOMAIN, "AA:BB:CC:DD:EE:26_legs") is None

    async def test_cover_open_close(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        enable_custom_integrations,
    ):
        """Test cover open and close commands."""
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
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
        enable_custom_integrations,
    ):
        """Test cover stop command."""
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
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


class TestNumberEntities:
    """Test number entities."""

    async def test_box25_number_entities_only_include_head_and_feet_position(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """BOX25 should only create head_position and feet_position number entities."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Sleepy's BOX25 Numbers",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:27",
                CONF_NAME: "Sleepy's BOX25 Numbers",
                CONF_BED_TYPE: BED_TYPE_SLEEPYS_BOX25,
                CONF_MOTOR_COUNT: 4,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: False,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:27",
            entry_id="sleepys_box25_number_entry",
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(hass)
        assert registry.async_get_entity_id(
            "number", DOMAIN, "AA:BB:CC:DD:EE:27_head_position"
        ) is not None
        assert registry.async_get_entity_id(
            "number", DOMAIN, "AA:BB:CC:DD:EE:27_feet_position"
        ) is not None
        assert (
            registry.async_get_entity_id("number", DOMAIN, "AA:BB:CC:DD:EE:27_back_position")
            is None
        )
        assert (
            registry.async_get_entity_id("number", DOMAIN, "AA:BB:CC:DD:EE:27_legs_position")
            is None
        )


class TestButtonEntities:
    """Test button entities."""

    def test_massage_buttons_cancel_running_commands(self):
        """Massage buttons should preempt long-running movement/preset actions."""
        massage_buttons = [desc for desc in BUTTON_DESCRIPTIONS if desc.key.startswith("massage_")]

        assert len(massage_buttons) > 0
        assert all(desc.cancel_movement for desc in massage_buttons)

    async def test_button_entities_created(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Test button entities are created."""
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        button_states = [
            state for state in hass.states.async_all() if state.entity_id.startswith("button.")
        ]

        # Linak has memory_slot_count=6 and supports_memory_programming=True, but supports_preset_flat=False
        # Should have: memory presets (6) + program_memory (6) + stop_all (1) + connect (1) + disconnect (1) = 15
        # Massage buttons are excluded because has_massage=False
        assert len(button_states) == 15

    async def test_button_entities_with_massage(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict,
        mock_coordinator_connected,
        enable_custom_integrations,
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

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        button_states = [
            state for state in hass.states.async_all() if state.entity_id.startswith("button.")
        ]

        # Should have: base (15) + massage buttons (11) = 26
        # Base: memory presets (6) + program_memory (6) + stop_all (1) + connect (1) + disconnect (1) = 15
        # (Linak has memory_slot_count=6, supports_memory_programming=True, supports_preset_flat=False)
        assert len(button_states) == 26

    async def test_kaidi_entities_expose_book_leisure_direct_position_and_filtered_massage(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Kaidi should expose the newly wired presets, direct-position controls, and clean light/massage entities."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Kaidi Feature Bed",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:40",
                CONF_NAME: "Kaidi Feature Bed",
                CONF_BED_TYPE: BED_TYPE_KAIDI,
                CONF_PROTOCOL_VARIANT: KAIDI_VARIANT_SEAT_1,
                CONF_KAIDI_PRODUCT_ID: 135,
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: True,
                CONF_DISABLE_ANGLE_SENSING: False,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="AA:BB:CC:DD:EE:40",
            entry_id="kaidi_feature_entry",
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(hass)

        assert registry.async_get_entity_id(
            "button", DOMAIN, "AA:BB:CC:DD:EE:40_preset_tv"
        ) is not None
        assert registry.async_get_entity_id(
            "button", DOMAIN, "AA:BB:CC:DD:EE:40_preset_lounge"
        ) is not None
        assert registry.async_get_entity_id(
            "switch", DOMAIN, "AA:BB:CC:DD:EE:40_under_bed_lights"
        ) is not None
        assert (
            registry.async_get_entity_id("button", DOMAIN, "AA:BB:CC:DD:EE:40_toggle_light")
            is None
        )

        assert registry.async_get_entity_id(
            "number", DOMAIN, "AA:BB:CC:DD:EE:40_back_position"
        ) is not None
        assert registry.async_get_entity_id(
            "number", DOMAIN, "AA:BB:CC:DD:EE:40_legs_position"
        ) is not None
        assert registry.async_get_entity_id(
            "cover", DOMAIN, "AA:BB:CC:DD:EE:40_lumbar"
        ) is not None
        assert (
            registry.async_get_entity_id("number", DOMAIN, "AA:BB:CC:DD:EE:40_head_position")
            is None
        )

        assert registry.async_get_entity_id(
            "select", DOMAIN, "AA:BB:CC:DD:EE:40_massage_timer"
        ) is not None
        assert registry.async_get_entity_id(
            "button", DOMAIN, "AA:BB:CC:DD:EE:40_massage_all_toggle"
        ) is not None
        assert (
            registry.async_get_entity_id(
                "button", DOMAIN, "AA:BB:CC:DD:EE:40_massage_mode_step"
            )
            is None
        )
        assert (
            registry.async_get_entity_id("button", DOMAIN, "AA:BB:CC:DD:EE:40_massage_all_up")
            is None
        )
        assert (
            registry.async_get_entity_id(
                "button", DOMAIN, "AA:BB:CC:DD:EE:40_massage_head_toggle"
            )
            is None
        )
        assert (
            registry.async_get_entity_id(
                "button", DOMAIN, "AA:BB:CC:DD:EE:40_massage_foot_toggle"
            )
            is None
        )

    async def test_preset_button_press(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        enable_custom_integrations,
    ):
        """Test pressing a preset button sends command."""
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
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
        enable_custom_integrations,
    ):
        """Test switch entities are created."""
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        switch_states = [
            state for state in hass.states.async_all() if state.entity_id.startswith("switch.")
        ]

        # Should have under-bed lights switch
        assert len(switch_states) == 1


class TestLightEntities:
    """Test light entities."""

    async def test_richmat_qrrm_light_entity_created_and_toggle_button_removed(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """QRRM beds should expose a light entity instead of the legacy toggle button."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Casper QRRM Bed",
            data={
                CONF_ADDRESS: "57:4C:62:C3:39:05",
                CONF_NAME: "Casper QRRM Bed",
                CONF_BED_TYPE: BED_TYPE_RICHMAT,
                CONF_PROTOCOL_VARIANT: "wilinke",
                CONF_RICHMAT_REMOTE: "qrrm",
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="57:4C:62:C3:39:05",
            entry_id="richmat_qrrm_light_entity_entry",
        )
        entry.add_to_hass(hass)

        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(hass)
        registry.async_get_or_create(
            "button",
            DOMAIN,
            "57:4C:62:C3:39:05_toggle_light",
            config_entry=entry,
            suggested_object_id="casper_qrrm_bed_toggle_light",
        )

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert registry.async_get_entity_id(
            "light", DOMAIN, "57:4C:62:C3:39:05_under_bed_lights"
        ) is not None
        assert (
            registry.async_get_entity_id("switch", DOMAIN, "57:4C:62:C3:39:05_under_bed_lights")
            is None
        )
        assert (
            registry.async_get_entity_id("button", DOMAIN, "57:4C:62:C3:39:05_toggle_light")
            is None
        )
        assert registry.async_get_entity_id(
            "select", DOMAIN, "57:4C:62:C3:39:05_light_timer"
        ) is not None

    async def test_richmat_qrrm_light_turn_on_and_off(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        enable_custom_integrations,
    ):
        """QRRM light entity should power on, set color, and power off explicitly."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Casper QRRM Bed",
            data={
                CONF_ADDRESS: "57:4C:62:C3:39:05",
                CONF_NAME: "Casper QRRM Bed",
                CONF_BED_TYPE: BED_TYPE_RICHMAT,
                CONF_PROTOCOL_VARIANT: "wilinke",
                CONF_RICHMAT_REMOTE: "qrrm",
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="57:4C:62:C3:39:05",
            entry_id="richmat_qrrm_light_service_entry",
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        coordinator = hass.data[DOMAIN][entry.entry_id]
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id(
            "light", DOMAIN, "57:4C:62:C3:39:05_under_bed_lights"
        )
        assert entity_id is not None

        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            "light",
            "turn_on",
            {
                "entity_id": entity_id,
                "rgb_color": [1, 221, 255],
            },
            blocking=True,
        )

        assert mock_bleak_client.write_gatt_char.call_args_list == [
            call(
                coordinator.controller.control_characteristic_uuid,
                coordinator.controller._build_light_power_command(is_on=True),
                response=True,
            ),
            call(
                coordinator.controller.control_characteristic_uuid,
                coordinator.controller._build_light_color_command((1, 221, 255)),
                response=True,
            ),
        ]
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == STATE_ON
        assert state.attributes["rgb_color"] == (1, 221, 255)

        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            "light",
            "turn_off",
            {"entity_id": entity_id},
            blocking=True,
        )

        mock_bleak_client.write_gatt_char.assert_called_with(
            coordinator.controller.control_characteristic_uuid,
            coordinator.controller._build_light_power_command(is_on=False),
            response=True,
        )

    async def test_richmat_qrrm_light_timer_select_supports_three_minutes(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        enable_custom_integrations,
    ):
        """QRRM timer select should expose minute-granular RGB-strip timers."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Casper QRRM Bed",
            data={
                CONF_ADDRESS: "57:4C:62:C3:39:05",
                CONF_NAME: "Casper QRRM Bed",
                CONF_BED_TYPE: BED_TYPE_RICHMAT,
                CONF_PROTOCOL_VARIANT: "wilinke",
                CONF_RICHMAT_REMOTE: "qrrm",
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="57:4C:62:C3:39:05",
            entry_id="richmat_qrrm_light_timer_service_entry",
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        coordinator = hass.data[DOMAIN][entry.entry_id]
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id(
            "select", DOMAIN, "57:4C:62:C3:39:05_light_timer"
        )
        assert entity_id is not None

        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity_id, "option": "3 min"},
            blocking=True,
        )

        mock_bleak_client.write_gatt_char.assert_called_with(
            coordinator.controller.control_characteristic_uuid,
            coordinator.controller._build_light_timer_command(3),
            response=True,
        )

    async def test_richmat_legacy_rgb_light_entity_created_and_toggle_button_removed(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        enable_custom_integrations,
    ):
        """Legacy Richmat RGB beds should expose a light entity and timer select."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Forty Winks VIRM Bed",
            data={
                CONF_ADDRESS: "57:4C:62:C3:39:06",
                CONF_NAME: "Forty Winks VIRM Bed",
                CONF_BED_TYPE: BED_TYPE_RICHMAT,
                CONF_PROTOCOL_VARIANT: "wilinke",
                CONF_RICHMAT_REMOTE: "virm",
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="57:4C:62:C3:39:06",
            entry_id="richmat_virm_light_entity_entry",
        )
        entry.add_to_hass(hass)

        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(hass)
        registry.async_get_or_create(
            "button",
            DOMAIN,
            "57:4C:62:C3:39:06_toggle_light",
            config_entry=entry,
            suggested_object_id="forty_winks_virm_bed_toggle_light",
        )

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert registry.async_get_entity_id(
            "light", DOMAIN, "57:4C:62:C3:39:06_under_bed_lights"
        ) is not None
        assert (
            registry.async_get_entity_id("switch", DOMAIN, "57:4C:62:C3:39:06_under_bed_lights")
            is None
        )
        assert (
            registry.async_get_entity_id("button", DOMAIN, "57:4C:62:C3:39:06_toggle_light")
            is None
        )
        assert registry.async_get_entity_id(
            "select", DOMAIN, "57:4C:62:C3:39:06_light_timer"
        ) is not None

    async def test_richmat_legacy_rgb_light_turn_on_and_off(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        enable_custom_integrations,
    ):
        """Legacy Richmat RGB lights should use explicit ON and toggle-based OFF."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Forty Winks VIRM Bed",
            data={
                CONF_ADDRESS: "57:4C:62:C3:39:06",
                CONF_NAME: "Forty Winks VIRM Bed",
                CONF_BED_TYPE: BED_TYPE_RICHMAT,
                CONF_PROTOCOL_VARIANT: "wilinke",
                CONF_RICHMAT_REMOTE: "virm",
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="57:4C:62:C3:39:06",
            entry_id="richmat_virm_light_service_entry",
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        coordinator = hass.data[DOMAIN][entry.entry_id]
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id(
            "light", DOMAIN, "57:4C:62:C3:39:06_under_bed_lights"
        )
        assert entity_id is not None

        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            "light",
            "turn_on",
            {
                "entity_id": entity_id,
                "rgb_color": [1, 221, 255],
            },
            blocking=True,
        )

        assert mock_bleak_client.write_gatt_char.call_args_list == [
            call(
                coordinator.controller.control_characteristic_uuid,
                coordinator.controller._build_legacy_light_power_on_command(),
                response=True,
            ),
            call(
                coordinator.controller.control_characteristic_uuid,
                coordinator.controller._build_light_color_command((1, 221, 255)),
                response=True,
            ),
        ]
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == STATE_ON
        assert state.attributes["rgb_color"] == (1, 221, 255)

        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            "light",
            "turn_off",
            {"entity_id": entity_id},
            blocking=True,
        )

        mock_bleak_client.write_gatt_char.assert_called_with(
            coordinator.controller.control_characteristic_uuid,
            coordinator.controller._build_command(RichmatCommands.LIGHTS_TOGGLE),
            response=True,
        )

    async def test_richmat_legacy_rgb_light_timer_select_supports_three_minutes(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        enable_custom_integrations,
    ):
        """Legacy Richmat RGB timers should expose minute labels and send seconds."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Forty Winks VIRM Bed",
            data={
                CONF_ADDRESS: "57:4C:62:C3:39:06",
                CONF_NAME: "Forty Winks VIRM Bed",
                CONF_BED_TYPE: BED_TYPE_RICHMAT,
                CONF_PROTOCOL_VARIANT: "wilinke",
                CONF_RICHMAT_REMOTE: "virm",
                CONF_MOTOR_COUNT: 2,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id="57:4C:62:C3:39:06",
            entry_id="richmat_virm_light_timer_service_entry",
        )
        entry.add_to_hass(hass)

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        coordinator = hass.data[DOMAIN][entry.entry_id]
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id(
            "select", DOMAIN, "57:4C:62:C3:39:06_light_timer"
        )
        assert entity_id is not None

        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity_id, "option": "3 min"},
            blocking=True,
        )

        mock_bleak_client.write_gatt_char.assert_called_with(
            coordinator.controller.control_characteristic_uuid,
            coordinator.controller._build_light_timer_command(180),
            response=True,
        )

    async def test_switch_turn_on_off(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        enable_custom_integrations,
    ):
        """Test turning switch on and off."""
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
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
        enable_custom_integrations,
    ):
        """Test sensor entities are not created when angle sensing is disabled."""
        # Default config has disable_angle_sensing=True
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
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
        enable_custom_integrations,
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

        await hass.config_entries.async_setup(entry.entry_id)
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

    async def test_entities_available_when_connected(
        self,
        hass: HomeAssistant,
        mock_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        enable_custom_integrations,
    ):
        """Test entities are available when coordinator is connected."""
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        # All entities should be available (not STATE_UNAVAILABLE)
        cover_entities = [
            state for state in hass.states.async_all() if state.entity_id.startswith("cover.")
        ]

        for state in cover_entities:
            current_state = hass.states.get(state.entity_id)
            assert current_state.state != STATE_UNAVAILABLE
