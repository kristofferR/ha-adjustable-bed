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
    CONF_BED_TYPE,
    CONF_PAIR_CONNECTION_MODE,
    CONF_PAIR_ID,
    DEFAULT_PAIR_CONNECTION_MODE,
    DOMAIN,
    PAIR_CONNECTION_MODE_AUTO,
    PAIR_CONNECTION_MODE_CONCURRENT,
    PAIR_CONNECTION_MODE_SEQUENTIAL,
    PAIR_SIDES,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
    requires_sequential_pairing,
)

if TYPE_CHECKING:
    from .coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

CommandFn = Callable[[Any], Coroutine[Any, Any, None]]


def _merge_stop_errors(
    errors: Mapping[str, BaseException],
    stop_errors: Mapping[str, BaseException],
) -> dict[str, BaseException]:
    """Merge command errors with cleanup-STOP failures under distinct keys, so a
    combined failure surfaces both — a dropped STOP can leave a side moving."""
    merged: dict[str, BaseException] = dict(errors)
    for side, err in stop_errors.items():
        merged.setdefault(f"{side} (stop)", err)
    return merged


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
        # Resolve "auto" to a concrete mode from the bed type: single-connection
        # beds (Octo) get the sequential active-connection profile; everything
        # else stays concurrent. An explicit concurrent/sequential choice is
        # honoured as-is. Resolving here (not at pair-build) auto-upgrades any
        # pre-existing "auto" pair on the next load; entry.data stays "auto".
        raw_mode = connection_mode or entry.data.get(
            CONF_PAIR_CONNECTION_MODE, DEFAULT_PAIR_CONNECTION_MODE
        )
        if raw_mode == PAIR_CONNECTION_MODE_AUTO:
            raw_mode = (
                PAIR_CONNECTION_MODE_SEQUENTIAL
                if requires_sequential_pairing(entry.data.get(CONF_BED_TYPE))
                else PAIR_CONNECTION_MODE_CONCURRENT
            )
        self._connection_mode: str = raw_mode
        # Orders connection switching in sequential mode; unused when concurrent.
        self._pair_command_lock = asyncio.Lock()
        # Preemption: STOP bumps this so a movement still queued on the lock is
        # dropped instead of starting after the stop; _active_children are the
        # sides executing under the lock, so a cancel_running command can cancel
        # them before queueing and preempt instead of waiting out the pulse window.
        self._pair_cancel_counter: dict[str, int] = {SIDE_LEFT: 0, SIDE_RIGHT: 0}
        self._active_children: set[AdjustableBedCoordinator] = set()
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

        await self._run("command", side, op, cancel_running=cancel_running)

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
        *,
        cancel_running: bool = True,
    ) -> None:
        targets = self._targets_for(side)
        target_sides = [target_side for target_side, _ in targets]

        # Preempt: invalidate any OLDER movement still queued on the lock AND
        # cancel the in-flight command on THIS command's own target sides, so a
        # reverse wins instead of waiting out the pulse window or letting a stale
        # queued movement run first. Both the cancel and the counter bump are
        # per-side — a left command must not abort or invalidate an independent
        # right movement (and vice versa).
        if cancel_running:
            for target_side in target_sides:
                self._pair_cancel_counter[target_side] += 1
            target_children = {child for _, child in targets}
            # If this command overlaps the in-flight one, preempt the WHOLE
            # in-flight command (all its children), not just the shared side: a
            # whole-bed command holds the pair lock until BOTH its children
            # finish, so cancelling only the shared side would leave the other
            # still moving AND keep the lock held until its pulse window ends,
            # delaying this command. A NON-overlapping command (e.g. a right
            # command while an independent left-only move runs) leaves the other
            # side alone — it just waits its turn on the lock.
            if any(child in target_children for child in self._active_children):
                for child in list(self._active_children):
                    child.request_command_cancel()
        entry_cancel = {s: self._pair_cancel_counter[s] for s in target_sides}

        # Serialize ALL paired commands at the parent — including a single-side
        # command, which must wait for an in-flight whole-bed command so the two
        # sides can't desync (and so sequential mode orders connection switching
        # across sides). STOP never takes this lock, so it can always interrupt.
        async with self._pair_command_lock:
            # A STOP (or newer command) bumped one of OUR target sides while we
            # waited — drop this now-stale movement instead of starting it right
            # after the safety stop.
            if any(self._pair_cancel_counter[s] != entry_cancel[s] for s in target_sides):
                return

            self._active_children = {child for _, child in targets}
            try:
                sequential = self._connection_mode == PAIR_CONNECTION_MODE_SEQUENTIAL
                if not sequential and len(targets) == 1:
                    # Single side, concurrent: no fan-out, the child owns its
                    # STOP-on-failure; nothing to cancel-STOP at the parent.
                    await op(targets[0][1])
                    return

                try:
                    if sequential:
                        # One BLE link at a time: connect/op/disconnect each
                        # targeted side in turn (one or both).
                        await self._run_both_sequential(
                            action, targets, op, entry_cancel
                        )
                    else:
                        await self._run_both_concurrent(action, targets, op)
                except asyncio.CancelledError:
                    # The parent command was cancelled (service cancellation or
                    # config-entry unload) while a side may still be moving.
                    # Cancelling the child TASKS is not the same as a STOP write,
                    # so explicitly STOP the still-connected side(s) before
                    # propagating — otherwise a motor can be left running. In
                    # sequential mode _stop_children only targets a side that is
                    # still connected (a disconnected side already halted on its
                    # link drop). _stop_children never raises and we re-raise the
                    # cancellation regardless, so this is best-effort cleanup.
                    await self._stop_children(targets)
                    raise
            finally:
                self._active_children = set()

    async def _run_both_concurrent(
        self,
        action: str,
        targets: list[tuple[str, AdjustableBedCoordinator]],
        op: Callable[[AdjustableBedCoordinator], Coroutine[Any, Any, None]],
    ) -> None:
        tasks: dict[str, asyncio.Task[None]] = {
            side: asyncio.ensure_future(op(child)) for side, child in targets
        }
        try:
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
                # STOP every side now (this also makes each child's in-flight
                # command exit early). Surface any cleanup-STOP failure too, so a
                # caller knows the "healthy" side may still be moving.
                stop_errors = await self._stop_children(targets)
                raise PairedSideError(action, _merge_stop_errors(errors, stop_errors))
        finally:
            # Never let a child task outlive this call (e.g. if the parent
            # coroutine is cancelled mid-wait): cancel any still-running task and
            # settle them all so none keep writing outside the parent lock.
            for task in tasks.values():
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)

    async def _run_both_sequential(
        self,
        action: str,
        targets: list[tuple[str, AdjustableBedCoordinator]],
        op: Callable[[AdjustableBedCoordinator], Coroutine[Any, Any, None]],
        entry_cancel: dict[str, int],
    ) -> None:
        """Run each side in turn holding only ONE BLE link at a time: connect the
        side, run its op, then disconnect it before moving to the next.

        Used for single-connection beds (Octo) whose firmware allows only one
        concurrent link. Dropping the link halts that side's motors (verified
        dead-man model — the bed only moves while a command stream arrives), so a
        side that has been disconnected needs no separate STOP. On failure the
        loop stops at the first failing side; every side that was connected is
        disconnected (the ``finally``), so nothing is left connected or moving.

        ``entry_cancel`` is the per-side cancel counter captured at command entry:
        a STOP (or newer command) bumps it, so before starting each side we re-check
        and abort the rest of the cycle — otherwise a STOP during side A would still
        let side B connect and move.
        """
        errors: dict[str, BaseException] = {}
        for side, child in targets:
            if self._pair_cancel_counter[side] != entry_cancel[side]:
                # A STOP / newer command for this side landed mid-cycle — abort
                # before connecting it (the earlier side already disconnected).
                break

            # One-link guard: release any OTHER side that is still connected (it
            # may have been connected out-of-band, e.g. a per-side diagnostic
            # Connect button) before opening this link, so we never hold two.
            if not await self._release_other_sides(child):
                errors[side] = HomeAssistantError(
                    "could not release the other side before switching"
                )
                break

            try:
                connected = await child.async_connect()
            except Exception as err:  # noqa: BLE001 - CancelledError must propagate
                errors[side] = err
                break
            if not connected:
                errors[side] = HomeAssistantError(
                    f"{side} side of the pair could not be connected"
                )
                break

            # A STOP (or newer command) may have landed WHILE we were connecting —
            # _stop_children couldn't reach this side then (it wasn't connected
            # yet), so re-check now and bail (releasing the link) instead of
            # starting a motor command after the STOP was accepted.
            if self._pair_cancel_counter[side] != entry_cancel[side]:
                await self._safe_disconnect(side, child)
                break

            op_error: BaseException | None = None
            try:
                await op(child)
            except asyncio.CancelledError:
                # Release this side (halts it) before propagating the cancellation.
                await self._safe_disconnect(side, child)
                raise
            except Exception as err:  # noqa: BLE001
                op_error = err

            # Disconnecting is BOTH the one-link guard and the halt for this side,
            # so a disconnect failure is fatal: abort rather than connect the next
            # side onto a possibly-still-live/moving link.
            disconnected = await self._safe_disconnect(side, child)
            if op_error is not None or not disconnected:
                if op_error is not None and not disconnected:
                    # Both failed: the command erred AND the release that should
                    # have halted/released the side also failed — surface both, as
                    # the link may still be live/moving (the more critical fact).
                    err = HomeAssistantError(
                        f"{side} side command failed and its release also failed "
                        f"— the link may still be live"
                    )
                    err.__cause__ = op_error
                    errors[side] = err
                elif op_error is not None:
                    errors[side] = op_error
                else:
                    errors[side] = HomeAssistantError(
                        f"{side} side failed to disconnect — aborting to keep one link"
                    )
                break
        if errors:
            raise PairedSideError(action, errors)

    async def _release_other_sides(self, keep: AdjustableBedCoordinator) -> bool:
        """Disconnect every side except ``keep`` (the one-link guard before a
        sequential connect). Returns False if any disconnect failed, so the caller
        can abort rather than risk opening a second link."""
        ok = True
        for side, child in self._children.items():
            if child is not keep and child.is_connected:
                if not await self._safe_disconnect(side, child):
                    ok = False
        return ok

    async def _safe_disconnect(
        self, side: str, child: AdjustableBedCoordinator
    ) -> bool:
        """Disconnect one side, swallowing failures. Returns True only if the link
        is actually DOWN afterwards.

        A disconnect error must not mask the command outcome, but callers that
        rely on the link being down (sequential switching) check the result — so
        besides a raised error, a disconnect that returns normally yet leaves the
        side connected (a swallowed BLE/proxy error) is also reported as a failure
        here, centrally, so no sequential caller opens a second link onto a live
        one.
        """
        try:
            await child.async_disconnect("sequential_switch")
        except Exception as err:  # noqa: BLE001 - CancelledError must propagate
            _LOGGER.warning(
                "Disconnect failed on %s side (%s): %s", side, child.address, err
            )
            return False
        if child.is_connected:
            _LOGGER.warning(
                "Disconnect returned on %s side (%s) but the link is still up",
                side,
                child.address,
            )
            return False
        return True

    async def async_stop_command(self, *, side: str = SIDE_BOTH) -> None:
        """Stop the targeted side(s); never let one side's failure skip another."""
        targets = self._targets_for(side)
        # Bump each targeted side's counter so a movement still queued on the pair
        # lock for that side drops instead of starting right after this safety stop.
        for target_side, _ in targets:
            self._pair_cancel_counter[target_side] += 1
        errors = await self._stop_children(targets)
        if errors:
            raise PairedSideError("stop", errors)

    async def _stop_children(
        self, targets: list[tuple[str, AdjustableBedCoordinator]]
    ) -> dict[str, BaseException]:
        """Send STOP to every target, swallowing individual failures.

        Returns the per-side errors (if any). Always attempts every side — a STOP
        failure on one must never prevent stopping another.

        In sequential mode only a side that is still CONNECTED is stopped: a
        disconnected side already halted when its link dropped (dead-man model),
        and stopping it would reconnect it (async_stop_command ensures a link),
        momentarily creating the two-link state the sequential profile avoids.
        """
        if self._connection_mode == PAIR_CONNECTION_MODE_SEQUENTIAL:
            targets = [(side, child) for side, child in targets if child.is_connected]
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
            # Single-connection beds hold one link at a time, so don't keep either
            # side connected after setup. Connect each side once to verify it is
            # reachable (this is also where a capability snapshot is captured),
            # then release it; commands reconnect the targeted side on demand.
            any_connected = False
            for side, child in items:
                try:
                    connected = await child.async_connect()
                except Exception as err:  # noqa: BLE001 - CancelledError must propagate
                    _LOGGER.warning("Connect failed on %s side: %s", side, err)
                    continue
                if connected:
                    any_connected = True
                    # Keep the just-discovered live controller as this side's
                    # offline capability source BEFORE releasing the link, so its
                    # per-side entities still build after this disconnect (which
                    # drops the live controller).
                    child.cache_capability_controller()
                    if not await self._safe_disconnect(side, child):
                        # Releasing the just-verified side failed (_safe_disconnect
                        # returns False on a raised error OR a disconnect that left
                        # the link up). Opening the next side now would hold two
                        # links at once, which the single-connection profile must
                        # never do (the reference app strictly disconnects-before-
                        # connect and aborts on a genuine disconnect error). Stop
                        # verifying the rest — one side left up beats two — commands
                        # reconnect on demand.
                        _LOGGER.warning(
                            "Could not release %s side after verify; skipping the "
                            "remaining side(s) to keep a single BLE link",
                            side,
                        )
                        break
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


class PairedSideProxy:
    """A child coordinator as seen by its per-side entities, with writes routed
    through the parent so they take the pair command lock.

    Per-side cover/button/number/switch entities are built against this proxy:
    reads and identity (device, unique_id, controller, positions, listeners)
    come straight from the wrapped child, while movement/command writes go
    through the parent with this side. That way a side command waits for an
    in-flight whole-bed command instead of starting concurrently and
    desyncing the pair. (Connect/disconnect stay per-child — they're connection
    management, not motion, and don't need the pair lock.)
    """

    def __init__(
        self,
        parent: PairedBedCoordinator,
        child: AdjustableBedCoordinator,
        side: str,
    ) -> None:
        """Wrap ``child`` (on ``side``) with writes routed through ``parent``."""
        self._pair_parent = parent
        self._pair_child = child
        self._pair_side = side

    def __getattr__(self, name: str) -> Any:
        # Everything not overridden below delegates to the wrapped child. Guard
        # the proxy's own attrs so a miss before __init__ can't infinitely recurse.
        if name.startswith("_pair_"):
            raise AttributeError(name)
        return getattr(self._pair_child, name)

    def __setattr__(self, name: str, value: Any) -> None:
        # The proxy's own wiring stays local; everything else delegates to the
        # child (e.g. timed_move temporarily tuning the child's _motor_pulse_count).
        if name.startswith("_pair_"):
            object.__setattr__(self, name, value)
        else:
            setattr(self._pair_child, name, value)

    async def async_execute_controller_command(
        self, command_fn: CommandFn, **kwargs: Any
    ) -> None:
        """Route a side command through the parent (takes the pair lock)."""
        await self._pair_parent.async_execute_controller_command(
            command_fn, side=self._pair_side, **kwargs
        )

    async def async_seek_position(self, *args: Any, **kwargs: Any) -> None:
        """Route a side seek through the parent (takes the pair lock)."""
        await self._pair_parent.async_seek_position(
            *args, side=self._pair_side, **kwargs
        )

    async def async_stop_command(self, **kwargs: Any) -> None:
        """Stop just this side via the parent's resilient stop contract."""
        await self._pair_parent.async_stop_command(side=self._pair_side)
