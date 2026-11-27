"""Native command delivery controls state, caches and the shared timer select."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from custom_components.adjustable_bed.beds.jiecang import dreamotion_smart as bed
from custom_components.adjustable_bed.command_scheduler import (
    Delivery,
    current_command_context,
    delivered,
)
from custom_components.adjustable_bed.profiles import dreamotion_smart as app
from custom_components.adjustable_bed.select import (
    AdjustableBedMassageTimerSelect,
    _select_entities_for,
)
from custom_components.adjustable_bed.state_keys import (
    LIGHT_LEVEL,
    MASSAGE_TIMER_MINUTES,
    UNDER_BED_LIGHTS_RGB,
)
from tests.error_helpers import raises_key
from tests.test_dreamotion_smart_runtime import runtime as runtime  # noqa: F401


@pytest.fixture
def settings(runtime, monkeypatch):
    c = runtime.controller
    for packet in (
        "f2f28002a132",
        "f2f28105a101020101",
        "f2f24507a164ff0080012c",
        "f2f2440da164ff00003200ff00190000ff",
    ):
        c._receive(bytes.fromhex(packet))

    async def pause(_ms, cancel):
        await asyncio.sleep(0)
        return cancel.is_set()

    monkeypatch.setattr(c, "_pause", pause)
    return runtime, c, runtime.client


def value(target, kind):
    key = {"timer": MASSAGE_TIMER_MINUTES, "mode": bed.MODE, "rgb": UNDER_BED_LIGHTS_RGB}[kind]
    return target.controller_state.get(key)


def cached(c, kind):
    return {
        "timer": (c._massage, c._massage_known),
        "mode": (c._massage.hz, c._mode_known),
        "rgb": c._timed,
    }[kind]


async def change(c, kind):
    if kind == "timer":
        await c.set_massage_timer(20)
    elif kind == "mode":
        await c.set_mode("acoustic")
    else:
        await c.set_light_color_with_level((1, 2, 3), 50)


@pytest.mark.parametrize("kind", ("timer", "mode", "rgb"))
@pytest.mark.parametrize("interrupt", ("cancel", "stop"))
async def test_before_dispatch_keeps_state_and_cache(settings, kind, interrupt):
    target, c, client = settings
    before, state = cached(c, kind), dict(target.controller_state)
    results = []
    entered = asyncio.Event()
    stop = None

    async def operation(ctrl):
        entered.set()
        with delivered(results.append):
            await change(ctrl, kind)

    async with c._ble_lock:
        task = asyncio.create_task(target.async_execute_controller_command(operation))
        await entered.wait()
        if interrupt == "cancel":
            task.cancel()
            await asyncio.sleep(0)
        else:
            stop = asyncio.create_task(target.async_stop_command())
            while not target.cancel_command.is_set():
                await asyncio.sleep(0)
    if interrupt == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        assert stop is not None
        await stop
        await task
    assert results == [Delivery.NONE]
    assert cached(c, kind) == before
    assert dict(target.controller_state) == state
    assert all(a.args[1][2] == 0x4E for a in client.write_gatt_char.await_args_list)


@pytest.mark.parametrize("kind", ("timer", "mode", "rgb"))
@pytest.mark.parametrize("interrupt", ("cancel", "stop"))
async def test_submitted_final_write_settles_before_cancellation(settings, kind, interrupt):
    target, c, client = settings
    entered, finish = asyncio.Event(), asyncio.Event()
    results = []
    final_count = 2 if kind == "rgb" else 1
    stop = None

    async def write(_char, _packet, **_kwargs):
        if client.write_gatt_char.await_count == final_count:
            entered.set()
            await finish.wait()

    async def operation(ctrl):
        with delivered(results.append):
            await change(ctrl, kind)

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(target.async_execute_controller_command(operation))
    await entered.wait()
    # Before backend settlement nothing claims the requested value.
    assert value(target, kind) == {"timer": 10, "mode": "inherent", "rgb": (255, 0, 128)}[kind]
    if interrupt == "cancel":
        task.cancel()
        await asyncio.sleep(0)
    else:
        stop = asyncio.create_task(target.async_stop_command())
        while not target.cancel_command.is_set():
            await asyncio.sleep(0)
    finish.set()
    if interrupt == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        assert stop is not None
        await stop
        await task
    assert results == [Delivery.SENT]
    assert value(target, kind) == {"timer": 20, "mode": "acoustic", "rgb": (1, 2, 3)}[kind]
    if kind == "timer":
        assert c._massage.duration == 2 and c._massage_known
    elif kind == "mode":
        assert c._massage.hz == 0 and c._mode_known
    else:
        assert c._timed == (app.Color(50, 1, 2, 3), 300)


@pytest.mark.parametrize("kind", ("mode", "rgb", "saved"))
@pytest.mark.parametrize("interrupt", ("cancel", "stop"))
async def test_composite_cut_between_frames_marks_value_and_cache_unknown(
    settings, kind, interrupt, monkeypatch
):
    target, c, client = settings
    entered = asyncio.Event()
    results = []
    if kind == "saved":
        c.set_page("presets")

    async def pause(_ms, cancel):
        entered.set()
        await asyncio.Event().wait()
        return cancel.is_set()

    async def operation(ctrl):
        with delivered(results.append):
            if kind == "mode":
                await ctrl.set_mode("inherent")
            else:
                await ctrl.set_light_color_with_level((1, 2, 3), 50)

    monkeypatch.setattr(c, "_pause", pause)
    task = asyncio.create_task(target.async_execute_controller_command(operation))
    await entered.wait()
    if interrupt == "cancel":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        # Native STOP preempts the blocked opaque command task.
        await target.async_stop_command()
        await task
    assert results == [Delivery.PARTIAL]
    if kind == "mode":
        assert target.controller_state[bed.MODE] is None and not c._mode_known
    else:
        assert target.controller_state[UNDER_BED_LIGHTS_RGB] is None
        assert target.controller_state[LIGHT_LEVEL] is None
        assert (c._colors if kind == "saved" else c._timed) is None
    assert client.write_gatt_char.await_args_list[0].args[1][2] in (0x80, 0x44, 0x45)


@pytest.mark.parametrize("kind", ("timer", "mode", "rgb", "saved"))
@pytest.mark.parametrize("partial", (False, True))
async def test_newer_notifications_win_over_command_echo_and_invalidation(settings, kind, partial):
    target, c, client = settings
    if kind == "saved":
        c.set_page("presets")
    report = {
        "timer": "f2f28105a103020103",
        "mode": "f2f28002a132",
        "rgb": "f2f24507a119090807003c",
        "saved": "f2f2440da1190908073200ff00190000ff",
    }[kind]

    async def write(_char, _packet, **_kwargs):
        if client.write_gatt_char.await_count == 1:
            c._receive(bytes.fromhex(report))
            if partial:
                context = current_command_context()
                assert context is not None
                context.cancel_event.set()

    client.write_gatt_char.side_effect = write
    if kind == "saved":
        await target.async_execute_controller_command(lambda ctrl: ctrl.set_light_color((1, 2, 3)))
    else:
        await target.async_execute_controller_command(lambda ctrl: change(ctrl, kind))
    if kind == "timer":
        assert c._massage.duration == 3 and c._massage.back == 3
        assert target.controller_state[MASSAGE_TIMER_MINUTES] == 30
    elif kind == "mode":
        assert c._massage.hz == 0x32 and target.controller_state[bed.MODE] == "inherent"
    else:
        assert c._color() == app.Color(25, 9, 8, 7)
        assert target.controller_state[UNDER_BED_LIGHTS_RGB] == (9, 8, 7)


async def test_shared_timer_select_toggles_proven_durations_without_an_off_option(hass, settings):
    target, c, client = settings
    (timer,) = [
        e
        for e in _select_entities_for(hass, target)
        if isinstance(e, AdjustableBedMassageTimerSelect)
    ]
    timer.async_write_ha_state = MagicMock()
    assert timer.options == ["10 min", "20 min", "30 min"]
    assert timer.current_option == "10 min"
    await timer.async_select_option("20 min")
    assert c._massage.duration == 2 and timer.current_option == "20 min"
    await timer.async_select_option("20 min")
    assert c._massage.duration == 0 and timer.current_option is None
    assert [a.args[1] for a in client.write_gatt_char.await_args_list] == [
        replace(c._massage, duration=2).frame(),
        c._massage.frame(),
    ]
    with raises_key("option_unavailable"):
        await timer.async_select_option("Off")
    with raises_key("option_unavailable"):
        await c.set_massage_timer(0)
    assert not any(
        s.key.endswith(("timer10", "timer20", "timer30")) for s in c.controller_button_specs
    )


async def test_user_refusals_carry_translated_keys(settings):
    target, c, client = settings
    c._massage_known = False
    with raises_key("dreamotion_smart_refresh"):
        await c.set_massage_timer(10)
    with raises_key("dreamotion_smart_refresh"):
        await c.set_mode("inherent")
    c._massage_known = True
    c._massage = replace(c._massage, hz=0)
    with raises_key("dreamotion_smart_inherent"):
        await c.cycle_massage("back")
    c._timed = None
    with raises_key("dreamotion_smart_refresh"):
        await c.set_light_color((1, 2, 3))
    with raises_key("dreamotion_smart_refresh"):
        await c._save_light(preview=False)
    with raises_key("dreamotion_smart_duration"):
        await c.set_duration(7)
    with raises_key("option_unavailable"):
        await c.set_mode("unsupported")
    assert client.write_gatt_char.await_count == 0


@pytest.mark.parametrize("kind", ("timer", "mode", "rgb"))
async def test_replaced_link_and_old_callback_cannot_settle_into_new_state(settings, kind):
    target, c, client = settings
    sender, old_callback = client.start_notify.await_args.args
    original_link = c._link
    report = {
        "timer": "f2f28105a103020103",
        "mode": "f2f28002a132",
        "rgb": "f2f24507a119090807003c",
    }[kind]

    async def write(_char, _packet, **_kwargs):
        if client.write_gatt_char.await_count == 1:
            # Same physical client object, new controller session identity.
            c.on_disconnect()
            c._select_transport()
            assert c._link is not original_link
            c._receive(bytes.fromhex(report))
            old_callback(sender, bytearray.fromhex("f2f28105a100000000"))

    client.write_gatt_char.side_effect = write
    with raises_key("dreamotion_smart_session"):
        await target.async_execute_controller_command(lambda ctrl: change(ctrl, kind))
    assert value(target, kind) == {"timer": 30, "mode": "inherent", "rgb": (9, 8, 7)}[kind]
    if kind == "timer":
        assert c._massage.duration == 3
    elif kind == "mode":
        assert c._massage.hz == 0x32
    else:
        assert c._timed == (app.Color(25, 9, 8, 7), 60)


async def test_save_single_frame_survives_cancel_after_its_settled_write(settings):
    target, c, client = settings
    entered, finish = asyncio.Event(), asyncio.Event()
    result = []
    proposed = (app.Color(50, 1, 2, 3), 60)

    async def write(*_args, **_kwargs):
        entered.set()
        await finish.wait()

    async def save(ctrl):
        with delivered(result.append):
            await ctrl._save_light(preview=False, timed=proposed)

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(target.async_execute_controller_command(save))
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert result == [Delivery.SENT]
    assert c._timed == proposed
    assert target.controller_state[UNDER_BED_LIGHTS_RGB] == (1, 2, 3)
    assert target.controller_state[bed.SECONDS] == 60
    assert len(client.write_gatt_char.await_args_list) == 1


async def test_native_mode_and_light_entities_preserve_translation_keys(hass, settings):
    from custom_components.adjustable_bed.light import _light_entities_for

    target, c, _client = settings
    mode = next(
        e
        for e in _select_entities_for(hass, target)
        if e.entity_description.key == "controller_select_dreamotion_smart_mode"
    )
    mode.async_write_ha_state = MagicMock()
    c._massage_known = False
    with raises_key("dreamotion_smart_refresh"):
        await mode.async_select_option("inherent")
    c._timed = None
    (light,) = _light_entities_for(hass, target)
    light.async_write_ha_state = MagicMock()
    with raises_key("dreamotion_smart_refresh"):
        await light.async_turn_on(rgb_color=(1, 2, 3), brightness=128)


@pytest.mark.parametrize("switch_at", ("write", "pause"))
async def test_light_save_preserves_newly_selected_page(settings, monkeypatch, switch_at):
    target, c, client = settings
    entered, finish = asyncio.Event(), asyncio.Event()

    async def write(_char, _packet, **_kwargs):
        if switch_at == "write" and client.write_gatt_char.await_count == 1:
            entered.set()
            await finish.wait()

    async def pause(_ms, cancel):
        if switch_at == "pause":
            entered.set()
            await finish.wait()
        return cancel.is_set()

    client.write_gatt_char.side_effect = write
    monkeypatch.setattr(c, "_pause", pause)
    task = asyncio.create_task(target.async_execute_controller_command(
        lambda ctrl: ctrl.set_light_color_with_level((1, 2, 3), 50)
    ))
    await entered.wait()
    c.set_page("presets")
    selected = value(target, "rgb")
    assert selected == (255, 0, 0)
    finish.set()
    await task
    assert c._timed == (app.Color(50, 1, 2, 3), 300)
    assert value(target, "rgb") == selected
    assert target.controller_state.get(LIGHT_LEVEL) == 100
