"""Native P1 massage switch delivery, session and per-side behavior."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak import BleakClient
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.keeson import powersbedding as module
from custom_components.adjustable_bed.command_scheduler import current_command_context
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles import powersbedding as app
from custom_components.adjustable_bed.runtime_data import entry_runtime
from scripts.wire_snapshot import FakeClock, virtual_time
from tests.test_paired_setup import LEFT_ADDR, RIGHT_ADDR, _paired_entry_data
from tests.test_powersbedding import gatt, make_bed, packets

ADDRESS = "AA:BB:CC:DD:15:61"


@pytest.fixture
async def native(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    mock_async_ble_device_from_address,
    enable_custom_integrations,
):
    mock_async_ble_device_from_address.return_value.name = "okin-Powers"
    mock_bleak_client.services = gatt()
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="PowersBedding",
        unique_id=ADDRESS,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "PowersBedding",
            const.CONF_BED_TYPE: "powersbedding",
            const.CONF_BLE_DEVICE_NAME: "okin-Powers",
            const.CONF_HAS_MASSAGE: True,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    runtime = entry_runtime(hass, entry.entry_id)
    assert isinstance(runtime, AdjustableBedCoordinator)
    bed = runtime.controller
    assert isinstance(bed, module.PowersBeddingController)
    registry = er.async_get(hass)
    eid = registry.async_get_entity_id(
        "switch", const.DOMAIN, f"{ADDRESS}_controller_switch_powersbedding_massage"
    )
    assert eid is not None
    for suffix in (
        "powersbedding_start",
        "powersbedding_stop",
        "massage_all_off",
        "massage_all_toggle",
    ):
        assert registry.async_get_entity_id("button", const.DOMAIN, f"{ADDRESS}_{suffix}") is None
    with virtual_time(FakeClock()):
        await runtime.async_execute_controller_command(lambda c: c.set_massage_timer(10))
    mock_bleak_client.write_gatt_char.reset_mock()
    try:
        yield SimpleNamespace(
            hass=hass, entry=entry, runtime=runtime, bed=bed, client=mock_bleak_client, eid=eid
        )
    finally:
        mock_bleak_client.write_gatt_char.side_effect = None
        assert await hass.config_entries.async_unload(entry.entry_id)


async def invoke(native, on):
    await native.hass.services.async_call(
        "switch", "turn_on" if on else "turn_off", {"entity_id": native.eid}, blocking=True
    )


def shown(native):
    state = native.hass.states.get(native.eid)
    assert state is not None
    return state.state


async def establish(native, on):
    with virtual_time(FakeClock()):
        await invoke(native, on)
    assert shown(native) == ("on" if on else "off")
    native.client.write_gatt_char.reset_mock()


async def test_native_switch_roundtrip_uses_original_sequences_and_assumed_state(native):
    assert shown(native) == "unknown"
    assert native.hass.states.get(native.eid).attributes["assumed_state"] is True
    assert native.hass.states.get(native.eid).attributes["card_section"] == "massage"
    for on in (True, False):
        with virtual_time(FakeClock()):
            await invoke(native, on)
        words = [base + int(on) for base in (0x11000010, 0x10000010, 0x10000020) for _ in range(2)]
        assert packets(native.client) == [app.normal("p1", word) for word in words]
        assert shown(native) == ("on" if on else "off")
        assert native.runtime.controller_state[module.MASSAGE_ON] is on
        native.client.write_gatt_char.reset_mock()


@pytest.mark.parametrize("on", (True, False))
async def test_no_completed_frame_preserves_known_switch_value(native, on):
    await establish(native, not on)
    native.client.write_gatt_char.side_effect = BleakError("no frame completed")
    with virtual_time(FakeClock()), pytest.raises(HomeAssistantError):
        await invoke(native, on)
    assert native.client.write_gatt_char.await_count == 1
    assert shown(native) == ("off" if on else "on")
    assert native.runtime.controller_state[module.MASSAGE_ON] is not on


@pytest.mark.parametrize("on", (True, False))
@pytest.mark.parametrize("interruption", ("cancel_event", "write_failure", "task_cancel"))
async def test_partial_sequence_is_unknown_for_real_native_switch(native, on, interruption):
    await establish(native, not on)
    cancelled_tasks = []
    original_wait = module.cancellable

    async def backend(*args, **kwargs):
        if interruption == "write_failure" and native.client.write_gatt_char.await_count == 2:
            raise BleakError("second frame failed")
        if interruption == "cancel_event":
            current_command_context().cancel_event.set()

    async def wait(operation, event):
        if interruption == "task_cancel" and native.client.write_gatt_char.await_count >= 2:
            operation.close()
            task = asyncio.current_task()
            cancelled_tasks.append(task)
            task.cancel()
            await asyncio.sleep(0)
        return await original_wait(operation, event)

    native.client.write_gatt_char.side_effect = backend
    with patch.object(module, "cancellable", new=wait), virtual_time(FakeClock()):
        if interruption == "write_failure":
            with pytest.raises(HomeAssistantError):
                await invoke(native, on)
        else:
            await invoke(native, on)
    if interruption == "task_cancel":
        assert cancelled_tasks  # The command worker received Task.cancel(), not only its event.
    assert shown(native) == "unknown"
    assert native.runtime.controller_state[module.MASSAGE_ON] is None


@pytest.mark.parametrize("on", (True, False))
@pytest.mark.parametrize("cancel_kind", ("event", "task"))
async def test_final_completed_frame_survives_late_cancel(native, on, cancel_kind):
    await establish(native, not on)

    worker = []
    send = native.bed._send

    async def capture_worker(*args, **kwargs):
        worker[:] = [asyncio.current_task()]
        await send(*args, **kwargs)

    async def cancel_last(*args, **kwargs):
        if native.client.write_gatt_char.await_count == 6:
            if cancel_kind == "event":
                current_command_context().cancel_event.set()
            else:
                worker[0].cancel()

    native.client.write_gatt_char.side_effect = cancel_last
    with patch.object(native.bed, "_send", new=capture_worker), virtual_time(FakeClock()):
        await invoke(native, on)
    assert native.client.write_gatt_char.await_count == 6
    assert shown(native) == ("on" if on else "off")
    assert native.runtime.controller_state[module.MASSAGE_ON] is on


async def test_disconnect_and_old_link_completion_cannot_claim_switch_state(native):
    await establish(native, False)

    async def replace_last(*args, **kwargs):
        if native.client.write_gatt_char.await_count == 6:
            native.bed._link = replace(native.bed._live())
            native.bed.forward_controller_state_updates(module.MASSAGE_ON(False))

    native.client.write_gatt_char.side_effect = replace_last
    with virtual_time(FakeClock()), pytest.raises(HomeAssistantError):
        await invoke(native, True)
    assert native.runtime.controller_state[module.MASSAGE_ON] is False
    native.client.write_gatt_char.side_effect = None
    assert await native.runtime.async_disconnect("intentional")
    assert native.runtime.controller_state.get(module.MASSAGE_ON) is None
    assert shown(native) != "on"


@pytest.mark.parametrize(
    "route,name,manufacturer",
    [
        ("p1", "okin-Powers", None),
        ("p2", "okin-Powers", b"BLE-4.0 Module"),
        ("p3", "smartbed-Powers", None),
    ],
)
async def test_switch_is_p1_only_and_other_routes_keep_proven_actions(route, name, manufacturer):
    _, _, bed = make_bed(name=name, manufacturer=manufacturer)
    await bed.async_discover_capabilities()
    assert [spec.key for spec in bed.controller_switch_specs] == (
        ["powersbedding_massage"] if route == "p1" else []
    )
    assert not bed.supports_massage_off_control
    assert not bed.supports_massage_toggle_control
    buttons = {spec.key: spec for spec in bed.controller_button_specs}
    assert not {"powersbedding_start", "powersbedding_stop"} & buttons.keys()
    actions = ("timer",) if route == "p1" else app.STEPS
    for action in actions:
        assert buttons[f"powersbedding_{action}"].translation_key in {
            "catalog_massage",
            "massage_all_toggle",
            "massage_head_up",
            "massage_head_down",
            "massage_foot_up",
            "massage_foot_down",
            "massage_timer_step",
        }
    assert bed.supports_massage_timer == (route == "p1")


@pytest.mark.parametrize("right_route", ("p1", "p2", "p3"))
async def test_actual_pair_routes_native_switch_and_steps_to_their_physical_side(
    hass,
    mock_coordinator_connected,
    mock_establish_connection,
    mock_async_ble_device_from_address,
    enable_custom_integrations,
    right_route,
):
    data = _paired_entry_data()
    data[const.CONF_BED_TYPE] = "powersbedding"
    clients = {}
    for side, address, route in (("left", LEFT_ADDR, "p1"), ("right", RIGHT_ADDR, right_route)):
        client = MagicMock(spec=BleakClient)
        client.address, client.is_connected, client.mtu_size = address, True, 23
        client.services = gatt(route == "p3", route == "p2")
        client.read_gatt_char = AsyncMock(return_value=b"BLE-4.0 Module")
        client.write_gatt_char, client.start_notify, client.stop_notify = (
            AsyncMock(),
            AsyncMock(),
            AsyncMock(),
        )

        async def disconnect(client=client):
            client.is_connected = False

        client.disconnect = AsyncMock(side_effect=disconnect)
        clients[address] = client
        child = next(c for c in data[const.CONF_PAIR_CHILDREN] if c[const.CONF_SIDE] == side)
        child.update(
            {
                const.CONF_BED_TYPE: "powersbedding",
                const.CONF_HAS_MASSAGE: True,
                const.CONF_BLE_DEVICE_NAME: "smartbed-Powers" if route == "p3" else "okin-Powers",
                "capabilities": {"powersbedding": {"route": route}},
            }
        )

    def device(_hass, address, **kwargs):
        return SimpleNamespace(
            address=address,
            name="smartbed-Powers"
            if address == RIGHT_ADDR and right_route == "p3"
            else "okin-Powers",
            details={"source": "local"},
        )

    async def connect(_class, device, *args, **kwargs):
        clients[device.address].is_connected = True
        return clients[device.address]

    mock_async_ble_device_from_address.side_effect = device
    mock_establish_connection.side_effect = connect
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Paired PowersBedding",
        data=data,
        unique_id="powers-pair",
        version=4,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    pair = entry_runtime(hass, entry.entry_id)
    registry = er.async_get(hass)

    def entity(domain, address, suffix):
        return registry.async_get_entity_id(domain, const.DOMAIN, f"{address}_{suffix}")

    left_switch = entity("switch", LEFT_ADDR, "controller_switch_powersbedding_massage")
    right_switch = entity("switch", RIGHT_ADDR, "controller_switch_powersbedding_massage")
    assert left_switch is not None
    assert bool(right_switch) == (right_route == "p1")
    for client in clients.values():
        client.write_gatt_char.reset_mock()
    try:
        with virtual_time(FakeClock()):
            await hass.services.async_call(
                "switch", "turn_on", {"entity_id": left_switch}, blocking=True
            )
        assert packets(clients[LEFT_ADDR]) and not packets(clients[RIGHT_ADDR])
        assert pair.children["left"].controller_state[module.MASSAGE_ON] is True
        assert pair.children["right"].controller_state.get(module.MASSAGE_ON) is None
        clients[LEFT_ADDR].write_gatt_char.reset_mock()
        if right_switch:
            with virtual_time(FakeClock()):
                await hass.services.async_call(
                    "switch", "turn_off", {"entity_id": right_switch}, blocking=True
                )
            assert pair.children["right"].controller_state[module.MASSAGE_ON] is False
        else:
            toggle = entity("button", RIGHT_ADDR, "powersbedding_toggle")
            assert toggle is not None
            with virtual_time(FakeClock()):
                await hass.services.async_call(
                    "button", "press", {"entity_id": toggle}, blocking=True
                )
            assert packets(clients[RIGHT_ADDR]) == [
                app.normal(right_route, 0x100),
                *([b"\x00\xb0"] if right_route == "p3" else []),
            ]
        assert not packets(clients[LEFT_ADDR]) and packets(clients[RIGHT_ADDR])
        assert pair.children["left"].controller_state[module.MASSAGE_ON] is True
    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)
