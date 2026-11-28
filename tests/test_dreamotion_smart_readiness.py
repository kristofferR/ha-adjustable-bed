"""Query completion precedes accepted settings notifications on real HA actions."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_homeassistant.common import MockEntityPlatform

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.jiecang import dreamotion_smart as bed
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.light import _light_entities_for
from custom_components.adjustable_bed.profiles import dreamotion_smart as app
from custom_components.adjustable_bed.select import (
    AdjustableBedMassageTimerSelect,
    _select_entities_for,
)
from custom_components.adjustable_bed.state_keys import LIGHT_LEVEL, UNDER_BED_LIGHTS_RGB
from scripts.wire_snapshot import FakeServices
from tests.error_helpers import raises_key
from tests.test_dreamotion_smart import LAYOUT
from tests.test_dreamotion_smart_runtime import runtime as runtime  # noqa: F401

TIMED = "f2f24507a119090807012c"
COLORS = "f2f2440da164ff00003200ff00190000ff"
GROUPS = (app.Color(100, 255, 0, 0), app.Color(50, 0, 255, 0), app.Color(25, 0, 0, 255))


def select(hass, target, key):
    entity = next(e for e in _select_entities_for(hass, target)
                  if e.entity_description.key == "controller_select_dreamotion_smart_" + key)
    entity.async_write_ha_state = MagicMock()
    return entity


def action(hass, target, kind):
    if kind == "duration":
        entity = select(hass, target, "duration")
        return lambda: entity.async_select_option("60")
    if kind == "slot":
        entity = select(hass, target, "slot")
        return lambda: entity.async_select_option("3")
    if kind.startswith("rgb"):
        (light,) = _light_entities_for(hass, target)
        light.async_write_ha_state = MagicMock()
        if kind == "rgb":
            return lambda: light.async_turn_on(rgb_color=(1, 2, 3))
        if kind == "rgb_with_level":
            return lambda: light.async_turn_on(rgb_color=(1, 2, 3), brightness=128)
        return lambda: light.async_turn_on(brightness=128)
    key = "dreamotion_smart_" + ("preview_light" if kind == "preview" else "save_light")
    entity = ControllerActionButton(
        target, next(s for s in target.controller.controller_button_specs if s.key == key)
    )
    return entity.async_press


async def install(target, monkeypatch, *, reuse=None) -> SimpleNamespace:
    client = reuse or SimpleNamespace(
        is_connected=True, services=FakeServices(LAYOUT), write_gatt_char=AsyncMock(),
        start_notify=AsyncMock(), stop_notify=AsyncMock(), disconnect=AsyncMock(),
    )
    client.is_connected = True

    async def disconnect():
        client.is_connected = False

    client.disconnect.side_effect = disconnect
    client.write_gatt_char.side_effect = None
    target._client = client
    target._controller = await create_controller(
        target, const.BED_TYPE_DREAMOTION_SMART, "auto", client
    )
    c = target.controller

    async def pause(_ms, cancel):
        await asyncio.sleep(0)
        return cancel.is_set()

    monkeypatch.setattr(c, "_pause", pause)
    await c.async_discover_capabilities()
    await c.async_on_connect(SimpleNamespace(async_start_notify=c.start_notify))
    sender, callback = client.start_notify.await_args.args
    assert c._timed is None and c._colors is None
    return SimpleNamespace(c=c, client=client, sender=sender, callback=callback)


async def pending(
    hass, target, monkeypatch, kind, page, release=False, *, invoke=None
) -> tuple[SimpleNamespace, asyncio.Task[None]]:
    c, old_client = target.controller, target.client
    for packet in (TIMED, COLORS, "f2f24302a101"):
        c._receive(bytes.fromhex(packet))
    await select(hass, target, "duration").async_select_option("60")
    await select(hass, target, "page").async_select_option(page)
    if invoke is None:
        invoke = action(hass, target, kind)  # Entity remains across replacement.
    target._disconnect_after_command = release
    target._cancel_disconnect_timer()
    await target._async_idle_disconnect()
    assert target.controller is None and c._timed is None and c._colors is None
    await target.async_prime_offline_controller()
    ready = asyncio.Event()
    current = None

    async def reconnect(**_kwargs):
        nonlocal current
        if target.client is None:
            current = await install(target, monkeypatch)
            ready.set()  # Every query write completed, but no callback ran.
        return True

    target.async_ensure_connected.side_effect = reconnect
    task = asyncio.create_task(invoke())
    task.add_done_callback(lambda _task: ready.set())
    await asyncio.wait_for(ready.wait(), 1)
    if current is None:
        await task
    await asyncio.sleep(0)
    assert current is not None and not task.done()
    assert current.client is not old_client
    return current, task


def notify(current, packet):
    current.callback(current.sender, bytearray.fromhex(packet))


def frames(current):
    return [a.args[1] for a in current.client.write_gatt_char.await_args_list]


def settings_frames(current):
    return [f for f in frames(current) if f[2] in (0x44, 0x45) and f[4] == 0xA1]


CASES = [("duration", "timed"), ("slot", "presets")] + [
    (kind, page) for kind in ("rgb", "rgb_with_level", "rgb_level", "save", "preview")
    for page in ("timed", "presets")
]


@pytest.mark.parametrize("kind,page", CASES)
@pytest.mark.parametrize("release", (False, True), ids=("idle", "release"))
async def test_first_native_action_waits_for_delayed_notification_after_queries(
    hass, runtime, monkeypatch, kind, page, release
):
    current, task = await pending(hass, runtime, monkeypatch, kind, page, release)
    timed = kind == "duration" or kind != "slot" and page == "timed"
    assert not settings_frames(current)
    # A power reply, malformed record and the other page's valid record cannot
    # turn a completed query into receipt of the record this action requires.
    notify(current, "f2f24302a101")
    notify(current, "f2f24507a100")
    notify(current, COLORS if timed else TIMED)
    await asyncio.sleep(0)
    assert not task.done() and not settings_frames(current)
    notify(current, TIMED if timed else COLORS)
    await task
    for op in (0x45, 0x44):
        assert frames(current).count(app.query(op)) == 1
    if kind == "duration":
        assert runtime.controller_state[bed.DURATION] == "60"
        assert not settings_frames(current)
    else:
        colors = list(GROUPS)
        color = app.Color(25, 9, 8, 7) if timed else GROUPS[0]
        if kind == "rgb":
            color = app.Color(color.brightness, 1, 2, 3)
        elif kind == "rgb_with_level":
            color = app.Color(51, 1, 2, 3)
        elif kind == "rgb_level":
            color = app.Color(51, color.red, color.green, color.blue)
        if not timed:
            colors[0] = color
        expected = app.timed(color, 60) if timed else app.slots(tuple(colors))
        assert settings_frames(current) == [expected]
        if kind == "slot":
            assert frames(current)[-1] == app.preview(GROUPS[2])
            assert current.c._slot == 3


@pytest.mark.parametrize("kind,page", [("duration", "timed"), ("slot", "presets"),
                                       ("save", "timed"), ("preview", "presets")])
async def test_missing_readback_has_bounded_translated_timeout(hass, runtime, monkeypatch, kind, page):
    monkeypatch.setattr(bed, "DEVICE_INFO_READ_TIMEOUT", 0.03)
    current, task = await pending(hass, runtime, monkeypatch, kind, page)
    with raises_key("dreamotion_smart_refresh"):
        await task
    assert not settings_frames(current)
    assert runtime.controller_state.get(bed._DURATION_DRAFT) == 60
    for op in (0x45, 0x44):
        assert frames(current).count(app.query(op)) == 1
    # A reply after timeout updates this session's readback, never resumes the action.
    notify(current, TIMED)
    notify(current, COLORS)
    await asyncio.sleep(0)
    assert not settings_frames(current)


@pytest.mark.parametrize("interrupt", ("task", "stop"))
@pytest.mark.parametrize("page", ("timed", "presets"))
async def test_cancelled_wait_does_not_resume_on_late_reply(hass, runtime, monkeypatch, interrupt, page):
    current, task = await pending(hass, runtime, monkeypatch, "preview", page)
    if interrupt == "task":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        await runtime.async_stop_command()
        await task
    notify(current, TIMED)
    notify(current, COLORS)
    await asyncio.sleep(0)
    assert not settings_frames(current)
    assert runtime.controller_state.get(bed._DURATION_DRAFT) == 60


@pytest.mark.parametrize("reuse", (False, True), ids=("new-client", "same-client-new-Link"))
async def test_old_callback_cannot_admit_replacement_session(hass, runtime, monkeypatch, reuse):
    old, task = await pending(hass, runtime, monkeypatch, "save", "timed")
    old.c.on_disconnect()  # Wakes this Link's waiter so it fails before a replacement can admit it.
    fresh = await install(runtime, monkeypatch, reuse=old.client if reuse else None)
    with raises_key("dreamotion_smart_session"):
        await task
    fresh.client.write_gatt_char.reset_mock()
    new_task = asyncio.create_task(action(hass, runtime, "save")())
    await asyncio.sleep(0)
    notify(old, TIMED)
    await asyncio.sleep(0)
    assert fresh.c._timed is None and not new_task.done() and not settings_frames(fresh)
    notify(fresh, TIMED)
    await new_task
    assert settings_frames(fresh) == [app.timed(app.Color(25, 9, 8, 7), 60)]


async def test_rgb_selection_change_during_wait_cannot_retarget_edit(hass, runtime, monkeypatch):
    current, task = await pending(hass, runtime, monkeypatch, "rgb", "timed")
    await select(hass, runtime, "page").async_select_option("presets")
    notify(current, COLORS)
    notify(current, TIMED)
    with raises_key("option_unavailable"):
        await task
    assert not settings_frames(current)
    assert runtime.controller_state[UNDER_BED_LIGHTS_RGB] == (255, 0, 0)
    assert runtime.controller_state[LIGHT_LEVEL] == 100


async def test_save_does_not_consume_edit_made_while_readiness_is_awaited(hass, runtime, monkeypatch):
    current, task = await pending(hass, runtime, monkeypatch, "save", "timed")
    # Both calls complete synchronously before Save's waiting task is resumed:
    # it must capture the draft revision before awaiting readiness, not after.
    notify(current, TIMED)
    await current.c.set_duration(120)
    await task
    assert settings_frames(current) == [app.timed(app.Color(25, 9, 8, 7), 60)]
    assert current.c.protocol_diagnostics["duration_draft_seconds"] == 120
    assert runtime.controller_state[bed.DURATION] == "120"


MODE = "f2f28002a132"
MASSAGE = "f2f28105a101020302"
REPORTED_MASSAGE = app.Massage(back=1, foot=2, pattern=3, duration=2, hz=0x32)


async def registered_massage_action(hass, target, kind):
    if kind in ("inherent", "acoustic", "timer"):
        choices = _select_entities_for(hass, target)
        entity = next(e for e in choices if (
            isinstance(e, AdjustableBedMassageTimerSelect) if kind == "timer" else
            e.entity_description.key == "controller_select_dreamotion_smart_mode"
        ))
        domain = "select"

        async def invoke():
            await entity.async_select_option("20 min" if kind == "timer" else kind)
    else:
        spec = next(s for s in target.controller.controller_button_specs
                    if s.key == "dreamotion_smart_" + kind)
        entity = ControllerActionButton(target, spec)
        domain = "button"
        invoke = entity.async_press
    platform = MockEntityPlatform(hass, domain=domain, platform_name=const.DOMAIN)
    await platform.async_add_entities([entity])
    assert hass.states.get(entity.entity_id) is not None
    return invoke


@pytest.fixture
def massage_native(hass, runtime, monkeypatch, enable_custom_integrations):
    async def start(kind, *, release=False):
        invoke = await registered_massage_action(hass, runtime, kind)
        current, task = await pending(
            hass, runtime, monkeypatch, kind, "timed", release, invoke=invoke
        )
        assert not current.c._massage_known and not current.c._mode_known
        return current, task, invoke

    return start


def massage_frames(current):
    return [f for f in frames(current) if f[2] in (0x80, 0x81) and f[4] == 0xA1]


def expected_massage_frames(kind):
    if kind == "inherent":
        return [app.setting(0x80, 0x32), app.Massage(pattern=3, duration=2).frame()]
    _, wire = REPORTED_MASSAGE.cycle("timer20" if kind == "timer" else kind)
    assert wire is not None
    return [wire.frame()]


@pytest.mark.parametrize("kind", ("back", "foot", "pattern", "timer", "inherent"))
@pytest.mark.parametrize("order", ((MODE, MASSAGE), (MASSAGE, MODE)))
async def test_registered_massage_actions_wait_for_their_delayed_records(massage_native, kind, order):
    current, task, _ = await massage_native(kind, release=order[0] == MASSAGE)
    assert not massage_frames(current)
    for packet in (TIMED, COLORS, "f2f28002a1", "f2f28105a101"):
        notify(current, packet)
    await asyncio.sleep(0)
    assert not task.done() and not massage_frames(current)
    notify(current, order[0])
    if kind != "inherent" or order[0] != MASSAGE:
        await asyncio.sleep(0)
        assert not task.done() and not massage_frames(current)
        notify(current, order[1])
    # Inherent needs the 81 record only, even if no 80 has ever arrived.
    await asyncio.wait_for(task, 1)
    assert massage_frames(current) == expected_massage_frames(kind)
    for op in (0x80, 0x81):
        assert frames(current).count(app.query(op)) == 1


@pytest.mark.parametrize("kind,received", [
    (kind, received) for kind in ("back", "timer") for received in (None, MODE, MASSAGE)
] + [("inherent", None), ("inherent", MODE)])
async def test_missing_massage_records_time_out_without_command_or_late_resume(
    massage_native, monkeypatch, kind, received
):
    monkeypatch.setattr(bed, "DEVICE_INFO_READ_TIMEOUT", 0.03)
    current, task, _ = await massage_native(kind)
    if received:
        notify(current, received)
    with raises_key("dreamotion_smart_refresh"):
        await task
    assert not massage_frames(current)
    notify(current, MODE)
    notify(current, MASSAGE)
    await asyncio.sleep(0)
    assert not massage_frames(current)
    for op in (0x80, 0x81):
        assert frames(current).count(app.query(op)) == 1


@pytest.mark.parametrize("kind", ("back", "timer", "inherent"))
@pytest.mark.parametrize("interrupt", ("task", "stop"))
async def test_cancelled_massage_admission_never_writes_after_late_report(
    massage_native, runtime, kind, interrupt
):
    current, task, _ = await massage_native(kind)
    if interrupt == "task":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        await runtime.async_stop_command()
        await task
    notify(current, MODE)
    notify(current, MASSAGE)
    await asyncio.sleep(0)
    assert not massage_frames(current)


@pytest.mark.parametrize("kind", ("back", "timer", "inherent"))
async def test_disconnected_massage_waiter_rejects_late_reports(massage_native, kind):
    old, task, _ = await massage_native(kind)
    old.c.on_disconnect()
    with raises_key("dreamotion_smart_session"):
        await task
    notify(old, MODE)
    notify(old, MASSAGE)
    assert not old.c._massage_known and not old.c._mode_known
    assert not massage_frames(old)


@pytest.mark.parametrize("kind", ("back", "timer", "inherent"))
@pytest.mark.parametrize("reuse", (False, True), ids=("new-client", "same-client-new-Link"))
async def test_old_massage_callback_cannot_admit_a_replacement(
    massage_native, runtime, monkeypatch, kind, reuse
):
    old, task, invoke = await massage_native(kind)
    old.c.on_disconnect()
    fresh = await install(runtime, monkeypatch, reuse=old.client if reuse else None)
    with raises_key("dreamotion_smart_session"):
        await task
    new_task = asyncio.create_task(invoke())
    await asyncio.sleep(0)
    notify(old, MODE)
    notify(old, MASSAGE)
    await asyncio.sleep(0)
    assert not fresh.c._massage_known and not fresh.c._mode_known
    assert not new_task.done() and not massage_frames(fresh)
    notify(fresh, MASSAGE)
    if kind != "inherent":
        notify(fresh, MODE)
    await asyncio.wait_for(new_task, 1)
    assert massage_frames(fresh) == expected_massage_frames(kind)


async def test_registered_acoustic_mode_needs_no_massage_reports(
    hass, runtime, monkeypatch, enable_custom_integrations
):
    current = await install(runtime, monkeypatch)
    invoke = await registered_massage_action(hass, runtime, "acoustic")
    await asyncio.wait_for(invoke(), 1)
    assert not current.c._massage_known
    assert massage_frames(current) == [app.setting(0x80, 0)]
