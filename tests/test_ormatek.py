"""Ormatek production behavior, independent frames and virtual time."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.app_profiles import per_side_profile
from custom_components.adjustable_bed.beds.keeson import ormatek as ctrl
from custom_components.adjustable_bed.beds.keeson.ormatek_state import Alarm, Massage, Parser, value
from custom_components.adjustable_bed.profiles import ormatek as app
from custom_components.adjustable_bed.setup_questions import setup_profile_for
from tests.hold_lease_wire import virtual_clock
from tests.test_controller_contract import _FactoryCoordinator


class Services(list):
    def get_service(self, uuid):
        return next((s for s in self if s.uuid == uuid), None)


def gatt(nordic=False):
    def char(uuid, props):
        return SimpleNamespace(uuid=uuid, properties=props, handle=1)

    def service(uuid, chars):
        return SimpleNamespace(
            uuid=uuid,
            characteristics=chars,
            get_characteristic=lambda key: next((c for c in chars if c.uuid == key), None),
        )

    if nordic:
        w, r = (
            char(ctrl.NUS.write_uuid, ["write-without-response"]),
            char(ctrl.NUS.notify_uuid, ["notify"]),
        )
        return Services([service(ctrl.NUS.service_uuid, [w, r])])
    w, r = (
        char("0000ffe9-0000-1000-8000-00805f9b34fb", ["write-without-response"]),
        char("0000ffe4-0000-1000-8000-00805f9b34fb", ["indicate"]),
    )
    return Services(
        [
            service("0000ffe5-0000-1000-8000-00805f9b34fb", [w]),
            service("0000ffe0-0000-1000-8000-00805f9b34fb", [r]),
        ]
    )


async def connected(wire="okin15", layout="new", services=None, coordinator=None):
    c = coordinator or _FactoryCoordinator()
    c.client = SimpleNamespace(
        is_connected=True,
        services=services or gatt(),
        start_notify=AsyncMock(),
        stop_notify=AsyncMock(),
    )
    controller = ctrl.OrmatekController(c, wire, layout)
    await controller.async_discover_capabilities()
    await controller.start_notify()
    writes = []

    async def record(link, frame, event):
        controller._live(link)
        if not event.is_set():
            writes.append((round(asyncio.get_running_loop().time() * 1000), frame.hex()))

    controller._send = record
    return controller, c, writes


@pytest.mark.parametrize("wire", app.WIRES)
@pytest.mark.parametrize("layout", app.LAYOUTS)
@pytest.mark.parametrize("nordic", (True, False))
async def test_independent_catalog_gatt_layout_and_setup(wire, layout, nordic):
    c, _, _ = await connected(wire, layout, gatt(nordic))
    assert c.wire == wire and c.layout == layout
    assert c.control_characteristic_uuid == (
        ctrl.NUS.write_uuid if nordic else "0000ffe9-0000-1000-8000-00805f9b34fb"
    )
    assert c.supports_massage == (layout == "new")
    assert c.supports_preset_lounge == (layout == "new")
    assert c.memory_slot_count == (1 if layout == "new" else 0)
    assert not c.supports_memory_programming and not c.supports_single_address_pairing
    assert not c.supports_position_feedback and not c.supports_discrete_light_control
    assert not c.supports_massage_intensity_control and not c.supports_head_massage_toggle_control
    assert c.alarm_capability.wake_actions == (
        ("massage", "memory_1", "flat") if layout == "new" else ("zero_g", "tv")
    )
    data = {"bed_type": "ormatek", "product_type": layout, "protocol_variant": wire}
    setup = setup_profile_for(data)
    assert setup is not None and setup.derive is not None
    assert setup.derive(data)["has_massage"] == (layout == "new")
    side = per_side_profile("ormatek", wire)
    assert side is not None
    assert side.keys >= {
        "product_type",
        "protocol_variant",
        "motor_count",
        "has_massage",
        "ble_device_name",
    }


async def test_last_write_service_selects_whole_tuple_and_requires_properties():
    c, _, _ = await connected(services=Services([*gatt(), *gatt(True)]))
    assert c.control_characteristic_uuid == ctrl.NUS.write_uuid
    services = Services([*gatt(True), *gatt()])
    c, _, _ = await connected("okin24", services=services)
    assert c.control_characteristic_uuid == "0000ffe9-0000-1000-8000-00805f9b34fb"
    for services in (Services([*gatt(True), gatt()[0]]), gatt()):
        if len(services) == 2:
            services[0].characteristics[0].properties = ["write"]
        with pytest.raises(ConnectionError):
            await connected(services=services)


@pytest.mark.parametrize(
    ("name", "wire"),
    [
        ("OkIn001", "okin15"),
        ("SmartBed001", "okin24"),
        ("okinmat", "okin15"),
        ("Unknown", None),
        ("prefix-okin", None),
    ],
)
def test_name_rule_is_not_advertisement_ownership(name, wire):
    assert app.match_name(name) == wire


async def test_captured_notification_disconnect_and_replacement_owner():
    c, coordinator, _ = await connected()
    updates = []
    coordinator.handle_controller_state_updates = lambda *items: updates.extend(items)
    link = c._link
    packet = bytes.fromhex("edfe00000000000603000000000023ff")
    c._receive(link, packet)
    assert c._timer == 3
    assert {u.key: u.value for u in updates}[ctrl.HEAD] == 3
    other = ctrl.OrmatekController(coordinator)
    await other.async_discover_capabilities()
    await other.start_notify()
    before = len(updates)
    c._receive(link, packet)
    await c.stop_notify()
    assert len(updates) == before
    coordinator.client.stop_notify.assert_not_awaited()
    assert other._live() is not None
    other.on_disconnect()
    assert other._parser.pending == b""
    assert all(u.value is None for u in updates[-6:])


@pytest.mark.parametrize(
    ("way", "data", "expected"),
    [
        (1511, b"\0", 1),
        (1511, b"\x05", 3),
        (1512, b"\x44", 0),
        (1513, b"\x53", 0),
        (2411, b"\xff", 86),
        (2412, b"\xff\xff", 110),
        (2412, b"\x02", 1),
        (2413, b"\xff", 255),
        (1521, b"\x80", 0),
        (1521, b"\xff", 1),
        (1002, b"\x0c", 0),
    ],
)
def test_parser_rules(way, data, expected):
    assert value(data, 0, way) == expected
    assert value(data, len(data), way) == 0


def test_parser_fragments_current_chunk_prefix_dedup_and_short_boundaries():
    packet = bytes.fromhex("edfe00000000000603000000000023ff")
    parser = Parser("okin15")
    assert parser.feed(packet) == Massage(3, 3, 2, 2)
    assert parser.feed(packet) is None
    assert Parser("okin15").feed(b"\xed\x80\x03") == Alarm(False, 0, 0)
    assert value(b"", -1, 1001) == 0
    with pytest.raises(IndexError):
        value(b"\0" * 6, 4, 2422)
    parser = Parser("okin15")
    assert parser.feed(packet + bytes(4)) is None
    assert parser.feed(b"\x01\x02") is None
    assert parser.feed(b"\xed\xfe\x01") == Massage(3, 3, 2, 2)
    assert parser.feed(b"\xed\xfe\x01") is None
    assert Parser("okin24").feed(bytes.fromhex("a50c0000ff05061e0001")) == Alarm(True, 6, 30)


async def test_held_and_release_timing():
    with virtual_clock():
        c, _, writes = await connected()
        await c.hold_control("head_up", 450)
        assert [(at - writes[0][0], data) for at, data in writes] == [
            (0, "e6fe16010000000004"),
            (200, "e6fe16010000000004"),
            (400, "e6fe16010000000004"),
            (550, "e6fe16000000000005"),
            (750, "e6fe16000000000005"),
        ]


async def test_preset_begins_on_invocation_and_cancelled_cleanup_drains():
    with virtual_clock():
        c, coordinator, writes = await connected()
        await c.preset_flat()
        assert [(at - writes[0][0], data) for at, data in writes] == [
            (0, "e6fe160000000800fd"),
            (100, "e6fe16000000000005"),
            (300, "e6fe16000000000005"),
        ]
        writes.clear()
        task = asyncio.create_task(c.hold_control("head_up", 1000))
        await asyncio.sleep(0.05)
        coordinator.cancel_command.set()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert [data for _, data in writes][-2:] == ["e6fe16000000000005"] * 2
        assert writes[-1][0] - writes[-2][0] == 200


async def test_current_timer_dispatch_and_query_300ms_preserves_stop_repeat():
    with virtual_clock():
        c, _, writes = await connected("okin24")
        c._receive(c._link, bytes.fromhex("a50b00000000000000"))
        await c.massage_action("massageTimeSwitch")
        assert [(at - writes[0][0], data) for at, data in writes] == [
            (0, "05020000010000"),
            (200, "05020000010000"),
            (200, "05020000000000"),
            (300, "00b0"),
            (400, "05020000000000"),
        ]
        writes.clear()
        c._timer = 1
        await c.massage_action("massageWaveSwitch")
        assert writes[0][1] == "05021000000000"
        assert writes[2][0] - writes[0][0] == 200


@pytest.mark.parametrize("wire", app.WIRES)
async def test_shared_alarm_capability_bytes_and_queries(wire):
    with virtual_clock():
        c, _, writes = await connected(wire)
        await c.configure_alarm(
            AlarmRequest(
                enabled=True,
                hour=6,
                minute=30,
                wake_action="memory_1",
                reference_time=datetime(2026, 11, 18),
            )
        )
        expected = (
            ["ed8003061eff1100000000000000005b", "e28003009a", "e28003009a", "e28003009a"]
            if wire == "okin15"
            else ["0705ff05061e000100", "00c0", "00d0"]
        )
        assert [data for _, data in writes] == expected
        assert [at - writes[0][0] for at, _ in writes] == (
            [0, 0, 100, 200] if wire == "okin15" else [0, 100, 100]
        )
        writes.clear()
        with pytest.raises(ValueError):
            c.validate_alarm(
                AlarmRequest(
                    enabled=True, wake_action="memory_2", reference_time=datetime(2026, 11, 18)
                )
            )
        assert writes == []


async def test_set_alarm_service_admits_layout_and_writes_its_frame(hass):
    from homeassistant.exceptions import ServiceValidationError

    from tests.alarm_helpers import call_set_alarm

    with virtual_clock():
        c, _, writes = await connected("okin24", "lite")
        await call_set_alarm(
            hass, c, {"enabled": True, "time": "06:30:00", "wake_action": "tv"}, bed_type="ormatek"
        )
        assert writes[0][1] == "0705ff03061e000100"
        writes.clear()
        for data in ({}, {"wake_action": "memory_1"}, {"weekdays": ["monday"]}, {"slot": 2}):
            with pytest.raises(ServiceValidationError):
                await call_set_alarm(
                    hass, c, {"enabled": True, "time": "06:30:00", **data}, bed_type="ormatek"
                )
            assert writes == []


@pytest.mark.parametrize(
    ("mask", "now", "expected"),
    [
        (255, datetime(2026, 11, 22, 7), 255),
        (0, datetime(2026, 11, 22, 5), 1),
        (128, datetime(2026, 11, 22, 7), 2),
    ],
)
def test_builder_weekday_matches_local_next_day(mask, now, expected):
    assert app.weekday(mask, 6, 30, now) == expected


async def test_cleanup_attempts_both_stops_after_write_failure():
    with virtual_clock():
        c, _, writes = await connected()
        send = c._send
        failed = False

        async def failing(link, frame, event):
            nonlocal failed
            await send(link, frame, event)
            if not failed:
                failed = True
                raise ConnectionError("write initiation failed")

        c._send = failing
        with pytest.raises(ConnectionError):
            await c.stop_all()
        assert [data for _, data in writes] == ["e6fe16000000000005"] * 2
        assert writes[1][0] - writes[0][0] == 200


async def test_delayed_cleanup_cannot_write_to_replacement_session():
    with virtual_clock():
        c, coordinator, writes = await connected()
        task = asyncio.create_task(c.hold_control("head_up", 100))
        await asyncio.sleep(0.15)
        replacement = ctrl.OrmatekController(coordinator)
        await replacement.async_discover_capabilities()
        await replacement.start_notify()
        await task
        assert [data for _, data in writes] == ["e6fe16010000000004"]
        assert replacement._live() is not None


async def test_clock_and_alarm_initialization_stays_on_captured_session():
    with virtual_clock():
        c, _, writes = await connected("okin24")
        session = SimpleNamespace(is_current=lambda: True)
        await c.async_after_connect(session)
        assert bytes.fromhex(writes[0][1])[:2] == bytes.fromhex("0704")
        assert [data for _, data in writes[1:]] == ["00c0", "00d0"]


async def test_auto_factory_refuses_unknown_name_and_setup_remains_explicit():
    from custom_components.adjustable_bed.beds.builder import BuildContext

    coordinator = _FactoryCoordinator()
    coordinator.entry.data["product_type"] = "new"
    ctx = BuildContext(coordinator=coordinator, bed_type="ormatek", variant="auto", client=None)
    with pytest.raises(ValueError, match="explicitly"):
        await ctrl.build_controller(ctx)
    coordinator.entry.data["ble_device_name"] = "SmArTbEd001"
    controller = await ctrl.build_controller(ctx)
    assert controller.wire == "okin24"


async def test_alarm_validation_is_offline_but_live_preflight_refuses_ended_session():
    controller = ctrl.OrmatekController(_FactoryCoordinator())
    request = AlarmRequest(enabled=True, wake_action="flat", reference_time=datetime(2026, 11, 18))
    controller.validate_alarm(request)
    assert controller.alarm_capability.live_check
    with pytest.raises(ConnectionError):
        await controller.check_alarm(request)


async def test_out_of_range_feedback_stays_diagnostic_and_disabled_alarm_keeps_time():
    c, coordinator, _ = await connected("okin24")
    updates = []
    coordinator.handle_controller_state_updates = lambda *items: updates.extend(items)
    c._receive(c._link, bytes.fromhex("a50b0000ffffffffffff"))
    assert {u.key: u.value for u in updates}[ctrl.HEAD] is None
    assert c._raw_state.head == 86
    assert "86" in c.protocol_diagnostics["notification"]
    c._receive(c._link, bytes.fromhex("a50c0000ff05061e0001"))
    c._receive(c._link, bytes.fromhex("a50d0000000000000000"))
    assert {u.key: u.value for u in updates}[ctrl.TIME] == "06:30"
    assert {u.key: u.value for u in updates}[ctrl.ALARM] is True
    assert c._raw_state.slot == 2
    c._receive(c._link, bytes.fromhex("a50c0000000000000000"))
    assert {u.key: u.value for u in updates}[ctrl.TIME] == "06:30"
    assert {u.key: u.value for u in updates}[ctrl.ALARM] is False


async def test_preset_release_deadline_does_not_drift_with_write_latency():
    with virtual_clock():
        c, _, writes = await connected()
        send = c._send

        async def slow(link, frame, event):
            await send(link, frame, event)
            await asyncio.sleep(0.03)

        c._send = slow
        await c.preset_flat()
        assert [at - writes[0][0] for at, _ in writes] == [0, 100, 300]


async def test_alarm_query_deadlines_do_not_drift_with_write_latency():
    with virtual_clock():
        c, _, writes = await connected()
        send = c._send

        async def slow(link, frame, event):
            await send(link, frame, event)
            await asyncio.sleep(0.03)

        c._send = slow
        await c.configure_alarm(
            AlarmRequest(
                enabled=True,
                hour=6,
                minute=30,
                wake_action="flat",
                reference_time=datetime(2026, 11, 18),
            )
        )
        assert [at - writes[0][0] for at, _ in writes] == [0, 30, 100, 200]


async def test_slow_hold_skips_missed_refreshes_and_never_starts_after_deadline():
    with virtual_clock():
        c, _, writes = await connected()
        send = c._send

        async def slow(link, frame, event):
            await send(link, frame, event)
            await asyncio.sleep(0.3)

        c._send = slow
        await c.hold_control("head_up", 450)
        assert [(at - writes[0][0], data) for at, data in writes] == [
            (0, "e6fe16010000000004"),
            (400, "e6fe16010000000004"),
            (700, "e6fe16000000000005"),
            (1000, "e6fe16000000000005"),
        ]


@pytest.mark.parametrize("action", ("massageTimeSwitch", "massageWaveSwitch"))
async def test_unknown_massage_state_queries_before_choosing_cycle(action):
    with virtual_clock():
        c, _, writes = await connected("okin24")
        send = c._send

        async def responding(link, frame, event):
            await send(link, frame, event)
            if frame == b"\0\xb0":
                c._receive(link, bytes.fromhex("a50b00000258010106"))

        c._send = responding
        await c.massage_action(action)
        assert [data for _, data in writes][:2] == [
            "00b0",
            "05020000020000" if action == "massageTimeSwitch" else "05021000000000",
        ]


async def test_missing_massage_reply_is_bounded_and_sends_no_toggle():
    with virtual_clock() as clock:
        c, _, writes = await connected("okin24")
        started = clock.now
        with pytest.raises(ValueError, match="Massage state"):
            await c.massage_action("massageTimeSwitch")
        assert clock.now - started == 2
        assert [data for _, data in writes] == ["00b0"]


@pytest.mark.parametrize("end", ("cancel", "disconnect", "replace"))
async def test_pending_massage_query_cannot_choose_action_after_session_ends(end):
    with virtual_clock():
        c, coordinator, writes = await connected("okin24")
        task = asyncio.create_task(c.massage_action("massageWaveSwitch"))
        await asyncio.sleep(0.1)
        if end == "cancel":
            coordinator.cancel_command.set()
            error = asyncio.CancelledError
        elif end == "disconnect":
            c.on_disconnect()
            error = ConnectionError
        else:
            other = ctrl.OrmatekController(coordinator, "okin24")
            await other.async_discover_capabilities()
            await other.start_notify()
            error = ConnectionError
        with pytest.raises(error):
            await task
        assert [data for _, data in writes] == ["00b0"]


async def test_multi_target_alarm_admits_every_layout_before_first_write(hass):
    from unittest.mock import MagicMock, patch

    from homeassistant.exceptions import ServiceValidationError

    from custom_components.adjustable_bed import services
    from custom_components.adjustable_bed.const import DOMAIN

    first, _, first_writes = await connected(layout="new")
    second, _, second_writes = await connected(layout="lite")
    owners = [MagicMock(), MagicMock()]
    targets = [
        SimpleNamespace(
            controller_side=None,
            capability_controller=c,
            controller=c,
            name=name,
            operation_identity=index,
            bed_type="ormatek",
        )
        for index, (name, c) in enumerate((("New", first), ("Lite", second)), 1)
    ]
    await services.async_register_services(hass)
    execute = AsyncMock()
    with (
        patch.object(
            services,
            "_resolve_sided_targets",
            return_value=([(owner, "both") for owner in owners], []),
        ),
        patch.object(
            services,
            "_command_targets",
            side_effect=lambda owner, side: [targets[owners.index(owner)]],
        ),
        patch.object(services, "_execute_sided", execute),
        pytest.raises(ServiceValidationError),
    ):
        await hass.services.async_call(
            DOMAIN,
            "set_alarm",
            {
                "device_id": ["new", "lite"],
                "enabled": True,
                "time": "06:30:00",
                "wake_action": "memory_1",
            },
            blocking=True,
        )
    execute.assert_not_awaited()
    assert first_writes == second_writes == []


async def test_cancelled_massage_query_does_not_suppress_required_stop_repeat():
    with virtual_clock():
        c, coordinator, writes = await connected("okin24")
        task = asyncio.create_task(c.hold_control("head_massage", 1000))
        await asyncio.sleep(0.15)
        coordinator.cancel_command.set()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert [(at - writes[0][0], data) for at, data in writes] == [
            (0, "05020000080000"),
            (150, "05020000000000"),
            (300, "00b0"),
            (350, "05020000000000"),
        ]
