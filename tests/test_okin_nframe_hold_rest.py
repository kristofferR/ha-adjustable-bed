"""Renewable holds (#483) on the remaining stream-supported Okin N-frame rows.

Each route's real controller runs on the wire snapshot's stored GATT layout
and virtual time (``tests/hold_lease_wire.py``), with the pulse plan a leased
``timed_move`` gives it. The held frame streams at the route's own cadence
until the lease expires or STOP arrives, then exactly the route's release
frames follow.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from custom_components.adjustable_bed.const import (
    CONF_STARCODE_COMMAND_SELECTOR,
    ZSERIES_VARIANT_Z280,
)
from custom_components.adjustable_bed.profiles import okin_nframe as profiles
from tests.hold_lease_wire import intervals, leased_hold
from tests.okin_nframe_vectors import FROZEN_FRAMES
from tests.sleepys_box25_star_vectors import BOX25_STAR_FRAMES
from tests.starcode_abm5_4_vectors import BUILDER_VECTORS

CST_HEAD = "0c02000000010000000000000000"
CST_STOP = "0c02000000000000000000000000"
NFRAME40_STOP = "05020000000000"
NFRAME64_STOP = "08020000000000000000"
# Held time after the route's post-connect reads have settled.
HOLD_S = 5


@dataclass(frozen=True)
class Route:
    scenario: str
    move: str
    held: str
    stop: str
    releases: int
    """STOP frames the route sends at release."""
    interval_ms: int
    """The route's refresh: its profile's, or the entry's pulse delay plus the write."""
    entry_data: dict[str, Any] = field(default_factory=dict)
    variant: str | None = None

    def frozen(self, profile_key: str) -> frozenset[str]:
        if not profile_key:
            return BOX25_STAR_FRAMES
        frozen = FROZEN_FRAMES[profile_key]
        selector = self.entry_data.get(CONF_STARCODE_COMMAND_SELECTOR)
        if selector is not None:
            # BOX15 and BOX1220 move and stop with their own report frames.
            frozen |= {vector for row, *_, vector in BUILDER_VECTORS if row == selector}
        return frozen


def _abm(selector: str, held: str, stop: str) -> Route:
    return Route(
        "starcode_abm5_4",
        "move_back_up",
        held,
        stop,
        1,
        profiles.STARCODE_ABM5_4_REFRESH_MS,
        {CONF_STARCODE_COMMAND_SELECTOR: selector},
    )


_CST_PRODUCTS = (
    "sanctuary",
    "resident",
    "aviada",
    "bob",
    "contempo",
    "carefree",
    "clarity",
    "mf900",
    "support",
    "nectar_move",
)
ROUTES: dict[str, Route] = {
    # Okin CST: 100 ms at the snapshot entry's pulse delay, plus the write; two STOPs.
    **{
        f"cst_{product}": Route(
            f"okin_cst:cst_{product}", "move_head_up", CST_HEAD, CST_STOP, 2, 107
        )
        for product in _CST_PRODUCTS
    },
    "serenity": Route("serenity", "move_head_up", CST_HEAD, CST_STOP, 2, 100),
    "tranquil": Route("tranquil", "move_head_up", CST_HEAD, CST_STOP, 2, 100),
    "zseries_z230": Route("customatic_zseries", "move_head_up", CST_HEAD, CST_STOP, 2, 100),
    "zseries_z280": Route(
        "customatic_zseries",
        "move_feet_up",
        "0c02000000040000000000000000",
        CST_STOP,
        2,
        100,
        variant=ZSERIES_VARIANT_Z280,
    ),
    "adjustable_lumbar_okin": Route(
        "adjustable_lumbar:adjustable_lumbar_okin",
        "move_head_up",
        "08020000000100000000",
        NFRAME64_STOP,
        2,
        100,
    ),
    "adjustable_lumbar_star": Route(
        "adjustable_lumbar:adjustable_lumbar_star",
        "move_lumbar_up",
        "08020000001000000000",
        NFRAME64_STOP,
        2,
        100,
    ),
    "simmons_okin": Route(
        "simmons:simmons_okin", "move_back_up", "e6fe16010000000004", "e6fe16000000000005", 2, 300
    ),
    "simmons_smartbed": Route(
        "simmons:simmons_smartbed", "move_legs_up", "05020000000400", NFRAME40_STOP, 2, 300
    ),
    "starcode_abm5_4": _abm("none", "05020000000100", NFRAME40_STOP),
    "starcode_abm5_4_box3633": _abm("BOX3633", "05020000000100", NFRAME40_STOP),
    "starcode_abm5_4_box25": _abm("BOX25", "05020000000100", NFRAME40_STOP),
    "starcode_abm5_4_box15": _abm("BOX15", "e6fe16010000000004", "e6fe16000000000005"),
    "starcode_abm5_4_box1220": _abm("BOX1220", "a55ade00002001", "a55adf00002000"),
    "sleepys_box25_star": Route(
        "sleepys_box25:box25_star", "move_head_up", "5a0103103000a5", "5a010310300fa5", 1, 107
    ),
    "sleepys_box25_legacy": Route(
        "sleepys_box25:box25_legacy", "move_feet_up", "05020000000400", NFRAME40_STOP, 1, 107
    ),
}


async def _hold(route: Route, end: str, end_after_s: float) -> Any:
    async def move(controller: Any) -> None:
        # Let the route's own post-connect reads finish first: the virtual
        # coordinator runs them inline instead of queueing them.
        await asyncio.sleep(2)
        await getattr(controller, route.move)()

    return await leased_hold(
        route.scenario,
        move,
        end_after_s=2 + end_after_s,
        end=end,  # type: ignore[arg-type]
        entry_data=route.entry_data,
        variant=route.variant,
        timed_move=True,
    )


@pytest.mark.parametrize("key", sorted(ROUTES))
async def test_lease_streams_until_expiry_then_sends_exactly_its_release(key: str) -> None:
    route = ROUTES[key]
    wire = await _hold(route, "expire", HOLD_S)

    assert {route.held, route.stop} <= route.frozen(wire.profile_key)
    profile = next((p for p in _declared() if p.key == wire.profile_key), None)
    if profile is not None and profile.hold.releases:
        # BOX15 and BOX1220 stop with their own frame; the rest as profiled.
        assert route.releases == profile.hold.releases
    assert {write.data.hex() for write in wire.held} == {route.held}
    # The refresh outlives any finite pulse train, at the route's own cadence.
    assert intervals(wire.held) == {route.interval_ms}
    assert len(wire.held) >= HOLD_S * 1000 // route.interval_ms
    # Expiry ends with the route's complete release and nothing else.
    assert [write.data.hex() for write in wire.after] == [route.stop] * route.releases


@pytest.mark.parametrize("key", sorted(ROUTES))
async def test_stop_preempts_the_lease_and_releases(key: str) -> None:
    route = ROUTES[key]
    wire = await _hold(route, "stop", 1)

    after = [write.data.hex() for write in wire.after]
    assert {write.data.hex() for write in wire.held} == {route.held}
    # The hold's own release, then the STOP's; motion never resumes.
    assert after[: route.releases] == [route.stop] * route.releases
    assert set(after) == {route.stop}


def _declared() -> list[profiles.OkinNFrameProfile]:
    return [
        profile
        for group in (
            profiles.CST_PROFILES,
            profiles.BEDDING_PROFILES,
            profiles.SIMMONS_PROFILES,
            profiles.STARCODE_ABM5_4_PROFILES,
            profiles.ADJUSTABLE_LUMBAR_PROFILES,
        )
        for profile in group.values()
        if profile.execution.hold
    ]


def test_routes_cover_every_declared_profile() -> None:
    assert {profile.key for profile in _declared()} <= set(ROUTES)
