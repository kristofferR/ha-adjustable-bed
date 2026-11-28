"""Sven & Son 1.0.4: explicit models over the Richmat command encoder."""

from dataclasses import dataclass
from typing import Final

from ..execution import STREAM_HOLD
from .richmat import Button, Recall, RichmatProfile

PREFIXES: Final = ("QRRM", "QJ-", "LW-", "QR-")
REFRESH_MS: Final = 50
TAP_MS: Final = 100
HOLD_LIMIT_MS: Final = 30000
SAVE_THRESHOLD_MS: Final = 2000
MASSAGE_LIMIT_S: Final = 1800
MASSAGE_REST_S: Final = 600
TIMER_OPTIONS: Final = (10, 20, 30)
TARGETS: Final = (
    ("0000fee9-0000-1000-8000-00805f9b34fb", "d44bc439-abfd-45a2-b575-925416129600"),
    ("8ebd4f76-da9d-4b5a-a96e-8ebfbeb622e7", "d44bc439-abfd-45a2-b575-925416129600"),
    ("0000fee9-0000-1000-8000-00805f9b34bb", "d44bc439-abfd-45a2-b575-925416129622"),
    ("0000fff0-0000-1000-8000-00805f9b34fb", "0000fff2-0000-1000-8000-00805f9b34fb"),
    ("0000ffe0-0000-1000-8000-00805f9b34fb", "0000ffe2-0000-1000-8000-00805f9b34fb"),
)
EXCLUDED_SERVICES: Final = ("00001800", "00001801", "0000180a")


@dataclass(frozen=True, slots=True)
class Model:
    label: str
    axes: tuple[str, ...]
    profile: RichmatProfile


MODELS: Final = {
    key: Model(
        label,
        axes,
        RichmatProfile(
            key=f"sven:{key}",
            transports=(),
            execution=STREAM_HOLD,
            motor_repeat_ms=REFRESH_MS,
            recall=Recall(release=True),
            codes={
                "head_up": 0x24,
                "head_down": 0x25,
                "feet_up": 0x26,
                "feet_down": 0x27,
                "flat": 0x31,
                "zero_g": 0x45,
                "anti_snore": 0x46,
                "tv": 0x58,
                "massage_head": 0x4C,
                "massage_foot": 0x4E,
                "massage_mode": 0x48,
                **({"light_toggle": 0x3C} if key != "unknown" else {}),
                **({"pillow_up": 0x41, "pillow_down": 0x42} if "pillow" in axes else {}),
                **({"lumbar_up": 0x3F, "lumbar_down": 0x40} if "lumbar" in axes else {}),
            },
            memory=((0x2E, 0x2B), (0x2F, 0x2C)),
        ),
    )
    for key, label, axes in (
        ("classic", "Classic (200S)", ("back", "legs")),
        ("harmony", "Harmony (300S)", ("back", "legs", "pillow")),
        ("bliss", "Bliss (400S)", ("back", "legs", "pillow", "lumbar")),
        ("platinum", "Platinum (500S)", ("back", "legs", "pillow", "lumbar")),
        ("unknown", "Not sure (head and foot only)", ("back", "legs")),
    )
}
CHOICES: Final = {key: model.label for key, model in MODELS.items()}
MOTOR_BUTTONS: Final[dict[str, tuple[Button, Button]]] = {
    "back": ("head_up", "head_down"),
    "legs": ("feet_up", "feet_down"),
    "pillow": ("pillow_up", "pillow_down"),
    "lumbar": ("lumbar_up", "lumbar_down"),
}
PRESETS: Final = {0x31: "Flat", 0x45: "Zero gravity", 0x46: "Anti-snore", 0x58: "TV"}
POSITION_COMMANDS: Final = (
    frozenset(PRESETS)
    | {
        code
        for model in MODELS.values()
        for key, code in (model.profile.codes or {}).items()
        if key.endswith(("_up", "_down"))
    }
    | {recall for recall, _save in MODELS["classic"].profile.memory}
)


def admits(name: str | None, local_name: str | None = None) -> bool:
    """The app uses name OR localName, with case-sensitive prefix admission."""
    return (name or local_name or "").startswith(PREFIXES)


def model_key(value: object) -> str:
    """Normalize source model/name/series aliases, retaining conservative fallback."""
    text = value.strip().lower() if isinstance(value, str) else ""
    for key, model in MODELS.items():
        if text in (
            key,
            model.label.lower(),
            model.label.rsplit("(", 1)[-1].removesuffix(")").lower(),
        ):
            return key
        if key != "unknown" and text.startswith((key + " ", key + "-")):
            return key
    return "unknown"
