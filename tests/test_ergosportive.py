"""Selected A100 behavior through native setup, entities, scheduler and paired admission."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const
from custom_components.adjustable_bed.beds.keeson import ergosportive as bed
from custom_components.adjustable_bed.codec import sleep_assistant as codec
from custom_components.adjustable_bed.profiles import ergosportive as app
from tests.hold_lease_wire import _tool, virtual_clock

ADDRESS = "AA:BB:CC:DD:01:A0"


def data(variant="remote", controls=None, sensor="old_dsp_normal"):
    return {
        "address": ADDRESS,
        "name": "ErgoSportive",
        const.CONF_BED_TYPE: "ergosportive",
        const.CONF_PROTOCOL_VARIANT: variant,
        const.CONF_PRODUCT_TYPE: sensor,
        app.CONF_CONTROLS: list(app.CONTROLS) if controls is None else controls,
        const.CONF_DISABLE_ANGLE_SENSING: True,
        const.CONF_HAS_MASSAGE: False,
        const.CONF_MOTOR_COUNT: 3,
        const.CONF_MOTOR_PULSE_DELAY_MS: 100,
        const.CONF_CONNECTION_MODE: const.CONNECTION_MODE_IDLE,
    }


def gatt(response=True):
    return _tool().FakeServices(
        {
            "services": {codec.SERVICE: [codec.WRITE, codec.NOTIFY]},
            "properties": {
                codec.WRITE: ["write" if response else "write-without-response"],
                codec.NOTIFY: ["notify"],
            },
        }
    )


async def native(hass, client, variant="remote", controls=None):
    client.services = gatt()
    entry = MockConfigEntry(
        domain=const.DOMAIN, title="ErgoSportive", unique_id=ADDRESS, data=data(variant, controls)
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, hass.data[const.DOMAIN][entry.entry_id]


@pytest.mark.parametrize("variant", app.VARIANTS)
async def test_native_setup_requires_explicit_release_and_optional_sensor(hass, variant):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES
    from custom_components.adjustable_bed.profile_id import resolve_profile_id
    from tests.form_helpers import finish_new_bed

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._app_after_device = "manual_entry"
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    await flow.async_step_select_app()
    await flow.async_step_select_app({const.CONF_BED_TYPE: BED_TYPE_DISPLAY_NAMES["ergosportive"]})
    result = await flow.async_step_manual_entry({"address": ADDRESS})
    assert result["step_id"] == "profile_questions"
    result = await flow.async_step_profile_questions(
        {
            const.CONF_PROTOCOL_VARIANT: variant,
            const.CONF_PRODUCT_TYPE: "old_dsp_normal",
            app.CONF_CONTROLS: ["head", "tilt", "lamp"],
        }
    )
    await finish_new_bed(flow, result)
    saved = flow._finish_with_verify.await_args.args[0]
    assert app.selected(saved).controls == {"head", "tilt", "lamp"}
    assert app.selected(saved).old_dsp_normal
    assert resolve_profile_id(saved) == f"ergosportive:{variant}"


@pytest.mark.parametrize("variant", app.VARIANTS)
async def test_all_selected_actions_and_sensor_entities(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, variant
):
    entry, coordinator = await native(hass, mock_bleak_client, variant)
    controller = coordinator.controller
    assert isinstance(controller, bed.ErgoSportiveController)
    registry = er.async_get(hass)
    entities = [e for e in registry.entities.values() if e.config_entry_id == entry.entry_id]
    assert not controller.supports_memory_programming
    assert controller.execution.declared == {"hold"}
    assert not controller.supports_single_address_pairing
    with virtual_clock():
        for name, word in app.WORDS.items():
            mock_bleak_client.write_gatt_char.reset_mock()
            if name in controller.held_control_options:
                await hass.services.async_call(
                    const.DOMAIN,
                    "hold_control",
                    {"device_id": entities[0].device_id, "control": name, "duration": 0.2},
                    blocking=True,
                )
                expected = [codec.instruction(word)] * 2
            elif name in ("flat", "zero_g"):
                entity = next(
                    e
                    for e in entities
                    if e.domain == "button" and e.translation_key == f"preset_{name}"
                )
                await hass.services.async_call(
                    "button", "press", {"entity_id": entity.entity_id}, blocking=True
                )
                expected = [codec.instruction(word)]
            else:
                entity = next(e for e in entities if e.translation_key == f"ergosportive_{name}")
                await hass.services.async_call(
                    "button", "press", {"entity_id": entity.entity_id}, blocking=True
                )
                expected = [codec.instruction(word)]
            expected.append(codec.instruction(0))
            if variant == "hardware221":
                expected.append(codec.ergosportive_secondary_release())
            assert [
                call.args[1] for call in mock_bleak_client.write_gatt_char.await_args_list
            ] == expected, name
        number = next(e for e in entities if e.translation_key == "ergosportive_brightness")
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            "number", "set_value", {"entity_id": number.entity_id, "value": 13}, blocking=True
        )
        assert [c.args[1] for c in mock_bleak_client.write_gatt_char.await_args_list] == [
            codec.light(13, False),
            codec.instruction(0),
        ]
    sender, receive = mock_bleak_client.start_notify.await_args.args
    frame = bytearray(15)
    frame[0], frame[9], frame[10], frame[12] = 0x8A, 72, 16, 1
    receive(sender, frame)
    await hass.async_block_till_done()
    assert coordinator.controller_state[bed.HEART] == 72
    assert coordinator.controller_state[bed.BREATHING] == 16
    assert coordinator.controller_state[bed.PRESENCE] is True
    frame[14] = 1
    receive(sender, frame)
    assert coordinator.controller_state[bed.HEART] is None
    assert coordinator.controller_state[bed.TWITCH] == 0
    controller.on_disconnect()
    frame[14] = 0
    receive(sender, frame)
    assert coordinator.controller_state[bed.PRESENCE] is None
    assert await hass.config_entries.async_unload(entry.entry_id)


async def connected(hass, client, variant="remote", controls=None, response=True):
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    client.services = gatt(response)
    entry = MockConfigEntry(domain=const.DOMAIN, data=data(variant, controls), title="ErgoSportive")
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._client = client
    controller = bed.ErgoSportiveController(coordinator, app.selected(entry.data))
    coordinator._controller = controller
    await controller.async_discover_capabilities()
    await controller.start_notify()
    return coordinator, controller


@pytest.mark.parametrize("variant", app.VARIANTS)
async def test_cancellation_settles_write_then_cleans_original_link(
    hass, mock_bleak_client, variant
):
    coordinator, controller = await connected(hass, mock_bleak_client, variant)
    entered, proceed = asyncio.Event(), asyncio.Event()
    original = mock_bleak_client.write_gatt_char

    async def write(char, frame, **kwargs):
        if frame == codec.instruction(1):
            entered.set()
            await proceed.wait()

    original.side_effect = write
    with virtual_clock():
        task = asyncio.create_task(controller.hold_control("head_up", 1000))
        await entered.wait()
        task.cancel()
        proceed.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    expected = [codec.instruction(1), codec.instruction(0)]
    if variant == "hardware221":
        expected.append(codec.ergosportive_secondary_release())
    assert [c.args[1] for c in original.await_args_list] == expected


async def test_precancel_subscription_failure_and_replaced_controller_write_nothing(
    hass, mock_bleak_client
):
    coordinator, controller = await connected(hass, mock_bleak_client, controls=["head"])
    coordinator.cancel_command.set()
    with pytest.raises(asyncio.CancelledError):
        await controller.run_action("head_up")
    mock_bleak_client.write_gatt_char.assert_not_awaited()
    coordinator.cancel_command.clear()
    coordinator._controller = None
    with pytest.raises(ConnectionError):
        await controller.run_action("head_up")
    coordinator._controller = controller
    await controller.stop_notify()
    mock_bleak_client.start_notify.side_effect = ConnectionError("subscription failure")
    with pytest.raises(ConnectionError):
        await controller.start_notify()
    with pytest.raises(ConnectionError):
        await controller.run_action("head_up")
    mock_bleak_client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("missing_subscription", [True, False])
async def test_paired_all_target_readiness_before_either_receiver_moves(
    hass, mock_bleak_client, missing_subscription
):
    from copy import deepcopy

    from custom_components.adjustable_bed.paired_coordinator import (
        PairedBedCoordinator,
        PairedSideError,
    )

    first, left = await connected(hass, mock_bleak_client)
    right_client = deepcopy(mock_bleak_client)
    second, right = await connected(hass, right_client)
    first.async_ensure_connected = AsyncMock(return_value=True)
    second.async_ensure_connected = AsyncMock(return_value=True)
    pair_entry = MockConfigEntry(domain=const.DOMAIN, data={const.CONF_PAIR_ID: "a100-pair"})
    pair_entry.add_to_hass(hass)
    pair = PairedBedCoordinator(
        hass,
        pair_entry,
        {const.SIDE_LEFT: first, const.SIDE_RIGHT: second},
        connection_mode=const.PAIR_CONNECTION_MODE_CONCURRENT,
    )
    if missing_subscription:
        right._subscription = None
    else:
        second._controller = None  # queued replacement cannot use the captured old controller
    with virtual_clock(), pytest.raises((PairedSideError, ValueError, ConnectionError)):
        await pair.async_execute_controller_command(
            lambda c: c.hold_control("head_up", 100), side=const.SIDE_BOTH
        )
    mock_bleak_client.write_gatt_char.assert_not_awaited()
    right_client.write_gatt_char.assert_not_awaited()
    await pair.async_shutdown()


@pytest.mark.parametrize("variant", app.VARIANTS)
async def test_exact_release_deadlines_and_discovered_write_property(
    hass, mock_bleak_client, variant
):
    _, controller = await connected(hass, mock_bleak_client, variant, response=False)
    writes = []

    async def record(char, frame, **kwargs):
        writes.append(
            (round(asyncio.get_running_loop().time() * 1000), bytes(frame), kwargs["response"])
        )

    mock_bleak_client.write_gatt_char.side_effect = record
    with virtual_clock():
        start = round(asyncio.get_running_loop().time() * 1000)
        await controller.run_action("flat")
    assert [(time - start, frame, response) for time, frame, response in writes] == [
        (0, codec.instruction(app.WORDS["flat"]), False),
        (500, codec.instruction(0), False),
        *(
            ([(800, codec.ergosportive_secondary_release(), False)])
            if variant == "hardware221"
            else []
        ),
    ]


async def test_gatt_failure_after_dispatch_still_releases_and_stale_callback_is_ignored(
    hass, mock_bleak_client
):
    _, controller = await connected(hass, mock_bleak_client)

    async def fail(char, frame, **kwargs):
        if frame == codec.instruction(1):
            raise ConnectionError("transport may already have delivered the movement")

    mock_bleak_client.write_gatt_char.side_effect = fail
    with virtual_clock(), pytest.raises(ConnectionError):
        await controller.run_action("head_up")
    assert [c.args[1] for c in mock_bleak_client.write_gatt_char.await_args_list] == [
        codec.instruction(1),
        codec.instruction(0),
    ]


async def test_replaced_subscription_during_cleanup_cannot_release_new_session(
    hass, mock_bleak_client
):
    _, controller = await connected(hass, mock_bleak_client)

    async def replace(char, frame, **kwargs):
        if frame == codec.instruction(app.WORDS["flat"]):
            controller._subscription = object()

    mock_bleak_client.write_gatt_char.side_effect = replace
    with virtual_clock():
        await controller.run_action("flat")
    # A changed subscription already present when cleanup begins also means
    # the command no longer owns that session.
    assert [c.args[1] for c in mock_bleak_client.write_gatt_char.await_args_list] == [
        codec.instruction(app.WORDS["flat"])
    ]


@pytest.mark.parametrize("role", ["service", "write", "notify"])
async def test_setup_and_runtime_use_the_same_exact_gatt_tuple(hass, mock_bleak_client, role):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow

    _, controller = await connected(hass, mock_bleak_client)
    service = next(iter(mock_bleak_client.services))
    if role == "service":
        service.uuid = "0000ffe0-0000-1000-8000-00805f9b34fb"
    else:
        service.get_characteristic(codec.WRITE if role == "write" else codec.NOTIFY).properties = [
            "read"
        ]
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    with pytest.raises(ConnectionError):
        flow._migration_endpoint_check(mock_bleak_client, data())
    with pytest.raises(ConnectionError):
        await controller.async_discover_capabilities()
    mock_bleak_client.write_gatt_char.assert_not_awaited()


async def test_queued_profile_change_revokes_old_control_admission(hass, mock_bleak_client):
    coordinator, controller = await connected(hass, mock_bleak_client)
    coordinator.entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        coordinator.entry,
        data={**coordinator.entry.data, const.CONF_PROTOCOL_VARIANT: "hardware221"},
    )
    with pytest.raises(ConnectionError):
        await controller.run_action("flat")
    mock_bleak_client.write_gatt_char.assert_not_awaited()


async def test_secondary_release_keeps_its_own_deadline_when_neutral_delivery_fails(
    hass, mock_bleak_client
):
    _, controller = await connected(hass, mock_bleak_client, "hardware221")
    writes = []

    async def fail_neutral(char, frame, **kwargs):
        writes.append((round(asyncio.get_running_loop().time() * 1000), bytes(frame)))
        if frame == codec.instruction(0):
            await asyncio.sleep(0.1)
            raise ConnectionError("neutral failed after dispatch")

    mock_bleak_client.write_gatt_char.side_effect = fail_neutral
    with virtual_clock():
        start = round(asyncio.get_running_loop().time() * 1000)
        with pytest.raises(ConnectionError):
            await controller.run_action("flat")
    assert [(at - start, frame) for at, frame in writes] == [
        (0, codec.instruction(app.WORDS["flat"])),
        (500, codec.instruction(0)),
        (800, codec.ergosportive_secondary_release()),
    ]
