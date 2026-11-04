"""Profiles over the Okin 5A codec.

``OKIN_7BYTE`` serves the ``okin_7byte`` and ``nectar`` bed types, ``OKIN_NORDIC``
serves ``okin_nordic`` and ``mattressfirm``, ``OKIN_CB35`` serves ``okin_cb35`` and
``ELEVATE`` serves ``star_elevate`` with both of its routes. No accepted APK
report covers these key frames, so each profile holds the frames its pre-v5
controller sent.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal

from ..codec import okin_5a as codec
from ..codec.okin_5a import (
    ALTERNATE,
    MATTRESSFIRM_HANDSHAKE,
    NORMAL,
    STOP,
    WAKE,
    TransportKey,
    command,
)
from ..execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities

Action = Literal[
    "stop",
    "head_up",
    "head_down",
    "feet_up",
    "feet_down",
    "lumbar_up",
    "lumbar_down",
    "neck_up",
    "neck_down",
    "hips_up",
    "hips_down",
    "both_up",
    "both_down",
    "interrupt",
    "flat",
    "zero_g",
    "anti_snore",
    "lounge",
    "tv",
    "incline",
    "memory_1",
    "memory_2",
    "massage_toggle",
    "massage_on",
    "massage_off",
    "massage_mode",
    "massage_up",
    "massage_down",
    "massage_head_up",
    "massage_head_down",
    "massage_foot_up",
    "massage_foot_down",
    "light_on",
    "light_off",
    "light_toggle",
    "light_brightness_up",
    "light_brightness_down",
    "light_color",
]


@dataclass(frozen=True, kw_only=True)
class Tap:
    """Write a frame ``repeats`` times, ``repeat_ms`` apart."""

    repeats: int = 1
    repeat_ms: int = 100


@dataclass(frozen=True, kw_only=True)
class Okin5AProfile:
    key: str
    execution: ExecutionCapabilities = NO_EXECUTION_CAPABILITIES
    """Held and concurrent execution this app is proven to support."""
    transport: TransportKey
    write_with_response: bool
    wake: tuple[bytes, ...] = ()
    """Connection frames sent once, before the first command of a session."""
    wake_with_response: bool = False
    frames: Mapping[Action, bytes]
    """Every action the profile sends. A missing action is unsupported."""
    recall: Tap
    """Presets and memory recall. Bed profiles follow each with STOP; ELEVATE flat sends none."""
    stop: Tap = Tap()
    lights_off: Tap = Tap()
    light_cycle: bool = False
    """Expose the light-cycle button, which presses light on."""

    def frame(self, action: Action) -> bytes:
        if (data := self.frames.get(action)) is None:
            raise NotImplementedError(f"{action} is not supported by {self.key}")
        return data

    @property
    def transport_uuid(self) -> str:
        return codec.TRANSPORTS[self.transport].write_uuid

    @property
    def notify_uuid(self) -> str:
        return codec.TRANSPORTS[self.transport].notify_uuid


def _keys(keys: Mapping[Action, int], page: int = NORMAL) -> dict[Action, bytes]:
    return {action: command(key, page) for action, key in keys.items()}


_STOP: Final[dict[Action, bytes]] = {"stop": STOP}
# Keys shared by the three bed profiles. Each profile adds or overrides its own.
_BED_KEYS: Final = _STOP | _keys(
    {
        "head_up": 0x00,
        "head_down": 0x01,
        "feet_up": 0x02,
        "feet_down": 0x03,
        "lumbar_down": 0x07,
        "flat": 0x10,
        "zero_g": 0x13,
        "anti_snore": 0x16,
        "massage_mode": 0x59,
        "light_on": 0x73,
        "light_off": 0x74,
        "light_toggle": 0x71,
    }
)

# Nordic and CB35 share these massage keys.
_MASSAGE_MODE_KEYS: Final = _keys({"massage_toggle": 0x5A, "massage_on": 0x52, "massage_off": 0x6F})

OKIN_7BYTE: Final = Okin5AProfile(
    key="okin_7byte",
    transport="okin",
    write_with_response=False,
    frames=_BED_KEYS
    | _keys(
        {
            "lumbar_up": 0x04,
            "lounge": 0x11,
            "tv": 0x11,
            "memory_1": 0x1A,
            "memory_2": 0x1B,
            "massage_toggle": 0x58,
            "massage_on": 0x58,
            "massage_off": 0x5A,
        }
    ),
    recall=Tap(repeats=100, repeat_ms=300),
)
OKIN_NORDIC: Final = Okin5AProfile(
    key="okin_nordic",
    transport="nus",
    write_with_response=True,
    wake=(MATTRESSFIRM_HANDSHAKE, WAKE),
    wake_with_response=True,
    frames=_BED_KEYS
    | _MASSAGE_MODE_KEYS
    | _keys({"lumbar_up": 0x06, "lounge": 0x17, "tv": 0x17, "incline": 0x18})
    | _keys({"massage_up": 0x60, "massage_down": 0x63}, ALTERNATE),
    recall=Tap(repeats=100, repeat_ms=300),
    lights_off=Tap(repeats=3),
    light_cycle=True,
)
OKIN_CB35: Final = Okin5AProfile(
    key="okin_cb35",
    transport="nus",
    write_with_response=False,
    wake=(WAKE,),
    frames=_BED_KEYS
    | _MASSAGE_MODE_KEYS
    | _keys(
        {
            "lumbar_up": 0x06,
            "neck_up": 0x0A,
            "neck_down": 0x0B,
            "hips_up": 0x08,
            "hips_down": 0x09,
            "lounge": 0x17,
            "tv": 0x11,
            "incline": 0x18,
            "memory_1": 0x1A,
            "memory_2": 0x1B,
            "massage_up": 0x60,
            "massage_down": 0x61,
            "massage_head_up": 0x60,
            "massage_head_down": 0x61,
            "massage_foot_up": 0x62,
            "massage_foot_down": 0x63,
            "light_brightness_up": 0x80,
            "light_brightness_down": 0x81,
            "light_color": 0x70,
        }
    ),
    # Verified on a Sealy Element (2026-09): a preset key x2 only arms the bed;
    # STOP x3 at 300 ms commits the move.
    recall=Tap(repeats=2, repeat_ms=300),
    stop=Tap(repeats=3, repeat_ms=300),
    lights_off=Tap(repeats=3),
    light_cycle=True,
)
# ELEVATE lifts: actuator 1 is head, actuator 2 is feet, both is their union.
# Flat is a one-shot without STOP.
ELEVATE: Final = Okin5AProfile(
    key="star_elevate",
    transport="nus",
    write_with_response=False,
    wake=(WAKE,),
    frames=_STOP
    | _keys(
        {
            "head_up": 0x40,
            "head_down": 0x41,
            "feet_up": 0x42,
            "feet_down": 0x43,
            "both_up": 0x44,
            "both_down": 0x45,
            "flat": 0x46,
            "interrupt": 0x4F,
        }
    ),
    recall=Tap(),
)
PROFILES: Final[dict[str, Okin5AProfile]] = {
    profile.key: profile for profile in (OKIN_7BYTE, OKIN_NORDIC, OKIN_CB35, ELEVATE)
}
