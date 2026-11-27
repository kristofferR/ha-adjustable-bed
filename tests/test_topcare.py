"""TOP CARE 1.0.0's bounded motor surface, without sensor or parser inference."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.richmat.topcare import TopcareController
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.detection import (
    BED_TYPE_DISPLAY_NAMES,
    detect_bed_type_detailed,
)
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.profiles.richmat import TOPCARE
from tests.error_helpers import raises_key
from tests.hold_lease_wire import intervals, leased_hold, virtual_clock
from tests.test_atlas_lift import client_on, frames, packet_info, session_for
from tests.test_richmat_family_flow import setup_flow

FROZEN = json.loads((Path(__file__).parent / "fixtures/topcare_vectors.json").read_text())


def service(key="n1", properties=("write",)):
    route = FROZEN["routes"][("n1", "w1", "w2", "w3", "w4", "w5").index(key)]
    return SimpleNamespace(
        uuid=route["service"].lower(),
        characteristics=[
            SimpleNamespace(
                uuid=route["write"].lower(), properties=list(properties), handle=1, descriptors=[]
            ),
            SimpleNamespace(
                uuid="00009999-0000-1000-8000-00805f9b34fb",
                properties=["notify"],
                handle=2,
                descriptors=[],
            ),
        ],
    )


def expected(action, key="n1"):
    return bytes.fromhex(
        next(
            v["expected_bytes"]
            for v in FROZEN["vectors"]
            if v["action"] == action and v["inputs"]["nordic"] == (key == "n1")
        )
    )


def test_every_frozen_literal_reproduces_through_existing_codec_first():
    assert len(FROZEN["vectors"]) == 24
    for v in FROZEN["vectors"]:
        assert codec.function(
            v["inputs"]["enum_code"],
            action="deviceFunctionItemExitLimit" if v["action"] == "exit_limit" else "",
            single=not v["inputs"]["nordic"],
        ) == bytes.fromhex(v["expected_bytes"])
    for key, route in zip(TOPCARE.transports, FROZEN["routes"], strict=True):
        actual = codec.TRANSPORTS[key]
        assert (actual.service_uuid, actual.write_uuid, actual.notify_uuid) == tuple(
            route[k].lower() for k in ("service", "write", "notify_declared")
        )


@pytest.mark.parametrize("key", TOPCARE.transports)
@pytest.mark.parametrize("no_response", (False, True))
async def test_session_uses_actual_roles_mode_and_app_encoding(key, no_response):
    gatt = service(key, ("write", "write-without-response") if no_response else ("write",))
    client = client_on(gatt)
    ctrl = TopcareController(MagicMock(client=client, cancel_command=asyncio.Event()))
    await ctrl.async_on_connect(session_for(ctrl, client))
    assert frames(client) == [expected("exit_limit", key)]
    assert client.write_gatt_char.await_args.args[0] is gatt.characteristics[0]
    assert client.write_gatt_char.await_args.kwargs["response"] is not no_response
    assert client.start_notify.await_args.args[0] is gatt.characteristics[1]
    client.write_gatt_char.reset_mock()
    with virtual_clock():
        for spec, actions in zip(
            ctrl.motor_control_specs,
            (
                ("head_up", "head_down"),
                ("foot_up", "foot_down"),
                ("head_and_foot_up", "head_and_foot_down"),
                ("lumber_and_pillow_up", "lumber_and_pillow_down"),
                ("tile_up", "tile_down"),
            ),
            strict=True,
        ):
            await ctrl.hold_control(spec.hold.up_control, 350)
            await ctrl.hold_control(spec.hold.down_control, 350)
            assert frames(client) == [
                frame
                for action in actions
                for frame in [expected(action, key)] * 3 + [expected("stop", key)]
            ]
            client.write_gatt_char.reset_mock()


@pytest.mark.parametrize(
    "services", ([], [service("n1"), service("w1")], [service("w2", ("write-without-response",))])
)
async def test_ambiguous_or_nonwritable_route_rejected_before_writes(services):
    client = client_on(*services)
    ctrl = TopcareController(MagicMock(client=client))
    with raises_key("topcare_gatt"):
        await ctrl.async_on_connect(session_for(ctrl, client))
    client.write_gatt_char.assert_not_awaited()
    client.start_notify.assert_not_awaited()


@pytest.mark.parametrize("key", ("topcare", "topcare:w1"))
@pytest.mark.parametrize("end", ("expire", "stop"))
async def test_combined_native_hold_renews_and_releases(key, end):
    wire = await leased_hold(
        key, lambda ctrl: ctrl.motor_control_specs[3].open_fn(ctrl), end_after_s=2.5, end=end
    )
    route = "n1" if key == "topcare" else "w1"
    assert len(wire.held) > wire.pulse_count
    assert wire.held[0].at_ms == 100
    assert intervals(wire.held) == {100}
    assert {v.data for v in wire.held} == {expected("lumber_and_pillow_up", route)}
    assert [v.data for v in wire.after] == [expected("stop", route)] * (2 if end == "stop" else 1)


async def test_searchable_setup_owns_capabilities(hass):
    assert "TOP CARE" in BED_TYPE_DISPLAY_NAMES["topcare"]
    flow = setup_flow(hass)
    flow._manual_data.update({const.CONF_MOTOR_COUNT: 4, const.CONF_HAS_MASSAGE: True})
    with patch.object(flow, "_verification_possible", return_value=False):
        result = await flow.async_step_richmat_family({"choice": "topcare"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert resolve_profile_id(data) == "topcare"
    assert data[const.CONF_MOTOR_COUNT] == 2
    assert data[const.CONF_HAS_MASSAGE] is False
    ctrl = TopcareController(MagicMock())
    assert [s.key for s in ctrl.motor_control_specs] == [
        "back",
        "legs",
        "head_feet",
        "lumbar_pillow",
        "tilt",
    ]
    assert (
        not ctrl.supports_preset_flat
        and not ctrl.supports_memory_presets
        and not ctrl.supports_massage
    )
    assert not ctrl.has_lumbar_support and not ctrl.has_pillow_support
    assert not ctrl.supports_single_address_pairing
    assert ctrl.position_number_specs == ()
    assert ctrl.execution.declared == {"hold"}
    assert all(
        s.hold and s.hold.press_is_native and s.hold.stop_scope == "side"
        for s in ctrl.motor_control_specs
    )


@pytest.mark.parametrize("local,candidate", [("xRMTC123", True), ("rmtc", False), (None, False)])
def test_case_sensitive_packet_name_only_adds_app_choice(local, candidate):
    info = packet_info("RMTC cached name", local, (FROZEN["routes"][0]["service"],))
    result = detect_bed_type_detailed(info)
    assert ("topcare" in (result.ambiguous_types or ())) is candidate


@pytest.fixture
async def runtime(hass, mock_coordinator_connected, mock_bleak_client):
    from homeassistant.const import CONF_ADDRESS, CONF_NAME
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
    from custom_components.adjustable_bed.services import async_register_services

    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="TOP CARE",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:15",
            CONF_NAME: "TOP CARE",
            const.CONF_BED_TYPE: "topcare",
            const.CONF_MOTOR_COUNT: 4,
            const.CONF_HAS_MASSAGE: True,
            const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = coordinator
    mock_bleak_client.services = [service("n1")]
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    await coordinator.async_prime_offline_controller()
    await async_register_services(hass)
    try:
        with patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coordinator, "both")], []),
        ):
            yield coordinator, mock_bleak_client
    finally:
        await coordinator.async_shutdown()


async def test_actual_task_cancel_settles_inflight_and_stop_ownership(runtime):
    coordinator, client = runtime
    assert await coordinator.async_connect()
    client.write_gatt_char.reset_mock()
    began, finish = asyncio.Event(), asyncio.Event()

    async def write(_char, data, **kwargs):
        if data == expected("head_up"):
            began.set()
            await finish.wait()

    client.write_gatt_char.side_effect = write
    with virtual_clock():
        movement = asyncio.create_task(
            coordinator.async_execute_controller_command(lambda c: c.move_back_up())
        )
        await began.wait()
        stop = asyncio.create_task(coordinator.async_stop_command())
        await asyncio.sleep(0)
        assert not stop.done()
        assert frames(client) == [expected("head_up")]
        finish.set()
        await asyncio.gather(movement, stop)
        assert frames(client) == [expected("head_up"), expected("stop")]
        await coordinator.async_stop_command()
        assert frames(client) == [expected("head_up"), expected("stop"), expected("stop")]


async def test_native_entities_card_and_public_combined_timed_service(hass, runtime):
    from custom_components.adjustable_bed.button import _button_entities_for
    from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
    from custom_components.adjustable_bed.number import _position_number_specs

    coordinator, client = runtime
    assert await coordinator.async_connect()
    ctrl = coordinator.controller
    assert isinstance(ctrl, TopcareController)
    assert _position_number_specs(coordinator) == ()
    assert not any("preset" in b.unique_id for b in _button_entities_for(hass, coordinator))
    for spec in ctrl.motor_control_specs:
        cover = AdjustableBedCover(coordinator, _build_cover_description(spec))
        attrs = cover.capability_attributes | cover.extra_state_attributes
        assert attrs["card_section"] == "motors"
        assert attrs["card_motor"] == spec.key
        assert attrs["held_control_up"] == spec.hold.up_control
    client.write_gatt_char.reset_mock()
    with virtual_clock():
        await hass.services.async_call(
            const.DOMAIN,
            "timed_move",
            {"device_id": "bed", "motor": "lumbar_pillow", "direction": "up", "duration_ms": 350},
            blocking=True,
        )
    assert frames(client) == [expected("lumber_and_pillow_up")] * 3 + [expected("stop")]


async def test_raw_diagnostic_subscription_is_current_and_cleanup_is_exact():
    old = client_on(service())
    coordinator = MagicMock(client=old, cancel_command=asyncio.Event())
    ctrl = TopcareController(coordinator)
    ctrl.forward_raw_notification = MagicMock()
    await ctrl.async_on_connect(session_for(ctrl, old))
    notify = old.start_notify.await_args.args[1]
    rx = old.services[0].characteristics[1]
    notify(rx, bytearray(b"opaque"))
    ctrl.forward_raw_notification.assert_called_once_with(rx.uuid, b"opaque")
    await ctrl.stop_notify()
    old.stop_notify.assert_awaited_once_with(rx)
    notify(rx, bytearray(b"after cleanup"))
    ctrl.forward_raw_notification.assert_called_once()
    ctrl.on_disconnect()
    new = client_on(service("w1"))
    coordinator.client = new
    await ctrl.async_on_connect(session_for(ctrl, new))
    notify(rx, bytearray(b"old session"))
    ctrl.forward_raw_notification.assert_called_once()


async def test_old_movement_cannot_cross_connection_replacement_or_cleanup():
    old = client_on(service())
    coordinator = MagicMock(client=old, cancel_command=asyncio.Event())
    ctrl = TopcareController(coordinator)
    await ctrl.async_on_connect(session_for(ctrl, old))
    old.write_gatt_char.reset_mock()
    began, finish = asyncio.Event(), asyncio.Event()

    async def write(_char, data, **kwargs):
        began.set()
        await finish.wait()

    old.write_gatt_char.side_effect = write
    with virtual_clock():
        task = asyncio.create_task(ctrl.hold_control("tilt_up", 350))
        await began.wait()
        ctrl.on_disconnect()
        new = client_on(service("w1"))
        coordinator.client = new
        task.cancel()
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        await ctrl.async_on_connect(session_for(ctrl, new))
        new.write_gatt_char.reset_mock()
    assert frames(old) == [expected("tile_up")]
    new.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("invalid", (False, True))
async def test_setup_checks_fresh_gatt_and_rejects_mixed_services(
    hass, enable_custom_integrations, invalid
):
    from homeassistant.config_entries import SOURCE_BLUETOOTH

    from tests.test_atlas_lift import ADDRESS
    from tests.test_config_flow import _advance_only_progress, _patch_gate

    info = packet_info("Receiver", "xRMTC123")
    manager = hass.config_entries.flow
    chooser = await manager.async_init(
        const.DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info
    )
    assert chooser["step_id"] == "bluetooth_disambiguate"
    confirmed = await manager.async_configure(chooser["flow_id"], {"bed_type_choice": "topcare"})
    settings = await manager.async_configure(confirmed["flow_id"], {const.CONF_BED_TYPE: "topcare"})
    assert settings["step_id"] == "finish_settings"
    client = client_on(service())
    if invalid:
        client.services = (*client.services, service("w1"))

    async def disconnect():
        client.is_connected = False

    client.disconnect = AsyncMock(side_effect=disconnect)
    connect = AsyncMock(return_value=client)
    with (
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=True),
        _patch_gate("hci0", -53),
        patch("bleak_retry_connector.establish_connection", connect),
    ):
        progress = await manager.async_configure(settings["flow_id"], {})
        result = await _advance_only_progress(hass, progress)
    assert connect.await_args.kwargs["use_services_cache"] is False
    client.write_gatt_char.assert_not_awaited()
    client.start_notify.assert_not_awaited()
    client.disconnect.assert_awaited_once()
    assert result["step_id"] == "verify_connection"
    if invalid:
        assert "TOP CARE needs exactly one" in result["description_placeholders"]["capabilities"]
    else:
        created = await manager.async_configure(result["flow_id"], {})
        assert created["type"] is FlowResultType.CREATE_ENTRY
        assert created["data"]["address"] == ADDRESS


@pytest.mark.parametrize("bad_right", (False, True))
async def test_paired_hold_admits_every_live_target_before_first_movement(hass, bad_right):
    from homeassistant.exceptions import HomeAssistantError

    from tests.test_shared_action_hardening import beds

    async with beds(hass, topology="concurrent") as made:
        clients = []
        for bed, key in zip(made.items, ("n1", "w1"), strict=True):
            bed._bed_type = "topcare"
            client = client_on(service(key))

            async def disconnect(client=client):
                client.is_connected = False

            client.disconnect = AsyncMock(side_effect=disconnect)
            bed._client = client
            bed._controller = TopcareController(bed)
            bed._offline_controller = TopcareController(bed)
            await bed._controller.async_on_connect(session_for(bed._controller, client))
            client.write_gatt_char.reset_mock()
            clients.append(client)
        if bad_right:
            made.items[1].controller.on_disconnect()
        with (
            patch(
                "custom_components.adjustable_bed.services._resolve_sided_targets",
                return_value=([(made.pair, "both")], []),
            ),
            virtual_clock(),
        ):
            call = hass.services.async_call(
                const.DOMAIN,
                "hold_control",
                {"device_id": "pair", "control": "lumbar_pillow_up", "duration": 0.35},
                blocking=True,
            )
            if bad_right:
                with pytest.raises((HomeAssistantError, ValueError)):
                    await call
                assert all(frames(client) == [] for client in clients)
            else:
                await call
                for client, key in zip(clients, ("n1", "w1"), strict=True):
                    assert frames(client) == [expected("lumber_and_pillow_up", key)] * 3 + [
                        expected("stop", key)
                    ]


async def test_idle_reconnect_reselects_route_and_runs_init_once(runtime):
    coordinator, client = runtime
    assert await coordinator.async_connect()
    first = coordinator.controller
    client.write_gatt_char.reset_mock()

    async def disconnect():
        client.is_connected = False

    client.disconnect.side_effect = disconnect
    assert await coordinator.async_disconnect("idle_timeout")
    assert coordinator.controller is None
    client.services = [service("w1")]
    client.is_connected = True
    assert await coordinator.async_connect()
    assert coordinator.controller is not first
    assert frames(client) == [expected("exit_limit", "w1")]
    client.write_gatt_char.reset_mock()
    with virtual_clock():
        await coordinator.async_execute_controller_command(
            lambda c: c.hold_control("tilt_down", 350)
        )
    assert frames(client) == [expected("tile_down", "w1")] * 3 + [expected("stop", "w1")]


async def test_retained_link_failure_restores_session_before_commands(runtime):
    from bleak.exc import BleakError

    coordinator, client = runtime
    assert await coordinator.async_connect()
    client.write_gatt_char.reset_mock()
    client.disconnect.side_effect = BleakError("link retained")
    assert await coordinator.async_disconnect("idle_timeout") is False
    assert coordinator.is_connected
    assert frames(client) == []  # The physical connection survived, so no new init.
    client.write_gatt_char.reset_mock()
    with virtual_clock():
        await coordinator.async_execute_controller_command(lambda c: c.hold_control("head_up", 350))
    assert frames(client) == [expected("head_up")] * 3 + [expected("stop")]
    client.disconnect.side_effect = None


async def test_diagnostic_pause_cleans_up_and_resume_does_not_add_motion(runtime):
    coordinator, client = runtime
    assert await coordinator.async_connect()
    client.write_gatt_char.reset_mock()
    await coordinator.async_pause_position_hydration()
    try:
        await coordinator.controller.stop_notify()
        await coordinator.controller.start_notify()
    finally:
        coordinator.resume_position_hydration()
    assert frames(client) == []
    assert client.stop_notify.await_count == 1
    assert client.start_notify.await_count == 2


async def test_public_combined_card_lease_renews_one_stream_then_expires(hass, runtime):
    coordinator, client = runtime
    assert await coordinator.async_connect()
    client.write_gatt_char.reset_mock()

    async def hold():
        await hass.services.async_call(
            const.DOMAIN,
            "hold_control",
            {
                "device_id": "bed",
                "control": "lumbar_pillow_up",
                "duration": 0.4,
                "hold_owner": "topcare-card",
                "hold_generation": 1,
            },
            blocking=True,
        )

    with virtual_clock():
        initial = asyncio.create_task(hold())
        for _ in range(6):
            await asyncio.sleep(0.2)
            await hold()
            assert not initial.done()
            assert expected("stop") not in frames(client)
        await initial
    assert len(frames(client)) > 11
    assert frames(client)[-1] == expected("stop")
    assert set(frames(client)[:-1]) == {expected("lumber_and_pillow_up")}


async def test_actual_cancellation_before_first_tick_sends_no_movement_or_cleanup():
    client = client_on(service())
    ctrl = TopcareController(MagicMock(client=client, cancel_command=asyncio.Event()))
    await ctrl.async_on_connect(session_for(ctrl, client))
    client.write_gatt_char.reset_mock()
    with virtual_clock():
        task = asyncio.create_task(ctrl.hold_control("tilt_up", 350))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert frames(client) == []
