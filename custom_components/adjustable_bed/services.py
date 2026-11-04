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
import logging
from collections.abc import (
    AsyncIterator,
    Awaitable,
    Callable,
    Collection,
    Coroutine,
    Mapping,
)
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.service import async_get_device_and_config_entry
from homeassistant.util import dt as dt_util

from .alarm_table import AlarmTableSchedule, OneTimeAlarmRecord, WeeklyAlarmRecord
from .command_scheduler import (
    ALL_COMMAND_RESOURCES,
    HoldClaim,
    HoldLease,
    StaleHoldLease,
    command_resources,
    current_command_context,
)
from .const import (
    BED_TYPE_ERGOMOTION,
    BED_TYPE_FURNIMOVE,
    BED_TYPE_KAIDI,
    BED_TYPE_KEESON,
    BED_TYPE_LIMOSS_REMOTE,
    BED_TYPE_LINAK,
    BED_TYPE_SERTA_MP_REMOTE,
    BED_TYPE_SLEEP_NUMBER_MCR,
    BED_TYPE_SLEEPYS_BOX25,
    BED_TYPE_SLEEPYS_ELITE_APP,
    BED_TYPE_SVANE,
    BED_TYPE_VMATBASIC,
    BED_TYPE_ZSERIES,
    CONF_BED_TYPE,
    CONF_MOTOR_COUNT,
    CONF_PROTOCOL_VARIANT,
    DEFAULT_MOTOR_COUNT,
    DOMAIN,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
    TIMED_MOVE_MOTOR_OPTIONS,
    bed_type_has_position_feedback,
)
from .execution import HOLD_CEILING_MS
from .paired_coordinator import (
    BedChild,
    PairedBedCoordinator,
    SingleAddressSideCoordinator,
)
from .paired_devices import side_identifier
from .pairing import is_paired, pair_member_addresses
from .position_estimate import (
    invalidate_on_command,
    track_held_control,
    track_motor_command,
    track_stream_member,
)

if TYPE_CHECKING:
    from .beds.base import BedController, ControllerMotorHoldSpec, SideBoundController
    from .beds.limoss_remote import LimossRemoteController
    from .beds.svane import SvaneHoldAdmission

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


def _capture_command_admission(
    coordinator: BedTarget,
    side: str,
    resources: Collection[str] = ALL_COMMAND_RESOURCES,
) -> _CommandAdmission:
    """Capture the selected physical owners before live validation/connect waits."""
    scope = command_resources(*resources)
    if isinstance(coordinator, PairedBedCoordinator):
        targets = coordinator._targets_for(side)
        pair_generations = {
            target_side: coordinator._pair_cancel_generation(target_side, scope)
            for target_side, _child in targets
        }
    else:
        targets = [(SIDE_BOTH, coordinator)]
        pair_generations = {}

    stop_epochs: dict[str, int] = {}
    for target_side, child in targets:
        owner = getattr(child, "_single_inner", child)
        scheduler = getattr(owner, "_command_scheduler", None)
        stop_epoch = getattr(scheduler, "stop_epoch", None)
        if isinstance(stop_epoch, int) and not isinstance(stop_epoch, bool):
            stop_epochs[target_side] = stop_epoch
    return _CommandAdmission(scope, pair_generations, stop_epochs)


# Service names
SERVICE_GOTO_PRESET = "goto_preset"
SERVICE_GENERATE_SUPPORT_BUNDLE = "generate_support_bundle"
SERVICE_SAVE_PRESET = "save_preset"
SERVICE_SET_POSITION = "set_position"
SERVICE_SET_POSITIONS = "set_positions"
SERVICE_STOP_ALL = "stop_all"
SERVICE_TIMED_MOVE = "timed_move"
SERVICE_LINAK_RENAME = "linak_rename"
SERVICE_HOLD_CONTROL = "hold_control"
SERVICE_RENAME = "rename"
SERVICE_SYNC_CLOCK = "sync_clock"
SERVICE_CONFIGURE_ALARM_SCHEDULE = "configure_alarm_schedule"
# Released per-app names that now alias the generic actions above (linak_rename
# is listed above).
SERVICE_LEGGETT_HOLD_CONTROL = "leggett_hold_control"
SERVICE_LOGICDATA_RENAME = "logicdata_rename"
SERVICE_JIECANG_RENAME = "jiecang_rename"
SERVICE_MALOUF_SYNC_CLOCK = "malouf_sync_clock"
ATTR_SLOT = "slot"
ATTR_MODE = "mode"
ATTR_CONFIRM_CUSTOM_MODE = "confirm_custom_mode"

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
ATTR_SECONDS = "seconds"
ATTR_ACTIONS = "actions"
ATTR_ACTION = "action"
ATTR_LIFETIME = "lifetime"
ATTR_PAUSE = "pause"
ATTR_RECURRENCE_COUNT = "recurrence_count"
ATTR_RECURRENCE_MINUTES = "recurrence_minutes"
ATTR_ENABLED = "enabled"
ATTR_TIME = "time"
ATTR_WEEKDAYS = "weekdays"
ATTR_MODE = "mode"
ATTR_MASSAGE = "massage"
ATTR_SOUND = "sound"
ATTR_TRACK = "track"
ATTR_VOLUME = "volume"
ATTR_MINUTES = "minutes"
ATTR_CONTROL = "control"
ATTR_HEAD_LEVEL = "head_level"
ATTR_FOOT_LEVEL = "foot_level"
ATTR_WAKE_MODE = "wake_mode"


SOLACE_WEEKDAY_OPTIONS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


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

LEGGETT_HELD_CONTROLS = (
    "flat",
    "snore",
    "lights_toggle",
    "massage_toggle",
    "massage_wave",
    "massage_head_up",
    "massage_head_down",
    "massage_foot_up",
    "massage_foot_down",
    "memory_1",
    "memory_2",
    "store",
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


def _resolve_sided_target(
    hass: HomeAssistant, device_id: str
) -> tuple[BedTarget, str | None] | None:
    """Resolve (coordinator, inferred_side) for a sided service target.

    ``inferred_side`` is the left/right of a targeted paired child sub-device
    (matched by its MAC identifier), or ``None`` for a single bed or the
    paired parent device. Lets a caller targeting one side's device act on
    just that side without passing ``side`` explicitly.
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
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is None:
        return None
    inferred_side: str | None = None
    if isinstance(coordinator, PairedBedCoordinator):
        identifiers = {value.upper() for domain, value in device.identifiers if domain == DOMAIN}
        for side in coordinator.children:
            if side_identifier(coordinator, side)[1].upper() in identifiers:
                inferred_side = side
                break
        parent_identifiers = {
            value.upper()
            for domain, value in coordinator.device_info.get("identifiers", set())
            if domain == DOMAIN
        }
        if inferred_side is None and not identifiers.intersection(parent_identifiers):
            raise ServiceValidationError(
                "The selected bed side is unavailable",
                translation_domain=DOMAIN,
                translation_key="side_unavailable",
            )
    return coordinator, inferred_side


def _resolve_sided_targets(
    hass: HomeAssistant,
    device_ids: list[str],
    explicit_side: str | None,
) -> tuple[list[tuple[BedTarget, str]], list[str]]:
    """Group sided-service targets by coordinator, merging inferred sides.

    Targeting both of a pair's child devices (or the parent) in one call
    collapses to a single ``both`` fan-out - preserving the both-failure
    contract - instead of two separate side commands. Each coordinator
    appears once in first-seen order. Returns (targets, missing_device_ids).
    """
    ordered: list[int] = []
    by_key: dict[int, tuple[BedTarget, set[str | None]]] = {}
    missing: list[str] = []
    for device_id in device_ids:
        resolved = _resolve_sided_target(hass, device_id)
        if resolved is None:
            missing.append(device_id)
            continue
        coordinator, inferred_side = resolved
        if (
            inferred_side is not None
            and explicit_side is not None
            and explicit_side != inferred_side
        ):
            raise ServiceValidationError(
                f"The selected {inferred_side} child device conflicts with side {explicit_side}",
                translation_domain=DOMAIN,
                translation_key="side_selection_conflict",
                translation_placeholders={"inferred_side": inferred_side, "side": explicit_side},
            )
        key = id(coordinator)
        if key not in by_key:
            by_key[key] = (coordinator, set())
            ordered.append(key)
        by_key[key][1].add(inferred_side)

    targets: list[tuple[BedTarget, str]] = []
    for key in ordered:
        coordinator, sides = by_key[key]
        if explicit_side is not None:
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


def _missing_device_error(device_id: str) -> ServiceValidationError:
    """Build the error for a service target that resolved to no bed."""
    return ServiceValidationError(
        f"Could not find Adjustable Bed device with ID {device_id}",
        translation_domain=DOMAIN,
        translation_key="device_not_found",
        translation_placeholders={"device_id": device_id},
    )


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
            raise ServiceValidationError(
                f"{entry.title} is a paired bed; target one side's device for the support bundle.",
                translation_domain=DOMAIN,
                translation_key="bundle_needs_side_for_paired",
                translation_placeholders={"device_name": entry.title},
            )
    if not isinstance(address, str):
        return None

    coordinator: BedChild | None = None
    stored = hass.data.get(DOMAIN, {}).get(entry_id)
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


async def _get_controller_for_service(
    coordinator: BedChild,
) -> BedController | SideBoundController:
    """Return an active controller for service validation/execution.

    Service calls may arrive while the coordinator is idle-disconnected and
    controller is None. Reconnect first so capability checks don't fail with
    a false "not supported" error.
    """
    controller = coordinator.controller
    if controller is not None:
        if getattr(controller, "requires_disconnected_transport", False) is True:
            if getattr(controller, "disconnected_transport_ready", False) is not True:
                raise ServiceValidationError(
                    f"Device '{coordinator.name}' local Pairlink session is not ready"
                )
        return controller

    capability_controller = coordinator.capability_controller
    if (
        capability_controller is not None
        and getattr(capability_controller, "requires_disconnected_transport", False) is True
    ):
        if getattr(capability_controller, "disconnected_transport_ready", False) is not True:
            raise ServiceValidationError(
                f"Device '{coordinator.name}' local Pairlink session is not ready"
            )
        return capability_controller

    runtime = getattr(coordinator, "_pairlink_runtime", None)
    if getattr(getattr(runtime, "role", None), "value", None) == "peripheral":
        raise ServiceValidationError(
            f"Device '{coordinator.name}' local Pairlink controller is unavailable"
        )

    _LOGGER.debug(
        "No active controller for %s during service call; attempting reconnect",
        coordinator.name,
    )
    connected = await coordinator.async_ensure_connected(reset_timer=False)
    controller = coordinator.controller
    if not connected or controller is None:
        raise ServiceValidationError(
            f"Device '{coordinator.name}' is currently unavailable (unable to connect)",
        )
    return controller


async def _validation_controller(
    coordinator: BedTarget,
    target: BedChild,
    preflighted: PreflightedSides,
) -> BedController | SideBoundController:
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
        if getattr(controller, "requires_disconnected_transport", False) is True and getattr(
            controller, "disconnected_transport_ready", False
        ) is not True:
            raise ServiceValidationError(
                f"Device '{target.name}' local Pairlink session is not ready"
            )
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
            raise ServiceValidationError(
                f"This bed has no {side} side",
                translation_domain=DOMAIN,
                translation_key="side_not_available",
                translation_placeholders={"side": side},
            )
        return [child]

    if side != SIDE_BOTH:
        raise ServiceValidationError(
            "This is a single bed; the Left/Right/Both option only applies to paired beds.",
            translation_domain=DOMAIN,
            translation_key="side_not_supported",
        )
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
    if isinstance(coordinator, PairedBedCoordinator):
        if lease is not None:
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
            return
        await coordinator.async_execute_controller_command(
            command_fn,
            side=side,
            cancel_running=cancel_running,
            skip_disconnect=skip_disconnect,
            resource=resource,
            resources=resources,
            expected_pair_generations=expected_pair_generations,
            expected_stop_epochs=expected_stop_epochs,
        )
    elif lease is not None:
        await coordinator.async_execute_controller_command(
            command_fn,
            cancel_running=cancel_running,
            skip_disconnect=skip_disconnect,
            resource=resource,
            resources=resources,
            expected_stop_epoch=expected_stop_epoch,
            lease=lease,
        )
    else:
        if expected_stop_epoch is None:
            await coordinator.async_execute_controller_command(
                command_fn,
                cancel_running=cancel_running,
                skip_disconnect=skip_disconnect,
                resource=resource,
                resources=resources,
            )
        else:
            await coordinator.async_execute_controller_command(
                command_fn,
                cancel_running=cancel_running,
                skip_disconnect=skip_disconnect,
                resource=resource,
                resources=resources,
                expected_stop_epoch=expected_stop_epoch,
            )


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
async def _release_idle_on_validation_failure(
    coordinator: BedChild,
) -> AsyncIterator[None]:
    """Release a bed reconnected for a per-motor service if validation fails.

    _get_controller_for_service reconnects with reset_timer=False; without
    this an invalid set_position/timed_move would leave the BLE link open
    with no idle timer (the preset preflight path already guards this way)."""
    try:
        yield
    except ServiceValidationError:
        if coordinator.is_connected:
            with contextlib.suppress(Exception):
                await coordinator.async_ensure_connected(reset_timer=True)
        raise


def _plan_key(target: BedChild) -> int:
    """Stable per-side key for a validated plan (a proxy shares its child's identity)."""
    return getattr(target, "operation_identity", id(target))


def _timed_move_resource(target: BedChild, motor: str) -> str:
    """Read the selected motor's existing scheduler resource without awaiting."""
    controller = target.capability_controller
    if controller is not None:
        spec = next(
            (item for item in controller.motor_control_specs if item.key == motor),
            None,
        )
        if spec is not None:
            return spec.scheduler_resource or f"motor:{spec.position_key or spec.key}"
    return f"motor:{motor}"


async def handle_goto_preset(call: ServiceCall) -> None:
    """Handle goto_preset service call with sided all-target preflight."""
    from .limoss_remote_services import (
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

    async with _limoss_remote_reload_transaction(targets):
        await _preflight_live_limoss_remote(
            targets, lambda ctrl: ctrl.validate_memory_recall(preset)
        )

        # Phase 1: validate the preset on EVERY targeted side before moving any
        # bed, so a multi-target call never half-executes.
        preflighted: PreflightedSides = []
        try:
            for coordinator, side in targets:
                for target in _command_targets(coordinator, side):
                    controller = await _validation_controller(coordinator, target, preflighted)
                    if not controller.supports_memory_presets:
                        raise ServiceValidationError(
                            f"Device '{target.name}' does not support memory presets",
                            translation_domain=DOMAIN,
                            translation_key="memory_presets_not_supported",
                            translation_placeholders={"device_name": target.name},
                        )
                    # Validate preset against controller's memory slot count
                    slot_count = controller.memory_slot_count
                    if preset > slot_count:
                        raise ServiceValidationError(
                            f"Device '{target.name}' only supports memory presets 1-{slot_count}. "
                            f"Preset {preset} is not available for this bed type.",
                            translation_domain=DOMAIN,
                            translation_key="invalid_preset_number",
                            translation_placeholders={
                                "device_name": target.name,
                                "max_preset": str(slot_count),
                                "requested_preset": str(preset),
                            },
                        )
                    if hold_ms is not None and not controller.supports_held_memory_recall:
                        raise ServiceValidationError(
                            f"Device '{target.name}' does not accept a preset hold duration",
                            translation_domain=DOMAIN,
                            translation_key="preset_duration_not_supported",
                            translation_placeholders={"device_name": target.name},
                        )
                    try:
                        controller.validate_memory_recall(preset)
                    except ValueError as error:
                        raise ServiceValidationError(str(error)) from error
        except ServiceValidationError:
            await _release_preflighted(preflighted)
            raise

        async def recall(controller: BedController | SideBoundController) -> None:
            if hold_ms is None:
                await controller.preset_memory(preset)
            else:
                await controller.recall_memory(preset, hold_ms=hold_ms)

        # Phase 2: every target validated - now move them. If one bed's command
        # fails, release the still-connected preflighted beds that never ran (and
        # so never reset their idle timer) before propagating.
        try:
            for coordinator, side in targets:
                await _execute_sided(coordinator, side, invalidate_on_command(hass, recall))
        except Exception:
            await _release_preflighted(preflighted)
            raise


async def handle_save_preset(call: ServiceCall) -> None:
    """Handle save_preset service call with sided all-target preflight."""
    from .limoss_remote_services import (
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

    def validate_remote_slot(controller: LimossRemoteController | SideBoundController) -> None:
        if (
            not controller.supports_memory_programming
            or not 1 <= preset <= controller.memory_slot_count
        ):
            raise ValueError("The fresh Limoss Remote profile cannot program this memory slot")

    async with _limoss_remote_reload_transaction(targets):
        await _preflight_live_limoss_remote(targets, validate_remote_slot)

        # Phase 1: validate that every targeted side can program this slot before
        # programming any, so a multi-target call never half-executes.
        preflighted: PreflightedSides = []
        try:
            for coordinator, side in targets:
                for target in _command_targets(coordinator, side):
                    controller = await _validation_controller(coordinator, target, preflighted)
                    if not controller.supports_memory_programming:
                        raise ServiceValidationError(
                            f"Device '{target.name}' does not support programming memory presets",
                            translation_domain=DOMAIN,
                            translation_key="memory_programming_not_supported",
                            translation_placeholders={"device_name": target.name},
                        )
                    # Validate preset against controller's memory slot count
                    slot_count = controller.memory_slot_count
                    if preset > slot_count:
                        raise ServiceValidationError(
                            f"Device '{target.name}' only supports memory presets 1-{slot_count}. "
                            f"Preset {preset} is not available for this bed type.",
                            translation_domain=DOMAIN,
                            translation_key="invalid_preset_number",
                            translation_placeholders={
                                "device_name": target.name,
                                "max_preset": str(slot_count),
                                "requested_preset": str(preset),
                            },
                        )
        except ServiceValidationError:
            await _release_preflighted(preflighted)
            raise

        # Phase 2: every target validated - now program them. Release any
        # still-connected preflighted bed that never ran if one fails.
        try:
            for coordinator, side in targets:
                await _execute_sided(
                    coordinator,
                    side,
                    lambda ctrl, p=preset: ctrl.program_memory(p),  # type: ignore[misc]
                    cancel_running=False,
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

    targets, missing_device_ids = _resolve_sided_targets(hass, device_ids, explicit_side)

    async def _stop_one(coordinator: BedTarget, side: str) -> None:
        # Validate that side applies (rejects left/right on a single bed).
        _command_targets(coordinator, side)
        if isinstance(coordinator, PairedBedCoordinator):
            await coordinator.async_stop_command(side=side)
        else:
            await coordinator.async_stop_command()

    # STOP is a safety action: attempt every target before surfacing an
    # error, so one bed's failure never leaves another still moving.
    results = await asyncio.gather(
        *(_stop_one(coordinator, side) for coordinator, side in targets),
        return_exceptions=True,
    )
    stop_errors = [r for r in results if isinstance(r, BaseException)]

    if missing_device_ids:
        raise ServiceValidationError(
            f"Could not find Adjustable Bed device(s) with ID(s): {', '.join(missing_device_ids)}",
            translation_domain=DOMAIN,
            translation_key="devices_not_found",
            translation_placeholders={"device_ids": ", ".join(missing_device_ids)},
        )

    if stop_errors:
        # Every target was attempted; surface the first failure.
        raise stop_errors[0]


async def _set_position_plan(
    parent: BedTarget,
    coordinator: BedChild,
    preflighted: PreflightedSides,
    motor: str,
    position: float,
) -> dict[str, Any]:
    """Validate one physical side and return its seek configuration."""
    async with _release_idle_on_validation_failure(coordinator):
        controller = await _validation_controller(parent, coordinator, preflighted)

        # Bed type / motor count come from the coordinator's own entry (the
        # child's ChildEntryView for a paired-side target - children aren't in
        # hass.data, so don't scan it).
        entry = coordinator.entry
        bed_type = entry.data.get(CONF_BED_TYPE)
        motor_count = entry.data.get(CONF_MOTOR_COUNT, DEFAULT_MOTOR_COUNT)
        protocol_variant = entry.data.get(CONF_PROTOCOL_VARIANT)
        supports_direct_position_control = controller.supports_direct_position_control

        # Validate bed supports position feedback
        if (
            not bed_type_has_position_feedback(bed_type, protocol_variant)
            and not supports_direct_position_control
        ):
            raise ServiceValidationError(
                f"Device '{coordinator.name}' (type: {bed_type}) does not support position feedback",
                translation_domain=DOMAIN,
                translation_key="position_feedback_not_supported",
                translation_placeholders={
                    "device_name": coordinator.name,
                    "bed_type": bed_type or "unknown",
                },
            )

        # Validate angle sensing is enabled
        if coordinator.disable_angle_sensing:
            raise ServiceValidationError(
                f"Angle sensing is disabled for device '{coordinator.name}'",
                translation_domain=DOMAIN,
                translation_key="angle_sensing_disabled",
                translation_placeholders={"device_name": coordinator.name},
            )

        # Define motor configurations.
        # For Keeson/Ergomotion: only head and feet are valid, they map to back/legs keys.
        # For BOX25: head, feet, and lumbar are valid, using direct percentage positions.
        # For Kaidi: direct position writes expose back/legs percentage targets.
        # For standard beds: based on motor_count (2=back/legs, 3=+head, 4=+feet).
        uses_percentage_positions = bed_type in (
            BED_TYPE_KEESON,
            BED_TYPE_ERGOMOTION,
            BED_TYPE_SLEEPYS_BOX25,
            BED_TYPE_SVANE,
            BED_TYPE_SLEEP_NUMBER_MCR,
        ) or (bed_type == BED_TYPE_KAIDI and supports_direct_position_control) or (
            controller.reports_percentage_position is True
        )

        if bed_type in (BED_TYPE_SLEEP_NUMBER_MCR, BED_TYPE_SERTA_MP_REMOTE):
            # These direct setters own native bounds independently of generic
            # angle overrides. Validate every axis/target before scheduling.
            motor_configs = {
                spec.position_key: {
                    "position_key": spec.position_key,
                    "move_up_fn": spec.open_fn,
                    "move_down_fn": spec.close_fn,
                    "move_stop_fn": spec.stop_fn,
                    "max_value": spec.native_max_value,
                }
                for spec in controller.position_number_specs
            }
            valid_motors = set(motor_configs)
        elif bed_type == BED_TYPE_KAIDI and supports_direct_position_control:
            valid_motors = {"back", "legs"}
            motor_configs = {
                "back": {
                    "position_key": "back",
                    "move_up_fn": lambda ctrl: ctrl.move_back_up(),
                    "move_down_fn": lambda ctrl: ctrl.move_back_down(),
                    "move_stop_fn": lambda ctrl: ctrl.move_back_stop(),
                    "max_value": 100.0,
                },
                "legs": {
                    "position_key": "legs",
                    "move_up_fn": lambda ctrl: ctrl.move_legs_up(),
                    "move_down_fn": lambda ctrl: ctrl.move_legs_down(),
                    "move_stop_fn": lambda ctrl: ctrl.move_legs_stop(),
                    "max_value": 100.0,
                },
            }
        elif supports_direct_position_control and controller.reports_percentage_position is True:
            motor_configs = {
                spec.position_key: {
                    "position_key": spec.position_key,
                    "move_up_fn": spec.open_fn,
                    "move_down_fn": spec.close_fn,
                    "move_stop_fn": spec.stop_fn,
                    "max_value": spec.native_max_value,
                }
                for spec in controller.position_number_specs
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
        elif bed_type == BED_TYPE_SLEEPYS_BOX25:
            valid_motors = {"head", "feet", "lumbar"}
            motor_configs = {
                "head": {
                    "position_key": "head",
                    "move_up_fn": lambda ctrl: ctrl.move_head_up(),
                    "move_down_fn": lambda ctrl: ctrl.move_head_down(),
                    "move_stop_fn": lambda ctrl: ctrl.move_head_stop(),
                    "max_value": 100.0,
                },
                "feet": {
                    "position_key": "feet",
                    "move_up_fn": lambda ctrl: ctrl.move_feet_up(),
                    "move_down_fn": lambda ctrl: ctrl.move_feet_down(),
                    "move_stop_fn": lambda ctrl: ctrl.move_feet_stop(),
                    "max_value": 100.0,
                },
                "lumbar": {
                    "position_key": "lumbar",
                    "move_up_fn": lambda ctrl: ctrl.move_lumbar_up(),
                    "move_down_fn": lambda ctrl: ctrl.move_lumbar_down(),
                    "move_stop_fn": lambda ctrl: ctrl.move_lumbar_stop(),
                    "max_value": 100.0,
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
            raise ServiceValidationError(
                f"Motor '{motor}' is not valid for device '{coordinator.name}'. "
                f"Valid motors: {', '.join(sorted(valid_motors))}",
                translation_domain=DOMAIN,
                translation_key="invalid_motor_for_bed_type",
                translation_placeholders={
                    "motor": motor,
                    "device_name": coordinator.name,
                    "valid_motors": ", ".join(sorted(valid_motors)),
                },
            )

        config = motor_configs[motor]
        max_value = config["max_value"]

        # Validate position is in range
        if position < 0 or position > max_value:
            unit = "%" if uses_percentage_positions else "°"
            raise ServiceValidationError(
                f"Position {position} is out of range for motor '{motor}'. "
                f"Valid range: 0-{max_value}{unit}",
                translation_domain=DOMAIN,
                translation_key="invalid_position_range",
                translation_placeholders={
                    "position": str(position),
                    "motor": motor,
                    "max_value": str(max_value),
                    "unit": unit,
                },
            )

        return config


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
        raise ServiceValidationError(
            "Each motor may appear only once in a set_positions call",
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

    async def seek(target: BedChild, motor: str, position: float) -> None:
        config = plans[(_plan_key(target), motor)]
        await target.async_seek_position(
            position_key=cast(str, config["position_key"]),
            target_angle=position,
            move_up_fn=config["move_up_fn"],  # type: ignore[arg-type]
            move_down_fn=config["move_down_fn"],  # type: ignore[arg-type]
            move_stop_fn=config["move_stop_fn"],  # type: ignore[arg-type]
        )

    async def seek_all(target: BedChild) -> None:
        operations: list[Callable[[], Coroutine[Any, Any, None]]] = []
        for motor, position in requests:

            async def operation(
                motor: str = motor,
                position: float = position,
            ) -> None:
                await seek(target, motor, position)

            operations.append(operation)

        await target.async_execute_command_group(
            operations,
            resources=tuple(
                f"motor:{plans[(_plan_key(target), motor)]['position_key']}"
                for motor, _ in requests
            ),
        )

    try:
        for coordinator, side in targets:
            if isinstance(coordinator, PairedBedCoordinator):
                resources = {
                    f"motor:{plans[(_plan_key(target), motor)]['position_key']}"
                    for target in _command_targets(coordinator, side)
                    for motor, _ in requests
                }
                await coordinator.async_run_child_operation(
                    "set positions",
                    seek_all,
                    side=side,
                    resources=resources,
                )
            else:
                await seek_all(coordinator)
    except Exception:
        await _release_preflighted(preflighted)
        raise


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
) -> tuple[Callable[[BedController], Coroutine[Any, Any, None]], int, int, str]:
    """Validate one physical side and build its timed command."""
    async with _release_idle_on_validation_failure(coordinator):
        controller = await _validation_controller(parent, coordinator, preflighted)
        if hold_lease:
            _require_hold_execution(coordinator, controller)
            duration_ms = _hold_ceiling(controller, duration_ms)

        motor_specs = {
            spec.key: spec
            for spec in controller.motor_control_specs
            if spec.key in TIMED_MOVE_MOTOR_OPTIONS
        }
        valid_motors = set(motor_specs)

        # Validate motor is valid for this bed
        if motor not in valid_motors:
            raise ServiceValidationError(
                f"Motor '{motor}' is not valid for device '{coordinator.name}'. "
                f"Valid motors: {', '.join(sorted(valid_motors))}",
                translation_domain=DOMAIN,
                translation_key="invalid_motor_for_bed_type",
                translation_placeholders={
                    "motor": motor,
                    "device_name": coordinator.name,
                    "valid_motors": ", ".join(sorted(valid_motors)),
                },
            )

        spec = motor_specs[motor]
        try:
            controller.validate_timed_movement(motor, direction, duration_ms)
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err

        from .beds.svane import SvaneController
        from .svane_services import _preflight_live_svane

        if coordinator.bed_type == BED_TYPE_SVANE and isinstance(controller, SvaneController):
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
                raise ServiceValidationError(str(err)) from err

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
                raise ServiceValidationError(
                    f"Motor '{motor}' declares unsupported held control '{hold_control}'"
                )
            try:
                controller.validate_hold_control(hold_control, duration_ms)
            except ValueError as err:
                raise ServiceValidationError(str(err)) from err

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
            spec.scheduler_resource or f"motor:{spec.position_key or spec.key}",
        )


def _hold_lease(call: ServiceCall, action: str, duration_ms: int) -> HoldLease | None:
    """Return the call's renewable hold lease, or None for a finite move."""
    owner = call.data.get(ATTR_HOLD_OWNER)
    if owner is None:
        return None
    if not MIN_HOLD_LEASE_MS <= duration_ms <= MAX_HOLD_LEASE_MS:
        raise ServiceValidationError(
            f"A renewable hold lasts {MIN_HOLD_LEASE_MS} to {MAX_HOLD_LEASE_MS} ms per call"
        )
    return HoldLease(
        owner=owner,
        generation=call.data[ATTR_HOLD_GENERATION],
        action=action,
        duration_s=duration_ms / 1000,
    )


def _hold_ceiling(controller: BedController | SideBoundController, duration_ms: int) -> int:
    """Bound a renewable hold by its mode's ceiling: latched beds move until STOP."""
    return min(duration_ms, controller.execution.hold_ceiling_ms or duration_ms)


def _require_hold_execution(
    target: BedChild, controller: BedController | SideBoundController
) -> None:
    """Allow a lease only on a controller that declares an open-ended hold."""
    if controller.execution.hold is None:
        raise ServiceValidationError(
            f"Device '{target.name}' does not support renewable holds"
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
        raise ServiceValidationError("A renewable hold targets one bed at a time")
    coordinator, side = targets[0]
    # Key every claim by the target that executes the command: a native
    # single-address Both runs once on its combined side view.
    executing = (
        list({id(child): child for _, child in coordinator._targets_for(side)}.values())
        if isinstance(coordinator, PairedBedCoordinator)
        else _command_targets(coordinator, side)
    )
    physical = [(target, resource_for(target)) for target in executing]
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
        raise ServiceValidationError(
            f"Hold generation {lease.generation} has ended; start a new generation"
        )
    modes = {
        controller.execution.hold
        for target, _resource in physical
        if (controller := target.capability_controller) is not None
    }
    if len(modes) > 1:
        raise ServiceValidationError("Both sides must declare the same hold mode")
    for target, resource in physical:
        target.claim_hold_lease(lease, resource=resource)
    try:
        await start()
    except StaleHoldLease as err:
        raise ServiceValidationError(str(err)) from err
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

    from .beds.svane import SvaneController

    svane_admissions = {
        _plan_key(target): controller.prepare_svane_hold_admission()
        for parent, side in targets
        for target in _command_targets(parent, side)
        if target.bed_type == BED_TYPE_SVANE
        and isinstance(controller := target.capability_controller, SvaneController)
    }
    preflighted: PreflightedSides = []
    plans: dict[
        int,
        tuple[Callable[[BedController], Coroutine[Any, Any, None]], int, int, str],
    ] = {}
    stop_epoch_by_target: dict[int, int] = {}
    try:
        for coordinator, side in targets:
            for target in _command_targets(coordinator, side):
                target_key = _plan_key(target)
                command_admission = command_admissions[(id(coordinator), side)]
                if isinstance(coordinator, PairedBedCoordinator):
                    target_side = next(
                        target_side
                        for target_side, child in coordinator._targets_for(side)
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
                )
            admission = command_admissions[(id(coordinator), side)]
            actual_resources = {
                plans[_plan_key(target)][3]
                for target in _command_targets(coordinator, side)
            }
            if actual_resources != set(admission.resources):
                raise ServiceValidationError(
                    "The selected motor resource changed during timed-move preflight"
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

    async def move(target: BedChild) -> None:
        command, pulse_count, pulse_delay_ms, resource = plans[_plan_key(target)]
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
            return
        await target.async_execute_controller_command(
            command,
            resource=resource,
            pulse_count=pulse_count,
            pulse_delay_ms=pulse_delay_ms,
            expected_stop_epoch=stop_epoch_by_target.get(_plan_key(target)),
        )

    try:
        for coordinator, side in targets:
            if isinstance(coordinator, PairedBedCoordinator):
                resources = {
                    plans[_plan_key(target)][3] for target in _command_targets(coordinator, side)
                }
                admission = command_admissions[(id(coordinator), side)]
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
    check: Callable[[BedChild, BedController | SideBoundController], None],
) -> PreflightedSides:
    """Check every physical target before any write.

    A ``ValueError`` from ``check`` becomes a ``ServiceValidationError``; any
    failure releases the sides connected only for validation.
    """
    preflighted: PreflightedSides = []
    try:
        for coordinator, side in targets:
            for target in _command_targets(coordinator, side):
                check(target, await _validation_controller(coordinator, target, preflighted))
    except asyncio.CancelledError:
        await _release_preflighted(preflighted)
        raise
    except (ServiceValidationError, ValueError) as err:
        await _release_preflighted(preflighted)
        if isinstance(err, ValueError):
            raise ServiceValidationError(str(err)) from err
        raise
    return preflighted


async def _preflight_capability(
    targets: list[tuple[BedTarget, str]],
    capability: str,
    label: str,
    validate: Callable[[BedController | SideBoundController], None] | None = None,
) -> PreflightedSides:
    """Validate a capability on every physical target before any write."""

    def check(target: BedChild, controller: BedController | SideBoundController) -> None:
        if not getattr(controller, capability, False):
            raise ServiceValidationError(f"Device '{target.name}' does not support {label}")
        if validate is not None:
            validate(controller)

    return await _preflight_each(targets, check)


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
        raise ServiceValidationError(
            f"These beds use different app profiles; call {action} separately for each",
            translation_domain=DOMAIN,
            translation_key="mixed_profile_targets",
            translation_placeholders={"action": action},
        )
    return next(iter(selected), None)


async def handle_rename(call: ServiceCall) -> None:
    """Write a new Bluetooth name to every targeted controller that supports it."""
    from .furnimove_services import _rename_furnimove
    from .vmatbasic_services import _rename_vmatbasic

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
        await _rename_vmatbasic(targets, name)
        return

    disconnect: set[int] = set()

    def check(target: BedChild, controller: BedController | SideBoundController) -> None:
        if not controller.supports_device_rename:
            raise ServiceValidationError(
                f"Device '{target.name}' does not support Bluetooth rename",
                translation_domain=DOMAIN,
                translation_key="device_rename_not_supported",
                translation_placeholders={"device_name": target.name},
            )
        # Each app has its own name rule; reject before any target writes.
        controller.validate_device_rename(name)
        if controller.disconnects_after_rename:
            disconnect.add(id(target))

    preflighted = await _preflight_each(targets, check)

    async def rename(controller: BedController | SideBoundController) -> None:
        await controller.rename_device(name)

    try:
        for coordinator, side in targets:
            await _execute_sided(
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
    from .limoss_remote_services import _hold_limoss_remote
    from .svane_services import _hold_svane
    from .vmatbasic_services import _hold_vmatbasic_floor

    control = call.data[ATTR_CONTROL]
    duration_ms = int(call.data[ATTR_DURATION] * 1000)
    targets = _call_targets(call)
    route = _profile_route(
        targets,
        {BED_TYPE_SVANE: "svane", BED_TYPE_LIMOSS_REMOTE: "limoss_remote"},
        SERVICE_HOLD_CONTROL,
    )
    lease = _hold_lease(call, control, duration_ms)
    if lease is not None:
        if route == "svane" or control == "floor_hold":
            raise ServiceValidationError("This control does not support renewable holds")
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
            else lambda: _hold_targets(targets, control, MAX_HOLD_LEASE_MS, lease=held),
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
        await _hold_vmatbasic_floor(targets, control, duration_ms)
    else:
        await _hold_targets(targets, control, duration_ms)


def _require_held_control(
    target: BedChild, controller: BedController | SideBoundController, control: str
) -> None:
    """Reject a control the target's controller does not declare, listing valid ones."""
    options = controller.held_control_options
    if not options:
        raise ServiceValidationError(
            f"Device '{target.name}' has no held controls",
            translation_domain=DOMAIN,
            translation_key="held_controls_not_supported",
            translation_placeholders={"device_name": target.name},
        )
    if control not in options:
        raise ServiceValidationError(
            f"Device '{target.name}' does not support held control '{control}'. "
            f"Valid controls: {', '.join(options)}",
            translation_domain=DOMAIN,
            translation_key="held_control_not_supported",
            translation_placeholders={
                "device_name": target.name,
                "control": control,
                "valid_controls": ", ".join(options),
            },
        )


@dataclass(frozen=True, slots=True)
class _HoldAdmission:
    """Cancellation state captured before hold capability preflight awaits."""

    stop_epoch: int | None = None
    pair_generations: Mapping[str, tuple[int, ...]] | None = None
    stop_epochs: Mapping[str, int] | None = None


def _target_stop_epoch(target: BedChild) -> int | None:
    """Read the owning physical scheduler's STOP epoch for one service target."""
    owner = getattr(target, "_single_inner", target)
    scheduler = getattr(owner, "_command_scheduler", None)
    epoch = getattr(scheduler, "stop_epoch", None)
    return epoch if isinstance(epoch, int) else None


def _hold_admission(coordinator: BedTarget, side: str) -> _HoldAdmission:
    """Snapshot STOP ownership before a hold's possibly blocking preflight."""
    if not isinstance(coordinator, PairedBedCoordinator):
        return _HoldAdmission(stop_epoch=_target_stop_epoch(coordinator))

    pair_generations: dict[str, tuple[int, ...]] = {}
    stop_epochs: dict[str, int] = {}
    for target_side, target in coordinator._targets_for(side):
        pair_generations[target_side] = coordinator._pair_cancel_generation(
            target_side, ALL_COMMAND_RESOURCES
        )
        stop_epoch = _target_stop_epoch(target)
        if stop_epoch is not None:
            stop_epochs[target_side] = stop_epoch
    return _HoldAdmission(
        pair_generations=pair_generations,
        stop_epochs=stop_epochs or None,
    )


async def _hold_targets(
    targets: list[tuple[BedTarget, str]],
    control: str,
    duration_ms: int,
    *,
    lease: HoldLease | None = None,
) -> None:
    """Preflight the whole selection before starting any held write sequence."""

    # A STOP during any per-side capability/connect wait owns the event that
    # was current when the user pressed. Capture before _preflight_each awaits.
    admissions = [
        (coordinator, side, _capture_command_admission(coordinator, side))
        for coordinator, side in targets
    ]

    def check(target: BedChild, controller: BedController | SideBoundController) -> None:
        _require_held_control(target, controller, control)
        if lease is not None:
            _require_hold_execution(target, controller)
        controller.validate_hold_control(control, duration_ms)

    admissions = [_hold_admission(coordinator, side) for coordinator, side in targets]
    preflighted = await _preflight_each(targets, check)

    async def hold(controller: BedController | SideBoundController) -> None:
        await controller.hold_control(
            control, duration_ms if lease is None else _hold_ceiling(controller, duration_ms)
        )

    try:
        for (coordinator, side), admission in zip(targets, admissions, strict=True):
            await _execute_sided(
                coordinator,
                side,
                track_held_control(getattr(coordinator, "hass", None), control, hold),
                cancel_running=True,
                expected_stop_epoch=admission.stop_epoch,
                expected_pair_generations=admission.pair_generations,
                expected_stop_epochs=admission.stop_epochs,
                lease=lease,
            )
    except (Exception, asyncio.CancelledError):
        await _release_preflighted(preflighted)
        raise
    else:
        # A stale scheduler admission is a normal no-op after STOP, so restore
        # the idle deadline on links opened during preflight on either path.
        await _release_preflighted(preflighted)


async def handle_configure_alarm_schedule(call: ServiceCall) -> None:
    """Preflight both tables on all physical targets before encoding or writing."""
    schedule = AlarmTableSchedule(
        weekly=tuple(WeeklyAlarmRecord(**{**row, "weekdays": tuple(row["weekdays"])}) for row in call.data["weekly"]),
        one_time=tuple(OneTimeAlarmRecord(**row) for row in call.data["one_time"]),
        dispatch=call.data["dispatch"],
        reference_time=dt_util.now(),
    )
    targets = _call_targets(call)
    # A table call cannot connect merely to discover whether it is valid:
    # initialization can write clock/zero/query frames. These static profiles
    # are offline-mintable, and all other controllers lack this contract.
    for coordinator, side in targets:
        for target in _command_targets(coordinator, side):
            controller = target.capability_controller
            if controller is None or controller.alarm_table_schedule_spec is None:
                raise ServiceValidationError(f"Device '{target.name}' has no available alarm-table contract")

    def check(target: BedChild, controller: BedController | SideBoundController) -> None:
        spec = controller.alarm_table_schedule_spec
        if spec is None:
            raise ServiceValidationError(f"Device '{target.name}' has no alarm-table contract")
        spec.validate(schedule)

    preflighted = await _preflight_each(targets, check)

    async def configure(controller: BedController) -> None:
        await controller.configure_alarm_table_schedule(schedule)

    try:
        for coordinator, side in targets:
            await _execute_sided(coordinator, side, configure, cancel_running=False, resource="configuration")
    except BaseException:
        await _release_preflighted(preflighted)
        raise


async def handle_sync_clock(call: ServiceCall) -> None:
    """Synchronize each targeted device clock to Home Assistant's local time."""
    from .serenity_services import _execute_zseries_alarm

    targets = _call_targets(call)

    async def sync(controller: BedController | SideBoundController) -> None:
        await controller.sync_clock()

    if _profile_route(targets, {BED_TYPE_ZSERIES: "zseries"}, SERVICE_SYNC_CLOCK):
        # Z-Series clocks live on the alarm page, gated by a live manufacturer read.
        await _execute_zseries_alarm(call, "Z-Series clock synchronization", sync)
        return

    def check(target: BedChild, controller: BedController | SideBoundController) -> None:
        if not controller.supports_clock_sync:
            raise ServiceValidationError(
                f"Device '{target.name}' does not support clock synchronization",
                translation_domain=DOMAIN,
                translation_key="clock_sync_not_supported",
                translation_placeholders={"device_name": target.name},
            )

    preflighted = await _preflight_each(targets, check)
    try:
        for coordinator, side in targets:
            await _execute_sided(
                coordinator, side, sync, cancel_running=False, resource="configuration"
            )
    except Exception, asyncio.CancelledError:
        await _release_preflighted(preflighted)
        raise


async def handle_generate_support_bundle(call: ServiceCall) -> None:
    """Handle generate_support_bundle service call."""
    hass = call.hass
    from homeassistant.components.persistent_notification import (
        async_create,
        async_dismiss,
    )

    from .download import register_download
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
            raise ServiceValidationError(
                f"Invalid MAC address format: {target_address}. "
                "Please provide a valid MAC address in the format "
                "XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX.",
                translation_domain=DOMAIN,
                translation_key="invalid_mac_address",
            )
        _LOGGER.info(
            "Generating support bundle for unconfigured device at %s",
            address,
        )
    elif device_ids:
        if len(device_ids) > 1:
            raise ServiceValidationError(
                "Support bundle generation only supports one configured device at a time. "
                "Select a single device or use target_address for an unconfigured bed.",
                translation_domain=DOMAIN,
                translation_key="multiple_device_targets_not_supported",
            )
        # str() narrows the untyped service-call value for the str-typed parameter
        selected_device_id = str(device_ids[0])
        target = _get_support_bundle_target_from_device(hass, selected_device_id)
        if target is not None:
            address, coordinator, entry = target
            device_name = coordinator.name if coordinator is not None else entry.title
            _LOGGER.info(
                "Generating support bundle for configured device %s at %s",
                device_name,
                address,
            )
        else:
            raise ServiceValidationError(
                f"Could not find Adjustable Bed device with ID: {selected_device_id}. "
                "Please verify the device is configured and try again.",
                translation_domain=DOMAIN,
                translation_key="device_not_found",
            )
    else:
        raise ServiceValidationError(
            "No device_id or target_address was provided. "
            "Please specify either a configured device or a target MAC address.",
            translation_domain=DOMAIN,
            translation_key="missing_target",
        )

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
                    + "\n\nThe capture is running anyway, so you will still get a "
                    "bundle with Bluetooth diagnostics.",
                    title="Adjustable Bed: this bundle will have no logs",
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
            warning_summary = "\n\n**Capture warnings:**\n" + "\n".join(
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
            f"[**Download support bundle**]({download_url})\n\n"
            "The download link expires in one hour or when Home Assistant restarts. "
            "The saved file remains available at the path below.\n\n"
            f"Captured {notification_count} notifications. "
            f"Requested capture window: {capture_duration} seconds."
            f"{logging_notice}"
            f"{warning_summary}\n\n"
            "Attach this JSON file when reporting unsupported or broken beds.\n\n"
            f"File path: `{filepath}`",
            title="Adjustable Bed Support Bundle Ready",
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
            f"Support bundle generation timed out after {capture_duration + 120} seconds "
            f"for {address}.\n\n"
            "The BLE diagnostics may be hanging. Check Bluetooth connectivity and try again.",
            title="Adjustable Bed Support Bundle Timeout",
            notification_id=f"adjustable_bed_support_bundle_error_{address.replace(':', '_').lower()}",
        )
        raise
    except Exception as err:
        _LOGGER.exception("Failed to generate support bundle for %s", address)
        async_create(
            hass,
            f"Failed to generate support bundle for {address}:\n\n{err}",
            title="Adjustable Bed Support Bundle Error",
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


async def async_register_services(hass: HomeAssistant) -> None:
    """Register the Adjustable Bed services (idempotent)."""
    from .support_logs import async_setup_support_logs

    async_setup_support_logs(hass)
    if hass.services.has_service(DOMAIN, SERVICE_GOTO_PRESET):
        return  # Services already registered

    from .bf_cherish_services import register_services as register_bf_cherish_services
    from .casper_base_services import async_register_casper_base_services
    from .comfort_enhancements_services import async_register_comfort_enhancements_services
    from .customatic_services import async_register_customatic_services
    from .doublesleep_services import async_register_doublesleep_services
    from .eshine_okin_services import async_register_eshine_okin_services
    from .floyd_services import async_register_floyd_services
    from .fsm_relax_services import async_register_fsm_relax_services
    from .furnimove_services import async_register_furnimove_services
    from .glideaway_motion_services import async_register_glideaway_motion_services
    from .gmmotor_services import async_register_gmmotor_services
    from .goodvibe_services import async_register_goodvibe_services
    from .hjbed_services import async_register_hjbed_services
    from .jiecang_app_services import async_register_jiecang_app_services
    from .leggett_okin_services import async_register_leggett_okin_services
    from .limoss_remote_services import async_register_limoss_remote_services
    from .linak_services import async_register_linak_services
    from .logicdata_app_services import async_register_logicdata_app_services
    from .malouf_app_services import async_register_malouf_app_services
    from .motion_bed_services import async_register_motion_bed_services
    from .octo_services import async_register_octo_services
    from .position_estimate_services import async_register_position_estimate_services
    from .reverie_services import async_register_reverie_services
    from .richmat_mh_services import async_register_richmat_mh_services
    from .rmcontrol_services import async_register_rmcontrol_services
    from .serenity_services import async_register_serenity_services
    from .simmons_services import async_register_simmons_services
    from .sleep_number_services import async_register_sleep_number_services
    from .sleeptracker_services import async_register_sleeptracker_services
    from .solace_services import async_register_solace_services
    from .svane_services import async_register_svane_services

    register_bf_cherish_services(hass)
    async_register_motion_bed_services(hass)
    async_register_casper_base_services(hass)
    async_register_gmmotor_services(hass)
    async_register_richmat_mh_services(hass)
    async_register_position_estimate_services(hass)
    async_register_hjbed_services(hass)
    async_register_goodvibe_services(hass)
    async_register_rmcontrol_services(hass)
    async_register_sleep_number_services(hass)
    async_register_doublesleep_services(hass)
    async_register_sleeptracker_services(hass)
    async_register_reverie_services(hass)
    async_register_linak_services(hass)
    async_register_solace_services(hass)
    async_register_leggett_okin_services(hass)
    async_register_floyd_services(hass)
    async_register_octo_services(hass)
    async_register_customatic_services(hass)
    async_register_furnimove_services(hass)
    async_register_fsm_relax_services(hass)
    async_register_limoss_remote_services(hass)
    async_register_serenity_services(hass)
    async_register_eshine_okin_services(hass)
    async_register_glideaway_motion_services(hass)
    async_register_simmons_services(hass)
    async_register_comfort_enhancements_services(hass)
    async_register_malouf_app_services(hass)
    async_register_logicdata_app_services(hass)
    async_register_jiecang_app_services(hass)
    async_register_svane_services(hass)

    from .starcode_accessory_group import register_group_services

    register_group_services(hass)
    hass.services.async_register(
        DOMAIN,
        SERVICE_GOTO_PRESET,
        handle_goto_preset,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                vol.Required(ATTR_PRESET): vol.All(vol.Coerce(int), vol.Range(min=1)),
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
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                vol.Required(ATTR_PRESET): vol.All(vol.Coerce(int), vol.Range(min=1)),
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
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
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
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
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
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
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
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
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
                vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
                # Each target's controller applies its app's own name rule.
                vol.Required(ATTR_NAME): cv.string,
                **SIDE_FIELD,
            }
        ),
    )
    # Released per-app rename actions keep their original schemas.
    for service, devices, name_rule in (
        (SERVICE_LINAK_RENAME, cv.ensure_list, vol.Length(min=1, max=17)),
        (
            SERVICE_LOGICDATA_RENAME,
            vol.All(cv.ensure_list, vol.Length(min=1)),
            vol.Match(r"\A[\x20-\x7eäöüÄÖÜß]{1,255}\Z"),
        ),
        (
            SERVICE_JIECANG_RENAME,
            vol.All(cv.ensure_list, vol.Length(min=1)),
            vol.Match(r"\A[A-Za-z0-9]{1,20}\Z"),
        ),
    ):
        hass.services.async_register(
            DOMAIN,
            service,
            handle_rename,
            schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): devices,
                    vol.Required(ATTR_NAME): vol.All(cv.string, name_rule),
                    **SIDE_FIELD,
                }
            ),
        )
    hold_fields = {
        vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
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
        SERVICE_LEGGETT_HOLD_CONTROL,
        handle_hold_control,
        schema=vol.Schema(
            {**hold_fields, vol.Required(ATTR_CONTROL): vol.In(LEGGETT_HELD_CONTROLS)}
        ),
    )
    alarm_fields = {
        vol.Optional("enabled", default=False): cv.boolean,
        vol.Optional("wake", default=False): cv.boolean,
        vol.Optional("hour", default=0): vol.All(int, vol.Range(min=0, max=23)),
        vol.Optional("minute", default=0): vol.All(int, vol.Range(min=0, max=59)),
    }
    hass.services.async_register(
        DOMAIN,
        SERVICE_CONFIGURE_ALARM_SCHEDULE,
        handle_configure_alarm_schedule,
        schema=vol.Schema({
            vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
            vol.Required("weekly"): [vol.Schema({**alarm_fields, vol.Optional("weekdays", default=[]): [vol.All(int, vol.Range(min=0, max=6))]})],
            vol.Required("one_time"): [vol.Schema(alarm_fields)],
            vol.Required("dispatch"): vol.In(("both", "weekly", "one_time")),
            **SIDE_FIELD,
        }),
    )
    for service in (SERVICE_SYNC_CLOCK, SERVICE_MALOUF_SYNC_CLOCK):
        hass.services.async_register(
            DOMAIN,
            service,
            handle_sync_clock,
            schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): vol.All(cv.ensure_list, vol.Length(min=1)),
                    **SIDE_FIELD,
                }
            ),
        )
    hass.services.async_register(
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
