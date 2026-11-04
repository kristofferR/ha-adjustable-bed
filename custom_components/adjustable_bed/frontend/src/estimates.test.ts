import { expect, test } from "bun:test";
import { bedEntitiesForDevice } from "./discovery";
import {
  canRecall,
  estimateAlert,
  estimateChip,
  estimateReadout,
  estimatedAngle,
  motorEstimate,
  positionScope,
  positionsForPane,
  savedPositions,
  type MotorEstimate,
  type SavedPosition,
} from "./estimates";
import type { HomeAssistant } from "./types";

const text = (key: string, params?: Record<string, string>): string =>
  `${key}${params?.percent !== undefined ? `:${params.percent}` : ""}`;

function hass(states: Record<string, { state: string; attributes?: Record<string, unknown> }>) {
  const entity = (id: string, key: string, device = "bed") => ({
    entity_id: id, platform: "adjustable_bed", device_id: device, translation_key: key,
  });
  return {
    entities: {
      "number.back_est": entity("number.back_est", "back_position_estimated"),
      "number.legs_est": entity("number.legs_est", "legs_position_estimated"),
      "button.set_back": entity("button.set_back", "set_back_reference"),
      "button.remote": entity("button.remote", "estimate_remote_used"),
      "sensor.saved": entity("sensor.saved", "saved_positions"),
      "cover.back": entity("cover.back", "back"),
    },
    states: Object.fromEntries(
      Object.entries(states).map(([id, s]) => [id, { entity_id: id, attributes: {}, ...s }]),
    ),
    devices: {}, themes: {}, language: "en", locale: { language: "en" },
    callService: async () => undefined,
  } as unknown as HomeAssistant;
}

test("discovery attaches estimates and references to their motors", () => {
  const bed = bedEntitiesForDevice(hass({}), "bed");
  const back = bed.motors.find((m) => m.key === "back");
  expect(back).toMatchObject({
    cover: "cover.back", estimate: "number.back_est", reference: "button.set_back",
  });
  expect(back?.position).toBeUndefined();
  expect(bed.estimateRemote).toBe("button.remote");
  expect(bed.savedPositions).toBe("sensor.saved");
  // None of them are utility tiles or presets.
  expect(bed.utility).toEqual([]);
  expect(bed.presets).toEqual([]);
});

test("readouts never show a guess as a bare number", () => {
  const h = hass({
    "number.back_est": { state: "42", attributes: { estimate_state: "tracking", last_estimate: 42.4 } },
    "number.legs_est": { state: "unknown", attributes: { estimate_state: "unconfirmed", last_estimate: 20 } },
  });
  const back = motorEstimate(h, { key: "back", estimate: "number.back_est" })!;
  const legs = motorEstimate(h, { key: "legs", estimate: "number.legs_est" })!;
  expect(estimateReadout(back, text)).toBe("estimate.readout:42");
  expect(estimateReadout(legs, text)).toBe("estimate.readout_was:20");
  const unknown = motorEstimate(hass({
    "number.back_est": { state: "unknown", attributes: { estimate_state: "unknown", estimate_reason: "remote" } },
  }), { key: "back", estimate: "number.back_est" })!;
  expect(estimateReadout(unknown, text)).toBe("estimate.unknown");
  const uncalibrated = motorEstimate(hass({ "number.back_est": { state: "unavailable" } }),
    { key: "back", estimate: "number.back_est" })!;
  expect(uncalibrated.state).toBe("not_calibrated");
  expect(estimateReadout(uncalibrated, text)).toBe("estimate.not_calibrated");
});

const est = (motor: string, state: MotorEstimate["state"], extra: Partial<MotorEstimate> = {}) =>
  ({ motor, entityId: `number.${motor}`, state, ...extra }) as MotorEstimate;

test("alerts and chips put the most actionable state first", () => {
  expect(estimateChip([])).toBeUndefined();
  expect(estimateChip([est("back", "tracking")])).toBe("estimated");
  expect(estimateChip([est("back", "tracking"), est("legs", "unconfirmed")])).toBe("unconfirmed");
  expect(estimateAlert([est("back", "tracking")])).toBeUndefined();
  expect(estimateAlert([est("back", "unconfirmed"), est("legs", "not_calibrated")]))
    .toEqual({ kind: "calibrate" });
  expect(estimateAlert([est("back", "unconfirmed"), est("legs", "unknown", { reason: "hardware_preset" })]))
    .toEqual({ kind: "unknown", reason: "hardware_preset" });
  expect(estimateAlert([est("back", "unconfirmed", { percent: 42 })])?.kind).toBe("unconfirmed");
});

const reading: SavedPosition = {
  id: "a", name: "Reading", button: true,
  beds: { left: { back: 45, legs: 20 }, right: { back: 40, legs: 25 } },
};
const snore: SavedPosition = { id: "b", name: "Snore", button: false, beds: { left: { back: 18 } } };

test("paired panes: both shows every position, a side only its own", () => {
  expect(positionsForPane([reading, snore], ["left", "right"])).toEqual([reading, snore]);
  expect(positionsForPane([reading, snore], ["left"])).toEqual([snore]);
  expect(positionsForPane([reading, snore], ["right"])).toEqual([]);
  expect(positionScope(reading)).toBe("both");
  expect(positionScope(snore)).toBe("left");
});

test("a both-sides position waits while either side is not tracking", () => {
  const tracking = [est("back", "tracking"), est("legs", "tracking")];
  expect(canRecall(reading, { left: tracking, right: tracking })).toBe(true);
  expect(canRecall(reading, { left: tracking, right: [est("back", "unknown"), est("legs", "tracking")] }))
    .toBe(false);
  expect(canRecall(snore, { left: tracking, right: [est("back", "unknown")] })).toBe(true);
  // A saved motor that is no longer estimated blocks the whole position.
  expect(canRecall(snore, { left: [] })).toBe(false);
  expect(canRecall(reading, { left: [est("back", "tracking")], right: tracking })).toBe(false);
});

test("saved positions are read from the sensor and invalid rows dropped", () => {
  const h = hass({ "sensor.saved": { state: "2", attributes: { positions: [
    { id: "a", name: "Reading", button: true, beds: { bed: { back: 40 } } },
    { name: "broken" },
  ] } } });
  expect(savedPositions(h, "sensor.saved")).toEqual([
    { id: "a", name: "Reading", button: true, beds: { bed: { back: 40 } } },
  ]);
});

test("the dashed graphic needs a tracking estimate and a configured max angle", () => {
  expect(estimatedAngle(est("back", "tracking", { percent: 50, maxAngle: 60 }))).toBe(30);
  expect(estimatedAngle(est("back", "tracking", { percent: 50 }))).toBeUndefined();
  expect(estimatedAngle(est("back", "unconfirmed", { percent: 50, maxAngle: 60 }))).toBeUndefined();
});
