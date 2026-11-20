"""Explicit app discovery and selected-model capability admission."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.beds.sleep_assistant.controller import (
    SleepAssistantController,
)
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.profiles import sleep_assistant as app
from custom_components.adjustable_bed.runtime_data import entry_runtime
from custom_components.adjustable_bed.setup_questions import SETUP_PROFILES
from tests.hold_lease_wire import _tool, virtual_clock
from tests.test_controller_contract import _FactoryCoordinator
from tests.test_sleep_assistant_runtime import LAYOUT


@pytest.mark.parametrize(
    ("tokens", "hw", "expected"),
    [
        (("o2", "o5"), False, ("o5",)),
        (("o2", "o5"), True, ("o2", "o5")),
        (("o5",), True, ()),
        (("o2", "o3", "o4"), False, ("o2", "o3", "o4")),
        (("o1", "o2", "o3", "o4"), False, ("o1", "o2", "o3", "o4")),
        (("o5", "o1", "o2", "o3", "o4"), False, ("o5", "o1", "o2", "o3")),
        (("o1", "o2", "o3", "o5"), False, ("o2", "o3")),
    ],
)
def test_exact_preset_group_and_first_slot_quirk(tokens, hw, expected):
    assert app.visible_presets(tokens, hw) == expected


@pytest.mark.parametrize(
    ("controls", "actions"),
    [
        ({"m2"}, set()),
        ({"m1"}, {"massage_timer_cycle"}),
        ({"m1", "m2"}, {"massage_timer_cycle", "massage_all"}),
        ({"m3"}, set()),
        (
            {"m3", "m4"},
            {"massage_head_up", "massage_head_down", "massage_feet_up", "massage_feet_down"},
        ),
        ({"m5"}, {"massage_head_up"}),
        ({"m6"}, {"massage_feet_up"}),
    ],
)
def test_massage_layout_gates(controls, actions):
    c = SleepAssistantController(
        _FactoryCoordinator(), app.SleepAssistantProfile(controls=frozenset(controls))
    )
    assert {a for a in c.available_actions if a.startswith("massage_")} == actions


def test_setup_has_no_server_defaults_and_owns_each_physical_bed_settings():
    profile = SETUP_PROFILES["sleep_assistant"]
    side = per_side_profile("sleep_assistant", None)
    assert side is not None
    assert {q.key for q in profile.questions} <= side.keys
    selected = app.selected({const.CONF_BLE_DEVICE_NAME: "KSBT012345678"})
    assert (
        selected.identity is None and selected.calibration is None and selected.anti_snore is None
    )
    assert selected.presets == () and selected.controls == frozenset()
    assert profile.derive is not None and profile.validate is not None
    assert profile.derive({app.CONF_SLEEP_ASSISTANT_CONTROLS: ["m8"]})[const.CONF_MOTOR_COUNT] == 3
    for settings in ('{"token":"redacted"}', '{"gain":256}', '{"calibration":[1,2,3]}'):
        assert profile.validate({app.CONF_SLEEP_ASSISTANT_PARAMETERS: settings})


@pytest.mark.parametrize(
    "name", ["KSBT012345678", "ksbt012345678", "KSBTshort", "xKSBT012345678", "KSBT_DfuTarg"]
)
def test_exact_discovery_and_explicit_app_selection(name):
    info = SimpleNamespace(
        name=name,
        address="AA:BB:CC:DD:EE:FF",
        service_uuids=[],
        manufacturer_data={},
        service_data={},
    )
    result = detect_bed_type_detailed(info)
    offered = result.bed_type == "sleep_assistant" or "sleep_assistant" in (
        result.ambiguous_types or []
    )
    assert offered == (name == "KSBT012345678")
    if result.bed_type == "sleep_assistant":
        assert result.confidence < 0.7


async def test_manual_picker_reconfigure_and_real_native_entities(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, monkeypatch
):
    from custom_components.adjustable_bed.beds.sleep_assistant import controller as module
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from tests.form_helpers import finish_new_bed

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._app_after_device = "manual_entry"
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    await flow.async_step_select_app()
    await flow.async_step_select_app({const.CONF_BED_TYPE: "Sleep Assist"})
    result = await flow.async_step_manual_entry({"address": "AA:BB:CC:DD:EE:FF"})
    assert result["step_id"] == "finish_settings"
    answers = {
        app.CONF_SLEEP_ASSISTANT_PRESETS: ["o1", "o2", "o3", "o4"],
        app.CONF_SLEEP_ASSISTANT_CONTROLS: ["m1", "m2", "m3", "m4", "m7", "m8"],
        app.CONF_SLEEP_ASSISTANT_LIGHTING: "4193",
        app.CONF_SLEEP_ASSISTANT_IDENTITY: "",
        app.CONF_SLEEP_ASSISTANT_PARAMETERS: "",
        const.CONF_HAS_LIGHT: True,
    }
    result = await finish_new_bed(flow, result, answers)
    assert result["type"] == "create_entry"
    data = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Bedroom",
        const.CONF_BED_TYPE: "sleep_assistant",
        const.CONF_MOTOR_COUNT: 4,
        const.CONF_DISABLE_ANGLE_SENSING: True,
        **answers,
    }
    e = MockConfigEntry(
        domain=const.DOMAIN, title="Bedroom", unique_id=data[CONF_ADDRESS], data=data
    )
    e.add_to_hass(hass)
    mock_bleak_client.services = _tool().FakeServices(LAYOUT)

    async def no_wait(operation, event):
        operation.close()
        if event.is_set():
            raise asyncio.CancelledError

    monkeypatch.setattr(module, "cancellable", no_wait)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    runtime = entry_runtime(hass, e.entry_id)
    assert isinstance(runtime.controller, SleepAssistantController)
    registry = er.async_get(hass)
    entities = [v for v in registry.entities.values() if v.config_entry_id == e.entry_id]
    assert len([v for v in entities if v.domain == "cover"]) == 4
    assert any(v.domain == "light" for v in entities)
    assert any(
        v.domain == "switch" and v.translation_key == "sleep_assistant_storage" for v in entities
    )
    assert not any("program_memory" in v.unique_id for v in entities)
    with virtual_clock():
        button = next(
            v
            for v in entities
            if v.domain == "button" and v.unique_id.endswith("sleep_assistant_tv")
        )
        await hass.services.async_call(
            "button", "press", {"entity_id": button.entity_id}, blocking=True
        )
        assert any(
            call.args[1] == module.codec.instruction(16384)
            for call in mock_bleak_client.write_gatt_char.call_args_list
        )
    result = await hass.config_entries.flow.async_init(
        const.DOMAIN, context={"source": "reconfigure", "entry_id": e.entry_id}
    )
    assert result["type"] == "form"
    assert await hass.config_entries.async_unload(e.entry_id)


def test_standalone_scope_rejects_two_address_conversion():
    from custom_components.adjustable_bed.pairing import build_pair_entry_data

    data = {CONF_ADDRESS: "AA:BB:CC:DD:EE:01", const.CONF_BED_TYPE: "sleep_assistant"}
    with pytest.raises(ValueError, match="standalone"):
        build_pair_entry_data(data, {**data, CONF_ADDRESS: "AA:BB:CC:DD:EE:02"}, name="Bedroom")


async def test_late_version_hydrates_native_buttons_and_rgb_power_is_guarded(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, monkeypatch
):

    from custom_components.adjustable_bed.beds.sleep_assistant import controller as module

    async def no_wait(operation, event):
        operation.close()
        if event.is_set():
            raise asyncio.CancelledError

    monkeypatch.setattr(module, "cancellable", no_wait)
    data = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Bedroom",
        const.CONF_BED_TYPE: "sleep_assistant",
        const.CONF_DISABLE_ANGLE_SENSING: True,
        app.CONF_SLEEP_ASSISTANT_PRESETS: ["o2", "o5"],
        app.CONF_SLEEP_ASSISTANT_LIGHTING: "4193",
    }
    e = MockConfigEntry(
        domain=const.DOMAIN, title="Bedroom", unique_id=data[CONF_ADDRESS], data=data
    )
    e.add_to_hass(hass)
    mock_bleak_client.services = _tool().FakeServices(LAYOUT)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    runtime = entry_runtime(hass, e.entry_id)
    controller = runtime.controller
    assert isinstance(controller, SleepAssistantController)
    registry = er.async_get(hass)
    memory_id = f"{data[CONF_ADDRESS]}_sleep_assistant_memory"
    assert registry.async_get_entity_id("button", const.DOMAIN, memory_id) is None
    controller._receive(bytes.fromhex("8b0000021800000200020900"))
    await hass.async_block_till_done()
    memory = registry.async_get_entity_id("button", const.DOMAIN, memory_id)
    assert memory is not None
    assert hass.states.get(memory).state != "unavailable"
    controller._receive(bytes.fromhex("8b0000021700000200020400"))
    await hass.async_block_till_done()
    assert hass.states.get(memory).state == "unavailable"
    light = next(
        v
        for v in registry.entities.values()
        if v.config_entry_id == e.entry_id and v.domain == "light"
    )
    mock_bleak_client.write_gatt_char.reset_mock()
    with virtual_clock():
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                "light", "turn_on", {"entity_id": light.entity_id}, blocking=True
            )
        assert not mock_bleak_client.write_gatt_char.call_args_list
        controller._receive(bytes.fromhex("dd000000000000000000000000004002000000"))
        await hass.async_block_till_done()
        await hass.services.async_call(
            "light", "turn_on", {"entity_id": light.entity_id}, blocking=True
        )
        assert not mock_bleak_client.write_gatt_char.call_args_list
    assert await hass.config_entries.async_unload(e.entry_id)


@pytest.mark.parametrize(
    "failure",
    [
        "returned",
        "timeout",
        "subscription",
        "shutdown",
        "shutdown_race",
        "startup",
        "recovered_then_startup",
        "startup_oserror",
        "startup_second_cancel",
        "startup_early_cleanup_cancel",
    ],
)
async def test_real_failed_disconnect_restores_normal_command_and_polling(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    enable_custom_integrations,
    monkeypatch,
    failure,
):
    from custom_components.adjustable_bed.beds.sleep_assistant import controller as module

    async def no_wait(operation, event):
        operation.close()
        if event.is_set():
            raise asyncio.CancelledError

    monkeypatch.setattr(module, "cancellable", no_wait)
    data = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Bedroom",
        const.CONF_BED_TYPE: "sleep_assistant",
        const.CONF_DISABLE_ANGLE_SENSING: True,
        app.CONF_SLEEP_ASSISTANT_IDENTITY: "12345678",
    }
    e = MockConfigEntry(
        domain=const.DOMAIN, title="Bedroom", unique_id=data[CONF_ADDRESS], data=data
    )
    e.add_to_hass(hass)
    mock_bleak_client.services = _tool().FakeServices(LAYOUT)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    runtime = entry_runtime(hass, e.entry_id)
    assert isinstance(runtime.controller, SleepAssistantController)
    controller = runtime.controller
    calls = mock_bleak_client.start_notify.await_count
    cancel_startup = failure in {
        "startup",
        "recovered_then_startup",
        "startup_oserror",
        "startup_second_cancel",
        "startup_early_cleanup_cancel",
    }
    mock_bleak_client.disconnect = AsyncMock()  # Backend returns while the OS link remains live.
    if failure == "shutdown_race":
        entered, release = asyncio.Event(), asyncio.Event()

        async def blocked_subscription(*_args, **_kwargs):
            entered.set()
            await release.wait()

        mock_bleak_client.start_notify.side_effect = blocked_subscription
        controller.async_resume_session = AsyncMock()
        disconnect = asyncio.create_task(runtime.async_disconnect("idle_timeout"))
        await entered.wait()
        shutdown = asyncio.create_task(runtime.async_shutdown())
        await asyncio.sleep(0)
        release.set()
        assert not await disconnect
        await shutdown
        controller.async_resume_session.assert_not_awaited()
        assert runtime._diagnostic_poll_task is None
        mock_bleak_client.is_connected = False
        mock_bleak_client.write_gatt_char.reset_mock()
        assert not await runtime.async_ensure_connected()
        assert not await runtime.async_connect()
        mock_bleak_client.write_gatt_char.assert_not_awaited()
        assert await hass.config_entries.async_unload(e.entry_id)
        return
    if failure == "shutdown":
        controller.async_resume_session = AsyncMock()
        await runtime.async_shutdown()
        controller.async_resume_session.assert_not_awaited()
        assert runtime._diagnostic_poll_task is None
        assert not await runtime.async_ensure_connected()
        mock_bleak_client.is_connected = False
        assert await hass.config_entries.async_unload(e.entry_id)
        return
    if cancel_startup:
        # Release the fully initialized link, then cancel the next startup.
        if failure == "recovered_then_startup":
            mock_bleak_client.start_notify.side_effect = BleakError("subscription failed")
            assert not await runtime.async_disconnect("idle_timeout")
            mock_bleak_client.is_connected = False
            runtime._on_disconnect(mock_bleak_client)
            mock_bleak_client.start_notify.side_effect = None
        else:
            mock_bleak_client.is_connected = False
            assert await runtime.async_disconnect("idle_timeout")
        entered = asyncio.Event()
        original_startup = SleepAssistantController.async_on_connect

        async def interrupted_startup(self, session):
            entered.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(SleepAssistantController, "async_on_connect", interrupted_startup)
        reconnect = asyncio.create_task(runtime.async_connect())
        await entered.wait()
        cleanup_entered = asyncio.Event()
        original_hydration_cancel = runtime._async_cancel_position_hydration

        async def blocked_cleanup():
            cleanup_entered.set()
            await asyncio.Event().wait()

        if failure == "startup_oserror":
            mock_bleak_client.disconnect.side_effect = OSError("transport release failed")
        elif failure == "startup_second_cancel":
            mock_bleak_client.disconnect.side_effect = blocked_cleanup
        elif failure == "startup_early_cleanup_cancel":
            monkeypatch.setattr(runtime, "_async_cancel_position_hydration", blocked_cleanup)
        reconnect.cancel()
        if failure in ("startup_second_cancel", "startup_early_cleanup_cancel"):
            await cleanup_entered.wait()
            reconnect.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reconnect
        monkeypatch.setattr(runtime, "_async_cancel_position_hydration", original_hydration_cancel)
        mock_bleak_client.disconnect.side_effect = None
        assert runtime.is_connected and runtime.controller is None
        monkeypatch.setattr(SleepAssistantController, "async_on_connect", original_startup)
    if failure == "timeout":
        mock_bleak_client.disconnect.side_effect = TimeoutError("BlueZ disconnect timed out")
    if failure == "subscription":
        mock_bleak_client.start_notify.side_effect = [
            BleakError("notification subscription unavailable"),
            BleakError("notification subscription still unavailable"),
            None,
        ]
    if not cancel_startup:
        assert not await runtime.async_disconnect("idle_timeout")
        assert runtime.is_connected and runtime.controller is controller
        assert mock_bleak_client.start_notify.await_count > calls
        assert (runtime._diagnostic_poll_task is None) == (failure == "subscription")
    registry = er.async_get(hass)
    switch = next(
        v
        for v in registry.entities.values()
        if v.config_entry_id == e.entry_id
        and v.domain == "switch"
        and v.translation_key == "sleep_assistant_storage"
    )
    mock_bleak_client.write_gatt_char.reset_mock()
    if failure == "subscription" or cancel_startup:
        with pytest.raises(ConnectionError):
            await hass.services.async_call(
                "switch", "turn_on", {"entity_id": switch.entity_id}, blocking=True
            )
        mock_bleak_client.write_gatt_char.assert_not_awaited()
        assert runtime.is_connected and runtime._diagnostic_poll_task is None
    if cancel_startup:

        async def released_startup_link():
            mock_bleak_client.is_connected = False

        mock_bleak_client.disconnect.side_effect = released_startup_link
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": switch.entity_id}, blocking=True
    )
    assert runtime._diagnostic_poll_task is not None
    if cancel_startup:
        writes = [call.args[1] for call in mock_bleak_client.write_gatt_char.call_args_list]
        assert (
            writes.index(module.codec.serial_identity("12345678"))
            < writes.index(module.codec.storage_query())
            < writes.index(module.codec.storage(1))
        )
    assert any(
        call.args[1] == module.codec.storage(1)
        for call in mock_bleak_client.write_gatt_char.call_args_list
    )

    async def released():
        mock_bleak_client.is_connected = False

    mock_bleak_client.disconnect.side_effect = released
    assert await hass.config_entries.async_unload(e.entry_id)


async def test_native_firmware_preset_reconnects_then_revalidates_before_actuation(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, monkeypatch
):

    from custom_components.adjustable_bed.beds.sleep_assistant import controller as module

    async def no_wait(operation, event):
        operation.close()
        if event.is_set():
            raise asyncio.CancelledError

    monkeypatch.setattr(module, "cancellable", no_wait)
    firmware = [bytes.fromhex("8b0000021800000200020900")]

    async def subscribe(characteristic, callback, **_kwargs):
        callback(characteristic, bytearray(firmware[0]))

    mock_bleak_client.start_notify.side_effect = subscribe
    data = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
        CONF_NAME: "Bedroom",
        const.CONF_BED_TYPE: "sleep_assistant",
        const.CONF_DISABLE_ANGLE_SENSING: True,
        app.CONF_SLEEP_ASSISTANT_PRESETS: ["o2", "o5"],
    }
    e = MockConfigEntry(
        domain=const.DOMAIN, title="Bedroom", unique_id=data[CONF_ADDRESS], data=data
    )
    e.add_to_hass(hass)
    mock_bleak_client.services = _tool().FakeServices(LAYOUT)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    runtime = entry_runtime(hass, e.entry_id)
    registry = er.async_get(hass)
    memory = registry.async_get_entity_id(
        "button", const.DOMAIN, f"{data[CONF_ADDRESS]}_sleep_assistant_memory"
    )
    assert memory is not None
    for current, permitted in (
        (firmware[0], True),
        (bytes.fromhex("8b0000021700000200020400"), False),
    ):
        assert await runtime.async_disconnect("idle_timeout")
        await hass.async_block_till_done()
        assert hass.states.get(memory).state != "unavailable"
        firmware[0] = current
        mock_bleak_client.write_gatt_char.reset_mock()
        with virtual_clock():
            if permitted:
                await hass.services.async_call(
                    "button", "press", {"entity_id": memory}, blocking=True
                )
            else:
                with pytest.raises(HomeAssistantError):
                    await hass.services.async_call(
                        "button", "press", {"entity_id": memory}, blocking=True
                    )
        sent = any(
            call.args[1] == module.codec.instruction(65536)
            for call in mock_bleak_client.write_gatt_char.call_args_list
        )
        assert sent is permitted
    assert await hass.config_entries.async_unload(e.entry_id)
