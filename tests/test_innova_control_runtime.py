"""Public settings, native entities, pairing admission and grouping teardown."""

import asyncio
from contextlib import asynccontextmanager, nullcontext, suppress
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const, services
from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.richmat_classic.controller import BEFORE_SETTINGS_WRITE
from custom_components.adjustable_bed.beds.richmat_classic.homezone import HomeZoneReceive
from custom_components.adjustable_bed.beds.richmat_classic.innova_control import (
    AROMA_PAUSE_3,
    AROMA_START_2,
    AROMA_START_3,
)
from custom_components.adjustable_bed.beds.richmat_classic.resource_protocol import Request
from custom_components.adjustable_bed.command_scheduler import current_command_context
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.light import _light_entities_for
from custom_components.adjustable_bed.number import _number_entities_for
from custom_components.adjustable_bed.state_keys import UNDER_BED_LIGHTS_ON, UNDER_BED_LIGHTS_RGB
from tests.hold_lease_wire import virtual_clock
from tests.test_entity_sweep import async_setup_platforms_and_sweep
from tests.test_innova_control import controller, packets
from tests.test_richmat_classic_transport import Services, channel, route

AROMA_KEYS = (AROMA_START_2, AROMA_START_3, AROMA_PAUSE_3)


@pytest.fixture
async def runtime(hass, monkeypatch, request):
    layout = getattr(request, "param", "BTRM")
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            "address": "AA:BB:CC:DD:EE:66",
            "bed_type": const.BED_TYPE_RICHMAT_CLASSIC_APPS,
            "protocol_variant": "innova2",
            "product_type": layout,
            "ble_device_name": "BTRM-bed",
            "motor_pulse_count": 1,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    ctrl, double = controller(layout)
    ctrl._coordinator = coordinator
    coordinator._controller = ctrl
    coordinator._client = double.client
    coordinator._is_connected = True

    async def disconnected():
        double.client.is_connected = False

    double.client.disconnect = AsyncMock(side_effect=disconnected)

    async def connected(reset_timer=True):
        return True

    await services.async_register_services(hass)
    monkeypatch.setattr(coordinator, "async_ensure_connected", connected)
    monkeypatch.setattr(services, "_call_targets", lambda call: [(coordinator, "both")])
    monkeypatch.setattr(
        services, "_resolve_sided_targets", lambda *args, **kwargs: ([(coordinator, "both")], [])
    )
    yield coordinator, ctrl, double
    await coordinator.async_shutdown()


async def test_public_stop_uses_admitted_mode(hass, runtime):
    _, ctrl, double = runtime
    ctrl._select("mode", "2")
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN, "stop_all", {"device_id": ["bed"]}, blocking=True
        )
    assert packets(double) == ["6e01026edf"]


async def test_native_capability_entities_disappear_safely_after_disconnect(hass, runtime):
    coordinator, ctrl, _ = runtime
    ctrl._receive = HomeZoneReceive(light_capable=True, aroma_capable=True)
    assert len(ctrl.controller_number_specs) == 4
    assert await async_setup_platforms_and_sweep(hass, coordinator.entry, coordinator)
    ctrl.on_disconnect()
    assert ctrl.controller_number_specs == ()
    assert (
        "controller_number_innova_control_aroma_start_2" in ctrl.unavailable_controller_entity_keys
    )


async def test_public_settings_native_alarm_and_no_default_replay(hass, runtime):
    _, ctrl, double = runtime
    ctrl._receive.light_capable = True
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN,
            "innova_control",
            {"device_id": ["bed"], "operation": "lamp_timeout", "seconds": 256},
            blocking=True,
        )
    assert packets(double) == ["6e0b01007a"]
    ctrl, double = controller("A9RM")
    request = AlarmRequest(
        enabled=True,
        hour=6,
        minute=0,
        wake_action="zero_g",
        massage=True,
        massage_zone="head",
        reference_time=datetime(2026, 1, 2, 5, tzinfo=UTC),
    )
    with virtual_clock():
        await ctrl.configure_alarm(request)
    assert len(packets(double)) == 2
    assert packets(double)[1][6:8] == "7c"
    ctrl.restore_persisted_app_state({"wire": "RAW", "lamp_rgb": "abcdef", "mode": 2})
    assert ctrl._mode == 0 and "lamp_rgb" not in ctrl.persisted_app_state


@pytest.mark.parametrize("runtime", ["YGRM"], indirect=True)
async def test_registered_rgb_updates_native_light_and_its_next_colorless_turn_on(hass, runtime):
    coordinator, ctrl, double = runtime
    ctrl._receive.light_capable = True
    coordinator.handle_controller_state_update(UNDER_BED_LIGHTS_RGB, (7, 8, 9))
    lamp = next(
        light for light in _light_entities_for(hass, coordinator)
        if light.entity_description.key == "under_bed_lights"
    )
    lamp.async_write_ha_state = MagicMock()
    unregister = coordinator.register_controller_state_callback(lamp._handle_light_state)
    try:
        assert lamp.rgb_color == (7, 8, 9)
        with virtual_clock():
            await hass.services.async_call(
                const.DOMAIN, "innova_control",
                {"device_id": ["bed"], "operation": "rgb", "rgb_color": [18, 52, 86]},
                blocking=True,
            )
            assert coordinator.controller_state[UNDER_BED_LIGHTS_RGB] == (18, 52, 86)
            assert lamp.rgb_color == (18, 52, 86)
            await lamp.async_turn_on()
        assert packets(double) == ["6e0cff128b6e0d345605", "6e0cff128b6e0d345605"]
    finally:
        unregister()


async def test_registered_rgb_failed_write_preserves_previous_color(hass, runtime):
    coordinator, ctrl, double = runtime
    ctrl._receive.light_capable = True
    coordinator.handle_controller_state_update(UNDER_BED_LIGHTS_RGB, (7, 8, 9))
    double.client.write_gatt_char.side_effect = BleakError("RGB write failed")
    with virtual_clock(), pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            const.DOMAIN, "innova_control",
            {"device_id": ["bed"], "operation": "rgb", "rgb_color": [18, 52, 86]},
            blocking=True,
        )
    assert coordinator.controller_state[UNDER_BED_LIGHTS_RGB] == (7, 8, 9)


async def test_registered_rgb_skipped_write_preserves_previous_color(hass, runtime):
    coordinator, ctrl, double = runtime
    ctrl._receive.light_capable = True
    coordinator.handle_controller_state_update(UNDER_BED_LIGHTS_RGB, (7, 8, 9))
    token = BEFORE_SETTINGS_WRITE.set(lambda: False)
    try:
        with virtual_clock():
            await hass.services.async_call(
                const.DOMAIN, "innova_control",
                {"device_id": ["bed"], "operation": "rgb", "rgb_color": [18, 52, 86]},
                blocking=True,
            )
    finally:
        BEFORE_SETTINGS_WRITE.reset(token)
    assert packets(double) == []
    assert coordinator.controller_state[UNDER_BED_LIGHTS_RGB] == (7, 8, 9)


async def test_registered_rgb_cancelled_inflight_write_publishes_only_after_delivery(hass, runtime):
    coordinator, ctrl, double = runtime
    ctrl._receive.light_capable = True
    coordinator.handle_controller_state_update(UNDER_BED_LIGHTS_RGB, (7, 8, 9))
    entered, finish = asyncio.Event(), asyncio.Event()
    admitted = []

    async def write(*args, **kwargs):
        context = current_command_context()
        assert context is not None
        admitted.append(context.cancel_event)
        entered.set()
        await finish.wait()

    double.client.write_gatt_char.side_effect = write
    with virtual_clock():
        task = asyncio.create_task(hass.services.async_call(
            const.DOMAIN, "innova_control",
            {"device_id": ["bed"], "operation": "rgb", "rgb_color": [18, 52, 86]},
            blocking=True,
        ))
        await entered.wait()
        admitted[0].set()
        await asyncio.sleep(0)
        assert not task.done()
        assert coordinator.controller_state[UNDER_BED_LIGHTS_RGB] == (7, 8, 9)
        finish.set()
        await task
    assert coordinator.controller_state[UNDER_BED_LIGHTS_RGB] == (18, 52, 86)
    assert packets(double) == ["6e0cff128b6e0d345605"]


@pytest.mark.parametrize("change", ("disconnect", "session", "client"))
async def test_registered_rgb_never_republishes_after_link_change(hass, runtime, change):
    coordinator, ctrl, double = runtime
    ctrl._receive.light_capable = True
    old = ctrl._session

    async def write(*args, **kwargs):
        if change == "disconnect":
            double.client.is_connected = False
            ctrl.on_disconnect()
        elif change == "session":
            ctrl._session = replace(old)
            coordinator.handle_controller_state_update(UNDER_BED_LIGHTS_RGB, (7, 8, 9))
        else:
            client = MagicMock(is_connected=True, stop_notify=AsyncMock())

            async def disconnected():
                client.is_connected = False

            client.disconnect = AsyncMock(side_effect=disconnected)
            coordinator._client = client
            coordinator.handle_controller_state_update(UNDER_BED_LIGHTS_RGB, (7, 8, 9))

    double.client.write_gatt_char.side_effect = write
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN, "innova_control",
            {"device_id": ["bed"], "operation": "rgb", "rgb_color": [18, 52, 86]},
            blocking=True,
        )
    assert coordinator.controller_state[UNDER_BED_LIGHTS_RGB] == (
        None if change == "disconnect" else (7, 8, 9)
    )
    assert packets(double) == ["6e0cff128b6e0d345605"]


async def test_registered_aroma_updates_each_native_number(hass, runtime):
    coordinator, ctrl, double = runtime
    ctrl._receive.aroma_capable = True
    numbers = {
        number.entity_description.key: number
        for number in _number_entities_for(hass, coordinator)
        if number.entity_description.key.startswith("controller_number_innova_control_aroma_")
    }
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN, "innova_control",
            {"device_id": ["bed"], "operation": "aroma", "aroma_times": [1, 60, 12]},
            blocking=True,
        )
    assert tuple(coordinator.controller_state.get(key) for key in AROMA_KEYS) == (1, 60, 12)
    assert {
        key: number.native_value for key, number in numbers.items()
    } == {
        "controller_number_innova_control_aroma_start_2": 1,
        "controller_number_innova_control_aroma_start_3": 60,
        "controller_number_innova_control_aroma_pause_3": 12,
    }
    assert packets(double) == ["6e1b00018a", "6e1c003cc6", "6e1d000c97"]


@pytest.mark.parametrize("failure_at", (1, 2, 3))
async def test_registered_aroma_failure_retains_each_completed_setting(hass, runtime, failure_at):
    coordinator, ctrl, double = runtime
    ctrl._receive.aroma_capable = True
    previous, requested = (2, 3, 4), (1, 60, 12)
    coordinator.handle_controller_state_updates(*(k(v) for k, v in zip(AROMA_KEYS, previous, strict=True)))
    attempts = 0

    async def write(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == failure_at:
            raise BleakError("Aroma write failed")

    double.client.write_gatt_char.side_effect = write
    with virtual_clock(), pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            const.DOMAIN, "innova_control",
            {"device_id": ["bed"], "operation": "aroma", "aroma_times": requested},
            blocking=True,
        )
    assert attempts == failure_at
    assert tuple(coordinator.controller_state[k] for k in AROMA_KEYS) == (
        requested[:failure_at - 1] + previous[failure_at - 1:]
    )


async def test_registered_aroma_keeps_before_write_guard_for_each_setting(hass, runtime):
    coordinator, ctrl, double = runtime
    ctrl._receive.aroma_capable = True
    coordinator.handle_controller_state_updates(*(k(v) for k, v in zip(AROMA_KEYS, (2, 3, 4), strict=True)))
    checked = 0

    def before_write():
        nonlocal checked
        checked += 1
        return checked == 1

    token = BEFORE_SETTINGS_WRITE.set(before_write)
    try:
        with virtual_clock():
            await hass.services.async_call(
                const.DOMAIN, "innova_control",
                {"device_id": ["bed"], "operation": "aroma", "aroma_times": [1, 60, 12]},
                blocking=True,
            )
    finally:
        BEFORE_SETTINGS_WRITE.reset(token)
    assert checked == 3
    assert packets(double) == ["6e1b00018a"]
    assert tuple(coordinator.controller_state[k] for k in AROMA_KEYS) == (1, 3, 4)


@pytest.mark.parametrize("cancel_at", (1, 2, 3))
async def test_registered_aroma_cancel_drains_and_publishes_only_completed_settings(
    hass, runtime, cancel_at
):
    coordinator, ctrl, double = runtime
    ctrl._receive.aroma_capable = True
    previous, requested = (2, 3, 4), (1, 60, 12)
    coordinator.handle_controller_state_updates(*(k(v) for k, v in zip(AROMA_KEYS, previous, strict=True)))
    entered, finish = asyncio.Event(), asyncio.Event()
    pending = []
    attempts = 0

    async def write(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == cancel_at:
            context = current_command_context()
            assert context is not None
            pending.append(context.cancel_event)
            entered.set()
            await finish.wait()

    double.client.write_gatt_char.side_effect = write
    with virtual_clock():
        task = asyncio.create_task(hass.services.async_call(
            const.DOMAIN, "innova_control",
            {"device_id": ["bed"], "operation": "aroma", "aroma_times": requested},
            blocking=True,
        ))
        await entered.wait()
        pending[0].set()
        await asyncio.sleep(0)
        assert not task.done()
        assert tuple(coordinator.controller_state[k] for k in AROMA_KEYS) == (
            requested[:cancel_at - 1] + previous[cancel_at - 1:]
        )
        finish.set()
        await task
    assert attempts == cancel_at
    assert tuple(coordinator.controller_state[k] for k in AROMA_KEYS) == (
        requested[:cancel_at] + previous[cancel_at:]
    )


async def test_aroma_task_cancellation_drains_one_setting_without_sending_the_next(runtime):
    coordinator, ctrl, double = runtime
    ctrl._receive.aroma_capable = True
    coordinator.handle_controller_state_updates(*(k(v) for k, v in zip(AROMA_KEYS, (2, 3, 4), strict=True)))
    entered, finish = asyncio.Event(), asyncio.Event()

    async def write(*args, **kwargs):
        if len(packets(double)) == 2:
            entered.set()
            await finish.wait()

    double.client.write_gatt_char.side_effect = write
    with virtual_clock():
        task = asyncio.create_task(coordinator.async_execute_controller_command(
            lambda c: c.execute_request(Request("aroma", aroma_times=(1, 60, 12))),
            resource="configuration",
        ))
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert tuple(coordinator.controller_state[k] for k in AROMA_KEYS) == (1, 3, 4)
        finish.set()
        with suppress(asyncio.CancelledError):
            await task
    assert packets(double) == ["6e1b00018a", "6e1c003cc6"]
    assert tuple(coordinator.controller_state[k] for k in AROMA_KEYS) == (1, 60, 4)


@pytest.mark.parametrize("change", ("disconnect", "session", "client"))
@pytest.mark.parametrize("change_at", (1, 3))
async def test_registered_aroma_never_publishes_or_continues_on_replaced_link(
    hass, runtime, change, change_at
):
    coordinator, ctrl, double = runtime
    ctrl._receive.aroma_capable = True
    old = ctrl._session

    async def write(*args, **kwargs):
        if len(packets(double)) != change_at:
            return
        if change == "disconnect":
            double.client.is_connected = False
            ctrl.on_disconnect()
        elif change == "session":
            ctrl._session = replace(old)
        else:
            client = MagicMock(is_connected=True, stop_notify=AsyncMock())

            async def disconnected():
                client.is_connected = False

            client.disconnect = AsyncMock(side_effect=disconnected)
            coordinator._client = client
        if change != "disconnect":
            coordinator.handle_controller_state_updates(*(k(v) for k, v in zip(AROMA_KEYS, (9, 8, 7), strict=True)))

    double.client.write_gatt_char.side_effect = write
    with virtual_clock(), (pytest.raises(ConnectionError) if change_at == 1 else nullcontext()):
        await hass.services.async_call(
            const.DOMAIN, "innova_control",
            {"device_id": ["bed"], "operation": "aroma", "aroma_times": [1, 60, 12]},
            blocking=True,
        )
    assert tuple(coordinator.controller_state[k] for k in AROMA_KEYS) == (
        (None, None, None) if change == "disconnect" else (9, 8, 7)
    )
    assert len(packets(double)) == change_at


async def test_preflight_rejects_invalid_second_side_before_first_write(hass, runtime, monkeypatch):
    coordinator, ctrl, double = runtime
    other = AdjustableBedCoordinator(hass, coordinator.entry)
    bad, stub = controller("D9RM")
    bad._coordinator = other
    other._controller = bad
    other._client = stub.client
    other._is_connected = True

    async def disconnected():
        stub.client.is_connected = False

    stub.client.disconnect = AsyncMock(side_effect=disconnected)

    async def connected(reset_timer=True):
        return True

    monkeypatch.setattr(other, "async_ensure_connected", connected)
    monkeypatch.setattr(
        services,
        "_resolve_sided_targets",
        lambda *args, **kwargs: ([(coordinator, "both"), (other, "both")], []),
    )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            const.DOMAIN,
            "innova_control",
            {"device_id": ["bed"], "operation": "massage_popup", "popup": "15"},
            blocking=True,
        )
    assert packets(double) == packets(stub) == []
    await other.async_shutdown()


async def test_group_write_and_cleanup_are_bound_to_original_link():
    ctrl, coord = controller()
    group = route(0)
    group.uuid = "0000ffe0-0000-1000-8000-00805f9b34fb"
    write = channel("0000ffe2-0000-1000-8000-00805f9b34fb", "write")
    notify = channel("0000ffe1-0000-1000-8000-00805f9b34fb", "notify")
    group.characteristics = [write, notify]
    coord.client.services = Services([group])
    closed = []

    @asynccontextmanager
    async def guard():
        async def disconnect(reason):
            closed.append(reason)
            coord.client.is_connected = False
            return True

        yield disconnect

    coord.async_connection_operation_guard = guard
    with virtual_clock():
        await ctrl.async_group("1234")
    assert packets(coord) == ["41542b47524f5550313233340d0a"]
    assert coord.client.write_gatt_char.await_args.args[0] is write
    assert closed == ["innova_control_group"]


async def test_stop_epoch_fences_later_side_after_first_side_wait(hass, runtime, monkeypatch):
    coordinator, ctrl, double = runtime
    ctrl._receive.light_capable = True
    original = ctrl.validate_request
    checked = False

    def validate(request, *, live=True):
        nonlocal checked
        original(request, live=live)
        if not checked:
            checked = True
            epoch = coordinator.command_scheduler.request_stop()
            coordinator.command_scheduler.finish_stop(epoch)

    monkeypatch.setattr(ctrl, "validate_request", validate)
    with virtual_clock():
        try:
            await hass.services.async_call(
                const.DOMAIN,
                "innova_control",
                {"device_id": ["bed"], "operation": "lamp_timeout", "seconds": 60},
                blocking=True,
            )
        except ServiceValidationError:
            pass
    assert packets(double) == []


async def test_real_paired_runtime_keeps_own_wire_and_side_settings(hass, monkeypatch):
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    children = {}
    doubles = {}
    for side, wire, address in [
        ("left", "RAW", "AA:BB:CC:DD:EE:71"),
        ("right", "FRAMED", "AA:BB:CC:DD:EE:72"),
    ]:
        entry = MockConfigEntry(
            domain=const.DOMAIN,
            data={
                "address": address,
                "name": side,
                "bed_type": const.BED_TYPE_RICHMAT_CLASSIC_APPS,
                "protocol_variant": "innova2",
                "product_type": "6BRM",
                "connection_mode": "idle",
            },
        )
        entry.add_to_hass(hass)
        child = AdjustableBedCoordinator(hass, entry)
        ctrl, double = controller(wire=wire)
        ctrl._coordinator = child
        child._client = double.client
        child._controller = ctrl
        child.async_ensure_connected = AsyncMock(return_value=True)
        child._async_refresh_controller_auth = AsyncMock()

        async def disconnect(client=double.client):
            client.is_connected = False

        double.client.disconnect = AsyncMock(side_effect=disconnect)
        children[side], doubles[side] = child, double
    entry = MockConfigEntry(domain=const.DOMAIN, data={"pair_id": "innova-control", "name": "Pair"})
    pair = PairedBedCoordinator(hass, entry, children, connection_mode="concurrent")
    await services.async_register_services(hass)
    monkeypatch.setattr(
        services, "_resolve_sided_targets", lambda *args, **kwargs: ([(pair, "both")], [])
    )
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN,
            "hold_control",
            {"device_id": "bed", "control": "richmat_classic_1", "duration": 0.2},
            blocking=True,
        )
    assert packets(doubles["left"])[0] == "34"
    assert packets(doubles["left"])[-1] == "6e"
    assert packets(doubles["right"])[0] == "6e01002493"
    assert packets(doubles["right"])[-1] == "6e01006edd"
    for double in doubles.values():
        double.client.write_gatt_char.reset_mock()
    monkeypatch.setattr(
        services, "_resolve_sided_targets", lambda *args, **kwargs: ([(pair, "right")], [])
    )
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN,
            "innova_control",
            {"device_id": "bed", "operation": "query"},
            blocking=True,
        )
    assert packets(doubles["left"]) == []
    assert packets(doubles["right"]) == ["6e0a000179", "6e1a000088"]
    for child in children.values():
        await child.async_shutdown()


@pytest.mark.parametrize("layout", ("FDRM", "FFRM"))
async def test_second_zero_g_alarm_preserves_own_layout_tag(layout):
    ctrl, double = controller(layout)
    assert "zero_g_2" in ctrl.alarm_capability.wake_actions
    request = AlarmRequest(
        enabled=True,
        hour=6,
        minute=0,
        wake_action="zero_g_2",
        reference_time=datetime(2026, 1, 2, 5, tzinfo=UTC),
    )
    with virtual_clock():
        await ctrl.configure_alarm(request)
    assert packets(double)[1][6:8] == "6b"
    with pytest.raises(ServiceValidationError):
        ctrl.validate_alarm(replace(request, massage=True, massage_zone="both"))


@pytest.mark.parametrize("operation", ("lamp_timeout", "rgb", "aroma", "join_group"))
async def test_live_batch_rejects_incapable_second_target_before_any_write(
    hass, runtime, monkeypatch, operation
):
    coordinator, first, double = runtime
    first._receive.light_capable = first._receive.aroma_capable = True
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={**coordinator.entry.data, "address": "AA:BB:CC:DD:EE:77"},
    )
    entry.add_to_hass(hass)
    other = AdjustableBedCoordinator(hass, entry)
    second, stub = controller("BTRM")
    second._coordinator = other
    other._controller, other._client = second, stub.client
    other._is_connected = True
    other.async_ensure_connected = AsyncMock(return_value=True)

    async def disconnected():
        stub.client.is_connected = False

    stub.client.disconnect = AsyncMock(side_effect=disconnected)
    if operation == "join_group":
        group = route(0)
        group.uuid = "0000ffe0-0000-1000-8000-00805f9b34fb"
        group.characteristics = [
            channel("0000ffe2-0000-1000-8000-00805f9b34fb", "write"),
            channel("0000ffe1-0000-1000-8000-00805f9b34fb", "notify"),
        ]
        double.client.services, stub.client.services = Services([group]), Services([])
    arguments = {
        "lamp_timeout": {"seconds": 60},
        "rgb": {"rgb_color": [18, 52, 86]},
        "aroma": {"aroma_times": [12, 15, 2]},
        "join_group": {"group": "1234"},
    }[operation]
    monkeypatch.setattr(
        services,
        "_resolve_sided_targets",
        lambda *args, **kwargs: ([(coordinator, "both"), (other, "both")], []),
    )
    try:
        with virtual_clock(), pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                const.DOMAIN,
                "innova_control",
                {"device_id": ["bed"], "operation": operation, **arguments},
                blocking=True,
            )
        assert packets(double) == packets(stub) == []
        other.async_ensure_connected.assert_not_awaited()
    finally:
        await other.async_shutdown()


@pytest.mark.parametrize("kind", ("aroma", "rgb"))
@pytest.mark.parametrize("change", ("disconnect", "session", "client"))
async def test_native_settings_never_republish_after_link_change(runtime, kind, change):
    coordinator, ctrl, double = runtime
    ctrl._receive.aroma_capable = ctrl._receive.light_capable = True
    key = AROMA_START_2 if kind == "aroma" else UNDER_BED_LIGHTS_RGB
    replacement_value = 7 if kind == "aroma" else (7, 8, 9)
    old = ctrl._session

    async def write(*args, **kwargs):
        if change == "disconnect":
            double.client.is_connected = False
            ctrl.on_disconnect()
        elif change == "session":
            ctrl._session = replace(old)
            coordinator.handle_controller_state_update(key, replacement_value)
        else:
            client = MagicMock(is_connected=True, stop_notify=AsyncMock())

            async def disconnected():
                client.is_connected = False

            client.disconnect = AsyncMock(side_effect=disconnected)
            coordinator._client = client
            coordinator.handle_controller_state_update(key, replacement_value)

    double.client.write_gatt_char.side_effect = write
    with virtual_clock():
        if kind == "aroma":
            spec = next(
                s for s in ctrl.controller_number_specs if s.key == "innova_control_aroma_start_2"
            )
            await spec.set_fn(ctrl, 12)
        else:
            await ctrl.set_light_color((18, 52, 86))
    assert coordinator.controller_state[key] == (
        None if change == "disconnect" else replacement_value
    )
    assert len(packets(double)) == 1


@pytest.mark.parametrize("kind", ("aroma", "rgb"))
async def test_native_settings_drain_cancelled_write_and_publish_only_current_delivery(
    runtime, kind
):
    coordinator, ctrl, double = runtime
    ctrl._receive.aroma_capable = ctrl._receive.light_capable = True
    key = AROMA_START_2 if kind == "aroma" else UNDER_BED_LIGHTS_RGB
    expected = 12 if kind == "aroma" else (18, 52, 86)
    entered, finish = asyncio.Event(), asyncio.Event()

    async def write(*args, **kwargs):
        entered.set()
        await finish.wait()

    double.client.write_gatt_char.side_effect = write
    with virtual_clock():
        if kind == "aroma":
            spec = next(
                s for s in ctrl.controller_number_specs if s.key == "innova_control_aroma_start_2"
            )

            async def operation(c):
                await spec.set_fn(c, 12)
        else:

            async def operation(c):
                await c.set_light_color((18, 52, 86))

        task = asyncio.create_task(
            coordinator.async_execute_controller_command(operation, resource="configuration")
        )
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert coordinator.controller_state.get(key) is None
        finish.set()
        with suppress(asyncio.CancelledError):
            await task
    assert coordinator.controller_state[key] == expected


@pytest.mark.parametrize("operation", ("rgb", "join_group"))
async def test_offline_preflight_does_not_connect_or_use_retained_capability_flags(
    hass, runtime, monkeypatch, operation
):
    coordinator, ctrl, double = runtime
    ctrl._session = None
    ctrl._receive.light_capable = True
    assert not ctrl.has_live_session
    connect = AsyncMock(return_value=False)
    monkeypatch.setattr(coordinator, "async_ensure_connected", connect)
    execute = AsyncMock()
    from custom_components.adjustable_bed.beds.richmat_classic import innova_control_services

    monkeypatch.setattr(innova_control_services, "_execute_preflighted", execute)
    group_check = MagicMock(side_effect=AssertionError("Offline preflight queried GATT"))
    monkeypatch.setattr(ctrl, "validate_group_request", group_check)
    original = ctrl.validate_request
    validated = []

    def validate(request, *, live=True):
        validated.append(live)
        original(request, live=live)

    monkeypatch.setattr(ctrl, "validate_request", validate)
    arguments = {"rgb_color": [18, 52, 86]} if operation == "rgb" else {"group": "1234"}
    await hass.services.async_call(
        const.DOMAIN,
        "innova_control",
        {"device_id": ["bed"], "operation": operation, **arguments},
        blocking=True,
    )
    assert validated == ([False] if operation == "rgb" else [])
    execute.assert_awaited_once()
    connect.assert_not_awaited()
    group_check.assert_not_called()
    assert packets(double) == []


@pytest.mark.parametrize("runtime", ["YGRM"], indirect=True)
async def test_old_light_report_is_not_replayed_after_sent_off(runtime):
    coordinator, ctrl, double = runtime
    ctrl._notification(ctrl._session, None, bytearray.fromhex("6e0e00037f"))
    assert coordinator.controller_state[UNDER_BED_LIGHTS_ON] is True
    assert ctrl.supports_lights
    with virtual_clock():
        await coordinator.async_execute_controller_command(lambda c: c.lights_off())
    assert coordinator.controller_state[UNDER_BED_LIGHTS_ON] is False
    first = packets(double)
    assert first
    ctrl._select("hold", "hold")
    assert coordinator.controller_state[UNDER_BED_LIGHTS_ON] is False
    with virtual_clock():
        await coordinator.async_execute_controller_command(lambda c: c.lights_off())
    assert packets(double) == first
    ctrl._notification(ctrl._session, None, bytearray.fromhex("6e0e00037f"))
    assert coordinator.controller_state[UNDER_BED_LIGHTS_ON] is True
