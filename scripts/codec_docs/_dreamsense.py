"""Dream Sense reference tables generated from the shipped product profiles."""

from collections import defaultdict

from custom_components.adjustable_bed.beds.dreamsense import protocol as p
from custom_components.adjustable_bed.beds.dreamsense.transport import ROUTES
from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles.dreamsense import (
    CHOICES,
    PROBE_MS,
    PROFILES,
    TICK_MS,
)
from scripts.codec_docs._common import _block, _hex, _table


def render() -> str:
    commands = defaultdict(list)
    for key, profile in PROFILES.items():
        for action in profile.controls:
            commands[(action.label, action.code, action.save, action.held, action.release)].append(
                key
            )
    return _block(
        "##### Products and setup labels",
        _table(
            ("Product choice", "Saved product", "Remote label", "Alarm", "Lighting", "Side choice"),
            (
                (
                    CHOICES[key],
                    f"`{key}`",
                    profile.remote or "none",
                    ("Existing repeat records" if profile.repeat else "Single alarm")
                    if profile.clock
                    else "none",
                    "Reply required" if profile.light else "none",
                    "Left / Right" if profile.side else "none",
                )
                for key, profile in PROFILES.items()
            ),
        ),
        "##### GATT routes",
        _table(
            ("Service", "Write", "Generic commands"),
            (
                (f"`{service}`", f"`{write}`", "Single byte" if single else "Side-scoped 6E frame")
                for service, write, single in ROUTES
            ),
        ),
        "The first writable matching endpoint and first notify-property characteristic are retained. "
        "The last recognized service selects the generic framing, in the device’s service order. "
        "Write requires the write property; write-without-response is used when also present. "
        "Special alarm, split, light and clock frames are sent unchanged on every route.",
        "##### Motor, preset, memory and massage commands",
        _table(
            ("Control", "Products", "Single byte", "Side 0", "Save", "Timing / release"),
            (
                (
                    name,
                    ", ".join(products),
                    _hex(codec.function(code, single=True)),
                    _hex(codec.function(code)),
                    _hex(codec.function(save)) if save is not None else "none",
                    (f"First tick {TICK_MS} ms, then every {TICK_MS} ms" if held else "Once")
                    + ("; STOP after delivery" if release else "; no STOP"),
                )
                for (name, code, save, held, release), products in commands.items()
            ),
        ),
        "Saves use a separate confirmed action and never a renewable hold. BJRN waits three seconds "
        "before its save write. Other save icons write once immediately. Fixed massage timers appear "
        "as the shared duration select. Intensity step controls do not imply absolute intensity levels.",
        "##### Startup and settings",
        _table(
            ("Operation", "Frame / behavior"),
            (
                (
                    "Initialize, once after subscription",
                    _hex(codec.function(0, action="deviceFunctionItemExitLimit"))
                    + " or single byte `00`",
                ),
                *(
                    (
                        name,
                        _hex(codec.function(1, action="deviceFunctionItem" + name))
                        + " or single byte `01`",
                    )
                    for name in ("CheckClock", "CheckLight", "CheckMusic")
                ),
                ("Split control", _hex(p.split_mode(0))),
                ("Standard control", _hex(p.split_mode(2))),
                ("Read split mode", _hex(p.split_query())),
                (
                    "Light duration: always on / 300 seconds",
                    _hex(p.light_seconds(0)) + " / " + _hex(p.light_seconds(300)),
                ),
                ("RGB example: red", _hex(codec.rgb(255, 0, 0))),
                ("Light off, side 0, no release", _hex(codec.function(0x75))),
                ("Vibration mode, side 0, no release", _hex(codec.function(0xD6))),
                ("Single alarm: cancel", " then ".join(_hex(f) for f in codec.countdown(0, 0))),
                ("List existing repeat alarms", _hex(p.alarm_list())),
                ("Update existing alarm 1 example", _hex(p.alarm_add(1, 1, 69, 7, 30))),
                ("Delete existing alarm 1 example", _hex(p.alarm_delete(1))),
            ),
        ),
        f"Clock, light and music capability probes run in that order at {PROBE_MS} ms intervals, "
        "without product or reply gates. Clock-enabled products also synchronize timezone and local "
        "calendar independently of the clock reply. Clock synchronization uses shared sync_clock. "
        "Alarms require a current clock reply and the selected product’s alarm choices. "
        "Lighting settings and light off require a current light reply and the product’s lighting flag. "
        "Vibration mode requires the product’s vibration page and a music-capability reply; no audio "
        "action is exposed. Green, Orange and Blue offer split/standard control independently of GATT framing.",
    )


BLOCKS = [("docs/beds/richmat.md", "dreamsense", render)]
