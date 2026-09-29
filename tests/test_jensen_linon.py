"""Tests for the Jensen LinOn profile on the LinonPI services.

Frame vectors (TVnnn) come from the frozen clean-room audit of
air.no.jensen.adjustablesleep 2.0.37.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.jensen_linon import (
    HOLD_INTERVAL_MS,
    JensenLinonCommands,
    JensenLinonController,
)
from custom_components.adjustable_bed.beds.svane import SvaneController
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.const import (
    BED_TYPE_SVANE,
    CONF_BED_TYPE,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    SVANE_CHAR_DOWN_UUID,
    SVANE_CHAR_POSITION_UUID,
    SVANE_CHAR_UP_UUID,
    SVANE_FEET_SERVICE_UUID,
    SVANE_HEAD_SERVICE_UUID,
    SVANE_LIGHT_ON_OFF_UUID,
    SVANE_LIGHT_SERVICE_UUID,
    SVANE_VARIANT_JENSEN_LINON,
    VARIANT_AUTO,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import is_jensen_linon_name

HEAD = SVANE_HEAD_SERVICE_UUID
FOOT = SVANE_FEET_SERVICE_UUID
UP = SVANE_CHAR_UP_UUID
DOWN = SVANE_CHAR_DOWN_UUID
STOP_PAIR = [(HEAD, UP, "ff"), (FOOT, UP, "ff")]


def make_controller(pulses: tuple[int, int] = (10, 100)) -> JensenLinonController:
    """Build a controller whose writes are recorded instead of sent."""
    coordinator = MagicMock()
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count, coordinator.motor_pulse_delay_ms = pulses
    controller = JensenLinonController(coordinator)
    controller._write_to_service_char = AsyncMock()
    return controller


def written(controller: JensenLinonController) -> list[tuple[str, str, str]]:
    """Return every (service, characteristic, frame) write, in order."""
    mock = controller._write_to_service_char
    assert isinstance(mock, AsyncMock)
    return [(c.args[0], c.args[1], c.args[2].hex()) for c in mock.await_args_list]


@pytest.fixture
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Skip the 800 ms hold interval (this patches ``asyncio.sleep`` itself)."""
    sleep = AsyncMock()
    monkeypatch.setattr("custom_components.adjustable_bed.beds.jensen_linon.asyncio.sleep", sleep)
    return sleep


class TestProfileSelection:
    """The Jensen app's name rule selects its profile for new Bluetooth entries."""

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Jensen Bed", True),
            ("My Adjustable Bed", True),
            ("Svane Bed", False),
            (None, False),
        ],
    )
    def test_name_rule(self, name: str | None, expected: bool) -> None:
        assert is_jensen_linon_name(name) is expected


@pytest.mark.usefixtures("_no_sleep")
class TestJensenLinonMovement:
    """Held motion, STOP and flat against the app vectors."""

    @pytest.mark.parametrize(
        ("method", "target"),
        [
            ("move_head_up", (HEAD, UP)),  # TV101
            ("move_head_down", (HEAD, DOWN)),  # TV102
            ("move_legs_up", (FOOT, UP)),  # TV104
            ("move_legs_down", (FOOT, DOWN)),  # TV111
        ],
    )
    async def test_single_motor_hold_then_stop(
        self, method: str, target: tuple[str, str], _no_sleep: AsyncMock
    ) -> None:
        """The default 0.9 s hold becomes 01 every 800 ms, then STOP head then foot."""
        controller = make_controller()

        await getattr(controller, method)()

        assert written(controller) == [(*target, "01")] * 3 + STOP_PAIR
        assert [c.args[0] for c in _no_sleep.await_args_list] == [HOLD_INTERVAL_MS / 1000] * 2

    async def test_combined_motion_alternates_head_and_foot(self) -> None:
        """TV113: head up + foot down steps head, then foot, then STOP."""
        controller = make_controller()

        await controller.move_simultaneously("back", True, "legs", False, duration_ms=800)

        assert written(controller) == [(HEAD, UP, "01"), (FOOT, DOWN, "01")] + STOP_PAIR

    async def test_combined_motion_rejects_other_axes(self) -> None:
        controller = make_controller()
        with pytest.raises(ValueError):
            await controller.move_simultaneously("back", True, "head", True)

    async def test_cancel_still_sends_stop(self) -> None:
        """A cancelled hold writes nothing more but always releases the bed."""
        controller = make_controller()
        controller._coordinator.cancel_command.set()

        await controller.move_head_up()

        assert written(controller) == STOP_PAIR

    async def test_stop_all(self) -> None:
        """TV099/TV100: STOP is FF to the head, then the foot, up characteristic."""
        controller = make_controller()

        await controller.stop_all()
        await controller.move_legs_stop()

        assert written(controller) == STOP_PAIR * 2

    async def test_flat(self) -> None:
        """TV125/TV126: 00 to the head, then the foot, position characteristic."""
        controller = make_controller()

        await controller.preset_flat()

        assert written(controller) == [
            (HEAD, SVANE_CHAR_POSITION_UUID, "00"),
            (FOOT, SVANE_CHAR_POSITION_UUID, "00"),
        ]


class TestJensenLinonLights:
    """Under-bed light on/off; the app's intensity path never writes."""

    async def test_light_frames_and_state(self) -> None:
        """TV133/TV134: on 01 00 00, off 00 00 00 on the under-bed characteristic."""
        controller = make_controller()

        await controller.lights_on()
        await controller.lights_toggle()
        await controller.lights_toggle()

        target = (SVANE_LIGHT_SERVICE_UUID, SVANE_LIGHT_ON_OFF_UUID)
        assert written(controller) == [(*target, "010000"), (*target, "000000"), (*target, "010000")]
        assert controller.get_light_state() == {"is_on": True}
        controller._coordinator.handle_controller_state_updates.assert_called_with(
            {"under_bed_lights_on": True}
        )

    def test_light_frame_builder(self) -> None:
        assert JensenLinonCommands.light(True).hex() == "010000"
        assert JensenLinonCommands.light(False).hex() == "000000"


class TestJensenLinonCapabilities:
    """Paths the app never sends to the bed are not offered."""

    def test_capabilities(self) -> None:
        controller = make_controller()

        assert controller.supports_preset_flat
        assert controller.supports_discrete_light_control
        assert controller.supports_simultaneous_movement
        assert not controller.supports_light_level_control
        assert not controller.supports_memory_presets
        assert not controller.supports_memory_programming
        assert controller.memory_slot_count == 0
        assert not controller.supports_preset_zero_g
        assert not controller.supports_position_feedback

    @pytest.mark.parametrize(
        ("method", "args"),
        [
            ("set_light_level", (5,)),
            ("preset_memory", (1,)),
            ("program_memory", (1,)),
            ("preset_zero_g", ()),
        ],
    )
    async def test_unreachable_paths_raise(self, method: str, args: tuple[int, ...]) -> None:
        controller = make_controller()
        with pytest.raises(NotImplementedError):
            await getattr(controller, method)(*args)
        assert written(controller) == []

    async def test_notifications_are_not_subscribed(self) -> None:
        """The app never subscribes to LinOn reports."""
        controller = make_controller()
        client = MagicMock()
        client.start_notify = AsyncMock()
        controller._coordinator.client = client

        await controller.start_notify(lambda *_: None)
        await controller.read_positions()

        client.start_notify.assert_not_awaited()


@pytest.mark.parametrize(
    ("name", "variant", "expected"),
    [
        ("Jensen Bed", VARIANT_AUTO, SVANE_VARIANT_JENSEN_LINON),
        ("Adjustable Bed", VARIANT_AUTO, SVANE_VARIANT_JENSEN_LINON),
        ("Svane Bed", VARIANT_AUTO, VARIANT_AUTO),
        ("Svane Bed", SVANE_VARIANT_JENSEN_LINON, SVANE_VARIANT_JENSEN_LINON),
    ],
)
async def test_bluetooth_setup_stores_the_app_profile(
    hass: HomeAssistant,
    mock_bluetooth_service_info: MagicMock,
    name: str,
    variant: str,
    expected: str,
) -> None:
    """A new entry keeps the profile the device name selects; auto stays Svane."""
    mock_bluetooth_service_info.name = name
    mock_bluetooth_service_info.service_uuids = [SVANE_HEAD_SERVICE_UUID]
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._discovery_info = mock_bluetooth_service_info
    finish = AsyncMock()
    flow._finish_with_verify = finish

    await flow.async_step_bluetooth_confirm(
        {
            CONF_BED_TYPE: BED_TYPE_SVANE,
            CONF_PROTOCOL_VARIANT: variant,
            CONF_DISCONNECT_AFTER_COMMAND: False,
        }
    )

    assert finish.await_args is not None
    assert finish.await_args.args[0][CONF_PROTOCOL_VARIANT] == expected


@pytest.mark.parametrize(
    ("variant", "controller_type"),
    [
        (SVANE_VARIANT_JENSEN_LINON, JensenLinonController),
        (VARIANT_AUTO, SvaneController),
        (None, SvaneController),
    ],
)
async def test_factory_uses_the_stored_profile(
    hass: HomeAssistant, variant: str | None, controller_type: type
) -> None:
    """Existing entries without the Jensen profile keep the Svane controller."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:22",
            CONF_NAME: "Jensen Bed",
            CONF_BED_TYPE: BED_TYPE_SVANE,
        },
    )
    coordinator = AdjustableBedCoordinator(hass, entry)

    controller = await create_controller(
        coordinator, BED_TYPE_SVANE, variant, None, device_name="Jensen Bed"
    )

    assert type(controller) is controller_type
