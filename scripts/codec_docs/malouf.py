"""Generated blocks of the Malouf codec guide."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from custom_components.adjustable_bed.codec import malouf as malouf_codec
from custom_components.adjustable_bed.const import (
    BED_TYPE_MALOUF_APP,
    BED_TYPE_MALOUF_NEW_OKIN,
    get_motor_pulse_defaults,
)
from custom_components.adjustable_bed.profiles import malouf as malouf_profiles
from scripts.codec_docs._common import Block, _block, _hex, _table

GUIDE = "docs/beds/malouf.md"
_MALOUF_TRANSPORT_NAMES: dict[malouf_codec.TransportKey, str] = {
    "richmat_single": "Richmat single",
    "richmat_framed": "Richmat framed",
    "okin_legacy": "OKIN legacy",
    "okin_custom": "OKIN custom",
    "okin_new": "OKIN new",
}
_MALOUF_NAMES = {"malouf_new_okin": "NEW_OKIN", "malouf": "Malouf Base", "lucid": "Lucid Base"}
_MALOUF_LABELS = {
    "stop": "STOP",
    "head_up": "Head up",
    "head_down": "Head down",
    "foot_up": "Foot up",
    "foot_down": "Foot down",
    "dual_up": "Combined (dual) up",
    "dual_down": "Combined (dual) down",
    "tilt_up": "Tilt up",
    "tilt_down": "Tilt down",
    "lumbar_up": "Lumbar up",
    "lumbar_down": "Lumbar down",
    "tilt_head_up": "Altitude head tilt up",
    "tilt_head_down": "Altitude head tilt down",
    "full_tilt_up": "Altitude full tilt up",
    "full_tilt_down": "Altitude full tilt down",
    "bed_height_up": "Bed height up (both lift columns)",
    "bed_height_down": "Bed height down (both lift columns)",
    "flat": "Flat",
    "zero_g": "Zero-G",
    "anti_snore": "Anti-Snore",
    "tv": "TV",
    "lounge": "Lounge (and Lucid Premium Read)",
    "memory_1": "Memory 1 recall",
    "memory_2": "Memory 2 recall",
    "save_1": "Memory 1 save",
    "save_2": "Memory 2 save",
    "light": "Light toggle",
    "massage_head": "Head massage",
    "massage_foot": "Foot massage",
    "massage_head_minus": "Head massage down",
    "massage_foot_minus": "Foot massage down",
    "massage_wave": "Wave mode",
    "massage_off": "Massage off",
    "massage_timer_step": "Massage timer step",
    "massage_10": "Massage timer 10 min",
    "massage_20": "Massage timer 20 min",
    "massage_30": "Massage timer 30 min",
}
_MALOUF_FUNCTIONS = {
    "massage": None,
    "massage_head": "head massage",
    "massage_foot": "foot massage",
    "massage_wave": "wave",
    "massage_off": "massage off",
    "massage_timer_set": "direct timer",
    "massage_timer_step": "timer step",
    "alarm": "alarm",
    "light": "light",
}


def _malouf_profiles() -> dict[
    str, malouf_profiles.MaloufAppProfile | malouf_profiles.MaloufRouteProfile
]:
    return {malouf_profiles.NEW_OKIN.key: malouf_profiles.NEW_OKIN, **malouf_profiles.APP_PROFILES}


def _malouf_word(word: int) -> str:
    return f"`0x{word:08X}`"


def render_malouf_profiles() -> str:
    new = malouf_profiles.NEW_OKIN
    apps = malouf_profiles.APP_PROFILES
    count, delay = get_motor_pulse_defaults(BED_TYPE_MALOUF_NEW_OKIN)
    summary = _table(
        ("Profile", "Bed type", "Transports", "Held movement", "Release"),
        (
            (
                _MALOUF_NAMES[new.key],
                f"`{BED_TYPE_MALOUF_NEW_OKIN}`",
                _MALOUF_TRANSPORT_NAMES[new.transport],
                f"motor pulse settings (default {count} × {delay} ms)",
                "STOP at once",
            ),
            *(
                (
                    _MALOUF_NAMES[key],
                    f"`{BED_TYPE_MALOUF_APP}`",
                    ", ".join(_MALOUF_TRANSPORT_NAMES[t] for t in profile.routes),
                    f"pulse count × {profile.hold_ms} ms",
                    f"STOP {profile.release_ms} ms after release",
                )
                for key, profile in apps.items()
            ),
        ),
    )

    def recall(r: malouf_profiles.Recall) -> str:
        sends = f"{r.repeats} writes" if r.repeats > 1 else "1 write"
        return f"{sends}, then STOP" if r.stop else f"{sends}, no STOP"

    def save(s: malouf_profiles.Save | None) -> str:
        return "save opcode, 1 write" if s is None else f"{s.repeats} × {s.interval_ms} ms"

    routes = _table(
        (
            "Profile",
            "Transport",
            "Presets and recall",
            "Memory save",
            "Clock and alarm",
            "Status query",
        ),
        (
            *(
                (
                    _MALOUF_NAMES[key],
                    _MALOUF_TRANSPORT_NAMES[transport],
                    recall(route.recall),
                    save(route.save),
                    "n/a"
                    if route.save is None
                    else f"{route.settings_repeats} write{'s' if route.settings_repeats > 1 else ''}",
                    "yes" if route.status_query else "no",
                )
                for key, profile in apps.items()
                for transport, route in profile.routes.items()
            ),
            (
                _MALOUF_NAMES[new.key],
                _MALOUF_TRANSPORT_NAMES[new.transport],
                recall(new.recall),
                save(new.save),
                "n/a",
                "no",
            ),
        ),
    )
    return _block(
        "### Profile summary",
        summary,
        "### Timing per transport",
        "A memory save waits one interval before its first write and ends without "
        "STOP. Light and massage commands are single writes.",
        routes,
    )


def render_malouf_transports() -> str:
    users = {
        key: ", ".join(
            _MALOUF_NAMES[name]
            for name, profile in _malouf_profiles().items()
            if key in getattr(profile, "routes", (getattr(profile, "transport", None),))
        )
        for key in malouf_codec.TRANSPORTS
    }
    return _block(
        _table(
            ("Transport", "Service", "Write", "Notify", "STOP frame", "Profiles"),
            (
                (
                    _MALOUF_TRANSPORT_NAMES[key],
                    f"`{transport.command_service}`",
                    f"`{transport.command_characteristic}`",
                    f"`{transport.notify_characteristic}`"
                    if transport.notify_characteristic
                    else "none",
                    _hex(
                        malouf_codec.command(
                            key,
                            malouf_codec.STOP_OPCODE
                            if transport.family == "richmat"
                            else malouf_codec.STOP_WORD,
                        )
                    ),
                    users[key],
                )
                for key, transport in malouf_codec.TRANSPORTS.items()
            ),
        )
    )


def render_malouf_commands() -> str:
    app = malouf_profiles.MALOUF
    new = malouf_profiles.NEW_OKIN
    if missing := ({*app.richmat, *app.okin, *new.words} - _MALOUF_LABELS.keys()):
        raise ValueError(f"Malouf actions without a label: {sorted(missing)}")
    if app.richmat != malouf_profiles.LUCID.richmat or app.okin != malouf_profiles.LUCID.okin:
        raise ValueError("The command table assumes both apps share their command tables")
    words = app.save_words
    save_words = {"save_1": words.slots[1], "save_2": words.slots[2]}

    def cell(table: Mapping[str, int], action: str, fmt: Callable[[int], str]) -> str:
        value = table.get(action, save_words.get(action) if table is not app.richmat else None)
        return "none" if value is None else fmt(value)

    rows = [
        (
            _MALOUF_LABELS[action],
            cell(app.richmat, action, lambda code: f"`0x{code:02X}`"),
            cell(app.okin, action, _malouf_word),
            cell(new.words, action, _malouf_word),
        )
        for action in _MALOUF_LABELS
    ]
    rows.append(
        (
            "Memory 1 save, `smartbed238` names",
            f"`0x{app.richmat['save_1']:02X}`",
            _malouf_word(words.smartbed238_slot_1),
            _malouf_word(new.save_words.smartbed238_slot_1),
        )
    )
    return _block(
        _table(
            ("Command", "Richmat opcode (apps)", "OKIN word (apps)", "OKIN word (NEW_OKIN)"), rows
        ),
        "Framed Richmat sends selector 1 on a secondary bed for: "
        + ", ".join(_MALOUF_LABELS[action] for action in sorted(app.selector_actions))
        + ".",
    )


def render_malouf_models() -> str:
    def picker(key: str) -> str:
        apps = [
            _MALOUF_NAMES[name]
            for name, p in malouf_profiles.APP_PROFILES.items()
            if key in p.models
        ]
        return ", ".join(apps) or "stored entries only"

    def functions(model: malouf_profiles.MaloufAppModel) -> str:
        names = [_MALOUF_FUNCTIONS[f] for f in model.functions if _MALOUF_FUNCTIONS[f]]
        return ", ".join(names) or "none"

    return _block(
        _table(
            ("Model", "Picker", "Memory slots", "Movement", "Presets", "Functions"),
            (
                (
                    model.name,
                    picker(key),
                    str(model.memory_slots),
                    ", ".join(model.manual).replace("_", " "),
                    ", ".join(_MALOUF_LABELS[p].split(" (")[0] for p in model.presets),
                    functions(model),
                )
                for key, model in malouf_profiles.MALOUF_APP_MODELS.items()
            ),
        )
    )


def render_malouf_alarm_types() -> str:
    return _block(
        _table(
            ("Alarm choice", "Type"),
            (
                (_MALOUF_LABELS[preset].removesuffix(" recall").split(" (")[0], str(value))
                for preset, value in malouf_codec.ALARM_TYPES.items()
            ),
        )
    )


def bed_types() -> dict[str, tuple[str, ...]]:
    """Bed types per profile, as the profile summary lists them."""
    return {
        malouf_profiles.NEW_OKIN.key: (BED_TYPE_MALOUF_NEW_OKIN,),
        **dict.fromkeys(malouf_profiles.APP_PROFILES, (BED_TYPE_MALOUF_APP,)),
    }


BLOCKS: list[Block] = [
    (GUIDE, "malouf-profiles", render_malouf_profiles),
    (GUIDE, "malouf-transports", render_malouf_transports),
    (GUIDE, "malouf-commands", render_malouf_commands),
    (GUIDE, "malouf-models", render_malouf_models),
    (GUIDE, "malouf-alarm-types", render_malouf_alarm_types),
]
