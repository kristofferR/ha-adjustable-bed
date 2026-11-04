"""Tests for Okin CSTProtocol bed controller."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.okin_cst import (
    CstMotorCommands,
    CstRemoteCommands,
    OkinCstController,
)
from custom_components.adjustable_bed.codec.okin_nframe import frame96
from custom_components.adjustable_bed.const import (
    BED_TYPE_OKIN_CST,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    OKIMAT_NOTIFY_CHAR_UUID,
    OKIMAT_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles.okin_nframe import CST_PRESS


@pytest.fixture
def mock_okin_cst_config_entry_data() -> dict:
    """Return mock config entry data for an Okin CST bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Okin CST Test Bed",
        CONF_BED_TYPE: BED_TYPE_OKIN_CST,
        CONF_MOTOR_COUNT: 3,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_okin_cst_config_entry(
    hass: HomeAssistant, mock_okin_cst_config_entry_data: dict
) -> MockConfigEntry:
    """Return a mock config entry for an Okin CST bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Okin CST Test Bed",
        data=mock_okin_cst_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="okin_cst_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def okin_cst_controller(
    hass: HomeAssistant,
    mock_okin_cst_config_entry: MockConfigEntry,
    request: pytest.FixtureRequest,
) -> OkinCstController:
    """Return a connected Okin CST controller."""
    request.getfixturevalue("mock_coordinator_connected")
    coordinator = AdjustableBedCoordinator(hass, mock_okin_cst_config_entry)
    await coordinator.async_connect()
    controller = coordinator.controller
    assert isinstance(controller, OkinCstController)
    return controller


def _payloads(mock_client: MagicMock) -> list[bytes]:
    """Return written BLE payloads."""
    return [call.args[1] for call in mock_client.write_gatt_char.call_args_list]


def _assert_writes_use_cst_characteristic(mock_client: MagicMock) -> None:
    """Assert every write targets the CST write characteristic."""
    for recorded_call in mock_client.write_gatt_char.call_args_list:
        assert recorded_call.args[0] == OKIMAT_WRITE_CHAR_UUID
        assert recorded_call.kwargs["response"] is True


def _assert_button_press_sequence(payloads: list[bytes], command: bytes) -> None:
    """Assert a short app-style press followed by the STOP sequence."""
    assert payloads == (
        [command] * CST_PRESS.repeats + [frame96(0)] * 2
    )


def _assert_preset_sequence(payloads: list[bytes], command: bytes) -> None:
    """Assert a long preset hold followed by the STOP sequence."""
    assert payloads == [command] * CST_PRESS.repeats + [frame96(0)] * 2


class TestOkinCstCapabilities:
    """Test Okin CST capability declarations."""

    async def test_capabilities_match_mfirm_app(
        self, okin_cst_controller: OkinCstController
    ) -> None:
        """The CST profile should expose only commands present in the MFirm app."""
        assert okin_cst_controller.supports_preset_zero_g is True
        assert okin_cst_controller.supports_preset_anti_snore is True
        assert okin_cst_controller.supports_preset_lounge is True
        assert okin_cst_controller.supports_preset_incline is True
        assert okin_cst_controller.supports_memory_presets is True
        assert okin_cst_controller.memory_slot_count == 3
        assert okin_cst_controller.supports_memory_programming is True
        assert okin_cst_controller.supports_discrete_light_control is True
        assert okin_cst_controller.supports_massage is True
        assert okin_cst_controller.supports_massage_off_control is True
        assert okin_cst_controller.supports_massage_toggle_control is False
        assert okin_cst_controller.supports_massage_intensity_step_control is True
        assert okin_cst_controller.supports_head_massage_intensity_step_control is False
        assert okin_cst_controller.supports_foot_massage_intensity_step_control is False
        assert okin_cst_controller.supports_position_feedback is False
        assert [spec.key for spec in okin_cst_controller.motor_control_specs] == [
            "head",
            "feet",
            "lumbar",
        ]
        assert okin_cst_controller.stale_motor_entity_keys == frozenset({"back", "legs", "tilt"})

    def test_command_values_match_reachable_cst_protocol(self) -> None:
        """Only command values reachable from the shipped app are declared."""
        assert CstMotorCommands.HEAD_UP == 0x00000001
        assert CstMotorCommands.HEAD_DOWN == 0x00000002
        assert CstMotorCommands.FOOT_UP == 0x00000004
        assert CstMotorCommands.FOOT_DOWN == 0x00000008
        assert CstMotorCommands.LUMBAR_UP == 0x00000010
        assert CstMotorCommands.LUMBAR_DOWN == 0x00000020
        assert CstRemoteCommands.MASSAGE_OFF == 0x02000000
        assert CstRemoteCommands.MASSAGE_INTENSITY == 0x00000C00
        assert CstRemoteCommands.MASSAGE_INTENSITY_MINUS == 0x01800000


class TestOkinCstCommands:
    """Test Okin CST command routing and timing."""

    @patch(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep",
        new_callable=AsyncMock,
    )
    async def test_flat_preset_uses_primary_field_and_app_one_shot_cadence(
        self,
        _mock_sleep: AsyncMock,
        okin_cst_controller: OkinCstController,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Flat uses the primary field and the app's fixed 500 ms voice cadence."""
        mock_bleak_client.write_gatt_char.reset_mock()

        await okin_cst_controller.preset_flat()

        expected = frame96(CstRemoteCommands.FLAT)
        payloads = _payloads(mock_bleak_client)
        _assert_preset_sequence(payloads, expected)
        _assert_writes_use_cst_characteristic(mock_bleak_client)

    @pytest.mark.parametrize(
        ("method_name", "command_value"),
        [
            ("preset_zero_g", CstRemoteCommands.ZERO_G),
            ("preset_anti_snore", CstRemoteCommands.ANTI_SNORE),
            ("preset_lounge", CstRemoteCommands.LOUNGE),
            ("preset_incline", CstRemoteCommands.INCLINE),
        ],
    )
    @patch(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep",
        new_callable=AsyncMock,
    )
    async def test_preset_actions_use_primary_field(
        self,
        _mock_sleep: AsyncMock,
        okin_cst_controller: OkinCstController,
        mock_bleak_client: MagicMock,
        method_name: str,
        command_value: int,
    ) -> None:
        """MFirm preset-style actions are carried in the primary CST field."""
        mock_bleak_client.write_gatt_char.reset_mock()
        method: Callable[[], Awaitable[None]]
        method = getattr(okin_cst_controller, method_name)
        await method()

        payloads = _payloads(mock_bleak_client)
        _assert_preset_sequence(
            payloads,
            frame96(command_value),
        )

    @pytest.mark.parametrize(
        ("memory_num", "command_value"),
        [
            (1, CstRemoteCommands.ZERO_G),
            (2, CstRemoteCommands.INCLINE),
            (3, CstRemoteCommands.LOUNGE),
        ],
    )
    @patch(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep",
        new_callable=AsyncMock,
    )
    async def test_memory_recalls_use_programmable_preset_slots(
        self,
        _mock_sleep: AsyncMock,
        okin_cst_controller: OkinCstController,
        mock_bleak_client: MagicMock,
        memory_num: int,
        command_value: int,
    ) -> None:
        """HA memory slots map to MFirm's saveable ZG, incline, and lounge slots."""
        mock_bleak_client.write_gatt_char.reset_mock()

        await okin_cst_controller.preset_memory(memory_num)

        payloads = _payloads(mock_bleak_client)
        _assert_preset_sequence(
            payloads,
            frame96(command_value),
        )

    @pytest.mark.parametrize(
        ("memory_num", "command_value"),
        [
            (1, CstRemoteCommands.SAVE_ZERO_G),
            (2, CstRemoteCommands.SAVE_INCLINE),
            (3, CstRemoteCommands.SAVE_LOUNGE),
        ],
    )
    @patch(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep",
        new_callable=AsyncMock,
    )
    async def test_program_memory_uses_app_save_combos(
        self,
        _mock_sleep: AsyncMock,
        okin_cst_controller: OkinCstController,
        mock_bleak_client: MagicMock,
        memory_num: int,
        command_value: int,
    ) -> None:
        """Program memory sends MFirm's Flat+preset save packets."""
        mock_bleak_client.write_gatt_char.reset_mock()

        await okin_cst_controller.program_memory(memory_num)

        _assert_button_press_sequence(
            _payloads(mock_bleak_client),
            frame96(command_value),
        )

    @patch(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep",
        new_callable=AsyncMock,
    )
    async def test_lights_on_uses_secondary_field(
        self,
        _mock_sleep: AsyncMock,
        okin_cst_controller: OkinCstController,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Discrete light-on uses the secondary CST field."""
        mock_bleak_client.write_gatt_char.reset_mock()

        await okin_cst_controller.lights_on()

        _assert_button_press_sequence(
            _payloads(mock_bleak_client),
            frame96(0, CstRemoteCommands.LIGHT_ON),
        )

    @patch(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep",
        new_callable=AsyncMock,
    )
    async def test_lights_off_uses_secondary_field(
        self,
        _mock_sleep: AsyncMock,
        okin_cst_controller: OkinCstController,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Discrete light-off uses the secondary CST field."""
        mock_bleak_client.write_gatt_char.reset_mock()

        await okin_cst_controller.lights_off()

        _assert_button_press_sequence(
            _payloads(mock_bleak_client),
            frame96(0, CstRemoteCommands.LIGHT_OFF),
        )

    @patch(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep",
        new_callable=AsyncMock,
    )
    async def test_lights_toggle_uses_primary_field(
        self,
        _mock_sleep: AsyncMock,
        okin_cst_controller: OkinCstController,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Light toggle uses the primary CST field in the MFirm app."""
        mock_bleak_client.write_gatt_char.reset_mock()

        await okin_cst_controller.lights_toggle()

        _assert_button_press_sequence(
            _payloads(mock_bleak_client),
            frame96(CstRemoteCommands.LIGHT_TOGGLE),
        )

    @pytest.mark.parametrize(
        ("method_name", "command_value"),
        [
            ("massage_off", CstRemoteCommands.MASSAGE_OFF),
            ("massage_intensity_up", CstRemoteCommands.MASSAGE_INTENSITY),
            ("massage_intensity_down", CstRemoteCommands.MASSAGE_INTENSITY_MINUS),
        ],
    )
    @patch(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep",
        new_callable=AsyncMock,
    )
    async def test_massage_actions_use_primary_field(
        self,
        _mock_sleep: AsyncMock,
        okin_cst_controller: OkinCstController,
        mock_bleak_client: MagicMock,
        method_name: str,
        command_value: int,
    ) -> None:
        """Most MFirm massage actions are carried in the primary CST field."""
        mock_bleak_client.write_gatt_char.reset_mock()
        method: Callable[[], Awaitable[None]] = getattr(okin_cst_controller, method_name)

        await method()

        _assert_button_press_sequence(
            _payloads(mock_bleak_client),
            frame96(command_value),
        )

    @patch(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep",
        new_callable=AsyncMock,
    )
    async def test_massage_mode_step_cycles_secondary_field_waves(
        self,
        _mock_sleep: AsyncMock,
        okin_cst_controller: OkinCstController,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Massage mode cycling uses the app's secondary-field wave commands."""
        mock_bleak_client.write_gatt_char.reset_mock()

        await okin_cst_controller.massage_mode_step()
        await okin_cst_controller.massage_mode_step()

        payloads = _payloads(mock_bleak_client)
        expected_press_length = CST_PRESS.repeats + 2
        assert len(payloads) == expected_press_length * 2
        first_press = payloads[:expected_press_length]
        second_press = payloads[expected_press_length:]
        _assert_button_press_sequence(
            first_press,
            frame96(0, CstRemoteCommands.MASSAGE_WAVE_1),
        )
        _assert_button_press_sequence(
            second_press,
            frame96(0, CstRemoteCommands.MASSAGE_WAVE_2),
        )

    @pytest.mark.parametrize(
        ("method_name", "command_value"),
        [
            ("move_back_up", CstMotorCommands.HEAD_UP),
            ("move_back_down", CstMotorCommands.HEAD_DOWN),
            ("move_legs_up", CstMotorCommands.FOOT_UP),
            ("move_legs_down", CstMotorCommands.FOOT_DOWN),
            ("move_lumbar_up", CstMotorCommands.LUMBAR_UP),
            ("move_lumbar_down", CstMotorCommands.LUMBAR_DOWN),
        ],
    )
    @patch(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep",
        new_callable=AsyncMock,
    )
    async def test_motor_actions_use_exact_primary_field_bits(
        self,
        _mock_sleep: AsyncMock,
        okin_cst_controller: OkinCstController,
        mock_bleak_client: MagicMock,
        method_name: str,
        command_value: int,
    ) -> None:
        """Head, foot, and lumbar use the app's reachable motor bits."""
        mock_bleak_client.write_gatt_char.reset_mock()
        method: Callable[[], Awaitable[None]] = getattr(okin_cst_controller, method_name)

        await method()

        expected = frame96(command_value)
        assert _payloads(mock_bleak_client) == [
            expected,
        ] * okin_cst_controller._coordinator.motor_pulse_count + [
            frame96(0),
            frame96(0),
        ]

    @patch(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep",
        new_callable=AsyncMock,
    )
    async def test_stop_sequence_waits_before_both_release_frames(
        self,
        mock_sleep: AsyncMock,
        okin_cst_controller: OkinCstController,
        mock_bleak_client: MagicMock,
    ) -> None:
        """The app sends zero releases at +100 ms and +200 ms."""
        mock_bleak_client.write_gatt_char.reset_mock()

        await okin_cst_controller.stop_all()

        assert _payloads(mock_bleak_client) == [frame96(0)] * 2
        assert mock_sleep.await_args_list == [call(0.1), call(0.1)]

    async def test_notifications_are_forwarded_raw_without_position_updates(
        self,
        okin_cst_controller: OkinCstController,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Diagnostics should receive CST notifications without invented positions."""
        raw_callback = MagicMock()
        position_callback = MagicMock()
        okin_cst_controller.set_raw_notify_callback(raw_callback)
        mock_bleak_client.start_notify.reset_mock()

        await okin_cst_controller.start_notify(position_callback)

        mock_bleak_client.start_notify.assert_awaited_once()
        notify_uuid, handler = mock_bleak_client.start_notify.await_args.args
        assert notify_uuid == OKIMAT_NOTIFY_CHAR_UUID

        payload = bytearray.fromhex("0c02000000000000000001000000")
        handler(MagicMock(), payload)

        raw_callback.assert_called_once_with(OKIMAT_NOTIFY_CHAR_UUID, bytes(payload))
        position_callback.assert_not_called()

        await okin_cst_controller.stop_notify()
        mock_bleak_client.stop_notify.assert_awaited_once_with(OKIMAT_NOTIFY_CHAR_UUID)
