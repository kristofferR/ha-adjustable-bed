"""Super Colchones 1.0.2's explicit products and inverted GATT framing."""

from dataclasses import dataclass
from typing import Final

from ..codec import richmat as codec
from ..execution import STREAM_HOLD, ExecutionCapabilities


@dataclass(frozen=True, slots=True)
class Action:
    label: str
    code: int
    alternate: int | None = None


ACTIONS: Final = {
    "head_up": Action("Head up", 0x24),
    "head_down": Action("Head down", 0x25),
    "foot_up": Action("Foot up", 0x26),
    "foot_down": Action("Foot down", 0x27),
    "lumbar_up": Action("Lumbar up", 0x3F),
    "lumbar_down": Action("Lumbar down", 0x40),
    "flat": Action("Flat", 0x31),
    "light": Action("Bed light", 0x3C),
    "massage_head": Action("Massage head intensity strengthen", 0x4C),
    "massage_foot": Action("Massage foot intensity strengthen", 0x4E),
    "massage_mode": Action("Massage mode change", 0x48),
    "massage_off": Action("Massage mode all off", 0x5E),
    "timer_10": Action("Massage 10 minute timer", 0x5F),
    "timer_20": Action("Massage 20 minute timer", 0x63),
    "timer_30": Action("Massage 30 minute timer", 0x61),
    "anti_snore": Action("Anti-snore", 0x46, 0x69),
    "zero_gravity": Action("Zero Gravity", 0x45, 0x66),
    "memory_1": Action("Memory 1", 0x2E, 0x2B),
    "memory_2": Action("Memory 2", 0x2F, 0x2C),
    "sleep_assist": Action("Coaxing sleep mode", 0x86, 0x89),
}
DIRECTIONS: Final = tuple(key for key in ACTIONS if key.endswith(("_up", "_down")))
STARTUP: Final = (
    ("deviceFunctionItemExitLimit", 0),
    ("deviceFunctionItemCheckClock", 1),
    ("deviceFunctionItemCheckLight", 1),
)
TICK_S: Final = 0.1
LONG_PRESS_MS: Final = 3000
RESIDUAL_EXPIRY_S: Final = 0.5
# The source selects P1 on Nordic and P2 on every W route. This is the
# opposite of the codec transport's usual single-byte convention.
ROUTES: Final[tuple[codec.TransportKey, ...]] = ("n1", "w1", "w5", "w4", "w3", "w2")


@dataclass(frozen=True, slots=True)
class SuperColchonesProfile:
    key: str
    label: str
    metadata: str
    actions: tuple[str, ...]
    execution: ExecutionCapabilities = STREAM_HOLD

    def frame(self, code: int, *, raw: bool, action: str = "") -> bytes:
        return codec.function(code, single=raw, action=action)


PROFILES: Final = {
    "afeg302": SuperColchonesProfile(
        "afeg302", "AFEG302", "NLRN",
        ("head_up", "head_down", "foot_up", "foot_down", "flat", "massage_head",
         "anti_snore", "zero_gravity", "memory_1"),
    ),
    "afeg350": SuperColchonesProfile("afeg350", "AFEG350", "NMRN", tuple(ACTIONS)),
}
VARIANTS: Final = {key: profile.label for key, profile in PROFILES.items()}
