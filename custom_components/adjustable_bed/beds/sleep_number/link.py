"""Fence a SleepIQ transaction and its cleanup to one controller and BLE link."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bleak import BleakClient

from ...command_scheduler import note_frame_skipped
from ..base import BedController
from ..cancellation import settled

if TYPE_CHECKING:
    from ..lifecycle import ControllerSession


class ReplyTimeout(TimeoutError):
    """A completed write received no reply before the protocol deadline."""


async def finish_frame(
    task: asyncio.Task[None],
    started: asyncio.Event,
    *,
    cancellable_before_start: bool = True,
    required: bool = True,
) -> None:
    """Cancel queued control, but finish a buffer whose first write has begun."""
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        if cancellable_before_start and not started.is_set() and not task.done():
            if required:
                note_frame_skipped()
            task.cancel()

        async def collect() -> None:
            await task

        await settled(collect())
        raise


@dataclass(frozen=True, slots=True)
class Link:
    client: BleakClient
    profile: object
    generation: object


@dataclass(slots=True)
class _Operation:
    link: Link
    control_started: bool = False


class SleepIQLink:
    """A replacement controller, profile or connection invalidates old work."""

    def __init__(self) -> None:
        self.generation = object()
        self.session: ControllerSession | None = None
        self._current: Link | None = None
        self._operation: ContextVar[_Operation | None] = ContextVar(
            f"sleepiq_link_{id(self)}", default=None
        )

    def capture(self, controller: BedController, profile: object) -> Link:
        operation = self._operation.get()
        if (link := operation.link if operation else self._current) is not None:
            self.check(controller, profile, link)
            return link
        client = controller.client
        if client is None or not client.is_connected:
            raise ConnectionError("Sleep Number BLE connection ended")
        link = Link(client, profile, self.generation)
        self.check(controller, profile, link)
        self._current = link
        return link

    @contextmanager
    def operation(self, controller: BedController, profile: object) -> Iterator[Link]:
        """Keep every query, control and cleanup of an operation on its original link."""
        link = self.capture(controller, profile)
        token = self._operation.set(self._operation.get() or _Operation(link))
        try:
            yield link
        finally:
            self._operation.reset(token)

    @property
    def control_started(self) -> bool:
        operation = self._operation.get()
        return operation is not None and operation.control_started

    def note_control_started(self) -> None:
        if (operation := self._operation.get()) is not None:
            operation.control_started = True

    def permits_state(self, controller: BedController, profile: object) -> bool:
        if not self.owns(controller):
            return False
        if (operation := self._operation.get()) is not None:
            try:
                self.check(controller, profile, operation.link)
            except ConnectionError:
                return False
        return True

    def check(self, controller: BedController, profile: object, link: Link) -> None:
        owner = controller._coordinator.controller
        if (
            self.generation is not link.generation
            or controller.client is not link.client
            or profile is not link.profile
            or not link.client.is_connected
            or self.session is not None
            and not self.session.is_current()
            or isinstance(owner, BedController)
            and owner is not controller
        ):
            raise ConnectionError("Sleep Number command belongs to an ended BLE session")

    @staticmethod
    def owns(controller: BedController) -> bool:
        owner = controller._coordinator.controller
        return not isinstance(owner, BedController) or owner is controller

    def clear(self) -> Link | None:
        previous = self._current
        self.generation = object()
        self.session = None
        self._current = None
        return previous
