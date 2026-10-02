"""SIMMONS through the real coordinator: link-time session, raw names and pairs."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.config_flow import (
    AdjustableBedOptionsFlow,
    _name_rule_setup_name,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_SIMMONS,
    CONF_BED_TYPE,
    CONF_BLE_DEVICE_NAME,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_IDLE_DISCONNECT_SECONDS,
    CONF_MOTOR_COUNT,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    SIMMONS_VARIANT_INCLINED,
    SIMMONS_VARIANT_SMARTBED,
    VARIANT_AUTO,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.pairing import build_pair_entry_data, effective_child_data

NUS = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
CLOCK_PREFIX = bytes.fromhex("E7 80 01")


def _entry(hass: HomeAssistant, **data: object) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "Bedroom",
            CONF_BED_TYPE: BED_TYPE_SIMMONS,
            CONF_PROTOCOL_VARIANT: VARIANT_AUTO,
            CONF_MOTOR_COUNT: 2,
            CONF_DISABLE_ANGLE_SENSING: True,
            **data,
        },
        unique_id="AA:BB:CC:DD:EE:FF",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def simmons_client(mock_bleak_client: MagicMock) -> MagicMock:
    service = MagicMock(uuid=NUS, handle=0, description="Nordic UART")
    service.characteristics = [
        MagicMock(uuid=uuid, handle=handle, properties=[prop], descriptors=[])
        for uuid, handle, prop in (
            ("6e400002-b5a3-f393-e0a9-e50e24dcca9e", 1, "write"),
            ("6e400003-b5a3-f393-e0a9-e50e24dcca9e", 2, "notify"),
        )
    ]
    mock_bleak_client.services.__iter__ = lambda self: iter([service])
    mock_bleak_client.services.__len__ = lambda self: 1
    return mock_bleak_client


def _frames(client: MagicMock) -> list[bytes]:
    return [bytes(call.args[1]) for call in client.write_gatt_char.call_args_list]


@pytest.mark.usefixtures("mock_coordinator_connected")
async def test_quick_handoff_session_syncs_clock_before_the_first_alarm_write(
    hass: HomeAssistant,
    simmons_client: MagicMock,
    mock_async_ble_device_from_address: MagicMock,
) -> None:
    mock_async_ble_device_from_address.return_value.name = "OKIN-112233"
    entry = _entry(hass, **{CONF_DISCONNECT_AFTER_COMMAND: True})
    coordinator = AdjustableBedCoordinator(hass, entry)
    original_write = simmons_client.write_gatt_char.side_effect

    async def write_and_reply(char: object, data: bytes, response: bool = False) -> None:
        await original_write(char, data, response)
        if bytes(data) == bytes.fromhex("E1 80 03 9B"):
            # The bed answers the link-time query, so this connection has fresh records.
            coordinator.controller._handle_notification(
                None, bytearray.fromhex("ED 80 03 06 00 00 00 08 2D 84 1C")
            )

    simmons_client.write_gatt_char.side_effect = write_and_reply
    with (
        patch("custom_components.adjustable_bed.beds.simmons.PAGE_QUERY_OFFSETS_S", (0, 0, 0)),
        patch("custom_components.adjustable_bed.beds.simmons.QUERY_GAP_S", 0),
    ):
        assert await coordinator.async_connect()
        session = _frames(simmons_client)
        # Link-time traffic runs during setup, before any command can start.
        assert session[0].startswith(CLOCK_PREFIX)
        assert session[1:] == [bytes.fromhex("E1 80 03 9B")] * 3

        async def program(controller) -> None:
            await controller.configure_simmons_alarm(slot=1, enabled=False)

        await coordinator.async_execute_controller_command(program, cancel_running=False)
    frames = _frames(simmons_client)[len(session) :]
    assert frames[0].startswith(bytes.fromhex("ED 80 03"))  # No second clock write needed.
    assert not any(frame.startswith(CLOCK_PREFIX) for frame in frames)
    await coordinator.async_disconnect()


@pytest.mark.usefixtures("mock_coordinator_connected")
async def test_renamed_entry_with_address_alias_uses_the_stored_raw_name(
    hass: HomeAssistant,
    simmons_client: MagicMock,
    mock_async_ble_device_from_address: MagicMock,
) -> None:
    mock_async_ble_device_from_address.return_value.name = "AA-BB-CC-DD-EE-FF"
    entry = _entry(hass, **{CONF_BLE_DEVICE_NAME: "OKIN-112233", CONF_NAME: "SmartBed room"})
    coordinator = AdjustableBedCoordinator(hass, entry)
    with patch("asyncio.sleep", new=AsyncMock()):
        assert await coordinator.async_connect()
    assert coordinator.controller.protocol == "okin"
    # An address alias never replaces the stored raw name.
    assert entry.data[CONF_BLE_DEVICE_NAME] == "OKIN-112233"
    await coordinator.async_disconnect()


@pytest.mark.usefixtures("mock_coordinator_connected")
async def test_observed_real_name_is_persisted_for_the_name_rule(
    hass: HomeAssistant,
    simmons_client: MagicMock,
    mock_async_ble_device_from_address: MagicMock,
) -> None:
    mock_async_ble_device_from_address.return_value.name = "SmartBed-55"
    entry = _entry(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    with patch("asyncio.sleep", new=AsyncMock()):
        assert await coordinator.async_connect()
    assert entry.data[CONF_BLE_DEVICE_NAME] == "SmartBed-55"
    assert coordinator.controller.protocol == "smartbed"
    await coordinator.async_disconnect()


def test_setup_stores_only_a_real_raw_name():
    assert _name_rule_setup_name(BED_TYPE_SIMMONS, "OKIN-1") == {CONF_BLE_DEVICE_NAME: "OKIN-1"}
    assert _name_rule_setup_name(BED_TYPE_SIMMONS, "AA:BB:CC:DD:EE:FF") == {}
    assert _name_rule_setup_name(BED_TYPE_SIMMONS, None) == {}
    assert _name_rule_setup_name("okin_ffe", "OKIN-1") == {}


def _side(address: str, variant: str) -> dict[str, object]:
    return {
        CONF_ADDRESS: address,
        CONF_NAME: address,
        CONF_BED_TYPE: BED_TYPE_SIMMONS,
        CONF_PROTOCOL_VARIANT: variant,
        CONF_MOTOR_COUNT: 2,
        CONF_DISABLE_ANGLE_SENSING: True,
    }


@pytest.mark.parametrize(
    ("left", "right"),
    [(VARIANT_AUTO, VARIANT_AUTO), (SIMMONS_VARIANT_INCLINED, SIMMONS_VARIANT_SMARTBED)],
)
async def test_two_address_pair_refuses_shared_variant_changes(
    hass: HomeAssistant, left: str, right: str
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=build_pair_entry_data(
            _side("AA:BB:CC:DD:EE:11", left), _side("AA:BB:CC:DD:EE:22", right), name="Pair"
        ),
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    requested = SIMMONS_VARIANT_INCLINED if left != SIMMONS_VARIANT_INCLINED else VARIANT_AUTO

    refused = await flow.async_step_settings({CONF_PROTOCOL_VARIANT: requested})

    assert refused["type"] is FlowResultType.FORM
    assert refused["errors"] == {CONF_PROTOCOL_VARIANT: "simmons_unpair_first"}
    # A shared, non-variant change still saves and leaves each side's variant.
    saved = await flow.async_step_settings({CONF_IDLE_DISCONNECT_SECONDS: 60})
    assert saved["type"] is FlowResultType.CREATE_ENTRY
    assert effective_child_data(entry.data, "left")[CONF_PROTOCOL_VARIANT] == left
    assert effective_child_data(entry.data, "right")[CONF_PROTOCOL_VARIANT] == right
