"""Render Platinum's layouts, wire keys, GATT roles and press schedules."""

from custom_components.adjustable_bed.codec import aminach as codec
from custom_components.adjustable_bed.profiles import aminach as app

from ._common import Block, _block, _hex, _table

GUIDE = "docs/beds/aminach.md"


def bed_types() -> dict[str, tuple[str, ...]]:
    return {"aminach": ("platinum",)}


def profiles() -> str:
    p = app.PLATINUM
    return _block(
        _table(
            ("Bed type / profile", "Layout", "Controls", "Default"),
            (
                (
                    f"aminach / {p.key}",
                    str(count),
                    ", ".join("foot" if axis == "legs" else axis for axis in axes),
                    "Yes" if count == p.default_motor_count else "No",
                )
                for count, axes in app.LAYOUTS.items()
            ),
        ),
        _table(
            ("Setting", "Value"),
            (
                ("Discovery prefix (case-sensitive)", f"`{app.NAME_PREFIX}`"),
                ("Normal key refresh", f"{p.refresh_ms} ms, immediate first write"),
                ("New Memo gesture refresh", f"{p.memo_refresh_ms} ms, immediate first write"),
                ("Memo minimum elapsed before ordinary release", f"{p.memo_minimum_ms} ms"),
                ("Held execution", str(p.execution.hold)),
                ("Concurrent axes / native sides", "None"),
            ),
        ),
    )


def transports() -> str:
    return _block(
        _table(
            ("Role", "Service", "Characteristic", "Write mode"),
            (
                (
                    "Control and address response",
                    app.SERVICE,
                    app.WRITE,
                    "Android default: without response when offered, otherwise with response",
                ),
                ("Notifications", app.SERVICE, app.NOTIFY, "Notify subscription"),
            ),
        )
    )


def commands() -> str:
    return _block(
        _table(
            ("Action", "Key", "Frame", "Layouts"),
            (
                (
                    action,
                    f"`{key:04X}`",
                    _hex(app.PLATINUM.frame(action)),
                    ", ".join(
                        str(count)
                        for count, axes in app.LAYOUTS.items()
                        if action in ("sleep", "light", "memo", "release")
                        or action.rsplit("_", 1)[0] in axes
                    ),
                )
                for action, key in app.KEYS.items()
            ),
        )
    )


def session() -> str:
    return _block(
        _table(
            ("Message", "Encoding / handling"),
            (
                (
                    "Address request",
                    _hex(codec.ADDRESS_REQUEST) + ", exact payload before recognition",
                ),
                (
                    "Adapter response example (synthetic)",
                    _hex(codec.adapter_response("01:23:45:67:89:AB")),
                ),
                (
                    "Adapter response fields",
                    "B1 07 00, six initiating adapter MAC octets in display order, sum of preceding bytes modulo 256",
                ),
                (
                    "Post-recognition indicator",
                    "B2 02 S X, S 0 or 1, X ignored, trailing bytes accepted, no checksum check",
                ),
                ("Indicator meaning", "Opaque title indicator, protocol diagnostics only"),
            ),
        )
    )


BLOCKS: list[Block] = [
    (GUIDE, "aminach-profiles", profiles),
    (GUIDE, "aminach-transports", transports),
    (GUIDE, "aminach-commands", commands),
    (GUIDE, "aminach-session", session),
]
