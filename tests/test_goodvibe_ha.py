"""Real HA coordinator ownership and service contracts for Good Vibe Sleep."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.goodvibe import GoodVibeController, Link
from custom_components.adjustable_bed.const import (
    BED_TYPE_GOODVIBE,
    CONF_BED_TYPE,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.goodvibe_protocol import action_frame


def runtime(hass, profile="sleep_hj", handoff=True, address="AA:BB:CC:DD:EE:16"):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "Good Vibe Sleep",
            CONF_BED_TYPE: BED_TYPE_GOODVIBE,
            CONF_PROTOCOL_VARIANT: profile,
            CONF_DISCONNECT_AFTER_COMMAND: handoff,
        },
    )
    entry.add_to_hass(hass)
    c = AdjustableBedCoordinator(hass, entry)
    c._offline_controller = GoodVibeController(c, profile=profile)
    c._controller = GoodVibeController(c, profile=profile)
    c._client = MagicMock()
    c._client.is_connected = True
    c._client.disconnect = AsyncMock()
    c._client.stop_notify = AsyncMock()
    tx = MagicMock(uuid="tx", properties=["write"], handle=1)
    rx = MagicMock(uuid="rx", properties=["notify"], handle=2)
    c._controller._link = Link(c._client, tx, rx, False)
    return c


async def test_unexpected_drop_retains_monitoring_intent_despite_handoff(hass):
    c = runtime(hass)
    obj = c._controller
    obj.choices.monitoring = True
    c._cache_persistent_connection_policy()
    assert not c._disconnect_after_operation_enabled()
    old = c._client
    old.is_connected = False
    c._on_disconnect(old)
    assert c._controller is None
    assert obj._link is None
    assert obj.choices.monitoring
    assert c._auto_reconnect_enabled()
    assert c._reconnect_timer is not None
    c._cancel_auto_reconnect()
    c._controller = GoodVibeController(c, profile="sleep_hj")
    assert c._controller.choices.monitoring
    await c.async_shutdown()
    assert not obj.choices.monitoring


async def test_recovery_failure_rearms_only_while_monitoring_intent_exists(hass):
    c = runtime(hass)
    c._controller.choices.monitoring = True
    c._client = None
    c._controller = None
    with patch.object(c, "async_connect", AsyncMock(return_value=False)):
        await c._async_auto_reconnect()
    assert c._reconnect_timer is not None
    await c.async_disconnect()
    assert c._reconnect_timer is None
    assert not c._offline_controller.choices.monitoring
    with patch.object(c, "async_connect", AsyncMock(return_value=False)):
        await c._async_auto_reconnect()
    assert c._reconnect_timer is None
    await c.async_shutdown()


async def test_manual_release_closes_resources_and_monitoring_without_recovery(hass):
    c = runtime(hass)
    obj, client = c._controller, c._client
    obj.choices.monitoring = True

    async def disconnect():
        client.is_connected = False
        c._on_disconnect(client)

    client.disconnect.side_effect = disconnect
    await c.async_disconnect()
    assert not obj.choices.monitoring
    assert obj._link is None
    assert c._reconnect_timer is None
    client.stop_notify.assert_awaited_once()
    await c.async_shutdown()


async def test_stop_uses_production_scheduler_and_clears_sleep_intent(hass):
    c = runtime(hass)
    obj = c._controller
    obj.choices.monitoring = True
    obj._sleep.last = "q_realtime"
    with (
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        await c.async_stop_command()
    assert not obj.choices.monitoring
    assert obj._sleep.last is None
    assert c._disconnect_after_operation_enabled()
    await c.async_shutdown()


async def test_background_writes_use_serialized_production_command_path(hass):
    c = runtime(hass)
    obj = c._controller
    c._client.mtu_size = 23
    c._client.write_gatt_char = AsyncMock()
    obj.choices.monitoring = True
    c.cancel_command.clear()
    with (
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):

        async def request(controller):
            assert controller is obj
            await controller.sleep_request("realtime")

        await c.async_execute_controller_command(
            request, cancel_running=False, read_positions_after_operation=False
        )
    assert c._client.write_gatt_char.await_count > 1
    assert obj._sleep.last == "q_realtime"
    assert c._disconnect_timer is None
    await c.async_shutdown()


async def test_release_entity_uses_stop_admission_without_an_extra_wire_stop(hass):
    from custom_components.adjustable_bed.beds.base import CONTROLLER_GESTURE_RELEASE
    from custom_components.adjustable_bed.button import ControllerActionButton
    from custom_components.adjustable_bed.goodvibe_catalog import ACTIONS

    c = runtime(hass, profile="selector-0001")
    obj = c._controller
    detail = next(d for d in obj.product.actions if ACTIONS[d].gesture == "sustainPress")
    first_sent = asyncio.Event()

    async def write(_char, _data, **_kwargs):
        first_sent.set()

    c._client.write_gatt_char = AsyncMock(side_effect=write)
    release = ControllerActionButton(
        c, next(s for s in obj.controller_button_specs if s.release_only)
    )
    with (
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):

        async def press(controller):
            await controller.press(detail, 60000)

        task = asyncio.create_task(
            c.async_execute_controller_command(press, read_positions_after_operation=False)
        )
        await first_sent.wait()
        await release.async_press()
        await task
    frames = [call.args[1] for call in c._client.write_gatt_char.await_args_list]
    assert frames == [action_frame(ACTIONS[detail], 0, False), bytes.fromhex("6e01006edd")]
    assert not CONTROLLER_GESTURE_RELEASE.get()
    c._client.is_connected = False
    await c.async_shutdown()


async def test_release_entity_invalidates_a_hold_still_in_connection_preflight(hass):
    from custom_components.adjustable_bed.button import ControllerActionButton
    from custom_components.adjustable_bed.goodvibe_catalog import ACTIONS

    c = runtime(hass, profile="selector-0001")
    obj = c._controller
    detail = next(d for d in obj.product.actions if ACTIONS[d].gesture == "sustainPress")
    entered = asyncio.Event()
    calls = 0
    gate = asyncio.get_running_loop().create_future()

    async def ensure(**_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await gate
        return True

    c._client.write_gatt_char = AsyncMock()
    release = ControllerActionButton(
        c, next(s for s in obj.controller_button_specs if s.release_only)
    )
    with (
        patch.object(c, "async_ensure_connected", ensure),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):

        async def press(controller):
            await controller.press(detail, 60000)

        task = asyncio.create_task(
            c.async_execute_controller_command(press, read_positions_after_operation=False)
        )
        await entered.wait()
        release_task = asyncio.create_task(release.async_press())
        await asyncio.sleep(0)
        gate.set_result(None)
        await release_task
        await task
    c._client.write_gatt_char.assert_not_awaited()
    c._client.is_connected = False
    await c.async_shutdown()


async def test_public_hold_service_released_during_preflight_cannot_start_later(hass):
    from custom_components.adjustable_bed import services
    from custom_components.adjustable_bed.button import ControllerActionButton
    from custom_components.adjustable_bed.goodvibe_catalog import ACTIONS

    c = runtime(hass, profile="selector-0001")
    obj = c._controller
    detail = next(d for d in obj.product.actions if ACTIONS[d].gesture == "sustainPress")
    entered = asyncio.Event()
    gate = asyncio.get_running_loop().create_future()

    async def validation(_owner, _target, _preflighted):
        entered.set()
        await gate
        return obj

    c._client.write_gatt_char = AsyncMock()
    release = ControllerActionButton(
        c, next(s for s in obj.controller_button_specs if s.release_only)
    )
    hass.services.async_register(DOMAIN, "hold_control", services.handle_hold_control)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(c, "both")], []),
        ),
        patch("custom_components.adjustable_bed.services._validation_controller", validation),
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        task = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "hold_control",
                {"device_id": ["bed"], "control": "goodvibe_" + detail, "duration": 1},
                blocking=True,
            )
        )
        await entered.wait()
        await release.async_press()
        gate.set_result(None)
        await task
    c._client.write_gatt_char.assert_not_awaited()
    c._client.is_connected = False
    await c.async_shutdown()


async def test_public_configuration_preflights_every_target_before_any_write(hass):
    import pytest
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed import goodvibe_services as service
    from custom_components.adjustable_bed.goodvibe_catalog import PRODUCTS

    light = next(k for k, v in PRODUCTS.items() if v.light)
    dark = next(k for k, v in PRODUCTS.items() if not v.light)
    a, b = runtime(hass, light), runtime(hass, dark)
    a._client.write_gatt_char = AsyncMock()
    b._client.write_gatt_char = AsyncMock()
    service.async_register_goodvibe_services(hass)
    with (
        patch.object(
            service, "_resolve_sided_targets", return_value=([(a, "both"), (b, "both")], [])
        ),
        pytest.raises(ServiceValidationError),
    ):
        await hass.services.async_call(
            DOMAIN,
            "goodvibe",
            {"device_id": ["a", "b"], "operation": "light_color", "rgb_color": [255, 0, 0]},
            blocking=True,
        )
    a._client.write_gatt_char.assert_not_awaited()
    b._client.write_gatt_char.assert_not_awaited()
    a._client.is_connected = b._client.is_connected = False
    await a.async_shutdown()
    await b.async_shutdown()


async def test_public_configuration_and_dynamic_entities_use_real_scheduler(hass):
    from custom_components.adjustable_bed import goodvibe_services as service
    from custom_components.adjustable_bed.goodvibe_catalog import PRODUCTS
    from custom_components.adjustable_bed.goodvibe_protocol import (
        SNORE_MENU_EXCLUDED_MODELS,
        light_duration,
        snore_config,
    )
    from custom_components.adjustable_bed.number import AdjustableBedControllerNumber
    from custom_components.adjustable_bed.select import AdjustableBedControllerSelect
    from custom_components.adjustable_bed.sensor import AdjustableBedControllerStateSensor

    key = next(
        k
        for k, v in PRODUCTS.items()
        if v.light
        and v.sleep != "deviceSleepMonitoringNone"
        and v.label not in SNORE_MENU_EXCLUDED_MODELS
    )
    c = runtime(hass, key)
    obj = c._controller
    c._client.write_gatt_char = AsyncMock()
    service.async_register_goodvibe_services(hass)
    paired = runtime(hass, next(k for k, v in PRODUCTS.items() if len(v.sides) > 1))
    side = AdjustableBedControllerSelect(
        paired,
        next(s for s in paired._controller.controller_select_specs if s.key == "goodvibe_side"),
    )
    await side.async_select_option("1")
    assert side.current_option == "1"
    paired._client.is_connected = False
    await paired.async_shutdown()
    c._client.write_gatt_char.assert_not_awaited()
    duration = AdjustableBedControllerSelect(
        c, next(s for s in obj.controller_select_specs if s.key == "goodvibe_light_duration")
    )
    count = AdjustableBedControllerNumber(
        c, next(s for s in obj.controller_number_specs if s.key == "goodvibe_snore_count")
    )
    status = AdjustableBedControllerStateSensor(c, obj.controller_state_sensor_specs[0])
    with (
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
        patch.object(service, "_resolve_sided_targets", return_value=([(c, "both")], [])),
    ):
        await duration.async_select_option("300")
        await count.async_set_native_value(17)
        await hass.services.async_call(
            DOMAIN,
            "goodvibe",
            {"device_id": ["bed"], "operation": "snore_count", "value": 18},
            blocking=True,
        )
    assert [x.args[1] for x in c._client.write_gatt_char.await_args_list] == [
        light_duration(300),
        snore_config(True, 17),
        snore_config(True, 18),
    ]
    obj._event("deviceAntiSnoreConfigCountEvent", 18)
    assert count.native_value == 18
    assert duration.current_option == "300"
    assert status.native_value == "deviceAntiSnoreConfigCountEvent"
    assert status.extra_state_attributes["goodvibe_events"]["deviceAntiSnoreConfigCountEvent"] == 18
    c._client.is_connected = False
    await c.async_shutdown()


async def test_monitoring_poll_write_failure_keeps_intent_and_retries(hass):
    from custom_components.adjustable_bed.beds import goodvibe as bed

    c = runtime(hass)
    obj = c._controller
    obj.choices.monitoring = True
    c._client.mtu_size = 512
    attempts = 0

    async def write(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConnectionError("poll failure")
        obj.choices.monitoring = False

    c._client.write_gatt_char = AsyncMock(side_effect=write)
    pause = asyncio.sleep

    async def fast(seconds):
        assert seconds == 2
        await pause(0)

    with (
        patch.object(bed.asyncio, "sleep", fast),
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        obj._start_polling()
        await obj._poll
    assert attempts == 2
    c._client.is_connected = False
    await c.async_shutdown()


async def test_sleep_sensor_localization_keys_preserve_identity_and_raw_state(hass):
    import json
    import re
    from contextlib import ExitStack
    from pathlib import Path

    from custom_components.adjustable_bed.sensor import AdjustableBedControllerStateSensor

    c = runtime(hass)
    obj = c._controller
    expected = {
        "goodvibe_L_heart": "61",
        "goodvibe_L_respiration": "12",
        "goodvibe_L_occupancy": "On Bed",
        "goodvibe_L_movement": "--",
        "goodvibe_L_snore": "Snoring",
        "goodvibe_R_heart": "72",
        "goodvibe_R_respiration": "18",
        "goodvibe_R_occupancy": "On Bed",
        "goodvibe_R_movement": "Body Move",
        "goodvibe_R_snore": "--",
    }
    specs = [s for s in obj.controller_state_sensor_specs if s.key != "goodvibe_status"]
    assert {s.key for s in specs} == set(expected)
    sensors = [AdjustableBedControllerStateSensor(c, spec) for spec in specs]
    for spec, sensor in zip(specs, sensors, strict=True):
        assert spec.state_key == spec.key
        assert sensor.unique_id == f"{c.address}_{spec.key}"
        assert sensor.translation_key == spec.translation_key == spec.key.lower()
        assert re.fullmatch(r"[a-z0-9]+(?:[a-z0-9_-]*[a-z0-9])?", spec.translation_key)
    integration = Path(__file__).parents[1] / "custom_components/adjustable_bed"
    for path in (integration / "strings.json", integration / "translations/en.json"):
        translated = json.loads(path.read_text())["entity"]["sensor"]
        assert all(spec.translation_key in translated for spec in specs)
        assert not set(expected).intersection(translated)
    with ExitStack() as stack:
        writes = [stack.enter_context(patch.object(s, "async_write_ha_state")) for s in sensors]
        for sensor in sensors:
            stack.callback(
                c.register_controller_state_callback(sensor._handle_controller_state_update)
            )
        obj.choices.realtime["L"].accept(3, [0, 1, 61, 12, 1])
        obj.choices.realtime["R"].accept(3, [0, -2, 72, 18, 0])
        obj._publish()
        assert {s._spec.state_key: s.native_value for s in sensors} == expected
        assert all(write.call_count == 1 for write in writes)
        assert all(key in c.controller_state for key in expected)
        assert not {key.lower() for key in expected}.intersection(c.controller_state)
    c._client.is_connected = False
    await c.async_shutdown()
