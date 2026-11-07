"""Customatic concurrent motors (#516) on the merged stream, and STOP pre-emption.

Clarity, Jerome's and Remedy OR every held motor key into one shared mask on a
120 ms refresh, and a released motor's bit leaves the mask while the others
keep streaming (row028). The real controller runs through the coordinator and
services on virtual time, with every write taking ``WRITE_S``, so a Stop can
arrive while a refresh is on the wire.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import ExitStack
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.customatic.controller import CustomaticController
from custom_components.adjustable_bed.codec import okin_nframe as codec
from custom_components.adjustable_bed.command_scheduler import CommandOutcome, StreamMember
from custom_components.adjustable_bed.const import (
    BED_TYPE_CUSTOMATIC_CLARITY,
    BED_TYPE_CUSTOMATIC_JEROMES,
    BED_TYPE_CUSTOMATIC_REMEDY,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    DOMAIN,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles.okin_nframe import (
    CUSTOMATIC_HOLD,
    CUSTOMATIC_PROFILES,
    CUSTOMATIC_REFRESH_MS,
)
from custom_components.adjustable_bed.services import async_register_services
from tests.hold_lease_wire import virtual_clock
from tests.okin_nframe_vectors import FROZEN_FRAMES

WRITE_S = 0.007
BED_TYPES = {
    "clarity": BED_TYPE_CUSTOMATIC_CLARITY,
    "jeromes": BED_TYPE_CUSTOMATIC_JEROMES,
    "remedy": BED_TYPE_CUSTOMATIC_REMEDY,
}
KEYS = CUSTOMATIC_PROFILES["clarity"].keys
BACK = codec.frame(KEYS["back_up"]).hex()
LEGS = codec.frame(KEYS["legs_up"]).hex()
BOTH = codec.frame(KEYS["back_up"] | KEYS["legs_up"]).hex()
ZERO = codec.STOP.hex()


class Bed:
    """One Customatic bed: its coordinator and every write, stamped in ms."""

    def __init__(self, hass: HomeAssistant, profile: str) -> None:
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Customatic bed",
            unique_id="AA:BB:CC:DD:EE:28",
            data={
                CONF_ADDRESS: "AA:BB:CC:DD:EE:28",
                CONF_NAME: "Customatic bed",
                CONF_BED_TYPE: BED_TYPES[profile],
                CONF_DISABLE_ANGLE_SENSING: True,
                CONF_DISCONNECT_AFTER_COMMAND: False,
            },
        )
        entry.add_to_hass(hass)
        self.hass = hass
        self.writes: list[tuple[int, str]] = []
        self.coordinator = AdjustableBedCoordinator(hass, entry)
        self.coordinator._client = self._client()  # type: ignore[assignment]
        self.controller = CustomaticController(self.coordinator, profile=profile)
        self.coordinator._controller = self.controller
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = self.coordinator

    def _client(self) -> SimpleNamespace:
        async def write(_characteristic: object, payload: bytes, **_kwargs: object) -> None:
            self.writes.append((self.now(), bytes(payload).hex()))
            await asyncio.sleep(WRITE_S)

        characteristic = SimpleNamespace(uuid=codec.WRITE_UUID, properties=["write"], handle=1)
        return SimpleNamespace(
            is_connected=True,
            services=[SimpleNamespace(uuid=codec.SERVICE_UUID, characteristics=[characteristic])],
            write_gatt_char=write,
            start_notify=AsyncMock(),
            stop_notify=AsyncMock(),
            read_gatt_char=AsyncMock(return_value=b""),
            disconnect=AsyncMock(),
        )

    @staticmethod
    def now() -> int:
        return round(asyncio.get_running_loop().time() * 1000)

    def spec(self, motor: str) -> Any:
        return next(s for s in self.controller.motor_control_specs if s.key == motor)

    async def move(self, motor: str, duration_ms: int, *, lease_ms: int | None = None) -> None:
        data: dict[str, object] = {
            "device_id": ["bed"],
            "motor": motor,
            "direction": "up",
            "duration_ms": duration_ms if lease_ms is None else lease_ms,
        }
        if lease_ms is not None:
            data |= {"hold_owner": f"card-{motor}", "hold_generation": 1}
        await self.hass.services.async_call(DOMAIN, "timed_move", data, blocking=True)

    async def stop_motor(self, motor: str) -> None:
        """What a cover's own Stop sends on a standalone bed."""
        await self.coordinator.async_stop_motor(self.spec(motor).stop_fn, f"motor:{motor}")

    async def until(self, frame: str, *, count: int = 1) -> None:
        async with asyncio.timeout(5):
            while [data for _at, data in self.writes].count(frame) < count:
                await asyncio.sleep(0.001)

    def mark(self) -> tuple[int, int]:
        """Now, and how many writes have started (one may still be on the wire)."""
        return self.now(), len(self.writes)

    def since(self, mark: tuple[int, int]) -> list[tuple[int, str]]:
        """Writes started after ``mark``, in ms from it."""
        at_ms, count = mark
        return [(at - at_ms, data) for at, data in self.writes[count:]]


@pytest.fixture
async def make_bed(hass: HomeAssistant) -> AsyncIterator[Callable[[str], Bed]]:
    beds: list[Bed] = []
    with ExitStack() as stack:

        def build(profile: str = "clarity") -> Bed:
            bed = Bed(hass, profile)
            stack.enter_context(
                patch.object(bed.coordinator, "async_ensure_connected", AsyncMock(return_value=True))
            )
            stack.enter_context(
                patch.object(bed.coordinator, "_async_refresh_controller_auth", AsyncMock())
            )
            stack.enter_context(
                patch(
                    "custom_components.adjustable_bed.services._resolve_sided_targets",
                    return_value=([(bed.coordinator, "both")], []),
                )
            )
            beds.append(bed)
            return bed

        await async_register_services(hass)
        yield build
        for bed in beds:
            await bed.coordinator.async_shutdown()


@pytest.fixture
async def clock(make_bed) -> AsyncIterator[Any]:
    with virtual_clock() as fake:
        yield fake


def _members(*held: str) -> tuple[StreamMember, ...]:
    return tuple(
        StreamMember(
            motor=control.rsplit("_", 1)[0],
            resource=f"motor:{control.rsplit('_', 1)[0]}",
            action=control.rsplit("_", 1)[1],
            deadline=1.0,
        )
        for control in held
    )


@pytest.mark.parametrize("profile", sorted(CUSTOMATIC_PROFILES))
def test_every_composed_mask_is_the_apps(profile: str) -> None:
    """A composed tick is the app's shared OR mask: frozen literal or exact builder."""
    controller = CustomaticController(SimpleNamespace(), profile=profile)  # type: ignore[arg-type]
    axes = controller.simultaneous_movement_axes
    assert controller.execution.concurrent == {f"motor:{axis}" for axis in axes}
    frozen = FROZEN_FRAMES[profile]
    # The reports freeze the all-up chords.
    all_up = codec.frame(controller._stream_mask(_members(*(f"{a}_up" for a in axes)))).hex()
    assert all_up in frozen
    for control in controller.held_control_options:
        tokens = control.split("+")
        if not all(token.rsplit("_", 1)[0] in axes for token in tokens):
            continue  # memory pages are not motors
        mask, motor = controller._control_mask(control)
        assert motor
        # The stream builds the same mask the held control does.
        assert controller._stream_mask(_members(*tokens)) == mask
        if len(tokens) == 1:
            assert codec.frame(mask).hex() in frozen


async def test_two_held_motors_share_one_stream(make_bed, clock) -> None:
    bed = make_bed()
    back = asyncio.create_task(bed.move("back", 600))
    await bed.until(BACK)
    legs = asyncio.create_task(bed.move("legs", 600))
    await asyncio.gather(back, legs)

    frames = [data for _at, data in bed.writes]
    assert BOTH in frames
    assert set(frames) <= {BACK, LEGS, BOTH, ZERO}
    # One lane: composed ticks are 120 ms apart from each write's start.
    both = [at for at, data in bed.writes if data == BOTH]
    assert {b - a for a, b in zip(both, both[1:], strict=False)} == {CUSTOMATIC_REFRESH_MS}
    # The last motor out: one zero write 100 ms after the release.
    assert frames[-1] == ZERO and frames.count(ZERO) == 1


async def test_a_motor_stop_mid_refresh_goes_out_within_one_write(make_bed, clock) -> None:
    bed = make_bed()
    back = asyncio.create_task(bed.move("back", 5000))
    await bed.until(BACK)
    legs = asyncio.create_task(bed.move("legs", 5000))
    await bed.until(BOTH, count=3)
    # The third composed refresh is on the wire.
    requested = bed.mark()
    assert requested[0] - bed.writes[-1][0] < WRITE_S * 1000
    await bed.stop_motor("legs")
    await legs
    await asyncio.sleep(0.5)

    after = bed.since(requested)
    # The reduced mask is next, within one write's latency; back keeps moving.
    assert after[0][1] == BACK
    assert after[0][0] <= WRITE_S * 1000
    assert {data for _at, data in after} == {BACK}
    gaps = {b[0] - a[0] for a, b in zip(after, after[1:], strict=False)}
    assert max(gaps) <= CUSTOMATIC_REFRESH_MS
    bed.coordinator._command_scheduler.request_cancel()
    await asyncio.gather(back, return_exceptions=True)


async def test_stop_all_ends_every_member_but_a_motor_stop_only_its_own(make_bed, clock) -> None:
    bed = make_bed("remedy")
    moves = [asyncio.create_task(bed.move(motor, 5000)) for motor in ("back", "legs", "lumbar")]
    remedy = CUSTOMATIC_PROFILES["remedy"].keys
    all_up = codec.frame(remedy["back_up"] | remedy["legs_up"] | remedy["lumbar_up"]).hex()
    await bed.until(all_up, count=2)
    await bed.stop_motor("lumbar")
    await moves[2]
    await bed.until(BOTH, count=2)
    assert not moves[0].done() and not moves[1].done()

    requested = bed.mark()
    await bed.coordinator.async_stop_command()
    await asyncio.gather(*moves)
    after = bed.since(requested)
    # Every member ends: the release (100 ms) then the STOP's own zero, nothing else.
    assert [data for _at, data in after] == [ZERO, ZERO]
    assert after[0][0] == CUSTOMATIC_HOLD.release_after_ms


async def test_a_motor_stop_preempts_another_motors_serial_move(make_bed, clock) -> None:
    """A cover's own serial pulses on one motor never delay another motor's Stop."""
    bed = make_bed()
    move = asyncio.create_task(
        bed.coordinator.async_execute_controller_command(
            bed.spec("back").open_fn, resource="motor:back"
        )
    )
    await bed.until(BACK, count=3)
    requested = bed.mark()
    await bed.stop_motor("legs")
    await move

    after = bed.since(requested)
    # No further refresh: the move's own release (the app's zero 100 ms after
    # release), then the STOP's zero.
    assert [data for _at, data in after] == [ZERO, ZERO]
    assert after[0][0] == CUSTOMATIC_HOLD.release_after_ms
    record = bed.coordinator._command_scheduler.recent_records
    assert any(r.outcome is CommandOutcome.STOPPED for r in record)


async def test_a_lease_expiring_while_a_stop_is_pending(make_bed, clock) -> None:
    bed = make_bed()
    back = asyncio.create_task(bed.move("back", 5000))
    await bed.until(BACK)
    # The card's lease on legs is never renewed: it ends 750 ms after its claim.
    leased_at = asyncio.get_running_loop().time()
    legs = asyncio.create_task(bed.move("legs", 0, lease_ms=750))
    await bed.until(BOTH)
    # Back's Stop arrives just before, so the lease ends during its cleanup write.
    await asyncio.sleep(leased_at + 0.75 - WRITE_S / 2 - asyncio.get_running_loop().time())
    requested = bed.mark()
    stop = asyncio.create_task(bed.stop_motor("back"))
    await asyncio.gather(stop, back, legs)
    await asyncio.sleep(0.3)

    after = bed.since(requested)
    # Back's Stop writes the reduced mask; legs' lease ends during that write,
    # so legs is the last out and gets the one release. No tick follows.
    assert [data for _at, data in after] == [LEGS, ZERO]
    assert after[0][0] <= WRITE_S * 1000
    assert after[1][0] <= WRITE_S * 1000 + CUSTOMATIC_HOLD.release_after_ms


async def test_cancelling_the_stop_caller_keeps_the_stop(make_bed, clock) -> None:
    bed = make_bed()
    move = asyncio.create_task(
        bed.coordinator.async_execute_controller_command(
            bed.spec("back").open_fn, resource="motor:back"
        )
    )
    await bed.until(BACK, count=2)
    requested = bed.mark()
    stop = asyncio.create_task(bed.stop_motor("legs"))
    # Cancel the caller while the pre-empted move runs its own release.
    await asyncio.sleep(0.05)
    stop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await stop
    await move
    # The STOP outlived its caller: the move's release, then its own zero.
    assert [data for _at, data in bed.since(requested)] == [ZERO, ZERO]



async def test_stop_all_during_a_member_cleanup_sends_no_further_motion(make_bed, clock) -> None:
    """A whole-stream STOP between two members' cleanups ends the rest at once."""
    bed = make_bed("remedy")
    remedy = CUSTOMATIC_PROFILES["remedy"].keys
    all_up = codec.frame(remedy["back_up"] | remedy["legs_up"] | remedy["lumbar_up"]).hex()
    lumbar = codec.frame(remedy["lumbar_up"]).hex()
    moves = [asyncio.create_task(bed.move(motor, 5000)) for motor in ("back", "legs", "lumbar")]
    await bed.until(all_up, count=2)
    await bed.stop_motor("back")
    await bed.stop_motor("legs")
    # Back's cleanup writes the reduced mask; Stop all lands during that write.
    await bed.until(lumbar)
    requested = bed.mark()
    await bed.coordinator.async_stop_command()
    await asyncio.gather(*moves)

    # Legs' cleanup must not write lumbar again: only the release and the STOP.
    assert [data for _at, data in bed.since(requested)] == [ZERO, ZERO]
