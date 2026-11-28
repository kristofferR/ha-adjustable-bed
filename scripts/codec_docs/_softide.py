"""Softide tables over the shared AA codec and independent app profile."""

from custom_components.adjustable_bed.profiles import softide as app

from ._common import _block, _hex, _table

GUIDE = "docs/beds/sleep-assistant.md"


def profiles() -> str:
    return _block(
        _table(
            ("Model", "Primary remote", "Care remote", "Controls", "Primary programs"),
            (
                (
                    label,
                    app.SoftideProfile(key).layout or "None",
                    app.SoftideProfile(key, "care").layout or "None",
                    ", ".join(app.SoftideProfile(key).controls),
                    ", ".join(app.PROGRAMS[a][0] for a in app.SoftideProfile(key).programs),
                )
                for key, label in app.MODELS.items()
            ),
        )
    )


def commands() -> str:
    return _block(
        _table(
            ("Control", "Frame"),
            ((name.replace("_", " "), _hex(app.frame(name))) for name in app.WORDS),
        )
    )


def auxiliary() -> str:
    from custom_components.adjustable_bed.codec.sleep_assistant import SOFTIDE_LITERALS

    return _block(
        _table(
            ("Action", "Frame"),
            ((name.replace("_", " "), _hex(app.frame(name))) for name in SOFTIDE_LITERALS),
        )
    )


def programs() -> str:
    return _block(
        _table(
            ("Program", "Offset", "Frame"),
            (
                (label, f"{at} ms", _hex(frame))
                for action, (label, _) in app.PROGRAMS.items()
                for at, frame in app.program(action)
            ),
        )
    )


def timing() -> str:
    return _block(
        _table(
            ("Operation", "Schedule"),
            (
                ("Held motion", f"Immediate, then every {app.REFRESH_MS} ms"),
                ("Primary app ceiling", f"{app.PRIMARY_TIMEOUT_MS} ms; timer ends refresh"),
                ("Care app ceiling", "None; Home Assistant bounds every hold"),
                ("Primary release", "One immediate STOP"),
                ("Care release", "End refresh; no packet"),
                ("Massage follow-up", f"{app.QUERY_DELAY_MS} ms after action"),
                (
                    "Optional first-use massage preparation",
                    f"{app.FREQUENCY_DELAY_MS} ms before action",
                ),
                ("Program stages", ", ".join(f"{ms} ms" for ms in app.PROGRAM_OFFSETS_MS)),
                ("GATT request pacing", f"{app.REQUEST_DELAY_MS} ms"),
                ("Connection timeout", "10 s"),
                ("Startup writes", "None"),
                ("Moon display gate", f"{app.MOON_DISPLAY_SECONDS} s"),
                ("Moon packet gate", f"Reject elapsed intervals <= {app.MOON_GATE_MS} ms; every packet resets its clock"),
                ("Moon new-sample budget", str(app.MOON_SAMPLE_LIMIT)),
                (
                    "Home Assistant tap policy",
                    "3 refreshes; held controls use the gesture duration",
                ),
            ),
        )
    )


def transport() -> str:
    return _block(
        _table(
            ("Role", "Service", "Characteristic"),
            (
                ("Write", app.SERVICE, app.WRITE),
                ("Notify", app.SERVICE, app.NOTIFY),
            ),
        )
    )


BLOCKS = [
    (GUIDE, "softide-" + name, renderer)
    for name, renderer in (
        ("profiles", profiles),
        ("transport", transport),
        ("commands", commands),
        ("auxiliary", auxiliary),
        ("programs", programs),
        ("timing", timing),
    )
]
