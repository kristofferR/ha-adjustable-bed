"""Saved setup to factory, entities and registered actions on real HA schedulers."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.sonicsleep import controller as bed
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.profiles.sonicsleep import ROUTES
from custom_components.adjustable_bed.services import async_register_services
from tests.test_richmat_family_flow import setup_flow
from tests.test_sonicsleep import GATT, notify
from tests.test_sonicsleep import clock as clock


@pytest.fixture
async def runtime(hass, request, mock_coordinator_connected, mock_bleak_client, clock):
    entry = MockConfigEntry(domain=const.DOMAIN, title="SonicSleep", data={CONF_ADDRESS: "AA:BB:CC:DD:EE:79", CONF_NAME: "SonicSleep", const.CONF_BED_TYPE: "sonicsleep", const.CONF_PRODUCT_TYPE: "one", const.CONF_DISABLE_ANGLE_SENSING: True, const.CONF_DISCONNECT_AFTER_COMMAND: False})
    entry.add_to_hass(hass)
    target = AdjustableBedCoordinator(hass, entry)
    target._max_retries = 1
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = target
    route = GATT[getattr(request, "param", "W1")]
    tx = SimpleNamespace(uuid=route["write"], properties=["write"], handle=79, descriptors=[])
    rx = SimpleNamespace(uuid=route["expected_notify_constant"], properties=["notify"], handle=80, descriptors=[])
    mock_bleak_client.services = [SimpleNamespace(uuid=route["service"], characteristics=[tx, rx])]
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    await target.async_prime_offline_controller()
    assert isinstance(target.capability_controller, bed.SonicSleepController)
    await async_register_services(hass)
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets", return_value=([(target, "both")], [])) as resolve:
        yield target, mock_bleak_client, resolve
    await target.async_shutdown()


def written(client):
    return [call.args[1].hex() for call in client.write_gatt_char.await_args_list]


async def settings(hass, operation, **fields):
    await hass.services.async_call(const.DOMAIN, "sonicsleep", {"device_id": "bed", "operation": operation, **fields}, blocking=True)


@pytest.mark.parametrize("runtime", ROUTES, indirect=True)
async def test_real_factory_connect_entities_and_registered_alarm_paths(hass, runtime):
    target, client, _ = runtime
    assert await target.async_connect()
    ctrl = target.controller
    assert isinstance(ctrl, bed.SonicSleepController)
    entities = _button_entities_for(hass, target)
    save = next(e for e in entities if e.unique_id.endswith("program_memory_1"))
    assert save.extra_state_attributes["requires_confirmation"] is True
    custom = next(e for e in entities if e.unique_id.endswith("sonicsleep_lounge_save"))
    assert custom.extra_state_attributes["requires_confirmation"] is True
    cover = AdjustableBedCover(target, _build_cover_description(ctrl.motor_control_specs[0]))
    cover.async_write_ha_state = MagicMock()
    client.write_gatt_char.reset_mock()
    await cover.async_open_cover()
    expected = "24" if ctrl._link.single else "6e01002493"
    assert written(client) and set(written(client)) == {expected}
    notify(target, "6e09010078")
    notify(target, "6e200d0501020307061e458399")
    client.write_gatt_char.reset_mock()
    await settings(hass, "toggle", alarm_id=3, enabled=False)
    assert written(client) == ["6e0d200501010307061e458297"]
    notify(target, "6e200d0501020307061e458399")
    client.write_gatt_char.reset_mock()
    await settings(hass, "edit", alarm_id=3, hour=6, minute=30, mode="zero_gravity", weekdays=[0, 6], enabled=False)
    assert written(client) == ["6e0d200501010300061e458290"]
    client.write_gatt_char.reset_mock()
    await hass.services.async_call(const.DOMAIN, "timed_move", {"device_id": "bed", "motor": "back", "direction": "down", "duration_ms": 250}, blocking=True)
    assert written(client) == ["25" if ctrl._link.single else "6e01002594"] * 2
    client.write_gatt_char.reset_mock()
    await hass.services.async_call(const.DOMAIN, "timed_move", {"device_id": "bed", "motor": "both", "direction": "up", "duration_ms": 250}, blocking=True)
    assert written(client) == ["29" if ctrl._link.single else "6e01002998"] * 2


async def test_registered_alarm_edit_ack_requires_current_fields_before_toggle(hass, runtime):
    target, client, _ = runtime
    assert await target.async_connect()
    notify(target, "6e09010078")
    notify(target, "6e200d0501020307061e458399")
    await settings(hass, "edit", alarm_id=3, hour=7, minute=45, weekdays=[0, 6])
    notify(target, "6e07010177")
    assert target.controller.alarms[0].hour == 6

    async def fresh_record(_char, packet, **kwargs):
        if packet.hex() == "6e0820050100009c":
            notify(target, "6e200d0501020300072d4583a2")

    client.write_gatt_char.reset_mock()
    client.write_gatt_char.side_effect = fresh_record
    await settings(hass, "toggle", alarm_id=3, enabled=False)
    assert written(client) == ["6e0820050100009c", "6e0d200501010300072d4582a0"]


async def test_real_stop_drains_owner_and_reconnect_cannot_replay_cache(hass, runtime):
    target, client, _ = runtime
    assert await target.async_connect()
    old = target.controller
    notify(target, "6e09010078")
    notify(target, "6e200d0501020307061e458399")
    old_callback = client.start_notify.call_args
    client.write_gatt_char.reset_mock()
    started, finish = asyncio.Event(), asyncio.Event()

    async def delayed(*args, **kwargs):
        started.set()
        await finish.wait()

    client.write_gatt_char.side_effect = delayed
    command = asyncio.create_task(target.async_execute_controller_command(lambda c: c.hold_control("head_up", 1000)))
    await started.wait()
    stop = asyncio.create_task(target.async_stop_command())
    await asyncio.sleep(0)
    assert not stop.done()
    finish.set()
    await asyncio.gather(command, stop)
    assert written(client) == ["6e01002493"]
    client.write_gatt_char.side_effect = None
    await target.async_disconnect("idle_timeout")
    assert not old.alarms and not old.observations
    assert await target.async_connect()
    assert target.controller is not old
    old_callback.args[1](old_callback.args[0], bytearray.fromhex("6e09010078"))
    assert not old.observations and not target.controller.observations


async def test_all_target_local_rejection_before_first_connect(hass, runtime):
    from tests.test_generic_services import target as fake_target

    target, client, resolve = runtime
    other, _ = fake_target(name="wrong app")
    resolve.return_value = ([(target, "both"), (other, "both")], [])
    with pytest.raises(ServiceValidationError, match="Select SonicSleep"):
        await settings(hass, "toggle", alarm_id=3, enabled=False)
    client.write_gatt_char.assert_not_awaited()
    assert not target.is_connected


async def test_stop_during_lazy_import_cancels_settings_and_goto_preset(hass, runtime):
    from custom_components.adjustable_bed import services
    from custom_components.adjustable_bed.beds.sonicsleep import services as sonic_services

    target, client, _ = runtime
    assert await target.async_connect()
    real = sonic_services.async_import_modules

    async def importing(*args, **kwargs):
        await target.async_stop_command()
        await real(*args, **kwargs)

    client.write_gatt_char.reset_mock()
    with patch.object(sonic_services, "async_import_modules", importing):
        await settings(hass, "link_name")
    assert not written(client)
    original = services._validation_controller

    async def preflight(*args, **kwargs):
        await target.async_stop_command()
        return await original(*args, **kwargs)

    with patch.object(services, "_validation_controller", preflight):
        await hass.services.async_call(const.DOMAIN, "goto_preset", {"device_id": "bed", "preset": 1}, blocking=True)
    assert not written(client)


async def test_second_target_missing_cache_prevents_first_mutation(hass, runtime, monkeypatch):
    from tests.test_generic_services import target as fake_target

    target, client, resolve = runtime
    assert await target.async_connect()
    notify(target, "6e09010078")
    notify(target, "6e200d0501020307061e458399")
    other, ctrl = fake_target(family=bed.SonicSleepController)
    ctrl.validate_request = MagicMock()
    ctrl.prepare_plan = AsyncMock(side_effect=ValueError("missing second cache"))

    async def query(fn, **kwargs):
        return await fn(ctrl)

    other.async_execute_controller_query = query
    resolve.return_value = ([(target, "both"), (other, "both")], [])
    client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError, match="missing second cache"):
        await settings(hass, "toggle", alarm_id=3, enabled=False)
    assert not written(client)


async def test_sequential_both_lease_rejected_before_claims_finite_still_runs(hass, runtime):
    from tests.test_paired_coordinator import _pair

    target, client, resolve = runtime
    pair, left, right = _pair([], mode=const.PAIR_CONNECTION_MODE_SEQUENTIAL)
    pair.hass = hass
    left.capability_controller = target.capability_controller
    right.capability_controller = target.capability_controller
    left.claim_hold_lease = MagicMock()
    right.claim_hold_lease = MagicMock()
    resolve.return_value = ([(pair, "both")], [])
    with pytest.raises(ServiceValidationError, match="concurrent physical"):
        await hass.services.async_call(const.DOMAIN, "timed_move", {"device_id": "pair", "motor": "back", "direction": "up", "duration_ms": 1000, "hold_owner": "card", "hold_generation": 1}, blocking=True)
    left.claim_hold_lease.assert_not_called()
    right.claim_hold_lease.assert_not_called()
    client.write_gatt_char.assert_not_awaited()
    resolve.return_value = ([(target, "both")], [])
    await hass.services.async_call(const.DOMAIN, "timed_move", {"device_id": "bed", "motor": "back", "direction": "up", "duration_ms": 250}, blocking=True)
    assert "6e01002493" in written(client)


async def test_full_setup_saves_fixed_product_and_factory_can_rebuild(hass):
    from custom_components.adjustable_bed.config_flow import _bed_type_selector
    from custom_components.adjustable_bed.controller_factory import create_controller
    from tests.form_helpers import finish_new_bed

    flow = setup_flow(hass)
    flow._discovery_info = None
    with patch.object(flow, "_verification_possible", return_value=False):
        result = await flow.async_step_richmat_family({"choice": "sonicsleep"})
        result = await finish_new_bed(flow, result)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[const.CONF_PRODUCT_TYPE] == "one"
    assert data[const.CONF_BED_TYPE] == "sonicsleep"
    entry = MockConfigEntry(domain=const.DOMAIN, title="SonicSleep", data=data)
    entry.add_to_hass(hass)
    target = AdjustableBedCoordinator(hass, entry)
    controller = await create_controller(target, "sonicsleep", "auto", None)
    assert isinstance(controller, bed.SonicSleepController)
    assert len(controller.motor_control_specs) == 3
    assert _bed_type_selector("sonicsleep", show_saved_id=True)("sonicsleep") == "sonicsleep"
    await target.async_shutdown()


async def test_configure_persists_fixed_product_and_owned_layout(hass):
    from tests.test_richmat_family_flow import configure, entry_for

    entry = entry_for(hass, **{const.CONF_BED_TYPE: "sonicsleep", const.CONF_PRODUCT_TYPE: "unknown", const.CONF_MOTOR_COUNT: 4, const.CONF_HAS_MASSAGE: True})
    result = await configure(hass, entry, {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[const.CONF_PRODUCT_TYPE] == "one"
    assert entry.data[const.CONF_MOTOR_COUNT] == 2
    assert entry.data[const.CONF_HAS_MASSAGE] is False
