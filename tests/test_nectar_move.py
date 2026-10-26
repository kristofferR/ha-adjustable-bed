"""Artifact-vector regression tests for the Nectar Move CST app profile."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.actuator_groups import ACTUATOR_GROUPS
from custom_components.adjustable_bed.beds.okin_cst import OkinCstController
from custom_components.adjustable_bed.beds.okin_protocol import build_cst_command
from custom_components.adjustable_bed.binary_sensor import AdjustableBedControllerStateBinarySensor
from custom_components.adjustable_bed.button import BUTTON_DESCRIPTIONS, _should_add_button
from custom_components.adjustable_bed.config_flow import _apply_bed_type_choice
from custom_components.adjustable_bed.const import (
    BED_TYPE_OKIN_CST,
    BEDS_WITH_POSITION_FEEDBACK,
    BEDS_WITHOUT_ANGLE_FEEDBACK,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
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
    return [build_cst_command(value, secondary), build_cst_command(), build_cst_command()]


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
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
    value: int,
) -> None:
    controller = _controller(nectar_move_coordinator)
    client = mock_bleak_client
    client.write_gatt_char.reset_mock()
    nectar_move_coordinator.cancel_command.clear()
    refresh_timeouts: list[float] = []
    cleanup_delays: list[float] = []
    original_sleep = asyncio.sleep

    async def cancel_on_first_refresh(awaitable: Awaitable[bool], timeout: float) -> bool:
        assert timeout == pytest.approx(0.1)
        refresh_timeouts.append(timeout)
        if len(refresh_timeouts) == 1:
            nectar_move_coordinator.cancel_command.set()
        return await awaitable

    async def controlled_cleanup_sleep(delay: float) -> None:
        if delay == 0.1:
            cleanup_delays.append(delay)
            return
        await original_sleep(delay)

    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.wait_for",
        cancel_on_first_refresh,
    )
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep",
        controlled_cleanup_sleep,
    )
    await getattr(controller, method_name)()

    assert _writes(client) == _expected_tap(value)[:1] + [build_cst_command()] * 2
    assert refresh_timeouts == [0.1]
    assert cleanup_delays == [0.1, 0.1]
    assert [record.kwargs["response"] for record in client.write_gatt_char.call_args_list] == [
        True,
        True,
        True,
    ]


async def test_held_cleanup_uses_one_fresh_uncancellable_stop_event(
    nectar_move_coordinator: AdjustableBedCoordinator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _controller(nectar_move_coordinator)
    writes: list[tuple[bytes, asyncio.Event | None]] = []
    cleanup_delays: list[float] = []
    nectar_move_coordinator.cancel_command.clear()

    async def record_write(
        payload: bytes,
        *,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        assert repeat_count == 1
        assert repeat_delay_ms == 100
        writes.append((payload, cancel_event))

    async def cancel_after_first_refresh(awaitable: Awaitable[bool], timeout: float) -> bool:
        assert timeout == pytest.approx(0.1)
        if len(writes) == 1:
            nectar_move_coordinator.cancel_command.set()
        return await awaitable

    async def controlled_cleanup_sleep(delay: float) -> None:
        if delay == 0.1:
            cleanup_delays.append(delay)

    monkeypatch.setattr(controller, "write_command", record_write)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep",
        controlled_cleanup_sleep,
    )
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.wait_for",
        cancel_after_first_refresh,
    )
    await controller.move_head_up()

    assert [payload for payload, _event in writes] == [
        build_cst_command(motor_value=0x00000001),
        build_cst_command(),
        build_cst_command(),
    ]
    assert writes[0][1] is nectar_move_coordinator.cancel_command
    stop_event = writes[1][1]
    assert isinstance(stop_event, asyncio.Event)
    assert not stop_event.is_set()
    assert writes[2][1] is stop_event
    assert cleanup_delays == [0.1, 0.1]


async def test_held_write_error_still_releases_with_fresh_stop_event(
    nectar_move_coordinator: AdjustableBedCoordinator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _controller(nectar_move_coordinator)
    writes: list[tuple[bytes, asyncio.Event | None]] = []
    sleep_delays: list[float] = []
    original_sleep = asyncio.sleep

    async def record_write(
        payload: bytes,
        *,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
    ) -> None:
        assert repeat_count == 1
        assert repeat_delay_ms == 100
        writes.append((payload, cancel_event))
        if payload != build_cst_command():
            raise BleakError("movement write failed")

    async def controlled_sleep(delay: float) -> None:
        if delay == 0.1:
            sleep_delays.append(delay)
            return
        await original_sleep(delay)

    monkeypatch.setattr(controller, "write_command", record_write)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep", controlled_sleep
    )
    with pytest.raises(BleakError, match="movement write failed"):
        await controller.move_head_up()

    assert [payload for payload, _event in writes] == [
        build_cst_command(motor_value=0x00000001),
        build_cst_command(),
        build_cst_command(),
    ]
    assert writes[0][1] is nectar_move_coordinator.cancel_command
    assert writes[1][1] is not writes[0][1]
    assert writes[1][1] is writes[2][1]
    assert sleep_delays == [0.1, 0.1]


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

    assert _writes(mock_bleak_client) == [build_cst_command(), build_cst_command()]
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


async def test_coordinator_serializes_replacement_and_stop_cleanup(
    nectar_move_coordinator: AdjustableBedCoordinator,
    mock_bleak_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = nectar_move_coordinator
    client = mock_bleak_client
    client.write_gatt_char.reset_mock()
    refresh_timeouts: list[float] = []
    cleanup_delays: list[float] = []
    first_hold = asyncio.Event()
    second_hold = asyncio.Event()

    async def controlled_wait_for(awaitable: Awaitable[bool], timeout: float) -> bool:
        assert timeout == pytest.approx(0.1)
        refresh_timeouts.append(timeout)
        if len(refresh_timeouts) == 1:
            first_hold.set()
        elif len(refresh_timeouts) == 2:
            second_hold.set()
        return await awaitable

    async def controlled_cleanup_sleep(delay: float) -> None:
        if delay == 0.1:
            cleanup_delays.append(delay)

    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.wait_for", controlled_wait_for
    )
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep",
        controlled_cleanup_sleep,
    )
    first = asyncio.create_task(
        coordinator.async_execute_controller_command(
            lambda current: current.move_head_up(),
            read_positions_after_operation=False,
        )
    )
    await first_hold.wait()
    replacement = asyncio.create_task(
        coordinator.async_execute_controller_command(
            lambda current: current.move_head_down(),
            read_positions_after_operation=False,
        )
    )
    await second_hold.wait()
    await coordinator.async_stop_command()
    await asyncio.gather(first, replacement)

    assert _writes(client) == [
        build_cst_command(motor_value=0x00000001),
        build_cst_command(),
        build_cst_command(),
        build_cst_command(motor_value=0x00000002),
        build_cst_command(),
        build_cst_command(),
    ]
    assert refresh_timeouts == [0.1, 0.1]
    assert cleanup_delays == [0.1] * 4
    assert all(
        record.args[0] == OKIMAT_WRITE_CHAR_UUID for record in client.write_gatt_char.call_args_list
    )
    assert all(
        record.kwargs["response"] is True for record in client.write_gatt_char.call_args_list
    )


async def test_normal_cover_resources_replace_nectar_head_with_feet(
    nectar_move_coordinator: AdjustableBedCoordinator,
    mock_bleak_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Different normal cover axes share only Nectar's movement cancellation scope."""
    coordinator = nectar_move_coordinator
    controller = _controller(coordinator)
    client = mock_bleak_client
    client.write_gatt_char.reset_mock()
    coordinator.cancel_command.clear()
    original_sleep = asyncio.sleep
    waiting_refreshes: list[float] = []
    cleanup_delays: list[float] = []

    async def controlled_wait_for(awaitable: Awaitable[bool], timeout: float) -> bool:
        assert timeout == pytest.approx(0.1)
        waiting_refreshes.append(timeout)
        return await awaitable

    async def controlled_sleep(delay: float) -> None:
        if delay == 0.1:
            cleanup_delays.append(delay)
            return
        await original_sleep(0)

    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.wait_for", controlled_wait_for
    )
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep", controlled_sleep
    )
    covers = {
        spec.key: AdjustableBedCover(coordinator, _build_cover_description(spec))
        for spec in controller.motor_control_specs
    }
    for cover in covers.values():
        cover.async_write_ha_state = MagicMock()
    head = covers["head"]
    feet = covers["feet"]
    assert head._motor_resource == feet._motor_resource == "motor:*"
    assert "*" not in {head._motor_resource, feet._motor_resource}

    head_task = asyncio.create_task(head.async_open_cover())
    while not waiting_refreshes:
        await original_sleep(0)
    feet_task = asyncio.create_task(feet.async_open_cover())
    while len(waiting_refreshes) < 2:
        await original_sleep(0)

    # Feet was admitted through its ordinary cover resource, after Head's finally
    # completed both release frames under the shared motor-prefix scope.
    assert _writes(client)[:4] == [
        build_cst_command(motor_value=0x00000001),
        build_cst_command(),
        build_cst_command(),
        build_cst_command(motor_value=0x00000004),
    ]
    await coordinator.async_stop_command()
    await asyncio.gather(head_task, feet_task)

    assert _writes(client) == [
        build_cst_command(motor_value=0x00000001),
        build_cst_command(),
        build_cst_command(),
        build_cst_command(motor_value=0x00000004),
        build_cst_command(),
        build_cst_command(),
    ]
    assert cleanup_delays == [0.1] * 4


async def test_coordinator_stop_settles_held_refresh_before_explicit_stop(
    nectar_move_coordinator: AdjustableBedCoordinator,
    mock_bleak_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = nectar_move_coordinator
    client = mock_bleak_client
    controller = _controller(coordinator)
    client.write_gatt_char.reset_mock()
    coordinator.cancel_command.clear()
    original_sleep = asyncio.sleep
    refresh_wait_started = asyncio.Event()
    synthetic_midpoint = asyncio.Event()
    midpoint_reached = asyncio.Event()
    timeline: list[str] = []

    async def controlled_wait_for(awaitable: Awaitable[bool], timeout: float) -> bool:
        assert timeout == pytest.approx(0.1)
        timeline.append("refresh-wait-pending")
        refresh_wait_started.set()
        await synthetic_midpoint.wait()
        timeline.append("refresh-wait-at-midpoint")
        midpoint_reached.set()
        result = await awaitable
        timeline.append("cancel-observed")
        return result

    async def controlled_cleanup_sleep(delay: float) -> None:
        if delay == 0.1:
            timeline.append("cleanup-delay")
            return
        await original_sleep(0)

    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.wait_for", controlled_wait_for
    )
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep",
        controlled_cleanup_sleep,
    )
    original_stop_all = controller.stop_all

    async def verify_stop_uses_the_same_cancellation() -> None:
        assert controller._cleanup_stop_cancel_counter == coordinator._cancel_counter
        await original_stop_all()

    monkeypatch.setattr(controller, "stop_all", verify_stop_uses_the_same_cancellation)
    movement = asyncio.create_task(
        coordinator.async_execute_controller_command(
            lambda current: current.move_head_up(),
            cancel_running=False,
            read_positions_after_operation=False,
        )
    )
    await refresh_wait_started.wait()
    assert coordinator.cancel_command.is_set() is False
    assert _writes(client) == [build_cst_command(motor_value=0x00000001)]
    timeline.append("synthetic-midpoint")
    synthetic_midpoint.set()
    await midpoint_reached.wait()
    timeline.append("stop-request")
    stop = asyncio.create_task(coordinator.async_stop_command())
    await coordinator.cancel_command.wait()
    await asyncio.gather(movement, stop)

    assert timeline == [
        "refresh-wait-pending",
        "synthetic-midpoint",
        "refresh-wait-at-midpoint",
        "stop-request",
        "cancel-observed",
        "cleanup-delay",
        "cleanup-delay",
    ]
    assert _writes(client) == [
        build_cst_command(motor_value=0x00000001),
        build_cst_command(),
        build_cst_command(),
    ]
    assert all(
        record.args[0] == OKIMAT_WRITE_CHAR_UUID for record in client.write_gatt_char.call_args_list
    )


async def test_later_explicit_stop_is_not_suppressed_by_old_cancel_cleanup(
    nectar_move_coordinator: AdjustableBedCoordinator,
    mock_bleak_client: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator = nectar_move_coordinator
    client = mock_bleak_client
    client.write_gatt_char.reset_mock()
    coordinator.cancel_command.clear()
    original_sleep = asyncio.sleep
    refresh_wait_started = asyncio.Event()

    async def controlled_wait_for(awaitable: Awaitable[bool], timeout: float) -> bool:
        assert timeout == pytest.approx(0.1)
        refresh_wait_started.set()
        return await awaitable

    async def controlled_cleanup_sleep(delay: float) -> None:
        if delay != 0.1:
            await original_sleep(0)

    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.wait_for", controlled_wait_for
    )
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.okin_cst.asyncio.sleep",
        controlled_cleanup_sleep,
    )
    movement = asyncio.create_task(
        coordinator.async_execute_controller_command(
            lambda current: current.move_head_up(),
            read_positions_after_operation=False,
        )
    )
    await refresh_wait_started.wait()
    coordinator.request_command_cancel()
    await movement
    await coordinator.async_stop_command()

    assert _writes(client) == [
        build_cst_command(motor_value=0x00000001),
        build_cst_command(),
        build_cst_command(),
        build_cst_command(),
        build_cst_command(),
    ]
