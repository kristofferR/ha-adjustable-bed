"""Layout-owned Jerome controls, without Android's transient screen selectors."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from ..richmat.labels import resource_label
from .caller import Selection, selected_operand, transition
from .profiles import Control, load_catalog


@dataclass(frozen=True, slots=True)
class Action:
    name: str
    node: int
    long_press: bool = False
    keep: bool = False
    flag: str = "53"


def excluded(button: Control) -> bool:
    """Phone/audio controls are outside the bed integration, even over BLE."""
    return button.resource_keys.get("android:background") == "@drawable/sel_cir_ble_on_off" or any(
        word in " ".join(button.resource_keys.values()).lower()
        for word in ("music", "volume", "song", "sound", "play", "pause")
    )


def label(button: Control, *, long: bool = False) -> str:
    background = button.resource_keys.get("android:background", "")
    if not long:
        if button.tag == "63":
            return {
                "@drawable/sel_rec_plus": "Head up",
                "@drawable/sel_rec_minus": "Head down",
                "@drawable/sel_rec_pos_up": "Head position up",
                "@drawable/sel_rec_pos_down": "Head position down",
                "@drawable/sel_rec_off2": "Head off",
            }.get(background, "")
        if button.short is None and button.short_old is not None:
            visible = {
                "@drawable/sel_rec_tv7": "TV",
                "@drawable/sel_rec_lounge6": "Lounge",
                "@drawable/sel_rec_zg6": "Zero Gravity",
                "@drawable/sel_rec_flat9": "Flat",
                "@drawable/sel_rec_ubl3": "Toggle underbed light",
            }.get(background)
            if visible:
                return visible
        # Some layouts reuse a timer resource on a separately labelled control.
        # Preserve the visible role while keeping that widget's exact getter.
        if background == "@drawable/sel_rec_pos1":
            return "Position 1"
        if (
            button.short_old is not None
            and button.resource_keys.get("press_short") == "@string/com_msg_10min"
        ):
            if background == "@drawable/sel_rec_msg_on":
                return "Start massage"
            if background in ("@drawable/sel_rec_msg_off", "@drawable/sel_rec_msg_off7"):
                return "Massage off"
            if background == "@drawable/sel_rec_msg_off4":
                return "Head massage down"
    key = button.resource_keys.get("press_long" if long else "press_short")
    key = key or button.resource_keys.get("press_short_old")
    if key is None:
        return ""
    name = resource_label(key.removeprefix("@string/"))
    names = {
        "Motor 1 up": "Head up",
        "Motor 1 down": "Head down",
        "Motor 2 up": "Foot up",
        "Motor 2 down": "Foot down",
        "Motor 1+2 up": "Head and foot up",
        "Motor 1+2 down": "Head and foot down",
        "Motor 1 up 2 down": "Head up and foot down",
        "Motor 2 up 1 down": "Foot up and head down",
        "Motor 1 up once": "Raise head",
        "Motor 2 up once": "Raise foot",
        "Motor 1+2 once up": "Raise head and foot",
        "Massage 1 intensity up": "Cycle head massage",
        "Massage 2 intensity up": "Cycle foot massage",
        "Massage 1 intensity down": "Head massage down",
        "Massage 2 intensity down": "Foot massage down",
        "Massage intensity up": "Cycle massage intensity",
        "Massage 1 on/off": "Toggle head massage",
        "Massage 2 on/off": "Toggle foot massage",
        "Massage on/off": "Toggle massage",
        "Underbed light on/off": "Toggle underbed light",
        "Massage off 2": "Massage off",
        "Massage off 3": "Massage off",
        "Sync on": "Synchronization on",
        "Sync off": "Synchronization off",
    }
    return names.get(name, name)


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


@lru_cache(maxsize=532)
def actions(layout: str) -> dict[str, Action]:
    """Keep every live gesture; deduplicate equal user labels on one layout.

    Long gestures are explicit, so saving never joins a renewable hold.
    Hidden dedicated save widgets offer the same named save without UI arming.
    """
    result: dict[str, Action] = {}
    for button in load_catalog("jerome2").models[layout].controls:
        if button.status not in (1, 2, 3) or excluded(button):
            continue
        hidden = any(v in ("gone", "invisible", "8", "4") for v in button.ancestor_visibility)
        if hidden and not button.hold_affected:
            continue
        if transition(button, layout, "FRAMED", Selection(), "DOWN", app="jerome2").local:
            continue
        for save in (False, True):
            if save and (button.status != 3 or button.long is None):
                continue
            name = label(button, long=save)
            if not name:
                continue
            # A long-only control has no meaningful short action.
            if not save and not any(
                isinstance(
                    selected_operand(
                        button, wire, button.status if button.status == 1 else 2, Selection()
                    ),
                    bytes,
                )
                for wire in ("RAW", "FRAMED")
            ):
                continue
            if save and button.short == button.long:
                continue
            saving = save or name.startswith("Save ")
            action = Action(
                name, button.node, save, button.status == 1 or button.mem_special and not save
            )
            key = slug(name)
            previous = result.get(key)
            # Prefer the explicitly exposed dedicated save, which needs no long wait.
            if previous is None or saving and not save:
                result[key] = action
    if layout == "U3RM":
        model = load_catalog("jerome2").models[layout]
        for button in model.controls:
            if button.tag not in ("51", "52"):
                continue
            for name, flag in (
                ("Zero Gravity", "54"),
                ("TV", "54"),
                ("Lounge", "55"),
                ("Zero Gravity 2", "53"),
                ("Anti-snore", "54"),
            ):
                title = f"{name} {'up' if button.tag == '51' else 'down'}"
                result[slug(title)] = Action(title, button.node, keep=True, flag=flag)
    return result


def inverse_pairs(layout: str) -> dict[str, tuple[str, str]]:
    available = actions(layout)
    return {
        slug(name): (on, off)
        for name, on, off in (
            ("Massage", "massage_on", "massage_off"),
            ("Synchronization", "synchronization_on", "synchronization_off"),
        )
        if on in available
        and off in available
        and not any(
            c.resource_keys.get("press_short") == "@string/com_msg_10min"
            and c.node in (available[on].node, available[off].node)
            for c in load_catalog("jerome2").models[layout].controls
        )
    }


@lru_cache(maxsize=532)
def long_actions(layout: str) -> dict[str, Action]:
    """The explicit long gesture, including saves also offered as a tap."""
    return {
        slug(label(c, long=True)): Action(label(c, long=True), c.node, long_press=True)
        for c in load_catalog("jerome2").models[layout].controls
        if c.status == 3
        and c.long is not None
        and not excluded(c)
        and not any(v in ("gone", "invisible", "8", "4") for v in c.ancestor_visibility)
        and label(c, long=True)
    }
