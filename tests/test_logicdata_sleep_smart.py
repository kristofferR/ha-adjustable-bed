"""Sleep Smart Air Mattress 1.0.0 bed profile: frozen row053 vectors and lifecycle."""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError

from custom_components.adjustable_bed import logicdata_app_protocol as protocol
from custom_components.adjustable_bed.beds.logicdata_app import LogicdataAppController

T1, T2, T3 = (protocol.TRANSPORTS[key] for key in ("t1", "t2", "t3"))

# Every reachable P1 command row in the accepted report, by row number. P2 and
# P3 rows carry identical bytes on their own write role.
ROWS = {
    1: ("f1f1010101037e", lambda: protocol.sleep_smart_motion_command("p1", "back", True)),
    2: ("f1f1020101047e", lambda: protocol.sleep_smart_motion_command("p1", "back", False)),
    3: ("f1f1030101057e", lambda: protocol.sleep_smart_motion_command("p1", "legs", True)),
    4: ("f1f1040101067e", lambda: protocol.sleep_smart_motion_command("p1", "legs", False)),
    5: ("f1f1050101077e", lambda: protocol.sleep_smart_motion_command("p2", "both", True)),
    6: ("f1f1060101087e", lambda: protocol.sleep_smart_motion_command("p1", "both", False)),
    7: ("f1f101020000037e", lambda: protocol.sleep_smart_motion_command("p2", "back", True)),
    8: ("f1f102020000047e", lambda: protocol.sleep_smart_motion_command("p2", "back", False)),
    9: ("f1f103020000057e", lambda: protocol.sleep_smart_motion_command("p2", "legs", True)),
    10: ("f1f104020000067e", lambda: protocol.sleep_smart_motion_command("p2", "legs", False)),
    11: ("f1f1070101097e", lambda: protocol.held_preset_command("zero_g")),
    12: ("f1f10801010a7e", lambda: protocol.held_preset_command("flat")),
    13: ("f1f10901010b7e", lambda: protocol.held_preset_command("anti_snore")),
    14: ("f1f10b01010d7e", lambda: protocol.held_preset_command("memory_1")),
    15: ("f1f10a000a7e", lambda: protocol.SLEEP_SMART_MEMORY_SAVE),
    16: ("f1f14e004e7e", lambda: protocol.P1_RELEASE),
    17: ("f1f14e020000507e", lambda: protocol.P2_RELEASE),
    18: ("f1f10f000f7e", lambda: protocol.light_command("p1")),
    19: ("f1f1120208001c7e", lambda: protocol.massage_command("back", 0)),
    20: ("f1f1120208021e7e", lambda: protocol.massage_command("back", 1)),
    21: ("f1f1120208031f7e", lambda: protocol.massage_command("back", 2)),
    22: ("f1f112020804207e", lambda: protocol.massage_command("back", 3)),
    23: ("f1f1140208001e7e", lambda: protocol.massage_command("legs", 0)),
    24: ("f1f114020802207e", lambda: protocol.massage_command("legs", 1)),
    25: ("f1f114020803217e", lambda: protocol.massage_command("legs", 2)),
    26: ("f1f114020804227e", lambda: protocol.massage_command("legs", 3)),
    27: ("f1f1220208002c7e", lambda: protocol.massage_command("right", 0)),
    28: ("f1f1220208022e7e", lambda: protocol.massage_command("right", 1)),
    29: ("f1f1220208032f7e", lambda: protocol.massage_command("right", 2)),
    30: ("f1f122020804307e", lambda: protocol.massage_command("right", 3)),
    31: ("f1f11101081a7e", lambda: protocol.MASSAGE_STOP),
    32: ("f1f116010a217e", lambda: protocol.MASSAGE_MODE),
    33: ("f1f11d0200001f7e", lambda: protocol.FACTORY_RESET),
    34: ("f1f100024000427e", lambda: protocol.QUERY_SOFTWARE),
    35: ("f1f1000108097e", lambda: protocol.QUERY_VIBRATION),
    36: ("f1f1000140417e", lambda: protocol.QUERY_HARDWARE),
    37: ("f1f1000150517e", lambda: protocol.QUERY_ACTUATOR),
    38: ("f1f100020100037e", lambda: protocol.QUERY_LIGHT),
    39: ("f1f10000007e", lambda: protocol.QUERY_STATUS),
    41: ("f1f1000208000a7e", lambda: protocol.QUERY_MASSAGE),
}


@pytest.mark.parametrize("row", sorted(ROWS))
def test_every_fixed_command_row_is_byte_exact(row):
    expected, build = ROWS[row]
    assert build().hex() == expected


def test_dynamic_rows_reproduce_the_report_vectors():
    # Row 40, middle hardware query, is the software-config frame (V-cmdHardConfig).
    assert protocol.FACTORY_RESET.hex() == "f1f11d0200001f7e"  # V-reset
    assert protocol.P2_RELEASE.hex() == "f1f14e020000507e"  # V-touchRelease
    # Row 42 (V-time1, V-time2): Calendar weekday is Sunday=0.
    assert (
        protocol.clock_command(datetime(2026, 10, 1, 12, 34, 56)).hex()
        == "f1f15007380a01040c2238047e"
    )
    assert (
        protocol.clock_command(datetime(2025, 1, 5, 1, 2, 3)).hex()
        == "f1f15007370105000102039a7e"
    )
    # Row 43 (V-name-ascii, V-name-allowed-utf8): 01 FC 07, byte length, UTF-8.
    for transport in ("t1", "t3"):
        assert protocol.rename_command("sleep_smart", transport, "Bed").hex() == "01fc0703426564"
        assert protocol.rename_command("sleep_smart", transport, "Ä").hex() == "01fc0702c384"
    assert protocol.rename_schedule("sleep_smart", "t1", "Bed") == (
        (0, bytes.fromhex("01fc0703426564")),
    )


@pytest.mark.parametrize("name", ["", "Å", "Bed 1", "A" * 21, "bed\n", "Bett-1"])
def test_rename_uses_the_edit_alphabet_and_length(name):
    with pytest.raises(ValueError, match="1..20"):
        protocol.rename_command("sleep_smart", "t3", name)
    assert len(protocol.validate_rename("sleep_smart", "ÄÖÜäöüß" + "a" * 13)) == 27


def test_startup_merges_both_ready_handlers():
    p1 = [(t, data.hex()) for t, data in protocol.sleep_smart_startup_schedule("p1")]
    assert p1 == [
        (300, "f1f100024000427e"),
        (600, "f1f1000108097e"),
        (900, "f1f1000140417e"),
        (1000, "f1f1000150517e"),
        (1100, "f1f1000150517e"),
        (1200, "f1f1000150517e"),
        (1200, "f1f1000140417e"),
        (1300, "f1f1000140417e"),
        (1400, "f1f1000108097e"),
        (1500, "f1f1000150517e"),
        (1500, "f1f1000108097e"),
        (1800, "f1f100020100037e"),
        (2100, "f1f100020100037e"),
        (2400, "f1f10000007e"),
        (2700, "f1f10000007e"),
    ]
    p2 = [(t, data.hex()) for t, data in protocol.sleep_smart_startup_schedule("p2")]
    assert p2[6:8] == [(1200, "f1f100024000427e"), (1300, "f1f100024000427e")]
    assert tuple(
        (offset, protocol.QUERY_MASSAGE) for offset in (100, 250, 450)
    ) == protocol.MASSAGE_QUERY_SCHEDULE


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        # V-bed-state1: byte 4 back, byte 6 foot/right, byte 8 bit 6 light.
        ("f2f206050200040040", protocol.Notification(massage_back=2, massage_legs=4, light_on=True)),
        ("f2f205000000000040", protocol.Notification(light_on=True)),
        ("f2f205000000000000", protocol.Notification(light_on=False)),
        ("f2f205", None),
        # V-bed-mode-*: byte 4 hex text parsed as decimal.
        ("f2f20d0101", protocol.Notification(massage_mode="long_interval", massage_mode_reported=True)),
        ("f2f20d0102", protocol.Notification(massage_mode="short_interval", massage_mode_reported=True)),
        ("f2f20d0103", protocol.Notification(massage_mode="wave", massage_mode_reported=True)),
        ("f2f20d0104", protocol.Notification(massage_mode="continuous", massage_mode_reported=True)),
        ("f2f20d0110", protocol.Notification(massage_mode_reported=True)),
        ("f2f20d010a", None),
        ("f2f20d", None),
        ("f2f250", protocol.Notification(clock_requested=True)),
        # No family selector exists in this app.
        ("f2f2110001", None),
    ],
)
def test_parser_vectors(data, expected):
    assert protocol.parse_notification("sleep_smart", bytes.fromhex(data)) == expected


def _client(coordinator, transports=(T1, T2, T3), *, without=()):
    services, characteristics = {}, {}
    for transport in transports:
        uuids = {transport.write_uuid, transport.notify_uuid, transport.rename_uuid} - {None}
        chars = [MagicMock(uuid=uuid, properties=["write", "notify"]) for uuid in uuids - set(without)]
        services[transport.service_uuid] = MagicMock(
            uuid=transport.service_uuid, characteristics=chars
        )
        characteristics.update({char.uuid: char for char in chars})
    coordinator.client.services.get_service.side_effect = services.get
    coordinator.client.services.get_characteristic.side_effect = characteristics.get


@pytest.fixture
def coordinator():
    coordinator = MagicMock()
    coordinator.cancel_command = asyncio.Event()
    coordinator.motor_pulse_count = 2
    coordinator.client.is_connected = True
    coordinator.client.write_gatt_char = AsyncMock()
    coordinator.client.start_notify = AsyncMock()
    coordinator.client.stop_notify = AsyncMock()
    coordinator.async_execute_controller_command = AsyncMock()
    _client(coordinator)
    return coordinator


def bed(coordinator, **overrides):
    options = {
        "profile": "sleep_smart",
        "command_family": "p1",
        "layout": "standard_2",
        "transport": "t3",
        "has_light": True,
        "has_massage": True,
    }
    options.update(overrides)
    return LogicdataAppController(coordinator, **options)


def writes(coordinator):
    return [(call.args[0], call.args[1].hex()) for call in coordinator.client.write_gatt_char.call_args_list]


def packets(coordinator):
    return [packet for _, packet in writes(coordinator)]


@pytest.fixture
def instant():
    with patch.object(LogicdataAppController, "_pause", new=AsyncMock(return_value=True)) as pause:
        yield pause


@pytest.mark.parametrize(
    ("family", "axis", "expected"),
    [("p1", "back", "f1f1010101037e"), ("p2", "back", "f1f101020000037e"), ("p2", "both", "f1f1050101077e")],
)
async def test_movement_repeats_then_releases(coordinator, instant, family, axis, expected):
    controller = bed(coordinator, command_family=family)
    await controller.move_axis(axis, True)
    assert packets(coordinator) == [expected] * 3 + ["f1f14e004e7e"]


async def test_two_motor_layout_for_every_series(coordinator):
    for layout in protocol.SLEEP_SMART_LAYOUTS:
        controller = bed(coordinator, layout=layout, command_family="p2")
        assert [spec.key for spec in controller.motor_control_specs] == ["back", "legs", "both"]
        assert controller.supports_massage
    assert bed(coordinator, layout="split_series").massage_intensity_zones == ["head", "right"]
    assert bed(coordinator).massage_intensity_zones == ["head", "foot"]
    with pytest.raises(ValueError, match="two-motor"):
        bed(coordinator, layout="middle", command_family="p2")


@pytest.mark.parametrize(
    ("method", "frame"),
    [
        ("preset_zero_g", "f1f1070101097e"),
        ("preset_flat", "f1f10801010a7e"),
        ("preset_anti_snore", "f1f10901010b7e"),
    ],
)
async def test_presets_are_hold_only_at_200_ms_then_release(coordinator, method, frame):
    controller = bed(coordinator, command_family="p2")
    requested = []

    async def pause(seconds, cancel_event=None):
        requested.append((round(seconds, 1), cancel_event is not None))
        return True

    with patch.object(controller, "_pause", side_effect=pause):
        await getattr(controller, method)()
    # Pulse count 2 holds 400 ms: refreshes at 0 and 200 ms, no terminal frame,
    # then the release 100 ms after the hold ends with a fresh event. Pauses
    # are relative to the hold start, which instant pauses leave unchanged.
    assert packets(coordinator) == [frame, frame, "f1f14e004e7e"]
    assert requested == [(0.2, False), (0.4, False), (0.1, True)]


async def test_one_memory_slot_hold_recall_and_single_save(coordinator, instant):
    controller = bed(coordinator)
    assert controller.memory_slot_count == 1
    await controller.preset_memory(1)
    await controller.program_memory(1)
    assert packets(coordinator) == ["f1f10b01010d7e"] * 2 + ["f1f14e004e7e", "f1f10a000a7e"]
    coordinator.client.write_gatt_char.reset_mock()
    for call in (controller.preset_memory(2), controller.program_memory(2)):
        with pytest.raises(ValueError, match="one memory"):
            await call
    with pytest.raises(ValueError, match="must be one of"):
        await controller.hold_preset("memory_2", 1000)
    assert packets(coordinator) == []


async def test_cancelled_hold_still_releases(coordinator):
    controller = bed(coordinator)

    async def pause(seconds, cancel_event=None):
        if cancel_event is None:
            coordinator.cancel_command.set()
            return False
        assert not cancel_event.is_set()
        return True

    with patch.object(controller, "_pause", side_effect=pause):
        await controller.hold_preset("zero_g", 5000)
    assert packets(coordinator) == ["f1f1070101097e", "f1f14e004e7e"]


async def test_massage_mode_and_light_send_their_release_companions(coordinator, instant):
    controller = bed(coordinator)
    await controller.massage_mode_step()
    await controller.lights_toggle()
    await controller.set_massage_intensity("head", 3)
    await controller.massage_off()
    assert packets(coordinator) == [
        "f1f116010a217e", "f1f14e020000507e", "f1f14e004e7e",
        "f1f10f000f7e", "f1f14e004e7e", "f1f14e020000507e", "f1f14e004e7e",
        "f1f112020804207e",
        "f1f11101081a7e",
    ]


async def test_factory_reset_and_massage_query_are_profile_actions(coordinator, instant):
    controller = bed(coordinator)
    assert controller.supports_factory_reset
    assert [spec.key for spec in controller.controller_button_specs] == ["logicdata_app_query_massage"]
    await controller.factory_reset()
    await controller.query_massage()
    assert packets(coordinator) == ["f1f11d0200001f7e"] + ["f1f1000208000a7e"] * 3
    phone = bed(coordinator, profile="phone")
    assert not phone.supports_factory_reset
    assert phone.controller_button_specs == ()
    with pytest.raises(NotImplementedError):
        await phone.factory_reset()


async def test_t3_ready_event_runs_both_startup_handlers(coordinator, instant):
    controller = bed(coordinator)
    await controller.async_discover_capabilities()
    await controller.start_notify()
    assert [call.args[0] for call in coordinator.client.start_notify.call_args_list] == [
        T3.notify_uuid,
        T3.rename_uuid,
    ]
    assert writes(coordinator) == [
        (T3.write_uuid, packet.hex()) for _, packet in protocol.sleep_smart_startup_schedule("p1")
    ]
    assert controller._initialized


@pytest.mark.parametrize("transport", ["t1", "t2"])
async def test_t1_or_t2_alone_never_become_ready(coordinator, instant, transport):
    _client(coordinator, (protocol.TRANSPORTS[transport],))
    controller = bed(coordinator, transport="auto")
    await controller.async_discover_capabilities()
    await controller.start_notify()
    assert [call.args[0] for call in coordinator.client.start_notify.call_args_list] == [
        protocol.TRANSPORTS[transport].notify_uuid
    ]
    assert packets(coordinator) == []
    assert controller._initialized


async def test_copresent_t3_readiness_initializes_the_selected_write_role(coordinator, instant):
    controller = bed(coordinator, transport="t2")
    await controller.async_discover_capabilities()
    await controller.start_notify()
    assert [call.args[0] for call in coordinator.client.start_notify.call_args_list] == [
        T2.notify_uuid,
        T3.notify_uuid,
        T3.rename_uuid,
    ]
    assert {uuid for uuid, _ in writes(coordinator)} == {T2.write_uuid}
    assert len(packets(coordinator)) == 15


async def test_failed_name_subscription_skips_queries_but_keeps_the_link(coordinator, instant):
    async def start_notify(uuid, callback):
        if uuid == T3.rename_uuid:
            raise BleakError("CCCD rejected")

    coordinator.client.start_notify.side_effect = start_notify
    controller = bed(coordinator)
    await controller.async_discover_capabilities()
    await controller.start_notify()
    assert packets(coordinator) == []
    assert controller._subscribed == [T3.notify_uuid]
    assert controller._initialized


async def test_t1_without_name_role_still_controls(coordinator, instant):
    _client(coordinator, (T1,), without=(T1.rename_uuid,))
    controller = bed(coordinator, transport="t1")
    await controller.async_discover_capabilities()
    assert not controller.supports_device_rename
    await controller.move_axis("legs", False)
    assert packets(coordinator)[0] == "f1f1040101067e"


@pytest.mark.parametrize(
    ("transport", "services", "uuid"),
    [("t1", (T1, T3), T1.rename_uuid), ("t3", (T3,), T3.rename_uuid), ("t2", (T2, T3), T3.rename_uuid), ("t2", (T1, T2), T1.rename_uuid)],
)
async def test_rename_targets_the_name_role_once(coordinator, instant, transport, services, uuid):
    _client(coordinator, services)
    controller = bed(coordinator, transport=transport)
    await controller.async_discover_capabilities()
    with pytest.raises(ValueError):
        controller.validate_device_rename("Bad name")
    await controller.rename_device("Bed")
    assert writes(coordinator) == [(uuid, "01fc0703426564")]


async def test_t2_alone_has_no_name_role(coordinator):
    _client(coordinator, (T2,))
    controller = bed(coordinator, transport="t2")
    await controller.async_discover_capabilities()
    assert not controller.supports_device_rename
    with pytest.raises(NotImplementedError):
        await controller.rename_device("Bed")


async def test_notifications_publish_state_and_answer_clock_requests(coordinator):
    controller = bed(coordinator, layout="split_series")
    updates = []
    controller.forward_controller_state_updates = updates.append
    sender = MagicMock(uuid=T3.notify_uuid)
    controller._notification_handler(sender, bytearray.fromhex("f2f206050300040040"))
    controller._notification_handler(sender, bytearray.fromhex("f2f20d0103"))
    controller._notification_handler(sender, bytearray.fromhex("f2f20d0109"))
    assert updates == [
        {"under_bed_lights_on": True, "head_intensity": 2, "right_intensity": 3},
        {"logicdata_app_massage_mode": "wave"},
        {"logicdata_app_massage_mode": None},
    ]
    controller._notification_handler(sender, bytearray.fromhex("f2f250"))
    assert controller._clock_task is not None
    await controller._clock_task
    coordinator.async_execute_controller_command.assert_awaited_once()
    assert coordinator.async_execute_controller_command.await_args.kwargs == {
        "cancel_running": False,
        "skip_disconnect": True,
    }
    send = coordinator.async_execute_controller_command.await_args.args[0]
    with patch(
        "custom_components.adjustable_bed.beds.logicdata_app.dt_util.now",
        return_value=datetime(2026, 10, 1, 12, 34, 56),
    ):
        await send(controller)
    assert writes(coordinator) == [(T3.write_uuid, "f1f15007380a01040c2238047e")]


def test_capabilities_follow_the_profile(coordinator):
    controller = bed(coordinator, command_family="p2", has_light=False)
    assert controller.supports_preset_zero_g and controller.supports_preset_anti_snore
    assert controller.held_preset_options == ("flat", "zero_g", "anti_snore", "memory_1")
    assert not controller.supports_clock_alarm
    assert not controller.supports_lights
    assert [spec.key for spec in controller.controller_state_sensor_specs] == [
        "logicdata_app_massage_mode"
    ]
    assert controller.stale_controller_state_sensor_entity_keys == {
        "logicdata_app_alarm",
        "logicdata_app_family_match",
    }
    quiet = bed(coordinator, has_massage=False)
    assert quiet.controller_state_sensor_specs == ()
    assert "logicdata_app_massage_mode" in quiet.stale_controller_state_sensor_entity_keys
    phone = bed(coordinator, profile="phone", command_family="p2", layout="middle")
    assert phone.held_preset_options == ("flat", "memory_1", "memory_2")
    assert "logicdata_app_massage_mode" in phone.stale_controller_state_sensor_entity_keys
