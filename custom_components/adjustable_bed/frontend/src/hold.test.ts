// Unit tests for the press-and-hold state machine.
// Run with: bun test
//
// Every case here is a defect that was found in review while building this, so
// they are regression tests rather than illustrative examples.
import { expect, test } from "bun:test";
import {
  attachHoldLifecycle,
  heldButtonMotor,
  type Direction,
  type HoldActions,
  type HoldTimers,
  type HoldLifecycleTarget,
  MotorHold,
  movementHold,
  movementPulse,
} from "./hold";
import type { HomeAssistant, MotorEntity } from "./types";

interface Recorder {
  actions: HoldActions;
  pulses: Array<{ key: string; dir: Direction }>;
  stoppedCovers: string[];
  stoppedCoverTargets: Array<string | undefined>;
  bedStops: number;
  // Which stop each bedStop pressed. On a paired bed each side has its own, so
  // "a stop happened" is not enough: it has to be the held side's.
  stoppedBeds: Array<string | undefined>;
  // Lets a test decide when the in-flight pulse resolves, which is the whole
  // point: a hold ends while a pulse is still running.
  release: () => void;
}

// Pulses never resolve on their own: a test drives them with release(). In
// production each pulse takes about a second, but a promise that resolves
// immediately would spin the repeat loop as fast as the microtask queue allows
// and starve the timers the test itself waits on.
function recorder(opts: { reject?: boolean; missingEntity?: boolean } = {}): Recorder {
  const pulses: Array<{ key: string; dir: Direction }> = [];
  const stoppedCovers: string[] = [];
  let resolvePending: (() => void) | null = null;
  const rec: Recorder = {
    pulses,
    stoppedCovers,
    stoppedCoverTargets: [],
    bedStops: 0,
    stoppedBeds: [],
    release: () => resolvePending?.(),
    actions: {
      pulse: (m, dir) => {
        // The card returns undefined when the motor has no entity for this
        // direction, which must end the loop rather than spin it.
        if (opts.missingEntity) return undefined;
        pulses.push({ key: m.key, dir });
        if (opts.reject) return Promise.reject(new Error("bed said no"));
        return new Promise<void>((resolve) => {
          resolvePending = resolve;
        });
      },
      holdControl: () => undefined,
      stopCover: (cover, stopEntityId) => {
        stoppedCovers.push(cover);
        rec.stoppedCoverTargets.push(stopEntityId);
      },
      stopBed: (stopEntityId) => {
        rec.bedStops += 1;
        rec.stoppedBeds.push(stopEntityId);
      },
    },
  };
  return rec;
}

const buttonMotor: MotorEntity = { key: "head", up: "button.head_up", down: "button.head_down" };
const coverMotor: MotorEntity = { key: "legs", cover: "cover.legs" };

// A fresh object for the same motor, as render() produces on every state
// change. Ownership must survive this.
const rebuiltButtonMotor: MotorEntity = { ...buttonMotor };

class FakeTimers implements HoldTimers {
  private now = 0;
  private nextId = 0;
  private readonly timers = new Map<number, { due: number; callback: () => void }>();

  setTimeout(callback: () => void, delayMs: number): ReturnType<typeof setTimeout> {
    const id = ++this.nextId;
    this.timers.set(id, { due: this.now + delayMs, callback });
    return { id } as unknown as ReturnType<typeof setTimeout>;
  }

  clearTimeout(timer: ReturnType<typeof setTimeout>): void {
    const handle = timer as unknown as { id: number };
    this.timers.delete(handle.id);
  }

  advance(milliseconds: number): void {
    const end = this.now + milliseconds;
    while (true) {
      const next = [...this.timers.entries()]
        .filter(([, timer]) => timer.due <= end)
        .sort((left, right) => left[1].due - right[1].due)[0];
      if (!next) break;
      const [id, timer] = next;
      this.timers.delete(id);
      this.now = timer.due;
      timer.callback();
    }
    this.now = end;
  }
}

class FakeLifecycleTarget implements HoldLifecycleTarget {
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

function heldActions(events: string[]): HoldActions {
  return {
    pulse: () => undefined,
    holdControl: (motor, direction) => {
      events.push(`start:${motor.key}:${direction}`);
      return new Promise<void>(() => {});
    },
    stopCover: (cover, stop) => events.push(`cover-stop:${cover}:${stop ?? ""}`),
    stopBed: (stop) => events.push(`stop:${stop ?? ""}`),
  };
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

test("button hold metadata uses the bounded side-scoped service", async () => {
  const calls: unknown[] = [];
  const entityId = "button.left_head_up";
  const hass = {
    entities: { [entityId]: { device_id: "left-device" } },
    states: {
      [entityId]: {
        attributes: {
          held_control: "headUp",
          hold_start_delay_ms: 100,
          hold_release_delay_ms: 100,
          bed_side: "left",
        },
      },
    },
    callService: async (...args: unknown[]) => { calls.push(args); },
  } as HomeAssistant;

  const motor = heldButtonMotor(hass, entityId);
  expect(motor?.heldControl).toEqual({
    control: "headUp",
    startDelayMs: 100,
    releaseDelayMs: 100,
  });
  await movementHold(hass, motor!, "up");

  expect(calls).toEqual([[
    "adjustable_bed",
    "hold_control",
    { device_id: ["left-device"], control: "headUp", duration: 60, side: "left" },
  ]]);
});

test("eligible Both holds use the parent timed action and retain combined Stop", async () => {
  const calls: unknown[] = [];
  let finish!: () => void;
  const hass = { callService: (...args: unknown[]) => {
    calls.push(args);
    return new Promise<void>((resolve) => { finish = resolve; });
  } } as HomeAssistant;
  const motor: MotorEntity = { key: "back", up: "button.pair_back_up",
    timedMove: { deviceId: "pair", motor: "back" } };
  const rec = recorder();
  const hold = new MotorHold({ ...rec.actions, pulse: (m, dir) => movementPulse(hass, m, dir) });
  hold.start(motor, "up", 1, "button.pair_stop");
  expect(calls).toEqual([["adjustable_bed", "timed_move", {
    device_id: "pair", side: "both", motor: "back", direction: "up", duration_ms: 1000,
  }]]);
  hold.end({ ...motor });
  finish();
  await tick();
  expect(calls).toHaveLength(1);
  expect(rec.stoppedBeds).toEqual(["button.pair_stop"]);
});

test("ordinary covers, buttons and unsupported directions keep their finite actions", async () => {
  const calls: unknown[] = [];
  const hass = { callService: async (...args: unknown[]) => { calls.push(args); } } as HomeAssistant;
  await movementPulse(hass, coverMotor, "down");
  await movementPulse(hass, buttonMotor, "up");
  expect(movementPulse(hass, { key: "back_legs" }, "down")).toBeUndefined();
  expect(calls).toEqual([
    ["cover", "close_cover", { entity_id: "cover.legs" }],
    ["button", "press", { entity_id: "button.head_up" }],
  ]);
});

test("a hold repeats until it is released", async () => {
  const rec = recorder();
  const hold = new MotorHold(rec.actions);

  hold.start(buttonMotor, "up", 1);
  await tick();
  expect(rec.pulses.length).toBe(1);

  rec.release();
  await tick();
  expect(rec.pulses.length).toBe(2);

  hold.end(buttonMotor);
  rec.release();
  await tick();
  await tick();
  // No further pulse after the release, and the bed was told to stop.
  expect(rec.pulses.length).toBe(2);
  expect(rec.bedStops).toBe(1);
});

test("ownership survives the card rebuilding the motor object", async () => {
  const rec = recorder();
  const hold = new MotorHold(rec.actions);

  hold.start(buttonMotor, "up", 1);
  await tick();
  // The first pulse completing re-renders the card, so the release handler
  // receives a different object for the same motor.
  hold.end(rebuiltButtonMotor);
  rec.release();
  await tick();
  await tick();

  expect(hold.heldKey).toBeNull();
  expect(rec.pulses.length).toBe(1);
});

test("releasing one motor does not end another motor's hold", async () => {
  const rec = recorder();
  const hold = new MotorHold(rec.actions);

  hold.start(buttonMotor, "up", 1);
  await tick();
  hold.end(coverMotor);

  expect(hold.heldKey).toBe("head");
  expect(rec.bedStops).toBe(0);
  expect(rec.stoppedCovers).toEqual([]);

  hold.end(buttonMotor);
  rec.release();
  await tick();
});

test("a second pointer's release is ignored", async () => {
  const rec = recorder();
  const hold = new MotorHold(rec.actions);

  hold.start(buttonMotor, "up", 1);
  await tick();

  hold.endFromPointer(buttonMotor, 2, true);
  expect(hold.heldKey).toBe("head");

  hold.endFromPointer(buttonMotor, 1, true);
  expect(hold.heldKey).toBeNull();
  rec.release();
  await tick();
});

test("a non-primary button release is ignored", async () => {
  const rec = recorder();
  const hold = new MotorHold(rec.actions);

  hold.start(buttonMotor, "up", 1);
  await tick();

  hold.endFromPointer(buttonMotor, 1, false);
  expect(hold.heldKey).toBe("head");

  hold.endFromPointer(buttonMotor, 1, true);
  expect(hold.heldKey).toBeNull();
  rec.release();
  await tick();
});

test("keyboard holds have no owning pointer, so any release ends them", async () => {
  const rec = recorder();
  const hold = new MotorHold(rec.actions);

  hold.start(buttonMotor, "up", null);
  await tick();
  hold.endFromPointer(buttonMotor, 99, true);

  expect(hold.heldKey).toBeNull();
  rec.release();
  await tick();
});

test("a cover-backed hold stops the cover and preserves its retained bed target", async () => {
  const rec = recorder();
  const hold = new MotorHold(rec.actions);

  hold.start(coverMotor, "down", 1, "button.left_stop");
  await tick();
  hold.end(coverMotor);
  rec.release();
  await tick();

  expect(rec.stoppedCovers).toEqual(["cover.legs"]);
  expect(rec.stoppedCoverTargets).toEqual(["button.left_stop"]);
  expect(rec.bedStops).toBe(0);
});

test("stopAll ends a hold on a different motor", async () => {
  const rec = recorder();
  const hold = new MotorHold(rec.actions);

  hold.start(buttonMotor, "up", 1);
  await tick();
  // The user hits the bed-wide stop, or another row's stop, while head is held.
  hold.stopAll();
  rec.release();
  await tick();
  await tick();

  expect(hold.heldKey).toBeNull();
  expect(rec.bedStops).toBe(1);
  // Crucially the loop did not issue another pulse after the stop landed.
  expect(rec.pulses.length).toBe(1);
});

test("cancel stops the loop without touching the bed", async () => {
  const rec = recorder();
  const hold = new MotorHold(rec.actions);

  hold.start(buttonMotor, "up", 1);
  await tick();
  expect(hold.cancel(buttonMotor)).toBe(true);
  rec.release();
  await tick();
  await tick();

  expect(rec.bedStops).toBe(0);
  expect(rec.stoppedCovers).toEqual([]);
  expect(rec.pulses.length).toBe(1);
});

test("cancel ignores a motor that does not own the hold", async () => {
  const rec = recorder();
  const hold = new MotorHold(rec.actions);

  hold.start(buttonMotor, "up", 1);
  await tick();
  expect(hold.cancel(coverMotor)).toBe(false);
  expect(hold.cancel(null)).toBe(false);
  expect(hold.heldKey).toBe("head");

  hold.end(buttonMotor);
  rec.release();
  await tick();
});

test("abandoning mid-hold stops a cover that would keep running", async () => {
  const rec = recorder();
  const hold = new MotorHold(rec.actions);

  hold.start(coverMotor, "up", 1);
  await tick();
  hold.abandon();
  rec.release();
  await tick();
  await tick();

  expect(hold.heldKey).toBeNull();
  expect(rec.stoppedCovers).toEqual(["cover.legs"]);
  expect(rec.pulses.length).toBe(1);
});

test("abandoning a button-backed hold stops the bed", async () => {
  const rec = recorder();
  const hold = new MotorHold(rec.actions);

  hold.start(buttonMotor, "up", 1);
  await tick();
  // Navigating away leaves the pulse in flight; without a stop the bed keeps
  // moving for the rest of it with the control no longer on screen.
  hold.abandon();
  rec.release();
  await tick();

  expect(rec.bedStops).toBe(1);
  expect(rec.stoppedCovers).toEqual([]);
});

test("abandoning with no hold active touches nothing", async () => {
  const rec = recorder();
  const hold = new MotorHold(rec.actions);

  hold.abandon();

  expect(rec.bedStops).toBe(0);
  expect(rec.stoppedCovers).toEqual([]);
});

test("a second start while held is ignored", async () => {
  const rec = recorder();
  const hold = new MotorHold(rec.actions);

  hold.start(buttonMotor, "up", 1);
  await tick();
  hold.start(coverMotor, "down", 2);
  await tick();

  expect(hold.heldKey).toBe("head");
  expect(rec.pulses.every((p) => p.key === "head")).toBe(true);

  hold.end(buttonMotor);
  rec.release();
  await tick();
});

test("a rejected pulse stops the loop instead of hammering the bed", async () => {
  const rec = recorder({ reject: true });
  const hold = new MotorHold(rec.actions);

  hold.start(buttonMotor, "up", 1);
  await tick();
  await tick();

  expect(rec.pulses.length).toBe(1);
});

test("a motor with no entity for that direction never pulses", async () => {
  const rec = recorder({ missingEntity: true });
  const hold = new MotorHold(rec.actions);
  const upOnly: MotorEntity = { key: "lumbar", up: "button.lumbar_up" };

  hold.start(upOnly, "down", 1);
  await tick();
  await tick();

  // The loop exits immediately rather than spinning on a motor it cannot move.
  expect(rec.pulses.length).toBe(0);
  hold.end(upOnly);
  expect(rec.bedStops).toBe(1);
});

// A paired bed renders one section per side, each with its own stop. Pressing
// the parent's stop, or none at all, would leave the released side running.
test("releasing a hold stops the side the motor belongs to", async () => {
  const rec = recorder();
  const hold = new MotorHold(rec.actions);

  hold.start(buttonMotor, "up", 1, "button.left_stop");
  await tick();
  hold.end(buttonMotor);

  expect(rec.stoppedBeds).toEqual(["button.left_stop"]);
});

test("a side's stop button stops that side, not the held one", async () => {
  const rec = recorder();
  const hold = new MotorHold(rec.actions);

  hold.start(buttonMotor, "up", 1, "button.left_stop");
  await tick();
  // The pressed button carries its own stop, which wins: it is the bed the
  // user actually asked to stop.
  hold.stopAll("button.right_stop");

  expect(rec.stoppedBeds).toEqual(["button.right_stop"]);
  expect(hold.heldKey).toBe(buttonMotor.key);

  hold.end(buttonMotor);
  expect(rec.stoppedBeds).toEqual(["button.right_stop", "button.left_stop"]);
  expect(hold.heldKey).toBeNull();
});

test("abandoning mid-hold stops the held side", async () => {
  const rec = recorder();
  const hold = new MotorHold(rec.actions);

  hold.start(buttonMotor, "up", 1, "button.left_stop");
  await tick();
  hold.abandon();

  expect(rec.stoppedBeds).toEqual(["button.left_stop"]);
});

test("a tap canceled before the declared start delay never starts movement", () => {
  const events: string[] = [];
  const timers = new FakeTimers();
  const hold = new MotorHold(heldActions(events), timers);
  const delayed: MotorEntity = {
    key: "left-head",
    up: "button.left_head_up",
    heldControl: { control: "headUp", startDelayMs: 100, releaseDelayMs: 100 },
  };

  hold.start(delayed, "up", 1, "button.left_stop");
  timers.advance(99);
  hold.end(delayed);
  timers.advance(1_000);

  expect(events).toEqual([]);
  expect(hold.heldKey).toBeNull();
});

test("release delay retains its old side when a new side starts", () => {
  const events: string[] = [];
  const timers = new FakeTimers();
  const hold = new MotorHold(heldActions(events), timers);
  const left: MotorEntity = {
    key: "left-head",
    up: "button.left_head_up",
    heldControl: { control: "headUp", startDelayMs: 0, releaseDelayMs: 100 },
  };
  const right: MotorEntity = {
    key: "right-head",
    up: "button.right_head_up",
    heldControl: { control: "headUp", startDelayMs: 0, releaseDelayMs: 100 },
  };

  hold.start(left, "up", 1, "button.left_stop");
  hold.end(left);
  hold.start(right, "up", 2, "button.right_stop");
  expect(events).toEqual([
    "start:left-head:up",
    "start:right-head:up",
  ]);

  timers.advance(100);
  expect(events).toEqual([
    "start:left-head:up",
    "start:right-head:up",
    "stop:button.left_stop",
  ]);
});

test("a new start flushes its own pending release before moving again", () => {
  const events: string[] = [];
  const timers = new FakeTimers();
  const hold = new MotorHold(heldActions(events), timers);
  const left: MotorEntity = {
    key: "left-head",
    up: "button.left_head_up",
    heldControls: {
      up: { control: "headUp", startDelayMs: 0, releaseDelayMs: 100 },
      down: { control: "headDown", startDelayMs: 200, releaseDelayMs: 50 },
    },
  };

  hold.start(left, "up", 1, "button.left_stop");
  hold.end(left);
  hold.start({ ...left }, "up", 2, "button.left_stop");

  expect(events).toEqual([
    "start:left-head:up",
    "stop:button.left_stop",
    "start:left-head:up",
  ]);
  hold.abandon();
  timers.advance(500);
  expect(events.filter((event) => event === "stop:button.left_stop")).toHaveLength(2);
});

test("abandon flushes pending release and cancels an active or delayed hold", () => {
  const events: string[] = [];
  const timers = new FakeTimers();
  const hold = new MotorHold(heldActions(events), timers);
  const delayed: MotorEntity = {
    key: "left-head",
    up: "button.left_head_up",
    heldControl: { control: "headUp", startDelayMs: 100, releaseDelayMs: 100 },
  };

  hold.start(delayed, "up", 1, "button.left_stop");
  hold.abandon();
  timers.advance(100);
  expect(events).toEqual([]);

  const started = { ...delayed, heldControl: { ...delayed.heldControl!, startDelayMs: 0 } };
  hold.start(started, "up", 1, "button.left_stop");
  hold.abandon();
  expect(events).toEqual([
    "start:left-head:up",
    "stop:button.left_stop",
  ]);

  hold.start(started, "up", 1, "button.left_stop");
  hold.end(started);
  hold.abandon();
  timers.advance(100);
  expect(events.filter((event) => event === "stop:button.left_stop")).toHaveLength(2);
});

test("hidden and pagehide abandon holds, then remove their lifecycle listeners", () => {
  const events: string[] = [];
  const hold = new MotorHold(heldActions(events), new FakeTimers());
  const documentTarget = new FakeLifecycleTarget();
  const windowTarget = new FakeLifecycleTarget();
  const detach = attachHoldLifecycle(hold, documentTarget, windowTarget);
  const active: MotorEntity = {
    key: "left-head",
    up: "button.left_head_up",
    heldControl: { control: "headUp", startDelayMs: 0, releaseDelayMs: 100 },
  };

  hold.start(active, "up", 1, "button.left_stop");
  documentTarget.visibilityState = "hidden";
  documentTarget.dispatch("visibilitychange");
  expect(events).toEqual([
    "start:left-head:up",
    "stop:button.left_stop",
  ]);

  hold.start(active, "up", 2, "button.left_stop");
  windowTarget.dispatch("pagehide");
  expect(events.filter((event) => event === "stop:button.left_stop")).toHaveLength(2);

  detach();
  hold.start(active, "up", 3, "button.left_stop");
  windowTarget.dispatch("pagehide");
  expect(hold.heldKey).toBe("left-head");
  hold.abandon();
});
