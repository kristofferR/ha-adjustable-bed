"""Cached diagnostic values and transactional options profile boundaries."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.limoss import LimossController
from custom_components.adjustable_bed.beds.limoss_remote_protocol import format_command
from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
from custom_components.adjustable_bed.pairing import get_child
from custom_components.adjustable_bed.sensor import AdjustableBedControllerStateSensor
from tests.test_coordinator_limoss_remote import actual_coordinator
from tests.test_limoss_remote_review_lifecycle import CAPS, live_controller, pair_runtime


async def test_offline_paired_cached_capability_sensors_publish_restored_values(hass):
    _, children, _ = await pair_runtime(hass)
    child = children[const.SIDE_RIGHT]
    client = child.client
    child._client = child._controller = child._offline_controller = None
    await child.async_prime_offline_controller()
    controller = child.capability_controller
    assert controller is not None
    assert controller.protocol_diagnostics["capabilities"] == CAPS
    expected = {
        "key_count": 8, "motor_count": 2, "configuration": 0,
        "memory_slots": 8, "reported_entry": "bed",
    }
    sensors = {
        spec.state_key: AdjustableBedControllerStateSensor(child, spec)
        for spec in controller.controller_state_sensor_specs
    }
    assert {field: sensors["limoss_remote_" + field].native_value for field in expected} == expected
    client.write_gatt_char.assert_not_awaited()
    client.start_notify.assert_awaited_once()  # Original ready session only; offline rebuild performs no I/O.
    assert child.client is None


@pytest.mark.parametrize("requested", [const.BED_TYPE_LIMOSS, const.BED_TYPE_KEESON])
@pytest.mark.parametrize("mixed", [False, True])
async def test_paired_conversion_away_requires_unpair_before_any_pending_change(
    hass, requested, mixed
):
    pair, children, _ = await pair_runtime(hass)
    if mixed:
        data = deepcopy(dict(pair.entry.data))
        data[const.CONF_PAIR_CHILDREN][0][const.CONF_BED_TYPE] = requested
        hass.config_entries.async_update_entry(pair.entry, data=data)
    before = deepcopy(dict(pair.entry.data))
    flow = AdjustableBedOptionsFlow(pair.entry)
    flow.hass, flow.handler = hass, pair.entry.entry_id
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock()) as reload:
        result = await flow.async_step_settings({const.CONF_BED_TYPE: requested})
    assert result.get("errors") == {"base": "limoss_remote_pair_settings"}
    assert not flow._pending_data and pair.entry.data == before
    reload.assert_not_awaited()
    for side, child in children.items():
        assert get_child(pair.entry.data, side) == get_child(before, side)
        child.client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("failure", [None, "error", "cancel"])
async def test_leaving_remote_finishes_old_native_off_transaction_before_save(hass, failure):
    coordinator = actual_coordinator(
        hass,
        **{
            const.CONF_HAS_LIGHT: True,
            const.CONF_HAS_MASSAGE: True,
            const.CONF_LIMOSS_REMOTE_STATE: {"capabilities": CAPS},
        },
    )
    controller = await live_controller(coordinator)
    client = coordinator.client

    def startup(char, packet, **kwargs):
        opcode = LimossController._tea_decrypt(packet[1:9])[1]
        payload = {2: "0208120008", 0: "0001020304", 1: "0101020304"}[opcode]
        callback = client.start_notify.call_args.args[1]
        callback(char, bytearray(format_command(bytes.fromhex(payload), 0)))

    client.write_gatt_char.side_effect = startup
    await coordinator.async_start_notify()
    before = deepcopy(dict(coordinator.entry.data))
    client.write_gatt_char.reset_mock()
    payloads = []
    entered = asyncio.Event()
    held = asyncio.Event()

    async def write(char, packet, **kwargs):
        assert coordinator.entry.data == before
        payloads.append(LimossController._tea_decrypt(packet[1:9])[1:6].hex())
        if len(payloads) == 12:
            if failure == "error":
                raise ConnectionError("OFF failed after partial hardware success")
            if failure == "cancel":
                entered.set()
                await held.wait()

    client.write_gatt_char.side_effect = write
    flow = AdjustableBedOptionsFlow(coordinator.entry)
    flow.hass, flow.handler = hass, coordinator.entry.entry_id
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock()) as reload:
        first = await flow.async_step_settings({const.CONF_BED_TYPE: const.BED_TYPE_LIMOSS})
        assert first["type"] == "form" and coordinator.entry.data == before
        client.write_gatt_char.assert_not_awaited()
        if failure == "cancel":
            save = asyncio.create_task(flow.async_step_settings({}))
            try:
                await asyncio.wait_for(entered.wait(), timeout=2)
                save.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await save
            finally:
                held.set()
                save.cancel()
                await asyncio.gather(save, return_exceptions=True)
        else:
            result = await flow.async_step_settings({})
            if failure == "error":
                assert result.get("errors") == {"base": "limoss_remote_feature_update_failed"}
            else:
                assert result["type"] == "create_entry"
        if failure is not None:
            assert coordinator.entry.data == before
            assert controller.underbed_light and controller.massage
            reload.assert_not_awaited()
        else:
            assert coordinator.entry.data[const.CONF_BED_TYPE] == const.BED_TYPE_LIMOSS
            # has_massage is a shared setting the new profile reads too.
            assert not (
                const.LIMOSS_REMOTE_CONFIG_KEYS - {const.CONF_HAS_MASSAGE}
            ).intersection(coordinator.entry.data)
            assert coordinator.entry.data[const.CONF_LIMOSS_REMOTE_STATE] == before[const.CONF_LIMOSS_REMOTE_STATE]
            assert not controller.underbed_light and not controller.massage
    assert payloads == ["7100000000"] * 10 + ["6600000000"] * (2 if failure else 10)


async def test_leaving_remote_without_selected_features_stays_offline(hass):
    coordinator = actual_coordinator(
        hass, **{const.CONF_LIMOSS_REMOTE_STATE: {"capabilities": CAPS}}
    )
    await coordinator.async_prime_offline_controller()
    coordinator.async_ensure_connected = AsyncMock(side_effect=AssertionError("Local profile edit"))
    flow = AdjustableBedOptionsFlow(coordinator.entry)
    flow.hass, flow.handler = hass, coordinator.entry.entry_id
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock()):
        assert (await flow.async_step_settings({const.CONF_BED_TYPE: const.BED_TYPE_LIMOSS}))["type"] == "form"
        assert (await flow.async_step_settings({}))["type"] == "create_entry"
    coordinator.async_ensure_connected.assert_not_awaited()
