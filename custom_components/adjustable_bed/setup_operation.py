"""Shared state and progress plumbing for slow Bluetooth setup operations.

Locating a bed, connecting to it, discovering its GATT tree, pairing, verifying a
bond and unpairing all take seconds, sometimes tens of seconds. Running them
inline leaves the form the user just submitted sitting there looking frozen, and
a frozen form is indistinguishable from a broken one.

Every such operation therefore runs as a tracked background task behind a Home
Assistant progress view. This module owns what all of those operations share:

* ``SetupAction`` — the vocabulary of phases, one translation key each.
* ``SetupOperationState`` — what the flow is doing, over which transport, how far
  along, and how it ended.
* ``BluetoothOperationMixin`` — the step behaviour.

Three things here are subtle enough to be worth stating outright.

**Progress text versus progress bar.** A numeric bar comes from
``async_update_progress``, which fires an event without re-running the step.
Changing the *label* requires the step to run again and return a different
``progress_action``, so a phase change schedules a re-configure of the flow. Both
patterns come from Home Assistant core (``components/airos`` and
``components/cloud/repairs``).

**Determinate progress is nearly always a lie.** A BLE connect can take 200 ms or
20 s and offers no completion signal, so "phase 2 of 4 = 50%" is invented
precision. Only the advertisement wait, whose duration really is known up front,
drives the bar; every other phase is a spinner with honest status text.

**Completion races.** When the worker finishes, Home Assistant schedules its own
``_async_configure()`` via the progress task's done-callback
(``data_entry_flow.py``). That can land at the same moment as one of our phase
refreshes, so both the terminal transition and the refresh driver are built to be
safe when they overlap: the result is consumed once, and only one refresh is ever
in flight.

**Task identity.** ``ReentrantAddressLock`` keys reentrancy on
``asyncio.current_task()``, so everything for one BLE client's lifetime —
connect, use, disconnect — must happen inside the single worker task. Delegating
part of it to a helper task would block on the lock rather than re-enter it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from homeassistant.core import callback
from homeassistant.data_entry_flow import UnknownFlow

from .bluetooth_transport import ConnectionPath, PathPrediction, TransportClass

if TYPE_CHECKING:
    from bleak import BleakClient
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class SetupAction(StrEnum):
    """A phase of a Bluetooth setup operation, shown while it is running.

    Each value is also the ``progress_action`` translation key, so adding a phase
    means adding a string in every language.
    """

    LOCATING = "locating"
    CONNECTING = "connecting"
    DISCOVERING_SERVICES = "discovering_services"
    READING_CAPABILITIES = "reading_capabilities"
    PAIRING = "pairing"
    VERIFYING_BOND = "verifying_bond"
    VERIFYING_PIN = "verifying_pin"
    DISCONNECTING = "disconnecting"
    UNPAIRING = "unpairing"


class OperationOutcome(StrEnum):
    """How a Bluetooth setup operation ended.

    Deliberately narrower than "it failed": each value maps to different advice,
    and issue #461 requires that a plain connection failure is never presented as
    a pairing failure.
    """

    SUCCESS = "success"
    NOT_ADVERTISING = "not_advertising"
    # The bed *was* advertising, but Home Assistant could not turn that into a
    # connectable device in time. Kept apart from NOT_ADVERTISING so the advice
    # is "try again" rather than "go wake your bed".
    DEVICE_UNRESOLVED = "device_unresolved"
    CONNECTION_FAILED = "connection_failed"
    CONNECTION_IN_USE = "connection_in_use"
    NO_CONNECTION_SLOTS = "no_connection_slots"
    TIMEOUT = "timeout"
    PAIRING_NOT_SUPPORTED = "pairing_not_supported"
    AUTHENTICATION_FAILED = "authentication_failed"
    PIN_VERIFICATION_INCONCLUSIVE = "pin_verification_inconclusive"
    BOND_VERIFICATION_FAILED = "bond_verification_failed"
    # Distinct from a failure: a timeout or an absent characteristic proves
    # neither that a bond exists nor that it does not, and telling a user their
    # link is unauthenticated would push them into replacing a working bond.
    BOND_VERIFICATION_INCONCLUSIVE = "bond_verification_inconclusive"
    PROXY_OWNED_BOND = "proxy_owned_bond"
    UNPAIR_FAILED = "unpair_failed"
    UNPAIR_UNCONFIRMED = "unpair_unconfirmed"
    CANCELLED = "cancelled"


class ConnectionLifetimePolicy(StrEnum):
    """How freely an operation may spend BLE connections to this bed.

    ``KEEP_FIRST_LINK`` marks a bed that grants roughly one usable connection per
    power cycle (LP Comfort Connect / Leggett & Platt Gen2, issue #385). For such
    a bed a throwaway probe or a standalone pairing connect consumes the only
    connection the coordinator was going to get, and reconnecting to "do it
    properly" strands the bed until the user unplugs it. Operations must consult
    this before opening anything.
    """

    ORDINARY = "ordinary"
    KEEP_FIRST_LINK = "keep_first_link"


@dataclass(frozen=True, slots=True)
class OperationResult:
    """The terminal state of one operation."""

    outcome: OperationOutcome
    detail: str | None = None
    path: ConnectionPath | None = None
    payload: Any = None

    @property
    def succeeded(self) -> bool:
        """Return True only for an unambiguous success."""
        return self.outcome is OperationOutcome.SUCCESS


@dataclass
class SetupOperationState:
    """Everything a progress view and its result step need to know."""

    action: SetupAction = SetupAction.LOCATING
    prediction: PathPrediction | None = None
    actual: ConnectionPath | None = None
    progress: float | None = None
    result: OperationResult | None = None
    terminal_consumed: bool = False
    name: str = ""
    address: str = ""
    policy: ConnectionLifetimePolicy = ConnectionLifetimePolicy.ORDINARY
    placeholders: dict[str, str] = field(default_factory=dict)

    @property
    def predicted(self) -> ConnectionPath | None:
        """Return the path Home Assistant was expected to use."""
        return self.prediction.chosen if self.prediction is not None else None

    @property
    def path_changed(self) -> bool:
        """Return True when the connection did not take the predicted path."""
        predicted = self.predicted
        return (
            predicted is not None
            and self.actual is not None
            and predicted.source != self.actual.source
        )

    @property
    def effective_path(self) -> ConnectionPath | None:
        """Return the real path when known, else the prediction."""
        return self.actual or self.predicted

    @property
    def transport(self) -> TransportClass:
        """Return the transport class currently believed to be in use."""
        path = self.effective_path
        return path.transport if path is not None else TransportClass.UNKNOWN


# A worker returns the terminal result for its operation. It must never raise for
# an expected BLE failure — expected failures are outcomes, not exceptions — but
# the mixin still catches anything that escapes so a bug cannot wedge a flow.
OperationWorker = Callable[[], Awaitable[OperationResult]]


class BluetoothOperationMixin:
    """Progress-step behaviour shared by the config, options and repair flows.

    The host class must be a Home Assistant flow handler: this uses ``self.hass``,
    ``self.flow_id``, ``async_show_progress``, ``async_show_progress_done`` and
    ``async_update_progress``.
    """

    _operation: SetupOperationState | None = None
    _operation_task: asyncio.Task[OperationResult] | None = None
    _operation_client: BleakClient | None = None

    if TYPE_CHECKING:
        # Supplied by the flow handler this is mixed into. Declared rather than
        # inherited so the mixin stays usable with ConfigFlow, OptionsFlow and
        # RepairsFlow, which do not share a base that carries these.
        hass: HomeAssistant
        flow_id: str

        def async_update_progress(self, progress: float) -> None: ...

        def async_show_progress(self, **kwargs: Any) -> Any: ...

        def async_show_progress_done(self, *, next_step_id: str) -> Any: ...
    _refresh_task: asyncio.Task[None] | None = None
    _refresh_pending: bool = False

    # -- state ---------------------------------------------------------------

    @property
    def operation(self) -> SetupOperationState:
        """Return the current operation state, creating an empty one if needed."""
        state = self._operation
        if state is None:
            state = SetupOperationState()
            self._operation = state
        return state

    @callback
    def async_begin_operation(
        self,
        *,
        name: str = "",
        address: str = "",
        prediction: PathPrediction | None = None,
        action: SetupAction = SetupAction.LOCATING,
        policy: ConnectionLifetimePolicy = ConnectionLifetimePolicy.ORDINARY,
        placeholders: dict[str, str] | None = None,
    ) -> SetupOperationState:
        """Start a new operation, discarding any state from a previous one.

        Call this when a step is entered with user input — a fresh submission or
        an explicit Retry — never on re-entry while a task is running, which is
        what makes double submits harmless.
        """
        # Defensive: a caller should only start an operation when none is
        # running, but replacing the state while a task still holds a client
        # would orphan both, so tear the old one down first.
        if self._operation_task is not None and not self._operation_task.done():
            self._operation_task.cancel()
        if self._operation_client is not None:
            stray, self._operation_client = self._operation_client, None
            hass = getattr(self, "hass", None)
            if hass is not None:
                hass.async_create_task(_async_disconnect_quietly(stray))
        self._operation = SetupOperationState(
            action=action,
            prediction=prediction,
            name=name,
            address=address,
            policy=policy,
            placeholders=dict(placeholders or {}),
        )
        self._operation_task = None
        self._operation_client = None
        return self._operation

    # -- progress reporting (called from inside the worker) -------------------

    @callback
    def async_report_action(
        self, action: SetupAction, *, progress: float | None = None
    ) -> None:
        """Record the current phase and push it to the frontend.

        ``progress`` should be supplied only where the fraction is genuinely
        measurable. Everything here is best-effort: a UI update must never be
        able to fail the operation it is describing.
        """
        state = self.operation
        changed = state.action is not action
        state.action = action
        if changed:
            # Drop any bar left over from the previous phase. Carrying it would
            # show a full bar through a phase whose duration is unknowable.
            state.progress = None
        if progress is not None:
            state.progress = progress
            with contextlib.suppress(Exception):
                self.async_update_progress(progress)
        if changed:
            self.async_refresh_progress_view()

    @callback
    def async_report_progress(self, progress: float) -> None:
        """Update only the numeric bar, without re-rendering the step."""
        state = self.operation
        state.progress = progress
        with contextlib.suppress(Exception):
            self.async_update_progress(progress)

    @callback
    def async_report_path(self, path: ConnectionPath | None) -> None:
        """Record the transport a connection actually used."""
        if path is None:
            return
        self.operation.actual = path
        self.async_refresh_progress_view()

    @callback
    def async_track_client(self, client: BleakClient | None) -> None:
        """Remember the client an operation opened so cancellation can close it."""
        self._operation_client = client

    # -- refresh driver ------------------------------------------------------

    @callback
    def _async_flow_manager(self) -> Any:
        """Return the flow manager driving this flow.

        Home Assistant does not hand a handler a reference to its own manager,
        and the three managers are distinct objects: config flows, options flows
        and repair flows each have their own. This default is the config-flow
        manager; hosts elsewhere override it.
        """
        hass = getattr(self, "hass", None)
        if hass is None:
            return None
        return hass.config_entries.flow

    @callback
    def async_refresh_progress_view(self) -> None:
        """Ask Home Assistant to re-render the running progress step.

        Coalesced deliberately. Several phases can change in quick succession,
        and each re-configure re-runs the step; letting them pile up would mean
        many concurrent invocations racing each other and the flow manager's own
        completion callback. At most one refresh is ever in flight, and a request
        that arrives while one is running just marks the next round.
        """
        hass = getattr(self, "hass", None)
        if hass is None or not getattr(self, "flow_id", None):
            return
        if self._refresh_task is not None and not self._refresh_task.done():
            self._refresh_pending = True
            return
        self._refresh_pending = False
        self._refresh_task = hass.async_create_task(self._async_refresh_loop())

    async def _async_refresh_loop(self) -> None:
        """Re-configure the flow until no further refresh has been requested."""
        manager = self._async_flow_manager()
        flow_id = getattr(self, "flow_id", None)
        if manager is None or not flow_id:
            return
        while True:
            self._refresh_pending = False
            try:
                await manager.async_configure(flow_id=flow_id)
            except UnknownFlow:
                # The user closed the dialog while we were mid-phase. Nothing to
                # update, and nothing worth logging.
                return
            except Exception:  # noqa: BLE001 - a redraw must never break the flow
                _LOGGER.debug("Could not refresh the setup progress view", exc_info=True)
                return
            if not self._refresh_pending:
                return

    # -- the progress step ---------------------------------------------------

    async def async_run_operation_step(
        self,
        *,
        step_id: str,
        worker: OperationWorker,
        next_step_id: str,
        description_placeholders: dict[str, str] | None = None,
    ) -> Any:
        """Render a progress view for ``worker``, then hand off to a result step.

        Returns ``Any`` rather than ``FlowResult`` because the three host flows
        each have their own narrower result type (``ConfigFlowResult`` and
        friends); the type is checked where it matters, at the step that returns
        it.

        Re-entering while the task runs returns the same task rather than
        starting a second one, so a double submit, a frontend reconnect and a
        phase refresh cannot open two BLE connections. Completion transitions to
        ``next_step_id`` once and only once, whether the worker succeeded, failed
        or raised.
        """
        state = self.operation

        if self._operation_task is None and not state.terminal_consumed:
            self._operation_task = self.hass.async_create_task(
                self._async_guarded_worker(worker),
                eager_start=False,
            )

        task = self._operation_task
        if task is not None and not task.done():
            return self.async_show_progress(
                step_id=step_id,
                progress_action=state.action.value,
                progress_task=task,
                description_placeholders={
                    **state.placeholders,
                    **(description_placeholders or {}),
                },
            )

        if task is not None:
            # Read the result exactly once. Home Assistant's own done-callback and
            # a phase refresh can both arrive here; the second one must not try to
            # re-read a task that has already been cleared.
            self._operation_task = None
            state.terminal_consumed = True
            try:
                state.result = task.result()
            except asyncio.CancelledError:
                state.result = OperationResult(outcome=OperationOutcome.CANCELLED)
            except Exception as err:  # noqa: BLE001 - a bug must not wedge the flow
                _LOGGER.exception("Bluetooth setup operation failed unexpectedly")
                state.result = OperationResult(
                    outcome=OperationOutcome.CONNECTION_FAILED,
                    detail=str(err) or err.__class__.__name__,
                )

        return self.async_show_progress_done(next_step_id=next_step_id)

    async def _async_guarded_worker(self, worker: OperationWorker) -> OperationResult:
        """Run a worker, guaranteeing the BLE client is released afterwards."""
        try:
            return await worker()
        finally:
            await self._async_release_client()

    async def _async_release_client(self) -> None:
        """Disconnect any client the operation still holds.

        Shielded so a cancelled flow still completes the disconnect: leaving the
        link open would hold the bed's single BLE connection and block both the
        coordinator and the physical remote.
        """
        client = self._operation_client
        self._operation_client = None
        if client is None:
            return
        with contextlib.suppress(Exception):
            await asyncio.shield(client.disconnect())

    # -- teardown ------------------------------------------------------------

    @callback
    def async_remove(self) -> None:
        """Clean up when the flow is abandoned.

        Home Assistant cancels the registered progress task itself before calling
        this, which runs the worker's own ``finally``. What is left is the
        refresh driver, a task we started but never registered, and a client
        opened outside a running task.
        """
        refresh_task = self._refresh_task
        self._refresh_task = None
        self._refresh_pending = False
        if refresh_task is not None and not refresh_task.done():
            refresh_task.cancel()

        task = self._operation_task
        self._operation_task = None
        if task is not None and not task.done():
            task.cancel()

        client = self._operation_client
        self._operation_client = None
        if client is not None:
            hass = getattr(self, "hass", None)
            if hass is not None:
                # async_remove is a callback and cannot await, so the disconnect
                # is handed to a task of its own.
                hass.async_create_task(_async_disconnect_quietly(client))


async def _async_disconnect_quietly(client: BleakClient) -> None:
    """Disconnect a client, swallowing anything that goes wrong."""
    with contextlib.suppress(Exception):
        await client.disconnect()
