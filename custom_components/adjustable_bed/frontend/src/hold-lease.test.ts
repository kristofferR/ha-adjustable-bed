// Renewable hold leases (#483): a declared controller gets one leased call
// renewed every 250 ms; everything else keeps its finite pulses.
// Run with: bun test
import { expect, test } from "bun:test";
import { bedEntitiesForDevice } from "./discovery";
import {
  attachHoldLifecycle,
  type Direction,
  canTapMove,
  HOLD_LEASE_MS,
  HOLD_LEASE_RENEW_MS,
  type HoldActions,
  type HoldLeaseCall,
  type HoldLifecycleTarget,
  type HoldTimers,
  MotorHold,
  movementLease,
  TAP_MOVE_MAX_MS,
} from "./hold";
import type { EntityRegistryDisplayEntry, HomeAssistant, MotorEntity } from "./types";

class FakeTimers implements HoldTimers {
  now = 0;
  private nextId = 0;
  private readonly timers = new Map<number, { due: number; callback: () => void }>();

  setTimeout(callback: () => void, delayMs: number): ReturnType<typeof setTimeout> {
    const id = ++this.nextId;
    this.timers.set(id, { due: this.now + delayMs, callback });
    return { id } as unknown as ReturnType<typeof setTimeout>;
  }

  clearTimeout(timer: ReturnType<typeof setTimeout>): void {
    this.timers.delete((timer as unknown as { id: number }).id);
  }

  advance(milliseconds: number): void {
    const end = this.now + milliseconds;
    while (true) {
      const next = [...this.timers.entries()]
        .filter(([, timer]) => timer.due <= end)
        .sort((left, right) => left[1].due - right[1].due)[0];
      if (!next) break;
      this.timers.delete(next[0]);
      this.now = next[1].due;
      next[1].callback();
    }
    this.now = end;
  }
}

// The backend's lease, on the fake clock: the first call of a generation
// starts motion and settles when it ends; a renewal replaces the deadline.
class FakeLeaseBed {
  readonly calls: Array<{ key: string; dir: Direction } & HoldLeaseCall> = [];
  moving = false;
  ignoreStop = false;
  refuseRenewals = false;
  private deadline = 0;
  private finish?: () => void;

  constructor(private readonly timers: FakeTimers) {}

  lease = (motor: MotorEntity, dir: Direction, lease: HoldLeaseCall): Promise<unknown> => {
    this.calls.push({ key: motor.key, dir, ...lease });
    this.deadline = this.timers.now + HOLD_LEASE_MS;
    this.timers.setTimeout(() => {
      if (this.timers.now >= this.deadline) this.end();
    }, HOLD_LEASE_MS);
    if (this.moving) {
      return this.refuseRenewals ? Promise.reject(new Error("ended")) : Promise.resolve();
    }
    this.moving = true;
    return new Promise<void>((resolve) => { this.finish = resolve; });
  };

  end(): void {
    this.moving = false;
    this.finish?.();
    this.finish = undefined;
  }

  stop(): void {
    if (!this.ignoreStop) this.end();
  }
}

interface Rig {
  bed: FakeLeaseBed;
  timers: FakeTimers;
  hold: MotorHold;
  events: string[];
  pulses: string[];
  changes: { count: number };
}

function rig(withLease = true): Rig {
  const timers = new FakeTimers();
  const bed = new FakeLeaseBed(timers);
  const events: string[] = [];
  const pulses: string[] = [];
  const changes = { count: 0 };
  const actions: HoldActions = {
    pulse: (motor, dir) => {
      pulses.push(`${motor.key}:${dir}`);
      return new Promise<void>(() => {});
    },
    holdControl: (motor, dir) => {
      events.push(`window:${motor.key}:${dir}`);
      return new Promise<void>(() => {});
    },
    ...(withLease ? { lease: bed.lease } : {}),
    stopCover: (cover) => {
      events.push(`cover-stop:${cover}`);
      bed.stop();
    },
    stopBed: (stop) => {
      events.push(`stop:${stop ?? ""}`);
      bed.stop();
    },
    changed: () => { changes.count++; },
  };
  return { bed, timers, hold: new MotorHold(actions, timers), events, pulses, changes };
}

const leasedCover: MotorEntity = {
  key: "back",
  cover: "cover.back",
  holdLease: { deviceId: "bed", motor: "back" },
};

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

test("a declared hold sends one leased call and renews it every 250 ms", () => {
  // The maintainer's cadence: two lost renewals end the hold.
  expect([HOLD_LEASE_RENEW_MS, HOLD_LEASE_MS]).toEqual([250, 750]);
  const { bed, timers, hold, pulses } = rig();
  hold.start(leasedCover, "up", 1);
  expect(bed.calls).toHaveLength(1);
  timers.advance(249);
  expect(bed.calls).toHaveLength(1);
  timers.advance(1);
  expect(bed.calls).toHaveLength(2);
  timers.advance(5000);
  // One call at 0 ms, then one every 250 ms: the lease never lapses.
  expect(bed.calls).toHaveLength(22);
  expect(bed.moving).toBe(true);
  expect(new Set(bed.calls.map((call) => `${call.owner}:${call.generation}`)).size).toBe(1);
  expect(pulses).toEqual([]);
});

test("release stops the renewals and keeps the STOP on release", () => {
  const { bed, timers, hold, events } = rig();
  hold.start(leasedCover, "up", 7);
  timers.advance(600);
  const sent = bed.calls.length;
  hold.endFromPointer({ ...leasedCover }, 7, true);
  expect(events).toEqual(["cover-stop:cover.back"]);
  expect(bed.moving).toBe(false);
  timers.advance(2000);
  expect(bed.calls).toHaveLength(sent);
});

test("the lease expires within 750 ms when renewals stop and STOP is lost", () => {
  const { bed, timers, hold } = rig();
  bed.ignoreStop = true;
  hold.start(leasedCover, "up", 1);
  timers.advance(500);
  // The last renewal went out at 500 ms; the card then leaves the page.
  hold.abandon();
  timers.advance(HOLD_LEASE_MS - 1);
  expect(bed.moving).toBe(true);
  timers.advance(1);
  expect(bed.moving).toBe(false);
});

test("unmount ends the hold and its renewals", () => {
  const { bed, timers, hold, events } = rig();
  hold.start(leasedCover, "down", 1);
  timers.advance(250);
  const sent = bed.calls.length;
  expect(hold.abandon()).toEqual(["cover.back"]);
  expect(events).toEqual(["cover-stop:cover.back"]);
  timers.advance(1000);
  expect(bed.calls).toHaveLength(sent);
});

test("a hidden document ends the hold and its renewals", () => {
  const { bed, timers, hold, events } = rig();
  const documentTarget = new FakeDocument();
  const remove = attachHoldLifecycle(hold, documentTarget, new FakeDocument());
  hold.start(leasedCover, "up", 1);
  timers.advance(250);
  const sent = bed.calls.length;
  documentTarget.visibilityState = "hidden";
  documentTarget.dispatch("visibilitychange");
  expect(events).toEqual(["cover-stop:cover.back"]);
  timers.advance(1000);
  expect(bed.calls).toHaveLength(sent);
  remove();
});

test("a hold the bed ends stops renewing but its release still sends STOP", async () => {
  const { bed, timers, hold, events } = rig();
  hold.start(leasedCover, "up", 1);
  timers.advance(250);
  // A STOP from elsewhere, or the 30-second ceiling, settles the starting call.
  bed.end();
  await tick();
  const sent = bed.calls.length;
  timers.advance(1000);
  expect(bed.calls).toHaveLength(sent);
  hold.endFromPointer(leasedCover, 1, true);
  expect(events).toEqual(["cover-stop:cover.back"]);
});

test("a refused renewal stops the renewals", async () => {
  const { bed, timers, hold } = rig();
  bed.refuseRenewals = true;
  hold.start(leasedCover, "up", 1);
  timers.advance(250);
  await tick();
  timers.advance(1000);
  expect(bed.calls).toHaveLength(2);
});

test("each press leases a new, higher generation for the same owner", () => {
  const { bed, timers, hold } = rig();
  hold.start(leasedCover, "up", 1);
  hold.end(leasedCover);
  hold.start(leasedCover, "down", 1);
  timers.advance(250);
  const [first, second, renewal] = bed.calls;
  expect(second.owner).toBe(first.owner);
  expect(second.generation).toBeGreaterThan(first.generation);
  expect(renewal).toEqual({ ...second });
});

test("controllers without a declared hold keep the finite pulse loop", () => {
  const { bed, timers, hold, pulses } = rig();
  const plain: MotorEntity = { key: "legs", cover: "cover.legs" };
  // A declared hold with no route the card can name also keeps pulses.
  const routeless: MotorEntity = { key: "tilt", cover: "cover.tilt", holdLease: { deviceId: "bed" } };
  for (const motor of [plain, routeless]) {
    hold.start(motor, "up", 1);
    timers.advance(1000);
    hold.end(motor);
  }
  expect(pulses).toEqual(["legs:up", "tilt:up"]);
  expect(bed.calls).toEqual([]);

  const withoutAction = rig(false);
  withoutAction.hold.start(leasedCover, "up", 1);
  withoutAction.timers.advance(1000);
  expect(withoutAction.pulses).toEqual(["back:up"]);
});

test("a held control waits its start delay, leases, and delays its release", () => {
  const { bed, timers, hold, events } = rig();
  const motor: MotorEntity = {
    key: "head",
    holdEntityId: "button.head_up",
    deviceId: "bed",
    heldControl: { control: "headUp", startDelayMs: 100, releaseDelayMs: 200 },
    holdLease: { deviceId: "bed" },
  };
  hold.start(motor, "up", 1, "button.stop");
  timers.advance(99);
  expect(bed.calls).toEqual([]);
  timers.advance(1 + HOLD_LEASE_RENEW_MS);
  expect(bed.calls).toHaveLength(2);
  hold.end(motor, "button.stop");
  timers.advance(199);
  expect(events).toEqual([]);
  timers.advance(1);
  expect(events).toEqual(["stop:button.stop"]);
  expect(bed.calls).toHaveLength(2);
});

test("leased calls carry the lease on the existing actions", async () => {
  const calls: unknown[] = [];
  const hass = {
    states: { "button.head_up": { attributes: { bed_side: "left" } } },
    callService: async (...args: unknown[]) => { calls.push(args); },
  } as unknown as HomeAssistant;
  const lease = { owner: "card-x", generation: 3 };
  await movementLease(hass, leasedCover, "up", lease);
  await movementLease(hass, {
    key: "back",
    timedMove: { deviceId: "pair", motor: "back", side: "both" },
    holdLease: { deviceId: "pair" },
  }, "down", lease);
  await movementLease(hass, {
    key: "head",
    holdEntityId: "button.head_up",
    deviceId: "child",
    heldControl: { control: "headUp", startDelayMs: 0, releaseDelayMs: 0 },
    holdLease: { deviceId: "child", side: "left" },
  }, "up", lease);
  expect(movementLease(hass, { key: "legs", cover: "cover.legs" }, "up", lease)).toBeUndefined();
  const owner = { hold_owner: "card-x", hold_generation: 3 };
  expect(calls).toEqual([
    ["adjustable_bed", "timed_move", {
      device_id: "bed", motor: "back", direction: "up", duration_ms: 750, ...owner,
    }],
    ["adjustable_bed", "timed_move", {
      device_id: "pair", side: "both", motor: "back", direction: "down", duration_ms: 750, ...owner,
    }],
    ["adjustable_bed", "hold_control", {
      device_id: ["child"], control: "headUp", duration: 0.75, ...owner, side: "left",
    }],
  ]);
});

function entry(entity_id: string, translation_key: string, device_id: string): EntityRegistryDisplayEntry {
  return { entity_id, translation_key, device_id, platform: "adjustable_bed" };
}

function hassWith(
  entries: EntityRegistryDisplayEntry[],
  attributes: Record<string, Record<string, unknown>>,
): HomeAssistant {
  return {
    entities: Object.fromEntries(entries.map((item) => [item.entity_id, item])),
    states: Object.fromEntries(Object.entries(attributes).map(([id, attrs]) => [id, {
      entity_id: id, state: "unknown", last_changed: "", last_updated: "", attributes: attrs,
    }])),
    devices: {},
    locale: { language: "en" },
    language: "en",
    themes: {},
    callService: async () => undefined,
  };
}

test("discovery reads the advertised hold from covers and combined motors", () => {
  const hass = hassWith([
    entry("cover.back", "back", "bed"),
    entry("cover.legs", "legs", "bed"),
  ], {
    "cover.back": { hold_lease_mode: "stream", hold_lease_motor: "back" },
    "cover.legs": {},
  });
  const motors = bedEntitiesForDevice(hass, "bed").motors;
  expect(motors.find((motor) => motor.key === "back")?.holdLease)
    .toEqual({ deviceId: "bed", motor: "back" });
  expect(motors.find((motor) => motor.key === "legs")?.holdLease).toBeUndefined();

  // The backend advertises a combined hold only when both sides declare the
  // same mode; one call to the parent then renews both sides.
  const paired = hassWith([
    entry("button.pair_back_up", "back_up", "pair"),
    entry("button.pair_back_down", "back_down", "pair"),
  ], {
    "button.pair_back_up": { hold_lease_mode: "latched", hold_lease_motor: "back", bed_side: "both" },
    "button.pair_back_down": { hold_lease_mode: "latched", hold_lease_motor: "back", bed_side: "both" },
  });
  const combined = bedEntitiesForDevice(paired, "pair").motors[0];
  expect(combined.holdLease).toEqual({ deviceId: "pair", motor: "back", side: "both" });
  const { bed, timers, hold } = rig();
  hold.start(combined, "up", 1);
  timers.advance(500);
  expect(bed.calls).toHaveLength(3);

  for (const id of ["button.pair_back_up", "button.pair_back_down"]) {
    delete paired.states[id].attributes.hold_lease_mode;
  }
  expect(bedEntitiesForDevice(paired, "pair").motors[0].holdLease).toBeUndefined();
});

// Tap to move (#609): a tap starts a motor, the next tap stops it.

test("a tap leases the motor until the next tap, which stops it and starts nothing", () => {
  const { bed, timers, hold, events, changes } = rig();
  hold.tap(leasedCover, "up");
  expect(hold.tapDirection({ ...leasedCover })).toBe("up");
  timers.advance(5000);
  // One call at 0 ms and a renewal every 250 ms, as for a held press.
  expect(bed.calls).toHaveLength(21);
  expect(bed.moving).toBe(true);
  // Any arrow stops the running motor; it does not start the tapped one.
  hold.tap({ key: "legs", cover: "cover.legs" }, "down");
  expect(events).toEqual(["cover-stop:cover.back"]);
  expect(bed.moving).toBe(false);
  expect(hold.tapMoving).toBe(false);
  timers.advance(1000);
  expect(bed.calls).toHaveLength(21);
  expect(changes.count).toBe(2);
});

test("a tap move stops after 30 s however long its renewals succeed", () => {
  const { bed, timers, hold, events } = rig();
  hold.tap(leasedCover, "up");
  timers.advance(TAP_MOVE_MAX_MS - 1);
  expect(hold.tapMoving).toBe(true);
  timers.advance(1);
  expect(events).toEqual(["cover-stop:cover.back"]);
  expect(bed.moving).toBe(false);
  expect(hold.tapMoving).toBe(false);
});

test("a tap move the bed ends or refuses ends without a STOP of its own", async () => {
  // The backend's ceiling, a replacing command, or a lost connection. The
  // backend already released the hold, and a STOP could cancel a replacement.
  const ended = rig();
  ended.hold.tap(leasedCover, "up");
  ended.timers.advance(250);
  ended.bed.end();
  await tick();
  expect(ended.hold.tapMoving).toBe(false);
  expect(ended.events).toEqual([]);

  const refused = rig();
  refused.bed.refuseRenewals = true;
  refused.hold.tap(leasedCover, "up");
  refused.timers.advance(250);
  await tick();
  expect(refused.hold.tapMoving).toBe(false);
  refused.timers.advance(1000);
  expect(refused.bed.calls).toHaveLength(2);
  expect(refused.events).toEqual([]);
});

test("a key or pointer release does not end a tap move", () => {
  const { bed, hold } = rig();
  hold.tap(leasedCover, "up");
  // Enter and Space activate the arrow, so their release reaches the window.
  hold.endKeyboard(undefined, undefined, "Enter");
  hold.endKeyboard(leasedCover);
  hold.endActiveFromPointer(1, true);
  expect(hold.tapMoving).toBe(true);
  expect(bed.moving).toBe(true);
});

test("a tap without a declared hold repeats finite pulses until one fails", async () => {
  const timers = new FakeTimers();
  const events: string[] = [];
  let sent = 0;
  const hold = new MotorHold({
    pulse: (motor, dir) => {
      events.push(`pulse:${motor.key}:${dir}`);
      return ++sent < 3 ? Promise.resolve() : Promise.reject(new Error("link lost"));
    },
    stopCover: (cover) => events.push(`stop:${cover}`),
    stopBed: () => undefined,
  }, timers);
  hold.tap({ key: "legs", cover: "cover.legs" }, "up");
  await tick();
  // Each pulse stops by itself, so the failed one needs no STOP.
  expect(events).toEqual(["pulse:legs:up", "pulse:legs:up", "pulse:legs:up"]);
  expect(hold.tapMoving).toBe(false);
});

test("a held control without a lease keeps press-and-hold", () => {
  const { hold, events, bed } = rig();
  const windowed: MotorEntity = {
    key: "head",
    holdEntityId: "button.head_up",
    deviceId: "bed",
    heldControl: { control: "headUp", startDelayMs: 0, releaseDelayMs: 0 },
  };
  // Its 60 s window ends only on release, so a vanished card would not stop it.
  expect(canTapMove(windowed, "up")).toBe(false);
  expect(canTapMove({ ...windowed, holdLease: { deviceId: "bed" } }, "up")).toBe(true);
  expect(canTapMove({ key: "legs", cover: "cover.legs" }, "up")).toBe(true);
  hold.tap(windowed, "up");
  expect(hold.tapMoving).toBe(false);
  expect(events).toEqual([]);
  expect(bed.calls).toEqual([]);
});

class FakeDocument implements HoldLifecycleTarget {
  visibilityState = "visible";
  private readonly listeners = new Map<string, Set<() => void>>();

  addEventListener(type: "visibilitychange" | "pagehide", listener: () => void): void {
    const listeners = this.listeners.get(type) ?? new Set();
    listeners.add(listener);
    this.listeners.set(type, listeners);
  }

  removeEventListener(type: "visibilitychange" | "pagehide", listener: () => void): void {
    this.listeners.get(type)?.delete(listener);
  }

  dispatch(type: "visibilitychange" | "pagehide"): void {
    this.listeners.get(type)?.forEach((listener) => listener());
  }
}
