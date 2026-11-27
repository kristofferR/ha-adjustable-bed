"""Explicit duration edits outlive a BLE link, not its physical readbacks."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.jiecang import dreamotion_smart as bed
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.command_scheduler import (
    Delivery,
    current_command_context,
    delivered,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.profiles import dreamotion_smart as app
from custom_components.adjustable_bed.select import _select_entities_for
from custom_components.adjustable_bed.state_keys import LIGHT_LEVEL, UNDER_BED_LIGHTS_RGB
from scripts.wire_snapshot import FakeServices
from tests.error_helpers import raises_key
from tests.test_dreamotion_smart import LAYOUT
from tests.test_dreamotion_smart_delivery import settings as settings  # noqa: F401
from tests.test_dreamotion_smart_runtime import runtime as runtime  # noqa: F401


def select(hass, target, key):
    entity = next(e for e in _select_entities_for(hass, target)
                  if e.entity_description.key == "controller_select_dreamotion_smart_" + key)
    entity.async_write_ha_state = MagicMock()
    return entity


def button(target, preview):
    key = "dreamotion_smart_" + ("preview_light" if preview else "save_light")
    spec = next(s for s in target.controller.controller_button_specs if s.key == key)
    entity = ControllerActionButton(target, spec)
    entity.async_write_ha_state = MagicMock()
    return entity


@pytest.mark.parametrize("release", (False, True), ids=("idle", "release"))
@pytest.mark.parametrize("preview", (False, True), ids=("save", "preview"))
@pytest.mark.parametrize("page", ("timed", "presets"))
async def test_native_duration_disconnect_new_client_and_save(hass, settings, release, preview, page):
    target, c, old_client = settings
    target._disconnect_after_command = release
    duration = select(hass, target, "duration")
    await duration.async_select_option("60")
    assert c._timed[1] == 300  # A local edit is not receiver state.
    await select(hass, target, "page").async_select_option(page)
    assert target._idle_disconnect_delay() == (1 if release else 40)
    target._cancel_disconnect_timer()  # Fire the native timer path without a real wait.
    await target._async_idle_disconnect()
    assert target.controller is None and not old_client.is_connected
    assert c._timed is None and c._colors is None
    assert duration.current_option == "60"
    assert target.controller_state[UNDER_BED_LIGHTS_RGB] is None

    async def reconnect(**_kwargs):
        if target.client is not None:
            return True
        client = SimpleNamespace(is_connected=True, services=FakeServices(LAYOUT),
                                 write_gatt_char=AsyncMock(), start_notify=AsyncMock(),
                                 stop_notify=AsyncMock(), disconnect=AsyncMock())

        async def disconnect():
            client.is_connected = False

        client.disconnect.side_effect = disconnect
        target._client = client
        target._controller = await create_controller(
            target, const.BED_TYPE_DREAMOTION_SMART, "auto", client
        )
        fresh = target.controller

        async def pause(_ms, cancel):
            await asyncio.sleep(0)
            return cancel.is_set()

        fresh._pause = pause

        async def reply(_char, frame, **_kwargs):
            if frame == app.query(0x45):
                fresh._receive(bytes.fromhex("f2f24507a119090807012c"))
            elif frame == app.query(0x44):
                fresh._receive(bytes.fromhex("f2f2440da164ff00003200ff00190000ff"))

        client.write_gatt_char.side_effect = reply
        await fresh.async_discover_capabilities()
        await fresh.async_on_connect(SimpleNamespace(async_start_notify=fresh.start_notify))
        assert fresh._timed == (app.Color(25, 9, 8, 7), 300)
        assert fresh.protocol_diagnostics["duration_draft_seconds"] == 60
        assert duration.current_option == "60"
        client.write_gatt_char.reset_mock()
        return True

    target.async_ensure_connected.side_effect = reconnect
    await button_from_spec(c, target, preview).async_press()
    fresh, client = target.controller, target.client
    frames = [a.args[1] for a in client.write_gatt_char.await_args_list]
    if page == "presets":
        assert frames[0] == app.slots(fresh._colors)
        assert fresh.protocol_diagnostics["duration_draft_seconds"] == 60
        assert duration.current_option == "60"
        await select(hass, target, "page").async_select_option("timed")
        client.write_gatt_char.reset_mock()
        await button(target, preview).async_press()
        frames = [a.args[1] for a in client.write_gatt_char.await_args_list]
    assert frames == [app.timed(app.Color(25, 9, 8, 7), 60)] + (
        [app.setting(0x43, 1)] if preview else []
    )
    assert fresh.protocol_diagnostics["duration_draft_seconds"] is None
    assert fresh._timed == (app.Color(25, 9, 8, 7), 60)
    assert duration.current_option == "60"
    fresh._receive(bytes.fromhex("f2f24507a1190908070078"))
    assert duration.current_option == "120"  # The saved draft no longer masks reports.


def button_from_spec(controller, target, preview):
    # An already-created entity must follow the replacement controller via its callback.
    key = "dreamotion_smart_" + ("preview_light" if preview else "save_light")
    return ControllerActionButton(
        target, next(s for s in controller.controller_button_specs if s.key == key)
    )


async def test_disconnect_without_an_edit_does_not_keep_readbacks(settings):
    target, c, _ = settings
    await target.async_disconnect()
    assert c._timed is None
    assert target.controller_state[bed.SECONDS] is None
    assert target.controller_state[bed.DURATION] is None


@pytest.mark.parametrize("preview", (False, True))
async def test_failed_write_keeps_draft_but_not_physical_readbacks(hass, settings, preview):
    target, c, client = settings
    await select(hass, target, "duration").async_select_option("60")
    client.write_gatt_char.side_effect = BleakError("not submitted")
    with pytest.raises(BleakError):
        await target.async_execute_controller_command(lambda ctrl: ctrl._save_light(preview=preview))
    assert c.protocol_diagnostics["duration_draft_seconds"] == 60
    assert target.controller_state[bed.SECONDS] == 60
    assert c._timed is None and c._link is None and not client.is_connected


@pytest.mark.parametrize("preview", (False, True))
async def test_no_frame_keeps_exact_draft(hass, settings, preview):
    target, c, client = settings
    await select(hass, target, "duration").async_select_option("60")
    entered = asyncio.Event()

    async def save(ctrl):
        entered.set()
        await ctrl._save_light(preview=preview)

    async with c._ble_lock:
        task = asyncio.create_task(target.async_execute_controller_command(save))
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.write_gatt_char.await_count == 0
    assert c.protocol_diagnostics["duration_draft_seconds"] == 60
    assert target.controller_state[bed.DURATION] == "60"
    assert c._timed[1] == 300


async def test_partial_preview_retains_draft_and_requires_fresh_color(hass, settings):
    target, c, client = settings
    await select(hass, target, "duration").async_select_option("60")
    results = []

    async def interrupt(*_args, **_kwargs):
        current_command_context().cancel_event.set()

    async def preview(ctrl):
        with delivered(results.append):
            await ctrl._save_light(preview=True)

    client.write_gatt_char.side_effect = interrupt
    await target.async_execute_controller_command(preview)
    assert results == [Delivery.PARTIAL]
    assert c._timed is None and target.controller_state[UNDER_BED_LIGHTS_RGB] is None
    assert target.controller_state[bed.SECONDS] == 60
    assert c.protocol_diagnostics["duration_draft_seconds"] == 60
    with raises_key("dreamotion_smart_refresh"):
        await target.async_execute_controller_command(lambda ctrl: ctrl._save_light(preview=False))
    c._receive(bytes.fromhex("f2f24507a119090807012c"))
    client.write_gatt_char.reset_mock(side_effect=True)
    await button(target, False).async_press()
    assert client.write_gatt_char.await_args.args[1] == app.timed(app.Color(25, 9, 8, 7), 60)


@pytest.mark.parametrize("preview", (False, True))
@pytest.mark.parametrize("later", (60, 120))
@pytest.mark.parametrize("page", ("timed", "presets"))
async def test_inflight_save_owns_only_its_captured_edit(hass, settings, preview, later, page):
    target, c, client = settings
    await select(hass, target, "duration").async_select_option("60")
    entered, finish = asyncio.Event(), asyncio.Event()

    async def write(*_args, **_kwargs):
        if client.write_gatt_char.await_count == 1:
            entered.set()
            await finish.wait()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(button(target, preview).async_press())
    await entered.wait()
    await select(hass, target, "page").async_select_option(page)
    await c.set_duration(later)
    color = target.controller_state[UNDER_BED_LIGHTS_RGB]
    finish.set()
    await task
    assert c.protocol_diagnostics["duration_draft_seconds"] == later
    assert target.controller_state[bed.SECONDS] == later
    assert target.controller_state[bed.DURATION] == str(later)
    assert target.controller_state[UNDER_BED_LIGHTS_RGB] == color
    assert target.controller_state[LIGHT_LEVEL] == 100
    assert c._timed[1] == 60
    await select(hass, target, "page").async_select_option("timed")
    await button(target, False).async_press()
    assert client.write_gatt_char.await_args.args[1] == app.timed(c._timed[0], later)
    assert c.protocol_diagnostics["duration_draft_seconds"] is None


async def test_report_before_and_during_save_remains_separate_from_draft(hass, settings):
    target, c, client = settings
    await select(hass, target, "duration").async_select_option("60")
    c._receive(bytes.fromhex("f2f24507a119090807012c"))
    assert c._timed[1] == 300 and target.controller_state[bed.SECONDS] == 60

    async def report(*_args, **_kwargs):
        c._receive(bytes.fromhex("f2f24507a1190605040078"))

    client.write_gatt_char.side_effect = report
    await button(target, False).async_press()
    assert client.write_gatt_char.await_args.args[1] == app.timed(app.Color(25, 9, 8, 7), 60)
    assert c._timed == (app.Color(25, 6, 5, 4), 120)
    assert c.protocol_diagnostics["duration_draft_seconds"] is None
    assert target.controller_state[bed.SECONDS] == 120


@pytest.mark.parametrize("preview", (False, True))
async def test_consumed_duration_draft_reveals_newer_report_after_page_switch(hass, settings, preview):
    target, c, client = settings
    duration = select(hass, target, "duration")
    await duration.async_select_option("60")
    entered, finish = asyncio.Event(), asyncio.Event()

    async def write(*_args, **_kwargs):
        if client.write_gatt_char.await_count == 1:
            entered.set()
            await finish.wait()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(button(target, preview).async_press())
    await entered.wait()
    await select(hass, target, "page").async_select_option("presets")
    color = target.controller_state[UNDER_BED_LIGHTS_RGB]
    c._receive(bytes.fromhex("f2f24507a1190605040078"))
    assert duration.current_option == "60"
    finish.set()
    await task
    assert c.protocol_diagnostics["duration_draft_seconds"] is None
    assert c._timed[1] == 120
    assert duration.current_option == "120"
    assert target.controller_state[UNDER_BED_LIGHTS_RGB] == color
    assert target.controller_state[LIGHT_LEVEL] == 100


async def test_partial_preview_invalidates_duration_after_page_switch(hass, settings, monkeypatch):
    target, c, _ = settings
    entered = asyncio.Event()
    outcomes = []

    async def pause(_ms, cancel):
        entered.set()
        await asyncio.Event().wait()
        return cancel.is_set()

    monkeypatch.setattr(c, "_pause", pause)

    async def preview(ctrl):
        with delivered(outcomes.append):
            await ctrl._save_light(preview=True)

    task = asyncio.create_task(target.async_execute_controller_command(preview))
    await entered.wait()
    await select(hass, target, "page").async_select_option("presets")
    color = target.controller_state[UNDER_BED_LIGHTS_RGB]
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert outcomes == [Delivery.PARTIAL]
    assert c._timed is None
    assert target.controller_state[bed.SECONDS] is None
    assert select(hass, target, "duration").current_option is None
    assert target.controller_state[UNDER_BED_LIGHTS_RGB] == color
    assert target.controller_state[LIGHT_LEVEL] == 100


@pytest.mark.parametrize("preview", (False, True))
async def test_final_settled_write_consumes_only_saved_draft_even_on_task_cancel(hass, settings, preview):
    target, c, client = settings
    await select(hass, target, "duration").async_select_option("60")
    entered, finish = asyncio.Event(), asyncio.Event()

    async def write(*_args, **_kwargs):
        if client.write_gatt_char.await_count == (2 if preview else 1):
            entered.set()
            await finish.wait()

    client.write_gatt_char.side_effect = write
    task = asyncio.create_task(button(target, preview).async_press())
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert c.protocol_diagnostics["duration_draft_seconds"] is None
    assert c._timed[1] == 60
    assert target.controller_state[bed.SECONDS] == 60


@pytest.mark.parametrize("preview", (False, True))
async def test_expired_link_cannot_consume_draft_or_publish_over_new_session(hass, settings, preview):
    target, c, client = settings
    await select(hass, target, "duration").async_select_option("60")
    sender, old_callback = client.start_notify.await_args.args
    replacement = None

    async def replace_link(*_args, **_kwargs):
        nonlocal replacement
        c.on_disconnect()
        replacement = bed.DreamotionSmartController(target)
        target._controller = replacement
        await replacement.start_notify()
        replacement._receive(bytes.fromhex("f2f24507a119090807012c"))
        old_callback(sender, bytearray.fromhex("f2f24507a1190605040078"))

    client.write_gatt_char.side_effect = replace_link
    with raises_key("dreamotion_smart_session"):
        await button(target, preview).async_press()
    assert replacement is not None
    assert replacement._timed == (app.Color(25, 9, 8, 7), 300)
    assert replacement.protocol_diagnostics["duration_draft_seconds"] == 60
    assert target.controller_state[bed.SECONDS] == 60
    assert target.controller_state[UNDER_BED_LIGHTS_RGB] == (9, 8, 7)
