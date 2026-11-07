"""Generated blocks of the Kaidi mesh codec guide."""

from __future__ import annotations

from collections import defaultdict

from custom_components.adjustable_bed.codec import kaidi as codec
from custom_components.adjustable_bed.const import BED_TYPE_ISLEEP, BED_TYPE_KAIDI
from custom_components.adjustable_bed.profiles import kaidi as profiles
from scripts.codec_docs._common import Block, _block, _hex, _table

GUIDE = "docs/beds/kaidi.md"
_NAMES = {
    "seat_1": "Seat 1",
    "seat_2": "Seat 2",
    "seat_3": "Seat 3",
    "seat_1_2": "Seat 1+2",
    "floyd": "Floyd Home",
    "isleep": "ISleep",
}
_SEATS = (profiles.SEAT_1, profiles.SEAT_2, profiles.SEAT_3)
# Seat table rows: label and the up / down / stop (or single) fields they show.
_SEAT_ROWS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Head up / down / stop", ("head_up", "head_down", "head_stop")),
    ("Foot up / down / stop", ("foot_up", "foot_down", "foot_stop")),
    ("Back up / down / stop", ("back_up", "back_down", "back_stop")),
    ("Waist (lumbar) up / down / stop", ("waist_up", "waist_down", "waist_stop")),
    ("Stop all", ("stop_all",)),
    ("Head (back) setting", ("head_setting",)),
    ("Leg setting", ("leg_setting",)),
    ("Flat", ("preset_flat",)),
    ("Zero G", ("preset_zero_g",)),
    ("Anti-Snore", ("preset_anti_snore",)),
    ("Book (TV preset)", ("preset_book",)),
    ("Leisure (Lounge preset)", ("preset_leisure",)),
    ("Light on / off", ("light_on", "light_off")),
    ("Massage start / stop", ("massage_start", "massage_stop")),
    (
        "Massage timer 15 / 30 / 45 min",
        ("massage_timer_15", "massage_timer_30", "massage_timer_45"),
    ),
    ("Neck up / down / stop (not sent)", ("neck_up", "neck_down", "neck_stop")),
    ("All up / down / stop (not sent)", ("all_up", "all_down", "all_stop")),
    ("New All up / down / stop (not sent)", ("new_all_up", "new_all_down", "new_all_stop")),
)
_ISLEEP_LABELS = {
    "head_up": "Head up",
    "head_down": "Head down",
    "head_stop": "Head release",
    "back_up": "Back up",
    "back_down": "Back down",
    "back_stop": "Back release",
    "legs_up": "Feet up",
    "legs_down": "Feet down",
    "legs_stop": "Feet release",
    "lumbar_up": "Waist up",
    "lumbar_down": "Waist down",
    "lumbar_stop": "Waist release",
    "all_up": "All up",
    "all_down": "All down",
    "all_stop": "All release",
    "new_all_up": "New All up",
    "new_all_down": "New All down",
    "new_all_stop": "New All release",
    "flat": "Flat",
    "zero_g": "Zero-G",
    "anti_snore": "Anti-snore",
    "memory_1": "Recall 1",
    "memory_2": "Recall 2",
    "memory_3": "Recall 3",
    "save_1": "Program 1",
    "save_2": "Program 2",
    "save_3": "Program 3",
    "light_on": "Light on",
    "light_off": "Light off",
    "massage_on": "Massage on",
    "massage_off": "Massage off",
    "head_strength": "Head strength",
    "foot_strength": "Foot strength",
    "pattern_1": "Pattern 1",
    "pattern_2": "Pattern 2",
    "pattern_3": "Pattern 3",
    "pattern_cancel": "Pattern cancel",
    "timer_1": "Timer choice 1",
    "timer_2": "Timer choice 2",
    "timer_3": "Timer choice 3",
    "timer_cancel": "Timer cancel",
}
_FLOYD_HOLDS = {
    "head_up": "Head up (HA back)",
    "head_down": "Head down (HA back)",
    "feet_up": "Feet up (HA legs)",
    "feet_down": "Feet down (HA legs)",
    "head_feet_up": "Head and feet up",
    "head_feet_down": "Head and feet down",
}
_FLOYD_PRESETS = {
    "flat": "Flat",
    "zero_g": "Zero gravity",
    "anti_snore": "Anti-snore",
    "memory_1": "Recall 1",
    "memory_2": "Recall 2",
    "memory_3": "Recall 3",
}


def _op(value: int | None) -> str:
    return "none" if value is None else f"`0x{value:02X}`"


def _ops(profile: profiles.KaidiCommandProfile, names: tuple[str, ...]) -> str:
    values = [getattr(profile, name) for name in names]
    return "none" if all(v is None for v in values) else " / ".join(_op(v) for v in values)


def _products() -> dict[str, list[int]]:
    """Product IDs that ``auto`` resolves to each variant."""
    found: dict[str, list[int]] = defaultdict(list)
    for product in sorted(profiles.KAIDI_SINGLE_PRODUCT_IDS | profiles.KAIDI_DOUBLE_PRODUCT_IDS):
        variant = profiles.resolve_kaidi_variant("auto", product_id=product).variant
        if variant is not None:
            found[variant].append(product)
    return found


def render_kaidi_profiles() -> str:
    products = _products()

    def listed(values: list[int] | tuple[int, ...]) -> str:
        return ", ".join(str(value) for value in values) or "manual or single seat bar"

    rows = [
        (
            _NAMES[key],
            f"`{BED_TYPE_KAIDI}`",
            f"`{key}`",
            listed(products.get(key, [])),
            str(len(profile.memory_recall)),
            "pulse settings, then the axis stop",
        )
        for key, profile in profiles.SEAT_PROFILES.items()
    ]
    floyd = profiles.FLOYD
    rows.append(
        (
            _NAMES[floyd.key],
            f"`{BED_TYPE_KAIDI}`",
            f"`{floyd.key}`",
            listed(products[floyd.key]),
            str(len(floyd.memory_recall)),
            f"one start, release after the hold; writes {floyd.write_spacing_ms} ms apart",
        )
    )
    isleep = profiles.IsleepProfile
    rows.append(
        (
            _NAMES[isleep.key],
            f"`{BED_TYPE_ISLEEP}`",
            "explicit app choice",
            listed(profiles.ISLEEP_PRODUCTS),
            str(sum(action.startswith("memory_") for action in isleep.commands)),
            "one press, release after the hold",
        )
    )
    return _block(
        _table(
            ("Profile", "Bed type", "Protocol variant", "Products", "Memory slots", "Movement"),
            rows,
        )
    )


def render_kaidi_transports() -> str:
    return _block(
        _table(
            ("Role", "UUID"),
            (
                ("Service (Seat profiles' detection)", f"`{codec.SERVICE_UUID}`"),
                ("Write", f"`{codec.WRITE_CHAR_UUID}`"),
                ("Notify", f"`{codec.NOTIFY_CHAR_UUID}`"),
            ),
        )
    )


def render_kaidi_frames() -> str:
    own, target = 0x90ABCDEF, 0x12345678
    return _block(
        _table(
            ("Frame", "Layout", "Example"),
            (
                (
                    "Join",
                    "`01 16 01` + room (LE32) + ASCII `1122`",
                    f"{_hex(codec.join(target))}, room `0x{target:08X}`",
                ),
                (
                    "Enrollment",
                    "`01 03` + room (LE32) + ASCII `1122` + `00 00 00 00`",
                    f"{_hex(codec.enroll(target))}, room `0x{target:08X}`",
                ),
                (
                    "Ping all",
                    "`03 FF FF FF FF FE` + own address (LE32)",
                    f"{_hex(codec.ping(codec.BROADCAST))}, own `0x{codec.BROADCAST:08X}`",
                ),
                (
                    "Control",
                    "`03` + target (LE32) + `20` + own (LE32) + `01 command parameter 00`",
                    f"{_hex(codec.control(target, own, 0x01, 0))}, command `0x01` from "
                    f"`0x{own:08X}` to `0x{target:08X}`",
                ),
            ),
        )
    )


def render_kaidi_seat_commands() -> str:
    seat_1 = profiles.SEAT_1
    rows = [(label, *(_ops(seat, names) for seat in _SEATS)) for label, names in _SEAT_ROWS]
    for kind in ("memory_save", "memory_recall"):
        label = "Save" if kind == "memory_save" else "Recall"
        slots = sorted(getattr(seat_1, kind))
        rows.append(
            (
                f"{label} {' / '.join(map(str, slots))}",
                *(
                    " / ".join(_op(getattr(seat, kind).get(slot)) for slot in slots)
                    for seat in _SEATS
                ),
            )
        )
    return _block(_table(("Command", "Seat 1", "Seat 2", "Seat 3"), rows))


def render_kaidi_floyd_commands() -> str:
    floyd = profiles.FLOYD
    sides = tuple(floyd.presets)
    holds = _table(
        ("Control", "Start", "Release"),
        ((_FLOYD_HOLDS[key], _op(start), _op(stop)) for key, (start, stop) in floyd.holds.items()),
    )
    presets = _table(
        ("Command", *(f"`{side}`" for side in sides)),
        (
            (label, *(_op(floyd.presets[side][action]) for side in sides))
            for action, label in _FLOYD_PRESETS.items()
        ),
    )
    other = _table(
        ("Command", "Command byte", "Parameter"),
        (
            ("Stop all", _op(floyd.stop_all), "retained"),
            (
                f"Save {' / '.join(map(str, floyd.memory_save))}",
                " / ".join(_op(v) for v in floyd.memory_save.values()),
                "retained",
            ),
            ("Light on / off", f"{_op(floyd.light_on)} / {_op(floyd.light_off)}", "retained"),
            *(
                (f"`{action}`", _op(floyd.save_preset), f"`{parameter:02X}`")
                for action, parameter in floyd.save_parameters.items()
            ),
            ("`confirm_add`", _op(floyd.confirm_add), "retained"),
        ),
    )
    return _block(
        "##### Held controls",
        holds,
        "##### Presets and recall per internal side",
        presets,
        "##### Other commands",
        other,
    )


def render_kaidi_isleep_commands() -> str:
    commands = profiles.ISLEEP_COMMANDS
    if missing := set(commands) - _ISLEEP_LABELS.keys():
        raise ValueError(f"ISleep actions without a label: {sorted(missing)}")
    rows = [
        (label, *(_op(code) for code in commands[action]))
        for action, label in _ISLEEP_LABELS.items()
    ]
    rows.append(("Enrollment acknowledgment", _op(profiles.IsleepProfile.enroll_ack), "", ""))
    return _block(_table(("Command", "Left / single", "Right", "Both"), rows))


def bed_types() -> dict[str, tuple[str, ...]]:
    """Bed types per profile, as the profile summary lists them."""
    return {
        **dict.fromkeys(profiles.SEAT_PROFILES, (BED_TYPE_KAIDI,)),
        profiles.FLOYD.key: (BED_TYPE_KAIDI,),
        profiles.IsleepProfile.key: (BED_TYPE_ISLEEP,),
    }


BLOCKS: list[Block] = [
    (GUIDE, "kaidi-profiles", render_kaidi_profiles),
    (GUIDE, "kaidi-transports", render_kaidi_transports),
    (GUIDE, "kaidi-frames", render_kaidi_frames),
    (GUIDE, "kaidi-seat-commands", render_kaidi_seat_commands),
    (GUIDE, "kaidi-floyd-commands", render_kaidi_floyd_commands),
    (GUIDE, "kaidi-isleep-commands", render_kaidi_isleep_commands),
]
