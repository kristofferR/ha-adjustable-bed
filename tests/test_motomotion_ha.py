"""MotoMotion capabilities, platform controls and services through real HA ownership."""

import asyncio
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.motomotion import MotoMotionController
from custom_components.adjustable_bed.const import CONF_BED_TYPE, CONF_BLE_DEVICE_NAME, DOMAIN
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.motomotion_protocol import binary_command, posture


def runtime(hass, name="SOFA000001A000H", address="AA:BB:CC:DD:EE:13"):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "My chair",
            CONF_BED_TYPE: "motomotion",
            CONF_BLE_DEVICE_NAME: name,
        },
    )
    entry.add_to_hass(hass)
    c = AdjustableBedCoordinator(hass, entry)
    return c


async def test_offline_prime_factory_uses_ble_identity_and_creates_exact_controls(hass):
    c = runtime(hass, "SOFA000005S000M")
    await c.async_prime_offline_controller()
    ctrl = c.capability_controller
    assert isinstance(ctrl, MotoMotionController)
    assert ctrl.profile.name == "SOFA000005S000M"
    assert ctrl.profile.sides and ctrl.profile.massage
    assert "motomotion_main_up" in ctrl.held_control_options
    assert ctrl.movement_commands()["main"] == (32776, 32775, False)
    assert not ctrl.supports_preset_flat
    assert c.client is None
    await c.async_shutdown()


async def test_dynamic_number_select_sensor_use_real_command_serialization(hass, monkeypatch):
    async def wait(self, seconds, cancel):
        return not cancel.is_set()

    monkeypatch.setattr(MotoMotionController, "_wait", wait)
    from custom_components.adjustable_bed.number import AdjustableBedControllerNumber
    from custom_components.adjustable_bed.select import AdjustableBedControllerSelect
    from custom_components.adjustable_bed.sensor import AdjustableBedControllerStateSensor

    c = runtime(hass, "BT2010000")
    await c.async_prime_offline_controller()
    ctrl = c._controller = MotoMotionController(c)
    c._client = MagicMock()
    c._client.is_connected = True
    c._client.write_gatt_char = AsyncMock()
    c._client.stop_notify = AsyncMock()
    c._client.disconnect = AsyncMock()
    char = SimpleNamespace(uuid="ffe1", handle=13)
    ctrl._session = (c._client, char, char)
    volume = AdjustableBedControllerNumber(
        c, next(s for s in ctrl.controller_number_specs if s.key == "motomotion_volume")
    )
    mode = AdjustableBedControllerSelect(c, ctrl.controller_select_specs[0])
    status = AdjustableBedControllerStateSensor(c, ctrl.controller_state_sensor_specs[0])

    async def write(*args, **kwargs):
        assert c._command_lock.locked()

    c._client.write_gatt_char.side_effect = write
    with (
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        await volume.async_set_native_value(17)
        await mode.async_select_option("custom")
    assert c._client.write_gatt_char.await_args_list[0].args[1] == binary_command(9, 17)
    assert volume.native_value == 17 and mode.current_option == "custom"
    assert status.native_value == "ready"
    c._client.is_connected = False
    await c.async_shutdown()


async def test_selected_side_survives_disconnect_and_controller_replacement(hass):
    from custom_components.adjustable_bed.motomotion_protocol import ascii_command
    from custom_components.adjustable_bed.select import AdjustableBedControllerSelect

    c = runtime(hass, "SOFA000001SB00H")
    await c.async_prime_offline_controller()
    ctrl = c._controller = MotoMotionController(c)
    await c._async_restore_app_state(ctrl)
    c._client = MagicMock()
    c._client.is_connected = True
    c._client.stop_notify = AsyncMock()
    c._client.disconnect = AsyncMock(
        side_effect=lambda: setattr(c._client, "is_connected", False)
    )
    side = AdjustableBedControllerSelect(
        c, next(s for s in ctrl.controller_select_specs if s.key == "motomotion_side")
    )
    with (
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        await side.async_select_option("right")
    await c.async_disconnect("idle_timeout")
    assert c.controller is None

    replacement = c._controller = MotoMotionController(c)
    await c._async_restore_app_state(replacement)
    c._client = MagicMock()
    c._client.is_connected = True
    c._client.write_gatt_char = AsyncMock()
    c._client.stop_notify = AsyncMock()
    c._client.disconnect = AsyncMock()
    char = SimpleNamespace(uuid="ffe1", handle=13)
    replacement._session = (c._client, char, char)
    with (
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        await c.async_execute_controller_command(
            lambda controller: controller.async_execute_motomotion_action("motomotion_light_toggle")
        )
    assert side.current_option == "right"
    assert c._client.write_gatt_char.await_args.args[1] == ascii_command(262, 10000)
    c._client.is_connected = False
    await c.async_shutdown()


async def test_public_user_action_validates_all_targets_before_any_write(hass):
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed import motomotion_services as service

    a, b = runtime(hass), runtime(hass, "BT2010000", "AA:BB:CC:DD:EE:14")
    await a.async_prime_offline_controller()
    await b.async_prime_offline_controller()
    service.async_register_motomotion_services(hass)
    with (
        patch.object(
            service, "_resolve_sided_targets", return_value=([(a, "left"), (b, "left")], [])
        ),
        pytest.raises(ServiceValidationError),
    ):
        await hass.services.async_call(
            DOMAIN,
            "motomotion",
            {
                "device_id": ["a", "b"],
                "operation": "save_user",
                "user": "K",
                "dimensions": [170, 100, 55],
            },
            blocking=True,
        )
    assert a.capability_controller.persisted_app_state["users"] == {}
    await a.async_shutdown()
    await b.async_shutdown()


async def test_public_posture_request_and_restore_have_one_physical_owner(hass):
    from custom_components.adjustable_bed import motomotion_services as service

    c = runtime(hass)
    await c.async_prime_offline_controller()
    ctrl = c._controller = MotoMotionController(c)
    await c._async_restore_app_state(ctrl)
    c._client = MagicMock()
    c._client.is_connected = True
    c._client.write_gatt_char = AsyncMock()
    c._client.stop_notify = AsyncMock()
    c._client.disconnect = AsyncMock()
    char = SimpleNamespace(uuid="ffe1", handle=13)
    ctrl._session = (c._client, char, char)
    service.async_register_motomotion_services(hass)
    with (
        patch.object(service, "_resolve_sided_targets", return_value=([(c, "both")], [])),
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        await hass.services.async_call(
            DOMAIN,
            "motomotion",
            {
                "device_id": ["c"],
                "operation": "save_user",
                "user": "K",
                "dimensions": [170, 100, 55],
            },
            blocking=True,
        )
        await hass.services.async_call(
            DOMAIN,
            "motomotion",
            {"device_id": ["c"], "operation": "recall", "user": "K", "posture": "tv"},
            blocking=True,
        )
    assert (
        c._client.write_gatt_char.await_args_list[0].args[1]
        == posture("tv", 170, 100, 55).to_bytes()
    )
    saved = ctrl.persisted_app_state
    replacement = MotoMotionController(c)
    replacement.restore_persisted_app_state(saved)
    assert replacement.persisted_app_state == saved
    assert replacement._position() == posture("upright", 170, 100, 55)
    c._client.is_connected = False
    await c.async_shutdown()


async def test_setup_step_and_options_ownership_use_same_identity_validation(hass):
    from custom_components.adjustable_bed.app_profiles import (
        hidden_generic_fields,
        per_side_profile,
    )
    from custom_components.adjustable_bed.config_flow import (
        AdjustableBedConfigFlow,
        _add_motomotion_schema_fields,
        _name_rule_setup_name,
        _normalize_motomotion_data,
    )

    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._manual_data = {CONF_BED_TYPE: "motomotion", CONF_NAME: "A renamed chair"}
    result = await flow.async_step_motomotion({CONF_BLE_DEVICE_NAME: "MOTO"})
    assert result["type"] == "form" and result["errors"] == {"base": "motomotion_profile"}
    values = {CONF_BED_TYPE: "motomotion", CONF_BLE_DEVICE_NAME: "SOFA000001S000H"}
    _normalize_motomotion_data(values)
    assert values["disable_angle_sensing"] is True and values["has_massage"] is False
    assert _name_rule_setup_name("motomotion", "SOFA000001S000H") == {
        CONF_BLE_DEVICE_NAME: "SOFA000001S000H"
    }
    schema = {}
    _add_motomotion_schema_fields(schema, values)
    assert {marker.schema for marker in schema} == {CONF_BLE_DEVICE_NAME}
    assert CONF_BLE_DEVICE_NAME in per_side_profile("motomotion", None).keys
    assert "has_massage" in hidden_generic_fields("motomotion", None)


def test_scan_hint_does_not_turn_an_incomplete_name_into_a_protocol():
    from custom_components.adjustable_bed.detection import detect_bed_type, detect_bed_type_detailed

    info = MagicMock()
    info.name = "MOTOAMP"
    info.service_uuids = []
    info.manufacturer_data = {}
    info.service_data = {}
    hint = detect_bed_type_detailed(info)
    assert hint.bed_type == "motomotion" and hint.confidence == 0.3
    assert detect_bed_type(info) is None


async def connected_runtime(hass, name):
    c = runtime(hass, name)
    await c.async_prime_offline_controller()
    ctrl = c._controller = MotoMotionController(c)
    await c._async_restore_app_state(ctrl)
    c._client = MagicMock()
    c._client.is_connected = True
    c._client.write_gatt_char = AsyncMock()
    c._client.stop_notify = AsyncMock()
    c._client.disconnect = AsyncMock()
    char = SimpleNamespace(uuid="ffe1", handle=13)
    ctrl._session = (c._client, char, char)
    return c, ctrl


@pytest.fixture
def protocol_clock(monkeypatch):
    from custom_components.adjustable_bed.beds import motomotion as bed

    now = [0.0]

    async def wait(self, seconds, cancel):
        if cancel.is_set():
            return False
        now[0] += seconds
        return True

    original_sleep = bed.asyncio.sleep

    async def sleep(seconds):
        now[0] += seconds
        await original_sleep(0)

    monkeypatch.setattr(bed, "monotonic", lambda: now[0])
    monkeypatch.setattr(bed.MotoMotionController, "_wait", wait)
    monkeypatch.setattr(bed.asyncio, "sleep", sleep)
    return now


@pytest.mark.parametrize(
    ("name", "slot", "recall", "program"),
    [
        ("SOFA000001MC00M", 2, 257, (264,)),
        ("SOFA00000DMC00M", 1, 257, (264,)),
        ("SOFA00000EMC00M", 1, 256, (33050, 263)),
        ("SOFA000006MC00M", 1, 256, (263,)),
        ("SOFA00000GMC00M", 4, 32780, (33053,)),
        ("MOTOASOFA6M000M", 1, None, ()),
    ],
)
async def test_public_memory_buttons_and_actions_send_exact_panel_packets(
    hass,
    name,
    slot,
    recall,
    program,
    protocol_clock,
    mock_bleak_client,
    mock_coordinator_connected,
    enable_custom_integrations,
):
    from homeassistant.helpers import device_registry as dr

    from custom_components.adjustable_bed import button, services
    from custom_components.adjustable_bed.motomotion_protocol import ascii_command

    c, ctrl = await loaded_runtime(hass, name, mock_bleak_client)
    hass.data.setdefault(DOMAIN, {})[c.entry.entry_id] = c
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=c.entry.entry_id, identifiers={(DOMAIN, c.address)}
    )
    entities = []
    await button.async_setup_entry(hass, c.entry, lambda items: entities.extend(items))
    buttons = {
        e.entity_description.key: e for e in entities if isinstance(e, button.AdjustableBedButton)
    }
    assert {key for key in buttons if key.startswith("preset_memory_")} == {
        f"preset_memory_{i}" for i in range(1, ctrl.memory_slot_count + 1)
    }
    assert {key for key in buttons if key.startswith("program_memory_")} == {
        f"program_memory_{i}" for i in range(1, ctrl.memory_slot_count + 1)
    }
    assert (
        buttons[f"preset_memory_{slot}"].extra_state_attributes["held_control"]
        == f"motomotion_memory_{slot}"
    )
    await services.async_register_services(hass)
    with (
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        await hass.services.async_call(
            DOMAIN,
            "goto_preset",
            {"device_id": device.id, "preset": slot, "duration": 0.25},
            blocking=True,
        )
        expected = binary_command(32777) if recall is None else ascii_command(recall)
        assert [x.args[1] for x in c._client.write_gatt_char.await_args_list] == [
            expected,
            expected,
        ]
        c._client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            DOMAIN, "save_preset", {"device_id": device.id, "preset": slot}, blocking=True
        )
        expected_program = (
            [binary_command(33050)] if recall is None else [ascii_command(code) for code in program]
        )
        assert [x.args[1] for x in c._client.write_gatt_char.await_args_list] == expected_program
        c._client.write_gatt_char.reset_mock()
        await buttons[f"program_memory_{slot}"].async_press()
        assert [x.args[1] for x in c._client.write_gatt_char.await_args_list] == expected_program
    c._client.is_connected = False
    await c.async_shutdown()


async def test_panel_a_public_memory_is_not_created_or_admitted(
    hass, protocol_clock, mock_bleak_client, mock_coordinator_connected, enable_custom_integrations
):
    from homeassistant.exceptions import ServiceValidationError
    from homeassistant.helpers import device_registry as dr

    from custom_components.adjustable_bed import button, services

    c, ctrl = await loaded_runtime(hass, "SOFA00000AMC00H", mock_bleak_client)
    hass.data.setdefault(DOMAIN, {})[c.entry.entry_id] = c
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=c.entry.entry_id, identifiers={(DOMAIN, c.address)}
    )
    entities = []
    await button.async_setup_entry(hass, c.entry, lambda items: entities.extend(items))
    assert not any(
        e.entity_description.memory_slot is not None
        for e in entities
        if isinstance(e, button.AdjustableBedButton)
    )
    await services.async_register_services(hass)
    for service in ("goto_preset", "save_preset"):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN, service, {"device_id": device.id, "preset": 1}, blocking=True
            )
    c._client.write_gatt_char.assert_not_awaited()
    c._client.is_connected = False
    await c.async_shutdown()


async def test_single_address_parent_holds_and_stop_fan_out_exact_side_packets(
    hass, protocol_clock
):
    from custom_components.adjustable_bed.motomotion_protocol import ascii_command
    from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator
    from custom_components.adjustable_bed.pairing import build_single_address_pair_entry_data

    c, ctrl = await connected_runtime(hass, "SOFA000001SC00M")
    paired_data = build_single_address_pair_entry_data(c.entry.data, name="Chair pair")
    pair_entry = MockConfigEntry(domain=DOMAIN, data=paired_data)
    parent = SingleAddressPairedCoordinator(hass, pair_entry, c)
    assert not parent._single_native_both

    async def held(controller):
        await controller.hold_control("motomotion_headrest_up", 150)

    with (
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        await parent.async_execute_controller_command(held, side="both")
        assert [x.args[1] for x in c._client.write_gatt_char.await_args_list] == [
            ascii_command(2),
            *([ascii_command(0)] * 3),
            ascii_command(2, 10000),
            *([ascii_command(0, 10000)] * 3),
        ]
        c._client.write_gatt_char.reset_mock()
        await parent.async_stop_command(side="both")
        assert [x.args[1] for x in c._client.write_gatt_char.await_args_list] == [
            *([ascii_command(0)] * 3),
            *([ascii_command(0, 10000)] * 3),
        ]
        c._client.write_gatt_char.reset_mock()
        await parent.async_execute_controller_command(held, side="right")
        assert [x.args[1] for x in c._client.write_gatt_char.await_args_list] == [
            ascii_command(2, 10000),
            *([ascii_command(0, 10000)] * 3),
        ]
    c._client.is_connected = False
    await parent.async_shutdown()


async def test_home_release_button_cancels_held_refresh_without_extra_stop(hass, monkeypatch):
    import asyncio

    from custom_components.adjustable_bed.beds import motomotion as bed
    from custom_components.adjustable_bed.button import ControllerActionButton
    from custom_components.adjustable_bed.motomotion_protocol import ascii_command

    c, ctrl = await connected_runtime(hass, "SOFA000001MC00M")
    started = asyncio.Event()
    waits = [0]

    async def wait(self, seconds, cancel):
        waits[0] += 1
        if waits[0] == 1:
            return True
        await cancel.wait()
        return False

    async def write(char, value, **kwargs):
        started.set()

    monkeypatch.setattr(bed.MotoMotionController, "_wait", wait)
    c._client.write_gatt_char.side_effect = write
    release = ControllerActionButton(
        c, next(s for s in ctrl.controller_button_specs if s.release_only)
    )

    async def hold(controller):
        await controller.hold_control("motomotion_home", 60000)

    with (
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        task = asyncio.create_task(
            c.async_execute_controller_command(hold, read_positions_after_operation=False)
        )
        await started.wait()
        await release.async_press()
        await task
    assert [x.args[1] for x in c._client.write_gatt_char.await_args_list] == [ascii_command(262)]
    c._client.is_connected = False
    await c.async_shutdown()


@pytest.mark.skipif(shutil.which("bun") is None, reason="Cross-runtime card test requires Bun")
@pytest.mark.parametrize(
    ("key", "release_at", "command", "stops"),
    [
        ("motomotion_home", 50, 262, False),
        ("motomotion_home", 99, 262, False),
        ("motomotion_home", 150, 262, False),
        ("motomotion_home", 250, 262, False),
        ("motomotion_headrest_up", 150, 2, True),
        ("preset_memory_1", 150, 256, True),
    ],
)
async def test_card_pointer_to_wire_charges_native_timing_once(
    hass, monkeypatch, key, release_at, command, stops
):
    from custom_components.adjustable_bed import button
    from custom_components.adjustable_bed.beds import motomotion as bed
    from custom_components.adjustable_bed.motomotion_protocol import ascii_command

    c, ctrl = await connected_runtime(hass, "SOFA000001MCE0M")
    if key.startswith("preset_"):
        entity = button.AdjustableBedButton(
            c, next(d for d in button.BUTTON_DESCRIPTIONS if d.key == key)
        )
    else:
        entity = button.ControllerActionButton(
            c, next(s for s in ctrl.controller_button_specs if s.key == key)
        )
    # Run the actual TypeScript state machine with actual HA entity metadata,
    # then replay its service/release times through the real serialized runtime.
    driver = (
        Path(__file__).parents[1]
        / "custom_components/adjustable_bed/frontend/src/fixtures/motomotion-hold-driver.ts"
    )
    script = (
        f"import {{ pointerTrace }} from {json.dumps(str(driver))};\n"
        "console.log(JSON.stringify(pointerTrace(JSON.parse(process.argv[1]), "
        "Number(process.argv[2]))));"
    )
    events = json.loads(
        subprocess.run(
            ["bun", "--eval", script, json.dumps(entity.extra_state_attributes), str(release_at)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    assert [(e["domain"], e["service"]) for e in events] == [
        (DOMAIN, "hold_control"),
        ("button", "press"),
    ]
    assert events[1]["data"] == {"entity_id": "button.release"}
    now = [events[0]["at"] / 1000]
    release_time = events[1]["at"] / 1000
    release_due = asyncio.Event()
    wire = []
    original_sleep = asyncio.sleep

    async def wait(self, seconds, cancel):
        if now[0] + seconds >= release_time:
            now[0] = release_time
            release_due.set()
            await cancel.wait()
            return False
        now[0] += seconds
        return not cancel.is_set()

    async def sleep(seconds):
        now[0] += seconds
        await original_sleep(0)

    async def write(char, value, **kwargs):
        assert c._command_lock.locked()
        wire.append((round(now[0] * 1000), value))

    monkeypatch.setattr(bed, "monotonic", lambda: now[0])
    monkeypatch.setattr(bed.MotoMotionController, "_wait", wait)
    monkeypatch.setattr(bed.asyncio, "sleep", sleep)
    c._client.write_gatt_char.side_effect = write
    release = button.ControllerActionButton(
        c, next(s for s in ctrl.controller_button_specs if s.release_only)
    )

    async def held(controller):
        await controller.hold_control(
            events[0]["data"]["control"], int(events[0]["data"]["duration"] * 1000)
        )

    try:
        with (
            patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
            patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
        ):
            task = asyncio.create_task(
                c.async_execute_controller_command(held, read_positions_after_operation=False)
            )
            await release_due.wait()
            await release.async_press()
            await task
        expected = [(at, ascii_command(command)) for at in range(100, release_at, 100)]
        if stops:
            expected.extend([(release_at + 50, ascii_command(0))] * 3)
        assert wire == expected
        assert [e["at"] for e in events] == [0, release_at]
    finally:
        c._client.is_connected = False
        await c.async_shutdown()


@pytest.mark.parametrize("side_name", [True, False])
async def test_options_single_address_conversion_and_revert_preserve_profile(
    hass, mock_bleak_client, mock_coordinator_connected, enable_custom_integrations, side_name
):
    from homeassistant.data_entry_flow import FlowResultType
    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed.const import CONF_PAIR_MODE, PAIR_MODE_SINGLE_ADDRESS
    from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator
    from custom_components.adjustable_bed.pairing import is_paired

    tx = MagicMock(uuid="0000fff1-0000-1000-8000-00805f9b34fb", handle=13)
    rx = MagicMock(uuid="0000fff2-0000-1000-8000-00805f9b34fb", handle=14)
    service = SimpleNamespace(uuid="0000fff0-0000-1000-8000-00805f9b34fb", characteristics=[tx, rx])
    mock_bleak_client.services.__iter__ = lambda self: iter([service])
    mock_bleak_client.services.__len__ = lambda self: 1
    name = "SOFA000001S000M" if side_name else "SOFA000001M000M"
    original = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:13",
        CONF_NAME: "MotoMotion chair",
        CONF_BED_TYPE: "motomotion",
        CONF_BLE_DEVICE_NAME: name,
        "disable_angle_sensing": True,
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="MotoMotion chair",
        data=original,
        unique_id=original[CONF_ADDRESS],
        version=4,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    options = await hass.config_entries.options.async_init(entry.entry_id)
    assert options["type"] == FlowResultType.MENU
    assert ("pair_sides" in options["menu_options"]) is side_name
    if not side_name:
        from custom_components.adjustable_bed.pairing import build_single_address_pair_entry_data

        with pytest.raises(ValueError, match="does not support"):
            build_single_address_pair_entry_data(entry.data, name="invalid pair")
        assert not is_paired(entry.data)
    else:
        options = await hass.config_entries.options.async_configure(
            options["flow_id"], {"next_step_id": "pair_sides"}
        )
        result = await hass.config_entries.options.async_configure(
            options["flow_id"], {"confirm": True}
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
        assert entry.data[CONF_PAIR_MODE] == PAIR_MODE_SINGLE_ADDRESS
        parent = hass.data[DOMAIN][entry.entry_id]
        assert isinstance(parent, SingleAddressPairedCoordinator) and not parent._single_native_both
        rows = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        assert any(row.unique_id.endswith("_left") for row in rows)
        assert any(row.unique_id.endswith("_right") for row in rows)
        options = await hass.config_entries.options.async_init(entry.entry_id)
        options = await hass.config_entries.options.async_configure(
            options["flow_id"], {"next_step_id": "revert_sides"}
        )
        result = await hass.config_entries.options.async_configure(
            options["flow_id"], {"confirm": True}
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
        assert entry.data == original
        assert not is_paired(entry.data)
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def loaded_runtime(hass, name, client):
    tx = MagicMock(uuid="0000fff1-0000-1000-8000-00805f9b34fb", handle=13)
    rx = MagicMock(uuid="0000fff2-0000-1000-8000-00805f9b34fb", handle=14)
    service = SimpleNamespace(uuid="0000fff0-0000-1000-8000-00805f9b34fb", characteristics=[tx, rx])
    client.services.__iter__ = lambda self: iter([service])
    client.services.__len__ = lambda self: 1
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="MotoMotion chair",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:13",
            CONF_NAME: "MotoMotion chair",
            CONF_BED_TYPE: "motomotion",
            CONF_BLE_DEVICE_NAME: name,
            "disable_angle_sensing": True,
            "disconnect_after_command": False,
        },
        unique_id="AA:BB:CC:DD:EE:13",
        version=4,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = hass.data[DOMAIN][entry.entry_id]
    assert isinstance(c.controller, MotoMotionController)
    return c, c.controller
