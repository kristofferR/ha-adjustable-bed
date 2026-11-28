"""Frozen EasyCtrl contracts through the production codec, factory and HA callers."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.easyctrl import controller as bed
from custom_components.adjustable_bed.codec import cheerssleep as carrier
from custom_components.adjustable_bed.codec import easyctrl as codec
from custom_components.adjustable_bed.const import CONF_PRODUCT_TYPE
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.profiles import easyctrl as app
from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON
from tests.hold_lease_wire import virtual_clock
from tests.test_cheerssleep import entity_runtime, frames
from tests.test_cheerssleep import make as cheers_make

FIXTURES = Path(__file__).parent / "fixtures/easyctrl"
COMMANDS = json.loads((FIXTURES / "commands.json").read_text())
CATALOG = json.loads((FIXTURES / "variant-catalog.json").read_text())
VECTORS = json.loads((FIXTURES / "vectors.json").read_text())


@pytest.fixture(autouse=True)
def monotonic_clock(monkeypatch):
    monkeypatch.setattr(bed, "monotonic", lambda: asyncio.get_running_loop().time())


def make(key=100):
    _, c = cheers_make(45)
    c.client.services[0].get_characteristic(carrier.WRITE).properties = [
        "write-without-response",
        "notify",
    ]
    c.entry.data[CONF_PRODUCT_TYPE] = str(key)
    ctrl = bed.EasyCtrlController(c, app.MODELS[key])
    c.controller = ctrl
    return ctrl, c


def test_original_literals_and_counter_variant_differences():
    count = codec.Counters()
    for row in VECTORS["transmit"][:10]:
        fields = row["inputs"]
        builder = fields["builder"]
        if builder == "query":
            actual = count.query(fields["code"])
        elif builder == "setting":
            actual = count.setting(fields["code"], fields["parameter"])
        else:
            actual = count.control(fields["code"], fields["parameter"], cached=builder == "held")
        assert actual.hex() == row["expected_bytes"]
    count.sequence = 255
    assert count.control(0x315).hex() == VECTORS["transmit"][10]["expected_bytes"]
    count = codec.Counters()
    assert [count.control(code).hex() for code in (0x111, 1, 1, 1)] == [
        r["expected_bytes"] for r in VECTORS["transmit"][11:]
    ]
    # EasyCtrl settings always use serial zero, unlike CheersSleep settings.
    assert count.setting(0x1101, 10) == count.setting(0x1101, 10) == carrier.p1(0, 3, 0x1101, 10)


@pytest.mark.parametrize("row", VECTORS["receive"], ids=lambda r: r["action"])
def test_frozen_notification_dispatch(row):
    expected = row.get("expected_event")
    actual = codec.parse(bytes.fromhex(row["notification_hex"]))
    assert (list(actual) if actual is not None else None) == expected


def test_catalog_membership_both_directions_and_unique_control_keys():
    live = {
        int(row["id"])
        for row in CATALOG
        if row["scope"] in ("DIRECT_BED", "SOFA_BED") and row["disposition"] == "REACHABLE"
    }
    assert set(app.MODELS) == live and len(live) == 37
    assert {int(model) for row in COMMANDS for model in row["models"]} == live
    for model in app.MODELS.values():
        assert len({a.key for a in model.axes}) == len(model.axes)
        expected = set()
        for row in COMMANDS:
            if (
                row["models"] != [str(model.key)]
                or not row["action"].endswith(" up")
                or "order_index" not in row
            ):
                continue
            down = next(x for x in COMMANDS if x["action"] == row["action"][:-3] + " down")
            stop = next(x for x in COMMANDS if x["action"] == row["action"][:-3] + " STOP")
            selector = row["selector"].split()[0] if row["order_index"] else "default"
            expected.add((row["opcode"], down["opcode"], stop["opcode"], selector))
        assert {(a.up, a.down, a.stop, a.selector) for a in model.axes} == expected


@pytest.mark.parametrize("key", app.MODELS)
async def test_all_routes_factory_capabilities_and_command_membership(key):
    ctrl, c = make(key)
    ctrl = await create_controller(c, "easyctrl", "auto", c.client)
    c.controller = ctrl
    assert isinstance(ctrl, bed.EasyCtrlController)
    assert ctrl.profile.key == key
    assert not ctrl.position_number_specs and not ctrl.execution.concurrent
    assert not ctrl.supports_single_address_pairing
    assert ctrl.memory_slot_count == app.MODELS[key].memory
    with virtual_clock():
        await ctrl.async_on_connect(None)
        for spec in ctrl.motor_control_specs:
            await spec.open_fn(ctrl)
            await spec.close_fn(ctrl)
        if ctrl.supports_preset_flat:
            await ctrl.preset_flat()
        for preset in ctrl.profile.presets:
            await ctrl._preset(preset)
        for slot in range(1, ctrl.memory_slot_count + 1):
            await ctrl.preset_memory(slot)
            await ctrl.program_memory(slot)
        for spec in ctrl.controller_button_specs:
            await spec.press_fn(ctrl)
        for spec in ctrl.controller_select_specs:
            for option in spec.options:
                await spec.select_fn(ctrl, option)
        for spec in ctrl.controller_number_specs:
            for value in (spec.native_min_value, spec.native_max_value):
                await spec.set_fn(ctrl, value)
        for spec in ctrl.controller_switch_specs:
            await spec.set_fn(ctrl, True)
            await spec.set_fn(ctrl, False)
        if ctrl.supports_lights:
            await ctrl.lights_on()
            if ctrl.supports_discrete_light_control:
                await ctrl.lights_off()
        if ctrl.profile.rgb:
            await ctrl.set_light_color_with_level((17, 34, 51), 68)
        if ctrl.alarm_capability:
            for enabled in (True, False):
                await ctrl.configure_alarm(
                    AlarmRequest(
                        enabled=enabled,
                        hour=7,
                        minute=30,
                        weekdays=(0, 2, 4),
                        wake_action="backrest",
                        massage=True,
                        reference_time=datetime(2026, 11, 28, 6),
                    )
                )
    observed = {int.from_bytes(bytes.fromhex(frame)[2:4], "little") for frame in frames(c)}
    expected = {row["opcode"] for row in COMMANDS if str(key) in row["models"]}
    assert observed == expected, (key, observed - expected, expected - observed)
    assert all(call.kwargs["response"] is False for call in c.client.write_gatt_char.call_args_list)


@pytest.mark.parametrize("duration", [0, 100, 400, 401, 1000])
async def test_model300_repaired_release_exact_serials_and_offsets(duration):
    ctrl, c = make(300)
    await ctrl.start_notify()
    times = []
    with virtual_clock():
        start = asyncio.get_running_loop().time()
        c.client.write_gatt_char.side_effect = lambda *_a, **_k: times.append(
            round((asyncio.get_running_loop().time() - start) * 1000)
        )
        if duration == 0:
            await ctrl._control(0x111)
            await ctrl._stops(ctrl._live())
        else:
            await ctrl.move_axis("all", False, duration)
    assert frames(c) == [
        "0201110100000000",
        "0301010000000000",
        "0401010000000000",
        "0501010000000000",
    ]
    assert times == [0, duration, duration + 20, duration + 40]


@pytest.mark.parametrize("task_cancel", [False, True])
async def test_cancel_sends_cleanup_with_fresh_event(task_cancel):
    ctrl, c = make(300)
    await ctrl.start_notify()
    task = asyncio.current_task()

    def stop(*_a, **_kw):
        if c.client.write_gatt_char.call_count == 1:
            if task_cancel:
                task.cancel()
            else:
                c.cancel_command.set()

    c.client.write_gatt_char.side_effect = stop
    with virtual_clock():
        if task_cancel:
            with pytest.raises(asyncio.CancelledError):
                await ctrl.move_axis("all", False, 1000)
        else:
            with pytest.raises(asyncio.CancelledError):
                await ctrl.move_axis("all", False, 1000)
    assert frames(c)[-3:] == ["0301010000000000", "0401010000000000", "0501010000000000"]


async def test_disconnect_stale_callback_and_delayed_setting_never_switch_link():
    ctrl, c = make(324)
    await ctrl.start_notify()
    old_callback = c.client.start_notify.call_args.args[1]
    old_callback(None, bytearray.fromhex("0082050301000000"))
    assert c.controller_state[UNDER_BED_LIGHTS_ON] is True
    old_link = ctrl._link

    async def change_link(*_a, **_kw):
        ctrl.on_disconnect()
        await ctrl.start_notify()

    c.client.write_gatt_char.side_effect = change_link
    with virtual_clock(), pytest.raises(ConnectionError):
        await ctrl.save_light()
    assert len(frames(c)) == 1
    await ctrl._stops(old_link)
    old_callback(None, bytearray.fromhex("0082050301000000"))
    assert c.controller_state.get(UNDER_BED_LIGHTS_ON) is None
    assert len(frames(c)) == 1


async def test_ble_failure_cleanup_and_settings_failure_do_not_publish():
    from bleak.exc import BleakError

    ctrl, c = make(100)
    await ctrl.start_notify()
    c.client.write_gatt_char.side_effect = [BleakError("failed"), None, None, None]
    with virtual_clock(), pytest.raises(BleakError):
        await ctrl.move_axis("legs", True, 100)
    assert len(frames(c)) == 4
    c.client.write_gatt_char.side_effect = BleakError("failed")
    with pytest.raises(BleakError):
        await ctrl.lights_on()
    assert c.controller_state.get(UNDER_BED_LIGHTS_ON) is None


def test_alarm_calendar_future_past_and_no_bed_clock():
    now = datetime(2026, 11, 28, 12)
    assert codec.alarm_values(13, 0, (0, 5, 6), now) == (3600, 0b111)
    assert codec.alarm_values(11, 0, (0, 5, 6), now) == (82800, 0b1000011)
    ctrl, _ = make()
    assert not ctrl.supports_clock_sync
    with pytest.raises(ServiceValidationError):
        ctrl.validate_alarm(AlarmRequest(enabled=True, reference_time=now))


async def test_setup_advertisement_and_explicit_model_are_not_interchanged(hass):
    from custom_components.adjustable_bed.setup_questions import setup_profile

    profile = setup_profile("easyctrl")
    assert profile is not None and profile.seed is not None and profile.validate is not None
    info = SimpleNamespace(manufacturer_data={324: b""})
    assert profile.seed(hass, {}, info)[CONF_PRODUCT_TYPE] == "324"
    assert profile.seed(hass, {CONF_PRODUCT_TYPE: "300"}, info)[CONF_PRODUCT_TYPE] == "300"
    assert profile.validate({CONF_PRODUCT_TYPE: "300"}) == {}
    assert profile.validate({CONF_PRODUCT_TYPE: "9"})
    assert profile.validate({})
    assert app.advertised_model({1: b"", 324: b""}) is None
    assert app.advertised_model({324: b""}) == 324


@pytest.mark.parametrize(
    "manufacturer,offered", [({100: b""}, True), ({1: b"", 100: b""}, False), ({1000: b""}, False)]
)
def test_discovery_only_adds_candidate_and_preserves_shared_receiver(manufacturer, offered):
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed

    result = detect_bed_type_detailed(
        SimpleNamespace(
            name="Bed",
            address="AA:BB",
            service_uuids=[carrier.SERVICE],
            manufacturer_data=manufacturer,
            service_data={},
        )
    )
    assert result.bed_type == "remacro"
    assert ("easyctrl" in (result.ambiguous_types or [])) is offered


async def test_native_cover_light_timer_and_card_use_controller_specs(hass):
    from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
    from custom_components.adjustable_bed.light import _light_entities_for
    from custom_components.adjustable_bed.select import (
        MASSAGE_TIMER_DESCRIPTION,
        AdjustableBedMassageTimerSelect,
    )

    ctrl, c = make(100)
    await ctrl.start_notify()
    runtime = entity_runtime(ctrl, c)
    runtime.controller_state = c.controller_state
    spec = next(s for s in ctrl.motor_control_specs if s.key == "legs")
    cover = AdjustableBedCover(runtime, _build_cover_description(spec))
    cover.hass = hass
    cover.async_write_ha_state = MagicMock()
    with virtual_clock():
        await cover.async_open_cover()
        timer = AdjustableBedMassageTimerSelect(runtime, MASSAGE_TIMER_DESCRIPTION, [10, 20, 30])
        timer.hass = hass
        await timer.async_select_option("20 min")
    lights = _light_entities_for(hass, runtime)
    assert len(lights) == 1
    light = lights[0]
    light.hass = hass
    light.async_write_ha_state = MagicMock()
    await light.async_turn_on(rgb_color=(17, 34, 51), brightness=68)
    assert frames(c)[0] == "0201050100000000"
    assert bytes.fromhex(frames(c)[-1])[2:] == bytes.fromhex("010544332211")
    assert runtime.async_execute_controller_command.call_count >= 3
    assert cover.capability_attributes["card_section"] == "motors"
    assert timer.capability_attributes["card_section"] == "massage"


@pytest.mark.parametrize("key", [14, 100, 300, 324, 1091])
async def test_ha_setup_public_actions_entities_and_unload(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    enable_custom_integrations,
    key,
    monkeypatch,
):
    from dataclasses import replace

    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed import const
    from custom_components.adjustable_bed.runtime_data import loaded_runtime
    from custom_components.adjustable_bed.setup_questions import _easyctrl_settings

    _, transport = make(key)
    mock_bleak_client.services = transport.client.services
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    mock_bleak_client.write_gatt_char = AsyncMock()
    monkeypatch.setitem(app.MODELS, key, replace(app.MODELS[key], query_delay_ms=0))
    data = {
        "address": "AA:BB:CC:DD:EE:FF",
        "name": "EasyCtrl",
        "bed_type": "easyctrl",
        "product_type": str(key),
        "disable_angle_sensing": True,
        "connection_mode": "idle",
        "motor_pulse_count": 1,
    }
    data.update(_easyctrl_settings(data))
    entry = MockConfigEntry(domain=const.DOMAIN, version=5, unique_id=data["address"], data=data)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    runtime = loaded_runtime(hass, entry.entry_id)
    assert isinstance(runtime.controller, bed.EasyCtrlController)
    ctrl = runtime.controller
    entities = [
        v for v in er.async_get(hass).entities.values() if v.config_entry_id == entry.entry_id
    ]
    covers = [v for v in entities if v.domain == "cover"]
    assert len(covers) == len(ctrl.profile.axes)
    assert all(hass.states.get(v.entity_id).attributes["card_section"] == "motors" for v in covers)
    device = covers[0].device_id
    with virtual_clock():
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            const.DOMAIN,
            "hold_control",
            {"device_id": device, "control": f"{ctrl.profile.axes[0].key}_down", "duration": 0.1},
            blocking=True,
        )
        writes = [call.args[1] for call in mock_bleak_client.write_gatt_char.call_args_list]
        assert int.from_bytes(writes[0][2:4], "little") == ctrl.profile.axes[0].down
        assert [
            int.from_bytes(frame[2:4], "little")
            for frame in writes[-len(ctrl.profile.release_ms) :]
        ] == [ctrl.profile.axes[0].stop] * len(ctrl.profile.release_ms)
        if ctrl.profile.alarm:
            mock_bleak_client.write_gatt_char.reset_mock()
            await hass.services.async_call(
                const.DOMAIN,
                "set_alarm",
                {
                    "device_id": device,
                    "enabled": True,
                    "time": "07:30",
                    "weekdays": ["monday", "friday"],
                    "wake_action": "backrest",
                    "massage": True,
                },
                blocking=True,
            )
            assert [
                int.from_bytes(call.args[1][2:4], "little")
                for call in mock_bleak_client.write_gatt_char.call_args_list
            ] == [0x410, 0x411]
        lights = [v for v in entities if v.domain == "light"]
        if ctrl.profile.rgb:
            assert len(lights) == 1
            await hass.services.async_call(
                "light",
                "turn_on",
                {"entity_id": lights[0].entity_id, "rgb_color": [17, 34, 51], "brightness": 68},
                blocking=True,
            )
            assert mock_bleak_client.write_gatt_char.call_args.args[1][2:] == bytes.fromhex(
                "010544332211"
            )
        if key == 14:
            target = next(v for v in entities if v.unique_id.endswith("easyctrl_light_on"))
            await hass.services.async_call(
                "button", "press", {"entity_id": target.entity_id}, blocking=True
            )
            assert mock_bleak_client.write_gatt_char.call_args.args[1][2:] == bytes.fromhex(
                "010500000000"
            )
        if ctrl.profile.memory:
            target = next(v for v in entities if v.unique_id.endswith("program_memory_1"))
            assert hass.states.get(target.entity_id).attributes["card_role"] == "save"
            assert "held_control" not in hass.states.get(target.entity_id).attributes
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_app_picker_routes_to_required_easyctrl_model(hass):
    from custom_components.adjustable_bed import const
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES
    from custom_components.adjustable_bed.profile_id import resolve_profile_id
    from tests.form_helpers import finish_new_bed

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._app_after_device = "manual_entry"
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    await flow.async_step_select_app()
    await flow.async_step_select_app({const.CONF_BED_TYPE: BED_TYPE_DISPLAY_NAMES["easyctrl"]})
    result = await flow.async_step_manual_entry({"address": "AA:BB:CC:DD:EE:FF"})
    assert result["step_id"] == "profile_questions"
    result = await flow.async_step_profile_questions({CONF_PRODUCT_TYPE: "300"})
    result = await finish_new_bed(flow, result)
    data = result.get("data", flow._manual_data)
    assert data[CONF_PRODUCT_TYPE] == "300"
    assert resolve_profile_id(data) == "easyctrl"
    assert not data[const.CONF_HAS_MASSAGE]
    assert data[const.CONF_DISABLE_ANGLE_SENSING]


async def test_stream_refresh_absorbs_write_latency_and_stale_write_state_is_ignored():
    ctrl, c = make(100)
    await ctrl.start_notify()
    times = []
    with virtual_clock():
        start = asyncio.get_running_loop().time()

        async def latency(*_a, **_kw):
            times.append(round((asyncio.get_running_loop().time() - start) * 1000))
            await asyncio.sleep(0.007)

        c.client.write_gatt_char.side_effect = latency
        await ctrl.move_axis("legs", True, 300)
    assert times == [0, 100, 200, 300, 320, 340]

    async def disconnect(*_a, **_kw):
        ctrl.on_disconnect()

    c.client.write_gatt_char.side_effect = disconnect
    await ctrl.lights_on()
    assert c.controller_state.get(UNDER_BED_LIGHTS_ON) is None


def test_model_labels_are_searchable_without_selecting_capabilities_from_their_names():
    labels = json.loads((FIXTURES / "model-labels.json").read_text())
    assert {str(k): v for k, v in app.APP_MODEL_NAMES.items()} == labels
    assert all(label in app.CHOICES[key] for key, label in labels.items())
    # The app labels 118 "FourMotor", but its bound panel retains table 2.
    assert app.APP_MODEL_NAMES[118] == "Bed-FourMotor"
    assert app.MODELS[118].motor_count == 3
    from custom_components.adjustable_bed.setup_questions import _easyctrl_settings

    assert _easyctrl_settings({CONF_PRODUCT_TYPE: "118"})["motor_count"] == 3
    assert [(a.up, a.down) for a in app.MODELS[118].axes] == [
        (272, 273),
        (276, 277),
        (257, 258),
        (261, 262),
        (265, 266),
    ]
