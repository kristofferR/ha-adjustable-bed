"""Flexispot's model catalog and exact BLE encoders."""

from custom_components.adjustable_bed.codec import flexispot as codec
from custom_components.adjustable_bed.profiles import flexispot as app
from custom_components.adjustable_bed.profiles import ghostbed as ghost

from ._common import Block, _block, _hex, _table

GUIDE = "docs/beds/flexispot.md"


def bed_types() -> dict[str, tuple[str, ...]]:
    return {**dict.fromkeys(app.PROFILES, ("flexispot",)), "ghostbed": ("ghostbed",)}


def profiles() -> str:
    return _block(
        _table(
            ("Profile", "Model", "Motors (wire key)", "Programmable presets", "Light"),
            (
                (
                    key,
                    profile.label,
                    ", ".join(f"{axis}: `{motor:02X}`" for axis, motor in profile.motors),
                    ", ".join(f"{name}: `{value:02X}`" for name, value in profile.memories),
                    "Yes" if profile.light else "No",
                )
                for key, profile in {**app.PROFILES, "ghostbed": ghost.PROFILE}.items()
            ),
        ),
        f"Movement refresh: {app.REFRESH_MS} ms; release delay: {app.RELEASE_MS} ms; "
        f"relative massage step: {app.MASSAGE_STEP_MS} ms. The app saves after a {app.SAVE_HOLD_MS} ms press; Home Assistant uses confirmed save actions. "
        "Flexispot startup subscribes to notifications and sends no query or authentication frame. GhostBed timing and clock startup are listed in its profile section.",
    )


def transports() -> str:
    return _block(
        _table(("Service", "Write", "Notify"), ((codec.SERVICE, codec.WRITE, codec.NOTIFY),))
    )


def commands() -> str:
    rows = []
    for profile in app.PROFILES.values():
        for axis, key in profile.motors:
            for label, op in (("up", 1), ("down", 2), ("stop", 3)):
                rows.append((profile.label, f"{axis} {label}", _hex(codec.frame(op, key))))
        for side, mask in (("left", 0), ("right", 128)) if profile.split else (("", 0),):
            rows.extend(
                (profile.label, f"{side} {name}".strip(), _hex(codec.frame(op, key | mask)))
                for name, key in (("flat", 2), ("zero_g", 5), *profile.memories)
                for op in ((5,) if name == "flat" else (7,))
            )
            rows.extend(
                (
                    profile.label,
                    f"Save {side} {name}".replace("  ", " "),
                    _hex(codec.frame(6, key | mask)),
                )
                for name, key in profile.memories
            )
    rows.extend(
        ("All", label, _hex(codec.frame(op, key)))
        for label, op, key in (
            ("Restore original settings", 5, 10),
            ("Massage on", 14, 1),
            ("Massage off", 14, 0),
            ("Upper/left massage increase", 12, 0),
            ("Upper/left massage decrease", 18, 0),
            ("Feet massage increase", 17, 0),
            ("Feet massage decrease", 13, 0),
        )
    )
    rows.extend(
        ("V3", label, _hex(codec.frame(op, 128)))
        for label, op in (("Right massage increase", 12), ("Right massage decrease", 18))
    )
    rows.extend(
        ("Light models", f"Light {'on' if key == 1 else 'off'}", _hex(codec.frame(4, key)))
        for key in (1, 2)
    )
    rows.extend(
        ("All", f"Massage pattern {index + 1} (V3: {mode})", _hex(codec.frame(16, index)))
        for index, mode in enumerate(app.MODES)
    )
    return _block(
        _table(("Model", "Action", "Frame"), rows),
        "Massage timer: `frame(0F, minutes)` with 0–59 on EB632/703/704, 0–60 on EB803. "
        "Snore: `frame(35, mask, {4: angle_pair*16+sensitivity_pair})`. "
        "Alarm: `frame(34, key, {4..11: both slot records}, num=edited_slot)`.",
    )


BLOCKS: list[Block] = [
    (GUIDE, f"flexispot-{name}", renderer)
    for name, renderer in (
        ("profiles", profiles),
        ("transports", transports),
        ("commands", commands),
    )
]


def ghostbed_commands() -> str:
    rows = []
    for axis, key in ghost.PROFILE.motors:
        for label, op in (("up", 1), ("down", 2), ("release", 3)):
            rows.append((f"{axis} {label}", _hex(codec.frame(op, key))))
    for name, key in ghost.PROFILE.memories:
        rows.extend(
            (
                (f"Recall {name}", _hex(codec.frame(7, key))),
                (f"Save {name}", _hex(codec.frame(6, key))),
            )
        )
    rows.extend(
        (label, _hex(codec.frame(op, key)))
        for label, op, key in (
            ("Flat", 5, 2),
            ("Zero gravity", 7, 5),
            ("Light on", 4, 1),
            ("Light off", 4, 2),
            ("Massage on", 14, 1),
            ("Massage off", 14, 0),
            ("Head massage increase", 12, 0),
            ("Head massage decrease", 18, 0),
            ("Feet massage increase", 17, 0),
            ("Feet massage decrease", 13, 0),
            ("Restore original settings", 5, 10),
        )
    )
    rows.extend(
        (f"Massage {mode}", _hex(codec.frame(16, index))) for index, mode in enumerate(ghost.MODES)
    )
    return _block(
        _table(("Action", "Frame"), rows),
        f"Movement refresh: {ghost.REFRESH_MS} ms; release delay: {ghost.RELEASE_MS} ms; relative massage step: {ghost.MASSAGE_STEP_MS} ms. "
        f"App save hold: {ghost.SAVE_HOLD_MS} ms. Alarm delete pair gap: {ghost.ALARM_DELETE_GAP_MS} ms.",
        f"Timer minutes: {ghost.TIMER_OPTIONS[0]}–{ghost.TIMER_OPTIONS[-1]}, encoded as `frame(0F, minutes)`. "
        "Clock: `frame(34, 03, {4: hour24, 5: minute, 6: second, 7: weekdayMonday1})`. "
        "Snore: `snore(enabled, angle_code, sensitivity_code)`. Settings edits use `pair(left_level, 0)`; home preserves both raw codes. "
        "Alarms 1/2: `alarm((record1, record2), edited_slot, 01)`. Alarms 3/4: `alarm((record3, record4), 04, 34)`. "
        "Each record is hour, minute, weekday/enabled flags, mode (0 empty, 1 Basic, 2 Pro).",
    )


BLOCKS.append((GUIDE, "ghostbed-commands", ghostbed_commands))
