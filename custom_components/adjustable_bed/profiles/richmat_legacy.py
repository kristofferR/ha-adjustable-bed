"""App-qualified fixed ASCII controls from SleepEvolution and W.Silver 3.x."""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field, replace
from functools import cache
from pathlib import Path
from typing import Final, NotRequired, TypedDict, cast

from ..execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities

APP_NAMES: Final = {
    "sleep_evolution": "SleepEvolution",
    "wsilver_legacy": "W.Silver Products (3.x)",
}


class BranchData(TypedDict):
    writes: list[str]
    threshold: int | None


class ActionData(TypedDict):
    key: str
    label: str
    down: list[str]
    branches: dict[str, BranchData]
    states: list[str]
    short: list[str]
    short_guard: int | None
    release: list[str]
    select: str | None
    selected_value: int | None
    motion: bool
    down_by_selection: NotRequired[list[list[str]]]
    axis_value: NotRequired[int]
    reset_counter: NotRequired[bool]


class ScreenData(TypedDict):
    app: str
    code: str
    initial_ms: int
    period_ms: int
    routes: list[str]
    actions: list[ActionData]


@dataclass(frozen=True, slots=True)
class Branch:
    writes: tuple[str, ...]
    threshold: int | None


@dataclass(frozen=True, slots=True)
class Action:
    key: str
    label: str
    screen: str
    down: tuple[str, ...]
    branches: tuple[tuple[str, Branch], ...]
    states: tuple[str, ...]
    short: tuple[str, ...]
    short_guard: int | None
    release: tuple[str, ...]
    select: str | None
    selected_value: int | None
    motion: bool
    down_by_selection: tuple[tuple[str, ...], ...] = ()
    axis_value: int | None = None
    reset_counter: bool = False

    @property
    def programmable(self) -> bool:
        return any(b.threshold is not None for _, b in self.branches)

    @property
    def choices(self) -> tuple[int, ...]:
        """Values of the app's axis/mode choice this control acts on, if any."""
        if self.select == "axis":
            return (0, 1)
        if self.select == "mode":
            # Mode 0 arms no movement.
            return tuple(m for m in (1, 2, 3) if m < len(self.states) and self.states[m] != "0")
        return ()

    def control_ids(self) -> tuple[str, ...]:
        """The bare key plus one "<key>@<choice>" id per choice."""
        return (self.key, *(f"{self.key}@{choice}" for choice in self.choices))


@dataclass(frozen=True, slots=True)
class LegacyProfile:
    key: str
    app: str
    code: str
    routes: tuple[str, ...]
    schedules: tuple[tuple[str, int, int], ...]
    actions: tuple[Action, ...]

    execution: ExecutionCapabilities = field(init=False)

    def __post_init__(self) -> None:
        controls = frozenset(c for a in self.actions if a.motion for c in a.control_ids())
        object.__setattr__(
            self,
            "execution",
            ExecutionCapabilities(hold="stream", hold_controls=controls)
            if controls
            else NO_EXECUTION_CAPABILITIES,
        )

    def action(self, key: str) -> Action:
        """The action for a control id, accepting "<key>@<choice>" for its offered choices."""
        base, _, choice = key.partition("@")
        for action in self.actions:
            if action.key == base and key in action.control_ids():
                return action
        raise ValueError("Choose a control offered by this app and prefix")


@cache
def profiles() -> dict[str, LegacyProfile]:
    data = cast(
        dict[str, ScreenData],
        json.loads(
            gzip.decompress((Path(__file__).parent / "data/richmat_legacy.json.gz").read_bytes())
        ),
    )
    result = {}
    for key, screen in data.items():
        actions = tuple(
            Action(
                key=a["key"],
                label=a["label"],
                screen=screen["code"],
                down=tuple(a["down"]),
                branches=tuple(
                    (k, Branch(tuple(v["writes"]), v["threshold"]))
                    for k, v in a["branches"].items()
                ),
                states=tuple(a["states"]),
                short=tuple(a["short"]),
                short_guard=a["short_guard"],
                release=tuple(a["release"]),
                select=a["select"],
                selected_value=a["selected_value"],
                motion=a["motion"],
                down_by_selection=tuple(tuple(v) for v in a.get("down_by_selection", [])),
                axis_value=a.get("axis_value"),
                reset_counter=a.get("reset_counter", False),
            )
            for a in screen["actions"]
        )
        result[key] = LegacyProfile(
            key,
            screen["app"],
            screen["code"],
            tuple(screen["routes"]),
            ((screen["code"], screen["initial_ms"], screen["period_ms"]),),
            actions,
        )
    for app in APP_NAMES:
        primary, massage = result[f"{app}:BE"], result.pop(f"{app}:BE_massage")
        result[primary.key] = replace(
            primary,
            schedules=primary.schedules + massage.schedules,
            actions=primary.actions
            + tuple(replace(a, key="massage_" + a.key) for a in massage.actions),
        )
    return result


def choices(app: str) -> dict[str, str]:
    return {p.code: p.code for p in profiles().values() if p.app == app}


def matching_profile(app: str, name: str | None) -> str:
    """Exact two-character case-sensitive source gates, only after app selection."""
    if name is not None:
        for profile in profiles().values():
            if profile.app == app and name.startswith(profile.routes):
                return profile.code
    return ""
