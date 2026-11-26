"""Bedgear tables over the shared HHC codec, from its own app profile."""

from custom_components.adjustable_bed.codec import motomotion as codec
from custom_components.adjustable_bed.profiles.bedgear import BedgearProfile
from scripts.codec_docs._common import _block, _hex, _table

GUIDE = "docs/beds/motomotion.md"
PAIRS = ("15", "35", "E1", "81", "51", "44", "91", "13", "71", "61", "D1", "34", "23", "01", "97")


def profiles() -> str:
    rows = []
    for pair in PAIRS:
        p = BedgearProfile("HHC00000" + pair + "D00X")
        rows.append(
            (
                pair,
                p.panel,
                ", ".join(axis for axis, _, _ in p.axes),
                str(p.memory_slots),
                ", ".join(key for key, _ in p.presets),
            )
        )
    return _block(
        _table(
            (
                "Panel selector example (name[8:10])",
                "Layout",
                "Motor zones",
                "Memory slots",
                "Presets",
            ),
            rows,
        )
    )


def commands() -> str:
    controls = {}
    for pair in PAIRS:
        p = BedgearProfile("HHC00000" + pair + "D00X")
        for c in p.controls:
            controls[c.key, c.letter, c.release, c.held] = None
    return _block(
        _table(
            ("Control", "Plain bytes", "M-name bytes", "Press", "Release"),
            (
                (
                    key.replace("_", " "),
                    _hex(codec.letter_command(letter)),
                    _hex(codec.letter_command(letter, wrapped=True)),
                    "100 ms refresh" if held else "once",
                    release,
                )
                for key, letter, release, held in controls
            ),
        )
    )


def timing() -> str:
    p = BedgearProfile("HHC0000001D00X")
    return _block(
        _table(
            ("Behavior", "Value"),
            (
                ("First held tick and interval", f"{p.refresh_ms} ms, no immediate write"),
                ("Motor STOP", f"{p.stop_count} writes, {p.stop_interval_ms} ms apart"),
                (
                    "Short up, fewer than five ticks and no custom up",
                    f"{p.fallback_count} extra writes, {p.refresh_ms} ms apart",
                ),
            ),
        )
    )


BLOCKS = [
    (GUIDE, "bedgear-layouts", profiles),
    (GUIDE, "bedgear-controls", commands),
    (GUIDE, "bedgear-timing", timing),
]


def l2motion_layouts() -> str:
    from custom_components.adjustable_bed.profiles.l2motion import LAYOUT_EXAMPLES, L2MotionProfile

    return _block(
        _table(
            ("Name selector example", "Layout", "Motor zones", "Memory slots", "Presets"),
            (
                (
                    pair,
                    p.panel,
                    ", ".join(axis for axis, _, _ in p.axes),
                    str(p.memory_slots),
                    ", ".join(key for key, _ in p.presets),
                )
                for pair in LAYOUT_EXAMPLES
                for p in (L2MotionProfile("HHC00000" + pair + "D00X"),)
            ),
        )
    )


def l2motion_controls() -> str:
    from custom_components.adjustable_bed.profiles.l2motion import LAYOUT_EXAMPLES, L2MotionProfile

    controls = dict.fromkeys(
        c for pair in LAYOUT_EXAMPLES for c in L2MotionProfile("HHC00000" + pair + "D00X").controls
    )
    return _block(
        _table(
            ("Control", "Plain bytes", "M-name bytes", "Press", "Release"),
            (
                (
                    c.key.replace("_", " "),
                    _hex(codec.letter_command(c.letter)),
                    _hex(codec.letter_command(c.letter, wrapped=True)),
                    "Periodic"
                    if c.held
                    else "Completed tap"
                    if c.key == "light_toggle"
                    else "Once on press",
                    c.release,
                )
                for c in controls
            ),
        )
    )


def l2motion_auxiliary() -> str:
    from custom_components.adjustable_bed.beds.bedgear.music import MODES, Music
    from custom_components.adjustable_bed.profiles.l2motion import L2MotionProfile

    p = L2MotionProfile("HHC0000015DE0X")
    return _block(
        _table(
            ("Setting", "Value or frame"),
            (
                ("First periodic tick and interval", f"{p.refresh_ms} ms"),
                ("Motor release", f"{p.stop_count} writes, {p.stop_interval_ms} ms apart"),
                ("Short normal-UP filler", f"{p.fallback_count} writes, {p.refresh_ms} ms apart"),
                (
                    "Red / green / blue at full scale",
                    "; ".join(_hex(codec.ascii_command(c, 120)) for c in (315, 316, 317)),
                ),
                ("Light timer, 10 minutes", _hex(codec.ascii_command(319, 10))),
                (
                    "Synchronization on / off",
                    "; ".join(_hex(codec.ascii_command(c)) for c in (12, 15)),
                ),
                (
                    "Wireless / wired synchronization",
                    "; ".join(_hex(codec.ascii_command(33049, v)) for v in (0, 1)),
                ),
                (
                    "Alarm 06:30, strengths off / 1 / 2",
                    "; ".join(
                        _hex(codec.decimal_fields("063000", v)) for v in ("0017", "0118", "0219")
                    ),
                ),
                *(
                    (f"Initial {mode} sound, volume 11", _hex(Music().aggregate(mode)))
                    for mode in MODES
                ),
            ),
        )
    )


BLOCKS.extend(
    [
        (GUIDE, "l2motion-layouts", l2motion_layouts),
        (GUIDE, "l2motion-controls", l2motion_controls),
        (GUIDE, "l2motion-auxiliary", l2motion_auxiliary),
    ]
)


def moodbase_layouts() -> str:
    from custom_components.adjustable_bed.profiles.moodbase import LAYOUT_EXAMPLES, MoodBaseProfile

    return _block(_table(
        ("Name selector", "Layout", "Axes and letter pairs", "Memory slots", "Presets"),
        (
            (
                pair + (" / H" if marker == "H" else ""),
                p.panel,
                ", ".join(f"{axis} ({up}/{down})" for axis, up, down in p.axes),
                str(p.memory_slots),
                ", ".join(key.replace("_", " ") for key, _ in p.presets),
            )
            for pair in LAYOUT_EXAMPLES
            for marker in (("X", "H") if pair in ("15", "35", "45", "85", "C1") else ("X",))
            for p in (MoodBaseProfile(f"HHC00000{pair}D00{marker}"),)
        ),
    ))


def moodbase_controls() -> str:
    from custom_components.adjustable_bed.profiles.moodbase import (
        LAYOUT_EXAMPLES,
        SAVE_SNORE,
        MoodBaseProfile,
    )

    controls = dict.fromkeys(
        (c.key, c.letter, c.held, c.release)
        for pair in LAYOUT_EXAMPLES
        for flag in ("X", "H")
        for c in MoodBaseProfile(f"HHC00000{pair}D00{flag}").controls
    )
    controls.update(dict.fromkeys((
        ("save memory 1", "Z", False, "none"),
        ("save memory 2", "a", False, "none"),
        ("save anti-snore position", SAVE_SNORE, False, "none"),
        ("motion stop", "b", False, "five writes"),
        ("status query", "z", False, "never sent on M"),
    )))
    return _block(_table(
        ("Control", "Plain bytes", "M-name bytes", "Gesture", "Release"),
        (
            (
                key.replace("_", " "),
                _hex(codec.letter_command(letter)),
                _hex(wrapped) if (wrapped := codec.short_transport(f"${letter}", wrapped=True)) else "suppressed",
                "Periodic" if held else "Completed tap" if key == "light_toggle" else "Direct",
                release,
            )
            for key, letter, held, release in controls
        ),
    ))


def moodbase_auxiliary() -> str:
    from custom_components.adjustable_bed.profiles.moodbase import (
        CARRIER_SERVICE_UUID,
        CHARACTERISTIC_UUID,
        COLOR_COMMANDS,
        COLOR_INTERVAL_MS,
        SETTINGS_DELAY_MS,
        SYNC_DISABLE,
        SYNC_ENABLE,
        SYNC_MODE_COMMAND,
        TIMER_COMMAND,
        TIMER_DEFAULT_MINUTES,
        TIMER_MAX_MINUTES,
        VIBRATION_MAX,
        MoodBaseProfile,
        lighting_frame,
    )

    p = MoodBaseProfile("HHC0000001DM0X")
    rows = [
        ("Service and write/notify channel", f"`{CARRIER_SERVICE_UUID}` / `{CHARACTERISTIC_UUID}`", "Case-insensitive identifier substrings; write without response"),
        ("Held controls", f"First tick at {p.refresh_ms} ms; repeat every {p.refresh_ms} ms", f"STOP, where used, sends {p.stop_count} writes {p.stop_interval_ms} ms apart"),
        ("Short release fallback", f"{p.fallback_count} extra frames {p.refresh_ms} ms apart", "Only after a completed release with fewer than five ticks and no release callback"),
    ]
    for index, (channel, command) in enumerate(zip(("Red", "Green", "Blue"), COLOR_COMMANDS, strict=True)):
        rows.append((channel, _hex(lighting_frame(command, 120)), f"Maximum channel value at +{index * COLOR_INTERVAL_MS} ms nominally"))
    rows.extend((
        ("Light timer on", _hex(lighting_frame(TIMER_COMMAND, TIMER_DEFAULT_MINUTES)), f"Set {TIMER_DEFAULT_MINUTES} minutes, after {SETTINGS_DELAY_MS} ms"),
        ("Light timer off", _hex(lighting_frame(TIMER_COMMAND, 0)), f"Set zero, after {SETTINGS_DELAY_MS} ms"),
        ("Light timer maximum", _hex(lighting_frame(TIMER_COMMAND, TIMER_MAX_MINUTES)), f"Minutes from 0 to {TIMER_MAX_MINUTES}"),
        ("Alarm off", _hex(codec.decimal_fields("073000", "0017")), f"07:30 example, {SETTINGS_DELAY_MS} ms after query"),
        ("Alarm strength 1", _hex(codec.decimal_fields("073000", "0118")), f"07:30 example, {SETTINGS_DELAY_MS} ms after query"),
        ("Alarm strength 2", _hex(codec.decimal_fields("064500", "0219")), f"06:45 example, {SETTINGS_DELAY_MS} ms after query"),
        ("Synchronize bases", _hex(codec.ascii_command(SYNC_ENABLE)), "Available when the bed reports bound and unsynchronized"),
        ("Stop synchronization", _hex(codec.ascii_command(SYNC_DISABLE)), "Available when the bed reports bound and synchronized"),
        ("Wireless mode", _hex(codec.ascii_command(SYNC_MODE_COMMAND, 0)), "Sync settings when unbound"),
        ("Wired mode", _hex(codec.ascii_command(SYNC_MODE_COMMAND, 1)), "Sync settings when unbound"),
        ("Vibration", _hex(codec.music_command("V", VIBRATION_MAX)), f"Level 0–{VIBRATION_MAX}; M names add the shared envelope"),
    ))
    return _block(_table(("Behavior", "Value or example bytes", "Notes"), rows))


BLOCKS.extend([
    (GUIDE, "moodbase-layouts", moodbase_layouts),
    (GUIDE, "moodbase-controls", moodbase_controls),
    (GUIDE, "moodbase-auxiliary", moodbase_auxiliary),
])


def ergobed_layouts() -> str:
    from custom_components.adjustable_bed.profiles.ergobed import LAYOUT_EXAMPLES, ErgoBedProfile

    layouts = {}
    for selector in LAYOUT_EXAMPLES:
        profile = ErgoBedProfile(f"HHC00000{selector}DE00")
        layout = (
            profile.panel,
            ", ".join(f"{axis} ({up}/{down})" for axis, up, down in profile.axes),
            ", ".join(key.replace("_", " ") for key, _ in profile.presets),
            str(profile.memory_slots),
        )
        layouts.setdefault(layout, []).append(selector)
    return _block(
        _table(
            ("Selector examples", "Panel", "Motor controls", "Presets", "Memory slots"),
            ((", ".join(selectors), *layout) for layout, selectors in layouts.items()),
        )
    )


def ergobed_controls() -> str:
    from custom_components.adjustable_bed.profiles.ergobed import LAYOUT_EXAMPLES, ErgoBedProfile

    controls = dict.fromkeys(
        control
        for selector in LAYOUT_EXAMPLES
        for control in ErgoBedProfile(f"HHC00000{selector}DE00").controls
    )
    rows = [
        (
            control.key.replace("_", " "),
            _hex(codec.letter_command(control.letter)),
            f"First tick, then every {ErgoBedProfile.refresh_ms} ms" if control.held else "Once",
        )
        for control in controls
    ]
    rows.extend(
        (f"Save memory {slot}", _hex(codec.letter_command(letter)), "Once")
        for slot, letter in enumerate("Za", 1)
    )
    return _block(_table(("Control", "Bytes", "Writes"), rows))


def ergobed_settings() -> str:
    from datetime import datetime

    from custom_components.adjustable_bed.profiles.ergobed import (
        CHARACTERISTIC_MARKER,
        COLOR_COMMANDS,
        SERVICE_MARKER,
        SETTINGS_INTERVAL_MS,
        STARTUP_DELAY_MS,
        TIMER_MAX_SECONDS,
        alarm_frame,
        clock_frame,
        color_frame,
        timer_frame,
    )

    rows = [
        ("Transport", f"`{SERVICE_MARKER.upper()}` / `{CHARACTERISTIC_MARKER.upper()}`", "Service / shared write and notify characteristic, matched by UUID substring"),
        ("Status query", _hex(codec.TIMER_PREFIX), f"Before each settings write and at {STARTUP_DELAY_MS} ms after discovery on alarm layouts"),
        ("Local clock", _hex(clock_frame(datetime(2026, 1, 1, 9, 7, 5))), "09:07:05 example, immediately after the startup query"),
    ]
    rows.extend(
        (channel, _hex(color_frame(command, value)), f"{value}/255, at +{(index * 2 + 1) * SETTINGS_INTERVAL_MS} ms")
        for index, (channel, command, value) in enumerate(
            zip(("Red", "Green", "Blue"), COLOR_COMMANDS, (255, 128, 0), strict=True)
        )
    )
    rows.append(("Light timer", _hex(timer_frame(120)), f"120 s example. Range 0–{TIMER_MAX_SECONDS} s, {SETTINGS_INTERVAL_MS} ms after query"))
    rows.extend(
        (label, _hex(alarm_frame(hour, minute, strength)), f"{hour:02d}:{minute:02d} example, {SETTINGS_INTERVAL_MS} ms after query")
        for strength, (label, hour, minute) in enumerate(
            (("Alarm off", 7, 30), ("Alarm strength 1", 12, 34), ("Alarm strength 2", 23, 45))
        )
    )
    return _block(_table(("Setting", "Value or example bytes", "Schedule"), rows))


BLOCKS.extend([
    (GUIDE, "ergobed-layouts", ergobed_layouts),
    (GUIDE, "ergobed-controls", ergobed_controls),
    (GUIDE, "ergobed-settings", ergobed_settings),
])
