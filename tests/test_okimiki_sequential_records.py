"""Registered parent/Both record edits across real two-receiver pair lanes."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak import BleakClient
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import (
    _async_ensure_paired_device_registry,
    _build_paired_children,
    const,
    services,
)
from custom_components.adjustable_bed.beds.okimiki import protocol as p
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    PairedSideError,
)
from custom_components.adjustable_bed.profile_id import with_profile_ids
from custom_components.adjustable_bed.services import async_register_services
from tests.test_okimiki import virtual as virtual
from tests.test_paired_setup import LEFT_ADDR, RIGHT_ADDR, _paired_entry_data


def mutation(data: bytes) -> bool:
    return len(data) >= 7 and data[2:4] == b"\x20\x05" and (data[4], data[5]) in ((1, 1), (2, 1))


@pytest.fixture
async def record_pair(
    hass,
    mock_coordinator_connected,
    mock_establish_connection,
    mock_async_ble_device_from_address,
    virtual,
):
    pairs = []
    deliveries = []
    mock_async_ble_device_from_address.side_effect = lambda _hass, address, **_: SimpleNamespace(
        address=address, name="Okimiki", details={"source": "local"}
    )

    async def build(mode, *, deferred=False, right_product="KWRN"):
        data = _paired_entry_data()
        data[const.CONF_BED_TYPE] = "okimiki"
        data[const.CONF_CONNECTION_MODE] = const.CONNECTION_MODE_IDLE
        for descriptor, product in zip(
            data[const.CONF_PAIR_CHILDREN], ("KWRN", right_product), strict=True
        ):
            descriptor.update(
                {
                    const.CONF_BED_TYPE: "okimiki",
                    const.CONF_PROTOCOL_VARIANT: product,
                    const.CONF_HAS_MASSAGE: False,
                }
            )
            descriptor.pop("capabilities", None)
        entry = MockConfigEntry(
            domain=const.DOMAIN, title="Record pair", data=with_profile_ids(data)
        )
        entry.add_to_hass(hass)
        entry.mock_state(hass, ConfigEntryState.LOADED)
        pair = PairedBedCoordinator(
            hass, entry, _build_paired_children(hass, entry), connection_mode=mode
        )
        pairs.append(pair)
        hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = pair
        for child in pair.children.values():
            child._max_retries = 1
            await child.async_prime_offline_controller()
        _async_ensure_paired_device_registry(hass, entry, pair)
        parent = dr.async_get(hass).async_get_device_by_identifier(
            next(iter(pair.device_info["identifiers"])), entry.entry_id
        )
        assert parent is not None
        state = SimpleNamespace(
            pair=pair,
            entry=entry,
            parent=parent,
            records={
                LEFT_ADDR: p.Alarm(1, 17, 7, 30, 0x59, 0x89),
                RIGHT_ADDR: p.Alarm(1, 34, 8, 45, 0x45, 0x05),
            },
            sessions={LEFT_ADDR: [], RIGHT_ADDR: []},
            writes=[],
            queries=[],
            stale_only=False,
        )

        async def establish(_class, device, _name, **kwargs):
            address = device.address
            client = MagicMock(spec=BleakClient)
            client.address = address
            client.is_connected = True
            client.mtu_size = 23
            route = codec.TRANSPORTS["w1"]
            tx = SimpleNamespace(
                uuid=route.write_uuid, handle=169, properties=["write"], descriptors=[]
            )
            rx = SimpleNamespace(
                uuid=route.notify_uuid, handle=170, properties=["notify"], descriptors=[]
            )
            client.services = [SimpleNamespace(uuid=route.service_uuid, characteristics=[tx, rx])]
            session = SimpleNamespace(client=client, callback=None)
            state.sessions[address].append(session)

            async def subscribe(_characteristic, callback):
                session.callback = callback

            async def disconnect():
                client.is_connected = False
                kwargs["disconnected_callback"](client)

            async def report(data):
                if deferred:
                    await asyncio.sleep(0.01)
                session.callback(None, bytearray(data))

            async def write(_characteristic, data, **_):
                data = bytes(data)
                state.writes.append((address, len(state.sessions[address]), data))
                if data == codec.function(1, action="deviceFunctionItemCheckLight"):
                    # Menus are fresh for every actual subscription. Records
                    # deliberately require the integration's proven list query.
                    packet = bytes.fromhex("6e09010078")
                elif data == codec.record(5, 1, 0, (0,)):
                    state.queries.append((address, len(state.sessions[address])))
                    row = state.records[address]
                    packet = codec.record_20_len(
                        5, 1, 2, (row.id, row.reserved, row.hour, row.minute, row.opcode, row.mask)
                    )
                    if state.stale_only and len(state.sessions[address]) > 1:
                        state.sessions[address][0].callback(None, bytearray(packet))
                        return
                else:
                    return
                if deferred:
                    deliveries.append(asyncio.create_task(report(packet)))
                else:
                    await report(packet)

            client.start_notify = AsyncMock(side_effect=subscribe)
            client.stop_notify = AsyncMock()
            client.disconnect = AsyncMock(side_effect=disconnect)
            client.write_gatt_char = AsyncMock(side_effect=write)
            return client

        mock_establish_connection.side_effect = establish
        await async_register_services(hass)
        return state

    yield build
    for pair in pairs:
        await pair.async_shutdown()
    for task in deliveries:
        if not task.done():
            task.cancel()
    await asyncio.gather(*deliveries, return_exceptions=True)


async def call(hass, state, operation):
    """Turn slot 1 off ("enable") or rewrite it ("repeat") through set_alarm."""
    fields = (
        {"enabled": False}
        if operation == "enable"
        else {"enabled": True, "time": "06:15:00", "wake_action": "memory_2", "weekdays": ["monday"]}
    )
    await hass.services.async_call(
        const.DOMAIN,
        "set_alarm",
        {"device_id": state.parent.id, "side": "both", "slot": 1, **fields},
        blocking=True,
    )


def edits(state, address):
    return [data for owner, _session, data in state.writes if owner == address and mutation(data)]


@pytest.mark.parametrize("mode", ("sequential", "concurrent"))
@pytest.mark.parametrize("operation", ("enable", "repeat"))
@pytest.mark.parametrize("deferred", (False, True))
async def test_registered_both_record_actions_rebuild_from_matching_live_receivers(
    hass, record_pair, mode, operation, deferred
):
    state = await record_pair(mode, deferred=deferred)
    await call(hass, state, operation)
    for address, row in state.records.items():
        writes = edits(state, address)
        assert len(writes) == 1
        # Turning off keeps the received record; a complete alarm for a slot this
        # session never read is written whole, with a zero reserved byte.
        expected = (
            (row.id, row.reserved, row.hour, row.minute, row.opcode, row.mask & 0xFE)
            if operation == "enable"
            else (row.id, 0, 6, 15, 0x2F, p.repeat_mask((0,), True))
        )
        assert writes[0][6:-1] == bytes(expected)
        expected_sessions = 2 if mode == "sequential" else 1
        assert len(state.sessions[address]) == expected_sessions
        # Turning off reads each session's record first; a complete new alarm does not.
        assert [session for owner, session in state.queries if owner == address] == (
            list(range(1, expected_sessions + 1)) if operation == "enable" else []
        )
    assert state.sessions[LEFT_ADDR][0].client is not state.sessions[RIGHT_ADDR][0].client


def after_preflight(monkeypatch, effect):
    """Run ``effect`` after set_alarm checked every target, before any write."""
    original = services._execute_sided
    phases = 0

    async def execute(*args, **kwargs):
        nonlocal phases
        phases += 1
        await original(*args, **kwargs)
        if phases == 1:
            await effect()

    monkeypatch.setattr(services, "_execute_sided", execute)


@pytest.mark.parametrize("side", ("left", "right"))
async def test_changed_record_after_sequential_handoff_rejects_that_receiver(
    hass, record_pair, monkeypatch, side
):
    state = await record_pair("sequential", deferred=True)
    address = state.pair.children[side].address

    async def drift():
        state.records[address] = replace(state.records[address], reserved=99)

    after_preflight(monkeypatch, drift)
    with pytest.raises(PairedSideError) as failure:
        await call(hass, state, "enable")
    assert set(failure.value.side_errors) == {side}
    assert isinstance(failure.value.side_errors[side], ServiceValidationError)
    assert (
        str(failure.value.side_errors[side]) == "The Okimiki alarm record changed after validation"
    )
    assert not edits(state, address)
    assert len(edits(state, LEFT_ADDR)) == (1 if side == "right" else 0)
    assert not edits(state, RIGHT_ADDR)


@pytest.mark.parametrize("mode", ("sequential", "concurrent"))
@pytest.mark.parametrize("fault", ("invalid_second", "stop", "owner_replaced"))
async def test_all_target_barrier_and_admission_keep_requested_mutations_zero(
    hass, record_pair, monkeypatch, mode, fault
):
    state = await record_pair(mode, right_product="IPRM" if fault == "invalid_second" else "KWRN")

    async def interrupt():
        if fault == "stop":
            await state.pair.async_stop_command(side="both")
        elif fault == "owner_replaced":
            replacement = _build_paired_children(hass, state.entry)["left"]
            await replacement.async_prime_offline_controller()
            state.pair._children["left"] = replacement

    after_preflight(monkeypatch, interrupt)
    if fault == "stop":
        await call(hass, state, "enable")
    else:
        with pytest.raises(HomeAssistantError):
            await call(hass, state, "enable")
    assert not edits(state, LEFT_ADDR) and not edits(state, RIGHT_ADDR)


async def test_reconnect_after_check_rereads_the_record_before_writing(
    hass, record_pair, monkeypatch
):
    state = await record_pair("concurrent")

    async def reconnect():
        child = state.pair.children["left"]
        await child.async_disconnect("manual")
        assert await child.async_connect()

    after_preflight(monkeypatch, reconnect)
    await call(hass, state, "enable")
    # The new session's own list reply supplies the record; no old bytes are reused.
    assert [session for owner, session in state.queries if owner == LEFT_ADDR] == [1, 2]
    row = state.records[LEFT_ADDR]
    assert edits(state, LEFT_ADDR) == [replace(row, mask=row.mask & 0xFE).frame()]


async def test_old_subscription_cannot_supply_record_after_sequential_handoff(
    hass, record_pair, monkeypatch
):
    state = await record_pair("sequential")

    async def stale():
        state.stale_only = True

    after_preflight(monkeypatch, stale)
    with pytest.raises(PairedSideError) as failure:
        await call(hass, state, "enable")
    assert set(failure.value.side_errors) == {"left"}
    assert isinstance(failure.value.side_errors["left"], ServiceValidationError)
    assert (
        str(failure.value.side_errors["left"])
        == "The bed did not report current Okimiki alarm data"
    )
    assert not edits(state, LEFT_ADDR) and not edits(state, RIGHT_ADDR)
