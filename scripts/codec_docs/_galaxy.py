"""Galaxy's exact Richmat catalog data, rendered without hand-copied frames."""

from custom_components.adjustable_bed.beds.galaxy.catalog import (
    ACTIONS,
    CATALOG,
    PRODUCTS,
    RUNTIMES,
)
from custom_components.adjustable_bed.beds.goodvibe import protocol as p
from custom_components.adjustable_bed.codec import richmat as codec
from scripts.codec_docs._common import _block, _hex, _table

GUIDE = "docs/beds/richmat.md"


def products() -> str:
    return _block(
        _table(
            (
                "Product / configuration",
                "Controls / alarms",
                "Sides",
                "Light / repeat / snore",
                "Remote picker",
            ),
            (
                (
                    f"`{key}`",
                    f"{len(product.actions)} / {len(product.alarms)}",
                    ", ".join(map(str, product.sides)),
                    " / ".join(
                        "yes" if flag else "no"
                        for flag in (product.light, product.repeat_alarm, RUNTIMES[key].snore)
                    ),
                    ", ".join(RUNTIMES[key].remote_targets) or "none",
                )
                for key, product in PRODUCTS.items()
            ),
        )
    )


def commands() -> str:
    return _block(
        _table(
            (
                "Action ID",
                "App label / gesture",
                "Framed short / long (Left)",
                "Nordic short / long",
            ),
            (
                (
                    key,
                    f"{action.label} / {action.gesture}" + (" (local)" if action.local else ""),
                    " / ".join(
                        _hex(p.action_frame(action, 0, False, long)) for long in (False, True)
                    )
                    if not action.local
                    else "no BLE",
                    " / ".join(
                        _hex(p.action_frame(action, 0, True, long)) for long in (False, True)
                    )
                    if not action.local
                    else "no BLE",
                )
                for key, action in ACTIONS.items()
            ),
        )
    )


def settings() -> str:
    frames = {
        **p.queries(codec.record),
        "snore on": p.snore_switch(True, build=codec.record),
        "snore count 3": p.snore_config(True, 3, build=codec.record),
        "snore time 15": p.snore_config(False, 15, build=codec.record),
        "repeat slot 1, 07:30, mode 2, Mon/Sun enabled": p.repeat_alarm(
            1, 7, 30, 2, 131, build=codec.record
        ),
        "delete slot 3": p.delete_alarm(3, build=codec.record),
        "light 300 seconds": p.light_duration(300),
        "red": codec.rgb(255, 0, 0),
    }
    for model, codes in CATALOG.timer_codes.items():
        for minutes, code in codes.items():
            frames[f"{model} massage countdown {minutes} min"] = codec.function(code)
    return _block(
        _table(
            ("Setting / query", "Write"), ((name, _hex(frame)) for name, frame in frames.items())
        )
    )


def startup() -> str:
    return _block(
        "Subscribe before initialization. Queue the applicable local time and sleep-name records, then check clock and light on the 300 ms menu schedule. "
        "Sync the two local time records only for a product with an alarm list; "
        "query the sleep advertisement name only for the nine BLE-enabled bed products. "
        "The catalog keeps each copied configuration’s own gates.",
        _table(
            ("Step", "Framed / Nordic"),
            (
                (
                    "Check clock",
                    _hex(codec.function(1, action="deviceFunctionItemCheckClock"))
                    + " / "
                    + _hex(codec.function(1, single=True)),
                ),
                (
                    "Check light",
                    _hex(codec.function(1, action="deviceFunctionItemCheckLight"))
                    + " / "
                    + _hex(codec.function(1, single=True)),
                ),
            ),
        ),
    )


BLOCKS = [
    (GUIDE, "galaxy-products", products),
    (GUIDE, "galaxy-commands", commands),
    (GUIDE, "galaxy-settings", settings),
    (GUIDE, "galaxy-startup", startup),
]
