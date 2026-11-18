import { expect, test } from "bun:test";
import { bedEntitiesForDevice } from "./discovery";
import projection from "./fixtures/agingplace069.json";
import { heldButtonMotor, movementHold } from "./hold";
import { placed } from "./test-placements";
import type { HomeAssistant } from "./types";

function fixture() {
  const calls: unknown[][] = [];
  const hass: HomeAssistant = {
    entities: {}, states: {}, devices: {}, locale: { language: "en" },
    language: "en", themes: {}, callService: async (...args: unknown[]) => { calls.push(args); },
  };
  for (const row of projection.entities) {
    const id = `${row.domain}.${row.key}`;
    hass.entities[id] = { entity_id: id, translation_key: row.translation_key, device_id: "dawn", platform: "adjustable_bed" };
    hass.states[id] = { entity_id: id, state: "unknown", last_changed: "", last_updated: "", attributes: { ...row.attributes, bed_side: "left" } };
  }
  return { hass: placed(hass), calls };
}

test("Dawn House factory projections retain three motors, app controls and bounded settings", () => {
  const { hass } = fixture();
  const bed = bedEntitiesForDevice(hass, "dawn");
  expect(projection.profile).toBe("agingplace");
  expect(bed.motors).toHaveLength(3);
  expect(bed.motors.map((motor) => motor.cover)).toEqual(expect.arrayContaining(["cover.back", "cover.legs", "cover.bed_height"]));
  expect(bed.motors.every((motor) => !motor.angle && !motor.position)).toBe(true);
  expect(bed.utility).toEqual(expect.arrayContaining(["button.agingplace_in", "button.agingplace_out", "button.agingplace_diagnostic"]));
  expect(bed.lights.numbers).toEqual(["number.agingplace_brightness", "number.agingplace_motion_minutes"]);
  expect(bed.massage.timer).toBe("number.agingplace_massage_minutes");
  expect(bed.memory).toEqual([]);
});

test("Dawn House In keeps its physical device and HA side when leasing a held action", async () => {
  const { hass, calls } = fixture();
  const motor = heldButtonMotor(hass, "button.agingplace_in");
  expect(motor?.heldControl).toEqual({ control: "in", startDelayMs: 0, releaseDelayMs: 0 });
  expect(motor).toBeDefined();
  await movementHold(hass, motor!, "up", { owner: "dawn-card", generation: 1 });
  expect(calls).toEqual([["adjustable_bed", "hold_control", { device_id: ["dawn"], control: "in", duration: 0.75, side: "left", hold_owner: "dawn-card", hold_generation: 1 }]]);
});

test("Dawn House head and aggregate height expose their source controls without a wire-side choice", async () => {
  const { hass, calls } = fixture();
  const bed = bedEntitiesForDevice(hass, "dawn");
  const height = bed.motors.find((motor) => motor.cover === "cover.bed_height");
  expect(height?.heldControls).toEqual({ up: { control: "bed_up", startDelayMs: 0, releaseDelayMs: 0 }, down: { control: "bed_down", startDelayMs: 0, releaseDelayMs: 0 } });
  expect(height?.coverStopScope).toBe("side");
  await movementHold(hass, height!, "down");
  expect(calls[0]).toEqual(["adjustable_bed", "hold_control", { device_id: ["dawn"], control: "bed_down", duration: 60, side: "left" }]);
});
