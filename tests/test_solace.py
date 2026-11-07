"""Tests for Solace bed controller."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.solace import (
    SolaceCommands,
    SolaceController,
    SolaceProfile,
    build_solace_alarm_command,
    build_solace_clock_command,
    resolve_solace_profile,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_SOLACE,
    CONF_BED_TYPE,
    CONF_BLE_DEVICE_NAME,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    SOLACE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.number import _number_entities_for
from custom_components.adjustable_bed.profiles.ff_frame import SOLACE_PROFILES
from tests.state_helpers import published


@pytest.fixture
def mock_solace_config_entry_data() -> dict:
    """Return mock config entry data for Solace bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Solace Test Bed",
        CONF_BED_TYPE: BED_TYPE_SOLACE,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: False,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_solace_config_entry(
    hass: HomeAssistant, mock_solace_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Solace bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Solace Test Bed",
        data=mock_solace_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="solace_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


class TestSolaceController:
    """Test Solace controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports correct characteristic UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == SOLACE_CHAR_UUID

    async def test_write_command_not_connected(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command when not connected raises error."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        mock_bleak_client.is_connected = False

        with pytest.raises(ConnectionError):
            await coordinator.controller.write_command(SolaceCommands.MOTOR_STOP)


class TestSolaceProfiles:
    """Test evidence-backed device-name routing and capability isolation."""

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("QMS-IQ-123", SOLACE_PROFILES["home_k1"]),
            ("QMS-NQ", SOLACE_PROFILES["home_k1"]),
            ("QMS-JQ-D", SOLACE_PROFILES["home_k2"]),
            ("QMS4", SOLACE_PROFILES["home_k2"]),
            ("QMS4-QMS3", SOLACE_PROFILES["home_k2"]),
            ("QMS-IQ-QMS4", SOLACE_PROFILES["home_k1"]),
            ("QMS2", SOLACE_PROFILES["common"]),
            ("QMS-MQ-123", SOLACE_PROFILES["common"]),
            ("SealyMF Base", SOLACE_PROFILES["motion_flex"]),
            ("My QMS2", SOLACE_PROFILES["common"]),
            ("S4-Y-192-461000AD", SOLACE_PROFILES["legacy_s4_y"]),
            ("S3-Y-192-461000AD", SOLACE_PROFILES["unverified"]),
            ("Other-QMS2", SOLACE_PROFILES["unverified"]),
            ("Other-SealyMF", SOLACE_PROFILES["unverified"]),
            ("Solace Smart Bed", SOLACE_PROFILES["unverified"]),
        ],
    )

    def test_profile_resolution(self, name: str, expected: SolaceProfile) -> None:
        assert resolve_solace_profile(name) is expected

    @pytest.mark.parametrize(
        ("name", "motor_keys", "massage", "lights", "timer"),
        [
            ("QMS-IQ", {"back", "legs", "head", "hip"}, True, False, True),
            ("QMS4", {"back", "legs", "head", "lumbar"}, True, False, True),
            ("QMS2", {"back", "legs"}, False, False, True),
            ("SealyMF", {"back", "legs"}, False, True, True),
            (
                "S4-Y-192-461000AD",
                {"back", "legs", "bed_height", "tilt"},
                False,
                False,
                False,
            ),
            ("Solace Smart Bed", {"back", "legs"}, False, False, False),
        ],
    )

    def test_profile_capabilities(
        self,
        name: str,
        motor_keys: set[str],
        massage: bool,
        lights: bool,
        timer: bool,
    ) -> None:
        coordinator = MagicMock()
        coordinator.ble_device_name = name
        controller = SolaceController(coordinator)

        assert {spec.key for spec in controller.motor_control_specs} == motor_keys
        assert controller.supports_massage is massage
        assert controller.supports_lights is lights
        assert controller.supports_light_level_control is lights
        assert controller.supports_light_timer is timer
        assert controller.memory_slot_count == (0 if name == "Solace Smart Bed" else 2)
        assert controller.supports_preset_flat is (name != "Solace Smart Bed")
        assert controller.supports_preset_tv is (name != "Solace Smart Bed")
        assert controller.supports_memory_presets is (name != "Solace Smart Bed")

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("QMS-IQ", "q1"),
            ("QMS-JQ-D", "q1"),
            ("QMS-JQ-D-QMS3", "q2"),
            ("QMS-JQ-D-QMS2", "q2"),
            ("QMS2", "q2"),
            ("SealyMF", "q2"),
            ("S4-Y-192-461000AD", None),
            ("Solace Smart Bed", None),
        ],
    )

    def test_query_family(self, name: str, expected: str | None) -> None:
        coordinator = MagicMock()
        coordinator.ble_device_name = name

        assert SolaceController(coordinator)._query_family == expected

    async def test_offline_profile_uses_persisted_observed_name(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry_data: dict,
    ) -> None:
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Renamed bedroom bed",
            data={
                **mock_solace_config_entry_data,
                CONF_NAME: "Renamed bedroom bed",
                CONF_BLE_DEVICE_NAME: "SealyMF Base",
            },
            unique_id="AA:BB:CC:DD:EE:11",
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)

        await coordinator.async_prime_offline_controller()

        assert isinstance(coordinator.capability_controller, SolaceController)
        assert coordinator.capability_controller.profile is SOLACE_PROFILES["motion_flex"]

    async def test_observed_name_is_persisted_for_offline_routing(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        hass.data.setdefault(DOMAIN, {})[mock_solace_config_entry.entry_id] = coordinator

        coordinator._record_observed_ble_device_name("SealyMF Base")

        assert mock_solace_config_entry.data[CONF_BLE_DEVICE_NAME] == "SealyMF Base"
        assert coordinator.consume_internal_entry_update(mock_solace_config_entry) is True

    async def test_unknown_profile_keeps_existing_light_level_entity(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
    ) -> None:
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        registry = er.async_get(hass)
        stale = registry.async_get_or_create(
            "number",
            DOMAIN,
            "AA:BB:CC:DD:EE:FF_light_level",
            config_entry=mock_solace_config_entry,
        )

        assert coordinator.capability_controller is None

        _number_entities_for(hass, coordinator)

        assert registry.async_get(stale.entity_id) is not None

    def test_motionflex_variable_frame_vectors(self) -> None:
        assert build_solace_clock_command(datetime(2023, 12, 31, 23, 59, 58)).hex() == (
            "ffffffff01000111235958072312315005"
        )
        assert build_solace_alarm_command(
            enabled=False,
            hour=0,
            minute=0,
            weekdays=(),
            mode="no_action",
            massage=False,
            sound="none",
        ).hex() == "ffffffff01000213a10000000000030000b604"

    def test_alarm_weekday_mask_ignores_duplicate_days(self) -> None:
        command = build_solace_alarm_command(
            enabled=True,
            hour=6,
            minute=30,
            weekdays=(1, 1, 2),
            mode="zero_g",
            massage=False,
            sound="alarm",
        )

        assert command[12] == (1 << 1) | (1 << 2)

    async def test_motionflex_startup_syncs_clock_before_queries(self) -> None:
        coordinator = MagicMock()
        coordinator.ble_device_name = "SealyMF Base"
        controller = SolaceController(coordinator)
        coordinator.controller = controller
        controller.write_command = AsyncMock()

        async def execute_query(query_fn, **kwargs):
            return await query_fn(controller)

        coordinator.async_execute_controller_query = AsyncMock(side_effect=execute_query)
        now = datetime(2023, 12, 31, 23, 59, 58)
        with (
            patch("custom_components.adjustable_bed.beds.solace.dt_util.now", return_value=now),
            patch(
                "custom_components.adjustable_bed.beds.solace.asyncio.sleep",
                new_callable=AsyncMock,
            ),
        ):
            await controller._async_query_preset_states("q2")

        assert [call.args[0] for call in controller.write_command.await_args_list] == [
            build_solace_clock_command(now),
            *SolaceCommands.QUERY_Q2,
            SolaceCommands.LIGHT_STATUS_QUERY,
        ]

    async def test_stale_startup_query_does_not_write_to_replacement_controller(
        self,
    ) -> None:
        coordinator = MagicMock()
        coordinator.ble_device_name = "QMS-IQ"
        controller = SolaceController(coordinator)
        replacement = MagicMock()
        replacement.write_command = AsyncMock()
        coordinator.controller = controller

        async def execute_query(query_fn, **kwargs):
            coordinator.controller = replacement
            return await query_fn(replacement)

        coordinator.async_execute_controller_query = AsyncMock(side_effect=execute_query)
        with patch(
            "custom_components.adjustable_bed.beds.solace.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            await controller._async_query_preset_states("q1")

        replacement.write_command.assert_not_awaited()

    async def test_motionflex_audio_commands_match_artifact_vectors(self) -> None:
        coordinator = MagicMock()
        coordinator.ble_device_name = "SealyMF Base"
        controller = SolaceController(coordinator)
        controller.write_command = AsyncMock()

        await controller.solace_select_music(3)
        await controller.solace_select_music(5, preview=True)
        await controller.solace_set_audio_volume(4)
        await controller.solace_query_audio_volume()

        assert [call.args[0].hex() for call in controller.write_command.await_args_list] == [
            "ffffffff0100130b031e04",
            "ffffffff0100130b85a004",
            "ffffffff0100140b042004",
            "ffffffff0100150b001d04",
        ]

    async def test_alarm_programming_publishes_requested_state(self) -> None:
        coordinator = MagicMock()
        coordinator.ble_device_name = "SealyMF Base"
        controller = SolaceController(coordinator)
        controller.write_command = AsyncMock()

        await controller.program_solace_alarm(
            enabled=True,
            hour=6,
            minute=45,
            weekdays=(1, 3, 7),
            mode="memory_1",
            massage=True,
            sound="music_5",
        )

        assert coordinator.handle_controller_state_updates.call_count == 1
        assert published(*coordinator.handle_controller_state_updates.call_args.args) == {
                "solace_alarm_enabled": True,
                "solace_alarm_time": "06:45",
                "solace_alarm_weekdays": "1,3,7",
                "solace_alarm_mode": "memory_1",
                "solace_alarm_massage": True,
                "solace_alarm_sound": "music_5",
            }

    async def test_motionflex_light_writes_publish_selected_level(self) -> None:
        coordinator = MagicMock()
        coordinator.ble_device_name = "SealyMF Base"
        controller = SolaceController(coordinator)
        controller.write_command = AsyncMock()

        await controller.set_light_level(4)
        coordinator.handle_controller_state_update.assert_called_once_with("light_level", 4)

        coordinator.handle_controller_state_update.reset_mock()
        await controller.lights_off()
        coordinator.handle_controller_state_update.assert_called_once_with("light_level", 0)

    def test_motionflex_notification_parser_tracks_audio_and_alarm(self) -> None:
        coordinator = MagicMock()
        coordinator.ble_device_name = "SealyMF Base"
        controller = SolaceController(coordinator)

        controller._parse_notification(bytes.fromhex("FF FF FF FF 01 00 15 0B AF 00 00"))
        assert coordinator.handle_controller_state_updates.call_count == 1
        assert published(*coordinator.handle_controller_state_updates.call_args.args) == {"solace_audio_volume": 15}

        coordinator.handle_controller_state_updates.reset_mock()
        controller._parse_notification(bytes.fromhex("FF FF FF FF 05 00 01 FE 00 00 00"))
        coordinator.handle_controller_state_updates.assert_not_called()

        coordinator.handle_controller_state_updates.reset_mock()
        controller._parse_notification(
            bytes.fromhex("FF FF FF FF 01 00 04 13 0F 06 45 00 8A 01 02 01 15")
        )
        assert coordinator.handle_controller_state_updates.call_count == 1
        assert published(*coordinator.handle_controller_state_updates.call_args.args) == {
                "solace_alarm_enabled": True,
                "solace_alarm_time": "06:45",
                "solace_alarm_weekdays": "1,3,7",
                "solace_alarm_mode": "memory_1",
                "solace_alarm_massage": True,
                "solace_alarm_sound": "music_5",
            }

    async def test_audio_query_reply_updates_sensor_entity(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_async_ble_device_from_address: MagicMock,
        mock_bleak_client: MagicMock,
        enable_custom_integrations,
    ) -> None:
        """The query result should be observable through Home Assistant state."""
        del mock_coordinator_connected, enable_custom_integrations
        mock_async_ble_device_from_address.return_value.name = "SealyMF Base"
        hass.config_entries.async_update_entry(
            mock_solace_config_entry,
            data={
                **mock_solace_config_entry.data,
                CONF_DISCONNECT_AFTER_COMMAND: True,
            },
        )

        await hass.config_entries.async_setup(mock_solace_config_entry.entry_id)
        await hass.async_block_till_done()
        mock_bleak_client.disconnect.reset_mock()

        devices = dr.async_entries_for_config_entry(
            dr.async_get(hass), mock_solace_config_entry.entry_id
        )
        assert devices
        await hass.services.async_call(
            DOMAIN,
            "solace_audio",
            {"device_id": [devices[0].id], "action": "query"},
            blocking=True,
        )
        mock_bleak_client.write_gatt_char.assert_any_call(
            SOLACE_CHAR_UUID,
            SolaceCommands.AUDIO_VOLUME_QUERY,
            response=True,
        )
        mock_bleak_client.disconnect.assert_not_awaited()

        notify_callback = mock_bleak_client.start_notify.await_args.args[1]
        notify_callback(
            SOLACE_CHAR_UUID,
            bytearray.fromhex("FF FF FF FF 01 00 15 0B 05 00 00"),
        )

        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id(
            "sensor",
            DOMAIN,
            "AA:BB:CC:DD:EE:FF_solace_audio_volume",
        )
        assert entity_id is not None
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == "5"

        notify_callback(
            SOLACE_CHAR_UUID,
            bytearray.fromhex("FF FF FF FF 01 00 04 13 0F 06 45 00 8A 01 02 01 15"),
        )
        alarm_entity_id = registry.async_get_entity_id(
            "binary_sensor",
            DOMAIN,
            "AA:BB:CC:DD:EE:FF_solace_alarm_enabled",
        )
        assert alarm_entity_id is not None
        alarm_state = hass.states.get(alarm_entity_id)
        assert alarm_state is not None
        assert alarm_state.state == "on"
        assert alarm_state.attributes["solace_alarm_time"] == "06:45"
        assert alarm_state.attributes["solace_alarm_weekdays"] == "1,3,7"
        assert alarm_state.attributes["solace_alarm_mode"] == "memory_1"
        assert alarm_state.attributes["solace_alarm_massage"] is True
        assert alarm_state.attributes["solace_alarm_sound"] == "music_5"

        notify_callback(
            SOLACE_CHAR_UUID,
            bytearray.fromhex("FF FF FF FF 05 00 01 07 00 00 00"),
        )
        light_entity_id = registry.async_get_entity_id(
            "number",
            DOMAIN,
            "AA:BB:CC:DD:EE:FF_light_level",
        )
        assert light_entity_id is not None
        light_state = hass.states.get(light_entity_id)
        assert light_state is not None
        assert light_state.state == "7.0"

    async def test_non_motionflex_setup_removes_motionflex_only_entities(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_async_ble_device_from_address: MagicMock,
        enable_custom_integrations,
    ) -> None:
        """A narrowed Solace profile should remove its old broad brightness entity."""
        del mock_coordinator_connected, enable_custom_integrations
        mock_async_ble_device_from_address.return_value.name = "QMS-IQ"
        registry = er.async_get(hass)
        stale = registry.async_get_or_create(
            "number",
            DOMAIN,
            "AA:BB:CC:DD:EE:FF_light_level",
            config_entry=mock_solace_config_entry,
        )
        stale_audio = registry.async_get_or_create(
            "sensor",
            DOMAIN,
            "AA:BB:CC:DD:EE:FF_solace_audio_volume",
            config_entry=mock_solace_config_entry,
        )
        stale_alarm = registry.async_get_or_create(
            "binary_sensor",
            DOMAIN,
            "AA:BB:CC:DD:EE:FF_solace_alarm_enabled",
            config_entry=mock_solace_config_entry,
        )

        await hass.config_entries.async_setup(mock_solace_config_entry.entry_id)
        await hass.async_block_till_done()

        assert registry.async_get(stale.entity_id) is None
        assert registry.async_get(stale_audio.entity_id) is None
        assert registry.async_get(stale_alarm.entity_id) is None

    async def test_query_sequence_is_serialized_with_app_pacing(self) -> None:
        coordinator = MagicMock()
        coordinator.ble_device_name = "QMS-IQ"
        controller = SolaceController(coordinator)
        coordinator.controller = controller
        controller.write_command = AsyncMock()

        async def execute_query(query_fn, **kwargs):
            assert kwargs["skip_disconnect"] is True
            assert kwargs["preemptible"] is True
            assert callable(kwargs["run_if"])
            return await query_fn(controller)

        coordinator.async_execute_controller_query = AsyncMock(side_effect=execute_query)
        sleep = AsyncMock()
        with patch("custom_components.adjustable_bed.beds.solace.asyncio.sleep", sleep):
            await controller._async_query_preset_states("q1")

        assert [call.args[0] for call in controller.write_command.await_args_list] == list(
            SolaceCommands.QUERY_Q1
        )
        assert [call.args[0] for call in sleep.await_args_list] == [
            0.3,
            0.5,
            0.5,
            0.5,
            0.5,
        ]
        assert coordinator.handle_controller_state_updates.call_count == 1
        assert published(*coordinator.handle_controller_state_updates.call_args.args) == {
                "solace_tv_selected": False,
                "solace_zero_g_selected": False,
                "solace_memory_1_selected": False,
                "solace_memory_2_selected": False,
                "solace_anti_snore_selected": False,
            }

    def test_notification_parser_tracks_preset_selection(self) -> None:
        coordinator = MagicMock()
        coordinator.ble_device_name = "QMS2"
        controller = SolaceController(coordinator)

        controller._parse_notification(bytes.fromhex("00 FF FF FF FF 03 06 00 09 00"))
        assert coordinator.handle_controller_state_updates.call_count == 1
        assert published(*coordinator.handle_controller_state_updates.call_args.args) == {"solace_zero_g_selected": True}

        coordinator.handle_controller_state_updates.reset_mock()
        controller._parse_notification(SolaceCommands.PROGRAM_MEMORY_1)
        assert coordinator.handle_controller_state_updates.call_count == 1
        assert published(*coordinator.handle_controller_state_updates.call_args.args) == {"solace_memory_1_selected": True}

    async def test_named_presets_use_selected_branch_after_status_reply(self) -> None:
        coordinator = MagicMock()
        coordinator.ble_device_name = "QMS2"
        coordinator.controller_state = {
            "solace_tv_selected": True,
            "solace_zero_g_selected": True,
            "solace_anti_snore_selected": True,
        }
        controller = SolaceController(coordinator)
        controller.write_command = AsyncMock()

        await controller.preset_tv()
        await controller.preset_zero_g()
        await controller.preset_anti_snore()

        assert [call.args[0] for call in controller.write_command.await_args_list] == [
            SolaceCommands.PRESET_TV_SELECTED,
            SolaceCommands.PRESET_ZERO_G_SELECTED,
            SolaceCommands.PRESET_ANTI_SNORE_SELECTED,
        ]

    async def test_program_memory_uses_selected_state_branch(self) -> None:
        coordinator = MagicMock()
        coordinator.ble_device_name = "QMS2"
        coordinator.controller_state = {
            "solace_memory_1_selected": True,
            "solace_memory_2_selected": False,
        }
        controller = SolaceController(coordinator)
        controller.write_command = AsyncMock()

        await controller.program_memory(1)
        await controller.program_memory(2)

        assert [call.args[0] for call in controller.write_command.await_args_list] == [
            SolaceCommands.PROGRAM_MEMORY_1_SELECTED,
            SolaceCommands.PROGRAM_MEMORY_2,
        ]


class TestSolacePresets:
    """Test Solace preset commands."""

    async def test_preset_flat(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset flat command."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_flat()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert [call.args[1] for call in calls] == [SolaceCommands.PRESET_FLAT_BED]

    async def test_s4_y_uses_deployed_legacy_all_flat_variant(self) -> None:
        coordinator = MagicMock()
        coordinator.ble_device_name = "S4-Y-192-461000AD"
        controller = SolaceController(coordinator)
        controller.write_command = AsyncMock()

        await controller.preset_flat()

        controller.write_command.assert_awaited_once()
        assert controller.write_command.await_args.args[0] == SolaceCommands.PRESET_LEGACY_ALL_FLAT

    async def test_preset_zero_g(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset zero gravity command."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_zero_g()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert [call.args[1] for call in calls] == [SolaceCommands.PRESET_ZERO_G]

    async def test_preset_tv(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset TV command."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_tv()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert [call.args[1] for call in calls] == [SolaceCommands.PRESET_TV]

    async def test_preset_anti_snore(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset anti-snore command."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_anti_snore()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert [call.args[1] for call in calls] == [SolaceCommands.PRESET_ANTI_SNORE]

    async def test_preset_yoga(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Yoga stays unavailable until its separate APK passes APK Protocol Audit."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_yoga is False
        with pytest.raises(NotImplementedError):
            await coordinator.controller.preset_yoga()
        mock_bleak_client.write_gatt_char.assert_not_called()

    @pytest.mark.parametrize(
        "memory_num,expected_command",
        [
            (1, SolaceCommands.PRESET_MEMORY_1),
            (2, SolaceCommands.PRESET_MEMORY_2),
        ],
    )

    async def test_preset_memory(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_command: bytes,
    ):
        """Test preset memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(memory_num)

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert [call.args[1] for call in calls] == [expected_command]

    @pytest.mark.parametrize(
        "memory_num,expected_command",
        [
            (1, SolaceCommands.PROGRAM_MEMORY_1),
            (2, SolaceCommands.PROGRAM_MEMORY_2),
        ],
    )

    async def test_program_memory(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        memory_num: int,
        expected_command: bytes,
    ):
        """Test program memory commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(memory_num)

        mock_bleak_client.write_gatt_char.assert_called_with(
            SOLACE_CHAR_UUID, expected_command, response=True
        )


class TestSolacePositionNotifications:
    """Test Solace position notification handling."""

    async def test_start_notify_no_support(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
    ):
        """Test start_notify stores callback without BLE subscription."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        await coordinator.controller.start_notify(callback)

        assert coordinator.controller._notify_callback is callback

    async def test_read_positions_noop(
        self,
        hass: HomeAssistant,
        mock_solace_config_entry,
        mock_coordinator_connected,
    ):
        """Test read_positions does nothing (not supported)."""
        coordinator = AdjustableBedCoordinator(hass, mock_solace_config_entry)
        await coordinator.async_connect()

        # Should complete without error
        await coordinator.controller.read_positions()


