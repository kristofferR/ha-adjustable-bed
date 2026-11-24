"""Leva's accepted frame literals, app gates and session boundaries."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.beds.leva import LevaController
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_PRODUCT_TYPE,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    KEESON_BASE_SERVICE_UUID,
    NORDIC_UART_READ_CHAR_UUID,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import (
    detect_bed_type_detailed,
    get_bed_type_options,
)
from custom_components.adjustable_bed.discovery_hints import first_pass
from custom_components.adjustable_bed.errors import BedNotConnectedError
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.paired_devices import child_device_info
from custom_components.adjustable_bed.pairing import get_child
from custom_components.adjustable_bed.pairing_candidates import (
    CONF_PAIR_SELECTION,
    encode_pair_selection,
)
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.profiles import leva as app
from custom_components.adjustable_bed.services import async_register_services
from tests.form_helpers import complete, form_fields
from tests.hold_lease_wire import virtual_clock
from tests.test_config_flow import _advance_progress, _fresh_gate
from tests.test_controller_contract import _FactoryCoordinator
from tests.test_setup_routes import _typed

VECTORS = json.loads((Path(__file__).parent / "fixtures/leva_vectors.json").read_text())


@pytest.mark.parametrize("route", app.TRANSPORTS)
def test_shared_codec_reproduces_leva_literals(route):
    transport = app.TRANSPORTS[route]
    assert set(transport.words) == set(VECTORS[route])
    assert {action: transport.frame(action).hex() for action in transport.words} == VECTORS[route]


def test_leva_clock_reuses_the_nframe_record():
    assert {
        iso: app.clock_frame(datetime.fromisoformat(iso)).hex() for iso in VECTORS["clock"]
    } == VECTORS["clock"]


def _char(uuid, properties, handle):
    return SimpleNamespace(uuid=uuid, properties=properties, handle=handle)


def _client(
    receiver, *, nordic_properties=("write", "write-without-response"), notify_property="notify"
):
    nordic, okin = app.TRANSPORTS["ascent"], app.TRANSPORTS["okin"]
    services = []
    if receiver != "okin":
        services.append(
            SimpleNamespace(
                uuid=nordic.service,
                characteristics=[
                    _char(nordic.write, nordic_properties, 1),
                    _char(NORDIC_UART_READ_CHAR_UUID, (notify_property,), 2),
                ],
            )
        )
    if receiver != "nordic":
        services.append(
            SimpleNamespace(
                uuid=okin.service,
                characteristics=[
                    _char(okin.write, ("write",), 3),
                ],
            )
        )
    return SimpleNamespace(
        is_connected=True,
        services=services,
        write_gatt_char=AsyncMock(),
        start_notify=AsyncMock(),
        write_gatt_descriptor=AsyncMock(),
        stop_notify=AsyncMock(),
    )


async def _controller(model="ascent", receiver="nordic", *, client=None, name="Bed"):
    coordinator = _FactoryCoordinator()
    coordinator.entry.data.update({CONF_PRODUCT_TYPE: model, CONF_PROTOCOL_VARIANT: receiver})
    coordinator.record_command_trace = lambda **_: None
    coordinator.record_notification_trace = lambda **_: None
    coordinator.client = client if client is not None else _client(receiver)
    bed = await create_controller(
        coordinator, "leva", receiver, coordinator.client, device_name=name
    )
    assert isinstance(bed, LevaController)
    await bed.async_discover_capabilities()
    return coordinator, bed


def _writes(client):
    return [
        (call.args[0].uuid, call.kwargs["response"], call.args[1].hex())
        for call in client.write_gatt_char.await_args_list
    ]


@pytest.mark.parametrize(
    ("model", "nordic", "okin", "axes", "memories", "massage"),
    [
        ("ascent", "ascent", None, app.EXTRA_AXES, 0, True),
        ("elite250", "ascent", None, app.BASIC_AXES, 0, False),
        ("elite500", "ascent", "okin", app.BASIC_AXES, 0, True),
        ("evolutionlx", "evolution", None, app.EXTRA_AXES, 2, True),
        ("questelite", "evolution", None, app.EXTRA_AXES, 2, True),
    ],
)
async def test_model_gates_and_separate_app_screen_routes(
    model, nordic, okin, axes, memories, massage
):
    for receiver, remote, home in (
        ("nordic", nordic, nordic),
        ("okin", okin, "okin"),
        ("dual", okin or nordic, "okin"),
    ):
        coordinator, bed = await _controller(model, receiver)
        assert bed.profile.remote == remote and bed.profile.home == home
        assert tuple(spec.key for spec in bed.motor_control_specs) == (axes if remote else ())
        assert bed.memory_slot_count == (memories if remote == "evolution" else 0)
        assert bed.supports_massage == bed.supports_lights == (massage and remote is not None)
        assert bed.supports_preset_tv == bed.supports_preset_anti_snore == massage
        assert bed.supports_clock_sync == (remote == "ascent")
        assert not bed.supports_memory_programming
        assert not bed.supports_device_rename
        assert bed.alarm_capability is None
        assert bed.supports_motor_control == bed.supports_held_control == (remote is not None)
        assert bed.execution.hold == ("stream" if remote else None)
        buttons = {spec.key: spec for spec in bed.controller_button_specs}
        assert not any(spec.hold for spec in buttons.values())
        with virtual_clock():
            await bed.preset_flat()
            main = app.TRANSPORTS[remote or home]
            assert _writes(coordinator.client)[-1] == (
                main.write,
                main.response,
                main.frame("flat").hex(),
            )
            if remote and remote != home:
                await buttons["leva_home_flat"].press_fn(bed)
                quick = app.TRANSPORTS[home]
                assert _writes(coordinator.client)[-1] == (
                    quick.write,
                    quick.response,
                    VECTORS[home]["flat"],
                )
                assert ("leva_home_tv" in buttons) == massage
            else:
                assert "leva_home_flat" not in buttons


@pytest.mark.parametrize(
    "case", ["wrong_mode", "wrong_service", "name_conflict", "duplicate", "missing_gateway"]
)
async def test_gatt_admission_never_guesses_from_a_name_or_shared_uuids(case):
    client = _client("nordic")
    if case == "wrong_mode":
        client.services[0].characteristics[0].properties = ("write",)
    if case == "wrong_service":
        client.services[0].uuid = "bad-service"
    if case == "duplicate":
        client.services[0].characteristics.append(client.services[0].characteristics[0])
    if case == "missing_gateway":
        client.services.append(SimpleNamespace(uuid=KEESON_BASE_SERVICE_UUID, characteristics=[]))
    with pytest.raises(BedNotConnectedError, match="unambiguous"):
        await _controller(client=client, name="OKIN-BLE0000" if case == "name_conflict" else "Bed")
    client.write_gatt_char.assert_not_called()


@pytest.mark.parametrize("notify_property", ["notify", "indicate"])
async def test_nordic_monitor_uses_standard_lifecycle_and_ignores_stale_events(notify_property):
    client = _client("nordic", notify_property=notify_property)
    _, bed = await _controller(client=client)
    with patch.object(bed, "forward_raw_notification") as forward:
        await bed.start_notify()
        char, receive = client.start_notify.await_args.args
        receive(char, bytearray.fromhex("a50b0d"))
        forward.assert_called_once_with(NORDIC_UART_READ_CHAR_UUID, bytes.fromhex("a50b0d"))
        await bed.stop_notify()
        client.stop_notify.assert_awaited_once_with(char)
        await bed.start_notify()
        receive(char, bytearray.fromhex("aa0c"))
        forward.assert_called_once()
        client.write_gatt_descriptor.assert_not_called()


@pytest.mark.parametrize("end", ["cancel", "reconnect"])
async def test_p2_clock_wait_cannot_write_movement_to_an_ended_session(end):
    coordinator, bed = await _controller()
    original = coordinator.client
    with virtual_clock():
        moving = asyncio.create_task(bed.hold_control("legs_up", 500))
        await asyncio.sleep(0.3)  # In the P2 clock settle, before any movement.
        assert len(_writes(original)) == 3
        if end == "cancel":
            coordinator.cancel_command.set()
            moving.cancel()
            with pytest.raises(asyncio.CancelledError):
                await moving
            assert _writes(original)[-1][2] == VECTORS["ascent"]["stop"]
            coordinator.cancel_command.clear()
            await bed.preset_flat()
            assert len(_writes(original)) == 8  # three fresh clock copies and one tap
        else:
            # Even a replacement session on the same Bleak wrapper owns new state.
            await bed.async_discover_capabilities()
            with pytest.raises(BedNotConnectedError):
                await moving
            assert len(_writes(original)) == 3
            await bed.preset_flat()
            assert len(_writes(original)) == 7
        assert not any(frame == VECTORS["ascent"]["footUp"] for _, _, frame in _writes(original))


@pytest.mark.parametrize(
    ("model", "receiver", "route", "release_at"),
    [
        ("questelite", "nordic", "evolution", (250, 300, 350)),
        ("elite500", "okin", "okin", (250, 300, 350)),
    ],
)
async def test_held_frames_and_stop_copies_keep_app_cadence(model, receiver, route, release_at):
    coordinator, bed = await _controller(model, receiver)
    seen = []
    with virtual_clock() as clock:
        coordinator.client.write_gatt_char.side_effect = lambda *args, **_: seen.append(
            (round(clock.time() * 1000), args[1].hex())
        )
        await bed.hold_control("back_up", 250)
    assert seen == [
        *((i, VECTORS[route]["headUp"]) for i in (0, 100, 200)),
        *((i, VECTORS[route]["stop"]) for i in release_at),
    ]


async def test_p1_retry_delays_then_releases_even_when_motion_writes_fail():
    coordinator, bed = await _controller("evolutionlx")
    seen = []
    with virtual_clock() as clock:

        def write(_char, data, *, response):
            assert response is True
            seen.append((round(clock.time() * 1000), data.hex()))
            if data.hex() == VECTORS["evolution"]["headDown"]:
                raise BleakError("Write failed")

        coordinator.client.write_gatt_char.side_effect = write
        with pytest.raises(BleakError):
            await bed.hold_control("back_down", 500)
    assert seen == [
        *((i, VECTORS["evolution"]["headDown"]) for i in (0, 50, 150)),
        *((i, VECTORS["evolution"]["stop"]) for i in (150, 200, 250)),
    ]


async def test_config_flow_keeps_model_receiver_and_derived_fields_on_each_side(
    hass, enable_custom_integrations
):
    assert any(option["value"] == "leva" for option in get_bed_type_options())
    result = await _typed(hass, "leva")
    assert result["step_id"] == "profile_questions"
    assert {str(marker.schema) for marker in form_fields(result["data_schema"])} == {
        CONF_PRODUCT_TYPE,
        CONF_PROTOCOL_VARIANT,
    }
    with (
        patch(
            "custom_components.adjustable_bed.config_flow.AdjustableBedConfigFlow._verification_possible",
            return_value=False,
        ),
        patch("custom_components.adjustable_bed.async_setup_entry", return_value=True),
    ):
        result = await complete(
            hass,
            result,
            {
                "profile_questions": {
                    CONF_PRODUCT_TYPE: "questelite",
                    CONF_PROTOCOL_VARIANT: "dual",
                },
                "finish_settings": {CONF_NAME: "Leva"},
            },
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[CONF_MOTOR_COUNT] == 4 and data[CONF_HAS_MASSAGE]
    assert resolve_profile_id(data) == "leva:dual"
    side = per_side_profile("leva", "dual")
    assert side is not None and side.variant_owned
    assert {
        CONF_PRODUCT_TYPE,
        CONF_PROTOCOL_VARIANT,
        CONF_MOTOR_COUNT,
        CONF_HAS_MASSAGE,
    } <= side.keys


def test_shared_advertisement_keeps_existing_detection_ambiguous():
    info = SimpleNamespace(
        name="OKIN-BLE1234",
        address="AA:BB:CC:DD:EE:FF",
        service_uuids=[KEESON_BASE_SERVICE_UUID],
        service_data={},
        manufacturer_data={},
        connectable=True,
        rssi=-52,
    )
    result = detect_bed_type_detailed(info)
    assert result.bed_type and result.bed_type != "leva"
    assert first_pass(info).service("leva")
    assert "leva" not in (result.ambiguous_types or ())


async def _live_entry(hass, address, model, receiver):
    profile = app.LevaProfile(app.MODELS[model], receiver)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=profile.model.label,
        unique_id=address,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: profile.model.label,
            CONF_BED_TYPE: "leva",
            CONF_PRODUCT_TYPE: model,
            CONF_PROTOCOL_VARIANT: receiver,
            CONF_MOTOR_COUNT: len(profile.axes),
            "disable_angle_sensing": True,
            "disconnect_after_command": False,
            "idle_disconnect_seconds": 0,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    client = _client(receiver)
    client.disconnect = AsyncMock(side_effect=lambda: setattr(client, "is_connected", False))
    coordinator._client = client
    bed = await create_controller(coordinator, "leva", receiver, client)
    coordinator._controller = coordinator._offline_controller = bed
    coordinator._ready = coordinator._link_ready = True
    await bed.async_discover_capabilities()
    entry.mock_state(hass, ConfigEntryState.LOADED)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    return entry, coordinator, client


async def test_public_hold_stop_and_clock_share_one_session_lane(hass):
    """STOP finishes a pending P2 init, then a new action can sync and move."""
    entry, coordinator, client = await _live_entry(hass, "AA:BB:CC:DD:EE:62", "ascent", "nordic")
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **coordinator.device_info
    )
    await async_register_services(hass)

    async def action(action_name, **data):
        await hass.services.async_call(
            DOMAIN, action_name, {"device_id": [device.id], **data}, blocking=True
        )

    seen = []
    try:
        with virtual_clock():

            async def write(_char, data, *, response):
                assert response is False
                seen.append(data.hex())
                # STOP arrives while the first backend write is still in flight.
                await asyncio.sleep(0.1)

            client.write_gatt_char.side_effect = write
            moving = asyncio.create_task(action("hold_control", control="back_up", duration=2))
            await asyncio.sleep(0.05)
            await action("stop_all")
            await moving
            assert [frame[:4] for frame in seen] == ["0704", "0502"]
            assert seen[-1] == VECTORS["ascent"]["stop"]
            await action("sync_clock")
            assert [frame[:4] for frame in seen[2:]] == ["0704"] * 3
            await action("hold_control", control="pillow_up", duration=0.1)
        assert seen[-2:] == [VECTORS["ascent"]["pillowTiltUp"], VECTORS["ascent"]["stop"]]
    finally:
        await coordinator.async_shutdown()


async def test_p3_delayed_stop_copies_stay_on_the_released_link():
    coordinator, bed = await _controller("elite500", "okin")
    original = coordinator.client
    with virtual_clock():
        releasing = asyncio.create_task(bed.hold_control("back_up", 100))
        await asyncio.sleep(0.125)
        assert [frame for _, _, frame in _writes(original)] == [
            VECTORS["okin"]["headUp"],
            VECTORS["okin"]["stop"],
        ]
        coordinator.client = _client("okin")
        await bed.async_discover_capabilities()
        await releasing
    assert len(_writes(original)) == 2
    assert not _writes(coordinator.client)


async def test_setup_rejects_wrong_write_mode_and_rechecks_corrected_receiver(
    hass, enable_custom_integrations
):
    result = await _typed(hass, "leva")
    evidence, device = _fresh_gate("hci0", -50)
    device.name = "Bed"
    wrong_mode = _client("nordic", nordic_properties=("write",))
    right_mode = _client("okin")
    for client in (wrong_mode, right_mode):
        client.disconnect = AsyncMock()
    with (
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=True),
        patch(
            "custom_components.adjustable_bed.config_flow.async_wait_for_advertisement",
            return_value=(evidence, device),
        ),
        patch("bleak_retry_connector.establish_connection", side_effect=(wrong_mode, right_mode)),
        patch("custom_components.adjustable_bed.config_flow.discover_services", return_value=True),
        patch("custom_components.adjustable_bed.config_flow.read_ble_device_info") as read_info,
        patch("custom_components.adjustable_bed.async_setup_entry", return_value=True),
    ):
        pending = await complete(
            hass,
            result,
            {
                "profile_questions": {
                    CONF_PRODUCT_TYPE: "elite500",
                    CONF_PROTOCOL_VARIANT: "nordic",
                },
            },
        )
        mismatch = await _advance_progress(hass, pending)
        assert mismatch["step_id"] == "profile_questions"
        assert mismatch["errors"] == {CONF_PROTOCOL_VARIANT: "leva_receiver_mismatch"}
        assert not hass.config_entries.async_entries(DOMAIN)
        pending = await hass.config_entries.flow.async_configure(
            mismatch["flow_id"],
            {
                CONF_PRODUCT_TYPE: "elite500",
                CONF_PROTOCOL_VARIANT: "okin",
            },
        )
        verified = await _advance_progress(hass, pending)
        assert verified["step_id"] == "verify_connection"
        created = await hass.config_entries.flow.async_configure(verified["flow_id"], {})
        assert created["type"] == FlowResultType.CREATE_ENTRY
        assert created["data"][CONF_PROTOCOL_VARIANT] == "okin"
    for client in (wrong_mode, right_mode):
        client.disconnect.assert_awaited_once()
        client.write_gatt_char.assert_not_called()
    read_info.assert_not_awaited()


async def test_mixed_pair_keeps_its_models_and_rejects_both_for_one_side_only_axis(
    hass, enable_custom_integrations
):
    left, left_coord, left_client = await _live_entry(hass, "AA:BB:CC:DD:EE:61", "elite500", "okin")
    right, right_coord, right_client = await _live_entry(
        hass, "AA:BB:CC:DD:EE:62", "ascent", "nordic"
    )
    pair = None
    try:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_ADDRESS: "pair_beds"}
        )
        with patch("custom_components.adjustable_bed.async_setup_entry", return_value=True):
            created = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_PAIR_SELECTION: encode_pair_selection(left.entry_id, right.entry_id)},
            )
        assert created["type"] == FlowResultType.CREATE_ENTRY
        for side, model, receiver in (("left", "elite500", "okin"), ("right", "ascent", "nordic")):
            child = get_child(created["data"], side)
            assert child is not None
            assert child[CONF_PRODUCT_TYPE] == model and child[CONF_PROTOCOL_VARIANT] == receiver
        paired_entry = created["result"]
        pair = PairedBedCoordinator(hass, paired_entry, {"left": left_coord, "right": right_coord})
        hass.data[DOMAIN][paired_entry.entry_id] = pair
        registry = dr.async_get(hass)
        parent = registry.async_get_or_create(
            config_entry_id=paired_entry.entry_id, **pair.device_info
        )
        children = {
            side: registry.async_get_or_create_child(
                config_entry_id=paired_entry.entry_id, **child_device_info(pair, side)
            )
            for side in ("left", "right")
        }
        await async_register_services(hass)

        async def hold(device, control):
            await hass.services.async_call(
                DOMAIN,
                "hold_control",
                {
                    "device_id": [device.id],
                    "control": control,
                    "duration": 0.1,
                },
                blocking=True,
            )

        with virtual_clock():
            with pytest.raises(ServiceValidationError):
                await hold(parent, "pillow_up")
            assert not _writes(left_client) and not _writes(right_client)
            await hold(children["left"], "back_up")
            assert [frame for _, _, frame in _writes(left_client)] == [
                VECTORS["okin"]["headUp"],
                *[VECTORS["okin"]["stop"]] * 3,
            ]
            assert not _writes(right_client)
            await hold(children["right"], "pillow_up")
            assert [frame for _, _, frame in _writes(right_client)][-2:] == [
                VECTORS["ascent"]["pillowTiltUp"],
                VECTORS["ascent"]["stop"],
            ]
    finally:
        if pair is not None:
            await pair.async_shutdown()
        else:
            await left_coord.async_shutdown()
            await right_coord.async_shutdown()
