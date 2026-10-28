"""Production-path assertions for the five consolidated Cluster033 repairs."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.command_scheduler import CommandKind, current_command_context
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import _cover_entities_for
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.paired_devices import child_device_info
from custom_components.adjustable_bed.services import async_register_services

from .test_cluster033 import coordinator as transport

LOCAL = bytes.fromhex("e5fe175001008034")
ZERO = bytes.fromhex("e5fe160000000006")


@pytest.fixture(autouse=True)
async def cleanup(hass):
    yield
    for target in hass.data.get("repair005_targets", []):
        await target.async_shutdown()


async def target(hass, monkeypatch, app="serta_mp_remote"):
    index = len(hass.data.setdefault("repair005_targets", [])) + 1
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=f"Repair {index}",
        unique_id=f"AA:33:05:00:00:{index:02X}",
        data={
            "address": f"AA:33:05:00:00:{index:02X}",
            "name": f"Repair {index}",
            "bed_type": app,
            "motor_count": 2,
            "disable_angle_sensing": False,
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    coordinator = AdjustableBedCoordinator(hass, entry)
    hass.data["repair005_targets"].append(coordinator)
    client = transport().client

    async def disconnect():
        client.is_connected = False

    client.disconnect = AsyncMock(side_effect=disconnect)
    coordinator._client = client
    ctrl = await create_controller(coordinator, app, protocol_variant="auto", client=client)
    coordinator._controller, coordinator._ready = ctrl, True
    monkeypatch.setattr(ctrl, "_wait", AsyncMock(return_value=False))
    monkeypatch.setattr(coordinator, "async_ensure_connected", AsyncMock(return_value=True))
    await ctrl.start_notify(coordinator._handle_position_update)
    client.write_gatt_char.reset_mock()
    return coordinator, ctrl, client


async def pair(hass, monkeypatch):
    triples = {side: await target(hass, monkeypatch) for side in ("left", "right")}
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Serta pair",
        data={"pair_id": "repair005-pair", "bed_type": "serta_mp_remote"},
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    owner = PairedBedCoordinator(hass, entry, {side: row[0] for side, row in triples.items()})
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = owner
    registry = dr.async_get(hass)
    parent = registry.async_get_or_create(config_entry_id=entry.entry_id, **owner.device_info)
    devices = {
        side: registry.async_get_or_create_child(
            config_entry_id=entry.entry_id, **child_device_info(owner, side)
        )
        for side in triples
    }
    await async_register_services(hass)
    return owner, parent, devices, triples


async def call(hass, device, action, **kwargs):
    await hass.services.async_call(
        DOMAIN, action, {"device_id": [device.id], **kwargs}, blocking=True
    )


def frames(client):
    return [c.args[1] for c in client.write_gatt_char.await_args_list]


@pytest.mark.parametrize("side", ["left", "right", "both"])
@pytest.mark.parametrize("ending", ["stop", "replacement", "failed_release", "interrupted_release"])
async def test_paired_group_local_edit_release_ownership(hass, monkeypatch, side, ending):
    _owner, parent, devices, triples = await pair(hass, monkeypatch)
    selected = ("left", "right") if side == "both" else (side,)
    device = parent if side == "both" else devices[side]
    starts = {s: asyncio.Event() for s in selected}
    contexts = []
    for s in selected:
        coord, ctrl, _client = triples[s]

        async def wait(_ms, *, cleanup=False, s=s, coord=coord):
            context = current_command_context()
            contexts.append(
                (context.kind, context.scheduler_token is coord._command_scheduler.token)
            )
            starts[s].set()
            await coord.cancel_command.wait()
            return True

        monkeypatch.setattr(ctrl, "_wait", wait)
    editing = asyncio.create_task(
        call(hass, device, "hold_control", control="head_target_up", duration=60)
    )
    try:
        await asyncio.wait_for(asyncio.gather(*(e.wait() for e in starts.values())), 2)
        assert contexts and all(kind is CommandKind.GROUP and own for kind, own in contexts)
        error = RuntimeError("paired target write failed")
        completed = []
        if ending in ("failed_release", "interrupted_release"):
            for s in selected:

                async def write(_char, command, *, response, s=s):
                    if command == LOCAL:
                        if ending == "failed_release":
                            raise error
                        # The existing coordinator cancels this suspended write;
                        # an attempted packet must never acknowledge completion.
                        await asyncio.Event().wait()
                    completed.append((s, command))

                triples[s][2].write_gatt_char.side_effect = write
        if ending == "replacement":
            for s in selected:
                monkeypatch.setattr(triples[s][1], "_wait", AsyncMock(return_value=False))
            await asyncio.wait_for(
                call(hass, device, "hold_control", control="head_up", duration=0.1), 2
            )
        else:
            await asyncio.wait_for(call(hass, device, "stop_all"), 2)
        result = (await asyncio.wait_for(asyncio.gather(editing, return_exceptions=True), 2))[0]
        if ending == "failed_release":
            assert isinstance(result, BaseException)
            assert result is error or error in getattr(result, "side_errors", {}).values()
        else:
            assert result is None
        for s, (_coord, ctrl, client) in triples.items():
            if s not in selected:
                assert frames(client) == []
                continue
            assert frames(client)[0] == LOCAL
            assert ctrl._local_release_stop is None
            if ending == "stop":
                assert frames(client) == [LOCAL]
            elif ending == "replacement":
                assert frames(client) == [LOCAL, bytes.fromhex("e5fe160100000005"), ZERO]
            else:
                assert ZERO in frames(client)
                assert (s, LOCAL) not in completed
        # A genuine later STOP still writes the remote zero on every selected
        # physical receiver, including after replacement and failed cleanup.
        counts = {s: len(frames(triples[s][2])) for s in selected}
        await call(hass, device, "stop_all")
        for s in selected:
            assert frames(triples[s][2])[counts[s] :] == [ZERO]
    finally:
        editing.cancel()
        await asyncio.gather(editing, return_exceptions=True)


@pytest.mark.parametrize("side", ["left", "right", "both"])
async def test_paired_normal_local_completion_retains_later_global_stop(hass, monkeypatch, side):
    _owner, parent, devices, triples = await pair(hass, monkeypatch)
    device = parent if side == "both" else devices[side]
    await call(hass, device, "hold_control", control="head_target_up", duration=0.2)
    await call(hass, device, "stop_all")
    for s, (_coord, ctrl, client) in triples.items():
        assert frames(client) == ([LOCAL, ZERO] if side in (s, "both") else [])
        assert ctrl._local_release_stop is None


@pytest.mark.parametrize(
    "angles,percentages", [((60, 45), (100, 100)), ((30, 15), (50, 33)), ((0, 0), (0, 0))]
)
async def test_serta_factory_notifications_publish_calibrated_cover_states(
    hass, monkeypatch, angles, percentages
):
    from custom_components.adjustable_bed.beds.serta_mp_remote import FOOT_TABLE, HEAD_TABLE

    coord, ctrl, client = await target(hass, monkeypatch)
    await async_setup_component(hass, "cover", {})
    covers = _cover_entities_for(hass, coord)
    for cover in covers:
        cover.entity_id = "cover.repair_" + cover.entity_description.key
    await hass.data["cover"].async_add_entities(covers)
    assert {s.key: s.max_angle for s in ctrl.motor_control_specs} == ctrl.motor_max_angles
    assert {
        c.entity_description.key: c.entity_description.max_angle for c in covers
    } == ctrl.motor_max_angles
    data = bytearray(16)
    data[3:5] = HEAD_TABLE[angles[0]].to_bytes(2, "little")
    data[5:7] = FOOT_TABLE[angles[1]].to_bytes(2, "little")
    client.start_notify.await_args.args[1](None, data)
    assert coord.position_data == {"back": float(angles[0]), "legs": float(angles[1])}
    for cover in covers:
        await cover.async_update_ha_state(force_refresh=True)
    assert {
        c.entity_description.key: hass.states.get(c.entity_id).attributes["current_position"]
        for c in covers
    } == dict(zip(("back", "legs"), percentages, strict=True))


async def rename_targets(hass, monkeypatch, apps):
    result = []
    for app in apps:
        coord, ctrl, client = await target(hass, monkeypatch, app)
        hass.data.setdefault(DOMAIN, {})[coord.entry.entry_id] = coord
        device = dr.async_get(hass).async_get_or_create(
            config_entry_id=coord.entry.entry_id, **coord.device_info
        )
        result.append((coord, ctrl, client, device))
    await async_register_services(hass)
    return result


@pytest.mark.parametrize(
    "app,name,expected",
    [
        ("tempur_au", "  Bed  ", "ef0242656400000000000000000000000003"),
        ("row_control", "ABCDEFGHIJKLMNO", "ef024142434445464748494a4b4c4d4e4fd6"),
        ("row_control", " é ", "ef02c300000000000000000000000000004b"),
        ("serta_mp_remote", " Bed ", "ef0242656400000000000000000000000003"),
        ("tempur_curve", " Bed ", "ef0242656400000000000000000000000003"),
        ("ergo_slim", " Bed ", "ef0242656400000000000000000000000003"),
        ("ergomotion_app", "ABCDEFGHIJKLMNO", "ef024142434445464748494a4b4c4d4e4fd6"),
        ("ergomotion_app", " Bed ", "ef0242656400000000000000000000000003"),
        ("qplus_app", "Bed", "ef0242656400000000000000000000000003"),
    ],
)
async def test_registered_rename_preserves_profile_caller_domain(
    hass, monkeypatch, app, name, expected
):
    ((_coord, _ctrl, client, device),) = await rename_targets(hass, monkeypatch, [app])
    await call(hass, device, "rename", name=name)
    assert frames(client) == [bytes.fromhex(expected)]


@pytest.mark.parametrize(
    "app,name",
    [
        ("tempur_au", " \t "),
        ("tempur_au", "A" * 15),
        ("row_control", "A" * 16),
        ("row_control", "A" * 17),
        ("row_control", "😀" * 8),
        ("qplus_app", " Bed "),
        ("qplus_app", "A" * 15),
        ("serta_mp_remote", "A" * 15),
        ("ergo_slim", "A" * 15),
        ("tempur_curve", "A" * 15),
    ],
)
async def test_registered_rename_rejects_profile_or_unsafe_overflow_before_write(
    hass, monkeypatch, app, name
):
    ((_coord, _ctrl, client, device),) = await rename_targets(hass, monkeypatch, [app])
    with pytest.raises(ServiceValidationError):
        await call(hass, device, "rename", name=name)
    assert frames(client) == []


async def test_registered_rename_all_target_preflight_and_independent_normalization(
    hass, monkeypatch
):
    targets = await rename_targets(hass, monkeypatch, ["row_control", "tempur_au"])
    devices = [row[3].id for row in targets]
    await hass.services.async_call(
        DOMAIN, "rename", {"device_id": devices, "name": "  Bed  "}, blocking=True
    )
    for _coord, _ctrl, client, _device in targets:
        assert frames(client) == [bytes.fromhex("ef0242656400000000000000000000000003")]
        client.write_gatt_char.reset_mock()
    # ROW's safe15-unit domain cannot widen the independently selected AU UI.
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "rename", {"device_id": devices, "name": "ABCDEFGHIJKLMNO"}, blocking=True
        )
    assert all(frames(row[2]) == [] for row in targets)


async def test_row_copy_counts_java_utf16_units_without_overflow(hass, monkeypatch):
    ((_coord, _ctrl, client, device),) = await rename_targets(hass, monkeypatch, ["row_control"])
    await call(hass, device, "rename", name="😀" * 7 + "A")
    (packet,) = frames(client)
    # Conditional UTF-8 model, copying exactly15 Java code units' worth of
    # encoded bytes, not15 Unicode code points or the entire encoded string.
    assert packet[:2] == b"\xef\x02" and len(packet) == 18
    assert packet[2:17] == ("😀" * 7 + "A").encode("utf-8")[:15]
    assert packet[-1] == (~sum(packet[:-1])) & 255
