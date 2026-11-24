"""Maxprime gestures and countdown choices over the classic Richmat codec."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ...alarm import AlarmRequest
from ...errors import invalid
from ..catalog_buttons import Kind, classify
from ..richmat.labels import resource_label
from .caller import Selection, effective_status, selected_operand, short_operand, transition
from .profiles import Control
from .protocol import ALARM_WAKE_ACTIONS, HELD_RELEASE_MS, TAP_RELEASE_MS, Wire

ALARM_COMBINATIONS: Final = {
    0x58: (0x77, 0x7A, 0x7D),
    0x46: (0x78, 0x7B, 0x7E),
    0x45: (0x79, 0x7C, 0x7F),
    0x59: (0xAC, 0xAD, 0xAE),
    0x2E: (0x81, 0x82, 0x83),
    0x2F: (0xA6, 0xA7, 0xA8),
    0x30: (0xA9, 0xAA, 0xAB),
}
MASSAGE_ZONES: Final = {"both": 0x5D, "head": 0x4C, "feet": 0x4E}
_RELEASE_ONLY_LAYOUTS: Final = frozenset({"BRRM", "YFRM", "YGRM"})
_LABELS: Final = {
    "com_first_up_second_down": "Motor 1 up and motor 2 down",
    "com_second_up_first_down": "Motor 2 up and motor 1 down",
    "com_first_up_once": "Motor 1 up",
    "com_second_up_once": "Motor 2 up",
    "com_first_second_once_up": "Motors 1 and 2 up",
    "com_msg_aroma": "Aroma",
    "k_sync_on": "Enable synchronization",
    "k_sync_off": "Disable synchronization",
    "m4_set_pos": "Save M4",
}


@dataclass(frozen=True, slots=True)
class Gesture:
    """One intent, before choosing the current receiver's command format and mode."""

    node: int
    resource: str
    payload: bytes
    repeat: bool
    release_ms: int | None
    threshold_ms: int = 0
    confirm: bool = False
    axis_after: str | None = None

    @property
    def label(self) -> str:
        return _LABELS.get(self.resource) or resource_label(self.resource)

    @property
    def kind(self) -> Kind | None:
        if self.confirm and self.resource != "com_reset":
            return Kind.SAVE
        if self.resource == "com_msg_aroma":
            return Kind.EXTRA
        if self.resource.startswith(("k_motor", "com_motor")):
            return Kind.MOTOR
        return None


def gesture(
    button: Control,
    layout: str,
    wire: Wire,
    selection: Selection,
    *,
    long: bool,
) -> Gesture | None:
    """A reachable named press from the loaded getters and local selections."""
    if button.status not in (1, 2, 3, 5):
        return None
    if layout in _RELEASE_ONLY_LAYOUTS and button.view_id.endswith("Long") and not selection.hold:
        return None
    armed_memory = layout == "E3RM" and button.extra == "100"
    status = effective_status(button, layout, selection)
    if long:
        if status != 3 or not button.long or button.excluded_long:
            return None
        operand, field = 3, "press_long"
        threshold = 0 if armed_memory else button.threshold_ms
        # Raw long-only bindings have no UP frame. A held/armed recall
        # returns to mode 0; dual bindings finish in mode 4.
        release_ms = (
            HELD_RELEASE_MS
            if armed_memory
            else (HELD_RELEASE_MS if wire == "FRAMED" else None)
            if short_operand(button, wire) is None
            else TAP_RELEASE_MS
        )
    else:
        if button.excluded_short:
            return None
        if transition(button, layout, wire, selection, "DOWN", app="maxprime").local:
            return None
        if armed_memory:
            status = 1
        operand = 2 if status == 3 else status
        field = (
            "press_short_old" if wire == "RAW" and button.short_old is not None else "press_short"
        )
        threshold = 0
        release_ms = {1: HELD_RELEASE_MS, 2: TAP_RELEASE_MS, 3: TAP_RELEASE_MS, 5: None}[status]
    payload = selected_operand(button, wire, operand, selection)
    if not isinstance(payload, bytes):
        return None
    resource = button.resource_keys.get(field, "").removeprefix("@string/")
    if operand == 1 and button.tag in ("51", "52"):
        resource = "Selected motor up" if button.tag == "51" else "Selected motor down"
    elif operand == 1 and button.tag == "63":
        resource = button.resource_keys.get("press_short_old", "").removeprefix("@string/")
    if not resource:
        resource = button.label
    label = _LABELS.get(resource) or resource_label(resource)
    shape = classify(label)
    confirm = (
        resource in ("k_set_old", "com_set_old", "com_reset")
        or shape is not None
        and shape.kind is Kind.SAVE
    )
    axis_after = button.tag if layout == "U3RM" and button.tag in ("53", "54", "55") else None
    return Gesture(
        button.node,
        resource,
        payload,
        status == 1 and not confirm,
        release_ms,
        threshold,
        confirm,
        axis_after,
    )


def alarm_code(codes: frozenset[int], request: AlarmRequest) -> int:
    """Resolve the layout's exposed preset and zone, rejecting unbound combinations."""
    if not request.enabled:
        return 0
    choices = {action: code for code, action in ALARM_WAKE_ACTIONS.items() if code in codes}
    action = choices.get(request.wake_action)
    zone = None
    if request.massage or request.massage_zone is not None:
        zone = MASSAGE_ZONES.get(request.massage_zone or "both")
        if zone not in codes and not (zone == 0x5D and {0x4C, 0x4E} <= codes):
            raise invalid("maxprime_alarm")
    if action is not None and action in MASSAGE_ZONES.values():
        if zone is not None and zone != action:
            raise invalid("maxprime_alarm")
        return action
    if action is not None and zone is not None:
        if action not in ALARM_COMBINATIONS:
            raise invalid("maxprime_alarm")
        return ALARM_COMBINATIONS[action][tuple(MASSAGE_ZONES.values()).index(zone)]
    if action is not None and request.wake_action != "none":
        return action
    if request.wake_action == "none" and zone is not None:
        return zone
    raise invalid("maxprime_alarm")
