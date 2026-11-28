"""Public HA/card and connection boundaries from the full Flexx review."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const, services
from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.dreamsense.controller import ALARMS, SPLIT
from custom_components.adjustable_bed.beds.dreamsense.flexx_motion import (
    COLOR,
    FlexxMotionController,
)
from custom_components.adjustable_bed.beds.dreamsense.muuegm import ACTIVE
from custom_components.adjustable_bed.button import ControllerActionButton, _button_entities_for
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from tests.entry_entities import async_add_entry_entities
from tests.error_helpers import raises_key
from tests.test_dreamsense import make_client, written
from tests.test_flexx_motion_runtime import NOW, notify, runtime

CARD_METADATA = Path(__file__).parent / "fixtures/flexx_motion/card_metadata.json"


async def test_card_metadata_comes_from_registered_ha_entities_and_states(hass, tmp_path):
    coord, ctrl = await runtime(hass, "HZRM")
    await async_setup_component(hass, "button", {})
    buttons = _button_entities_for(hass, coord)
    await async_add_entry_entities(hass, coord.entry, "button", buttons)
    registry = er.async_get(hass)
    metadata = []
    owners = set()
    for button in buttons:
        state = hass.states.get(button.entity_id)
        entry = registry.async_get(button.entity_id)
        if state is None or entry is None:
            continue
        assert entry.device_id is not None
        owners.add(entry.device_id)
        # Normalize only the generated device ID. Translation keys and published
        # state attributes are copied from HA, never constructed to match a hold.
        metadata.append(
            {
                "entity_id": entry.entity_id,
                "translation_key": entry.translation_key,
                "device_id": "bed",
                "attributes": {
                    key: value
                    for key, value in state.attributes.items()
                    if key.startswith(("card_", "hold_", "held_")) or key == "requires_confirmation"
                },
            }
        )
    metadata.sort(key=lambda item: item["entity_id"])
    assert len(owners) == 1
    (tmp_path / "flexx-card-metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    releases = {row["translation_key"] for row in metadata}
    held = [row for row in metadata if "held_control" in row["attributes"]]
    assert any(row["attributes"]["held_control"] == "HeadUp" for row in held)
    assert any(row["attributes"]["held_control"] == "MemoryPosition1" for row in held)
    assert all(row["attributes"]["hold_release_button_key"] in releases for row in held)
    assert metadata == json.loads(CARD_METADATA.read_text())
    ctrl.on_disconnect()


@pytest.mark.parametrize(("enabled", "wire"), [(True, 0), (False, 2)])
async def test_box_enum_source_binding_and_fresh_roundtrip(hass, enabled, wire):
    # Frozen enum objects: headSplit@98bda1=0, strandard@98bdc1=2.
    coord, ctrl = await runtime(hass, "blue")
    setting = next(s for s in ctrl.controller_switch_specs if s.key == "dreamsense_split")
    coord.client.write_gatt_char.reset_mock()
    await coord.async_execute_controller_command(lambda c: setting.set_fn(c, enabled))
    assert written(coord) == [codec.record_20_len(11, 2, 1, (0, wire)).hex()]
    notify(coord, codec.record_20_len(11, 2, 2, (0, wire)).hex())
    assert coord.controller_state[SPLIT] is enabled
    notify(coord, codec.record_20_len(11, 2, 2, (0, 7)).hex())
    observations = ctrl.protocol_diagnostics["observations"]
    assert isinstance(observations, dict) and observations["box_mode_raw"] == 7
    assert coord.controller_state[SPLIT] is enabled
    ctrl.on_disconnect()


async def test_only_fields_completed_in_this_notification_replace_delivered_state(hass):
    coord, ctrl = await runtime(hass, "blue")
    notify(coord, "6e0e00037f")
    notify(coord, codec.record_20_len(4, 1, 2, (0, 255, 0, 0)).hex())
    notify(coord, codec.record_20_len(11, 2, 2, (0, 2)).hex())
    assert coord.controller_state[COLOR] == "red" and coord.controller_state[SPLIT] is False
    await coord.async_execute_controller_command(lambda c: c.light_settings(color=(0, 0, 255)))
    setting = next(s for s in ctrl.controller_switch_specs if s.key == "dreamsense_split")
    await coord.async_execute_controller_command(lambda c: setting.set_fn(c, True))
    green = codec.record_20_len(4, 1, 2, (0, 0, 255, 0))
    for packet in ("6e09010078", "00", green[:5].hex(), green[5:7].hex()):
        notify(coord, packet)
        assert coord.controller_state[COLOR] == "blue" and coord.controller_state[SPLIT] is True
    # Finish the green RGB record begun above; only now may it change color.
    notify(coord, green[7:].hex())
    assert coord.controller_state[COLOR] == "green"
    assert coord.controller_state[SPLIT] is True
    observations = ctrl.protocol_diagnostics["observations"]
    assert isinstance(observations, dict) and observations["box_mode_raw"] == 2
    notify(coord, codec.record_20_len(11, 2, 2, (0, 2)).hex())
    assert coord.controller_state[SPLIT] is False
    ctrl.on_disconnect()


@pytest.mark.parametrize("second_enabled", [True, False])
async def test_bare_ack_never_confirms_details_of_overlapping_requests(hass, second_enabled):
    coord, ctrl = await runtime(hass, "blue")
    notify(coord, "6e09010078")
    first = AlarmRequest(enabled=True, hour=6, minute=30, wake_action="zero_g", reference_time=NOW)
    await services.async_register_services(hass)

    async def send(request: AlarmRequest) -> None:
        with patch.object(services, "_resolve_sided_targets", return_value=([(coord, "both")], [])):
            await hass.services.async_call(
                const.DOMAIN,
                "set_alarm",
                {
                    "device_id": ["bed"],
                    "enabled": request.enabled,
                    "time": f"{request.hour:02d}:{request.minute:02d}:00",
                    "wake_action": request.wake_action,
                },
                blocking=True,
            )

    with patch(
        "custom_components.adjustable_bed.beds.dreamsense.muuegm.dt_util.now", return_value=NOW
    ):
        for request in (first, replace(first, hour=7, enabled=second_enabled)):
            await send(request)
    for ack in ("6e07010177", "6e07010278", "6e07010177"):
        notify(coord, ack)
        assert coord.controller_state.get(ALARMS) is None
        assert coord.controller_state.get(ACTIVE) is None
    # A new request on the ambiguous link cannot borrow a delayed duplicate ACK.
    await send(replace(first, hour=8))
    notify(coord, "6e07010177")
    assert coord.controller_state.get(ALARMS) is None
    coord.client.is_connected = False
    ctrl.on_disconnect()
    coord._client = make_client(1)
    await ctrl.start_notify()
    notify(coord, "6e09010078")
    await send(first)
    notify(coord, "6e07010177")
    assert coord.controller_state[ALARMS] == {"hour": 6, "minute": 30, "wake_action": "zero_g"}
    assert coord.controller_state[ACTIVE] is True
    ctrl.on_disconnect()


@pytest.mark.parametrize("fresh_reply", [False, True])
@pytest.mark.parametrize("key", ["dreamsense_refresh_alarms", "dreamsense_light_close"])
async def test_cached_idle_button_is_available_and_reconnects_before_fresh_write_admission(
    hass, mock_coordinator_connected, mock_bleak_client, monkeypatch, key, fresh_reply
):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            "address": "11:22:33:44:55:81",
            "name": "Flexx Motion",
            const.CONF_BED_TYPE: "flexx_motion",
            const.CONF_PROTOCOL_VARIANT: "PB325",
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
            "capabilities": {
                "flexx_motion": {"product": "PB325", "single": False, "clock": True, "light": True}
            },
        },
    )
    entry.add_to_hass(hass)
    coord = AdjustableBedCoordinator(hass, entry)
    mock_bleak_client.services = make_client(1).services
    monkeypatch.setattr(FlexxMotionController, "_wait", AsyncMock())

    async def reply(char, callback):
        if fresh_reply:
            callback(char, bytearray.fromhex("6e09010078 6e0e00037f"))

    mock_bleak_client.start_notify.side_effect = reply
    await coord.async_prime_offline_controller()
    controller = coord.capability_controller
    assert isinstance(controller, FlexxMotionController)
    spec = next(s for s in controller.controller_button_specs if s.key == key)
    button = ControllerActionButton(coord, spec)
    registry = er.async_get(hass)
    registry.async_get_or_create("button", const.DOMAIN, button.unique_id, disabled_by=None)
    await async_setup_component(hass, "button", {})
    await async_add_entry_entities(hass, entry, "button", [button])
    assert not coord.is_connected
    assert button.available and hass.states.get(button.entity_id).state != "unavailable"
    try:
        call = hass.services.async_call(
            "button", "press", {"entity_id": button.entity_id}, blocking=True
        )
        if fresh_reply:
            await call
        else:
            with raises_key("dreamsense_capability"):
                await call
        assert coord.is_connected and mock_bleak_client.start_notify.await_count == 1
        packets = [c.args[1] for c in mock_bleak_client.write_gatt_char.await_args_list]
        mutation = (
            codec.record_20_len(5, 1, 0, (0,)) if key.endswith("alarms") else codec.function(0x75)
        )
        assert (mutation in packets) is fresh_reply
    finally:
        await coord.async_shutdown()


async def test_failed_disconnect_preserves_ack_ambiguity_until_a_real_new_connection(
    hass, mock_coordinator_connected, mock_bleak_client, monkeypatch
):
    from bleak.exc import BleakError

    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            "address": "11:22:33:44:55:81",
            "name": "Flexx Motion",
            const.CONF_BED_TYPE: "flexx_motion",
            const.CONF_PROTOCOL_VARIANT: "blue",
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        },
    )
    entry.add_to_hass(hass)
    coord = AdjustableBedCoordinator(hass, entry)
    mock_bleak_client.services = make_client(1).services
    monkeypatch.setattr(FlexxMotionController, "_wait", AsyncMock())

    async def subscribe(char, callback):
        callback(char, bytearray.fromhex("6e09010078"))

    mock_bleak_client.start_notify.side_effect = subscribe
    await services.async_register_services(hass)

    async def send(hour):
        with patch.object(services, "_resolve_sided_targets", return_value=([(coord, "both")], [])):
            await hass.services.async_call(
                const.DOMAIN,
                "set_alarm",
                {
                    "device_id": ["bed"],
                    "enabled": True,
                    "time": f"{hour:02d}:30:00",
                    "wake_action": "zero_g",
                },
                blocking=True,
            )

    try:
        assert await coord.async_connect()
        original_controller, original_generation = coord.controller, coord.connection_generation
        assert isinstance(original_controller, FlexxMotionController)
        original_subscription = mock_bleak_client.start_notify.await_args.args[1]
        await send(6)
        await send(7)
        mock_bleak_client.disconnect.side_effect = BleakError("Link retained")
        assert await coord.async_disconnect(reason="idle_timeout") is False
        assert coord.client is mock_bleak_client and coord.controller is original_controller
        assert coord.connection_generation == original_generation and coord.is_connected
        assert mock_bleak_client.start_notify.await_count == 2
        assert mock_bleak_client.start_notify.await_args.args[1] is not original_subscription
        await send(8)
        # The first old bare ACK is delivered through the restored subscription.
        notify(coord, "6e07010177")
        assert coord.controller_state.get(ALARMS) is None
        assert coord.controller_state.get(ACTIVE) is None

        async def close_link():
            mock_bleak_client.is_connected = False

        mock_bleak_client.disconnect.side_effect = close_link
        assert await coord.async_disconnect(reason="manual")
        assert not coord.is_connected
        assert await coord.async_connect()
        # The transport fixture reuses its client object, but this is a new
        # physical connection generation, not a notification restart.
        assert coord.client is mock_bleak_client
        assert coord.connection_generation > original_generation
        await send(9)
        notify(coord, "6e07010177")
        assert coord.controller_state[ALARMS] == {"hour": 9, "minute": 30, "wake_action": "zero_g"}
        assert coord.controller_state[ACTIVE] is True
    finally:
        mock_bleak_client.disconnect.side_effect = lambda: setattr(
            mock_bleak_client, "is_connected", False
        )
        await coord.async_shutdown()
