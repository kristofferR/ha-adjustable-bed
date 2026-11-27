"""FlexiRest tables from its profile and the shared control catalog."""

from custom_components.adjustable_bed.profiles import flexirest as app
from custom_components.adjustable_bed.profiles.ff_frame import SolaceCommands as C
from scripts.codec_docs._common import _block, _hex, _table


def render() -> str:
    commands = (
        ("Back up / down", C.MOTOR_BACK_UP, C.MOTOR_BACK_DOWN),
        ("Feet up / down", C.MOTOR_LEGS_UP, C.MOTOR_LEGS_DOWN),
        ("Head massage increase / decrease", C.MASSAGE_HEAD_UP, C.MASSAGE_HEAD_DOWN),
        ("Feet massage increase / decrease", C.MASSAGE_FOOT_UP, C.MASSAGE_FOOT_DOWN),
        ("Massage frequency increase / decrease", C.MASSAGE_FREQUENCY_UP, C.MASSAGE_FREQUENCY_DOWN),
        ("Controller sync on / off", app.SYNC_ON, app.SYNC_OFF),
    )
    single = (
        ("Movement release / STOP", C.MOTOR_STOP),
        ("Flat", C.PRESET_FLAT_BED),
        ("Leg relaxation", C.PRESET_RELAXING_BEDTIME),
        ("Massage off", C.MASSAGE_STOP),
        ("Light off (independent of brightness support)", app.LIGHT_OFF),
        ("Brightness query", C.LIGHT_STATUS_QUERY),
        ("Controller sync query", app.SYNC_QUERY),
        ("Fault query", app.FAULT_QUERY),
        *(
            (f"Saved {key} query", frame)
            for key, frame in zip(
                ("memory_1", "memory_2", "tv", "zero_g", "anti_snore"), C.QUERY_Q2, strict=True
            )
        ),
    )
    timing = (
        ("Local clock", app.CLOCK_DELAY_MS),
        ("Brightness query", app.LIGHT_QUERY_DELAY_MS),
        ("Controller sync query", app.SYNC_DELAY_MS),
        ("First saved preset query", app.PRESET_QUERY_DELAY_MS),
        ("Between saved preset queries", app.PRESET_QUERY_SPACING_MS),
        ("Android long-press save / clear threshold", app.PRESET_HOLD_MS),
    )
    return _block(
        _table(
            ("Control", "First frame", "Second frame"),
            ((label, _hex(a), _hex(b)) for label, a, b in commands),
        ),
        _table(("Action", "Frame"), ((label, _hex(frame)) for label, frame in single)),
        _table(
            ("Startup / gesture", "Milliseconds"), ((label, str(value)) for label, value in timing)
        ),
        _table(
            ("Selector", "Effect"),
            (
                (
                    ", ".join(app.NAME_TOKENS),
                    "Raw case-sensitive substring discovery candidates, explicit app selection required",
                ),
                (", ".join(app.FAULT_HIDDEN_TOKENS), "Hide fault query"),
                ("QMS2, case-insensitive", "Hide alarm massage, manual massage remains available"),
            ),
        ),
    )


BLOCKS = [("docs/beds/ff_frame.md", "flexirest", render)]
