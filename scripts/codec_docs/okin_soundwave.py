"""Symphony Sleep Sense's app-owned tables, built through the proven codecs."""

from custom_components.adjustable_bed.codec import okin_nframe, okin_soundwave
from custom_components.adjustable_bed.profiles import symphony as app

from ._common import Block, _block, _hex, _table

GUIDE = "docs/beds/okin-soundwave.md"


def products() -> str:
    return _block(
        _table(
            ("Product", "ID", "Actuators", "Page", "Legacy massage", "Light"),
            (
                (
                    p.name,
                    str(p.value),
                    ", ".join(p.axes),
                    p.page,
                    p.massage or "None",
                    "Yes" if p.light else "No",
                )
                for p in app.PRODUCTS.values()
            ),
        )
    )


def selectors() -> str:
    return _block(
        _table(
            ("Selector", "App label", "Generic wire"),
            (
                (key, label, app.SymphonyProfile(app.PRODUCTS["0"], int(key)).wire)
                for key, label in app.SELECTORS.items()
            ),
        )
    )


def commands() -> str:
    rows = []
    for wire in ("P1", "P3"):
        for name, word in app.WORDS.items():
            if wire == "P1" and name in ("reading", "tv"):
                continue
            if wire == "P3" and name == "wave_previous":
                word = 0x80000
            rows.append((name, wire, _hex(app.encode_word(wire, word))))
    for name, index in app.P2_PRESETS.items():
        if name in ("reading", "tv"):
            continue
        rows.append((name, "P2", _hex(okin_soundwave.preset(index))))
        if name != "flat":
            rows.append(("save_" + name, "P2", _hex(okin_soundwave.preset(index + 32, save=True))))
    for domain, fields, label in (
        (3, (1,), "alarm"),
        (4, (), "light"),
        (6, (), "sonic massage"),
        (7, (), "anti-snore"),
        (5, (1, 255, 255, 0, 0, 34, 37, 18, 75), "confirmation"),
    ):
        rows.append(("query " + label, "P2", _hex(okin_soundwave.query(domain, fields))))
    for operation, label in ((12, "massage"), (5, "sonic")):
        for enabled in (False, True):
            rows.append(
                (
                    label + (" on" if enabled else " off"),
                    "P2",
                    _hex(okin_soundwave.record(6, operation, (0, int(enabled)))),
                )
            )
    rows.append(
        ("opaque bed diagnostic query", "P3", _hex(okin_nframe.parameter_record(0xB4, (1,))))
    )
    return _block(_table(("Action", "Wire", "Frame (selector zero)"), rows))


def modes() -> str:
    return _block(
        _table(
            ("Alarm page", "Admitted modes"),
            ((page, ", ".join(values)) for page, values in app.ALARM_CHOICES.items()),
        ),
        _table(
            ("Mode", "P1 code", "P3 code"),
            (
                (key, str(app.P1_MODES.get(key, 0)), str(value))
                for key, value in app.P3_MODES.items()
            ),
        ),
    )


BLOCKS: list[Block] = [
    (GUIDE, "symphony-products", products),
    (GUIDE, "symphony-selectors", selectors),
    (GUIDE, "symphony-commands", commands),
    (GUIDE, "symphony-alarm-modes", modes),
]
