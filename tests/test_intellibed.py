"""Intellibed's frozen bytes, explicit setup, native controls and link ownership."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.beds.intellibed.controller import IntellibedController
from custom_components.adjustable_bed.codec import keeson, motomotion
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.detection import detect_bed_type, detect_new_bed
from custom_components.adjustable_bed.discovery_hints import first_pass
from custom_components.adjustable_bed.errors import BedNotConnectedError
from custom_components.adjustable_bed.profiles.intellibed import PROFILES, uuid
from custom_components.adjustable_bed.setup_questions import setup_profile_for
from custom_components.adjustable_bed.validators import is_valid_variant_for_bed_type
from scripts.wire_snapshot import FakeClock, FakeServices, virtual_time
from tests.test_controller_contract import _FactoryCoordinator

VECTORS = json.loads((Path(__file__).parent / "fixtures/intellibed/vectors.json").read_text())


def gatt(route):
    p = PROFILES[route]
    services = {p.write_service: [p.write_uuid]}
    if p.notify_uuid != p.write_uuid:
        services.setdefault(p.notify_service, []).append(p.notify_uuid)
    return FakeServices({"services": services, "properties": {"*": ["write", "notify"]}})


def make_bed(route="old"):
    coordinator = _FactoryCoordinator()
    coordinator.record_command_trace = MagicMock()
    coordinator.cancel_command = asyncio.Event()
    coordinator.address = "AA:BB:CC:DD:17:20"
    client = SimpleNamespace(
        is_connected=True,
        services=gatt(route),
        write_gatt_char=AsyncMock(),
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
    )
    coordinator.client = client
    bed = IntellibedController(coordinator, route)
    coordinator.controller = bed
    return coordinator, client, bed


async def connect(bed):
    await bed.async_discover_capabilities()
    await bed.start_notify()


@pytest.mark.parametrize("v", VECTORS, ids=lambda v: v["id"])
def test_all_frozen_literals_and_raw_timer_exception(v):
    frame = bytes.fromhex(v["expected_bytes"])
    payload = bytes.fromhex(v["inputs"]["payload"])
    if v["protocol"] == "P1":
        assert keeson.frame(int.from_bytes(payload, "little")) == frame
    elif len(frame) == 9:
        body = payload if len(payload) == 4 else payload[2:6]
        assert (
            motomotion.binary_command(
                int.from_bytes(body[:2], "big"), int.from_bytes(body[2:], "big")
            )
            == frame
        )
    else:
        # Frozen exception only: not normalized to an HHC frame or exposed.
        assert v["id"] == "P2-D"
        assert payload == frame == b"\x00\x02\x00\x00"
        assert all(p.encode(a) != frame for p in PROFILES.values() for a in p.actions.values())


@pytest.mark.parametrize("route", PROFILES)
async def test_every_exposed_control_is_one_frozen_write_on_exact_destination(route):
    _, client, bed = make_bed(route)
    await connect(bed)
    literals = {
        bytes.fromhex(v["expected_bytes"])
        for v in VECTORS
        if v["protocol"] == ("P1" if route == "old" else "P2")
    }
    with virtual_time(FakeClock()):
        for key, value in bed.profile.actions.items():
            client.write_gatt_char.reset_mock()
            await bed.press(key)
            call = client.write_gatt_char.call_args
            assert client.write_gatt_char.await_count == 1
            assert call.args[0] is bed._link.write
            assert call.args[1] == bed.profile.encode(value)
            assert call.args[1] in literals
            assert call.kwargs["response"] is True
    assert not bed.execution.declared
    assert not bed.supports_motor_control and not bed.supports_stop_all
    assert not bed.supports_preset_flat and not bed.supports_memory_presets
    assert not bed.motor_control_specs
    assert all(
        not s.combine_sides and not s.invalidates_position for s in bed.controller_button_specs
    )
    assert bed.protocol_diagnostics["raw_status"] is None


@pytest.mark.parametrize("route", [None, "auto", "unknown"])
async def test_factory_never_guesses_variant(route):
    coordinator, client, _ = make_bed()
    with pytest.raises(ValueError, match="explicitly"):
        await create_controller(coordinator, "intellibed", route, client)


@pytest.mark.parametrize("route", PROFILES)
async def test_factory_explicit_variant_and_setup_owned_fields(route):
    coordinator, client, _ = make_bed(route)
    bed = await create_controller(coordinator, "intellibed", route, client)
    assert isinstance(bed, IntellibedController) and bed.profile.key == route
    assert is_valid_variant_for_bed_type("intellibed", route)
    assert not is_valid_variant_for_bed_type("intellibed", "auto")
    profile = setup_profile_for({const.CONF_BED_TYPE: "intellibed"})
    assert profile is not None
    assert profile.owns[const.CONF_HAS_MASSAGE] is False  # app-labelled controls own exposure
    assert profile.questions[0].key == const.CONF_PROTOCOL_VARIANT
    assert per_side_profile("intellibed", route) is not None


@pytest.mark.parametrize("name", ["BASE-i4.123", "xx-HhC-yy"])
def test_shared_name_is_only_an_app_candidate(name):
    info = SimpleNamespace(
        name=name,
        service_uuids=[uuid("fff0")],
        manufacturer_data={},
        advertisement=SimpleNamespace(local_name=name),
        address="AA:BB:CC:DD:17:20",
    )
    assert first_pass(info).name("intellibed")
    result = detect_new_bed(info)
    assert "intellibed" in {result.bed_type, *(result.ambiguous_types or ())}
    assert "name:intellibed_app_candidate" in result.signals
    if result.bed_type == "intellibed":
        assert detect_bed_type(info) is None


@pytest.mark.parametrize("route", PROFILES)
async def test_gatt_is_service_scoped_unique_and_requires_acknowledged_write(route):
    _, client, bed = make_bed(route)
    client.services = gatt("hhc" if route == "old" else "old")
    with pytest.raises(ValueError):
        await bed.async_discover_capabilities()
    client.services = gatt(route)
    write = bed._role(client, bed.profile.write_service, bed.profile.write_uuid)
    write.properties = ["write-without-response", "notify"]
    with pytest.raises(ValueError, match="write-with-response"):
        await bed.async_discover_capabilities()


@pytest.mark.parametrize("route", PROFILES)
async def test_notifications_require_current_controller_link_subscription_and_sender(route):
    coordinator, client, bed = make_bed(route)
    await connect(bed)
    sender, receive = client.start_notify.call_args.args
    receive(SimpleNamespace(uuid=sender.uuid), bytearray(range(15)))
    assert bed.protocol_diagnostics["raw_status"] is None
    for size in range(15):
        receive(sender, bytearray(range(size)))
        assert bed.protocol_diagnostics["raw_fields"] is None
    receive(sender, bytearray(range(15)))
    assert bed.protocol_diagnostics["raw_fields"] == {
        "head": 7,
        "feet": 8,
        "light": 13,
        "timer": 14,
    }
    assert bed.protocol_diagnostics["ui_notify_uuid"] == uuid("ffe4")
    assert bed.profile.notify_uuid == uuid("ffe4" if route == "old" else "ffe1")
    assert not coordinator.controller_state
    await bed.stop_notify()
    receive(sender, bytearray([255] * 15))
    assert bed.protocol_diagnostics["raw_status"] is None
    await bed.start_notify()
    receive(sender, bytearray([255] * 15))  # previous subscription
    assert bed.protocol_diagnostics["raw_status"] is None
    _, current = client.start_notify.call_args.args
    coordinator.controller = IntellibedController(coordinator, route)
    current(sender, bytearray([255] * 15))
    assert bed.protocol_diagnostics["raw_status"] is None


async def test_cancel_during_source_delay_sends_no_action_or_invented_release():
    coordinator, client, bed = make_bed("hhc")
    await connect(bed)
    task = asyncio.create_task(bed.press("head_low"))
    await asyncio.sleep(0)
    coordinator.cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not client.write_gatt_char.called
    with pytest.raises(HomeAssistantError):
        await bed.stop_all()
    assert not client.write_gatt_char.called


async def test_queued_write_cannot_cross_controller_or_gatt_replacement():
    coordinator, client, bed = make_bed()
    await connect(bed)
    async with bed.ble_lock:
        task = asyncio.create_task(bed.press("head_up"))
        await asyncio.sleep(0)
        coordinator.controller = IntellibedController(coordinator, "hhc")
    with pytest.raises(BedNotConnectedError):
        await task
    assert not client.write_gatt_char.called
    coordinator.controller = bed
    async with bed.ble_lock:
        task = asyncio.create_task(bed.press("head_up"))
        await asyncio.sleep(0)
        client.services = gatt("old")
    with pytest.raises(BedNotConnectedError):
        await task
    assert not client.write_gatt_char.called


async def test_cancellation_settles_the_inflight_write_without_extra_frames():
    _, client, bed = make_bed()
    await connect(bed)
    entered, finish = asyncio.Event(), asyncio.Event()

    async def write(*args, **kwargs):
        entered.set()
        await finish.wait()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(bed.press("head_up"))
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.write_gatt_char.await_count == 1
    assert bed.protocol_diagnostics["raw_status"] is None


async def test_old_entity_rejects_a_different_variant_before_any_write():
    coordinator, client, bed = make_bed("old")
    old_spec = bed.controller_button_specs[0]
    coordinator.controller = new = IntellibedController(coordinator, "hhc")
    with pytest.raises(HomeAssistantError):
        await old_spec.press_fn(new)
    assert not client.write_gatt_char.called


@pytest.mark.parametrize("route", PROFILES)
async def test_native_setup_button_service_and_unsupported_motion(
    hass,
    route,
    mock_coordinator_connected,
    mock_bleak_client,
    mock_async_ble_device_from_address,
    enable_custom_integrations,
):
    from homeassistant.const import CONF_ADDRESS, CONF_NAME
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.runtime_data import entry_runtime

    address = "AA:BB:CC:DD:17:21"
    mock_async_ble_device_from_address.return_value.name = (
        "base-i4-test" if route == "old" else "HHC-test"
    )
    mock_bleak_client.services = gatt(route)
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Intellibed",
        unique_id=address,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "Intellibed",
            const.CONF_BED_TYPE: "intellibed",
            const.CONF_PROTOCOL_VARIANT: route,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_HAS_MASSAGE: False,
            const.CONF_HAS_LIGHT: False,
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    runtime = entry_runtime(hass, entry.entry_id)
    assert isinstance(runtime, AdjustableBedCoordinator)
    assert isinstance(runtime.controller, IntellibedController)
    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert not any(e.domain == "cover" for e in entities)
    assert not any(e.unique_id.endswith("_stop") for e in entities)
    spec = runtime.controller.controller_button_specs[0]
    eid = registry.async_get_entity_id("button", const.DOMAIN, f"{address}_{spec.key}")
    assert eid is not None
    mock_bleak_client.write_gatt_char.reset_mock()
    await hass.services.async_call("button", "press", {"entity_id": eid}, blocking=True)
    assert mock_bleak_client.write_gatt_char.await_count == 1
    assert mock_bleak_client.write_gatt_char.call_args.args[1] == runtime.controller.profile.encode(
        next(iter(runtime.controller.profile.actions.values()))
    )
    state = hass.states.get(eid)
    assert state is not None and state.attributes["card_section"] == "massage"
    lights = [entity for entity in entities if entity.domain == "light"]
    assert len(lights) == (1 if route == "hhc" else 0)
    if lights:
        from bleak.exc import BleakError

        light_id = lights[0].entity_id
        assert hass.states.get(light_id).state == "unknown"
        for action in ("on", "off"):
            mock_bleak_client.write_gatt_char.reset_mock()
            await hass.services.async_call(
                "light", f"turn_{action}", {"entity_id": light_id}, blocking=True
            )
            mock_bleak_client.write_gatt_char.assert_awaited_once()
            assert mock_bleak_client.write_gatt_char.call_args.args[1] == (
                PROFILES[route].encode(PROFILES[route].actions[f"light_{action}"])
            )
            assert hass.states.get(light_id).state == action
        mock_bleak_client.write_gatt_char.side_effect = BleakError("not delivered")
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                "light", "turn_on", {"entity_id": light_id}, blocking=True
            )
        assert hass.states.get(light_id).state != "on"

        async def retire(_char, _packet, **_kwargs):
            runtime.controller.on_disconnect()

        mock_bleak_client.write_gatt_char.side_effect = retire
        await hass.services.async_call("light", "turn_on", {"entity_id": light_id}, blocking=True)
        assert hass.states.get(light_id).state != "on"
        mock_bleak_client.write_gatt_char.side_effect = None
    mock_bleak_client.write_gatt_char.reset_mock()
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            const.DOMAIN,
            "goto_preset",
            {"device_id": registry.async_get(eid).device_id, "preset": 1},
            blocking=True,
        )
    assert not mock_bleak_client.write_gatt_char.called
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_native_service_preflights_all_targets_before_any_delivery(hass):
    from unittest.mock import patch

    from custom_components.adjustable_bed.services import async_register_services
    from tests.test_generic_services import target

    await async_register_services(hass)
    supported, _ = target()  # first target could execute the requested memory
    unsupported, _ = target()
    _, client, bed = make_bed()
    unsupported.capability_controller = bed
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(supported, const.SIDE_BOTH), (unsupported, const.SIDE_BOTH)], []),
        ),
        pytest.raises(HomeAssistantError),
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "goto_preset",
            {"device_id": ["left", "right"], "preset": 1},
            blocking=True,
        )
    supported.async_execute_controller_command.assert_not_called()
    unsupported.async_execute_controller_command.assert_not_called()
    assert not client.write_gatt_char.called


async def test_paired_parent_has_no_combined_controls_for_unreconciled_topologies():
    from custom_components.adjustable_bed.button import _combined_controller_buttons_for
    from tests.test_paired_coordinator import _pair

    pair, left, right = _pair([])
    _, _, old = make_bed("old")
    _, _, hhc = make_bed("hhc")
    left.capability_controller = old
    right.capability_controller = hhc
    assert not list(_combined_controller_buttons_for(pair, [left, right]))
    assert not old.supports_single_address_pairing and not hhc.supports_single_address_pairing
