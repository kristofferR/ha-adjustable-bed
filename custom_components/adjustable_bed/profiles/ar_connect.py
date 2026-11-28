"""AR Connect 3.2.2 source-proven native bed profile."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal, cast

from ..codec.linak import build_simultaneous_command, control_frame, custom_speed_frame

type Axis = Literal["back", "legs", "head", "feet"]


@dataclass(frozen=True, slots=True)
class ArConnectProfile:
    """Only source-checked native values; memory indices are not product capacity."""

    key: str = "ar_connect"
    control_service: str = "99fa0001-338a-1024-8a49-009c0215f78a"
    command_characteristic: str = "99fa0002-338a-1024-8a49-009c0215f78a"
    error_characteristic: str = "99fa0003-338a-1024-8a49-009c0215f78a"
    configuration_service: str = "99fa0010-338a-1024-8a49-009c0215f78a"
    configuration_characteristic: str = "99fa0011-338a-1024-8a49-009c0215f78a"
    reference_service: str = "99fa0020-338a-1024-8a49-009c0215f78a"
    reference_mask: str = "99fa0029-338a-1024-8a49-009c0215f78a"
    references: tuple[tuple[Axis, str], ...] = (
        ("head", "99fa0026-338a-1024-8a49-009c0215f78a"),
        ("back", "99fa0028-338a-1024-8a49-009c0215f78a"),
        ("legs", "99fa0027-338a-1024-8a49-009c0215f78a"),
        ("feet", "99fa0025-338a-1024-8a49-009c0215f78a"),
    )
    scan_timeout_ms: int = 300000
    axes: tuple[Axis, ...] = ("back", "legs", "head", "feet")
    pair_precedence: tuple[tuple[Axis, Axis], ...] = (
        ("legs", "back"),
        ("feet", "back"),
        ("head", "back"),
        ("feet", "legs"),
        ("head", "legs"),
        ("feet", "head"),
    )
    single_opcodes: tuple[int, ...] = (0x0A, 0x08, 0x02, 0x04)
    recall_opcodes: tuple[int, ...] = (0x0E, 0x0F, 0x0C, 0x44, 0x83, 0x84)
    save_opcodes: tuple[int, ...] = (0x38, 0x39, 0x3A, 0x45, 0x85, 0x86)
    # The bridge's stopBed action is WAKE_UP, distinct from empty-map STOP_MOVEMENT.
    stop_bed_opcode: int = 0xFE
    empty_map_opcode: int = 0xFF
    light_toggle_opcode: int = 0x94
    custom_speed_axes: tuple[tuple[str, int], ...] = (
        ("back", 0xDF),
        ("legs", 0xDE),
        ("feet", 0xDC),
        ("base", 0xDB),
    )
    custom_speed_post_write_ms: int = 100

    def movement(self, directions: Mapping[Axis, bool], *, slow: bool = False) -> bytes:
        """Select the native four-key map; True means up, absent means unselected."""
        if any(axis not in self.axes for axis in directions):
            raise ValueError("AR Connect native movement accepts back, legs, head or feet")
        if len(directions) == 4 and len(set(directions.values())) == 1:
            return control_frame(int(next(iter(directions.values()))), slow=slow)
        for first, second in self.pair_precedence:
            if first in directions and second in directions:
                opcode = build_simultaneous_command(
                    first, directions[first], second, directions[second]
                )[0]
                return control_frame(opcode, slow=slow)
        for axis, opcode in zip(self.axes, self.single_opcodes, strict=True):
            if axis in directions:
                return control_frame(opcode + directions[axis], slow=slow)
        return control_frame(self.empty_map_opcode, slow=slow)

    def custom_speed(
        self, speed_up: float, acceleration_up: float
    ) -> tuple[tuple[str, bytes], ...]:
        """Encode the native order only; HEAD is skipped and no I/O is performed."""
        return tuple(
            (axis, custom_speed_frame(opcode, speed_up, acceleration_up))
            for axis, opcode in self.custom_speed_axes
        )


AR_CONNECT: Final = ArConnectProfile()

# Runtime data from the independently accepted full contract. The native SDK's
# six indices remain above as kernel data; only these four recalls/three saves
# are reachable from the app's controls.
PRESETS: Final = {"television": 0, "zero_g": 1, "reading": 2, "favorite": 3}
SAVE_PRESETS: Final = frozenset({"television", "reading", "favorite"})
REFRESH_MS: Final = 400
DEBOUNCE_MS: Final = 200
IDLE_INITIAL_MS: Final = 1500
IDLE_AFTER_REFERENCE_MS: Final = 750
STARTUP_DELAY_S: Final = 0.7
STARTUP_SPEED_UP: Final = 1.0
STARTUP_ACCELERATION_UP: Final = 0.0
PROBE_DIRECTION_S: Final = 2.0
SIDE_DIRECTION_S: Final = 5.0
SIDE_GAP_S: Final = 0.5  # PP ja@4707a1 stores 500000 microseconds.
LAYOUTS: Final = {
    "back_legs": ("back", "legs"),
    "back_legs_head": ("back", "legs", "head"),
    "back_legs_feet": ("back", "legs", "feet"),
    "back_legs_head_feet": ("back", "legs", "head", "feet"),
}
LAYOUT_CHOICES: Final = {
    key: ", ".join(axis.capitalize() for axis in axes) for key, axes in LAYOUTS.items()
}
ROUTE_CHOICES: Final = {"native": "Adjustable bed", "headboard": "Headboard"}
NATIVE_REFERENCES: Final = (
    *AR_CONNECT.references,
    ("base", "99fa0024-338a-1024-8a49-009c0215f78a"),
)
NATIVE_SUBSCRIBE_ORDER: Final = ("back", "legs", "head", "feet", "base")
TIMER_SERVICE: Final = "99fa0050-338a-1024-8a49-009c0215f78a"
TIMER_EVENT: Final = "99fa0051-338a-1024-8a49-009c0215f78a"
NAME_CHARACTERISTIC: Final = "00002a00-0000-1000-8000-00805f9b34fb"


def peaceful_directions(positions: Mapping[str, float]) -> dict[Axis, bool]:
    result: dict[Axis, bool] = {}
    if positions.get("head", 0) > 0:
        result["head"] = False
    for axis, low, high in (("back", 297, 303), ("legs", 97, 103)):
        value = positions.get(axis)
        if value is not None:
            if value < low:
                result[cast(Axis, axis)] = True
            elif value > high:
                result[cast(Axis, axis)] = False
    if positions.get("feet", 0) < 0:
        result["feet"] = True
    return result
