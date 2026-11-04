"""Generated blocks of the FFFF frame codec guide."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from custom_components.adjustable_bed.codec import ff_frame as ff_codec
from custom_components.adjustable_bed.profiles import ff_frame as ff_profiles
from scripts.codec_docs._common import Block, _block, _hex, _table

GUIDE = "docs/beds/ff_frame.md"

C = ff_profiles.SolaceCommands
SOLACE = ff_profiles.SOLACE_PROFILES
_ROUTE_NAMES = {
    "common": "Common",
    "home_k1": "Home K1",
    "home_k2": "Home K2",
    "motion_flex": "MotionFlex",
    "woosa": "Woosa Sleep",
    "legacy_s4_y": "Legacy S4-Y",
    "unverified": "Unverified",
}
_FF_QUERIES = {"q1": "Q1", "q2": "Q2", "home_k2": "Q1 (Q2 for compound names)", "woosa": "Woosa"}
_FF_AXES: dict[ff_profiles.Axis, tuple[str, bytes, bytes]] = {
    "back": ("Back", C.MOTOR_BACK_UP, C.MOTOR_BACK_DOWN),
    "legs": ("Legs", C.MOTOR_LEGS_UP, C.MOTOR_LEGS_DOWN),
    "head": ("Head", C.MOTOR_HEAD_UP, C.MOTOR_HEAD_DOWN),
    "hip": ("Hip", C.MOTOR_HIP_UP, C.MOTOR_HIP_DOWN),
    "lumbar": ("Lumbar", C.MOTOR_HIP_UP, C.MOTOR_HIP_DOWN),
    "bed_height": ("Bed height", C.MOTOR_LIFT_UP, C.MOTOR_LIFT_DOWN),
    "tilt": ("Tilt", C.MOTOR_TILT_UP, C.MOTOR_TILT_DOWN),
}
# Motion Bed frames named by the app callsite the controller sends.
_MOTION_BED_FRAMES = (
    ("Home startup and sleep configuration", "HomeActivity:321"),
    ("Bed status", "HomeActivity:311"),
    ("Hub module status", "MainMcuActivity:182"),
    ("Motor module startup", "DiandongFragment:319"),
    ("Air module startup", "QinangFragment:133"),
    ("Thermal module startup and status", "LengnuanFragment:183"),
    ("Thermal status (timer on)", "LengnuanFragment:58"),
    ("Audio status", "KuaijieK2MFragment:466"),
    ("Brightness status", "HomeActivity:455"),
    ("Raw positions", "SleepAdjustActivity:255"),
    ("Calibration, sleep configuration and exit status", "HomeActivity:463"),
    ("Calibration debug sample", "SleepDataEntryActivity:293"),
    ("Capture flat calibration", "SleepDataEntryActivity:248"),
    ("Capture side calibration", "SleepDataEntryActivity:253"),
    ("Air status", "AnmoSetActivity:260"),
    ("Pressure status", "PressSetActivity:224"),
    ("Air stop", "QinangFragment:302"),
)


def _routes(test: Callable[[ff_profiles.SolaceProfile], bool]) -> str:
    return (
        ", ".join(_ROUTE_NAMES[key] for key, profile in SOLACE.items() if test(profile)) or "none"
    )


def _has(name: str) -> Callable[[ff_profiles.SolaceProfile], bool]:
    return lambda profile: bool(getattr(profile, name))


def _ff_flags(profile: ff_profiles.SolaceProfile, *names: str) -> str:
    return ", ".join(name.replace("_", " ") for name in names if getattr(profile, name)) or "none"


def _ff_startup(profile: ff_profiles.SolaceProfile) -> str:
    if profile.queries is None:
        return "none"
    if profile.key == "woosa":
        return "Woosa startup schedule"
    clock = "clock, " if profile.clock_sync else ""
    light = ", light status" if profile.clock_sync else ""
    return (
        f"+{profile.query_delay_ms} ms: {clock}{_FF_QUERIES[profile.queries]} queries{light}, "
        f"{profile.query_spacing_ms} ms apart"
    )


def render_ff_frame_profiles() -> str:
    solace = _table(
        (
            "Route",
            "Key",
            "Axes",
            "Presets",
            "Memory",
            "Status query",
            "Massage",
            "Lights",
            "Extras",
        ),
        (
            (
                _ROUTE_NAMES[key],
                f"`{key}`",
                ", ".join(profile.axes),
                "yes" if profile.presets else "no",
                f"{profile.memory_slots} slot{'' if profile.memory_slots == 1 else 's'}",
                _FF_QUERIES[profile.queries] if profile.queries else "none, no notifications",
                _ff_flags(profile, "massage", "circulation"),
                _ff_flags(profile, "light_levels", "light_timer"),
                _ff_flags(profile, "relaxing_bedtime", "audio", "alarm", "clock_sync"),
            )
            for key, profile in SOLACE.items()
        ),
    )
    woosa = SOLACE["woosa"]
    bedsense = ff_profiles.BEDSENSE
    timing = _table(
        ("Profile", "Startup", "Other pacing"),
        (
            *(
                (_ROUTE_NAMES[key], _ff_startup(profile), "none")
                for key, profile in SOLACE.items()
                if key != "woosa"
            ),
            (
                _ROUTE_NAMES["woosa"],
                "Woosa startup schedule",
                f"presets: STOP, {woosa.preset_preamble_ms} ms, preset; massage start steps "
                f"{woosa.massage_step_ms} ms apart; after a save, each preset query "
                f"{woosa.save_requery_ms} ms apart",
            ),
            (
                "BedSense",
                f"read every FFE1 characteristic after {bedsense.read_delay_ms} ms; memory "
                f"queries from +{bedsense.query_start_ms} ms, {bedsense.query_spacing_ms} ms apart",
                f"memory refresh: +{bedsense.query_start_ms} ms, then "
                f"{bedsense.query_spacing_ms} ms apart",
            ),
        ),
    )
    woosa_startup = _table(
        ("Offset", "Bytes (hex)"),
        (
            (f"{offset} ms", _hex(command) if command is not None else "clock")
            for offset, command in ff_profiles.WOOSA_STARTUP
        ),
    )
    layouts = _table(
        ("Type", "Movement axes", "App actions"),
        (
            (
                str(layout),
                ", ".join(axes),
                str(sum(layout in action.variants for action in bedsense.actions.values())),
            )
            for layout, axes in bedsense.layouts.items()
        ),
    )
    commands = ff_profiles.MOTION_BED.commands
    return _block(
        "### Solace routes",
        solace,
        "### Timing",
        "Offsets count from notification start. Movement and STOP timing are in "
        "[STOP and release behavior](#stop-and-release-behavior).",
        timing,
        "### Woosa startup schedule",
        "Both app startup workers, serialized; equal offsets keep their order.",
        woosa_startup,
        "### BedSense layouts",
        layouts,
        "### Motion Bed callsites",
        f"{len(commands)} app callsites over {len(set(commands.values()))} distinct frames, "
        "each gated by layout, module and state.",
    )


def render_ff_frame_transports() -> str:
    return _block(
        _table(
            ("Service", "Write and notify", "Profiles"),
            (
                (
                    f"`{ff_codec.SERVICE_UUID}` (advertised, not required)",
                    f"`{ff_codec.CHARACTERISTIC_UUID}`",
                    "all",
                ),
            ),
        )
    )


def render_ff_frame_motion() -> str:
    return _block(
        _table(
            ("Axis", "Up", "Down", "Routes"),
            (
                (
                    label,
                    _hex(up),
                    _hex(down),
                    _routes(lambda profile, axis=axis: axis in profile.axes),
                )
                for axis, (label, up, down) in _FF_AXES.items()
            ),
        ),
        f"STOP is {_hex(ff_codec.STOP)} on every route. Woosa's leg-down control sends Flat.",
    )


def render_ff_frame_presets() -> str:
    rows = (
        (
            "Flat",
            C.PRESET_FLAT_BED,
            None,
            None,
            None,
            "every route with presets except Legacy S4-Y",
        ),
        ("Flat (legacy all-flat)", C.PRESET_LEGACY_ALL_FLAT, None, None, None, "Legacy S4-Y"),
        ("TV", C.PRESET_TV, C.PRESET_TV_SELECTED, C.PROGRAM_TV, C.PROGRAM_TV_DESELECTED, ""),
        (
            "Zero-G",
            C.PRESET_ZERO_G,
            C.PRESET_ZERO_G_SELECTED,
            C.PROGRAM_ZERO_G,
            C.PROGRAM_ZERO_G_DESELECTED,
            "",
        ),
        (
            "Anti-Snore (Woosa: Love)",
            C.PRESET_ANTI_SNORE,
            C.PRESET_ANTI_SNORE_SELECTED,
            C.PROGRAM_ANTI_SNORE,
            C.PROGRAM_ANTI_SNORE_DESELECTED,
            "",
        ),
        (
            "Relaxing bedtime",
            C.PRESET_RELAXING_BEDTIME,
            None,
            None,
            None,
            _routes(_has("relaxing_bedtime")),
        ),
    )
    presets = _routes(_has("presets"))

    def cell(frame: bytes | None) -> str:
        return _hex(frame) if frame is not None else "n/a"

    return _block(
        "Programming a named preset is Woosa only; the other routes recognize these "
        "program frames in replies and echoes.",
        _table(
            ("Preset", "Recall", "Recall while selected", "Program", "Clear", "Routes"),
            (
                (label, cell(recall), cell(selected), cell(program), cell(clear), routes or presets)
                for label, recall, selected, program, clear, routes in rows
            ),
        ),
    )


def render_ff_frame_memory() -> str:
    slots = (
        (1, C.PRESET_MEMORY_1, C.PROGRAM_MEMORY_1, C.PROGRAM_MEMORY_1_SELECTED),
        (2, C.PRESET_MEMORY_2, C.PROGRAM_MEMORY_2, C.PROGRAM_MEMORY_2_SELECTED),
    )
    return _block(
        _table(
            ("Slot", "Recall", "Program", "Program while selected", "Routes"),
            (
                (
                    str(slot),
                    _hex(recall),
                    _hex(program),
                    _hex(selected),
                    _routes(lambda profile, slot=slot: profile.memory_slots >= slot),
                )
                for slot, recall, program, selected in slots
            ),
        ),
        "Woosa saves its Favourite slot with the program frame only.",
    )


def render_ff_frame_massage() -> str:
    shared = (
        ("Head +", C.MASSAGE_HEAD_UP),
        ("Head -", C.MASSAGE_HEAD_DOWN),
        ("Foot +", C.MASSAGE_FOOT_UP),
        ("Foot -", C.MASSAGE_FOOT_DOWN),
        ("Stop", C.MASSAGE_STOP),
        ("Timer 10 min", C.MASSAGE_TIMER_10_MIN),
        ("Timer 20 min", C.MASSAGE_TIMER_20_MIN),
        ("Timer 30 min", C.MASSAGE_TIMER_30_MIN),
    )
    home = _routes(lambda profile: profile.massage)
    wave = _routes(lambda profile: profile.massage and profile.key != "woosa")
    circulation = _routes(_has("circulation"))
    rows = [(label, _hex(frame), home) for label, frame in shared]
    rows += [
        ("Wave +", _hex(C.MASSAGE_FREQUENCY_UP), wave),
        ("Wave -", _hex(C.MASSAGE_FREQUENCY_DOWN), wave),
        ("Cycle full body", _hex(C.MASSAGE_CIRCULATION_FULL_BODY), circulation),
        ("Cycle head", _hex(C.MASSAGE_CIRCULATION_HEAD), circulation),
        ("Cycle leg", _hex(C.MASSAGE_CIRCULATION_LEG), circulation),
        ("Cycle hip", _hex(C.MASSAGE_CIRCULATION_HIP), circulation),
    ]
    woosa = [
        *(
            (f"Head level {level}", _hex(frame))
            for level, frame in enumerate(ff_profiles.WOOSA_HEAD_LEVELS)
        ),
        *(
            (f"Foot level {level}", _hex(frame))
            for level, frame in enumerate(ff_profiles.WOOSA_FOOT_LEVELS)
        ),
        *((f"Mode {mode}", _hex(frame)) for mode, frame in enumerate(ff_profiles.WOOSA_MODES, 1)),
        ("Mode step", _hex(ff_profiles.WOOSA_MODE_STEP)),
    ]
    replies = _table(
        ("Reply", "Level or mode 0-3 (mode 1-4)"),
        (
            (zone.capitalize(), ", ".join(_hex(frame) for frame in frames))
            for zone, frames in ff_profiles.WOOSA_MASSAGE_REPLIES.items()
        ),
    )
    return _block(
        _table(("Command", "Bytes (hex)", "Routes"), rows),
        "**Woosa massage levels and modes**",
        _table(("Command", "Bytes (hex)"), woosa),
        "##### Woosa massage replies",
        replies,
    )


def render_ff_frame_lights() -> str:
    levels = _routes(_has("light_levels"))
    timers = _routes(_has("light_timer"))
    rows = [(f"Level {level}", _hex(frame), levels) for level, frame in enumerate(C.LIGHT_LEVELS)]
    rows += [
        ("Status query", _hex(C.LIGHT_STATUS_QUERY), _routes(_has("clock_sync")) + ", Woosa Sleep"),
        ("Timer 10 min", _hex(C.LIGHT_TIMER_10_MIN), timers),
        ("Timer 8 hours", _hex(C.LIGHT_TIMER_8_HOURS), timers),
        ("Timer 10 hours", _hex(C.LIGHT_TIMER_10_HOURS), timers),
        ("Off", _hex(ff_profiles.WOOSA_LIGHT_OFF), "Woosa Sleep"),
    ]
    return _block(
        _table(("Command", "Bytes (hex)", "Routes"), rows),
        "Routes with brightness offer an Off light timer, which sends level 0 (Woosa: Off).",
    )


def render_ff_frame_audio() -> str:
    rows = [
        ("Music toggle", _hex(C.MUSIC_TOGGLE)),
        ("Music off", _hex(C.MUSIC_OFF)),
        ("Volume query", _hex(C.AUDIO_VOLUME_QUERY)),
    ]
    rows += [
        (
            f"Track {track}{' preview' if flag else ''}",
            _hex(ff_codec.summed(0x01, 0x13, bytes((track | flag,)))),
        )
        for track in range(1, 6)
        for flag in (0, 0x80)
    ]
    rows += [
        (f"Volume {level}", _hex(ff_codec.summed(0x01, 0x14, bytes((level,)))))
        for level in range(1, 6)
    ]
    return _block(f"Routes: {_routes(_has('audio'))}.", _table(("Command", "Bytes (hex)"), rows))


def render_ff_frame_queries() -> str:
    def table(frames: Iterable[bytes]) -> list[str]:
        return _table(
            ("Order", "Bytes (hex)"), ((str(i), _hex(f)) for i, f in enumerate(frames, 1))
        )

    bedsense = ff_profiles.BEDSENSE.actions
    groups = {
        "Default (types 1-5, 9)": "default",
        "Types 6 and 8": "68",
        "Type 7": "7",
    }
    lines: list[str | list[str]] = [
        "**Q1**",
        table(C.QUERY_Q1),
        "**Q2**",
        table(C.QUERY_Q2),
        "**Woosa preset queries** (also re-sent after each save)",
        table(ff_profiles.WOOSA_PRESET_QUERIES),
        f"Woosa also sends init {_hex(ff_profiles.WOOSA_INIT)} and alarm query "
        f"{_hex(ff_profiles.WOOSA_ALARM_QUERY)} at startup.",
    ]
    for label, group in groups.items():
        lines += [
            f"**BedSense {label}**",
            table(bedsense[f"query_{group}_{slot}"].frame for slot in (3, 4, 1, 2, 5)),
        ]
    return _block(*lines)


def render_ff_frame_bedsense() -> str:
    return _block(
        _table(
            ("Row", "Action", "Bytes (hex)", "Types"),
            (
                (
                    action.row,
                    action.label,
                    _hex(action.frame),
                    ", ".join(str(variant) for variant in sorted(action.variants)),
                )
                for action in ff_profiles.BEDSENSE.actions.values()
            ),
        )
    )


def render_ff_frame_motion_bed() -> str:
    commands = ff_profiles.MOTION_BED.commands
    selectors = (0x01, 0x03, 0x06, 0x0D, 0x21, 0x28, 0x35, 0x37)
    movement = [
        (
            f"`{code:02X}` / `{code + 1:02X}`",
            _hex(ff_codec.control(code)),
            _hex(ff_codec.control(code + 1)),
        )
        for code in selectors
    ]
    movement.append(
        (
            "BACK LEG `2B` / `2C`",
            _hex(ff_codec.control(0x2B, group=5)),
            _hex(ff_codec.control(0x2C, group=5)),
        )
    )
    sleep = [
        (label, _hex(ff_codec.control(up, arg=2)), _hex(ff_codec.control(up + 1, arg=2)))
        for label, up in (("Head", 0x03), ("Back", 0x01), ("Legs", 0x06), ("Lumbar", 0x0D))
    ]
    return _block(
        "**Movement selectors**",
        _table(("Selector (up / down)", "Up", "Down"), movement),
        "**Sleep adjustment** (`arg` 02)",
        _table(("Control", "Up", "Down"), sleep),
        "**Startup, status and stop frames**",
        _table(
            ("Frame", "App callsite", "Bytes (hex)"),
            ((label, f"`{key}`", _hex(commands[key])) for label, key in _MOTION_BED_FRAMES),
        ),
    )


BLOCKS: list[Block] = [
    (GUIDE, "ff-frame-profiles", render_ff_frame_profiles),
    (GUIDE, "ff-frame-transports", render_ff_frame_transports),
    (GUIDE, "ff-frame-motion", render_ff_frame_motion),
    (GUIDE, "ff-frame-presets", render_ff_frame_presets),
    (GUIDE, "ff-frame-memory", render_ff_frame_memory),
    (GUIDE, "ff-frame-massage", render_ff_frame_massage),
    (GUIDE, "ff-frame-lights", render_ff_frame_lights),
    (GUIDE, "ff-frame-audio", render_ff_frame_audio),
    (GUIDE, "ff-frame-queries", render_ff_frame_queries),
    (GUIDE, "ff-frame-bedsense", render_ff_frame_bedsense),
    (GUIDE, "ff-frame-motion-bed", render_ff_frame_motion_bed),
]
