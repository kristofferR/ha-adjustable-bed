"""Softide's independent realtime, Moon and SmartRelax consumer state."""

from dataclasses import dataclass, field
from struct import pack, unpack

from ...codec.sleep_assistant import SoftideData
from ...profiles.softide import MOON_DISPLAY_SECONDS, MOON_GATE_MS, MOON_SAMPLE_LIMIT


def no_data(shown: int, zero: int) -> bool:
    """Original Java float division, widened to double before the 0.4 comparison."""

    def f32(value: float) -> float:
        return unpack("f", pack("f", value))[0]

    return shown > 18 and f32(f32(zero) / f32(shown)) > 0.4


@dataclass(slots=True)
class Rates:
    right: tuple[int, int] = (0, 0)
    left: tuple[int, int] = (0, 0)
    right_present: bool = False
    left_present: bool = False
    presence: bool = False
    right_motion: int = 0
    left_motion: int = 0
    twitch: int = 0
    last: float = 0
    shown: int = 0
    zero: int = 0

    def realtime(self, data: SoftideData, selection: str) -> tuple[int, int] | None:
        pair = data.rates
        if data.si == 0:
            self.right, self.right_motion = pair, data.bm if data.lb == 0 else 0
            self.right_present = data.lb == 0
        else:
            self.left, self.left_motion = pair, data.bm if data.lb == 0 else 0
            self.left_present = data.lb == 0
        motion = data.bm
        if selection == "right" and data.si != 0 or selection == "left" and data.si == 0:
            return None
        self.presence = data.lb == 0
        if selection == "combined":
            self.presence = self.right_present or self.left_present
            if data.si != 0:
                return None
            pair = (max(self.right[0], self.left[0]), max(self.right[1], self.left[1]))
            motion = max(self.right_motion, self.left_motion)
        if selection == "single" and data.lb != 0 or selection != "single" and pair == (0, 0):
            self.twitch = 0
        elif motion > 0:
            self.twitch = self.twitch + 1 if self.twitch < 99 else 1
        return pair

    def moon(
        self, data: SoftideData, selection: str, now: float, *, has_bed: bool = True
    ) -> tuple[int, int] | None:
        if not has_bed:
            return None
        elapsed, self.last = now - self.last, now
        if elapsed <= MOON_GATE_MS / 1000:
            return None
        pair = data.rates
        if data.si == 0:
            self.right = pair
        else:
            self.left = pair
        if selection == "right" and data.si != 0 or selection == "left" and data.si == 0:
            return None
        if selection == "combined":
            return (
                (max(self.right[0], self.left[0]), max(self.right[1], self.left[1]))
                if data.si == 0
                else None
            )
        return pair

    def relax(
        self, data: SoftideData, selection: str, *, playing: bool, has_bed: bool = True
    ) -> tuple[int, int] | None:
        if not has_bed or not playing or data.lb != 0:
            return None
        pair = (data.hr, data.br)
        if selection == "combined":
            if data.si == 0:
                self.right = pair
            elif data.si == 1:
                self.left = pair
            return (
                (max(self.right[0], self.left[0]), max(self.right[1], self.left[1]))
                if data.si == 1
                else None
            )
        if selection == "right" and data.si != 0 or selection == "left" and data.si != 1:
            return None
        return pair if selection in ("single", "right", "left") else None


@dataclass(slots=True)
class SoftideState:
    realtime: Rates = field(default_factory=Rates)
    moon: Rates = field(default_factory=Rates)
    relax: Rates = field(default_factory=Rates)
    active_program: str | None = None
    program_started: float = 0
    moon_samples: int = 0
    epoch: object = field(default_factory=object)
    last_relax: tuple[int, int] | None = None
    last_moon: tuple[int, int] | None = None

    def retire(self) -> None:
        self.active_program = None
        self.epoch = object()

    def start(self, action: str, now: float) -> None:
        self.active_program, self.program_started = action, now
        self.moon_samples = 0
        self.epoch = object()
        self.moon = Rates()
        self.relax = Rates()
        self.last_relax = self.last_moon = None

    def feed(self, data: SoftideData, selection: str, now: float) -> bool:
        self.last_relax = self.relax.relax(
            data, selection, playing=self.active_program == "smart_relaxation"
        )
        if self.active_program != "one_button_sleep":
            return False
        self.last_moon = self.moon.moon(data, selection, now)
        if self.last_moon is not None:
            # startMoonSuccess freezes storage at startIndex + 96. Inactive
            # chart history is unrelated to this program's new-sample budget.
            if self.moon_samples >= MOON_SAMPLE_LIMIT:
                return False
            self.moon_samples += 1
        if self.last_moon is not None and now - self.program_started >= MOON_DISPLAY_SECONDS:
            self.moon.shown += 1
            self.moon.zero += self.last_moon == (0, 0)
            return no_data(self.moon.shown, self.moon.zero)
        return False
