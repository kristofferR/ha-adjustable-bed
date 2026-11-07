"""Typed HJBed service requests; no arbitrary packet bytes or model inference."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Literal

Operation = Literal[
    "single",
    "cancel_single",
    "repeat",
    "delete",
    "query",
    "toggle",
    "sync",
    "light_timeout",
    "light_color",
    "mode",
]


@dataclass(frozen=True, slots=True)
class Request:
    operation: Operation
    action: str | None = None
    when: time | None = None
    alarm_id: int | None = None
    weekdays: tuple[int, ...] = ()
    enabled: bool = True
    seconds: int | None = None
    rgb: tuple[int, int, int] | None = None
    mode: Literal["split_head", "standard"] | None = None
