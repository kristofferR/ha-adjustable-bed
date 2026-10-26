"""Focused regressions for independently reproduced M1X12 review findings."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.star_elevate import StarElevateCommands
from custom_components.adjustable_bed.beds.starcode_m1x12 import (
    StarcodeM1X12Controller,
    StarElevateM1X12Controller,
)
from custom_components.adjustable_bed.beds.starcode_m1x12_protocol import (
    normal_packet,
    parse_notification,
)
from custom_components.adjustable_bed.button import _combined_motor_buttons_for
from custom_components.adjustable_bed.const import (
    BED_TYPE_STAR_ELEVATE,
    CONF_PAIR_CHILDREN,
    CONF_PAIR_ID,
    CONF_PROTOCOL_VARIANT,
    CONF_STARCODE_LIFT_ENTRIES,
    DOMAIN,
    STAR_ELEVATE_VARIANT_M1X12,
)
from custom_components.adjustable_bed.controller_factory import create_controller
from custom_components.adjustable_bed.light import _light_entities_for
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.pairing_candidates import (
    CONF_PAIR_SELECTION,
    encode_pair_selection,
)
from custom_components.adjustable_bed.sensor import _sensor_entities_for
from custom_components.adjustable_bed.services import async_register_services
from tests.test_starcode_m1x12 import (
    _controller_target,
    _create_controller,
    _GattClient,
)


async def _patch_protocol_sleeps(monkeypatch: pytest.MonkeyPatch) -> None:
    real_sleep = asyncio.sleep

    async def yield_only(_delay: float) -> None:
        await real_sleep(0)

    monkeypatch.setattr(
        "custom_components.adjustable_bed.beds.starcode_m1x12.asyncio.sleep", yield_only
    )


@pytest.mark.parametrize("source_kind", ("main", "elevate"))
async def test_public_hold_interrupts_accessory_peer_and_clears_progress(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    source_kind: str,
) -> None:
    await _patch_protocol_sleeps(monkeypatch)
    main, main_controller = await _create_controller(hass, client=_GattClient())
    main_controller._ready = True
    main_controller.dialect = "star"
    main_controller.queue_position_targets(((0, 140),))
    lift, lift_entry = _controller_target(
        hass,
        bed_type=BED_TYPE_STAR_ELEVATE,
        name="ELEVATE123456",
        variant=STAR_ELEVATE_VARIANT_M1X12,
        client=_GattClient(),
    )
    lift_controller = StarElevateM1X12Controller(lift)
    lift_controller._initialized = True
    lift._controller = lift_controller
    hass.config_entries.async_update_entry(
        main.entry,
        data={**main.entry.data, CONF_STARCODE_LIFT_ENTRIES: [lift_entry.entry_id]},
    )
    for target in (main, lift):
        target.entry.mock_state(hass, ConfigEntryState.LOADED)
        target._ready = True

    source, peer = (main, lift) if source_kind == "main" else (lift, main)
    source_controller = main_controller if source_kind == "main" else lift_controller
    control = "part_1_up" if source_kind == "main" else "both_up"
    movement = normal_packet(0x03103000 if source_kind == "main" else 0x03103044, "star")
    peer_interrupt = normal_packet(0x0310304F if source_kind == "main" else 0x0310301F, "star")
    source_writes: list[bytes] = []
    peer_writes: list[bytes] = []

    async def source_writer(_uuid: Any, data: bytes, *, response: bool = False) -> None:
        del response
        source_writes.append(bytes(data))
        if bytes(data) == movement:
            source.cancel_command.set()

    async def peer_writer(_uuid: Any, data: bytes, *, response: bool = False) -> None:
        del response
        peer_writes.append(bytes(data))

    source.client.write_gatt_char = source_writer  # type: ignore[method-assign]
    peer.client.write_gatt_char = peer_writer  # type: ignore[method-assign]
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=source.entry.entry_id, **source.device_info
    )
    await async_register_services(hass)
    await hass.services.async_call(
        DOMAIN,
        "hold_control",
        {"device_id": [device.id], "control": control, "duration": 0.1},
        blocking=True,
    )

    assert movement in source_writes
    assert peer_interrupt in peer_writes
    if source_kind == "main":
        assert main_controller._progress_queue == []
        assert main_controller._progress_generation >= 2
    assert isinstance(source_controller, (StarcodeM1X12Controller, StarElevateM1X12Controller))


@pytest.mark.parametrize("source_kind", ("main", "elevate"))
async def test_paired_motor_buttons_publish_declared_flat_hold_metadata(
    hass: HomeAssistant,
    source_kind: str,
) -> None:
    if source_kind == "main":
        left, left_controller = await _create_controller(hass, client=_GattClient())
        right, right_controller = await _create_controller(hass, client=_GattClient())
        controllers = (left_controller, right_controller)
        for controller in controllers:
            controller._ready = True
    else:
        left, _ = _controller_target(
            hass,
            bed_type=BED_TYPE_STAR_ELEVATE,
            name="ELEVATE-left",
            variant=STAR_ELEVATE_VARIANT_M1X12,
            client=_GattClient(),
        )
        right, _ = _controller_target(
            hass,
            bed_type=BED_TYPE_STAR_ELEVATE,
            name="ELEVATE-right",
            variant=STAR_ELEVATE_VARIANT_M1X12,
            client=_GattClient(),
        )
        controllers = tuple(
            StarElevateM1X12Controller(coordinator) for coordinator in (left, right)
        )
        for coordinator, controller in zip((left, right), controllers, strict=True):
            controller._initialized = True
            coordinator._controller = controller

    pair_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PAIR_ID: f"review-pair-{source_kind}"},
    )
    pair_entry.add_to_hass(hass)
    pair = PairedBedCoordinator(hass, pair_entry, {"left": left, "right": right})
    buttons = _combined_motor_buttons_for(pair, [left, right])

    assert buttons
    for button in buttons:
        spec = next(
            item for item in controllers[0].motor_control_specs if item.key == button._motor_key
        )
        assert spec.hold is not None
        expected_control = (
            spec.hold.up_control if button._direction == "up" else spec.hold.down_control
        )
        assert button.extra_state_attributes == {
            "held_control": expected_control,
            "hold_start_delay_ms": spec.hold.start_delay_ms,
            "hold_release_delay_ms": spec.hold.release_delay_ms,
        }

    if source_kind == "main":
        assert any(button.translation_key == "starcode_m1x12_part_1_up" for button in buttons)
        assert any(
            button.extra_state_attributes["held_control"] == "part_1_up" for button in buttons
        )
    else:
        assert any(button.translation_key == "elevate_actuator_1_up" for button in buttons)
        assert any(
            button.extra_state_attributes["held_control"] == "actuator_1_up" for button in buttons
        )


@pytest.mark.parametrize("explicit_side", ("left", "right"))
async def test_mixed_elevate_pair_keeps_combined_parent_movement_finite(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    enable_custom_integrations: None,
    explicit_side: str,
) -> None:
    """The wizard-supported mixed profile pair must use its existing finite route."""
    await _patch_protocol_sleeps(monkeypatch)
    sides: dict[str, Any] = {}
    clients: dict[str, _GattClient] = {}
    variants = {
        side: STAR_ELEVATE_VARIANT_M1X12 if side == explicit_side else None
        for side in ("left", "right")
    }
    for side, variant in variants.items():
        client = _GattClient()
        child, _entry = _controller_target(
            hass,
            bed_type=BED_TYPE_STAR_ELEVATE,
            name=f"ELEVATE-{side}",
            variant=variant,
            client=client,
        )
        controller = await create_controller(child, BED_TYPE_STAR_ELEVATE, variant, child.client)
        child._controller = controller
        child._ready = True
        child.entry.mock_state(hass, ConfigEntryState.LOADED)
        sides[side] = child
        clients[side] = client

    flow_result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert flow_result["type"] == "form"
    flow_result = await hass.config_entries.flow.async_configure(
        flow_result["flow_id"], {"address": "pair_beds"}
    )
    assert flow_result["type"] == "form"
    assert flow_result["step_id"] == "pair_beds"
    flow_result = await hass.config_entries.flow.async_configure(
        flow_result["flow_id"],
        {
            CONF_PAIR_SELECTION: encode_pair_selection(
                sides["left"].entry.entry_id,
                sides["right"].entry.entry_id,
            ),
            "name": "Mixed ELEVATE pair",
        },
    )
    assert flow_result["type"] == "create_entry"
    child_descriptors = flow_result["data"][CONF_PAIR_CHILDREN]
    assert [item.get(CONF_PROTOCOL_VARIANT) for item in child_descriptors] == [
        variants["left"],
        variants["right"],
    ]

    pair_entry = MockConfigEntry(domain=DOMAIN, data=flow_result["data"])
    pair_entry.add_to_hass(hass)
    pair_entry.mock_state(hass, ConfigEntryState.LOADED)
    pair = PairedBedCoordinator(hass, pair_entry, sides)
    buttons = _combined_motor_buttons_for(pair, [sides["left"], sides["right"]])
    assert buttons
    assert all(
        not {"held_control", "hold_start_delay_ms", "hold_release_delay_ms"}.intersection(
            button.extra_state_attributes
        )
        for button in buttons
    )

    actuator_up = next(
        button
        for button in buttons
        if button._motor_key == "elevate_actuator_1" and button._direction == "up"
    )
    try:
        await actuator_up.async_press()
        assert all(
            any(event[0] == "write" for event in client.events) for client in clients.values()
        )
        assert all(not child.controller.ble_lock.locked() for child in sides.values())
    finally:
        for child in sides.values():
            child._cancel_disconnect_timer()


@pytest.mark.parametrize(
    ("field", "direction", "expected_hold"),
    (
        ("up_control", "up", False),
        ("up_control", "down", True),
        ("down_control", "up", True),
        ("down_control", "down", False),
        ("start_delay_ms", "up", False),
        ("start_delay_ms", "down", False),
        ("release_delay_ms", "up", False),
        ("release_delay_ms", "down", False),
    ),
)
def test_combined_motor_hold_intersection_checks_direction_and_timing(
    hass: HomeAssistant,
    field: str,
    direction: str,
    expected_hold: bool,
) -> None:
    """Only a direction with matching declared control and timing stays held."""
    from dataclasses import replace

    explicit, _entry = _controller_target(
        hass,
        bed_type=BED_TYPE_STAR_ELEVATE,
        name="ELEVATE-explicit",
        variant=STAR_ELEVATE_VARIANT_M1X12,
        client=_GattClient(),
    )
    controller = StarElevateM1X12Controller(explicit)
    specs = controller.motor_control_specs
    motor = next(spec for spec in specs if spec.key == "elevate_actuator_1")
    assert motor.hold is not None
    hold_value: str | int = getattr(motor.hold, field)
    changed: str | int = f"{hold_value}_other" if isinstance(hold_value, str) else hold_value + 1
    changed_hold = replace(motor.hold, **{field: changed})
    changed_motor = replace(motor, hold=changed_hold)
    other_side_specs = tuple(changed_motor if spec.key == motor.key else spec for spec in specs)

    left = SimpleNamespace(
        capability_controller=SimpleNamespace(
            supports_motor_control=True,
            has_discrete_motor_control=False,
            motor_control_specs=specs,
        )
    )
    right = SimpleNamespace(
        capability_controller=SimpleNamespace(
            supports_motor_control=True,
            has_discrete_motor_control=False,
            motor_control_specs=other_side_specs,
        )
    )
    pair = SimpleNamespace(
        pair_id="pair", device_info={}, children={}, connection_mode="sequential"
    )
    button = next(
        item
        for item in _combined_motor_buttons_for(pair, [left, right])
        if item._motor_key == motor.key and item._direction == direction
    )
    assert ("held_control" in button.extra_state_attributes) is expected_hold


async def test_light_telemetry_getter_updates_actual_light_and_teardown_clears_it(
    hass: HomeAssistant,
) -> None:
    client = _GattClient()
    coordinator, controller = await _create_controller(hass, client=client)
    controller._ready = True
    controller._subscribed = True
    controller._subscription_client = client
    light = _light_entities_for(hass, coordinator)[0]
    light.async_write_ha_state = Mock()
    unregister = coordinator.register_controller_state_callback(
        light._handle_controller_state_update
    )
    payload = bytearray(20)
    payload[:2] = b"\xa5\x0b"
    payload[14] = 1
    controller._apply_notification(bytes(payload))
    assert controller.get_light_state() == {"is_on": True}
    assert light.is_on is True

    controller.query_status = AsyncMock()
    assert await controller.read_light_state() == {"is_on": True}
    controller.query_status.assert_awaited_once()

    controller._next_tick = asyncio.get_running_loop().time()
    await controller.stop_notify()
    assert controller.get_light_state() == {"is_on": None}
    assert light.is_on is None
    assert ("stop_notify", "6e400003-b5a3-f393-e0a9-e50e24dcca9e") in client.events
    unregister()


@pytest.mark.parametrize("profile", ("f23", "kneading"))
def test_advanced_alarm_first_record_uses_accepted_630_time(profile: str) -> None:
    payload = bytearray(25)
    payload[:2] = b"\xa5\x0c"
    payload[3:14] = bytes((127, 0, 1, 4, 99, 3, 2, 6, 30, 0, 1))
    payload[14:25] = bytes((1, 6, 7, 6, 0, 0, 3, 7, 45, 0, 0))
    state = parse_notification(bytes(payload), profile=profile, dialect="legacy")
    assert state["alarm_0_details"]["hour"] == 6  # type: ignore[index]
    assert state["alarm_0_details"]["minute"] == 30  # type: ignore[index]


async def test_cb25_alarm_entities_and_records_are_not_gated_by_outbound_dialect(
    hass: HomeAssistant,
) -> None:
    coordinator, controller = await _create_controller(hass, client=_GattClient())
    controller.dialect = "legacy"
    payload = bytearray(17)
    payload[:2] = b"\xa5\x0c"
    payload[4:10] = bytes((127, 5, 6, 30, 0, 1))
    payload[11:17] = bytes((1, 9, 7, 45, 0, 0))
    controller._apply_notification(bytes(payload))
    assert "alarm_1_details" in coordinator.controller_state
    assert any(spec.state_key == "alarm_1" for spec in controller.controller_state_sensor_specs)
    assert any(
        sensor._spec.state_key == "alarm_1" for sensor in _sensor_entities_for(hass, coordinator)
    )


def test_sonic_state_keeps_mode_and_type_on_their_distinct_accepted_bytes() -> None:
    payload = bytearray(20)
    payload[:2] = b"\xa5\x0b"
    payload[6] = 0x63
    payload[8] = 0
    state = parse_notification(bytes(payload), profile="cb25", dialect="legacy")
    assert state["sonic_mode"] == 6
    assert state["sonic_massage_type"] == 0


async def test_m1x12_elevate_hold_cannot_write_after_owned_session_disconnect(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _patch_protocol_sleeps(monkeypatch)
    old_client = _GattClient()
    source, _entry = _controller_target(
        hass,
        bed_type=BED_TYPE_STAR_ELEVATE,
        name="ELEVATE123456",
        variant=STAR_ELEVATE_VARIANT_M1X12,
        client=old_client,
    )
    old_controller = StarElevateM1X12Controller(source)
    old_controller._initialized = True
    source._controller = old_controller
    source.entry.mock_state(hass, ConfigEntryState.LOADED)
    source._ready = True
    entered = asyncio.Event()
    monkeypatch.setattr(source, "record_command_trace", lambda **_kwargs: entered.set())
    await old_controller.ble_lock.acquire()
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=source.entry.entry_id, **source.device_info
    )
    await async_register_services(hass)
    service = asyncio.create_task(
        hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": [device.id], "control": "both_up", "duration": 0.1},
            blocking=True,
        )
    )
    await asyncio.wait_for(entered.wait(), 1)

    old_client.is_connected = False
    generation = old_controller.session_generation
    source._on_disconnect(old_client)
    assert old_controller.session_generation > generation
    source._cancel_auto_reconnect()
    replacement = _GattClient()
    replacement_writes: list[bytes] = []

    async def replacement_writer(_uuid: Any, data: bytes, *, response: bool = False) -> None:
        del response
        replacement_writes.append(bytes(data))

    replacement.write_gatt_char = replacement_writer  # type: ignore[method-assign]
    source._client = replacement
    replacement_controller = StarElevateM1X12Controller(source)
    replacement_controller._initialized = True
    source._controller = replacement_controller
    old_controller.ble_lock.release()
    await service

    assert replacement_writes == []
    assert not any(event[0] == "write" for event in old_client.events)


async def test_m1x12_elevate_hold_skips_sender_ticks_elapsed_during_slow_write(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from custom_components.adjustable_bed.beds import starcode_m1x12 as module

    source, _entry = _controller_target(
        hass,
        bed_type=BED_TYPE_STAR_ELEVATE,
        name="ELEVATE123456",
        variant=STAR_ELEVATE_VARIANT_M1X12,
        client=_GattClient(),
    )
    controller = StarElevateM1X12Controller(source)
    controller._initialized = True
    source._controller = controller
    clock = SimpleNamespace(now=0.0)
    starts: list[float] = []

    async def advance(delay: float) -> None:
        clock.now += delay

    async def slow_write(_uuid: Any, data: bytes, *, response: bool = False) -> None:
        del response
        if bytes(data) == StarElevateCommands.BOTH_UP:
            starts.append(clock.now)
            clock.now += 0.25 if len(starts) == 1 else 0.01
            if len(starts) == 3:
                source.cancel_command.set()

    source.client.write_gatt_char = slow_write  # type: ignore[method-assign]
    monkeypatch.setattr(
        module,
        "asyncio",
        SimpleNamespace(
            get_running_loop=lambda: SimpleNamespace(time=lambda: clock.now),
            sleep=advance,
            Event=asyncio.Event,
            CancelledError=asyncio.CancelledError,
        ),
    )
    await controller.hold_control("both_up", 1000)
    assert starts == pytest.approx([0.1, 0.4, 0.5])
