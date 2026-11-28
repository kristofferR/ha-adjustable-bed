"""Dunlopillo tables from its independent profile and the Keeson codec."""

from custom_components.adjustable_bed.profiles import dunlopillo as app
from scripts.codec_docs._common import _hex, _table


def render() -> str:
    return "\n".join(
        [
            *_table(
                ("Role", "Value"),
                [
                    ("Service", "Not pinned; last matching characteristic in enumeration order"),
                    ("Write", app.WRITE_UUID),
                    ("Notify", app.NOTIFY_UUID),
                    (
                        "Write mode",
                        "Without response when offered, otherwise with response (Android default)",
                    ),
                ],
            ),
            "",
            *_table(
                ("Layout", "Controls", "Refresh", "Pulse release"),
                [
                    (
                        app.CHOICES[key],
                        ", ".join(app.AXES[key]),
                        f"{app.REFRESH_MS} ms",
                        f"{app.PULSE_RELEASE_MS} ms",
                    )
                    for key in app.PROFILES
                ],
            ),
            "",
            *_table(
                ("Layout", "Control", "Frame", "Dispatch"),
                [
                    (
                        layout.upper(),
                        control.label,
                        _hex(app.codec.frame(control.word)),
                        control.mode,
                    )
                    for layout, controls in app.CONTROLS.items()
                    for control in controls.values()
                ],
            ),
            "",
            *_table(
                ("Operation", "Frame"),
                [
                    ("Release / STOP", _hex(app.codec.frame(0))),
                    ("Rename to Test", _hex(app.rename("Test"))),
                    ("Rename to Bed", _hex(app.rename("Bed"))),
                ],
            ),
        ]
    )


BLOCKS = [("docs/beds/keeson.md", "keeson-dunlopillo", render)]
