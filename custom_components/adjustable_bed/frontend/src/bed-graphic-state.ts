import type { BedGraphicPanel } from "./bed-graphic";
import { type MotorEstimate, estimatedAngle } from "./estimates";
import type { BedEntities, HomeAssistant, MotorEntity } from "./types";

export interface BedGraphicMotors {
  upper: MotorEntity;
  lower: MotorEntity;
  middle?: MotorEntity;
}

export function selectBedGraphicMotors(
  motors: readonly MotorEntity[],
): BedGraphicMotors | undefined {
  const upper = motors.find(
    (motor) => motor.key === "back" || motor.key === "head",
  );
  const lower = motors.find(
    (motor) => motor.key === "legs" || motor.key === "feet",
  );
  const middle = motors.find((motor) => motor.key === "lumbar");
  return upper && lower ? { upper, lower, ...(middle ? { middle } : {}) } : undefined;
}

export function bedHasGraphicFeedback(
  bed: BedEntities,
  hass: HomeAssistant,
  allowPercentage = false,
): boolean {
  const positionMotors = bed.motors.filter((motor) => {
    const entityId = motor.angle ?? motor.position;
    const unit = hass.states[entityId ?? ""]?.attributes.unit_of_measurement;
    return unit === "°" || (allowPercentage && unit === "%");
  });
  // A calibrated estimate is drawn too, dashed: in degrees when its maximum
  // angle is set, or as a schematic pose when percentage graphics are on.
  const estimatedMotors = bed.motors.filter((motor) => {
    const estimate = hass.states[motor.estimate ?? ""];
    return estimate !== undefined &&
      (allowPercentage || typeof estimate.attributes.max_angle === "number");
  });
  return (
    selectBedGraphicMotors(positionMotors) !== undefined ||
    selectBedGraphicMotors(estimatedMotors) !== undefined
  );
}

export function bedGraphicMotorOrder(motors: readonly MotorEntity[], showLumbar = false): readonly MotorEntity[] {
  if (!showLumbar) return motors;
  const graphic = selectBedGraphicMotors(motors);
  if (!graphic?.middle) return motors;
  const panels = [graphic.upper, graphic.middle, graphic.lower];
  return [...panels, ...motors.filter((motor) => !panels.includes(motor))];
}

// Full travel maps onto the graphic's 75° range; the label keeps the percentage.
function percentagePanel(value: number): BedGraphicPanel {
  const percentage = Math.max(0, Math.min(100, value));
  return { angle: percentage * 0.75, readout: `${Math.round(percentage)}%` };
}

/** A percentage drives a schematic pose, never a measured angle label. */
export function bedGraphicPanel(
  motor: MotorEntity,
  hass: HomeAssistant,
  allowPercentage = false,
): BedGraphicPanel | undefined {
  const entityId = motor.angle ?? motor.position;
  const state = hass.states[entityId ?? ""];
  const unit = state?.attributes.unit_of_measurement;
  if (unit !== "°" && unit !== "%") return undefined;
  if (unit === "%" && !allowPercentage) return undefined;
  const raw = state.state.trim();
  if (raw === "") return undefined;
  const value = Number(raw);
  if (!Number.isFinite(value)) return undefined;
  if (unit === "°") return { angle: value };
  return percentagePanel(value);
}

/**
 * A tracking estimate's panel: degrees when the axis' maximum angle is set,
 * otherwise a schematic percentage pose when that graphic is on. The caller
 * marks the graphic estimated, so it is drawn dashed and labeled "≈".
 */
export function estimatedGraphicPanel(
  estimate: MotorEstimate | undefined,
  allowPercentage = false,
): BedGraphicPanel | undefined {
  const angle = estimatedAngle(estimate);
  if (angle !== undefined) return { angle };
  if (!allowPercentage || estimate?.state !== "tracking" || estimate.percent === undefined)
    return undefined;
  return percentagePanel(estimate.percent);
}
