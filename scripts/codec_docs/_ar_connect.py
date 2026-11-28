"""Native AR Connect reference tables; no admitted Home Assistant controls."""

from itertools import product

from custom_components.adjustable_bed.codec.linak import control_frame
from custom_components.adjustable_bed.profiles.ar_connect import AR_CONNECT as P
from custom_components.adjustable_bed.profiles.ar_connect import Axis

from ._common import Block, _block, _hex, _table


def transport() -> str:
    return _block(
        _table(
            ("Native role", "Value"),
            [
                ("Profile key (not selectable)", f"`{P.key}`"),
                ("Default scan filter / control service", f"`{P.control_service}`"),
                ("Scan timeout", f"{P.scan_timeout_ms} ms"),
                ("Standard command", f"`{P.command_characteristic}`"),
                ("Error", f"`{P.error_characteristic}`"),
                ("Configuration service", f"`{P.configuration_service}`"),
                ("Configuration write", f"`{P.configuration_characteristic}`"),
                ("Reference service", f"`{P.reference_service}`"),
                ("Reference mask candidate", f"`{P.reference_mask}`"),
                *((f"{axis.capitalize()} reference", f"`{uuid}`") for axis, uuid in P.references),
            ],
        )
    )


def commands() -> str:
    movements: dict[bytes, tuple[str, str, str]] = {}
    for values in product((None, False, True), repeat=len(P.axes)):
        directions: dict[Axis, bool] = {
            axis: up for axis, up in zip(P.axes, values, strict=True) if up is not None
        }
        frame = P.movement(directions)
        label = ", ".join(f"{axis} {'up' if up else 'down'}" for axis, up in directions.items())
        movements.setdefault(
            frame,
            (
                label or "Empty map (STOP_MOVEMENT)",
                _hex(frame),
                _hex(P.movement(directions, slow=True)),
            ),
        )
    return _block(
        "Native construction examples only. All four axes selected in the same direction "
        "use the all-up or all-down opcode first. Other selections use the first "
        "applicable pair in this order: "
        + "; ".join(" + ".join(pair) for pair in P.pair_precedence)
        + ".",
        _table(("Selected sections (example)", "Normal", "Slow"), movements.values()),
        _table(
            ("Native memory index", "Recall normal", "Recall slow", "Store"),
            [
                (
                    str(index),
                    _hex(control_frame(recall)),
                    _hex(control_frame(recall, slow=True)),
                    _hex(control_frame(save)),
                )
                for index, (recall, save) in enumerate(
                    zip(P.recall_opcodes, P.save_opcodes, strict=True)
                )
            ],
        ),
        _table(
            ("Native bridge action", "Bytes"),
            [
                ("stopBed (WAKE_UP)", _hex(control_frame(P.stop_bed_opcode))),
                ("toggleLight (AUX_1_TOGGLE)", _hex(control_frame(P.light_toggle_opcode))),
            ],
        ),
    )


def configuration() -> str:
    return _block(
        _table(
            ("Native write order", "Conversion example: speedUp=100, accelerationUp=50"),
            [(axis.capitalize(), _hex(frame)) for axis, frame in P.custom_speed(100, 50)],
        ),
        f"HEAD is skipped. Each awaited write is followed by {P.custom_speed_post_write_ms} ms, "
        "including the last. This is configuration pacing, not movement refresh timing.",
    )


BLOCKS: list[Block] = [
    ("docs/beds/linak.md", "linak-ar-connect-transport", transport),
    ("docs/beds/linak.md", "linak-ar-connect-commands", commands),
    ("docs/beds/linak.md", "linak-ar-connect-configuration", configuration),
]
