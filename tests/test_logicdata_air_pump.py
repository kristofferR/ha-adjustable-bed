"""Sleep Smart Air Mattress 1.0.0 pump: frozen row053 P4 vectors and lifecycle."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds import logicdata_air_pump as pump
from custom_components.adjustable_bed.beds.logicdata_air_pump import LogicdataAirPumpController
from custom_components.adjustable_bed.const import (
    BED_TYPE_LOGICDATA_AIR_PUMP,
    CONF_BED_TYPE,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_PREFERRED_ADAPTER,
    DOMAIN,
    disconnect_after_command_default_enabled,
)
from custom_components.adjustable_bed.detection import detect_bed_type_detailed

# All ten P4 command rows, in report order.
ROWS = [
    ("firmness_30", "433e534554503e303e33300a"),
    ("inflate", "433e46494c4c3e300a"),  # also the "60" mode button
    ("deflate", "433e4558434150453e300a"),
    ("recall_memory", "433e4d454d4f52593e300a"),
]


def test_command_rows_are_byte_exact():
    for key, expected in ROWS:
        assert pump.COMMANDS[key].hex() == expected
    assert pump.STOP.hex() == "433e53544f504e0a"
    assert pump.SAVE_MEMORY.hex() == "433e4d454d5f533e300a"
    assert pump.QUERY_PRESSURE.hex() == "523e53503e300a"
    assert [frame.hex() for frame in pump.rename_frames("Bed")] == [
        "41542b454e41540d0a",
        "41542b4c454e414265640d0a",
        "41542b524553540d0a",
    ]


@pytest.mark.parametrize("name", ["", "Bed 1", "Å", "a" * 21])
def test_rename_rejects_names_outside_the_edit_field(name):
    with pytest.raises(ValueError, match="1..20"):
        pump.rename_frames(name)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("RET>SP>0000001E", 30),
        ("RET>SP>000000FF", 255),
        ("RET>SP>000000ff", 255),
        ("RET>SP>12", None),
        ("RET>SP>000000ZZ", None),
        ("RET>SP>000000 A", None),
        ("RET>SP>000000A ", None),
        ("RET>SP>000000+A", 10),
        ("RET>SP>000000-A", -10),
        ("RET>SP>000000++", None),
        ("XRET>SP>0000001E", None),
        ("RET>SP>0000001E trailing", 30),
    ],
)
def test_pressure_parser_follows_java_radix16(text, expected):
    assert pump.parse_pressure(text.encode()) == expected


def test_pressure_parser_counts_utf16_units():
    # An astral character occupies two UTF-16 units before the field.
    assert pump.parse_pressure("RET>SP>\U0001f600000041".encode()) == 0x41
    assert pump.parse_pressure("RET>SP>00000\U0001f600".encode()) is None


@pytest.fixture
def coordinator():
    coordinator = MagicMock()
    coordinator.cancel_command = asyncio.Event()
    coordinator.client.is_connected = True
    coordinator.client.write_gatt_char = AsyncMock()
    coordinator.client.start_notify = AsyncMock()
    coordinator.client.stop_notify = AsyncMock()
    characteristics = {uuid: MagicMock(uuid=uuid) for uuid in (pump.WRITE_UUID, pump.NOTIFY_UUID)}
    service = MagicMock(uuid=pump.SERVICE_UUID)
    service.get_characteristic.side_effect = characteristics.get
    coordinator.client.services.get_service.side_effect = (
        lambda uuid: service if uuid == pump.SERVICE_UUID else None
    )
    coordinator.client.services.get_characteristic.side_effect = characteristics.get
    return coordinator


def writes(coordinator):
    return [call.args[1] for call in coordinator.client.write_gatt_char.call_args_list]


@pytest.fixture
def waits():
    requested: list[float] = []

    async def wait(self, seconds, event):
        requested.append(round(seconds, 2))
        return not event.is_set()

    with patch.object(LogicdataAirPumpController, "_wait", wait):
        yield requested


async def test_taps_write_with_response_and_keep_500_ms_spacing(coordinator, waits):
    controller = LogicdataAirPumpController(coordinator)
    await controller.press("inflate")
    await controller.press("deflate")
    assert writes(coordinator) == [pump.COMMANDS["inflate"], pump.COMMANDS["deflate"]]
    assert waits == [0.5]
    for call in coordinator.client.write_gatt_char.call_args_list:
        assert call.args[0] == pump.WRITE_UUID
        assert call.kwargs["response"] is True


async def test_save_stops_then_saves_after_the_throttle(coordinator, waits):
    controller = LogicdataAirPumpController(coordinator)
    await controller.press("save_memory")
    assert writes(coordinator) == [pump.STOP, pump.SAVE_MEMORY]
    assert waits == [0.5]


async def test_cancel_during_save_wait_sends_only_the_stop(coordinator):
    controller = LogicdataAirPumpController(coordinator)

    async def wait(seconds, event):
        coordinator.cancel_command.set()
        return False

    with patch.object(controller, "_wait", side_effect=wait):
        await controller.press("save_memory")
    assert writes(coordinator) == [pump.STOP]


async def test_stop_is_immediate_and_uses_a_fresh_event(coordinator, waits):
    controller = LogicdataAirPumpController(coordinator)
    await controller.press("inflate")
    coordinator.cancel_command.set()
    await controller.stop_all()
    assert writes(coordinator) == [pump.COMMANDS["inflate"], pump.STOP]
    assert waits == []


async def test_rename_sends_three_phases_at_0_50_100_ms(coordinator, waits):
    controller = LogicdataAirPumpController(coordinator)
    with pytest.raises(ValueError):
        controller.validate_device_rename("Bad name")
    await controller.rename_device("Bed")
    assert writes(coordinator) == list(pump.rename_frames("Bed"))
    assert waits == [0.0, 0.05, 0.1]


async def test_pressure_polls_after_800_ms_then_every_500_ms(coordinator):
    controller = LogicdataAirPumpController(coordinator)
    updates: list[dict] = []
    controller.forward_controller_state_updates = updates.append
    sleeps: list[float] = []

    async def sleep(seconds):
        sleeps.append(round(seconds, 1))

    await controller.start_notify()
    # The coordinator invalidates diagnostics when it schedules polling, after
    # start_notify; that must not cancel the 800 ms first query.
    controller.invalidate_diagnostics()
    coordinator.client.start_notify.assert_awaited_once()
    assert coordinator.client.start_notify.await_args.args[0] == pump.NOTIFY_UUID
    assert controller.diagnostic_poll_interval == 0.5
    with patch.object(pump.asyncio, "sleep", side_effect=sleep):
        await controller.async_refresh_diagnostics()
        await controller.async_refresh_diagnostics()
    assert sleeps == [0.8, 0.5]
    assert writes(coordinator) == [pump.QUERY_PRESSURE] * 2
    handler = coordinator.client.start_notify.await_args.args[1]
    handler(SimpleNamespace(uuid=pump.NOTIFY_UUID), bytearray(b"RET>SP>0000001E"))
    handler(SimpleNamespace(uuid=pump.NOTIFY_UUID), bytearray(b"RET>SP>12"))
    controller.invalidate_diagnostics()
    assert updates == [
        {pump.PRESSURE_STATE: None},
        {pump.PRESSURE_STATE: 30},
        {pump.PRESSURE_STATE: None},
    ]
    await controller.stop_notify()
    await controller.async_refresh_diagnostics()
    assert writes(coordinator) == [pump.QUERY_PRESSURE] * 2


async def test_discovery_requires_the_pump_service_and_write_role(coordinator):
    controller = LogicdataAirPumpController(coordinator)
    await controller.async_discover_capabilities()
    coordinator.client.services.get_service.side_effect = lambda uuid: None
    with pytest.raises(ValueError, match="ffe0"):
        await controller.async_discover_capabilities()


def test_pump_has_no_motor_or_bed_preset_capabilities(coordinator):
    controller = LogicdataAirPumpController(coordinator)
    assert controller.motor_control_specs == ()
    assert not controller.supports_preset_flat
    assert controller.memory_slot_count == 0
    assert controller.supports_device_rename
    assert [spec.key for spec in controller.controller_button_specs] == [
        "logicdata_air_pump_inflate",
        "logicdata_air_pump_deflate",
        "logicdata_air_pump_firmness_30",
        "logicdata_air_pump_recall_memory",
        "logicdata_air_pump_save_memory",
    ]
    # The shared ffe0 service never selects the pump automatically.
    assert not disconnect_after_command_default_enabled(BED_TYPE_LOGICDATA_AIR_PUMP)


def test_shared_service_never_detects_the_pump():
    info = SimpleNamespace(
        name="Pump",
        address="AA:BB:CC:DD:EE:01",
        service_uuids=[pump.SERVICE_UUID],
        manufacturer_data={},
        service_data={},
    )
    assert detect_bed_type_detailed(info).bed_type != BED_TYPE_LOGICDATA_AIR_PUMP


async def test_entry_exposes_pump_controls_without_motors(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations
):
    characteristics = {
        uuid: SimpleNamespace(
            uuid=uuid, properties=["write", "notify"], descriptors=[], handle=handle,
            description="Pump characteristic",
        )
        for handle, uuid in enumerate((pump.WRITE_UUID, pump.NOTIFY_UUID), start=1)
    }
    service = SimpleNamespace(
        uuid=pump.SERVICE_UUID,
        characteristics=list(characteristics.values()),
        get_characteristic=characteristics.get,
    )
    mock_bleak_client.services.__iter__ = lambda self: iter((service,))
    mock_bleak_client.services.get_service = MagicMock(
        side_effect=lambda uuid: service if uuid == pump.SERVICE_UUID else None
    )
    mock_bleak_client.services.get_characteristic = MagicMock(side_effect=characteristics.get)
    mock_bleak_client.write_gatt_char.side_effect = None
    address = "AA:BB:CC:DD:EE:FF"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Air pump",
        data={
            CONF_ADDRESS: address,
            CONF_NAME: "Air pump",
            CONF_BED_TYPE: BED_TYPE_LOGICDATA_AIR_PUMP,
            CONF_PREFERRED_ADAPTER: "auto",
            CONF_DISCONNECT_AFTER_COMMAND: False,
        },
        unique_id=address,
    )
    entry.add_to_hass(hass)
    with patch.object(LogicdataAirPumpController, "_wait", AsyncMock(return_value=True)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        rows = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        keys = {(row.domain, row.unique_id.removeprefix(f"{address}_")) for row in rows}
        assert not {domain for domain, _ in keys} & {"cover", "light", "number"}
        assert {
            ("button", f"logicdata_air_pump_{key}")
            for key in ("inflate", "deflate", "firmness_30", "recall_memory", "save_memory")
        } <= keys
        assert ("button", "stop") in keys
        assert ("sensor", "logicdata_air_pump_pressure") in keys
        assert not any(key.startswith(("preset_", "program_memory_")) for _, key in keys)
        mock_bleak_client.write_gatt_char.reset_mock()
        entity_id = er.async_get(hass).async_get_entity_id(
            "button", DOMAIN, f"{address}_logicdata_air_pump_deflate"
        )
        await hass.services.async_call("button", "press", {"entity_id": entity_id}, blocking=True)
    assert mock_bleak_client.write_gatt_char.await_args_list[-1].args[:2] == (
        pump.WRITE_UUID,
        pump.COMMANDS["deflate"],
    )
