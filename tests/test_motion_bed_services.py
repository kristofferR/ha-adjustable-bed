"""Registered Motion Bed schemas, source builders and all-target preflight."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TypedDict, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed import _async_ensure_paired_device_registry
from custom_components.adjustable_bed.beds.base import BedController
from custom_components.adjustable_bed.beds.motion_bed import MotionBedController
from custom_components.adjustable_bed.const import BED_TYPE_MOTION_BED, DOMAIN, SIDE_BOTH
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.motion_bed_models import select_motion_bed
from custom_components.adjustable_bed.motion_bed_services import build_motion_bed_request
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.paired_devices import async_register_children
from custom_components.adjustable_bed.services import async_register_services


@dataclass
class Target:
    coordinator: MagicMock
    controller: MotionBedController
    client: MagicMock
    entry: MockConfigEntry

    @property
    def writes(self) -> list[bytes]:
        return [call.args[1] for call in self.client.write_gatt_char.await_args_list]


def make_target(
    hass: HomeAssistant,
    name: str = "QMS4",
    *,
    address: str = "01:23:45:67:89:AB",
    audio: bool = True,
) -> Target:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=name,
        data={"address": address, "bed_type": BED_TYPE_MOTION_BED, "name": name},
    )
    entry.add_to_hass(hass)
    coordinator = MagicMock(spec=AdjustableBedCoordinator)
    coordinator.address = address
    coordinator.name = name
    coordinator.entry = entry
    coordinator.bed_type = BED_TYPE_MOTION_BED
    coordinator.cancel_command = asyncio.Event()
    coordinator.update_state = MagicMock()
    coordinator.record_command_trace = MagicMock()
    client = MagicMock()
    client.is_connected = True
    client.write_gatt_char = AsyncMock()
    coordinator.client = client
    controller = MotionBedController(coordinator, selection=select_motion_bed(name))
    controller._state = replace(
        controller._state,
        audio_available=audio,
        motor_module_present=True,
        air_module_present=True,
        thermal_module_present=True,
    )
    characteristic = MagicMock()
    characteristic.properties = ("write", "notify")
    characteristic.handle = 7
    controller._session_client = client
    controller._characteristic = characteristic
    coordinator.controller = controller
    coordinator.capability_controller = controller
    coordinator.device_info = {"identifiers": {(DOMAIN, address)}, "name": name}

    async def execute(
        command: Callable[[BedController], Awaitable[None]], **_kwargs: object
    ) -> None:
        await command(controller)

    coordinator.async_execute_controller_command = AsyncMock(side_effect=execute)
    return Target(coordinator, controller, client, entry)


async def invoke(
    hass: HomeAssistant, targets: list[Target], service: str, data: dict[str, object]
) -> None:
    await async_register_services(hass)
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(target.coordinator, SIDE_BOTH) for target in targets], []),
    ):
        await hass.services.async_call(DOMAIN, service, {"device_id": "bed", **data}, blocking=True)


_VALID_PUBLIC_CASES: tuple[tuple[str, str, dict[str, object]], ...] = (
    ("motion_bed_action", "QMS4", {"action": "home_activity_bed_status"}),
    (
        "motion_bed_alarm",
        "QMS4",
        {"enabled": True, "hour": 6, "minute": 30, "audio": True, "confirmed": True},
    ),
    ("motion_bed_clock", "QMS4", {"timestamp": "2026-09-30T07:45:00"}),
    (
        "motion_bed_sleep_angles",
        "QMS4",
        {"page": 4, "flat": [1, 2, 3, 4], "side_positions": [5, 6, 7, 8], "confirmed": True},
    ),
    ("motion_bed_calibration", "QMS4", {"flat": 10, "side_position": 140, "confirmed": True}),
    ("motion_bed_sleep_timer", "QMS4", {"slot": 8, "confirmed": True}),
    ("motion_bed_sleep_report", "QMS4", {"kind": "day", "offset": 29}),
    (
        "motion_bed_module",
        "TL-Q",
        {
            "operation": "bind",
            "module_type": 0x0A,
            "address": "01:23:45:67:89:AB",
            "confirmed": True,
        },
    ),
    ("motion_bed_air_setting", "TL-A", {"mode": 3, "gear": 8, "timer": 2, "confirmed": True}),
    ("motion_bed_pressure", "TL-A", {"operation": "save", "values": [9] * 12, "confirmed": True}),
    (
        "motion_bed_thermal_schedule",
        "TL-W",
        {"hour": 21, "minute": 30, "mode": 1, "gear": 4, "confirmed": True},
    ),
    ("motion_bed_audio", "QMS4", {"operation": "track", "value": 5}),
)


@pytest.mark.parametrize("service, profile, data", _VALID_PUBLIC_CASES)
async def test_every_registered_public_action_validates_and_dispatches(
    hass: HomeAssistant, service: str, profile: str, data: dict[str, object]
) -> None:
    target = make_target(hass, profile)
    with patch.object(target.controller, "_spawn"):
        await invoke(hass, [target], service, data)
    assert target.writes
    target.coordinator.async_execute_controller_command.assert_awaited_once()
    assert target.coordinator.async_execute_controller_command.await_args.kwargs["resource"] == "*"


async def test_exact_ble_action_schemas_are_registered(hass: HomeAssistant) -> None:
    await async_register_services(hass)
    registered = hass.services.async_services()[DOMAIN]
    assert {name for name in registered if name.startswith("motion_bed_")} == {
        name for name, _, _ in _VALID_PUBLIC_CASES
    }


@pytest.mark.parametrize(
    "service, profile, data", [case for case in _VALID_PUBLIC_CASES if case[2].get("confirmed")]
)
async def test_persistent_public_changes_require_explicit_confirmation_before_io(
    hass: HomeAssistant, service: str, profile: str, data: dict[str, object]
) -> None:
    target = make_target(hass, profile)
    with pytest.raises(ServiceValidationError, match="Confirm"):
        await invoke(hass, [target], service, {**data, "confirmed": False})
    assert not target.writes
    target.coordinator.async_execute_controller_command.assert_not_awaited()


@pytest.mark.parametrize("operation", ("bind", "delete"))
async def test_module_rebinding_and_deletion_are_confirmed(
    hass: HomeAssistant, operation: str
) -> None:
    target = make_target(hass, "TL-Q")
    data: dict[str, object] = {
        "operation": operation,
        "module_type": 0x0A,
        "address": "01:23:45:67:89:AB",
    }
    with pytest.raises(ServiceValidationError, match="Confirm"):
        await invoke(hass, [target], "motion_bed_module", data)
    assert not target.writes
    await invoke(hass, [target], "motion_bed_module", {**data, "confirmed": True})
    assert len(target.writes) == 1


@pytest.mark.parametrize(
    "service, profile, data",
    (
        ("motion_bed_alarm", "QMS4", {"enabled": True, "hour": 24, "minute": 0}),
        ("motion_bed_alarm", "QMS4", {"enabled": True, "hour": 1, "minute": 0, "weekdays": [0]}),
        ("motion_bed_alarm", "QMS4", {"enabled": True, "hour": 1, "minute": 0, "mode": 7}),
        ("motion_bed_clock", "QMS4", {"timestamp": "not-a-date"}),
        (
            "motion_bed_sleep_angles",
            "QMS4",
            {"page": 1, "flat": [0] * 4, "side_positions": [0] * 4},
        ),
        (
            "motion_bed_sleep_angles",
            "QMS4",
            {"page": 4, "flat": [0] * 3, "side_positions": [0] * 4},
        ),
        ("motion_bed_calibration", "QMS4", {"flat": 256, "side_position": 2}),
        ("motion_bed_sleep_timer", "QMS4", {"slot": 9}),
        ("motion_bed_sleep_timer", "QMS4", {"slot": 5, "fall": True}),
        ("motion_bed_sleep_report", "QMS4", {"kind": "day", "offset": 30}),
        (
            "motion_bed_module",
            "TL-Q",
            {"operation": "bind", "module_type": 0x0D, "address": "01:23:45:67:89:AB"},
        ),
        (
            "motion_bed_module",
            "TL-Q",
            {"operation": "bind", "module_type": 0x0A, "address": "invalid"},
        ),
        ("motion_bed_air_setting", "TL-A", {"mode": 3, "gear": 9}),
        ("motion_bed_air_setting", "TL-A", {"mode": 3, "gear": 1, "timer": 3}),
        ("motion_bed_pressure", "TL-A", {"operation": "save", "values": [0] * 11}),
        ("motion_bed_pressure", "TL-A", {"operation": "live", "channel": 12, "value": 1}),
        ("motion_bed_pressure", "TL-A", {"operation": "live", "channel": 0, "value": 10}),
        ("motion_bed_thermal_schedule", "TL-W", {"hour": 0, "minute": 0, "mode": 1, "gear": 5}),
        ("motion_bed_audio", "QMS4", {"operation": "volume", "value": 6}),
    ),
)
async def test_invalid_public_domains_fail_before_connection_or_write(
    hass: HomeAssistant, service: str, profile: str, data: dict[str, object]
) -> None:
    target = make_target(hass, profile)
    with pytest.raises((ServiceValidationError, vol.Invalid)):
        await invoke(hass, [target], service, {**data, "confirmed": True})
    target.coordinator.async_execute_controller_command.assert_not_awaited()
    target.coordinator.async_ensure_connected.assert_not_called()
    assert not target.writes


@pytest.mark.parametrize(
    "profile, thermal",
    (("TL-A", False), ("TL-A", True), ("TL-W", False), ("QMS4", True), ("TL-B", True)),
)
async def test_clock_protocol_cannot_cross_module_surface(
    hass: HomeAssistant, profile: str, thermal: bool
) -> None:
    target = make_target(hass, profile)
    with pytest.raises(ServiceValidationError):
        await invoke(
            hass,
            [target],
            "motion_bed_clock",
            {"timestamp": "2026-09-30T07:45:00", "thermal": thermal},
        )
    assert not target.writes


async def test_day_report_offset_is_not_graph_viewport_offset(hass: HomeAssistant) -> None:
    target = make_target(hass)
    for offset in (0, 4, 5, 29):
        await invoke(hass, [target], "motion_bed_sleep_report", {"kind": "day", "offset": offset})
        assert target.writes[-1][8] == offset
        assert target.controller._route.day_window_offset == 0
        assert target.controller._route.historical_day


async def test_alarm_preserves_disabled_map_repeat_and_modular_first_switch(
    hass: HomeAssistant,
) -> None:
    home = make_target(hass, audio=False)
    await invoke(
        hass,
        [home],
        "motion_bed_alarm",
        {
            "enabled": False,
            "hour": 6,
            "minute": 30,
            "repeat": True,
            "weekdays": [],
            "confirmed": True,
        },
    )
    assert home.writes[0][12:14] == b"\x00\x01"
    motor = make_target(hass, "TL-B", address="01:23:45:67:89:AC", audio=False)
    await invoke(
        hass,
        [motor],
        "motion_bed_alarm",
        {"enabled": False, "hour": 6, "minute": 30, "switch": 0, "confirmed": True},
    )
    assert motor.writes[0][8] == 0




@pytest.mark.parametrize("service, profile, data", _VALID_PUBLIC_CASES)
async def test_every_public_action_preflights_later_receiver_before_first_write(
    hass: HomeAssistant, service: str, profile: str, data: dict[str, object]
) -> None:
    first = make_target(hass, profile)
    incompatible = "QMS4" if profile in ("TL-A", "TL-W", "TL-Q") else "TL-A"
    second = make_target(hass, incompatible, address="01:23:45:67:89:AC")
    with pytest.raises(ServiceValidationError):
        await invoke(hass, [first, second], service, data)
    assert not first.writes and not second.writes
    first.coordinator.async_execute_controller_command.assert_not_awaited()
    second.coordinator.async_execute_controller_command.assert_not_awaited()


async def make_registered_pair(
    hass: HomeAssistant, *, right_profile: str = "QMS4"
) -> tuple[PairedBedCoordinator, Target, Target, str, str]:
    from .test_paired_setup import _paired_entry

    entry = _paired_entry(hass)
    left = make_target(hass, "QMS4-left", address="AA:BB:CC:DD:EE:01")
    right = make_target(hass, right_profile + "-right", address="AA:BB:CC:DD:EE:02")
    pair = PairedBedCoordinator(hass, entry, {"left": left.coordinator, "right": right.coordinator})
    _async_ensure_paired_device_registry(hass, entry, pair)
    async_register_children(hass, pair)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = pair
    children = dr.async_child_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    left_id = next(child.id for child in children if child.name == left.coordinator.name)
    right_id = next(child.id for child in children if child.name == right.coordinator.name)
    pair.async_execute_controller_command = AsyncMock()
    return pair, left, right, left_id, right_id


@pytest.mark.parametrize("side", ("left", "right"))
async def test_native_paired_child_targets_retain_their_side(
    hass: HomeAssistant, side: str
) -> None:
    await async_register_services(hass)
    pair, _, _, left_id, right_id = await make_registered_pair(hass)
    await hass.services.async_call(
        DOMAIN,
        "motion_bed_clock",
        {"device_id": left_id if side == "left" else right_id, "timestamp": "2026-09-30T07:45:00"},
        blocking=True,
    )
    pair.async_execute_controller_command.assert_awaited_once()
    assert pair.async_execute_controller_command.await_args.kwargs["side"] == side


@pytest.mark.parametrize("explicit_side", ("right", "both"))
async def test_native_child_conflicting_explicit_side_rejected_before_io(
    hass: HomeAssistant, explicit_side: str
) -> None:
    await async_register_services(hass)
    pair, left, right, left_id, _ = await make_registered_pair(hass)
    with pytest.raises(ServiceValidationError) as error:
        await hass.services.async_call(
            DOMAIN,
            "motion_bed_clock",
            {"device_id": left_id, "side": explicit_side, "timestamp": "2026-09-30T07:45:00"},
            blocking=True,
        )
    assert error.value.translation_key == "side_selection_conflict"
    pair.async_execute_controller_command.assert_not_awaited()
    assert not left.writes and not right.writes


async def test_both_native_children_merge_and_preflight_all_before_dispatch(
    hass: HomeAssistant,
) -> None:
    await async_register_services(hass)
    pair, left, right, left_id, right_id = await make_registered_pair(hass, right_profile="TL-W")
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "motion_bed_sleep_angles",
            {
                "device_id": [left_id, right_id],
                "page": 4,
                "flat": [0] * 4,
                "side_positions": [0] * 4,
                "confirmed": True,
            },
            blocking=True,
        )
    pair.async_execute_controller_command.assert_not_awaited()
    assert not left.writes and not right.writes


async def test_matching_children_dispatch_once_with_both(hass: HomeAssistant) -> None:
    await async_register_services(hass)
    pair, _, _, left_id, right_id = await make_registered_pair(hass)
    await hass.services.async_call(
        DOMAIN,
        "motion_bed_clock",
        {"device_id": [left_id, right_id], "timestamp": "2026-09-30T07:45:00"},
        blocking=True,
    )
    pair.async_execute_controller_command.assert_awaited_once()
    assert pair.async_execute_controller_command.await_args.kwargs["side"] == "both"


@pytest.mark.parametrize("operation, value", (("track", 1), ("volume", 1)))
async def test_audio_requires_current_physical_capability(
    hass: HomeAssistant, operation: str, value: int
) -> None:
    target = make_target(hass, audio=False)
    with pytest.raises(ServiceValidationError):
        await invoke(hass, [target], "motion_bed_audio", {"operation": operation, "value": value})
    assert not target.writes


async def test_home_alarm_cannot_force_modular_initial_switch(hass: HomeAssistant) -> None:
    target = make_target(hass, audio=False)
    with pytest.raises(ServiceValidationError):
        await invoke(
            hass,
            [target],
            "motion_bed_alarm",
            {"enabled": True, "hour": 0, "minute": 0, "switch": 0, "confirmed": True},
        )
    assert not target.writes


@pytest.mark.parametrize(
    "action",
    (
        "alarm_activity_audio_preview_1",
        "alarm_activity_audio_stop",
        "kuaijie_k2mfragment_music",
        "kuaijie_k2mfragment_audio_off",
        "kuaijie_k2mfragment_audio_stop",
    ),
)
async def test_named_audio_actions_cannot_bypass_physical_audio_gate(
    hass: HomeAssistant, action: str
) -> None:
    target = make_target(hass, audio=False)
    with pytest.raises(ServiceValidationError):
        await invoke(hass, [target], "motion_bed_action", {"action": action})
    assert not target.writes
    target.coordinator.async_execute_controller_command.assert_not_awaited()


class BuilderVector(TypedDict):
    id: str
    expected: str | list[str]


_BUILDER_EXPECTED = {
    vector["id"]: vector["expected"]
    for vector in cast(
        list[BuilderVector],
        json.loads(
            Path(__file__)
            .with_name("fixtures")
            .joinpath("motion_bed_protocol_vectors.json")
            .read_text()
        )["vectors"],
    )
}
_BUILDER_EXPECTED.update(
    {"audio-track-1": "FFFFFFFF0100130B011C04", "audio-volume-1": "FFFFFFFF0100140B011D04"}
)
_DYNAMIC_SOURCE_ROUTES: tuple[tuple[str, str, dict[str, object], str, int | None], ...] = (
    (
        "AlarmActivity:371",
        "motion_bed_alarm",
        {
            "enabled": True,
            "hour": 6,
            "minute": 30,
            "weekdays": [],
            "mode": 1,
            "massage": True,
            "sound": 17,
            "audio": True,
        },
        "alarm-True-{}",
        None,
    ),
    (
        "AnmoSetActivity:188",
        "motion_bed_air_setting",
        {"mode": 3, "gear": 1, "timer": 0},
        "air-save-03-1-00",
        None,
    ),
    (
        "AnmoSetActivity:205",
        "motion_bed_air_setting",
        {"mode": 18, "query": True},
        "air-query-12",
        None,
    ),
    (
        "AnmoSetActivity:210",
        "motion_bed_air_setting",
        {"mode": 4, "query": True},
        "air-query-04",
        None,
    ),
    (
        "AnmoSetActivity:215",
        "motion_bed_air_setting",
        {"mode": 3, "query": True},
        "air-query-03",
        None,
    ),
    (
        "AnmoSetActivity:220",
        "motion_bed_air_setting",
        {"mode": 5, "query": True},
        "air-query-05",
        None,
    ),
    (
        "AnmoSetActivity:225",
        "motion_bed_air_setting",
        {"mode": 12, "query": True},
        "air-query-0C",
        None,
    ),
    (
        "ConnectMcuActivity:91",
        "motion_bed_module",
        {"operation": "bind", "module_type": 10, "address": "01:23:45:67:89:AB"},
        "bind-0A",
        None,
    ),
    (
        "DianDongSetActivity:653",
        "motion_bed_clock",
        {"timestamp": "2026-09-30T07:45:00", "thermal": False},
        "clock-0",
        None,
    ),
    (
        "DianDongSetActivity:881",
        "motion_bed_alarm",
        {
            "enabled": False,
            "hour": 6,
            "minute": 30,
            "weekdays": [1, 7],
            "mode": 1,
            "massage": True,
            "sound": 17,
            "audio": True,
            "switch": 161,
            "repeat": True,
        },
        "alarm-False-{'1': True, '7': True}",
        None,
    ),
    (
        "HomeActivity:337",
        "motion_bed_clock",
        {"timestamp": "2026-09-30T07:45:00", "thermal": False},
        "clock-0",
        None,
    ),
    (
        "PressSetActivity:59",
        "motion_bed_pressure",
        {"operation": "live", "channel": 0, "value": 0},
        "pressure-0-0",
        None,
    ),
    (
        "PressSetActivity:186",
        "motion_bed_pressure",
        {"operation": "save", "values": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]},
        "pressure-save-0:case-1",
        None,
    ),
    (
        "SleepAdjustActivity:360",
        "motion_bed_sleep_angles",
        {"page": 2, "flat": [1, 2, 3, 4], "side_positions": [5, 6, 7, 8]},
        "angles-02",
        None,
    ),
    (
        "SleepDataEntryActivity:263",
        "motion_bed_calibration",
        {"flat": 10, "side_position": 140},
        "calibration-10",
        None,
    ),
    (
        "SleepDayReportActivity:150",
        "motion_bed_sleep_report",
        {"kind": "day", "offset": 0},
        "report-day-0",
        None,
    ),
    (
        "SleepFallTimerSelectActivity:117",
        "motion_bed_sleep_timer",
        {"slot": 0, "fall": True},
        "sleep-timer-True-0",
        None,
    ),
    (
        "SleepMonthReportActivity:81",
        "motion_bed_sleep_report",
        {"kind": "month", "offset": 0},
        "report-month-0",
        None,
    ),
    (
        "SleepReportMainActivity:175",
        "motion_bed_sleep_report",
        {"kind": "timer", "offset": 0},
        "report-timer-0",
        None,
    ),
    (
        "SleepTimerSelectActivity:146",
        "motion_bed_sleep_timer",
        {"slot": 0, "fall": False},
        "sleep-timer-False-0",
        None,
    ),
    (
        "TimeSettingActivity:173",
        "motion_bed_thermal_schedule",
        {"hour": 21, "minute": 30, "mode": 1, "gear": 1},
        "thermal-timer-01-1",
        None,
    ),
    (
        "DiandongFragment:302",
        "motion_bed_alarm",
        {
            "enabled": True,
            "hour": 6,
            "minute": 30,
            "weekdays": [],
            "mode": 1,
            "massage": True,
            "sound": 17,
            "audio": True,
        },
        "alarm-True-{}",
        None,
    ),
    (
        "DiandongFragment:340",
        "motion_bed_clock",
        {"timestamp": "2026-09-30T07:45:00", "thermal": False},
        "clock-0",
        None,
    ),
    (
        "KuaijieK2MFragment:452",
        "motion_bed_audio",
        {"operation": "track", "value": 1},
        "audio-track-1",
        None,
    ),
    (
        "KuaijieK2MFragment:474",
        "motion_bed_audio",
        {"operation": "volume", "value": 1},
        "audio-volume-1",
        None,
    ),
    (
        "LengnuanFragment:206",
        "motion_bed_clock",
        {"timestamp": "2026-09-30T07:45:00", "thermal": True},
        "thermal_clock-0",
        None,
    ),
)


@pytest.mark.parametrize("source_id, service, data, vector_id, frame_index", _DYNAMIC_SOURCE_ROUTES)
async def test_every_dynamic_source_builder_is_bound_to_public_request(
    hass: HomeAssistant,
    source_id: str,
    service: str,
    data: dict[str, object],
    vector_id: str,
    frame_index: int | None,
) -> None:
    await async_register_services(hass)
    schema = hass.services.async_services()[DOMAIN][service].schema
    assert schema is not None
    validated = schema({"device_id": "bed", **data})
    request = build_motion_bed_request(service, validated)
    expected = _BUILDER_EXPECTED[vector_id]
    if frame_index is not None:
        assert isinstance(expected, list)
        assert request.frames[frame_index].hex().upper() == expected[frame_index]
    else:
        assert isinstance(expected, str)
        assert request.frames[0].hex().upper() == expected
    assert source_id
    if service == "motion_bed_pressure" and data["operation"] == "live":
        assert request.initial_delay_ms == 2500


def test_all_ble_dynamic_source_rows_are_covered() -> None:
    assert len(_DYNAMIC_SOURCE_ROUTES) == len({row[0] for row in _DYNAMIC_SOURCE_ROUTES}) == 26
