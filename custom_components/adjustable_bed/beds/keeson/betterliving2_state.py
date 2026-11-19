"""BetterLiving2's field projections and separate, stateful P1 alarm consumer."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ...profiles.betterliving2 import Protocol


def signed(value: int) -> int:
    return value if value < 128 else value - 256


@dataclass(frozen=True, slots=True)
class AlarmView:
    """App selection/preferences, never an assertion of physical alarm state."""

    switch_selected: bool = False
    controls_enabled: bool = True
    hour: int | None = None
    minute: int | None = None
    massage: bool = False
    memory_a: bool = False
    memory_b: bool = False
    weeks: tuple[int, ...] = ()


def restore_actions(massage: bool, memory_a: bool, memory_b: bool) -> tuple[bool, bool, bool]:
    """doSomething priority; normalized-zero notifications do not call this."""
    return massage, memory_a and not massage, memory_b and not massage and not memory_a


def consume_p1(data: bytes, prior: AlarmView, saved: AlarmView) -> tuple[AlarmView, AlarmView]:
    if len(data) < 10:
        return prior, saved
    minute = 0 if data[3] == 255 else signed(data[3])
    hour = 0 if data[4] == 255 else signed(data[4])
    if not 0 <= minute <= 60 or not 0 <= hour <= 24:
        return prior, saved
    week = 0 if data[6] == 255 else data[6]
    if not week:
        if prior.switch_selected:
            return prior, saved
        return replace(
            prior,
            controls_enabled=True,
            hour=saved.hour,
            minute=saved.minute,
            massage=saved.massage,
            memory_a=saved.memory_a,
            memory_b=saved.memory_b,
        ), saved
    weeks = tuple(day for day in range(7) if week & 128 and week & (1 << day))
    massage, memory_a, memory_b = data[7] == data[8] == 17, data[9] == 248, data[9] == 249
    return (
        replace(
            prior,
            switch_selected=True,
            controls_enabled=False,
            hour=hour,
            minute=minute,
            massage=massage,
            memory_a=memory_a,
            memory_b=memory_b,
            weeks=weeks,
        ),
        replace(
            saved,
            switch_selected=True,
            hour=hour,
            minute=minute,
            massage=massage,
            memory_a=memory_a,
            memory_b=memory_b,
            weeks=weeks,
        ),
    )


@dataclass(frozen=True, slots=True)
class AlarmFields:
    hour: int
    minute: int
    week: int
    enabled: bool
    kind: int
    massage: bool = False
    memory: int = 0
    stop_driver_side_effect: bool = False


def alarm_fields(protocol: Protocol, data: bytes) -> AlarmFields | None:
    """Raw projection. P1.enabled is explicitly not the consumer transition."""
    if protocol == "P1":
        if len(data) < 10:
            return None
        hour = 0 if data[4] == 255 else signed(data[4])
        minute = 0 if data[3] == 255 else signed(data[3])
        if not 0 <= hour <= 24 or not 0 <= minute <= 60:
            return None
        week = 0 if data[6] == 255 else data[6]
        return AlarmFields(
            hour,
            minute,
            week,
            bool(week),
            data[9],
            data[7] == data[8] == 17,
            {248: 1, 249: 2}.get(data[9], 0),
        )
    if protocol == "P2" and len(data) >= 7 and data[:3] == b"\xed\x80\x03":
        hour, minute, week, kind = data[3:7]
        return AlarmFields(
            hour,
            minute,
            week,
            bool(hour or minute or week),
            kind,
            kind == 9,
            {17: 1, 19: 2}.get(kind, 0),
            True,
        )
    if protocol == "P3" and len(data) >= 10 and data[:2] == b"\xa5\x0c":
        return AlarmFields(
            data[6],
            data[7],
            data[4],
            bool(data[9]),
            data[5],
            data[5] == 8,
            {5: 1, 6: 2}.get(data[5], 0),
            True,
        )
    return None


@dataclass(frozen=True, slots=True)
class MassageFields:
    timer_level: int
    wave: int
    head_level: int
    foot_level: int

    @property
    def enabled(self) -> bool:
        return self.head_level > 0 or self.foot_level > 0


def massage_fields(protocol: Protocol, data: bytes) -> MassageFields | None:
    if protocol == "P2" and len(data) == 16:
        return MassageFields(
            min(data[14] & 15, 4),
            signed(data[14]) >> 4,
            ((data[7] & 15) + 1) // 2,
            ((data[8] & 15) + 1) // 2,
        )
    if protocol == "P3" and len(data) >= 9:
        timer = signed(data[4])
        # int division truncates toward zero in Java, unlike Python //.
        return MassageFields(
            0 if timer <= 0 else 1 if timer <= 2 else 2 if timer <= 4 else 3,
            signed(data[6]),
            int((signed(data[7]) + 1) / 2),
            int((signed(data[8]) + 1) / 2),
        )
    return None
