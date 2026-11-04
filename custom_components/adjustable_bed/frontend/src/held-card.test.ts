// Real Lit templates and event handlers, using Lit's existing Node DOM shim.
import { expect, test } from "bun:test";
import type { TemplateResult } from "lit";
import { bedEntitiesForDevice } from "./discovery";
import type { MotorHold } from "./hold";
import type { BedEntities, HomeAssistant } from "./types";

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

interface CardUnderTest {
  hass: HomeAssistant;
  _hold: MotorHold;
  _utility(bed: BedEntities): TemplateResult;
  disconnectedCallback(): void;
}
function fixture() {
  const calls: Array<{ domain: string; service: string; data: Record<string, unknown> }> = [];
  let finish: (() => void) | undefined;
  const hass = {
    entities: {
      "button.mx_memory1": { entity_id: "button.mx_memory1", platform: "adjustable_bed", device_id: "right-child", translation_key: "remote_action" },
      "button.right_stop": { entity_id: "button.right_stop", platform: "adjustable_bed", device_id: "right-child", translation_key: "stop" },
    },
    states: {
      "button.mx_memory1": { entity_id: "button.mx_memory1", state: "unknown", attributes: { friendly_name: "MX Memory 1", held_control: "mx_memory1", hold_start_delay_ms: 0, hold_release_delay_ms: 0, bed_side: "right" } },
      "button.right_stop": { entity_id: "button.right_stop", state: "unknown", attributes: {} },
    },
    devices: {}, themes: {}, language: "en", locale: { language: "en" },
    callService: async (domain: string, service: string, data: Record<string, unknown>) => {
      calls.push({ domain, service, data });
      if (service === "hold_control") await new Promise<void>((resolve) => { finish = resolve; });
    },
  } as unknown as HomeAssistant;
  const card = new AdjustableBedCard() as unknown as CardUnderTest;
  card.hass = hass;
  return { card, hass, calls, finish: () => finish?.() };
}
function tile(template: TemplateResult): TemplateResult {
  for (const value of template.values) {
    for (const candidate of Array.isArray(value) ? value : [value]) {
      if (candidate && typeof candidate === "object" && "strings" in candidate && "values" in candidate) {
        const result = candidate as TemplateResult;
        if (result.strings.some((s) => s.includes("<button"))) return result;
      }
    }
  }
  throw new Error("No actual card button template");
}
function handler(template: TemplateResult, event: string): (event: Event) => void {
  const index = template.strings.findIndex((s) => s.endsWith(`@${event}=`));
  const value = template.values[index];
  expect(value).toBeFunction();
  return value as (event: Event) => void;
}
class KeyEvent extends Event {
  readonly repeat = false;
  constructor(readonly key: string, type = "keydown") { super(type, { cancelable: true }); }
}
async function withKeyboard(run: () => Promise<void> | void) {
  const previous = Object.getOwnPropertyDescriptor(globalThis, "KeyboardEvent");
  const previousWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  if (typeof window === "undefined" || typeof window.removeEventListener !== "function") {
    Object.defineProperty(globalThis, "window", { configurable: true, value: new EventTarget() });
  }
  Object.defineProperty(globalThis, "KeyboardEvent", { configurable: true, value: KeyEvent });
  try { await run(); }
  finally {
    if (previous) Object.defineProperty(globalThis, "KeyboardEvent", previous);
    else Reflect.deleteProperty(globalThis, "KeyboardEvent");
    if (previousWindow) Object.defineProperty(globalThis, "window", previousWindow);
    else Reflect.deleteProperty(globalThis, "window");
  }
}
test.each(["Enter", " "])("real utility tile retains right STOP for %p keyboard hold", async (key) => {
  await withKeyboard(async () => {
    const f = fixture();
    try {
      const button = tile(f.card._utility(bedEntitiesForDevice(f.hass, "right-child")));
      handler(button, "keydown")(new KeyEvent(key));
      expect(f.calls[0]).toEqual({ domain: "adjustable_bed", service: "hold_control", data: {
        device_id: ["right-child"], control: "mx_memory1", duration: 60, side: "right",
      } });
      handler(button, "keyup")(new KeyEvent(key, "keyup"));
      expect(f.calls[1]).toEqual({ domain: "button", service: "press", data: { entity_id: "button.right_stop" } });
      expect(f.card._hold.heldKey).toBeNull();
      f.finish();
      await Promise.resolve();
    } finally { f.card.disconnectedCallback(); }
  });
});
test("real card page abandonment cancels a pending utility hold on its owning side", async () => {
  await withKeyboard(async () => {
    const f = fixture();
    const button = tile(f.card._utility(bedEntitiesForDevice(f.hass, "right-child")));
    handler(button, "keydown")(new KeyEvent("Enter"));
    f.card.disconnectedCallback();
    expect(f.calls[1].data).toEqual({ entity_id: "button.right_stop" });
    expect(f.card._hold.heldKey).toBeNull();
    f.finish();
    await Promise.resolve();
  });
});
// Registry IDs are opaque. No entity name or held-control string determines
// scope; native children and legacy same-device explicit sides share behavior.
interface OwnershipCard extends CardUnderTest {
  _motors(bed: BedEntities): TemplateResult;
  _motorRow(motor: import("./types").MotorEntity, stop?: string): TemplateResult;
  _motorDirection(motor: import("./types").MotorEntity, dir: "up" | "down", stop?: string): TemplateResult;
  _stopCompact(bed?: BedEntities): void;
}
function ownershipFixture(mode: "native" | "legacy" | "via") {
  const calls: Array<{ domain: string; service: string; data: Record<string, unknown> }> = [];
  const finishes: Array<() => void> = [];
  const stopFinishes: Array<() => void> = [];
  const root = "opaque-root";
  const devices: HomeAssistant["devices"] = { [root]: { id: root } };
  const entities: HomeAssistant["entities"] = {};
  const states: HomeAssistant["states"] = {};
  const owner = (side: string) => mode === "legacy" || side === "both" ? root : `opaque-${side}`;
  if (mode !== "legacy") for (const side of ["left", "right"]) {
    devices[owner(side)] = { id: owner(side), [mode === "via" ? "via_device_id" : "parent_device_id"]: root };
  }
  function add(id: string, side: "left" | "right" | "both", key: string, attributes = {}) {
    entities[id] = { entity_id: id, device_id: owner(side), platform: "adjustable_bed", translation_key: mode === "legacy" ? `${key}_${side}` : key };
    states[id] = { entity_id: id, state: "unknown", attributes: { bed_side: side, ...attributes }, last_changed: "", last_updated: "" };
  }
  for (const side of ["left", "right", "both"] as const) {
    add(`button.${side}_stop`, side, side === "both" ? "stop_both" : "stop");
    for (const motor of ["back", "legs"]) add(`cover.${side}_${motor}`, side, motor, {
      held_control_up: motor === "back" ? "head_up" : "foot_up",
      held_control_down: motor === "back" ? "head_down" : "foot_down",
      held_stop_scope: "side",
      hold_start_delay_ms: 0, hold_release_delay_ms: 0,
    });
    // Source-owned opaque MX and Serta local-target actions use utility tiles.
    add(`button.${side}_mx`, side, "remote_action", { held_control: "mx_memory1", hold_start_delay_ms: 0, hold_release_delay_ms: 0 });
    add(`button.${side}_angle`, side, "remote_action", { held_control: "head_target_up", hold_start_delay_ms: 0, hold_release_delay_ms: 0 });
  }
  const hass: HomeAssistant = { entities, states, devices, themes: {}, language: "en", locale: { language: "en" },
    callService: (domain, service, data = {}) => {
      calls.push({ domain, service, data });
      if (service === "hold_control" || service === "timed_move" || service === "open_cover" || data.entity_id === "button.finite_both") {
        return new Promise<void>((resolve) => finishes.push(resolve));
      }
      return new Promise<void>((resolve) => stopFinishes.push(resolve));
    },
  };
  const card = new AdjustableBedCard() as unknown as OwnershipCard;
  card.hass = hass;
  const bed = (side: "left" | "right" | "both") => bedEntitiesForDevice(hass, owner(side), mode === "legacy" ? side : undefined);
  const stop = (side: "left" | "right" | "both") => {
    const template = card._motors(bed(side));
    const result = (template.values.find((value) => isTemplate(value) && value.strings.some((s) => s.includes('class="stop-all"'))) as TemplateResult);
    handler(result, "click")(new Event("click"));
  };
  return { card, hass, calls, finishes, stopFinishes, bed, stop, add };
}
function isTemplate(value: unknown): value is TemplateResult {
  return !!value && typeof value === "object" && "strings" in value && "values" in value;
}
function matchingTile(template: TemplateResult, id: string): TemplateResult {
  const result = matchingTileOrUndefined(template, id);
  if (result) return result;
  throw new Error(`Missing tile ${id}`);
}
function matchingTileOrUndefined(template: TemplateResult, id: string): TemplateResult | undefined {
  if (template.strings.some((s) => s.includes("<button")) && template.values.includes(id)) return template;
  for (const v of template.values) for (const child of Array.isArray(v) ? v : [v]) {
    if (isTemplate(child)) { const found = matchingTileOrUndefined(child, id); if (found) return found; }
  }
  return undefined;
}
function rowStop(template: TemplateResult): TemplateResult {
  const result = template.values.find((v) => isTemplate(v) &&
    v.strings.some((s) => s.includes('class="cg-btn"')) &&
    !v.strings.some((s) => s.endsWith("@pointerdown=")) &&
    v.strings.some((s) => s.endsWith("@click=")));
  if (!isTemplate(result)) throw new Error("Missing actual row STOP");
  return result;
}
async function settle() { for (let i = 0; i < 8; i++) await Promise.resolve(); }

for (const mode of ["native", "legacy", "via"] as const) {
  test(`${mode}: explicit full STOP invalidates old hold completion without forgetting a newer one`, async () => withKeyboard(async () => {
    const f = ownershipFixture(mode);
    const right = f.bed("right");
    const motor = right.motors.find((m) => m.key === "back")!;
    const button = f.card._motorDirection(motor, "up", right.stop);
    handler(button, "keydown")(new KeyEvent("Enter"));
    f.stop("both");
    handler(button, "keydown")(new KeyEvent("Enter"));
    f.finishes[0](); f.stopFinishes[0](); await settle();
    expect(f.card._hold.heldKey).toBe("back");
    handler(button, "keyup")(new KeyEvent("Enter", "keyup"));
    expect(f.calls.map((c) => c.data.entity_id ?? c.data.control)).toEqual(["head_up", "button.both_stop", "head_up", "cover.right_back"]);
    f.finishes[1](); f.stopFinishes.forEach((done) => done()); await settle();
  }));
}

for (const mode of ["native", "legacy", "via"] as const) {
  for (const action of ["mx", "angle"] as const) test(`${mode}: ${action} utility release keeps source timing and exact owner after opposite STOP`, async () => withKeyboard(async () => {
    const f = ownershipFixture(mode);
    const id = `button.right_${action}`;
    f.hass.states[id].attributes.friendly_name = id;
    const button = matchingTile(f.card._utility(f.bed("right")), id);
    handler(button, "keydown")(new KeyEvent("Enter"));
    f.stop("left");
    handler(button, "keyup")(new KeyEvent("Enter", "keyup"));
    // No extra UI release timer: MX's 300/600/900-ms query schedule is backend-owned.
    expect(f.calls).toEqual([
      { domain: "adjustable_bed", service: "hold_control", data: { device_id: [mode === "legacy" ? "opaque-root" : "opaque-right"], side: "right", control: action === "mx" ? "mx_memory1" : "head_target_up", duration: 60 } },
      { domain: "button", service: "press", data: { entity_id: "button.left_stop" } },
      { domain: "button", service: "press", data: { entity_id: "button.right_stop" } },
    ]);
    f.finishes[0](); f.stopFinishes.forEach((done) => done()); await settle();
  }));
  test(`${mode}: matching row STOP invalidates its hold and later release cannot stop newer work`, async () => withKeyboard(async () => {
    const f = ownershipFixture(mode);
    const right = f.bed("right");
    const back = right.motors.find((m) => m.key === "back")!;
    const legs = right.motors.find((m) => m.key === "legs")!;
    const old = f.card._motorDirection(back, "up", right.stop);
    handler(old, "keydown")(new KeyEvent("Enter"));
    handler(rowStop(f.card._motorRow(back, right.stop)), "click")(new Event("click"));
    const fresh = f.card._motorDirection(legs, "up", right.stop);
    handler(fresh, "keydown")(new KeyEvent("Enter"));
    f.finishes[0](); f.stopFinishes[0](); await settle();
    handler(old, "keyup")(new KeyEvent("Enter", "keyup"));
    expect(f.calls).toHaveLength(3);
    handler(fresh, "keyup")(new KeyEvent("Enter", "keyup"));
    expect(f.calls[3].data.entity_id).toBe("cover.right_legs");
    f.finishes[1](); f.stopFinishes.forEach((done) => done()); await settle();
  }));
  test(`${mode}: partial row STOP blocks finite Both repetition but abandonment cleans remaining side`, async () => withKeyboard(async () => {
    const f = ownershipFixture(mode);
    const both = f.bed("both"), left = f.bed("left");
    const back = both.motors.find((m) => m.key === "back")!;
    back.heldControls = undefined; // Current finite fallback after mode/capability change.
    handler(f.card._motorDirection(back, "up", both.stop), "keydown")(new KeyEvent("Enter"));
    handler(rowStop(f.card._motorRow(left.motors.find((m) => m.key === "back")!, left.stop)), "click")(new Event("click"));
    f.finishes[0](); await settle();
    expect(f.calls).toHaveLength(2);
    f.card.disconnectedCallback();
    expect(f.calls[2]).toEqual({ domain: "cover", service: "stop_cover", data: { entity_id: "cover.both_back" } });
    f.stopFinishes.forEach((done) => done()); await settle();
  }));
}

test("pointer release owns the actual opposite-side callback after STOP", async () => withKeyboard(async () => {
  const f = ownershipFixture("native"), right = f.bed("right");
  const back = right.motors.find((m) => m.key === "back")!;
  const button = f.card._motorDirection(back, "up", right.stop);
  const pointer = (type: string, id = 7) => {
    const event = Object.assign(new Event(type, { cancelable: true }), {
      pointerId: id, button: 0, isPrimary: true,
    });
    Object.defineProperty(event, "currentTarget", { value: { setPointerCapture() {} } });
    return event;
  };
  handler(button, "pointerdown")(pointer("pointerdown"));
  f.stop("left");
  handler(button, "pointerup")(pointer("pointerup", 9));
  expect(f.calls).toHaveLength(2);
  handler(button, "pointerup")(pointer("pointerup"));
  expect(f.calls[2].data.entity_id).toBe("cover.right_back");
  f.finishes[0](); f.stopFinishes.forEach((done) => done()); await settle();
}));

for (const event of ["pagehide", "visibilitychange"] as const) test(`actual connected card ${event} releases owner and detaches listeners`, async () => withKeyboard(async () => {
  const f = ownershipFixture("native"), right = f.bed("right");
  const back = right.motors.find((m) => m.key === "back")!;
  const button = f.card._motorDirection(back, "up", right.stop);
  const doc = Object.assign(new EventTarget(), { visibilityState: "visible" });
  const win = new EventTarget();
  const previousDocument = Object.getOwnPropertyDescriptor(globalThis, "document");
  const previousWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  Object.defineProperty(globalThis, "document", { configurable: true, value: doc });
  Object.defineProperty(globalThis, "window", { configurable: true, value: win });
  // Lit's real Node DOM shim has no renderer. Keep its real lifecycle while
  // preventing this test from scheduling a DOM render after connection.
  Object.defineProperty(f.card, "createRenderRoot", { value: () => ({}) });
  Object.defineProperty(f.card, "shouldUpdate", { value: () => false });
  try {
    (f.card as unknown as { connectedCallback(): void }).connectedCallback();
    handler(button, "keydown")(new KeyEvent("Enter"));
    f.stop("left");
    if (event === "visibilitychange") doc.visibilityState = "hidden";
    (event === "pagehide" ? win : doc).dispatchEvent(new Event(event));
    expect(f.calls[2].data.entity_id).toBe("cover.right_back");
    f.card.disconnectedCallback();
    win.dispatchEvent(new Event("pagehide"));
    expect(f.calls).toHaveLength(3);
    f.finishes[0](); f.stopFinishes.forEach((done) => done()); await settle();
  } finally {
    if (previousDocument) Object.defineProperty(globalThis, "document", previousDocument); else Reflect.deleteProperty(globalThis, "document");
    if (previousWindow) Object.defineProperty(globalThis, "window", previousWindow); else Reflect.deleteProperty(globalThis, "window");
  }
}));

class HoldClock {
  now = 0;
  next = 0;
  tasks = new Map<number, { at: number; run: () => void }>();
  setTimeout = (run: () => void, delay: number) => {
    const id = ++this.next; this.tasks.set(id, { at: this.now + delay, run }); return id;
  };
  clearTimeout = (id: number) => { this.tasks.delete(id); };
  advance(ms: number) {
    this.now += ms;
    for (const [id, task] of [...this.tasks]) if (task.at <= this.now) { this.tasks.delete(id); task.run(); }
  }
}
async function withHoldClock(run: (clock: HoldClock) => Promise<void>) {
  const clock = new HoldClock();
  const set = Object.getOwnPropertyDescriptor(globalThis, "setTimeout")!, clear = Object.getOwnPropertyDescriptor(globalThis, "clearTimeout")!;
  Object.defineProperty(globalThis, "setTimeout", { configurable: true, value: clock.setTimeout });
  Object.defineProperty(globalThis, "clearTimeout", { configurable: true, value: clock.clearTimeout });
  try { await run(clock); }
  finally { Object.defineProperty(globalThis, "setTimeout", set); Object.defineProperty(globalThis, "clearTimeout", clear); }
}
for (const ending of ["release", "abandon", "stop"] as const) test(`compact ${ending} before deferred start retains no cleanup ownership`, async () => withKeyboard(async () => withHoldClock(async (clock) => {
  const f = ownershipFixture("native"), bed = f.bed("right");
  (f.card as unknown as AdjustableBedCard).setConfig({ type: "custom:adjustable-bed-card", device_id: "opaque-root", layout: "compact" });
  const back = bed.motors.find((m) => m.key === "back")!; back.heldControls!.up!.startDelayMs = 250;
  const button = f.card._motorDirection(back, "up", bed.stop);
  handler(button, "keydown")(new KeyEvent("Enter")); clock.advance(249); expect(f.calls).toEqual([]);
  if (ending === "release") handler(button, "keyup")(new KeyEvent("Enter", "keyup"));
  else if (ending === "stop") f.stop("right"); else f.card.disconnectedCallback();
  clock.advance(1000);
  expect(f.calls).toEqual(ending === "stop" ? [{ domain: "button", service: "press", data: { entity_id: "button.right_stop" } }] : []);
  expect(clock.tasks.size).toBe(0); f.stopFinishes.forEach((done) => done()); await settle();
})));
