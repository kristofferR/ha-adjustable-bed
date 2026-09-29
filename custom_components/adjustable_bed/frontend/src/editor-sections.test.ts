import { expect, test } from "bun:test";
import { presentSections } from "./editor-sections";
import type { BedEntities, HassEntity, HomeAssistant } from "./types";

const emptyBed = (): BedEntities => ({
  motors: [],
  firmness: [],
  presets: [],
  memory: [],
  presence: [],
  lights: {},
  massage: { buttons: [], numbers: [] },
  climate: { entities: [], selects: [], numbers: [] },
  utility: [],
});

const state = (entityId: string, unit: string): HassEntity => ({
  entity_id: entityId,
  state: "0",
  attributes: { unit_of_measurement: unit },
  last_changed: "",
  last_updated: "",
});

test("visual editor exposes utility controls", () => {
  const bed = emptyBed();
  bed.utility.push("button.bed_wake");

  expect(presentSections(bed, { states: {} } as HomeAssistant).utility).toBe(true);
});

test("visual editor offers the graphic only for two degree panel groups", () => {
  const bed = emptyBed();
  bed.motors = [
    { key: "back", position: "number.bed_back" },
    { key: "legs", position: "number.bed_legs" },
  ];
  const hass = {
    states: {
      "number.bed_back": state("number.bed_back", "°"),
      "number.bed_legs": state("number.bed_legs", "%"),
    },
  } as HomeAssistant;

  expect(presentSections(bed, hass).graphic).toBe(false);
  hass.states["number.bed_legs"] = state("number.bed_legs", "°");
  expect(presentSections(bed, hass).graphic).toBe(true);
  bed.motors.pop();
  expect(presentSections(bed, hass).graphic).toBe(false);
});
