"""BedSmart setup, HA service admission and delivery accounting."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import const, services
from custom_components.adjustable_bed.app_state_store import discard_app_state_store
from custom_components.adjustable_bed.beds.richmat_classic.bedsmart import BedSmartController
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.setup_questions import _classic_layouts
from tests.test_bedsmart import clock as clock
from tests.test_richmat_classic_transport import Services, route
from tests.test_richmat_family_flow import answer, fields, setup_flow


async def test_setup_owns_app_and_layout_with_no_protocol_question(hass):
    flow = setup_flow(hass, "6BRM-bed")
    form, _ = await answer(flow, "bedsmart")
    assert form["step_id"] == "profile_questions"
    assert const.CONF_PRODUCT_TYPE in fields(form)
    assert const.CONF_PROTOCOL_VARIANT not in fields(form)
    assert (
        not {"QRRM", "6HRM", "RMCS", "WFRM", "FWRM", "COOL"}
        & _classic_layouts({const.CONF_PROTOCOL_VARIANT: "bedsmart"}).keys()
    )
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions({const.CONF_PRODUCT_TYPE: "B6RU"})
    saved = finish.call_args.args[0]
    assert saved[const.CONF_PROTOCOL_VARIANT] == "bedsmart"
    assert saved[const.CONF_PRODUCT_TYPE] == "B6RM"
    assert saved[const.CONF_DISABLE_ANGLE_SENSING] is True
    entry = MockConfigEntry(domain=const.DOMAIN, data=saved)
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    await coordinator.async_prime_offline_controller()
    assert isinstance(coordinator.capability_controller, BedSmartController)
    await coordinator.async_shutdown()


@pytest.fixture
async def runtime(hass, mock_coordinator_connected, mock_bleak_client, clock):
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            "address": "AA:BB:CC:DD:EE:71",
            "name": "BedSmart",
            "bed_type": const.BED_TYPE_RICHMAT_CLASSIC_APPS,
            "protocol_variant": "bedsmart",
            "product_type": "6BRM",
            "ble_device_name": "6BRM-bed",
            "disable_angle_sensing": True,
            "connection_mode": "idle",
            "motor_pulse_count": 1,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._max_retries = 1
    mock_bleak_client.services = Services([route(0)])
    for service in mock_bleak_client.services:
        service.handle = 1
        for index, channel in enumerate(service.characteristics, 1):
            channel.descriptors = []
            channel.handle = index
            channel.service_uuid = service.uuid
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    mock_bleak_client.stop_notify = AsyncMock()
    await coordinator.async_prime_offline_controller()
    await services.async_register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, "both")], []),
    ):
        yield coordinator, mock_bleak_client
    await coordinator.async_shutdown()


async def test_layout_change_recovers_stale_selection_before_connecting(runtime):
    coordinator, _client = runtime
    controller = coordinator.capability_controller
    assert isinstance(controller, BedSmartController)
    with patch.object(
        coordinator._app_state_store, "async_slot", new=AsyncMock(return_value={"mode": 1})
    ):
        await coordinator._async_restore_app_state(controller)
        assert controller.persisted_app_state["mode"] == 0
        assert await coordinator.async_connect()
    assert coordinator.controller.persisted_app_state["mode"] == 0


@pytest.mark.parametrize(
    ("choice", "layout"),
    [
        ("ZRS0:B8TT", "B8TT"),
        ("ZRS0:B9TT", "B9TT"),
        ("ZRS1:ZRI0", "ZRI0"),
        ("ZRS1:I4RM", "I4RM"),
        ("ZRS1:I5RM", "I5RM"),
        ("ZRS1:D7RM", "D7RM"),
        ("ZRS2:ZR00", "ZR00"),
        ("ZRS2:ZR01", "ZR01"),
        ("ZRS3:APRM", "APRM"),
        ("ZRS3:AQRM", "AQRM"),
    ],
)
async def test_navigation_choice_saves_a_concrete_controllable_layout(hass, choice, layout):
    flow = setup_flow(hass, "6BRM-bed")
    await answer(flow, "bedsmart")
    choices = _classic_layouts({const.CONF_PROTOCOL_VARIANT: "bedsmart"})
    assert not {"ZRS0", "ZRS1", "ZRS2", "ZRS3"} & choices.keys()
    assert choice in choices
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_profile_questions({const.CONF_PRODUCT_TYPE: choice})
    assert finish.await_count == 1
    saved = finish.call_args.args[0]
    assert saved[const.CONF_PRODUCT_TYPE] == layout
    entry = MockConfigEntry(domain=const.DOMAIN, data=saved)
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    try:
        await coordinator.async_prime_offline_controller()
        controller = coordinator.capability_controller
        assert isinstance(controller, BedSmartController)
        assert any(s.key != "richmat_classic_release" for s in controller.controller_button_specs)
    finally:
        await coordinator.async_shutdown()


async def test_named_bed_command_and_source_specific_stop_caller(hass, runtime):
    coordinator, client = runtime
    await hass.services.async_call(
        const.DOMAIN,
        "bedsmart",
        {"device_id": "bed", "operation": "bed_command", "command": "head_up", "duration_ms": 150},
        blocking=True,
    )
    frames = [call.args[1].hex() for call in client.write_gatt_char.await_args_list]
    assert frames[-2:] == ["6e01002493", "6e01006edd"]
    assert coordinator.controller is not None
    client.write_gatt_char.reset_mock()
    await hass.services.async_call(
        const.DOMAIN,
        "bedsmart",
        {"device_id": "bed", "operation": "bed_command", "command": "voice_stop_request"},
        blocking=True,
    )
    assert [call.args[1].hex() for call in client.write_gatt_char.await_args_list] == [
        "6e010047b6",
        "6e01006edd",
    ]


async def test_bedsmart_cannot_reach_lp2_admin_service(hass, runtime):
    _, client = runtime
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            const.DOMAIN, "lp2", {"device_id": "bed", "operation": "motor_program"}, blocking=True
        )
    client.write_gatt_char.assert_not_awaited()


async def test_unknown_and_excluded_actions_fail_before_any_write(hass, runtime):
    import voluptuous as vol

    _, client = runtime
    for op in ("fan", "motor_program", "wifi", "control"):
        with pytest.raises(vol.Invalid):
            await hass.services.async_call(
                const.DOMAIN, "bedsmart", {"device_id": "bed", "operation": op}, blocking=True
            )
    client.write_gatt_char.assert_not_awaited()


async def test_startup_and_release_cannot_deliver_a_cancelled_own_action(runtime):
    from custom_components.adjustable_bed.command_scheduler import (
        Delivery,
        current_command_context,
        delivered,
    )

    coordinator, client = runtime
    seen = []

    async def operation(controller):
        with delivered(seen.append):
            context = current_command_context()
            assert context is not None
            context.cancel_event.set()
            await controller.execute_action(1)

    await coordinator.async_execute_controller_command(operation)
    assert seen == [Delivery.NONE]
    assert [call.args[1].hex() for call in client.write_gatt_char.await_args_list] == [
        "6e02010071",
        "6e01006edd",
    ]


async def test_interrupted_held_refresh_is_partial_despite_cleanup(runtime):
    from custom_components.adjustable_bed.command_scheduler import (
        Delivery,
        current_command_context,
        delivered,
    )

    coordinator, client = runtime
    seen = []

    async def stop_after_frame(_char, frame, **kwargs):
        if frame == bytes.fromhex("6e01002493"):
            context = current_command_context()
            assert context is not None
            context.cancel_event.set()

    client.write_gatt_char.side_effect = stop_after_frame

    async def operation(controller):
        with delivered(seen.append):
            await controller.execute_action(1, hold_ms=600)

    await coordinator.async_execute_controller_command(operation)
    assert seen == [Delivery.PARTIAL]


@pytest.mark.parametrize(
    "operation,fields,expected",
    [
        ("light_duration", {"seconds": 60}, ["6e0b003cb5"]),
        ("aromatherapy", {"aroma_times": [1, 2, 3]}, ["6e1b00018a", "6e1c00028c", "6e1d00038e"]),
    ],
)
async def test_settings_on_fresh_connection_query_and_publish_state(
    hass, runtime, operation, fields, expected
):
    from custom_components.adjustable_bed.beds.richmat_classic.bedsmart import (
        AROMA_KEYS,
        LAMP_SECONDS,
    )

    coordinator, client = runtime

    async def response(_char, frame, **kwargs):
        replies = {"6e0a000179": "6e0e00037f", "6e1a000088": "6e1a000189"}
        if frame.hex() in replies:
            c = coordinator.controller
            c._notification(c._session, c._session.notify, bytearray.fromhex(replies[frame.hex()]))

    client.write_gatt_char.side_effect = response
    await hass.services.async_call(
        const.DOMAIN,
        "bedsmart",
        {"device_id": "bed", "operation": operation, **fields},
        blocking=True,
    )
    frames = [call.args[1].hex() for call in client.write_gatt_char.await_args_list]
    assert frames == ["6e02010071", "6e0a000179", "6e1a000088", *expected]
    if operation == "light_duration":
        assert coordinator.controller_state[LAMP_SECONDS] == 60
    else:
        assert [coordinator.controller_state[key] for key in AROMA_KEYS] == [1, 2, 3]


async def test_number_dispatch_reproves_support_after_reconnect(runtime):
    from custom_components.adjustable_bed.beds.richmat_classic.bedsmart import LAMP_SECONDS
    from custom_components.adjustable_bed.number import AdjustableBedControllerNumber

    coordinator, client = runtime

    async def response(_char, frame, **kwargs):
        if frame.hex() == "6e0a000179":
            c = coordinator.controller
            c._notification(c._session, c._session.notify, bytearray.fromhex("6e0e00037f"))

    client.write_gatt_char.side_effect = response
    await coordinator.async_execute_controller_command(lambda c: c.query_settings())
    spec = next(
        s
        for s in coordinator.controller.controller_number_specs
        if s.key == "bedsmart_lamp_seconds"
    )
    number = AdjustableBedControllerNumber(coordinator, spec)
    await coordinator.async_disconnect()
    client.write_gatt_char.reset_mock()
    await number.async_set_native_value(60)
    frames = [call.args[1].hex() for call in client.write_gatt_char.await_args_list]
    assert "6e0a000179" in frames
    assert frames[-1] == "6e0b003cb5"
    assert coordinator.controller_state[LAMP_SECONDS] == 60


@pytest.mark.parametrize("action", ["refresh", "alarm_pair"])
async def test_task_cancellation_during_required_wait_is_partial(runtime, monkeypatch, action):
    import asyncio
    import contextlib

    from custom_components.adjustable_bed.codec.richmat import countdown
    from custom_components.adjustable_bed.command_scheduler import Delivery, delivered

    coordinator, client = runtime
    await coordinator.async_execute_controller_command(lambda c: c.read_positions())
    client.write_gatt_char.reset_mock()
    c = coordinator.controller

    async def cancelled_wait(_milliseconds, _cancel):
        raise asyncio.CancelledError

    monkeypatch.setattr(c, "_wait", cancelled_wait)
    seen = []

    async def operation(controller):
        with delivered(seen.append):
            if action == "refresh":
                await controller.execute_action(1, hold_ms=600)
            else:
                await controller._frames(countdown(1, 0x45), 300)

    with contextlib.suppress(asyncio.CancelledError):
        await coordinator.async_execute_controller_command(operation)
    assert seen == [Delivery.PARTIAL]
    frames = [call.args[1].hex() for call in client.write_gatt_char.await_args_list]
    assert frames == (["6e01002493", "6e01006edd"] if action == "refresh" else ["6e05010074"])


async def test_stop_on_other_target_during_bedsmart_readiness_prevents_first_write(hass):
    from types import SimpleNamespace

    from custom_components.adjustable_bed.beds.richmat_classic.lp2_services import (
        async_register_lp2_services,
    )
    from tests.test_generic_services import target

    async_register_lp2_services(hass)
    a, first = target(family=BedSmartController, settings=AsyncMock())
    b, second = target(family=BedSmartController, settings=AsyncMock())
    calls = [0]

    async def first_ready(**kwargs):
        calls[0] += 1
        if calls[0] == 2:
            b.stop_epoch += 1

    first.ensure_feature = AsyncMock(side_effect=first_ready)
    second.ensure_feature = AsyncMock()
    for child, c in ((a, first), (b, second)):
        c._receive = SimpleNamespace(light_capable=True, aroma_capable=True)

        async def query(fn, *, current=c, **kwargs):
            return await fn(current)

        child.async_execute_controller_query = AsyncMock(side_effect=query)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(a, "both"), (b, "both")], []),
    ):
        await hass.services.async_call(
            const.DOMAIN,
            "bedsmart",
            {"device_id": ["a", "b"], "operation": "light_duration", "seconds": 60},
            blocking=True,
        )
    assert first.ensure_feature.await_count == 2
    first.settings.assert_not_awaited()
    second.settings.assert_not_awaited()


async def test_movement_test_cancelled_during_release_marks_remaining_stages(runtime, monkeypatch):
    import asyncio
    import contextlib

    from custom_components.adjustable_bed.command_scheduler import Delivery, delivered

    coordinator, _ = runtime
    await coordinator.async_execute_controller_command(lambda c: c.read_positions())
    c = coordinator.controller
    real_release = c._release

    async def release_then_cancel(*args, **kwargs):
        await real_release(*args, **kwargs)
        raise asyncio.CancelledError

    monkeypatch.setattr(c, "_release", release_then_cancel)
    seen = []

    async def operation(controller):
        with delivered(seen.append):
            await controller.diagnostic_cycle()

    with contextlib.suppress(asyncio.CancelledError):
        await coordinator.async_execute_controller_command(operation)
    assert seen == [Delivery.PARTIAL]


async def test_native_stop_after_idle_setting_change_keeps_physical_session(runtime, hass):
    coordinator, client = runtime
    await coordinator.async_execute_controller_command(lambda c: c.read_positions())
    original = coordinator.controller
    hass.config_entries.async_update_entry(
        coordinator.entry, data={**coordinator.entry.data, "idle_disconnect_seconds": 20}
    )
    client.write_gatt_char.reset_mock()
    await coordinator.async_stop_command()
    assert coordinator.controller is original
    assert [call.args[1].hex() for call in client.write_gatt_char.await_args_list] == ["6e01006edd"]


async def test_command_format_survives_a_restart_before_the_first_connection(hass, runtime):
    coordinator, _client = runtime
    offline = coordinator.capability_controller
    assert isinstance(offline, BedSmartController)
    assert ("button", "richmat_classic_1_framed") in offline.retained_entity_keys
    assert not any(s.key.endswith("_framed") for s in offline.controller_button_specs)
    assert await coordinator.async_connect()
    await coordinator._app_state_store.async_save()
    await coordinator.async_shutdown()
    # A restart reads the stored format, not this process's store object.
    discard_app_state_store(hass, coordinator.address)

    restarted = AdjustableBedCoordinator(hass, coordinator.entry)
    await restarted.async_prime_offline_controller()
    controller = restarted.capability_controller
    assert isinstance(controller, BedSmartController)
    assert controller.retained_entity_keys == frozenset()
    keys = {s.key for s in controller.controller_button_specs}
    assert "richmat_classic_1_framed" in keys
    assert not any(key.endswith("_raw") for key in keys)
    await restarted.async_shutdown()
