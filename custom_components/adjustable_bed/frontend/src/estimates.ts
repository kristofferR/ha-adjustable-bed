// Estimated positions and saved positions (#601). Pure helpers so the card's
// readouts, alerts and saved-position rules can be unit tested.
import type { HomeAssistant, MotorEntity } from "./types";

export type EstimateState = "tracking" | "unconfirmed" | "unknown" | "not_calibrated";

export interface MotorEstimate {
  motor: string;
  entityId: string;
  state: EstimateState;
  // Tracking value, or the restored/last estimate when not tracking.
  percent?: number;
  reason?: string;
  // Present only when the user configured this axis' maximum angle.
  maxAngle?: number;
  side?: string;
}

export interface SavedPosition {
  id: string;
  name: string;
  button: boolean;
  // Bed key ("bed", "left" or "right") -> motor -> estimated percent.
  beds: Record<string, Record<string, number>>;
}

const finite = (value: unknown): number | undefined =>
  typeof value === "number" && Number.isFinite(value) ? value : undefined;

export function motorEstimate(
  hass: HomeAssistant | undefined,
  motor: MotorEntity,
): MotorEstimate | undefined {
  const entityId = motor.estimate;
  const entity = entityId ? hass?.states[entityId] : undefined;
  if (!entityId || !entity) return undefined;
  const attributes = entity.attributes;
  const side = typeof attributes.bed_side === "string" ? attributes.bed_side : undefined;
  // Unavailable means enabled but not calibrated: HA drops the attributes then.
  if (entity.state === "unavailable")
    return { motor: motor.key, entityId, state: "not_calibrated", side };
  const declared = attributes.estimate_state;
  const state: EstimateState =
    declared === "tracking" || declared === "unconfirmed" || declared === "unknown"
      ? declared
      : "unknown";
  const value = Number.parseFloat(entity.state);
  return {
    motor: motor.key,
    entityId,
    state,
    percent: state === "tracking" && Number.isFinite(value)
      ? value
      : finite(attributes.last_estimate),
    reason: typeof attributes.estimate_reason === "string" ? attributes.estimate_reason : undefined,
    maxAngle: finite(attributes.max_angle),
    side,
  };
}

export function bedEstimates(
  hass: HomeAssistant | undefined,
  motors: MotorEntity[],
): MotorEstimate[] {
  return motors.flatMap((motor) => {
    const estimate = motorEstimate(hass, motor);
    return estimate ? [estimate] : [];
  });
}

// "≈ 42%" while tracking; a guess is never shown as a bare number.
export function estimateReadout(
  estimate: MotorEstimate,
  text: (key: string, params?: Record<string, string>) => string,
): string {
  const percent = estimate.percent === undefined ? undefined : `${Math.round(estimate.percent)}`;
  if (estimate.state === "tracking" && percent !== undefined)
    return text("estimate.readout", { percent });
  if (estimate.state === "unconfirmed" && percent !== undefined)
    return text("estimate.readout_was", { percent });
  if (estimate.state === "not_calibrated") return text("estimate.not_calibrated");
  return text("estimate.unknown");
}

export type EstimateChip = "estimated" | "unconfirmed" | "unknown";

export function estimateChip(estimates: MotorEstimate[]): EstimateChip | undefined {
  if (estimates.length === 0) return undefined;
  if (estimates.some((e) => e.state === "unknown" || e.state === "not_calibrated"))
    return "unknown";
  if (estimates.some((e) => e.state === "unconfirmed")) return "unconfirmed";
  return "estimated";
}

export type EstimateAlert =
  | { kind: "calibrate" }
  | { kind: "unconfirmed"; estimates: MotorEstimate[] }
  | { kind: "unknown"; reason?: string };

// One alert, most actionable first. Hold controls stay usable in every case.
export function estimateAlert(estimates: MotorEstimate[]): EstimateAlert | undefined {
  if (estimates.some((e) => e.state === "not_calibrated")) return { kind: "calibrate" };
  const unknown = estimates.filter((e) => e.state === "unknown");
  if (unknown.length) return { kind: "unknown", reason: unknown[0].reason };
  const unconfirmed = estimates.filter((e) => e.state === "unconfirmed");
  if (unconfirmed.length) return { kind: "unconfirmed", estimates: unconfirmed };
  return undefined;
}

export function savedPositions(
  hass: HomeAssistant | undefined,
  sensorId: string | undefined,
): SavedPosition[] {
  const raw = sensorId ? hass?.states[sensorId]?.attributes.positions : undefined;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((item): SavedPosition[] => {
    if (!item || typeof item !== "object") return [];
    const { id, name, button, beds } = item as Record<string, unknown>;
    if (typeof id !== "string" || typeof name !== "string" || !beds || typeof beds !== "object")
      return [];
    return [{ id, name, button: button !== false, beds: beds as SavedPosition["beds"] }];
  });
}

// The bed keys a pane covers: a standalone bed, both sides, or one side.
export function paneBedKeys(paneSide: string | undefined, paired: boolean): string[] {
  if (!paired) return ["bed"];
  return paneSide === "left" || paneSide === "right" ? [paneSide] : ["left", "right"];
}

// Both shows every position; a side only the positions saved for that side,
// because a side selection never moves or changes the other side.
export function positionsForPane(
  positions: SavedPosition[],
  paneKeys: string[],
): SavedPosition[] {
  return positions.filter((position) => {
    const keys = Object.keys(position.beds);
    return keys.length > 0 && keys.every((key) => paneKeys.includes(key));
  });
}

export function positionScope(position: SavedPosition): "both" | "left" | "right" | "bed" {
  const keys = Object.keys(position.beds);
  if (keys.includes("left") && keys.includes("right")) return "both";
  if (keys.includes("left")) return "left";
  if (keys.includes("right")) return "right";
  return "bed";
}

// A saved position needs every motor it moves still estimated and tracking on
// every side it covers; recall never moves only part of it.
export function canRecall(
  position: SavedPosition,
  estimatesByKey: Record<string, MotorEstimate[]>,
): boolean {
  const sides = Object.entries(position.beds);
  return sides.length > 0 && sides.every(([key, motors]) => {
    const estimates = estimatesByKey[key] ?? [];
    const saved = Object.keys(motors);
    return saved.length > 0 && saved.every((motor) =>
      estimates.find((e) => e.motor === motor)?.state === "tracking");
  });
}

export function allTracking(estimates: MotorEstimate[]): boolean {
  return estimates.length > 0 && estimates.every((e) => e.state === "tracking");
}

// Degrees for the dashed graphic, only when the axis' maximum angle is configured.
export function estimatedAngle(estimate: MotorEstimate | undefined): number | undefined {
  if (!estimate || estimate.state !== "tracking") return undefined;
  if (estimate.percent === undefined || estimate.maxAngle === undefined) return undefined;
  return (estimate.percent / 100) * estimate.maxAngle;
}
