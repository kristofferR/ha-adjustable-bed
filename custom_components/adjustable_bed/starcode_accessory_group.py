"""AdjustableM5X5's main plus up to three independently addressed lifts."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from typing import cast

import voluptuous as vol
from homeassistant.const import CONF_ADDRESS, CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_get_device_and_config_entry

from .beds.base import BedController
from .beds.starcode_m5x5 import PROFILES, StarcodeM5X5Controller
from .const import (
    BED_TYPE_STARCODE_M5X5,
    CONF_BED_TYPE,
    CONF_STARCODE_LIFT_ENTRIES,
    CONF_STARCODE_M5X5_PROFILE,
    DOMAIN,
)
from .coordinator import AdjustableBedCoordinator
from .pairing import is_paired

_OPERATIONS = f"{DOMAIN}_starcode_group_operations"
_GROUP_DISPATCH: ContextVar[bool] = ContextVar("starcode_group_dispatch", default=False)
type GroupTasks = dict[str, set[asyncio.Task[object]]]


@dataclass
class _CleanupStopScope:
    active: bool = True


_GROUP_CLEANUP: ContextVar[_CleanupStopScope | None] = ContextVar("starcode_group_cleanup", default=None)


def _tasks(hass: HomeAssistant, *, cleanup: bool = False) -> GroupTasks:
    key = f"{_OPERATIONS}_cleanup" if cleanup else _OPERATIONS
    return cast(GroupTasks, hass.data.setdefault(key, {}))


def _stop_epochs(hass: HomeAssistant) -> dict[str, int]:
    return cast(dict[str, int], hass.data.setdefault(f"{_OPERATIONS}_stop_epochs", {}))


def cancel_group_operations(
    hass: HomeAssistant, entry_id: str, *, invalidate_admission: bool = True
) -> None:
    """Cancel retained delayed writes on STOP, unload and configuration edits."""
    cleanup_scope = _GROUP_CLEANUP.get()
    if invalidate_admission and (cleanup_scope is None or not cleanup_scope.active):
        epochs = _stop_epochs(hass)
        epochs[entry_id] = epochs.get(entry_id, 0) + 1
    current = asyncio.current_task()
    for task in tuple(_tasks(hass).get(entry_id, ())):
        if task is not current and not task.done():
            task.cancel()


def validate_lift_entries(
    hass: HomeAssistant,
    main_data: Mapping[str, object],
    entries: object,
    *,
    main_entry_id: str | None = None,
) -> tuple[str, ...]:
    """Validate offline identity and the app's four bedding classes in either slot."""
    if (
        not isinstance(entries, (tuple, list))
        or len(entries) > 3
        or any(not isinstance(v, str) for v in entries)
    ):
        raise ValueError("Select at most three independently configured lift beds")
    result: list[str] = []
    addresses = {str(main_data.get(CONF_ADDRESS, "")).upper()}
    for entry_id in entries:
        if entry_id in result or entry_id == main_entry_id:
            raise ValueError("The main and each lift must be distinct")
        entry = hass.config_entries.async_get_entry(entry_id)
        if (
            entry is None
            or entry.domain != DOMAIN
            or entry.data.get(CONF_BED_TYPE) != BED_TYPE_STARCODE_M5X5
            or entry.data.get(CONF_STARCODE_M5X5_PROFILE) not in PROFILES
        ):
            raise ValueError("Each lift must use an AdjustableM5X5 bedding profile")
        address = str(entry.data.get(CONF_ADDRESS, "")).upper()
        if not address or address in addresses:
            raise ValueError("Each group member must have a distinct Bluetooth address")
        # A one-main/multiple-lifts layout is separate from paired Left/Right ownership.
        if is_paired(entry.data):
            raise ValueError("Paired entries cannot become independently addressed lifts")
        addresses.add(address)
        result.append(entry_id)
    return tuple(result)


def lift_choices(hass: HomeAssistant, main_entry_id: str | None = None) -> dict[str, str]:
    return {
        entry.entry_id: entry.title
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.entry_id != main_entry_id
        and entry.data.get(CONF_BED_TYPE) == BED_TYPE_STARCODE_M5X5
        and entry.data.get(CONF_STARCODE_M5X5_PROFILE) in PROFILES
    }


def _resolve(hass: HomeAssistant, entry_id: str) -> AdjustableBedCoordinator:
    value = hass.data.get(DOMAIN, {}).get(entry_id)
    if not isinstance(value, AdjustableBedCoordinator) or value.bed_type != BED_TYPE_STARCODE_M5X5:
        raise ServiceValidationError("The selected AdjustableM5X5 bed is unavailable")
    return value


def _controller(controller: BedController | None) -> StarcodeM5X5Controller:
    if not isinstance(controller, StarcodeM5X5Controller) or not controller.ready:
        raise ConnectionError("An AdjustableM5X5 group member is not ready")
    return controller


async def _interrupt(controller: BedController) -> None:
    await _controller(controller).interrupt()


@contextmanager
def _group_dispatch() -> Iterator[None]:
    """Suppress cross-interrupt only inside this scheduled group command."""
    token = _GROUP_DISPATCH.set(True)
    try:
        yield
    finally:
        _GROUP_DISPATCH.reset(token)


async def _flat(controller: BedController) -> None:
    with _group_dispatch():
        await _controller(controller).preset_flat()


async def _up(controller: BedController) -> None:
    with _group_dispatch():
        await _controller(controller).move_both_up()


async def _down(controller: BedController) -> None:
    with _group_dispatch():
        await _controller(controller).move_both_down()


async def _preflight(
    targets: Sequence[AdjustableBedCoordinator], admitted: list[AdjustableBedCoordinator]
) -> None:
    for target in targets:
        if not await target.async_ensure_connected():
            raise ConnectionError("An AdjustableM5X5 group member could not connect")
        admitted.append(target)
        if target.controller is None:
            raise ConnectionError("An AdjustableM5X5 group member has no controller")
        _controller(target.controller)


async def _stop(targets: Sequence[AdjustableBedCoordinator], *, cleanup: bool = False) -> None:
    # Safety STOP tasks inherit this invocation's context, unlike retained command workers.
    scope = _CleanupStopScope() if cleanup else None
    token = _GROUP_CLEANUP.set(scope)
    try:
        results = await asyncio.gather(
            *(target.async_stop_command() for target in targets), return_exceptions=True
        )
    finally:
        if scope is not None:
            scope.active = False
        _GROUP_CLEANUP.reset(token)
    failures = [result for result in results if isinstance(result, Exception)]
    if failures:
        raise ExceptionGroup("Some AdjustableM5X5 targets could not stop", failures)


async def interrupt_conflicting_group(source: AdjustableBedCoordinator) -> None:
    """Ordinary main motion interrupts lifts; ordinary lift motion interrupts its main."""
    if _GROUP_DISPATCH.get():
        return
    hass = source.hass
    cancel_group_operations(hass, source.entry.entry_id)
    other_ids = list(
        validate_lift_entries(
            hass,
            source.entry.data,
            source.entry.data.get(CONF_STARCODE_LIFT_ENTRIES, []),
            main_entry_id=source.entry.entry_id,
        )
    )
    for entry in hass.config_entries.async_entries(DOMAIN):
        if source.entry.entry_id in entry.data.get(CONF_STARCODE_LIFT_ENTRIES, ()):
            other_ids.append(entry.entry_id)
    targets = [_resolve(hass, entry_id) for entry_id in dict.fromkeys(other_ids)]
    admitted: list[AdjustableBedCoordinator] = []
    try:
        await _preflight(targets, admitted)
        for target in targets:
            cancel_group_operations(hass, target.entry.entry_id)
            await target.async_execute_controller_command(
                _interrupt, read_positions_after_operation=False
            )
    except BaseException:
        await _stop(admitted)
        raise


async def _stop_configured_group(
    hass: HomeAssistant, main_entry_id: str, lift_entries: object
) -> None:
    """Cancel first, then attempt every reachable target before reporting failures."""
    failures: list[Exception] = []
    ids = [main_entry_id]
    if isinstance(lift_entries, (tuple, list)):
        for entry_id in lift_entries:
            if isinstance(entry_id, str):
                if entry_id not in ids:
                    ids.append(entry_id)
            else:
                failures.append(ServiceValidationError("A configured lift ID is invalid"))
    else:
        failures.append(ServiceValidationError("The configured lift selection is invalid"))
    epochs = _stop_epochs(hass)
    for entry_id in ids:
        epochs[entry_id] = epochs.get(entry_id, 0) + 1
        cancel_group_operations(hass, entry_id)
    reachable: list[AdjustableBedCoordinator] = []
    for entry_id in ids:
        try:
            reachable.append(_resolve(hass, entry_id))
        except ServiceValidationError as error:
            failures.append(error)
    try:
        await _stop(reachable)
    except Exception as error:
        failures.append(error)
    if failures:
        raise ExceptionGroup("Some AdjustableM5X5 targets could not stop", failures)


async def _settle_previous_groups(hass: HomeAssistant, ids: Sequence[str]) -> None:
    """Drain prior cleanup without letting a cancelled waiter cancel its STOPs."""
    current = asyncio.current_task()
    while True:
        prior = {
            task
            for cleanup in (False, True)
            for entry_id in ids
            for task in _tasks(hass, cleanup=cleanup).get(entry_id, ())
            if task is not current and not task.done()
        }
        if not prior:
            return
        for entry_id in ids:
            cancel_group_operations(hass, entry_id, invalidate_admission=False)
        results = await asyncio.shield(asyncio.gather(*prior, return_exceptions=True))
        failures = [result for result in results if isinstance(result, Exception)]
        if failures:
            raise ExceptionGroup("Previous AdjustableM5X5 group cleanup failed", failures)


async def run_group(main: AdjustableBedCoordinator, action: str) -> None:
    """Preflight all four possible addresses before admitting any group writes."""
    if action not in ("up", "down", "flat", "stop"):
        raise ValueError("Use up, down, flat or stop")
    hass = main.hass
    if action == "stop":
        await _stop_configured_group(
            hass, main.entry.entry_id, main.entry.data.get(CONF_STARCODE_LIFT_ENTRIES, [])
        )
        return
    ids = validate_lift_entries(
        hass,
        main.entry.data,
        main.entry.data.get(CONF_STARCODE_LIFT_ENTRIES, []),
        main_entry_id=main.entry.entry_id,
    )
    if not ids:
        raise ServiceValidationError("Configure at least one lift on the main bed")
    lifts = tuple(_resolve(hass, entry_id) for entry_id in ids)
    targets = (main, *lifts)
    target_ids = (main.entry.entry_id, *ids)
    epochs = tuple(_stop_epochs(hass).get(entry_id, 0) for entry_id in target_ids)

    def require_admission() -> None:
        if epochs != tuple(_stop_epochs(hass).get(entry_id, 0) for entry_id in target_ids):
            raise asyncio.CancelledError("An AdjustableM5X5 STOP cancelled admission")
        if ids != validate_lift_entries(
            hass,
            main.entry.data,
            main.entry.data.get(CONF_STARCODE_LIFT_ENTRIES, []),
            main_entry_id=main.entry.entry_id,
        ) or any(hass.data.get(DOMAIN, {}).get(t.entry.entry_id) is not t for t in targets):
            raise asyncio.CancelledError("The AdjustableM5X5 selection changed before admission")

    def owned(command: Callable[[BedController], Awaitable[None]]):
        @wraps(command)
        async def dispatch(controller: BedController) -> None:
            require_admission()
            await command(controller)

        return dispatch

    await _settle_previous_groups(hass, target_ids)
    require_admission()
    task = asyncio.current_task()
    if task is None:
        raise RuntimeError("Group operations require a retained task")
    retained = cast(asyncio.Task[object], task)
    for target in targets:
        _tasks(hass).setdefault(target.entry.entry_id, set()).add(retained)
    admitted: list[AdjustableBedCoordinator] = []
    completed = False
    connections = ExitStack()
    try:
        for target in targets:
            connections.enter_context(target.hold_command_connection())
        await _preflight(targets, admitted)
        require_admission()
        sessions = tuple(
            (
                _controller(target.controller),
                target.client,
                _controller(target.controller).session_generation,
            )
            for target in targets
        )
        # Interruption is distinct from a held operation's release/STOP frame.
        for target in targets:
            await target.async_execute_controller_command(
                owned(_interrupt), read_positions_after_operation=False
            )
        if action == "flat":
            await main.async_execute_controller_command(
                owned(_flat), read_positions_after_operation=False
            )
            await asyncio.sleep(1.6)
            require_admission()
            current = validate_lift_entries(
                hass,
                main.entry.data,
                main.entry.data.get(CONF_STARCODE_LIFT_ENTRIES, []),
                main_entry_id=main.entry.entry_id,
            )
            if current != ids or any(
                hass.data.get(DOMAIN, {}).get(target.entry.entry_id) is not target
                for target in targets
            ):
                raise asyncio.CancelledError("The AdjustableM5X5 selection changed")
            if any(
                target.controller is not controller
                or target.client is not client
                or not controller.ready
                or controller.session_generation != generation
                for target, (controller, client, generation) in zip(targets, sessions, strict=True)
            ):
                raise asyncio.CancelledError("An AdjustableM5X5 group session changed")
            command = _flat
        else:
            command = _up if action == "up" else _down
        async with asyncio.TaskGroup() as running:
            for target in lifts:
                running.create_task(
                    target.async_execute_controller_command(
                        owned(command), read_positions_after_operation=False
                    )
                )
        completed = True
    finally:
        for target in targets:
            _tasks(hass, cleanup=True).setdefault(target.entry.entry_id, set()).add(retained)
            members = _tasks(hass).get(target.entry.entry_id)
            if members is not None:
                members.discard(retained)
                if not members:
                    _tasks(hass).pop(target.entry.entry_id, None)
        try:
            if not completed or action != "flat":
                await _stop(admitted, cleanup=True)
        finally:
            connections.close()
            for target in targets:
                members = _tasks(hass, cleanup=True).get(target.entry.entry_id)
                if members is not None:
                    members.discard(retained)
                    if not members:
                        _tasks(hass, cleanup=True).pop(target.entry.entry_id, None)


async def handle_group(call: ServiceCall) -> None:
    _, entry = async_get_device_and_config_entry(call.hass, DOMAIN, call.data[CONF_DEVICE_ID])
    if call.data["action"] == "stop":
        await _stop_configured_group(
            call.hass, entry.entry_id, entry.data.get(CONF_STARCODE_LIFT_ENTRIES, [])
        )
        return
    await run_group(_resolve(call.hass, entry.entry_id), call.data["action"])


def register_group_services(hass: HomeAssistant) -> None:
    hass.services.async_register(
        DOMAIN,
        "starcode_move_lifts",
        handle_group,
        schema=vol.Schema(
            {
                vol.Required(CONF_DEVICE_ID): cv.string,
                vol.Required("action"): vol.In(("up", "down", "flat", "stop")),
            }
        ),
    )
