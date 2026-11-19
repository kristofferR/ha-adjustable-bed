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
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final

from ..card import (
    CARD_CLIMATE,
    CARD_LIGHTING,
    CARD_MASSAGE,
    CARD_PRESET_SAVE,
    CARD_PRESETS,
    CARD_UTILITY,
    CardPlacement,
    CardRole,
    CardSection,
    memory_card,
    motor_card,
)
from ..labels import display_label
from .entity_specs import ControllerButtonSpec, ControllerSwitchSpec, MotorCommandCallable

if TYPE_CHECKING:
    from .base import BedController


class Kind(StrEnum):
    """What a catalog control is."""

    MOTOR = "motor"
    PRESET = "preset"
    MEMORY = "memory"
    SAVE = "save"
    MASSAGE = "massage"
    LIGHT = "light"
    # Fans and cooling a catalog lists with the bed's controls.
    CLIMATE = "climate"
    # Anything else (music, resets, Bluetooth): available, off by default.
    EXTRA = "extra"


# Translation keys of the shared ``{action}`` shapes, one per placement.
EXTRA_KEY: Final = "catalog_action"
PRESET_KEY: Final = "catalog_preset"
SAVE_KEY: Final = "catalog_save"
MASSAGE_KEY: Final = "catalog_massage"
LIGHT_KEY: Final = "catalog_light"
CLIMATE_KEY: Final = "catalog_climate"

_CARDS: Final[dict[str, CardPlacement]] = {
    EXTRA_KEY: CARD_UTILITY,
    PRESET_KEY: CARD_PRESETS,
    SAVE_KEY: CARD_PRESET_SAVE,
    MASSAGE_KEY: CARD_MASSAGE,
    LIGHT_KEY: CARD_LIGHTING,
    CLIMATE_KEY: CARD_CLIMATE,
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
    "head tilt": "head_tilt",
    "headrest": "headrest",
    "head rest": "headrest",
    "mid-body": "mid_body",
    "t-flat": "t_flat",
    "m3 and m4": "motors_3_4",
    "main motor": "main_motor",
    "storage lift": "storage_lift",
    "extra": "extra",
    "upper section": "upper_section",
    "lower section": "lower_section",
    "lounge": "lounge",
    "zero gravity": "zero_gravity",
    "zero gravity motor": "zero_gravity",
    "lumbar and pillow": "lumbar_pillow",
    "pillow and lumbar tilt": "pillow_lumbar_tilt",
    "pillow 2": "pillow_2",
    **{f"motor {n}": f"motor_{n}" for n in range(1, 8)},
    **{f"control {n}": f"control_{n}" for n in range(1, 6)},
    "motor 1+2": "motors_1_2",
    "motor 2+3": "motors_2_3",
    "motor 3+4": "motors_3_4",
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
        (r"read(?:ing)?(?: position)?", "preset_reading"),
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
    r"(?P<lead>increase|decrease)?\s*(?:massage\s*)?(?P<zone>head|foot|feet|leg|all)?\s*"
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
    r"refresh|calibrate|clear|demonstration|beep|clock|smart sleep|adjustment)\b",
    re.IGNORECASE,
)
_CLOCK: Final = re.compile(r"\bclock\b", re.IGNORECASE)
# Both ends moving in opposite directions: a one-touch position, not a motor row.
_COMBO: Final = re.compile(
    r"(?:head|foot) (?:up|down)(?: and)? (?:head|foot) (?:up|down|stop)", re.IGNORECASE
)
_LIGHT_WORDS: Final = re.compile(r"\b(?:light|lights|lamp|night light)\b", re.IGNORECASE)
# An app's fixed-duration massage timer action, by the minutes it sets.
_MASSAGE_TIMER_ACTION: Final = re.compile(r"(?:deviceFunctionItem)?Massage(?P<minutes>\d+)MinuteTimer")


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
        return self.kind not in (Kind.EXTRA, Kind.CLIMATE)


def _shaped(kind: Kind, key: str, name: str) -> CatalogControl:
    return CatalogControl(kind, key, _CARDS[key], name, {"action": name})


def _preset(name: str) -> CatalogControl:
    for pattern, key in _PRESETS:
        if pattern.fullmatch(name):
            return CatalogControl(Kind.PRESET, key, CARD_PRESETS, name, None)
    return _shaped(Kind.PRESET, PRESET_KEY, name)


def _massage_key(name: str) -> str | None:
    """Return the shared massage description a label names, if any."""
    text = name.lower().replace("massage: ", "massage ")
    if text in ("massage on/off", "massage toggle", "toggle massage"):
        return "massage_all_toggle"
    if text in ("massage off", "massage mode all off", "stop massage", "massage all off"):
        return "massage_all_off"
    if text in ("massage mode change", "cycle massage mode", "massage mode"):
        return "massage_mode_step"
    if text in ("massage timer", "cycle massage timer"):
        return "massage_timer_step"
    match = _MASSAGE_ZONE.fullmatch(text)
    if match is None or "massage" not in text and "intensity" not in text:
        return None
    op = match["op"] or match["lead"]
    if op is None:
        return None
    zone = {"feet": "foot", "leg": "foot", None: "all"}.get(match["zone"], match["zone"])
    return f"massage_{zone}_{'up' if op in ('up', '+', 'add', 'increase', 'strengthen') else 'down'}"


def massage_timer_minutes(action: str) -> int | None:
    """The minutes an app's fixed-duration massage timer action sets, if it is one.

    Such actions are the bed's massage timer select, not buttons of their own.
    """
    match = _MASSAGE_TIMER_ACTION.fullmatch(action)
    return int(match["minutes"]) if match else None


def on_off_switch(
    key: str,
    translation_key: str,
    on: MotorCommandCallable,
    off: MotorCommandCallable,
    **kwargs: Any,
) -> ControllerSwitchSpec:
    """One switch for a feature's separate on and off controls.

    The bed reports neither, so the switch shows what it last sent.
    """

    async def set_fn(controller: BedController, enabled: bool) -> None:
        await (on if enabled else off)(controller)

    return ControllerSwitchSpec(key, translation_key, set_fn, **kwargs)


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
    save = _SAVE.fullmatch(name) if kind in (None, Kind.SAVE) else None
    if kind is Kind.SAVE or save is not None:
        rest = display_label(save["rest"]) if save is not None else re.sub(r"^Save\s+", "", name)
        if memory := _MEMORY.fullmatch(rest):
            slot = int(memory["slot"])
            return CatalogControl(
                Kind.SAVE, f"program_memory_{slot}", memory_card(slot, save=True), name, None
            )
        return CatalogControl(Kind.SAVE, SAVE_KEY, CARD_PRESET_SAVE, name, {"preset": rest})
    # A catalog's group can hold music, fans or resets: they stay extras.
    if (
        kind in (None, Kind.PRESET, Kind.MASSAGE, Kind.LIGHT)
        and _EXTRA_WORDS.search(name)
        and "massage" not in name.lower()
    ):
        return _shaped(Kind.EXTRA, EXTRA_KEY, name)
    if kind is None and _COMBO.fullmatch(name):
        return _shaped(Kind.PRESET, PRESET_KEY, name)
    if kind is Kind.CLIMATE:
        return _shaped(Kind.CLIMATE, CLIMATE_KEY, name)
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
    if (
        meaning is not None
        and control.kind is not Kind.SAVE
        and _EXTRA_WORDS.search(display_label(label))
        and "massage" not in label.lower()
    ):
        # The shown label names a fan, music or reset control the enum files elsewhere.
        control = _shaped(Kind.EXTRA, EXTRA_KEY, display_label(label))
    elif meaning is not None and control.placeholders is not None:
        name = display_label(label)
        placeholders = (
            {"preset": re.sub(r"^Save\s+", "", name)}
            if "preset" in control.placeholders
            else {"action": name}
        )
        control = CatalogControl(control.kind, control.translation_key, control.card, name, placeholders)
    if control.card == CARD_PRESET_SAVE:
        # The card confirms a tap; a held gesture would send the save unasked.
        kwargs.pop("hold", None)
    if control.kind is Kind.EXTRA and _CLOCK.search(control.name):
        # Setting the clock is maintenance until the shared sync_clock action covers it.
        kwargs.setdefault("diagnostic", True)
    return ControllerButtonSpec(
        key,
        label,
        press_fn,
        translation_key=control.translation_key,
        translation_placeholders=control.placeholders,
        card=control.card,
        # The card's Set mode guards a memory save; a preset save asks first.
        requires_confirmation=kwargs.pop("requires_confirmation", False)
        or control.card == CARD_PRESET_SAVE,
        entity_registry_enabled_default=kwargs.pop("enabled", True) and control.enabled,
        **kwargs,
    )


def save_button(
    key: str, label: str, press_fn: MotorCommandCallable, **kwargs: Any
) -> ControllerButtonSpec:
    """A catalog's save of a named preset (``label`` starts with "Save")."""
    spec = catalog_button(key, label, press_fn, kind=Kind.SAVE, **kwargs)
    assert spec is not None
    return spec


def massage_button(
    key: str, label: str, press_fn: MotorCommandCallable, **kwargs: Any
) -> ControllerButtonSpec:
    """A catalog's massage control."""
    spec = catalog_button(key, label, press_fn, kind=Kind.MASSAGE, **kwargs)
    assert spec is not None
    return spec


def unique_buttons(
    specs: Iterable[ControllerButtonSpec | None],
) -> tuple[ControllerButtonSpec, ...]:
    """Drop placeholders and repeated keys; tell same-named controls apart.

    A catalog can list one action twice, or two actions the shared description
    names the same way. The first keeps the shared shape; a later one keeps its
    own label in its kind's ``{action}`` shape, numbered when that name is taken.
    """
    result: list[ControllerButtonSpec] = []
    keys: set[str] = set()
    shared: set[str] = set()
    names: Counter[str] = Counter()
    for spec in specs:
        if spec is None or spec.key in keys:
            continue
        translation_key = spec.translation_key
        if spec.translation_placeholders is None and translation_key is not None:
            if translation_key in shared:
                spec = _own_label(spec)
            else:
                shared.add(translation_key)
        name = _shown_name(spec).casefold()
        names[name] += 1
        if names[name] > 1:
            spec = _numbered(spec, names[name])
        keys.add(spec.key)
        result.append(spec)
    return tuple(result)


def _shown_name(spec: ControllerButtonSpec) -> str:
    placeholders = spec.translation_placeholders or {}
    if "preset" in placeholders:
        return "Save " + display_label(placeholders["preset"])
    return display_label(placeholders.get("action", spec.name))


def _numbered(spec: ControllerButtonSpec, number: int) -> ControllerButtonSpec:
    if spec.translation_placeholders is None:
        spec = _own_label(spec)
    placeholders = dict(spec.translation_placeholders or {})
    field = "preset" if "preset" in placeholders else "action"
    placeholders[field] = f"{display_label(placeholders[field])} {number}"
    return replace(spec, translation_placeholders=placeholders)


def _own_label(spec: ControllerButtonSpec) -> ControllerButtonSpec:
    name = display_label(spec.name)
    key = {
        CardSection.PRESETS: PRESET_KEY,
        CardSection.MEMORY: PRESET_KEY,
        CardSection.MASSAGE: MASSAGE_KEY,
        CardSection.LIGHTING: LIGHT_KEY,
    }.get(spec.card.section, EXTRA_KEY)
    if spec.card.role is CardRole.SAVE:
        return replace(
            spec,
            translation_key=SAVE_KEY,
            translation_placeholders={"preset": re.sub(r"^Save\s+", "", name)},
            card=CARD_PRESET_SAVE,
        )
    return replace(
        spec, translation_key=key, translation_placeholders={"action": name}, card=_CARDS[key]
    )


def kind_of(spec: ControllerButtonSpec) -> Kind | None:
    """The kind a catalog spec was placed as, from its card placement."""
    card = spec.card
    if card == CARD_PRESET_SAVE or card.role is CardRole.SAVE:
        return Kind.SAVE
    return {
        CardSection.PRESETS: Kind.PRESET,
        CardSection.MEMORY: Kind.MEMORY,
        CardSection.MASSAGE: Kind.MASSAGE,
        CardSection.LIGHTING: Kind.LIGHT,
        CardSection.MOTORS: Kind.MOTOR,
    }.get(card.section)


# Preset keys whose plain name is not the key with spaces.
_PRESET_NAMES: Final = {
    "zero_g": "zero gravity",
    "zero_gravity": "zero gravity",
    "zg": "zero gravity",
    "anti_snore": "anti-snore",
    "anti_snore_preset": "anti-snore",
    "anti": "anti-snore",
    "snore": "anti-snore",
    "tv": "TV",
    "tv_pc": "TV position",
}


def save_name(preset: str) -> str:
    """The save button name for a bed's preset key: "Save zero gravity"."""
    key = preset.lower()
    return "Save " + _PRESET_NAMES.get(key, key.replace("_", " "))


def as_save(spec: ControllerButtonSpec) -> ControllerButtonSpec:
    """A bed's own save button (named "Save ..."), in the shared save shape."""
    reshaped = relabel(spec, spec.name, kind=Kind.SAVE)
    assert reshaped is not None
    # The card confirms a tap; a held gesture would send the save unasked.
    return replace(reshaped, hold=None)


def relabel(
    spec: ControllerButtonSpec, label: str, *, kind: Kind | None = None
) -> ControllerButtonSpec | None:
    """Give a catalog spec another label, reshaping it for what the label names."""
    if kind is None and _SAVE.fullmatch(display_label(label)):
        kind = Kind.SAVE
    control = classify(label, kind=kind if kind is not None else kind_of(spec))
    if control is None:
        return None
    return replace(
        spec,
        name=label,
        translation_key=control.translation_key,
        translation_placeholders=control.placeholders,
        card=control.card,
        requires_confirmation=control.card == CARD_PRESET_SAVE
        or spec.requires_confirmation and kind_of(spec) is not Kind.SAVE,
        entity_registry_enabled_default=spec.entity_registry_enabled_default and control.enabled,
    )
