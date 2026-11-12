"""Generated values for the accepted Smart Sleep bed surface."""

from custom_components.adjustable_bed.codec import smart_sleep as codec
from custom_components.adjustable_bed.profiles import smart_sleep as app

from ._common import Block, _block, _hex, _table

GUIDE = "docs/beds/smart-sleep.md"


def bed_types() -> dict[str, tuple[str, ...]]:
    return dict.fromkeys(app.PROFILES, ("smart_sleep",))


def profiles() -> str:
    return _block(
        _table(
            ("Profile", "Refresh / massage / release / query (ms)", "Startup", "SAVE hold (ms)"),
            (
                (
                    key,
                    f"{p.refresh_ms} / {p.massage_ms} / {p.release_ms} / {p.query_ms}",
                    "Subscribe, "
                    + ("opaque initialization, " if key == "p2" else "")
                    + "settings, massage, alarm queries",
                    str(p.save_ms) if key == "p2" else "No proven SAVE",
                )
                for key, p in app.PROFILES.items()
            ),
        )
    )


def transports() -> str:
    return _block(
        _table(
            ("Role", "Service", "Characteristic", "Mode"),
            (
                ("Bed writes", codec.SERVICE, codec.WRITE, "With response"),
                ("Bed notifications", codec.SERVICE, codec.NOTIFY, "Notify"),
                ("Device name", "1800", codec.NAME, "Read"),
                ("Firmware", "180A", codec.FIRMWARE, "Read"),
                ("Protocol string", "180A", codec.PROTOCOL, "Read"),
            ),
        )
    )


def commands() -> str:
    return _block(
        _table(
            ("Profile", "Action", "Frame"),
            (
                (key, action, _hex(frame))
                for key, p in app.PROFILES.items()
                for action, frame in p.frames.items()
            ),
        )
    )


def models() -> str:
    return _block(
        _table(
            ("Numeric model", "App label", "Bed gate"),
            (
                (
                    str(model),
                    label,
                    "AI-zero preset group"
                    if model == 8
                    else "Legacy flexible wake"
                    if model == 67
                    else "Shared controls",
                )
                for model, label in app.MODELS.items()
            ),
        )
    )


def catalogs() -> str:
    return _block(
        _table(
            ("P2 catalog", "Index", "Opcode", "Frame"),
            (
                (kind, str(index), str(first + index - 1), _hex(codec.massage("p2", kind, index)))
                for kind, (first, count) in codec.CATALOGS.items()
                if kind != "alarm"
                for index in range(1, count + 1)
            ),
        )
    )


def settings() -> str:
    rows = [
        ("Privacy on", codec.privacy(True)),
        ("Privacy off", codec.privacy(False)),
        ("Antisnore demo", codec.antisnore(True, 6, demo=True)),
        ("Antisnore off", codec.antisnore(False, 0)),
    ]
    rows += [(f"Antisnore {v}", codec.antisnore(True, v)) for v in (1, 3, 6)]
    rows += [(f"Sensitivity {v}", codec.sensitivity(v)) for v in (1, 2, 3)]
    rows += [
        (f"{key} light {enabled}", codec.light(app.PROFILES[key].key, enabled))
        for key in app.PROFILES
        for enabled in (False, True)
    ]
    rows += [
        (f"{key} massage {action}", codec.massage(app.PROFILES[key].key, action))
        for key in app.PROFILES
        for action in ("massage_all", "massage_off")
    ]
    rows += [
        (f"p1 {action}", codec.massage("p1", action))
        for action in ("wave", "timer", "head_strength", "foot_strength")
    ]
    rows += [("p1 AI-zero", codec.preset("p1", "ai_zero"))]
    return _block(_table(("Action", "Frame"), ((name, _hex(frame)) for name, frame in rows)))


def alarms() -> str:
    return _block(
        _table(
            ("Format", "Action", "Value"),
            (
                (fmt, name, str(value))
                for fmt, catalog in (
                    ("p1", app.LEGACY_ALARM_ACTIONS),
                    ("p2", app.ALARM_ACTIONS),
                    ("p2 visible label", app.APP_ALARM_LABELS),
                )
                for name, value in catalog.items()
            ),
        )
    )


BLOCKS: list[Block] = [
    (GUIDE, f"smart-sleep-{name}", fn)
    for name, fn in (
        ("profiles", profiles),
        ("transports", transports),
        ("commands", commands),
        ("models", models),
        ("catalogs", catalogs),
        ("settings", settings),
        ("alarms", alarms),
    )
]
