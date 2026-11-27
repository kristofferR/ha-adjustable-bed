"""PowersBedding's tables from its app profile and the shared encoders."""

from datetime import datetime

from custom_components.adjustable_bed.profiles import powersbedding as app
from scripts.codec_docs._common import _hex, _table


def render() -> str:
    rows = []
    now = datetime(2026, 11, 27, 6, 45, 30)
    for route, profile in app.PROFILES.items():
        words = {
            f"{axis} {direction}": values[i]
            for axis, values in app.AXES.items()
            for i, direction in enumerate(("up", "down"))
        }
        for name, word in words.items():
            rows.append((route, name, _hex(app.normal(route, word)), "held, 100 ms"))
        rows.append((route, "driver STOP", _hex(app.normal(route, 0)), "twice, 100 ms apart"))
        for name, word in profile.presets.items():
            rows.append((route, name, _hex(app.normal(route, word)), "once"))
        for slot, word in profile.memory.items():
            rows.append((route, f"memory {slot}", _hex(app.normal(route, word)), "once"))
            save = {1: 0x20000008, 2: 0x20000009}[slot] if route == "p1" else word
            rows.append(
                (
                    route,
                    f"save memory {slot}",
                    _hex(app.normal(route, save)),
                    "6 s hold, 5 s refresh" if route == "p1" else "6 s hold, 100 ms refresh",
                )
            )
        rows.append(
            (
                route,
                "save zero gravity",
                _hex(app.normal(route, 0x20000001 if route == "p1" else app.PRESETS["zero_g"])),
                "6 s, no release packet",
            )
        )
        if route == "p1":
            for zone, word in app.LEVELS.items():
                for level in range(4):
                    rows.append(
                        (
                            route,
                            f"{zone} massage {level}",
                            _hex(app.normal(route, word + level)),
                            "once",
                        )
                    )
            for level in (-1, 0, 1, 2):
                rows.append(
                    (
                        route,
                        f"timer argument {level}",
                        _hex(app.normal(route, 0x10000030 + level)),
                        "once",
                    )
                )
            for enabled in (False, True):
                rows.append(
                    (
                        route,
                        f"light {'on' if enabled else 'off'}",
                        _hex(app.normal(route, 0x31000000 + enabled)),
                        "once",
                    )
                )
            rows.append(
                (
                    route,
                    "stop preset",
                    _hex(app.normal(route, 0x01000000)),
                    "same-preset second tap",
                )
            )
        else:
            for action, word in app.STEPS.items():
                rows.append(
                    (
                        route,
                        f"massage {action}",
                        _hex(app.normal(route, word)),
                        "once; P3 query after 150 ms",
                    )
                )
            rows.append((route, "light toggle", _hex(app.normal(route, 0x20000)), "once"))
            rows.append((route, "read alarm", _hex(app.alarm_query(route) or b""), "once"))
        rows.append(
            (route, "clock example", _hex(app.clock(route, now)), "local 2026-11-27 06:45:30")
        )
        rows.append(
            (
                route,
                "alarm example",
                _hex(
                    app.alarm_fields(
                        route, 7, 30, -66, 17, {"p1": 8, "p2": 17, "p3": 5}[route], now
                    )
                ),
                "weekdays, memory A",
            )
        )
        rows.append(
            (
                route,
                "cancel alarm example",
                _hex(app.cancel(route, now)),
                "twice, then clock at 100 ms",
            )
        )
    return "\n".join(_table(("Route", "Control", "Frame", "Timing"), rows))


BLOCKS = [("docs/beds/keeson.md", "keeson-powersbedding", render)]
