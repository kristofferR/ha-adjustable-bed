"""HHC's absolute massage numbers show only delivery on their own session."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.intellibed.controller import IntellibedController
from custom_components.adjustable_bed.command_scheduler import current_command_context
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles.intellibed import PROFILES
from custom_components.adjustable_bed.runtime_data import entry_runtime
from custom_components.adjustable_bed.state_keys import massage_intensity
from tests.card_placements import declared_placements, spec_entities
from tests.state_helpers import state_writer
from tests.test_intellibed import VECTORS, connect, gatt, make_bed

ADDRESS = "AA:BB:CC:DD:17:24"
LEVELS = ("off", "low", "medium", "high")


@pytest.fixture
async def native(hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations):
    mock_bleak_client.services = gatt("hhc")
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="HHC massage levels",
        unique_id=ADDRESS,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "HHC massage levels",
            const.CONF_BED_TYPE: "intellibed",
            const.CONF_PROTOCOL_VARIANT: "hhc",
            const.CONF_HAS_MASSAGE: False,
            const.CONF_HAS_LIGHT: False,
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
    assert isinstance(bed, IntellibedController)
    # Delivery tests do not wait on the app's prewrite delay.
    bed.profile = replace(bed.profile, actions={
        key: replace(action, delay_ms=0) for key, action in bed.profile.actions.items()
    })
    registry = er.async_get(hass)
    numbers = {
        zone: registry.async_get_entity_id(
            "number", const.DOMAIN, f"{ADDRESS}_controller_number_{spec.key}"
        )
        for zone, spec in zip(("head", "foot"), bed.controller_number_specs, strict=True)
    }
    assert all(numbers.values())
    try:
        yield SimpleNamespace(hass=hass, runtime=runtime, bed=bed, client=mock_bleak_client,
                              numbers=numbers)
    finally:
        assert await hass.config_entries.async_unload(entry.entry_id)


async def invoke(native, value, zone="head"):
    await native.hass.services.async_call(
        "number", "set_value", {"entity_id": native.numbers[zone], "value": value}, blocking=True
    )


def shown(native, zone="head"):
    return native.hass.states.get(native.numbers[zone]).state


async def test_native_number_routes_each_level_to_a_frozen_literal(native):
    literals = {bytes.fromhex(v["expected_bytes"]) for v in VECTORS if v["protocol"] == "P2"}
    for zone, prefix in (("head", "head"), ("foot", "feet")):
        state = native.hass.states.get(native.numbers[zone])
        assert state.state == "unknown"
        assert {key: state.attributes[key] for key in ("min", "max", "step")} == {
            "min": 0, "max": 3, "step": 1
        }
        assert state.attributes["assumed_state"] is True
        assert state.attributes["card_section"] == "massage"
        for level, label in enumerate(LEVELS):
            native.client.write_gatt_char.reset_mock()
            await invoke(native, level, zone)
            native.client.write_gatt_char.assert_awaited_once()
            args = native.client.write_gatt_char.call_args
            expected = PROFILES["hhc"].encode(PROFILES["hhc"].actions[f"{prefix}_{label}"])
            assert args.args[1] == expected and expected in literals
            assert args.args[0] is native.bed._link.write and args.kwargs["response"] is True
            assert float(shown(native, zone)) == level
            assert native.runtime.controller_state[massage_intensity(zone)] == level
    sender, receive = native.client.start_notify.call_args.args
    receive(sender, bytearray(range(15)))
    assert float(shown(native, "head")) == float(shown(native, "foot")) == 3
    fixture = json.loads((Path(__file__).parent / "fixtures/card_placements.json").read_text())
    actual = declared_placements(spec_entities(native.bed))
    assert actual["number:massage_head_intensity"] == fixture["number:massage_head_intensity"]
    assert actual["number:massage_foot_intensity"] == fixture["number:massage_foot_intensity"]
    buttons = {s.key for s in native.bed.controller_button_specs}
    assert len(buttons) == 5
    assert all(f"intellibed_hhc_{prefix}_{label}" not in buttons
               for prefix in ("head", "feet") for label in LEVELS)
    assert {f"intellibed_hhc_{prefix}_{direction}" for prefix in ("head", "feet")
            for direction in ("up", "down")} <= buttons


async def test_failed_level_write_preserves_last_delivered_level(native):
    await invoke(native, 1)
    native.client.write_gatt_char.reset_mock()
    native.client.write_gatt_char.side_effect = BleakError("not delivered")
    with pytest.raises(HomeAssistantError):
        await invoke(native, 2)
    native.client.write_gatt_char.assert_awaited_once()
    assert float(shown(native)) == 1


async def test_relative_step_invalidates_only_its_zone_and_all_off_sets_both_zero(native):
    await invoke(native, 1, "head")
    await invoke(native, 2, "foot")
    registry = er.async_get(native.hass)
    for action in ("head_up", "massage_off"):
        entity_id = registry.async_get_entity_id(
            "button", const.DOMAIN, f"{ADDRESS}_intellibed_hhc_{action}"
        )
        assert entity_id is not None
        await native.hass.services.async_call("button", "press", {"entity_id": entity_id},
                                             blocking=True)
        if action == "head_up":
            assert shown(native, "head") == "unknown"
            assert float(shown(native, "foot")) == 2
        else:
            assert float(shown(native, "head")) == float(shown(native, "foot")) == 0


async def test_cancelled_before_ble_admission_does_not_publish_a_level(native):
    await invoke(native, 1)
    native.client.write_gatt_char.reset_mock()
    entered = asyncio.Event()
    contexts = []
    write = native.bed.write_command

    async def queued(*args, **kwargs):
        contexts.append(current_command_context())
        entered.set()
        await write(*args, **kwargs)

    with patch.object(native.bed, "write_command", new=queued):
        async with native.bed.ble_lock:
            task = asyncio.create_task(invoke(native, 2))
            await asyncio.wait_for(entered.wait(), 1)
            contexts[0].cancel_event.set()
        await task
    native.client.write_gatt_char.assert_not_called()
    assert float(shown(native)) == 1


@pytest.mark.parametrize("cancel_kind", ("event", "task"))
async def test_completed_frame_publishes_even_when_its_operation_is_cancelled(native, cancel_kind):
    entered, finish = asyncio.Event(), asyncio.Event()
    owners, contexts = [], []
    write = native.bed.write_command

    async def tracked(*args, **kwargs):
        owners.append(asyncio.current_task())
        await write(*args, **kwargs)

    async def pending(*args, **kwargs):
        contexts.append(current_command_context())
        entered.set()
        await finish.wait()

    native.client.write_gatt_char.side_effect = pending
    with patch.object(native.bed, "write_command", new=tracked):
        task = asyncio.create_task(invoke(native, 3))
        await asyncio.wait_for(entered.wait(), 1)
        assert shown(native) == "unknown"
        if cancel_kind == "task":
            owners[0].cancel()
        else:
            contexts[0].cancel_event.set()
        finish.set()
        await task
    assert contexts[0].frames_written == 1
    native.client.write_gatt_char.assert_awaited_once()
    assert float(shown(native)) == 3


@pytest.mark.parametrize("retirement", ("disconnect", "stop_notify", "replace_subscription"))
async def test_retired_subscription_cannot_republish_a_completed_level(native, retirement):
    await invoke(native, 1)

    async def retire(*args, **kwargs):
        if retirement == "disconnect":
            native.bed.on_disconnect()
        elif retirement == "stop_notify":
            await native.bed.stop_notify()
        else:
            await native.bed.start_notify()

    native.client.write_gatt_char.side_effect = retire
    await invoke(native, 2)
    assert shown(native) == "unknown"
    assert native.runtime.controller_state[massage_intensity("head")] is None


@pytest.mark.parametrize("replacement", ("controller", "client", "gatt"))
async def test_replaced_owner_cannot_publish_a_completed_level(replacement):
    coordinator, client, bed = make_bed("hhc")
    state = {}
    coordinator.handle_controller_state_updates = state_writer(state)
    await connect(bed)
    bed.profile = replace(bed.profile, actions={
        key: replace(action, delay_ms=0) for key, action in bed.profile.actions.items()
    })
    spec = bed.controller_number_specs[0]
    await spec.set_fn(bed, 1)

    async def replace_owner(*args, **kwargs):
        if replacement == "controller":
            coordinator.controller = IntellibedController(coordinator, "hhc")
        elif replacement == "client":
            coordinator.client = SimpleNamespace(**vars(client))
        else:
            client.services = gatt("hhc")

    client.write_gatt_char.side_effect = replace_owner
    await spec.set_fn(bed, 2)
    assert state[massage_intensity("head")] == 1


async def test_number_setter_rejects_old_profile_and_unsupported_levels():
    _, client, old = make_bed()
    assert old.controller_number_specs == ()
    _, hhc_client, hhc = make_bed("hhc")
    setter = hhc.controller_number_specs[0].set_fn
    with pytest.raises(HomeAssistantError):
        await setter(old, 1)
    for value in (-1, 4, 0.5, True, float("nan"), float("inf")):
        with pytest.raises(HomeAssistantError):
            await setter(hhc, value)
    client.write_gatt_char.assert_not_called()
    hhc_client.write_gatt_char.assert_not_called()
