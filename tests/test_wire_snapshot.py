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
import difflib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "wire_snapshot.py"
CAPTURE_PARTS = 4


def _load_tool():
    spec = importlib.util.spec_from_file_location("wire_snapshot", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module", params=("0", "1"))
def wire_catalog(request):
    hash_seed = request.param
    listed = subprocess.run(
        [sys.executable, str(SCRIPT), "--probe", "--list"],
        env={**os.environ, "PYTHONHASHSEED": hash_seed},
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert listed.returncode == 0, listed.stderr
    ids = sorted(listed.stdout.splitlines())
    committed = json.loads((REPO_ROOT / "tests" / "fixtures" / "wire_snapshot.json").read_text())
    assert len(ids) == len(set(ids)), "Duplicate wire scenario ids"
    assert set(ids) == set(committed["scenarios"]), "Wire catalog and committed scenarios differ"
    return hash_seed, ids, committed


@pytest.mark.xdist_group("wire_snapshot")
@pytest.mark.parametrize("part", range(CAPTURE_PARTS))
def test_wire_bytes_match_committed_snapshot(wire_catalog, part: int) -> None:
    # Bound each case's work while covering the entire catalog under each seed.
    hash_seed, ids, committed = wire_catalog
    selected = ids[part::CAPTURE_PARTS]
    assert selected, "Empty wire capture part"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--probe", "--only", *selected],
        env={**os.environ, "PYTHONHASHSEED": hash_seed},
        stdout=subprocess.PIPE,
        stderr=None if os.environ.get("WIRE_SNAPSHOT_VERBOSE") else subprocess.PIPE,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    assert result.returncode == 0, (
        f"Wire capture failed for hash seed {hash_seed}:\n"
        + result.stdout[-6000:]
        + (result.stderr or "")[-2000:]
    )
    scenarios = {sid: committed["scenarios"][sid] for sid in selected}
    used_chars = {
        write[1]
        for scenario in scenarios.values()
        for command in scenario["commands"].values()
        for write in command.get("writes", [])
    }
    expected = {
        "schema": committed["schema"],
        "chars": {key: value for key, value in committed["chars"].items() if key in used_chars},
        "scenarios": scenarios,
    }
    expected_text = json.dumps(expected, sort_keys=True, indent=2)
    fresh_text = json.dumps(json.loads(result.stdout), sort_keys=True, indent=2)
    diff = difflib.unified_diff(
        expected_text.splitlines(), fresh_text.splitlines(),
        "committed", "fresh", n=0, lineterm="",
    )
    assert fresh_text == expected_text, (
        "Bytes on the wire changed. Review the diff, and if the change is deliberate "
        "regenerate with `uv run --no-sync python scripts/wire_snapshot.py`:\n"
        + "\n".join(line[:240] for _, line in zip(range(20), diff, strict=False))
    )


@pytest.mark.parametrize("hash_seed", ("0", "1"))
@pytest.mark.parametrize("verbose", [False, True])
@pytest.mark.parametrize("returncode", [0, 1])
def test_wire_subprocess_diagnostic_routing(monkeypatch, verbose, returncode, hash_seed) -> None:
    if verbose:
        monkeypatch.setenv("WIRE_SNAPSHOT_VERBOSE", "1")
    else:
        monkeypatch.delenv("WIRE_SNAPSHOT_VERBOSE", raising=False)
    stderr = None if verbose else "snapshot stderr"
    committed = {"schema": 3, "chars": {}, "scenarios": {"one": {"commands": {}}}}
    stdout = "snapshot stdout" if returncode else json.dumps(committed)
    run = Mock(return_value=subprocess.CompletedProcess([], returncode, stdout, stderr))
    monkeypatch.setattr(subprocess, "run", run)

    if returncode:
        with pytest.raises(AssertionError, match="snapshot stdout") as error:
            test_wire_bytes_match_committed_snapshot((hash_seed, ["one"], committed), 0)
        assert ("snapshot stderr" in str(error.value)) is (not verbose)
    else:
        test_wire_bytes_match_committed_snapshot((hash_seed, ["one"], committed), 0)

    run.assert_called_once_with(
        [sys.executable, str(SCRIPT), "--probe", "--only", "one"],
        env={**os.environ, "PYTHONHASHSEED": hash_seed},
        stdout=subprocess.PIPE,
        stderr=None if verbose else subprocess.PIPE,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )


def test_existing_snapshot_has_canonical_rendering_without_capture() -> None:
    """Appending accepted captures must retain the renderer's canonical order."""
    tool = _load_tool()
    text = tool.SNAPSHOT_PATH.read_text()
    stored = json.loads(text)
    scenarios = {}
    for sid, entry in stored["scenarios"].items():
        commands = {}
        for name, command in entry["commands"].items():
            commands[name] = (
                {**command, "writes": [[w[0], stored["chars"][w[1]], *w[2:]]
                                       for w in command["writes"]]}
                if "writes" in command else command
            )
        scenarios[sid] = {**entry["info"], "commands": commands}
    assert tool.render({"schema": stored["schema"], "scenarios": scenarios}) == text


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
