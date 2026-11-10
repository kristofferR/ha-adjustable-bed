"""Unit132's 100 frozen vectors and app-specific runtime behavior, hardware unverified."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed.beds.builder import BuildContext
from custom_components.adjustable_bed.beds.keeson import jalon as controller
from custom_components.adjustable_bed.beds.keeson.jalon_state import parse_notification
from custom_components.adjustable_bed.const import (
    BED_TYPE_JALON,
    CONF_BED_TYPE,
    CONF_BLE_DEVICE_NAME,
    CONF_MOTOR_COUNT,
    CONF_PRODUCT_TYPE,
)
from custom_components.adjustable_bed.profiles import jalon as app
from custom_components.adjustable_bed.profiles import keeson
from custom_components.adjustable_bed.setup_questions import SETUP_PROFILES
from tests.test_controller_contract import _FactoryCoordinator

VECTORS = json.loads((Path(__file__).parent / "fixtures/jalon/vectors.json").read_text())


@pytest.mark.parametrize("row", VECTORS, ids=lambda row: row["id"])
def test_frozen_vectors(row):
    inputs = row["inputs"]
    profile = app.PROFILES[row["protocol"]]
    kind = inputs["kind"]
    if kind == "ordinary":
        key = {"stop": "stopCommand", "lighting": "lightSwitch"}.get(inputs["key"], inputs["key"])
        result = keeson.encode(profile, app.COMMANDS[key])
    elif kind == "raw":
        result = (
            app.alarm_query(profile)
            if inputs["key"] == "checkAlarm"
            else app.massage_query(profile)
        )
    elif kind == "calibration":
        fields = dict(inputs["parameters"])
        fields.pop("weekday")
        result = app.clock(profile, datetime(**fields))
    elif kind in ("alarm", "alarm_ui"):
        fields = dict(inputs["parameters"])
        fields["wake_type"] = fields.pop("type")
        fields["enabled"] = bool(fields.pop("is_open"))
        if kind == "alarm_ui":
            now = datetime.fromisoformat(fields.pop("now"))
            fields["week"] = app.alarm_week(fields["week"], fields["hour"], fields["minute"], now)
        result = app.alarm(profile, **fields)
    else:
        assert kind == "parse"
        result = bytes.fromhex(inputs["data"])
        parsed = parse_notification(profile.key, result)
        assert parsed is not None
        assert asdict(parsed) == row["expected_decoded"]
    assert result.hex() == row["expected_bytes"]


@pytest.fixture
def bed(monkeypatch):
    coordinator = _FactoryCoordinator()
    coordinator.motor_count = 4
    from tests.state_helpers import state_writer

    coordinator.handle_controller_state_updates = state_writer(coordinator.controller_state)
    ctrl = controller.JalonController(coordinator, protocol="P2", layout="2")
    clock = [0.0]
    writes = []

    async def wait(event, seconds):
        clock[0] += max(0, seconds)

    async def sleep(seconds):
        clock[0] += seconds

    async def write(frame, **kwargs):
        event = kwargs.get("cancel_event", coordinator.cancel_command)
        if not event.is_set():
            writes.append((clock[0], frame, kwargs))

    monkeypatch.setattr(controller, "monotonic_ns", lambda: round(clock[0] * 1_000_000_000))
    monkeypatch.setattr(controller, "_wait_unless_cancelled", wait)
    monkeypatch.setattr(controller.asyncio, "sleep", sleep)
    monkeypatch.setattr(ctrl, "write_command", write)
    return ctrl, coordinator, clock, writes


@pytest.mark.parametrize("layout,axes", app.LAYOUTS.items())
def test_layouts_are_independent_of_protocol(layout, axes):
    for protocol in app.PROFILES:
        coordinator = _FactoryCoordinator()
        coordinator.motor_count = len(axes)
        ctrl = controller.JalonController(coordinator, protocol=protocol, layout=layout)
        assert tuple(spec.key for spec in ctrl.motor_control_specs) == axes
        assert ctrl.supports_single_address_pairing is False
        assert not ctrl.supports_position_feedback
        assert ctrl.execution.hold == "stream"
        assert not ctrl.execution.concurrent


async def test_movement_cancellation_still_sends_both_releases(bed):
    ctrl, coordinator, clock, writes = bed

    async def cancel(event, seconds):
        clock[0] += seconds
        event.set()

    from unittest.mock import patch

    with patch.object(controller, "_wait_unless_cancelled", cancel):
        await ctrl.move_head_up()
    assert [(t, f.hex()) for t, f, _ in writes] == [
        (0, "e6fe16010000000004"),
        (0.3, "e6fe16000000000005"),
        (0.6, "e6fe16000000000005"),
    ]
    assert all(not kw["cancel_event"].is_set() for _, _, kw in writes[1:])


async def test_memory_programs_same_word_for_six_seconds_then_releases(bed):
    ctrl, _, _, writes = bed
    await ctrl.program_memory(1)
    assert len(writes) == 22
    assert [t for t, _, _ in writes[:20]] == pytest.approx([i * 0.3 for i in range(20)])
    assert {f.hex() for _, f, _ in writes[:20]} == {"e6fe16000001000004"}
    assert [t for t, _, _ in writes[-2:]] == pytest.approx([6, 6.3])


async def test_presets_release_at_100ms_and_memory_recall_is_short(bed):
    ctrl, _, clock, writes = bed
    await ctrl.preset_zero_g()
    assert [t for t, _, _ in writes] == pytest.approx([0, 0.1, 0.4])
    writes.clear()
    clock[0] = 0
    await ctrl.preset_memory(2)
    assert [t for t, _, _ in writes] == pytest.approx([0, 0.3, 0.6])


async def test_stop_retries_second_frame_after_first_failure(bed, monkeypatch):
    ctrl, _, _, _ = bed
    write = AsyncMock(side_effect=[BleakError("first"), None])
    monkeypatch.setattr(ctrl, "write_command", write)
    with pytest.raises(BleakError, match="first"):
        await ctrl.stop_all()
    assert write.await_count == 2


async def test_repeated_task_cancellation_cannot_abandon_cleanup(monkeypatch):
    ctrl = controller.JalonController(_FactoryCoordinator(), protocol="P1", layout="0")
    entered = asyncio.Event()
    finish = asyncio.Event()
    writes = []

    async def write(frame, **kwargs):
        writes.append(frame)
        if len(writes) == 1:
            entered.set()
            await finish.wait()

    monkeypatch.setattr(ctrl, "write_command", write)
    task = asyncio.create_task(ctrl.stop_all())
    await entered.wait()
    task.cancel()
    await asyncio.get_running_loop().run_in_executor(None, lambda: None)
    task.cancel()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(writes) == 2


async def test_massage_toggle_effective_single_write_and_gate(bed):
    ctrl, _, _, writes = bed
    with pytest.raises(ValueError, match="turn massage on"):
        await ctrl._massage_action("strengthHeadUp")
    await ctrl.massage_toggle()
    assert [(t, f.hex()) for t, f, _ in writes] == [(0, "e6fe16000100000004"), (0.1, "00000000")]
    ctrl._timer = 2
    await ctrl._massage_action("strengthHeadUp")
    assert writes[-1][1].hex() == "e6fe160008000000fd"


@pytest.mark.parametrize("protocol,count", [("P1", 0), ("P2", 2), ("P3", 3)])
async def test_alarm_capability_and_followup(protocol, count, monkeypatch):
    ctrl = controller.JalonController(_FactoryCoordinator(), protocol=protocol, layout="0")
    write = AsyncMock()
    monkeypatch.setattr(ctrl, "write_command", write)
    monkeypatch.setattr(controller.asyncio, "sleep", AsyncMock())
    if not count:
        with pytest.raises(ValueError):
            await ctrl.configure_clock_alarm(
                enabled=True, weekdays=(1,), hour=6, minute=30, preset="flat"
            )
        write.assert_not_called()
    else:
        await ctrl.configure_clock_alarm(
            enabled=True, weekdays=(7,), hour=6, minute=30, preset="flat"
        )
        assert write.await_count == 2
        assert write.await_args_list[1].kwargs == {"repeat_count": count, "repeat_delay_ms": 350}
        assert write.await_args_list[0].args[0] == app.alarm(
            ctrl.profile,
            hour=6,
            minute=30,
            week=129,
            wake_type=28 if protocol == "P2" else 9,
            enabled=True,
        )


def test_parser_gates_truncation_and_zero_distinctions():
    assert parse_notification("jalon_13", bytes.fromhex("f4fe") + bytes(20)) is None
    assert parse_notification("jalon_15", bytes.fromhex("f4fe") + bytes(19)) is None
    assert parse_notification("jalon_15", bytes.fromhex("edfe")) is None
    assert parse_notification("jalon_24", bytes.fromhex("a50c00000000000000")) is None
    for size in range(15):
        assert parse_notification("jalon_15", (b"\xed\xfe" + bytes(13))[:size]) is None
    status = parse_notification("jalon_15", b"\xed\xfe" + bytes(13))
    assert status is not None and status.headStrength == 1
    status = parse_notification("jalon_24", b"\xa5\x0b" + bytes(7))
    assert status is not None and status.headStrength == 0


@pytest.mark.parametrize(
    "name,ff20,expected",
    [
        ("oKiN-bLe123", False, "jalon_13"),
        ("OKIN-BLE123", True, "jalon_15"),
        ("SmartBed123", False, "jalon_24"),
    ],
)
async def test_live_name_and_service_select_profile(name, ff20, expected):
    coordinator = _FactoryCoordinator()
    coordinator.entry.data[CONF_PRODUCT_TYPE] = "0"
    coordinator.entry.data[CONF_BLE_DEVICE_NAME] = "smartbed stale"
    client = SimpleNamespace(services=MagicMock())
    client.services.get_service.return_value = object() if ff20 else None
    ctrl = await controller.build_controller(
        BuildContext(
            coordinator=coordinator,
            bed_type=BED_TYPE_JALON,
            variant=None,
            client=client,
            device_name=name,
        )
    )
    assert ctrl.profile.key == expected


async def test_exact_gatt_roles_and_write_mode(monkeypatch):
    for protocol in app.PROFILES:
        coordinator = _FactoryCoordinator()
        coordinator.client = MagicMock(is_connected=True)
        ctrl = controller.JalonController(coordinator, protocol=protocol, layout="0")
        writer = AsyncMock()
        monkeypatch.setattr(ctrl, "_write_gatt_with_retry", writer)
        await ctrl.write_command(b"test")
        assert writer.await_args.kwargs["response"] is (protocol == "P1")
        assert (
            writer.await_args.kwargs["characteristic"]
            is coordinator.client.services.get_service.return_value.get_characteristic.return_value
        )


def test_setup_layout_owns_generic_fields():
    profile = SETUP_PROFILES[BED_TYPE_JALON]
    assert profile.derive is not None
    for layout, axes in app.LAYOUTS.items():
        assert profile.derive({CONF_BED_TYPE: BED_TYPE_JALON, CONF_PRODUCT_TYPE: layout})[
            CONF_MOTOR_COUNT
        ] == len(axes)


def test_notifications_publish_all_fields_and_disconnect_clears(bed):
    ctrl, coordinator, _, _ = bed
    ctrl._on_notification(MagicMock(), bytearray.fromhex("edfe00000000000005000000000023"))
    assert coordinator.controller_state[controller.TIMER] == 3
    assert coordinator.controller_state[controller.WAVE] == 2
    assert coordinator.controller_state[controller.HEAD] == 1
    assert coordinator.controller_state[controller.FOOT] == 3
    ctrl._on_notification(MagicMock(), bytearray.fromhex("ed8003061e3e1100000000000000000000"))
    assert coordinator.controller_state[controller.ALARM] == "on"
    assert coordinator.controller_state[controller.WEEK] == 62
    assert coordinator.controller_state[controller.HOUR] == 6
    assert coordinator.controller_state[controller.MINUTE] == 30
    assert coordinator.controller_state[controller.WAKE] == 17
    ctrl.invalidate_diagnostics()
    assert all(coordinator.controller_state[key] is None for key in controller.STATE_KEYS)
    assert ctrl._timer is None


async def test_notification_retry_and_clock_initialization(monkeypatch):
    coordinator = _FactoryCoordinator()
    coordinator.client = MagicMock(is_connected=True)
    coordinator.client.start_notify = AsyncMock(side_effect=[BleakError("retry"), None])
    coordinator.client.stop_notify = AsyncMock()
    ctrl = controller.JalonController(coordinator, protocol="P2", layout="0")
    write = AsyncMock()
    monkeypatch.setattr(ctrl, "write_command", write)
    await ctrl.start_notify()
    assert coordinator.client.start_notify.await_count == 2
    assert coordinator.client.stop_notify.await_count == 1
    await ctrl.async_after_connect(MagicMock())
    assert write.await_args.kwargs == {"repeat_count": 2, "repeat_delay_ms": 300}
    await ctrl.stop_notify()
    assert not ctrl._notifying


def test_app_is_findable_and_advertisement_is_only_a_candidate():
    from custom_components.adjustable_bed.detection import (
        detect_bed_type_detailed,
        get_bed_type_options,
    )

    assert any("OkinComfortBed II" in choice["label"] for choice in get_bed_type_options())
    info = MagicMock(
        name="info", address="AA:BB:CC:DD:EE:FF", service_uuids=[], manufacturer_data={}
    )
    info.name = "sMaRtBeD123"
    info.device.name = "sMaRtBeD123"
    result = detect_bed_type_detailed(info)
    assert result.bed_type == BED_TYPE_JALON
    assert result.confidence < 0.5


async def test_alarm_action_uses_scheduler_and_validates_before_writes(hass):
    from homeassistant.config_entries import ConfigEntryState
    from homeassistant.const import CONF_ADDRESS
    from homeassistant.exceptions import ServiceValidationError
    from homeassistant.helpers import device_registry as dr
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed import services
    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Jalon",
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:32",
            CONF_BED_TYPE: BED_TYPE_JALON,
            CONF_PRODUCT_TYPE: "0",
            CONF_BLE_DEVICE_NAME: "smartbed123",
        },
    )
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._controller = controller.JalonController(coordinator, protocol="P3", layout="0")
    coordinator.async_execute_controller_command = AsyncMock()
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, entry.data[CONF_ADDRESS])}
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await services.async_register_services(hass)
    data = {
        "device_id": [device.id],
        "enabled": True,
        "time": "06:30:00",
        "weekdays": ["mon", "sun"],
        "wake_mode": "memory_1",
    }
    await hass.services.async_call(DOMAIN, "jalon_set_alarm", data, blocking=True)
    coordinator.async_execute_controller_command.assert_awaited_once()
    command = coordinator.async_execute_controller_command.await_args.args[0]
    bed = MagicMock(spec=controller.JalonController)
    bed.configure_clock_alarm = AsyncMock()
    await command(bed)
    bed.configure_clock_alarm.assert_awaited_once_with(
        enabled=True, weekdays=(1, 7), hour=6, minute=30, preset="memory_1"
    )
    coordinator.async_execute_controller_command.reset_mock()
    for invalid in ({**data, "time": "06:30:01"}, {"device_id": [device.id], "enabled": True}):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(DOMAIN, "jalon_set_alarm", invalid, blocking=True)
    coordinator._controller = controller.JalonController(coordinator, protocol="P1", layout="0")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "jalon_set_alarm", data, blocking=True)
    coordinator.async_execute_controller_command.assert_not_awaited()


@pytest.mark.parametrize("layout,axes", app.LAYOUTS.items())
async def test_manual_setup_saves_app_owned_layout(hass, layout, axes):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.const import (
        CONF_DISABLE_ANGLE_SENSING,
        CONF_MOTOR_PULSE_DELAY_MS,
    )
    from tests.form_helpers import finish_new_bed, start_new_bed

    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    result = await start_new_bed(flow, "typed", "jalon", "AA:BB:CC:DD:EE:32")
    assert result["step_id"] == "finish_settings"
    await finish_new_bed(flow, result, {CONF_PRODUCT_TYPE: layout})
    saved = flow._finish_with_verify.await_args.args[0]
    assert saved[CONF_PRODUCT_TYPE] == layout
    assert saved[CONF_MOTOR_COUNT] == len(axes)
    assert saved[CONF_MOTOR_PULSE_DELAY_MS] == 300
    assert saved[CONF_DISABLE_ANGLE_SENSING] is True


@pytest.mark.parametrize(
    "protocol,literal",
    [
        ("P2", "ed8003061e811c0000000000000000ce"),
        ("P3", "07058109061e000100"),
    ],
)
async def test_recurring_sunday_keeps_repeat_marker(protocol, literal, monkeypatch):
    ctrl = controller.JalonController(_FactoryCoordinator(), protocol=protocol, layout="0")
    write = AsyncMock()
    monkeypatch.setattr(ctrl, "write_command", write)
    monkeypatch.setattr(controller.asyncio, "sleep", AsyncMock())
    await ctrl.configure_clock_alarm(enabled=True, weekdays=(7,), hour=6, minute=30, preset="flat")
    assert write.await_args_list[0].args[0].hex() == literal


def test_stop_entity_and_dashboard_stop_are_exposed(hass):
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.button import _button_entities_for
    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ADDRESS: "AA:BB:CC:DD:EE:32", CONF_BED_TYPE: BED_TYPE_JALON}
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    coordinator._controller = controller.JalonController(coordinator, protocol="P3", layout="0")
    assert coordinator.controller.supports_stop_all
    buttons = _button_entities_for(hass, coordinator)
    assert any(
        getattr(button.entity_description, "key", None) == "stop"
        for button in buttons
        if hasattr(button, "entity_description")
    )


@pytest.mark.parametrize(
    "control,duration", [("memory_1", 6000), ("memory_2", 10000), ("flat", 50), ("other", 1000)]
)
async def test_hold_restrictions_are_identical_in_preflight_and_execution(
    control, duration, monkeypatch
):
    ctrl = controller.JalonController(_FactoryCoordinator(), protocol="P3", layout="0")
    hold = AsyncMock()
    monkeypatch.setattr(ctrl, "_hold", hold)
    with pytest.raises(ValueError):
        ctrl.validate_hold_control(control, duration)
    with pytest.raises(ValueError):
        await ctrl.hold_control(control, duration)
    hold.assert_not_awaited()


def test_discovery_candidate_uses_normalized_name_without_device_object():
    from custom_components.adjustable_bed.detection import detect_bed_type_detailed

    for name, expected in (("sMaRtBeD123", BED_TYPE_JALON), ("unrelated", None)):
        info = SimpleNamespace(
            name=name,
            address="AA:BB:CC:DD:EE:FF",
            service_uuids=[],
            manufacturer_data={},
            service_data={},
        )
        assert detect_bed_type_detailed(info).bed_type == expected


def test_entity_translation_keys_follow_home_assistant_contract():
    import re

    ctrl = controller.JalonController(_FactoryCoordinator(), protocol="P3", layout="0")
    translations = json.loads(
        (Path(__file__).parents[1] / "custom_components/adjustable_bed/strings.json").read_text()
    )
    for spec in ctrl.controller_button_specs:
        assert isinstance(spec.translation_key, str)
        assert re.fullmatch(r"[a-z0-9]+(?:[_-][a-z0-9]+)*", spec.translation_key)
        assert spec.translation_key in translations["entity"]["button"]


def test_massage_connection_state_keeps_link_between_commands_by_default():
    from custom_components.adjustable_bed.bed_traits import (
        bed_traits,
        disconnect_after_command_default_enabled,
    )

    traits = bed_traits(BED_TYPE_JALON)
    assert traits.connection_scoped_state
    assert not traits.persistent_connection
    assert not disconnect_after_command_default_enabled(BED_TYPE_JALON)
