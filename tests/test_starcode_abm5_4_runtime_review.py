"""Classification admission, native light state and deferred capability rebuilds."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.starcode_abm5_4_profiles import MANUFACTURER_UUID
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from tests.test_starcode_abm5_4 import make_controller
from tests.test_starcode_abm5_4_public_presets import literal_frame


@pytest.mark.parametrize("result", [b"star", None])
async def test_UART_readiness_waits_for_optional_classification_or_its_proved_absence(result):
    controller = make_controller("BOX15", ui="BOX15")
    entered, release = asyncio.Event(), asyncio.Event()

    async def read(_role):
        entered.set()
        await release.wait()
        if result is None:
            raise OSError("optional manufacturer unavailable")
        return result

    controller.client.read_gatt_char.side_effect = read
    task = asyncio.create_task(controller.start_notify())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert not task.done() and not controller._ready
        assert controller.command_selector == "BOX15"
        release.set()
        await asyncio.wait_for(task, 2)
        assert controller._ready and controller._classification_complete
        assert controller.command_selector == ("BOX25_STAR" if result is not None else "BOX15")
        assert controller.ui_selector == "BOX15"
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await controller.stop_notify()
    assert not controller._tasks


@pytest.mark.parametrize("transition", ["cancel", "stop", "client", "address"])
async def test_pending_classification_cannot_admit_cancelled_or_replaced_startup(transition):
    controller = make_controller("BOX15")
    client = controller.client
    entered, release = asyncio.Event(), asyncio.Event()

    async def read(_role):
        entered.set()
        await release.wait()
        return b"star"

    client.read_gatt_char.side_effect = read
    task = asyncio.create_task(controller.start_notify())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert not controller._ready
        if transition == "cancel":
            task.cancel()
        elif transition == "stop":
            await controller.stop_notify()
        elif transition == "client":
            controller._coordinator.client = make_controller().client
        else:
            controller._coordinator.address = "AA:BB:CC:DD:EE:00"
        release.set()
        expected = asyncio.CancelledError if transition in ("cancel", "stop") else ConnectionError
        with pytest.raises(expected):
            await asyncio.wait_for(task, 2)
        assert not controller._ready and not controller._tasks
        assert controller._notify_client is None
        assert controller.command_selector == "BOX15"
    finally:
        release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await controller.stop_notify()


@pytest.mark.parametrize("terminal_failure", [False, True])
async def test_cold_public_coordinator_classification_and_pending_query_do_not_deadlock(
    hass, mock_coordinator_connected, terminal_failure
):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_NAME: "Cold app command",
            const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
            const.CONF_STARCODE_COMMAND_SELECTOR: "BOX15",
            const.CONF_STARCODE_UI_SELECTOR: "BOX15",
            const.CONF_STARCODE_TRANSPORT_SELECTOR: "BOX25",
            const.CONF_DISABLE_ANGLE_SENSING: True,
            const.CONF_DISCONNECT_AFTER_COMMAND: False,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    client = make_controller().client
    entered, release, query_queued = asyncio.Event(), asyncio.Event(), asyncio.Event()
    real_execute, real_sleep = coordinator.async_execute_controller_command, asyncio.sleep

    async def read(role):
        if not isinstance(role, str) and role.uuid == MANUFACTURER_UUID:
            entered.set()
            await release.wait()
            return b"star"
        return b"version"

    async def advance(delay):
        if delay == 2:
            await asyncio.wait_for(query_queued.wait(), 2)
        await real_sleep(0)

    async def execute(action, **kwargs):
        if kwargs.get("cancel_running") is False:
            query_queued.set()
        await real_execute(action, **kwargs)

    async def disconnect():
        client.is_connected = False

    client.read_gatt_char.side_effect = read
    client.disconnect = AsyncMock(side_effect=disconnect)
    if terminal_failure:
        client.start_notify.side_effect = OSError("required subscription failed")

    async def user_action(controller):
        await controller.hold_control("head_up", 1)

    task = None
    try:
        with (
            patch(
                "custom_components.adjustable_bed.coordinator.establish_connection",
                AsyncMock(return_value=client),
            ),
            patch("custom_components.adjustable_bed.beds.starcode_abm5_4.asyncio.sleep", advance),
            patch.object(coordinator, "async_execute_controller_command", execute),
        ):
            task = asyncio.create_task(execute(user_action))
            await asyncio.wait_for(entered.wait(), 2)
            await asyncio.wait_for(query_queued.wait(), 2)
            assert not task.done() and coordinator._command_lock.locked()
            assert coordinator.controller is not None and not coordinator.controller._ready
            assert all(
                call.args[1].hex() == "5a0b00a5" for call in client.write_gatt_char.await_args_list
            )
            release.set()
            if terminal_failure:
                with pytest.raises((OSError, ConnectionError)):
                    await asyncio.wait_for(task, 3)
                assert coordinator.controller is None or not coordinator.controller._ready
            else:
                await asyncio.wait_for(task, 3)
                controller = coordinator.controller
                assert controller is not None and controller._ready
                assert controller.command_selector == "BOX25_STAR"
                frames = [call.args[1].hex() for call in client.write_gatt_char.await_args_list]
                assert frames[:3] == [
                    "5a0b00a5",
                    literal_frame("BOX25_STAR", "headUp"),
                    literal_frame("BOX25_STAR", "stop"),
                ]
            if not terminal_failure:
                active = coordinator.controller
                assert active is not None
                await asyncio.wait_for(asyncio.gather(*tuple(active._tasks)), 2)
            assert not coordinator._command_lock.locked()
    finally:
        release.set()
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await coordinator.async_shutdown()


@pytest.mark.parametrize("selector", ["BOX1220", "BOX3633", "BOX25", "BOX25_STAR"])
@pytest.mark.parametrize(
    "level,direction,action,value",
    [
        (4, 1, "changeLightBrightness", 5),
        (4, -1, "changeLightBrightness", 3),
        (6, 1, "changeLightBrightness", 6),
        (1, -1, "turnoffUnderbedLighting", 0),
    ],
)
@pytest.mark.parametrize("fail_write", [False, True])
async def test_no_notify_light_steps_use_retained_level_without_inventing_local_feedback(
    selector, level, direction, action, value, fail_write
):
    controller = make_controller(selector, device="BOX3633")
    controller._level, controller._light_on, controller._ui_state_observed = level, True, True
    controller._publish = lambda: None
    if fail_write:
        controller.client.write_gatt_char.side_effect = BleakError("not an acknowledgement")
    loop, now = asyncio.get_running_loop(), 1.0
    with patch.object(loop, "time", lambda: now):
        await controller._light_step(direction)
        now = 1.5
        await controller._light_step(direction)
        now = 1.501
        await controller._light_step(direction)
    expected = (
        literal_frame(selector, action)
        if action == "turnoffUnderbedLighting"
        else f"5ae00400{value:02x}0000a5"
        if selector == "BOX25_STAR"
        else f"04e000{value:02x}0000"
    )
    assert [call.args[1].hex() for call in controller.client.write_gatt_char.await_args_list] == [
        expected,
        expected,
    ]
    assert controller._level == level and controller._light_on is True
    controller.client.start_notify.assert_not_awaited()
    assert controller._raw_fields["53"] == 0


@pytest.mark.parametrize("paired", [False, True])
async def test_actual_HA_adoption_rebuilds_catalog_once_preserves_side_identity_and_user_updates(
    hass, enable_custom_integrations, paired
):
    from homeassistant.helpers import entity_registry as er

    from custom_components.adjustable_bed.beds.starcode_abm5_4 import StarcodeAbm5_4Controller
    from custom_components.adjustable_bed.controller_factory import create_controller
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    left, right = "AA:BB:CC:DD:EE:01", "AA:BB:CC:DD:EE:02"
    data = {
        CONF_NAME: "App adoption",
        CONF_ADDRESS: left,
        const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
        const.CONF_MOTOR_COUNT: 2,
        const.CONF_HAS_MASSAGE: True,
        const.CONF_DISABLE_ANGLE_SENSING: True,
        const.CONF_DISCONNECT_AFTER_COMMAND: False,
        const.CONF_STARCODE_COMMAND_SELECTOR: "none",
        const.CONF_STARCODE_UI_SELECTOR: "BOX25",
        const.CONF_STARCODE_TRANSPORT_SELECTOR: "BOX1220",
    }
    if paired:
        data.update(
            {
                const.CONF_PAIR_ID: "app-adoption-pair",
                const.CONF_PAIR_MODE: const.PAIR_MODE_SEPARATE_ADDRESS,
                const.CONF_PAIR_SCHEMA_VERSION: 1,
                const.CONF_PAIR_MEMBER_ADDRESSES: [left, right],
                const.CONF_PAIR_CHILDREN: [
                    {**data, CONF_ADDRESS: address, CONF_NAME: side, const.CONF_SIDE: side}
                    for side, address in [("left", left), ("right", right)]
                ],
            }
        )
        data.pop(CONF_ADDRESS)
    entry = MockConfigEntry(domain=const.DOMAIN, version=4, unique_id="app-adoption", data=data)
    entry.add_to_hass(hass)

    async def connect(coordinator: AdjustableBedCoordinator):
        client = make_controller(device="BOX1220").client

        async def disconnect():
            client.is_connected = False

        client.disconnect = AsyncMock(side_effect=disconnect)
        coordinator._client = client
        coordinator._controller = await create_controller(
            coordinator, const.BED_TYPE_STARCODE_ABM5_4, None, client
        )
        await coordinator._controller.start_notify()
        return True

    def loaded_child():
        loaded = hass.data[const.DOMAIN][entry.entry_id]
        if paired:
            assert isinstance(loaded, PairedBedCoordinator)
            child = loaded.child_for_side("left")
            assert isinstance(child, AdjustableBedCoordinator)
            return child
        assert isinstance(loaded, AdjustableBedCoordinator)
        return loaded

    registry = er.async_get(hass)
    with (
        patch.object(AdjustableBedCoordinator, "async_connect", connect),
        patch.object(AdjustableBedCoordinator, "_schedule_position_hydration"),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        original = {
            row.unique_id: row.entity_id
            for row in er.async_entries_for_config_entry(registry, entry.entry_id)
        }
        assert not any("controller_number_starcode_abm5_4_light_level" in key for key in original)
        profile_button = next(
            row.entity_id
            for row in er.async_entries_for_config_entry(registry, entry.entry_id)
            if left in row.unique_id
            and row.unique_id.endswith("_starcode_abm5_4_use_detected_profile")
        )
        coordinator = loaded_child()
        controller = coordinator.controller
        assert isinstance(controller, StarcodeAbm5_4Controller)
        controller._ui_state_observed = True
        controller._massage_on, controller._light_on, controller._level, controller._timer_index = (
            True,
            True,
            4,
            2,
        )
        (
            controller._head_intensity,
            controller._wave,
            controller._low_4b,
            controller._automatic_white_flag,
        ) = 2, 4, 1, True
        controller._publish()
        if paired:
            loaded = hass.data[const.DOMAIN][entry.entry_id]
            assert isinstance(loaded, PairedBedCoordinator)
            other = loaded.child_for_side("right")
            assert isinstance(other, AdjustableBedCoordinator)
            other_controller = other.controller
            assert isinstance(other_controller, StarcodeAbm5_4Controller)
            other_controller._ui_state_observed = True
            other_controller._massage_on = False
            other_controller._light_on = True
            other_controller._level = 3
            other_controller._timer_index = 1
            other_controller._head_intensity = 1
            other_controller._wave = 2
            other_controller._low_4b = 0
            other_controller._automatic_white_flag = False
            other_controller._publish()
        with patch.object(
            hass.config_entries, "async_reload", wraps=hass.config_entries.async_reload
        ) as reload:
            await hass.services.async_call(
                "button", "press", {"entity_id": profile_button}, blocking=True
            )
            await hass.async_block_till_done()
            assert coordinator._pending_capability_reload
            assert coordinator._pending_internal_bond_marker is None
            reload.assert_not_awaited()
            await coordinator.async_disconnect(serialize_with_commands=True)
            await hass.async_block_till_done()
            reload.assert_awaited_once_with(entry.entry_id)
            rebuilt = loaded_child()
            adopted = rebuilt.controller
            assert isinstance(adopted, StarcodeAbm5_4Controller)
            assert (adopted.command_selector, adopted.ui_selector) == ("BOX1220", "BOX1220")
            current = {
                row.unique_id: row.entity_id
                for row in er.async_entries_for_config_entry(registry, entry.entry_id)
            }
            removed_light = coordinator.entity_unique_id("under_bed_lights")
            assert removed_light not in current
            assert all(
                current.get(key) == value for key, value in original.items() if key != removed_light
            )
            assert any(
                left in row.unique_id and row.translation_key == "toggle_light"
                for row in er.async_entries_for_config_entry(registry, entry.entry_id)
            )
            assert any(
                left in key and "controller_number_starcode_abm5_4_light_level" in key
                for key in current
            )
            assert any(
                left in key and "controller_select_starcode_abm5_4_massage_timer" in key
                for key in current
            )
            if paired:
                assert not any(
                    right in key and "controller_number_starcode_abm5_4_light_level" in key
                    for key in current
                )
                descriptors = entry.data[const.CONF_PAIR_CHILDREN]
                assert descriptors[1][const.CONF_STARCODE_COMMAND_SELECTOR] == "none"
                loaded = hass.data[const.DOMAIN][entry.entry_id]
                assert isinstance(loaded, PairedBedCoordinator)
                other = loaded.child_for_side("right")
                assert isinstance(other, AdjustableBedCoordinator)
                restored_other = other.controller
                assert isinstance(restored_other, StarcodeAbm5_4Controller)
                assert (
                    restored_other._massage_on,
                    restored_other._light_on,
                    restored_other._level,
                    restored_other._timer_index,
                    restored_other._head_intensity,
                    restored_other._wave,
                    restored_other._low_4b,
                    restored_other._automatic_white_flag,
                ) == (False, True, 3, 1, 1, 2, 0, False)
                assert not restored_other._parser_state_observed
            assert (
                adopted._massage_on,
                adopted._light_on,
                adopted._level,
                adopted._timer_index,
                adopted._head_intensity,
                adopted._wave,
                adopted._low_4b,
                adopted._automatic_white_flag,
            ) == (True, True, 4, 2, 2, 4, 1, True)
            assert not adopted._parser_state_observed and adopted._raw_fields["53"] == 0
            await hass.services.async_call(
                "button", "press", {"entity_id": profile_button}, blocking=True
            )
            await hass.async_block_till_done()
            assert (
                not rebuilt._pending_capability_reload
                and rebuilt._pending_internal_bond_marker is None
            )
            assert reload.await_count == 1
            hass.config_entries.async_update_entry(
                entry, data={**entry.data, const.CONF_IDLE_DISCONNECT_SECONDS: 45}
            )
            await hass.async_block_till_done()
            assert reload.await_count == 2
        assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    "replacement",
    ["delayed", "fresh_native", "light_intent", "address", "profile", "failed", "missing"],
)
async def test_internal_reload_handoff_preserves_delayed_factory_but_rejects_new_owner_or_state(
    hass, mock_coordinator_connected, replacement
):
    from dataclasses import replace

    from custom_components.adjustable_bed.beds.starcode_abm5_4 import StarcodeAbm5_4Controller
    from custom_components.adjustable_bed.beds.starcode_abm5_4_profiles import RetainedAppState
    from custom_components.adjustable_bed.controller_factory import create_controller

    address = "AA:BB:CC:DD:EE:FF"
    data = {
        CONF_ADDRESS: address,
        CONF_NAME: "Reload owner",
        const.CONF_BED_TYPE: const.BED_TYPE_STARCODE_ABM5_4,
        const.CONF_STARCODE_COMMAND_SELECTOR: "BOX1220",
        const.CONF_STARCODE_UI_SELECTOR: "BOX1220",
        const.CONF_STARCODE_TRANSPORT_SELECTOR: "BOX1220",
    }
    entry = MockConfigEntry(domain=const.DOMAIN, version=4, data=data)
    entry.add_to_hass(hass)
    old = AdjustableBedCoordinator(hass, entry)
    snapshot = RetainedAppState(address, True, True, True, 4, 2, 2, 4, 1, True, 1000)
    old.starcode_app_retained_state = snapshot
    old._pending_capability_reload = True
    hass.data.setdefault(const.DOMAIN, {})[entry.entry_id] = old
    new_data = {**data}
    if replacement == "address":
        new_data[CONF_ADDRESS] = "AA:BB:CC:DD:EE:00"
    if replacement == "profile":
        new_data[const.CONF_BED_TYPE] = const.BED_TYPE_LINAK
    other_entry = MockConfigEntry(
        domain=const.DOMAIN, version=4, data=new_data, entry_id=entry.entry_id
    )
    new = AdjustableBedCoordinator(hass, other_entry)
    fresh = None
    if replacement in ("fresh_native", "light_intent"):
        fresh = replace(
            snapshot,
            level=2,
            wave=1,
            observed=replacement == "fresh_native",
            last_light_time_ms=2000 if replacement == "light_intent" else None,
        )
        new.starcode_app_retained_state = fresh

    async def reload(_entry_id):
        if replacement == "failed":
            return False
        if replacement == "missing":
            hass.data[const.DOMAIN].pop(entry.entry_id)
        else:
            hass.data[const.DOMAIN][entry.entry_id] = new
        return True

    with patch.object(hass.config_entries, "async_reload", side_effect=reload) as operation:
        await old._async_reload_if_capability_changed()
        operation.assert_awaited_once_with(entry.entry_id)
    if replacement == "delayed":
        assert new.controller is None and new._offline_controller is None
        assert new.starcode_app_retained_state == snapshot
        controller = await create_controller(
            new, const.BED_TYPE_STARCODE_ABM5_4, None, make_controller(device="BOX1220").client
        )
        assert isinstance(controller, StarcodeAbm5_4Controller)
        assert (
            controller._massage_on,
            controller._light_on,
            controller._level,
            controller._timer_index,
            controller._head_intensity,
            controller._wave,
            controller._low_4b,
            controller._automatic_white_flag,
        ) == (True, True, 4, 2, 2, 4, 1, True)
        assert controller._last_light_time_ms == 1000
        assert not controller._parser_state_observed and not controller._tasks
        assert controller._raw_fields["53"] == 0 and not controller._ready
    elif fresh is not None:
        assert new.starcode_app_retained_state == fresh
    else:
        assert new.starcode_app_retained_state is None
    await old.async_shutdown()
    await new.async_shutdown()


@pytest.mark.parametrize("ui", ["BOX25", "BOX1220"])
@pytest.mark.parametrize("changed", [False, True])
async def test_first_partial_callback_uses_fresh_model_and_exact_whole_Home_consumer(ui, changed):
    from custom_components.adjustable_bed.beds.starcode_abm5_4_profiles import RetainedAppState

    controller = make_controller("BOX25", ui=ui)
    retained = RetainedAppState(
        controller._owner_address, True, True, True, 4, 2, 2, 4, 1, True, 1000
    )
    assert controller.restore_retained_app_state(retained)
    role = controller.client.services[0].characteristics[1]
    pending = []
    controller._spawn = pending.append
    data = bytearray.fromhex("a50d0000000000000000000000000000000000")
    if changed:
        data[4] = 1
    controller._notification(controller.client, 0, role, data)
    assert controller._parser_state_observed
    assert controller._raw_fields["2b"] == int(changed)
    expected = (
        (False, False, 0, 0, 0, 0, 0, True)
        if changed and ui == "BOX25"
        else (True, True, 4, 2, 2, 4, 1, True)
    )
    assert (
        controller._massage_on,
        controller._light_on,
        controller._level,
        controller._timer_index,
        controller._head_intensity,
        controller._wave,
        controller._low_4b,
        controller._automatic_white_flag,
    ) == expected
    assert controller._last_light_time_ms == 1000
    assert not controller._tasks
    assert len(pending) == int(changed and ui == "BOX25")
