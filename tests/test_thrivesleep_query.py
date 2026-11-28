"""Native alarm refresh delivery, newer-report priority and diagnostic boundaries."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.const import Platform
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockEntityPlatform

from custom_components.adjustable_bed.beds.thrivesleep.controller import ALARMS
from custom_components.adjustable_bed.codec import richmat as codec
from tests.test_entity_sweep import async_setup_platforms_and_sweep
from tests.test_thrivesleep import capabilities, notify
from tests.test_thrivesleep import clock as clock
from tests.test_thrivesleep_runtime import runtime as runtime
from tests.test_thrivesleep_runtime import written


def report(client, number, hour=7, *, update=False):
    notify(
        SimpleNamespace(client=client),
        codec.record_20_len(5, 1, 3 if update else 2, (number, 0, hour, 30, 69, 1)).hex(),
    )


async def prepare(runtime):
    target, client = runtime
    assert await target.async_connect()
    capabilities(SimpleNamespace(client=client))
    report(client, 1)
    report(client, 2)
    client.write_gatt_char.reset_mock()
    return target, client, target.controller


async def refresh(hass):
    await hass.services.async_call(
        "adjustable_bed", "thrivesleep",
        {"device_id": ["bed"], "operation": "query_alarms"}, blocking=True,
    )


@pytest.mark.parametrize("newer_reply", (False, True))
async def test_registered_failed_refresh_preserves_old_and_newer_records(hass, runtime, newer_reply):
    target, client, ctrl = await prepare(runtime)

    async def fail(*args, **kwargs):
        assert len(ctrl.alarms) == 2
        if newer_reply:
            report(client, 1, 8, update=True)
        raise OSError("query write failed")

    client.write_gatt_char = AsyncMock(side_effect=fail)
    with pytest.raises(OSError, match="query write failed"):
        await refresh(hass)
    assert [row["id"] for row in ctrl.alarms] == [1, 2]
    assert ctrl.alarms[0]["hour"] == (8 if newer_reply else 7)
    assert target.controller_state[ALARMS] == ctrl.alarms
    assert written(client) == ["6e2008050100009c"]


@pytest.mark.parametrize("newer_reply", (False, True))
async def test_registered_actual_cancel_while_waiting_for_ble_keeps_cache(
    hass, runtime, monkeypatch, newer_reply
):
    target, client, ctrl = await prepare(runtime)
    entered = asyncio.Event()
    operations = []
    original = ctrl.query_alarms

    async def query():
        operations.append(asyncio.current_task())
        entered.set()
        await original()

    monkeypatch.setattr(ctrl, "query_alarms", query)
    async with ctrl.ble_lock:
        task = asyncio.create_task(refresh(hass))
        await entered.wait()
        if newer_reply:
            report(client, 1, 8, update=True)
        operations[0].cancel()
        for _ in range(30):
            if operations[0].done():
                break
            await asyncio.sleep(0)
        assert operations[0].cancelled()
    await task
    assert written(client) == []
    assert [row["id"] for row in ctrl.alarms] == [1, 2]
    assert ctrl.alarms[0]["hour"] == (8 if newer_reply else 7)
    assert target.controller_state[ALARMS] == ctrl.alarms


@pytest.mark.parametrize("reply_phase", ("queued", "writing"))
@pytest.mark.parametrize("cancel_task", (False, True))
@pytest.mark.parametrize("new_hour", (7, 8))
@pytest.mark.parametrize("list_reply", (False, True))
async def test_registered_delivered_refresh_retires_only_captured_record_identities(
    hass, runtime, monkeypatch, reply_phase, cancel_task, new_hour, list_reply
):
    target, client, ctrl = await prepare(runtime)
    operation_entered, writing, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    operations = []
    original = ctrl.query_alarms

    async def query():
        operations.append(asyncio.current_task())
        operation_entered.set()
        await original()

    async def write(*args, **kwargs):
        writing.set()
        await release.wait()

    def newer():
        report(client, 1, new_hour, update=not list_reply)
        report(client, 3, 9)

    monkeypatch.setattr(ctrl, "query_alarms", query)
    client.write_gatt_char = AsyncMock(side_effect=write)
    async with ctrl.ble_lock:
        task = asyncio.create_task(refresh(hass))
        await operation_entered.wait()
        assert len(ctrl.alarms) == 2
        if reply_phase == "queued":
            newer()
    await writing.wait()
    if reply_phase == "writing":
        newer()
    assert [row["id"] for row in ctrl.alarms] == [1, 2, 3]
    if cancel_task:
        operations[0].cancel()
        await asyncio.sleep(0)
    release.set()
    await task
    assert operations[0].cancelled() is cancel_task
    assert written(client) == ["6e2008050100009c"]
    assert [(row["id"], row["hour"]) for row in ctrl.alarms] == [(1, new_hour), (3, 9)]
    assert target.controller_state[ALARMS] == ctrl.alarms
    # A returned refresh record and its later update still use the native cache.
    report(client, 2)
    report(client, 2, 10, update=True)
    assert ctrl.alarms[-1]["hour"] == 10
    assert target.controller_state[ALARMS] == ctrl.alarms


async def test_refresh_settlement_cannot_retire_replacement_link_records(hass, runtime):
    target, client, ctrl = await prepare(runtime)
    entered, release = asyncio.Event(), asyncio.Event()

    async def write(*args, **kwargs):
        entered.set()
        await release.wait()

    client.write_gatt_char = AsyncMock(side_effect=write)
    task = asyncio.create_task(refresh(hass))
    await entered.wait()
    ctrl.on_disconnect()
    replacement = {"id": 1, "hour": 8}
    ctrl.alarms = [replacement]
    ctrl.forward_controller_state_updates(ALARMS([dict(replacement)]))
    release.set()
    with pytest.raises(ConnectionError, match="session has ended"):
        await task
    assert ctrl.alarms == [replacement]
    assert target.controller_state[ALARMS] == [replacement]


async def test_native_product_sensor_keeps_protocol_records_in_diagnostics(hass, runtime):
    target, client, ctrl = await prepare(runtime)
    notify(SimpleNamespace(client=client), "6e90392d64")
    created = await async_setup_platforms_and_sweep(hass, target.entry, target, (Platform.SENSOR,))
    product = next(e for e in created if e.unique_id.endswith("_thrivesleep"))
    er.async_get(hass).async_get_or_create(
        "sensor", "adjustable_bed", product.unique_id,
        config_entry=target.entry, disabled_by=None,
    )
    platform = MockEntityPlatform(hass, domain="sensor", platform_name="adjustable_bed")
    platform.config_entry = target.entry
    await platform.platform_data.async_load_translations()
    await platform.async_add_entities([product])
    await hass.async_block_till_done()
    assert product.native_value == ctrl.profile.label
    state = hass.states.get(product.entity_id)
    assert state is not None and state.state == ctrl.profile.label
    assert "thrivesleep_observations" not in state.attributes
    assert ALARMS not in state.attributes
    diagnostics = ctrl.protocol_diagnostics
    assert diagnostics["observations"] == ctrl.observations
    assert diagnostics["alarms"] == ctrl.alarms
    assert ctrl.observations["angle"] == 45
    assert target.controller_state[ALARMS] == ctrl.alarms
    ctrl.on_disconnect()
    assert ctrl.protocol_diagnostics == {"observations": {}, "alarms": []}
