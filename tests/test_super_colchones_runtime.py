"""Saved setup, native entities and shared services on the real HA scheduler."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME, STATE_UNKNOWN
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.super_colchones.controller import (
    SuperColchonesController,
)
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.light import _light_entities_for
from custom_components.adjustable_bed.select import _select_entities_for
from custom_components.adjustable_bed.services import async_register_services
from custom_components.adjustable_bed.state_keys import MASSAGE_TIMER_MINUTES
from tests.test_richmat_family_flow import setup_flow
from tests.test_super_colchones import GATT
from tests.test_super_colchones import clock as clock


@pytest.fixture
async def runtime(hass, request, mock_coordinator_connected, mock_bleak_client, clock):
    product = getattr(request, "param", "afeg350")
    entry = MockConfigEntry(domain=const.DOMAIN, title="Super Colchones", data={CONF_ADDRESS: "AA:BB:CC:DD:EE:15", CONF_NAME: "Super Colchones", const.CONF_BED_TYPE: "super_colchones", const.CONF_PROTOCOL_VARIANT: product, const.CONF_DISABLE_ANGLE_SENSING: True, const.CONF_HAS_MASSAGE: True, const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE})
    entry.add_to_hass(hass)
    target = AdjustableBedCoordinator(hass, entry)
    target._max_retries = 1
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = target
    route = GATT[0]
    tx = SimpleNamespace(uuid=route["write"], properties=["write"], handle=15, descriptors=[])
    rx = SimpleNamespace(uuid=route["notify_candidate"], properties=["notify"], handle=16, descriptors=[])
    mock_bleak_client.services = [SimpleNamespace(uuid=route["service"], characteristics=[tx, rx])]
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    await target.async_prime_offline_controller()
    assert isinstance(target.capability_controller, SuperColchonesController)
    await async_register_services(hass)
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets", return_value=([(target, "both")], [])):
        yield target, mock_bleak_client
    await target.async_shutdown()


def written(client):
    return [call.args[1].hex() for call in client.write_gatt_char.await_args_list]


@pytest.mark.parametrize("product", ("afeg302", "afeg350"))
async def test_setup_requires_exact_product_and_keeps_owned_fields(hass, product):
    flow = setup_flow(hass, name="xQRRM123")
    flow._discovery_info = None
    with patch.object(flow, "_verification_possible", return_value=False):
        result = await flow.async_step_richmat_family({"choice": "super_colchones"})
        assert result["step_id"] == "profile_questions"
        assert result["data_schema"] is not None
        answer = result["data_schema"]({const.CONF_PROTOCOL_VARIANT: product})
        result = await flow.async_step_profile_questions(answer)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[const.CONF_BED_TYPE] == "super_colchones"
    assert data[const.CONF_PROTOCOL_VARIANT] == product
    assert data[const.CONF_HAS_MASSAGE] is True
    assert data[const.CONF_MOTOR_COUNT] == (3 if product == "afeg350" else 2)


@pytest.mark.parametrize("runtime", ("afeg302", "afeg350"), indirect=True)
async def test_native_entity_shapes_shared_memory_and_hold_services(hass, runtime):
    target, client = runtime
    assert await target.async_connect()
    ctrl = target.controller
    assert isinstance(ctrl, SuperColchonesController)
    entities = _button_entities_for(hass, target)
    ids = [entity.unique_id for entity in entities]
    assert len(ids) == len(set(ids))
    for slot in range(1, ctrl.memory_slot_count + 1):
        save = next(e for e in entities if e.unique_id.endswith(f"program_memory_{slot}"))
        assert save.extra_state_attributes["requires_confirmation"] is True
    client.write_gatt_char.reset_mock()
    await hass.services.async_call(const.DOMAIN, "save_preset", {"device_id": ["bed"], "preset": 1}, blocking=True)
    assert written(client) == ["6e01002b9a"]
    cover = AdjustableBedCover(target, _build_cover_description(ctrl.motor_control_specs[0]))
    cover.async_write_ha_state = MagicMock()
    client.write_gatt_char.reset_mock()
    await cover.async_open_cover()
    assert written(client)[-1] == "6e01006edd"
    assert set(written(client)[:-1]) == {"6e01002493"}
    client.write_gatt_char.reset_mock()
    await hass.services.async_call(const.DOMAIN, "hold_control", {"device_id": ["bed"], "control": "head_up", "duration": 0.25}, blocking=True)
    assert written(client) == ["6e01002493"] * 2 + ["6e01006edd"]
    assert not ctrl.supports_clock_sync


async def test_timer_select_uses_delivery_and_reports_explicit_unknown(hass, runtime):
    target, client = runtime
    assert await target.async_connect()
    timer = next(e for e in _select_entities_for(hass, target) if e.unique_id.endswith("massage_timer"))
    assert timer.options == ["10 min", "20 min", "30 min"]
    assert target.controller_state[MASSAGE_TIMER_MINUTES] == STATE_UNKNOWN
    assert timer.current_option is None
    client.write_gatt_char.reset_mock()
    await timer.async_select_option("20 min")
    assert written(client) == ["6e010063d2"]
    assert timer.current_option == "20 min"
    client.write_gatt_char.side_effect = OSError("radio failure")
    with pytest.raises(OSError):
        await timer.async_select_option("30 min")
    assert timer.current_option == "20 min"
    target.controller.on_disconnect()
    assert target.controller_state[MASSAGE_TIMER_MINUTES] == STATE_UNKNOWN
    assert timer.current_option is None


async def test_completed_hold_never_swallows_new_stop(hass, runtime):
    target, client = runtime
    assert await target.async_connect()
    client.write_gatt_char.reset_mock()
    await target.async_execute_controller_command(lambda c: c.hold_control("head_up", 150))
    await target.async_stop_command()
    assert written(client) == ["6e01002493", "6e01006edd", "6e01006edd"]


async def test_preempting_stop_deduplicates_only_the_cancelled_owner(hass, runtime):
    import asyncio
    target, client = runtime
    assert await target.async_connect()
    client.write_gatt_char.reset_mock()
    entered, finish = asyncio.Event(), asyncio.Event()
    async def write(_char, packet, **kwargs):
        if packet == bytes.fromhex("6e01002493"):
            entered.set()
            await finish.wait()
    client.write_gatt_char.side_effect = write
    movement = asyncio.create_task(target.async_execute_controller_command(lambda c: c.hold_control("head_up", 5000)))
    await entered.wait()
    stop = asyncio.create_task(target.async_stop_command())
    await asyncio.sleep(0)
    assert not stop.done()
    finish.set()
    await asyncio.gather(movement, stop)
    assert written(client) == ["6e01002493", "6e01006edd"]
    await target.async_stop_command()
    assert written(client)[-2:] == ["6e01006edd", "6e01006edd"]


@pytest.mark.parametrize("runtime", ("afeg302", "afeg350"), indirect=True)
async def test_light_entity_requires_the_selected_product(hass, runtime):
    target, client = runtime
    assert await target.async_connect()
    assert _light_entities_for(hass, target) == []
    lights = [e for e in _button_entities_for(hass, target) if e.unique_id.endswith("toggle_light")]
    if target.controller.profile.key == "afeg302":
        assert lights == []
    else:
        assert len(lights) == 1
        client.write_gatt_char.reset_mock()
        await lights[0].async_press()
        assert written(client) == ["6e01003cab"]
