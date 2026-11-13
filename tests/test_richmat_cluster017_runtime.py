"""Setup, saved entries, factory, real entities, registered services and admission."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const, services
from custom_components.adjustable_bed.beds.richmat_classic import resource_controller as bed
from custom_components.adjustable_bed.beds.richmat_classic.resource_services import (
    async_register_resource_bed_services,
)
from custom_components.adjustable_bed.button import ControllerActionButton, _button_entities_for
from custom_components.adjustable_bed.command_scheduler import CommandIntent, DeviceCommandScheduler
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.number import AdjustableBedControllerNumber
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.profiles.richmat_resource_apps import APPS
from custom_components.adjustable_bed.select import AdjustableBedControllerSelect
from tests.test_richmat_classic_transport import Services, route
from tests.test_richmat_cluster017 import clock as clock
from tests.test_richmat_family_flow import answer, fields, setup_flow


@pytest.mark.parametrize("app", APPS)
async def test_real_setup_saves_explicit_app_layout_owned_defaults_and_factory(hass, app):
    flow = setup_flow(hass, "6BRM-bed")
    form, _ = await answer(flow, app)
    assert form["step_id"] == "profile_questions"
    assert fields(form)[const.CONF_PRODUCT_TYPE].default is vol.UNDEFINED
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions({const.CONF_PRODUCT_TYPE: "O0RM"})
    saved = finish.call_args.args[0]
    assert saved[const.CONF_PROTOCOL_VARIANT] == app
    assert saved[const.CONF_PRODUCT_TYPE] == "O0RM"
    assert saved[const.CONF_HAS_MASSAGE] is False
    assert saved[const.CONF_DISABLE_ANGLE_SENSING] is True
    entry = MockConfigEntry(domain=const.DOMAIN, data=saved)
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    await coordinator.async_prime_offline_controller()
    assert isinstance(coordinator.capability_controller, bed.ResourceBedController)
    assert coordinator.capability_controller.app == app
    assert coordinator.capability_controller.layout == "O0RM"
    await coordinator.async_shutdown()


@pytest.fixture
async def runtime(hass, request, mock_coordinator_connected, mock_bleak_client, monkeypatch):
    app, layout, wire = getattr(request, "param", ("lady_americana", "O0RM", "FRAMED"))
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title=APPS[app].name,
        data={
            "address": "AA:BB:CC:DD:EE:71",
            "name": APPS[app].name,
            "bed_type": const.BED_TYPE_RICHMAT_CLASSIC_APPS,
            "protocol_variant": app,
            "product_type": layout,
            "ble_device_name": "6BRM-bed",
            "disable_angle_sensing": True,
            "disconnect_after_command": False,
            "motor_pulse_count": 1,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._max_retries = 1
    mock_bleak_client.services = Services([route(2 if wire == "RAW" else 0)])
    for service in mock_bleak_client.services:
        service.handle = 1
        for index, channel in enumerate(service.characteristics, 1):
            channel.descriptors = []
            channel.handle = index
            channel.service_uuid = service.uuid
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    now, original_sleep = [0.0], asyncio.sleep

    async def sleep(seconds):
        now[0] += seconds
        await original_sleep(0)

    async def wait(milliseconds, cancel):
        await sleep(milliseconds / 1000)
        return not cancel.is_set()

    monkeypatch.setattr(bed, "monotonic", lambda: now[0])
    monkeypatch.setattr(bed.asyncio, "sleep", sleep)
    monkeypatch.setattr(bed.ResourceBedController, "_wait", staticmethod(wait))
    await coordinator.async_prime_offline_controller()
    await services.async_register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, "both")], []),
    ):
        yield coordinator, mock_bleak_client
    await coordinator.async_shutdown()


def written(client):
    return [call.args[1].hex() for call in client.write_gatt_char.await_args_list]


async def invoke(hass, operation, **fields):
    await hass.services.async_call(
        const.DOMAIN,
        "richmat_resource_bed",
        {"device_id": "bed", "operation": operation, **fields},
        blocking=True,
    )


@pytest.mark.parametrize(
    "runtime", [(app, "O0RM", wire) for app in APPS for wire in ("RAW", "FRAMED")], indirect=True
)
async def test_real_connect_startup_public_alarm_query_and_reconnect(hass, runtime):
    target, client = runtime
    assert await target.async_connect()
    live = target.controller
    assert isinstance(live, bed.ResourceBedController)
    assert written(client) == (["6e02010071"] if live._session.wire == "FRAMED" else [])
    client.write_gatt_char.reset_mock()
    await invoke(hass, "query")
    assert written(client) == ["6e08010178", "6e0a000179", "6e1a000088"]
    client.write_gatt_char.reset_mock()
    await invoke(hass, "alarm", actions=["zero_gravity", "massage_head", "massage_foot"])
    assert written(client) == ["6e05a00013", "6e060579f2"]
    old = live._session
    live._notification(old, old.notify, bytearray.fromhex("6e0e00037f"))
    number = AdjustableBedControllerNumber(target, live.controller_number_specs[0])
    await number.async_set_native_value(256)
    assert written(client)[-1] == "6e0b00017a"
    assert number.native_value == 256
    await target.async_disconnect("idle_timeout")
    assert await target.async_connect()
    current = target.controller
    assert current is not live
    assert not current._receive.light_capable
    live._notification(old, old.notify, bytearray.fromhex("6e0e00037f"))
    with pytest.raises(ServiceValidationError, match="LED"):
        await invoke(hass, "lamp_timeout", seconds=300)


@pytest.mark.parametrize("runtime", [("sta2", "D1RM", "RAW")], indirect=True)
async def test_real_massage_slider_keeps_direct_framing_and_literal_passthrough(runtime):
    target, client = runtime
    assert await target.async_connect()
    number = AdjustableBedControllerNumber(target, target.controller.controller_number_specs[0])
    client.write_gatt_char.reset_mock()
    for progress in range(6):
        await number.async_set_native_value(progress)
        assert number.native_value == progress
    assert written(client) == [
        "6e01005ecd", "6e01000170", "6e01005fce", "6e010063d2", "6e01000473", "6e010061d0"
    ]


@pytest.mark.parametrize("runtime", [("acaa", "GVRM", "RAW")], indirect=True)
async def test_real_button_select_and_current_hold_metadata_survive_recreation(hass, runtime):
    target, client = runtime
    assert await target.async_connect()
    ctrl = target.controller
    button = next(
        e
        for e in _button_entities_for(hass, target)
        if isinstance(e, ControllerActionButton) and e._spec.key == "richmat_classic_2"
    )
    button.hass = hass
    selector = AdjustableBedControllerSelect(target, ctrl.controller_select_specs[0])
    assert button.extra_state_attributes["held_control"] == "richmat_classic_2"
    await selector.async_select_option("foot")
    assert not button.available
    assert "held_control" not in button.extra_state_attributes
    assert "hold_lease_ms" not in button.extra_state_attributes
    client.write_gatt_char.reset_mock()
    await button.async_press()
    assert written(client) == []
    await target.async_write_app_state(ctrl, ctrl.persisted_app_state)
    await target.async_disconnect("idle_timeout")
    assert await target.async_connect()
    await selector.async_select_option("head")
    assert target.controller._selection.head is True
    assert ctrl._selection.head is False
    client.write_gatt_char.reset_mock()
    await button.async_press()
    assert written(client)[0] == "37" and written(client)[-1] == "6e"


@pytest.mark.parametrize("operation", ["query", "bed_command"])
async def test_registered_all_target_stop_epoch_captured_before_first_await(hass, operation):
    async_register_resource_bed_services(hass)
    started, finish = asyncio.Event(), asyncio.Event()
    events = []

    async def first(_request):
        events.append("A starts")
        started.set()
        await finish.wait()

    async def second(_request):
        events.append("B starts")

    def target(name, command):
        scheduler = DeviceCommandScheduler(name)
        ctrl = MagicMock(
            spec=bed.ResourceBedController,
            validate_request=lambda request: None,
            execute_request=command,
            requires_disconnected_transport=False,
        )
        coord = SimpleNamespace(
            name=name,
            controller_side=None,
            capability_controller=ctrl,
            entry=SimpleNamespace(data={}),
            _command_scheduler=scheduler,
            stop_epoch=scheduler.stop_epoch,
        )

        async def execute(fn, *, expected_stop_epoch=None, **_kwargs):
            async def admitted(_context):
                await fn(ctrl)

            await scheduler.execute(
                CommandIntent(admitted), expected_stop_epoch=expected_stop_epoch
            )

        coord.async_execute_controller_command = execute
        return coord

    a, b = target("A", first), target("B", second)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(a, "both"), (b, "both")], []),
    ):
        task = asyncio.create_task(invoke(hass, operation, command="head_up"))
        await started.wait()
        epoch = b._command_scheduler.request_stop()
        b._command_scheduler.finish_stop(epoch)
        finish.set()
        await task
    assert events == ["A starts"]


@pytest.mark.parametrize("renewable", [False, True])
async def test_sequential_both_hold_rejected_before_claims_or_motion(hass, renewable):
    pair = MagicMock(spec=PairedBedCoordinator)
    pair.connection_mode = "sequential"
    await services.async_register_services(hass)
    data = {"device_id": "bed", "control": "richmat_classic_1", "duration": 1}
    if renewable:
        data.update(hold_owner="card", hold_generation=1)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(pair, "both")], []),
        ),
        pytest.raises(ServiceValidationError, match="one side"),
    ):
        await hass.services.async_call(const.DOMAIN, "hold_control", data, blocking=True)
    pair._targets_for.assert_not_called()
    pair.async_execute_controller_command.assert_not_awaited()


@pytest.mark.parametrize("app", APPS)
@pytest.mark.parametrize("raw", [False, True])
async def test_source_holds_use_real_scheduler_leases_and_cleanup(app, raw):
    from tests.hold_lease_wire import intervals, leased_hold

    scenario = f"richmat_classic_apps:{app}:6BRM" + (":nordic" if raw else "")

    async def move(controller):
        await controller.hold_control("richmat_classic_1", 30000)

    wire = await leased_hold(scenario, move, end_after_s=0.8, end="expire")
    assert wire.held
    assert {write.data for write in wire.held} == {bytes.fromhex("34" if raw else "6e01002493")}
    refresh = 170 if raw else 150
    assert all(refresh <= gap <= refresh + 10 for gap in intervals(wire.held))
    assert [write.data for write in wire.after] == [bytes.fromhex("6e" if raw else "6e01006edd")]
    assert wire.after[0].at_ms == wire.ended_ms + 50


async def test_pair_configure_keeps_app_layout_and_defaults_owned_by_each_receiver(
    hass, enable_custom_integrations
):
    from tests.test_paired_receiver_questions import child, fields, pair_entry, receiver_form

    entry = pair_entry(
        hass,
        {
            "bed_type": const.BED_TYPE_RICHMAT_CLASSIC_APPS,
            "protocol_variant": "lady_americana",
            "product_type": "O0RM",
            "ble_device_name": "6BRM-left",
        },
        {
            "bed_type": const.BED_TYPE_RICHMAT_CLASSIC_APPS,
            "protocol_variant": "zerogravity",
            "product_type": "D1RM",
            "ble_device_name": "6BRM-right",
        },
    )
    form = await receiver_form(hass, entry, "left")
    assert fields(form)[const.CONF_PRODUCT_TYPE].default() == "O0RM"
    result = await hass.config_entries.options.async_configure(
        form["flow_id"],
        {
            **form["data_schema"]({}),
            const.CONF_PRODUCT_TYPE: "U3RM",
        },
    )
    assert result["type"].value == "create_entry"
    assert child(entry, "left")[const.CONF_PRODUCT_TYPE] == "U3RM"
    assert child(entry, "left")[const.CONF_PROTOCOL_VARIANT] == "lady_americana"
    assert child(entry, "right")[const.CONF_PRODUCT_TYPE] == "D1RM"
    assert child(entry, "right")[const.CONF_PROTOCOL_VARIANT] == "zerogravity"
    assert child(entry, "right")[const.CONF_BLE_DEVICE_NAME] == "6BRM-right"


async def test_real_concurrent_pair_routes_each_app_session_and_single_side(hass, clock):
    from custom_components.adjustable_bed.beds.richmat_classic.transport import Transport

    children = {}
    clients = {}
    for side, app, wire, address in (
        ("left", "lady_americana", "RAW", "AA:BB:CC:DD:EE:71"),
        ("right", "zerogravity", "FRAMED", "AA:BB:CC:DD:EE:72"),
    ):
        entry = MockConfigEntry(
            domain=const.DOMAIN,
            data={
                "address": address,
                "name": side,
                "bed_type": const.BED_TYPE_RICHMAT_CLASSIC_APPS,
                "protocol_variant": app,
                "product_type": "6BRM",
                "disconnect_after_command": False,
            },
        )
        entry.add_to_hass(hass)
        child = AdjustableBedCoordinator(hass, entry)
        await child.async_prime_offline_controller()
        child._client = MagicMock(
            is_connected=True,
            write_gatt_char=AsyncMock(),
            disconnect=AsyncMock(),
            stop_notify=AsyncMock(),
        )
        child._controller = child._offline_controller
        child._controller._session = Transport(
            child._client,
            SimpleNamespace(uuid="write", properties=["write"], handle=71),
            SimpleNamespace(uuid="notify", properties=["notify"], handle=72),
            wire,
        )
        child.async_ensure_connected = AsyncMock(return_value=True)
        child._async_refresh_controller_auth = AsyncMock()
        children[side], clients[side] = child, child._client
    entry = MockConfigEntry(domain=const.DOMAIN, data={"pair_id": "cluster017", "name": "Pair"})
    pair = PairedBedCoordinator(hass, entry, children, connection_mode="concurrent")
    await services.async_register_services(hass)
    try:
        with patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(pair, "both")], []),
        ):
            await hass.services.async_call(
                const.DOMAIN,
                "hold_control",
                {
                    "device_id": "bed",
                    "control": "richmat_classic_1",
                    "duration": 0.2,
                },
                blocking=True,
            )
        assert written(clients["left"])[0] == "34"
        assert written(clients["left"])[-1] == "6e"
        assert written(clients["right"])[0] == "6e01002493"
        assert written(clients["right"])[-1] == "6e01006edd"
        for client in clients.values():
            client.write_gatt_char.reset_mock()
        with patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(pair, "right")], []),
        ):
            await invoke(hass, "bed_command", command="memory_three")
        assert written(clients["left"]) == []
        assert written(clients["right"]) == ["6e0100309f", "6e01006edd"]
    finally:
        await pair.async_shutdown()
