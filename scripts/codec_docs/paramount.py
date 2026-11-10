"""Generated Paramount tables, directly from the P1 codec and app profile."""

from custom_components.adjustable_bed.codec import paramount as codec
from custom_components.adjustable_bed.profiles.paramount import PARAMOUNT
from scripts.codec_docs._common import Block, _block, _hex, _table

GUIDE = "docs/beds/paramount.md"


def bed_types() -> dict[str, tuple[str, ...]]:
    return {PARAMOUNT.key: ("paramount",)}


def profiles() -> str:
    p = PARAMOUNT
    return _block(
        _table(
            (
                "Profile",
                "Bed type",
                "Initial guard",
                "Next request",
                "Press guard",
                "Missing reply",
            ),
            (
                (
                    p.key,
                    "`paramount`",
                    f"{p.initial_delay_ms} ms",
                    f"{p.response_delay_ms} ms after matching reply",
                    f"{p.press_delay_ms} ms",
                    f"{p.response_timeout_ms} ms, fail without replay",
                ),
            ),
        ),
        _table(
            ("Capability bit", "Control"),
            ((str(bit), axis) for axis, bit in codec.CAPABILITIES.items()),
        ),
        _table(
            ("Low five bits", "Named layout"),
            ((f"0x{mask:02x}", label) for mask, label in codec.LAYOUTS.items()),
        ),
        _table(
            ("Axis", "Default range"),
            (
                ("Head / linked motion", f"0–{p.head_max} degrees"),
                ("Legs", f"0–{p.legs_max} degrees"),
                ("Height", "Device-reported minimum and maximum, cm"),
            ),
        ),
    )


def transports() -> str:
    return _block(
        _table(
            ("Role", "UUID"),
            (
                (name, f"`{value}`")
                for name, value in (
                    ("Control service", codec.SERVICE_UUID),
                    ("Connect-wait advertisement", codec.CONNECT_WAIT_UUID),
                    ("Registration advertisement", codec.REGISTRATION_UUID),
                    ("Write, with response", codec.WRITE_UUID),
                    ("Indications", codec.NOTIFY_UUID),
                    ("Serial ATT read", codec.SERIAL_UUID),
                )
            ),
        )
    )


def commands() -> str:
    return _block(
        _table(
            ("Control", "Bytes"),
            ((name.replace("_", " "), _hex(value)) for name, value in PARAMOUNT.frames.items()),
        ),
        _table(
            ("Memory recall example", "Bytes"),
            (
                ("Slot 1, H=30, L=10, Z=40, T=0", _hex(codec.control(22, (30, 10, 40, 0)))),
                ("Slot 2, H=75, L=30, Z=255, T=5", _hex(codec.control(23, (75, 30, 255, 5)))),
            ),
        ),
        _table(
            ("Setting", "Flags byte index (zero based)", "Mask"),
            (
                (name, str(index), f"0x{mask:02x}")
                for name, (index, mask) in codec.SETTING_BITS.items()
            ),
        ),
        "Settings writes encode command 0x85 with all four flag bytes and both four-byte memory postures. Only the selected bit or memory is replaced.",
    )


BLOCKS: tuple[Block, ...] = (
    (GUIDE, "paramount-profiles", profiles),
    (GUIDE, "paramount-transports", transports),
    (GUIDE, "paramount-commands", commands),
)
