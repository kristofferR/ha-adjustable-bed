"""Generated Maxprime command examples and layout gates."""

from collections import defaultdict

from custom_components.adjustable_bed.beds.richmat_classic import protocol as p
from custom_components.adjustable_bed.beds.richmat_classic.caller import Selection
from custom_components.adjustable_bed.beds.richmat_classic.maxprime_commands import (
    ALARM_COMBINATIONS,
    gesture,
)
from custom_components.adjustable_bed.beds.richmat_classic.profiles import load_catalog
from custom_components.adjustable_bed.codec import richmat
from custom_components.adjustable_bed.profiles import maxprime

from ._common import _block, _hex, _table


def render_maxprime() -> str:
    catalog = load_catalog(maxprime.APP)
    modes = defaultdict(list)
    for layout, model in catalog.models.items():
        if len(model.modes) > 1:
            modes[model.modes].append(layout)
    examples = []
    for layout, resource, long in (
        ("6BRM", "k_motor1_up", False),
        ("DXRM", "k_sync_on", True),
        ("AORM", "k_lock", True),
        ("YRRM", "k_tv_return", False),
        ("E3RM", "k_m1_return", False),
        ("E3RM", "k_m1_set", True),
    ):
        frames = []
        for wire in ("RAW", "FRAMED"):
            matches = [
                candidate
                for button in catalog.models[layout].controls
                if (candidate := gesture(button, layout, wire, Selection(), long=long)) is not None
                and candidate.resource == resource
            ]
            # The first 6BRM direction uses the old resource on raw transport.
            if not matches and layout == "6BRM":
                matches = [
                    gesture(
                        catalog.models[layout].controls[0], layout, wire, Selection(), long=False
                    )
                ]
            action = matches[0]
            assert action is not None
            frames.append(_hex(p.control(action.payload, wire)))
        examples.append((layout, action.label, *frames))

    return _block(
        _table(("Layout", "Control", "Raw", "Wrapped, mode 0"), examples),
        _table(
            ("Available mode bytes", "Layouts"),
            [
                (", ".join(str(mode) for mode in values), ", ".join(layouts))
                for values, layouts in sorted(modes.items())
            ],
        ),
        _table(
            ("Feature", "Example frame or write sequence"),
            [
                (
                    "Release, raw / wrapped mode 0",
                    f"{_hex(p.release('RAW'))} / {_hex(p.release('FRAMED'))}",
                ),
                ("Wrapped startup", _hex(p.INITIALIZE)),
                (
                    "Alarm / light / aroma probes",
                    " / ".join(map(_hex, (p.ALARM_QUERY, p.LAMP_QUERY, p.AROMA_QUERY))),
                ),
                (
                    "Alarm countdown, 1440 minutes to zero gravity",
                    " then ".join(map(_hex, p.alarm(1440, 0x45))),
                ),
                ("Cancel alarm", " then ".join(map(_hex, p.alarm(0, 0)))),
                ("RGB 18, 52, 86", _hex(richmat.rgb(18, 52, 86))),
                ("Light duration, 300 s", _hex(richmat.light_timer(1, 44))),
                (
                    "Aroma 60 min / 2 min / 12 h",
                    " then ".join(
                        _hex(p.aroma(op, value))
                        for op, value in ((0x1B, 60), (0x1C, 2), (0x1D, 12))
                    ),
                ),
                (
                    "Massage slider position 0, D1RM / D9RM",
                    f"{_hex(p.massage_timer('D1RM', 0))} / {_hex(p.massage_timer('D9RM', 0))}",
                ),
                (
                    "Y6RM 10 / 20 / 30 minutes",
                    " / ".join(_hex(p.massage_popup(value)) for value in ("15", "30", "45")),
                ),
            ],
        ),
        _table(
            ("Alarm position", "Both zones", "Head", "Feet"),
            [
                (
                    p.ALARM_WAKE_ACTIONS[action].replace("_", " "),
                    *(f"`{opcode:02x}`" for opcode in codes),
                )
                for action, codes in ALARM_COMBINATIONS.items()
            ],
        ),
    )
