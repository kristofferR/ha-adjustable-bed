"""Dreamlab Control layout gestures on the shared Classic Richmat getters."""

from __future__ import annotations

from dataclasses import dataclass

from ...labels import display_label
from ..catalog_buttons import Kind, classify
from .caller import Selection, effective_status, selected_operand, short_operand
from .jerome_controls import label
from .profiles import Control
from .protocol import Wire, decode_resource


@dataclass(frozen=True, slots=True)
class Gesture:
    payload: bytes
    held: bool
    threshold_ms: int = 0
    release_ms: int | None = 150


def gesture(
    button: Control, layout: str, wire: Wire, selection: Selection, *, long: bool
) -> Gesture | None:
    """An immutable write plan for one admitted action."""
    if button.hold_affected:
        # The layout's initial statuses already describe Release. Only an
        # explicit Hold choice exposes its separate save buttons.
        if button.view_id.endswith("Long") and selection.hold is not True:
            return None
    elif any(value in ("gone", "invisible", "8", "4") for value in button.ancestor_visibility):
        return None
    status = effective_status(button, layout, selection)
    if long:
        if status != 3 or button.excluded_long or button.long is None:
            return None
        payload = decode_resource(button.long)
        if payload is None:
            return None
        if button.mem_special:
            return Gesture(payload, False, release_ms=50)
        has_short = short_operand(button, wire) is not None
        return Gesture(
            payload,
            False,
            button.threshold_ms,
            150 if has_short else 50 if wire == "FRAMED" else None,
        )
    if button.excluded_short:
        return None
    held = status == 1 or button.mem_special
    payload = selected_operand(button, wire, 1 if held else 2, selection)
    return (
        Gesture(payload, held, release_ms=50 if held else 150)
        if isinstance(payload, bytes)
        else None
    )


def action_name(button: Control, *, long: bool, raw: bool) -> str:
    if button.view_id in ("btnRelease", "btnHold") and button.short in ("21", "22"):
        return "Release mode" if button.short == "21" else "Hold mode"
    if button.tag in ("51", "52"):
        return "Selected motor up" if button.tag == "51" else "Selected motor down"
    if button.mem_special and long:
        return "Save " + label(button, raw=raw).lower()
    name = display_label(label(button, long=long, raw=raw))
    if long and not name.lower().startswith(("save ", "program ", "set ")):
        recall = classify(display_label(label(button, raw=raw)))
        if recall is not None and recall.kind in (Kind.PRESET, Kind.MEMORY):
            return "Save " + recall.name
        if name == display_label(label(button, raw=raw)) and button.short is not None:
            return f"{name} (long press)"
    return name or f"Control {button.node}"
