"""Tests for Okin CB35 Star bed controller."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.okin_7byte import _cmd
from custom_components.adjustable_bed.beds.okin_cb35 import (
    OKIN_CB35_CONFIG,
    OkinCB35Controller,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_OKIN_CB35,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


@pytest.fixture
def mock_okin_cb35_config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Return a mock config entry for an Okin CB35 bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Okin CB35 Test Bed",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "Okin CB35 Test Bed",
            CONF_BED_TYPE: BED_TYPE_OKIN_CB35,
            CONF_MOTOR_COUNT: 4,
            CONF_HAS_MASSAGE: True,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="okin_cb35_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_cb35_client() -> AsyncMock:
    """Return a connected BLE client mock for CB35 tests."""
    client = AsyncMock()
    client.is_connected = True
    client.services = []
    return client


@pytest.mark.asyncio
class TestOkinCB35Controller:
    """Test Okin CB35 controller behavior."""

    async def test_write_command_passes_effective_cancel_event(
        self,
        hass: HomeAssistant,
        mock_okin_cb35_config_entry: MockConfigEntry,
        mock_cb35_client: AsyncMock,
    ) -> None:
        """write_command should propagate the coordinator cancel event explicitly."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_cb35_config_entry)
        coordinator._client = mock_cb35_client
        controller = OkinCB35Controller(coordinator)
        controller._initialized = True

        with patch.object(controller, "_write_gatt_with_retry", new=AsyncMock()) as write_mock:
            await controller.write_command(_cmd(0x00))

        write_mock.assert_awaited_once()
        assert write_mock.await_args.kwargs["cancel_event"] is coordinator.cancel_command
        assert write_mock.await_args.kwargs["response"] is OKIN_CB35_CONFIG.write_with_response

    async def test_cancelled_movement_sends_stop_with_fresh_event(
        self,
        hass: HomeAssistant,
        mock_okin_cb35_config_entry: MockConfigEntry,
        mock_cb35_client: AsyncMock,
    ) -> None:
        """A pre-cancelled CB35 movement should skip motion and still send STOP."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_cb35_config_entry)
        coordinator._client = mock_cb35_client
        controller = OkinCB35Controller(coordinator)
        coordinator.cancel_command.set()

        await controller.move_head_up()

        payloads = [call.args[1] for call in mock_cb35_client.write_gatt_char.call_args_list]
        assert _cmd(0x00) not in payloads
        assert payloads[-1] == _cmd(0x0F)

    async def test_preset_is_tap_then_triple_stop(
        self,
        hass: HomeAssistant,
        mock_okin_cb35_config_entry: MockConfigEntry,
        mock_cb35_client: AsyncMock,
    ) -> None:
        """A preset is the key x2 followed by STOP x3; the STOP burst commits the move."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_cb35_config_entry)
        coordinator._client = mock_cb35_client
        controller = OkinCB35Controller(coordinator)
        controller._initialized = True

        with patch("asyncio.sleep", new=AsyncMock()):
            await controller.preset_flat()

        payloads = [call.args[1] for call in mock_cb35_client.write_gatt_char.call_args_list]
        assert payloads == [_cmd(0x10)] * 2 + [_cmd(0x0F)] * 3

    async def test_preset_release_survives_cancel(
        self,
        hass: HomeAssistant,
        mock_okin_cb35_config_entry: MockConfigEntry,
        mock_cb35_client: AsyncMock,
    ) -> None:
        """A cancelled preset still sends its STOP x3 release."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_cb35_config_entry)
        coordinator._client = mock_cb35_client
        controller = OkinCB35Controller(coordinator)
        controller._initialized = True
        coordinator.cancel_command.set()

        with patch("asyncio.sleep", new=AsyncMock()):
            await controller.preset_memory(1)

        payloads = [call.args[1] for call in mock_cb35_client.write_gatt_char.call_args_list]
        assert _cmd(0x1A) not in payloads
        assert payloads == [_cmd(0x0F)] * 3
        assert controller._preset_started_at is None

        mock_cb35_client.write_gatt_char.reset_mock()
        with patch("asyncio.sleep", new=AsyncMock()):
            await controller.stop_all()

        payloads = [call.args[1] for call in mock_cb35_client.write_gatt_char.call_args_list]
        assert payloads == [_cmd(0x0F)] * 3

    async def test_preset_reports_release_failure_after_successful_tap(
        self,
        hass: HomeAssistant,
        mock_okin_cb35_config_entry: MockConfigEntry,
    ) -> None:
        """A failed required release must fail an otherwise successful preset tap."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_cb35_config_entry)
        controller = OkinCB35Controller(coordinator)

        with (
            patch.object(
                controller,
                "write_command",
                new=AsyncMock(side_effect=[None, ConnectionError("release failed")]),
            ),
            pytest.raises(ConnectionError, match="release failed"),
        ):
            await controller.preset_flat()

    async def test_preset_preserves_command_failure_when_release_also_fails(
        self,
        hass: HomeAssistant,
        mock_okin_cb35_config_entry: MockConfigEntry,
    ) -> None:
        """A release failure must not replace the original preset-write failure."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_cb35_config_entry)
        controller = OkinCB35Controller(coordinator)

        with (
            patch.object(
                controller,
                "write_command",
                new=AsyncMock(
                    side_effect=[BleakError("preset failed"), ConnectionError("release failed")]
                ),
            ),
            pytest.raises(BleakError, match="preset failed"),
        ):
            await controller.preset_flat()

    async def test_stop_all_interrupts_running_preset_with_motor_tap(
        self,
        hass: HomeAssistant,
        mock_okin_cb35_config_entry: MockConfigEntry,
        mock_cb35_client: AsyncMock,
    ) -> None:
        """While a preset may be driving, stop_all taps a motor key before STOP x3."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_cb35_config_entry)
        coordinator._client = mock_cb35_client
        controller = OkinCB35Controller(coordinator)
        controller._initialized = True

        with patch("asyncio.sleep", new=AsyncMock()):
            await controller.preset_flat()
            mock_cb35_client.write_gatt_char.reset_mock()
            await controller.stop_all()

        payloads = [call.args[1] for call in mock_cb35_client.write_gatt_char.call_args_list]
        assert payloads == [_cmd(0x00)] + [_cmd(0x0F)] * 3

    async def test_stop_all_retains_preset_and_releases_when_interrupt_fails(
        self,
        hass: HomeAssistant,
        mock_okin_cb35_config_entry: MockConfigEntry,
    ) -> None:
        """A failed motor interrupt retains state and still attempts STOP cleanup."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_cb35_config_entry)
        controller = OkinCB35Controller(coordinator)
        controller._preset_started_at = asyncio.get_running_loop().time()

        write_mock = AsyncMock(side_effect=[ConnectionError("interrupt failed"), None])
        with (
            patch.object(controller, "write_command", new=write_mock),
            pytest.raises(ConnectionError, match="interrupt failed"),
        ):
            await controller.stop_all()

        assert controller._preset_started_at is not None
        assert [call.args[0] for call in write_mock.await_args_list] == [
            _cmd(0x00),
            _cmd(0x0F),
        ]

    async def test_motor_command_clears_active_preset(
        self,
        hass: HomeAssistant,
        mock_okin_cb35_config_entry: MockConfigEntry,
        mock_cb35_client: AsyncMock,
    ) -> None:
        """A successful motor command supersedes the active preset window."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_cb35_config_entry)
        coordinator._client = mock_cb35_client
        controller = OkinCB35Controller(coordinator)
        controller._initialized = True
        controller._preset_started_at = asyncio.get_running_loop().time()

        with patch("asyncio.sleep", new=AsyncMock()):
            await controller.move_feet_up()

        assert controller._preset_started_at is None

    @pytest.mark.parametrize("operation", ["preset", "motor"])
    async def test_cancel_during_wake_preserves_previous_preset_state(
        self,
        hass: HomeAssistant,
        mock_okin_cb35_config_entry: MockConfigEntry,
        mock_cb35_client: AsyncMock,
        operation: str,
    ) -> None:
        """A cancelled wake sends no movement packet and cannot change preset state."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_cb35_config_entry)
        coordinator._client = mock_cb35_client
        controller = OkinCB35Controller(coordinator)
        previous = asyncio.get_running_loop().time() if operation == "motor" else None
        controller._preset_started_at = previous

        async def cancel_on_wake(uuid: str, command: bytes, **kwargs: object) -> None:
            if command == OKIN_CB35_CONFIG.init_commands[0]:
                coordinator.cancel_command.set()

        mock_cb35_client.write_gatt_char.side_effect = cancel_on_wake
        with patch("asyncio.sleep", new=AsyncMock()):
            if operation == "preset":
                await controller.preset_flat()
            else:
                await controller.move_feet_up()

        payloads = [call.args[1] for call in mock_cb35_client.write_gatt_char.await_args_list]
        assert payloads == list(OKIN_CB35_CONFIG.init_commands) + [_cmd(0x0F)] * 3
        assert controller._preset_started_at == previous

        mock_cb35_client.write_gatt_char.reset_mock()
        with patch("asyncio.sleep", new=AsyncMock()):
            await controller.stop_all()
        payloads = [call.args[1] for call in mock_cb35_client.write_gatt_char.await_args_list]
        assert payloads == ([_cmd(0x00)] if operation == "motor" else []) + [_cmd(0x0F)] * 3

    @pytest.mark.parametrize("operation", ["preset", "motor"])
    @pytest.mark.parametrize("interruption", ["cancel_event", "task_cancel", "write_failure"])
    async def test_successful_first_write_updates_state_before_interruption(
        self,
        hass: HomeAssistant,
        mock_okin_cb35_config_entry: MockConfigEntry,
        mock_cb35_client: AsyncMock,
        operation: str,
        interruption: str,
    ) -> None:
        """A successful packet counts even when its later repeats do not finish."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_cb35_config_entry)
        coordinator._client = mock_cb35_client
        controller = OkinCB35Controller(coordinator)
        controller._initialized = True
        controller._preset_started_at = None if operation == "preset" else 1.0
        movement = _cmd(0x10 if operation == "preset" else 0x02)
        movement_writes = 0

        async def interrupt_repeat(uuid: str, command: bytes, **kwargs: object) -> None:
            nonlocal movement_writes
            if command != movement:
                return
            movement_writes += 1
            if interruption == "cancel_event":
                coordinator.cancel_command.set()
            elif movement_writes == 2:
                raise BleakError("repeat failed")

        async def interrupt_delay(delay: float) -> None:
            if interruption == "task_cancel" and movement_writes == 1:
                # Only the first movement delay is cancelled; cleanup may sleep.
                if mock_cb35_client.write_gatt_char.await_args.args[1] == movement:
                    raise asyncio.CancelledError

        mock_cb35_client.write_gatt_char.side_effect = interrupt_repeat
        with patch("asyncio.sleep", new=AsyncMock(side_effect=interrupt_delay)):
            command = controller.preset_flat if operation == "preset" else controller.move_feet_up
            if interruption == "task_cancel":
                with pytest.raises(asyncio.CancelledError):
                    await command()
            elif interruption == "write_failure":
                with pytest.raises(BleakError, match="repeat failed"):
                    await command()
            else:
                await command()

        assert (controller._preset_started_at is not None) == (operation == "preset")
        payloads = [call.args[1] for call in mock_cb35_client.write_gatt_char.await_args_list]
        assert payloads[-3:] == [_cmd(0x0F)] * 3

    async def test_stop_all_is_silent_when_idle(
        self,
        hass: HomeAssistant,
        mock_okin_cb35_config_entry: MockConfigEntry,
        mock_cb35_client: AsyncMock,
    ) -> None:
        """With no recent preset, stop_all sends STOP x3 only, so an idle stop does not nudge the bed."""
        coordinator = AdjustableBedCoordinator(hass, mock_okin_cb35_config_entry)
        coordinator._client = mock_cb35_client
        controller = OkinCB35Controller(coordinator)
        controller._initialized = True

        with patch("asyncio.sleep", new=AsyncMock()):
            await controller.stop_all()

        payloads = [call.args[1] for call in mock_cb35_client.write_gatt_char.call_args_list]
        assert payloads == [_cmd(0x0F)] * 3
