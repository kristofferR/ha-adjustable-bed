"""Generated blocks of the Limoss DD codec guide."""

from __future__ import annotations

from collections.abc import Iterable

from custom_components.adjustable_bed.codec import limoss as limoss_codec
from custom_components.adjustable_bed.const import (
    BED_TYPE_FSM_RELAX,
    BED_TYPE_LIMOSS,
    BED_TYPE_LIMOSS_REMOTE,
    get_motor_pulse_defaults,
)
from custom_components.adjustable_bed.profiles import limoss as limoss_profiles
from scripts.codec_docs._common import Block, _block, _hex, _table

GUIDE = "docs/beds/limoss.md"

LIMOSS_BED_TYPES: dict[str, str] = {
    "legacy": BED_TYPE_LIMOSS,
    "limoss_remote": BED_TYPE_LIMOSS_REMOTE,
    "fsm_relax": BED_TYPE_FSM_RELAX,
}


def bed_types() -> dict[str, tuple[str, ...]]:
    """Bed types per profile, as the profile summary lists them."""
    return {key: (bed_type,) for key, bed_type in LIMOSS_BED_TYPES.items()}

_LIMOSS_NAMES = {"legacy": "Legacy route", "limoss_remote": "Limoss Remote", "fsm_relax": "FSM Relax"}
_LIMOSS_COUNTERS = {
    "controller": "per controller; repeats resend one frame",
    "session": "per bed, kept across reconnects; one value per frame",
    "app": "one process-wide app counter; one value per frame",
}
_LIMOSS_WRITE_MODES = {
    "property": "with response when the characteristic has `write`",
    "without_response": "always without response",
}
_LIMOSS_RELEASES = {
    limoss_codec.STOP: "STOP",
    limoss_codec.RECALL_RELEASE: "recall release",
    limoss_codec.LIGHT_OFF: "light off",
    limoss_codec.MASSAGE_OFF: "massage off",
}
_ZERO_FLAGS = (False, False, False, False)


def _limoss_names(keys: Iterable[str]) -> str:
    return ", ".join(_LIMOSS_NAMES[key] for key in keys) or "none"


def _burst(burst: limoss_profiles.Burst | None, tick: str) -> str:
    if burst is None:
        return "none"
    body = _hex(limoss_codec.release(burst.opcode, _ZERO_FLAGS))
    sends = "once" if burst.frames == 1 else f"{burst.frames} × {tick}"
    return f"{_LIMOSS_RELEASES[burst.opcode]} {body}, {sends}"


def _limoss_tick(key: str, profile: limoss_profiles.LimossProfile) -> str:
    if profile.tick_ms is not None:
        return f"{profile.tick_ms} ms"
    count, delay = get_motor_pulse_defaults(LIMOSS_BED_TYPES[key])
    return f"motor pulse delay (default {delay} ms)"


def render_limoss_profiles() -> str:
    profiles = limoss_profiles.PROFILES
    summary = _table(
        ("Profile", "Bed type", "Counter", "Write mode", "Key tables"),
        (
            (
                _LIMOSS_NAMES[key],
                f"`{LIMOSS_BED_TYPES[key]}`",
                _LIMOSS_COUNTERS[profile.counter],
                _LIMOSS_WRITE_MODES[profile.write_mode],
                str(len(profile.layouts)) if profile.layouts else "none (motor count)",
            )
            for key, profile in profiles.items()
        ),
    )

    def hold(key: str, profile: limoss_profiles.LimossProfile) -> str:
        if profile.tick_ms is not None:
            return f"every {profile.tick_ms} ms, first after {profile.tick_ms} ms"
        count, delay = get_motor_pulse_defaults(LIMOSS_BED_TYPES[key])
        return (
            "motor pulse count × delay, first immediately "
            f"(default {count} × {delay} ms)"
        )

    def calibration(profile: limoss_profiles.LimossProfile, tick: str) -> str:
        if profile.calibration is None:
            return "none"
        refresh = profile.calibration.refresh_ms
        sends = "one frame" if refresh is None else f"held, every {refresh} ms"
        if profile.calibration.release is None:
            return sends
        return f"{sends}, then {_burst(profile.calibration.release, tick)}"

    timing = _table(
        ("Profile", "Hold refresh", "Stop", "Recall interval", "Calibration", "Feature off"),
        (
            (
                _LIMOSS_NAMES[key],
                hold(key, profile),
                _burst(profile.stop, _limoss_tick(key, profile)),
                f"{profile.recall_ms} ms, then {_burst(profile.recall_release, _limoss_tick(key, profile))}",
                calibration(profile, _limoss_tick(key, profile)),
                f"{profile.feature_off_frames} × {_limoss_tick(key, profile)}"
                if profile.feature_off_frames
                else "none",
            )
            for key, profile in profiles.items()
        ),
    )

    def layouts(profile: limoss_profiles.LimossProfile) -> list[str]:
        return _table(
            ("Key table", "Opcodes in key order (`·` is an empty key)"),
            (
                (
                    f"`{name}`",
                    " ".join("·" if opcode is None else f"`{opcode:02X}`" for opcode in table),
                )
                for name, table in profile.layouts.items()
            ),
        )

    return _block(
        "### Profile summary",
        summary,
        "### Timing",
        "Stop and release frames go out one per tick. An explicit stop sends the same "
        "frames as the end of a hold. The recall interval separates set-position writes "
        "(see each profile's Timing for how a recall repeats).",
        timing,
        "### Limoss Remote key tables",
        "Named `<chair c|bed g>Key<keys>[UnderBedLight|Vibrate|BothUnderBedLightVibrate]`, "
        "as the app's layouts are.",
        layouts(limoss_profiles.LIMOSS_REMOTE),
        "### FSM Relax key tables",
        "`chair/<keys>`, or `keyboard/<keys>/<features>` for the bed layout, where "
        "features is 0 none, 1 light, 2 massage, 3 both.",
        layouts(limoss_profiles.FSM_RELAX),
    )


def render_limoss_transport() -> str:
    return _block(
        _table(
            ("Role", "UUID", "Profiles"),
            (
                ("Service", f"`{limoss_codec.SERVICE_UUID}`", "all"),
                ("Write and notify", f"`{limoss_codec.CHAR_UUID}`", "all"),
            ),
        )
    )


def render_limoss_commands() -> str:
    profiles = limoss_profiles.PROFILES

    legacy_held = {limoss_codec.motor(i, up) for i in range(1, 5) for up in (True, False)}
    legacy_held |= {limoss_codec.FLAT, limoss_codec.LIGHT, *limoss_codec.MASSAGE_ZONES}

    def users(opcode: int) -> str:
        return _limoss_names(
            key
            for key, profile in profiles.items()
            if (opcode in legacy_held if profile is limoss_profiles.LEGACY else False)
            or any(opcode in table for table in profile.layouts.values())
        )

    held = sorted(
        legacy_held
        | {
            opcode
            for profile in profiles.values()
            for table in profile.layouts.values()
            for opcode in table
            if opcode is not None
        }
    )
    remote_names = {opcode: name for name, opcode in limoss_profiles.REMOTE_CHANNELS.items()}
    legacy_labels = {
        limoss_codec.motor(i, up): f"Motor {i} {'up' if up else 'down'}"
        for i in range(1, 5)
        for up in (True, False)
    }
    legacy_labels[limoss_codec.FLAT] = "Flat (held)"
    legacy_labels[limoss_codec.LIGHT] = "Light toggle"
    for zone, opcode in enumerate(limoss_codec.MASSAGE_ZONES, 1):
        legacy_labels[opcode] = f"Vibration zone {zone}"
    held_table = _table(
        (
            "Opcode",
            "Body (flags clear)",
            "Legacy route",
            "Limoss Remote channel",
            "FSM Relax label",
            "Profiles",
        ),
        (
            (
                f"`{opcode:02X}`",
                _hex(limoss_codec.flagged(opcode, _ZERO_FLAGS)),
                legacy_labels.get(opcode, ""),
                f"`{remote_names[opcode]}`" if opcode in remote_names else "",
                limoss_profiles.FSM_LABELS.get(opcode, ""),
                users(opcode),
            )
            for opcode in held
        ),
    )
    control = _table(
        ("Command", "Body", "Profiles"),
        (
            (
                "STOP",
                _hex(limoss_codec.release(limoss_codec.STOP, _ZERO_FLAGS)),
                _limoss_names(profiles),
            ),
            (
                "Release (recall or calibration)",
                _hex(limoss_codec.release(limoss_codec.RECALL_RELEASE, _ZERO_FLAGS)),
                _limoss_names(
                    key
                    for key, profile in profiles.items()
                    if limoss_codec.RECALL_RELEASE
                    in {
                        burst.opcode
                        for burst in (
                            profile.recall_release,
                            profile.calibration.release if profile.calibration else None,
                        )
                        if burst is not None
                    }
                ),
            ),
            (
                "Calibrate",
                _hex(limoss_codec.flagged(limoss_codec.CALIBRATE, _ZERO_FLAGS)),
                _limoss_names(key for key, profile in profiles.items() if profile.calibration),
            ),
            *(
                (
                    label,
                    _hex(limoss_codec.body(opcode)),
                    _limoss_names(
                        key for key, profile in profiles.items() if profile.feature_off_frames
                    ),
                )
                for label, opcode in (
                    ("Light off", limoss_codec.LIGHT_OFF),
                    ("Massage off", limoss_codec.MASSAGE_OFF),
                )
            ),
        ),
    )
    queries = _table(
        ("Query", "Body", "Reply"),
        (
            ("Hardware version", _hex(limoss_codec.query(limoss_codec.QUERY_HARDWARE)), "`00` + four signed bytes"),
            ("Software version", _hex(limoss_codec.query(limoss_codec.QUERY_SOFTWARE)), "`01` + four signed bytes"),
            ("Capabilities", _hex(limoss_codec.query(limoss_codec.QUERY_CAPABILITIES)), "`02` + four capability bytes"),
            *(
                (
                    f"Motor {index} position",
                    _hex(limoss_codec.ask_position(index)),
                    f"`{index * 0x10:02X}` + big-endian 32-bit raw position",
                )
                for index in range(1, 5)
            ),
        ),
    )
    memory = _table(
        ("Command", "Body", "Example"),
        (
            (
                f"Set motor {index} position",
                f"`{index * 0x10 + 1:02X}` + big-endian 32-bit raw position",
                _hex(limoss_codec.set_position(index, 0x12345678)),
            )
            for index in range(1, 5)
        ),
    )
    return _block(
        "#### Held controls",
        "Held bodies carry the four motor reversal flags as `00`/`01` in the "
        "parameter bytes on the app profiles; the legacy route sends them clear.",
        held_table,
        "#### Stop, release and features",
        control,
        "#### Queries",
        "The legacy route sends only the capability and position queries.",
        queries,
        "#### Memory recall",
        memory,
    )


BLOCKS: list[Block] = [
    (GUIDE, "limoss-profiles", render_limoss_profiles),
    (GUIDE, "limoss-transport", render_limoss_transport),
    (GUIDE, "limoss-commands", render_limoss_commands),
]
