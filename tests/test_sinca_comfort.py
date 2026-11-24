"""Sinca controls through the factory, shared transport, and current BLE session."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from bleak.exc import BleakError
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.sinca_comfort import controller as runtime
from custom_components.adjustable_bed.codec import mline as wire
from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_PRODUCT_TYPE,
    CONF_PROTOCOL_VARIANT,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.controller_state import ControllerState
from custom_components.adjustable_bed.detection import detect_new_bed
from custom_components.adjustable_bed.errors import BedNotConnectedError
from custom_components.adjustable_bed.profiles import sinca_comfort as app
from custom_components.adjustable_bed.setup_questions import setup_profile_for
from custom_components.adjustable_bed.state_keys import massage_intensity
from tests.hold_lease_wire import virtual_clock


@dataclass
class GattChar:
    uuid: str
    properties: tuple[str, ...]

    @property
    def handle(self) -> int:
        return hash(self.uuid)


def service(uuid: str, *chars: GattChar) -> SimpleNamespace:
    return SimpleNamespace(uuid=uuid, characteristics=chars)


def gatt() -> list[SimpleNamespace]:
    return [
        service(
            wire.NORDIC_SERVICE,
            GattChar(wire.NORDIC_WRITE, ("write-without-response",)),
            GattChar(wire.NORDIC_NOTIFY, ("notify",)),
        ),
        service(wire.FFE_SERVICE, GattChar(wire.FFE_WRITE, ("write-without-response",))),
        service(
            wire.INFO_SERVICE,
            GattChar(wire.FIRMWARE, ("read",)),
            GattChar(wire.PROTOCOL_STRING, ("read",)),
        ),
    ]


@pytest.fixture
def bed() -> tuple[runtime.SincaComfortController, MagicMock, MagicMock]:
    client = MagicMock(is_connected=True, services=gatt())
    client.write_gatt_char = AsyncMock()
    client.read_gatt_char = AsyncMock(side_effect=[b"1.1", b"SENSOR_VOICE"])
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    co = MagicMock(client=client, cancel_command=asyncio.Event())
    co.controller_state = ControllerState()
    co.handle_controller_state_updates.side_effect = lambda *updates: co.controller_state.update(
        (u.key, u.value) for u in updates
    )
    return runtime.SincaComfortController(co, app.PROFILES["sleep"], "four"), co, client


def notifications(client: MagicMock) -> Callable[[str], None]:
    char, callback = client.start_notify.call_args.args
    return lambda hex_data: callback(char, bytearray.fromhex(hex_data))


def frames(client: MagicMock) -> list[str]:
    return [call.args[1].hex() for call in client.write_gatt_char.call_args_list]


@pytest.mark.parametrize(
    ("name", "manufacturer", "expected"),
    [
        ("", {}, "sleep"),
        ("a sleep", {}, "sleep"),
        ("SLEEP SmartBed", {89: b"\0\0\0\0\5"}, "smart"),
        ("SmartBed", {89: b"\5\0\0\0\0"}, "smartsainuo"),
        ("SmartBed OKIN", {89: b"\5\0\0\0\0"}, "okin"),
        ("other", {}, "unknown"),
    ],
)
def test_protocol_classifier(name, manufacturer, expected) -> None:
    assert app.protocol_from_scan(name, manufacturer) == expected


async def test_setup_selects_layout_and_profile_without_granting_single_address_pairing(hass):
    discovered = SimpleNamespace(
        name="Wrong name",
        device=SimpleNamespace(name="MySmartBed"),
        manufacturer_data={89: b"\5\0\0\0\0"},
    )
    for layout, axes in app.LAYOUTS.items():
        data = {
            CONF_BED_TYPE: "sinca_comfort",
            CONF_PROTOCOL_VARIANT: "auto",
            CONF_PRODUCT_TYPE: layout,
        }
        setup = setup_profile_for(data)
        assert setup is not None and setup.seed is not None
        data = setup.seed(hass, data, discovered)
        data.update(setup.settled(data))
        co = MagicMock(hass=hass)
        co.entry.data = data
        controller = await create_controller(co, "sinca_comfort", data[CONF_PROTOCOL_VARIANT], None)
        assert isinstance(controller, runtime.SincaComfortController)
        assert controller.profile.key == "smartsainuo"
        assert tuple(spec.key for spec in controller.motor_control_specs) == axes
        assert not controller.supports_single_address_pairing
        assert not controller.supports_position_feedback
        assert controller.alarm_capability is None
        assert controller.standard_button_hold_spec("program_memory_1") is None
        assert controller.supports_memory_programming
        assert controller.execution.hold == "latched"


def test_discovery_offers_app_only_from_name_and_shared_write_service() -> None:
    def detect(name: str, services: list[str]):
        return detect_new_bed(
            SimpleNamespace(
                name=name,
                address="AA:BB:CC:DD:01:47",
                service_uuids=services,
                manufacturer_data={},
                service_data={},
                device=SimpleNamespace(name=name),
            )
        )

    offered = detect("My Okin", [wire.NORDIC_SERVICE])
    assert "sinca_comfort" in (offered.ambiguous_types or ())
    assert offered.bed_type != "sinca_comfort"
    for result in (
        detect("My Okin", []),
        detect("Generic", [wire.NORDIC_SERVICE]),
        detect("My Okin", [wire.FFE_NOTIFY_SERVICE]),
    ):
        assert "sinca_comfort" not in (result.ambiguous_types or ())


async def test_mixed_gatt_roles_startup_and_independent_state_updates(bed):
    c, co, client = bed
    await c.async_discover_capabilities()
    session = MagicMock(async_start_notify=c.start_notify)
    with virtual_clock():
        await c.async_on_connect(session)
    assert client.start_notify.call_args.args[0].uuid == wire.NORDIC_NOTIFY
    assert all(
        call.args[0].uuid == wire.FFE_WRITE and call.kwargs == {"response": False}
        for call in client.write_gatt_char.call_args_list
    )
    assert [value[:4] for value in frames(client)] == ["0704", "00b0", "00b0"]
    notify = notifications(client)
    notify("a50b000058020315070000000000000106000002")
    assert co.controller_state[runtime.PRIVACY] is True
    assert co.controller_state[runtime.ANTI_SNORE] is True
    assert co.controller_state[runtime.ANTI_SNORE_LEVEL] == "high"
    assert co.controller_state[massage_intensity("all")] == 4
    assert co.controller_state[runtime.MASSAGE_TIMER] == 2
    notify("ed80030725850f")
    assert co.controller_state[runtime.ALARM_TIME] == "07:37"
    notify("a50c00")
    assert co.controller_state[runtime.ALARM_ENABLED] is False
    assert co.controller_state[runtime.ALARM_TIME] is None
    c.on_disconnect()
    await c.async_discover_capabilities()
    notify("a50c0e00050307250001")
    assert co.controller_state[runtime.ALARM_ENABLED] is None
    assert co.controller_state[runtime.PRIVACY] is None


async def test_transport_requires_exact_properties_and_subscription(bed):
    c, _, client = bed
    client.services[1] = service(wire.FFE_SERVICE, GattChar(wire.FFE_WRITE, ("write",)))
    with pytest.raises(BedNotConnectedError, match="missing"):
        await c.async_discover_capabilities()
    client.services = gatt()
    await c.async_discover_capabilities()
    client.start_notify.side_effect = BleakError("subscription failed")
    with virtual_clock(), pytest.raises(BleakError, match="subscription failed"):
        await c.async_on_connect(MagicMock(async_start_notify=c.start_notify))
    assert frames(client) == []


@pytest.mark.parametrize("stalled", [False, True])
async def test_restore_notifications_on_retained_client(bed, stalled):
    c, co, client = bed
    await c.async_discover_capabilities()
    await c.start_notify()
    old_notify = notifications(client)
    original_link = c._live()

    if stalled:

        async def stalled_unsubscribe(_char):
            await asyncio.sleep(5)

        client.stop_notify.side_effect = stalled_unsubscribe
        with virtual_clock() as clock:
            start = clock.now
            with pytest.raises(TimeoutError):
                async with asyncio.timeout(0.05):
                    await c.stop_notify()
            assert clock.now - start == pytest.approx(0.05)
            assert not c.ble_lock.locked()
    else:
        # A failed physical disconnect leaves the coordinator with this client.
        await c.stop_notify()
    await c.start_notify()
    assert c._live() is original_link
    assert client.stop_notify.await_count == 1
    assert client.start_notify.await_count == 2
    old_notify("a50c0e00050307250001")
    assert co.controller_state.get(runtime.ALARM_ENABLED) is None
    notifications(client)("a50c0e00050307250001")
    assert co.controller_state[runtime.ALARM_ENABLED] is True
    await c.lights_toggle()
    assert frames(client) == ["05020002000000"]


async def test_early_sleep_status_waits_only_for_privacy_metadata(bed):
    c, co, client = bed
    await c.async_discover_capabilities()

    async def subscribe(char, callback):
        packet = bytearray.fromhex("a50b000058020315070000000000000106000000")
        callback(char, packet)
        assert co.controller_state.get(runtime.PRIVACY) is None
        assert co.controller_state[runtime.ANTI_SNORE] is True
        assert co.controller_state[massage_intensity("all")] == 4
        packet[19] = 2
        callback(char, packet)
        callback(char, packet[:19])

    client.start_notify.side_effect = subscribe
    with virtual_clock():
        await c.async_on_connect(MagicMock(async_start_notify=c.start_notify))
    assert co.controller_state[runtime.PRIVACY] is True


@pytest.mark.parametrize(
    ("variant", "press", "release", "release_ms"),
    [
        ("sleep", "05020000001000", "05020000000000", 100),
        ("okin", "e6fe161000000000f5", "e6fe16000000000005", 300),
    ],
)
async def test_one_motor_press_and_release_after_external_cancel(
    bed, variant, press, release, release_ms
):
    c, _, client = bed
    c.profile = app.PROFILES[variant]
    await c.async_discover_capabilities()
    times = []

    async def record(*_args, **_kwargs):
        times.append(asyncio.get_running_loop().time())

    client.write_gatt_char.side_effect = record
    with virtual_clock():
        move = asyncio.create_task(c.hold_control("lumbar_up", 2000))
        await asyncio.sleep(0.15)
        move.cancel()
        with pytest.raises(asyncio.CancelledError):
            await move
    assert frames(client) == [press, release]
    assert round((times[1] - times[0]) * 1000) == 150 + release_ms


async def test_replaced_same_client_session_cannot_receive_old_release_or_alarm_repeat(bed):
    c, _, client = bed
    await c.async_discover_capabilities()
    for run, expected in (
        (lambda: c.hold_control("back_up", 500), "05020000000100"),
        (c.alarm_refresh, "00c0"),
    ):
        client.write_gatt_char.reset_mock()
        with virtual_clock():
            waiting = asyncio.create_task(run())
            await asyncio.sleep(0.05)
            await c.async_discover_capabilities()
            if expected == "00c0":
                with pytest.raises(BedNotConnectedError):
                    await waiting
            else:
                await waiting
        assert frames(client) == [expected]


@pytest.mark.parametrize(
    ("variant", "disable", "query", "state"),
    [
        ("sleep", "070500000000000000", "00c0", "00b0"),
        ("okin", "ed80030000000000000000000000008f", "e180039b", "e6fe16000000000005"),
    ],
)
async def test_alarm_followups_and_massage_release_order(bed, variant, disable, query, state):
    c, _, client = bed
    c.profile = app.PROFILES[variant]
    await c.async_discover_capabilities()
    times = []

    async def record(*_args, **_kwargs):
        times.append(asyncio.get_running_loop().time())

    client.write_gatt_char.side_effect = record
    with virtual_clock():
        await c.disable_alarm()
        await c.cycle_massage("head")
    assert frames(client)[:4] == [disable, query, query, query]
    assert [round((t - times[0]) * 1000) for t in times[:4]] == [0, 300, 600, 900]
    assert frames(client)[-3:] == [c.profile.control(0).hex(), state, state]
    assert round((times[-2] - times[-4]) * 1000) == 300


@pytest.mark.parametrize(
    ("chunks", "confirmed", "count", "acknowledged"),
    [
        (["a63000"], False, 0, False),
        (["a63000000002017e00010000"], False, 0, True),
        (["a63000000003017e00010000", "a63100000003017e00010009"], False, 2, True),
        (["a63000000003017e00010000", "a63100000003017e0001000a"], False, 2, False),
        (["a63000000003017e00010000", "a63100000003017e0001000a"], True, 2, True),
    ],
)
async def test_history_ack_gates(bed, chunks, confirmed, count, acknowledged):
    c, _, client = bed
    await c.async_discover_capabilities()
    await c.start_notify()
    notify = notifications(client)
    with virtual_clock():
        transfer = asyncio.create_task(
            c.consume_history(all_records=confirmed, confirmed=confirmed)
        )
        await asyncio.sleep(0.09)
        for chunk in chunks:
            notify(chunk)
        if count and not acknowledged:
            with pytest.raises(ServiceValidationError, match="Confirm"):
                await transfer
        else:
            assert await transfer == (acknowledged, count)
    assert frames(client) == (
        ["01b101" if confirmed else "01b102"] * 2 + (["01b301"] * 2 if acknowledged else [])
    )


async def test_confirmed_history_disconnect_prevents_old_ack(bed):
    c, _, client = bed
    await c.async_discover_capabilities()
    await c.start_notify()
    with virtual_clock():
        transfer = asyncio.create_task(c.consume_history(all_records=True, confirmed=True))
        await asyncio.sleep(0.15)
        notifications(client)("a63000000003017e00010000")
        await c.async_discover_capabilities()
        with pytest.raises(BedNotConnectedError):
            await transfer
    assert frames(client) == ["01b101", "01b101"]


async def test_history_retires_input_before_the_ack_writes(bed):
    c, _, client = bed
    await c.async_discover_capabilities()
    await c.start_notify()
    notify = notifications(client)

    async def write(_char, data, **_kwargs):
        if data == bytes.fromhex("01b301"):
            # Late data after the idle boundary belongs to no admitted transfer.
            notify("a63100000003017e0001000a")

    client.write_gatt_char.side_effect = write
    with virtual_clock():
        transfer = asyncio.create_task(c.consume_history(all_records=False, confirmed=False))
        await asyncio.sleep(0.15)
        notify("a63000000003017e00010000")
        assert await transfer == (True, 1)
    assert frames(client) == ["01b102", "01b102", "01b301", "01b301"]


async def test_history_confirmation_uses_elapsed_time_across_dst(bed, monkeypatch):
    c, _, client = bed
    monkeypatch.setattr(runtime.dt_util, "get_default_time_zone", lambda: ZoneInfo("Europe/Oslo"))
    await c.async_discover_capabilities()
    await c.start_notify()
    notify = notifications(client)
    with virtual_clock():
        transfer = asyncio.create_task(c.consume_history(all_records=False, confirmed=False))
        await asyncio.sleep(0.15)
        # Local 01:55 and 03:05 straddle the spring-forward gap. They are
        # ten minutes apart and both start before the local 06:00 threshold.
        notify("a63000000003017e021d0137")
        notify("a63100000003017e021d0305")
        with pytest.raises(ServiceValidationError, match="Confirm"):
            await transfer
    assert frames(client) == ["01b102", "01b102"]
