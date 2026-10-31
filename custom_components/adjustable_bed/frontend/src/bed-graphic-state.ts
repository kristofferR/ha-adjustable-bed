import type { BedEntities, HomeAssistant, MotorEntity } from "./types";
import type { BedGraphicPanel } from "./bed-graphic";

export interface BedGraphicMotors {
  upper: MotorEntity;
  lower: MotorEntity;
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
  return upper && lower ? { upper, lower } : undefined;
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
