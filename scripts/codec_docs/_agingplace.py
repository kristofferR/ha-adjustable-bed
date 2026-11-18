"""Dawn House's generated reference tables over the existing Keeson codec."""

import json

from custom_components.adjustable_bed.codec.keeson import TRANSPORTS
from custom_components.adjustable_bed.profiles import agingplace as app
from scripts.codec_docs._common import _block, _table


def render_controls() -> str:
    return _block(
        _table(
            ("Control", "code", "cmd (typed JSON)", "Execution"),
            (
                (
                    action.label,
                    str(action.code),
                    "`"
                    + json.dumps(json.loads(action.frame("D"))["cmd"], separators=(",", ":"))
                    + "`",
                    "Held" if action.held else "Single write",
                )
                for action in app.ACTIONS.values()
            ),
        )
    )


def render_settings() -> str:
    return _block(
        _table(
            ("Setting", "Range", "Default picker", "Wire example (dvid D)"),
            (
                (
                    "Light brightness",
                    "0–100",
                    "50",
                    f"`{app.setting('brightness', 50, 'D').decode()}`",
                ),
                (
                    "Massage duration",
                    "1–60 min",
                    "30 min",
                    f"`{app.setting('massage_minutes', 30, 'D').decode()}`",
                ),
                (
                    "Motion light duration",
                    "1–30 min",
                    "15 min",
                    f"`{app.setting('motion_minutes', 15, 'D').decode()}`",
                ),
                (
                    "Device information",
                    "Query",
                    "No startup write",
                    f"`{app.device_info('D').decode()}`",
                ),
            ),
        ),
        _table(
            ("Cycle", "Display total (seconds)"),
            ((name, str(total)) for name, total in app.CYCLE_TOTALS.values()),
        ),
    )


def render_timing() -> str:
    transport = TRANSPORTS["json"]
    return _block(
        _table(
            ("Role", "UUID"),
            (
                ("Service", transport.service_uuid),
                ("Write", transport.write_uuid),
                ("Indicate", transport.notify_uuid),
            ),
        ),
        _table(
            ("Operation", "Value"),
            (
                ("Post-connect wait", f"{app.CONNECT_WAIT * 1000:g} ms"),
                ("App requested MTU", str(app.REQUESTED_MTU)),
                ("Literal split size", f"{app.CHUNK_BYTES} bytes"),
                ("Indication ready wait", f"{app.INDICATION_WAIT * 1000:g} ms"),
                (
                    "Held refresh",
                    f"Immediate, then fixed {app.REFRESH_MS} ms delays after completion",
                ),
                ("Release", "One zero-key packet after the drained refresh"),
                (
                    "Self check timeout / quiet aggregation",
                    f"{app.SELF_CHECK_TIMEOUT:g} s / {app.DIAGNOSTIC_QUIET:g} s",
                ),
            ),
        ),
    )


BLOCKS = [
    ("docs/beds/keeson.md", "agingplace-controls", render_controls),
    ("docs/beds/keeson.md", "agingplace-settings", render_settings),
    ("docs/beds/keeson.md", "agingplace-timing", render_timing),
]
