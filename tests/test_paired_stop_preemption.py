"""A paired side's cover Stop never waits behind another motor (#516).

Leggett Okin Prodigy CE receivers (per-motor scheduler resources) run on a
concurrent or sequential two-address pair and on a one-address pair, on virtual
time with every write taking ``WRITE_S``. Before STOP pre-emption reached the
paired topologies, a left feet Stop sent during a left head move put its first
zero on the wire about 0.55 s later, after the head burst and its release.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.leggett.okin import LeggettOkinController
from custom_components.adjustable_bed.codec import okin_nframe as codec
from custom_components.adjustable_bed.const import (
    BED_TYPE_LEGGETT_OKIN,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    DOMAIN,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.cover import _cover_entities_for
from custom_components.adjustable_bed.paired_coordinator import (
    PairedBedCoordinator,
    PairedSideProxy,
    SingleAddressPairedCoordinator,
)
from custom_components.adjustable_bed.paired_devices import child_device_info
from custom_components.adjustable_bed.profiles.okin_nframe import LEGGETT_HOLD, LEGGETT_PROFILES
from tests.hold_lease_wire import virtual_clock
from tests.test_okin_nframe_hold import _client

WRITE_S = 0.007
KEYS = LEGGETT_PROFILES["prodigy4"].keys
HEAD = codec.frame(KEYS["head_up"]).hex()
ZERO = codec.STOP.hex()
RELEASE = [ZERO] * LEGGETT_HOLD.releases


class Wire:
    """Every write on every receiver, stamped in virtual ms and tagged."""

    def __init__(self) -> None:
        self.writes: list[tuple[int, str, str]] = []

    def mark(self) -> tuple[int, int]:
        return round(asyncio.get_running_loop().time() * 1000), len(self.writes)

    def since(self, mark: tuple[int, int], tag: str | None = None) -> list[tuple[int, str]]:
        at_ms, count = mark
        return [
            (at - at_ms, frame)
            for at, written, frame in self.writes[count:]
            if tag is None or written == tag
        ]

    async def until(self, tag: str, frame: str, count: int) -> None:
        async with asyncio.timeout(3):
            while [(t, f) for _a, t, f in self.writes].count((tag, frame)) < count:
                await asyncio.sleep(0.001)


def _receiver(hass: HomeAssistant, index: int, wire: Wire, tag: str) -> AdjustableBedCoordinator:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ADDRESS: f"AA:BB:CC:DD:EE:{index:02X}",
            CONF_NAME: f"Receiver {index}",
            CONF_BED_TYPE: BED_TYPE_LEGGETT_OKIN,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_DISCONNECT_AFTER_COMMAND: False,
        },
    )
    entry.add_to_hass(hass)
    coordinator = AdjustableBedCoordinator(hass, entry)
    client = _client([])

    async def write(_characteristic: object, payload: bytes, **_kwargs: object) -> None:
        wire.writes.append(
            (round(asyncio.get_running_loop().time() * 1000), tag, bytes(payload).hex())
        )
        await asyncio.sleep(WRITE_S)

    client.write_gatt_char = write
    coordinator._client = client
    coordinator._controller = LeggettOkinController(coordinator, app_profile="prodigy4")
    coordinator._async_refresh_controller_auth = AsyncMock()  # type: ignore[method-assign]

    async def connect(*_args: object, **_kwargs: object) -> bool:
        client.is_connected = True
        return True

    async def disconnect(*_args: object, **_kwargs: object) -> bool:
        # A sequential pair switches its one link between the receivers.
        client.is_connected = False
        return True

    coordinator.async_connect = connect  # type: ignore[method-assign]
    coordinator.async_ensure_connected = connect  # type: ignore[method-assign]
    coordinator.async_disconnect = disconnect  # type: ignore[method-assign]
    return coordinator


def _two_address(hass: HomeAssistant, wire: Wire, mode: str) -> PairedBedCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data={"pair_id": f"pair-{mode}"})
    entry.add_to_hass(hass)
    return PairedBedCoordinator(
        hass,
        entry,
        {SIDE_LEFT: _receiver(hass, 1, wire, "L"), SIDE_RIGHT: _receiver(hass, 2, wire, "R")},
        connection_mode=mode,
    )


def _one_address(hass: HomeAssistant, wire: Wire) -> SingleAddressPairedCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data={"pair_id": "one", CONF_BED_TYPE: BED_TYPE_LEGGETT_OKIN})
    entry.add_to_hass(hass)
    return SingleAddressPairedCoordinator(hass, entry, _receiver(hass, 3, wire, "I"))


@pytest.fixture
async def clock(hass: HomeAssistant) -> AsyncIterator[Any]:
    with virtual_clock() as fake:
        yield fake


def _proxy(pair: PairedBedCoordinator, side: str) -> PairedSideProxy:
    return PairedSideProxy(pair, pair.children[side], side)


def _spec(pair: PairedBedCoordinator, motor: str) -> Any:
    controller = pair.children[SIDE_LEFT].capability_controller
    assert controller is not None
    return next(spec for spec in controller.motor_control_specs if spec.key == motor)


def _move(pair: PairedBedCoordinator, side: str, motor: str = "head") -> asyncio.Task[None]:
    """What a side's cover Open sends: serial pulses through the pair."""
    return asyncio.create_task(
        pair.async_execute_controller_command(
            _spec(pair, motor).open_fn, side=side, resource=f"motor:{motor}"
        )
    )


async def _stop(pair: PairedBedCoordinator, side: str, motor: str = "feet") -> None:
    """What a side's cover Stop sends."""
    await _proxy(pair, side).async_stop_motor(_spec(pair, motor).stop_fn, f"motor:{motor}")


@pytest.mark.parametrize("topology", ["concurrent", "sequential", "one"])
async def test_a_side_stop_preempts_another_motors_move_on_that_side(
    hass: HomeAssistant, clock: Any, topology: str
) -> None:
    wire = Wire()
    pair = _one_address(hass, wire) if topology == "one" else _two_address(hass, wire, topology)
    tag = "I" if topology == "one" else "L"
    move = _move(pair, SIDE_LEFT)
    # The fourth head refresh is on the wire when the feet Stop arrives.
    await wire.until(tag, HEAD, 4)
    requested = wire.mark()
    await _stop(pair, SIDE_LEFT)
    await move

    after = wire.since(requested, tag)
    # No further refresh: head's own release, the first within one write's
    # latency, then feet's. A sequential cycle instead drops the side's link
    # after the release, which halts it, so no STOP frame races that drop.
    expected = RELEASE if topology == "sequential" else RELEASE + RELEASE
    assert [frame for _at, frame in after] == expected
    assert after[0][0] <= WRITE_S * 1000
    if topology == "sequential":
        assert not pair.children[SIDE_LEFT].is_connected


async def test_the_other_receiver_of_a_two_address_pair_keeps_moving(
    hass: HomeAssistant, clock: Any
) -> None:
    wire = Wire()
    pair = _two_address(hass, wire, "concurrent")
    left, right = _move(pair, SIDE_LEFT), _move(pair, SIDE_RIGHT)
    await wire.until("L", HEAD, 3)
    requested = wire.mark()
    await _stop(pair, SIDE_LEFT)
    await asyncio.gather(left, right)

    # The right head finishes its whole burst and its own release.
    assert [frame for _at, frame in wire.since(requested, "R")][-len(RELEASE) :] == RELEASE
    assert HEAD in [frame for _at, frame in wire.since(requested, "R")]
    assert {frame for _at, frame in wire.since(requested, "L")} == {ZERO}


async def test_a_linked_both_move_keeps_its_other_side(hass: HomeAssistant, clock: Any) -> None:
    wire = Wire()
    pair = _two_address(hass, wire, "concurrent")
    both = _move(pair, SIDE_BOTH)
    await wire.until("L", HEAD, 3)
    requested = wire.mark()
    await _stop(pair, SIDE_LEFT)
    await both

    left = wire.since(requested, "L")
    assert {frame for _at, frame in left} == {ZERO}
    assert left[0][0] <= WRITE_S * 1000
    # The linked right half runs its burst out.
    assert HEAD in [frame for _at, frame in wire.since(requested, "R")]


async def test_a_one_address_stop_never_preempts_the_other_side(
    hass: HomeAssistant, clock: Any
) -> None:
    wire = Wire()
    pair = _one_address(hass, wire)
    right = _move(pair, SIDE_RIGHT)
    await wire.until("I", HEAD, 3)
    requested = wire.mark()
    await asyncio.gather(_stop(pair, SIDE_LEFT), right)

    after = [frame for _at, frame in wire.since(requested, "I")]
    # The right head burst completes and releases; only then the left Stop.
    assert after[: after.index(ZERO)] == [HEAD] * (10 - 3)
    assert after[after.index(ZERO) :] == RELEASE + RELEASE


@pytest.mark.parametrize("resource", ["motor:feet", "motor:head", "motor:*"])
async def test_a_one_address_side_stop_ends_a_native_both_move(
    hass: HomeAssistant, clock: Any, resource: str
) -> None:
    """A native Both move drives this side in the same frame as the other.

    So a Stop on this side, for another motor, the same motor or side-wide,
    ends it on both sides, as overlapping replacement and a side STOP do.
    """
    wire = Wire()
    pair = _one_address(hass, wire)
    both = _move(pair, SIDE_BOTH)
    await wire.until("I", HEAD, 3)
    active = pair._single_inner._command_scheduler._active
    assert active is not None and any(r.startswith("side:right:") for r in active.intent.resources)
    requested = wire.mark()
    await _proxy(pair, SIDE_LEFT).async_stop_motor(_spec(pair, "feet").stop_fn, resource)
    await both

    after = wire.since(requested, "I")
    assert {frame for _at, frame in after} == {ZERO}
    assert after[0][0] <= WRITE_S * 1000


async def test_a_side_wide_stop_drops_a_move_queued_on_that_side(
    hass: HomeAssistant, clock: Any
) -> None:
    """A move still waiting on the side lane behind a linked Both move never starts."""
    wire = Wire()
    pair = _two_address(hass, wire, "concurrent")
    both = _move(pair, SIDE_BOTH)
    await wire.until("L", HEAD, 3)
    queued = _move(pair, SIDE_LEFT, "feet")
    await asyncio.sleep(0)
    requested = wire.mark()
    await _proxy(pair, SIDE_LEFT).async_stop_motor(_spec(pair, "feet").stop_fn, "motor:*")
    await asyncio.gather(both, queued)

    feet = codec.frame(KEYS["feet_up"]).hex()
    assert feet not in [frame for _at, frame in wire.since(requested, "L")]


async def test_a_sequential_stop_on_the_disconnected_side_sends_nothing(
    hass: HomeAssistant, clock: Any
) -> None:
    """A side without the shared link already halted when it dropped."""
    wire = Wire()
    pair = _two_address(hass, wire, "sequential")
    pair.children[SIDE_RIGHT]._client.is_connected = False  # type: ignore[union-attr]
    move = _move(pair, SIDE_LEFT)
    await wire.until("L", HEAD, 3)
    requested = wire.mark()
    await _stop(pair, SIDE_RIGHT)
    await move

    assert wire.since(requested, "R") == []
    # The left move was not touched: its whole burst, then its release.
    assert [frame for _at, frame in wire.since(requested, "L")] == [HEAD] * (10 - 3) + RELEASE


async def test_a_paired_cover_stop_takes_the_preempting_path(
    hass: HomeAssistant, clock: Any
) -> None:
    wire = Wire()
    pair = _two_address(hass, wire, "concurrent")
    registry = dr.async_get(hass)
    registry.async_get_or_create(config_entry_id=pair.entry.entry_id, **pair.device_info)
    registry.async_get_or_create_child(
        config_entry_id=pair.entry.entry_id, **child_device_info(pair, SIDE_LEFT)
    )
    covers = {
        cover.entity_description.key: cover
        for cover in _cover_entities_for(hass, _proxy(pair, SIDE_LEFT))
    }
    for cover in covers.values():
        cover.async_write_ha_state = lambda: None  # type: ignore[method-assign]
    move = asyncio.create_task(covers["head"].async_open_cover())
    await wire.until("L", HEAD, 4)
    requested = wire.mark()
    await covers["feet"].async_stop_cover()
    await move

    after = wire.since(requested, "L")
    assert [frame for _at, frame in after] == RELEASE + RELEASE
    assert after[0][0] <= WRITE_S * 1000
