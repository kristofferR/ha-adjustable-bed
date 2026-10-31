import { expect, test } from "bun:test";
import { bedGraphicMotorOrder, bedGraphicPanel, bedHasGraphicFeedback, selectBedGraphicMotors } from "./bed-graphic-state";
import { bedGraphicGeometry, renderBedGraphic, renderDualBedGraphic } from "./bed-graphic";
import type { BedEntities, HomeAssistant, MotorEntity } from "./types";

const motor = (key: string): MotorEntity => ({ key, position: `number.bed_${key}` });

test("bed graphic requires both upper and lower feedback groups", () => {
  expect(selectBedGraphicMotors([motor("back")])).toBeUndefined();
  expect(selectBedGraphicMotors([motor("legs")])).toBeUndefined();
  expect(selectBedGraphicMotors([motor("back"), motor("head")])).toBeUndefined();
  expect(selectBedGraphicMotors([motor("legs"), motor("feet")])).toBeUndefined();
});

test("bed graphic maps one upper and one lower feedback axis", () => {
  const back = motor("back");
  const feet = motor("feet");

  expect(selectBedGraphicMotors([feet, back])).toEqual({ upper: back, lower: feet });
});

test("lumbar is selected as a distinct middle section, not the pillow or head tilt", () => {
  const head = motor("head"), lumbar = motor("lumbar"), feet = motor("feet");
  expect(selectBedGraphicMotors([head, motor("tilt"), lumbar, feet])).toEqual({upper: head, middle: lumbar, lower: feet});
  expect(bedGraphicMotorOrder([head, feet, lumbar]).map(m => m.key)).toEqual(["head", "feet", "lumbar"]);
  expect(bedGraphicMotorOrder([head, feet, lumbar], true).map(m => m.key)).toEqual(["head", "lumbar", "feet"]);
});

test("three-section geometry gives lumbar its own space and independent lift", () => {
  const opts = {upper: {angle: 30}, middle: {angle: 0}, lower: {angle: 15}, moving: false};
  const flatLumbar = bedGraphicGeometry(opts);
  const raisedLumbar = bedGraphicGeometry({...opts, middle: {angle: 75}});
  expect(flatLumbar.upperWidth).toBe(80);
  expect(flatLumbar.lowerX).toBe(178);
  expect(flatLumbar.lowerWidth).toBe(80);
  expect(raisedLumbar.upperTransform).toBe(flatLumbar.upperTransform);
  expect(raisedLumbar.lowerTransform).toBe(flatLumbar.lowerTransform);
  expect(raisedLumbar.middlePath).not.toBe(flatLumbar.middlePath);
});

test("lumbar feedback is labeled independently in both single and paired graphics", () => {
  const side = {upper: {angle: 30, label: "Head", readout: "40%"}, middle: {angle: 15, label: "Lumbar", readout: "20%"}, lower: {angle: 0, label: "Feet", readout: "0%"}, moving: false};
  const flatten = (template: unknown): string => {
    if (typeof template !== "object" || template === null) return String(template);
    const t = template as {strings?: readonly string[]; values?: unknown[]};
    return [...(t.strings ?? []), ...(t.values ?? []).map(flatten)].join(" ");
  };
  expect(flatten(renderBedGraphic(side))).toContain("Lumbar 20%");
  expect(flatten(renderBedGraphic({...side, middle: {label: "Lumbar"}}))).toContain("Lumbar ?");
  expect(flatten(renderDualBedGraphic({left: side, right: side}))).toContain("bed-lumbar-panel");
});

test("bed graphic accepts degree and percentage feedback for both panels", () => {
  const bed = {
    motors: [motor("back"), motor("legs")],
  } as BedEntities;
  const hass = {
    states: {
      "number.bed_back": { attributes: { unit_of_measurement: "°" } },
      "number.bed_legs": { attributes: { unit_of_measurement: "%" } },
    },
  } as HomeAssistant;

  expect(bedHasGraphicFeedback(bed, hass)).toBe(false);
  expect(bedHasGraphicFeedback(bed, hass, true)).toBe(true);
  hass.states["number.bed_legs"].attributes.unit_of_measurement = "°";
  expect(bedHasGraphicFeedback(bed, hass)).toBe(true);
  hass.states["number.bed_legs"].attributes.unit_of_measurement = "cm";
  expect(bedHasGraphicFeedback(bed, hass)).toBe(false);
});

const panelFor = (state: string, unit: string) => bedGraphicPanel(motor("head"), {
  states: { "number.bed_head": { state, attributes: { unit_of_measurement: unit } } },
} as HomeAssistant, true);

test("percentage graphics are opt-in while measured degree feedback keeps working", () => {
  const hass = {states: {"number.bed_head": {state: "50", attributes: {unit_of_measurement: "%"}}}} as HomeAssistant;
  expect(bedGraphicPanel(motor("head"), hass)).toBeUndefined();
  expect(bedGraphicPanel(motor("head"), hass, false)).toBeUndefined();
  expect(bedGraphicPanel(motor("head"), hass, true)?.readout).toBe("50%");
  hass.states["number.bed_head"].attributes.unit_of_measurement = "°";
  expect(bedGraphicPanel(motor("head"), hass)?.angle).toBe(50);
});

test("percentage poses preserve percent labels at flat, intermediate and full travel", () => {
  expect(panelFor("0", "%")).toEqual({ angle: 0, readout: "0%" });
  expect(panelFor("50", "%")).toEqual({ angle: 37.5, readout: "50%" });
  expect(panelFor("100", "%")).toEqual({ angle: 75, readout: "100%" });
  expect(panelFor("-10", "%")).toEqual({ angle: 0, readout: "0%" });
  expect(panelFor("120", "%")).toEqual({ angle: 75, readout: "100%" });
});

test("measured angles retain their existing rendering", () => {
  expect(panelFor("42.5", "°")).toEqual({ angle: 42.5 });
});

test("missing, invalid or unsupported feedback cannot become a flat pose", () => {
  for (const state of ["unknown", "unavailable", "", " ", "NaN", "Infinity", "12bad"]) {
    expect(panelFor(state, "%")).toBeUndefined();
    expect(panelFor(state, "°")).toBeUndefined();
  }
  expect(panelFor("50", "cm")).toBeUndefined();
  expect(bedGraphicPanel(motor("head"), { states: {} } as HomeAssistant)).toBeUndefined();
});

test("rendered schematic labels never present percentage travel as measured degrees", () => {
  const template = renderBedGraphic({
    upper: { label: "Head", ...panelFor("50", "%") },
    lower: { label: "Feet", ...panelFor("25", "%") },
    moving: false,
  });
  expect(template.values).toContain("rotate(37.5 150 70)");
  expect(template.values).toContain("rotate(-18.75 150 70)");
  const labels = template.values.flatMap(value =>
    value && typeof value === "object" && "values" in value
      ? (value as {values: unknown[]}).values : []);
  expect(labels).toContain("Head 50%");
  expect(labels).toContain("Feet 25%");
  expect(labels).not.toContain("Head 38°");
});
