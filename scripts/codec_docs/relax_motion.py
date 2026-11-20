"""Relax Motion reference tables from the production model and command tables."""

from custom_components.adjustable_bed.codec import relax_motion as codec
from custom_components.adjustable_bed.profiles import relax_motion as app

from ._common import _block, _hex, _table

GUIDE = "docs/beds/relax-motion.md"


def models() -> str:
    return _block(
        _table(
            (
                "Model number",
                "App label",
                "Actuators",
                "Presets",
                "Massage",
                "Light",
                "Initial memories",
            ),
            (
                (
                    str(m.number),
                    m.label,
                    ", ".join(app.axes(m)),
                    str(m.presets),
                    ", ".join(
                        zone
                        for zone, supported in (("head", m.head_massage), ("foot", m.foot_massage))
                        if supported
                    )
                    or "none",
                    str(m.light),
                    str(m.initial_memory),
                )
                for m in app.RELAX.values()
            ),
        )
    )


def movement() -> str:
    rows = []
    for axis, command in app.P1_AXES.items():
        rows.append(
            ("P1", axis, _hex(codec.p1(1, 1, command, 10000)), _hex(codec.p1(1, 1, command)))
        )
    rows.append(
        ("P1", "combined actuator", _hex(codec.p1(1, 1, 0x110)), _hex(codec.p1(1, 1, 0x111)))
    )
    for axis, (up, down) in app.P2_AXES.items():
        rows.append(("P2", axis, _hex(codec.normal(up)), _hex(codec.normal(down))))
    return _block(_table(("Format", "Actuator", "Up (q=1)", "Down (q=1)"), rows))


def commands() -> str:
    rows = [("P1", name, _hex(codec.p1(1, 1, command))) for name, command in app.PRESETS.items()]
    rows += [
        ("P1", f"memory {slot} {kind}", _hex(codec.p1(1, 1, command)))
        for slot, pair in app.MEMORY.items()
        for kind, command in zip(("recall", "save"), pair, strict=True)
    ]
    rows += [
        ("P1", f"{zone} massage {level}", _hex(codec.p1(1, 1, command)))
        for zone, values in app.MASSAGE.items()
        for level, command in enumerate(values)
    ]
    rows += [
        ("P1 Chinese alternative only", f"rhythm {mode}", _hex(codec.p1(1, 1, command)))
        for mode, command in enumerate(app.RHYTHM)
    ]
    rows += [
        (
            "P1 Chinese alternative, rhythm active",
            f"{zone} strength {level}",
            _hex(codec.p1(1, 1, command)),
        )
        for zone, values in app.STRENGTH.items()
        for level, command in enumerate(values, 1)
    ]
    rows += [
        ("P1", f"editor {axis} STOP", _hex(codec.p1(1, 1, command)))
        for axis, command in app.EDITOR_STOPS.items()
    ]
    rows += [
        ("P1", "global STOP", _hex(codec.p1(1, 1, 1))),
        ("P1", "sleep-state query", _hex(codec.p1(1, 2, 0x1201))),
        ("P1", "brightness 128", _hex(codec.p1(1, 1, 0x501, 0xFFFFFF80))),
        ("P1", "light off", _hex(codec.p1(1, 1, 0x500))),
        (
            "P1",
            "sensed light: 6000 seconds",
            _hex(codec.p1(1, 3, app.SETTINGS["light_time"], 6000)),
        ),
        ("P1", "snore interval: 2 minutes", _hex(codec.p1(1, 3, app.SETTINGS["interval"], 120))),
        ("P1", "snore enabled", _hex(codec.p1(1, 3, app.SETTINGS["snore"], 1))),
        ("P1 alternative only", "comfort sleep on", _hex(codec.p1(1, 1, 0x601))),
        ("P2", "flat", _hex(codec.normal(0x08000000))),
        ("P2 model 500", "memory 1 recall", _hex(codec.normal(0x10000))),
        ("P2 model 500", "memory 1 save", _hex(codec.extra(6, 0x050000))),
        ("P2", "release", _hex(codec.P2_RELEASE)),
    ]
    return _block(_table(("Format / qualification", "Command", "Bytes (q=1)"), rows))


BLOCKS = [
    (GUIDE, "relax-motion-models", models),
    (GUIDE, "relax-motion-movement", movement),
    (GUIDE, "relax-motion-commands", commands),
]
