"""Row067 exact artifact vectors, all 28 layouts and finite command lifecycles."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.adjustable_bed.beds.adjustamattress import (
    FFE_NOTIFY,
    FFE_NOTIFY_SERVICE,
    FFE_WRITE,
    FFE_WRITE_SERVICE,
    FFF0,
    NUS_NOTIFY,
    NUS_SERVICE,
    NUS_WRITE,
    AdjustaMattressController,
)
from custom_components.adjustable_bed.beds.adjustamattress_protocol import (
    BASE_ACTIONS,
    CYCLIC,
    DEDICATED,
    LAYOUT_ACTIONS,
    MODELS,
    State,
    dedicated_massage,
    frame,
    has_snore,
    model_from_name,
    parse,
    scan_admits,
)
from custom_components.adjustable_bed.const import (
    ADJUSTAMATTRESS_VARIANTS,
    BED_TYPE_ADJUSTAMATTRESS,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.validators import get_variants_for_bed_type

FIXTURES = Path(__file__).parent / "fixtures/adjustamattress"
COMMANDS = json.loads((FIXTURES / "commands.json").read_text())
NOTIFICATIONS = json.loads((FIXTURES / "notifications.json").read_text())


@pytest.mark.parametrize("row", COMMANDS, ids=lambda r: r["id"])
def test_all_180_command_vectors(row):
    inputs = row["inputs"].copy()
    parts = inputs.pop("parts", [0, 0, 0, 0, 0, 1, 1, 1, 2026])
    now = datetime(parts[8], parts[7], parts[5], parts[4], parts[3], parts[2])
    retained = inputs.pop("retained_frame", None)
    packet = frame(row["protocol"], row["action"], now=now, **inputs)
    if row["protocol"] == "P2" and row["action"] == "underbedLighting":
        assert packet is None  # No lighting opcode exists; arbitrary prior replay is unsafe.
        assert retained is not None
    else:
        assert (packet.hex(" ").upper() if packet is not None else "NO WRITE") == row[
            "expected_bytes"
        ]


FIELD_NAMES = {
    "massageTime": "massage_time",
    "headIntensity": "head_intensity",
    "footIntensity": "foot_intensity",
    "alarmOn": "alarm_on",
    "alarmHour": "alarm_hour",
    "alarmMin": "alarm_minute",
    "alarmType": "alarm_type",
    "alarmRepeat": "alarm_repeat",
    "antiSnoreEnabled": "snore_enabled",
    "strengthIndex": "strength_index",
}


@pytest.mark.parametrize("row", NOTIFICATIONS)
def test_notification_fields(row):
    state = State()
    parse(row["protocol"], bytes(row["input"]), state)
    for key, expected in row["expected_state"].items():
        assert getattr(state, FIELD_NAMES.get(key, key)) == expected


@pytest.mark.parametrize("model", MODELS)
def test_short_notifications_do_not_partially_mutate_or_throw(model):
    for size in range(20):
        for prefix in (b"\xa5\x0b\x0e", b"\xa5\x0c", b"\xed\x80", b"\xe2\xfe"):
            data = (prefix + bytes(20))[:size]
            state = State()
            parse(model, data, state)


def test_fragment_buffer_and_on_only_alarm_update():
    state = State()
    assert parse("P1", b"\xf4\xfe\x16\x00", state) == set()
    parse("P1", bytes(19), state)
    assert state.saved_buffer == b"\xf4\xfe\x16\x00"
    state = State(alarm_type=9)
    assert "alarm_on" in parse("P3", bytes((165, 12, 0, 0, 0, 0, 0, 0, 0, 1)), state)
    assert state.alarm_on


def char(uuid, properties):
    return SimpleNamespace(uuid=uuid, properties=properties, handle=4)


def service(uuid, *chars):
    return SimpleNamespace(uuid=uuid, characteristics=chars)


def make_controller(model="P1", layout=1, *, automatic=False, name=None, services=None):
    c = MagicMock()
    c.hass.data = {}
    c.address = "AA:BB:CC:DD:EE:FF"
    c.cancel_command = asyncio.Event()
    c.motor_pulse_count = 2
    c.entry = SimpleNamespace(data={"ble_device_name": name} if name else {})
    c.client = MagicMock(is_connected=True)
    if services is None:
        services = (
            [service(NUS_SERVICE, char(NUS_WRITE, ["write"]), char(NUS_NOTIFY, ["notify"]))]
            if model in ("P3", "P4")
            else [
                service(FFE_WRITE_SERVICE, char(FFE_WRITE, ["write"])),
                service(FFE_NOTIFY_SERVICE, char(FFE_NOTIFY, ["notify"])),
            ]
        )
    c.client.services = services
    c.client.start_notify = AsyncMock()
    c.client.stop_notify = AsyncMock()
    c.client.write_gatt_char = AsyncMock()
    controller = AdjustaMattressController(
        c, protocol_variant="auto" if automatic else f"{model}_L{layout}", device_name=name
    )
    c.controller = c.capability_controller = controller
    return controller


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("layout", range(7))
async def test_all_28_profile_gates_roles_and_native_entities(model, layout):
    c = make_controller(model, layout)
    await c.async_discover_capabilities()
    assert set(c.position_actions) == set(BASE_ACTIONS + LAYOUT_ACTIONS[layout])
    assert c.control_characteristic_uuid == (NUS_WRITE if model in ("P3", "P4") else FFE_WRITE)
    keys = {s.key for s in c.controller_select_specs}
    assert ("adjustamattress_head_selector" in keys) == dedicated_massage(model, layout)
    assert ("adjustamattress_snore_control" in keys) == has_snore(model, layout)
    assert ("underbedLighting" in c.held_control_options) == (
        layout not in (2, 4) and model != "P2"
    )
    assert not c.supports_position_feedback
    assert not c.supports_single_address_pairing
    assert not c.supports_memory_programming
    assert {s.key for s in c.motor_control_specs} >= {"back", "legs"}
    assert ("m1" in c.held_control_options) == (layout == 0)
    assert not (set(c.held_control_options) & set(DEDICATED))


@pytest.mark.parametrize(
    "name,scan,model,reconnect_model",
    [
        ("Smartbed-1", True, "P3", "P3"),
        ("smartbed-1", True, "P1", "P1"),
        ("OKIN-1", True, "P1", "P1"),
        ("SLEEP_V1", True, "P4", "P4"),
        ("sleep_v1", False, "P1", "P1"),
        ("SleepBT-1", False, "P1", "P4"),
        ("", False, "P1", "P1"),
    ],
)
def test_name_constructor_is_separate_from_admission(name, scan, model, reconnect_model):
    assert scan_admits(name) is scan
    assert model_from_name(name, reconnect=False) == model
    assert model_from_name(name) == reconnect_model


async def test_auto_gatt_fff0_refines_only_non_nus_model():
    c = make_controller("P1", automatic=True, name="okin-one")
    c.client.services.append(service(FFF0))
    await c.async_discover_capabilities()
    assert c.model == "P2"
    for name, expected in (("Smartbed-one", "P3"), ("SLEEP_V1", "P4")):
        c = make_controller(expected, automatic=True, name=name)
        c.client.services.append(service(FFF0))
        await c.async_discover_capabilities()
        assert c.model == expected


async def test_same_uuid_under_wrong_service_or_without_write_is_rejected():
    c = make_controller(
        services=[service("wrong", char(FFE_WRITE, ["write"]), char(FFE_NOTIFY, ["notify"]))]
    )
    with pytest.raises(ConnectionError):
        await c.async_discover_capabilities()
    c = make_controller(
        services=[
            service(FFE_WRITE_SERVICE, char(FFE_WRITE, ["write-without-response"])),
            service(FFE_NOTIFY_SERVICE, char(FFE_NOTIFY, ["notify"])),
        ]
    )
    with pytest.raises(ConnectionError):
        await c.async_discover_capabilities()


async def test_factory_profile_registration(hass):
    c = make_controller("P4", 0)._coordinator
    c.hass = hass
    controller = await create_controller(
        c, BED_TYPE_ADJUSTAMATTRESS, protocol_variant="P4_L0", client=c.client
    )
    assert isinstance(controller, AdjustaMattressController)
    assert get_variants_for_bed_type(BED_TYPE_ADJUSTAMATTRESS) == ADJUSTAMATTRESS_VARIANTS
    assert len(ADJUSTAMATTRESS_VARIANTS) == 29


async def ready(model="P3", layout=0):
    c = make_controller(model, layout)
    await c.async_discover_capabilities()
    return c


@pytest.mark.parametrize("model", MODELS)
async def test_hold_timing_with_response_and_uncancelled_stop(model):
    c = await ready(model)
    events = []
    clock = [0.0]

    async def delay(seconds, *, cleanup=False):
        clock[0] += seconds

    async def write(packet, **kwargs):
        events.append((round(clock[0], 3), packet, kwargs))

    with (
        patch.object(c, "_delay", side_effect=delay),
        patch.object(c, "write_command", side_effect=write),
        patch("asyncio.get_running_loop", return_value=SimpleNamespace(time=lambda: clock[0])),
    ):
        await c.hold_control("headUp", 601)
    assert [t for t, _, _ in events] == [0.2, 0.4, 0.6, 0.801]
    assert events[-1][1] == frame(model, "stop")
    assert not events[-1][2]["cancel_event"].is_set()
    await c.write_command(frame(model, "stop"))
    assert c.client.write_gatt_char.call_args.kwargs["response"] is True


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("action", CYCLIC)
async def test_cancelled_hold_releases_and_ordinary_massage_queries(model, action):
    c = await ready(model, 4)  # P2 uses the ordinary page only on L4/L6.
    packets = []

    async def write(packet, **kwargs):
        packets.append(packet)
        if len(packets) == 1:
            c._coordinator.cancel_command.set()

    with (
        patch.object(c, "write_command", side_effect=write),
        patch.object(c, "_delay", new=AsyncMock()),
    ):
        await c.hold_control(action, 1000)
    assert packets == [
        frame(model, action),
        frame(model, "stop"),
        *([b"\x00\xb0"] * 2 if model in ("P3", "P4") else []),
    ]


async def test_task_cancellation_finishes_stop_before_return():
    c = await ready()
    c.write_command = AsyncMock()
    task = asyncio.create_task(c.hold_control("headUp", 2000))
    await asyncio.sleep(0)
    task.cancel()
    with patch.object(c, "_delay", new=AsyncMock()), pytest.raises(asyncio.CancelledError):
        await task
    assert c.write_command.call_args.args[0] == frame("P3", "stop")
    assert not c.write_command.call_args.kwargs["cancel_event"].is_set()


async def test_invalid_or_unsafe_action_never_writes():
    c = await ready("P2", 1)
    c.write_command = AsyncMock()
    for action in ("underbedLighting", "lumbarUp", "sleep", "query_status", "query_massage"):
        with pytest.raises(ValueError):
            await c.execute_action(action)
    c.write_command.assert_not_awaited()


@pytest.mark.parametrize("sleeping", (False, True))
@pytest.mark.parametrize("enabled", (False, True))
@pytest.mark.parametrize("demo", (False, True))
@pytest.mark.parametrize("strength", (0, 1, 2, 3))
async def test_all_32_p4_sleep_states(sleeping, enabled, demo, strength):
    c = await ready("P4")
    c.state.sleeping, c.state.snore_enabled = sleeping, enabled
    c.state.demonstration, c.state.strength_index = demo, strength
    clock = [0.0]
    events = []

    async def delay(seconds, *, cleanup=False):
        clock[0] += seconds

    async def write(packet, **kwargs):
        events.append((round(clock[0], 3), packet))

    with (
        patch.object(c, "_delay", side_effect=delay),
        patch.object(c, "write_command", side_effect=write),
        patch.object(c, "_refresh_sleep_state", new=AsyncMock()),
        patch("asyncio.get_running_loop", return_value=SimpleNamespace(time=lambda: clock[0])),
    ):
        await c.execute_action("sleep")
    prelude = not sleeping and not enabled
    expected = []
    if prelude:
        expected.append((0.0, bytes((5, 11, 2 if demo else 1, 3, 1, 35, 0))))
    expected += [(0.2 if prelude else 0.0, bytes((1, 181, int(not sleeping)))), (0.5, b"\x00\xb0")]
    assert events == expected
    assert c.state.sleeping == sleeping  # Wait for a notification, never guess success.
    assert c.state.demonstration == demo


async def test_alarm_commit_and_drafts_and_privacy_are_separate():
    c = await ready("P4")
    c.write_command = AsyncMock()
    with patch.object(c, "_delay", new=AsyncMock()):
        await c.set_number("alarm_draft_hour", 7.0)
        await c.set_number("alarm_draft_minute", 30.0)
        c.local_setting("alarm_draft_type", "17")
        c.write_command.assert_not_awaited()
        await c.set_setting("alarm_commit", "on")
    assert c.write_command.call_args_list[0].args[0] == bytes((8, 5, 255, 5, 7, 30, 0, 1, 0, 0))
    assert c.write_command.call_args_list[-1].args[0] == b"\x00\xc0"
    with pytest.raises(ValueError, match="privacy"):
        await c.set_setting("snore_control", "on")
    c.local_setting("privacy", "accepted")
    c.local_setting("strength_setting", "2")
    await c.set_setting("snore_control", "on")
    assert c.write_command.call_args.args[0] == bytes((5, 11, 1, 6, 1, 35, 0))
    assert c.persisted_app_state == {"privacy": True}


async def test_p2_alarm_disable_sentinel_and_selectors():
    c = await ready("P2")
    c.write_command = AsyncMock()
    with patch.object(c, "_delay", new=AsyncMock()):
        await c.set_setting("alarm_commit", "off")
    assert c.write_command.call_args_list[0].args[0][6:8] == b"\xff\xff"
    assert c.write_command.call_args_list[0].args[0][9:13] == b"\xff" * 4
    for zone in ("head", "foot", "wave"):
        spec = next(
            s for s in c.controller_select_specs if s.key == f"adjustamattress_{zone}_selector"
        )
        for i in range(4):
            await spec.select_fn(c, str(i))
        assert c.client.start_notify.await_count == 0


async def test_notification_busy_timer_is_cancelled_on_disconnect():
    c = await ready("P4")
    c._notification(None, bytearray((166, 64)))
    assert c.state.busy
    handle = c._busy_timer
    c.on_disconnect()
    assert handle.cancelled()
    assert not c.state.busy
    assert c._write_char is None


@pytest.mark.parametrize("model", MODELS)
async def test_session_hydration_and_subscription_retry_are_bounded(model):
    from bleak.exc import BleakError

    c = await ready(model)
    c.write_command = AsyncMock()
    if model in ("P1", "P2"):
        c.client.start_notify.side_effect = [BleakError("temporary"), None]
    with patch.object(c, "_delay", new=AsyncMock()):
        await c.start_notify()
        await c.start_notify()
    assert c.client.start_notify.await_count == (2 if model in ("P1", "P2") else 1)
    packets = [call.args[0] for call in c.write_command.call_args_list]
    assert len(packets) == (1 if model == "P2" else 2)
    assert packets[-1][:2] == (
        b"\xe2\x80" if model == "P1" else b"\xe2\xfe" if model == "P2" else b"\x00\xc0"
    )
    await c.stop_notify()
    assert c.client.stop_notify.await_count == 1


async def test_failed_nus_subscription_does_not_send_hydration():
    from bleak.exc import BleakError

    c = await ready("P4")
    c.client.start_notify.side_effect = BleakError("no CCCD")
    c.write_command = AsyncMock()
    with pytest.raises(BleakError):
        await c.start_notify()
    assert c.client.start_notify.await_count == 1
    c.write_command.assert_not_awaited()


async def test_declared_entity_actions_revalidate_current_profile_and_serialize(hass):
    from custom_components.adjustable_bed.number import AdjustableBedControllerNumber
    from custom_components.adjustable_bed.select import AdjustableBedControllerSelect
    from tests.test_controller_custom_entities import runtime_for

    c = await ready("P2", 1)
    c.write_command = AsyncMock()
    runtime = runtime_for(hass, c)
    select = AdjustableBedControllerSelect(
        runtime,
        next(s for s in c.controller_select_specs if s.key == "adjustamattress_head_selector"),
    )
    await select.async_select_option("2")
    assert c.write_command.call_args.args[0] == bytes.fromhex("e5fe1610000012e4")
    runtime.async_execute_controller_command.assert_awaited_once()
    c.write_command.reset_mock()
    number = AdjustableBedControllerNumber(runtime, c.controller_number_specs[0])
    await number.async_set_native_value(8)
    assert c._preferences.alarm_hour == 8
    c.write_command.assert_not_awaited()
    c.layout = 4
    from homeassistant.exceptions import ServiceValidationError

    with pytest.raises(ServiceValidationError):
        await select.async_select_option("2")


async def test_disabled_only_demonstration_and_persisted_privacy():
    c = await ready("P4")
    c.write_command = AsyncMock()
    with pytest.raises(ValueError):
        await c.execute_action("demonstration")
    c.state.snore_enabled = False
    await c.execute_action("demonstration")
    assert c.write_command.call_args.args[0] == bytes.fromhex("050b0201012300")
    c.restore_persisted_app_state({"privacy": True})
    assert c.persisted_app_state == {"privacy": True}
    with pytest.raises(ValueError):
        c.restore_persisted_app_state({"privacy": "true"})


async def test_first_use_restore_and_reconnect_keep_local_choices(hass):
    from pytest_homeassistant.common import MockConfigEntry

    from custom_components.adjustable_bed.const import DOMAIN
    from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "address": "AA:BB:CC:DD:EE:FF",
            "name": "AdjustaMattress",
            "bed_type": BED_TYPE_ADJUSTAMATTRESS,
            "protocol_variant": "P4_L0",
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    old = AdjustaMattressController(coordinator, protocol_variant="P4_L0")
    coordinator._controller = old
    await coordinator._async_restore_app_state(old)
    assert old.persisted_app_state == {"privacy": False}
    saved = {s.key: s for s in old.controller_select_specs}
    privacy = saved["adjustamattress_privacy"].local_select_fn
    alarm_type = saved["adjustamattress_alarm_draft_type"].local_select_fn
    strength = saved["adjustamattress_strength_setting"].local_select_fn
    assert privacy is not None and alarm_type is not None and strength is not None
    privacy("accepted")
    await old.set_number("alarm_draft_hour", 8)
    await old.set_number("alarm_draft_minute", 30)
    old.on_disconnect()
    live = AdjustaMattressController(coordinator, protocol_variant="P4_L0")
    coordinator._controller = live
    await coordinator._async_restore_app_state(live)
    alarm_type("17")
    strength("2")
    assert live._preferences is old._preferences
    assert (live._preferences.alarm_hour, live._preferences.alarm_minute) == (8, 30)
    assert live._preferences.alarm_type == 17
    assert live.persisted_app_state == {"privacy": True}
    live.state.alarm_on = True
    with pytest.raises(ValueError, match="Turn off"):
        alarm_type("9")
    live.state.alarm_on = False
    # Hydration must not erase draft edits that predate reconnect.
    live._notification(None, bytearray((165, 12, 0, 0, 0, 6, 6, 15, 0, 0)))
    assert (live._preferences.alarm_hour, live._preferences.alarm_minute) == (8, 30)
    status = bytearray((165, 11, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 0, 1, 0, 0, 0))
    live._notification(None, status)
    live.write_command = AsyncMock()
    await live.set_setting("snore_control", "on")
    assert live.write_command.call_args.args[0] == bytes.fromhex("050b0106012300")
    other = AdjustaMattressController(coordinator, protocol_variant="P4_L3")
    coordinator._controller = other
    with pytest.raises(ValueError, match="profile has changed"):
        privacy("not_accepted")


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("layout", range(7))
def test_card_hold_duration_and_metadata_have_one_timing_owner(model, layout):
    c = make_controller(model, layout)
    for spec in c.motor_control_specs:
        assert spec.hold.start_delay_ms == spec.hold.release_delay_ms == 0
        c.validate_hold_control(spec.hold.up_control, 60000)
    for spec in c.controller_button_specs:
        if spec.hold is not None:
            assert spec.hold.start_delay_ms == spec.hold.release_delay_ms == 0
            c.validate_hold_control(spec.hold.control, 60000)
    with pytest.raises(ValueError):
        c.validate_hold_control("headUp", 60001)


@pytest.mark.parametrize(
    "action,duration,expected",
    [
        ("headUp", 1200, (0.2, 0.4, 0.6, 0.8, 1.0, 1.4)),
        ("headStrengthAdd", 1000, (0.0, 0.2, 0.4, 0.6, 0.8, 1.2, 1.4, 1.6)),
    ],
)
async def test_write_latency_does_not_extend_refresh_or_release_schedule(
    action, duration, expected
):
    c = await ready("P4")
    clock = [0.0]
    events = []

    async def delay(seconds, *, cleanup=False):
        clock[0] += seconds

    async def write(packet, **kwargs):
        events.append((round(clock[0], 3), packet))
        clock[0] += 0.1

    with (
        patch.object(c, "_delay", side_effect=delay),
        patch.object(c, "write_command", side_effect=write),
        patch("asyncio.get_running_loop", return_value=SimpleNamespace(time=lambda: clock[0])),
    ):
        await c.hold_control(action, duration)
    assert tuple(t for t, _ in events) == expected
    assert events[-1][1] == (frame("P4", "stop") if action == "headUp" else b"\x00\xb0")


async def test_card_sixty_second_request_reaches_controller_through_registered_service(hass):
    from custom_components.adjustable_bed.const import DOMAIN, SIDE_BOTH
    from custom_components.adjustable_bed.services import async_register_services
    from tests.test_generic_services import target

    controller = await ready("P4")
    coordinator, _ = target(bed_type=BED_TYPE_ADJUSTAMATTRESS)
    coordinator.capability_controller = controller

    async def execute(command, **kwargs):
        await command(controller)

    coordinator.async_execute_controller_command.side_effect = execute
    writes = []

    async def write(packet, **kwargs):
        writes.append(packet)
        controller._coordinator.cancel_command.set()

    await async_register_services(hass)
    with (
        patch(
            "custom_components.adjustable_bed.services._resolve_sided_targets",
            return_value=([(coordinator, SIDE_BOTH)], []),
        ),
        patch.object(controller, "write_command", side_effect=write),
        patch.object(controller, "_delay", new=AsyncMock()),
    ):
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {
                "device_id": ["bed"],
                "control": "headStrengthAdd",
                "duration": 60,
            },
            blocking=True,
        )
    assert writes == [frame("P4", "headStrengthAdd"), frame("P4", "stop"), b"\x00\xb0", b"\x00\xb0"]


async def test_strength_edit_during_awaited_write_survives_older_reply():
    c = await ready("P4")
    c.local_setting("strength_setting", "1")
    started, complete = asyncio.Event(), asyncio.Event()
    packets = []

    async def write(packet, **kwargs):
        packets.append(packet)
        started.set()
        await complete.wait()

    with patch.object(c, "write_command", side_effect=write):
        task = asyncio.create_task(c._send_snore())
        await started.wait()
        c.local_setting("strength_setting", "2")
        complete.set()
        await task
    assert packets == [bytes.fromhex("050b0103012300")]
    assert c._preferences.strength_edited
    status = bytearray((165, 11, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 1, 3, 0, 0, 0))
    c._notification(None, status)
    assert c.state.strength_index == 1
    assert c._preferences.strength_index == 2


@pytest.mark.parametrize("model", ("P2", "P4"))
@pytest.mark.parametrize("commit", ("on", "off"))
async def test_alarm_edit_during_awaited_write_stays_uncommitted(model, commit):
    c = await ready(model)
    c.local_setting("alarm_draft_type", "17")
    started, complete = asyncio.Event(), asyncio.Event()
    packets = []

    async def write(packet, **kwargs):
        packets.append(packet)
        started.set()
        await complete.wait()

    with (
        patch.object(c, "write_command", side_effect=write),
        patch.object(c, "_delay", new=AsyncMock()),
    ):
        task = asyncio.create_task(c.set_setting("alarm_commit", commit))
        await started.wait()
        c.local_setting("alarm_draft_type", "9")
        complete.set()
        await task
    assert c._preferences.alarm_edited
    assert c._preferences.alarm_type == 9
    if model == "P4":
        c._notification(None, bytearray((165, 12, 0, 0, 255, 5, 7, 30, 0, 1)))
        assert c.state.alarm_type == 17
        assert c._preferences.alarm_type == 9


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("layout", range(7))
def test_native_translation_keys_are_valid_and_have_english_names(model, layout):
    c = make_controller(model, layout)
    english = json.loads(
        (Path(__file__).parents[1] / "custom_components/adjustable_bed/strings.json").read_text()
    )["entity"]
    for domain, specs in (
        ("button", c.controller_button_specs),
        ("select", c.controller_select_specs),
        ("number", c.controller_number_specs),
        ("sensor", c.controller_state_sensor_specs),
        ("binary_sensor", c.controller_state_binary_sensor_specs),
    ):
        for spec in specs:
            assert isinstance(spec.translation_key, str)
            assert re.fullmatch(r"[a-z0-9][a-z0-9_-]*[a-z0-9]", spec.translation_key)
            assert english[domain][spec.translation_key]["name"]


@pytest.mark.parametrize("sleeping", (False, True))
@pytest.mark.parametrize("enabled", (False, True))
async def test_sleep_toggle_uses_fresh_report_instead_of_reconnect_defaults(sleeping, enabled):
    c = await ready("P4")
    c.state.sleeping = not sleeping
    c.state.snore_enabled = not enabled
    packets = []
    status = bytearray(
        (
            165,
            11,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            3,
            int(enabled),
            1,
            0,
            0,
            4 if sleeping else 0,
        )
    )

    async def write(packet, **kwargs):
        packets.append(packet)
        if len(packets) == 1:
            assert packet == b"\x00\xb0"
            c._notification(None, status)

    with (
        patch.object(c, "write_command", side_effect=write),
        patch.object(c, "_delay", new=AsyncMock()),
    ):
        await c.execute_action("sleep")
    expected = [b"\x00\xb0"]
    if not sleeping and not enabled:
        expected.append(bytes.fromhex("050b0103012300"))
    expected += [bytes((1, 181, int(not sleeping))), b"\x00\xb0"]
    assert packets == expected


async def test_sleep_status_timeout_cannot_reuse_earlier_reply_or_send_toggle():
    c = await ready("P4")
    c._notification(
        None, bytearray((165, 11, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 1, 1, 0, 0, 4))
    )
    assert c._sleep_status.is_set()
    c.write_command = AsyncMock()
    with (
        patch("custom_components.adjustable_bed.beds.adjustamattress.STATUS_TIMEOUT_S", 0),
        pytest.raises(ConnectionError, match="No fresh sleep status"),
    ):
        await c.execute_action("sleep")
    assert [call.args[0] for call in c.write_command.call_args_list] == [b"\x00\xb0"]


async def test_cancelled_sleep_status_wait_sends_no_toggle():
    c = await ready("P4")
    requested = asyncio.Event()

    async def write(packet, **kwargs):
        assert packet == b"\x00\xb0"
        requested.set()

    with patch.object(c, "write_command", side_effect=write):
        task = asyncio.create_task(c.execute_action("sleep"))
        await requested.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
