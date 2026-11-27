"""MLILY discovery, translated admission and diagnostic boundaries through public flows."""

import asyncio
from unittest.mock import AsyncMock

import pytest
import voluptuous as vol
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

from custom_components.adjustable_bed import command_scheduler as scheduler
from custom_components.adjustable_bed import const, sensor
from custom_components.adjustable_bed.beds.casper_base.protocol import Request
from custom_components.adjustable_bed.beds.mlily0.controller import MlilyController
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
from custom_components.adjustable_bed.detection import detect_bed_type_detailed
from custom_components.adjustable_bed.diagnostics import async_get_config_entry_diagnostics
from custom_components.adjustable_bed.profiles.mlily0 import SCAN_KEYWORDS
from tests.alarm_helpers import call_set_alarm
from tests.error_helpers import raises_key
from tests.form_helpers import select_options, suggested
from tests.hold_lease_wire import virtual_clock
from tests.test_mlily0 import make
from tests.test_mlily_remote_ha import runtime, shutdown
from tests.test_shown_state import _running_command


def advertisement(name, services=()):
    return BluetoothServiceInfoBleak.from_scan(
        "test", BLEDevice("AA:BB:CC:DD:EE:98", name, {}),
        AdvertisementData(local_name=name, manufacturer_data={}, service_data={},
                          service_uuids=list(services), tx_power=None, rssi=-50, platform_data=()),
        0, True,
    )


@pytest.mark.parametrize("keyword", SCAN_KEYWORDS)
def test_accepted_scan_keywords_offer_app_without_selecting_product(keyword):
    result = detect_bed_type_detailed(advertisement(f"prefix-{keyword}-suffix"))
    assert "mlily0" in {result.bed_type, *(result.ambiguous_types or ())}
    if result.bed_type == "mlily0":
        assert result.confidence == 0.3
    assert "mlily0" not in {r.bed_type for r in (
        detect_bed_type_detailed(advertisement(f"prefix-{keyword.lower()}-suffix")),
        detect_bed_type_detailed(advertisement(f"Mouse-{keyword}")),
        detect_bed_type_detailed(advertisement("Other device", [codec.TRANSPORTS["n1"].service_uuid])),
    )}  # Name exclusions and shared UUIDs alone cannot establish this app.


def test_shared_name_preserves_a_confident_receiver():
    baseline = detect_bed_type_detailed(advertisement("Test", [const.LINAK_CONTROL_SERVICE_UUID]))
    result = detect_bed_type_detailed(advertisement("prefix-209A-suffix", [const.LINAK_CONTROL_SERVICE_UUID]))
    assert (result.bed_type, result.confidence) == (baseline.bed_type, baseline.confidence)
    assert "mlily0" in result.ambiguous_types


async def test_bluetooth_setup_requires_explicit_product(hass):
    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._async_transport_note = AsyncMock(return_value="")
    result = await flow.async_step_bluetooth(advertisement("prefix-209A-suffix"))
    if result["step_id"] == "bluetooth_disambiguate":
        assert "mlily0" in select_options(result, "bed_type_choice")
        assert suggested(result, "bed_type_choice") is None
        result = await flow.async_step_bluetooth_disambiguate({"bed_type_choice": "mlily0"})
    assert result["step_id"] == "bluetooth_confirm", result
    result = await flow.async_step_bluetooth_confirm({const.CONF_BED_TYPE: "mlily0"})
    assert result["step_id"] == "profile_questions", result
    assert flow._manual_data.get(const.CONF_PROTOCOL_VARIANT) in (None, "auto")
    schema = result["data_schema"]
    assert schema is not None
    with pytest.raises(vol.Invalid):
        schema({})


@pytest.mark.parametrize(("product", "data", "key"), [
    ("bedc", {"weekdays": ["monday"]}, "mlily0_alarm_repeat"),
    ("bedm4", {}, "alarm_not_supported"),
    ("bedc", {"wake_action": "heat"}, "alarm_wake_action_not_supported"),
])
async def test_native_alarm_rejections_keep_translation_key(hass, product, data, key):
    controller, c = make(product)
    await controller.start_notify()
    with raises_key(key):
        await call_set_alarm(hass, controller, {
            "enabled": True, "time": "12:00:00", "wake_action": "memory_1", **data,
        }, bed_type="mlily0")
    c.client.write_gatt_char.assert_not_awaited()
    await controller.stop_notify()


async def test_entities_keep_protocol_state_in_diagnostics(hass, enable_custom_integrations):
    c = runtime(hass)
    link = c.controller._link
    hass.config_entries.async_update_entry(c.entry, data={
        **c.entry.data, const.CONF_BED_TYPE: "mlily0", const.CONF_PROTOCOL_VARIANT: "bedc",
        const.CONF_DISABLE_ANGLE_SENSING: True,
    })
    controller = MlilyController(c, product="bedc")
    c._controller = c._offline_controller = controller
    controller._link = link
    hass.data.setdefault(const.DOMAIN, {})[c.entry.entry_id] = c
    try:
        # Keep meaningful readbacks and unlabelled mode values without adding entities.
        for packet in (codec.record_20_len(3, 1, 2, (0, 1)),
                       codec.record_20_len(2, 1, 2, (1, 4, 2, 6)),
                       codec.record_20_len(2, 2, 2, (0, 99)),
                       codec.record_20_len(4, 1, 2, (0, 18, 52, 86))):
            controller._notification(link, link.rx, bytearray(packet))
        entities = []
        await sensor.async_setup_entry(hass, c.entry, entities.extend)
        assert not any(isinstance(e, sensor.AdjustableBedControllerStateSensor) for e in entities)
        assert not any(str(key).startswith("mlily0_") for key in c.controller_state)
        report = await async_get_config_entry_diagnostics(hass, c.entry)
        state = report["controller"]["protocol_state"]
        assert state["events"]["white_led"] is True
        assert state["events"]["deviceMassageHeadStrengthStatusEvent"] == 4
        assert state["events"]["deviceMassageFootStrengthStatusEvent"] == 6
        assert state["events"]["deviceMassageModeStatusEvent"] == 99
        assert state["events"]["deviceRGBStripColorStatusEvent"] == {"rgba_bytes": [18, 52, 86, 255]}
        assert "product_flags_3c_40_44" in state
        spec = next(s for s in controller.controller_button_specs if s.key.endswith("zerogravity"))
        with controller.side_scope("right"), raises_key("side_not_supported"):
            await ControllerActionButton(c, spec).async_press()
        with raises_key("mlily0_native_actions"):
            controller.validate_casper_base_request(Request("alarm"))
    finally:
        await shutdown(c)


@pytest.mark.parametrize("cleanup", (False, True))
@pytest.mark.parametrize("cancel_caller", (False, True))
async def test_successful_write_is_counted_before_settled_cancellation(cleanup, cancel_caller):
    controller, c = make()
    await controller.start_notify()
    entered, release = asyncio.Event(), asyncio.Event()

    async def write(*args, **kwargs):
        entered.set()
        await release.wait()

    c.client.write_gatt_char.side_effect = write
    command = _running_command(c.cancel_command)
    token = scheduler._CURRENT_COMMAND_CONTEXT.set(command)
    shown = []

    async def operation():
        with scheduler.delivered(shown.append):
            await controller._write(codec.function(0x3C), controller._current(), cleanup=cleanup)

    try:
        with virtual_clock():
            task = asyncio.create_task(operation())
            await entered.wait()
            if cancel_caller:
                task.cancel()
            c.cancel_command.set()
            await asyncio.sleep(0)
            assert not task.done()
            release.set()
            if cancel_caller:
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                await task
        assert shown == [scheduler.Delivery.NONE if cleanup else scheduler.Delivery.SENT]
        assert command.frames_written == (0 if cleanup else 1)
        assert c.client.write_gatt_char.await_count == 1
    finally:
        scheduler._CURRENT_COMMAND_CONTEXT.reset(token)
        await controller.stop_notify()


@pytest.mark.parametrize("stop", ("cancel", "deadline"))
async def test_zero_submissions_report_no_delivery(stop):
    controller, c = make()
    await controller.start_notify()
    command = _running_command(c.cancel_command)
    token = scheduler._CURRENT_COMMAND_CONTEXT.set(command)
    if stop == "cancel":
        c.cancel_command.set()
    shown = []
    try:
        with virtual_clock(), scheduler.delivered(shown.append):
            sent = await controller._write(codec.function(0x3C), controller._current(),
                deadline=-1 if stop == "deadline" else None)
        assert sent is False and shown == [scheduler.Delivery.NONE]
        assert command.frames_written == 0
        c.client.write_gatt_char.assert_not_awaited()
    finally:
        scheduler._CURRENT_COMMAND_CONTEXT.reset(token)
        await controller.stop_notify()
