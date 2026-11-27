"""Accepted King Koil frames, parser edges and owned native operations."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import _build_paired_children, const, services
from custom_components.adjustable_bed.beds.suta_king_koil.controller import (
    MODE,
    STEPS,
    KingKoilController,
)
from custom_components.adjustable_bed.beds.suta_king_koil.receive import Receiver
from custom_components.adjustable_bed.beds.truemotion.receive import Observations
from custom_components.adjustable_bed.codec.suta import text
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.errors import BedCommandFailedError
from custom_components.adjustable_bed.number import _number_entities_for
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.pairing import build_pair_entry_data
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.profile_recommendations import recommend_profile
from custom_components.adjustable_bed.profiles import suta_king_koil as app
from custom_components.adjustable_bed.select import _select_entities_for
from scripts.wire_snapshot import FakeClock, virtual_time
from tests.form_helpers import finish_new_bed
from tests.test_controller_contract import _FactoryCoordinator
from tests.test_detection import _make_service_info
from tests.test_richmat_family_flow import setup_flow
from tests.test_truemotion import _roles

VECTORS = json.loads((Path(__file__).parent / "fixtures/suta_king_koil_vectors.json").read_text())


@pytest.mark.parametrize("row", VECTORS, ids=lambda row: row["id"])
def test_accepted_vectors(row):
    args = row["inputs"]
    match row.get("kind", "literal"):
        case "literal":
            actual = text(args["command"])
        case "alarm":
            actual = text(
                app.alarm(args["op"], args["day"], args["hour"], args["minute"], args["loop"])
            )
        case "clock":
            actual = text(app.clock(**args))
        case "parser":
            rx = Receiver(Observations())
            rx.collecting = args.get("pending_exists", True)
            chunks = [bytes.fromhex(c) for c in args["chunks_hex"]]
            for chunk in chunks:
                rx.feed(chunk)
            actual = b"".join(chunks)
            assert {
                "buffer": rx.pending,
                "version": rx.observations.version,
                "raw": rx.raw,
                "date": rx.observations.gd,
                "pending": rx.alarms if rx.collecting else None,
            } == row["expected_state"]
        case _:
            raise AssertionError(row)
    assert actual.hex() == row["expected_bytes"]


def data(address="AA:BB:CC:DD:EE:28"):
    return {
        const.CONF_BED_TYPE: const.BED_TYPE_SUTA_KING_KOIL,
        CONF_ADDRESS: address,
        const.CONF_DISABLE_ANGLE_SENSING: True,
        const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
    }


async def fake():
    coordinator = _FactoryCoordinator()
    coordinator.entry.data = data()
    coordinator.client = MagicMock(
        is_connected=True,
        write_gatt_char=AsyncMock(),
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
    )
    _roles(coordinator.client)
    coordinator.record_command_trace = MagicMock()
    coordinator.handle_controller_state_updates = MagicMock()
    controller = await create_controller(
        coordinator, const.BED_TYPE_SUTA_KING_KOIL, None, coordinator.client
    )
    coordinator.controller = controller
    assert isinstance(controller, KingKoilController)
    await controller.start_notify()
    return coordinator, controller


def frames(client):
    return [call.args[1] for call in client.write_gatt_char.await_args_list]


async def test_recall_save_stop_and_massage_timing():
    coordinator, controller = await fake()
    clock = FakeClock()
    writes = []

    async def write(_char, packet, *, response):
        assert response is False
        writes.append((round(clock.now * 1000), packet))

    coordinator.client.write_gatt_char.side_effect = write
    with virtual_time(clock):
        await controller.preset_memory(1)
        assert writes == [(t, text("AT+MODE=BOTH M1")) for t in (100, 200, 300, 400, 500)]
        start = clock.now
        writes.clear()
        await controller.program_memory(1)
        assert [(round(t - start * 1000), p) for t, p in writes] == [
            (t, text("AT+SETMODE=BOTH M1")) for t in (5100, 5200, 5300)
        ]
        await controller.set_step("HEAD", 1)
        await controller.set_step("FOOT", 2)
        writes.clear()
        start = clock.now
        await controller.set_mode("Mode 3")
        assert [(round(t - start * 1000), p) for t, p in writes] == [
            (t, text(f"AT+MASS=BOTH {zone} LV20"))
            for t, zone in (
                (100, "HEAD"),
                (150, "FOOT"),
                (200, "HEAD"),
                (250, "FOOT"),
                (300, "HEAD"),
                (350, "FOOT"),
            )
        ]
        writes.clear()
        start = clock.now
        await controller.stop_all()
        assert [(round(t - start * 1000), p) for t, p in writes] == [
            (t, text(c))
            for t, c in (
                (100, "AT+CTRL=BOTH STOP"),
                (200, "AT+CTRL=BOTH STOP"),
                (250, "AT+MASS=BOTH HEAD DT00"),
                (350, "AT+MASS=BOTH HEAD DT00"),
                (400, "AT+MASS=BOTH FOOT DT00"),
                (500, "AT+MASS=BOTH FOOT DT00"),
            )
        ]
        with pytest.raises(ServiceValidationError):
            await controller.set_mode("Mode 1")


async def test_hold_cap_failure_cleanup_and_replacement_fence():
    coordinator, controller = await fake()
    with virtual_time(FakeClock()):
        await controller.hold_control("back_up", 60000)
    assert (
        frames(coordinator.client)
        == [text("AT+CTRL=BOTH BACK UP")] * 400 + [text("AT+CTRL=BOTH STOP")] * 3
    )
    coordinator.client.write_gatt_char.reset_mock()
    coordinator.client.write_gatt_char.side_effect = [BleakError("failed"), None, None, None]
    with virtual_time(FakeClock()), pytest.raises(BleakError, match="failed"):
        await controller.move_back_up()
    assert frames(coordinator.client)[1:] == [text("AT+CTRL=BOTH STOP")] * 3
    coordinator.client.write_gatt_char.reset_mock()

    async def replace_session(*_args, **_kwargs):
        controller.on_disconnect()
        await controller.start_notify()

    coordinator.client.write_gatt_char.side_effect = replace_session
    with virtual_time(FakeClock()):
        await controller.move_back_up()
    assert frames(coordinator.client) == [text("AT+CTRL=BOTH BACK UP")]


async def test_cancel_inflight_motion_settles_before_release():
    coordinator, controller = await fake()
    started, finish = asyncio.Event(), asyncio.Event()

    async def write(_char, packet, *, response):
        if packet == text("AT+CTRL=BOTH BACK UP"):
            started.set()
            await finish.wait()

    coordinator.client.write_gatt_char.side_effect = write
    with virtual_time(FakeClock()):
        task = asyncio.create_task(controller.move_back_up())
        await started.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert (
        frames(coordinator.client)
        == [text("AT+CTRL=BOTH BACK UP")] + [text("AT+CTRL=BOTH STOP")] * 3
    )


@pytest.fixture
async def runtime(hass, mock_coordinator_connected, mock_bleak_client):
    entry = MockConfigEntry(domain=const.DOMAIN, title="King Koil", data=data())
    entry.add_to_hass(hass)
    target = AdjustableBedCoordinator(hass, entry)
    _roles(mock_bleak_client)
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    await target.async_prime_offline_controller()
    await services.async_register_services(hass)
    with patch.object(
        services, "_resolve_sided_targets", return_value=([(target, "both")], [])
    ) as resolve:
        yield target, mock_bleak_client, resolve
    await target.async_shutdown()


async def test_actual_entities_clock_and_alarm_services(hass, runtime):
    target, client, _ = runtime
    numbers = _number_entities_for(hass, target)
    step = next(e for e in numbers if e.translation_key == "suta_king_koil_head_step")
    mode = next(
        e
        for e in _select_entities_for(hass, target)
        if e.translation_key == "suta_king_koil_massage_mode"
    )
    assert step.native_value is None and mode.current_option is None
    with virtual_time(FakeClock()):
        await step.async_set_native_value(2.0)
        assert target.controller_state[STEPS["HEAD"]] == 2
        await mode.async_select_option("Mode 2")
        assert target.controller_state[MODE] == "Mode 2"
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                const.DOMAIN,
                "set_alarm",
                {"device_id": "bed", "time": "07:30:00", "enabled": True, "weekdays": ["sunday"]},
                blocking=True,
            )
        # The receive callback represents the real bed clock and per-address alarm response.
        sender, callback = client.start_notify.await_args.args
        callback(sender, bytearray(b"+OK:GD=2611270905\r\n"))
        client.write_gatt_char.reset_mock()

        async def write(_char, packet, *, response):
            if packet == text("AT+GA"):
                callback(sender, bytearray(b"+OK:GA=0007300101\r\n"))

        client.write_gatt_char.side_effect = write
        await hass.services.async_call(
            const.DOMAIN,
            "set_alarm",
            {"device_id": "bed", "time": "07:30:00", "enabled": False, "weekdays": ["sunday"]},
            blocking=True,
        )
        assert frames(client) == [text("AT+CA=00073001")] * 3 + [text("AT+GA")] * 3
        assert target.controller.protocol_diagnostics["alarms_raw"] == {"07300101": "0,"}
        client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            const.DOMAIN,
            "suta_king_koil_confirm_alarm",
            {"device_id": "bed", "weekdays": [6], "hour": 23, "minute": 59},
            blocking=True,
        )
        assert frames(client) == [text("AT+DA=06235901")] * 3 + [text("AT+GA")] * 3
        client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            const.DOMAIN, "sync_clock", {"device_id": "bed"}, blocking=True
        )
        assert len(frames(client)) == 9 and frames(client)[0].startswith(b"AT+SD=")
        assert frames(client)[3:] == [text("AT+GD")] * 3 + [text("AT+GA")] * 3


@pytest.mark.parametrize("failure", (None, "FOOT", "ALL"))
async def test_public_stop_publishes_only_delivered_massage_state(hass, runtime, failure):
    target, client, _ = runtime
    numbers = {entity.translation_key: entity for entity in _number_entities_for(hass, target)}
    mode = next(
        entity
        for entity in _select_entities_for(hass, target)
        if entity.translation_key == "suta_king_koil_massage_mode"
    )
    with virtual_time(FakeClock()):
        await numbers["suta_king_koil_head_step"].async_set_native_value(2)
        await numbers["suta_king_koil_foot_step"].async_set_native_value(3)
        await mode.async_select_option("Mode 2")
        client.write_gatt_char.reset_mock()

        async def write(_char, packet, *, response):
            if failure == "ALL" or failure == "FOOT" and packet == text("AT+MASS=BOTH FOOT DT00"):
                raise BleakError("stop failed")

        client.write_gatt_char.side_effect = write
        if failure is None:
            await target.async_stop_command()
        else:
            with pytest.raises(BedCommandFailedError):
                await target.async_stop_command()
        assert len(frames(client)) == 6
        if failure == "ALL":
            expected = (2, 3, "Mode 2")
        elif failure == "FOOT":
            expected = (None, None, None)
        else:
            expected = (0, 0, None)
        assert (
            target.controller_state[STEPS["HEAD"]],
            target.controller_state[STEPS["FOOT"]],
            target.controller_state[MODE],
        ) == expected


async def test_explicit_app_setup_discovery_and_profile_identity(hass):
    flow = setup_flow(hass, **{const.CONF_BED_TYPE: const.BED_TYPE_SUTA_KING_KOIL})
    flow._discovery_info = None
    with patch.object(flow, "_verification_possible", return_value=False):
        result = await finish_new_bed(flow, await flow._async_continue_route())
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][const.CONF_MOTOR_COUNT] == 2
    assert result["data"][const.CONF_DISABLE_ANGLE_SENSING]
    assert resolve_profile_id(result["data"]) == "suta_king_koil"
    for name in ("SUTA-M510C", "SUTA-M510D", "SUTA-M510E", "SUTA-other"):
        info = _make_service_info(name=name, service_uuids=[app.SERVICE_UUID])
        detected = detect_bed_type_detailed(info)
        assert const.BED_TYPE_SUTA_KING_KOIL in (detected.ambiguous_types or [detected.bed_type])
        assert recommend_profile(data(), info, {}) is None
    for name in ("suta-M510", "LZ-OTA", "KK01S", "SUTA-DRAWER", "SUTA-DRAW"):
        detected = detect_bed_type_detailed(
            _make_service_info(name=name, service_uuids=[app.SERVICE_UUID])
        )
        assert const.BED_TYPE_SUTA_KING_KOIL not in (
            detected.ambiguous_types or [detected.bed_type]
        )


@pytest.mark.parametrize("side", ["left", "right", "both"])
async def test_native_pair_addresses_preserve_side_and_literals(hass, side):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Pair",
        data=build_pair_entry_data(
            data("AA:BB:CC:DD:EE:01"), data("AA:BB:CC:DD:EE:02"), name="Pair"
        ),
    )
    entry.add_to_hass(hass)
    children = _build_paired_children(hass, entry)
    for child in children.values():
        child._client = MagicMock(
            is_connected=True,
            write_gatt_char=AsyncMock(),
            start_notify=AsyncMock(),
            stop_notify=AsyncMock(),
            disconnect=AsyncMock(),
        )
        _roles(child._client)
        child._controller = await create_controller(
            child, const.BED_TYPE_SUTA_KING_KOIL, None, child._client
        )
        await child._controller.start_notify()
        child._link_ready = True
    pair = PairedBedCoordinator(hass, entry, children)
    try:
        with virtual_time(FakeClock()):
            await pair.async_execute_controller_command(
                lambda ctrl: ctrl.preset_memory(1), side=side
            )
        for name, child in children.items():
            assert frames(child.client) == (
                [text("AT+MODE=BOTH M1")] * 5 if side in (name, "both") else []
            )
    finally:
        await pair.async_shutdown()


async def test_cancelled_save_and_alarm_leave_no_unowned_writes():
    coordinator, controller = await fake()
    with virtual_time(FakeClock()):

        async def cancel_before_save():
            await asyncio.sleep(1)
            coordinator.cancel_command.set()

        cancellation = asyncio.create_task(cancel_before_save())
        with pytest.raises(asyncio.CancelledError):
            await controller.program_memory(1)
        await cancellation
    assert frames(coordinator.client) == []
    coordinator.cancel_command = asyncio.Event()

    async def cancel_on_write(*_args, **_kwargs):
        coordinator.cancel_command.set()

    coordinator.client.write_gatt_char.side_effect = cancel_on_write
    with virtual_time(FakeClock()), pytest.raises(asyncio.CancelledError):
        await controller.alarm_operation("SA", [0, 6], 7, 30)
    assert frames(coordinator.client) == [text("AT+SA=00073001")]
    receiver = controller._receiver()
    assert receiver is not None and not receiver.collecting
    assert controller.protocol_diagnostics["alarms_raw"] is None


async def test_king_koil_gatt_requires_notify_and_ignores_old_subscription():
    coordinator, controller = await fake()
    sender, callback = coordinator.client.start_notify.await_args.args
    controller.on_disconnect()
    callback(sender, bytearray(b"+OK:GD=2611270905\r\n"))
    assert controller.protocol_diagnostics["date_raw"] is None
    service = coordinator.client.services.get_service(app.SERVICE_UUID)
    for characteristic in service.characteristics:
        characteristic.properties = [p for p in characteristic.properties if p != "notify"]
    with pytest.raises(ServiceValidationError):
        await controller.start_notify()
    assert frames(coordinator.client) == []


async def test_partial_massage_stop_does_not_admit_a_mode_from_old_state():
    coordinator, controller = await fake()
    with virtual_time(FakeClock()):
        await controller.set_step("HEAD", 1)
        coordinator.client.write_gatt_char.side_effect = [None, BleakError("failed")]
        with pytest.raises(BleakError):
            await controller.set_step("HEAD", 0)
        coordinator.client.write_gatt_char.reset_mock()
        with pytest.raises(ServiceValidationError):
            await controller.set_mode("Mode 2")
        assert frames(coordinator.client) == []


@pytest.mark.parametrize("operation", ["step", "mode"])
@pytest.mark.parametrize("reconnect_during_write", [False, True])
async def test_final_massage_write_cannot_restore_disconnected_state(
    operation, reconnect_during_write
):
    coordinator, controller = await fake()
    with virtual_time(FakeClock()):
        if operation == "mode":
            await controller.set_step("HEAD", 1)
        coordinator.client.write_gatt_char.reset_mock()
        count = 0

        async def disconnect_on_final_write(*_args, **_kwargs):
            nonlocal count
            count += 1
            if count == 3:
                controller.on_disconnect()
                if reconnect_during_write:
                    await controller.start_notify()

        coordinator.client.write_gatt_char.side_effect = disconnect_on_final_write
        if operation == "step":
            await controller.set_step("HEAD", 1)
        else:
            await controller.set_mode("Mode 2")
        assert count == 3
        assert controller._state.timers == {"HEAD": "00", "FOOT": "00"}
        assert controller._state.level is None
        coordinator.client.write_gatt_char.side_effect = None
        coordinator.client.write_gatt_char.reset_mock()
        if not reconnect_during_write:
            await controller.start_notify()
        with pytest.raises(ServiceValidationError):
            await controller.set_mode("Mode 2")
        assert frames(coordinator.client) == []
