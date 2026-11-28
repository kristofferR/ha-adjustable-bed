"""RÖWA literal proof, captured-session delivery and real HA action coverage."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.roewa.controller import MEMORY_STORE, RoewaController
from custom_components.adjustable_bed.codec import okin_nframe as codec
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import detect_bed_type, detect_new_bed
from custom_components.adjustable_bed.errors import BedNotConnectedError
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.profile_recommendations import recommend_profile
from custom_components.adjustable_bed.profiles import roewa as app
from custom_components.adjustable_bed.runtime_data import entry_runtime
from custom_components.adjustable_bed.setup_questions import setup_profile
from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON
from tests.hold_lease_wire import virtual_clock

ROWS = json.loads((Path(__file__).parent / "fixtures/roewa/vectors.json").read_text())["vectors"]
ACTIONS = (
    "flat",
    "light_toggle",
    "head_up",
    "head_down",
    "back_up",
    "back_down",
    "legs_up",
    "legs_down",
    "feet_up",
    "feet_down",
    "memory_store",
    "memory_1",
    "memory_2",
    "memory_3",
    "memory_4",
)


@dataclass(eq=False)
class Char:
    uuid: str
    properties: list[str]
    handle: int
    descriptors: list[object]


def client():
    specs = (
        (app.WRITE_UUID, ["write"]),
        (app.FEEDBACK_UUID, ["read", "notify"]),
        (app.NAME_UUID, ["write"]),
        (app.FIRMWARE_UUID, ["read"]),
        (app.MODEL_UUID, ["read"]),
    )
    chars = [
        Char(uuid=u, properties=p, handle=n, descriptors=[]) for n, (u, p) in enumerate(specs, 1)
    ]
    return SimpleNamespace(
        services=[SimpleNamespace(uuid="irrelevant-service", characteristics=chars)],
        is_connected=True,
        write_gatt_char=AsyncMock(),
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
        read_gatt_char=AsyncMock(return_value=b"1.0"),
    )


async def connected(layout=app.DEFAULT_LAYOUT, hass=None):
    coordinator = MagicMock(
        client=client(), name="RÖWA", motor_pulse_count=1, cancel_command=asyncio.Event()
    )
    if hass is not None:
        coordinator.hass = hass
    coordinator.controller_state = {}
    c = RoewaController(coordinator, layout)
    coordinator.controller = c
    await c.async_discover_capabilities()
    session = SimpleNamespace(is_current=lambda: True, store_device_info=MagicMock())
    await c.async_on_connect(session)
    return c, coordinator


def written(coordinator):
    return [bytes(call.args[1]) for call in coordinator.client.write_gatt_char.call_args_list]


def callback(coordinator):
    return coordinator.client.start_notify.call_args.args[1]


@pytest.mark.parametrize("row", ROWS, ids=lambda row: row["id"])
def test_all_frozen_literals_match_existing_codec(row):
    index = int(row["id"][1:])
    actual = (
        codec.frame(app.PROFILES["remote4Drive"].keys[ACTIONS[index]])
        if index < 15
        else app.INITIALIZE
        if index == 15
        else app.rename_frame(row["inputs"]["name"])
    )
    assert actual == bytes.fromhex(row["expected_bytes"])


def test_unicode_rename_and_feedback_bounds():
    assert app.rename_frame("😀") == bytes.fromhex("0204f09f9880")
    frame = bytes.fromhex("ff0b0003000000030000")
    assert all(codec.parse_masked_feedback(frame[:n]) is None for n in range(10))
    assert codec.parse_masked_feedback(frame) == 0x30000
    assert codec.parse_masked_feedback(frame + b"anything") == 0x30000
    assert codec.parse_masked_feedback(bytes.fromhex("ff0b0003000000000000")) == 0
    assert codec.parse_masked_feedback(b"\x00\x0a" + frame[2:]) is None


@pytest.mark.parametrize("layout", app.PROFILES)
async def test_entry_bound_layout_factory_and_quiet_position_census(layout, hass):
    coordinator = MagicMock()
    coordinator.hass = hass
    coordinator.entry.data = {"bed_type": "roewa", "protocol_variant": layout}
    c = await create_controller(coordinator, "roewa", layout, None)
    assert isinstance(c, RoewaController)
    assert c.profile is app.PROFILES[layout]
    assert tuple(s.key for s in c.motor_control_specs) == c.profile.axes
    assert len(c.held_control_options) == len(c.profile.axes) * 2 + 5
    assert c.memory_slot_count == 4
    assert not c.supports_position_feedback
    assert not c.position_number_specs
    assert not c.controller_number_specs
    assert not c.supports_preset_zero_g
    assert not c.execution.concurrent
    assert not c.supports_single_address_pairing
    assert resolve_profile_id(coordinator.entry.data) == f"roewa:{layout}"
    profile = setup_profile("roewa")
    assert profile is not None
    assert profile.questions[0].choices == app.LAYOUTS


async def test_setup_awaits_identity_subscribe_initialize_before_commands():
    c, coordinator = await connected()
    assert written(coordinator) == [app.INITIALIZE]
    assert [call.args[0].uuid for call in coordinator.client.read_gatt_char.call_args_list] == [
        app.FIRMWARE_UUID,
        app.MODEL_UUID,
    ]
    await c.move_head_stop()
    assert written(coordinator) == [app.INITIALIZE]
    coordinator.client.write_gatt_char.reset_mock()
    with virtual_clock():
        await c.move_back_up()
        await c.program_memory(4)
        await c.lights_toggle()
        await c.rename_device("AB")
    assert written(coordinator) == [
        codec.frame(4),
        codec.frame(0x10000),
        codec.frame(0x8000),
        codec.frame(0x20000),
        app.rename_frame("AB"),
    ]
    assert coordinator.client.write_gatt_char.call_args.args[0].uuid == app.NAME_UUID
    assert all(
        call.kwargs["response"] for call in coordinator.client.write_gatt_char.call_args_list
    )


@pytest.mark.parametrize(
    "problem",
    [
        "missing_write",
        "no_response_only",
        "missing_feedback",
        "no_subscription",
        "missing_model",
        "empty_identity",
    ],
)
async def test_setup_failure_cannot_admit_control(problem):
    c, coordinator = await connected()
    c.on_disconnect()
    coordinator.client = client()
    chars = coordinator.client.services[0].characteristics
    if problem.startswith("missing_"):
        uuid = {
            "missing_write": app.WRITE_UUID,
            "missing_feedback": app.FEEDBACK_UUID,
            "missing_model": app.MODEL_UUID,
        }[problem]
        chars[:] = [char for char in chars if char.uuid != uuid]
    elif problem == "no_response_only":
        chars[0].properties = ["write-without-response"]
    elif problem == "no_subscription":
        chars[1].properties = ["read"]
    else:
        coordinator.client.read_gatt_char.return_value = b""
    with pytest.raises(BedNotConnectedError):
        await c.async_discover_capabilities()
        await c.async_on_connect(
            SimpleNamespace(is_current=lambda: True, store_device_info=lambda *_: None)
        )
    with pytest.raises(BedNotConnectedError):
        await c.move_back_up()
    assert not written(coordinator)


async def test_feedback_highlight_never_changes_slot_frames_or_positions():
    c, coordinator = await connected()
    coordinator.handle_controller_state_updates.reset_mock()
    callback(coordinator)(None, bytearray.fromhex("990b0003000000030000"))
    updates = coordinator.handle_controller_state_updates.call_args.args
    assert updates == (UNDER_BED_LIGHTS_ON(True), MEMORY_STORE(True))
    with virtual_clock():
        await c.preset_memory(1)
    assert written(coordinator)[-1] == codec.frame(0x1000)
    assert not c.supports_position_feedback
    old_callback = callback(coordinator)
    c.on_disconnect()
    coordinator.handle_controller_state_updates.reset_mock()
    old_callback(None, bytearray.fromhex("990b0003000000030000"))
    coordinator.handle_controller_state_updates.assert_not_called()
    assert c._firmware is None


@pytest.mark.parametrize("ending", ["release", "cancel", "disconnect", "replace", "task_cancel"])
async def test_hold_cannot_escape_its_session_or_release(ending):
    c, coordinator = await connected("remote4Drive")
    old = coordinator.client
    old.write_gatt_char.reset_mock()
    with virtual_clock():
        task = asyncio.create_task(c.hold_control("head_up", 1000))
        await asyncio.sleep(0.17)
        count = old.write_gatt_char.await_count
        if ending == "release":
            await c.stop_all()
        elif ending == "cancel":
            coordinator.cancel_command.set()
        elif ending == "disconnect":
            old.is_connected = False
            c.on_disconnect()
        elif ending == "replace":
            c.on_disconnect()
            coordinator.client = client()
            await c.async_discover_capabilities()
            await c.async_on_connect(
                SimpleNamespace(is_current=lambda: True, store_device_info=lambda *_: None)
            )
        else:
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert old.write_gatt_char.await_count == count
    assert all(bytes(call.args[1]) == codec.frame(1) for call in old.write_gatt_char.call_args_list)
    if ending == "replace":
        assert written(coordinator) == [app.INITIALIZE]


async def test_settled_write_delay_and_queued_deadline_do_not_burst():
    c, coordinator = await connected()
    sent = []
    with virtual_clock():
        loop = asyncio.get_running_loop()
        start = loop.time()

        async def write(*args, **kwargs):
            sent.append(round((loop.time() - start) * 1000))
            await asyncio.sleep(0.03)

        coordinator.client.write_gatt_char.side_effect = write
        await c.hold_control("back_up", 300)
    assert sent == [0, 110, 220]
    coordinator.client.write_gatt_char.reset_mock()
    await c._ble_lock.acquire()
    with virtual_clock():
        task = asyncio.create_task(c.hold_control("back_up", 100))
        await asyncio.sleep(0.2)
        c._ble_lock.release()
        await task
    assert not written(coordinator)


@pytest.mark.parametrize(
    "control,duration",
    [("light_toggle", 80), ("memory_store", 80), ("head_up", 80), ("flat", 0), ("flat", True)],
)
async def test_invalid_hold_is_translated_and_sends_nothing(control, duration):
    c, coordinator = await connected()
    coordinator.client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError):
        await c.hold_control(control, duration)
    assert not written(coordinator)


def advertisement(name="Unknown", services=(app.SERVICE_UUID,)):
    info = MagicMock(spec=BluetoothServiceInfoBleak)
    info.name, info.address = name, "AA:BB:CC:DD:EE:FF"
    info.service_uuids, info.manufacturer_data = list(services), {}
    info.advertisement = SimpleNamespace(local_name=name)
    return info


def test_shared_discovery_is_an_optional_app_choice_and_never_recommends_switching():
    info = advertisement()
    result = detect_new_bed(info)
    assert "roewa" in {result.bed_type, *(result.ambiguous_types or ())}
    flow = AdjustableBedConfigFlow()
    assert flow._prepare_disambiguation(result)
    assert "roewa" in flow._disambiguation_types
    assert detect_bed_type(advertisement(services=[app.INFO_SERVICE_UUID])) is None
    excluded = detect_new_bed(advertisement("keyboard"))
    assert excluded.bed_type is None
    assert "roewa" not in (excluded.ambiguous_types or ())
    assert (
        recommend_profile({"bed_type": "roewa", "protocol_variant": "remote4Drive"}, info, {})
        is None
    )


async def test_disconnected_stop_never_reconnects(hass, mock_config_entry):
    hass.config_entries.async_update_entry(
        mock_config_entry, data={**mock_config_entry.data, const.CONF_BED_TYPE: "roewa"}
    )
    coordinator = AdjustableBedCoordinator(hass, mock_config_entry)
    coordinator.async_ensure_connected = AsyncMock()
    await coordinator.async_stop_command()
    coordinator.async_ensure_connected.assert_not_awaited()


async def test_native_ha_entities_shared_memory_rename_and_card_hold(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    enable_custom_integrations,
):
    mock_bleak_client.services = client().services
    mock_bleak_client.read_gatt_char.side_effect = None
    mock_bleak_client.read_gatt_char.return_value = b"1.0"
    address = "AA:BB:CC:DD:01:49"
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="RÖWA",
        unique_id=address,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "RÖWA",
            const.CONF_BED_TYPE: "roewa",
            const.CONF_PROTOCOL_VARIANT: "remote4Drive",
            const.CONF_MOTOR_COUNT: 2,
            const.CONF_MOTOR_PULSE_COUNT: 1,
            const.CONF_HAS_MASSAGE: False,
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry_runtime(hass, entry.entry_id)
    assert isinstance(coordinator.controller, RoewaController)
    entities = [
        e for e in er.async_get(hass).entities.values() if e.config_entry_id == entry.entry_id
    ]
    by_key = {e.unique_id.removeprefix(address + "_"): e for e in entities}
    assert {e.domain for e in entities} >= {"cover", "button", "binary_sensor"}
    assert any(e.domain == "light" for e in entities)
    assert not any(e.domain == "climate" for e in entities)
    assert by_key["roewa_release"].hidden_by is not None
    assert by_key["roewa_memory_store"].disabled_by is None
    device_id = by_key["roewa_release"].device_id
    mock_bleak_client.write_gatt_char.reset_mock()
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN,
            "hold_control",
            {"device_id": device_id, "control": "head_up", "duration": 0.17},
            blocking=True,
        )
        await hass.services.async_call(
            const.DOMAIN, "save_preset", {"device_id": device_id, "preset": 3}, blocking=True
        )
        await hass.services.async_call(
            const.DOMAIN, "rename", {"device_id": device_id, "name": "AB"}, blocking=True
        )
    frames = [bytes(call.args[1]) for call in mock_bleak_client.write_gatt_char.call_args_list]
    assert frames[:3] == [codec.frame(1)] * 3
    assert frames[3:] == [codec.frame(0x10000), codec.frame(0x4000), app.rename_frame("AB")]
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            const.DOMAIN,
            "hold_control",
            {"device_id": device_id, "control": "memory_store", "duration": 0.17},
            blocking=True,
        )
    mock_bleak_client.write_gatt_char.reset_mock()
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN,
            "hold_control",
            {
                "device_id": device_id,
                "control": "memory_2",
                "duration": 0.4,
                "hold_owner": "roewa-card",
                "hold_generation": 1,
            },
            blocking=True,
        )
        await asyncio.sleep(0.1)
        await hass.services.async_call(
            "button", "press", {"entity_id": by_key["roewa_release"].entity_id}, blocking=True
        )
        count = mock_bleak_client.write_gatt_char.await_count
        await asyncio.sleep(0.5)
    assert mock_bleak_client.write_gatt_char.await_count == count
    assert all(
        bytes(call.args[1]) == codec.frame(0x2000)
        for call in mock_bleak_client.write_gatt_char.call_args_list
    )
    assert count > 0
    assert isinstance(coordinator, AdjustableBedCoordinator)
    prior = coordinator.controller
    await coordinator.async_disconnect(serialize_with_commands=True)
    mock_bleak_client.write_gatt_char.reset_mock()
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN,
            "goto_preset",
            {"device_id": device_id, "preset": 1, "duration": 0.16},
            blocking=True,
        )
        await hass.services.async_call(
            const.DOMAIN,
            "timed_move",
            {"device_id": device_id, "motor": "head", "direction": "up", "duration_ms": 160},
            blocking=True,
        )
    assert coordinator.controller is not prior
    frames = [bytes(call.args[1]) for call in mock_bleak_client.write_gatt_char.call_args_list]
    assert frames == [app.INITIALIZE] + [codec.frame(0x1000)] * 2 + [codec.frame(1)] * 2
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    "row",
    json.loads((Path(__file__).parent / "fixtures/roewa/feedback.json").read_text())["cases"],
    ids=lambda row: row["label"],
)
def test_accepted_feedback_cases(row):
    assert codec.parse_masked_feedback(bytes.fromhex(row["bytes"])) == row["mask"]


async def test_rename_respects_live_att_bound_and_preserves_utf16_modulo_count():
    c, coordinator = await connected()
    coordinator.client.mtu_size = 517
    await c.rename_device("A" * 256)
    assert written(coordinator)[-1] == b"\x00\x04" + b"A" * 256
    c.validate_device_rename("B" * 510)
    for name in ("", "A" * 511, "\ud800"):
        with pytest.raises(ServiceValidationError):
            c.validate_device_rename(name)
    coordinator.client.mtu_size = 23
    with pytest.raises(ServiceValidationError):
        c.validate_device_rename("😀" * 5)


async def test_light_on_off_uses_confirmed_state_and_unknown_is_translated():
    c, coordinator = await connected()
    coordinator.client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError, match="state"):
        await c.lights_on()
    assert not written(coordinator)
    coordinator.controller_state[UNDER_BED_LIGHTS_ON] = False
    with virtual_clock():
        await c.lights_off()
        assert not written(coordinator)
        await c.lights_on()
    assert written(coordinator) == [codec.frame(app.COMMON["light_toggle"])]


async def test_program_cancelled_during_store_latch_never_sends_slot():
    c, coordinator = await connected()
    coordinator.client.write_gatt_char.reset_mock()
    with virtual_clock():
        task = asyncio.create_task(c.program_memory(1))
        await asyncio.sleep(0.1)
        await c.stop_all()
        await task
    assert written(coordinator) == [codec.frame(app.COMMON["memory_store"])]
