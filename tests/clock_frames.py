"""Capture the writes one controller call makes, on the wire snapshot's harness.

The clock-sync tests use it to prove that ``sync_clock`` puts exactly the frames
on the wire that a bed's own clock operation did, at the snapshot's frozen time.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "wire_snapshot.py"


def _tool() -> Any:
    module = sys.modules.get("wire_snapshot")
    if module is None:
        spec = importlib.util.spec_from_file_location("wire_snapshot", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    return module


async def capture(
    scenario_id: str,
    call: Callable[[Any], Awaitable[Any]],
    *,
    bed_type: str | None = None,
    entry_data: dict[str, Any] | None = None,
) -> list[list[Any]]:
    """Connect ``scenario_id``'s controller and return what ``call`` writes after connect.

    ``bed_type`` and ``entry_data`` adjust the scenario, on its own GATT layout.
    """
    import asyncio
    import dataclasses

    from freezegun import freeze_time

    tool = _tool()
    baseline = asyncio.all_tasks()
    scenario = next(s for s in tool.build_scenarios() if s.id == scenario_id)
    scenario = dataclasses.replace(
        scenario,
        bed_type=bed_type or scenario.bed_type,
        entry_data={**scenario.entry_data, **(entry_data or {})},
        layout_id=scenario.layout_id or scenario.id,
    )
    layout = json.loads(tool.LAYOUTS_PATH.read_text())[scenario.layout_id or scenario.id]
    with freeze_time(tool.FROZEN_NOW, real_asyncio=True) as frozen:
        clock = tool.FakeClock(frozen)
        recorder = tool.Recorder(clock)
        with tool.deterministic_process_state(), tool.virtual_time(clock):
            client = tool.FakeClient(recorder, layout, scenario.replies)
            controller = await tool._build(scenario, client)  # noqa: SLF001
            await tool._connect(controller, recorder, clock)  # noqa: SLF001
            recorder.events.clear()
            clock.begin_phase()
            try:
                result = await tool._timed(call(controller), recorder, clock)  # noqa: SLF001
            finally:
                await tool._cancel_strays(baseline)  # noqa: SLF001
    assert result["status"] in ("ok", "no_writes"), result
    return result.get("writes", [])
