"""Actual sequential-pair admission and offline-sibling public release."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.svane import SvaneController
from custom_components.adjustable_bed.const import (
    BED_TYPE_SVANE,
    CONF_BED_TYPE,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_PAIR_CONNECTION_MODE,
    CONF_PAIR_ID,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    PAIR_CONNECTION_MODE_SEQUENTIAL,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
    SVANE_VARIANT_JMC,
    SVANE_VARIANT_MULTI,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.services import async_register_services
from tests.test_svane import make_controller


@pytest.fixture
async def sequential_pair(hass, request, monkeypatch):
    profile = request.param
    children, clients, records = {}, {}, []
    clock = [0.0]
    local_asyncio = SimpleNamespace(**vars(asyncio))
    local_asyncio.get_running_loop = lambda: SimpleNamespace(time=lambda: clock[0])
    monkeypatch.setattr("custom_components.adjustable_bed.beds.svane.asyncio", local_asyncio)

    async def advance(seconds):
        clock[0] += seconds
        await asyncio.sleep(0)

    for side, address in [(SIDE_LEFT, "AA:BB:CC:DD:01:01"), (SIDE_RIGHT, "AA:BB:CC:DD:01:02")]:
        entry = MockConfigEntry(domain=DOMAIN, data={
            CONF_ADDRESS: address, CONF_NAME: side, CONF_BED_TYPE: BED_TYPE_SVANE,
            CONF_PROTOCOL_VARIANT: SVANE_VARIANT_JMC if profile == "jmc" else SVANE_VARIANT_MULTI,
            CONF_DISCONNECT_AFTER_COMMAND: False,
        })
        entry.add_to_hass(hass)
        child = AdjustableBedCoordinator(hass, entry)
        await child.async_prime_offline_controller()
        assert isinstance(child.capability_controller, SvaneController)
        client = make_controller(profile).client
        client.is_connected = False
        clients[side], children[side] = client, child

        async def connect(*args, target=child, wire=client, child_side=side, **kwargs):
            assert not any(other.is_connected for other in children.values() if other is not target), "two live links"
            if not target.is_connected:
                capability = target.capability_controller
                assert isinstance(capability, SvaneController)
                wire.is_connected = True
                target._client = wire
                target._controller = SvaneController(target, profile=profile, session=capability.session)
                target._controller._motor_wait = advance
                records.append((child_side, "connect"))
            return True

        async def disconnect(*args, target=child, wire=client, child_side=side, **kwargs):
            records.append((child_side, "disconnect"))
            wire.is_connected = False
            target._client = target._controller = None
            return True

        async def write(role, payload, child_side=side, **kwargs):
            records.append((child_side, bytes(payload).hex()))

        client.write_gatt_char.side_effect = write
        child.async_connect = AsyncMock(side_effect=connect)
        child.async_ensure_connected = AsyncMock(side_effect=connect)
        child.async_disconnect = AsyncMock(side_effect=disconnect)
    parent = MockConfigEntry(domain=DOMAIN, data={
        CONF_PAIR_ID: "seq", CONF_NAME: "Pair", CONF_PAIR_CONNECTION_MODE: PAIR_CONNECTION_MODE_SEQUENTIAL,
    })
    parent.add_to_hass(hass)
    pair = PairedBedCoordinator(hass, parent, children)
    await async_register_services(hass)
    try:
        yield pair, children, clients, records, clock
    finally:
        for child in children.values():
            child._cancel_disconnect_timer()
            await child._command_scheduler.async_shutdown()


@pytest.mark.parametrize("sequential_pair", ["multi", "jmc"], indirect=True)
async def test_public_both_release_signals_moving_side_with_offline_sibling(hass, sequential_pair):
    pair, children, clients, records, clock = sequential_pair
    left = children[SIDE_LEFT]
    await left.async_connect()
    started = asyncio.Event()
    controller = left.controller
    assert isinstance(controller, SvaneController)

    async def waiting(seconds):
        started.set()
        await controller._wake.wait()

    connect = left.async_connect.side_effect

    async def connect_waiting(*args, **kwargs):
        nonlocal controller
        result = await connect(*args, **kwargs)
        controller = left.controller
        assert isinstance(controller, SvaneController)
        controller._motor_wait = waiting
        return result

    controller._motor_wait = waiting
    left.async_connect.side_effect = connect_waiting
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
               return_value=([(pair, SIDE_LEFT)], [])):
        held = asyncio.create_task(hass.services.async_call(DOMAIN, "hold_control", {
            "device_id": "pair", "control": "head_up", "duration": .2,
        }, blocking=True))
        try:
            async with asyncio.timeout(1):
                await started.wait()
                with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
                           return_value=([(pair, SIDE_BOTH)], [])):
                    await hass.services.async_call(DOMAIN, "svane_release_axis", {
                        "device_id": "pair", "motor": "head",
                    }, blocking=True)
                await held
            assert children[SIDE_RIGHT].controller is None
            assert not clients[SIDE_RIGHT].write_gatt_char.await_count
            assert records[-2][1] in ("0000", "100000000000")
            assert not controller._started
        finally:
            held.cancel()
            await asyncio.gather(held, return_exceptions=True)


@pytest.mark.parametrize("sequential_pair", ["multi", "jmc"], indirect=True)
@pytest.mark.parametrize("endpoint", ["hold_control", "timed_move"])
async def test_public_both_preflight_never_opens_two_links(hass, sequential_pair, endpoint):
    pair, children, clients, records, clock = sequential_pair
    data = {"device_id": "pair", "control": "head_up", "duration": .2} if endpoint == "hold_control" else {
        "device_id": "pair", "motor": "back", "direction": "up", "duration_ms": 200,
    }
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
               return_value=([(pair, SIDE_BOTH)], [])):
        await hass.services.async_call(DOMAIN, endpoint, data, blocking=True)
    assert all(client.write_gatt_char.await_count for client in clients.values())
    assert all(not child.is_connected for child in children.values())
    for side in (SIDE_LEFT, SIDE_RIGHT):
        assert (side, "connect") in records and (side, "disconnect") in records


@pytest.mark.parametrize("sequential_pair", ["multi", "jmc"], indirect=True)
@pytest.mark.parametrize("endpoint", ["hold_control", "timed_move"])
async def test_later_sequential_invalid_role_prevents_all_movement(hass, sequential_pair, endpoint):
    pair, children, clients, records, clock = sequential_pair
    clients[SIDE_RIGHT].services[0 if sequential_pair[1][SIDE_RIGHT].capability_controller.profile == "multi" else 3].characteristics = []
    data = {"device_id": "pair", "control": "head_up", "duration": .2} if endpoint == "hold_control" else {
        "device_id": "pair", "motor": "back", "direction": "up", "duration_ms": 200,
    }
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
               return_value=([(pair, SIDE_BOTH)], [])), pytest.raises(HomeAssistantError):
        await hass.services.async_call(DOMAIN, endpoint, data, blocking=True)
    assert all(not client.write_gatt_char.await_count for client in clients.values())
    assert all(not child.is_connected for child in children.values())
