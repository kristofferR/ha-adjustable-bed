"""BERUN through actual HA setup declarations, entities and public scheduling."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.berun.controller import BerunController
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.profiles import berun as app
from custom_components.adjustable_bed.services import async_register_services
from custom_components.adjustable_bed.setup_questions import setup_profile_for
from tests.hold_lease_wire import virtual_clock
from tests.test_berun import frames, gatt


async def receiver(hass, version="v6"):
    data = {
        "bed_type": "berun",
        "protocol_variant": version,
        "connection_mode": "always",
        "motor_pulse_count": 1,
    }
    data.update(setup_profile_for(data).settled(data))
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="BERUN",
        unique_id="AA:BB:CC:DD:01:03",
        data={CONF_ADDRESS: "AA:BB:CC:DD:01:03", "name": "BERUN", **data},
    )
    entry.add_to_hass(hass)
    co = AdjustableBedCoordinator(hass, entry)
    client = MagicMock(
        is_connected=True, services=gatt({6: 0, 7: 1, 8: 2, 9: 2}[app.PROFILES[version].version])
    )
    client.write_gatt_char, client.start_notify, client.stop_notify, client.disconnect = (
        AsyncMock(),
        AsyncMock(),
        AsyncMock(),
        AsyncMock(),
    )
    co._client = client
    c = await create_controller(co, "berun", version, client)
    co._controller = co._offline_controller = c
    await c.async_discover_capabilities()
    await c.start_notify()
    co.async_ensure_connected = AsyncMock(return_value=True)
    co.async_connect = AsyncMock(return_value=True)
    co._async_refresh_controller_auth = AsyncMock()

    async def disconnect():
        client.is_connected = False

    client.disconnect.side_effect = disconnect
    return co, client


@pytest.mark.parametrize("version", app.PROFILES)
async def test_saved_profile_factory_entities_and_setup_ownership(hass, version):
    co, client = await receiver(hass, version)
    try:
        c = co.controller
        assert isinstance(c, BerunController)
        assert resolve_profile_id(co.entry.data) == f"berun:{version}"
        assert co.entry.data["motor_count"] == 2 and co.entry.data["has_massage"] is False
        assert (
            co.entry.data["motor_pulse_delay_ms"] == 200
            and co.entry.data["disable_angle_sensing"] is True
        )
        assert len(c.motor_control_specs) == 2 and all(
            s.scheduler_resource == "*" for s in c.motor_control_specs
        )
        assert not c.supports_memory_programming and not c.supports_memory_presets
        buttons = _button_entities_for(hass, co)
        assert buttons
        memory = next(b for b in buttons if b.unique_id == co.entity_unique_id("memory"))
        assert memory.entity_registry_enabled_default
        assert memory.capability_attributes["card_section"] == "presets"
        assert memory.extra_state_attributes["held_control"] == "memory"
        flat = next(b for b in buttons if b.unique_id == co.entity_unique_id("preset_flat"))
        assert flat.extra_state_attributes["held_control"] == "flat"
        assert flat.extra_state_attributes["hold_lease_mode"] == "stream"
        assert flat.extra_state_attributes["hold_start_delay_ms"] == 0
        assert flat.extra_state_attributes["hold_release_delay_ms"] == 0
        assert not any("save" in spec.key for spec in c.controller_button_specs)
        cover = AdjustableBedCover(co, _build_cover_description(c.motor_control_specs[0]))
        cover.hass = hass
        cover.async_write_ha_state = MagicMock()
        assert cover.extra_state_attributes["hold_lease_mode"] == "stream"
        with virtual_clock():
            await cover.async_open_cover()
        assert len(frames(client)) >= 2
        assert all(f == c.berun.frame(1).hex() for f in frames(client)[:-1])
        assert frames(client)[-1] == c.berun.frame(0).hex()
    finally:
        await co.async_shutdown()


def test_version_advertisement_priority_company_id_and_explicit_setup_seed(hass):
    setup = setup_profile_for({"bed_type": "berun"})
    assert setup is not None and setup.seed is not None

    def info(md, name="OKIN device"):
        return MagicMock(name=name, manufacturer_data=md)

    for md, expected in (
        ({0x4B4F: b"DOT\0\x01"}, "v7"),
        ({0x1234: b"DOT\0\x01"}, "v8"),
        ({0x1234: b"DOT\0\x02"}, "v9"),
        ({}, "v6"),
    ):
        assert app.advertisement("OKIN device", md) == expected
        discovered = info(md)
        discovered.name = "OKIN device"
        assert setup.seed(hass, {"bed_type": "berun"}, discovered)["protocol_variant"] == expected
        assert (
            setup.seed(hass, {"bed_type": "berun", "protocol_variant": "v7"}, discovered)[
                "protocol_variant"
            ]
            == "v7"
        )
    assert app.advertisement("other", {0x4B4F: b""}) is None


@pytest.mark.parametrize("version", app.PROFILES)
async def test_public_alarm_has_exact_interleaved_repetition(hass, monkeypatch, version):
    co, client = await receiver(hass, version)
    await async_register_services(hass)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        lambda *_: ([(co, "both")], []),
    )
    try:
        with virtual_clock() as clock:
            starts = []

            async def write(char, data, **kwargs):
                starts.append(clock.now)

            client.write_gatt_char.side_effect = write
            began = clock.now
            await hass.services.async_call(
                const.DOMAIN,
                "set_alarm",
                {"device_id": "bed", "enabled": True, "time": "07:30:00", "wake_action": "massage"},
                blocking=True,
            )
        c = co.controller
        kind = 9 if c.berun.version < 8 else 8
        alarm = c.berun.alarm_frame(7, 30, 255, kind).hex()
        query = c.berun.query(alarm=True).hex()
        assert frames(client) == [alarm, query, alarm, query, alarm]
        assert [round((t - began) * 1000) for t in starts] == [0, 0, 300, 300, 600]
        client.write_gatt_char.reset_mock()
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                const.DOMAIN,
                "set_alarm",
                {
                    "device_id": "bed",
                    "enabled": True,
                    "time": "07:30:00",
                    "weekdays": ["monday"],
                    "wake_action": "massage",
                },
                blocking=True,
            )
        assert not client.write_gatt_char.called
        with virtual_clock():
            await hass.services.async_call(
                const.DOMAIN, "set_alarm", {"device_id": "bed", "enabled": False}, blocking=True
            )
        off = c.berun.alarm_frame(0, 0, 0, 0).hex()
        assert frames(client) == [off, query, off, query, off]
    finally:
        await co.async_shutdown()


async def test_public_stop_waits_for_inflight_frame_and_single_release(hass, monkeypatch):
    co, client = await receiver(hass)
    await async_register_services(hass)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        lambda *_: ([(co, "both")], []),
    )
    entered, drain = asyncio.Event(), asyncio.Event()

    async def pending(char, data, **kwargs):
        if bytes(data) != co.controller.berun.frame(0):
            entered.set()
            await drain.wait()

    client.write_gatt_char.side_effect = pending
    try:
        with virtual_clock():
            moving = asyncio.create_task(
                hass.services.async_call(
                    const.DOMAIN,
                    "timed_move",
                    {"device_id": "bed", "motor": "back", "direction": "up", "duration_ms": 1000},
                    blocking=True,
                )
            )
            await entered.wait()
            stop = asyncio.create_task(co.async_stop_command())
            await asyncio.sleep(0)
            assert not stop.done() and len(frames(client)) == 1
            drain.set()
            await asyncio.gather(moving, stop)
        assert frames(client) == [
            co.controller.berun.frame(1).hex(),
            co.controller.berun.frame(0).hex(),
        ]
    finally:
        await co.async_shutdown()


async def test_manual_profile_question_is_required_and_saved(hass):
    from unittest.mock import patch

    from custom_components.adjustable_bed.config_flow import (
        AdjustableBedConfigFlow,
        _configure_questions,
    )

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._manual_data = {CONF_ADDRESS: "AA:BB:CC:DD:01:03", "bed_type": "berun"}
    form = await flow.async_step_profile_questions()
    assert form["type"] == "form" and form["step_id"] == "profile_questions"
    with patch.object(flow, "_async_finish_family_route", new=AsyncMock()):
        await flow.async_step_profile_questions({"protocol_variant": "v8"})
    saved = flow._manual_data
    assert saved["protocol_variant"] == "v8" and saved["motor_count"] == 2
    assert {q.key for q in _configure_questions(saved).questions} == {"protocol_variant"}


async def test_shared_names_only_offer_berun_as_explicit_app_candidate(hass):
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.test_detection import _make_service_info

    result = detect_bed_type_detailed(_make_service_info(name="smartbedBERUN"))
    assert result.bed_type != "berun" and "berun" in (result.ambiguous_types or [])


@pytest.mark.parametrize("version", tuple(app.PROFILES))
async def test_each_version_can_submit_final_settings(hass, version):
    from unittest.mock import patch

    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._manual_data = {CONF_ADDRESS: "AA:BB:CC:DD:01:03", "bed_type": "berun"}
    with patch.object(flow, "_async_finish_family_route", new=AsyncMock()):
        await flow.async_step_profile_questions({"protocol_variant": version})
    flow._final_settings_then = "verify"
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_finish_settings({"name": "BERUN"})
    finish.assert_awaited_once()
    assert finish.await_args.args[0]["protocol_variant"] == version
