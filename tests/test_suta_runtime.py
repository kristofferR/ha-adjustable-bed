"""Actual HA flow, factory, entities, services and scheduler callers for SUTA."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const, services
from custom_components.adjustable_bed.beds.suta import controller as bed
from custom_components.adjustable_bed.beds.suta import services as suta_services
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.codec import suta as codec
from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.profiles.suta import service_for_name
from tests.form_helpers import finish_new_bed
from tests.test_richmat_family_flow import setup_flow
from tests.test_suta import clock as clock


@pytest.fixture
async def runtime(hass, request, mock_coordinator_connected, mock_bleak_client, clock):
    name = getattr(request, "param", "SUTA-B803")
    entry = MockConfigEntry(
        domain=const.DOMAIN, title="SUTA display title",
        data={CONF_ADDRESS: "AA:BB:CC:DD:EE:28", CONF_NAME: "SUTA display title",
              const.CONF_BED_TYPE: "suta", const.CONF_BLE_DEVICE_NAME: name,
              const.CONF_HAS_MASSAGE: False, const.CONF_DISABLE_ANGLE_SENSING: True,
              const.CONF_DISCONNECT_AFTER_COMMAND: False},
    )
    entry.add_to_hass(hass)
    target = AdjustableBedCoordinator(hass, entry)
    target._max_retries = 1
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = target
    tx = SimpleNamespace(uuid="suta-property-write", properties=["write"], handle=28, descriptors=[])
    rx = SimpleNamespace(uuid="suta-property-notify", properties=["notify"], handle=29, descriptors=[])
    service = SimpleNamespace(uuid=service_for_name(name), characteristics=[rx, tx])
    mock_bleak_client.services.get_service.side_effect = lambda uuid: service if uuid == service.uuid else None
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    mock_bleak_client._backend = None
    await target.async_prime_offline_controller()
    assert isinstance(target.capability_controller, bed.SutaController)
    await services.async_register_services(hass)
    with patch.object(services, "_resolve_sided_targets", return_value=([(target, "both")], [])) as resolve:
        yield target, mock_bleak_client, resolve
    await target.async_shutdown()


def written(client):
    return [call.args[1] for call in client.write_gatt_char.await_args_list]


async def action(hass, key, **fields):
    await hass.services.async_call(const.DOMAIN, "suta", {"device_id": "bed", "action": key, **fields}, blocking=True)


async def test_actual_factory_cover_timed_hold_and_saved_entity(hass, runtime):
    target, client, _ = runtime
    assert await target.async_connect()
    ctrl = target.controller
    assert isinstance(ctrl, bed.SutaController)
    assert ctrl.profile.key == "MattressControllerB803Fragment"
    save = next(entity for entity in _button_entities_for(hass, target) if entity.unique_id.endswith("program_memory_3"))
    assert save.extra_state_attributes["requires_confirmation"] is True
    cover = AdjustableBedCover(target, _build_cover_description(ctrl.motor_control_specs[0]))
    cover.async_write_ha_state = MagicMock()
    await cover.async_open_cover()
    assert written(client)[0] == codec.text("AT+CTRL=BOTH BACK UP")
    assert written(client)[-2:] == [codec.text("AT+CTRL=BOTH STOP")] * 2
    client.write_gatt_char.reset_mock()
    await hass.services.async_call(const.DOMAIN, "timed_move", {"device_id": "bed", "motor": "back", "direction": "down", "duration_ms": 250}, blocking=True)
    assert written(client) == [codec.text("AT+CTRL=BOTH BACK DOWN")] * 2 + [codec.text("AT+CTRL=BOTH STOP")] * 2
    client.write_gatt_char.reset_mock()
    await hass.services.async_call(const.DOMAIN, "hold_control", {"device_id": "bed", "control": "ctrl_back_up", "duration": 0.1}, blocking=True)
    assert written(client) == [codec.text("AT+CTRL=BOTH BACK UP")] + [codec.text("AT+CTRL=BOTH STOP")] * 2


async def test_all_targets_validate_before_any_connect_or_effect(hass, runtime):
    from tests.test_generic_services import target as fake_target

    target, client, resolve = runtime
    wrong, _ = fake_target(name="other family")
    resolve.return_value = ([(target, "both"), (wrong, "both")], [])
    with pytest.raises(ServiceValidationError, match="Select a SUTA"):
        await action(hass, "both_tv")
    assert not target.is_connected
    assert not written(client)


async def test_stop_during_lazy_import_invalidates_original_admission(hass, runtime):
    target, client, _ = runtime
    assert await target.async_connect()
    original = suta_services.async_import_modules

    async def importing(*args, **kwargs):
        await target.async_stop_command()
        await original(*args, **kwargs)

    with patch.object(suta_services, "async_import_modules", importing):
        await action(hass, "both_tv")
    assert written(client) == [codec.text("AT+CTRL=BOTH STOP")] * 2


async def test_actual_stop_drains_submitted_movement_and_owns_one_cleanup(hass, runtime):
    target, client, _ = runtime
    assert await target.async_connect()
    started, finish = asyncio.Event(), asyncio.Event()

    async def block_first(_char, packet, **kwargs):
        if packet == codec.text("AT+CTRL=BOTH BACK UP"):
            started.set()
            await finish.wait()

    client.write_gatt_char.side_effect = block_first
    task = asyncio.create_task(target.async_execute_controller_command(lambda c: c.hold_control("ctrl_back_up", 1000)))
    await started.wait()
    stop = asyncio.create_task(target.async_stop_command())
    await asyncio.sleep(0)
    assert not stop.done()
    finish.set()
    await asyncio.gather(task, stop)
    assert written(client) == [codec.text("AT+CTRL=BOTH BACK UP")] + [codec.text("AT+CTRL=BOTH STOP")] * 2


@pytest.mark.parametrize("runtime", ["SUTA-MOON", "SUTA-TEMP", "SUTA-RBHC"], indirect=True)
async def test_binary_or_feedback_routes_through_real_connect(hass, runtime):
    target, client, _ = runtime
    assert await target.async_connect()
    ctrl = target.controller
    assert isinstance(ctrl, bed.SutaController)
    if ctrl.family == "MOON":
        assert len(written(client)) == 3
        client.write_gatt_char.reset_mock()
        await action(hass, "massage_timer_10", logical_side=2)
        assert written(client) == [codec.binary(0x96, 2, bytes((2, 10)))]
    elif ctrl.family == "TEMP":
        assert written(client) == [codec.binary(0xA1, 5, b"\x0f"), codec.binary(0xA0, 1, b"\x0f")]
        client.write_gatt_char.reset_mock()
        await action(hass, "temperature_setpoint", logical_side=1, value=22)
        assert written(client) == [codec.binary(0xA1, 3, bytes((1, 22)))]
    else:
        sender, callback = client.start_notify.call_args.args
        callback(sender, bytearray.fromhex("00000afffe0014ffff"))
        assert ctrl.observations == {"back": 10, "extra_1_raw": -2, "foot": 20, "extra_2_raw": -1}


async def test_text_alarm_and_active_zone_level_use_proven_schedules(hass, runtime):
    target, client, _ = runtime
    assert await target.async_connect()
    await action(hass, "alarm_set", weekdays=[0, 6], time="0630", loop="01")
    assert written(client) == [codec.text("AT+SA=00063001")] * 3 + [codec.text("AT+SA=06063001")] * 3 + [codec.text("AT+GA")] * 3
    client.write_gatt_char.reset_mock()
    await action(hass, "mass_head_dt", suffix="20")
    await action(hass, "mass_foot_dt", suffix="33")
    client.write_gatt_char.reset_mock()
    await action(hass, "mass_head_lv", suffix="10")
    assert written(client) == [codec.text("AT+MASS=BOTH HEAD LV10"), codec.text("AT+MASS=BOTH FOOT LV10")]


async def test_sequential_both_renewable_lease_rejects_before_claims(hass, runtime):
    from tests.test_paired_coordinator import _pair

    target, client, resolve = runtime
    pair, left, right = _pair([], mode=const.PAIR_CONNECTION_MODE_SEQUENTIAL)
    pair.hass = hass
    left.capability_controller = target.capability_controller
    right.capability_controller = target.capability_controller
    left.claim_hold_lease = MagicMock()
    right.claim_hold_lease = MagicMock()
    resolve.return_value = ([(pair, "both")], [])
    with pytest.raises(ServiceValidationError, match="one side"):
        await hass.services.async_call(const.DOMAIN, "timed_move", {"device_id": "pair", "motor": "back", "direction": "up", "duration_ms": 1000, "hold_owner": "card", "hold_generation": 1}, blocking=True)
    left.claim_hold_lease.assert_not_called()
    right.claim_hold_lease.assert_not_called()
    assert not written(client)


async def test_new_install_and_configure_keep_raw_name_and_rebuild_factory(hass):
    flow = setup_flow(hass, **{const.CONF_BED_TYPE: "suta", const.CONF_BLE_DEVICE_NAME: "SUTA-TEMP"})
    flow._discovery_info = None
    with patch.object(flow, "_verification_possible", return_value=False):
        result = await flow.async_step_profile_questions({const.CONF_BLE_DEVICE_NAME: "SUTA-TEMP"})
        result = await finish_new_bed(flow, result)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[const.CONF_BLE_DEVICE_NAME] == "SUTA-TEMP"
    assert data[const.CONF_HAS_MASSAGE] is False
    entry = MockConfigEntry(domain=const.DOMAIN, title="Friendly bed", data=data)
    entry.add_to_hass(hass)
    options = AdjustableBedOptionsFlow(entry)
    options.handler = entry.entry_id
    options.hass = hass
    # Configure uses the same persisted question and never a display-name guess.
    from custom_components.adjustable_bed.setup_questions import setup_profile
    profile = setup_profile(data[const.CONF_BED_TYPE])
    assert profile is not None
    assert any(q.key == const.CONF_BLE_DEVICE_NAME for q in profile.questions)
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = await create_controller(coordinator, "suta", "auto", None)
    assert controller.profile.key == "TempControllerFragment"

async def test_configure_persists_name_and_panel_owned_fields(hass):
    from tests.test_richmat_family_flow import configure, entry_for

    entry = entry_for(hass, **{const.CONF_BED_TYPE: "suta", const.CONF_BLE_DEVICE_NAME: "SUTA-B905", const.CONF_HAS_MASSAGE: True, const.CONF_MOTOR_COUNT: 4})
    result = await configure(hass, entry, {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[const.CONF_BLE_DEVICE_NAME] == "SUTA-B905"
    assert entry.data[const.CONF_HAS_MASSAGE] is False
    assert entry.data[const.CONF_MOTOR_COUNT] == 2


async def test_renewable_timed_motor_uses_declared_native_hold_control(hass, runtime):
    target, client, _ = runtime
    assert await target.async_connect()
    started, finish = asyncio.Event(), asyncio.Event()

    async def block_first(_char, packet, **kwargs):
        if packet == codec.text("AT+CTRL=BOTH BACK UP"):
            started.set()
            await finish.wait()

    client.write_gatt_char.side_effect = block_first
    task = asyncio.create_task(hass.services.async_call(
        const.DOMAIN, "timed_move",
        {"device_id": "bed", "motor": "back", "direction": "up", "duration_ms": 1000,
         "hold_owner": "card", "hold_generation": 1}, blocking=True,
    ))
    await asyncio.wait_for(started.wait(), 1)
    stop = asyncio.create_task(target.async_stop_command())
    await asyncio.sleep(0)
    finish.set()
    await asyncio.gather(task, stop)
    assert written(client) == [codec.text("AT+CTRL=BOTH BACK UP")] + [codec.text("AT+CTRL=BOTH STOP")] * 2


async def test_countdown_cannot_be_renewed_into_programming(hass, runtime):
    target, client, _ = runtime
    with pytest.raises(ServiceValidationError, match="renewable"):
        await hass.services.async_call(
            const.DOMAIN, "hold_control",
            {"device_id": "bed", "control": "both_set_tv", "duration": 1,
             "hold_owner": "card", "hold_generation": 2}, blocking=True,
        )
    assert not written(client)


async def test_massage_level_entity_refreshes_on_each_local_zone_change(hass, runtime):
    target, client, _ = runtime
    assert await target.async_connect()
    level = next(entity for entity in _button_entities_for(hass, target) if entity.unique_id.endswith("suta_mass_head_lv10"))
    level.hass = hass
    level.entity_id = "button.suta_level"
    level.async_write_ha_state = MagicMock()
    await level.async_added_to_hass()
    try:
        assert not level.available
        await action(hass, "mass_head_dt", suffix="20")
        assert level.available
        level.async_write_ha_state.assert_called()
        level.async_write_ha_state.reset_mock()
        await action(hass, "massage_off")
        assert not level.available
        assert level.async_write_ha_state.call_count == 2
    finally:
        await level.async_will_remove_from_hass()
