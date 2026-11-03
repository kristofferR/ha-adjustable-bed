import { afterEach, expect, test } from "bun:test";
import type { TemplateResult } from "lit";
import type { HomeAssistant, MotorEntity } from "./types";
import { bedEntitiesForDevice } from "./discovery";
import projections from "./fixtures/reverie041-holds.json";

// Lit supplies its node HTMLElement shim. Only event targets are faked here;
// templates, registered closures, card lifecycle and service dispatch are real.
const registry = new Map<string, CustomElementConstructor>();
const browser = Object.assign(new EventTarget(), {
  customElements: {
    get: (key: string) => registry.get(key),
    define: (key: string, value: CustomElementConstructor) => registry.set(key, value),
    whenDefined: () => new Promise<CustomElementConstructor>(() => {}),
  },
});
const page = Object.assign(new EventTarget(), { visibilityState: "visible" });
class KeyEvent extends Event {
  constructor(public key: string, public repeat = false, type = "keydown") { super(type, { bubbles: true, cancelable: true }); }
}
Object.assign(globalThis, { window: browser, KeyboardEvent: KeyEvent });
const { AdjustableBedCard } = await import("./adjustable-bed-card");
Object.assign(globalThis, { document: page });

interface CardHandlers {
  _motorRow(m: MotorEntity, stop?: string): TemplateResult;
  _motorDirection(m: MotorEntity, dir: "up" | "down", stop?: string,
    scope?: string[], remaining?: string[]): TemplateResult;
  _motors(bed: ReturnType<typeof bedEntitiesForDevice>, scope?: string[], remaining?: string[]): TemplateResult;
}
function handler(template: TemplateResult, name: string): (event: Event) => void {
  const index = template.strings.findIndex((part) => part.endsWith(name + "="));
  if (index < 0) {
    for (const value of [...template.values.flat()].reverse()) {
      if (value && typeof value === "object" && "strings" in value) {
        try { return handler(value as TemplateResult, name); } catch {}
      }
    }
    throw new Error("Missing registered handler: " + name);
  }
  return template.values[index] as (event: Event) => void;
}
function stopHandler(template: TemplateResult): (event: Event) => void {
  if (template.strings.some((part) => part.includes('icon="mdi:stop"'))) {
    return handler(template, "@click");
  }
  for (const value of template.values.flat()) {
    if (value && typeof value === "object" && "strings" in value) {
      try { return stopHandler(value as TemplateResult); } catch {}
    }
  }
  throw new Error("Missing rendered motor STOP");
}
const calls: { domain: string; service: string; data?: Record<string, unknown> }[] = [];
const mounted: InstanceType<typeof AdjustableBedCard>[] = [];
const deferred = () => {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => { resolve = done; });
  return { promise, resolve };
};
const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
function fixture() {
  const hass: HomeAssistant = { entities: {}, states: {}, devices: {}, themes: {},
    locale: { language: "en" }, language: "en", callService: async (domain, service, data) => {
      calls.push({ domain, service, data });
      return new Promise<void>(() => {});
    } };
  for (const [device, key] of [["pair", "back_up"], ["left", "back_up"], ["right", "back_up"]]) {
    const entity_id = "button." + device + "_" + key;
    hass.entities[entity_id] = { entity_id, device_id: device, platform: "adjustable_bed", translation_key: key };
    hass.states[entity_id] = { entity_id, state: "unknown", last_changed: "", last_updated: "",
      attributes: device === "pair" ? projections.compatible_both_button : {
        held_control: "back_up", hold_start_delay_ms: 0, hold_release_delay_ms: 0,
      } };
    const stop = "button." + device + "_stop";
    hass.entities[stop] = { entity_id: stop, device_id: device, platform: "adjustable_bed",
      translation_key: device === "pair" ? "stop_both" : "stop" };
  }
  const card = new AdjustableBedCard();
  // Suppress rendering into a fake DOM, while retaining production template event closures.
  card.scheduleUpdate = () => {};
  card.hass = hass;
  card.setConfig({ type: "custom:adjustable-bed-card", device_id: "pair" });
  card.connectedCallback();
  mounted.push(card);
  return { card, api: card as unknown as CardHandlers, hass };
}
function row(api: CardHandlers, hass: HomeAssistant, device: string, scope?: string[], remaining?: string[]) {
  const bed = bedEntitiesForDevice(hass, device);
  return { bed, template: api._motorDirection(bed.motors[0], "up", bed.stop, scope, remaining) };
}
function down(id: number): Event {
  const event = Object.assign(new Event("pointerdown", { cancelable: true }), {
    button: 0, isPrimary: true, pointerId: id,
  });
  Object.defineProperty(event, "currentTarget", { value: {} });
  return event;
}
function up(id: number): Event {
  return Object.assign(new Event("pointerup"), { button: 0, pointerId: id });
}
afterEach(() => {
  for (const card of mounted.splice(0)) card.disconnectedCallback();
  calls.length = 0;
  page.visibilityState = "visible";
});

test("actual card handlers route discovered standalone and Both holds, then captured focus release", async () => {
  for (const device of ["left", "pair"]) {
    const { api, hass } = fixture();
    const { template } = row(api, hass, device);
    handler(template, "@pointerdown")(down(1));
    expect(calls.at(-1)).toEqual({ domain: "adjustable_bed", service: "hold_control", data: {
      device_id: [device], control: "back_up", duration: 60,
    } });
    delete hass.entities["button." + device + "_stop"];
    page.visibilityState = "visible";
    page.dispatchEvent(new Event("visibilitychange"));
    const count = calls.length;
    page.visibilityState = "hidden";
    page.dispatchEvent(new Event("visibilitychange"));
    expect(calls.slice(count)).toEqual([{ domain: "button", service: "press",
      data: { entity_id: "button." + device + "_stop" } }]);
    browser.dispatchEvent(new Event("blur"));
    expect(calls.length).toBe(count + 1);
  }
  await flush();
});

test("actual card disconnect unregisters focus listeners without another STOP", () => {
  const { card, api, hass } = fixture();
  handler(row(api, hass, "left").template, "@pointerdown")(down(2));
  card.disconnectedCallback();
  const count = calls.length;
  browser.dispatchEvent(new Event("blur"));
  page.visibilityState = "hidden";
  page.dispatchEvent(new Event("visibilitychange"));
  expect(calls.length).toBe(count);
});

test("old side keyboard release cannot end a newer same-key motor on the other side", () => {
  const { api, hass } = fixture();
  const left = row(api, hass, "left");
  const right = row(api, hass, "right");
  handler(left.template, "@keydown")(new KeyEvent("Enter"));
  handler(api._motors(left.bed), "@click")(new Event("click"));
  handler(right.template, "@keydown")(new KeyEvent("Enter"));
  const count = calls.length;
  handler(left.template, "@keyup")(new KeyEvent("Enter"));
  expect(calls.length).toBe(count);
  handler(right.template, "@keyup")(new KeyEvent("Enter"));
  expect(calls.at(-1)?.data).toEqual({ entity_id: "button.right_stop" });
});

test("window keyup from another activation key cannot release a newer keyboard owner", () => {
  const { api, hass } = fixture();
  const left = row(api, hass, "left");
  handler(left.template, "@keydown")(new KeyEvent(" "));
  browser.dispatchEvent(Object.assign(new Event("keyup"), { key: "Enter" }));
  expect(calls).toHaveLength(1);
  browser.dispatchEvent(Object.assign(new Event("keyup"), { key: " " }));
  expect(calls.at(-1)?.data).toEqual({ entity_id: "button.left_stop" });
});

test.each([false, true])("pending Both remainder keeps a reused exact STOP after metadata loss (new hold ended: %s)", async (endNewHold) => {
  const { api, hass } = fixture();
  const pending = deferred();
  hass.callService = async (domain, service, data) => {
    calls.push({ domain, service, data });
    return domain === "adjustable_bed" && data?.device_id === "pair" ? pending.promise : new Promise<void>(() => {});
  };
  const both = row(api, hass, "pair",
    ["button.pair_stop", "button.left_stop", "button.right_stop"], ["button.left_stop", "button.right_stop"]);
  handler(both.template, "@pointerdown")(down(1));
  handler(api._motors(bedEntitiesForDevice(hass, "left")), "@click")(new Event("click"));
  // A live pane can lose its composite physical-scope metadata while retaining
  // the exact STOP entity. The start-time identity still supersedes old cleanup.
  const right = row(api, hass, "right", []);
  handler(right.template, "@pointerdown")(down(2));
  if (endNewHold) handler(right.template, "@pointerup")(up(2));
  const count = calls.length;
  pending.resolve();
  await flush();
  expect(calls.slice(count)).toEqual([]);
  if (!endNewHold) handler(right.template, "@pointerup")(up(2));
  expect(calls.at(-1)?.data).toEqual({ entity_id: "button.right_stop" });
});

test("a delayed pointer end from an old side never releases a new pointer owner", () => {
  const { api, hass } = fixture();
  const left = row(api, hass, "left");
  const right = row(api, hass, "right");
  handler(left.template, "@pointerdown")(down(1));
  handler(api._motors(left.bed), "@click")(new Event("click"));
  handler(right.template, "@pointerdown")(down(2));
  const count = calls.length;
  handler(left.template, "@pointerup")(up(1));
  expect(calls.length).toBe(count);
  handler(right.template, "@pointerup")(up(2));
  expect(calls.at(-1)?.data).toEqual({ entity_id: "button.right_stop" });
});

function useCover(hass: HomeAssistant, device: string): void {
  delete hass.entities["button." + device + "_back_up"];
  const entity_id = "cover." + device + "_back";
  hass.entities[entity_id] = { entity_id, device_id: device, platform: "adjustable_bed", translation_key: "back" };
  hass.states[entity_id] = { entity_id, state: "open", last_changed: "", last_updated: "",
    attributes: device === "left" ? projections.paired_left_cover : projections.standalone_cover };
}

test("real Python standalone cover metadata reaches the registered bounded card path", () => {
  const { api, hass } = fixture();
  useCover(hass, "left");
  const left = row(api, hass, "left");
  handler(left.template, "@pointerdown")(down(5));
  expect(calls.at(-1)).toEqual({ domain: "adjustable_bed", service: "hold_control", data: {
    device_id: ["left"], control: "back_up", duration: 60, side: "left",
  } });
  handler(left.template, "@pointerup")(up(5));
  expect(calls.at(-1)).toEqual({ domain: "cover", service: "stop_cover", data: {
    entity_id: "cover.left_back",
  } });
});

for (const ending of ["pointer-row", "key-row", "pointer-window", "key-window"] as const) {
  test(`registered ${ending} release retains its original cover across a live projection change`, () => {
    const { api, hass } = fixture();
    useCover(hass, "left");
    const before = row(api, hass, "left");
    if (ending.startsWith("pointer")) handler(before.template, "@pointerdown")(down(61));
    else handler(before.template, "@keydown")(new KeyEvent("Enter"));

    delete hass.entities["cover.left_back"];
    const entity_id = "button.left_changed_up";
    hass.entities[entity_id] = { entity_id, device_id: "left", platform: "adjustable_bed", translation_key: "back_up" };
    hass.states[entity_id] = { entity_id, state: "unknown", last_changed: "", last_updated: "", attributes: {} };
    const after = row(api, hass, "left");
    expect(after.bed.motors[0].up).toBe(entity_id);
    expect(after.bed.stop).toBe(before.bed.stop);
    if (ending === "pointer-row") handler(after.template, "@pointerup")(up(61));
    else if (ending === "key-row") handler(after.template, "@keyup")(new KeyEvent("Enter", false, "keyup"));
    else if (ending === "pointer-window") {
      browser.dispatchEvent(Object.assign(new Event("pointerup"), { pointerId: 61, button: 0 }));
    } else browser.dispatchEvent(Object.assign(new Event("keyup"), { key: "Enter" }));
    expect(calls).toHaveLength(2);
    expect(calls[1]).toEqual({ domain: "cover", service: "stop_cover", data: { entity_id: "cover.left_back" } });
  });
}

test("legacy strings-only cover projection retains the finite timed action", () => {
  const { api, hass } = fixture();
  useCover(hass, "left");
  delete hass.states["cover.left_back"].attributes.held_stop_scope;
  const left = row(api, hass, "left");
  handler(left.template, "@pointerdown")(down(55));
  expect(calls.at(-1)).toEqual({ domain: "adjustable_bed", service: "timed_move", data: {
    device_id: "left", motor: "back", direction: "up", duration_ms: 1000,
  } });
  handler(left.template, "@pointerup")(up(55));
});

test("live sequential or mismatched Both metadata keeps the existing finite button fallback", () => {
  const { api, hass } = fixture();
  for (const attributes of [projections.compatible_both_button,
    projections.incompatible_both_button, projections.sequential_both_button]) {
    hass.states["button.pair_back_up"].attributes = attributes;
    const both = row(api, hass, "pair");
    handler(both.template, "@pointerdown")(down(6));
    expect(calls.at(-1)?.service).toBe("held_control" in attributes ? "hold_control" : "press");
    expect(both.bed.motors[0].heldControls !== undefined).toBe("held_control" in attributes);
    if (!("paired_hold_motor" in attributes)) {
      expect(calls.at(-1)?.data).toEqual({ entity_id: "button.pair_back_up" });
    }
    handler(both.template, "@pointerup")(up(6));
  }
});

test("STOP on the independent right cover preserves the left cover hold and captured release", () => {
  const { api, hass } = fixture();
  useCover(hass, "left");
  useCover(hass, "right");
  const left = row(api, hass, "left");
  const right = row(api, hass, "right");
  handler(left.template, "@pointerdown")(down(7));
  const motorStopTemplate = api._motorRow(right.bed.motors[0], right.bed.stop);
  // Find the STOP icon's template so this exercises the rendered row handler.
  stopHandler(motorStopTemplate)(new Event("click"));
  expect(calls.at(-1)?.data).toEqual({ entity_id: "cover.right_back" });
  const count = calls.length;
  handler(left.template, "@pointerup")(up(7));
  expect(calls.slice(count)).toEqual([{ domain: "cover", service: "stop_cover",
    data: { entity_id: "cover.left_back" } }]);
});

test("pending Both remainder cannot stop a newer finite assistive activation", async () => {
  const { api, hass } = fixture();
  const pending = deferred();
  hass.callService = async (domain, service, data) => {
    calls.push({ domain, service, data });
    return domain === "adjustable_bed" && data?.device_id === "pair" ? pending.promise : new Promise<void>(() => {});
  };
  const both = row(api, hass, "pair",
    ["button.pair_stop", "button.left_stop", "button.right_stop"], ["button.left_stop", "button.right_stop"]);
  handler(both.template, "@pointerdown")(down(8));
  handler(api._motors(bedEntitiesForDevice(hass, "left")), "@click")(new Event("click"));
  const right = row(api, hass, "right", []);
  handler(right.template, "@click")(Object.assign(new Event("click"), { detail: 0 }));
  const count = calls.length;
  pending.resolve();
  await flush();
  expect(calls.slice(count)).toEqual([]);
});

function axisCover(hass: HomeAssistant, device: string, axis: string): MotorEntity {
  const entity_id = `cover.${device}_${axis}`;
  hass.entities[entity_id] = { entity_id, device_id: device, platform: "adjustable_bed", translation_key: axis };
  hass.states[entity_id] = { entity_id, state: "open", last_changed: "", last_updated: "", attributes: {
    ...projections.standalone_cover, held_control_up: `${axis}_up`, held_control_down: `${axis}_down`,
  } };
  // Older side-wide controls do not publish the new typed scope field.
  if (axis.startsWith("starcode_m1x12_part_") || axis === "elevate_both") {
    delete hass.states[entity_id].attributes.held_stop_scope;
  }
  return bedEntitiesForDevice(hass, device).motors.find((motor) => motor.key === axis)!;
}

test.each([
  ["back", "legs"], ["back", "lumbar"], ["legs", "back"],
  ["legs", "lumbar"], ["lumbar", "back"], ["lumbar", "legs"],
])("another-axis Stop retains %s release when stopping %s", (heldAxis, stoppedAxis) => {
  const { api, hass } = fixture();
  const held = axisCover(hass, "left", heldAxis);
  const stopped = axisCover(hass, "left", stoppedAxis);
  const movement = api._motorDirection(held, "up", "button.left_stop");
  handler(movement, "@pointerdown")(down(9));
  stopHandler(api._motorRow(stopped, "button.left_stop"))(new Event("click"));
  expect(calls.at(-1)?.data).toEqual({ entity_id: stopped.cover });
  const count = calls.length;
  handler(movement, "@pointerup")(up(9));
  expect(calls.slice(count)).toEqual([{ domain: "cover", service: "stop_cover", data: { entity_id: held.cover } }]);
});

test("same-axis child Stop still invalidates Both and settles its remaining side", async () => {
  const { api, hass } = fixture();
  hass.states["button.pair_back_up"].attributes = {
    paired_hold_motor: "back", paired_hold_side: "both",
  };
  const pending = deferred();
  hass.callService = async (domain, service, data) => {
    calls.push({ domain, service, data });
    return domain === "adjustable_bed" ? pending.promise : new Promise<void>(() => {});
  };
  const both = row(api, hass, "pair", ["button.pair_stop", "button.left_stop", "button.right_stop"],
    ["button.left_stop", "button.right_stop"]);
  handler(both.template, "@pointerdown")(down(10));
  const left = axisCover(hass, "left", "back");
  stopHandler(api._motorRow(left, "button.left_stop"))(new Event("click"));
  pending.resolve();
  await flush();
  expect(calls.slice(1)).toEqual([
    { domain: "cover", service: "stop_cover", data: { entity_id: left.cover } },
    { domain: "button", service: "press", data: { entity_id: "button.right_stop" } },
  ]);
});

test("a declared side-wide cover Stop still invalidates another motor's owner", () => {
  const { api, hass } = fixture();
  const held = axisCover(hass, "left", "starcode_m1x12_part_1");
  const stopped = axisCover(hass, "left", "starcode_m1x12_part_2");
  expect(stopped.coverStopScope).toBe("side");
  const movement = api._motorDirection(held, "up", "button.left_stop");
  handler(movement, "@pointerdown")(down(11));
  stopHandler(api._motorRow(stopped, "button.left_stop"))(new Event("click"));
  const count = calls.length;
  handler(movement, "@pointerup")(up(11));
  expect(calls.length).toBe(count);
  expect(calls.at(-1)?.data).toEqual({ entity_id: stopped.cover });
});

test.each(["left", "right"])("declared %s lumbar assistive actions use finite movement", (device) => {
  for (const direction of ["up", "down"] as const) {
    const { api, hass } = fixture();
    const motor = axisCover(hass, device, "lumbar");
    handler(api._motorDirection(motor, direction, `button.${device}_stop`), "@click")(
      Object.assign(new Event("click"), { detail: 0 }),
    );
    expect(calls.at(-1)).toEqual({ domain: "adjustable_bed", service: "timed_move", data: {
      device_id: device, motor: "lumbar", direction, duration_ms: 1000,
    } });
  }
});

test.each(["Enter", " "])("stale %s row ending cannot escape to the window fallback", (key) => {
  for (const oldSide of ["left", "right"]) {
    const newSide = oldSide === "left" ? "right" : "left";
    const { api, hass } = fixture();
    const old = row(api, hass, oldSide);
    handler(old.template, "@keydown")(new KeyEvent(key));
    stopHandler(api._motorRow(old.bed.motors[0], old.bed.stop))(new Event("click"));
    const current = row(api, hass, newSide);
    handler(current.template, "@keydown")(new KeyEvent(key));
    const count = calls.length;
    const ending = new KeyEvent(key, false, "keyup");
    handler(old.template, "@keyup")(ending);
    if (!ending.cancelBubble) browser.dispatchEvent(ending);
    expect(calls.length).toBe(count);
    handler(current.template, "@keyup")(new KeyEvent(key, false, "keyup"));
    expect(calls.at(-1)?.data).toEqual({ entity_id: `button.${newSide}_stop` });
  }
});


for (const key of ["Enter", " "]) for (const metadata of [false, true]) {
  test(`motor keyboard release after row focus moves: ${JSON.stringify(key)}, held=${metadata}`, () => {
    const { card, api, hass } = fixture();
    delete hass.entities["button.left_back_up"];
    delete hass.states["button.left_back_up"];
    for (const axis of ["back", "legs"]) {
      const id = "cover.left_" + axis;
      hass.entities[id] = { entity_id: id, device_id: "left", platform: "adjustable_bed", translation_key: axis };
      hass.states[id] = { entity_id: id, state: "open", last_changed: "", last_updated: "", attributes: metadata ? {
        held_control_up: axis + "_up", held_control_down: axis + "_down", held_stop_scope: "motor",
        hold_start_delay_ms: 0, hold_release_delay_ms: 0,
      } : {} };
    }
    const bed = bedEntitiesForDevice(hass, "left");
    const back = bed.motors.find((m) => m.key === "back")!;
    const legs = bed.motors.find((m) => m.key === "legs")!;
    const first = api._motorDirection(back, "up", bed.stop);
    const second = api._motorDirection(legs, "up", bed.stop);
    handler(first, "@keydown")(new KeyEvent(key));
    const owner = (card as unknown as { _hold: { heldKey: string | null } })._hold;
    expect(owner.heldKey).toBe("back");
    let onBlur: ((event: Event) => void) | undefined;
    try { onBlur = handler(first, "@blur"); } catch {}
    onBlur?.(new Event("blur"));
    const release = new KeyEvent(key, false, "keyup");
    handler(second, "@keyup")(release);
    if (!release.cancelBubble) browser.dispatchEvent(release);
    expect(owner.heldKey).toBeNull();
  });
}

test("motor blur preserves a pointer hold until its captured pointer releases", () => {
  const { card, api, hass } = fixture();
  const { template } = row(api, hass, "left");
  handler(template, "@pointerdown")(down(73));
  const owner = (card as unknown as { _hold: { heldKey: string | null } })._hold;
  const count = calls.length;
  handler(template, "@blur")(new Event("blur"));
  expect(owner.heldKey).toBe("back");
  expect(calls.length).toBe(count);
  handler(template, "@pointerup")(up(73));
  expect(owner.heldKey).toBeNull();
});

test("a departed row blur cannot release a newer keyboard owner on another side", () => {
  const { card, api, hass } = fixture();
  const left = row(api, hass, "left").template;
  const right = row(api, hass, "right").template;
  handler(left, "@keydown")(new KeyEvent("Enter"));
  handler(left, "@keyup")(new KeyEvent("Enter", false, "keyup"));
  handler(right, "@keydown")(new KeyEvent("Enter"));
  const count = calls.length;
  handler(left, "@blur")(new Event("blur"));
  expect(calls.length).toBe(count);
  expect((card as unknown as { _hold: { heldKey: string | null } })._hold.heldKey).toBe("back");
  handler(right, "@keyup")(new KeyEvent("Enter", false, "keyup"));
  expect((card as unknown as { _hold: { heldKey: string | null } })._hold.heldKey).toBeNull();
});


for (const key of ["Enter", " "]) {
  test(`repeat activation after keyboard focus leaves stays prevented: ${JSON.stringify(key)}`, () => {
    const { api, hass } = fixture();
    const left = row(api, hass, "left").template;
    const right = row(api, hass, "right").template;
    handler(left, "@keydown")(new KeyEvent(key));
    handler(left, "@blur")(new Event("blur"));
    const count = calls.length;
    const repeat = new KeyEvent(key, true);
    handler(right, "@keydown")(repeat);
    expect(repeat.defaultPrevented).toBe(true);
    expect(calls.length).toBe(count);
  });
}
