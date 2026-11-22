import { expect, test } from "bun:test";
import { bedEntitiesForDevice, hasLightingControls } from "./discovery";
import { presentSections } from "./sections";
import type { BedEntities, HassEntity, HomeAssistant } from "./types";
import { placed } from "./test-placements";

const emptyBed = (): BedEntities => ({
  motors: [],
  firmness: [],
  presets: [],
  presetSaves: [],
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

test("visual editor offers lighting for a discovered state-only bed", () => {
  // Sleeptracker's safety light reading, with its toggle button disabled.
  const entityId = "binary_sensor.bed_safety_light";
  const hass: HomeAssistant = placed({
    entities: {
      [entityId]: {
        entity_id: entityId,
        translation_key: "sleeptracker_light_on",
        device_id: "bed",
        platform: "adjustable_bed",
      },
    },
    states: {},
    devices: {},
    locale: { language: "en" },
    language: "en",
    themes: {},
    callService: async () => undefined,
  });
  const bed = bedEntitiesForDevice(hass, "bed");

  expect(bed.lights.state).toBe(entityId);
  expect(hasLightingControls(bed.lights)).toBe(false);
  expect(presentSections(bed, hass).lighting).toBe(true);
  expect(presentSections(bedEntitiesForDevice(hass, "other"), hass).lighting).toBe(
    false,
  );
});

test("visual editor offers bounded mood, pending floor timer and massage-only sections", () => {
  const hass = placed({ states: {} } as HomeAssistant);
  const bed = emptyBed();
  bed.lights.mood = { selects: ["select.palette"], numbers: [] };
  expect(presentSections(bed, hass).lighting).toBe(true);
  expect(presentSections(bed, hass).massage).toBe(false);
  bed.lights = { timerMinutes: "number.timer", timerToggle: "button.timer" };
  expect(presentSections(bed, hass).lighting).toBe(true);
  bed.lights = {};
  bed.massage.selects = ["select.wave"];
  expect(presentSections(bed, hass).lighting).toBe(false);
  expect(presentSections(bed, hass).massage).toBe(true);
});

test("visual editor offers the graphic for degree and percentage panel groups", () => {
  const bed = emptyBed();
  bed.motors = [
    { key: "back", position: "number.bed_back" },
    { key: "legs", position: "number.bed_legs" },
  ];
  const hass = placed({
    states: {
      "number.bed_back": state("number.bed_back", "°"),
      "number.bed_legs": state("number.bed_legs", "%"),
    },
  } as HomeAssistant);

  expect(presentSections(bed, hass).graphic).toBe(false);
  expect(presentSections(bed, hass, {type: "custom:adjustable-bed-card", show_percentage_graphic: true}).graphic).toBe(true);
  hass.states["number.bed_legs"] = state("number.bed_legs", "°");
  expect(presentSections(bed, hass).graphic).toBe(true);
  bed.motors.pop();
  expect(presentSections(bed, hass).graphic).toBe(false);
});

test("utility and motors count every row the card renders", () => {
  const hass = { states: {} } as HomeAssistant;
  for (const fill of [
    (b: BedEntities) => { b.utilityNumbers = ["number.bed_timer"]; },
    (b: BedEntities) => { b.utilitySelects = ["select.bed_mode"]; },
    (b: BedEntities) => { b.utilityStates = ["sensor.bed_status"]; },
    (b: BedEntities) => { b.utilitySwitches = ["switch.bed_beep"]; },
  ]) {
    const bed = emptyBed();
    fill(bed);
    expect(presentSections(bed, hass).utility).toBe(true);
  }
  const sideOnly = emptyBed();
  sideOnly.controlSide = "select.bed_side";
  expect(presentSections(sideOnly, hass).motors).toBe(true);
  const positionOnly = emptyBed();
  positionOnly.motors = [{ key: "back", position: "number.bed_back" }];
  expect(presentSections(positionOnly, hass).motors).toBe(true);
  expect(presentSections(emptyBed(), hass).motors).toBe(false);
});
