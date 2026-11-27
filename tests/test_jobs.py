"""JobsAI 1.0.6 literal commands, native exposure and connection-bound cancellation."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.serenity.controller import clock_frame
from custom_components.adjustable_bed.beds.serenity.jobs import (
    ALARM_KEYS,
    JOBS_ACTIONS,
    JOBS_PROFILES,
    JobsController,
    alarm_frame,
    repeat_mask,
)
from custom_components.adjustable_bed.card import CARD_MASSAGE, CARD_PRESET_SAVE
from custom_components.adjustable_bed.codec import okin_nframe as codec
from custom_components.adjustable_bed.const import BED_TYPE_JOBS, DOMAIN, SIDE_BOTH
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.services import async_register_services
from tests.hold_lease_wire import virtual_clock
from tests.test_controller_contract import _FactoryCoordinator
from tests.test_okin_bedding_apps import STOP, _coordinator, written
from tests.test_okin_bedding_apps_integration import _target

VECTORS = json.loads((Path(__file__).parent / "fixtures/jobs_vectors.json").read_text())


def jobs(mode="mode1") -> JobsController:
    coordinator = _coordinator()
    coordinator._cancel_counter = 0
    coordinator.cancel_counter = 0
    return JobsController(coordinator, mode=mode)


@pytest.mark.parametrize(
    "vector", [v for v in VECTORS if v["inputs"]["builder"] != "legacy"], ids=lambda v: v["id"]
)
def test_live_frozen_literals_use_existing_codec(vector):
    i = vector["inputs"]
    match i["builder"]:
        case "normal":
            frame = codec.frame96(i["a"], i["b"])
        case "alarm":
            frame = alarm_frame(i["kind"], i["repeat"], i["action"], i["hour"], i["minute"])
        case "query":
            frame = codec.request(i["bytes"][1])
        case "calendar":
            year, month, day, _, hour, minute, second = i["fields"]
            frame = clock_frame(datetime(year, month, day, hour, minute, second))
        case _:
            raise AssertionError("Unknown frozen builder")
    assert frame.hex() == vector["expected_bytes"]


@pytest.mark.parametrize("mode", JOBS_PROFILES)
@pytest.mark.parametrize("action", JOBS_ACTIONS)
async def test_every_live_control_writes_its_own_fields_and_two_releases(mode, action):
    controller = jobs(mode)
    with virtual_clock():
        await controller.hold_control(action, 350)
    assert written(controller) == [codec.frame96(*JOBS_ACTIONS[action]).hex()] * 2 + [STOP] * 2


@pytest.mark.parametrize(
    "method,action",
    [
        ("move_head_up", "head_up"),
        ("move_legs_down", "foot_down"),
        ("preset_flat", "flat"),
        ("preset_incline", "incline"),
        ("preset_lounge", "lounge"),
        ("massage_off", "massage_off"),
        ("massage_intensity_down", "massage_intensity_down"),
        ("massage_toggle", "massage_on"),
    ],
)
async def test_native_commands_send_jobs_table_not_parent_cst_fields(method, action):
    controller = jobs()
    with virtual_clock():
        await getattr(controller, method)()
    assert set(written(controller)[:-2]) == {codec.frame96(*JOBS_ACTIONS[action]).hex()}
    assert written(controller)[-2:] == [STOP] * 2


async def test_both_modes_are_offline_constructible_and_searchable():
    from unittest.mock import MagicMock

    from custom_components.adjustable_bed.config_flow import _motor_count_options
    from custom_components.adjustable_bed.detection import detect_bed_type, get_bed_type_options
    from custom_components.adjustable_bed.validators import get_variants_for_bed_type

    assert any("JobsAI" in option["label"] for option in get_bed_type_options())
    assert set(get_variants_for_bed_type(BED_TYPE_JOBS)) == {"mode1", "mode2"}
    assert _motor_count_options(BED_TYPE_JOBS) == [2]
    for mode in JOBS_PROFILES:
        controller = await create_controller(_FactoryCoordinator(), BED_TYPE_JOBS, mode, None)
        assert controller.profile is JOBS_PROFILES[mode]
        assert controller.memory_slot_names == ("M1", "M2")
        assert not controller.supports_lights and not controller.has_lumbar_support
    info = MagicMock(name="OKIN anything", service_uuids=[], manufacturer_data={})
    info.name = "OKIN anything"
    assert detect_bed_type(info) != BED_TYPE_JOBS  # Shared name never identifies this app.


async def test_parser_alarm_and_status_in_same_packet_signed_values_and_save_feedback():
    controller = jobs()
    updates = {}
    controller._coordinator.handle_controller_state_update.side_effect = lambda key, value: (
        updates.update({key: value})
    )
    controller._coordinator.handle_controller_state_updates.side_effect = lambda *values: (
        updates.update({v.key: v.value for v in values})
    )
    controller._save_code = 4
    # byte0/header/size/checksum are deliberately not validated by this app.
    frame = bytearray.fromhex("ff0c0000be09161e000181")
    controller._handle_notification(None, frame[:10])
    assert not updates
    controller._handle_notification(None, frame)
    assert updates == {
        "jobs_sleep_type": 9,
        "jobs_sleep_repeat": -66,
        "jobs_sleep_hour": 22,
        "jobs_sleep_minute": 30,
        "jobs_sleep_enabled": True,
        "jobs_status": -127,
        "jobs_save_event": 4,
    }
    assert controller._save_code == 0
    updates.clear()
    frame[1] = 13
    frame[5] = 11
    controller._handle_notification(None, frame)
    assert updates["jobs_wake_type"] == 11
    assert "jobs_status" not in updates and "jobs_save_event" not in updates
    assert controller.validate_alarm_action("wake", "keep") == 11
    controller.on_disconnect()
    with pytest.raises(ValueError, match="not_received"):
        controller.validate_alarm_action("wake", "keep")


@pytest.mark.parametrize("mode,automatic", [("mode1", 12), ("mode2", 7)])
async def test_dual_alarm_programming_queries_and_retained_hidden_types(mode, automatic):
    controller = jobs(mode)
    assert controller.validate_alarm_action("wake", "automatic") == automatic
    assert repeat_mask(datetime(2026, 11, 27, 22, 30), ()) == 32  # No invented tomorrow rollover.
    assert repeat_mask(datetime(2026, 11, 27), (0, 1, 2, 3, 4, 5, 6)) == 255
    controller._alarm_types["sleep"] = 1
    assert controller.validate_alarm_action("sleep", "keep") == 1
    with (
        patch(
            "custom_components.adjustable_bed.beds.serenity.jobs.dt_util.now",
            return_value=datetime(2026, 11, 27),
        ),
        virtual_clock(),
    ):
        await controller.configure_jobs_alarm(
            kind="wake",
            enabled=True,
            action="automatic",
            hour=8,
            minute=0,
            weekdays=(0, 1, 2, 3, 4, 5, 6),
        )
        await controller.configure_jobs_alarm(
            kind="sleep", enabled=False, action="keep", hour=0, minute=0, weekdays=()
        )
    assert written(controller) == [
        alarm_frame("wake", 255, automatic, 8, 0).hex(),
        "00d0",
        "070500000000000000",
        "00c0",
    ]


async def test_notification_callback_and_release_cannot_migrate_to_replacement_link():
    controller = jobs()
    old = controller.client
    with virtual_clock():
        await controller.start_notify()
    callback = old.start_notify.await_args.args[1]
    old.write_gatt_char.reset_mock()
    replacement = _coordinator().client

    async def replace_on_first_write(*args, **kwargs):
        controller.on_disconnect()
        controller._coordinator.client = replacement

    old.write_gatt_char.side_effect = replace_on_first_write
    with virtual_clock(), pytest.raises(ConnectionError):
        await controller.hold_control("head_up", 400)
    assert written(controller) == []
    assert len(old.write_gatt_char.await_args_list) == 1
    controller._coordinator.handle_controller_state_update.reset_mock()
    callback(old.start_notify.await_args.args[0], bytearray.fromhex("000c000001090800000181"))
    controller._coordinator.handle_controller_state_update.assert_not_called()


async def test_cancelled_queued_refresh_cannot_write_after_stop_cancellation_is_cleared():
    controller = jobs()
    coordinator = controller._coordinator
    await controller._ble_lock.acquire()
    task = asyncio.create_task(controller.hold_control("head_up", 400))
    await asyncio.sleep(0)
    coordinator.cancel_command.set()
    coordinator._cancel_counter += 1
    coordinator.cancel_counter += 1
    coordinator.cancel_command.clear()
    controller._ble_lock.release()
    with virtual_clock(), pytest.raises(asyncio.CancelledError):
        await task
    assert written(controller) == [STOP] * 2


async def test_alarm_query_pending_at_stop_is_suppressed():
    controller = jobs()

    async def stop(*args, **kwargs):
        controller._coordinator._cancel_counter += 1
        controller._coordinator.cancel_counter += 1

    controller.client.write_gatt_char.side_effect = stop
    with virtual_clock(), pytest.raises(asyncio.CancelledError):
        await controller.configure_jobs_alarm(
            kind="sleep", enabled=False, action="keep", hour=0, minute=0, weekdays=()
        )
    assert written(controller) == ["070500000000000000"]


async def test_task_cancellation_waits_for_both_releases():
    controller = jobs()
    reached = asyncio.Event()
    finish_write = asyncio.Event()

    async def movement(*args, **kwargs):
        if args[1] != bytes.fromhex(STOP):
            reached.set()
            await finish_write.wait()

    controller.client.write_gatt_char.side_effect = movement
    task = asyncio.create_task(controller.hold_control("head_up", 400))
    await reached.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    assert STOP not in written(controller)
    finish_write.set()
    with virtual_clock(), pytest.raises(asyncio.CancelledError):
        await task
    assert written(controller)[-2:] == [STOP] * 2
    writes = len(written(controller))
    await asyncio.sleep(0)
    assert len(written(controller)) == writes


async def test_native_entities_card_placement_typed_state_and_side_ids(hass):
    from custom_components.adjustable_bed.button import _button_entities_for
    from custom_components.adjustable_bed.sensor import _sensor_entities_for
    from tests.test_malouf_app_entities import configure_entity_runtime

    controller = jobs()
    specs = {spec.key: spec for spec in controller.controller_button_specs}
    assert specs["jobs_wave_4"].card == CARD_MASSAGE
    assert specs["jobs_save_incline"].card == CARD_PRESET_SAVE
    runtime = configure_entity_runtime(hass, controller, BED_TYPE_JOBS)
    buttons = {entity.unique_id for entity in _button_entities_for(hass, runtime)}
    sensors = {entity.unique_id for entity in _sensor_entities_for(hass, runtime)}
    assert "bed_jobs_wave_4_left" in buttons
    assert "bed_jobs_sleep_alarm_left" in sensors
    assert ALARM_KEYS["sleep"].enabled in {
        spec.state_key for spec in controller.controller_state_binary_sensor_specs
    }


@pytest.mark.parametrize("mode", ["mode1", "mode2"])
async def test_alarm_service_routes_selected_side_and_preflights_all_before_writing(hass, mode):
    await async_register_services(hass)
    controller = jobs(mode)
    controller.configure_alarm = AsyncMock()
    coordinator = _target(BED_TYPE_JOBS, controller)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, SIDE_BOTH)], []),
    ):
        await hass.services.async_call(
            DOMAIN,
            "set_alarm",
            {
                "device_id": "bed",
                "slot": 2,
                "enabled": True,
                "wake_action": "wake_up",
                "time": "08:00",
                "weekdays": ["monday", "sunday"],
            },
            blocking=True,
        )
        alarm = controller.configure_alarm.await_args.args[0]
        assert alarm.slot == 2 and alarm.wake_action == "wake_up" and alarm.weekdays == (0, 6)
        controller.configure_alarm.reset_mock()
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                "set_alarm",
                {
                    "device_id": "bed",
                    "slot": 1,
                    "enabled": True,
                    "wake_action": "wake_up",
                    "time": "08:00",
                },
                blocking=True,
            )
        controller.configure_alarm.assert_not_awaited()


@pytest.mark.parametrize("name", ["OKIN", "oKiN custom", "okin-123"])
def test_discovery_offers_shared_prefix_as_explicit_candidate(name):
    from unittest.mock import MagicMock

    from custom_components.adjustable_bed.detection import detect_bed_type_detailed

    info = MagicMock(service_uuids=[], manufacturer_data={})
    info.name = name
    info.address = "AA:BB:CC:DD:EE:FF"
    result = detect_bed_type_detailed(info)
    assert result.bed_type != BED_TYPE_JOBS
    assert BED_TYPE_JOBS in result.ambiguous_types


async def test_jobs_startup_uses_exact_roles_optional_model_read_and_local_clock():
    controller = jobs()
    client = controller.client
    model_role = client.services[1].characteristics[0]
    model_role.uuid = "00002a24-0000-1000-8000-00805f9b34fb"
    now = datetime(2026, 11, 27, 8, 9, 10)
    with (
        virtual_clock(),
        patch("custom_components.adjustable_bed.beds.serenity.jobs.dt_util.now", return_value=now),
    ):
        await controller.start_notify()
    client.read_gatt_char.assert_awaited_once_with(model_role)
    assert client.start_notify.await_args.args[0] is client.services[0].characteristics[1]
    assert written(controller) == ["07061a0b1b0508090a"]


async def test_hidden_alarm_actions_require_the_same_received_type_on_that_physical_side(hass):
    from custom_components.adjustable_bed.alarm import AlarmRequest
    from tests.alarm_helpers import call_set_alarm

    left, right = jobs("mode1"), jobs("mode2")
    left._alarm_types["wake"] = 11
    now = datetime(2026, 11, 27, 8)
    request = AlarmRequest(
        enabled=True, slot=2, hour=9, wake_action="wave_massage", reference_time=now
    )
    left.validate_alarm(request)
    with pytest.raises(ValueError):
        right.validate_alarm(request)
    with virtual_clock():
        scheduled = await call_set_alarm(
            hass,
            left,
            {"enabled": True, "slot": 2, "wake_action": "wave_massage", "time": "09:00"},
            side="left",
            bed_type=BED_TYPE_JOBS,
        )
    assert written(left)[-1] == "00d0"
    assert written(right) == []
    assert scheduled[0]["cancel_running"] is True
    assert scheduled[0]["resource"] is None


async def test_incline_recall_clears_prior_pending_save_intent():
    controller = jobs()
    controller._save_code = 4
    with virtual_clock():
        await controller.preset_incline()
    assert controller._save_code == 0


@pytest.mark.parametrize("replace_link", [False, True])
async def test_timed_move_releases_only_on_its_original_link(hass, monkeypatch, replace_link):
    await async_register_services(hass)
    controller = jobs()
    physical = controller._coordinator
    coordinator = _target(BED_TYPE_JOBS, controller)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        lambda *_: ([(coordinator, SIDE_BOTH)], []),
    )
    first = physical.client
    replacement = _coordinator().client

    async def swap(*_args, **_kwargs):
        controller.on_disconnect()
        physical.client = replacement

    if replace_link:
        first.write_gatt_char.side_effect = swap
    with virtual_clock():
        call = hass.services.async_call(
            DOMAIN, "timed_move",
            {"device_id": "bed", "motor": "head", "direction": "up", "duration_ms": 250},
            blocking=True,
        )
        if replace_link:
            with pytest.raises(ConnectionError, match="previous BLE connection"):
                await call
        else:
            await call
    if replace_link:
        assert first.write_gatt_char.await_count == 1
        replacement.write_gatt_char.assert_not_awaited()
    else:
        assert written(controller) == [codec.frame96(*JOBS_ACTIONS["head_up"]).hex()] * 2 + [STOP] * 2
