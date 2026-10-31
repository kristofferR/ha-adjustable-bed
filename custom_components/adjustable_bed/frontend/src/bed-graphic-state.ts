import type { BedEntities, HomeAssistant, MotorEntity } from "./types";
import type { BedGraphicPanel } from "./bed-graphic";

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
): boolean {
  const positionMotors = bed.motors.filter((motor) => {
    const entityId = motor.angle ?? motor.position;
    const unit = hass.states[entityId ?? ""]?.attributes.unit_of_measurement;
    return unit === "°" || unit === "%";
  });
  return selectBedGraphicMotors(positionMotors) !== undefined;
}

export function bedGraphicMotorOrder(motors: readonly MotorEntity[]): readonly MotorEntity[] {
  const graphic = selectBedGraphicMotors(motors);
  if (!graphic?.middle) return motors;
  const panels = [graphic.upper, graphic.middle, graphic.lower];
  return [...panels, ...motors.filter((motor) => !panels.includes(motor))];
}

/** A percentage drives a schematic pose, never a measured angle label. */
export function bedGraphicPanel(
  motor: MotorEntity,
  hass: HomeAssistant,
): BedGraphicPanel | undefined {
  const entityId = motor.angle ?? motor.position;
  const state = hass.states[entityId ?? ""];
  const unit = state?.attributes.unit_of_measurement;
  if (unit !== "°" && unit !== "%") return undefined;
  const raw = state.state.trim();
  if (raw === "") return undefined;
  const value = Number(raw);
  if (!Number.isFinite(value)) return undefined;
  if (unit === "°") return { angle: value };
  const percentage = Math.max(0, Math.min(100, value));
  return { angle: percentage * 0.75, readout: `${Math.round(percentage)}%` };
}
