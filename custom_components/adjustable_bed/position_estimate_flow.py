"""Options-flow steps that enable and calibrate estimated positions (#601).

The user chooses motors and acknowledges that positions are estimated. For each
motor they bring it to flat, then the flow raises it until they select
"Reached the top" and lowers it until "Reached the bottom". Each time runs from
the motor's first movement command. Every movement is an ordinary timed move
through the coordinator, bounded by the longest calibratable travel, and either
action button or closing the dialog sends STOP. The last step shows the times
for fine tuning. Measured motors end flat, so their reference is set.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import DOMAIN, SIDE_LEFT, SIDE_RIGHT
from .position_estimate import (
    MAX_TRAVEL_S,
    MIN_TRAVEL_S,
    BedEstimate,
    PositionEstimates,
    async_measure_move,
    async_stop_bed,
    position_estimates,
)

if TYPE_CHECKING:
    from .beds.base import BedController, SideBoundController

_LOGGER = logging.getLogger(__name__)

ESTIMATE_MOTORS = ("back", "legs", "head", "feet")
CONF_ACKNOWLEDGE = "acknowledge"
CONF_MEASURE = "measure"
_STOP_TIMEOUT_S = 10.0


def eligible_motors(controller: BedController | SideBoundController | None) -> list[str]:
    """Motors a controller declares for estimates, in the standard order."""
    if controller is None:
        return []
    groups = controller.estimated_position_motor_groups
    return [motor for motor in ESTIMATE_MOTORS if groups.get(motor) == (motor,)]


def not_offered_motors(controller: BedController | SideBoundController | None) -> list[str]:
    """Single motor controls without a proven estimate, for the explanation."""
    if controller is None:
        return []
    groups = controller.estimated_position_motor_groups
    return [
        spec.key
        for spec in controller.motor_control_specs
        if len(groups.get(spec.key, (spec.key,))) <= 1 and groups.get(spec.key) != (spec.key,)
    ]


def _label(key: str) -> str:
    return key.replace("_", " ").capitalize()


class EstimatedPositionsFlowMixin:
    """Calibration steps for ``AdjustableBedOptionsFlow``."""

    if TYPE_CHECKING:
        hass: HomeAssistant

        @property
        def config_entry(self) -> ConfigEntry: ...

        def async_show_form(self, **kwargs: Any) -> ConfigFlowResult: ...

        def async_show_menu(self, **kwargs: Any) -> ConfigFlowResult: ...

        def async_create_entry(self, **kwargs: Any) -> ConfigFlowResult: ...

        def async_abort(self, **kwargs: Any) -> ConfigFlowResult: ...

    _est_manager: PositionEstimates | None = None
    _est_bed: BedEstimate | None = None
    _est_initial: frozenset[str] = frozenset()
    _est_queue: list[str]
    _est_motor: str | None = None
    _est_times: dict[str, list[float | None]]
    _est_measured: set[str]
    _est_task: asyncio.Task[None] | None = None
    _est_step: int = 1
    _est_steps: int = 1
    _est_finished: bool = False

    # ---------------------------------------------------------------- helpers
    def _estimate_runtime(self, side: str | None) -> Any:
        coordinator = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        if coordinator is None:
            return None
        if side is None:
            return coordinator
        child_for_side = getattr(coordinator, "child_for_side", None)
        return child_for_side(side) if child_for_side is not None else None

    def estimate_menu_options(self) -> list[str]:
        """Menu entries for the beds or sides that can be estimated."""
        manager = position_estimates(self.hass, self.config_entry.entry_id)
        if manager is None:
            return []
        options: list[str] = []
        for bed in manager.beds.values():
            runtime = self._estimate_runtime(bed.side)
            controller = getattr(runtime, "capability_controller", None)
            if eligible_motors(controller) or bed.motors:
                options.append(
                    "estimated_positions" if bed.side is None else f"{bed.side}_estimated_positions"
                )
        return sorted(
            options,
            key=[
                "estimated_positions",
                f"{SIDE_LEFT}_estimated_positions",
                f"{SIDE_RIGHT}_estimated_positions",
            ].index,
        )

    # ----------------------------------------------------------- choose motors
    async def async_step_estimated_positions(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_estimate_choose(None, "estimated_positions", user_input)

    async def async_step_left_estimated_positions(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_estimate_choose(SIDE_LEFT, "left_estimated_positions", user_input)

    async def async_step_right_estimated_positions(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_estimate_choose(
            SIDE_RIGHT, "right_estimated_positions", user_input
        )

    async def _async_estimate_choose(
        self, side: str | None, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        manager = position_estimates(self.hass, self.config_entry.entry_id)
        bed = (
            None
            if manager is None
            else next((item for item in manager.beds.values() if item.side == side), None)
        )
        if manager is None or bed is None:
            return self.async_abort(reason="estimated_positions_unavailable")
        controller = getattr(self._estimate_runtime(side), "capability_controller", None)
        offered = eligible_motors(controller) or [
            motor for motor in ESTIMATE_MOTORS if motor in bed.motors
        ]
        calibrated = bool(bed.motors) and all(
            estimate.calibrated for estimate in bed.motors.values()
        )
        schema: dict[vol.Marker, Any] = {
            vol.Optional(motor, default=motor in bed.motors or not bed.motors): bool
            for motor in offered
        }
        schema[vol.Optional(CONF_MEASURE, default=not calibrated)] = bool
        schema[vol.Optional(CONF_ACKNOWLEDGE, default=False)] = bool
        errors: dict[str, str] = {}
        if user_input is not None:
            chosen = [motor for motor in offered if user_input.get(motor)]
            if chosen and not user_input.get(CONF_ACKNOWLEDGE):
                errors[CONF_ACKNOWLEDGE] = "estimate_acknowledge_required"
            else:
                self._est_manager = manager
                self._est_bed = bed
                self._est_initial = frozenset(bed.motors)
                if not chosen:
                    bed.configure({})
                    return self._async_estimate_finish()
                bed.configure(
                    {
                        motor: (
                            (bed.motors[motor].up_s, bed.motors[motor].down_s)
                            if motor in bed.motors
                            else (None, None)
                        )
                        for motor in chosen
                    }
                )
                self._est_times = {
                    motor: [bed.motors[motor].up_s, bed.motors[motor].down_s] for motor in chosen
                }
                self._est_measured = set()
                self._est_queue = list(chosen) if user_input.get(CONF_MEASURE) else []
                self._est_steps = 2 + 3 * len(self._est_queue)
                return await self._async_estimate_next_motor()
        not_offered = not_offered_motors(controller)
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(schema),
            errors=errors,
            description_placeholders={
                "not_offered": ", ".join(_label(key) for key in not_offered) or "-",
                "max_s": str(int(MAX_TRAVEL_S)),
            },
        )

    async def _async_estimate_next_motor(self) -> ConfigFlowResult:
        if not self._est_queue:
            self._est_motor = None
            return await self.async_step_estimate_review()
        self._est_motor = self._est_queue[0]
        self._est_step = 2 + 3 * len(self._est_measured)
        return await self.async_step_estimate_flat()

    def _estimate_placeholders(self) -> dict[str, str]:
        return {
            "motor": _label(self._est_motor or ""),
            "step": str(self._est_step),
            "steps": str(self._est_steps),
            "max_s": str(int(MAX_TRAVEL_S)),
        }

    def _estimate_menu(self, step_id: str, options: list[str]) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id=step_id,
            menu_options=options,
            description_placeholders=self._estimate_placeholders(),
        )

    # --------------------------------------------------------------- movement
    def _estimate_start(self, direction: str) -> None:
        manager, bed, motor = self._est_manager, self._est_bed, self._est_motor
        assert manager is not None and bed is not None and motor is not None
        self._est_task = self.hass.async_create_background_task(
            async_measure_move(self.hass, manager, bed, motor, direction),
            f"{DOMAIN} calibrate {motor} {direction}",
        )

    async def _async_estimate_stop(self) -> float | None:
        """STOP the measured move; return its elapsed time if it was still running."""
        manager, bed, motor, task = (
            self._est_manager,
            self._est_bed,
            self._est_motor,
            self._est_task,
        )
        self._est_task = None
        if manager is None or bed is None or motor is None or task is None:
            return None
        elapsed = None if task.done() else bed.move_elapsed(motor)
        try:
            await async_stop_bed(self.hass, manager, bed)
        except Exception:  # noqa: BLE001 - the measurement fails, the flow reports it
            _LOGGER.warning("STOP after a calibration move failed", exc_info=True)
            elapsed = None
        with contextlib.suppress(Exception, asyncio.CancelledError):
            async with asyncio.timeout(_STOP_TIMEOUT_S):
                await task
        if elapsed is None or not MIN_TRAVEL_S <= elapsed <= MAX_TRAVEL_S:
            return None
        return round(elapsed, 1)

    def async_remove(self) -> None:
        """Stop a calibration movement when the dialog closes."""
        if self._est_task is not None and not self._est_task.done():
            self.hass.async_create_background_task(
                self._async_estimate_stop(), f"{DOMAIN} stop abandoned calibration"
            )
        self._async_estimate_reload()
        parent_remove = getattr(super(), "async_remove", None)
        if parent_remove is not None:
            parent_remove()

    def _async_estimate_reload(self) -> None:
        """Reload once when the enabled motors changed, so their entities follow."""
        bed = self._est_bed
        if bed is None or self._est_finished:
            return
        self._est_finished = True
        if frozenset(bed.motors) != self._est_initial:
            self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)

    def _async_estimate_finish(self) -> ConfigFlowResult:
        self._async_estimate_reload()
        return self.async_create_entry(title="", data=dict(self.config_entry.options))

    # ----------------------------------------------------------- flat, raise, lower
    async def async_step_estimate_flat(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self._estimate_menu(
            "estimate_flat", ["estimate_flat_confirm", "estimate_flat_lower", "estimate_cancel"]
        )

    async def async_step_estimate_flat_lower(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self.async_step_estimate_lowering()

    async def async_step_estimate_lowering(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        self._estimate_start("down")
        return self._estimate_menu("estimate_lowering", ["estimate_lowered", "estimate_cancel"])

    async def async_step_estimate_lowered(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        await self._async_estimate_stop()
        return await self.async_step_estimate_flat_confirm()

    async def async_step_estimate_flat_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self.async_step_estimate_raise()

    async def async_step_estimate_raise(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        self._est_step = 3 + 3 * len(self._est_measured)
        self._estimate_start("up")
        return self._estimate_menu("estimate_raise", ["estimate_top", "estimate_cancel"])

    async def async_step_estimate_top(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        elapsed = await self._async_estimate_stop()
        if elapsed is None or self._est_motor is None:
            return await self.async_step_estimate_retry()
        self._est_times[self._est_motor][0] = elapsed
        return await self.async_step_estimate_lower()

    async def async_step_estimate_lower(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        self._est_step = 4 + 3 * len(self._est_measured)
        self._estimate_start("down")
        return self._estimate_menu("estimate_lower", ["estimate_bottom", "estimate_cancel"])

    async def async_step_estimate_retry(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self._estimate_menu("estimate_retry", ["estimate_retry_again", "estimate_cancel"])

    async def async_step_estimate_bottom(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        elapsed = await self._async_estimate_stop()
        if elapsed is None or self._est_motor is None:
            return await self.async_step_estimate_retry()
        self._est_times[self._est_motor][1] = elapsed
        self._est_measured.add(self._est_motor)
        self._est_queue.pop(0)
        return await self._async_estimate_next_motor()

    async def async_step_estimate_retry_again(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        # Measure this motor again from flat; earlier motors keep their times.
        return await self._async_estimate_next_motor()

    async def async_step_estimate_cancel(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        await self._async_estimate_stop()
        self._async_estimate_reload()
        return self.async_abort(reason="estimate_cancelled")

    # ----------------------------------------------------------------- review
    async def async_step_estimate_review(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        bed = self._est_bed
        assert bed is not None
        seconds = NumberSelector(
            NumberSelectorConfig(
                min=MIN_TRAVEL_S,
                max=MAX_TRAVEL_S,
                step=0.1,
                unit_of_measurement="s",
                mode=NumberSelectorMode.BOX,
            )
        )
        schema: dict[vol.Marker, Any] = {}
        for motor, (up_s, down_s) in self._est_times.items():
            for key, value in ((f"{motor}_up", up_s), (f"{motor}_down", down_s)):
                marker = vol.Required(key) if value is None else vol.Required(key, default=value)
                schema[marker] = seconds
        if user_input is not None:
            bed.configure(
                {
                    motor: (float(user_input[f"{motor}_up"]), float(user_input[f"{motor}_down"]))
                    for motor in self._est_times
                }
            )
            if self._est_measured:
                # Each measured motor ended its last move at the bottom: flat.
                bed.set_reference(self._est_measured)
            return self._async_estimate_finish()
        return self.async_show_form(
            step_id="estimate_review",
            data_schema=vol.Schema(schema),
            description_placeholders={
                **self._estimate_placeholders(),
                "step": str(self._est_steps),
            },
        )
