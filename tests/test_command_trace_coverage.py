"""Every GATT write a controller sends reaches the support-bundle command trace.

Drives the wire-snapshot scenarios with a recording coordinator, so the check
covers every write path the snapshot plan exercises, not only ``write_command``.
Pairlink writes nothing before a join; its redacted traces are tested in
``test_reverie_pairlink.py``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from freezegun import freeze_time

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "wire_snapshot.py"

# Controllers whose own write loops bypass ``_write_gatt_with_retry``.
TRACED_SCENARIOS = [
    "fsm_relax",
    "okimat",
    "okin_nordic",
    "okin_dot",
    "reverie",
    "reverie_nightstand",
    "rondure",
    "sleep_number",
    "svane",
    "svane:jensen_linon",
]


def _tool() -> Any:
    module = sys.modules.get("wire_snapshot")
    if module is None:
        spec = importlib.util.spec_from_file_location("wire_snapshot", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    return module


async def _capture(
    scenario_id: str, monkeypatch: pytest.MonkeyPatch
) -> tuple[list[tuple[str, str]], list[dict[str, Any]]]:
    tool = _tool()
    traces: list[dict[str, Any]] = []
    monkeypatch.setattr(
        tool.Coordinator, "record_command_trace", lambda _self, **trace: traces.append(trace)
    )
    scenario = next(s for s in tool.build_scenarios() if s.id == scenario_id)
    layout = json.loads(tool.LAYOUTS_PATH.read_text())[scenario.layout_id or scenario.id]
    with freeze_time(tool.FROZEN_NOW, real_asyncio=True) as frozen:
        result = await tool.capture_scenario(scenario, layout, frozen)
    writes = [
        (event[1], event[3])
        for command in result["commands"].values()
        for event in command.get("writes", ())
        if isinstance(event[2], bool)  # the kind of a GATT write is its response flag
    ]
    assert writes, f"{scenario_id} wrote nothing"
    return writes, traces


@pytest.mark.parametrize("scenario_id", TRACED_SCENARIOS)
async def test_every_write_is_traced(scenario_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    writes, traces = await _capture(scenario_id, monkeypatch)
    traced = {trace["payload"]["hex"] for trace in traces}
    assert {payload for _char, payload in writes} <= traced
