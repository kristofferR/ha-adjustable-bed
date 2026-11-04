"""Generated blocks of the Okin 5A codec guide."""

from __future__ import annotations

from typing import get_args

from custom_components.adjustable_bed import controller_factory
from custom_components.adjustable_bed.codec import okin_5a as okin_5a_codec
from custom_components.adjustable_bed.const import (
    BED_TYPE_STAR_ELEVATE,
)
from custom_components.adjustable_bed.profiles import okin_5a as okin_5a_profiles
from scripts.codec_docs._common import Block, _block, _hex, _table

GUIDE = "docs/beds/okin-5a.md"

_OKIN_5A_NAMES = {
    "okin_7byte": "Nectar",
    "okin_nordic": "Mattress Firm 900 / iFlex",
    "okin_cb35": "Sealy Posturematic (CB35)",
    "star_elevate": "DewertOkin ELEVATE",
}
# Controllers the factory registry builds over each profile; ELEVATE has its own branch.
_OKIN_5A_CONTROLLERS = {
    "okin_7byte": ("okin_7byte", "Okin7ByteController"),
    "okin_nordic": ("okin_nordic", "OkinNordicController"),
    "okin_cb35": ("okin_cb35", "OkinCB35Controller"),
}
_OKIN_5A_TRANSPORT_NAMES: dict[okin_5a_codec.TransportKey, str] = {
    "okin": "Okin",
    "nus": "Nordic UART",
}
_OKIN_5A_LABELS: dict[okin_5a_profiles.Action, str] = {
    "stop": "STOP",
    "head_up": "Head up (ELEVATE actuator 1 up)",
    "head_down": "Head down (ELEVATE actuator 1 down)",
    "feet_up": "Foot up (ELEVATE actuator 2 up)",
    "feet_down": "Foot down (ELEVATE actuator 2 down)",
    "lumbar_up": "Lumbar up",
    "lumbar_down": "Lumbar down",
    "neck_up": "Neck up",
    "neck_down": "Neck down",
    "hips_up": "Hips up (Head End Tilt cover)",
    "hips_down": "Hips down (Head End Tilt cover)",
    "both_up": "Both actuators up",
    "both_down": "Both actuators down",
    "interrupt": "Group interrupt",
    "flat": "Flat",
    "zero_g": "Zero-G",
    "anti_snore": "Anti-Snore",
    "lounge": "Lounge",
    "tv": "TV",
    "incline": "Incline",
    "memory_1": "Memory 1 recall",
    "memory_2": "Memory 2 recall",
    "massage_toggle": "Massage toggle (also head and foot toggles)",
    "massage_on": "Massage on",
    "massage_off": "Massage off",
    "massage_mode": "Massage mode step (wave)",
    "massage_up": "Massage intensity up",
    "massage_down": "Massage intensity down",
    "massage_head_up": "Head massage strength up",
    "massage_head_down": "Head massage strength down",
    "massage_foot_up": "Foot massage strength up",
    "massage_foot_down": "Foot massage strength down",
    "light_on": "Light on",
    "light_off": "Light off",
    "light_toggle": "Light toggle (controller method; HA hides the button)",
    "light_brightness_up": "Light brightness up (controller method, no entity)",
    "light_brightness_down": "Light brightness down (controller method, no entity)",
    "light_color": "Light color change (controller method, no entity)",
}
_OKIN_5A_GROUPS: dict[str, tuple[okin_5a_profiles.Action, ...]] = {
    "motors": (
        "head_up",
        "head_down",
        "feet_up",
        "feet_down",
        "lumbar_up",
        "lumbar_down",
        "neck_up",
        "neck_down",
        "hips_up",
        "hips_down",
        "both_up",
        "both_down",
        "stop",
        "interrupt",
    ),
    "presets": (
        "flat",
        "zero_g",
        "anti_snore",
        "lounge",
        "tv",
        "incline",
        "memory_1",
        "memory_2",
    ),
    "massage": (
        "massage_toggle",
        "massage_on",
        "massage_off",
        "massage_mode",
        "massage_up",
        "massage_down",
        "massage_head_up",
        "massage_head_down",
        "massage_foot_up",
        "massage_foot_down",
    ),
    "lights": (
        "light_on",
        "light_off",
        "light_toggle",
        "light_brightness_up",
        "light_brightness_down",
        "light_color",
    ),
}


def bed_types() -> dict[str, tuple[str, ...]]:
    """Bed types per profile, from the factory registry; ``tests`` check them against it."""
    registry = controller_factory._SIMPLE_CONTROLLERS
    return {
        **{
            key: tuple(
                bed_type
                for bed_type, spec in registry.items()
                if (spec.module, spec.class_name) == controller
            )
            for key, controller in _OKIN_5A_CONTROLLERS.items()
        },
        "star_elevate": (BED_TYPE_STAR_ELEVATE,),
    }


def _okin_5a_tap(tap: okin_5a_profiles.Tap) -> str:
    return f"{tap.repeats} × {tap.repeat_ms} ms" if tap.repeats > 1 else "once"


def render_okin_5a_profiles() -> str:
    profiles = okin_5a_profiles.PROFILES
    types = bed_types()
    summary = _table(
        ("Profile", "Bed types", "Transport", "Writes", "Wake, once per session"),
        (
            (
                _OKIN_5A_NAMES[key],
                ", ".join(f"`{bed_type}`" for bed_type in types[key]),
                _OKIN_5A_TRANSPORT_NAMES[profile.transport],
                "with response" if profile.write_with_response else "without response",
                ", ".join(_hex(frame) for frame in profile.wake)
                + (" (with response)" if profile.wake_with_response else "")
                if profile.wake
                else "none",
            )
            for key, profile in profiles.items()
        ),
    )
    timing = _table(
        ("Profile", "Presets and memory recall", "STOP", "Light off"),
        (
            (
                _OKIN_5A_NAMES[key],
                _okin_5a_tap(profile.recall),
                _okin_5a_tap(profile.stop),
                _okin_5a_tap(profile.lights_off) if "light_off" in profile.frames else "n/a",
            )
            for key, profile in profiles.items()
        ),
    )
    return _block(
        "### Profile summary",
        summary,
        "### Timing",
        "Motor movement repeats at the entry's motor pulse count and delay, then sends "
        "STOP. Massage and light commands are single writes unless listed here.",
        timing,
    )


def render_okin_5a_transports() -> str:
    profiles = okin_5a_profiles.PROFILES
    return _block(
        _table(
            ("Transport", "Service", "Write", "Notify", "Profiles"),
            (
                (
                    _OKIN_5A_TRANSPORT_NAMES[key],
                    f"`{transport.service_uuid}`",
                    f"`{transport.write_uuid}`",
                    f"`{transport.notify_uuid}`",
                    ", ".join(
                        _OKIN_5A_NAMES[name]
                        for name, profile in profiles.items()
                        if profile.transport == key
                    ),
                )
                for key, transport in okin_5a_codec.TRANSPORTS.items()
            ),
        )
    )


def _okin_5a_commands(group: str) -> str:
    profiles = okin_5a_profiles.PROFILES
    missing = set(get_args(okin_5a_profiles.Action)) - {
        action for actions in _OKIN_5A_GROUPS.values() for action in actions
    }
    if missing:
        raise ValueError(f"Okin 5A actions without a command table: {sorted(missing)}")
    return _block(
        _table(
            ("Command", *(_OKIN_5A_NAMES[key] for key in profiles)),
            (
                (
                    _OKIN_5A_LABELS[action],
                    *(
                        _hex(frame) if (frame := profile.frames.get(action)) else "n/a"
                        for profile in profiles.values()
                    ),
                )
                for action in _OKIN_5A_GROUPS[group]
            ),
        )
    )


def render_okin_5a_connection() -> str:
    profiles = okin_5a_profiles.PROFILES
    frames = {
        okin_5a_codec.MATTRESSFIRM_HANDSHAKE: "Mattress Firm handshake",
        okin_5a_codec.WAKE: "Wake / keep connected",
    }
    return _block(
        _table(
            ("Frame", "Bytes (hex)", "Sent by"),
            (
                (
                    name,
                    _hex(frame),
                    ", ".join(
                        _OKIN_5A_NAMES[key]
                        + (
                            f" ({profile.wake.index(frame) + 1} of {len(profile.wake)})"
                            if len(profile.wake) > 1
                            else ""
                        )
                        for key, profile in profiles.items()
                        if frame in profile.wake
                    ),
                )
                for frame, name in frames.items()
            ),
        )
    )


BLOCKS: list[Block] = [
    (GUIDE, "okin-5a-profiles", render_okin_5a_profiles),
    (GUIDE, "okin-5a-transports", render_okin_5a_transports),
    (GUIDE, "okin-5a-connection", render_okin_5a_connection),
    (GUIDE, "okin-5a-motors", lambda: _okin_5a_commands("motors")),
    (GUIDE, "okin-5a-presets", lambda: _okin_5a_commands("presets")),
    (GUIDE, "okin-5a-massage", lambda: _okin_5a_commands("massage")),
    (GUIDE, "okin-5a-lights", lambda: _okin_5a_commands("lights")),
]
