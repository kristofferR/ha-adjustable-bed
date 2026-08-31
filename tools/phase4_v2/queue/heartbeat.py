"""Non-model lease heartbeat loop for a running Phase 4 worker."""

from __future__ import annotations

from collections.abc import Callable
from threading import Event

from .core import Lease, Queue


def run_heartbeat(
    queue: Queue,
    lease: Lease,
    stop: Event,
    *,
    ttl_seconds: int = 1_800,
    interval_seconds: float = 60.0,
    on_renewed: Callable[[Lease], None] | None = None,
) -> Lease:
    """Renew until stopped, without requiring a model or mutating work output."""
    if ttl_seconds < 1:
        raise ValueError("ttl_seconds must be positive")
    if interval_seconds <= 0 or interval_seconds >= ttl_seconds:
        raise ValueError("heartbeat interval must be positive and shorter than the lease TTL")
    current = lease
    while not stop.wait(interval_seconds):
        current = queue.renew(current, ttl_seconds=ttl_seconds)
        if on_renewed is not None:
            on_renewed(current)
    return current
