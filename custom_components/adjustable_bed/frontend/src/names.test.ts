import { expect, test } from "bun:test";
import type { TemplateResult } from "lit";
import { deviceName, entityLabel } from "./names";
import type { EntityNameItem, HassEntity, HomeAssistant } from "./types";

const previousWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
Object.defineProperty(globalThis, "window", {
  configurable: true,
  value: { customElements: { get: () => undefined, define: () => undefined } },
});
const { AdjustableBedCard } = await import("./adjustable-bed-card");
if (previousWindow) Object.defineProperty(globalThis, "window", previousWindow);
else Reflect.deleteProperty(globalThis, "window");

// HA's formatter for one `{ type: "entity" }` item: the entity's own name, or
// its device's name when it has none. The friendly name is never consulted.
function fixture(): HomeAssistant {
  const hass: HomeAssistant = {
    states: {}, entities: {}, devices: {
      bed: { id: "bed", name: "Bedroom bed" },
      pair: { id: "pair", name: "Bed" },
      left: { id: "left", name: "Left", parent_device_id: "pair" },
      right: { id: "right", name: "Right", parent_device_id: "pair" },
    },
    locale: { language: "en" }, language: "en", themes: {},
    formatEntityName: (stateObj: HassEntity, name?: string | EntityNameItem | EntityNameItem[]) => {
      expect(name).toEqual({ type: "entity" });
      const entry = hass.entities[stateObj.entity_id];
      return entry?.name || deviceName(hass, entry?.device_id) || "";
    },
    callService: async () => undefined,
  };
  return hass;
}

function add(hass: HomeAssistant, entityId: string, deviceId: string, key: string, name?: string, side?: string) {
  hass.entities[entityId] = { entity_id: entityId, device_id: deviceId, platform: "adjustable_bed", translation_key: key, name };
  // A pre-2026.11 name HA keeps in the attribute until the entity is renamed.
  hass.states[entityId] = { entity_id: entityId, state: "unknown", last_changed: "", last_updated: "",
    attributes: { friendly_name: `Old name ${name}`, ...(side ? { bed_side: side } : {}) } };
}

function texts(template: TemplateResult): string[] {
  return template.values.flatMap((value) => (Array.isArray(value) ? value : [value]))
    .flatMap((value) => typeof value === "string" ? [value]
      : value && typeof value === "object" && "strings" in value ? texts(value as TemplateResult) : []);
}

function render(hass: HomeAssistant, config: Record<string, unknown>): string[] {
  const card = new AdjustableBedCard();
  card.setConfig({ type: "custom:adjustable-bed-card", ...config });
  card.hass = hass;
  return texts((card as unknown as { render(): TemplateResult }).render());
}

test("a standalone bed labels entities by their own name", () => {
  const hass = fixture();
  add(hass, "button.bed_flat", "bed", "preset_flat", "Flat");
  const labels = render(hass, { device_id: "bed" });
  expect(labels).toContain("Bedroom bed");
  expect(labels).toContain("Flat");
  expect(labels.some((label) => label.includes("Old name"))).toBe(false);
});

test("a paired side labels its entities by their own name under its side tab", () => {
  const hass = fixture();
  add(hass, "button.pair_flat", "pair", "preset_flat", "Flat", "both");
  add(hass, "button.left_zero_g", "left", "preset_zero_g", "Zero G", "left");
  add(hass, "button.right_zero_g", "right", "preset_zero_g", "Zero G", "right");
  const labels = render(hass, { device_id: "pair", default_target: "left" });
  expect(labels).toEqual(expect.arrayContaining(["Bed", "Left", "Right", "Zero G"]));
  expect(labels.some((label) => label.includes("Old name") || label.startsWith("Left "))).toBe(false);
});

test("older HA renders standalone and paired labels without a name formatter", () => {
  const hass = fixture();
  delete hass.formatEntityName;
  add(hass, "button.bed_flat", "bed", "preset_flat", "Flat");
  hass.states["button.bed_flat"].attributes.friendly_name = "Bedroom bed Lie flat";
  expect(render(hass, { device_id: "bed" })).toContain("Lie flat");

  add(hass, "button.pair_flat", "pair", "preset_flat", "Flat", "both");
  add(hass, "button.left_zero_g", "left", "preset_zero_g", "Zero G", "left");
  hass.states["button.left_zero_g"].attributes.friendly_name = "Left Zero gravity";
  expect(render(hass, { device_id: "pair", default_target: "left" })).toContain("Zero gravity");
});

test("legacy labels preserve custom names and fall back when names are missing", () => {
  const hass = fixture();
  delete hass.formatEntityName;
  add(hass, "button.bed_memory_1", "bed", "preset_memory_1", "Reading");
  const state = hass.states["button.bed_memory_1"];
  state.attributes.friendly_name = "My reading position";
  expect(entityLabel(hass, state.entity_id)).toBe("My reading position");
  delete state.attributes.friendly_name;
  expect(entityLabel(hass, state.entity_id)).toBe("Reading");
  delete hass.entities[state.entity_id].name;
  expect(entityLabel(hass, state.entity_id, "Memory 1")).toBe("Memory 1");
  expect(entityLabel(undefined, state.entity_id, "Memory 1")).toBe("Memory 1");
});

test("an entity without a name of its own goes by its device", () => {
  const hass = fixture();
  add(hass, "button.left_flat", "left", "preset_flat");
  expect(entityLabel(hass, "button.left_flat")).toBe("Left");
});

test("an entity without state falls back to its registry name, then the fallback", () => {
  const hass = fixture();
  hass.entities["button.bed_memory_1"] = { entity_id: "button.bed_memory_1", device_id: "bed", name: "Reading" };
  hass.entities["button.bed_memory_2"] = { entity_id: "button.bed_memory_2", device_id: "bed" };
  expect(entityLabel(hass, "button.bed_memory_1", "Memory 1")).toBe("Reading");
  expect(entityLabel(hass, "button.bed_memory_2", "Memory 2")).toBe("Memory 2");
});

test("device names prefer the user's name and ignore blank names", () => {
  const hass = fixture();
  hass.devices.bed = { id: "bed", name: "Bedroom bed", name_by_user: " Guest bed " };
  hass.devices.blank = { id: "blank", name: " ", name_by_user: null };
  expect(deviceName(hass, "bed")).toBe("Guest bed");
  expect(deviceName(hass, "blank")).toBeUndefined();
  expect(deviceName(hass, "missing")).toBeUndefined();
});

test("a renamed entity re-renders once HA installs its new name formatter", () => {
  const hass = fixture();
  add(hass, "button.bed_flat", "bed", "preset_flat", "Flat");
  const card = new AdjustableBedCard() as unknown as {
    hass: HomeAssistant; setConfig(config: object): void; render(): void;
    shouldUpdate(changed: Map<string, unknown>): boolean;
  };
  card.setConfig({ type: "custom:adjustable-bed-card", device_id: "bed" });
  card.hass = hass;
  card.render();
  const renamed = { ...hass, formatEntityName: () => "Lie flat" };
  card.hass = renamed;
  expect(card.shouldUpdate(new Map([["hass", hass]]))).toBe(true);
  card.hass = { ...renamed };
  expect(card.shouldUpdate(new Map([["hass", renamed]]))).toBe(false);
});
