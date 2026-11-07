"""Typed direct-BLE posture and local-user actions for MotoMotion."""

from dataclasses import dataclass
from typing import Literal

from .codec.motomotion import Position


@dataclass(frozen=True)
class Request:
    operation: Literal[
        "save_user",
        "select_user",
        "delete_user",
        "recall",
        "save_posture",
        "reset_posture",
        "fine_tune",
    ]
    user: str | None = None
    dimensions: tuple[float, float, float] | None = None
    posture: str = "upright"
    targets: Position | None = None
