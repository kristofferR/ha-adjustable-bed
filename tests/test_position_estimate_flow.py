"""Options-flow calibration of estimated positions (#601)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant.common import MockConfigEntry

from custom_components.adjustable_bed import position_estimate as pe
from custom_components.adjustable_bed import position_estimate_flow as flow_module
from custom_components.adjustable_bed.const import (
    BED_TYPE_OCTO,
    CONF_BED_TYPE,
    CONF_DISABLE_ANGLE_SENSING,
    CONF_HAS_MASSAGE,
    CONF_MOTOR_COUNT,
    CONF_OCTO_MOTOR_COUNT_OVERRIDE,
    CONF_PREFERRED_ADAPTER,
    CONF_PROTOCOL_VARIANT,
    DOMAIN,
    OCTO_VARIANT_STANDARD,
)
from custom_components.adjustable_bed.position_estimate import EstimateState

ADDRESS = "AA:BB:CC:DD:EE:62"


class Bench:
    """Stands in for the timed move: a tracked move that runs until STOP."""

    def __init__(self, hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch) -> None:
        self.hass = hass
        self.now = 0.0
        self.moves: list[tuple[str, str, int]] = []
        self.stops = 0
        self.fail_after_stop = False
        self.release_fails_quietly = False
        self.started = asyncio.Event()
        self.admit = asyncio.Event()
        self.admit.set()
        self._release = asyncio.Event()
        monkeypatch.setattr(pe, "_clock", lambda: self.now)
        monkeypatch.setattr(
            "custom_components.adjustable_bed.services._async_timed_move", self.move
        )
        monkeypatch.setattr(flow_module, "async_stop_bed", AsyncMock(side_effect=self.stop))

    async def move(self, targets: Any, motor: str, direction: str, duration_ms: int) -> None:
        manager = pe.position_estimates(self.hass, "octo_flow_entry")
        assert manager is not None
        bed = manager.beds[ADDRESS]
        self.moves.append((motor, direction, duration_ms))
        self._release.clear()
        await self.admit.wait()  # queued behind earlier work until admitted
        token = bed.begin_move((motor,))
        self.started.set()
        await self._release.wait()
        if self.fail_after_stop:
            bed.end_move(token, direction, None)
            raise ConnectionError("lost during STOP")
        if self.release_fails_quietly:
            pe.notify_release_failed(
                SimpleNamespace(
                    hass=self.hass,
                    entry=SimpleNamespace(entry_id="octo_flow_entry"),
                    address=ADDRESS,
                )
            )
        bed.end_move(token, direction, 0.0)

    async def stop(self, *_args: object) -> None:
        self.stops += 1
        self._release.set()
        self.admit.set()  # STOP ends queued work too


@pytest.fixture
async def entry(
    hass: HomeAssistant,
    mock_octo_ready_transport: None,
    enable_custom_integrations: None,
    request: pytest.FixtureRequest,
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bedroom bed",
        data={
            "address": ADDRESS,
            "name": "Bedroom bed",
            CONF_BED_TYPE: BED_TYPE_OCTO,
            CONF_MOTOR_COUNT: getattr(request, "param", 2),
            CONF_OCTO_MOTOR_COUNT_OVERRIDE: str(getattr(request, "param", 2)),
            CONF_HAS_MASSAGE: False,
            CONF_DISABLE_ANGLE_SENSING: True,
            CONF_PREFERRED_ADAPTER: "auto",
            CONF_PROTOCOL_VARIANT: OCTO_VARIANT_STANDARD,
        },
        unique_id=ADDRESS,
        entry_id="octo_flow_entry",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


async def open_estimates(hass: HomeAssistant, entry: MockConfigEntry) -> Any:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert "estimated_positions" in result["menu_options"]
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "estimated_positions"}
    )


@pytest.mark.parametrize(("entry", "motor"), [(2, "back"), (1, "tv_lift")], indirect=["entry"])
async def test_measures_raising_and_lowering_then_sets_flat(
    hass: HomeAssistant, entry: MockConfigEntry, monkeypatch: pytest.MonkeyPatch, motor: str
) -> None:
    bench = Bench(hass, monkeypatch)
    options = hass.config_entries.options
    result = await open_estimates(hass, entry)
    assert result["type"] is FlowResultType.FORM
    flow_id = result["flow_id"]

    selected = {motor: True, "measure": True}
    if motor == "back":
        selected["legs"] = False
    result = await options.async_configure(flow_id, selected)
    assert result["errors"] == {"acknowledge": "estimate_acknowledge_required"}

    result = await options.async_configure(flow_id, {**selected, "acknowledge": True})
    assert result["step_id"] == "estimate_flat"
    assert result["description_placeholders"]["step"] == "2"

    result = await options.async_configure(flow_id, {"next_step_id": "estimate_flat_confirm"})
    assert result["step_id"] == "estimate_raise"
    await settle()
    bench.now += 18.4
    result = await options.async_configure(flow_id, {"next_step_id": "estimate_top"})
    assert result["step_id"] == "estimate_lower"
    await settle()
    bench.now += 16.9
    result = await options.async_configure(flow_id, {"next_step_id": "estimate_bottom"})
    assert result["step_id"] == "estimate_review"
    assert [(m, d) for m, d, _ms in bench.moves] == [(motor, "up"), (motor, "down")]
    assert bench.moves[0][2] == 60000
    assert bench.stops == 2

    result = await options.async_configure(flow_id, {f"{motor}_up": 18.0, f"{motor}_down": 16.9})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    manager = pe.position_estimates(hass, entry.entry_id)
    assert manager is not None
    back = manager.beds[ADDRESS].motors[motor]
    assert (back.up_s, back.down_s) == (18.0, 16.9)
    assert back.state is EstimateState.TRACKING and back.percent == 0.0
    # The reload created the new motor's entities and kept its confirmation.
    state = hass.states.get(f"number.bedroom_bed_{motor}_position_estimated")
    assert state is not None and state.state == "0"


async def test_typed_times_without_measuring(
    hass: HomeAssistant, entry: MockConfigEntry, monkeypatch: pytest.MonkeyPatch
) -> None:
    bench = Bench(hass, monkeypatch)
    options = hass.config_entries.options
    result = await open_estimates(hass, entry)
    result = await options.async_configure(
        result["flow_id"], {"back": False, "legs": True, "measure": False, "acknowledge": True}
    )
    assert result["step_id"] == "estimate_review"
    result = await options.async_configure(result["flow_id"], {"legs_up": 11.2, "legs_down": 10.8})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert bench.moves == []
    manager = pe.position_estimates(hass, entry.entry_id)
    assert manager is not None
    # Typed times alone are no reference: the user sets it when the bed is flat.
    assert manager.beds[ADDRESS].state("legs") is EstimateState.UNKNOWN


async def test_cancel_and_safety_stop_save_no_times(
    hass: HomeAssistant, entry: MockConfigEntry, monkeypatch: pytest.MonkeyPatch
) -> None:
    bench = Bench(hass, monkeypatch)
    options = hass.config_entries.options
    result = await open_estimates(hass, entry)
    flow_id = result["flow_id"]
    await options.async_configure(
        flow_id, {"back": True, "legs": False, "measure": True, "acknowledge": True}
    )
    await options.async_configure(flow_id, {"next_step_id": "estimate_flat_confirm"})
    await settle()
    # A tap past the safety ceiling is not a measurement.
    bench.now += 61.0
    result = await options.async_configure(flow_id, {"next_step_id": "estimate_top"})
    assert result["step_id"] == "estimate_retry"
    result = await options.async_configure(flow_id, {"next_step_id": "estimate_retry_again"})
    assert result["step_id"] == "estimate_flat"
    result = await options.async_configure(flow_id, {"next_step_id": "estimate_flat_lower"})
    assert result["step_id"] == "estimate_lowering"
    await settle()
    result = await options.async_configure(flow_id, {"next_step_id": "estimate_cancel"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "estimate_cancelled"
    assert bench.stops == 2
    await hass.async_block_till_done()
    manager = pe.position_estimates(hass, entry.entry_id)
    assert manager is not None
    assert manager.beds[ADDRESS].state("back") is EstimateState.NOT_CALIBRATED


async def test_closing_the_dialog_stops_the_motor(
    hass: HomeAssistant, entry: MockConfigEntry, monkeypatch: pytest.MonkeyPatch
) -> None:
    bench = Bench(hass, monkeypatch)
    options = hass.config_entries.options
    result = await open_estimates(hass, entry)
    flow_id = result["flow_id"]
    await options.async_configure(
        flow_id, {"back": True, "legs": False, "measure": True, "acknowledge": True}
    )
    await options.async_configure(flow_id, {"next_step_id": "estimate_flat_confirm"})
    await settle()
    options.async_abort(flow_id)
    await hass.async_block_till_done()
    assert bench.stops == 1


async def test_clearing_every_motor_turns_estimates_off(
    hass: HomeAssistant, entry: MockConfigEntry, monkeypatch: pytest.MonkeyPatch
) -> None:
    Bench(hass, monkeypatch)
    manager = pe.position_estimates(hass, entry.entry_id)
    assert manager is not None
    manager.beds[ADDRESS].configure({"back": (20.0, 10.0)})
    result = await open_estimates(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"back": False, "legs": False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    manager = pe.position_estimates(hass, entry.entry_id)
    assert manager is not None and not manager.active


async def measure_back_from_flat(hass: HomeAssistant, entry: MockConfigEntry) -> str:
    options = hass.config_entries.options
    result = await open_estimates(hass, entry)
    flow_id = result["flow_id"]
    await options.async_configure(
        flow_id, {"back": True, "legs": True, "measure": True, "acknowledge": True}
    )
    await options.async_configure(flow_id, {"next_step_id": "estimate_flat_confirm"})
    await settle()
    return flow_id


async def test_a_move_failing_during_stop_is_not_a_measurement(
    hass: HomeAssistant, entry: MockConfigEntry, monkeypatch: pytest.MonkeyPatch
) -> None:
    bench = Bench(hass, monkeypatch)
    flow_id = await measure_back_from_flat(hass, entry)
    bench.fail_after_stop = True
    bench.now += 12.0
    result = await hass.config_entries.options.async_configure(
        flow_id, {"next_step_id": "estimate_top"}
    )
    assert result["step_id"] == "estimate_retry"


async def test_an_earlier_move_is_not_the_calibration(
    hass: HomeAssistant, entry: MockConfigEntry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A card move still running when calibration queues must not be timed."""
    bench = Bench(hass, monkeypatch)
    manager = pe.position_estimates(hass, entry.entry_id)
    assert manager is not None
    bench.admit.clear()
    options = hass.config_entries.options
    result = await open_estimates(hass, entry)
    flow_id = result["flow_id"]
    await options.async_configure(
        flow_id, {"back": True, "legs": True, "measure": True, "acknowledge": True}
    )
    manager.beds[ADDRESS].begin_move(("back",))  # an older card hold, not ours
    await options.async_configure(flow_id, {"next_step_id": "estimate_flat_confirm"})
    await settle()
    assert not bench.started.is_set()
    bench.now += 12.0
    result = await hass.config_entries.options.async_configure(
        flow_id, {"next_step_id": "estimate_top"}
    )
    assert result["step_id"] == "estimate_retry"


async def test_cancel_restores_the_initial_calibration_without_trust(
    hass: HomeAssistant, entry: MockConfigEntry, monkeypatch: pytest.MonkeyPatch
) -> None:
    Bench(hass, monkeypatch)
    manager = pe.position_estimates(hass, entry.entry_id)
    assert manager is not None
    bed = manager.beds[ADDRESS]
    bed.configure({"back": (20.0, 10.0), "legs": (10.0, 8.0)})
    bed.set_reference()
    bed.motors["back"].percent = 50.0
    options = hass.config_entries.options
    result = await open_estimates(hass, entry)
    flow_id = result["flow_id"]
    # Deselect legs and recalibrate back, then cancel.
    await options.async_configure(
        flow_id, {"back": True, "legs": False, "measure": True, "acknowledge": True}
    )
    result = await options.async_configure(flow_id, {"next_step_id": "estimate_cancel"})
    assert result["reason"] == "estimate_cancelled"
    assert {m: (e.up_s, e.down_s) for m, e in bed.motors.items()} == {
        "back": (20.0, 10.0),
        "legs": (10.0, 8.0),
    }
    # The user may have flattened the back for calibration: its old 50% is gone.
    assert bed.state("back") is EstimateState.UNKNOWN
    assert bed.state("legs") is EstimateState.TRACKING


async def test_a_move_after_the_bottom_withholds_the_reference(
    hass: HomeAssistant, entry: MockConfigEntry, monkeypatch: pytest.MonkeyPatch
) -> None:
    bench = Bench(hass, monkeypatch)
    options = hass.config_entries.options
    result = await open_estimates(hass, entry)
    flow_id = result["flow_id"]
    await options.async_configure(
        flow_id, {"back": True, "legs": False, "measure": True, "acknowledge": True}
    )
    await options.async_configure(flow_id, {"next_step_id": "estimate_flat_confirm"})
    await settle()
    bench.now += 18.0
    await options.async_configure(flow_id, {"next_step_id": "estimate_top"})
    await settle()
    bench.now += 16.0
    await options.async_configure(flow_id, {"next_step_id": "estimate_bottom"})
    manager = pe.position_estimates(hass, entry.entry_id)
    assert manager is not None
    bed = manager.beds[ADDRESS]
    later = bed.begin_move(("back",))  # someone raised the back before Submit
    bed.end_move(later, "up", 5.0)
    await options.async_configure(flow_id, {"back_up": 18.0, "back_down": 16.0})
    await hass.async_block_till_done()
    manager = pe.position_estimates(hass, entry.entry_id)
    assert manager is not None
    assert manager.beds[ADDRESS].state("back") is EstimateState.UNKNOWN


async def test_a_quiet_release_failure_during_stop_is_not_a_measurement(
    hass: HomeAssistant, entry: MockConfigEntry, monkeypatch: pytest.MonkeyPatch
) -> None:
    bench = Bench(hass, monkeypatch)
    flow_id = await measure_back_from_flat(hass, entry)
    bench.release_fails_quietly = True
    bench.now += 12.0
    result = await hass.config_entries.options.async_configure(
        flow_id, {"next_step_id": "estimate_top"}
    )
    assert result["step_id"] == "estimate_retry"


async def test_a_hardware_preset_after_the_bottom_withholds_the_reference(
    hass: HomeAssistant, entry: MockConfigEntry, monkeypatch: pytest.MonkeyPatch
) -> None:
    bench = Bench(hass, monkeypatch)
    options = hass.config_entries.options
    result = await open_estimates(hass, entry)
    flow_id = result["flow_id"]
    await options.async_configure(
        flow_id, {"back": True, "legs": False, "measure": True, "acknowledge": True}
    )
    await options.async_configure(flow_id, {"next_step_id": "estimate_flat_confirm"})
    await settle()
    bench.now += 18.0
    await options.async_configure(flow_id, {"next_step_id": "estimate_top"})
    await settle()
    bench.now += 16.0
    await options.async_configure(flow_id, {"next_step_id": "estimate_bottom"})
    manager = pe.position_estimates(hass, entry.entry_id)
    assert manager is not None
    # A hardware preset moved the (not yet calibrated) back before Submit.
    manager.beds[ADDRESS].invalidate(pe.EstimateReason.HARDWARE_PRESET)
    await options.async_configure(flow_id, {"back_up": 18.0, "back_down": 16.0})
    await hass.async_block_till_done()
    manager = pe.position_estimates(hass, entry.entry_id)
    assert manager is not None
    assert manager.beds[ADDRESS].state("back") is EstimateState.UNKNOWN
