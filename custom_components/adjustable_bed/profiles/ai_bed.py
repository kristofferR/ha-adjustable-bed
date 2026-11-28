"""AI Bed 5.7.9 route data. All routes remain hardware unverified."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from ..codec import ai_bed, limoss, richmat
from ..execution import ExecutionCapabilities


@dataclass(frozen=True, slots=True)
class Action:
    label: str
    code: int
    parameters: tuple[int, ...] = ()
    motion: bool = False
    save: bool = False


@dataclass(frozen=True, slots=True)
class Profile:
    key: str
    codec: Literal["limoss", "richmat", "ai_bed"]
    refresh_ms: int
    actions: dict[str, Action]
    service: str
    write: str
    notify: str
    release_count: int = 0

    @property
    def execution(self) -> ExecutionCapabilities:
        if not self.actions:
            return ExecutionCapabilities()
        return ExecutionCapabilities(
            hold="stream",
            hold_controls=frozenset(
                key
                for key, action in self.actions.items()
                if action.motion or self.key == "limos" and not action.save
            ),
        )

    def encode(self, action: Action) -> bytes:
        if self.codec == "limoss":
            return limoss.frame(limoss.body(action.code), 1)
        if self.codec == "richmat":
            return richmat.command(action.code)
        return ai_bed.frame(action.code, action.parameters)


FFE0: Final = "0000ffe0-0000-1000-8000-00805f9b34fb"
FFE1: Final = "0000ffe1-0000-1000-8000-00805f9b34fb"
FEE9: Final = "0000fee9-0000-1000-8000-00805f9b34fb"
HJ_WRITE: Final = "d44bc439-abfd-45a2-b575-925416129600"
HJ_NOTIFY: Final = "d44bc439-abfd-45a2-b575-925416129601"

LIMOS_ACTIONS: Final = {
    "sleep_recall": Action("Sleep recall", 0x81, (), motion=False, save=False),
    "deep_recall": Action("Deep recall", 0x83, (), motion=False, save=False),
    "leisure_recall": Action("Leisure recall", 0x84, (), motion=False, save=False),
    "deep_program": Action("Deep program", 0x82, (), motion=False, save=True),
    "head_up": Action("Head up", 0x12, (), motion=True, save=False),
    "foot_up": Action("Foot up", 0x22, (), motion=True, save=False),
    "head_down": Action("Head down", 0x13, (), motion=True, save=False),
    "foot_down": Action("Foot down", 0x23, (), motion=True, save=False),
    "both_up": Action("Both up", 0x50, (), motion=True, save=False),
    "both_down": Action("Both down", 0x51, (), motion=True, save=False),
}

HJ001_ACTIONS: Final = {
    "recall_sleep": Action("Recall Sleep", 0x31, (), motion=False, save=False),
    "recall_leisure": Action("Recall Leisure", 0x2E, (), motion=False, save=False),
    "recall_relax": Action("Recall Relax", 0x45, (), motion=False, save=False),
    "recall_deep": Action("Recall Deep", 0x46, (), motion=False, save=False),
    "recall_sleep_aid": Action("Recall Sleep Aid", 0x2F, (), motion=False, save=False),
    "recall_decomp": Action("Recall Decomp", 0x30, (), motion=False, save=False),
    "program_leisure": Action("Program Leisure (id2)", 0x2B, (), motion=False, save=True),
    "program_relax": Action("Program Relax (id3)", 0x66, (), motion=False, save=True),
    "program_deep": Action("Program Deep (id4)", 0x69, (), motion=False, save=True),
    "program_sleep_aid": Action("Program Sleep Aid (id5)", 0x2C, (), motion=False, save=True),
    "program_decomp": Action("Program Decomp (id6)", 0x2D, (), motion=False, save=True),
    "both_rise": Action("Both Rise (id301)", 0x29, (), motion=True, save=False),
    "both_down": Action("Both Down (id302)", 0x2A, (), motion=True, save=False),
    "foot_rise": Action("Foot Rise (id201)", 0x26, (), motion=True, save=False),
    "foot_down": Action("Foot Down (id202)", 0x27, (), motion=True, save=False),
    "head_rise": Action("Head Rise (id101)", 0x24, (), motion=True, save=False),
    "head_down": Action("Head Down (id102)", 0x25, (), motion=True, save=False),
}

PRIMARY_ACTIONS: Final = {
    "both_down": Action("Both down", 0x8, (2, 0, 2, 0), motion=True, save=False),
    "foot_down": Action("Foot down", 0x8, (0, 0, 2, 0), motion=True, save=False),
    "head_down": Action("Head down", 0x8, (2, 0, 0, 0), motion=True, save=False),
    "both_up": Action("Both up", 0x8, (1, 0, 1, 0), motion=True, save=False),
    "foot_up": Action("Foot up", 0x8, (0, 0, 1, 0), motion=True, save=False),
    "head_up": Action("Head up", 0x8, (1, 0, 0, 0), motion=True, save=False),
    "wake_up_recall": Action("Wake-up recall", 0x14, (12, 0), motion=False, save=False),
    "leisure_program": Action("Leisure program", 0x14, (3, 0), motion=False, save=True),
    "leisure_recall": Action("Leisure recall", 0x14, (4, 0), motion=False, save=False),
    "relax_program": Action("Relax program", 0x14, (7, 0), motion=False, save=True),
    "relax_recall": Action("Relax recall", 0x14, (8, 0), motion=False, save=False),
    "sleep_aid_program": Action("Sleep Aid program", 0x14, (14, 0), motion=False, save=True),
    "sleep_aid_recall": Action("Sleep Aid recall", 0x14, (15, 0), motion=False, save=False),
    "deep_program": Action("Deep program", 0x14, (5, 0), motion=False, save=True),
    "deep_recall": Action("Deep recall", 0x14, (6, 0), motion=False, save=False),
    "sleep_recall": Action("Sleep recall", 0x14, (2, 0), motion=False, save=False),
}

PROFILES: Final = {
    "unselected": Profile("unselected", "ai_bed", 500, {}, FFE0, FFE1, FFE1),
    "limos": Profile("limos", "limoss", 100, LIMOS_ACTIONS, FFE0, FFE1, FFE1),
    "hj001": Profile("hj001", "richmat", 30, HJ001_ACTIONS, FEE9, HJ_WRITE, HJ_NOTIFY),
    "qrrm": Profile(
        "qrrm",
        "richmat",
        30,
        {k: v for k, v in HJ001_ACTIONS.items() if v.motion or k == "recall_sleep"},
        FEE9,
        HJ_WRITE,
        HJ_NOTIFY,
    ),
    "305": Profile("305", "ai_bed", 500, PRIMARY_ACTIONS, FFE0, FFE1, FFE1, 2),
}
ROUTE_CHOICES: Final = {
    "limos": "AI Bed: Limos",
    "qrrm": "AI Bed: QRRM (Sleep only)",
    "hj001": "AI Bed: HJ001/HJ010/HJ011",
    "305": "AI Bed: primary 305 (bounded subset)",
}


def candidate(name: str) -> bool:
    return any(
        value in name
        for value in (
            "limos",
            "QRRM",
            "MPE_HJ001",
            "MPE_HJ010",
            "MPE_HJ011",
            "MpeV3B-5",
            "MpeV3L-5",
            "MpeV3B-7",
            "MpeV3L-7",
            "MpeV3B-9",
            "MpeV3L-9",
        )
    )


def esp_name(name: str) -> bool:
    import re

    return re.sub(r"-M\d+$", "", name.strip().upper()).endswith("E")
