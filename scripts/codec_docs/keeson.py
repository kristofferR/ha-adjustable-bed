"""Generated blocks of the Keeson E5/E6 codec guide."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any, cast

from custom_components.adjustable_bed import controller_factory
from custom_components.adjustable_bed.beds import cluster033 as cluster033_module
from custom_components.adjustable_bed.beds import glideaway_motion as glideaway_module
from custom_components.adjustable_bed.beds import innova as innova_module
from custom_components.adjustable_bed.beds import keeson_okin_apps as okin_apps_module
from custom_components.adjustable_bed.beds import ore_comfort_bed as ore_module
from custom_components.adjustable_bed.beds import scott_living as scott_living_module
from custom_components.adjustable_bed.beds import serta_mp_remote as serta_mp_module
from custom_components.adjustable_bed.beds.ore_comfort_bed import ORE_COMFORT_BED_APPS
from custom_components.adjustable_bed.codec import keeson as keeson_codec
from custom_components.adjustable_bed.profiles import keeson as keeson_profiles
from scripts.codec_docs._common import Block, _block, _hex, _table

GUIDE = "docs/beds/keeson.md"

_K = keeson_profiles.KeesonCommands
_S = keeson_profiles.SinoCommands
_KEESON_NAMES: dict[str, str] = {
    "base": "Base (BaseI4/I5)",
    "ergomotion": "Ergomotion",
    "serta": "Serta",
    "okin": "OKIN FFE",
    "cb1322": "BetterLiving CB1322",
    "sino": "Sino",
    "betterliving": "BetterLiving",
    "json": "JSON/A00A",
    "ksbt": "KSBT",
    "ksbt03c": "KSBT03C",
    "ksbt_cr": "KSBT03CR",
    "ksbt04c": "KSBT04C",
    "sleep_harmony": "Sleep Harmony (KSBT04C)",
    "sleep_harmony_base_i5": "Sleep Harmony (base-i5)",
    "purple": "Purple Premium",
    "purple_plus": "Purple Premium Plus",
    "adjustable_lite": "Adjustable Lite (KSBT01C)",
    "adjustable_lite_ksbt03c": "Adjustable Lite (KSBT03C)",
    "restonic_a": "Restonic BT remote A",
    "restonic_b": "Restonic BT remote B",
    "innova": "INNOVA",
    "simon_li": "Simon Li",
    "okin_seating": "OKIN-Seating",
    "heal_every_night": "Heal Every Night",
    "americanstar": "AMERICANSTAR",
    "avanti_bases": "Avanti Bases",
    "bedsense_bases": "Bedsense Bases",
    "dynasty_bases": "Dynasty Bases",
    "maxcoil_una": "MaxCoil Una",
    "glideaway_motion": "Glideaway Motion",
    "malouf_legacy_okin": "Malouf legacy OKIN",
    "sleepys_box15": "Sleepy's BOX15",
    "scott_living": "Scott Living",
    "adjustamattress": "AdjustaMattress P1",
    "adjustamattress_p2": "AdjustaMattress P2",
    "sbi": "SBI",
    "rondure": "Rondure",
    "coolbase": "Cool Base",
    "bf": "BF",
    "cherish": "Cherish",
    "comfort_enhancements": "Comfort Enhancements",
}
# Controllers that keep their key tables and timing; their profile is only the frame.
_KEESON_CONTROLLERS: dict[str, tuple[str, str]] = {
    "glideaway_motion": ("`glideaway_motion`", "[Glideaway Motion](#glideaway-motion)"),
    "malouf_legacy_okin": ("`malouf_legacy_okin`", "[Malouf](malouf.md)"),
    "sleepys_box15": ("`sleepys_box15`", "[Sleepy's](sleepys.md)"),
    "scott_living": ("`scott_living`", "[Scott Living](#scott-living)"),
    "adjustamattress": ("`adjustamattress`, model P1", "[AdjustaMattress](adjustamattress.md)"),
    "adjustamattress_p2": ("`adjustamattress`, model P2", "[AdjustaMattress](adjustamattress.md)"),
    "sbi": ("`sbi`", "[SBI / Q-Plus](#sbi--q-plus-costco)"),
    "rondure": ("`rondure`", "[Rondure](#rondure)"),
    "coolbase": ("`coolbase`", "[Cool Base](#cool-base)"),
    "bf": ("`bf`", "[BF and Cherish](#bf-and-cherish)"),
    "cherish": ("`cherish`", "[BF and Cherish](#bf-and-cherish)"),
    "comfort_enhancements": (
        "`comfort_enhancements`",
        "[Comfort Enhancements](#comfort-enhancements)",
    ),
}
# Profiles chosen inside a variant: (variant, rule). tests/test_codec_docs_keeson.py checks them.
KEESON_SUB_ROUTES: dict[str, tuple[str, str]] = {
    "ksbt03c": ("ksbt", "name starts with `KSBT03C`, not `KSBT03CR`"),
    "sleep_harmony_base_i5": ("sleep_harmony", "name starts with `base-i5.`"),
    "purple_plus": ("purple", "name starts with `KSBT04C`, or the Nordic UART service exists"),
    "adjustable_lite_ksbt03c": ("adjustable_lite", "name contains `KSBT03C` (case-sensitive)"),
    "betterliving": ("sino", "Auto: both fallback services, or an `OKIN-BLE` name with one"),
    "cb1322": (
        "okin",
        "Auto: as BetterLiving, with a `BLE-4.0 Module` or `DewertOKIN` manufacturer",
    ),
}
# Profiles whose app controller keeps its own key table (see the profile sections).
_KEESON_APP_TABLES = frozenset(
    {
        "innova",
        "simon_li",
        "okin_seating",
        "heal_every_night",
        *ORE_COMFORT_BED_APPS,
        *_KEESON_CONTROLLERS,
    }
)
_CARRIER_LAYOUTS = {
    "k1": "`header FE 16` + word + checksum",
    "p2": "`04 02` + big-endian word",
    "p2_side": "`05 02` + big-endian word + `00`",
    "p2_padded": "`04 02` + big-endian word + `00`",
    "p2_checked": "`04 02` + big-endian word + checksum",
    "json": "JSON envelope, see below",
}


def _kname(key: str) -> str:
    return _KEESON_NAMES[key]


def _knames(keys: Iterable[str]) -> str:
    return ", ".join(_kname(key) for key in keys) or "none"


def keeson_aliases() -> dict[str, tuple[str, ...]]:
    """Alias bed types per profile, from the factory registry."""
    aliases: dict[str, tuple[str, ...]] = {}
    for bed_type, spec in controller_factory._SIMPLE_CONTROLLERS.items():
        if (spec.module, spec.class_name) == ("keeson", "KeesonController"):
            variant = spec.kwargs["variant"]
            aliases[variant] = (*aliases.get(variant, ()), bed_type)
    return aliases


def _route(key: str) -> str:
    if key in _KEESON_CONTROLLERS:
        return f"bed type {_KEESON_CONTROLLERS[key][0]}"
    if key in KEESON_SUB_ROUTES:
        variant, rule = KEESON_SUB_ROUTES[key]
        route = f"`keeson` `{variant}`: {rule}"
    else:
        route = f"`keeson` `{key}`" + (" (Auto default)" if key == "base" else "")
    aliases = keeson_aliases().get(key, ())
    return route + "".join(f"; bed type `{bed_type}`" for bed_type in aliases)


def _carrier(profile: keeson_profiles.KeesonProfile) -> str:
    if profile.carrier != "k1":
        return {
            "p2": "P2 6-byte",
            "p2_side": "P2 7-byte (`05`)",
            "p2_padded": "P2 7-byte, `00` end",
            "p2_checked": "P2 7-byte, checksum end",
            "json": "JSON",
        }[profile.carrier]
    side = f", side `{profile.side:02X}`" if profile.side is not None else ""
    return f"K1 `{profile.header:02X}`, {profile.order}-endian{side}"


def _word(word: int) -> str:
    return f"`0x{word:08X}`"


def _kframe(profile: keeson_profiles.KeesonProfile, step: int | bytes) -> str:
    if profile.carrier == "json" and isinstance(step, int):
        return f"JSON key `{step:08x}`, `ctrm` {int(step != 0)}"
    return _hex(step if isinstance(step, bytes) else keeson_profiles.encode(profile, step, "Bed"))


def _steps(profile: keeson_profiles.KeesonProfile, *, waits: bool) -> str:
    return (
        ", ".join(
            (f"+{wait} ms " if waits else "") + _kframe(profile, step)
            for wait, step in profile.release.steps
        )
        or "none"
    )


def _lease(profile: keeson_profiles.KeesonProfile | keeson_profiles.AppProfile) -> str:
    return "renewable lease" if profile.execution.hold == "stream" else "no"


def _hold(profile: keeson_profiles.KeesonProfile) -> str:
    if profile.refresh_ms:
        return f"pulse count × {profile.refresh_ms} ms"
    if profile.hold:
        return f"{profile.hold[0]} × {profile.hold[1]} ms"
    return "configured"


def _keeson_timing_rows() -> Iterable[tuple[str, ...]]:
    for key, profile in keeson_profiles.PROFILES.items():
        if key in _KEESON_CONTROLLERS:
            continue  # Timing stays in these controllers; see their sections.
        release = profile.release
        if not release.steps:
            stop = "none"
        elif release.on_stop:
            stop = _steps(profile, waits=False)
        else:
            stop = "none"
        yield (
            _kname(key),
            _hold(profile),
            "{} × {} ms".format(*profile.three_motor_hold) if profile.three_motor_hold else "same",
            _steps(profile, waits=True)
            + (" (STOP ends the wait)" if release.guarded and release.steps else ""),
            stop,
            "yes" if release.after_tap else "no",
            f"{profile.tap_wait_ms} ms" if profile.tap_wait_ms else "none",
        )


def _preset_cell(profile: keeson_profiles.KeesonProfile, preset: keeson_profiles.Preset) -> str:
    word = profile.presets.get(preset)
    if word is None:
        return "no"
    held = profile.held_controls.get(preset)
    suffix = " (not listed)" if preset in profile.unlisted_presets else ""
    suffix += " (held)" if held and held[1] else ""
    return _word(word) + suffix


def _memory_cell(words: Mapping[int, int]) -> str:
    return "<br>".join(f"{slot}: {_word(word)}" for slot, word in words.items()) or "none"


def render_keeson_profiles() -> str:
    profiles = keeson_profiles.PROFILES
    summary = _table(
        ("Profile", "Route", "Frame", "Transport", "Lights", "Massage", "Hold until release"),
        (
            (
                _kname(key),
                _route(key),
                _carrier(profile),
                "app controller"
                if key in _KEESON_CONTROLLERS
                else profile.transport.upper() + (" (fixed)" if profile.fixed_write else ""),
                "app controller" if key in _KEESON_APP_TABLES else profile.lights or "none",
                "app controller" if key in _KEESON_APP_TABLES else profile.massage,
                _lease(profile),
            )
            for key, profile in profiles.items()
        ),
    )
    timing = _table(
        (
            "Profile",
            "Hold",
            "Three motors",
            "Release after a hold",
            "Explicit stop",
            "Released after one-shots",
            "Wait before one-shots",
        ),
        _keeson_timing_rows(),
    )
    presets = _table(
        ("Profile", "Flat", "Zero G", "Lounge", "TV", "Anti-snore", "Memory recall", "Memory save"),
        (
            (
                _kname(key),
                *(
                    _preset_cell(profile, preset)
                    for preset in ("flat", "zero_g", "lounge", "tv", "anti_snore")
                ),
                _memory_cell(profile.memory),
                (
                    _memory_cell(profile.memory_save.words)
                    + (
                        f"<br>{profile.memory_save.repeats} × {profile.memory_save.repeat_ms} ms"
                        + (", waiting first" if profile.memory_save.wait_first else "")
                        if profile.memory_save.repeats > 1
                        else ""
                    )
                )
                if profile.memory_save
                else "none",
            )
            for key, profile in profiles.items()
            if key not in _KEESON_APP_TABLES
        ),
    )
    return _block(
        "### Profile summary",
        summary,
        "### Hold and release timing",
        "A hold writes its frame the given number of times while the stored cadence is "
        "the Keeson default; a customized cadence wins. Release waits count from the "
        "previous write. An explicit stop sends the release without its waits. The "
        "[controller profiles](#controller-profiles) keep their timing in their "
        "controllers. Under a [renewable hold](../SERVICES.md#renewable-holds), a "
        "profile with hold until release refreshes at its app interval until the "
        "lease ends or STOP arrives, up to 30 s, then sends its release.",
        timing,
        "### Presets and memory",
        f"Words, encoded in the profile's frame. {_knames(sorted(_KEESON_APP_TABLES))} "
        "keep their key tables with their app controllers; see their sections.",
        presets,
    )


def render_keeson_transports() -> str:
    profiles = keeson_profiles.PROFILES
    return _block(
        _table(
            ("Transport", "Service", "Write", "Notify", "Fallbacks (service / write)", "Profiles"),
            (
                (
                    key.upper(),
                    f"`{transport.service_uuid}`",
                    f"`{transport.write_uuid}`",
                    f"`{transport.notify_uuid}`",
                    "<br>".join(f"`{s}` / `{w}`" for s, w in transport.fallbacks) or "none",
                    _knames(
                        name
                        for name, profile in profiles.items()
                        if profile.transport == key and name not in _KEESON_CONTROLLERS
                    ),
                )
                for key, transport in keeson_codec.TRANSPORTS.items()
            ),
        )
    )


def render_keeson_carriers() -> str:
    groups: dict[tuple[str, int, str, int | None], list[str]] = {}
    for key, profile in keeson_profiles.PROFILES.items():
        groups.setdefault(
            (profile.carrier, profile.header, profile.order, profile.side), []
        ).append(key)
    rows = []
    for (carrier, *_shape), keys in groups.items():
        profile = keeson_profiles.PROFILES[keys[0]]
        rows.append(
            (
                _carrier(profile),
                _CARRIER_LAYOUTS[carrier],
                "see JSON envelope" if carrier == "json" else _kframe(profile, _K.MOTOR_HEAD_UP),
                _knames(keys),
            )
        )
    split = [key for key, profile in keeson_profiles.PROFILES.items() if profile.single_side]
    for side, selector in keeson_codec.SIDE_SELECTORS.items():
        frame = keeson_profiles.encode(
            keeson_profiles.PROFILES[split[0]], _K.MOTOR_HEAD_UP, side=side
        )
        rows.append(
            (
                f"K1 `E6`, little-endian, {side.title()} side `{selector:02X}`",
                "`E6 FE 16` + word + side + checksum",
                _hex(frame),
                _knames(split),
            )
        )
    return _block(_table(("Frame", "Layout", "Head up", "Profiles"), rows))


_KEY_LABELS: tuple[tuple[str, int], ...] = (
    ("Release (all keys up)", keeson_codec.RELEASE),
    ("Head up / down", _K.MOTOR_HEAD_UP),
    ("", _K.MOTOR_HEAD_DOWN),
    ("Feet up / down", _K.MOTOR_FEET_UP),
    ("", _K.MOTOR_FEET_DOWN),
    ("Tilt up / down", _K.MOTOR_TILT_UP),
    ("", _K.MOTOR_TILT_DOWN),
    ("Lumbar up / down", _K.MOTOR_LUMBAR_UP),
    ("", _K.MOTOR_LUMBAR_DOWN),
    ("Massage step", _K.MASSAGE_STEP),
    ("Massage timer step", _K.MASSAGE_TIMER_STEP),
    ("Foot massage + / -", _K.MASSAGE_FOOT_UP),
    ("", _K.MASSAGE_FOOT_DOWN),
    ("Head massage + / -", _K.MASSAGE_HEAD_UP),
    ("", _K.MASSAGE_HEAD_DOWN),
    ("Zero G", _K.PRESET_ZERO_G),
    ("`0x2000`: Read, Lounge or a memory", _K.PRESET_MEMORY_1),
    ("`0x4000`: TV or a memory", _K.PRESET_MEMORY_2),
    ("`0x8000`: Anti-snore or a memory", _K.PRESET_MEMORY_3),
    ("`0x10000`: M or a memory", _K.PRESET_MEMORY_4),
    ("Light toggle", _K.TOGGLE_SAFETY_LIGHTS),
    ("Flat", _K.PRESET_FLAT),
    ("Wave next / previous (Base)", _K.MASSAGE_WAVE_STEP),
    ("", _K.MASSAGE_WAVE_PREVIOUS),
    ("Intensity 1 / 2 / 3 (Base)", _K.MASSAGE_INTENSITY_1),
    ("", _K.MASSAGE_INTENSITY_2),
    ("", _K.MASSAGE_INTENSITY_3),
    ("All massage off (Sleep Harmony)", _K.MASSAGE_ALL_STOP),
)


def render_keeson_keys() -> str:
    base = keeson_profiles.BASE
    harmony = keeson_profiles.SLEEP_HARMONY_BASE_I5
    rows = []
    for label, word in _KEY_LABELS:
        profile = harmony if word == _K.MASSAGE_ALL_STOP else base
        rows.append((label, _word(word), _kframe(profile, word), _kname(profile.key)))
    return _block(
        _table(("Key", "Word", "Example frame", "Example profile"), rows),
        "Which word a profile sends for a preset or memory slot is in "
        "[Presets and memory](#presets-and-memory).",
    )


def render_keeson_sino() -> str:
    sino = keeson_profiles.SINO
    rows = (
        (
            "Light on / off",
            f"{_word(_S.LIGHT_ON)} / {_word(_S.LIGHT_OFF)}",
            f"{_kframe(sino, _S.LIGHT_ON)} / {_kframe(sino, _S.LIGHT_OFF)}",
        ),
        (
            "Head massage level 0-10",
            f"{_word(_S.MASSAGE_HEAD_INTENSITY_BASE)} + level",
            f"{_kframe(sino, _S.MASSAGE_HEAD_INTENSITY_BASE)} … "
            f"{_kframe(sino, _S.MASSAGE_HEAD_INTENSITY_BASE + 10)}",
        ),
        (
            "Foot massage level 0-10",
            f"{_word(_S.MASSAGE_FOOT_INTENSITY_BASE)} + level",
            f"{_kframe(sino, _S.MASSAGE_FOOT_INTENSITY_BASE)} … "
            f"{_kframe(sino, _S.MASSAGE_FOOT_INTENSITY_BASE + 10)}",
        ),
        (
            "Wave pattern 1-10",
            f"{_word(_S.MASSAGE_HEAD_WAVE_BASE)} + pattern",
            f"{_kframe(sino, _S.MASSAGE_HEAD_WAVE_BASE + 1)} … "
            f"{_kframe(sino, _S.MASSAGE_HEAD_WAVE_BASE + 10)}",
        ),
    )
    return _block(_table(("Command", "Word", "Frames (Sino)"), rows))


def _control_rows(
    profile: keeson_profiles.KeesonProfile, controls: Iterable[tuple[str, int, str]]
) -> list[str]:
    return _table(
        ("Control", "Word", "Frame", "Sent"),
        ((label, _word(word), _kframe(profile, word), how) for label, word, how in controls),
    )


def render_keeson_adjustable_lite() -> str:
    lite, ksbt03c = keeson_profiles.ADJUSTABLE_LITE, keeson_profiles.ADJUSTABLE_LITE_KSBT03C
    rows = [
        ("Head/back up", _K.MOTOR_HEAD_UP, "both"),
        ("Head/back down", _K.MOTOR_HEAD_DOWN, "both"),
        ("Leg/foot up", _K.MOTOR_FEET_UP, "both"),
        ("Leg/foot down", _K.MOTOR_FEET_DOWN, "both"),
        *(
            (preset.replace("_", " ").title(), word, "both")
            for preset, word in lite.presets.items()
        ),
        *((f"Memory {slot}", word, "both") for slot, word in lite.memory.items()),
        ("Light", _K.TOGGLE_SAFETY_LIGHTS, "both"),
        *(
            (preset.replace("_", " ").title(), word, "KSBT03C")
            for preset, word in ksbt03c.presets.items()
            if preset not in lite.presets
        ),
        ("Massage timer", _K.MASSAGE_TIMER_STEP, "KSBT03C"),
        ("Head massage +", _K.MASSAGE_HEAD_UP, "KSBT03C"),
        ("Head massage -", _K.MASSAGE_HEAD_DOWN, "KSBT03C"),
        ("Leg massage +", _K.MASSAGE_FOOT_UP, "KSBT03C"),
        ("Leg massage -", _K.MASSAGE_FOOT_DOWN, "KSBT03C"),
    ]
    table = _table(
        ("Control", "Word", "Frame", "Remotes"),
        ((label, _word(word), _kframe(lite, word), remotes) for label, word, remotes in rows),
    )
    return _block(table, f"Status query: {_hex(keeson_codec.STATUS_QUERY)}, both remotes.")


def render_keeson_restonic() -> str:
    a, b = keeson_profiles.RESTONIC_A_CONTROLS, keeson_profiles.RESTONIC_B_CONTROLS
    profile = keeson_profiles.RESTONIC_A

    def mode(controls: Mapping[str, tuple[int, bool]], name: str) -> str:
        if name not in controls:
            return "no"
        return "held" if controls[name][1] else "once"

    return _block(
        _table(
            ("`hold_control` name", "Word", "Frame", "Remote A", "Remote B"),
            (
                (f"`{name}`", _word(word), _kframe(profile, word), mode(a, name), mode(b, name))
                for name, (word, _held) in {**a, **b}.items()
            ),
        ),
        f"Release: {_kframe(profile, keeson_codec.RELEASE)} after every control.",
    )


def render_keeson_innova() -> str:
    profile = keeson_profiles.INNOVA
    held = {**innova_module._COMMON_HELD}
    for layout in innova_module._LAYOUT_HELD.values():
        held.update(layout)
    screens = {
        name: "/".join(
            f"{count}M" for count, layout in innova_module._LAYOUT_HELD.items() if name in layout
        )
        or "all"
        for name in held
    }
    once = (
        ("Zero G", profile.presets["zero_g"]),
        ("Flat", profile.presets["flat"]),
        ("Light", _K.TOGGLE_LIGHTS),
        ("Head massage +", _K.MASSAGE_HEAD_UP),
        ("Head massage -", _K.MASSAGE_HEAD_DOWN),
        ("Foot massage +", _K.MASSAGE_FOOT_UP),
        ("Foot massage -", _K.MASSAGE_FOOT_DOWN),
        ("Massage level", innova_module.MASSAGE_LEVEL),
        ("Massage timer (massage page)", innova_module.MASSAGE_TIMER),
    )
    return _block(
        _table(
            ("Held control (`hold_control` name)", "Word", "Frame", "Screens"),
            ((f"`{n}`", _word(w), _kframe(profile, w), screens[n]) for n, w in held.items()),
        ),
        _table(
            ("One-shot control", "Word", "Frame"),
            ((label, _word(word), _kframe(profile, word)) for label, word in once),
        ),
        f"Release and Stop: {_kframe(profile, keeson_codec.RELEASE)}. Rename example "
        f"(`BED`): {_hex(innova_module.innova_rename_frame('BED'))}.",
    )


def render_keeson_okin_apps() -> str:
    apps = okin_apps_module
    simon, seating = apps.SIMON_KEYS, apps.SEATING_KEYS
    profile = keeson_profiles.SIMON_LI
    seats = _table(
        ("Control", "Simon Li", "OKIN-Seating"),
        (
            (
                f"`{name}`",
                _kframe(profile, simon[name]) if name in simon else "-",
                _kframe(profile, seating[name]) if name in seating else "-",
            )
            for name in {**simon, **seating}
        ),
    )
    heal = keeson_profiles.HEAL_EVERY_NIGHT
    movement = dict(
        zip(
            (
                "Head up",
                "Foot up",
                "Tilt up",
                "Lumbar up",
                "Head down",
                "Foot down",
                "Tilt down",
                "Lumbar down",
            ),
            apps.HEAL_MOVEMENT_KEYS,
            strict=True,
        )
    )
    heal_rows = [
        *((label, _word(word), _kframe(heal, word)) for label, word in movement.items()),
        *(
            (f"{name.replace('_', ' ').title()}", _word(w), _kframe(heal, w))
            for name, w in apps.HEAL_PRESETS.items()
        ),
        *(
            (f"Save memory {slot}", _word(w), _kframe(heal, w))
            for slot, w in apps.HEAL_MEMORY_SAVE.items()
        ),
        ("Preset STOP", _word(apps.HEAL_PRESET_STOP), _kframe(heal, apps.HEAL_PRESET_STOP)),
        (
            f"Head massage level 0-{apps.HEAL_ZONE_MAX}",
            f"{_word(apps.HEAL_HEAD_MASSAGE)} + level",
            f"{_kframe(heal, apps.HEAL_HEAD_MASSAGE)} … "
            f"{_kframe(heal, apps.HEAL_HEAD_MASSAGE + apps.HEAL_ZONE_MAX)}",
        ),
        (
            f"Foot massage level 0-{apps.HEAL_ZONE_MAX}",
            f"{_word(apps.HEAL_FOOT_MASSAGE)} + level",
            f"{_kframe(heal, apps.HEAL_FOOT_MASSAGE)} … "
            f"{_kframe(heal, apps.HEAL_FOOT_MASSAGE + apps.HEAL_ZONE_MAX)}",
        ),
        (
            f"Wave 1-{apps.HEAL_WAVE_MAX}",
            f"{_word(apps.HEAL_WAVE)} + wave - 1",
            f"{_kframe(heal, apps.HEAL_WAVE)} … "
            f"{_kframe(heal, apps.HEAL_WAVE + apps.HEAL_WAVE_MAX - 1)}",
        ),
        ("Timer (every label)", _word(apps.HEAL_TIMER), _kframe(heal, apps.HEAL_TIMER)),
        (
            "Light on / off",
            f"{_word(apps.HEAL_LIGHT_ON)} / {_word(apps.HEAL_LIGHT_OFF)}",
            f"{_kframe(heal, apps.HEAL_LIGHT_ON)} / {_kframe(heal, apps.HEAL_LIGHT_OFF)}",
        ),
    ]
    return _block(
        "#### Simon Li and OKIN-Seating keys",
        seats,
        "#### Heal Every Night keys",
        "Movement keys before the settings below swap or reverse them.",
        _table(("Control", "Word", "Frame"), heal_rows),
        f"Release: {_kframe(profile, keeson_codec.RELEASE)} for all three apps.",
    )


def render_keeson_ore() -> str:
    ore = ore_module
    profile = keeson_profiles.MAXCOIL_UNA
    names = {2: "2M", 3: "3M", 4: "4M"}
    axes: dict[tuple[int, int], tuple[list[str], list[str]]] = {}
    for count, layout in ore.LAYOUTS.items():
        for key, _tk, up, down in layout:
            entry = axes.setdefault((up, down), ([], []))
            entry[0].append(f"{names[count]} {key}")
    motion = _table(
        ("Axis", "Up", "Down"),
        (
            (", ".join(labels), _kframe(profile, up), _kframe(profile, down))
            for (up, down), (labels, _unused) in axes.items()
        ),
    )
    recall = {"Zero G": ore.RECALL_ZERO_G, "Flat": ore.RECALL_FLAT}
    recall |= {f"Memory {'AB'[slot - 1]}": w for slot, w in ore.RECALL_MEMORY.items()}
    save = {"Zero G": ore.SAVE_ZERO_G, "Flat": ore.SAVE_FLAT}
    save |= {f"Memory {'AB'[slot - 1]}": w for slot, w in ore.SAVE_MEMORY.items()}
    presets = _table(
        ("Preset", "Recall", "Save"),
        ((name, _kframe(profile, recall[name]), _kframe(profile, save[name])) for name in recall),
    )
    top = ore.MASSAGE_LEVEL_MAX
    other = _table(
        ("Command", "Word", "Frames"),
        (
            *(
                (
                    f"{zone.title()} massage level 0-{top}",
                    f"{_word(base)} + level",
                    f"{_kframe(profile, base)} … {_kframe(profile, base + top)}",
                )
                for zone, base in ore.MASSAGE_BASE.items()
            ),
            *(
                (f"Massage timer {minutes} min", _word(w), _kframe(profile, w))
                for minutes, w in ore.MASSAGE_TIMER.items()
            ),
            (
                "Light on / off",
                f"{_word(ore.LIGHT_ON)} / {_word(ore.LIGHT_OFF)}",
                f"{_kframe(profile, ore.LIGHT_ON)} / {_kframe(profile, ore.LIGHT_OFF)}",
            ),
            ("Release / STOP", _word(keeson_codec.RELEASE), _kframe(profile, keeson_codec.RELEASE)),
        ),
    )
    return _block(
        "#### Motion", motion, "#### Presets and memory", presets, "#### Massage and lights", other
    )


def render_keeson_controllers() -> str:
    rows = []
    for key, (route, guide) in _KEESON_CONTROLLERS.items():
        profile = keeson_profiles.PROFILES[key]
        rows.append(
            (
                _kname(key),
                route,
                _carrier(profile)
                + (
                    " (A/B: `E6`, side "
                    + "/".join(f"`{byte:02X}`" for byte in profile.split_sides.values())
                    + ")"
                    if profile.split_sides
                    else ""
                ),
                _kframe(profile, _K.MOTOR_HEAD_UP),
                _kframe(profile, keeson_codec.RELEASE),
                _lease(profile),
                guide,
            )
        )
    return _block(
        _table(
            (
                "Profile",
                "Bed type",
                "Frame",
                "Word `0x1`",
                "Zero word",
                "Hold until release",
                "Guide",
            ),
            rows,
        )
    )


def render_keeson_glideaway() -> str:
    gm = glideaway_module
    profile = keeson_profiles.GLIDEAWAY_MOTION
    axes = {
        "back": "Back/head",
        "feet": "Feet",
        "both": "Head + feet",
        "tilt": "Neck tilt",
        "bed_height": "Bed height",
    }
    rows = [
        (f"{axes[axis]} {direction}", _word(word), _kframe(profile, word))
        for axis, pair in gm.AXES.items()
        for direction, word in zip(("up", "down"), pair, strict=True)
    ]
    rows += [
        (name.replace("_", " ").capitalize(), _word(word), _kframe(profile, word))
        for name, word in gm.PRESETS.items()
    ]
    rows.append(("Light toggle (500/600)", _word(gm.LIGHT), _kframe(profile, gm.LIGHT)))
    rows += [
        (f"Massage {name.replace('_', ' ')} (500/600)", _word(word), _kframe(profile, word))
        for name, word in gm.MASSAGE.items()
    ]
    rows.append(("Release", _word(keeson_codec.RELEASE), _kframe(profile, keeson_codec.RELEASE)))
    return _block(_table(("Control", "Word", "Frame"), rows))


def render_keeson_scott_living() -> str:
    table = scott_living_module.ScottLivingCommands
    profile = keeson_profiles.SCOTT_LIVING
    words = {name: word for name, word in vars(table).items() if name.isupper()}
    rows = [
        (name.replace("_", " ").title(), _word(word), _kframe(profile, word))
        for name, word in words.items()
    ]
    rows.append(("Stop", _word(keeson_codec.RELEASE), _kframe(profile, keeson_codec.RELEASE)))
    return _block(_table(("Command", "Word", "Frame"), rows))


# Keeson cluster033 apps

_C033_ROLES = {
    cluster033_module.FFE9: "FFE9",
    cluster033_module.FFE4: "FFE4",
    cluster033_module.NUS_TX: "NUS TX",
    cluster033_module.NUS_RX: "NUS RX",
}


def _c033_controller(
    profile: keeson_profiles.AppProfile, side: str = "both"
) -> cluster033_module.AppController:
    return cluster033_module.AppController(cast(Any, None), profile, side=side)


_C033_HEADINGS = {"ergomotion_app": "Ergomotion app"}


def _c033_heading(app: str) -> str:
    return _C033_HEADINGS.get(app, keeson_profiles.APP_NAMES[app])


def _c033_layouts(app: str) -> str:
    default = keeson_profiles.DEFAULT_LAYOUTS[app]
    return ", ".join(
        f"**{layout}**" if layout == default else layout
        for layout in keeson_profiles.APP_LAYOUTS[app]
    )


def _c033_frame(app: str) -> str:
    if app == "qplus_app":
        return "K1 `E5` (Both) or `E6` + side byte (A/B); MX: P2 6-byte"
    return "K1 `E5`, little-endian"


def _c033_clock(profile: keeson_profiles.AppProfile) -> str:
    if not profile.clock:
        return "none"
    delay = profile.clock_init_delay_ms
    if delay is None:
        return "on demand"
    when = "at connect" if delay == 0 else f"{delay / 1000:g} s after connect"
    return f"{when}, and on demand"


def _c033_rename(profile: keeson_profiles.AppProfile) -> str:
    if not profile.rename_units:
        return "none"
    trim = "trimmed" if profile.rename_trimmed else "outer spaces rejected"
    return f"{profile.rename_units} UTF-16 units, {trim}"


def _c033_alarm(profile: keeson_profiles.AppProfile) -> str:
    spec = profile.alarm
    if spec is None:
        return "none"
    marker = f"marker `{spec.weekday_marker:#04x}`" if spec.weekday_marker else "no marker"
    return f"wake byte `{spec.wake_byte:#04x}`, {marker}, {spec.capacity} per table"


def render_keeson_apps() -> str:
    rows = []
    for app in keeson_profiles.APP_LAYOUTS:
        profile = keeson_profiles.app_profile(app)
        roles = ("FFE9", "FFE4") + (("NUS TX", "NUS RX") if app == "qplus_app" else ())
        dismiss = (
            f"{profile.shutdown_count} × {_hex(keeson_codec.ALARM_DISMISS)}, "
            f"{profile.shutdown_delay_ms} ms apart"
            if profile.shutdown_count
            else "none"
        )
        rows.append(
            (
                f"[{_c033_heading(app)}](#{_anchor(_c033_heading(app))})",
                f"`{app}`",
                _c033_layouts(app),
                _c033_frame(app),
                " / ".join(roles),
                _c033_rename(profile),
                _c033_clock(profile),
                dismiss,
                _c033_alarm(profile),
                _lease(profile),
            )
        )
    return _block(
        _table(
            (
                "Profile",
                "Bed type",
                "Layouts (default bold)",
                "Frame",
                "Write / notify",
                "Rename",
                "Clock",
                "Wake dismissal",
                "Alarm tables",
                "Hold until release",
            ),
            rows,
        )
    )


def _anchor(title: str) -> str:
    return re.sub(r"[^a-z0-9 -]", "", title.lower()).replace(" ", "-")


def render_keeson_app_controls(app: str) -> str:
    """One row per distinct app key, with the layouts that show it."""
    layouts = keeson_profiles.APP_LAYOUTS[app]
    rows: dict[tuple[str, ...], list[str]] = {}
    for layout in layouts:
        profile = keeson_profiles.app_profile(app, layout)
        controller = _c033_controller(profile)
        for action in profile.actions:
            cover = {"head_up": "Back", "head_down": "Back", "foot_up": "Legs", "foot_down": "Legs"}
            label = action.name + (f" ({cover[action.key]} cover)" if action.key in cover else "")
            row = (
                label,
                f"`{action.key}`",
                f"`{action.mask:#x}`",
                _hex(controller._frame(action.mask)),
                f"`{action.mode}`",
            )
            rows.setdefault(row, []).append(layout)
    header = ("App label", "Key", "Mask", "Frame", "Behavior")
    if len(layouts) == 1:
        return _block(_table(header, rows))
    return _block(
        _table((*header, "Layouts"), ((*row, ", ".join(found)) for row, found in rows.items()))
    )


def render_keeson_qplus_sides() -> str:
    profile = keeson_profiles.app_profile("qplus_app", "M2")
    rows = []
    for side, name in (("both", "Both"), ("side_a", "Side A"), ("side_b", "Side B")):
        controller = _c033_controller(profile, side)
        rows.append(
            (
                f"{name} (`{side}`)",
                _hex(controller._frame(keeson_codec.HEAD_UP)),
                _hex(controller._frame(keeson_codec.RELEASE)),
            )
        )
    mx = keeson_profiles.app_profile("qplus_app", "MX")
    assert mx.p2_keys is not None
    keys = ", ".join(f"`{key:#x}`" for key in sorted(mx.p2_keys))
    return _block(
        _table(("Selector", "Head up", "Release"), rows),
        f"MX keys the sparse builder accepts (any other key is sent as zero): {keys}.",
    )


def render_keeson_serta_mp() -> str:
    head, foot = serta_mp_module.HEAD_TABLE, serta_mp_module.FOOT_TABLE

    def calibration(name: str, table: tuple[int, ...]) -> list[str]:
        return _table(
            (name, *(f"+{step}" for step in range(10))),
            (
                (
                    f"{start}°",
                    *(str(v) for v in table[start : start + 10]),
                    *[""] * (10 - len(table[start : start + 10])),
                )
                for start in range(0, len(table), 10)
            ),
        )

    other = 0x8000
    targets = _table(
        ("Target", "Head field", "Foot field", "Example"),
        (
            (
                "Back slider or `set_position`",
                "head table value",
                f"`{other:#x}`",
                f"Back 30°: {_hex(keeson_codec.position_target(head[30], other))}",
            ),
            (
                "Legs slider or `set_position`",
                f"`{other:#x}`",
                "foot table value",
                f"Legs 15°: {_hex(keeson_codec.position_target(other, foot[15]))}",
            ),
            (
                "Local memory recall",
                "head table value",
                "foot table value",
                f"Slot 1 default (15°/35°): {_hex(keeson_codec.position_target(head[15], foot[35]))}",
            ),
        ),
    )
    return _block(
        "#### Position targets",
        targets,
        "#### Calibration tables",
        "Pulse value per degree, used for targets and for feedback conversion.",
        calibration("Head", head),
        calibration("Foot", foot),
    )


BLOCKS: list[Block] = [
    (GUIDE, "keeson-profiles", render_keeson_profiles),
    (GUIDE, "keeson-transports", render_keeson_transports),
    (GUIDE, "keeson-carriers", render_keeson_carriers),
    (GUIDE, "keeson-keys", render_keeson_keys),
    (GUIDE, "keeson-sino", render_keeson_sino),
    (GUIDE, "keeson-adjustable-lite", render_keeson_adjustable_lite),
    (GUIDE, "keeson-restonic", render_keeson_restonic),
    (GUIDE, "keeson-innova", render_keeson_innova),
    (GUIDE, "keeson-okin-apps", render_keeson_okin_apps),
    (GUIDE, "keeson-ore", render_keeson_ore),
    (GUIDE, "keeson-apps", render_keeson_apps),
    *(
        (
            GUIDE,
            f"keeson-app-{app.replace('_', '-')}",
            lambda app=app: render_keeson_app_controls(app),
        )
        for app in keeson_profiles.APP_LAYOUTS
    ),
    (GUIDE, "keeson-qplus-sides", render_keeson_qplus_sides),
    (GUIDE, "keeson-serta-mp", render_keeson_serta_mp),
    (GUIDE, "keeson-controllers", render_keeson_controllers),
    (GUIDE, "keeson-glideaway", render_keeson_glideaway),
    (GUIDE, "keeson-scott-living", render_keeson_scott_living),
]
