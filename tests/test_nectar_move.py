"""Artifact-vector regression tests for the Nectar Move CST app profile."""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.actuator_groups import ACTUATOR_GROUPS
from custom_components.adjustable_bed.beds.okin_cst import OkinCstController
from custom_components.adjustable_bed.binary_sensor import AdjustableBedControllerStateBinarySensor
from custom_components.adjustable_bed.button import BUTTON_DESCRIPTIONS, _should_add_button
from custom_components.adjustable_bed.codec.okin_nframe import frame96
from custom_components.adjustable_bed.config_flow import _apply_bed_type_choice
from custom_components.adjustable_bed.const import (
    BED_TYPE_OKIN_CST,
    BEDS_WITH_POSITION_FEEDBACK,
    BEDS_WITHOUT_ANGLE_FEEDBACK,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    OKIMAT_WRITE_CHAR_UUID,
    OKIN_CST_VARIANT_MF900,
    OKIN_CST_VARIANT_NECTAR_MOVE,
    VARIANT_AUTO,
    requires_pairing,
    supports_runtime_authentication_recovery,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.detection import (
    bed_type_choice,
    detect_bed_type_detailed,
    get_bed_type_options,
    resolve_bed_type_choice,
)

# A short configured pulse count keeps bounded movements quick in tests; the
# long one keeps a movement running until the test cancels it.
_PULSE_COUNT = 3
_LONG_PULSE_COUNT = 100


class _WireLog:
    """Record real-time GATT writes while keeping the mock client's behavior."""

    def __init__(self, client: MagicMock) -> None:
        self.frames: list[bytes] = []
        self.times: list[float] = []
        client.write_gatt_char.reset_mock()
        original = client.write_gatt_char.side_effect

        async def record(char_uuid: str, data: bytes, response: bool = False) -> None:
            self.frames.append(bytes(data))
            self.times.append(asyncio.get_running_loop().time())
            await original(char_uuid, data, response=response)

        client.write_gatt_char.side_effect = record

    def gaps(self) -> list[float]:
        return [later - earlier for earlier, later in itertools.pairwise(self.times)]

    async def wait_for(self, count: int) -> None:
        async with asyncio.timeout(5):
            while len(self.frames) < count:
                await asyncio.sleep(0.005)


@pytest.fixture
async def nectar_move_coordinator(
    hass: HomeAssistant,
    mock_coordinator_connected: None,
) -> AsyncIterator[AdjustableBedCoordinator]:
    """Connect a real coordinator with the explicit Nectar Move profile."""
    del mock_coordinator_connected
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nectar Move",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "OKIN-Receiver",
            CONF_BED_TYPE: BED_TYPE_OKIN_CST,
            CONF_PROTOCOL_VARIANT: OKIN_CST_VARIANT_NECTAR_MOVE,
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_MOTOR_PULSE_COUNT: _PULSE_COUNT,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id="AA:BB:CC:DD:EE:FF",
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    assert await coordinator.async_connect()
    assert isinstance(coordinator.controller, OkinCstController)
    yield coordinator
    await coordinator.async_disconnect(reason="test_cleanup")


def _controller(coordinator: AdjustableBedCoordinator) -> OkinCstController:
    controller = coordinator.controller
    assert isinstance(controller, OkinCstController)
    return controller


def _writes(client: MagicMock) -> list[bytes]:
    return [record.args[1] for record in client.write_gatt_char.call_args_list]


def _expected_tap(value: int, secondary: int = 0) -> list[bytes]:
    return [frame96(value, secondary), frame96(0), frame96(0)]


def test_nectar_move_is_an_explicit_bed_choice(
    mock_bluetooth_service_info_ambiguous_okin: MagicMock,
) -> None:
    choice = bed_type_choice(BED_TYPE_OKIN_CST, OKIN_CST_VARIANT_NECTAR_MOVE)
    choices = {option["value"] for option in get_bed_type_options()}
    group_choices = ACTUATOR_GROUPS["okin"]["variants"]
    assert group_choices is not None

    assert choice in choices
    assert resolve_bed_type_choice(choice) == (BED_TYPE_OKIN_CST, OKIN_CST_VARIANT_NECTAR_MOVE)
    assert any(
        item.get("variant") == OKIN_CST_VARIANT_NECTAR_MOVE and item["label"] == "Nectar Move app"
        for item in group_choices
    )
    assert bed_type_choice(BED_TYPE_OKIN_CST, VARIANT_AUTO) == BED_TYPE_OKIN_CST
    auto_detect = detect_bed_type_detailed(mock_bluetooth_service_info_ambiguous_okin)
    assert BED_TYPE_OKIN_CST in auto_detect.ambiguous_types
    assert bed_type_choice(auto_detect.bed_type, VARIANT_AUTO) != choice

    # Bluetooth confirm, manual config, manual entry, and options all resolve
    # app selector values through this shared helper.
    selected = {CONF_BED_TYPE: choice}
    _apply_bed_type_choice(selected, BED_TYPE_OKIN_CST)
    assert selected == {
        CONF_BED_TYPE: BED_TYPE_OKIN_CST,
        CONF_PROTOCOL_VARIANT: OKIN_CST_VARIANT_NECTAR_MOVE,
    }

    unchanged = {
        CONF_BED_TYPE: choice,
        CONF_PROTOCOL_VARIANT: OKIN_CST_VARIANT_NECTAR_MOVE,
    }
    _apply_bed_type_choice(unchanged, choice)
    assert unchanged[CONF_PROTOCOL_VARIANT] == OKIN_CST_VARIANT_NECTAR_MOVE


async def test_factory_profile_is_two_axes_without_position_feedback(
    hass: HomeAssistant,
    nectar_move_coordinator: AdjustableBedCoordinator,
) -> None:
    controller = await create_controller(
        nectar_move_coordinator,
        BED_TYPE_OKIN_CST,
        OKIN_CST_VARIANT_NECTAR_MOVE,
        None,
        None,
    )

    assert isinstance(controller, OkinCstController)
    assert tuple(spec.key for spec in controller.motor_control_specs) == ("head", "feet")
    assert controller.supports_position_feedback is False
    assert BED_TYPE_OKIN_CST not in BEDS_WITH_POSITION_FEEDBACK
    assert BED_TYPE_OKIN_CST in BEDS_WITHOUT_ANGLE_FEEDBACK


def test_profile_exposes_only_reachable_controls(
    nectar_move_coordinator: AdjustableBedCoordinator,
) -> None:
    controller = _controller(nectar_move_coordinator)
    button_keys = {
        desc.key
        for desc in BUTTON_DESCRIPTIONS
        if _should_add_button(desc, controller, controller.auto_enable_massage)
    }

    assert controller.supports_preset_lounge is False
    assert controller.supports_preset_reading is True
    assert controller.memory_slot_names == ("Zero Gravity", "Reading")
    assert controller.memory_slot_count == 2
    assert controller.requires_notification_channel is True
    assert controller.supports_light_toggle_control is True
    assert controller.supports_discrete_light_control is False
    assert controller.supports_massage is True
    assert controller.auto_enable_massage is True
    assert controller.supports_massage_intensity_up_control is True
    assert controller.supports_massage_intensity_step_control is False
    assert controller.supports_massage_off_control is False
    assert controller.supports_massage_toggle_control is False
    assert controller.supports_massage_mode_step_control is False
    assert controller.supports_massage_wave_direction_control is False
    assert "preset_reading" in button_keys
    assert "preset_lounge" not in button_keys
    assert "preset_incline" not in button_keys
    assert "preset_memory_3" not in button_keys
    assert "program_memory_3" not in button_keys
    assert "toggle_light" in button_keys
    assert "massage_all_up" in button_keys
    assert not button_keys.intersection(
        {"massage_all_down", "massage_all_off", "massage_all_toggle", "massage_mode_step"}
    )
    assert controller.controller_state_binary_sensor_specs[0].key == (
        "memory_save_response_observed"
    )
    assert nectar_move_coordinator.controller_state["memory_save_response_observed"] is False


def test_memory_save_response_is_a_typed_read_only_binary_sensor(
    nectar_move_coordinator: AdjustableBedCoordinator,
) -> None:
    controller = _controller(nectar_move_coordinator)
    spec = controller.controller_state_binary_sensor_specs[0]
    sensor = AdjustableBedControllerStateBinarySensor(nectar_move_coordinator, spec)

    assert spec.translation_key == "memory_save_response_observed"
    assert sensor.translation_key == "memory_save_response_observed"
    assert sensor.is_on is False
    nectar_move_coordinator.handle_controller_state_update(spec.state_key, True)
    assert sensor.is_on is True
    assert sensor.extra_state_attributes == {}


@pytest.mark.parametrize(
    ("method_name", "value"),
    [
        ("move_head_up", 0x00000001),
        ("move_head_down", 0x00000002),
        ("move_feet_up", 0x00000004),
        ("move_feet_down", 0x00000008),
    ],
)
async def test_held_motor_vectors_refresh_then_release(
    nectar_move_coordinator: AdjustableBedCoordinator,
    mock_bleak_client: MagicMock,
    method_name: str,
    value: int,
) -> None:
    """One HA movement refreshes the axis for the pulse count, then releases."""
    controller = _controller(nectar_move_coordinator)
    wire = _WireLog(mock_bleak_client)

    await getattr(controller, method_name)()

    assert wire.frames == [frame96(value)] * _PULSE_COUNT + [frame96(0)] * 2
    # Refreshes and both release frames are 100 ms apart, per the app.
    assert all(gap >= 0.09 for gap in wire.gaps())
    assert all(
        record.args[0] == OKIMAT_WRITE_CHAR_UUID and record.kwargs["response"] is True
        for record in mock_bleak_client.write_gatt_char.call_args_list
    )


async def test_cover_open_returns_after_bounded_movement(
    nectar_move_coordinator: AdjustableBedCoordinator,
    mock_bleak_client: MagicMock,
) -> None:
    """cover.open_cover finishes on its own instead of driving to the end stop."""
    coordinator = nectar_move_coordinator
    controller = _controller(coordinator)
    wire = _WireLog(mock_bleak_client)
    spec = next(spec for spec in controller.motor_control_specs if spec.key == "head")
    cover = AdjustableBedCover(coordinator, _build_cover_description(spec))
    cover.async_write_ha_state = MagicMock()

    async with asyncio.timeout(5):
        await cover.async_open_cover()

    assert wire.frames == [frame96(0x00000001)] * _PULSE_COUNT + [
        frame96(0)
    ] * 2


async def test_held_cleanup_uses_one_fresh_uncancellable_stop_event(
    nectar_move_coordinator: AdjustableBedCoordinator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _controller(nectar_move_coordinator)
    writes: list[tuple[bytes, int, int, asyncio.Event | None]] = []

    async def record_write(
        payload: bytes,
        *,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        writes.append((payload, repeat_count, repeat_delay_ms, cancel_event))

    monkeypatch.setattr(controller, "write_command", record_write)
    await controller.move_head_up()

    assert [write[:3] for write in writes] == [
        (frame96(0x00000001), _PULSE_COUNT, 100),
        (frame96(0), 1, 100),
        (frame96(0), 1, 100),
    ]
    # The movement observes the coordinator's cancellation; the release cannot.
    assert writes[0][3] is None
    stop_event = writes[1][3]
    assert isinstance(stop_event, asyncio.Event)
    assert stop_event is not nectar_move_coordinator.cancel_command
    assert writes[2][3] is stop_event


async def test_held_write_error_still_releases_with_fresh_stop_event(
    nectar_move_coordinator: AdjustableBedCoordinator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _controller(nectar_move_coordinator)
    writes: list[tuple[bytes, asyncio.Event | None]] = []

    async def record_write(
        payload: bytes,
        *,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        del repeat_count, repeat_delay_ms
        writes.append((payload, cancel_event))
        if payload != frame96(0):
            raise BleakError("movement write failed")

    monkeypatch.setattr(controller, "write_command", record_write)
    with pytest.raises(BleakError, match="movement write failed"):
        await controller.move_head_up()

    assert [payload for payload, _event in writes] == [
        frame96(0x00000001),
        frame96(0),
        frame96(0),
    ]
    assert isinstance(writes[1][1], asyncio.Event)
    assert writes[1][1] is writes[2][1]


@pytest.mark.parametrize(
    ("action", "value"),
    [
        ("preset_flat", 0x08000000),
        ("preset_anti_snore", 0x00008000),
        ("preset_zero_g", 0x00001000),
        ("preset_reading", 0x00002000),
        ("program_zero_g", 0x08001000),
        ("program_reading", 0x08002000),
        ("lights_toggle", 0x00020000),
        ("massage_intensity_up", 0x00000C00),
    ],
)
async def test_stateless_actions_use_one_artifact_frame_and_bounded_stop_pair(
    nectar_move_coordinator: AdjustableBedCoordinator,
    mock_bleak_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    value: int,
) -> None:
    controller = _controller(nectar_move_coordinator)
    client = mock_bleak_client
    client.write_gatt_char.reset_mock()
    sleeps: list[float] = []

    async def controlled_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep", controlled_sleep
    )
    if action == "program_zero_g":
        await controller.program_memory(1)
    elif action == "program_reading":
        await controller.program_memory(2)
    else:
        await getattr(controller, action)()

    assert _writes(client) == _expected_tap(value)
    assert sleeps == [0.1, 0.1]
    assert all(
        record.kwargs["response"] is True for record in client.write_gatt_char.call_args_list
    )


async def test_save_status_vectors_are_signed_pending_and_session_local(
    nectar_move_coordinator: AdjustableBedCoordinator,
    mock_bleak_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _controller(nectar_move_coordinator)
    monkeypatch.setattr("custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep", AsyncMock())

    await controller.program_memory(1)
    assert controller._pending_memory_save_code == 3
    signed_negative = bytearray(11)
    signed_negative[10] = 0xFF
    controller._handle_notification(MagicMock(), signed_negative)
    assert controller._previous_status == -1
    assert controller._pending_memory_save_code is None
    assert nectar_move_coordinator.controller_state["memory_save_response_observed"] is True

    await controller.program_memory(2)
    assert controller._pending_memory_save_code == 5
    assert nectar_move_coordinator.controller_state["memory_save_response_observed"] is False
    controller._handle_notification(MagicMock(), signed_negative)
    assert controller._pending_memory_save_code == 5  # duplicate status is not a response

    short = bytearray(10)
    short[9] = 1
    controller._handle_notification(MagicMock(), short)
    assert controller._pending_memory_save_code == 5

    callback = controller._memory_save_response_callback
    controller._memory_save_response_callback = None
    changed_without_callback = bytearray(11)
    changed_without_callback[10] = 1
    controller._handle_notification(MagicMock(), changed_without_callback)
    assert controller._previous_status == 1
    assert controller._pending_memory_save_code == 5
    assert nectar_move_coordinator.controller_state["memory_save_response_observed"] is False
    controller._memory_save_response_callback = callback

    isolated = OkinCstController(MagicMock(), variant=OKIN_CST_VARIANT_NECTAR_MOVE)
    isolated._handle_notification(MagicMock(), bytearray([0] * 10 + [2]))
    assert isolated._pending_memory_save_code is None
    assert controller._pending_memory_save_code == 5

    changed = bytearray(11)
    changed[10] = 2
    controller._handle_notification(MagicMock(), changed)
    assert controller._pending_memory_save_code is None
    assert nectar_move_coordinator.controller_state["memory_save_response_observed"] is True

    await controller.program_memory(1)
    assert controller._memory_save_response_callback is not None
    controller.on_disconnect()
    assert controller._pending_memory_save_code is None
    assert controller._previous_status == 0
    assert controller._memory_save_response_callback is None
    assert nectar_move_coordinator.controller_state["memory_save_response_observed"] is False


async def test_recall_clears_pending_memory_save_response_tracking(
    nectar_move_coordinator: AdjustableBedCoordinator,
    mock_bleak_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _controller(nectar_move_coordinator)
    mock_bleak_client.write_gatt_char.reset_mock()
    monkeypatch.setattr("custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep", AsyncMock())

    await controller.program_memory(1)
    assert controller._pending_memory_save_code == 3
    await controller.preset_reading()

    assert controller._pending_memory_save_code is None
    changed_status = bytearray(11)
    changed_status[10] = 1
    controller._handle_notification(MagicMock(), changed_status)
    assert nectar_move_coordinator.controller_state["memory_save_response_observed"] is False
    assert _writes(mock_bleak_client) == _expected_tap(0x08001000) + _expected_tap(0x00002000)


@pytest.mark.parametrize("failure", [BleakError("write failed"), asyncio.CancelledError()])
async def test_save_error_or_cancellation_clears_pending_feedback(
    nectar_move_coordinator: AdjustableBedCoordinator,
    monkeypatch: pytest.MonkeyPatch,
    failure: BaseException,
) -> None:
    controller = _controller(nectar_move_coordinator)
    monkeypatch.setattr(controller, "_send_button_press", AsyncMock(side_effect=failure))

    with pytest.raises(type(failure)):
        await controller.program_memory(1)

    assert controller._pending_memory_save_code is None
    assert nectar_move_coordinator.controller_state["memory_save_response_observed"] is False


async def test_save_coordinator_cancel_event_clears_pending_feedback(
    nectar_move_coordinator: AdjustableBedCoordinator,
    mock_bleak_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _controller(nectar_move_coordinator)
    mock_bleak_client.write_gatt_char.reset_mock()
    monkeypatch.setattr("custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep", AsyncMock())
    nectar_move_coordinator.cancel_command.set()

    await controller.program_memory(1)

    assert _writes(mock_bleak_client) == [frame96(0), frame96(0)]
    assert controller._pending_memory_save_code is None
    assert nectar_move_coordinator.controller_state["memory_save_response_observed"] is False


async def test_required_nectar_notification_failure_fails_setup_and_cleans_link(
    hass: HomeAssistant,
    mock_coordinator_connected: None,
    mock_bleak_client: MagicMock,
) -> None:
    del mock_coordinator_connected
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nectar Move",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "OKIN-Receiver",
            CONF_BED_TYPE: BED_TYPE_OKIN_CST,
            CONF_PROTOCOL_VARIANT: OKIN_CST_VARIANT_NECTAR_MOVE,
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: False,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id="AA:BB:CC:DD:EE:FF",
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    mock_bleak_client.start_notify.side_effect = BleakError("CCCD setup failed")

    assert await coordinator.async_connect() is False
    assert mock_bleak_client.start_notify.await_count >= 1
    assert mock_bleak_client.disconnect.await_count >= 1
    assert coordinator.controller is None
    assert coordinator.client is None


async def test_old_cst_profiles_keep_suppressed_notify_failure_and_pairing_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert requires_pairing(BED_TYPE_OKIN_CST, VARIANT_AUTO) is True
    assert requires_pairing(BED_TYPE_OKIN_CST, OKIN_CST_VARIANT_MF900) is True
    assert supports_runtime_authentication_recovery(BED_TYPE_OKIN_CST, VARIANT_AUTO)
    client = MagicMock(is_connected=True)
    client.start_notify = AsyncMock(side_effect=BleakError("CCCD setup failed"))
    coordinator = MagicMock(client=client)
    old_controller = OkinCstController(coordinator, variant=OKIN_CST_VARIANT_MF900)

    await old_controller.start_notify(None)

    assert old_controller.requires_notification_channel is False
    assert old_controller.protocol_diagnostics["cst_profile"] == OKIN_CST_VARIANT_MF900


async def test_no_proactive_pairing_keeps_runtime_authentication_recovery(
    nectar_move_coordinator: AdjustableBedCoordinator,
) -> None:
    coordinator = nectar_move_coordinator
    required, requested, after_discovery = coordinator._prepare_pairing_attempt(
        MagicMock(), {}, source="local"
    )

    assert (required, requested, after_discovery) == (False, False, False)
    assert requires_pairing(BED_TYPE_OKIN_CST, OKIN_CST_VARIANT_NECTAR_MOVE) is False
    assert (
        supports_runtime_authentication_recovery(BED_TYPE_OKIN_CST, OKIN_CST_VARIANT_NECTAR_MOVE)
        is True
    )

    coordinator._async_raise_pairing_issue = AsyncMock()
    coordinator.async_disconnect = AsyncMock()
    await coordinator._async_handle_ble_authentication_error(
        BleakError("Insufficient authentication")
    )
    coordinator._async_raise_pairing_issue.assert_awaited_once()
    coordinator.async_disconnect.assert_awaited_once_with(reason="authentication_failed")


async def test_auth_gated_notify_startup_pair_repair_pairs_on_reconnect(
    hass: HomeAssistant,
    mock_coordinator_connected: None,
    mock_bleak_client: MagicMock,
    mock_establish_connection: AsyncMock,
    mock_async_ble_device_from_address: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Startup auth failure offers repair, and explicit repair pairs on reconnect."""
    del mock_coordinator_connected, mock_async_ble_device_from_address
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nectar Move",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:F1",
            CONF_NAME: "OKIN-Receiver",
            CONF_BED_TYPE: BED_TYPE_OKIN_CST,
            CONF_PROTOCOL_VARIANT: OKIN_CST_VARIANT_NECTAR_MOVE,
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id="AA:BB:CC:DD:EE:F1",
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._max_retries = 1
    raise_pairing_issue = AsyncMock()
    mock_bleak_client.start_notify.side_effect = [
        BleakError("Insufficient authentication"),
        None,
    ]
    monkeypatch.setattr(coordinator, "_async_raise_pairing_issue", raise_pairing_issue)
    monkeypatch.setattr(coordinator, "_async_verify_bonded", AsyncMock(return_value=True))

    assert await coordinator.async_connect() is False
    assert coordinator.client is None
    assert (
        coordinator.pairing_diagnostics["last_bond_verification"]["status"]
        == "authentication_failed"
    )
    raise_pairing_issue.assert_awaited_once()
    assert mock_establish_connection.await_args_list[0].kwargs["pair"] is False

    assert await coordinator.async_pair_now() is True
    assert mock_establish_connection.await_args_list[1].kwargs["pair"] is True
    assert coordinator._ble_bond_established is True
    assert coordinator._force_pairing_requested is False
    await coordinator.async_disconnect(reason="test_cleanup")


async def test_setup_auth_failure_keeps_pair_now_repair(
    hass: HomeAssistant,
    enable_custom_integrations: None,
    mock_coordinator_connected: None,
    mock_bleak_client: MagicMock,
) -> None:
    """Failed setup must not clear the repair its own auth failure raised."""
    del enable_custom_integrations, mock_coordinator_connected
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nectar Move",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:F2",
            CONF_NAME: "OKIN-Receiver",
            CONF_BED_TYPE: BED_TYPE_OKIN_CST,
            CONF_PROTOCOL_VARIANT: OKIN_CST_VARIANT_NECTAR_MOVE,
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: True,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id="AA:BB:CC:DD:EE:F2",
    )
    entry.add_to_hass(hass)
    mock_bleak_client.start_notify.side_effect = BleakError("Insufficient authentication")

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "pairing_required_aa_bb_cc_dd_ee_f2")
    assert issue is not None
    assert issue.translation_key == "pairing_required"


async def test_successful_retry_retires_startup_auth_failure(
    hass: HomeAssistant,
    mock_coordinator_connected: None,
    mock_bleak_client: MagicMock,
) -> None:
    """A retry whose startup succeeds unpaired resolves the earlier auth failure."""
    del mock_coordinator_connected
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nectar Move",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:F3",
            CONF_NAME: "OKIN-Receiver",
            CONF_BED_TYPE: BED_TYPE_OKIN_CST,
            CONF_PROTOCOL_VARIANT: OKIN_CST_VARIANT_NECTAR_MOVE,
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: True,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
        },
        unique_id="AA:BB:CC:DD:EE:F3",
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._max_retries = 2
    mock_bleak_client.start_notify.side_effect = [
        BleakError("Insufficient authentication"),
        None,
    ]

    assert await coordinator.async_connect() is True
    assert ir.async_get(hass).async_get_issue(DOMAIN, "pairing_required_aa_bb_cc_dd_ee_f3") is None
    await coordinator.async_disconnect(reason="test_cleanup")


async def test_coordinator_serializes_replacement_and_stop_cleanup(
    nectar_move_coordinator: AdjustableBedCoordinator,
    mock_bleak_client: MagicMock,
) -> None:
    """A replacement releases the old axis first; STOP then releases only once."""
    coordinator = nectar_move_coordinator
    coordinator._motor_pulse_count = _LONG_PULSE_COUNT
    wire = _WireLog(mock_bleak_client)

    first = asyncio.create_task(
        coordinator.async_execute_controller_command(
            lambda current: current.move_head_up(),
            read_positions_after_operation=False,
        )
    )
    await wire.wait_for(1)
    replacement = asyncio.create_task(
        coordinator.async_execute_controller_command(
            lambda current: current.move_head_down(),
            read_positions_after_operation=False,
        )
    )
    await wire.wait_for(4)
    await coordinator.async_stop_command()
    async with asyncio.timeout(5):
        await asyncio.gather(first, replacement)

    assert wire.frames == [
        frame96(0x00000001),
        frame96(0),
        frame96(0),
        frame96(0x00000002),
        frame96(0),
        frame96(0),
    ]


async def test_normal_cover_resources_replace_nectar_head_with_feet(
    nectar_move_coordinator: AdjustableBedCoordinator,
    mock_bleak_client: MagicMock,
) -> None:
    """Different normal cover axes share only Nectar's movement cancellation scope."""
    coordinator = nectar_move_coordinator
    coordinator._motor_pulse_count = _LONG_PULSE_COUNT
    controller = _controller(coordinator)
    wire = _WireLog(mock_bleak_client)
    covers = {
        spec.key: AdjustableBedCover(coordinator, _build_cover_description(spec))
        for spec in controller.motor_control_specs
    }
    for cover in covers.values():
        cover.async_write_ha_state = MagicMock()
    head = covers["head"]
    feet = covers["feet"]
    assert head._motor_resource == feet._motor_resource == "motor:*"

    head_task = asyncio.create_task(head.async_open_cover())
    await wire.wait_for(1)
    feet_task = asyncio.create_task(feet.async_open_cover())
    await wire.wait_for(4)

    # Feet was admitted after Head's finally sent both release frames.
    assert wire.frames == [
        frame96(0x00000001),
        frame96(0),
        frame96(0),
        frame96(0x00000004),
    ]
    await coordinator.async_stop_command()
    async with asyncio.timeout(5):
        await asyncio.gather(head_task, feet_task)

    assert wire.frames[4:] == [frame96(0), frame96(0)]


async def test_coordinator_stop_settles_held_refresh_before_explicit_stop(
    nectar_move_coordinator: AdjustableBedCoordinator,
    mock_bleak_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cancelled movement's own release satisfies the STOP that cancelled it."""
    coordinator = nectar_move_coordinator
    coordinator._motor_pulse_count = _LONG_PULSE_COUNT
    controller = _controller(coordinator)
    wire = _WireLog(mock_bleak_client)
    frames_at_stop: list[int] = []
    original_stop_all = controller.stop_all

    async def observe_stop_all() -> None:
        frames_at_stop.append(len(wire.frames))
        await original_stop_all()

    monkeypatch.setattr(controller, "stop_all", observe_stop_all)
    movement = asyncio.create_task(
        coordinator.async_execute_controller_command(
            lambda current: current.move_head_up(),
            cancel_running=False,
            read_positions_after_operation=False,
        )
    )
    await wire.wait_for(1)
    await coordinator.async_stop_command()
    async with asyncio.timeout(5):
        await movement

    # STOP waited for the movement's release frames, then sent no duplicate pair.
    assert frames_at_stop == [3]
    assert wire.frames == [
        frame96(0x00000001),
        frame96(0),
        frame96(0),
    ]


async def test_later_explicit_stop_is_not_suppressed_by_old_cancel_cleanup(
    nectar_move_coordinator: AdjustableBedCoordinator,
    mock_bleak_client: MagicMock,
) -> None:
    coordinator = nectar_move_coordinator
    coordinator._motor_pulse_count = _LONG_PULSE_COUNT
    wire = _WireLog(mock_bleak_client)

    movement = asyncio.create_task(
        coordinator.async_execute_controller_command(
            lambda current: current.move_head_up(),
            read_positions_after_operation=False,
        )
    )
    await wire.wait_for(1)
    coordinator.request_command_cancel()
    async with asyncio.timeout(5):
        await movement
    await coordinator.async_stop_command()

    assert wire.frames == [
        frame96(0x00000001),
        frame96(0),
        frame96(0),
        frame96(0),
        frame96(0),
    ]
