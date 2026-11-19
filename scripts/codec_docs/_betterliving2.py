"""BetterLiving2 reference tables rendered from production profile data."""

from custom_components.adjustable_bed.profiles import betterliving2 as app
from scripts.codec_docs._common import _block, _hex, _table


def render_betterliving2() -> str:
    wires = ("P1", "P2", "P3")
    motors = {
        f"{axis} {'up' if i == 0 else 'down'}": word
        for axis, words in app.MOTORS.items()
        for i, word in enumerate(words)
    }
    motors.update(
        {
            "2-motor back and feet up": 5,
            "2-motor back and feet down": 10,
            "3-motor all sections up": 16,
            "3-motor all sections down": 32,
            "STOP": 0,
        }
    )
    return _block(
        "#### Controls",
        _table(
            ("Control", *wires),
            (
                (name, *(_hex(app.command(wire, word)) for wire in wires))
                for name, word in motors.items()
            ),
        ),
        _table(
            ("Preset", *wires),
            (
                (name, *(_hex(app.command(wire, app.PRESETS[wire][name])) for wire in wires))
                for name in app.PRESETS["P1"]
            ),
        ),
        _table(
            ("Program", *wires),
            (
                (name, *(_hex(app.command(wire, app.PROGRAM[wire][name])) for wire in wires))
                for name in app.PROGRAM["P1"]
            ),
        ),
        _table(
            ("P1 absolute control", "Values", "Word base"),
            (
                *((zone, "0..3", f"`0x{word:08X}`") for zone, word in app.P1_MASSAGE_BASES.items()),
                (
                    "Timer input",
                    ", ".join(map(str, app.P1_TIMER_INPUTS)),
                    f"`0x{app.P1_TIMER_BASE:08X}`",
                ),
                (
                    "Light",
                    "off / on",
                    " / ".join(f"`0x{word:08X}`" for word in app.P1_LIGHT.values()),
                ),
                ("Second same preset tap", "stop active preset", f"`0x{app.P1_PRESET_STOP:08X}`"),
            ),
        ),
        _table(
            ("Step control", "P2", "P3"),
            (
                (name, *(_hex(app.command(wire, word)) for wire in ("P2", "P3")))
                for name, word in {**app.STEP_MASSAGE, "light": app.STEP_LIGHT}.items()
            ),
        ),
        _table(
            ("Wake action", *wires),
            (
                (name, *(str(app.ALARM_KINDS[wire][name]) for wire in wires))
                for name in app.ALARM_KINDS["P1"]
            ),
        ),
        _table(
            ("Role", *wires),
            (
                (name, *(f"`{app.GATT[wire][i]}`" for wire in wires))
                for i, name in enumerate(("Write service", "Write", "Notify service", "Notify"))
            ),
        ),
        "#### Timing",
        _table(
            ("Operation", "Schedule"),
            (
                *(
                    (screen.label, f"refresh every {screen.refresh_ms} ms")
                    for screen in app.LAYOUTS.values()
                ),
                ("Movement cleanup", f"{app.RELEASE_COUNT} zero words, {app.RELEASE_MS} ms apart"),
                ("Recall", f"one key, owned zero release after {app.RECALL_RELEASE_MS} ms"),
                *(
                    (
                        f"Program {wire}",
                        f"{app.PROGRAM_DURATION_MS} ms, every {app.PROGRAM_REFRESH_MS[wire]} ms",
                    )
                    for wire in wires
                ),
                (
                    "P1 zone pairs",
                    f"two writes per zone; {app.MASSAGE_ZONE_GAP_MS} ms between pairs",
                ),
                ("P3 massage follow-up", f"query at +{app.P3_MASSAGE_QUERY_MS} ms"),
                (
                    "Set/cancel alarm",
                    f"{app.ALARM_REPEAT_COUNT} immediate writes, sync at +{app.ALARM_SYNC_DELAY_MS} ms, query at +{app.ALARM_QUERY_DELAY_MS} ms",
                ),
                (
                    "First connection",
                    f"subscribe, time sync, query at +{app.SETUP_QUERY_DELAY_MS} ms",
                ),
                ("Reconnect", "subscribe, time sync, immediate sequential alarm read"),
            ),
        ),
    )


BLOCKS = [("docs/beds/keeson.md", "keeson-betterliving2", render_betterliving2)]
