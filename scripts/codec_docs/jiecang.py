"""Generated blocks of the Jiecang F1 codec guide."""

from __future__ import annotations

from collections.abc import Iterable

from custom_components.adjustable_bed import controller_factory
from custom_components.adjustable_bed.beds.jiecang_app import LIGHT_TIMEOUTS
from custom_components.adjustable_bed.codec import jiecang as jiecang_codec
from custom_components.adjustable_bed.const import (
    BED_TYPE_JIECANG_APP,
    JIECANG_APP_LAYOUTS,
    JIECANG_APP_PROFILES,
)
from custom_components.adjustable_bed.profiles import jiecang as jiecang_profiles
from scripts.codec_docs._common import Block, _block, _hex, _table

GUIDE = "docs/beds/jiecang.md"

_RELEASE_NAMES = {
    jiecang_codec.SHORT_RELEASE: "short release",
    jiecang_codec.LONG_RELEASE: "long release",
}
_TRANSPORT_ALIASES = {"g1": "Lierda1 / Comfort Motion", "g3": "Lierda3 / LOGICDATA"}
_AXIS_LABELS: dict[jiecang_codec.Axis, str] = {
    "back": "Back",
    "legs": "Legs",
    "both": "Both (back and legs)",
    "head": "Head / neck",
    "bed_height": "Bed height",
    "lumbar": "Lumbar",
    "right_back": "Right back",
    "both_backs": "Both backs",
    "right_legs": "Right legs",
    "both_legs": "Both legs",
}
_PRESET_LABELS: dict[jiecang_codec.Preset, str] = {
    "flat": "Flat",
    "zero_g": "Zero-G",
    "anti_snore": "Anti-Snore",
    "yoga": "Yoga (only when the bed reports it)",
}
_ZONE_LABELS: dict[jiecang_codec.MassageZone, str] = {
    "back": "Head (back)",
    "legs": "Foot (legs)",
    "right": "Right",
}
_QUERY_NAMES = {
    jiecang_codec.query(): "Initial status",
    jiecang_profiles.QUERY_SOFTWARE: "Software",
    jiecang_profiles.QUERY_LIGHT: "Light",
    jiecang_codec.query(b"\x01"): "Actuator",
    jiecang_codec.query(b"\x50"): "Actuator",
    jiecang_profiles.QUERY_HARDWARE: "Hardware",
    jiecang_profiles.QUERY_VIBRATION: "Vibration (massage)",
    jiecang_profiles.QUERY_ALARM: "Alarm",
}


def _profiles() -> dict[str, jiecang_profiles.JiecangProfile]:
    return {"legacy": jiecang_profiles.LEGACY, **jiecang_profiles.APP_PROFILES}


def _name(key: str) -> str:
    return "Legacy route" if key == "legacy" else JIECANG_APP_PROFILES[key]


def bed_types() -> dict[str, tuple[str, ...]]:
    """Bed types per profile: the legacy route from the factory registry.

    App profiles are chosen inside the ``jiecang_app`` factory branch;
    ``tests/test_codec_docs.py`` checks both against ``create_controller``.
    """
    legacy = tuple(
        bed_type
        for bed_type, spec in controller_factory._SIMPLE_CONTROLLERS.items()
        if (spec.module, spec.class_name) == ("jiecang", "JiecangController")
    )
    return {
        "legacy": legacy,
        **dict.fromkeys(jiecang_profiles.APP_PROFILES, (BED_TYPE_JIECANG_APP,)),
    }


def _names(keys: Iterable[str]) -> str:
    return ", ".join(_name(key) for key in keys) or "none"


def _frame(command: bytes) -> str:
    return _RELEASE_NAMES.get(command) or _hex(command)


def _schedule(schedule: jiecang_profiles.Schedule) -> str:
    return ", ".join(f"+{offset} ms {_frame(command)}" for offset, command in schedule) or "none"


def _tap(tap: jiecang_profiles.Tap) -> str:
    sends = f"{tap.repeats} × {tap.repeat_ms} ms" if tap.repeats > 1 else "once"
    if tap.release is None:
        return f"{sends}, no release"
    return f"{sends}, {_frame(tap.release)} after {tap.release_after_ms} ms"


def _massage(levels: tuple[int, ...]) -> str:
    span = f"0-{len(levels) - 1}"
    if levels == tuple(range(len(levels))):
        return f"{span} (wire equals level)"
    return f"{span} (wire {' '.join(f'{wire:02X}' for wire in levels)})"


def _startup_tables() -> list[str]:
    """One query table per distinct startup schedule, consecutive repeats on one row."""
    groups: dict[jiecang_profiles.Schedule, list[str]] = {}
    for key, profile in _profiles().items():
        if profile.bootstrap:
            groups.setdefault(profile.bootstrap, []).append(key)
    lines: list[str] = []
    for schedule, keys in groups.items():
        rows: list[tuple[list[int], bytes]] = []
        for offset, command in schedule:
            if rows and rows[-1][1] == command:
                rows[-1][0].append(offset)
            else:
                rows.append(([offset], command))
        lines += [
            "",
            f"**{_names(keys)}**",
            "",
            *_table(
                ("Offset", "Query", "Bytes (hex)"),
                (
                    (
                        ", ".join(f"{offset} ms" for offset in offsets),
                        _QUERY_NAMES[command],
                        _hex(command),
                    )
                    for offsets, command in rows
                ),
            ),
        ]
    return lines[1:]


def render_jiecang_profiles() -> str:
    profiles = _profiles()
    types = bed_types()
    summary = _table(
        ("Profile", "Bed type", "Transports", "Memory", "Massage levels", "Name rule", "Startup"),
        (
            (
                _name(key),
                ", ".join(f"`{bed_type}`" for bed_type in types[key]),
                ", ".join(transport.upper() for transport in profile.transports),
                f"{profile.memory_slots} slots, payload {_hex(profile.memory_payload)}",
                _massage(profile.massage_levels),
                f"`{profile.name_rule.pattern}`" if profile.name_rule else "none",
                f"{len(profile.bootstrap)} queries, last at +{profile.bootstrap[-1][0]} ms"
                if profile.bootstrap
                else "none",
            )
            for key, profile in profiles.items()
        ),
    )
    timing = _table(
        (
            "Profile",
            "Hold refresh",
            "Repeats",
            "Final frame",
            "Release after hold",
            "Explicit stop",
        ),
        (
            (
                _name(key),
                f"{profile.hold.repeat_ms} ms ({'fixed rate' if profile.fixed_rate else 'after each write'})",
                str(profile.hold.repeats or "motor pulse count"),
                "yes" if profile.hold.final_frame else "no",
                _schedule(profile.hold.releases),
                _schedule(
                    tuple(
                        (offset - profile.hold.releases[0][0], command)
                        for offset, command in profile.hold.releases
                    )
                ),
            )
            for key, profile in profiles.items()
        ),
    )
    actions = _table(
        ("Profile", "Presets and memory recall", "Memory save"),
        (
            (_name(key), _tap(profile.recall), _tap(profile.memory_save))
            for key, profile in profiles.items()
        ),
    )
    layouts: dict[tuple[str, tuple[str, ...]], list[str]] = {}
    for key, profile in profiles.items():
        for layout, axes in profile.layouts.items():
            layouts.setdefault((layout, axes), []).append(key)
    layout_table = _table(
        (
            "Layout",
            "Axes",
            "Motion payload",
            "Bilateral presets and massage",
            "Massage zones",
            "Profiles",
        ),
        (
            (
                f"`{layout}` ({JIECANG_APP_LAYOUTS[layout]})",
                ", ".join(axes),
                _hex(jiecang_profiles.motion_payload(layout)),
                "yes" if jiecang_profiles.is_bilateral(layout) else "no",
                ", ".join(jiecang_profiles.massage_zones(layout)),
                _names(keys),
            )
            for (layout, axes), keys in sorted(
                layouts.items(), key=lambda item: list(JIECANG_APP_LAYOUTS).index(item[0][0])
            )
        ),
    )
    layoutless = _names(key for key, profile in profiles.items() if not profile.layouts)
    return _block(
        "### Profile summary",
        summary,
        "### Hold and release timing",
        "Release offsets count from the last hold frame.",
        timing,
        "### One-shot timing",
        actions,
        "### Layouts and axes",
        layout_table,
        f"{layoutless} has no selectable layouts: it uses the entry's motor count.",
        "### Startup queries",
        "Offsets count from the start of the profile's startup sequence (see its Timing). "
        "Each query is listed with every offset it is sent at.",
        _startup_tables(),
    )


def render_jiecang_transports() -> str:
    profiles = _profiles()
    return _block(
        _table(
            ("Selection", "Service", "Write", "Notify", "Name", "Profiles"),
            (
                (
                    key.upper()
                    + (f" ({_TRANSPORT_ALIASES[key]})" if key in _TRANSPORT_ALIASES else ""),
                    f"`{transport.service_uuid}`",
                    f"`{transport.write_uuid}`",
                    "same as write"
                    if transport.notify_uuid == transport.write_uuid
                    else f"`{transport.notify_uuid}`",
                    f"`{transport.name_uuid}`" if transport.name_uuid else "none",
                    _names(name for name, profile in profiles.items() if key in profile.transports),
                )
                for key, transport in jiecang_codec.TRANSPORTS.items()
            ),
        )
    )


def render_jiecang_motion() -> str:
    standard: set[jiecang_codec.Axis] = set()
    bilateral: set[jiecang_codec.Axis] = set()
    for profile in _profiles().values():
        for layout, axes in profile.layouts.items():
            sent = (
                bilateral
                if jiecang_profiles.motion_payload(layout) == jiecang_codec.BILATERAL
                else standard
            )
            sent.update(axes)
    groups: dict[int, list[jiecang_codec.Axis]] = {}
    for axis, opcode in jiecang_codec.AXIS_OPCODES.items():
        groups.setdefault(opcode, []).append(axis)

    def pair(
        axes: list[jiecang_codec.Axis], sent: set[jiecang_codec.Axis], payload: bytes
    ) -> tuple[str, str]:
        if not sent.intersection(axes):
            return ("n/a", "n/a")
        return (
            _hex(jiecang_codec.motion(axes[0], True, payload)),
            _hex(jiecang_codec.motion(axes[0], False, payload)),
        )

    rows = []
    for axes in groups.values():
        up, down = pair(axes, standard, jiecang_codec.STANDARD)
        bi_up, bi_down = pair(axes, bilateral, jiecang_codec.BILATERAL)
        rows.append(
            (
                ", ".join(
                    label if index == 0 else label.lower()
                    for index, label in enumerate(_AXIS_LABELS[axis] for axis in axes)
                ),
                up,
                down,
                "n/a" if bi_up == "n/a" else f"{bi_up} / {bi_down}",
            )
        )
    return _block(
        _table(("Axis", "Up", "Down", "Bilateral up / down"), rows),
        _table(
            ("Release", "Bytes (hex)", "Description"),
            (
                ("Short release", _hex(jiecang_codec.SHORT_RELEASE), "Button release / stop all"),
                ("Long release", _hex(jiecang_codec.LONG_RELEASE), "Bilateral release"),
            ),
        ),
    )


def render_jiecang_presets() -> str:
    return _block(
        _table(
            ("Command", "Standard", "Bilateral layouts"),
            (
                (
                    label,
                    _hex(jiecang_profiles.preset_command(None, preset)),
                    _hex(jiecang_profiles.preset_command("standard_4_bilateral", preset)),
                )
                for preset, label in _PRESET_LABELS.items()
            ),
        )
    )


def render_jiecang_memory() -> str:
    slots: dict[bytes, int] = {}
    for profile in _profiles().values():
        slots[profile.memory_payload] = max(
            slots.get(profile.memory_payload, 0), profile.memory_slots
        )

    def row(label: str, slot: int, save: bool) -> tuple[str, ...]:
        return (
            label,
            *(
                _hex(jiecang_codec.memory(slot, save=save, payload=payload))
                if slot <= count
                else "n/a"
                for payload, count in slots.items()
            ),
        )

    top = max(slots.values())
    return _block(
        _table(
            ("Command", *(f"Payload {_hex(payload)}" for payload in slots)),
            [
                *(row(f"Memory {slot} recall", slot, False) for slot in range(1, top + 1)),
                *(row(f"Memory {slot} save", slot, True) for slot in range(1, top + 1)),
            ],
        )
    )


def render_jiecang_massage() -> str:
    app_levels = {profile.massage_levels for profile in jiecang_profiles.APP_PROFILES.values()}
    if len(app_levels) != 1:
        raise ValueError("App profiles disagree on massage levels; split the massage table")
    (levels,) = app_levels
    legacy = jiecang_profiles.LEGACY.massage_levels
    zones = _table(
        ("Zone", "Zone byte", "Off", *(f"Level {level}" for level in range(1, len(levels)))),
        (
            (
                _ZONE_LABELS[zone],
                f"`{opcode:02X}`",
                *(_hex(jiecang_codec.massage(zone, wire)) for wire in levels),
            )
            for zone, opcode in jiecang_codec.MASSAGE_OPCODES.items()
        ),
    )
    return _block(
        zones,
        f"Level columns show the app levels 0-{len(levels) - 1} "
        f"(wire {'/'.join(f'`{wire:02X}`' for wire in levels)}). The legacy route sends "
        f"wire levels 0-{legacy[-1]} directly for the back and foot zones, for example "
        f"{_hex(jiecang_codec.massage('back', legacy[len(legacy) // 2]))}.",
        _table(
            ("Command", "Standard", "Bilateral layouts"),
            (
                ("Massage start", _hex(jiecang_codec.massage_start()), "n/a"),
                (
                    "Massage stop",
                    _hex(jiecang_codec.massage_stop()),
                    _hex(jiecang_codec.massage_stop(bilateral=True)),
                ),
                (
                    "Massage mode",
                    _hex(jiecang_codec.massage_mode()),
                    _hex(jiecang_codec.massage_mode(bilateral=True)),
                ),
            ),
        ),
    )


def render_jiecang_lights() -> str:
    tap = jiecang_profiles.DREAMHD.recall
    return _block(
        _table(
            ("Command", "Bytes (hex)", "Description"),
            (
                (
                    "Light toggle (legacy route, Comfort Motion, Dream Motion HD)",
                    _hex(jiecang_codec.light_toggle()),
                    "The only light command of the first two; Dream Motion HD sends it after the RGB state write",
                ),
                (
                    "Light toggle (ERGOBALANCE, Dream Motion)",
                    _hex(jiecang_codec.light_toggle(jiecang_codec.BILATERAL)),
                    "Sent after the RGB state write",
                ),
                (
                    "Automatic light toggle",
                    _hex(jiecang_codec.AUTOMATIC_LIGHT_TOGGLE),
                    "Sent only when the reported state differs. ERGOBALANCE and Dream Motion write "
                    f"it once; Dream Motion HD sends it as a tap, with a {_frame(tap.release or b'')} "
                    f"{tap.release_after_ms} ms later",
                ),
                (
                    "RGB state",
                    "`F1 F1 52 07 BB GG RR brightness time_hi time_lo on checksum 7E`",
                    "Blue, green, red 0-255; brightness 0-100; big-endian timeout seconds; on `00`/`01`",
                ),
            ),
        ),
        f"Timeouts: {', '.join(str(seconds) for seconds in LIGHT_TIMEOUTS[:-1])} or "
        f"{LIGHT_TIMEOUTS[-1]} seconds.",
    )


def render_jiecang_queries() -> str:
    senders: dict[bytes, list[str]] = {}
    for key, profile in _profiles().items():
        for _, command in profile.bootstrap:
            if key not in senders.setdefault(command, []):
                senders[command].append(key)
    return _block(
        _table(
            ("Query", "Bytes (hex)", "Startup query of"),
            (
                (_QUERY_NAMES[command], _hex(command), _names(keys))
                for command, keys in sorted(senders.items(), key=lambda item: item[0])
            ),
        )
    )


BLOCKS: list[Block] = [
    (GUIDE, "jiecang-profiles", render_jiecang_profiles),
    (GUIDE, "jiecang-transports", render_jiecang_transports),
    (GUIDE, "jiecang-motion", render_jiecang_motion),
    (GUIDE, "jiecang-presets", render_jiecang_presets),
    (GUIDE, "jiecang-memory", render_jiecang_memory),
    (GUIDE, "jiecang-massage", render_jiecang_massage),
    (GUIDE, "jiecang-lights", render_jiecang_lights),
    (GUIDE, "jiecang-queries", render_jiecang_queries),
]
