"""Atlas Lift's exact GATT routes and normal Cama Lift workflows."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.config_entries import SOURCE_BLUETOOTH
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from probatio import Invalid
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.cancellation import cancellable
from custom_components.adjustable_bed.beds.richmat import atlas_lift
from custom_components.adjustable_bed.beds.richmat.atlas_lift import AtlasLiftController
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.detection import detect_bed_type, detect_bed_type_detailed
from custom_components.adjustable_bed.light import _light_entities_for
from custom_components.adjustable_bed.number import _position_number_specs
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.services import async_register_services
from tests.error_helpers import raises_key
from tests.form_helpers import options_of, select_options, suggested
from tests.hold_lease_wire import intervals, leased_hold, virtual_clock
from tests.test_bluetooth_matchers import _info
from tests.test_config_flow import _advance_only_progress, _patch_gate
from tests.test_richmat_family_flow import setup_flow
from tests.test_shared_action_hardening import beds

FROZEN = json.loads((Path(__file__).parent / "fixtures" / "atlas_lift_vectors.json").read_text())
STARTUP = ("Exit-limit initialization", "Clock capability query", "Light capability query")
ADDRESS = "AA:BB:CC:DD:EE:15"


def service(route, *properties):
    service_uuid, tx_uuid, nominal_rx = FROZEN["routes"][route]
    tx = SimpleNamespace(uuid=tx_uuid, properties=properties, handle=15, descriptors=[])
    rx = SimpleNamespace(uuid="first-notify", properties=["notify"], handle=16, descriptors=[])
    nominal = SimpleNamespace(uuid=nominal_rx, properties=["notify"], handle=17, descriptors=[])
    return SimpleNamespace(uuid=service_uuid, characteristics=[tx, rx, nominal])


def client_on(*services):
    return MagicMock(
        is_connected=True,
        services=services,
        write_gatt_char=AsyncMock(),
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
    )


def session_for(controller, client):
    return SimpleNamespace(
        client=client, is_current=lambda: True, async_start_notify=controller.start_notify
    )


def frames(client):
    return [call.args[1] for call in client.write_gatt_char.await_args_list]


def frozen(framing, *actions):
    return [bytes.fromhex(FROZEN["commands"][action][framing]) for action in actions]


def packet_info(name, local_name, services=(), manufacturer=None):
    info = _info(name, services, manufacturer_data=manufacturer)
    info.address = ADDRESS
    info.source = "local"
    info.rssi = -53
    info.raw = None
    info.advertisement = SimpleNamespace(local_name=local_name, platform_data=(object(),))
    return info


@pytest.mark.parametrize("route", FROZEN["routes"])
@pytest.mark.parametrize("no_response", (False, True))
async def test_startup_uses_the_exact_same_service_role_and_encoding(route, no_response):
    gatt = service(route, *("write", "write-without-response") if no_response else ("write",))
    client = client_on(gatt)
    controller = AtlasLiftController(MagicMock(client=client, cancel_command=asyncio.Event()))
    await controller.async_on_connect(session_for(controller, client))
    framing = "nordic" if route == "n1" else "framed"
    assert frames(client) == frozen(framing, *STARTUP)
    assert all(
        call.args[0] is gatt.characteristics[0] and call.kwargs["response"] is not no_response
        for call in client.write_gatt_char.await_args_list
    )
    client.start_notify.assert_awaited_once()
    assert client.start_notify.await_args.args[0] is gatt.characteristics[1]


@pytest.mark.parametrize("routes", (("n1", "w1"), ("w1", "n1"), ("w1", "w2")))
async def test_mixed_supported_services_fail_before_notifying_or_writing(routes):
    # The last service could affect the stock encoder despite having no TX.
    client = client_on(service(routes[0], "write"), service(routes[1], "read"))
    controller = AtlasLiftController(MagicMock(client=client))
    with raises_key("atlas_lift_gatt"):
        await controller.async_on_connect(session_for(controller, client))
    client.write_gatt_char.assert_not_awaited()
    client.start_notify.assert_not_awaited()


@pytest.mark.parametrize("bed_type", [const.BED_TYPE_ATLAS_LIFT, const.BED_TYPE_COMFORT_BED])
async def test_runtime_rejects_mixed_roles_even_with_one_cached_service(hass, bed_type):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={CONF_ADDRESS: ADDRESS, CONF_NAME: bed_type, const.CONF_BED_TYPE: bed_type},
    )
    entry.add_to_hass(hass)
    cached = client_on(service("n1", "write"))
    live = client_on(service("n1", "write"), service("w1", "write"))
    def disconnect(client):
        client.is_connected = False

    for client in (live, cached):
        client.disconnect = AsyncMock(side_effect=lambda client=client: disconnect(client))

    async def connect(*args, use_services_cache, **kwargs):
        return cached if use_services_cache else live

    adapter = MagicMock()
    adapter.device.address = ADDRESS
    adapter.device.name = "QRRM"
    adapter.source = "local"
    adapter.rssi = -53
    adapter.connectable = True
    adapter.available_sources = ["local"]
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._max_retries = 1
    with (
        patch(
            "custom_components.adjustable_bed.coordinator_connection.select_adapter",
            new=AsyncMock(return_value=adapter),
        ),
        patch(
            "custom_components.adjustable_bed.coordinator_connection.establish_connection",
            new=AsyncMock(side_effect=connect),
        ) as establish,
    ):
        assert not await coordinator.async_connect()

    assert establish.await_args.kwargs["use_services_cache"] is False
    cached.write_gatt_char.assert_not_awaited()
    live.write_gatt_char.assert_not_awaited()
    live.start_notify.assert_not_awaited()


async def test_exact_tx_needs_the_write_property():
    gatt = service("w1", "write-without-response")
    gatt.characteristics.append(SimpleNamespace(uuid="unknown-tx", properties=["write"]))
    client = client_on(gatt)
    controller = AtlasLiftController(MagicMock(client=client))
    with raises_key("atlas_lift_gatt"):
        await controller.async_on_connect(session_for(controller, client))
    client.write_gatt_char.assert_not_awaited()


async def test_notifications_only_forward_current_raw_diagnostics():
    client = client_on(service("w1", "write"))
    coordinator = MagicMock(client=client)
    controller = AtlasLiftController(coordinator)
    raw = MagicMock()
    controller.set_raw_notify_callback(raw)
    await controller.async_on_connect(session_for(controller, client))
    sender, receive = client.start_notify.await_args.args
    data = bytearray.fromhex("6e 0e 00 03 7f")
    receive(sender, data)
    raw.assert_called_once_with(sender.uuid, bytes(data))
    coordinator.handle_controller_state_updates.assert_not_called()

    await controller.stop_notify()
    client.stop_notify.assert_awaited_once_with(sender)
    controller.on_disconnect()
    receive(sender, data)
    raw.assert_called_once()


async def test_release_before_the_first_tick_never_dispatches_motion_or_cleanup():
    client = client_on(service("w1", "write"))
    cancel = asyncio.Event()
    controller = AtlasLiftController(MagicMock(client=client, cancel_command=cancel))
    await controller.async_on_connect(session_for(controller, client))
    client.write_gatt_char.reset_mock()
    with virtual_clock():
        holding = asyncio.create_task(controller.move_back_up())
        await asyncio.sleep(0.05)
        cancel.set()
        with pytest.raises(asyncio.CancelledError):
            await holding
    client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize(
    ("scenario", "framing"), (("atlas_lift", "nordic"), ("atlas_lift:w1", "framed"))
)
async def test_hold_renews_motion_at_the_proven_interval_until_expiry(scenario, framing):
    wire = await leased_hold(
        scenario, lambda ctrl: ctrl.move_back_up(), end_after_s=2, end="expire"
    )
    (motion, stop) = frozen(framing, "Head up", "Motor release STOP")
    assert len(wire.held) > wire.pulse_count
    assert wire.held[0].at_ms == 100
    assert intervals(wire.held) == {100}
    assert {event.data for event in wire.held} == {motion}
    assert [event.data for event in wire.after] == [stop]


@pytest.mark.parametrize(
    ("name", "local_name", "candidate"),
    (("Receiver", "xQRRM123", True), ("QRRM123", "qrrm123", False), ("QRRM123", None, False)),
)
def test_discovery_uses_the_case_sensitive_packet_name(name, local_name, candidate):
    info = packet_info(name, local_name, (FROZEN["routes"]["n1"][0],))
    result = detect_bed_type_detailed(info)
    assert result.bed_type != const.BED_TYPE_ATLAS_LIFT
    assert (const.BED_TYPE_ATLAS_LIFT in (result.ambiguous_types or ())) is candidate


async def discover_cama_lift(hass):
    info = packet_info("Receiver", "xQRRM123")
    manager = hass.config_entries.flow
    chooser = await manager.async_init(
        const.DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info
    )
    assert detect_bed_type(info) == const.BED_TYPE_MYSIDE
    assert detect_bed_type_detailed(info).confidence == 0.3
    assert chooser["step_id"] == "bluetooth_disambiguate"
    assert set(select_options(chooser, "bed_type_choice")) == {
        const.BED_TYPE_ATLAS_LIFT,
        const.BED_TYPE_COMFORT_BED,
        const.BED_TYPE_LIKIMIO,
        const.BED_TYPE_MYSIDE,
        "muuegm",
        "show_all",
    }
    confirm = await manager.async_configure(
        chooser["flow_id"], {"bed_type_choice": const.BED_TYPE_ATLAS_LIFT}
    )
    assert confirm["step_id"] == "bluetooth_confirm"
    settings = await manager.async_configure(
        confirm["flow_id"], {const.CONF_BED_TYPE: const.BED_TYPE_ATLAS_LIFT}
    )
    assert settings["step_id"] == "finish_settings"
    return settings


@pytest.mark.parametrize("routes", (("n1",), ("n1", "w1"), (), None))
async def test_discovered_atlas_checks_the_live_gatt_table_before_finish(
    hass, enable_custom_integrations, routes
):
    settings = await discover_cama_lift(hass)
    manager = hass.config_entries.flow
    # A different writable characteristic is insufficient on an unsupported service.
    roles = [service(route, "write") for route in (routes or ())] or [
        SimpleNamespace(
            uuid="unrelated-service", characteristics=service("n1", "write").characteristics
        )
    ]
    client = client_on(*roles)

    async def disconnect():
        client.is_connected = False

    client.disconnect = AsyncMock(side_effect=disconnect)
    connect = AsyncMock(return_value=client)
    if routes is None:
        connect.side_effect = BleakError("Receiver unavailable")
    with (
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=True),
        _patch_gate("hci0", -53),
        patch("bleak_retry_connector.establish_connection", connect),
    ):
        progress = await manager.async_configure(settings["flow_id"], {})
        result = await _advance_only_progress(hass, progress)
    assert result["step_id"] == "verify_connection"
    assert connect.await_args.kwargs["use_services_cache"] is False
    if routes is None:
        client.disconnect.assert_not_awaited()
        assert "Couldn't connect" in result["description_placeholders"]["capabilities"]
        created = await manager.async_configure(result["flow_id"], {})
        assert created["type"] is FlowResultType.CREATE_ENTRY
        return
    client.disconnect.assert_awaited_once()
    client.write_gatt_char.assert_not_awaited()
    client.start_notify.assert_not_awaited()
    if len(routes) == 1:
        assert (
            "The app's connection type is available"
            in result["description_placeholders"]["capabilities"]
        )
        created = await manager.async_configure(result["flow_id"], {})
        assert created["type"] is FlowResultType.CREATE_ENTRY
        assert created["data"][const.CONF_BED_TYPE] == const.BED_TYPE_ATLAS_LIFT
    else:
        assert (
            "Atlas Lift needs exactly one supported Bluetooth service"
            in (result["description_placeholders"]["capabilities"])
        )
        (selector,) = result["data_schema"].schema.values()
        assert options_of(selector) == ["retry", "change_app"]
        with pytest.raises(Invalid, match="value must be one of"):
            result["data_schema"]({"action": "finish"})
        choose = await manager.async_configure(result["flow_id"], {"action": "change_app"})
        assert choose["step_id"] == "select_app"
        if len(routes) > 1:
            # A fresh selection must open its own probe, not reuse this rejection.
            settings = await manager.async_configure(
                choose["flow_id"], {const.CONF_BED_TYPE: const.BED_TYPE_ATLAS_LIFT}
            )
            assert settings["step_id"] == "finish_settings"
            client.services = [service("n1", "write")]
            client.is_connected = True
            with (
                patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=True),
                _patch_gate("hci0", -53),
                patch("bleak_retry_connector.establish_connection", connect),
            ):
                progress = await manager.async_configure(settings["flow_id"], {})
                result = await _advance_only_progress(hass, progress)
            assert connect.await_count == 2
            created = await manager.async_configure(result["flow_id"], {})
            assert created["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize(
    ("manufacturer", "expected"),
    [
        ({}, const.BED_TYPE_RICHMAT),
        ({const.BEDTECH_MANUFACTURER_ID: bytes.fromhex("54307651")}, const.BED_TYPE_BEDTECH),
    ],
)
async def test_picked_qrrm_preserves_the_confident_receiver(hass, manufacturer, expected):
    info = packet_info("QRRM157052", "QRRM157052", (const.BEDTECH_SERVICE_UUID,), manufacturer)
    flow = setup_flow(hass)
    flow._all_ble_devices = {info.address: info}
    picked = await flow.async_step_manual({CONF_ADDRESS: info.address})
    assert picked["step_id"] == "select_app"
    (picker,) = picked["data_schema"].schema.values()
    assert picker(suggested(picked, const.CONF_BED_TYPE)) == expected
    assert const.BED_TYPE_ATLAS_LIFT in picker.rows().values()
    uncertain = await flow.async_step_select_app({const.CONF_BED_TYPE: "not_listed"})
    assert uncertain["step_id"] == "select_family"
    fallback = await flow.async_step_select_family({const.CONF_BED_TYPE: "not_sure"})
    assert "not_sure_detected" in fallback["menu_options"]
    assert fallback["description_placeholders"]["detected"] == suggested(
        picked, const.CONF_BED_TYPE
    )


async def test_setup_owns_the_cama_lift_layout(hass):
    flow = setup_flow(hass)
    flow._manual_data.update({const.CONF_MOTOR_COUNT: 4, const.CONF_HAS_MASSAGE: False})
    with patch.object(flow, "_verification_possible", return_value=False):
        result = await flow.async_step_richmat_family({"choice": "atlas_lift"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[const.CONF_BED_TYPE] == const.BED_TYPE_ATLAS_LIFT
    assert resolve_profile_id(data) == const.BED_TYPE_ATLAS_LIFT
    assert data[const.CONF_MOTOR_COUNT] == 2
    assert data[const.CONF_HAS_MASSAGE] is True


@pytest.fixture
async def runtime(hass, request, mock_coordinator_connected, mock_bleak_client, monkeypatch):
    route = getattr(request, "param", "w1")
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Cama Lift",
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "Cama Lift",
            const.CONF_BED_TYPE: const.BED_TYPE_ATLAS_LIFT,
            # A previous route's settings cannot change the Atlas layout.
            const.CONF_PRODUCT_TYPE: "AFEG350",
            const.CONF_MOTOR_COUNT: 4,
            const.CONF_MOTOR_PULSE_COUNT: 2,
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = coordinator
    mock_bleak_client.services = [service(route, "write")]
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()

    async def fast_wait(operation, cancel):
        operation.close()
        await asyncio.sleep(0)
        if cancel.is_set():
            raise asyncio.CancelledError

    monkeypatch.setattr(atlas_lift, "cancellable", fast_wait)
    await coordinator.async_prime_offline_controller()
    await async_register_services(hass)
    try:
        with patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coordinator, "both")], []),
        ):
            yield coordinator, mock_bleak_client, "nordic" if route == "n1" else "framed"
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("runtime", ("n1", "w1"), indirect=True)
async def test_native_controls_send_only_the_cama_lift_frames(hass, runtime):
    coordinator, client, framing = runtime
    offline = coordinator.capability_controller
    assert isinstance(offline, AtlasLiftController)
    assert await coordinator.async_connect()
    controller = coordinator.controller
    assert isinstance(controller, AtlasLiftController)
    assert [spec.key for spec in controller.motor_control_specs] == ["back", "legs"]
    assert _position_number_specs(coordinator) == ()
    assert not controller.supports_single_address_pairing
    assert _light_entities_for(hass, coordinator) == []
    buttons = _button_entities_for(hass, coordinator)
    assert not any(
        entity.unique_id.endswith(
            ("preset_memory_2", "preset_lounge", "massage_all_toggle", "massage_head_down")
        )
        for entity in buttons
    )
    client.write_gatt_char.reset_mock()
    actions = {
        "preset_flat": "Flat / motor reset",
        "preset_anti_snore": "Anti-snore recall",
        "preset_zero_g": "Zero gravity recall",
        "preset_memory_1": "Memory 1 recall",
        "atlas_lift_save_zero_g": "Zero gravity save",
        "atlas_lift_save_anti_snore": "Anti-snore save",
        "massage_head_up": "Head massage intensity increase",
    }
    for suffix in actions:
        button = next(entity for entity in buttons if entity.unique_id.endswith(suffix))
        await button.async_press()
    assert frames(client) == frozen(framing, *actions.values())
    client.write_gatt_char.reset_mock()
    await hass.services.async_call(
        const.DOMAIN, "save_preset", {"device_id": ["bed"], "preset": 1}, blocking=True
    )
    assert frames(client) == frozen(framing, "Memory 1 save")

    client.write_gatt_char.reset_mock()
    for spec in controller.motor_control_specs:
        cover = AdjustableBedCover(coordinator, _build_cover_description(spec))
        cover.async_write_ha_state = MagicMock()
        await cover.async_open_cover()
        await cover.async_close_cover()
    directions = ("Head up", "Head down", "Foot up", "Foot down")
    expected = [
        action
        for direction in directions
        for action in (direction, direction, "Motor release STOP")
    ]
    assert frames(client) == frozen(framing, *expected)


async def test_stop_drains_an_inflight_movement_and_sends_one_release(runtime):
    coordinator, client, _ = runtime
    assert await coordinator.async_connect()
    client.write_gatt_char.reset_mock()
    began, finish = asyncio.Event(), asyncio.Event()
    (motor,) = frozen("framed", "Head up")

    async def write(_characteristic, frame, **kwargs):
        if frame == motor:
            began.set()
            await finish.wait()

    client.write_gatt_char.side_effect = write
    movement = asyncio.create_task(
        coordinator.async_execute_controller_command(lambda ctrl: ctrl.move_back_up())
    )
    await asyncio.wait_for(began.wait(), 2)
    stop = asyncio.create_task(coordinator.async_stop_command())
    await asyncio.sleep(0)
    assert not stop.done()
    assert frames(client) == [motor]
    finish.set()
    await asyncio.gather(movement, stop)
    assert frames(client) == frozen("framed", "Head up", "Motor release STOP")
    await coordinator.async_stop_command()
    assert frames(client) == frozen("framed", "Head up", "Motor release STOP", "Motor release STOP")


@pytest.mark.parametrize("pre_dispatch_expiry", (False, True))
async def test_public_minimum_timed_move_obeys_the_dispatch_window(
    hass, runtime, monkeypatch, pre_dispatch_expiry
):
    coordinator, client, _ = runtime
    assert await coordinator.async_connect()
    controller = coordinator.controller
    assert isinstance(controller, AtlasLiftController)
    monkeypatch.setattr(atlas_lift, "cancellable", cancellable)
    recorded = []

    async def timed_move():
        await hass.services.async_call(
            const.DOMAIN,
            "timed_move",
            {"device_id": "bed", "motor": "legs", "direction": "down", "duration_ms": 100},
            blocking=True,
        )

    with virtual_clock() as clock:

        async def write(_characteristic, frame, **kwargs):
            recorded.append((round(clock.now * 1000), frame))

        client.write_gatt_char.side_effect = write
        if pre_dispatch_expiry:
            async with controller.ble_lock:
                running = asyncio.create_task(timed_move())
                await asyncio.sleep(0.125)
                assert not recorded
            await running
        else:
            await timed_move()
    expected = (
        []
        if pre_dispatch_expiry
        else list(zip((0, 100), frozen("framed", "Foot down", "Motor release STOP"), strict=True))
    )
    assert recorded == expected


async def test_renewable_timed_move_expiring_before_first_tick_has_no_cleanup(
    hass, runtime, monkeypatch
):
    coordinator, client, _ = runtime
    assert await coordinator.async_connect()
    client.write_gatt_char.reset_mock()
    monkeypatch.setattr(atlas_lift, "cancellable", cancellable)
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN,
            "timed_move",
            {
                "device_id": "bed",
                "motor": "back",
                "direction": "up",
                "duration_ms": 100,
                "hold_owner": "atlas-test",
                "hold_generation": 1,
            },
            blocking=True,
        )
    client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize(
    ("stop_kind", "stopped_sides"), (("all", ("left", "right")), ("motor", ("right",)))
)
async def test_sequential_pair_stop_reconnects_only_the_selected_released_receivers(
    hass, stop_kind, stopped_sides
):
    async with beds(hass, topology="sequential", connected=False) as made:
        pair = made.pair
        assert pair is not None
        sessions = []

        def connector(side, bed, route):
            async def connect(**kwargs):
                if bed.is_connected:
                    return True
                assert not any(peer.is_connected for peer in made.items if peer is not bed)
                assert await bed.fake_connect(**kwargs)
                client = bed.client
                client.services = [service(route, "write")]
                client.write_gatt_char = AsyncMock()
                client.start_notify = AsyncMock()
                client.stop_notify = AsyncMock()
                controller = AtlasLiftController(bed)
                bed._controller = controller
                await controller.async_on_connect(session_for(controller, client))
                sessions.append((side, client))
                return True

            return connect

        for side, bed, route in zip(("left", "right"), made.items, ("n1", "w1"), strict=True):
            bed._offline_controller = AtlasLiftController(bed)
            bed.async_connect.side_effect = bed.async_ensure_connected.side_effect = connector(
                side, bed, route
            )

        def resolve(_hass, _devices, side, **kwargs):
            return [(pair, side or "both")], []

        with patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets", side_effect=resolve
        ):
            await hass.services.async_call(
                const.DOMAIN, "goto_preset", {"device_id": "pair", "preset": 1}, blocking=True
            )
            assert not any(bed.is_connected for bed in made.items)
            if stop_kind == "all":
                await hass.services.async_call(
                    const.DOMAIN, "stop_all", {"device_id": "pair"}, blocking=True
                )
            else:
                await pair.async_stop_motor(
                    lambda ctrl: ctrl.move_back_stop(), "motor:back", side="right"
                )
        assert not any(bed.is_connected for bed in made.items)
        assert [side for side, _ in sessions] == ["left", "right", *stopped_sides]
        assert len({id(client) for _, client in sessions}) == len(sessions)
        for index, (side, client) in enumerate(sessions):
            framing = "nordic" if side == "left" else "framed"
            action = "Memory 1 recall" if index < 2 else "Motor release STOP"
            assert frames(client) == frozen(framing, *STARTUP, action)


async def test_replaced_link_cannot_receive_a_queued_write():
    old = client_on(service("w1", "write"))
    coordinator = MagicMock(client=old, cancel_command=asyncio.Event())
    controller = AtlasLiftController(coordinator)
    await controller.async_on_connect(session_for(controller, old))
    old.write_gatt_char.reset_mock()
    async with controller.ble_lock:
        recall = asyncio.create_task(controller.preset_anti_snore())
        await asyncio.sleep(0)
        controller.on_disconnect()
        new = client_on(service("n1", "write"))
        coordinator.client = new
    with pytest.raises(ConnectionError):
        await recall
    await controller.async_on_connect(session_for(controller, new))
    await controller.preset_anti_snore()
    assert frames(old) == []
    assert frames(new) == frozen("nordic", *STARTUP, "Anti-snore recall")
