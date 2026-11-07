"""Paired-bed coordinator (Dual Bed 4.0).

A thin parent that owns the two per-side child coordinators behind one uniform
side-routing API (``left`` / ``right`` / ``both``). It holds **no BleakClient of
its own** — every per-link invariant (command lock, cancel/STOP, idle/reconnect
timers, keepalive) lives unchanged in the children.

The parent is a facade over one topology strategy (``paired_topology``), chosen
by the physical layout and connection mode. The strategy owns target admission,
locking, prepare/commit, connection switching and STOP fan-out, including the
partial-failure contract: if one side fails, every started side is stopped and
a single aggregated error is raised.

Children are injected (built from child descriptors in production, recording
doubles in tests), so this module never imports the heavy coordinator and is
fully unit-testable. See ``docs/design/dual-bed-4.0-plan.md``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable, Collection, Coroutine, Mapping
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import ChildDeviceInfo, DeviceInfo

from .beds.base import CONTROLLER_GESTURE_RELEASE, BedController
from .command_scheduler import (
    CommandHandle,
    CommandKind,
    HoldClaim,
    HoldLease,
    command_resources,
)
from .const import (
    BED_TYPE_ERGOMOTION,
    BED_TYPE_GMMOTOR,
    BED_TYPE_GOODVIBE,
    BED_TYPE_KEESON,
    BED_TYPE_MOTOMOTION,
    BED_TYPE_OKIN_CB24,
    BED_TYPE_SLEEP_NUMBER,
    CONF_BED_TYPE,
    CONF_PAIR_CONNECTION_MODE,
    CONF_PAIR_ID,
    CONF_PRODUCT_TYPE,
    CONF_PROTOCOL_VARIANT,
    DEFAULT_PAIR_CONNECTION_MODE,
    DOMAIN,
    PAIR_CONNECTION_MODE_AUTO,
    PAIR_CONNECTION_MODE_CONCURRENT,
    PAIR_CONNECTION_MODE_SEQUENTIAL,
    PAIR_SIDES,
    SIDE_BOTH,
    SIDE_LEFT,
    SIDE_RIGHT,
)
from .entity_runtime import ControllerCommand, EntityRuntime, EntityRuntimeView
from .paired_devices import child_device_info
from .paired_topology import (
    ConcurrentTwoLinkTopology,
    ConnectionModeChanged,
    PairAdmission,
    PairedSideError,
    PairTarget,
    PairTopology,
    SequentialTwoLinkTopology,
    SingleLinkSideAwareTopology,
    linked_readiness_required,
)
from .position_seek import SeekOutcome, SeekResult
from .remacro_discovery import remacro_side_lacks_global_stop

if TYPE_CHECKING:
    from bleak import BleakClient

    from .coordinator import AdjustableBedCoordinator

_LOGGER = logging.getLogger(__name__)

CommandFn = ControllerCommand

type BedChild = AdjustableBedCoordinator | SingleAddressSideCoordinator

__all__ = [
    "BedChild",
    "PairedBedCoordinator",
    "PairedSideError",
    "PairedSideProxy",
    "SingleAddressPairedCoordinator",
    "SingleAddressSideCoordinator",
    "entity_runtimes",
]


class PairedBedCoordinator:
    """Routes left/right/both commands across two child coordinators."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        children: Mapping[str, BedChild],
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
        self._children: dict[str, BedChild] = {
            side: children[side] for side in PAIR_SIDES if side in children
        }
        if not self._children:
            raise ValueError("PairedBedCoordinator requires at least one child")
        # Separate receivers retain their standalone connection lifecycles. Auto
        # starts concurrent and can fall back at runtime when a real adapter-slot
        # exhaustion error proves that both links cannot coexist. Explicit choices
        # never change automatically.
        raw_mode = connection_mode or entry.data.get(
            CONF_PAIR_CONNECTION_MODE, DEFAULT_PAIR_CONNECTION_MODE
        )
        self._automatic_connection_mode = raw_mode == PAIR_CONNECTION_MODE_AUTO
        if self._automatic_connection_mode:
            raw_mode = PAIR_CONNECTION_MODE_CONCURRENT
        # Keep a public STOP from selecting concurrent targets while automatic
        # fallback is disconnecting those same children before switching modes.
        self._connection_mode_transition_lock = asyncio.Lock()
        self._admission = PairAdmission()
        self._lanes, self._sequential = self._build_topologies()
        self._connection_mode = raw_mode
        self._connection_state_callbacks: set[Callable[[bool], None]] = set()
        self._child_unsubs: list[Callable[[], None]] = []
        self._wire_child_connection_callbacks()

    def _build_topologies(
        self,
    ) -> tuple[ConcurrentTwoLinkTopology | SingleLinkSideAwareTopology, SequentialTwoLinkTopology | None]:
        """Return the lane topology and, for two links, the sequential one.

        Both exist for two-link pairs so automatic fallback, and the lanes it
        quiesces, survive a mode change.
        """
        return ConcurrentTwoLinkTopology(self), SequentialTwoLinkTopology(self)

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
    def _connection_mode(self) -> str:
        return self._mode

    @_connection_mode.setter
    def _connection_mode(self, mode: str) -> None:
        if mode == PAIR_CONNECTION_MODE_SEQUENTIAL and self._sequential is None:
            raise ValueError("A single-link pair has no sequential connection mode")
        self._mode = mode

    @property
    def _topology(self) -> PairTopology:
        """The strategy that routes the next command, from the current mode."""
        if self._mode == PAIR_CONNECTION_MODE_SEQUENTIAL and self._sequential is not None:
            return self._sequential
        return self._lanes

    def _adopt_connection_mode(self, mode: str) -> None:
        """Switch strategies after automatic fallback and announce the result."""
        self._connection_mode = mode
        self._on_child_connection_change(self.is_connected)

    @property
    def sides(self) -> tuple[str, ...]:
        """Sides that have a child, in stable order."""
        return tuple(self._children)

    @property
    def children(self) -> dict[str, BedChild]:
        return dict(self._children)

    def child_for_side(self, side: str) -> BedChild | None:
        return self._children.get(side)

    @contextlib.asynccontextmanager
    async def async_capability_reload_guard(self) -> AsyncIterator[None]:
        """Wait for every side to become idle before reloading the pair."""
        targets = list(self._children.items())
        async with contextlib.AsyncExitStack() as stack:
            await stack.enter_async_context(self._topology.capability_reload_guard(targets))
            for _, child in targets:
                await stack.enter_async_context(child.async_command_operation_guard())
            yield

    async def async_remove_child(self, side: str) -> None:
        """Drop a side whose standalone entry could not be absorbed safely."""
        child = self._children.pop(side, None)
        if child is None:
            return
        # Rebuild the aggregate connection callbacks without the removed child.
        for unsubscribe in self._child_unsubs:
            unsubscribe()
        self._child_unsubs.clear()
        self._wire_child_connection_callbacks()
        await child.async_shutdown()

    @property
    def is_connected(self) -> bool:
        """True if *any* side is connected (a half-available pair is usable)."""
        return any(child.is_connected for child in self._children.values())

    @property
    def device_info(self) -> DeviceInfo:
        """Synthetic parent device; each side is a child device of it."""
        first = next(iter(self._children.values()))
        return DeviceInfo(
            identifiers={(DOMAIN, self._pair_id)},
            name=self._name,
            manufacturer=first.device_info.get("manufacturer"),
            model="Adjustable Bed (paired)",
        )

    def entity_unique_id(self, key: str) -> str:
        """Return a stable unique id for a combined parent entity."""
        return f"{self._pair_id}_{key}"

    # ------------------------------------------------------------------ admission
    # Services capture and revalidate pair ownership around their own preflight.
    def _targets_for(self, side: str) -> list[PairTarget]:
        return self._topology.targets_for(side)

    def _pair_cancel_generation(self, side: str, resources: Collection[str]) -> tuple[int, ...]:
        return self._admission.generation(side, resources)

    def _pair_admission_was_cancelled(
        self,
        targets: Collection[PairTarget],
        resources: Collection[str],
        entry_cancel: Mapping[str, tuple[int, ...]],
        expected_stop_epochs: Mapping[str, int] | None,
    ) -> bool:
        return self._admission.admission_was_cancelled(
            targets, resources, entry_cancel, expected_stop_epochs
        )

    def _locked_target_sides(
        self, targets: Collection[PairTarget]
    ) -> contextlib.AbstractAsyncContextManager[None]:
        """Lock selected side lanes in stable order (Reverie comfort reservations)."""
        return self._lanes.locked_target_sides(targets)

    # ------------------------------------------------------------------ commands
    async def async_execute_controller_command(
        self,
        command_fn: CommandFn,
        *,
        side: str = SIDE_BOTH,
        cancel_running: bool = True,
        skip_disconnect: bool = False,
        resource: str | None = None,
        resources: Collection[str] | None = None,
        expected_pair_generations: Mapping[str, tuple[int, ...]] | None = None,
        expected_stop_epochs: Mapping[str, int] | None = None,
        lease: HoldLease | None = None,
    ) -> None:
        """Run ``command_fn`` on the targeted side(s) with the both-failure contract.

        A ``lease`` gives each physical side its own hold with that owner and
        generation, so one renewal renews both.
        """
        if resource is not None and resources is not None:
            raise ValueError("Pass resource or resources, not both")
        targets_by_child = {
            id(child): target_side for target_side, child in self._targets_for(side)
        }

        async def op(child: BedChild) -> None:
            target_side = targets_by_child[id(child)]
            expected_stop_epoch = (
                expected_stop_epochs.get(target_side)
                if expected_stop_epochs is not None
                else None
            )
            if lease is not None:
                await child.async_execute_controller_command(
                    command_fn,
                    cancel_running=cancel_running,
                    skip_disconnect=skip_disconnect,
                    resource=resource,
                    resources=resources,
                    expected_stop_epoch=expected_stop_epoch,
                    lease=lease,
                )
            elif expected_stop_epoch is None:
                await child.async_execute_controller_command(
                    command_fn,
                    cancel_running=cancel_running,
                    skip_disconnect=skip_disconnect,
                    resource=resource,
                    resources=resources,
                )
            else:
                await child.async_execute_controller_command(
                    command_fn,
                    cancel_running=cancel_running,
                    skip_disconnect=skip_disconnect,
                    resource=resource,
                    resources=resources,
                    expected_stop_epoch=expected_stop_epoch,
                )

        await self._run(
            "command",
            side,
            op,
            cancel_running=cancel_running,
            resource=resource,
            resources=resources,
            expected_pair_generations=expected_pair_generations,
            expected_stop_epochs=expected_stop_epochs,
        )

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

        async def op(child: BedChild) -> None:
            await child.async_seek_position(
                position_key, target_angle, move_up_fn, move_down_fn, move_stop_fn
            )

        await self._run("seek", side, op, resource=f"motor:{position_key}")

    async def async_run_child_operation(
        self,
        action: str,
        operation: Callable[
            [BedChild], Coroutine[Any, Any, None]
        ],
        *,
        side: str = SIDE_BOTH,
        cancel_running: bool = True,
        resource: str | None = None,
        resources: Collection[str] | None = None,
        expected_pair_generations: Mapping[str, tuple[int, ...]] | None = None,
        expected_stop_epochs: Mapping[str, int] | None = None,
    ) -> None:
        """Run a child-specific operation with the paired failure contract."""
        if resource is not None and resources is not None:
            raise ValueError("Pass resource or resources, not both")
        await self._run(
            action,
            side,
            operation,
            cancel_running=cancel_running,
            resource=resource,
            resources=resources,
            expected_pair_generations=expected_pair_generations,
            expected_stop_epochs=expected_stop_epochs,
        )

    async def _run(
        self,
        action: str,
        side: str,
        op: Callable[[BedChild], Coroutine[Any, Any, None]],
        *,
        cancel_running: bool = True,
        resource: str | None = None,
        resources: Collection[str] | None = None,
        expected_pair_generations: Mapping[str, tuple[int, ...]] | None = None,
        expected_stop_epochs: Mapping[str, int] | None = None,
    ) -> None:
        if resource is not None and resources is not None:
            raise ValueError("Pass resource or resources, not both")
        command_scope = (
            command_resources(*resources)
            if resources is not None
            else command_resources(resource or "*")
        )
        topology = self._topology
        targets = topology.targets_for(side)
        target_sides = [target_side for target_side, _ in targets]
        topology.check_admission(targets)

        admission = self._admission
        if expected_pair_generations is not None and any(
            expected_pair_generations.get(target_side)
            != admission.generation(target_side, command_scope)
            for target_side in target_sides
        ):
            return
        if not admission.stop_epochs_match(targets, expected_stop_epochs):
            return

        # Preempt: invalidate any OLDER movement still queued on a lane AND
        # cancel the in-flight command on THIS command's own target sides, so a
        # reverse wins instead of waiting out the pulse window or letting a stale
        # queued movement run first. Both the cancel and the counter bump are
        # per-side — a left command must not abort or invalidate an independent
        # right movement (and vice versa).
        if cancel_running:
            for target_side in target_sides:
                admission.bump(target_side, command_scope)
            target_children = {child for _, child in targets}
            # The topology decides whether an overlapping active group or cycle
            # is preempted as a whole or left to finish while this one waits.
            if any(
                child in target_children for child in admission.active_children
            ) and topology.preempts_active(command_scope):
                cancel_scope = admission.active_group_resources or command_scope
                for child in list(admission.active_children):
                    child.request_command_cancel(resources=cancel_scope)
        entry_cancel = {s: admission.generation(s, command_scope) for s in target_sides}

        try:
            await topology.run(
                action,
                targets,
                op,
                cancel_running=cancel_running,
                resources=command_scope,
                entry_cancel=entry_cancel,
                expected_stop_epochs=expected_stop_epochs,
            )
        except ConnectionModeChanged:
            # Queued in concurrent mode, admitted after automatic fallback: run
            # on the one-link path with the STOP ownership captured above.
            if len(targets) > 1 and linked_readiness_required(targets):
                raise ValueError(
                    "This linked profile requires concurrent ready physical receivers"
                ) from None
            if self._sequential is None:
                raise
            await self._sequential.run(
                action,
                targets,
                op,
                cancel_running=cancel_running,
                resources=command_scope,
                entry_cancel=entry_cancel,
                expected_stop_epochs=expected_stop_epochs,
            )

    async def async_stop_command(self, *, side: str = SIDE_BOTH) -> None:
        """Stop the targeted side(s); never let one side's failure skip another."""
        targets = self._targets_for(side)
        # Bump EVERY targeted side's counter first so a movement still queued on
        # a lane for that side drops instead of starting after this stop,
        # including a side that gets no STOP frame below.
        for target_side, _ in targets:
            self._admission.bump(target_side, command_resources("*"))
        # A Remacro side without a global STOP frame only has its running
        # movement cancelled, which sends that axis's release STOP; it is never
        # reconnected for a frame it cannot take.
        for _target_side, child in targets:
            if remacro_side_lacks_global_stop(child):
                child.request_command_cancel()
        targets = [
            (target_side, child)
            for target_side, child in targets
            if not remacro_side_lacks_global_stop(child)
        ]
        async with self._connection_mode_transition_lock:
            errors = await self._stop_children(targets)
        if errors:
            raise PairedSideError("stop", errors)

    async def _stop_children(self, targets: list[PairTarget]) -> dict[str, BaseException]:
        """Send STOP through the current topology's fan-out, collecting failures."""
        return await self._topology.stop_children(targets)

    async def async_stop_motor(
        self,
        stop_fn: CommandFn,
        resource: str,
        *,
        side: str,
        stream_member: bool = True,
    ) -> None:
        """Stop one motor on the side(s) at once, never behind another motor (#516).

        Like a side STOP, this bypasses the side lanes: on each receiver it
        pre-empts the motion holding that side's writer, then runs ``stop_fn``.
        """
        del stream_member  # paired topologies never stream
        targets = self._targets_for(side)
        # A movement for this motor still queued on a side lane drops.
        for target_side, _ in targets:
            self._admission.bump(target_side, command_resources(resource))
        async with self._connection_mode_transition_lock:
            errors = await self._topology.stop_motor(targets, stop_fn, resource)
        if errors:
            raise PairedSideError("stop", errors)

    # ------------------------------------------------------------------ lifecycle
    async def async_connect(self) -> bool:
        """Connect children that are ready for ordinary control."""
        return await self._async_connect_children()

    async def _async_connect_children(self, *, started_local_sides: Collection[str] = ()) -> bool:
        """Connect children, retaining local servers explicitly started by setup."""
        return await self._topology.connect_children(started_local_sides=started_local_sides)

    async def async_disconnect(self, reason: str = "intentional") -> None:
        await asyncio.gather(
            *(child.async_disconnect(reason) for child in self._children.values()),
            return_exceptions=True,
        )

    async def async_shutdown(self) -> None:
        for unsub in self._child_unsubs:
            unsub()
        self._child_unsubs.clear()
        local_children: list[BedChild] = []
        central_children: list[BedChild] = []
        for child in self._children.values():
            controller = child.controller or child.capability_controller
            if controller is not None and controller.requires_disconnected_transport:
                local_children.append(child)
            else:
                central_children.append(child)
        # Setup starts local servers in side order; unwind their adapter/profile
        # ownership in reverse, including when a later child's startup fails.
        for child in reversed(local_children):
            try:
                await child.async_shutdown()
            except Exception:
                _LOGGER.exception("Could not shut down paired local transport")
        await asyncio.gather(
            *(child.async_shutdown() for child in central_children),
            return_exceptions=True,
        )

    def consume_internal_entry_update(self, entry: ConfigEntry) -> bool:
        """Let the side that changed bond state claim the parent entry update.

        A separate-address pair persists a child's runtime bond markers by
        updating the one real parent entry. The update listener therefore sees
        this wrapper, not the child that armed the internal-update marker.
        Forwarding the check prevents a successful verification or confirmed
        removal from unnecessarily reloading and disconnecting both sides.
        """
        # Each parent write queues its own listener invocation. Consume exactly
        # one marker per pass so concurrent child writes can each claim theirs.
        return any(
            child.consume_internal_entry_update(entry)
            for child in self._children.values()
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


class SingleAddressSideCoordinator(EntityRuntimeView):
    """Logical left/right coordinator view over one physical BLE coordinator."""

    def __init__(
        self,
        inner: AdjustableBedCoordinator,
        side: str,
        hydration_owner: SingleAddressPairedCoordinator,
    ) -> None:
        self._single_inner = inner
        self._single_side = side
        self._single_hydration_owner = hydration_owner
        self._single_position_data: dict[str, float] = {}
        self._single_position_callbacks: set[Callable[[dict[str, float]], None]] = set()
        self._single_unregister_position_callback: Callable[[], None] | None = None
        # CB24 shares axes; Sleep Number reports explicitly side-owned axes.
        if inner.bed_type in {BED_TYPE_OKIN_CB24, BED_TYPE_SLEEP_NUMBER}:
            self._single_unregister_position_callback = inner.register_position_callback(
                lambda _positions: self._sync_position_state()
            )

    @property
    def _entity_source(self) -> EntityRuntime:
        return self._single_inner

    def async_command_operation_guard(self) -> contextlib.AbstractAsyncContextManager[None]:
        return self._single_inner.async_command_operation_guard()

    def async_connection_operation_guard(
        self,
    ) -> contextlib.AbstractAsyncContextManager[
        Callable[[str], Coroutine[object, object, bool]]
    ]:
        return self._single_inner.async_connection_operation_guard()

    def cache_capability_controller(self) -> None:
        return self._single_inner.cache_capability_controller()

    def consume_internal_entry_update(self, entry: ConfigEntry) -> bool:
        return self._single_inner.consume_internal_entry_update(entry)

    async def async_connect(self) -> bool:
        return await self._single_inner.async_connect()

    async def async_shutdown(self) -> None:
        return await self._single_inner.async_shutdown()

    async def async_wait_prepared_command(self, handle: CommandHandle) -> None:
        return await self._single_inner.async_wait_prepared_command(handle)

    def commit_prepared_command(self, handle: CommandHandle) -> None:
        return self._single_inner.commit_prepared_command(handle)

    async def async_wait_prepared_command_result(self, handle: CommandHandle) -> None:
        return await self._single_inner.async_wait_prepared_command_result(handle)

    async def async_abort_prepared_command(self, handle: CommandHandle) -> None:
        return await self._single_inner.async_abort_prepared_command(handle)

    @property
    def command_timing(self) -> dict[str, object]:
        return self._single_inner.command_timing

    def get_max_angle(self, motor: str) -> float:
        return self._single_inner.get_max_angle(motor)

    @property
    def observed_ble_device_name(self) -> str | None:
        return self._single_inner.observed_ble_device_name

    @property
    def client(self) -> BleakClient | None:
        return self._single_inner.client

    @property
    def pairing_supported(self) -> bool | None:
        return self._single_inner.pairing_supported

    @property
    def connection_history(self) -> dict[str, object]:
        return self._single_inner.connection_history

    @property
    def pairing_diagnostics(self) -> dict[str, object]:
        return self._single_inner.pairing_diagnostics

    @property
    def adapter_details(self) -> dict[str, object]:
        return self._single_inner.adapter_details

    @property
    def command_trace(self) -> list[dict[str, object]]:
        return self._single_inner.command_trace

    @property
    def connection_attempt_details(self) -> list[dict[str, object]]:
        return self._single_inner.connection_attempt_details

    @property
    def connection_attempt_count(self) -> int:
        return self._single_inner.connection_attempt_count

    def pause_disconnect_timer(self) -> None:
        return self._single_inner.pause_disconnect_timer()

    def hold_command_connection(self) -> contextlib.AbstractContextManager[None]:
        return self._single_inner.hold_command_connection()

    def resume_disconnect_timer(self) -> None:
        return self._single_inner.resume_disconnect_timer()

    async def async_start_notify_for_diagnostics(self) -> None:
        return await self._single_inner.async_start_notify_for_diagnostics()

    def set_raw_notify_callback(self, callback: Callable[[str, bytes], None] | None) -> None:
        return self._single_inner.set_raw_notify_callback(callback)

    def __hash__(self) -> int:
        return hash(id(self._single_inner))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SingleAddressSideCoordinator) and (
            self._single_inner is other._single_inner
        )

    @property
    def side(self) -> str:
        return self._single_side

    @property
    def entity_side(self) -> str:
        """Logical side exposed to entity state and the Lovelace card."""
        return self._single_side

    @property
    def operation_identity(self) -> int:
        """Shared key used by preflight plans for left/right/native-both views."""
        return id(self._single_inner)

    @property
    def stop_epoch(self) -> int:
        return self._single_inner.stop_epoch

    @property
    def pairlink_peripheral(self) -> bool:
        return self._single_inner.pairlink_peripheral

    @property
    def position_data(self) -> dict[str, float]:
        return dict(self._single_position_data)

    def _sync_position_state(self) -> None:
        if self._single_inner.bed_type in {BED_TYPE_KEESON, BED_TYPE_ERGOMOTION}:
            # Legacy P1 feedback cannot identify which half reported a position.
            return
        positions = self._single_inner.position_data
        if self._single_inner.bed_type == BED_TYPE_SLEEP_NUMBER:
            prefix = f"{self._single_side}_"
            positions = {
                key.removeprefix(prefix): value
                for key, value in positions.items()
                if key.startswith(prefix)
            }
        if positions == self._single_position_data:
            return
        self._single_position_data.clear()
        self._single_position_data.update(positions)
        for callback_fn in list(self._single_position_callbacks):
            callback_fn(dict(self._single_position_data))

    def _unregister_inner_position_callback(self) -> None:
        """Release the physical coordinator's position relay."""
        unregister = self._single_unregister_position_callback
        if unregister is not None:
            unregister()
            self._single_unregister_position_callback = None

    def register_position_callback(
        self, callback_fn: Callable[[dict[str, float]], None]
    ) -> Callable[[], None]:
        self._single_position_callbacks.add(callback_fn)
        if self._single_position_data:
            callback_fn(dict(self._single_position_data))

        def unregister() -> None:
            self._single_position_callbacks.discard(callback_fn)

        return unregister

    @property
    def controller(self) -> BedController | None:
        return self._single_inner.controller

    @property
    def capability_controller(self) -> BedController | None:
        return self._single_inner.capability_controller

    @property
    def controller_side(self) -> str:
        """Logical side bound to calls on the shared controller."""
        return self._single_side

    def entity_unique_id(self, key: str) -> str:
        suffix = f"_{self._single_side}"
        sided_key = key if key.endswith(suffix) else f"{key}{suffix}"
        return f"{self._single_inner.address}_{sided_key}"

    def _scoped_command_resources(
        self,
        resource: str | None = None,
        resources: Collection[str] | None = None,
    ) -> frozenset[str]:
        """Namespace scheduler resources by logical side on the shared link."""
        if resource is not None and resources is not None:
            raise ValueError("Pass resource or resources, not both")
        raw_resources = (
            command_resources(*resources)
            if resources is not None
            else command_resources(resource or "*")
        )
        sides = PAIR_SIDES if self._single_side == SIDE_BOTH else (self._single_side,)
        return frozenset(
            f"side:{side}:{item}" for side in sides for item in raw_resources
        )

    def request_command_cancel(
        self,
        resource: str | None = None,
        *,
        resources: Collection[str] | None = None,
    ) -> None:
        """Cancel only this logical side's resources on the shared scheduler."""
        self._single_inner.request_command_cancel(
            resources=self._scoped_command_resources(resource, resources)
        )

    async def async_prepare_command_operation(
        self,
        operation: Callable[[], Coroutine[Any, Any, None]],
        *,
        resource: str | None = None,
        resources: Collection[str] | None = None,
        **kwargs: Any,
    ) -> CommandHandle:
        """Reserve this logical side without colliding with the other side."""
        return await self._single_inner.async_prepare_command_operation(
            operation,
            resources=self._scoped_command_resources(resource, resources),
            **kwargs,
        )

    async def async_execute_controller_command(
        self,
        command_fn: CommandFn,
        cancel_running: bool = True,
        skip_disconnect: bool = False,
        *,
        resource: str | None = None,
        resources: Collection[str] | None = None,
        pulse_count: int | None = None,
        pulse_delay_ms: int | None = None,
        group_id: str | None = None,
        kind: CommandKind = CommandKind.COMMAND,
        read_positions_after_operation: bool = True,
        expected_stop_epoch: int | None = None,
        lease: HoldLease | None = None,
    ) -> None:
        side_feedback = self._single_inner.bed_type == BED_TYPE_SLEEP_NUMBER

        async def bound(controller: BedController) -> None:
            with controller.side_scope(self._single_side):
                await command_fn(controller)
                if (
                    side_feedback
                    and not self._single_inner.disable_angle_sensing
                    and not self._single_inner.cancel_command.is_set()
                ):
                    # Read under the same command lock and side binding. An unbound
                    # background read would query the default side after this returns.
                    await self._single_inner._async_read_positions(controller)

        if side_feedback:
            read_positions_after_operation = False
        await self._single_inner.async_execute_controller_command(
            bound,
            cancel_running=cancel_running,
            skip_disconnect=skip_disconnect,
            pulse_count=pulse_count,
            pulse_delay_ms=pulse_delay_ms,
            group_id=group_id,
            kind=kind,
            read_positions_after_operation=read_positions_after_operation,
            expected_stop_epoch=expected_stop_epoch,
            resources=self._scoped_command_resources(resource, resources),
            lease=lease,
        )
        self._sync_position_state()

    def claim_hold_lease(
        self,
        lease: HoldLease,
        *,
        resource: str | None = None,
        resources: Collection[str] | None = None,
        reserve: bool = True,
    ) -> HoldClaim:
        """Claim a hold lease on this logical side's resources."""
        return self._single_inner.claim_hold_lease(
            lease, resources=self._scoped_command_resources(resource, resources), reserve=reserve
        )

    def release_hold_claim(
        self,
        lease: HoldLease,
        *,
        resource: str | None = None,
        resources: Collection[str] | None = None,
    ) -> None:
        """End this logical side's unadmitted hold reservation."""
        self._single_inner.release_hold_claim(
            lease, resources=self._scoped_command_resources(resource, resources)
        )

    async def async_execute_command_group(
        self,
        operations: Collection[Callable[[], Coroutine[Any, Any, None]]],
        *,
        resources: Collection[str],
        **kwargs: Any,
    ) -> None:
        """Run a logical-side command group on side-scoped resources."""
        await self._single_inner.async_execute_command_group(
            operations,
            resources=self._scoped_command_resources(resources=resources),
            **kwargs,
        )

    async def async_execute_controller_query[T](
        self, query_fn: Callable[[BedController], Coroutine[object, object, T]],
        cancel_running: bool = False, skip_disconnect: bool = False,
        preemptible: bool = True, run_if: Callable[[], bool] | None = None,
    ) -> T:
        async def bound(controller: BedController) -> T:
            with controller.side_scope(self._single_side):
                return await query_fn(controller)

        result = await self._single_inner.async_execute_controller_query(
            bound, cancel_running, skip_disconnect, preemptible, run_if
        )
        self._sync_position_state()
        return result

    async def async_seek_position(
        self,
        position_key: str,
        target_angle: float,
        move_up_fn: CommandFn,
        move_down_fn: CommandFn,
        move_stop_fn: CommandFn,
    ) -> None:
        controller = self.capability_controller
        direct = False
        if controller is not None:
            with controller.side_scope(self._single_side):
                direct = controller.supports_direct_position_control
        if direct:

            async def set_direct(bound: BedController) -> None:
                native = bound.angle_to_native_position(position_key, target_angle)
                await bound.set_motor_position(position_key, native)
                self._single_inner._record_seek_result(
                    SeekResult(
                        position_key=f"{self._single_side}:{position_key}",
                        target=target_angle,
                        outcome=SeekOutcome.DIRECT_SET,
                        final_angle=None,
                        final_direction=None,
                        duration=0.0,
                    )
                )

            await self.async_execute_controller_command(
                set_direct,
                resource=f"motor:{position_key}",
            )
            return

        def bind(fn: CommandFn) -> CommandFn:
            async def bound(controller: BedController) -> None:
                with controller.side_scope(self._single_side):
                    await fn(controller)

            return bound

        await self._single_inner.async_seek_position(
            position_key,
            target_angle,
            bind(move_up_fn),
            bind(move_down_fn),
            bind(move_stop_fn),
            resources=self._scoped_command_resources(
                resource=f"motor:{position_key}"
            ),
        )
        self._sync_position_state()

    async def async_read_initial_positions(self) -> None:
        if self._single_inner.disable_angle_sensing:
            return

        async def read(controller: BedController) -> None:
            with controller.side_scope(self._single_side):
                await controller.prepare_for_position_read()
                await controller.read_positions(self._single_inner.motor_count)

        await self._single_inner.async_execute_controller_query(
            read, skip_disconnect=True
        )
        self._sync_position_state()

    async def async_pause_position_hydration(self) -> None:
        """Pause both physical and logical hydration through the paired owner."""
        await self._single_hydration_owner.async_pause_position_hydration()

    def resume_position_hydration(self) -> None:
        """Resume both physical and logical hydration through the paired owner."""
        self._single_hydration_owner.resume_position_hydration()

    async def async_stop_command(
        self, *, cancel_running: bool = True, **_kwargs: Any
    ) -> None:
        gesture_release = CONTROLLER_GESTURE_RELEASE.get()
        if cancel_running:
            self.request_command_cancel()

        async def stop(controller: BedController) -> None:
            # This STOP can run in a scheduler worker created by an older call.
            token = CONTROLLER_GESTURE_RELEASE.set(gesture_release)
            try:
                with controller.side_scope(self._single_side):
                    await controller.stop_all()
            finally:
                CONTROLLER_GESTURE_RELEASE.reset(token)

        await self._single_inner.async_execute_controller_command(
            stop,
            cancel_running=False,
            resources=self._scoped_command_resources(),
            kind=CommandKind.STOP,
        )

    async def async_stop_motor(
        self, stop_fn: CommandFn, resource: str, *, stream_member: bool = True
    ) -> None:
        """Stop one motor of this side at once (#516).

        Both sides share the receiver's scheduler, so this is a queued STOP: it
        pre-empts this side's motion only, never the other side's, and leaves
        the shared STOP epoch alone.
        """
        del stream_member  # one-address sides never stream
        await self.async_execute_controller_command(
            stop_fn, resource=resource, kind=CommandKind.STOP
        )


class SingleAddressPairedCoordinator(PairedBedCoordinator):
    """Paired surface backed by one coordinator and one physical BLE link."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        inner: AdjustableBedCoordinator,
    ) -> None:
        self._single_inner = inner
        self._single_native_both = entry.data.get(CONF_BED_TYPE) not in {BED_TYPE_SLEEP_NUMBER, BED_TYPE_MOTOMOTION}
        if entry.data.get(CONF_BED_TYPE) == BED_TYPE_GMMOTOR:
            from .gmmotor_profiles import load_profile

            # Some exact products admit left/right but no native Both choice.
            # The parent then runs the two admitted side frames on one link.
            self._single_native_both = 2 in load_profile(entry.data.get(CONF_PRODUCT_TYPE, "")).sides
        if entry.data.get(CONF_BED_TYPE) == BED_TYPE_GOODVIBE:
            from .goodvibe_catalog import PRODUCTS

            product = PRODUCTS.get(entry.data.get(CONF_PROTOCOL_VARIANT, ""))
            self._single_native_both = product is not None and 2 in product.sides
        self._single_position_hydration_task: asyncio.Task[None] | None = None
        self._single_position_hydration_pause_count = 0
        children = {
            SIDE_LEFT: SingleAddressSideCoordinator(inner, SIDE_LEFT, self),
            SIDE_RIGHT: SingleAddressSideCoordinator(inner, SIDE_RIGHT, self),
        }
        self._single_both = SingleAddressSideCoordinator(inner, SIDE_BOTH, self)
        self._single_side_coordinators = (*children.values(), self._single_both)
        super().__init__(
            hass,
            entry,
            children,
            connection_mode=PAIR_CONNECTION_MODE_CONCURRENT,
        )

    @property
    def is_connected(self) -> bool:
        return self._single_inner.is_connected

    @property
    def device_info(self) -> DeviceInfo:
        return self._single_inner.device_info

    def entity_unique_id(self, key: str) -> str:
        return f"{self._single_inner.address}_{key}"

    def _build_topologies(self) -> tuple[SingleLinkSideAwareTopology, None]:
        return SingleLinkSideAwareTopology(self, native_both=self._single_native_both), None

    async def async_connect(self) -> bool:
        return await self._single_inner.async_connect()

    def _on_child_connection_change(self, connected: bool) -> None:
        super()._on_child_connection_change(connected)
        if not connected:
            task = self._single_position_hydration_task
            if task is not None and not task.done():
                task.cancel()
            return
        if self._single_inner.bed_type != BED_TYPE_SLEEP_NUMBER:
            return
        self._schedule_single_position_hydration()

    def _schedule_single_position_hydration(self) -> None:
        """Refresh logical sides unless diagnostics currently own the BLE link."""
        if self._single_position_hydration_pause_count:
            return
        previous_task = self._single_position_hydration_task
        if previous_task is not None and not previous_task.done():
            previous_task.cancel()
        else:
            previous_task = None
        self._single_position_hydration_task = self.entry.async_create_background_task(
            self.hass,
            self._async_hydrate_logical_positions(previous_task),
            name=f"adjustable_bed_single_address_position_hydration_{self.entry.entry_id}",
        )

    async def _async_hydrate_logical_positions(
        self, previous_task: asyncio.Task[None] | None = None
    ) -> None:
        """Refresh each logical side without mixing same-named position axes."""
        current_task = asyncio.current_task()
        retry_after_preemption = False
        try:
            if previous_task is not None:
                try:
                    await previous_task
                except asyncio.CancelledError:
                    if current_task is not None and current_task.cancelling():
                        raise
            # The inner coordinator schedules an unbound read during connect.
            # Replace it with side-bound reads for protocols whose two logical
            # sides report the same axis names.
            await self._single_inner._async_cancel_position_hydration()
            if current_task is not None and current_task.cancelling():
                raise asyncio.CancelledError
            results = await asyncio.gather(
                *(
                    child.async_read_initial_positions()
                    for child in self._children.values()
                ),
                return_exceptions=True,
            )
            for side, result in zip(self._children, results, strict=True):
                if isinstance(result, asyncio.CancelledError):
                    retry_after_preemption = True
                if isinstance(result, BaseException):
                    _LOGGER.debug(
                        "Single-address position hydration failed for %s side: %s",
                        side,
                        result,
                    )
        finally:
            if self._single_position_hydration_task is current_task:
                self._single_position_hydration_task = None
            if (
                retry_after_preemption
                and (current_task is None or not current_task.cancelling())
                and not self._single_position_hydration_pause_count
                and self._single_inner.is_connected
                and self._single_inner.bed_type == BED_TYPE_SLEEP_NUMBER
            ):
                self._schedule_single_position_hydration()

    async def _async_cancel_single_position_hydration(self) -> None:
        """Cancel and await logical-side hydration."""
        task = self._single_position_hydration_task
        try:
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    current_task = asyncio.current_task()
                    if current_task is not None and current_task.cancelling():
                        raise
        finally:
            if self._single_position_hydration_task is task:
                self._single_position_hydration_task = None

    async def async_pause_position_hydration(self) -> None:
        """Pause physical and logical hydration during diagnostics."""
        self._single_position_hydration_pause_count += 1
        await self._single_inner.async_pause_position_hydration()
        await self._async_cancel_single_position_hydration()

    def resume_position_hydration(self) -> None:
        """Resume physical and logical hydration after diagnostics."""
        if self._single_position_hydration_pause_count == 0:
            return
        self._single_position_hydration_pause_count -= 1
        self._single_inner.resume_position_hydration()
        if (
            self._single_position_hydration_pause_count == 0
            and self._single_inner.is_connected
            and self._single_inner.bed_type == BED_TYPE_SLEEP_NUMBER
        ):
            self._schedule_single_position_hydration()

    async def async_disconnect(self, reason: str = "intentional") -> None:
        await self._single_inner.async_disconnect(reason)

    @contextlib.asynccontextmanager
    async def async_transport_operation(self, operation: str) -> AsyncIterator[None]:
        """Hold the one physical link still for a whole transport operation.

        This surface keeps the entry's own address, so it is offered the bond
        actions. The locks and the link both live on the inner coordinator, so
        the gate has to be its gate rather than a second one that guards
        nothing.
        """
        async with self._single_inner.async_transport_operation(operation):
            yield

    def apply_confirmed_bond_removal(self) -> None:
        """Clear the bond state held by the coordinator that owns the link."""
        self._single_inner.apply_confirmed_bond_removal()

    def begin_internal_bond_update(
        self,
        bond_established: bool,
        *,
        marker_unreliable: bool | None = None,
    ) -> None:
        """Tag the next bond write on the coordinator that owns the link."""
        self._single_inner.begin_internal_bond_update(
            bond_established,
            marker_unreliable=marker_unreliable,
        )

    async def async_shutdown(self) -> None:
        # Suppress reconnect-driven hydration before awaiting cancellation:
        # connection callbacks can otherwise replace the task being drained.
        self._single_position_hydration_pause_count += 1
        for unsub in self._child_unsubs:
            unsub()
        self._child_unsubs.clear()
        try:
            await self._async_cancel_single_position_hydration()
        finally:
            try:
                # Also drain any task queued by a callback that was already in
                # flight when shutdown disabled future scheduling.
                await self._async_cancel_single_position_hydration()
            finally:
                for side_coordinator in self._single_side_coordinators:
                    side_coordinator._unregister_inner_position_callback()
                await self._single_inner.async_shutdown()

    def _wire_child_connection_callbacks(self) -> None:
        self._child_unsubs.append(
            self._single_inner.register_connection_state_callback(
                self._on_child_connection_change
            )
        )


class PairedSideProxy(EntityRuntimeView):
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
        child: BedChild,
        side: str,
    ) -> None:
        """Wrap ``child`` (on ``side``) with writes routed through ``parent``."""
        self._pair_parent = parent
        self._pair_child = child
        self._pair_side = side

    @property
    def _entity_source(self) -> EntityRuntime:
        return self._pair_child

    @property
    def device_info(self) -> ChildDeviceInfo:
        return child_device_info(self._pair_parent, self._pair_side)

    @property
    def entity_side(self) -> str:
        return self._pair_side

    async def async_execute_controller_command(
        self, command_fn: ControllerCommand, *, cancel_running: bool = True,
        skip_disconnect: bool = False, resource: str | None = None,
        resources: Collection[str] | None = None,
    ) -> None:
        """Route entity commands through the parent safety contract."""
        await self._pair_parent.async_execute_controller_command(
            command_fn, side=self._pair_side, cancel_running=cancel_running,
            skip_disconnect=skip_disconnect, resource=resource, resources=resources,
        )

    async def async_seek_position(
        self, position_key: str, target_angle: float,
        move_up_fn: ControllerCommand, move_down_fn: ControllerCommand,
        move_stop_fn: ControllerCommand,
    ) -> None:
        await self._pair_parent.async_seek_position(
            position_key, target_angle, move_up_fn, move_down_fn, move_stop_fn,
            side=self._pair_side,
        )

    async def async_stop_command(self) -> None:
        await self._pair_parent.async_stop_command(side=self._pair_side)

    async def async_stop_motor(
        self, stop_fn: ControllerCommand, resource: str, *, stream_member: bool = True
    ) -> None:
        await self._pair_parent.async_stop_motor(
            stop_fn, resource, side=self._pair_side, stream_member=stream_member
        )


def entity_runtimes(
    coordinator: AdjustableBedCoordinator | PairedBedCoordinator,
) -> tuple[EntityRuntime, ...]:
    """Build entity views with the same identity and routing on every platform."""
    if isinstance(coordinator, PairedBedCoordinator):
        return tuple(
            PairedSideProxy(coordinator, child, side)
            for side, child in coordinator.children.items()
        )
    return (coordinator,)
