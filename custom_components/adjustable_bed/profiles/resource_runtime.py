"""App-owned rules for the shared resource-catalog BLE session runtime."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResourceRuntime:
    layouts: tuple[str, ...]
    side_layouts: frozenset[str]
    direct_alarm_layouts: frozenset[str]
    alarm_combinations: Mapping[int, tuple[int, int, int]]
    massage_popup: Mapping[int, int]
    poll_interval: Callable[..., int]
    startup_ms: int
    query_spacing_ms: int
    alarm_spacing_ms: int
    rgb_spacing_ms: int
    held_release_ms: int
    tap_release_ms: int
