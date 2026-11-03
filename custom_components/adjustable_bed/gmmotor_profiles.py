"""Typed GM Control app catalogs and product-local state transitions."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from .gmmotor_catalog_types import Phase, ProfileRow, TransitionRow
from .gmmotor_protocol import Material, stop_packet

# Ordered RGB values of the eight-color page (0x781e84..0x781ee0).
EIGHT_COLORS = (
    (255, 255, 0),
    (0, 255, 0),
    (0, 127, 255),
    (0, 0, 255),
    (139, 0, 255),
    (255, 255, 255),
    (255, 0, 0),
    (255, 165, 0),
)


@lru_cache(maxsize=512)
def material(index: int) -> Material:
    """Resolve a compact runtime material without importing unrelated controllers."""
    from .gmmotor_catalog import MATERIALS

    return Material(*MATERIALS[index][:6])


@dataclass(frozen=True, slots=True)
class Action:
    """One exact app control, including its state-dependent captured material."""

    index: int

    @property
    def material(self) -> Material:
        from .gmmotor_catalog import ACTIONS

        return material(ACTIONS[self.index][0])

    @property
    def gesture(self) -> int:
        from .gmmotor_catalog import ACTIONS, MATERIALS

        return MATERIALS[ACTIONS[self.index][0]][6]

    @property
    def transitions(self) -> tuple[TransitionRow, ...]:
        from .gmmotor_catalog import ACTIONS

        return ACTIONS[self.index][1]

    @property
    def phases(self) -> frozenset[Phase]:
        return frozenset(row[1] for row in self.transitions)

    @property
    def phone_only(self) -> bool:
        return self.material.name == "deviceFunctionItemPhoneLight"

    def apply(self, state: int, phase: Phase, *, side: int, single: bool) -> tuple[int, bytes]:
        """Resolve the exact admitted transition before any write or state change."""
        candidates = [row for row in self.transitions if row[0] == state and row[1] == phase]
        if len(candidates) != 1:
            raise ValueError("Control phase is unavailable in the current GM Control state")
        _, _, after, emit, long, target = candidates[0]
        if not emit:
            return after, b""
        return after, (
            stop_packet(side=side, single=single)
            if phase == "release"
            else material(target).packet(side=side, single=single, long=long)
        )


@dataclass(frozen=True, slots=True)
class Profile:
    """Selected default or nested product configuration with consumed features."""

    key: str
    row: ProfileRow

    @property
    def controls(self) -> tuple[Action, ...]:
        return tuple(Action(index) for index in self.row[0])

    @property
    def initial_state(self) -> int:
        return self.row[1]

    @property
    def has_light(self) -> bool:
        return self.row[2]

    @property
    def eight_colors(self) -> bool:
        return self.row[3]

    @property
    def repeat_alarm(self) -> bool:
        return self.row[4]

    @property
    def sleep_kind(self) -> str:
        return self.row[5]

    @property
    def massage_timer(self) -> bool:
        return self.row[8]

    @property
    def sides(self) -> tuple[int, ...]:
        return self.row[6]

    @property
    def alarm_choices(self) -> tuple[tuple[str, int], ...]:
        return self.row[7]


def load_profile(key: str) -> Profile:
    """Require an exact admitted primary product/configuration."""
    from .gmmotor_catalog import PROFILES

    if key in ("FWRM", "WFRM"):
        # These routes bypass detailsPageDisplayList for the dedicated desk UI.
        return Profile(key, ((), 0, False, False, False, "none", (0,), (), False))
    if key not in PROFILES or key == "QRRM":
        raise ValueError("Choose an exact GM Control product and configuration")
    return Profile(key, PROFILES[key])


def profile_choices() -> dict[str, str]:
    """Explicit products keep shared BLE names from overriding existing profiles."""
    from .gmmotor_catalog import PROFILES

    choices = {
        key: (
            key.replace(":0", " (standard)").replace(":1", " (split head)") or "Empty app fallback"
        )
        for key in PROFILES
        if key != "QRRM"
    }
    choices.update({"FWRM": "FWRM (desk)", "WFRM": "WFRM (desk)"})
    return choices
