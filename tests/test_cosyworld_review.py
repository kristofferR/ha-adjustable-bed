"""Sol round-one fixes through native notification, teardown, setup and entity paths."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.octo.cosyworld import CosyworldController
from custom_components.adjustable_bed.codec.octo import _encode_capability_value
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.light import _light_entities_for
from custom_components.adjustable_bed.pairing import get_child
from custom_components.adjustable_bed.pairing_candidates import (
    CONF_PAIR_SELECTION,
    encode_pair_selection,
)
from custom_components.adjustable_bed.profiles import cosyworld as app
from tests.error_helpers import raises_key
from tests.test_cosyworld import VECTORS, complete, record, writes
from tests.test_cosyworld import runtime as runtime


def session_replies(c, client, records, *, after_records=None):
    """Radio-only fixture: actual subscribe/startup/parser/controller paths run."""
    callbacks = []
    client.start_notify.side_effect = lambda _char, cb: callbacks.append(cb)
    info = bytes.fromhex(next(r["expected_bytes"] for r in VECTORS if r["id"] == "V-info-response"))

    def receive(command, data):
        callbacks[-1](MagicMock(), bytearray(c._build_packet(command, data)))

    async def answer(_char, payload, **_kwargs):
        if payload == app.STARTUP[0]:
            callbacks[-1](MagicMock(), bytearray(app.HANDSHAKE_RESPONSE))
        elif payload == app.STARTUP[1]:
            callbacks[-1](MagicMock(), bytearray(info))
        elif payload == app.STARTUP[2]:
            for r in records:
                receive([0x21, 0x71], _encode_capability_value(r, r.value))
            if after_records:
                after_records(receive)
            receive([0x21, 0x71], [255, 255, 255, 0, 0, 0])

    client.write_gatt_char.side_effect = answer
    return callbacks, receive


@pytest.mark.parametrize("before_end", (0x44, 0x43))
async def test_cap_end_preserves_newer_pin_notification_through_startup(runtime, before_end):
    co, c, client = runtime
    _, receive = session_replies(
        c,
        client,
        [record(1, characteristic=b"\x02"), record(3, b"\x01\x01"), record(0x102, b"\x00\x40")],
        after_records=lambda notify: notify([0x21, before_end], [] if before_end == 0x44 else [0]),
    )
    assert await c.discover_features()
    try:
        assert c.controller_entity_discovery_complete
        assert c._pin_feature_active is True and c._has_pin is True
        assert c._pin_locked is True
        assert not c.normal_controls_available
        with raises_key("cosyworld_locked"):
            await c.lights_on()
        assert writes(client) == list(app.STARTUP)
        # A newer genuine unlock remains usable through a repeated CAP_END too.
        receive([0x21, 0x43], [1])
        receive([0x21, 0x71], [255, 255, 255, 0, 0, 0])
        assert c.normal_controls_available
    finally:
        await c.stop_keepalive()


@pytest.mark.parametrize("wait_lane", ("_lock", "_command_lock"))
async def test_reset_service_timer_never_disconnects_a_session_replaced_under_lock(
    runtime,
    hass,
    monkeypatch,
    wait_lane,
):
    from custom_components.adjustable_bed.services import async_register_services
    from tests.test_octo_services import _register_service_device

    co, c, client = runtime
    co._link_ready = True
    device = _register_service_device(hass, co.entry, co)
    await async_register_services(hass)
    timers = []
    c.profile = replace(app.PROFILE, reset_disconnect_s=0)
    monkeypatch.setattr(
        co.entry, "async_create_background_task", lambda _h, coro, **_kw: timers.append(coro)
    )
    await hass.services.async_call(
        const.DOMAIN,
        "octo_reset_defaults",
        {
            "device_id": device.id,
            "confirmed": True,
        },
        blocking=True,
    )
    assert writes(client) == [bytes.fromhex("40 20 ae 00 00 b2 40")]
    lock = getattr(co, wait_lane)
    await lock.acquire()
    timer = asyncio.create_task(timers.pop())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert not timer.done()
    replacement = MagicMock(is_connected=True, disconnect=AsyncMock())
    co._client = replacement
    lock.release()
    await timer
    replacement.disconnect.assert_not_called()
    client.disconnect.assert_not_called()
    assert co.client is replacement
    co._cancel_disconnect_timer()


async def test_pair_flow_captures_each_cosyworld_snapshot_and_offline_constructor(
    runtime, hass, mock_coordinator_connected
):
    left, c, client = runtime
    complete(c, record(0x102, b"\x00\x40"), record(2, characteristic=b"\x02"))
    left.entry.mock_state(hass, ConfigEntryState.LOADED)
    hass.data.setdefault(const.DOMAIN, {})[left.entry.entry_id] = left
    right_entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Right Cosyworld",
        unique_id="AA:BB:CC:DD:99:02",
        state=ConfigEntryState.LOADED,
        data={**left.entry.data, CONF_ADDRESS: "AA:BB:CC:DD:99:02", CONF_NAME: "Right Cosyworld"},
    )
    right_entry.add_to_hass(hass)
    right = AdjustableBedCoordinator(hass, right_entry)
    right._client = client
    rc = CosyworldController(right)
    right._controller = rc
    rc._device_info = dict(c._device_info)
    complete(
        rc,
        record(1, characteristic=b"\x02"),
        record(3, b"\x00\x01", characteristic=b"\x00"),
        record(0x102, b"\x01\x41"),
        record(2, characteristic=b"\x02"),
    )
    rc._session_ready = True
    hass.data[const.DOMAIN][right_entry.entry_id] = right
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    result = await flow.async_step_pair_beds(
        {CONF_PAIR_SELECTION: encode_pair_selection(left.entry.entry_id, right_entry.entry_id)}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    from custom_components.adjustable_bed import _build_paired_children

    parent = MockConfigEntry(domain=const.DOMAIN, title="Paired Cosyworld", data=result["data"])
    parent.add_to_hass(hass)
    children = _build_paired_children(hass, parent)
    for side, tail in (("left", 0x40), ("right", 0x41)):
        child = get_child(result["data"], side)
        assert "cosyworld" in child["capabilities"] and "octo" not in child["capabilities"]
        assert (
            child["capabilities"]["cosyworld"]["capability_records"][str(0x102)]["value"][1] == tail
        )
        offline = children[side]
        await offline.async_prime_offline_controller()
        cached = offline.capability_controller
        assert isinstance(cached, CosyworldController)
        assert len(cached.motor_control_specs) == 3 and cached.memory_slot_count == 2
        assert cached.supports_lights and cached.normal_controls_available
        lights = _light_entities_for(hass, offline)
        assert len(lights) == 1 and lights[0].available
        # A remembered surface can request connection, never write from saved PIN/caps.
        with raises_key("cosyworld_session"):
            await cached.lights_on()
    # A fresh flow can also read a previously persisted Cosyworld snapshot.
    persisted = MockConfigEntry(
        domain=const.DOMAIN, title="Saved", data=get_child(result["data"], "left")
    )
    fresh = AdjustableBedConfigFlow()
    fresh.hass = hass
    assert fresh._octo_capability_snapshot(persisted) is not None
    # The remembered light can enter normal command admission and reconnect.
    # A fresh locked PIN record must defeat the saved unlocked snapshot.
    offline = children["left"]
    cached = offline.capability_controller
    session_replies(
        cached,
        client,
        [record(1, characteristic=b"\x02"), record(3, b"\x01\x00"), record(0x102, b"\x00\x40")],
    )
    client.write_gatt_char.reset_mock()
    with pytest.raises(PermissionError):
        await offline.async_execute_controller_command(lambda controller: controller.lights_on())
    assert writes(client) == list(app.STARTUP)
    assert offline.controller is not cached and not offline.controller.normal_controls_available
    offline._cancel_disconnect_timer()


async def test_failed_disconnect_restores_full_cosyworld_session_before_next_public_command(
    runtime,
):
    co, c, client = runtime
    complete(c, record(0x102, b"\x00\x40"))
    session_replies(
        c,
        client,
        [
            record(1, characteristic=b"\x02"),
            record(3, b"\x00\x01", characteristic=b"\x00"),
            record(0x102, b"\x00\x40"),
        ],
    )
    co._link_ready = True
    client.disconnect.side_effect = BleakError("receiver kept the link")
    assert await co.async_disconnect() is False
    assert co.client is client and co.controller is c
    assert c._session_ready and c._notifications_started and co._link_ready
    assert writes(client) == list(app.STARTUP)
    client.write_gatt_char.reset_mock()
    await co.async_execute_controller_command(
        lambda controller: controller.lights_on(), resource="lighting"
    )
    assert len(writes(client)) == 1
    assert writes(client)[0].hex() == "40207200099e00010200010101013c0140"
    co._cancel_disconnect_timer()


async def test_retained_link_restore_without_handshake_remains_unusable(runtime):
    co, c, client = runtime
    complete(c, record(0x102, b"\x00\x40"))
    c.profile = replace(app.PROFILE, handshake_timeout_s=0.001)
    client.start_notify.side_effect = None
    client.write_gatt_char.side_effect = None
    co._link_ready = True
    client.disconnect.side_effect = BleakError("receiver kept the link")
    assert await co.async_disconnect() is False
    assert not co._link_ready and not c._session_ready
    with raises_key("cosyworld_session"):
        await c.lights_on()
    assert writes(client) == [app.STARTUP[0]]
    co._cancel_disconnect_timer()


async def test_rc2_bluetooth_flow_requires_app_choice_with_octo_first(
    hass,
    mock_bluetooth_service_info_octo_rc2,
    enable_custom_integrations,
):
    info = mock_bluetooth_service_info_octo_rc2
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=info
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "bluetooth_disambiguate"
    selector = next(
        v for k, v in result["data_schema"].schema.items() if k.schema == "bed_type_choice"
    )
    values = [option["value"] for option in selector.config["options"]]
    assert values[0] == "octo" and "cosyworld" in values


async def test_native_onoff_light_tracks_pin_lock_and_unlock_availability(runtime, hass):
    co, c, client = runtime
    complete(c, record(0x102, b"\x00\x40"))
    callbacks = []
    client.start_notify.side_effect = lambda _char, cb: callbacks.append(cb)
    await c.start_notify()
    lights = _light_entities_for(hass, co)
    assert len(lights) == 1 and lights[0].available
    try:
        callbacks[-1](MagicMock(), bytearray(c._build_packet([0x21, 0x44])))
        assert not lights[0].available
        callbacks[-1](MagicMock(), bytearray(c._build_packet([0x21, 0x43], [1])))
        assert lights[0].available
    finally:
        await c.stop_keepalive()


async def test_reset_timer_releases_its_matching_session_through_serialized_disconnect(
    runtime, monkeypatch
):
    co, c, client = runtime
    co._link_ready = True
    c.profile = replace(app.PROFILE, reset_disconnect_s=0)
    timers = []
    monkeypatch.setattr(
        co.entry, "async_create_background_task", lambda _h, coro, **_kw: timers.append(coro)
    )

    async def disconnected():
        client.is_connected = False

    client.disconnect.side_effect = disconnected
    await c.reset_defaults()
    await timers.pop()
    client.disconnect.assert_awaited_once()
    assert co.client is None and co.controller is None
