"""Resident unit160: frozen wire vectors and the reachable app lifecycle."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.bed_traits import bed_traits
from custom_components.adjustable_bed.beds.resident import controller as resident
from custom_components.adjustable_bed.codec import okin_nframe as codec
from custom_components.adjustable_bed.const import (
    BED_TYPE_RESIDENT,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
)
from custom_components.adjustable_bed.profiles.okin_nframe import RESIDENT
from custom_components.adjustable_bed.setup_questions import setup_profile_for

_REAL_PAUSE = resident._pause

VECTORS = json.loads((Path(__file__).parent / "fixtures/resident_vectors.json").read_text())
# Exact getter-to-profile mapping, independently of the shared 64-bit legacy table.
ACTIONS = {
    "flatPosition": "flat",
    "footDown": "foot_down",
    "footUp": "foot_up",
    "headDown": "head_down",
    "headUp": "head_up",
    "headfootDown": "head_foot_down",
    "headfootUp": "head_foot_up",
    "massageAll": "massage_switch",
    "massageStopAll": "massage_off",
    "massageTimerSwitch": "massage_timer",
    "memory1_m5": "memory_1",
    "memory2_m6": "memory_2",
    "memory_antiSnore": "anti_snore",
    "memory_lounge": "lounge",
    "memory_tvpc": "tv_pc",
    "memory_zero": "zero_g",
    "stopCommand": "stop",
    "strengthAdd": "strength_up",
    "strengthReduce": "strength_down",
    "underbedLighting": "light_toggle",
}


@pytest.mark.parametrize("row", VECTORS, ids=lambda row: row["id"])
def test_all_31_frozen_vectors(row):
    if row["kind"] == "catalog":
        if row["action"] == "checkMassage":
            actual = resident.QUERY_MASSAGE
        elif row["action"] == "checkTime":
            actual = resident.QUERY_CLOCK
        else:
            actual = codec.frame(RESIDENT.keys[ACTIONS[row["action"]]], RESIDENT.width)
        assert actual == bytes.fromhex(row["expected_bytes"])
    elif row["kind"] == "clock":
        i = row["inputs"]
        assert codec.calendar_record(
            0xE7,
            (
                i["year"] - 1900,
                i["month"] - 1,
                i["day"],
                i["hour"],
                i["minute"],
                i["second"],
            ),
        ) == bytes.fromhex(row["expected_bytes"])
    else:
        parser = codec.MassageTimerParser()
        actual = [parser.feed(bytes(chunk)) for chunk in row["inputs"]["chunks"]]
        # Intentional safety difference: malformed matching frames do not raise.
        assert actual == [None if v == "RangeError" else v for v in row["expected_outputs"]]
        assert bool(parser.pending) is row["expected_pending"]


def char(uuid, properties):
    return SimpleNamespace(
        uuid=uuid, properties=properties, handle=1, descriptors=[], description="Resident role"
    )


@pytest.fixture
def bed(monkeypatch):
    write = char(codec.WRITE_UUID, ["write"])
    notify = char(resident.NOTIFY_UUID, ["notify"])
    model = char(resident.MODEL_UUID, ["read"])
    client = MagicMock()
    client.is_connected = True
    client.services = [
        SimpleNamespace(uuid=codec.SERVICE_UUID, characteristics=[write, notify]),
        SimpleNamespace(uuid=resident.INFO_SERVICE, characteristics=[model]),
    ]
    client.write_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.read_gatt_char = AsyncMock(return_value=b"ignored model")
    coordinator = MagicMock()
    coordinator.client = client
    coordinator.motor_count = 4  # A saved generic setting must not add extra axes.
    coordinator.motor_pulse_count = 3
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_delay_ms = 17
    controller = resident.ResidentController(coordinator)
    controller.static_traits = bed_traits(BED_TYPE_RESIDENT)
    coordinator.mock_sleep = AsyncMock()
    monkeypatch.setattr(resident, "sleep", coordinator.mock_sleep)
    coordinator.mock_pause = AsyncMock(return_value=False)
    monkeypatch.setattr(resident, "_pause", coordinator.mock_pause)
    return controller, coordinator, client


async def connected(bed):
    controller, coordinator, client = bed
    await controller.async_discover_capabilities()
    return controller, coordinator, client


def frames(client):
    return [c.args[1] for c in client.write_gatt_char.await_args_list]


def frame(key):
    return codec.frame(RESIDENT.keys[key], RESIDENT.width)


async def test_fixed_capabilities_and_setup_ownership(bed):
    c, _, _ = await connected(bed)
    assert c.profile is RESIDENT
    assert c.execution.hold == "stream" and not c.execution.concurrent
    assert {s.key for s in c.motor_control_specs} == {"back", "legs"}
    assert {s.scheduler_resource for s in c.motor_control_specs} == {"*"}
    assert c.supports_simultaneous_movement
    assert not c.supports_single_address_pairing
    assert not c.has_lumbar_support
    assert c.memory_slot_count == 2 and not c.supports_memory_programming
    assert c.supports_massage and c.auto_enable_massage
    assert c.supports_massage_intensity_step_control
    assert not c.supports_head_massage_intensity_step_control
    assert not c.supports_foot_massage_intensity_step_control
    assert c.massage_mode_step_is_timer
    assert not c.supports_discrete_light_control
    assert c.supports_light_toggle_control
    assert c.supports_clock_sync and not c.supports_clock_alarm
    assert not c.supports_position_feedback
    assert c.static_traits.owns_device_info_reads
    assert c.standard_button_hold_spec("preset_memory_1").control == "memory_1"
    owned = setup_profile_for({CONF_BED_TYPE: BED_TYPE_RESIDENT}).owns
    assert owned[CONF_MOTOR_COUNT] == 2
    assert owned[CONF_HAS_MASSAGE] is True
    assert owned[CONF_DISABLE_ANGLE_SENSING] is True
    assert owned[CONF_MOTOR_PULSE_DELAY_MS] == 300


@pytest.mark.parametrize(
    ("method", "key", "massage"),
    [
        ("preset_flat", "flat", False),
        ("preset_zero_g", "zero_g", False),
        ("preset_tv", "tv_pc", False),
        ("preset_lounge", "lounge", False),
        ("preset_anti_snore", "anti_snore", False),
        ("lights_toggle", "light_toggle", False),
        ("massage_toggle", "massage_switch", True),
        ("massage_off", "massage_off", True),
        ("massage_intensity_up", "strength_up", True),
        ("massage_intensity_down", "strength_down", True),
        ("massage_mode_step", "massage_timer", True),
    ],
)
async def test_all_presses_release_and_refresh_timer(bed, method, key, massage):
    c, coordinator, client = await connected(bed)
    await getattr(c, method)()
    release = [frame("stop"), resident.QUERY_MASSAGE] if massage else [frame("stop")]
    assert frames(client) == [frame(key), *release, *release]
    assert all(call.kwargs["response"] is True for call in client.write_gatt_char.await_args_list)
    coordinator.mock_sleep.assert_awaited_once_with(pytest.approx(0.3, abs=0.005))


@pytest.mark.parametrize("slot", [1, 2])
async def test_m1_m2_recall_only(bed, slot):
    c, coordinator, client = await connected(bed)
    await c.preset_memory(slot)
    assert frames(client) == [frame(f"memory_{slot}"), frame("stop"), frame("stop")]


@pytest.mark.parametrize(
    ("method", "key"),
    [
        ("move_head_up", "head_up"),
        ("move_back_down", "head_down"),
        ("move_legs_up", "foot_up"),
        ("move_feet_down", "foot_down"),
    ],
)
async def test_motor_pulses_use_profile_interval(bed, method, key):
    c, coordinator, client = await connected(bed)
    await getattr(c, method)()
    assert frames(client) == [frame(key)] * 3 + [frame("stop")] * 2
    assert [call.args[0] for call in coordinator.mock_pause.await_args_list] == pytest.approx(
        [300, 600], abs=5
    )


async def test_combined_axes_and_invalid_direction_before_write(bed):
    c, coordinator, client = await connected(bed)
    await c.move_simultaneously("back", True, "legs", True)
    assert frames(client) == [frame("head_foot_up")] * 3 + [frame("stop")] * 2
    client.write_gatt_char.reset_mock()
    with pytest.raises(ValueError):
        await c.move_simultaneously("back", True, "legs", False)
    assert not frames(client)


async def test_cancel_event_and_failed_write_cannot_suppress_second_stop(bed):
    c, coordinator, client = await connected(bed)
    coordinator.cancel_command.set()
    client.write_gatt_char.side_effect = [BleakError("first STOP failed"), None]
    with pytest.raises(BleakError):
        await c.stop_all()
    assert frames(client) == [frame("stop"), frame("stop")]


async def test_task_cancellation_still_completes_release(bed, monkeypatch):
    c, coordinator, client = await connected(bed)
    first_write = asyncio.Event()
    block_write = asyncio.Event()

    async def write(*_args, **_kwargs):
        if len(frames(client)) == 1:
            first_write.set()
            await block_write.wait()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(c.preset_flat())
    await first_write.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert frames(client) == [frame("flat"), frame("stop"), frame("stop")]


async def test_release_does_not_follow_replaced_session(bed, monkeypatch):
    c, coordinator, client = await connected(bed)

    async def pause(_seconds):
        # The old action's final release must never write to a new BLE client.
        c.on_disconnect()
        coordinator.client = MagicMock(is_connected=True)
        coordinator.client.services = client.services
        coordinator.client.write_gatt_char = AsyncMock()
        await c.async_discover_capabilities()

    monkeypatch.setattr(resident, "sleep", pause)
    with pytest.raises(ConnectionError):
        await c.preset_flat()
    assert frames(client) == [frame("flat"), frame("stop")]
    coordinator.client.write_gatt_char.assert_not_awaited()


async def test_notification_retry_idempotence_and_stale_callbacks(bed):
    c, coordinator, client = await connected(bed)
    client.start_notify.side_effect = [
        BleakError("busy"),
        BleakError("busy"),
        BleakError("busy"),
        None,
    ]
    await c.start_notify()
    assert [call.args[0] for call in coordinator.mock_sleep.await_args_list] == [0.35, 0.35, 0.3]
    receive = client.start_notify.call_args.args[1]
    await c.start_notify()
    assert client.start_notify.await_count == 4
    receive(client.services[0].characteristics[1], bytearray.fromhex("090b000000000000000003"))
    update = coordinator.handle_controller_state_updates.call_args.args[0]
    assert update.key == resident.MASSAGE_TIMER and update.value == 30
    await c.stop_notify()
    coordinator.handle_controller_state_updates.reset_mock()
    receive(client.services[0].characteristics[1], bytearray.fromhex("090b000000000000000001"))
    coordinator.handle_controller_state_updates.assert_not_called()
    client.stop_notify.assert_awaited_once()


@pytest.mark.parametrize("missing", [codec.WRITE_UUID, resident.NOTIFY_UUID, resident.MODEL_UUID])
async def test_missing_gatt_role_refuses_controls(bed, missing):
    c, _, client = bed
    for service in client.services:
        service.characteristics = [ch for ch in service.characteristics if ch.uuid != missing]
    with pytest.raises(ValueError, match="exact write"):
        await c.async_discover_capabilities()
    with pytest.raises(ConnectionError):
        await c.preset_flat()
    assert not frames(client)


async def test_startup_clock_queries_info_and_timer_init(bed, monkeypatch):
    c, coordinator, client = await connected(bed)
    monkeypatch.setattr(resident.dt_util, "now", lambda: datetime(2026, 11, 10, 7, 8, 9))
    session = SimpleNamespace(async_start_notify=c.start_notify)
    await c.async_on_connect(session)
    assert sorted(frames(client)) == sorted(
        [
            bytes.fromhex("e780017e0a0a070809"),
            resident.QUERY_CLOCK,
            resident.QUERY_MASSAGE,
            resident.QUERY_MASSAGE,
        ]
    )
    client.read_gatt_char.assert_awaited_once_with(client.services[1].characteristics[0])
    assert [call.args[0] for call in coordinator.mock_sleep.await_args_list] == [0.3, 1.0]
    assert sorted(call.args[0] for call in coordinator.mock_pause.await_args_list) == pytest.approx(
        [100, 300], abs=5
    )


async def test_hold_all_controls_validation_and_write_timeout(bed):
    c, coordinator, client = await connected(bed)
    for key in c.held_control_options:
        c.validate_hold_control(key, 500)
    for key, duration in [("wave_mode", 500), ("flat", True), ("flat", 0), ("flat", 60001)]:
        with pytest.raises(ValueError):
            await c.hold_control(key, duration)
    assert not frames(client)
    client.write_gatt_char.side_effect = [TimeoutError("GATT failed"), None, None]
    with pytest.raises(TimeoutError, match="GATT failed"):
        await c.hold_control("flat", 1000)
    assert frames(client) == [frame("flat"), frame("stop"), frame("stop")]


async def test_renewable_motor_hold_refreshes_then_releases_on_expiry(bed, monkeypatch):
    from custom_components.adjustable_bed.command_scheduler import (
        _CURRENT_COMMAND_CONTEXT,
        CommandContext,
        CommandKind,
        HoldLease,
    )
    from tests.hold_lease_wire import virtual_clock

    c, coordinator, client = await connected(bed)
    writes: list[tuple[int, bytes]] = []
    with virtual_clock() as clock:
        # Use the real cancellation/pacing code on the existing virtual clock.
        monkeypatch.setattr(resident, "sleep", asyncio.sleep)

        monkeypatch.setattr(resident, "_pause", _REAL_PAUSE)

        async def write(_char, data, **_kwargs):
            writes.append((round(clock.elapsed * 1000), data))

        client.write_gatt_char.side_effect = write
        context = CommandContext(
            scheduler_token=object(),
            cancel_event=coordinator.cancel_command,
            admitted_stop_epoch=0,
            intent_id="resident-hold",
            kind=CommandKind.HOLD,
            group_id=None,
            resources=frozenset({"motor:back"}),
            lease=HoldLease(owner="card", generation=1, action="up", duration_s=1),
        )
        token = _CURRENT_COMMAND_CONTEXT.set(context)
        try:
            task = asyncio.create_task(c.move_head_up())
        finally:
            _CURRENT_COMMAND_CONTEXT.reset(token)
        await asyncio.wait({task}, timeout=1.05)
        coordinator.cancel_command.set()
        await task
    assert writes == [
        (0, frame("head_up")),
        (300, frame("head_up")),
        (600, frame("head_up")),
        (900, frame("head_up")),
        (1050, frame("stop")),
        (1350, frame("stop")),
    ]


@pytest.mark.usefixtures(
    "mock_bluetooth_api", "mock_establish_connection", "mock_async_ble_device_from_address"
)
async def test_real_coordinator_respects_owned_device_info_reads(hass, mock_bleak_client):
    from unittest.mock import patch

    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_BED_TYPE: BED_TYPE_RESIDENT,
            CONF_DISABLE_ANGLE_SENSING: True,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._max_retries = 1
    # Exercise the coordinator policy with the real controller and GATT roles.
    write = char(codec.WRITE_UUID, ["write"])
    notify = char(resident.NOTIFY_UUID, ["notify"])
    model = char(resident.MODEL_UUID, ["read"])
    services = [
        SimpleNamespace(uuid=codec.SERVICE_UUID, characteristics=[write, notify]),
        SimpleNamespace(uuid=resident.INFO_SERVICE, characteristics=[model]),
    ]
    mock_bleak_client.services.__iter__ = lambda _: iter(services)
    mock_bleak_client.read_gatt_char = AsyncMock(return_value=b"ignored model")
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    mock_bleak_client.write_gatt_char = AsyncMock()
    with (
        patch(
            "custom_components.adjustable_bed.coordinator_connection.read_ble_device_info",
            new_callable=AsyncMock,
        ) as generic_read,
        patch.object(resident, "sleep", AsyncMock()),
        patch.object(resident, "_pause", AsyncMock(return_value=False)),
    ):
        assert await coordinator.async_connect()
        generic_read.assert_not_awaited()
        mock_bleak_client.read_gatt_char.assert_awaited_once_with(model)
        await coordinator.async_disconnect()


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        (
            "move_head_up",
            [(0, "head_up"), (300, "head_up"), (600, "head_up"), (700, "stop"), (1000, "stop")],
        ),
        (
            "massage_off",
            [
                (0, "massage_off"),
                (100, "stop"),
                (200, "query_massage"),
                (400, "stop"),
                (500, "query_massage"),
            ],
        ),
        ("check_massage", [(0, "query_massage"), (300, "query_massage")]),
        ("sync_clock", [(0, "clock"), (100, "query_clock")]),
    ],
)
async def test_deadlines_do_not_add_acknowledged_write_latency(bed, monkeypatch, method, expected):
    from tests.hold_lease_wire import virtual_clock

    c, _, client = await connected(bed)
    writes: list[tuple[int, str]] = []
    names = {frame(key): key for key in RESIDENT.keys}
    names.update({resident.QUERY_MASSAGE: "query_massage", resident.QUERY_CLOCK: "query_clock"})
    with virtual_clock() as clock:
        monkeypatch.setattr(resident, "sleep", asyncio.sleep)
        monkeypatch.setattr(resident, "_pause", _REAL_PAUSE)

        async def write(_char, data, **_kwargs):
            writes.append((round(clock.elapsed * 1000), names.get(data, "clock")))
            await asyncio.sleep(0.1)

        client.write_gatt_char.side_effect = write
        await getattr(c, method)()
    assert writes == expected


@pytest.mark.parametrize("name", ["OKIN-123456", "smartbed123", "SmArTbEd123"])
def test_name_only_advertisements_offer_app_without_a_service_filter(name):
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.test_detection import _make_service_info

    result = detect_bed_type_detailed(_make_service_info(name=name, service_uuids=[]))
    assert BED_TYPE_RESIDENT in {result.bed_type, *(result.ambiguous_types or ())}
    assert result.confidence == 0.3
    assert "name:resident_app_candidate" in result.signals


@pytest.mark.parametrize(
    "metadata",
    ["missing", None, SimpleNamespace(name=None), MagicMock()],
)
@pytest.mark.parametrize(
    ("name", "expected"), [("Unrelated device", None), ("OKIN-123456", BED_TYPE_RESIDENT)]
)
def test_discovery_uses_only_string_names_when_device_metadata_is_incomplete(
    metadata, name, expected
):
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.test_detection import _make_service_info

    info = _make_service_info(name=name, service_uuids=[])
    if metadata == "missing":
        del info.device
    else:
        info.device = metadata
    assert detect_bed_type_detailed(info).bed_type == expected


@pytest.mark.parametrize("selected", ["malouf_new_okin", BED_TYPE_RESIDENT])
def test_resident_search_hint_preserves_explicit_app_and_matching_receiver(selected):
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from custom_components.adjustable_bed.profile_recommendations import recommend_profile
    from tests.test_profile_recommendations import info

    observed = info("Smartbed428000193")
    observed.manufacturer_data = {89: bytes.fromhex("4142010204")}
    detected = detect_bed_type_detailed(observed)
    assert detected.bed_type == "malouf_new_okin"
    assert BED_TYPE_RESIDENT in (detected.ambiguous_types or ())
    assert recommend_profile({CONF_BED_TYPE: selected}, observed, {}) is None
