"""Stable native controls and delivery after cancellation on the captured link."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from homeassistant.const import Platform
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.adjustable_bed.beds.thrivesleep.controller import ALARMS, LIGHT_SECONDS
from custom_components.adjustable_bed.command_scheduler import current_command_context
from custom_components.adjustable_bed.select import _select_entities_for
from custom_components.adjustable_bed.state_keys import MASSAGE_TIMER_MINUTES
from tests.test_entity_sweep import async_setup_platforms_and_sweep
from tests.test_thrivesleep import capabilities, notify
from tests.test_thrivesleep import clock as clock
from tests.test_thrivesleep_runtime import runtime as runtime
from tests.test_thrivesleep_runtime import written


async def test_light_timer_keeps_customized_registry_identity_across_disconnect_and_offline_setup(
    hass, runtime
):
    target, client = runtime
    assert await target.async_connect()
    capabilities(SimpleNamespace(client=client))
    created = await async_setup_platforms_and_sweep(hass, target.entry, target, (Platform.NUMBER,))
    timer = next(e for e in created if e.unique_id.endswith("thrivesleep_light_seconds"))
    await timer.async_set_native_value(100)
    registry = er.async_get(hass)
    row = registry.async_get_or_create(
        "number",
        "adjustable_bed",
        timer.unique_id,
        config_entry=target.entry,
        suggested_object_id="bed_light_duration",
    )
    row = registry.async_update_entity(
        row.entity_id,
        new_entity_id="number.my_bed_light_duration",
        name="My bed timer",
        icon="mdi:timer-sand",
    )
    identity = row.id
    assert timer.available and timer.native_value == 100

    await target.async_disconnect()
    await hass.async_block_till_done()
    assert timer.native_value is None and not timer.available
    assert registry.async_get(row.entity_id).id == identity
    assert registry.async_get(row.entity_id).name == "My bed timer"
    assert registry.async_get(row.entity_id).icon == "mdi:timer-sand"

    offline = await async_setup_platforms_and_sweep(hass, target.entry, target, (Platform.NUMBER,))
    offline_timer = next(e for e in offline if e.unique_id == timer.unique_id)
    assert not offline_timer.available and offline_timer.native_value is None
    assert registry.async_get(row.entity_id).id == identity
    assert await target.async_connect()
    assert not offline_timer.available  # A connection alone never grants light permission.
    capabilities(SimpleNamespace(client=client))
    await hass.async_block_till_done()
    assert offline_timer.available
    assert registry.async_get(row.entity_id).id == identity
    assert registry.async_get(row.entity_id).name == "My bed timer"
    assert registry.async_get(row.entity_id).icon == "mdi:timer-sand"
    await offline_timer.async_set_native_value(300)
    assert offline_timer.native_value == 300
    assert written(client)[-1] == "6e0b012ca6"


@pytest.mark.parametrize(
    "operation,frame",
    [("light", "6e0b012ca6"), ("delete", "6e2008050201019f"), ("massage", "6e010063d2")],
)
@pytest.mark.parametrize("cancel_kind", ("event", "task"))
async def test_successful_inflight_frame_updates_state_even_when_operation_is_cancelled(
    hass, runtime, operation, frame, cancel_kind
):
    target, client = runtime
    assert await target.async_connect()
    ctrl = target.controller
    capabilities(SimpleNamespace(client=client))
    await ctrl.light_timer(100)
    await ctrl.set_massage_timer(10)
    notify(SimpleNamespace(client=client), "6e200d0501020100071e45f907")
    entered, release = asyncio.Event(), asyncio.Event()
    operations, contexts = [], []

    async def write(*args, **kwargs):
        contexts.append(current_command_context())
        entered.set()
        await release.wait()

    async def apply(live):
        operations.append(asyncio.current_task())
        match operation:
            case "light":
                await live.light_timer(300)
            case "delete":
                await live.delete_alarm(1)
            case "massage":
                await live.set_massage_timer(20)

    client.write_gatt_char = AsyncMock(side_effect=write)
    task = asyncio.create_task(
        target.async_execute_controller_command(
            apply, resource="configuration", cancel_running=False
        )
    )
    await entered.wait()
    if cancel_kind == "task":
        operations[0].cancel()
    else:
        contexts[0].cancel_event.set()
    for _ in range(30):
        if operations[0].cancelling():
            break
        await asyncio.sleep(0)
    assert operations[0].cancelling()
    release.set()
    await task
    assert operations[0].cancelled()
    assert contexts[0].frames_written == 1
    assert written(client) == [frame]
    if operation == "light":
        assert target.controller_state[LIGHT_SECONDS] == 300
    elif operation == "delete":
        assert ctrl.alarms == [] and target.controller_state[ALARMS] == []
    else:
        assert target.controller_state[MASSAGE_TIMER_MINUTES] == 20


@pytest.mark.parametrize("operation", ("light", "delete", "massage"))
async def test_actual_cancel_while_queued_writes_nothing_and_preserves_observed_state(
    hass, runtime, operation
):
    target, client = runtime
    assert await target.async_connect()
    ctrl = target.controller
    capabilities(SimpleNamespace(client=client))
    await ctrl.light_timer(100)
    await ctrl.set_massage_timer(10)
    notify(SimpleNamespace(client=client), "6e200d0501020100071e45f907")
    operations, entered = [], asyncio.Event()

    async def apply(live):
        operations.append(asyncio.current_task())
        entered.set()
        if operation == "light":
            await live.light_timer(300)
        elif operation == "delete":
            await live.delete_alarm(1)
        else:
            await live.set_massage_timer(20)

    client.write_gatt_char.reset_mock()
    async with ctrl.ble_lock:
        task = asyncio.create_task(
            target.async_execute_controller_command(
                apply, resource="configuration", cancel_running=False
            )
        )
        await entered.wait()
        operations[0].cancel()
        for _ in range(30):
            if operations[0].done():
                break
            await asyncio.sleep(0)
        assert operations[0].cancelled()
    await task
    assert written(client) == []
    assert target.controller_state[LIGHT_SECONDS] == 100
    assert target.controller_state[MASSAGE_TIMER_MINUTES] == 10
    assert ctrl.alarms[0]["id"] == 1


@pytest.mark.parametrize("order", ("light_then_delete", "delete_then_light"))
async def test_failed_final_write_does_not_borrow_delivery_from_the_previous_step(
    hass, runtime, order
):
    target, client = runtime
    assert await target.async_connect()
    ctrl = target.controller
    capabilities(SimpleNamespace(client=client))
    await ctrl.light_timer(100)
    notify(SimpleNamespace(client=client), "6e200d0501020100071e45f907")
    client.write_gatt_char = AsyncMock(side_effect=[None, OSError("last write failed")])

    async def apply(live):
        if order == "light_then_delete":
            await live.light_timer(300)
            await live.delete_alarm(1)
        else:
            await live.delete_alarm(1)
            await live.light_timer(300)

    with pytest.raises(OSError, match="last write failed"):
        await target.async_execute_controller_command(
            apply, resource="configuration", cancel_running=False
        )
    if order == "light_then_delete":
        assert written(client) == ["6e0b012ca6", "6e2008050201019f"]
        assert target.controller_state[LIGHT_SECONDS] == 300
        assert ctrl.alarms[0]["id"] == 1
    else:
        assert written(client) == ["6e2008050201019f", "6e0b012ca6"]
        assert ctrl.alarms == []
        assert target.controller_state[LIGHT_SECONDS] == 100


@pytest.mark.parametrize("operation", ("light", "delete", "massage"))
async def test_settled_write_never_publishes_into_a_replacement_session(hass, runtime, operation):
    target, client = runtime
    assert await target.async_connect()
    ctrl = target.controller
    capabilities(SimpleNamespace(client=client))
    await ctrl.light_timer(100)
    await ctrl.set_massage_timer(10)
    notify(SimpleNamespace(client=client), "6e200d0501020100071e45f907")
    entered, release = asyncio.Event(), asyncio.Event()

    async def write(*args, **kwargs):
        entered.set()
        await release.wait()

    async def apply(live):
        if operation == "light":
            await live.light_timer(300)
        elif operation == "delete":
            await live.delete_alarm(1)
        else:
            await live.set_massage_timer(20)

    client.write_gatt_char = AsyncMock(side_effect=write)
    task = asyncio.create_task(
        target.async_execute_controller_command(
            apply, resource="configuration", cancel_running=False
        )
    )
    await entered.wait()
    ctrl.on_disconnect()
    # A replacement link already has fresh state; the old writer must leave it alone.
    ctrl.forward_controller_state_updates(LIGHT_SECONDS(42), MASSAGE_TIMER_MINUTES(30))
    notify_record = {"id": 1, "hour": 8}
    ctrl.alarms = [notify_record]
    release.set()
    with pytest.raises(ConnectionError, match="session has ended"):
        await task
    assert target.controller_state[LIGHT_SECONDS] == 42
    assert target.controller_state[MASSAGE_TIMER_MINUTES] == 30
    assert ctrl.alarms == [notify_record]


@pytest.mark.parametrize("runtime", ("level5", "eco_comfort", "cool_flow"), indirect=True)
async def test_native_massage_timer_select_has_verified_options_and_one_frame(hass, runtime):
    target, client = runtime
    assert await target.async_connect()
    ctrl = target.controller
    selectors = [
        e for e in _select_entities_for(hass, target) if e.entity_description.key == "massage_timer"
    ]
    assert not any("minute_timer" in spec.key for spec in ctrl.controller_button_specs)
    if ctrl.profile.key == "cool_flow":
        assert selectors == []
        return
    [timer] = selectors
    assert timer.options == ["10 min", "20 min", "30 min"]
    assert timer.current_option is None
    assert timer.capability_attributes["card_section"] == "massage"
    for option, expected in (
        ("10 min", "6e01005fce"),
        ("20 min", "6e010063d2"),
        ("30 min", "6e010061d0"),
    ):
        client.write_gatt_char.reset_mock()
        await timer.async_select_option(option)
        assert written(client) == [expected]
        assert timer.current_option == option
    with pytest.raises(ServiceValidationError):
        await timer.async_select_option("Off")
    # The app's held motor path still sends refreshes and its release separately.
    client.write_gatt_char.reset_mock()
    await target.async_execute_controller_command(lambda live: live.hold_control("head_up", 250))
    assert written(client) == ["6e01002493", "6e01002493", "6e01006edd"]
    ctrl.on_disconnect()
    assert timer.current_option is None


async def test_capability_preflight_uses_the_same_translated_rejection_as_dispatch(hass, runtime):
    target, client = runtime
    assert await target.async_connect()
    client.write_gatt_char.reset_mock()
    with pytest.raises(ServiceValidationError) as failure:
        await hass.services.async_call(
            "adjustable_bed",
            "thrivesleep",
            {"device_id": ["bed"], "operation": "light_rgb", "rgb_color": [1, 2, 3]},
            blocking=True,
        )
    assert failure.value.translation_domain == "adjustable_bed"
    assert failure.value.translation_key == "action_rejected"
    assert "confirmed its light capability" in str(failure.value)
    assert written(client) == []


@pytest.mark.parametrize("cancel_task", (False, True))
async def test_newer_alarm_report_survives_settled_delete(runtime, cancel_task):
    target, client = runtime
    assert await target.async_connect()
    ctrl = target.controller
    capabilities(SimpleNamespace(client=client))
    notify(SimpleNamespace(client=client), "6e200d0501020100071e45f907")
    entered, release = asyncio.Event(), asyncio.Event()
    operations = []

    async def write(*args, **kwargs):
        entered.set()
        await release.wait()

    async def operation(live):
        operations.append(asyncio.current_task())
        await live.delete_alarm(1)

    client.write_gatt_char = AsyncMock(side_effect=write)
    task = asyncio.create_task(target.async_execute_controller_command(
        operation, resource="configuration", cancel_running=False
    ))
    await entered.wait()
    notify(SimpleNamespace(client=client), "6e200d0501030100081e45f909")
    newer = [dict(row) for row in ctrl.alarms]
    assert newer[0]["hour"] == 8
    if cancel_task:
        operations[0].cancel()
        await asyncio.sleep(0)
    release.set()
    await task
    assert written(client) == ["6e2008050201019f"]
    assert ctrl.alarms == newer
    assert target.controller_state[ALARMS] == newer
