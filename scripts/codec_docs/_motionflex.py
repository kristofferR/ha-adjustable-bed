"""MotionFlex tables from its product data and the shared Richmat codec."""

from custom_components.adjustable_bed.codec import richmat as codec
from custom_components.adjustable_bed.profiles.motionflex import (
    LIGHT_DELAY_S,
    MENU_DELAY_S,
    PRODUCTS,
    REFRESH_MS,
)

from ._common import Block, _block, _hex, _table


def render() -> str:
    rows = []
    for key, product in PRODUCTS.items():
        for action, code in (product.wire.codes or {}).items():
            release = (
                "refresh then STOP"
                if action.endswith(("_up", "_down"))
                else "once then STOP"
                if action == "flat" or action == "light_toggle" or action.startswith("massage_")
                else "once"
            )
            rows.append(
                (key.upper(), action, _hex(codec.command(code)), _hex(bytes((code,))), release)
            )
        for name, code in product.saves:
            rows.append(
                (
                    key.upper(),
                    "save_" + name,
                    _hex(codec.command(code)),
                    _hex(bytes((code,))),
                    "once, separate Save",
                )
            )
        for slot, (recall, save) in enumerate(product.wire.memory, 1):
            for action, code in (("recall", recall), ("save", save)):
                rows.append(
                    (
                        key.upper(),
                        f"{action}_memory_{slot}",
                        _hex(codec.command(code)),
                        _hex(bytes((code,))),
                        "once",
                    )
                )
    return _block(
        _table(("Model", "Action", "WiLinke", "Nordic", "Execution"), rows),
        _table(
            ("Operation", "Frames / timing"),
            (
                ("Motor refresh / outgoing queue", f"{REFRESH_MS} ms"),
                ("Menu query spacing", f"{MENU_DELAY_S:g} s"),
                ("Light timer change delay", f"{LIGHT_DELAY_S:g} s"),
                ("STOP", _hex(codec.command(codec.STOP)) + " / " + _hex(bytes((codec.STOP,)))),
                *(
                    (
                        name,
                        _hex(codec.function(code, action=name))
                        + " / "
                        + _hex(codec.function(code, action=name, single=True)),
                    )
                    for name, code in (
                        ("deviceFunctionItemExitLimit", 0),
                        ("deviceFunctionItemCheckClock", 1),
                        ("deviceFunctionItemCheckLight", 1),
                    )
                ),
                (
                    "Light timer, always on / maximum",
                    _hex(codec.light_timer(255, 255))
                    + " / "
                    + _hex(codec.light_timer(900 >> 8, 900 & 255)),
                ),
                ("RGB byte channels 18,52,86 (one write)", _hex(codec.rgb(18, 52, 86))),
                (
                    "Single alarm, 300 minutes / zero gravity",
                    " / ".join(_hex(p) for p in codec.countdown(300, 0x45)),
                ),
                ("Cancel single alarm", " / ".join(_hex(p) for p in codec.countdown(0, 0))),
            ),
        ),
    )


BLOCKS: list[Block] = [("docs/beds/richmat.md", "motionflex", render)]
