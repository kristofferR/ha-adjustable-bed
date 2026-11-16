"""Nerum through HA entities, public actions, schedulers and paired routing."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.nerum import controller as runtime
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.profiles import nerum as app
from custom_components.adjustable_bed.services import async_register_services
from custom_components.adjustable_bed.setup_questions import setup_profile_for
from tests.hold_lease_wire import virtual_clock
from tests.test_nerum import frames, gatt

ALARMS = [
    {"hour": 6, "minute": 30, "repeat": 130, "enabled": True, "action": "memory_1"},
    {"hour": 8, "minute": 0, "repeat": 255, "enabled": False, "action": "none"},
    {"hour": 9, "minute": 45, "repeat": 4, "enabled": True, "action": "light"},
]


async def receiver(hass, protocol="p2", address="AA:BB:CC:DD:01:03", layout="4"):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title=address,
        unique_id=address,
        data={
            CONF_ADDRESS: address,
            "name": "Nerum",
            "bed_type": "nerum",
            "protocol_variant": protocol,
            "product_type": layout,
            "motor_count": 4,
            "disable_angle_sensing": True,
            "disconnect_after_command": False,
            "idle_disconnect_seconds": 0,
            "motor_pulse_count": 1,
        },
    )
    entry.add_to_hass(hass)
    co = AdjustableBedCoordinator(hass, entry)
    client = MagicMock(is_connected=True, services=gatt(app.PROFILES[protocol]))
    client.write_gatt_char, client.start_notify, client.stop_notify, client.disconnect = (
        AsyncMock(),
        AsyncMock(),
        AsyncMock(),
        AsyncMock(),
    )
    co._client = client
    ctrl = runtime.NerumController(co, protocol)
    co._controller = co._offline_controller = ctrl
    await ctrl.async_discover_capabilities()
    await ctrl.start_notify()
    co.async_ensure_connected = AsyncMock(return_value=True)
    co.async_connect = AsyncMock(return_value=True)
    co._async_refresh_controller_auth = AsyncMock()

    async def disconnected():
        client.is_connected = False

    client.disconnect.side_effect = disconnected
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = co
    return co, client


@pytest.mark.parametrize("protocol", app.PROTOCOLS)
@pytest.mark.parametrize("layout", app.LAYOUTS)
async def test_saved_setup_lazy_factory_and_side_ownership(hass, protocol, layout):
    from custom_components.adjustable_bed.app_profiles import per_side_profile

    data = {"bed_type": "nerum", "protocol_variant": protocol, "product_type": layout}
    setup = setup_profile_for(data)
    data.update(setup.settled(data))
    co = MagicMock(hass=hass)
    co.entry.data = data
    ctrl = await create_controller(co, "nerum", protocol, None)
    assert isinstance(ctrl, runtime.NerumController)
    assert ctrl.profile.key == protocol
    assert tuple(s.key for s in ctrl.motor_control_specs) == app.LAYOUTS[layout]
    assert data["motor_count"] == (int(layout) if layout != "nerum" else 2)
    assert data["has_massage"] is False and data["motor_pulse_delay_ms"] == 300
    assert {"protocol_variant", "product_type"} <= set(per_side_profile("nerum", protocol).keys)


async def test_app_findability_and_configure_questions(hass):
    from custom_components.adjustable_bed.config_flow import (
        AdjustableBedConfigFlow,
        _configure_questions,
    )
    from custom_components.adjustable_bed.detection import get_bed_type_options

    assert any(
        row["value"] == "nerum" and "Nerum" in row["label"] for row in get_bed_type_options()
    )
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._manual_data = {CONF_ADDRESS: "AA:BB:CC:DD:01:03", "bed_type": "nerum"}
    with patch.object(flow, "_async_finish_family_route", new=AsyncMock()):
        await flow.async_step_profile_questions({"protocol_variant": "p3", "product_type": "3"})
    saved = flow._manual_data
    assert saved["motor_count"] == 3 and saved["disable_angle_sensing"] is True
    assert {q.key for q in _configure_questions(saved).questions} == {
        "protocol_variant",
        "product_type",
    }


@pytest.mark.parametrize("route", ("typed", "picked", "discovered"))
@pytest.mark.parametrize("protocol", ("p1", "p3"))
async def test_new_install_routes_preserve_selected_protocol(
    hass, mock_bluetooth_service_info, route, protocol
):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from tests.form_helpers import finish_new_bed, start_new_bed

    mock_bluetooth_service_info.name = "OKIN-Nerum"
    mock_bluetooth_service_info.device.name = "OKIN-Nerum"
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._discovery_info = mock_bluetooth_service_info
    form = await start_new_bed(flow, route, "nerum", "AA:BB:CC:DD:01:03")
    assert form["step_id"] == "profile_questions"
    answers = form["data_schema"]({"protocol_variant": protocol, "product_type": "3"})
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        final = await flow.async_step_profile_questions(answers)
        assert final["step_id"] == "finish_settings"
        await finish_new_bed(flow, final, {"name": "Nerum"})
    saved = finish.call_args.args[0]
    assert saved["protocol_variant"] == protocol
    assert saved["product_type"] == "3" and saved["motor_count"] == 3
    assert saved["motor_pulse_delay_ms"] == 300 and saved["has_massage"] is False
    coordinator = MagicMock(hass=hass)
    coordinator.entry.data = saved
    controller = await create_controller(coordinator, "nerum", saved["protocol_variant"], None)
    assert isinstance(controller, runtime.NerumController)
    assert controller.profile.key == protocol


@pytest.mark.parametrize("duration", [100, 200, 350])
@pytest.mark.parametrize("latency", [0.005, 0.4])
async def test_real_timed_move_deadline_and_cover_entity(hass, monkeypatch, duration, latency):
    co, client = await receiver(hass)
    await async_register_services(hass)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        lambda *_: ([(co, "both")], []),
    )
    try:
        with virtual_clock() as clock:
            starts = []

            async def write(_char, data, **_kwargs):
                assert co._command_lock.locked()
                starts.append((clock.now, bytes(data)))
                await asyncio.sleep(latency)

            client.write_gatt_char.side_effect = write
            start = clock.now
            await hass.services.async_call(
                const.DOMAIN,
                "timed_move",
                {"device_id": "bed", "motor": "back", "direction": "up", "duration_ms": duration},
                blocking=True,
            )
            movement = [(t, f) for t, f in starts if f != app.build("p2", 6)]
            assert movement and all(t - start < duration / 1000 for t, _ in movement)
            assert frames(client)[-4:] == [app.build("p2", 6)] * 4
            client.write_gatt_char.reset_mock()
            ctrl = co.controller
            cover = AdjustableBedCover(co, _build_cover_description(ctrl.motor_control_specs[0]))
            cover.hass = hass
            cover.async_write_ha_state = MagicMock()
            assert cover.extra_state_attributes["hold_lease_mode"] == "stream"
            await cover.async_open_cover()
            assert frames(client)[0] == app.build("p2", 1, 1)
            assert frames(client)[-1] == app.build("p2", 6)
            buttons = _button_entities_for(hass, co)
            assert any(b.unique_id.endswith("nerum_light") for b in buttons)
            assert not any("program_memory" in b.unique_id for b in buttons)
    finally:
        await co.async_shutdown()


async def test_renewable_hold_expiry_and_stop_drain(hass, monkeypatch):
    co, client = await receiver(hass, layout="nerum")
    await async_register_services(hass)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        lambda *_: ([(co, "both")], []),
    )
    args = {
        "device_id": "bed",
        "motor": "back",
        "direction": "up",
        "duration_ms": 200,
        "hold_owner": "card",
        "hold_generation": 1,
    }
    try:
        with virtual_clock():
            task = asyncio.create_task(
                hass.services.async_call(const.DOMAIN, "timed_move", args, blocking=True)
            )
            for _ in range(3):
                await asyncio.sleep(0.1)
                await hass.services.async_call(const.DOMAIN, "timed_move", args, blocking=True)
                assert not task.done()
                assert app.build("p2", 6) not in frames(client)
            await task
        assert frames(client)[-2:] == [app.build("p2", 6)] * 2
        client.write_gatt_char.reset_mock()
        entered, drain = asyncio.Event(), asyncio.Event()

        async def pending(_char, data, **_kwargs):
            if data != app.build("p2", 6):
                entered.set()
                await drain.wait()

        client.write_gatt_char.side_effect = pending
        with virtual_clock():
            task = asyncio.create_task(
                co.async_execute_controller_command(lambda c: c.hold_control("back_up", 1000))
            )
            await entered.wait()
            stop = asyncio.create_task(co.async_stop_command())
            await asyncio.sleep(0)
            assert not stop.done() and app.build("p2", 6) not in frames(client)
            drain.set()
            await asyncio.gather(task, stop)
        assert frames(client)[-2:] == [app.build("p2", 6)] * 2
    finally:
        await co.async_shutdown()


async def test_bank_batch_validation_and_stop_before_import(hass, monkeypatch):
    left, lc = await receiver(hass)
    right, rc = await receiver(hass, "p1", "AA:BB:CC:DD:01:04")
    await async_register_services(hass)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        lambda *_: ([(left, "both"), (right, "both")], []),
    )
    try:
        with virtual_clock(), pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                const.DOMAIN,
                "nerum_set_alarms",
                {"device_id": ["a", "b"], "alarms": ALARMS},
                blocking=True,
            )
        assert frames(lc) == frames(rc) == []
        monkeypatch.setattr(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            lambda *_: ([(left, "both")], []),
        )
        original = runtime.NerumController

        async def during_import(*_args):
            await left.async_stop_command()

        monkeypatch.setattr(
            "custom_components.adjustable_bed.beds.nerum.services.async_import_modules",
            during_import,
        )
        with virtual_clock():
            await hass.services.async_call(
                const.DOMAIN,
                "nerum_set_alarms",
                {"device_id": "a", "alarms": ALARMS},
                blocking=True,
            )
        assert frames(lc) and all(f == app.build("p2", 6) for f in frames(lc))
        assert isinstance(left.controller, original)
    finally:
        await left.async_shutdown()
        await right.async_shutdown()


async def test_paired_bank_and_movement_keep_physical_side(hass, monkeypatch):
    left, lc = await receiver(hass)
    right, rc = await receiver(hass, "p3", "AA:BB:CC:DD:01:04")
    entry = MockConfigEntry(domain=const.DOMAIN, data={"pair_id": "nerum103"})
    entry.add_to_hass(hass)
    pair = PairedBedCoordinator(
        hass, entry, {"left": left, "right": right}, connection_mode="concurrent"
    )
    await async_register_services(hass)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        lambda *_: ([(pair, "right")], []),
    )
    try:
        with virtual_clock():
            await hass.services.async_call(
                const.DOMAIN,
                "nerum_set_alarms",
                {"device_id": "pair", "alarms": ALARMS},
                blocking=True,
            )
            assert not frames(lc)
            assert len(frames(rc)) == 7
            rc.write_gatt_char.reset_mock()
            await hass.services.async_call(
                const.DOMAIN,
                "timed_move",
                {"device_id": "pair", "motor": "lumbar", "direction": "up", "duration_ms": 100},
                blocking=True,
            )
        assert not frames(lc)
        assert frames(rc) == [app.build("p3", 5, 1)] + [app.build("p3", 6)] * 4
    finally:
        await pair.async_shutdown()


async def test_real_integration_setup_creates_entities_and_parsed_state(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations
):
    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed.beds.nerum import state

    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="Nerum",
        unique_id="AA:BB:CC:DD:01:03",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:01:03",
            "name": "Nerum",
            "bed_type": "nerum",
            "protocol_variant": "p1",
            "product_type": "nerum",
            "motor_count": 2,
            "disable_angle_sensing": True,
            "has_massage": False,
        },
    )
    entry.add_to_hass(hass)
    mock_bleak_client.services = gatt(app.PROFILES["p1"])
    with patch.object(runtime.NerumController, "async_after_connect", AsyncMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    co = hass.data[const.DOMAIN][entry.entry_id]
    ctrl = co.controller
    assert isinstance(ctrl, runtime.NerumController)
    ctrl._receive(ctrl._live(), ctrl._live().notify, bytes.fromhex("a55a000007205000010203020101"))
    assert co.controller_state[state.HEAD] == 1
    registry = er.async_get(hass)
    cover = registry.async_get_entity_id("cover", const.DOMAIN, "AA:BB:CC:DD:01:03_back")
    assert cover and hass.states.get(cover).attributes["card_section"] == "motors"
    assert registry.async_get_entity_id(
        "sensor", const.DOMAIN, "AA:BB:CC:DD:01:03_nerum_head_massage"
    )
    assert not registry.async_get_entity_id(
        "button", const.DOMAIN, "AA:BB:CC:DD:01:03_program_memory_1"
    )
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_stop_of_later_batch_target_during_first_target_prevents_alarm_writes(
    hass, monkeypatch
):
    left, lc = await receiver(hass)
    right, rc = await receiver(hass, "p3", "AA:BB:CC:DD:01:04")
    await async_register_services(hass)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        lambda *_: ([(left, "both"), (right, "both")], []),
    )
    stopped = False

    async def first_write(*_args, **_kwargs):
        nonlocal stopped
        if not stopped:
            stopped = True
            await right.async_stop_command()

    lc.write_gatt_char.side_effect = first_write
    try:
        with virtual_clock():
            await hass.services.async_call(
                const.DOMAIN,
                "nerum_set_alarms",
                {"device_id": ["left", "right"], "alarms": ALARMS},
                blocking=True,
            )
        assert len(frames(lc)) == 2
        assert frames(rc) == [app.build("p3", 6)] * 2
    finally:
        await left.async_shutdown()
        await right.async_shutdown()
