"""SleepIQ route timing and semantic command reference from runtime declarations."""

from custom_components.adjustable_bed.beds.sleep_number.commands import COMMANDS
from custom_components.adjustable_bed.beds.sleep_number.mcr import _COMMAND_FIELDS
from custom_components.adjustable_bed.beds.sleep_number.services import INTERNAL_COMMANDS
from custom_components.adjustable_bed.codec import sleepiq as codec
from custom_components.adjustable_bed.profiles.sleepiq import FUZION, MCR

from ._common import Block, _block, _hex, _table


def profiles() -> str:
    return _block(
        _table(
            ("Profile", "Response timeout", "Response retries", "Discovery delay", "Selection"),
            (
                (
                    p.key,
                    f"{p.response_timeout:g} s",
                    str(p.response_retries),
                    f"{p.discovery_delay:g} s",
                    "FUZION generation" if p.key == "fuzion" else "Other generations, UART service",
                )
                for p in (FUZION, MCR)
            ),
        )
    )


def commands() -> str:
    return _block(
        _table(
            ("Operation", "Key", "Parameters", "Result", "Surface"),
            (
                (
                    name,
                    spec.key,
                    ", ".join(f"`{field}`: {kind}" for field, kind in spec.parameters) or "None",
                    ", ".join(f"`{field}`: {kind}" for field, kind in spec.response) or "None",
                    "Native control / diagnostics" if name in INTERNAL_COMMANDS else "Action",
                )
                for name, spec in COMMANDS.items()
            ),
        )
    )


def mcr_commands() -> str:
    return _block(
        _table(
            ("Operation", "Required parameters", "Optional parameters", "Surface"),
            (
                (
                    name,
                    ", ".join(f"`{field}`" for field in sorted(required)) or "None",
                    ", ".join(f"`{field}`" for field in sorted(optional)) or "None",
                    "Diagnostics" if name in INTERNAL_COMMANDS else "Action",
                )
                for name, (required, optional) in _COMMAND_FIELDS.items()
            ),
        )
    )


def frames() -> str:
    return _block(
        _table(
            ("Example", "Frame"),
            (
                ("Fuzion halt", _hex(FUZION.command("ACHA"))),
                ("Fuzion left head 100", _hex(FUZION.command("ACTS", "left", "head", "100"))),
                (
                    "MCR flat, assigned addresses 1234 / 5678",
                    _hex(
                        codec.mcr(
                            command_type=66,
                            status=66,
                            function_code=21,
                            side=0,
                            payload=b"\x04\0",
                            client_address=0x1234,
                            sub_address=0x5678,
                        )
                    ),
                ),
            ),
        )
    )


BLOCKS: list[Block] = [
    ("docs/beds/sleep_number.md", "sleepiq-profiles", profiles),
    ("docs/beds/sleep_number.md", "sleepiq-frames", frames),
    ("docs/beds/sleep-number-services.md", "sleepiq-commands", commands),
    ("docs/beds/sleep-number-services.md", "sleepiq-mcr-commands", mcr_commands),
]
