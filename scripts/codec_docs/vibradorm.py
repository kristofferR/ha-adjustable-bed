"""Generated blocks of the Vibradorm VMAT codec guide."""

from __future__ import annotations

from custom_components.adjustable_bed.codec import vibradorm as codec
from custom_components.adjustable_bed.const import (
    BED_TYPE_VIBRADORM,
    BED_TYPE_VIBRADORM_APP,
    BED_TYPE_VMATBASIC,
    CONF_VIBRADORM_APP_PROFILE,
    CONF_VMATBASIC_PROFILE,
    VIBRADORM_APP_PROFILES,
    VMATBASIC_PROFILES,
)
from custom_components.adjustable_bed.profiles import vibradorm as profiles
from custom_components.adjustable_bed.profiles import vmatbasic
from scripts.codec_docs._common import Block, _block, _hex, _table

GUIDE = "docs/beds/vibradorm.md"
_SECTIONS = {
    "legacy": "[Generic controller](#generic-controller)",
    "caresse": "[Caresse and Werkmeister](#caresse-and-werkmeister)",
    "werkmeister": "[Caresse and Werkmeister](#caresse-and-werkmeister)",
    "vmat": "[VMAT](#vmat)",
    **dict.fromkeys(VMATBASIC_PROFILES, "[V-MAT Basic](#v-mat-basic)"),
}


def _uuid(uuid: str) -> str:
    return f"`{uuid}`"


def render_vibradorm_profiles() -> str:
    rows = [
        (
            "`legacy`",
            f"`{BED_TYPE_VIBRADORM}`",
            "detection or **Legacy setup**",
            _SECTIONS["legacy"],
        )
    ]
    rows += [
        (
            f"`{key}`",
            f"`{BED_TYPE_VIBRADORM_APP}`",
            f"`{CONF_VIBRADORM_APP_PROFILE}` = {label}",
            _SECTIONS[key],
        )
        for key, label in VIBRADORM_APP_PROFILES.items()
    ]
    rows += [
        (
            f"`{key}`",
            f"`{BED_TYPE_VMATBASIC}`",
            f"`{CONF_VMATBASIC_PROFILE}` = {label}",
            _SECTIONS[key],
        )
        for key, label in VMATBASIC_PROFILES.items()
    ]
    return _block(_table(("Profile key", "Bed type", "Chosen by", "Section"), rows))


def render_vibradorm_transports() -> str:
    rows = (
        ("Control service", codec.SERVICE_UUID, "generic; VMAT (exact service); V-MAT Basic"),
        ("Motor", codec.MOTOR_CHAR_UUID, "generic; basic app layouts; V-MAT Basic"),
        ("Light", codec.LIGHT_CHAR_UUID, "generic; basic app layouts; V-MAT Basic CBI"),
        (
            "CBI (V-MAT Basic: XT)",
            codec.CBI_CHAR_UUID,
            "every profile but V-MAT Basic `basic` and `cbi`",
        ),
        ("Response", codec.RESPONSE_CHAR_UUID, "generic; nonbasic app layouts; VMAT"),
        (
            "Status service",
            codec.STATUS_SERVICE_UUID,
            "generic (secondary service); VMAT; V-MAT Basic",
        ),
        ("ED", codec.ED_CHAR_UUID, "V-MAT Basic"),
        ("Temperature", codec.TEMPERATURE_CHAR_UUID, "V-MAT Basic"),
        ("Management", codec.MANAGEMENT_CHAR_UUID, "VMAT setup"),
    )
    return _block(
        _table(
            ("Role", "UUID", "Used by"), ((role, _uuid(uuid), users) for role, uuid, users in rows)
        )
    )


def render_vibradorm_generic_commands() -> str:
    p = profiles.LEGACY
    rows = (
        ("Stop", codec.STOP, "Stops all motors"),
        ("Head Up (KH)", p.back_up, "back; also head on 2-motor beds"),
        ("Head Down (KR)", p.back_down, "back; also head on 2-motor beds"),
        ("Legs Up (OSH)", p.legs_up, "also feet on 2/3-motor beds"),
        ("Legs Down (OSR)", p.legs_down, "also feet on 2/3-motor beds"),
        ("Neck Up (NH)", p.head_up, "head on 3/4-motor beds"),
        ("Neck Down (NR)", p.head_down, "head on 3/4-motor beds"),
        ("Foot Up (FH)", p.feet_up, "feet on 4-motor beds"),
        ("Foot Down (FR)", p.feet_down, "feet on 4-motor beds"),
        ("All Down/Flat (AR)", p.flat, "used as the flat preset"),
        *((f"Memory {slot}", code, "recall") for slot, code in p.memory.items()),
    )
    commands = _table(
        ("Command", "Motor frame", "Description"),
        ((name, _hex(codec.motor(code)), text) for name, code, text in rows),
    )
    cbi = _table(
        ("Command", "CBI frame, T = 0 / T = 8000"),
        (
            (name, " / ".join(_hex(codec.command(word, parameters, t)) for t in (0, codec.TOGGLE)))
            for name, word, parameters in (
                ("Store", p.store, b""),
                *((f"Save memory {slot}", code, b"") for slot, code in p.memory.items()),
                ("Vibration on", p.vibration, b"\x01"),
                ("Vibration off", p.vibration, b"\x00"),
                ("CmdGetStatusMotMon", *p.status_request),
            )
        ),
    )
    lights = _table(
        ("Command", "Light frame"),
        (("Light on", _hex(codec.light(p.light_on, 0))), ("Light off", _hex(codec.light(0, 0)))),
    )
    return _block(commands, cbi, lights)


def _app_layouts() -> list[profiles.VibradormAppProfile]:
    validate = profiles.validate_vibradorm_app_profile
    layouts = [validate("caresse", c, restored=True) for c in (-1, 0, 1, 2, 3, 4, 5, 6, 7)]
    layouts += [validate("werkmeister", c) for c in (5, 7)]
    for ordinal, r in profiles.VMAT_REMOTES.items():
        flags = {"rgb": r.rgb, "massage": r.massage, "light_extension": r.light_extension}
        layouts.append(
            validate("vmat", r.control_type, floor_light=r.floor_light, remote=ordinal, **flags)
        )
    return layouts


def _held(layout: profiles.VibradormAppProfile) -> set[str]:
    """The held motor and memory controls a layout offers."""
    motors = {
        action
        for action in profiles.MOTORS
        if action.startswith("all_") and layout.groups or action.rsplit("_", 1)[0] in layout.groups
    }
    return motors | {f"memory_{slot}" for slot in range(1, layout.memory_slots + 1)}


def render_vibradorm_app_commands() -> str:
    actions = [(action, code) for action, code in profiles.MOTORS.items()]
    actions += [(f"memory_{slot}", code) for slot, code in enumerate(profiles.MEMORY, 1)]
    basic = set().union(*(_held(layout) for layout in _app_layouts() if layout.basic))
    rows = [
        (
            f"`{action}`",
            _hex(codec.motor(code)) if action in basic else "n/a",
            _hex(codec.command(code)),
        )
        for action, code in actions
    ]
    rows.append(("Release", _hex(codec.motor(codec.STOP)), _hex(codec.command(codec.STOP))))
    return _block(
        _table(("`hold_control`", "Basic: motor frame", "CBI frame, T = 0"), rows),
        "A CBI frame ORs the toggle into its first byte (`80`); the release frame never carries it.",
    )


def render_vibradorm_mood_palettes() -> str:
    vmat = list(profiles.VMAT_MOOD_PALETTE.values())
    return _block(
        _table(
            ("Palette index", "HA option", "Caresse packet RGB", "VMAT packet RGB"),
            (
                (
                    str(index),
                    f"`{option}`",
                    ", ".join(map(str, rgb)),
                    ", ".join(map(str, vmat[index])),
                )
                for index, (option, rgb) in enumerate(profiles.MOOD_PALETTE.items())
            ),
        )
    )


def render_vibradorm_vmat_remotes() -> str:
    def yes(flag: bool) -> str:
        return "Yes" if flag else "No"

    rows = []
    layouts = {layout.remote: layout for layout in _app_layouts() if layout.remote}
    for ordinal, remote in profiles.VMAT_REMOTES.items():
        layout = layouts[ordinal]
        rows.append(
            (
                ordinal,
                remote.asset,
                str(remote.control_type),
                ", ".join(remote.groups).capitalize(),
                str(layout.memory_slots) if layout.memory_slots else "No",
                yes(layout.sync),
                yes(remote.floor_light),
                yes(remote.rgb and remote.massage),
                "Basic" if layout.basic else "CBI",
            )
        )
    header = ("Remote", "Image", "Control", "Logical groups", "Memory", "Sync", "Floor")
    return _block(_table((*header, "Mood / massage", "Movement route"), rows))


_STAGES = {
    "xmc_status": "Status",
    "opmode": "Operating mode",
    "main_firmware_article": "Article",
    "device_name": "Name",
    "revision_id": "Revision ID",
    "revision_string": "Revision string",
    "variant": "Variant",
}


def render_vibradorm_vmat_stages() -> str:
    rows = (
        (_STAGES[field], _hex(request), f"`{prefix.hex()}`", f"{timeout:g} s")
        for field, request, prefix, timeout in profiles.VMAT_QUERY_STAGES
    )
    return _block(
        _table(("Stage", "CBI request", "Reply prefix", "Reply timeout"), rows),
        f"After native pairing, setup closes with {_hex(profiles.VMAT_CLOSE)}.",
    )


def render_vibradorm_vmatbasic_commands() -> str:
    motors = _table(
        ("Command", "`hold_control`", "Motor frame"),
        [
            (action.replace("_", " ").capitalize(), f"`{action}`", _hex(codec.motor(code)))
            for action, code in vmatbasic.MOTOR_ACTIONS.items()
        ]
        + [("Release", "", _hex(codec.motor(codec.STOP)))],
    )
    xt = _table(
        ("XT-Box command", "CBI frame"),
        [
            ("Floor hold (`floor_hold`)", _hex(codec.command(vmatbasic.FLOOR))),
            ("Mood toggle", _hex(codec.command(vmatbasic.MOOD))),
            ("Mood nightlight", _hex(vmatbasic.rgb(0))),
            *((f"Mood effect e{n}", _hex(vmatbasic.effect(n))) for n in (1, 2, 3)),
            *(
                (f"Massage {action.replace('_', ' ')}", _hex(codec.command(word)))
                for action, word in vmatbasic.MASSAGE_ACTIONS.items()
            ),
        ],
    )
    return _block(motors, xt)


BLOCKS: list[Block] = [
    (GUIDE, "vibradorm-profiles", render_vibradorm_profiles),
    (GUIDE, "vibradorm-transports", render_vibradorm_transports),
    (GUIDE, "vibradorm-generic-commands", render_vibradorm_generic_commands),
    (GUIDE, "vibradorm-app-commands", render_vibradorm_app_commands),
    (GUIDE, "vibradorm-mood-palettes", render_vibradorm_mood_palettes),
    (GUIDE, "vibradorm-vmat-remotes", render_vibradorm_vmat_remotes),
    (GUIDE, "vibradorm-vmat-stages", render_vibradorm_vmat_stages),
    (GUIDE, "vibradorm-vmatbasic-commands", render_vibradorm_vmatbasic_commands),
]
