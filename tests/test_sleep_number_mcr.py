"""Tests for the older Sleep Number BAM / MCR controller."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.sleep_number_mcr import SleepNumberMcrController
from custom_components.adjustable_bed.const import (
    BED_TYPE_SLEEP_NUMBER_MCR,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    SLEEP_NUMBER_MCR_RX_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


def _mcr_address_from_mac(address: str) -> int:
    """Return the BAM/MCR address derived from the BLE MAC address."""
    parts = address.split(":")
    return (int(parts[-2], 16) << 8) | int(parts[-1], 16)


@pytest.fixture
def sleep_number_mcr_coordinator(hass: HomeAssistant, mock_coordinator_connected):
    """Create and connect a coordinator for a Sleep Number BAM/MCR test device."""

    async def _create(
        *,
        address: str,
        name: str,
        entry_id: str,
    ) -> AdjustableBedCoordinator:
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Sleep Number MCR Test Bed",
            data={
                CONF_ADDRESS: address,
                CONF_NAME: name,
                CONF_BED_TYPE: BED_TYPE_SLEEP_NUMBER_MCR,
                CONF_MOTOR_COUNT: 2,
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


class TestSleepNumberMcrController:
    """Test Sleep Number BAM / MCR controller behavior."""

    async def test_control_characteristic_uuid(self, sleep_number_mcr_coordinator) -> None:
        """Controller should write to the MCR RX characteristic."""
        coordinator = await sleep_number_mcr_coordinator(
            address="AA:BB:CC:DD:EE:51",
            name="64:DB:A0:07:DD:02",
            entry_id="sleep_number_mcr_uuid",
        )

        assert coordinator.controller.control_characteristic_uuid == SLEEP_NUMBER_MCR_RX_CHAR_UUID
        assert coordinator.controller.requires_notification_channel is True
        assert coordinator.controller.supports_motor_control is False

    async def test_query_config_hydrates_state(self, sleep_number_mcr_coordinator) -> None:
        """Connect-time hydration should read firmness and under-bed light state."""
        coordinator = await sleep_number_mcr_coordinator(
            address="AA:BB:CC:DD:EE:52",
            name="64:DB:A0:07:DD:03",
            entry_id="sleep_number_mcr_query_config",
        )

        assert coordinator.controller_state["sleep_number_left"] == 35
        assert coordinator.controller_state["sleep_number_right"] == 65
        assert coordinator.controller_state["under_bed_lights_on"] is True
        assert coordinator.controller.supports_bed_presence is False
        assert coordinator.controller.bed_presence_sides == ()

    async def test_set_sleep_number_setting_for_side_rounds_and_updates_state(
        self,
        sleep_number_mcr_coordinator,
    ) -> None:
        """Firmness writes should snap to 5-point increments and publish side state."""
        coordinator = await sleep_number_mcr_coordinator(
            address="AA:BB:CC:DD:EE:53",
            name="64:DB:A0:07:DD:04",
            entry_id="sleep_number_mcr_sleep_number",
        )

        await coordinator.controller.set_sleep_number_setting_for_side("right", 63)

        assert coordinator.controller_state["sleep_number_right"] == 65

    async def test_set_foundation_preset_for_side_updates_state(
        self,
        sleep_number_mcr_coordinator,
    ) -> None:
        """Preset writes should cache the last requested option per side."""
        coordinator = await sleep_number_mcr_coordinator(
            address="AA:BB:CC:DD:EE:54",
            name="64:DB:A0:07:DD:05",
            entry_id="sleep_number_mcr_preset",
        )

        await coordinator.controller.set_foundation_preset_for_side("left", "Flat")
        await coordinator.controller.set_foundation_preset_for_side("right", "Zero G")

        assert coordinator.controller_state["foundation_preset_left"] == "Flat"
        assert coordinator.controller_state["foundation_preset_right"] == "Zero G"

    async def test_read_bed_presence_returns_none_when_firmware_does_not_report_it(
        self,
        sleep_number_mcr_coordinator,
    ) -> None:
        """0.4.x BAM firmware should not expose occupancy sensors from a short chamber payload."""
        coordinator = await sleep_number_mcr_coordinator(
            address="AA:BB:CC:DD:EE:55",
            name="64:DB:A0:07:DD:06",
            entry_id="sleep_number_mcr_presence",
        )

        assert await coordinator.controller.read_bed_presence() is None
        assert coordinator.controller.supports_bed_presence is False

    async def test_notification_handler_reassembles_split_mcr_frames(
        self,
        sleep_number_mcr_coordinator,
    ) -> None:
        """Split MCR notifications should be buffered until a full frame is available."""
        coordinator = await sleep_number_mcr_coordinator(
            address="AA:BB:CC:DD:EE:56",
            name="64:DB:A0:07:DD:07",
            entry_id="sleep_number_mcr_chunked_notification",
        )
        controller = coordinator.controller
        assert isinstance(controller, SleepNumberMcrController)

        controller._response_buffer.clear()
        controller._response_frames.clear()
        controller._response_event.clear()
        # Simulate an in-flight request so the correlation check in
        # _handle_mcr_notification accepts the frame. Function 20 is the
        # under-bed light read; the response carries side 3 (outlet index).
        controller._outstanding_request_key = (20, 3)
        response = controller._build_frame(
            command_type=1,
            status=0x42,
            function_code=0x80 | 20,
            side=3,
            payload=b"\x01",
            sub_address=_mcr_address_from_mac("AA:BB:CC:DD:EE:56"),
        )

        controller._handle_mcr_notification(None, bytearray(response[:7]))
        assert controller._response_frames == []
        assert controller._response_event.is_set() is False

        controller._handle_mcr_notification(None, bytearray(response[7:]))

        assert len(controller._response_frames) == 1
        assert controller._response_frames[0].function_code == 20
        assert controller._response_frames[0].payload == b"\x01"
