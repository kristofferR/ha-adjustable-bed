"""Guard the bytes every bed controller writes to the wire.

``scripts/wire_snapshot.py`` drives each bed type, protocol variant and app
profile route through the real controller factory and records the characteristic,
bytes, write mode, order and virtual timing of each write. The committed snapshot
is the contract for the v5 protocol-split refactors (#742): a refactor that moves
code between codecs and profiles must keep this test green without touching the
snapshot. A deliberate wire change (a bug fix) regenerates it in the same PR:

    uv run --no-sync python scripts/wire_snapshot.py
"""

from __future__ import annotations

import asyncio
import difflib
import importlib.util
import logging
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "wire_snapshot.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("wire_snapshot", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_wire_bytes_match_committed_snapshot() -> None:
    tool = _load_tool()
    logging.disable(logging.CRITICAL)
    try:
        fresh = tool.render(asyncio.run(tool.capture_all()))
    finally:
        logging.disable(logging.NOTSET)
    committed = tool.SNAPSHOT_PATH.read_text()
    if fresh != committed:
        diff = difflib.unified_diff(
            committed.splitlines(), fresh.splitlines(), "committed", "fresh", n=0, lineterm=""
        )
        shown = [line[:240] for _, line in zip(range(20), diff, strict=False)]
        raise AssertionError(
            "Bytes on the wire changed. Review the diff, and if the change is deliberate "
            "regenerate with `uv run --no-sync python scripts/wire_snapshot.py`:\n"
            + "\n".join(shown)
        )


async def test_virtual_clock_orders_sleeps_and_timeouts() -> None:
    """Timeouts fire at their own deadline, after runnable work, and sleeps wake in order."""
    tool = _load_tool()
    clock = tool.FakeClock()
    woke: list[str] = []

    async def sleeper(name: str, delay: float) -> None:
        await asyncio.sleep(delay)
        woke.append(name)

    async def noop() -> None:
        return None

    async def busy_then_return() -> str:
        await asyncio.sleep(0.9)
        await asyncio.gather(*(asyncio.ensure_future(noop()) for _ in range(100)))
        return "done"

    with tool.virtual_time(clock):
        await asyncio.gather(sleeper("late", 0.5), sleeper("early", 0.2))
        assert woke == ["early", "late"]
        assert clock.now == 0.5

        # Runnable work inside the body must not trigger the timeout.
        assert await asyncio.wait_for(busy_then_return(), 1) == "done"
        async with asyncio.timeout(1):
            assert await busy_then_return() == "done"

        # A pending background sleep does not delay a timeout past its own deadline.
        background = asyncio.ensure_future(asyncio.sleep(5))
        start = clock.now
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.sleep(10), 1)
        assert clock.now == start + 1
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(1):
                await asyncio.sleep(10)
        assert clock.now == start + 2
        background.cancel()
