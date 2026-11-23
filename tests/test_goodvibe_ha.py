"""Real HA coordinator ownership and service contracts for Good Vibe Sleep."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.goodvibe.controller import GoodVibeController, Link
from custom_components.adjustable_bed.beds.goodvibe.protocol import action_frame
from custom_components.adjustable_bed.const import (
    BED_TYPE_GOODVIBE,
    CONF_BED_TYPE,
    CONF_CONNECTION_MODE,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator


def runtime(hass, profile="sleep_hj", handoff=True, address="AA:BB:CC:DD:EE:16"):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "Good Vibe Sleep",
            CONF_BED_TYPE: BED_TYPE_GOODVIBE,
            CONF_PROTOCOL_VARIANT: profile,
            CONF_CONNECTION_MODE: "release" if handoff else "idle",
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
    from custom_components.adjustable_bed.beds.goodvibe.catalog import ACTIONS
    from custom_components.adjustable_bed.button import ControllerActionButton

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
    from custom_components.adjustable_bed.beds.goodvibe.catalog import ACTIONS
    from custom_components.adjustable_bed.button import ControllerActionButton

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
    from custom_components.adjustable_bed.beds.goodvibe.catalog import ACTIONS
    from custom_components.adjustable_bed.button import ControllerActionButton

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

    from custom_components.adjustable_bed.beds.goodvibe import services as service
    from custom_components.adjustable_bed.beds.goodvibe.catalog import PRODUCTS

    light = next(k for k, v in PRODUCTS.items() if v.light)
    dark = next(k for k, v in PRODUCTS.items() if not v.light)
    a, b = runtime(hass, light), runtime(hass, dark)
    a._client.write_gatt_char = AsyncMock()
    b._client.write_gatt_char = AsyncMock()
    service.async_register_goodvibe_services(hass)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets", return_value=([(a, "both"), (b, "both")], [])
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
    from custom_components.adjustable_bed.beds.goodvibe import services as service
    from custom_components.adjustable_bed.beds.goodvibe.catalog import PRODUCTS
    from custom_components.adjustable_bed.beds.goodvibe.protocol import (
        SNORE_MENU_EXCLUDED_MODELS,
        light_duration,
        snore_config,
    )
    from custom_components.adjustable_bed.number import AdjustableBedControllerNumber
    from custom_components.adjustable_bed.select import (
        LIGHT_TIMER_DESCRIPTION,
        AdjustableBedControllerSelect,
        AdjustableBedControllerStateSelect,
    )
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
    duration = AdjustableBedControllerStateSelect(
        c,
        replace(LIGHT_TIMER_DESCRIPTION, available_fn=obj.light_timer_available_fn),
        obj.light_timer_options,
    )
    count = AdjustableBedControllerNumber(
        c, next(s for s in obj.controller_number_specs if s.key == "goodvibe_snore_count")
    )
    status = AdjustableBedControllerStateSensor(c, obj.controller_state_sensor_specs[0])
    with (
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
        patch("custom_components.adjustable_bed.services._resolve_sided_targets", return_value=([(c, "both")], [])),
    ):
        await duration.async_select_option("5 min")
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
    assert duration.current_option == "5 min"
    assert status.native_value == "deviceAntiSnoreConfigCountEvent"
    assert status.extra_state_attributes["goodvibe_events"]["deviceAntiSnoreConfigCountEvent"] == 18
    c._client.is_connected = False
    await c.async_shutdown()


async def test_monitoring_poll_write_failure_keeps_intent_and_retries(hass):
    from custom_components.adjustable_bed.beds.goodvibe import controller as bed

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


async def test_sleep_readings_are_typed_shared_entities(hass):
    from contextlib import ExitStack

    from homeassistant.components.binary_sensor import BinarySensorDeviceClass
    from homeassistant.components.sensor import SensorStateClass

    from custom_components.adjustable_bed.binary_sensor import (
        AdjustableBedControllerStateBinarySensor,
    )
    from custom_components.adjustable_bed.sensor import AdjustableBedControllerStateSensor

    c = runtime(hass)
    obj = c._controller
    rates = {
        "goodvibe_L_heart": ("heart_rate_left", 61),
        "goodvibe_L_respiration": ("breathing_rate_left", 12),
        "goodvibe_R_heart": ("heart_rate_right", 72),
        "goodvibe_R_respiration": ("breathing_rate_right", 18),
    }
    # The app's "--" is unknown, not a state string.
    flags = {
        "goodvibe_L_occupancy": ("bed_presence_left", True),
        "goodvibe_L_movement": ("body_movement_left", None),
        "goodvibe_L_snore": ("snoring_left", True),
        "goodvibe_R_occupancy": ("bed_presence_right", True),
        "goodvibe_R_movement": ("body_movement_right", True),
        "goodvibe_R_snore": ("snoring_right", None),
    }
    specs = [s for s in obj.controller_state_sensor_specs if s.key != "goodvibe_status"]
    binary_specs = list(obj.controller_state_binary_sensor_specs)
    assert {s.key: s.translation_key for s in specs} == {k: v[0] for k, v in rates.items()}
    assert {s.key: s.translation_key for s in binary_specs} == {
        k: v[0] for k, v in flags.items()
    }
    sensors = [AdjustableBedControllerStateSensor(c, spec) for spec in specs]
    binaries = [AdjustableBedControllerStateBinarySensor(c, spec) for spec in binary_specs]
    for entity in (*sensors, *binaries):
        assert entity.unique_id == f"{c.address}_{entity._spec.key}"
        assert entity.entity_category is None
        assert entity.entity_registry_enabled_default
    assert all(s.native_unit_of_measurement in ("bpm", "breaths/min") for s in sensors)
    assert all(s.state_class == SensorStateClass.MEASUREMENT for s in sensors)
    assert {b.device_class for b in binaries} == {
        BinarySensorDeviceClass.OCCUPANCY,
        BinarySensorDeviceClass.MOTION,
        BinarySensorDeviceClass.SOUND,
    }
    with ExitStack() as stack:
        for entity in (*sensors, *binaries):
            stack.enter_context(patch.object(entity, "async_write_ha_state"))
            stack.callback(
                c.register_controller_state_callback(entity._handle_controller_state_update)
            )
        obj.choices.realtime["L"].accept(3, [0, 1, 61, 12, 1])
        obj.choices.realtime["R"].accept(3, [0, -2, 72, 18, 0])
        obj._publish()
        assert {s._spec.key: s.native_value for s in sensors} == {
            k: v[1] for k, v in rates.items()
        }
        assert {b._spec.key: b.is_on for b in binaries} == {k: v[1] for k, v in flags.items()}
        obj.choices.realtime["L"].accept(3, [0, 0, 0, 0, 0])
        obj._publish()
        assert sensors[0].native_value is None
    c._client.is_connected = False
    await c.async_shutdown()
