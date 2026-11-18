"""Lunio setup, entities and actions through actual HA coordinators and schedulers."""

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
from custom_components.adjustable_bed.beds.luniosmart import controller as bed
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.services import async_register_services
from tests.test_luniosmart import GATT, notify
from tests.test_luniosmart import clock as clock
from tests.test_richmat_family_flow import setup_flow


@pytest.fixture
async def runtime(hass, request, mock_coordinator_connected, mock_bleak_client, clock):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Lunio Smart+",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:41",
            CONF_NAME: "Lunio Smart+",
            const.CONF_BED_TYPE: "luniosmart",
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        },
    )
    entry.add_to_hass(hass)
    from custom_components.adjustable_bed import _async_sync_profile_ids

    _async_sync_profile_ids(hass, entry)
    assert entry.data[const.CONF_PROFILE_ID] == "luniosmart"
    target = AdjustableBedCoordinator(hass, entry)
    target._max_retries = 1
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = target
    route = GATT[getattr(request, "param", 0)]
    tx = SimpleNamespace(uuid=route["write"], properties=["write"], handle=141, descriptors=[])
    rx = SimpleNamespace(
        uuid=route["declared_notify"], properties=["notify"], handle=142, descriptors=[]
    )
    mock_bleak_client.services = [SimpleNamespace(uuid=route["service"], characteristics=[tx, rx])]
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    await target.async_prime_offline_controller()
    assert isinstance(target.capability_controller, bed.LunioSmartController)
    await async_register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(target, "both")], []),
    ) as resolve:
        yield target, mock_bleak_client, resolve
    await target.async_shutdown()


def written(client):
    return [call.args[1].hex() for call in client.write_gatt_char.await_args_list]


@pytest.mark.parametrize("runtime", range(6), indirect=True)
async def test_factory_actual_entities_and_registered_actions(hass, runtime):
    target, client, _ = runtime
    assert await target.async_connect()
    ctrl = target.controller
    assert isinstance(ctrl, bed.LunioSmartController)
    buttons = _button_entities_for(hass, target)
    save = next(e for e in buttons if e.unique_id.endswith("program_memory_1"))
    assert save.extra_state_attributes["requires_confirmation"] is True
    assert not any(e.unique_id.endswith("preset_memory_2") for e in buttons)
    for key, expected in (
        ("preset_flat", "6e010031a0"),
        ("preset_zero_g", "6e010045b4"),
        ("preset_anti_snore", "6e010046b5"),
        ("preset_memory_1", "6e01002e9d"),
        ("program_memory_1", "6e01002b9a"),
    ):
        entity = next(e for e in buttons if e.unique_id.endswith(key))
        client.write_gatt_char.reset_mock()
        await entity.async_press()
        assert written(client) == [expected, "6e01006edd"]
    cover = AdjustableBedCover(target, _build_cover_description(ctrl.motor_control_specs[0]))
    cover.async_write_ha_state = MagicMock()
    client.write_gatt_char.reset_mock()
    await cover.async_open_cover()
    assert set(written(client)) == {"6e01002493", "6e01006edd"}
    client.write_gatt_char.reset_mock()
    await hass.services.async_call(
        const.DOMAIN,
        "timed_move",
        {"device_id": "bed", "motor": "legs", "direction": "down", "duration_ms": 250},
        blocking=True,
    )
    assert written(client) == ["6e01002796"] * 3 + ["6e01006edd"]
    for service, expected in (("goto_preset", "6e01002e9d"), ("save_preset", "6e01002b9a")):
        client.write_gatt_char.reset_mock()
        await hass.services.async_call(const.DOMAIN, service, {"device_id": "bed", "preset": 1}, blocking=True)
        assert written(client) == [expected, "6e01006edd"]
    notify(target, "6e90000700")
    assert target.controller.protocol_diagnostics["observations"]["deviceControlBoxProtocolVersionEvent"] == 7


async def test_real_stop_drains_inflight_and_releases_without_retention(hass, runtime):
    target, client, _ = runtime
    assert await target.async_connect()
    old = target.controller
    started, finish = asyncio.Event(), asyncio.Event()

    async def delayed(_char, packet, **kwargs):
        if packet.hex() == "6e01002493":
            started.set()
            await finish.wait()

    client.write_gatt_char.reset_mock()
    client.write_gatt_char.side_effect = delayed
    command = asyncio.create_task(
        target.async_execute_controller_command(lambda c: c.hold_control("head_up", 1000))
    )
    await started.wait()
    stop = asyncio.create_task(target.async_stop_command())
    await asyncio.sleep(0)
    assert not stop.done()
    finish.set()
    await asyncio.gather(command, stop)
    assert written(client)[0] == "6e01002493"
    assert set(written(client)[1:]) == {"6e01006edd"}
    client.write_gatt_char.side_effect = None
    notify(target, "6e20ff")
    old_callback = client.start_notify.call_args
    await target.async_disconnect("idle_timeout")
    assert not old._receiver.pending and old._expiry is None
    assert await target.async_connect()
    old_callback.args[1](old_callback.args[0], bytearray.fromhex("6e90000700"))
    assert not target.controller.observations


async def test_all_target_memory_admission_rejects_before_any_write(hass, runtime):
    from tests.test_generic_services import target as fake_target

    target, client, resolve = runtime
    other, _ = fake_target(name="second bed")
    resolve.return_value = ([(other, "both"), (target, "both")], [])
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            const.DOMAIN, "goto_preset", {"device_id": "bed", "preset": 2}, blocking=True
        )
    client.write_gatt_char.assert_not_awaited()
    assert not target.is_connected


async def test_stop_during_lazy_validation_invalidates_owner_before_execute(hass, runtime):
    from custom_components.adjustable_bed import services

    target, client, _ = runtime
    assert await target.async_connect()
    original = services._validation_controller

    async def preflight(*args, **kwargs):
        await target.async_stop_command()
        client.write_gatt_char.reset_mock()
        return await original(*args, **kwargs)

    with patch.object(services, "_validation_controller", preflight):
        await hass.services.async_call(
            const.DOMAIN, "goto_preset", {"device_id": "bed", "preset": 1}, blocking=True
        )
    assert not written(client)


async def test_sequential_pair_both_lease_rejected_before_claims(hass, runtime):
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
        await hass.services.async_call(
            const.DOMAIN,
            "timed_move",
            {
                "device_id": "pair",
                "motor": "back",
                "direction": "up",
                "duration_ms": 1000,
                "hold_owner": "card",
                "hold_generation": 1,
            },
            blocking=True,
        )
    left.claim_hold_lease.assert_not_called()
    right.claim_hold_lease.assert_not_called()
    client.write_gatt_char.assert_not_awaited()


async def test_new_install_saves_profile_and_factory_rebuilds(hass):
    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.profile_id import resolve_profile_id
    from tests.form_helpers import finish_new_bed

    flow = setup_flow(hass)
    flow._discovery_info = None
    with patch.object(flow, "_verification_possible", return_value=False):
        result = await flow.async_step_richmat_family({"choice": "luniosmart"})
        result = await finish_new_bed(flow, result)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[const.CONF_BED_TYPE] == "luniosmart"
    assert resolve_profile_id(data) == "luniosmart"
    entry = MockConfigEntry(domain=const.DOMAIN, title="Lunio Smart+", data=data)
    entry.add_to_hass(hass)
    from custom_components.adjustable_bed import _async_sync_profile_ids

    _async_sync_profile_ids(hass, entry)
    assert entry.data[const.CONF_PROFILE_ID] == "luniosmart"
    target = AdjustableBedCoordinator(hass, entry)
    ctrl = await create_controller(target, "luniosmart", "auto", None)
    assert isinstance(ctrl, bed.LunioSmartController)
    assert len(ctrl.motor_control_specs) == 2
    await target.async_shutdown()


async def test_configure_restores_fixed_app_fields(hass):
    from tests.test_richmat_family_flow import configure, entry_for

    entry = entry_for(
        hass,
        **{
            const.CONF_BED_TYPE: "luniosmart",
            const.CONF_MOTOR_COUNT: 4,
            const.CONF_HAS_MASSAGE: True,
        },
    )
    result = await configure(hass, entry, {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[const.CONF_MOTOR_COUNT] == 2
    assert entry.data[const.CONF_HAS_MASSAGE] is False
