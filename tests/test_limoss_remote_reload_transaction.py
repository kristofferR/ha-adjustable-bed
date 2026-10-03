"""Real HA reload/unload waits for whole Remote service transactions."""

import asyncio
from contextlib import AsyncExitStack, ExitStack, asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest
from bleak.backends.device import BLEDevice
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const, services
from custom_components.adjustable_bed.adapter import AdapterSelectionResult
from custom_components.adjustable_bed.beds.limoss import LimossController
from custom_components.adjustable_bed.beds.limoss_remote_protocol import format_command
from tests.test_limoss_remote import make_controller
from tests.test_limoss_remote_config import app_data
from tests.test_limoss_remote_review_lifecycle import CAPS


@asynccontextmanager
async def loaded_runtime(hass, paired):
    addresses = ["AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02"] if paired else ["AA:BB:CC:DD:EE:01"]
    data = [app_data(**{
        "address": address,
        const.CONF_SIDE: side,
        const.CONF_DISCONNECT_AFTER_COMMAND: True,
        const.CONF_DISABLE_ANGLE_SENSING: True,
        const.CONF_LIMOSS_REMOTE_LIGHT: True,
        const.CONF_LIMOSS_REMOTE_MASSAGE: True,
        const.CONF_LIMOSS_REMOTE_STATE: {"capabilities": CAPS},
    }) for address, side in zip(addresses, (const.SIDE_LEFT, const.SIDE_RIGHT), strict=False)]
    entry = MockConfigEntry(domain=const.DOMAIN, version=4, data={
        const.CONF_PAIR_ID: "reload-review",
        const.CONF_PAIR_CONNECTION_MODE: const.PAIR_CONNECTION_MODE_SEQUENTIAL,
        const.CONF_PAIR_CHILDREN: data,
    } if paired else data[0])
    entry.add_to_hass(hass)
    clients = {address: make_controller().client for address in addresses}
    for client in clients.values():
        client.is_connected = False
    trace = []
    state = {"capacity": 8, "failure": None}
    entered, release = asyncio.Event(), asyncio.Event()
    for address, client in clients.items():
        async def disconnect(address=address, client=client):
            client.is_connected = False
            trace.append((address, "disconnect"))

        async def write(role, packet, *, address=address, client=client, **kwargs):
            opcode = LimossController._tea_decrypt(packet[1:9])[1]
            trace.append((address, opcode))
            if opcode in {0, 1, 2}:
                reply = {
                    2: bytes((2, 8, 0x12, 0, state["capacity"])),
                    0: bytes.fromhex("0001020304"),
                    1: bytes.fromhex("0101020304"),
                }[opcode]
                client.start_notify.call_args.args[1](role, bytearray(format_command(reply, 0)))
            elif opcode == 0x11 and state["failure"]:
                entered.set()
                if state["failure"] == "error":
                    raise ConnectionError("Memory write failed")
                await release.wait()

        client.disconnect = AsyncMock(side_effect=disconnect)
        client.write_gatt_char.side_effect = write

    async def adapter(hass, address, *args, **kwargs):
        return AdapterSelectionResult(BLEDevice(address, "App bed", {}), "local", -50, True, ["local"])

    async def establish(cls, device, name, **kwargs):
        if paired:
            assert not any(client.is_connected for client in clients.values()), "Opened two sequential BLE links"
        clients[device.address].is_connected = True
        trace.append((device.address, "connect"))
        return clients[device.address]

    with ExitStack() as stack:
        module = "custom_components.adjustable_bed.coordinator."
        for name, mock in [
            ("select_adapter", AsyncMock(side_effect=adapter)),
            ("establish_connection", AsyncMock(side_effect=establish)),
            ("close_stale_connections_by_address", AsyncMock()),
            ("discover_services", AsyncMock(return_value=True)),
        ]:
            stack.enter_context(patch(module + name, new=mock))
        stack.enter_context(patch(module + "client_source", return_value="local"))
        stack.enter_context(patch(module + "async_path_for_source", return_value=None))
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        original = hass.data[const.DOMAIN][entry.entry_id]
        children = list(original.children.values()) if paired else [original]
        for child in children:
            child.limoss_remote_memory_store.save(1, ((0, -1),))
        await hass.async_block_till_done()
        await original.async_disconnect(reason="initial idle")
        trace.clear()
        try:
            yield entry, original, children, trace, state, entered, release
        finally:
            release.set()
            await hass.async_block_till_done()
            await hass.config_entries.async_unload(entry.entry_id)
            await hass.async_block_till_done()


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.parametrize(("paired", "service", "changed"), [
    (False, "goto_preset", False),
    (False, "goto_preset", True),
    (True, "goto_preset", True),
    (True, "goto_preset", True),
    (True, "limoss_remote_features", True),
])
async def test_capability_reload_waits_for_real_public_transaction(hass, paired, service, changed):
    async with loaded_runtime(hass, paired) as (entry, original, children, trace, state, _, _):
        state["capacity"] = 7 if changed else 8
        preflight = services._preflight_live_limoss_remote

        async def preflight_then_disconnect(*args, **kwargs):
            await preflight(*args, **kwargs)
            for child in children:
                if child._disconnect_timer is not None:
                    # Fire the actual default handoff callback without waiting for wall time.
                    child._disconnect_timer.cancel()
                    child._schedule_idle_disconnect()
            await hass.async_block_till_done()
            assert hass.data[const.DOMAIN][entry.entry_id] is original
            assert not any(child.is_connected for child in children)

        data = {"preset": 1}
        if service == "goto_preset":
            data["duration"] = 0.1
        elif service == "limoss_remote_features":
            data = {"underbed_light": False, "massage": False}
        with (
            patch.object(services, "_resolve_sided_targets", return_value=([(original, const.SIDE_BOTH)], [])),
            patch.object(services, "_preflight_live_limoss_remote", side_effect=preflight_then_disconnect),
        ):
            await asyncio.wait_for(hass.services.async_call(
                const.DOMAIN, service, {"device_id": ["physical"], **data}, blocking=True,
            ), 8)
        if service == "limoss_remote_features":
            assert [opcode for _, opcode in trace].count(0x71) == 10 * len(children)
            assert [opcode for _, opcode in trace].count(0x66) == 10 * len(children)
        else:
            assert {address for address, opcode in trace if opcode == 0x11} == {child.address for child in children}
            assert sum(opcode == 0xFF for _, opcode in trace) >= 5 * len(children)
        assert all(child._capability_reload_deferrals == 0 for child in children)
        # End the final default handoff too: real async_reload unloads the old schedulers.
        for child in children:
            if child._disconnect_timer is not None:
                child._disconnect_timer.cancel()
                child._schedule_idle_disconnect()
        await hass.async_block_till_done()
        assert (hass.data[const.DOMAIN][entry.entry_id] is not original) == (changed or service == "limoss_remote_features")
        if changed or service == "limoss_remote_features":
            assert all(child._shutting_down for child in children)


@pytest.mark.usefixtures("enable_custom_integrations")
@pytest.mark.parametrize("failure", ["error", "cancel"])
async def test_failed_or_cancelled_public_transaction_releases_reload_after_native_cleanup(hass, failure):
    async with loaded_runtime(hass, True) as (entry, original, children, trace, state, entered, release):
        state.update(capacity=7, failure=failure)
        with patch.object(services, "_resolve_sided_targets", return_value=([(original, const.SIDE_BOTH)], [])):
            operation = asyncio.create_task(hass.services.async_call(
                const.DOMAIN, "goto_preset",
                {"device_id": ["physical"], "preset": 1, "duration": 0.1}, blocking=True,
            ))
            try:
                await asyncio.wait_for(entered.wait(), 3)
                if failure == "cancel":
                    operation.cancel()
                with pytest.raises((HomeAssistantError, asyncio.CancelledError, ConnectionError)):
                    await asyncio.wait_for(operation, 3)
            finally:
                release.set()
                operation.cancel()
                await asyncio.gather(operation, return_exceptions=True)
        assert all(child._capability_reload_deferrals == 0 for child in children)
        assert sum(opcode == 0xFF for _, opcode in trace) >= 5
        for child in children:
            if child._disconnect_timer is not None:
                child._disconnect_timer.cancel()
                child._schedule_idle_disconnect()
        await hass.async_block_till_done()
        assert hass.data[const.DOMAIN][entry.entry_id] is not original


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_unselected_sibling_reload_waits_for_selected_service_phases(hass):
    async with loaded_runtime(hass, True) as (entry, original, children, _, _, _, _):
        left, right = children
        preflight = services._preflight_live_limoss_remote

        async def changed_sibling_after_preflight(*args, **kwargs):
            await preflight(*args, **kwargs)
            right.remember_limoss_remote_data({"capabilities": {**CAPS, "memory_count": 7}})
            await hass.async_block_till_done()
            assert hass.data[const.DOMAIN][entry.entry_id] is original
            assert right._pending_capability_reload

        with (
            patch.object(services, "_resolve_sided_targets", return_value=([(original, const.SIDE_LEFT)], [])),
            patch.object(services, "_preflight_live_limoss_remote", side_effect=changed_sibling_after_preflight),
        ):
            await asyncio.wait_for(hass.services.async_call(
                const.DOMAIN, "goto_preset", {"device_id": ["physical"], "preset": 1}, blocking=True,
            ), 4)
        await hass.async_block_till_done()
        assert all(child._capability_reload_deferrals == 0 for child in children)
        assert hass.data[const.DOMAIN][entry.entry_id] is not original
        assert left._shutting_down and right._shutting_down


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_already_scheduled_reload_rechecks_nested_transaction_before_unloading(hass):
    async with loaded_runtime(hass, False) as (entry, original, children, _, _, _, _):
        child = children[0]
        async with AsyncExitStack() as transaction:
            async with child.async_command_operation_guard():
                # Schedule a reload that must first acquire the existing lane guard.
                child.remember_limoss_remote_data({"capabilities": {**CAPS, "memory_count": 7}})
                assert child._capability_reload_scheduled
                await transaction.enter_async_context(child.async_defer_capability_reload())
            async with child.async_defer_capability_reload():
                await hass.async_block_till_done()
                assert hass.data[const.DOMAIN][entry.entry_id] is original
                assert not child._capability_reload_scheduled
            await hass.async_block_till_done()
            assert child._pending_capability_reload and not child._capability_reload_scheduled
        await hass.async_block_till_done()
        assert child._capability_reload_deferrals == 0
        assert child._shutting_down
        assert hass.data[const.DOMAIN][entry.entry_id] is not original
