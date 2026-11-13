"""Row180 literal, session, execution and Home Assistant exposure contracts."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.serenity.rize import SAVE_ACK, RizeRemedyIIController
from custom_components.adjustable_bed.codec.okin_nframe import frame
from custom_components.adjustable_bed.const import BED_TYPE_RIZE_REMEDY_II, CONF_MOTOR_COUNT
from custom_components.adjustable_bed.profiles.okin_nframe import RIZE_REMEDY_II
from tests.hold_lease_wire import intervals, leased_hold, virtual_clock
from tests.rize_remedy_ii_vectors import VECTORS
from tests.test_okin_bedding_apps import _coordinator, written

STOP = dict(VECTORS)["stop"]


def rize(pulse_count: int = 2) -> RizeRemedyIIController:
    coordinator = _coordinator(pulse_count=pulse_count)
    coordinator.client.stop_notify = AsyncMock()
    return RizeRemedyIIController(coordinator)


@pytest.mark.parametrize(("action", "literal"), VECTORS)
async def test_every_live_row_and_release(action: str, literal: str) -> None:
    ctrl = rize()
    assert frame(RIZE_REMEDY_II.keys[action], 12).hex() == literal
    times: list[float] = []

    async def write(*_args, **_kwargs):
        times.append(asyncio.get_running_loop().time())
        await asyncio.sleep(0.007)  # Pacing absorbs real BLE write latency.

    ctrl.client.write_gatt_char.side_effect = write
    with virtual_clock():
        if action == "stop":
            await ctrl.stop_all()
        else:
            await ctrl.hold_control(action, 250)
    assert written(ctrl)[-2:] == [STOP, STOP]
    assert times[-2:] == pytest.approx([0.1, 0.2] if action == "stop" else [0.35, 0.45])
    if action != "stop":
        assert written(ctrl)[:-2] == [literal] * 3
        assert times[:-2] == pytest.approx([0, 0.1, 0.2])


@pytest.mark.parametrize("count", [1, 3, 11])
async def test_finite_cover_preserves_configured_pulse_count(count: int) -> None:
    ctrl = rize(count)
    with virtual_clock():
        await ctrl.move_lumbar_up()
    assert written(ctrl) == [dict(VECTORS)["lumbar_up"]] * count + [STOP, STOP]
    assert {spec.key for spec in ctrl.motor_control_specs} == {"head", "feet", "lumbar"}
    assert all(spec.scheduler_resource == "*" for spec in ctrl.motor_control_specs)
    assert not ctrl.execution.concurrent


@pytest.mark.parametrize("end", ["expire", "stop"])
async def test_renewable_cover_hold_and_expiry(end) -> None:
    wire = await leased_hold("rize_remedy_ii", lambda ctrl: ctrl.move_head_up(), end_after_s=3, end=end)
    held = tuple(w for w in wire.held if w.data.hex() == dict(VECTORS)["head_up"])
    assert len(held) > wire.pulse_count
    assert all(100 <= gap <= 101 for gap in intervals(held))
    assert wire.after and {w.data.hex() for w in wire.after} == {STOP}
    assert wire.after[0].at_ms - wire.ended_ms == pytest.approx(100, abs=100)


@pytest.mark.parametrize(("slot", "action", "pending"), [(1, "save_zero_g", 5), (2, "save_incline", 6), (3, "save_lounge", 3)])
async def test_save_chord_then_remaining_key_or_both_released(slot, action, pending) -> None:
    ctrl = rize()
    with virtual_clock():
        await ctrl.start_notify()
        await ctrl.program_memory(slot)
        assert written(ctrl) == [dict(VECTORS)[action]] * 5 + [STOP, STOP]
        assert ctrl._pending_save == pending
        await ctrl.stop_all()
        assert ctrl._pending_save == pending  # Source STOP does not clear pending.
        ctrl.client.write_gatt_char.reset_mock()
        # Partial release is represented by the remaining live control, after
        # HA releases the previous operation under the scheduler's lock.
        await ctrl.hold_control("flat", 100)
        assert written(ctrl) == [dict(VECTORS)["flat"], STOP, STOP]
        ctrl.client.write_gatt_char.reset_mock()
        await ctrl.preset_memory(slot)
        assert written(ctrl)[0] == dict(VECTORS)[action.removeprefix("save_")]
    assert ctrl.memory_slot_names == ("Zero Gravity", "Incline", "Leisure")
    with pytest.raises(ValueError):
        await ctrl.program_memory(4)


@pytest.mark.parametrize(("data", "expected"), [
    ("000000000000a000000001", True),
    ("000000000000a00000007f", True),
    ("000000000000a000000000", False),
    ("000000000000a000000080", False),
    ("000000000000a0000000ff", False),
    ("000000000000a0000000", False),
    ("000000000000a100000001", False),
])
async def test_save_parser_signed_length_and_tag_boundaries(data, expected) -> None:
    ctrl = rize()
    with virtual_clock():
        await ctrl.start_notify()
        await ctrl.program_memory(1)
    ctrl.forward_controller_state_update = MagicMock()
    receive = ctrl.client.start_notify.call_args.args[1]
    receive(None, bytearray.fromhex(data))
    assert ctrl.forward_controller_state_update.call_args_list == (
        [((SAVE_ACK, 5),)] if expected else []
    )
    receive(None, bytearray.fromhex(data))  # Duplicate cannot acknowledge twice.
    assert ctrl.forward_controller_state_update.call_count == int(expected)


async def test_no_pending_unsubscribed_stale_session_or_overlapping_save_ack() -> None:
    ctrl = rize()
    ack = bytearray.fromhex("000000000000a000000001")
    ctrl.forward_controller_state_update = MagicMock()
    ctrl._handle_notification(None, ack)
    ctrl.forward_controller_state_update.assert_not_called()
    with virtual_clock():
        await ctrl.start_notify()
        stale = ctrl.client.start_notify.call_args.args[1]
        await ctrl.program_memory(1)
        await ctrl.program_memory(2)  # No operation id in the packet, refuse ambiguity.
        ctrl.forward_controller_state_update.reset_mock()
        stale(None, ack)
        ctrl.forward_controller_state_update.assert_not_called()
        ctrl.on_disconnect()
        await ctrl.start_notify()
        await ctrl.program_memory(3)
        ctrl.forward_controller_state_update.reset_mock()
        stale(None, ack)
        ctrl.forward_controller_state_update.assert_not_called()
        current = ctrl.client.start_notify.call_args.args[1]
        current(None, ack)
        ctrl.forward_controller_state_update.assert_called_once_with(SAVE_ACK, 3)
        ctrl.forward_controller_state_update.reset_mock()
        await ctrl.stop_notify()
        ctrl.forward_controller_state_update.reset_mock()
        current(None, ack)
        ctrl.forward_controller_state_update.assert_not_called()


async def test_cancelled_movement_releases_before_replacement_no_late_stop() -> None:
    ctrl = rize(10)
    cancel = ctrl._coordinator.cancel_command

    async def cancel_first(*_args, **_kwargs):
        cancel.set()

    ctrl.client.write_gatt_char.side_effect = cancel_first
    with virtual_clock():
        await ctrl.move_head_up()
        assert written(ctrl) == [dict(VECTORS)["head_up"], STOP, STOP]
        cancel.clear()
        ctrl.client.write_gatt_char.side_effect = None
        ctrl.client.write_gatt_char.reset_mock()
        await ctrl.move_lumbar_down()
        await asyncio.sleep(1)
    assert written(ctrl) == [dict(VECTORS)["lumbar_down"]] * 10 + [STOP, STOP]


async def test_cleanup_cannot_migrate_to_reconnected_client() -> None:
    ctrl = rize()
    old, new = ctrl.client, rize().client

    async def replace_link(*_args, **_kwargs):
        ctrl._coordinator.client = new

    old.write_gatt_char.side_effect = replace_link
    with virtual_clock(), pytest.raises(ConnectionError):
        await ctrl.move_head_up()
    new.write_gatt_char.assert_not_called()


async def test_optional_info_read_exact_roles_and_write_type_policy() -> None:
    ctrl = rize()
    info = ctrl.client.services[1].characteristics[0]
    info.uuid = "00002a24-0000-1000-8000-00805f9b34fb"
    with virtual_clock():
        await ctrl.start_notify()
        ctrl.client.read_gatt_char.assert_awaited_once_with(info.uuid)
        ctrl.client.services[0].characteristics[0].properties = ["write-without-response"]
        await ctrl.lights_on()
        assert all(not call.kwargs["response"] for call in ctrl.client.write_gatt_char.call_args_list)
    ctrl.client.services[0].characteristics.pop()
    with pytest.raises(ValueError, match="notification"):
        ctrl.require_roles()
    assert not ctrl.supports_clock_alarm
    assert not ctrl.supports_massage_toggle_control
    assert not ctrl.position_number_specs
    assert not ctrl.controller_state_binary_sensor_specs
    assert len(ctrl.controller_state_sensor_specs) == 1


async def test_manual_picker_profile_route_defaults_and_entities(hass) -> None:
    from custom_components.adjustable_bed.button import _button_entities_for
    from custom_components.adjustable_bed.config_flow import (
        AdjustableBedConfigFlow,
        _motor_count_options,
    )
    from custom_components.adjustable_bed.const import (
        CONF_BED_TYPE,
        CONF_MOTOR_PULSE_DELAY_MS,
        CONF_PROFILE_ID,
        requires_pairing,
    )
    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.detection import get_bed_type_options
    from custom_components.adjustable_bed.profile_id import with_profile_ids
    from tests.form_helpers import shown_markers
    from tests.test_controller_contract import _FactoryCoordinator
    from tests.test_malouf_app_entities import configure_entity_runtime

    assert any(option["value"] == BED_TYPE_RIZE_REMEDY_II and "Rize Remedy II" in option["label"] for option in get_bed_type_options())
    assert _motor_count_options(BED_TYPE_RIZE_REMEDY_II) == [3]
    assert not requires_pairing(BED_TYPE_RIZE_REMEDY_II)
    assert with_profile_ids({CONF_BED_TYPE: BED_TYPE_RIZE_REMEDY_II})[CONF_PROFILE_ID] == BED_TYPE_RIZE_REMEDY_II
    factory = await create_controller(_FactoryCoordinator(), BED_TYPE_RIZE_REMEDY_II, None, None)
    assert isinstance(factory, RizeRemedyIIController)
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._selected_bed_type = flow._disambiguated_bed_type = BED_TYPE_RIZE_REMEDY_II
    flow._async_transport_note = AsyncMock(return_value="")
    form = await flow.async_step_manual_entry()
    assert CONF_MOTOR_COUNT not in shown_markers(form)
    assert CONF_MOTOR_PULSE_DELAY_MS not in shown_markers(form)
    ctrl = rize()
    runtime = configure_entity_runtime(hass, ctrl, BED_TYPE_RIZE_REMEDY_II)
    buttons = _button_entities_for(hass, runtime)
    assert any(button.translation_key == "rize_remedy_ii_wave_1" for button in buttons)
    assert ctrl.memory_slot_count == 3


@pytest.mark.parametrize("name", ["OKIN", "oKiN-example", "okin-003444", "OKIN Receiver"])
async def test_name_only_candidate_keeps_receiver_precedence(name) -> None:
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    info = MagicMock(name=None)
    info.name, info.device, info.address = name, None, "AA:BB:CC:DD:EE:FF"
    info.service_uuids, info.manufacturer_data = [], {}
    result = detect_bed_type_detailed(info)
    assert BED_TYPE_RIZE_REMEDY_II in (result.ambiguous_types or ())
    assert result.bed_type != BED_TYPE_RIZE_REMEDY_II
    from custom_components.adjustable_bed.const import (
        BED_TYPE_LEGGETT_GEN2,
        LEGGETT_GEN2_SERVICE_UUID,
    )
    info.service_uuids = [LEGGETT_GEN2_SERVICE_UUID]
    # A concrete strong receiver result keeps its primary route/confidence.
    strong = detect_bed_type_detailed(info)
    assert strong.bed_type == BED_TYPE_LEGGETT_GEN2 and strong.confidence == 1.0
    assert BED_TYPE_RIZE_REMEDY_II in (strong.ambiguous_types or ())


async def test_actual_ha_setup_connect_and_reconnect(hass, enable_custom_integrations, mock_coordinator_connected, mock_bleak_client, monkeypatch) -> None:
    from homeassistant.const import CONF_ADDRESS, CONF_NAME
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.const import (
        CONF_BED_TYPE,
        CONF_DISABLE_ANGLE_SENSING,
        CONF_HAS_MASSAGE,
        CONF_PROFILE_ID,
        DOMAIN,
    )
    from custom_components.adjustable_bed.profile_id import with_profile_ids

    monkeypatch.setattr("custom_components.adjustable_bed.beds.serenity.rize._INFO_READ_DELAY_S", 0)
    client = mock_bleak_client
    roles = rize().client.services
    client.services = roles
    client.is_connected = True
    entry = MockConfigEntry(domain=DOMAIN, version=5, minor_version=3, data=with_profile_ids({
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_NAME: "Rize Remedy II",
        CONF_BED_TYPE: BED_TYPE_RIZE_REMEDY_II, CONF_MOTOR_COUNT: 3,
        CONF_HAS_MASSAGE: True, CONF_DISABLE_ANGLE_SENSING: True,
    }))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][entry.entry_id]
    assert entry.data[CONF_PROFILE_ID] == BED_TYPE_RIZE_REMEDY_II
    assert isinstance(coordinator.capability_controller, RizeRemedyIIController)
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert {entity.translation_key for entity in entities if entity.domain == "cover"} == {"head", "feet", "lumbar"}
    assert any(entity.translation_key == "rize_remedy_ii_wave_3" for entity in entities)
    assert not any(entity.domain == "number" and "position" in (entity.translation_key or "") for entity in entities)
    # The real coordinator builds and subscribes the selected profile on reconnect.
    assert await coordinator.async_ensure_connected()
    first = coordinator.controller
    assert isinstance(first, RizeRemedyIIController)
    await coordinator.async_disconnect("test")
    assert first._pending_save is None
    assert await coordinator.async_ensure_connected()
    assert isinstance(coordinator.controller, RizeRemedyIIController)
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_shared_services_admit_only_live_controls_and_named_memories(hass) -> None:
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed.const import DOMAIN, SIDE_BOTH
    from custom_components.adjustable_bed.services import async_register_services
    from tests.test_okin_bedding_apps_integration import _target

    await async_register_services(hass)
    ctrl = rize()
    target = _target(BED_TYPE_RIZE_REMEDY_II, ctrl)
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets", return_value=([(target, SIDE_BOTH)], [])):
        with virtual_clock():
            await hass.services.async_call(DOMAIN, "hold_control", {"device_id": "bed", "control": "save_incline", "duration": 0.3}, blocking=True)
        assert written(ctrl)[0] == dict(VECTORS)["save_incline"]
        ctrl.client.write_gatt_char.reset_mock()
        for control in ("selector_4_up", "memory_4", "massage_timer_cycle", "alarm", "head_up+foot_up"):
            with pytest.raises(ServiceValidationError):
                await hass.services.async_call(DOMAIN, "hold_control", {"device_id": "bed", "control": control, "duration": 1}, blocking=True)
        ctrl.client.write_gatt_char.assert_not_called()


async def test_options_change_and_pair_side_profile_ownership(hass) -> None:
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.app_profiles import per_side_profile
    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
    from custom_components.adjustable_bed.const import (
        BED_TYPE_OKIN_CST,
        CONF_BED_TYPE,
        CONF_DISABLE_ANGLE_SENSING,
        CONF_HAS_MASSAGE,
        CONF_MOTOR_PULSE_COUNT,
        CONF_MOTOR_PULSE_DELAY_MS,
        CONF_PROTOCOL_VARIANT,
        DOMAIN,
    )
    from tests.form_helpers import shown_markers

    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_BED_TYPE: BED_TYPE_OKIN_CST,
        CONF_PROTOCOL_VARIANT: "cst_support", CONF_MOTOR_COUNT: 4, CONF_MOTOR_PULSE_COUNT: 7,
        CONF_MOTOR_PULSE_DELAY_MS: 150, CONF_HAS_MASSAGE: False})
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    form = await flow._async_options_form({CONF_BED_TYPE: BED_TYPE_RIZE_REMEDY_II}, step_id="settings")
    assert not {CONF_MOTOR_COUNT, CONF_PROTOCOL_VARIANT, CONF_MOTOR_PULSE_DELAY_MS} & shown_markers(form).keys()
    saved = await flow._async_options_form({CONF_BED_TYPE: BED_TYPE_RIZE_REMEDY_II}, step_id="settings")
    assert saved["type"] == "create_entry"
    assert entry.data[CONF_MOTOR_COUNT] == 3
    assert entry.data[CONF_HAS_MASSAGE] is True
    assert entry.data[CONF_DISABLE_ANGLE_SENSING] is True
    assert entry.data.get(CONF_PROTOCOL_VARIANT, "auto") == "auto"
    assert (entry.data[CONF_MOTOR_PULSE_COUNT], entry.data[CONF_MOTOR_PULSE_DELAY_MS]) == (10, 100)
    assert per_side_profile(BED_TYPE_RIZE_REMEDY_II, "auto") is not None


@pytest.mark.parametrize(("count", "invalid"), [(0, True), (1, False), (600, False), (601, True)])
def test_cover_pulse_count_bounds_match_the_admitted_ha_press_window(count, invalid) -> None:
    from custom_components.adjustable_bed.config_flow import _invalid_pulse_count
    assert _invalid_pulse_count(BED_TYPE_RIZE_REMEDY_II, count) is invalid


async def test_fixed_app_setup_finishes_without_an_empty_question_step(hass, enable_custom_integrations) -> None:
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.const import (
        CONF_DISABLE_ANGLE_SENSING,
        CONF_HAS_MASSAGE,
    )
    from tests.form_helpers import complete
    from tests.test_setup_entry import _app_then_address

    with (
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=False),
        patch("custom_components.adjustable_bed.async_setup_entry", AsyncMock(return_value=True)),
    ):
        result = await _app_then_address(hass, BED_TYPE_RIZE_REMEDY_II)
        assert result["step_id"] == "finish_settings"
        result = await complete(hass, result)
    assert result["type"] == "create_entry"
    assert result["data"][CONF_MOTOR_COUNT] == 3
    assert result["data"][CONF_HAS_MASSAGE] is True
    assert result["data"][CONF_DISABLE_ANGLE_SENSING] is True
    from custom_components.adjustable_bed.profile_id import resolve_profile_id
    assert resolve_profile_id(result["data"]) == BED_TYPE_RIZE_REMEDY_II


@pytest.mark.parametrize("control", ["head_up", "save_zero_g"])
async def test_scheduler_stop_preserves_this_and_subsequent_save_acknowledgments(
    hass, mock_coordinator_connected, mock_bleak_client, monkeypatch, control
) -> None:
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.command_scheduler import CommandOutcome
    from custom_components.adjustable_bed.const import CONF_BED_TYPE, DOMAIN
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.profile_id import with_profile_ids

    monkeypatch.setattr("custom_components.adjustable_bed.beds.serenity.rize._INFO_READ_DELAY_S", 0)
    mock_bleak_client.services = rize().client.services
    entry = MockConfigEntry(domain=DOMAIN, data=with_profile_ids({
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_BED_TYPE: BED_TYPE_RIZE_REMEDY_II,
        CONF_MOTOR_COUNT: 3,
    }))
    entry.add_to_hass(hass)
    coordinator = await AdjustableBedCoordinator.async_create(hass, entry)
    started = asyncio.Event()

    async def block_first_write(_char, data, **_kwargs):
        if data.hex() != STOP:
            started.set()
            await asyncio.Event().wait()

    with virtual_clock():
        assert await coordinator.async_connect()
        ctrl = coordinator.controller
        assert isinstance(ctrl, RizeRemedyIIController)
        receive = mock_bleak_client.start_notify.call_args.args[1]
        mock_bleak_client.write_gatt_char.side_effect = block_first_write
        task = asyncio.create_task(coordinator.async_execute_controller_command(
            lambda current: current.hold_control(control, 2000), cancel_running=False,
        ))
        await started.wait()
        await coordinator.async_stop_command()
        await task
        assert coordinator._command_scheduler.recent_records[-2].outcome is CommandOutcome.STOPPED
        assert not ctrl._save_ambiguous
        assert ctrl._pending_save == (5 if control == "save_zero_g" else None)
        if control == "head_up":
            mock_bleak_client.write_gatt_char.side_effect = None
            await coordinator.async_execute_controller_command(lambda current: current.program_memory(1))
        ctrl.forward_controller_state_update = MagicMock()
        receive(None, bytearray.fromhex("000000000000a000000001"))
        ctrl.forward_controller_state_update.assert_called_once_with(SAVE_ACK, 5)
        assert ctrl._pending_save is None
        await coordinator.async_disconnect("test")
        await coordinator._command_scheduler.async_shutdown()


async def test_failed_save_still_invalidates_untagged_acknowledgments() -> None:
    ctrl = rize()

    async def fail_command(_char, data, **_kwargs):
        if data.hex() != STOP:
            raise OSError("write failed")

    with virtual_clock():
        await ctrl.start_notify()
        ctrl.client.write_gatt_char.side_effect = fail_command
        with pytest.raises(OSError, match="write failed"):
            await ctrl.program_memory(1)
        assert ctrl._pending_save is None and ctrl._save_ambiguous
        ctrl.forward_controller_state_update = MagicMock()
        ctrl.client.start_notify.call_args.args[1](None, bytearray.fromhex("000000000000a000000001"))
        ctrl.forward_controller_state_update.assert_not_called()
