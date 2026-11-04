"""Guard the bytes every bed controller writes to the wire.

``scripts/wire_snapshot.py`` drives each bed type, protocol variant and app
profile route through the real controller factory and records the characteristic,
bytes, write mode, order and virtual timing of every GATT write, subscription,
read and pairing, on stored GATT layouts. The committed snapshot is the contract
for the v5 protocol-split refactors (#742): a refactor that moves code between
codecs and profiles must keep this test green without touching it. A deliberate wire change (a bug fix) regenerates them in the same PR:

    uv run --no-sync python scripts/wire_snapshot.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import subprocess
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
    # A separate process: the capture must not see this test session's state.
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, (
        "Bytes on the wire changed. Review the diff, and if the change is deliberate "
        "regenerate with `uv run --no-sync python scripts/wire_snapshot.py`:\n"
        + result.stdout[-6000:]
        + result.stderr[-2000:]
    )


async def test_virtual_clock_orders_sleeps_and_timeouts() -> None:
    """Timeouts fire at their own deadline, after runnable work, and sleeps wake in order."""
    tool = _load_tool()
    clock = tool.FakeClock()
    woke: list[str] = []
    real_timeout_at = asyncio.timeout_at

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
        async with asyncio.timeout_at(asyncio.get_running_loop().time() + 1) as budget:
            assert await busy_then_return() == "done"
        assert not budget.expired()
        async with asyncio.timeout_at(None):
            await asyncio.sleep(0.1)

        # An inner timeout that fires first is handled before an outer one can fire.
        inner_fired = False
        async with asyncio.timeout(1):
            try:
                await asyncio.wait_for(asyncio.Event().wait(), 0.08)
            except TimeoutError:
                inner_fired = True
        assert inner_fired

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
        with pytest.raises(TimeoutError):
            async with asyncio.timeout_at(asyncio.get_running_loop().time() + 1) as budget:
                await asyncio.sleep(10)
        assert budget.expired()
        assert clock.now == start + 3

        # ``asyncio.wait`` and ``call_later`` run on the same clock.
        done, pending = await asyncio.wait({asyncio.ensure_future(asyncio.sleep(10))}, timeout=1)
        assert not done and len(pending) == 1 and clock.now == start + 4
        pending.pop().cancel()
        fired: list[float] = []
        asyncio.get_running_loop().call_later(2, lambda: fired.append(clock.now))
        await asyncio.sleep(3)
        assert fired == [start + 6]
        background.cancel()

    assert asyncio.timeout_at is real_timeout_at
