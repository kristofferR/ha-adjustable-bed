"""Profile reloads reconcile app entities and preserve native unknown-state toggles."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.codec.malouf import TRANSPORTS
from custom_components.adjustable_bed.const import (
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_MALOUF_APP,
    CONF_BED_TYPE,
    DOMAIN,
)
from custom_components.adjustable_bed.controller_state import ControllerState, StateUpdate
from custom_components.adjustable_bed.cover import _cover_entities_for
from custom_components.adjustable_bed.light import _light_entities_for
from custom_components.adjustable_bed.sensor import _sensor_entities_for
from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON

from .conftest import make_controller_mock
from .state_helpers import state_writer
from .test_malouf_app import make_controller, written


def configure_entity_runtime(
    hass: HomeAssistant, controller: BedController, bed_type: str = BED_TYPE_MALOUF_APP
) -> MagicMock:
    controller._coordinator.motor_count = 2
    controller._coordinator.get_max_angle.return_value = 68.0
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_BED_TYPE: bed_type})
    entry.add_to_hass(hass)
    coordinator = MagicMock()
    coordinator.entry = entry
    coordinator.capability_controller = controller
    coordinator.controller = controller
    coordinator.has_massage = True
    coordinator.disable_angle_sensing = True
    coordinator.device_info = {}
    coordinator.entity_side = "left"
    coordinator.entity_unique_id.side_effect = lambda key: f"bed_{key}_left"
    return coordinator


@pytest.mark.parametrize(
    ("transport", "model", "app", "active_key"),
    [
        ("okin_new", "Premium", "lucid", "malouf_read"),
        ("richmat_framed", "GoodLifeBase", "lucid", "malouf_oz_save_memory_2"),
        ("richmat_framed", "Premium", "lucid", None),
        ("okin_new", "Premium", "malouf", None),
    ],
)
async def test_profile_app_buttons_follow_the_model(
    hass: HomeAssistant, transport: str, model: str, app: str, active_key: str | None
) -> None:
    controller = make_controller(transport, model, app)
    coordinator = configure_entity_runtime(hass, controller)

    entities = _button_entities_for(hass, coordinator)

    assert {
        entity.unique_id for entity in entities if "malouf_" in entity.unique_id
    } == ({f"bed_{active_key}_left"} if active_key else set())


@pytest.mark.parametrize("destination", ["richmat", "no_massage", "different_bed_type", "retain"])
async def test_profile_massage_sensor_follows_the_model(
    hass: HomeAssistant, destination: str
) -> None:
    controller = (
        make_controller_mock(
            controller_state_sensor_specs=(),
            position_number_specs=(),
        )
        if destination == "different_bed_type"
        else make_controller(
            "richmat_framed" if destination == "richmat" else "okin_new",
            "E450" if destination == "no_massage" else "S755",
        )
    )
    coordinator = configure_entity_runtime(
        hass, controller,
        BED_TYPE_DIAGNOSTIC if destination == "different_bed_type" else BED_TYPE_MALOUF_APP,
    )

    entities = _sensor_entities_for(hass, coordinator)

    assert any(
        entity.unique_id == "bed_malouf_massage_remaining_left" for entity in entities
    ) is (destination == "retain")


@pytest.mark.parametrize(
    ("transport", "expected"),
    [
        ("okin_legacy", ["e6fe16000002000003"]),
        ("okin_new", ["0502000200000000", "00b0"]),
    ],
)
async def test_feedback_light_entity_toggles_without_initial_state(
    hass: HomeAssistant, transport: str, expected: list[str]
) -> None:
    controller = make_controller(transport, "S750")
    coordinator = configure_entity_runtime(hass, controller)

    async def dispatch(command, *, cancel_running):
        assert cancel_running is False
        await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=dispatch)
    light = _light_entities_for(hass, coordinator)[0]
    assert light.is_on is None
    assert controller._light_status is None

    await light.async_toggle()

    assert [frame.hex() for frame in written(controller)] == expected
    assert light.is_on is None
    assert controller._light_status is None


@pytest.mark.parametrize(("light_byte", "is_on"), [(0x40, True), (0, False)])
async def test_light_entity_reflects_the_published_light_state(
    hass: HomeAssistant, light_byte: int, is_on: bool
) -> None:
    controller = make_controller("okin_legacy", "S750")
    coordinator = configure_entity_runtime(hass, controller)
    light = _light_entities_for(hass, coordinator)[0]
    light.async_write_ha_state = MagicMock()
    state = ControllerState()

    def publish(*updates: StateUpdate) -> None:
        state_writer(state)(*updates)
        light._handle_controller_state_update(state)

    controller._coordinator.handle_controller_state_updates.side_effect = publish
    data = bytearray(10)
    data[7] = light_byte
    controller._notification_handler(
        MagicMock(uuid=TRANSPORTS["okin_legacy"].notify_characteristic), data
    )

    assert state[UNDER_BED_LIGHTS_ON] is is_on
    assert light.is_on is is_on


@pytest.mark.parametrize("destination", ["different_bed_type", "okin", "retain"])
async def test_profile_altitude_covers_follow_the_transport(
    hass: HomeAssistant, destination: str
) -> None:
    controller = (
        make_controller_mock(
            motor_control_specs=(),
            supports_motor_control=False,
        )
        if destination == "different_bed_type"
        else make_controller("okin_new" if destination == "okin" else "richmat_framed", "Altitude")
    )
    coordinator = configure_entity_runtime(
        hass, controller,
        BED_TYPE_DIAGNOSTIC if destination == "different_bed_type" else BED_TYPE_MALOUF_APP,
    )
    keys = {"malouf_tilt_head", "malouf_full_tilt"}

    entities = _cover_entities_for(hass, coordinator)

    assert {
        entity.unique_id for entity in entities if "malouf_" in entity.unique_id
    } == ({f"bed_{key}_left" for key in keys} if destination == "retain" else set())
