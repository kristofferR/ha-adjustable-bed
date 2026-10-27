import { expect, test } from "bun:test";
import type { TemplateResult } from "lit";
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
