"""SleepFunction's exact layouts, native actions, and session-owned cleanup."""

import asyncio
from datetime import UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.richmat_classic.caller import Selection
from custom_components.adjustable_bed.beds.richmat_classic.profiles import load_catalog
from custom_components.adjustable_bed.beds.richmat_classic.sleepfunction import (
    SleepFunctionController,
    SleepFunctionReceive,
)
from custom_components.adjustable_bed.beds.richmat_classic.sleepfunction_settings import Settings
from custom_components.adjustable_bed.beds.richmat_classic.transport import Transport
from custom_components.adjustable_bed.command_scheduler import (
    CommandIntent,
    DeviceCommandScheduler,
)
from custom_components.adjustable_bed.profiles.sleepfunction import EXCLUDED_LAYOUTS, PICKER_LAYOUTS
from tests.error_helpers import raises_key
from tests.test_richmat_classic import packets
from tests.test_richmat_resource_apps import clock as clock


def controller(layout="6BRM", wire="FRAMED"):
    coordinator = MagicMock()
    coordinator.address = "AA:BB:CC:DD:EE:71"
    coordinator.cancel_command = asyncio.Event()
    coordinator.entry.data = {
        "protocol_variant": "sleepfunction",
        "product_type": layout,
        "ble_device_name": "6BRM-bed",
        "motor_pulse_count": 1,
    }
    coordinator.client.is_connected = True
    coordinator.client.write_gatt_char = AsyncMock()
    coordinator.client.start_notify = AsyncMock()
    coordinator.client.stop_notify = AsyncMock()
    ctrl = SleepFunctionController(coordinator)
    coordinator.controller = ctrl
    ctrl._session = Transport(
        coordinator.client,
        SimpleNamespace(uuid="write", properties=["write"], handle=1),
        SimpleNamespace(uuid="notify", properties=["notify"], handle=2),
        wire,
    )
    ctrl._wire = wire
    return ctrl, coordinator


async def test_a_frame_waiting_for_another_gatt_operation_obeys_a_later_stop_or_owner():
    ctrl, coordinator = controller()
    cancel = asyncio.Event()
    async with ctrl.ble_lock:
        stopped = asyncio.create_task(ctrl._send(b"\x01", cancel))
        await asyncio.sleep(0)
        cancel.set()
    await stopped
    async with ctrl.ble_lock:
        replaced = asyncio.create_task(ctrl._send(b"\x02"))
        await asyncio.sleep(0)
        coordinator.controller = object()
    with raises_key("sleepfunction_session"):
        await replaced
    assert packets(coordinator) == []


def test_all_layouts_have_native_names_and_no_placeholder_or_duplicate_keys():
    assert len(load_catalog("sleepfunction").models) == 558
    for layout in load_catalog("sleepfunction").models:
        if layout in EXCLUDED_LAYOUTS | PICKER_LAYOUTS:
            continue
        ctrl, _ = controller(layout)
        for hold in (False, True) if any(c.hold_affected for c in ctrl._controls) else (False,):
            ctrl._selection = Selection(hold=hold)
            specs = ctrl.controller_button_specs
            assert len({s.key for s in specs}) == len(specs), layout
            import json
            from pathlib import Path

            translations = json.loads(
                (
                    Path(__file__).parents[1] / "custom_components/adjustable_bed/strings.json"
                ).read_text()
            )["entity"]["button"]
            names = [
                translations[s.translation_key]["name"].format(**(s.translation_placeholders or {}))
                if s.translation_key
                else s.name
                for s in specs
            ]
            assert len(set(names)) == len(names), (layout, names)
            assert not any(n.startswith("Button ") for n in names), layout
            assert all(s.hold is None for s in specs if s.requires_confirmation)


@pytest.mark.parametrize(
    "wire,first,end", [("RAW", "34", "6e"), ("FRAMED", "6e01002493", "6e01006edd")]
)
async def test_actual_getter_and_cancellation_proof_release(clock, wire, first, end):
    ctrl, target = controller(wire=wire)
    await ctrl.execute_action(1, hold_ms=300)
    assert packets(target)[0] == first
    assert packets(target)[-1] == end
    assert ctrl._worker.mode == -1


@pytest.mark.parametrize("layout,node", [("FRRM", 11), ("F4RM", 4)])
async def test_inert_long_only_once_control_never_writes(clock, layout, node):
    ctrl, target = controller(layout)
    with raises_key("sleepfunction_control"):
        await ctrl.execute_action(node, long=True)
    assert not packets(target)


@pytest.mark.parametrize("wire,tail", [("RAW", "84"), ("FRAMED", "6e01006edd")])
async def test_null_short_long_control_uses_transport_release(clock, wire, tail):
    ctrl, target = controller("AORM", wire)
    await ctrl.execute_action(8, long=True)
    assert packets(target)[-1] == tail
    assert ("6e010084f3" in packets(target)) if wire == "FRAMED" else packets(target) == ["84"]


async def test_stop_before_first_frame_does_not_start_movement(clock):
    ctrl, target = controller()
    target.cancel_command.set()
    await ctrl.execute_action(1)
    assert packets(target) == ["6e01006edd"]


async def test_replacement_owner_cannot_receive_old_cleanup(clock):
    ctrl, target = controller()
    old = ctrl._session

    async def write(*args, **kwargs):
        target.controller = MagicMock()
        target.forward_controller_state_updates.reset_mock()
        ctrl.forward_controller_state_updates = MagicMock()

    target.client.write_gatt_char.side_effect = write
    with raises_key("sleepfunction_session"):
        await ctrl.execute_action(1, hold_ms=300)
    assert packets(target) == ["6e01002493"]
    ctrl._notification(old, old.notify, bytearray.fromhex("6e0e00037f"))
    assert not ctrl._receive.light_capable
    ctrl._publish()
    ctrl.on_disconnect()
    ctrl.forward_controller_state_updates.assert_not_called()


@pytest.mark.parametrize(
    "wire,expected", [("FRAMED", ["6e01006edd", "6e01016ede"]), ("RAW", ["6e"])]
)
async def test_global_stop_releases_every_exposed_target(clock, wire, expected):
    ctrl, target = controller("DHRM", wire)
    await ctrl.move_back_stop()
    assert packets(target) == expected


async def test_cancelled_global_stop_finishes_all_targets(clock):
    ctrl, target = controller("DHRM")
    first = asyncio.Event()

    async def write(*args, **kwargs):
        first.set()
        await asyncio.sleep(0)

    target.client.write_gatt_char.side_effect = write
    operation = asyncio.create_task(ctrl.stop_all())
    await first.wait()
    operation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await operation
    assert packets(target) == ["6e01006edd", "6e01016ede"]


async def test_manual_stop_frames_are_delivered_command_frames(clock):
    ctrl, target = controller("DHRM")
    scheduler = DeviceCommandScheduler("sleepfunction")

    async def stop(context):
        target.cancel_command = context.cancel_event
        await ctrl.stop_all()
        assert context.frames_written == 2
        assert not context.cleanup_stop_sent

    await scheduler.admit_stop(stop)
    await scheduler.async_shutdown()


async def test_native_scheduler_stop_drains_release_once(clock):
    ctrl, target = controller()
    scheduler = DeviceCommandScheduler("sleepfunction")
    first = asyncio.Event()

    async def write(*args, **kwargs):
        first.set()
        await asyncio.sleep(0)

    target.client.write_gatt_char.side_effect = write

    async def move(context):
        target.cancel_command = context.cancel_event
        await ctrl.execute_action(1, hold_ms=60000)

    running = asyncio.create_task(scheduler.execute(CommandIntent(operation=move)))
    await first.wait()

    async def stop(context):
        target.cancel_command = context.cancel_event
        await ctrl.stop_all()

    await scheduler.admit_stop(stop)
    await asyncio.gather(running, return_exceptions=True)
    assert packets(target)[-1] == "6e01006edd"
    assert all(v == "6e01006edd" for v in packets(target)[1:])
    await scheduler.async_shutdown()


def test_parser_fragments_validates_checksum_and_discards_malformed_data():
    receive = SleepFunctionReceive()
    receive.feed(bytes.fromhex("6e09"), app="sleepfunction", layout="6BRM")
    receive.feed(bytes.fromhex("010078"), app="sleepfunction", layout="6BRM")
    assert receive.alarm_capable
    receive.feed(bytes.fromhex("6e0e00037e"), app="sleepfunction", layout="6BRM")
    assert not receive.light_capable
    receive.feed(bytes.fromhex("6e0e00037f"), app="sleepfunction", layout="6BRM")
    assert receive.light_capable and receive.light_on_seen
    receive.feed(bytes.fromhex("0011223344"), app="sleepfunction", layout="6BRM")
    assert receive.buffer == ""


async def test_source_direct_settings_and_foot_fan_duplicate(clock):
    ctrl, target = controller()
    await ctrl.execute_settings(Settings("foot_fan", hours=2, speed=40))
    assert packets(target) == ["6e0101d949"] * 2
    target.client.write_gatt_char.reset_mock()
    ctrl._receive.aroma_capable = True
    await ctrl.execute_settings(
        Settings("aroma", mode_2_minutes=1, mode_3_minutes=1, pause_hours=2)
    )
    assert packets(target) == ["6e1b00018a", "6e1c00018b", "6e1d00028d"]


async def test_hold_mode_is_a_sending_switch_and_preserves_recall_and_save(clock):
    ctrl, target = controller("YFRM")
    switch = ctrl.controller_switch_specs[0]
    await switch.set_fn(ctrl, True)
    assert packets(target)[0] == "6e01002291"
    assert ctrl._selection.hold is True
    buttons = ctrl.controller_button_specs
    assert any(s.hold and s.key.startswith("sleepfunction_8_") for s in buttons)
    saves = [s for s in buttons if s.key.startswith("sleepfunction_10_")]
    assert saves and all(s.card.role.value == "save" and not s.hold for s in saves)


async def test_setup_and_reconfigure_offer_the_app_and_searchable_exact_layouts(hass):
    from unittest.mock import patch

    import voluptuous as vol

    from custom_components.adjustable_bed import const
    from custom_components.adjustable_bed.setup_questions import _classic_errors, _classic_layouts
    from tests.test_richmat_family_flow import answer, fields, setup_flow

    flow = setup_flow(hass, "6BRM-bed")
    form, _ = await answer(flow, "sleepfunction")
    assert form["step_id"] == "profile_questions"
    assert fields(form)[const.CONF_PRODUCT_TYPE].default is vol.UNDEFINED
    choices = _classic_layouts({const.CONF_PROTOCOL_VARIANT: "sleepfunction"})
    assert {"AORM", "FRRM", "U3RM", "GVRM", "YGRM"} <= set(choices)
    assert not set(EXCLUDED_LAYOUTS) & set(choices)
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions({const.CONF_PRODUCT_TYPE: "YGRM"})
    saved = finish.call_args.args[0]
    assert saved[const.CONF_PROTOCOL_VARIANT] == "sleepfunction"
    assert saved[const.CONF_PRODUCT_TYPE] == "YGRM"
    assert not _classic_errors(saved)


async def test_native_connection_entity_commands_and_set_alarm(
    hass, clock, mock_coordinator_connected, mock_bleak_client, monkeypatch
):
    from unittest.mock import patch

    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed import const, services
    from custom_components.adjustable_bed.button import ControllerActionButton, _button_entities_for
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from tests.test_richmat_classic_transport import Services, route

    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Bed",
        data={
            "address": "AA:BB:CC:DD:EE:71",
            "name": "Bed",
            "bed_type": const.BED_TYPE_RICHMAT_CLASSIC_APPS,
            "protocol_variant": "sleepfunction",
            "product_type": "O0RM",
            "ble_device_name": "TWRM-bed",
            "disable_angle_sensing": True,
            "connection_mode": "idle",
        },
    )
    entry.add_to_hass(hass)
    target = AdjustableBedCoordinator(hass, entry)
    mock_bleak_client.services = Services([route(0)])
    for service in mock_bleak_client.services:
        service.handle = 1
        for i, c in enumerate(service.characteristics, 1):
            c.descriptors = []
            c.handle = i
            c.service_uuid = service.uuid
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    try:
        await target.async_prime_offline_controller()
        assert await target.async_connect()
        ctrl = target.controller
        assert isinstance(ctrl, SleepFunctionController)
        assert ctrl._worker.tick_ms == 150  # Actual discovered name is Test Bed.

        def writes():
            return [
                call.args[1].hex() for call in mock_bleak_client.write_gatt_char.await_args_list
            ]

        assert writes() == ["6e02010071", "6e08010178", "6e0a000179", "6e1a000088"]
        mock_bleak_client.write_gatt_char.reset_mock()
        button = next(
            e
            for e in _button_entities_for(hass, target)
            if isinstance(e, ControllerActionButton) and e._spec.name == "M1"
        )
        button.hass = hass
        await button.async_press()
        assert writes() == ["6e01002e9d", "6e01006edd"]
        mock_bleak_client.write_gatt_char.reset_mock()
        await services.async_register_services(hass)
        with patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(target, "both")], []),
        ):
            await hass.services.async_call(
                const.DOMAIN,
                "set_alarm",
                {"device_id": "bed", "enabled": True, "time": "12:00:00", "wake_action": "zero_g"},
                blocking=True,
            )
        assert len(writes()) == 2 and writes()[0].startswith("6e05") and writes()[1][6:8] == "45"
    finally:
        await target.async_shutdown()


async def test_entity_callbacks_follow_reconnect_but_reject_changed_layout(clock):
    old, _ = controller()
    spec = next(s for s in old.controller_button_specs if s.key == "sleepfunction_1_0_53")
    current, target = controller()
    await spec.press_fn(current)
    assert packets(target)[0] == "6e01002493"
    other, target = controller("AORM")
    with raises_key("sleepfunction_control"):
        await spec.press_fn(other)
    assert not packets(target)


async def test_alarm_combines_only_current_layout_massage(clock):
    from datetime import datetime

    from custom_components.adjustable_bed.alarm import AlarmRequest

    ctrl, target = controller("O0RM")
    request = AlarmRequest(
        enabled=True,
        hour=0,
        minute=1,
        wake_action="zero_g",
        massage=True,
        massage_zone="both",
        reference_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    await ctrl.configure_alarm(request)
    assert packets(target)[-1][6:8] == "79"


async def test_changed_entry_route_blocks_command_and_cleanup(clock):
    ctrl, target = controller()
    target.entry.data = {**target.entry.data, "bed_type": "other"}
    with raises_key("sleepfunction_session"):
        await ctrl.execute_action(1)
    assert not packets(target)


async def test_raw_transport_never_accepts_a_stale_side_button(clock):
    framed, _ = controller("DHRM")
    node = next(c.node for c in framed._controls if c.short == "24")
    old = next(s for s in framed.controller_button_specs if s.key == f"sleepfunction_{node}_1_53")
    raw, target = controller("DHRM", "RAW")
    assert all("Left" not in s.name and "Right" not in s.name for s in raw.controller_button_specs)
    with raises_key("sleepfunction_control"):
        await old.press_fn(raw)
    assert not packets(target)
    current = next(
        s for s in raw.controller_button_specs if s.key == f"sleepfunction_{node}_0_53_raw"
    )
    await current.press_fn(raw)
    assert packets(target)[0] == "24"


async def test_light_off_keeps_selected_color_and_state_across_other_replies(clock):
    from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_RGB

    ctrl, target = controller()
    ctrl._receive.light_capable = True
    await ctrl.set_light_color((255, 0, 0))
    await ctrl.lights_off()
    assert packets(target)[-1] == "6e0cff00796e0d00007b"
    rgb_values = [
        u.value
        for call in target.handle_controller_state_updates.call_args_list
        for u in call.args
        if u.key == UNDER_BED_LIGHTS_RGB
    ]
    assert rgb_values == [(255, 0, 0)]
    ctrl._notification(ctrl._session, ctrl._session.notify, bytearray.fromhex("6e09010078"))
    assert ctrl._light_on is False


async def test_actual_empty_name_does_not_reuse_cached_timing(monkeypatch):
    from custom_components.adjustable_bed.beds.richmat_classic import sleepfunction

    ctrl, target = controller(wire="RAW")
    ctrl._device_name = ""
    monkeypatch.setattr(sleepfunction, "select", lambda *a, **k: ctrl._session)
    with raises_key("sleepfunction_session"):
        await ctrl.start_notify()
    assert not packets(target)


@pytest.mark.parametrize("layout", ["F4RM", "FGRM", "FMRM", "FNRM"])
async def test_media_resource_is_never_an_executable_bed_control(clock, layout):
    ctrl, target = controller(layout)
    node = next(
        c.node
        for c in ctrl._controls
        if c.resource_keys.get("press_short") == "@string/k_start_pause"
    )
    with raises_key("sleepfunction_control"):
        await ctrl.execute_action(node)
    assert not any(s.key.startswith(f"sleepfunction_{node}_") for s in ctrl.controller_button_specs)
    assert not packets(target)


async def test_raw_callback_cannot_become_a_framed_side_after_reconnect(clock):
    raw, _ = controller("DHRM", "RAW")
    spec = next(s for s in raw.controller_button_specs if s.key == "sleepfunction_5_0_53_raw")
    framed, target = controller("DHRM")
    with raises_key("sleepfunction_control"):
        await spec.press_fn(framed)
    assert not packets(target)


def test_scoped_card_actions_never_share_a_motor_or_memory_slot():
    from custom_components.adjustable_bed.card import CardSection

    for layout, model in load_catalog("sleepfunction").models.items():
        if len(model.modes) < 2:
            continue
        ctrl, _ = controller(layout)
        for spec in ctrl.controller_button_specs:
            if spec.release_only:
                continue
            assert spec.card.section not in (CardSection.MOTORS, CardSection.MEMORY), (layout, spec)
            assert spec.card.motor is None and spec.card.slot is None


@pytest.mark.parametrize(
    "layout,node,long,frame", [("DHRM", 21, False, "6e01013cac"), ("CZRM", 15, True, "6e010075e4")]
)
async def test_led_discovery_retains_scoped_and_long_light_gestures(
    clock, layout, node, long, frame
):
    ctrl, target = controller(layout)
    ctrl._receive.light_capable = True
    key = f"sleepfunction_{node}_{1 if layout == 'DHRM' else 0}_53" + ("_long" if long else "")
    spec = next(s for s in ctrl.controller_button_specs if s.key == key)
    await spec.press_fn(ctrl)
    assert packets(target)[0] == frame


async def test_stop_attempts_remaining_modes_after_a_write_failure(clock):
    ctrl, target = controller("DHRM")
    error = OSError("first END failed")
    target.client.write_gatt_char.side_effect = [error, None]
    with pytest.raises(OSError, match="first END failed"):
        await ctrl.stop_all()
    assert packets(target) == ["6e01006edd", "6e01016ede"]


async def test_cancellation_inside_end_write_does_not_repeat_end(clock):
    ctrl, target = controller()
    ending = asyncio.Event()
    proceed = asyncio.Event()

    async def write(_char, packet, **_kwargs):
        if packet.hex() == "6e01006edd":
            ending.set()
            await proceed.wait()

    target.client.write_gatt_char.side_effect = write
    action = asyncio.create_task(ctrl.execute_action(1, hold_ms=150))
    await ending.wait()
    action.cancel()
    proceed.set()
    with pytest.raises(asyncio.CancelledError):
        await action
    assert packets(target).count("6e01006edd") == 1


async def test_countdown_uses_write_time_and_rejects_unencodable_day(clock, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from custom_components.adjustable_bed.alarm import AlarmRequest
    from custom_components.adjustable_bed.beds.richmat_classic import sleepfunction

    ctrl, target = controller("O0RM")
    request = AlarmRequest(
        enabled=True,
        hour=0,
        minute=10,
        wake_action="zero_g",
        reference_time=datetime(2026, 1, 1, tzinfo=UTC),
    )
    monkeypatch.setattr(
        sleepfunction.dt_util, "now", lambda: datetime(2026, 1, 1, 0, 2, tzinfo=UTC)
    )
    await ctrl.configure_alarm(request)
    assert packets(target)[0] == "6e0508007b"  # Eight minutes, not the queued ten.
    dst = AlarmRequest(
        enabled=True,
        hour=23,
        minute=59,
        wake_action="zero_g",
        reference_time=datetime(2026, 10, 25, tzinfo=ZoneInfo("Europe/Oslo")),
    )
    assert dst.minutes_until() == 1499
    with raises_key("sleepfunction_control"):
        ctrl.validate_alarm(dst)


def test_flat_sleep_is_selectable_in_the_native_alarm_action():
    from pathlib import Path

    import yaml

    data = yaml.safe_load(
        (Path(__file__).parents[1] / "custom_components/adjustable_bed/services.yaml").read_text()
    )
    assert (
        "flat_sleep" in data["set_alarm"]["fields"]["wake_action"]["selector"]["select"]["options"]
    )


async def test_oversized_notification_cannot_replay_an_old_light_event(clock):
    ctrl, target = controller()
    ctrl._notification(ctrl._session, ctrl._session.notify, bytearray.fromhex("6e0e00037f"))
    await ctrl.lights_off()
    assert ctrl._light_on is False
    ctrl._notification(ctrl._session, ctrl._session.notify, bytearray(300))
    assert ctrl._light_on is False and ctrl._receive.value_event is None


@pytest.mark.parametrize("layout", ["YFRM", "DHRM"])
async def test_native_platform_discovers_hold_saves_and_raw_routes(hass, clock, layout):
    from homeassistant.const import Platform

    from custom_components.adjustable_bed import const
    from custom_components.adjustable_bed.button import ControllerActionButton
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from tests.test_entity_sweep import _entry, async_setup_platforms_and_sweep

    entry = _entry(
        hass,
        bed_type=const.BED_TYPE_RICHMAT_CLASSIC_APPS,
        protocol_variant="sleepfunction",
        product_type=layout,
    )
    target = AdjustableBedCoordinator(hass, entry)
    try:
        await target.async_prime_offline_controller()
        ctrl = target.capability_controller
        assert isinstance(ctrl, SleepFunctionController)
        created = await async_setup_platforms_and_sweep(hass, entry, target, (Platform.BUTTON,))

        def keys():
            return {e._spec.key for e in created if isinstance(e, ControllerActionButton)}

        before = keys()
        if layout == "YFRM":
            # Attach the primed profile to a fake live native link, then use the
            # switch callback through its delivery boundary.
            _, mock = controller(layout)
            target._controller = ctrl
            mock.client.disconnect = AsyncMock(return_value=True)
            target._client = mock.client
            ctrl._session = Transport(
                mock.client,
                mock.controller._session.write,
                mock.controller._session.notify,
                "FRAMED",
            )
            ctrl._wire = "FRAMED"
            switch = next(
                s
                for s in ctrl.controller_switch_specs
                if s.translation_placeholders == {"action": "Continuous movement"}
            )
            await switch.set_fn(ctrl, True)
            assert "sleepfunction_10_0_53" not in before
            assert "sleepfunction_10_0_53" in keys()
        else:
            ctrl._wire = "RAW"
            ctrl._publish()
            assert not any(k.endswith("_raw") for k in before)
            assert any(k.endswith("_raw") for k in keys())
    finally:
        await target.async_shutdown()


@pytest.mark.parametrize("layout,node", [("FGRM", 1), ("FMRM", 2), ("FNRM", 5)])
async def test_media_short_gesture_does_not_hide_its_native_long_lock(clock, layout, node):
    ctrl, target = controller(layout)
    with raises_key("sleepfunction_control"):
        await ctrl.execute_action(node)
    spec = next(
        s for s in ctrl.controller_button_specs if s.key == f"sleepfunction_{node}_0_53_long"
    )
    await spec.press_fn(ctrl)
    assert "6e010084f3" in packets(target)
    assert not any(p[6:8] == "d9" for p in packets(target))


async def test_delivered_hold_survives_native_offline_controller_rebuild(hass, clock):
    from custom_components.adjustable_bed import const
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from tests.test_entity_sweep import _entry

    entry = _entry(
        hass,
        bed_type=const.BED_TYPE_RICHMAT_CLASSIC_APPS,
        protocol_variant="sleepfunction",
        product_type="YFRM",
    )
    first = AdjustableBedCoordinator(hass, entry)
    second = AdjustableBedCoordinator(hass, entry)
    try:
        await first.async_prime_offline_controller()
        ctrl = first.capability_controller
        assert isinstance(ctrl, SleepFunctionController)
        _, mock = controller("YFRM")
        mock.client.disconnect = AsyncMock(return_value=True)
        first._controller, first._client = ctrl, mock.client
        ctrl._session = Transport(
            mock.client, mock.controller._session.write, mock.controller._session.notify, "FRAMED"
        )
        ctrl._wire = "FRAMED"
        switch = next(
            s
            for s in ctrl.controller_switch_specs
            if s.translation_placeholders == {"action": "Continuous movement"}
        )
        await switch.set_fn(ctrl, True)
        saved = next(s for s in ctrl.controller_button_specs if s.key == "sleepfunction_10_0_53")
        writes = list(packets(mock))
        await second.async_prime_offline_controller()
        rebuilt = second.capability_controller
        assert isinstance(rebuilt, SleepFunctionController)
        assert rebuilt.persisted_app_state["hold"] is True
        assert packets(mock) == writes  # Restore never replays the Hold command.
        second._controller, second._client = rebuilt, mock.client
        rebuilt._session = ctrl._session
        rebuilt._wire = "FRAMED"
        await saved.press_fn(rebuilt)
        assert packets(mock)[len(writes)] == "6e01002b9a"
    finally:
        await first.async_shutdown()
        await second.async_shutdown()


async def test_last_stop_mode_lost_during_delay_records_partial_delivery(clock, monkeypatch):
    from custom_components.adjustable_bed.beds.richmat_classic import sleepfunction
    from custom_components.adjustable_bed.command_scheduler import Delivery, delivered

    ctrl, target = controller("DHRM")
    original_sleep = asyncio.sleep

    async def sleep(seconds):
        if packets(target):
            target.controller = MagicMock()
        await original_sleep(0)

    monkeypatch.setattr(sleepfunction.asyncio, "sleep", sleep)
    scheduler = DeviceCommandScheduler("sleepfunction")
    shown = []

    async def stop(context):
        target.cancel_command = context.cancel_event
        with delivered(shown.append):
            await ctrl.stop_all()

    await scheduler.admit_stop(stop)
    assert packets(target) == ["6e01006edd"]
    assert shown == [Delivery.PARTIAL]
    await scheduler.async_shutdown()


def test_picker_screens_offer_their_children_and_cannot_finish_setup():
    from custom_components.adjustable_bed import const
    from custom_components.adjustable_bed.setup_questions import _classic_errors, _classic_layouts

    data = {const.CONF_PROTOCOL_VARIANT: "sleepfunction"}
    choices = _classic_layouts(data)
    assert not set(PICKER_LAYOUTS) & set(choices)
    assert {"B8TT", "B9TT", "ZRI0", "I4RM", "I5RM", "D7RM", "ZR00", "ZR01", "APRM", "AQRM"} <= set(
        choices
    )
    for layout in PICKER_LAYOUTS:
        assert _classic_errors({**data, const.CONF_PRODUCT_TYPE: layout})
        with raises_key("sleepfunction_layout"):
            controller(layout)


async def test_aroma_preflight_waits_for_its_current_session_reply(clock):
    ctrl, target = controller()
    request = Settings("aroma", mode_2_minutes=1, mode_3_minutes=1, pause_hours=1)
    task = asyncio.create_task(ctrl.check_settings(request))
    await asyncio.sleep(0)
    assert not task.done()
    ctrl._notification(ctrl._session, ctrl._session.notify, bytearray.fromhex("6e1a000189"))
    await task
    assert not packets(target)


async def test_aroma_wait_is_bounded_and_cannot_cross_owner_or_cancel(clock, monkeypatch):
    from custom_components.adjustable_bed.beds.richmat_classic import sleepfunction

    ctrl, target = controller()
    request = Settings("aroma", mode_2_minutes=1, mode_3_minutes=1, pause_hours=1)
    monkeypatch.setattr(sleepfunction, "SETTINGS_REPLY_TIMEOUT", 0)
    with raises_key("sleepfunction_control"):
        await ctrl.check_settings(request)
    monkeypatch.setattr(sleepfunction, "SETTINGS_REPLY_TIMEOUT", 2)
    task = asyncio.create_task(ctrl.check_settings(request))
    await asyncio.sleep(0)
    target.controller = MagicMock()
    ctrl.on_disconnect()
    with raises_key("sleepfunction_session"):
        await task
    ctrl, target = controller()
    target.cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await ctrl.check_settings(request)
    assert not packets(target)


@pytest.mark.parametrize("operation", ["alarm", "head_fan", "aroma"])
@pytest.mark.parametrize("task_cancel", [False, True])
async def test_pending_settings_frames_are_partial_on_both_gap_cancellations(
    clock, operation, task_cancel
):
    from datetime import datetime

    from custom_components.adjustable_bed.alarm import AlarmRequest
    from custom_components.adjustable_bed.command_scheduler import Delivery, delivered

    ctrl, target = controller("O0RM")
    ctrl._receive.aroma_capable = True
    gap = asyncio.Event()
    shown = []

    async def wait(_ms, _cancel):
        gap.set()
        if task_cancel:
            current = asyncio.current_task()
            assert current is not None
            current.cancel()
            await asyncio.sleep(0)
        return False  # Controller-local interruption, scheduler event stays clear.

    ctrl._wait = wait
    scheduler = DeviceCommandScheduler("sleepfunction")

    async def action(context):
        target.cancel_command = context.cancel_event
        with delivered(shown.append):
            if operation == "alarm":
                await ctrl.configure_alarm(
                    AlarmRequest(
                        enabled=True,
                        hour=0,
                        minute=10,
                        wake_action="zero_g",
                        reference_time=datetime(2026, 1, 1, tzinfo=UTC),
                    )
                )
            elif operation == "aroma":
                await ctrl.execute_settings(
                    Settings("aroma", mode_2_minutes=1, mode_3_minutes=1, pause_hours=1)
                )
            else:
                await ctrl.execute_settings(Settings("head_fan", hours=1, speed=20))

    task = asyncio.create_task(scheduler.execute(CommandIntent(operation=action)))
    await gap.wait()
    await asyncio.gather(task, return_exceptions=True)
    assert len(packets(target)) == 1
    assert shown == [Delivery.PARTIAL]
    await scheduler.async_shutdown()


async def _native_settings_target(hass, suffix):
    from custom_components.adjustable_bed import const
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from tests.test_entity_sweep import _entry

    entry = _entry(
        hass,
        address=f"AA:BB:CC:DD:EE:{suffix:02X}",
        bed_type=const.BED_TYPE_RICHMAT_CLASSIC_APPS,
        protocol_variant="sleepfunction",
        product_type="O0RM",
        connection_mode=const.CONNECTION_MODE_RELEASE,
    )
    target = AdjustableBedCoordinator(hass, entry)
    await target.async_prime_offline_controller()
    ctrl = target.capability_controller
    assert isinstance(ctrl, SleepFunctionController)
    _, mock = controller("O0RM")
    mock.client.disconnect = AsyncMock(return_value=True)

    async def disconnect():
        mock.client.is_connected = False
        return True

    mock.client.disconnect = AsyncMock(side_effect=disconnect)
    target._controller, target._client = ctrl, mock.client
    target._disconnect_after_command = True
    ctrl._session = Transport(
        mock.client, mock.controller._session.write, mock.controller._session.notify, "FRAMED"
    )
    ctrl._wire = "FRAMED"
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = target
    return target, ctrl, mock


async def test_aroma_service_retains_early_release_links_through_delayed_later_check(hass):
    from unittest.mock import patch

    from custom_components.adjustable_bed import const, services
    from tests.hold_lease_wire import virtual_clock

    first, early, early_mock = await _native_settings_target(hass, 0x81)
    second, later, later_mock = await _native_settings_target(hass, 0x82)
    early._receive.aroma_capable = True
    try:
        await services.async_register_services(hass)
        with (
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(first, "both"), (second, "both")], []),
            ),
            virtual_clock() as time,
            patch.object(hass, "loop", asyncio.get_running_loop()),
        ):
            original = early._session

            async def reply():
                await asyncio.sleep(1.2)
                later._notification(
                    later._session, later._session.notify, bytearray.fromhex("6e1a000189")
                )

            response = asyncio.create_task(reply())
            await hass.services.async_call(
                const.DOMAIN,
                "sleepfunction_settings",
                {
                    "device_id": ["beds"],
                    "operation": "aroma",
                    "mode_2_minutes": 1,
                    "mode_3_minutes": 1,
                    "pause_hours": 1,
                },
                blocking=True,
            )
            await response
            assert time.elapsed >= 2.09
            assert first.is_connected and second.is_connected
            assert early._session is original
            expected = ["6e1b00018a", "6e1c00018b", "6e1d00018c"]
            assert packets(early_mock) == packets(later_mock) == expected
            assert first._command_connection_holds == second._command_connection_holds == 0
            assert first._disconnect_timer is not None and second._disconnect_timer is not None
    finally:
        await first.async_shutdown()
        await second.async_shutdown()


async def test_settings_service_cannot_reuse_a_changed_checked_session(hass, clock):
    from unittest.mock import patch

    from custom_components.adjustable_bed import const, services

    first, early, early_mock = await _native_settings_target(hass, 0x83)
    second, later, later_mock = await _native_settings_target(hass, 0x84)
    early._receive.aroma_capable = later._receive.aroma_capable = True
    original_check = later.check_settings

    async def changed(request):
        proof = await original_check(request)
        old = early._session
        early._session = Transport(old.client, old.write, old.notify, old.wire)
        return proof

    later.check_settings = changed
    try:
        await services.async_register_services(hass)
        with (
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(first, "both"), (second, "both")], []),
            ),
            raises_key("sleepfunction_session"),
        ):
            await hass.services.async_call(
                const.DOMAIN,
                "sleepfunction_settings",
                {
                    "device_id": ["beds"],
                    "operation": "aroma",
                    "mode_2_minutes": 1,
                    "mode_3_minutes": 1,
                    "pause_hours": 1,
                },
                blocking=True,
            )
        assert not packets(early_mock) and not packets(later_mock)
        assert first._command_connection_holds == second._command_connection_holds == 0
    finally:
        await first.async_shutdown()
        await second.async_shutdown()


async def test_native_fan_action_accepts_exact_float_percentage(hass, clock):
    from unittest.mock import patch

    from custom_components.adjustable_bed import const, services

    target, ctrl, mock = await _native_settings_target(hass, 0x85)
    try:
        await services.async_register_services(hass)
        with patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(target, "both")], []),
        ):
            await hass.services.async_call(
                const.DOMAIN,
                "sleepfunction_settings",
                {"device_id": "bed", "operation": "head_fan", "hours": 1, "speed": 40.0},
                blocking=True,
            )
        assert packets(mock) == ["6e01d10040", "6e01d90048"]
        import voluptuous as vol

        from custom_components.adjustable_bed.beds.richmat_classic.sleepfunction_services import (
            FIELDS,
        )

        with pytest.raises(vol.Invalid):
            vol.Schema(FIELDS)(
                {"device_id": "bed", "operation": "head_fan", "hours": 1, "speed": 40.5}
            )
    finally:
        await target.async_shutdown()


async def test_aroma_preflight_failure_releases_every_held_link_without_settings_writes(
    hass, monkeypatch
):
    from unittest.mock import patch

    from custom_components.adjustable_bed import const, services
    from custom_components.adjustable_bed.beds.richmat_classic import sleepfunction
    from tests.hold_lease_wire import virtual_clock

    first, early, early_mock = await _native_settings_target(hass, 0x86)
    second, later, later_mock = await _native_settings_target(hass, 0x87)
    early._receive.aroma_capable = True
    monkeypatch.setattr(sleepfunction, "SETTINGS_REPLY_TIMEOUT", 0.01)
    try:
        await services.async_register_services(hass)
        with (
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(first, "both"), (second, "both")], []),
            ),
            virtual_clock(),
            patch.object(hass, "loop", asyncio.get_running_loop()),
        ):
            with raises_key("sleepfunction_control"):
                await hass.services.async_call(
                    const.DOMAIN,
                    "sleepfunction_settings",
                    {
                        "device_id": ["beds"],
                        "operation": "aroma",
                        "mode_2_minutes": 1,
                        "mode_3_minutes": 1,
                        "pause_hours": 1,
                    },
                    blocking=True,
                )
            assert not packets(early_mock) and not packets(later_mock)
            assert first._command_connection_holds == second._command_connection_holds == 0
            assert first._disconnect_timer is not None and second._disconnect_timer is not None
    finally:
        await first.async_shutdown()
        await second.async_shutdown()


@pytest.mark.parametrize("value", [False, True, 40.5])
async def test_fan_action_rejects_non_percentage_inputs_before_writes(hass, clock, value):
    from unittest.mock import patch

    import voluptuous as vol

    from custom_components.adjustable_bed import const, services

    target, ctrl, mock = await _native_settings_target(hass, 0x88)
    try:
        await services.async_register_services(hass)
        with (
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(target, "both")], []),
            ),
            pytest.raises(vol.Invalid),
        ):
            await hass.services.async_call(
                const.DOMAIN,
                "sleepfunction_settings",
                {"device_id": "bed", "operation": "head_fan", "hours": 1, "speed": value},
                blocking=True,
            )
        assert not packets(mock)
    finally:
        await target.async_shutdown()


@pytest.mark.parametrize("mode", ["concurrent", "sequential"])
async def test_a_skipped_pair_preflight_blocks_all_targets_before_any_settings_write(
    hass, clock, mode
):
    from unittest.mock import patch

    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed import const, services
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    first, early, early_mock = await _native_settings_target(hass, 0x89)
    left, lc, lm = await _native_settings_target(hass, 0x8A)
    right, rc, rm = await _native_settings_target(hass, 0x8B)
    entry = MockConfigEntry(domain=const.DOMAIN, data={"pair_id": "sleepfunction-settings"})
    entry.add_to_hass(hass)
    parent = PairedBedCoordinator(hass, entry, {"left": left, "right": right}, connection_mode=mode)
    try:
        await services.async_register_services(hass)
        # The native pair API may return without invoking a stale queued
        # wildcard query. A successful standalone check must not permit writes.
        with (
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(first, "both"), (parent, "both")], []),
            ),
            patch.object(parent, "async_run_child_operation", new=AsyncMock(return_value=None)),
            raises_key("action_stopped"),
        ):
            await hass.services.async_call(
                const.DOMAIN,
                "sleepfunction_settings",
                {"device_id": ["beds"], "operation": "head_fan", "hours": 1, "speed": 40},
                blocking=True,
            )
        assert not packets(early_mock) and not packets(lm) and not packets(rm)
        assert (
            first._command_connection_holds
            == left._command_connection_holds
            == right._command_connection_holds
            == 0
        )
    finally:
        await parent.async_shutdown()
        await first.async_shutdown()
        await left.async_shutdown()
        await right.async_shutdown()


async def test_sent_state_honors_the_shared_current_owner_predicate(clock):
    from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON

    ctrl, target = controller()
    ctrl.forward_controller_state_updates = MagicMock()
    with ctrl.sent_state(UNDER_BED_LIGHTS_ON(True), is_current=lambda: False):
        await ctrl.write_command(bytes.fromhex("6e0a000179"))
    assert packets(target) == ["6e0a000179"]
    assert ctrl._light_on is None
    ctrl.forward_controller_state_updates.assert_not_called()


async def test_massage_timer_is_the_shared_select_and_the_popup_has_no_off():
    from custom_components.adjustable_bed.beds.richmat_classic.protocol import (
        massage_popup,
        massage_timer,
    )
    from custom_components.adjustable_bed.state_keys import MASSAGE_TIMER_MINUTES

    ctrl, coordinator = controller("D1RM")
    assert ctrl.supports_massage_timer and ctrl.auto_enable_massage
    assert ctrl.massage_timer_options == [10, 20, 30] and ctrl.massage_timer_can_turn_off
    assert ctrl.controller_select_specs == ()
    # The slider's four stops, which the app labels 0, 2H, 3H and 5H.
    for minutes, progress in ((0, 0), (10, 2), (20, 3), (30, 5)):
        coordinator.client.write_gatt_char.reset_mock()
        await ctrl.set_massage_timer(minutes)
        assert packets(coordinator) == [massage_timer("D1RM", progress).hex()]
    # A later notification republishes state without clearing the chosen timer.
    coordinator.handle_controller_state_updates.reset_mock()
    ctrl._publish()
    assert not any(
        update.key == MASSAGE_TIMER_MINUTES
        for call in coordinator.handle_controller_state_updates.call_args_list
        for update in call.args
    )

    popup = next(
        layout
        for layout, model in load_catalog("sleepfunction").models.items()
        if layout not in EXCLUDED_LAYOUTS | PICKER_LAYOUTS | {"D1RM", "D9RM"}
        and any(c.tag == "65" for c in model.controls)
    )
    ctrl, coordinator = controller(popup)
    # The popup's artwork reads 10MIN, 20MIN and 30min.
    assert ctrl.massage_timer_options == [10, 20, 30] and not ctrl.massage_timer_can_turn_off
    await ctrl.set_massage_timer(20)
    assert packets(coordinator) == [massage_popup("30").hex()] == ["6e010063d2"]
    with raises_key("sleepfunction_control"):
        await ctrl.set_massage_timer(0)


async def test_a_nordic_connection_names_each_control_by_what_it_sends():
    framed, _ = controller("BERM", "FRAMED")
    node = next(c.node for c in framed._controls if c.label.endswith("ubl on off"))
    listed_for_framed = next(
        s for s in framed.controller_button_specs if s.key.startswith(f"sleepfunction_{node}_")
    )
    assert "light" in listed_for_framed.name.lower()

    ctrl, coordinator = controller("BERM", "RAW")
    # Over Nordic UART this layout's light control sends the legacy "motor 1+2 up" operand.
    spec = next(s for s in ctrl.controller_button_specs if s.key.startswith(f"sleepfunction_{node}_"))
    assert spec.key.endswith("_raw") and spec.name == "Head and foot up"
    assert not any("light" in s.name.lower() for s in ctrl.controller_button_specs)
    assert not ctrl.supports_light_toggle_control
    with raises_key("sleepfunction_control"):
        await listed_for_framed.press_fn(ctrl)
    assert packets(coordinator) == []
