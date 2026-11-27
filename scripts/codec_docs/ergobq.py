"""Tables from the shipped ErgoBQ profile and codec."""

from custom_components.adjustable_bed.codec import ergobq as codec
from custom_components.adjustable_bed.profiles import ergobq as app

from ._common import Block, _block, _hex, _table

GUIDE = "docs/beds/ergobq.md"


def transport() -> str:
    return _block(
        _table(
            ("Role", "UUID"),
            (
                (role, f"`{uuid}`")
                for role, uuid in (
                    ("Service", codec.SERVICE),
                    ("Write", codec.WRITE),
                    ("Notify", codec.NOTIFY),
                    ("Product service data", codec.IDENTITY_SERVICE),
                )
            ),
        )
    )


def profiles() -> str:
    return _block(
        _table(
            ("Profile", "Bed type", "Product IDs", "Layout", "Execution"),
            (
                (
                    "ErgoBQ BED",
                    "ergobq",
                    ", ".join(app.PRODUCTS),
                    "Serial byte 4 = 4: four motors; other values or blank: two",
                    str(app.PROFILE.execution.hold),
                ),
            ),
        )
    )


def commands() -> str:
    rows = []
    for dp, (name, limit) in app.AXES.items():
        for value in (0, limit):
            rows.append(
                (
                    f"{name} target {value}",
                    f"DP{dp}, signed BE32",
                    _hex(codec.publish((codec.number(dp, value),))),
                )
            )
    rows.append(("STOP", "DP5 = true", _hex(codec.publish((codec.boolean(5, True),)))))
    for operation, label in ((6, "Recall"), (7, "Save"), (8, "Restore default")):
        for scene, value in app.SCENES.items():
            rows.append(
                (
                    f"{label} {scene}",
                    f"DP{operation}, enum {value}",
                    _hex(codec.publish((codec.enumeration(operation, value),))),
                )
            )
    for value, name in enumerate(("A", "B", "AB")):
        rows.append(
            (f"Route {name}", f"DP9 = {value}", _hex(codec.publish((codec.enumeration(9, value),))))
        )
    for value, name in enumerate(("A to B", "B to A")):
        rows.append(
            (
                f"Force sync {name}",
                f"DP9 = AB, DP10 = {value}",
                _hex(codec.publish(codec.force_sync(value))),
            )
        )
    for dp in (12, 14):
        rows.append(
            (
                f"Massage DP{dp}",
                "on, intensity 0..5, mode 0..3, minutes 0..60",
                _hex(codec.publish((codec.raw(dp, codec.Massage(True, 3, 0, 15).encode()),))),
            )
        )
    for dp, name in ((18, "Massage sync"), (30, "Child lock"), (50, "Underbed light")):
        for value in (False, True):
            rows.append(
                (
                    f"{name} {value}",
                    f"DP{dp}, bool",
                    _hex(codec.publish((codec.boolean(dp, value),))),
                )
            )
    rows.extend(
        (
            ("Light brightness", "DP51, 0..100", _hex(codec.publish((codec.number(51, 50),)))),
            (
                "Light RGB",
                "DP52, exactly three bytes",
                _hex(codec.publish((codec.raw(52, bytes([255, 0, 16])),))),
            ),
            ("Light auto-off", "DP53, 0..120 minutes", _hex(codec.publish((codec.number(53, 5),)))),
            (
                "Custom schedule example",
                "DP41, full 24-byte record",
                _hex(codec.publish((codec.raw(41, codec.custom_schedule(1, 2, 0, 7, 30)),))),
            ),
            (
                "DIY schedule example",
                "DP41, header and saved mode",
                _hex(codec.publish((codec.raw(41, codec.diy_schedule(2, 1, 2, 6, 45, 11)),))),
            ),
            (
                "Run saved DIY example",
                "DP61, saved modes 11..30",
                _hex(codec.publish(codec.run_diy(11))),
            ),
            ("Terminate DIY", "DP61, command 3", _hex(codec.publish(codec.run_diy(3)))),
            ("Feature query", "CMD00, reply acceptance unknown", _hex(codec.frame(0))),
            ("Full-state query", "CMD02, CMD05 reports", _hex(codec.frame(2))),
            ("Metadata query", "CMD01, nonempty CMD01 reply", _hex(codec.frame(1, b"\x00"))),
            ("Link example", "CMD03, synthetic stamp 12", _hex(codec.auth("12"))),
            (
                "Unlink example",
                "CMD03 phase 2, synthetic stamp 12",
                _hex(codec.auth("12", phase=2)),
            ),
            (
                "Release association example",
                "CMD03 phase 3, synthetic stamp 12",
                _hex(codec.auth("12", phase=3)),
            ),
        )
    )
    return _block(_table(("Action", "Fields / bounds", "Example frame"), rows))


def timing() -> str:
    p = app.PROFILE
    return _block(
        _table(
            ("Operation", "Timing"),
            (
                ("Notify settle", f"{p.notify_settle:g} s"),
                (
                    "GATT write",
                    f"{p.write_timeout:g} s, at most {p.attempts} attempts, {p.retry_delay:g} s retry delay",
                ),
                (
                    "Link authentication",
                    f"{p.auth_timeout:g} s; nonempty CMD03 first byte 1 succeeds",
                ),
                (
                    "Metadata",
                    f"{p.metadata_timeout:g} s sync wait; {p.response_timeout:g} s last-fragment response wait",
                ),
                (
                    "Unlink",
                    f"{p.unlink_timeout:g} s sync wait; {p.response_timeout:g} s last-fragment response wait",
                ),
                ("Gesture", "One target on start, one DP5 on release; no refresh"),
                ("RTC / feature query", "No proven response/ACK contract"),
            ),
        )
    )


BLOCKS: list[Block] = [
    (GUIDE, "ergobq-transport", transport),
    (GUIDE, "ergobq-profiles", profiles),
    (GUIDE, "ergobq-commands", commands),
    (GUIDE, "ergobq-timing", timing),
]
