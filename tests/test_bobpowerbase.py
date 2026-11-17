"""Power Bob Base's actual factory, scheduler, entities and public service."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import services
from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.beds.goodvibe import controller as bed
from custom_components.adjustable_bed.beds.goodvibe import services as configuration
from custom_components.adjustable_bed.beds.goodvibe.controller import (
    GoodVibeController,
    Link,
    select_link,
)
from custom_components.adjustable_bed.beds.goodvibe.receive import Notifications
from custom_components.adjustable_bed.beds.goodvibe.services import Request
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_PRODUCT_TYPE,
    CONF_PROFILE_ID,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profile_id import resolve_profile_id
from custom_components.adjustable_bed.profiles.bobpowerbase import (
    ACTIONS,
    CATALOG,
    LAYOUTS,
    PROFILE_CHOICES,
)
from custom_components.adjustable_bed.sensor import AdjustableBedControllerStateSensor
from custom_components.adjustable_bed.setup_questions import setup_profile

REAL_SLEEP = asyncio.sleep

def runtime(hass, product="ultra_sh", address="AA:BB:CC:DD:EE:96"):
    data = {
        CONF_ADDRESS: address, CONF_NAME: "Power Bob Base", CONF_BED_TYPE: "bobpowerbase",
        CONF_PROTOCOL_VARIANT: product, CONF_PRODUCT_TYPE: "split_head",
        CONF_DISCONNECT_AFTER_COMMAND: False,
    }
    data[CONF_PROFILE_ID] = resolve_profile_id(data)
    entry = MockConfigEntry(domain=DOMAIN, data=data)
    entry.add_to_hass(hass)
    c = AdjustableBedCoordinator(hass, entry)
    c._client = MagicMock(is_connected=True)
    c._client.write_gatt_char = AsyncMock()
    c._client.stop_notify = AsyncMock()
    c._controller = GoodVibeController(c, profile=product, catalog=CATALOG)
    c._offline_controller = GoodVibeController(c, profile=product, catalog=CATALOG)
    c.controller._link = Link(c._client, MagicMock(uuid="tx", properties=["write"], handle=1),
                              MagicMock(uuid="rx", properties=["notify"], handle=2), False)
    return c


@pytest.fixture
def fake_time(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(bed, "monotonic", lambda: now[0])

    async def delay(self, ms):
        now[0] += ms / 1000
        return not self._coordinator.cancel_command.is_set()

    monkeypatch.setattr(GoodVibeController, "_delay", delay)
    monkeypatch.setattr(bed.asyncio, "sleep", AsyncMock())
    return now


@pytest.mark.parametrize("product", PROFILE_CHOICES)
@pytest.mark.parametrize("layout", LAYOUTS)
async def test_persisted_product_layout_reaches_actual_factory(hass, product, layout):
    c = runtime(hass, product)
    hass.config_entries.async_update_entry(c.entry, data={**c.entry.data, CONF_PRODUCT_TYPE: layout})
    obj = await create_controller(c, "bobpowerbase", product, c._client)
    assert isinstance(obj, GoodVibeController) and obj.product is CATALOG.products[product]
    assert obj.profile.key == "bobpowerbase"
    assert c.entry.data[CONF_PROFILE_ID] == f"bobpowerbase:{product}"
    questions = setup_profile("bobpowerbase").questions
    assert [(q.key, q.options(c.entry.data)) for q in questions] == [
        (CONF_PROTOCOL_VARIANT, PROFILE_CHOICES), (CONF_PRODUCT_TYPE, LAYOUTS),
    ]
    assert {CONF_PROTOCOL_VARIANT, CONF_PRODUCT_TYPE} <= per_side_profile("bobpowerbase", product).keys
    assert obj.supports_single_address_pairing == product.endswith("_sh")


def test_all_catalog_actions_and_precise_gates():
    assert {a.short for a in ACTIONS.values()} == {
        0x24, 0x25, 0x26, 0x27, 0x29, 0x2A, 0x3F, 0x40, 0x41, 0x42, 0x31, 0x3C,
        0x4C, 0x4E, 0x48, 0x5E, 0x5F, 0x63, 0x61, 0x46, 0x45, 0x58, 0x2E, 0x2F,
    }
    assert {a.long for a in ACTIONS.values() if a.long} == {0x69, 0x66, 0x64, 0x2B, 0x2C}
    for key, product in CATALOG.products.items():
        assert len(product.alarms) == 5 and product.repeat_alarm
        assert ("light" in product.actions) == key.startswith("elite")
        assert ("massage_head" in product.actions) == key.startswith("ultra")
        assert product.sleep == "deviceSleepMonitoringNone"


@pytest.mark.parametrize("key", CATALOG.wire.transports)
async def test_exact_gatt_properties_write_type_and_startup(hass, fake_time, key):
    c = runtime(hass)
    route = codec.TRANSPORTS[key]
    tx = MagicMock(uuid=route.write_uuid, properties=["write", "write-without-response"], handle=1)
    # Selection follows NOTIFY properties, not the catalog notify UUID.
    rx = MagicMock(uuid="arbitrary-notify", properties=["notify"], handle=2)
    c.client.services = [MagicMock(uuid=route.service_uuid, characteristics=[tx, rx])]
    c.client.start_notify = AsyncMock()
    assert select_link(c.client, 1, CATALOG.wire, bind_framing=True).legacy == route.single
    await c.controller.start_notify()
    frames = [call.args[1] for call in c.client.write_gatt_char.await_args_list]
    assert frames[:3] == [codec.function(code, action=name, single=route.single) for name, code in CATALOG.startup]
    assert len(frames) == 4 and frames[-1][3:6] == bytes((8, 3, 1))
    assert all(call.kwargs["response"] is False for call in c.client.write_gatt_char.await_args_list)


async def test_manual_and_configure_share_product_layout_questions(hass):
    from custom_components.adjustable_bed.config_flow import _configure_questions
    from custom_components.adjustable_bed.validators import (
        get_variants_for_bed_type,
        is_valid_variant_for_bed_type,
    )

    c = runtime(hass)
    assert _configure_questions(c.entry.data).questions == setup_profile("bobpowerbase").questions
    assert get_variants_for_bed_type("bobpowerbase") == PROFILE_CHOICES
    assert not is_valid_variant_for_bed_type("bobpowerbase", "auto")


@pytest.mark.parametrize("route", ("typed", "picked"))
async def test_actual_new_install_and_configure_persist_product_layout(hass, mock_bluetooth_service_info, route):
    from custom_components.adjustable_bed.config_flow import (
        AdjustableBedConfigFlow,
        AdjustableBedOptionsFlow,
    )
    from tests.form_helpers import start_new_bed

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    mock_bluetooth_service_info.name = "QRRM_Bob"
    flow._discovery_info = mock_bluetooth_service_info
    picker = await flow.async_step_select_app()
    assert "bobpowerbase" in picker["data_schema"].schema[CONF_BED_TYPE].rows().values()
    result = await start_new_bed(flow, route, "bobpowerbase")
    assert result["step_id"] == "profile_questions"
    result = await flow.async_step_profile_questions({
        CONF_PROTOCOL_VARIANT: "ultra_sh", CONF_PRODUCT_TYPE: "split",
    })
    assert result["step_id"] == "finish_settings"
    with patch.object(flow, "_finish_with_verify", new=AsyncMock()) as finish:
        await flow.async_step_finish_settings({CONF_NAME: "Bob"})
    saved = finish.call_args.args[0]
    assert (saved[CONF_BED_TYPE], saved[CONF_PROTOCOL_VARIANT], saved[CONF_PRODUCT_TYPE]) == (
        "bobpowerbase", "ultra_sh", "split",
    )
    c = runtime(hass)
    hass.config_entries.async_update_entry(c.entry, data={**c.entry.data, **saved})
    options = AdjustableBedOptionsFlow(c.entry)
    options.hass, options.handler = hass, c.entry.entry_id
    with patch.object(hass.config_entries, "async_schedule_reload"):
        result = await options._async_options_form({}, step_id="settings")
    assert result["type"] == "create_entry"
    assert c.entry.data[CONF_PROFILE_ID] == "bobpowerbase:ultra_sh"
    assert c.entry.data[CONF_PRODUCT_TYPE] == "split"
    controller = await create_controller(c, "bobpowerbase", "ultra_sh", c._client)
    assert controller.product is CATALOG.products["ultra_sh"]


@pytest.mark.parametrize("name", ("QRRM_1", "beforeBED-after", "MPE_x", "209A", "COOL"))
def test_scan_candidates_require_explicit_app_product(name):
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed
    from tests.test_detection import _make_service_info

    found = detect_bed_type_detailed(_make_service_info(name=name))
    assert "bobpowerbase" in {found.bed_type, *(found.ambiguous_types or ())}


@pytest.mark.parametrize(("key", "code"), (("reset", 0x31), ("massage_head", 0x4C), ("massage_10", 0x5F)))
async def test_actual_one_shot_entities_do_not_send_release(hass, fake_time, key, code):
    c = runtime(hass)
    spec = next(s for s in c.controller.controller_button_specs if s.key == "goodvibe_" + key)
    button = ControllerActionButton(c, spec)
    with patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)), patch.object(c, "_async_refresh_controller_auth", AsyncMock()):
        await button.async_press()
    assert [call.args[1] for call in c.client.write_gatt_char.await_args_list] == [codec.function(code)]


async def test_finite_hold_elapsed_deadline_does_not_backfill_latency(hass, fake_time):
    c = runtime(hass)

    async def write(_char, data, **kwargs):
        if data[3] == 0x24:
            fake_time[0] += 0.25

    c.client.write_gatt_char.side_effect = write
    await c.controller.hold_control("goodvibe_head_up", 500)
    assert [call.args[1][3] for call in c.client.write_gatt_char.await_args_list] == [0x24, 0x24, 0x6E]
    assert c.controller.execution.hold == "stream"
    assert "goodvibe_head_up" in c.controller.execution.hold_controls
    assert "goodvibe_reset" not in c.controller.execution.hold_controls


async def test_preset_recall_and_program_have_no_release_or_duplicate_recall(hass, fake_time):
    c = runtime(hass)
    await c.controller.press("memory_1", 1000)
    await c.controller.press("memory_1", 3100)
    assert [call.args[1][3] for call in c.client.write_gatt_char.await_args_list] == [0x2E, 0x2B]


async def test_side_and_captured_release_are_exact_and_raw_right_fails_before_writes(hass, fake_time):
    c = runtime(hass)
    with c.controller.side_scope("right"):
        await c.controller.hold_control("goodvibe_pillow_up", 100)
    assert [call.args[1].hex() for call in c.client.write_gatt_char.await_args_list] == ["6e010141b1", "6e01016ede"]
    c.client.write_gatt_char.reset_mock()
    old = c.controller._link
    c.controller._link = Link(old.client, old.tx, old.rx, True)
    with c.controller.side_scope("right"), pytest.raises(ValueError, match="Nordic"):
        c.controller.validate_hold_control("goodvibe_head_up", 100)
    c.client.write_gatt_char.assert_not_awaited()


async def test_single_address_finite_both_has_no_invented_both_frame(hass, fake_time):
    from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator

    c = runtime(hass)
    entry = MockConfigEntry(domain=DOMAIN, data={"pair_id": "bob-pair", CONF_BED_TYPE: "bobpowerbase", CONF_PROTOCOL_VARIANT: "ultra_sh"})
    pair = SingleAddressPairedCoordinator(hass, entry, c)
    with patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)), patch.object(c, "_async_refresh_controller_auth", AsyncMock()):
        await pair.async_execute_controller_command(lambda ctrl: ctrl.hold_control("goodvibe_head_up", 100), side="both")
    frames = [call.args[1] for call in c.client.write_gatt_char.await_args_list]
    assert [(frame[2], frame[3]) for frame in frames] == [(0, 0x24), (0, 0x6E), (1, 0x24), (1, 0x6E)]


async def test_sequential_renewable_both_rejects_before_claim_or_preflight(hass, fake_time):
    from custom_components.adjustable_bed.command_scheduler import HoldLease
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    left = runtime(hass)
    right = runtime(hass, address="AA:BB:CC:DD:EE:97")
    entry = MockConfigEntry(domain=DOMAIN, data={"pair_id": "bob-two"})
    pair = PairedBedCoordinator(hass, entry, {"left": left, "right": right}, connection_mode="sequential")
    with patch.object(left, "claim_hold_lease") as claim:
        with pytest.raises(ServiceValidationError, match="sequential"):
            await services._async_with_hold_lease([(pair, "both")], HoldLease("card", 1, "goodvibe_head_up", 1), lambda _: None, AsyncMock())
        claim.assert_not_called()
    left.client.write_gatt_char.assert_not_awaited()
    right.client.write_gatt_char.assert_not_awaited()


async def test_light_capability_range_color_and_connection_scoped_state(hass, fake_time):
    c = runtime(hass)
    obj = c.controller
    assert not obj.menu_available("light")
    with pytest.raises(ValueError, match="light menu"):
        Request("light_duration", seconds=0).validate(obj)
    obj._normal.feed(bytes.fromhex("6e0e00037f"))
    assert obj.menu_available("light")
    assert next(s for s in obj.controller_select_specs if s.key == "goodvibe_light_duration").options == tuple(map(str, range(0, 901, 60)))
    with pytest.raises(ValueError, match="durations"):
        Request("light_duration", seconds=960).validate(obj)
    await obj.async_execute_goodvibe_request(Request("light_duration", seconds=0))
    await obj.async_execute_goodvibe_request(Request("light_color", rgb=(16, 32, 48)))
    assert [call.args[1].hex() for call in c.client.write_gatt_char.await_args_list] == [
        "6e0bffff77", "6e0cff10896e0d2030cb",
    ]
    old = obj._link
    obj.on_disconnect()
    assert not obj.menu_available("light") and "repeat_alarms" not in obj.choices.events
    assert obj.persisted_app_state == {"light_duration": 0, "light_color": (16, 32, 48)}
    obj._notification(old, old.rx, bytearray.fromhex("6e0e00037f"))
    assert not obj.menu_available("light")


async def test_stale_queued_write_cannot_cross_session_or_controller(hass, fake_time):
    c = runtime(hass)
    obj, link = c.controller, c.controller._link
    await obj._ble_lock.acquire()
    queued = asyncio.create_task(obj._send(codec.function(0x24), link=link))
    await REAL_SLEEP(0)
    c._controller = GoodVibeController(c, profile="ultra_sh", catalog=CATALOG)
    obj._ble_lock.release()
    with pytest.raises(ConnectionError, match="session changed"):
        await queued
    c.client.write_gatt_char.assert_not_awaited()


async def test_submitted_write_and_canceled_cleanup_both_drain(hass, fake_time):
    c = runtime(hass)
    submitted, release_started, finish_write, finish_release = (asyncio.Event() for _ in range(4))

    async def write(_char, data, **kwargs):
        if data[3] == 0x24:
            submitted.set()
            await finish_write.wait()
        else:
            release_started.set()
            await finish_release.wait()

    c.client.write_gatt_char.side_effect = write
    task = asyncio.create_task(c.controller.hold_control("goodvibe_head_up", 100))
    await submitted.wait()
    task.cancel()
    finish_write.set()
    await release_started.wait()
    task.cancel()
    finish_release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert [call.args[1][3] for call in c.client.write_gatt_char.await_args_list] == [0x24, 0x6E]


async def test_cancellation_first_arriving_during_release_drains_then_propagates(hass, fake_time):
    c = runtime(hass)
    entered, finish = asyncio.Event(), asyncio.Event()

    async def write(_char, data, **kwargs):
        if data[3] == 0x6E:
            entered.set()
            await finish.wait()

    c.client.write_gatt_char.side_effect = write
    task = asyncio.create_task(c.controller.hold_control("goodvibe_head_up", 100))
    await entered.wait()
    task.cancel()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert [call.args[1][3] for call in c.client.write_gatt_char.await_args_list] == [0x24, 0x6E]


async def test_shared_feedback_is_visible_without_invented_position_or_snore_setters(hass):
    c = runtime(hass)
    obj = c.controller
    obj._normal.feed(bytes.fromhex("6e200a01030301002dcd"))
    obj._normal.feed(bytes.fromhex("6e23018416"))
    sensor = AdjustableBedControllerStateSensor(c, obj.controller_state_sensor_specs[0])
    assert sensor.native_value == "deviceCharacteristicsSubscriptionBoxLockEvent"
    assert obj.choices.events["deviceVersionOneMotorAngleEvent"] == {"position": 1, "angle": 45}
    assert not obj.supports_position_feedback and not obj.snore_available
    with pytest.raises(ValueError, match="not offered"):
        Request("snore_switch", enabled=True).validate(obj)


def test_raw_config_events_and_unreachable_check_dispatch_are_preserved():
    events = []
    receiver = Notifications(lambda name, value: events.append((name, value)), direct_bed=True)
    frame = codec.record_20_len(6, 5, 2, (0, 1, 25))
    receiver.feed(frame)
    assert events == [("deviceAntiSnoreConfigCountEvent", {"raw_frame": list(frame)})]
    receiver.feed(codec.record_20_len(10, 1, 2, (0, 1)))
    assert len(events) == 1


@pytest.fixture
async def public_service(hass, fake_time):
    c = runtime(hass)
    configuration.async_register_goodvibe_services(hass)
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets", return_value=([(c, "both")], [])), patch.object(c, "async_ensure_connected", AsyncMock(return_value=True)), patch.object(c, "_async_refresh_controller_auth", AsyncMock()):
        yield c


async def test_registered_service_uses_real_scheduler_and_exact_alarm_record(hass, public_service):
    c = public_service
    await hass.services.async_call(DOMAIN, "bobpowerbase", {
        "device_id": "bed", "operation": "repeat", "action": "anti_snore", "alarm_id": 3,
        "datetime": datetime(2026, 11, 17, 7, 30, tzinfo=UTC), "weekdays": [0], "enabled": True,
    }, blocking=True)
    assert [call.args[1] for call in c.client.write_gatt_char.await_args_list] == [
        codec.record_20_len(5, 1, 1, (3, 0, 7, 30, 0x46, 0x81)),
    ]


async def test_all_target_validation_precedes_every_control_write(hass, public_service):
    first = public_service
    first.controller._normal.feed(bytes.fromhex("6e0e00037f"))
    second = runtime(hass, product="elite", address="AA:BB:CC:DD:EE:97")
    with patch("custom_components.adjustable_bed.services._resolve_sided_targets", return_value=([(first, "both"), (second, "both")], [])), pytest.raises(ServiceValidationError, match="no light menu"):
        await hass.services.async_call(DOMAIN, "bobpowerbase", {"device_id": ["first", "second"], "operation": "light_color", "rgb_color": [1, 2, 3]}, blocking=True)
    first.client.write_gatt_char.assert_not_awaited()
    second.client.write_gatt_char.assert_not_awaited()


async def test_stop_during_first_lazy_import_invalidates_every_admitted_target(hass, public_service):
    c = public_service

    async def stopped(*args):
        c._command_scheduler._stop_epoch += 1

    with patch.object(configuration, "async_import_modules", stopped), pytest.raises(ServiceValidationError, match="interrupted"):
        await hass.services.async_call(DOMAIN, "bobpowerbase", {"device_id": "bed", "operation": "sync"}, blocking=True)
    c.client.write_gatt_char.assert_not_awaited()
