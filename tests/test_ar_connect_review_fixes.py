"""Public HA and live-session regressions from full-runtime Sol review S1–S6."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.ar_connect.controller import build_controller
from custom_components.adjustable_bed.beds.ar_connect.headboard import (
    LAST_CREATED_ROUTINE_ID,
    MOOD_DELAY,
    MOOD_ON,
    ROUTINE_COUNT,
    ROUTINE_LIST,
    STATUS,
)
from custom_components.adjustable_bed.beds.builder import BuildContext
from custom_components.adjustable_bed.bluetooth_transport import ConnectionPath, TransportClass
from custom_components.adjustable_bed.codec import ar_connect as codec
from custom_components.adjustable_bed.coordinator_connection import _ConnectSession
from custom_components.adjustable_bed.errors import BedNotConnectedError
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    PairedSideProxy,
)
from custom_components.adjustable_bed.paired_devices import child_device_info
from custom_components.adjustable_bed.pairing import build_pair_entry_data
from tests.hold_lease_wire import virtual_clock
from tests.test_ar_connect_runtime import RX, hb, publish_runtime, runtime, writes


@pytest.fixture
async def paired(hass):
    left = await runtime(hass, mask=None, address="AA:BB:CC:DD:EE:81")
    right = await runtime(hass, mask=None, address="AA:BB:CC:DD:EE:82")
    for _, c, *_ in (left, right):
        await publish_runtime(hass, c)
    data = build_pair_entry_data(
        dict(left[1].entry.data), dict(right[1].entry.data), name="AR pair"
    )
    parent = MockConfigEntry(domain=const.DOMAIN, title="AR pair", version=5, data=data)
    pair = PairedBedCoordinator(
        hass, parent, {"left": left[1], "right": right[1]}, connection_mode="concurrent"
    )
    parent_id = await publish_runtime(hass, pair)
    registry = dr.async_get(hass)
    children = {
        side: registry.async_get_or_create_child_from_info(
            config_entry_id=parent.entry_id, device_info=child_device_info(pair, side)
        ).id
        for side in ("left", "right")
    }
    for row in (left, right):
        row[2].write_gatt_char.reset_mock()
    yield pair, parent_id, children, left, right
    for row in (left, right):
        row[2].is_connected = False
    await pair.async_shutdown()


async def call(hass, service, device_id, **data):
    await hass.services.async_call(
        const.DOMAIN, service, {"device_id": device_id, **data}, blocking=True
    )


@pytest.mark.parametrize("route_change,established", [(False, True), (True, True), (False, False)])
async def test_s1_proxy_reconnect_reuses_only_actual_route_completed_attempt(
    hass, route_change, established
):
    _, c, client, _, _ = await runtime(hass)
    c.entry.add_to_hass(hass)
    c._connection_path = ConnectionPath(
        "new-proxy" if route_change else "paired-proxy", TransportClass.PROXY
    )
    c._async_observe_native_bond = AsyncMock(return_value=False)
    hass.config_entries.async_update_entry(
        c.entry,
        data={
            **c.entry.data,
            "ble_bond_established": established,
            "ble_bond_attempted_source": "paired-proxy",
        },
    )
    c._ble_bond_established = established
    client.pair = AsyncMock(
        side_effect=BleakError("redundant pair refused")
        if established and not route_change
        else None,
        return_value=True,
    )
    session = _ConnectSession(c, client, {}, c.connection_generation)
    await session.async_require_native_bond()
    assert client.pair.await_count == (0 if established and not route_change else 1)
    assert "ble_bond_context" not in c.entry.data
    client.is_connected = False
    await c.async_shutdown()


@pytest.mark.parametrize("cache_cleared", [False, True])
async def test_s1_auth_failure_invalidates_proxy_attempt_even_during_cache_retry(
    hass, cache_cleared
):
    _, c, client, _, _ = await runtime(hass)
    c.entry.add_to_hass(hass)
    c._connection_path = ConnectionPath("proxy", TransportClass.PROXY)
    c._async_observe_native_bond = AsyncMock(return_value=False)
    c._record_native_bond_attempt("proxy")
    c._attempt_trusted_bond_marker = True
    c._async_raise_pairing_issue = AsyncMock()
    with (
        patch(
            "custom_components.adjustable_bed.coordinator_bonds.async_clear_proxy_gatt_cache",
            new=AsyncMock(return_value=cache_cleared),
        ),
        patch.object(c, "async_disconnect", new=AsyncMock()),
    ):
        await c._async_handle_ble_authentication_error(
            BleakError("Insufficient authentication"), defer_pairing_issue=True
        )
    assert not c._ble_bond_established and not c._unverified_marker_applies("proxy")
    assert not c.entry.data["ble_bond_established"]
    client.pair = AsyncMock(return_value=True)
    await _ConnectSession(c, client, {}, c.connection_generation).async_require_native_bond()
    client.pair.assert_awaited_once()
    await _ConnectSession(c, client, {}, c.connection_generation).async_require_native_bond()
    client.pair.assert_awaited_once()
    assert not c._ble_bond_marker_unreliable
    client.is_connected = False
    await c.async_shutdown()


MOTION_CALLS = [
    ("ar_connect_move_sections", {"directions": {"back": "up"}, "duration_ms": 600}),
    ("timed_move", {"motor": "back", "direction": "up", "duration_ms": 600}),
    ("hold_control", {"control": "back_up", "duration": 0.6}),
    ("goto_preset", {"preset": 1, "duration": 0.6}),
]


@pytest.mark.parametrize("service,fields", MOTION_CALLS)
async def test_s2_combined_parent_cannot_fan_out_any_shared_motion(hass, paired, service, fields):
    pair, parent_id, _, left, right = paired
    counts = [row[1].cancel_counter for row in (left, right)]
    with pytest.raises(ServiceValidationError, match="one physical receiver"):
        await call(hass, service, parent_id, **fields)
    assert [row[1].cancel_counter for row in (left, right)] == counts
    assert not writes(left[2]) and not writes(right[2])
    for row in (left, right):
        row[1].async_ensure_connected.assert_not_awaited()


@pytest.mark.parametrize("selection", ["left", "right", "child_left", "child_right"])
async def test_s2_explicit_side_and_native_child_keep_one_recipient(hass, paired, selection):
    _, parent_id, children, left, right = paired
    side = selection.removeprefix("child_")
    device = children[side] if selection.startswith("child_") else parent_id
    fields = {} if selection.startswith("child_") else {"side": side}
    with virtual_clock():
        await call(
            hass,
            "ar_connect_move_sections",
            device,
            directions={"back": "up"},
            duration_ms=600,
            **fields,
        )
    active, inactive = (left, right) if side == "left" else (right, left)
    assert [row[1] for row in writes(active[2])] == [b"\x0b\0", b"\xfe\0"]
    assert not writes(inactive[2])


async def test_s2_pair_api_and_cover_cannot_bypass_recipient_gate_but_stop_fans_out(hass, paired):
    from custom_components.adjustable_bed.button import _combined_button_entities_for
    from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description

    pair, _, _, left, right = paired
    assert not pair.supports_simultaneous_side_holds
    assert not _combined_button_entities_for(pair, [left[1], right[1]])
    with pytest.raises(ServiceValidationError):
        await pair.async_execute_controller_command(lambda c: c.move_back_up())
    # Ordinary covers use a side view and retain that explicit physical target.
    view = PairedSideProxy(pair, left[1], "left")
    entity = AdjustableBedCover(view, _build_cover_description(left[0].motor_control_specs[0]))
    entity.async_write_ha_state = MagicMock()
    with virtual_clock():
        await entity.async_open_cover()
    assert writes(left[2]) and not writes(right[2])
    before = [row[1].stop_epoch for row in (left, right)]
    await pair.async_stop_command()
    assert all(row[1].stop_epoch > epoch for row, epoch in zip((left, right), before, strict=True))


def fragments():
    return [
        bytes.fromhex(row["input_hex"])
        for row in RX
        if row["id"] in ("FD01.length", "FD01.first_chunk", "FD01.completed_chunks")
    ]


async def test_s3_created_id_is_visible_then_public_refresh_enables_edit_delete(hass):
    from custom_components.adjustable_bed.button import ControllerActionButton
    from custom_components.adjustable_bed.sensor import AdjustableBedControllerStateSensor

    ctrl, c, client, callbacks, _ = await runtime(hass, "headboard")
    device = await publish_runtime(hass, c)
    ctrl.receive("routine", b'{"createid":13}')
    assert c.controller_state.get(LAST_CREATED_ROUTINE_ID) == "13"
    assert (
        c.controller_state.get(ROUTINE_COUNT) is None
        and c.controller_state.get(ROUTINE_LIST) is None
    )
    assert "13" not in ctrl.routines
    sensor_spec = next(
        spec for spec in ctrl.controller_state_sensor_specs if spec.key == "ar_headboard_routines"
    )
    sensor = AdjustableBedControllerStateSensor(c, sensor_spec)
    assert sensor.native_value is None
    assert sensor.extra_state_attributes[LAST_CREATED_ROUTINE_ID] == "13"
    original = client.read_gatt_char.side_effect
    stored = codec.compact_json({"13": codec.Routine(True, "wake", 7, 30, 10).payload()})

    async def read(char):
        if char.uuid == hb.TRANSPORTS["routine"][1]:
            asyncio.get_running_loop().call_soon(callbacks[char.uuid], char, bytearray(stored))
            return codec.compact_json({"length": len(stored)})
        return await original(char)

    client.read_gatt_char.side_effect = read
    await call(hass, "ar_connect_routine", device, action="refresh")
    assert c.controller_state.get(ROUTINE_COUNT) == 1 and "13" in c.controller_state.get(
        ROUTINE_LIST
    )
    assert c.controller_state.get(LAST_CREATED_ROUTINE_ID) == "13"
    refresh_spec = ctrl.controller_button_specs[0]
    assert refresh_spec.diagnostic and not refresh_spec.entity_registry_enabled_default
    refresh = ControllerActionButton(c, refresh_spec)
    refresh.async_write_ha_state = MagicMock()
    await refresh.async_press()
    await call(
        hass,
        "ar_connect_routine",
        device,
        action="update",
        id=13,
        mode="sleep",
        hour=22,
        duration=5,
    )
    assert writes(client)[-2][1] == b'{"id":13}'
    assert codec.object_record(writes(client)[-1][1])["mode"] == "sleep"
    await call(hass, "ar_connect_routine", device, action="delete", id=13)
    assert writes(client)[-1][1] == b'{"id":13}'
    client.is_connected = False
    await c.async_shutdown()


@pytest.mark.parametrize("interruption", ["cancel", "replacement", "malformed"])
async def test_s3_refresh_is_bound_to_session_and_does_not_fabricate_records(hass, interruption):
    ctrl, c, client, callbacks, _ = await runtime(hass, "headboard")
    with virtual_clock():
        task = asyncio.create_task(ctrl.refresh_routines())
        await asyncio.sleep(0.05)
        if interruption == "cancel":
            c.cancel_command.set()
        elif interruption == "replacement":
            c._client = MagicMock(is_connected=True, disconnect=AsyncMock())
            callbacks[hb.TRANSPORTS["routine"][1]](None, bytearray(b'{"createid":13}'))
        else:
            ctrl.receive("routine", b"{broken")
        if interruption == "replacement":
            with pytest.raises(BedNotConnectedError):
                await task
        elif interruption == "malformed":
            with pytest.raises(TimeoutError):
                await task
        else:
            await task
    assert c.controller_state.get(ROUTINE_LIST) is None and not ctrl.routines
    if interruption == "replacement":
        assert c.controller_state.get(LAST_CREATED_ROUTINE_ID) is None
    client.is_connected = False
    await c.async_shutdown()


@pytest.mark.parametrize(
    "key,cleared", [("mood_state", MOOD_ON), ("mood_values", MOOD_DELAY), ("status", STATUS)]
)
async def test_s4_corrupt_characteristic_preserves_other_fragment_and_state(hass, key, cleared):
    ctrl, c, _, _, _ = await runtime(hass, "headboard")
    ctrl.receive("status", b'{"sysstat":"live"}')
    ctrl.receive("mood_state", b'{"scenstat":true}')
    start, first, last = fragments()
    ctrl.receive("routine", start)
    ctrl.receive("routine", first)
    ctrl.receive(key, b"{broken")
    assert c.controller_state.get(cleared) is None
    if key != "status":
        assert c.controller_state.get(STATUS) == "live"
    if key != "mood_state":
        assert c.controller_state.get(MOOD_ON) is True
    ctrl.receive("routine", last)
    assert c.controller_state.get(ROUTINE_COUNT) == 1 and "12" in ctrl.routines
    ctrl.receive(
        key,
        b'{"scenstat":false}'
        if key == "mood_state"
        else b'{"sysstat":"idle"}'
        if key == "status"
        else codec.mood(False, 5, ((0, 0, 255, 0),) * 5),
    )
    assert c.controller_state.get(cleared) is not None


@pytest.mark.parametrize("snapshot_layout", [None, "back_legs_head_feet", "back_legs"])
async def test_s5_snapshot_only_restores_axes_for_its_configured_layout(hass, snapshot_layout):
    _, c, client, _, _ = await runtime(hass, layout="back_legs")
    c.entry.add_to_hass(hass)
    saved = {"axes": ["back", "legs", "head", "feet"], "mask": 240}
    if snapshot_layout is not None:
        saved["layout"] = snapshot_layout
    hass.config_entries.async_update_entry(
        c.entry, data={**c.entry.data, "capabilities": {"ar_connect": saved}}
    )
    rebuilt = await build_controller(
        BuildContext(coordinator=c, bed_type="ar_connect", variant="native", client=None)
    )
    assert rebuilt.axes == (
        ("back", "legs", "head", "feet") if snapshot_layout == "back_legs" else ("back", "legs")
    )
    if snapshot_layout != "back_legs":
        with pytest.raises(ServiceValidationError):
            rebuilt.validate_hold_control("head_up", 600)
    assert rebuilt.capability_snapshot()["layout"] == "back_legs"
    client.is_connected = False
    await c.async_shutdown()


@pytest.mark.parametrize("service,fields", MOTION_CALLS)
async def test_s6_public_second_start_is_ignored_before_preemption(hass, paired, service, fields):
    pair, parent_id, _, left, right = paired
    with virtual_clock():
        first = asyncio.create_task(
            call(
                hass,
                "ar_connect_move_sections",
                parent_id,
                side="left",
                directions={"back": "up"},
                duration_ms=1000,
            )
        )
        await asyncio.sleep(0.1)
        before = left[1].cancel_counter
        generation = pair.pair_cancel_generation("left", frozenset({"*"}))
        await call(hass, service, parent_id, side="left", **fields)
        assert not first.done() and left[1].cancel_counter == before
        assert pair.pair_cancel_generation("left", frozenset({"*"})) == generation
        assert not writes(left[2])
        await first
    assert [row[1] for row in writes(left[2])] == [b"\x0b\0", b"\x0b\0", b"\xfe\0"]
    assert not writes(right[2])


async def test_s6_standalone_cover_debounce_and_explicit_stop(hass):
    from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description

    ctrl, c, client, _, _ = await runtime(hass, mask=None)
    await publish_runtime(hass, c)
    entity = AdjustableBedCover(c, _build_cover_description(ctrl.motor_control_specs[0]))
    entity.async_write_ha_state = MagicMock()
    client.write_gatt_char.reset_mock()
    with virtual_clock():
        first = asyncio.create_task(entity.async_open_cover())
        await asyncio.sleep(0.1)
        before = c.cancel_counter
        await entity.async_close_cover()
        assert not first.done() and c.cancel_counter == before and not writes(client)
        assert entity._is_moving and entity._move_direction == "open"
        await entity.async_stop_cover()
        await first
    assert [row[1] for row in writes(client)] == [b"\xfe\0"]
    client.is_connected = False
    await c.async_shutdown()


async def test_s6_start_after_window_replaces_prior_motion(hass, paired):
    _, parent, _, left, right = paired
    with virtual_clock():
        first = asyncio.create_task(
            call(
                hass,
                "ar_connect_move_sections",
                parent,
                side="left",
                directions={"back": "up"},
                duration_ms=1000,
            )
        )
        await asyncio.sleep(0.25)
        await call(
            hass,
            "ar_connect_move_sections",
            parent,
            side="left",
            directions={"back": "down"},
            duration_ms=600,
        )
        await first
    assert [row[1] for row in writes(left[2])] == [b"\xfe\0", b"\x0a\0", b"\xfe\0"]
    assert not writes(right[2])
