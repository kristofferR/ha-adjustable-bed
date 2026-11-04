"""Public-path regressions from the independent Good Vibe Sleep review."""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed import goodvibe_services as configuration
from custom_components.adjustable_bed import services
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.command_scheduler import CommandOutcome
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.goodvibe_catalog import ACTIONS, PRODUCTS
from tests.test_goodvibe_ha import runtime


@pytest.mark.parametrize("release", (True, False))
async def test_early_public_card_release_runs_short_but_explicit_stop_aborts(hass, release):
    c = runtime(hass, "selector-0003")
    obj = c._controller
    detail = "38910fea480caabe"
    entered = asyncio.Event()

    async def delay(_milliseconds):
        entered.set()
        await c.cancel_command.wait()
        return False

    obj._delay = delay
    c._client.write_gatt_char = AsyncMock()
    button = ControllerActionButton(
        c, next(s for s in obj.controller_button_specs if s.release_only)
    )
    hass.services.async_register(DOMAIN, "hold_control", services.handle_hold_control)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(c, "both")], []),
        ),
        patch(
            "custom_components.adjustable_bed.services._validation_controller",
            AsyncMock(return_value=obj),
        ),
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        task = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "hold_control",
                {"device_id": ["bed"], "control": "goodvibe_" + detail, "duration": 60},
                blocking=True,
            )
        )
        await asyncio.wait_for(entered.wait(), 1)
        if release:
            await button.async_press()
        else:
            await c.async_stop_command()
        await asyncio.wait_for(task, 1)
    frames = [x.args[1] for x in c._client.write_gatt_char.await_args_list]
    assert frames == [bytes.fromhex("6e010046b5" if release else "6e01006edd")]
    c._client.is_connected = False
    await c.async_shutdown()


async def test_y6rm_menu_descendants_are_public_buttons_and_held_controls(hass):
    c = runtime(hass, "selector-0632")
    obj = c._controller
    expected = {
        "deviceFunctionItemHeadUp": (36, "sustainPress"),
        "deviceFunctionItemFootUp": (38, "sustainPress"),
        "deviceFunctionItemHeadDown": (37, "sustainPress"),
        "deviceFunctionItemFootDown": (39, "sustainPress"),
        "deviceFunctionItemMotorReset": (49, "shortPress"),
    }
    exposed = {
        ACTIONS[s.key.removeprefix("goodvibe_")].label: s
        for s in obj.controller_button_specs
        if s.key.removeprefix("goodvibe_") in ACTIONS
    }
    assert expected.keys() <= exposed.keys()
    c._client.write_gatt_char = AsyncMock()
    obj._delay = AsyncMock(return_value=True)
    with (
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        for name, (code, gesture) in expected.items():
            spec = exposed[name]
            assert spec.key in obj.held_control_options
            assert ACTIONS[spec.key.removeprefix("goodvibe_")].gesture == gesture
            await ControllerActionButton(c, spec).async_press()
            frames = [x.args[1] for x in c._client.write_gatt_char.await_args_list]
            assert frames[0] == bytes([110, 1, 0, code, (111 + code) & 255])
            assert frames[-1] == bytes.fromhex("6e01006edd")
            c._client.write_gatt_char.reset_mock()
    c._client.is_connected = False
    await c.async_shutdown()


async def test_repeat_allocation_full_later_target_prevents_every_write(hass):
    key = next(k for k, p in PRODUCTS.items() if p.alarms and p.repeat_alarm)
    a, b = runtime(hass, key), runtime(hass, key)
    # Independent process-local views for this two-physical-device call.
    from copy import deepcopy

    b._controller.choices = deepcopy(a._controller.choices)
    b._controller.choices.events["repeat_alarms"] = {str(n): [] for n in range(1, 8)}
    a._client.write_gatt_char = AsyncMock()
    b._client.write_gatt_char = AsyncMock()
    configuration.async_register_goodvibe_services(hass)
    with (
        patch.object(
            configuration, "_resolve_sided_targets", return_value=([(a, "both"), (b, "both")], [])
        ),
        patch.object(a, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(b, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(a, "_async_refresh_controller_auth", AsyncMock()),
        patch.object(b, "_async_refresh_controller_auth", AsyncMock()),
        pytest.raises(ServiceValidationError, match="occupied"),
    ):
        await hass.services.async_call(
            DOMAIN,
            "goodvibe",
            {
                "device_id": ["a", "b"],
                "operation": "repeat",
                "action": a._controller.product.alarms[0],
                "datetime": datetime(2026, 11, 4, 7, tzinfo=ZoneInfo("Europe/Oslo")),
            },
            blocking=True,
        )
    a._client.write_gatt_char.assert_not_awaited()
    b._client.write_gatt_char.assert_not_awaited()
    a._client.is_connected = b._client.is_connected = False
    await a.async_shutdown()
    await b.async_shutdown()


async def test_safety_stop_supersedes_deferred_short_while_wire_is_busy(hass):
    c = runtime(hass, "selector-0003")
    obj = c._controller
    detail = "38910fea480caabe"
    entered = asyncio.Event()
    released = asyncio.Event()

    async def delay(_milliseconds):
        entered.set()
        await c.cancel_command.wait()
        return False

    obj._delay = delay
    send = obj._send

    async def sending(data, **kwargs):
        if kwargs.get("release_gesture") is not None:
            released.set()
        return await send(data, **kwargs)

    obj._send = sending
    c._client.write_gatt_char = AsyncMock()
    button = ControllerActionButton(
        c, next(s for s in obj.controller_button_specs if s.release_only)
    )
    with (
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):

        async def hold(controller):
            await controller.hold_control("goodvibe_" + detail, 60000)

        task = asyncio.create_task(
            c.async_execute_controller_command(hold, read_positions_after_operation=False)
        )
        await asyncio.wait_for(entered.wait(), 1)
        await obj._ble_lock.acquire()
        release = asyncio.create_task(button.async_press())
        await asyncio.wait_for(released.wait(), 1)
        stop = asyncio.create_task(c.async_stop_command())
        await asyncio.sleep(0)
        assert c._command_scheduler.stop_epoch == 2
        obj._ble_lock.release()
        await asyncio.wait_for(asyncio.gather(task, release, stop), 1)
    assert [x.args[1] for x in c._client.write_gatt_char.await_args_list] == [
        bytes.fromhex("6e01006edd")
    ]
    c._client.is_connected = False
    await c.async_shutdown()


async def test_caller_cancellation_does_not_become_a_short_release(hass):
    c = runtime(hass, "selector-0003")
    obj = c._controller
    entered = asyncio.Event()

    async def delay(_milliseconds):
        entered.set()
        await c.cancel_command.wait()
        return False

    obj._delay = delay
    c._client.write_gatt_char = AsyncMock()
    with (
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):

        async def hold(controller):
            await controller.hold_control("goodvibe_38910fea480caabe", 60000)

        task = asyncio.create_task(
            c.async_execute_controller_command(hold, read_positions_after_operation=False)
        )
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await c._command_scheduler.async_shutdown()
    c._client.write_gatt_char.assert_not_awaited()
    c._client.is_connected = False
    await c.async_shutdown()


async def test_repeat_execution_keeps_each_targets_preflighted_slot(hass):
    key = next(k for k, p in PRODUCTS.items() if p.alarms and p.repeat_alarm)
    a, b = runtime(hass, key), runtime(hass, key, address="AA:BB:CC:DD:EE:17")
    a._controller.choices.events["repeat_alarms"] = {"1": []}

    async def first_write(*_args, **_kwargs):
        b._controller.choices.events["repeat_alarms"] = {str(n): [] for n in range(1, 8)}

    a._client.write_gatt_char = AsyncMock(side_effect=first_write)
    b._client.write_gatt_char = AsyncMock()
    configuration.async_register_goodvibe_services(hass)
    with (
        patch.object(
            configuration, "_resolve_sided_targets", return_value=([(a, "both"), (b, "both")], [])
        ),
        patch.object(a, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(b, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(a, "_async_refresh_controller_auth", AsyncMock()),
        patch.object(b, "_async_refresh_controller_auth", AsyncMock()),
    ):
        await hass.services.async_call(
            DOMAIN,
            "goodvibe",
            {
                "device_id": ["a", "b"],
                "operation": "repeat",
                "action": a._controller.product.alarms[0],
                "datetime": datetime(2026, 11, 4, 7, tzinfo=ZoneInfo("Europe/Oslo")),
            },
            blocking=True,
        )
    assert a._client.write_gatt_char.await_args.args[1][6] == 2
    assert b._client.write_gatt_char.await_args.args[1][6] == 1
    a._client.is_connected = b._client.is_connected = False
    await a.async_shutdown()
    await b.async_shutdown()


async def test_single_address_paired_card_release_keeps_its_short_callback_and_side(hass):
    from homeassistant.helpers import device_registry as dr
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed.const import (
        BED_TYPE_GOODVIBE,
        CONF_BED_TYPE,
        CONF_PAIR_ID,
    )
    from custom_components.adjustable_bed.paired_coordinator import (
        SingleAddressPairedCoordinator,
        entity_runtimes,
    )

    key, detail = next(
        (key, detail)
        for key, product in PRODUCTS.items()
        if 1 in product.sides
        for detail in product.actions
        if not ACTIONS[detail].local
        and ACTIONS[detail].gesture == "shortAndLongPress"
        and not ACTIONS[detail].force_long
    )
    c = runtime(hass, key)
    obj = c._controller
    pair = SingleAddressPairedCoordinator(
        hass,
        MockConfigEntry(
            domain=DOMAIN, data={CONF_PAIR_ID: "pair_goodvibe", CONF_BED_TYPE: BED_TYPE_GOODVIBE}
        ),
        c,
    )
    pair.entry.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=pair.entry.entry_id,
        identifiers=pair.device_info["identifiers"],
    )
    proxy = next(view for view in entity_runtimes(pair) if view.entity_side == "right")
    entered = asyncio.Event()

    async def delay(_milliseconds):
        entered.set()
        await c.cancel_command.wait()
        return False

    obj._delay = delay
    c._client.write_gatt_char = AsyncMock()
    button = ControllerActionButton(
        proxy, next(s for s in obj.controller_button_specs if s.release_only)
    )
    hass.services.async_register(DOMAIN, "hold_control", services.handle_hold_control)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(pair, "right")], []),
        ),
        patch(
            "custom_components.adjustable_bed.services._validation_controller",
            AsyncMock(return_value=proxy.capability_controller),
        ),
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        task = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "hold_control",
                {"device_id": ["right"], "control": "goodvibe_" + detail, "duration": 60},
                blocking=True,
            )
        )
        await asyncio.wait_for(entered.wait(), 1)
        await button.async_press()
        await asyncio.wait_for(task, 1)
    assert [x.args[1] for x in c._client.write_gatt_char.await_args_list] == [
        ACTIONS[detail].packet(1, False)
    ]
    c._client.write_gatt_char.reset_mock()
    with patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)):
        await proxy.async_stop_command()
    assert [x.args[1] for x in c._client.write_gatt_char.await_args_list] == [
        bytes.fromhex("6e01016ede")
    ]
    c._client.is_connected = False
    await pair.async_shutdown()


@pytest.mark.parametrize("native_both", (False, True))
async def test_combined_pair_uses_only_sides_admitted_by_the_product(hass, native_both):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed.const import (
        BED_TYPE_GOODVIBE,
        CONF_BED_TYPE,
        CONF_PAIR_ID,
        CONF_PROTOCOL_VARIANT,
    )
    from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator

    key, detail = next(
        (key, detail)
        for key, product in PRODUCTS.items()
        if 1 in product.sides and (2 in product.sides) == native_both
        for detail in product.actions
        if not ACTIONS[detail].local
        and ACTIONS[detail].gesture == "sustainPress"
        and not ACTIONS[detail].force_long
    )
    c = runtime(hass, key)
    obj = c._controller
    pair = SingleAddressPairedCoordinator(
        hass,
        MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_PAIR_ID: "pair_goodvibe_both",
                CONF_BED_TYPE: BED_TYPE_GOODVIBE,
                CONF_PROTOCOL_VARIANT: key,
            },
        ),
        c,
    )
    obj._delay = AsyncMock(return_value=True)
    c._client.write_gatt_char = AsyncMock()
    with (
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):

        async def hold(controller):
            await controller.hold_control("goodvibe_" + detail, 100)

        await pair.async_execute_controller_command(hold, side="both")
    sides = (2,) if native_both else (0, 1)
    expected = [
        frame
        for side in sides
        for frame in (
            ACTIONS[detail].packet(side, False),
            bytes([110, 1, side, 110, (221 + side) & 255]),
        )
    ]
    assert [x.args[1] for x in c._client.write_gatt_char.await_args_list] == expected
    c._client.write_gatt_char.reset_mock()
    with patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)):
        await pair.async_stop_command(side="both")
    assert [x.args[1] for x in c._client.write_gatt_char.await_args_list] == [
        bytes([110, 1, side, 110, (221 + side) & 255]) for side in sides
    ]
    c._client.is_connected = False
    await pair.async_shutdown()


async def test_public_safety_stop_then_pointer_release_does_not_revive_short(hass):
    c = runtime(hass, "selector-0003")
    obj = c._controller
    entered = asyncio.Event()

    async def delay(_milliseconds):
        entered.set()
        await c.cancel_command.wait()
        return False

    obj._delay = delay
    c._client.write_gatt_char = AsyncMock()
    button = ControllerActionButton(
        c, next(s for s in obj.controller_button_specs if s.release_only)
    )
    hass.services.async_register(DOMAIN, "hold_control", services.handle_hold_control)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(c, "both")], []),
        ),
        patch(
            "custom_components.adjustable_bed.services._validation_controller",
            AsyncMock(return_value=obj),
        ),
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        task = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "hold_control",
                {"device_id": ["bed"], "control": "goodvibe_38910fea480caabe", "duration": 60},
                blocking=True,
            )
        )
        await asyncio.wait_for(entered.wait(), 1)
        baseline = c._cancel_counter
        stop = asyncio.create_task(c.async_stop_command())
        await asyncio.sleep(0)
        assert c._cancel_counter == baseline + 1
        await button.async_press()
        await asyncio.wait_for(asyncio.gather(task, stop), 1)
    frames = [x.args[1].hex() for x in c._client.write_gatt_char.await_args_list]
    c._client.is_connected = False
    await c.async_shutdown()
    assert frames == ["6e01006edd"], frames


async def test_public_caller_abort_then_release_cannot_revive_short_during_cleanup(hass):
    c = runtime(hass, "selector-0003")
    obj = c._controller
    entered, cancelled, unwind = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def delay(_milliseconds):
        entered.set()
        try:
            await c.cancel_command.wait()
        finally:
            cancelled.set()
            while not unwind.is_set():
                try:
                    await unwind.wait()
                except asyncio.CancelledError:
                    # Keep cancellation cleanup in flight until pointer release.
                    pass
        return False

    obj._delay = delay
    c._client.write_gatt_char = AsyncMock()
    button = ControllerActionButton(
        c, next(s for s in obj.controller_button_specs if s.release_only)
    )
    hass.services.async_register(DOMAIN, "hold_control", services.handle_hold_control)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(c, "both")], []),
        ),
        patch(
            "custom_components.adjustable_bed.services._validation_controller",
            AsyncMock(return_value=obj),
        ),
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        task = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "hold_control",
                {"device_id": ["bed"], "control": "goodvibe_38910fea480caabe", "duration": 60},
                blocking=True,
            )
        )
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        await asyncio.wait_for(cancelled.wait(), 1)
        assert obj._gesture is not None
        release = asyncio.create_task(button.async_press())
        await asyncio.sleep(0)
        unwind.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        await asyncio.wait_for(release, 1)
    c._client.write_gatt_char.assert_not_awaited()
    c._client.is_connected = False
    await c.async_shutdown()


async def test_other_side_button_does_not_revoke_active_right_release(hass):
    from homeassistant.helpers import device_registry as dr
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed.const import (
        BED_TYPE_GOODVIBE,
        CONF_BED_TYPE,
        CONF_PAIR_ID,
    )
    from custom_components.adjustable_bed.paired_coordinator import (
        SingleAddressPairedCoordinator,
        entity_runtimes,
    )

    key, detail = next(
        (key, detail)
        for key, product in PRODUCTS.items()
        if 1 in product.sides
        for detail in product.actions
        if not ACTIONS[detail].local
        and ACTIONS[detail].gesture == "shortAndLongPress"
        and not ACTIONS[detail].force_long
    )
    c = runtime(hass, key)
    obj = c._controller
    pair = SingleAddressPairedCoordinator(
        hass,
        MockConfigEntry(
            domain=DOMAIN, data={CONF_PAIR_ID: "pair_goodvibe", CONF_BED_TYPE: BED_TYPE_GOODVIBE}
        ),
        c,
    )
    pair.entry.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=pair.entry.entry_id,
        identifiers=pair.device_info["identifiers"],
    )
    proxy = next(view for view in entity_runtimes(pair) if view.entity_side == "right")
    entered = asyncio.Event()

    async def delay(milliseconds):
        if milliseconds != 3000:
            return True
        entered.set()
        await c.cancel_command.wait()
        return False

    obj._delay = delay
    c._client.write_gatt_char = AsyncMock()
    button = ControllerActionButton(
        proxy, next(s for s in obj.controller_button_specs if s.release_only)
    )
    hass.services.async_register(DOMAIN, "hold_control", services.handle_hold_control)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(pair, "right")], []),
        ),
        patch(
            "custom_components.adjustable_bed.services._validation_controller",
            AsyncMock(return_value=proxy.capability_controller),
        ),
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        task = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "hold_control",
                {"device_id": ["right"], "control": "goodvibe_" + detail, "duration": 60},
                blocking=True,
            )
        )
        await asyncio.wait_for(entered.wait(), 1)
        # An independent left action reserves only side:left:* on the same
        # physical scheduler. Its admission must leave the right hold active.
        opposite = next(view for view in entity_runtimes(pair) if view.entity_side == "left")
        other_button = ControllerActionButton(
            opposite, next(s for s in obj.controller_button_specs if s.key == "goodvibe_" + detail)
        )
        enqueued = asyncio.Event()
        enqueue = c._command_scheduler.enqueue

        async def admitted(*args, **kwargs):
            handle = await enqueue(*args, **kwargs)
            enqueued.set()
            return handle

        baseline = c._cancel_counter
        with patch.object(c._command_scheduler, "enqueue", side_effect=admitted):
            other = asyncio.create_task(other_button.async_press())
            await asyncio.wait_for(enqueued.wait(), 1)
            assert c._cancel_counter == baseline + 1
            assert not c._command_scheduler._active.context.cancel_event.is_set()
            assert not obj._gesture.cancel_event.is_set()
            assert not obj._gesture.owner.cancelling()
            await button.async_press()
            await asyncio.wait_for(asyncio.gather(task, other), 1)
    frames = [x.args[1] for x in c._client.write_gatt_char.await_args_list]
    expected = [ACTIONS[detail].packet(1, False), ACTIONS[detail].packet(0, False)]
    c._client.is_connected = False
    await pair.async_shutdown()
    assert frames == expected


async def test_public_release_and_other_side_button_concurrently(hass):
    from homeassistant.helpers import device_registry as dr
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed.const import (
        BED_TYPE_GOODVIBE,
        CONF_BED_TYPE,
        CONF_PAIR_ID,
    )
    from custom_components.adjustable_bed.paired_coordinator import (
        SingleAddressPairedCoordinator,
        entity_runtimes,
    )

    key, detail = next(
        (key, detail)
        for key, product in PRODUCTS.items()
        if 1 in product.sides
        for detail in product.actions
        if not ACTIONS[detail].local
        and ACTIONS[detail].gesture == "shortAndLongPress"
        and not ACTIONS[detail].force_long
    )
    c = runtime(hass, key)
    obj = c._controller
    pair = SingleAddressPairedCoordinator(
        hass,
        MockConfigEntry(
            domain=DOMAIN, data={CONF_PAIR_ID: "pair_goodvibe", CONF_BED_TYPE: BED_TYPE_GOODVIBE}
        ),
        c,
    )
    pair.entry.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=pair.entry.entry_id,
        identifiers=pair.device_info["identifiers"],
    )
    proxy = next(view for view in entity_runtimes(pair) if view.entity_side == "right")
    entered = asyncio.Event()

    original_delay = obj._delay

    async def delay(milliseconds):
        if milliseconds != 3000:
            return True
        entered.set()
        return await original_delay(milliseconds)

    obj._delay = delay
    c._client.write_gatt_char = AsyncMock()
    button = ControllerActionButton(
        proxy, next(s for s in obj.controller_button_specs if s.release_only)
    )
    hass.services.async_register(DOMAIN, "hold_control", services.handle_hold_control)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(pair, "right")], []),
        ),
        patch(
            "custom_components.adjustable_bed.services._validation_controller",
            AsyncMock(return_value=proxy.capability_controller),
        ),
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        task = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "hold_control",
                {"device_id": ["right"], "control": "goodvibe_" + detail, "duration": 60},
                blocking=True,
            )
        )
        await asyncio.wait_for(entered.wait(), 1)
        # An independent left action reserves only side:left:* on the same
        # physical scheduler. Its admission must leave the right hold active.
        opposite = next(view for view in entity_runtimes(pair) if view.entity_side == "left")
        other_button = ControllerActionButton(
            opposite, next(s for s in obj.controller_button_specs if s.key == "goodvibe_" + detail)
        )
        # Queue two real public button calls in the same event-loop turn.
        # No BLE-lock barrier, _send patch, scheduler patch or counter mutation.
        release = asyncio.create_task(button.async_press())
        other = asyncio.create_task(other_button.async_press())
        await asyncio.wait_for(asyncio.gather(task, release, other), 3)
    frames = [x.args[1] for x in c._client.write_gatt_char.await_args_list]
    expected = [ACTIONS[detail].packet(1, False), ACTIONS[detail].packet(0, False)]
    c._client.is_connected = False
    await pair.async_shutdown()
    assert frames == expected


async def test_other_side_button_after_release_waits_for_short_wire(hass):
    from homeassistant.helpers import device_registry as dr
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed.const import (
        BED_TYPE_GOODVIBE,
        CONF_BED_TYPE,
        CONF_PAIR_ID,
    )
    from custom_components.adjustable_bed.paired_coordinator import (
        SingleAddressPairedCoordinator,
        entity_runtimes,
    )

    key, detail = next(
        (key, detail)
        for key, product in PRODUCTS.items()
        if 1 in product.sides
        for detail in product.actions
        if not ACTIONS[detail].local
        and ACTIONS[detail].gesture == "shortAndLongPress"
        and not ACTIONS[detail].force_long
    )
    c = runtime(hass, key)
    obj = c._controller
    pair = SingleAddressPairedCoordinator(
        hass,
        MockConfigEntry(
            domain=DOMAIN, data={CONF_PAIR_ID: "pair_goodvibe", CONF_BED_TYPE: BED_TYPE_GOODVIBE}
        ),
        c,
    )
    pair.entry.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=pair.entry.entry_id,
        identifiers=pair.device_info["identifiers"],
    )
    proxy = next(view for view in entity_runtimes(pair) if view.entity_side == "right")
    entered = asyncio.Event()

    async def delay(milliseconds):
        if milliseconds != 3000:
            return True
        entered.set()
        await c.cancel_command.wait()
        return False

    obj._delay = delay
    c._client.write_gatt_char = AsyncMock()
    short_wire_waiting = asyncio.Event()
    send = obj._send

    async def sending(data, **kwargs):
        if kwargs.get("release_gesture") is not None:
            short_wire_waiting.set()
        return await send(data, **kwargs)

    obj._send = sending
    button = ControllerActionButton(
        proxy, next(s for s in obj.controller_button_specs if s.release_only)
    )
    hass.services.async_register(DOMAIN, "hold_control", services.handle_hold_control)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(pair, "right")], []),
        ),
        patch(
            "custom_components.adjustable_bed.services._validation_controller",
            AsyncMock(return_value=proxy.capability_controller),
        ),
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        task = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "hold_control",
                {"device_id": ["right"], "control": "goodvibe_" + detail, "duration": 60},
                blocking=True,
            )
        )
        await asyncio.wait_for(entered.wait(), 1)
        # An independent left action reserves only side:left:* on the same
        # physical scheduler. Its admission must leave the right hold active.
        opposite = next(view for view in entity_runtimes(pair) if view.entity_side == "left")
        other_button = ControllerActionButton(
            opposite, next(s for s in obj.controller_button_specs if s.key == "goodvibe_" + detail)
        )
        enqueued = asyncio.Event()
        enqueue = c._command_scheduler.enqueue

        async def admitted(*args, **kwargs):
            handle = await enqueue(*args, **kwargs)
            enqueued.set()
            return handle

        await obj._ble_lock.acquire()
        release = asyncio.create_task(button.async_press())
        await asyncio.wait_for(short_wire_waiting.wait(), 1)
        baseline = c._cancel_counter
        release_generation = obj._gesture.release_generation
        with patch.object(c._command_scheduler, "enqueue", side_effect=admitted):
            other = asyncio.create_task(other_button.async_press())
            await asyncio.wait_for(enqueued.wait(), 1)
            assert c._cancel_counter == baseline + 1
            assert c._command_scheduler._active.context.cancel_event.is_set()
            assert obj._gesture.release_generation == release_generation
            assert c._command_scheduler._queue[-1].intent.resources == frozenset({"side:left:*"})
            obj._ble_lock.release()
            await asyncio.wait_for(asyncio.gather(task, release, other), 1)
    frames = [x.args[1] for x in c._client.write_gatt_char.await_args_list]
    expected = [ACTIONS[detail].packet(1, False), ACTIONS[detail].packet(0, False)]
    c._client.is_connected = False
    await pair.async_shutdown()
    assert frames == expected


async def test_public_release_then_caller_abort_before_short_wire(hass):
    c = runtime(hass, "selector-0003")
    obj = c._controller
    entered, wire_entered, abort_seen = asyncio.Event(), asyncio.Event(), asyncio.Event()

    original_delay = obj._delay

    async def delay(milliseconds):
        entered.set()
        return await original_delay(milliseconds)

    obj._delay = delay
    send = obj._send

    async def sending(data, **kwargs):
        if kwargs.get("release_gesture") is not None:
            wire_entered.set()
        return await send(data, **kwargs)

    obj._send = sending
    cancel = c._command_scheduler.cancel

    async def cancelling(handle, outcome=CommandOutcome.GROUP_ABORTED):
        if outcome is CommandOutcome.CALLER_CANCELLED:
            abort_seen.set()
        return await cancel(handle, outcome)

    c._command_scheduler.cancel = cancelling
    c._client.write_gatt_char = AsyncMock()
    button = ControllerActionButton(
        c, next(s for s in obj.controller_button_specs if s.release_only)
    )
    hass.services.async_register(DOMAIN, "hold_control", services.handle_hold_control)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(c, "both")], []),
        ),
        patch(
            "custom_components.adjustable_bed.services._validation_controller",
            AsyncMock(return_value=obj),
        ),
        patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)),
        patch.object(c, "_async_refresh_controller_auth", AsyncMock()),
    ):
        task = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "hold_control",
                {
                    "device_id": ["bed"],
                    "control": "goodvibe_38910fea480caabe",
                    "duration": 60,
                },
                blocking=True,
            )
        )
        await asyncio.wait_for(entered.wait(), 1)
        await obj._ble_lock.acquire()
        release = asyncio.create_task(button.async_press())
        await asyncio.wait_for(wire_entered.wait(), 1)
        task.cancel()
        await asyncio.wait_for(abort_seen.wait(), 1)
        assert c._command_scheduler._active.context.cancel_reason is CommandOutcome.CALLER_CANCELLED
        obj._ble_lock.release()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 1)
        await asyncio.wait_for(release, 1)
    frames = [x.args[1].hex() for x in c._client.write_gatt_char.await_args_list]
    c._client.is_connected = False
    await c.async_shutdown()
    assert frames == [], frames
