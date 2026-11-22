"""Typed local selections for Sleep Assistant 2.5.5, hardware unverified.

Server-assigned model fields are inputs, never a catalog inferred from names.
Empty selections promise only the app's unconditional head/feet and flat/Zero G.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from ..execution import STREAM_HOLD, ExecutionCapabilities

MODEL_KEYS: Final = {
    "o1": "Anti-snore",
    "o2": "Memory",
    "o3": "Relax",
    "o4": "TV",
    "o5": "One-button sleep",
}
MASSAGE_KEYS: Final = {
    "m1": "Massage timer",
    "m2": "Combined massage",
    "m3": "Head massage increase/decrease",
    "m4": "Feet massage increase/decrease",
    "m5": "Cycle head massage",
    "m6": "Cycle feet massage",
    "m7": "Tilt",
    "m8": "Lumbar",
}
WORDS: Final = {
    "head_up": 1,
    "head_down": 2,
    "feet_up": 4,
    "feet_down": 8,
    "tilt_up": 16,
    "tilt_down": 32,
    "lumbar_up": 64,
    "lumbar_down": 128,
    "zero_gravity": 4096,
    "flat": 134217728,
    "anti_snore_preset": 32768,
    "memory": 65536,
    "relax": 8192,
    "tv": 16384,
    "one_button_sleep": 1073741824,
    "massage_all": 256,
    "massage_timer_cycle": 512,
    "massage_feet_up": 1024,
    "massage_head_up": 2048,
    "massage_head_down": 8388608,
    "massage_feet_down": 16777216,
    "light_toggle": 131072,
    "stop": 0,
}
PRESET_ACTIONS: Final = dict(
    zip(MODEL_KEYS, ("anti_snore_preset", "memory", "relax", "tv", "one_button_sleep"), strict=True)
)
CONF_SLEEP_ASSISTANT_PRESETS: Final = "sleep_assistant_presets"
CONF_SLEEP_ASSISTANT_CONTROLS: Final = "sleep_assistant_controls"
CONF_SLEEP_ASSISTANT_LIGHTING: Final = "sleep_assistant_lighting"
CONF_SLEEP_ASSISTANT_PARAMETERS: Final = "sleep_assistant_parameters"
CONF_SLEEP_ASSISTANT_IDENTITY: Final = "sleep_assistant_identity"


def discovered(name: str) -> bool:
    return name.startswith("KSBT") and len(name) == 13


def visible_presets(tokens: tuple[str, ...], hw218: bool) -> tuple[str, ...]:
    """Mirror group/order admission, including the first-horizontal-slot quirk."""
    four = all(key in tokens for key in ("o1", "o2", "o3", "o4"))
    if not any(key in tokens for key in ("o1", "o2", "o3", "o4")):
        return ()
    slots = list(dict.fromkeys(tokens))[:4]
    if four:
        return tuple(slots)  # o5 changes first_h, outside the vertical group.
    hide_first = "o5" in slots and not hw218
    visible = slots[:3]
    return tuple(visible[1:] if hide_first else visible)


@dataclass(frozen=True, slots=True)
class SleepAssistantProfile:
    key: str = "sleep_assistant"
    execution: ExecutionCapabilities = STREAM_HOLD
    presets: tuple[str, ...] = ()
    controls: frozenset[str] = frozenset()
    lighting: str = "none"
    light: bool = False
    identity: str | None = None
    # Only supplied per-selected-model values. No app-auth/account fields.
    calibration: tuple[int, int, int, int] | None = None
    gain: int | None = None
    out_of_bed: tuple[str, str] | None = None
    anti_snore: tuple[int, int, int, int, int] | None = None
    anti_snore_levels: tuple[tuple[int, int, int, int, int], ...] = ()


def selected(data: Mapping[str, object]) -> SleepAssistantProfile:
    import json

    presets, controls = (
        data.get(CONF_SLEEP_ASSISTANT_PRESETS, []),
        data.get(CONF_SLEEP_ASSISTANT_CONTROLS, []),
    )
    if not isinstance(presets, list) or any(p not in MODEL_KEYS for p in presets):
        raise ValueError("Choose supported presets")
    if not isinstance(controls, list) or any(p not in MASSAGE_KEYS for p in controls):
        raise ValueError("Choose supported controls")
    lighting = data.get(CONF_SLEEP_ASSISTANT_LIGHTING, "none")
    if lighting not in ("none", "sleep8", "4193"):
        raise ValueError("Choose a lighting model")
    identity = data.get(CONF_SLEEP_ASSISTANT_IDENTITY, "")
    if (
        not isinstance(identity, str)
        or identity
        and (len(identity) != 8 or not identity.isascii() or not identity.isdecimal())
    ):
        raise ValueError("Use the selected device's eight decimal identity digits")
    text = data.get(CONF_SLEEP_ASSISTANT_PARAMETERS, "")
    if not isinstance(text, str):
        raise ValueError("Selected model settings must be text")
    values = json.loads(text) if text.strip() else {}
    if not isinstance(values, dict) or values.keys() - {
        "calibration",
        "gain",
        "out_of_bed",
        "anti_snore",
        "anti_snore_levels",
    }:
        raise ValueError("Only selected model bed settings are accepted")

    def numbers(key: str, maxima: tuple[int, ...]) -> tuple[int, ...] | None:
        value = values.get(key)
        if value is None:
            return None
        if (
            not isinstance(value, list)
            or len(value) != len(maxima)
            or any(
                type(v) is not int or not 0 <= v <= maximum
                for v, maximum in zip(value, maxima, strict=True)
            )
        ):
            raise ValueError(f"Invalid {key} settings")
        return tuple(value)

    calibration = numbers("calibration", (65535, 255, 65535, 255))
    anti = numbers("anti_snore", (3, 255, 255, 255, 255))
    levels = values.get("anti_snore_levels", [])
    if not isinstance(levels, list):
        raise ValueError("Invalid anti-snore levels")
    known_levels: list[tuple[int, int, int, int, int]] = []
    for level in levels:
        if (
            not isinstance(level, list)
            or len(level) != 5
            or any(
                type(v) is not int or not 0 <= v <= (3 if i == 0 else 255)
                for i, v in enumerate(level)
            )
            or level[0] == 0
        ):
            raise ValueError("Invalid anti-snore level settings")
        known_levels.append((level[0], level[1], level[2], level[3], level[4]))
    if len({level[0] for level in known_levels}) != len(known_levels):
        raise ValueError("Duplicate anti-snore level settings")
    if anti and any(level[0] == anti[0] and level != anti for level in known_levels):
        raise ValueError("Conflicting anti-snore level settings")
    gain = values.get("gain")
    if gain is not None and (type(gain) is not int or not 0 <= gain <= 255):
        raise ValueError("Invalid sensor gain")
    out = values.get("out_of_bed")
    if out is not None and (
        not isinstance(out, list)
        or len(out) != 2
        or any(
            not isinstance(v, str)
            or len(v) != 16
            or any(c not in "0123456789abcdefABCDEF" for c in v)
            for v in out
        )
    ):
        raise ValueError("Invalid out-of-bed settings")
    return SleepAssistantProfile(
        presets=tuple(presets),
        controls=frozenset(controls),
        lighting=str(lighting),
        light=data.get("has_light") is True,
        identity=identity or None,
        calibration=(calibration[0], calibration[1], calibration[2], calibration[3])
        if calibration
        else None,
        gain=gain,
        out_of_bed=(out[0], out[1]) if out else None,
        anti_snore=(anti[0], anti[1], anti[2], anti[3], anti[4]) if anti else None,
        anti_snore_levels=tuple(known_levels),
    )
