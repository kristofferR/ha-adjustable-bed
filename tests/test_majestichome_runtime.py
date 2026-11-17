"""Real HA factory, setup, entities, services, STOP and paired-device targets."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import (
    _async_ensure_paired_device_registry,
    _async_sync_profile_ids,
    _build_paired_children,
    const,
)
from custom_components.adjustable_bed.beds.majestichome import controller as bed
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.profile_id import with_profile_ids
from custom_components.adjustable_bed.services import async_register_services
from tests.test_majestichome import GATT, notify, written
from tests.test_majestichome import clock as clock
from tests.test_paired_setup import _paired_entry_data
from tests.test_richmat_family_flow import configure, entry_for, setup_flow


@pytest.fixture
async def runtime(hass, mock_coordinator_connected, mock_bleak_client, clock):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Majestic Home",
        data=with_profile_ids(
            {
                CONF_ADDRESS: "AA:BB:CC:DD:EE:51",
                CONF_NAME: "Majestic Home",
                const.CONF_BED_TYPE: "majestichome",
                const.CONF_PROTOCOL_VARIANT: "FARM",
                const.CONF_DISABLE_ANGLE_SENSING: True,
                const.CONF_DISCONNECT_AFTER_COMMAND: False,
            }
        ),
    )
    entry.add_to_hass(hass)
    target = AdjustableBedCoordinator(hass, entry)
    target._max_retries = 1
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = target
    tx = SimpleNamespace(
        uuid=GATT[1]["write"].lower(), properties=["write"], handle=51, descriptors=[]
    )
    rx = SimpleNamespace(uuid="first-notify", properties=["notify"], handle=52, descriptors=[])
    mock_bleak_client.services = [
        SimpleNamespace(uuid=GATT[1]["service"].lower(), characteristics=[tx, rx])
    ]
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    await target.async_prime_offline_controller()
    await async_register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(target, "both")], []),
    ) as resolve:
        yield target, mock_bleak_client, resolve
    await target.async_shutdown()


async def settings(hass, operation, **fields):
    await hass.services.async_call(
        const.DOMAIN,
        "majestichome",
        {"device_id": "bed", "operation": operation, **fields},
        blocking=True,
    )


async def test_real_factory_native_entities_services_and_timed_move(hass, runtime):
    target, client, _ = runtime
    assert isinstance(target.capability_controller, bed.MajesticHomeController)
    assert await target.async_connect()
    ctrl = target.controller
    assert isinstance(ctrl, bed.MajesticHomeController)
    buttons = _button_entities_for(hass, target)
    save = next(b for b in buttons if b.unique_id.endswith("majestichome_memory_1_save"))
    assert save.extra_state_attributes["requires_confirmation"]
    cover = AdjustableBedCover(target, _build_cover_description(ctrl.motor_control_specs[0]))
    cover.async_write_ha_state = MagicMock()
    client.write_gatt_char.reset_mock()
    await cover.async_open_cover()
    assert written(target)[-1] == "6e01006edd"
    assert set(written(target)[:-1]) == {"6e01002493"}
    notify(target, "6e09010078")
    notify(target, "6e200d0501020100071e2ef9f0")
    client.write_gatt_char.reset_mock()
    await settings(hass, "toggle", alarm_id=1, enabled=False)
    assert written(target) == ["6e0d200501010100071e2ef8ee"]
    client.write_gatt_char.reset_mock()
    await hass.services.async_call(
        const.DOMAIN,
        "timed_move",
        {"device_id": "bed", "motor": "back", "direction": "down", "duration_ms": 250},
        blocking=True,
    )
    assert written(target) == ["6e01002594"] * 2 + ["6e01006edd"]


async def test_real_stop_drains_inflight_then_releases_and_disconnect_fences_callback(
    hass, runtime
):
    target, client, _ = runtime
    assert await target.async_connect()
    old = target.controller
    callback = client.start_notify.call_args
    started, complete = asyncio.Event(), asyncio.Event()

    async def write(_characteristic, packet, **kwargs):
        if packet.hex() == "6e01002493":
            started.set()
            await complete.wait()

    client.write_gatt_char.reset_mock()
    client.write_gatt_char.side_effect = write
    command = asyncio.create_task(
        target.async_execute_controller_command(lambda c: c.hold_control("head_up", 1000))
    )
    await started.wait()
    stop = asyncio.create_task(target.async_stop_command())
    await asyncio.sleep(0)
    assert not stop.done()
    complete.set()
    await asyncio.gather(command, stop)
    assert written(target)[0] == "6e01002493"
    assert set(written(target)[1:]) == {"6e01006edd"}
    client.write_gatt_char.side_effect = None
    await target.async_disconnect("idle_timeout")
    callback.args[1](callback.args[0], bytearray.fromhex("6e09010078"))
    assert not old.observations


async def test_native_motor_lease_renews_one_stream_and_refuses_ended_generation(
    hass, runtime, monkeypatch
):
    from tests.hold_lease_wire import virtual_clock

    target, client, _ = runtime
    assert await target.async_connect()
    client.write_gatt_char.reset_mock()
    data = {
        "device_id": "bed",
        "motor": "back",
        "direction": "up",
        "duration_ms": 500,
        "hold_owner": "card",
        "hold_generation": 1,
    }
    with virtual_clock() as fake:
        target.controller._next_write_at = 0  # Startup used the real loop's epoch.
        monkeypatch.setattr(bed, "monotonic", fake.time)
        monkeypatch.setattr(bed.MajesticHomeController, "_delay", bed.GoodVibeController._delay)
        start = asyncio.create_task(
            hass.services.async_call(const.DOMAIN, "timed_move", data, blocking=True)
        )
        await asyncio.sleep(0.25)
        before = len(written(target))
        await hass.services.async_call(const.DOMAIN, "timed_move", data, blocking=True)
        assert "6e01006edd" not in written(target)[before:]
        await asyncio.wait_for(start, 2)
        assert written(target)[-1] == "6e01006edd"
        assert set(written(target)[:-1]) == {"6e01002493"}
        with pytest.raises(ServiceValidationError, match="has ended"):
            await hass.services.async_call(const.DOMAIN, "timed_move", data, blocking=True)


async def test_stop_during_lazy_import_and_invalid_second_target_never_mutate(hass, runtime):
    from custom_components.adjustable_bed.beds.majestichome import services

    target, client, resolve = runtime
    assert await target.async_connect()
    notify(target, "6e09010078")
    real = services.async_import_modules

    async def importing(*args, **kwargs):
        await target.async_stop_command()
        client.write_gatt_char.reset_mock()
        await real(*args, **kwargs)

    with patch.object(services, "async_import_modules", importing):
        await settings(hass, "set", alarm_id=1)
    assert not written(target)
    bad = MagicMock()
    bad.capability_controller = MagicMock()
    resolve.return_value = ([(target, "both"), (bad, "both")], [])
    with (
        patch.object(services, "async_import_modules", AsyncMock()) as importing,
        pytest.raises(ServiceValidationError, match="Select Majestic Home"),
    ):
        await settings(hass, "set", alarm_id=1)
    importing.assert_not_awaited()
    assert not written(target)


@pytest.mark.parametrize("product", ("FARM", "JLRM", "JGRN", "JHRN"))
async def test_new_install_configure_and_profile_restore(hass, product):
    from custom_components.adjustable_bed.controller_factory import create_controller
    from tests.form_helpers import finish_new_bed

    flow = setup_flow(hass)
    flow._discovery_info = None
    with patch.object(flow, "_verification_possible", return_value=False):
        form = await flow.async_step_richmat_family({"choice": "majestichome"})
        form = await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: product})
        result = await finish_new_bed(flow, form)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[const.CONF_PROTOCOL_VARIANT] == product
    entry = entry_for(hass, **data)
    _async_sync_profile_ids(hass, entry)
    assert entry.data[const.CONF_PROFILE_ID] == "majestichome:" + product
    target = AdjustableBedCoordinator(hass, entry)
    ctrl = await create_controller(target, "majestichome", product, None)
    assert ctrl.layout.key == product
    configured = await configure(hass, entry, {const.CONF_PROTOCOL_VARIANT: product})
    assert configured["type"] is FlowResultType.CREATE_ENTRY
    _async_sync_profile_ids(hass, entry)
    assert entry.data[const.CONF_PROFILE_ID] == "majestichome:" + product
    await target.async_shutdown()


async def test_real_native_pair_parent_and_child_devices_route_settings(
    hass, mock_coordinator_connected, clock
):
    data = _paired_entry_data()
    data[const.CONF_BED_TYPE] = "majestichome"
    data[const.CONF_PAIR_CONNECTION_MODE] = const.PAIR_CONNECTION_MODE_CONCURRENT
    for row, product in zip(data[const.CONF_PAIR_CHILDREN], ("FARM", "JLRM"), strict=True):
        row.update(
            {
                const.CONF_BED_TYPE: "majestichome",
                const.CONF_PROTOCOL_VARIANT: product,
                const.CONF_DISCONNECT_AFTER_COMMAND: False,
            }
        )
        row.pop("capabilities", None)
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Majestic pair",
        data=with_profile_ids(data),
        version=5,
        state=ConfigEntryState.LOADED,
    )
    entry.add_to_hass(hass)
    children = _build_paired_children(hass, entry)
    pair = PairedBedCoordinator(hass, entry, children)
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = pair
    _async_ensure_paired_device_registry(hass, entry, pair)
    for child in children.values():
        await child.async_prime_offline_controller()
        client = MagicMock(is_connected=True)
        client.write_gatt_char = AsyncMock()
        client.start_notify = AsyncMock()
        client.stop_notify = AsyncMock()

        async def disconnect(client=client):
            client.is_connected = False

        client.disconnect = AsyncMock(side_effect=disconnect)
        child._client = client
        child._controller = bed.MajesticHomeController(
            child, product=child.entry.data[const.CONF_PROTOCOL_VARIANT]
        )
        tx = SimpleNamespace(uuid="tx", properties=["write"], handle=1)
        rx = SimpleNamespace(uuid="rx", properties=["notify"], handle=2)
        child._controller._link = bed.Link(client, tx, rx, False)
        child._controller.observations["clock_available"] = True
    await async_register_services(hass)
    registry = dr.async_get(hass)
    parent = registry.async_get_device_by_identifier(
        next(iter(pair.device_info["identifiers"])), entry.entry_id
    )
    assert parent is not None
    native = dr.async_entries_for_parent_device(registry, parent.id)
    assert len(native) == 2
    await hass.services.async_call(
        const.DOMAIN,
        "majestichome",
        {"device_id": parent.id, "operation": "set", "alarm_id": 1},
        blocking=True,
    )
    assert all(written(child) == ["6e0d200501010100071e2e01f7"] for child in children.values())
    for child in children.values():
        child.client.write_gatt_char.reset_mock()
    left_device = next(d for d in native if "Left" in d.name)
    await hass.services.async_call(
        const.DOMAIN,
        "majestichome",
        {"device_id": left_device.id, "operation": "delete", "alarm_id": 1},
        blocking=True,
    )
    assert written(children["left"]) == ["6e0820050201019f"]
    assert written(children["right"]) == []
    await hass.services.async_call(
        const.DOMAIN, "stop_all", {"device_id": left_device.id}, blocking=True
    )
    assert written(children["left"]) == ["6e0820050201019f", "6e01006edd"]
    assert written(children["right"]) == []
    await pair.async_shutdown()
