"""Tests for the Jensen LinOn profile on the LinonPI services.

Frame vectors (TVnnn) come from the frozen clean-room audit of
air.no.jensen.adjustablesleep 2.0.37.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.jensen_linon import (
    HOLD_INTERVAL_MS,
    JensenLinonCommands,
    JensenLinonController,
)
from custom_components.adjustable_bed.beds.svane import SvaneController
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    AdjustableBedOptionsFlow,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_SVANE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
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
from custom_components.adjustable_bed.pairing import build_pair_entry_data, effective_child_data

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
        """The default 0.9 s hold becomes two 800 ms steps, then STOP head then foot."""
        controller = make_controller()

        await getattr(controller, method)()

        assert written(controller) == [(*target, "01")] * 2 + STOP_PAIR
        assert [c.args[0] for c in _no_sleep.await_args_list] == [HOLD_INTERVAL_MS / 1000] * 2

    async def test_combined_motion_alternates_head_and_foot(self, _no_sleep: AsyncMock) -> None:
        """TV113: head up + foot down steps head, then foot, each held before STOP."""
        controller = make_controller()

        await controller.move_simultaneously("back", True, "legs", False, duration_ms=800)

        assert written(controller) == [(HEAD, UP, "01"), (FOOT, DOWN, "01")] + STOP_PAIR
        # The foot's step is held for a full interval too, not stopped at once.
        assert _no_sleep.await_count == 2

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

    async def test_foot_stop_follows_a_failed_head_stop(self) -> None:
        """Both motors get STOP even when the head write fails."""
        controller = make_controller()
        head_error = BleakError("head write failed")
        controller._write_to_service_char.side_effect = [head_error, None]

        with pytest.raises(BleakError):
            await controller.stop_all()

        assert written(controller) == STOP_PAIR

    async def test_failed_move_keeps_its_error(self) -> None:
        """A STOP failure after a failed MOVE does not replace the MOVE error."""
        controller = make_controller()
        move_error = BleakError("move write failed")
        stop_error = ConnectionError("Not connected to bed")
        controller._write_to_service_char.side_effect = [move_error, stop_error, stop_error]

        with pytest.raises(BleakError) as raised:
            await controller.move_head_up()

        assert raised.value is move_error
        assert written(controller) == [(HEAD, UP, "01"), *STOP_PAIR]

    async def test_stop_all(self) -> None:
        """TV099/TV100: STOP is FF to the head, then the foot, up characteristic."""
        controller = make_controller()

        await controller.stop_all()
        await controller.move_legs_stop()

        assert written(controller) == STOP_PAIR * 2

    async def test_interrupted_flat_sends_stop(self) -> None:
        """A flat cancelled mid-write releases both motors and keeps the cancellation."""
        controller = make_controller()
        controller._write_to_service_char.side_effect = [asyncio.CancelledError, None, None]

        with pytest.raises(asyncio.CancelledError):
            await controller.preset_flat()

        assert written(controller) == [(HEAD, SVANE_CHAR_POSITION_UUID, "00"), *STOP_PAIR]

    async def test_flat_cancelled_between_motors_sends_stop(self) -> None:
        """A stop request after the head's frame releases the head again."""
        controller = make_controller()

        async def write(*_args: object, **_kwargs: object) -> None:
            controller._coordinator.cancel_command.set()

        controller._write_to_service_char.side_effect = write

        await controller.preset_flat()

        assert written(controller) == [(HEAD, SVANE_CHAR_POSITION_UUID, "00"), *STOP_PAIR]

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


@pytest.mark.parametrize(
    ("initial", "requested"),
    [(VARIANT_AUTO, SVANE_VARIANT_JENSEN_LINON), (SVANE_VARIANT_JENSEN_LINON, VARIANT_AUTO)],
)
async def test_paired_options_reject_a_shared_profile_change(
    hass: HomeAssistant, initial: str, requested: str
) -> None:
    """One pair side's LinOn profile is never copied onto a Svane side."""

    def side(address: str, variant: str) -> dict:
        return {
            CONF_ADDRESS: address,
            CONF_NAME: "Bed",
            CONF_BED_TYPE: BED_TYPE_SVANE,
            CONF_PROTOCOL_VARIANT: variant,
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
            CONF_DISCONNECT_AFTER_COMMAND: False,
        }

    entry = MockConfigEntry(
        domain=DOMAIN,
        data=build_pair_entry_data(
            side("AA:BB:CC:DD:EE:11", initial),
            side("AA:BB:CC:DD:EE:22", VARIANT_AUTO),
            name="Paired bed",
        ),
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id

    result = await flow.async_step_settings({CONF_PROTOCOL_VARIANT: requested})

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_PROTOCOL_VARIANT: "jensen_linon_unpair_first"}
    assert effective_child_data(entry.data, "right")[CONF_PROTOCOL_VARIANT] == VARIANT_AUTO


async def test_svane_light_slider_removed_for_linon(
    hass: HomeAssistant, mock_coordinator_connected, enable_custom_integrations
) -> None:
    """Switching a Svane entry to LinOn drops its now-unsupported light slider."""
    del mock_coordinator_connected, enable_custom_integrations
    from homeassistant.helpers import entity_registry as er

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Jensen Bed",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "Jensen Bed",
            CONF_BED_TYPE: BED_TYPE_SVANE,
            CONF_PROTOCOL_VARIANT: SVANE_VARIANT_JENSEN_LINON,
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="linon_stale_light_entry",
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "number", DOMAIN, "AA:BB:CC:DD:EE:FF_light_level", config_entry=entry
    )

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert registry.async_get_entity_id("number", DOMAIN, "AA:BB:CC:DD:EE:FF_light_level") is None
