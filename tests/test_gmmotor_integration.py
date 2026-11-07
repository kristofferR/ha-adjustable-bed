"""GM Control setup, real scheduler, entity and paired lifecycle contracts."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.gmmotor.controller import GmmotorController
from custom_components.adjustable_bed.beds.gmmotor.desk import GmmotorDeskController
from custom_components.adjustable_bed.beds.gmmotor.notifications import Event
from custom_components.adjustable_bed.beds.gmmotor.requests import Request
from custom_components.adjustable_bed.beds.gmmotor.services import async_register_gmmotor_services
from custom_components.adjustable_bed.beds.gmmotor.sleep import GmmotorSleepController
from custom_components.adjustable_bed.beds.gmmotor.transport import Transport
from custom_components.adjustable_bed.button import ControllerActionButton
from custom_components.adjustable_bed.config_flow import (
    AdjustableBedConfigFlow,
    _name_rule_setup_name,
)
from custom_components.adjustable_bed.const import DOMAIN
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import SingleAddressPairedCoordinator
from custom_components.adjustable_bed.pairing import (
    build_pair_entry_data,
    build_single_address_pair_entry_data,
    effective_child_data,
    supports_single_address_pairing,
)
from custom_components.adjustable_bed.sensor import AdjustableBedControllerStateSensor
from custom_components.adjustable_bed.setup_questions import _gmmotor_errors


def physical(hass, product="6BRM", address="AA:BB:CC:DD:EE:01"):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "address": address,
            "bed_type": "gmmotor",
            "product_type": product,
            "gmmotor_side": "left",
            "disable_angle_sensing": True,
            "disconnect_after_command": False,
        },
    )
    c = AdjustableBedCoordinator(hass, entry)
    c._client = MagicMock(is_connected=True, mtu_size=247)
    c._client.write_gatt_char = AsyncMock()
    ctrl = (
        GmmotorDeskController(c, profile=product)
        if product in ("FWRM", "WFRM")
        else GmmotorController(c, profile=product)
    )
    ctrl._transport = Transport(
        MagicMock(uuid="write", handle=7), (MagicMock(uuid="notify"),), True
    )
    ctrl._pause = AsyncMock(return_value=True)
    c._controller = ctrl
    return c, ctrl


def test_setup_and_single_address_admission_are_exact():
    assert _name_rule_setup_name("gmmotor", "V9RM_RAW") == {"ble_device_name": "V9RM_RAW"}
    assert not _gmmotor_errors({"product_type": "V9RM:1", "gmmotor_side": "right"})
    assert _gmmotor_errors({"product_type": "V9RM:0", "gmmotor_side": "right"})
    assert _gmmotor_errors({"product_type": "QLRN"})
    assert supports_single_address_pairing("gmmotor", product_type="V9RM:1")
    assert not supports_single_address_pairing("gmmotor", product_type="V9RM:0")
    assert not supports_single_address_pairing("gmmotor", product_type="FWRM")


async def test_real_app_step_preserves_raw_name_and_rejects_incompatible_nested_side(hass):
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow._manual_data = {
        "address": "AA:BB:CC:DD:EE:01",
        "bed_type": "gmmotor",
        "ble_device_name": "V9RM-raw",
    }
    result = await flow.async_step_profile_questions()
    assert result["type"] == "form" and result["step_id"] == "profile_questions"
    with patch.object(
        flow, "_finish_with_verify", AsyncMock(return_value={"type": "create_entry"})
    ) as finish:
        result = await flow.async_step_profile_questions({"product_type": "V9RM:0", "gmmotor_side": "right"})
        assert result["errors"] == {"gmmotor_side": "gmmotor_side"}
        finish.assert_not_awaited()
        await flow.async_step_profile_questions({"product_type": "V9RM:1", "gmmotor_side": "right"})
    data = finish.await_args.args[0]
    assert data["product_type"] == "V9RM:1" and data["gmmotor_side"] == "right"
    assert data["ble_device_name"] == "V9RM-raw" and data["disable_angle_sensing"] is True


def test_pair_keeps_exact_product_and_wire_side_per_physical_receiver():
    a = {
        "address": "AA:BB:CC:DD:EE:01",
        "bed_type": "gmmotor",
        "product_type": "6BRM",
        "gmmotor_side": "left",
    }
    b = {
        "address": "AA:BB:CC:DD:EE:02",
        "bed_type": "gmmotor",
        "product_type": "HNRN",
        "gmmotor_side": "right",
    }
    pair = build_pair_entry_data(a, b, name="Pair")
    assert effective_child_data(pair, "left")["product_type"] == "6BRM"
    assert effective_child_data(pair, "right")["product_type"] == "HNRN"
    assert effective_child_data(pair, "right")["gmmotor_side"] == "right"


async def test_service_checks_all_real_products_before_scheduling_any_write(hass):
    async_register_gmmotor_services(hass)
    a, ac = physical(hass, "HNRN")
    b, bc = physical(hass, "6BRM", "AA:BB:CC:DD:EE:02")
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(a, "both"), (b, "both")], []),
        ),
        pytest.raises(ServiceValidationError, match="anti-snore"),
    ):
        await hass.services.async_call(
            DOMAIN,
            "gmmotor",
            {"device_id": ["a", "b"], "operation": "snore_query"},
            blocking=True,
        )
    ac.client.write_gatt_char.assert_not_awaited()
    bc.client.write_gatt_char.assert_not_awaited()


@pytest.mark.parametrize(
    "fields",
    [
        {"operation": "repeat_alarm", "hour": 24},
        {"operation": "sensor_report", "report_date": "2026-02-30"},
        {"operation": "snore_count", "value": True},
        {"operation": "light_color", "rgb_color": [1, 2]},
    ],
)
async def test_invalid_service_input_never_resolves_or_writes(hass, fields):
    async_register_gmmotor_services(hass)
    with (
        patch("custom_components.adjustable_bed.services._resolve_sided_targets") as resolve,
        pytest.raises((vol.Invalid, ServiceValidationError)),
    ):
        await hass.services.async_call(
            DOMAIN, "gmmotor", {"device_id": "a", **fields}, blocking=True
        )
    resolve.assert_not_called()


async def test_real_scheduler_keeps_two_countdown_frames_atomic(hass):
    c, ctrl = physical(hass, "A0RN")
    ctrl._accept(Event("clock_capability"))
    mode = ctrl.profile.alarm_choices[0][0]
    entered, release = asyncio.Event(), asyncio.Event()
    writes = []

    async def write(_characteristic, payload, **_kwargs):
        assert c._command_lock.locked()
        writes.append(bytes(payload))
        if len(writes) == 1:
            entered.set()
            await release.wait()

    c.client.write_gatt_char.side_effect = write
    with patch.object(c, "async_connect", AsyncMock(return_value=True)):
        first = asyncio.create_task(
            c.async_execute_controller_command(
                lambda _: ctrl.async_execute_gmmotor_request(
                    Request("alarm", mode=mode, value=258)
                ),
                cancel_running=False,
                resource="configuration",
            )
        )
        await entered.wait()
        second = asyncio.create_task(
            c.async_execute_controller_command(
                lambda _: ctrl.stop_all(),
                cancel_running=False,
            )
        )
        await asyncio.sleep(0)
        assert len(writes) == 1
        release.set()
        await asyncio.gather(first, second)
    assert len(writes) == 3
    assert writes[0] == bytes.fromhex("6e05020075")
    assert writes[1][1] == 6 and writes[2] == bytes.fromhex("6e01006edd")
    c._cancel_disconnect_timer()


async def test_button_and_sensor_use_production_runtime(hass):
    c, ctrl = physical(hass)
    spec = next(x for x in ctrl.controller_button_specs if x.name == "Head Up")
    button = ControllerActionButton(c, spec)
    sensor = AdjustableBedControllerStateSensor(c, ctrl.controller_state_sensor_specs[0])
    assert button.extra_state_attributes["hold_start_delay_ms"] == 100
    with patch.object(c, "async_connect", AsyncMock(return_value=True)):
        await button.async_press()
    payloads = [x.args[1] for x in c.client.write_gatt_char.await_args_list]
    assert payloads[0] == bytes.fromhex("6e01002493")
    assert payloads[-1] == bytes.fromhex("6e01006edd")
    ctrl._accept(Event("version", {"value": "1.2.3"}))
    assert sensor.native_value == "version"
    assert sensor.extra_state_attributes["gmmotor_events"]["version"] == {"value": "1.2.3"}
    ctrl._accept(Event("sleep_name", [82, 77, 45, 233]))
    assert sensor.extra_state_attributes["gmmotor_sleep_name"] == "RM-é"
    ctrl._accept(Event("sleep_name", [True]))
    assert sensor.extra_state_attributes["gmmotor_sleep_name"] == "RM-é"
    c._cancel_disconnect_timer()


@pytest.mark.parametrize(
    ("product", "key", "packet"),
    [
        ("6DRM", "gm_7", "6e010045b4"),
        ("6DRM", "gm_7_long", "6e010066d5"),
        ("FWRM", "desk_memory_1", "6e01000473"),
    ],
)
async def test_finite_card_buttons_press_the_selected_callback(hass, product, key, packet):
    c, ctrl = physical(hass, product)
    spec = next(x for x in ctrl.controller_button_specs if x.key == key)
    button = ControllerActionButton(c, spec)
    # The card routes entities without held_control to button.press. A 60-second
    # continuous hold would suppress the short callback or select the wrong one.
    assert "held_control" not in button.extra_state_attributes
    with patch.object(c, "async_connect", AsyncMock(return_value=True)):
        await button.async_press()
    c.client.write_gatt_char.assert_awaited_once_with(
        ctrl._transport.write, bytes.fromhex(packet), response=True
    )
    c._cancel_disconnect_timer()


@pytest.mark.parametrize("sxb", [False, True])
async def test_sleep_stop_service_waits_for_the_entire_active_frame(hass, sxb):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "address": "AA:BB:CC:DD:EE:01",
            "bed_type": "gmmotor_sleep_sxb" if sxb else "gmmotor_sleep_mm",
            "disconnect_after_command": False,
        },
    )
    c = AdjustableBedCoordinator(hass, entry)
    c._client = MagicMock(is_connected=True, mtu_size=23)
    ctrl = GmmotorSleepController(c, sxb=sxb)
    ctrl._transport = Transport(MagicMock(uuid="write"), (MagicMock(uuid="notify"),), sxb)
    c._controller = ctrl
    async_register_gmmotor_services(hass)
    entered, release, stop_admitted = asyncio.Event(), asyncio.Event(), asyncio.Event()
    chunks = []
    cancelled = False

    async def write(_characteristic, payload, **_kwargs):
        nonlocal cancelled
        chunks.append(bytes(payload))
        if len(chunks) == 1:
            entered.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                cancelled = True
                raise

    c.client.write_gatt_char = AsyncMock(side_effect=write)
    validate = ctrl.validate_gmmotor_request

    def admit(request):
        validate(request)
        if request.operation == "sensor_stop":
            stop_admitted.set()

    with (
        patch.object(c, "async_connect", AsyncMock(return_value=True)),
        patch.object(ctrl, "validate_gmmotor_request", side_effect=admit),
        patch("custom_components.adjustable_bed.beds.gmmotor.sleep._QUEUE_TICK", 0),
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(c, "both")], []),
        ),
    ):
        first = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "gmmotor",
                {"device_id": "sleep", "operation": "sensor_query_part"},
                blocking=True,
            )
        )
        await entered.wait()
        stop = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "gmmotor",
                {"device_id": "sleep", "operation": "sensor_stop"},
                blocking=True,
            )
        )
        await stop_admitted.wait()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        release.set()
        await asyncio.gather(first, stop)
    assert not cancelled
    assert len(chunks) == 3
    assert b"".join(chunks)[14:] == (
        b'{"id":1,"cmd":"q_part","val":null}' if sxb else b'{"id":1,"cmd":"s_part","val":null}'
    )
    assert ctrl._receive_buffer.command is None
    c._cancel_disconnect_timer()


async def test_single_address_both_uses_two_admitted_frames_and_right_cleanup(hass):
    c, ctrl = physical(hass, "V9RM:1")
    paired_data = build_single_address_pair_entry_data(c.entry.data, name="Split")
    entry = MockConfigEntry(domain=DOMAIN, data=paired_data)
    parent = SingleAddressPairedCoordinator(hass, entry, c)
    assert not parent._single_native_both
    control = next(
        f"gm_{i}"
        for i, a in enumerate(ctrl.profile.controls)
        if a.material.name == "deviceFunctionItemHeadUp"
    )
    with patch.object(c, "async_connect", AsyncMock(return_value=True)):
        await parent.async_execute_controller_command(
            lambda side_ctrl: side_ctrl.hold_control(control, 100), side="both"
        )
    payloads = [x.args[1] for x in c.client.write_gatt_char.await_args_list]
    assert payloads == [
        bytes.fromhex(x) for x in ("6e01002493", "6e01006edd", "6e01012494", "6e01016ede")
    ]
    assert ctrl.command_side is None
    c._cancel_disconnect_timer()
