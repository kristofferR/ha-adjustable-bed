"""Q-Plus Adjustable Remote position feedback (#239): pulse tables, sliders and targets."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.keeson.layout_app import FFE4, FFE9
from custom_components.adjustable_bed.beds.qplus_app import (
    FOOT_PULSE_TABLE,
    HEAD_PULSE_TABLE,
    QPlusAppController,
    pulse_to_angle,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_QPLUS_APP,
    CONF_BED_TYPE,
    CONF_PRODUCT_TYPE,
    DOMAIN,
    QPLUS_FOOT_MAX_ANGLE,
    QPLUS_HEAD_MAX_ANGLE,
)
from custom_components.adjustable_bed.services import SERVICE_SET_POSITION
from tests.error_helpers import raises_key
from tests.test_keeson_layout_app import coordinator

ADDRESS = "AA:BB:CC:DD:EE:FF"


def test_pulse_tables_end_at_the_travel_limits():
    assert len(HEAD_PULSE_TABLE) == 61 == QPLUS_HEAD_MAX_ANGLE + 1
    assert len(FOOT_PULSE_TABLE) == 33 == QPLUS_FOOT_MAX_ANGLE + 1


@pytest.mark.parametrize(
    ("pulse", "table", "angle"),
    [
        (0, HEAD_PULSE_TABLE, 0),
        (327, HEAD_PULSE_TABLE, 1),
        (20413, HEAD_PULSE_TABLE, 60),
        (25000, HEAD_PULSE_TABLE, 60),
        (0, FOOT_PULSE_TABLE, 0),
        (10000, FOOT_PULSE_TABLE, 32),
        # 32768 and above are inverted: 65535 - 65208 is 327.
        (65535, HEAD_PULSE_TABLE, 0),
        (65208, HEAD_PULSE_TABLE, 1),
    ],
)
def test_pulse_to_angle(pulse, table, angle):
    assert pulse_to_angle(pulse, table) == angle


def _frame(head: int, foot: int, length: int = 16) -> bytes:
    """A status frame with the head and foot pulse counts at bytes 3-4 and 5-6."""
    data = bytearray(length)
    data[0] = 0xED
    data[3:5] = head.to_bytes(2, "little")
    data[5:7] = foot.to_bytes(2, "little")
    return bytes(data)


def _positions(controller: QPlusAppController, data: bytes) -> dict[str, float]:
    callback = MagicMock()
    controller._notify_callback = callback
    controller._parse_notification(data)
    return {call.args[0]: call.args[1] for call in callback.call_args_list}


@pytest.mark.parametrize("layout", ["H", "M1", "M2", "M3"])
def test_p1_layouts_report_head_and_foot_as_back_and_legs(layout):
    controller = QPlusAppController(coordinator(), layout=layout)

    assert _positions(controller, _frame(327, 570)) == {"back": 1.0, "legs": 1.0}
    assert _positions(controller, _frame(0, 0)) == {"back": 0.0, "legs": 0.0}
    assert _positions(controller, _frame(20413, 8718)) == {"back": 60.0, "legs": 32.0}
    assert _positions(controller, _frame(65208, 0)) == {"back": 1.0, "legs": 0.0}
    assert _positions(controller, bytes([0xED, 0x00, 0x00])) == {}


def test_the_timer_frame_is_not_read_as_a_position():
    """A5 0B 0D carries the massage timer's seconds where the pulse count sits."""
    coord = coordinator()
    controller = QPlusAppController(coord, layout="H")
    data = bytearray(16)
    data[:5] = bytes.fromhex("a50b0d0259")  # 601 seconds: the 20 minute timer

    assert _positions(controller, bytes(data)) == {}
    assert coord.controller_state["app_timer_status"] == 20


def test_mx_reports_no_position():
    """MX is the app's P2 remote; its status frames were never read for positions."""
    controller = QPlusAppController(coordinator(), layout="MX")

    assert not controller.supports_position_feedback
    assert controller.position_number_specs == ()
    assert _positions(controller, _frame(327, 570, length=20)) == {}


class _Gatt:
    def __init__(self, **fields) -> None:
        self.__dict__.update(fields)


async def _loaded(hass: HomeAssistant, client: MagicMock, layout: str) -> MockConfigEntry:
    write = _Gatt(uuid=FFE9, properties=("write",), handle=1, descriptors=[])
    notify = _Gatt(uuid=FFE4, properties=("notify",), handle=2, descriptors=[])
    client.services = [_Gatt(uuid="ffe5", characteristics=[write, notify])]
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Q-Plus Test Bed",
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Q-Plus Test Bed",
            CONF_BED_TYPE: BED_TYPE_QPLUS_APP,
            CONF_PRODUCT_TYPE: layout,
        },
        unique_id=ADDRESS,
        # A new setup; an older entry keeps the angle-sensing choice it ran with.
        version=5,
        minor_version=9,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_sliders_are_the_reported_back_and_legs_axes(
    hass: HomeAssistant, mock_bleak_client, mock_coordinator_connected, enable_custom_integrations
):
    """A new setup reads positions, and gets the two axes the notifications report."""
    entry = await _loaded(hass, mock_bleak_client, "H")

    registry = er.async_get(hass)
    for key, max_angle in (("back", 60), ("legs", 32)):
        entity_id = registry.async_get_entity_id("number", DOMAIN, f"{ADDRESS}_{key}_position")
        assert entity_id is not None
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.attributes["max"] == max_angle
        assert state.attributes["unit_of_measurement"] == "°"
    for key in ("head", "feet"):
        assert registry.async_get_entity_id("number", DOMAIN, f"{ADDRESS}_{key}_position") is None
    # Validation and slider limits agree, connected or not.
    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert (coordinator.get_max_angle("back"), coordinator.get_max_angle("legs")) == (60, 32)


@pytest.mark.parametrize(
    ("layout", "motor", "position", "message"),
    [
        ("H", "head", 10, "invalid_motor_for_bed_type"),
        ("H", "back", 61, "invalid_position_range"),
        ("H", "legs", 33, "invalid_position_range"),
        ("MX", "back", 10, "position_feedback_not_supported"),
    ],
)
async def test_set_position_rejects_axes_and_angles_it_cannot_report(
    hass: HomeAssistant,
    mock_bleak_client,
    mock_coordinator_connected,
    enable_custom_integrations,
    layout: str,
    motor: str,
    position: int,
    message: str,
):
    """Targets beyond the pulse tables would only stall the seek; MX reports nothing."""
    entry = await _loaded(hass, mock_bleak_client, layout)
    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)

    with raises_key(message, ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_POSITION,
            {"device_id": [device.id], "motor": motor, "position": position},
            blocking=True,
        )
