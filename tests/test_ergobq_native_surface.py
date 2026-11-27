"""ErgoBQ card placement and native timer actions on the HA command scheduler."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.codec import ergobq as codec
from custom_components.adjustable_bed.command_scheduler import Delivery, delivered
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.number import _number_entities_for
from custom_components.adjustable_bed.select import _select_entities_for
from tests.error_helpers import raises_key
from tests.test_ergobq import bed, frames


@pytest.fixture
async def native(hass):
    ctrl, original, client, receive, _ = await bed(serial="010203040405")
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        title="ErgoBQ",
        data={
            **original.entry.data,
            "address": original.address,
            "bed_type": "ergobq",
            "motor_count": 4,
            "has_massage": True,
            "disable_angle_sensing": True,
            "connection_mode": "always",
        },
    )
    entry.add_to_hass(hass)
    co = AdjustableBedCoordinator(hass, entry)
    co._client, co._controller, co._link_ready = client, ctrl, True
    client.disconnect.side_effect = lambda: setattr(client, "is_connected", False)
    ctrl._coordinator = co
    try:
        yield co, ctrl, client, receive
    finally:
        co._client = client
        await co.async_shutdown()


def report(receive, *entries):
    receive(None, bytearray(codec.frame(5, b"".join(dp.encode() for dp in entries))))


def timers(hass, co):
    return {
        e.entity_description.key: e
        for e in _select_entities_for(hass, co)
        if e.entity_description.key.endswith("timer")
    }


async def test_actual_cover_and_target_entities_share_each_motor_row(hass, native):
    co, ctrl, _, _ = native
    targets = {
        e.entity_description.key: e for e in _number_entities_for(hass, co)
    }
    for dp, spec in enumerate(ctrl.motor_control_specs, start=1):
        cover = AdjustableBedCover(co, _build_cover_description(spec))
        target = targets[f"controller_number_ergobq_target_{dp}"]
        assert cover.capability_attributes["card_motor"] == f"ergobq_motor_{dp}"
        assert all(
            target.capability_attributes[key] == value
            for key, value in cover.capability_attributes.items()
        )
    assert not any("minutes" in key for key in targets)


async def test_native_timers_use_reported_state_and_proven_per_zone_options(hass, native):
    co, ctrl, client, receive = native
    controls = timers(hass, co)
    assert set(controls) == {
        "light_timer", "controller_select_ergobq_head_timer", "controller_select_ergobq_legs_timer",
    }
    light = controls["light_timer"]
    head = controls["controller_select_ergobq_head_timer"]
    legs = controls["controller_select_ergobq_legs_timer"]
    assert light.options == [f"{v} min" for v in range(121)]
    assert head.options == legs.options == [f"{v} min" for v in range(61)]
    assert all(e.current_option is None for e in controls.values())
    assert not head.available and not legs.available
    with raises_key("ergobq_massage_state_required"):
        await head.async_select_option("15 min")
    client.write_gatt_char.assert_not_awaited()
    report(
        receive,
        codec.raw(12, codec.Massage(True, 3, 1, 10).encode()),
        codec.raw(14, codec.Massage(False, 2, 0, 20).encode()),
        codec.number(53, 30),
    )
    assert head.available and legs.available
    assert [light.current_option, head.current_option, legs.current_option] == [
        "30 min", "10 min", "20 min",
    ]
    await light.async_select_option("120 min")
    await head.async_select_option("0 min")
    await legs.async_select_option("60 min")
    assert frames(client) == [
        codec.publish((codec.number(53, 120),)).hex(),
        codec.publish((codec.raw(12, codec.Massage(True, 3, 1, 0).encode()),)).hex(),
        codec.publish((codec.raw(14, codec.Massage(False, 2, 0, 60).encode()),)).hex(),
    ]
    # A command does not invent a report, power change, or edit to the other zone.
    assert [light.current_option, head.current_option, legs.current_option] == [
        "30 min", "10 min", "20 min",
    ]
    report(receive, codec.raw(54, bytes([1, 50, 10, 20, 30, 120])))
    assert light.current_option == "120 min"
    report(receive, codec.number(53, 121))
    assert light.current_option is None
    client.write_gatt_char.reset_mock()
    for entity, option in ((light, "121 min"), (head, "61 min"), (legs, "Off")):
        with raises_key("option_unavailable"):
            await entity.async_select_option(option)
    client.write_gatt_char.assert_not_awaited()
    ctrl.on_disconnect()
    assert all(e.current_option is None for e in controls.values())
    assert not head.available and not legs.available


async def test_timer_cancel_before_gatt_marks_no_delivery(native):
    co, _, client, _ = native
    results = []

    async def command(c):
        with delivered(results.append):
            co.cancel_command.set()
            await c.set_light_timer("15 min")

    await co.async_execute_controller_command(command)
    assert results == [Delivery.NONE]
    client.write_gatt_char.assert_not_awaited()


async def test_cancelled_timer_settles_on_original_link_without_replay_or_fake_state(native):
    from custom_components.adjustable_bed.state_keys import LIGHT_TIMER_OPTION

    co, _, client, receive = native
    writing, finish = asyncio.Event(), asyncio.Event()
    results = []

    async def send(*_args, **_kwargs):
        writing.set()
        await finish.wait()

    async def command(c):
        with delivered(results.append):
            await c.set_light_timer("45 min")

    client.write_gatt_char.side_effect = send
    task = asyncio.create_task(co.async_execute_controller_command(command))
    await asyncio.wait_for(writing.wait(), 1)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    replacement = AsyncMock()
    replacement.is_connected = True
    co._client = replacement
    receive(None, bytearray(codec.frame(5, codec.number(53, 45).encode())))
    assert co.controller_state.get(LIGHT_TIMER_OPTION) is None
    finish.set()
    await asyncio.gather(task, return_exceptions=True)
    assert results == [Delivery.SENT]
    assert frames(client) == [codec.publish((codec.number(53, 45),)).hex()]
    replacement.write_gatt_char.assert_not_awaited()
    assert co.controller_state.get(LIGHT_TIMER_OPTION) is None
