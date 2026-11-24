"""Exercise the frozen Shuda byte vectors and per-receiver BLE lifecycle."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.base import CONTROLLER_GESTURE_RELEASE
from custom_components.adjustable_bed.beds.shuda import controller as app
from custom_components.adjustable_bed.codec import okin_nframe as codec
from custom_components.adjustable_bed.command_scheduler import CommandIntent, DeviceCommandScheduler
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.const import (
    BED_TYPE_MALOUF_NEW_OKIN,
    BED_TYPE_SHUDA,
)
from custom_components.adjustable_bed.const import (
    NORDIC_UART_READ_CHAR_UUID as NOTIFY,
)
from custom_components.adjustable_bed.const import (
    NORDIC_UART_SERVICE_UUID as UART,
)
from custom_components.adjustable_bed.const import (
    NORDIC_UART_WRITE_CHAR_UUID as WRITE,
)
from custom_components.adjustable_bed.detection import detect_bed_type_detailed, detect_new_bed
from custom_components.adjustable_bed.errors import BedNotConnectedError
from custom_components.adjustable_bed.profiles import shuda as p
from tests.hold_lease_wire import virtual_clock

VECTORS = json.loads((Path(__file__).parent / "fixtures/shuda_vectors.json").read_text())
KEYS = {control: bytes.fromhex(literal) for control, literal in VECTORS["keys"].items()}
STOP = KEYS["stop"]
NOW = datetime(2026, 11, 24, 14, 37, 42)
CLOCK = bytes.fromhex("05 02 07 04 1A 0B 18 02 0E 25 2A 00")


def test_fixed_frames_match_named_actions():
    assert {key: codec.frame40(word) for key, word in p.KEYS.items()} | {
        "stop": codec.frame40(0)
    } == KEYS


@pytest.mark.parametrize("vector", VECTORS["settings"], ids=lambda row: row["id"])
def test_setting_vectors(vector):
    inputs = dict(vector["inputs"])
    match vector["builder"]:
        case "clock":
            actual = p.clock_frame(datetime.fromisoformat(inputs["local_time"]))
        case "query":
            actual = p.query_frame(inputs["slot"])
        case "setup":
            actual = p.alarm_frame(codec.ShortAlarmReport(**inputs))
        case "edited_setup":
            initial = inputs.pop("initial_week")
            days = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
            selected = {day for day in range(7) if initial & (1 << ((day + 1) % 7))}
            selected.symmetric_difference_update(days.index(day) for day in inputs.pop("toggles"))
            row = codec.ShortAlarmReport(week=p.edited_week(selected), **inputs)
            actual = p.alarm_frame(row)
        case unexpected:
            pytest.fail(f"Unknown builder {unexpected}")
    assert actual == bytes.fromhex(vector["expected_bytes"])


@pytest.mark.parametrize("vector", VECTORS["notifications"], ids=lambda row: row["input_hex"])
def test_alarm_notification_vectors(vector):
    parsed = p.alarm_model(bytes.fromhex(vector["input_hex"]))
    expected = vector["expected"]
    if isinstance(expected, dict) and expected["type"] == "alarm":
        assert parsed is not None
        assert asdict(parsed) == {key: value for key, value in expected.items() if key != "type"}
    else:
        # Unused massage callbacks, short frames and other prefixes have no state.
        assert parsed is None


def test_identity_has_no_address_fallback():
    assert p.manufacturer_identity({89: bytes.fromhex("A0 01 02 03 04 05 06 EE")}) == "060504030201"
    assert p.manufacturer_identity({89: bytes.fromhex("01 02 03 04 05 06")}) is None
    assert p.manufacturer_identity({}) is None


def _client(*, write_props=("write",), notify_props=("indicate",), service_uuid=UART):
    write = SimpleNamespace(uuid=WRITE, properties=write_props, handle=1, descriptors=[])
    notify = SimpleNamespace(uuid=NOTIFY, properties=notify_props, handle=2, descriptors=[])
    chars = {WRITE: write, NOTIFY: notify}
    return SimpleNamespace(
        is_connected=True,
        services=[SimpleNamespace(uuid=service_uuid, get_characteristic=chars.get)],
        write_gatt_char=AsyncMock(),
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
    )


@pytest.fixture
def bed():
    coordinator = MagicMock()
    coordinator.client = _client()
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_count = 4  # Stale data cannot grant extra axes.
    coordinator.motor_pulse_count = 5
    return app.ShudaController(coordinator), coordinator


def _frames(client):
    return [call.args[1] for call in client.write_gatt_char.await_args_list]


def _callback(client):
    char, callback = client.start_notify.await_args.args
    return lambda data: callback(char, bytearray.fromhex(data))


async def _connect(controller, coordinator):
    await controller.async_discover_capabilities()
    await controller.async_on_connect(SimpleNamespace(async_start_notify=controller.start_notify))
    return coordinator.client


@pytest.mark.parametrize(
    "parameters",
    [
        {"write_props": ("write-without-response",)},
        {"notify_props": ("read",)},
        {"service_uuid": "other"},
    ],
)
async def test_exact_service_and_characteristic_roles_required(bed, parameters):
    controller, coordinator = bed
    coordinator.client = _client(**parameters)
    with pytest.raises(BedNotConnectedError) as err:
        await controller.async_discover_capabilities()
    assert err.value.translation_key == "shuda_gatt_roles"
    coordinator.client.write_gatt_char.assert_not_awaited()


async def test_connect_clock_queries_retry_subscription_and_retire_old_callback(bed, monkeypatch):
    controller, coordinator = bed
    monkeypatch.setattr(app.dt_util, "now", lambda: NOW)
    client = coordinator.client
    client.start_notify.side_effect = [BleakError("first subscription failed"), None]
    await _connect(controller, coordinator)
    assert _frames(client) == [CLOCK, b"\x00\xc0", b"\x00\xd0"]
    assert all(call.kwargs == {"response": True} for call in client.write_gatt_char.await_args_list)
    old_char, old_callback = client.start_notify.await_args_list[0].args
    old_callback(old_char, bytearray.fromhex("A5 0E 00 00 41 05 16 05 00 00"))
    assert controller.persisted_app_state == {"alarms": {}}
    receive = _callback(client)
    await controller.stop_notify()
    client.stop_notify.assert_awaited_once()
    client.start_notify.side_effect = None
    await controller.start_notify()
    # The stale callback belongs to the same client wrapper and GATT handle.
    receive("A5 0E 00 00 41 05 16 05 00 00")
    assert controller.persisted_app_state == {"alarms": {}}
    _callback(client)("A5 0E 00 00 41 05 16 05 00 00")
    assert controller.persisted_app_state["alarms"]["3"] == [65, 9, 22, 5, 0]


@pytest.mark.parametrize(
    ("reply", "later"),
    [("A5 0E 00 00 41 05 16 05 00 00", [b"\x00\xe0"]), ("A5 0E 00 00 C1 05 16 05 00 01", [])],
)
async def test_conditional_slot_three_survives_controller_recreation(bed, reply, later):
    controller, coordinator = bed
    old_client = await _connect(controller, coordinator)
    _callback(old_client)(reply)
    coordinator.save_app_state.assert_called_once_with(controller)
    stored = json.loads(json.dumps(controller.persisted_app_state))
    controller.on_disconnect()
    coordinator.client = _client()
    newer = app.ShudaController(coordinator)
    newer.restore_persisted_app_state(stored)
    assert newer.persisted_app_state == stored
    new_client = await _connect(newer, coordinator)
    assert _frames(new_client)[1:] == [b"\x00\xc0", b"\x00\xd0", *later]
    assert newer.alarm_capability.slots == 2
    assert len(newer.controller_state_sensor_specs) == 2


def _alarm(**values):
    return AlarmRequest(**({"enabled": True, "reference_time": NOW} | values))


async def test_edited_alarm_conflict_and_disable_preserve_distinct_week_fields(bed):
    controller, coordinator = bed
    client = await _connect(controller, coordinator)
    client.write_gatt_char.reset_mock()
    receive = _callback(client)
    receive("A5 0D 00 FF BE 01 07 1E 00 01")
    request = _alarm(slot=1, hour=7, minute=30, weekdays=(0, 1, 2, 3, 4), wake_action="memory_1")
    with pytest.raises(ServiceValidationError, match="overlaps"):
        await controller.configure_alarm(request)
    assert not _frames(client)
    await controller.configure_alarm(_alarm(enabled=False, slot=2))
    assert _frames(client) == [bytes.fromhex("05 02 07 06 BE 01 07 1E 00 00 00 00"), b"\x00\xd0"]
    client.write_gatt_char.reset_mock()
    receive("A5 0D 00 FF BE 01 07 1E 00 00")
    await controller.configure_alarm(request)
    assert _frames(client) == [bytes.fromhex("05 02 07 05 BE 05 07 1E 00 01 00 00"), b"\x00\xc0"]

    # Do not disable a guessed alarm from old storage or fall back to slot 1.
    await controller.stop_notify()
    await controller.start_notify()
    client.write_gatt_char.reset_mock()
    with virtual_clock(), pytest.raises(ServiceValidationError, match="did not report alarm 2"):
        await controller.configure_alarm(_alarm(enabled=False, slot=2))
    assert _frames(client) == [b"\x00\xd0"]
    with pytest.raises(ServiceValidationError, match="Choose Shuda alarm 1 or 2"):
        await controller.configure_alarm(_alarm(enabled=False, slot=3))


async def test_held_motion_and_programming_are_separate_and_release_on_cancel(bed):
    controller, coordinator = bed
    client = await _connect(controller, coordinator)
    client.write_gatt_char.reset_mock()
    assert [spec.key for spec in controller.motor_control_specs] == ["back", "legs"]

    with virtual_clock() as clock:
        await controller.move_back_up()
        assert clock.now == pytest.approx(1)
    assert _frames(client) == [KEYS["head_up"]] * 5 + [STOP]

    client.write_gatt_char.reset_mock()
    await controller.preset_memory(1)
    assert _frames(client) == [KEYS["memory_1"], STOP]
    assert all(
        spec.requires_confirmation and spec.hold is None
        for spec in controller.controller_button_specs
        if spec.key.startswith("shuda_save_")
    )
    with pytest.raises(ServiceValidationError, match="less than five seconds"):
        await controller.hold_control("memory_1", 5000)
    assert controller.execution.hold_for("memory_1") is None

    client.write_gatt_char.reset_mock()
    with virtual_clock() as clock:
        await controller.program_memory(1)
        assert clock.now == pytest.approx(5.5)
    assert _frames(client) == [KEYS["memory_1"]] * 28 + [STOP]

    client.write_gatt_char.reset_mock()
    sent = asyncio.Event()

    async def capture(_char, frame, *, response):
        if frame != STOP:
            sent.set()
            await coordinator.cancel_command.wait()

    client.write_gatt_char.side_effect = capture
    task = asyncio.create_task(controller.hold_control("feet_up", 60_000))
    await sent.wait()
    task.cancel()
    coordinator.cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert _frames(client) == [KEYS["feet_up"], STOP]


async def test_discovery_admits_only_an_ambiguous_corroborated_app_candidate():
    def info(platform_name, services, *, advertised="Other", manufacturer_data=None):
        return SimpleNamespace(
            name=advertised,
            device=SimpleNamespace(name=platform_name),
            service_uuids=services,
            manufacturer_data=manufacturer_data or {},
            service_data={},
            address="00:11:22:33:44:55",
            connectable=True,
            rssi=-60,
        )

    def detect(*args, **kwargs):
        return detect_bed_type_detailed(info(*args, **kwargs))

    corroborated = detect("sMaRtBeD arbitrary suffix", [UART.upper()])
    assert corroborated.bed_type != BED_TYPE_SHUDA
    assert BED_TYPE_SHUDA in corroborated.ambiguous_types
    for result in (
        detect("Smartbed", []),
        detect("Other", [UART], advertised="Smartbed"),
        detect("", [UART], advertised="Smartbed"),
        detect("Other", [UART], manufacturer_data={89: bytes(7)}),
    ):
        assert BED_TYPE_SHUDA not in (result.ambiguous_types or ())

    chooser = AdjustableBedConfigFlow()
    shared = info("Smartbed", [UART], advertised="Smartbed", manufacturer_data={89: bytes(7)})
    assert detect_bed_type_detailed(shared).confidence == 0.7
    assert chooser._prepare_disambiguation(detect_new_bed(shared))
    assert BED_TYPE_SHUDA in chooser._disambiguation_types

    identified = detect_new_bed(
        info(
            "Smartbed428000193",
            [UART],
            advertised="Smartbed428000193",
            manufacturer_data={89: bytes.fromhex("4142010204")},
        )
    )
    assert identified.bed_type == BED_TYPE_MALOUF_NEW_OKIN
    assert identified.confidence == 0.85
    assert not chooser._prepare_disambiguation(identified)
    assert BED_TYPE_SHUDA not in (identified.ambiguous_types or ())


async def test_enable_waits_for_competing_alarm_before_writing(bed):
    controller, coordinator = bed
    client = await _connect(controller, coordinator)
    client.write_gatt_char.reset_mock()
    query = asyncio.Event()

    async def write(_char, frame, *, response):
        assert frame == b"\x00\xd0"
        query.set()  # ATT completed before the alarm report.

    client.write_gatt_char.side_effect = write
    request = _alarm(slot=1, hour=7, minute=30, weekdays=(0,), wake_action="flat")
    command = asyncio.create_task(controller.configure_alarm(request))
    await query.wait()
    assert not command.done()
    _callback(client)("A5 0D 00 00 82 01 07 1E 00 01")
    with pytest.raises(ServiceValidationError, match="overlaps"):
        await command
    assert _frames(client) == [b"\x00\xd0"]


async def test_stop_can_interrupt_the_alarm_report_wait(bed):
    controller, coordinator = bed
    client = await _connect(controller, coordinator)
    client.write_gatt_char.reset_mock()
    queried = asyncio.Event()

    async def write(_char, frame, *, response):
        assert frame == b"\x00\xd0"
        queried.set()

    client.write_gatt_char.side_effect = write
    request = _alarm(slot=1, hour=7, minute=30, wake_action="flat")
    command = asyncio.create_task(controller.configure_alarm(request))
    await queried.wait()
    coordinator.cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await command
    assert _frames(client) == [b"\x00\xd0"]


@pytest.mark.parametrize(
    ("gesture", "fail_cleanup", "replace_link"),
    [(False, False, False), (True, True, False), (True, True, True)],
)
async def test_scheduled_stop_consumes_or_retries_only_the_owned_release(
    bed, gesture, fail_cleanup, replace_link
):
    controller, coordinator = bed
    client = await _connect(controller, coordinator)
    client.write_gatt_char.reset_mock()
    scheduler = DeviceCommandScheduler("shuda")
    sent = asyncio.Event()
    lane = asyncio.Lock()
    stops = 0

    async def write(_char, frame, *, response):
        nonlocal stops
        if frame == STOP:
            stops += 1
            if fail_cleanup and stops == 1:
                raise BleakError("cleanup STOP failed")
        else:
            sent.set()

    async def move(context):
        async with lane:
            coordinator.cancel_command = context.cancel_event
            await controller.move_back_up()

    async def stop(_context):
        async with lane:
            if replace_link:
                controller.on_disconnect()
                coordinator.client = _client()
                await controller.async_discover_capabilities()
            await controller.stop_all()

    client.write_gatt_char.side_effect = write
    movement = await scheduler.enqueue(CommandIntent(move))
    await sent.wait()
    token = CONTROLLER_GESTURE_RELEASE.set(gesture)
    try:
        await scheduler.admit_stop(stop)
    finally:
        CONTROLLER_GESTURE_RELEASE.reset(token)
    if fail_cleanup:
        with pytest.raises(BleakError, match="cleanup STOP failed"):
            await movement.future
    else:
        await movement.future
    assert _frames(client) == [
        KEYS["head_up"],
        STOP,
        *([STOP] if fail_cleanup and not replace_link else []),
    ]
    if replace_link:
        coordinator.client.write_gatt_char.assert_not_awaited()
