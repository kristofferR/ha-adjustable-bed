// Pytest compares this fixture to actual HA registry entries and state attributes.
import { expect, test } from "bun:test";
import metadata from "../../../../tests/fixtures/flexx_motion/card_metadata.json";
import { bedEntitiesForDevice } from "./discovery";
import { heldButtonMotor, heldReleaseButton, movementLease } from "./hold";
import type { HomeAssistant } from "./types";

test("Flexx registered motor, preset and memory gestures resolve their real release", async () => {
  const calls: Array<{ domain: string; service: string; data: unknown }> = [];
  const hass = {
    entities: Object.fromEntries(metadata.map(({ entity_id, translation_key, device_id }) => [
      entity_id, { entity_id, translation_key, device_id, platform: "adjustable_bed" },
    ])),
    states: Object.fromEntries(metadata.map(({ entity_id, attributes }) => [entity_id, {
      entity_id, attributes, state: "unknown", last_changed: "", last_updated: "",
    }])),
    devices: {},
    callService: async (domain: string, service: string, data: unknown) => {
      calls.push({ domain, service, data });
    },
  } as HomeAssistant;
  const bed = bedEntitiesForDevice(hass, "bed");
  const head = bed.motors.find((motor) => motor.heldControls?.up.control === "HeadUp");
  const release = metadata.find((row) => row.translation_key === "richmat_classic_release")!;
  expect(head?.releaseButton).toBe(release.entity_id);
  expect(head?.heldControls?.down.control).toBe("HeadDown");
  const preset = metadata.find((row) => row.attributes.held_control === "ZeroGravity")!;
  const memory = metadata.find((row) => row.attributes.held_control === "MemoryPosition1")!;
  expect(bed.presets).toContain(preset.entity_id);
  expect(bed.memory.some((slot) => slot.goto === memory.entity_id)).toBe(true);
  for (const row of [preset, memory]) {
    expect(heldReleaseButton(hass, row.entity_id)).toBe(release.entity_id);
    const gesture = heldButtonMotor(hass, row.entity_id)!;
    expect(gesture.heldControl?.control).toBe(row.attributes.held_control);
    await movementLease(hass, gesture, "up", { owner: "card", generation: 1 });
  }
  await movementLease(hass, head!, "up", { owner: "card", generation: 2 });
  await hass.callService("button", "press", { entity_id: release.entity_id });
  expect(calls.map((call) => call.service)).toEqual([
    "hold_control", "hold_control", "hold_control", "press",
  ]);
  expect(calls.slice(0, 3).map((call) => (call.data as { control: string }).control)).toEqual([
    "ZeroGravity", "MemoryPosition1", "HeadUp",
  ]);
  for (const row of metadata.filter((row) => row.attributes.requires_confirmation)) {
    expect(heldButtonMotor(hass, row.entity_id)).toBeUndefined();
  }
});
