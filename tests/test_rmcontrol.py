"""Exact opt-in RMControl commands, capabilities, and cancellation."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.rmcontrol import (
    RmcontrolController,
    detect_rmcontrol_transport,
)
from custom_components.adjustable_bed.rmcontrol_protocol import Notification


def controller(
    code: str = "A0RM", *, nordic: bool = False, side: str = "left"
) -> RmcontrolController:
    coordinator = MagicMock()
    coordinator.motor_pulse_count = 2
    coordinator.cancel_command = asyncio.Event()
    return RmcontrolController(coordinator, code, rmcontrol_side=side, is_wilinke=not nordic)


@pytest.mark.parametrize("code", ["unknown", "FWRM", "WFRM"])
def test_invalid_or_separate_desk_profile_rejected(code: str) -> None:
    with pytest.raises(ValueError):
        controller(code)


def test_empty_profile_does_not_inherit_remote_capabilities() -> None:
    ctrl = controller("A3RN")
    assert not ctrl.supports_preset_flat
    assert not ctrl.supports_preset_zero_g
    assert not ctrl.supports_motor_control
    assert not ctrl.supports_massage
    assert not ctrl.supports_lights
    assert not ctrl.supports_synchro
    assert not ctrl.supports_memory_presets
    assert ctrl.motor_control_specs == ()
    assert ctrl.controller_button_specs == ()


async def test_motion_uses_corrected_product_bytes_side_and_fresh_release() -> None:
    ctrl = controller(side="right")
    ctrl.write_command = AsyncMock()
    await ctrl.move_feet_up()
    first, release = ctrl.write_command.call_args_list
    assert first.args == (bytes.fromhex("6e 01 01 26 96"),)
    assert first.kwargs == {"repeat_count": 2, "repeat_delay_ms": 100}
    assert release.args == (bytes.fromhex("6e 01 01 6e de"),)
    assert not release.kwargs["cancel_event"].is_set()
    assert release.kwargs["cancel_event"] is not ctrl._coordinator.cancel_command


async def test_motion_failure_still_releases_without_masking_error() -> None:
    ctrl = controller()
    ctrl.write_command = AsyncMock(side_effect=[RuntimeError("movement failed"), None])
    with pytest.raises(RuntimeError, match="movement failed"):
        await ctrl.move_pillow_up()
    assert ctrl.write_command.call_count == 2
    assert ctrl.write_command.call_args_list[0].args[0] == bytes.fromhex("6e 01 00 3f ae")
    assert ctrl.write_command.call_args_list[1].args[0] == bytes.fromhex("6e 01 00 6e dd")


async def test_task_cancellation_still_releases() -> None:
    ctrl = controller()
    ctrl.write_command = AsyncMock(side_effect=[asyncio.CancelledError(), None])
    with pytest.raises(asyncio.CancelledError):
        await ctrl.move_head_up()
    assert ctrl.write_command.call_count == 2


async def test_release_failure_is_not_reported_as_success() -> None:
    ctrl = controller()
    ctrl.write_command = AsyncMock(side_effect=[None, RuntimeError("release failed")])
    with pytest.raises(RuntimeError, match="release failed"):
        await ctrl.move_head_up()


async def test_nordic_getter_override_and_long_press_are_separate() -> None:
    ctrl = controller("A3RM", nordic=True)
    ctrl.write_command = AsyncMock()
    name = "deviceFunctionItemMemoryPosition1"
    with pytest.raises(ValueError, match="ambiguous"):
        await ctrl.async_execute_product_action(name)
    await ctrl.async_execute_product_action(name, getter="get _ detailsPageDisplayList")
    assert ctrl.write_command.call_args.args == (bytes([0x42]),)
    await ctrl.async_execute_product_action(
        name, getter="get _ detailsPageDisplayList", long_press=True
    )
    assert ctrl.write_command.call_args.args == (bytes([0x2B]),)
    with pytest.raises(ValueError, match="no long-press"):
        await ctrl.async_execute_product_action(name, getter="get _ memoryList", long_press=True)


async def test_native_controls_use_details_context_not_alarm_gestures() -> None:
    ctrl = controller("A4RN")
    ctrl.write_command = AsyncMock()
    assert ctrl.supports_preset_tv
    assert ctrl._has("TVPosition", long_press=True)
    await ctrl.preset_tv()
    assert ctrl.write_command.call_args.args[0][3] == 0x58
    save_tv = next(
        spec
        for spec in ctrl.controller_button_specs
        if "detailspagedisplaylist_itemtvposition" in spec.key and spec.key.endswith("_long")
    )
    await save_tv.press_fn(ctrl)
    assert ctrl.write_command.call_args.args[0][3] == 0x64
    with pytest.raises(ValueError, match="no long-press"):
        await ctrl.async_execute_product_action(
            "deviceFunctionItemTVPosition",
            getter="get _ alarmList",
            long_press=True,
        )


def test_native_controls_still_reject_conflicting_main_page_occurrences() -> None:
    ctrl = controller("EORN")
    assert not ctrl.supports_memory_presets
    assert ctrl._lookup("MemoryPosition1") is None


async def test_local_items_never_become_ble_packets() -> None:
    ctrl = controller("E3RM")
    ctrl.write_command = AsyncMock()
    with pytest.raises(ValueError, match="local UI"):
        await ctrl.async_execute_product_action("deviceFunctionItemMemory")
    ctrl.write_command.assert_not_called()


async def test_exact_conflicting_occurrence_has_separate_button() -> None:
    ctrl = controller("EORN")
    ctrl.write_command = AsyncMock()
    name = "deviceFunctionItemMemoryPosition1"
    getter = "get _ detailsPageDisplayList"
    with pytest.raises(ValueError, match="ambiguous"):
        await ctrl.async_execute_product_action(name, getter=getter)
    actions = ctrl.product_profile.find_actions(name, getter=getter)
    assert len(actions) == 2
    for action in actions:
        ctrl.write_command.reset_mock()
        await ctrl.async_execute_product_action(name, getter=getter, occurrence=action.occurrence)
        assert ctrl.write_command.call_args_list[0].args[0][3] == action.short_opcode
    specs = ctrl.controller_button_specs
    assert len({spec.key for spec in specs}) == len(specs)
    assert all(not spec.entity_registry_enabled_default for spec in specs)


async def test_product_button_callback_uses_selected_occurrence() -> None:
    ctrl = controller()
    ctrl.write_command = AsyncMock()
    spec = next(spec for spec in ctrl.controller_button_specs if "pillowup" in spec.key)
    await spec.press_fn(ctrl)
    assert ctrl.write_command.call_args_list[0].args[0][3] == 0x3F


async def test_fixed_queue_spacing_and_cancelled_write_cleanup() -> None:
    ctrl = controller()
    with patch.object(ctrl, "_write_gatt_with_retry", new_callable=AsyncMock) as write:
        await ctrl.write_command(b"first")
        ctrl._coordinator.cancel_command.set()
        await ctrl.write_command(b"cancelled")
        await ctrl.stop_all()
    assert write.call_count == 2
    assert write.call_args_list[0].args[1] == b"first"
    assert write.call_args_list[1].args[1] == bytes.fromhex("6e 01 00 6e dd")
    assert not write.call_args_list[1].kwargs["cancel_event"].is_set()


async def test_transport_detection_requires_exact_writable_pair() -> None:
    client = MagicMock()
    characteristic = MagicMock()
    characteristic.uuid = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
    characteristic.properties = ["write", "write-without-response"]
    service = MagicMock()
    service.uuid = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
    service.characteristics = [characteristic]
    client.services = [service]
    assert await detect_rmcontrol_transport(client) == (False, characteristic.uuid, False)
    characteristic.properties = ["read"]
    with pytest.raises(ValueError, match="exactly one"):
        await detect_rmcontrol_transport(client)
    characteristic.properties = ["write"]
    service.uuid = "unknown"
    with pytest.raises(ValueError):
        await detect_rmcontrol_transport(client)


async def test_notify_exact_role_probes_buffer_and_state_forwarding() -> None:
    ctrl = controller(nordic=True)
    client = ctrl._coordinator.client
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.services.get_characteristic.return_value.properties = ["notify"]
    ctrl.write_command = AsyncMock()
    await ctrl.start_notify()
    notify_uuid, callback = client.start_notify.call_args.args
    assert notify_uuid == "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
    assert [call.args[0] for call in ctrl.write_command.call_args_list] == [
        b"\x00",
        b"\x01",
        b"\x01",
    ]
    assert not ctrl.supports_rmcontrol_alarm
    callback(None, bytearray.fromhex("6e0901"))
    assert not ctrl.supports_rmcontrol_alarm
    callback(None, bytearray.fromhex("0078"))
    assert not ctrl.supports_rmcontrol_alarm  # This exact product has no alarmList.
    ctrl._coordinator.handle_controller_state_updates.assert_called_with(
        {"rmcontrol_capability_alarm": True}
    )
    await ctrl.stop_notify()
    client.stop_notify.assert_awaited_once_with(notify_uuid)


async def test_notify_setup_failure_unsubscribes_and_retains_original_error() -> None:
    ctrl = controller(nordic=True)
    client = ctrl._coordinator.client
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock(side_effect=RuntimeError("cleanup failed"))
    client.services.get_characteristic.return_value.properties = ["notify"]
    ctrl.write_command = AsyncMock(side_effect=ValueError("query failed"))
    with pytest.raises(ValueError, match="query failed"):
        await ctrl.start_notify()
    assert ctrl._notify_uuid is None


async def test_alarm_action_selection_weekdays_and_cancel_frames() -> None:
    ctrl = controller("MXRN")
    ctrl.write_command = AsyncMock()
    ctrl._accept_notification(Notification("capability", {"alarm": True}))
    assert ctrl.supports_rmcontrol_alarm
    await ctrl.rmcontrol_repeat_alarm(2, 7, 30, (0, 6), "TVPosition")
    frame = ctrl.write_command.call_args.args[0]
    assert frame[6:-1] == bytes([2, 0, 7, 30, 0x58, 0x82])
    ctrl = controller("A4RN")
    ctrl.write_command = AsyncMock()
    ctrl._accept_notification(Notification("capability", {"alarm": True}))
    await ctrl.rmcontrol_single_alarm(299, "TVPosition")
    assert [call.args[0][2:4] for call in ctrl.write_command.call_args_list] == [
        bytes([43, 0]),
        bytes([1, 0x58]),
    ]
    ctrl.write_command.reset_mock()
    await ctrl.rmcontrol_single_alarm(0, None)
    assert all(call.args[0][2:4] == b"\x00\x00" for call in ctrl.write_command.call_args_list)


async def test_alarm_validation_and_capability_fail_before_write() -> None:
    ctrl = controller("A4RN")
    ctrl.write_command = AsyncMock()
    with pytest.raises(NotImplementedError):
        await ctrl.rmcontrol_single_alarm(10, "TVPosition")
    ctrl._accept_notification(Notification("capability", {"alarm": True}))
    with pytest.raises(ValueError, match="alarm catalog"):
        await ctrl.rmcontrol_single_alarm(10, "HeadUp")
    with pytest.raises(NotImplementedError):
        await ctrl.rmcontrol_repeat_alarm(1, 7, 30, (7,), "TVPosition")
    ctrl.write_command.assert_not_called()


async def test_anti_snore_requires_negotiation_and_preserves_mode() -> None:
    ctrl = controller("HNRN")
    ctrl.write_command = AsyncMock()
    with pytest.raises(NotImplementedError):
        await ctrl.rmcontrol_anti_snore_switch(True)
    ctrl._accept_notification(Notification("capability", {"anti_snore": True}))
    assert not ctrl.supports_rmcontrol_anti_snore
    ctrl._accept_notification(Notification("anti_snore", {"enabled": True}))
    assert not ctrl.supports_rmcontrol_anti_snore
    ctrl._accept_notification(Notification("anti_snore", {"sleep_advertisement": (83, 76)}))
    await ctrl.rmcontrol_anti_snore_config("time", 9)
    assert ctrl.write_command.call_args.args[0][6:-1] == bytes([2, 0, 9])


@pytest.mark.parametrize("code", ["A0RM", "ETRN", "G1RN", "G2RN", "GKRN"])
def test_sleep_name_does_not_enable_snore_on_other_products(code: str) -> None:
    ctrl = controller(code)
    ctrl._accept_notification(Notification("anti_snore", {"sleep_advertisement": (83,)}))
    assert not ctrl.supports_rmcontrol_anti_snore


@pytest.mark.parametrize("code", ["HNRN", "HQRN", "HSRN", "HURN", "M7RN", "MJRN"])
def test_only_six_source_snore_products_enable_after_sleep_event(code: str) -> None:
    ctrl = controller(code)
    assert not ctrl.supports_rmcontrol_anti_snore
    ctrl._accept_notification(Notification("anti_snore", {"sleep_advertisement": (83,)}))
    assert ctrl.supports_rmcontrol_anti_snore


@pytest.mark.parametrize("code, expected", [("A0RM", False), ("ETRN", True), ("HNRN", True)])
async def test_sleep_query_uses_exact_factory_gate(code: str, expected: bool) -> None:
    ctrl = controller(code, nordic=True)
    client = ctrl._coordinator.client
    client.start_notify = AsyncMock()
    client.services.get_characteristic.return_value.properties = ["notify"]
    ctrl.write_command = AsyncMock()
    await ctrl.start_notify()
    packets = [call.args[0] for call in ctrl.write_command.call_args_list]
    assert (bytes.fromhex("6e0820060300009f") in packets) is expected


async def test_light_reply_requires_selected_factory_light_flag() -> None:
    ctrl = controller("6ERM")
    ctrl.write_command = AsyncMock()
    assert not ctrl.supports_light_color_control
    assert not ctrl.supports_light_timer
    with pytest.raises(NotImplementedError):
        await ctrl.set_light_color((20, 30, 40))
    ctrl._accept_notification(Notification("light_timer", {"seconds": 300}))
    assert not ctrl.supports_light_timer  # A parser event is not the menu gate.
    ctrl._accept_notification(Notification("capability", {"light": True}))
    assert ctrl.supports_light_color_control
    assert ctrl.light_timer_options[-1] == "15 min"
    await ctrl.set_light_timer("15 min")
    assert ctrl.write_command.call_args.args[0] == bytes.fromhex("6e0b038400")
    with pytest.raises(ValueError):
        await ctrl.set_light_timer("16 min")


def test_reported_state_precedes_entity_discovery_callback_and_retains_alarm_records() -> None:
    ctrl = controller()
    assert ctrl.controller_state_sensor_specs == ()
    snapshots = []
    ctrl._coordinator.handle_controller_state_updates.side_effect = lambda _: snapshots.append(
        {spec.key for spec in ctrl.controller_state_sensor_specs}
    )
    ctrl._accept_notification(Notification("light_timer", {"seconds": 120}))
    assert snapshots == [{"rmcontrol_light_timer"}]
    for alarm_id in (1, 2):
        ctrl._accept_notification(
            Notification(
                "repeat_alarm",
                {
                    "alarm_id": alarm_id,
                    "record_flag": 0,
                    "hour": 7,
                    "minute": 30,
                    "command": 0x45,
                    "repeat_mask": 0x80,
                },
            )
        )
    assert set(ctrl.protocol_diagnostics["last_received_alarm_records"]) == {1, 2}
    alarm_spec = next(
        spec for spec in ctrl.controller_state_sensor_specs if spec.key == "rmcontrol_alarm_record"
    )
    assert "rmcontrol_repeat_alarm_command" in alarm_spec.attribute_keys


async def test_reconnect_clears_previously_forwarded_telemetry() -> None:
    ctrl = controller(nordic=True)
    ctrl._accept_notification(Notification("rgb", {"rgb": (1, 2, 3), "on": True}))
    ctrl._accept_notification(Notification("light_timer", {"seconds": 120}))
    ctrl._coordinator.handle_controller_state_updates.reset_mock()
    client = ctrl._coordinator.client
    client.start_notify = AsyncMock()
    client.services.get_characteristic.return_value.properties = ["notify"]
    ctrl.write_command = AsyncMock()
    await ctrl.start_notify()
    cleared = ctrl._coordinator.handle_controller_state_updates.call_args.args[0]
    assert cleared["under_bed_lights_rgb"] is None
    assert cleared["under_bed_lights_on"] is None
    assert cleared["rmcontrol_light_timer_seconds"] is None
    assert ctrl._reported_state == {}
    assert not ctrl.supports_light_timer


async def test_alarm_query_invalidates_previous_observations_without_claiming_deletion() -> None:
    ctrl = controller("MXRN")
    ctrl.write_command = AsyncMock()
    ctrl._accept_notification(Notification("capability", {"alarm": True}))
    ctrl._accept_notification(Notification("repeat_alarm", {"alarm_id": 1, "hour": 7}))
    await ctrl.rmcontrol_query_alarms()
    assert ctrl.protocol_diagnostics["last_received_alarm_records"] == {}
    assert ctrl._coordinator.handle_controller_state_updates.call_args.args[0] == {
        "rmcontrol_repeat_alarm_alarm_id": None,
        "rmcontrol_repeat_alarm_hour": None,
    }


@pytest.mark.parametrize("deleted_id", [1, 2])
async def test_alarm_delete_invalidates_only_the_displayed_slot(deleted_id: int) -> None:
    ctrl = controller("MXRN")
    ctrl.write_command = AsyncMock()
    ctrl._accept_notification(Notification("capability", {"alarm": True}))
    for alarm_id in (1, 2):
        ctrl._accept_notification(Notification("repeat_alarm", {"alarm_id": alarm_id, "hour": 7}))
    ctrl._coordinator.handle_controller_state_updates.reset_mock()
    await ctrl.rmcontrol_delete_alarm(deleted_id)
    assert set(ctrl.protocol_diagnostics["last_received_alarm_records"]) == {3 - deleted_id}
    if deleted_id == 2:
        assert "rmcontrol_repeat_alarm_alarm_id" not in ctrl._reported_state
        ctrl._coordinator.handle_controller_state_updates.assert_called_once_with({
            "rmcontrol_repeat_alarm_alarm_id": None,
            "rmcontrol_repeat_alarm_hour": None,
        })
    else:
        assert ctrl._reported_state["rmcontrol_repeat_alarm_alarm_id"] == 2
        ctrl._coordinator.handle_controller_state_updates.assert_not_called()


def test_alarm_menu_and_type_are_separate_exact_gates() -> None:
    single, repeating, empty, exception = (
        controller(code) for code in ("A4RN", "MXRN", "HNRN", "PNRN")
    )
    assert exception.supports_rmcontrol_single_alarm
    assert not exception.supports_rmcontrol_alarm_time_sync
    for ctrl in (single, repeating, empty):
        assert not ctrl.supports_rmcontrol_alarm
        ctrl._accept_notification(Notification("capability", {"alarm": True}))
    assert single.supports_rmcontrol_single_alarm
    assert not single.supports_rmcontrol_repeat_alarm
    assert repeating.supports_rmcontrol_repeat_alarm
    assert not repeating.supports_rmcontrol_single_alarm
    assert not empty.supports_rmcontrol_alarm  # richmatAlarmList is not alarmList.
    empty._accept_notification(Notification("repeat_alarm", {"alarm_id": 1}))
    assert not empty.supports_rmcontrol_alarm


async def test_repeat_only_controller_rejects_countdown_without_writes() -> None:
    ctrl = controller("MXRN")
    ctrl.write_command = AsyncMock()
    ctrl._accept_notification(Notification("capability", {"alarm": True}))
    with pytest.raises(NotImplementedError):
        await ctrl.rmcontrol_single_alarm(1, "TVPosition")
    with pytest.raises(ValueError):
        await ctrl.rmcontrol_repeat_alarm(1, 7, 30, (7,), "TVPosition")
    ctrl.write_command.assert_not_called()


async def test_alarm_time_sync_startup_does_not_require_repeat_or_reply() -> None:
    ctrl = controller("A4RN", nordic=True)
    client = ctrl._coordinator.client
    client.start_notify = AsyncMock()
    client.services.get_characteristic.return_value.properties = ["notify"]
    ctrl.write_command = AsyncMock()
    with patch(
        "custom_components.adjustable_bed.beds.rmcontrol.dt_util.now",
        return_value=datetime(1970, 1, 1, tzinfo=UTC),
    ):
        await ctrl.start_notify()
    assert not ctrl.supports_rmcontrol_single_alarm
    assert ctrl.supports_rmcontrol_alarm_time_sync
    packets = [call.args[0] for call in ctrl.write_command.call_args_list]
    assert packets == [
        b"\x00",
        bytes.fromhex("6e0c200802010000000000a5"),
        bytes.fromhex("6e0d20080301000101000000a9"),
        b"\x01",
        b"\x01",
    ]
    await ctrl.rmcontrol_sync_alarm_time(datetime(1970, 1, 1, tzinfo=UTC))
    unsupported = controller("PNRN")
    unsupported.write_command = AsyncMock()
    with pytest.raises(NotImplementedError):
        await unsupported.rmcontrol_sync_alarm_time(datetime(1970, 1, 1, tzinfo=UTC))
    unsupported.write_command.assert_not_called()


async def test_light_flag_false_rejects_reply_and_reports_as_setter_authority() -> None:
    ctrl = controller("FCRN")
    ctrl.write_command = AsyncMock()
    ctrl._accept_notification(Notification("capability", {"light": True}))
    ctrl._accept_notification(Notification("rgb", {"rgb": (20, 30, 40)}))
    assert not ctrl.supports_light_color_control
    assert not ctrl.supports_light_timer
    with pytest.raises(NotImplementedError):
        await ctrl.set_light_color((20, 30, 40))
    ctrl.write_command.assert_not_called()


async def test_parn_enforces_exact_source_eight_color_palette() -> None:
    ctrl = controller("PARN")
    ctrl.write_command = AsyncMock()
    ctrl._accept_notification(Notification("capability", {"light": True}))
    assert ctrl.supports_light_color_control
    assert ctrl.supports_light_timer
    palette = (
        (255, 255, 0),
        (0, 255, 0),
        (0, 127, 255),
        (0, 0, 255),
        (139, 0, 255),
        (255, 255, 255),
        (255, 0, 0),
        (255, 165, 0),
    )
    assert ctrl.protocol_diagnostics["light_rgb_palette"] == palette
    for rgb in palette:
        await ctrl.set_light_color(rgb)
    assert ctrl.write_command.await_count == 8
    with pytest.raises(ValueError, match="eight RGB colors"):
        await ctrl.set_light_color((0, 255, 255))
    assert ctrl.write_command.await_count == 8


@pytest.mark.parametrize(
    ("seconds", "option"),
    [(0, "Always On"), (65535, "Always On"), (60, "1 min"), (900, "15 min"),
     (61, None), (960, None)],
)
def test_timer_report_updates_select_and_diagnostic(seconds: int, option: str | None) -> None:
    ctrl = controller()
    ctrl._accept_notification(Notification("light_timer", {"seconds": seconds}))
    updates = ctrl._coordinator.handle_controller_state_updates.call_args.args[0]
    assert updates["light_timer_option"] == option
    assert updates["rmcontrol_light_timer_seconds"] == seconds


async def test_reconnect_waits_for_delayed_menu_capabilities() -> None:
    ctrl = controller("HNRN", nordic=True)
    client = ctrl._coordinator.client
    client.start_notify = AsyncMock()
    client.services.get_characteristic.return_value.properties = ["notify"]
    ctrl.write_command = AsyncMock()
    with patch("custom_components.adjustable_bed.beds.rmcontrol._CAPABILITY_TIMEOUT", 1):
        setup = asyncio.create_task(ctrl.start_notify())
        await asyncio.sleep(0)
        assert not setup.done()
        ctrl._accept_notification(Notification("rgb", {"on": True}))
        await asyncio.sleep(0)
        assert not setup.done()
        ctrl._accept_notification(Notification("capability", {"light": True}))
        ctrl._accept_notification(Notification("capability", {"alarm": True}))
        await asyncio.sleep(0)
        assert not setup.done()
        ctrl._accept_notification(Notification("anti_snore", {"sleep_advertisement": (83,)}))
        await setup
    assert ctrl.supports_light_color_control
    assert ctrl.supports_rmcontrol_anti_snore
    await ctrl.set_light_color((20, 30, 40))
    await ctrl.rmcontrol_anti_snore_switch(True)


async def test_missing_capability_reply_times_out_and_late_reply_still_enables() -> None:
    ctrl = controller("6ERM", nordic=True)
    client = ctrl._coordinator.client
    client.start_notify = AsyncMock()
    client.services.get_characteristic.return_value.properties = ["notify"]
    ctrl.write_command = AsyncMock()
    with patch("custom_components.adjustable_bed.beds.rmcontrol._CAPABILITY_TIMEOUT", 0):
        await ctrl.start_notify()
    assert not ctrl.supports_light_color_control
    assert ctrl._notify_uuid is not None
    ctrl._accept_notification(Notification("capability", {"light": True}))
    assert ctrl.supports_light_color_control


def test_strip_acknowledgement_requires_a_power_off_route() -> None:
    ctrl = controller("A3RN")
    ctrl._accept_notification(Notification("capability", {"light": True}))
    assert not ctrl.supports_light_color_control
    assert ctrl.supports_light_timer  # Timer configuration does not require a power-off route.


async def test_replacement_controller_clears_coordinator_session_state() -> None:
    ctrl = controller(nordic=True)
    state = {"unrelated": 42}
    ctrl._coordinator.controller_state = state
    ctrl._coordinator.handle_controller_state_updates.side_effect = state.update
    ctrl._accept_notification(Notification("music", {"playing": True}))
    ctrl._accept_notification(Notification("lock", {"locked": True}))
    ctrl._accept_notification(Notification("massage", {"head_strength": 3}))
    replacement = RmcontrolController(ctrl._coordinator, "A0RM", is_wilinke=False)
    client = ctrl._coordinator.client
    client.start_notify = AsyncMock()
    client.services.get_characteristic.return_value.properties = ["notify"]
    replacement.write_command = AsyncMock()
    await replacement.start_notify()
    assert state["rmcontrol_music_playing"] is None
    assert state["rmcontrol_lock_locked"] is None
    assert state["rmcontrol_massage_head_strength"] is None
    assert state["unrelated"] == 42


@pytest.mark.parametrize("code, paired", [("A0RM", False), ("ACRM", True)])
async def test_zone_strength_actions_use_intensity_controls(code: str, paired: bool) -> None:
    ctrl = controller(code)
    assert not ctrl.supports_head_massage_toggle_control
    assert not ctrl.supports_foot_massage_toggle_control
    assert ctrl.supports_head_massage_intensity_step_control is paired
    assert ctrl.supports_foot_massage_intensity_step_control is paired
    if paired:
        with patch.object(ctrl, "_execute", new_callable=AsyncMock) as execute:
            await ctrl.massage_head_up()
            await ctrl.massage_head_down()
            await ctrl.massage_foot_up()
            await ctrl.massage_foot_down()
        assert [call.args[0] for call in execute.call_args_list] == [
            "MassageHeadInstensityStrengthen",
            "MassageHeadInstensityWeaken",
            "MassageFootInstensityStrengthen",
            "MassageFootInstensityWeaken",
        ]
    else:
        names = [spec.name for spec in ctrl.controller_button_specs]
        assert any("Massage Head Instensity Strengthen" in name for name in names)
        assert any("Massage Foot Instensity Strengthen" in name for name in names)
