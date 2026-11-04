"""Generated blocks of the Richmat 6E codec guide."""

from __future__ import annotations

from custom_components.adjustable_bed import const as _const
from custom_components.adjustable_bed import hjbed_catalog
from custom_components.adjustable_bed import hjbed_protocol as hjbed_frames
from custom_components.adjustable_bed import rmcontrol_protocol as rmcontrol_frames
from custom_components.adjustable_bed.beds import hjbed as hjbed_bed
from custom_components.adjustable_bed.beds import richmat_mh_protocol as mh_frames
from custom_components.adjustable_bed.beds import rmcontrol as rmcontrol_bed
from custom_components.adjustable_bed.beds.hjbed import action_label as hjbed_label
from custom_components.adjustable_bed.codec import richmat as richmat_codec
from custom_components.adjustable_bed.profiles import richmat as richmat_profiles
from scripts.codec_docs._common import Block, _block, _hex, _table

GUIDE = "docs/beds/richmat.md"

_RICHMAT_NAMES = {
    "richmat_wilinke": "Richmat WiLinke",
    "richmat_nordic": "Richmat Nordic",
    "richmat_prefix55": "Richmat Prefix55",
    "richmat_prefixaa": "Richmat PrefixAA",
    "bedtech": "BedTech",
    "leggett_wilinke": "L&P MlRM",
    "hjbed": "HJBed",
    **{
        profile.key: f"Richmat MH {name}"
        for profile, name in zip(
            richmat_profiles.RICHMAT_MH.values(),
            ("Revive Control", "Best Mattress", "Blvd Home", "HARMONY", "Idealbed"),
            strict=True,
        )
    },
}
_FIXED_ROUTES = (
    *richmat_profiles.RICHMAT.values(),
    richmat_profiles.BEDTECH,
    richmat_profiles.LEGGETT_WILINKE,
)
_BUTTON_LABELS: dict[richmat_profiles.Button, str] = {
    "head_up": "Head up",
    "head_down": "Head down",
    "feet_up": "Feet up",
    "feet_down": "Feet down",
    "head_feet_up": "Head and feet up",
    "head_feet_down": "Head and feet down",
    "pillow_up": "Pillow up",
    "pillow_down": "Pillow down",
    "lumbar_up": "Lumbar up",
    "lumbar_down": "Lumbar down",
    "flat": "Flat",
    "zero_g": "Zero-G",
    "anti_snore": "Anti-Snore",
    "tv": "TV",
    "lounge": "Lounge",
    "save_lounge": "Save lounge",
    "light_toggle": "Light toggle",
    "light_off": "Light off",
    "massage_toggle": "Massage toggle",
    "massage_off": "Massage off",
    "massage_head": "Head massage step",
    "massage_foot": "Foot massage step",
    "massage_mode": "Massage mode step",
    "massage_head_up": "Head massage up",
    "massage_head_down": "Head massage down",
    "massage_foot_up": "Foot massage up",
    "massage_foot_down": "Foot massage down",
    "massage_intensity_up": "Massage intensity up",
    "massage_intensity_down": "Massage intensity down",
    "massage_wave": "Wave massage",
    "massage_timer_10": "Massage timer 10 min",
    "massage_timer_20": "Massage timer 20 min",
    "massage_timer_30": "Massage timer 30 min",
    "sync_on": "Controller sync on",
    "sync_off": "Controller sync off",
}


def _richmat_profiles() -> dict[str, richmat_profiles.RichmatProfile]:
    return {
        profile.key: profile
        for profile in (
            *_FIXED_ROUTES,
            richmat_profiles.HJBED,
            *richmat_profiles.RICHMAT_MH.values(),
        )
    }


def bed_types() -> dict[str, tuple[str, ...]]:
    """Bed types per profile; ``tests/test_codec_docs.py`` checks them against the factory."""
    mh_types = {app: bed_type for bed_type, app in _const.RICHMAT_MH_APPS.items()}
    return {
        **{
            profile.key: (_const.BED_TYPE_RICHMAT,) for profile in richmat_profiles.RICHMAT.values()
        },
        "bedtech": (_const.BED_TYPE_BEDTECH,),
        "leggett_wilinke": (_const.BED_TYPE_LEGGETT_WILINKE,),
        "hjbed": (_const.BED_TYPE_HJBED,),
        **{
            profile.key: (mh_types[profile.key.removeprefix("richmat_mh_")],)
            for profile in richmat_profiles.RICHMAT_MH.values()
        },
    }


def _code_hex(code: int) -> str:
    return f"`{code:02X}`"


def _recall(profile: richmat_profiles.RichmatProfile) -> str:
    recall = profile.recall
    sends = f"{recall.repeats} × {recall.repeat_ms} ms" if recall.repeats > 1 else "once"
    return f"{sends}, then STOP" if recall.release else sends


def render_richmat_profiles() -> str:
    types = bed_types()
    fixed = _table(
        (
            "Profile",
            "Bed type",
            "Framing",
            "STOP",
            "Default pulses",
            "Presets and recall",
            "Memory",
        ),
        (
            (
                _RICHMAT_NAMES[profile.key],
                ", ".join(f"`{bed_type}`" for bed_type in types[profile.key]),
                profile.framing,
                _hex(profile.frame(profile.stop)),
                "{} × {} ms".format(*_const.get_motor_pulse_defaults(types[profile.key][0])),
                _recall(profile),
                f"{len(profile.memory)} slots",
            )
            for profile in _FIXED_ROUTES
        ),
    )
    catalog = _table(
        ("Profile", "Bed type", "Transport order", "Commands"),
        (
            (
                _RICHMAT_NAMES[key],
                ", ".join(f"`{bed_type}`" for bed_type in types[key]),
                ", ".join(transport.upper() for transport in profile.transports),
                "per-product catalog" if key == "hjbed" else "per-model catalog",
            )
            for key, profile in _richmat_profiles().items()
            if profile.codes is None
        ),
    )
    return _block(
        "### Fixed-table routes",
        "Movement repeats the code at the entry's pulse count and delay, whose defaults "
        "are listed, then always sends STOP with a fresh cancel event. Every other "
        "button is one write.",
        fixed,
        "### Catalog apps",
        catalog,
    )


def render_richmat_transports() -> str:
    profiles = _richmat_profiles()
    users: dict[str, list[str]] = {}
    for key, profile in profiles.items():
        for transport in profile.transports:
            users.setdefault(transport, []).append(_RICHMAT_NAMES[key])
    return _block(
        _table(
            ("Key", "Service", "Write", "Notify", "Commands", "Profiles"),
            (
                (
                    key.upper(),
                    f"`{transport.service_uuid}`",
                    f"`{transport.write_uuid}`",
                    f"`{transport.notify_uuid}`",
                    "bare code" if transport.single else "framed",
                    ", ".join(dict.fromkeys(users.get(key, ()))) or "none",
                )
                for key, transport in richmat_codec.TRANSPORTS.items()
            ),
        ),
        "W0 is the legacy custom service, W4 and W5 are name-guarded (see the "
        "Richmat profile's Setup). The Richmat routes try W0 to W5, then N1, then fall "
        "back to W1.",
    )


def render_richmat_framing() -> str:
    flat = richmat_profiles.RICHMAT_CODES["flat"]
    return _block(
        _table(
            ("Framing", "Layout", "Flat"),
            (
                (
                    framing,
                    "bare code"
                    if framing == "nordic"
                    else f"`{richmat_codec.encode(framing, 0)[0]:02X} 01 00 code sum8`",
                    _hex(richmat_codec.encode(framing, flat)),
                )
                for framing in richmat_profiles.RICHMAT
            ),
        )
    )


def render_richmat_commands() -> str:
    def cell(profile: richmat_profiles.RichmatProfile, button: richmat_profiles.Button) -> str:
        frame = profile.button(button)
        return "n/a" if frame is None else _hex(frame)

    routes = (
        richmat_profiles.RICHMAT["wilinke"],
        richmat_profiles.BEDTECH,
        richmat_profiles.LEGGETT_WILINKE,
    )
    rows = [
        (label, *(cell(profile, button) for profile in routes))
        for button, label in _BUTTON_LABELS.items()
    ]
    rows += [
        ("STOP", *(_hex(profile.frame(profile.stop)) for profile in routes)),
        (
            "Compatibility STOP (QRRM, BT6500 remotes)",
            _hex(routes[0].frame(richmat_codec.COMPAT_STOP)),
            "n/a",
            "n/a",
        ),
    ]
    return _block(_table(("Command", "Richmat (WiLinke)", "BedTech", "L&P MlRM"), rows))


def render_richmat_memory() -> str:
    routes = (
        richmat_profiles.RICHMAT["wilinke"],
        richmat_profiles.BEDTECH,
        richmat_profiles.LEGGETT_WILINKE,
    )
    top = max(len(profile.memory) for profile in routes)

    def cell(profile: richmat_profiles.RichmatProfile, slot: int, save: bool) -> str:
        if slot > len(profile.memory):
            return "n/a"
        return _hex(profile.frame(profile.memory[slot - 1][int(save)]))

    return _block(
        _table(
            ("Command", "Richmat (WiLinke)", "BedTech", "L&P MlRM"),
            [
                *(
                    (f"Memory {slot} recall", *(cell(p, slot, False) for p in routes))
                    for slot in range(1, top + 1)
                ),
                *(
                    (f"Memory {slot} save", *(cell(p, slot, True) for p in routes))
                    for slot in range(1, top + 1)
                ),
            ],
        ),
        "The Richmat remote code decides how many slots appear (up to three); "
        "recall and save accept every listed slot.",
    )


def render_richmat_ggrm() -> str:
    route = richmat_profiles.RICHMAT["wilinke"]
    return _block(
        _table(
            ("GGRM action", "WiLinke frame"),
            (
                (label, _hex(route.frame(code)))
                for code, (label, _) in richmat_profiles.GGRM_ACTIONS.items()
            ),
        )
    )


def render_richmat_lights() -> str:
    return _block(
        _table(
            ("Command", "RGB strip (QRRM family)", "Legacy RGB"),
            (
                (
                    "On",
                    _hex(richmat_codec.strip(0x04, b"\x02")),
                    _hex(richmat_codec.frame(richmat_codec.BED, 0x0A, 0x00, 0x01)),
                ),
                ("Off", _hex(richmat_codec.strip(0x04, b"\x00")), "light toggle"),
                (
                    "Colour",
                    "`04 0B 01 01 00 R G B 00 00 sum8`",
                    "`6E 0C FF R sum8 6E 0D G B sum8` (one write)",
                ),
                (
                    "Timer",
                    f"minutes, for example 5 min {_hex(richmat_codec.strip(0x02, (5).to_bytes(2, 'big')))}",
                    f"seconds, for example 5 min {_hex(richmat_codec.light_timer(*divmod(300, 256)))}",
                ),
                (
                    "Always On",
                    _hex(richmat_codec.strip(0x02, bytes(2))),
                    _hex(richmat_codec.light_timer(0, 0)),
                ),
            ),
        )
    )


def render_richmat_functions() -> str:
    return _block(
        _table(
            ("Catalog action", "Prefix"),
            (
                (
                    f"`{action.removeprefix('deviceFunction')}`",
                    f"`{' '.join(f'{b:02X}' for b in prefix)}`",
                )
                for action, prefix in richmat_codec.FUNCTION_PREFIXES.items()
            ),
        ),
        "Every other catalog action uses `6E 01 side`. HJBed sends only the first four.",
    )


def render_richmat_mh_setup() -> str:
    def row(name: str, literal: str) -> tuple[str, str, str]:
        sent = mh_frames.query_frame(literal)
        return (
            name,
            _hex(sent) if literal in mh_frames.INIT_VER0 else "none",
            _hex(sent) if literal in mh_frames.INIT_VER1 else "none",
        )

    names = {
        mh_frames.TX_EXIT_ONE_MIN: "Exit one-minute",
        mh_frames.TX_ALARM: "Alarm",
        mh_frames.TX_LED: "LED",
        mh_frames.TX_AROMA: "Aroma",
        mh_frames.TX_MATTRESS: "Mattress",
        mh_frames.TX_WAIST_MATTRESS: "Waist mattress",
        mh_frames.TX_SNORE: "Snore",
        mh_frames.TX_SPEECH: "Speech",
        mh_frames.TX_DETECTION: "Detection",
        mh_frames.TX_MOTOR_MODE: "Motor mode",
        mh_frames.TX_QUERY_MASSAGE: "Massage query",
        mh_frames.TX_QUERY_UBL_LOCK: "Button-light lock query",
        **{
            literal: f"Motor {index} angle"
            for index, literal in enumerate(mh_frames.TX_MOTOR_ANGLES, 1)
        },
    }
    steps = list(dict.fromkeys((*mh_frames.INIT_VER0, *mh_frames.INIT_VER1)))
    version = _hex(mh_frames.query_frame(mh_frames.TX_VERSION))
    return _block(
        _table(
            ("Step", "VER0", "VER1"),
            [
                ("Version query", version, version),
                *(row(names[literal], literal) for literal in steps),
            ],
        ),
        f"The app's mattress literal ends in checksum `{mh_frames.TX_MATTRESS[-2:].upper()}`; the sender recomputes "
        "its checksum, so the bed receives the frame above.",
    )


def render_richmat_mh_fixed() -> str:
    return _block(
        _table(
            ("Command", "Frame (single-device group)"),
            (
                ("STOP", _hex(mh_frames.stop_frame())),
                (
                    "Button light off (Revive Control, Best Mattress)",
                    _hex(mh_frames.control_frame(mh_frames.BTN_LED_OFF_CODE)),
                ),
                (
                    "Smart set lock toggle, once",
                    _hex(mh_frames.control_frame(mh_frames.SMART_SET_LOCK_CODE)),
                ),
                ("Start detection", _hex(mh_frames.query_frame(mh_frames.TX_START_DETECTION))),
                ("Stop detection", _hex(mh_frames.query_frame(mh_frames.TX_STOP_DETECTION))),
                (
                    "Cancel alarm (single-slot models)",
                    " then ".join(
                        _hex(mh_frames.query_frame(x)) for x in mh_frames.TX_ALARM_CANCEL
                    ),
                ),
            ),
        )
    )


_HJBED_GROUPS = {
    "motor": "Motor Control",
    "preset": "Presets",
    "massage": "Massage",
    "light": "Lights",
    "music": "Music",
    "other": "Reset, stop and sync",
}


def _hjbed_group(action: hjbed_catalog.Action) -> str:
    if action.kind in ("motor", "preset", "music"):
        return action.kind
    if "Massage" in action.enum:
        return "massage"
    if "Light" in action.enum:
        return "light"
    return "other"


def _hjbed_gesture(action: hjbed_catalog.Action) -> str:
    gesture = "Refresh 100 ms" if action.sustain else "Once"
    gesture += "; STOP" if action.release else "; no extra STOP"
    return gesture + ("; Motion once" if action.kind == "reset" else "")


def render_hjbed_commands() -> str:
    def frames(action: hjbed_catalog.Action, code: int) -> tuple[str, str, str]:
        right = 0 if action.kind == "music" else 1
        return (
            _code_hex(code),
            _hex(hjbed_frames.function(action.enum, code, 0, False)),
            _hex(hjbed_frames.function(action.enum, code, right, False)),
        )

    groups: dict[str, list[hjbed_catalog.Action]] = {}
    for action in hjbed_catalog.ACTIONS.values():
        groups.setdefault(_hjbed_group(action), []).append(action)
    parts: list[str | list[str]] = []
    for group, title in _HJBED_GROUPS.items():
        parts += [
            f"##### {title}",
            _table(
                (
                    "Command (detail)",
                    "Single code",
                    "Framed left",
                    "Framed right",
                    "Gesture / release",
                ),
                (
                    (
                        f"{hjbed_label(action)} (`{action.object}`)",
                        *frames(action, action.code),
                        _hjbed_gesture(action),
                    )
                    for action in groups[group]
                ),
            ),
        ]
    parts += [
        "##### Memory",
        "Save is available only for selected preset details with a long code. BJRN waits "
        "three seconds; other product saves send once immediately. Recall and save remain "
        "separate actions.",
        _table(
            ("Save command (detail)", "Single code", "Framed left", "Framed right"),
            (
                (f"{hjbed_label(action)} (`{action.object}`)", *frames(action, action.save_code))
                for action in hjbed_catalog.ACTIONS.values()
                if action.save_code is not None
            ),
        ),
    ]
    return _block(*parts)


def _ms(seconds: float) -> str:
    return f"{round(seconds * 1000)} ms"


def render_richmat_catalog_timing() -> str:
    return _block(
        _table(
            ("Profile", "Operation", "Timing"),
            (
                (
                    "RMControl",
                    "Write queue, including release",
                    f"at least {rmcontrol_bed.WRITE_SPACING_MS} ms apart",
                ),
                (
                    "RMControl",
                    "Sustain press",
                    f"entry pulse count at {rmcontrol_bed.WRITE_SPACING_MS} ms, then STOP",
                ),
                ("RMControl", "Short and long press", "one write"),
                ("Richmat MH", "Version query after subscribing", _ms(mh_frames.INIT_DELAY_S)),
                (
                    "Richmat MH",
                    "Initialization tasks",
                    f"{_ms(mh_frames.INIT_TASK_SLEEP_S)} apart, the first {_ms(mh_frames.INIT_DELAY_S)} after the version query",
                ),
                ("Richmat MH", "STOP after a release or a single tap", _ms(mh_frames.STOP_DELAY_S)),
                (
                    "Richmat MH",
                    "VER1 angle target",
                    f"{_ms(mh_frames.ANGLE_SEND_DELAY_S)} after the slider release",
                ),
                (
                    "Richmat MH",
                    "Alarm frames",
                    f"{_ms(mh_frames.ALARM_TASK_SLEEP_S)} apart ({_ms(mh_frames.MULTI_ALARM_SLEEP_S)} for three-slot save/delete)",
                ),
                ("Richmat MH", "Aroma frames", f"{_ms(mh_frames.AROMA_TASK_SLEEP_S)} apart"),
                ("HJBed", "Sustained refresh", f"every {hjbed_bed.TICK_MS} ms from the first tick"),
                ("HJBed", "Write spacing", f"at least {hjbed_bed.TICK_MS} ms between attempts"),
                ("HJBed", "Menu probes at connect", f"{_ms(hjbed_bed.MENU_PROBE_S)} apart"),
                ("HJBed", "BJRN preset save", f"waits {hjbed_bed.BJRN_SAVE_WAIT_S} s"),
            ),
        )
    )


def render_rmcontrol_startup() -> str:
    def action(name: str) -> str:
        code = 0 if name == "ExitLimit" else 1
        framed = rmcontrol_frames.build_action(code, action="deviceFunctionItem" + name)
        nordic = rmcontrol_frames.build_action(
            code, nordic=True, action="deviceFunctionItem" + name
        )
        return f"{_hex(framed)} (Nordic {_hex(nordic)})"

    return _block(
        _table(
            ("Step", "Sent when", "Frames"),
            (
                ("Exit limit", "always", action("ExitLimit")),
                (
                    "Time sync",
                    "the product has an alarm catalog",
                    "extended `08 02 01` then `08 03 01`",
                ),
                (
                    "Sleep-advertisement query",
                    "a BLE sleep product",
                    "extended `06 03 00`: `00`",
                ),
                ("Check clock", "always", action("CheckClock")),
                ("Check light", "always", action("CheckLight")),
            ),
        )
    )


def render_hjbed_startup() -> str:
    probe = hjbed_bed.MENU_PROBE_S
    return _block(
        _table(
            ("Step", "When", "Framed", "Single-code"),
            (
                (
                    "Exit limit",
                    "first",
                    _hex(hjbed_frames.function("deviceFunctionItemExitLimit", 0, 0, False)),
                    _hex(hjbed_frames.function("deviceFunctionItemExitLimit", 0, 0, True)),
                ),
                ("Time sync", "next, two frames", "extended `08 02 01` then `08 03 01`", "same"),
                (
                    "Control mode query",
                    "blue, green and orange; green and orange only in the Motion layout",
                    _hex(hjbed_frames.control_mode()),
                    "same",
                ),
                *(
                    (
                        f"{name} menu probe",
                        f"+{_ms(probe * tick)}",
                        _hex(hjbed_frames.function(f"deviceFunctionItemCheck{name}", 1, 0, False)),
                        _hex(hjbed_frames.function(f"deviceFunctionItemCheck{name}", 1, 0, True)),
                    )
                    for tick, name in enumerate(("Clock", "Light", "Music"), start=1)
                ),
            ),
        ),
        "Probe offsets count from the start of the menu request, after the exit frame.",
    )


BLOCKS: list[Block] = [
    (GUIDE, "richmat-profiles", render_richmat_profiles),
    (GUIDE, "richmat-transports", render_richmat_transports),
    (GUIDE, "richmat-framing", render_richmat_framing),
    (GUIDE, "richmat-commands", render_richmat_commands),
    (GUIDE, "richmat-memory", render_richmat_memory),
    (GUIDE, "richmat-ggrm", render_richmat_ggrm),
    (GUIDE, "richmat-lights", render_richmat_lights),
    (GUIDE, "richmat-functions", render_richmat_functions),
    (GUIDE, "richmat-mh-setup", render_richmat_mh_setup),
    (GUIDE, "richmat-mh-fixed", render_richmat_mh_fixed),
    (GUIDE, "hjbed-commands", render_hjbed_commands),
    (GUIDE, "richmat-catalog-timing", render_richmat_catalog_timing),
    (GUIDE, "rmcontrol-startup", render_rmcontrol_startup),
    (GUIDE, "hjbed-startup", render_hjbed_startup),
]
