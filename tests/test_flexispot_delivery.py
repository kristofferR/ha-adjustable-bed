"""Public regressions for settings delivery, preset exposure and timed motor routing."""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr

from custom_components.adjustable_bed.beds.flexispot import controller as ctrl
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.card import CardSection
from custom_components.adjustable_bed.codec import flexispot as codec
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.number import AdjustableBedControllerNumber
from custom_components.adjustable_bed.services import async_register_services
from custom_components.adjustable_bed.switch import AdjustableBedControllerSwitch
from tests.hold_lease_wire import virtual_clock
from tests.test_flexispot import cleanup as cleanup
from tests.test_flexispot import frames, notify, target


async def _service_target(hass, coord):
    coord.entry.mock_state(hass, ConfigEntryState.LOADED)
    hass.data.setdefault(DOMAIN, {})[coord.entry.entry_id] = coord
    device = dr.async_get(hass).async_get_or_create_from_info(
        config_entry_id=coord.entry.entry_id, device_info=coord.device_info
    )
    await async_register_services(hass)
    return device


async def _settings_actions(hass, coord, bed, kind):
    switches = {
        spec.key: AdjustableBedControllerSwitch(coord, spec) for spec in bed.controller_switch_specs
    }
    level = AdjustableBedControllerNumber(
        coord, next(spec for spec in bed.controller_number_specs if spec.key == "right_massage")
    )
    if kind == "snore":
        return switches["left_snore"].async_turn_off, switches["right_snore"].async_turn_off
    if kind == "global_snore":
        return switches["snore"].async_turn_off, switches["right_snore"].async_turn_off
    if kind == "level":

        async def increment():
            await level.async_set_native_value(3)

        async def next_target():
            await level.async_set_native_value(4)

        return increment, next_target
    if kind == "restore":
        button = ControllerActionButton(
            coord, next(spec for spec in bed.controller_button_specs if spec.key == "restore")
        )
        button.hass = hass

        async def next_level():
            await level.async_set_native_value(3)

        return button.async_press, next_level
    assert kind == "alarm"
    device = await _service_target(hass, coord)

    async def edit_alarm():
        await hass.services.async_call(
            DOMAIN,
            "set_alarm",
            {
                "device_id": [device.id],
                "enabled": True,
                "slot": 2,
                "time": "09:10",
                "weekdays": ["monday", "sunday"],
                "wake_action": "wake_mode_2",
            },
            blocking=True,
        )

    async def next_alarm():
        await hass.services.async_call(
            DOMAIN,
            "set_alarm",
            {"device_id": [device.id], "enabled": False, "slot": 1},
            blocking=True,
        )

    return edit_alarm, next_alarm


@pytest.mark.parametrize("kind", ["snore", "global_snore", "alarm", "level", "restore"])
@pytest.mark.parametrize("submitted", [False, True], ids=["before_submission", "inflight_success"])
async def test_cancelled_public_settings_only_invalidate_delivered_snapshot(hass, kind, submitted):
    coord, bed, client = await target(hass, "eb803")
    action, next_action = await _settings_actions(hass, coord, bed, kind)
    notify(bed)
    snapshot, state = bed._status, dict(coord.controller_state)
    if submitted:
        entered, finish = asyncio.Event(), asyncio.Event()

        async def write(*_args, **_kwargs):
            entered.set()
            await finish.wait()

        client.write_gatt_char.side_effect = write
        task = asyncio.create_task(action())
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        finish.set()
    else:
        async with bed._ble_lock:
            task = asyncio.create_task(action())
            await asyncio.sleep(0)
            task.cancel()
            await asyncio.sleep(0)
    with pytest.raises(asyncio.CancelledError):
        await task
    client.write_gatt_char.side_effect = None
    if submitted:
        assert len(frames(client)) == 1
        if kind in ("snore", "global_snore"):
            assert bed._status.snore_mask is None
            assert all(coord.controller_state[key] is None for key in ctrl.SNORE.values())
            assert coord.controller_state[ctrl.GLOBAL_SNORE] is (
                False if kind == "global_snore" else None
            )
        elif kind == "alarm":
            assert bed._status.alarms is None
        elif kind == "level":
            assert bed._status.right is None
            assert coord.controller_state[ctrl.LEVELS["right"]] is None
        else:
            assert bed._status is None
            assert coord.controller_state[ctrl.LEVELS["right"]] is None
        with pytest.raises(ServiceValidationError) as err:
            await next_action()
        assert err.value.translation_key == "flexispot_status_required"
        assert len(frames(client)) == 1
        notify(bed)
    else:
        assert frames(client) == []
        assert bed._status is snapshot
        assert dict(coord.controller_state) == state
    await next_action()
    assert len(frames(client)) > int(submitted)


@pytest.mark.parametrize("side,key", [("left", 3), ("right", 0x83)])
async def test_eb803_memory_recall_is_an_enabled_public_preset(hass, side, key):
    coord, bed, client = await target(hass, "eb803")
    spec = next(spec for spec in bed.controller_button_specs if spec.key == f"{side}_memory")
    entity = ControllerActionButton(coord, spec)
    entity.hass = hass
    assert entity.entity_registry_enabled_default
    assert spec.card.section is CardSection.PRESETS
    assert entity.capability_attributes["card_section"] == "presets"
    await entity.async_press()
    assert frames(client) == [codec.frame(7, key)]


@pytest.mark.parametrize("direction,opcode", [("up", 1), ("down", 2)])
async def test_eb803_public_back_timed_move_keeps_left_label_and_wire_address(
    hass, direction, opcode
):
    coord, bed, client = await target(hass, "eb803")
    spec = next(spec for spec in bed.motor_control_specs if spec.key == "back")
    assert spec.translation_key == "flexispot_left_back"
    assert spec.hold.up_control == "left_back_up"
    device = await _service_target(hass, coord)
    with virtual_clock():
        await hass.services.async_call(
            DOMAIN,
            "timed_move",
            {
                "device_id": [device.id],
                "motor": "back",
                "direction": direction,
                "duration_ms": 450,
            },
            blocking=True,
        )
    assert frames(client) == [codec.frame(opcode, 1)] * 3 + [codec.frame(3, 1)]


@pytest.mark.parametrize("kind", ["snore", "global_snore", "alarm", "level", "restore"])
async def test_old_settings_completion_preserves_replacement_link_snapshot(hass, kind):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    coord, bed, client = await target(hass, "eb803")
    action, _ = await _settings_actions(hass, coord, bed, kind)
    notify(bed)
    replacement = SimpleNamespace(**vars(client))
    replacement.write_gatt_char = AsyncMock()

    async def disconnect():
        replacement.is_connected = False

    replacement.disconnect = AsyncMock(side_effect=disconnect)
    entered, finish = asyncio.Event(), asyncio.Event()
    fresh_snapshot = None
    fresh_state = None

    async def write(*_args, **_kwargs):
        nonlocal fresh_snapshot, fresh_state
        entered.set()
        await finish.wait()
        coord._client = replacement
        await bed.async_discover_capabilities()
        notify(bed)
        fresh_snapshot, fresh_state = bed._status, dict(coord.controller_state)

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(action())
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert fresh_snapshot is not None and fresh_state is not None
    assert bed._status is fresh_snapshot
    assert dict(coord.controller_state) == fresh_state
    assert frames(replacement) == []
