"""Service registration for the Adjustable Bed integration.

Handlers live here as module-level functions rather than closures so they can be
read, tested, and type-checked independently of integration setup. Each one
recovers Home Assistant from ``call.hass``.

Every motion service is *sided*: a paired (Dual Bed) target fans out to one or
both sides, while a single bed behaves exactly as it always has.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
import math
from collections.abc import (
    AsyncIterator,
    Awaitable,
    Callable,
    Collection,
    Coroutine,
    Mapping,
    Sequence,
)
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Final, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.service import (
    async_get_device_and_config_entry,
    async_register_admin_service,
)
from homeassistant.util import dt as dt_util

from .alarm import (
    ALARM_SOUNDS,
    MASSAGE_ZONES,
    MATTRESS_SIDES,
    WAKE_ACTIONS,
    AlarmCapability,
    AlarmError,
    AlarmRequest,
)
from .alarm import OPTIONAL_FIELDS as ALARM_OPTIONAL_FIELDS
from .alarm import WEEKDAYS as ALARM_WEEKDAYS
from .bed_traits import bed_type_has_position_feedback
from .beds.base import BedController, controller_as
from .beds.entity_specs import POSITION_UNIT_DEGREES, POSITION_UNIT_PERCENT
from .command_scheduler import (
    ALL_COMMAND_RESOURCES,
    CommandOutcome,
    HoldClaim,
    HoldLease,
    HoldWindow,
    StaleHoldLease,
    command_resources,
    current_command_context,
)
from .command_target import capture_command_targets, command_target_scope
from .const import (
    BED_TYPE_ASKONA,
    BED_TYPE_ERGOMOTION,
    BED_TYPE_FURNIMOVE,
    BED_TYPE_KEESON,
    BED_TYPE_LANGJUE,
    BED_TYPE_LIMOSS_REMOTE,
    BED_TYPE_LINAK,
    BED_TYPE_OKIN_UUID,
    BED_TYPE_QPLUS_APP,
    BED_TYPE_SERTA_MP_REMOTE,
    BED_TYPE_SLEEP_NUMBER_MCR,
    BED_TYPE_SLEEPYS_ELITE_APP,
    BED_TYPE_STARCODE_M1X12,
    BED_TYPE_SVANE,
    BED_TYPE_SYMPHONY,
    BED_TYPE_ULTRAMATIC_SMART_BED,
    BED_TYPE_VMATBASIC,
    BED_TYPE_ZSERIES,
    CONF_BED_TYPE,
    CONF_MOTOR_COUNT,
    CONF_PROTOCOL_VARIANT,
    DEFAULT_MOTOR_COUNT,
    DOMAIN,
    PAIR_CONNECTION_MODE_CONCURRENT,
    PAIR_CONNECTION_MODE_SEQUENTIAL,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
    TIMED_MOVE_MOTOR_OPTIONS,
)
from .coordinator import AdjustableBedCoordinator
from .download import register_download
from .entity_runtime import controller_side_scope
from .errors import invalid, rejected
from .execution import HOLD_CEILING_MS
from .import_executor import async_import_modules
from .paired_coordinator import (
    BedChild,
    PairedBedCoordinator,
    SingleAddressPairedCoordinator,
    SingleAddressSideCoordinator,
)
from .paired_devices import side_identifier
from .paired_topology import (
    PairedSideError,
    ready_disconnected_transport,
)
from .pairing import is_paired, pair_member_addresses
from .position_estimate import (
    invalidate_on_command,
    track_held_control,
    track_motor_command,
    track_stream_member,
)
from .runtime_data import loaded_runtime
from .support_logs import async_setup_support_logs

if TYPE_CHECKING:
    from .beds.entity_specs import ControllerMotorHoldSpec
    from .beds.limoss.remote import LimossRemoteController
    from .beds.svane.controller import SvaneHoldAdmission

# Bed service modules build their errors with this name.
_invalid = invalid
_LOGGER = logging.getLogger(__name__)

# A service target: a single bed's coordinator, or a paired bed's parent.
BedTarget = BedChild | PairedBedCoordinator
# (target, physical side) pairs connected purely to validate a call, so a failed
# pre-flight can hand them back their idle timer.
PreflightedSides = list[tuple[BedTarget, BedChild]]


@dataclass(frozen=True, slots=True)
class _CommandAdmission:
    """STOP and pair ownership captured before a service preflight can await."""

    resources: frozenset[str]
    expected_pair_generations: dict[str, tuple[int, ...]]
    expected_stop_epochs: dict[str, int]
    command_targets: dict[int, str]


def _capture_command_admission(
    coordinator: BedTarget,
    side: str,
    resources: Collection[str] = ALL_COMMAND_RESOURCES,
) -> _CommandAdmission:
    """Capture the selected physical owners before live validation/connect waits."""
    scope = command_resources(*resources)
    if isinstance(coordinator, PairedBedCoordinator):
        targets = coordinator.targets_for(side)
        pair_generations = {
            target_side: coordinator.pair_cancel_generation(target_side, scope)
            for target_side, _child in targets
        }
    else:
        targets = [(SIDE_BOTH, coordinator)]
        pair_generations = {}

    stop_epochs: dict[str, int] = {}
    for target_side, child in targets:
        stop_epochs[target_side] = child.stop_epoch
    return _CommandAdmission(
        scope, pair_generations, stop_epochs, capture_command_targets(child for _, child in targets)
    )


# Service names
SERVICE_GOTO_PRESET = "goto_preset"
SERVICE_GENERATE_SUPPORT_BUNDLE = "generate_support_bundle"
SERVICE_SAVE_PRESET = "save_preset"
SERVICE_SET_POSITION = "set_position"
SERVICE_SET_POSITIONS = "set_positions"
SERVICE_STOP_ALL = "stop_all"
SERVICE_TIMED_MOVE = "timed_move"
SERVICE_HOLD_CONTROL = "hold_control"
SERVICE_RENAME = "rename"
SERVICE_SYNC_CLOCK = "sync_clock"
SERVICE_SET_ALARM = "set_alarm"
ATTR_SLOT = "slot"

# Service call attributes
ATTR_PRESET = "preset"
ATTR_MOTOR = "motor"
ATTR_POSITION = "position"
ATTR_POSITIONS = "positions"
ATTR_TARGET_ADDRESS = "target_address"
ATTR_CAPTURE_DURATION = "capture_duration"
ATTR_INCLUDE_LOGS = "include_logs"
ATTR_DIRECTION = "direction"
ATTR_DURATION_MS = "duration_ms"
ATTR_HOLD_OWNER = "hold_owner"
ATTR_HOLD_GENERATION = "hold_generation"
ATTR_DURATION = "duration"
ATTR_SIDE = "side"
ATTR_FIRST_MOTOR = "first_motor"
ATTR_FIRST_DIRECTION = "first_direction"
ATTR_SECOND_MOTOR = "second_motor"
ATTR_SECOND_DIRECTION = "second_direction"
ATTR_NAME = "name"
ATTR_ACTIONS = "actions"
ATTR_ACTION = "action"
ATTR_ENABLED = "enabled"
ATTR_TIME = "time"
ATTR_WEEKDAYS = "weekdays"
ATTR_MASSAGE = "massage"
ATTR_SOUND = "sound"
ATTR_TRACK = "track"
ATTR_VOLUME = "volume"
ATTR_MINUTES = "minutes"
ATTR_CONTROL = "control"
ATTR_HEAD_LEVEL = "head_level"
ATTR_FOOT_LEVEL = "foot_level"



POSITION_MOTOR_OPTIONS = (
    "back",
    "legs",
    "head",
    "feet",
    "lumbar",
    "left_back",
    "right_back",
    "left_legs",
    "right_legs",
)


# Default capture duration for diagnostics (seconds)
DEFAULT_CAPTURE_DURATION = 120

# Bound for the best-effort pre-capture log probe. Generous for a local stat,
# short enough that a stalled mount cannot delay the capture noticeably.
_LOG_PROBE_TIMEOUT = 5.0

# hass.data key: notification id -> tokens of the invocations that raised it.
_LOG_NOTICE_OWNERS = f"{DOMAIN}_log_notice_owners"
MIN_CAPTURE_DURATION = 10
MAX_CAPTURE_DURATION = 300

# Timed move duration limits (milliseconds)
MIN_TIMED_MOVE_DURATION_MS = 100
MAX_TIMED_MOVE_DURATION_MS = 30000  # 30 seconds max
# A renewable hold (#483) lasts each call's lease within these bounds. The
# ceiling also bounds one hold in total: it never streams past it, however
# often it is renewed.
MIN_HOLD_LEASE_MS = MIN_TIMED_MOVE_DURATION_MS
MAX_HOLD_LEASE_MS = HOLD_CEILING_MS
HOLD_LEASE_FIELDS = {
    vol.Inclusive(ATTR_HOLD_OWNER, "hold_lease"): vol.All(
        cv.string, vol.Length(min=1, max=64)
    ),
    vol.Inclusive(ATTR_HOLD_GENERATION, "hold_lease"): vol.All(
        vol.Coerce(int), vol.Range(min=0, max=2**53)
    ),
}


# Optional left/right/both target (paired beds). No default: when omitted, a call
# that targets one side's child device acts on just that side, otherwise it falls
# back to 'both' - so single-bed automations are unchanged.
SIDE_FIELD = {vol.Optional(ATTR_SIDE): vol.In([SIDE_LEFT, SIDE_RIGHT, SIDE_BOTH])}
# One or more target devices, for actions that act on every selected bed.
DEVICE_IDS = vol.All(cv.ensure_list, vol.Length(min=1))


def local_datetime(value: object) -> datetime:
    """A date and time; one without a zone, as the action form sends it, is local time."""
    when = cv.datetime(value)
    return when if when.tzinfo else when.replace(tzinfo=dt_util.get_default_time_zone())


def _resolve_sided_target(
    hass: HomeAssistant, device_id: str
) -> tuple[BedTarget, str | None] | None:
    """Resolve (coordinator, inferred_side) for a sided service target.

    ``inferred_side`` is the left/right of a targeted paired child sub-device
    (matched by its MAC identifier), or ``None`` for a single bed or the
    paired parent device. Lets a caller targeting one side's device act on
    just that side without passing ``side`` explicitly. ``SIDE_BOTH`` marks a
    device of a paired entry that is neither a side nor the pair itself.
    """
    selected = dr.async_get(hass).async_get(device_id)
    # HA's validation helper accepts full devices only. Validate a native
    # child's parent, then retain the child for side routing.
    validation_id = (
        selected.parent_device_id if isinstance(selected, dr.ChildDeviceEntry) else device_id
    )
    device, entry = async_get_device_and_config_entry(hass, DOMAIN, validation_id)
    if isinstance(selected, dr.ChildDeviceEntry):
        device = selected
    coordinator = loaded_runtime(hass, entry.entry_id)
    if coordinator is None:
        return None
    inferred_side: str | None = None
    if isinstance(coordinator, PairedBedCoordinator):
        identifiers = {value.upper() for domain, value in device.identifiers if domain == DOMAIN}
        for side in coordinator.children:
            if side_identifier(coordinator, side)[1].upper() in identifiers:
                inferred_side = side
                break
        parent_identifiers = coordinator.device_info.identifiers
        is_parent = isinstance(parent_identifiers, set) and any(
            domain == DOMAIN and value.upper() in identifiers
            for domain, value in parent_identifiers
        )
        if inferred_side is None and not is_parent:
            inferred_side = SIDE_BOTH
    return coordinator, inferred_side


def _resolve_sided_targets(
    hass: HomeAssistant,
    device_ids: list[str],
    explicit_side: str | None,
    *,
    problems: list[BaseException] | None = None,
) -> tuple[list[tuple[BedTarget, str]], list[str]]:
    """Group sided-service targets by coordinator, merging inferred sides.

    Targeting both of a pair's child devices (or the parent) in one call
    collapses to a single ``both`` fan-out - preserving the both-failure
    contract - instead of two separate side commands. Each coordinator
    appears once in first-seen order. Returns (targets, missing_device_ids).

    With ``problems`` (STOP), nothing raises: a device that cannot be resolved
    is recorded there and skipped, and a side that cannot be honoured is
    recorded and widened to the whole bed, so every reachable bed still stops.
    """
    ordered: list[int] = []
    by_key: dict[int, tuple[BedTarget, set[str | None]]] = {}
    missing: list[str] = []
    for device_id in device_ids:
        try:
            resolved = _resolve_sided_target(hass, device_id)
        except Exception as err:
            if problems is None:
                raise
            problems.append(err)
            continue
        if resolved is None:
            if problems is not None:
                problems.append(invalid("devices_not_found", device_ids=device_id))
            missing.append(device_id)
            continue
        coordinator, inferred_side = resolved
        problem: ServiceValidationError | None = None
        if inferred_side == SIDE_BOTH:
            problem = invalid("side_unavailable")
        elif inferred_side is not None and explicit_side not in (None, inferred_side):
            problem = invalid(
                "side_selection_conflict", inferred_side=inferred_side, side=explicit_side
            )
        if problem is not None:
            if problems is None:
                raise problem
            problems.append(problem)
            inferred_side = SIDE_BOTH
        key = id(coordinator)
        if key not in by_key:
            by_key[key] = (coordinator, set())
            ordered.append(key)
        by_key[key][1].add(inferred_side)

    targets: list[tuple[BedTarget, str]] = []
    for key in ordered:
        coordinator, sides = by_key[key]
        if SIDE_BOTH in sides:
            # Only a STOP whose side could not be honoured gets here.
            side = SIDE_BOTH
        elif explicit_side is not None:
            side = explicit_side
        elif sides == {SIDE_LEFT}:
            side = SIDE_LEFT
        elif sides == {SIDE_RIGHT}:
            side = SIDE_RIGHT
        else:
            # parent device (None), both children, or a mix -> whole bed.
            side = SIDE_BOTH
        targets.append((coordinator, side))
    return targets, missing


def _whole_number(value: object) -> int:
    """Accept a whole number, also as 2.0 or "2"; reject Booleans and fractions."""
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        # YAML accepts .inf and .nan, which have no whole-number value.
        or (isinstance(value, float) and not math.isfinite(value))
        or value != int(value)
    ):
        raise invalid("whole_number_required", value=value)
    return int(value)


def _validation_error(err: ValueError) -> ServiceValidationError:
    """Turn a controller's rejection into a validation error, translated where it can be."""
    key = getattr(err, "translation_key", None)
    if key is None:
        return rejected(err)
    return invalid(key, **(getattr(err, "translation_placeholders", None) or {}))


def _missing_device_error(device_id: str) -> ServiceValidationError:
    """Build the error for a service target that resolved to no bed."""
    return invalid("device_not_found", device_id=device_id)


def _get_support_bundle_target_from_device(
    hass: HomeAssistant, device_id: str
) -> tuple[str, BedChild | None, ConfigEntry] | None:
    """Resolve support-bundle target details from a device registry ID."""
    selected = dr.async_get(hass).async_get(device_id)
    validation_id = (
        selected.parent_device_id if isinstance(selected, dr.ChildDeviceEntry) else device_id
    )
    device, entry = dr.async_get_device_and_config_entry_for_domain(
        hass, validation_id, domain=DOMAIN
    )
    if isinstance(selected, dr.ChildDeviceEntry):
        device = selected
    if device is None or entry is None:
        return None
    entry_id = entry.entry_id
    address = entry.data.get(CONF_ADDRESS)
    if not isinstance(address, str) and is_paired(entry.data):
        # Paired entries keep addresses only in pair_children. Resolve to
        # the targeted child sub-device's MAC (else the first member) so
        # the bundle can still capture BLE/GATT for that side by address.
        members = pair_member_addresses(entry.data)
        device_macs = {ident[1].upper() for ident in device.identifiers if ident[0] == DOMAIN}
        address = next((m for m in members if m in device_macs), None)
        if address is None and members:
            # The synthetic parent device (pair_id identifier) covers both
            # sides; a bundle is per-address, so make the user pick one
            # side's device instead of silently capturing only the first.
            raise invalid("bundle_needs_side_for_paired", device_name=entry.title)
    if not isinstance(address, str):
        return None

    coordinator: BedChild | None = None
    stored = loaded_runtime(hass, entry_id)
    if isinstance(stored, PairedBedCoordinator):
        # Reuse the matching live child coordinator so the bundle pauses
        # and reuses its connection instead of opening a second BLE link
        # (single-connection beds can't take two).
        for child in stored.children.values():
            if child.address.upper() == address.upper():
                coordinator = child
                break
    else:
        coordinator = cast("BedChild | None", stored)
    return address, coordinator, entry


def _require_disconnected_transport_ready(target: BedChild, controller: BedController) -> None:
    """Refuse a controller whose selected non-central transport cannot take commands."""
    if controller.requires_disconnected_transport and not controller.disconnected_transport_ready:
        raise invalid(
            "pairlink_not_ready",
            device_name=target.name,
        )


async def _get_controller_for_service(
    coordinator: BedChild,
) -> BedController:
    """Return an active controller for service validation/execution.

    Service calls may arrive while the coordinator is idle-disconnected and
    controller is None. Reconnect first so capability checks don't fail with
    a false "not supported" error.
    """
    controller = coordinator.controller
    if controller is not None:
        _require_disconnected_transport_ready(coordinator, controller)
        return controller

    capability_controller = coordinator.capability_controller
    if capability_controller is not None and capability_controller.requires_disconnected_transport:
        _require_disconnected_transport_ready(coordinator, capability_controller)
        return capability_controller

    if coordinator.pairlink_peripheral:
        raise invalid(
            "pairlink_not_ready",
            device_name=coordinator.name,
        )

    _LOGGER.debug(
        "No active controller for %s during service call; attempting reconnect",
        coordinator.name,
    )
    connected = await coordinator.async_ensure_connected(reset_timer=False)
    controller = coordinator.controller
    if not connected or controller is None:
        raise invalid(
            "bed_unavailable",
            device_name=coordinator.name,
        )
    return controller


async def _validation_controller(
    coordinator: BedTarget,
    target: BedChild,
    preflighted: PreflightedSides,
) -> BedController:
    """Return a controller for capability VALIDATION without opening a BLE link
    when avoidable.

    Prefer the side's ``capability_controller`` - the live controller, or a
    client-free one minted from config/snapshot - so we read capabilities
    without connecting. That matters for single-connection (Octo) pairs: the
    preflight validates EVERY targeted side before commanding any, and
    connecting each side to validate would momentarily hold two BLE links,
    which the sequential profile must never do. Only connect (and track the
    side in ``preflighted`` for release on failure) when no capability
    controller exists - a non-offline-mintable bed that is currently
    disconnected.
    """
    controller = target.capability_controller
    if controller is not None:
        _require_disconnected_transport_ready(target, controller)
        return controller
    controller = await _get_controller_for_service(target)
    preflighted.append((coordinator, target))
    return controller


def _command_targets(coordinator: BedTarget, side: str) -> list[BedChild]:
    """Return the per-side coordinators a sided command must validate.

    For a paired bed this is the child coordinator(s) for ``side``; the
    caller validates each (pre-flight all sides before commanding any) and
    then executes via the paired coordinator's fan-out. For a single bed,
    ``left``/``right`` is rejected and ``both`` maps to the one controller.
    """
    if isinstance(coordinator, PairedBedCoordinator):
        if side == SIDE_BOTH:
            return list(coordinator.children.values())
        child = coordinator.child_for_side(side)
        if child is None:
            raise invalid("side_not_available", side=side)
        return [child]

    if side != SIDE_BOTH:
        raise invalid("side_not_supported")
    return [coordinator]


async def _execute_sided(
    coordinator: BedTarget,
    side: str,
    command_fn: Callable[[BedController], Coroutine[Any, Any, None]],
    *,
    cancel_running: bool = True,
    skip_disconnect: bool = False,
    resource: str | None = None,
    resources: Collection[str] | None = None,
    admission: _CommandAdmission | None = None,
    expected_stop_epoch: int | None = None,
    expected_pair_generations: Mapping[str, tuple[int, ...]] | None = None,
    expected_stop_epochs: Mapping[str, int] | None = None,
    lease: HoldLease | None = None,
) -> None:
    """Run a command on the targeted side(s).

    A paired bed fans out (with the both-failure stop-the-other contract); a
    single bed runs exactly as before. A ``lease`` makes it a renewable hold.
    """
    if admission is not None:
        expected_pair_generations = admission.expected_pair_generations
        expected_stop_epochs = admission.expected_stop_epochs
        expected_stop_epoch = admission.expected_stop_epochs.get(SIDE_BOTH)
    with command_target_scope(admission.command_targets if admission is not None else None):
        if isinstance(coordinator, PairedBedCoordinator):
            await coordinator.async_execute_controller_command(
                command_fn,
                side=side,
                cancel_running=cancel_running,
                skip_disconnect=skip_disconnect,
                resource=resource,
                resources=resources,
                expected_pair_generations=expected_pair_generations,
                expected_stop_epochs=expected_stop_epochs,
                lease=lease,
            )
        else:
            await coordinator.async_execute_controller_command(
                command_fn,
                cancel_running=cancel_running,
                skip_disconnect=skip_disconnect,
                resource=resource,
                resources=resources,
                expected_stop_epoch=expected_stop_epoch,
                lease=lease,
            )


async def _execute_sided_translated(
    coordinator: BedTarget,
    side: str,
    command_fn: Callable[[BedController], Coroutine[Any, Any, None]],
    **kwargs: Any,
) -> None:
    """Run ``_execute_sided``, surfacing a combined bed's one translated side error.

    A combined bed wraps each side's failure in one combined error. When only
    one thing failed and it is a request the user can correct, raise that error
    instead, with the combined one as cause. More failures keep the combined
    error, which names each one.
    """
    try:
        await _execute_sided(coordinator, side, command_fn, **kwargs)
    except PairedSideError as err:
        [*errors] = err.side_errors.values()
        if (
            len(errors) == 1
            and isinstance(errors[0], ServiceValidationError)
            and errors[0].translation_key
        ):
            raise errors[0] from err
        raise


@dataclass(slots=True)
class _LiveCheck:
    """A preflight check, run again on any controller it has not checked.

    Preflight may check a cached or offline controller, and the one that
    connects can differ. A side the writing controller rejects is refused
    with that controller's own reason instead of being written.
    """

    check: Callable[[BedChild, BedController], None]
    checked: list[BedController] = field(default_factory=list)

    def preflight(self, target: BedChild, controller: BedController) -> None:
        self.check(target, controller)
        self.checked.append(controller)

    def command(
        self,
        targets: Sequence[tuple[BedTarget, str]],
        command: Callable[[BedController], Coroutine[Any, Any, None]],
    ) -> Callable[[BedController], Coroutine[Any, Any, None]]:
        physical = [
            target for parent, side in targets for target in _command_targets(parent, side)
        ]

        async def run(controller: BedController) -> None:
            if all(controller is not checked for checked in self.checked):
                # The scheduler has already bound a combined bed's side.
                target = next(
                    (item for item in physical if item.controller is controller), physical[0]
                )
                try:
                    self.check(target, controller)
                except ValueError as err:
                    # The same rejection preflight would have shown.
                    raise _validation_error(err) from err
            await command(controller)

        return run


def _bed_changed() -> ServiceValidationError:
    return invalid("bed_changed")


def _pair_mode(parent: BedTarget) -> str | None:
    return parent.connection_mode if isinstance(parent, PairedBedCoordinator) else None


def _child_side(parent: BedTarget, side: str, child: BedChild) -> str:
    """Return the side that runs ``child`` on its own."""
    if not isinstance(parent, PairedBedCoordinator):
        return side
    return next(name for name, item in parent.children.items() if item is child)


def _stop_marks(
    targets: Sequence[tuple[BedTarget, str]], children: Sequence[Sequence[BedChild]]
) -> tuple[int, ...]:
    """Counters that only a STOP advances, for every selected side.

    Commands preempting each other never move them, so a call can tell a
    user's STOP apart from its own earlier steps.
    """
    marks: list[int] = []
    for (parent, side), group in zip(targets, children, strict=True):
        if isinstance(parent, PairedBedCoordinator):
            sides = (SIDE_LEFT, SIDE_RIGHT) if side == SIDE_BOTH else (side,)
            marks.extend(parent.stop_count(name) for name in sides)
            marks.extend(child.stop_epoch for child in group)
        else:
            marks.append(parent.stop_epoch)
    return tuple(marks)


@dataclass(frozen=True, slots=True)
class _Selection:
    """The physical sides a call selected, captured before its first await."""

    targets: tuple[tuple[BedTarget, str], ...]
    children: tuple[tuple[BedChild, ...], ...]
    modes: tuple[str | None, ...]
    stops: tuple[int, ...]

    @classmethod
    def capture(cls, targets: Sequence[tuple[BedTarget, str]]) -> _Selection:
        children = tuple(tuple(_command_targets(parent, side)) for parent, side in targets)
        return cls(
            tuple(targets),
            children,
            tuple(_pair_mode(parent) for parent, _ in targets),
            _stop_marks(targets, children),
        )

    def stopped(self) -> bool:
        """Return whether a STOP reached any selected side since the capture."""
        return _stop_marks(self.targets, self.children) != self.stops

    def require_unchanged(self, call: ServiceCall) -> None:
        """Refuse a selection whose beds were replaced, removed or re-paired."""
        try:
            current = _call_targets(call)
            children = [tuple(_command_targets(parent, side)) for parent, side in current]
        except ServiceValidationError as err:
            raise _bed_changed() from err
        same = (
            len(current) == len(self.targets)
            and all(
                parent is old_parent and side == old_side
                for (parent, side), (old_parent, old_side) in zip(
                    current, self.targets, strict=True
                )
            )
            and all(
                len(group) == len(old)
                and all(child is old_child for child, old_child in zip(group, old, strict=True))
                for group, old in zip(children, self.children, strict=True)
            )
            and tuple(_pair_mode(parent) for parent, _ in current) == self.modes
        )
        if not same:
            raise _bed_changed()


async def _release_preflighted(preflighted: PreflightedSides) -> None:
    """Give every bed/side connected during a failed pre-flight a normal idle
    disconnect, so a validation abort doesn't leave a BLE link open with no
    idle timer (the command finalizer that would reset it never ran). Applies
    to single beds too, not just paired sides - both reconnect with
    reset_timer=False during validation."""
    for _coordinator, target in preflighted:
        if target.is_connected:
            with contextlib.suppress(Exception):
                await target.async_ensure_connected(reset_timer=True)


@contextlib.asynccontextmanager
async def _side_validation(
    parent: BedTarget,
    coordinator: BedChild,
    preflighted: PreflightedSides,
) -> AsyncIterator[BedController]:
    """Yield one side's validation controller, bound to that side.

    Release a bed reconnected for a per-motor service if validation fails.
    _get_controller_for_service reconnects with reset_timer=False; without
    this an invalid set_position/timed_move would leave the BLE link open
    with no idle timer (the preset preflight path already guards this way)."""
    try:
        controller = await _validation_controller(parent, coordinator, preflighted)
        with controller_side_scope(coordinator):
            yield controller
    except ServiceValidationError:
        if coordinator.is_connected:
            with contextlib.suppress(Exception):
                await coordinator.async_ensure_connected(reset_timer=True)
        raise


def _plan_key(target: BedChild) -> int:
    """Stable per-side key for a validated plan (a proxy shares its child's identity)."""
    return target.operation_identity


def _timed_move_resource(target: BedChild, motor: str) -> str:
    """Read the selected motor's existing scheduler resource without awaiting."""
    controller = target.capability_controller
    if controller is not None:
        with controller_side_scope(target):
            spec = next(
                (item for item in controller.motor_control_specs if item.key == motor),
                None,
            )
        if spec is not None:
            return spec.scheduler_resource or f"motor:{spec.position_key or spec.key}"
    return f"motor:{motor}"


def _require_preset_slot(target: BedChild, controller: BedController, preset: int) -> None:
    """Reject a memory preset beyond the controller's slot count."""
    slot_count = controller.memory_slot_count
    if preset > slot_count:
        raise invalid("invalid_preset_number", device_name=target.name, max_preset=str(slot_count), requested_preset=str(preset))


async def handle_goto_preset(call: ServiceCall) -> None:
    """Handle goto_preset service call with sided all-target preflight."""
    from .beds.limoss.remote_services import (
        _limoss_remote_reload_transaction,
        _preflight_live_limoss_remote,
    )

    hass = call.hass
    preset = call.data[ATTR_PRESET]
    device_ids = call.data.get(CONF_DEVICE_ID, [])
    explicit_side = call.data.get(ATTR_SIDE)
    duration = call.data.get(ATTR_DURATION)
    # None keeps each controller's own recall gesture.
    hold_ms = None if duration is None else int(duration * 1000)

    _LOGGER.info(
        "Service goto_preset called: preset=%d, hold_ms=%s (side=%s)",
        preset,
        hold_ms,
        explicit_side,
    )

    targets, missing = _resolve_sided_targets(hass, device_ids, explicit_side)
    if missing:
        raise _missing_device_error(missing[0])

    def check(target: BedChild, controller: BedController) -> None:
        if not controller.supports_memory_presets:
            raise invalid("memory_presets_not_supported", device_name=target.name)
        _require_preset_slot(target, controller, preset)
        if hold_ms is not None and not controller.supports_memory_recall_duration(preset):
            raise invalid("preset_duration_not_supported", device_name=target.name)
        try:
            controller.validate_memory_recall(preset)
        except ValueError as error:
            raise rejected(error) from error

    async def recall(controller: BedController) -> None:
        if hold_ms is None:
            await controller.preset_memory(preset)
        else:
            await controller.recall_memory(preset, hold_ms=hold_ms)

    admissions = [_capture_command_admission(coordinator, side) for coordinator, side in targets]
    async with _limoss_remote_reload_transaction(targets):
        await _preflight_live_limoss_remote(
            targets, lambda ctrl: ctrl.validate_memory_recall(preset)
        )
        # Validate the preset on EVERY targeted side before moving any bed, so a
        # multi-target call never half-executes.
        live = _LiveCheck(check)
        preflighted = await _preflight_each(targets, live.preflight)
        command = invalidate_on_command(hass, live.command(targets, recall))
        # Every target validated - now move them. If one bed's command fails,
        # release the still-connected preflighted beds that never ran (and so
        # never reset their idle timer) before propagating.
        try:
            for (coordinator, side), admission in zip(targets, admissions, strict=True):
                await _execute_sided(coordinator, side, command, admission=admission)
        except Exception:
            await _release_preflighted(preflighted)
            raise


async def handle_save_preset(call: ServiceCall) -> None:
    """Handle save_preset service call with sided all-target preflight."""
    from .beds.limoss.remote_services import (
        _limoss_remote_reload_transaction,
        _preflight_live_limoss_remote,
    )

    hass = call.hass
    preset = call.data[ATTR_PRESET]
    device_ids = call.data.get(CONF_DEVICE_ID, [])
    explicit_side = call.data.get(ATTR_SIDE)

    _LOGGER.info("Service save_preset called: preset=%d (side=%s)", preset, explicit_side)

    targets, missing = _resolve_sided_targets(hass, device_ids, explicit_side)
    if missing:
        raise _missing_device_error(missing[0])

    admissions = [_capture_command_admission(coordinator, side) for coordinator, side in targets]

    def check(target: BedChild, controller: BedController) -> None:
        if not controller.supports_memory_programming:
            raise invalid("memory_programming_not_supported", device_name=target.name)
        _require_preset_slot(target, controller, preset)

    def validate_remote_slot(controller: LimossRemoteController) -> None:
        if (
            not controller.supports_memory_programming
            or not 1 <= preset <= controller.memory_slot_count
        ):
            raise ValueError("This remote cannot save to that memory position. Choose another position")

    async with _limoss_remote_reload_transaction(targets):
        await _preflight_live_limoss_remote(targets, validate_remote_slot)

        # Validate that every targeted side can program this slot before
        # programming any, so a multi-target call never half-executes.
        live = _LiveCheck(check)
        preflighted = await _preflight_each(targets, live.preflight)
        program = live.command(targets, lambda ctrl: ctrl.program_memory(preset))
        # Every target validated - now program them. Release any
        # still-connected preflighted bed that never ran if one fails.
        try:
            for (coordinator, side), admission in zip(targets, admissions, strict=True):
                await _execute_sided_translated(
                    coordinator, side, program, cancel_running=False, admission=admission
                )
        except Exception:
            await _release_preflighted(preflighted)
            raise


async def handle_stop_all(call: ServiceCall) -> None:
    """Handle stop_all service call."""
    hass = call.hass
    device_ids = call.data.get(CONF_DEVICE_ID, [])
    explicit_side = call.data.get(ATTR_SIDE)

    _LOGGER.info("Service stop_all called (side=%s)", explicit_side)

    # STOP is a safety action: attempt every bed that resolves before surfacing
    # an error, so one bad target never leaves another bed still moving.
    problems: list[BaseException] = []
    targets, _missing = _resolve_sided_targets(hass, device_ids, explicit_side, problems=problems)

    async def _stop_one(coordinator: BedTarget, side: str) -> None:
        try:
            _command_targets(coordinator, side)
        except ServiceValidationError as err:
            # A side this bed does not have stops the whole bed.
            problems.append(err)
            side = SIDE_BOTH
        if isinstance(coordinator, PairedBedCoordinator):
            await coordinator.async_stop_command(side=side)
        else:
            await coordinator.async_stop_command()

    results = await asyncio.gather(
        *(_stop_one(coordinator, side) for coordinator, side in targets),
        return_exceptions=True,
    )
    problems.extend(r for r in results if isinstance(r, BaseException))
    if problems:
        raise problems[0]


async def _set_position_plan(
    parent: BedTarget,
    coordinator: BedChild,
    preflighted: PreflightedSides,
    motor: str,
    position: float,
) -> dict[str, Any]:
    """Validate one physical side and return its seek configuration."""
    async with _side_validation(parent, coordinator, preflighted) as controller:
        return _position_config(coordinator, controller, motor, position)


def _position_config(
    coordinator: BedChild, controller: BedController, motor: str, position: float
) -> dict[str, Any]:
    """Check one motor target against ``controller`` and return its seek configuration."""
    # Bed type / motor count come from the coordinator's own entry (the
    # child's ChildEntryView for a paired-side target - children aren't in
    # hass.data, so don't scan it).
    entry = coordinator.entry
    bed_type = entry.data.get(CONF_BED_TYPE)
    motor_count = entry.data.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT)
    protocol_variant = entry.data.get(CONF_PROTOCOL_VARIANT)
    supports_direct_position_control = controller.supports_direct_position_control

    # Validate bed supports position feedback. Q-Plus's MX layout and an Okin
    # UUID receiver without the position characteristic report none; M1X12 and
    # the Elite app's control boxes without a target offer no slider.
    if (
        not bed_type_has_position_feedback(bed_type, protocol_variant)
        or (
            bed_type in (BED_TYPE_QPLUS_APP, BED_TYPE_OKIN_UUID)
            and not controller.supports_position_feedback
        )
        or (
            bed_type in (BED_TYPE_SLEEPYS_ELITE_APP, BED_TYPE_STARCODE_M1X12)
            and not controller.position_number_specs
        )
    ) and not supports_direct_position_control:
        raise invalid("position_feedback_not_supported", device_name=coordinator.name)

    # Validate angle sensing is enabled
    if coordinator.disable_angle_sensing:
        raise invalid("angle_sensing_disabled", device_name=coordinator.name)

    # Define motor configurations.
    # Direct setters with percentage sliders (Kaidi, BOX25 and others) and
    # setters with their own native bounds target their position sliders.
    # For Keeson/Ergomotion: only head and feet are valid, they map to back/legs keys.
    # For standard beds: based on motor_count (2=back/legs, 3=+head, 4=+feet).
    specs = controller.position_number_specs
    # A percentage bed with no sliders (for example articulation disabled)
    # keeps an empty axis set rather than falling back to generic motors.
    percentage_targets = controller.reports_percentage_position is True or (
        bool(specs)
        and all(spec.native_unit_of_measurement == POSITION_UNIT_PERCENT for spec in specs)
    )
    # Q-Plus reports back/legs only, within its pulse tables.
    if bed_type in (BED_TYPE_ASKONA, BED_TYPE_SLEEP_NUMBER_MCR, BED_TYPE_SERTA_MP_REMOTE, BED_TYPE_QPLUS_APP) or (
        percentage_targets and (supports_direct_position_control or not specs)
    ):
        motor_configs = {
            spec.position_key: {
                "position_key": spec.position_key,
                "move_up_fn": spec.open_fn,
                "move_down_fn": spec.close_fn,
                "move_stop_fn": spec.stop_fn,
                "max_value": spec.native_max_value,
                "unit": spec.native_unit_of_measurement,
            }
            for spec in specs
        }
        valid_motors = set(motor_configs)
    elif bed_type in (BED_TYPE_KEESON, BED_TYPE_ERGOMOTION):
        # Keeson/Ergomotion only have head and feet motors
        valid_motors = {"head", "feet"}
        motor_configs = {
            "head": {
                "position_key": "back",  # Maps to "back" in position_data
                "move_up_fn": lambda ctrl: ctrl.move_head_up(),
                "move_down_fn": lambda ctrl: ctrl.move_head_down(),
                "move_stop_fn": lambda ctrl: ctrl.move_head_stop(),
                "max_value": 100.0,  # Percentage
            },
            "feet": {
                "position_key": "legs",  # Maps to "legs" in position_data
                "move_up_fn": lambda ctrl: ctrl.move_feet_up(),
                "move_down_fn": lambda ctrl: ctrl.move_feet_down(),
                "move_stop_fn": lambda ctrl: ctrl.move_feet_stop(),
                "max_value": 100.0,  # Percentage
            },
        }
    else:
        # Standard beds: motor availability depends on motor_count
        motor_configs = {
            "back": {
                "position_key": "back",
                "move_up_fn": lambda ctrl: ctrl.move_back_up(),
                "move_down_fn": lambda ctrl: ctrl.move_back_down(),
                "move_stop_fn": lambda ctrl: ctrl.move_back_stop(),
                "max_value": coordinator.get_max_angle("back"),  # Degrees
                "min_motors": 2,
            },
            "legs": {
                "position_key": "legs",
                "move_up_fn": lambda ctrl: ctrl.move_legs_up(),
                "move_down_fn": lambda ctrl: ctrl.move_legs_down(),
                "move_stop_fn": lambda ctrl: ctrl.move_legs_stop(),
                "max_value": coordinator.get_max_angle("legs"),  # Degrees
                "min_motors": 2,
            },
            "head": {
                "position_key": "head",
                "move_up_fn": lambda ctrl: ctrl.move_head_up(),
                "move_down_fn": lambda ctrl: ctrl.move_head_down(),
                "move_stop_fn": lambda ctrl: ctrl.move_head_stop(),
                "max_value": coordinator.get_max_angle("head"),  # Degrees
                "min_motors": 3,
            },
            "feet": {
                "position_key": "feet",
                "move_up_fn": lambda ctrl: ctrl.move_feet_up(),
                "move_down_fn": lambda ctrl: ctrl.move_feet_down(),
                "move_stop_fn": lambda ctrl: ctrl.move_feet_stop(),
                "max_value": coordinator.get_max_angle("feet"),  # Degrees
                "min_motors": 4,
            },
        }
        if bed_type == BED_TYPE_LINAK:
            valid_motors = {spec.position_key for spec in controller.position_number_specs}
        else:
            # Filter standard beds to motors enabled by their configured count.
            valid_motors = {
                motor
                for motor, config in motor_configs.items()
                if motor_count >= config.get("min_motors", 2)
            }

    # Validate motor is valid for this bed
    if motor not in valid_motors:
        raise invalid("invalid_motor_for_bed_type", motor=motor, device_name=coordinator.name, valid_motors=", ".join(sorted(valid_motors)))

    config = motor_configs[motor]
    max_value = config["max_value"]

    # Validate position is in range
    if position < 0 or position > max_value:
        unit = config.get("unit") or (
            POSITION_UNIT_PERCENT
            if controller.reports_percentage_position is True
            else POSITION_UNIT_DEGREES
        )
        raise invalid("invalid_position_range", position=str(position), motor=motor, max_value=str(max_value), unit=unit)

    return {**config, "combine_targets": controller.supports_combined_position_control is True}


async def handle_set_position(call: ServiceCall) -> None:
    """Handle set_position service call with sided all-target preflight."""
    hass = call.hass
    device_ids = call.data.get(CONF_DEVICE_ID, [])
    motor = call.data[ATTR_MOTOR]
    position = call.data[ATTR_POSITION]
    explicit_side = call.data.get(ATTR_SIDE)

    _LOGGER.info(
        "Service set_position called: motor=%s, position=%.1f%% (side=%s)",
        motor,
        position,
        explicit_side,
    )
    await _execute_position_requests(
        hass,
        device_ids,
        explicit_side,
        [(motor, position)],
    )


async def handle_set_positions(call: ServiceCall) -> None:
    """Handle an all-preflighted list of motor position targets."""
    hass = call.hass
    device_ids = call.data.get(CONF_DEVICE_ID, [])
    explicit_side = call.data.get(ATTR_SIDE)
    requests = [
        (str(item[ATTR_MOTOR]), float(item[ATTR_POSITION])) for item in call.data[ATTR_POSITIONS]
    ]
    motors = [motor for motor, _ in requests]
    if len(motors) != len(set(motors)):
        raise invalid(
            "duplicate_motor_positions"
        )
    _LOGGER.info(
        "Service set_positions called: motors=%s (side=%s)",
        ", ".join(motors),
        explicit_side,
    )
    await _execute_position_requests(hass, device_ids, explicit_side, requests)


async def _execute_position_requests(
    hass: HomeAssistant,
    device_ids: list[str],
    explicit_side: str | None,
    requests: list[tuple[str, float]],
) -> None:
    """Preflight every requested axis and then execute the complete plan."""
    targets, missing = _resolve_sided_targets(hass, device_ids, explicit_side)
    if missing:
        raise _missing_device_error(missing[0])

    # A STOP pressed while preflight connects or checks keeps every bed still.
    selection = _Selection.capture(targets)
    preflighted: PreflightedSides = []
    plans: dict[tuple[int, str], dict[str, Any]] = {}
    try:
        for coordinator, side in targets:
            for target in _command_targets(coordinator, side):
                for motor, position in requests:
                    plans[(_plan_key(target), motor)] = await _set_position_plan(
                        coordinator, target, preflighted, motor, position
                    )
    except ServiceValidationError:
        await _release_preflighted(preflighted)
        raise

    def resources(target: BedChild) -> tuple[str, ...]:
        return tuple(
            f"motor:{plans[(_plan_key(target), motor)]['position_key']}" for motor, _ in requests
        )

    def checked_configs(
        target: BedChild, controller: BedController
    ) -> dict[str, dict[str, Any]] | None:
        configs: dict[str, dict[str, Any]] = {}
        with controller_side_scope(target):
            for motor, position in requests:
                configs[motor] = _position_config(target, controller, motor, position)
        for motor, _ in requests:
            checked = plans[(_plan_key(target), motor)]
            if any(configs[motor].get(key) != checked.get(key) for key in _CHECKED_SEEK_FIELDS):
                raise _bed_changed()
        return None if selection.stopped() else configs

    async def recheck(target: BedChild) -> dict[str, dict[str, Any]] | None:
        """Check the complete plan on the live controller before moving."""
        controller = await _get_controller_for_service(target)
        preflighted.append((target, target))
        return checked_configs(target, controller)

    async def seek(target: BedChild, motor: str, position: float) -> None:
        # Seek only what preflight checked, on the controller that moves the bed.
        configs = await recheck(target)
        if configs is None:
            return
        config = configs[motor]
        await target.async_seek_position(
            position_key=cast(str, config["position_key"]),
            target_angle=position,
            move_up_fn=config["move_up_fn"],  # type: ignore[arg-type]
            move_down_fn=config["move_down_fn"],  # type: ignore[arg-type]
            move_stop_fn=config["move_stop_fn"],  # type: ignore[arg-type]
        )

    def seek_all(
        stop_epochs: Mapping[int, int],
    ) -> Callable[[BedChild], Coroutine[Any, Any, None]]:
        async def run(target: BedChild) -> None:
            async def check_all() -> None:
                await recheck(target)

            # Every axis is checked before the first one moves.
            operations: list[Callable[[], Coroutine[Any, Any, None]]] = [check_all]
            if len(requests) > 1 and plans[(_plan_key(target), requests[0][0])]["combine_targets"]:
                async def combined(controller: BedController) -> None:
                    configs = checked_configs(target, controller)
                    if configs is None:
                        return
                    await controller.set_motor_positions({
                        configs[motor]["position_key"]: controller.angle_to_native_position(
                            configs[motor]["position_key"], position
                        )
                        for motor, position in requests
                    })

                operations.append(
                    lambda: target.async_execute_controller_command(
                        combined, resources=resources(target)
                    )
                )
            else:
                for motor, position in requests:

                    async def operation(
                        motor: str = motor,
                        position: float = position,
                    ) -> None:
                        await seek(target, motor, position)

                    operations.append(operation)

            await target.async_execute_command_group(
                operations,
                resources=resources(target),
                expected_stop_epoch=stop_epochs.get(id(target)),
            )

        return run

    try:
        for coordinator, side in targets:
            if selection.stopped():
                await _release_preflighted(preflighted)
                return
            # Captured with no await since the STOP check above.
            if isinstance(coordinator, PairedBedCoordinator):
                pair_targets = coordinator.targets_for(side)
                group = {
                    item
                    for target in _command_targets(coordinator, side)
                    for item in resources(target)
                }
                admission = _capture_command_admission(coordinator, side, group)
                await coordinator.async_run_child_operation(
                    "set positions",
                    seek_all({id(child): child.stop_epoch for _, child in pair_targets}),
                    side=side,
                    resources=group,
                    expected_pair_generations=admission.expected_pair_generations,
                    expected_stop_epochs=admission.expected_stop_epochs,
                )
            else:
                await seek_all({id(coordinator): coordinator.stop_epoch})(coordinator)
    except Exception:
        await _release_preflighted(preflighted)
        raise
    if selection.stopped():
        await _release_preflighted(preflighted)


# A seek runs only when the live controller plans the same axis and range.
_CHECKED_SEEK_FIELDS: Final = ("position_key", "max_value", "unit", "combine_targets")


async def _timed_move_plan(
    parent: BedTarget,
    coordinator: BedChild,
    preflighted: PreflightedSides,
    motor: str,
    direction: str,
    duration_ms: int,
    svane_admission: SvaneHoldAdmission | None = None,
    *,
    hold_lease: bool = False,
    shared_motors: set[int] | None = None,
) -> tuple[Callable[[BedController], Coroutine[Any, Any, None]], int, int, str]:
    """Validate one physical side and build its timed command."""
    async with _side_validation(parent, coordinator, preflighted) as controller:
        motor_specs = {
            spec.key: spec
            for spec in controller.motor_control_specs
            if spec.key in TIMED_MOVE_MOTOR_OPTIONS
        }
        valid_motors = set(motor_specs)

        # Validate motor is valid for this bed
        if motor not in valid_motors:
            raise invalid("invalid_motor_for_bed_type", motor=motor, device_name=coordinator.name, valid_motors=", ".join(sorted(valid_motors)))

        spec = motor_specs[motor]
        if hold_lease:
            control = (
                spec.hold.up_control if direction == "up" else spec.hold.down_control
            ) if spec.hold is not None else None
            _require_hold_execution(coordinator, controller, control)
            duration_ms = _hold_ceiling(controller, duration_ms)
        try:
            controller.validate_timed_movement(motor, direction, duration_ms)
        except ValueError as err:
            raise rejected(err) from err

        if (
            shared_motors is not None
            and isinstance(coordinator, SingleAddressSideCoordinator)
            and spec.shared_across_sides
        ):
            shared_motors.add(_plan_key(coordinator))

        if coordinator.bed_type == BED_TYPE_SVANE:
            # The factory imported the Svane controller module, off the event loop.
            from .beds.svane.controller import SvaneController
            from .beds.svane.services import _preflight_live_svane

            if isinstance(controller, SvaneController):
                svane_admission = svane_admission or controller.prepare_svane_hold_admission()
                if (parent, coordinator) not in preflighted:
                    preflighted.append((parent, coordinator))
                await _preflight_live_svane(
                    parent,
                    coordinator,
                    svane_admission,
                    f"{'head' if motor == 'back' else 'feet'}_{direction}",
                    duration_ms,
                )

        resource = spec.scheduler_resource or f"motor:{spec.position_key or spec.key}"
        if (native_timed_move := spec.timed_move_fn) is not None:
            async def native_move(ctrl: BedController) -> None:
                await ctrl.prepare_for_movement()
                await native_timed_move(ctrl, direction == "up", duration_ms)

            tracked = track_motor_command(
                getattr(coordinator, "hass", None), motor, direction, native_move
            )
            return tracked, 1, 0, resource

        # The explicit app profile's direction is a held route. timed_move has
        # an elapsed duration, so delegate its bounded window and release to
        # the controller instead of treating one press frame as a full move.
        hold_control = None
        if coordinator.bed_type == BED_TYPE_SLEEPYS_ELITE_APP and spec.hold is not None:
            hold_control = (
                spec.hold.up_control if direction == "up" else spec.hold.down_control
            )
            try:
                controller.validate_hold_control(hold_control, duration_ms)
            except ValueError as err:
                raise rejected(err) from err

        move_fn = spec.open_fn if direction == "up" else spec.close_fn
        stop_fn = spec.stop_fn
        hold_spec = spec.hold
        hold_control = (
            hold_spec.up_control
            if hold_spec is not None and direction == "up"
            else hold_spec.down_control
            if hold_spec is not None
            else None
        )

        if hold_control is not None:
            if hold_control not in controller.held_control_options:
                # The bed declares a motor it cannot hold: it has no such timed move.
                raise invalid(
                    "invalid_motor_for_bed_type",
                    motor=motor,
                    device_name=coordinator.name,
                    valid_motors=", ".join(sorted(valid_motors - {motor})),
                )
            try:
                controller.validate_hold_control(hold_control, duration_ms)
            except ValueError as err:
                raise rejected(err) from err

        # Preserve the controller's repeat planning and cadence. An elapsed
        # ceiling below also bounds slow acknowledged writes and proxy latency.
        if hold_spec is not None:
            calculated_repeat_count = 1
            pulse_delay_ms = 0
        else:
            _, pulse_delay_ms = controller.motor_pulse_settings()
            if pulse_delay_ms <= 0:
                _LOGGER.warning(
                    "Invalid motor_pulse_delay_ms (%d) for device %s, using default 100ms",
                    pulse_delay_ms,
                    coordinator.name,
                )
                pulse_delay_ms = 100  # DEFAULT_MOTOR_PULSE_DELAY_MS
            calculated_repeat_count = controller.timed_move_repeat_count(
                duration_ms, pulse_delay_ms
            )

        _LOGGER.debug(
            "Timed move: duration=%dms, pulse_delay=%dms, repeat_count=%d",
            duration_ms,
            pulse_delay_ms,
            calculated_repeat_count,
        )

        async def held_movement(ctrl: BedController, _control: str | None = hold_control) -> None:
            assert _control is not None
            await ctrl.hold_control(_control, duration_ms)

        # Only the movement itself is timed: hold start and release delays and
        # the STOP cleanup around it are not travel. Single-address side views
        # carry no hass and are never estimated.
        estimate_hass = getattr(coordinator, "hass", None)
        tracked_hold = track_motor_command(estimate_hass, motor, direction, held_movement)
        tracked_move = track_motor_command(estimate_hass, motor, direction, move_fn)

        # Bind closure variables as defaults to avoid late-binding bugs
        async def timed_movement(
            ctrl: BedController,
            *,
            _move_fn: Callable[..., Coroutine[Any, Any, None]] = tracked_move,
            _held: Callable[..., Coroutine[Any, Any, None]] = tracked_hold,
            _stop_fn: Callable[..., Coroutine[Any, Any, None]] = stop_fn,
            _hold_control: str | None = hold_control,
            _hold_spec: ControllerMotorHoldSpec | None = hold_spec,
        ) -> None:
            """Execute movement for specified duration, always sending stop."""
            with contextlib.ExitStack() as admission_scope:
                if svane_admission is not None:
                    admission_scope.enter_context(svane_admission.activate(ctrl))
                if (
                    _hold_spec is not None
                    and _hold_control is not None
                    and coordinator.bed_type != BED_TYPE_SLEEPYS_ELITE_APP
                ):
                    await ctrl.prepare_for_movement()
                    if _hold_spec.start_delay_ms:
                        await asyncio.sleep(_hold_spec.start_delay_ms / 1000)
                    await _held(ctrl)
                    if _hold_spec.release_delay_ms:
                        await asyncio.sleep(_hold_spec.release_delay_ms / 1000)
                    return
                controller_timed_out = False
                try:
                    await ctrl.prepare_for_movement()
                    if _hold_control is not None:
                        await _held(ctrl)
                    else:
                        deadline = asyncio.timeout(duration_ms / 1000)
                        try:
                            async with deadline:
                                try:
                                    await _move_fn(ctrl)
                                except TimeoutError:
                                    # Controller cleanup can time out while responding
                                    # to our cancellation; that is still a real failure.
                                    controller_timed_out = True
                                    raise
                        except TimeoutError:
                            if controller_timed_out or not deadline.expired():
                                raise
                finally:
                    # Release is outside the movement ceiling. Keep the wire lane
                    # until it settles even if the caller is cancelled during STOP.
                    context = current_command_context()
                    # Leave a completed controller release for its admitted
                    # external STOP owner to consume after this wrapper returns.
                    if context is None or not context.cleanup_stop_sent:
                        stop_task = asyncio.create_task(_stop_fn(ctrl))
                        try:
                            await asyncio.shield(stop_task)
                        except asyncio.CancelledError:
                            await stop_task
                            raise

        return (
            timed_movement,
            calculated_repeat_count,
            pulse_delay_ms,
            resource,
        )


def _hold_lease(call: ServiceCall, action: str, duration_ms: int) -> HoldLease | None:
    """Return the call's renewable hold lease, or None for a finite move."""
    owner = call.data.get(ATTR_HOLD_OWNER)
    if owner is None:
        return None
    if not MIN_HOLD_LEASE_MS <= duration_ms <= MAX_HOLD_LEASE_MS:
        raise invalid(
            "hold_lease_duration",
            min=MIN_HOLD_LEASE_MS,
            max=MAX_HOLD_LEASE_MS,
        )
    return HoldLease(
        owner=owner,
        generation=call.data[ATTR_HOLD_GENERATION],
        action=action,
        duration_s=duration_ms / 1000,
    )


def _hold_ceiling(controller: BedController, duration_ms: int) -> int:
    """Bound a renewable hold by its mode's ceiling: latched beds move until STOP."""
    return min(duration_ms, controller.execution.hold_ceiling_ms or duration_ms)


def _require_hold_execution(
    target: BedChild,
    controller: BedController,
    control: str | None = None,
) -> None:
    """Allow a lease only where the controller declares an open-ended hold.

    ``control`` names a ``hold_control`` control; None is a motor route. A hold
    scoped to some controls refuses the others exactly as an undeclared one.
    """
    if controller.execution.hold_for(control) is None:
        raise invalid(
            "hold_renewal_not_supported",
            device_name=target.name,
        )


async def _async_with_hold_lease(
    targets: list[tuple[BedTarget, str]],
    lease: HoldLease,
    resource_for: Callable[[BedChild], str | None],
    start: Callable[[], Awaitable[None]],
) -> None:
    """Renew a live hold of this generation, or start one (#483).

    A renewal writes no frame and never starts motion on a side whose hold has
    ended. A generation that has ended everywhere is refused. A new hold
    reserves its generation before preflight, so renewals that arrive meanwhile
    extend the reservation and a STOP before admission ends it.
    """
    if len(targets) != 1:
        raise invalid("hold_one_bed")
    _require_hold_topology(targets)
    coordinator, side = targets[0]
    if (isinstance(coordinator, PairedBedCoordinator) and side == SIDE_BOTH
            and coordinator.connection_mode == PAIR_CONNECTION_MODE_SEQUENTIAL):
        raise invalid(
            "hold_needs_concurrent",
        )
    # Key every claim by the target that executes the command: a native
    # single-address Both runs once on its combined side view.
    executing = (
        list({id(child): child for _, child in coordinator.targets_for(side)}.values())
        if isinstance(coordinator, PairedBedCoordinator)
        else _command_targets(coordinator, side)
    )
    if len(executing) > 1 and isinstance(coordinator, PairedBedCoordinator) and not coordinator.supports_simultaneous_side_holds:
        raise invalid(
            "hold_select_side"
        )
    physical = [(target, resource_for(target)) for target in executing]
    if (
        isinstance(coordinator, PairedBedCoordinator)
        and not isinstance(coordinator, SingleAddressPairedCoordinator)
        and len(executing) > 1
        and coordinator.connection_mode != PAIR_CONNECTION_MODE_CONCURRENT
    ):
        raise invalid(
            "hold_needs_concurrent",
        )
    claims = [
        target.claim_hold_lease(lease, resource=resource, reserve=False)
        for target, resource in physical
    ]
    if HoldClaim.RENEW in claims:
        for (target, resource), claim in zip(physical, claims, strict=True):
            if claim is HoldClaim.RENEW:
                target.claim_hold_lease(lease, resource=resource)
        return
    if HoldClaim.STALE in claims:
        raise invalid("hold_ended")
    modes = {
        controller.execution.hold
        for target, _resource in physical
        if (controller := target.capability_controller) is not None
    }
    if len(modes) > 1:
        raise invalid(
            "hold_modes_differ"
        )
    for target, resource in physical:
        target.claim_hold_lease(lease, resource=resource)
    try:
        await start()
    except StaleHoldLease as err:
        raise rejected(err) from err
    finally:
        for target, resource in physical:
            target.release_hold_claim(lease, resource=resource)


async def handle_timed_move(call: ServiceCall) -> None:
    """Handle timed_move service call with sided all-target preflight."""
    hass = call.hass
    device_ids = call.data.get(CONF_DEVICE_ID, [])
    motor = call.data[ATTR_MOTOR]
    direction = call.data[ATTR_DIRECTION]
    duration_ms = call.data[ATTR_DURATION_MS]
    explicit_side = call.data.get(ATTR_SIDE)

    _LOGGER.info(
        "Service timed_move called: motor=%s, direction=%s, duration_ms=%d (side=%s)",
        motor,
        direction,
        duration_ms,
        explicit_side,
    )
    targets, missing = _resolve_sided_targets(hass, device_ids, explicit_side)
    if missing:
        raise _missing_device_error(missing[0])

    lease = _hold_lease(call, direction, duration_ms)
    if lease is None:
        await _async_timed_move(targets, motor, direction, duration_ms)
        return
    await _async_with_hold_lease(
        targets,
        lease,
        lambda target: _timed_move_resource(target, motor),
        # The lease ends the hold; the ceiling only bounds it in total.
        lambda: _async_timed_move(targets, motor, direction, MAX_HOLD_LEASE_MS, lease=lease),
    )


async def _async_timed_move(
    targets: list[tuple[BedTarget, str]],
    motor: str,
    direction: str,
    duration_ms: int,
    *,
    lease: HoldLease | None = None,
) -> None:
    """Share the bounded service path with declared-hold entity fallbacks."""
    # Resolve each selected motor resource from any offline capability
    # controller before preflight can connect or wait. The scheduler and pair
    # snapshots then reject a STOP or replacement that overtakes this event.
    command_admissions: dict[tuple[int, str], _CommandAdmission] = {}
    for coordinator, side in targets:
        physical_resources = {
            _timed_move_resource(target, motor)
            for target in _command_targets(coordinator, side)
        }
        command_admissions[(id(coordinator), side)] = _capture_command_admission(
            coordinator, side, physical_resources
        )

    svane_controllers = [
        (target, controller)
        for parent, side in targets
        for target in _command_targets(parent, side)
        if target.bed_type == BED_TYPE_SVANE
        and (controller := target.capability_controller) is not None
    ]
    svane_admissions: dict[int, SvaneHoldAdmission] = {}
    if svane_controllers:
        # The factory imported the Svane controller module, off the event loop.
        from .beds.svane.controller import SvaneController

        svane_admissions = {
            _plan_key(target): controller.prepare_svane_hold_admission()
            for target, controller in svane_controllers
            if isinstance(controller, SvaneController)
        }
    preflighted: PreflightedSides = []
    plans: dict[
        int,
        tuple[Callable[[BedController], Coroutine[Any, Any, None]], int, int, str],
    ] = {}
    stop_epoch_by_target: dict[int, int] = {}
    shared_motors: set[int] = set()
    try:
        for coordinator, side in targets:
            for target in _command_targets(coordinator, side):
                target_key = _plan_key(target)
                command_admission = command_admissions[(id(coordinator), side)]
                if isinstance(coordinator, PairedBedCoordinator):
                    target_side = next(
                        target_side
                        for target_side, child in coordinator.targets_for(side)
                        if child is target
                    )
                else:
                    target_side = SIDE_BOTH
                if target_side in command_admission.expected_stop_epochs:
                    stop_epoch_by_target[target_key] = command_admission.expected_stop_epochs[
                        target_side
                    ]
                plans[_plan_key(target)] = await _timed_move_plan(
                    coordinator, target, preflighted, motor, direction, duration_ms,
                    svane_admissions.get(target_key),
                    hold_lease=lease is not None,
                    shared_motors=shared_motors,
                )
            admission = command_admissions[(id(coordinator), side)]
            actual_resources = {
                    plans[_plan_key(target)][3] for target in _command_targets(coordinator, side)
                }
            if actual_resources != set(admission.resources):
                raise invalid(
                    "bed_changed"
                )
    except Exception, asyncio.CancelledError:
        await _release_preflighted(preflighted)
        raise

    # #516: merge into one stream only on a standalone bed whose controller
    # declares this motor concurrent. Paired topologies run each side inside a
    # prepared reservation, where a streamer cannot start, so they stay serial.
    physical = [
        target for coordinator, side in targets for target in _command_targets(coordinator, side)
    ]
    streamed = not any(
        isinstance(coordinator, PairedBedCoordinator) for coordinator, _ in targets
    ) and all(
        not isinstance(target, SingleAddressSideCoordinator)
        and (resources := target.stream_resources()) is not None
        and plans[_plan_key(target)][3] in resources
        for target in physical
    )

    completed_shared_motors: set[int] = set()

    async def move(target: BedChild) -> None:
        target_key = _plan_key(target)
        if target_key in completed_shared_motors:
            return
        command, pulse_count, pulse_delay_ms, resource = plans[target_key]
        if streamed:
            assert not isinstance(target, SingleAddressSideCoordinator)
            svane_admission = svane_admissions.get(_plan_key(target))
            if svane_admission is not None and svane_admission.released(
                "head" if motor == "back" else "feet"
            ):
                # svane_release_axis arrived during preflight: admit no motion,
                # and give the link preflight opened its normal idle disconnect.
                if target.is_connected:
                    with contextlib.suppress(Exception):
                        await target.async_ensure_connected(reset_timer=True)
                return
            # Timed from the member's first write to its retirement, like the
            # serial move's own span; a renewal never starts a new move.
            tracker = track_stream_member(
                getattr(target, "hass", None), target.capability_controller, motor, direction
            )
            await target.async_execute_stream_member(
                motor=motor,
                resource=resource,
                action=direction,
                duration_s=lease.duration_s if lease is not None else duration_ms / 1000,
                ceiling_s=duration_ms / 1000 if lease is not None else None,
                lease=lease,
                expected_stop_epoch=stop_epoch_by_target.get(_plan_key(target)),
                on_wire=tracker.started if tracker is not None else None,
                on_left=tracker.finished if tracker is not None else None,
            )
            return
        if lease is not None:
            await target.async_execute_controller_command(
                command,
                resource=resource,
                pulse_count=pulse_count,
                pulse_delay_ms=pulse_delay_ms,
                expected_stop_epoch=stop_epoch_by_target.get(_plan_key(target)),
                lease=lease,
            )
        else:
            await target.async_execute_controller_command(
                command,
                resource=resource,
                pulse_count=pulse_count,
                pulse_delay_ms=pulse_delay_ms,
                expected_stop_epoch=stop_epoch_by_target.get(_plan_key(target)),
            )
        if target_key in shared_motors:
            completed_shared_motors.add(target_key)

    try:
        for coordinator, side in targets:
            admission = command_admissions[(id(coordinator), side)]
            with command_target_scope(admission.command_targets):
                if isinstance(coordinator, PairedBedCoordinator):
                    resources = {
                        plans[_plan_key(target)][3] for target in _command_targets(coordinator, side)
                    }
                    await coordinator.async_run_child_operation(
                        "timed move",
                        move,
                        side=side,
                        resources=resources,
                        expected_pair_generations=admission.expected_pair_generations,
                        expected_stop_epochs=admission.expected_stop_epochs,
                    )
                else:
                    await move(coordinator)
    except Exception, asyncio.CancelledError:
        await _release_preflighted(preflighted)
        raise


async def _preflight_each(
    targets: list[tuple[BedTarget, str]],
    check: Callable[[BedChild, BedController], Awaitable[None] | None],
) -> PreflightedSides:
    """Check every physical target before executing the requested command.

    A ``ValueError`` from ``check`` becomes a ``ServiceValidationError``; any
    failure releases the sides connected only for validation.
    """
    preflighted: PreflightedSides = []
    try:
        for coordinator, side in targets:
            for target in _command_targets(coordinator, side):
                controller = await _validation_controller(coordinator, target, preflighted)
                with controller_side_scope(target):
                    if (pending := check(target, controller)) is not None:
                        await pending
    except (ServiceValidationError, ValueError) as err:
        await _release_preflighted(preflighted)
        if isinstance(err, ValueError):
            raise _validation_error(err) from err
        raise
    except BaseException:
        await _release_preflighted(preflighted)
        raise
    return preflighted


async def _preflight_capability[T](
    targets: list[tuple[BedTarget, str]],
    interface: type[T],
    supported: Callable[[T], bool] | None = None,
    validate: Callable[[T], None] | None = None,
) -> PreflightedSides:
    """Validate a family capability on every physical target before any write.

    A target supports the action when its controller implements ``interface``
    and, if given, ``supported`` accepts it.
    """

    def check(target: BedChild, controller: BedController) -> None:
        family = controller_as(controller, interface)
        if family is None or (supported is not None and not supported(family)):
            raise invalid(
                "feature_not_supported",
                device_name=target.name,
                feature="this action",
            )
        if validate is not None:
            validate(family)

    return await _preflight_each(targets, check)


def _family_command[T](
    interface: type[T], command: Callable[[T], Awaitable[None]]
) -> Callable[[BedController], Coroutine[Any, Any, None]]:
    """Adapt a family command to the scheduler; a ``ValueError`` is a validation error."""

    async def execute(controller: BedController) -> None:
        family = controller_as(controller, interface)
        if family is None:
            raise invalid(
                "feature_not_supported",
                device_name=controller._coordinator.name,
                feature="this action",
            )
        try:
            await command(family)
        except ValueError as err:
            raise _validation_error(err) from err

    return execute


async def _preflight_and_execute[T](
    targets: list[tuple[BedTarget, str]],
    interface: type[T],
    command: Callable[[T], Awaitable[None]],
    *,
    supported: Callable[[T], bool] | None = None,
    validate: Callable[[T], None] | None = None,
    cancel_running: bool = False,
    skip_disconnect: bool = False,
    resource: str | None = "configuration",
    admit: bool = False,
    admissions: Sequence[_CommandAdmission | None] | None = None,
    prepare: Callable[[], None] | None = None,
) -> None:
    """Preflight every physical target, then run ``command`` on each in turn.

    A ``ValueError`` from validation or the command becomes a
    ``ServiceValidationError``. Any failure or cancellation hands the links
    opened only for validation back to their idle timer. ``admit`` lets a STOP
    pressed during the preflight cancel the command. ``admissions`` can carry
    snapshots captured before a lazy import awaits. ``prepare`` publishes
    synchronous ingress input after the complete batch passes validation and
    its captured STOP generations still match, before queued execution.
    """
    if admissions is None:
        admissions = [
            _capture_command_admission(
                coordinator, side, ALL_COMMAND_RESOURCES if resource is None else (resource,)
            )
            if admit
            else None
            for coordinator, side in targets
        ]
    preflighted = await _preflight_capability(targets, interface, supported, validate)
    if prepare is not None:
        try:
            # An ingress update may affect an already running operation. Admit
            # the complete batch before publishing it, with no await between
            # the owner/STOP checks and the synchronous update.
            if all(
                admission is not None
                and _capture_command_admission(parent, side, admission.resources) == admission
                for (parent, side), admission in zip(targets, admissions, strict=True)
            ):
                prepare()
        except BaseException:
            await _release_preflighted(preflighted)
            raise
    await _execute_preflighted(
        targets,
        preflighted,
        _family_command(interface, command),
        cancel_running=cancel_running,
        skip_disconnect=skip_disconnect,
        resource=resource,
        admissions=admissions,
    )


async def _execute_preflighted(
    targets: list[tuple[BedTarget, str]],
    preflighted: PreflightedSides,
    command_fn: Callable[[BedController], Coroutine[Any, Any, None]],
    *,
    cancel_running: bool = False,
    skip_disconnect: bool = False,
    resource: str | None = "configuration",
    resources: Collection[str] | None = None,
    admissions: Sequence[_CommandAdmission | None] | None = None,
    translate_side_errors: bool = False,
) -> None:
    """Run a preflighted command on each target in turn.

    Any failure or cancellation hands the links opened only for validation
    back to their idle timer.
    """
    execute = _execute_sided_translated if translate_side_errors else _execute_sided
    try:
        for index, (coordinator, side) in enumerate(targets):
            await execute(
                coordinator,
                side,
                command_fn,
                cancel_running=cancel_running,
                skip_disconnect=skip_disconnect,
                resource=resource,
                resources=resources,
                admission=None if admissions is None else admissions[index],
            )
    except BaseException:
        await _release_preflighted(preflighted)
        raise


def _call_targets(call: ServiceCall) -> list[tuple[BedTarget, str]]:
    """Resolve a sided call's targets, rejecting a device with no configured bed."""
    targets, missing = _resolve_sided_targets(
        call.hass, call.data[CONF_DEVICE_ID], call.data.get(ATTR_SIDE)
    )
    if missing:
        raise _missing_device_error(missing[0])
    return targets


def _profile_route(
    targets: list[tuple[BedTarget, str]], routes: dict[str, str], action: str
) -> str | None:
    """Return the dedicated route shared by every physical target, else None.

    Some profiles validate and release through their own live session, so a
    call cannot mix them with beds that use the generic route.
    """
    selected = {
        routes.get(target.bed_type)
        for coordinator, side in targets
        for target in _command_targets(coordinator, side)
    }
    if len(selected) > 1:
        raise invalid("mixed_profile_targets", action=action)
    return next(iter(selected), None)


async def handle_rename(call: ServiceCall) -> None:
    """Write a new Bluetooth name to every targeted controller that supports it."""
    # The other family action modules load with the services, this one does not.
    await async_import_modules(call.hass, "beds.vmatbasic.services")
    from .beds.furnimove.services import _rename_furnimove
    from .beds.vmatbasic.services import _rename_vmatbasic

    name = call.data[ATTR_NAME]
    targets = _call_targets(call)
    route = _profile_route(
        targets,
        {BED_TYPE_FURNIMOVE: "furnimove", BED_TYPE_VMATBASIC: "vmatbasic"},
        SERVICE_RENAME,
    )
    if route == "furnimove":
        await _rename_furnimove(call, targets, name)
        return
    if route == "vmatbasic":
        await async_import_modules(call.hass, "beds.vmatbasic.controller")
        await _rename_vmatbasic(targets, name)
        return

    disconnect: set[int] = set()

    def check(target: BedChild, controller: BedController) -> None:
        if not controller.supports_device_rename:
            raise invalid("device_rename_not_supported", device_name=target.name)
        # Each app has its own name rule; reject before any target writes.
        controller.validate_device_rename(name)

    live = _LiveCheck(check)

    def preflight(target: BedChild, controller: BedController) -> None:
        live.preflight(target, controller)
        if controller.disconnects_after_rename:
            disconnect.add(id(target))

    preflighted = await _preflight_each(targets, preflight)

    async def write_name(controller: BedController) -> None:
        await controller.rename_device(name)

    rename = live.command(targets, write_name)

    try:
        for coordinator, side in targets:
            await _execute_sided_translated(
                coordinator, side, rename, cancel_running=False, resource="configuration"
            )
            for target in _command_targets(coordinator, side):
                if id(target) in disconnect:
                    await target.async_disconnect(reason="intentional")
    except Exception, asyncio.CancelledError:
        await _release_preflighted(preflighted)
        raise


def _leggett_integer(value: object) -> int:
    """Reject fractional or Boolean values before timer parameters are sent."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise vol.Invalid("Value must be a whole number")
    return value


def _hold_seconds(value: object) -> Decimal:
    """Accept bounded seconds that convert exactly to whole milliseconds."""
    try:
        duration = Decimal(str(value))
    except InvalidOperation as err:
        raise vol.Invalid("Duration must be a number of seconds") from err
    if not duration.is_finite() or not Decimal("0.1") <= duration <= 60:
        raise vol.Invalid("Duration must be between 0.1 and 60 seconds")
    milliseconds = int(duration * 1000)
    if duration != Decimal(milliseconds) / 1000:
        raise vol.Invalid("Duration must resolve to whole milliseconds")
    return duration


async def handle_hold_control(call: ServiceCall) -> None:
    """Hold one controller-declared control, then run its protocol release."""
    targets = _call_targets(call)
    admissions = [_capture_command_admission(coordinator, side) for coordinator, side in targets]
    # The other family action modules load with the services, this one does not.
    await async_import_modules(call.hass, "beds.vmatbasic.services")
    from .beds.limoss.remote_services import _hold_limoss_remote
    from .beds.richmat_classic.profiles import current_control_name
    from .beds.svane.services import _hold_svane
    from .beds.vmatbasic.services import _hold_vmatbasic_floor

    control = current_control_name(call.data[ATTR_CONTROL])
    duration_ms = int(call.data[ATTR_DURATION] * 1000)
    route = _profile_route(
        targets,
        {BED_TYPE_SVANE: "svane", BED_TYPE_LIMOSS_REMOTE: "limoss_remote"},
        SERVICE_HOLD_CONTROL,
    )
    lease = _hold_lease(call, control, duration_ms)
    if lease is not None:
        if route == "svane" or control == "floor_hold":
            raise invalid(
                "control_hold_renewal_not_supported",
            )
        if route is None and _windowed_press(targets, lease, control):
            await _async_hold_window(
                call.hass,
                targets,
                lease,
                lambda window: _hold_targets(
                    targets, control, HOLD_CEILING_MS, admissions=admissions, window=window
                ),
            )
            return
        held = lease
        await _async_with_hold_lease(
            targets,
            held,
            lambda _target: None,
            (
                lambda: _hold_limoss_remote(
                    call, control, MAX_HOLD_LEASE_MS, targets=targets, lease=held
                )
            )
            if route == "limoss_remote"
            else lambda: _hold_targets(targets, control, MAX_HOLD_LEASE_MS, lease=held, admissions=admissions),
        )
        return
    if route == "svane":
        await _hold_svane(call, control, duration_ms)
    elif route == "limoss_remote":
        await _hold_limoss_remote(call, control, duration_ms)
    elif control == "floor_hold" and any(
        target.bed_type == BED_TYPE_VMATBASIC
        for coordinator, side in targets
        for target in _command_targets(coordinator, side)
    ):
        await async_import_modules(call.hass, "beds.vmatbasic.controller")
        await _hold_vmatbasic_floor(targets, control, duration_ms)
    else:
        await _hold_targets(targets, control, duration_ms, admissions=admissions)


def _declares_hold(targets: list[tuple[BedTarget, str]], control: str) -> bool:
    """Whether every executing target declares a renewable hold on ``control``."""
    controllers = [
        target.capability_controller
        for coordinator, side in targets
        for target in _command_targets(coordinator, side)
    ]
    return bool(controllers) and all(
        controller is not None and controller.execution.hold_for(control) is not None
        for controller in controllers
    )


def _windowed_press(
    targets: list[tuple[BedTarget, str]], lease: HoldLease, control: str
) -> bool:
    """Route a press once, so its renewals follow it when capabilities change.

    A press of a control the bed declares no renewable hold for takes a window;
    the rest take the scheduler lease. A Good Vibe memory save, for one, makes
    its control a sustained press the moment it lands.
    """
    if len(targets) != 1:
        return not _declares_hold(targets, control)
    coordinator, side = targets[0]
    press = coordinator.hold_windows.get(side, lease.owner)
    if press is not None and press.generation >= lease.generation:
        return press.windowed
    if _declares_hold(targets, control):
        coordinator.hold_windows.remember(
            side,
            lease.owner,
            HoldWindow(control, lease.generation, math.inf, windowed=False, ended=True),
        )
        return False
    return True


async def _async_hold_window(
    hass: HomeAssistant,
    targets: list[tuple[BedTarget, str]],
    lease: HoldLease,
    run: Callable[[HoldWindow], Awaitable[None]],
) -> None:
    """Hold a control that declares no renewable hold until its renewals stop.

    The hold is the bounded one ``hold_control`` always runs, so the bed gets
    the same frames. A renewal (same owner, generation and control) only moves
    the deadline and writes nothing. When the deadline passes, the commands
    this press started are cancelled as a STOP cancels them, so each runs its
    release, and nothing else is touched; one not yet started never starts.
    """
    if len(targets) != 1:
        raise invalid("hold_one_bed")
    coordinator, side = targets[0]
    now = asyncio.get_running_loop().time()
    window = coordinator.hold_windows.get(side, lease.owner)
    if window is not None and window.generation >= lease.generation:
        if window.generation > lease.generation or window.control != lease.action:
            raise invalid("hold_ended")
        # A renewal in flight when the hold ended moves nothing.
        if not window.ended:
            window.deadline = now + lease.duration_s
        return
    window = HoldWindow(lease.action, lease.generation, now + lease.duration_s)
    coordinator.hold_windows.remember(side, lease.owner, window)
    # A dropped caller (a closed dashboard) must not take the deadline with it.
    task = hass.async_create_background_task(
        _run_hold_window(window, run), "adjustable_bed hold window"
    )
    await asyncio.shield(task)


async def _run_hold_window(
    window: HoldWindow, run: Callable[[HoldWindow], Awaitable[None]]
) -> None:
    loop = asyncio.get_running_loop()
    hold = asyncio.ensure_future(run(window))
    try:
        while not hold.done():
            remaining = window.deadline - loop.time()
            if remaining <= 0:
                _LOGGER.debug("Held %s stopped renewing; ending its hold", window.control)
                window.expired = True
                for context in window.commands:
                    # Ended as a STOP ends it, so a pair takes it as cleanup;
                    # a command already cancelled keeps its own reason.
                    if not context.cancel_event.is_set():
                        context.request_cancel(CommandOutcome.STOPPED)
                break
            await asyncio.wait((hold,), timeout=remaining)
        await asyncio.wait((hold,))
        if not hold.cancelled():
            hold.result()
    except asyncio.CancelledError:
        # Shutdown or unload: the hold must not outlive its deadline keeper.
        hold.cancel()
        raise
    finally:
        window.ended = True


def _require_held_control(
    target: BedChild, controller: BedController, control: str
) -> None:
    """Reject a control the target's controller does not declare, listing valid ones."""
    options = controller.held_control_options
    if not options:
        raise invalid("held_controls_not_supported", device_name=target.name)
    if control not in options:
        raise invalid("held_control_not_supported", device_name=target.name, control=control, valid_controls=", ".join(options))


def _require_hold_topology(targets: list[tuple[BedTarget, str]]) -> None:
    """A sequential link cannot sustain Both, before any lease reservation."""
    if any(
        isinstance(coordinator, PairedBedCoordinator)
        and side == SIDE_BOTH
        and coordinator.connection_mode == "sequential"
        for coordinator, side in targets
    ):
        raise invalid(
            "hold_needs_concurrent",
        )


async def _hold_targets(
    targets: list[tuple[BedTarget, str]],
    control: str,
    duration_ms: int,
    *,
    lease: HoldLease | None = None,
    admissions: Sequence[_CommandAdmission] | None = None,
    window: HoldWindow | None = None,
) -> None:
    """Preflight the whole selection before starting any held write sequence."""
    bounded_catalog = lease is None and all(
        child.bed_type == "bobpowerbase"
        for parent, side in targets for child in _command_targets(parent, side)
    )
    if not bounded_catalog:
        _require_hold_topology(targets)
    shared_receivers: set[int] = set()

    def check(target: BedChild, controller: BedController) -> None:
        _require_held_control(target, controller, control)
        if lease is not None:
            _require_hold_execution(target, controller, control)
        controller.validate_hold_control(control, duration_ms)
        if isinstance(target, SingleAddressSideCoordinator) and any(
            spec.shared_across_sides
            and spec.hold is not None
            and control in (spec.hold.up_control, spec.hold.down_control)
            for spec in controller.motor_control_specs
        ):
            shared_receivers.add(_plan_key(target))

    # A STOP during any per-side capability/connect wait owns the event that
    # was current when the user pressed. Capture before _preflight_each awaits.
    if admissions is None:
        admissions = [_capture_command_admission(coordinator, side) for coordinator, side in targets]
    live = _LiveCheck(check)
    preflighted = await _preflight_each(targets, live.preflight)
    completed_shared_receivers: set[int] = set()

    async def hold_checked(controller: BedController) -> None:
        # Automatic link-slot fallback may have changed topology after admission.
        if not bounded_catalog:
            _require_hold_topology(targets)
        if window is not None:
            # Renewals stopped before this command began: start nothing.
            if window.lapsed:
                return
            if (context := current_command_context()) is not None:
                window.commands.append(context)
        await controller.hold_control(
            control, duration_ms if lease is None else _hold_ceiling(controller, duration_ms)
        )

    hold = live.command(targets, hold_checked)

    try:
        for (coordinator, side), admission in zip(targets, admissions, strict=True):
            if window is not None and window.lapsed:
                # Renewals stopped during preflight: never replace another command.
                break
            if isinstance(coordinator, SingleAddressPairedCoordinator) and any(
                _plan_key(target) in shared_receivers
                for target in _command_targets(coordinator, side)
            ):
                stop_epochs = {
                    id(child): admission.expected_stop_epochs.get(target_side)
                    for target_side, child in coordinator.targets_for(side)
                }

                async def hold_shared(
                    target: BedChild,
                    _stop_epochs: dict[int, int | None] = stop_epochs,
                ) -> None:
                    receiver = _plan_key(target)
                    # Skip the duplicate before its scheduler can reconnect the receiver.
                    if receiver in completed_shared_receivers:
                        return
                    await target.async_execute_controller_command(
                        track_held_control(getattr(target, "hass", None), control, hold),
                        cancel_running=True,
                        expected_stop_epoch=_stop_epochs[id(target)],
                        lease=lease,
                    )
                    if receiver in shared_receivers:
                        completed_shared_receivers.add(receiver)

                await coordinator.async_run_child_operation(
                    "hold control",
                    hold_shared,
                    side=side,
                    expected_pair_generations=admission.expected_pair_generations,
                    expected_stop_epochs=admission.expected_stop_epochs,
                )
                continue
            await _execute_sided(
                coordinator,
                side,
                track_held_control(getattr(coordinator, "hass", None), control, hold),
                cancel_running=True,
                admission=admission,
                lease=lease,
            )
    except (Exception, asyncio.CancelledError):
        await _release_preflighted(preflighted)
        raise
    else:
        # A stale scheduler admission is a normal no-op after STOP, so restore
        # the idle deadline on links opened during preflight on either path.
        await _release_preflighted(preflighted)


def _alarm_request(call: ServiceCall) -> AlarmRequest:
    """Build the call's one alarm request, captured against one local time."""
    data = call.data
    enabled = data[ATTR_ENABLED]
    alarm_time = data.get(ATTR_TIME)
    if enabled and alarm_time is None:
        raise invalid("alarm_time_required")
    if alarm_time is not None and (alarm_time.second or alarm_time.microsecond):
        raise invalid("alarm_time_whole_minutes")
    optional = {name: data[name] for name in ALARM_OPTIONAL_FIELDS if name in data}
    if "weekdays" in optional:
        optional["weekdays"] = tuple(sorted({ALARM_WEEKDAYS.index(day) for day in optional["weekdays"]}))
    return AlarmRequest(
        enabled=enabled,
        hour=alarm_time.hour if alarm_time is not None else 0,
        minute=alarm_time.minute if alarm_time is not None else 0,
        reference_time=dt_util.now(),
        time_provided=alarm_time is not None,
        **optional,
    )


def _check_alarm(
    device_name: str, controller: BedController, alarm: AlarmRequest, given: Collection[str]
) -> AlarmRequest:
    """Validate one physical target's alarm and return it with its defaults filled in."""
    capability = controller.alarm_capability
    if capability is None:
        raise invalid("alarm_not_supported", device_name=device_name)
    if capability.requires_slot and "slot" not in given:
        raise invalid("alarm_slot_required", device_name=device_name)
    for name in given:
        if not capability.accepts(name):
            raise invalid("alarm_option_not_supported", device_name=device_name, option=name)
    wake_action = alarm.wake_action if "wake_action" in given else None
    if wake_action is not None and wake_action not in capability.wake_actions:
        raise invalid("alarm_wake_action_not_supported", device_name=device_name, wake_action=wake_action, wake_actions=", ".join(capability.wake_actions))
    if (
        alarm.enabled
        and capability.requires_wake_action
        and wake_action is None
        and "mattress_side" not in given
    ):
        raise invalid("alarm_wake_action_required", device_name=device_name)
    limits = (
        ("slot", alarm.slot, capability.first_slot, capability.slots),
        ("head_massage_level", alarm.head_massage_level, 0, capability.massage_levels),
        ("foot_massage_level", alarm.foot_massage_level, 0, capability.massage_levels),
        ("massage_intensity", alarm.massage_intensity, 1, capability.massage_intensities),
    )
    for name, value, low, high in limits:
        if name == "slot" and capability.live_slots:
            continue  # The controller admits the exact identity during check_alarm.
        if name in given and not low <= value <= high:
            raise invalid("alarm_value_out_of_range", device_name=device_name, option=name, min=str(low), max=str(high))
    if "massage_duration" in given and alarm.massage_duration not in capability.massage_durations:
        raise invalid("alarm_massage_duration_not_supported", device_name=device_name, durations=", ".join(map(str, capability.massage_durations)))
    if "sleep_timer" in given and alarm.sleep_timer not in capability.sleep_timers:
        raise invalid("alarm_sleep_timer_not_supported", device_name=device_name, durations=", ".join(map(str, capability.sleep_timers)))
    if "massage_zone" in given and alarm.massage_zone not in capability.massage_zones:
        raise invalid("alarm_massage_zone_not_supported", device_name=device_name, zone=str(alarm.massage_zone))
    if "mattress_side" in given and alarm.mattress_side not in capability.mattress_sides:
        raise invalid("alarm_mattress_side_not_supported", device_name=device_name, mattress_side=str(alarm.mattress_side))
    if "sound" in given and alarm.sound not in capability.sounds:
        raise invalid("alarm_sound_not_supported", device_name=device_name, sound=alarm.sound)
    resolved = _with_bed_defaults(alarm, capability, given)
    if (
        resolved.enabled
        and resolved.wake_action in capability.confirm_actions
        and not resolved.confirm_custom_position
    ):
        raise invalid("alarm_confirmation_required", device_name=device_name)
    controller.validate_alarm(resolved)
    return resolved


def _with_bed_defaults(
    alarm: AlarmRequest, capability: AlarmCapability, given: Collection[str]
) -> AlarmRequest:
    """Fill in the bed's own default for each choice the caller left out."""
    defaults: dict[str, object] = {}
    # A mattress topper alarm has no wake action, so none is filled in for it.
    bed_alarm = "mattress_side" not in given
    for name, choices in (
        ("wake_action", capability.wake_actions if bed_alarm else ()),
        ("sound", capability.sounds),
        ("massage_duration", capability.massage_durations),
        ("massage_zone", capability.massage_zones if capability.default_massage_zone else ()),
    ):
        if name not in given and choices:
            defaults[name] = choices[0]
    return dataclasses.replace(alarm, **defaults) if defaults else alarm


# Values of set_alarm fields that ask nothing of the bed.
_ALARM_NOTHING: Final[dict[str, object]] = {
    ATTR_WEEKDAYS: [],
    ATTR_MASSAGE: False,
    "light": False,
}


async def handle_set_alarm(call: ServiceCall) -> None:
    """Validate one alarm on every physical target, then write it to each."""
    alarm = _alarm_request(call)
    # No repeat days, no massage and no light ask nothing of a bed without
    # those options, so a bed is not refused for them.
    given = [
        name
        for name in ALARM_OPTIONAL_FIELDS
        if name in call.data
        and (name not in _ALARM_NOTHING or call.data[name] != _ALARM_NOTHING[name])
    ]
    targets = _call_targets(call)

    route = _profile_route(
        targets,
        {
            BED_TYPE_ZSERIES: "zseries",
            "betterliving2": "betterliving2",
            BED_TYPE_SYMPHONY: "symphony",
            BED_TYPE_ULTRAMATIC_SMART_BED: "ultramatic",
        },
        SERVICE_SET_ALARM,
    )
    if route == "betterliving2":
        from .beds.keeson.betterliving2_services import set_alarm

        await set_alarm(call, alarm, given)
        return
    if route == "ultramatic":
        # Its fenced A/AB/B plans capture every target before their first await.
        from .beds.ultramatic.services import set_ultramatic_alarm

        await set_ultramatic_alarm(call, alarm, given)
        return
    if route == "symphony":
        # Symphony reads the current alarm table live before rewriting one side.
        from .beds.symphony.services import set_symphony_alarm

        await set_symphony_alarm(call, alarm, given)
        return
    if route == "zseries":
        await async_import_modules(call.hass, "beds.serenity.services")
        from .beds.serenity.services import _execute_zseries_alarm

        # Z-Series alarms exist only after a live manufacturer read. The options
        # are checked on every target, connecting where needed, before anything
        # is scheduled.
        async def write_zseries(controller: BedController) -> None:
            await controller.configure_alarm(
                _check_alarm(controller._coordinator.name, controller, alarm, given)
            )

        def check_zseries(controller: BedController) -> None:
            _check_alarm(controller._coordinator.name, controller, alarm, given)

        await _execute_zseries_alarm(call, write_zseries, validate=check_zseries)
        return

    selection = _Selection.capture(targets)
    # Each physical side's scheduling, from the capability preflight checked.
    plans: dict[int, AlarmCapability] = {}

    def check(target: BedChild, controller: BedController) -> None:
        _check_alarm(target.name, controller, alarm, given)
        capability = cast("AlarmCapability", controller.alarm_capability)
        if not alarm.enabled and capability.time_to_turn_off and ATTR_TIME not in call.data:
            raise invalid("alarm_time_required_to_turn_off", device_name=target.name)
        plans[id(target)] = capability

    langjue_addresses = {
        child.address
        for children in selection.children
        for child in children
        if child.bed_type == BED_TYPE_LANGJUE
    }
    async with contextlib.AsyncExitStack() as transaction:
        # A sibling's reload would replace the same parent. Defer both sides'
        # reloads even when the action targets just one side of the pair.
        receivers: dict[int, AdjustableBedCoordinator] = {}
        for (parent, _), group in zip(selection.targets, selection.children, strict=True):
            children = parent.children.values() if isinstance(parent, PairedBedCoordinator) else group
            for child in children:
                receiver = child.inner if isinstance(child, SingleAddressSideCoordinator) else child
                if isinstance(receiver, AdjustableBedCoordinator):
                    receivers[id(receiver)] = receiver
        for receiver in receivers.values():
            await transaction.enter_async_context(receiver.async_defer_capability_reload())

        if langjue_addresses:
            await async_import_modules(call.hass, "beds.langjue")
            from .beds.langjue import reserve_alarm_receivers

            transaction.enter_context(reserve_alarm_receivers(call.hass, langjue_addresses))

        preflighted = await _preflight_each(targets, check)
        try:
            finished = await _write_checked_alarms(call, selection, plans, alarm, given)
        except BaseException:
            await _release_preflighted(preflighted)
            raise
        if not finished:
            # STOP won: hand the links opened for the check back to their idle timer.
            await _release_preflighted(preflighted)


@dataclass(frozen=True, slots=True)
class _CheckedSession:
    """The connection a side's alarm was checked on."""

    controller: BedController
    generation: object
    alarm_identity: tuple[int, int] | None = None


def _connection_generation(child: BedChild) -> object:
    """Return the side's connection generation; each new connection advances it."""
    return None if isinstance(child, SingleAddressSideCoordinator) else child.connection_generation


async def _write_checked_alarms(
    call: ServiceCall,
    selection: _Selection,
    plans: Mapping[int, AlarmCapability],
    alarm: AlarmRequest,
    given: Collection[str],
) -> bool:
    """Prepare every side, verify the whole selection, then write each target.

    Every write verifies the whole selection again once it owns its link.
    Returns False when a STOP ended the call early: one before the first
    write leaves every bed unwritten, one during the writes skips the rest.
    """
    call_task = asyncio.current_task()
    groups = list(zip(selection.targets, selection.children, strict=True))
    sessions: dict[int, _CheckedSession] = {}
    sequential_langjue = {
        id(child)
        for (parent, _), group in groups
        if _pair_mode(parent) == PAIR_CONNECTION_MODE_SEQUENTIAL
        for child in group
        if child.bed_type == BED_TYPE_LANGJUE
    }
    if sequential_langjue and sum(map(len, selection.children)) > 1:
        # The sequential topology releases each checked session before the next
        # receiver can connect. A Langjue alarm must be written on its checked link.
        raise invalid("langjue_alarm_sequential")

    # Beds that read their stored alarms, and every side of a combined bed, are
    # prepared on a live link before anything is written.
    prepare: list[tuple[BedTarget, str, BedChild]] = []
    for (parent, side), group in groups:
        combined = len({child.operation_identity for child in group}) > 1
        for child in group:
            if id(child) not in sequential_langjue and (plans[id(child)].live_check or combined) and all(
                child is not other for _, _, other in prepare
            ):
                prepare.append((parent, _child_side(parent, side, child), child))

    def step(
        run: Callable[[BedController, AlarmCapability], Awaitable[None]],
    ) -> Callable[[BedController], Coroutine[Any, Any, None]]:
        async def execute(controller: BedController) -> None:
            capability = controller.alarm_capability
            if capability is None:
                raise AlarmError(
                    "alarm_lost", "This bed no longer reports an alarm; reload it and try again"
                )
            await run(controller, capability)

        return _family_command(BedController, execute)

    async def prepare_side(parent: BedTarget, side: str, child: BedChild) -> None:
        plan = plans[id(child)]

        async def check_live(controller: BedController, _capability: AlarmCapability) -> None:
            request = _check_alarm(child.name, controller, alarm, given)
            if plan.live_check:
                await controller.check_alarm(request)
            # Fixed-capacity slots can still need a reported-record stamp.
            identity = controller.alarm_record_identity(request)
            if plan.live_slots and request.mattress_side is None and identity is None:
                raise _bed_changed()
            sessions[id(child)] = _CheckedSession(
                controller,
                _connection_generation(child),
                identity,
            )

        # One side at a time, and a read never preempts movement: a failed
        # check is not a reason to stop anything.
        await _execute_alarm_step(parent, side, step(check_live), plan, cancel_running=False)

    def unchanged(skip: Collection[int]) -> bool:
        """Verify every selected side; False when a STOP reached one.

        ``skip`` holds sides already written, or writing now, whose link this
        call may have changed itself.
        """
        selection.require_unchanged(call)
        for (parent, _side), group in groups:
            sequential = _pair_mode(parent) == PAIR_CONNECTION_MODE_SEQUENTIAL
            for child in group:
                session = sessions.get(id(child))
                if session is None or id(child) in skip:
                    continue
                if _connection_generation(child) == session.generation and (
                    child.is_connected
                    or ready_disconnected_transport(child)
                    # A sequential pair releases each side after its check, by plan.
                    or (sequential and child.last_disconnect_reason == "sequential_switch")
                ):
                    continue
                raise _bed_changed()
        return not selection.stopped()

    def require_write_session(
        parent: BedTarget, group: tuple[BedChild, ...], controller: BedController
    ) -> BedChild:
        """Return the side writing on ``controller``, if it writes on its checked session."""
        checked = [item for item in group if id(item) in sessions]
        owner = next(
            (item for item in checked if sessions[id(item)].controller is controller), None
        )
        if owner is not None or not checked:
            return owner or next(
                (item for item in group if item.controller is controller), group[0]
            )
        # Only the sequential cycle of this call may open a new session.
        child = next((item for item in checked if item.controller is controller), None)
        cycle = parent.sequential_cycle if isinstance(parent, PairedBedCoordinator) else None
        if (
            child is not None
            and cycle is not None
            and cycle.task is call_task
            and isinstance(parent, PairedBedCoordinator)
            and parent.cycle_is_current(cycle)
            and not isinstance(child, SingleAddressSideCoordinator)
            and child.connection_creator_task is cycle.task
            and _connection_generation(child)
            == cast("int", sessions[id(child)].generation) + 1
        ):
            return child
        raise _bed_changed()

    written: set[int] = set()
    stopped = False

    def write(
        parent: BedTarget, group: tuple[BedChild, ...]
    ) -> Callable[[BedController], Coroutine[Any, Any, None]]:
        async def configure(controller: BedController, _capability: AlarmCapability) -> None:
            nonlocal stopped
            child = require_write_session(parent, group, controller)
            # Verify the whole selection again once this side owns its link.
            if stopped or not unchanged({*written, id(child)}):
                stopped = True
                return
            # Check the request again on the controller that actually writes.
            request = _check_alarm(child.name, controller, alarm, given)
            if (session := sessions.get(id(child))) is not None and session.alarm_identity is not None:
                request = dataclasses.replace(request, record_identity=session.alarm_identity)
            if _capability.live_slots and request.mattress_side is None and request.record_identity is None:
                raise _bed_changed()
            if id(child) in sequential_langjue:
                # This is the sole target. Read and write within one link cycle.
                await controller.check_alarm(request)
            await controller.configure_alarm(request)
            written.add(id(child))

        return step(configure)

    async def check_linked(_controller: BedController, _capability: AlarmCapability) -> None:
        # The topology checks all reserved receivers before invoking this callback.
        return None

    with contextlib.ExitStack() as held:
        # Keep checked links up until written, whatever the idle setting.
        for _, _, child in prepare:
            held.enter_context(child.hold_command_connection())
        for (parent, side), group in groups:
            if len(group) > 1 and any(child.bed_type == BED_TYPE_LANGJUE for child in group):
                if selection.stopped():
                    return False
                await _execute_alarm_step(
                    parent, side, step(check_linked), plans[id(group[0])], cancel_running=False
                )
        for parent, side, child in prepare:
            if selection.stopped():
                return False
            await prepare_side(parent, side, child)
        if any(id(child) not in sessions for _, _, child in prepare):
            return False

        for (parent, side), group in groups:
            if not unchanged(written):
                return False
            await _execute_alarm_step(parent, side, write(parent, group), plans[id(group[0])])
            if stopped:
                return False
            written.update(id(child) for child in group)
    return True


async def _execute_alarm_step(
    parent: BedTarget,
    side: str,
    command: Callable[[BedController], Coroutine[Any, Any, None]],
    plan: AlarmCapability,
    *,
    cancel_running: bool | None = None,
) -> None:
    """Run one alarm step, owning the STOP state current right now."""
    resources = ALL_COMMAND_RESOURCES if plan.resource is None else (plan.resource,)
    await _execute_sided_translated(
        parent,
        side,
        command,
        cancel_running=plan.cancel_running if cancel_running is None else cancel_running,
        resource=plan.resource,
        admission=_capture_command_admission(parent, side, resources),
    )


async def handle_sync_clock(call: ServiceCall) -> None:
    """Synchronize each targeted device clock to Home Assistant's local time."""
    targets = _call_targets(call)
    synced: set[int] = set()

    async def sync(controller: BedController) -> None:
        # Both sides of a one-receiver bed share its coordinator, and its clock.
        receiver = id(controller._coordinator)
        if receiver in synced:
            return
        await controller.sync_clock()
        synced.add(receiver)

    if _profile_route(targets, {BED_TYPE_ZSERIES: "zseries"}, SERVICE_SYNC_CLOCK):
        await async_import_modules(call.hass, "beds.serenity.services")
        from .beds.serenity.services import _execute_zseries_alarm

        # Z-Series clocks live on the alarm page, gated by a live manufacturer read.
        await _execute_zseries_alarm(call, sync)
        return

    def check(target: BedChild, controller: BedController) -> None:
        if not controller.supports_clock_sync:
            raise invalid("clock_sync_not_supported", device_name=target.name)

        controller.validate_clock_sync()

    admissions = [
        _capture_command_admission(coordinator, side, ("configuration",))
        for coordinator, side in targets
    ]
    live = _LiveCheck(check)
    preflighted = await _preflight_each(targets, live.preflight)
    command = live.command(targets, sync)
    try:
        for (coordinator, side), admission in zip(targets, admissions, strict=True):
            await _execute_sided_translated(
                coordinator,
                side,
                command,
                cancel_running=False,
                resource="configuration",
                admission=admission,
            )
    except Exception, asyncio.CancelledError:
        await _release_preflighted(preflighted)
        raise


# English text of the support-bundle notifications, used when no translation loads.
_NOTICES: Final = {
    "support_bundle_ready_title": "Adjustable bed: support bundle ready",
    "support_bundle_ready_message": (
        "[**Download the support bundle**]({url})\n\n"
        "Bluetooth messages captured: {count}, over {seconds} seconds.\n\n"
        "Next, attach the file to your bug report or bed support request. The download "
        "link works for one hour or until Home Assistant restarts; the file stays saved "
        "at `{path}`."
    ),
    "support_bundle_warnings": "**While capturing:**",
    "support_bundle_no_logs_title": "Adjustable bed: this bundle will have no logs",
    "support_bundle_no_logs_message": (
        "The capture is running anyway, so you will still get a bundle with the Bluetooth details."
    ),
    "support_bundle_timeout_title": "Adjustable bed: support bundle timed out",
    "support_bundle_timeout_message": (
        "The capture for {address} did not finish within {seconds} seconds. Move the bed "
        "closer to its Bluetooth adapter or proxy, then run the action again."
    ),
    "support_bundle_failed_title": "Adjustable bed: support bundle failed",
    "support_bundle_failed_message": (
        "The support bundle for {address} could not be created. Check the Home Assistant "
        "log for details, then run the action again."
    ),
}


async def _notice(hass: HomeAssistant, key: str, **placeholders: object) -> str:
    """Return one support-bundle notification text in the user's language."""
    from homeassistant.helpers.translation import async_get_translations

    translations = await async_get_translations(
        hass, hass.config.language, "exceptions", {DOMAIN}
    )
    template = translations.get(f"component.{DOMAIN}.exceptions.{key}.message", _NOTICES[key])
    return template.format(**placeholders)


async def handle_generate_support_bundle(call: ServiceCall) -> None:
    """Handle generate_support_bundle service call."""
    hass = call.hass
    from homeassistant.components.persistent_notification import (
        async_create,
        async_dismiss,
    )

    # support_bundle imports support_report.
    await async_import_modules(hass, "support_bundle")
    from .support_bundle import generate_support_bundle, save_support_bundle
    from .support_report import async_check_log_file, build_missing_log_notice

    device_ids = call.data.get(CONF_DEVICE_ID, [])
    target_address = call.data.get(ATTR_TARGET_ADDRESS)
    capture_duration = call.data.get(ATTR_CAPTURE_DURATION, DEFAULT_CAPTURE_DURATION)
    include_logs = call.data.get(ATTR_INCLUDE_LOGS, True)

    address: str | None = None
    coordinator: BedChild | None = None
    entry: ConfigEntry | None = None
    selected_device_id: str | None = None

    if target_address:
        from .config_flow import is_valid_mac_address

        address = str(target_address).upper().replace("-", ":")
        if not is_valid_mac_address(address):
            raise invalid("invalid_mac_address", address=str(target_address))
        _LOGGER.info(
            "Generating support bundle for unconfigured device at %s",
            address,
        )
    elif device_ids:
        if len(device_ids) > 1:
            raise invalid("multiple_device_targets_not_supported")
        # str() narrows the untyped service-call value for the str-typed parameter
        selected_device_id = str(device_ids[0])
        target = _get_support_bundle_target_from_device(hass, selected_device_id)
        if target is not None:
            address, coordinator, entry = target
            # By address only: the device name is typed text the bundle leaves out.
            _LOGGER.info("Generating support bundle for configured device at %s", address)
        else:
            raise _missing_device_error(selected_device_id)
    else:
        raise invalid("missing_target")

    assert address is not None

    # Probe the log file before capturing. The capture runs for minutes, and a
    # bundle without logs is missing the evidence that matters most for
    # connection problems, so warn while the user can still fix it and re-run
    # rather than only telling them afterwards (issue #385).
    log_notification_id = f"adjustable_bed_support_bundle_logs_{address.replace(':', '_').lower()}"
    # Only retract a notice this invocation still owns. The id is
    # address-stable on purpose, so a later run can clear a stale warning left
    # by an earlier one; per-invocation ids would lose that. The cost is that
    # overlapping captures share the id, so record who raised it last and let
    # only that invocation retract it. A later capture that re-raises the notice
    # takes ownership, and the earlier one then leaves it alone.
    log_notice_token = object()
    owns_log_notice = False
    # What the probe concluded, kept so the finished-bundle notice can repeat the
    # guidance even when the capture itself reports something else (an empty file
    # comes back as "empty", not "unavailable") or never read the log at all.
    probe_reason: str | None = None
    probe_error: str | None = None
    if include_logs:
        try:
            # O_NONBLOCK does not make regular-file I/O asynchronous, so a
            # stalled network or FUSE mount can still block the open. This probe
            # runs before the capture's own timeout, so bound it here or the
            # service could hang without ever starting or reporting. The
            # executor thread stays blocked either way, but the service does not.
            log_check = await asyncio.wait_for(async_check_log_file(hass), _LOG_PROBE_TIMEOUT)
        except TimeoutError:
            # Inconclusive, not proof of a wedged path: Home Assistant's shared
            # executor can be saturated enough that the job never started. Say
            # nothing and change nothing - the capture performs its own read and
            # reports what it actually found. Disabling logs here would drop them
            # from a minutes-long capture over a five-second queue delay.
            _LOGGER.warning(
                "Timed out checking whether %s is readable; capturing anyway",
                hass.config.path("home-assistant.log"),
            )
            log_check = None
        if log_check is not None:
            if log_check["available"]:
                # A previous run may have warned about missing logs, and that
                # warning is address-stable, so it would otherwise sit there
                # contradicting a bundle that does contain logs. Only clear it
                # when no capture still owns it: another logless capture may be
                # running right now and its warning is not stale.
                if not hass.data.get(_LOG_NOTICE_OWNERS, {}).get(log_notification_id):
                    async_dismiss(hass, log_notification_id)
            else:
                probe_reason = log_check["reason"]
                probe_error = log_check["error"]
                _LOGGER.warning(
                    "Support bundle for %s will not include logs: %s (%s)",
                    address,
                    log_check["path"],
                    probe_reason,
                )
                async_create(
                    hass,
                    build_missing_log_notice(log_check["reason"], log_check["error"], future=True)
                    + "\n\n"
                    + await _notice(hass, "support_bundle_no_logs_message"),
                    title=await _notice(hass, "support_bundle_no_logs_title"),
                    notification_id=log_notification_id,
                )
                hass.data.setdefault(_LOG_NOTICE_OWNERS, {}).setdefault(
                    log_notification_id, set()
                ).add(log_notice_token)
                owns_log_notice = True

    try:
        report = await asyncio.wait_for(
            generate_support_bundle(
                hass,
                address=address,
                capture_duration=capture_duration,
                include_logs=include_logs,
                coordinator=coordinator,
                entry=entry,
                device_id=selected_device_id,
            ),
            timeout=capture_duration + 120,
        )
        filepath = await hass.async_add_executor_job(
            save_support_bundle,
            hass,
            report,
            address,
        )

        download_url = register_download(hass, filepath)
        notification_count = len(report.get("notifications", []))
        evidence = report.get("evidence", {})
        evidence_warnings = evidence.get("warnings", [])
        warning_summary = ""
        if evidence_warnings:
            warning_summary = "\n\n" + await _notice(hass, "support_bundle_warnings") + "\n" + "\n".join(
                f"- {warning}" for warning in evidence_warnings
            )

        # A bundle without logs usually cannot explain why a command failed, and
        # the user only learns that after a maintainer asks for a second one. Say
        # it up front, at the moment they still have the bed in front of them.
        # The capture is the authority: it actually read the file, so a log that
        # appeared or filled up during the window really is usable whatever the
        # probe saw beforehand. The one carry-over is a file the probe measured
        # as empty, which the capture reports as "empty" rather than
        # "unavailable" but which is still unusable.
        log_status = evidence.get("log_capture_status")
        logs_missing = include_logs and (
            log_status == "unavailable" or (log_status == "empty" and probe_reason == "empty_file")
        )
        logging_notice = ""
        if logs_missing:
            log_error = evidence.get("log_capture_error") or probe_error
            _LOGGER.warning(
                "Support bundle for %s was generated without logs: %s",
                address,
                log_error or "the Home Assistant log file could not be read",
            )
            logging_notice = "\n\n" + build_missing_log_notice(
                evidence.get("log_capture_reason") or probe_reason, log_error
            )

        async_create(
            hass,
            await _notice(
                hass,
                "support_bundle_ready_message",
                url=download_url,
                path=filepath,
                count=notification_count,
                seconds=capture_duration,
            )
            + logging_notice
            + warning_summary,
            title=await _notice(hass, "support_bundle_ready_title"),
            notification_id=f"adjustable_bed_support_bundle_{address.replace(':', '_').lower()}",
        )
        _LOGGER.info("Support bundle saved to %s", filepath)
    except TimeoutError:
        _LOGGER.exception(
            "Support bundle generation timed out after %d seconds for %s",
            capture_duration + 120,
            address,
        )
        async_create(
            hass,
            await _notice(
                hass,
                "support_bundle_timeout_message",
                address=address,
                seconds=capture_duration + 120,
            ),
            title=await _notice(hass, "support_bundle_timeout_title"),
            notification_id=f"adjustable_bed_support_bundle_error_{address.replace(':', '_').lower()}",
        )
        raise
    except Exception:
        _LOGGER.exception("Failed to generate support bundle for %s", address)
        async_create(
            hass,
            await _notice(hass, "support_bundle_failed_message", address=address),
            title=await _notice(hass, "support_bundle_failed_title"),
            notification_id=f"adjustable_bed_support_bundle_error_{address.replace(':', '_').lower()}",
        )
        raise
    finally:
        # Whatever happened, the capture is no longer running, so the
        # pre-capture notice must not keep claiming that it is. A finally also
        # covers cancellation: CancelledError inherits from BaseException, so an
        # automation stopped mid-capture would skip an except Exception handler
        # and strand the notice forever.
        owners = hass.data.get(_LOG_NOTICE_OWNERS, {}).get(log_notification_id)
        if owns_log_notice and owners is not None:
            owners.discard(log_notice_token)
            # Retract only once the last overlapping logless capture is done,
            # so a short one finishing first cannot pull the notice out from
            # under a longer one that is still running without logs.
            if not owners:
                hass.data[_LOG_NOTICE_OWNERS].pop(log_notification_id, None)
                async_dismiss(hass, log_notification_id)


def _import_service_registrars() -> tuple[Callable[[HomeAssistant], None], ...]:
    """Import the family action modules, which import this one, in the import executor."""
    from .beds.ambient.services import async_register_ambient_services
    from .beds.baseremote.services import register_services as register_baseremote_services
    from .beds.bedgear.services import async_register_bedgear_services
    from .beds.bedtech.services import register_services as register_bedtech_services
    from .beds.casper_base.services import async_register_casper_base_services
    from .beds.cheerssleep.services import register_services as register_cheerssleep_services
    from .beds.comfort_enhancement3.services import register_services as register_apex_services
    from .beds.customatic.services import async_register_customatic_services
    from .beds.customatic_demo.services import (
        register_services as register_customatic_demo_services,
    )
    from .beds.dorsal.services import register_services as register_dorsal_services
    from .beds.doublesleep.services import async_register_doublesleep_services
    from .beds.dreamsense.services import async_register_dreamsense_services
    from .beds.enso2.services import register_services as register_enso2_services
    from .beds.ergobq.services import register_services as register_ergobq_services
    from .beds.fsm_relax.services import async_register_fsm_relax_services
    from .beds.furnimove.services import async_register_furnimove_services
    from .beds.gmmotor.services import async_register_gmmotor_services
    from .beds.goodvibe.services import async_register_goodvibe_services
    from .beds.hjbed.services import async_register_hjbed_services
    from .beds.instant_comfort.services import (
        register_services as register_instant_comfort_services,
    )
    from .beds.jiecang.app_services import async_register_jiecang_app_services
    from .beds.kaidi.comfy_services import async_register_comfy_services
    from .beds.kaidi.floyd_services import async_register_floyd_services
    from .beds.kaidi.rize_services import async_register_rize_services
    from .beds.keeson.agingplace_services import register_services as register_agingplace_services
    from .beds.keeson.betterliving2_services import (
        register_services as register_betterliving2_services,
    )
    from .beds.keeson.somos_services import register_services as register_somos_services
    from .beds.leggett.okin_services import async_register_leggett_okin_services
    from .beds.limoss.remote_services import async_register_limoss_remote_services
    from .beds.linak.services import async_register_linak_services
    from .beds.linx.services import register_services as register_linx_services
    from .beds.logicdata.app_services import async_register_logicdata_app_services
    from .beds.majestichome.services import async_register_majestichome_services
    from .beds.mlily_remote.services import register_services as register_mlily_remote_services
    from .beds.mline.services import register_services as register_mline_services
    from .beds.motion_bed.services import async_register_motion_bed_services
    from .beds.motomotion.services import async_register_motomotion_services
    from .beds.myside.services import register_services as register_myside_services
    from .beds.octo.services import async_register_octo_services
    from .beds.okimiki.services import register_services as register_okimiki_services
    from .beds.onlysnore.services import register_services as register_onlysnore_services
    from .beds.personal_comfort.services import (
        register_services as register_personal_comfort_services,
    )
    from .beds.reverie.services import async_register_reverie_services
    from .beds.richmat.jerome_services import async_register_jerome_repeat_alarm
    from .beds.richmat_app.services import async_register_richmat_app_services
    from .beds.richmat_classic.homezone_services import async_register_homezone_services
    from .beds.richmat_classic.jerome_services import async_register_jerome_services
    from .beds.richmat_classic.lp2_services import async_register_lp2_services
    from .beds.richmat_classic.resource_services import async_register_resource_bed_services
    from .beds.richmat_classic.rise_services import async_register_richmat_rise_services
    from .beds.richmat_classic.services import async_register_richmat_classic_services
    from .beds.richmat_classic.sleepfunction_services import async_register_sleepfunction_services
    from .beds.richmat_legacy.services import async_register_richmat_legacy_services
    from .beds.richmat_mh.app_services import (
        register_services as register_mh_app_services,
    )
    from .beds.richmat_mh.services import async_register_richmat_mh_services
    from .beds.rmcontrol.services import async_register_rmcontrol_services
    from .beds.sinca_comfort.services import register_services as register_sinca_comfort_services
    from .beds.sleep_number.services import async_register_sleep_number_services
    from .beds.sleeptracker.services import async_register_sleeptracker_services
    from .beds.solace.services import async_register_solace_services
    from .beds.sonicsleep.services import async_register_sonicsleep_services
    from .beds.starcode.accessory_group import register_group_services
    from .beds.superior_sleep.services import register_services as register_superior_sleep_services
    from .beds.suta.services import register_services as register_suta_services
    from .beds.suta_king_koil.services import register_services as register_suta_king_koil_services
    from .beds.svane.services import async_register_svane_services
    from .beds.symphony.services import register_services as register_symphony_sense_services

    # Ultramatic registers no action of its own; set_alarm uses this module.
    from .beds.ultramatic import services as _ultramatic_alarm  # noqa: F401
    from .position_estimate_services import async_register_position_estimate_services

    return (
        async_register_ambient_services,
        async_register_bedgear_services,
        register_mline_services,
        register_sinca_comfort_services,
        register_instant_comfort_services,
        register_personal_comfort_services,
        register_mlily_remote_services,
        register_bedtech_services,
        register_ergobq_services,
        register_linx_services,
        register_somos_services,
        register_cheerssleep_services,
        register_enso2_services,
        register_symphony_sense_services,
        async_register_motion_bed_services,
        async_register_casper_base_services,
        async_register_gmmotor_services,
        async_register_richmat_mh_services,
        register_mh_app_services,
        async_register_position_estimate_services,
        async_register_richmat_classic_services,
        async_register_homezone_services,
        async_register_sleepfunction_services,
        async_register_lp2_services,
        async_register_jerome_services,
        async_register_jerome_repeat_alarm,
        register_baseremote_services,
        async_register_resource_bed_services,
        async_register_dreamsense_services,
        async_register_richmat_legacy_services,
        async_register_richmat_rise_services,
        async_register_motomotion_services,
        async_register_hjbed_services,
        register_myside_services,
        async_register_richmat_app_services,
        async_register_goodvibe_services,
        register_okimiki_services,
        async_register_rmcontrol_services,
        async_register_sleep_number_services,
        register_dorsal_services,
        async_register_doublesleep_services,
        async_register_sleeptracker_services,
        async_register_reverie_services,
        async_register_linak_services,
        async_register_solace_services,
        async_register_sonicsleep_services,
        async_register_majestichome_services,
        register_suta_services,
        register_suta_king_koil_services,
        async_register_leggett_okin_services,
        async_register_floyd_services,
        async_register_rize_services,
        async_register_comfy_services,
        async_register_octo_services,
        async_register_customatic_services,
        async_register_furnimove_services,
        async_register_fsm_relax_services,
        async_register_limoss_remote_services,
        register_apex_services,
        register_betterliving2_services,
        register_agingplace_services,
        register_onlysnore_services,
        register_customatic_demo_services,
        async_register_logicdata_app_services,
        async_register_jiecang_app_services,
        async_register_svane_services,
        register_group_services,
        register_superior_sleep_services,
    )


async def async_register_services(hass: HomeAssistant) -> None:
    """Register the Adjustable Bed services (idempotent)."""
    registrars = await hass.async_add_import_executor_job(_import_service_registrars)
    async_setup_support_logs(hass)
    if hass.services.has_service(DOMAIN, SERVICE_GOTO_PRESET):
        return  # Services already registered

    for register in registrars:
        register(hass)
    hass.services.async_register(
        DOMAIN,
        SERVICE_GOTO_PRESET,
        handle_goto_preset,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required(ATTR_PRESET): vol.All(_whole_number, vol.Range(min=1)),
                vol.Optional(ATTR_DURATION): _hold_seconds,
                **SIDE_FIELD,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SAVE_PRESET,
        handle_save_preset,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required(ATTR_PRESET): vol.All(_whole_number, vol.Range(min=1)),
                **SIDE_FIELD,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP_ALL,
        handle_stop_all,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                **SIDE_FIELD,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_POSITION,
        handle_set_position,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required(ATTR_MOTOR): vol.In(POSITION_MOTOR_OPTIONS),
                # No max cap here - per-motor validation handles bed-specific limits
                vol.Required(ATTR_POSITION): vol.All(vol.Coerce(float), vol.Range(min=0)),
                **SIDE_FIELD,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_POSITIONS,
        handle_set_positions,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required(ATTR_POSITIONS): vol.All(
                    [
                        {
                            vol.Required(ATTR_MOTOR): vol.In(POSITION_MOTOR_OPTIONS),
                            vol.Required(ATTR_POSITION): vol.All(
                                vol.Coerce(float), vol.Range(min=0)
                            ),
                        }
                    ],
                    vol.Length(min=1, max=4),
                ),
                **SIDE_FIELD,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TIMED_MOVE,
        handle_timed_move,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required(ATTR_MOTOR): vol.In(TIMED_MOVE_MOTOR_OPTIONS),
                vol.Required(ATTR_DIRECTION): vol.In(["up", "down"]),
                vol.Required(ATTR_DURATION_MS): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_TIMED_MOVE_DURATION_MS, max=MAX_TIMED_MOVE_DURATION_MS),
                ),
                **SIDE_FIELD,
                **HOLD_LEASE_FIELDS,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RENAME,
        handle_rename,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                # Each target's controller applies its app's own name rule.
                vol.Required(ATTR_NAME): cv.string,
                **SIDE_FIELD,
            }
        ),
    )
    hold_fields = {
        vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
        vol.Required(ATTR_DURATION): _hold_seconds,
        **SIDE_FIELD,
    }
    hass.services.async_register(
        DOMAIN,
        SERVICE_HOLD_CONTROL,
        handle_hold_control,
        # Each target's controller declares its valid controls.
        schema=vol.Schema(
            {
                **hold_fields,
                **HOLD_LEASE_FIELDS,
                vol.Required(ATTR_CONTROL): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_ALARM,
        handle_set_alarm,
        # Each target's controller declares which of these its alarm accepts.
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): DEVICE_IDS,
                vol.Required(ATTR_ENABLED): cv.boolean,
                vol.Optional(ATTR_TIME): cv.time,
                vol.Optional(ATTR_WEEKDAYS): vol.All(cv.ensure_list, [vol.In(ALARM_WEEKDAYS)]),
                vol.Optional(ATTR_SLOT): vol.All(_whole_number, vol.Range(min=0, max=255)),
                vol.Optional("wake_action"): vol.In(WAKE_ACTIONS),
                vol.Optional(ATTR_MASSAGE): cv.boolean,
                vol.Optional("head_massage_level"): vol.All(_whole_number, vol.Range(min=0, max=10)),
                vol.Optional("foot_massage_level"): vol.All(_whole_number, vol.Range(min=0, max=10)),
                vol.Optional("massage_intensity"): vol.All(_whole_number, vol.Range(min=1, max=10)),
                vol.Optional("massage_duration"): vol.All(_whole_number, vol.Range(min=1, max=120)),
                vol.Optional("sleep_timer"): vol.All(_whole_number, vol.Range(min=1, max=120)),
                vol.Optional("massage_zone"): vol.In(MASSAGE_ZONES),
                vol.Optional("mattress_side"): vol.In(MATTRESS_SIDES),
                vol.Optional(ATTR_SOUND): vol.In(ALARM_SOUNDS),
                vol.Optional("light"): cv.boolean,
                vol.Optional("confirm_custom_position"): cv.boolean,
                **SIDE_FIELD,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SYNC_CLOCK,
        handle_sync_clock,
        schema=vol.Schema({vol.Required(CONF_DEVICE_ID): DEVICE_IDS, **SIDE_FIELD}),
    )
    # Admin only: it captures any address and writes a file anyone can download.
    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_GENERATE_SUPPORT_BUNDLE,
        handle_generate_support_bundle,
        schema=vol.Schema(
            {
                vol.Exclusive(CONF_DEVICE_ID, "target"): cv.ensure_list,
                vol.Exclusive(ATTR_TARGET_ADDRESS, "target"): cv.string,
                vol.Optional(ATTR_CAPTURE_DURATION, default=DEFAULT_CAPTURE_DURATION): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=MIN_CAPTURE_DURATION, max=MAX_CAPTURE_DURATION),
                ),
                vol.Optional(ATTR_INCLUDE_LOGS, default=True): cv.boolean,
            }
        ),
    )


    _LOGGER.debug("Registered Adjustable Bed services")
