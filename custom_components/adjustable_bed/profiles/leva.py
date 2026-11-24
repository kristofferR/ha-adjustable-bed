"""Leva Bed Remote model, screen and transport choices over the Okin N-frame codec."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal, cast

from ..codec import okin_nframe
from ..const import (
    KEESON_BASE_SERVICE_UUID,
    KEESON_BASE_WRITE_CHAR_UUID,
    NORDIC_UART_SERVICE_UUID,
    NORDIC_UART_WRITE_CHAR_UUID,
)
from ..execution import NO_EXECUTION_CAPABILITIES, STREAM_HOLD, ExecutionCapabilities

type Route = Literal["evolution", "ascent", "okin"]
type Receiver = Literal["nordic", "okin", "dual"]

DIRECTIONS: Final = {
    "back_up": "headUp",
    "back_down": "headDown",
    "legs_up": "footUp",
    "legs_down": "footDown",
    "pillow_up": "pillowTiltUp",
    "pillow_down": "pillowTiltDown",
    "lumbar_up": "lumbarUp",
    "lumbar_down": "lumbarDown",
}
BASIC_AXES: Final = ("back", "legs")
EXTRA_AXES: Final = (*BASIC_AXES, "pillow", "lumbar")
HOME_PRESETS: Final = ("flat", "zeroG", "antiSnore", "tv")
MASSAGE: Final = ("massageHeadPlus", "massageFeetPlus", "massageTimer")
REFRESH_MS: Final = 100
SETUP_SECONDS: Final = 0.2
CLOCK_COPIES: Final = 3
CLOCK_GAP_SECONDS: Final = 0.05
CLOCK_SETTLE_SECONDS: Final = 0.5

# Numeric words below are in on-wire byte order for the codec's big-endian encoders.
_EVOLUTION: Final = {
    "stop": 0,
    "headUp": 0x01,
    "headDown": 0x02,
    "footUp": 0x04,
    "footDown": 0x08,
    "pillowTiltUp": 0x10,
    "pillowTiltDown": 0x20,
    "lumbarUp": 0x40,
    "lumbarDown": 0x80,
    "flat": 0x08000000,
    "zeroG": 0x00001000,
    "antiSnore": 0x00008000,
    "tv": 0x00004000,
    "memory1": 0x00010000,
    "memory2": 0x00002000,
    "underBedLight": 0x00020000,
    "massageHeadPlus": 0x00000100,
    "massageFeetPlus": 0x00000400,
    "massageTimer": 0x00000800,
}
_ASCENT: Final = {
    "stop": 0,
    "headUp": 0x0100,
    "headDown": 0x0200,
    "footUp": 0x0700,
    "footDown": 0x0800,
    "pillowTiltUp": 0x5000,
    "pillowTiltDown": 0x2000,
    "lumbarUp": 0x4000,
    "lumbarDown": 0x8000,
    "flat": 0x0800000000,
    "zeroG": 0x00100000,
    "antiSnore": 0x00800000,
    "tv": 0x00400000,
    "light": 0x02000000,
    "massageHeadPlus": 0x00080000,
    "massageFeetPlus": 0x00040000,
    "massageTimer": 0x00020000,
    "massageMode": 0x1000000000,
}
_OKIN: Final = {
    "stop": 0,
    "headUp": 0x01000000,
    "headDown": 0x02000000,
    "footUp": 0x04000000,
    "footDown": 0x08000000,
    "flat": 0x08,
    "zeroG": 0x00100000,
    "antiSnore": 0x00800000,
    "tv": 0x00400000,
    "light": 0x00000200,
    "massageHeadPlus": 0x00080000,
    "massageFeetPlus": 0x00040000,
    "massageTimer": 0x00020000,
    "massageMode": 0x00004000,
}


@dataclass(frozen=True, slots=True)
class Transport:
    """A route selects the exact characteristic, write mode and release schedule."""

    service: str
    write: str
    response: bool
    words: dict[str, int]
    width: Literal[4, 5] | None
    stop_copies: int
    retry_gaps: tuple[float, ...] = ()
    stop_gap: float = 0.05
    clock_init: bool = False

    def frame(self, action: str) -> bytes:
        word = self.words[action]
        if self.width is None:
            return okin_nframe.gateway_frame(word)
        return okin_nframe.frame(word, self.width)


TRANSPORTS: Final[dict[Route, Transport]] = {
    "evolution": Transport(
        NORDIC_UART_SERVICE_UUID, NORDIC_UART_WRITE_CHAR_UUID, True, _EVOLUTION, 4, 3, (0.05, 0.1)
    ),
    "ascent": Transport(
        NORDIC_UART_SERVICE_UUID, NORDIC_UART_WRITE_CHAR_UUID, False, _ASCENT, 5, 1, clock_init=True
    ),
    "okin": Transport(KEESON_BASE_SERVICE_UUID, KEESON_BASE_WRITE_CHAR_UUID, True, _OKIN, None, 3),
}


@dataclass(frozen=True, slots=True)
class Model:
    label: str
    nordic_route: Route
    axes: tuple[str, ...]
    expanded: bool = True
    okin_remote: bool = False


MODELS: Final = {
    "ascent": Model("Ascent", "ascent", EXTRA_AXES),
    "elite250": Model("Elite 250", "ascent", BASIC_AXES, expanded=False),
    "elite500": Model("Elite 500", "ascent", BASIC_AXES, okin_remote=True),
    "evolutionlx": Model("Evolution LX", "evolution", EXTRA_AXES),
    "questelite": Model("Quest Elite", "evolution", EXTRA_AXES),
}
RECEIVERS: Final[dict[str, str]] = {
    "nordic": "Nordic UART",
    "okin": "OKIN (FFE5/FFE9)",
    "dual": "OKIN and Nordic UART",
}


@dataclass(frozen=True, slots=True)
class LevaProfile:
    model: Model
    receiver: Receiver

    @property
    def remote(self) -> Route | None:
        if self.receiver != "nordic" and self.model.okin_remote:
            return "okin"
        return self.model.nordic_route if self.receiver != "okin" else None

    @property
    def home(self) -> Route:
        return self.model.nordic_route if self.receiver == "nordic" else "okin"

    @property
    def home_presets(self) -> tuple[str, ...]:
        return HOME_PRESETS if self.model.expanded else HOME_PRESETS[:2]

    @property
    def axes(self) -> tuple[str, ...]:
        return self.model.axes if self.remote is not None else ()

    @property
    def execution(self) -> ExecutionCapabilities:
        return STREAM_HOLD if self.axes else NO_EXECUTION_CAPABILITIES

    @property
    def memory_slots(self) -> int:
        return 2 if self.remote == "evolution" else 0

    @property
    def routes(self) -> tuple[Route, ...]:
        if self.remote is None or self.remote == self.home:
            return (self.home,)
        return (self.remote, self.home)

    def allows_tap(self, action: str, *, home: bool) -> bool:
        if home:
            return action in self.home_presets
        if self.remote is None:
            return False
        return (
            action in self.home_presets
            or action in ("memory1", "memory2")
            and self.memory_slots > 0
            or self.expanded_remote
            and action in (*MASSAGE, "light", "underBedLight", "massageMode")
            and action in TRANSPORTS[self.remote].words
        )

    @property
    def expanded_remote(self) -> bool:
        return self.remote is not None and self.model.expanded


def selected_profile(model_key: object, receiver: object) -> LevaProfile | None:
    """Return the explicitly chosen model and receiver if both are valid."""
    model = MODELS.get(str(model_key))
    if model is None or not isinstance(receiver, str) or receiver not in RECEIVERS:
        return None
    return LevaProfile(model, cast(Receiver, receiver))


def clock_frame(now: datetime) -> bytes:
    """Encode HA local time as the app's seven packed-BCD fields, Sunday = zero."""
    fields = (
        now.year - 2000,
        now.month,
        now.day,
        (now.weekday() + 1) % 7,
        now.hour,
        now.minute,
        now.second,
    )
    return okin_nframe.clock(tuple(int(str(value), 16) & 0xFF for value in fields))


def okin_name(name: str) -> bool:
    """The app's post-verification classification hint."""
    name = name.lower()
    return name.startswith("okin") or "okin-ble" in name
