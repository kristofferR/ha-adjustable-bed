"""Tests for the Jensen JMC400 controller.

Frame vectors come from the frozen clean-room audit of
air.no.jensen.adjustablesleep 2.0.29; position reports and calibration come
from the JMC400 support bundle and capture in issue #631.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.jensen import (
    FOOT_POS_FLAT,
    FOOT_POS_MAX,
    HEAD_POS_FLAT,
    HEAD_POS_MAX,
    JensenCommands,
    JensenController,
    JensenFeatureFlags,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_JENSEN,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_JENSEN_PIN,
    CONF_MOTOR_COUNT,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    JENSEN_CHAR_UUID,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

from .conftest import make_controller_mock

JENSEN_MODULE = "custom_components.adjustable_bed.beds.jensen"


def report(state: int, head: int, foot: int) -> bytearray:
    """Build a 0x10 position report the way the JMC400 sends it."""
    return bytearray([0x10, state, *head.to_bytes(2, "little"), *foot.to_bytes(2, "little")])


@pytest.fixture
def _shorten_mocked_config_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep mocked response timeouts while avoiding five-second waits."""
    monkeypatch.setattr(f"{JENSEN_MODULE}._CONFIG_RESPONSE_TIMEOUT", 0.01)
    monkeypatch.setattr(f"{JENSEN_MODULE}._POSITION_RESPONSE_TIMEOUT", 0.01)


@pytest.fixture
def _fast_movement_monitor(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink the movement monitor's safeguards so tests run quickly."""
    monkeypatch.setattr(f"{JENSEN_MODULE}._MOVEMENT_START_SECONDS", 0.05)
    monkeypatch.setattr(f"{JENSEN_MODULE}._MOVEMENT_STALL_SECONDS", 0.05)
    monkeypatch.setattr(f"{JENSEN_MODULE}._POSITION_RESPONSE_TIMEOUT", 0.05)


@pytest.fixture
def mock_jensen_config_entry_data() -> dict:
    """Return mock config entry data for Jensen bed."""
    return {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Jensen Test Bed",
        CONF_BED_TYPE: BED_TYPE_JENSEN,
        CONF_MOTOR_COUNT: 2,
        CONF_HAS_MASSAGE: False,
        CONF_DISABLE_ANGLE_SENSING: True,
        CONF_PREFERRED_ADAPTER: "auto",
    }


@pytest.fixture
def mock_jensen_config_entry(
    hass: HomeAssistant,
    mock_jensen_config_entry_data: dict,
    _shorten_mocked_config_timeout: None,
) -> MockConfigEntry:
    """Return a mock config entry for Jensen bed."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Jensen Test Bed",
        data=mock_jensen_config_entry_data,
        unique_id="AA:BB:CC:DD:EE:FF",
        entry_id="jensen_test_entry",
    )
    entry.add_to_hass(hass)
    return entry


def make_controller(hass: HomeAssistant | None = None) -> JensenController:
    """Build a controller whose writes are recorded instead of sent."""
    coordinator = MagicMock()
    coordinator.hass = hass
    coordinator.address = "AA:BB:CC:DD:EE:FF"
    coordinator.disable_angle_sensing = False
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count = 1
    coordinator.motor_pulse_delay_ms = 1
    controller = JensenController(coordinator)
    controller._write_gatt_with_retry = AsyncMock()
    controller.motor_pulse_settings = MagicMock(return_value=(1, 1))
    return controller


def written(controller: JensenController) -> list[bytes]:
    """Return every frame the controller wrote, in order."""
    mock = controller._write_gatt_with_retry
    assert isinstance(mock, AsyncMock)
    return [write_call.args[1] for write_call in mock.await_args_list]


class TestJensenFrames:
    """Frame builders against artifact and capture vectors."""

    @pytest.mark.parametrize(
        ("frame", "expected"),
        [
            (JensenCommands.pin_unlock("3060"), "1e03000600"),
            (JensenCommands.CONFIG_READ_ALL, "0a00000000"),
            (JensenCommands.MOTOR_STOP, "100000000000"),
            (JensenCommands.motion(True, None), "100100000000"),
            (JensenCommands.motion(False, None), "100200000000"),
            (JensenCommands.motion(None, True), "101000000000"),
            (JensenCommands.motion(None, False), "102000000000"),
            (JensenCommands.motion(True, True), "101100000000"),
            (JensenCommands.motion(True, False), "102100000000"),
            (JensenCommands.motion(False, True), "101200000000"),
            (JensenCommands.motion(False, False), "102200000000"),
            (JensenCommands.PRESET_FLAT, "108100000000"),
            (JensenCommands.PRESET_MEMORY_SAVE, "104000000000"),
            (JensenCommands.PRESET_MEMORY_RECALL, "108000000000"),
            # The #631 capture's Memory 1 recall: head 30771, foot 30000.
            (JensenCommands.goto_position(30771, 30000), "100433783075"),
            # The #631 capture's massage sweep: head 6, wave 6.
            (JensenCommands.massage(6, 0, 6), "120600060000"),
            (JensenCommands.MASSAGE_OFF, "120000000000"),
            (JensenCommands.light(4), "130204000000"),
            # 2.0.37 vector TV078.
            (JensenCommands.LIGHT_OFF, "130200000032"),
            (JensenCommands.fan(4), "140400000050"),
            (JensenCommands.FAN_OFF, "140000000050"),
        ],
    )
    def test_frame_bytes(self, frame: bytes, expected: str) -> None:
        """Each builder emits the documented frame."""
        assert frame.hex() == expected

    def test_named_motion_frames_match_builder(self) -> None:
        """The named single-section frames are the builder's frames."""
        assert JensenCommands.motion(True, None) == JensenCommands.MOTOR_HEAD_UP
        assert JensenCommands.motion(False, None) == JensenCommands.MOTOR_HEAD_DOWN
        assert JensenCommands.motion(None, True) == JensenCommands.MOTOR_FOOT_UP
        assert JensenCommands.motion(None, False) == JensenCommands.MOTOR_FOOT_DOWN
        assert JensenCommands.motion(None, None) == JensenCommands.MOTOR_STOP


class TestJensenController:
    """Controller setup and PIN handling."""

    async def test_default_pin_is_3060(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
    ):
        """Test default PIN is 3060 when not configured."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        assert coordinator.controller.control_characteristic_uuid == JENSEN_CHAR_UUID
        assert coordinator.controller._build_pin_unlock_command().hex() == "1e03000600"

    async def test_custom_pin_from_config(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry_data: dict,
        mock_coordinator_connected,
    ):
        """Test custom PIN from config entry."""
        mock_jensen_config_entry_data[CONF_JENSEN_PIN] = "1234"
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Jensen Test Bed",
            data=mock_jensen_config_entry_data,
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id="jensen_test_entry_pin",
        )

        coordinator = AdjustableBedCoordinator(hass, entry)
        await coordinator.async_connect()

        assert coordinator.controller._build_pin_unlock_command().hex() == "1e01020304"

    def test_invalid_pin_falls_back_to_default(self, caplog: pytest.LogCaptureFixture):
        """A PIN without digits sends the default PIN."""
        controller = JensenController(MagicMock(), pin="abc")

        assert controller._build_pin_unlock_command().hex() == "1e03000600"
        assert "Invalid Jensen PIN" in caplog.text

    def test_rejected_pin_is_logged(self, caplog: pytest.LogCaptureFixture):
        """The bed's PIN reply warns when it did not unlock."""
        controller = make_controller()

        controller._handle_notification(MagicMock(), bytearray([0x1E, 0x01]))
        assert "rejected the configured PIN" not in caplog.text

        controller._handle_notification(MagicMock(), bytearray([0x1E, 0x00]))
        assert "rejected the configured PIN" in caplog.text


class TestJensenWriteMode:
    """The app writes without response."""

    @pytest.mark.parametrize(
        ("properties", "expected_response"),
        [
            (["write", "write-without-response", "notify"], False),
            (["write-without-response", "notify"], False),
            (["write", "notify"], True),
        ],
    )
    async def test_write_mode_follows_characteristic(
        self, properties: list[str], expected_response: bool
    ):
        """Write without response unless the characteristic only supports writes."""
        characteristic = MagicMock()
        characteristic.uuid = JENSEN_CHAR_UUID
        characteristic.properties = properties
        service = MagicMock()
        service.uuid = "00001234-0000-1000-8000-00805f9b34fb"
        service.characteristics = [characteristic]
        controller = make_controller()
        client = controller._coordinator.client
        client.is_connected = True
        client.services = [service]
        client.start_notify = AsyncMock()
        controller.read_positions = AsyncMock()

        await controller.start_notify(None)

        pin_write = controller._write_gatt_with_retry.await_args_list[0]
        assert pin_write.args == (JENSEN_CHAR_UUID, JensenCommands.pin_unlock("3060"))
        assert pin_write.kwargs["response"] is expected_response


class TestJensenNotificationStartup:
    """Test Jensen notification startup behavior."""

    async def test_start_notify_sends_pin_then_read_position(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Callback-less startup still unlocks and warms up command acceptance."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()
        mock_bleak_client.write_gatt_char.reset_mock()

        await coordinator.controller.start_notify(None)

        calls = mock_bleak_client.write_gatt_char.call_args_list
        assert calls[0].args == (JENSEN_CHAR_UUID, JensenCommands.pin_unlock("3060"))
        assert calls[1].args == (JENSEN_CHAR_UUID, JensenCommands.READ_POSITION)
        assert calls[0].kwargs == {"response": False}

    async def test_start_notify_waits_for_read_position_response(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """No later operation can inherit the warm-up query's response."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()
        mock_bleak_client.write_gatt_char = AsyncMock()

        notify_task = asyncio.create_task(coordinator.controller.start_notify(None))
        await asyncio.sleep(0)

        assert not notify_task.done()
        assert mock_bleak_client.write_gatt_char.call_args_list[-1].args == (
            JENSEN_CHAR_UUID,
            JensenCommands.READ_POSITION,
        )

        coordinator.controller._handle_notification(MagicMock(), report(0xFF, 30000, 30000))
        await notify_task

    async def test_start_notify_continues_without_warmup_response(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        caplog: pytest.LogCaptureFixture,
    ):
        """A missing warm-up response must not prevent command startup."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()
        mock_bleak_client.write_gatt_char = AsyncMock()

        await coordinator.controller.start_notify(None)

        mock_bleak_client.start_notify.assert_awaited()
        assert "Timeout waiting for Jensen warm-up position response" in caplog.text

    async def test_start_notify_none_keeps_position_updates_ignored(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
    ):
        """Callback-less startup does not publish positions."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        await coordinator.controller.start_notify(None)
        coordinator.controller._handle_notification(MagicMock(), report(0x00, 30400, 29700))

        assert coordinator.controller._notify_callback is None
        assert coordinator._position_data == {}


class TestJensenCoordinatorAuthRefresh:
    """Test Jensen command auth refresh in coordinator command paths."""

    async def test_async_execute_controller_command_refreshes_pin(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
    ):
        """Test coordinator refreshes Jensen PIN before controller command execution."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        coordinator._client = MagicMock()
        coordinator._client.is_connected = True
        coordinator._controller = make_controller_mock()
        coordinator._controller.send_pin = AsyncMock()
        coordinator._controller.command_called = AsyncMock()

        async def _command_fn(_controller):
            await _controller.command_called()

        await coordinator.async_execute_controller_command(_command_fn, cancel_running=False)

        coordinator._controller.assert_has_calls(
            [call.send_pin(), call.command_called()],
            any_order=False,
        )

    async def test_async_write_command_refreshes_pin(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
    ):
        """Test coordinator refreshes Jensen PIN before raw write commands."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        coordinator._client = MagicMock()
        coordinator._client.is_connected = True
        coordinator._controller = make_controller_mock()
        coordinator._controller.send_pin = AsyncMock()
        coordinator._controller.write_command = AsyncMock()

        await coordinator.async_write_command(
            JensenCommands.PRESET_FLAT,
            cancel_running=False,
        )

        send_pin_idx = coordinator._controller.mock_calls.index(call.send_pin())
        write_idx = next(
            idx
            for idx, mock_call in enumerate(coordinator._controller.mock_calls)
            if mock_call[0] == "write_command"
        )
        assert send_pin_idx < write_idx

    async def test_async_stop_command_refreshes_pin(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
    ):
        """Test coordinator refreshes Jensen PIN before stop command execution."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        coordinator._client = MagicMock()
        coordinator._client.is_connected = True
        coordinator._controller = make_controller_mock()
        coordinator._controller.send_pin = AsyncMock()
        coordinator._controller.stop_all = AsyncMock()

        await coordinator.async_stop_command()

        send_pin_idx = coordinator._controller.mock_calls.index(call.send_pin())
        stop_all_idx = coordinator._controller.mock_calls.index(call.stop_all())
        assert send_pin_idx < stop_all_idx

    async def test_async_stop_command_continues_when_auth_refresh_fails(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
    ):
        """Test stop still runs when Jensen auth refresh raises an error."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        coordinator._client = MagicMock()
        coordinator._client.is_connected = True
        coordinator._controller = MagicMock()
        coordinator._controller.send_pin = AsyncMock(side_effect=BleakError("PIN failed"))
        coordinator._controller.stop_all = AsyncMock()

        await coordinator.async_stop_command()

        coordinator._controller.send_pin.assert_awaited_once()
        coordinator._controller.stop_all.assert_awaited_once()

    async def test_async_seek_position_uses_direct_control(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
    ):
        """Seeks go straight to the go-to command after refreshing the PIN."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        coordinator._client = MagicMock()
        coordinator._client.is_connected = True
        coordinator._controller = make_controller_mock()
        coordinator._controller.send_pin = AsyncMock()
        coordinator._controller.supports_direct_position_control = True
        coordinator._controller.angle_to_native_position = MagicMock(return_value=55)
        coordinator._controller.set_motor_position = AsyncMock()

        move = AsyncMock()
        await coordinator.async_seek_position(
            "back", 20.0, lambda c: move(c), lambda c: move(c), lambda c: move(c)
        )

        send_pin_idx = coordinator._controller.mock_calls.index(call.send_pin())
        set_position_idx = coordinator._controller.mock_calls.index(
            call.set_motor_position("back", 55)
        )
        assert send_pin_idx < set_position_idx
        move.assert_not_awaited()


class TestJensenConfig:
    """Config report decoding."""

    async def _query(self, controller: JensenController, config: bytes) -> None:
        controller._coordinator.client.is_connected = True
        task = asyncio.create_task(controller.query_config())
        await asyncio.sleep(0)
        controller._handle_notification(MagicMock(), bytearray(config))
        await task

    async def test_issue_631_config(self):
        """The #631 JMC400 reports head and foot massage on box type 1."""
        controller = make_controller()

        await self._query(controller, bytes.fromhex("0a0503080175"))

        assert controller.has_massage_head and controller.has_massage_foot
        assert not controller.supports_lights
        assert not controller.has_fan
        assert controller._box_type == 1
        assert controller.memory_slot_count == 4
        assert controller.massage_intensity_zones == ["head", "foot", "wave"]
        assert controller.supports_massage_intensity_control

    async def test_config_bytes_are_read_as_hex_text(self):
        """A report byte of 16 means flags 0x16, the way the app reads it."""
        controller = make_controller()

        await self._query(controller, bytes([0x0A, 0x00, 16, 0x00, 0x04, 0x00]))

        assert controller._features == (
            JensenFeatureFlags.MASSAGE_FOOT | JensenFeatureFlags.LIGHT | JensenFeatureFlags.FAN
        )
        assert controller.uses_device_memory
        assert controller.memory_slot_count == 1

    async def test_under_bed_flag_drives_the_single_light(self):
        """The app drives every light kind through the same output."""
        controller = make_controller()

        await self._query(controller, bytes([0x0A, 0x00, 40, 0x00, 0x01, 0x00]))

        assert controller._features == JensenFeatureFlags.LIGHT_UNDERBED
        assert controller.supports_lights
        assert controller.supports_light_level_control
        assert not controller.supports_under_bed_lights

    async def test_full_features_assumed_on_timeout(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry,
        mock_coordinator_connected,
    ):
        """Without a config reply, massage and light stay available."""
        coordinator = AdjustableBedCoordinator(hass, mock_jensen_config_entry)
        await coordinator.async_connect()

        controller = coordinator.controller
        assert controller.supports_lights is True
        assert controller.has_massage is True
        assert controller.has_fan is False
        assert controller.memory_slot_count == 4


class TestJensenPositionParsing:
    """Position reports from the #631 support bundle."""

    def test_reports_are_little_endian_and_calibrated(self):
        """Head rises with its value, foot falls; both map to 0-100 %."""
        controller = make_controller()
        callback = MagicMock()
        controller._notify_callback = callback

        controller._handle_notification(MagicMock(), bytearray.fromhex("10ff1e771575"))

        assert controller._raw_positions == (30494, 29973)
        assert controller._motion_state == 0xFF
        back = callback.call_args_list[0].args
        legs = callback.call_args_list[1].args
        assert back[0] == "back"
        assert back[1] == pytest.approx((30494 - 30000) / 804 * 100)
        assert legs[0] == "legs"
        assert legs[1] == pytest.approx((29973 - 30000) / (29369 - 30000) * 100)

    def test_foot_raising_increases_percentage(self):
        """Bundle frames while the foot rises report a growing legs value."""
        controller = make_controller()
        callback = MagicMock()
        controller._notify_callback = callback

        for frame in ("1010e477fe74", "1010e477e774", "1010e477d274", "1010e477bc74"):
            controller._handle_notification(MagicMock(), bytearray.fromhex(frame))

        legs = [c.args[1] for c in callback.call_args_list if c.args[0] == "legs"]
        assert legs == sorted(legs)
        assert legs[-1] > legs[0]

    @pytest.mark.parametrize(
        ("head", "foot", "back_pct", "legs_pct"),
        [
            (HEAD_POS_FLAT, FOOT_POS_FLAT, 0.0, 0.0),
            (HEAD_POS_MAX, FOOT_POS_MAX, 100.0, 100.0),
            (29000, 31000, 0.0, 0.0),
            (31500, 29000, 100.0, 100.0),
        ],
    )
    def test_calibration_anchors_and_clamping(self, head, foot, back_pct, legs_pct):
        """Anchors map to 0 and 100 %, and values beyond them clamp."""
        controller = make_controller()
        callback = MagicMock()
        controller._notify_callback = callback

        controller._handle_notification(MagicMock(), report(0x00, head, foot))

        assert callback.call_args_list == [call("back", back_pct), call("legs", legs_pct)]

    def test_short_report_is_ignored(self):
        """A truncated 0x10 frame is not treated as a position."""
        controller = make_controller()

        controller._handle_notification(MagicMock(), bytearray([0x10, 0x00, 0x30]))

        assert controller._raw_positions is None

    def test_notification_signals_waiter_before_callback(self):
        """A callback failure must not hide a received position response."""
        controller = make_controller()
        controller._position_received = asyncio.Event()
        controller._notify_callback = MagicMock(side_effect=RuntimeError("callback failed"))

        with pytest.raises(RuntimeError, match="callback failed"):
            controller._handle_notification(MagicMock(), report(0xFF, 30000, 30000))

        assert controller._position_received.is_set()

    async def test_read_positions_waits_for_notification_response(self):
        """The query is incomplete until its asynchronous position frame arrives."""
        controller = make_controller()
        controller._coordinator.client.is_connected = True
        controller._notify_callback = MagicMock()

        read_task = asyncio.create_task(controller.read_positions())
        await asyncio.sleep(0)

        assert written(controller) == [JensenCommands.READ_POSITION]
        assert not read_task.done()

        controller._handle_notification(MagicMock(), report(0xFF, 30000, 30000))
        await read_task

        assert controller._position_received is None
        assert controller._notify_callback.call_count == 2

    async def test_read_positions_serializes_overlapping_queries(self):
        """Each overlapping reader must wait for its own position response."""
        controller = make_controller()
        controller._send_position_query = AsyncMock(return_value=True)

        first_read = asyncio.create_task(controller.read_positions())
        await asyncio.sleep(0)
        second_read = asyncio.create_task(controller.read_positions())
        await asyncio.sleep(0)

        controller._send_position_query.assert_awaited_once()
        controller._handle_notification(MagicMock(), report(0xFF, 30000, 30000))
        await first_read
        await asyncio.sleep(0)

        assert controller._send_position_query.await_count == 2
        assert not second_read.done()

        controller._handle_notification(MagicMock(), report(0xFF, 30000, 30000))
        await second_read

    async def test_read_positions_times_out_without_notification_response(
        self,
        _shorten_mocked_config_timeout: None,
    ):
        """A missing response must not block serialized controller operations."""
        controller = make_controller()
        controller._coordinator.client.is_connected = True

        with pytest.raises(TimeoutError):
            await controller.read_positions()

        assert controller._position_received is None

    async def test_read_positions_raises_when_query_fails(self):
        """A failed query must not look like a successful position refresh."""
        controller = make_controller()
        controller._send_position_query = AsyncMock(return_value=False)

        with pytest.raises(ConnectionError, match="Failed to send Jensen position query"):
            await controller.read_positions()

    async def test_send_position_query_handles_disconnect_during_write(self):
        """A disconnect race follows the explicit failed-query path."""
        controller = make_controller()
        controller._coordinator.client.is_connected = True
        controller._write_gatt_with_retry = AsyncMock(side_effect=ConnectionError("gone"))

        assert await controller._send_position_query() is False


class TestJensenHeldMovement:
    """Held controls repeat their frame and always release with STOP."""

    @pytest.mark.parametrize(
        ("method", "frame"),
        [
            ("move_head_up", JensenCommands.MOTOR_HEAD_UP),
            ("move_back_down", JensenCommands.MOTOR_HEAD_DOWN),
            ("move_legs_up", JensenCommands.MOTOR_FOOT_UP),
            ("move_feet_down", JensenCommands.MOTOR_FOOT_DOWN),
        ],
    )
    async def test_held_move_ends_with_stop(self, method: str, frame: bytes):
        """The motion frame repeats, then STOP follows."""
        controller = make_controller()
        controller.motor_pulse_settings = MagicMock(return_value=(4, 300))

        await getattr(controller, method)()

        assert written(controller) == [frame, JensenCommands.MOTOR_STOP]
        motion_write = controller._write_gatt_with_retry.await_args_list[0]
        assert motion_write.kwargs["repeat_count"] == 4
        assert motion_write.kwargs["repeat_delay_ms"] == 300

    async def test_stop_sent_when_held_move_fails(self):
        """A failed motion write still releases the motor."""
        controller = make_controller()
        controller._write_gatt_with_retry.side_effect = [BleakError("drop"), None]

        with pytest.raises(BleakError):
            await controller.move_head_up()

        assert written(controller)[-1] == JensenCommands.MOTOR_STOP

    @pytest.mark.parametrize(
        ("first", "second", "frame"),
        [
            (("back", True), ("legs", True), "101100000000"),
            (("legs", False), ("back", True), "102100000000"),
            (("back", False), ("legs", True), "101200000000"),
            (("back", False), ("legs", False), "102200000000"),
        ],
    )
    async def test_simultaneous_movement(self, first, second, frame):
        """Back and legs combine into one motion frame for the requested time."""
        controller = make_controller()
        controller.motor_pulse_settings = MagicMock(return_value=(4, 300))

        await controller.move_simultaneously(*first, *second, duration_ms=900)

        assert [f.hex() for f in written(controller)] == [frame, "100000000000"]
        assert controller._write_gatt_with_retry.await_args_list[0].kwargs["repeat_count"] == 4

    async def test_simultaneous_movement_rejects_other_axes(self):
        """Only back and legs can be combined."""
        controller = make_controller()

        assert controller.simultaneous_movement_axes == ("back", "legs")
        with pytest.raises(ValueError, match="back and legs"):
            await controller.move_simultaneously("back", True, "head", True)


@pytest.mark.usefixtures("_fast_movement_monitor")
class TestJensenMovementMonitoring:
    """Autonomous moves hold the command until reports show they finished."""

    async def _run(self, controller: JensenController, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        await asyncio.sleep(0)
        return task

    async def test_flat_waits_through_reports_until_idle(self):
        """Ack first, initial value held, then intermediate and final reports."""
        controller = make_controller()
        controller._coordinator.client.is_connected = True
        callback = MagicMock()
        controller._notify_callback = callback
        controller._raw_positions = (30600, 29500)

        task = await self._run(controller, controller.preset_flat())
        assert written(controller)[0] == JensenCommands.PRESET_FLAT
        assert not task.done()

        # The first report may just restate the start; it does not end the move.
        controller._handle_notification(MagicMock(), report(0x00, 30600, 29500))
        await asyncio.sleep(0.02)
        assert not task.done()

        for head, foot in ((30400, 29700), (30100, 29950)):
            controller._handle_notification(MagicMock(), report(0x81, head, foot))
            await asyncio.sleep(0.01)
            assert not task.done()

        controller._handle_notification(MagicMock(), report(0x00, 30000, 30000))
        await asyncio.sleep(0.01)
        assert not task.done()  # a changed position still counts as movement
        controller._handle_notification(MagicMock(), report(0x00, 30000, 30000))
        await asyncio.sleep(0.01)

        # The settled move ends with a measured read.
        assert written(controller)[-1] == JensenCommands.READ_POSITION
        controller._handle_notification(MagicMock(), report(0xFF, 30000, 30000))
        await task

        assert JensenCommands.MOTOR_STOP not in written(controller)
        legs = [c.args[1] for c in callback.call_args_list if c.args[0] == "legs"]
        assert legs[0] > legs[-1] == 0.0

    async def test_move_ends_when_reports_stop(self, monkeypatch: pytest.MonkeyPatch):
        """Silence after movement means the bed stopped or dropped the link."""
        monkeypatch.setattr(f"{JENSEN_MODULE}._POSITION_RESPONSE_TIMEOUT", 5.0)
        controller = make_controller()
        controller._coordinator.client.is_connected = True
        controller._raw_positions = (30000, 30000)

        task = await self._run(controller, controller.set_motor_position("back", 12))
        controller._handle_notification(MagicMock(), report(0x00, 30100, 30000))
        await asyncio.sleep(0.2)

        assert written(controller)[-1] == JensenCommands.READ_POSITION
        assert not task.done()
        controller._handle_notification(MagicMock(), report(0xFF, 30100, 30000))
        await task

    async def test_no_movement_reported_ends_after_start_window(self):
        """A bed already at the target sends nothing; the command still finishes."""
        controller = make_controller()
        controller._send_position_query = AsyncMock(return_value=False)

        await controller.preset_flat()

        assert written(controller)[0] == JensenCommands.PRESET_FLAT

    async def test_cancel_sends_stop_and_propagates(self):
        """A stop or replacement request ends the move with STOP."""
        controller = make_controller()
        controller._raw_positions = (30500, 30000)

        task = await self._run(controller, controller.preset_flat())
        controller._handle_notification(MagicMock(), report(0x81, 30400, 30000))
        await asyncio.sleep(0)
        controller._coordinator.cancel_command.set()

        with pytest.raises(asyncio.CancelledError):
            await task
        assert written(controller)[-1] == JensenCommands.MOTOR_STOP

    async def test_task_cancellation_sends_stop(self):
        """Task cancellation (reload, shutdown) still releases the motors."""
        controller = make_controller()

        task = await self._run(controller, controller.preset_flat())
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task
        assert written(controller)[-1] == JensenCommands.MOTOR_STOP

    async def test_bounded_timeout_releases_command(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ):
        """Endless movement reports cannot hold the command forever."""
        monkeypatch.setattr(f"{JENSEN_MODULE}._MOVEMENT_FEEDBACK_TIMEOUT_SECONDS", 0.1)
        controller = make_controller()

        async def keep_moving() -> None:
            head = 30000
            while True:
                head += 10
                controller._handle_notification(MagicMock(), report(0x81, head, 30000))
                await asyncio.sleep(0.01)

        mover = asyncio.create_task(keep_moving())
        try:
            await controller.preset_flat()
        finally:
            mover.cancel()

        assert "still reported movement" in caplog.text
        assert JensenCommands.MOTOR_STOP not in written(controller)

    async def test_disabled_angle_sensing_skips_monitoring(self):
        """With feedback disabled the frame is sent and the command returns."""
        controller = make_controller()
        controller._coordinator.disable_angle_sensing = True

        await controller.preset_flat()

        assert set(written(controller)) == {JensenCommands.PRESET_FLAT}


class TestJensenDirectPosition:
    """Go-to targets keep the other section where it is."""

    @pytest.mark.usefixtures("_fast_movement_monitor")
    async def test_target_preserves_other_axis(self):
        """Moving the back sends the measured foot back unchanged."""
        controller = make_controller()
        controller._coordinator.disable_angle_sensing = True
        controller._raw_positions = (30000, 29700)

        await controller.set_motor_position("back", 50)

        assert written(controller) == [JensenCommands.goto_position(30402, 29700)]

    @pytest.mark.usefixtures("_fast_movement_monitor")
    async def test_legs_target_uses_falling_scale(self):
        """Raising the legs lowers the raw foot value."""
        controller = make_controller()
        controller._coordinator.disable_angle_sensing = True
        controller._raw_positions = (30300, 30000)

        await controller.set_motor_position("legs", 100)

        assert written(controller) == [JensenCommands.goto_position(30300, FOOT_POS_MAX)]

    async def test_unknown_position_is_read_first(self):
        """Without a report, the current position is queried before moving."""
        controller = make_controller()
        controller._coordinator.disable_angle_sensing = True
        controller._coordinator.client.is_connected = True

        task = asyncio.create_task(controller.set_motor_position("legs", 0))
        await asyncio.sleep(0)
        assert written(controller) == [JensenCommands.READ_POSITION]
        controller._handle_notification(MagicMock(), report(0xFF, 30500, 29600))
        await task

        assert written(controller)[-1] == JensenCommands.goto_position(30500, FOOT_POS_FLAT)

    async def test_unknown_motor_is_rejected(self):
        """Only back/head and legs/feet exist."""
        controller = make_controller()

        with pytest.raises(ValueError, match="Unknown Jensen motor"):
            await controller.set_motor_position("tilt", 10)


class TestJensenMemory:
    """Device memory on box type 4, app-stored positions otherwise."""

    async def test_device_memory_slot(self):
        """Box type 4 saves and recalls its single device slot."""
        controller = make_controller()
        controller._coordinator.disable_angle_sensing = True
        controller._box_type = 4

        await controller.program_memory(1)
        await controller.preset_memory(1)

        assert written(controller) == [
            JensenCommands.PRESET_MEMORY_SAVE,
            JensenCommands.PRESET_MEMORY_RECALL,
        ]
        with pytest.raises(ValueError, match="one memory slot"):
            await controller.preset_memory(2)

    async def test_app_memory_is_saved_and_recalled(self, hass: HomeAssistant):
        """Other boxes store the measured position and replay it as a go-to."""
        controller = make_controller(hass)
        controller._coordinator.disable_angle_sensing = True
        controller._coordinator.client.is_connected = True
        controller._box_type = 1

        task = asyncio.create_task(controller.program_memory(3))
        await asyncio.sleep(0)
        assert written(controller) == [JensenCommands.READ_POSITION]
        controller._handle_notification(MagicMock(), report(0xFF, 30771, 30000))
        await task

        # A new connection's controller loads the saved slot.
        reloaded = make_controller(hass)
        reloaded._coordinator.disable_angle_sensing = True
        reloaded._box_type = 1
        await reloaded.async_discover_capabilities()
        await reloaded.preset_memory(3)

        assert written(reloaded) == [bytes.fromhex("100433783075")]

    async def test_unsaved_app_memory_is_rejected(self, hass: HomeAssistant):
        """Recalling an empty slot says so instead of moving."""
        controller = make_controller(hass)
        await controller.async_discover_capabilities()

        with pytest.raises(ValueError, match="has not been saved"):
            await controller.preset_memory(2)
        assert written(controller) == []

    async def test_app_memory_slot_range(self):
        """App-stored memory has four slots."""
        controller = make_controller()

        with pytest.raises(ValueError, match="slots are 1-4"):
            await controller.program_memory(5)


class TestJensenLightsAndFan:
    """Light and fan levels."""

    async def test_light_levels(self):
        """Level frames, on at the last level, and off."""
        controller = make_controller()
        controller._features = JensenFeatureFlags.LIGHT

        await controller.lights_on()
        await controller.set_light_level(4)
        await controller.lights_toggle()
        await controller.lights_toggle()

        assert [f.hex() for f in written(controller)] == [
            "13020a000000",
            "130204000000",
            "130200000032",
            "130204000000",
        ]
        controller._coordinator.handle_controller_state_updates.assert_called_with(
            {"light_level": 4}
        )
        assert controller.get_light_state() == {"is_on": True, "light_level": 4}

    async def test_lights_require_feature(self):
        """Beds without a light raise instead of writing."""
        controller = make_controller()

        with pytest.raises(NotImplementedError):
            await controller.lights_on()
        assert not controller.supports_light_level_control

    async def test_fan_levels(self):
        """Fan level frames, with 0 turning it off."""
        controller = make_controller()
        controller._features = JensenFeatureFlags.FAN

        assert controller.supports_fan_level_control
        assert controller.fan_level_max == 10
        await controller.set_fan_level(12)
        await controller.set_fan_level(0)

        assert [f.hex() for f in written(controller)] == ["140a00000050", "140000000050"]

    async def test_fan_requires_feature(self):
        """Beds without a fan raise instead of writing."""
        controller = make_controller()

        assert not controller.supports_fan_level_control
        with pytest.raises(NotImplementedError):
            await controller.set_fan_level(3)


class TestJensenMassage:
    """Massage frames carry all three levels."""

    async def test_zone_levels_keep_the_other_zones(self):
        """Each change resends head, foot and wave together."""
        controller = make_controller()
        controller._features = JensenFeatureFlags.MASSAGE_HEAD | JensenFeatureFlags.MASSAGE_FOOT

        await controller.set_massage_intensity("head", 6)
        await controller.set_massage_intensity("wave", 10)
        await controller.set_massage_intensity("foot", 3)
        await controller.set_massage_intensity("head", 0)

        assert [f.hex() for f in written(controller)] == [
            "120600000000",
            "1206000a0000",
            "1206030a0000",
            "1200030a0000",
        ]
        assert controller.get_massage_state()["wave_intensity"] == 10

    async def test_toggles(self):
        """Toggles switch a zone between level 5 and off."""
        controller = make_controller()
        controller._features = JensenFeatureFlags.MASSAGE_HEAD | JensenFeatureFlags.MASSAGE_FOOT

        await controller.massage_head_toggle()
        await controller.massage_foot_toggle()
        await controller.massage_toggle()
        await controller.massage_toggle()

        assert [f.hex() for f in written(controller)] == [
            "120500000000",
            "120505000000",
            "120000000000",
            "120505000000",
        ]

    async def test_massage_requires_feature(self):
        """Beds without massage raise instead of writing."""
        controller = make_controller()

        with pytest.raises(NotImplementedError):
            await controller.massage_toggle()
        with pytest.raises(ValueError, match="Unknown Jensen massage zone"):
            await controller.set_massage_intensity("lumbar", 1)


class TestJensenEntities:
    """Entities follow the config report."""

    async def test_config_driven_entities(
        self,
        hass: HomeAssistant,
        mock_jensen_config_entry_data: dict,
        mock_coordinator_connected,
        mock_bleak_client: MagicMock,
        enable_custom_integrations,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Fan, light, massage and four app-stored memory slots are exposed."""
        del mock_coordinator_connected, enable_custom_integrations

        async def reported_config(self: JensenController) -> None:
            self._features = (
                JensenFeatureFlags.FAN
                | JensenFeatureFlags.LIGHT
                | JensenFeatureFlags.MASSAGE_HEAD
            )
            self._box_type = 1
            self._config_loaded = True

        monkeypatch.setattr(JensenController, "query_config", reported_config)
        mock_jensen_config_entry_data[CONF_HAS_MASSAGE] = True
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Jensen Test Bed",
            data=mock_jensen_config_entry_data,
            unique_id="AA:BB:CC:DD:EE:FF",
            entry_id="jensen_entities_entry",
        )
        entry.add_to_hass(hass)
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(hass)

        def entity_id(domain: str, key: str) -> str | None:
            return registry.async_get_entity_id(domain, DOMAIN, f"AA:BB:CC:DD:EE:FF_{key}")

        for key in ("fan_level", "light_level", "massage_head_intensity", "massage_wave_intensity"):
            assert entity_id("number", key) is not None, key
        assert entity_id("number", "massage_foot_intensity") is None
        assert entity_id("button", "preset_memory_4") is not None
        assert entity_id("button", "program_memory_4") is not None
        assert entity_id("button", "preset_memory_5") is None

        fan = entity_id("number", "fan_level")
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            "number", "set_value", {"entity_id": fan, "value": 5}, blocking=True
        )
        await hass.async_block_till_done()

        frames = [c.args[1] for c in mock_bleak_client.write_gatt_char.call_args_list]
        assert JensenCommands.fan(5) in frames
        state = hass.states.get(fan)
        assert state is not None and float(state.state) == 5
