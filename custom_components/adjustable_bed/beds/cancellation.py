"""Awaiting work that must finish, or stop, around a cancellation."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine


async def settled[T](operation: Coroutine[object, object, T], *, eager_start: bool | None = None) -> T:
    """Finish ``operation`` even when the caller is cancelled meanwhile, then re-raise.

    An in-flight write or release completes before cancellation can hand its
    wire lane to STOP. A failure of the operation itself takes precedence.
    ``eager_start`` lets safety work reserve its lane before this caller yields.
    """
    task = asyncio.create_task(operation, eager_start=eager_start)
    interrupted: asyncio.CancelledError | None = None
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError as err:
            interrupted = err
    result = task.result()
    if interrupted is not None:
        raise interrupted
    return result


async def cancellable[T](operation: Coroutine[object, object, T], event: asyncio.Event | None) -> T:
    """Await ``operation`` unless ``event`` is set first; then cancel it and raise."""
    if event is None:
        return await operation
    if event.is_set():
        operation.close()
        raise asyncio.CancelledError
    task = asyncio.create_task(operation)
    cancellation = asyncio.create_task(event.wait())
    try:
        done, _ = await asyncio.wait((task, cancellation), return_when=asyncio.FIRST_COMPLETED)
        if cancellation in done:
            raise asyncio.CancelledError
        return task.result()
    finally:
        for pending in (task, cancellation):
            if not pending.done():
                pending.cancel()
        await asyncio.gather(task, cancellation, return_exceptions=True)
