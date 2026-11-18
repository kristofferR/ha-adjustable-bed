"""One alarm request shape for every bed that stores its own wake alarm.

Each alarm-capable controller declares an :class:`AlarmCapability`. The shared
``set_alarm`` action checks a request against it on every target before any
write, then hands the controller one :class:`AlarmRequest`. The controller
turns that request into its own frames, so wire output stays per bed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

# Monday is index 0 everywhere in a request; controllers map to their own order.
WEEKDAYS: Final = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

# Every wake action a bed may offer. A capability lists the subset it accepts.
WAKE_ACTIONS: Final = (
    "none",
    "flat",
    "zero_g",
    "anti_snore",
    "lounge",
    "tv",
    "reading",
    "yoga",
    "memory_1",
    "memory_2",
    "memory_3",
    "memory_4",
    "memory_5",
    "custom_position",
    "massage",
    "head_massage",
    "foot_massage",
    "wave_massage",
    "light",
    "heat",
    "sleep_aid",
    "wake_mode_1",
    "wake_mode_2",
)

ALARM_SOUNDS: Final = (
    "none",
    "alarm",
    "music_1",
    "music_2",
    "music_3",
    "music_4",
    "music_5",
)

MASSAGE_ZONES: Final = ("head", "feet", "both", "wave")
MATTRESS_SIDES: Final = ("left", "right", "both")

# Request fields a capability must enable before a caller may set them.
OPTIONAL_FIELDS: Final = (
    "weekdays",
    "slot",
    "wake_action",
    "massage",
    "head_massage_level",
    "foot_massage_level",
    "massage_intensity",
    "massage_duration",
    "massage_zone",
    "mattress_side",
    "sound",
    "light",
    "confirm_custom_position",
)


@dataclass(frozen=True, slots=True, kw_only=True)
class AlarmCapability:
    """What one bed's alarm accepts.

    ``wake_actions``, ``sounds``, ``massage_durations`` and ``massage_zones``
    list the selectable choices, the first being the default. ``slots`` above one adds a slot choice. The remaining flags admit
    their request fields. ``cancel_running`` and ``resource`` say how the
    command is scheduled against other commands on the same bed.
    """

    wake_actions: tuple[str, ...] = ()
    weekdays: bool = False
    slots: int = 1
    massage: bool = False
    massage_levels: int = 0
    massage_intensities: int = 0
    massage_durations: tuple[int, ...] = ()
    massage_zones: tuple[str, ...] = ()
    # A vibrating mattress topper with its own alarm, per half.
    mattress_sides: tuple[str, ...] = ()
    sounds: tuple[str, ...] = ()
    light: bool = False
    # The bed refuses to turn an alarm on without an explicit wake action.
    requires_wake_action: bool = False
    # Wake actions that move to a user-saved position need explicit consent.
    confirm_actions: frozenset[str] = field(default_factory=frozenset)
    # Run ``check_alarm`` on every target over Bluetooth before the first write.
    live_check: bool = False
    cancel_running: bool = False
    resource: str | None = "configuration"

    def __post_init__(self) -> None:
        unknown = set(self.wake_actions).difference(WAKE_ACTIONS)
        unknown |= set(self.sounds).difference(ALARM_SOUNDS)
        unknown |= set(self.massage_zones).difference(MASSAGE_ZONES)
        if unknown:
            raise ValueError(f"Unknown alarm choices: {sorted(unknown)}")

    def accepts(self, name: str) -> bool:
        """Return whether a caller may set the optional request field ``name``."""
        return {
            "weekdays": self.weekdays,
            "slot": self.slots > 1,
            "wake_action": bool(self.wake_actions),
            "massage": self.massage,
            "head_massage_level": self.massage_levels > 0,
            "foot_massage_level": self.massage_levels > 0,
            "massage_intensity": self.massage_intensities > 0,
            "massage_duration": bool(self.massage_durations),
            "massage_zone": bool(self.massage_zones),
            "mattress_side": bool(self.mattress_sides),
            "sound": bool(self.sounds),
            "light": self.light,
            "confirm_custom_position": bool(self.confirm_actions),
        }[name]


@dataclass(frozen=True, slots=True, kw_only=True)
class AlarmRequest:
    """One validated alarm write; unset optional fields hold their defaults."""

    enabled: bool
    hour: int = 0
    minute: int = 0
    # Empty means the next occurrence of the time only.
    weekdays: tuple[int, ...] = ()
    slot: int = 1
    wake_action: str = "none"
    massage: bool = False
    head_massage_level: int = 0
    foot_massage_level: int = 0
    massage_intensity: int = 1
    massage_duration: int | None = None
    massage_zone: str | None = None
    # Set to target the mattress topper's alarm instead of the bed's.
    mattress_side: str | None = None
    sound: str = "none"
    light: bool = False
    confirm_custom_position: bool = False
    # Home Assistant local time, captured once for the whole call.
    reference_time: datetime

    @property
    def weekday_names(self) -> tuple[str, ...]:
        """Return the selected days as names, Monday first."""
        return tuple(WEEKDAYS[day] for day in self.weekdays)

    def minutes_until(self) -> int:
        """Return whole minutes from the call's minute to the next occurrence, 1 to 1440."""
        now = self.reference_time.hour * 60 + self.reference_time.minute
        return (self.hour * 60 + self.minute - now - 1) % 1440 + 1
