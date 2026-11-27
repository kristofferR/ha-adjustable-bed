"""Accepted enum86 literals and the actual HA setup, controls and session boundaries."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.comfort_bed import controller as bed
from custom_components.adjustable_bed.beds.comfort_bed.receive import EXACT, CommonReceive
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.light import _light_entities_for
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.profiles.comfort_bed import PROFILE, QUERIES
from custom_components.adjustable_bed.services import async_register_services
from tests.hold_lease_wire import virtual_clock
from tests.test_atlas_lift import client_on, frames, session_for

FIXTURES = Path(__file__).parent / "fixtures/comfort_bed"
VECTORS = json.loads((FIXTURES / "vectors.json").read_text())
RX = json.loads((FIXTURES / "rx-vectors.json").read_text())


GATT = json.loads((FIXTURES / "gatt.json").read_text())


def service(route, *properties):
    service_uuid, tx_uuid, nominal_rx = GATT[route]
    tx = SimpleNamespace(uuid=tx_uuid, properties=properties, handle=15, descriptors=[])
    rx = SimpleNamespace(uuid="first-notify", properties=["notify"], handle=16, descriptors=[])
    nominal = SimpleNamespace(uuid=nominal_rx, properties=["notify"], handle=17, descriptors=[])
    return SimpleNamespace(uuid=service_uuid, characteristics=[tx, rx, nominal])


def literal(name: str, raw: bool = False, side: int = 0) -> bytes:
    return next(
        bytes.fromhex(row["expected_bytes"])
        for row in VECTORS
        if row["action"] == name
        and row["inputs"]["raw"] == raw
        and row["inputs"].get("side", 0) == side
    )


@pytest.mark.parametrize("row", VECTORS, ids=lambda r: r["id"])
def test_existing_codec_reproduces_every_frozen_literal(row):
    inputs = row["inputs"]
    if inputs["kind"] == "query":
        query = {"exitlimit": 0, "clock": 1, "light": 2}[inputs["query"]]
        action, code = QUERIES[query]
    else:
        action = ""
        code = inputs.get("long_code", 0) if inputs["long_press"] else inputs["code"]
    assert codec.function(
        code, inputs.get("side", 0), action=action, single=inputs["raw"]
    ) == bytes.fromhex(row["expected_bytes"])


@pytest.mark.parametrize("row", RX, ids=lambda r: r["id"])
def test_only_the_accepted_common_framer_and_exact_capability_events(row):
    parser = CommonReceive()
    parsed = [frame for chunk in row["chunks"] for frame in parser.feed(bytes.fromhex(chunk))]
    assert [p.hex() for p in parsed] == row["expected_frames"]
    assert parser.buffer.hex() == row["expected_remaining"]
    assert [EXACT[p] for p in parsed if p in EXACT] == row["expected_events"]
    parser.expire()
    assert not parser.buffer


@pytest.mark.parametrize("route", PROFILE.transports)
@pytest.mark.parametrize("no_response", (False, True))
async def test_startup_probes_use_exact_gatt_mode_order_and_early_notifications(route, no_response):
    gatt = service(route, *("write", "write-without-response") if no_response else ("write",))
    client = client_on(gatt)
    c = bed.ComfortBedController(MagicMock(client=client, cancel_command=asyncio.Event()))

    async def subscribe(char, callback):
        callback(char, bytearray.fromhex("6e090100786e0e00037f"))

    client.start_notify.side_effect = subscribe
    with virtual_clock():
        await c.async_on_connect(session_for(c, client))
    assert frames(client) == [
        literal(name, route == "n1")
        for name in ("Startup ExitLimit", "Query clock capability", "Query light capability")
    ]
    assert all(
        call.args[0] is gatt.characteristics[0] and call.kwargs["response"] is not no_response
        for call in client.write_gatt_char.await_args_list
    )
    assert client.start_notify.await_args.args[0] is gatt.characteristics[1]
    assert c._features == {"clock_feature": True, "light_feature": True}
    assert not c.supports_clock_alarm and not c.supports_clock_sync
    assert not c.supports_lights and not c.supports_single_address_pairing
    c.on_disconnect()
    assert c._features == {} and not c._receive.buffer


@pytest.mark.parametrize("bad", ("multiple", "missing_notify", "no_response_only"))
async def test_incoherent_gatt_fails_before_subscription_and_startup(bad):
    gatt = service("w1", "write")
    if bad == "missing_notify":
        gatt.characteristics = gatt.characteristics[:1]
    elif bad == "no_response_only":
        gatt.characteristics[0].properties = ["write-without-response"]
    client = client_on(gatt, *([service("n1", "write")] if bad == "multiple" else []))
    c = bed.ComfortBedController(MagicMock(client=client, cancel_command=asyncio.Event()))
    with pytest.raises(ValueError):
        await c.async_on_connect(session_for(c, client))
    client.start_notify.assert_not_awaited()
    client.write_gatt_char.assert_not_awaited()


@pytest.fixture
async def runtime(hass, request, mock_coordinator_connected, mock_bleak_client, monkeypatch):
    route = getattr(request, "param", "w1")
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Comfort Bed",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:86",
            CONF_NAME: "Comfort Bed",
            const.CONF_BED_TYPE: const.BED_TYPE_COMFORT_BED,
            const.CONF_MOTOR_COUNT: 4,
            const.CONF_PRODUCT_TYPE: "other-app",
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
    monkeypatch.setattr(bed, "TICK_S", 0)
    monkeypatch.setattr(bed, "MENU_DELAY_S", 0)
    await coordinator.async_prime_offline_controller()
    await async_register_services(hass)
    try:
        with patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coordinator, "both")], []),
        ):
            yield coordinator, mock_bleak_client, route == "n1"
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("runtime", ("n1", "w1"), indirect=True)
async def test_native_controls_presets_saves_timers_sides_and_real_services(hass, runtime):
    coordinator, client, raw = runtime
    assert resolve_profile_id(coordinator.entry.data) == "comfort_bed"
    assert await coordinator.async_connect()
    c = coordinator.controller
    assert isinstance(c, bed.ComfortBedController)
    assert [s.key for s in c.motor_control_specs] == ["back", "legs", "head_feet"]
    assert _light_entities_for(hass, coordinator) == []
    buttons = _button_entities_for(hass, coordinator)
    actions = {
        "preset_tv": "TV recall",
        "preset_anti_snore": "AntiSnoring recall",
        "preset_zero_g": "ZeroGravity recall",
        "preset_lounge": "LoungePosition recall",
        "preset_memory_1": "Memory1 recall",
        "preset_memory_2": "Memory2 recall",
        "comfort_bed_save_tv": "TV save",
        "comfort_bed_save_anti_snore": "AntiSnoring save",
        "comfort_bed_save_zero_g": "ZeroGravity save",
        "comfort_bed_save_lounge": "LoungePosition save",
        "comfort_bed_reset": "Motor reset (short)",
        "comfort_bed_sync": "SyncOn (short)",
        "comfort_bed_massage_head_up": "Massage head strengthen",
        "comfort_bed_massage_foot_up": "Massage foot strengthen",
        "comfort_bed_massage_mode": "Massage mode change",
        "comfort_bed_massage_off": "Massage all off",
        "comfort_bed_massage_timer_10": "Massage10 minute timer (short)",
        "comfort_bed_massage_timer_20": "Massage20 minute timer (short)",
        "comfort_bed_massage_timer_30": "Massage30 minute timer (short)",
        "comfort_bed_light_toggle": "Bed light button",
    }
    for side in (0, 1):
        c._select_side("right" if side else "left")
        client.write_gatt_char.reset_mock()
        for suffix in actions:
            button = next(entity for entity in buttons if entity.unique_id.endswith("_" + suffix))
            await button.async_press()
        assert frames(client) == [
            literal(name, raw, 0 if raw else side) for name in actions.values()
        ]
        client.write_gatt_char.reset_mock()
        for slot in (1, 2):
            await hass.services.async_call(
                const.DOMAIN, "save_preset", {"device_id": ["bed"], "preset": slot}, blocking=True
            )
        assert frames(client) == [
            literal(f"Memory{slot} save", raw, 0 if raw else side) for slot in (1, 2)
        ]
        for control, name in (
            ("reset", "Motor reset (3s long fallback)"),
            ("sync", "SyncOn (3s long)"),
            ("timer_10", "Massage10 timer (3s long fallback)"),
            ("timer_20", "Massage20 timer (3s long fallback)"),
            ("timer_30", "Massage30 timer (3s long fallback)"),
        ):
            client.write_gatt_char.reset_mock()
            with virtual_clock():
                await hass.services.async_call(
                    const.DOMAIN,
                    "hold_control",
                    {"device_id": "bed", "control": control, "duration": 3},
                    blocking=True,
                )
            assert frames(client) == [literal(name, raw, 0 if raw else side)]
    c.restore_persisted_app_state({"side": "right"})
    assert c.persisted_app_state == {"side": "right"}
    with pytest.raises(ValueError):
        c.restore_persisted_app_state({"side": "both"})


async def test_native_motor_release_and_stop_drain_inflight_write_on_original_side(runtime):
    coordinator, client, _ = runtime
    assert await coordinator.async_connect()
    c = coordinator.controller
    assert isinstance(c, bed.ComfortBedController)
    for spec, names in zip(
        c.motor_control_specs,
        (
            ("Head up", "Head down"),
            ("Foot up", "Foot down"),
            ("Head and foot up", "Head and foot down"),
        ),
        strict=True,
    ):
        cover = AdjustableBedCover(coordinator, _build_cover_description(spec))
        cover.async_write_ha_state = MagicMock()
        client.write_gatt_char.reset_mock()
        with virtual_clock():
            await cover.async_open_cover()
            await cover.async_close_cover()
        assert frames(client) == [
            literal(n) for name in names for n in (name, name, "Movement STOP")
        ]
    client.write_gatt_char.reset_mock()
    began, finish = asyncio.Event(), asyncio.Event()

    async def write(_char, frame, **kwargs):
        if frame == literal("Head up"):
            began.set()
            await finish.wait()

    client.write_gatt_char.side_effect = write
    movement = asyncio.create_task(
        coordinator.async_execute_controller_command(lambda ctrl: ctrl.move_back_up())
    )
    await asyncio.wait_for(began.wait(), 2)
    c._select_side("right")
    stop = asyncio.create_task(coordinator.async_stop_command())
    await asyncio.sleep(0)
    assert not stop.done()
    finish.set()
    await asyncio.gather(movement, stop)
    assert frames(client) == [literal("Head up"), literal("Movement STOP")]


async def test_replacement_session_never_receives_old_hold_or_queued_command():
    old = client_on(service("w1", "write"))
    coordinator = MagicMock(client=old, cancel_command=asyncio.Event())
    c = bed.ComfortBedController(coordinator)
    with virtual_clock():
        await c.async_on_connect(session_for(c, old))
    callback = old.start_notify.await_args.args[1]
    old.write_gatt_char.reset_mock()
    async with c.ble_lock:
        recall = asyncio.create_task(c.preset_tv())
        await asyncio.sleep(0.15)
        c.on_disconnect()
        new = client_on(service("n1", "write"))
        coordinator.client = new
    with pytest.raises(ConnectionError):
        await recall
    with virtual_clock():
        await c.async_on_connect(session_for(c, new))
    new.write_gatt_char.reset_mock()
    callback(old.services[0].characteristics[1], bytearray.fromhex("6e09010078"))
    assert c._features == {}
    old.write_gatt_char.assert_not_awaited()
    new.write_gatt_char.assert_not_awaited()
    c.on_disconnect()


async def test_failed_movement_is_not_retried_and_still_releases(runtime):
    coordinator, client, _ = runtime
    assert await coordinator.async_connect()
    client.write_gatt_char.reset_mock()

    async def write(_char, frame, **kwargs):
        if frame == literal("Head up"):
            raise BleakError("failed ATT write")

    client.write_gatt_char.side_effect = write
    with pytest.raises(BleakError), virtual_clock():
        await coordinator.controller.move_back_up()
    assert frames(client) == [literal("Head up"), literal("Movement STOP")]


async def test_setup_fixes_current_product_and_restoration_profile(hass):
    from homeassistant.data_entry_flow import FlowResultType

    from tests.test_richmat_family_flow import setup_flow

    flow = setup_flow(hass)
    flow._manual_data.update(
        {const.CONF_MOTOR_COUNT: 4, const.CONF_HAS_MASSAGE: False, const.CONF_PRODUCT_TYPE: "85"}
    )
    with patch.object(flow, "_verification_possible", return_value=False):
        result = await flow.async_step_richmat_family({"choice": "comfort_bed"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[const.CONF_BED_TYPE] == const.BED_TYPE_COMFORT_BED
    assert resolve_profile_id(data) == "comfort_bed"
    assert data[const.CONF_PRODUCT_TYPE] == "86"
    assert data[const.CONF_MOTOR_COUNT] == 2 and data[const.CONF_HAS_MASSAGE] is True


async def test_canceling_text_hold_never_turns_zero_fallback_into_release(runtime):
    coordinator, client, _ = runtime
    assert await coordinator.async_connect()
    client.write_gatt_char.reset_mock()
    with virtual_clock():
        task = asyncio.create_task(coordinator.controller.hold_control("reset", 3000))
        await asyncio.sleep(1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    client.write_gatt_char.assert_not_awaited()


async def test_notify_failure_revokes_early_reply_and_pending_startup():
    client = client_on(service("w1", "write"))
    c = bed.ComfortBedController(MagicMock(client=client, cancel_command=asyncio.Event()))
    callbacks = []

    async def subscribe(char, callback):
        callbacks.append((char, callback))
        callback(char, bytearray.fromhex("6e09010078"))
        raise BleakError("notify failed")

    client.start_notify.side_effect = subscribe
    with pytest.raises(BleakError):
        await c.async_on_connect(session_for(c, client))
    assert c._features == {} and c._link is None
    char, callback = callbacks[0]
    callback(char, bytearray.fromhex("6e0e00037f"))
    assert c._features == {}
    client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("routes", (("n1",), ("n1", "w1"), ()))
async def test_setup_preflight_checks_live_gatt_without_sending_controls(
    hass, enable_custom_integrations, routes
):
    from homeassistant.config_entries import SOURCE_BLUETOOTH

    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from tests.test_atlas_lift import packet_info
    from tests.test_config_flow import _advance_only_progress, _patch_gate

    manager = hass.config_entries.flow
    info = packet_info("Receiver", "xQRRM123")
    choice = await manager.async_init(const.DOMAIN, context={"source": SOURCE_BLUETOOTH}, data=info)
    confirm = await manager.async_configure(
        choice["flow_id"], {"bed_type_choice": const.BED_TYPE_COMFORT_BED}
    )
    settings = await manager.async_configure(
        confirm["flow_id"], {const.CONF_BED_TYPE: const.BED_TYPE_COMFORT_BED}
    )
    assert settings["step_id"] == "finish_settings"
    client = client_on(*(service(route, "write") for route in routes))
    client.disconnect = AsyncMock()
    with (
        patch.object(AdjustableBedConfigFlow, "_verification_possible", return_value=True),
        _patch_gate("hci0", -53),
        patch("bleak_retry_connector.establish_connection", AsyncMock(return_value=client)),
    ):
        progress = await manager.async_configure(settings["flow_id"], {})
        report = await _advance_only_progress(hass, progress)
    assert report["step_id"] == "verify_connection"
    client.start_notify.assert_not_awaited()
    client.write_gatt_char.assert_not_awaited()
    client.disconnect.assert_awaited_once()
    message = report["description_placeholders"]["capabilities"]
    assert ("Comfort Bed needs exactly one" in message) is (len(routes) != 1)
    assert ("The app's connection type is available" in message) is (len(routes) == 1)


async def test_disconnect_during_motion_never_claims_an_unsent_cleanup(runtime):
    coordinator, client, _ = runtime
    assert await coordinator.async_connect()
    c = coordinator.controller
    replacement = client_on(service("n1", "write"))
    replacement.disconnect = AsyncMock()
    client.write_gatt_char.reset_mock()

    async def write(_char, frame, **kwargs):
        c.on_disconnect()
        coordinator._client = replacement

    client.write_gatt_char.side_effect = write
    with pytest.raises(ConnectionError), virtual_clock():
        await c.move_back_up()
    assert frames(client) == [literal("Head up")]
    replacement.write_gatt_char.assert_not_awaited()
    assert c._cleanup_context is None
