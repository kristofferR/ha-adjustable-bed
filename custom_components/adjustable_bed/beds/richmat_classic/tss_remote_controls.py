"""TSS Remote's immutable gestures and labels, independent of BLE sessions."""

from dataclasses import replace

from ...profiles import tss_remote as app
from ..richmat.labels import resource_label
from .caller import Selection, nordic_label
from .dreamlab_controls import Gesture, action_name, gesture
from .profiles import Control
from .protocol import Wire


def plan(
    button: Control, layout: str, wire: Wire, selection: Selection, *, long: bool
) -> Gesture | None:
    if not button.rich_button or button.status not in (1, 2, 3):
        return None
    if button.tag in ("61", "62", "65") or (button.tag or "").lower() in {
        "b8tt",
        "b9tt",
        "zri0",
        "i4rm",
        "i5rm",
        "d7rm",
        "zr00",
        "zr01",
        "aprm",
        "aqrm",
    }:
        return None
    result = gesture(button, layout, wire, selection, long=long)
    if result is not None and long and button.excluded_short and button.short is not None:
        # Mixed audio/lock: the short operand exists. UP after its long action
        # owns the 150 ms END on both routes, without ever sending audio D9.
        return replace(result, release_ms=app.RUNTIME.tap_release_ms)
    if result is not None and result.release_ms is not None:
        return replace(
            result,
            release_ms=app.RUNTIME.held_release_ms
            if result.release_ms == 50
            else app.RUNTIME.tap_release_ms,
        )
    return result


def name(button: Control, layout: str, *, long: bool, raw: bool) -> str:
    asset = button.resource_keys.get("android:background", "").removeprefix("@drawable/")
    if not long and (not raw or nordic_label(button) is None):
        visible = (
            app.APPEARANCE_LABELS.get((layout, button.node))
            or app.CONTROL_LABELS.get(asset)
            or app.MOTION_LABELS.get(asset)
        )
        if visible:
            return visible
    key = button.resource_keys.get(
        "press_short_old" if raw and button.short_old is not None else "press_short", ""
    )
    if not long and "motor" in resource_label(key.removeprefix("@string/")).lower():
        return ""
    result = action_name(button, long=long, raw=raw)
    return "" if any(word in result.lower() for word in ("motor ", "control ", "code ")) else result
