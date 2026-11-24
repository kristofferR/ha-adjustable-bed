"""Dorsal wire parity and session behavior for the ordinary and restored routes."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.adjustable_bed.beds.builder import BuildContext
from custom_components.adjustable_bed.beds.dorsal.controller import (
    DorsalController,
    build_controller,
)
from custom_components.adjustable_bed.beds.dorsal.receive import Alarm, Stream, decode
from custom_components.adjustable_bed.beds.richmat.transport import select_app_link
from custom_components.adjustable_bed.codec import richmat
from custom_components.adjustable_bed.discovery_hints.dorsal import DORSAL_TRANSPORTS
from custom_components.adjustable_bed.profiles import dorsal
from tests.dorsal_vectors import CONTROL, ROOMI, STATUS

_STD = "00001801-0000-1000-8000-00805f9b34fb"
_CHANGED = "00002a05-0000-1000-8000-00805f9b34fb"
_ALT_RX = "12340000-0000-1000-8000-00805f9b34fb"


def _characteristic(uuid, *properties):
    return SimpleNamespace(uuid=uuid, properties=properties, handle=1)


def _gatt(service, write, notify, *, other_notify=False):
    return SimpleNamespace(
        uuid=service.upper(),
        characteristics=[
            *([_characteristic(_ALT_RX, "notify")] if other_notify else []),
            _characteristic(write.upper(), "write", "write-without-response"),
            _characteristic(notify, "notify"),
        ],
    )


def _client(*services):
    return SimpleNamespace(
        is_connected=True,
        services=services,
        write_gatt_char=AsyncMock(),
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
    )


class Coordinator:
    def __init__(self, client):
        self.client = client
        self.address = "00:11:22:33:44:55"
        self.cancel_command = asyncio.Event()
        self.motor_pulse_count = 2
        self.record_command_trace = MagicMock()
        self.handle_controller_state_updates = MagicMock()
        self.entry = SimpleNamespace(data={})


def _wire(client):
    return [args[1].hex(" ") for args, _ in client.write_gatt_char.await_args_list]


@pytest.mark.parametrize(
    ("transport", "service", "write", "notify"),
    [
        (
            "n1",
            "6e400001-b5a3-f393-e0a9-e50e24dcca9e",
            "6e400002-b5a3-f393-e0a9-e50e24dcca9e",
            "6e400003-b5a3-f393-e0a9-e50e24dcca9e",
        ),
        (
            "w1",
            "0000fee9-0000-1000-8000-00805f9b34fb",
            "d44bc439-abfd-45a2-b575-925416129600",
            "d44bc439-abfd-45a2-b575-925416129601",
        ),
        (
            "w2",
            "0000fee9-0000-1000-8000-00805f9b34bb",
            "d44bc439-abfd-45a2-b575-925416129622",
            "d44bc439-abfd-45a2-b575-925416129611",
        ),
        (
            "w3",
            "0000ffe0-0000-1000-8000-00805f9b34fb",
            "0000ffe2-0000-1000-8000-00805f9b34fb",
            "0000ffe1-0000-1000-8000-00805f9b34fb",
        ),
        (
            "w4",
            "0000fff0-0000-1000-8000-00805f9b34fb",
            "0000fff2-0000-1000-8000-00805f9b34fb",
            "0000fff1-0000-1000-8000-00805f9b34fb",
        ),
        (
            "w5",
            "0000e0ff-3c17-d293-8e48-14fe2e4da212",
            "00000002-3c17-d293-8e48-14fe2e4da212",
            "00000003-3c17-d293-8e48-14fe2e4da212",
        ),
    ],
)
def test_six_exact_gatt_routes(transport, service, write, notify):
    link = select_app_link(_client(_gatt(service, write, notify)), DORSAL_TRANSPORTS)
    assert link.tx.uuid.lower() == write
    assert link.rx.uuid == notify
    assert link.query_single == (transport == "n1")


def test_dorsal_own_literals_select_the_richmat_codec():
    for name, bare, framed in CONTROL:
        opcode = int(bare, 16)
        selector = {
            "Exit limit": "deviceFunctionItemExitLimit",
            "Check clock": "deviceFunctionItemCheckClock",
            "Check light": "deviceFunctionItemCheckLight",
        }.get(name, "")
        assert richmat.function(opcode, action=selector, single=True).hex(" ") == bare
        assert richmat.function(opcode, action=selector).hex(" ") == framed
    # The retained clock builders use the same wire format, even though the
    # normal settings path never permits this clock action on Dorsal.
    zone, _ = richmat.time_sync(
        datetime.fromtimestamp(0x01020304, timezone(timedelta(hours=-1))),
        build=richmat.record_20_len,
        first_hex=True,
    )
    assert zone.hex(" ") == "6e 20 0c 08 02 01 01 02 03 04 ff ae"
    assert (
        richmat.calendar(
            datetime(2026, 11, 24, 6, 34, 7, tzinfo=UTC), build=richmat.record_20_len
        ).hex(" ")
        == "6e 20 0d 08 03 01 38 0b 18 06 22 07 31"
    )
    actual = (
        [(item.sustain or item.short)[1] for item in dorsal.ROOMI]
        + [item.long[1] for item in dorsal.ROOMI if item.long]
        + [richmat.STOP]
    )
    assert sorted(actual) == sorted(opcode for _, opcode, _ in ROOMI)
    for _, opcode, expected in ROOMI:
        assert richmat.command(opcode).hex(" ") == expected


def test_profile_admission_and_restored_overrides():
    assert dorsal.code_for("cprn", "CORN") == "CPRN"
    assert dorsal.code_for("corn", "") == "CORN"
    for invalid in ("a0rm", " A0RM", "QRRN", "FWRM", "ZR90", ""):
        assert dorsal.code_for("restored", invalid) is None
    assert dorsal.code_for("restored", "QRRM") == "QRRM"
    assert not dorsal.products()["QRRM"].controls
    assert len(dorsal.products()) == 1262
    pillow = next(c for c in dorsal.products()["A0RM"].controls if c.action.endswith("PillowUp"))
    lounge = next(
        c for c in dorsal.products()["A3RM"].controls if c.action.endswith("LoungePosition")
    )
    assert richmat.function(pillow.sustain[0], single=True).hex() == "3f"
    assert richmat.function(pillow.sustain[1]).hex() == "6e01003fae"
    assert richmat.function(lounge.short[0], single=True).hex() == "32"
    assert richmat.function(lounge.short[1]).hex() == "6e010059c8"


async def test_roomi_requires_exact_receiver_name(hass, monkeypatch):
    from custom_components.adjustable_bed.beds.dorsal import transport

    monkeypatch.setattr(
        transport.bluetooth, "async_last_service_info", MagicMock(return_value=None)
    )
    coordinator = Coordinator(_client())
    coordinator.hass = hass
    context = BuildContext(
        coordinator=coordinator,
        bed_type="dorsal",
        variant="roomi",
        client=coordinator.client,
        device_name="qrrm123",
    )
    with pytest.raises(Exception, match="QRRM"):
        await build_controller(context)


async def test_startup_subscription_and_cached_profile_admission(monkeypatch):
    monkeypatch.setattr(dorsal, "PROBE_SECONDS", 0)
    n1, w1 = (richmat.TRANSPORTS[key] for key in ("n1", "w1"))
    standard = SimpleNamespace(uuid=_STD, characteristics=[_characteristic(_CHANGED, "indicate")])
    client = _client(
        standard,
        _gatt(n1.service_uuid, n1.write_uuid, n1.notify_uuid, other_notify=True),
        _gatt(w1.service_uuid, w1.write_uuid, w1.notify_uuid),
    )
    coordinator = Coordinator(client)
    controller = DorsalController(coordinator, "cprn", "CPRN")
    session = SimpleNamespace(async_start_notify=controller.start_notify)
    await controller.async_on_connect(session)
    assert [call.args[0].uuid for call in client.start_notify.await_args_list] == [
        _CHANGED,
        _ALT_RX,
    ]
    assert [c.args[0].uuid.lower() for c in client.write_gatt_char.await_args_list] == [
        n1.write_uuid
    ] * 4
    assert all(c.kwargs["response"] is False for c in client.write_gatt_char.await_args_list)
    assert _wire(client) == ["6e 02 01 00 71", "6e 02 01 00 71", "6e 08 01 01 78", "6e 0a 00 01 79"]
    # The standard indication reaches its own sink and cannot produce a bed update.
    char, indication = client.start_notify.await_args_list[0].args
    indication(char, bytearray.fromhex("6e 90 00 04 00"))
    assert "protocol_version" not in controller.protocol_diagnostics["dorsal"]

    controller.on_disconnect()
    client.write_gatt_char.reset_mock()
    controller = DorsalController(coordinator, "cprn", "CPRN")
    await controller.async_on_connect(SimpleNamespace(async_start_notify=controller.start_notify))
    assert _wire(client) == ["6e 02 01 00 71"]


async def test_roomi_stage3_does_not_probe_and_fixed_writes_use_nordic(monkeypatch):
    monkeypatch.setattr(dorsal, "PROBE_SECONDS", 0)
    n1 = richmat.TRANSPORTS["n1"]
    client = _client(_gatt(n1.service_uuid, n1.write_uuid, n1.notify_uuid))
    coordinator = Coordinator(client)
    controller = DorsalController(coordinator, "roomi", None)
    await controller.async_on_connect(SimpleNamespace(async_start_notify=controller.start_notify))
    await controller.preset_anti_snore()
    await controller.run_control(dorsal.ROOMI_SNORE.key)
    await controller.set_massage_timer(20)
    await controller.program_memory(1)
    assert _wire(client) == [
        "00",
        "6e 01 00 46 b5",
        "6e 01 00 6e dd",
        "46",
        "6e 01 00 63 d2",
        "6e 01 00 6e dd",
        "6e 01 00 2b 9a",
        "6e 01 00 6e dd",
    ]


async def test_cancel_pending_refresh_then_release_the_same_link(monkeypatch):
    transport = richmat.TRANSPORTS["w1"]
    client = _client(_gatt(transport.service_uuid, transport.write_uuid, transport.notify_uuid))
    coordinator = Coordinator(client)
    controller = DorsalController(coordinator, "cprn", "CPRN")
    await controller.start_notify()
    first_write = asyncio.Event()
    finish_write = asyncio.Event()
    stop = bytes.fromhex("6e 01 00 6e dd")

    async def write(_char, wire, **_kwargs):
        if wire != stop:
            first_write.set()
            await finish_write.wait()

    client.write_gatt_char.side_effect = write

    async def crossing(_seconds, cancel):
        await asyncio.sleep(0)
        return not cancel.is_set()

    monkeypatch.setattr(controller, "_delay", crossing)
    task = asyncio.create_task(controller.move_head_up())
    await first_write.wait()
    coordinator.cancel_command.set()
    finish_write.set()
    await task
    assert _wire(client) == ["6e 01 00 24 93", "6e 01 00 6e dd"]


def test_receive_progress_and_alarm_tail_parity():
    stream = Stream()
    motor = bytes.fromhex("6e 20 0d 01 03 02 01 00 6e 02 01 2c 3f")
    common = bytes.fromhex("6e 90 39 14 00")
    assert stream.feed(bytes.fromhex("ff 6e 20 00") + motor[:9]) == []
    assert stream.feed(motor[9:] + common) == [motor, common]
    assert decode(motor) == {"motor_angle": ((1, 110), (2, 300))}
    assert decode(common) == {"motor_status": ((2, 1, 20),)}
    assert decode(bytes.fromhex("6e 90 a2 9c 00")) == {
        "massage_mode": 1,
        "massage_1": 2,
        "massage_2": 3,
        "massage_3": 4,
    }
    assert decode(bytes.fromhex("6e 20 0f 0f 02 02 01 01 2c a5 02 00 1e 5a fd")) == {
        "sleep_aid_timers": ((1, 300), (2, 30))
    }
    assert decode(bytes.fromhex("6e 09 01 00 78")) == {"clock_available": True}
    assert decode(bytes.fromhex("6e 0e 00 03 7f")) == {"light_available": True}
    reply = bytes.fromhex("6e 20 0f 05 01 03 02 01 06 1e 00 3e 24 99 c8")
    assert decode(reply) == Alarm(2, 1, 6, 30, 0, 0x3E, b"\x24\x99")
    assert decode(reply[:-1] + b"\x00") == {}
    assert Alarm(2, 1, 6, 30, 0xFF, 0x3F, b"\x24\x99").encode().hex(" ") == (
        "6e 20 0f 05 01 01 02 01 06 1e 00 3f 24 99 c7"
    )
    assert Alarm(2, 0, 6, 30, 0xFF, 0x3E, b"\x24").encode().hex(" ") == (
        "6e 20 0e 05 01 01 02 00 06 1e ff 3e 24 2a"
    )
    assert richmat.record_20_len(5, 1, 0, (0,)).hex(" ") == "6e 20 08 05 01 00 00 9c"
    assert richmat.record_20_len(5, 2, 1, (2,)).hex(" ") == "6e 20 08 05 02 01 02 a0"


def test_status_transforms_from_dorsal_literals():
    packets = []
    for _, wire, _ in STATUS:
        packet = decode(bytes.fromhex(wire))
        assert isinstance(packet, dict)
        packets.append(packet)
    height, rgb, rgb_timer, *heating = packets
    assert (
        height["motor_height"],
        height["motor_height_type"],
        height["height_angle"],
        height["monitor_height"],
    ) == STATUS[0][2]
    colors = rgb["rgb"]
    assert isinstance(colors, tuple)
    assert (1.0, *colors) == STATUS[1][2]
    assert rgb_timer["rgb_timer"] == STATUS[2][2]
    assert [packet["heating_timer"] for packet in heating] == [row[2] for row in STATUS[3:]]


def test_roomi_save_buttons_are_confirmed_and_have_no_hold():
    controller = DorsalController(Coordinator(None), "roomi", None)
    saves = [spec for spec in controller.controller_button_specs if spec.key.endswith("_save")]
    assert len(saves) == 6
    assert controller.memory_slots_programmed_by_presets == {1, 2}
    assert all(spec.requires_confirmation and spec.hold is None for spec in saves)
    assert not controller.supports_single_address_pairing
    assert not controller.supports_clock_sync
    assert not controller.supports_device_rename


async def test_shared_alarm_edit_preserves_the_opaque_record(monkeypatch):
    from custom_components.adjustable_bed.alarm import AlarmRequest

    transport = richmat.TRANSPORTS["w1"]
    client = _client(_gatt(transport.service_uuid, transport.write_uuid, transport.notify_uuid))
    controller = DorsalController(Coordinator(client), "restored", "A4RN")
    assert controller.alarm_capability is not None
    assert "none" in controller.alarm_capability.wake_actions
    await controller.start_notify()
    existing = Alarm(2, 1, 6, 30, 0, 0x3E, b"\x24\x99")
    monkeypatch.setattr(controller, "refresh_alarms", AsyncMock(return_value={2: existing}))
    await controller.configure_alarm(
        AlarmRequest(
            enabled=True,
            slot=2,
            hour=7,
            minute=10,
            weekdays=(0, 6),
            reference_time=datetime(2026, 11, 24, tzinfo=UTC),
        )
    )
    assert _wire(client) == ["6e 20 0f 05 01 01 02 01 07 0a 00 83 24 99 f8"]


async def test_shared_alarm_edit_requires_a_current_slot_report(monkeypatch):
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.adjustable_bed.alarm import AlarmRequest

    transport = richmat.TRANSPORTS["w1"]
    client = _client(_gatt(transport.service_uuid, transport.write_uuid, transport.notify_uuid))
    controller = DorsalController(Coordinator(client), "restored", "A4RN")
    await controller.start_notify()
    monkeypatch.setattr(controller, "refresh_alarms", AsyncMock(return_value={}))
    request = AlarmRequest(
        enabled=True,
        slot=2,
        hour=7,
        minute=10,
        wake_action="zero_g",
        reference_time=datetime(2026, 11, 24, tzinfo=UTC),
    )
    for step in (controller.check_alarm, controller.configure_alarm):
        with pytest.raises(HomeAssistantError, match="slot"):
            await step(request)
    assert _wire(client) == []

    await controller.create_or_replace_alarm(request)
    assert _wire(client) == ["6e 20 0d 05 01 01 02 00 07 0a 45 01 fb"]


@pytest.mark.parametrize(
    ("name", "connectable_name", "all_name", "writable", "error"),
    [
        ("qrrm0001", None, None, True, "dorsal_roomi_receiver"),
        ("QRRM0001", None, None, False, "dorsal_receiver_unavailable"),
        ("QRRM0001", None, None, True, None),
        ("Controller", "QRRM0001", "Controller", True, None),
        ("Controller", "Controller", "QRRM0001", True, None),
    ],
)
async def test_roomi_setup_probe_checks_the_exact_receiver(
    hass, monkeypatch, name, connectable_name, all_name, writable, error
):
    from custom_components.adjustable_bed import config_flow
    from tests.test_config_flow import _fresh_gate

    transport = richmat.TRANSPORTS["w1"]
    service = _gatt(transport.service_uuid, transport.write_uuid, transport.notify_uuid)
    if not writable:
        # A writer with the wrong UUID is insufficient, even when it is writable.
        service.characteristics[0].uuid = _ALT_RX
    client = _client(service)
    client.disconnect = AsyncMock()
    flow = config_flow.AdjustableBedConfigFlow()
    flow.hass = hass
    freshness, device = _fresh_gate("hci0", -55)
    device.name = name
    monkeypatch.setattr(
        config_flow, "async_gate_connection", lambda *_args, **_kwargs: (freshness, device)
    )
    monkeypatch.setattr(
        "bleak_retry_connector.establish_connection", AsyncMock(return_value=client)
    )

    def advertisement(_hass, _address, *, connectable):
        seen = connectable_name if connectable else all_name
        return SimpleNamespace(name=seen) if seen is not None else None

    monkeypatch.setattr(config_flow.bluetooth, "async_last_service_info", advertisement)
    monkeypatch.setattr(config_flow, "discover_services", AsyncMock())
    monkeypatch.setattr(config_flow, "read_ble_device_info", AsyncMock(return_value=(None, None)))

    result = await flow._probe_capabilities("AA:BB:CC:DD:EE:01", "auto", "dorsal", "roomi")
    assert result.connected is (error is None)
    assert result.dorsal_endpoint_error == error
    assert _wire(client) == []
    client.disconnect.assert_awaited_once()

    coordinator = Coordinator(client)
    coordinator.hass = hass
    context = BuildContext(
        coordinator=coordinator,
        bed_type="dorsal",
        variant="roomi",
        client=client,
        device_name=name,
        advertisement_name=all_name,
    )
    if error == "dorsal_roomi_receiver":
        from homeassistant.exceptions import ServiceValidationError

        with pytest.raises(ServiceValidationError, match="QRRM"):
            await build_controller(context)
    elif error is None:
        assert (await build_controller(context)).route == "roomi"

    flow._manual_data = {"bed_type": "dorsal", "protocol_variant": "roomi"}
    assert flow._migration_requires_check


async def test_compound_move_sends_one_write_then_stop_at_release(monkeypatch):
    transport = richmat.TRANSPORTS["w1"]
    client = _client(_gatt(transport.service_uuid, transport.write_uuid, transport.notify_uuid))
    controller = DorsalController(Coordinator(client), "restored", "APRM")
    await controller.start_notify()
    move = next(
        spec for spec in controller.controller_button_specs if spec.name == "Head up and foot down"
    )
    assert move.hold is not None and move.hold.control in controller.held_control_options

    async def delay(seconds, _cancel):
        assert seconds == 0.4
        assert _wire(client) == ["6e 01 00 21 90"]
        return True

    monkeypatch.setattr(controller, "_delay", delay)
    await controller.hold_control(move.hold.control, 400)
    assert _wire(client) == ["6e 01 00 21 90", "6e 01 00 6e dd"]


async def test_offline_roomi_has_capabilities_without_a_live_receiver_name():
    from custom_components.adjustable_bed.const import OFFLINE_CAPABILITY_SAFE_BED_TYPES

    coordinator = Coordinator(None)
    context = BuildContext(coordinator=coordinator, bed_type="dorsal", variant="roomi", client=None)
    controller = await build_controller(context)
    assert "dorsal" in OFFLINE_CAPABILITY_SAFE_BED_TYPES
    assert controller.memory_slot_count == 2
    assert controller.motor_control_specs


@pytest.mark.parametrize("during_write", [False, True])
async def test_massage_switch_follows_receiver_feedback(during_write):
    from custom_components.adjustable_bed.state_keys import MASSAGE_ACTIVE

    transport = richmat.TRANSPORTS["w1"]
    client = _client(_gatt(transport.service_uuid, transport.write_uuid, transport.notify_uuid))
    coordinator = Coordinator(client)
    controller = DorsalController(coordinator, "restored", "FCRM")
    await controller.start_notify()
    (switch,) = controller.controller_switch_specs
    assert switch.state_key is MASSAGE_ACTIVE
    char, callback = client.start_notify.await_args.args

    def report_off():
        callback(char, bytearray(richmat.record_20_len(2, 6, 2, (0, 0))))

    if during_write:

        async def write(_char, frame, **_kwargs):
            if frame[3] == 0x5D:
                report_off()

        client.write_gatt_char.side_effect = write
    await switch.set_fn(controller, True)
    if not during_write:
        coordinator.handle_controller_state_updates.assert_called_with(MASSAGE_ACTIVE(True))
        report_off()
    coordinator.handle_controller_state_updates.assert_called_with(MASSAGE_ACTIVE(False))


def test_dorsal_alarm_schema_requires_a_whole_slot():
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed.beds.dorsal.services import register_services

    hass = MagicMock()
    register_services(hass)
    schema = hass.services.async_register.call_args.kwargs["schema"]
    request = {"device_id": "receiver", "operation": "delete"}
    assert schema({**request, "slot": 2.0})["slot"] == 2
    for slot in (2.9, True):
        with pytest.raises(ServiceValidationError):
            schema({**request, "slot": slot})


async def test_create_alarm_rejects_enabled_input_before_dispatch(hass, monkeypatch):
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed.beds.dorsal import services

    monkeypatch.setattr(services, "_call_targets", lambda _call: [(None, "both")])
    monkeypatch.setattr(services, "_command_targets", lambda _parent, _side: [None])
    execute = AsyncMock()
    monkeypatch.setattr(services, "_preflight_and_execute", execute)
    services.register_services(hass)
    with pytest.raises(ServiceValidationError, match="Omit the on setting"):
        await hass.services.async_call(
            "adjustable_bed",
            "dorsal_alarm",
            {
                "device_id": "receiver",
                "operation": "create_or_replace",
                "slot": 2,
                "time": "07:10",
                "wake_action": "zero_g",
                "enabled": False,
            },
            blocking=True,
        )
    execute.assert_not_called()
