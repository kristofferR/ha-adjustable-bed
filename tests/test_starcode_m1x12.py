"""M1X12 controller behavior tied to the accepted command and lifecycle rows."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.star_elevate import StarElevateCommands
from custom_components.adjustable_bed.beds.starcode_m1x12 import (
    DEVICE_INFORMATION,
    FIRMWARE,
    MANUFACTURER,
    NOTIFY,
    SERVICE,
    WRITE,
    StarcodeM1X12Controller,
    StarElevateM1X12Controller,
)
from custom_components.adjustable_bed.beds.starcode_m1x12_protocol import (
    clock_packet,
    extended_packet,
    keep_open_packet,
    long_packet,
    normal_packet,
    position_packet,
    query_packet,
)
from custom_components.adjustable_bed.binary_sensor import _binary_sensor_entities_for
from custom_components.adjustable_bed.button import _button_entities_for
from custom_components.adjustable_bed.config_flow import _starcode_m1x12_errors
from custom_components.adjustable_bed.const import (
    BED_TYPE_STAR_ELEVATE,
    BED_TYPE_STARCODE_M1X12,
    CONF_BED_TYPE,
    CONF_BLE_DEVICE_NAME,
    CONF_HAS_MASSAGE,
    CONF_PROTOCOL_VARIANT,
    CONF_STARCODE_M1X12_PROFILE,
    DOMAIN,
    STAR_ELEVATE_VARIANT_M1X12,
    VARIANT_AUTO,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import _cover_entities_for
from custom_components.adjustable_bed.light import _light_entities_for
from custom_components.adjustable_bed.number import _number_entities_for
from custom_components.adjustable_bed.select import _select_entities_for
from custom_components.adjustable_bed.sensor import _sensor_entities_for
from custom_components.adjustable_bed.services import async_register_services

_FIXTURE_DIR = Path(__file__).parent / "fixtures"
COMMAND_ROWS = json.loads((_FIXTURE_DIR / "starcode_m1x12_command_rows.json").read_text())
_PROFILE = {"P1": "cb25", "P3": "f23", "P4": "kneading"}
_MOTOR_CONTROLS = {
    "head out/up": "part_1_up",
    "head in/down": "part_1_down",
    "foot out/up": "part_2_up",
    "foot in/down": "part_2_down",
    "lumbar out/up": "part_4_up",
    "lumbar in/down": "part_4_down",
    "part4 out/up": "part_8_up",
    "part4 in/down": "part_8_down",
    "part5 out/up": "part_16_up",
    "part5 in/down": "part_16_down",
    "head+foot out/up": "union_up",
    "head+foot in/down": "union_down",
}
_ELEVATE_CONTROLS = {
    "elevation Part(1) out/up": "actuator_1_up",
    "elevation Part(1) in/down": "actuator_1_down",
    "elevation Part(2) out/up": "actuator_2_up",
    "elevation Part(2) in/down": "actuator_2_down",
    "elevation Part(3) out/up": "both_up",
    "elevation Part(3) in/down": "both_down",
}
_MASSAGE_CONTROLS = {
    "massage wave increase": "massage_wave_up",
    "massage wave decrease": "massage_wave_down",
    "head massage intensity increase": "massage_head_up",
    "head massage intensity decrease": "massage_head_down",
    "foot massage intensity increase": "massage_foot_up",
    "foot massage intensity decrease": "massage_foot_down",
    "both-zone massage intensity increase": "massage_both_up",
    "both-zone massage intensity decrease": "massage_both_down",
}


def _controller_target(
    hass: HomeAssistant,
    *,
    bed_type: str = BED_TYPE_STARCODE_M1X12,
    name: str = "STAR252201123456",
    profile: str = "cb25",
    variant: str | None = None,
    client: Any | None = None,
) -> tuple[AdjustableBedCoordinator, Any]:
    data: dict[str, Any] = {
        CONF_ADDRESS: f"AA:BB:CC:DD:EE:{len(hass.config_entries.async_entries(DOMAIN)) + 1:02X}",
        CONF_NAME: name,
        CONF_BLE_DEVICE_NAME: name,
        CONF_BED_TYPE: bed_type,
    }
    if bed_type == BED_TYPE_STARCODE_M1X12:
        data[CONF_STARCODE_M1X12_PROFILE] = profile
    if variant is not None:
        data[CONF_PROTOCOL_VARIANT] = variant
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=name,
        unique_id=data[CONF_ADDRESS],
        data=data,
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    if client is not None:
        coordinator._client = client
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    return coordinator, entry


class _Services:
    def __init__(self, *, missing: set[str] | None = None) -> None:
        self._services = {
            SERVICE: SimpleNamespace(uuid=SERVICE),
            DEVICE_INFORMATION: SimpleNamespace(uuid=DEVICE_INFORMATION),
        }
        self._characteristics = {
            WRITE: SimpleNamespace(
                uuid=WRITE, service_uuid=SERVICE, properties=["write-without-response"], handle=1
            ),
            NOTIFY: SimpleNamespace(
                uuid=NOTIFY, service_uuid=SERVICE, properties=["notify"], handle=2
            ),
            FIRMWARE: SimpleNamespace(
                uuid=FIRMWARE, service_uuid=DEVICE_INFORMATION, properties=["read"], handle=3
            ),
            MANUFACTURER: SimpleNamespace(
                uuid=MANUFACTURER, service_uuid=DEVICE_INFORMATION, properties=["read"], handle=4
            ),
        }
        for uuid in missing or set():
            self._services.pop(uuid, None)
            self._characteristics.pop(uuid, None)

    def __iter__(self) -> Iterator[Any]:
        for service in self._services.values():
            service.characteristics = [
                characteristic
                for characteristic in self._characteristics.values()
                if characteristic.service_uuid == service.uuid
            ]
            yield service

    def get_service(self, uuid: str) -> Any | None:
        return self._services.get(uuid)

    def get_characteristic(self, uuid: str) -> Any | None:
        return self._characteristics.get(uuid)


class _GattClient:
    def __init__(
        self,
        *,
        missing: set[str] | None = None,
        reads: dict[str, Any] | None = None,
        notify_error: BaseException | None = None,
    ) -> None:
        self.is_connected = True
        self.services = _Services(missing=missing)
        self.reads = reads or {FIRMWARE: b"1.2", MANUFACTURER: b"star"}
        self.notify_error = notify_error
        self.events: list[tuple[Any, ...]] = []

    async def read_gatt_char(self, uuid: str) -> bytes:
        self.events.append(("read", uuid))
        result = self.reads.get(uuid, b"")
        if isinstance(result, BaseException):
            raise result
        return result

    async def start_notify(self, uuid: str, callback: Any) -> None:
        self.events.append(("notify", uuid))
        if self.notify_error is not None:
            raise self.notify_error
        self.notify_callback = callback

    async def stop_notify(self, uuid: str) -> None:
        self.events.append(("stop_notify", uuid))

    async def write_gatt_char(self, uuid: str, data: bytes, *, response: bool = False) -> None:
        self.events.append(("write", uuid, bytes(data), response))


async def _create_controller(
    hass: HomeAssistant,
    *,
    profile: str = "cb25",
    name: str = "STAR252201123456",
    client: _GattClient | None = None,
) -> tuple[AdjustableBedCoordinator, StarcodeM1X12Controller]:
    coordinator, entry = _controller_target(hass, name=name, profile=profile, client=client)
    controller = await create_controller(
        coordinator, BED_TYPE_STARCODE_M1X12, VARIANT_AUTO, client, device_name=name
    )
    assert isinstance(controller, StarcodeM1X12Controller)
    coordinator._controller = controller
    return coordinator, controller


@pytest.mark.parametrize(
    ("entity_kind", "entity_key", "control", "expected_key"),
    (
        ("cover", "m1x12_part_1", "part_1_up", 0x03103000),
        (
            "button",
            "starcode_m1x12_hold_massage_wave_up",
            "massage_wave_up",
            0x03103058,
        ),
    ),
)
async def test_held_entity_metadata_reaches_real_bounded_service_and_controller(
    hass: HomeAssistant,
    entity_kind: str,
    entity_key: str,
    control: str,
    expected_key: int,
) -> None:
    """The target cover and button metadata drive the registered shared service."""
    client = _GattClient()
    coordinator, controller = await _create_controller(hass, client=client)
    coordinator.entry.mock_state(hass, ConfigEntryState.LOADED)
    coordinator._ready = True
    controller._ready = True
    controller.dialect = "star"

    entities = (
        _cover_entities_for(hass, coordinator)
        if entity_kind == "cover"
        else _button_entities_for(hass, coordinator)
    )
    entity = next(
        row for row in entities if row.unique_id == coordinator.entity_unique_id(entity_key)
    )
    attributes = entity.extra_state_attributes
    if entity_kind == "cover":
        assert attributes["held_control_up"] == control
        assert attributes["held_control_down"] == control.replace("_up", "_down")
    else:
        assert attributes["held_control"] == control
    assert attributes["hold_start_delay_ms"] == attributes["hold_release_delay_ms"] == 100

    button_entities = _button_entities_for(hass, coordinator)
    stop_button = next(
        row for row in button_entities if row.unique_id == coordinator.entity_unique_id("stop")
    )

    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=coordinator.entry.entry_id,
        **coordinator.device_info,
    )
    await async_register_services(hass)
    writes: list[bytes] = []
    first_write = asyncio.Event()

    async def cancel_after_first_refresh(
        _characteristic: Any, data: bytes, *, response: bool = False
    ) -> None:
        del response
        writes.append(bytes(data))
        first_write.set()

    client.write_gatt_char = cancel_after_first_refresh  # type: ignore[method-assign]
    held_service = asyncio.create_task(
        hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": [device.id], "control": control, "duration": 60},
            blocking=True,
        )
    )
    await first_write.wait()
    await stop_button.async_press()
    await held_service

    assert writes[0] == normal_packet(expected_key, "star")
    assert writes[-1] == normal_packet(0x0310300F, "star")
    assert all(packet == normal_packet(0x0310300F, "star") for packet in writes[1:])
    assert controller._coordinator is coordinator


@pytest.mark.parametrize(
    ("profile", "extra_sensors", "extra_binary"),
    (
        ("cb25", {"starcode_m1x12_alarm_0", "starcode_m1x12_alarm_1"}, set()),
        (
            "f23",
            {
                "starcode_m1x12_alarm_0",
                "starcode_m1x12_alarm_1",
                "starcode_m1x12_eq_volume",
                "starcode_m1x12_eq_band_7",
            },
            {"starcode_m1x12_usb_on"},
        ),
        (
            "kneading",
            {
                "starcode_m1x12_alarm_0",
                "starcode_m1x12_eq_volume",
                "starcode_m1x12_kneading_time_raw",
            },
            {"starcode_m1x12_kneading_on", "starcode_m1x12_kneading_demo"},
        ),
    ),
)
async def test_m1x12_entities_follow_explicit_app_profile(
    hass: HomeAssistant,
    profile: str,
    extra_sensors: set[str],
    extra_binary: set[str],
) -> None:
    coordinator, controller = await _create_controller(hass, profile=profile)
    controller.dialect = "star"

    assert {spec.key for spec in controller.motor_control_specs} == {
        "m1x12_part_1",
        "m1x12_part_2",
        "m1x12_part_4",
        "m1x12_part_8",
        "m1x12_part_16",
    }
    assert all(spec.hold is not None for spec in controller.motor_control_specs)
    number_ids = {entity.unique_id for entity in _number_entities_for(hass, coordinator)}
    assert (
        not {
            coordinator.entity_unique_id(key)
            for key in ("back_position", "legs_position", "head_position", "feet_position")
        }
        & number_ids
    )
    assert {spec.key for spec in controller.controller_number_specs} == {
        "starcode_m1x12_brightness"
    }
    (brightness,) = controller.controller_number_specs
    assert (brightness.native_min_value, brightness.native_max_value, brightness.native_step) == (
        1,
        6,
        1,
    )
    sensor_keys = {spec.key for spec in controller.controller_state_sensor_specs}
    binary_keys = {spec.key for spec in controller.controller_state_binary_sensor_specs}
    assert extra_sensors <= sensor_keys
    assert extra_binary <= binary_keys
    assert "starcode_m1x12_alarm_1" in sensor_keys
    assert ("starcode_m1x12_usb_on" in binary_keys) == (profile != "cb25")
    assert ("starcode_m1x12_kneading_mode" in sensor_keys) == (profile == "kneading")
    held_buttons = [spec for spec in controller.controller_button_specs if spec.hold is not None]
    assert len(held_buttons) == 8
    assert {spec.hold.control for spec in held_buttons if spec.hold is not None} == {
        "massage_wave_up",
        "massage_wave_down",
        "massage_head_up",
        "massage_head_down",
        "massage_foot_up",
        "massage_foot_down",
        "massage_both_up",
        "massage_both_down",
    }
    hass.config_entries.async_update_entry(
        coordinator.entry,
        data={**coordinator.entry.data, CONF_HAS_MASSAGE: True},
    )
    built_sensor_ids = {entity.unique_id for entity in _sensor_entities_for(hass, coordinator)}
    built_binary_ids = {
        entity.unique_id for entity in _binary_sensor_entities_for(hass, coordinator)
    }
    built_number_ids = {entity.unique_id for entity in _number_entities_for(hass, coordinator)}
    built_select_ids = {entity.unique_id for entity in _select_entities_for(hass, coordinator)}
    expected_sensor_ids = {coordinator.entity_unique_id(key) for key in sensor_keys}
    expected_binary_ids = {coordinator.entity_unique_id(key) for key in binary_keys}
    assert expected_sensor_ids <= built_sensor_ids
    assert expected_binary_ids <= built_binary_ids
    assert (
        coordinator.entity_unique_id("controller_number_starcode_m1x12_brightness")
        in built_number_ids
    )
    assert coordinator.entity_unique_id("massage_timer") in built_select_ids
    assert len(_light_entities_for(hass, coordinator)) == 1


@pytest.mark.parametrize(
    ("name", "profile", "valid"),
    (
        ("STAR252201123456", "cb25", True),
        ("star254205123456", "f23", True),
        ("STAR255402123456", "kneading", True),
        ("STAR25OTHER", "f23", False),
        ("ELEVATE123456", "cb25", False),
    ),
)
async def test_m1x12_setup_requires_explicit_matching_app_name_and_profile(
    hass: HomeAssistant,
    name: str,
    profile: str,
    valid: bool,
) -> None:
    data = {
        CONF_BED_TYPE: BED_TYPE_STARCODE_M1X12,
        CONF_BLE_DEVICE_NAME: name,
        CONF_STARCODE_M1X12_PROFILE: profile,
    }
    errors = _starcode_m1x12_errors(hass, data)
    assert (not errors) is valid
    if not valid:
        assert errors == {CONF_STARCODE_M1X12_PROFILE: "starcode_m1x12_profile_mismatch"}


@pytest.mark.parametrize(
    ("name", "special"),
    (
        ("STAR252201123456", True),
        ("STAR254202123456", True),
        ("STAR352201123456", True),
        ("STAR250000123456", False),
        ("STAR25", False),
    ),
)
@pytest.mark.parametrize("dialect", ("star", "legacy"))
async def test_light_mode_model_gate_covers_all_three_special_ids_and_other_names(
    hass: HomeAssistant,
    name: str,
    special: bool,
    dialect: str,
) -> None:
    _coordinator, controller = await _create_controller(hass, name=name)
    controller._ready = True
    controller.dialect = dialect
    writes: list[tuple[bytes, int, asyncio.Event | None]] = []

    async def record_write(
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
        **_kwargs: Any,
    ) -> None:
        del repeat_delay_ms
        writes.append((bytes(command), repeat_count, cancel_event))

    controller.write_command = record_write
    for mode in (0, 1):
        writes.clear()
        await controller.light_mode(mode)
        if special:
            key = 0x03103079 if mode == 0 else 0x0310307A
            frame = (
                normal_packet(key, "star")
                if dialect == "star"
                else normal_packet(0x00020004, "legacy")
            )
            assert [(packet, count) for packet, count, _event in writes] == [(frame, 35)]
        else:
            key = 0x03103089 if mode == 0 else 0x0310308A
            expected = [(normal_packet(key, "star"), 1)]
            if mode == 1:
                expected.append((normal_packet(0x0310300F, "star"), 1))
            assert [(packet, count) for packet, count, _event in writes] == expected


async def test_internal_progress_feedback_advances_queue_and_stop_invalidates_next_target(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    coordinator, controller = await _create_controller(hass, client=_GattClient())
    controller._ready = True
    controller.dialect = "star"
    writer = AsyncMock()
    monkeypatch.setattr(controller, "write_command", writer)
    controller.queue_position_targets(((0, 50), (4, 75)))

    moving = bytearray.fromhex("a5 0d 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 01")
    controller._apply_notification(bytes(moving))
    await asyncio.sleep(0)
    writer.assert_not_awaited()

    stopped = bytearray(moving)
    stopped[17] = 0
    controller._apply_notification(bytes(stopped))
    await asyncio.sleep(0)
    writer.assert_awaited_once_with(position_packet(0, 50, "star"))
    assert controller._progress_queue == [(4, 75)]

    controller._apply_notification(bytes(stopped))
    await asyncio.sleep(0)
    writer.assert_awaited_with(position_packet(4, 75, "star"))
    assert controller._progress_queue == []

    controller.queue_position_target(2, 99)
    await controller.stop_all()
    assert controller._progress_queue == []
    assert coordinator.controller is controller


async def test_m1x12_sender_first_tick_cadence_and_busy_tick_skip(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _coordinator, controller = await _create_controller(hass, client=_GattClient())
    controller._ready = True
    clock = SimpleNamespace(now=100.0)
    sleeps: list[float] = []

    class FakeLoop:
        def time(self) -> float:
            return clock.now

    async def advance_clock(delay: float) -> None:
        sleeps.append(delay)
        clock.now += delay

    fake_asyncio = SimpleNamespace(
        get_running_loop=lambda: FakeLoop(),
        sleep=advance_clock,
    )
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.starcode_m1x12.asyncio", fake_asyncio
    )

    controller._next_tick = clock.now + 0.1
    await controller.write_command(b"first", repeat_count=2)
    assert sleeps == pytest.approx([0.1, 0.1])

    sleeps.clear()
    clock.now = 200.0
    controller._next_tick = clock.now - 0.25
    await controller.write_command(b"late", repeat_count=2)
    assert sleeps == pytest.approx([0.05, 0.1])


def _expected_main_frame(row: dict[str, Any], dialect: str) -> bytes:
    description = row["bytes"]
    selected_normal = re.search(
        r"select\(S: N_S\((0x[0-9a-fA-F]+)\), C: (N_C|N_S|LONG_C)\((0x[0-9a-fA-F]+|\d+)\)\)",
        description,
    )
    if selected_normal:
        if dialect == "star":
            return normal_packet(int(selected_normal[1], 16), "star")
        value = int(selected_normal[3], 0)
        return (
            normal_packet(value, "legacy")
            if selected_normal[2] == "N_C"
            else long_packet(value)
            if selected_normal[2] == "LONG_C"
            else normal_packet(value, "star")
        )
    selected_extended = re.search(
        r"select\(S: E_S\((\d+),(\d+)\), C: E_C\((\d+),(\d+)\)\)",
        description,
    )
    if selected_extended:
        index = 1 if dialect == "star" else 3
        return extended_packet(
            int(selected_extended[index]), int(selected_extended[index + 1]), dialect
        )
    selected_query = re.search(r"select\(S: 5a b0 00 a5, C: 00 b0\)", description)
    if selected_query:
        return query_packet("star" if row["protocol"] in ("P3", "P4") else dialect)
    selected_position = re.search(
        r"select\(S: P_S\(axis,target\), C: P_C\(axis,target\)\)", description
    )
    if selected_position:
        return position_packet(0, 50, dialect)
    if row["action"] in {"STOP", "interrupt movement"}:
        selected_stop = re.search(
            r"N_S\((0x[0-9a-fA-F]+)\) when manufacturer selector is S; N_C\((0x[0-9a-fA-F]+|\d+)\) otherwise",
            description,
        )
        if selected_stop:
            if dialect == "star":
                return normal_packet(int(selected_stop[1], 16), "star")
            return normal_packet(int(selected_stop[2], 0), "legacy")
    special_packet = re.search(r"LONG_C\((0x[0-9a-fA-F]+)\)", description)
    if row["action"] == "connection keep-open" or row["action"] == "elevation connection keep-open":
        return keep_open_packet()
    if row["action"] == "query status":
        return query_packet("star" if row["protocol"] in ("P3", "P4") else dialect)
    if row["action"] == "clock correction at connection":
        return clock_packet(datetime(2026, 10, 26, 12, 34, 56))
    if "Delegates to massage off" in description:
        return normal_packet(0x0310306F if dialect == "star" else 0x02000000, dialect)
    direct_extended = re.search(r"E_S\((\d+),level\)", description)
    if direct_extended:
        direct_dialect = "star" if row["protocol"] in ("P3", "P4") else dialect
        return extended_packet(int(direct_extended[1]), 6, direct_dialect)
    direct_duration = re.search(r"E_S\((\d+),(\d+)\)", description)
    if direct_duration:
        return extended_packet(int(direct_duration[1]), int(direct_duration[2]), "star")
    if special_packet:
        selected_star = re.search(r"select\(S: N_S\((0x[0-9a-fA-F]+)\)", description)
        if selected_star and dialect == "star":
            return normal_packet(int(selected_star[1], 16), "star")
        if dialect == "legacy":
            return long_packet(int(special_packet[1], 16))
    normal = re.search(r"N_S\((0x[0-9a-fA-F]+)\)", description)
    if normal:
        return normal_packet(int(normal[1], 16), "star")
    legacy = re.search(r"N_C\((0x[0-9a-fA-F]+)\)", description)
    if legacy:
        return normal_packet(int(legacy[1], 16), "legacy")
    raise AssertionError(f"No target packet oracle for {row['id']}: {description}")


def _row_count(row: dict[str, Any]) -> int:
    action = row["action"]
    if action == "massage duration zero":
        return 2
    for count in (55, 35, 3, 2):
        if re.search(rf"\b{count} (?:copies|repeats)", row["bytes"] + " " + row["timing"]):
            return count
    return 1


async def _invoke_row(controller: Any, row: dict[str, Any]) -> bool:
    """Run the controller path for one accepted command row; return held status."""
    action = row["action"]
    if row["protocol"] == "P2":
        if action in _ELEVATE_CONTROLS:
            await controller.hold_control(_ELEVATE_CONTROLS[action], 300)
            return True
        if action == "elevation flat":
            await controller.preset_flat()
        elif action == "elevation interrupt":
            await controller.interrupt()
        elif action == "elevation STOP":
            await controller.stop_all()
        elif action == "elevation connection keep-open":
            await controller.write_command(keep_open_packet())
        else:
            raise AssertionError(f"Unmapped M1X12 ELEVATE row {row['id']}: {action}")
        return False

    if action in _MOTOR_CONTROLS:
        await controller.hold_control(_MOTOR_CONTROLS[action], 300)
        return True
    if action in _MASSAGE_CONTROLS:
        await controller.hold_control(_MASSAGE_CONTROLS[action], 300)
        return True
    if action == "STOP":
        await controller.stop_all()
    elif action == "interrupt movement":
        await controller.interrupt()
    elif action == "flat":
        await controller.app_action("flat")
    elif action == "recall TV (UI ascent)":
        await controller.app_action("tv")
    elif action == "recall zero gravity":
        await controller.app_action("zero_g")
    elif action == "recall anti-snore":
        await controller.app_action("anti_snore")
    elif action == "recall reading/lounge":
        await controller.app_action("lounge")
    elif action.startswith("recall MemoryType(8)"):
        await controller.app_action("memory_8")
    elif action == "recall memory A/M1":
        await controller.app_action("memory_1")
    elif action == "recall memory B/M2":
        await controller.app_action("memory_2")
    elif action.startswith("program TV"):
        await controller.app_action("save_tv")
    elif action == "program zero gravity":
        await controller.app_action("save_zero_g")
    elif action == "program reading":
        await controller.app_action("save_lounge")
    elif action == "program M1":
        await controller.app_action("save_memory_1")
    elif action == "program M2":
        await controller.app_action("save_memory_2")
    elif action == "reset programmed positions":
        await controller.app_action("reset")
    elif action == "massage toggle":
        await controller.app_action("massage_toggle")
    elif action == "massage off" or action == "massage duration zero":
        await controller.app_action("massage_off")
    elif action.startswith("massage duration "):
        await controller.set_massage_timer(int(action.split()[2]) // 60)
    elif action == "light/color cycle":
        await controller.app_action("light_cycle")
    elif action == "light on":
        await controller.app_action("light_on")
    elif action == "light off":
        await controller.app_action("light_off")
    elif action.startswith("light mode 0, special"):
        await controller.light_mode(0)
    elif action.startswith("light mode 1, special"):
        await controller.light_mode(1)
    elif action == "light mode 0, other model":
        await controller.light_mode(0)
    elif action == "light mode 1, other model" or action == "light mode (argument ignored)":
        await controller.light_mode(1)
    elif action == "brightness level 1..6":
        await controller.set_brightness(6)
    elif action == "query status":
        await controller.query_status()
    elif action == "connection keep-open":
        await controller.write_command(keep_open_packet())
    elif action == "internal progress target":
        controller.queue_position_targets(((0, 50),))
        await controller._send_progress_target(
            0,
            50,
            session_generation=controller.session_generation,
            progress_generation=controller._progress_generation,
        )
    elif action == "clock correction at connection":
        await controller.write_command(clock_packet(datetime(2026, 10, 26, 12, 34, 56)))
    else:
        raise AssertionError(f"Unmapped M1X12 row {row['id']}: {action}")
    return False


def _expected_sequence(row: dict[str, Any], dialect: str, profile: str) -> list[bytes]:
    action = row["action"]
    if row["protocol"] == "P2":
        stop = normal_packet(0x0310300F, "star")
        if action in _ELEVATE_CONTROLS:
            key = {
                "actuator_1_up": 0x40,
                "actuator_1_down": 0x41,
                "actuator_2_up": 0x42,
                "actuator_2_down": 0x43,
                "both_up": 0x44,
                "both_down": 0x45,
            }[_ELEVATE_CONTROLS[action]]
            return [normal_packet(0x03103000 + key - 0x00, "star"), stop]
        if action == "elevation flat":
            return [normal_packet(0x03103046, "star")]
        if action == "elevation interrupt":
            return [normal_packet(0x0310304F, "star")]
        if action == "elevation STOP":
            return [stop]
        return [keep_open_packet()]

    stop = normal_packet(0x0310300F, "star") if dialect == "star" else normal_packet(0, "legacy")
    if action in _MOTOR_CONTROLS or action in _MASSAGE_CONTROLS:
        if action in _MASSAGE_CONTROLS and action.startswith("massage_both") and dialect == "star":
            return []
        primary = _expected_main_frame(row, dialect)
        if action.startswith("both-zone") and dialect == "star":
            return []
        return [primary, stop]

    if action == "massage duration zero":
        massage_off = normal_packet(0x0310306F if dialect == "star" else 0x02000000, dialect)
        return [massage_off, massage_off, stop]

    primary = _expected_main_frame(row, dialect)
    count = _row_count(row)
    if action.startswith(("program ", "reset programmed")):
        return [stop, *([primary] * count)]
    if action in {
        "flat",
        "recall TV (UI ascent)",
        "recall zero gravity",
        "recall anti-snore",
        "recall reading/lounge",
        "recall memory A/M1",
        "recall memory B/M2",
    }:
        return [*([primary] * count), stop]
    if action in {
        "STOP",
        "interrupt movement",
        "query status",
        "connection keep-open",
        "internal progress target",
        "clock correction at connection",
        "light mode 0, special model",
        "light mode 1, special model",
        "light mode 0, other model",
    }:
        return [*([primary] * count)]
    if action == "light mode 1, special model":
        return [*([primary] * count)]
    if action == "light mode 1, other model":
        return [primary, normal_packet(0x0310300F, "star")]
    if action == "light mode (argument ignored)":
        return [primary, normal_packet(0x0310300F, "star")]
    if action.startswith("recall MemoryType(8)"):
        return [*([primary] * 3), stop]
    if action in {"massage off", "massage toggle"}:
        return [*([primary] * 2), stop]
    if action in {"light/color cycle", "light on", "light off"}:
        copies = 2 if row["protocol"] == "P1" else 1
        actual_stop = stop if row["protocol"] == "P1" else normal_packet(0x0310300F, "star")
        return [*([primary] * copies), actual_stop]
    if action == "brightness level 1..6":
        actual_stop = stop if row["protocol"] == "P1" else normal_packet(0x0310300F, "star")
        return [primary, actual_stop]
    if action.startswith("massage duration "):
        actual_stop = stop
        return [primary, actual_stop]
    return [primary]


_ROW_CASES = tuple(
    (row, dialect)
    for row in COMMAND_ROWS
    for dialect in (("star",) if row["protocol"] == "P2" else ("star", "legacy"))
)
_ROW_CASE_IDS = tuple(f"{row['id']}-{dialect}" for row, dialect in _ROW_CASES)


@pytest.mark.parametrize(
    ("row", "dialect"),
    _ROW_CASES,
    ids=_ROW_CASE_IDS,
)
async def test_accepted_command_rows_run_through_the_m1x12_controller(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    row: dict[str, Any],
    dialect: str,
) -> None:
    protocol = row["protocol"]
    client = _GattClient()
    if protocol == "P2":
        coordinator, entry = _controller_target(
            hass,
            bed_type=BED_TYPE_STAR_ELEVATE,
            name="ELEVATE123456",
            variant=STAR_ELEVATE_VARIANT_M1X12,
            client=client,
        )
        controller = await create_controller(
            coordinator,
            BED_TYPE_STAR_ELEVATE,
            STAR_ELEVATE_VARIANT_M1X12,
            client,
            device_name="ELEVATE123456",
        )
        assert isinstance(controller, StarElevateM1X12Controller)
        controller._initialized = True
        dialect = "star"
        profile = "elevate"
    else:
        profile = _PROFILE[protocol]
        name = "STAR252201123456" if row["action"].endswith("special model") else "STAR250000123456"
        coordinator, controller = await _create_controller(
            hass, profile=profile, name=name, client=client
        )
        controller.dialect = dialect

    controller._interrupt_group = AsyncMock()
    if isinstance(controller, StarcodeM1X12Controller):
        controller._ready = True
    writes: list[tuple[bytes, int, asyncio.Event | None]] = []
    held = (
        row["action"] in _MOTOR_CONTROLS
        or row["action"] in _MASSAGE_CONTROLS
        or row["action"] in _ELEVATE_CONTROLS
    )

    async def record_write(
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
        **_: Any,
    ) -> None:
        del repeat_delay_ms
        writes.append((bytes(command), repeat_count, cancel_event))
        if held and cancel_event is coordinator.cancel_command:
            coordinator.cancel_command.set()

    if isinstance(controller, StarElevateM1X12Controller) and row["action"] in _ELEVATE_CONTROLS:

        async def record_owned_write(
            command: bytes,
            *,
            client: Any,
            generation: int,
            cancel_event: asyncio.Event,
        ) -> None:
            del client, generation
            writes.append((bytes(command), 1, cancel_event))
            if held and cancel_event is coordinator.cancel_command:
                coordinator.cancel_command.set()

        controller._write_owned_command = record_owned_write
    else:
        controller.write_command = record_write

    async def no_protocol_wait(_delay: float) -> None:
        return None

    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.starcode_m1x12.asyncio.sleep", no_protocol_wait
    )

    await _invoke_row(controller, row)
    expanded = [packet for packet, count, _ in writes for _ in range(max(1, count))]
    expected = _expected_sequence(row, dialect, profile)
    assert expanded == expected, row["id"]


@pytest.mark.parametrize("variant", [None, "", VARIANT_AUTO])
async def test_elevate_defaults_keep_the_legacy_controller(
    hass: HomeAssistant, variant: str | None
) -> None:
    coordinator, _entry = _controller_target(
        hass,
        bed_type=BED_TYPE_STAR_ELEVATE,
        name="ELEVATE123456",
        variant=variant,
    )
    controller = await create_controller(
        coordinator, BED_TYPE_STAR_ELEVATE, variant, None, device_name="ELEVATE123456"
    )
    from custom_components.adjustable_bed.beds.star_elevate import StarElevateController

    assert type(controller) is StarElevateController


async def test_only_explicit_m1x12_elevate_selects_version_gated_controller(
    hass: HomeAssistant,
) -> None:
    coordinator, _entry = _controller_target(
        hass,
        bed_type=BED_TYPE_STAR_ELEVATE,
        name="ELEVATE123456",
        variant=STAR_ELEVATE_VARIANT_M1X12,
    )
    controller = await create_controller(
        coordinator,
        BED_TYPE_STAR_ELEVATE,
        STAR_ELEVATE_VARIANT_M1X12,
        None,
        device_name="ELEVATE123456",
    )
    assert type(controller) is StarElevateM1X12Controller
    assert controller.held_control_options == (
        "actuator_1_up",
        "actuator_1_down",
        "actuator_2_up",
        "actuator_2_down",
        "both_up",
        "both_down",
    )
    assert [spec.key for spec in controller.motor_control_specs] == [
        "elevate_actuator_1",
        "elevate_actuator_2",
        "elevate_both",
    ]
    assert all(spec.hold is not None for spec in controller.motor_control_specs)


async def test_m1x12_startup_keeps_read_subscribe_and_wake_order(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed_time = datetime(2026, 10, 26, 12, 34, 56)

    async def no_wait(_delay: float) -> None:
        return None

    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.starcode_m1x12.asyncio.sleep", no_wait
    )
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.starcode_m1x12.dt_util.now", lambda: fixed_time
    )

    cases = (
        ("cb25", b"star", [keep_open_packet(), query_packet("star")]),
        ("cb25", b"other", [query_packet("legacy")]),
        ("f23", b"other", [clock_packet(fixed_time), query_packet("star")]),
    )
    for index, (profile, manufacturer, expected_writes) in enumerate(cases, 1):
        client = _GattClient(reads={FIRMWARE: b"\xffA \t", MANUFACTURER: manufacturer})
        coordinator, controller = await _create_controller(hass, profile=profile, client=client)
        assert not controller.ready
        await controller.start_notify()

        assert client.events[:3] == [
            ("read", FIRMWARE),
            ("notify", NOTIFY),
            ("read", MANUFACTURER),
        ]
        assert [event[2] for event in client.events if event[0] == "write"] == expected_writes
        assert controller.ready
        assert controller._state["firmware"] == "ÿA \t"
        assert controller.dialect == ("star" if manufacturer.lower() == b"star" else "legacy")
        await controller.stop_notify()
        startup_writes = [event[2] for event in client.events if event[0] == "write"]
        assert startup_writes[-1] == normal_packet(
            0x0310300F if manufacturer.lower() == b"star" else 0, controller.dialect
        )
        assert client.events[-1] == ("stop_notify", NOTIFY)
        del coordinator, index


@pytest.mark.parametrize(
    "firmware",
    [b"", ValueError("read failed"), TimeoutError("read timed out")],
    ids=["empty", "error", "timeout"],
)
async def test_m1x12_firmware_read_failure_leaves_version_unknown_but_session_ready(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    firmware: bytes | BaseException,
) -> None:
    timeouts: list[float] = []
    original_wait_for = asyncio.wait_for

    async def record_timeout(awaitable, timeout: float):
        timeouts.append(timeout)
        return await original_wait_for(awaitable, timeout)

    async def no_wait(_delay: float) -> None:
        return None

    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.starcode_m1x12.asyncio.sleep", no_wait
    )
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.starcode_m1x12.asyncio.wait_for", record_timeout
    )
    client = _GattClient(reads={FIRMWARE: firmware, MANUFACTURER: b"star"})
    _coordinator, controller = await _create_controller(hass, client=client)

    await controller.start_notify()

    assert controller.ready
    assert controller._firmware is None
    assert "firmware" not in controller._state
    assert timeouts == [5, 1]


async def test_m1x12_missing_required_characteristic_and_notify_failure_are_not_ready(
    hass: HomeAssistant,
) -> None:
    client = _GattClient(missing={FIRMWARE})
    _coordinator, controller = await _create_controller(hass, client=client)
    with pytest.raises(ConnectionError, match="2a28"):
        await controller.start_notify()
    assert not controller.ready

    notify_client = _GattClient(notify_error=RuntimeError("subscribe failed"))
    _coordinator, notify_controller = await _create_controller(hass, client=notify_client)
    with pytest.raises(RuntimeError, match="subscribe failed"):
        await notify_controller.start_notify()
    assert not notify_controller.ready
    assert notify_client.events[-1] == ("notify", NOTIFY)


async def test_m1x12_stale_version_read_cannot_replace_a_new_client_session(
    hass: HomeAssistant,
) -> None:
    entered = asyncio.Event()
    finish_read = asyncio.Event()
    client = _GattClient()

    async def blocked_read(uuid: str) -> bytes:
        client.events.append(("read", uuid))
        entered.set()
        await finish_read.wait()
        return b"old-session"

    client.read_gatt_char = blocked_read
    coordinator, controller = await _create_controller(hass, client=client)
    start = asyncio.create_task(controller.start_notify())
    await entered.wait()
    coordinator._client = _GattClient()
    finish_read.set()

    with pytest.raises(asyncio.CancelledError):
        await start
    assert controller._firmware is None
    assert not controller.ready


async def test_m1x12_elevate_reads_2a28_and_never_selects_from_2a29(
    hass: HomeAssistant,
) -> None:
    client = _GattClient(reads={FIRMWARE: b"\xffA \t", MANUFACTURER: b"star"})
    coordinator, _entry = _controller_target(
        hass,
        bed_type=BED_TYPE_STAR_ELEVATE,
        name="ELEVATE123456",
        variant=STAR_ELEVATE_VARIANT_M1X12,
        client=client,
    )
    controller = await create_controller(
        coordinator,
        BED_TYPE_STAR_ELEVATE,
        STAR_ELEVATE_VARIANT_M1X12,
        client,
        device_name="ELEVATE123456",
    )
    assert isinstance(controller, StarElevateM1X12Controller)

    await controller.start_notify()

    assert [event for event in client.events if event[0] == "read"] == [("read", FIRMWARE)]
    assert client.events[:2] == [("read", FIRMWARE), ("notify", NOTIFY)]
    assert controller._firmware == "ÿA \t"
    assert controller.ready
    await controller.stop_notify()


@pytest.mark.parametrize(
    "firmware",
    [b"", ValueError("read failed"), TimeoutError("read timed out")],
    ids=["empty", "error", "timeout"],
)
async def test_m1x12_elevate_read_failure_keeps_version_unknown_and_session_ready(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    firmware: bytes | BaseException,
) -> None:
    timeouts: list[float] = []
    original_wait_for = asyncio.wait_for

    async def record_timeout(awaitable, timeout: float):
        timeouts.append(timeout)
        return await original_wait_for(awaitable, timeout)

    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.starcode_m1x12.asyncio.wait_for",
        record_timeout,
    )
    client = _GattClient(reads={FIRMWARE: firmware, MANUFACTURER: b"star"})
    coordinator, _entry = _controller_target(
        hass,
        bed_type=BED_TYPE_STAR_ELEVATE,
        name="ELEVATE123456",
        variant=STAR_ELEVATE_VARIANT_M1X12,
        client=client,
    )
    controller = await create_controller(
        coordinator,
        BED_TYPE_STAR_ELEVATE,
        STAR_ELEVATE_VARIANT_M1X12,
        client,
        device_name="ELEVATE123456",
    )
    assert isinstance(controller, StarElevateM1X12Controller)

    await controller.start_notify()

    assert controller.ready
    assert controller._firmware is None
    assert timeouts == [5]
    assert client.events[:3] == [
        ("read", FIRMWARE),
        ("notify", NOTIFY),
        ("write", WRITE, StarElevateCommands.WAKE, False),
    ]
    assert not any(event[:2] == ("read", MANUFACTURER) for event in client.events)
    await controller.stop_notify()


async def test_m1x12_elevate_requires_firmware_characteristic_before_subscribing(
    hass: HomeAssistant,
) -> None:
    client = _GattClient(missing={FIRMWARE})
    coordinator, _entry = _controller_target(
        hass,
        bed_type=BED_TYPE_STAR_ELEVATE,
        name="ELEVATE123456",
        variant=STAR_ELEVATE_VARIANT_M1X12,
        client=client,
    )
    controller = await create_controller(
        coordinator,
        BED_TYPE_STAR_ELEVATE,
        STAR_ELEVATE_VARIANT_M1X12,
        client,
        device_name="ELEVATE123456",
    )
    assert isinstance(controller, StarElevateM1X12Controller)

    with pytest.raises(ConnectionError, match="2a28"):
        await controller.start_notify()

    assert not controller.ready
    assert client.events == []


async def test_m1x12_held_action_failure_sends_fresh_stop(
    hass: HomeAssistant,
) -> None:
    coordinator, controller = await _create_controller(hass, client=_GattClient())
    controller._ready = True
    controller.dialect = "star"
    events: list[tuple[bytes, asyncio.Event | None]] = []

    async def writer(
        command: bytes,
        repeat_count: int = 1,
        repeat_delay_ms: int = 100,
        cancel_event: asyncio.Event | None = None,
        **_kwargs: Any,
    ) -> None:
        del repeat_count, repeat_delay_ms
        events.append((bytes(command), cancel_event))
        if command == normal_packet(0x03103000, "star"):
            raise RuntimeError("writer failed")

    controller.write_command = writer
    with pytest.raises(RuntimeError, match="writer failed"):
        await controller.hold_control("part_1_up", 100)

    assert [packet for packet, _event in events] == [
        normal_packet(0x03103000, "star"),
        normal_packet(0x0310300F, "star"),
    ]
    assert events[-1][1] is not coordinator.cancel_command
    assert events[-1][1] is not None and events[-1][1].is_set() is False
