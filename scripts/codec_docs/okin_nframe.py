"""Generated blocks of the Okin N-frame codec guide."""

from __future__ import annotations

from custom_components.adjustable_bed.beds.okin_uuid import (
    OKIN_UUID_REMOTES,
    OkinUuidComplexCommand,
)
from custom_components.adjustable_bed.beds.okin_uuid_remotes import (
    OKIN_UUID_VARIANT_LABELS,
)
from custom_components.adjustable_bed.codec import okin_nframe as okin_codec
from custom_components.adjustable_bed.profiles import okin_nframe as okin_profiles
from scripts.codec_docs._common import Block, _block, _hex, _table

GUIDE = "docs/beds/okin-nframe.md"

_OKIN_KEY_LABELS = {
    "head_up": "Head up",
    "head_down": "Head down",
    "back_up": "Back up",
    "back_down": "Back down",
    "feet_up": "Feet up",
    "feet_down": "Feet down",
    "legs_up": "Legs up",
    "legs_down": "Legs down",
    "pillow_up": "Pillow up",
    "pillow_down": "Pillow down",
    "lumbar_up": "Lumbar up",
    "lumbar_down": "Lumbar down",
    "stair_out": "Stair out (open)",
    "stair_in": "Stair in (close)",
    "flat": "Flat",
    "restored_flat": "Restored Flat",
    "zero_g": "Zero-G",
    "tv": "TV",
    "anti_snore": "Anti-snore / Snore",
    "memory_1": "Memory 1",
    "memory_2": "Memory 2",
    "memory_3": "Memory 3",
    "memory_4": "Memory 4",
    "memory_store": "Memory store (arm)",
    "memory_flat": "Memory page: Flat",
    "memory_zg": "Memory page: ZG",
    "memory_anti": "Memory page: ANTI",
    "memory_program": "Memory page: Program",
    "memory_incline": "Memory page: Incline",
    "massage_wave": "Wave massage",
    "massage_head": "Head massage",
    "massage_foot": "Foot massage",
    "massage_off": "Massage off",
    "massage_head_up": "Head massage up",
    "massage_head_down": "Head massage down",
    "massage_foot_up": "Foot massage up",
    "massage_foot_down": "Foot massage down",
    "massage_step": "Massage on/off",
    "massage_wave_step": "Massage wave mode step",
    "light": "Under-bed light toggle",
    "control_mode_press_and_hold": "Control mode: press-and-hold",
    "control_mode_press_and_release": "Control mode: press-and-release",
    "sleep_cancel": "Sleep timer cancel",
    "alarm_cancel": "Alarm cancel / stop",
    "cu170_stop": "CU170 stop (DUMMY)",
}
_OKIN_GROUPS = {
    "Okimat": (okin_profiles.OKIMAT,),
    "DewertOkin": (okin_profiles.DEWERTOKIN,),
    "RF ECO BT": (okin_profiles.RF_ECO_BT,),
    "Customatic": tuple(okin_profiles.CUSTOMATIC_PROFILES.values()),
    "Leggett Okin": tuple(okin_profiles.LEGGETT_PROFILES.values()),
}


def _okin_profiles() -> list[okin_profiles.OkinNFrameProfile]:
    return [profile for group in _OKIN_GROUPS.values() for profile in group]


def bed_types() -> dict[str, tuple[str, ...]]:
    """Bed types per profile, as the profile summary lists them."""
    return {profile.key: profile.bed_types for profile in _okin_profiles()}


def _okin_tap(tap: okin_profiles.Tap | None) -> str:
    if tap is None:
        return "n/a"
    if tap.repeats > 1:
        sends = f"{tap.repeats} × {tap.repeat_ms} ms"
    elif tap.releases and tap.repeat_ms:
        sends = f"once, then {tap.repeat_ms} ms"
    else:
        sends = "once"
    return f"{sends}, {tap.releases} STOP" if tap.releases else f"{sends}, no STOP"


def _okin_hold(hold: okin_profiles.Hold) -> tuple[str, str, str]:
    refresh = f"{hold.repeat_ms} ms" if hold.repeat_ms else "entry pulse delay"
    repeats = str(hold.repeats) if hold.repeats else "entry pulse count"
    if not hold.releases:
        release = "none (refresh ends)"
    else:
        release = f"{hold.releases} STOP"
        if hold.releases > 1:
            release += f" at {hold.release_ms} ms"
        if hold.release_after_ms:
            release += f", {hold.release_after_ms} ms after the last write"
    return refresh, repeats, release


_ENVELOPES = {
    "plain": "plain frame",
    "gateway_detected": "plain; RF-Gateway envelope when detected",
    "revision_selector": "plain (R1) or envelope (R0), by selector characteristic",
}
_WRITES = {
    "response": "with response",
    "no_response": "without response",
    "characteristic": "from the characteristic's properties",
}


def render_okin_nframe_profiles() -> str:
    profiles = _okin_profiles()
    summary = _table(
        ("Profile", "Key", "Bed types", "Word", "Frame", "Write", "Axes", "Memory"),
        (
            (
                profile.name,
                f"`{profile.key}`",
                ", ".join(f"`{bed_type}`" for bed_type in profile.bed_types),
                f"{profile.width * 8}-bit",
                _ENVELOPES[profile.envelope],
                _WRITES[profile.write],
                ", ".join(profile.axes) or "handset table",
                str(profile.memory_slots) if profile.keys else "handset table",
            )
            for profile in profiles
        ),
    )
    hold = _table(
        ("Profile", "Hold refresh", "Repeats", "Release"),
        ((profile.name, *_okin_hold(profile.hold)) for profile in profiles),
    )
    one_shot = _table(
        (
            "Profile",
            "Presets and recall",
            "Memory save",
            "Sync, child lock",
            "Light, massage",
            "Control mode",
        ),
        (
            (
                profile.name,
                _okin_tap(profile.recall),
                _okin_tap(profile.memory_save)
                + (" (or the handset's hold)" if profile is okin_profiles.OKIMAT else ""),
                _okin_tap(profile.long_press),
                _okin_tap(profile.tap)
                if not profile.keys or "light" in profile.keys or "massage_off" in profile.keys
                else "n/a",
                _okin_tap(profile.control_mode),
            )
            for profile in profiles
        ),
    )
    store_ms, slot_ms = okin_profiles.LEGGETT_STORE_HOLD_MS
    return _block(
        "### Profile summary",
        summary,
        "### Hold and release timing",
        hold,
        "Entry pulse settings are the configured motor pulse count and delay.",
        "### One-shot timing",
        one_shot,
        f"Leggett Okin profiles also stream Flat for {okin_profiles.LEGGETT_FLAT_HOLD_MS} ms "
        f"and program a favorite by holding the store key {store_ms} ms, then the slot "
        f"{slot_ms} ms. Customatic named memory controls hold "
        f"{okin_profiles.CUSTOMATIC_APP_HOLD_MS} ms with no STOP.",
    )


def render_okin_nframe_transports() -> str:
    rows = (
        ("Service", okin_codec.SERVICE_UUID, "All profiles"),
        ("Write", okin_codec.WRITE_UUID, "All profiles"),
        ("Position notify", okin_codec.POSITION_UUID, "Okimat (receivers that expose it)"),
        ("Status notify", okin_codec.STATUS_UUID, "Leggett Okin"),
        (
            "Revision selector",
            okin_codec.REVISION_SELECTOR_UUID,
            "Leggett Okin (presence selects R1)",
        ),
        ("Settings write", okin_codec.SETTINGS_WRITE_UUID, "Leggett Okin Prodigy profiles"),
        ("Settings notify", okin_codec.SETTINGS_NOTIFY_UUID, "Leggett Okin Prodigy profiles"),
    )
    return _block(
        _table(
            ("Role", "UUID", "Used by"), ((role, f"`{uuid}`", users) for role, uuid, users in rows)
        ),
        f"The settings channel opens with {_hex(okin_codec.SETTINGS_INIT)} after subscribing.",
    )


def _okin_key_table(
    profiles: tuple[okin_profiles.OkinNFrameProfile, ...], *, envelope: bool
) -> list[str]:
    names: list[str] = []
    for profile in sorted(profiles, key=lambda profile: -len(profile.keys)):
        names += [name for name in profile.keys if name not in names]
    multi = len(profiles) > 1
    header = ["Command", "Word"]
    if multi:
        header.append("Profiles")
    header.append("Frame")
    if envelope:
        header.append("Envelope (R0)")
    rows = []
    for name in names:
        words = {profile.keys[name] for profile in profiles if name in profile.keys}
        for word in sorted(words):
            row = [_OKIN_KEY_LABELS[name], f"`0x{word:08X}`"]
            if multi:
                users = [p.name for p in profiles if p.keys.get(name) == word]
                row.append(", ".join(users) if len(users) < len(profiles) else "all")
            row.append(_hex(okin_codec.frame(word)))
            if envelope:
                row.append(_hex(okin_codec.gateway_frame(word)))
            rows.append(tuple(row))
    stop = ["STOP / release", "`0x00000000`", *(["all"] if multi else []), _hex(okin_codec.STOP)]
    if envelope:
        stop.append(_hex(okin_codec.gateway_frame(0)))
    return _table(tuple(header), [*rows, tuple(stop)])


def render_okin_nframe_keys() -> str:
    return _block(
        "#### DewertOkin keys",
        _okin_key_table(_OKIN_GROUPS["DewertOkin"], envelope=True),
        "#### RF ECO BT keys",
        _okin_key_table(_OKIN_GROUPS["RF ECO BT"], envelope=False)[:-1],
        "The stair profile has no STOP: release ends the refresh.",
        "#### Customatic keys",
        _okin_key_table(_OKIN_GROUPS["Customatic"], envelope=False),
        "#### Leggett Okin keys",
        _okin_key_table(_OKIN_GROUPS["Leggett Okin"], envelope=True),
    )


def _okin_remote_words(field: str) -> dict[int, list[str]]:
    words: dict[int, list[str]] = {}
    for code, remote in OKIN_UUID_REMOTES.items():
        if code not in OKIN_UUID_VARIANT_LABELS:
            continue
        value = getattr(remote, field)
        if isinstance(value, OkinUuidComplexCommand):
            value = value.data
        if value is not None:
            words.setdefault(value, []).append(code)
    return words


def render_okin_nframe_okimat() -> str:
    fields = (
        ("Back up / down", ("back_up", "back_down")),
        ("Legs up / down", ("legs_up", "legs_down")),
        ("Head (tilt) up / down", ("head_up", "head_down")),
        ("Feet up / down", ("feet_up", "feet_down")),
        ("Flat", ("flat",)),
        ("Memory 1-4", ("memory_1", "memory_2", "memory_3", "memory_4")),
        ("Memory save", ("memory_save",)),
        ("Under-bed light", ("toggle_lights",)),
        ("Sync both sides", ("sync",)),
        ("Child lock", ("child_lock",)),
        ("Zero-gravity", ("zero_gravity",)),
    )
    codes = [code for code in OKIN_UUID_REMOTES if code in OKIN_UUID_VARIANT_LABELS]
    rows = []
    for label, names in fields:
        words: set[int] = set()
        users: set[str] = set()
        for name in names:
            for word, remotes in _okin_remote_words(name).items():
                words.add(word)
                users.update(remotes)
        rows.append(
            (label, str(len(users)), ", ".join(f"`0x{word:08X}`" for word in sorted(words)))
        )
    massage = [code for code in codes if OKIN_UUID_REMOTES[code].massage]
    rows.append(("Massage", str(len(massage)), "per handset"))
    timed = sorted(
        {
            (save.count, save.wait_time)
            for code in codes
            if isinstance(save := OKIN_UUID_REMOTES[code].memory_save, OkinUuidComplexCommand)
        }
    )
    flats = _okin_remote_words("flat")
    flat_table = _table(
        ("Flat word", "Codes"),
        (
            (f"`0x{word:08X}`", ", ".join(sorted(users, key=int)))
            for word, users in sorted(flats.items())
        ),
    )
    slots: dict[int, list[str]] = {}
    for code in codes:
        remote = OKIN_UUID_REMOTES[code]
        keys = (remote.memory_1, remote.memory_2, remote.memory_3, remote.memory_4)
        top = max((slot for slot, key in enumerate(keys, 1) if key is not None), default=0)
        if top:
            slots.setdefault(top, []).append(code)
    slot_table = _table(
        ("Memory slots", "Codes"),
        ((str(top), ", ".join(sorted(users, key=int))) for top, users in sorted(slots.items())),
    )
    return _block(
        f"{len(codes)} selectable handset codes. Each row counts the codes that define the "
        "key and lists every command word they use for it.",
        _table(("Key", "Codes", "Command words"), rows),
        "Handset memory-save holds: "
        + ", ".join(f"{count} × {wait} ms" for count, wait in timed)
        + ". Other handsets use the profile's default memory save.",
        "Flat words per handset:",
        flat_table,
        "Memory slots per handset (the highest slot each code defines):",
        slot_table,
    )


BLOCKS: list[Block] = [
    (GUIDE, "okin-nframe-profiles", render_okin_nframe_profiles),
    (GUIDE, "okin-nframe-transports", render_okin_nframe_transports),
    (GUIDE, "okin-nframe-keys", render_okin_nframe_keys),
    (GUIDE, "okin-nframe-okimat", render_okin_nframe_okimat),
]
