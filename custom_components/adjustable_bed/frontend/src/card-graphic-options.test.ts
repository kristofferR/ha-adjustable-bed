// The opt-in percentage, lumbar and dialog options (#713) through the card's
// real templates.
import { expect, test } from "bun:test";
import type { TemplateResult } from "lit";
import type { AdjustableBedCardConfig, HomeAssistant } from "./types";

const previousWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
Object.defineProperty(globalThis, "window", {
  configurable: true,
  value: { customElements: { get: () => undefined, define: () => undefined } },
});
const { AdjustableBedCard } = await import("./adjustable-bed-card");
const { AdjustableBedCardEditor } = await import("./editor");
if (previousWindow) Object.defineProperty(globalThis, "window", previousWindow);
else Reflect.deleteProperty(globalThis, "window");

type Feedback = "°" | "%" | "estimate";

// Back 40, legs 20 and lumbar 60, as degrees, percentages or tracking estimates.
function fixture(feedback: Feedback, estimateState = "tracking"): HomeAssistant {
  const hass: HomeAssistant = {
    states: {}, entities: {}, devices: { bed: { id: "bed", name: "Bed" } },
    locale: { language: "en" }, language: "en", themes: {},
    formatEntityName: (stateObj) => hass.entities[stateObj.entity_id]?.name ?? "",
    callService: async () => undefined,
  };
  const add = (entityId: string, key: string, state: string, attributes: Record<string, unknown> = {}) => {
    hass.entities[entityId] = { entity_id: entityId, device_id: "bed", platform: "adjustable_bed", translation_key: key };
    hass.states[entityId] = { entity_id: entityId, state, last_changed: "", last_updated: "", attributes };
  };
  for (const [motor, value] of [["back", "40"], ["legs", "20"], ["lumbar", "60"]] as const) {
    add(`cover.bed_${motor}`, motor, "open");
    if (feedback === "estimate")
      add(`number.bed_${motor}_estimated`, `${motor}_position_estimated`, value, { estimate_state: estimateState });
    else add(`number.bed_${motor}_position`, `${motor}_position`, value, { unit_of_measurement: feedback });
  }
  add("button.bed_stop", "stop", "unknown");
  return hass;
}

// The rendered markup and text; event handlers and directives are placeholders.
function serialize(value: unknown): string {
  if (Array.isArray(value)) return value.map(serialize).join("");
  if (value && typeof value === "object" && "strings" in value && "values" in value) {
    const template = value as TemplateResult;
    return template.strings.map((s, i) => s + (i < template.values.length ? serialize(template.values[i]) : "")).join("");
  }
  if (typeof value === "function") return "ƒ";
  if (typeof value === "symbol" || value === undefined || value === null) return "";
  return String(value);
}

function render(hass: HomeAssistant, config: Partial<AdjustableBedCardConfig>): string {
  const card = new AdjustableBedCard();
  card.setConfig({ type: "custom:adjustable-bed-card", device_id: "bed", ...config });
  card.hass = hass;
  return serialize((card as unknown as { render(): TemplateResult }).render());
}

const SWITCHED_OFF: Partial<AdjustableBedCardConfig> = {
  show_percentage_graphic: false, show_lumbar_graphic: false, show_graphic_labels: true,
  open_dialog: false, dialog_config: { show_motors: false, show_lumbar_graphic: true },
};

test("cards without the new options render exactly as with them switched off", () => {
  for (const feedback of ["°", "%", "estimate"] as const) {
    for (const config of [{}, { layout: "compact" }, { layout: "compact", navigation_path: "/bed" }] as const) {
      expect(render(fixture(feedback), { ...config, ...SWITCHED_OFF }))
        .toBe(render(fixture(feedback), config));
    }
  }
});

test("by default the graphic keeps two degree panels and opens no dialog", () => {
  const degrees = render(fixture("°"), {});
  expect(degrees).toContain("Back 40°");
  expect(degrees).toContain("Legs 20°");
  expect(degrees).not.toContain("bed-lumbar-panel");
  // Percentages, and estimates without a maximum angle, are not drawn.
  expect(render(fixture("%"), {})).not.toContain("bed-graphic");
  expect(render(fixture("estimate"), {})).not.toContain("bed-graphic");
  const compact = render(fixture("°"), { layout: "compact" });
  expect(compact).toContain('class="compact-graphic" role="img"');
  expect(compact).not.toContain("bed-details-dialog");
  expect(compact).not.toContain("compact-open");
});

test("switched on, measured percentages and lumbar draw a schematic pose", () => {
  const out = render(fixture("%"), { show_percentage_graphic: true, show_lumbar_graphic: true });
  expect(out).toContain("Back 40%");
  expect(out).toContain("Lumbar 60%");
  expect(out).toContain("Legs 20%");
  expect(out).toContain("bed-lumbar-panel");
  expect(out).not.toContain("is-estimated");
});

test("the percentage graphic says when it draws an estimate", () => {
  const out = render(fixture("estimate"), { show_percentage_graphic: true, show_lumbar_graphic: true });
  expect(out).toContain("is-estimated");
  expect(out).toContain("Back ≈ 40%");
  expect(out).toContain("Lumbar ≈ 60%");
  expect(out).not.toContain("Back 40%");
  // Only a tracking estimate is a position; an unconfirmed one is never drawn.
  expect(render(fixture("estimate", "unconfirmed"), { show_percentage_graphic: true }))
    .not.toContain("bed-graphic");
});

test("the dialog editor stores tap to move and saved positions for the dialog only", () => {
  const editor = new AdjustableBedCardEditor() as unknown as {
    hass: HomeAssistant; setConfig(config: AdjustableBedCardConfig): void;
    dispatchEvent(event: Event): boolean; _editingDialog: boolean;
    _setOption(key: string, value: unknown): void; _toggleSection(key: string, checked: boolean): void;
  };
  const emitted: AdjustableBedCardConfig[] = [];
  // Home Assistant hands every emitted config back to the editor.
  editor.dispatchEvent = (event) => {
    const { config } = (event as CustomEvent<{ config: AdjustableBedCardConfig }>).detail;
    emitted.push(config);
    editor.setConfig(config);
    return true;
  };
  editor.hass = fixture("°");
  const root: AdjustableBedCardConfig = {
    type: "custom:adjustable-bed-card", device_id: "bed", layout: "compact",
    open_dialog: true, tap_to_move: true, show_motors: true,
  };
  editor.setConfig(root);
  editor._editingDialog = true;
  editor._setOption("tap_to_move", undefined);
  editor._toggleSection("saved_positions", false);
  expect(emitted.map((config) => config.dialog_config?.tap_to_move)).toEqual([false, false]);
  expect(emitted[1].dialog_config?.show_saved_positions).toBe(false);
  // The compact card keeps its own settings.
  expect(emitted.every((config) => config.tap_to_move === true && config.layout === "compact")).toBe(true);
});
