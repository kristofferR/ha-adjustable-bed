// The opt-in percentage, lumbar and dialog options (#713) through the card's
// real templates.
import { expect, test } from "bun:test";
import type { TemplateResult } from "lit";
import type { AdjustableBedCardConfig, HomeAssistant } from "./types";
import { placed } from "./test-placements";

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

// Back 40, legs 20 and lumbar 60, as degrees, percentages or estimates.
// Estimates exist only for back and legs, never lumbar.
function fixture(feedback: Feedback, estimateState = "tracking", maxAngle?: number): HomeAssistant {
  const hass: HomeAssistant = placed({
    states: {}, entities: {}, devices: { bed: { id: "bed", name: "Bed" } },
    locale: { language: "en" }, language: "en", themes: {},
    formatEntityName: (stateObj) => hass.entities[stateObj.entity_id]?.name ?? "",
    callService: async () => undefined,
  });
  const add = (entityId: string, key: string, state: string, attributes: Record<string, unknown> = {}) => {
    hass.entities[entityId] = { entity_id: entityId, device_id: "bed", platform: "adjustable_bed", translation_key: key };
    hass.states[entityId] = { entity_id: entityId, state, last_changed: "", last_updated: "", attributes };
  };
  for (const [motor, value] of [["back", "40"], ["legs", "20"], ["lumbar", "60"]] as const) {
    add(`cover.bed_${motor}`, motor, "open");
    if (feedback !== "estimate")
      add(`number.bed_${motor}_position`, `${motor}_position`, value, { unit_of_measurement: feedback });
    else if (motor !== "lumbar")
      add(`number.bed_${motor}_estimated`, `${motor}_position_estimated`, value, {
        estimate_state: estimateState, last_estimate: Number(value), ...(maxAngle ? { max_angle: maxAngle } : {}),
      });
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

// The labels beneath the graphic; a stacked name and value joined by a space.
function graphicLabels(markup: string): string[] {
  return [...markup.matchAll(
    /class="bed-graphic-label">(?:<tspan[^>]*>([^<]*)<\/tspan><tspan[^>]*>([^<]*)<\/tspan>|([^<]*))<\/text>/g,
  )].map(([, name, value, inline]) => inline ?? `${name} ${value}`);
}

// The visible text of the bed graphic's container, chip included.
function graphicText(markup: string): string[] {
  const start = markup.search(/class="(compact-)?graphic"/);
  const end = markup.indexOf("</div>", markup.indexOf("</svg>", start));
  return markup.slice(start, end).split(/<[^>]*>/).slice(1).map((text) => text.trim()).filter(Boolean);
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
  expect(graphicLabels(degrees)).toEqual(["Back 40°", "Legs 20°"]);
  expect(degrees).not.toContain("bed-lumbar-panel");
  // Percentages, and estimates without a maximum angle, are not drawn.
  expect(render(fixture("%"), {})).not.toContain("bed-graphic");
  expect(render(fixture("estimate"), {})).not.toContain("bed-graphic");
  expect(render(fixture("estimate", "unconfirmed", 75), {})).not.toContain("bed-graphic");
  // A tracking estimate with a maximum angle keeps v5's dashed degrees, unchipped.
  const estimate = render(fixture("estimate", "tracking", 75), {});
  expect(graphicLabels(estimate)).toEqual(["Back ≈ 30°", "Legs ≈ 15°"]);
  expect(estimate).toContain("is-estimated");
  expect(render(fixture("estimate", "tracking", 75), { layout: "compact" })).not.toContain("compact-estimate-chip");
  const compact = render(fixture("°"), { layout: "compact" });
  expect(compact).toContain('class="compact-graphic" role="img"');
  expect(compact).not.toContain("bed-details-dialog");
  expect(compact).not.toContain("compact-open");
});

test("switched on, measured percentages and lumbar draw a solid pose with stacked labels", () => {
  const out = render(fixture("%"), { show_percentage_graphic: true, show_lumbar_graphic: true });
  expect(graphicLabels(out)).toEqual(["Back 40%", "Lumbar 60%", "Legs 20%"]);
  expect(out).toContain("<tspan");
  expect(out).toContain("bed-lumbar-panel");
  expect(out).toContain("is-measured");
  expect(out).not.toMatch(/is-(estimated|unconfirmed|unknown)/);
});

test("a measured percentage graphic carries no chip or caption, only its labels", () => {
  const options = { show_percentage_graphic: true, show_lumbar_graphic: true };
  for (const layout of ["full", "compact"] as const) {
    const out = render(fixture("%"), { ...options, layout });
    expect(graphicText(out)).toEqual(["Back", "40%", "Lumbar", "60%", "Legs", "20%"]);
    expect(out).not.toMatch(/estimate-chip|estimate-footer|Estimated from movement time/);
  }
  // An estimate does carry its chip.
  expect(graphicText(render(fixture("estimate"), { ...options, layout: "compact" }))).toContain("Estimated");
});

test("the percentage graphic draws each estimate state in its own style", () => {
  const options = { show_percentage_graphic: true, show_lumbar_graphic: true };
  const cases = [
    ["tracking", ["Back ≈ 40%", "Lumbar ?", "Legs ≈ 20%"], "is-estimated", "Estimated"],
    ["unconfirmed", ["Back Was ≈ 40%", "Lumbar ?", "Legs Was ≈ 20%"], "is-unconfirmed", "Unconfirmed"],
    ["unknown", ["Back ?", "Lumbar ?", "Legs ?"], "is-unknown", "Unknown"],
  ] as const;
  for (const [state, labels, style, chip] of cases) {
    const out = render(fixture("estimate", state), options);
    expect(graphicLabels(out)).toEqual([...labels]);
    expect(out).toContain(style);
    expect(out).not.toContain("is-measured");
    // There is no lumbar estimate, so lumbar is unknown in every state.
    expect(out).toMatch(/bed-lumbar-panel is-unknown/);
    const compact = render(fixture("estimate", state), { ...options, layout: "compact" });
    expect(compact).toContain(`chip-${state === "tracking" ? "estimated" : state}`);
    expect(compact).toContain(chip);
  }
  // Unknown is drawn flat.
  const unknown = render(fixture("estimate", "unknown"), options);
  expect(unknown).toContain("rotate(0 122 70)");
  expect(unknown).toContain("rotate(0 178 70)");
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
