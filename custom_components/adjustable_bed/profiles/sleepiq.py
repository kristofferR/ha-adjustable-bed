"""SleepIQ 5.4.11: generation selects Fuzion or the bound MCR UART route.

Hardware features come from live configuration, node and chamber replies.
The profile selects a format and its session timing, never device features.
"""

from dataclasses import dataclass
from typing import Final, Literal

from ..codec import sleepiq
from ..execution import NO_EXECUTION_CAPABILITIES, ExecutionCapabilities


@dataclass(frozen=True, slots=True)
class SleepIQProfile:
    key: Literal["fuzion", "mcr"]
    response_timeout: float
    write_timeout: float = 7.0
    response_retries: int = 0
    discovery_delay: float = 0.0
    execution: ExecutionCapabilities = NO_EXECUTION_CAPABILITIES

    def command(self, key: str, *args: str) -> bytes:
        if self.key != "fuzion":
            raise ValueError("Bamkeys require the Fuzion profile")
        return sleepiq.fuzion(f"{key} {' '.join(args)}")


FUZION: Final = SleepIQProfile("fuzion", 7.128)
MCR: Final = SleepIQProfile("mcr", 0.9, response_retries=3, discovery_delay=0.128)
