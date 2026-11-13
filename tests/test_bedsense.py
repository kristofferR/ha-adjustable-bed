"""BedSense 1.8 accepted artifact vectors and HA command lifecycle."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.app_profiles import hidden_generic_fields, per_side_profile
from custom_components.adjustable_bed.beds.bedsense import (
    CHARACTERISTIC,
    BedSenseController,
    bedsense_layout,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_BEDSENSE,
    CONF_BLE_DEVICE_NAME,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES
from custom_components.adjustable_bed.profiles.ff_frame import BEDSENSE_ACTIONS as ACTIONS
from custom_components.adjustable_bed.validators import VARIANTS_BY_BED_TYPE

VECTORS = json.loads((Path(__file__).parent / "fixtures/bedsense_vectors.json").read_text())
RELEASE = bytes.fromhex("ffffffff0500000000d700")


def make_controller(layout=3, *, name=None):
    co = MagicMock()
    co.address = "AA:BB:CC:DD:EE:FF"
    co.hass.data = {}
    co.cancel_command = asyncio.Event()
    co.motor_pulse_count = 1
    co.motor_pulse_delay_ms = 1
    co.client = MagicMock(is_connected=True)
    char = MagicMock(uuid=CHARACTERISTIC, handle=7, properties=["write", "notify", "read"])
    co.client.services = [MagicMock(characteristics=[char])]
    co.client.write_gatt_char = AsyncMock()
    co.client.start_notify = AsyncMock()
    co.client.stop_notify = AsyncMock()
    co.client.read_gatt_char = AsyncMock(return_value=b"\x00\xaa")
    return BedSenseController(
        co, variant=f"bedsense_{layout}" if layout else "auto", device_name=name
    )


def packets(c):
    return [call.args[1] for call in c.client.write_gatt_char.call_args_list]


@pytest.mark.parametrize("row", VECTORS["commands"], ids=lambda r: r["row"])
async def test_artifact_command_vectors_through_writer(row):
    c = make_controller(row["variants"][0])
    action = ACTIONS[row["key"]]
    assert action.row == row["row"] and action.variants == frozenset(row["variants"])
    await c.execute_action(row["key"])
    expected = [bytes.fromhex(row["hex"])]
    if row["key"].endswith(("_up", "_down")) and not row["key"].startswith("massage_"):
        expected.append(RELEASE)
    assert packets(c) == expected
    assert all(
        call.kwargs == {"response": True} for call in c.client.write_gatt_char.call_args_list
    )


@pytest.mark.parametrize("row", VECTORS["memory"])
def test_all41_memory_predicates(row):
    c = make_controller()
    c._n = row["n"]
    for key, value in row["saved"].items():
        c._saved[int(key[1:])] = value != "red"
    c._parse(bytes.fromhex(row["input"]), "notification")
    assert c._n == (row["n"] if row["next_n"] is None else row["next_n"])
    for key, value in row["saved"].items():
        assert c.persisted_app_state[key.lower()] is (value == "red")


@pytest.mark.parametrize(
    ("name", "layout"),
    [
        ("JQ-D-IQ", 2),
        ("NQ-H", 1),
        ("JQ", 1),
        ("IQ-LQ", 4),
        ("LQ-KQ", 5),
        ("KQ", 6),
        ("KQH", 8),
        ("MQ-S4-2", 7),
        ("UPS", 7),
        ("S4-2-H", 9),
        ("H", 8),
        ("S4H", 3),
        ("jq", 3),
        ("unmatched", 3),
        (None, 3),
    ],
)
def test_case_sensitive_ordered_selection(name, layout):
    assert bedsense_layout(name) == layout
    assert make_controller(0, name=name).layout == layout


@pytest.mark.parametrize(
    ("layout", "axes", "cycle"),
    [
        (
            1,
            {"back", "waist", "back_and_leg", "legs"},
            {"whole_body", "waist", "back_and_leg", "legs"},
        ),
        (2, {"back", "waist", "head", "legs"}, {"whole_body", "waist", "head", "legs"}),
        (3, {"back", "waist", "head", "legs"}, {"default", "waist", "head", "legs"}),
        (4, {"back", "hip", "head", "legs"}, {"whole_body", "hip", "head", "legs"}),
        (5, {"back", "hip", "head", "legs"}, {"whole_body", "hip", "head", "legs"}),
        (6, {"back"}, set()),
        (7, {"back", "legs"}, set()),
        (8, {"back", "rise_and_fall"}, set()),
        (9, {"back", "hip", "lift", "legs"}, set()),
    ],
)
def test_nine_fresh_layouts_expose_only_proven_controls(layout, axes, cycle):
    c = make_controller(layout)
    assert {s.key for s in c.motor_control_specs} == axes
    assert all(s.scheduler_resource == "*" for s in c.motor_control_specs)
    buttons = {s.key.removeprefix("bedsense_") for s in c.controller_button_specs}
    assert {
        k.removeprefix("circulation_") for k in buttons if k.startswith("circulation_")
    } == cycle
    assert {"light_10_min", "light_8_h", "light_10_h", "refresh_memory"} <= buttons
    assert ("lumbar" in buttons) is (layout in (6, 8))
    assert ("music" in buttons) is (layout in (4, 5))
    assert ("rise" in buttons) is (layout == 9)
    assert ("clear_anti_snore" in buttons) is (layout not in (6, 8))
    assert not c.supports_single_address_pairing
    assert not c.supports_position_feedback and not c.position_number_specs
    assert not c.supports_lights and not c.supports_massage  # app-labelled buttons instead
    assert len(c.controller_state_binary_sensor_specs) == 5
    assert len(c.controller_state_sensor_specs) == 8


async def test_factory_and_explicit_app_registration():
    c = make_controller()
    c._coordinator.hass.async_add_import_executor_job = AsyncMock(
        side_effect=lambda func, *args: func(*args)
    )
    result = await create_controller(c._coordinator, BED_TYPE_BEDSENSE, "auto", c.client, "JQ-D")
    assert isinstance(result, BedSenseController) and result.layout == 2
    assert "com.fenmenbielei.bedsense" in BED_TYPE_DISPLAY_NAMES[BED_TYPE_BEDSENSE]
    assert len(VARIANTS_BY_BED_TYPE[BED_TYPE_BEDSENSE]) == 10
    assert {
        CONF_MOTOR_COUNT,
        CONF_HAS_MASSAGE,
        CONF_DISABLE_ANGLE_SENSING,
    } <= hidden_generic_fields(BED_TYPE_BEDSENSE, "auto")
    profile = per_side_profile(BED_TYPE_BEDSENSE, "auto")
    assert profile and CONF_BLE_DEVICE_NAME in profile.keys and profile.variant_owned


@pytest.mark.parametrize(("layout", "group"), [(3, "default"), (6, "68"), (8, "68"), (7, "7")])
async def test_session_duplicate_roles_read_and_five_query_order(layout, group, monkeypatch):
    c = make_controller(layout)
    first = c.client.services[0].characteristics[0]
    last = MagicMock(
        uuid=CHARACTERISTIC, handle=12, properties=["write-without-response", "notify", "read"]
    )
    c.client.services.append(MagicMock(characteristics=[last]))
    sleeps = AsyncMock()
    monkeypatch.setattr("custom_components.adjustable_bed.beds.bedsense.asyncio.sleep", sleeps)
    await c.start_notify()
    assert [call.args[0] for call in c.client.start_notify.call_args_list] == [first, last]
    assert [call.args[0] for call in c.client.read_gatt_char.call_args_list] == [first, last]
    assert packets(c) == [
        bytes.fromhex(
            next(r["hex"] for r in VECTORS["commands"] if r["key"] == f"query_{group}_{slot}")
        )
        for slot in (3, 4, 1, 2, 5)
    ]
    assert [call.args[0] for call in c.client.write_gatt_char.call_args_list] == [last] * 5
    assert all(
        call.kwargs == {"response": False} for call in c.client.write_gatt_char.call_args_list
    )
    assert [call.args[0] for call in sleeps.call_args_list] == [0.2, 1.8, 0.2, 0.2, 0.2, 0.2]
    await c.stop_notify()
    assert c.client.stop_notify.await_count == 2
    assert not c._subscribed


async def test_setup_failure_unsubscribes_and_disconnect_resets_parser(monkeypatch):
    c = make_controller()
    monkeypatch.setattr("custom_components.adjustable_bed.beds.bedsense.asyncio.sleep", AsyncMock())
    c.client.read_gatt_char.side_effect = BleakError("read failed")
    with pytest.raises(BleakError):
        await c.start_notify()
    c.client.stop_notify.assert_awaited_once()
    c._n = 5
    c.on_disconnect()
    assert c._n == 0 and not c._subscribed


async def test_movement_event_and_task_cancellation_always_release():
    c = make_controller()
    c._coordinator.motor_pulse_delay_ms = 60000
    sent = asyncio.Event()
    c.client.write_gatt_char.side_effect = lambda *a, **kw: sent.set()
    task = asyncio.create_task(c.move_back_up())
    await sent.wait()
    c._coordinator.cancel_command.set()
    await task
    assert packets(c) == [bytes.fromhex("ffffffff05000000039701"), RELEASE]
    c._coordinator.cancel_command.clear()
    c.client.write_gatt_char.reset_mock()
    sent.clear()
    task = asyncio.create_task(c.move_back_down())
    await sent.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert packets(c) == [bytes.fromhex("ffffffff0500000004d6c3"), RELEASE]


async def test_failed_write_does_not_publish_success_and_cancel_skips_clicks():
    c = make_controller()
    c.client.write_gatt_char.side_effect = BleakError("write failed")
    with pytest.raises(BleakError):
        await c.program_memory(1)
    assert c.persisted_app_state["m1"] is False
    c.client.write_gatt_char.side_effect = None
    c._coordinator.cancel_command.set()
    await c.execute_action("light_8_h")
    assert "bedsense_light_duration" not in c.protocol_diagnostics


async def test_saved_flags_recall_fallback_and_special_flat():
    c = make_controller()
    with pytest.raises(ValueError, match="Save"):
        await c.preset_memory(1)
    assert packets(c) == []
    await c.preset_tv()
    await c.program_memory(3)
    await c.preset_tv()
    await c.execute_action("clear_tv")
    await c.preset_tv()
    assert packets(c) == [
        bytes.fromhex(s)
        for s in [
            "ffffffff05000000051703",
            "ffffffff05000050052b03",
            "ffffffff05000051052a93",
            "ffffffff0500005f052ef3",
            "ffffffff05000000051703",
        ]
    ]
    for layout in (6, 8):
        special = make_controller(layout)
        await special.preset_flat()
        await special.program_memory(5)
        await special.preset_memory(5)
        assert packets(special) == [
            bytes.fromhex(s)
            for s in ["ffffffff050000f10fd294", "ffffffff050000f00fd304", "ffffffff050000f10fd294"]
        ]


def test_parser_order_exact_matches_unmatched_and_default_m1_gap():
    c = make_controller()
    c._parse(bytes.fromhex("00a500aa"), "notification")
    assert c.persisted_app_state["m3"] and not c.persisted_app_state["m1"]
    c._saved[1] = True
    c._parse(bytes.fromhex("ffffffff050000af0a2af7"), "notification")
    assert not c.persisted_app_state["m1"] and not c.persisted_app_state["m5"]
    c._parse(bytes.fromhex("ffffffff03002800091f0e"), "local_write")
    assert c._n == 10
    c._parse(bytes.fromhex("000a"), "notification")
    assert not c.persisted_app_state["m1"]
    c._n = 14
    c._parse(bytes.fromhex("0009aec0"), "notification")
    assert c._n == 10 and not c.persisted_app_state["m4"]


@pytest.mark.parametrize(
    ("payload", "key", "value"),
    [
        ("0100", "head_bar", 0),
        ("011e", "head_bar", 20),
        ("011f", "head_bar", 40),
        ("0120", "head_bar", 60),
        ("0200", "head_bar", 0),
        ("0221", "head_bar", 20),
        ("0222", "head_bar", 40),
        ("0223", "head_bar", 60),
        ("0324", "wave_bar", 15),
        ("0325", "wave_bar", 30),
        ("0326", "wave_bar", 45),
        ("0327", "wave_bar", 60),
    ],
)
def test_massage_parser_app_bar_vectors(payload, key, value):
    c = make_controller()
    c._notification(MagicMock(), bytearray.fromhex(payload))
    assert c.protocol_diagnostics[f"bedsense_{key}"] == value
    assert "bedsense_foot_bar" not in c.protocol_diagnostics
    c._parse(bytes.fromhex("001c"), "notification")
    assert (
        c.protocol_diagnostics["bedsense_head_bar"]
        == c.protocol_diagnostics["bedsense_wave_bar"]
        == 0
    )


@pytest.mark.parametrize(
    ("payload", "value"),
    [
        ("ffffffff05000000e7974a", "whole_body"),
        ("ffffffff05000500e4c74a", "whole_body"),
        ("ffffffff05000500e4d74b", "hip"),
        ("ffffffff05000500e38688", "head"),
        ("ffffffff05000500e5068a", "legs"),
        ("ffffffff05000500e6468b", "hip"),
        ("ffffffff05000500e8c74f", "back_and_leg"),
    ],
)
def test_circulation_consumer_vectors(payload, value):
    c = make_controller(4)
    c._parse(bytes.fromhex(payload), "notification")
    assert c.protocol_diagnostics["bedsense_circulation"] == value
    if value == "hip":
        other = make_controller(3)
        other._parse(bytes.fromhex(payload), "notification")
        assert other.protocol_diagnostics["bedsense_circulation"] == "waist"


async def test_massage_timer_toggle_steps_and_light_duration_are_local():
    c = make_controller()
    await c.execute_action("massage_timer_20")
    assert c.protocol_diagnostics["bedsense_massage_timer"] == 20
    await c.execute_action("massage_timer_20")
    assert packets(c)[-1].hex() == "ffffffff050000001cd6c9"
    assert c.protocol_diagnostics["bedsense_massage_timer"] == 0
    for zone, bound in (("head", 3), ("foot", 3), ("wave", 4)):
        for _ in range(6):
            await c.execute_action(f"massage_{zone}_up")
        assert c.protocol_diagnostics[f"bedsense_{zone}_steps"] == bound
        for _ in range(6):
            await c.execute_action(f"massage_{zone}_down")
        assert c.protocol_diagnostics[f"bedsense_{zone}_steps"] == 0
    await c.execute_action("light_10_h")
    assert c.protocol_diagnostics["bedsense_light_duration"] == "10 h"
    assert c.protocol_diagnostics["bedsense_state_source"] == "local_write"


def test_memory_persistence_is_per_app_without_cross_device_state():
    c = make_controller()
    c.restore_persisted_app_state({"m1": True})
    restored = make_controller(9)
    restored.restore_persisted_app_state(c.persisted_app_state)
    assert c.persisted_app_state_key == restored.persisted_app_state_key == "bedsense"
    assert restored.persisted_app_state["m1"] is True
    assert make_controller().persisted_app_state["m1"] is False
    with pytest.raises(ValueError):
        c.restore_persisted_app_state({"m1": 1})
    assert c.persisted_app_state["m1"] is True


@pytest.mark.parametrize("retain", [True, False])
async def test_profile_entity_exposure_follows_the_profile(hass, retain):
    from custom_components.adjustable_bed.binary_sensor import _binary_sensor_entities_for
    from custom_components.adjustable_bed.button import _button_entities_for
    from custom_components.adjustable_bed.const import BED_TYPE_DIAGNOSTIC
    from custom_components.adjustable_bed.cover import _cover_entities_for
    from custom_components.adjustable_bed.sensor import _sensor_entities_for
    from tests.conftest import make_controller_mock
    from tests.test_malouf_app_entities import configure_entity_runtime

    c = (
        make_controller(9)
        if retain
        else make_controller_mock(
            motor_control_specs=(),
            controller_button_specs=(),
            controller_state_sensor_specs=(),
            controller_state_binary_sensor_specs=(),
        )
    )
    runtime = configure_entity_runtime(
        hass, c, BED_TYPE_BEDSENSE if retain else BED_TYPE_DIAGNOSTIC
    )
    for key, build in (
        ("hip", _cover_entities_for),
        ("bedsense_rise", _button_entities_for),
        ("bedsense_head_bar", _sensor_entities_for),
        ("bedsense_m1_saved", _binary_sensor_entities_for),
    ):
        entities = build(hass, runtime)
        assert (f"bed_{key}_left" in {e.unique_id for e in entities}) is retain


async def test_other_axis_stop_preempts_held_movement_through_scheduler(hass):
    from unittest.mock import patch

    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.const import CONF_BED_TYPE, DOMAIN
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.cover import _cover_entities_for

    c = make_controller(9)
    client = c.client
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_BED_TYPE: BED_TYPE_BEDSENSE,
            CONF_DISABLE_ANGLE_SENSING: True,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._client = client
    coordinator._controller = c
    coordinator._motor_pulse_count = 100
    c._coordinator = coordinator
    started = asyncio.Event()
    client.write_gatt_char.side_effect = lambda *a, **kw: started.set()
    covers = {
        cover.entity_description.key: cover for cover in _cover_entities_for(hass, coordinator)
    }
    with (
        patch.object(coordinator, "_async_prepare_controller_operation", AsyncMock(return_value=c)),
        patch.object(coordinator, "_async_finish_controller_operation", AsyncMock()),
        patch.object(covers["back"], "async_write_ha_state", MagicMock()),
        patch.object(covers["hip"], "async_write_ha_state", MagicMock()),
    ):
        movement = asyncio.create_task(covers["back"].async_open_cover())
        await started.wait()
        async with asyncio.timeout(2):
            await covers["hip"].async_stop_cover()
            await movement
    assert packets(c)[0].hex() == "ffffffff05000000039701"
    assert packets(c)[1:] and all(p == RELEASE for p in packets(c)[1:])


async def test_offline_factory_uses_stored_raw_name_and_live_address_falls_back():
    c = make_controller()
    c._coordinator.hass.async_add_import_executor_job = AsyncMock(
        side_effect=lambda func, *args: func(*args)
    )
    c._coordinator.entry.data = {CONF_BLE_DEVICE_NAME: "JQ-D"}
    for client, name, expected in (
        (None, "My KQ bed", 2),
        (c.client, "AA:BB:CC:DD:EE:FF", 2),
        (c.client, "IQ", 4),
    ):
        result = await create_controller(c._coordinator, BED_TYPE_BEDSENSE, "auto", client, name)
        assert isinstance(result, BedSenseController) and result.layout == expected
    fixed = await create_controller(c._coordinator, BED_TYPE_BEDSENSE, "bedsense_9", None, "KQ")
    assert isinstance(fixed, BedSenseController) and fixed.layout == 9


async def test_write_completion_retains_local_selection_when_stop_arrives():
    c = make_controller()
    c.client.write_gatt_char.side_effect = lambda *a, **kw: c._coordinator.cancel_command.set()
    await c.execute_action("massage_timer_20")
    assert c.protocol_diagnostics["bedsense_massage_timer"] == 20
    c._coordinator.cancel_command.clear()
    c.client.write_gatt_char.side_effect = None
    await c.execute_action("massage_timer_20")
    assert packets(c)[-1].hex() == "ffffffff050000001cd6c9"


async def test_reconnect_retains_timer_toggle_steps_and_indicators_per_address(hass):
    c = make_controller()
    co = c._coordinator
    co.hass = hass
    co.entry.data = {}
    first = await create_controller(co, BED_TYPE_BEDSENSE, "bedsense_3", co.client)
    assert isinstance(first, BedSenseController)
    await first.execute_action("massage_timer_20")
    await first.execute_action("massage_head_up")
    await first.execute_action("massage_head_up")
    await first.execute_action("light_8_h")
    first.on_disconnect()
    second = await create_controller(co, BED_TYPE_BEDSENSE, "bedsense_3", co.client)
    assert isinstance(second, BedSenseController)
    await second.execute_action("massage_timer_20")
    assert packets(second)[-1].hex() == "ffffffff050000001cd6c9"
    await second.execute_action("massage_head_up")
    assert second.protocol_diagnostics["bedsense_head_steps"] == 3
    assert second.protocol_diagnostics["bedsense_light_duration"] == "8 h"
    co.address = "AA:BB:CC:DD:EE:00"
    other = await create_controller(co, BED_TYPE_BEDSENSE, "bedsense_3", co.client)
    assert isinstance(other, BedSenseController)
    await other.execute_action("massage_timer_20")
    assert packets(other)[-1].hex() == "ffffffff0500000017970e"
    assert "bedsense_head_steps" not in other.protocol_diagnostics


async def test_reconnected_memory_flags_reach_cached_service_preflight(hass):
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.const import CONF_BED_TYPE, DOMAIN
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.services import _validation_controller

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_BED_TYPE: BED_TYPE_BEDSENSE,
            CONF_DISABLE_ANGLE_SENSING: True,
        },
    )
    entry.add_to_hass(hass)
    co = AdjustableBedCoordinator(hass, entry)
    await co.async_prime_offline_controller()
    offline = co.capability_controller
    assert isinstance(offline, BedSenseController)
    with pytest.raises(ValueError, match="Save"):
        offline.validate_memory_recall(1)
    co._client = make_controller().client
    live = await create_controller(co, BED_TYPE_BEDSENSE, "auto", co.client)
    assert isinstance(live, BedSenseController)
    co._controller = live
    await co._async_restore_app_state(live)
    await live.program_memory(1)
    co._controller = None
    co._client.is_connected = False
    preflight = await _validation_controller(co, co, [])
    assert preflight is offline
    preflight.validate_memory_recall(1)
    assert preflight.persisted_app_state["m1"] is True
    # A fresh live controller restores into the same flags, including clears.
    co._client.is_connected = True
    next_live = await create_controller(co, BED_TYPE_BEDSENSE, "auto", co.client)
    assert isinstance(next_live, BedSenseController)
    co._controller = next_live
    await co._async_restore_app_state(next_live)
    await next_live.execute_action("clear_m1")
    co._controller = None
    with pytest.raises(ValueError, match="Save"):
        offline.validate_memory_recall(1)


async def test_movement_write_timeout_propagates_after_release():
    c = make_controller()
    c.client.write_gatt_char.side_effect = [TimeoutError("proxy write timed out"), None]
    with pytest.raises(TimeoutError, match="proxy write timed out"):
        await c.move_back_up()
    assert packets(c) == [bytes.fromhex("ffffffff05000000039701"), RELEASE]
