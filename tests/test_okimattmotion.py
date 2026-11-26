"""Replay row 137's literals through the codec and the exposed controls."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bleak.exc import BleakError
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.alarm import AlarmRequest
from custom_components.adjustable_bed.beds.okimattmotion import OkimattMotionController
from custom_components.adjustable_bed.command_scheduler import (
    CommandContext,
    CommandIntent,
    Delivery,
    DeviceCommandScheduler,
    current_command_context,
    delivered,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_OKIMATTMOTION,
    CONF_BED_TYPE,
    CONF_CONNECTION_MODE,
    CONF_PAIR_ID,
    CONF_PRODUCT_TYPE,
    DOMAIN,
    PAIR_CONNECTION_MODE_SEQUENTIAL,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import AdjustableBedCover, _build_cover_description
from custom_components.adjustable_bed.detection import BED_TYPE_DISPLAY_NAMES, detect_bed_type
from custom_components.adjustable_bed.errors import BedCommandFailedError
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.profiles import okimattmotion as app
from custom_components.adjustable_bed.services import async_register_services
from custom_components.adjustable_bed.setup_questions import setup_profile
from custom_components.adjustable_bed.state_keys import (
    MASSAGE_TIMER_MINUTES,
    UNDER_BED_LIGHTS_ON,
    massage_intensity,
)
from tests.alarm_helpers import call_set_alarm
from tests.error_helpers import raises_key
from tests.pair_mode import CONF_PAIR_CONNECTION_MODE
from tests.state_helpers import state_writer
from tests.test_controller_contract import _FactoryCoordinator
from tests.test_detection import _make_service_info

VECTORS = {
    row["id"]: row
    for row in json.loads(
        (Path(__file__).parent / "fixtures/okimattmotion/vectors.json").read_text()
    )
}
NOW = datetime(2026, 11, 26, 12, 34, 56, tzinfo=UTC)


def frame(vector: str) -> bytes:
    return bytes.fromhex(VECTORS[vector]["expected_bytes"])


def profile_frames() -> set[bytes]:
    """Every frame the app profile can build at the frozen example times."""
    words = {app.MANUAL_STOP, app.PRESET_STOP, *app.LIGHT.values(), *app.MASSAGE_TIMERS.values()}
    words.update(word for pair in (*app.MOTORS.values(), *app.PRESETS.values()) for word in pair)
    words.update(
        base + level
        for base in (app.MASSAGE_INTENSITY, app.MASSAGE_WAVE)
        for level in (0, *app.MASSAGE_LEVELS)
    )
    return (
        {app.control_frame(word) for word in words}
        | {
            app.alarm_frame(NOW, time(7, 45), timer, wake)
            for timer in app.SLEEP_TIMERS
            for wake in app.WAKE_MODES
        }
        | {app.alarm_frame(NOW.replace(second=s), None, None, "none") for s in (56, 57)}
    )


@pytest.mark.parametrize("vector", tuple(VECTORS))
def test_frozen_encoder(vector: str) -> None:
    inputs = VECTORS[vector]["inputs"]
    if inputs["encoding"] == "word":
        actual = app.control_frame(int(inputs["word"], 16))
    else:
        target = time(*inputs["target_hm"]) if "target_hm" in inputs else None
        selector = inputs.get("sleep_selector", 255)
        actual = app.alarm_frame(
            datetime(2026, 11, 26, *inputs["now_hms"], tzinfo=UTC),
            target,
            {255: None, 48: 10, 49: 20, 50: 30}[selector],
            "wake_mode_1" if inputs.get("wake_mode_selected") else "none",
        )
    assert actual == frame(vector)


def make_client(properties: tuple[str, ...] = ("write",)) -> tuple[MagicMock, SimpleNamespace]:
    writer = SimpleNamespace(uuid=app.WRITE_CHAR, handle=9, properties=properties)
    service = SimpleNamespace(uuid=app.WRITE_SERVICE, get_characteristic=lambda _: writer)
    client = MagicMock(is_connected=True, services=[service], write_gatt_char=AsyncMock())
    return client, writer


async def make_controller(*, layout: str | None = "30", properties: tuple[str, ...] = ("write",)):
    owner = _FactoryCoordinator()
    if layout is None:
        owner.entry.data.pop(CONF_PRODUCT_TYPE, None)
    else:
        owner.entry.data[CONF_PRODUCT_TYPE] = layout
    owner.motor_pulse_count = 1
    owner.record_command_trace = MagicMock()
    owner.client, writer = make_client(properties)
    state: dict[str, object] = {}
    owner.handle_controller_state_updates = state_writer(state)
    controller = await create_controller(owner, BED_TYPE_OKIMATTMOTION, "auto", owner.client)
    assert isinstance(controller, OkimattMotionController)
    await controller.async_discover_capabilities()
    return controller, owner, writer, state


def writes(client: MagicMock) -> list[bytes]:
    return [call.args[1] for call in client.write_gatt_char.await_args_list]


@pytest.mark.parametrize("name", ["OKIN-123", "ComfortX", "BLE-123"])
def test_setup_remains_explicit(name: str) -> None:
    assert BED_TYPE_DISPLAY_NAMES[BED_TYPE_OKIMATTMOTION] == "OkimattMotion app"
    profile = setup_profile(BED_TYPE_OKIMATTMOTION)
    assert profile is not None and profile.questions[0].key == CONF_PRODUCT_TYPE
    assert (
        detect_bed_type(_make_service_info(name=name, service_uuids=[app.WRITE_SERVICE]))
        != BED_TYPE_OKIMATTMOTION
    )


@pytest.mark.parametrize(
    ("layout", "axes"),
    [
        ("20", ("back", "legs")),
        ("30", ("back", "legs", "both")),
        ("40", ("back", "legs", "both")),
        (None, ("back", "legs", "both")),
    ],
)
async def test_layouts_expose_only_the_app_directions(
    layout: str | None, axes: tuple[str, ...]
) -> None:
    controller, owner, writer, _ = await make_controller(
        layout=layout,
        properties=("write-without-response",),
    )
    assert tuple(spec.key for spec in controller.motor_control_specs) == axes
    runtime = SimpleNamespace(
        capability_controller=controller,
        entity_side=None,
        device_info={},
        entity_unique_id=lambda key: key,
    )
    if "both" in axes:
        assert controller.motor_control_specs[-1].translation_key == "back_legs"
    assert {
        spec.key: AdjustableBedCover(runtime, _build_cover_description(spec)).extra_state_attributes
        for spec in controller.motor_control_specs
    } == {
        axis: {
            "hold_lease_mode": "stream",
            "hold_lease_motor": axis,
            "held_stop_scope": "side",
        }
        for axis in axes
    }
    assert controller.execution.hold == "stream"
    assert not controller.execution.concurrent
    assert not controller.supports_position_feedback
    assert not controller.supports_single_address_pairing
    owner.client.start_notify.assert_not_called()
    owner.client.write_gatt_char.assert_not_awaited()
    assert any(spec.key == "okimattmotion_book" for spec in controller.controller_button_specs) == (
        len(axes) == 3
    )
    for spec, action in zip(
        controller.motor_control_specs, ("head", "feet", "head_feet"), strict=False
    ):
        assert spec.stop_scope == "side"
        for direction, run in (("up", spec.open_fn), ("down", spec.close_fn)):
            owner.client.write_gatt_char.reset_mock()
            await run(controller)
            assert writes(owner.client) == [
                frame(f"{action}_{direction}"),
                frame("manual_stop"),
                frame("manual_stop"),
            ]
            assert all(
                write.args[0] is writer and write.kwargs["response"] is False
                for write in owner.client.write_gatt_char.await_args_list
            )


@pytest.fixture
async def transport(hass, monkeypatch):
    """Real scheduling and topology with an offline, single-slot BLE transport."""
    children: dict[str, AdjustableBedCoordinator] = {}
    clients: dict[str, MagicMock] = {}
    events: list[tuple[str, str | bytes]] = []
    for side, address in ((SIDE_LEFT, "AA:BB:CC:DD:01:01"), (SIDE_RIGHT, "AA:BB:CC:DD:01:02")):
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_ADDRESS: address,
                CONF_NAME: side,
                CONF_BED_TYPE: BED_TYPE_OKIMATTMOTION,
                CONF_CONNECTION_MODE: "idle",
            },
        )
        entry.add_to_hass(hass)
        child = AdjustableBedCoordinator(hass, entry)
        await child.async_prime_offline_controller()
        assert isinstance(child.capability_controller, OkimattMotionController)
        client, writer = make_client()
        client.is_connected = False
        children[side], clients[side] = child, client

        async def connect(*, target=child, wire=client, which=side, **kwargs):
            if not target.is_connected:
                assert not any(other.is_connected for other in children.values())
                events.append((which, "connect"))
                wire.is_connected = True
                target._client = wire
                target._controller = await create_controller(
                    target,
                    BED_TYPE_OKIMATTMOTION,
                    "auto",
                    wire,
                )
                await target._controller.async_discover_capabilities()
            return True

        async def disconnect(*_args, target=child, wire=client, which=side, **_kwargs):
            assert target.is_connected
            events.append((which, "disconnect"))
            wire.is_connected = False
            target.controller.on_disconnect()
            target._client = target._controller = None
            return True

        async def write(role, payload, *, response, which=side, expected=writer):
            assert role is expected
            assert [name for name, child in children.items() if child.is_connected] == [which]
            events.append((which, bytes(payload)))

        client.write_gatt_char.side_effect = write
        monkeypatch.setattr(child, "async_connect", AsyncMock(side_effect=connect))
        monkeypatch.setattr(child, "async_ensure_connected", AsyncMock(side_effect=connect))
        monkeypatch.setattr(child, "async_disconnect", AsyncMock(side_effect=disconnect))
    await async_register_services(hass)
    try:
        yield children, clients, events
    finally:
        for child in children.values():
            child._cancel_disconnect_timer()
            await child.command_scheduler.async_shutdown()
            if child.is_connected:
                await child.async_disconnect()


async def test_sequential_stop_reopens_the_released_preset_receiver(hass, transport) -> None:
    children, clients, events = transport
    parent = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_PAIR_ID: "okimattmotion-pair",
            CONF_NAME: "Pair",
            CONF_PAIR_CONNECTION_MODE: PAIR_CONNECTION_MODE_SEQUENTIAL,
        },
    )
    parent.add_to_hass(hass)
    pair = PairedBedCoordinator(hass, parent, children)
    assert pair.connection_mode == PAIR_CONNECTION_MODE_SEQUENTIAL
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(pair, SIDE_LEFT)], []),
    ):
        await hass.services.async_call(
            DOMAIN,
            "goto_preset",
            {"device_id": "left", "preset": 2},
            blocking=True,
        )
        assert not children[SIDE_LEFT].is_connected
        assert not children[SIDE_RIGHT].is_connected
        await children[SIDE_RIGHT].async_connect()  # An out-of-band diagnostic link.
        await hass.services.async_call(DOMAIN, "stop_all", {"device_id": "left"}, blocking=True)

    assert events == [
        (SIDE_LEFT, "connect"),
        (SIDE_LEFT, frame("recall_memory_b")),
        (SIDE_LEFT, "disconnect"),
        (SIDE_RIGHT, "connect"),
        (SIDE_RIGHT, "disconnect"),
        (SIDE_LEFT, "connect"),
        (SIDE_LEFT, frame("manual_stop")),
        (SIDE_LEFT, frame("manual_stop")),
        (SIDE_LEFT, frame("preset_stop")),
        (SIDE_LEFT, "disconnect"),
    ]
    clients[SIDE_RIGHT].write_gatt_char.assert_not_awaited()
    assert all(not child.is_connected for child in children.values())


@pytest.mark.parametrize("fail_cleanup", [False, True])
async def test_timed_move_consumes_only_full_manual_cleanup(
    hass, transport, monkeypatch, fail_cleanup
):
    children, clients, _events = transport
    target, client = children[SIDE_LEFT], clients[SIDE_LEFT]
    pacing = SimpleNamespace(**vars(asyncio))
    pacing.sleep = AsyncMock()
    monkeypatch.setattr("custom_components.adjustable_bed.beds.gatt_write.asyncio", pacing)
    base_write = client.write_gatt_char.side_effect
    movement_context: CommandContext | None = None
    releases = 0

    async def write(role, payload, *, response):
        nonlocal movement_context, releases
        await base_write(role, payload, response=response)
        if payload == frame("head_feet_up"):
            movement_context = current_command_context()
        if payload == frame("manual_stop"):
            releases += 1
            if releases == 1 and fail_cleanup:
                raise BleakError("manual cleanup write failed")

    client.write_gatt_char.side_effect = write
    with patch(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        return_value=([(target, SIDE_BOTH)], []),
    ):

        async def timed_move():
            await hass.services.async_call(
                DOMAIN,
                "timed_move",
                {"device_id": "bed", "motor": "both", "direction": "up", "duration_ms": 1000},
                blocking=True,
            )

        if fail_cleanup:
            with pytest.raises(BedCommandFailedError, match="manual cleanup write failed"):
                await timed_move()
        else:
            await timed_move()
        assert movement_context is not None
        assert movement_context.cleanup_stop_sent == (not fail_cleanup)
        sent = writes(client)
        directions = sent[: sent.index(frame("manual_stop"))]
        assert directions and all(payload == frame("head_feet_up") for payload in directions)
        assert sent[len(directions) :] == [frame("manual_stop")] * (4 if fail_cleanup else 2)
        await hass.services.async_call(DOMAIN, "stop_all", {"device_id": "bed"}, blocking=True)

    assert writes(client)[len(sent) :] == [
        frame("manual_stop"),
        frame("manual_stop"),
        frame("preset_stop"),
    ]


async def test_rejects_wrong_service_and_fences_replaced_link() -> None:
    controller, owner, old_writer, _ = await make_controller()
    original = owner.client
    owner.motor_pulse_count = 2
    started = asyncio.Event()

    async def first_write(*_args, **_kwargs):
        started.set()
        await asyncio.Event().wait()

    original.write_gatt_char.side_effect = first_write
    move = asyncio.create_task(controller.move_back_up())
    await asyncio.wait_for(started.wait(), 1)
    owner.client, _ = make_client(("write", "write-without-response"))
    controller.on_disconnect()
    await controller.async_discover_capabilities()
    move.cancel()
    with pytest.raises(asyncio.CancelledError):
        await move
    owner.client.write_gatt_char.assert_not_awaited()
    assert original.write_gatt_char.await_args.args[0] is old_writer

    await controller.lights_on()
    assert owner.client.write_gatt_char.await_args.kwargs == {"response": True}
    owner.client.services[0].uuid = app.NOTIFY_SERVICE
    with pytest.raises(ConnectionError, match="FFE9 under FFE5"):
        await controller.async_discover_capabilities()


async def test_cancelled_movement_attempts_both_releases_even_if_first_fails() -> None:
    controller, owner, _, _ = await make_controller()
    started = asyncio.Event()
    issued: list[bytes] = []

    async def write(_char, payload, **_kwargs):
        issued.append(payload)
        if payload == frame("head_up"):
            started.set()
            await asyncio.Event().wait()
        if len(issued) == 2:
            raise BleakError("first release failed")

    owner.client.write_gatt_char.side_effect = write
    move = asyncio.create_task(controller.move_back_up())
    await asyncio.wait_for(started.wait(), 1)
    owner.cancel_command.set()
    move.cancel()
    with pytest.raises(asyncio.CancelledError):
        await move
    assert issued == [frame("head_up"), frame("manual_stop"), frame("manual_stop")]
    await controller.stop_all()
    assert issued[-3:] == [frame("manual_stop"), frame("manual_stop"), frame("preset_stop")]


async def test_presets_and_saves() -> None:
    controller, owner, _, _ = await make_controller()
    for action in (
        controller.preset_zero_g,
        controller.preset_flat,
        controller.preset_anti_snore,
        lambda: controller.preset_memory(1),
        lambda: controller.preset_memory(2),
        lambda: controller.program_memory(1),
        lambda: controller.program_memory(2),
    ):
        await action()
    for spec in controller.controller_button_specs:
        await spec.press_fn(controller)
    assert writes(owner.client) == [
        frame(key)
        for key in (
            "recall_zero_g",
            "recall_flat",
            "recall_quiet_sleep_or_book",
            "recall_memory_a",
            "recall_memory_b",
            "program_memory_a",
            "program_memory_b",
            "program_zero_g",
            "program_flat",
            "program_quiet_sleep_or_book",
            "recall_quiet_sleep_or_book",
        )
    ]


async def test_light_and_massage_sequences(monkeypatch: pytest.MonkeyPatch) -> None:
    controller, owner, _, state = await make_controller()
    delay = AsyncMock()
    monkeypatch.setattr("custom_components.adjustable_bed.beds.okimattmotion.asyncio.sleep", delay)
    power = controller.controller_switch_specs[0]
    await controller.lights_on()
    await controller.lights_off()
    await controller.set_massage_intensity("wave", 3)
    await controller.set_massage_intensity("all", 2)
    await controller.set_massage_timer(30)
    await power.set_fn(controller, True)
    assert state[MASSAGE_TIMER_MINUTES] == 10
    await power.set_fn(controller, False)
    assert state[MASSAGE_TIMER_MINUTES] is None
    assert state[UNDER_BED_LIGHTS_ON] is False
    assert state[power.key] is False
    assert writes(owner.client) == [
        frame(key)
        for key in (
            "light_on",
            "light_off",
            "massage_intensity_0",
            "massage_wave_3",
            "massage_intensity_2",
            "massage_wave_3",
            "massage_timer_30m",
            "massage_wave_1",
            "massage_intensity_1",
            "massage_timer_10m",
            "massage_wave_0",
            "massage_intensity_0",
        )
    ]
    assert [call.args for call in delay.await_args_list] == [(0.1,), (0.1,)]


@pytest.mark.parametrize("link_replaced", [False, True])
async def test_light_state_requires_a_write_on_the_current_link(link_replaced: bool) -> None:
    controller, owner, _, state = await make_controller()
    await controller.lights_off()
    original = owner.client
    if link_replaced:

        async def replace_link(*_args, **_kwargs):
            controller.on_disconnect()
            owner.client, _ = make_client()
            await controller.async_discover_capabilities()

        original.write_gatt_char.side_effect = replace_link
    else:
        owner.cancel_command.set()

    await controller.lights_on()
    assert state[UNDER_BED_LIGHTS_ON] is False
    assert writes(original) == [frame("light_off")] + ([frame("light_on")] if link_replaced else [])


async def test_massage_level_keeps_the_delivered_part_of_a_pair() -> None:
    controller, owner, _, state = await make_controller()
    await controller.set_massage_intensity("wave", 3)
    owner.client.write_gatt_char.side_effect = [None, BleakError("wave write failed")]

    with pytest.raises(BleakError, match="wave write failed"):
        await controller.set_massage_intensity("all", 2)
    assert state[massage_intensity("all")] == 2
    assert state[massage_intensity("wave")] == 3

    owner.client.write_gatt_char.side_effect = None
    await controller.set_massage_intensity("wave", 1)
    assert writes(owner.client)[-2:] == [frame("massage_intensity_2"), frame("massage_wave_1")]


async def test_cancel_massage_power_does_not_send_delayed_positive_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, owner, _, state = await make_controller()
    power = controller.controller_switch_specs[0]
    scheduler = DeviceCommandScheduler("okimattmotion")
    deliveries: list[Delivery] = []

    async def cancel_during_delay(_seconds):
        owner.cancel_command.set()

    pacing = SimpleNamespace(**vars(asyncio))
    pacing.sleep = cancel_during_delay
    monkeypatch.setattr("custom_components.adjustable_bed.beds.okimattmotion.asyncio", pacing)

    async def enable(context):
        owner.cancel_command = context.cancel_event
        with delivered(deliveries.append):
            await power.set_fn(controller, True)
        assert context.frames_written == 1  # Only the initial positive wave write.

    try:
        operation = await scheduler.enqueue(CommandIntent(enable))
        await operation.future
    finally:
        await scheduler.async_shutdown()

    assert deliveries == [Delivery.PARTIAL]
    assert state[power.key] is False
    assert state[MASSAGE_TIMER_MINUTES] is None
    assert writes(owner.client) == [
        frame(key)
        for key in (
            "massage_wave_1",
            "massage_wave_0",
            "massage_intensity_0",
        )
    ]


async def test_alarm_rebuilds_each_write_and_validates_shared_service(hass, monkeypatch) -> None:
    controller, owner, _, _ = await make_controller()
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.okimattmotion.dt_util.now",
        MagicMock(return_value=NOW),
    )
    await call_set_alarm(
        hass,
        controller,
        {"enabled": True, "time": "07:45:00", "wake_action": "wake_mode_1", "sleep_timer": 20},
        bed_type=BED_TYPE_OKIMATTMOTION,
    )
    await call_set_alarm(
        hass,
        controller,
        {"enabled": True, "time": "07:45:00"},
        bed_type=BED_TYPE_OKIMATTMOTION,
    )
    assert writes(owner.client) == [frame("alarm-set-31-04")] * 2 + [frame("alarm-set-ff-ff")] * 2
    with raises_key("alarm_sleep_timer_not_supported", ServiceValidationError):
        await call_set_alarm(
            hass,
            controller,
            {"enabled": True, "time": "07:45:00", "sleep_timer": 15},
            bed_type=BED_TYPE_OKIMATTMOTION,
        )
    assert len(writes(owner.client)) == 4
    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.okimattmotion.dt_util.now",
        MagicMock(side_effect=[NOW, NOW.replace(second=57)]),
    )
    await controller.configure_alarm(AlarmRequest(enabled=False, reference_time=NOW))
    assert writes(owner.client)[-2:] == [frame("alarm-cancel-s56"), frame("alarm-cancel-s57")]
