"""FurniMove source-vector encoding, callers, state and cancellation."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from custom_components.adjustable_bed.beds.furnimove import (
    CSS_FEEDBACK,
    DOT_FEEDBACK,
    DOT_WRITE,
    FEEDBACK,
    GAP_NAME,
    INFO,
    RF_NAME,
    WRITE,
    FurniMoveController,
    build_furnimove_command,
    combine_furnimove_commands,
    validate_furnimove_name,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.furnimove_profiles import FurniMoveAction as Action


def char(uuid: str, properties=("write",)):
    return MagicMock(uuid=uuid, properties=list(properties))


def make_controller(handset_id="82417", *, characteristics=None) -> FurniMoveController:
    coordinator = MagicMock()
    coordinator.address = "AA:BB:CC:DD:EE:FF"
    coordinator.cancel_command = asyncio.Event()
    coordinator.controller_state = {}
    coordinator.handle_controller_state_update.side_effect = (
        lambda key, value: coordinator.controller_state.update({key: value})
    )
    coordinator.motor_pulse_count = 2
    coordinator.client = MagicMock(
        is_connected=True,
        services=[
            MagicMock(characteristics=characteristics or [char(WRITE), char(FEEDBACK, ("notify",))])
        ],
    )
    coordinator.client.write_gatt_char = AsyncMock()
    coordinator.client.read_gatt_char = AsyncMock(return_value=bytes(10))
    coordinator.client.start_notify = AsyncMock()
    coordinator.client.stop_notify = AsyncMock()
    return FurniMoveController(coordinator, handset_id=handset_id)


def written(controller: FurniMoveController) -> list[str]:
    return [entry.args[1].hex() for entry in controller.client.write_gatt_char.call_args_list]


async def fast_controller(handset_id="82417", **kwargs) -> FurniMoveController:
    controller = make_controller(handset_id, **kwargs)
    await controller.async_discover_capabilities()
    controller._pause = AsyncMock(return_value=True)
    return controller


@pytest.mark.parametrize(
    ("keycode", "old", "dot", "expected"),
    [
        ("0x00000001", False, False, "040200000001"),
        ("0x00000001", True, True, "e5fe160000000105"),
        ("0x00000001", False, True, "05020000000100"),
        (None, False, False, "040200000000"),
        (None, True, False, "e5fe160000000006"),
        ("XX12", False, False, "040212000000"),
        ("0xGG", False, False, "0402ef000000"),
        ("0x\uff21\uff26", False, False, "0402af000000"),
        ("0x0102030405", True, False, "e5fe1601020304f7"),
        ("0x0102030405", False, True, "05020102030400"),
    ],
)
def test_literal_hex_converter(keycode, old, dot, expected) -> None:
    assert build_furnimove_command(keycode, old=old, dot=dot).hex() == expected


def test_composite_or_and_gateway_checksum() -> None:
    a = build_furnimove_command("0x00000001", old=True)
    b = build_furnimove_command("0x00000004", old=True)
    assert combine_furnimove_commands([a, b], old=True).hex() == "e5fe160000000501"
    assert combine_furnimove_commands([]) is None
    with pytest.raises(IndexError):
        combine_furnimove_commands([a, b[:3]])
    with pytest.raises(IndexError):
        build_furnimove_command("0x123")


@pytest.mark.parametrize(
    ("uuids", "selected", "old", "dot"),
    [
        ([RF_NAME, DOT_WRITE], DOT_WRITE, True, True),
        ([DOT_WRITE, WRITE], WRITE, False, True),
        ([RF_NAME, CSS_FEEDBACK, WRITE], WRITE, False, False),
        ([CSS_FEEDBACK, RF_NAME, WRITE], WRITE, True, False),
    ],
)
async def test_gatt_selection_order_and_rf_precedence(uuids, selected, old, dot) -> None:
    controller = await fast_controller(characteristics=[char(uuid) for uuid in uuids])
    assert controller.control_characteristic_uuid == selected
    assert controller.protocol_diagnostics["old_protocol"] is old
    assert controller.protocol_diagnostics["dot_protocol"] is dot
    frame = controller._frame(Action("a", "memory", "0x00000001"))
    assert frame[0] == (0xE5 if old else 5 if dot else 4)


async def test_discovery_requires_known_writable_role() -> None:
    for characteristics in ([char(CSS_FEEDBACK)], [char(WRITE, ("read",))]):
        with pytest.raises(ValueError):
            await make_controller(characteristics=characteristics).async_discover_capabilities()
    controller = await fast_controller(characteristics=[char(WRITE, ("write-without-response",))])
    await controller.write_command(b"test")
    assert controller.client.write_gatt_char.call_args.kwargs["response"] is False


async def test_duplicate_uuid_uses_last_actual_characteristic_not_uuid_lookup() -> None:
    first, last = char(WRITE), char(WRITE)
    controller = await fast_controller(characteristics=[first, last])
    await controller.move_back_up()
    assert all(entry.args[0] is last for entry in controller.client.write_gatt_char.call_args_list)
    assert (
        controller._coordinator.record_command_trace.call_args.kwargs["characteristic_handle"]
        == last.handle
    )


async def test_light_exposure_is_toggle_and_unpublished_initial_boolean() -> None:
    controller = await fast_controller()
    assert controller.supports_lights and controller.supports_light_toggle_control
    assert not controller.supports_discrete_light_control
    assert not controller.supports_light_state_feedback
    assert not any(
        entry.args[0] == "furnimove_ubl"
        for entry in controller._coordinator.handle_controller_state_update.call_args_list
    )
    assert controller.stale_motor_entity_keys == frozenset({"stair"})


async def test_axes_main_release_tail_and_offline_no_stop_frame(monkeypatch) -> None:
    controller = await fast_controller("93558")
    assert controller.simultaneous_movement_axes == ("head", "feet")
    # The mocked pauses do not advance time, so fix the release deadline's clock too.
    loop = asyncio.get_running_loop()
    started = loop.time()
    with monkeypatch.context() as clock:
        clock.setattr(loop, "time", lambda: started)
        await controller.move_head_up()
    assert written(controller) == ["040200000001"] * 2 + ["040200000000"] * 2
    assert [entry.args[0] for entry in controller._pause.call_args_list[-2:]] == [100, 100]
    with pytest.raises(ValueError):
        await controller.move_back_up()
    offline = await fast_controller("00000")
    await offline.move_back_up()
    assert written(offline) == ["040200000001"] * 2
    await offline.stop_all()
    assert len(written(offline)) == 2


async def test_cancellation_uses_fresh_cleanup_and_dot_query_without_affirm() -> None:
    controller = await fast_controller(characteristics=[char(DOT_WRITE)])

    async def cancel_on_write(*args, **kwargs):
        controller._coordinator.cancel_command.set()

    controller.client.write_gatt_char.side_effect = cancel_on_write
    await controller.move_back_up()
    assert written(controller) == ["05020000000100", "05020000000000"]
    assert controller._coordinator.cancel_command.is_set()


async def test_dot_query_only_on_ubl_main_release() -> None:
    controller = await fast_controller(characteristics=[char(DOT_WRITE)])
    await controller.lights_toggle()
    assert written(controller) == ["05020002000000"] * 2 + ["05020000000000", "00b0"]


async def test_task_cancellation_still_releases() -> None:
    controller = await fast_controller()
    original = controller.write_command

    async def write(*args, **kwargs):
        if "cancel_event" not in kwargs:
            raise asyncio.CancelledError
        await original(*args, **kwargs)

    controller.write_command = write
    with pytest.raises(asyncio.CancelledError):
        await controller.move_back_up()
    assert written(controller) == ["040200000000"] * 2


async def test_memory_program_selected_slot_timer_and_dot_omission() -> None:
    controller = await fast_controller(characteristics=[char(DOT_WRITE)])
    controller.profile = replace(
        controller.profile,
        actions=(
            Action("MemoSave", "memory-update", "0x00010000", 400, 200),
            Action("Arbitrary slot A", "memory", "0x00001000"),
            Action("Arbitrary slot B", "memory", "0x00002000"),
            Action("DisobeyStandbyTime", "utility", "0x00000000"),
        ),
    )
    assert controller.memory_slot_names == ("Arbitrary slot A", "Arbitrary slot B")
    await controller.program_memory(2)
    assert written(controller) == ["040200010000"] * 3 + ["040200002000"]
    assert controller._pause.call_args_list == [call(200), call(200), call(0), call(400), call(200)]
    controller.client.write_gatt_char.reset_mock()
    await controller.preset_memory(1)
    assert written(controller) == ["05020000100000"] * 2 + ["05020000000000"]


async def test_cancelled_save_never_writes_selected_slot() -> None:
    controller = await fast_controller()
    controller.profile = replace(
        controller.profile,
        actions=(
            Action("MemoSave", "memory-update", "0x00010000", 400, 200),
            Action("Slot", "memory", "0x00001000"),
        ),
    )

    async def cancel(*args, **kwargs):
        controller._coordinator.cancel_command.set()

    controller.client.write_gatt_char.side_effect = cancel
    await controller.program_memory(1)
    assert written(controller) == ["040200010000"]


@pytest.mark.parametrize("consumer", ["program", "massage", "widget"])
async def test_dot_cancel_then_stop_does_not_append_wrong_main_release(consumer) -> None:
    controller = await fast_controller("12234", characteristics=[char(DOT_WRITE)])

    async def cancel_on_write(*args, **kwargs):
        controller._coordinator.cancel_command.set()

    controller.client.write_gatt_char.side_effect = cancel_on_write
    if consumer == "program":
        await controller.program_memory(1)
    elif consumer == "massage":
        await controller.set_massage_intensity("head", 1)
    else:
        row = next(
            i for i, value in enumerate(controller.profile.actions) if value.action == "Flat"
        )
        await controller.async_execute_furnimove_action(row, consumer="widget")
    frames = written(controller)
    await controller.stop_all()
    assert written(controller) == frames
    assert all(frame.startswith("0402") for frame in frames)
    if consumer != "program":
        assert frames[-1] == "040200000000"


async def test_failed_consumer_cleanup_is_retryable_with_original_dot_omission() -> None:
    controller = await fast_controller("12234", characteristics=[char(DOT_WRITE)])
    attempts = 0

    async def fail_release(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            controller._coordinator.cancel_command.set()
        if attempts == 2:
            raise ConnectionError("release failed")

    controller.client.write_gatt_char.side_effect = fail_release
    with pytest.raises(ConnectionError):
        await controller.set_massage_intensity("head", 1)
    assert not controller._cleanup_done
    await controller.stop_all()
    assert written(controller) == ["040200000800", "040200000000", "040200000000"]


async def test_completed_cleanup_consumed_once_then_standalone_stop_uses_main() -> None:
    controller = await fast_controller()
    await controller.move_back_up()
    frames = written(controller)
    await controller.stop_all()
    assert written(controller) == frames
    await controller.stop_all()
    assert written(controller) == frames + ["040200000000"] * 2


async def test_utilities_missing_sync_guard_and_functioning_mode_default_dot_false() -> None:
    controller = await fast_controller(characteristics=[char(DOT_WRITE)])
    controller.profile = replace(
        controller.profile,
        actions=(
            Action("ChildLock", "unknown", "0x04000000", 200, 100),
            Action("DisobeyStandbyTime", "utility", "0x00000000"),
        ),
    )
    await controller.child_lock_toggle()
    assert written(controller) == ["05020400000000"] * 2
    controller.profile = replace(
        controller.profile,
        actions=controller.profile.actions
        + (
            Action("Sync", "unknown", "0x10000000", 200, 100),
            Action("SwitchToPH", "unknown", "0x10000000", 200, 100),
            Action("SwitchToPR", "unknown", "0x20000000", 200, 100),
        ),
    )
    controller.client.write_gatt_char.reset_mock()
    await controller.set_control_mode_press_and_release()
    assert written(controller) == ["040220000000"] * 2 + ["040200000000"]
    assert controller.protocol_diagnostics["furnimove_control_mode"] == "press_and_release"


async def test_sync_finish_comparison_uses_dot_false_and_does_not_confirm_hardware() -> None:
    controller = await fast_controller(characteristics=[char(WRITE)])
    controller.profile = replace(
        controller.profile,
        actions=(
            Action("Sync", "utility", "0x10000000", 100, 100),
            Action("DisobeyStandbyTime", "utility", "0x00000000"),
        ),
    )
    await controller.sync_positions()
    assert controller.protocol_diagnostics["furnimove_function_result"] == "feedback_unchanged"
    assert controller.protocol_diagnostics["furnimove_sync"] is False
    controller._dot = True
    await controller.sync_positions()
    assert controller.protocol_diagnostics["furnimove_function_result"] == "completed"
    assert controller.protocol_diagnostics["furnimove_sync"] is False


def generic(bits: int) -> bytes:
    return b"\x08\x0b" + bits.to_bytes(4, "big") * 2


@pytest.mark.parametrize("rf", [False, True])
def test_initial_off_feedback_publishes_once_and_invalid_packets_remain_unknown(rf):
    controller = make_controller()
    if rf:
        controller._rf_name = char(RF_NAME)
    controller._parse_feedback(bytes(9))
    controller._parse_feedback(bytes(10))
    assert controller._coordinator.controller_state == {}
    feedback = bytes.fromhex("e5fe0714020000000000") if rf else generic(0)
    controller._parse_feedback(feedback)
    assert controller._coordinator.controller_state == {
        "furnimove_ubl": False,
        "furnimove_sync": False,
        "furnimove_child_lock": False,
    }
    controller._coordinator.handle_controller_state_update.reset_mock()
    controller._parse_feedback(feedback)
    controller._coordinator.handle_controller_state_update.assert_not_called()


def test_generic_rf_cu170_and_dot_state_parser_order() -> None:
    controller = make_controller()
    controller._parse_feedback(generic(0x14020000))
    assert all(
        controller.protocol_diagnostics["furnimove_" + key] is True
        for key in ("ubl", "sync", "child_lock")
    )
    controller._coordinator.handle_controller_state_update.reset_mock()
    controller._parse_feedback(generic(0x14020000))
    controller._parse_feedback(bytes(9))
    assert not controller._coordinator.handle_controller_state_update.called
    controller._rf_name = char(RF_NAME)
    controller._parse_feedback(bytes.fromhex("e5fe0714020000000000"))
    assert all(
        controller.protocol_diagnostics["furnimove_" + key] is False
        for key in ("ubl", "sync", "child_lock")
    )
    controller._parse_feedback(bytes.fromhex("e6fe0600040000000000"))
    assert controller.protocol_diagnostics["furnimove_child_lock"] is True
    controller._state["furnimove_model"] = "CU170"
    controller._state["furnimove_sync"] = True
    controller._parse_feedback(bytes.fromhex("ffff0000021400000204"))
    assert controller.protocol_diagnostics["furnimove_sync"] is True  # byte9=4 retain
    assert controller.protocol_diagnostics["furnimove_ubl"] is True
    assert controller.protocol_diagnostics["furnimove_child_lock"] is True
    controller._dot = True
    controller._coordinator.handle_controller_state_update.reset_mock()
    controller._parse_feedback(bytes.fromhex("ffff0000021400000204") + bytes(5))
    assert controller._coordinator.handle_controller_state_update.call_args_list[:2] == [
        call("furnimove_ubl", False),
        call("furnimove_ubl", True),
    ]


def test_feedback_transport_gate_and_cu170_precedence() -> None:
    controller = make_controller()
    controller._parse_feedback(bytes.fromhex("05fe0600020000000000"))
    assert controller.protocol_diagnostics["furnimove_ubl"] is False
    controller._rf_name = char(RF_NAME)
    controller._parse_feedback(generic(0x00020000))
    assert controller.protocol_diagnostics["furnimove_ubl"] is False
    controller._parse_feedback(bytes.fromhex("05fe0600020000000000"))
    assert controller.protocol_diagnostics["furnimove_ubl"] is True
    controller._state["furnimove_model"] = "CU170"
    controller._parse_feedback(bytes.fromhex("080b0000020000000200"))
    assert controller.protocol_diagnostics["furnimove_ubl"] is True


def test_recreated_controller_retains_runtime_feedback_without_publishing_new_proof() -> None:
    old = make_controller()
    old._coordinator.controller_state = {
        "furnimove_ubl": True,
        "furnimove_sync": True,
        "furnimove_child_lock": "true",
        "furnimove_massage_program": 3,
    }
    restored = FurniMoveController(old._coordinator, handset_id="82417")
    assert restored.protocol_diagnostics["furnimove_ubl"] is True
    assert restored.protocol_diagnostics["furnimove_sync"] is True
    assert restored.protocol_diagnostics["furnimove_child_lock"] is False
    assert restored.protocol_diagnostics["furnimove_massage_program"] == 3
    assert "program" not in restored.furnimove_local_state
    old._coordinator.handle_controller_state_update.assert_not_called()
    restored._parse_feedback(generic(0))
    assert old._coordinator.handle_controller_state_update.call_args_list == [
        call("furnimove_ubl", False),
        call("furnimove_sync", False),
        call("furnimove_child_lock", False),
    ]


async def test_factory_queue_null_keys_order_and_target_intensity() -> None:
    controller = await fast_controller("12234", characteristics=[char(DOT_WRITE)])
    head = controller.build_massage_queue("head", 2)
    assert [frame.hex() for frame in head] == ["040200800000", "040200000000"] * 3
    both = controller.build_massage_queue("both", 1)
    assert [frame.hex() for frame in both] == [
        "040200000800",
        "040200000000",
        "040200400000",
        "040200000000",
    ]
    await controller.set_massage_intensity("head", 2)
    assert written(controller) == [frame.hex() for frame in head]
    assert controller._pause.call_args_list == [call(150)] * 5
    controller.profile = replace(
        controller.profile,
        actions=(Action("MassageAll", "massage-function", "0x00200000", intensity=4),),
    )
    assert [frame.hex() for frame in controller.build_massage_queue("both", 1)] == [
        "040200000000"
    ] * 4
    with pytest.raises(ValueError):
        controller.validate_furnimove_action(0)


async def test_massage_program_stop_variants_and_local_countdown_no_wire() -> None:
    controller = await fast_controller("12234", characteristics=[char(DOT_WRITE)])
    await controller.massage_off()
    assert written(controller) == ["040200000400"] * 2
    controller.client.write_gatt_char.reset_mock()
    controller._pause.reset_mock()
    await controller.massage_off()
    assert written(controller) == ["040200000400"] * 2
    assert controller._pause.call_args_list == [call(150, controller._pause.call_args.args[1])]
    controller._state["furnimove_massage_intensity"] = 5
    controller.client.write_gatt_char.reset_mock()
    await controller.massage_off()
    assert written(controller) == ["040200000400"]
    assert controller._pause.call_args.args[0] == 250
    controller.client.write_gatt_char.reset_mock()
    await controller.set_furnimove_massage_program(4)
    assert written(controller)[-2:] == ["040204000000", "040200000000"]
    controller.client.write_gatt_char.reset_mock()
    await controller.set_massage_timer(30)
    assert written(controller) == []
    assert controller.get_massage_state()["timer"] == 30
    assert not controller.supports_massage_timer


@pytest.mark.parametrize(
    ("handset", "missing"),
    [(handset, program) for handset in ("90167", "91983", "93558") for program in (1, 2, 3)]
    + [("90916", 4), ("91914", 4)],
)
async def test_absent_massage_program_rejected_without_writes_or_state_changes(handset, missing):
    controller = await fast_controller(handset)
    state = controller.protocol_diagnostics.copy()
    with pytest.raises(ValueError, match="absent"):
        await controller.set_furnimove_massage_program(missing)
    assert not written(controller)
    assert controller.protocol_diagnostics == state


@pytest.mark.parametrize("handset", ["90167", "91983", "93558"])
async def test_absent_wave_intensity_rejected_but_wave_program_remains_available(handset):
    controller = await fast_controller(handset)
    assert controller.massage_intensity_zones == ["head", "foot", "all"]
    state = controller.protocol_diagnostics.copy()
    with pytest.raises(ValueError, match="absent"):
        controller.build_massage_queue("wave", 1)
    with pytest.raises(ValueError, match="Unsupported"):
        await controller.set_massage_intensity("wave", 1)
    assert not written(controller)
    assert controller.protocol_diagnostics == state
    await controller.set_furnimove_massage_program(4)
    assert written(controller)[-2] == controller._frame(controller.profile.first("MassagerWave")).hex()


@pytest.mark.parametrize("handset", ["90167", "91983", "93558"])
@pytest.mark.parametrize("direction", ["up", "down"])
async def test_absent_wave_intensity_step_preserves_program_state(handset, direction):
    controller = await fast_controller(handset)
    await controller.set_furnimove_massage_program(4)
    await controller.set_furnimove_massage_program(4)
    state = controller.protocol_diagnostics.copy()
    assert controller.get_massage_state()["intensity"] == 2
    controller.client.write_gatt_char.reset_mock()
    controller._coordinator.handle_controller_state_update.reset_mock()
    controller._pause.reset_mock()

    if direction == "up":
        await controller.massage_intensity_up()
    else:
        await controller.massage_intensity_down()

    assert not written(controller)
    assert controller.protocol_diagnostics == state
    controller._coordinator.handle_controller_state_update.assert_not_called()
    controller._pause.assert_not_called()


@pytest.mark.parametrize(
    ("handset", "programs"),
    [("90167", [4, 4]), ("91983", [4, 4]), ("93558", [4, 4]),
     ("90916", [1, 2, 3, 1]), ("91914", [1, 2, 3, 1])],
)
async def test_mode_step_cycles_only_available_massage_programs(handset, programs):
    controller = await fast_controller(handset)
    assert controller.supports_massage_mode_step_control
    for program in programs:
        await controller.massage_mode_step()
        assert controller.get_massage_state()["mode"] == program
        name = f"Massager{program}" if program < 4 else "MassagerWave"
        assert written(controller)[-2] == controller._frame(controller.profile.first(name)).hex()


async def test_massage_handset_without_program_rows_hides_mode_step():
    controller = await fast_controller("12234")
    controller.profile = replace(
        controller.profile,
        actions=tuple(row for row in controller.profile.actions
                      if row.action not in {"Massager1", "Massager2", "Massager3", "MassagerWave"}),
    )
    assert controller.supports_massage
    assert not controller.supports_massage_mode_step_control
    with pytest.raises(ValueError, match="no massage programs"):
        await controller.massage_mode_step()
    assert not written(controller)


async def test_local_state_restore_selects_wire_consumer_without_hardware_claim() -> None:
    controller = await fast_controller("12234")
    controller.restore_furnimove_local_state(
        {"duration_minutes": 20, "running": True, "zone": "wave", "intensity": 2}
    )
    assert written(controller) == []
    assert controller.get_massage_state()["source"] == "local_app_state"
    assert controller.furnimove_local_state == {
        "duration_minutes": 20,
        "running": True,
        "zone": "wave",
        "intensity": 2,
    }
    await controller.massage_intensity_up()
    assert written(controller) == ["040280000000", "040200000000"]
    assert controller.furnimove_local_state["intensity"] == 3
    await controller.massage_off()
    assert controller.furnimove_local_state == {"duration_minutes": 20}
    with pytest.raises(ValueError):
        controller.restore_furnimove_local_state(
            {"duration_minutes": 15, "running": True, "zone": "head", "intensity": 99}
        )
    assert controller.furnimove_local_state == {"duration_minutes": 20}


async def test_widget_uses_fixed_once_timing_and_dot_false() -> None:
    controller = await fast_controller(characteristics=[char(DOT_WRITE)])
    flat_index = next(i for i, row in enumerate(controller.profile.actions) if row.action == "Flat")
    await controller.async_execute_furnimove_action(flat_index, consumer="widget")
    assert written(controller) == ["0402000000aa"] * 100 + ["040200000000"]
    assert controller._pause.call_args_list == [call(200)] * 100
    with pytest.raises(ValueError):
        controller.validate_furnimove_action(flat_index, duration_ms=50, consumer="widget")


async def test_arbitrary_preset_duplicate_labels_and_no_invented_dead_massage() -> None:
    controller = await fast_controller()
    controller.profile = replace(
        controller.profile,
        actions=(
            Action("Custom", "memory-preset", "0x00001000"),
            Action("Custom", "memory-preset", "0x00002000"),
            Action("MassageAll", "massage-function", "0x00000001"),
            Action("DisobeyStandbyTime", "utility", "0x00000000"),
        ),
    )
    assert [spec.row_index for spec in controller.furnimove_action_specs] == [0, 1]
    assert [spec.key for spec in controller.controller_button_specs] == [
        "furnimove_action_0",
        "furnimove_action_1",
    ]
    await controller.async_execute_furnimove_action(1)
    assert written(controller) == ["040200002000"] * 2 + ["040200000000"]


async def test_rename_original_text_rf_precedence_and_utf16_validation() -> None:
    controller = await fast_controller(characteristics=[char(WRITE), char(GAP_NAME), char(RF_NAME)])
    await controller.rename_device("  My Bed  ")
    assert controller.client.write_gatt_char.call_args.args == (controller._rf_name, b"  My Bed  ")
    validate_furnimove_name("😀" * 9)
    for name in ("  ", "😀" * 10, "x" * 19):
        with pytest.raises(ValueError):
            validate_furnimove_name(name)


async def test_notification_info_query_and_session_cleanup_preserves_boolean_state(
    monkeypatch,
) -> None:
    characteristics = [
        char(DOT_WRITE),
        char(DOT_FEEDBACK, ("notify",)),
        char(CSS_FEEDBACK, ("indicate",)),
    ] + [char(uuid, ("read",)) for uuid in INFO.values()]
    controller = make_controller(characteristics=characteristics)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    controller.client.read_gatt_char.side_effect = [b"CU170", b"HW", b"SW", b"FW"]
    await controller.start_notify()
    assert written(controller) == ["00b0"]
    assert controller.protocol_diagnostics["furnimove_model"] == "CU170"
    assert len(controller.client.start_notify.call_args_list) == 2
    controller._state["furnimove_ubl"] = True
    await controller.stop_notify()
    assert controller.protocol_diagnostics["furnimove_ubl"] is True
    assert controller.protocol_diagnostics["furnimove_model"] == "HE150"
    assert controller.protocol_diagnostics["dot_protocol"] is False
    with pytest.raises(ValueError):
        _ = controller.control_characteristic_uuid


async def test_actual_coordinator_starts_furnimove_notifications_with_angles_disabled(
    monkeypatch,
) -> None:
    controller = make_controller(characteristics=[char(DOT_WRITE), char(DOT_FEEDBACK, ("notify",))])
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    coordinator = SimpleNamespace(
        _controller=controller,
        _disable_angle_sensing=True,
        _address="AA:BB:CC:DD:EE:FF",
        _bed_type="furnimove",
    )
    await AdjustableBedCoordinator.async_start_notify(coordinator)
    controller.client.start_notify.assert_awaited_once()
    assert controller._notify_callback is None
    assert written(controller) == ["00b0"]


async def test_dot_write_notification_property_does_not_subscribe(monkeypatch) -> None:
    dot_write = char(DOT_WRITE, ("write", "notify", "indicate"))
    ordinary_write = char(WRITE, ("write", "notify"))
    feedback = char(DOT_FEEDBACK, ("notify",))
    controller = make_controller(characteristics=[ordinary_write, dot_write, feedback])
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    await controller.start_notify()
    assert controller._write_characteristic is dot_write
    assert controller.protocol_diagnostics["dot_protocol"] is True
    assert [entry.args[0] for entry in controller.client.start_notify.call_args_list] == [
        ordinary_write,
        feedback,
    ]
    assert controller.client.write_gatt_char.call_args.args == (dot_write, b"\x00\xb0")
