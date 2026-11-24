"""Generate SUTA's selectors, complete command domains and panel timing."""

from custom_components.adjustable_bed.codec import suta as codec
from custom_components.adjustable_bed.profiles import suta as app

from ._common import Block, _block, _hex, _table

GUIDE = "docs/beds/suta.md"


def routes() -> str:
    return _block(_table(("Name route", "Controller"), ((key, value or "No controller") for key, value in app.ROUTES.items())))


def commands() -> str:
    rows = []
    for key, profile in app.PROFILES.items():
        for action, command in profile.commands.items():
            rows.extend((key, action + (" " + suffix if suffix else ""), _hex(codec.text(command.text + suffix))) for suffix in command.suffixes or ("",))
    rows.extend(("Shared text", action, _hex(codec.text(command.text))) for action, command in app.SHARED.items())
    for action in app.BINARY.values():
        rows.extend(("/".join(action.controllers), action.key + " " + p[6:].hex(" "), _hex(codec.from_prefix(p))) for p in action.prefixes)
    return _block(_table(("Panel", "Action / parameter", "Frame"), rows))


def timing() -> str:
    return _block(_table(
        ("Panel", "Refresh ms", "Save threshold s", "Action", "Count / initial / interval ms", "Source owner"),
        ((key, str(profile.refresh_ms), str(profile.threshold_s), action,
          f"{command.count} / {command.delay_ms} / {command.interval_ms}", command.source_scope)
         for key, profile in app.PROFILES.items() for action, command in profile.commands.items()),
    ))


BLOCKS: list[Block] = [
    (GUIDE, "suta-routes", routes),
    (GUIDE, "suta-commands", commands),
    (GUIDE, "suta-timing", timing),
]


def truemotion_routes() -> str:
    from custom_components.adjustable_bed.profiles import truemotion as tm

    names = ("B202", "B202B", "B202D", "B205", "B205B", "B205C", "B206", "B206A",
             "B206B", "B206C", "B206D", "B206E", "B206F", "B206G", "B206H", "B207",
             "B301", "B402", "B402B", "B603", "B604", "B604A", "B701", "B903")
    rows = []
    for suffix in (*names, "other"):
        name = tm.PREFIX + suffix
        split = tm.profile_for_name(name, split=True).model if tm.supports_pair_primary(name) else "—"
        rows.append((name, tm.profile_for_name(name).model, split))
    return _block(_table(("Name starts with", "Standalone editor", "Split editor as primary"), rows))


def truemotion_commands() -> str:
    from custom_components.adjustable_bed.profiles import truemotion as tm

    rows = []
    for model, profile in tm.PROFILES.items():
        entries = [
            (f"{axis.key} {direction}", axis.text(direction), f"Tap once, hold every {axis.interval_ms} ms")
            for axis, direction in profile.controls.values()
        ]
        entries.extend((mode, tm.preset(mode), "Once") for mode in profile.presets)
        entries.extend((f"Save {mode}", tm.preset(mode, save=True),
                        f"3 × {tm.REPEAT_MS} ms after {tm.SAVE_DELAY_MS} ms") for mode in profile.saves)
        if profile.massage_schedule:
            for zone in ("HEAD", "FOOT"):
                entries.extend((f"{zone} timer {code}", tm.massage(zone, "DT", code),
                                f"3 × {tm.REPEAT_MS} ms") for code in tm.TIMERS)
                entries.extend((f"{zone} level {code}", tm.massage(zone, "LV", code),
                                {"b202": "Paired zone bursts", "delayed_foot": "Delayed Foot write",
                                 "b603": "Active-zone bursts"}[profile.massage_schedule]) for code in tm.LEVELS)
        if profile.light:
            entries.extend((f"Light {'on' if enabled else 'off'}", tm.light(enabled),
                            f"3 × {tm.REPEAT_MS} ms") for enabled in (True, False))
        if profile.lock:
            entries.extend((f"Lock {'on' if enabled else 'off'}", tm.lock(enabled),
                            f"3 × {tm.REPEAT_MS} ms") for enabled in (True, False))
        if profile.dedicated_stop:
            entries.append(("Stop all", tm.STOP, "Once, then both timers off"))
        if profile.has_beep:
            entries.append(("Enable beep", tm.BEEP, "Once"))
        rows.extend((model, label, _hex(codec.text(frame)), timing) for label, frame, timing in entries)
    rows.extend((
        ("Standalone", "Read firmware version", _hex(codec.text(tm.VERSION)), "Once"),
        ("All", "Release motion", _hex(codec.text(tm.STOP)), f"3 × {tm.REPEAT_MS} ms"),
    ))
    return _block(_table(("Editor", "Control", "Frame", "Timing"), rows))


BLOCKS += [
    (GUIDE, "truemotion-routes", truemotion_routes),
    (GUIDE, "truemotion-commands", truemotion_commands),
]
