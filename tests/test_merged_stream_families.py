"""Shutdown and fairness with two motors on every merged-stream family (#516).

Leggett Okin Prodigy CE and U Series, Svane Remote (P1 and P2) and Customatic
Clarity run their real controllers through the coordinator and services on
virtual time, with every write taking ``WRITE_S``. Two motors stream together;
then an entry unload, or Home Assistant's shutdown cancelling every task, must
end both with the family's release, and while they stream neither motor may
starve the other's refreshes, even while one is replaced over and over.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import ExitStack
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed.beds.customatic.controller import CustomaticController
from custom_components.adjustable_bed.beds.leggett.okin import LeggettOkinController
from custom_components.adjustable_bed.beds.svane.controller import FEET, HEAD, OLD
from custom_components.adjustable_bed.codec import okin_nframe as codec
from custom_components.adjustable_bed.const import (
    BED_TYPE_CUSTOMATIC_CLARITY,
    BED_TYPE_LEGGETT_OKIN,
    BED_TYPE_SVANE,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_DISCONNECT_AFTER_COMMAND,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    SVANE_VARIANT_JMC,
    SVANE_VARIANT_MULTI,
)
from custom_components.adjustable_bed.coordinator import AdjustableBedCoordinator
from custom_components.adjustable_bed.profiles.okin_nframe import (
    CUSTOMATIC_PROFILES,
    LEGGETT_PROFILES,
)
from custom_components.adjustable_bed.services import async_register_services
from tests.hold_lease_wire import virtual_clock
from tests.test_okin_nframe_hold import _client as okin_client
from tests.test_svane import make_controller as svane_controller

WRITE_S = 0.007
ZERO = codec.STOP.hex()
UP = "000001ac-0000-1000-8000-00805f9b34fb"


@dataclass(frozen=True)
class Family:
    name: str
    motors: tuple[str, str]
    carries: Callable[[str, str], bool]
    """Whether a written frame refreshes ``motor`` moving up."""
    release: Callable[[list[str]], bool]
    """Whether frames written after the stream ended hold the full release."""
    max_gap_ms: int
    """Longest a streaming motor may go without a refresh."""
    min_gap_ms: int = 0
    """Shortest spacing between one motor's refreshes; composing families
    refresh at once on every membership change, by design."""


def _word_carries(keys: dict[str, int]) -> Callable[[str, str], bool]:
    def carries(frame: str, motor: str) -> bool:
        return frame.startswith("0402") and bool(int(frame[4:], 16) & keys[f"{motor}_up"])

    return carries


def _zeros(count: int) -> Callable[[list[str]], bool]:
    return lambda frames: frames.count(ZERO) >= count and set(frames) <= {ZERO}


def _p1_carries(frame: str, motor: str) -> bool:
    return frame == f"{HEAD if motor == 'back' else FEET}/{UP}/0100"


def _p1_release(frames: list[str]) -> bool:
    return {f"{HEAD}/{UP}/0000", f"{FEET}/{UP}/0000"} <= set(frames)


def _p2_carries(frame: str, motor: str) -> bool:
    if not frame.startswith(f"{OLD}/"):
        return False
    mask = int(frame.rsplit("/", 1)[1][2:4], 16)
    return bool(mask & (0x01 if motor == "back" else 0x10))


def _p2_release(frames: list[str]) -> bool:
    return bool(frames) and frames[-1].endswith("/100000000000")


FAMILIES = {
    "prodigy4": Family(
        "prodigy4", ("head", "feet"), _word_carries(dict(LEGGETT_PROFILES["prodigy4"].keys)),
        _zeros(4), 100 + 10,
    ),
    "useries": Family(
        "useries", ("head", "feet"), _word_carries(dict(LEGGETT_PROFILES["useries"].keys)),
        _zeros(4), 100 + 10,
    ),
    # P1 refreshes each axis once per 200 ms pass, timed from its previous write.
    "svane_p1": Family("svane_p1", ("back", "legs"), _p1_carries, _p1_release, 200 + 30, 190),
    "svane_p2": Family("svane_p2", ("back", "legs"), _p2_carries, _p2_release, 100 + 10),
    "clarity": Family(
        "clarity", ("back", "legs"), _word_carries(dict(CUSTOMATIC_PROFILES["clarity"].keys)),
        _zeros(1), 120 + 10,
    ),
}


class Bed:
    def __init__(self, hass: HomeAssistant, family: Family) -> None:
        self.hass = hass
        self.family = family
        self.writes: list[tuple[int, str]] = []
        data = {
            CONF_ADDRESS: "AA:BB:CC:DD:EE:51",
            CONF_NAME: "Stream bed",
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_DISCONNECT_AFTER_COMMAND: False,
        }
        if family.name.startswith("svane"):
            data |= {
                CONF_BED_TYPE: BED_TYPE_SVANE,
                CONF_PROTOCOL_VARIANT: SVANE_VARIANT_JMC
                if family.name == "svane_p2"
                else SVANE_VARIANT_MULTI,
            }
        else:
            data[CONF_BED_TYPE] = (
                BED_TYPE_CUSTOMATIC_CLARITY if family.name == "clarity" else BED_TYPE_LEGGETT_OKIN
            )
        entry = MockConfigEntry(domain=DOMAIN, data=data)
        entry.add_to_hass(hass)
        self.coordinator = coordinator = AdjustableBedCoordinator(hass, entry)
        if family.name.startswith("svane"):
            controller = svane_controller("jmc" if family.name == "svane_p2" else "multi")
            client = controller.client
            controller._coordinator = coordinator
        else:
            client = (
                okin_client([])
                if family.name in ("prodigy4", "useries")
                else SimpleNamespace(
                    is_connected=True,
                    services=[
                        SimpleNamespace(
                            uuid=codec.SERVICE_UUID,
                            characteristics=[
                                SimpleNamespace(
                                    uuid=codec.WRITE_UUID, properties=["write"], handle=1
                                )
                            ],
                        )
                    ],
                    start_notify=AsyncMock(),
                    stop_notify=AsyncMock(),
                    read_gatt_char=AsyncMock(return_value=b""),
                )
            )
            coordinator._client = client
            controller = (
                LeggettOkinController(coordinator, app_profile=family.name)
                if family.name in ("prodigy4", "useries")
                else CustomaticController(coordinator, profile="clarity")
            )
        coordinator._client = client
        coordinator._controller = controller

        async def write(characteristic: Any, payload: bytes, **_kwargs: object) -> None:
            frame = bytes(payload).hex()
            if family.name.startswith("svane"):
                service = next(
                    s.uuid for s in client.services if characteristic in s.characteristics
                )
                frame = f"{service}/{characteristic.uuid}/{frame}"
            self.writes.append((round(asyncio.get_running_loop().time() * 1000), frame))
            await asyncio.sleep(WRITE_S)

        if isinstance(client, SimpleNamespace):
            client.write_gatt_char = write
        else:
            client.write_gatt_char = AsyncMock(side_effect=write)
        client.disconnect = AsyncMock(side_effect=self._disconnected)
        self.disconnected_at: int | None = None

    async def _disconnected(self, *_args: object, **_kwargs: object) -> bool:
        self.disconnected_at = len(self.writes)
        return True

    def move(self, motor: str, duration_ms: int = 5000) -> asyncio.Task[Any]:
        return asyncio.create_task(
            self.hass.services.async_call(
                DOMAIN,
                "timed_move",
                {"device_id": ["bed"], "motor": motor, "direction": "up", "duration_ms": duration_ms},
                blocking=True,
            )
        )

    async def both_streaming(self) -> None:
        """Wait until each motor has had a refresh (P1 writes the axes apart)."""
        async with asyncio.timeout(3):
            while not all(
                any(self.family.carries(frame, motor) for _at, frame in self.writes)
                for motor in self.family.motors
            ):
                await asyncio.sleep(0.001)

    def gaps(self, motor: str, since: int, until: int) -> list[int]:
        """Every interval without a refresh of ``motor``, the window's edges included."""
        times = [
            self.writes[since][0],
            *(at for at, frame in self.writes[since:until] if self.family.carries(frame, motor)),
            self.writes[until - 1][0],
        ]
        return [b - a for a, b in zip(times, times[1:], strict=False)]


@pytest.fixture(params=sorted(FAMILIES))
async def bed(hass: HomeAssistant, request: pytest.FixtureRequest) -> AsyncIterator[Bed]:
    bed = Bed(hass, FAMILIES[request.param])
    await async_register_services(hass)
    with ExitStack() as stack:
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
        stack.enter_context(virtual_clock())
        yield bed
        await bed.coordinator.async_shutdown()


async def test_unload_ends_both_motors_with_their_release(bed: Bed) -> None:
    moves = [bed.move(motor) for motor in bed.family.motors]
    await bed.both_streaming()
    await asyncio.sleep(0.3)
    mark = len(bed.writes)
    # What async_unload_entry runs.
    await bed.coordinator.async_shutdown()
    await asyncio.wait_for(asyncio.gather(*moves, return_exceptions=True), 2)

    after = [frame for _at, frame in bed.writes[mark:]]
    released = next(
        index
        for index, frame in enumerate(after)
        if not any(bed.family.carries(frame, motor) for motor in bed.family.motors)
    )
    # No refresh follows the release, and the link drops only after it.
    assert bed.family.release(after[released:]), after
    assert bed.disconnected_at is not None and bed.disconnected_at >= mark + len(after)


async def test_shutdown_cancelling_every_task_still_releases_both(bed: Bed) -> None:
    moves = [bed.move(motor) for motor in bed.family.motors]
    await bed.both_streaming()
    await asyncio.sleep(0.3)
    mark = len(bed.writes)
    # Home Assistant's stop cancels the callers, then asyncio cancels the rest,
    # the scheduler's worker included.
    worker = bed.coordinator._command_scheduler._worker
    assert worker is not None
    for task in (*moves, worker):
        task.cancel()
    await asyncio.wait_for(asyncio.gather(*moves, worker, return_exceptions=True), 2)

    after = [frame for _at, frame in bed.writes[mark:]]
    released = next(
        index
        for index, frame in enumerate(after)
        if not any(bed.family.carries(frame, motor) for motor in bed.family.motors)
    )
    assert bed.family.release(after[released:]), after


@pytest.mark.parametrize("churned", [0, 1])
async def test_neither_motor_starves_the_other(bed: Bed, churned: int) -> None:
    """A motor replaced faster than the refresh never delays the other one's."""
    motor, steady_motor = bed.family.motors[churned], bed.family.motors[1 - churned]
    steady = bed.move(steady_motor)
    await asyncio.sleep(0.25)
    start = len(bed.writes)
    # Churn: a new move replaces the other motor's every 60 ms for 1.2 s.
    churn = []
    for _ in range(20):
        churn.append(bed.move(motor, 3000))
        await asyncio.sleep(0.06)
    end = len(bed.writes)

    gaps = bed.gaps(steady_motor, start, end)
    assert len(gaps) > 2
    assert max(gaps) <= bed.family.max_gap_ms, gaps
    # Nor is the steady motor refreshed sooner than its own pacing allows.
    assert min(gaps[1:-1]) >= bed.family.min_gap_ms, gaps
    bed.coordinator._command_scheduler.request_cancel()
    await asyncio.gather(steady, *churn, return_exceptions=True)
