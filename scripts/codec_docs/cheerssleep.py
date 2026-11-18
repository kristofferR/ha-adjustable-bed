"""CheersSleep tables generated from shipped catalog, codec and timing data."""

from custom_components.adjustable_bed.codec import cheerssleep as codec
from custom_components.adjustable_bed.profiles import cheerssleep as app

from ._common import Block, _block, _hex, _table

GUIDE = "docs/beds/cheerssleep.md"


def models() -> str:
    return _block(
        _table(
            ("Key", "Model", "Page", "Format", "Axes", "Features"),
            (
                (
                    str(m.key),
                    m.label,
                    m.page,
                    m.format.upper(),
                    ", ".join(m.axes),
                    ", ".join(
                        name
                        for name, enabled in (
                            ("2 memories", m.memory),
                            ("ZZ/TV/ZG", m.presets),
                            ("light", m.light),
                            ("vibration", m.massage),
                            ("split sides", m.split),
                            ("sonic I/HI", m.sonic),
                            ("sonic AS", m.as_layout),
                            ("RGB", m.rgb),
                        )
                        if enabled
                    ),
                )
                for m in app.MODELS.values()
            ),
        )
    )


def transports() -> str:
    return _block(
        _table(
            ("Role", "Service", "Characteristic"),
            (
                ("Write", f"`{codec.SERVICE}`", f"`{codec.WRITE}`"),
                ("Notify", f"`{codec.SERVICE}`", f"`{codec.NOTIFY}`"),
            ),
        )
    )


def movement() -> str:
    rows = []
    for side, mapping in ((0, app.P1_AXES), *app.P1_SPLIT.items()):
        for axis, values in mapping.items():
            rows.append(("P1", str(side), axis, *(_hex(codec.p1(2, 1, v)) for v in values)))
    for axis, values in {
        **app.P2_AXES,
        "all2": (5, 10),
        "all3": (21, 42),
        "400I neck": (64, 128),
        "600I neck": (1024, 2048),
    }.items():
        rows.append(
            (
                "P2",
                "0 (or selected side)",
                axis,
                *(_hex(codec.normal(v)) for v in values),
                _hex(codec.normal(0)),
            )
        )
    return _block(_table(("Format", "Side", "Axis", "Up", "Down", "Release"), rows))


def controls() -> str:
    rows = []
    for name, (legacy, modern) in app.PRESETS.items():
        rows.append((name, _hex(codec.p1(2, 1, legacy)), _hex(codec.normal(modern))))
    rows.extend(
        (
            ("flat", _hex(codec.p1(2, 1, 0x111)), _hex(codec.normal(0x08000000))),
            ("second preset tap", _hex(codec.p1(2, 1, 1)), _hex(codec.normal(0x40000000))),
            ("memory1 recall", _hex(codec.p1(2, 1, 0x311)), _hex(codec.normal(0x10000))),
            ("memory2 recall", _hex(codec.p1(2, 1, 0x313)), _hex(codec.normal(0x40000))),
            ("memory1 save", _hex(codec.p1(2, 1, 0x310)), _hex(codec.setting(6, 5))),
            ("memory2 save", _hex(codec.p1(2, 1, 0x312)), _hex(codec.setting(6, 6))),
            ("light off / toggle", _hex(codec.p1(2, 1, 0x500)), _hex(codec.normal(0x20000))),
            ("light on", _hex(codec.p1(2, 1, 0x501)), "Toggle only"),
        )
    )
    for name, word in app.SONIC.items():
        rows.append((name, "Unavailable", _hex(codec.normal(word))))
    return _block(_table(("Action", "P1 serial2", "P2 side0"), rows))


def profiles() -> str:
    return _block(
        _table(
            ("Format", "Movement", "Release", "Tap burst", "Startup"),
            (
                (
                    "P1",
                    "One frame; the hold is latched for up to 10 s",
                    "STOP for the same motor 120 ms after release",
                    "One write",
                    "Pages Two and Two1: up to 20 address queries, each after a 120 ms wait",
                ),
                (
                    "P2",
                    "Repeats every 100 ms while held, within the hold limit",
                    "Zero key at once, for both sides",
                    "Command at 0, 100 and 200 ms; release at 300, 400, 500 and 500 ms; an interrupted tap keeps its counter",
                    "Simple pages send a B0 query; pages with navigation send a D0 query for side 0 when the parent page resumes or a destination opens",
                ),
            ),
        )
    )


BLOCKS: list[Block] = [
    (GUIDE, "cheerssleep-models", models),
    (GUIDE, "cheerssleep-transports", transports),
    (GUIDE, "cheerssleep-movement", movement),
    (GUIDE, "cheerssleep-controls", controls),
    (GUIDE, "cheerssleep-profiles", profiles),
]


def massage_and_settings() -> str:
    rows = []
    for selected, zones in app.P1_STEADY.items():
        for zone, commands in zones.items():
            rows.extend(
                (f"P1 side{selected} {zone} steady {level}", _hex(codec.p1(2, 1, command)))
                for level, command in enumerate(commands)
            )
    for selected, zones in app.P1_WAVE.items():
        for zone, commands in zones.items():
            rows.extend(
                (f"P1 side{selected} {zone} wave {level}", _hex(codec.p1(2, 1, command)))
                for level, command in enumerate(commands, 1)
            )
    for selected, commands in app.P1_WAVE_MODE.items():
        rows.extend(
            (f"P1 side{selected} wave mode{mode}", _hex(codec.p1(2, 1, command)))
            for mode, command in enumerate(commands)
        )
    for name, command in app.P2_MASSAGE.items():
        rows.append((f"P2 conventional {name}", _hex(codec.normal(command))))
    for side in (1, 2):
        for slot in (1, 2):
            rows.append(
                (
                    f"P1 side{side} memory{slot} recall",
                    _hex(codec.p1(2, 1, (0x6530 if side == 1 else 0x6538) + slot - 1)),
                )
            )
            rows.append(
                (
                    f"P1 side{side} memory{slot} save",
                    _hex(codec.p1(2, 1, (0x6540 if side == 1 else 0x6548) + slot - 1)),
                )
            )
        for name, (legacy, _) in app.PRESETS.items():
            rows.append(
                (
                    f"P1 side{side} {name}",
                    _hex(codec.p1(2, 1, (0x6511 if side == 1 else 0x6521) + legacy - 0x301)),
                )
            )
    for name, command in app.P1_SETTINGS.items():
        if name == "delay":
            rows.append(
                (
                    "P1 delay10..120 (example10, independent counter1)",
                    _hex(codec.p1(1, 3, command, 10)),
                )
            )
        else:
            rows.extend(
                (f"P1 {name} {value}", _hex(codec.p1(2, 3, command, value))) for value in (0, 1)
            )
    for speed, command in enumerate(app.YB_SPEEDS, 1):
        rows.extend(
            (f"P1 Yb speed{speed} timer{timer}", _hex(codec.p1(2, 1, command, timer)))
            for timer in app.YB_TIMERS
        )
    rows.extend(
        (
            (
                "P1 RGB preview112233/brightness44 (serial5)",
                _hex(codec.p1(5, 1, 0x501, codec.rgb_parameter(17, 34, 51, 68))),
            ),
            (
                "P1 RGB save112233/brightness44 (serial2)",
                _hex(codec.p1(2, 1, 0x50F, codec.rgb_parameter(17, 34, 51, 68))),
            ),
            ("P2 RGB112233, always side0", _hex(codec.setting(5, 17, 34, 51))),
            ("P2 brightness0..100, example100", _hex(codec.setting(10, 100))),
            ("P2 I/HI sonic0..100, example60", _hex(codec.setting(11, 3, 60))),
            ("P2 AS sonic decrease", _hex(codec.setting(11, 2, 0))),
            ("P2 AS sonic increase", _hex(codec.setting(11, 2, 1))),
            ("P2 AS sonic toggle", _hex(codec.setting(11, 2, 3))),
            ("P2 setting release", _hex(codec.setting(0xAA))),
            ("P1 sleep MAC query (current serial1)", _hex(codec.p1(1, 7, 0))),
            ("P2 B0 query", _hex(codec.query())),
            ("P2 shared D0 query", _hex(codec.query(True))),
        )
    )
    return _block(_table(("Action / parameter", "Frame"), rows))


BLOCKS.append((GUIDE, "cheerssleep-massage-settings", massage_and_settings))
