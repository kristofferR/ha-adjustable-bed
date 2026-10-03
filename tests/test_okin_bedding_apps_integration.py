"""Row 052 setup, entities and services for the Tranquil and Z-Series app profiles."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.adjustable_bed.actuator_groups import get_actuator_group_for_bed_type
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.config_flow import (
    _motor_count_options,
    _normalize_fixed_motor_count,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_DIAGNOSTIC,
    BED_TYPE_TRANQUIL,
    BED_TYPE_ZSERIES_Z230,
    BED_TYPE_ZSERIES_Z280,
    DOMAIN,
    SIDE_BOTH,
    bed_type_has_position_feedback,
    get_motor_pulse_defaults,
    requires_pairing,
)
from custom_components.adjustable_bed.controller_factory import _create_from_registry
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.detection import detect_bed_type, get_bed_type_options
from custom_components.adjustable_bed.sensor import _sensor_entities_for
from custom_components.adjustable_bed.services import async_register_services
from tests.conftest import make_controller_mock
from tests.test_controller_contract import _FactoryCoordinator
from tests.test_malouf_app_entities import configure_entity_runtime
from tests.test_okin_bedding_apps import tranquil, written, zseries

ROOT = Path(__file__).parents[1] / "custom_components" / "adjustable_bed"
LABELS = {
    BED_TYPE_TRANQUIL: ("tranquil", "Jordan's Tranquil app", 2),
    BED_TYPE_ZSERIES_Z230: ("zseries_z230", "Customatic Z-Series app (Z-230)", 1),
    BED_TYPE_ZSERIES_Z280: ("zseries_z280", "Customatic Z-Series app (Z-280)", 2),
}


@pytest.mark.parametrize("bed_type", list(LABELS))
async def test_explicit_profile_is_offline_constructible_and_never_auto_detected(bed_type):
    profile, label, slots = LABELS[bed_type]
    controller = await _create_from_registry(_FactoryCoordinator(), bed_type)
    assert controller is not None
    assert controller.protocol_diagnostics["cst_profile"] == profile
    assert controller.memory_slot_count == slots
    assert get_actuator_group_for_bed_type(bed_type) == ("okin", label)
    assert next(o for o in get_bed_type_options() if o["value"] == bed_type)["label"] == label
    assert _motor_count_options(bed_type) == [2]
    assert _normalize_fixed_motor_count(bed_type, "auto", 4) == 2
    assert get_motor_pulse_defaults(bed_type) == (10, 100)
    assert not requires_pairing(bed_type)
    assert not bed_type_has_position_feedback(bed_type, "auto")
    for name in ("OKIN", "OKIN-003444", "okin example"):
        info = MagicMock()
        info.name = name
        info.address = "AA:BB:CC:DD:EE:FF"
        info.service_uuids = ["62741523-52f9-8864-b1ab-3b3a8d65950b"]
        info.manufacturer_data = {}
        assert detect_bed_type(info) != bed_type


@pytest.mark.parametrize("bed_type", list(LABELS))
async def test_setup_hides_fixed_layout_and_refresh_delay(hass, bed_type):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.const import CONF_MOTOR_COUNT, CONF_MOTOR_PULSE_DELAY_MS

    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._selected_bed_type = bed_type
    flow._disambiguated_bed_type = bed_type
    info = MagicMock()
    info.name = "OKIN-003444"
    info.address = "AA:BB:CC:DD:EE:FF"
    info.service_uuids = ["62741523-52f9-8864-b1ab-3b3a8d65950b"]
    info.manufacturer_data = {}
    info.source = "auto"
    flow._discovery_info = info
    flow._async_transport_note = AsyncMock(return_value="")
    form = await flow.async_step_manual_entry()
    markers = {marker.schema for marker in form["data_schema"].schema}
    assert CONF_MOTOR_COUNT not in markers
    assert CONF_MOTOR_PULSE_DELAY_MS not in markers


@pytest.mark.parametrize(
    ("factory", "bed_type", "prefix"),
    [(tranquil, BED_TYPE_TRANQUIL, "tranquil"), (lambda: zseries("z280"), BED_TYPE_ZSERIES_Z280, "zseries")],
)
async def test_profile_change_retires_previous_app_buttons_and_sensors(hass, factory, bed_type, prefix):
    runtime = configure_entity_runtime(hass, factory(), bed_type)
    registry = er.async_get(hass)
    stale = [
        registry.async_get_or_create("button", DOMAIN, "bed_serenity_save_tv_left", config_entry=runtime.entry),
        registry.async_get_or_create("sensor", DOMAIN, "bed_serenity_status_code_left", config_entry=runtime.entry),
    ]
    buttons = {entity.unique_id for entity in _button_entities_for(hass, runtime)}
    sensors = {entity.unique_id for entity in _sensor_entities_for(hass, runtime)}
    assert all(registry.async_get(row.entity_id) is None for row in stale)
    assert f"bed_{prefix}_save_zero_g_left" in buttons
    assert f"bed_{prefix}_status_code_left" in sensors
    # Moving away from the app profile removes its namespace again.
    retired = configure_entity_runtime(
        hass,
        make_controller_mock(
            controller_button_specs=(),
            controller_state_sensor_specs=(),
            stale_controller_state_sensor_entity_keys=frozenset(),
            position_number_specs=(),
        ),
        BED_TYPE_DIAGNOSTIC,
    )
    kept = [
        registry.async_get_or_create("button", DOMAIN, f"bed_{prefix}_save_zero_g_left", config_entry=retired.entry),
        registry.async_get_or_create("sensor", DOMAIN, f"bed_{prefix}_status_code_left", config_entry=retired.entry),
    ]
    _button_entities_for(hass, retired)
    _sensor_entities_for(hass, retired)
    assert all(registry.async_get(row.entity_id) is None for row in kept)


@pytest.mark.parametrize(("factory", "has_switch"), [(tranquil, True), (lambda: zseries("z230"), False)])
async def test_discrete_light_switch_only_where_the_app_has_on_off(hass, factory, has_switch):
    from custom_components.adjustable_bed.switch import _switch_entities_for

    controller = factory()
    bed_type = BED_TYPE_TRANQUIL if has_switch else BED_TYPE_ZSERIES_Z230
    runtime = configure_entity_runtime(hass, controller, bed_type)
    runtime.bed_type = bed_type
    switches = [
        switch for switch in _switch_entities_for(hass, runtime)
        if switch.entity_description.key == "under_bed_lights"
    ]
    assert bool(switches) is has_switch
    if switches:
        assert switches[0].is_on is None and switches[0].assumed_state is True


def _target(bed_type, controller):
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.name = "Bed"
    coordinator.bed_type = bed_type
    coordinator.entry = SimpleNamespace(data={})
    coordinator.capability_controller = controller
    coordinator.controller = controller  # Live controller once connected.
    coordinator.is_connected = True
    coordinator.async_ensure_connected = AsyncMock(return_value=True)

    async def execute(command, **kwargs):
        await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    return coordinator


@pytest.mark.parametrize(
    ("service", "bed_type", "factory", "control", "error"),
    [
        ("hold_control", BED_TYPE_TRANQUIL, tranquil, "save_lounge", None),
        ("hold_control", BED_TYPE_ZSERIES_Z230, lambda: zseries("z230"), "head_foot_up", None),
        ("hold_control", BED_TYPE_ZSERIES_Z230, lambda: zseries("z230"), "memory_2", "does not support held control"),
    ],
)
async def test_hold_services_preflight_profile_and_literal_action(
    hass, service, bed_type, factory, control, error
):
    await async_register_services(hass)
    controller = factory()
    controller.hold_control = AsyncMock()
    coordinator = _target(bed_type, controller)
    data = {"device_id": "bed", "control": control, "duration": 1.5}
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(coordinator, SIDE_BOTH)], []),
    ):
        if error:
            with pytest.raises(ServiceValidationError, match=error):
                await hass.services.async_call(DOMAIN, service, data, blocking=True)
            coordinator.async_execute_controller_command.assert_not_awaited()
        else:
            await hass.services.async_call(DOMAIN, service, data, blocking=True)
            controller.hold_control.assert_awaited_once_with(control, 1500)


@pytest.mark.parametrize(
    ("bed_type", "available", "error"),
    [
        (BED_TYPE_ZSERIES_Z280, True, None),
        (BED_TYPE_ZSERIES_Z280, False, "does not support"),
        (BED_TYPE_TRANQUIL, True, "not a Customatic Z-Series"),
    ],
)
async def test_alarm_service_requires_zseries_and_manufacturer_enabled_page(
    hass, bed_type, available, error
):
    await async_register_services(hass)
    controller = zseries("z280")
    controller._alarm_available = available
    coordinator = _target(bed_type, controller)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coordinator, SIDE_BOTH)], []),
        ),
        patch("asyncio.sleep", new=AsyncMock()),
        patch(
            "custom_components.adjustable_bed.beds.serenity.dt_util.now",
            return_value=datetime(2026, 10, 1, 13, 47, 59),
        ),
    ):
        data = {"device_id": "bed", "enabled": True, "time": "07:45:00", "wake_mode": "memory_1"}
        if error:
            with pytest.raises(ServiceValidationError, match=error):
                await hass.services.async_call(DOMAIN, "zseries_set_alarm", data, blocking=True)
            assert written(controller) == []
            return
        with pytest.raises(ServiceValidationError, match="wake-up mode"):
            await hass.services.async_call(
                DOMAIN,
                "zseries_set_alarm",
                {key: value for key, value in data.items() if key != "wake_mode"},
                blocking=True,
            )
        assert written(controller) == []
        await hass.services.async_call(DOMAIN, "zseries_set_alarm", data, blocking=True)
        await hass.services.async_call(DOMAIN, "sync_clock", {"device_id": "bed"}, blocking=True)
    clock = "07061a0a01040d2f3b"
    assert written(controller) == [
        clock, "07052002072d000101", "00c0", "00c0", clock, "00c0", "00c0"
    ]
    assert coordinator.async_execute_controller_command.await_args.kwargs["cancel_running"]


def test_state_sensor_translations_match_controller_catalogs():
    for filename in ("strings.json", "translations/en.json"):
        metadata = json.loads((ROOT / filename).read_text())
        for prefix in ("tranquil", "zseries"):
            for spec in (tranquil() if prefix == "tranquil" else zseries("z280")).controller_state_sensor_specs:
                assert spec.translation_key in metadata["entity"]["sensor"]


@pytest.mark.parametrize("bed_type", list(LABELS))
async def test_options_switch_from_generic_okin_profile_applies_fixed_defaults(hass, bed_type):
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
    from custom_components.adjustable_bed.const import (
        BED_TYPE_OKIN_CST,
        CONF_BED_TYPE,
        CONF_DISABLE_ANGLE_SENSING,
        CONF_MOTOR_COUNT,
        CONF_MOTOR_PULSE_COUNT,
        CONF_MOTOR_PULSE_DELAY_MS,
        CONF_PROTOCOL_VARIANT,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: "AA:BB:CC:DD:EE:FF",
            CONF_BED_TYPE: BED_TYPE_OKIN_CST,
            CONF_MOTOR_COUNT: 4,
            CONF_PROTOCOL_VARIANT: "cst_support",
            CONF_MOTOR_PULSE_COUNT: 7,
            CONF_MOTOR_PULSE_DELAY_MS: 150,
        },
    )
    entry.add_to_hass(hass)
    flow = AdjustableBedOptionsFlow(entry)
    flow.hass = hass
    flow.handler = entry.entry_id
    rebuilt = await flow._async_options_form({CONF_BED_TYPE: bed_type}, step_id="settings")
    markers = {marker.schema for marker in rebuilt["data_schema"].schema}
    assert CONF_MOTOR_COUNT not in markers and CONF_MOTOR_PULSE_DELAY_MS not in markers
    saved = await flow._async_options_form({CONF_BED_TYPE: bed_type}, step_id="settings")
    assert saved["type"] == "create_entry"
    assert entry.data[CONF_BED_TYPE] == bed_type
    assert entry.data[CONF_MOTOR_COUNT] == 2
    assert (entry.data[CONF_MOTOR_PULSE_COUNT], entry.data[CONF_MOTOR_PULSE_DELAY_MS]) == (10, 100)
    assert entry.data[CONF_DISABLE_ANGLE_SENSING] is True


@pytest.mark.parametrize(("count", "error"), [("0", True), ("601", True), ("1", False), ("600", False)])
async def test_zseries_pulse_count_range_is_validated_in_setup_and_options(hass, count, error):
    from homeassistant.const import CONF_ADDRESS, CONF_NAME
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed.config_flow import (
        AdjustableBedConfigFlow,
        AdjustableBedOptionsFlow,
        _invalid_pulse_count,
    )
    from custom_components.adjustable_bed.const import CONF_BED_TYPE, CONF_MOTOR_PULSE_COUNT

    assert _invalid_pulse_count(BED_TYPE_ZSERIES_Z230, int(count)) is error
    assert not _invalid_pulse_count(BED_TYPE_TRANQUIL, int(count))  # Other profiles unchanged.

    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._selected_bed_type = BED_TYPE_ZSERIES_Z230
    flow._disambiguated_bed_type = BED_TYPE_ZSERIES_Z230
    info = MagicMock()
    info.name = "OKIN-003444"
    info.address = "AA:BB:CC:DD:EE:FF"
    info.service_uuids = ["62741523-52f9-8864-b1ab-3b3a8d65950b"]
    info.manufacturer_data = {}
    info.source = "auto"
    flow._discovery_info = info
    flow._async_transport_note = AsyncMock(return_value="")
    if error:
        form = await flow.async_step_bluetooth_confirm(
            {CONF_BED_TYPE: BED_TYPE_ZSERIES_Z230, CONF_NAME: "Bed", CONF_MOTOR_PULSE_COUNT: count}
        )
        assert form["type"] == "form"
        assert form["errors"][CONF_MOTOR_PULSE_COUNT] == "invalid_pulse_count_range"

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ADDRESS: "AA:BB:CC:DD:EE:FF", CONF_BED_TYPE: BED_TYPE_ZSERIES_Z230},
    )
    entry.add_to_hass(hass)
    options = AdjustableBedOptionsFlow(entry)
    options.hass = hass
    options.handler = entry.entry_id
    result = await options._async_options_form(
        {CONF_BED_TYPE: BED_TYPE_ZSERIES_Z230, CONF_MOTOR_PULSE_COUNT: count}, step_id="settings"
    )
    if error:
        assert result["errors"] == {CONF_MOTOR_PULSE_COUNT: "invalid_pulse_count_range"}
    else:
        assert result["type"] == "create_entry"
        assert entry.data[CONF_MOTOR_PULSE_COUNT] == int(count)


async def test_enabling_alarm_requires_time_and_clearing_does_not(hass):
    await async_register_services(hass)
    controller = zseries("z230")
    controller._alarm_available = True
    coordinator = _target(BED_TYPE_ZSERIES_Z230, controller)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coordinator, SIDE_BOTH)], []),
        ),
        patch("asyncio.sleep", new=AsyncMock()),
        patch(
            "custom_components.adjustable_bed.beds.serenity.dt_util.now",
            return_value=datetime(2026, 10, 1, 13, 47, 59),
        ),
    ):
        with pytest.raises(ServiceValidationError) as raised:
            await hass.services.async_call(
                DOMAIN,
                "zseries_set_alarm",
                {"device_id": "bed", "enabled": True, "wake_mode": "massage"},
                blocking=True,
            )
        assert raised.value.translation_key == "zseries_alarm_time_required"
        assert written(controller) == []
        await hass.services.async_call(
            DOMAIN, "zseries_set_alarm", {"device_id": "bed", "enabled": False}, blocking=True
        )
    assert written(controller) == ["07061a0a01040d2f3b", "070500000000000001", "00c0", "00c0"]


def _persisting(controller, data: dict):
    """Give a controller a real per-entry store, like the coordinator's internal update."""
    coordinator = controller._coordinator
    coordinator.entry = SimpleNamespace(data=dict(data))

    def persist(new_data, *, keys=None):
        coordinator.entry.data = dict(new_data)

    coordinator._async_persist_config = MagicMock(side_effect=persist)
    coordinator._begin_internal_entry_update = MagicMock()
    return coordinator


async def _set_alarm(hass, controller):
    await async_register_services(hass)
    target = _target(BED_TYPE_ZSERIES_Z280, controller)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(target, SIDE_BOTH)], []),
        ),
        patch("asyncio.sleep", new=AsyncMock()),
        patch(
            "custom_components.adjustable_bed.beds.serenity.dt_util.now",
            return_value=datetime(2026, 10, 1, 13, 47, 59),
        ),
    ):
        await hass.services.async_call(
            DOMAIN,
            "zseries_set_alarm",
            {"device_id": "bed", "enabled": True, "time": "07:45:00", "wake_mode": "massage"},
            blocking=True,
        )


async def test_failed_setup_read_is_retried_before_the_alarm_and_then_persisted(hass):
    controller = zseries("z280")
    coordinator = _persisting(controller, {})
    controller.client.read_gatt_char.side_effect = [TimeoutError("setup read"), b"CST13"]
    with patch("asyncio.sleep", new=AsyncMock()):
        await controller.start_notify()
    assert controller.alarm_state is None  # Unknown, not "no alarm page".
    assert not controller.supports_clock_alarm and controller.alarm_not_ruled_out
    await _set_alarm(hass, controller)
    assert controller.client.read_gatt_char.await_count == 2
    assert written(controller)[1] == "07052001072d000101"
    assert coordinator.entry.data["zseries_alarm_available"] is True
    coordinator._begin_internal_entry_update.assert_called_once_with(False)


async def test_persisted_capability_survives_disconnect_and_a_later_failed_read(hass):
    first = zseries("z280")
    store = _persisting(first, {})
    with patch("asyncio.sleep", new=AsyncMock()):
        await first.start_notify()  # CST13
    # Reconnect: a new controller for the same entry, whose own read fails.
    second = zseries("z280")
    _persisting(second, store.entry.data)
    second.client.read_gatt_char.side_effect = TimeoutError("flaky")
    with patch("asyncio.sleep", new=AsyncMock()):
        await second.start_notify()
    assert second.supports_clock_alarm and second.alarm_state is True
    await _set_alarm(hass, second)
    assert second.client.read_gatt_char.await_count == 1  # No extra read needed.
    assert written(second)[1] == "07052001072d000101"


async def test_confirmed_other_manufacturer_is_rejected_without_reconnecting(hass):
    controller = zseries("z280")
    _persisting(controller, {"zseries_alarm_available": False})
    with pytest.raises(ServiceValidationError, match="does not support"):
        await _set_alarm(hass, controller)
    controller.client.read_gatt_char.assert_not_awaited()
    assert written(controller) == []


async def test_unknown_state_that_cannot_be_read_fails_without_writing(hass):
    controller = zseries("z280")
    _persisting(controller, {})
    controller.client.read_gatt_char.side_effect = TimeoutError("still unreadable")
    with pytest.raises(ServiceValidationError, match="Could not read the manufacturer"):
        await _set_alarm(hass, controller)
    assert written(controller) == []


def _known_and_unknown(second_read):
    """First bed is a confirmed CST13 bed; the second has never been read."""
    first = zseries("z280")
    _persisting(first, {"zseries_alarm_available": True})
    second = zseries("z280")
    _persisting(second, {})
    second.client.read_gatt_char.side_effect = second_read
    return first, second


def _paired(first, second):
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    children = {"left": _target(BED_TYPE_ZSERIES_Z280, first), "right": _target(BED_TYPE_ZSERIES_Z280, second)}
    paired = MagicMock(spec=PairedBedCoordinator)
    paired.name = "Pair"
    paired.children = children

    async def execute(command, *, side, **kwargs):
        for child in children.values():
            await command(child.controller)

    paired.async_execute_controller_command = AsyncMock(side_effect=execute)
    return paired, [(paired, SIDE_BOTH)], list(children.values())


def _two_devices(first, second):
    targets = [_target(BED_TYPE_ZSERIES_Z280, first), _target(BED_TYPE_ZSERIES_Z280, second)]
    return None, [(target, SIDE_BOTH) for target in targets], targets


async def _call(hass, resolved, service="zseries_set_alarm"):
    await async_register_services(hass)
    data = {"device_id": ["a", "b"]}
    if service == "zseries_set_alarm":
        data |= {"enabled": True, "time": "07:45:00", "wake_mode": "massage"}
    with (
        patch("custom_components.adjustable_bed.services._resolve_sided_targets", return_value=(resolved, [])),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        await hass.services.async_call(DOMAIN, service, data, blocking=True)


@pytest.mark.parametrize("layout", [_two_devices, _paired])
@pytest.mark.parametrize("service", ["zseries_set_alarm", "sync_clock"])
@pytest.mark.parametrize(
    ("second_read", "error"),
    [([b"CST20"], "does not support"), (TimeoutError("unreadable"), "Could not read")],
)
async def test_unknown_later_target_is_resolved_before_any_bed_is_written(
    hass, layout, service, second_read, error
):
    first, second = _known_and_unknown(second_read)
    _, resolved, children = layout(first, second)
    with pytest.raises(ServiceValidationError, match=error):
        await _call(hass, resolved, service)
    assert written(first) == [] and written(second) == []
    second.client.read_gatt_char.assert_awaited()
    first.client.read_gatt_char.assert_not_awaited()  # Confirmed state needs no read.
    # The bed connected for validation gets its normal idle release.
    children[1].async_ensure_connected.assert_any_await(reset_timer=True)
    if second_read == [b"CST20"]:
        assert second._coordinator.entry.data["zseries_alarm_available"] is False


@pytest.mark.parametrize("layout", [_two_devices, _paired])
async def test_unknown_later_cst_target_is_resolved_then_both_beds_are_written(hass, layout):
    first, second = _known_and_unknown([b"CST14"])
    _, resolved, _children = layout(first, second)
    await _call(hass, resolved, "sync_clock")
    assert written(first)[1:] == ["00c0", "00c0"] and written(second)[1:] == ["00c0", "00c0"]
    assert second._coordinator.entry.data["zseries_alarm_available"] is True


@pytest.mark.parametrize("layout", [_two_devices, _paired])
async def test_cancelled_resolution_writes_nothing_and_releases_connected_beds(hass, layout):
    blocked = asyncio.Event()

    async def hang(*args, **kwargs):
        blocked.set()
        await asyncio.Event().wait()

    first, second = _known_and_unknown(hang)
    _, resolved, children = layout(first, second)
    task = asyncio.create_task(_call(hass, resolved))
    await blocked.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert written(first) == [] and written(second) == []
    children[1].async_ensure_connected.assert_any_await(reset_timer=True)


class _OneSlotChild:
    """A side on a one-slot Bluetooth path: a second simultaneous link fails."""

    slot: list[_OneSlotChild] = []

    def __init__(self, name: str, store: dict) -> None:
        self.name = name
        self.bed_type = BED_TYPE_ZSERIES_Z280
        self.live = zseries("z280")
        _persisting(self.live, store)
        self.entry = self.live._coordinator.entry
        # The cached offline controller is a separate, stale instance for the same entry.
        self.capability_controller = zseries("z280")
        self.capability_controller._coordinator.entry = self.entry
        self.disconnects: list[str] = []

    @property
    def is_connected(self) -> bool:
        return self in self.slot

    @property
    def controller(self):
        return self.live if self.is_connected else None

    async def async_ensure_connected(self, reset_timer: bool = True) -> bool:
        if self.slot and self.slot[0] is not self:
            return False  # The one Bluetooth slot is held by the other side.
        if not self.slot:
            self.slot.append(self)
        return True

    async def async_disconnect(self, reason: str = "intentional", **kwargs) -> bool:
        self.disconnects.append(reason)
        if self in self.slot:
            self.slot.remove(self)
        return True


@pytest.mark.parametrize("paired", [False, True])
async def test_capability_probe_releases_each_link_on_a_one_slot_path(hass, paired):
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator

    _OneSlotChild.slot = []
    left, right = _OneSlotChild("Left", {}), _OneSlotChild("Right", {})

    async def run(child, command):
        assert await child.async_ensure_connected()
        try:
            await command(child.controller)
        finally:
            await child.async_disconnect("sequential_switch")

    if paired:
        pair = MagicMock(spec=PairedBedCoordinator)
        pair.name = "Pair"
        pair.children = {"left": left, "right": right}

        async def execute(command, *, side, **kwargs):
            for child in (left, right):  # Sequential mode: one link at a time.
                await run(child, command)

        pair.async_execute_controller_command = AsyncMock(side_effect=execute)
        resolved = [(pair, SIDE_BOTH)]
    else:
        def executor(child):
            async def execute(command, **kwargs):
                await run(child, command)

            return execute

        for child in (left, right):
            child.async_execute_controller_command = AsyncMock(side_effect=executor(child))
        resolved = [(left, SIDE_BOTH), (right, SIDE_BOTH)]
    with patch(
        "custom_components.adjustable_bed.services._command_targets",
        side_effect=lambda coordinator, side: list(coordinator.children.values())
        if paired
        else [coordinator],
    ):
        await _call(hass, resolved, "sync_clock")
    for child in (left, right):
        assert child.disconnects[0] == "capability_probe"
        assert child.entry.data["zseries_alarm_available"] is True
        assert [frame for frame in written(child.live) if frame != "00c0"][0].startswith("0706")
    assert _OneSlotChild.slot == []


async def test_pair_profile_changes_to_or_from_these_apps_require_unpair(hass):
    from homeassistant.const import CONF_ADDRESS
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.adjustable_bed.config_flow import AdjustableBedOptionsFlow
    from custom_components.adjustable_bed.const import (
        BED_TYPE_OKIN_CST,
        CONF_BED_TYPE,
        CONF_MOTOR_COUNT,
        CONF_MOTOR_PULSE_COUNT,
        CONF_PAIR_CHILDREN,
    )
    from custom_components.adjustable_bed.pairing import build_pair_entry_data

    cases = [
        # (left type, right type, requested type, refused)
        (BED_TYPE_OKIN_CST, BED_TYPE_OKIN_CST, BED_TYPE_TRANQUIL, True),
        (BED_TYPE_ZSERIES_Z230, BED_TYPE_ZSERIES_Z230, BED_TYPE_ZSERIES_Z280, True),
        (BED_TYPE_ZSERIES_Z280, BED_TYPE_ZSERIES_Z280, BED_TYPE_OKIN_CST, True),
        (BED_TYPE_TRANQUIL, BED_TYPE_ZSERIES_Z280, BED_TYPE_TRANQUIL, True),  # Mixed pair.
        (BED_TYPE_OKIN_CST, BED_TYPE_ZSERIES_Z230, BED_TYPE_OKIN_CST, True),  # Mixed pair.
        (BED_TYPE_TRANQUIL, BED_TYPE_TRANQUIL, BED_TYPE_TRANQUIL, False),  # Same type kept.
    ]
    for index, (left_type, right_type, requested, refused) in enumerate(cases):
        left = {CONF_ADDRESS: f"11:22:33:44:55:{index:02d}", CONF_BED_TYPE: left_type, CONF_MOTOR_COUNT: 2}
        right = {**left, CONF_ADDRESS: f"11:22:33:44:66:{index:02d}", CONF_BED_TYPE: right_type}
        entry = MockConfigEntry(domain=DOMAIN, data=build_pair_entry_data(left, right, name="Pair"))
        entry.add_to_hass(hass)
        children = [dict(child) for child in entry.data[CONF_PAIR_CHILDREN]]
        flow = AdjustableBedOptionsFlow(entry)
        flow.handler = entry.entry_id
        flow.hass = hass
        result = await flow.async_step_settings(
            {CONF_BED_TYPE: requested, CONF_MOTOR_PULSE_COUNT: "10"}
        )
        if refused:
            assert result["errors"] == {CONF_BED_TYPE: "okin_bedding_app_unpair_first"}, cases[index]
            assert [dict(child) for child in entry.data[CONF_PAIR_CHILDREN]] == children
        else:
            assert result.get("errors") != {CONF_BED_TYPE: "okin_bedding_app_unpair_first"}
