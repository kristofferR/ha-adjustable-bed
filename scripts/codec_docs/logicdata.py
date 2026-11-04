"""Generated block of the LOGICDATA app profiles, in the Jiecang codec guide."""

from __future__ import annotations

from collections.abc import Iterable

from custom_components.adjustable_bed.codec import jiecang as jiecang_codec
from custom_components.adjustable_bed.const import (
    LOGICDATA_APP_LAYOUTS,
    LOGICDATA_APP_PROFILES,
)
from custom_components.adjustable_bed.profiles import logicdata as logicdata_profiles
from scripts.codec_docs._common import Block, _block, _hex, _table
from scripts.codec_docs.jiecang import _schedule

GUIDE = "docs/beds/jiecang.md"

_LOGICDATA_QUERY_NAMES = {
    logicdata_profiles.QUERY_SOFTWARE: "Software",
    logicdata_profiles.QUERY_VIBRATION: "Vibration (massage)",
    logicdata_profiles.QUERY_HARDWARE: "Hardware",
    logicdata_profiles.QUERY_ACTUATOR: "Actuator status (selector `50`)",
    jiecang_codec.query(b"\x01"): "Actuator status (selector `01`)",
    logicdata_profiles.QUERY_LIGHT: "Light",
    logicdata_profiles.QUERY_STATUS: "Device status",
}


def _offsets(offsets: Iterable[int]) -> str:
    return ", ".join(f"+{offset} ms" for offset in offsets) or "none"


def _families(families: Iterable[str]) -> str:
    return ", ".join(family.upper() for family in families) or "none"


def _logicdata_massage_zones(layout: logicdata_profiles.Layout) -> str:
    """Zones of a layout, or none when no family that drives it has massage."""
    for profile in logicdata_profiles.APP_PROFILES.values():
        for family in profile.massage_families:
            try:
                logicdata_profiles.validate_setup(profile, family, layout)
            except ValueError:
                continue
            return "back, right" if layout == "split_series" else "back, legs"
    return "none"


def _logicdata_startup_tables() -> list[str]:
    """One query table per distinct schedule; a query's offsets share a row."""
    groups: dict[logicdata_profiles.Schedule, list[str]] = {}
    for key, profile in logicdata_profiles.APP_PROFILES.items():
        for family, schedule in profile.startup.items():
            groups.setdefault(schedule, []).append(
                f"{LOGICDATA_APP_PROFILES[key]} {family.upper()}"
            )
    lines: list[str] = []
    for schedule, labels in groups.items():
        rows: dict[bytes, list[int]] = {}
        for offset, command in schedule:
            rows.setdefault(command, []).append(offset)
        lines += [
            "",
            f"**{', '.join(labels)}**",
            "",
            *_table(
                ("Offsets", "Query", "Bytes (hex)"),
                (
                    (
                        ", ".join(f"{offset} ms" for offset in offsets),
                        _LOGICDATA_QUERY_NAMES[command],
                        _hex(command),
                    )
                    for command, offsets in rows.items()
                ),
            ),
        ]
    return lines[1:]


def render_logicdata_profiles() -> str:
    profiles = logicdata_profiles.APP_PROFILES
    names = {key: LOGICDATA_APP_PROFILES[key] for key in profiles}
    summary = _table(
        (
            "Profile",
            "P2 payload `00 00` on",
            "Presets (P1 / P2)",
            "Memory",
            "Massage",
            "Clock request",
            "Alarm",
            "Name rule",
            "Name writes",
        ),
        (
            (
                names[key],
                "back and legs movement, presets, memory, light"
                if profile.p2_controls
                else "back and legs movement",
                " / ".join(", ".join(profile.presets[family]) for family in ("p1", "p2")),
                f"{profile.memory_slots} slot{'s' if profile.memory_slots > 1 else ''}",
                _families(profile.massage_families),
                "none"
                if profile.clock_request_length is None
                else f"{profile.clock_request_length}+ bytes",
                _families(profile.alarm_families),
                f"`{profile.name_rule.pattern}` ({profile.name_rule.encoding})",
                _offsets(profile.rename_offsets)
                + ("; T1 bare" if profile.bare_t1_name else "; always wrapped"),
            )
            for key, profile in profiles.items()
        ),
    )
    timing = _table(
        (
            "Profile",
            "Movement refresh",
            "Touch release",
            "Held presets (P1 / P2)",
            "Hold refresh",
            "Memory save",
            "Light",
            "Massage mode",
            "Massage query",
        ),
        (
            (
                names[key],
                f"{profile.movement_repeat_ms} ms, final frame",
                _schedule(profile.touch_release),
                " / ".join(
                    ", ".join(profile.held_presets[family]) or "none" for family in ("p1", "p2")
                )
                + (" (buttons hold)" if profile.hold_only_presets else ""),
                ", ".join(
                    f"{preset} {ms} ms"
                    + (" + final frame" if preset in profile.hold_final_frame else "")
                    for preset, ms in profile.hold_repeat_ms.items()
                ),
                _offsets(profile.memory_save_offsets)
                + ("" if profile.memory_save_payload is None else ", no payload"),
                _schedule(profile.light_releases),
                _schedule(profile.massage_mode_releases),
                _offsets(offset for offset, _ in profile.massage_query),
            )
            for key, profile in profiles.items()
        ),
    )
    sessions = _table(
        ("Profile", "Wait, then subscribe", "T3 name subscription", "Clock"),
        (
            (
                names[key],
                f"{profile.subscribe_delay_ms} ms",
                f"at +{profile.name_subscribe_ms} ms"
                if profile.session == "motionrelax"
                else f"{profile.name_subscribe_ms} ms after T3 data; queries only once both succeed",
                f"at {_offsets(profile.clock_startup_offsets)}"
                if profile.clock_startup_offsets
                else ("on request" if profile.clock_request_length is not None else "none"),
            )
            for key, profile in profiles.items()
        ),
    )
    layouts = _table(
        ("Layout", "Axes", "Massage zones", "Profiles"),
        (
            (
                f"`{layout}` ({LOGICDATA_APP_LAYOUTS[layout]})",
                ", ".join(axes),
                _logicdata_massage_zones(layout),
                ", ".join(
                    names[key]
                    for key, profile in profiles.items()
                    if profile.layouts.get(layout) == axes
                ),
            )
            for layout in logicdata_profiles.MOTIONRELAX_LAYOUTS
            for axes in dict.fromkeys(
                profile.layouts[layout]
                for profile in profiles.values()
                if layout in profile.layouts
            )
        ),
    )
    return _block(
        "**LOGICDATA profile summary**",
        summary,
        "**LOGICDATA timing**",
        timing,
        "**LOGICDATA startup**",
        sessions,
        _logicdata_startup_tables(),
        "**LOGICDATA layouts and axes**",
        layouts,
    )


BLOCKS: list[Block] = [
    (GUIDE, "logicdata-profiles", render_logicdata_profiles),
]
