"""Askona frozen vectors and native callers, lifecycle and cancellation."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.beds.keeson.askona import TIMER_SECONDS, AskonaController
from custom_components.adjustable_bed.controller_state import ControllerState
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.profile_recommendations import recommend_profile
from custom_components.adjustable_bed.profiles import askona as app
from custom_components.adjustable_bed.profiles.keeson import encode
from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON
from tests.error_helpers import raises_key
from tests.test_detection import _make_service_info

VECTORS = json.loads((Path(__file__).parent / "fixtures/askona/vectors.json").read_text())
MODELS = {
    "ERGOMOTION_633": "633",
    "ERGOMOTION_180_x_200": "180x200",
    "ERGOMOTION_ELEMENT": "element",
}


@pytest.mark.parametrize("row", VECTORS, ids=lambda r: r["id"])
def test_frozen_vectors(row):
    raw = bytes.fromhex(row["expected_bytes"])
    if row["kind"] == "packet":
        payload = row["inputs"]["payload"]
        if row["inputs"]["custom"]:
            assert app.target(payload[1], payload[3]) == raw
        else:
            for profile in app.PROFILES.values():
                assert encode(profile, int.from_bytes(bytes(payload), "little")) == raw
    else:
        selected = MODELS.get(row["inputs"]["selected"])
        state = app.parse_status(raw, selected)
        expected = {key: value for key, value in row["expected_state"].items() if key != "variant"}
        assert asdict(state) == expected


async def bed(model="633", response=True):
    write = SimpleNamespace(
        uuid=app.WRITE_UUID,
        handle=22,
        properties=["write"] if response else ["write-without-response"],
    )
    notify = SimpleNamespace(uuid=app.NOTIFY_UUID, handle=32, properties=["notify"])
    services = MagicMock()
    service_map = {
        app.WRITE_SERVICE: SimpleNamespace(get_characteristic=lambda _: write),
        app.NOTIFY_SERVICE: SimpleNamespace(get_characteristic=lambda _: notify),
    }
    services.get_service.side_effect = service_map.get
    services.get_characteristic.return_value = None
    client = MagicMock(is_connected=True, services=services)
    client.write_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.read_gatt_char = AsyncMock(return_value=b"5.4.3")
    state = ControllerState()
    co = SimpleNamespace(
        client=client,
        address="AA:BB:CC:DD:EE:FF",
        name="Bed",
        motor_count=2,
        motor_pulse_count=10,
        motor_pulse_delay_ms=100,
        cancel_command=asyncio.Event(),
        record_command_trace=MagicMock(),
        controller_state=state,
        handle_controller_state_updates=lambda *updates: state.update(
            (u.key, u.value) for u in updates
        ),
    )
    c = AskonaController(co, model)
    await c.async_discover_capabilities()
    await c.start_notify()
    return c, co, client, state, notify


def report(client, notify, index=20):
    callback = client.start_notify.call_args.args[1]
    callback(notify, bytearray.fromhex(VECTORS[index]["expected_bytes"]))
    return callback


def frames(client):
    return [bytes(call.args[1]).hex() for call in client.write_gatt_char.call_args_list]


@pytest.mark.parametrize("model", app.PROFILES)
async def test_app_actions_have_no_foreign_release(model):
    c, _, client, _, _ = await bed(model)
    await c.preset_flat()
    await c.preset_lounge()
    await c.preset_zero_g()
    await c.preset_tv()
    await c.massage_toggle()
    await c.massage_head_up()
    await c.massage_head_down()
    await c.massage_foot_up()
    await c.massage_foot_down()
    await c.massage_mode_step()
    await c.lights_toggle()
    assert frames(client) == [
        "e5fe170000000005",
        "e5fe1600200000e6",
        "e5fe1600100000f6",
        "e5fe1600400000c6",
        "e5fe160001000005",
        "e5fe1600080000fe",
        "e5fe160000800086",
        "e5fe160004000002",
        "e5fe160000000105",
        "e5fe160002000004",
        "e5fe160000020004",
    ]
    assert c.motor_control_specs == () and c.held_control_options == ()
    assert not c.supports_stop_all and not c.supports_single_address_pairing
    assert not c.supports_memory_presets and not c.supports_memory_programming
    assert bool(c.position_number_specs) == (model != "180x200")


async def test_position_preserves_reported_other_axis_and_native_bounds():
    c, _, client, _, notify = await bed()
    with raises_key("askona_feedback_required"):
        await c.set_motor_position("back", 21)
    report(client, notify)
    await c.set_motor_position("back", 21)
    await c.set_motor_position("legs", 37)
    assert frames(client) == [app.target(21, 44).hex(), app.target(68, 37).hex()]
    for motor, value in (("back", 69), ("legs", 45), ("back", True), ("tilt", 1)):
        with raises_key("askona_target_invalid"):
            await c.set_motor_position(motor, value)
    c180, _, _, _, _ = await bed("180x200")
    with raises_key("askona_movement_unavailable"):
        await c180.set_motor_position("back", 21)


async def test_stale_callbacks_and_reports_cannot_cross_sessions():
    c, co, client, state, notify = await bed()
    old = report(client, notify)
    assert state.get(TIMER_SECONDS) == 46.6
    c.on_disconnect()
    assert state.get(UNDER_BED_LIGHTS_ON) is None
    old(notify, bytearray.fromhex(VECTORS[20]["expected_bytes"]))
    assert state.get(TIMER_SECONDS) is None
    await c.async_discover_capabilities()
    await c.start_notify()
    old(notify, bytearray.fromhex(VECTORS[20]["expected_bytes"]))
    with raises_key("askona_feedback_required"):
        await c.set_motor_position("back", 10)
    co.address = "11:22:33:44:55:66"
    with raises_key("askona_session_changed"):
        await c.lights_toggle()
    client.write_gatt_char.assert_not_awaited()


async def test_subscription_failure_does_not_leave_writable_or_reported_state():
    c, _, client, state, notify = await bed()
    old = report(client, notify)
    c.on_disconnect()
    await c.async_discover_capabilities()
    client.start_notify.side_effect = BleakError("subscription failed")
    with pytest.raises(BleakError):
        await c.lights_toggle()
    old(notify, bytearray.fromhex(VECTORS[20]["expected_bytes"]))
    assert state.get(TIMER_SECONDS) is None
    client.write_gatt_char.assert_not_awaited()


async def test_cancel_and_failure_end_massage_steps_without_release():
    c, co, client, _, notify = await bed()
    report(client, notify)
    sent = asyncio.Event()

    async def sent_frame(*args, **kwargs):
        sent.set()

    client.write_gatt_char.side_effect = sent_frame
    task = asyncio.create_task(c.set_head_massage(5))
    await sent.wait()
    co.cancel_command.set()
    await task
    assert frames(client) == ["e5fe1600080000fe"]
    co.cancel_command.clear()
    client.write_gatt_char.side_effect = BleakError("write failed")
    with pytest.raises(BleakError):
        await c.set_head_massage(5)
    assert len(frames(client)) == 2


async def test_task_cancel_massage_and_version_do_not_retarget():
    c, _, client, _, notify = await bed(response=False)
    report(client, notify)
    sent = asyncio.Event()

    async def write(*args, **kwargs):
        sent.set()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(c.set_head_massage(5))
    await sent.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(frames(client)) == 1
    assert client.write_gatt_char.call_args.kwargs["response"] is False
    client.services.get_characteristic.return_value = SimpleNamespace(
        uuid=app.VERSION_UUID, properties=["read"]
    )
    await c.async_read_device_info(SimpleNamespace(is_current=lambda: True))
    assert c.protocol_diagnostics["software_version"] == "5.4.3"


def test_discovery_and_recommendations_offer_an_app_without_replacing_the_receiver():
    info = _make_service_info("base-i5.12345678", service_uuids=[app.NOTIFY_SERVICE])
    detected = detect_bed_type_detailed(info)
    assert detected.bed_type != "askona"
    assert "askona" in detected.ambiguous_types
    existing = recommend_profile({"bed_type": detected.bed_type}, info, {})
    assert existing is None or existing.suggested != "askona"
    assert recommend_profile({"bed_type": "askona", "protocol_variant": "633"}, info, {}) is None
    for name in ("BASE-i5.12345678", "base-i5.1234567", "base-i5.123456789"):
        assert not app.admitted_name(name)
    assert app.admitted_name("base-i4x12345678")


@pytest.mark.parametrize("model", app.PROFILES)
async def test_native_setup_creates_explicit_profile(hass, model):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._manual_data = {CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_NAME: "Bed", "bed_type": "askona"}
    flow._final_settings_pending = True
    with patch.object(flow, "_verification_possible", return_value=False):
        question = await flow.async_step_profile_questions({"protocol_variant": model})
        assert question["step_id"] == "finish_settings"
        result = await flow.async_step_finish_settings(
            {
                CONF_NAME: "Askona",
                "motor_count": 4,
                "has_massage": False,
                "disable_angle_sensing": True,
            }
        )
    assert result["type"] == "create_entry"
    saved = result["data"]
    assert saved["protocol_variant"] == model
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed import _async_sync_profile_ids

    entry = MockConfigEntry(domain=const.DOMAIN, title="Bed", data=saved, version=5)
    entry.add_to_hass(hass)
    _async_sync_profile_ids(hass, entry)
    saved = entry.data
    assert saved["profile_id"] == f"askona:{model}"
    assert saved["motor_count"] == 2 and saved["has_massage"] is True
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    assert AdjustableBedCoordinator(hass, entry).disable_angle_sensing is False
    assert resolve_profile_id(saved) == saved["profile_id"]


def test_pair_model_belongs_to_each_receiver():
    from custom_components.adjustable_bed.pairing import effective_child_data

    profile = per_side_profile("askona", "633")
    assert profile.variant_owned and "protocol_variant" in profile.keys
    data = {
        "bed_type": "askona",
        "protocol_variant": "633",
        const.CONF_PAIR_CHILDREN: [
            {
                "side": "left",
                "bed_type": "askona",
                "protocol_variant": "633",
                "address": "AA:BB:CC:DD:EE:01",
            },
            {
                "side": "right",
                "bed_type": "askona",
                "protocol_variant": "element",
                "address": "AA:BB:CC:DD:EE:02",
            },
        ],
    }
    right = effective_child_data(data, "right", {"protocol_variant": "180x200"})
    assert right["protocol_variant"] == "element"


async def test_native_position_number_uses_coordinator_command_lane(hass):
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.bed_traits import bed_traits
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.number import (
        AdjustableBedPositionNumber,
        _build_position_description,
    )

    _, _, client, _, notify = await bed()
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Askona",
        version=5,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            "bed_type": "askona",
            "protocol_variant": "633",
            "disable_angle_sensing": False,
        },
    )
    entry.add_to_hass(hass)
    co = AdjustableBedCoordinator(hass, entry)
    co._client = client
    co._position_connection_generation = 1
    c = AskonaController(co, "633")
    c.static_traits = bed_traits("askona", "633")
    co._controller = c
    await c.async_discover_capabilities()
    await c.start_notify(co._handle_position_update)
    report(client, notify)
    entity = AdjustableBedPositionNumber(
        co, _build_position_description(c.position_number_specs[0])
    )
    with patch.object(co, "async_ensure_connected", new=AsyncMock(return_value=True)):
        await entity.async_set_native_value(21)
    assert frames(client) == [app.target(21, 44).hex()]
    assert co._command_scheduler.recent_records[-1].outcome.value == "completed"
    co._cancel_disconnect_timer()


@pytest.mark.parametrize("disconnect_kind", ("cancel", "error", "noop", "notify_retry"))
async def test_retained_connection_restores_subscription_without_trusting_old_feedback(
    hass, disconnect_kind
):
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.bed_traits import bed_traits
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    _, _, client, _, notify = await bed()
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Askona",
        version=5,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            "bed_type": "askona",
            "protocol_variant": "633",
            "disable_angle_sensing": False,
        },
    )
    entry.add_to_hass(hass)
    co = AdjustableBedCoordinator(hass, entry)
    co._client = client
    co._position_connection_generation = 1
    c = AskonaController(co, "633")
    c.static_traits = bed_traits("askona", "633")
    co._controller = c
    await c.async_discover_capabilities()
    await c.start_notify(co._handle_position_update)
    original_link = c._live()
    old_callback = report(client, notify)
    subscriptions_before = client.start_notify.await_count
    co._link_ready = True

    async def disconnect():
        if disconnect_kind == "cancel":
            raise asyncio.CancelledError
        if disconnect_kind == "error":
            raise BleakError("disconnect failed")

    client.disconnect = AsyncMock(side_effect=disconnect)
    if disconnect_kind == "notify_retry":
        client.start_notify.side_effect = [BleakError("restore notification failed"), None]
    try:
        async with co._lock:
            if disconnect_kind == "cancel":
                with pytest.raises(asyncio.CancelledError):
                    await co._async_disconnect_locked()
            else:
                assert await co._async_disconnect_locked() is False
        assert co._client is client and co._controller is c
        if disconnect_kind == "notify_retry":
            assert not co._link_ready
            assert await co.async_ensure_connected(reset_timer=False)
        assert co._link_ready
        assert c._live() is original_link and c._subscribed is original_link
        assert client.start_notify.await_count == subscriptions_before + (
            2 if disconnect_kind == "notify_retry" else 1
        )
        assert c._status is None
        with raises_key("askona_feedback_required"):
            await c.lights_on()
        old_callback(notify, bytearray.fromhex(VECTORS[20]["expected_bytes"]))
        assert c._status is None
        report(client, notify)
        assert c._status is not None
        await co.async_execute_controller_command(lambda ctrl: ctrl.preset_flat())
        assert frames(client)[-1] == app.target(0, 0).hex()
    finally:
        async def close():
            client.is_connected = False

        client.disconnect.side_effect = close
        await co.async_shutdown()


async def test_queued_write_cannot_follow_replacement_client():
    c, co, client, _, _ = await bed()
    replacement = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
    async with c._ble_lock:
        task = asyncio.create_task(c.lights_toggle())
        await asyncio.sleep(0)
        co.client = replacement
    with pytest.raises(ConnectionError):
        await task
    client.write_gatt_char.assert_not_awaited()
    replacement.write_gatt_char.assert_not_awaited()


async def test_head_massage_wrap_and_delta_keep_app_timing():
    from tests.hold_lease_wire import virtual_clock

    c, _, client, _, notify = await bed()
    callback = report(client, notify)
    status = bytearray.fromhex(VECTORS[20]["expected_bytes"])
    status[7] = 6
    callback(notify, status)
    with virtual_clock():
        await c.set_head_massage(0)
    assert frames(client) == ["e5fe1600080000fe"]
    status[7] = 0
    callback(notify, status)
    with virtual_clock():
        await c.set_head_massage(6)
    assert frames(client)[-1] == "e5fe160000800086"
    status[7] = 2
    callback(notify, status)
    with virtual_clock():
        await c.set_head_massage(5)
    assert frames(client)[-3:] == ["e5fe1600080000fe"] * 3


async def test_native_light_uses_report_and_sent_state_without_double_toggle():
    c, _, client, state, notify = await bed()
    with raises_key("askona_feedback_required"):
        await c.lights_on()
    report(client, notify)
    await c.lights_on()
    client.write_gatt_char.assert_not_awaited()
    await c.lights_off()
    assert state.get(UNDER_BED_LIGHTS_ON) is False
    await c.lights_off()
    assert frames(client) == ["e5fe160000020004"]


@pytest.fixture
async def native_askona(hass):
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.bed_traits import bed_traits
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    beds = []

    async def create(model="633"):
        _, _, client, _, notify = await bed(model)
        address = f"AA:BB:CC:DD:EE:{len(beds):02X}"
        entry = MockConfigEntry(
            domain=const.DOMAIN,
            title="Askona",
            version=5,
            data={
                CONF_ADDRESS: address,
                "bed_type": "askona",
                "protocol_variant": model,
                "disable_angle_sensing": False,
            },
        )
        entry.add_to_hass(hass)
        co = AdjustableBedCoordinator(hass, entry)
        co._client = client
        co._position_connection_generation = 1
        controller = AskonaController(co, model)
        controller.static_traits = bed_traits("askona", model)
        co._controller, co._link_ready = controller, True
        await controller.async_discover_capabilities()
        await controller.start_notify(co._handle_position_update)
        report(client, notify)
        co.async_ensure_connected = AsyncMock(return_value=True)
        beds.append((co, client))
        return co, controller, client, notify

    yield create
    for co, client in beds:
        async def disconnect(client=client):
            client.is_connected = False

        client.disconnect = AsyncMock(side_effect=disconnect)
        await co.async_shutdown()


@pytest.mark.parametrize("during_write", ("report", "disconnect"))
async def test_native_light_completion_cannot_override_feedback_or_retirement(
    hass, native_askona, during_write
):
    from custom_components.adjustable_bed.light import LIGHT_DESCRIPTION, AdjustableBedOnOffLight

    co, controller, client, notify = await native_askona()
    entity = AdjustableBedOnOffLight(co, LIGHT_DESCRIPTION)
    entity.hass = hass
    entity.async_write_ha_state = MagicMock()
    remove = co.register_controller_state_callback(entity._handle_controller_state_update)
    entity._handle_controller_state_update(co.controller_state)

    async def write(*_args, **_kwargs):
        if during_write == "report":
            report(client, notify)
        else:
            client.is_connected = False
            co._on_disconnect(client)

    client.write_gatt_char.side_effect = write
    try:
        await entity.async_turn_off()
        assert frames(client) == ["e5fe160000020004"]
        expected = True if during_write == "report" else None
        assert co.controller_state.get(UNDER_BED_LIGHTS_ON) is expected
        if during_write == "report":
            assert controller._status is not None
            assert controller._status.light is True
            assert entity.is_on is True
    finally:
        remove()


@pytest.mark.parametrize(("model", "foot"), (("633", 37), ("element", 30)))
async def test_native_position_service_composes_requested_axes(hass, native_askona, model, foot):
    from custom_components.adjustable_bed import services

    co, _, client, _ = await native_askona(model)
    await services.async_register_services(hass)
    with patch.object(services, "_resolve_sided_targets", return_value=([(co, const.SIDE_BOTH)], [])):
        await hass.services.async_call(
            const.DOMAIN,
            "set_positions",
            {"device_id": ["bed"], "positions": [
                {"motor": "back", "position": 21}, {"motor": "legs", "position": foot}
            ]},
            blocking=True,
        )
    assert frames(client) == [app.target(21, foot).hex()]
    # A target is an instruction, not observed motor feedback.
    assert co.position_data["back"] == 68


@pytest.mark.parametrize(
    ("second_model", "motor", "position"), (("180x200", "back", 21), ("element", "legs", 37))
)
async def test_position_service_checks_every_model_and_range_before_moving(
    hass, native_askona, second_model, motor, position
):
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed import services

    first, _, first_client, _ = await native_askona()
    second, _, second_client, _ = await native_askona(second_model)
    await services.async_register_services(hass)
    targets = [(first, const.SIDE_BOTH), (second, const.SIDE_BOTH)]
    with (
        patch.object(services, "_resolve_sided_targets", return_value=(targets, [])),
        pytest.raises(ServiceValidationError),
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "set_positions",
            {"device_id": ["first", "second"], "positions": [{"motor": motor, "position": position}]},
            blocking=True,
        )
    assert frames(first_client) == []
    assert frames(second_client) == []
