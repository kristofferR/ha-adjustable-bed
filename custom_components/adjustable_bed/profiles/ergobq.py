"""ErgoBQ 1.8.1 product5 aliases. Defaults are from this app only."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from ..codec import ergobq as codec
from ..execution import ExecutionCapabilities

PRODUCTS: Final = {
    "txbazdssmqcnndfc": "ErgoBQ BED (product c)",
    "txbazdssmqcnndfd": "ErgoBQ BED (product d)",
}
SERIAL: Final = "ergobq_serial"
STAMP: Final = "ergobq_stamp"
SCENES: Final = {
    "flat": 0,
    "tv": 1,
    "zero_g": 2,
    "sleep_aid": 3,
    "memory_1": 4,
    "memory_2": 5,
    "yoga": 6,
    "reading": 7,
}
MODES: Final = ("wave", "pulse", "continuous", "intermittent")
AXES: Final = {1: ("head", 65), 2: ("legs", 45), 3: ("motor_3", 35), 4: ("waist", 145)}


@dataclass(frozen=True, slots=True)
class ErgoBQProfile:
    key: str = "bed"
    execution: ExecutionCapabilities = ExecutionCapabilities(hold="latched")
    auth_timeout: float = 30
    metadata_timeout: float = 10
    unlink_timeout: float = 6
    response_timeout: float = 1
    write_timeout: float = 5
    attempts: int = 3
    retry_delay: float = 1
    notify_settle: float = 0.5


PROFILE: Final = ErgoBQProfile()


def motor_count(serial: str) -> int:
    if not serial.strip():
        return 2
    data = bytes.fromhex(serial.strip())
    if len(data) != 6:
        raise ValueError("Expected the six-byte manufacturer serial")
    return 4 if data[4] == 4 else 2


def product(service_data: bytes, name: str | None = None) -> str | None:
    if name == "MindLax":
        return None
    try:
        value = service_data[:16].decode("utf-8")
    except UnicodeDecodeError:
        return None
    return value if value in PRODUCTS else None


def validate_setup(data: Mapping[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    if data.get("product_type") not in PRODUCTS:
        errors["product_type"] = "ergobq_identity"
    try:
        motor_count(data.get(SERIAL, ""))
    except ValueError, TypeError:
        errors[SERIAL] = "ergobq_identity"
    try:
        codec.auth(data.get(STAMP, ""))
    except ValueError, AttributeError:
        errors[STAMP] = "ergobq_identity"
    return errors
