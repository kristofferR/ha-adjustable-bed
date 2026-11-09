"""The single Bed Operation app profile over the Paramount P1 codec."""

from dataclasses import dataclass
from typing import Final

from ..codec import paramount as codec
from ..execution import ExecutionCapabilities


@dataclass(frozen=True, slots=True)
class ParamountProfile:
    key: str = "paramount"
    initial_delay_ms: int = 500
    response_delay_ms: int = 80
    press_delay_ms: int = 70
    response_timeout_ms: int = 500
    head_max: int = 75
    legs_max: int = 30
    execution: ExecutionCapabilities = ExecutionCapabilities(hold="stream")

    @property
    def frames(self) -> dict[str, bytes]:
        return {
            **{key: codec.control(value) for key, value in codec.OPERATIONS.items()},
            **{f"query_{code:02x}": codec.frame(code) for code in (0x81, 0x82, 0x83)},
            "registration": codec.frame(0x86, b"AUTH_REQ"),
        }


PARAMOUNT: Final = ParamountProfile()
PROFILES: Final = {PARAMOUNT.key: PARAMOUNT}
