"""Finite typed Richmat app actions. No arbitrary byte or opcode service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .protocol import BlanketSleep

OPERATIONS = (
    "sync",
    "detection",
    "toggle_alarm",
    "sleep_sync",
    "query",
    "single_alarm",
    "cancel_alarm",
    "repeat_alarm",
    "delete_alarm",
    "light_timer",
    "light_rgb",
    "strip_rgb",
    "strip_timer",
    "strip_groove",
    "strip_color_mode",
    "strip_breathe",
    "strip_power",
    "therapy_light",
    "therapy_sound",
    "therapy_timer",
    "music_source",
    "white_noise",
    "snore",
    "get_off_bed",
    "snore_intervention",
    "blanket_power",
    "blanket_mode",
    "blanket_temperature",
    "blanket_delay",
    "blanket_mite",
    "blanket_settings",
    "blanket_sleep",
    "usb",
    "demo",
    "sleep_time",
    "sleep_part",
    "sleep_realtime",
    "sleep_report",
    "sleep_snore",
    "sleep_sensitivity",
    "sleep_init",
    "sleep_cancel",
    "sleep_poll",
)


@dataclass(frozen=True, slots=True)
class DemoStep:
    action: str
    sustain: bool = False
    seconds: int = 0
    delay: int = 0


@dataclass(frozen=True, slots=True)
class Request:
    operation: str
    value: int = 0
    mode: int = 0
    enabled: bool = True
    rgb: tuple[int, int, int] = (255, 255, 255)
    opacity: int = 100
    zone: int = 1
    temperature: int = 25
    temperature_b: int = 25
    flags: tuple[bool, bool, bool, bool, bool, bool] | None = None
    sleep: BlanketSleep | None = None
    when: datetime | None = None
    action: str = ""
    alarm_id: int = 1
    weekdays: tuple[int, ...] = ()
    query: str = "alarms"
    steps: tuple[DemoStep, ...] = ()
    cycle: bool = False
    part: int = 1
    report_type: int = 1
