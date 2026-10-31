import { expect, test } from "bun:test";
import { bedGraphicPanel, bedHasGraphicFeedback, selectBedGraphicMotors } from "./bed-graphic-state";
import { renderBedGraphic } from "./bed-graphic";
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

  expect(bedHasGraphicFeedback(bed, hass)).toBe(true);
  hass.states["number.bed_legs"].attributes.unit_of_measurement = "°";
  expect(bedHasGraphicFeedback(bed, hass)).toBe(true);
  hass.states["number.bed_legs"].attributes.unit_of_measurement = "cm";
  expect(bedHasGraphicFeedback(bed, hass)).toBe(false);
});

const panelFor = (state: string, unit: string) => bedGraphicPanel(motor("head"), {
  states: { "number.bed_head": { state, attributes: { unit_of_measurement: unit } } },
} as HomeAssistant);

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
  expect(template.values).toContain("Head 50%");
  expect(template.values).toContain("Feet 25%");
  expect(template.values).not.toContain("Head 38°");
});
