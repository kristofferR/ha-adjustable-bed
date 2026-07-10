"""Tests for SUTA Smart Home controller."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.suta import SutaCommands
from custom_components.adjustable_bed.const import (
    BED_TYPE_SUTA,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    SUTA_DEFAULT_WRITE_CHAR_UUID,
    SUTA_NOTIFY_CHAR_UUID,
    SUTA_SERVICE_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


def _to_packet(command: str) -> bytes:
    return f"{command}\r\n".encode()


def _configure_wlt8016_gatt(client: MagicMock, events: list[str]) -> AsyncMock:
    """Configure the FFF0/FFF1/FFF2 GATT shape reported by WLT8016_S106."""
    notify_char = MagicMock()
    notify_char.uuid = SUTA_NOTIFY_CHAR_UUID
    notify_char.properties = ["notify"]

    write_char = MagicMock()
    write_char.uuid = SUTA_DEFAULT_WRITE_CHAR_UUID
    write_char.properties = ["write-without-response"]

    service = MagicMock()
    service.uuid = SUTA_SERVICE_UUID
    service.characteristics = [notify_char, write_char]
    client.services.get_service.side_effect = lambda uuid: (
        service if str(uuid).lower() == SUTA_SERVICE_UUID else None
    )
    client.services.__iter__ = lambda _: iter([service])
    client.services.__len__ = lambda _: 1

    async def _start_notify(char_uuid: str, callback: object) -> None:
        del callback
        assert char_uuid == SUTA_NOTIFY_CHAR_UUID
        events.append("notify")

    async def _acquire_mtu() -> None:
        events.append("mtu")

    client.start_notify = AsyncMock(side_effect=_start_notify)
    backend = MagicMock()
    acquire_mtu = AsyncMock(side_effect=_acquire_mtu)
    backend._acquire_mtu = acquire_mtu
    client._backend = backend
    client.mtu_size = 250
    return acquire_mtu


@pytest.fixture
def suta_coordinator(hass: HomeAssistant, mock_coordinator_connected):
    """Create and connect a coordinator for a SUTA test device."""

    async def _create(
        *,
        address: str,
        name: str,
        entry_id: str,
        motor_count: int = 2,
    ) -> AdjustableBedCoordinator:
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="SUTA Test Bed",
            data={
                CONF_ADDRESS: address,
                CONF_NAME: name,
                CONF_BED_TYPE: BED_TYPE_SUTA,
                CONF_MOTOR_COUNT: motor_count,
                CONF_HAS_MASSAGE: False,
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_PREFERRED_ADAPTER: "auto",
            },
            unique_id=address,
            entry_id=entry_id,
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()
        return coordinator

    return _create


class TestSutaController:
    """Test SUTA controller behavior."""

    async def test_control_characteristic_uuid(self, suta_coordinator) -> None:
        """Controller should expose fallback write UUID before dynamic discovery."""
        coordinator = await suta_coordinator(
            address="AA:BB:CC:DD:EE:01",
            name="SUTA-B803",
            entry_id="suta_test_entry",
        )

        assert coordinator.controller.control_characteristic_uuid == SUTA_DEFAULT_WRITE_CHAR_UUID

    async def test_wlt8016_initializes_notify_and_mtu_before_no_response_write(
        self,
        suta_coordinator,
        mock_bleak_client: MagicMock,
    ) -> None:
        """WLT8016 must subscribe FFF1 and acquire MTU before writing FFF2."""
        events: list[str] = []
        acquire_mtu = _configure_wlt8016_gatt(mock_bleak_client, events)

        coordinator = await suta_coordinator(
            address="AA:BB:CC:DD:EE:B2",
            name="SUTA-B202B",
            entry_id="suta_wlt8016_entry",
        )

        assert coordinator.controller.requires_notification_channel is True
        assert events == ["notify", "mtu"]
        mock_bleak_client.start_notify.assert_awaited_once()
        acquire_mtu.assert_awaited_once()

        # Diagnostics may ask to start notifications again on an already-connected
        # controller; the subscription must remain idempotent.
        await coordinator.async_start_notify_for_diagnostics()
        mock_bleak_client.start_notify.assert_awaited_once()

        await coordinator.controller.move_back_down()

        first_write = mock_bleak_client.write_gatt_char.call_args_list[0]
        assert first_write.args[0] == SUTA_DEFAULT_WRITE_CHAR_UUID
        assert first_write.args[1] == _to_packet(SutaCommands.BACK_DOWN)
        assert first_write.kwargs["response"] is False

    async def test_move_back_up_sends_back_and_stop(
        self,
        suta_coordinator,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Back-up movement should send BACK UP and then STOP."""
        coordinator = await suta_coordinator(
            address="AA:BB:CC:DD:EE:02",
            name="SUTA-B207",
            entry_id="suta_test_entry_2",
        )

        await coordinator.controller.move_back_up()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert calls
        first_payload = calls[0][0][1]
        last_payload = calls[-1][0][1]
        assert first_payload == _to_packet(SutaCommands.BACK_UP)
        assert last_payload == _to_packet(SutaCommands.STOP_ALL)

    async def test_lights_on_and_off(
        self,
        suta_coordinator,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Light commands should send discrete ENABLE/DISABLE commands."""
        coordinator = await suta_coordinator(
            address="AA:BB:CC:DD:EE:03",
            name="SUTA-B410",
            entry_id="suta_test_entry_3",
        )

        await coordinator.controller.lights_on()
        await coordinator.controller.lights_off()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert calls[0][0][1] == _to_packet(SutaCommands.LIGHT_ON)
        assert calls[1][0][1] == _to_packet(SutaCommands.LIGHT_OFF)

    async def test_lights_toggle_tracks_local_state(
        self,
        suta_coordinator,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Toggle should alternate between ON and OFF using local state tracking."""
        coordinator = await suta_coordinator(
            address="AA:BB:CC:DD:EE:05",
            name="SUTA-B803",
            entry_id="suta_test_entry_5",
        )

        await coordinator.controller.lights_toggle()
        await coordinator.controller.lights_toggle()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert calls[0][0][1] == _to_packet(SutaCommands.LIGHT_ON)
        assert calls[1][0][1] == _to_packet(SutaCommands.LIGHT_OFF)

    async def test_preset_memory_2_sends_m2_command(
        self,
        suta_coordinator,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Memory preset 2 should send one M2 recall command without STOP."""
        coordinator = await suta_coordinator(
            address="AA:BB:CC:DD:EE:04",
            name="SUTA-B505",
            entry_id="suta_test_entry_4",
        )

        await coordinator.controller.preset_memory(2)

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) == 1
        assert calls[0][0][1] == _to_packet(SutaCommands.PRESET_MEMORY_2)

    async def test_preset_tv_sends_single_command_without_stop(
        self,
        suta_coordinator,
        mock_bleak_client: MagicMock,
    ) -> None:
        """TV preset should send one preset command and let firmware run continuously."""
        coordinator = await suta_coordinator(
            address="AA:BB:CC:DD:EE:06",
            name="SUTA-B201B",
            entry_id="suta_test_entry_6",
        )

        await coordinator.controller.preset_tv()

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) == 1
        assert calls[0][0][1] == _to_packet(SutaCommands.PRESET_TV)


class TestSutaSync:
    """Test SUTA split-king sync commands."""

    async def test_supports_synchro(
        self,
        suta_coordinator,
    ) -> None:
        """Test that SUTA controller reports sync support."""
        coordinator = await suta_coordinator(
            address="AA:BB:CC:DD:EE:07",
            name="SUTA-B201C",
            entry_id="suta_test_entry_7",
        )

        assert coordinator.controller.supports_synchro is True

    async def test_set_synchro_on(
        self,
        suta_coordinator,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Test sync on sends AT+SINSLAVE=ON command."""
        coordinator = await suta_coordinator(
            address="AA:BB:CC:DD:EE:08",
            name="SUTA-B201D",
            entry_id="suta_test_entry_8",
        )

        await coordinator.controller.set_synchro(True)

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) == 1
        assert calls[0][0][1] == _to_packet(SutaCommands.SYNC_SLAVE_ON)

    async def test_set_synchro_off(
        self,
        suta_coordinator,
        mock_bleak_client: MagicMock,
    ) -> None:
        """Test sync off sends AT+SINSLAVE=OFF command."""
        coordinator = await suta_coordinator(
            address="AA:BB:CC:DD:EE:09",
            name="SUTA-B201E",
            entry_id="suta_test_entry_9",
        )

        await coordinator.controller.set_synchro(False)

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert len(calls) == 1
        assert calls[0][0][1] == _to_packet(SutaCommands.SYNC_SLAVE_OFF)
