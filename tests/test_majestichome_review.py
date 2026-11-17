"""S1/S2: actual registered actions through reconnecting physical pair targets."""

import asyncio
from copy import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import (
    _async_ensure_paired_device_registry,
    _build_paired_children,
    const,
)
from custom_components.adjustable_bed.beds.majestichome import controller as bed
from custom_components.adjustable_bed.beds.majestichome import services
from custom_components.adjustable_bed.beds.majestichome.protocol import Alarm
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.profile_id import with_profile_ids
from custom_components.adjustable_bed.services import async_register_services
from tests.test_majestichome import GATT, notify, written
from tests.test_majestichome import clock as clock
from tests.test_majestichome_runtime import runtime as runtime
from tests.test_majestichome_runtime import settings
from tests.test_paired_setup import _paired_entry_data


def alarm_reply(alarm):
    frame = bytes(
        (
            0x6E,
            0x20,
            13,
            5,
            1,
            2,
            alarm.number,
            alarm.reserved,
            alarm.hour,
            alarm.minute,
            alarm.preset,
            alarm.repeat,
        )
    )
    return frame + bytes((sum(frame) & 255,))


@pytest.fixture
async def live_pair(hass, mock_coordinator_connected, clock):
    async def build(mode, *, delayed_clock=False):
        data = _paired_entry_data()
        data[const.CONF_BED_TYPE] = "majestichome"
        data[const.CONF_PAIR_CONNECTION_MODE] = mode
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
            title="Majestic review pair",
            data=with_profile_ids(data),
            version=5,
            state=ConfigEntryState.LOADED,
        )
        entry.add_to_hass(hass)
        children = _build_paired_children(hass, entry)
        pair = PairedBedCoordinator(hass, entry, children)
        hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = pair
        _async_ensure_paired_device_registry(hass, entry, pair)
        events, connections = [], dict.fromkeys(children, 0)
        records = {side: Alarm(1, 0, 7, 30, 0x2E, 249) for side in children}
        hooks = {}
        for side, child in children.items():
            await child.async_prime_offline_controller()

            async def connect(*, reset_timer=True, side=side, child=child):
                connections[side] += 1
                state = {"ready": False}
                client = MagicMock(is_connected=True)
                row = GATT[1]
                tx = SimpleNamespace(uuid=row["write"].lower(), properties=["write"], handle=1)
                rx = SimpleNamespace(
                    uuid=row["declared_notify"].lower(), properties=["notify"], handle=2
                )
                client.services = [
                    SimpleNamespace(uuid=row["service"].lower(), characteristics=[tx, rx])
                ]
                client.start_notify = AsyncMock()
                client.stop_notify = AsyncMock()

                async def disconnect():
                    client.is_connected = False

                client.disconnect = AsyncMock(side_effect=disconnect)

                async def write(_char, packet, **kwargs):
                    if state["ready"]:
                        events.append((side, bytes(packet)))
                    if packet.hex() == "6e08010178":
                        if not delayed_clock or state["ready"]:
                            hass.loop.call_soon(
                                child.controller._notification,
                                child.controller._link,
                                rx,
                                bytearray.fromhex("6e09010078"),
                            )
                    elif packet == bed.LIST_ALARMS:
                        if hook := hooks.get("query"):
                            hook(side, child, connections[side])
                        child.controller._notification(
                            child.controller._link, rx, bytearray(alarm_reply(records[side]))
                        )

                client.write_gatt_char = AsyncMock(side_effect=write)
                child._client = client
                child._controller = await create_controller(
                    child, "majestichome", child.entry.data[const.CONF_PROTOCOL_VARIANT], client
                )
                await child.controller.start_notify()
                state["ready"] = True
                return True

            child._async_connect_locked = connect
        await async_register_services(hass)
        registry = dr.async_get(hass)
        parent = registry.async_get_device_by_identifier(
            next(iter(pair.device_info["identifiers"])), entry.entry_id
        )
        native = dr.async_entries_for_parent_device(registry, parent.id)
        left = next(device for device in native if "Left" in device.name)
        pairs.append(pair)
        return SimpleNamespace(
            pair=pair,
            children=children,
            parent=parent.id,
            left=left.id,
            events=events,
            connections=connections,
            records=records,
            hooks=hooks,
        )

    pairs = []
    yield build
    for pair in pairs:
        await pair.async_shutdown()


def mutations(events):
    return [
        (side, packet.hex())
        for side, packet in events
        if len(packet) > 6 and packet[3] == 5 and packet[5] == 1
    ]


@pytest.mark.parametrize("operation", ("list", "new", "set", "delete"))
async def test_standalone_waits_for_late_clock_reply(hass, runtime, operation):
    target, client, _ = runtime
    queries = 0

    async def write(_char, packet, **kwargs):
        nonlocal queries
        if packet.hex() == "6e08010178":
            queries += 1
            if queries > 1:
                hass.loop.call_soon(notify, target, "6e09010078")

    client.write_gatt_char.side_effect = write
    await settings(hass, operation, alarm_id=1)
    assert queries == 2
    assert target.controller.observations["clock_available"]


async def test_concurrent_pair_waits_for_late_clock_replies(hass, live_pair):
    live = await live_pair("concurrent", delayed_clock=True)
    await hass.services.async_call(
        const.DOMAIN,
        "majestichome",
        {"device_id": live.parent, "operation": "set", "alarm_id": 1},
        blocking=True,
    )
    assert {side for side, _packet in mutations(live.events)} == {"left", "right"}
    assert live.connections == {"left": 1, "right": 1}


@pytest.mark.parametrize("fail", (False, True))
@pytest.mark.parametrize("paired", (False, True))
async def test_preflight_retains_links_until_all_targets_finish(
    hass, live_pair, monkeypatch, fail, paired
):
    live = await live_pair("concurrent")
    original = bed.MajesticHomeController.prepare_live
    if not paired:
        monkeypatch.setattr(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            lambda *args: ([(child, "both") for child in live.children.values()], []),
        )
    for child in live.children.values():
        child._disconnect_after_command = True
        # Make the handoff expire as soon as the next target yields.
        monkeypatch.setattr(child, "_idle_disconnect_delay", lambda: 0)

    async def prepare(controller, request, **kwargs):
        if controller.layout.key == "JLRM":
            for _ in range(5):
                await asyncio.sleep(0)
            assert live.children["left"].is_connected
            if fail:
                raise ValueError("Right preflight failed")
        return await original(controller, request, **kwargs)

    with patch.object(bed.MajesticHomeController, "prepare_live", prepare):
        call = hass.services.async_call(
            const.DOMAIN,
            "majestichome",
            {"device_id": live.parent, "operation": "sync_clock"},
            blocking=True,
        )
        if fail:
            with pytest.raises(ServiceValidationError, match="Right preflight failed"):
                await call
        else:
            await call
            for side in live.children:
                assert len([packet for owner, packet in live.events if owner == side]) == 2
    assert live.connections == {"left": 1, "right": 1}
    for child in live.children.values():
        assert child._command_connection_holds == 0
        assert not child.is_connected or child._disconnect_timer is not None


@pytest.mark.parametrize("mode", ("concurrent", "sequential"))
@pytest.mark.parametrize("target", ("parent", "left"))
@pytest.mark.parametrize("operation", ("sync_clock", "list", "new", "set", "toggle", "delete"))
async def test_registered_actions_rebuild_on_actual_pair_links(
    hass, live_pair, mode, target, operation
):
    live = await live_pair(mode)
    fields = {
        "device_id": getattr(live, target),
        "operation": operation,
        "alarm_id": 1,
        "enabled": False,
    }
    if mode == "concurrent" and operation == "toggle":
        for side, child in live.children.items():
            if target == "left" and side != "left":
                continue
            await child.async_connect()
            child.controller.alarms[1] = live.records[side]
    await hass.services.async_call(const.DOMAIN, "majestichome", fields, blocking=True)
    sides = {"left", "right"} if target == "parent" else {"left"}
    expected = {
        "new": "6e0d200501010100071e2e00f6",
        "set": "6e0d200501010100071e2e00f6",
        "toggle": "6e0d200501010100071e2ef8ee",
        "delete": "6e0820050201019f",
    }
    if operation in expected:
        assert sorted(mutations(live.events)) == sorted(
            (side, expected[operation]) for side in sides
        )
    elif operation == "list":
        assert sorted((side, packet.hex()) for side, packet in live.events) == sorted(
            (side, "6e0820050100009c") for side in sides
        )
    else:
        for side in sides:
            assert [packet[3:6] for owner, packet in live.events if owner == side] == [
                bytes((8, 2, 1)),
                bytes((8, 3, 1)),
            ]
    assert all(live.connections[side] == (2 if mode == "sequential" else 1) for side in sides)
    assert all(live.connections[side] == 0 for side in live.children.keys() - sides)
    assert not mutations([(side, packet) for side, packet in live.events if side not in sides])
    if mode == "sequential":
        assert not any(child.is_connected for child in live.children.values())


@pytest.mark.parametrize("race", ("stop", "changed", "session", "owner", "target", "product"))
async def test_sequential_races_never_write_a_stale_mutation(hass, live_pair, race):
    live = await live_pair("sequential")
    real = services._execute_preflighted

    async def before_execution(*args, **kwargs):
        if race == "stop":
            await live.pair.async_stop_command()
        elif race == "changed":
            live.records["left"] = Alarm(1, 99, 22, 45, 250, 131)
        elif race == "target":
            await live.pair.async_remove_child("right")
        elif race == "product":
            child = live.children["left"]
            child.entry.persist_data({**child.entry.data, const.CONF_PROTOCOL_VARIANT: "JHRN"})
        else:

            def invalidate(side, child, generation):
                if generation == 2:
                    if race == "session":
                        child.controller.on_disconnect()
                    else:
                        child.controller._physical_owner = copy(child)

            live.hooks["query"] = invalidate
        await real(*args, **kwargs)

    with patch.object(services, "_execute_preflighted", before_execution):
        if race == "stop":
            await hass.services.async_call(
                const.DOMAIN,
                "majestichome",
                {"device_id": live.parent, "operation": "toggle", "alarm_id": 1},
                blocking=True,
            )
        else:
            with pytest.raises(HomeAssistantError):
                await hass.services.async_call(
                    const.DOMAIN,
                    "majestichome",
                    {"device_id": live.parent, "operation": "toggle", "alarm_id": 1},
                    blocking=True,
                )
    assert mutations(live.events) == []
    assert not any(child.is_connected for child in live.children.values())


async def test_all_entry_routes_are_rechecked_after_queued_group_lock(hass, live_pair):
    live = await live_pair("sequential")
    original = services._execute_preflighted

    async def queue_then_change(*args, **kwargs):
        async with live.pair._topology.command_lock:
            task = asyncio.create_task(original(*args, **kwargs))
            await asyncio.sleep(0)
            right = live.children["right"]
            right.entry.persist_data({**right.entry.data, const.CONF_PROTOCOL_VARIANT: "JHRN"})
        await task

    with (
        patch.object(services, "_execute_preflighted", queue_then_change),
        pytest.raises(HomeAssistantError),
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "majestichome",
            {"device_id": live.parent, "operation": "set", "alarm_id": 1},
            blocking=True,
        )
    assert mutations(live.events) == []


async def test_all_entry_routes_are_rechecked_at_submission_after_pacing(hass, live_pair):
    live = await live_pair("concurrent")
    original = services._execute_preflighted
    pace = bed.MajesticHomeController._pace
    armed = False

    async def execute(*args, **kwargs):
        nonlocal armed
        armed = True
        await original(*args, **kwargs)

    async def change_during_pace(controller, cleanup):
        nonlocal armed
        result = await pace(controller, cleanup)
        if armed:
            armed = False
            right = live.children["right"]
            right.entry.persist_data({**right.entry.data, const.CONF_PROTOCOL_VARIANT: "JHRN"})
        return result

    with (
        patch.object(services, "_execute_preflighted", execute),
        patch.object(bed.MajesticHomeController, "_pace", change_during_pace),
        pytest.raises(HomeAssistantError),
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "majestichome",
            {"device_id": live.parent, "operation": "set", "alarm_id": 1},
            blocking=True,
        )
    assert mutations(live.events) == []


async def test_sequential_all_target_live_preflight_before_first_mutation(hass, live_pair):
    live = await live_pair("sequential")
    original = bed.MajesticHomeController.prepare_live

    async def reject_right(controller, request, **kwargs):
        result = await original(controller, request, **kwargs)
        if controller.layout.key == "JLRM":
            raise ValueError("Right current settings unavailable")
        return result

    with (
        patch.object(bed.MajesticHomeController, "prepare_live", reject_right),
        pytest.raises(HomeAssistantError),
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "majestichome",
            {"device_id": live.parent, "operation": "set", "alarm_id": 1},
            blocking=True,
        )
    assert mutations(live.events) == []


@pytest.mark.parametrize("partial", (False, True))
async def test_new_requires_explicit_id_before_import_even_with_partial_records(
    hass, runtime, partial
):
    target, client, _ = runtime
    assert await target.async_connect()
    notify(target, "6e09010078")
    if partial:
        notify(target, "6e200d0501020100071e2ef9f0")
    client.write_gatt_char.reset_mock()
    with (
        patch.object(services, "async_import_modules", AsyncMock()) as importing,
        pytest.raises(ServiceValidationError, match="explicit alarm ID"),
    ):
        await settings(hass, "new")
    importing.assert_not_awaited()
    assert written(target) == []
    await settings(hass, "new", alarm_id=2)
    assert written(target) == ["6e0d200501010200071e2e01f8"]
