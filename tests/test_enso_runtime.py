"""Enso public routing and retained-session behavior."""

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest

from custom_components.adjustable_bed.beds.keeson.enso import LIGHT
from custom_components.adjustable_bed.codec import keeson
from custom_components.adjustable_bed.command_scheduler import (
    _CURRENT_COMMAND_CONTEXT,
    CommandContext,
    CommandKind,
)
from tests.error_helpers import raises_key
from tests.hold_lease_wire import virtual_clock
from tests.test_enso import bed, frames


async def test_massage_timer_tap_never_advertises_a_native_hold():
    c, _, client, _ = await bed()
    timer = next(s for s in c.controller_button_specs if s.key == "enso_timer_massage_page")
    assert timer.hold is None
    await timer.press_fn(c)
    assert frames(client) == [keeson.frame(0x200).hex()]
    client.write_gatt_char.reset_mock()
    with virtual_clock():
        await c.hold_control("timer_memory_page", 200)
    assert frames(client) == [keeson.frame(0x200).hex()] * 2 + [keeson.frame(0).hex()]


async def test_combined_axis_routes_through_the_shared_timed_move_plan():
    from custom_components.adjustable_bed.services import _timed_move_plan

    c, co, client, _ = await bed()
    co.bed_type = "enso"

    @asynccontextmanager
    async def validated(*_args):
        yield c

    with patch("custom_components.adjustable_bed.services._side_validation", validated):
        command, count, interval, resource = await _timed_move_plan(co, co, [], "both", "up", 300)
    assert (count, interval) == (1, 0)
    with virtual_clock():
        await command(c)
    assert frames(client) == [keeson.frame(5).hex()] * 3 + [keeson.frame(0).hex()]
    assert resource == "motor:*"


@pytest.mark.parametrize("unsubscribe_fails", [False, True])
async def test_retained_physical_link_restores_subscription_and_fences_old_callback(
    unsubscribe_fails,
):
    c, _, client, state = await bed()
    await c.start_notify()
    sender, old_receive = client.start_notify.await_args.args
    if unsubscribe_fails:
        client.stop_notify.side_effect = RuntimeError("unsubscribe failed")
        with pytest.raises(RuntimeError):
            await c.stop_notify()
    else:
        await c.stop_notify()
    # A failed disconnect leaves this exact physical client alive.
    await c.lights_toggle()
    assert client.start_notify.await_count == 2
    _, current_receive = client.start_notify.await_args.args
    data = bytearray(16)
    data[13] = 0x40
    old_receive(sender, data)
    assert state.get(LIGHT) is None
    current_receive(sender, data)
    assert state.get(LIGHT) is True
    c.on_disconnect()
    current_receive(sender, data)
    assert state.get(LIGHT) is None


def context(cancel, *, kind=CommandKind.COMMAND, token=None, preempted=()):
    return CommandContext(
        token or object(),
        cancel,
        0,
        "enso-test",
        kind,
        None,
        frozenset({"motor:*"}),
        preempted_contexts=preempted,
    )


async def test_stop_consumes_only_the_preempted_owners_release_once():
    c, co, client, _ = await bed()
    owner = context(co.cancel_command)
    marker = _CURRENT_COMMAND_CONTEXT.set(owner)
    try:
        with virtual_clock():
            await c.hold_control("head_up", 100)
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(marker)
    assert owner.cleanup_stop_sent
    stop = context(
        co.cancel_command, kind=CommandKind.STOP, token=owner.scheduler_token, preempted=(owner,)
    )
    marker = _CURRENT_COMMAND_CONTEXT.set(stop)
    try:
        await c.stop_all()
        assert frames(client) == [keeson.frame(1).hex(), keeson.frame(0).hex()]
        await c.stop_all()  # A later standalone STOP must still send.
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(marker)
    assert frames(client)[-2:] == [keeson.frame(0).hex()] * 2


@pytest.mark.parametrize("new_link", [False, True])
async def test_unrelated_stop_or_a_new_link_cannot_consume_old_cleanup(new_link):
    c, co, client, _ = await bed()
    owner = context(co.cancel_command)
    marker = _CURRENT_COMMAND_CONTEXT.set(owner)
    try:
        with virtual_clock():
            await c.hold_control("head_up", 100)
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(marker)
    if new_link:
        await c.async_discover_capabilities()
    stop = context(
        co.cancel_command,
        kind=CommandKind.STOP,
        token=owner.scheduler_token,
        preempted=(owner,) if new_link else (),
    )
    marker = _CURRENT_COMMAND_CONTEXT.set(stop)
    try:
        await c.stop_all()
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(marker)
    assert frames(client)[-2:] == [keeson.frame(0).hex()] * 2


async def test_fixed_finite_tap_window_is_profile_owned_and_not_offered_in_settings():
    from custom_components.adjustable_bed.app_profiles import hidden_generic_fields
    from custom_components.adjustable_bed.const import CONF_MOTOR_PULSE_COUNT
    from custom_components.adjustable_bed.setup_questions import setup_profile

    profile = setup_profile("enso")
    # Setup and Configure use these declarations to remove generic fields and
    # settle their values; a stale pulse setting cannot change the tap window.
    assert CONF_MOTOR_PULSE_COUNT in hidden_generic_fields("enso", None)
    assert profile.settled({CONF_MOTOR_PULSE_COUNT: 3})[CONF_MOTOR_PULSE_COUNT] == 10
    c, _, client, _ = await bed()
    with virtual_clock():
        await c.move_head_up()
    assert frames(client) == [keeson.frame(1).hex()] * 10 + [keeson.frame(0).hex()]


async def test_rename_trims_java_space_characters_before_validation_and_encoding():
    c, _, client, _ = await bed()
    await c.rename_device(" \tEnso\n ")
    assert frames(client) == [keeson.rename(b"Enso").hex()]
    with raises_key("enso_name_invalid"):
        c.validate_device_rename(" \r\n\t ")


async def test_configure_hides_and_resets_the_profile_owned_tap_window(hass):
    from custom_components.adjustable_bed import const
    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
    from tests.test_sleepys_family_flow import entry_for

    entry = entry_for(
        hass,
        {
            const.CONF_BED_TYPE: "enso",
            const.CONF_PRODUCT_TYPE: "3",
            const.CONF_MOTOR_COUNT: 3,
            const.CONF_MOTOR_PULSE_COUNT: 3,
        },
    )
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    form = await flow._async_options_form(None, step_id="settings")
    assert const.CONF_MOTOR_PULSE_COUNT not in {
        marker.schema for marker in form["data_schema"].schema
    }
    with patch.object(hass.config_entries, "async_schedule_reload"):
        await flow._async_options_form({}, step_id="settings")
    assert entry.data[const.CONF_MOTOR_PULSE_COUNT] == 10


@pytest.mark.parametrize(
    "sent_first,duration,expected",
    [(False, 300, "none"), (True, 300, "partial"), (True, 100, "sent")],
)
async def test_delivery_counts_only_required_frames_withheld_when_event_is_cleared(
    sent_first, duration, expected
):
    from custom_components.adjustable_bed.command_scheduler import delivered

    c, co, client, _ = await bed()
    owner = context(co.cancel_command)
    deliveries = []

    async def cancel_after_frame(*args, **kwargs):
        if bytes(args[1]) != keeson.frame(0):
            co.cancel_command.set()

    client.write_gatt_char.side_effect = cancel_after_frame
    if not sent_first:
        co.cancel_command.set()
    marker = _CURRENT_COMMAND_CONTEXT.set(owner)
    try:
        with virtual_clock(), delivered(deliveries.append):
            await c.hold_control("head_up", duration)
            # Local interruption accounting must not depend on the scheduler
            # event still being set when delivery settles.
            co.cancel_command.clear()
    finally:
        _CURRENT_COMMAND_CONTEXT.reset(marker)
    assert [value.value for value in deliveries] == [expected]
