"""Dunlopillo Remote: frozen builders, native callers and connection ownership."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.keeson.dunlopillo import TIMER, DunlopilloController
from custom_components.adjustable_bed.codec import keeson as codec
from custom_components.adjustable_bed.errors import BedNotConnectedError
from custom_components.adjustable_bed.profiles import dunlopillo as app
from custom_components.adjustable_bed.setup_questions import _dunlopillo_settings
from tests.hold_lease_wire import virtual_clock

VECTORS = json.loads(
    Path(__file__).with_name("fixtures").joinpath("dunlopillo_vectors.json").read_text()
)
FRAMES = {
    int(row["inputs"]["key"], 16): bytes.fromhex(row["expected_bytes"])
    for row in VECTORS
    if "key" in row["inputs"]
}
ADDRESS = "AA:BB:CC:DD:10:01"


@pytest.mark.parametrize("row", VECTORS[:26], ids=lambda row: row["id"])
def test_every_transmit_literal_matches_existing_codec(row):
    actual = (
        codec.frame(int(row["inputs"]["key"], 16))
        if "key" in row["inputs"]
        else app.rename(row["inputs"]["name"])
    )
    assert actual == bytes.fromhex(row["expected_bytes"])


def test_every_layout_word_has_an_independent_literal():
    assert {c.word for controls in app.CONTROLS.values() for c in controls.values()} | {0} == set(
        FRAMES
    )
    assert [len(app.CONTROLS[key]) for key in ("b1", "b2", "c1", "d1")] == [13, 13, 16, 20]
    assert app.rename(" é ")[2:4] == b"\xc3\x00"


@pytest.mark.parametrize("size", (16, 19, 20))
@pytest.mark.parametrize("first", (0, 0xF1))
@pytest.mark.parametrize("offset", (14, 15))
@pytest.mark.parametrize(
    "value,minutes", ((1, 10), (2, 20), (3, 30), (255, 0), (0, None), (128, None))
)
def test_timer_offsets_and_unchanged_values(size, first, offset, value, minutes):
    data = bytearray(size)
    data[0], data[offset] = first, value
    expected_offset = 15 if size == 19 and first != 0xF1 else 14
    assert app.timer_minutes(data) == (minutes if offset == expected_offset else None)


@pytest.mark.parametrize("size", (0, 1, 15, 17, 18, 21, 40))
def test_timer_rejects_other_lengths(size):
    assert app.timer_minutes(bytes(size)) is None


class Char:
    def __init__(self, uuid, properties, handle, descriptors):
        self.uuid, self.properties, self.handle = uuid, properties, handle
        self.descriptors = descriptors


def gatt():
    # No fixed service; the last matching concrete role wins across all services.
    chars = [
        Char(uuid=app.WRITE_UUID, properties=["write"], handle=1, descriptors=[]),
        Char(uuid=app.NOTIFY_UUID, properties=["notify"], handle=2, descriptors=[]),
        SimpleNamespace(
            uuid=app.WRITE_UUID,
            properties=["write", "write-without-response"],
            handle=3,
            descriptors=[],
        ),
        Char(uuid=app.NOTIFY_UUID, properties=["notify"], handle=4, descriptors=[]),
    ]
    return [
        SimpleNamespace(uuid=f"arbitrary-{i}", characteristics=chars[i : i + 1]) for i in range(4)
    ]


def entry(hass, layout):
    data = {
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "Dunlopillo",
        const.CONF_BED_TYPE: "dunlopillo",
        const.CONF_PROTOCOL_VARIANT: layout,
        const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        **_dunlopillo_settings({const.CONF_PROTOCOL_VARIANT: layout}),
    }
    e = MockConfigEntry(domain=const.DOMAIN, unique_id=ADDRESS, title="Dunlopillo", data=data)
    e.add_to_hass(hass)
    return e


@pytest.fixture
async def running(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    enable_custom_integrations,
    mock_async_ble_device_from_address,
    request,
):
    layout = getattr(request, "param", "d1")
    client = mock_bleak_client
    client.services = gatt()
    e = entry(hass, layout)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    target = hass.data[const.DOMAIN][e.entry_id]
    assert isinstance(target.controller, DunlopilloController)
    client.write_gatt_char.reset_mock()
    client.write_gatt_char.side_effect = None
    yield e, target, client
    await hass.config_entries.async_unload(e.entry_id)


def written(client):
    return [bytes(c.args[1]) for c in client.write_gatt_char.call_args_list]


@pytest.mark.parametrize("running", ("b1", "b2", "c1", "d1"), indirect=True)
async def test_native_entities_all_layout_controls_and_rename(hass, running):
    e, target, client = running
    c = target.controller
    assert len(c.motor_control_specs) == len(app.AXES[c.layout])
    assert not c.supports_memory_presets and not c.supports_memory_programming
    assert not c.execution.concurrent
    registry = er.async_get(hass)
    for key, row in app.CONTROLS[c.layout].items():
        client.write_gatt_char.reset_mock()
        with virtual_clock():
            if key == "reset":
                spec = next(s for s in c.controller_button_specs if s.key == "dunlopillo_reset")
                assert spec.requires_confirmation and spec.hold is None
                await target.async_execute_controller_command(spec.press_fn)
            else:
                if key in ("flat", "zero_g"):
                    uid = f"{ADDRESS}_preset_{key}"
                    domain, service = "button", "press"
                elif key == "light":
                    uid, domain, service = f"{ADDRESS}_toggle_light", "button", "press"
                elif key.rsplit("_", 1)[0] in app.AXES[c.layout]:
                    axis, direction = key.rsplit("_", 1)
                    uid, domain, service = (
                        f"{ADDRESS}_{axis}",
                        "cover",
                        "open_cover" if direction == "up" else "close_cover",
                    )
                else:
                    uid, domain, service = f"{ADDRESS}_dunlopillo_{key}", "button", "press"
                entity = registry.async_get_entity_id(domain, const.DOMAIN, uid)
                assert entity is not None, (key, uid)
                await hass.services.async_call(
                    domain, service, {"entity_id": entity}, blocking=True
                )
        frames = written(client)
        repeats = target.motor_pulse_count if row.mode == "hold" else 1
        assert frames == [FRAMES[row.word]] * repeats + (
            [FRAMES[0]] if row.mode != "single" else []
        ), key
        assert all(
            call.args[0].handle == 3 and call.kwargs["response"] is False
            for call in client.write_gatt_char.call_args_list
        )
    client.write_gatt_char.reset_mock()
    await target.async_execute_controller_command(lambda ctrl: ctrl.rename_device("Test"))
    assert written(client) == [bytes.fromhex("ef025465737400000000000000000000006e")]


async def test_cancelled_hold_and_pulse_release_with_fresh_event(running):
    _, target, client = running
    for method in (
        lambda: target.controller.hold_control("head_up", 500),
        lambda: target.controller.action("head_massage_up"),
    ):
        target.cancel_command.clear()
        client.write_gatt_char.reset_mock()

        async def cancel(*_args, **_kwargs):
            target.cancel_command.set()

        client.write_gatt_char.side_effect = cancel
        with virtual_clock():
            await method()
        assert len(written(client)) == 2
        assert written(client)[-1] == FRAMES[0]
    client.write_gatt_char.side_effect = None


async def test_captured_session_rejects_replacement_and_stale_notifications(running):
    _, target, client = running
    c = target.controller
    notify, callback = client.start_notify.call_args.args
    c.forward_controller_state_updates = updates = MagicMock()
    payload = bytearray(19)
    payload[15] = 2
    callback(notify, payload)
    assert updates.call_args.args == (TIMER(20),)
    updates.reset_mock()
    old = c._link
    await c.async_discover_capabilities()
    updates.reset_mock()
    callback(notify, payload)
    updates.assert_not_called()
    with pytest.raises(BedNotConnectedError):
        await c._release(old)
    assert written(client) == []


async def test_slow_backend_does_not_send_expired_hold_frames(running):
    _, target, client = running

    async def slow(*_args, **_kwargs):
        await asyncio.sleep(0.4)

    client.write_gatt_char.side_effect = slow
    with virtual_clock():
        await target.controller.hold_control("head_up", 300)
    assert written(client) == [FRAMES[1], FRAMES[0]]
    client.write_gatt_char.side_effect = None


async def test_native_rename_validates_and_preserves_app_copy(hass, running):
    e, target, client = running
    registry = er.async_get(hass)
    device = next(
        v.device_id for v in registry.entities.values() if v.config_entry_id == e.entry_id
    )
    for name, expected in (
        ("Test", "ef025465737400000000000000000000006e"),
        ("Bed", "ef0242656400000000000000000000000003"),
    ):
        client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            const.DOMAIN, "rename", {"device_id": device, "name": name}, blocking=True
        )
        assert written(client) == [bytes.fromhex(expected)]
    from tests.error_helpers import raises_key

    client.write_gatt_char.reset_mock()
    for name in ("", "  ", "012345678901234", "😀" * 8):
        with raises_key("dunlopillo_name_invalid"):
            await hass.services.async_call(
                const.DOMAIN, "rename", {"device_id": device, "name": name}, blocking=True
            )
    assert written(client) == []


async def test_task_cancellation_settles_submitted_frame_before_release(running):
    _, target, client = running
    first = asyncio.Event()
    finish = asyncio.Event()

    async def send(_char, frame, **_kwargs):
        if bytes(frame) != FRAMES[0]:
            first.set()
            await finish.wait()

    client.write_gatt_char.side_effect = send
    task = asyncio.create_task(target.controller.hold_control("head_up", 500))
    await first.wait()
    task.cancel()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert written(client) == [FRAMES[1], FRAMES[0]]
    client.write_gatt_char.side_effect = None


@pytest.mark.parametrize("layout", app.PROFILES)
def test_setup_owns_layout_and_keeps_bounded_movement_customizable(layout):
    from custom_components.adjustable_bed.app_profiles import hidden_generic_fields
    from custom_components.adjustable_bed.setup_questions import SETUP_PROFILES
    from custom_components.adjustable_bed.validators import is_valid_variant_for_bed_type

    assert is_valid_variant_for_bed_type(const.BED_TYPE_DUNLOPILLO, layout)
    profile = SETUP_PROFILES[const.BED_TYPE_DUNLOPILLO]
    settled = profile.settled({const.CONF_PROTOCOL_VARIANT: layout})
    assert settled[const.CONF_MOTOR_COUNT] == len(app.AXES[layout])
    assert settled[const.CONF_HAS_MASSAGE] is True
    assert settled[const.CONF_DISABLE_ANGLE_SENSING] is True
    assert settled[const.CONF_MOTOR_PULSE_DELAY_MS] == 100
    hidden = hidden_generic_fields(const.BED_TYPE_DUNLOPILLO, layout)
    assert const.CONF_MOTOR_COUNT in hidden
    assert const.CONF_MOTOR_PULSE_COUNT not in hidden


@pytest.mark.parametrize(
    "properties,response",
    (
        (["write"], True),
        (["write-without-response"], False),
        (["write", "write-without-response"], False),
    ),
)
async def test_default_android_write_mode_from_selected_characteristic(
    running, properties, response
):
    _, target, client = running
    target.controller._link.write.properties = properties
    await target.controller.preset_flat()
    assert client.write_gatt_char.call_args.kwargs["response"] is response


@pytest.mark.parametrize(
    "row,minutes",
    zip(VECTORS[26:], (10, 20, 30, 0), strict=True),
    ids=lambda v: v["id"] if isinstance(v, dict) else str(v),
)
def test_frozen_receive_literals(row, minutes):
    assert app.timer_minutes(bytes.fromhex(row["inputs"]["incoming_frame_hex"])) == minutes


@pytest.mark.parametrize("layout", app.PROFILES)
async def test_setup_flow_accepts_each_layout(hass, layout):
    from unittest.mock import patch

    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._manual_data = {const.CONF_BED_TYPE: const.BED_TYPE_DUNLOPILLO}
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: layout})
    saved = finish.call_args.args[0]
    assert saved[const.CONF_PROTOCOL_VARIANT] == layout
    assert saved[const.CONF_MOTOR_COUNT] == len(app.AXES[layout])
    assert saved[const.CONF_HAS_MASSAGE] is True


@pytest.mark.parametrize(
    "control", ("head_up", "reclined", "reset", "head_massage_up", "flat", "light")
)
async def test_dispatch_cadence_and_distinct_release_policies(running, control):
    _, target, client = running
    stamps = []

    async def record(_char, frame, **_kwargs):
        stamps.append((asyncio.get_running_loop().time(), bytes(frame)))

    client.write_gatt_char.side_effect = record
    row = app.CONTROLS["d1"][control]
    with virtual_clock():
        await target.controller.action(control)
    start = stamps[0][0]
    times = [round((at - start) * 1000) for at, _ in stamps]
    count = target.motor_pulse_count
    assert times == (
        list(range(0, (count + 1) * 100, 100))
        if row.mode == "hold"
        else [0, 300]
        if row.mode == "pulse"
        else [0]
    )
    client.write_gatt_char.side_effect = None


@pytest.mark.parametrize("failing_handles", ({2}, {2, 4}))
@pytest.mark.parametrize("subscribe_error", ("bleak", "timeout"))
async def test_optional_timer_subscriptions_do_not_block_native_controls(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    enable_custom_integrations,
    mock_async_ble_device_from_address,
    failing_handles,
    subscribe_error,
):
    from bleak.exc import BleakError

    client = mock_bleak_client
    client.services = gatt()
    callbacks = {}

    async def subscribe(char, callback):
        callbacks[char.handle] = callback
        if char.handle in failing_handles:
            raise (
                BleakError("NotSupported")
                if subscribe_error == "bleak"
                else TimeoutError("proxy timeout")
            )

    client.start_notify.side_effect = subscribe
    client.write_gatt_char.side_effect = None
    e = entry(hass, "d1")
    assert await hass.config_entries.async_setup(e.entry_id)
    target = hass.data[const.DOMAIN][e.entry_id]
    try:
        assert set(callbacks) == {2, 4}
        client.write_gatt_char.reset_mock()
        entity = er.async_get(hass).async_get_entity_id(
            "button", const.DOMAIN, f"{ADDRESS}_preset_flat"
        )
        await hass.services.async_call("button", "press", {"entity_id": entity}, blocking=True)
        assert written(client) == [FRAMES[0x08000000]]
        target.controller.forward_controller_state_updates = updates = MagicMock()
        for char in target.controller._link.notifies:
            payload = bytearray(16)
            payload[14] = 1
            callbacks[char.handle](char, payload)
        assert updates.call_count == 2 - len(failing_handles)
    finally:
        await hass.config_entries.async_unload(e.entry_id)


async def test_all_receive_handles_have_independent_callbacks(running):
    _, target, client = running
    c = target.controller
    callbacks = {call.args[0].handle: call.args for call in client.start_notify.call_args_list}
    assert set(callbacks) == {2, 4}
    c.forward_controller_state_updates = updates = MagicMock()
    for handle, minutes in ((2, 10), (4, 20)):
        char, callback = callbacks[handle]
        data = bytearray(16)
        data[14] = minutes // 10
        callback(char, data)
        assert updates.call_args.args == (TIMER(minutes),)
        updates.reset_mock()
        other = callbacks[4 if handle == 2 else 2][0]
        callback(other, data)
        updates.assert_not_called()
    # Restarting an existing subscription does not duplicate it.
    await c.start_notify()
    assert client.start_notify.call_count == 2


@pytest.mark.parametrize("error", (asyncio.CancelledError, RuntimeError))
async def test_subscription_does_not_swallow_cancellation_or_other_errors(running, error):
    _, target, client = running
    c = target.controller
    await c.stop_notify()
    client.start_notify.side_effect = error()
    with pytest.raises(error):
        await c.start_notify()
    client.start_notify.side_effect = None


@pytest.mark.parametrize("stale", ("generation", "disconnected", "binding"))
@pytest.mark.parametrize("error", ("bleak", "timeout"))
async def test_ble_subscribe_error_only_optional_on_exact_live_session(running, stale, error):
    from dataclasses import replace

    from bleak.exc import BleakError

    _, target, client = running
    c = target.controller
    await c.stop_notify()
    old = c._link

    async def fail(*_args):
        if stale == "generation":
            c._link = replace(old, generation=old.generation - 1)
        elif stale == "disconnected":
            client.is_connected = False
        else:
            c._link = replace(old)
        raise (BleakError("NotSupported") if error == "bleak" else TimeoutError("proxy timeout"))

    client.start_notify.side_effect = fail
    try:
        with pytest.raises(BedNotConnectedError):
            await c.start_notify()
    finally:
        client.start_notify.side_effect = None
        client.is_connected = True
        c._link = old


@pytest.mark.parametrize("failure", ("error", "cancelled"))
async def test_retained_disconnect_restores_same_binding_and_fences_old_callbacks(running, failure):
    from bleak.exc import BleakError

    _, target, client = running
    c = target.controller
    old_link = c._link
    old_callbacks = [call.args for call in client.start_notify.call_args_list]
    client.disconnect.side_effect = (
        BleakError("link retained") if failure == "error" else asyncio.CancelledError()
    )
    try:
        if failure == "error":
            assert not await target.async_disconnect("sequential_switch")
        else:
            with pytest.raises(asyncio.CancelledError):
                await target.async_disconnect("sequential_switch")
        assert c._link is old_link
        assert target.controller is c and target.is_connected
        assert client.start_notify.call_count == 4
        assert {call.args[0].handle for call in client.stop_notify.call_args_list} == {2, 4}
        c.forward_controller_state_updates = updates = MagicMock()
        data = bytearray(16)
        data[14] = 3
        for char, callback in old_callbacks:
            callback(char, data)
        updates.assert_not_called()
        for call in client.start_notify.call_args_list[-2:]:
            char, callback = call.args
            callback(char, data)
        assert updates.call_args_list == [((TIMER(30),),), ((TIMER(30),),)]
        client.write_gatt_char.reset_mock()
        await target.async_execute_controller_command(lambda ctrl: ctrl.preset_flat())
        assert written(client) == [FRAMES[0x08000000]]
    finally:
        client.disconnect.side_effect = None


async def test_cancelled_stop_preserves_binding_and_can_restore_subscriptions(running):
    _, target, client = running
    c = target.controller
    link = c._link
    entered, finish = asyncio.Event(), asyncio.Event()

    async def stop(char):
        if char.handle == 2:
            entered.set()
            await finish.wait()

    client.stop_notify.side_effect = stop
    task = asyncio.create_task(c.stop_notify())
    await entered.wait()
    task.cancel()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert c._link is link
    assert {call.args[0].handle for call in client.stop_notify.call_args_list} == {2}
    await c.start_notify()
    assert client.start_notify.call_count == 4
    client.stop_notify.side_effect = None


async def test_rename_wire_preserved_and_debug_and_bundle_trace_redacted(hass, running, caplog):
    import logging
    from unittest.mock import patch

    from custom_components.adjustable_bed.ble_diagnostics import (
        BLEDiagnosticRunner,
        DiagnosticReport,
    )
    from custom_components.adjustable_bed.support_bundle import generate_support_bundle

    e, target, client = running
    name = "PrivateBedName"
    frame = app.rename(name)
    with caplog.at_level(logging.DEBUG, logger="custom_components.adjustable_bed"):
        await target.async_execute_controller_command(lambda ctrl: ctrl.rename_device(name))
        await target.async_execute_controller_command(lambda ctrl: ctrl.preset_flat())
    assert written(client) == [frame, FRAMES[0x08000000]]
    assert name not in caplog.text and name.encode().hex() not in caplog.text
    assert frame.hex() not in caplog.text
    assert "**REDACTED**" in caplog.text
    trace = target.command_trace[-2:]
    assert trace[0]["payload"] == {"redacted": True, "length": 18, "command": "rename"}
    assert trace[0]["characteristic_handle"] == 3
    assert trace[1]["payload"]["hex"] == FRAMES[0x08000000].hex()
    capture = DiagnosticReport(
        metadata={"version": "2.0"},
        device={"address": ADDRESS},
        advertisement={},
        advertisements_by_source=[],
        detection={"bed_type": "dunlopillo", "supported_match": True},
        gatt_services=[],
        gatt_summary={"available": False, "service_count": 0},
        device_information={},
        notifications=[],
        notification_summary={"total_notifications": 0},
        adapter_details={},
        connection_history={},
        connection_attempt_details=[],
        command_trace=trace,
        errors=[],
    )
    with (
        patch.object(BLEDiagnosticRunner, "run_diagnostics", new=AsyncMock(return_value=capture)),
        patch(
            "custom_components.adjustable_bed.support_bundle.bluetooth.async_current_scanners",
            return_value=[],
        ),
    ):
        bundle = await generate_support_bundle(
            hass,
            address=ADDRESS,
            capture_duration=0,
            include_logs=False,
            coordinator=target,
            entry=e,
        )
    assert bundle["command_trace"] == trace
    rendered = json.dumps(bundle)
    assert name not in rendered and name.encode().hex() not in rendered
    assert frame.hex() not in rendered


@pytest.mark.parametrize("missing", (app.WRITE_UUID, app.NOTIFY_UUID))
async def test_both_gatt_roles_remain_mandatory(running, missing):
    _, target, client = running
    client.services = [
        SimpleNamespace(
            uuid=s.uuid,
            characteristics=[char for char in s.characteristics if char.uuid != missing],
        )
        for s in client.services
    ]
    with pytest.raises(BedNotConnectedError):
        await target.controller.async_discover_capabilities()


async def test_subscribe_cancellation_can_retry_with_new_callback_identity(running):
    _, target, client = running
    c = target.controller
    await c.stop_notify()
    callbacks = []

    async def cancelled(char, callback):
        callbacks.append((char, callback))
        raise asyncio.CancelledError

    client.start_notify.side_effect = cancelled
    with pytest.raises(asyncio.CancelledError):
        await c.start_notify()
    client.start_notify.side_effect = None
    await c.start_notify()
    c.forward_controller_state_updates = updates = MagicMock()
    data = bytearray(16)
    data[14] = 1
    char, callback = callbacks[0]
    callback(char, data)
    updates.assert_not_called()
    char, callback = client.start_notify.call_args_list[-2].args
    callback(char, data)
    assert updates.call_args.args == (TIMER(10),)


async def test_real_esphome_timeout_is_optional_on_live_binding(running):
    from aioesphomeapi import APIVersion, DeviceInfo
    from aioesphomeapi.core import TimeoutAPIError
    from bleak.backends.device import BLEDevice
    from bleak_esphome.backend.client import ESPHomeClient, ESPHomeClientData
    from bleak_esphome.backend.device import ESPHomeBluetoothDevice

    _, target, client = running
    c = target.controller
    await c.stop_notify()
    proxy_api = MagicMock()
    proxy_api.bluetooth_gatt_start_notify = AsyncMock(
        side_effect=TimeoutAPIError("notify timed out")
    )
    backend = ESPHomeClient(
        BLEDevice(ADDRESS, "Dunlopillo", {"source": "test-proxy", "address_type": 0}),
        client_data=ESPHomeClientData(
            bluetooth_device=ESPHomeBluetoothDevice("test-proxy", "00:00:00:00:00:01"),
            client=proxy_api,
            device_info=DeviceInfo(),
            api_version=APIVersion(1, 10),
            title="test proxy",
            scanner=None,
        ),
    )
    backend._is_connected = True
    client.start_notify.side_effect = backend.start_notify
    try:
        await c.start_notify()
        assert proxy_api.bluetooth_gatt_start_notify.await_count == 2
        assert backend.is_connected and c._link is not None
        await c.preset_flat()
        assert written(client) == [FRAMES[0x08000000]]
    finally:
        client.start_notify.side_effect = None
        backend._is_connected = False


@pytest.mark.parametrize("mode", ("timeout", "cancel", "pairing_deadline"))
async def test_real_bluez_stalled_stop_is_bounded_and_binding_can_restore(running, mode):
    from bleak.backends.bluezdbus.client import BleakClientBlueZDBus
    from dbus_fast import Message, MessageType

    from custom_components.adjustable_bed.beds.keeson import dunlopillo as bed

    _, target, client = running
    c = target.controller
    await c.stop_notify()
    link = c._link
    for char in link.notifies:
        char.obj = (f"/org/bluez/hci0/dev_test/service0001/char{char.handle:04d}", {})
    backend = BleakClientBlueZDBus(ADDRESS, bluez={}, timeout=10)
    backend._is_connected = True
    stall = True
    cancelled = []

    async def bus_call(message):
        if message.member == "StopNotify" and stall:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.append(message.path)
                raise
        return Message(message_type=MessageType.METHOD_RETURN, reply_serial=1)

    backend._bus = MagicMock()
    backend._bus.call = AsyncMock(side_effect=bus_call)

    async def subscribe(char, callback):
        await backend.start_notify(
            char, lambda data: callback(char, data), bluez={"use_start_notify": True}
        )

    client.start_notify.side_effect = subscribe
    client.stop_notify.side_effect = backend.stop_notify
    try:
        await c.start_notify()
        old_callbacks = list(backend._notification_callbacks.values())
        c.forward_controller_state_updates = updates = MagicMock()
        with virtual_clock() as clock:
            started = clock.now
            if mode in ("cancel", "pairing_deadline"):
                with pytest.raises(TimeoutError):
                    async with asyncio.timeout(0.02):
                        if mode == "pairing_deadline":
                            await target.async_release_for_pairing_transfer()
                        else:
                            await c.stop_notify()
            else:
                await c.stop_notify()
            elapsed = clock.now - started
        if mode == "pairing_deadline":
            # The coordinator also restores the retained session within its own
            # five-second recovery window, then releases the connection lane.
            assert elapsed <= 5.02
            assert not target._pairing_transfer_active
            async with target.async_connection_operation_guard():
                pass
        else:
            assert elapsed == pytest.approx(
                0.02 if mode == "cancel" else bed._NOTIFY_CLEANUP_TIMEOUT
            )
        assert cancelled
        assert c._link is link
        updates.reset_mock()
        payload = bytearray(16)
        payload[14] = 2
        for callback in old_callbacks:
            callback(payload)
        updates.assert_not_called()
        stall = False
        await c.start_notify()
        for callback in old_callbacks:
            callback(payload)
        updates.assert_not_called()
        for callback in backend._notification_callbacks.values():
            callback(payload)
        assert updates.call_count == 2
        await c.preset_flat()
        assert written(client) == [FRAMES[0x08000000]]
    finally:
        stall = False
        client.start_notify.side_effect = None
        client.stop_notify.side_effect = None
        backend._is_connected = False


async def test_real_bluez_rename_debug_is_sanitized_by_support_log_buffer(hass, running, caplog):
    import logging

    from bleak.backends.bluezdbus.client import BleakClientBlueZDBus
    from dbus_fast import Message, MessageType

    from custom_components.adjustable_bed.support_logs import async_setup_support_logs

    _, target, client = running
    buffer = async_setup_support_logs(hass)
    char = target.controller._link.write
    char.obj = ("/org/bluez/hci0/dev_test/service0001/char0003", {})
    backend = BleakClientBlueZDBus(ADDRESS, bluez={}, timeout=10)
    backend._is_connected = True
    backend._bus = MagicMock()
    backend._bus.call = AsyncMock(
        return_value=Message(message_type=MessageType.METHOD_RETURN, reply_serial=1)
    )
    client.write_gatt_char.side_effect = backend.write_gatt_char
    name = "PrivateBedName"
    frame = app.rename(name)
    try:
        with caplog.at_level(logging.DEBUG, logger="bleak.backends.bluezdbus.client"):
            await target.controller.rename_device(name)
        message = backend._bus.call.call_args.args[0]
        assert message.member == "WriteValue" and message.body[0] == frame
        logs = [
            row for row in buffer.snapshot() if row["name"] == "bleak.backends.bluezdbus.client"
        ]
        assert logs
        assert "**REDACTED**" in logs[-1]["message"]
        assert name not in json.dumps(logs) and name.encode().hex() not in json.dumps(logs)
        assert target.command_trace[-1]["payload"] == {
            "redacted": True,
            "length": 18,
            "command": "rename",
        }
    finally:
        client.write_gatt_char.side_effect = None
        backend._is_connected = False
