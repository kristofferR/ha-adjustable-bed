"""Public STOP and replacement of a paused Independence demo on one pair link."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from bleak.exc import BleakError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.customatic_demo.controller import (
    CustomaticDemoController,
)
from custom_components.adjustable_bed.const import (
    BED_TYPE_CUSTOMATIC_DEMO,
    DOMAIN,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import _cover_entities_for
from custom_components.adjustable_bed.errors import BedCommandFailedError, BedCommandTimedOutError
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    PairedSideProxy,
)
from custom_components.adjustable_bed.paired_devices import async_register_children
from custom_components.adjustable_bed.paired_topology import PairedSideError
from custom_components.adjustable_bed.services import async_register_services
from tests.customatic_demo_vectors import FRAMES
from tests.hold_lease_wire import virtual_clock
from tests.test_okin_bedding_apps import _coordinator

NEUTRAL = FRAMES["stop"]


@pytest.mark.parametrize(
    ("action", "boundary", "failed_neutrals", "stalled", "cancellations"),
    [
        ("replacement", False, (), False, 0),
        ("other_side_stop", False, (), False, 0),
        *(
            (route, boundary, attempt, stalled, 0)
            for route in ("cover_stop", "bed_stop")
            for boundary, attempt, stalled in (
                (False, (), False),
                (True, (), False),
                (False, (3,), False),
                (False, (3,), True),
                (False, (4,), False),
                (False, (4,), True),
                (False, (3, 4), True),
            )
        ),
        *(
            (route, False, (3,), False, cancellations)
            for route in ("cover_stop", "bed_stop")
            for cancellations in (1, 2)
        ),
    ],
)
async def test_paused_demo_releases_its_original_sequential_link(
    hass, monkeypatch, action, boundary, failed_neutrals, stalled, cancellations
) -> None:
    await async_register_services(hass)
    wire: list[tuple[str, str]] = []
    first_release = asyncio.Event()
    fallback_entered = asyncio.Event()
    resume_fallback = asyncio.Event()
    receivers = {}

    for side, last_octet in ((SIDE_LEFT, "01"), (SIDE_RIGHT, "02")):
        entry = MockConfigEntry(
            domain=DOMAIN,
            title=side,
            version=5,
            data={
                "address": f"AA:BB:CC:DD:EE:{last_octet}",
                "bed_type": BED_TYPE_CUSTOMATIC_DEMO,
                "motor_count": 4,
                "disable_angle_sensing": True,
                "connection_mode": "always",
            },
        )
        entry.add_to_hass(hass)
        coordinator = AdjustableBedCoordinator(hass, entry)
        receivers[side] = coordinator
        client = _coordinator().client
        client.is_connected = side == SIDE_LEFT
        coordinator._client = client
        controller = CustomaticDemoController(coordinator)
        coordinator._controller = controller
        if client.is_connected:
            await controller.start_notify()

        async def write(_char, data, *, response, side=side, client=client):
            assert client.is_connected
            wire.append((side, data.hex()))
            if side == SIDE_LEFT and data.hex() == NEUTRAL:
                count = wire.count((side, NEUTRAL))
                if count == 2:
                    first_release.set()
                if cancellations and count == 5:
                    fallback_entered.set()
                    await resume_fallback.wait()
                if count in failed_neutrals:
                    if stalled:
                        await asyncio.Future()
                    raise BleakError("fresh neutral write failed")

        async def connect(
            *_args, side=side, client=client, controller=controller, owner=coordinator, **_kwargs
        ):
            if not client.is_connected and action == "replacement" and side == SIDE_LEFT:
                wire.append((side, "connect"))
                client.is_connected = True
                owner._client = client
                owner._controller = controller
                owner._position_connection_generation += 1
                await controller.start_notify()
            return client.is_connected

        async def disconnect(*_args, side=side, client=client, **_kwargs):
            if client.is_connected:
                wire.append((side, "disconnect"))
                client.is_connected = False

        async def unsubscribe(*_args, side=side, **_kwargs):
            wire.append((side, "unsubscribe"))

        client.write_gatt_char.side_effect = write
        client.stop_notify = AsyncMock(side_effect=unsubscribe)
        client.disconnect = AsyncMock(side_effect=disconnect)
        coordinator.async_connect = AsyncMock(side_effect=connect)
        coordinator.async_ensure_connected = AsyncMock(side_effect=connect)

    entry = MockConfigEntry(domain=DOMAIN, version=5, title="Pair", data={"pair_id": "demo-stop"})
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    pair = PairedBedCoordinator(hass, entry, receivers, connection_mode="sequential")
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = pair
    device = dr.async_get(hass).async_get_or_create_from_info(
        config_entry_id=entry.entry_id, device_info=pair.device_info
    )
    async_register_children(hass, pair)
    left, right = receivers[SIDE_LEFT], receivers[SIDE_RIGHT]
    cover = next(
        entity
        for entity in _cover_entities_for(hass, PairedSideProxy(pair, left, SIDE_LEFT))
        if entity.entity_description.key == "back"
    )
    cover.async_write_ha_state = lambda: None
    flat_ready = asyncio.Event()
    resume_flat = asyncio.Event()
    if boundary:
        controller = left.controller
        assert isinstance(controller, CustomaticDemoController)
        write_frame = controller._write_gatt_with_retry

        async def pause_at_flat(uuid, command, **kwargs):
            if command.hex() == FRAMES["auto_flat"]:
                flat_ready.set()
                await resume_flat.wait()
            await write_frame(uuid, command, **kwargs)

        monkeypatch.setattr(controller, "_write_gatt_with_retry", pause_at_flat)
        note_stop = pair._admission.note_stop

        def release_flat_after_recording_stop(side, resources):
            note_stop(side, resources)
            if side == SIDE_LEFT:
                assert left.stop_epoch == epochs[0]
                resume_flat.set()

        monkeypatch.setattr(pair._admission, "note_stop", release_flat_after_recording_stop)

    try:
        with virtual_clock():
            demo = asyncio.create_task(
                hass.services.async_call(
                    DOMAIN,
                    "customatic_demo_run",
                    {"device_id": device.id, "side": SIDE_LEFT, "confirm": True},
                    blocking=True,
                )
            )
            async with asyncio.timeout(2):
                await first_release.wait()
            await asyncio.sleep(0.001)
            initial = [(SIDE_LEFT, FRAMES["auto_sit"])] * 3 + [(SIDE_LEFT, NEUTRAL)] * 2
            teardown = [(SIDE_LEFT, "unsubscribe"), (SIDE_LEFT, "disconnect")]
            assert wire == initial
            epochs = (left.stop_epoch, right.stop_epoch)
            ensure_calls = left.async_ensure_connected.await_count
            queued: asyncio.Task[None] | None = None
            if action in {"cover_stop", "bed_stop"}:
                # A request already queued on this pair lane cannot start after STOP.
                queued = asyncio.create_task(
                    pair.async_execute_controller_command(
                        lambda ctrl: ctrl.move_legs_up(),
                        side=SIDE_LEFT,
                        cancel_running=False,
                        resource="motor:legs",
                    )
                )
                await asyncio.sleep(0)
            if boundary:
                async with asyncio.timeout(120):
                    await flat_ready.wait()

            if cancellations:
                if action == "cover_stop":
                    stop = asyncio.create_task(cover.async_stop_cover())
                else:
                    stop = asyncio.create_task(hass.services.async_call(
                        DOMAIN, "stop_all", {"device_id": device.id}, blocking=True
                    ))
                async with asyncio.timeout(2):
                    await fallback_entered.wait()
                for _ in range(cancellations):
                    demo.cancel()
                    await asyncio.sleep(0)
                resume_fallback.set()
                await stop
            elif action == "cover_stop":
                await cover.async_stop_cover()
            elif action == "bed_stop":
                await hass.services.async_call(
                    DOMAIN, "stop_all", {"device_id": device.id}, blocking=True
                )
            elif action == "other_side_stop":
                await hass.services.async_call(
                    DOMAIN,
                    "stop_all",
                    {"device_id": device.id, "side": SIDE_RIGHT},
                    blocking=True,
                )
                assert wire == initial
                await demo
                assert wire == (
                    initial
                    + [(SIDE_LEFT, FRAMES["auto_flat"])] * 3
                    + [(SIDE_LEFT, NEUTRAL)] * 2
                    + teardown
                )
                assert (left.stop_epoch, right.stop_epoch) == epochs
                assert (pair.stop_count(SIDE_LEFT), pair.stop_count(SIDE_RIGHT)) == (0, 1)
                return
            else:
                await cover.async_close_cover()
            # Both public STOP calls wait for the new release, even when the
            # command cycle disconnects before their writer lane opens.
            release = initial + [(SIDE_LEFT, NEUTRAL)] * (4 if failed_neutrals else 2)
            assert wire[: len(release)] == release
            if cancellations:
                with pytest.raises(asyncio.CancelledError):
                    await demo
                assert not left.is_connected
            elif failed_neutrals:
                with pytest.raises(PairedSideError) as error:
                    await demo
                expected_error = BedCommandTimedOutError if stalled else BedCommandFailedError
                assert isinstance(error.value.side_errors[SIDE_LEFT], expected_error)
            else:
                await demo
            if queued is not None:
                await queued
                assert left.async_ensure_connected.await_count == ensure_calls
            await asyncio.sleep(121)

        assert wire[len(release) : len(release) + 2] == teardown
        assert all(side == SIDE_LEFT for side, _ in wire)
        assert all(frame != FRAMES["auto_flat"] for _, frame in wire)
        if action == "replacement":
            assert wire[len(release) + 2 : len(release) + 4] == [
                (SIDE_LEFT, "connect"),
                (SIDE_LEFT, FRAMES["back_down"]),
            ]
            assert (left.stop_epoch, right.stop_epoch) == epochs
        else:
            assert wire == release + teardown
            assert (left.stop_epoch, right.stop_epoch) == (epochs[0] + 1, epochs[1])
            assert pair.stop_count(SIDE_LEFT) == 1
            assert pair.stop_count(SIDE_RIGHT) == (action == "bed_stop")
    finally:
        for receiver in receivers.values():
            await receiver.async_shutdown()
