"""Accepted AVEK literals, native controls and connection-owned refresh."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.avek import AvekController
from custom_components.adjustable_bed.codec import avek as codec
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import (
    BED_TYPE_DISPLAY_NAMES,
    detect_bed_type,
    detect_bed_type_detailed,
    detect_new_bed,
)
from custom_components.adjustable_bed.errors import BedNotConnectedError
from custom_components.adjustable_bed.profiles.avek import AVEK
from custom_components.adjustable_bed.runtime_data import entry_runtime
from custom_components.adjustable_bed.setup_questions import setup_profile
from tests.hold_lease_wire import virtual_clock

ROWS = json.loads((Path(__file__).parent / "fixtures/avek/vectors.json").read_text())
TX = ROWS[:12]
RX = ROWS[12:]


@dataclass(eq=False)
class Char:
    uuid: str
    properties: list[str]
    handle: int
    descriptors: list[object]


def client(properties=("write",)):
    write = Char(uuid=codec.WRITE_UUID, properties=list(properties), handle=2, descriptors=[])
    notify = Char(uuid=codec.NOTIFY_UUID, properties=["notify"], handle=3, descriptors=[])
    chars = {codec.WRITE_UUID: write, codec.NOTIFY_UUID: notify}
    service = SimpleNamespace(
        uuid=codec.SERVICE_UUID, get_characteristic=chars.get, characteristics=list(chars.values())
    )
    return SimpleNamespace(
        services=[service],
        is_connected=True,
        write_gatt_char=AsyncMock(),
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
    )


async def connected(hass=None, properties=("write",)):
    if hass is None:
        hass = SimpleNamespace(async_create_task=asyncio.create_task)
    coordinator = MagicMock(
        client=client(properties),
        hass=hass,
        cancel_command=asyncio.Event(),
        motor_pulse_count=1,
        name="AVEK",
    )
    controller = AvekController(coordinator)
    coordinator.controller = controller
    controller.restore_persisted_app_state({"app_id": "001122334455"})
    await controller.async_discover_capabilities()
    await controller.start_notify()
    return controller, coordinator


def written(coordinator):
    return [bytes(call.args[1]) for call in coordinator.client.write_gatt_char.call_args_list]


def callback(coordinator):
    return coordinator.client.start_notify.call_args.args[1]


@pytest.mark.parametrize("row", TX, ids=lambda row: row["id"])
def test_frozen_outgoing_literals(row):
    inputs = row["inputs"]
    actual = (
        codec.control(inputs["word"])
        if "word" in inputs
        else codec.identity(bytes.fromhex(inputs["app_id"]))
    )
    assert actual == bytes.fromhex(row["expected_bytes"])


def test_profile_census_and_capabilities():
    assert {a.frame for a in AVEK.actions} == {
        bytes.fromhex(row["expected_bytes"]) for row in TX[:10]
    }
    c = AvekController(MagicMock())
    assert not c.supports_motor_control
    assert not c.supports_preset_flat
    assert not c.memory_slot_count
    assert not c.supports_position_feedback
    assert not c.supports_single_address_pairing
    assert c.execution.hold == "stream"
    assert not c.execution.concurrent
    assert len(c.held_control_options) == 8
    assert not c.controller_state_sensor_specs
    specs = {s.key: s for s in c.controller_button_specs}
    assert set(specs) == {a.key for a in AVEK.actions} | {"avek_release"}
    assert specs["save"].requires_confirmation
    assert specs["save"].hold is None
    assert specs["initial"].hold is None
    assert specs["avek_release"].release_only


@pytest.mark.parametrize("row", RX, ids=lambda row: row["id"])
def test_frozen_incoming_observations(row):
    data = bytes.fromhex(row["expected_bytes"])
    expected = row["expected_parse"]
    if expected["kind"] == "identity_request":
        assert data == codec.IDENTITY_REQUEST
    elif expected["kind"] == "position":
        assert codec.parse_count(data) == codec.Count(expected["motor"], expected["value"])
    else:
        assert codec.parse_count(data) is None


def test_count_parser_is_bounded_and_preserves_mask_and_signed_values():
    valid = bytes.fromhex(ROWS[13]["expected_bytes"])
    assert all(codec.parse_count(valid[:n]) is None for n in range(9))
    for index in (3, 127, 128, 255):
        body = valid[:5] + bytes((index,)) + valid[6:8]
        assert codec.parse_count(body + bytes((sum(body) & 255,))) is None
    for kind in (0, 0xC2, 0xC1, 0x83):
        body = valid[:4] + bytes((kind,)) + valid[5:8]
        assert codec.parse_count(body + bytes((sum(body) & 255,))) is None
    assert codec.parse_count(valid + valid) == codec.Count(0, 10000)
    assert [
        codec.display_level(n) for n in (-1, 9999, 10000, 10065, 10066, 10396, 10462, 32767)
    ] == [0, 0, 0, 0, 1, 6, 6, 6]
    with pytest.raises(ValueError):
        codec.identity(b"too short")


@pytest.mark.parametrize(
    "name,matched",
    [
        ("TBA3", True),
        ("TBA4-01", True),
        ("TBA-AK bed", True),
        ("tba4-01", False),
        ("TBA2", False),
        ("TBA-T0", False),
        ("", False),
    ],
)
def test_name_discovery_is_only_a_case_sensitive_app_candidate(name, matched):
    info = MagicMock(spec=BluetoothServiceInfoBleak)
    info.name, info.address = name, "AA:BB:CC:DD:EE:FF"
    info.service_uuids, info.manufacturer_data = [], {}
    info.advertisement = SimpleNamespace(local_name=name)
    detected = detect_bed_type_detailed(info)
    assert (detected.bed_type == "avek") is matched
    if matched:
        assert detected.confidence == 0.3
        assert detect_bed_type(info) is None
    assert BED_TYPE_DISPLAY_NAMES["avek"] == "AVEK Ergo System"


def test_setup_owns_fixed_panel_fields():
    profile = setup_profile("avek")
    assert profile is not None
    assert not profile.questions
    assert profile.owns["motor_count"] == 2
    assert profile.owns["has_massage"] is False
    assert profile.owns["disable_angle_sensing"] is True
    assert profile.owns["protocol_variant"] == "auto"


async def test_all_native_buttons_reach_their_literal_frames():
    c, coordinator = await connected()
    callback(coordinator)(None, codec.IDENTITY_REQUEST)
    await asyncio.gather(*c._identity_tasks)
    assert written(coordinator) == [bytes.fromhex(TX[10]["expected_bytes"])]
    # The ordinary controls need connection, not optimistic recognition.
    specs = {s.key: s for s in c.controller_button_specs}
    with virtual_clock():
        for action in AVEK.actions:
            coordinator.client.write_gatt_char.reset_mock()
            if action.key == "initial":
                callback(coordinator)(None, bytes.fromhex(ROWS[13]["expected_bytes"]))
                body = bytes.fromhex("b0 06 10 00 c3 01 10 27")
                callback(coordinator)(None, body + bytes((sum(body) & 255,)))
            await specs[action.key].press_fn(c)
            assert written(coordinator) == [action.frame]
            assert coordinator.client.write_gatt_char.call_args.kwargs["response"] is True
    assert c.protocol_diagnostics["raw_counts"] == [10000, 10000, None]


async def test_held_refresh_and_release_emit_no_invented_stop():
    c, coordinator = await connected()
    times = []
    with virtual_clock():
        start = asyncio.get_running_loop().time()

        async def record(*args, **kwargs):
            times.append(round((asyncio.get_running_loop().time() - start) * 1000))

        coordinator.client.write_gatt_char.side_effect = record
        await c.hold_control("shoulder_hard", 270)
        await c.stop_all()
    assert times == [0, 90, 180]
    assert written(coordinator) == [AVEK.action("shoulder_hard").frame] * 3
    assert not c.reconnect_for_explicit_stop


@pytest.mark.parametrize("task_cancel", [False, True])
async def test_cancel_and_task_cancellation_end_refresh(task_cancel):
    c, coordinator = await connected()

    async def cancel(*args, **kwargs):
        coordinator.cancel_command.set()

    # Cancellation is in the caller after a settled write, not its inner task.
    if task_cancel:
        task = asyncio.create_task(c.hold_control("hip_soft", 60000))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        count = len(written(coordinator))
        await c.stop_all()
        assert len(written(coordinator)) == count
    else:
        coordinator.client.write_gatt_char.side_effect = cancel
        await c.hold_control("hip_soft", 60000)
        assert len(written(coordinator)) == 1


async def test_waiting_frame_cannot_outlive_stop_or_deadline():
    for end in ("stop", "deadline"):
        c, coordinator = await connected()
        await c._ble_lock.acquire()
        with virtual_clock():
            task = asyncio.create_task(c.hold_control("a", 100))
            await asyncio.sleep(0)
            if end == "stop":
                c.on_gesture_release()
            else:
                await asyncio.sleep(0.2)
            c._ble_lock.release()
            await task
        assert not written(coordinator)


async def test_old_callbacks_and_writes_cannot_cross_reconnect_or_notify_restart():
    c, coordinator = await connected()
    old_callback = callback(coordinator)
    await c.stop_notify()
    await c.start_notify()
    old_callback(None, codec.IDENTITY_REQUEST)
    assert not c._identity_tasks
    old_callback = callback(coordinator)
    await c._ble_lock.acquire()
    task = asyncio.create_task(c.hold_control("b", 200))
    await asyncio.sleep(0)
    c.on_disconnect()
    coordinator.client = client()
    await c.async_discover_capabilities()
    await c.start_notify()
    old_callback(None, codec.IDENTITY_REQUEST)
    old_callback(None, bytes.fromhex(ROWS[13]["expected_bytes"]))
    c._ble_lock.release()
    with pytest.raises(ConnectionError):
        await task
    assert not written(coordinator)
    assert c.protocol_diagnostics["raw_counts"] == [None] * 3
    assert c.protocol_diagnostics["identity_reply_sent"] is False


async def test_initial_requires_current_identity_and_has_independent_ha_limit():
    c, coordinator = await connected()
    with virtual_clock():
        start = asyncio.get_running_loop().time()
        with pytest.raises(BedNotConnectedError, match="identity exchange"):
            await c.press("initial")
        assert asyncio.get_running_loop().time() - start == AVEK.identity_timeout_s
    callback(coordinator)(None, codec.IDENTITY_REQUEST)
    await asyncio.gather(*c._identity_tasks)
    coordinator.client.write_gatt_char.reset_mock()

    # No count reports: unknown state must not be treated as the app's default endpoint.
    async def lose_recognition(*args, **kwargs):
        # The app can skip its timer cancellation when this flag becomes false.
        c._recognized = False

    coordinator.client.write_gatt_char.side_effect = lose_recognition
    with virtual_clock():
        start = asyncio.get_running_loop().time()
        await c.press("initial")
        assert asyncio.get_running_loop().time() - start == pytest.approx(10)
    assert len(written(coordinator)) == 112
    assert set(written(coordinator)) == {AVEK.action("initial").frame}
    assert c.protocol_diagnostics["identity_reply_sent"] is False


async def test_identity_write_failure_does_not_recognize_the_link():
    c, coordinator = await connected()
    coordinator.client.write_gatt_char.side_effect = BleakError("failed")
    callback(coordinator)(None, codec.IDENTITY_REQUEST)
    await asyncio.gather(*c._identity_tasks)
    assert c.protocol_diagnostics["identity_reply_sent"] is False
    assert c.persisted_app_state == {"app_id": "001122334455"}
    c.on_disconnect()
    assert c.persisted_app_state == {"app_id": "001122334455"}


@pytest.mark.parametrize(
    "properties,response",
    [
        (("write-without-response",), False),
        (("write", "write-without-response"), False),
        (("write",), True),
    ],
)
async def test_live_gatt_property_mode_and_fixed_service_admission(properties, response):
    c, coordinator = await connected(properties=properties)
    await c.write_command(AVEK.action("c").frame)
    assert coordinator.client.write_gatt_char.call_args.kwargs["response"] is response
    coordinator.client.services[0].uuid = "another service"
    with pytest.raises(BedNotConnectedError):
        await c.async_discover_capabilities()


async def test_initial_waits_for_delayed_current_identity_before_starting_its_window():
    c, coordinator = await connected()
    sent = []
    with virtual_clock():
        loop = asyncio.get_running_loop()
        start = loop.time()

        async def write(_char, data, **kwargs):
            sent.append((round((loop.time() - start) * 1000), bytes(data)))
            if bytes(data).startswith(b"\xb1"):
                await asyncio.sleep(0.05)

        async def challenge():
            await asyncio.sleep(0.1)
            callback(coordinator)(None, codec.IDENTITY_REQUEST)

        coordinator.client.write_gatt_char.side_effect = write
        challenge_task = asyncio.create_task(challenge())
        await c.press("initial")
        await challenge_task
        assert loop.time() - start == pytest.approx(10.15)
    assert sent[0] == (100, codec.identity(bytes.fromhex("001122334455")))
    assert sent[1][0] == 150
    assert all(data == AVEK.action("initial").frame for _, data in sent[1:])


@pytest.mark.parametrize("ending", ["cancel", "release", "replace", "task_cancel"])
async def test_identity_wait_cannot_survive_cancellation_or_session_replacement(ending):
    c, coordinator = await connected()
    old_callback = callback(coordinator)
    with virtual_clock():
        task = asyncio.create_task(c.press("initial"))
        await asyncio.sleep(0.1)
        if ending == "replace":
            c.on_disconnect()
            coordinator.client = client()
            await c.async_discover_capabilities()
            await c.start_notify()
            old_callback(None, codec.IDENTITY_REQUEST)
            # Even valid recognition on the replacement session cannot admit the old press.
            callback(coordinator)(None, codec.IDENTITY_REQUEST)
            await asyncio.gather(*c._identity_tasks)
            with pytest.raises(BedNotConnectedError):
                await task
        elif ending == "task_cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        elif ending == "release":
            await c.stop_all()
            await task
        else:
            coordinator.cancel_command.set()
            with pytest.raises(asyncio.CancelledError):
                await task
    assert AVEK.action("initial").frame not in written(coordinator)


async def test_disconnected_standalone_stop_does_not_connect(hass, mock_config_entry):
    hass.config_entries.async_update_entry(
        mock_config_entry,
        data={**mock_config_entry.data, const.CONF_BED_TYPE: "avek"},
    )
    coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
    coordinator.async_ensure_connected = AsyncMock()
    await coordinator.async_stop_command()
    coordinator.async_ensure_connected.assert_not_awaited()
    assert not coordinator.is_connected


async def test_identity_trace_and_debug_are_redacted_without_changing_wire(caplog):
    c, coordinator = await connected()
    caplog.set_level("DEBUG")
    callback(coordinator)(None, codec.IDENTITY_REQUEST)
    await asyncio.gather(*c._identity_tasks)
    reply = codec.identity(bytes.fromhex("001122334455"))
    assert written(coordinator) == [reply]
    assert c._format_command_trace_payload(reply) == {"redacted": True, "length": 10}
    payload = coordinator.record_command_trace.call_args.kwargs["payload"]
    assert payload == {"redacted": True, "length": 10}
    assert "001122334455" not in json.dumps(payload) + caplog.text.lower()
    control = AVEK.action("a").frame
    assert c._format_command_trace_payload(control)["hex"] == control.hex()


@pytest.mark.parametrize(
    "name,uuids,expected,excluded",
    [
        ("TBA4-01", [const.LINAK_CONTROL_SERVICE_UUID], "linak", False),
        ("TBA4 keyboard", [codec.SERVICE_UUID], None, True),
    ],
)
def test_avek_name_never_overrides_strong_service_or_exclusion(name, uuids, expected, excluded):
    info = MagicMock(spec=BluetoothServiceInfoBleak)
    info.name, info.address = name, "AA:BB:CC:DD:EE:FF"
    info.service_uuids, info.manufacturer_data = uuids, {}
    info.advertisement = SimpleNamespace(local_name=name)
    detected = detect_bed_type_detailed(info)
    assert detected.bed_type == expected
    if excluded:
        assert any(signal.startswith("excluded:") for signal in detected.signals)
        assert "avek" not in (detected.ambiguous_types or ())
    else:
        assert detected.confidence >= 0.7
        assert "avek" in detected.ambiguous_types


def test_avek_app_hint_does_not_corroborate_a_shared_jensen_receiver():
    info = MagicMock(spec=BluetoothServiceInfoBleak)
    info.name, info.address = "TBA4-01", "AA:BB:CC:DD:EE:FF"
    info.service_uuids, info.manufacturer_data = [const.JENSEN_SERVICE_UUID], {}
    info.advertisement = SimpleNamespace(local_name=info.name)

    detected = detect_new_bed(info)

    assert detected.bed_type == const.BED_TYPE_JENSEN
    assert detected.confidence == 0.5
    assert "shared_service:no_name_match" in detected.signals
    assert "avek" in detected.ambiguous_types
    assert "app_hint:avek" in detected.signals
    flow = AdjustableBedConfigFlow()
    assert flow._prepare_disambiguation(detected)
    assert flow._disambiguation_types == [const.BED_TYPE_JENSEN, "avek"]


async def test_refresh_interval_starts_at_actual_dispatch_after_lock_contention():
    c, coordinator = await connected()
    sent_at = []
    await c._ble_lock.acquire()
    with virtual_clock():
        loop = asyncio.get_running_loop()
        start = loop.time()

        async def write(*args, **kwargs):
            sent_at.append(round((loop.time() - start) * 1000))

        coordinator.client.write_gatt_char.side_effect = write
        task = asyncio.create_task(c.hold_control("a", 400))
        await asyncio.sleep(0.17)
        c._ble_lock.release()
        await task
    assert sent_at == [170, 260, 350]


@pytest.mark.parametrize(
    "control,duration",
    [("save", 100), ("initial", 100), ("flat", 100), ("a", 0), ("a", True), ("a", 60001)],
)
async def test_invalid_holds_are_rejected_before_transmission(control, duration):
    c, coordinator = await connected()
    with pytest.raises(ServiceValidationError):
        await c.hold_control(control, duration)
    assert not written(coordinator)


async def test_native_ha_entities_and_shared_hold_action(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    enable_custom_integrations,
):
    mock_bleak_client.services = client().services
    address = "AA:BB:CC:DD:01:54"
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="AVEK",
        unique_id=address,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "AVEK",
            const.CONF_BED_TYPE: "avek",
            const.CONF_MOTOR_COUNT: 2,
            const.CONF_MOTOR_PULSE_COUNT: 1,
            const.CONF_HAS_MASSAGE: False,
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_PROTOCOL_VARIANT: "auto",
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry_runtime(hass, entry.entry_id)
    controller = coordinator.controller
    assert isinstance(controller, AvekController)
    registry = er.async_get(hass)
    entities = [e for e in registry.entities.values() if e.config_entry_id == entry.entry_id]
    by_key = {e.unique_id.removeprefix(address + "_"): e for e in entities}
    assert not any(e.domain in {"cover", "number", "light", "climate"} for e in entities)
    assert by_key["save"].disabled_by is not None
    assert by_key["initial"].disabled_by is not None
    assert by_key["a"].disabled_by is None
    assert by_key["shoulder_hard"].disabled_by is None
    assert by_key["avek_release"].disabled_by is None
    assert by_key["avek_release"].hidden_by is not None
    with virtual_clock():
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": by_key["a"].entity_id},
            blocking=True,
        )
    assert bytes(mock_bleak_client.write_gatt_char.call_args.args[1]) == AVEK.action("a").frame
    mock_bleak_client.write_gatt_char.reset_mock()
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN,
            "hold_control",
            {"device_id": by_key["a"].device_id, "control": "hip_hard", "duration": 0.18},
            blocking=True,
        )
    assert [bytes(call.args[1]) for call in mock_bleak_client.write_gatt_char.call_args_list] == [
        AVEK.action("hip_hard").frame
    ] * 2
    await hass.config_entries.async_unload(entry.entry_id)
