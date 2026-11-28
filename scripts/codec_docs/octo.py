"""Cosyworld tables from its own profile over the extracted OCTO encoder."""

from custom_components.adjustable_bed.codec.octo import OctoPacketCodec
from custom_components.adjustable_bed.profiles import cosyworld as app

from ._common import _block, _hex, _table

GUIDE = "docs/beds/octo.md"


def profile() -> str:
    p = app.PROFILE
    return _block(
        _table(
            ("Profile", "Service", "Write / notify", "Write mode"),
            [
                (f"`{p.key}`", f"`{app.SERVICE}`", f"`{app.CHARACTERISTIC}`", "Without response"),
            ],
        ),
        _table(
            ("Setting", "Value"),
            [
                ("Movement / recall refresh", f"{p.refresh_ms} ms"),
                ("Card start delay", f"{p.start_delay_ms} ms"),
                ("Card motor release delay", f"{p.motor_release_ms} ms"),
                ("Card memory release delay", f"{p.memory_release_ms} ms"),
                ("Maximum held action", f"{p.max_hold_ms / 1000:g} s"),
                ("Handshake reply deadline", f"{p.handshake_timeout_s:g} s"),
                (
                    "Host discovery / write deadline",
                    f"{p.discovery_timeout_s:g} / {p.write_timeout_s:g} s",
                ),
                ("Disconnect after reset", f"{p.reset_disconnect_s:g} s"),
                (
                    "Light timer",
                    f"{app.LIGHT_TIMER_OPTIONS[0]}, {app.LIGHT_TIMER_OPTIONS[1]} to {app.LIGHT_TIMER_OPTIONS[-1]}",
                ),
                ("Display aliases (no layout selection)", ", ".join(f"`{n}`" for n in app.ALIASES)),
            ],
        ),
    )


def commands() -> str:
    c = OctoPacketCodec()
    rows = [
        (f"{name} {direction}", _hex(c._build_packet([2, command], [mask])))
        for name, mask in app.MOTOR_MASKS.items()
        for direction, command in (("up", 0x70), ("down", 0x71))
    ]
    rows += [
        ("All motors down (four motors)", _hex(c._build_packet([2, 0x71], [0x1E]))),
        ("STOP", _hex(c._build_packet([2, 0x73]))),
        ("Recall slot 1 (wire index 0)", _hex(c._build_packet([2, 0x72], [0]))),
        ("Save slot 1 (wire index 0)", _hex(c._build_packet([0x10, 0x70], [0]))),
        *(
            (name, _hex(frame))
            for name, frame in zip(
                ("Handshake", "Device information", "Capabilities"), app.STARTUP, strict=True
            )
        ),
        ("Reset receiver", _hex(c._build_packet([0x20, 0xAE]))),
    ]
    rows += [
        ("Enroll PIN 0123 (numeric digits)", _hex(c._build_packet([0x20, 0x41], [0, 1, 2, 3]))),
        ("Unlock PIN 9876 (numeric digits)", _hex(c._build_packet([0x20, 0x43], [9, 8, 7, 6]))),
        ("Teach remote", _hex(c._build_packet([0x20, 0x72], [0, 0, 0x10, 1, 1, 1, 1, 1]))),
    ]
    return _block(
        _table(("Action", "Frame"), rows),
        _table(
            ("Capability", "Identifier", "Value update"),
            [
                *(
                    (
                        name.replace("_", " "),
                        f"`{key:06x}`",
                        "Replace first byte; retain every tail byte",
                    )
                    for name, key in app.TOGGLES.items()
                ),
                ("Light timer", "`000103`", "Replace whole value with selected minutes"),
            ],
        ),
        "Light, synchro and remote lock preserve the peer record's read-only flag, "
        "characteristic and type, replacing only the first byte of its nonempty "
        "value. Every trailing value byte stays intact. The light timer replaces "
        "the whole value with the selected minutes. No synthetic capability "
        "metadata is used as a receiver default.",
    )


BLOCKS = [(GUIDE, "cosyworld-profile", profile), (GUIDE, "cosyworld-commands", commands)]
