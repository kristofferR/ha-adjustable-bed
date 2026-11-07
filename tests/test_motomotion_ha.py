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
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.motomotion import MotoMotionController
from custom_components.adjustable_bed.codec.motomotion import (
    Position,
    ascii_command,
    binary_command,
)
from custom_components.adjustable_bed.const import CONF_BED_TYPE, CONF_BLE_DEVICE_NAME, DOMAIN
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.motomotion_protocol import posture


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


@pytest.mark.parametrize(
    ("name", "key", "value", "action", "expected"),
    [
        ("SOFA000001SB00H", "side", "right", "light_toggle", ascii_command(262, 10000)),
        *[
            (
                "SOFA000001A000H",
                "posture",
                value,
                "posture_recall",
                posture(value, 170, 100, 55).to_bytes(),
            )
            for value in ("tv", "recline", "lay")
        ],
    ],
)
async def test_selection_survives_disconnect_and_controller_replacement(
    hass, name, key, value, action, expected
):
    from custom_components.adjustable_bed.select import AdjustableBedControllerSelect

    c = runtime(hass, name)
    await c.async_prime_offline_controller()
    ctrl = c._controller = MotoMotionController(c)
    await c._async_restore_app_state(ctrl)
    ctrl.restore_persisted_app_state({"dimensions": {"height": 170, "buttocks": 100, "knee": 55}})
    c._client = MagicMock()
    c._client.is_connected = True
    c._client.stop_notify = AsyncMock()
    c._client.disconnect = AsyncMock(side_effect=lambda: setattr(c._client, "is_connected", False))
    selection = AdjustableBedControllerSelect(
        c, next(s for s in ctrl.controller_select_specs if s.key == "motomotion_" + key)
    )
    with (
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        await selection.async_select_option(value)
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
            lambda controller: controller.async_execute_motomotion_action("motomotion_" + action)
        )
    assert selection.current_option == value
    assert c._client.write_gatt_char.await_args.args[1] == expected
    c._client.is_connected = False
    await c.async_shutdown()


@pytest.mark.parametrize("selected_posture", ["upright", "tv"])
async def test_fine_tune_targets_survive_disconnect_and_controller_replacement(hass, selected_posture):
    from custom_components.adjustable_bed.number import AdjustableBedControllerNumber

    c = runtime(hass)
    await c.async_prime_offline_controller()
    ctrl = c._controller = MotoMotionController(c)
    await c._async_restore_app_state(ctrl)
    ctrl.restore_persisted_app_state(
        {"dimensions": {"height": 170, "buttocks": 100, "knee": 55}, "posture": selected_posture}
    )
    c._client = MagicMock()
    c._client.is_connected = True
    c._client.write_gatt_char = AsyncMock()
    c._client.stop_notify = AsyncMock()
    c._client.disconnect = AsyncMock(side_effect=lambda: setattr(c._client, "is_connected", False))
    char = SimpleNamespace(uuid="ffe1", handle=13)
    ctrl._session = (c._client, char, char)
    sliders = {
        key: AdjustableBedControllerNumber(
            c, next(s for s in ctrl.controller_number_specs if s.key == "motomotion_target_" + key)
        )
        for key in ("head", "back")
    }
    with (
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        await sliders["head"].async_set_native_value(300)
    await c.async_disconnect("idle_timeout")
    assert c.controller is None

    replacement = c._controller = MotoMotionController(c)
    await c._async_restore_app_state(replacement)
    assert sliders["head"].native_value == 300
    c._client = MagicMock()
    c._client.is_connected = True
    c._client.write_gatt_char = AsyncMock()
    c._client.stop_notify = AsyncMock()
    c._client.disconnect = AsyncMock()
    replacement._session = (c._client, char, char)
    with (
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        await sliders["back"].async_set_native_value(400)
    original = posture(selected_posture, 170, 100, 55)
    expected = Position(300, original.base, 400, original.lumbar, original.tilt)
    assert c._client.write_gatt_char.await_args.args[1] == expected.to_bytes()
    assert sliders["head"].native_value == 300
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
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets", return_value=([(a, "left"), (b, "left")], [])
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
        patch("custom_components.adjustable_bed.services._resolve_sided_targets", return_value=([(c, "both")], [])),
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
    assert replacement._position() == posture("tv", 170, 100, 55)
    c._client.is_connected = False
    await c.async_shutdown()


async def test_setup_step_and_options_ownership_use_same_identity_validation(hass):
    from custom_components.adjustable_bed.app_profiles import (
        hidden_generic_fields,
        per_side_profile,
    )
    from custom_components.adjustable_bed.config_flow import (
        AdjustableBedConfigFlow,
        _name_rule_setup_name,
    )
    from custom_components.adjustable_bed.setup_questions import setup_profile

    # The generic question step asks the exact name and checks it as the app does.
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._manual_data = {CONF_BED_TYPE: "motomotion", CONF_NAME: "A renamed chair"}
    result = await flow.async_step_profile_questions({CONF_BLE_DEVICE_NAME: "MOTO"})
    assert result["type"] == "form"
    assert result["errors"] == {CONF_BLE_DEVICE_NAME: "motomotion_profile"}
    profile = setup_profile("motomotion")
    assert profile is not None and profile.validate is not None
    assert {question.key for question in profile.questions} == {CONF_BLE_DEVICE_NAME}
    values = {CONF_BED_TYPE: "motomotion", CONF_BLE_DEVICE_NAME: "SOFA000001S000H"}
    assert profile.validate(values) == {}
    settled = profile.settled(values)
    assert settled["disable_angle_sensing"] is True and settled["has_massage"] is False
    assert _name_rule_setup_name("motomotion", "SOFA000001S000H") == {
        CONF_BLE_DEVICE_NAME: "SOFA000001S000H"
    }
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
    from custom_components.adjustable_bed.codec.motomotion import ascii_command

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
    from custom_components.adjustable_bed.codec.motomotion import ascii_command
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
    from custom_components.adjustable_bed.codec.motomotion import ascii_command

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
    from custom_components.adjustable_bed.codec.motomotion import ascii_command

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
    # Setup migrates the entry to schema 5, which records its profile id.
    assert entry.data["profile_id"] == "motomotion"
    original = dict(entry.data)
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


async def test_selected_right_survives_idle_disconnect_and_real_controller_replacement(
    hass, protocol_clock, mock_bleak_client, mock_coordinator_connected, enable_custom_integrations
):
    from custom_components.adjustable_bed.codec.motomotion import ascii_command
    from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator
    from custom_components.adjustable_bed.pairing import build_single_address_pair_entry_data
    from custom_components.adjustable_bed.select import AdjustableBedControllerSelect

    c, original = await loaded_runtime(hass, "SOFA000001SC00M", mock_bleak_client)
    selected = AdjustableBedControllerSelect(
        c, next(s for s in original.controller_select_specs if s.key == "motomotion_side")
    )
    await selected.async_select_option("right")
    c._cancel_disconnect_timer()
    await c._async_idle_disconnect()
    assert c.controller is None and c._last_disconnect_reason == "idle_timeout"
    mock_bleak_client.write_gatt_char.reset_mock()

    async def movement(controller):
        await controller.hold_control("motomotion_headrest_up", 150)

    async def comfort(controller):
        await controller.action("motomotion_heat_up")

    await c.async_execute_controller_command(movement, read_positions_after_operation=False)
    replacement = c.controller
    assert replacement is not original
    await c.async_execute_controller_command(comfort, read_positions_after_operation=False)
    assert [call.args[1] for call in mock_bleak_client.write_gatt_char.await_args_list] == [
        ascii_command(2, 10000),
        *([ascii_command(0, 10000)] * 3),
        ascii_command(332, 10000),
    ]
    assert c.controller_state["motomotion_side"] == "right"
    # A physical child owns its side even when the standalone preference is right.
    paired = MockConfigEntry(
        domain=DOMAIN, data=build_single_address_pair_entry_data(c.entry.data, name="Chair pair")
    )
    parent = SingleAddressPairedCoordinator(hass, paired, c)
    mock_bleak_client.write_gatt_char.reset_mock()
    await parent.async_execute_controller_command(comfort, side="left")
    await parent.async_execute_controller_command(comfort, side="right")
    assert [call.args[1] for call in mock_bleak_client.write_gatt_char.await_args_list] == [
        ascii_command(332, 0),
        ascii_command(332, 10000),
    ]
    assert replacement.persisted_app_state["side"] == "right"
    await parent.async_shutdown()


async def test_side_preferences_are_owned_by_exact_address_and_profile(hass):
    name = "SOFA000001SC00M"
    c = runtime(hass, name)
    await c.async_prime_offline_controller()
    original = c.capability_controller
    await original.select("side", "right")
    for profile, address, expected in (
        (name, c.address, "right"),
        ("SOFA000003SC00M", c.address, "left"),
        (name, "AA:BB:CC:DD:EE:14", "left"),
        ("SOFA000001MC00M", c.address, "left"),
    ):
        other = runtime(hass, profile, address)
        await other.async_prime_offline_controller()
        assert other.capability_controller.persisted_app_state["side"] == expected
        await other.async_shutdown()
    await c.async_shutdown()


@pytest.mark.parametrize("saved_side", ["both", "RIGHT", "", None, True, 1, ["right"]])
async def test_invalid_saved_side_cannot_become_a_physical_target(hass, saved_side):
    from custom_components.adjustable_bed.app_state_store import app_state_slot

    c = runtime(hass, "SOFA000001SC00M")
    await c.async_prime_offline_controller()
    original = c.capability_controller
    slot = app_state_slot("motomotion", None, original.persisted_app_state_key)
    c._app_state_store.update(slot, {"side": saved_side})
    replacement = MotoMotionController(c)
    await c._async_restore_app_state(replacement)
    assert replacement._parameter() == 0
    assert replacement.persisted_app_state["side"] == "left"
    assert (await c._app_state_store.async_slot(slot))["side"] == "left"
    await c.async_shutdown()


async def test_non_side_profile_cannot_restore_a_right_side_target(hass):
    c = runtime(hass, "SOFA000001MC00M")
    await c.async_prime_offline_controller()
    ctrl = c.capability_controller
    ctrl.restore_persisted_app_state({"side": "right"})
    assert ctrl.persisted_app_state["side"] == "left"
    assert ctrl._parameter() == 0
    assert all(s.key != "motomotion_side" for s in ctrl.controller_select_specs)
    await c.async_shutdown()


@pytest.mark.parametrize("sided", [True, False])
async def test_side_state_translations_belong_to_real_declared_sensors(hass, sided):
    from custom_components.adjustable_bed.sensor import AdjustableBedControllerStateSensor

    c = runtime(hass, "SOFA000001SC00M" if sided else "SOFA000001MC00M")
    await c.async_prime_offline_controller()
    ctrl = c.capability_controller
    keys = {
        f"motomotion_{kind}_{side}" for side in ("left", "right") for kind in ("heat", "massage")
    }
    sensors = {
        s.key: AdjustableBedControllerStateSensor(c, s)
        for s in ctrl.controller_state_sensor_specs
        if s.key in keys
    }
    assert set(sensors) == (keys if sided else set())
    for key, sensor in sensors.items():
        assert sensor.translation_key == key
        assert sensor.unique_id == c.entity_unique_id(key)
        c.handle_controller_state_update(key, 2)
        assert sensor.native_value == 2
    if sided:
        with ctrl.side_scope("right"):
            right_keys = {s.key for s in ctrl.controller_state_sensor_specs}
        assert right_keys & keys == {
            "motomotion_heat_right",
            "motomotion_massage_right",
        }
    await c.async_shutdown()


async def test_manual_discovery_keeps_substring_candidates_without_advertised_services(
    hass, mock_coordinator_connected
):
    from custom_components.adjustable_bed import config_flow
    from custom_components.adjustable_bed.profiles.motomotion import Profile
    from tests.test_detection import _make_service_info

    names = ["xSOFA00001SC00M", "xBT201000", "xMOTO0000100000"]
    infos = [
        _make_service_info(name=name, address=f"AA:BB:CC:DD:EE:{index:02X}", service_uuids=[])
        for index, name in enumerate(names, 0x20)
    ]
    flow = config_flow.AdjustableBedConfigFlow()
    flow.hass = hass
    with patch.object(config_flow, "get_discovered_service_info", return_value=infos):
        result = await flow.async_step_manual()
    assert result["type"] == "form" and result["step_id"] == "manual"
    assert [info.name for info in flow._all_ble_devices.values()] == names
    # The host's prefix index does not replace the exact native contains rules.
    for info in infos:
        assert Profile(info.name).name == info.name
        assert config_flow._name_rule_setup_name("motomotion", info.name) == {
            CONF_BLE_DEVICE_NAME: info.name
        }


@pytest.mark.parametrize("dimensions,edited_head", [((170, 100, 55), 300), ((140, 100, 55), None)])
async def test_working_targets_survive_real_idle_replacement_next_axis_and_save(
    hass,
    protocol_clock,
    mock_bleak_client,
    mock_coordinator_connected,
    enable_custom_integrations,
    dimensions,
    edited_head,
):
    from dataclasses import replace

    from custom_components.adjustable_bed.button import ControllerActionButton
    from custom_components.adjustable_bed.motomotion_requests import Request
    from custom_components.adjustable_bed.number import AdjustableBedControllerNumber

    c, ctrl = await loaded_runtime(hass, "SOFA000001A000H", mock_bleak_client)

    async def select_user(controller):
        await controller.async_execute_motomotion_request(
            Request("save_user", user="K", dimensions=dimensions)
        )
        await controller.async_execute_motomotion_request(Request("select_user", user="K"))
        await controller.action("motomotion_posture_recall")

    await c.async_execute_controller_command(select_user, read_positions_after_operation=False)
    baseline = posture("upright", *dimensions)
    if edited_head is not None:
        number = AdjustableBedControllerNumber(
            c, next(s for s in ctrl.controller_number_specs if s.key == "motomotion_target_head")
        )
        await number.async_set_native_value(edited_head)
        baseline = replace(baseline, head=edited_head)
    else:
        assert baseline.head == 867  # Helper output exceeds the head edit slider's 863 limit.
    c._cancel_disconnect_timer()
    await c._async_idle_disconnect()
    assert await c.async_ensure_connected()
    assert c.controller._targets == baseline
    back = AdjustableBedControllerNumber(
        c, next(s for s in ctrl.controller_number_specs if s.key == "motomotion_target_back")
    )
    await back.async_set_native_value(500)
    expected = replace(baseline, back=500)
    assert c.controller is not ctrl
    assert mock_bleak_client.write_gatt_char.await_args.args[1] == expected.to_bytes()
    save = ControllerActionButton(
        c,
        next(s for s in c.controller.controller_button_specs if s.key == "motomotion_posture_save"),
    )
    await save.async_press()
    c._cancel_disconnect_timer()
    await c._async_idle_disconnect()

    async def recall(controller):
        await controller.action("motomotion_posture_recall")

    await c.async_execute_controller_command(recall, read_positions_after_operation=False)
    assert mock_bleak_client.write_gatt_char.await_args.args[1] == expected.to_bytes()
    assert c.controller._user == "K"
    await hass.config_entries.async_unload(c.entry.entry_id)


@pytest.mark.parametrize("name", ["BT2010000", "SOFA00000MM0000"])
async def test_active_music_intent_survives_replacement_and_next_mode_packet(
    hass,
    protocol_clock,
    mock_bleak_client,
    mock_coordinator_connected,
    enable_custom_integrations,
    name,
):
    from custom_components.adjustable_bed.number import AdjustableBedControllerNumber
    from custom_components.adjustable_bed.select import AdjustableBedControllerSelect

    c, ctrl = await loaded_runtime(hass, name, mock_bleak_client)
    mode = AdjustableBedControllerSelect(
        c, next(s for s in ctrl.controller_select_specs if s.key == "motomotion_music_mode")
    )
    volume = AdjustableBedControllerNumber(
        c, next(s for s in ctrl.controller_number_specs if s.key == "motomotion_volume")
    )
    await mode.async_select_option("wide")
    await volume.async_set_native_value(17)
    c._cancel_disconnect_timer()
    await c._async_idle_disconnect()
    assert await c.async_ensure_connected()
    assert c.controller is not ctrl
    assert mode.current_option == "wide"
    assert volume.native_value == 17
    assert c.controller._custom_eq == [8, 2, 2, 7]

    async def edit_bass(controller):
        await controller.set_number("bass", 3)

    before = mock_bleak_client.write_gatt_char.await_count
    with pytest.raises(ValueError, match="custom music mode"):
        await c.async_execute_controller_command(edit_bass)
    assert mock_bleak_client.write_gatt_char.await_count == before
    await mode.async_select_option("electric")
    if name.startswith("BT201"):
        assert mock_bleak_client.write_gatt_char.await_args.args[1] == binary_command(9, 17)
    else:
        assert (
            mock_bleak_client.write_gatt_char.await_args.args[1] == b"$#M17\r$#T13\r$#B14\r$#V15\r"
        )
    await hass.config_entries.async_unload(c.entry.entry_id)


@pytest.mark.parametrize(
    "invalid",
    [
        {"posture": []},
        {"music_mode": []},
        {"eq": [True, 0, 0, 0]},
        {"timer": True},
        {"working_targets": {"positions": {"head": 1}}},
    ],
)
async def test_invalid_optional_intent_cannot_reset_valid_right_side(
    hass,
    protocol_clock,
    mock_bleak_client,
    mock_coordinator_connected,
    enable_custom_integrations,
    invalid,
):
    from custom_components.adjustable_bed.app_state_store import app_state_slot
    from custom_components.adjustable_bed.select import AdjustableBedControllerSelect

    c, ctrl = await loaded_runtime(hass, "SOFA000001SD00M", mock_bleak_client)
    side = AdjustableBedControllerSelect(
        c, next(s for s in ctrl.controller_select_specs if s.key == "motomotion_side")
    )
    await side.async_select_option("right")
    slot = app_state_slot("motomotion", None, ctrl.persisted_app_state_key)
    c._app_state_store.update(slot, {**ctrl.persisted_app_state, **invalid})
    c._cancel_disconnect_timer()
    await c._async_idle_disconnect()

    async def comfort(controller):
        await controller.action("motomotion_heat_up")

    await c.async_execute_controller_command(comfort, read_positions_after_operation=False)
    assert c.controller_state["motomotion_side"] == "right"
    assert mock_bleak_client.write_gatt_char.await_args.args[1] == ascii_command(332, 10000)
    await hass.config_entries.async_unload(c.entry.entry_id)


async def test_working_intent_address_and_exact_profile_isolation(hass):
    from custom_components.adjustable_bed.codec.motomotion import Position
    from custom_components.adjustable_bed.motomotion_requests import Request

    name = "SOFA000001A000H"
    c, ctrl = await connected_runtime(hass, name)
    await ctrl.async_execute_motomotion_request(
        Request("save_user", user="K", dimensions=(170, 100, 55))
    )
    await ctrl.async_execute_motomotion_request(Request("select_user", user="K", posture="tv"))
    targets = Position(300, 400, 500, 600, 200)
    await ctrl.async_execute_motomotion_request(Request("fine_tune", posture="tv", targets=targets))
    for profile, address, owns in [
        (name, c.address, True),
        ("SOFA000003A000H", c.address, False),
        (name, "AA:BB:CC:DD:EE:14", False),
    ]:
        other = runtime(hass, profile, address)
        await other.async_prime_offline_controller()
        restored = other.capability_controller
        assert restored._targets == (targets if owns else None)
        assert restored._user == ("K" if owns else None)
        assert restored._posture == ("tv" if owns else "upright")
        await other.async_shutdown()
    c._client.is_connected = False
    await c.async_shutdown()


async def test_selected_timer_survives_replacement_before_explicit_apply(
    hass, protocol_clock, mock_bleak_client, mock_coordinator_connected, enable_custom_integrations
):
    from custom_components.adjustable_bed.button import ControllerActionButton
    from custom_components.adjustable_bed.number import AdjustableBedControllerNumber

    c, ctrl = await loaded_runtime(hass, "SOFA000001SD00M", mock_bleak_client)
    timer = AdjustableBedControllerNumber(
        c, next(s for s in ctrl.controller_number_specs if s.key == "motomotion_timer")
    )
    await timer.async_set_native_value(127)
    c._cancel_disconnect_timer()
    await c._async_idle_disconnect()
    mock_bleak_client.write_gatt_char.reset_mock()
    apply = ControllerActionButton(
        c, next(s for s in ctrl.controller_button_specs if s.key == "motomotion_timer_apply")
    )
    await apply.async_press()
    assert [call.args[1] for call in mock_bleak_client.write_gatt_char.await_args_list] == [
        b"$z",
        ascii_command(32999, 127),
    ]
    await hass.config_entries.async_unload(c.entry.entry_id)


@pytest.mark.parametrize("name", ["BT2010000", "SOFA00000MM0000"])
async def test_muted_music_survives_idle_before_next_wide_mode_packet(
    hass, protocol_clock, mock_bleak_client, mock_coordinator_connected,
    enable_custom_integrations, name
):
    from custom_components.adjustable_bed.number import AdjustableBedControllerNumber
    from custom_components.adjustable_bed.select import AdjustableBedControllerSelect

    c, original = await loaded_runtime(hass, name, mock_bleak_client)
    volume = AdjustableBedControllerNumber(
        c, next(s for s in original.controller_number_specs if s.key == "motomotion_volume")
    )
    mode = AdjustableBedControllerSelect(
        c, next(s for s in original.controller_select_specs if s.key == "motomotion_music_mode")
    )
    await volume.async_set_native_value(0)
    c._cancel_disconnect_timer()
    await c._async_idle_disconnect()
    assert c.controller is None
    await mode.async_select_option("wide")
    assert c.controller is not original
    assert volume.native_value == 0 and mode.current_option == "wide"
    if name.startswith("BT201"):
        assert mock_bleak_client.write_gatt_char.await_args.args[1] == binary_command(9, 0)
    else:
        assert mock_bleak_client.write_gatt_char.await_args.args[1] == b"$#M00\r$#T10\r$#B05\r$#V05\r"
    await hass.config_entries.async_unload(c.entry.entry_id)


async def test_configure_switch_of_a_single_address_pair_applies_the_profile(hass):
    """The declaration's owned fields reach a paired save, which keeps only shown changes."""
    from unittest.mock import patch

    from homeassistant.data_entry_flow import FlowResultType

    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
    from custom_components.adjustable_bed.pairing import build_single_address_pair_entry_data

    single = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:14",
        CONF_NAME: "Chair",
        CONF_BED_TYPE: "keeson",
        "protocol_variant": "base",
        "motor_count": 2,
        "has_massage": True,
        "disable_angle_sensing": False,
        "motor_pulse_user_set": True,
    }
    entry = MockConfigEntry(
        domain=DOMAIN, data=build_single_address_pair_entry_data(single, name="Chair")
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    form = await flow.async_step_settings({CONF_BED_TYPE: "motomotion"})
    assert form["type"] == FlowResultType.FORM
    with patch.object(hass.config_entries, "async_schedule_reload"):
        result = await flow.async_step_settings({CONF_BLE_DEVICE_NAME: "SOFA000001S000M"})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_BED_TYPE] == "motomotion"
    assert entry.data[CONF_BLE_DEVICE_NAME] == "SOFA000001S000M"
    assert entry.data["has_massage"] is False
    assert entry.data["disable_angle_sensing"] is True
    assert entry.data["motor_pulse_user_set"] is False
