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
from collections.abc import AsyncIterator, Callable, Collection, Coroutine
from typing import TYPE_CHECKING, Any, cast

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .beds.linak_protocol import LinakAlarmAction, LinakAlarmStep
from .const import (
    BED_TYPE_ERGOMOTION,
    BED_TYPE_KAIDI,
    BED_TYPE_KEESON,
    BED_TYPE_LINAK,
    BED_TYPE_SLEEPYS_BOX25,
    CONF_BED_TYPE,
    CONF_MOTOR_COUNT,
    CONF_PROTOCOL_VARIANT,
    DEFAULT_MOTOR_COUNT,
    DOMAIN,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
    bed_type_has_position_feedback,
)
from .coordinator import AdjustableBedCoordinator
from .paired_coordinator import PairedBedCoordinator, SingleAddressPairedCoordinator
from .pairing import is_paired, pair_member_addresses

if TYPE_CHECKING:
    from .beds.base import BedController

_LOGGER = logging.getLogger(__name__)

# A service target: a single bed's coordinator, or a paired bed's parent.
BedTarget = AdjustableBedCoordinator | PairedBedCoordinator
# (target, physical side) pairs connected purely to validate a call, so a failed
# pre-flight can hand them back their idle timer.
PreflightedSides = list[tuple[BedTarget, AdjustableBedCoordinator]]


# Service names
SERVICE_GOTO_PRESET = "goto_preset"
SERVICE_GENERATE_SUPPORT_BUNDLE = "generate_support_bundle"
SERVICE_SAVE_PRESET = "save_preset"
SERVICE_SET_POSITION = "set_position"
SERVICE_SET_POSITIONS = "set_positions"
SERVICE_STOP_ALL = "stop_all"
SERVICE_TIMED_MOVE = "timed_move"
SERVICE_LINAK_MOVE_SIMULTANEOUS = "linak_move_simultaneously"
SERVICE_LINAK_RENAME = "linak_rename"
SERVICE_LINAK_SET_ALARM = "linak_set_alarm"
SERVICE_SOLACE_AUDIO = "solace_audio"
SERVICE_SOLACE_SET_ALARM = "solace_set_alarm"

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

LINAK_MOTOR_OPTIONS = ("base", "feet", "head", "legs", "back")
LINAK_DIRECTION_OPTIONS = ("up", "down")
LINAK_ALARM_ACTION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ACTION): vol.In(tuple(action.value for action in LinakAlarmAction)),
        vol.Optional(ATTR_LIFETIME, default=1): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
        vol.Optional(ATTR_PAUSE, default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
    }
)

SOLACE_AUDIO_ACTIONS = ("select", "preview", "query", "set_volume")
SOLACE_WEEKDAY_OPTIONS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
SOLACE_ALARM_MODES = ("zero_g", "memory_1", "no_action")
SOLACE_ALARM_SOUNDS = (
    "none",
    "alarm",
    "music_1",
    "music_2",
    "music_3",
    "music_4",
    "music_5",
)

TIMED_MOVE_MOTOR_OPTIONS = (
    "tv_lift",
    "back",
    "legs",
    "head",
    "feet",
    "tilt",
    "pillow",
    "lumbar",
    "bed_height",
    "stair",
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
    device_registry = dr.async_get(hass)
    device = device_registry.async_get(device_id)
    if not device:
        return None
    coordinator: BedTarget | None = None
    for entry_id in device.config_entries:
        if entry_id in hass.data.get(DOMAIN, {}):
            coordinator = hass.data[DOMAIN][entry_id]
            break
    if coordinator is None:
        return None
    inferred_side: str | None = None
    if isinstance(coordinator, PairedBedCoordinator) and not isinstance(
        coordinator, SingleAddressPairedCoordinator
    ):
        macs = {ident[1].upper() for ident in device.identifiers if ident[0] == DOMAIN}
        for side, child in coordinator.children.items():
            if child.address.upper() in macs:
                inferred_side = side
                break
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
) -> tuple[str, AdjustableBedCoordinator | None, ConfigEntry] | None:
    """Resolve support-bundle target details from a device registry ID."""
    device_registry = dr.async_get(hass)
    device = device_registry.async_get(device_id)
    if not device:
        return None

    for entry_id in device.config_entries:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            continue

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
                    f"{entry.title} is a paired bed; target one side's device "
                    "for the support bundle.",
                    translation_domain=DOMAIN,
                    translation_key="bundle_needs_side_for_paired",
                    translation_placeholders={"device_name": entry.title},
                )
        if not isinstance(address, str):
            continue

        coordinator: AdjustableBedCoordinator | None = None
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
            coordinator = cast("AdjustableBedCoordinator | None", stored)
        return address, coordinator, entry

    return None


async def _get_controller_for_service(
    coordinator: AdjustableBedCoordinator,
) -> BedController:
    """Return an active controller for service validation/execution.

    Service calls may arrive while the coordinator is idle-disconnected and
    controller is None. Reconnect first so capability checks don't fail with
    a false "not supported" error.
    """
    controller = coordinator.controller
    if controller is not None:
        return controller

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
    target: AdjustableBedCoordinator,
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
        return controller
    controller = await _get_controller_for_service(target)
    preflighted.append((coordinator, target))
    return controller


def _command_targets(coordinator: BedTarget, side: str) -> list[AdjustableBedCoordinator]:
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
) -> None:
    """Run a command on the targeted side(s).

    A paired bed fans out (with the both-failure stop-the-other contract); a
    single bed runs exactly as before.
    """
    if isinstance(coordinator, PairedBedCoordinator):
        await coordinator.async_execute_controller_command(
            command_fn,
            side=side,
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
    coordinator: AdjustableBedCoordinator,
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


def _plan_key(target: AdjustableBedCoordinator) -> int:
    """Stable per-side key for a validated plan (a proxy shares its child's identity)."""
    return getattr(target, "operation_identity", id(target))


async def handle_goto_preset(call: ServiceCall) -> None:
    """Handle goto_preset service call with sided all-target preflight."""
    hass = call.hass
    preset = call.data[ATTR_PRESET]
    device_ids = call.data.get(CONF_DEVICE_ID, [])
    explicit_side = call.data.get(ATTR_SIDE)

    _LOGGER.info("Service goto_preset called: preset=%d (side=%s)", preset, explicit_side)

    targets, missing = _resolve_sided_targets(hass, device_ids, explicit_side)
    if missing:
        raise _missing_device_error(missing[0])

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
    except ServiceValidationError:
        await _release_preflighted(preflighted)
        raise

    # Phase 2: every target validated - now move them. If one bed's command
    # fails, release the still-connected preflighted beds that never ran (and
    # so never reset their idle timer) before propagating.
    try:
        for coordinator, side in targets:
            await _execute_sided(
                coordinator,
                side,
                lambda ctrl, p=preset: ctrl.preset_memory(p),  # type: ignore[misc]
            )
    except Exception:
        await _release_preflighted(preflighted)
        raise


async def handle_save_preset(call: ServiceCall) -> None:
    """Handle save_preset service call with sided all-target preflight."""
    hass = call.hass
    preset = call.data[ATTR_PRESET]
    device_ids = call.data.get(CONF_DEVICE_ID, [])
    explicit_side = call.data.get(ATTR_SIDE)

    _LOGGER.info("Service save_preset called: preset=%d (side=%s)", preset, explicit_side)

    targets, missing = _resolve_sided_targets(hass, device_ids, explicit_side)
    if missing:
        raise _missing_device_error(missing[0])

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
    coordinator: AdjustableBedCoordinator,
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
        ) or (bed_type == BED_TYPE_KAIDI and supports_direct_position_control)

        if bed_type == BED_TYPE_KAIDI and supports_direct_position_control:
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
                valid_motors = {
                    spec.position_key for spec in controller.position_number_specs
                }
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

    async def seek(target: AdjustableBedCoordinator, motor: str, position: float) -> None:
        config = plans[(_plan_key(target), motor)]
        await target.async_seek_position(
            position_key=cast(str, config["position_key"]),
            target_angle=position,
            move_up_fn=config["move_up_fn"],  # type: ignore[arg-type]
            move_down_fn=config["move_down_fn"],  # type: ignore[arg-type]
            move_stop_fn=config["move_stop_fn"],  # type: ignore[arg-type]
        )

    async def seek_all(target: AdjustableBedCoordinator) -> None:
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
    coordinator: AdjustableBedCoordinator,
    preflighted: PreflightedSides,
    motor: str,
    direction: str,
    duration_ms: int,
) -> tuple[Callable[[BedController], Coroutine[Any, Any, None]], int, int, str]:
    """Validate one physical side and build its timed command."""
    async with _release_idle_on_validation_failure(coordinator):
        controller = await _validation_controller(parent, coordinator, preflighted)

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

        # Get the appropriate move function based on direction
        move_fn = spec.open_fn if direction == "up" else spec.close_fn
        stop_fn = spec.stop_fn

        # Execute timed movement
        # Calculate repeat count: duration_ms / pulse_delay_ms
        # Example: 3500ms on Octo (350ms delay) = 10 repeats
        _, pulse_delay_ms = controller.motor_pulse_settings()
        if pulse_delay_ms <= 0:
            _LOGGER.warning(
                "Invalid motor_pulse_delay_ms (%d) for device %s, using default 100ms",
                pulse_delay_ms,
                coordinator.name,
            )
            pulse_delay_ms = 100  # DEFAULT_MOTOR_PULSE_DELAY_MS
        # The first write is immediate, so one additional repeat is needed
        # after the requested number of delay intervals.
        calculated_repeat_count = max(
            2,
            (duration_ms + pulse_delay_ms - 1) // pulse_delay_ms + 1,
        )

        _LOGGER.debug(
            "Timed move: duration=%dms, pulse_delay=%dms, repeat_count=%d",
            duration_ms,
            pulse_delay_ms,
            calculated_repeat_count,
        )

        # Bind closure variables as defaults to avoid late-binding bugs
        async def timed_movement(
            ctrl: BedController,
            *,
            _move_fn: Callable[..., Coroutine[Any, Any, None]] = move_fn,
            _stop_fn: Callable[..., Coroutine[Any, Any, None]] = stop_fn,
        ) -> None:
            """Execute movement for specified duration, always sending stop."""
            try:
                await _move_fn(ctrl)
            finally:
                # Always send stop command
                await asyncio.shield(_stop_fn(ctrl))

        return (
            timed_movement,
            calculated_repeat_count,
            pulse_delay_ms,
            spec.position_key or spec.key,
        )


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

    preflighted: PreflightedSides = []
    plans: dict[
        int,
        tuple[Callable[[BedController], Coroutine[Any, Any, None]], int, int, str],
    ] = {}
    try:
        for coordinator, side in targets:
            for target in _command_targets(coordinator, side):
                plans[_plan_key(target)] = await _timed_move_plan(
                    coordinator, target, preflighted, motor, direction, duration_ms
                )
    except ServiceValidationError:
        await _release_preflighted(preflighted)
        raise

    async def move(target: AdjustableBedCoordinator) -> None:
        command, pulse_count, pulse_delay_ms, position_key = plans[_plan_key(target)]
        await target.async_execute_controller_command(
            command,
            resource=f"motor:{position_key}",
            pulse_count=pulse_count,
            pulse_delay_ms=pulse_delay_ms,
        )

    try:
        for coordinator, side in targets:
            if isinstance(coordinator, PairedBedCoordinator):
                resources = {
                    f"motor:{plans[_plan_key(target)][3]}"
                    for target in _command_targets(coordinator, side)
                }
                await coordinator.async_run_child_operation(
                    "timed move",
                    move,
                    side=side,
                    resources=resources,
                )
            else:
                await move(coordinator)
    except Exception:
        await _release_preflighted(preflighted)
        raise


async def _preflight_capability(
    targets: list[tuple[BedTarget, str]],
    capability: str,
    label: str,
) -> PreflightedSides:
    """Validate a capability on every physical target before any write."""
    preflighted: PreflightedSides = []
    try:
        for coordinator, side in targets:
            for target in _command_targets(coordinator, side):
                controller = await _validation_controller(
                    coordinator,
                    target,
                    preflighted,
                )
                if not getattr(controller, capability, False):
                    raise ServiceValidationError(
                        f"Device '{target.name}' does not support {label}",
                    )
    except ServiceValidationError:
        await _release_preflighted(preflighted)
        raise
    return preflighted


async def handle_linak_move_simultaneously(call: ServiceCall) -> None:
    """Drive two Linak sections with the app's combined opcode table."""
    hass = call.hass
    first_motor = call.data[ATTR_FIRST_MOTOR]
    second_motor = call.data[ATTR_SECOND_MOTOR]
    first_up = call.data[ATTR_FIRST_DIRECTION] == "up"
    second_up = call.data[ATTR_SECOND_DIRECTION] == "up"
    duration_ms = call.data[ATTR_DURATION_MS]
    explicit_side = call.data.get(ATTR_SIDE)
    if first_motor == second_motor:
        raise ServiceValidationError("Select two different Linak motors")

    targets, missing = _resolve_sided_targets(
        hass,
        call.data.get(CONF_DEVICE_ID, []),
        explicit_side,
    )
    if missing:
        raise _missing_device_error(missing[0])
    preflighted = await _preflight_capability(
        targets,
        "supports_simultaneous_movement",
        "Linak simultaneous movement",
    )
    try:
        for coordinator, side in targets:
            for target in _command_targets(coordinator, side):
                controller = await _validation_controller(
                    coordinator,
                    target,
                    preflighted,
                )
                unavailable = {first_motor, second_motor} - set(
                    controller.simultaneous_movement_axes
                )
                if unavailable:
                    axes = ", ".join(sorted(unavailable))
                    raise ServiceValidationError(
                        f"Device '{target.name}' does not expose Linak axis: {axes}",
                    )
    except ServiceValidationError:
        await _release_preflighted(preflighted)
        raise

    async def move(controller: BedController) -> None:
        await controller.move_simultaneously(
            first_motor,
            first_up,
            second_motor,
            second_up,
            duration_ms,
        )

    try:
        resources = tuple(
            f"motor:{'bed_height' if motor == 'base' else motor}"
            for motor in (first_motor, second_motor)
        )
        for coordinator, side in targets:
            await _execute_sided(coordinator, side, move, resources=resources)
    except Exception:
        await _release_preflighted(preflighted)
        raise


async def handle_linak_rename(call: ServiceCall) -> None:
    """Rename one or both targeted Linak BLE controllers."""
    hass = call.hass
    name = call.data[ATTR_NAME]
    if len(name.encode()) > 17:
        raise ServiceValidationError("Linak device names must be at most 17 UTF-8 bytes")
    explicit_side = call.data.get(ATTR_SIDE)
    targets, missing = _resolve_sided_targets(
        hass,
        call.data.get(CONF_DEVICE_ID, []),
        explicit_side,
    )
    if missing:
        raise _missing_device_error(missing[0])
    preflighted = await _preflight_capability(
        targets,
        "supports_device_rename",
        "Linak device rename",
    )

    async def rename(controller: BedController) -> None:
        await controller.rename_device(name)

    try:
        for coordinator, side in targets:
            await _execute_sided(
                coordinator,
                side,
                rename,
                cancel_running=False,
                resource="configuration",
            )
            for target in _command_targets(coordinator, side):
                await target.async_disconnect(reason="intentional")
    except Exception:
        await _release_preflighted(preflighted)
        raise


async def handle_linak_set_alarm(call: ServiceCall) -> None:
    """Program a Linak alarm using event, recurrence, and commit writes."""
    hass = call.hass
    steps = tuple(
        LinakAlarmStep(
            action=LinakAlarmAction(item[ATTR_ACTION]),
            lifetime=item[ATTR_LIFETIME],
            pause=item[ATTR_PAUSE],
        )
        for item in call.data[ATTR_ACTIONS]
    )
    explicit_side = call.data.get(ATTR_SIDE)
    targets, missing = _resolve_sided_targets(
        hass,
        call.data.get(CONF_DEVICE_ID, []),
        explicit_side,
    )
    if missing:
        raise _missing_device_error(missing[0])
    preflighted = await _preflight_capability(
        targets,
        "supports_alarm",
        "Linak alarm programming",
    )

    async def program(controller: BedController) -> None:
        await controller.program_alarm(
            call.data[ATTR_SECONDS],
            steps,
            call.data[ATTR_RECURRENCE_COUNT],
            call.data[ATTR_RECURRENCE_MINUTES],
        )

    try:
        for coordinator, side in targets:
            await _execute_sided(
                coordinator,
                side,
                program,
                cancel_running=False,
                resource="configuration",
            )
    except Exception:
        await _release_preflighted(preflighted)
        raise


async def handle_solace_audio(call: ServiceCall) -> None:
    """Control MotionFlex music selection, preview, query, or volume."""
    action = call.data[ATTR_ACTION]
    track = call.data.get(ATTR_TRACK)
    volume = call.data.get(ATTR_VOLUME)
    if action in {"select", "preview"} and track is None:
        raise ServiceValidationError(f"Solace audio action '{action}' requires track")
    if action == "set_volume" and volume is None:
        raise ServiceValidationError("Solace audio action 'set_volume' requires volume")
    track_value = int(track) if track is not None else 0
    volume_value = int(volume) if volume is not None else 0

    targets, missing = _resolve_sided_targets(
        call.hass,
        call.data.get(CONF_DEVICE_ID, []),
        call.data.get(ATTR_SIDE),
    )
    if missing:
        raise _missing_device_error(missing[0])
    preflighted = await _preflight_capability(
        targets,
        "supports_solace_audio",
        "Solace music/audio control",
    )

    async def control(controller: BedController) -> None:
        if action == "query":
            await controller.solace_query_audio_volume()
        elif action == "set_volume":
            await controller.solace_set_audio_volume(volume_value)
        else:
            await controller.solace_select_music(
                track_value,
                preview=action == "preview",
            )

    try:
        for coordinator, side in targets:
            await _execute_sided(
                coordinator,
                side,
                control,
                cancel_running=False,
                skip_disconnect=action == "query",
                resource="audio",
            )
    except Exception:
        await _release_preflighted(preflighted)
        raise


async def handle_solace_set_alarm(call: ServiceCall) -> None:
    """Program the MotionFlex alarm packet family."""
    weekday_numbers = tuple(
        SOLACE_WEEKDAY_OPTIONS.index(day) + 1 for day in call.data[ATTR_WEEKDAYS]
    )
    alarm_time = call.data[ATTR_TIME]
    targets, missing = _resolve_sided_targets(
        call.hass,
        call.data.get(CONF_DEVICE_ID, []),
        call.data.get(ATTR_SIDE),
    )
    if missing:
        raise _missing_device_error(missing[0])
    preflighted = await _preflight_capability(
        targets,
        "supports_solace_alarm",
        "Solace alarm programming",
    )

    async def program(controller: BedController) -> None:
        await controller.program_solace_alarm(
            enabled=call.data[ATTR_ENABLED],
            hour=alarm_time.hour,
            minute=alarm_time.minute,
            weekdays=weekday_numbers,
            mode=call.data[ATTR_MODE],
            massage=call.data[ATTR_MASSAGE],
            sound=call.data[ATTR_SOUND],
        )

    try:
        for coordinator, side in targets:
            await _execute_sided(
                coordinator,
                side,
                program,
                cancel_running=False,
                resource="configuration",
            )
    except Exception:
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
    coordinator: AdjustableBedCoordinator | None = None
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
            f"Captured {notification_count} notifications over "
            f"{capture_duration} seconds."
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
    if hass.services.has_service(DOMAIN, SERVICE_GOTO_PRESET):
        return  # Services already registered

    hass.services.async_register(
        DOMAIN,
        SERVICE_GOTO_PRESET,
        handle_goto_preset,
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
                vol.Required(ATTR_MOTOR): vol.In(["back", "legs", "head", "feet", "lumbar"]),
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
                            vol.Required(ATTR_MOTOR): vol.In(["back", "legs", "head", "feet", "lumbar"]),
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
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LINAK_MOVE_SIMULTANEOUS,
        handle_linak_move_simultaneously,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                vol.Required(ATTR_FIRST_MOTOR): vol.In(LINAK_MOTOR_OPTIONS),
                vol.Required(ATTR_FIRST_DIRECTION): vol.In(LINAK_DIRECTION_OPTIONS),
                vol.Required(ATTR_SECOND_MOTOR): vol.In(LINAK_MOTOR_OPTIONS),
                vol.Required(ATTR_SECOND_DIRECTION): vol.In(LINAK_DIRECTION_OPTIONS),
                vol.Required(ATTR_DURATION_MS): vol.All(
                    vol.Coerce(int),
                    vol.Range(
                        min=MIN_TIMED_MOVE_DURATION_MS,
                        max=MAX_TIMED_MOVE_DURATION_MS,
                    ),
                ),
                **SIDE_FIELD,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LINAK_RENAME,
        handle_linak_rename,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                vol.Required(ATTR_NAME): vol.All(cv.string, vol.Length(min=1, max=17)),
                **SIDE_FIELD,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LINAK_SET_ALARM,
        handle_linak_set_alarm,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                vol.Required(ATTR_SECONDS): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=0, max=0x1FFFF),
                ),
                vol.Required(ATTR_ACTIONS): vol.All(
                    [LINAK_ALARM_ACTION_SCHEMA],
                    vol.Length(min=1, max=4),
                ),
                vol.Optional(ATTR_RECURRENCE_COUNT, default=0): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=0, max=31),
                ),
                vol.Optional(ATTR_RECURRENCE_MINUTES, default=0): vol.All(
                    vol.Coerce(int),
                    vol.Range(min=0, max=2047),
                ),
                **SIDE_FIELD,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SOLACE_AUDIO,
        handle_solace_audio,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                vol.Required(ATTR_ACTION): vol.In(SOLACE_AUDIO_ACTIONS),
                vol.Optional(ATTR_TRACK): vol.All(vol.Coerce(int), vol.Range(min=1, max=5)),
                vol.Optional(ATTR_VOLUME): vol.All(vol.Coerce(int), vol.Range(min=1, max=5)),
                **SIDE_FIELD,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SOLACE_SET_ALARM,
        handle_solace_set_alarm,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.ensure_list,
                vol.Required(ATTR_ENABLED): cv.boolean,
                vol.Optional(ATTR_TIME, default="00:00:00"): cv.time,
                vol.Optional(ATTR_WEEKDAYS, default=[]): vol.All(
                    cv.ensure_list,
                    [vol.In(SOLACE_WEEKDAY_OPTIONS)],
                ),
                vol.Optional(ATTR_MODE, default="no_action"): vol.In(SOLACE_ALARM_MODES),
                vol.Optional(ATTR_MASSAGE, default=False): cv.boolean,
                vol.Optional(ATTR_SOUND, default="alarm"): vol.In(SOLACE_ALARM_SOUNDS),
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
