"""Artifact vectors and the safety boundaries of the reply-driven session."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.paramount.controller import (
    ParamountController,
)
from custom_components.adjustable_bed.codec import paramount as codec
from custom_components.adjustable_bed.controller_state import ControllerState
from custom_components.adjustable_bed.detection import detect_bed_type
from tests.paramount_vectors import (
    AUTH,
    CALL,
    CONTROLS,
    MEMORY1,
    MEMORY2,
    QUERIES,
    REPLIES,
    SETTINGS,
)


def test_all_frozen_outgoing_literals() -> None:
    assert [codec.control(code).hex() for code in range(10)] == list(CONTROLS)
    assert {code: codec.frame(code).hex() for code in QUERIES} == QUERIES
    assert codec.frame(0x86, b"AUTH_REQ").hex() == AUTH
    assert codec.control(22, (30, 10, 40, 0)).hex() == MEMORY1
    assert codec.control(23, (75, 30, 255, 5)).hex() == MEMORY2
    settings = codec.Settings((0, 1, 2, 3), (30, 10, 40, 0), (75, 30, 255, 5))
    assert settings.encode().hex() == SETTINGS
    assert settings.setting("call_prohibition", True).encode().hex() == CALL


@pytest.mark.parametrize("raw", REPLIES)
def test_reply_fields_are_unsigned_without_invented_checksum(raw: str) -> None:
    reply = codec.parse(bytes.fromhex(raw))
    assert reply is not None
    assert all(0 <= value <= 255 for value in reply.payload)
    assert codec.parse(bytes.fromhex(raw)[:-1]) is None


def test_parser_rssi_and_sentinel_rules() -> None:
    reply = codec.parse(bytes.fromhex(REPLIES[3]))
    assert reply is not None and reply.rssi == -60
    assert codec.parse(bytes.fromhex("40040700000000007f00")).rssi is None
    assert codec.parse(bytes.fromhex("9905ff")) is None
    assert codec.clip_memory(255, 0, 75, True) == 255
    assert codec.clip_memory(255, 0, 75, False) == 75
    assert codec.clip_memory(255, 20, 60, False, height=True) == 255
    assert codec.clip_memory(10, 20, 60, False, height=True) == 20
    assert codec.clip_memory(80, 20, 60, False, height=True) == 60


@pytest.fixture
def bed() -> ParamountController:
    coordinator = MagicMock()
    coordinator.client.is_connected = True
    coordinator.cancel_command = asyncio.Event()
    coordinator.controller_state = ControllerState()

    def publish(*updates: object) -> None:
        for update in updates:
            coordinator.controller_state[update.key] = update.value

    coordinator.forward_controller_state_updates.side_effect = publish
    ctrl = ParamountController(coordinator, {"mask": 31, "height_min": 20, "height_max": 70})
    ctrl.profile = replace(
        ctrl.profile,
        response_delay_ms=0,
        press_delay_ms=0,
        initial_delay_ms=0,
        response_timeout_ms=10,
    )
    return ctrl


def responding(bed: ParamountController) -> list[bytes]:
    sent: list[bytes] = []
    current = codec.parse(bytes.fromhex(REPLIES[2])).settings

    async def write(command: bytes, **kwargs: object) -> None:
        nonlocal current
        sent.append(command)
        opcode = command[1] - 128
        if opcode == 5:
            current = codec.Settings(
                codec.posture(command[3:7]),
                codec.posture(command[7:11]),
                codec.posture(command[11:15]),
            )
        raw = {
            1: bytes.fromhex("40010106"),
            2: bytes.fromhex(REPLIES[1]),
            3: bytes((0x40, 3, 12)) + current.encode()[3:15],
            4: bytes.fromhex(REPLIES[3]),
            5: bytes.fromhex(REPLIES[4]),
        }.get(opcode)
        if raw:
            bed._notification(raw)

    bed.write_command = AsyncMock(side_effect=write)
    return sent


@pytest.mark.parametrize("mask", range(32))
def test_capabilities_gate_every_layout_independently(bed: ParamountController, mask: int) -> None:
    bed._mask = mask
    assert {spec.key for spec in bed.motor_control_specs} == {
        axis for axis, bit in codec.CAPABILITIES.items() if axis != "memory" and mask & bit
    }
    assert bed.memory_slot_count == (2 if mask & 16 else 0)
    assert not bed.supports_preset_flat
    assert {spec.position_key for spec in bed.position_number_specs} == {
        axis for axis, bit in (("head", 1), ("legs", 2)) if mask & bit
    }


async def test_missing_reply_never_replays_movement_and_always_releases(
    bed: ParamountController,
) -> None:
    bed.write_command = AsyncMock()
    with pytest.raises(TimeoutError, match="not replayed"):
        await bed.hold_control("head_up", 1000)
    assert [call.args[0] for call in bed.write_command.await_args_list] == [
        codec.control(2),
        codec.control(0),
    ]
    assert not bed.write_command.await_args_list[-1].kwargs["cancel_event"].is_set()


async def test_stop_during_response_wait_releases_without_waiting_for_reply(
    bed: ParamountController,
) -> None:
    bed.profile = replace(bed.profile, response_timeout_ms=10000)
    written = asyncio.Event()
    bed.write_command = AsyncMock(side_effect=lambda *args, **kwargs: written.set())
    task = asyncio.create_task(bed.hold_control("height_up", 10000))
    await written.wait()
    bed._coordinator.cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 0.2)
    assert bed.write_command.await_args_list[-1].args[0] == codec.control(0)


@pytest.mark.parametrize("source", ("diagnostic", "stop"))
async def test_late_neutral_reply_is_drained_before_new_movement(
    bed: ParamountController, source: str
) -> None:
    written = asyncio.Event()
    bed.write_command = AsyncMock(side_effect=lambda *args, **kwargs: written.set())
    if source == "diagnostic":
        query = asyncio.create_task(bed.read_positions())
        await written.wait()
        query.cancel()
        with pytest.raises(asyncio.CancelledError):
            await query
    else:
        await bed.stop_all()

    written.clear()
    movement = asyncio.create_task(bed.hold_control("head_up", 1000))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert bed.write_command.await_count == 1
    bed._notification(bytes.fromhex(REPLIES[3]))
    await asyncio.wait_for(written.wait(), 0.2)
    with pytest.raises(TimeoutError, match="not replayed"):
        await movement
    assert [call.args[0] for call in bed.write_command.await_args_list] == [
        codec.control(0),
        codec.control(2),
        codec.control(0),
    ]


async def test_cancelled_movement_and_release_both_drain_before_next_request(
    bed: ParamountController,
) -> None:
    written = asyncio.Event()
    bed.write_command = AsyncMock(side_effect=lambda *args, **kwargs: written.set())
    movement = asyncio.create_task(bed.hold_control("head_up", 1000))
    await written.wait()
    bed._coordinator.cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await movement
    assert bed.write_command.await_count == 2
    bed._coordinator.cancel_command.clear()
    written.clear()
    query = asyncio.create_task(bed.read_positions())
    await asyncio.sleep(0)
    bed._notification(bytes.fromhex(REPLIES[3]))
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert bed.write_command.await_count == 2
    bed._notification(bytes.fromhex(REPLIES[3]))
    await asyncio.wait_for(written.wait(), 0.2)
    bed._notification(bytes.fromhex(REPLIES[3]))
    await query
    assert bed.write_command.await_count == 3


async def test_undrained_release_blocks_new_command_until_disconnect(
    bed: ParamountController,
) -> None:
    bed.write_command = AsyncMock()
    await bed.stop_all()
    with pytest.raises(TimeoutError, match="not replayed"):
        await bed.read_positions()
    bed.write_command.assert_awaited_once()
    bed.on_disconnect()
    sent = responding(bed)
    await bed.read_positions()
    assert sent == [codec.control(0)]


async def test_reply_driven_hold_is_bounded_and_cleans_up(bed: ParamountController) -> None:
    sent = responding(bed)
    await bed.hold_control("head_up", 20)
    assert sent[0] == codec.control(2) and sent[-1] == codec.control(0)


async def test_save_preserves_flags_other_memory_and_tilt(bed: ParamountController) -> None:
    sent = responding(bed)
    await bed.program_memory(1)
    write = next(frame for frame in sent if frame[1] == 0x85)
    assert write[3:7] == bytes((0, 1, 2, 3))
    assert write[7:11] == bytes((30, 10, 40, 5))
    assert write[11:15] == bytes((75, 30, 255, 5))


@pytest.mark.parametrize(
    ("name", "index", "mask"),
    (("call_prohibition", 0, 32), ("switch_prohibition", 3, 4), ("speed", 3, 1)),
)
async def test_settings_change_only_the_proven_bit(
    bed: ParamountController, name: str, index: int, mask: int
) -> None:
    sent = responding(bed)
    await bed._change_setting(name, True)
    write = next(frame for frame in sent if frame[1] == 0x85)
    before = bytes.fromhex(SETTINGS)
    desired = bytearray(before[3:15])
    desired[index] |= mask
    assert write[3:15] == desired


async def test_full_readback_rejects_xor_collision(bed: ParamountController) -> None:
    desired = codec.parse(bytes.fromhex(REPLIES[2])).settings
    changed = codec.Settings((1, 0, 2, 3), desired.memory1, desired.memory2)
    assert desired.encode()[-1] == changed.encode()[-1]
    bed._exchange = AsyncMock(
        side_effect=[codec.Reply(5, b""), codec.Reply(3, changed.encode()[3:15])]
    )
    with pytest.raises(ValueError, match="readback"):
        await bed._save_settings(desired)
    assert bed._exchange.await_count == 2


def test_memory_clamps_ranges_and_retains_sentinel_height_and_tilt(
    bed: ParamountController,
) -> None:
    bed._settings = codec.parse(bytes.fromhex(REPLIES[2])).settings
    bed._ranges = {"head": (5, 40), "legs": (0, 20), "height": (25, 60)}
    assert bed._memory_frame(2) == codec.control(23, (40, 20, 255, 5))


async def test_idle_refresh_requests_settings_every_fifth_reply(bed: ParamountController) -> None:
    sent = responding(bed)
    for _ in range(5):
        await bed.read_positions()
    assert [frame[1] for frame in sent] == [0x84] * 5 + [0x83]


async def test_unsolicited_and_old_session_replies_do_not_complete_current_request(
    bed: ParamountController,
) -> None:
    pending = bed._track_reply(codec.frame(0x81))
    bed._notification(bytes.fromhex(REPLIES[3]))
    assert not pending.done()
    bed.on_disconnect()
    assert isinstance(pending.exception(), ConnectionError)
    assert not bed._replies
    assert bed._settings is None and bed._posture is None


async def test_session_subscribes_before_startup_and_reads_binary_serial(
    bed: ParamountController,
) -> None:
    sent = responding(bed)
    session = SimpleNamespace(
        async_start_notify=AsyncMock(),
        hass=MagicMock(),
        address="AA:BB:CC:DD:EE:FF",
        client=bed.client,
        persist_capability_snapshot=MagicMock(),
    )
    bed.client.read_gatt_char = AsyncMock(return_value=bytearray((0, 255, 16)))
    with patch(
        "custom_components.adjustable_bed.beds.paramount.controller.bluetooth.async_last_service_info",
        return_value=None,
    ):
        await bed.async_on_connect(session)
    session.async_start_notify.assert_awaited_once()
    assert [frame[1] for frame in sent] == [0x81, 0x82, 0x83, 0x84]
    assert bed._serial == "00ff10"
    session.persist_capability_snapshot.assert_called_once()


async def test_connect_wait_enters_registration_without_claiming_a_verified_bond(
    bed: ParamountController,
) -> None:
    bed.write_command = AsyncMock()
    session = SimpleNamespace(
        async_start_notify=AsyncMock(), hass=MagicMock(), address="AA:BB:CC:DD:EE:FF"
    )
    with (
        patch(
            "custom_components.adjustable_bed.beds.paramount.controller.bluetooth.async_last_service_info",
            return_value=SimpleNamespace(service_uuids=[codec.CONNECT_WAIT_UUID]),
        ),
        pytest.raises(ConnectionError, match="registration mode"),
    ):
        await bed.async_on_connect(session)
    bed.write_command.assert_awaited_once_with(bytes.fromhex(AUTH))


@pytest.mark.parametrize("uuid", (codec.CONNECT_WAIT_UUID, codec.REGISTRATION_UUID))
def test_discovery_uses_only_real_session_services(uuid: str) -> None:
    info = SimpleNamespace(
        name="Unrelated name",
        service_uuids=[uuid],
        manufacturer_data={},
        address="AA:BB:CC:DD:EE:FF",
    )
    assert detect_bed_type(info) == "paramount"


async def test_disabled_manual_axis_never_writes_movement_even_without_posture(
    bed: ParamountController,
) -> None:
    bed._range_enabled["head"] = False
    bed.write_command = AsyncMock()
    await bed.hold_control("head_up", 1000)
    assert [call.args[0] for call in bed.write_command.await_args_list] == [codec.control(0)]


async def test_local_preferences_survive_controller_rebuild(bed: ParamountController) -> None:
    bed._ranges = {"head": (10, 60), "height": (25, 65)}
    bed._range_enabled = {"head": False}
    bed._duration = "4"
    bed._serial = "00ff"
    restored = ParamountController(bed._coordinator, bed.capability_snapshot())
    restored.restore_persisted_app_state(bed.persisted_app_state)
    assert restored._bounds("head") == (10, 60)
    assert restored._bounds("height") == (25, 65)
    assert restored._range_enabled == {"head": False}
    assert restored._duration == "4" and restored._serial == "00ff"
    assert restored._settings is None


async def test_native_cover_uses_selected_tap_duration(bed: ParamountController) -> None:
    bed._duration = "4"
    bed.hold_control = AsyncMock()
    spec = next(spec for spec in bed.motor_control_specs if spec.key == "head")
    assert spec.hold.press_hold_ms is None
    await spec.open_fn(bed)
    bed.hold_control.assert_awaited_once_with("head_up", 4000)


async def test_late_notification_from_old_subscription_cannot_hydrate_new_session(
    bed: ParamountController,
) -> None:
    bed.client.start_notify = AsyncMock()
    await bed.start_notify()
    old = bed.client.start_notify.await_args.args[1]
    bed.on_disconnect()
    await bed.start_notify()
    old(MagicMock(), bytearray.fromhex(REPLIES[3]))
    assert bed._posture is None
    current = bed.client.start_notify.await_args.args[1]
    current(MagicMock(), bytearray.fromhex(REPLIES[3]))
    assert bed._posture == (30, 10, 40, 5)


async def test_release_failure_is_reported(bed: ParamountController) -> None:
    bed._range_enabled["head"] = False
    bed.write_command = AsyncMock(side_effect=ConnectionError("release failed"))
    with pytest.raises(ConnectionError, match="release failed"):
        await bed.hold_control("head_up", 1000)


async def test_seek_step_does_not_inherit_four_second_native_tap(bed: ParamountController) -> None:
    bed._duration = "4"
    bed.hold_control = AsyncMock()
    default = AsyncMock()
    await bed.position_seek_policy.async_issue_step("head", True, default)
    bed.hold_control.assert_awaited_once_with("head_up", 1000)
    default.assert_not_awaited()


def test_builders_cast_payload_integers_to_unsigned_low_byte() -> None:
    assert codec.control(258, (-1, 256, 257, 511)) == codec.control(2, (255, 0, 1, 255))
    assert (
        codec.Settings((-1, 256, 257, 511), (0, 0, 0, 0), (0, 0, 0, 0)).encode()
        == codec.Settings((255, 0, 1, 255), (0, 0, 0, 0), (0, 0, 0, 0)).encode()
    )


def test_ha_connection_sensor_already_exposes_adapter_rssi() -> None:
    from custom_components.adjustable_bed.binary_sensor import AdjustableBedConnectionSensor

    sensor = SimpleNamespace(
        _coordinator=SimpleNamespace(
            entity_side=None,
            last_connected=None,
            last_disconnected=None,
            connection_source="host adapter",
            connection_rssi=-67,
            is_connecting=False,
            is_connected=True,
            last_disconnect_reason=None,
        )
    )
    getter = AdjustableBedConnectionSensor.extra_state_attributes.fget
    assert getter is not None
    assert getter(sensor)["rssi"] == -67


async def test_movement_enable_changes_schedule_app_state_saves(
    bed: ParamountController, hass
) -> None:
    from custom_components.adjustable_bed.app_state_store import AppStateStore

    store = AppStateStore(hass, "AA:BB:CC:DD:EE:FF")
    store._data = {}
    with patch.object(store, "_schedule_save") as save:
        store.update("paramount:auto", bed.persisted_app_state)
        enabled = next(
            spec for spec in bed.controller_select_specs if spec.key == "paramount_head_range"
        )
        await enabled.select_fn(bed, "disabled")
        store.update("paramount:auto", bed.persisted_app_state)
        await enabled.select_fn(bed, "enabled")
        store.update("paramount:auto", bed.persisted_app_state)
    assert save.call_count == 3
    assert (await store.async_slot("paramount:auto"))["range_enabled"] == {"head": True}


@pytest.mark.parametrize(
    ("axis", "limits"),
    (("head", (0, 40)), ("head", (10, 75)), ("legs", (0, 20)), ("legs", (5, 30))),
)
async def test_linked_motion_refuses_narrowed_enabled_axis_ranges_after_restore(
    bed: ParamountController, axis: str, limits: tuple[int, int]
) -> None:
    bed.restore_persisted_app_state({"ranges": {axis: list(limits)}, "range_enabled": {axis: True}})
    bed.write_command = AsyncMock()
    for direction in ("up", "down"):
        with pytest.raises(ValueError, match="Linked movement"):
            await bed.hold_control("gearing_" + direction, 1000)
    bed.write_command.assert_not_awaited()


def test_linked_motion_keeps_the_app_gate_for_disabled_axis_ranges(
    bed: ParamountController,
) -> None:
    bed._ranges["head"] = (0, 40)
    bed._range_enabled["head"] = False
    bed.validate_hold_control("gearing_up", 1000)


@pytest.mark.parametrize("slot", (1, 2))
def test_memory_buttons_publish_capability_gated_hold_metadata(
    bed: ParamountController, slot: int
) -> None:
    from custom_components.adjustable_bed.button import AdjustableBedButton

    key = f"preset_memory_{slot}"
    sensor = SimpleNamespace(
        _coordinator=SimpleNamespace(capability_controller=bed),
        entity_description=SimpleNamespace(key=key),
    )
    getter = AdjustableBedButton.extra_state_attributes.fget
    assert getter is not None
    assert getter(sensor)["held_control"] == f"memory_{slot}"
    assert getter(sensor)["hold_lease_mode"] == "stream"
    assert bed.standard_button_hold_spec("program_memory_1") is None
    bed._mask &= ~16
    assert bed.standard_button_hold_spec(key) is None
