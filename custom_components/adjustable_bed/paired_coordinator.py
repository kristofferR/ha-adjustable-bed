"""Paired-bed coordinator (Dual Bed 4.0).

A thin parent that owns the two per-side child coordinators behind one uniform
side-routing API (``left`` / ``right`` / ``both``). It holds **no BleakClient of
its own** — every per-link invariant (command lock, cancel/STOP, idle/reconnect
timers, keepalive) lives unchanged in the children. The parent only fans a
command out to the right child(ren) and, for ``both``, guarantees the
partial-failure contract: if one side fails, the other is stopped and a single
aggregated error is raised.

Children are injected (built from child descriptors in production, recording
doubles in tests), so this module never imports the heavy coordinator and is
fully unit-testable. See ``docs/design/dual-bed-4.0-plan.md``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine, Mapping
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    CONF_PAIR_CONNECTION_MODE,
    CONF_PAIR_ID,
    DEFAULT_PAIR_CONNECTION_MODE,
    DOMAIN,
    PAIR_CONNECTION_MODE_SEQUENTIAL,
    PAIR_SIDES,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
)

if TYPE_CHECKING:
    from .coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

CommandFn = Callable[[Any], Coroutine[Any, Any, None]]


class PairedSideError(HomeAssistantError):
    """A side-targeted paired command failed.

    Carries the per-side outcomes so the service layer can surface a clean,
    translated message. By the time this is raised, the coordinator has already
    stopped every started side.
    """

    def __init__(self, action: str, side_errors: Mapping[str, BaseException]) -> None:
        self.action = action
        self.side_errors = dict(side_errors)
        sides = ", ".join(sorted(side_errors))
        super().__init__(f"Paired {action} failed on side(s): {sides}")


class PairedBedCoordinator:
    """Routes left/right/both commands across two child coordinators."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        children: Mapping[str, AdjustableBedCoordinator],
        *,
        connection_mode: str | None = None,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self._pair_id: str = entry.data[CONF_PAIR_ID]
        self._name: str = entry.data.get("name", "Adjustable Bed")
        # Ordered {side: child}, left first. A side may be absent only in
        # degraded/test setups; normally both are present (a disconnected child
        # is still present, just not is_connected).
        self._children: dict[str, AdjustableBedCoordinator] = {
            side: children[side] for side in PAIR_SIDES if side in children
        }
        if not self._children:
            raise ValueError("PairedBedCoordinator requires at least one child")
        self._connection_mode: str = connection_mode or entry.data.get(
            CONF_PAIR_CONNECTION_MODE, DEFAULT_PAIR_CONNECTION_MODE
        )
        # Orders connection switching in sequential mode; unused when concurrent.
        self._pair_command_lock = asyncio.Lock()
        self._connection_state_callbacks: set[Callable[[bool], None]] = set()
        self._child_unsubs: list[Callable[[], None]] = []
        self._wire_child_connection_callbacks()

    # ------------------------------------------------------------------ identity
    @property
    def pair_id(self) -> str:
        return self._pair_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def connection_mode(self) -> str:
        return self._connection_mode

    @property
    def sides(self) -> tuple[str, ...]:
        """Sides that have a child, in stable order."""
        return tuple(self._children)

    @property
    def children(self) -> dict[str, AdjustableBedCoordinator]:
        return dict(self._children)

    def child_for_side(self, side: str) -> AdjustableBedCoordinator | None:
        return self._children.get(side)

    @property
    def is_connected(self) -> bool:
        """True if *any* side is connected (a half-available pair is usable)."""
        return any(child.is_connected for child in self._children.values())

    @property
    def device_info(self) -> DeviceInfo:
        """Synthetic parent device; children nest under it via ``via_device``."""
        first = next(iter(self._children.values()))
        child_info = first.device_info
        manufacturer = (
            child_info.get("manufacturer") if isinstance(child_info, dict) else None
        )
        return DeviceInfo(
            identifiers={(DOMAIN, self._pair_id)},
            name=self._name,
            manufacturer=manufacturer,
            model="Adjustable Bed (paired)",
        )

    # ------------------------------------------------------------------ routing
    def _validate_side(self, side: str) -> None:
        if side not in (SIDE_LEFT, SIDE_RIGHT, SIDE_BOTH):
            raise ValueError(f"Unknown side {side!r}")
        if side in (SIDE_LEFT, SIDE_RIGHT) and side not in self._children:
            raise ValueError(f"Paired bed has no {side} side")

    def _targets_for(self, side: str) -> list[tuple[str, AdjustableBedCoordinator]]:
        self._validate_side(side)
        if side == SIDE_BOTH:
            return [(s, self._children[s]) for s in PAIR_SIDES if s in self._children]
        return [(side, self._children[side])]

    # ------------------------------------------------------------------ commands
    async def async_execute_controller_command(
        self,
        command_fn: CommandFn,
        *,
        side: str = SIDE_BOTH,
        cancel_running: bool = True,
        skip_disconnect: bool = False,
    ) -> None:
        """Run ``command_fn`` on the targeted side(s) with the both-failure contract."""

        async def op(child: AdjustableBedCoordinator) -> None:
            await child.async_execute_controller_command(
                command_fn,
                cancel_running=cancel_running,
                skip_disconnect=skip_disconnect,
            )

        await self._run("command", side, op)

    async def async_seek_position(
        self,
        position_key: str,
        target_angle: float,
        move_up_fn: CommandFn,
        move_down_fn: CommandFn,
        move_stop_fn: CommandFn,
        *,
        side: str = SIDE_BOTH,
    ) -> None:
        """Seek a target position on the targeted side(s)."""

        async def op(child: AdjustableBedCoordinator) -> None:
            await child.async_seek_position(
                position_key, target_angle, move_up_fn, move_down_fn, move_stop_fn
            )

        await self._run("seek", side, op)

    async def _run(
        self,
        action: str,
        side: str,
        op: Callable[[AdjustableBedCoordinator], Coroutine[Any, Any, None]],
    ) -> None:
        targets = self._targets_for(side)

        # Single side: no fan-out, the child owns its own STOP-on-failure.
        if len(targets) == 1:
            await op(targets[0][1])
            return

        # Serialize whole-bed ('both') commands at the parent so two overlapping
        # commands can't interleave and desync the sides (and so sequential mode
        # orders connection switching across sides). STOP never takes this lock,
        # so it can always interrupt a running command.
        async with self._pair_command_lock:
            if self._connection_mode == PAIR_CONNECTION_MODE_SEQUENTIAL:
                await self._run_both_sequential(action, targets, op)
            else:
                await self._run_both_concurrent(action, targets, op)

    async def _run_both_concurrent(
        self,
        action: str,
        targets: list[tuple[str, AdjustableBedCoordinator]],
        op: Callable[[AdjustableBedCoordinator], Coroutine[Any, Any, None]],
    ) -> None:
        tasks: dict[str, asyncio.Task[None]] = {
            side: asyncio.ensure_future(op(child)) for side, child in targets
        }
        # Return as soon as the FIRST side fails (or all complete), so the
        # stop-the-other cleanup fires immediately instead of waiting for the
        # healthy side to finish its full send window.
        await asyncio.wait(tasks.values(), return_when=asyncio.FIRST_EXCEPTION)

        errors: dict[str, BaseException] = {}
        for side, task in tasks.items():
            if task.done() and not task.cancelled():
                exc = task.exception()
                if exc is not None:
                    errors[side] = exc

        if errors:
            # STOP every side now (this also makes each child's in-flight command
            # exit early), swallow per-side STOP errors, settle the tasks, raise.
            await self._stop_children(targets)
            await asyncio.gather(*tasks.values(), return_exceptions=True)
            raise PairedSideError(action, errors)

        # No failures: FIRST_EXCEPTION already waited for all to complete.
        await asyncio.gather(*tasks.values(), return_exceptions=True)

    async def _run_both_sequential(
        self,
        action: str,
        targets: list[tuple[str, AdjustableBedCoordinator]],
        op: Callable[[AdjustableBedCoordinator], Coroutine[Any, Any, None]],
    ) -> None:
        started: list[tuple[str, AdjustableBedCoordinator]] = []
        errors: dict[str, BaseException] = {}
        for side, child in targets:
            try:
                await op(child)
                started.append((side, child))
            except Exception as err:  # noqa: BLE001 - CancelledError must propagate
                errors[side] = err
                started.append((side, child))
                break
        if errors:
            await self._stop_children(started)
            raise PairedSideError(action, errors)

    async def async_stop_command(self, *, side: str = SIDE_BOTH) -> None:
        """Stop the targeted side(s); never let one side's failure skip another."""
        targets = self._targets_for(side)
        errors = await self._stop_children(targets)
        if errors:
            raise PairedSideError("stop", errors)

    async def _stop_children(
        self, targets: list[tuple[str, AdjustableBedCoordinator]]
    ) -> dict[str, BaseException]:
        """Send STOP to every target, swallowing individual failures.

        Returns the per-side errors (if any). Always attempts every side — a STOP
        failure on one must never prevent stopping another.
        """
        results = await asyncio.gather(
            *(child.async_stop_command() for _, child in targets),
            return_exceptions=True,
        )
        errors: dict[str, BaseException] = {}
        for (side, child), result in zip(targets, results, strict=True):
            if isinstance(result, BaseException):
                errors[side] = result
                _LOGGER.warning(
                    "STOP failed on %s side (%s): %s", side, child.address, result
                )
        return errors

    # ------------------------------------------------------------------ lifecycle
    async def async_connect(self) -> bool:
        """Connect the children; succeed if *at least one* connects (half-available)."""
        items = list(self._children.items())
        if self._connection_mode == PAIR_CONNECTION_MODE_SEQUENTIAL:
            any_connected = False
            for side, child in items:
                try:
                    if await child.async_connect():
                        any_connected = True
                except Exception as err:  # noqa: BLE001 - CancelledError must propagate
                    _LOGGER.warning("Connect failed on %s side: %s", side, err)
            return any_connected

        results = await asyncio.gather(
            *(child.async_connect() for _, child in items), return_exceptions=True
        )
        for (side, _), result in zip(items, results, strict=True):
            if isinstance(result, BaseException):
                _LOGGER.warning("Connect failed on %s side: %s", side, result)
        return any(result is True for result in results)

    async def async_disconnect(self, reason: str = "intentional") -> None:
        await asyncio.gather(
            *(child.async_disconnect(reason) for child in self._children.values()),
            return_exceptions=True,
        )

    async def async_shutdown(self) -> None:
        for unsub in self._child_unsubs:
            unsub()
        self._child_unsubs.clear()
        await asyncio.gather(
            *(child.async_shutdown() for child in self._children.values()),
            return_exceptions=True,
        )

    # --------------------------------------------------- connection-state relay
    def _wire_child_connection_callbacks(self) -> None:
        for child in self._children.values():
            self._child_unsubs.append(
                child.register_connection_state_callback(
                    self._on_child_connection_change
                )
            )

    def _on_child_connection_change(self, _connected: bool) -> None:
        aggregate = self.is_connected
        for callback_fn in list(self._connection_state_callbacks):
            try:
                callback_fn(aggregate)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Paired connection state callback error: %s", err)

    def register_connection_state_callback(
        self, callback_fn: Callable[[bool], None]
    ) -> Callable[[], None]:
        """Register for aggregate (any-side) connection-state changes."""
        self._connection_state_callbacks.add(callback_fn)

        def unregister() -> None:
            self._connection_state_callbacks.discard(callback_fn)

        return unregister
