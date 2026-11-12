"""Generated blocks of the Okin N-frame codec guide."""

from __future__ import annotations

from custom_components.adjustable_bed.beds.adjustable_lumbar import (
    REFRESH_MS,
    RELEASE_STOP_OFFSETS_S,
    SAVE_HOLD_MS,
)
from custom_components.adjustable_bed.beds.okin_uuid.controller import (
    OKIN_UUID_REMOTES,
    OkinUuidComplexCommand,
)
from custom_components.adjustable_bed.beds.okin_uuid.remotes import (
    OKIN_UUID_VARIANT_LABELS,
)
from custom_components.adjustable_bed.codec import keeson as keeson_codec
from custom_components.adjustable_bed.codec import okin_nframe as okin_codec
from custom_components.adjustable_bed.const import (
    NORDIC_UART_READ_CHAR_UUID,
    NORDIC_UART_SERVICE_UUID,
    NORDIC_UART_WRITE_CHAR_UUID,
)
from custom_components.adjustable_bed.profiles import n32_motion_bed as n32
from custom_components.adjustable_bed.profiles import okin_nframe as okin_profiles
from custom_components.adjustable_bed.profiles.adjustable_bed import (
    PROFILES as ADJUSTABLE_BED_PROFILES,
)
from custom_components.adjustable_bed.profiles.n32_motion_bed import N32
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
    "foot_up": "Foot up",
    "foot_down": "Foot down",
    "neck_tilt_up": "Neck tilt up",
    "neck_tilt_down": "Neck tilt down",
    "motor_stop": "STOP / release",
    "preset_flat": "Flat",
    "preset_tv": "TV",
    "preset_zero_gravity": "Zero-G",
    "preset_anti_snore": "Anti-snore",
    "preset_lounge": "Lounge",
    "preset_memory_1": "Memory 1",
    "preset_memory_2": "Memory 2",
    "stop": "STOP / release",
    "memory": "Custom Mode (memory)",
    "store_memory_1": "Store memory 1",
    "store_memory_2": "Store memory 2",
    "massage_toggle": "Massage toggle",
    "massage_exit": "Massage exit",
    "massage_intensity_up": "Massage intensity up",
    "massage_intensity_down": "Massage intensity down",
    "massage_wave1": "Massage wave 1",
    "massage_wave2": "Massage wave 2",
    "massage_wave3": "Massage wave 3",
    "light_toggle": "Under-bed light toggle",
    "inclined_left": "Inclined Left",
    "inclined_middle": "Inclined Middle",
    "inclined_right": "Inclined Right",
    "lounge": "Lounge / Reading",
    "incline": "Incline",
    "light_on": "Light on",
    "light_off": "Light off",
    "wave_1": "Massage wave 1",
    "wave_2": "Massage wave 2",
    "wave_3": "Massage wave 3",
    "massage_timer_step": "Massage timer step",
    "save_memory_1": "Save memory 1",
    "save_memory_2": "Save memory 2",
    "save_memory_3": "Save memory 3",
    "save_memory_4": "Save memory 4",
    "reading": "Reading",
    "massage_head_strength": "Head massage strength step",
    "massage_foot_strength": "Foot massage strength step",
    "massage_timer": "Massage timer step",
    "flat_zero_g": "Flat + Zero-G chord",
}
_OKIN_GROUPS = {
    "Okimat": (okin_profiles.OKIMAT,),
    "DewertOkin": (okin_profiles.DEWERTOKIN,),
    "RF ECO BT": (okin_profiles.RF_ECO_BT,),
    "Customatic": tuple(okin_profiles.CUSTOMATIC_PROFILES.values()),
    "Leggett Okin": tuple(okin_profiles.LEGGETT_PROFILES.values()),
    "CB24": (okin_profiles.OKIN_CB24,),
    "DOT": (okin_profiles.OKIN_DOT,),
    "SIMMONS": tuple(okin_profiles.SIMMONS_PROFILES.values()),
    "SleepEase": (okin_profiles.DOUBLESLEEP,),
    "Sleepy's legacy CB25": (okin_profiles.SLEEPYS_BOX25_LEGACY,),
    "AdjustableM5X4": tuple(
        {id(p): p for p in okin_profiles.STARCODE_ABM5_4_PROFILES.values()}.values()
    ),
    "eShine": tuple(okin_profiles.ESHINE_PROFILES.values()),
    "Okin CST": tuple(okin_profiles.CST_PROFILES.values()),
    "OKIN Bedding apps": tuple(okin_profiles.BEDDING_PROFILES.values()),
    "N32 Motion Bed": (N32,),
    "Resident Adjustable Base": (okin_profiles.RESIDENT,),
    "Okin 64-Bit": tuple(okin_profiles.OKIN_64BIT_PROFILES.values()),
    "Adjustable bed (Lumbar)": tuple(okin_profiles.ADJUSTABLE_LUMBAR_PROFILES.values()),
}


def _okin_profiles() -> list[okin_profiles.OkinNFrameProfile]:
    return [profile for group in _OKIN_GROUPS.values() for profile in group]


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


def _okin_hold(profile: okin_profiles.OkinNFrameProfile) -> tuple[str, str, str]:
    hold = profile.hold
    refresh = f"{hold.repeat_ms} ms" if hold.repeat_ms else "entry pulse delay"
    repeats = str(hold.repeats) if hold.repeats else "entry pulse count"
    if profile.execution.hold == "stream":
        repeats += "; until release with a renewable hold"
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
    "keeson_e6": "Keeson E6 frame; inclined keys plain",
}
_WRITES = {
    "response": "with response",
    "no_response": "without response",
    "characteristic": "from the characteristic's properties",
}


# AdjustableM5X4 selectors whose movement is a Keeson E6 or A5 5A frame.
_OKIN_OWN_MOTION = frozenset({"starcode_abm5_4_box15", "starcode_abm5_4_box1220"})
# The OKIN Bedding apps stream every action at 100 ms until its own deadline.
_DEADLINE = "held to its deadline, 2 STOP"


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
        (
            (profile.name, *_okin_hold(profile))
            if profile.key not in _OKIN_OWN_MOTION
            else (profile.name, "n/a", "n/a", "moves with its own frames")
            for profile in profiles
        ),
    )
    one_shot = _table(
        (
            "Profile",
            "Presets and recall",
            "Memory recall",
            "Memory save",
            "Sync, child lock",
            "Light, massage",
            "Control mode",
        ),
        (
            (profile.name, *([_DEADLINE] * 3), "n/a", _DEADLINE, "n/a")
            if profile.key in okin_profiles.BEDDING_PROFILES
            else (
                profile.name,
                _okin_tap(profile.recall),
                _okin_tap(profile.memory_recall or profile.recall),
                _okin_tap(profile.memory_save)
                + (" (or the handset's hold)" if not profile.keys else ""),
                _okin_tap(profile.long_press),
                _okin_tap(profile.tap)
                if not profile.keys
                or any(key.startswith(("light", "massage")) for key in profile.keys)
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
        f"{okin_profiles.CUSTOMATIC_APP_HOLD_MS} ms with no STOP. SIMMONS saves Custom "
        f"Mode by holding its recall key {okin_profiles.SIMMONS_SAVE_HOLD_MS} ms. "
        "AdjustableM5X4 presets and recalls are held keys on its refresh; it streams "
        f"Flat for {okin_profiles.STARCODE_ABM5_4_FLAT_HOLD_MS} ms and saves or resets for "
        f"{okin_profiles.STARCODE_ABM5_4_SAVE_HOLD_MS} ms. SleepEase P1 presets are held "
        "keys on its refresh too, as are eShine presets, its Flat + Zero-G chord and its "
        "light; its massage keys are one write. The OKIN Bedding apps hold every action "
        f"to its own deadline, saves for {okin_profiles.BEDDING_SAVE_HOLD_MS} ms; see their "
        "profiles.",
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
        ("Service", NORDIC_UART_SERVICE_UUID, "40-bit profiles"),
        ("Write", NORDIC_UART_WRITE_CHAR_UUID, "40-bit profiles"),
        (
            "Notify",
            NORDIC_UART_READ_CHAR_UUID,
            "SIMMONS, SleepEase, Sleepy's, AdjustableM5X4, eShine",
        ),
    )
    return _block(
        _table(
            ("Role", "UUID", "Used by"), ((role, f"`{uuid}`", users) for role, uuid, users in rows)
        ),
        f"The settings channel opens with {_hex(okin_codec.SETTINGS_INIT)} after subscribing. "
        "SIMMONS also accepts FFE5/FFE9 with FFE0/FFE4, and AdjustableM5X4 two more "
        "transports; see their profiles.",
    )


def _okin_frame(profile: okin_profiles.OkinNFrameProfile, word: int, name: str = "") -> str:
    if profile.envelope == "keeson_e6" and name not in profile.plain_keys:
        return _hex(keeson_codec.frame(word, header=0xE6, side=0))
    if profile.width == 5:
        return _hex(okin_codec.frame40(word))
    return _hex(okin_codec.frame(word, profile.width))


def _okin_key_table(
    profiles: tuple[okin_profiles.OkinNFrameProfile, ...], *, envelope: bool
) -> list[str]:
    names: list[str] = []
    for profile in sorted(profiles, key=lambda profile: -len(profile.keys)):
        names += [name for name in profile.keys if name not in names]
    longs: list[str] = []
    for profile in profiles:
        longs += [name for name in profile.long_keys if name not in longs]
    multi = len(profiles) > 1
    header = ["Command", "Word"]
    if multi:
        header.append("Profiles")
    header.append("Frame")
    if envelope:
        header.append("Envelope (R0)")
    rows = []
    for table, width in (("keys", 4), ("long_keys", 8)):
        for name in names if table == "keys" else longs:
            words = {
                getattr(profile, table)[name]
                for profile in profiles
                if name in getattr(profile, table)
            }
            for word in sorted(words):
                users = [p for p in profiles if getattr(p, table).get(name) == word]
                label = _OKIN_KEY_LABELS.get(name, f"`{name}`")
                if profiles[0] is N32:
                    label = {
                        "head_up": "Upper up",
                        "head_down": "Upper down",
                        "foot_up": "Lower up",
                        "foot_down": "Lower down",
                        "cervical_up": "Cervical up",
                        "cervical_down": "Cervical down",
                        **n32.PRESET_LABELS,
                    }.get(name, label)
                if name.isdigit():
                    label = f"Index {name}"
                digits = 2 * (8 if table == "long_keys" else max(width, profiles[0].width))
                if profiles[0].width == 12:
                    # The two 32-bit fields; the trailing padding is always zero.
                    row = [label, f"`{word >> 64:08X} {(word >> 32) & 0xFFFFFFFF:08X}`"]
                else:
                    row = [label, f"`0x{word:0{min(digits, 16)}X}`"]
                if multi:
                    labels = [p.name for p in users]
                    row.append(", ".join(labels) if len(users) < len(profiles) else "all")
                if table == "long_keys":
                    row.append(_hex(okin_codec.frame(word, 8)))
                else:
                    row.append(" or ".join(sorted({_okin_frame(p, word, name) for p in users})))
                if envelope:
                    row.append(_hex(okin_codec.gateway_frame(word)))
                rows.append(tuple(row))
    if any(0 in profile.keys.values() for profile in profiles):
        return _table(tuple(header), rows)
    stop_frames = " or ".join(sorted({_okin_frame(p, 0) for p in profiles}))
    zero = "`00000000 00000000`" if profiles[0].width == 12 else "`0x00000000`"
    stop = ["STOP / release", zero, *(["all"] if multi else []), stop_frames]
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
        "#### CB24 keys",
        _okin_key_table(_OKIN_GROUPS["CB24"], envelope=False),
        "Legacy CB24 replaces the last byte with `AA` (Side A) or `BB` (Side B) for one "
        "side; held motors send the sum of their words.",
        "#### SIMMONS keys",
        _okin_key_table(_OKIN_GROUPS["SIMMONS"], envelope=False),
        "SmartBed and unmatched names send the 40-bit frame, OKIN names the Keeson E6 "
        "frame. The inclined keys keep the 40-bit frame on both.",
        "#### SleepEase keys",
        _okin_key_table(_OKIN_GROUPS["SleepEase"], envelope=False),
        "SleepDriver (P1) words by the app's command index; index 1 is STOP. The "
        "profile's other static frames and the XiaoBao (P2) and P3 packets are listed "
        "in its section.",
        "#### Sleepy's legacy CB25 keys",
        _okin_key_table(_OKIN_GROUPS["Sleepy's legacy CB25"], envelope=False),
        "#### AdjustableM5X4 keys",
        _okin_key_table(_OKIN_GROUPS["AdjustableM5X4"], envelope=False),
        "Keyed by the app's action names. BOX15 and BOX1220 move with their own "
        "frames, so their profiles hold only the shared keys; BOX25_STAR sends "
        "StarCode only.",
        "#### eShine keys",
        _okin_key_table(_OKIN_GROUPS["eShine"], envelope=False),
        "The app's one key table; each product selector exposes the rows listed for it.",
        "#### Okin CST keys",
        _okin_key_table(_OKIN_GROUPS["Okin CST"], envelope=False),
        "The word column shows the primary and secondary fields. Each product lists "
        "the controls it supports; held motors send the OR of their primary words.",
        "#### OKIN Bedding app keys",
        _okin_key_table(_OKIN_GROUPS["OKIN Bedding apps"], envelope=False),
        "Each app's literal action table, by the app's action names.",
        "#### Resident Adjustable Base keys",
        _okin_key_table(_OKIN_GROUPS["Resident Adjustable Base"], envelope=False),
        "#### Okin 64-Bit keys",
        _okin_key_table(_OKIN_GROUPS["Okin 64-Bit"], envelope=False),
        "#### Adjustable bed (Lumbar) keys",
        _okin_key_table(_OKIN_GROUPS["Adjustable bed (Lumbar)"], envelope=False),
        "The 25_42_02 and 36_33_04a tables share these words; 35_22_01 sends StarCode "
        "`5A` frames, listed in its profile.",
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


def render_adjustable_bed() -> str:
    rows = (
        (profile.key, profile.table, action, _hex(frame))
        for profile in ADJUSTABLE_BED_PROFILES.values()
        for action, frame in profile.frames.items()
    )
    release = (
        "STOP at "
        + " and ".join(str(round(offset * 1000)) for offset in RELEASE_STOP_OFFSETS_S)
        + " ms"
    )
    return _block(
        _table(("Profile", "Asset", "Control", "Bytes"), rows),
        _table(
            ("Gesture", "Schedule", "Release"),
            (
                ("Touch hold", f"Immediate, every {REFRESH_MS} ms", release),
                ("Save named preset", f"Hold chord for {SAVE_HOLD_MS} ms", release),
                (
                    "Speech motor P1/P3",
                    f"{REFRESH_MS} ms stream, bounded by entry pulse count",
                    "Voice STOP and ordinary release",
                ),
                (
                    "Speech motor P2",
                    f"One start, bounded by entry pulse count × {REFRESH_MS} ms",
                    "Voice STOP and ordinary release",
                ),
                (
                    "Speech preset, massage or light",
                    f"Pre-STOP, two writes {REFRESH_MS} ms apart",
                    "No post-STOP",
                ),
                ("Massage query", "Once on request", "None"),
            ),
        ),
    )


def render_resident_session() -> str:
    from custom_components.adjustable_bed.beds.resident import controller as resident

    p = okin_profiles
    return _block(
        _table(
            ("Role", "Service", "Characteristic"),
            (
                (
                    "Control (with response)",
                    f"`{okin_codec.SERVICE_UUID}`",
                    f"`{okin_codec.WRITE_UUID}`",
                ),
                ("Notification", f"`{okin_codec.SERVICE_UUID}`", f"`{resident.NOTIFY_UUID}`"),
                ("Model read (ignored)", f"`{resident.INFO_SERVICE}`", f"`{resident.MODEL_UUID}`"),
            ),
        ),
        _table(
            ("Operation", "Frame", "Schedule"),
            (
                (
                    "Massage query",
                    _hex(resident.QUERY_MASSAGE),
                    f"now and +{p.RESIDENT_QUERY_DELAY_MS} ms on startup and massage release",
                ),
                (
                    "Clock query",
                    _hex(resident.QUERY_CLOCK),
                    f"{p.RESIDENT_CLOCK_QUERY_DELAY_MS} ms after clock setting",
                ),
                (
                    "Local clock (2026-11-10 07:08:09)",
                    _hex(okin_codec.calendar_record(0xE7, (126, 10, 10, 7, 8, 9))),
                    f"once at connect +{p.RESIDENT_CLOCK_DELAY_MS} ms, also manual sync",
                ),
            ),
        ),
        f"Model read: connect +{p.RESIDENT_INFO_DELAY_MS} ms; notification retry gaps: "
        + "/".join(str(ms) for ms in p.RESIDENT_NOTIFY_RETRIES_MS)
        + " ms. "
        + "Name prefixes (case-insensitive): "
        + ", ".join(f"`{v}`" for v in p.RESIDENT_NAME_PREFIXES)
        + ".",
    )


def render_n32_session() -> str:
    from datetime import datetime

    return _block(
        _table(
            ("Role", "UUID"),
            (
                ("Service", f"`{NORDIC_UART_SERVICE_UUID}`"),
                ("Write, with response", f"`{NORDIC_UART_WRITE_CHAR_UUID}`"),
                ("Notify or indicate", f"`{NORDIC_UART_READ_CHAR_UUID}`"),
            ),
        ),
        _table(
            ("Operation", "Frame", "Schedule"),
            (
                *(
                    (f"Query slot {slot}", _hex(n32.query_frame(slot)), "startup and on request")
                    for slot in n32.SLOTS
                ),
                (
                    "Clock (2026-11-12 23:59:01)",
                    _hex(n32.clock_frame(datetime(2026, 11, 12, 23, 59, 1))),
                    f"connect +{n32.CLOCK_DELAY_S * 1000:g} ms",
                ),
                *(
                    (
                        f"Delete slot {slot}",
                        _hex(n32.alarm_frame(slot, 0, 0, 0, 0, 0)),
                        "then query the same slot",
                    )
                    for slot in n32.SLOTS
                ),
                (
                    "Slot 1, Monday 06:30, M1",
                    _hex(n32.alarm_frame(1, 6, 30, n32.alarm_week((0,)), n32.ALARM_MODES["m1"], 1)),
                    "set then query slot 1",
                ),
            ),
        ),
        _table(
            ("Property", "Value"),
            (
                ("Held refresh", f"{n32.REFRESH_MS} ms"),
                ("Frame-button threshold", f"{n32.FRAME_HOLD_MS} ms"),
                ("Release", f"{N32.hold.releases} STOP"),
                ("Alarm slots", ", ".join(map(str, n32.SLOTS))),
                (
                    "Alarm modes",
                    ", ".join(f"{name}: {code}" for name, code in n32.ALARM_MODES.items()),
                ),
            ),
        ),
    )


BLOCKS: list[Block] = [
    (GUIDE, "n32-session", render_n32_session),
    (GUIDE, "adjustable-bed-commands", render_adjustable_bed),
    (GUIDE, "resident-session", render_resident_session),
    (GUIDE, "okin-nframe-profiles", render_okin_nframe_profiles),
    (GUIDE, "okin-nframe-transports", render_okin_nframe_transports),
    (GUIDE, "okin-nframe-keys", render_okin_nframe_keys),
    (GUIDE, "okin-nframe-okimat", render_okin_nframe_okimat),
]
