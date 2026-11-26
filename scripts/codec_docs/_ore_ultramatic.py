"""Generated tables for the ORE apps that select E5 or E6 on connection."""

from datetime import datetime

from custom_components.adjustable_bed.beds import ore_comfort_bed as ore
from custom_components.adjustable_bed.codec import keeson
from custom_components.adjustable_bed.profiles import keeson as profiles
from custom_components.adjustable_bed.profiles import leva_sleep
from custom_components.adjustable_bed.profiles import ore_ultramatic as app
from scripts.codec_docs._common import _block, _hex, _table


def render(*, leva: bool = False) -> str:
    profile_for = leva_sleep.profile if leva else app.profile
    p2_presets = leva_sleep.P2_PRESETS if leva else app.P2_PRESETS
    alarm = leva_sleep.alarm if leva else app.alarm

    def frame(route, word):
        return _hex(profiles.encode(profile_for(route), word))

    rows = []
    for route in ("P1", "P2"):
        for count, axes in ore.LAYOUTS.items():
            for key, _name, up, down in axes:
                if route == "P2" and key == "both":
                    up, down = 5, 10
                rows.append((route, str(count), key, frame(route, up), frame(route, down)))
    controls = []
    for route in ("P1", "P2"):
        for name, word in (app.P1_RECALL if route == "P1" else p2_presets).items():
            controls.append(
                (
                    route,
                    name,
                    frame(route, word),
                    frame(route, app.P1_SAVE[name]) if route == "P1" else "none",
                )
            )
    other = [
        ("P1", f"{zone} level {q}", frame("P1", base + q))
        for zone, base in ore.MASSAGE_BASE.items()
        for q in range(4)
    ]
    other += [
        ("P1", f"timer {minute} min", frame("P1", word))
        for minute, word in ore.MASSAGE_TIMER.items()
    ]
    other += [
        ("P1", "light on", frame("P1", ore.LIGHT_ON)),
        ("P1", "light off", frame("P1", ore.LIGHT_OFF)),
        ("P2", "light toggle", frame("P2", app.LIGHT_TOGGLE)),
    ]
    other += [
        ("P2", f"held massage {name}", frame("P2", word)) for name, word in app.P2_MASSAGE.items()
    ]
    other += [(route, "release / STOP", frame(route, 0)) for route in ("P1", "P2")]
    other += [
        (
            "P1",
            "massage start (saved wave/head/foot, default1)",
            "; ".join(frame("P1", ore.MASSAGE_BASE[zone] + 1) for zone in ("wave", "head", "foot")),
        ),
        (
            "P1",
            "massage stop",
            "; ".join(frame("P1", ore.MASSAGE_BASE[zone]) for zone in ("head", "foot")),
        ),
    ]
    now = datetime(2026, 11, 17, 7, 6, 5)
    alarms = [(route, "query", _hex(app.query(route, now))) for route in ("P1", "P2")]
    alarms += [("P2", "clock", _hex(keeson.clock(now)))]
    for route in ("P1", "P2"):
        for enabled, kind in ((False, 0), *((True, k) for k in range(4))):
            alarms.append(
                (
                    route,
                    f"{'enable type' + str(kind) if enabled else 'disable'}",
                    _hex(
                        alarm(
                            route, now, enabled=enabled, hour=7, minute=30, repeat=130, kind=kind
                        )
                    ),
                )
            )
    return _block(
        _table(
            ("Selector", "Write", "Notify"),
            ((app.SELECTOR + " present: P1, absent: P2", app.WRITE, app.NOTIFY),),
        ),
        _table(("Route", "Layout motors", "Axis", "Up", "Down"), rows),
        _table(("Route", "Preset", "Recall", "Program"), controls),
        _table(("Route", "Control", "Frame / sequence"), other),
        "Alarm examples use local2026-11-17 07:06:05, alarm07:30, repeat130.",
        _table(("Route", "Alarm control", "Frame"), alarms),
        _table(
            ("Lifecycle", "Timing"),
            (
                ("Held refresh", f"immediate, then{app.REFRESH_MS}ms after each write"),
                ("Single, release and clock", f"{app.SINGLE_MS}ms before each write"),
                ("Query", f"{app.QUERY_MS}ms before write"),
                ("Startup", "subscribe only, no initialization/query/control write"),
            ),
        ),
    )


BLOCKS = [
    ("docs/beds/keeson.md", "keeson-ore-ultramatic", render),
    ("docs/beds/keeson.md", "keeson-leva-sleep", lambda: render(leva=True)),
]
