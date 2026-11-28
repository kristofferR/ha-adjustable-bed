"""Dynasty Base A native callers, captured-session safety and app schedules."""

import asyncio
from datetime import datetime
from operator import methodcaller
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.keeson import dynasty_base_a as bed
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles import dynasty_base_a as app
from tests.hold_lease_wire import virtual_clock
from tests.test_dynasty_base_a_vectors import VECTORS

ADDRESS = "AA:BB:CC:DD:16:30"


class Char:
    def __init__(self, uuid, handle, properties):
        self.uuid, self.handle, self.properties = uuid, handle, properties
        self.descriptors = []


class Services(list):
    def get_service(self, uuid):
        return next((s for s in self if s.uuid == uuid), None)


def gatt(route, *, both=False):
    def char(uuid, handle, properties):
        return Char(uuid, handle, properties)

    def service(uuid, chars):
        return SimpleNamespace(
            uuid=uuid,
            characteristics=chars,
            get_characteristic=lambda uuid: next((c for c in chars if c.uuid == uuid), None),
        )

    p1, p2 = app.codec.TRANSPORTS["base"], app.codec.TRANSPORTS["dynasty_p2"]
    result = Services()
    if route == "p1" or both:
        result.extend(
            [
                service(p1.service_uuid, [char(p1.write_uuid, 1, ["write"])]),
                service(app.NOTIFY_SERVICE, [char(p1.notify_uuid, 2, ["notify"])]),
            ]
        )
    if route == "p2" or both:
        result.append(
            service(
                p2.service_uuid,
                [
                    char(p2.write_uuid, 3, ["write-without-response"]),
                    char(p2.notify_uuid, 4, ["read"]),
                ],
            )
        )
    return result


def entry(hass, layout="40"):
    from custom_components.adjustable_bed.setup_questions import _dynasty_base_a_settings

    e = MockConfigEntry(
        domain=const.DOMAIN,
        title="Dynasty Base A",
        unique_id=ADDRESS,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Dynasty Base A",
            const.CONF_BED_TYPE: "dynasty_base_a",
            const.CONF_PROTOCOL_VARIANT: layout,
            **_dynasty_base_a_settings({const.CONF_PROTOCOL_VARIANT: layout}),
        },
    )
    e.add_to_hass(hass)
    return e


def written(client):
    return [bytes(c.args[1]) for c in client.write_gatt_char.call_args_list]


async def connected(hass, client, route, layout="40", *, both=False):
    client.services = gatt(route, both=both)
    client.read_gatt_char.side_effect = None
    client.read_gatt_char.return_value = bytearray()
    target = AdjustableBedCoordinator(hass, entry(hass, layout))
    assert await target.async_connect()
    assert isinstance(target.controller, bed.DynastyBaseAController)
    client.write_gatt_char.reset_mock()
    client.read_gatt_char.reset_mock()
    return target, target.controller


@pytest.mark.parametrize("route", ["p1", "p2"])
async def test_every_live_control_through_coordinator(
    hass, mock_coordinator_connected, mock_bleak_client, route
):
    client = mock_bleak_client
    target, ctrl = await connected(hass, client, route, both=route == "p2")
    assert ctrl.route == route
    assert not ctrl.supports_memory_programming
    assert not ctrl.supports_single_address_pairing
    assert ctrl.execution.declared == {"hold"}
    assert not ctrl.position_number_specs
    assert not ctrl.supports_massage_intensity_control
    with virtual_clock():
        for row in VECTORS:
            if row["protocol"].lower() != route or "mask" not in row["inputs"]:
                continue
            client.write_gatt_char.reset_mock()
            client.read_gatt_char.reset_mock()
            word = row["inputs"]["mask"]
            branch_read = route == "p2" and word in (0x200000, 0x2000000)
            client.read_gatt_char.return_value = bytearray(
                [0] * 10 + [0 if word == 0x2000000 else 255]
            )
            expected = bytes.fromhex(row["expected_bytes"])
            zero = app.frame(route, 0)
            if word == 0:
                command = methodcaller("stop_all")

                sequence = [zero] * 3
            elif word in {v for pair in app.AXES.values() for v in pair}:
                control = next(k for k, v in app.controls(route, "40").items() if v == word)

                command = methodcaller("hold_control", control, 100)

                sequence = [zero] * 3 + [expected] + [zero] * 3
            elif word == app.CHORD:
                command = methodcaller("hold_control", "flat_zero_g", 100)

                sequence = [expected]
            elif word in ctrl.profile.presets.values():
                key = next(k for k, v in ctrl.profile.presets.items() if v == word)

                command = methodcaller("_preset", key)

                sequence = [expected] * 3 + [zero]
            elif word in ctrl.profile.memory.values():
                n = next(n for n, v in ctrl.profile.memory.items() if v == word)

                command = methodcaller("preset_memory", n)

                sequence = [expected] * 3 + [zero]
            elif word == app.LIGHT:
                command = methodcaller("lights_toggle")

                sequence = [expected] * 3 + [zero] * 2
            else:
                if route == "p2" and word == 0x2000000:
                    ctrl._massage_on = True
                    key = "massage_power"
                else:
                    ctrl._massage_on = False
                    key = next(k for k, v in app.actions(route).items() if v == word)

                command = methodcaller("action", key)

                sequence = (
                    [expected]
                    if route == "p2" and key in ("foot_massage", "massage_power")
                    else [expected] * 3 + [zero] * 2
                )
            await target.async_execute_controller_command(command)
            assert written(client) == sequence, row["id"]
            assert client.read_gatt_char.call_count == (len(sequence) + branch_read if route == "p2" else 0)
            assert all(
                call.kwargs["response"] == (route == "p1")
                for call in client.write_gatt_char.call_args_list
            )
    await target.async_shutdown()


@pytest.mark.parametrize("route", ["p1", "p2"])
@pytest.mark.parametrize("layout", app.LAYOUTS)
async def test_native_entities_and_setup(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, route, layout
):
    from custom_components.adjustable_bed.app_profiles import per_side_profile
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES
    from custom_components.adjustable_bed.profile_id import resolve_profile_id
    from tests.form_helpers import finish_new_bed

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._app_after_device = "manual_entry"
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    await flow.async_step_select_app()
    await flow.async_step_select_app(
        {const.CONF_BED_TYPE: BED_TYPE_DISPLAY_NAMES["dynasty_base_a"]}
    )
    result = await flow.async_step_manual_entry({"address": ADDRESS})
    assert result["step_id"] == "profile_questions"
    result = await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: layout})
    await finish_new_bed(flow, result)
    saved = flow._finish_with_verify.await_args.args[0]
    assert saved[const.CONF_MOTOR_COUNT] == len(app.LAYOUTS[layout])
    assert resolve_profile_id(saved) == f"dynasty_base_a:{layout}"
    assert per_side_profile("dynasty_base_a", layout).variant_owned
    client = mock_bleak_client
    client.read_gatt_char.side_effect = None
    client.services, client.read_gatt_char.return_value = gatt(route), bytearray([0] * 10 + [255])
    e = entry(hass, layout)
    assert await hass.config_entries.async_setup(e.entry_id)
    from custom_components.adjustable_bed.runtime_data import loaded_runtime

    target = loaded_runtime(hass, e.entry_id)
    assert {s.key for s in target.controller.motor_control_specs} == set(app.LAYOUTS[layout])
    registry = er.async_get(hass)
    client.write_gatt_char.reset_mock()
    with virtual_clock():
        for spec in target.controller.controller_button_specs:
            entity = registry.async_get_entity_id("button", const.DOMAIN, f"{ADDRESS}_{spec.key}")
            assert entity is not None, spec.key
            await hass.services.async_call("button", "press", {"entity_id": entity}, blocking=True)
        device = next(
            v.device_id for v in registry.entities.values() if v.config_entry_id == e.entry_id
        )
        await hass.services.async_call(
            const.DOMAIN,
            "set_alarm",
            {
                "device_id": device,
                "enabled": True,
                "time": "06:30:00",
                "weekdays": ["monday", "tuesday", "wednesday", "thursday", "friday"],
                "wake_action": "memory_1",
            },
            blocking=True,
        )
    assert app.alarm(6, 30, 190, 17) in written(client)
    assert await hass.config_entries.async_unload(e.entry_id)


@pytest.mark.parametrize("route", ["p1", "p2"])
async def test_alarm_enable_disable_and_clock_order(
    hass, mock_coordinator_connected, mock_bleak_client, route
):
    client = mock_bleak_client
    target, ctrl = await connected(hass, client, route)
    now = datetime(2026, 11, 27, 6, 0, 0)
    try:
        with virtual_clock():
            for days, expected in [((), 32), ((0, 1, 2, 3, 4), 190), (tuple(range(7)), 255)]:
                client.write_gatt_char.reset_mock()
                request = AlarmRequest(
                    enabled=True,
                    hour=6,
                    minute=30,
                    weekdays=days,
                    wake_action="memory_1",
                    reference_time=now,
                )
                await target.async_execute_controller_command(
                    lambda c, request=request: c.configure_alarm(request)
                )
                frames = written(client)
                assert len(frames) == 3
                assert frames[0].startswith(b"\xe7\x80\x01")
                assert frames[1:] == [app.alarm(6, 30, expected, 17), app.frame(route, 0)]
            client.write_gatt_char.reset_mock()
            request = AlarmRequest(enabled=False, reference_time=now)
            await target.async_execute_controller_command(
                lambda c, request=request: c.configure_alarm(request)
            )
            assert written(client) == [app.alarm(0, 0, 0, 0)] * 2 + [app.frame(route, 0)]
    finally:
        await target.async_shutdown()


async def test_notification_fragments_signed_light_and_stale_session(
    hass, mock_coordinator_connected, mock_bleak_client
):
    target, ctrl = await connected(hass, mock_bleak_client, "p1")
    char, receive = mock_bleak_client.start_notify.call_args.args
    prefix = bytearray(20)
    prefix[:3], prefix[18], prefix[19] = b"\xf4\xfe\x16", 0x40, 2
    receive(char, prefix)
    assert target.controller_state.get(bed.TIMER) is None
    receive(char, bytearray(3))
    assert target.controller_state[bed.TIMER] == 20
    assert target.controller_state[bed.UNDER_BED_LIGHTS_ON] is True
    # The original prefix remains cached, rather than consuming successive fragments.
    receive(char, bytearray(3))
    assert target.controller_state[bed.TIMER] == 20
    raw = bytearray(10)
    raw[7], raw[8] = 0x80, 3
    receive(char, raw)
    assert target.controller_state[bed.UNDER_BED_LIGHTS_ON] is False
    assert target.controller_state[bed.TIMER] == 30
    ctrl.on_disconnect()
    receive(char, raw)
    assert target.controller_state[bed.TIMER] is None
    await target.async_shutdown()


@pytest.mark.parametrize("interrupt", ["event", "task", "slow", "replacement"])
async def test_motion_cleanup_and_deadline(
    hass, mock_coordinator_connected, mock_bleak_client, interrupt
):
    client = mock_bleak_client
    target, ctrl = await connected(hass, client, "p1")
    move = app.frame("p1", 1)
    zero = app.frame("p1", 0)
    with virtual_clock():

        async def effect(_char, payload, **_kwargs):
            if bytes(payload) != move:
                return
            if interrupt == "event":
                target.cancel_command.set()
            elif interrupt == "task":
                asyncio.current_task().cancel()
                await asyncio.sleep(0)
            elif interrupt == "slow":
                await asyncio.sleep(0.4)
            else:
                target._address = "AA:BB:CC:DD:16:31"

        client.write_gatt_char.side_effect = effect
        command = (
            ctrl.hold_control("head_up", 200)
            if interrupt == "task"
            else target.async_execute_controller_command(lambda c: c.hold_control("head_up", 200))
        )
        if interrupt == "task":
            with pytest.raises(asyncio.CancelledError):
                await command
        elif interrupt == "replacement":
            with pytest.raises(ConnectionError):
                await command
        else:
            await command
    assert written(client) == [zero] * 3 + [move] + (
        [] if interrupt == "replacement" else [zero] * 3
    )
    client.write_gatt_char.side_effect = None
    await target.async_shutdown()


async def test_p2_status_power_and_preset_hold_release(
    hass, mock_coordinator_connected, mock_bleak_client
):
    client = mock_bleak_client
    target, ctrl = await connected(hass, client, "p2")
    raw = bytearray(11)
    raw[10] = 2
    client.read_gatt_char.return_value = raw
    with virtual_clock():
        await target.async_execute_controller_command(lambda c: c.action("foot_massage"))
        assert target.controller_state[bed.TIMER] == 20
        assert target.controller_state.get(bed.UNDER_BED_LIGHTS_ON) is None
        client.write_gatt_char.reset_mock()
        await target.async_execute_controller_command(lambda c: c.action("massage_power"))
        assert written(client) == [app.frame("p2", 0x2000000)]
        client.write_gatt_char.reset_mock()
        await target.async_execute_controller_command(lambda c: c.hold_control("memory_1", 250))
        assert written(client) == [app.frame("p2", 0x10000)] * 3
        await target.async_stop_command()
        assert written(client) == [app.frame("p2", 0x10000)] * 3 + [app.frame("p2", 0)] * 3
        ctrl.validate_hold_control("memory_1", 8001)
    await target.async_shutdown()


async def test_missing_p2_write_does_not_fall_back(
    hass, mock_coordinator_connected, mock_bleak_client
):
    target, ctrl = await connected(hass, mock_bleak_client, "p1")
    services = gatt("p2", both=True)
    services[-1].characteristics.pop(0)
    mock_bleak_client.services = services
    with pytest.raises(BleakError):
        await ctrl.async_discover_capabilities()
    with pytest.raises(ConnectionError):
        await ctrl.preset_flat()
    await target.async_shutdown()


@pytest.mark.parametrize("length,light,timer", [(10, 7, 8), (16, 13, 14), (23, 18, 19)])
def test_all_signed_status_bytes(length, light, timer):
    for value in range(256):
        packet = bytearray(length)
        packet[light] = packet[timer] = value
        status = app.status("p1", bytes(packet))
        assert status is not None
        minutes, on, power = status
        assert minutes == {1: 10, 2: 20, 3: 30}.get(value & 15, 0)
        assert on == (64 <= value <= 127)
        assert power is None


def test_frozen_gatt_roles_and_pair_ownership():
    from custom_components.adjustable_bed.pairing import effective_child_data

    assert app.codec.TRANSPORTS["base"].service_uuid == "0000ffe5-0000-1000-8000-00805f9b34fb"
    assert app.codec.TRANSPORTS["base"].write_uuid == "0000ffe9-0000-1000-8000-00805f9b34fb"
    assert app.NOTIFY_SERVICE == "0000ffe0-0000-1000-8000-00805f9b34fb"
    assert app.codec.TRANSPORTS["base"].notify_uuid == "0000ffe4-0000-1000-8000-00805f9b34fb"
    assert app.codec.TRANSPORTS["dynasty_p2"].service_uuid == "62741523-52f9-8864-b1ab-3b3a8d65950b"
    assert app.codec.TRANSPORTS["dynasty_p2"].write_uuid == "62741525-52f9-8864-b1ab-3b3a8d65950b"
    assert app.codec.TRANSPORTS["dynasty_p2"].notify_uuid == "62741625-52f9-8864-b1ab-3b3a8d65950b"
    pair = {
        const.CONF_BED_TYPE: "dynasty_base_a",
        const.CONF_PAIR_CHILDREN: [
            {
                const.CONF_SIDE: "left",
                const.CONF_BED_TYPE: "dynasty_base_a",
                const.CONF_PROTOCOL_VARIANT: "31",
                const.CONF_MOTOR_COUNT: 3,
            },
            {
                const.CONF_SIDE: "right",
                const.CONF_BED_TYPE: "dynasty_base_a",
                const.CONF_PROTOCOL_VARIANT: "20",
                const.CONF_MOTOR_COUNT: 2,
            },
        ],
    }
    left = effective_child_data(
        pair, "left", {const.CONF_PROTOCOL_VARIANT: "40", const.CONF_MOTOR_COUNT: 4}
    )
    assert left[const.CONF_PROTOCOL_VARIANT] == "31"
    assert left[const.CONF_MOTOR_COUNT] == 3


async def test_p2_failed_write_still_reads_and_unknown_power_clears(
    hass, mock_coordinator_connected, mock_bleak_client
):
    client = mock_bleak_client
    target, ctrl = await connected(hass, client, "p2")
    client.write_gatt_char.side_effect = BleakError("failed")
    raw = bytearray(11)
    raw[10] = 255
    client.read_gatt_char.return_value = raw
    with pytest.raises(BleakError):
        await ctrl.action("foot_massage")
    assert client.read_gatt_char.call_count == 1
    assert not ctrl._massage_on
    assert target.controller_state[bed.TIMER] == 0
    client.write_gatt_char.side_effect = None
    await target.async_shutdown()


@pytest.mark.parametrize("route", ["p1", "p2"])
async def test_missing_receive_role_never_gates_control(
    hass, mock_coordinator_connected, mock_bleak_client, route
):
    client = mock_bleak_client
    target, ctrl = await connected(hass, client, route)
    await ctrl.stop_notify()
    if route == "p1":
        client.services.pop()
    else:
        client.services[0].characteristics.pop()
    await ctrl.async_discover_capabilities()
    await ctrl.start_notify()
    await target.async_execute_controller_command(lambda c: c.preset_flat())
    assert written(client) == [app.frame(route, 0x08000000)] * 3 + [app.frame(route, 0)]
    await target.async_shutdown()


@pytest.mark.parametrize("route", ["p1", "p2"])
def test_shared_advertisements_offer_explicit_app_choice(route):
    from unittest.mock import MagicMock

    from custom_components.adjustable_bed.detection import detect_bed_type_detailed

    info = MagicMock()
    info.name = info.device.name = info.advertisement.local_name = "Unknown name"
    info.manufacturer_data = {}
    info.service_uuids = info.advertisement.service_uuids = [
        app.codec.TRANSPORTS[app.PROFILES[route].transport].service_uuid
    ]
    result = detect_bed_type_detailed(info)
    assert "dynasty_base_a" in {result.bed_type, *(result.ambiguous_types or ())}
    if result.bed_type == "dynasty_base_a":
        assert result.confidence < 0.8


@pytest.mark.parametrize("control", ["flat", "memory_1", "flat_zero_g"])
async def test_dashboard_preset_lease_admission_renewal_and_eight_second_cap(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, control
):
    from custom_components.adjustable_bed.runtime_data import loaded_runtime

    client = mock_bleak_client
    client.services = gatt("p1")
    e = entry(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    target = loaded_runtime(hass, e.entry_id)
    registry = er.async_get(hass)
    device = next(
        v.device_id for v in registry.entities.values() if v.config_entry_id == e.entry_id
    )
    request = {
        "device_id": device,
        "control": control,
        "duration": 0.3,
        "hold_owner": "card",
        "hold_generation": 1,
    }

    async def renew():
        await hass.services.async_call(const.DOMAIN, "hold_control", request, blocking=True)

    client.write_gatt_char.reset_mock()
    with virtual_clock() as clock:
        started = clock.now
        active = asyncio.create_task(renew())
        for _ in range(85):
            await asyncio.sleep(0.1)
            if active.done():
                break
            await renew()
        await active
        assert 8 <= clock.now - started < 8.2
        assert len(written(client)) == 80
        assert set(written(client)) == {app.frame("p1", app.controls("p1", "40")[control])}
        await target.async_stop_command()
        assert written(client)[-3:] == [app.frame("p1", 0)] * 3
    assert await hass.config_entries.async_unload(e.entry_id)


@pytest.mark.parametrize("preparation_end", ["ready", "cancel", "replacement"])
async def test_movement_budget_starts_after_three_status_reads(
    hass, mock_coordinator_connected, mock_bleak_client, preparation_end
):
    client = mock_bleak_client
    target, ctrl = await connected(hass, client, "p2")
    reads = 0
    with virtual_clock() as clock:
        started = clock.now
        motion_times = []

        async def read(_char):
            nonlocal reads
            reads += 1
            await asyncio.sleep(0.04)
            if reads == 3:
                if preparation_end == "cancel":
                    target.cancel_command.set()
                elif preparation_end == "replacement":
                    target._address = "AA:BB:CC:DD:16:31"
            return bytearray([0] * 10 + [255])

        async def write(_char, data, **_kwargs):
            if bytes(data) == app.frame("p2", 1):
                motion_times.append(clock.now - started)

        client.read_gatt_char.side_effect, client.write_gatt_char.side_effect = read, write
        if preparation_end == "replacement":
            with pytest.raises(ConnectionError):
                await ctrl.hold_control("head_up", 100)
        else:
            await ctrl.hold_control("head_up", 100)
        assert motion_times == ([pytest.approx(0.12)] if preparation_end == "ready" else [])
    client.write_gatt_char.side_effect = None
    await target.async_shutdown()


@pytest.mark.parametrize("route", ["p1", "p2"])
@pytest.mark.parametrize(
    "properties, response",
    [
        (["write"], True),
        (["write-without-response"], False),
        (["write", "write-without-response"], False),
    ],
)
async def test_android_default_write_preference(
    hass, mock_coordinator_connected, mock_bleak_client, route, properties, response
):
    client = mock_bleak_client
    target, ctrl = await connected(hass, client, route)
    ctrl._link.write.properties = properties
    await ctrl.async_discover_capabilities()
    await ctrl.preset_flat()
    assert all(c.kwargs["response"] is response for c in client.write_gatt_char.call_args_list)
    await target.async_shutdown()


@pytest.mark.parametrize("write_fails", [False, True])
async def test_optional_status_timeout_preserves_command_result(
    hass, mock_coordinator_connected, mock_bleak_client, write_fails
):
    client = mock_bleak_client
    target, ctrl = await connected(hass, client, "p2")
    client.read_gatt_char.side_effect = TimeoutError("optional read timeout")
    if write_fails:
        client.write_gatt_char.side_effect = BleakError("original write failure")
        with pytest.raises(BleakError, match="original write failure"):
            await ctrl.action("foot_massage")
    else:
        await ctrl.action("foot_massage")
    assert client.read_gatt_char.call_count == 1
    client.write_gatt_char.side_effect = None
    await target.async_shutdown()


async def test_stop_cleanup_bounds_hanging_optional_reads(
    hass, mock_coordinator_connected, mock_bleak_client
):
    client = mock_bleak_client
    target, ctrl = await connected(hass, client, "p2")

    drained = asyncio.Event()

    async def hanging(_char):
        await drained.wait()
        return bytearray([0] * 10 + [255])

    client.read_gatt_char.side_effect = hanging
    with virtual_clock() as clock:
        started = clock.now
        await target.async_stop_command()
        assert clock.now - started == pytest.approx(bed.STATUS_READ_TIMEOUT_S)
        assert written(client) == [app.frame("p2", 0)] * 3
        pending = ctrl._status_read
        assert pending is not None and not pending.task.done()
        drained.set()
        await pending.task
    await target.async_shutdown()


@pytest.mark.parametrize("where", ["before_write", "mid_write"])
async def test_cancelled_or_skipped_write_does_not_read_status(
    hass, mock_coordinator_connected, mock_bleak_client, where
):
    client = mock_bleak_client
    target, ctrl = await connected(hass, client, "p2")
    ctrl._massage_on = True
    with virtual_clock():
        if where == "before_write":
            async with ctrl._ble_lock:
                active = asyncio.create_task(ctrl.write_command(app.frame("p2", 1)))
                await asyncio.sleep(0)
                target.cancel_command.set()
            await active
            client.write_gatt_char.assert_not_called()
        else:
            started = asyncio.Event()

            async def hanging(*_args, **_kwargs):
                started.set()
                await asyncio.Event().wait()

            client.write_gatt_char.side_effect = hanging
            active = asyncio.create_task(ctrl.write_command(app.frame("p2", 1)))
            await started.wait()
            active.cancel()
            with pytest.raises(asyncio.CancelledError):
                await active
        client.read_gatt_char.assert_not_called()
        assert ctrl._massage_on is (True if where == "before_write" else None)
    client.write_gatt_char.side_effect = None
    await target.async_shutdown()


async def test_stop_of_active_preset_ends_only_that_gesture(
    hass, mock_coordinator_connected, mock_bleak_client
):
    client = mock_bleak_client
    target, ctrl = await connected(hass, client, "p1")
    with virtual_clock():
        active = asyncio.create_task(
            target.async_execute_controller_command(lambda c: c.hold_control("flat", 1000))
        )
        await asyncio.sleep(0.15)
        await target.async_stop_command()
        await active
        assert set(written(client)) == {app.frame("p1", 0x08000000)}
        await target.async_stop_command()
        assert written(client)[-3:] == [app.frame("p1", 0)] * 3
    await target.async_shutdown()


@pytest.mark.parametrize("power, word", [(255, 0x200000), (0, 0x2000000), (3, 0x2000000)])
async def test_reconnected_power_reads_before_choosing_branch(
    hass, mock_coordinator_connected, mock_bleak_client, power, word
):
    client = mock_bleak_client
    target, ctrl = await connected(hass, client, "p2")
    ctrl._massage_on = True
    await ctrl.async_discover_capabilities()
    assert ctrl._massage_on is None
    order = []

    async def read(_char):
        order.append("read")
        return bytearray([0] * 10 + [power])

    async def write(*_args, **_kwargs):
        order.append("write")

    client.read_gatt_char.side_effect, client.write_gatt_char.side_effect = read, write
    await target.async_execute_controller_command(lambda c: c.action("massage_power"))
    assert order == ["read", "write", "read"]
    assert written(client) == [app.frame("p2", word)]
    client.write_gatt_char.side_effect = None
    await target.async_shutdown()


@pytest.mark.parametrize("cached,current,word", [(True, 255, 0x200000), (False, 0, 0x2000000)])
async def test_power_refreshes_even_a_confirmed_cache(
    hass, mock_coordinator_connected, mock_bleak_client, cached, current, word
):
    client = mock_bleak_client
    target, ctrl = await connected(hass, client, "p2")
    ctrl._massage_on = cached  # A physical remote or timer can change it afterwards.
    client.read_gatt_char.return_value = bytearray([0] * 10 + [current])
    await target.async_execute_controller_command(lambda c: c.action("massage_power"))
    assert client.read_gatt_char.call_count == 2  # Fresh branch read and post-write read.
    assert written(client) == [app.frame("p2", word)]
    await target.async_shutdown()


@pytest.mark.parametrize("control", ["head_up", "flat"])
async def test_slow_post_write_status_preserves_every_hold_refresh(
    hass, mock_coordinator_connected, mock_bleak_client, control
):
    client = mock_bleak_client
    target, ctrl = await connected(hass, client, "p2")
    word = app.controls("p2", "40")[control]
    motion, zero = app.frame("p2", word), app.frame("p2", 0)
    events = []
    last_write = zero
    with virtual_clock() as clock:
        started = clock.now

        async def write(_char, payload, **_kwargs):
            nonlocal last_write
            last_write = bytes(payload)
            events.append((clock.now - started, last_write))

        async def read(_char):
            if last_write == motion:
                await asyncio.sleep(0.25)
            return bytearray([0] * 10 + [255])

        client.write_gatt_char.side_effect, client.read_gatt_char.side_effect = write, read
        await target.async_execute_controller_command(lambda c: c.hold_control(control, 400))
        assert [t for t, p in events if p == motion] == pytest.approx([0, 0.1, 0.2, 0.3])
        if control == "head_up":
            assert [t for t, p in events if p == zero][-3:] == pytest.approx([0.4] * 3)
        pending = ctrl._status_read
        if pending is not None:
            await pending.task
    client.write_gatt_char.side_effect = None
    await target.async_shutdown()


@pytest.mark.parametrize("route", ["p1", "p2"])
@pytest.mark.parametrize("layout", ["20", "30", "31", "40"])
async def test_wire_scenario_builds_its_actual_layout(route, layout):
    import json

    from tests.test_wire_snapshot import _load_tool

    tool = _load_tool()
    sid = "dynasty_base_a" if (route, layout) == ("p1", "40") else f"dynasty_base_a:{route}:{layout}"
    scenario = next(s for s in tool.build_scenarios() if s.id == sid)
    layouts = json.loads(tool.LAYOUTS_PATH.read_text())
    client = tool.FakeClient(tool.Recorder(tool.FakeClock()), layouts[scenario.layout_id], scenario.replies)
    ctrl = await tool._build(scenario, client)
    assert ctrl.layout == layout
    assert set(ctrl.held_control_options) & {"tilt_up", "lumbar_up"} == {
        f"{axis}_up" for axis in app.LAYOUTS[layout] if axis in ("tilt", "lumbar")
    }
    assert {s.key for s in ctrl.motor_control_specs} == set(app.LAYOUTS[layout])
    snapshot = json.loads(tool.SNAPSHOT_PATH.read_text())["scenarios"][sid]["commands"]
    for axis in ("tilt", "lumbar"):
        command = snapshot[f"{axis}_up"]
        if axis in app.LAYOUTS[layout]:
            assert command["status"] == "ok"
            assert any(w[3] == app.frame(route, app.AXES[axis][0]).hex() for w in command["writes"])
            assert f"cover:{axis}_open" in snapshot
        else:
            assert command["status"] == "error" and command["error"] == "ValueError"
            assert not command["writes"]
            assert f"cover:{axis}_open" not in snapshot


@pytest.mark.parametrize("result", ["timeout", "short", "absent"])
@pytest.mark.parametrize("cached", [None, False, True])
async def test_unknown_power_never_guesses_a_command(
    hass, mock_coordinator_connected, mock_bleak_client, result, cached
):
    from tests.error_helpers import raises_key

    client = mock_bleak_client
    target, ctrl = await connected(hass, client, "p2")
    ctrl._massage_on = cached
    if result == "timeout":
        client.read_gatt_char.side_effect = TimeoutError("no status")
    elif result == "absent":
        client.services[0].characteristics.pop()
        await ctrl.async_discover_capabilities()
    with raises_key(
        "dynasty_base_a_reconnect_required"
        if result == "timeout"
        else "dynasty_base_a_status_required"
    ):
        await target.async_execute_controller_command(lambda c: c.action("massage_power"))
    client.write_gatt_char.assert_not_called()
    await target.async_shutdown()


async def test_alarm_exact_current_minute_selects_tomorrow(
    hass, mock_coordinator_connected, mock_bleak_client
):
    client = mock_bleak_client
    target, ctrl = await connected(hass, client, "p1")
    request = AlarmRequest(
        enabled=True, hour=6, minute=30, reference_time=datetime(2026, 11, 27, 6, 30)
    )
    with virtual_clock():
        await target.async_execute_controller_command(lambda c: c.configure_alarm(request))
    assert written(client)[1] == app.alarm(6, 30, 64, 0)  # Saturday, not Friday.
    await target.async_shutdown()


@pytest.mark.parametrize("end", ["deadline", "cancel"])
async def test_native_movement_status_read_cannot_delay_release(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, end
):
    from custom_components.adjustable_bed.runtime_data import loaded_runtime

    client = mock_bleak_client
    client.services = gatt("p2")
    e = entry(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    target = loaded_runtime(hass, e.entry_id)
    registry = er.async_get(hass)
    device = next(
        v.device_id for v in registry.entities.values() if v.config_entry_id == e.entry_id
    )
    motion, zero = app.frame("p2", 1), app.frame("p2", 0)
    events = []
    reading_motion = False
    reads_active = 0
    drain_read = asyncio.Event()
    with virtual_clock() as clock:
        started = clock.now

        async def write(_char, payload, **_kwargs):
            nonlocal reading_motion
            reading_motion = bytes(payload) == motion
            events.append((clock.now - started, bytes(payload)))

        async def read(_char):
            nonlocal reads_active
            if reading_motion:
                reads_active += 1
                try:
                    if end == "cancel":
                        await asyncio.sleep(0.04)
                        target.cancel_command.set()
                    await drain_read.wait()
                finally:
                    reads_active -= 1
            return bytearray([0] * 10 + [255])

        client.write_gatt_char.side_effect, client.read_gatt_char.side_effect = write, read
        await hass.services.async_call(
            const.DOMAIN,
            "hold_control",
            {
                "device_id": device,
                "control": "head_up",
                "duration": 0.1,
            },
            blocking=True,
        )
        assert [payload for _, payload in events] == [zero] * 3 + [motion] + [zero] * 3
        assert events[4][0] == pytest.approx(0.1 if end == "deadline" else 0.04)
        assert reads_active == 1
        pending = target.controller._status_read
        assert pending is not None and not pending.task.done()
        drain_read.set()
        await pending.task
        assert reads_active == 0
        assert target.controller._massage_on is None
    client.write_gatt_char.side_effect = None
    assert await hass.config_entries.async_unload(e.entry_id)


@pytest.mark.parametrize("missing", ["timeout", "short", "bleak_error"])
async def test_native_power_toggle_requires_confirmation_after_changed_write(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, missing
):
    from custom_components.adjustable_bed.runtime_data import loaded_runtime
    from tests.error_helpers import raises_key

    client = mock_bleak_client
    client.services = gatt("p2")
    client.read_gatt_char.side_effect = None
    client.read_gatt_char.return_value = bytearray([0] * 11)  # Current power is on.
    e = entry(hass)
    assert await hass.config_entries.async_setup(e.entry_id)
    target = loaded_runtime(hass, e.entry_id)
    registry = er.async_get(hass)

    async def press(key):
        entity = registry.async_get_entity_id(
            "button", const.DOMAIN, f"{ADDRESS}_dynasty_base_a_{key}"
        )
        assert entity is not None
        await hass.services.async_call("button", "press", {"entity_id": entity}, blocking=True)

    await press("foot_massage")
    assert target.controller._massage_on is True
    client.write_gatt_char.reset_mock()
    client.read_gatt_char.return_value = bytearray()
    failure = {
        "timeout": TimeoutError("status timeout"),
        "short": bytearray(),
        "bleak_error": BleakError("status failed"),
    }[missing]
    fresh = True

    async def read(_char):
        nonlocal fresh
        if fresh:
            fresh = False
            return bytearray([0] * 11)
        if isinstance(failure, Exception):
            raise failure
        return failure

    client.read_gatt_char.side_effect = read
    await press("massage_power")
    assert written(client) == [app.frame("p2", 0x2000000)]
    assert target.controller._massage_on is None
    error = (
        "dynasty_base_a_status_required"
        if missing == "short"
        else "dynasty_base_a_reconnect_required"
    )
    with raises_key(error):
        await press("massage_power")
    assert written(client) == [app.frame("p2", 0x2000000)]
    client.read_gatt_char.side_effect = None
    client.read_gatt_char.return_value = bytearray([0] * 10 + [255])  # Fresh off status.
    if missing == "short":
        await press("massage_power")
        assert written(client) == [app.frame("p2", 0x2000000), app.frame("p2", 0x200000)]
    else:
        with raises_key("dynasty_base_a_reconnect_required"):
            await press("massage_power")
    assert await hass.config_entries.async_unload(e.entry_id)


@pytest.mark.parametrize("missing", ["timeout", "short"])
async def test_failed_power_write_invalidates_cache_until_valid_status(
    hass, mock_coordinator_connected, mock_bleak_client, missing
):
    from tests.error_helpers import raises_key

    client = mock_bleak_client
    target, ctrl = await connected(hass, client, "p2")
    ctrl._massage_on = True
    client.write_gatt_char.side_effect = BleakError("original power write failure")
    fresh = True

    async def read(_char):
        nonlocal fresh
        if fresh:
            fresh = False
            return bytearray([0] * 11)
        if missing == "timeout":
            raise TimeoutError("read failed")
        return bytearray()

    client.read_gatt_char.side_effect = read
    with pytest.raises(BleakError, match="original power write failure"):
        await target.async_execute_controller_command(lambda c: c.action("massage_power"))
    assert ctrl._massage_on is None
    client.write_gatt_char.side_effect = None
    with raises_key(
        "dynasty_base_a_reconnect_required"
        if missing == "timeout"
        else "dynasty_base_a_status_required"
    ):
        await target.async_execute_controller_command(lambda c: c.action("massage_power"))
    assert written(client) == [app.frame("p2", 0x2000000)]
    await target.async_shutdown()


async def test_optional_status_from_retired_session_never_updates_power(
    hass, mock_coordinator_connected, mock_bleak_client
):
    client = mock_bleak_client
    target, ctrl = await connected(hass, client, "p2")
    ctrl._massage_on = True

    async def replace(_char):
        target._address = "AA:BB:CC:DD:16:31"
        return bytearray([0] * 10 + [255])

    client.read_gatt_char.side_effect = replace
    with pytest.raises(ConnectionError):
        await target.async_execute_controller_command(lambda c: c.action("massage_power"))
    assert ctrl._massage_on is None
    assert written(client) == []  # Session changed during the mandatory branch read.
    await target.async_shutdown()
