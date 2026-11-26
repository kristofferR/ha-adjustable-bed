"""Independence artifact vectors and the HA controls that route them."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.customatic_demo import services
from custom_components.adjustable_bed.beds.customatic_demo.controller import (
    BED_PROBLEM,
    DEMO_MODE,
    LIGHT_TIMER,
    CustomaticDemoController,
)
from custom_components.adjustable_bed.codec import okin_nframe as codec
from custom_components.adjustable_bed.const import BED_TYPE_CUSTOMATIC_DEMO, DOMAIN
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import detect_bed_type_detailed, detect_new_bed
from custom_components.adjustable_bed.errors import BedNotConnectedError
from custom_components.adjustable_bed.profiles import customatic_demo as app
from tests.customatic_demo_vectors import FRAMES
from tests.hold_lease_wire import intervals, leased_hold, virtual_clock
from tests.test_detection import _make_service_info
from tests.test_okin_bedding_apps import _coordinator, written

STOP = [FRAMES["stop"]] * 2
QUERY = "040400000000"


async def connected() -> CustomaticDemoController:
    coordinator = _coordinator()
    coordinator.client.stop_notify = AsyncMock()
    controller = CustomaticDemoController(coordinator)
    await controller.start_notify()
    return controller


def test_frozen_frames() -> None:
    assert {
        key: codec.frame(word, app.PROFILE.width).hex() for key, word in app.PROFILE.keys.items()
    } == FRAMES
    assert app.STATUS_QUERY.hex() == QUERY
    assert codec.frame96(0x01020304, 0xFEDCBA98).hex() == "0c0201020304fedcba9800000000"


@pytest.mark.parametrize("control", [key for key in FRAMES if key != "stop"])
async def test_held_routes_and_neutral_deadlines(control: str) -> None:
    ctrl = await connected()
    times: list[float] = []

    async def record(*_args, **_kwargs):
        times.append(asyncio.get_running_loop().time())
        await asyncio.sleep(0.007)

    ctrl.client.write_gatt_char.side_effect = record
    with virtual_clock():
        await ctrl.hold_control(control, 250)
    assert written(ctrl) == [FRAMES[control]] * 3 + STOP
    assert times == pytest.approx([0, 0.1, 0.2, 0.35, 0.45])
    assert all(call.args[0].handle == 1 for call in ctrl.client.write_gatt_char.call_args_list)


@pytest.mark.parametrize("end", ["expire", "stop"])
async def test_renewable_rotation_hold(end) -> None:
    wire = await leased_hold(
        "customatic_demo",
        lambda ctrl: ctrl.hold_control("rotation_up", 250),
        end_after_s=3,
        end=end,
    )
    assert len(wire.held) > wire.pulse_count
    assert {frame.data.hex() for frame in wire.held} == {FRAMES["rotation_up"]}
    assert intervals(wire.held) == {100}
    assert wire.after and {frame.data.hex() for frame in wire.after} == {FRAMES["stop"]}


async def test_native_motor_and_button_callbacks_and_stop() -> None:
    ctrl = await connected()
    assert {spec.key for spec in ctrl.motor_control_specs} == {"back", "legs", "seat", "rotation"}
    assert not ctrl.execution.concurrent
    assert not ctrl.supports_memory_presets
    assert not ctrl.supports_massage
    with virtual_clock():
        for spec in ctrl.motor_control_specs:
            assert spec.hold.stop_scope == "side"
            for direction, operation in (("up", spec.open_fn), ("down", spec.close_fn)):
                ctrl.client.write_gatt_char.reset_mock()
                await operation(ctrl)
                assert written(ctrl) == [FRAMES[f"{spec.key}_{direction}"]] * 2 + STOP
            ctrl.client.write_gatt_char.reset_mock()
            await spec.stop_fn(ctrl)
            assert written(ctrl) == STOP
        actions = {"auto_flat": ctrl.preset_flat, "light_toggle": ctrl.lights_toggle}
        for spec in ctrl.controller_button_specs:

            async def press(spec=spec):
                await spec.press_fn(ctrl)

            actions[spec.hold.control] = press
        for key, execute in actions.items():
            ctrl.client.write_gatt_char.reset_mock()
            await execute()
            assert written(ctrl) == [FRAMES[key]] + STOP


@pytest.mark.parametrize(
    ("properties", "response"),
    [
        (["write", "write-without-response"], True),
        (["write-without-response"], False),
    ],
)
async def test_startup_subscribes_queries_and_reads_optional_manufacturer(
    properties, response
) -> None:
    ctrl = CustomaticDemoController(_coordinator())
    ctrl.client.services[0].characteristics[0].properties = properties
    events = []

    def record(action):
        async def log(char, *_args, **kwargs):
            events.append((action, char.handle, asyncio.get_running_loop().time(), kwargs))
            return b"Manufacturer"

        return log

    ctrl.client.start_notify.side_effect = record("notify")
    ctrl.client.write_gatt_char.side_effect = record("query")
    ctrl.client.read_gatt_char.side_effect = record("read")
    session = SimpleNamespace(async_start_notify=ctrl.start_notify, store_device_info=MagicMock())
    with virtual_clock():
        await ctrl.async_on_connect(session)
        assert await ctrl.async_read_device_info(session)
        await ctrl.start_notify()  # An extra diagnostic subscriber uses the existing channel.
    assert events == [
        ("notify", 2, 0.0, {}),
        ("query", 1, 0.3, {"response": response}),
        ("read", 3, 1.0, {}),
    ]
    assert written(ctrl) == [QUERY]
    session.store_device_info.assert_called_once_with("Manufacturer", None)


async def test_requires_roles_under_the_cst_service_before_writing() -> None:
    ctrl = CustomaticDemoController(_coordinator())
    ctrl.client.services[0].uuid = "another-service"
    with pytest.raises(BedNotConnectedError, match="command and status"):
        await ctrl.start_notify()
    ctrl.client.start_notify.assert_not_called()
    ctrl.client.write_gatt_char.assert_not_called()


@pytest.mark.parametrize(
    ("data", "timer", "problem", "demo"),
    [
        ([1, 0, 0, 0], 2, False, False),
        ([2, 0, 1, 1, 4, 10], 3, True, True),
        ([3, 0, 0, 3, 8], 5, False, True),
        ([255, 128, 254, 2], None, True, False),
        ([0, 0, 0, 0, 0, 1], None, True, False),
    ],
)
async def test_status_fields_and_stale_callbacks(data, timer, problem, demo) -> None:
    ctrl = await connected()
    ctrl.forward_controller_state_updates = MagicMock()
    receive = ctrl.client.start_notify.call_args.args[1]
    receive(None, bytearray(13))
    ctrl.forward_controller_state_updates.assert_not_called()
    receive(None, bytearray(10) + bytearray(data))
    ctrl.forward_controller_state_updates.assert_called_once_with(
        LIGHT_TIMER(timer),
        BED_PROBLEM(problem),
        DEMO_MODE(demo),
    )
    await ctrl.stop_notify()
    ctrl.forward_controller_state_updates.assert_called_with(
        LIGHT_TIMER(None),
        BED_PROBLEM(None),
        DEMO_MODE(None),
    )
    ctrl.forward_controller_state_updates.reset_mock()
    await ctrl.start_notify()
    receive(None, bytearray(10) + bytearray(data))
    ctrl.forward_controller_state_updates.assert_not_called()


async def test_cancelled_hold_retries_second_neutral_after_first_write_fails() -> None:
    ctrl = await connected()
    cancel = ctrl._coordinator.cancel_command

    async def write(_char, data, **_kwargs):
        if data.hex() == FRAMES["seat_up"]:
            cancel.set()
        elif ctrl.client.write_gatt_char.call_count == 2:
            raise BleakError("transient release failure")

    ctrl.client.write_gatt_char.side_effect = write
    with virtual_clock(), pytest.raises(BleakError, match="transient release failure"):
        await ctrl.hold_control("seat_up", 60000)
    assert written(ctrl) == [FRAMES["seat_up"], *STOP]


async def test_lost_link_cannot_send_release_on_replacement_link() -> None:
    ctrl = await connected()
    old = ctrl.client
    new = _coordinator().client

    async def replaced(*_args, **_kwargs):
        ctrl.on_disconnect()
        ctrl._coordinator.client = new
        ctrl._coordinator.cancel_command.set()

    old.write_gatt_char.side_effect = replaced
    with virtual_clock(), pytest.raises(BedNotConnectedError):
        await ctrl.hold_control("back_up", 250)
    assert written(ctrl) == []


async def test_demo_phase_timing() -> None:
    ctrl = await connected()
    times = []

    async def record(*_args, **_kwargs):
        times.append(asyncio.get_running_loop().time())

    ctrl.client.write_gatt_char.side_effect = record
    with virtual_clock():
        await ctrl.run_demo()
    assert written(ctrl) == [FRAMES["auto_sit"]] * 3 + STOP + [FRAMES["auto_flat"]] * 3 + STOP
    assert times[:5] == pytest.approx([0, 0.1, 0.2, 0.4, 0.5])
    assert times[5:] == pytest.approx([120, 120.1, 120.2, 120.4, 120.5])


@pytest.mark.parametrize("phase", ["auto_sit", "auto_flat"])
@pytest.mark.parametrize("notification", ["problem", "demo_off"])
@pytest.mark.parametrize("queued_refresh", [False, True])
async def test_status_abort_stops_refreshes_and_releases_original_link(
    monkeypatch, phase, notification, queued_refresh
) -> None:
    ctrl = await connected()
    client = ctrl.client
    receive = client.start_notify.call_args.args[1]
    receive(None, bytearray(10) + bytearray([0, 0, 0, 3]))
    phase_frame = FRAMES[phase]
    notice_at = None
    neutral_times = []

    def report() -> None:
        nonlocal notice_at
        notice_at = asyncio.get_running_loop().time()
        payload = bytearray(14)
        if notification == "problem":
            payload[11], payload[13] = 1, 3
        receive(None, payload)

    async def write(_char, data, **_kwargs):
        if not queued_refresh and data.hex() == phase_frame:
            report()
        elif data.hex() == FRAMES["stop"] and notice_at is not None:
            neutral_times.append(asyncio.get_running_loop().time())

    client.write_gatt_char.side_effect = write
    if queued_refresh:
        write_frame = ctrl._write_gatt_with_retry

        async def report_before_refresh(uuid, command, **kwargs):
            if command.hex() == phase_frame and phase_frame in written(ctrl):
                # The press already admitted its refresh, but the writer has
                # not checked the movement under the BLE lock yet.
                report()
            await write_frame(uuid, command, **kwargs)

        monkeypatch.setattr(ctrl, "_write_gatt_with_retry", report_before_refresh)

    with virtual_clock():
        await ctrl.run_demo()

    expected = [phase_frame] + STOP
    if phase == "auto_flat":
        expected = [FRAMES["auto_sit"]] * 3 + STOP + expected
    assert written(ctrl) == expected
    assert notice_at is not None
    assert neutral_times == pytest.approx([notice_at + 0.1, notice_at + 0.2])
    assert ctrl.client is client


@pytest.mark.parametrize(("name", "candidate"), [("oKiN-X", True), ("other", False)])
def test_discovery_offers_only_an_explicit_candidate(name, candidate) -> None:
    info = _make_service_info(name=name, service_uuids=[codec.SERVICE_UUID])
    info.device.name = name
    detailed = detect_bed_type_detailed(info)
    result = detect_new_bed(info)
    assert result.bed_type == detailed.bed_type != BED_TYPE_CUSTOMATIC_DEMO
    assert (BED_TYPE_CUSTOMATIC_DEMO in (result.ambiguous_types or [])) is candidate


@pytest.mark.parametrize("stop_during", ["hold", "pause"])
async def test_confirmed_action_uses_the_live_scheduler_and_stop_never_moves(
    hass, stop_during
) -> None:
    services.register_services(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=5,
        title="Independence",
        data={
            "address": "AA:BB:CC:DD:EE:FF",
            "bed_type": "customatic_demo",
            "motor_count": 4,
            "disable_angle_sensing": True,
            "idle_disconnect_seconds": 0,
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    coordinator = AdjustableBedCoordinator(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        **coordinator.device_info,
    )
    client = _coordinator().client
    client.stop_notify = AsyncMock()
    client.disconnect = AsyncMock()
    coordinator._client = client
    ctrl = await create_controller(coordinator, BED_TYPE_CUSTOMATIC_DEMO, None, client)
    assert isinstance(ctrl, CustomaticDemoController)
    coordinator._controller = ctrl
    await ctrl.start_notify()
    started = asyncio.Event()

    async def write(_char, data, **_kwargs):
        if (
            stop_during == "hold"
            and data.hex() == FRAMES["auto_sit"]
            or stop_during == "pause"
            and client.write_gatt_char.call_count == 5
        ):
            started.set()

    client.write_gatt_char.side_effect = write
    arguments = {"device_id": device.id}
    try:
        with pytest.raises(ServiceValidationError, match="confirmation"):
            await hass.services.async_call(DOMAIN, "customatic_demo_run", arguments, blocking=True)
        assert written(ctrl) == []
        with (
            patch.object(coordinator, "async_ensure_connected", AsyncMock(return_value=True)),
            patch.object(coordinator, "async_connect", AsyncMock(return_value=True)),
            virtual_clock(),
        ):
            run = asyncio.create_task(
                hass.services.async_call(
                    DOMAIN,
                    "customatic_demo_run",
                    {**arguments, "confirm": True},
                    blocking=True,
                )
            )
            async with asyncio.timeout(2):
                await started.wait()
            if stop_during == "pause":
                # Let the admitted operation transition from release to its wait.
                await asyncio.sleep(0.001)
            await coordinator.async_stop_command()
            await run
        expected = [FRAMES["auto_sit"], *STOP]
        if stop_during == "pause":
            expected = [FRAMES["auto_sit"]] * 3 + STOP + STOP
        assert written(ctrl) == expected
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize(
    ("stalled", "controls", "attempts", "finished"),
    [
        ("movement", 1, [0.4, 0.5], 0.5),
        ("first_neutral", 3, [0.4, 5.4], 5.4),
        ("both_neutrals", 3, [0.4, 5.4], 10.4),
    ],
)
async def test_stalled_demo_writes_are_bounded_and_cannot_start_flat(
    stalled, controls, attempts, finished
) -> None:
    ctrl = await connected()
    neutral_attempts = []

    async def write(_char, data, **_kwargs):
        if data.hex() == FRAMES["stop"]:
            neutral_attempts.append(asyncio.get_running_loop().time())
            if stalled == "both_neutrals" or (
                stalled == "first_neutral" and len(neutral_attempts) == 1
            ):
                await asyncio.Future()
        elif stalled == "movement":
            await asyncio.Future()

    ctrl.client.write_gatt_char.side_effect = write
    with virtual_clock(), pytest.raises(TimeoutError):
        try:
            await ctrl.run_demo()
        finally:
            assert asyncio.get_running_loop().time() == pytest.approx(finished)
    assert neutral_attempts == pytest.approx(attempts)
    assert written(ctrl) == [FRAMES["auto_sit"]] * controls + STOP


async def test_an_overrun_sit_phase_cannot_advance_to_flat(monkeypatch) -> None:
    ctrl = await connected()
    # The actual gap is two minutes. Move the deadline inside the neutral
    # window to simulate an overrun without relying on a stalled backend.
    monkeypatch.setattr(app, "DEMO_PHASE_S", 0.45)
    with virtual_clock(), pytest.raises(TimeoutError):
        await ctrl.run_demo()
    assert written(ctrl) == [FRAMES["auto_sit"]] * 3 + STOP


async def test_flat_write_revalidates_pair_stop_epoch_at_wire_admission(monkeypatch) -> None:
    ctrl = await connected()
    stop_epoch = 0
    write_frame = ctrl._write_gatt_with_retry

    async def advance_epoch_before_flat(uuid, command, **kwargs):
        nonlocal stop_epoch
        if command.hex() == FRAMES["auto_flat"]:
            # Change only the pair epoch after the upper phase admission checks.
            # Leave the child cancel event clear to exercise the GATT guard itself.
            stop_epoch += 1
        await write_frame(uuid, command, **kwargs)

    monkeypatch.setattr(ctrl, "_write_gatt_with_retry", advance_epoch_before_flat)
    with virtual_clock(), pytest.raises(asyncio.CancelledError):
        await ctrl.run_demo(still_admitted=lambda: stop_epoch == 0)
    assert stop_epoch == 1
    assert written(ctrl) == [FRAMES["auto_sit"]] * 3 + STOP + STOP
