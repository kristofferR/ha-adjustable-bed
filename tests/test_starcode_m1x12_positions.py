"""Head, foot and lumbar positions of the Adjustable Comfort M1X12 app (#628)."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.bed_traits import default_connection_mode, reads_positions
from custom_components.adjustable_bed.const import (
    BED_TYPE_STARCODE_M1X12,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONNECTION_MODE_RELEASE,
)
from custom_components.adjustable_bed.cover import _cover_entities_for
from custom_components.adjustable_bed.number import (
    AdjustableBedPositionNumber,
    _number_entities_for,
)
from custom_components.adjustable_bed.sensor import _sensor_entities_for
from custom_components.adjustable_bed.services import _position_config
from custom_components.adjustable_bed.setup_questions import setup_profile
from tests.error_helpers import raises_key
from tests.test_starcode_m1x12 import _create_controller, _GattClient

GROUP = "custom_components.adjustable_bed.beds.starcode.accessory_group"


def _motor_report(head: int, foot: int, lumbar: int, *, stopped: bool = True) -> bytearray:
    """The app's motor report: Parts 1, 2 and 4 at bytes 4, 6 and 8."""
    frame = bytearray(20)
    frame[:2] = b"\xa5\x0d"
    frame[4], frame[6], frame[8] = head, foot, lumbar
    frame[17] = 0 if stopped else 1
    return frame


@pytest.mark.parametrize("profile", ("cb25", "f23", "kneading"))
async def test_reports_reach_the_position_system_as_readings(
    hass: HomeAssistant, profile: str
) -> None:
    client = _GattClient()
    coordinator, controller = await _create_controller(hass, profile=profile, client=client)
    assert coordinator.disable_angle_sensing is False
    await coordinator.async_start_notify()

    client.notify_callback(Mock(), _motor_report(22, 0, 140, stopped=False))

    # The app clamps each Part to 100.
    assert coordinator.position_data == {"head": 22.0, "feet": 0.0, "lumbar": 100.0}
    covers = {cover.entity_description.key: cover for cover in _cover_entities_for(hass, coordinator)}
    assert {key: cover.current_cover_position for key, cover in covers.items()} == {
        "m1x12_part_1": 22,
        "m1x12_part_2": 0,
        "m1x12_part_4": 100,
    }
    # Each cover keeps the command lane it had before it showed a position.
    assert covers["m1x12_part_1"]._motor_resource == "motor:m1x12_part_1"
    # The app has no way to set a position: the readings stay sensors, with no slider.
    sensors = {entity.unique_id for entity in _sensor_entities_for(hass, coordinator)}
    assert {
        coordinator.entity_unique_id(f"starcode_m1x12_part_{part}_position") for part in (1, 2, 4)
    } <= sensors
    assert coordinator.controller_state["part_1_position"] == 22
    assert not any(
        isinstance(entity, AdjustableBedPositionNumber)
        for entity in _number_entities_for(hass, coordinator)
    )
    with raises_key("position_feedback_not_supported", ServiceValidationError):
        _position_config(coordinator, controller, "head", 30)


async def test_recalls_follow_and_other_actions_do_not(hass: HomeAssistant) -> None:
    _coordinator, controller = await _create_controller(hass, client=_GattClient())
    follow = AsyncMock()
    controller.follow_autonomous_move = follow  # type: ignore[method-assign]
    with (
        patch.object(controller, "write_command", AsyncMock()) as write,
        patch(f"{GROUP}.interrupt_conflicting_group", AsyncMock()),
        patch(f"{GROUP}.cancel_group_operations"),
    ):
        await controller.preset_flat()
        # Three copies of the key, then STOP, before the bed is followed.
        assert [call.kwargs.get("repeat_count", 1) for call in write.await_args_list] == [3, 1]
        await controller.preset_memory(2)
        await controller.preset_memory(8)
        assert follow.await_count == 3
        for action in ("part_1_up", "union_down", "save_tv", "light_on", "massage_toggle"):
            await controller.app_action(action)

    assert follow.await_count == 3


def test_a_new_bed_reads_positions_and_hands_the_link_back() -> None:
    profile = setup_profile(BED_TYPE_STARCODE_M1X12)
    assert profile is not None
    assert profile.fixed_values()[CONF_DISABLE_ANGLE_SENSING] is False
    # A bed set up before this stored nothing, so it reads its positions too.
    assert reads_positions({CONF_BED_TYPE: BED_TYPE_STARCODE_M1X12})
    assert default_connection_mode(BED_TYPE_STARCODE_M1X12) == CONNECTION_MODE_RELEASE
