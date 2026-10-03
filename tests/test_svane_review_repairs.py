"""Actual public boundaries for the four scoped PR648 findings."""

from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.svane import FEET, HEAD, OLD, OLD_CHAR, UP
from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
from custom_components.adjustable_bed.const import (
    BED_TYPE_SVANE,
    CONF_BED_TYPE,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_ID,
    CONF_PROTOCOL_VARIANT,
    CONF_SIDE,
    DOMAIN,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
    SVANE_VARIANT_JMC,
    SVANE_VARIANT_MULTI,
)
from custom_components.adjustable_bed.services import async_register_services
from tests.test_svane import make_controller, written
from tests.test_svane_services import target


@pytest.mark.parametrize("profile", ["multi", "jmc"])
async def test_failed_release_remains_admitted_for_public_stop_retry(profile):
    controller = make_controller(profile)
    role = (HEAD, UP) if profile == "multi" else (OLD, OLD_CHAR)
    controller._started.add(role)
    controller.client.write_gatt_char.side_effect = [BleakError("first STOP failed"), None]
    with pytest.raises(BleakError):
        await controller.stop_all()
    assert role in controller._started
    await controller.stop_all()
    assert role not in controller._started
    assert [packet for _, _, packet in written(controller)] == [
        "0000" if profile == "multi" else "100000000000"
    ] * 2


@pytest.mark.parametrize("profile", ["multi", "jmc"])
@pytest.mark.parametrize("failure", ["missing", "error", "empty"])
async def test_registered_save_does_not_overwrite_slot_with_stale_read(hass, profile, failure):
    await async_register_services(hass)
    coordinator, controller = target(profile)
    controller.session.head, controller.session.feet = b"old head", b"old feet"
    controller.session.position = bytes.fromhex("11223344")
    controller.session.multi_slots[1] = (b"saved head", b"saved feet")
    before = controller.session.preferences()
    multi_before = dict(controller.session.multi_slots)
    failed_service = FEET if profile == "multi" else OLD
    failed = next(s for s in controller.client.services if s.uuid == failed_service)
    if failure == "missing":
        failed.characteristics = []
    else:
        failed_roles = tuple(failed.characteristics)
        original_read = controller.client.read_gatt_char.side_effect

        async def read(role):
            if role in failed_roles:
                if failure == "error":
                    raise BleakError("read failed")
                return b""
            return await original_read(role)

        controller.client.read_gatt_char = AsyncMock(side_effect=read)
    with (
        patch("custom_components.adjustable_bed.services._resolve_sided_targets",
              return_value=([(coordinator, SIDE_BOTH)], [])),
        pytest.raises(ValueError, match="valid|fresh|raw|position"),
    ):
        await hass.services.async_call(
            DOMAIN, "save_preset", {"device_id": "bed", "preset": 1}, blocking=True
        )
    assert controller.session.preferences() == before
    assert controller.session.multi_slots == multi_before
    controller._coordinator.save_app_state.assert_not_called()
    controller.client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("requested", [SVANE_VARIANT_MULTI, SVANE_VARIANT_JMC])
async def test_shared_pair_profile_edit_preserves_each_physical_descriptor(hass, requested):
    first = {
        CONF_ADDRESS: "AA:BB:CC:DD:EE:01", CONF_BED_TYPE: BED_TYPE_SVANE,
        CONF_SIDE: SIDE_LEFT, CONF_PROTOCOL_VARIANT: (
            SVANE_VARIANT_JMC if requested == SVANE_VARIANT_MULTI else SVANE_VARIANT_MULTI
        ),
    }
    second = {**first, CONF_ADDRESS: "AA:BB:CC:DD:EE:02", CONF_SIDE: SIDE_RIGHT,
              CONF_PROTOCOL_VARIANT: requested}
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_PAIR_ID: "pair",
        CONF_PAIR_CHILDREN: [first, second], CONF_NAME: "Pair"})
    entry.add_to_hass(hass)
    before = deepcopy(dict(entry.data))
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    result = await flow._async_options_form({CONF_PROTOCOL_VARIANT: requested}, step_id="settings")
    if result.get("type") == "form" and not result.get("errors"):
        result = await flow._async_options_form({CONF_PROTOCOL_VARIANT: requested}, step_id="settings")
    assert result.get("errors", {}).get(CONF_PROTOCOL_VARIANT) == "svane_unpair_first"
    assert entry.data == before


@pytest.mark.parametrize("profile,control", [
    ("multi", "feet_up"), ("jmc", "feet_down"), ("multi", "head_up_feet_down"),
])
async def test_registered_minimum_hold_rejects_asymmetric_or_empty_delivery(hass, profile, control):
    await async_register_services(hass)
    coordinator, controller = target(profile)
    with (
        patch("custom_components.adjustable_bed.services._resolve_sided_targets",
              return_value=([(coordinator, SIDE_BOTH)], [])),
        pytest.raises(ServiceValidationError, match="100|0.1"),
    ):
        await hass.services.async_call(DOMAIN, "svane_hold_control",
            {"device_id": "bed", "control": control, "duration": 0.1}, blocking=True)
    controller.client.write_gatt_char.assert_not_awaited()
    coordinator.async_execute_controller_command.assert_not_awaited()


@pytest.mark.parametrize("profile", ["multi", "jmc"])
async def test_task_cancelled_release_is_retried_with_the_same_proven_frame(profile):
    import asyncio

    controller = make_controller(profile)
    role = (HEAD, UP) if profile == "multi" else (OLD, OLD_CHAR)
    controller._started.add(role)
    started = asyncio.Event()

    async def blocked_write(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    controller.client.write_gatt_char.side_effect = blocked_write
    task = asyncio.create_task(controller.stop_all())
    async with asyncio.timeout(1):
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert role in controller._started
    controller.client.write_gatt_char.side_effect = None
    await controller.stop_all()
    assert not controller._started
    assert [packet for _, _, packet in written(controller)] == [
        "0000" if profile == "multi" else "100000000000"
    ] * 2


@pytest.mark.parametrize("profile", ["multi", "jmc"])
async def test_admitted_coordinator_stop_retries_failed_cancelled_motion_cleanup(hass, profile):
    import asyncio

    from custom_components.adjustable_bed.const import CONF_DISCONNECT_AFTER_COMMAND
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_NAME: "Svane",
        CONF_BED_TYPE: BED_TYPE_SVANE,
        CONF_PROTOCOL_VARIANT: SVANE_VARIANT_JMC if profile == "jmc" else SVANE_VARIANT_MULTI,
        CONF_DISCONNECT_AFTER_COMMAND: False,
    })
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    controller = make_controller(profile)
    coordinator._client = controller.client
    controller._coordinator = coordinator
    coordinator._controller = controller
    moving = asyncio.Event()
    stop_frame = bytes.fromhex("0000" if profile == "multi" else "100000000000")
    stops = 0

    async def write(role, payload, **kwargs):
        nonlocal stops
        if bytes(payload) == stop_frame:
            stops += 1
            if stops == 1:
                raise BleakError("cancelled motion cleanup failed")
        else:
            moving.set()

    controller.client.write_gatt_char.side_effect = write

    async def blocked_refresh(seconds):
        await asyncio.Event().wait()

    controller._motor_wait = blocked_refresh
    task = asyncio.create_task(coordinator.async_execute_controller_command(
        lambda ctrl: ctrl.move_head_up(), read_positions_after_operation=False))
    try:
        async with asyncio.timeout(1):
            await moving.wait()
            await coordinator.async_stop_command()
            await asyncio.gather(task, return_exceptions=True)
        assert stops == 2
        assert not controller._started
        assert [packet for _, _, packet in written(controller)][-2:] == [stop_frame.hex()] * 2
        assert not coordinator._command_lock.locked()
        assert not controller.ble_lock.locked()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        coordinator._cancel_disconnect_timer()


@pytest.mark.parametrize("profile", ["multi", "jmc"])
async def test_cancelled_save_preserves_old_slots_and_completed_diagnostics(hass, profile):
    import asyncio

    await async_register_services(hass)
    coordinator, controller = target(profile)
    controller.session.multi_slots[1] = (b"saved head", b"saved feet")
    before = controller.session.preferences()
    multi_before = dict(controller.session.multi_slots)
    calls = 0
    original = controller.client.read_gatt_char.side_effect

    async def read(role):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise asyncio.CancelledError
        return await original(role)

    controller.client.read_gatt_char = AsyncMock(side_effect=read)
    with (
        patch("custom_components.adjustable_bed.services._resolve_sided_targets",
              return_value=([(coordinator, SIDE_BOTH)], [])),
        pytest.raises(asyncio.CancelledError),
    ):
        await hass.services.async_call(DOMAIN, "save_preset",
            {"device_id": "bed", "preset": 1}, blocking=True)
    assert controller.session.preferences() == before
    assert controller.session.multi_slots == multi_before
    assert controller.session.head == bytes.fromhex("8138")
    assert controller.session.position == bytes.fromhex("81388113")
    controller._coordinator.save_app_state.assert_not_called()
    controller.client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("profile", ["multi", "jmc"])
async def test_save_uses_completed_fresh_reads_even_when_notify_subscription_fails(hass, profile):
    await async_register_services(hass)
    coordinator, controller = target(profile)
    controller.client.start_notify.side_effect = BleakError("notification unavailable")
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
               return_value=([(coordinator, SIDE_BOTH)], [])):
        await hass.services.async_call(DOMAIN, "save_preset",
            {"device_id": "bed", "preset": 1}, blocking=True)
    if profile == "jmc":
        assert controller.session.jmc_slots[0] == bytes.fromhex("81388113")
    else:
        assert controller.session.multi_slots[1] == (bytes.fromhex("8138"),) * 2
    controller.client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize("profile,control", [
    ("multi", "feet_up"), ("jmc", "feet_down"), ("multi", "head_up_feet_down"),
])
async def test_first_feet_frame_after_source_delay_for_accepted_hold(hass, monkeypatch, profile, control):
    import asyncio
    from types import SimpleNamespace

    await async_register_services(hass)
    coordinator, controller = target(profile)
    clock = [0.0]
    local_asyncio = SimpleNamespace(**vars(asyncio))
    local_asyncio.get_running_loop = lambda: SimpleNamespace(time=lambda: clock[0])
    monkeypatch.setattr("custom_components.adjustable_bed.beds.svane.asyncio", local_asyncio)

    async def advance(seconds):
        clock[0] += seconds
        await asyncio.sleep(0)

    controller._motor_wait = advance
    observed = []

    async def write(role, payload, **kwargs):
        observed.append((clock[0], role, bytes(payload)))

    controller.client.write_gatt_char.side_effect = write
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets",
               return_value=([(coordinator, SIDE_BOTH)], [])):
        await hass.services.async_call(DOMAIN, "svane_hold_control",
            {"device_id": "bed", "control": control, "duration": 0.101}, blocking=True)
    feet_roles = next(s.characteristics for s in controller.client.services if s.uuid == FEET)
    movement = next(time for time, role, payload in observed
                    if (role in feet_roles and payload == b"\x01\x00")
                    or (profile == "jmc" and payload == bytes.fromhex("102000000000")))
    assert movement == pytest.approx(0.1)
    assert written(controller)[-1][2] in ("0000", "100000000000")


@pytest.mark.parametrize("representative", [SVANE_VARIANT_MULTI, SVANE_VARIANT_JMC])
async def test_shared_common_option_and_rendered_profile_keep_mixed_routes(hass, representative):
    from custom_components.adjustable_bed.const import CONF_IDLE_DISCONNECT_SECONDS
    from custom_components.adjustable_bed.pairing import get_child
    from custom_components.adjustable_bed.svane_state import get_svane_session

    opposite = SVANE_VARIANT_JMC if representative == SVANE_VARIANT_MULTI else SVANE_VARIANT_MULTI
    first = {CONF_ADDRESS: "AA:BB:CC:DD:EE:01", CONF_BED_TYPE: BED_TYPE_SVANE,
             CONF_SIDE: SIDE_LEFT, CONF_PROTOCOL_VARIANT: representative}
    second = {**first, CONF_ADDRESS: "AA:BB:CC:DD:EE:02", CONF_SIDE: SIDE_RIGHT,
              CONF_PROTOCOL_VARIANT: opposite}
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_PAIR_ID: "pair",
        CONF_PAIR_CHILDREN: [first, second], CONF_NAME: "Pair"})
    entry.add_to_hass(hass)
    sessions = [get_svane_session(hass, child[CONF_ADDRESS],
                "jmc" if child[CONF_PROTOCOL_VARIANT] == SVANE_VARIANT_JMC else "multi")
                for child in [first, second]]
    sessions[0].light_on = True
    sessions[1].intensity = 55
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass, flow.handler = hass, entry.entry_id
    form = await flow._async_options_form(None, step_id="settings")
    rendered = {marker.schema: marker.default() for marker in form["data_schema"].schema
                if callable(marker.default)}
    rendered[CONF_PROTOCOL_VARIANT] = representative
    rendered[CONF_IDLE_DISCONNECT_SECONDS] = 50
    result = await flow._async_options_form(rendered, step_id="settings")
    assert result["type"] == "create_entry"
    assert get_child(entry.data, SIDE_LEFT)[CONF_PROTOCOL_VARIANT] == representative
    assert get_child(entry.data, SIDE_RIGHT)[CONF_PROTOCOL_VARIANT] == opposite
    assert get_child(entry.data, SIDE_LEFT)[CONF_ADDRESS] == first[CONF_ADDRESS]
    assert get_child(entry.data, SIDE_RIGHT)[CONF_ADDRESS] == second[CONF_ADDRESS]
    assert sessions[0].light_on and sessions[1].intensity == 55
