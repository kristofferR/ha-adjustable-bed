"""Tests for DewertOkin Bluetooth RF-Gateway controller selection."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.dewertokin_rf_gateway import (
    DewertOkinRfGatewayController,
)
from custom_components.adjustable_bed.beds.okin_handle import OkinHandleController
from custom_components.adjustable_bed.const import (
    BED_TYPE_DEWERTOKIN,
    BED_TYPE_OKIN_HANDLE,
    BED_TYPE_OKIN_UUID,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DEWERTOKIN_RF_GATEWAY_MODEL,
    DEWERTOKIN_RF_GATEWAY_SERVICE_UUID,
    DEWERTOKIN_RF_GATEWAY_WRITE_CHAR_UUID,
    DOMAIN,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


@dataclass
class _FakeCharacteristic:
    uuid: str
    properties: list[str]


class _FakeService:
    def __init__(self, uuid: str, characteristics: list[_FakeCharacteristic]) -> None:
        self.uuid = uuid
        self.characteristics = characteristics

    def get_characteristic(self, uuid: str) -> _FakeCharacteristic | None:
        uuid_lower = uuid.lower()
        for characteristic in self.characteristics:
            if characteristic.uuid.lower() == uuid_lower:
                return characteristic
        return None


def _rf_gateway_services() -> list[_FakeService]:
    return [
        _FakeService(
            DEWERTOKIN_RF_GATEWAY_SERVICE_UUID,
            [
                _FakeCharacteristic(
                    DEWERTOKIN_RF_GATEWAY_WRITE_CHAR_UUID,
                    ["read", "write"],
                )
            ],
        )
    ]


def _make_entry(hass: HomeAssistant, bed_type: str = BED_TYPE_DEWERTOKIN) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="DewertOkin RF Gateway Test",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "DewertOkin RF Gateway Test",
            CONF_BED_TYPE: bed_type,
            CONF_MOTOR_COUNT: 4,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="dewertokin_rf_gateway_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


async def test_dewertokin_rf_gateway_selected_from_ble_model(
    hass: HomeAssistant,
    mock_bleak_client: MagicMock,
) -> None:
    """Test Bluetooth RF-Gateway model routes DewertOkin to RF-Gateway controller."""
    coordinator = AdjustableBedCoordinator(hass, _make_entry(hass))
    mock_bleak_client.services = []

    controller = await create_controller(
        coordinator,
        BED_TYPE_DEWERTOKIN,
        None,
        mock_bleak_client,
        ble_model=DEWERTOKIN_RF_GATEWAY_MODEL,
    )

    assert isinstance(controller, DewertOkinRfGatewayController)


async def test_okin_handle_rf_gateway_selected_from_gatt_pair(
    hass: HomeAssistant,
    mock_bleak_client: MagicMock,
) -> None:
    """Test RF-Gateway GATT pair routes Okin-handle entries to RF-Gateway controller."""
    coordinator = AdjustableBedCoordinator(hass, _make_entry(hass, BED_TYPE_OKIN_HANDLE))
    mock_bleak_client.services = _rf_gateway_services()

    controller = await create_controller(
        coordinator,
        BED_TYPE_OKIN_HANDLE,
        None,
        mock_bleak_client,
    )

    assert isinstance(controller, DewertOkinRfGatewayController)


async def test_okin_uuid_rf_gateway_selected_from_gatt_pair(
    hass: HomeAssistant,
    mock_bleak_client: MagicMock,
) -> None:
    """Test RF-Gateway GATT pair routes Okin UUID entries to RF-Gateway controller."""
    coordinator = AdjustableBedCoordinator(hass, _make_entry(hass, BED_TYPE_OKIN_UUID))
    mock_bleak_client.services = _rf_gateway_services()

    controller = await create_controller(
        coordinator,
        BED_TYPE_OKIN_UUID,
        None,
        mock_bleak_client,
    )

    assert isinstance(controller, DewertOkinRfGatewayController)


async def test_dewertokin_without_rf_gateway_signals_keeps_okin_handle(
    hass: HomeAssistant,
    mock_bleak_client: MagicMock,
) -> None:
    """Test ordinary DewertOkin entries keep the 6-byte Okin controller."""
    coordinator = AdjustableBedCoordinator(hass, _make_entry(hass))
    mock_bleak_client.services = []

    controller = await create_controller(
        coordinator,
        BED_TYPE_DEWERTOKIN,
        None,
        mock_bleak_client,
    )

    assert isinstance(controller, OkinHandleController)


async def test_rf_gateway_back_up_uses_8_byte_rf_packet(
    hass: HomeAssistant,
    mock_bleak_client: MagicMock,
) -> None:
    """Test RF-Gateway back-up writes the 8-byte RF command to the RF characteristic."""
    coordinator = AdjustableBedCoordinator(hass, _make_entry(hass))
    coordinator._client = mock_bleak_client
    mock_bleak_client.services = _rf_gateway_services()

    controller = await create_controller(
        coordinator,
        BED_TYPE_DEWERTOKIN,
        None,
        mock_bleak_client,
        ble_model=DEWERTOKIN_RF_GATEWAY_MODEL,
    )
    await controller.move_back_up()

    first_write = mock_bleak_client.write_gatt_char.call_args_list[0]
    assert first_write.args == (
        DEWERTOKIN_RF_GATEWAY_WRITE_CHAR_UUID,
        bytes.fromhex("e5fe160100000005"),
    )
    assert first_write.kwargs == {"response": True}


async def test_rf_gateway_keeps_standard_dewertokin_motor_keys(
    hass: HomeAssistant,
    mock_bleak_client: MagicMock,
) -> None:
    """Test RF-Gateway controller preserves standard DewertOkin motor entity keys."""
    coordinator = AdjustableBedCoordinator(hass, _make_entry(hass))
    mock_bleak_client.services = _rf_gateway_services()

    controller = await create_controller(
        coordinator,
        BED_TYPE_DEWERTOKIN,
        None,
        mock_bleak_client,
        ble_model=DEWERTOKIN_RF_GATEWAY_MODEL,
    )

    assert [spec.key for spec in controller.motor_control_specs] == [
        "back",
        "legs",
        "head",
        "feet",
    ]
