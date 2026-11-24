"""Names and native Home Assistant shapes for Dorsal's catalog controls."""

import re

from ...alarm import WAKE_ACTIONS
from ...profiles.dorsal import Control
from ..catalog_buttons import Kind, classify
from ..richmat.labels import function_label

_LABELS = {
    "BedLight": "Toggle under-bed light",
    "BedLightClose": "Under-bed light off",
    "ControlBoxLock": "Controller lock on/off",
    "FootUpAndHeadDown": "Head down and foot up",
    "HeadUpAndFootDown": "Head up and foot down",
    "HeadUpAndFootStop": "Raise head and stop foot",
    "LumberMemoryPosition": "Lumbar position",
    "MassageModeAllOff": "Massage off",
    "MassageModeAllOn": "Massage on",
    "MassageSwitch": "Massage on/off",
    "MotorReset": "Flat",
    "MotorReset2": "Flat position 2",
    "RelieveSnoreSetting": "Anti-snore setting",
    "RelieveZeroGravitySetting": "Zero gravity setting",
    "WakeUp": "Wake up",
    "ZeroGravity2": "Zero gravity 2",
}
_COMPOUND_MOVES = {"FootUpAndHeadDown", "HeadUpAndFootDown", "HeadUpAndFootStop"}

_ACTIONS = {
    "TVPosition": "tv",
    "ZeroGravity": "zero_g",
    "AntiSnoring": "anti_snore",
    "LoungePosition": "lounge",
    "MassageHeadInstensityStrengthen": "head_massage",
    "MassageFootInstensityStrengthen": "foot_massage",
    "ReadingPosition": "reading",
    "DeepSleepPosition": "deep_sleep",
    "ZeroGravity2": "zero_g_2",
    "WakeUp": "wake_up",
    "MassageModeAllOn": "massage",
    "AlarmMode1": "wake_mode_1",
    "AlarmMode2": "wake_mode_2",
    "HelpGetUpPosition": "get_up",
    "MotorReset": "flat",
    "YogaPosition": "yoga",
    "AllMotorUp": "all_up",
    "AllMotorDown": "flat_reset",
    **{f"MemoryPosition{i}": f"memory_{i}" for i in range(1, 6)},
}


def action_name(action: str) -> str:
    return action.removeprefix("deviceFunctionItem").removeprefix("deviceFunctionSofa")


def label(control: Control) -> str:
    action = action_name(control.action)
    if control.key == "roomi_snore_trigger":
        return "Anti-snore trigger"
    return _LABELS.get(action) or function_label(control.action)


def kind(control: Control) -> Kind | None:
    name = action_name(control.action)
    if name in _COMPOUND_MOVES:
        return Kind.PRESET
    if name.startswith("Fan"):
        return Kind.CLIMATE
    if name.startswith(("Massage", "MusicShake", "deviceFunctionAirbag")):
        return Kind.MASSAGE
    if name.startswith("BedLight"):
        return Kind.LIGHT
    return None


def is_directional(control: Control) -> bool:
    if action_name(control.action) in _COMPOUND_MOVES:
        return True
    shape = classify(label(control), kind=kind(control))
    return shape is not None and shape.kind is Kind.MOTOR


def timer_minutes(control: Control) -> int | None:
    match = re.fullmatch(r"Massage(\d+)MinuteTimer", action_name(control.action))
    return int(match[1]) if match is not None else None


def massage_level(control: Control) -> tuple[str, int] | None:
    name = action_name(control.action)
    for zone in ("Head", "Foot"):
        if name == f"Massage{zone}Off":
            return zone.lower(), 0
        for level, ordinal in enumerate(("First", "Second", "Third"), start=1):
            if name == f"Massage{zone}Instens{ordinal}Mode":
                return zone.lower(), level
    for level, ordinal in enumerate(("First", "Second", "Third"), start=1):
        if name == f"MassageInstensity{ordinal}Gear":
            return "all", level
    return None


def wake_modes(modes: dict[str, int]) -> dict[str, int]:
    return {
        name: modes[action]
        for action in modes
        if (name := _ACTIONS.get(action_name(action))) in WAKE_ACTIONS
    }
