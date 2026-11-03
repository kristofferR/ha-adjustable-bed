"""HJBed stream order and bed state, independent of the BLE connection."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextvars import ContextVar
from copy import deepcopy

from .hjbed_receive import EventSink, Value, be, parse_frame

GESTURE_RELEASE: ContextVar[bool] = ContextVar("hjbed_gesture_release", default=False)


class NonProgressFrame(ValueError):
    """Reject the artifact's zero-length infinite loop without inventing a frame."""


class Stream:
    """Destructively split before dispatch; only success may arm a remainder timer."""

    def __init__(
        self, emit: EventSink, arm: Callable[[], None], cancel: Callable[[], None]
    ) -> None:
        self.buffer: list[int] = []
        self._emit, self._arm, self._cancel = emit, arm, cancel

    def clear(self) -> None:
        self._cancel()
        self.buffer.clear()

    def feed(self, values: Sequence[int]) -> None:
        self.buffer.extend(values)
        self._cancel()
        frames: list[list[int]] = []
        while len(self.buffer) >= 3:
            try:
                start = self.buffer.index(0x6E)
            except ValueError:
                self.buffer.clear()
                break
            del self.buffer[:start]
            if len(self.buffer) < 3:
                break
            kind = self.buffer[1]
            if kind in (0x20, 0x21):
                length = self.buffer[2]
            elif kind == 0x40:
                length = be(self.buffer, 2)
            else:
                try:
                    length = self.buffer.index(0x6E, 1)
                except ValueError:
                    length = len(self.buffer)
            if len(self.buffer) < length:
                break
            if length == 0:
                # Exact safety deviation: the app loops forever on this same
                # buffer. Clear only that nonprogress input; dispatch no frames.
                self.buffer.clear()
                raise NonProgressFrame("Zero-length HJBed frame rejected")
            frames.append(self.buffer[:length])
            del self.buffer[:length]
        for frame in frames:
            parse_frame(frame, _event_sink=self._emit)
        if self.buffer:
            self._arm()


class State:
    """Observed values and app consumers, with alarms retaining full bean equality."""

    def __init__(self) -> None:
        self.values: dict[str, Value] = {}
        self.alarms: list[dict[str, Value]] = []
        self.features: set[str] = set()
        self.pending_alarm: dict[str, Value] | None = None
        self.saved_alarm: dict[str, Value] | None = None
        self.last_event: str | None = None

    def accept(self, event: str, value: Value) -> None:
        self.last_event = event
        self.values[event] = deepcopy(value)
        features = {
            "deviceCharacteristicsSubscriptionClockEvent": "alarm",
            "deviceCharacteristicsSubscriptionLightEvent": "light",
            "deviceCharacteristicsSubscriptionMusicEvent": "music",
        }
        if event in features:
            self.features.add(features[event])
        if event == "deviceRepeatAlarmListStatusEvent" and isinstance(value, dict):
            if value not in self.alarms:
                self.alarms.append(deepcopy(value))
        if event == "deviceRepeatAlarmListEscalationStatusEvent" and isinstance(value, dict):
            old = next(
                (row for row in self.alarms if row.get("number") == value.get("number")), None
            )
            if old is not None:
                self.alarms.insert(self.alarms.index(old), deepcopy(value))
                self.alarms.remove(old)
        if event == "deviceAddAlarmSuccessEvent" and self.pending_alarm is not None:
            self.saved_alarm = deepcopy(self.pending_alarm)
            self.pending_alarm = None
        if event == "deviceCancelAlarmSuccessEvent":
            self.saved_alarm = None
            self.pending_alarm = None
