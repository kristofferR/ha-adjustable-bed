// Saved positions and the reference dialog through the card's real templates (#601).
import { expect, test } from "bun:test";
import type { TemplateResult } from "lit";
import { bedEntitiesForDevice } from "./discovery";
import type { HomeAssistant } from "./types";

await import("lit");
const previousWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
const registry = new Map<string, CustomElementConstructor>();
Object.defineProperty(globalThis, "window", { configurable: true, value: { customElements: {
  get: (tag: string) => registry.get(tag),
  define: (tag: string, element: CustomElementConstructor) => registry.set(tag, element),
  whenDefined: () => new Promise<void>(() => {}),
} } });
const { AdjustableBedCard } = await import("./adjustable-bed-card");
if (previousWindow) Object.defineProperty(globalThis, "window", previousWindow);
else Reflect.deleteProperty(globalThis, "window");

type Call = { service: string; data: Record<string, unknown> };

function fixture(backState: "tracking" | "unknown") {
  const calls: Call[] = [];
  const entity = (id: string, key: string) => ({
    entity_id: id, platform: "adjustable_bed", device_id: "bed", translation_key: key,
  });
  const hass = {
    entities: {
      "cover.back": entity("cover.back", "back"),
      "cover.legs": entity("cover.legs", "legs"),
      "number.back_est": entity("number.back_est", "back_position_estimated"),
      "number.legs_est": entity("number.legs_est", "legs_position_estimated"),
      "sensor.saved": entity("sensor.saved", "saved_positions"),
    },
    states: {
      "cover.back": { entity_id: "cover.back", state: "open", attributes: {} },
      "cover.legs": { entity_id: "cover.legs", state: "open", attributes: {} },
      "number.back_est": {
        entity_id: "number.back_est",
        state: backState === "tracking" ? "42" : "unknown",
        attributes: { estimate_state: backState, last_estimate: 42, estimate_reason: "remote" },
      },
      "number.legs_est": {
        entity_id: "number.legs_est", state: "20", attributes: { estimate_state: "tracking" },
      },
      "sensor.saved": {
        entity_id: "sensor.saved", state: "1",
        attributes: { positions: [{ id: "p1", name: "Reading", button: true, beds: { bed: { back: 45, legs: 20 } } }] },
      },
    },
    devices: {}, themes: {}, language: "en", locale: { language: "en" },
    callService: async (_domain: string, service: string, data: Record<string, unknown>) => {
      calls.push({ service, data });
    },
  } as unknown as HomeAssistant;
  const card = new AdjustableBedCard() as unknown as Record<string, unknown> & {
    hass: HomeAssistant;
    _estimateDialog?: Record<string, unknown>;
    _savedPositions(ctx: unknown): TemplateResult;
    _estimateDialogTemplate(): TemplateResult;
    _motors(bed: unknown, a?: unknown, b?: unknown, ctx?: unknown): TemplateResult;
  };
  card.hass = hass;
  (card as unknown as { _config: unknown })._config = { type: "custom:adjustable-bed-card", device_id: "bed" };
  const bed = bedEntitiesForDevice(hass, "bed");
  const ctx = {
    deviceId: "bed", paired: false,
    sides: [{ key: "bed", deviceId: "bed", label: "Bed", motors: bed.motors }],
    savedPositions: bed.savedPositions,
  };
  return { card, calls, ctx, bed };
}

function templates(value: unknown, out: TemplateResult[] = []): TemplateResult[] {
  if (Array.isArray(value)) value.forEach((v) => templates(v, out));
  else if (value && typeof value === "object" && "strings" in value && "values" in value) {
    out.push(value as TemplateResult);
    (value as TemplateResult).values.forEach((v) => templates(v, out));
  }
  return out;
}

function text(template: TemplateResult): string {
  return templates(template)
    .flatMap((t) => [...t.strings, ...t.values.filter((v) => typeof v === "string")])
    .join("");
}

function clicks(template: TemplateResult, marker: string): Array<() => void> {
  return templates(template)
    .filter((t) => t.strings.join("").includes(marker))
    .flatMap((t) => t.strings.flatMap((s, i) => (s.endsWith("@click=") ? [t.values[i] as () => void] : [])));
}

test("an unknown estimate disables saved positions and shows the reason", () => {
  const { card, ctx, bed } = fixture("unknown");
  const saved = card._savedPositions(ctx);
  const tile = templates(saved).find((t) => t.strings.join("").includes("tile-sublabel") || t.values.includes("Reading"));
  expect(tile?.values).toContain(true); // ?disabled
  const motors = text(card._motors(bed, undefined, undefined, ctx));
  expect(motors).toContain("Position unknown: you reported using the remote");
  expect(motors).toContain("Unknown");
});

test("tapping a tracking saved position recalls it by id", async () => {
  const { card, ctx, calls } = fixture("tracking");
  const [recall] = clicks(card._savedPositions(ctx), "tile-label")
    .slice(1); // the section template itself owns the Save tile handler
  recall();
  await Promise.resolve();
  expect(calls).toEqual([{ service: "recall_position", data: { device_id: "bed", position: "p1" } }]);
});

test("lower to flat moves first, then the user confirms flat", async () => {
  const { card, ctx, calls } = fixture("unknown");
  card._estimateDialog = { kind: "reference", ctx, choice: "lower", phase: "choose" };
  let primary = clicks(card._estimateDialogTemplate(), "dialog-btn primary").at(-1)!;
  primary();
  expect(calls.map((c) => c.service)).toEqual(["lower_to_flat"]);
  // Confirming flat waits for the lowering to finish.
  expect(card._estimateDialog?.phase).toBe("lowering");
  clicks(card._estimateDialogTemplate(), "dialog-btn primary").at(-1)!();
  expect(calls.map((c) => c.service)).toEqual(["lower_to_flat"]);
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(card._estimateDialog?.phase).toBe("lowered");
  primary = clicks(card._estimateDialogTemplate(), "dialog-btn primary").at(-1)!;
  primary();
  expect(calls.at(-1)).toEqual({
    service: "set_position_reference", data: { device_id: "bed", motors: ["back", "legs"] },
  });
  expect(card._estimateDialog).toBeUndefined();
});

test("closing the dialog while lowering stops the bed", () => {
  const { card, ctx, calls } = fixture("unknown");
  card._estimateDialog = { kind: "reference", ctx, choice: "lower", phase: "lowering" };
  (card as unknown as { _closeEstimateDialog(): void })._closeEstimateDialog();
  expect(calls).toEqual([{ service: "stop_all", data: { device_id: "bed" } }]);
  expect(card._estimateDialog).toBeUndefined();
});

test("removing the card while lowering stops the bed", () => {
  const { card, ctx, calls } = fixture("unknown");
  card._estimateDialog = { kind: "reference", ctx, choice: "lower", phase: "lowering" };
  // The lifecycle detaches window listeners. Use a window of its own rather
  // than whatever another test file left behind, and restore it afterwards.
  const previous = Object.getOwnPropertyDescriptor(globalThis, "window");
  Object.defineProperty(globalThis, "window", { configurable: true, value: new EventTarget() });
  try {
    (card as unknown as { disconnectedCallback(): void }).disconnectedCallback();
  } finally {
    if (previous) Object.defineProperty(globalThis, "window", previous);
    else Reflect.deleteProperty(globalThis, "window");
  }
  expect(calls).toEqual([{ service: "stop_all", data: { device_id: "bed" } }]);
  expect(card._estimateDialog).toBeUndefined();
});

test("a failed lowering never offers to confirm flat", async () => {
  const { card, ctx } = fixture("unknown");
  card.hass.callService = async () => { throw new Error("not connected"); };
  card._estimateDialog = { kind: "reference", ctx, choice: "lower", phase: "choose" };
  clicks(card._estimateDialogTemplate(), "dialog-btn primary").at(-1)!();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(card._estimateDialog?.phase).toBe("choose");
});

test("saving names the current position and keeps the button choice", () => {
  const { card, ctx, calls } = fixture("tracking");
  card._estimateDialog = { kind: "save", ctx, name: " Reading ", button: false };
  clicks(card._estimateDialogTemplate(), "dialog-btn primary").at(-1)!();
  expect(calls).toEqual([{
    service: "save_position", data: { device_id: "bed", name: "Reading", create_button: false },
  }]);
});

test("compact readouts show estimate-only motors as the graphic labels them", () => {
  const entity = (id: string, key: string) => ({
    entity_id: id, platform: "adjustable_bed", device_id: "bed", translation_key: key,
  });
  const estimate = (id: string, state: string, attributes: Record<string, unknown>) =>
    ({ entity_id: id, state, attributes });
  const hass = {
    entities: Object.fromEntries(["back_up", "back_down", "legs_up", "legs_down"]
      .map((key) => [`button.bed_${key}`, entity(`button.bed_${key}`, key)])),
    states: {} as Record<string, unknown>,
    devices: {}, themes: {}, language: "en", locale: { language: "en" },
    callService: async () => undefined,
  } as unknown as HomeAssistant;
  for (const motor of ["back", "legs"])
    hass.entities[`number.bed_${motor}_est`] = entity(`number.bed_${motor}_est`, `${motor}_position_estimated`);
  const card = new AdjustableBedCard() as unknown as {
    hass: HomeAssistant; _config: unknown; _compactReadouts(sides: unknown[]): TemplateResult;
  };
  card.hass = hass;
  card._config = { type: "custom:adjustable-bed-card", device_id: "bed", layout: "compact" };
  const readout = (back: unknown, legs: unknown): string => {
    hass.states["number.bed_back_est"] = back as never;
    hass.states["number.bed_legs_est"] = legs as never;
    const bed = bedEntitiesForDevice(hass, "bed");
    expect(bed.motors.every((m) => m.estimate && !m.cover)).toBe(true);
    return text(card._compactReadouts([{ key: "both", label: "Bed", bed }]));
  };
  expect(readout(
    estimate("number.bed_back_est", "42", { estimate_state: "tracking" }),
    estimate("number.bed_legs_est", "unknown", { estimate_state: "unconfirmed", last_estimate: 20 }),
  )).toContain("≈ 42% / Was ≈ 20%");
  // Unknown, and not calibrated (unavailable), read "?" as on the graphic.
  const unknown = readout(
    estimate("number.bed_back_est", "unknown", { estimate_state: "unknown" }),
    estimate("number.bed_legs_est", "unavailable", {}),
  );
  expect(unknown).toContain("? / ?");
  expect(unknown).not.toContain("Position feedback unavailable");
});
