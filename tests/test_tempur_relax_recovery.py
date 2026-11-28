"""Deferred Linak authentication, same-link recovery and native late entities."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import button, const, cover, services
from custom_components.adjustable_bed.beds.linak.services import async_register_linak_services
from custom_components.adjustable_bed.beds.linak.tempur_relax import TempurRelaxController
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from tests.conftest import TEST_ADDRESS
from tests.hold_lease_wire import virtual_clock
from tests.test_carpe_diem import frames, shutdown
from tests.test_linak import ESPHOME_PROXY_PATH
from tests.test_tempur_relax import runtime


@pytest.mark.parametrize(
    "recovery", ["ordinary", "grouped", "timed", "reconnect", "grouped_reconnect", "probe_retry"]
)
async def test_deferred_mask_recovers_and_adds_omitted_entities(hass, recovery):
    c = runtime(hass)
    c._controller = TempurRelaxController(c)
    c._async_refresh_controller_auth = (
        AdjustableBedCoordinator._async_refresh_controller_auth.__get__(c)
    )
    client = c.client
    mask_reads = 0

    async def read(uuid):
        nonlocal mask_reads
        if uuid == const.LINAK_POSITION_MASK_UUID:
            mask_reads += 1
            if mask_reads == 1:
                raise BleakError("Insufficient authentication")
            return b"\xc0"
        return bytes(4)

    client.services.get_service.side_effect = lambda uuid: (
        SimpleNamespace() if uuid == const.LINAK_POSITION_SERVICE_UUID else None
    )
    client.read_gatt_char = AsyncMock(side_effect=read)
    if recovery == "probe_retry":
        client.services.get_characteristic.return_value = SimpleNamespace(
            properties=["write-without-response"]
        )
        rejected = False

        async def write(_uuid, frame, **_kwargs):
            nonlocal rejected
            if frame == bytes.fromhex("ff00") and not rejected:
                rejected = True
                raise BleakError("Insufficient authentication")

        client.write_gatt_char.side_effect = write
    c.entry.mock_state(hass, ConfigEntryState.LOADED)
    hass.data.setdefault(const.DOMAIN, {})[c.entry.entry_id] = c
    covers, buttons = [], []
    with patch(
        "custom_components.adjustable_bed.beds.linak.controller.async_path_for_source",
        return_value=None,
    ):
        await c.controller.async_discover_capabilities()
        await c.controller.start_notify()
        assert c.controller._capability_discovery_deferred
        await cover.async_setup_entry(hass, c.entry, lambda entities: covers.extend(entities))
        await button.async_setup_entry(hass, c.entry, lambda entities: buttons.extend(entities))
        assert covers == []
        assert not any(entity.unique_id.endswith("_preset_memory_1") for entity in buttons)
        if recovery == "grouped_reconnect":
            c.cache_capability_controller()
            c._controller = None
            c._client = None
            client.is_connected = False

            async def reconnect(*_args, **_kwargs):
                if c.client is None:
                    c._client = MagicMock(
                        is_connected=True,
                        services=client.services,
                        read_gatt_char=AsyncMock(side_effect=read),
                        start_notify=AsyncMock(),
                        stop_notify=AsyncMock(),
                        disconnect=AsyncMock(),
                        write_gatt_char=AsyncMock(),
                    )
                    c._controller = await create_controller(c, "linak", "tempur_relax", c.client)
                    await c.controller.async_discover_capabilities()
                    await c.controller.start_notify()
                return True

            c.async_ensure_connected = AsyncMock(side_effect=reconnect)
        if recovery == "reconnect":
            c._client = MagicMock(
                is_connected=True,
                services=client.services,
                read_gatt_char=AsyncMock(side_effect=read),
                start_notify=AsyncMock(),
                stop_notify=AsyncMock(),
                disconnect=AsyncMock(),
                write_gatt_char=AsyncMock(),
            )
            c._controller = await create_controller(c, "linak", "tempur_relax", c.client)
            await c.controller.async_discover_capabilities()
            await c.controller.start_notify()
        elif recovery in {"ordinary", "probe_retry"}:
            with virtual_clock():
                await c.async_execute_controller_command(lambda ctrl: ctrl.move_back_up())
            assert c.client is client
            assert frames(client)[0] == "ff00"
            offset = 2 if recovery == "probe_retry" else 1
            assert frames(client)[:offset] == ["ff00"] * offset
            assert set(frames(client)[offset:-1]) == {"0b00"}
            assert frames(client)[-1] == "ff00"
            if recovery == "probe_retry":
                assert all(
                    call.kwargs["response"] is False
                    for call in client.write_gatt_char.call_args_list
                )
        else:
            device = dr.async_get(hass).async_get_or_create(
                config_entry_id=c.entry.entry_id,
                identifiers={(const.DOMAIN, c.address)},
            )
            if recovery == "timed":
                await services.async_register_services(hass)
                action, fields, word = "timed_move", {"motor": "back"}, "0b00"
            else:
                async_register_linak_services(hass)
                action, fields, word = "linak_move_sections", {"sections": ["back", "legs"]}, "3700"
            with virtual_clock():
                await hass.services.async_call(
                    const.DOMAIN,
                    action,
                    {"device_id": [device.id], "direction": "up", "duration_ms": 250, **fields},
                    blocking=True,
                )
            if recovery == "grouped_reconnect":
                assert c.client is not client and frames(client) == []
                assert frames(c.client) == [word, word, word, "ff00"]
            else:
                assert c.client is client
                assert frames(client) == ["ff00", word, word, word, "ff00"]
        assert mask_reads == 2
        assert not c.controller._capability_discovery_deferred
        assert c._offline_controller is c.controller
        assert {entity.entity_description.key for entity in covers} == {"back", "legs"}
        assert any(entity.unique_id.endswith("_preset_memory_1") for entity in buttons)
        identities = [entity.unique_id for entity in (*covers, *buttons)]
        assert len(identities) == len(set(identities))
    await shutdown(c)


async def test_tempur_uses_existing_proxy_encryption_before_capability_read(hass):
    c = runtime(hass)
    c._controller = TempurRelaxController(c)
    order = []
    c.client.pair = AsyncMock(side_effect=lambda: order.append("pair"))
    c.client.services.get_service.side_effect = lambda uuid: (
        SimpleNamespace() if uuid == const.LINAK_POSITION_SERVICE_UUID else None
    )

    async def read(uuid):
        assert uuid == const.LINAK_POSITION_MASK_UUID
        order.append("mask")
        return b"\xc0"

    c.client.read_gatt_char = AsyncMock(side_effect=read)
    with (
        patch(
            "custom_components.adjustable_bed.beds.linak.controller.async_path_for_source",
            return_value=ESPHOME_PROXY_PATH,
        ),
        patch(
            "custom_components.adjustable_bed.beds.linak.controller.bluetooth.async_last_service_info",
            return_value=None,
        ),
    ):
        await c.controller.async_discover_capabilities()
    assert order == ["pair", "mask"]
    assert c.controller.simultaneous_movement_axes == ("back", "legs")
    await shutdown(c)


def mocked_receiver(*answers):
    masks = iter(answers)
    calls = []
    client = MagicMock(is_connected=True)
    client.services.get_service.side_effect = lambda uuid: (
        SimpleNamespace() if uuid == const.LINAK_POSITION_SERVICE_UUID else None
    )
    client.services.get_characteristic.return_value = SimpleNamespace(properties=["write"])
    client.write_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.disconnect = AsyncMock(side_effect=lambda: setattr(client, "is_connected", False))

    async def read(uuid):
        if uuid == const.LINAK_POSITION_MASK_UUID:
            calls.append(uuid)
            answer = next(masks)
            if answer is None:
                raise BleakError("Insufficient Authentication")
            return bytes((answer,))
        return bytes(4)

    client.read_gatt_char = AsyncMock(side_effect=read)
    return client, calls



@pytest.mark.parametrize("action", ["linak_move_sections", "timed_move"])
@pytest.mark.parametrize("initial", ["released", "left_live", "right_without_back", "cold"])
@pytest.mark.parametrize("missing_controller", [False, True])
async def test_sequential_pair_deferred_preflight_uses_one_link(
    hass, mock_async_ble_device_from_address, action, initial, missing_controller
):
    from custom_components.adjustable_bed import _async_ensure_paired_device_registry
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    pair_id = "tempur-pair-s4"
    entry = MockConfigEntry(domain=const.DOMAIN, data={"pair_id": pair_id})
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    addrs = {"left": TEST_ADDRESS, "right": "AA:BB:CC:DD:EE:68"}
    children = {}
    setups = {}
    live = []
    overlaps = []
    clients = {}
    for side, address in addrs.items():
        child_entry = MockConfigEntry(
            domain=const.DOMAIN, title=side, unique_id=address,
            data={"address": address, "name": side, "bed_type": "linak",
                  "protocol_variant": "tempur_relax", "motor_count": 2,
                  "disable_angle_sensing": True, "connection_mode": "always"},
        )
        child_entry.add_to_hass(hass)
        children[side] = AdjustableBedCoordinator(hass, child_entry)
        mask = 0x40 if side == "right" and initial == "right_without_back" else 0xC0
        clients[side] = [
            mocked_receiver(None, mask)[0] if initial == "cold" else mocked_receiver(None)[0],
            mocked_receiver(None, mask)[0] if side == "left" and initial == "left_live"
            else mocked_receiver(mask)[0],
            mocked_receiver(mask)[0],
        ]
        setups[address] = iter(clients[side])
    pair = PairedBedCoordinator(hass, entry, children, connection_mode="sequential")
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = pair
    _async_ensure_paired_device_registry(hass, entry, pair)
    device = dr.async_get(hass).async_get_device_by_identifier((const.DOMAIN, pair_id), entry.entry_id)
    assert device
    await services.async_register_services(hass)

    mock_async_ble_device_from_address.side_effect = lambda _hass, address, **kwargs: (
        SimpleNamespace(address=address, name="Tempur", details={"source": "local"}, rssi=-60)
    )

    async def establish(_client_type, device, *_args, **_kwargs):
        active = [address for address, client in live if client.is_connected]
        if active:
            overlaps.append((active, device.address))
        client = next(setups[device.address])
        assert not active, "single-slot adapter already has a live receiver"
        live.append((device.address, client))
        return client

    with patch("custom_components.adjustable_bed.coordinator_connection.establish_connection",
               new=AsyncMock(side_effect=establish)), patch(
                   "custom_components.adjustable_bed.beds.linak.controller.async_path_for_source",
                   return_value=None,
               ):
        try:
            if initial != "cold":
                assert await pair.async_connect()
                assert all(not c.is_connected for c in children.values())
                assert all(
                    not c.capability_controller.controller_entity_discovery_complete
                    for c in children.values()
                )
            else:
                assert all(c.controller is None and c.capability_controller is None for c in children.values())
            assert not overlaps
            if initial == "left_live":
                assert await children["left"].async_connect()
                assert children["left"].is_connected
                assert not children["left"].controller.controller_entity_discovery_complete
            if missing_controller:
                from custom_components.adjustable_bed.profile_id import entry_profile_id

                children["right"]._controller = None
                children["right"]._offline_controller = None
                assert children["right"].capability_controller is None
                saved = dict(children["right"].entry.data)
                saved["profile_id"] = entry_profile_id(saved)
                saved.pop("protocol_variant")
                hass.config_entries.async_update_entry(children["right"].entry, data=saved)
            selectors = {"sections": ["back", "legs"]} if action == "linak_move_sections" else {
                "motor": "back"
            }
            async def invoke():
                with virtual_clock():
                    await hass.services.async_call(
                        const.DOMAIN, action,
                        {"device_id": [device.id], "direction": "up", "duration_ms": 250, **selectors},
                        blocking=True,
                    )

            if initial == "right_without_back":
                with pytest.raises(ServiceValidationError):
                    await invoke()
                # Every receiver is checked before either receives motion.
                assert all(not frames(client) for group in clients.values() for client in group)
            else:
                await invoke()
                movement = "3700" if action == "linak_move_sections" else "0b00"
                for side, group in clients.items():
                    if initial == "cold":
                        assert frames(group[0]) == ["ff00"]
                        assert frames(group[1]) == [movement, movement, movement, "ff00"]
                        assert frames(group[2]) == []
                    else:
                        assert frames(group[0]) == []
                        assert frames(group[1]) == (["ff00"] if side == "left" and initial == "left_live" else [])
                        assert frames(group[2]) == [movement, movement, movement, "ff00"]
                    assert children[side].capability_controller.simultaneous_movement_axes == ("back", "legs")
            assert all(not child.is_connected for child in children.values())
            assert not overlaps
        finally:
            await pair.async_shutdown()
