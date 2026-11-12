"""Row178 frozen literals and actual Yamada production paths, no APK replay."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.keeson import yamada
from custom_components.adjustable_bed.beds.keeson.yamada_state import AlarmParser
from custom_components.adjustable_bed.codec import keeson, okin_nframe
from custom_components.adjustable_bed.const import (
    BED_TYPE_YAMADA,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_MOTOR_PULSE_COUNT,
    CONF_MOTOR_PULSE_DELAY_MS,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.controller_state import ControllerState
from custom_components.adjustable_bed.detection import (
    BED_TYPE_DISPLAY_NAMES,
    detect_bed_type_detailed,
)
from custom_components.adjustable_bed.profiles import yamada as app
from custom_components.adjustable_bed.profiles.keeson import encode
from tests.hold_lease_wire import virtual_clock

VECTORS = json.loads((Path(__file__).parent / "fixtures/yamada_vectors.json").read_text())
ADDRESS = "AA:BB:CC:DD:01:78"


@pytest.mark.parametrize("row", VECTORS["packet_vectors"], ids=lambda r: r["id"])
def test_every_literal_against_existing_codec_and_app_profile(row):
    i, kind = row["inputs"], row["kind"]
    profile = app.PROFILES[row["protocol"].lower()]
    if kind == "control":
        actual = encode(profile, app.WORDS[row["action"]])
        if row["protocol"] == "P2":
            assert actual == okin_nframe.frame40(app.WORDS[row["action"]])
    elif kind == "clock":
        actual = app.clock(
            profile, datetime(*(i[k] for k in ("year", "month", "day", "hour", "minute", "second")))
        )
    elif kind == "alarm_v1":
        actual = keeson.alarm_table(3, bytes(i["first"] + i["second"]))
    elif kind == "alarm_v2":
        selected = app.Alarm(i["hour"], i["minute"], i["weekday"], i["position"], i["enabled"])
        actual = app.alarm_frame(profile, i["slot"], selected, None)
    else:
        actual = app.queries(profile)[i["index"]][1]
    assert actual == bytes.fromhex(row["expected_bytes"])


@pytest.mark.parametrize("row", VECTORS["parser_vectors"], ids=lambda r: r["id"])
def test_original_valid_parser_cases(row):
    previous = {
        slot: app.Alarm(0, 0, week, 0, False) for slot, week in enumerate(row["previous_weeks"], 1)
    }
    actual = AlarmParser(row["version"] == 1).feed(bytes(row["input"]), previous)
    assert {str(slot): asdict(alarm) for slot, alarm in actual.items()} == row["expected"]


@pytest.mark.parametrize(
    "value,expected", [(0, 32), (128, 32), (1, 32), (127, 32), (129, 129), (255, 255)]
)
def test_caller_weekday_domains(value, expected):
    assert app.alarm_week(value, 6, 0, datetime(2026, 11, 12, 7)) == expected


def test_disabled_unknown_week_is_unknown_and_malformed_safety_is_not_android_truth():
    parser = AlarmParser(True)
    previous = parser.feed(bytes.fromhex("ed8003071e0000082d801c"), {})
    assert previous[1].weekday is None and previous[2].weekday is None
    for packet in (
        "ed8003071e",
        "ed8003071e810e",  # Android can partially mutate the latter.
        "a50c0e071e810e",  # R1 cross-prefix pre-confirmation counterexample.
        "ed8003071e810e0840811c",  # Invalid slot2 minute: HA rejects both atomically.
        "e78001",
        "a50e0e",
    ):
        assert parser.feed(bytes.fromhex(packet), previous) == {}
    assert previous[1].minute == 30
    assert AlarmParser(False).feed(bytes.fromhex("ed8003071e810e082d811c"), {}) == {}


def gatt(write_properties=("write",), *, mixed=False):
    def char(uuid, properties, handle):
        return SimpleNamespace(
            uuid=uuid, properties=list(properties), handle=handle, descriptors=[]
        )

    write = char("0000ffe9-0000-1000-8000-00805f9b34fb", write_properties, 1)
    notify = char("0000ffe4-0000-1000-8000-00805f9b34fb", ("notify",), 2)
    services = [
        SimpleNamespace(uuid="0000ffe5-0000-1000-8000-00805f9b34fb", characteristics=[write]),
        SimpleNamespace(uuid="0000ffe0-0000-1000-8000-00805f9b34fb", characteristics=[notify]),
    ]
    if mixed:
        # Both OR cross-pairs, followed by the later write override.
        services[0].characteristics += [char("6e400002-b5a3-f393-e0a9-e50e24dcca9e", ("write",), 3)]
        services[1].characteristics += [
            char("6e400003-b5a3-f393-e0a9-e50e24dcca9e", ("indicate",), 4)
        ]
        services += [
            SimpleNamespace(
                uuid="6e400001-b5a3-f393-e0a9-e50e24dcca9e",
                characteristics=[
                    char(write.uuid, ("write",), 5),
                    char(notify.uuid, ("notify",), 6),
                ],
            )
        ]
    return services


async def bed(version="p1", services=None):
    client = MagicMock()
    client.is_connected = True
    client.services = services or gatt()
    client.start_notify = AsyncMock()
    client.stop_notify = AsyncMock()
    client.write_gatt_char = AsyncMock()
    coordinator = MagicMock()
    coordinator.client = client
    coordinator.address = ADDRESS
    coordinator.motor_count = 4  # Saved generic fields cannot invent more actuators.
    coordinator.motor_pulse_count = 3
    coordinator.motor_pulse_delay_ms = 100
    coordinator.cancel_command = asyncio.Event()
    coordinator.controller_state = ControllerState()
    coordinator.handle_controller_state_updates.side_effect = lambda *updates: (
        coordinator.controller_state.update((u.key, u.value) for u in updates)
    )
    controller = yamada.YamadaController(coordinator, version=version)
    await controller.async_discover_capabilities()
    return controller, coordinator, client


@pytest.mark.parametrize("version", ("p1", "p2"))
async def test_gatt_roles_every_notify_clock_overlap_and_stale_session(version):
    c, coordinator, client = await bed(version, gatt(mixed=True))
    entered, finish = asyncio.Event(), asyncio.Event()
    callbacks = []

    async def subscribe(char, callback):
        callbacks.append((char, callback))
        entered.set()
        await finish.wait()

    client.start_notify.side_effect = subscribe
    session = SimpleNamespace(async_start_notify=c.start_notify)

    async def finish_subscription():
        await entered.wait()
        # The clock is written while subscription work is still pending.
        for _ in range(10):
            await asyncio.sleep(0)
        assert client.write_gatt_char.called
        finish.set()

    await asyncio.gather(c.async_on_connect(session), finish_subscription())
    assert len(callbacks) == 3
    assert client.write_gatt_char.call_args.args[0].handle == 5
    assert client.write_gatt_char.call_args.kwargs["response"] is True
    char, callback = callbacks[0]
    packet = (
        bytes.fromhex("ed8003071e810e082dff0f")
        if version == "p1"
        else bytes.fromhex("a50c0e008102071e000100000000")
    )
    callback(char, bytearray(packet))
    assert coordinator.controller_state[yamada.ALARM_1] == "on"
    old_link = c._link
    c.on_disconnect()
    await c.async_discover_capabilities()  # Same client identity, a new link epoch.
    callback(char, bytearray(packet))
    assert coordinator.controller_state[yamada.ALARM_1] is None
    with pytest.raises(ConnectionError):
        await c._write(old_link, b"x", asyncio.Event())


async def test_write_property_and_role_gates():
    for properties in (("write-without-response",), ("read",)):
        with pytest.raises(ValueError, match="write-with-response"):
            await bed(services=gatt(properties))
    services = gatt()
    services[1].uuid = "wrong-service"
    with pytest.raises(ValueError, match="both write and notification"):
        await bed(services=services)


@pytest.mark.parametrize("version", ("p1", "p2"))
@pytest.mark.parametrize("ack_s", (0, 0.05, 0.4))
async def test_elapsed_held_movement_and_captured_release(version, ack_s):
    c, _, client = await bed(version)
    events = []
    with virtual_clock() as clock:

        async def write(char, data, **kw):
            events.append((round(clock.now * 1000), bytes(data)))
            await asyncio.sleep(ack_s)

        client.write_gatt_char.side_effect = write
        await c.hold_control("head_up", 650)
    stop = encode(c.profile, 0)
    motion = [(ms, data) for ms, data in events if data != stop]
    releases = [(ms, data) for ms, data in events if data == stop]
    assert all(ms < 650 for ms, _ in motion)
    assert len(motion) == (2 if ack_s == 0.4 else 3)
    assert len(releases) == 2
    assert releases[0][0] >= 750
    assert releases[1][0] >= releases[0][0] + min(300, round(ack_s * 1000))


async def test_configured_pulses_and_save_use_same_word_with_distinct_durations():
    c, _, client = await bed()
    with virtual_clock() as clock:
        await c.move_head_up()
        assert round(clock.now * 1000) == 700  # 3 configured 100ms pulses plus release.
        assert [call.args[1] for call in client.write_gatt_char.call_args_list].count(
            encode(c.profile, 1)
        ) == 3
        client.write_gatt_char.reset_mock()
        await c.program_memory(1)
    frames = [call.args[1] for call in client.write_gatt_char.call_args_list]
    assert frames[:-2] == [encode(c.profile, 0x2000)] * 18
    assert frames[-2:] == [encode(c.profile, 0)] * 2
    assert not c.supports_single_address_pairing and not c.execution.concurrent
    assert len(c.motor_control_specs) == 2 and c.memory_slot_count == 1


async def test_repeated_cancellation_settles_cleanup_and_does_not_retarget():
    c, coordinator, client = await bed()
    started = asyncio.Event()

    async def write(char, data, **kw):
        if data != encode(c.profile, 0):
            started.set()
            await asyncio.Event().wait()

    client.write_gatt_char.side_effect = write
    with virtual_clock():
        task = asyncio.create_task(c.hold_control("head_up", 1000))
        await started.wait()
        coordinator.cancel_command.set()
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert [call.args[1] for call in client.write_gatt_char.call_args_list][-2:] == [
        encode(c.profile, 0)
    ] * 2
    # A changed client invalidates captured cleanup rather than sending on it.
    link = c._link
    coordinator.client = MagicMock(is_connected=True)
    with virtual_clock(), pytest.raises(ConnectionError):
        await c._release(link, encode(c.profile, 0))
    coordinator.client.write_gatt_char.assert_not_called()


@pytest.mark.parametrize("version", ("p1", "p2"))
async def test_query_page_schedule_is_distinct_from_post_save(version):
    c, coordinator, client = await bed(version)
    observed = []
    with virtual_clock() as clock:

        async def write(char, data, **kw):
            observed.append((round(clock.now * 1000), bytes(data)))

        client.write_gatt_char.side_effect = write
        await c.query_alarms()
        expected = sorted(
            (outer + delay, frame)
            for outer in app.PAGE_ROUNDS_MS
            for delay, frame in app.queries(c.profile)
        )
        assert observed == expected
        c._alarms[2] = app.Alarm(8, 45, 255, app.POSITIONS[c.profile.key]["flat"], True)
        plan = c.prepare_alarm(
            slot=1, enabled=True, hour=7, minute=30, weekday=129, preset="memory_1"
        )
        observed.clear()
        start = clock.now
        await c.set_alarm(plan)
        actual = [(ms - round(start * 1000), frame) for ms, frame in observed]
        assert actual == [
            (0, plan.frame),
            *((300 + delay, frame) for delay, frame in app.queries(c.profile)),
        ]
    assert coordinator.controller_state[yamada.ALARM_1] is None  # No invented completion ACK.
    c.on_disconnect()
    with pytest.raises(ConnectionError):
        await c.set_alarm(plan)


async def test_p1_queued_alarm_save_cannot_restore_an_old_other_slot():
    c, coordinator, client = await bed()
    await c.start_notify()
    sender, receive = client.start_notify.call_args.args
    original = bytes.fromhex("ed80030600810e082dff1c")
    receive(sender, bytearray(original))
    first = c.prepare_alarm(slot=1, enabled=True, hour=7, minute=30, weekday=129, preset="memory_1")
    queued = c.prepare_alarm(slot=2, enabled=True, hour=9, minute=0, weekday=130, preset="flat")

    with virtual_clock():
        await c.set_alarm(first)
        assert coordinator.controller_state[yamada.HOUR_1] is None
        assert c._alarms == {}  # No optimistic observations from the write.
        writes = client.write_gatt_char.call_count
        with pytest.raises(ValueError, match="observations changed"):
            await c.set_alarm(queued)
        assert client.write_gatt_char.call_count == writes

        # A delayed pre-save response is visible but cannot authorize a table write.
        receive(sender, bytearray(original))
        assert coordinator.controller_state[yamada.HOUR_1] == 6
        with pytest.raises(ValueError, match="Waiting for the written P1"):
            c.prepare_alarm(slot=2, enabled=True, hour=9, minute=0, weekday=130, preset="flat")

        receive(sender, bytearray(first.frame))
        assert coordinator.controller_state[yamada.HOUR_1] == 7
        with pytest.raises(ValueError, match="observations changed"):
            await c.set_alarm(queued)
        assert client.write_gatt_char.call_count == writes
        fresh = c.prepare_alarm(slot=2, enabled=True, hour=9, minute=0, weekday=130, preset="flat")
        assert fresh.frame == keeson.alarm_table(3, bytes((7, 30, 129, 14, 9, 0, 130, 28)))
        await c.set_alarm(fresh)
        assert client.write_gatt_char.call_args_list[writes].args[1] == fresh.frame
        assert coordinator.controller_state[yamada.HOUR_1] is None


def entry(hass, version):
    e = MockConfigEntry(
        domain=DOMAIN,
        title="アシステック",
        version=5,
        minor_version=3,
        data={
            CONF_ADDRESS: ADDRESS,
            CONF_NAME: "アシステック",
            CONF_BED_TYPE: BED_TYPE_YAMADA,
            CONF_PROTOCOL_VARIANT: version,
            CONF_MOTOR_COUNT: 2,
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_MOTOR_PULSE_COUNT: 2,
            CONF_MOTOR_PULSE_DELAY_MS: 100,
        },
    )
    e.add_to_hass(hass)
    return e


@pytest.mark.parametrize("version", ("p1", "p2"))
async def test_real_setup_entities_alarm_service_and_card_hold(
    hass,
    mock_coordinator_connected,
    mock_bleak_client,
    enable_custom_integrations,
    version,
):
    mock_bleak_client.services = gatt()
    # The generic fixture's protocol simulator stringifies characteristic objects.
    mock_bleak_client.write_gatt_char = AsyncMock()
    mock_bleak_client.start_notify = AsyncMock()
    e = entry(hass, version)
    assert await hass.config_entries.async_setup(e.entry_id)
    await hass.async_block_till_done()
    coordinator = hass.data[DOMAIN][e.entry_id]
    c = coordinator.controller
    assert isinstance(c, yamada.YamadaController)
    registry = er.async_get(hass)
    entities = [v for v in registry.entities.values() if v.config_entry_id == e.entry_id]
    dev = next(v.device_id for v in entities if v.device_id)
    keys = {v.translation_key for v in entities}
    assert {
        "head",
        "feet",
        "yamada_alarm_1",
        "yamada_alarm_2",
        "yamada_query_alarms",
        "yamada_sync_clock",
        "stop",
    } <= keys
    assert not {"massage_toggle", "preset_lounge", "preset_memory_2"} & keys
    stop = next(v.entity_id for v in entities if v.translation_key == "stop")
    stop_state = hass.states.get(stop)
    assert stop_state.attributes["card_section"] == "motors"
    assert stop_state.attributes["card_role"] == "stop"
    covers = [v.entity_id for v in entities if v.domain == "cover"]
    assert len(covers) == 2
    for eid in covers:
        state = hass.states.get(eid)
        assert state.attributes["held_stop_scope"] == "side"
        assert state.attributes["hold_lease_mode"] == "stream"
    data = {
        "device_id": dev,
        "slot": 1,
        "enabled": True,
        "time": "07:30",
        "weekday": 129,
        "preset": "memory_1",
    }
    if version == "p1":
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(DOMAIN, "yamada_set_alarm", data, blocking=True)
        c._alarms[2] = app.Alarm(8, 45, 255, 28, True)
    with virtual_clock():
        await hass.services.async_call(DOMAIN, "yamada_set_alarm", data, blocking=True)
        mock_bleak_client.write_gatt_char.reset_mock()
        await hass.services.async_call(
            DOMAIN,
            "timed_move",
            {
                "device_id": dev,
                "motor": "head",
                "direction": "up",
                "duration_ms": 650,
            },
            blocking=True,
        )
    frames = [call.args[1] for call in mock_bleak_client.write_gatt_char.call_args_list]
    assert frames == [encode(c.profile, 1)] * 3 + [encode(c.profile, 0)] * 2
    mock_bleak_client.write_gatt_char.reset_mock()
    with virtual_clock():

        async def renew():
            await hass.services.async_call(
                DOMAIN,
                "timed_move",
                {
                    "device_id": dev,
                    "motor": "head",
                    "direction": "up",
                    "duration_ms": 200,
                    "hold_owner": "card-yamada",
                    "hold_generation": 1,
                },
                blocking=True,
            )

        holding = asyncio.create_task(renew())
        for _ in range(4):
            await asyncio.sleep(0.1)
            await renew()
            assert not holding.done()
            assert all(
                call.args[1] != encode(c.profile, 0)
                for call in mock_bleak_client.write_gatt_char.call_args_list
            )
        await hass.services.async_call("button", "press", {"entity_id": stop}, blocking=True)
        await holding
    frames = [call.args[1] for call in mock_bleak_client.write_gatt_char.call_args_list]
    assert frames[-2:] == [encode(c.profile, 0)] * 2
    assert (
        frames.count(encode(c.profile, 0)) == 2
    )  # Only captured cleanup, no current-target duplicate.
    with virtual_clock():
        assert await hass.config_entries.async_unload(e.entry_id)


@pytest.mark.parametrize("byte3", (0, 255))
def test_first_manufacturer_value_predicate_and_searchable_app(byte3):
    assert app.manufacturer_version(bytes((89, 65, 77, byte3, 2))) == "p2"
    assert app.manufacturer_version(bytes((89, 65, 77, byte3, 1))) == "p1"
    assert app.manufacturer_version(b"YAM") is None
    assert "アシステック" in BED_TYPE_DISPLAY_NAMES[BED_TYPE_YAMADA]


@pytest.mark.parametrize("name", ("OKIN-BLE test", "sMaRtBeD test"))
def test_shared_name_only_suggests_explicit_app(name):
    info = MagicMock(name=name)
    info.name = name
    info.device.name = name
    info.service_uuids = []
    info.manufacturer_data = {123: b"YAM\x00\x02", 456: b"unrelated"}
    result = detect_bed_type_detailed(info)
    assert BED_TYPE_YAMADA in {result.bed_type, *(result.ambiguous_types or ())}
    assert result.bed_type != BED_TYPE_YAMADA or result.confidence < 1


async def test_factory_refuses_automatic_or_unknown_version():
    c, coordinator, client = await bed()
    coordinator.hass.async_add_import_executor_job = AsyncMock(
        side_effect=lambda fn, *args: fn(*args)
    )
    for version in (None, "auto", "p3"):
        with pytest.raises(ValueError, match="explicitly"):
            await create_controller(coordinator, BED_TYPE_YAMADA, version, client)


@pytest.mark.parametrize("version", ("p1", "p2"))
@pytest.mark.parametrize("slot", (1, 2))
async def test_alarm_write_domains_disable_and_other_slot_preservation(version, slot):
    c, _, _ = await bed(version)
    other = app.Alarm(8, 45, None, app.POSITIONS[c.profile.key]["flat"], False)
    c._alarms[3 - slot] = other
    plan = c.prepare_alarm(
        slot=slot, enabled=False, hour=7, minute=30, weekday=0, preset="memory_1"
    )
    if version == "p1":
        record = bytes((7, 30, 0, 0))
        records = record + other.fields if slot == 1 else other.fields + record
        assert plan.frame == keeson.alarm_table(3, records)
    else:
        assert plan.frame == okin_nframe.alarm((0, 2, 7, 30, 0, 0, 0), slot)
    for invalid in (
        {"slot": True},
        {"hour": 24},
        {"minute": 60},
        {"weekday": -1},
        {"preset": "lounge"},
    ):
        fields = {
            "slot": slot,
            "enabled": True,
            "hour": 7,
            "minute": 30,
            "weekday": 129,
            "preset": "flat",
            **invalid,
        }
        with pytest.raises(ValueError):
            c.prepare_alarm(**fields)


@pytest.mark.parametrize("version", ("p1", "p2"))
async def test_manual_setup_and_restore_own_only_proven_fields(hass, version):
    from custom_components.adjustable_bed.app_profiles import per_side_profile
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from custom_components.adjustable_bed.profile_id import resolve_profile_id
    from custom_components.adjustable_bed.setup_questions import setup_profile_for
    from tests.form_helpers import finish_new_bed
    from tests.test_controller_contract import _FactoryCoordinator

    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    flow.context = {}
    flow._app_after_device = "manual_entry"
    flow._finish_with_verify = AsyncMock(return_value={"type": "create_entry"})
    await flow.async_step_select_app()
    await flow.async_step_select_app({CONF_BED_TYPE: BED_TYPE_DISPLAY_NAMES[BED_TYPE_YAMADA]})
    result = await flow.async_step_manual_entry({"address": ADDRESS})
    assert result["step_id"] == "profile_questions"
    result = await flow.async_step_profile_questions({CONF_PROTOCOL_VARIANT: version})
    assert result["step_id"] == "finish_settings"
    await finish_new_bed(flow, result)
    saved = flow._finish_with_verify.await_args.args[0]
    assert saved[CONF_MOTOR_COUNT] == 2 and saved[CONF_HAS_MASSAGE] is False
    assert saved[CONF_DISABLE_ANGLE_SENSING] is True
    assert resolve_profile_id(saved) == f"yamada:{version}"
    assert per_side_profile(BED_TYPE_YAMADA, version).variant_owned
    profile = setup_profile_for(saved)
    assert profile.questions[0].default_for(saved) == version
    coordinator = _FactoryCoordinator()
    coordinator.entry.data = saved
    restored = await create_controller(coordinator, BED_TYPE_YAMADA, version, None)
    assert restored.profile.key == f"yamada_{version}"
