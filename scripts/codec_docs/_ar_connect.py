"""Generated AR Connect native and headboard runtime reference tables."""

from datetime import datetime
from itertools import product

from custom_components.adjustable_bed.codec import ar_connect as hb_codec
from custom_components.adjustable_bed.codec.linak import control_frame
from custom_components.adjustable_bed.profiles import ar_connect as APP
from custom_components.adjustable_bed.profiles import ar_headboard as HB
from custom_components.adjustable_bed.profiles.ar_connect import AR_CONNECT as P
from custom_components.adjustable_bed.profiles.ar_connect import Axis

from ._common import Block, _block, _hex, _table


def transport() -> str:
    return _block(
        _table(
            ("Native role", "Value"),
            [
                ("Home Assistant profile", f"`{P.key}:native`"),
                ("Default scan filter / control service", f"`{P.control_service}`"),
                ("Scan timeout", f"{P.scan_timeout_ms} ms"),
                ("Standard command", f"`{P.command_characteristic}`"),
                ("Error", f"`{P.error_characteristic}`"),
                ("Configuration service", f"`{P.configuration_service}`"),
                ("Configuration write", f"`{P.configuration_characteristic}`"),
                ("Reference service", f"`{P.reference_service}`"),
                ("Reference mask", f"`{P.reference_mask}`"),
                *(
                    (f"{axis.capitalize()} reference", f"`{uuid}`")
                    for axis, uuid in APP.NATIVE_REFERENCES
                ),
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
        "All four axes selected in the same direction "
        "use the all-up or all-down opcode first. Other selections use the first "
        "applicable pair in this order: "
        + "; ".join(" + ".join(pair) for pair in P.pair_precedence)
        + ".",
        _table(("Selected sections (example)", "Normal", "Slow"), movements.values()),
        _table(
            (
                "Native memory index",
                "Recall normal",
                "Recall slow",
                "Store",
                "Home Assistant controls",
            ),
            [
                (
                    str(index),
                    _hex(control_frame(recall)),
                    _hex(control_frame(recall, slow=True)),
                    _hex(control_frame(save)),
                    (
                        "Recall and save"
                        if index in (0, 2, 3)
                        else "Recall only"
                        if index == 1
                        else "Kernel only, no app control"
                    ),
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
            ("Native write order", "Automatic startup: speedUp=1, accelerationUp=0"),
            [
                (axis.capitalize(), _hex(frame))
                for axis, frame in P.custom_speed(APP.STARTUP_SPEED_UP, APP.STARTUP_ACCELERATION_UP)
            ],
        ),
        f"HEAD is skipped. Each awaited write is followed by {P.custom_speed_post_write_ms} ms, "
        "including the last. This is configuration pacing, not movement refresh timing.",
    )


def runtime_tables() -> str:
    return _block(
        _table(
            ("Native operation", "Timing"),
            [
                (
                    "Held motion and recall",
                    f"First tick {APP.REFRESH_MS} ms; refresh {APP.REFRESH_MS} ms",
                ),
                ("New-start debounce", f"{APP.DEBOUNCE_MS} ms"),
                (
                    "Reference-traffic watchdog",
                    f"Initially {APP.IDLE_INITIAL_MS} ms; each report resets to {APP.IDLE_AFTER_REFERENCE_MS} ms",
                ),
                (
                    "Custom-speed setup",
                    f"{APP.STARTUP_DELAY_S:g} s before dispatch, {P.custom_speed_post_write_ms} ms after each write",
                ),
                ("Optional-section check", f"{APP.PROBE_DIRECTION_S:g} s each direction"),
                (
                    "Side identification",
                    f"{APP.SIDE_DIRECTION_S:g} s each direction; {APP.SIDE_GAP_S:g} s between",
                ),
            ],
        ),
        _table(
            ("Setup layout", "Sections"),
            [(key, ", ".join(axes)) for key, axes in APP.LAYOUTS.items()],
        ),
        _table(
            ("Headboard role", "Service", "Characteristic"),
            [(key, f"`{service}`", f"`{char}`") for key, (service, char) in HB.TRANSPORTS.items()],
        ),
        _table(
            ("Headboard operation", "Order / choices"),
            [
                ("Notify", ", ".join(HB.NOTIFY_ORDER)),
                ("Initial read", ", ".join(HB.INITIAL_READS)),
                (
                    "Mood delay and routine duration",
                    ", ".join(map(str, hb_codec.DURATIONS)) + " minutes",
                ),
            ],
        ),
        _table(
            ("Headboard command", "UTF-8 JSON example"),
            [
                ("Live or mood power", _hex(hb_codec.state(True))),
                ("Live color", _hex(hb_codec.live((255, 0, 0, 0)))),
                ("Local clock", _hex(hb_codec.clock(datetime(2026, 11, 28, 12, 34, 56)))),
                ("Remove returned routine id", _hex(hb_codec.remove(12))),
            ],
        ),
    )


BLOCKS: list[Block] = [
    ("docs/beds/linak.md", "linak-ar-connect-runtime", runtime_tables),
    ("docs/beds/linak.md", "linak-ar-connect-transport", transport),
    ("docs/beds/linak.md", "linak-ar-connect-commands", commands),
    ("docs/beds/linak.md", "linak-ar-connect-configuration", configuration),
]
