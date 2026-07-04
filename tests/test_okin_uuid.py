"""Tests for Okin UUID-based bed controller."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.okin_uuid import (
    OKIN_UUID_REMOTES,
    OkinUuidComplexCommand,
    OkinUuidController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_OKIMAT,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    OKIMAT_WRITE_CHAR_UUID,
    VARIANT_AUTO,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

# Remote codes are plain strings now that the table is generated from the
# DewertOkin handset backend; keep readable aliases for the tests.
OKIMAT_VARIANT_80608 = "80608"
OKIMAT_VARIANT_82417 = "82417"
OKIMAT_VARIANT_82418 = "82418"
OKIMAT_VARIANT_88875 = "88875"
OKIMAT_VARIANT_89138 = "89138"
OKIMAT_VARIANT_93329 = "93329"
OKIMAT_VARIANT_93332 = "93332"
OKIMAT_VARIANT_94238 = "94238"
# A remote whose handset exposes massage (authoritative backend data).
OKIMAT_VARIANT_MASSAGE = "83126"


@pytest.fixture
def mock_okin_uuid_config_entry_data() -> dict:
    """Return mock config entry data for Okin UUID bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Okin UUID Test Bed",
        CONF_BED_TYPE: BED_TYPE_OKIMAT,
        CONF_PROTOCOL_VARIANT: OKIMAT_VARIANT_82417,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_okin_uuid_config_entry(
    hass: HomeAssistant, mock_okin_uuid_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Okin UUID bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Okin UUID Test Bed",
        data=mock_okin_uuid_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="okimat_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_okin_uuid_93329_config_entry_data() -> dict:
    """Return mock config entry data for Okin UUID 93329 bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Okin UUID 93329 Test Bed",
        CONF_BED_TYPE: BED_TYPE_OKIMAT,
        CONF_PROTOCOL_VARIANT: OKIMAT_VARIANT_93329,
        CONF_MOTOR_COUNT: 3,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_okin_uuid_93329_config_entry(
    hass: HomeAssistant, mock_okin_uuid_93329_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Okin UUID 93329 bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Okin UUID 93329 Test Bed",
        data=mock_okin_uuid_93329_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="okimat_93329_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_okin_uuid_94238_config_entry_data() -> dict:
    """Return mock config entry data for Okin UUID 94238 bed (complex commands)."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Okin UUID 94238 Test Bed",
        CONF_BED_TYPE: BED_TYPE_OKIMAT,
        CONF_PROTOCOL_VARIANT: OKIMAT_VARIANT_94238,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_okin_uuid_94238_config_entry(
    hass: HomeAssistant, mock_okin_uuid_94238_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for Okin UUID 94238 bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Okin UUID 94238 Test Bed",
        data=mock_okin_uuid_94238_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="okimat_94238_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_okin_uuid_massage_config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return a mock config entry for a massage-capable Okin UUID remote (83126)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Okin UUID Massage Test Bed",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "Okin UUID Massage Test Bed",
            CONF_BED_TYPE: BED_TYPE_OKIMAT,
            CONF_PROTOCOL_VARIANT: OKIMAT_VARIANT_MASSAGE,
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: True,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="okimat_massage_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


def _variant_coordinator(hass, variant, motor_count=2):
    """Build a connected-ready coordinator for an arbitrary remote variant."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=f"Okin UUID {variant}",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: f"Okin UUID {variant}",
            CONF_BED_TYPE: BED_TYPE_OKIMAT,
            CONF_PROTOCOL_VARIANT: variant,
            CONF_MOTOR_COUNT: motor_count,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id=f"okimat_{variant}_{motor_count}",
    )
    entry.add_to_hass(hass)
    return AdjustableBedCoordinator(hass, entry)


class TestOkinUuidController:
    """Test Okin UUID controller."""

    async def test_control_characteristic_uuid(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_config_entry,
        mock_coordinator_connected,
    ):
        """Test controller reports correct characteristic UUID."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == OKIMAT_WRITE_CHAR_UUID

    async def test_build_command(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_config_entry,
        mock_coordinator_connected,
    ):
        """Test command building format."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_config_entry)
        await coordinator.async_connect()

        # Okin UUID format: [0x04, 0x02, ...int_bytes]
        remote = OKIN_UUID_REMOTES[OKIMAT_VARIANT_82417]
        command = coordinator.controller._build_command(remote.back_up)

        assert len(command) == 6
        assert command[:2] == bytes([0x04, 0x02])
        # Command 0x1 in big-endian
        assert command[2:] == bytes([0x00, 0x00, 0x00, 0x01])

    async def test_variant_auto_defaults_to_82417(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
    ):
        """Test auto variant defaults to 82417."""
        entry_data = {
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "Okin UUID Test",
            CONF_BED_TYPE: BED_TYPE_OKIMAT,
            CONF_PROTOCOL_VARIANT: VARIANT_AUTO,
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        }
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Okin UUID Test",
            data=entry_data,
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id="okimat_auto_test",
        )
        entry.add_to_hass(hass)

        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()

        # Controller should use 82417 as default
        assert coordinator.controller._variant == OKIMAT_VARIANT_82417

    def test_rf_liteline_89138_uses_apk_profile(self):
        """Remote 89138 (RF-LITELINE) keeps the standard two-motor keycodes."""
        remote = OKIN_UUID_REMOTES[OKIMAT_VARIANT_89138]

        assert remote.flat == 0x100000AA
        assert remote.back_up == 0x1
        assert remote.back_down == 0x2
        assert remote.legs_up == 0x4
        assert remote.legs_down == 0x8

    # Authoritative per-code values from the DewertOkin handset backend
    # (GET /mobile-data/button/{code}). Flat is a per-code property, so codes in
    # the same model family can differ - these values replace the old
    # cross-referenced "alias" assumptions.
    @pytest.mark.parametrize(
        ("variant", "flat", "memory_1", "memory_2"),
        [
            ("82417", 0x000000AA, None, None),
            ("82620", 0x100000AA, None, None),
            ("83489", 0x100000AA, None, None),
            ("92461", 0x100000AA, None, None),
            ("82418", 0x000000AA, 0x1000, 0x2000),
            ("85058", 0x100000AA, 0x1000, 0x2000),
            ("93306", 0x100000AA, 0x1000, 0x2000),
            ("91246", 0x100000AA, 0x1000, 0x2000),
            ("92591", 0x100000AA, 0x1000, 0x2000),
            ("94238", 0x10000000, 0x1000, 0x2000),
        ],
    )
    def test_backend_remote_keycodes(self, variant, flat, memory_1, memory_2):
        """Each remote uses its authoritative backend Flat and memory keycodes."""
        remote = OKIN_UUID_REMOTES[variant]

        assert remote.flat == flat
        # Standard back/legs motor keycodes are universal across the family.
        assert remote.back_up == 0x1
        assert remote.back_down == 0x2
        assert remote.legs_up == 0x4
        assert remote.legs_down == 0x8
        assert remote.memory_1 == memory_1
        assert remote.memory_2 == memory_2

    async def test_write_command(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing a command to the bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_config_entry)
        await coordinator.async_connect()

        command = coordinator.controller._build_command(0)
        await coordinator.controller.write_command(command)

        mock_bleak_client.write_gatt_char.assert_called_with(
            OKIMAT_WRITE_CHAR_UUID, command, response=True
        )

    async def test_write_command_not_connected(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test writing command when not connected raises error."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_config_entry)
        await coordinator.async_connect()

        mock_bleak_client.is_connected = False

        with pytest.raises(ConnectionError):
            await coordinator.controller.write_command(coordinator.controller._build_command(0))


class TestOkinUuidMovement:
    """Test Okin UUID movement commands."""

    async def test_move_head_up(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head up sends commands followed by stop."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

        # Last call should be stop (zero command)
        last_command = calls[-1][0][1]
        expected_stop = coordinator.controller._build_command(0)
        assert last_command == expected_stop

    async def test_move_head_down(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move head down."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_down()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

    async def test_move_feet_up(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move feet up (maps to legs on basic remote)."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_feet_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 1

    async def test_stop_all(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test stop all sends zero command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.stop_all()

        expected_stop = coordinator.controller._build_command(0)
        mock_bleak_client.write_gatt_char.assert_called_with(
            OKIMAT_WRITE_CHAR_UUID, expected_stop, response=True
        )


class TestOkinUuidMultiMotor:
    """Test Okin UUID multi-motor command support."""

    def test_get_move_command_empty_state(self):
        """Test combined command with no active motors."""

        # Create controller without full coordinator setup
        class MockCoordinator:
            address = "AA:BB:CC:DD:EE:FF"

        controller = OkinUuidController(MockCoordinator(), OKIMAT_VARIANT_82417)
        assert controller._get_move_command() == 0

    def test_get_move_command_single_motor(self):
        """Test combined command with single motor."""

        class MockCoordinator:
            address = "AA:BB:CC:DD:EE:FF"

        controller = OkinUuidController(MockCoordinator(), OKIMAT_VARIANT_82417)
        remote = OKIN_UUID_REMOTES[OKIMAT_VARIANT_82417]

        # Set back motor to up
        controller._motor_state["back"] = remote.back_up
        assert controller._get_move_command() == remote.back_up

    def test_get_move_command_multiple_motors(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_config_entry,
    ):
        """Test combined command sums multiple motor values."""

        class MockCoordinator:
            address = "AA:BB:CC:DD:EE:FF"

        controller = OkinUuidController(MockCoordinator(), OKIMAT_VARIANT_82417)
        remote = OKIN_UUID_REMOTES[OKIMAT_VARIANT_82417]

        # Set both back and legs motors
        controller._motor_state["back"] = remote.back_up  # 0x1
        controller._motor_state["legs"] = remote.legs_up  # 0x4

        # Combined command should be sum: 0x1 + 0x4 = 0x5
        expected = remote.back_up + remote.legs_up
        assert controller._get_move_command() == expected

    def test_get_move_command_all_motors_93332(
        self,
        hass: HomeAssistant,
    ):
        """Test combined command with all four motors on 93332 remote."""

        class MockCoordinator:
            address = "AA:BB:CC:DD:EE:FF"

        controller = OkinUuidController(MockCoordinator(), OKIMAT_VARIANT_93332)
        remote = OKIN_UUID_REMOTES[OKIMAT_VARIANT_93332]

        # Set all four motors
        controller._motor_state["head"] = remote.head_up  # 0x10
        controller._motor_state["back"] = remote.back_up  # 0x1
        controller._motor_state["legs"] = remote.legs_up  # 0x4
        controller._motor_state["feet"] = remote.feet_up  # 0x40

        expected = remote.head_up + remote.back_up + remote.legs_up + remote.feet_up
        assert controller._get_move_command() == expected

    async def test_move_head_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move_head_up sends correct command value from remote config."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_head_up()

        remote = OKIN_UUID_REMOTES[OKIMAT_VARIANT_82417]
        expected_cmd = coordinator.controller._build_command(remote.back_up)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    async def test_move_legs_sends_correct_command(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test move_legs_down sends correct command value from remote config."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.move_legs_down()

        remote = OKIN_UUID_REMOTES[OKIMAT_VARIANT_82417]
        expected_cmd = coordinator.controller._build_command(remote.legs_down)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd


class TestOkinUuidPresets:
    """Test Okin UUID preset commands."""

    async def test_preset_flat_82417(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset flat command for 82417 remote."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_flat()

        remote = OKIN_UUID_REMOTES[OKIMAT_VARIANT_82417]
        expected_cmd = coordinator.controller._build_command(remote.flat)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    async def test_preset_flat_93329_different_value(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_93329_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset flat for 93329 uses different value (0x2A vs 0xAA)."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_93329_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_flat()

        remote = OKIN_UUID_REMOTES[OKIMAT_VARIANT_93329]
        expected_cmd = coordinator.controller._build_command(remote.flat)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd
        # Verify it's the 0x2A value
        assert first_call[0][1][5] == 0x2A

    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_preset_memory_available(
        self,
        _mock_sleep,
        hass: HomeAssistant,
        mock_okin_uuid_93329_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test preset memory commands on 93329 remote."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_93329_config_entry)
        await coordinator.async_connect()

        # Cancel the disconnect timer to prevent it from firing during the test
        coordinator._cancel_disconnect_timer()

        remote = OKIN_UUID_REMOTES[OKIMAT_VARIANT_93329]

        for memory_num, expected_value in [
            (1, remote.memory_1),
            (2, remote.memory_2),
            (3, remote.memory_3),
            (4, remote.memory_4),
        ]:
            mock_bleak_client.write_gatt_char.reset_mock()
            await coordinator.controller.preset_memory(memory_num)

            expected_cmd = coordinator.controller._build_command(expected_value)
            first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
            assert first_call[0][1] == expected_cmd

    async def test_preset_memory_not_available_on_basic(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test memory preset logs warning on basic remote without memory."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.preset_memory(1)

        assert "not available on remote" in caplog.text

    async def test_program_memory_available(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_93329_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test program memory on remote that supports it."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_93329_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(1)

        # Should have written the memory save command
        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) > 0

    async def test_program_memory_not_available(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog,
    ):
        """Test program memory logs warning on basic remote."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(1)

        assert "Memory save not available" in caplog.text

    async def test_program_memory_94238_backend_hold_timing(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_94238_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """94238 memory_save uses the backend 5s hold (25 x 200ms)."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_94238_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.program_memory(1)

        remote = OKIN_UUID_REMOTES[OKIMAT_VARIANT_94238]
        assert remote.memory_save == OkinUuidComplexCommand(0x10000, 25, 200)

        expected_cmd = coordinator.controller._build_command(remote.memory_save.data)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd
        assert len(mock_bleak_client.write_gatt_char.call_args_list) == 25

    async def test_execute_command_honours_complex_timing(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_config_entry,
        mock_coordinator_connected,
    ):
        """The OkinUuidComplexCommand mechanism passes its own count/delay."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_config_entry)
        await coordinator.async_connect()

        complex_cmd = OkinUuidComplexCommand(data=0x10000, count=25, wait_time=200)
        with patch.object(
            coordinator.controller, "write_command", new_callable=AsyncMock
        ) as mock_write:
            await coordinator.controller._execute_command(
                complex_cmd, default_count=10, default_delay_ms=100
            )

            mock_write.assert_called_once()
            _, kwargs = mock_write.call_args
            assert kwargs.get("repeat_count") == 25
            assert kwargs.get("repeat_delay_ms") == 200


class TestOkinUuidLights:
    """Test Okin UUID light commands."""

    async def test_lights_toggle(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test lights toggle command."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_toggle()

        remote = OKIN_UUID_REMOTES[OKIMAT_VARIANT_82417]
        expected_cmd = coordinator.controller._build_command(remote.toggle_lights)
        # Lights toggle sends multiple commands
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd

    async def test_lights_toggle_94238_backend_hold(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_94238_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """94238 UBL is a hold-style light key: backend 5s hold (50 x 100ms)."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_94238_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.lights_toggle()

        remote = OKIN_UUID_REMOTES[OKIMAT_VARIANT_94238]
        assert remote.toggle_lights == OkinUuidComplexCommand(0x20000, 50, 100)

        expected_cmd = coordinator.controller._build_command(remote.toggle_lights.data)
        first_call = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_call[0][1] == expected_cmd
        assert len(mock_bleak_client.write_gatt_char.call_args_list) == 50

    def test_lights_hidden_when_csv_says_no_ubl(self):
        """CSV codes with UBL=n (e.g. 63293) carry no light keycode."""
        assert OKIN_UUID_REMOTES["63293"].toggle_lights is None

    def test_csv_reconstructed_massage_map(self):
        """CSV-only massage codes (76208) get the modal massage keycodes."""
        remote = OKIN_UUID_REMOTES["76208"]
        assert remote.massage is not None
        assert remote.massage["mode1"] == 0x20000000
        assert remote.massage["stop"] == 0x400
        # Wave is not universal and must not be guessed.
        assert "wave" not in remote.massage


class TestOkinUuidMassage:
    """Test Okin UUID massage commands."""

    async def test_massage_not_advertised_without_config(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """A remote whose handset has no massage keys exposes no massage."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_massage is False
        # Massage calls are no-ops (no keycode to send) rather than wrong bytes.
        await coordinator.controller.massage_toggle()
        mock_bleak_client.write_gatt_char.assert_not_called()

    async def test_massage_toggle(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_massage_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Massage start/toggle sends the authoritative all-zones keycode."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_massage_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.supports_massage is True
        await coordinator.controller.massage_toggle()

        expected_cmd = coordinator.controller._build_command(0x200000)
        mock_bleak_client.write_gatt_char.assert_called_with(
            OKIMAT_WRITE_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_head_up(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_massage_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test head massage intensity up (authoritative keycode)."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_massage_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_head_up()

        expected_cmd = coordinator.controller._build_command(0x800)
        mock_bleak_client.write_gatt_char.assert_called_with(
            OKIMAT_WRITE_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_foot_down(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_massage_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Test foot massage intensity down (authoritative keycode)."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_massage_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_foot_down()

        expected_cmd = coordinator.controller._build_command(0x1000000)
        mock_bleak_client.write_gatt_char.assert_called_with(
            OKIMAT_WRITE_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_mode_step(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_massage_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Massage mode-step sends the wave keycode when present."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_massage_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.massage_mode_step()

        expected_cmd = coordinator.controller._build_command(0x4000000)
        mock_bleak_client.write_gatt_char.assert_called_with(
            OKIMAT_WRITE_CHAR_UUID, expected_cmd, response=True
        )

    async def test_massage_mode_step_cycles_programs_without_wave(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Handsets without a wave key (89837) cycle mode1 -> mode2 -> mode3."""
        coordinator = _variant_coordinator(hass, "89837")
        await coordinator.async_connect()

        controller = coordinator.controller
        assert "wave" not in controller._massage

        for expected in (0x20000000, 0x40000000, 0x80000000, 0x20000000):
            await controller.massage_mode_step()
            last = mock_bleak_client.write_gatt_char.call_args_list[-1]
            assert last[0][1] == controller._build_command(expected)


class TestOkinUuidExtras:
    """Sync / child-lock / zero-gravity capabilities driven by the remote table."""

    def _controller(self, hass, variant, motor_count=2):
        return _variant_coordinator(hass, variant, motor_count)

    async def test_sync_capability_and_command(
        self, hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock
    ):
        """A sync-capable remote (93332) advertises and sends the sync keycode."""
        coordinator = self._controller(hass, "93332")
        await coordinator.async_connect()

        assert coordinator.controller.supports_sync is True
        await coordinator.controller.sync_positions()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        expected_cmd = coordinator.controller._build_command(0x100)
        assert calls[0][0] == (OKIMAT_WRITE_CHAR_UUID, expected_cmd)
        # The held sync key is released with STOP, like the handset does.
        assert calls[-1][0] == (
            OKIMAT_WRITE_CHAR_UUID,
            coordinator.controller._build_command(0),
        )

    async def test_child_lock_capability_and_command(
        self, hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock
    ):
        """A child-lock-capable remote (90658) advertises and sends the keycode."""
        coordinator = self._controller(hass, "90658")
        await coordinator.async_connect()

        assert coordinator.controller.supports_child_lock is True
        await coordinator.controller.child_lock_toggle()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        expected_cmd = coordinator.controller._build_command(0x08000000)
        assert calls[0][0] == (OKIMAT_WRITE_CHAR_UUID, expected_cmd)
        # The held child-lock key is released with STOP, like the handset does.
        assert calls[-1][0] == (
            OKIMAT_WRITE_CHAR_UUID,
            coordinator.controller._build_command(0),
        )

    async def test_zero_gravity_preset(
        self, hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock
    ):
        """The single zero-gravity remote (94500) exposes the preset."""
        coordinator = self._controller(hass, "94500")
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_zero_g is True
        await coordinator.controller.preset_zero_g()

        expected_cmd = coordinator.controller._build_command(0x4000)
        assert any(
            call[0][1] == expected_cmd
            for call in mock_bleak_client.write_gatt_char.call_args_list
        )

    async def test_remote_without_flat_button(
        self, hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock
    ):
        """A basic RF-ECO remote (89424) with no flat button hides the preset."""
        coordinator = self._controller(hass, "89424")
        await coordinator.async_connect()

        assert coordinator.controller.supports_preset_flat is False
        await coordinator.controller.preset_flat()
        mock_bleak_client.write_gatt_char.assert_not_called()

    async def test_shifted_bit_remote_keeps_backend_keycodes(
        self, hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock
    ):
        """RF-FREE-ELEC (85281) uses its own bit assignment, not the default."""
        coordinator = self._controller(hass, "85281")
        await coordinator.async_connect()

        # This remote's back motor is 0x04 (not the usual 0x01).
        await coordinator.controller.move_back_up()
        expected = coordinator.controller._build_command(0x04)
        assert mock_bleak_client.write_gatt_char.call_args_list[0][0][1] == expected

    async def test_basic_remote_has_no_extras(
        self, hass: HomeAssistant, mock_coordinator_connected, mock_bleak_client: MagicMock
    ):
        """The default basic remote (82417) exposes no sync/child-lock/zero-g."""
        coordinator = self._controller(hass, "82417")
        await coordinator.async_connect()

        assert coordinator.controller.supports_sync is False
        assert coordinator.controller.supports_child_lock is False
        assert coordinator.controller.supports_preset_zero_g is False
        # Calling them is a safe no-op.
        await coordinator.controller.sync_positions()
        await coordinator.controller.child_lock_toggle()
        mock_bleak_client.write_gatt_char.assert_not_called()


class TestOkinUuidPositionNotifications:
    """Test Okin UUID position notification handling."""

    @pytest.mark.usefixtures("mock_coordinator_connected", "mock_bleak_client")
    async def test_start_notify_supported(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_config_entry,
        caplog,
    ):
        """Test that Okin UUID supports position notifications via Okin protocol."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_config_entry)
        await coordinator.async_connect()

        callback = MagicMock()
        await coordinator.controller.start_notify(callback)

        # Okin UUID uses OkinPositionMixin which supports position notifications
        assert "Position notifications active for Okin UUID bed" in caplog.text

    async def test_read_positions_noop(
        self,
        hass: HomeAssistant,
        mock_okin_uuid_config_entry,
        mock_coordinator_connected,
    ):
        """Test read_positions does nothing (not supported)."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_uuid_config_entry)
        await coordinator.async_connect()

        # Should complete without error
        await coordinator.controller.read_positions()


class TestOkinUuidMotorLayout:
    """Motor exposure and routing derived from each remote's handset layout."""

    def _controller(self, hass, variant, motor_count=2):
        return _variant_coordinator(hass, variant, motor_count)

    @pytest.mark.parametrize(
        ("variant", "motor_count", "expected_keys"),
        [
            # Standard 2-motor remote.
            ("82417", 2, ["back", "legs"]),
            # 4-motor remote exposes all axes when configured for 4 motors...
            ("93332", 4, ["back", "legs", "head", "feet"]),
            # ...and is still capped by the configured motor count.
            ("93332", 2, ["back", "legs"]),
            # Head/Back handset (no legs motor): no Legs cover with default
            # keycodes leaking in.
            ("90658", 2, ["back", "head"]),
            # Head-only handset exposes exactly its single axis.
            ("84582", 2, ["head"]),
        ],
    )
    async def test_motor_specs_match_handset_layout(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        variant,
        motor_count,
        expected_keys,
    ):
        """Motor covers are derived from the remote's keycodes, capped by motor count."""
        coordinator = self._controller(hass, variant, motor_count)
        await coordinator.async_connect()

        assert [spec.key for spec in coordinator.controller.motor_control_specs] == expected_keys

    async def test_head_control_drives_head_keycodes(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """On remotes with a head/tilt motor, the head control sends the M1 keycodes."""
        coordinator = self._controller(hass, "93329", motor_count=3)
        await coordinator.async_connect()

        await coordinator.controller.move_head_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert calls[0][0][1] == coordinator.controller._build_command(0x10)
        assert calls[-1][0][1] == coordinator.controller._build_command(0)

    async def test_head_control_falls_back_to_back_on_two_motor(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """On 2-motor remotes without a head motor, head stays a back synonym."""
        coordinator = self._controller(hass, "82417")
        await coordinator.async_connect()

        await coordinator.controller.move_head_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert calls[0][0][1] == coordinator.controller._build_command(0x1)

    async def test_absent_legs_axis_sends_nothing(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """A Head/Back handset never sends the (unadvertised) legs keycodes."""
        coordinator = self._controller(hass, "90658")
        await coordinator.async_connect()
        writes_before = len(mock_bleak_client.write_gatt_char.call_args_list)

        await coordinator.controller.move_legs_up()
        await coordinator.controller.move_legs_down()

        assert len(mock_bleak_client.write_gatt_char.call_args_list) == writes_before

    async def test_lights_gated_on_handset_ubl_key(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Remotes without a UBL key advertise no light and send nothing."""
        coordinator = self._controller(hass, "89448")
        await coordinator.async_connect()
        writes_before = len(mock_bleak_client.write_gatt_char.call_args_list)

        assert coordinator.controller.supports_lights is False
        await coordinator.controller.lights_toggle()

        assert len(mock_bleak_client.write_gatt_char.call_args_list) == writes_before

    async def test_lights_advertised_with_ubl_key(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
    ):
        """Remotes with a UBL key keep the light toggle."""
        coordinator = self._controller(hass, "82417")
        await coordinator.async_connect()

        assert coordinator.controller.supports_lights is True

    async def test_stale_keys_cover_absent_axes(
        self,
        hass: HomeAssistant,
        mock_coordinator_connected,
    ):
        """All motor keys are stale candidates; active axes are skipped by cleanup."""
        coordinator = self._controller(hass, "90658")
        await coordinator.async_connect()

        stale = coordinator.controller.stale_motor_entity_keys
        assert {"stair", "back", "legs", "head", "feet"} <= stale
