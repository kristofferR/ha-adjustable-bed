#!/usr/bin/env python3
"""Capture the BLE traffic every bed controller produces for a fixed command plan.

Purpose: refactors of a protocol family (v5 protocol split, #742) must keep the
wire output unchanged. This tool builds each bed type and route through the real
``create_controller`` factory, drives a command plan against a recording BLE
client and writes the result as a deterministic JSON snapshot.
``tests/test_wire_snapshot.py`` fails when a fresh capture differs from it.

Recorded per event: characteristic UUID, kind, payload (hex), order and virtual
time. The kind is the ``response`` flag (``true``/``false``/``null``) for a GATT
write, or ``notify``, ``unnotify``, ``read`` or ``pair``. Consecutive identical
events with a constant spacing collapse into one run:
``[t_ms, char, kind, hex, count, interval_ms]``.

Usage::

    uv run --no-sync python scripts/wire_snapshot.py             # rewrite snapshot
    uv run --no-sync python scripts/wire_snapshot.py --check     # diff against it
    uv run --no-sync python scripts/wire_snapshot.py --list      # list scenarios

A deliberate wire change (a bug fix) regenerates the snapshot in the same PR so
the diff is reviewed. A pure refactor must leave it untouched.

How it works, and where it stops:

- The coordinator is a stub owned by this script. Pulse count and delay come from
  ``get_motor_pulse_defaults(bed_type, variant)``, as the real coordinator does.
  Controllers are driven directly, so cover-level hold loops are not exercised.
  Every command ends by itself within ``HOLD_CAP_S`` of virtual time or is
  released then, like a STOP request.
- Time is virtual: ``asyncio.sleep``/``wait``/``wait_for``/``timeout``/
  ``timeout_at``, the loop clock and ``call_later`` run on a fake clock that only
  advances once runnable work has gone quiet. Wall-clock time is frozen to follow
  it. A command still running after ``COMMAND_BUDGET_S`` of virtual time is
  recorded as ``timeout``. Nothing depends on real time or CPU speed.
- The command plan: every motor axis, the standard presets, every memory slot up
  to ``memory_slot_count``, lights and massage, then one representative call of
  every other implemented ``BedController`` action (each option of option-taking
  ones), every controller-declared button, select option and number bound, and a
  STOP pressed partway through each cover movement. See ``plan_commands``.
- Each scenario replays a hand-maintained fake GATT layout from
  ``wire_snapshot_layouts.json``, so renaming a UUID constant changes nothing. A
  new scenario needs a layout there (another scenario's through ``layout_id``).
- A command the controller declares (through its capability properties, motor
  specs or entity specs) that does not succeed is listed in the scenario's
  ``gaps``. Every event it did record stays in the snapshot, whatever its status.
- ``--check`` also captures with a second hash seed and fails on any difference
  outside ``SEED_DEPENDENT``.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import contextvars
import dataclasses
import datetime
import difflib
import inspect
import json
import logging
import os
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

REPO_ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = REPO_ROOT / "tests" / "fixtures" / "wire_snapshot.json"
LAYOUTS_PATH = REPO_ROOT / "tests" / "fixtures" / "wire_snapshot_layouts.json"
SCHEMA_VERSION = 3

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Held in a tuple so freezegun, which patches module attributes, leaves it real.
_REAL_CLOCK = (time.perf_counter,)

# A held command (one that repeats until STOP) is stopped after this much virtual time.
# Long enough for every bounded preset and recall to finish on its own.
HOLD_CAP_S = 50.0
# Virtual time a command or the connect hooks may take before counting as stuck.
COMMAND_BUDGET_S = 60.0
# Consecutive yields without activity (a task created, an event recorded, a sleeper
# registered) before a sleeper may advance virtual time, and the same for a timeout.
SETTLE_YIELDS = 20
TIMEOUT_SETTLE_YIELDS = 200
# Hard cap on yields per settle, so a body that never goes quiet cannot hang a capture.
MAX_SETTLE_YIELDS = 20000
# Every stubbed GATT write takes this long, so pacing that absorbs write latency and
# pacing that adds to it land at different offsets.
WRITE_DURATION_S = 0.007
# Virtual time a scenario keeps running after its last command, so delayed work the
# final command scheduled (a follow-up write, a retry) is captured before cleanup.
DRAIN_WINDOW_S = 2.0
# Tasks inherit the phase that created them, so an event caused later by a task from
# an earlier phase (a delayed retry, a keepalive) is recorded as background.
PHASE: contextvars.ContextVar[int] = contextvars.ContextVar("wire_snapshot_phase", default=0)

FROZEN_NOW = "2026-01-02 03:04:05"
FROZEN_BASE = datetime.datetime.fromisoformat(FROZEN_NOW)

MOTORS: tuple[str, ...] = (
    "head",
    "back",
    "legs",
    "feet",
    "lumbar",
    "neck",
    "pillow",
    "tilt",
    "hip",
    "bed_height",
)

# ---------------------------------------------------------------------------
# Command plan
# ---------------------------------------------------------------------------

# Capability flag declaring a no-argument action, where the integration has one.
ACTION_FLAGS: dict[str, str] = {
    "stop_all": "supports_stop_all",
    "preset_flat": "supports_preset_flat",
    "preset_zero_g": "supports_preset_zero_g",
    "preset_anti_snore": "supports_preset_anti_snore",
    "preset_tv": "supports_preset_tv",
    "preset_reading": "supports_preset_reading",
    "preset_yoga": "supports_preset_yoga",
    "preset_both_up": "supports_preset_both_up",
    "preset_relaxing_bedtime": "supports_relaxing_bedtime",
    "lights_toggle": "supports_light_toggle_control",
    "lights_on": "supports_discrete_light_control",
    "lights_off": "supports_discrete_light_control",
    "underbed_lights_on": "supports_under_bed_lights",
    "underbed_lights_off": "supports_under_bed_lights",
    "underbed_lights_toggle": "supports_under_bed_lights",
    "massage_off": "supports_massage_off_control",
    "massage_toggle": "supports_massage_toggle_control",
    "massage_head_toggle": "supports_head_massage_toggle_control",
    "massage_foot_toggle": "supports_foot_massage_toggle_control",
    "massage_intensity_up": "supports_massage_intensity_up_control",
    "massage_head_up": "supports_head_massage_intensity_step_control",
    "massage_head_down": "supports_head_massage_intensity_step_control",
    "massage_foot_up": "supports_foot_massage_intensity_step_control",
    "massage_foot_down": "supports_foot_massage_intensity_step_control",
    "massage_mode_step": "supports_massage_mode_step_control",
    "massage_wave_next": "supports_massage_wave_direction_control",
    "massage_wave_previous": "supports_massage_wave_direction_control",
    "massage_wave_frequency_up": "supports_massage_wave_frequency_control",
    "massage_wave_frequency_down": "supports_massage_wave_frequency_control",
    "massage_circulation_full_body": "supports_circulation_massage",
    "massage_circulation_head": "supports_circulation_massage",
    "massage_circulation_hip": "supports_circulation_massage",
    "massage_circulation_leg": "supports_circulation_massage",
    "child_lock_toggle": "supports_child_lock",
    "impulse_toggle": "supports_impulse_control",
    "sync_clock": "supports_clock_sync",
    "set_control_mode_press_and_hold": "supports_control_mode_configuration",
    "set_control_mode_press_and_release": "supports_control_mode_configuration",
    "cancel_sleep_timer": "supports_sleep_timer",
    "cancel_alarm_timer": "supports_alarm_timer",
    "wake": "supports_wake_control",
    "stop_wake_routine": "supports_wake_routine",
    "reset_defaults": "supports_reset_defaults",
    "factory_reset": "supports_factory_reset",
    "solace_music_toggle": "supports_solace_audio",
    "solace_music_off": "supports_solace_audio",
    "solace_query_audio_volume": "supports_solace_audio",
    "rmcontrol_query_alarms": "supports_rmcontrol_alarm",
    "rmcontrol_query_anti_snore": "supports_rmcontrol_anti_snore",
}

# No-argument base methods that are connection plumbing, not user actions.
NOT_ACTIONS = frozenset(
    {
        "async_discover_capabilities",
        "start_notify",
        "stop_notify",
        "read_bed_presence_cached",
        "async_validate_linked_readiness",
        "async_refresh_auth",
        "async_resume_session",
        "stop_keepalive",
    }
)

# Actions declared on BedController after this plan was frozen. They run last,
# after every other command, so the rows before them keep their virtual timing.
LATE_ACTIONS = frozenset(
    {
        "auxiliary_action",
        "preset_incline",
        "preset_lounge",
        "preset_swing",
        "turn_footwarming_off",
        "turn_footwarming_on",
        "turn_thermal_off",
        "turn_thermal_on",
    }
)

# No-argument actions that moved from BedController to their family's controller
# after this plan was frozen. They keep their place in the name-ordered plan.
FAMILY_ACTIONS = frozenset(
    {
        "cancel_alarm_timer",
        "cancel_sleep_timer",
        "preset_yoga",
        "rmcontrol_query_alarms",
        "rmcontrol_query_anti_snore",
        "solace_music_off",
        "solace_music_toggle",
        "solace_query_audio_volume",
    }
)

Call = Callable[[Any], Awaitable[Any]]


@dataclass(frozen=True)
class Command:
    name: str
    call: Call
    # Whether the controller declares the command (a capability property or a
    # motor spec says the integration exposes it). A declared command that fails,
    # or a declared movement that writes nothing, is a coverage gap.
    declared: bool = False
    movement: bool = False

    def is_gap(self, status: str) -> bool:
        if not self.declared:
            return False
        return status != "ok" if self.movement else status not in {"ok", "no_writes"}


def _overrides(controller: Any, method: str) -> bool:
    from custom_components.adjustable_bed.beds.base import BedController

    impl = getattr(type(controller), method, None)
    return impl is not None and impl is not getattr(BedController, method, None)


def _flag(controller: Any, name: str | None) -> bool:
    if name is None:
        return False
    try:
        return bool(getattr(controller, name))
    except Exception:  # noqa: BLE001 - a property that cannot answer declares nothing
        return False


def _value(controller: Any, name: str, default: Any) -> Any:
    try:
        return getattr(controller, name)
    except Exception:  # noqa: BLE001
        return default


def _method(name: str, *args: Any, **kwargs: Any) -> Call:
    return lambda ctrl: getattr(ctrl, name)(*args, **kwargs)


# Virtual time into a movement at which the user presses STOP.
STOP_AFTER_S = 0.3


def _stopped(call: Call) -> Call:
    """Run a movement and STOP it after ``STOP_AFTER_S``, as ``async_stop_command`` does.

    The coordinator bumps the cancel counter, sets ``cancel_command``, waits for the
    running command's cleanup to release the wire, then sends ``stop_all``.
    """

    async def run(ctrl: Any) -> None:
        coordinator = ctrl._coordinator  # noqa: SLF001
        movement = asyncio.ensure_future(call(ctrl))
        await asyncio.sleep(STOP_AFTER_S)
        coordinator._cancel_counter += 1  # noqa: SLF001
        coordinator.cancel_command.set()
        await asyncio.gather(movement, return_exceptions=True)
        await ctrl.stop_all()

    return run


def _base_actions() -> list[str]:
    """Public no-argument actions of ``BedController``, in name order."""
    from custom_components.adjustable_bed.beds.base import BedController

    names = []
    for name, fn in inspect.getmembers(BedController, inspect.iscoroutinefunction):
        params = list(inspect.signature(fn).parameters.values())[1:]
        if name.startswith("_") or name in NOT_ACTIONS | LATE_ACTIONS:
            continue
        if all(p.default is not inspect.Parameter.empty for p in params):
            names.append(name)
    return sorted({*names, *FAMILY_ACTIONS})


def plan_commands(controller: Any) -> list[Command]:
    """The command plan for one controller.

    The first block keeps the order of the original plan so earlier captures stay
    comparable; everything after it only adds coverage.
    """
    slots = max(int(_value(controller, "memory_slot_count", 0) or 0), 1)
    specs: tuple[Any, ...] = ()
    if _flag(controller, "supports_motor_control") and not _flag(
        controller, "has_discrete_motor_control"
    ):
        specs = tuple(_value(controller, "motor_control_specs", ()))

    plan: list[Command] = []
    for motor in MOTORS:
        for action in ("up", "down", "stop"):
            plan.append(Command(f"{motor}_{action}", _method(f"move_{motor}_{action}")))
    for name in ("stop_all", "preset_flat", "preset_zero_g", "preset_anti_snore", "preset_tv"):
        plan.append(Command(name, _method(name), _flag(controller, ACTION_FLAGS[name])))
    plan.append(
        Command(
            "memory_recall_1",
            _method("preset_memory", 1),
            _flag(controller, "supports_memory_presets"),
        )
    )
    plan.append(
        Command(
            "memory_program_1",
            _method("program_memory", 1),
            _flag(controller, "supports_memory_programming"),
        )
    )
    for name in ("lights_toggle", "lights_on", "lights_off", "massage_toggle", "massage_off"):
        plan.append(Command(name, _method(name), _flag(controller, ACTION_FLAGS.get(name))))

    # Added coverage: further memory slots, other actions and controller specs.
    for slot in range(2, slots + 1):
        plan.append(
            Command(
                f"memory_program_{slot}",
                _method("program_memory", slot),
                _flag(controller, "supports_memory_programming"),
            )
        )
        plan.append(
            Command(
                f"memory_recall_{slot}",
                _method("preset_memory", slot),
                _flag(controller, "supports_memory_presets"),
            )
        )
    if _flag(controller, "supports_held_memory_recall"):
        for slot in range(1, slots + 1):
            plan.append(
                Command(f"recall_memory_{slot}", _method("recall_memory", slot, hold_ms=1000), True)
            )
    # The cover entities the integration creates, through their own callables.
    for spec in specs:
        plan.append(Command(f"cover:{spec.key}_open", spec.open_fn, True, movement=True))
        plan.append(Command(f"cover:{spec.key}_close", spec.close_fn, True, movement=True))
        plan.append(Command(f"cover:{spec.key}_stop", spec.stop_fn, True))
    done = {c.name for c in plan} | {
        f"move_{m}_{a}" for m in MOTORS for a in ("up", "down", "stop")
    }
    done |= {"preset_memory", "program_memory"}
    for name in _base_actions():
        if name not in done and _overrides(controller, name):
            plan.append(Command(name, _method(name), _flag(controller, ACTION_FLAGS.get(name))))
    plan.extend(_argument_commands(controller))
    # The user presses STOP while each cover moves.
    for spec in specs:
        plan.append(Command(f"stop:{spec.key}_open", _stopped(spec.open_fn), True, movement=True))
        plan.append(Command(f"stop:{spec.key}_close", _stopped(spec.close_fn), True, movement=True))
    for spec in _value(controller, "controller_button_specs", ()):
        plan.append(Command(f"button:{spec.key}", spec.press_fn, True))
    for spec in _value(controller, "controller_select_specs", ()):
        for option in spec.options:
            plan.append(
                Command(
                    f"select:{spec.key}={option}",
                    lambda ctrl, fn=spec.select_fn, o=option: fn(ctrl, o),
                    True,
                )
            )
    for spec in _value(controller, "controller_number_specs", ()):
        for bound in dict.fromkeys((spec.native_min_value, spec.native_max_value)):
            plan.append(
                Command(
                    f"number:{spec.key}={bound:g}",
                    lambda ctrl, fn=spec.set_fn, v=bound: fn(ctrl, v),
                    True,
                )
            )
    for name in sorted(LATE_ACTIONS):
        if _overrides(controller, name):
            plan.append(Command(name, _method(name), _flag(controller, ACTION_FLAGS.get(name))))
    return plan


def _argument_commands(controller: Any) -> list[Command]:
    """One representative call of each implemented action that takes arguments."""
    c = controller
    out: list[Command] = []

    def add(
        flag: str | bool | None, method: str, name: str, *args: Any, **kwargs: Any
    ) -> None:
        if not _overrides(c, method):
            return
        declared = flag if isinstance(flag, bool) else _flag(c, flag) if flag else False
        out.append(Command(name, _method(method, *args, **kwargs), declared))

    if _flag(c, "supports_light_level_control"):
        low, high = int(_value(c, "light_level_min", 0)), int(_value(c, "light_level_max", 10))
        mid = (low + high) // 2
        levels = (
            range(low, high + 1)
            if high - low <= 20
            else sorted({low, low + 1, mid - 1, mid, mid + 1, high - 1, high})
        )
        for level in levels:
            add("supports_light_level_control", "set_light_level", f"light_level_{level}", level)
    add("supports_light_color_control", "set_light_color", "light_color", (255, 128, 0))
    add(
        "supports_light_color_control",
        "set_light_color_rgbw",
        "light_color_rgbw",
        (255, 128, 0, 64),
    )
    for option in _value(c, "light_timer_options", []) if _flag(c, "supports_light_timer") else []:
        add("supports_light_timer", "set_light_timer", f"light_timer_{option}", option)
    if _flag(c, "supports_massage_intensity_control"):
        top = int(_value(c, "massage_intensity_max", 10))
        for zone in _value(c, "massage_intensity_zones", []):
            for level in range(top + 1):
                add(
                    "supports_massage_intensity_control",
                    "set_massage_intensity",
                    f"massage_{zone}_{level}",
                    zone,
                    level,
                )
    if _flag(c, "supports_massage_intensity_preset_control"):
        for level in (1, 2, 3):
            add(
                "supports_massage_intensity_preset_control",
                "set_massage_intensity_preset",
                f"massage_preset_{level}",
                level,
            )
    for minutes in (
        _value(c, "massage_timer_options", []) if _flag(c, "supports_massage_timer") else []
    ):
        add("supports_massage_timer", "set_massage_timer", f"massage_timer_{minutes}", minutes)
    if _flag(c, "supports_fan_level_control"):
        for level in range(int(_value(c, "fan_level_max", 0)) + 1):
            add("supports_fan_level_control", "set_fan_level", f"fan_level_{level}", level)
    if _flag(c, "supports_sleep_timer"):
        durations = _value(c, "sleep_timer_duration_options", ()) or (30,)
        memories = _value(c, "sleep_timer_memory_options", ()) or (1,)
        add("supports_sleep_timer", "set_sleep_timer", "sleep_timer", durations[0], memories[0])
    add("supports_alarm_timer", "set_alarm_timer", "alarm_timer_30", 30)
    for spec in (
        _value(c, "position_number_specs", ())
        if _flag(c, "supports_direct_position_control")
        else ()
    ):
        target = round(spec.native_max_value / 2)
        add(
            "supports_direct_position_control",
            "set_motor_position",
            f"position_{spec.position_key}_{target}",
            spec.position_key,
            target,
        )
    add(
        "supports_simultaneous_movement",
        "move_simultaneously",
        "move_back_legs_up",
        "back",
        True,
        "legs",
        True,
    )
    for control in (
        _value(c, "held_control_options", ()) if _flag(c, "supports_held_control") else ()
    ):
        add("supports_held_control", "hold_control", f"hold_{control}", control, 1000)
    for preset in _value(c, "held_preset_options", ()) if _flag(c, "supports_preset_hold") else ():
        add("supports_preset_hold", "hold_preset", f"hold_preset_{preset}", preset, 1000)
    if _flag(c, "supports_wake_routine"):
        presets = _value(c, "clock_alarm_preset_options", ()) or ("flat",)
        add("supports_wake_routine", "execute_wake_routine", "wake_routine", preset=presets[0])
    for flag, method in (
        ("supports_sync", "set_synchro"),
        ("supports_remote_control_lock", "set_remote_control_lock"),
        ("supports_automatic_drive", "set_automatic_drive"),
        ("supports_automatic_light", "set_automatic_light"),
        ("supports_rmcontrol_anti_snore", "rmcontrol_anti_snore_switch"),
    ):
        add(flag, method, f"{method}_on", True)
        add(flag, method, f"{method}_off", False)
    add(
        "supports_rmcontrol_anti_snore",
        "rmcontrol_anti_snore_config",
        "anti_snore_count",
        "count",
        3,
    )
    add("supports_rmcontrol_single_alarm", "rmcontrol_single_alarm", "rmcontrol_alarm_30", 30, None)
    add("supports_rmcontrol_alarm", "rmcontrol_delete_alarm", "rmcontrol_delete_alarm_1", 1)
    add(
        "supports_rmcontrol_alarm_time_sync",
        "rmcontrol_sync_alarm_time",
        "rmcontrol_sync_alarm_time",
        FROZEN_BASE,
    )
    add("supports_solace_audio", "solace_select_music", "solace_music_1", 1)
    add("supports_solace_audio", "solace_set_audio_volume", "solace_volume_5", 5)
    # Only the FSM Relax family implements confirmed calibration.
    add(True, "calibrate", "calibrate", confirmed=True)
    add("supports_device_rename", "rename_device", "rename_device", "Bed")
    add(None, "set_furnimove_massage_program", "furnimove_massage_program_1", 1)
    return out


# ---------------------------------------------------------------------------
# Virtual time
# ---------------------------------------------------------------------------


class FakeClock:
    """Virtual time, advanced only to the earliest pending sleep deadline.

    Wall-clock time (``datetime``, ``time.monotonic``) is frozen by freezegun and
    moved to ``FROZEN_BASE + now`` whenever the virtual clock advances, so
    controllers that compute deadlines from either clock see the same elapsed time.
    """

    def __init__(self, frozen: Any = None) -> None:
        self.now = 0.0
        self.origin = 0.0
        self.sleepers: list[float] = []
        self.phase = 0
        # Bumped by every observable step of runnable work; see ``virtual_time``.
        self.activity = 0
        self._frozen = frozen
        if frozen is not None:
            frozen.move_to(FROZEN_BASE)

    def begin_phase(self) -> None:
        """Start a capture phase: event offsets count from here."""
        self.origin = self.now
        self.phase += 1
        PHASE.set(self.phase)

    @property
    def elapsed(self) -> float:
        return self.now - self.origin

    def advance_to(self, deadline: float) -> None:
        # Advancing is activity: other waiters must let the woken task run first.
        self.activity += 1
        self.now = max(self.now, deadline)
        if self._frozen is not None:
            self._frozen.move_to(FROZEN_BASE + datetime.timedelta(seconds=self.now))

    def time(self) -> float:
        return self.now


class _VirtualHandle:
    """``TimerHandle`` stand-in for a virtual ``call_later``."""

    def __init__(self, task: asyncio.Task[None], when: float) -> None:
        self._task = task
        self._when = when

    def cancel(self) -> None:
        self._task.cancel()

    def cancelled(self) -> bool:
        return self._task.cancelled()

    def when(self) -> float:
        return self._when


class _LoopProxy:
    """Real running loop with its clock and timers answered by the fake clock."""

    def __init__(self, loop: asyncio.AbstractEventLoop, clock: FakeClock) -> None:
        self._loop = loop
        self._clock = clock

    def time(self) -> float:
        return self._clock.time()

    def call_at(self, when: float, callback: Callable[..., Any], *args: Any, **_: Any) -> Any:
        async def fire() -> None:
            await asyncio.sleep(when - self._clock.now)
            callback(*args)

        return _VirtualHandle(asyncio.ensure_future(fire()), when)

    def call_later(self, delay: float, callback: Callable[..., Any], *args: Any, **_: Any) -> Any:
        return self.call_at(self._clock.now + delay, callback, *args)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._loop, name)


@contextlib.contextmanager
def virtual_time(clock: FakeClock) -> Iterator[None]:
    """Run ``asyncio`` timing on the fake clock for the duration of the block."""
    real = {
        name: getattr(asyncio, name)
        for name in ("sleep", "wait", "wait_for", "timeout", "timeout_at", "get_running_loop")
    }
    real_sleep, real_wait = real["sleep"], real["wait"]

    async def settle(quiet: int, stop: Callable[[], bool] = lambda: False) -> None:
        """Yield until ``quiet`` consecutive yields saw no new activity, or ``stop()``."""
        seen, still = -1, 0
        for _ in range(MAX_SETTLE_YIELDS):
            await real_sleep(0)
            if stop():
                return
            if clock.activity == seen:
                still += 1
                if still >= quiet:
                    return
            else:
                seen, still = clock.activity, 0

    async def wait_until(deadline: float, quiet: int, stop: Callable[[], bool]) -> bool:
        """Wait until ``deadline`` is the earliest pending one; False if ``stop()`` first."""
        clock.sleepers.append(deadline)
        clock.activity += 1
        try:
            while not stop():
                await settle(quiet, stop)
                if not stop() and deadline <= min(clock.sleepers):
                    clock.advance_to(deadline)
                    return True
            return False
        finally:
            clock.sleepers.remove(deadline)
            clock.activity += 1

    async def fake_sleep(delay: float, result: Any = None) -> Any:
        await wait_until(clock.now + max(delay, 0), SETTLE_YIELDS, lambda: False)
        return result

    class FakeTimeout:
        """``asyncio.timeout_at`` that fires once its virtual deadline is the earliest."""

        def __init__(self, when: float | None) -> None:
            self._when = when
            self._task: asyncio.Task[Any] | None = None
            self._guard: asyncio.Task[None] | None = None
            self._expired = False

        def expired(self) -> bool:
            return self._expired

        def when(self) -> float | None:
            return self._when

        def reschedule(self, when: float | None) -> None:
            """Move the virtual deadline, as ``asyncio.Timeout.reschedule`` does."""
            if self._guard is not None:
                self._guard.cancel()
                self._guard = None
            self._when = when
            if when is not None and self._task is not None:
                self._guard = asyncio.ensure_future(self._expire(when))

        async def _expire(self, deadline: float) -> None:
            await wait_until(deadline, TIMEOUT_SETTLE_YIELDS, lambda: False)
            self._expired = True
            assert self._task is not None
            self._task.cancel()

        async def __aenter__(self) -> FakeTimeout:
            # Captured even without a deadline, so a later reschedule can expire it.
            self._task = asyncio.current_task()
            if self._when is not None:
                self._guard = asyncio.ensure_future(self._expire(self._when))
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> bool | None:
            if self._guard is not None:
                self._guard.cancel()
            if self._expired and exc_type is asyncio.CancelledError:
                self._task.uncancel()  # type: ignore[union-attr]
                raise TimeoutError from exc
            return None

    def fake_timeout(delay: float | None) -> FakeTimeout:
        return FakeTimeout(None if delay is None else clock.now + delay)

    async def fake_wait_for(awaitable: Any, timeout: float | None) -> Any:
        # The wait ends at its virtual deadline once no earlier sleeper is pending, and
        # only after the cancelled awaitable finished its cleanup.
        if timeout is None:
            return await awaitable
        task = asyncio.ensure_future(awaitable)
        try:
            expired = await wait_until(clock.now + timeout, TIMEOUT_SETTLE_YIELDS, task.done)
        except asyncio.CancelledError:
            task.cancel()
            raise
        if not expired:
            return task.result()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        raise TimeoutError

    async def fake_wait(
        fs: Any, *, timeout: float | None = None, return_when: str = asyncio.ALL_COMPLETED
    ) -> tuple[set[Any], set[Any]]:
        futures = set(fs)
        if timeout is None:
            return await real_wait(futures, return_when=return_when)

        def finished() -> bool:
            done = [f for f in futures if f.done()]
            if return_when == asyncio.FIRST_COMPLETED:
                return bool(done)
            if return_when == asyncio.FIRST_EXCEPTION and any(
                not f.cancelled() and f.exception() is not None for f in done
            ):
                return True
            return len(done) == len(futures)

        await wait_until(clock.now + timeout, TIMEOUT_SETTLE_YIELDS, finished)
        return {f for f in futures if f.done()}, {f for f in futures if not f.done()}

    loop = real["get_running_loop"]()
    previous_factory = loop.get_task_factory()

    def counting_factory(loop: asyncio.AbstractEventLoop, coro: Any, **kwargs: Any) -> Any:
        clock.activity += 1
        if previous_factory is not None:
            return previous_factory(loop, coro, **kwargs)
        return asyncio.Task(coro, loop=loop, **kwargs)

    proxy = _LoopProxy(loop, clock)
    loop.set_task_factory(counting_factory)
    asyncio.sleep = fake_sleep  # type: ignore[assignment]
    asyncio.wait = fake_wait  # type: ignore[assignment]
    asyncio.wait_for = fake_wait_for  # type: ignore[assignment]
    asyncio.timeout = fake_timeout  # type: ignore[assignment]
    asyncio.timeout_at = FakeTimeout  # type: ignore[assignment]
    asyncio.get_running_loop = lambda: proxy  # type: ignore[assignment]
    try:
        yield
    finally:
        loop.set_task_factory(previous_factory)
        for name, value in real.items():
            setattr(asyncio, name, value)


# ---------------------------------------------------------------------------
# Recording client and GATT
# ---------------------------------------------------------------------------

Event = tuple[float, str, Any, bytes]


class Recorder:
    """Collects GATT events with virtual timestamps."""

    def __init__(self, clock: FakeClock) -> None:
        self._clock = clock
        self.events: list[Event] = []
        self.background: list[Event] = []

    def add(self, char: Any, kind: Any, data: Any = b"") -> None:
        uuid = str(getattr(char, "uuid", char)).lower()
        self._clock.activity += 1
        if PHASE.get() != self._clock.phase:
            self.background.append((self._clock.now, uuid, kind, bytes(data)))
            return
        self.events.append((self._clock.elapsed, uuid, kind, bytes(data)))


ALL_PROPERTIES = ["read", "write", "write-without-response", "notify", "indicate"]


def _normalize(specifier: Any) -> Any:
    return specifier.lower() if isinstance(specifier, str) else specifier


class FakeChar:
    def __init__(self, uuid: str, handle: int, service: FakeService, properties: list[str]) -> None:
        self.uuid = uuid
        self.handle = handle
        self.properties = list(properties)
        self.descriptors: list[Any] = []
        self.description = ""
        self.service_uuid = service.uuid
        self.service_handle = service.handle
        self.max_write_without_response_size = 180

    def __repr__(self) -> str:
        return f"<FakeChar {self.uuid}>"


class FakeService:
    def __init__(self, uuid: str, handle: int) -> None:
        self.uuid = uuid
        self.handle = handle
        self.characteristics: list[FakeChar] = []
        self.description = ""

    def get_characteristic(self, specifier: Any) -> FakeChar | None:
        specifier = _normalize(specifier)
        return next((c for c in self.characteristics if specifier in (c.uuid, c.handle)), None)


class FakeServices:
    """Minimal ``BleakGATTServiceCollection`` stand-in built from a stored layout."""

    def __init__(self, layout: dict[str, Any]) -> None:
        services: dict[str, list[str]] = layout.get("services") or {
            # A pool: every listed UUID as a service holding every listed UUID.
            uuid: list(layout["pool"])
            for uuid in layout["pool"]
        }
        properties = layout.get("properties", {})
        default = properties.get("*", ALL_PROPERTIES)
        self._services: list[FakeService] = []
        self.characteristics: dict[int, FakeChar] = {}
        handle = 1
        for service_uuid, chars in services.items():
            service = FakeService(service_uuid, handle)
            handle += 1
            for char_uuid in chars:
                props = properties.get(char_uuid, default)
                char = FakeChar(char_uuid, handle, service, props)
                handle += 1
                service.characteristics.append(char)
                self.characteristics[char.handle] = char
            self._services.append(service)
        self.services = {s.handle: s for s in self._services}

    def __iter__(self) -> Any:
        return iter(self._services)

    def __len__(self) -> int:
        return len(self._services)

    def get_service(self, specifier: Any) -> FakeService | None:
        specifier = _normalize(specifier)
        return next((s for s in self._services if specifier in (s.uuid, s.handle)), None)

    def get_characteristic(self, specifier: Any) -> FakeChar | None:
        specifier = _normalize(specifier)
        for char in self.characteristics.values():
            if specifier in (char.uuid, char.handle):
                return char
        return None


class FakeClient:
    """A connected client whose GATT operations are recorded as wire events.

    ``replies`` maps a characteristic (or ``*``) to a notification delivered right
    after a subscription to it, such as a status frame a session waits for, and
    ``write:<hex prefix>`` to notifications (comma separated) answering a matching
    write, and
    ``read:<characteristic>`` to the value a read returns (empty otherwise).
    Attributes it lacks raise ``AttributeError`` like a real client.
    """

    is_connected = True
    address = "AA:BB:CC:DD:EE:FF"
    mtu_size = 185

    def __init__(self, recorder: Recorder, layout: dict[str, Any], replies: dict[str, str]) -> None:
        self._recorder = recorder
        self._replies = replies
        self._subscribers: list[tuple[Any, Callable[..., Any]]] = []
        self.services = FakeServices(layout)

    async def write_gatt_char(self, char: Any, data: Any, response: bool | None = None) -> None:
        self._recorder.add(char, response, data)
        await asyncio.sleep(WRITE_DURATION_S)
        for key, reply in self._replies.items():
            if key.startswith("write:") and bytes(data).hex().startswith(key[6:]):
                for frame in reply.split(","):
                    for target, callback in self._subscribers:
                        callback(target, bytearray.fromhex(frame))

    async def start_notify(self, char: Any, callback: Callable[..., Any], **_: Any) -> None:
        self._recorder.add(char, "notify")
        uuid = str(getattr(char, "uuid", char)).lower()
        target = self.services.get_characteristic(uuid) or char
        self._subscribers.append((target, callback))
        if (reply := self._replies.get(uuid, self._replies.get("*"))) is not None:
            asyncio.get_running_loop().call_soon(callback, target, bytearray.fromhex(reply))

    async def stop_notify(self, char: Any) -> None:
        self._recorder.add(char, "unnotify")

    async def read_gatt_char(self, char: Any, **_: Any) -> bytearray:
        self._recorder.add(char, "read")
        uuid = str(getattr(char, "uuid", char)).lower()
        return bytearray.fromhex(self._replies.get(f"read:{uuid}", ""))

    async def pair(self, *_: Any, **__: Any) -> bool:
        self._recorder.add("-", "pair")
        return True

    async def disconnect(self) -> bool:
        return True


def _collapse(events: list[Event]) -> list[list[Any]]:
    """Collapse constant-interval repeats of one event into ``[t, char, kind, hex, n, dt]``."""
    runs: list[list[Any]] = []
    for at, char, kind, data in events:
        t_ms = round(at * 1000)
        hex_data = data.hex()
        if runs:
            last = runs[-1]
            same = last[1] == char and last[2] == kind and last[3] == hex_data
            if same and last[4] == 1:
                last[4], last[5] = 2, t_ms - last[0]
                continue
            if same and t_ms - (last[0] + last[5] * (last[4] - 1)) == last[5]:
                last[4] += 1
                continue
        runs.append([t_ms, char, kind, hex_data, 1, 0])
    return runs


# ---------------------------------------------------------------------------
# Coordinator stub
# ---------------------------------------------------------------------------


async def _run_inline(func: Callable[..., Any], *args: Any) -> Any:
    return func(*args)


def _spawn(coro: Any, *_: Any, **__: Any) -> asyncio.Task[Any]:
    return asyncio.ensure_future(coro)


class Coordinator:
    """The coordinator surface controllers use, with the real pulse defaults.

    Attributes a controller reads that this stub lacks raise ``AttributeError``,
    which the capture records, rather than returning a silent mock.
    """

    def __init__(self, bed_type: str, variant: str | None, data: dict[str, Any]) -> None:
        from custom_components.adjustable_bed.const import (
            MALOUF_LAYOUT_AUTO,
            MALOUF_MEMORY_SLOTS_AUTO,
            VARIANT_AUTO,
            get_motor_pulse_defaults,
        )

        self.bed_type = bed_type
        self.entry = SimpleNamespace(
            data=data,
            options={},
            entry_id="wire-snapshot",
            title="Wire Snapshot Bed",
            unique_id="AA:BB:CC:DD:EE:FF",
            async_create_background_task=lambda _hass, coro, *_, **__: _spawn(coro),
        )
        self.hass = SimpleNamespace(
            data={},
            loop=asyncio.get_running_loop(),
            async_add_import_executor_job=_run_inline,
            async_add_executor_job=_run_inline,
            async_create_task=_spawn,
            async_create_background_task=_spawn,
            states=SimpleNamespace(get=lambda _entity_id: None),
            config=SimpleNamespace(
                time_zone="UTC",
                config_dir="/nonexistent/wire-snapshot",
                path=lambda *parts: "/".join(("/nonexistent/wire-snapshot", *parts)),
            ),
            config_entries=SimpleNamespace(
                async_get_entry=lambda entry_id: (
                    self.entry if entry_id == "wire-snapshot" else None
                ),
                async_entries=lambda *_: [self.entry],
                async_update_entry=self._update_entry,
            ),
        )
        self.motor_pulse_count, self.motor_pulse_delay_ms = get_motor_pulse_defaults(
            bed_type, variant or VARIANT_AUTO
        )
        self.cancel_command = asyncio.Event()
        self._cancel_counter = 0
        self._command_scheduler = SimpleNamespace(token=object(), stop_epoch=0)
        self._command_lock = asyncio.Lock()
        self.address = "AA:BB:CC:DD:EE:FF"
        # Some protocols embed the device name; kept from the first capture.
        self.name = "Contract Test Bed"
        self.ble_device_name = "Contract Test Bed"
        self.observed_ble_device_name = None
        self.motor_count = 2
        self.has_massage = True
        self.disable_angle_sensing = True
        self.malouf_layout = MALOUF_LAYOUT_AUTO
        self.malouf_memory_slots = MALOUF_MEMORY_SLOTS_AUTO
        self.head_max_angle = self.back_max_angle = 68.0
        self.legs_max_angle = self.feet_max_angle = 45.0
        self.position_data: dict[str, float] = {}
        self.controller_state: dict[str, Any] = {}
        self.capability_controller = None
        self.starcode_app_retained_state = None
        self.furnimove_widget_state = None
        self.okin_cb = None
        self.client: Any = None
        self.controller: Any = None
        self._offline_controller = None
        self._pairlink_runtime = None
        self._pending_capability_reload = False
        self._pending_internal_bond_marker = None

    def _update_entry(self, entry: Any, *, data: Any = None, options: Any = None, **_: Any) -> bool:
        if data is not None:
            entry.data = dict(data)
        if options is not None:
            entry.options = dict(options)
        return True

    def get_max_angle(self, position_key: str) -> float:
        return 45.0 if position_key in {"legs", "feet"} else 68.0

    def cache_capability_controller(self) -> None:
        """No offline capability controller to keep here."""

    async def async_execute_controller_command(self, command_fn: Any, *_: Any, **__: Any) -> None:
        await command_fn(self.controller)

    async def async_execute_controller_query(self, query_fn: Any, **kwargs: Any) -> Any:
        run_if = kwargs.get("run_if")
        if run_if is not None and not run_if():
            return None
        return await query_fn(self.controller)

    async def async_stop_command(self) -> None:
        self.cancel_command.set()

    async def async_disconnect(self, *_: Any, **__: Any) -> None:
        return None

    async def async_start_notify(self) -> None:
        return None

    async def async_write_app_state(self, *_: Any) -> None:
        return None

    @contextlib.contextmanager
    def hold_command_connection(self) -> Iterator[None]:
        yield

    def _uses_persistent_connection(self) -> bool:
        return False

    def request_command_cancel(self, *_: Any, **__: Any) -> None:
        self.cancel_command.set()

    def _ignore(self, *_: Any, **__: Any) -> None:
        return None

    record_command_trace = handle_controller_state_update = handle_controller_state_updates = (
        _ignore
    )
    save_app_state = clear_position_feedback = resume_disconnect_timer = _ignore
    remember_limoss_remote_capabilities = remember_limoss_remote_features = _ignore
    remember_fsm_relax_capabilities = remember_vibradorm_app_metadata = _ignore
    remember_vibradorm_app_floor_default = remember_remacro_led_level = _ignore
    _ble_bond_established = False
    remember_vmatbasic_settings = _begin_internal_entry_update = _ignore
    _async_persist_config = _schedule_pending_capability_reload = _ignore


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Scenario:
    """One way to reach a controller: bed type plus the route that changes bytes."""

    id: str
    bed_type: str
    protocol_variant: str | None = None
    # Config-entry data merged over ``BASE_ENTRY_DATA``.
    entry_data: dict[str, Any] = field(default_factory=dict)
    # Extra keyword arguments for ``create_controller``.
    factory_kwargs: dict[str, Any] = field(default_factory=dict)
    # Scripted notifications, see ``FakeClient``.
    replies: dict[str, str] = field(default_factory=dict)
    # The stored GATT layout to use, when it is another scenario's.
    layout_id: str | None = None
    # Properties every characteristic advertises, overriding the stored layout.
    properties: tuple[str, ...] | None = None


def _base_entry_data() -> dict[str, Any]:
    from custom_components.adjustable_bed import const

    return {
        const.CONF_FURNIMOVE_REMOTE: "00000",
        const.CONF_LOGICDATA_APP_PROFILE: "phone",
        const.CONF_LOGICDATA_APP_FAMILY: "p1",
        const.CONF_LOGICDATA_APP_LAYOUT: "standard_2",
        const.CONF_LOGICDATA_APP_TRANSPORT: "t1",
        const.CONF_JIECANG_APP_PROFILE: "dreamask",
        const.CONF_JIECANG_APP_LAYOUT: "standard_2",
        const.CONF_JIECANG_APP_TRANSPORT: "g1",
        const.CONF_MALOUF_APP_PROFILE: "malouf",
        const.CONF_MALOUF_APP_MODEL: "L600",
        const.CONF_MALOUF_APP_TRANSPORT: "okin_new",
        const.CONF_STARCODE_M5X5_PROFILE: "cb25",
        const.CONF_STARCODE_M1X12_PROFILE: "cb25",
        const.CONF_BLE_DEVICE_NAME: "STAR252201123456",
        const.CONF_PRODUCT_TYPE: "bed",
        const.CONF_VIBRADORM_APP_PROFILE: "caresse",
        const.CONF_VIBRADORM_CONTROL_TYPE: "2",
        const.CONF_VMATBASIC_PROFILE: "basic",
        const.CONF_REMACRO_MODEL: 50,
        const.CONF_STARCODE_COMMAND_SELECTOR: "none",
        const.CONF_STARCODE_UI_SELECTOR: "none",
        const.CONF_STARCODE_TRANSPORT_SELECTOR: "BOX3633",
    }


LIMOSS_REMOTE_CAPABILITIES = {
    "key_count": 8,
    "system": 0x14,
    "vibration": 1,
    "configuration": 0,
    "memory_count": 2,
}
# A valid TiMOTION AHF status frame: no lock bits, lamp code 0, checksum 0.
TIMOTION_STATUS = "9d" + "00" * 14


# MotoMotion names: panel One, panel Five with sides and massage, panel Six
# with users and heat.
MOTOMOTION_NAMES = ("SOFA000001MC00H", "SOFA000005S00FM", "SOFA000006AD00H")
# Room 0x12345678, vaddr 0x01020304; ``%s`` is the product ID byte.
KAIDI_BROADCAST = "c0ff0278563412ffeeddccbbaa0000%s0100a004030201"
# A node ping answer from AA:BB:CC:DD:EE:FF with vaddr 0x01020304.
KAIDI_PING_REPLY = "0300000000ffffeeddccbbaa04030201"


def default_scenario(bed_type: str) -> Scenario:
    """The bed type in its default route, with the entry data it needs to build."""
    from custom_components.adjustable_bed import const

    data: dict[str, Any] = {}
    variant: str | None = {
        const.BED_TYPE_LEGGETT_PLATT: const.LEGGETT_VARIANT_OKIN,
        const.BED_TYPE_SBI: const.SBI_VARIANT_BOTH,
        const.BED_TYPE_OCTO: const.OCTO_VARIANT_STANDARD,
        const.BED_TYPE_CASPER_BASE: "casperpro",
        const.BED_TYPE_HUSH_BASE: "hushl400",
        const.BED_TYPE_COMFORT_ENHANCEMENTS: "mc2",
        const.BED_TYPE_GLIDEAWAY_MOTION: "motion_400",
        const.BED_TYPE_ZSERIES: const.ZSERIES_VARIANT_Z230,
        const.BED_TYPE_RICHMAT: const.RICHMAT_VARIANT_WILINKE,
        const.BED_TYPE_HJBED: "hj_bedbjrn",
        const.BED_TYPE_RICHMAT_APP: "6BRM",
        const.BED_TYPE_RICHMAT_APP_SLEEP: "hj",
        const.BED_TYPE_DOUBLESLEEP: "p1",
        const.BED_TYPE_RICHMAT_CLASSIC_APPS: "avocadoecobase",
    }.get(bed_type)
    kwargs: dict[str, Any] = {}
    replies: dict[str, str] = {}
    if bed_type in const.KEESON_LAYOUT_APP_BED_TYPES:
        from custom_components.adjustable_bed.profiles.keeson import DEFAULT_LAYOUTS

        data[const.CONF_PRODUCT_TYPE] = DEFAULT_LAYOUTS[bed_type]
    if bed_type == const.BED_TYPE_ISLEEP:
        data.update({const.CONF_PRODUCT_TYPE: 129, const.CONF_KAIDI_ROOM_ID: 10000})
        replies = {
            # Room 10000 joined (own vaddr 1); the node ping finds this address.
            "write:0116011027": "021600,010a01000000",
            "write:03fffffffffe": KAIDI_PING_REPLY,
        }
    if bed_type == const.BED_TYPE_SLEEPTRACKER:
        data[const.CONF_PRODUCT_TYPE] = "unknown"
    if bed_type == const.BED_TYPE_RICHMAT_CLASSIC_APPS:
        data[const.CONF_PRODUCT_TYPE] = "GORM"  # three app modes
    if bed_type == const.BED_TYPE_SLEEPYS_ELITE_APP:
        data[const.CONF_SLEEPYS_ELITE_SELECTOR] = "BOX24"
    if bed_type == const.BED_TYPE_RICHMAT:
        data[const.CONF_RICHMAT_REMOTE] = "qrrm"
        kwargs = {"device_name": "Casper QRRM Bed"}
    if bed_type == const.BED_TYPE_LEGGETT_LP_LEGACY:
        from custom_components.adjustable_bed.beds.leggett.lp_legacy_profiles import (
            LP_LEGACY_PROFILE_CODES,
        )

        data.update(
            {
                const.CONF_LP_LEGACY_MODEL: LP_LEGACY_PROFILE_CODES[0],
                const.CONF_LP_LEGACY_MODE: "legacy",
                const.CONF_LP_LEGACY_WRITE_UUID: "11111111-2222-3333-4444-555555555555",
            }
        )
    if bed_type == const.BED_TYPE_MOTION_BED:
        # The app's identity is the exact advertised name.
        data[const.CONF_BLE_DEVICE_NAME] = "QMS-IQ"
    if bed_type == const.BED_TYPE_MOTOMOTION:
        # The exact name selects the panel: here panel One.
        data[const.CONF_BLE_DEVICE_NAME] = MOTOMOTION_NAMES[0]
        kwargs = {"device_name": MOTOMOTION_NAMES[0]}
    if bed_type == const.BED_TYPE_DOUBLESLEEP:
        data[const.CONF_PRODUCT_TYPE] = "3"
    if bed_type == const.BED_TYPE_LIMOSS_REMOTE:
        # Capabilities as a previous handshake stored them: a 4-motor bed with
        # vibration, two memory slots (the reply is not scripted).
        data[const.CONF_LIMOSS_REMOTE_STATE] = {"capabilities": LIMOSS_REMOTE_CAPABILITIES}
        data[const.CONF_PRODUCT_TYPE] = "bed"
    if bed_type == const.BED_TYPE_TIMOTION_AHF:
        replies = {"*": TIMOTION_STATUS}
    if bed_type == "ergomotion_4":
        data[const.CONF_PRODUCT_TYPE] = "H"  # the app's default P1 product
    if bed_type == const.BED_TYPE_SLEEP_NUMBER:
        # The Auth characteristic holds the 16-byte session UUID.
        replies = {f"read:{const.SLEEP_NUMBER_AUTH_CHAR_UUID}": "00112233445566778899aabbccddeeff"}
    if bed_type == const.BED_TYPE_SVANE:
        # Raw axis reads, so memory programming has a fresh position to save.
        replies = {
            "read:0000143d-0000-1000-8000-00805f9b34fb": "0102",
            "read:00001111-0000-1000-8000-00805f9b34fb": "000001020304",
        }
    if bed_type == const.BED_TYPE_KAIDI:
        # A provisioned broadcast advertisement carrying the room ID (tests/test_kaidi.py).
        kwargs = {"manufacturer_data": {0xFFFF: bytes.fromhex(KAIDI_BROADCAST % "81")}}
        replies = {"write:01160178563412": "021600"}  # join accepted
    return Scenario(
        id=bed_type,
        bed_type=bed_type,
        protocol_variant=variant,
        entry_data=data,
        factory_kwargs=kwargs,
        replies=replies,
    )


# Bed types whose protocol variants select a different controller or byte table.
VARIANT_ROUTES: dict[str, str] = {
    "keeson": "KEESON_VARIANTS",
    "richmat": "RICHMAT_VARIANTS",
    "leggett_platt": "LEGGETT_VARIANTS",
    "linak": "LINAK_VARIANTS",
    "octo": "OCTO_VARIANTS",
    "okin_cb24": "OKIN_CB24_VARIANTS",
    "okin_cst": "OKIN_CST_VARIANTS",
    "okin_64bit": "OKIN_64BIT_VARIANTS",
    "okin_dot": "OKIN_DOT_VARIANTS",
    "simmons": "SIMMONS_VARIANTS",
    "sbi": "SBI_VARIANTS",
    "rondure": "RONDURE_VARIANTS",
    "remacro": "REMACRO_VARIANTS",
    "sleepys_box25": "SLEEPYS_BOX25_VARIANTS",
    "adjustable_lumbar": "ADJUSTABLE_LUMBAR_VARIANTS",
    "bedsense": "BEDSENSE_VARIANTS",
    "comfort_enhancements": "COMFORT_ENHANCEMENTS_VARIANTS",
    "zseries": "ZSERIES_VARIANTS",
    "solace": "SOLACE_VARIANTS",
    "svane": "SVANE_VARIANTS",
    "star_elevate": "STAR_ELEVATE_VARIANTS",
    "doublesleep": "DOUBLESLEEP_VARIANTS",
    "kaidi": "KAIDI_VARIANTS",
    "adjustamattress": "ADJUSTAMATTRESS_VARIANTS",
}
ROUTE_ENTRY_DATA: dict[str, dict[str, Any]] = {
    "richmat": {"richmat_remote": "auto"},
}
ROUTE_KWARGS: dict[str, dict[str, Any]] = {
    "richmat": {"device_name": "Richmat"},
    # Floyd Home is advertised as product 139.
    "kaidi:floyd": {"manufacturer_data": {0xFFFF: bytes.fromhex(KAIDI_BROADCAST % "8b")}},
}
ROUTE_REPLIES: dict[str, dict[str, str]] = {
    # Floyd also pings for its node: this address answers with vaddr 0x01020304.
    "kaidi:floyd": {"write:03fffffffffe": KAIDI_PING_REPLY},
}
# Large variant sets are sampled: the first keys plus the last.
SAMPLED_ROUTES: dict[str, int] = {"adjustamattress": 3}


def route_scenarios() -> list[Scenario]:
    """Protocol-variant and app-profile routes, one scenario each."""
    from custom_components.adjustable_bed import const

    scenarios: list[Scenario] = []
    for bed_type, table in VARIANT_ROUTES.items():
        if bed_type not in const.SUPPORTED_BED_TYPES:
            continue
        base = default_scenario(bed_type)
        variants = [v for v in getattr(const, table) if v != const.VARIANT_AUTO]
        if (sample := SAMPLED_ROUTES.get(bed_type)) is not None:
            variants = [*variants[:sample], variants[-1]]
        for variant in variants:
            scenarios.append(
                dataclasses.replace(
                    base,
                    id=f"{bed_type}:{variant}",
                    protocol_variant=variant,
                    entry_data={**base.entry_data, **ROUTE_ENTRY_DATA.get(bed_type, {})},
                    factory_kwargs=ROUTE_KWARGS.get(f"{bed_type}:{variant}")
                    or ROUTE_KWARGS.get(bed_type, base.factory_kwargs),
                    replies={**base.replies, **ROUTE_REPLIES.get(f"{bed_type}:{variant}", {})},
                )
            )
    # Richmat app family: the picker model selects the byte table within one controller.
    from custom_components.adjustable_bed.beds.richmat_mh.controller import (
        MODEL_VARIANT_PREFIX,
        selectable_models,
    )

    for bed_type in sorted(const.RICHMAT_MH_BED_TYPES):
        models = selectable_models(const.RICHMAT_MH_APPS[bed_type])
        for model in dict.fromkeys([models[0], models[len(models) // 2]]):
            scenarios.append(
                Scenario(
                    id=f"{bed_type}:model_{model}",
                    bed_type=bed_type,
                    protocol_variant=f"{MODEL_VARIANT_PREFIX}{model}",
                )
            )
    # Jiecang family: one app, four profiles, shared and distinct layouts.
    for profile in ("dreamask", "dreamotion", "dreamhd", "comfort_motion"):
        second = "g2" if profile == "comfort_motion" else "g3"
        for layout, transport in (
            ("standard_2", "g1"),
            ("standard_2", second),
            ("standard_3_neck", "g1"),
            ("standard_4_legacy", "g1"),
        ):
            scenarios.append(
                Scenario(
                    id=f"jiecang_app:{profile}:{layout}:{transport}",
                    bed_type="jiecang_app",
                    entry_data={
                        const.CONF_JIECANG_APP_PROFILE: profile,
                        const.CONF_JIECANG_APP_LAYOUT: layout,
                        const.CONF_JIECANG_APP_TRANSPORT: transport,
                    },
                )
            )
    # LOGICDATA apps: phone, tablet and Sleep Smart over the three transports.
    for profile, family, layout, transport in (
        ("phone", "p1", "standard_2", "t1"),
        ("phone", "p2", "middle", "t1"),
        ("phone", "p1", "standard_2", "t3"),
        ("tablet", "p1", "standard_2", "t1"),
        ("tablet", "p2", "middle", "t1"),
        ("sleep_smart", "p1", "standard_2", "t1"),
        ("sleep_smart", "p1", "standard_2", "t2"),
        ("sleep_smart", "p1", "standard_2", "t3"),
    ):
        scenarios.append(
            Scenario(
                id=f"logicdata_app:{profile}:{family}:{layout}:{transport}",
                bed_type="logicdata_app",
                entry_data={
                    const.CONF_LOGICDATA_APP_PROFILE: profile,
                    const.CONF_LOGICDATA_APP_FAMILY: family,
                    const.CONF_LOGICDATA_APP_LAYOUT: layout,
                    const.CONF_LOGICDATA_APP_TRANSPORT: transport,
                },
            )
        )
    # Ergomotion 4.0: the product selects P1 or P2 frames, setup and light gates.
    if "ergomotion_4" in const.SUPPORTED_BED_TYPES:
        for product, extra, replies in ERGOMOTION_4_ROUTES:
            scenarios.append(
                Scenario(
                    id=f"ergomotion_4:{product}",
                    bed_type="ergomotion_4",
                    entry_data={const.CONF_PRODUCT_TYPE: product, **extra},
                    replies=replies,
                    layout_id="ergomotion_4",
                )
            )
    # Good Vibe Sleep: products by gesture mix and native sides, the legacy
    # single-byte link, and the two independent sleep sensors.
    if "goodvibe" in const.SUPPORTED_BED_TYPES:
        for profile, layout in GOODVIBE_ROUTES:
            scenarios.append(
                Scenario(
                    id=f"goodvibe:{profile}" + ("" if layout == "goodvibe" else f":{layout}"),
                    bed_type="goodvibe",
                    protocol_variant=profile,
                    layout_id=layout,
                )
            )
    # Classic Richmat apps: each app's own catalog, a desk, memory-arm and Hold
    # layouts, and the bare-byte Nordic UART route.
    if const.BED_TYPE_RICHMAT_CLASSIC_APPS in const.SUPPORTED_BED_TYPES:
        for app, layout, layout_id in CLASSIC_ROUTES:
            scenarios.append(
                Scenario(
                    id=f"{const.BED_TYPE_RICHMAT_CLASSIC_APPS}:{app}:{layout}"
                    + ("" if layout_id == const.BED_TYPE_RICHMAT_CLASSIC_APPS else ":nordic"),
                    bed_type=const.BED_TYPE_RICHMAT_CLASSIC_APPS,
                    protocol_variant=app,
                    entry_data={const.CONF_PRODUCT_TYPE: layout},
                    layout_id=layout_id,
                )
            )
    # MotoMotion: the panels whose controls differ from the default one.
    if const.BED_TYPE_MOTOMOTION in const.SUPPORTED_BED_TYPES:
        for name in MOTOMOTION_NAMES[1:]:
            scenarios.append(
                Scenario(
                    id=f"{const.BED_TYPE_MOTOMOTION}:{name}",
                    bed_type=const.BED_TYPE_MOTOMOTION,
                    entry_data={const.CONF_BLE_DEVICE_NAME: name},
                    factory_kwargs={"device_name": name},
                    layout_id=const.BED_TYPE_MOTOMOTION,
                )
            )
    # eShine (com.okin.eshine): each explicit product over the UART layout.
    if "eshine_okin" in const.SUPPORTED_BED_TYPES:
        for profile in const.ESHINE_OKIN_PROFILES:
            scenarios.append(
                Scenario(
                    id=f"eshine_okin:{profile}",
                    bed_type="eshine_okin",
                    protocol_variant=profile,
                    layout_id="eshine_okin",
                )
            )
    return scenarios


# App, layout and stored GATT layout. FWRM is a desk, JDRM arms memory saves and
# YGRM has the Hold selector and alarm actions. The framed layout offers only the
# fourth fixed service (W4), which the app frames like the first.
CLASSIC_ROUTES: tuple[tuple[str, str, str], ...] = (
    ("avocadoecobase", "GORM", "richmat_classic_apps_nordic"),
    ("coastersleep", "FWRM", "richmat_classic_apps"),
    ("fortywinks", "CORN", "richmat_classic_apps"),
    ("milemont", "JDRM", "richmat_classic_apps"),
    ("superior", "YGRM", "richmat_classic_apps"),
)


# Product key and stored layout. 6ERM mixes sustained, short and short-and-long
# presses on one side; ACRN offers sides 0 and 1, BTRM also the native side 2.
GOODVIBE_ROUTES: tuple[tuple[str, str], ...] = (
    ("selector-0004", "goodvibe"),
    ("selector-0004", "goodvibe_nordic"),
    ("selector-0026", "goodvibe"),
    ("selector-0095", "goodvibe"),
    ("sleep_rm", "goodvibe_sleep"),
    ("sleep_hj", "goodvibe_sleep"),
)


# A 19-byte status that reports the light on with colour 10 20 30, so the RGB
# products' light-gated controls run.
ERGOMOTION_4_LIGHT_ON = "f0" + "00" * 11 + "01" + "00" * 2 + "102030" + "00"
ERGOMOTION_4_ROUTES: tuple[tuple[str, dict[str, Any], dict[str, str]], ...] = (
    ("M10", {}, {}),  # plain P2
    ("M14", {"ble_device_name": "KSBT03CP123"}, {}),  # meditation, name-gated
    ("M19", {}, {"0000ffe4-0000-1000-8000-00805f9b34fb": ERGOMOTION_4_LIGHT_ON}),
    ("M22", {}, {}),  # 07 D0 frames
    ("M30", {}, {}),  # P1 zero at setup, P2 keys
    ("4194RGB", {}, {"0000ffe4-0000-1000-8000-00805f9b34fb": ERGOMOTION_4_LIGHT_ON}),
    (
        "custom",
        {
            "ergomotion4_product_name": "Custom",
            "ergomotion4_model_keys": ["o1", "o2", "o3", "o4"],
            "ergomotion4_massage_keys": ["m1", "m2", "m5", "m6"],
            "has_light": True,
        },
        {},
    ),
)


# Controllers that pick their write mode (or their write characteristic) from the
# GATT properties. The stored layouts advertise both write modes, as the tests'
# real-device fixtures do; these routes also pin the write-only and
# write-without-response-only branches.
PROPERTY_ROUTES: tuple[str, ...] = (
    "bedsense",
    "casper_base",
    "casper_sleep_sxb",
    "comfort_enhancements",
    "coolbase",
    "customatic_clarity",
    "eshine",
    "furnimove",
    "glideaway_motion",
    "hjbed",
    "hush_base",
    "hush_sleep_sxb",
    "jensen",
    "kaidi",
    "keeson:adjustable_lite",
    "keeson:americanstar",
    "keeson:base",
    "keeson:innova",
    "keeson:ksbt",
    "keeson:restonic_a",
    "keeson:simon_li",
    "limoss",
    "richmat",
    "richmat_classic_apps",
    "richmat_idealbed:model_3i",
    "serenity",
    "svane",
    "timotion_ahf",
    "vibradorm",
)
WRITE_ONLY: tuple[str, ...] = ("read", "write", "notify", "indicate")
NO_RESPONSE_ONLY: tuple[str, ...] = ("read", "write-without-response", "notify", "indicate")


def feature_scenarios(by_id: dict[str, Scenario]) -> list[Scenario]:
    """Routes with the optional massage and light hardware the factory reads from entry data."""
    from custom_components.adjustable_bed import const

    on = {const.CONF_HAS_MASSAGE: True, const.CONF_HAS_LIGHT: True}
    routes = [
        dataclasses.replace(
            by_id[sid],
            id=f"{sid}:massage_light",
            layout_id=sid,
            entry_data={**by_id[sid].entry_data, **on},
        )
        for sid in ("logicdata_app", "limoss_remote", "fsm_relax")
    ]
    # Vibradorm Caresse restored from an older app, with every optional feature.
    routes.append(
        dataclasses.replace(
            by_id["vibradorm_app"],
            id="vibradorm_app:caresse_restored",
            layout_id="vibradorm_app",
            entry_data={
                const.CONF_VIBRADORM_RESTORED: True,
                const.CONF_VIBRADORM_CONTROL_TYPE: "6",
                const.CONF_VIBRADORM_FLOOR_LIGHT: True,
                const.CONF_VIBRADORM_RGB: True,
                const.CONF_VIBRADORM_LIGHT_EXTENSION: True,
                const.CONF_HAS_MASSAGE: True,
            },
        )
    )
    return routes


def build_scenarios() -> list[Scenario]:
    """Every bed type once, plus the routes that change the controller or its bytes."""
    from custom_components.adjustable_bed.const import SUPPORTED_BED_TYPES

    scenarios = [default_scenario(bed_type) for bed_type in SUPPORTED_BED_TYPES]
    scenarios.extend(route_scenarios())
    by_id = {scenario.id: scenario for scenario in scenarios}
    scenarios.extend(feature_scenarios(by_id))
    for sid in PROPERTY_ROUTES:
        for suffix, properties in (("props_write", WRITE_ONLY), ("props_wwr", NO_RESPONSE_ONLY)):
            scenarios.append(
                dataclasses.replace(
                    by_id[sid], id=f"{sid}:{suffix}", layout_id=sid, properties=properties
                )
            )
    ids = [scenario.id for scenario in scenarios]
    assert len(ids) == len(set(ids)), "duplicate scenario ids"
    return scenarios


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def deterministic_process_state() -> Iterator[None]:
    """Seed randomness, reset app-global counters and empty HA's Bluetooth history.

    Nonces, session ids and process-wide sequence numbers then repeat, whatever
    ran earlier in the process.
    """
    import random
    import secrets
    from unittest.mock import patch

    from custom_components.adjustable_bed.beds.limoss.remote_protocol import APP_SEQUENCE

    rng = random.Random(0)
    random.seed(0)
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch.object(secrets, "randbits", rng.getrandbits))
        stack.enter_context(patch.object(secrets, "token_bytes", lambda n=32: rng.randbytes(n)))
        stack.enter_context(patch.object(secrets, "token_hex", lambda n=32: rng.randbytes(n).hex()))
        stack.enter_context(patch.object(APP_SEQUENCE, "value", 0))
        # No advertisement history or scanners: lookups answer like an empty HA.
        from homeassistant.components import bluetooth

        stack.enter_context(
            patch.object(bluetooth, "async_last_service_info", lambda *_, **__: None)
        )
        stack.enter_context(patch.object(bluetooth, "async_current_scanners", lambda *_: []))
        yield


async def _build(scenario: Scenario, client: Any) -> Any:
    from custom_components.adjustable_bed.controller_factory import create_controller

    coordinator = Coordinator(
        scenario.bed_type,
        scenario.protocol_variant,
        {**_base_entry_data(), **scenario.entry_data},
    )
    coordinator.client = client
    controller = await create_controller(
        cast(Any, coordinator),
        scenario.bed_type,
        scenario.protocol_variant,
        client,
        **scenario.factory_kwargs,
    )
    coordinator.controller = controller
    return controller


async def _timed(awaitable: Awaitable[Any], recorder: Recorder, clock: FakeClock) -> dict[str, Any]:
    """Run one phase on the virtual budget and summarise what it put on the wire."""
    try:
        await asyncio.wait_for(awaitable, COMMAND_BUDGET_S)
    except NotImplementedError:
        if recorder.events:
            return {"status": "not_implemented", "writes": _collapse(recorder.events)}
        return {"status": "unsupported"}
    except TimeoutError:
        return {"status": "timeout", "writes": _collapse(recorder.events)}
    except Exception as err:  # noqa: BLE001 - recorded, not hidden
        if os.environ.get("WIRE_SNAPSHOT_VERBOSE"):
            print(f"  {type(err).__name__}: {str(err)[:200]}", file=sys.stderr)
        return {
            "status": "error",
            "error": type(err).__name__,
            "writes": _collapse(recorder.events),
        }
    if not recorder.events:
        return {"status": "no_writes"}
    return {"status": "ok", "writes": _collapse(recorder.events)}


async def _connect(controller: Any, recorder: Recorder, clock: FakeClock) -> dict[str, Any]:
    """Replay the coordinator's post-connect hooks and record any handshake traffic."""

    async def hooks() -> None:
        # The coordinator's startup order, with notifications always started.
        discovery = controller.async_discover_capabilities()
        if inspect.isawaitable(discovery):
            await discovery
        await controller.start_notify(lambda *_: None)
        for hook in STARTUP_HOOKS.get(controller._coordinator.bed_type, ()):  # noqa: SLF001
            if hasattr(controller, hook):
                await getattr(controller, hook)()

    recorder.events.clear()
    clock.begin_phase()
    return await _timed(hooks(), recorder, clock)


# Bed-specific startup the coordinator runs after notifications, in its order.
STARTUP_HOOKS: dict[str, tuple[str, ...]] = {
    "octo": ("discover_features", "send_pin", "start_keepalive"),
    "jensen": ("query_config",),
    "sleep_number": ("query_config",),
    "sleep_number_mcr": ("query_config",),
}


async def _run_command(
    controller: Any, recorder: Recorder, clock: FakeClock, command: Command
) -> dict[str, Any]:
    recorder.events.clear()
    cancel = controller._coordinator.cancel_command  # noqa: SLF001
    cancel.clear()
    clock.begin_phase()

    async def release() -> None:
        # The user lets go of a held command after HOLD_CAP_S, like a STOP request.
        await asyncio.sleep(HOLD_CAP_S)
        cancel.set()

    hold_cap = asyncio.ensure_future(release())
    try:
        try:
            awaitable = command.call(controller)
        except NotImplementedError:
            return {"status": "unsupported"}
        except Exception as err:  # noqa: BLE001
            return {"status": "error", "error": type(err).__name__}
        return await _timed(awaitable, recorder, clock)
    finally:
        hold_cap.cancel()


async def _cancel_strays(baseline: set[asyncio.Task[Any]]) -> None:
    """Cancel tasks a controller left running (keepalives, retries) since ``baseline``."""
    strays = [
        t for t in asyncio.all_tasks() if t not in baseline and t is not asyncio.current_task()
    ]
    for task in strays:
        task.cancel()
    await asyncio.gather(*strays, return_exceptions=True)


async def capture_scenario(
    scenario: Scenario, layout: dict[str, Any], frozen: Any = None
) -> dict[str, Any]:
    """Capture one scenario on its stored GATT ``layout``."""
    baseline = asyncio.all_tasks()
    try:
        return await _capture(scenario, layout, frozen, baseline)
    finally:
        await _cancel_strays(baseline)


async def _capture(
    scenario: Scenario, layout: dict[str, Any], frozen: Any, baseline: set[asyncio.Task[Any]]
) -> dict[str, Any]:
    clock = FakeClock(frozen)
    recorder = Recorder(clock)
    with deterministic_process_state(), virtual_time(clock):
        controller = await _build(scenario, FakeClient(recorder, layout, scenario.replies))
        commands = {"connect": await _connect(controller, recorder, clock)}
        plan = plan_commands(controller)
        for command in plan:
            result = await _run_command(controller, recorder, clock, command)
            # A cover that emits exactly what the matching move call did points to it.
            twin = (
                command.name.removeprefix("cover:")
                .replace("_open", "_up")
                .replace("_close", "_down")
            )
            if command.name.startswith("cover:") and commands.get(twin) == result:
                result = {"status": "same", "as": twin, "ok": result["status"]}
            commands[command.name] = result
        # Let delayed work from the final command run before cleanup cancels it.
        clock.begin_phase()
        await asyncio.sleep(DRAIN_WINDOW_S)
        if recorder.background:
            # Events from tasks of an earlier phase, at absolute virtual time.
            commands["background"] = {
                "status": "background",
                "writes": _collapse(recorder.background),
            }

    gaps = [
        c.name for c in plan if c.is_gap(commands[c.name].get("ok", commands[c.name]["status"]))
    ]
    info: dict[str, Any] = {
        "bed_type": scenario.bed_type,
        "controller": type(controller).__name__,
        "module": type(controller).__module__.removeprefix("custom_components.adjustable_bed.beds."),
        "pulse": [
            controller._coordinator.motor_pulse_count,
            controller._coordinator.motor_pulse_delay_ms,
        ],  # noqa: SLF001
    }
    if commands["connect"]["status"] in {"error", "timeout"}:
        info["connect_error"] = commands["connect"].get("error", "timeout")
    if gaps:
        info["gaps"] = gaps
    return {**info, "commands": commands}


async def capture_all(only: list[str] | None = None) -> dict[str, Any]:
    """Capture every scenario with wall-clock time frozen (clock-sync frames carry it)."""
    from freezegun import freeze_time

    layouts = json.loads(LAYOUTS_PATH.read_text())
    scenarios = [s for s in build_scenarios() if not only or s.id in only]
    if missing := [s.id for s in scenarios if (s.layout_id or s.id) not in layouts]:
        raise SystemExit(f"add a GATT layout for {missing} to {LAYOUTS_PATH.name}")
    result: dict[str, Any] = {}
    with freeze_time(FROZEN_NOW, real_asyncio=True) as frozen:
        for scenario in scenarios:
            started = _REAL_CLOCK[0]()
            try:
                layout = layouts[scenario.layout_id or scenario.id]
                if scenario.properties is not None:
                    properties = {**layout.get("properties", {}), "*": list(scenario.properties)}
                    layout = {**layout, "properties": properties}
                result[scenario.id] = await capture_scenario(scenario, layout, frozen)
            except Exception as err:  # noqa: BLE001 - a scenario that cannot build is data too
                result[scenario.id] = {
                    "bed_type": scenario.bed_type,
                    "build_error": f"{type(err).__name__}: {err}",
                }
            if os.environ.get("WIRE_SNAPSHOT_VERBOSE"):
                elapsed = _REAL_CLOCK[0]() - started
                print(f"{scenario.id} {elapsed:.1f}s", file=sys.stderr, flush=True)
    return {"schema": SCHEMA_VERSION, "scenarios": result}


def render(snapshot: dict[str, Any]) -> str:
    """Stable text form: one line per command so diffs stay reviewable.

    Characteristic UUIDs are replaced by their first eight hex digits (the full
    UUID where two share them) and listed once under ``chars``. Commands a
    controller does not support are omitted.
    """
    uuids = sorted(
        {
            write[1]
            for entry in snapshot["scenarios"].values()
            for cmd in entry.get("commands", {}).values()
            for write in cmd.get("writes", [])
        }
    )
    prefixes = [u[:8] for u in uuids]
    short = {u: u[:8] if prefixes.count(u[:8]) == 1 else u for u in uuids}
    lines = ["{", f'"schema": {snapshot["schema"]},']
    lines.append('"chars": ' + json.dumps({short[u]: u for u in uuids}, sort_keys=True) + ",")
    lines.append('"scenarios": {')
    blocks: list[str] = []
    for sid, entry in sorted(snapshot["scenarios"].items()):
        head = {k: v for k, v in entry.items() if k != "commands"}
        block = [f"{json.dumps(sid)}: {{", f'"info": {json.dumps(head, sort_keys=True)},']
        rows = []
        for name, cmd in entry.get("commands", {}).items():
            if cmd["status"] == "unsupported":
                continue
            if "writes" in cmd:
                cmd = {**cmd, "writes": [[w[0], short[w[1]], *w[2:]] for w in cmd["writes"]]}
            rows.append(
                f"{json.dumps(name)}: {json.dumps(cmd, sort_keys=True, separators=(',', ':'))}"
            )
        block.append('"commands": {' + (("\n" + ",\n".join(rows) + "\n") if rows else "") + "}}")
        blocks.append("\n".join(block))
    lines.append(",\n".join(blocks))
    lines.append("}}")
    return "\n".join(lines) + "\n"


# Commands whose output may follow set iteration order, as (bed type, command),
# which a second hash seed is allowed to change. Empty: every controller now
# writes in a fixed order, so any difference between seeds fails the check.
SEED_DEPENDENT: frozenset[tuple[str, str]] = frozenset()


def seed_differences(first: str, second: str) -> list[str]:
    """``scenario/command`` entries that differ between two rendered captures."""
    a, b = json.loads(first)["scenarios"], json.loads(second)["scenarios"]
    return [
        f"{sid}/{name}"
        for sid in sorted(set(a) | set(b))
        for name in sorted(
            set(a.get(sid, {}).get("commands", {})) | set(b.get(sid, {}).get("commands", {}))
        )
        if a.get(sid, {}).get("commands", {}).get(name)
        != b.get(sid, {}).get("commands", {}).get(name)
        and (a.get(sid, b.get(sid, {})).get("info", {}).get("bed_type"), name) not in SEED_DEPENDENT
    ] + [f"{sid}/info" for sid in a if a[sid].get("info") != b.get(sid, {}).get("info")]


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--check", action="store_true", help="fail if the snapshot is stale")
    parser.add_argument("--list", action="store_true", help="list scenario ids")
    parser.add_argument("--only", nargs="*", help="limit to these scenario ids (no write)")
    parser.add_argument("--probe", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    # The snapshot is taken with set iteration order fixed (see SEED_DEPENDENT), in a
    # fresh process, so it is also free of whatever state a test session left behind.
    if not args.probe and os.environ.get("PYTHONHASHSEED") != "0":
        os.execve(
            sys.executable, [sys.executable, *sys.argv], {**os.environ, "PYTHONHASHSEED": "0"}
        )
    logging.disable(logging.CRITICAL)

    if args.list:
        for scenario in build_scenarios():
            print(scenario.id)
        return 0

    probe = None
    if args.check:
        # A second hash seed, captured in parallel: new set-order dependence fails.
        probe = subprocess.Popen(
            [sys.executable, __file__, "--probe"],
            env={**os.environ, "PYTHONHASHSEED": "1"},
            stdout=subprocess.PIPE,
            text=True,
        )
    text = render(asyncio.run(capture_all(args.only)))
    if args.only or args.probe:
        print(text, end="")
        return 0
    if args.check:
        assert probe is not None
        probed, _ = probe.communicate()
        committed = SNAPSHOT_PATH.read_text()
        if committed != text:
            diff = difflib.unified_diff(
                committed.splitlines(), text.splitlines(), "committed", "fresh", n=0, lineterm=""
            )
            print(f"{SNAPSHOT_PATH.relative_to(REPO_ROOT)} is stale:")
            print("\n".join(line[:240] for _, line in zip(range(20), diff, strict=False)))
            return 1
        if probe.returncode:
            print("the second-seed capture failed")
            return 1
        if differing := seed_differences(text, probed):
            print("output depends on the hash seed (set iteration order):")
            print("\n".join(differing[:20]))
            return 1
        return 0
    SNAPSHOT_PATH.write_text(text)
    print(f"wrote {SNAPSHOT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
