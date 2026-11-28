"""EasyCtrl's independent model/timing/control data on the shared P1 guide."""

from custom_components.adjustable_bed.codec import easyctrl as codec
from custom_components.adjustable_bed.profiles import easyctrl as app

from ._common import _block, _hex, _table

GUIDE = "docs/beds/cheerssleep.md"


def models() -> str:
    return _block(
        _table(
            (
                "Model",
                "App name",
                "Controls",
                "Motor channels",
                "Memory slots",
                "Presets",
                "Massage",
                "Light",
                "Wake/sleep timers",
                "Held refresh",
                "Release offsets (ms)",
            ),
            (
                (
                    str(m.key),
                    app.APP_MODEL_NAMES[m.key],
                    ", ".join(a.label for a in m.axes),
                    str(m.motor_count),
                    str(m.memory),
                    ", ".join(m.presets) or "None",
                    "Head/all/foot" if m.massage else "No",
                    "RGB" if m.rgb else "On only" if m.key == 14 else "On/off" if m.light else "No",
                    "Yes" if m.alarm else "No",
                    str(m.refresh_ms) + " ms" if m.stream else "One press frame",
                    ", ".join(map(str, m.release_ms)),
                )
                for m in app.MODELS.values()
            ),
        )
    )


def motors() -> str:
    return _block(
        _table(
            (
                "Models",
                "Control",
                "Action motor key",
                "Up (serial 2)",
                "Down (serial 2)",
                "STOP (serial 3)",
            ),
            (
                (
                    str(m.key),
                    axis.label,
                    f"`{axis.key}`",
                    _hex(codec.p1(2, 1, axis.up)),
                    _hex(codec.p1(2, 1, axis.down)),
                    _hex(codec.p1(3, 1, axis.stop)),
                )
                for m in app.MODELS.values()
                for axis in m.axes
            ),
        )
    )


def controls() -> str:
    rows = [
        (name.replace("_", " "), _hex(codec.p1(2, 1, code)), "0")
        for name, code in (*app.PRESET_CODES.items(), *app.ACTION_CODES.items())
    ]
    examples = {
        "light_on": (1, -128, "saved packed color/brightness, default -128"),
        "light_off": (1, -128, "saved packed color/brightness, default -128"),
        "light_save": (1, 0x11223344, "packed RGB and brightness"),
        "light_delay": (3, 10, "10 (fixed editor default)"),
        "light_query": (2, 0, "0"),
        "wakeup_countdown": (1, 3600, "seconds until selected time"),
        "wakeup_action": (1, 0x5504, "mode plus relative weekday mask << 8"),
        "sleep_countdown": (1, 600, "minutes × 60"),
        "sleep_action": (1, 3, "3"),
    }
    rows += [
        (name.replace("_", " "), _hex(codec.p1(0 if pid != 1 else 2, pid, code, value)), label)
        for name, code in app.CONTROL_CODES.items()
        for pid, value, label in (examples.get(name, (1, 0, "0")),)
    ]
    rows += [
        (f"Memory {i + 1} {kind}", _hex(codec.p1(2, 1, code)), "0")
        for kind, codes in (("recall", app.MEMORY_RECALL), ("save", app.MEMORY_SAVE))
        for i, code in enumerate(codes)
    ]
    rows += [
        (f"{zone} massage mode {i + 1}", _hex(codec.p1(2, 1, code, 600)), "10/20/30 minutes × 60")
        for zone, codes in app.MASSAGE_MODES.items()
        for i, code in enumerate(codes)
    ]
    rows += [
        (
            f"{zone} massage strength",
            _hex(codec.p1(2, 1, code, 5)),
            ", ".join(map(str, app.POWER_VALUES)),
        )
        for zone, code in app.MASSAGE_POWER.items()
    ]
    rows += [
        (f"Swing timer {minutes} min", _hex(codec.p1(2, 1, code)), "0")
        for minutes, code in app.SWING_TIMERS.items()
    ]
    return _block(_table(("Action", "Example carrier frame", "Parameter"), rows))


def timing() -> str:
    m = app.MODELS[100]
    return _block(
        _table(
            ("Operation", "Delay (ms)"),
            (
                ("Flat tap used by HA", str(m.flat_tap_ms)),
                ("Short flat threshold", str(m.flat_threshold_ms)),
                ("Before each KEEP", str(m.keep_delay_ms)),
                ("Massage stop → mode → power, RGB delay → persist", str(m.setting_delay_ms)),
                ("Wake/sleep countdown → action", str(m.alarm_delay_ms)),
                ("Model 324 initial light query", str(m.query_delay_ms)),
            ),
        )
    )


BLOCKS = [
    (GUIDE, "easyctrl-models", models),
    (GUIDE, "easyctrl-motors", motors),
    (GUIDE, "easyctrl-controls", controls),
    (GUIDE, "easyctrl-timing", timing),
]
