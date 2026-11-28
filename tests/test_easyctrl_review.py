"""Public HA regressions for EasyCtrl's accepted implementation review S1–S8."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from bleak.exc import BleakError
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import config_flow, const
from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.easyctrl import controller as bed
from custom_components.adjustable_bed.codec import cheerssleep as carrier
from custom_components.adjustable_bed.codec import easyctrl as codec
from custom_components.adjustable_bed.profiles import easyctrl as app
from custom_components.adjustable_bed.runtime_data import loaded_runtime
from custom_components.adjustable_bed.setup_questions import _easyctrl_settings
from tests.hold_lease_wire import virtual_clock
from tests.test_config_flow import _patch_gate
from tests.test_easyctrl import make


@pytest.fixture(autouse=True)
def monotonic_clock(monkeypatch):
    monkeypatch.setattr(bed, "monotonic", lambda: asyncio.get_running_loop().time())


@pytest.mark.parametrize("failed", [(0,), (1,), (0, 1, 2)])
async def test_model300_stop_errors_do_not_abandon_remaining_schedule(failed):
    ctrl, c = make(300)
    await ctrl.start_notify()
    times, frames = [], []
    failures = [BleakError(f"STOP {i}") for i in range(3)]
    with virtual_clock():
        start = asyncio.get_running_loop().time()

        async def write(_char, frame, **_kw):
            i = len(frames)
            frames.append(frame.hex())
            times.append(round((asyncio.get_running_loop().time() - start) * 1000))
            if i in failed:
                raise failures[i]

        c.client.write_gatt_char.side_effect = write
        with pytest.raises(BleakError, match=f"STOP {failed[0]}"):
            await ctrl.stop_all()
    assert frames == ["0201010000000000", "0301010000000000", "0401010000000000"]
    assert times == [0, 20, 40]


async def test_primary_movement_error_survives_cleanup_errors():
    ctrl, c = make(300)
    await ctrl.start_notify()
    original = BleakError("primary movement failure")
    c.client.write_gatt_char.side_effect = [
        original,
        BleakError("stop 1"),
        BleakError("stop 2"),
        None,
    ]
    with virtual_clock(), pytest.raises(BleakError, match="primary movement failure") as caught:
        await ctrl.move_axis("all", False, 100)
    assert c.client.write_gatt_char.call_count == 4
    assert any("cleanup" in note for note in caught.value.__notes__)


async def test_failed_stop_on_replaced_session_never_writes_successor():
    ctrl, c = make(300)
    await ctrl.start_notify()
    old = c.client

    async def replace_link(*_a, **_kw):
        _, replacement = make(300)
        c.client = replacement.client
        ctrl.on_disconnect()
        await ctrl.start_notify()
        raise BleakError("failed before reconnect")

    old.write_gatt_char.side_effect = replace_link
    with virtual_clock(), pytest.raises(BleakError, match="before reconnect"):
        await ctrl.stop_all()
    assert old.write_gatt_char.call_count == 1
    c.client.write_gatt_char.assert_not_called()


@pytest.mark.parametrize(
    "problem", [None, "response_only", "wrong_service", "missing_notify", "notify_without_property"]
)
async def test_read_only_probe_and_finish_require_runtime_roles(hass, monkeypatch, problem):
    _, c = make()
    client = c.client
    write = client.services[0].get_characteristic(carrier.WRITE)
    notify = client.services[0].get_characteristic(carrier.NOTIFY)
    if problem == "response_only":
        write.properties = ["write"]
    elif problem == "wrong_service":
        client.services[0].uuid = "180a"
    elif problem == "missing_notify":
        client.services[0].get_characteristic.side_effect = lambda uuid: (
            write if uuid == carrier.WRITE else None
        )
    elif problem == "notify_without_property":
        notify.properties = ["read"]
    flow = config_flow.AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    monkeypatch.setattr(flow, "_verification_possible", lambda: True)
    monkeypatch.setattr(
        "bleak_retry_connector.establish_connection", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(config_flow, "discover_services", AsyncMock())
    read = AsyncMock()
    monkeypatch.setattr(config_flow, "read_ble_device_info", read)
    with _patch_gate("hci0", -55):
        progress = await flow._finish_with_verify(
            {
                "address": c.address,
                "bed_type": "easyctrl",
                "product_type": "100",
                "name": "EasyCtrl",
            },
            "EasyCtrl",
        )
        task = progress["progress_task"]
        assert task is not None
        await task
        await flow.async_step_setup_progress()
    report = flow._operation.result.payload
    assert report.easyctrl_transport_valid is (problem is None)
    await flow.async_step_verify_connection()
    result = await flow.async_step_verify_connection({"action": "finish"})
    if problem:
        assert result["step_id"] == "verify_connection"
        selector = next(iter(result["data_schema"].schema.values()))
        assert selector.config["options"] == ["retry", "change_app"]
        assert not flow._migration_verified
    else:
        assert result["type"] == "create_entry"
    read.assert_not_awaited()
    client.write_gatt_char.assert_not_awaited()
    client.start_notify.assert_not_awaited()
    client.disconnect.assert_awaited_once()


async def test_setup_retains_live_mismatch_through_inconclusive_retry(hass, monkeypatch):
    _, bad = make()
    _, good = make()
    bad.client.services[0].get_characteristic(carrier.WRITE).properties = ["write"]
    flow = config_flow.AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    monkeypatch.setattr(flow, "_verification_possible", lambda: True)
    monkeypatch.setattr(
        "bleak_retry_connector.establish_connection",
        AsyncMock(side_effect=[bad.client, TimeoutError(), good.client]),
    )
    monkeypatch.setattr(config_flow, "discover_services", AsyncMock())

    async def show(progress):
        await progress["progress_task"]
        await flow.async_step_setup_progress()
        return await flow.async_step_verify_connection()

    with _patch_gate("hci0", -55):
        progress = await flow._finish_with_verify(
            {"address": bad.address, "bed_type": "easyctrl", "product_type": "100"},
            "EasyCtrl",
        )
        await show(progress)
        for _ in range(2):
            rejected = await flow.async_step_verify_connection({"action": "finish"})
            assert rejected["type"] == "form"
            assert rejected["step_id"] == "verify_connection"
            selector = next(iter(rejected["data_schema"].schema.values()))
            assert selector.config["options"] == ["retry", "change_app"]
            progress = await flow.async_step_verify_connection({"action": "retry"})
            await show(progress)
        accepted = await flow.async_step_verify_connection({"action": "finish"})
    assert accepted["type"] == "create_entry"
    bad.client.write_gatt_char.assert_not_awaited()
    good.client.write_gatt_char.assert_not_awaited()


async def test_changing_app_cannot_skip_remembered_mismatch_without_scanner(
    hass, enable_custom_integrations, monkeypatch
):
    from homeassistant.data_entry_flow import InvalidData

    from tests.test_config_flow import _advance_progress, _discover, _settings_input

    _, bed = make()
    bed.client.services[0].get_characteristic(carrier.WRITE).properties = ["write"]
    scanner_available = True
    monkeypatch.setattr(
        config_flow.AdjustableBedConfigFlow,
        "_verification_possible", lambda _flow: scanner_available,
    )
    monkeypatch.setattr(config_flow, "discover_services", AsyncMock())
    connect = AsyncMock(return_value=bed.client)
    monkeypatch.setattr("bleak_retry_connector.establish_connection", connect)
    manager = hass.config_entries.flow
    result = await _discover(hass, "LIN2BLE 34", [const.LINAK_CONTROL_SERVICE_UUID])
    flow_id = result["flow_id"]

    async def submit(**fields):
        return await manager.async_configure(flow_id, fields)

    async def choose_easyctrl():
        result = await submit(bed_type="easyctrl")
        assert result["step_id"] == "profile_questions"
        result = await submit(product_type="100")
        assert result["step_id"] == "finish_settings"
        return await submit(**_settings_input(result, {"name": "EasyCtrl"}))

    assert result["step_id"] == "bluetooth_disambiguate"
    result = await submit(bed_type_choice="show_all")
    assert result["step_id"] == "select_app"
    with _patch_gate("hci0", -55):
        result = await _advance_progress(hass, await choose_easyctrl())
        assert result["step_id"] == "verify_connection"
        result = await submit(action="change_app")
        assert result["step_id"] == "select_app"
        scanner_available = False
        connect.side_effect = TimeoutError()
        result = await choose_easyctrl()
        assert result["type"] != "create_entry"
        result = await _advance_progress(hass, result)
        assert result["step_id"] == "verify_connection"
        selector = next(iter(result["data_schema"].schema.values()))
        assert selector.config["options"] == ["retry", "change_app"]
        with pytest.raises(InvalidData):
            await submit(action="finish")
    manager.async_abort(flow_id)
    bed.client.write_gatt_char.assert_not_awaited()


async def test_reconfigure_requires_exact_read_only_endpoint_check(hass):
    flow = config_flow.AdjustableBedConfigFlow()
    flow.hass = hass
    flow._manual_data = {"bed_type": "easyctrl"}
    assert flow._migration_requires_check
    _, c = make()
    c.client.services[0].get_characteristic(carrier.WRITE).properties = ["write"]
    with pytest.raises(HomeAssistantError):
        flow._migration_endpoint_check(c.client, {"bed_type": "easyctrl"})
    c.client.write_gatt_char.assert_not_awaited()
    c.client.start_notify.assert_not_awaited()


@pytest.fixture
async def ha_beds(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, monkeypatch
):
    entries = []

    async def add(key=100):
        _, transport = make(key)
        mock_bleak_client.services = transport.client.services
        mock_bleak_client.start_notify = AsyncMock()
        mock_bleak_client.stop_notify = AsyncMock()
        mock_bleak_client.write_gatt_char = AsyncMock()
        monkeypatch.setitem(app.MODELS, key, replace(app.MODELS[key], query_delay_ms=0))
        data = {
            "address": f"AA:BB:CC:DD:EE:{len(entries) + 1:02X}",
            "name": f"EasyCtrl {len(entries)}",
            "bed_type": "easyctrl",
            "product_type": str(key),
            "disable_angle_sensing": True,
            "connection_mode": "idle",
            "motor_pulse_count": 1,
        }
        data.update(_easyctrl_settings(data))
        entry = MockConfigEntry(
            domain=const.DOMAIN, version=5, unique_id=data["address"], data=data
        )
        entry.add_to_hass(hass)
        entries.append(entry)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        runtime = loaded_runtime(hass, entry.entry_id)
        rows = [
            row
            for row in er.async_get(hass).entities.values()
            if row.config_entry_id == entry.entry_id
        ]
        device = next(row.device_id for row in rows if row.device_id)
        return SimpleNamespace(
            runtime=runtime,
            ctrl=runtime.controller,
            rows=rows,
            device=device,
            client=mock_bleak_client,
        )

    yield add
    for entry in entries:
        await hass.config_entries.async_unload(entry.entry_id)


def entity(target, suffix, domain):
    return next(
        row.entity_id
        for row in target.rows
        if row.domain == domain and row.unique_id.endswith(suffix)
    )


def codes(target):
    return [
        (int.from_bytes(call.args[1][2:4], "little"), int.from_bytes(call.args[1][4:], "little"))
        for call in target.client.write_gatt_char.call_args_list
    ]


async def test_public_massage_timer_uses_selected_zone_and_per_zone_history(hass, ha_beds):
    target = await ha_beds()

    async def select(zone, mode):
        await hass.services.async_call(
            "select",
            "select_option",
            {
                "entity_id": entity(target, f"easyctrl_{zone}_mode", "select"),
                "option": f"mode_{mode}",
            },
            blocking=True,
        )

    with virtual_clock():
        await select("head", 2)
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": entity(target, "easyctrl_head_power", "number"), "value": 2},
            blocking=True,
        )
        target.client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity(target, "massage_timer", "select"), "option": "20 min"},
            blocking=True,
        )
        assert codes(target) == [(0x202, 1200), (0x211, 8)]
        await select("foot", 3)
        await hass.async_block_till_done()
        assert hass.states.get(entity(target, "easyctrl_head_mode", "select")).state == "off"
        assert hass.states.get(entity(target, "easyctrl_all_mode", "select")).state == "off"
        assert hass.states.get(entity(target, "easyctrl_foot_mode", "select")).state == "mode_3"
        assert target.ctrl.local.minutes == {"head": 20, "all": 10, "foot": 10}
        target.client.write_gatt_char.reset_mock()
        await select("head", 2)
        assert codes(target) == [(0x202, 1200), (0x211, 8)]


async def test_public_hold_all_target_duration_preflight_has_zero_writes(
    hass, ha_beds, monkeypatch
):
    first, second = await ha_beds(), await ha_beds(300)

    async def long_hold(_control, _duration):
        await first.ctrl._control(0x101)

    first_hold = AsyncMock(side_effect=long_hold)
    monkeypatch.setattr(first.ctrl, "validate_hold_control", lambda *_: None)
    monkeypatch.setattr(first.ctrl, "hold_control", first_hold)
    first.client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            const.DOMAIN,
            "hold_control",
            {"device_id": [first.device, second.device], "control": "all_up", "duration": 31},
            blocking=True,
        )
    first_hold.assert_not_awaited()
    first.client.write_gatt_char.assert_not_awaited()
    second.client.write_gatt_char.assert_not_awaited()


# One real HA target for every group key missing from the old global vocabulary.
_OLD_MOTORS = set(const.TIMED_MOVE_MOTOR_OPTIONS)
_GROUP_MODELS = {}
for _key, _profile in app.MODELS.items():
    for _axis in _profile.axes:
        if _axis.key not in _OLD_MOTORS:
            _GROUP_MODELS.setdefault(_axis.key, _key)


@pytest.mark.parametrize("group,key", _GROUP_MODELS.items())
async def test_public_timed_move_accepts_each_declared_group(hass, ha_beds, group, key):
    target = await ha_beds(key)
    target.client.write_gatt_char.reset_mock()
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN,
            "timed_move",
            {"device_id": target.device, "motor": group, "direction": "up", "duration_ms": 100},
            blocking=True,
        )
    axis = target.ctrl.profile.axis(group)
    assert codes(target)[0] == (axis.up, 0)
    assert codes(target)[-1] == (axis.stop, 0)
    cover = hass.states.get(entity(target, group, "cover"))
    assert cover.attributes["hold_lease_motor"] == group
    assert cover.attributes["held_stop_scope"] == "side"


async def test_public_timed_group_preflight_rejects_other_profile_before_any_write(hass, ha_beds):
    first, second = await ha_beds(1091), await ha_beds(100)
    first.client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            const.DOMAIN,
            "timed_move",
            {
                "device_id": [first.device, second.device],
                "motor": "seat_1",
                "direction": "up",
                "duration_ms": 100,
            },
            blocking=True,
        )
    first.client.write_gatt_char.assert_not_awaited()
    second.client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("operation", ["rgb", "mode", "power"])
async def test_public_cancel_before_write_keeps_settings_and_ha_state(
    hass, ha_beds, operation, monkeypatch
):
    target = await ha_beds()
    ctrl = target.ctrl
    initial = (
        ctrl.local.rgb,
        ctrl.local.brightness,
        ctrl.local.packed,
        dict(ctrl.local.modes),
        dict(ctrl.local.powers),
        dict(ctrl.local.minutes),
        ctrl.local.zone,
    )
    if operation == "rgb":
        domain, service, data = (
            "light",
            "turn_on",
            {
                "entity_id": entity(target, "under_bed_lights", "light"),
                "rgb_color": [17, 34, 51],
                "brightness": 68,
            },
        )
    elif operation == "mode":
        domain, service, data = (
            "select",
            "select_option",
            {"entity_id": entity(target, "easyctrl_head_mode", "select"), "option": "mode_2"},
        )
    else:
        domain, service, data = (
            "number",
            "set_value",
            {"entity_id": entity(target, "easyctrl_head_power", "number"), "value": 3},
        )
    previous = hass.states.get(data["entity_id"]).state
    active_events = []
    control = ctrl._control

    async def capture(*args, **kwargs):
        active_events.append(target.runtime.cancel_command)
        await control(*args, **kwargs)

    monkeypatch.setattr(ctrl, "_control", capture)
    before = ctrl.local.counters.sequence
    await ctrl._ble_lock.acquire()
    task = asyncio.create_task(hass.services.async_call(domain, service, data, blocking=True))
    try:
        for _ in range(200):
            await asyncio.sleep(0)
            if ctrl.local.counters.sequence != before:
                break
        assert ctrl.local.counters.sequence != before
        active_events[0].set()
    finally:
        ctrl._ble_lock.release()
    await asyncio.gather(task, return_exceptions=True)
    await hass.async_block_till_done()
    assert (
        ctrl.local.rgb,
        ctrl.local.brightness,
        ctrl.local.packed,
        ctrl.local.modes,
        ctrl.local.powers,
        ctrl.local.minutes,
        ctrl.local.zone,
    ) == initial
    assert hass.states.get(data["entity_id"]).state == previous
    target.client.write_gatt_char.assert_not_awaited()
    target.runtime.cancel_command.clear()
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": entity(target, "under_bed_lights", "light")},
        blocking=True,
    )
    assert codes(target)[0] == (0x501, 0xFFFFFF80)


async def test_public_partial_massage_delivery_commits_mode_but_not_failed_strength(hass, ha_beds):
    target = await ha_beds()
    target.ctrl.local.powers["head"] = 2
    target.client.write_gatt_char.side_effect = [None, BleakError("strength failed")]
    with virtual_clock(), pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity(target, "easyctrl_head_mode", "select"), "option": "mode_2"},
            blocking=True,
        )
    await hass.async_block_till_done()
    assert target.ctrl.local.modes["head"] == 2
    assert target.ctrl.local.zone == "head"
    assert target.ctrl.local.powers["head"] == 2
    assert hass.states.get(entity(target, "easyctrl_head_mode", "select")).state == "mode_2"
    assert hass.states.get(entity(target, "easyctrl_all_mode", "select")).state == "off"
    assert hass.states.get(entity(target, "easyctrl_head_power", "number")).state == "unknown"


@pytest.mark.parametrize("operation", ["rgb", "mode", "power"])
async def test_public_failed_write_keeps_settings(hass, ha_beds, operation):
    target = await ha_beds()
    ctrl = target.ctrl
    before = (
        ctrl.local.rgb,
        ctrl.local.brightness,
        dict(ctrl.local.modes),
        dict(ctrl.local.powers),
        ctrl.local.zone,
    )
    target.client.write_gatt_char.side_effect = BleakError("not sent")
    domain, service, data = {
        "rgb": (
            "light",
            "turn_on",
            {
                "entity_id": entity(target, "under_bed_lights", "light"),
                "rgb_color": [17, 34, 51],
                "brightness": 68,
            },
        ),
        "mode": (
            "select",
            "select_option",
            {"entity_id": entity(target, "easyctrl_head_mode", "select"), "option": "mode_3"},
        ),
        "power": (
            "number",
            "set_value",
            {"entity_id": entity(target, "easyctrl_head_power", "number"), "value": 3},
        ),
    }[operation]
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(domain, service, data, blocking=True)
    assert (
        ctrl.local.rgb,
        ctrl.local.brightness,
        ctrl.local.modes,
        ctrl.local.powers,
        ctrl.local.zone,
    ) == before


@pytest.mark.parametrize(
    "now,hour,minute,seconds,mask",
    [
        (datetime(2026, 3, 29, 1, 30), 3, 30, 3600, 1),
        (datetime(2026, 3, 29, 1, 30), 2, 30, 3600, 1),
        (datetime(2026, 10, 25, 2, 30, fold=0), 3, 30, 7200, 1),
        (datetime(2026, 10, 25, 2, 30, fold=1), 3, 30, 3600, 1),
        (datetime(2026, 10, 25, 2, 30, fold=0), 2, 15, 2700, 1),
        (datetime(2026, 10, 25, 2, 30, fold=1), 2, 15, 85500, 0x40),
    ],
)
async def test_dst_elapsed_countdown_and_relative_day_mask(now, hour, minute, seconds, mask):
    aware = now.replace(tzinfo=ZoneInfo("Europe/Oslo"))
    assert codec.alarm_values(hour, minute, (6,), aware) == (seconds, mask)
    ctrl, c = make()
    await ctrl.start_notify()
    with virtual_clock():
        await ctrl.configure_alarm(
            AlarmRequest(
                enabled=True, hour=hour, minute=minute, weekdays=(6,), reference_time=aware
            )
        )
    assert (
        int.from_bytes(c.client.write_gatt_char.call_args_list[0].args[1][4:], "little") == seconds
    )
    assert int.from_bytes(c.client.write_gatt_char.call_args_list[1].args[1][4:], "little") == mask << 8


@pytest.mark.parametrize("valid", [False, True])
async def test_actual_reconfigure_cannot_apply_a_live_endpoint_mismatch(
    hass, enable_custom_integrations, monkeypatch, valid
):
    from homeassistant.config_entries import SOURCE_RECONFIGURE

    from tests.test_config_flow import _advance_progress

    entry = MockConfigEntry(
        domain=const.DOMAIN,
        version=5,
        unique_id="AA:BB:CC:DD:EE:90",
        data={"address": "AA:BB:CC:DD:EE:90", "name": "Bed", "bed_type": "linak"},
    )
    entry.add_to_hass(hass)
    original = dict(entry.data)
    _, c = make()
    if not valid:
        c.client.services[0].get_characteristic(carrier.WRITE).properties = ["write"]
    monkeypatch.setattr(
        config_flow.AdjustableBedConfigFlow, "_verification_possible", lambda self: True
    )
    monkeypatch.setattr(config_flow, "discover_services", AsyncMock())
    monkeypatch.setattr(
        "bleak_retry_connector.establish_connection", AsyncMock(return_value=c.client)
    )
    manager = hass.config_entries.flow
    with _patch_gate("hci0", -55):
        result = await manager.async_init(
            const.DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
        )
        result = await manager.async_configure(result["flow_id"], {"bed_type": "easyctrl"})
        assert result["step_id"] == "profile_questions"
        result = await manager.async_configure(result["flow_id"], {"product_type": "100"})
        if result.get("step_id") == "finish_settings":
            result = await manager.async_configure(result["flow_id"], {})
        result = await _advance_progress(hass, result)
    assert result["step_id"] == ("migration_confirm" if valid else "migration_check_failed")
    assert entry.data == original
    manager.async_abort(result["flow_id"])
    c.client.write_gatt_char.assert_not_awaited()
    c.client.start_notify.assert_not_awaited()
    c.client.disconnect.assert_awaited_once()


@pytest.mark.parametrize("operation", ["rgb", "mode", "power"])
async def test_public_delivered_write_commits_even_when_cancelled_after_transmission(
    hass, ha_beds, operation
):
    target = await ha_beds()
    if operation == "rgb":
        await hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": entity(target, "under_bed_lights", "light")},
            blocking=True,
        )
        domain, service, data = (
            "light",
            "turn_on",
            {"entity_id": entity(target, "under_bed_lights", "light"), "brightness": 42},
        )
    elif operation == "mode":
        domain, service, data = (
            "select",
            "select_option",
            {"entity_id": entity(target, "easyctrl_head_mode", "select"), "option": "mode_2"},
        )
    else:
        domain, service, data = (
            "number",
            "set_value",
            {"entity_id": entity(target, "easyctrl_head_power", "number"), "value": 3},
        )

    async def sent_then_cancel(*_args, **_kwargs):
        target.runtime.cancel_command.set()

    target.client.write_gatt_char.reset_mock()
    target.client.write_gatt_char.side_effect = sent_then_cancel
    await asyncio.gather(
        hass.services.async_call(domain, service, data, blocking=True), return_exceptions=True
    )
    await hass.async_block_till_done()
    assert target.client.write_gatt_char.await_count == 1
    if operation == "rgb":
        assert target.ctrl.local.brightness == 42
        assert hass.states.get(data["entity_id"]).attributes["brightness"] == 42
    elif operation == "mode":
        assert target.ctrl.local.modes["head"] == 2
        assert target.ctrl.local.zone == "head"
        assert hass.states.get(data["entity_id"]).state == "mode_2"
    else:
        assert target.ctrl.local.powers["head"] == 3
        assert hass.states.get(data["entity_id"]).state == "3.0"


@pytest.mark.parametrize("operation", ["rgb", "mode", "power"])
async def test_public_session_change_prevents_cache_and_state_from_old_write(
    hass, ha_beds, operation
):
    target = await ha_beds()
    ctrl = target.ctrl
    old = (
        ctrl.local.rgb,
        ctrl.local.brightness,
        dict(ctrl.local.modes),
        dict(ctrl.local.powers),
        ctrl.local.zone,
    )
    domain, service, data = {
        "rgb": (
            "light",
            "turn_on",
            {
                "entity_id": entity(target, "under_bed_lights", "light"),
                "rgb_color": [17, 34, 51],
                "brightness": 68,
            },
        ),
        "mode": (
            "select",
            "select_option",
            {"entity_id": entity(target, "easyctrl_head_mode", "select"), "option": "mode_3"},
        ),
        "power": (
            "number",
            "set_value",
            {"entity_id": entity(target, "easyctrl_head_power", "number"), "value": 3},
        ),
    }[operation]

    async def replace_session(*_args, **_kwargs):
        ctrl.on_disconnect()
        await ctrl.start_notify()

    target.client.write_gatt_char.side_effect = replace_session
    with virtual_clock():
        await asyncio.gather(
            hass.services.async_call(domain, service, data, blocking=True), return_exceptions=True
        )
    await hass.async_block_till_done()
    assert (
        ctrl.local.rgb,
        ctrl.local.brightness,
        ctrl.local.modes,
        ctrl.local.powers,
        ctrl.local.zone,
    ) == old
    # A replacement session has no state from this write, even on the same client.
    if operation != "rgb":
        assert hass.states.get(data["entity_id"]).state == "unknown"


async def test_cancelled_movement_retains_cancellation_when_stop_also_fails():
    ctrl, c = make(300)
    await ctrl.start_notify()

    async def write(*_args, **_kwargs):
        if c.client.write_gatt_char.call_count == 1:
            c.cancel_command.set()
        elif c.client.write_gatt_char.call_count == 2:
            raise BleakError("first stop failed")

    c.client.write_gatt_char.side_effect = write
    with virtual_clock(), pytest.raises(asyncio.CancelledError) as caught:
        await ctrl.move_axis("all", False, 100)
    assert c.client.write_gatt_char.call_count == 4
    assert any("first stop failed" in note for note in caught.value.__notes__)


async def test_cancelled_controller_admission_without_command_context_does_not_commit():
    ctrl, c = make()
    await ctrl.start_notify()
    c.cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await ctrl.set_light_color_with_level((17, 34, 51), 68)
    assert ctrl.local.rgb == (255, 255, 255) and ctrl.local.packed == -128
    c.client.write_gatt_char.assert_not_awaited()


async def test_cancelled_sleep_activation_reports_partial_delivery(hass, ha_beds):
    target = await ha_beds()

    async def cancel_after_countdown(_char, frame, **_kwargs):
        if int.from_bytes(frame[2:4], 'little') == app.CONTROL_CODES['sleep_countdown']:
            target.runtime.cancel_command.set()

    target.client.write_gatt_char.reset_mock()
    target.client.write_gatt_char.side_effect = cancel_after_countdown
    switch = entity(target, 'easyctrl_sleep', 'switch')
    with virtual_clock():
        await asyncio.gather(hass.services.async_call('switch', 'turn_on', {
            'entity_id': switch,
        }, blocking=True), return_exceptions=True)
    assert codes(target) == [(app.CONTROL_CODES['sleep_countdown'], 60)]
    assert target.runtime.controller_state.get(bed.SLEEP) is None
    assert hass.states.get(switch).state == 'unknown'


@pytest.mark.parametrize('motor_stop', [False, True])
async def test_sequential_pair_stop_reopens_released_latched_motion(hass, motor_stop):
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    children = {}
    for number, side in enumerate(('left', 'right'), 1):
        entry = MockConfigEntry(domain=const.DOMAIN, data={
            'address': f'AA:BB:CC:DD:EE:{number:02X}', 'name': side,
            'bed_type': 'easyctrl', 'product_type': '100', 'motor_count': 2,
            'disable_angle_sensing': True,
        })
        entry.add_to_hass(hass)
        child = AdjustableBedCoordinator(hass, entry)
        _, transport = make()
        child._client = transport.client
        child._client.is_connected = False
        child._controller = bed.EasyCtrlController(child, replace(app.MODELS[100], query_delay_ms=0))

        async def connect(*_args, child=child, **_kwargs):
            child.client.is_connected = True
            await child.controller.start_notify()
            return True

        async def disconnect(*_args, child=child, **_kwargs):
            child.client.is_connected = False
            child.controller.on_disconnect()
            return True

        child.async_connect = AsyncMock(side_effect=connect)
        child.async_ensure_connected = AsyncMock(side_effect=connect)
        child.async_disconnect = AsyncMock(side_effect=disconnect)
        children[side] = child
    entry = MockConfigEntry(domain=const.DOMAIN, data={'pair_id': 'easyctrl-pair'})
    entry.add_to_hass(hass)
    pair = PairedBedCoordinator(hass, entry, children, connection_mode='sequential')
    right = children['right']
    try:
        with virtual_clock():
            await pair.async_execute_controller_command(lambda ctrl: ctrl.preset_flat(), side='right')
            assert not right.is_connected
            assert int.from_bytes(right.client.write_gatt_char.call_args.args[1][2:4], 'little') == 3
            right.client.write_gatt_char.reset_mock()
            if motor_stop:
                await pair.async_stop_motor(lambda ctrl: ctrl.stop_all(), 'motor:all', side='right')
            else:
                await pair.async_stop_command(side='right')
        frames = [call.args[1] for call in right.client.write_gatt_char.call_args_list]
        assert len(frames) == 3
        assert all(int.from_bytes(frame[2:4], 'little') == 1 for frame in frames)
        assert children['left'].async_connect.await_count == 0
    finally:
        await pair.async_shutdown()
