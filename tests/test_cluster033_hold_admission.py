"""Registered cluster033 holds use the approved scheduler STOP-epoch seam.

Temporal cases adapt the immutable shared-admission regressions. These use real
HA service/device routing and coordinators; no M1X12 protocol code is imported.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.adjustable_bed.beds.cluster033 import AppController
from custom_components.adjustable_bed.cluster033_profiles import app_profile
from custom_components.adjustable_bed.const import CONF_BED_TYPE, CONF_PAIR_ID, DOMAIN
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.paired_coordinator import PairedBedCoordinator
from custom_components.adjustable_bed.paired_devices import child_device_info
from custom_components.adjustable_bed.services import async_register_services

from .test_cluster033 import coordinator as mock_transport


async def _target(hass: HomeAssistant, *, mx: bool = False):
    sequence = len(hass.data.setdefault("cluster033_test_targets", [])) + 1
    address = f"AA:33:00:00:00:{sequence:02X}"
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=f"App {sequence}",
        unique_id=address,
        data={
            CONF_ADDRESS: address,
            CONF_NAME: f"App {sequence}",
            CONF_BED_TYPE: "qplus_app" if mx else "tempur_curve",
        },
    )
    entry.add_to_hass(hass)
    target = AdjustableBedCoordinator(hass, entry)
    client = mock_transport().client
    client.disconnect = AsyncMock()
    controller = AppController(
        target, app_profile("qplus_app" if mx else "tempur_curve", "MX" if mx else None)
    )
    # Bind a synthetic current GATT session; real radio/setup is outside tests.
    target._client = client
    controller._wait = AsyncMock(return_value=False)
    await controller.start_notify()
    client.write_gatt_char.reset_mock()
    target._client = target._controller = target._offline_controller = None
    target._ready = True
    entry.mock_state(hass, ConfigEntryState.LOADED)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = target
    hass.data["cluster033_test_targets"].append(target)
    return target, controller, client


@pytest.fixture(autouse=True)
async def _cleanup_targets(hass):
    yield
    for target in hass.data.get("cluster033_test_targets", []):
        await target.async_shutdown()


async def _connected_pair(hass, monkeypatch):
    triples = {}
    for side in ("left", "right"):
        child, controller, client = await _target(hass)
        child._client, child._controller = client, controller
        monkeypatch.setattr(child, "async_ensure_connected", AsyncMock(return_value=True))
        monkeypatch.setattr(controller, "stop_all", AsyncMock())
        triples[side] = child, controller, client
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_PAIR_ID: "cluster033-admission"})
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    pair = PairedBedCoordinator(hass, entry, {side: triple[0] for side, triple in triples.items()})
    hass.data[DOMAIN][entry.entry_id] = pair
    registry = dr.async_get(hass)
    parent = registry.async_get_or_create(config_entry_id=entry.entry_id, **pair.device_info)
    children = {
        side: registry.async_get_or_create_child(
            config_entry_id=entry.entry_id, **child_device_info(pair, side)
        )
        for side in triples
    }
    await async_register_services(hass)
    return pair, parent, children, triples


async def test_stop_invalidates_hold_waiting_for_scheduler_admission(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scheduler closes the check/enqueue race before replacement logic."""
    coordinator, controller, _client = await _target(hass)
    coordinator._client = _client
    coordinator._controller = controller
    scheduler = coordinator._command_scheduler
    old_handle_created = asyncio.Event()
    new_handle_created = asyncio.Event()
    handles = 0
    original_new_handle = scheduler._new_handle

    def track_command_handle(intent, *args, **kwargs):
        nonlocal handles
        handle = original_new_handle(intent, *args, **kwargs)
        if intent.kind.value == "command":
            handles += 1
            if handles == 1:
                old_handle_created.set()
            elif handles == 2:
                new_handle_created.set()
        return handle

    monkeypatch.setattr(scheduler, "_new_handle", track_command_handle)
    held: list[str] = []
    hold_started = asyncio.Event()
    finish_hold = asyncio.Event()

    async def hold_control(control: str, _duration_ms: int) -> None:
        held.append(control)
        hold_started.set()
        await finish_hold.wait()

    monkeypatch.setattr(controller, "hold_control", hold_control)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=coordinator.entry.entry_id, **coordinator.device_info
    )
    await async_register_services(hass)

    await scheduler._lock.acquire()
    old_hold = asyncio.create_task(
        hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": [device.id], "control": "head_up", "duration": 60},
            blocking=True,
        )
    )
    await old_handle_created.wait()

    await hass.services.async_call(DOMAIN, "stop_all", {"device_id": [device.id]}, blocking=True)
    new_hold = asyncio.create_task(
        hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": [device.id], "control": "head_up", "duration": 0.1},
            blocking=True,
        )
    )
    await new_handle_created.wait()
    scheduler._lock.release()

    await old_hold
    await hold_started.wait()
    assert held == ["head_up"]
    assert not new_hold.done()

    finish_hold.set()
    await new_hold


@pytest.mark.parametrize("cancel_caller", (False, True))
async def test_hold_preflight_failure_or_cancellation_never_admits(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    cancel_caller: bool,
) -> None:
    coordinator, controller, _client = await _target(hass)
    preflight_started = asyncio.Event()
    resume_preflight = asyncio.Event()

    async def ensure_connected(*, reset_timer: bool = True) -> bool:
        del reset_timer
        preflight_started.set()
        if cancel_caller:
            await resume_preflight.wait()
            return True
        return False

    monkeypatch.setattr(coordinator, "async_ensure_connected", ensure_connected)
    held: list[str] = []

    async def hold_control(control: str, _duration_ms: int) -> None:
        held.append(control)

    monkeypatch.setattr(controller, "hold_control", hold_control)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=coordinator.entry.entry_id, **coordinator.device_info
    )
    await async_register_services(hass)
    service = asyncio.create_task(
        hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": [device.id], "control": "head_up", "duration": 60},
            blocking=True,
        )
    )
    await preflight_started.wait()

    if cancel_caller:
        service.cancel()
        with pytest.raises(asyncio.CancelledError):
            await service
        resume_preflight.set()
    else:
        with pytest.raises(ServiceValidationError, match="unable to connect"):
            await service

    assert held == []
    assert not coordinator._command_scheduler.has_pending


@pytest.mark.parametrize("released_side", ("left", "right"))
async def test_paired_side_stop_during_hold_preflight_drops_only_stale_side(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    released_side: str,
) -> None:
    """The paired STOP generation gates only the requested physical side."""
    left, left_controller, left_client = await _target(hass)
    right, right_controller, _right_client = await _target(hass)
    children = {"left": left, "right": right}
    controllers = {"left": left_controller, "right": right_controller}
    clients = {"left": left_client, "right": _right_client}
    preflight_started = asyncio.Event()
    resume_preflight = asyncio.Event()
    ensure_calls = 0

    async def ensure_connected(*, reset_timer: bool = True) -> bool:
        nonlocal ensure_calls
        del reset_timer
        ensure_calls += 1
        if ensure_calls == 1:
            preflight_started.set()
            await resume_preflight.wait()
        child = children[released_side]
        child._client = clients[released_side]
        child._controller = controllers[released_side]
        return True

    monkeypatch.setattr(children[released_side], "async_ensure_connected", ensure_connected)
    held: list[str] = []

    async def hold_control(control: str, _duration_ms: int) -> None:
        held.append(control)

    for controller in controllers.values():
        monkeypatch.setattr(controller, "hold_control", hold_control)

    pair_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_PAIR_ID: f"pending-admission-{released_side}"},
    )
    pair_entry.add_to_hass(hass)
    pair_entry.mock_state(hass, ConfigEntryState.LOADED)
    pair = PairedBedCoordinator(hass, pair_entry, children)
    await async_register_services(hass)
    monkeypatch.setattr(
        "custom_components.adjustable_bed.services._resolve_sided_targets",
        lambda *_args: ([(pair, released_side)], []),
    )
    call = {"device_id": ["paired-bed"], "control": "head_up", "duration": 60}
    pending = asyncio.create_task(
        hass.services.async_call(DOMAIN, "hold_control", call, blocking=True)
    )
    await preflight_started.wait()

    await hass.services.async_call(
        DOMAIN,
        "stop_all",
        {"device_id": ["paired-bed"], "side": released_side},
        blocking=True,
    )
    resume_preflight.set()
    await pending

    assert held == []
    assert clients[released_side].write_gatt_char.await_count > 0
    assert pair._pair_cancel_counter[released_side] == 1
    other_side = "right" if released_side == "left" else "left"
    assert clients[other_side].write_gatt_char.await_count == 0
    assert pair._pair_cancel_counter[other_side] == 0


@pytest.mark.parametrize(
    ("release_target", "newer_work"),
    (("both", False), ("left", False), ("both", True)),
)
async def test_parent_hold_stop_during_pair_lane_wait_drops_old_admission(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    release_target: str,
    newer_work: bool,
) -> None:
    pair, parent, children, triples = await _connected_pair(hass, monkeypatch)
    held: list[tuple[str, str, int]] = []
    new_started, finish_new = asyncio.Event(), asyncio.Event()
    new_cancelled: list[str] = []

    for side, (_child, controller, _client) in triples.items():

        async def hold(control: str, duration: int, side: str = side) -> None:
            held.append((side, control, duration))
            if duration == 100:
                new_started.set()
                try:
                    await finish_new.wait()
                except asyncio.CancelledError:
                    new_cancelled.append(side)
                    raise

        monkeypatch.setattr(controller, "hold_control", hold)

    entered = asyncio.Event()
    run_both = pair._run_both_concurrent

    async def observe_both(*args, **kwargs) -> None:
        entered.set()
        await run_both(*args, **kwargs)

    monkeypatch.setattr(pair, "_run_both_concurrent", observe_both)
    await pair._pair_side_locks["left"].acquire()
    old = asyncio.create_task(
        hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": [parent.id], "control": "head_up", "duration": 60},
            blocking=True,
        )
    )
    newer = None
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert pair._pair_side_locks["left"]._waiters
        target = parent if release_target == "both" else children[release_target]
        await hass.services.async_call(
            DOMAIN, "stop_all", {"device_id": [target.id]}, blocking=True
        )
        if newer_work:
            newer = asyncio.create_task(
                hass.services.async_call(
                    DOMAIN,
                    "hold_control",
                    {
                        "device_id": [children["right"].id],
                        "control": "head_up",
                        "duration": 0.1,
                    },
                    blocking=True,
                )
            )
            await asyncio.wait_for(new_started.wait(), 2)
    finally:
        pair._pair_side_locks["left"].release()

    try:
        await asyncio.wait_for(old, 2)
        assert not [item for item in held if item[2] == 60000]
        assert new_cancelled == []
    finally:
        finish_new.set()
        if newer is not None:
            await asyncio.wait_for(newer, 2)


@pytest.mark.parametrize("release_target", ("both", "left"))
async def test_parent_hold_stop_while_child_scheduler_lock_waits(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    release_target: str,
) -> None:
    pair, parent, children, triples = await _connected_pair(hass, monkeypatch)
    held: list[tuple[str, int]] = []
    new_started, finish_new = asyncio.Event(), asyncio.Event()
    newer_waiting = asyncio.Event()

    for _side, (_child, controller, _client) in triples.items():

        async def hold(control: str, duration: int) -> None:
            held.append((control, duration))
            if duration == 100:
                new_started.set()
                await finish_new.wait()

        monkeypatch.setattr(controller, "hold_control", hold)

    child, _controller, _client = triples["left"]
    scheduler = child._command_scheduler
    handle_created = asyncio.Event()
    new_handle = scheduler._new_handle

    def observe_handle(intent, **kwargs):
        handle = new_handle(intent, **kwargs)
        if intent.kind.value == "group":
            handle_created.set()
        return handle

    monkeypatch.setattr(scheduler, "_new_handle", observe_handle)
    run_single = pair._run_single_concurrent

    async def observe_single(action: str, side: str, *args, **kwargs) -> None:
        if side == "right":
            newer_waiting.set()
        await run_single(action, side, *args, **kwargs)

    monkeypatch.setattr(pair, "_run_single_concurrent", observe_single)
    await scheduler._lock.acquire()
    old = asyncio.create_task(
        hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": [parent.id], "control": "head_up", "duration": 60},
            blocking=True,
        )
    )
    newer = None
    try:
        await asyncio.wait_for(handle_created.wait(), 2)
        assert scheduler._lock._waiters
        target = parent if release_target == "both" else children[release_target]
        await hass.services.async_call(
            DOMAIN, "stop_all", {"device_id": [target.id]}, blocking=True
        )
        newer = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "hold_control",
                {
                    "device_id": [children["right"].id],
                    "control": "head_up",
                    "duration": 0.1,
                },
                blocking=True,
            )
        )
        await asyncio.wait_for(newer_waiting.wait(), 2)
    finally:
        scheduler._lock.release()

    try:
        await asyncio.wait_for(old, 2)
        await asyncio.wait_for(new_started.wait(), 2)
        assert ("head_up", 60000) not in held
        assert held.count(("head_up", 100)) == 1
        assert newer is not None and not newer.done()
    finally:
        finish_new.set()
        if newer is not None:
            await asyncio.wait_for(newer, 2)


@pytest.mark.parametrize(
    ("mx", "control"),
    ((False, "head_up"), (True, "mx_memory1")),
)
async def test_stop_during_hold_preflight_cannot_cancel_a_newer_hold(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    mx: bool,
    control: str,
) -> None:
    """A released disconnected hold cannot replace a newer post-STOP request."""
    coordinator, controller, client = await _target(hass, mx=mx)
    preflight_started = asyncio.Event()
    resume_preflight = asyncio.Event()
    new_hold_started = asyncio.Event()
    finish_new_hold = asyncio.Event()
    ensure_calls = 0
    reset_flags: list[bool] = []

    async def ensure_connected(*, reset_timer: bool = True) -> bool:
        nonlocal ensure_calls
        reset_flags.append(reset_timer)
        ensure_calls += 1
        if ensure_calls == 1:
            preflight_started.set()
            await resume_preflight.wait()
        coordinator._client = client
        coordinator._controller = controller
        return True

    monkeypatch.setattr(coordinator, "async_ensure_connected", ensure_connected)
    held: list[tuple[str, int]] = []

    async def hold_control(control: str, duration_ms: int) -> None:
        held.append((control, duration_ms))
        new_hold_started.set()
        await finish_new_hold.wait()

    monkeypatch.setattr(controller, "hold_control", hold_control)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=coordinator.entry.entry_id, **coordinator.device_info
    )
    await async_register_services(hass)
    released_hold = asyncio.create_task(
        hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": [device.id], "control": control, "duration": 60},
            blocking=True,
        )
    )
    await preflight_started.wait()

    await hass.services.async_call(DOMAIN, "stop_all", {"device_id": [device.id]}, blocking=True)
    assert coordinator._command_scheduler.stop_epoch == 1
    assert client.write_gatt_char.await_count > 0

    newer_hold = asyncio.create_task(
        hass.services.async_call(
            DOMAIN,
            "hold_control",
            {"device_id": [device.id], "control": control, "duration": 0.1},
            blocking=True,
        )
    )
    await new_hold_started.wait()
    resume_preflight.set()
    await released_hold

    assert held == [(control, 100)]
    assert reset_flags[-1] is True  # Stale no-op releases preflight-only idle ownership.
    assert not newer_hold.done()
    assert coordinator._command_scheduler.diagnostics["active_kind"] == "command"

    finish_new_hold.set()
    await newer_hold
    assert held == [(control, 100)]


@pytest.mark.parametrize(
    "mx,control,expected",
    [(False, "head_up", "e5fe160100000005"), (True, "mx_memory1", "040200010000")],
)
async def test_valid_registered_hold_executes_source_bytes_and_release(
    hass, monkeypatch, mx, control, expected
):
    target, controller, client = await _target(hass, mx=mx)
    target._client, target._controller = client, controller
    monkeypatch.setattr(target, "async_ensure_connected", AsyncMock(return_value=True))
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=target.entry.entry_id, **target.device_info
    )
    await async_register_services(hass)
    await hass.services.async_call(
        DOMAIN,
        "hold_control",
        {"device_id": [device.id], "control": control, "duration": 0.1},
        blocking=True,
    )
    frames = [call.args[1] for call in client.write_gatt_char.await_args_list]
    assert frames == [bytes.fromhex(expected)] + (
        [b"\0\xb0"] * 3 if mx else [bytes.fromhex("e5fe160000000006")]
    )
    assert not target._command_scheduler.has_pending


async def test_paired_explicit_child_conflict_rejects_before_any_hold(hass, monkeypatch):
    pair, _parent, children, triples = await _connected_pair(hass, monkeypatch)
    for _child, ctrl, _client in triples.values():
        monkeypatch.setattr(ctrl, "hold_control", AsyncMock())
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "hold_control",
            {
                "device_id": [children["left"].id],
                "side": "right",
                "control": "head_up",
                "duration": 0.1,
            },
            blocking=True,
        )
    for _child, ctrl, _client in triples.values():
        ctrl.hold_control.assert_not_awaited()
    assert pair._pair_cancel_counter == {"left": 0, "right": 0}


@pytest.mark.parametrize("side", ["left", "right", "both"])
async def test_valid_registered_pair_hold_routes_only_requested_physical_sides(
    hass, monkeypatch, side
):
    _pair, parent, _children, triples = await _connected_pair(hass, monkeypatch)
    await hass.services.async_call(
        DOMAIN,
        "hold_control",
        {"device_id": [parent.id], "side": side, "control": "head_up", "duration": 0.1},
        blocking=True,
    )
    for physical_side, (child, _controller, client) in triples.items():
        frames = [call.args[1] for call in client.write_gatt_char.await_args_list]
        assert frames == (
            [bytes.fromhex("e5fe160100000005"), bytes.fromhex("e5fe160000000006")]
            if side in (physical_side, "both")
            else []
        )
        assert not child._command_scheduler.has_pending
