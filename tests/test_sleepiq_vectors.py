"""SleepIQ frozen frames, parser quirks and direct-bed admission."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.beds.sleep_number.commands import COMMANDS, format_command
from custom_components.adjustable_bed.beds.sleep_number.mcr import SleepNumberMcrController
from custom_components.adjustable_bed.beds.sleep_number.mcr_protocol import decode_massage
from custom_components.adjustable_bed.codec import sleepiq as codec
from custom_components.adjustable_bed.profiles.sleepiq import FUZION
from tests.sleepiq_vectors import FUZION as FUZION_LITERALS
from tests.sleepiq_vectors import MCR
from tests.test_sleep_number_fuzion import SESSION, controller_with_client


@pytest.mark.parametrize("bamkey,skipped", [("ACTS", 1), ("SYCG", 0)])
async def test_prewrite_cancellation_counts_only_required_fuzion_frames(bamkey, skipped) -> None:
    from custom_components.adjustable_bed.command_scheduler import CommandContext, CommandKind

    controller, client = controller_with_client()
    cancel = controller._coordinator.cancel_command
    cancel.set()
    context = CommandContext(
        scheduler_token=object(),
        cancel_event=cancel,
        admitted_stop_epoch=0,
        intent_id="fuzion",
        kind=CommandKind.COMMAND,
        group_id=None,
        resources=frozenset({"*"}),
    )
    with (
        patch(
            "custom_components.adjustable_bed.command_scheduler.current_command_context",
            return_value=context,
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await controller._send_bamkey_command(bamkey)
    assert context.frames_skipped == skipped
    assert context.frames_written == 0
    client.write_gatt_char.assert_not_awaited()


def test_frozen_fuzion_commands() -> None:
    frames = {
        FUZION.command("ACHA").hex(),
        FUZION.command("ACTS", "left", "head", "100").hex(),
        FUZION.command(
            "BAMG", '[{"bamkey":"ACTG","args":"left head"},{"bamkey":"ACTM","args":""}]'
        ).hex(),
    }
    assert frames == FUZION_LITERALS
    for literal in frames:
        frame = bytes.fromhex(literal)
        assert codec.fuzion(codec.parse_fuzion(frame)) == frame
        corrupt = frame[:-1] + bytes((frame[-1] ^ 1,))
        with pytest.raises(ValueError, match="CRC"):
            codec.parse_fuzion(corrupt)


def test_frozen_mcr_commands() -> None:
    frames = set()
    for node, op, sub, payload, client, bed in (
        (2, 0, 0, bytes.fromhex("0102030405060708"), 0, 0),
        (66, 21, 0, b"\x04\0", 0x1234, 0x5678),
        (82, 27, 0, b"MFHL110", 0x1234, 0x5678),
    ):
        raw = codec.mcr(
            command_type=node,
            status=node,
            function_code=op,
            side=sub,
            payload=payload,
            client_address=client,
            sub_address=bed,
        )
        frames.add(raw.hex())
        assert codec.parse_mcr(raw).payload == payload
        for split in range(1, len(raw)):
            merger = codec.McrMerger()
            assert merger.feed(raw[:split]) is None
            assert merger.feed(raw[split:]) == raw
        assert codec.McrMerger().feed(raw + raw) == raw
        assert codec.McrMerger().feed(raw[:2] + b"\x16" + raw[2:]) == raw
    assert frames == MCR
    overflow = codec.mcr(
        command_type=255,
        status=255,
        function_code=255,
        side=15,
        payload=b"\xff" * 15,
        sub_address=65535,
        client_address=65535,
    )
    assert codec.parse_mcr(overflow) is None


def test_response_replace_first_and_group_member_quirks() -> None:
    assert codec.bamkey_values("PASS:PASS:ACK", 1) == [""]
    assert codec.bamkey_values('["PASS:100","PASS:0 1 0 1","FAIL:0"]', 1) == [
        '["100","PASS:0 1 0 1","FAIL:0"]'
    ]
    with pytest.raises(ValueError, match="expected 0"):
        codec.bamkey_values("PASS:unexpected", 0)
    result = decode_massage(bytes.fromhex("0001020300ffff0080ff7f"), "left")
    assert [result[f"massage_{name}_timer_left"] for name in ("head", "foot", "mode")] == [
        -1,
        -32768,
        32767,
    ]


def test_diagnostics_disallows_network_upload_or_arbitrary_tests() -> None:
    spec, args = format_command(
        "run_diagnostics", {"diagnostics": {"tests": ["actuator-test"], "group": "Base"}}
    )
    assert spec.key == "DSRS"
    request = json.loads(args[0])
    assert request["uploadToCloud"] is False
    assert request["metadata"]["clientLogin"] == ""
    assert request["testIds"] == [{"testId": "actuator-test"}]
    for test in ("connectivity-test", "ble-wifi-test", "unknown-test"):
        with pytest.raises(ValueError):
            format_command("run_diagnostics", {"diagnostics": {"tests": [test], "group": "Base"}})
    with pytest.raises(ValueError):
        format_command(
            "run_diagnostics",
            {"diagnostics": {"tests": ["actuator-test"], "group": "Base", "uploadToCloud": True}},
        )
    assert "get_system_status" not in COMMANDS
    spec, args = format_command("reset_articulation_presets", {"side": "right", "preset": "all"})
    assert (spec.key, args) == ("ACFR", ("right", "all"))


async def test_queued_fuzion_write_cannot_follow_replaced_link() -> None:
    controller, client = controller_with_client()
    await controller.start_notify()
    await controller.ble_lock.acquire()
    task = asyncio.create_task(controller._send_bamkey_command("ACHA"))
    await asyncio.sleep(0)
    controller._coordinator.client = MagicMock(is_connected=True)
    controller.ble_lock.release()
    with pytest.raises(ConnectionError, match="ended BLE session"):
        await task
    client.write_gatt_char.assert_not_awaited()


async def test_ended_notification_subscription_cannot_signal_new_session() -> None:
    controller, client = controller_with_client()
    await controller.start_notify()
    callback = client.start_notify.await_args.args[1]
    await controller.stop_notify()
    await controller.start_notify()
    callback(None, bytearray(SESSION))
    assert controller._readback_hint_queue.empty()


async def test_missing_fuzion_role_prevents_auth_or_subscription() -> None:
    controller, client = controller_with_client()
    client.services.get_characteristic.return_value.properties = ["read"]
    session = MagicMock()
    session.async_start_notify = AsyncMock()
    with pytest.raises(BleakError, match="GATT role"):
        await controller.async_on_connect(session)
    session.async_start_notify.assert_not_awaited()
    client.read_gatt_char.assert_not_awaited()


async def test_mcr_rejects_unbound_control_before_writes() -> None:
    coordinator = MagicMock()
    coordinator.cancel_command = asyncio.Event()
    controller = SleepNumberMcrController(coordinator, client_identifier=1)
    with pytest.raises(ConnectionError, match="has not bound"):
        await controller._mcr_request(0x42, 0x15, payload=b"\x04\0")
    coordinator.client.write_gatt_char.assert_not_called()


@pytest.mark.parametrize("cancel_count", [1, 2, 3])
async def test_fragmented_fuzion_buffer_finishes_before_cancellation_returns(
    cancel_count: int,
) -> None:
    controller, client = controller_with_client()
    await controller.start_notify()
    started, release = asyncio.Event(), asyncio.Event()
    chunks: list[bytes] = []

    async def write(_uuid, chunk, *, response):
        chunks.append(chunk)
        if len(chunks) == 1:
            started.set()
            await release.wait()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(controller._send_bamkey_command("ACTS", "left", "head", "100"))
    await started.wait()
    for _ in range(cancel_count):
        task.cancel()
        await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert b"".join(chunks).hex() in FUZION_LITERALS
    assert not controller._transaction_lock.locked()


async def test_presence_flags_do_not_enable_missing_side_modules() -> None:
    controller, _client = controller_with_client()
    config = [
        "dual",
        "yes",
        "yes",
        "no",
        "yes",
        "heat_cool",
        "yes",
        "yes",
        "yes",
        "yes",
        "yes",
        "yes",
        "yes",
        "yes",
        "yes",
        "yes",
    ]
    controller._ensure_notifications_started = AsyncMock()
    controller._send_bamkey_command = AsyncMock(
        side_effect=[
            config,
            ["0", "35", "50"],
            ["0", "40", "55"],
            ["0"],
            ["true"],
            ["off", "0"],
            ["1"],
            ["false"],
            ["low", "30", "60"],
            ["active"],
            ["0"],
            ["0"],
        ]
    )
    await controller.query_config()
    assert controller.footwarming_climate_sides == ("right",)
    assert controller.thermal_climate_sides == ("left",)
    assert all(
        spec.hold is None and spec.requires_confirmation
        for spec in controller.controller_button_specs
    )
    assert len({spec.key for spec in controller.controller_switch_specs}) == len(
        controller.controller_switch_specs
    )


def test_group_member_failure_is_null_without_changing_other_slots() -> None:
    assert codec.grouped_values('["PASS:100","FAIL:0","PASS:0 1 0 1"]') == ["100", None, "0 1 0 1"]


def test_action_editor_lists_bed_sides_and_all_public_commands() -> None:
    from pathlib import Path

    import yaml

    from custom_components.adjustable_bed.beds.sleep_number.mcr import _COMMAND_FIELDS
    from custom_components.adjustable_bed.beds.sleep_number.services import INTERNAL_COMMANDS

    fields = yaml.safe_load(
        (Path(__file__).parents[1] / "custom_components/adjustable_bed/services.yaml").read_text()
    )["sleep_number_command"]["fields"]
    assert fields["side"]["selector"]["select"]["options"] == ["both", "left", "right"]
    assert (
        set(fields["command"]["selector"]["select"]["options"])
        == (COMMANDS.keys() | _COMMAND_FIELDS.keys()) - INTERNAL_COMMANDS
    )


async def test_task_cancel_before_first_fuzion_write_sends_nothing() -> None:
    controller, client = controller_with_client()
    await controller.start_notify()
    await controller.ble_lock.acquire()
    task = asyncio.create_task(controller._send_bamkey_command("ACTS", "left", "head", "100"))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    controller.ble_lock.release()
    client.write_gatt_char.assert_not_awaited()


async def test_replaced_client_is_never_read_for_an_old_response() -> None:
    controller, client = controller_with_client()
    await controller.start_notify()
    replacement = MagicMock(is_connected=True)
    replacement.read_gatt_char = AsyncMock(return_value=controller._build_bamkey_blob("PASS:ACK"))

    async def write(_uuid, _chunk, *, response):
        controller._handle_bamkey_notification(None, bytearray(SESSION))
        controller._coordinator.client = replacement

    client.write_gatt_char.side_effect = write
    with pytest.raises(ConnectionError, match="ended BLE session"):
        await controller._send_bamkey_command("ACHA")
    replacement.read_gatt_char.assert_not_awaited()


async def test_movement_cleanup_cannot_adopt_a_changed_profile() -> None:
    from dataclasses import replace

    controller, client = controller_with_client()
    controller._coordinator.disable_angle_sensing = True
    await controller.start_notify()
    client.services.get_characteristic.return_value.max_write_without_response_size = 64
    writes: list[bytes] = []

    async def write(_uuid, data, *, response):
        writes.append(data)
        controller._handle_bamkey_notification(None, bytearray(SESSION))
        controller.profile = replace(FUZION)

    client.write_gatt_char.side_effect = write
    with pytest.raises(ConnectionError, match="ended BLE session"):
        await controller.async_execute_sleep_number_command(
            "set_actuator_target_position",
            {
                "side": "left",
                "actuator": "head",
                "target_actuator_position": 100,
            },
        )
    assert writes == [FUZION.command("ACTS", "left", "head", "100")]


def test_service_and_temperature_program_require_the_side_module() -> None:
    from custom_components.adjustable_bed.beds.sleep_number.commands import parse_response
    from tests.test_sleep_number_fuzion import program

    controller, client = controller_with_client()
    controller._system_config = parse_response(
        COMMANDS["get_system_configuration"],
        [
            "dual",
            "yes",
            "yes",
            "yes",
            "yes",
            "heat_cool",
            "yes",
            "yes",
            "yes",
            "yes",
            "yes",
            "yes",
            "yes",
            "yes",
            "yes",
            "yes",
        ],
    )
    controller._footwarming_states["right"].present = True
    with pytest.raises(ValueError, match="not present"):
        controller.validate_sleep_number_command(
            "set_footwarming_settings",
            {
                "side": "left",
                "footwarming_level": "high",
                "footwarming_timer_value": 30,
            },
        )
    controller.validate_sleep_number_command("get_footwarming_presence", {"side": "left"})
    controller.validate_sleep_number_command(
        "set_footwarming_settings",
        {
            "side": "right",
            "footwarming_level": "high",
            "footwarming_timer_value": 30,
        },
    )
    with pytest.raises(ValueError, match="No temperature module"):
        controller.validate_sleep_number_command("set_temperature_program", {"program": program()})
    with pytest.raises(ValueError, match="No temperature module"):
        controller.validate_sleep_number_command(
            "migrate_routines_to_temperature_programs",
            {"side": "left", "migration_options": "keep"},
        )
    controller.validate_sleep_number_command("get_heidi_presence", {"side": "left"})
    client.write_gatt_char.assert_not_called()


async def test_readable_switches_hydrate_and_clear_unavailable_values() -> None:
    controller, _client = controller_with_client()
    from custom_components.adjustable_bed.beds.sleep_number.commands import parse_response

    controller._system_config = parse_response(
        COMMANDS["get_system_configuration"],
        [
            "dual",
            "yes",
            "yes",
            "yes",
            "yes",
            "heat_cool",
            "yes",
            "yes",
            "yes",
            "yes",
            "yes",
            "yes",
            "yes",
            "yes",
            "yes",
            "yes",
        ],
    )
    controller._send_bamkey_command = AsyncMock(
        side_effect=[["active"], ["1"], ["0"], ["true", "high"]]
    )
    await controller._hydrate_switches()

    def values():
        return {
            update.key: update.value
            for call in controller._coordinator.handle_controller_state_updates.call_args_list
            for update in call.args
        }

    assert values()["sleepiq_privacy"] is False
    assert values()["sleepiq_responsive_air_left"] is True
    assert values()["sleepiq_responsive_air_right"] is False
    assert values()["sleepiq_auto_light"] is True
    controller._send_bamkey_command = AsyncMock(side_effect=ValueError("not supported"))
    await controller._hydrate_switches()
    assert all(
        values()[key] is None
        for key in (
            "sleepiq_privacy",
            "sleepiq_responsive_air_left",
            "sleepiq_responsive_air_right",
            "sleepiq_auto_light",
        )
    )


@pytest.mark.parametrize(
    "chambers,bound_side,expected_sides",
    [
        ("dual", None, ("left", "right")),
        ("dual", "left", ("left",)),
        ("dual", "right", ("right",)),
        ("single", None, ("right",)),
        ("single", "left", ()),
        ("single", "right", ("right",)),
    ],
)
async def test_responsive_air_switches_follow_the_bound_side(
    chambers: str, bound_side: str | None, expected_sides: tuple[str, ...]
) -> None:
    controller, _client = controller_with_client()
    controller._system_config = {
        "chamber_type": chambers,
        "pressure_control_enabled_flag": "yes",
        "underbed_light_enable_flag": "no",
        "thermal_control_enabled_flag": "none",
    }
    controller._send_bamkey_command = AsyncMock(return_value=[])

    with controller.side_scope(bound_side):
        switches = [
            spec
            for spec in controller.controller_switch_specs
            if spec.key.startswith("sleepiq_responsive_air_")
        ]
        assert [spec.key for spec in switches] == [
            f"sleepiq_responsive_air_{side}" for side in expected_sides
        ]
        for spec, side in zip(switches, expected_sides, strict=True):
            await spec.set_fn(controller, True)
            controller._send_bamkey_command.assert_awaited_with("LRAS", side, "1", expected_args=0)


async def test_stale_notification_cleanup_leaves_the_new_owner_alone() -> None:
    from custom_components.adjustable_bed.beds.sleep_number.controller import SleepNumberController

    old, client = controller_with_client()
    await old.start_notify()
    replacement = MagicMock(is_connected=True)
    replacement.stop_notify = AsyncMock()
    coordinator = old._coordinator
    coordinator.client = replacement
    coordinator.controller = SleepNumberController(coordinator)
    coordinator.handle_controller_state_updates.reset_mock()
    await old.stop_notify()
    replacement.stop_notify.assert_not_awaited()
    client.stop_notify.assert_not_awaited()
    coordinator.handle_controller_state_updates.assert_not_called()


async def test_queued_auth_rechecks_controller_owner_inside_the_ble_lock() -> None:
    from custom_components.adjustable_bed.beds.sleep_number.controller import SleepNumberController

    controller, client = controller_with_client()
    await controller.ble_lock.acquire()
    task = asyncio.create_task(controller.start_notify())
    await asyncio.sleep(0)
    controller._coordinator.controller = SleepNumberController(controller._coordinator)
    controller.ble_lock.release()
    with pytest.raises(ConnectionError, match="ended BLE session"):
        await task
    client.read_gatt_char.assert_not_awaited()


async def test_replaced_owner_cannot_publish_partial_switch_delivery() -> None:
    from custom_components.adjustable_bed.beds.sleep_number.controller import SleepNumberController

    controller, client = controller_with_client()
    await controller.start_notify()

    async def write(*args, **kwargs):
        controller._coordinator.controller = SleepNumberController(controller._coordinator)
        controller._handle_bamkey_notification(None, bytearray(SESSION))

    client.write_gatt_char.side_effect = write
    with pytest.raises(ConnectionError, match="ended BLE session"):
        await controller.async_execute_sleep_number_command(
            "set_sleepiq_privacy_state", {"sleepiq_privacy_state": "paused"}
        )
    controller._coordinator.handle_controller_state_updates.assert_not_called()


@pytest.mark.parametrize("same_turn", [True, False])
async def test_cancelled_queued_native_motion_sends_neither_control_nor_global_halt(
    same_turn,
) -> None:
    controller, client = controller_with_client()
    controller._coordinator.disable_angle_sensing = True
    await controller.start_notify()
    await controller.ble_lock.acquire()
    task = asyncio.create_task(controller.move_back_up())
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    if same_turn:
        controller.ble_lock.release()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    if not same_turn:
        controller.ble_lock.release()
    client.write_gatt_char.assert_not_awaited()
    assert not controller._coordinator.cancel_command.is_set()


async def test_started_native_motion_finishes_its_buffer_then_halts_on_repeated_cancel() -> None:
    controller, client = controller_with_client()
    controller._coordinator.disable_angle_sensing = True
    await controller.start_notify()
    client.read_gatt_char.return_value = codec.fuzion("PASS:ACK")
    started, release = asyncio.Event(), asyncio.Event()
    chunks = []

    async def write(_uuid, data, **kwargs):
        chunks.append(data)
        if len(chunks) == 1:
            started.set()
            await release.wait()
        if data == FUZION.command("ACHA"):
            controller._handle_bamkey_notification(None, bytearray(SESSION))

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(controller.move_back_up())
    await started.wait()
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert b"".join(chunks) == FUZION.command("ACTS", "left", "head", "100") + FUZION.command(
        "ACHA"
    )
    assert not controller._coordinator.cancel_command.is_set()


@pytest.mark.parametrize("timeout", [TimeoutError("GATT"), None])
async def test_optional_fuzion_hydration_suppresses_only_a_missing_reply(timeout) -> None:
    from custom_components.adjustable_bed.beds.sleep_number.link import ReplyTimeout

    controller, _client = controller_with_client()
    controller.async_execute_sleep_number_command = AsyncMock(
        side_effect=timeout or ReplyTimeout("no reply")
    )
    if timeout is not None:
        with pytest.raises(TimeoutError, match="GATT"):
            await controller._hydrate_switches()
    else:
        await controller._hydrate_switches()


async def test_optional_fuzion_reply_timeout_is_separate_from_gatt_timeout() -> None:
    from dataclasses import replace

    from custom_components.adjustable_bed.beds.sleep_number.link import ReplyTimeout

    controller, client = controller_with_client()
    await controller.start_notify()
    controller.profile = replace(FUZION, response_timeout=0.005)
    controller._link.clear()
    with pytest.raises(ReplyTimeout):
        await controller._send_bamkey_command("SYCG")
    client.write_gatt_char.side_effect = TimeoutError("GATT write")
    with pytest.raises(TimeoutError, match="GATT write") as error:
        await controller._send_bamkey_command("SYCG")
    assert not isinstance(error.value, ReplyTimeout)


async def test_stalled_read_after_valid_hint_is_a_transport_timeout_during_hydration() -> None:
    from dataclasses import replace

    from custom_components.adjustable_bed.beds.sleep_number.link import ReplyTimeout

    controller, client = controller_with_client()
    controller.profile = replace(FUZION, response_timeout=0.01)
    await controller.start_notify()

    async def write(*args, **kwargs):
        controller._handle_bamkey_notification(None, bytearray(SESSION))

    async def read(*args, **kwargs):
        await asyncio.Event().wait()

    client.write_gatt_char.side_effect = write
    client.read_gatt_char.side_effect = read
    with pytest.raises(TimeoutError) as error:
        await controller._hydrate_switches()
    assert not isinstance(error.value, ReplyTimeout)
    assert client.read_gatt_char.await_count == 2  # Auth, then the stalled readback.
