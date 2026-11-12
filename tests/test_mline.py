"""Accepted row147 literals through production encoders and real HA callers."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.mline import controller as runtime
from custom_components.adjustable_bed.beds.mline import history, state
from custom_components.adjustable_bed.codec import mline as codec
from custom_components.adjustable_bed.const import (
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_PRODUCT_TYPE,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.controller_state import ControllerState
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles import mline as app
from custom_components.adjustable_bed.setup_questions import setup_profile_for
from tests.hold_lease_wire import virtual_clock

FIXTURES = Path(__file__).parent / "fixtures/mline"
CONTROLS = json.loads((FIXTURES / "controls.json").read_text())
PARAMETERS = json.loads((FIXTURES / "parameters.json").read_text())
ADDRESS = "AA:BB:CC:DD:01:47"


@pytest.mark.parametrize("row", CONTROLS, ids=lambda row: row["id"])
def test_all_frozen_controls(row):
    protocol = "okin" if row["protocol"] == "P2" else "sleep"
    assert codec.control(row["action"], protocol) == bytes.fromhex(row["expected_bytes"])


@pytest.mark.parametrize("row", PARAMETERS, ids=lambda row: row["id"])
def test_all_frozen_parameters(row):
    args = row["inputs"]
    if row["action"] == "setAlarm":
        actual = codec.alarm(
            args["variant"], args["hour"], args["minute"], args["wake_type"], args["mode"]
        )
    elif row["action"] == "calibrationTime":
        year, month, day, weekday, hour, minute, second = args["components"]
        now = datetime(year, month, day, hour, minute, second)
        assert now.isoweekday() == weekday
        actual = codec.clock(args["variant"], now)
    elif row["action"] == "setAntiSnoring":
        actual = codec.anti_snore(args["enabled"], args["parameter5"], args["parameter3"])
    elif row["action"] == "setDemoAntiSnoring":
        actual = codec.anti_snore(True, 1, args["position"], demo=True)
    else:
        actual = codec.AUXILIARY[row["action"]]
    assert actual == bytes.fromhex(row["expected_bytes"])


class Char:
    def __init__(self, *, uuid, properties, handle, descriptors):
        self.uuid, self.properties, self.handle, self.descriptors = (
            uuid,
            properties,
            handle,
            descriptors,
        )


def gatt():
    def char(uuid, properties):
        return Char(uuid=uuid, properties=properties, handle=hash(uuid), descriptors=[])

    def service(uuid, chars):
        return SimpleNamespace(
            uuid=uuid,
            characteristics=chars,
            get_characteristic=lambda key: next((c for c in chars if c.uuid == key), None),
        )

    return [
        service(
            codec.NORDIC_SERVICE,
            [
                char(codec.NORDIC_WRITE, ["write-without-response"]),
                char(codec.NORDIC_NOTIFY, ["notify"]),
            ],
        ),
        service(codec.FFE_SERVICE, [char(codec.FFE_WRITE, ["write-without-response"])]),
        service(codec.FFE_NOTIFY_SERVICE, [char(codec.FFE_NOTIFY, ["notify"])]),
        service(
            codec.INFO_SERVICE,
            [char(codec.FIRMWARE, ["read"]), char(codec.PROTOCOL_STRING, ["read"])],
        ),
    ]


def frames(client):
    return [bytes(c.args[1]) for c in client.write_gatt_char.call_args_list]


@pytest.fixture
def bed():
    client = MagicMock(is_connected=True, services=gatt())
    client.write_gatt_char = AsyncMock()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    co = MagicMock(client=client, cancel_command=asyncio.Event(), motor_pulse_count=1)
    co.entry.data = {CONF_PRODUCT_TYPE: "four", CONF_HAS_MASSAGE: True}
    co.controller_state = ControllerState()
    co.handle_controller_state_updates.side_effect = lambda *updates: co.controller_state.update(
        (u.key, u.value) for u in updates
    )
    return runtime.MLineController(co), co, client


async def connected(bed):
    c, co, client = bed
    await c.async_discover_capabilities()
    await c.start_notify()
    return c, co, client


@pytest.mark.parametrize(
    ("name", "manufacturer", "result"),
    [
        ("", {}, "sleep"),
        ("other", {}, "unknown"),
        ("sleepSmartbed", {}, "smart"),
        ("SMARTBED", {89: b"\x05\x00\x00\x00\x00"}, "smart"),
        ("SMARTBED", {89: b"\x00\x00\x00\x00\x05"}, "smartsainuo"),
        ("sleepSMARTOKIN", {89: b"\x00\x00\x00\x00\x05"}, "okin"),
    ],
)
def test_selection(name, manufacturer, result):
    assert app.resolve_protocol(name, manufacturer) == result
    assert app.resolve_protocol(name, manufacturer, "smart") == "smart"


def test_scan_first_dedup_exactname_and_layout_tags():
    seen = set()
    assert app.scan_first((("a", "other"), ("b", "OKIN")), seen) is None
    assert app.scan_first((("a", "OKIN"),), seen, "okin") is None
    assert app.scan_first((("a", "OKIN"),), seen) is None
    assert app.scan_first((("b", "OKIN"),), seen, "OKIN") == ("b", "OKIN")
    assert not app.admitted_name("") and not app.admitted_name("SMART")
    assert [app.imported_layout(n) for n in (22, 33, 44, 99)] == ["two", "triple", "four", "four"]
    assert app.persisted_type("smartsainuo", "triple") == 53


@pytest.mark.parametrize("protocol", codec.PROTOCOLS)
@pytest.mark.parametrize("layout", app.LAYOUTS)
async def test_setup_saved_factory_axes_and_capabilities(hass, protocol, layout):
    data = {
        CONF_BED_TYPE: "mline",
        CONF_PROTOCOL_VARIANT: protocol,
        CONF_PRODUCT_TYPE: layout,
        CONF_HAS_MASSAGE: True,
    }
    profile = setup_profile_for(data)
    assert profile is not None and profile.imports == ("profiles.mline",)
    data.update(profile.settled(data))
    co = MagicMock(hass=hass)
    co.entry.data = data
    c = await create_controller(co, "mline", protocol, None)
    assert isinstance(c, runtime.MLineController)
    assert c.profile.key == protocol
    assert tuple(s.key for s in c.motor_control_specs) == app.LAYOUTS[layout]
    assert c.execution.hold == "stream" and not c.execution.concurrent
    assert not c.supports_single_address_pairing
    assert not c.supports_memory_programming and not c.supports_position_feedback
    assert all(
        s.scheduler_resource == "*" and s.hold.stop_scope == "side" for s in c.motor_control_specs
    )
    assert c.standard_button_hold_spec("preset_memory_1").control == "memory_1"


async def test_roles_notifications_reads_startup_and_retry(bed):
    c, co, client = bed
    await c.async_discover_capabilities()
    assert c._link.write.uuid == codec.FFE_WRITE
    assert c._link.notify.uuid == codec.FFE_NOTIFY
    client.start_notify.side_effect = [ValueError("already notifying"), None]
    with virtual_clock():
        await c.start_notify()
    assert client.start_notify.await_count == 2
    client.read_gatt_char = AsyncMock(side_effect=[b"1.1.0", b"SENSOR_VOICE"])
    await c.async_read_device_info(MagicMock())
    assert c._firmware == "1.1.0" and c._protocol_string == "SENSOR_VOICE"
    with virtual_clock():
        await c.async_after_connect(MagicMock())
    assert frames(client)[-2:] == [codec.AUXILIARY["checkState"]] * 2
    assert all(call.kwargs["response"] is False for call in client.write_gatt_char.call_args_list)


async def test_live_f1_safety_privacy_alarm_and_stale_callbacks(bed):
    c, co, client = await connected(bed)
    link = c._live()

    def notify(data):
        c._receive(link, link.notify, bytes(data))

    notify(b"\xa6\x10\x03")
    assert c._last_live is None
    notify(b"\xa6\x10\x03\x47\x11\x06")
    assert co.controller_state[state.HEART] == 71
    assert co.controller_state[state.BREATH] == 17
    assert co.controller_state[state.MOTION] is True
    assert co.controller_state[state.PROJECTION] is False
    notify(b"\xa6\x10\x03\x50\x12\x04")
    assert co.controller_state[state.HEART] == 71
    c._firmware, c._protocol_string = "1.1", "SENSOR_VOICE"
    data = bytearray(20)
    data[:2], data[15], data[16], data[19] = b"\xa5\x0b", 1, 3, 2
    notify(data)
    assert co.controller_state[state.PRIVACY] is True
    assert co.controller_state[state.ANTI_ANGLE] == 3
    notify(bytes.fromhex("a50c0e00820507110001"))
    assert co.controller_state[state.ALARM] == "07:17;130;5;1"
    notify(bytes.fromhex("ed800307118205000000000000000000"))
    assert co.controller_state[state.ALARM] == "07:17;130;5;1"
    c.on_disconnect()
    notify(b"\xa6\x10\x03\x47\x11\x06")
    assert co.controller_state[state.HEART] is None
    assert c._assembler.pending is None


def test_parser_fragment_uses_original_not_assembled_and_safe_version():
    p = codec.Assembler()
    first = bytes((0, 254, 22)) + bytes(17)
    assert p.feed(first) is None
    assert p.feed(first) is None and p.pending == first
    assert p.feed(b"abc") == first + b"abc"
    assert p.pending is None
    assert codec.new_sensor_protocol(None, "1.1") is None
    assert codec.new_sensor_protocol("SENSOR_VOICE", "bad") is None
    assert codec.new_sensor_protocol("SENSOR_VOICE", "1.0") is False
    assert codec.new_sensor_protocol("SENSOR_VOICE", "2.0") is True


async def test_hold_deadline_latency_drain_cancel_and_immutable_release(bed):
    c, co, client = await connected(bed)
    writes = []

    async def slow_write(char, data, **kwargs):
        writes.append((asyncio.get_running_loop().time(), data))
        await asyncio.sleep(0.35)

    client.write_gatt_char.side_effect = slow_write
    with virtual_clock():
        await c.hold_control("back_up", 300)
    assert [data for _, data in writes] == [
        codec.control("headUp", "sleep"),
        codec.control("stopCommand", "sleep"),
    ]
    writes.clear()
    with virtual_clock():
        task = asyncio.create_task(c.hold_control("back_up", 2000))
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert [data for _, data in writes] == [
        codec.control("headUp", "sleep"),
        codec.control("stopCommand", "sleep"),
    ]
    assert writes[1][0] - writes[0][0] == pytest.approx(0.45)


async def test_oneshots_settings_gates_and_no_save(bed):
    c, co, client = await connected(bed)
    with virtual_clock():
        await c.one_shot("light")
    assert frames(client) == [codec.control("light", "sleep")]
    client.write_gatt_char.reset_mock()
    with virtual_clock():
        await c.one_shot("waveAdd")
    assert frames(client) == [
        codec.control("waveAdd", "sleep"),
        codec.AUXILIARY["checkState"],
        codec.AUXILIARY["checkState"],
    ]
    co.entry.data[app.CHILD_MODE] = True
    with pytest.raises(ValueError):
        await c.hold_control("back_up", 100)
    with pytest.raises(NotImplementedError):
        await c.program_memory(1)
    co.entry.data[app.CHILD_MODE] = False
    c.profile = app.PROFILES["okin"]
    with virtual_clock():
        client.write_gatt_char.reset_mock()
        await c.settings_refresh()
        await c.sync_clock()
    assert frames(client)[0] == codec.AUXILIARY["checkState"] and len(frames(client)) == 3
    with pytest.raises(ValueError):
        await c.configure_privacy(True)


def record(now, heart=70):
    return bytes(
        (
            0xA6,
            0x30,
            0,
            heart,
            16,
            4,
            1,
            now.year - 1900,
            now.month - 1,
            now.day,
            now.hour,
            now.minute,
        )
    )


def test_raw_reader_tail_filter_stable_dedup_grouping():
    now = datetime(2026, 11, 12, 12)
    a, b = record(now), record(now, 80)
    items = history.records(a + b + b"tail", now)
    assert len(items) == 2
    groups = history.grouped(items)
    assert len(groups) == 1 and groups[0][0].raw == a
    assert history.grouped([]) == [[]]
    assert not history.records(record(now - timedelta(days=366)), now)
    assert (
        len(history.grouped(items + history.records(record(now + timedelta(minutes=6)), now))) == 2
    )


async def test_history_bounded_session_and_explicit_ack(bed, monkeypatch):
    c, co, client = await connected(bed)
    now = datetime(2026, 11, 12, 12)
    monkeypatch.setattr(runtime.dt_util, "now", lambda: now)
    link = c._live()

    async def write(char, data, **kwargs):
        if data == codec.AUXILIARY["gainNewHistoricalData"]:
            c._receive(link, link.notify, record(now))

    client.write_gatt_char.side_effect = write
    with virtual_clock():
        result = await c.read_history()
        assert result["acknowledged"] is False
        assert not any(data == codec.AUXILIARY["confirmGainHistoryData"] for data in frames(client))
        await c.acknowledge_history(result["transfer"])
    assert frames(client)[-2:] == [codec.AUXILIARY["confirmGainHistoryData"]] * 2
    with pytest.raises(ValueError):
        await c.acknowledge_history(result["transfer"])
    with virtual_clock():
        result = await c.read_history()
    c.on_disconnect()
    with pytest.raises((ValueError, ConnectionError)):
        await c.acknowledge_history(result["transfer"])


def entry(hass, layout="two", protocol="sleep"):
    data = {
        CONF_ADDRESS: ADDRESS,
        CONF_NAME: "M Line",
        CONF_BED_TYPE: "mline",
        CONF_PROTOCOL_VARIANT: protocol,
        CONF_PRODUCT_TYPE: layout,
        CONF_HAS_MASSAGE: True,
        CONF_DISABLE_ANGLE_SENSING: True,
    }
    data.update(setup_profile_for(data).settled(data))
    e = MockConfigEntry(domain=DOMAIN, title="M Line", unique_id=ADDRESS, data=data)
    e.add_to_hass(hass)
    return e


async def test_actual_entities_card_service_and_hold_lease(
    hass, mock_coordinator_connected, mock_bleak_client, enable_custom_integrations, monkeypatch
):
    mock_bleak_client.services = gatt()
    mock_bleak_client.read_gatt_char.side_effect = lambda char: (
        b"1.1" if char.uuid == codec.FIRMWARE else b"SENSOR_VOICE"
    )
    e = entry(hass)
    with monkeypatch.context() as startup:
        startup.setattr(runtime, "STARTUP_DELAY_S", 0)
        startup.setattr(runtime.MLineController, "_pause", AsyncMock(return_value=False))
        assert await hass.config_entries.async_setup(e.entry_id)
        await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][e.entry_id]
    controller = coordinator.controller
    assert controller._firmware == "1.1" and controller._protocol_string == "SENSOR_VOICE"
    status = bytearray(20)
    status[:2], status[19] = b"\xa5\x0b", 2
    link = controller._live()
    controller._receive(link, link.notify, bytes(status))
    assert coordinator.controller_state[state.PRIVACY] is True
    registry = er.async_get(hass)
    cover = registry.async_get_entity_id("cover", DOMAIN, f"{ADDRESS}_back")
    assert cover
    attributes = hass.states.get(cover).attributes
    assert attributes["hold_lease_mode"] == "stream"
    assert attributes["hold_lease_motor"] == "back"
    assert attributes["card_section"] == "motors"
    assert not registry.async_get_entity_id("button", DOMAIN, f"{ADDRESS}_program_memory_1")
    assert registry.async_get_entity_id("button", DOMAIN, f"{ADDRESS}_mline_light")
    dev = registry.async_get(cover).device_id
    mock_bleak_client.write_gatt_char.reset_mock()
    with virtual_clock():
        await hass.services.async_call(
            DOMAIN,
            "mline_command",
            {"device_id": dev, "action": "privacy", "enabled": True},
            blocking=True,
        )
    assert frames(mock_bleak_client) == [
        codec.AUXILIARY["openPrivacyMode"],
        codec.AUXILIARY["checkState"],
        codec.AUXILIARY["checkState"],
    ]
    mock_bleak_client.write_gatt_char.reset_mock()

    async def renew():
        await hass.services.async_call(
            DOMAIN,
            "timed_move",
            {
                "device_id": dev,
                "motor": "back",
                "direction": "up",
                "duration_ms": 200,
                "hold_owner": "card",
                "hold_generation": 1,
            },
            blocking=True,
        )

    with virtual_clock():
        task = asyncio.create_task(renew())
        for _ in range(4):
            await asyncio.sleep(0.1)
            await renew()
            assert not task.done()
            assert codec.control("stopCommand", "sleep") not in frames(mock_bleak_client)
        await task
    assert frames(mock_bleak_client)[-1] == codec.control("stopCommand", "sleep")
    with virtual_clock():
        assert await hass.config_entries.async_unload(e.entry_id)


async def test_real_profile_question_flow_saves_owned_values_and_configure(hass):
    from unittest.mock import patch

    from custom_components.adjustable_bed.config_flow import (
        AdjustableBedConfigFlow,
        _configure_questions,
    )

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {}
    flow._manual_data = {CONF_ADDRESS: ADDRESS, CONF_BED_TYPE: "mline"}
    with patch.object(flow, "_async_finish_family_route", new=AsyncMock()):
        await flow.async_step_profile_questions(
            {
                CONF_PRODUCT_TYPE: "triple",
                CONF_PROTOCOL_VARIANT: "okin",
                CONF_HAS_MASSAGE: True,
                app.CHILD_MODE: True,
            }
        )
    saved = flow._manual_data
    assert saved[CONF_PRODUCT_TYPE] == "triple" and saved[CONF_PROTOCOL_VARIANT] == "okin"
    assert saved["motor_count"] == 3 and saved["motor_pulse_delay_ms"] == 200
    assert saved[CONF_DISABLE_ANGLE_SENSING] is True and saved[app.CHILD_MODE] is True
    assert {q.key for q in _configure_questions(saved).questions} == {
        CONF_PRODUCT_TYPE,
        CONF_PROTOCOL_VARIANT,
        CONF_HAS_MASSAGE,
        app.CHILD_MODE,
    }


@pytest.mark.parametrize(
    "firmware,expected",
    [("1", False), ("1.0", False), ("1.1", True), ("2.0", True), ("0.9", False), ("bad", None)],
)
def test_source_version_cases_with_safe_malformed_fence(firmware, expected):
    assert codec.new_sensor_protocol("SENSOR_VOICE", firmware) is expected


@pytest.mark.parametrize(
    "protocol,encoded,expected",
    [
        ("smartsainuo", 1, "zg"),
        ("smartsainuo", 2, "m1"),
        ("smartsainuo", 3, "m2"),
        ("okin", 13, "zg"),
        ("okin", 28, "flat"),
        ("okin", 16, "antisnore"),
        ("sleep", 8, "vibration"),
        ("sleep", 255, "zg"),
    ],
)
def test_asymmetric_alarm_response_modes(protocol, encoded, expected):
    assert codec.alarm_mode(protocol, encoded) == expected


@pytest.mark.parametrize(
    "state_code,projected", [(2, True), (3, False), (4, True), (5, False), (6, False), (7, True)]
)
def test_live_boolean_source_projection(state_code, projected):
    assert codec.live(bytes((166, 16, 3, 71, 17, state_code))).projection is projected


async def test_deadline_while_wire_lane_is_blocked_and_recreated_session(bed):
    c, co, client = await connected(bed)
    await c._ble_lock.acquire()
    with virtual_clock():
        task = asyncio.create_task(c.hold_control("back_up", 100))
        await asyncio.sleep(0.2)
        c._ble_lock.release()
        await task
    assert frames(client) == [codec.control("stopCommand", "sleep")]
    client.write_gatt_char.reset_mock()
    old_link = c._live()
    with virtual_clock():
        task = asyncio.create_task(c.hold_control("back_up", 1000))
        await asyncio.sleep(0.05)
        c.on_disconnect()
        await c.async_discover_capabilities()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert frames(client) == [codec.control("headUp", "sleep")]
    assert c._live() is not old_link


async def test_raw_history_overflow_cancel_and_timeout_never_ack(bed, monkeypatch):
    c, co, client = await connected(bed)
    now = datetime(2026, 11, 12, 12)
    monkeypatch.setattr(runtime.dt_util, "now", lambda: now)
    monkeypatch.setattr(runtime, "HISTORY_LIMIT", 1)
    link = c._live()

    async def send(char, data, **kwargs):
        if data == codec.AUXILIARY["gainNewHistoricalData"]:
            c._receive(link, link.notify, record(now) + record(now))

    client.write_gatt_char.side_effect = send
    with virtual_clock(), pytest.raises(ValueError, match="bounded record limit"):
        await c.read_history()
    assert c._history is None and c._history_token is None
    client.write_gatt_char.side_effect = None
    with virtual_clock():
        task = asyncio.create_task(c.read_history())
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert c._history is None and c._history_token is None
    assert codec.AUXILIARY["confirmGainHistoryData"] not in frames(client)


async def make_receiver(hass, address, *, protocol="sleep"):
    e = MockConfigEntry(
        domain=DOMAIN,
        title=address,
        unique_id=address,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: address,
            CONF_BED_TYPE: "mline",
            CONF_PROTOCOL_VARIANT: protocol,
            CONF_PRODUCT_TYPE: "four",
            CONF_HAS_MASSAGE: True,
            CONF_DISABLE_ANGLE_SENSING: True,
            "disconnect_after_command": False,
        },
    )
    e.add_to_hass(hass)
    co = AdjustableBedCoordinator(hass, e)
    client = MagicMock(is_connected=True, services=gatt())
    client.disconnect = AsyncMock()
    client.write_gatt_char, client.start_notify, client.stop_notify = (
        AsyncMock(),
        AsyncMock(),
        AsyncMock(),
    )
    co._client = client
    co._controller = runtime.MLineController(co, protocol)
    await co._controller.async_discover_capabilities()
    await co._controller.start_notify()
    co.async_ensure_connected = AsyncMock(return_value=True)
    co.async_connect = AsyncMock(return_value=True)
    co._async_refresh_controller_auth = AsyncMock()
    hass.data.setdefault(DOMAIN, {})[e.entry_id] = co
    return co, client


async def test_public_service_all_target_admission_stop_during_first_target(hass, monkeypatch):
    from custom_components.adjustable_bed.services import async_register_services

    left, lc = await make_receiver(hass, "AA:BB:CC:DD:14:71")
    right, rc = await make_receiver(hass, "AA:BB:CC:DD:14:72")
    await async_register_services(hass)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        lambda *_: ([(left, "both"), (right, "both")], []),
    )

    async def stop_other(char, data, **kwargs):
        await right.async_stop_command()

    lc.write_gatt_char.side_effect = stop_other
    with virtual_clock():
        await hass.services.async_call(
            DOMAIN,
            "mline_command",
            {"device_id": ["left", "right"], "action": "privacy", "enabled": True},
            blocking=True,
        )
    assert codec.AUXILIARY["openPrivacyMode"] in frames(lc)
    assert codec.AUXILIARY["openPrivacyMode"] not in frames(rc)
    with virtual_clock():
        await left.async_shutdown()
        await right.async_shutdown()


async def test_paired_sides_and_sequential_both_renewal_rejected_before_claim(hass, monkeypatch):
    from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
    from custom_components.adjustable_bed.services import async_register_services

    left, lc = await make_receiver(hass, "AA:BB:CC:DD:14:73")
    right, rc = await make_receiver(hass, "AA:BB:CC:DD:14:74", protocol="okin")
    e = MockConfigEntry(domain=DOMAIN, data={"pair_id": "mline147"})
    e.add_to_hass(hass)
    pair = PairedBedCoordinator(
        hass, e, {"left": left, "right": right}, connection_mode="concurrent"
    )
    await async_register_services(hass)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        lambda *_: ([(pair, "right")], []),
    )
    with virtual_clock():
        await hass.services.async_call(
            DOMAIN,
            "timed_move",
            {"device_id": "pair", "motor": "lumbar", "direction": "up", "duration_ms": 150},
            blocking=True,
        )
    assert not frames(lc)
    assert frames(rc)[0] == codec.control("machinery4Up", "okin")
    assert frames(rc)[-1] == codec.control("stopCommand", "okin")
    await pair.async_shutdown()
    # A fresh explicit sequential pair must reject before invoking either reservation.
    pair = PairedBedCoordinator(
        hass, e, {"left": left, "right": right}, connection_mode="sequential"
    )
    monkeypatch.setattr(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        lambda *_: ([(pair, "both")], []),
    )
    claim_left, claim_right = MagicMock(), MagicMock()
    monkeypatch.setattr(left, "claim_hold_lease", claim_left)
    monkeypatch.setattr(right, "claim_hold_lease", claim_right)
    before = (len(frames(lc)), len(frames(rc)))
    with virtual_clock(), pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "timed_move",
            {
                "device_id": "pair",
                "motor": "back",
                "direction": "up",
                "duration_ms": 200,
                "hold_owner": "card",
                "hold_generation": 1,
            },
            blocking=True,
        )
    assert not claim_left.called and not claim_right.called
    assert before == (len(frames(lc)), len(frames(rc)))
    with virtual_clock():
        await pair.async_shutdown()


async def test_hold_admission_is_captured_before_import_await(hass, monkeypatch):
    from custom_components.adjustable_bed import services

    co, client = await make_receiver(hass, "AA:BB:CC:DD:14:75")
    await services.async_register_services(hass)
    monkeypatch.setattr(services, "_resolve_sided_targets", lambda *_: ([(co, "both")], []))

    async def stopped_import(*args):
        await co.async_stop_command()

    monkeypatch.setattr(services, "async_import_modules", stopped_import)
    with virtual_clock():
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": "bed", "control": "back_up", "duration": 0.2},
            blocking=True,
        )
    assert codec.control("headUp", "sleep") not in frames(client)
    with virtual_clock():
        await co.async_shutdown()


@pytest.mark.parametrize("protocol", ["sleep", "smartsainuo", "okin"])
async def test_registered_alarm_and_raw_history_response(hass, monkeypatch, protocol):
    from custom_components.adjustable_bed.services import async_register_services

    co, client = await make_receiver(hass, "AA:BB:CC:DD:14:76", protocol=protocol)
    await async_register_services(hass)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        lambda *_: ([(co, "both")], []),
    )
    now = datetime(2026, 11, 14, 8, 0)
    monkeypatch.setattr(runtime.dt_util, "now", lambda: now)
    with virtual_clock():
        await hass.services.async_call(
            DOMAIN,
            "mline_set_alarm",
            {
                "device_id": "bed",
                "enabled": True,
                "time": "07:17:00",
                "wake_mode": "m1",
                "weekdays": [],
            },
            blocking=True,
        )
    assert frames(client)[0] == codec.alarm(protocol, 7, 17, 1, "m1")
    assert (
        frames(client)[-1] == codec.AUXILIARY[f"checkAlarm.{'P2' if protocol == 'okin' else 'P1'}"]
    )
    client.write_gatt_char.reset_mock()
    with virtual_clock():
        await hass.services.async_call(
            DOMAIN, "mline_set_alarm", {"device_id": "bed", "enabled": False}, blocking=True
        )
    assert (
        frames(client)[0] == codec.AUXILIARY[f"closeAlarm.{'P2' if protocol == 'okin' else 'P1'}"]
    )
    if protocol == "sleep":
        with virtual_clock():
            result = await hass.services.async_call(
                DOMAIN,
                "mline_command",
                {"device_id": "bed", "action": "history_read"},
                blocking=True,
                return_response=True,
            )
            assert result["transfers"][0]["groups"] == [[]]
            await hass.services.async_call(
                DOMAIN,
                "mline_command",
                {
                    "device_id": "bed",
                    "action": "history_ack",
                    "transfer": result["transfers"][0]["transfer"],
                },
                blocking=True,
            )
        assert frames(client)[-2:] == [codec.AUXILIARY["confirmGainHistoryData"]] * 2
    with virtual_clock():
        await co.async_shutdown()


async def test_notification_enable_completion_cannot_revive_a_stale_session(bed):
    c, co, client = bed
    await c.async_discover_capabilities()

    async def disconnect_during_enable(*args):
        c.on_disconnect()

    client.start_notify.side_effect = disconnect_during_enable
    with pytest.raises(ConnectionError):
        await c.start_notify()
    assert c._link is None and not c._notifying


async def test_completed_history_ack_token_expires_without_a_timer_or_write(bed):
    c, co, client = await connected(bed)
    with virtual_clock():
        result = await c.read_history()
        client.write_gatt_char.reset_mock()
        await asyncio.sleep(runtime.HISTORY_ACK_WINDOW + 0.01)
        with pytest.raises(ValueError):
            await c.acknowledge_history(result["transfer"])
    assert not frames(client) and c._history_token is None


def test_smartsainuo_minute_bcd_does_not_convert_hour():
    assert codec.alarm("smartsainuo", 23, 59, 130, "m1") == bytes.fromhex("070582021759000101")


@pytest.mark.parametrize("duration", [None, 0.2])
async def test_goto_preset_fences_later_target_after_stop(hass, monkeypatch, duration):
    from custom_components.adjustable_bed.services import async_register_services

    left, lc = await make_receiver(hass, "AA:BB:CC:DD:14:81")
    right, rc = await make_receiver(hass, "AA:BB:CC:DD:14:82")
    await async_register_services(hass)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        lambda *_: ([(left, "both"), (right, "both")], []),
    )
    stopped = False

    async def stop_right(char, data, **kwargs):
        nonlocal stopped
        if not stopped:
            stopped = True
            await right.async_stop_command()

    lc.write_gatt_char.side_effect = stop_right
    data = {"device_id": ["left", "right"], "preset": 1}
    if duration is not None:
        data["duration"] = duration
    with virtual_clock():
        await hass.services.async_call(DOMAIN, "goto_preset", data, blocking=True)
    assert codec.control("memory5_M1", "sleep") in frames(lc)
    assert codec.control("memory5_M1", "sleep") not in frames(rc)
    with virtual_clock():
        await left.async_shutdown()
        await right.async_shutdown()


async def test_goto_preset_child_mode_fails_all_target_preflight(hass, monkeypatch):
    from custom_components.adjustable_bed.services import async_register_services

    left, lc = await make_receiver(hass, "AA:BB:CC:DD:14:83")
    right, rc = await make_receiver(hass, "AA:BB:CC:DD:14:84")
    hass.config_entries.async_update_entry(
        right.entry, data={**right.entry.data, app.CHILD_MODE: True}
    )
    await async_register_services(hass)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        lambda *_: ([(left, "both"), (right, "both")], []),
    )
    with virtual_clock(), pytest.raises(ServiceValidationError, match="child mode"):
        await hass.services.async_call(
            DOMAIN, "goto_preset", {"device_id": ["left", "right"], "preset": 1}, blocking=True
        )
    assert not frames(lc) and not frames(rc)
    with virtual_clock():
        await left.async_shutdown()
        await right.async_shutdown()


@pytest.mark.parametrize(
    "name,services",
    [
        ("SLEEP147", []),
        ("ACME_SLEEP147", [codec.NORDIC_SERVICE]),
        ("SMARTBED147", [codec.NORDIC_SERVICE]),
        ("OKIN147", [codec.FFE_SERVICE]),
    ],
)
def test_detection_offers_mline_without_overriding_receiver(name, services):
    from custom_components.adjustable_bed.detection import detect_bed_type, detect_bed_type_detailed
    from tests.test_detection import _make_service_info

    info = _make_service_info(name=name, service_uuids=services)
    result = detect_bed_type_detailed(info)
    assert "mline" in {result.bed_type, *(result.ambiguous_types or ())}
    assert "name:mline_app_candidate" in result.signals
    if not services:
        assert result.bed_type == "mline" and result.confidence == 0.3
        assert detect_bed_type(info) is None
    else:
        assert result.bed_type != "mline"


def test_mline_search_hint_preserves_explicit_app_and_matching_receiver():
    from custom_components.adjustable_bed.const import BED_TYPE_MALOUF_NEW_OKIN
    from custom_components.adjustable_bed.profile_recommendations import recommend_profile
    from tests.test_profile_recommendations import info

    observed = info("Smartbed428000193")
    observed.manufacturer_data = {89: bytes.fromhex("4142010204")}
    assert (
        recommend_profile(
            {CONF_BED_TYPE: BED_TYPE_MALOUF_NEW_OKIN, CONF_PROTOCOL_VARIANT: "auto"}, observed, {}
        )
        is None
    )
    assert (
        recommend_profile({CONF_BED_TYPE: "mline", CONF_PROTOCOL_VARIANT: "sleep"}, observed, {})
        is None
    )
