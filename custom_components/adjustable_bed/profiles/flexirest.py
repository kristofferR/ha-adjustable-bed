"""Sealy FlexiRest 1.0.4 (4), one K1 layout over the shared FFFF codec."""

from __future__ import annotations

from typing import Final

from ..codec import ff_frame as codec
from ..execution import ExecutionCapabilities
from .ff_frame import SolaceCommands as C
from .ff_frame import SolaceProfile

PROFILE: Final = SolaceProfile(
    key="flexirest",
    execution=ExecutionCapabilities(hold="latched"),
    axes=("back", "legs"),
    presets=True,
    memory_slots=2,
    queries="q2",
    massage=True,
    light_levels=True,
    light_timer=True,
    relaxing_bedtime=True,
)
NAME_TOKENS: Final = ("QMS", "QMS2", "QMS4", "Sealy", "S4-6")
CLOCK_DELAY_MS: Final = 1000
SYNC_DELAY_MS: Final = 1500
LIGHT_QUERY_DELAY_MS: Final = 1000
PRESET_QUERY_DELAY_MS: Final = 2300
PRESET_QUERY_SPACING_MS: Final = 500
PRESET_HOLD_MS: Final = 2000
SYNC_OFF: Final = codec.summed(1, 9, b"\x00")
SYNC_ON: Final = codec.summed(1, 9, b"\x01")
SYNC_QUERY: Final = codec.summed(1, 10, b"\x0f")
LIGHT_OFF: Final = codec.control(0x4B)
FAULT_QUERY: Final = codec.query(0x5A, 2)
ALARM_MODES: Final = {"none": 3, "zero_g": 1, "memory_1": 2}
PARTS: Final = {
    "6008": "Head",
    "4002": "Head",
    "6009": "Back",
    "4004": "Back",
    "600C": "Left hip",
    "600D": "Right hip",
    "6007": "Left leg",
    "600A": "Right leg",
    "60CD": "Hip",
    "400D": "Hip",
    "607A": "Leg",
    "400A": "Leg",
}
FAULTS: Final = {
    "000A": "Motor broken",
    "0014": "Motor overload",
    "001E": "Motor short circuit",
    "00C8": "Sensor broken",
    "00D2": "Same group sensor broken",
    "00DC": "Large distance difference",
    "00E6": "Motor reverse action",
    "0064": "Distance out of range",
    "006E": "Distance mutation",
    "0078": "Target position deviation",
    "0000": "The equipment is all right",
}
# These gates hide the app's diagnostics row, never select a different wire format.
FAULT_HIDDEN_TOKENS: Final = (
    "QMS-IQ",
    *(f"QMS-I{i}6" for i in range(10)),
    *(f"QMS-L{i}4" for i in range(10)),
)


def accepts_name(name: str | None) -> bool:
    return bool(name and any(token in name for token in NAME_TOKENS))


def normalize_name(name: str) -> str:
    return name.translate(
        str.maketrans({"<": "C", ":": "A", ";": "B", "=": "D", ">": "E", "?": "F"})
    )


def diagnostics_allowed(name: str) -> bool:
    return not any(token in normalize_name(name).upper() for token in FAULT_HIDDEN_TOKENS)


def alarm_massage_allowed(name: str) -> bool:
    return "QMS2" not in normalize_name(name).upper()


def startup_schedule() -> list[tuple[int, bytes | None]]:
    """Offsets from notification setup, merging the app's independent workers."""
    return [
        (CLOCK_DELAY_MS, None),
        (LIGHT_QUERY_DELAY_MS, C.LIGHT_STATUS_QUERY),
        (SYNC_DELAY_MS, SYNC_QUERY),
        *(
            (PRESET_QUERY_DELAY_MS + i * PRESET_QUERY_SPACING_MS, frame)
            for i, frame in enumerate(C.QUERY_Q2)
        ),
    ]
