"""Accepted row090 literals, layout gates and original-link release behavior."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.adjustable_bed.beds.alya.controller import AlyaController
from custom_components.adjustable_bed.beds.alya.protocol import (
    TRANSPORTS,
    alarm_frame,
    clock_frame,
    parse,
    query,
    require_roles,
)
from custom_components.adjustable_bed.profiles.alya import PROFILES, commands
from tests.state_helpers import state_writer

FIXTURES = Path(__file__).parent / "fixtures"
VECTORS = json.loads((FIXTURES / "alya_vectors.json").read_text())
PARSERS = json.loads((FIXTURES / "alya_parsers.json").read_text())
REACHABLE = json.loads((FIXTURES / "alya_reachability.json").read_text())
NOW = datetime.fromisoformat("2026-11-27T12:34:56+00:00")


@pytest.mark.parametrize("vector", VECTORS, ids=lambda v: v["id"])
def test_frozen_builders(vector):
    protocol, action, inputs = vector["protocol"], vector["action"], vector["inputs"]
    if action.startswith("alarm-"):
        fields = inputs["payload"] if action == "alarm-on" else (0, 0, 0, 0)
        frame = alarm_frame(protocol, fields[0], fields[1], fields[2], fields[3], inputs["side"])
    elif action == "set-clock":
        frame = clock_frame(protocol, NOW)
    elif action.startswith("query-"):
        frame = query(protocol, action == "query-alarm")
    else:
        frame = commands(protocol)[action].encode(protocol, inputs["side"])
    assert frame.hex() == vector["expected"]


@pytest.mark.parametrize("key", PROFILES)
def test_layout_reachability(key):
    profile = PROFILES[key]
    expected = {r["action"] for r in REACHABLE if key in r["layouts"]} - {
        "alarm-on",
        "alarm-off",
        "query-alarm",
        "query-massage",
        "set-clock",
    }
    assert set(profile.commands) == expected
    assert profile.side_controls == (key == "dacheng_5")


@pytest.mark.parametrize("vector", PARSERS, ids=lambda v: v["id"])
def test_frozen_parsers(vector):
    inputs = vector["inputs"]
    key = (
        "bluetooth_2"
        if inputs["protocol"] == "OREBedBleProtocol"
        else f"{inputs.get('device_type', 'CB').lower()}_{inputs.get('motors', 2)}"
    )
    # Two synthetic dormant CB1221 layouts share the live CB24 parser.
    if key not in PROFILES:
        key = "cb1221_2"
    actual = parse(PROFILES[key], bytes(inputs["data"]))
    expected = vector["expected"]
    if expected == {"ack": None}:
        expected = {}
    actual = {
        ("on" if k == "alarm_enabled" else k.removeprefix("alarm_")): v for k, v in actual.items()
    }
    if "weak-header" in vector["id"]:
        assert actual == {}  # Deliberate malformed-header safety correction.
    else:
        assert actual == expected


def make(key="cb24_5"):
    coord = MagicMock()
    coord.address = "AA:BB:CC:DD:EE:90"
    coord.cancel_command = asyncio.Event()
    coord.motor_pulse_count = 2
    coord.controller_state = {}
    coord.handle_controller_state_updates.side_effect = state_writer(coord.controller_state)
    route = TRANSPORTS[PROFILES[key].protocol]
    tx = SimpleNamespace(uuid=route.write, properties=["write"], handle=1)
    rx = SimpleNamespace(uuid=route.notify, properties=["notify"], handle=2)
    coord.client = MagicMock(
        is_connected=True,
        services=[
            SimpleNamespace(uuid=route.write_service, characteristics=[tx]),
            SimpleNamespace(uuid=route.notify_service, characteristics=[rx]),
        ],
    )
    for name in ("write_gatt_char", "start_notify", "stop_notify"):
        setattr(coord.client, name, AsyncMock())
    return AlyaController(coord, profile=key)


@pytest.fixture
def pauses(monkeypatch):
    observed = []

    async def pause(seconds, cancel):
        observed.append(seconds)
        return cancel.is_set()

    monkeypatch.setattr(AlyaController, "_pause", staticmethod(pause))
    return observed


def frames(controller):
    return [bytes(c.args[1]).hex() for c in controller.client.write_gatt_char.call_args_list]


async def test_axis_and_preset_release_counts(pauses):
    c = make()
    await c.async_discover_capabilities()
    await c.move_back_up()
    assert frames(c) == ["05020000000100"] * 2 + ["05020000000000"] * 2
    assert pauses == [0.3] * 4
    c.client.write_gatt_char.reset_mock()
    await c.preset_flat()
    assert frames(c) == ["05020800000000"] * 2 + ["05020000000000"]
    assert not c.supports_memory_programming


async def test_cancel_before_submission_sends_nothing(pauses):
    c = make()
    await c.async_discover_capabilities()
    c._coordinator.cancel_command.set()
    await c.move_back_up()
    assert frames(c) == []


async def test_cancel_in_write_settles_then_releases_original_side(pauses):
    c = make("dacheng_5")
    await c.async_discover_capabilities()
    entered, finish = asyncio.Event(), asyncio.Event()

    async def write(*args, **kwargs):
        if not entered.is_set():
            entered.set()
            await finish.wait()

    c.client.write_gatt_char.side_effect = write

    async def move():
        with c.side_scope("left"):
            await c.move_back_up()

    task = asyncio.create_task(move())
    await entered.wait()
    c._coordinator.cancel_command.set()
    task.cancel()
    await asyncio.sleep(0)
    assert frames(c) == ["05020000000101"]
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert frames(c) == ["05020000000101", "05020000000001", "05020000000001"]


async def test_replacement_link_never_receives_cleanup(pauses):
    c = make()
    await c.async_discover_capabilities()
    original = c.client

    async def replace(*args, **kwargs):
        c._coordinator.client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
        c._coordinator.cancel_command.set()

    original.write_gatt_char.side_effect = replace
    await c.move_back_up()
    c.client.write_gatt_char.assert_not_called()
    assert original.write_gatt_char.await_count == 1


async def test_reports_are_session_bound_and_no_optimistic_state(pauses):
    c = make("bluetooth_2")
    await c.async_discover_capabilities()
    await c.start_notify()
    notify = c.client.start_notify.call_args.args[1]
    c.client.write_gatt_char.assert_not_called()
    await c.execute("light")
    assert c._observed == {}
    sender = c._session.notify
    notify(sender, bytearray.fromhex("a55a000007205000010203020101"))
    assert c._observed["head"] == 1
    assert c.protocol_diagnostics["received"] == c._observed
    assert not c.controller_state_sensor_specs
    assert not any(key.startswith("alya_report") for key in c._coordinator.controller_state)
    c.protocol_diagnostics["received"].clear()
    assert c._observed["head"] == 1
    c.on_disconnect()
    notify(sender, bytearray.fromhex("a55a000007205000010203020101"))
    assert c._observed == {}
    assert c.protocol_diagnostics["received"] == {}


async def test_service_scoped_roles_reject_mixed_or_indicate_only():
    c = make("cb_2")
    assert require_roles(c.client, "P2")[0].uuid == TRANSPORTS["P2"].write
    c.client.services[0].uuid = TRANSPORTS["P2"].notify_service
    with pytest.raises(ValueError):
        require_roles(c.client, "P2")
    c = make()
    c.client.services[1].characteristics[0].properties = ["indicate"]
    with pytest.raises(ValueError):
        require_roles(c.client, "P4")


async def test_light_toggle_invalidates_last_report(pauses):
    c = make("bluetooth_2")
    await c.async_discover_capabilities()
    c._observed["light"] = False
    await c.lights_on()
    assert "light" not in c._observed
    with pytest.raises(ServiceValidationError):
        await c.lights_on()


async def test_bluetooth_massage_page_can_be_disabled():
    c = make("bluetooth_2")
    c._has_massage = False
    assert "massage-on" not in c.held_control_options
    assert not any("intensity" in spec.key for spec in c.controller_button_specs)


@pytest.mark.parametrize("outcome", ["cancel", "expire"])
async def test_queued_scheduler_work_never_moves(outcome, pauses):
    from custom_components.adjustable_bed.command_scheduler import (
        CommandIntent,
        CommandKind,
        CommandOutcome,
        DeviceCommandScheduler,
        HoldLease,
        command_resources,
    )

    c = make()
    await c.async_discover_capabilities()
    scheduler = DeviceCommandScheduler("alya-queue")
    started, finish = asyncio.Event(), asyncio.Event()

    async def block(context):
        started.set()
        await finish.wait()

    blocking = asyncio.create_task(
        scheduler.execute(CommandIntent(block, resources=command_resources("configuration")))
    )
    await started.wait()

    async def move(context):
        c._coordinator.cancel_command = context.cancel_event
        await c.move_back_up()

    handle = await scheduler.enqueue(
        CommandIntent(
            move,
            cancel_running=False,
            resources=command_resources("motor:back"),
            **(
                {
                    "kind": CommandKind.HOLD,
                    "lease": HoldLease(
                        owner="card", generation=1, action="headup", duration_s=0.01
                    ),
                }
                if outcome == "expire"
                else {}
            ),
        )
    )
    if outcome == "cancel":
        await scheduler.cancel(handle)
    await asyncio.wait_for(handle.future, 1)
    assert frames(c) == []
    assert handle.outcome is (
        CommandOutcome.EXPIRED if outcome == "expire" else CommandOutcome.GROUP_ABORTED
    )
    finish.set()
    await blocking
    await scheduler.async_shutdown()


async def test_later_public_stop_is_not_suppressed(pauses):
    from custom_components.adjustable_bed.command_scheduler import (
        CommandIntent,
        DeviceCommandScheduler,
    )

    c = make()
    await c.async_discover_capabilities()
    scheduler = DeviceCommandScheduler("alya-cleanup")

    async def cleaned(context):
        await c.stop_all()
        await c.stop_all()

    await scheduler.execute(CommandIntent(cleaned))
    assert frames(c) == ["05020000000000"]

    async def new_stop(context):
        await c.stop_all()

    await scheduler.execute(CommandIntent(new_stop))
    assert frames(c) == ["05020000000000"] * 2
    await scheduler.async_shutdown()


@pytest.mark.parametrize("profile", ["cb24_5", "dacheng_5"])
@pytest.mark.parametrize("control", ["hpsup", "hpsdown"])
async def test_unknown_hps_has_evidence_but_no_executable_control(profile, control):
    c = make(profile)
    assert control in c.profile.commands
    assert control not in c.held_control_options
    assert not any(spec.key == f"alya_{control}" for spec in c.controller_button_specs)
    await c.async_discover_capabilities()
    with pytest.raises(ServiceValidationError):
        await c.execute(control)
    assert frames(c) == []


@pytest.mark.parametrize("preempted", [False, True])
@pytest.mark.parametrize("released", ["both", "left", "right"])
@pytest.mark.parametrize("requested", ["both", "left", "right"])
async def test_stop_cleanup_must_cover_requested_side(pauses, preempted, released, requested):
    from custom_components.adjustable_bed.command_scheduler import (
        CommandIntent,
        DeviceCommandScheduler,
    )

    c = make("dacheng_5")
    await c.async_discover_capabilities()
    scheduler = DeviceCommandScheduler("alya-stop-side")
    previous = None
    expected = []

    async def release(context):
        nonlocal previous
        previous = context
        with c.side_scope(released):
            await c.move_back_up()
        expected.extend(frames(c))
        if not preempted:
            await stop(context)

    async def stop(context):
        if preempted:
            context.preempted_contexts = (previous,)
        with c.side_scope(requested):
            await c.stop_all()

    try:
        await scheduler.execute(CommandIntent(release))
        if preempted:
            await scheduler.execute(CommandIntent(stop))
        if released != "both" and released != requested:
            side = {"both": 0, "left": 1, "right": 2}[requested]
            expected.append(c.profile.commands["stop"].encode(c.profile.protocol, side).hex())
        assert frames(c) == expected
    finally:
        await scheduler.async_shutdown()


async def test_alarm_preflights_all_targets_before_mutation(hass, monkeypatch):
    from datetime import time

    from custom_components.adjustable_bed import services
    from custom_components.adjustable_bed.alarm import AlarmCapability
    from tests.error_helpers import raises_key
    from tests.test_generic_services import target

    first, one = target(
        "alya",
        family=AlyaController,
        alarm_capability=AlarmCapability(wake_actions=("memory_1",), weekdays=True),
        configure_alarm=AsyncMock(),
    )
    second, two = target(
        "alya",
        family=AlyaController,
        alarm_capability=AlarmCapability(wake_actions=("zero_g",), weekdays=True),
        configure_alarm=AsyncMock(),
    )
    monkeypatch.setattr(
        services, "_resolve_sided_targets", lambda *_: ([(first, "both"), (second, "both")], [])
    )
    call = SimpleNamespace(
        hass=hass,
        data={
            "device_id": ["one", "two"],
            "enabled": True,
            "time": time(7, 30),
            "wake_action": "memory_1",
            "weekdays": ["monday", "tuesday"],
        },
    )
    with raises_key("alarm_wake_action_not_supported"):
        await services.handle_set_alarm(call)
    one.configure_alarm.assert_not_called()
    two.configure_alarm.assert_not_called()


def test_setup_owns_layout_and_asks_optional_bluetooth_massage():
    from custom_components.adjustable_bed.const import (
        CONF_BED_TYPE,
        CONF_HAS_MASSAGE,
        CONF_PROTOCOL_VARIANT,
    )
    from custom_components.adjustable_bed.setup_questions import setup_profile_for

    profile = setup_profile_for({CONF_BED_TYPE: "alya", CONF_PROTOCOL_VARIANT: "bluetooth_2"})
    assert profile is not None
    question = next(q for q in profile.questions if q.key == CONF_PROTOCOL_VARIANT)
    assert question.searchable
    assert set(question.options({})) == set(PROFILES)
    assert (
        profile.settled({CONF_PROTOCOL_VARIANT: "bluetooth_2", CONF_HAS_MASSAGE: False})[
            CONF_HAS_MASSAGE
        ]
        is False
    )
    assert (
        profile.settled({CONF_PROTOCOL_VARIANT: "cb24_5", CONF_HAS_MASSAGE: False})[
            CONF_HAS_MASSAGE
        ]
        is True
    )


@pytest.mark.parametrize("valid", [True, False])
async def test_setup_probe_uses_runtime_roles(hass, monkeypatch, valid):
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from tests.test_config_flow import _patch_gate

    c = make("cb_2")
    client = c.client
    client.disconnect = AsyncMock()
    if not valid:
        client.services[0].uuid = TRANSPORTS["P2"].notify_service
    flow = AdjustableBedConfigFlow()
    flow.hass = hass
    monkeypatch.setattr(
        "bleak_retry_connector.establish_connection", AsyncMock(return_value=client)
    )
    monkeypatch.setattr(
        "custom_components.adjustable_bed.config_flow.discover_services", AsyncMock()
    )
    monkeypatch.setattr(
        "custom_components.adjustable_bed.config_flow.read_ble_device_info",
        AsyncMock(return_value=(None, None)),
    )
    with _patch_gate("test", -50):
        report = await flow._probe_capabilities(c._coordinator.address, None, "alya", "cb_2")
    assert report.alya_transport_valid is valid
    client.disconnect.assert_awaited_once()
    client.write_gatt_char.assert_not_called()


def test_refresh_entity_is_diagnostic_and_disabled():
    from homeassistant.const import EntityCategory

    from custom_components.adjustable_bed.button import ControllerActionButton

    c = make()
    spec = next(s for s in c.controller_button_specs if s.key == "alya_query-massage")
    entity = ControllerActionButton(c._coordinator, spec)
    assert entity.entity_category is EntityCategory.DIAGNOSTIC
    assert entity.entity_registry_enabled_default is False
    assert entity._spec.card.section.value == "utility"


async def test_cancelled_movement_reports_partial_delivery_and_does_not_count_release(pauses):
    from custom_components.adjustable_bed.command_scheduler import (
        CommandIntent,
        Delivery,
        DeviceCommandScheduler,
        delivered,
    )

    c = make()
    await c.async_discover_capabilities()
    scheduler = DeviceCommandScheduler("alya-delivery")
    seen = []

    async def write(char, data, **kwargs):
        if bytes(data).hex() == "05020000000100":
            c._coordinator.cancel_command.set()

    c.client.write_gatt_char.side_effect = write

    async def move(context):
        c._coordinator.cancel_command = context.cancel_event
        with delivered(seen.append):
            await c.move_back_up()

    await scheduler.execute(CommandIntent(move))
    assert seen == [Delivery.PARTIAL]
    assert frames(c) == ["05020000000100", "05020000000000", "05020000000000"]
    await scheduler.async_shutdown()


@pytest.mark.parametrize("profile", PROFILES)
async def test_weekly_alarm_through_shared_action(hass, pauses, monkeypatch, profile):
    from tests.alarm_helpers import call_set_alarm
    from tests.error_helpers import raises_key

    c = make(profile)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.alya.controller.dt_util.now", lambda: NOW
    )
    await c.async_discover_capabilities()
    if not c.supports_clock_alarm:
        with raises_key("alarm_not_supported"):
            await call_set_alarm(
                hass,
                c,
                {"enabled": True, "time": "06:45:00", "wake_action": "zero_g"},
                bed_type="alya",
            )
        assert frames(c) == []
        return
    await call_set_alarm(
        hass,
        c,
        {
            "enabled": True,
            "time": "06:45:00",
            "weekdays": ["monday", "friday"],
            "wake_action": "zero_g",
        },
        bed_type="alya",
    )
    expected = alarm_frame(c.profile.protocol, 6, 45, 0x80 | 2 | 32, 13, c._side)
    assert frames(c) == [
        clock_frame(c.profile.protocol, NOW).hex(),
        expected.hex(),
        query(c.profile.protocol, True).hex(),
    ]
    assert pauses == [0.3, 0.3]
    assert c._observed == {}


@pytest.mark.parametrize("profile", PROFILES)
def test_light_feedback_requires_a_proven_parser(hass, profile):
    from custom_components.adjustable_bed.light import AdjustableBedOnOffLight, _light_entities_for

    c = make(profile)
    c._coordinator.capability_controller = c
    assert c.supports_light_state_feedback == (c.profile.protocol == "P1")
    assert (
        any(
            isinstance(entity, AdjustableBedOnOffLight)
            for entity in _light_entities_for(hass, c._coordinator)
        )
        == c.supports_light_state_feedback
    )
    assert any(spec.key == "alya_light" for spec in c.controller_button_specs) == c.supports_lights


@pytest.mark.parametrize("interruption", ["cancel", "replacement"])
async def test_alarm_continuations_stay_on_the_captured_session(monkeypatch, interruption):
    c = make("cb_2")
    await c.async_discover_capabilities()
    original = c.client

    async def pause(seconds, cancel):
        assert seconds == 0.3
        if interruption == "cancel":
            cancel.set()
            return True
        c._coordinator.client = MagicMock(is_connected=True, write_gatt_char=AsyncMock())
        return False

    monkeypatch.setattr(c, "_pause", pause)
    configure = c.configure_clock_alarm(
        enabled=True, weekdays=(0,), hour=6, minute=45, preset="zero_g"
    )
    if interruption == "replacement":
        with pytest.raises(ConnectionError):
            await configure
        c.client.write_gatt_char.assert_not_called()
    else:
        await configure
    assert original.write_gatt_char.await_count == 1


@pytest.mark.parametrize("profile", PROFILES)
async def test_factory_uses_explicit_layout(profile):
    from custom_components.adjustable_bed.controller_factory import create_controller
    from tests.test_controller_contract import _FactoryCoordinator, _make_connected_client

    coordinator = _FactoryCoordinator()
    coordinator.entry.options = {}
    controller = await create_controller(coordinator, "alya", profile, _make_connected_client())
    assert isinstance(controller, AlyaController)
    assert controller.profile is PROFILES[profile]
    assert controller.supports_single_address_pairing is (profile == "dacheng_5")


def test_manual_app_choice_is_searchable_before_layout():
    from custom_components.adjustable_bed.detection import get_bed_type_options

    rows = [row for row in get_bed_type_options() if row["value"] == "alya"]
    assert len(rows) == 1
    assert "Alya" in rows[0]["label"]


@pytest.mark.parametrize("profile", PROFILES)
async def test_complete_offline_setup_keeps_selected_layout_and_motor_count(hass, profile):
    from unittest.mock import patch

    from homeassistant.const import CONF_ADDRESS, CONF_NAME
    from homeassistant.data_entry_flow import FlowResultType

    from custom_components.adjustable_bed import const
    from custom_components.adjustable_bed.config_flow import AdjustableBedConfigFlow
    from tests.form_helpers import form_fields

    flow = AdjustableBedConfigFlow()
    flow.hass, flow.context = hass, {"source": "user"}
    flow._selected_bed_type = "alya"
    result = await flow.async_step_manual_entry({CONF_ADDRESS: "AA:BB:CC:DD:EE:90"})
    assert result["step_id"] == "profile_questions"
    assert const.CONF_PROTOCOL_VARIANT in form_fields(result["data_schema"])
    with patch.object(flow, "_verification_possible", return_value=False):
        result = await flow.async_step_profile_questions({const.CONF_PROTOCOL_VARIANT: profile})
        assert result["step_id"] == "finish_settings"
        result = await flow.async_step_finish_settings(
            {CONF_NAME: "Alya", const.CONF_CONNECTION_MODE: "idle"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][const.CONF_PROTOCOL_VARIANT] == profile
    assert result["data"][const.CONF_MOTOR_COUNT] == PROFILES[profile].motors
