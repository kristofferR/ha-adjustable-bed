"""Calibrated travel-time position estimates and saved positions (#601).

Beds without position feedback can opt in per motor. The integration times each
movement it starts and turns that time into an estimated percentage of full
travel, using separately calibrated raising and lowering times. Flat is the only
reference. An estimate is trusted only while every movement since the reference
went through the integration and finished as expected:

- ``tracking``: calibrated and referenced, with every move accounted for.
- ``unconfirmed``: an estimate restored after a restart; the user confirms it.
- ``unknown``: a failed or untracked movement, a hardware preset or memory
  recall, a lost connection mid-move, or the user reported using the remote.
- ``not_calibrated``: enabled without both travel times.

The estimator sits above the controller layer. Movement still runs through the
coordinator's scheduler with each protocol's own cadence, cancellation and STOP.
The estimator only wraps the controller command an entry point already sends,
times it and never sends a frame of its own. Wrappers resolve the physical bed
from the controller they are called with, so a paired fan-out updates each side.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable, Coroutine, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final, TypedDict
from uuid import uuid4

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN, SIDE_BOTH

if TYPE_CHECKING:
    from .beds.base import BedController

type MotorCommand = Callable[[BedController], Coroutine[Any, Any, None]]

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION: Final = 1
_REGISTRY_KEY: Final = "position_estimates"
# Confirmations survive an entry reload (options change) but never a restart.
_SESSION_KEY: Final = "position_estimate_session"
STANDALONE_KEY: Final = "bed"

MIN_TRAVEL_S: Final = 1.0
MAX_TRAVEL_S: Final = 60.0
MIN_MOVE_MS: Final = 100
# "Lower to flat" runs past the calibrated time so a slow run still bottoms out.
LOWER_TO_FLAT_FACTOR: Final = 1.2
LOWER_TO_FLAT_EXTRA_S: Final = 1.0
# A recalled motor further than this from its target did not arrive.
ARRIVAL_TOLERANCE: Final = 2.0
MAX_POSITION_NAME_LENGTH: Final = 40


class EstimateState(StrEnum):
    """How far an estimated motor position can be trusted."""

    TRACKING = "tracking"
    UNCONFIRMED = "unconfirmed"
    UNKNOWN = "unknown"
    NOT_CALIBRATED = "not_calibrated"


class EstimateReason(StrEnum):
    """Why an estimate is not tracking."""

    NOT_REFERENCED = "not_referenced"
    RESTART = "restart"
    FAILED_MOVE = "failed_move"
    UNTRACKED_MOVE = "untracked_move"
    HARDWARE_PRESET = "hardware_preset"
    REMOTE = "remote"
    CONNECTION_LOST = "connection_lost"


def _clamp(value: float) -> float:
    return min(100.0, max(0.0, value))


class StoredMotor(TypedDict, total=False):
    up_s: float | None
    down_s: float | None
    percent: float | None
    reference_at: str | None
    moves_since_reference: int


@dataclass(slots=True)
class MotorEstimate:
    """Calibration and current estimate of one motor."""

    up_s: float | None = None
    down_s: float | None = None
    percent: float | None = None
    confirmed: bool = False
    reason: EstimateReason | None = EstimateReason.NOT_REFERENCED
    reference_at: datetime | None = None
    moves_since_reference: int = 0
    # Bumped by every discontinuous change, so a move that started before a
    # new reference or an invalidation never adds its travel afterwards.
    generation: int = 0

    @property
    def calibrated(self) -> bool:
        return self.up_s is not None and self.down_s is not None

    @property
    def state(self) -> EstimateState:
        if not self.calibrated:
            return EstimateState.NOT_CALIBRATED
        if self.percent is None:
            return EstimateState.UNKNOWN
        return EstimateState.TRACKING if self.confirmed else EstimateState.UNCONFIRMED

    def travel(self, direction: str, seconds: float) -> None:
        """Add a finished movement of ``seconds`` in ``direction``."""
        if self.up_s is None or self.down_s is None or self.percent is None or seconds <= 0:
            return
        full = self.up_s if direction == "up" else self.down_s
        delta = seconds / full * 100
        self.percent = _clamp(self.percent + delta if direction == "up" else self.percent - delta)
        self.moves_since_reference += 1

    def plan(self, target: float) -> tuple[str, float] | None:
        """Return the direction and seconds that move this motor to ``target``."""
        if self.up_s is None or self.down_s is None or self.percent is None:
            return None
        delta = _clamp(target) - self.percent
        if delta == 0:
            return None
        if delta > 0:
            return "up", delta / 100 * self.up_s
        return "down", -delta / 100 * self.down_s

    def invalidate(self, reason: EstimateReason) -> None:
        self.percent = None
        self.confirmed = False
        self.reason = reason
        self.generation += 1

    def set_reference(self, now: datetime) -> None:
        self.percent = 0.0
        self.confirmed = True
        self.reason = None
        self.reference_at = now
        self.moves_since_reference = 0
        self.generation += 1

    def stored(self) -> StoredMotor:
        return {
            "up_s": self.up_s,
            "down_s": self.down_s,
            "percent": self.percent,
            "reference_at": self.reference_at.isoformat() if self.reference_at else None,
            "moves_since_reference": self.moves_since_reference,
        }

    @classmethod
    def restored(cls, stored: Mapping[str, Any]) -> MotorEstimate:
        """Restore a stored motor; a restored estimate is never confirmed."""

        def seconds(value: object) -> float | None:
            if isinstance(value, bool) or not isinstance(value, int | float):
                return None
            return float(value) if MIN_TRAVEL_S <= value <= MAX_TRAVEL_S else None

        percent = stored.get("percent")
        reference = stored.get("reference_at")
        moves = stored.get("moves_since_reference")
        restored_percent = (
            _clamp(float(percent))
            if isinstance(percent, int | float) and not isinstance(percent, bool)
            else None
        )
        return cls(
            up_s=seconds(stored.get("up_s")),
            down_s=seconds(stored.get("down_s")),
            percent=restored_percent,
            confirmed=False,
            reason=(
                EstimateReason.RESTART
                if restored_percent is not None
                else EstimateReason.NOT_REFERENCED
            ),
            reference_at=dt_util.parse_datetime(reference) if isinstance(reference, str) else None,
            moves_since_reference=moves if isinstance(moves, int) and moves >= 0 else 0,
        )


@dataclass(slots=True)
class _Move:
    motors: tuple[str, ...]
    generations: dict[str, int]
    started: float
    failed: bool = False


class BedEstimate:
    """Calibration and estimates of one physical bed, or one side of a pair."""

    def __init__(self, owner: PositionEstimates, address: str, side: str | None) -> None:
        self._owner = owner
        self.address = address
        self.side = side
        self.motors: dict[str, MotorEstimate] = {}
        self._moves: dict[int, _Move] = {}
        self._next_move = 0

    @property
    def key(self) -> str:
        """Saved positions refer to a bed by this key."""
        return self.side or STANDALONE_KEY

    @property
    def target_side(self) -> str:
        """Side argument for the paired or standalone movement services."""
        return self.side or SIDE_BOTH

    def state(self, motor: str) -> EstimateState:
        estimate = self.motors.get(motor)
        return EstimateState.NOT_CALIBRATED if estimate is None else estimate.state

    @property
    def calibrated_motors(self) -> list[str]:
        return [motor for motor, estimate in self.motors.items() if estimate.calibrated]

    def tracking(self, motors: Iterable[str]) -> bool:
        return all(self.state(motor) is EstimateState.TRACKING for motor in motors)

    def configure(self, calibration: Mapping[str, tuple[float | None, float | None]]) -> None:
        """Replace the enabled motors and their travel times."""
        motors: dict[str, MotorEstimate] = {}
        for motor, (up_s, down_s) in calibration.items():
            estimate = self.motors.get(motor) or MotorEstimate()
            estimate.up_s = up_s
            estimate.down_s = down_s
            motors[motor] = estimate
        self.motors = motors
        self._owner.changed()

    def set_reference(self, motors: Iterable[str] | None = None) -> None:
        """Record that the selected motors are flat now."""
        now = dt_util.utcnow()
        for motor in self._selected(motors):
            if self.motors[motor].calibrated:
                self.motors[motor].set_reference(now)
        self._owner.changed()

    def confirm_unchanged(self) -> None:
        """Trust restored estimates after the user confirms the bed has not moved."""
        for estimate in self.motors.values():
            if estimate.state is EstimateState.UNCONFIRMED:
                estimate.confirmed = True
                estimate.reason = None
        self._owner.changed()

    def invalidate(self, reason: EstimateReason, motors: Iterable[str] | None = None) -> None:
        """Mark the selected motors unknown."""
        selected = self._selected(motors)
        for motor in selected:
            if self.motors[motor].calibrated:
                self.motors[motor].invalidate(reason)
        if selected:
            _LOGGER.debug("Estimated %s of %s is unknown: %s", selected, self.address, reason)
            self._owner.changed()

    def begin_move(self, motors: tuple[str, ...]) -> int:
        self._next_move += 1
        self._moves[self._next_move] = _Move(
            motors, {motor: self.motors[motor].generation for motor in motors}, _clock()
        )
        return self._next_move

    def move_elapsed(self, motor: str) -> float | None:
        """Seconds since the running tracked move of ``motor`` started, if any."""
        started = [move.started for move in self._moves.values() if motor in move.motors]
        return _clock() - max(started) if started else None

    def end_move(self, token: int, direction: str, seconds: float | None) -> None:
        """Apply a finished move, or mark its motors unknown when it failed."""
        move = self._moves.pop(token, None)
        if move is None or move.failed:
            return
        if seconds is None:
            self.invalidate(EstimateReason.FAILED_MOVE, move.motors)
            return
        for motor in move.motors:
            estimate = self.motors.get(motor)
            if estimate is not None and estimate.generation == move.generations[motor]:
                estimate.travel(direction, max(0.0, seconds))
        self._owner.changed()

    @property
    def moving(self) -> bool:
        return bool(self._moves)

    def abandon_moves(self, reason: EstimateReason) -> None:
        """A running tracked move ended in a way that cannot prove where it stopped."""
        motors: set[str] = set()
        for move in self._moves.values():
            move.failed = True
            motors.update(move.motors)
        if motors:
            self.invalidate(reason, motors)

    def _selected(self, motors: Iterable[str] | None) -> list[str]:
        if motors is None:
            return list(self.motors)
        return [motor for motor in motors if motor in self.motors]

    def stored(self) -> dict[str, StoredMotor]:
        return {motor: estimate.stored() for motor, estimate in self.motors.items()}


@dataclass(slots=True)
class SavedPosition:
    """A named software preset of estimated percentages, per bed key."""

    id: str
    name: str
    button: bool
    targets: dict[str, dict[str, float]] = field(default_factory=dict)

    def stored(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "button": self.button, "targets": self.targets}

    @classmethod
    def restored(cls, stored: Mapping[str, Any]) -> SavedPosition | None:
        position_id, name = stored.get("id"), stored.get("name")
        targets = stored.get("targets")
        if not isinstance(position_id, str) or not isinstance(name, str):
            return None
        if not isinstance(targets, dict):
            return None
        clean: dict[str, dict[str, float]] = {}
        for key, motors in targets.items():
            if isinstance(key, str) and isinstance(motors, dict):
                clean[key] = {
                    motor: _clamp(float(value))
                    for motor, value in motors.items()
                    if isinstance(motor, str)
                    and isinstance(value, int | float)
                    and not isinstance(value, bool)
                }
        return cls(position_id, name, stored.get("button") is not False, clean)


class PositionEstimates:
    """Every estimated bed and saved position of one config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        beds: Iterable[tuple[str, str | None]],
    ) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, storage_key(entry_id))
        self.beds: dict[str, BedEstimate] = {
            address.upper(): BedEstimate(self, address.upper(), side) for address, side in beds
        }
        self.positions: list[SavedPosition] = []
        self._listeners: list[Callable[[], None]] = []

    @property
    def active(self) -> bool:
        return any(bed.motors for bed in self.beds.values())

    def bed_for_address(self, address: str) -> BedEstimate | None:
        return self.beds.get(address.upper())

    def bed_for_key(self, key: str) -> BedEstimate | None:
        return next((bed for bed in self.beds.values() if bed.key == key), None)

    async def async_load(self) -> None:
        stored = await self._store.async_load() or {}
        stored_beds = stored.get("beds")
        session = self.hass.data.get(DOMAIN, {}).get(_SESSION_KEY, {}).pop(self.entry_id, {})
        if isinstance(stored_beds, dict):
            for address, motors in stored_beds.items():
                bed = self.bed_for_address(address) if isinstance(address, str) else None
                if bed is None or not isinstance(motors, dict):
                    continue
                for motor, data in motors.items():
                    if isinstance(motor, str) and isinstance(data, dict):
                        estimate = MotorEstimate.restored(data)
                        if (
                            estimate.percent is not None
                            and session.get((bed.address, motor)) == estimate.percent
                        ):
                            # An entry reload within one Home Assistant run keeps trust.
                            estimate.confirmed = True
                            estimate.reason = None
                        bed.motors[motor] = estimate
        stored_positions = stored.get("positions")
        if isinstance(stored_positions, list):
            self.positions = [
                position
                for item in stored_positions
                if isinstance(item, dict) and (position := SavedPosition.restored(item))
            ]

    def _data_to_save(self) -> dict[str, Any]:
        return {
            "beds": {address: bed.stored() for address, bed in self.beds.items() if bed.motors},
            "positions": [position.stored() for position in self.positions],
        }

    def changed(self) -> None:
        """Persist and publish a change."""
        self._store.async_delay_save(self._data_to_save, 1)
        for listener in list(self._listeners):
            listener()

    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove

    async def async_unload(self) -> None:
        """Flush, and keep confirmations for a reload in this Home Assistant run."""
        session: dict[str, dict[tuple[str, str], float]] = self.hass.data.setdefault(
            DOMAIN, {}
        ).setdefault(_SESSION_KEY, {})
        session[self.entry_id] = {
            (bed.address, motor): estimate.percent
            for bed in self.beds.values()
            for motor, estimate in bed.motors.items()
            if estimate.state is EstimateState.TRACKING and estimate.percent is not None
        }
        await self._store.async_save(self._data_to_save())

    # ------------------------------------------------------------- saved positions
    def position(self, reference: str) -> SavedPosition:
        """Find a saved position by id, then by case-insensitive name."""
        found = next((item for item in self.positions if item.id == reference), None)
        if found is None:
            folded = reference.strip().casefold()
            found = next((item for item in self.positions if item.name.casefold() == folded), None)
        if found is None:
            raise ServiceValidationError(
                f"No saved position named {reference}",
                translation_domain=DOMAIN,
                translation_key="saved_position_not_found",
                translation_placeholders={"position": reference},
            )
        return found

    def current_targets(self, beds: Iterable[BedEstimate]) -> dict[str, dict[str, float]]:
        """Capture the current estimates; every motor must be tracking."""
        targets: dict[str, dict[str, float]] = {}
        for bed in beds:
            motors = bed.calibrated_motors
            if not motors:
                continue
            _require_tracking(bed, motors)
            targets[bed.key] = {
                motor: round(bed.motors[motor].percent or 0.0, 1) for motor in motors
            }
        if not targets:
            raise ServiceValidationError(
                "No calibrated estimated motors to save",
                translation_domain=DOMAIN,
                translation_key="position_estimate_not_enabled",
            )
        return targets

    def save_position(
        self, name: str, beds: Iterable[BedEstimate], *, button: bool
    ) -> SavedPosition:
        clean = _position_name(name)
        if any(item.name.casefold() == clean.casefold() for item in self.positions):
            raise ServiceValidationError(
                f"A saved position named {clean} already exists",
                translation_domain=DOMAIN,
                translation_key="saved_position_exists",
                translation_placeholders={"position": clean},
            )
        position = SavedPosition(uuid4().hex[:12], clean, button, self.current_targets(beds))
        self.positions.append(position)
        self.changed()
        return position

    def rename_position(
        self, position: SavedPosition, name: str, *, button: bool | None = None
    ) -> None:
        clean = _position_name(name)
        if any(
            item is not position and item.name.casefold() == clean.casefold()
            for item in self.positions
        ):
            raise ServiceValidationError(
                f"A saved position named {clean} already exists",
                translation_domain=DOMAIN,
                translation_key="saved_position_exists",
                translation_placeholders={"position": clean},
            )
        position.name = clean
        if button is not None:
            position.button = button
        self.changed()

    def update_position(self, position: SavedPosition) -> None:
        """Store the current estimates for the beds this position covers."""
        beds = [bed for key in position.targets if (bed := self.bed_for_key(key)) is not None]
        position.targets = self.current_targets(beds)
        self.changed()

    def delete_position(self, position: SavedPosition) -> None:
        self.positions.remove(position)
        self.changed()


def storage_key(entry_id: str) -> str:
    return f"{DOMAIN}.position_estimates_{entry_id}"


def _position_name(name: str) -> str:
    clean = " ".join(name.split())
    if not clean or len(clean) > MAX_POSITION_NAME_LENGTH:
        raise ServiceValidationError(
            "Saved position names need 1 to 40 characters",
            translation_domain=DOMAIN,
            translation_key="saved_position_name_invalid",
        )
    return clean


def _require_tracking(bed: BedEstimate, motors: Iterable[str]) -> None:
    if not bed.tracking(motors):
        raise ServiceValidationError(
            "The estimated position is not confirmed. Set the reference first",
            translation_domain=DOMAIN,
            translation_key="position_estimate_not_tracking",
        )


# ----------------------------------------------------------------- registry
def _registry(hass: HomeAssistant) -> dict[str, PositionEstimates]:
    registry: dict[str, PositionEstimates] = hass.data.setdefault(DOMAIN, {}).setdefault(
        _REGISTRY_KEY, {}
    )
    return registry


def position_estimates(hass: HomeAssistant, entry_id: str) -> PositionEstimates | None:
    return _registry(hass).get(entry_id)


async def async_setup_position_estimates(
    hass: HomeAssistant, entry_id: str, beds: Iterable[tuple[str, str | None]]
) -> PositionEstimates:
    """Load one entry's estimates before its platforms set up."""
    manager = PositionEstimates(hass, entry_id, beds)
    await manager.async_load()
    _registry(hass)[entry_id] = manager
    return manager


async def async_unload_position_estimates(hass: HomeAssistant, entry_id: str) -> None:
    manager = _registry(hass).pop(entry_id, None)
    if manager is not None:
        await manager.async_unload()


async def async_remove_position_estimates(hass: HomeAssistant, entry_id: str) -> None:
    hass.data.get(DOMAIN, {}).get(_SESSION_KEY, {}).pop(entry_id, None)
    await Store(hass, STORAGE_VERSION, storage_key(entry_id)).async_remove()


def _estimates_active(hass: HomeAssistant | None) -> bool:
    # Entities built outside Home Assistant (unit tests) have no hass yet.
    data = getattr(hass, "data", None)
    if not isinstance(data, dict):
        return False
    registry = data.get(DOMAIN, {}).get(_REGISTRY_KEY, {})
    return any(manager.active for manager in registry.values())


def _bed_for_coordinator(coordinator: object) -> BedEstimate | None:
    """Resolve the estimate of a physical coordinator by its entry and address."""
    hass = getattr(coordinator, "hass", None)
    entry_id = getattr(getattr(coordinator, "entry", None), "entry_id", None)
    address = getattr(coordinator, "address", None)
    if not isinstance(hass, HomeAssistant) or not isinstance(entry_id, str):
        return None
    if not isinstance(address, str):
        return None
    manager = _registry(hass).get(entry_id)
    return None if manager is None else manager.bed_for_address(address)


def _bed_for_controller(controller: object) -> BedEstimate | None:
    """Resolve the physical bed a controller command runs on."""
    from .beds.base import SideBoundController

    # Single-address pairs share one address for two sides and are not eligible.
    if isinstance(controller, SideBoundController):
        return None
    return _bed_for_coordinator(getattr(controller, "_coordinator", None))


def notify_connection_lost(coordinator: object) -> None:
    """Coordinator hook: the link of a physical bed dropped."""
    bed = _bed_for_coordinator(coordinator)
    if bed is not None:
        bed.abandon_moves(EstimateReason.CONNECTION_LOST)


def notify_release_failed(coordinator: object) -> None:
    """Controller hook: a movement cleanup STOP failed without raising."""
    bed = _bed_for_coordinator(coordinator)
    if bed is not None:
        bed.abandon_moves(EstimateReason.FAILED_MOVE)


# ------------------------------------------------------------ command wrappers
def _clock() -> float:
    return time.monotonic()


def _estimated_motors(controller: BedController, motor_key: str) -> tuple[str, ...] | None:
    groups: Mapping[str, tuple[str, ...]] = controller.estimated_position_motor_groups
    return groups.get(motor_key)


async def _run_tracked(
    bed: BedEstimate,
    motors: tuple[str, ...],
    direction: str,
    command: MotorCommand,
    controller: BedController,
) -> None:
    token = bed.begin_move(motors)
    started = _clock()
    try:
        await command(controller)
    except asyncio.CancelledError:
        # STOP or a replacing command ended the move; the stop time is known.
        bed.end_move(token, direction, _clock() - started)
        raise
    except BaseException:
        bed.end_move(token, direction, None)
        raise
    bed.end_move(token, direction, _clock() - started)


def track_motor_command(
    hass: HomeAssistant | None,
    motor_key: str,
    direction: str,
    command: MotorCommand,
) -> MotorCommand:
    """Time a motor control command, keyed like ``MotorControlSpec.key``.

    Wrap only the movement itself, so delays around it are not counted.
    """
    if not _estimates_active(hass):
        return command

    async def tracked(controller: BedController) -> None:
        bed = _bed_for_controller(controller)
        if bed is None or not bed.motors:
            await command(controller)
            return
        motors = _estimated_motors(controller, motor_key)
        if motors is None:
            bed.invalidate(EstimateReason.UNTRACKED_MOVE)
            await command(controller)
            return
        selected = tuple(motor for motor in motors if motor in bed.motors)
        if not selected:
            await command(controller)
            return
        await _run_tracked(bed, selected, direction, command, controller)

    return tracked


def track_held_control(
    hass: HomeAssistant | None, control: str, command: MotorCommand
) -> MotorCommand:
    """Time a held control that a motor spec declares; others make estimates unknown."""
    if not _estimates_active(hass):
        return command

    async def tracked(controller: BedController) -> None:
        bed = _bed_for_controller(controller)
        if bed is None or not bed.motors:
            await command(controller)
            return
        for spec in controller.motor_control_specs:
            hold = spec.hold
            if hold is None or control not in (hold.up_control, hold.down_control):
                continue
            motors = _estimated_motors(controller, spec.key)
            if motors is None:
                break
            selected = tuple(motor for motor in motors if motor in bed.motors)
            if not selected:
                await command(controller)
                return
            direction = "up" if control == hold.up_control else "down"
            await _run_tracked(bed, selected, direction, command, controller)
            return
        bed.invalidate(
            EstimateReason.HARDWARE_PRESET
            if control.startswith("memory_")
            else EstimateReason.UNTRACKED_MOVE
        )
        await command(controller)

    return tracked


def invalidate_on_command(
    hass: HomeAssistant | None,
    command: MotorCommand,
    reason: EstimateReason = EstimateReason.HARDWARE_PRESET,
) -> MotorCommand:
    """Mark estimates unknown before an untimed movement such as a hardware preset."""
    if not _estimates_active(hass):
        return command

    async def invalidating(controller: BedController) -> None:
        bed = _bed_for_controller(controller)
        if bed is not None:
            bed.invalidate(reason)
        await command(controller)

    return invalidating


# ------------------------------------------------------------------ movement
def _parent(hass: HomeAssistant, manager: PositionEstimates) -> Any:
    parent = hass.data.get(DOMAIN, {}).get(manager.entry_id)
    if parent is None:
        raise HomeAssistantError("The bed is not loaded")
    return parent


def _stop_epoch(parent: Any, bed: BedEstimate) -> int | None:
    from .paired_coordinator import PairedBedCoordinator

    owner = (
        parent.child_for_side(bed.side)
        if isinstance(parent, PairedBedCoordinator) and bed.side is not None
        else parent
    )
    scheduler = getattr(owner, "_command_scheduler", None)
    epoch = getattr(scheduler, "stop_epoch", None)
    return epoch if isinstance(epoch, int) else None


async def _async_timed_move(
    parent: Any, bed: BedEstimate, motor: str, direction: str, seconds: float
) -> None:
    from .services import _async_timed_move as timed_move

    await timed_move([(parent, bed.target_side)], motor, direction, round(seconds * 1000))


async def async_stop_bed(hass: HomeAssistant, manager: PositionEstimates, bed: BedEstimate) -> None:
    """STOP one estimated bed, or only its side of a pair."""
    from .paired_coordinator import PairedBedCoordinator

    parent = _parent(hass, manager)
    if isinstance(parent, PairedBedCoordinator):
        await parent.async_stop_command(side=bed.target_side)
    else:
        await parent.async_stop_command()


def _require_idle(beds: Iterable[BedEstimate]) -> None:
    """Plan only from a settled estimate; a running move would add travel later."""
    if any(bed.moving for bed in beds):
        raise ServiceValidationError(
            "The bed is moving. Stop it, then try again",
            translation_domain=DOMAIN,
            translation_key="position_estimate_moving",
        )


def _epochs(
    hass: HomeAssistant, manager: PositionEstimates, beds: Iterable[BedEstimate]
) -> dict[str, int | None]:
    """STOP ownership of a request, captured before it awaits anything."""
    parent = _parent(hass, manager)
    return {bed.address: _stop_epoch(parent, bed) for bed in beds}


async def async_move_bed(
    hass: HomeAssistant,
    manager: PositionEstimates,
    bed: BedEstimate,
    targets: Mapping[str, float],
    *,
    epoch: int | None = None,
    owned: bool = False,
) -> bool:
    """Move tracking motors to estimated targets one at a time.

    Returns False when STOP left a motor short of its target, and raises when a
    movement left an estimate unknown. Movements are ordinary timed moves
    through the coordinator, so each protocol keeps its cadence and STOP.
    """
    motors = [motor for motor in targets if motor in bed.motors]
    if not owned:
        _require_tracking(bed, motors)
        _require_idle([bed])
        epoch = _epochs(hass, manager, [bed])[bed.address]
    parent = _parent(hass, manager)
    for motor in motors:
        if _stop_epoch(parent, bed) != epoch:
            return False
        estimate = bed.motors[motor]
        plan = estimate.plan(targets[motor])
        if plan is not None and plan[1] * 1000 >= MIN_MOVE_MS:
            await _async_timed_move(parent, bed, motor, plan[0], plan[1])
        if estimate.state is not EstimateState.TRACKING:
            raise HomeAssistantError(
                "A movement failed, so the estimated position is unknown",
                translation_domain=DOMAIN,
                translation_key="position_estimate_move_failed",
            )
        if not _arrived(bed, motor, targets[motor]):
            return False
    return True


def _arrived(bed: BedEstimate, motor: str, target: float) -> bool:
    estimate = bed.motors[motor]
    return (
        estimate.state is EstimateState.TRACKING
        and estimate.percent is not None
        and abs(estimate.percent - _clamp(target)) <= ARRIVAL_TOLERANCE
    )


async def async_recall_position(
    hass: HomeAssistant, manager: PositionEstimates, position: SavedPosition
) -> None:
    """Move every bed a saved position covers; a bed that is not tracking blocks it.

    Sides move together. A side that fails stops the others, like any paired
    command; a side stopped by the user just reports the position not reached.
    """
    plans: list[tuple[BedEstimate, dict[str, float]]] = []
    for key, targets in position.targets.items():
        bed = manager.bed_for_key(key)
        # Every saved side and motor must still be estimated: recalling only
        # part of a position would report a position that was never reached.
        if bed is None or not targets or any(motor not in bed.motors for motor in targets):
            raise ServiceValidationError(
                f"{position.name} includes a motor that is no longer estimated",
                translation_domain=DOMAIN,
                translation_key="saved_position_unavailable",
                translation_placeholders={"position": position.name},
            )
        _require_tracking(bed, targets)
        plans.append((bed, dict(targets)))
    if not plans:
        raise ServiceValidationError(
            "This saved position has no calibrated motors",
            translation_domain=DOMAIN,
            translation_key="position_estimate_not_enabled",
        )
    _require_idle(bed for bed, _targets in plans)
    epochs = _epochs(hass, manager, (bed for bed, _targets in plans))
    tasks = {
        asyncio.create_task(
            async_move_bed(hass, manager, bed, targets, epoch=epochs[bed.address], owned=True)
        ): bed
        for bed, targets in plans
    }
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        failed = next((task for task in done if task.exception() is not None), None)
        if failed is not None:
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in pending:
                with contextlib.suppress(Exception):
                    await async_stop_bed(hass, manager, tasks[task])
            exception = failed.exception()
            assert exception is not None
            raise exception
    finally:
        # Cancelling the recall must not leave a side's cleanup running behind it.
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    if not all(task.result() for task in tasks):
        raise HomeAssistantError(
            f"{position.name} was not reached",
            translation_domain=DOMAIN,
            translation_key="saved_position_not_reached",
            translation_placeholders={"position": position.name},
        )


def lower_to_flat_seconds(estimate: MotorEstimate) -> float:
    """Full lowering time plus a margin, bounded like any movement."""
    if estimate.down_s is None:
        return 0.0
    return min(MAX_TRAVEL_S, estimate.down_s * LOWER_TO_FLAT_FACTOR + LOWER_TO_FLAT_EXTRA_S)


async def async_measure_move(
    hass: HomeAssistant, manager: PositionEstimates, bed: BedEstimate, motor: str, direction: str
) -> None:
    """Move one motor until STOP, bounded by the longest calibratable travel."""
    await _async_timed_move(_parent(hass, manager), bed, motor, direction, MAX_TRAVEL_S)


async def async_lower_to_flat(
    hass: HomeAssistant,
    manager: PositionEstimates,
    beds: Iterable[BedEstimate],
    motors: Iterable[str] | None = None,
) -> None:
    """Lower the selected motors past their full travel; the user then confirms flat.

    Only an explicit user request starts this. It never sets the reference. A
    STOP during any part of the request ends the whole request.
    """
    wanted = None if motors is None else list(motors)
    plans = [
        (bed, selected)
        for bed in beds
        if (
            selected := [
                motor
                for motor in (bed.motors if wanted is None else wanted)
                if motor in bed.motors and bed.motors[motor].calibrated
            ]
        )
    ]
    if not plans:
        raise ServiceValidationError(
            "No calibrated estimated motors to lower",
            translation_domain=DOMAIN,
            translation_key="position_estimate_not_enabled",
        )
    _require_idle(bed for bed, _motors in plans)
    epochs = _epochs(hass, manager, (bed for bed, _motors in plans))
    parent = _parent(hass, manager)

    def stopped() -> bool:
        return any(_stop_epoch(parent, bed) != epochs[bed.address] for bed, _motors in plans)

    for bed, selected in plans:
        for motor in selected:
            if stopped():
                return
            await _async_timed_move(
                parent, bed, motor, "down", lower_to_flat_seconds(bed.motors[motor])
            )
