"""Native Tempur subset behavior, with original-link release and real setup."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.linak.controller import _AxisKeys
from custom_components.adjustable_bed.beds.linak.protocol import LinakModelVariant, LinakProfile
from custom_components.adjustable_bed.beds.linak.services import async_register_linak_services
from custom_components.adjustable_bed.beds.linak.tempur_relax import (
    MASSAGE_SELECTION,
    TempurRelaxController,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from tests.hold_lease_wire import virtual_clock
from tests.test_carpe_diem import frames, shutdown
from tests.test_carpe_diem import runtime as carpe_runtime


def runtime(hass, *, mask=0xF8):
    c = carpe_runtime(hass)
    hass.config_entries.async_update_entry(
        c.entry,
        data={
            **c.entry.data,
            "protocol_variant": "tempur_relax",
            "motor_pulse_count": 10,
            "motor_pulse_delay_ms": 100,
        },
    )
    c._controller = TempurRelaxController(c)
    c.controller._capabilities = replace(
        c.controller._capabilities,
        actuator_mask=mask,
        discovery_complete=True,
        model_variant=LinakModelVariant.STANDARD
        if mask is None
        else LinakModelVariant.TD3
        if mask == 0
        else LinakModelVariant.ADVANCED,
    )
    return c


async def test_movement_waits_after_write_and_releases_once(hass):
    c = runtime(hass)
    times = []

    async def record(*_args, **_kwargs):
        times.append(asyncio.get_running_loop().time())
        await asyncio.sleep(0.025)

    c.client.write_gatt_char.side_effect = record
    with virtual_clock():
        await c.controller.move_selected_sections(frozenset({"back", "head", "feet"}), True, 350)
    assert frames(c.client) == ["2b00"] * 3 + ["ff00"]
    assert [round(t - times[0], 3) for t in times] == [0, 0.125, 0.25, 0.35]
    await shutdown(c)


async def test_cancelled_write_settles_then_releases_original_link(hass):
    c = runtime(hass)
    entered, finish = asyncio.Event(), asyncio.Event()
    calls = []

    async def send(_uuid, frame, **_kwargs):
        calls.append(frame.hex())
        if frame == b"\x0b\x00":
            entered.set()
            await finish.wait()

    c.client.write_gatt_char.side_effect = send
    task = asyncio.create_task(c.controller.move_back_up())
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert calls == ["0b00"]
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert calls == ["0b00", "ff00"]
    await shutdown(c)


async def test_replaced_link_receives_no_old_release_or_followup(hass):
    c = runtime(hass)
    old = c.client
    replacement = MagicMock(
        is_connected=True,
        write_gatt_char=AsyncMock(),
        disconnect=AsyncMock(),
        stop_notify=AsyncMock(),
    )

    async def replace_link(*_args, **_kwargs):
        c._client = replacement

    old.write_gatt_char.side_effect = replace_link
    with virtual_clock(), pytest.raises(ConnectionError):
        await c.controller.move_back_up()
    assert frames(old) == ["0b00"]
    assert frames(replacement) == []
    await shutdown(c)


async def test_massage_sequences_same_selection_and_state(hass):
    c = runtime(hass)
    with virtual_clock():
        await c.async_execute_controller_command(lambda ctrl: ctrl.massage_head_toggle())
        assert c.controller_state.get(MASSAGE_SELECTION) == "back"
        await c.async_execute_controller_command(lambda ctrl: ctrl.massage_head_toggle())
        assert c.controller_state.get(MASSAGE_SELECTION) == "off"
        await c.async_execute_controller_command(lambda ctrl: ctrl.massage_foot_toggle())
        await c.async_execute_controller_command(lambda ctrl: ctrl.massage_toggle())
        await c.async_execute_controller_command(lambda ctrl: ctrl.massage_off())
    assert frames(c.client) == ["8900", "8c00", "8000", "8a00", "8b00", "8900", "8b00", "8000"]
    await shutdown(c)


@pytest.mark.parametrize(
    "mask,mode,axes,memories",
    [
        (None, "standard", set(), 0),
        (0, "td3", set(), 4),
        (1, "advanced_with_alarm", set(), 4),
        (0xF8, "advanced_with_alarm", {"back", "legs", "head", "feet", "base"}, 4),
    ],
)
async def test_capabilities_raw_reference_and_stale_callback(hass, mask, mode, axes, memories):
    c = runtime(hass)
    callbacks = {}
    c.client.services.get_service.side_effect = lambda uuid: (
        SimpleNamespace()
        if mask is not None
        and uuid in {const.LINAK_POSITION_SERVICE_UUID, const.LINAK_TIMER_SERVICE_UUID}
        else None
    )
    c.client.read_gatt_char = AsyncMock(
        side_effect=lambda uuid: (
            bytes((mask or 0,))
            if uuid == const.LINAK_POSITION_MASK_UUID
            else bytes.fromhex("102708ff")
        )
    )

    async def subscribe(uuid, callback):
        callbacks[uuid] = callback

    c.client.start_notify.side_effect = subscribe
    await c.controller.async_discover_capabilities()
    await c.controller.start_notify()
    assert c.controller.memory_slot_count == memories
    assert c.controller.protocol_diagnostics["model_variant"] == mode
    assert set(c.controller.protocol_diagnostics["position_axes"]) == axes
    assert not c.controller.supports_position_feedback
    assert not c.controller.position_number_specs
    assert (c.controller.alarm_capability is not None) == (mode == "advanced_with_alarm")
    assert c.controller.supports_automatic_drive
    assert not c.controller.supports_single_address_pairing
    if mask:
        assert {s.key for s in c.controller.motor_control_specs} == {
            "bed_height" if axis == "base" else axis for axis in axes
        }
    if axes:
        state = c.controller_state
        assert state.get(_AxisKeys.of("back").extension) == 100
        assert state.get(_AxisKeys.of("back").reported_speed) == 1.5625
        callback = callbacks[const.LINAK_POSITION_BACK_UUID]
        callback(None, bytearray())
        assert state.get(_AxisKeys.of("back").extension) == 0
        c._client = MagicMock(is_connected=True, disconnect=AsyncMock(), stop_notify=AsyncMock())
        callback(None, bytearray.fromhex("d2040001"))
        assert state.get(_AxisKeys.of("back").extension) == 0
    await shutdown(c)


async def test_rename_counts_java_characters_and_reads_original_link(hass):
    c = runtime(hass)
    c.client.read_gatt_char = AsyncMock(return_value=b"Bed")
    await c.controller.rename_device("é" * 17)
    call = c.client.write_gatt_char.call_args
    assert call.args == (const.LINAK_DEVICE_NAME_UUID, ("é" * 17).encode())
    c.client.read_gatt_char.assert_awaited_once_with(const.LINAK_DEVICE_NAME_UUID)
    with pytest.raises(ValueError):
        await c.controller.rename_device("😀" * 9)
    await shutdown(c)


@pytest.mark.parametrize("route", ["typed", "picked", "discovered"])
async def test_setup_and_factory(hass, mock_bluetooth_service_info, route):
    from custom_components.adjustable_bed.config_flow import (
        AdjustableBedConfigFlow,
        _bed_type_selector,
    )
    from custom_components.adjustable_bed.detection import bed_type_choice
    from tests.form_helpers import form_answers, form_fields, start_new_bed

    choice = bed_type_choice("linak", "tempur_relax")
    assert choice in _bed_type_selector(None).rows().values()
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {"source": "user"}
    flow._discovery_info = mock_bluetooth_service_info
    result = await start_new_bed(flow, route, choice)
    assert result["step_id"] == "finish_settings", result
    fields = form_fields(result["data_schema"])
    assert "has_massage" in fields
    assert "disable_angle_sensing" not in fields
    await flow.async_step_finish_settings(form_answers(result))
    data = flow._manual_data
    assert data["protocol_variant"] == "tempur_relax"
    assert (data["motor_pulse_count"], data["motor_pulse_delay_ms"]) == (10, 100)
    c = runtime(hass)
    ctrl = await create_controller(c, "linak", "tempur_relax", None)
    assert isinstance(ctrl, TempurRelaxController)
    assert ctrl._profile is LinakProfile.TEMPUR_RELAX
    await shutdown(c)


async def test_native_section_service_routes_base_through_mask(hass):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers import device_registry as dr

    c = runtime(hass)
    c.entry.mock_state(hass, ConfigEntryState.LOADED)
    hass.data.setdefault(const.DOMAIN, {})[c.entry.entry_id] = c
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=c.entry.entry_id, identifiers={(const.DOMAIN, c.address)}
    )
    async_register_linak_services(hass)
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN,
            "linak_move_sections",
            {
                "device_id": [device.id],
                "sections": ["base", "back"],
                "direction": "up",
                "duration_ms": 250,
            },
            blocking=True,
        )
    assert frames(c.client) == ["1f00"] * 3 + ["ff00"]
    await shutdown(c)


async def test_automatic_drive_uses_exact_four_byte_command_and_assumed_state(hass):
    from custom_components.adjustable_bed.state_keys import LINAK_AUTOMATIC_DRIVE
    from custom_components.adjustable_bed.switch import SWITCH_DESCRIPTIONS, AdjustableBedSwitch

    c = runtime(hass)
    description = next(d for d in SWITCH_DESCRIPTIONS if d.key == "linak_automatic_drive")
    switch = AdjustableBedSwitch(c, description)
    switch.hass = hass
    switch.entity_id = "switch.tempur_automatic_drive"
    switch.async_write_ha_state = MagicMock()
    await switch.async_turn_on()
    await switch.async_turn_off()
    assert frames(c.client) == ["893b8001", "893b8000"]
    assert c.controller_state.get(LINAK_AUTOMATIC_DRIVE) is False
    assert all(
        call.args[0] == const.LINAK_CONFIG_CHAR_UUID
        for call in c.client.write_gatt_char.call_args_list
    )
    await shutdown(c)


async def test_empty_mask_does_not_infer_capabilities(hass):
    c = runtime(hass)
    c.client.services.get_service.return_value = SimpleNamespace()
    c.client.read_gatt_char = AsyncMock(return_value=b"")
    await c.controller.async_discover_capabilities()
    assert not c.controller.controller_entity_discovery_complete
    assert c.controller.memory_slot_count == 0
    assert c.controller._capabilities.actuator_mask is None
    await shutdown(c)


async def test_native_memory_recall_is_bounded_and_sends_no_carpe_initial_burst(hass):
    from custom_components.adjustable_bed.beds.linak.protocol import LinakModelVariant

    c = runtime(hass, mask=0)
    c.controller._capabilities = replace(
        c.controller._capabilities, model_variant=LinakModelVariant.TD3
    )
    times = []

    async def record(*_args, **_kwargs):
        times.append(asyncio.get_running_loop().time())
        await asyncio.sleep(0.03)

    c.client.write_gatt_char.side_effect = record
    with virtual_clock():
        await c.controller.preset_memory(4)
    assert set(frames(c.client)) == {"4400"}
    assert set(frames(c.client)[:-1]) == {"4400"}
    assert round(times[1] - times[0], 3) == 0.13
    assert times[-1] - times[0] < 30
    c.client.write_gatt_char.reset_mock()
    await c.controller.program_memory(4)
    assert frames(c.client) == ["4500"]
    await shutdown(c)


async def test_native_paired_right_child_targets_only_its_link(hass):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers import device_registry as dr
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed import _async_ensure_paired_device_registry
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
    from custom_components.adjustable_bed.paired_devices import side_identifier

    left, right = runtime(hass), carpe_runtime(hass, address="AA:BB:CC:DD:EE:68")
    hass.config_entries.async_update_entry(
        right.entry, data={**left.entry.data, "address": right.address}
    )
    right._controller = TempurRelaxController(right)
    right.controller._capabilities = left.controller._capabilities
    entry = MockConfigEntry(domain=const.DOMAIN, data={"pair_id": "tempur-pair"})
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    pair = PairedBedCoordinator(
        hass, entry, {"left": left, "right": right}, connection_mode="concurrent"
    )
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = pair
    _async_ensure_paired_device_registry(hass, entry, pair)
    for receiver in (left, right):
        client = receiver.client
        async def connect(receiver=receiver, client=client):
            client.is_connected = True
            return True
        async def disconnect(reason="", receiver=receiver, client=client):
            client.is_connected = False
            return True
        receiver.async_connect = AsyncMock(side_effect=connect)
        receiver.async_disconnect = AsyncMock(side_effect=disconnect)
    child = dr.async_get(hass).async_get_child_device_by_identifier(
        side_identifier(pair, "right"), entry.entry_id
    )
    assert child is not None
    async_register_linak_services(hass)
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN,
            "linak_move_sections",
            {
                "device_id": [child.id],
                "sections": ["back", "legs"],
                "direction": "up",
                "duration_ms": 250,
            },
            blocking=True,
        )
    assert frames(left.client) == []
    assert frames(right.client) == ["3700"] * 3 + ["ff00"]
    await shutdown(left)
    await shutdown(right)


async def test_interrupted_massage_sequence_leaves_commanded_selection_unknown(hass):
    c = runtime(hass)
    c.handle_controller_state_updates(MASSAGE_SELECTION("back"))
    original = c.client
    replacement = MagicMock(
        is_connected=True,
        write_gatt_char=AsyncMock(),
        disconnect=AsyncMock(),
        stop_notify=AsyncMock(),
    )

    async def replace_link(*_args, **_kwargs):
        c._client = replacement

    original.write_gatt_char.side_effect = replace_link
    with virtual_clock(), pytest.raises(HomeAssistantError, match="connected"):
        await c.async_execute_controller_command(lambda ctrl: ctrl.massage_foot_toggle())
    assert frames(original) == ["8a00"]
    assert frames(replacement) == []
    assert c.controller_state.get(MASSAGE_SELECTION) is None
    await shutdown(c)


@pytest.mark.parametrize(
    "model,mask,up_frame,down_frame",
    [
        (LinakModelVariant.STANDARD, None, "0100", "0000"),
        (LinakModelVariant.ADVANCED, 0xE0, "0100", "0000"),
        (LinakModelVariant.ADVANCED, 0x01, "0100", "0000"),
        (LinakModelVariant.TD3, 0, "3700", "3400"),
    ],
)
async def test_native_presets_use_model_branch_not_selected_section_encoder(
    hass, model, mask, up_frame, down_frame
):
    c = runtime(hass, mask=mask)
    c.controller._capabilities = replace(c.controller._capabilities, model_variant=model)
    with virtual_clock():
        await c.controller.preset_both_up()
    assert set(frames(c.client)[:-1]) == {up_frame}
    assert frames(c.client)[-1] == ("fe00" if model is LinakModelVariant.TD3 else "ff00")
    c.client.write_gatt_char.reset_mock()
    with virtual_clock():
        await c.controller.preset_flat()
    assert set(frames(c.client)[:-1]) == {down_frame}
    assert frames(c.client)[-1] == ("fe00" if model is LinakModelVariant.TD3 else "ff00")
    await shutdown(c)


async def test_cancellation_in_massage_gap_invalidates_selection_before_next_toggle(hass):
    c = runtime(hass)
    in_gap = asyncio.Event()
    original_sleep = asyncio.sleep

    async def wait_in_gap(delay):
        if delay == 0.1:
            in_gap.set()
            await asyncio.Event().wait()
        else:
            await original_sleep(delay)

    with patch(
        "custom_components.adjustable_bed.beds.linak.tempur_relax.asyncio.sleep", wait_in_gap
    ):
        task = asyncio.create_task(
            c.async_execute_controller_command(lambda ctrl: ctrl.massage_head_toggle())
        )
        await in_gap.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert frames(c.client) == ["8900"]
    assert c.controller_state.get(MASSAGE_SELECTION) is None
    with virtual_clock():
        await c.async_execute_controller_command(lambda ctrl: ctrl.massage_head_toggle())
    assert frames(c.client)[-2:] == ["8900", "8c00"]
    assert c.controller_state.get(MASSAGE_SELECTION) == "back"
    await shutdown(c)


async def test_single_available_section_is_valid_but_two_section_action_is_not(hass):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.helpers import device_registry as dr

    c = runtime(hass, mask=0x08)
    c.entry.mock_state(hass, ConfigEntryState.LOADED)
    hass.data.setdefault(const.DOMAIN, {})[c.entry.entry_id] = c
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=c.entry.entry_id, identifiers={(const.DOMAIN, c.address)}
    )
    async_register_linak_services(hass)
    assert not c.controller.supports_simultaneous_movement
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN,
            "linak_move_sections",
            {"device_id": [device.id], "sections": ["base"], "direction": "up", "duration_ms": 250},
            blocking=True,
        )
    assert frames(c.client) == ["0700"] * 3 + ["ff00"]
    c.client.write_gatt_char.reset_mock()
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            const.DOMAIN,
            "linak_move_simultaneously",
            {
                "device_id": [device.id],
                "first_motor": "base",
                "first_direction": "up",
                "second_motor": "back",
                "second_direction": "up",
                "duration_ms": 250,
            },
            blocking=True,
        )
    assert frames(c.client) == []
    await shutdown(c)


@pytest.mark.parametrize(
    "model,mask,complete",
    [
        (LinakModelVariant.UNKNOWN, None, False),
        (LinakModelVariant.ADVANCED, None, True),
        (LinakModelVariant.UNKNOWN, None, True),
    ],
)
async def test_unresolved_capabilities_never_enable_declared_motor_fallback(
    hass, model, mask, complete
):
    c = runtime(hass)
    c.controller._capabilities = replace(
        c.controller._capabilities,
        model_variant=model,
        actuator_mask=mask,
        discovery_complete=complete,
    )
    assert c.controller.motor_control_specs == ()
    with pytest.raises(HomeAssistantError):
        await c.async_execute_controller_command(lambda ctrl: ctrl.move_back_up())
    with virtual_clock(), pytest.raises(HomeAssistantError):
        await c.async_execute_controller_command(lambda ctrl: ctrl.preset_flat())
    assert frames(c.client) == []
    await shutdown(c)


async def test_commanded_massage_selection_survives_routine_controller_recreation(hass):
    c = runtime(hass)
    with virtual_clock():
        await c.async_execute_controller_command(lambda ctrl: ctrl.massage_head_toggle())
    assert c.controller_state.get(MASSAGE_SELECTION) == "back"
    old = c.client
    c._client = MagicMock(
        is_connected=True,
        write_gatt_char=AsyncMock(),
        disconnect=AsyncMock(),
        stop_notify=AsyncMock(),
    )
    c._controller = await create_controller(c, "linak", "tempur_relax", None)
    assert c.controller_state.get(MASSAGE_SELECTION) == "back"
    await c.async_execute_controller_command(lambda ctrl: ctrl.massage_head_toggle())
    assert frames(old) == ["8900", "8c00"]
    assert frames(c.client) == ["8000"]
    assert c.controller_state.get(MASSAGE_SELECTION) == "off"
    await c.async_execute_controller_command(lambda ctrl: ctrl.reset_defaults())
    assert c.controller_state.get(MASSAGE_SELECTION) is None
    await shutdown(c)


@pytest.mark.parametrize("direction", ["open", "close"])
async def test_cached_cover_press_rechecks_current_connection_mask(hass, direction):
    from custom_components.adjustable_bed.cover import _cover_entities_for

    c = runtime(hass)
    cover = next(
        entity for entity in _cover_entities_for(hass, c) if entity.entity_description.key == "head"
    )
    cover.hass = hass
    cover.async_write_ha_state = MagicMock()
    snapshot = c.controller._capabilities
    c._controller = TempurRelaxController(c)
    c.controller._capabilities = replace(snapshot, actuator_mask=0xC0)
    with pytest.raises(HomeAssistantError):
        await (cover.async_open_cover() if direction == "open" else cover.async_close_cover())
    assert frames(c.client) == []
    await shutdown(c)


@pytest.mark.parametrize("mask", [None, 0], ids=["standard", "td3"])
async def test_resolved_standard_and_td3_keep_declared_axis_presses(hass, mask):
    c = runtime(hass, mask=mask)
    with virtual_clock():
        await c.controller.move_back_up()
    assert set(frames(c.client)[:-1]) == {"0b00"}
    assert frames(c.client)[-1] == ("fe00" if mask == 0 else "ff00")
    await shutdown(c)
