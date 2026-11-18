"""One entity shape for every button an app catalog or remote layout names.

Catalog families build a button for each action an app or remote shows. The
label stays the evidence; this module decides what the control is from it: a
motor's up or down beside its row, a preset tile, a memory slot, a confirmed
save, a massage or light control, or an extra that starts disabled. A control
that is the same thing on every bed reuses the shared description, so it gets
the same name and card placement everywhere. Only the entity shape changes:
keys, unique IDs and the bytes a press sends stay with the caller.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from ..card import (
    CARD_LIGHTING,
    CARD_MASSAGE,
    CARD_PRESET_SAVE,
    CARD_PRESETS,
    CARD_UTILITY,
    CardPlacement,
    CardRole,
    memory_card,
    motor_card,
)
from ..labels import display_label
from .entity_specs import ControllerButtonSpec, MotorCommandCallable


class Kind(StrEnum):
    """What a catalog control is."""

    MOTOR = "motor"
    PRESET = "preset"
    MEMORY = "memory"
    SAVE = "save"
    MASSAGE = "massage"
    LIGHT = "light"
    # Anything else (music, fans, resets, Bluetooth): available, off by default.
    EXTRA = "extra"


# Translation keys of the shared ``{action}`` shapes, one per placement.
EXTRA_KEY: Final = "catalog_action"
PRESET_KEY: Final = "catalog_preset"
SAVE_KEY: Final = "catalog_save"
MASSAGE_KEY: Final = "catalog_massage"
LIGHT_KEY: Final = "catalog_light"

_CARDS: Final[dict[str, CardPlacement]] = {
    EXTRA_KEY: CARD_UTILITY,
    PRESET_KEY: CARD_PRESETS,
    SAVE_KEY: CARD_PRESET_SAVE,
    MASSAGE_KEY: CARD_MASSAGE,
    LIGHT_KEY: CARD_LIGHTING,
}

# Labels a catalog uses for an empty slot or a menu heading, not a control.
_PLACEHOLDER: Final = re.compile(r"(?:no action|menu|.* menu|logo)", re.IGNORECASE)

# The motor a "<part> up/down" label moves, as its shared cover key.
_MOTORS: Final[dict[str, str]] = {
    "head": "head",
    "back": "back",
    "backrest": "back",
    "foot": "feet",
    "feet": "feet",
    "leg": "legs",
    "legs": "legs",
    "lumbar": "lumbar",
    "pillow": "pillow",
    "neck": "neck",
    "tilt": "tilt",
    "hip": "hip",
    "waist": "waist",
    "head and foot": "head_feet",
    "head and feet": "head_feet",
    "head and foot all": "head_feet",
    "back and legs": "both",
    "back and foot": "both",
    "all motor": "all_motors",
    "all motors": "all_motors",
    "whole bed": "all_motors",
    "bed height": "bed_height",
}
_MOTOR: Final = re.compile(r"(?P<part>.+?)\s+(?P<dir>up|down)", re.IGNORECASE)

# Presets every bed names the same way, as their shared description.
_PRESETS: Final[tuple[tuple[re.Pattern[str], str], ...]] = tuple(
    (re.compile(pattern, re.IGNORECASE), key)
    for pattern, key in (
        (r"flat", "preset_flat"),
        (r"zero g(?:ravity)?(?: position)?", "preset_zero_g"),
        (r"tv(?: position)?", "preset_tv"),
        (r"lounge(?: position)?", "preset_lounge"),
        (r"anti-snore(?: position)?", "preset_anti_snore"),
        (r"reading(?: position)?", "preset_reading"),
        (r"yoga", "preset_yoga"),
        (r"incline", "preset_incline"),
    )
)
# Other named positions an app recalls.
_PRESET_WORDS: Final = re.compile(
    r"\b(?:position|posture|flat|zero g(?:ravity)?|tv|lounge|anti-snore|reading|read|yoga|incline|"
    r"sleep aid|relax|leisure|recline|unwind|sit|chair|night|home|wake up|deep sleep|"
    r"side sleep|stretch|comfort-g|space mode|get-up assist|movie|sleep)\b",
    re.IGNORECASE,
)
_MEMORY: Final = re.compile(
    r"(?:memory(?: position| mode)?|mem|m|memory level)\s*(?P<slot>[1-9])", re.IGNORECASE
)
_SAVE: Final = re.compile(r"(?:save|program|set)\s+(?:to\s+)?(?P<rest>.+)", re.IGNORECASE)

# Massage controls every bed names the same way, as their shared description.
_MASSAGE_ZONE: Final = re.compile(
    r"(?:increase|decrease|massage)?\s*(?P<zone>head|foot|feet|leg|all)?\s*"
    r"(?:massage|massager)?\s*(?:intensity|strength)?\s*"
    r"(?P<op>up|down|\+|-|add|increase|decrease|strengthen|weaken)?",
    re.IGNORECASE,
)
_MASSAGE_WORDS: Final = re.compile(
    r"\b(?:massage|massager|vibration mode|wave|pulse|kneading|circulation|airbag)\b",
    re.IGNORECASE,
)
# Controls that are none of the shared kinds even when they name one.
_EXTRA_WORDS: Final = re.compile(
    r"\b(?:fan|fans|music|heat|heating|bluetooth|volume|aromatherapy|lock|sync|reset|usb|"
    r"refresh|calibrate|clear|demonstration|beep|clock)\b",
    re.IGNORECASE,
)
# Both ends moving in opposite directions: a one-touch position, not a motor row.
_COMBO: Final = re.compile(
    r"(?:head|foot) (?:up|down)(?: and)? (?:head|foot) (?:up|down|stop)", re.IGNORECASE
)
_LIGHT_WORDS: Final = re.compile(r"\b(?:light|lights|lamp|night light)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class CatalogControl:
    """The shared shape a catalog label maps onto."""

    kind: Kind
    translation_key: str
    card: CardPlacement
    name: str
    placeholders: Mapping[str, str] | None

    @property
    def enabled(self) -> bool:
        return self.kind is not Kind.EXTRA


def _shaped(kind: Kind, key: str, name: str) -> CatalogControl:
    return CatalogControl(kind, key, _CARDS[key], name, {"action": name})


def _preset(name: str) -> CatalogControl:
    for pattern, key in _PRESETS:
        if pattern.fullmatch(name):
            return CatalogControl(Kind.PRESET, key, CARD_PRESETS, name, None)
    return _shaped(Kind.PRESET, PRESET_KEY, name)


def _massage_key(name: str) -> str | None:
    """Return the shared massage description a label names, if any."""
    text = name.lower()
    if text in ("massage on/off", "massage toggle"):
        return "massage_all_toggle"
    if text in ("massage off", "massage mode all off", "stop massage", "massage all off"):
        return "massage_all_off"
    if text in ("massage mode change", "cycle massage mode", "massage mode"):
        return "massage_mode_step"
    if text in ("massage timer", "cycle massage timer"):
        return "massage_timer_step"
    match = _MASSAGE_ZONE.fullmatch(text)
    if match is None or match["op"] is None or "massage" not in text and "intensity" not in text:
        return None
    zone = {"feet": "foot", "leg": "foot", None: "all"}.get(match["zone"], match["zone"])
    up = match["op"] in ("up", "+", "add", "increase", "strengthen")
    if text.startswith("decrease"):
        up = False
    return f"massage_{zone}_{'up' if up else 'down'}"


def is_placeholder(label: str) -> bool:
    """Whether a catalog label names an empty slot or a menu heading, not a control."""
    name = display_label(label)
    return not name or _PLACEHOLDER.fullmatch(name) is not None


def classify(label: str, *, kind: Kind | None = None) -> CatalogControl | None:
    """Return the shape a catalog label maps onto, or None for a placeholder slot.

    ``kind`` overrides the guess where a catalog states what the control is.
    """
    if is_placeholder(label):
        return None
    name = display_label(label)
    if kind is Kind.SAVE or kind is None and (save := _SAVE.fullmatch(name)):
        rest = display_label(save["rest"]) if kind is None else re.sub(r"^Save\s+", "", name)
        if memory := _MEMORY.fullmatch(rest):
            slot = int(memory["slot"])
            return CatalogControl(
                Kind.SAVE, f"program_memory_{slot}", memory_card(slot, save=True), name, None
            )
        return CatalogControl(Kind.SAVE, SAVE_KEY, CARD_PRESET_SAVE, name, {"preset": rest})
    if kind is None and _EXTRA_WORDS.search(name) and "massage" not in name.lower():
        return _shaped(Kind.EXTRA, EXTRA_KEY, name)
    if kind is None and _COMBO.fullmatch(name):
        return _shaped(Kind.PRESET, PRESET_KEY, name)
    if kind in (None, Kind.MEMORY) and (memory := _MEMORY.fullmatch(name)):
        slot = int(memory["slot"])
        return CatalogControl(Kind.MEMORY, f"preset_memory_{slot}", memory_card(slot), name, None)
    if kind in (None, Kind.MOTOR) and (motor := _MOTOR.fullmatch(name)):
        if (key := _MOTORS.get(motor["part"].lower())) is not None:
            role = CardRole.UP if motor["dir"].lower() == "up" else CardRole.DOWN
            return CatalogControl(
                Kind.MOTOR, f"{key}_{role.value}", motor_card(key, role), name, None
            )
    if kind is Kind.MOTOR:
        return _shaped(Kind.MOTOR, EXTRA_KEY, name)
    if kind in (None, Kind.MASSAGE) and (
        kind is Kind.MASSAGE or _MASSAGE_WORDS.search(name)
    ):
        if (key := _massage_key(name)) is not None:
            return CatalogControl(Kind.MASSAGE, key, CARD_MASSAGE, name, None)
        return _shaped(Kind.MASSAGE, MASSAGE_KEY, name)
    if kind in (None, Kind.LIGHT) and (kind is Kind.LIGHT or _LIGHT_WORDS.search(name)):
        return _shaped(Kind.LIGHT, LIGHT_KEY, name)
    if kind in (None, Kind.PRESET) and (kind is Kind.PRESET or _PRESET_WORDS.search(name)):
        return _preset(name)
    return _shaped(Kind.EXTRA, EXTRA_KEY, name)


def catalog_button(
    key: str,
    label: str,
    press_fn: MotorCommandCallable,
    *,
    kind: Kind | None = None,
    meaning: str | None = None,
    **kwargs: Any,
) -> ControllerButtonSpec | None:
    """Build the button a catalog action is, or None for a placeholder slot.

    ``meaning`` is the catalog's own name for the control (an app enum) when
    ``label`` is a terse or translated screen label: it decides the shape, and
    ``label`` stays the name unless the shared description names it.
    """
    control = classify(meaning if meaning is not None else label, kind=kind)
    if control is None:
        return None
    if meaning is not None and control.placeholders is not None:
        name = display_label(label)
        placeholders = (
            {"preset": re.sub(r"^Save\s+", "", name)}
            if "preset" in control.placeholders
            else {"action": name}
        )
        control = CatalogControl(control.kind, control.translation_key, control.card, name, placeholders)
    return ControllerButtonSpec(
        key,
        label,
        press_fn,
        translation_key=control.translation_key,
        translation_placeholders=control.placeholders,
        card=control.card,
        requires_confirmation=kwargs.pop("requires_confirmation", False)
        or control.kind is Kind.SAVE,
        entity_registry_enabled_default=control.enabled,
        **kwargs,
    )


def unique_buttons(
    specs: Iterable[ControllerButtonSpec | None],
) -> tuple[ControllerButtonSpec, ...]:
    """Drop placeholders, repeated keys, and repeats of a shared description.

    A catalog can list one action twice, or two actions the shared description
    names the same way. The first keeps the shared shape; a later one with a
    different label keeps its own label in its kind's ``{action}`` shape.
    """
    result: list[ControllerButtonSpec] = []
    keys: set[str] = set()
    shared: set[str] = set()
    for spec in specs:
        if spec is None or spec.key in keys:
            continue
        translation_key = spec.translation_key
        if spec.translation_placeholders is None and translation_key is not None:
            if translation_key in shared:
                spec = _own_label(spec)
            else:
                shared.add(translation_key)
        keys.add(spec.key)
        result.append(spec)
    return tuple(result)


def _own_label(spec: ControllerButtonSpec) -> ControllerButtonSpec:
    from dataclasses import replace

    name = display_label(spec.name)
    key = {
        CARD_PRESETS: PRESET_KEY,
        CARD_MASSAGE: MASSAGE_KEY,
        CARD_PRESET_SAVE: SAVE_KEY,
    }.get(spec.card, EXTRA_KEY)
    if key == SAVE_KEY:
        return replace(
            spec,
            translation_key=key,
            translation_placeholders={"preset": re.sub(r"^Save\s+", "", name)},
            card=CARD_PRESET_SAVE,
        )
    return replace(
        spec, translation_key=key, translation_placeholders={"action": name}, card=_CARDS[key]
    )

