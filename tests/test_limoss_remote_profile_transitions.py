"""Cached diagnostic values and transactional options profile boundaries."""

import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.codec import limoss as codec
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


@pytest.mark.parametrize("failure", [None, "error", "cancel"])
async def test_leaving_remote_finishes_old_native_off_transaction_before_save(
    hass, enable_custom_integrations, failure
):
    """The guided change to the generic controls sends the app's OFF commands first."""
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
        opcode = codec.decrypt(packet[1:9])[1]
        payload = {2: "0208120008", 0: "0001020304", 1: "0101020304"}[opcode]
        callback = client.start_notify.call_args.args[1]
        callback(char, bytearray(codec.frame(bytes.fromhex(payload), 0)))

    client.write_gatt_char.side_effect = startup
    await coordinator.async_start_notify()
    before = deepcopy(dict(coordinator.entry.data))
    client.write_gatt_char.reset_mock()
    payloads = []
    entered = asyncio.Event()
    held = asyncio.Event()

    async def write(char, packet, **kwargs):
        assert coordinator.entry.data == before
        payloads.append(codec.decrypt(packet[1:9])[1:6].hex())
        if len(payloads) == 12:
            if failure == "error":
                raise ConnectionError("OFF failed after partial hardware success")
            if failure == "cancel":
                entered.set()
                await held.wait()

    client.write_gatt_char.side_effect = write
    manager = hass.config_entries.flow
    with patch.object(hass.config_entries, "async_reload", new=AsyncMock()) as reload:
        first = await manager.async_init(
            const.DOMAIN,
            context={"source": SOURCE_RECONFIGURE, "entry_id": coordinator.entry.entry_id},
        )
        assert first["step_id"] == "limoss_family"
        first = await manager.async_configure(first["flow_id"], {"choice": "generic"})
        assert first["step_id"] == "migration_confirm" and coordinator.entry.data == before
        client.write_gatt_char.assert_not_awaited()
        if failure == "cancel":
            save = asyncio.create_task(
                manager.async_configure(first["flow_id"], {"action": "apply"})
            )
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
            result = await manager.async_configure(first["flow_id"], {"action": "apply"})
            if failure == "error":
                assert result.get("errors") == {"base": "limoss_remote_feature_update_failed"}
            else:
                assert result["reason"] == "migration_applied"
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


