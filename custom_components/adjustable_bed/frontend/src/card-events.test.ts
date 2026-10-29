import { expect, test } from "bun:test";
import type { TemplateResult } from "lit";
import { bedEntitiesForDevice } from "./discovery";
import type { BedEntities, HomeAssistant, MemorySlot } from "./types";

const previousWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
const customElements = {
  get: () => undefined,
  define: () => undefined,
  whenDefined: () => new Promise<void>(() => undefined),
};
Object.defineProperty(globalThis, "window", {
  configurable: true,
  value: { customElements },
});
const { AdjustableBedCard } = await import("./adjustable-bed-card");
if (previousWindow) {
  Object.defineProperty(globalThis, "window", previousWindow);
} else {
  Reflect.deleteProperty(globalThis, "window");
}

interface PendingTimer {
  id: number;
  delay: number;
  callback: () => void;
  cancelled: boolean;
}

class TestKeyboardEvent {
  readonly repeat = false;
  defaultPrevented = false;

  constructor(readonly key: string) {}

  preventDefault(): void {
    this.defaultPrevented = true;
  }
}

function invoke(handler: unknown, thisArg: unknown, args: unknown[] = []): void {
  if (typeof handler !== "function") throw new Error("Expected an event handler");
  Reflect.apply(handler, thisArg, args);
}

function eventHandler(template: TemplateResult, eventName: string): unknown {
  const index = template.strings.findIndex((source) => source.includes(`@${eventName}=`));
  if (index < 0) throw new Error(`Missing @${eventName} handler`);
  return template.values[index];
}

function isTemplateResult(value: unknown): value is TemplateResult {
  return (
    typeof value === "object" &&
    value !== null &&
    "strings" in value &&
    "values" in value
  );
}

function nestedTemplateWithText(
  template: TemplateResult,
  text: string,
): TemplateResult | undefined {
  if (template.strings.some((part) => part.includes(text))) return template;
  for (const value of template.values) {
    if (isTemplateResult(value)) {
      const found = nestedTemplateWithText(value, text);
      if (found) return found;
    }
    if (Array.isArray(value)) {
      for (const item of value) {
        if (!isTemplateResult(item)) continue;
        const found = nestedTemplateWithText(item, text);
        if (found) return found;
      }
    }
  }
  return undefined;
}

function nestedTemplateMatching(
  template: TemplateResult,
  predicate: (candidate: TemplateResult) => boolean,
): TemplateResult | undefined {
  if (predicate(template)) return template;
  for (const value of template.values) {
    if (isTemplateResult(value)) {
      const found = nestedTemplateMatching(value, predicate);
      if (found) return found;
    }
    if (Array.isArray(value)) {
      for (const item of value) {
        if (!isTemplateResult(item)) continue;
        const found = nestedTemplateMatching(item, predicate);
        if (found) return found;
      }
    }
  }
  return undefined;
}

function memoryTile(
  bed: BedEntities,
): { card: InstanceType<typeof AdjustableBedCard>; tile: TemplateResult } {
  const card = new AdjustableBedCard();
  card.hass = {
    states: {},
    entities: {},
    devices: {},
    locale: { language: "en" },
    language: "en",
    themes: {},
    callService: async () => undefined,
  } satisfies HomeAssistant;
  const createSection: unknown = Reflect.get(AdjustableBedCard.prototype, "_memory");
  if (typeof createSection !== "function") throw new Error("Missing card memory section");
  const section: unknown = Reflect.apply(createSection, card, [bed]);
  if (!isTemplateResult(section)) throw new Error("Expected a rendered memory section");
  const tiles = section.values.find(Array.isArray);
  if (!Array.isArray(tiles)) throw new Error("Missing rendered memory tiles");
  const tile = tiles.find(isTemplateResult);
  if (!tile) throw new Error("Missing rendered memory tile");
  return { card, tile };
}

function fakeTimers(): {
  timers: PendingTimer[];
  restore: () => void;
} {
  const originalSetTimeout = globalThis.setTimeout;
  const originalClearTimeout = globalThis.clearTimeout;
  const timers: PendingTimer[] = [];
  let nextId = 1;
  globalThis.setTimeout = ((handler: TimerHandler, delay?: number) => {
    if (typeof handler !== "function") throw new Error("Expected a timer callback");
    const timer: PendingTimer = {
      id: nextId++,
      delay: delay ?? 0,
      callback: handler as () => void,
      cancelled: false,
    };
    timers.push(timer);
    return timer.id as ReturnType<typeof setTimeout>;
  }) as typeof setTimeout;
  globalThis.clearTimeout = ((handle: ReturnType<typeof setTimeout>) => {
    const timer = timers.find((candidate) => candidate.id === Number(handle));
    if (timer) timer.cancelled = true;
  }) as typeof clearTimeout;
  return {
    timers,
    restore: () => {
      globalThis.setTimeout = originalSetTimeout;
      globalThis.clearTimeout = originalClearTimeout;
    },
  };
}

function bedForMemory(slot: MemorySlot, stop: string): BedEntities {
  return {
    motors: [],
    firmness: [],
    presets: [],
    memory: [slot],
    stop,
    presence: [],
    lights: {},
    massage: { buttons: [], numbers: [] },
    climate: { entities: [], selects: [], numbers: [] },
    utility: [],
  };
}

interface RecordedServiceCall {
  domain: string;
  service: string;
  data?: Record<string, unknown>;
}

function nativePairCardFixture(
  calls: RecordedServiceCall[],
  parentRelation: "parent_device_id" | "via_device_id" = "parent_device_id",
): {
  card: InstanceType<typeof AdjustableBedCard>;
  hass: HomeAssistant;
  leftBed: BedEntities;
  rightBed: BedEntities;
  bothBed: BedEntities;
  finishHold: () => void;
} {
  let finishHold = (): void => undefined;
  const card = new AdjustableBedCard();
  const hass: HomeAssistant = {
    states: {},
    entities: {},
    devices: {
      parent: { id: "parent" },
      left: { id: "left", [parentRelation]: "parent" },
      right: { id: "right", [parentRelation]: "parent" },
    },
    locale: { language: "en" },
    language: "en",
    themes: {},
    callService: (domain, service, data) => {
      calls.push({ domain, service, data });
      if (service === "hold_control") {
        return new Promise<void>((resolve) => { finishHold = resolve; });
      }
      return Promise.resolve();
    },
  };
  card.hass = hass;

  const add = (
    entityId: string,
    deviceId: string,
    translationKey: string,
    attributes: Record<string, unknown> = {},
  ): void => {
    hass.entities[entityId] = {
      entity_id: entityId,
      device_id: deviceId,
      platform: "adjustable_bed",
      translation_key: translationKey,
    };
    hass.states[entityId] = {
      entity_id: entityId,
      state: "unknown",
      last_changed: "",
      last_updated: "",
      attributes,
    };
  };

  add("button.parent_stop_both", "parent", "stop_both");
  add("button.parent_back_up", "parent", "back_up", {
    paired_hold_motor: "back",
    held_control: "back_up",
    hold_start_delay_ms: 100,
    hold_release_delay_ms: 100,
  });
  for (const side of ["left", "right"] as const) {
    add(`button.${side}_stop`, side, "stop", { bed_side: side });
    add(`cover.${side}_back`, side, "back", {
      bed_side: side,
      held_control_up: "back_up",
      held_control_down: "back_down",
      hold_start_delay_ms: 100,
      hold_release_delay_ms: 100,
    });
  }

  return {
    card,
    hass,
    leftBed: bedEntitiesForDevice(hass, "left"),
    rightBed: bedEntitiesForDevice(hass, "right"),
    bothBed: bedEntitiesForDevice(hass, "parent"),
    finishHold: () => finishHold(),
  };
}

function singleAddressOctoCardFixture(calls: RecordedServiceCall[]): {
  card: InstanceType<typeof AdjustableBedCard>;
  bothBed: BedEntities;
  leftBed: BedEntities;
  rightBed: BedEntities;
  finishHold: () => void;
} {
  let finishHold = (): void => undefined;
  const card = new AdjustableBedCard();
  const hass: HomeAssistant = {
    states: {},
    entities: {},
    devices: { bed: { id: "bed" } },
    locale: { language: "en" },
    language: "en",
    themes: {},
    callService: (domain, service, data) => {
      calls.push({ domain, service, data });
      if (service === "hold_control") {
        return new Promise<void>((resolve) => { finishHold = resolve; });
      }
      return Promise.resolve();
    },
  };
  card.hass = hass;
  const add = (
    entityId: string,
    translationKey: string,
    side: "left" | "right" | "both",
    attributes: Record<string, unknown> = {},
  ): void => {
    hass.entities[entityId] = {
      entity_id: entityId,
      device_id: "bed",
      platform: "adjustable_bed",
      translation_key: translationKey,
    };
    hass.states[entityId] = {
      entity_id: entityId,
      state: "unknown",
      last_changed: "",
      last_updated: "",
      attributes: { bed_side: side, ...attributes },
    };
  };

  add("button.both_stop", "stop_both", "both");
  add("button.back_up_both", "back_up_both", "both", {
    held_control: "back_up",
    hold_start_delay_ms: 100,
    hold_release_delay_ms: 100,
  });
  add("button.left_stop", "stop_left", "left");
  add("button.right_stop", "stop_right", "right");

  return {
    card,
    bothBed: bedEntitiesForDevice(hass, "bed", "both"),
    leftBed: bedEntitiesForDevice(hass, "bed", "left"),
    rightBed: bedEntitiesForDevice(hass, "bed", "right"),
    finishHold: () => finishHold(),
  };
}

for (const scenario of [
  { key: "Enter", release: "keyup", stop: "button.left_stop" },
  { key: "Enter", release: "blur", stop: "button.right_stop" },
  { key: " ", release: "keyup", stop: "button.left_stop" },
  { key: " ", release: "blur", stop: "button.right_stop" },
] as const) {
  test(`memory tile ${JSON.stringify(scenario.key)} ${scenario.release} stops its paired side`, async () => {
    const previousKeyboardEvent = Object.getOwnPropertyDescriptor(globalThis, "KeyboardEvent");
    Object.defineProperty(globalThis, "KeyboardEvent", {
      configurable: true,
      value: TestKeyboardEvent,
    });
    const scheduled = fakeTimers();
    const calls: Array<{ domain: string; service: string; data?: Record<string, unknown> }> = [];
    const slot: MemorySlot = {
      slot: 1,
      goto: "button.preset_memory_1",
      save: "button.program_memory_1",
      heldControl: { control: "memory_1", startDelayMs: 100, releaseDelayMs: 200 },
    };
    const { card, tile } = memoryTile(bedForMemory(slot, scenario.stop));
    card.hass = {
      states: {},
      entities: {
        [slot.goto]: {
          entity_id: slot.goto,
          device_id: "right-bed",
          translation_key: "preset_memory_1",
          platform: "adjustable_bed",
        },
      },
      devices: {},
      locale: { language: "en" },
      language: "en",
      themes: {},
      callService: async (domain, service, data) => {
        calls.push({ domain, service, data });
      },
    };

    try {
      const keydown = new TestKeyboardEvent(scenario.key);
      invoke(eventHandler(tile, "keydown"), card, [keydown]);
      expect(keydown.defaultPrevented).toBe(true);

      if (scenario.release === "keyup") {
        invoke(eventHandler(tile, "keyup"), card, [keydown]);
      } else {
        invoke(eventHandler(tile, "blur"), card);
      }

      const pending = scheduled.timers.filter((timer) => !timer.cancelled);
      expect(pending.map((timer) => timer.delay)).toEqual([100, 200]);
      pending.find((timer) => timer.delay === 100)?.callback();
      await Promise.resolve();
      pending.find((timer) => timer.delay === 200)?.callback();

      expect(calls).toEqual([
        { domain: "button", service: "press", data: { entity_id: scenario.stop } },
      ]);
    } finally {
      scheduled.restore();
      if (previousKeyboardEvent) {
        Object.defineProperty(globalThis, "KeyboardEvent", previousKeyboardEvent);
      } else {
        Reflect.deleteProperty(globalThis, "KeyboardEvent");
      }
    }
  });
}

for (const shape of ["native", "single-address", "legacy-via-device"] as const) {
  test(`the rendered left Stop preserves the right release target for ${shape} discovery`, async () => {
    const previousKeyboardEvent = Object.getOwnPropertyDescriptor(globalThis, "KeyboardEvent");
    Object.defineProperty(globalThis, "KeyboardEvent", {
      configurable: true,
      value: TestKeyboardEvent,
    });
    const scheduled = fakeTimers();
    const calls: Array<{ domain: string; service: string; data?: Record<string, unknown> }> = [];
    let finishHold!: () => void;
    const card = new AdjustableBedCard();
    const hass: HomeAssistant = {
      states: {},
      entities: {},
      devices: {},
      locale: { language: "en" },
      language: "en",
      themes: {},
      callService: (domain, service, data) => {
        calls.push({ domain, service, data });
        if (service === "hold_control") {
          return new Promise<void>((resolve) => { finishHold = resolve; });
        }
        return Promise.resolve();
      },
    };
    card.hass = hass;

    const parentId = "paired-bed";
    const leftDevice = shape === "single-address" ? parentId : "left-device";
    const rightDevice = shape === "single-address" ? parentId : "right-device";
    if (shape === "single-address") {
      hass.devices[parentId] = { id: parentId };
    } else if (shape === "legacy-via-device") {
      hass.devices[parentId] = { id: parentId };
      hass.devices[leftDevice] = { id: leftDevice, via_device_id: parentId };
      hass.devices[rightDevice] = { id: rightDevice, via_device_id: parentId };
    } else {
      hass.devices[parentId] = { id: parentId };
      hass.devices[leftDevice] = { id: leftDevice, parent_device_id: parentId };
      hass.devices[rightDevice] = { id: rightDevice, parent_device_id: parentId };
    }

    for (const [side, deviceId] of [["left", leftDevice], ["right", rightDevice]] as const) {
      const key = (base: string): string =>
        shape === "single-address" ? `${base}_${side}` : base;
      const entries = [
        [`button.${side}_stop`, "stop", { bed_side: side }],
        [
          `cover.${side}_back`,
          "back",
          {
            bed_side: side,
            held_control_up: "back_up",
            held_control_down: "back_down",
            hold_start_delay_ms: 100,
            hold_release_delay_ms: 100,
          },
        ],
      ] as const;
      for (const [id, baseKey, attributes] of entries) {
        hass.entities[id] = {
          entity_id: id,
          device_id: deviceId,
          platform: "adjustable_bed",
          translation_key: key(baseKey),
        };
        hass.states[id] = {
          entity_id: id,
          state: "unknown",
          last_changed: "",
          last_updated: "",
          attributes,
        };
      }
    }

    try {
      const leftBed = bedEntitiesForDevice(
        hass,
        leftDevice,
        shape === "single-address" ? "left" : undefined,
      );
      const rightBed = bedEntitiesForDevice(
        hass,
        rightDevice,
        shape === "single-address" ? "right" : undefined,
      );
      const motor = rightBed.motors.find((candidate) => candidate.cover === "cover.right_back");
      if (!motor) throw new Error("Missing discovered right motor");
      expect(motor?.heldControls?.up).toEqual({
        control: "back_up",
        startDelayMs: 100,
        releaseDelayMs: 100,
      });
      expect(leftBed.stop).toBe("button.left_stop");
      expect(rightBed.stop).toBe("button.right_stop");

      const createDirection: unknown = Reflect.get(AdjustableBedCard.prototype, "_motorDirection");
      if (typeof createDirection !== "function") throw new Error("Missing motor direction renderer");
      const rightUp = Reflect.apply(createDirection, card, [motor, "up", rightBed.stop]);
      const keydown = new TestKeyboardEvent("Enter");
      invoke(eventHandler(rightUp, "keydown"), card, [keydown]);
      expect(keydown.defaultPrevented).toBe(true);
      scheduled.timers.find((timer) => timer.delay === 100 && !timer.cancelled)?.callback();
      await Promise.resolve();

      const createMotors: unknown = Reflect.get(AdjustableBedCard.prototype, "_motors");
      if (typeof createMotors !== "function") throw new Error("Missing motor section renderer");
      const leftSection = Reflect.apply(createMotors, card, [leftBed]);
      if (!isTemplateResult(leftSection)) throw new Error("Expected the left motor section");
      const leftStop = nestedTemplateWithText(leftSection, 'class="stop-all"');
      if (!leftStop) throw new Error("Missing the rendered side Stop button");
      invoke(eventHandler(leftStop, "click"), card);
      expect(calls).toEqual([
        {
          domain: "adjustable_bed",
          service: "hold_control",
          data: {
            device_id: [rightDevice],
            control: "back_up",
            duration: 60,
            side: "right",
          },
        },
        { domain: "button", service: "press", data: { entity_id: leftBed.stop } },
      ]);

      invoke(eventHandler(rightUp, "keyup"), card, [new TestKeyboardEvent("Enter")]);
      [...scheduled.timers]
        .reverse()
        .find((timer) => timer.delay === 100 && !timer.cancelled)
        ?.callback();
      expect(calls.at(-1)).toEqual({
        domain: "button", service: "press", data: { entity_id: rightBed.stop },
      });
      finishHold();
      await Promise.resolve();

      calls.length = 0;
      const nextKeydown = new TestKeyboardEvent("Enter");
      invoke(eventHandler(rightUp, "keydown"), card, [nextKeydown]);
      scheduled.timers
        .filter((timer) => timer.delay === 100 && !timer.cancelled)
        .at(-1)
        ?.callback();
      await Promise.resolve();

      const leftMotor = leftBed.motors.find(
        (candidate) => candidate.cover === "cover.left_back",
      );
      if (!leftMotor) throw new Error("Missing discovered left motor");
      const createRow: unknown = Reflect.get(AdjustableBedCard.prototype, "_motorRow");
      if (typeof createRow !== "function") throw new Error("Missing motor row renderer");
      const leftRow = Reflect.apply(createRow, card, [leftMotor, leftBed.stop]);
      if (!isTemplateResult(leftRow)) throw new Error("Expected a rendered left motor row");
      const leftMotorStop = nestedTemplateMatching(
        leftRow,
        (candidate) =>
          candidate.strings.some((part) => part.includes("@click=")) &&
          !candidate.strings.some((part) => part.includes("@pointerdown=")),
      );
      if (!leftMotorStop) throw new Error("Missing the rendered motor-specific Stop button");
      invoke(eventHandler(leftMotorStop, "click"), card);
      expect(calls.slice(-2)).toEqual([
        {
          domain: "adjustable_bed",
          service: "hold_control",
          data: {
            device_id: [rightDevice],
            control: "back_up",
            duration: 60,
            side: "right",
          },
        },
        { domain: "cover", service: "stop_cover", data: { entity_id: "cover.left_back" } },
      ]);

      invoke(eventHandler(rightUp, "keyup"), card, [new TestKeyboardEvent("Enter")]);
      [...scheduled.timers]
        .reverse()
        .find((timer) => timer.delay === 100 && !timer.cancelled)
        ?.callback();
      expect(calls.at(-1)).toEqual({
        domain: "button", service: "press", data: { entity_id: rightBed.stop },
      });
      finishHold();
    } finally {
      scheduled.restore();
      if (previousKeyboardEvent) {
        Object.defineProperty(globalThis, "KeyboardEvent", previousKeyboardEvent);
      } else {
        Reflect.deleteProperty(globalThis, "KeyboardEvent");
      }
    }
  });
}

for (const stopSide of ["left", "right"] as const) {
  const activeSide = stopSide === "left" ? "right" : "left";
  for (const phase of ["active", "pending-release"] as const) {
    test(`a state-less native ${stopSide} Stop preserves the ${activeSide} ${phase}`, async () => {
      const previousKeyboardEvent = Object.getOwnPropertyDescriptor(globalThis, "KeyboardEvent");
      Object.defineProperty(globalThis, "KeyboardEvent", {
        configurable: true,
        value: TestKeyboardEvent,
      });
      const scheduled = fakeTimers();
      const calls: RecordedServiceCall[] = [];
      const fixture = nativePairCardFixture(calls);
      const clickedStop = `button.${stopSide}_stop`;
      const activeBed = activeSide === "left" ? fixture.leftBed : fixture.rightBed;
      const activeMotor = activeBed.motors.find(
        (candidate) => candidate.cover === `cover.${activeSide}_back`,
      );
      if (!activeMotor || !activeBed.stop) throw new Error("Missing discovered side motor/Stop");
      const createDirection: unknown = Reflect.get(AdjustableBedCard.prototype, "_motorDirection");
      if (typeof createDirection !== "function") throw new Error("Missing motor direction renderer");
      const activeUp = Reflect.apply(createDirection, fixture.card, [
        activeMotor,
        "up",
        activeBed.stop,
      ]);

      try {
        // The state can be absent while HA keeps the registered Stop entity and
        // its native child device link.
        delete fixture.hass.states[clickedStop];
        const keydown = new TestKeyboardEvent("Enter");
        invoke(eventHandler(activeUp, "keydown"), fixture.card, [keydown]);
        scheduled.timers.find((timer) => timer.delay === 100 && !timer.cancelled)?.callback();
        await Promise.resolve();
        await Promise.resolve();
        expect(calls[0]).toEqual({
          domain: "adjustable_bed",
          service: "hold_control",
          data: {
            device_id: [`${activeSide}`],
            control: "back_up",
            duration: 60,
            side: activeSide,
          },
        });

        if (phase === "pending-release") {
          invoke(eventHandler(activeUp, "keyup"), fixture.card, [keydown]);
        }

        const clickedBed = stopSide === "left" ? fixture.leftBed : fixture.rightBed;
        expect(clickedBed.stop).toBe(clickedStop);
        const createMotors: unknown = Reflect.get(AdjustableBedCard.prototype, "_motors");
        if (typeof createMotors !== "function") throw new Error("Missing motor section renderer");
        const section = Reflect.apply(createMotors, fixture.card, [clickedBed]);
        if (!isTemplateResult(section)) throw new Error("Expected the clicked side motor section");
        const stopButton = nestedTemplateWithText(section, 'class="stop-all"');
        if (!stopButton) throw new Error("Missing the registry-backed side Stop button");
        invoke(eventHandler(stopButton, "click"), fixture.card);

        if (phase === "active") {
          invoke(eventHandler(activeUp, "keyup"), fixture.card, [keydown]);
        }
        [...scheduled.timers]
          .reverse()
          .find((timer) => timer.delay === 100 && !timer.cancelled)
          ?.callback();
        expect(calls.filter((call) => call.domain === "button")).toEqual([
          { domain: "button", service: "press", data: { entity_id: clickedStop } },
          {
            domain: "button",
            service: "press",
            data: { entity_id: `button.${activeSide}_stop` },
          },
        ]);
        fixture.finishHold();
      } finally {
        scheduled.restore();
        if (previousKeyboardEvent) {
          Object.defineProperty(globalThis, "KeyboardEvent", previousKeyboardEvent);
        } else {
          Reflect.deleteProperty(globalThis, "KeyboardEvent");
        }
      }
    });
  }
}

for (const parentRelation of ["parent_device_id", "via_device_id"] as const) {
  for (const phase of ["active", "pending-release", "before-start"] as const) {
    for (const stopSide of ["left", "right"] as const) {
      test(`a child ${stopSide} Stop settles the discovered OCTO Both hold during ${phase} (${parentRelation})`, async () => {
      const previousKeyboardEvent = Object.getOwnPropertyDescriptor(globalThis, "KeyboardEvent");
      Object.defineProperty(globalThis, "KeyboardEvent", {
        configurable: true,
        value: TestKeyboardEvent,
      });
      const scheduled = fakeTimers();
      const calls: RecordedServiceCall[] = [];
      const fixture = nativePairCardFixture(calls, parentRelation);
      const activeMotor = fixture.bothBed.motors.find(
        (candidate) => candidate.up === "button.parent_back_up",
      );
      if (!activeMotor || !fixture.bothBed.stop)
        throw new Error("Missing discovered paired OCTO Both action/Stop");
      expect(activeMotor.timedMove).toEqual({ deviceId: "parent", motor: "back" });
      expect(activeMotor.heldControls?.up).toEqual({
        control: "back_up",
        startDelayMs: 100,
        releaseDelayMs: 100,
      });

      const createDirection: unknown = Reflect.get(AdjustableBedCard.prototype, "_motorDirection");
      if (typeof createDirection !== "function") throw new Error("Missing motor direction renderer");
      const bothUp = Reflect.apply(createDirection, fixture.card, [
        activeMotor,
        "up",
        fixture.bothBed.stop,
      ]);

      try {
        const keydown = new TestKeyboardEvent("Enter");
        invoke(eventHandler(bothUp, "keydown"), fixture.card, [keydown]);
        if (phase !== "before-start") {
          scheduled.timers.find((timer) => timer.delay === 100 && !timer.cancelled)?.callback();
          await Promise.resolve();
          await Promise.resolve();
          expect(calls[0]).toEqual({
            domain: "adjustable_bed",
            service: "hold_control",
            data: { device_id: ["parent"], control: "back_up", duration: 60 },
          });
          if (phase === "pending-release") {
            invoke(eventHandler(bothUp, "keyup"), fixture.card, [keydown]);
          }
        }
        const pendingRelease = phase === "pending-release"
          ? [...scheduled.timers].reverse().find((timer) => timer.delay === 100)?.callback
          : undefined;

        const clickedBed = stopSide === "left" ? fixture.leftBed : fixture.rightBed;
        const createMotors: unknown = Reflect.get(AdjustableBedCard.prototype, "_motors");
        if (typeof createMotors !== "function") throw new Error("Missing motor section renderer");
        const section = Reflect.apply(createMotors, fixture.card, [clickedBed]);
        if (!isTemplateResult(section)) throw new Error("Expected the clicked side motor section");
        const stopButton = nestedTemplateWithText(section, 'class="stop-all"');
        if (!stopButton) throw new Error("Missing the side Stop button");
        invoke(eventHandler(stopButton, "click"), fixture.card);

        if (phase !== "pending-release") invoke(eventHandler(bothUp, "keyup"), fixture.card, [keydown]);
        pendingRelease?.();
        const expectedStops = phase === "before-start"
          ? [`button.${stopSide}_stop`]
          : [`button.${stopSide}_stop`, `button.${stopSide === "left" ? "right" : "left"}_stop`];
        expect(calls.filter((call) => call.domain === "button")).toEqual(
          expectedStops.map((entity_id) => ({
            domain: "button",
            service: "press",
            data: { entity_id },
          })),
        );
        expect(calls.some((call) => call.data?.entity_id === fixture.bothBed.stop)).toBe(false);
        if (phase === "before-start") {
          expect(calls.some((call) => call.service === "hold_control")).toBe(false);
        }
        fixture.finishHold();
      } finally {
        scheduled.restore();
        if (previousKeyboardEvent) {
          Object.defineProperty(globalThis, "KeyboardEvent", previousKeyboardEvent);
        } else {
          Reflect.deleteProperty(globalThis, "KeyboardEvent");
        }
      }
      });
    }
  }
}

for (const parentRelation of ["parent_device_id", "via_device_id"] as const) {
  for (const phase of ["active", "pending-release"] as const) {
    for (const stopSide of ["left", "right"] as const) {
      test(`a state-less child ${stopSide} Stop settles a started OCTO Both hold during ${phase} (${parentRelation})`, async () => {
        const previousKeyboardEvent = Object.getOwnPropertyDescriptor(globalThis, "KeyboardEvent");
        Object.defineProperty(globalThis, "KeyboardEvent", {
          configurable: true,
          value: TestKeyboardEvent,
        });
        const scheduled = fakeTimers();
        const calls: RecordedServiceCall[] = [];
        const fixture = nativePairCardFixture(calls, parentRelation);
        const clickedStop = `button.${stopSide}_stop`;
        delete fixture.hass.states[clickedStop];
        const activeMotor = fixture.bothBed.motors.find(
          (candidate) => candidate.up === "button.parent_back_up",
        );
        if (!activeMotor || !fixture.bothBed.stop) {
          throw new Error("Missing discovered OCTO Both action/Stop");
        }
        const createDirection: unknown = Reflect.get(
          AdjustableBedCard.prototype,
          "_motorDirection",
        );
        if (typeof createDirection !== "function") {
          throw new Error("Missing motor direction renderer");
        }
        const bothUp = Reflect.apply(createDirection, fixture.card, [
          activeMotor,
          "up",
          fixture.bothBed.stop,
        ]);

        try {
          const keydown = new TestKeyboardEvent("Enter");
          invoke(eventHandler(bothUp, "keydown"), fixture.card, [keydown]);
          scheduled.timers.find((timer) => timer.delay === 100 && !timer.cancelled)?.callback();
          await Promise.resolve();
          await Promise.resolve();
          expect(calls[0]).toEqual({
            domain: "adjustable_bed",
            service: "hold_control",
            data: { device_id: ["parent"], control: "back_up", duration: 60 },
          });

          if (phase === "pending-release") {
            invoke(eventHandler(bothUp, "keyup"), fixture.card, [keydown]);
          }
          const pendingRelease = phase === "pending-release"
            ? [...scheduled.timers].reverse().find((timer) => timer.delay === 100)?.callback
            : undefined;
          const clickedBed = stopSide === "left" ? fixture.leftBed : fixture.rightBed;
          expect(clickedBed.stop).toBe(clickedStop);
          const createMotors: unknown = Reflect.get(AdjustableBedCard.prototype, "_motors");
          if (typeof createMotors !== "function") throw new Error("Missing motor section renderer");
          const section = Reflect.apply(createMotors, fixture.card, [clickedBed]);
          if (!isTemplateResult(section)) throw new Error("Expected the clicked side motor section");
          const stopButton = nestedTemplateWithText(section, 'class="stop-all"');
          if (!stopButton) throw new Error("Missing registry-backed child Stop button");
          invoke(eventHandler(stopButton, "click"), fixture.card);

          if (phase === "active") invoke(eventHandler(bothUp, "keyup"), fixture.card, [keydown]);
          pendingRelease?.();
          const otherSide = stopSide === "left" ? "right" : "left";
          expect(calls.filter((call) => call.domain === "button")).toEqual([
            { domain: "button", service: "press", data: { entity_id: clickedStop } },
            {
              domain: "button",
              service: "press",
              data: { entity_id: `button.${otherSide}_stop` },
            },
          ]);
          expect(calls.some((call) => call.data?.entity_id === fixture.bothBed.stop)).toBe(false);
          fixture.finishHold();
        } finally {
          scheduled.restore();
          if (previousKeyboardEvent) {
            Object.defineProperty(globalThis, "KeyboardEvent", previousKeyboardEvent);
          } else {
            Reflect.deleteProperty(globalThis, "KeyboardEvent");
          }
        }
      });
    }
  }
}

for (const phase of ["active", "pending-release"] as const) {
  for (const stopSide of ["left", "right"] as const) {
    test(`a single-address ${stopSide} Stop settles the discovered OCTO Both hold during ${phase}`, async () => {
      const previousKeyboardEvent = Object.getOwnPropertyDescriptor(globalThis, "KeyboardEvent");
      Object.defineProperty(globalThis, "KeyboardEvent", {
        configurable: true,
        value: TestKeyboardEvent,
      });
      const scheduled = fakeTimers();
      const calls: RecordedServiceCall[] = [];
      const fixture = singleAddressOctoCardFixture(calls);
      const activeMotor = fixture.bothBed.motors.find(
        (candidate) => candidate.up === "button.back_up_both",
      );
      if (!activeMotor || !fixture.bothBed.stop)
        throw new Error("Missing discovered single-address OCTO Both action/Stop");
      expect(activeMotor.timedMove).toBeUndefined();
      expect(activeMotor.heldControls?.up).toEqual({
        control: "back_up",
        startDelayMs: 100,
        releaseDelayMs: 100,
      });
      const createDirection: unknown = Reflect.get(AdjustableBedCard.prototype, "_motorDirection");
      if (typeof createDirection !== "function") throw new Error("Missing motor direction renderer");
      const bothUp = Reflect.apply(createDirection, fixture.card, [
        activeMotor,
        "up",
        fixture.bothBed.stop,
      ]);

      try {
        const keydown = new TestKeyboardEvent("Enter");
        invoke(eventHandler(bothUp, "keydown"), fixture.card, [keydown]);
        scheduled.timers.find((timer) => timer.delay === 100 && !timer.cancelled)?.callback();
        await Promise.resolve();
        await Promise.resolve();
        expect(calls[0]).toEqual({
          domain: "adjustable_bed",
          service: "hold_control",
          data: { device_id: ["bed"], control: "back_up", duration: 60, side: "both" },
        });
        if (phase === "pending-release") {
          invoke(eventHandler(bothUp, "keyup"), fixture.card, [keydown]);
        }
        const pendingRelease = phase === "pending-release"
          ? [...scheduled.timers].reverse().find((timer) => timer.delay === 100)?.callback
          : undefined;

        const clickedBed = stopSide === "left" ? fixture.leftBed : fixture.rightBed;
        const createMotors: unknown = Reflect.get(AdjustableBedCard.prototype, "_motors");
        if (typeof createMotors !== "function") throw new Error("Missing motor section renderer");
        const section = Reflect.apply(createMotors, fixture.card, [clickedBed]);
        if (!isTemplateResult(section)) throw new Error("Expected the selected side motor section");
        const stopButton = nestedTemplateWithText(section, 'class="stop-all"');
        if (!stopButton) throw new Error("Missing the selected side Stop button");
        invoke(eventHandler(stopButton, "click"), fixture.card);
        if (phase === "active") invoke(eventHandler(bothUp, "keyup"), fixture.card, [keydown]);
        pendingRelease?.();

        expect(calls.filter((call) => call.domain === "button")).toEqual([
          { domain: "button", service: "press", data: { entity_id: `button.${stopSide}_stop` } },
          {
            domain: "button",
            service: "press",
            data: { entity_id: `button.${stopSide === "left" ? "right" : "left"}_stop` },
          },
        ]);
        expect(calls.some((call) => call.data?.entity_id === fixture.bothBed.stop)).toBe(false);
        fixture.finishHold();
      } finally {
        scheduled.restore();
        if (previousKeyboardEvent) {
          Object.defineProperty(globalThis, "KeyboardEvent", previousKeyboardEvent);
        } else {
          Reflect.deleteProperty(globalThis, "KeyboardEvent");
        }
      }
    });
  }
}

test("a side STOP prevents the registered finite Both action from repeating", async () => {
  const previousKeyboardEvent = Object.getOwnPropertyDescriptor(globalThis, "KeyboardEvent");
  Object.defineProperty(globalThis, "KeyboardEvent", {
    configurable: true,
    value: TestKeyboardEvent,
  });
  const scheduled = fakeTimers();
  const calls: Array<{ domain: string; service: string; data?: Record<string, unknown> }> = [];
  let finishMove!: () => void;
  const card = new AdjustableBedCard();
  const hass: HomeAssistant = {
    states: {},
    entities: {},
    devices: {
      parent: { id: "parent" },
      left: { id: "left", parent_device_id: "parent" },
      right: { id: "right", parent_device_id: "parent" },
    },
    locale: { language: "en" },
    language: "en",
    themes: {},
    callService: (domain, service, data) => {
      calls.push({ domain, service, data });
      if (service === "timed_move") {
        return new Promise<void>((resolve) => { finishMove = resolve; });
      }
      return Promise.resolve();
    },
  };
  card.hass = hass;

  const add = (
    entityId: string,
    deviceId: string,
    translationKey: string,
    attributes: Record<string, unknown> = {},
  ): void => {
    hass.entities[entityId] = {
      entity_id: entityId,
      device_id: deviceId,
      platform: "adjustable_bed",
      translation_key: translationKey,
    };
    hass.states[entityId] = {
      entity_id: entityId,
      state: "unknown",
      last_changed: "",
      last_updated: "",
      attributes,
    };
  };
  add("button.parent_stop", "parent", "stop_both");
  add("button.left_stop", "left", "stop", { bed_side: "left" });
  add("button.right_stop", "right", "stop", { bed_side: "right" });
  add("button.parent_back_up", "parent", "back_up", { paired_hold_motor: "back" });

  try {
    const bothBed = bedEntitiesForDevice(hass, "parent");
    const leftBed = bedEntitiesForDevice(hass, "left");
    const motor = bothBed.motors.find((candidate) => candidate.up === "button.parent_back_up");
    if (!motor) throw new Error("Missing discovered paired Both motor");
    expect(motor.timedMove).toEqual({ deviceId: "parent", motor: "back" });

    const createDirection: unknown = Reflect.get(AdjustableBedCard.prototype, "_motorDirection");
    if (typeof createDirection !== "function") throw new Error("Missing motor direction renderer");
    const bothUp = Reflect.apply(createDirection, card, [motor, "up", bothBed.stop]);
    invoke(eventHandler(bothUp, "keydown"), card, [new TestKeyboardEvent("Enter")]);
    expect(calls).toEqual([
      {
        domain: "adjustable_bed",
        service: "timed_move",
        data: {
          device_id: "parent",
          side: "both",
          motor: "back",
          direction: "up",
          duration_ms: 1000,
        },
      },
    ]);

    const createMotors: unknown = Reflect.get(AdjustableBedCard.prototype, "_motors");
    if (typeof createMotors !== "function") throw new Error("Missing motor section renderer");
    const leftSection = Reflect.apply(createMotors, card, [leftBed]);
    if (!isTemplateResult(leftSection)) throw new Error("Expected the left motor section");
    const leftStop = nestedTemplateWithText(leftSection, 'class="stop-all"');
    if (!leftStop) throw new Error("Missing the rendered side Stop button");
    invoke(eventHandler(leftStop, "click"), card);
    invoke(eventHandler(bothUp, "keyup"), card, [new TestKeyboardEvent("Enter")]);
    expect(calls.at(-1)).toEqual({
      domain: "button",
      service: "press",
      data: { entity_id: leftBed.stop },
    });

    finishMove();
    await Promise.resolve();
    expect(calls.filter((call) => call.service === "timed_move")).toHaveLength(1);
  } finally {
    scheduled.restore();
    if (previousKeyboardEvent) {
      Object.defineProperty(globalThis, "KeyboardEvent", previousKeyboardEvent);
    } else {
      Reflect.deleteProperty(globalThis, "KeyboardEvent");
    }
  }
});

for (const relation of ["parent_device_id", "via_device_id"] as const) {
  for (const side of ["left", "right"] as const) {
    for (const drift of ["none", "missing-parent", "missing-graph"] as const) {
      for (const phase of ["active", "pending-release"] as const) {
        test(`retained ${side} STOP after ${drift} settles ${phase} work (${relation})`, async () => {
          const previousKeyboardEvent = Object.getOwnPropertyDescriptor(globalThis, "KeyboardEvent");
          Object.defineProperty(globalThis, "KeyboardEvent", {
            configurable: true,
            value: TestKeyboardEvent,
          });
          const scheduled = fakeTimers();
          const calls: RecordedServiceCall[] = [];
          const fixture = nativePairCardFixture(calls, relation);
          const bed = side === "left" ? fixture.leftBed : fixture.rightBed;
          const motor = bed.motors.find((candidate) => candidate.cover === `cover.${side}_back`);
          if (!motor || !bed.stop) throw new Error(`Missing discovered ${side} motor or Stop`);
          const createDirection: unknown = Reflect.get(AdjustableBedCard.prototype, "_motorDirection");
          const createMotors: unknown = Reflect.get(AdjustableBedCard.prototype, "_motors");
          if (typeof createDirection !== "function" || typeof createMotors !== "function") {
            throw new Error("Missing production card motor handlers");
          }
          const up = Reflect.apply(createDirection, fixture.card, [motor, "up", bed.stop]);
          const section: unknown = Reflect.apply(createMotors, fixture.card, [bed]);
          if (!isTemplateResult(section)) throw new Error(`Missing ${side} motor section`);
          const stopButton = nestedTemplateWithText(section, 'class="stop-all"');
          if (!stopButton) throw new Error(`Missing rendered ${side} Stop`);

          try {
            const keydown = new TestKeyboardEvent("Enter");
            invoke(eventHandler(up, "keydown"), fixture.card, [keydown]);
            const firstStart = [...scheduled.timers].reverse().find(
              (timer) => timer.delay === 100 && !timer.cancelled,
            );
            if (!firstStart) throw new Error("Missing first held-operation start guard");
            firstStart.callback();
            await Promise.resolve();
            await Promise.resolve();
            expect(calls.filter((call) => call.service === "hold_control")).toHaveLength(1);

            let oldRelease: PendingTimer | undefined;
            if (phase === "pending-release") {
              invoke(eventHandler(up, "keyup"), fixture.card, [keydown]);
              oldRelease = [...scheduled.timers].reverse().find(
                (timer) => timer.delay === 100 && !timer.cancelled,
              );
              if (!oldRelease) throw new Error("Missing delayed release timer");
            }

            if (drift === "missing-parent") delete fixture.hass.devices.parent;
            if (drift === "missing-graph") fixture.hass.devices = {};
            invoke(eventHandler(stopButton, "click"), fixture.card);
            expect(calls.some(
              (call) => call.domain === "button" && call.data?.entity_id === bed.stop,
            )).toBe(true);

            if (phase === "active") {
              fixture.finishHold();
              await Promise.resolve();
              await Promise.resolve();
              expect(calls.filter((call) => call.service === "hold_control")).toHaveLength(1);
            } else {
              fixture.finishHold();
              await Promise.resolve();
              await Promise.resolve();

              const nextKeydown = new TestKeyboardEvent("Enter");
              invoke(eventHandler(up, "keydown"), fixture.card, [nextKeydown]);
              const nextStart = [...scheduled.timers].reverse().find(
                (timer) => timer.delay === 100 && !timer.cancelled,
              );
              if (!nextStart) throw new Error("Missing newer held-operation start guard");
              nextStart.callback();
              await Promise.resolve();
              await Promise.resolve();
              expect(calls.filter((call) => call.service === "hold_control")).toHaveLength(2);

              const stopsBeforeStaleCallback = calls.filter((call) => call.domain === "button").length;
              oldRelease.callback();
              expect(calls.filter((call) => call.domain === "button")).toHaveLength(
                stopsBeforeStaleCallback,
              );

              invoke(eventHandler(up, "keyup"), fixture.card, [nextKeydown]);
              const newRelease = [...scheduled.timers].reverse().find(
                (timer) => timer.delay === 100 && !timer.cancelled,
              );
              if (!newRelease) throw new Error("Missing newer release timer");
              newRelease.callback();
              fixture.finishHold();
              await Promise.resolve();
              await Promise.resolve();
            }
          } finally {
            scheduled.restore();
            if (previousKeyboardEvent) {
              Object.defineProperty(globalThis, "KeyboardEvent", previousKeyboardEvent);
            } else {
              Reflect.deleteProperty(globalThis, "KeyboardEvent");
            }
          }
        });
      }
    }
  }
}

for (const relation of ["parent_device_id", "via_device_id"] as const) {
  for (const side of ["left", "right"] as const) {
    test(`same-side ${side} re-entry flushes its retained release after graph loss (${relation})`, async () => {
      const previousKeyboardEvent = Object.getOwnPropertyDescriptor(globalThis, "KeyboardEvent");
      Object.defineProperty(globalThis, "KeyboardEvent", {
        configurable: true,
        value: TestKeyboardEvent,
      });
      const scheduled = fakeTimers();
      const calls: RecordedServiceCall[] = [];
      const fixture = nativePairCardFixture(calls, relation);
      const bed = side === "left" ? fixture.leftBed : fixture.rightBed;
      const motor = bed.motors.find((candidate) => candidate.cover === `cover.${side}_back`);
      if (!motor || !bed.stop) throw new Error(`Missing discovered ${side} motor or Stop`);
      const createDirection: unknown = Reflect.get(AdjustableBedCard.prototype, "_motorDirection");
      if (typeof createDirection !== "function") throw new Error("Missing motor direction renderer");
      const up = Reflect.apply(createDirection, fixture.card, [motor, "up", bed.stop]);

      try {
        const firstKeydown = new TestKeyboardEvent("Enter");
        invoke(eventHandler(up, "keydown"), fixture.card, [firstKeydown]);
        const firstStart = scheduled.timers.find((timer) => timer.delay === 100 && !timer.cancelled);
        if (!firstStart) throw new Error("Missing first held-operation start guard");
        firstStart.callback();
        await Promise.resolve();
        await Promise.resolve();
        expect(calls.filter((call) => call.service === "hold_control")).toHaveLength(1);

        invoke(eventHandler(up, "keyup"), fixture.card, [firstKeydown]);
        const oldRelease = [...scheduled.timers].reverse().find(
          (timer) => timer.delay === 100 && !timer.cancelled,
        );
        if (!oldRelease) throw new Error("Missing original release timer");
        fixture.finishHold();
        await Promise.resolve();
        await Promise.resolve();
        fixture.hass.devices = {};

        const nextKeydown = new TestKeyboardEvent("Enter");
        invoke(eventHandler(up, "keydown"), fixture.card, [nextKeydown]);
        expect(calls.filter((call) => call.domain === "button")).toEqual([
          { domain: "button", service: "press", data: { entity_id: bed.stop } },
        ]);
        const nextStart = [...scheduled.timers].reverse().find(
          (timer) => timer.delay === 100 && !timer.cancelled,
        );
        if (!nextStart) throw new Error("Missing newer held-operation start guard");
        nextStart.callback();
        await Promise.resolve();
        await Promise.resolve();
        expect(calls.filter((call) => call.service === "hold_control")).toHaveLength(2);

        oldRelease.callback();
        expect(calls.filter((call) => call.domain === "button")).toHaveLength(1);
        invoke(eventHandler(up, "keyup"), fixture.card, [nextKeydown]);
        const nextRelease = [...scheduled.timers].reverse().find(
          (timer) => timer.delay === 100 && !timer.cancelled,
        );
        if (!nextRelease) throw new Error("Missing newer release timer");
        nextRelease.callback();
        fixture.finishHold();
        await Promise.resolve();
        await Promise.resolve();
      } finally {
        scheduled.restore();
        if (previousKeyboardEvent) {
          Object.defineProperty(globalThis, "KeyboardEvent", previousKeyboardEvent);
        } else {
          Reflect.deleteProperty(globalThis, "KeyboardEvent");
        }
      }
    });
  }
}

test("metadata loss does not let a different side Stop cancel the retained hold", async () => {
  const previousKeyboardEvent = Object.getOwnPropertyDescriptor(globalThis, "KeyboardEvent");
  Object.defineProperty(globalThis, "KeyboardEvent", {
    configurable: true,
    value: TestKeyboardEvent,
  });
  const scheduled = fakeTimers();
  const calls: RecordedServiceCall[] = [];
  const fixture = nativePairCardFixture(calls);
  const rightBed = fixture.rightBed;
  const rightMotor = rightBed.motors.find((candidate) => candidate.cover === "cover.right_back");
  if (!rightMotor || !rightBed.stop) throw new Error("Missing discovered right motor or Stop");
  const createDirection: unknown = Reflect.get(AdjustableBedCard.prototype, "_motorDirection");
  const createMotors: unknown = Reflect.get(AdjustableBedCard.prototype, "_motors");
  if (typeof createDirection !== "function" || typeof createMotors !== "function") {
    throw new Error("Missing production card motor handlers");
  }
  const rightUp = Reflect.apply(createDirection, fixture.card, [rightMotor, "up", rightBed.stop]);
  const leftSection: unknown = Reflect.apply(createMotors, fixture.card, [fixture.leftBed]);
  if (!isTemplateResult(leftSection)) throw new Error("Missing left motor section");
  const leftStop = nestedTemplateWithText(leftSection, 'class="stop-all"');
  const rightSection: unknown = Reflect.apply(createMotors, fixture.card, [rightBed]);
  if (!isTemplateResult(rightSection)) throw new Error("Missing right motor section");
  const rightStop = nestedTemplateWithText(rightSection, 'class="stop-all"');
  if (!leftStop || !rightStop) throw new Error("Missing rendered side Stop");

  try {
    const keydown = new TestKeyboardEvent("Enter");
    invoke(eventHandler(rightUp, "keydown"), fixture.card, [keydown]);
    const start = scheduled.timers.find((timer) => timer.delay === 100 && !timer.cancelled);
    if (!start) throw new Error("Missing held-operation start guard");
    start.callback();
    await Promise.resolve();
    await Promise.resolve();
    expect(calls.filter((call) => call.service === "hold_control")).toHaveLength(1);

    fixture.hass.devices = {};
    invoke(eventHandler(leftStop, "click"), fixture.card);
    fixture.finishHold();
    await Promise.resolve();
    await Promise.resolve();
    expect(calls.filter((call) => call.service === "hold_control")).toHaveLength(2);

    invoke(eventHandler(rightStop, "click"), fixture.card);
    fixture.finishHold();
    await Promise.resolve();
    await Promise.resolve();
    expect(calls.filter((call) => call.service === "hold_control")).toHaveLength(2);
  } finally {
    scheduled.restore();
    if (previousKeyboardEvent) {
      Object.defineProperty(globalThis, "KeyboardEvent", previousKeyboardEvent);
    } else {
      Reflect.deleteProperty(globalThis, "KeyboardEvent");
    }
  }
});
