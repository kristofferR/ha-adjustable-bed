// Unit tests for the press-and-hold state machine.
// Run with: bun test
//
// Every case here is a defect that was found in review while building this, so
// they are regression tests rather than illustrative examples.
import { expect, test } from "bun:test";
import {
  attachHoldLifecycle,
  heldButtonMotor,
  holdTargetForEntity,
  pairedPeerStopEntityIds,
  type Direction,
  type HoldActions,
  type HoldTimers,
  type HoldLifecycleTarget,
  MotorHold,
  movementHold,
  movementPulse,
  stopFromCard,
} from "./hold";
import { bedEntitiesForDevice } from "./discovery";
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

test("one side's release does not end the other side's hold on a motor with the same key", async () => {
  // A paired bed renders one section per side, each with its own "back".
  const rec = recorder();
  const hold = new MotorHold(rec.actions);
  const left: MotorEntity = { key: "back", cover: "cover.left_back" };
  const right: MotorEntity = { key: "back", cover: "cover.right_back" };

  hold.start(right, "up", 1);
  await tick();
  hold.end(left);

  expect(hold.heldKey).toBe("back");
  expect(rec.stoppedCovers).toEqual([]);

  hold.end({ ...right });
  expect(rec.stoppedCovers).toEqual(["cover.right_back"]);
  rec.release();
  await tick();
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

function pairedStopHass(): HomeAssistant {
  return {
    entities: {
      "button.parent_stop": { device_id: "pair-parent" },
      "button.left_stop": { device_id: "pair-left" },
      "button.right_stop": { device_id: "pair-right" },
      "button.other_stop": { device_id: "other-bed" },
    },
    states: {
      "button.parent_stop": { attributes: { bed_side: "both" } },
      "button.left_stop": { attributes: { bed_side: "left" } },
      "button.right_stop": { attributes: { bed_side: "right" } },
      "button.other_stop": { attributes: {} },
    },
    devices: {
      "pair-parent": { id: "pair-parent" },
      "pair-left": { id: "pair-left", parent_device_id: "pair-parent" },
      "pair-right": { id: "pair-right", parent_device_id: "pair-parent" },
      "other-bed": { id: "other-bed" },
    },
  } as HomeAssistant;
}

test("card Left or Right Stop invalidates an in-flight combined hold", async () => {
  for (const side of ["left", "right"] as const) {
    const hass = pairedStopHass();
    const rec = recorder();
    const hold = new MotorHold(rec.actions);
    const motor: MotorEntity = { key: "both-head", up: "button.both_head_up" };

    hold.start(
      motor,
      "up",
      1,
      "button.parent_stop",
      holdTargetForEntity(hass, "button.parent_stop"),
    );
    await tick();
    expect(rec.pulses).toHaveLength(1);

    // The card's actual Stop callback resolves the child side from its device
    // and bed_side metadata while issuing that exact child Stop target.
    const stopEntityId = `button.${side}_stop`;
    stopFromCard(hold, hass, stopEntityId);
    rec.release();
    await tick();
    await tick();

    expect(hold.heldKey).toBeNull();
    expect(rec.pulses).toHaveLength(1);
    expect(rec.stoppedBeds).toEqual([stopEntityId]);
  }
});

test("side Stop leaves an opposite-side or unrelated-bed hold active", async () => {
  const hass = pairedStopHass();
  const rec = recorder();
  const hold = new MotorHold(rec.actions);
  const right: MotorEntity = { key: "right-head", up: "button.right_head_up" };

  hold.start(
    right,
    "up",
    1,
    "button.right_stop",
    holdTargetForEntity(hass, "button.right_stop"),
  );
  await tick();
  stopFromCard(hold, hass, "button.left_stop");
  expect(hold.heldKey).toBe("right-head");
  expect(rec.pulses).toHaveLength(1);
  rec.release();
  await tick();
  expect(rec.pulses).toHaveLength(2);

  hold.abandon();
  rec.release();
  await tick();
  const other = { key: "other-head", up: "button.other_head_up" };
  hold.start(other, "up", 2, "button.other_stop", holdTargetForEntity(hass, "button.other_stop"));
  await tick();
  stopFromCard(hold, hass, "button.parent_stop");
  expect(hold.heldKey).toBe("other-head");
  rec.release();
  await tick();
  expect(rec.pulses).toHaveLength(4);
  hold.abandon();
  rec.release();
  await tick();
});

test("parent Both Stop invalidates a side hold and owns its release", async () => {
  const hass = pairedStopHass();
  const rec = recorder();
  const hold = new MotorHold(rec.actions);
  const left: MotorEntity = { key: "left-head", up: "button.left_head_up" };

  hold.start(
    left,
    "up",
    1,
    "button.left_stop",
    holdTargetForEntity(hass, "button.left_stop"),
  );
  await tick();
  stopFromCard(hold, hass, "button.parent_stop");
  rec.release();
  await tick();

  expect(hold.heldKey).toBeNull();
  expect(rec.pulses).toHaveLength(1);
  expect(rec.stoppedBeds).toEqual(["button.parent_stop"]);
});

test("abandoning mid-hold stops the held side", async () => {
  const rec = recorder();
  const hold = new MotorHold(rec.actions);

  hold.start(buttonMotor, "up", 1, "button.left_stop");
  await tick();
  hold.abandon();

  expect(rec.stoppedBeds).toEqual(["button.left_stop"]);
});

test("opaque MX action uses one bounded service and retains the native child STOP owner", async () => {
  const { heldButtonMotor, movementHold } = await import("./hold");
  const calls: Array<{ domain: string; service: string; data: Record<string, unknown> }> = [];
  let finish: (() => void) | undefined;
  const hass = {
    entities: { "button.mx_memory1": { entity_id: "button.mx_memory1", device_id: "right-child" } },
    states: { "button.mx_memory1": { attributes: { held_control: "mx_memory1", hold_start_delay_ms: 0, hold_release_delay_ms: 0, bed_side: "right" } } },
    callService: async (domain: string, service: string, data: Record<string, unknown>) => {
      calls.push({ domain, service, data });
      if (service === "hold_control") await new Promise<void>((resolve) => { finish = resolve; });
    },
  } as unknown as HomeAssistant;
  const motor = heldButtonMotor(hass, "button.mx_memory1")!;
  expect(motor.heldControl).toEqual({ control: "mx_memory1", startDelayMs: 0, releaseDelayMs: 0 });
  const rec = recorder();
  const hold = new MotorHold({ ...rec.actions, holdControl: (m, dir) => movementHold(hass, m, dir) });
  hold.start(motor, "up", null, "button.right_stop");
  expect(calls).toEqual([{ domain: "adjustable_bed", service: "hold_control", data: {
    device_id: ["right-child"], control: "mx_memory1", duration: 60, side: "right",
  } }]);
  expect(rec.pulses).toEqual([]);
  // Keyboard release uses the exact retained STOP owner, including after discovery rebuild.
  hold.end({ ...motor });
  expect(rec.stoppedBeds).toEqual(["button.right_stop"]);
  finish?.();
  await Promise.resolve();
  expect(hold.heldKey).toBeNull();
  expect(calls).toHaveLength(1);
});

test("page abandonment cancels the owning cover hold and never repeats finite pulses", async () => {
  const rec = recorder();
  const holds: string[] = [];
  const motor: MotorEntity = { key: "back", cover: "cover.left_back", deviceId: "left-child", heldControls: {
    up: { control: "head_up", startDelayMs: 0, releaseDelayMs: 0 },
  } };
  let finish: (() => void) | undefined;
  const hold = new MotorHold({ ...rec.actions, holdControl: (m) => {
    holds.push(m.key);
    return new Promise<void>((resolve) => { finish = resolve; });
  } });
  hold.start(motor, "up", 7, "button.left_stop");
  hold.abandon();
  expect(holds).toEqual(["back"]);
  expect(rec.pulses).toEqual([]);
  expect(rec.stoppedCovers).toEqual(["cover.left_back"]);
  expect(rec.stoppedCoverTargets).toEqual(["button.left_stop"]);
  finish?.();
  await Promise.resolve();
  expect(hold.heldKey).toBeNull();
});

test("unsupported combined direction retains finite fallback", async () => {
  const rec = recorder();
  const motor: MotorEntity = { key: "back", up: "button.both_up", down: "button.both_down", heldControls: {
    down: { control: "head_down", startDelayMs: 0, releaseDelayMs: 0 },
  } };
  const hold = new MotorHold(rec.actions);
  hold.start(motor, "up", 1, "button.pair_stop");
  expect(rec.pulses).toEqual([{ key: "back", dir: "up" }]);
  hold.end(motor);
  rec.release();
  await Promise.resolve();
  expect(rec.stoppedBeds).toEqual(["button.pair_stop"]);
});

test("flat button hold metadata requires its owning device and rejects nested metadata", async () => {
  const { heldButtonMotor } = await import("./hold");
  const hass = {
    entities: { "button.action": { device_id: "bed" } },
    states: { "button.action": { attributes: { held_control: { control: "head_up" }, hold_start_delay_ms: 0, hold_release_delay_ms: 0 } } },
  } as unknown as HomeAssistant;
  expect(heldButtonMotor(hass, "button.action")).toBeUndefined();
  hass.states["button.action"].attributes = { held_control: "head_up", hold_start_delay_ms: 0, hold_release_delay_ms: 0 };
  expect(heldButtonMotor(hass, "button.action")?.deviceId).toBe("bed");
  delete hass.entities["button.action"].device_id;
  expect(heldButtonMotor(hass, "button.action")).toBeUndefined();
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

test("a side Stop cancels overlapping delayed Both release but retains the other side", () => {
  for (const side of ["left", "right"] as const) {
    const events: string[] = [];
    const timers = new FakeTimers();
    const hold = new MotorHold(heldActions(events), timers);
    const hass = pairedStopHass();
    const both: MotorEntity = {
      key: "both-head",
      up: "button.both_head_up",
      heldControl: { control: "headUp", startDelayMs: 0, releaseDelayMs: 100 },
    };
    const otherSide = side === "left" ? "right" : "left";
    const other: MotorEntity = {
      key: `${otherSide}-head`,
      up: `button.${otherSide}_head_up`,
      heldControl: { control: "headUp", startDelayMs: 0, releaseDelayMs: 100 },
    };

    hold.start(
      both,
      "up",
      1,
      "button.parent_stop",
      holdTargetForEntity(hass, "button.parent_stop"),
    );
    hold.end(both);
    hold.start(
      other,
      "up",
      2,
      `button.${otherSide}_stop`,
      holdTargetForEntity(hass, `button.${otherSide}_stop`),
    );
    stopFromCard(hold, hass, `button.${side}_stop`);
    timers.advance(100);

    expect(hold.heldKey).toBe(`${otherSide}-head`);
    expect(events).toEqual([
      "start:both-head:up",
      `start:${otherSide}-head:up`,
      `stop:button.${side}_stop`,
    ]);
    hold.abandon();
  }
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

// Two-address OCTO children publish no logical side, so the registry graph and
// the Stop translation keys are what keep one side from owning its sibling.
function twoAddressHass(
  relation: "parent_device_id" | "via_device_id" = "parent_device_id",
): HomeAssistant {
  const stop = (entityId: string, deviceId: string, translationKey: string) => ({
    entity_id: entityId,
    device_id: deviceId,
    platform: "adjustable_bed",
    translation_key: translationKey,
  });
  return {
    entities: {
      "button.parent_stop": stop("button.parent_stop", "parent", "stop_both"),
      "button.left_stop": stop("button.left_stop", "left", "stop"),
      "button.right_stop": stop("button.right_stop", "right", "stop"),
    },
    states: {},
    devices: {
      parent: { id: "parent" },
      left: { id: "left", [relation]: "parent" },
      right: { id: "right", [relation]: "parent" },
    },
  } as unknown as HomeAssistant;
}

for (const relation of ["parent_device_id", "via_device_id"] as const) {
  test(`a side-less child Stop leaves its sibling's hold running (${relation})`, async () => {
    const hass = twoAddressHass(relation);
    const rec = recorder();
    const hold = new MotorHold(rec.actions);
    const right: MotorEntity = { key: "right-back", up: "button.right_back_up" };

    expect(holdTargetForEntity(hass, "button.right_stop")).toEqual({
      deviceId: "right",
      side: undefined,
      physicalDeviceId: "right",
      parentDeviceId: "parent",
    });
    expect(holdTargetForEntity(hass, "button.parent_stop")?.side).toBe("both");

    hold.start(right, "up", 1, "button.right_stop", holdTargetForEntity(hass, "button.right_stop"));
    await tick();
    stopFromCard(hold, hass, "button.left_stop");
    expect(hold.heldKey).toBe("right-back");

    stopFromCard(hold, hass, "button.parent_stop");
    expect(hold.heldKey).toBeNull();
    expect(rec.stoppedBeds).toEqual(["button.left_stop", "button.parent_stop"]);
    rec.release();
    await tick();
  });
}

for (const topology of ["missing-parent", "missing-graph"] as const) {
  test(`a side-less child Stop stays device-scoped with ${topology}`, async () => {
    const hass = twoAddressHass();
    hass.devices = topology === "missing-parent"
      ? {
          left: { id: "left", parent_device_id: "deleted" },
          right: { id: "right", parent_device_id: "deleted" },
        }
      : {};
    const rec = recorder();
    const hold = new MotorHold(rec.actions);
    const right: MotorEntity = { key: "right-back", up: "button.right_back_up" };

    expect(holdTargetForEntity(hass, "button.left_stop")?.deviceId).toBe("left");
    hold.start(right, "up", 1, "button.right_stop", holdTargetForEntity(hass, "button.right_stop"));
    await tick();
    stopFromCard(hold, hass, "button.left_stop");
    expect(hold.heldKey).toBe("right-back");
    hold.end(right);
    expect(rec.stoppedBeds).toEqual(["button.left_stop", "button.right_stop"]);
  });
}

test("a sided Stop translation key names its side when state attributes are missing", () => {
  const hass = {
    entities: {
      "button.stop_left": {
        entity_id: "button.stop_left",
        device_id: "bed",
        platform: "adjustable_bed",
        translation_key: "stop_left",
      },
    },
    states: {},
    devices: { bed: { id: "bed" } },
  } as unknown as HomeAssistant;
  expect(holdTargetForEntity(hass, "button.stop_left")).toEqual({
    deviceId: "bed",
    side: "left",
    physicalDeviceId: "bed",
  });
});

const bothHeld: MotorEntity = {
  key: "both-back",
  up: "button.parent_back_up",
  heldControl: { control: "back_up", startDelayMs: 0, releaseDelayMs: 100 },
};

for (const phase of ["active", "pending-release"] as const) {
  test(`a child Stop also stops the peer of a started held Both operation (${phase})`, () => {
    const hass = twoAddressHass();
    const events: string[] = [];
    const timers = new FakeTimers();
    const hold = new MotorHold(heldActions(events), timers);

    hold.start(bothHeld, "up", 1, "button.parent_stop", holdTargetForEntity(hass, "button.parent_stop"));
    if (phase === "pending-release") hold.end(bothHeld);
    stopFromCard(hold, hass, "button.left_stop");
    timers.advance(100);

    expect(hold.heldKey).toBeNull();
    expect(events).toEqual([
      "start:both-back:up",
      "stop:button.left_stop",
      "stop:button.right_stop",
    ]);
  });
}

function twoAddressCoverHass(): HomeAssistant {
  const hass = twoAddressHass();
  for (const [entityId, deviceId] of [
    ["cover.left_back", "left"],
    ["cover.right_back", "right"],
    ["cover.both_back", "parent"],
  ] as const) {
    hass.entities[entityId] = {
      entity_id: entityId,
      device_id: deviceId,
      platform: "adjustable_bed",
      translation_key: "back",
    } as HomeAssistant["entities"][string];
  }
  hass.states["cover.both_back"] = {
    entity_id: "cover.both_back",
    state: "open",
    attributes: { bed_side: "both" },
  } as unknown as HomeAssistant["states"][string];
  return hass;
}

const leftHeldCover: MotorEntity = {
  key: "back",
  cover: "cover.left_back",
  heldControls: { up: { control: "back_up", startDelayMs: 0, releaseDelayMs: 100 } },
};

for (const phase of ["active", "pending-release"] as const) {
  test(`a one-side cover stop also stops the peer of a started held Both operation (${phase})`, () => {
    const hass = twoAddressCoverHass();
    const events: string[] = [];
    const timers = new FakeTimers();
    const hold = new MotorHold(heldActions(events), timers);

    hold.start(bothHeld, "up", 1, "button.parent_stop", holdTargetForEntity(hass, "button.parent_stop"));
    if (phase === "pending-release") hold.end(bothHeld);
    // The card stops the clicked cover itself; the hold must stop the other side.
    hold.stopCover(
      leftHeldCover,
      holdTargetForEntity(hass, "cover.left_back"),
      "side",
      pairedPeerStopEntityIds(hass, "cover.left_back"),
    );
    timers.advance(100);

    expect(hold.heldKey).toBeNull();
    expect(events).toEqual(["start:both-back:up", "stop:button.right_stop"]);
  });
}

// Single-address pairs give each native child a side-suffixed Stop key.
function singleAddressCoverHass(): HomeAssistant {
  const hass = twoAddressCoverHass();
  hass.entities["button.left_stop"].translation_key = "stop_left";
  hass.entities["button.right_stop"].translation_key = "stop_right";
  for (const [entityId, side] of [
    ["button.left_stop", "left"],
    ["button.right_stop", "right"],
    ["cover.left_back", "left"],
  ] as const) {
    hass.states[entityId] = {
      entity_id: entityId,
      state: "unknown",
      attributes: { bed_side: side },
    } as unknown as HomeAssistant["states"][string];
  }
  return hass;
}

for (const phase of ["active", "pending-release"] as const) {
  test(`a single-address side cover stop also stops the suffixed peer Stop (${phase})`, () => {
    const hass = singleAddressCoverHass();
    const events: string[] = [];
    const timers = new FakeTimers();
    const hold = new MotorHold(heldActions(events), timers);

    hold.start(bothHeld, "up", 1, "button.parent_stop", holdTargetForEntity(hass, "button.parent_stop"));
    if (phase === "pending-release") hold.end(bothHeld);
    hold.stopCover(
      leftHeldCover,
      holdTargetForEntity(hass, "cover.left_back"),
      "side",
      pairedPeerStopEntityIds(hass, "cover.left_back"),
    );
    timers.advance(100);

    expect(hold.heldKey).toBeNull();
    expect(events).toEqual(["start:both-back:up", "stop:button.right_stop"]);
  });
}

test("a Both cover stop leaves the peer Stops to the combined cover", () => {
  const hass = twoAddressCoverHass();
  const events: string[] = [];
  const hold = new MotorHold(heldActions(events), new FakeTimers());

  hold.start(bothHeld, "up", 1, "button.parent_stop", holdTargetForEntity(hass, "button.parent_stop"));
  hold.stopCover(
    { ...leftHeldCover, cover: "cover.both_back" },
    holdTargetForEntity(hass, "cover.both_back"),
    "side",
    pairedPeerStopEntityIds(hass, "cover.both_back"),
  );

  expect(hold.heldKey).toBeNull();
  expect(events).toEqual(["start:both-back:up"]);
});

test("a one-side cover stop before a held Both operation starts leaves the peer alone", () => {
  const hass = twoAddressCoverHass();
  const events: string[] = [];
  const timers = new FakeTimers();
  const hold = new MotorHold(heldActions(events), timers);
  const delayed = { ...bothHeld, heldControl: { ...bothHeld.heldControl!, startDelayMs: 100 } };

  hold.start(delayed, "up", 1, "button.parent_stop", holdTargetForEntity(hass, "button.parent_stop"));
  hold.stopCover(
    leftHeldCover,
    holdTargetForEntity(hass, "cover.left_back"),
    "side",
    pairedPeerStopEntityIds(hass, "cover.left_back"),
  );
  timers.advance(200);

  expect(events).toEqual([]);
});

test("a child Stop leaves the peer alone before a held Both operation starts", () => {
  const hass = twoAddressHass();
  const events: string[] = [];
  const timers = new FakeTimers();
  const hold = new MotorHold(heldActions(events), timers);
  const delayed = { ...bothHeld, heldControl: { ...bothHeld.heldControl!, startDelayMs: 100 } };

  hold.start(delayed, "up", 1, "button.parent_stop", holdTargetForEntity(hass, "button.parent_stop"));
  stopFromCard(hold, hass, "button.left_stop");
  timers.advance(200);

  expect(events).toEqual(["stop:button.left_stop"]);
});

test("a peer owned by a newer hold keeps moving after the stale Both release is dropped", () => {
  const hass = twoAddressHass();
  const events: string[] = [];
  const timers = new FakeTimers();
  const hold = new MotorHold(heldActions(events), timers);
  const right: MotorEntity = {
    key: "right-back",
    up: "button.right_back_up",
    heldControl: { control: "back_up", startDelayMs: 0, releaseDelayMs: 100 },
  };

  hold.start(bothHeld, "up", 1, "button.parent_stop", holdTargetForEntity(hass, "button.parent_stop"));
  hold.end(bothHeld);
  hold.start(right, "up", 2, "button.right_stop", holdTargetForEntity(hass, "button.right_stop"));
  stopFromCard(hold, hass, "button.left_stop");
  timers.advance(100);

  expect(hold.heldKey).toBe("right-back");
  expect(events).toEqual([
    "start:both-back:up",
    "start:right-back:up",
    "stop:button.left_stop",
  ]);
  hold.abandon();
});

test("abandon reports the entities it stopped", () => {
  const events: string[] = [];
  const timers = new FakeTimers();
  const hold = new MotorHold(heldActions(events), timers);
  const left: MotorEntity = {
    key: "left-head",
    up: "button.left_head_up",
    heldControl: { control: "headUp", startDelayMs: 0, releaseDelayMs: 100 },
  };
  const cover: MotorEntity = {
    key: "right-back",
    cover: "cover.right_back",
    heldControls: { up: { control: "back_up", startDelayMs: 0, releaseDelayMs: 100 } },
  };

  expect(hold.abandon()).toEqual([]);
  hold.start(left, "up", 1, "button.left_stop");
  hold.end(left);
  hold.start(cover, "up", 2, "button.right_stop");
  expect(hold.abandon().sort()).toEqual(["button.left_stop", "cover.right_back"]);
  timers.advance(100);
  expect(events).toEqual([
    "start:left-head:up",
    "start:right-back:up",
    "cover-stop:cover.right_back:button.right_stop",
    "stop:button.left_stop",
  ]);
});

test("held cover metadata uses the bounded service with the cover's side", async () => {
  const calls: unknown[] = [];
  const hass = {
    states: { "cover.left_back": { attributes: { bed_side: "left" } } },
    callService: async (...args: unknown[]) => { calls.push(args); },
  } as unknown as HomeAssistant;
  const motor: MotorEntity = {
    key: "back",
    cover: "cover.left_back",
    deviceId: "left-device",
    holdEntityId: "cover.left_back",
    heldControls: { up: { control: "back_up", startDelayMs: 100, releaseDelayMs: 100 } },
  };
  await movementHold(hass, motor, "up");
  expect(calls).toEqual([[
    "adjustable_bed",
    "hold_control",
    { device_id: ["left-device"], control: "back_up", duration: 60, side: "left" },
  ]]);
});

test("combined ELEVATE without common hold metadata uses the finite parent button", async () => {
  const calls: unknown[][] = [];
  const hass = {
    entities: {
      "button.elevate_actuator_1_up": {
        entity_id: "button.elevate_actuator_1_up",
        translation_key: "elevate_actuator_1_up",
        device_id: "pair",
        platform: "adjustable_bed",
      },
      "button.elevate_actuator_1_down": {
        entity_id: "button.elevate_actuator_1_down",
        translation_key: "elevate_actuator_1_down",
        device_id: "pair",
        platform: "adjustable_bed",
      },
    },
    states: {},
    devices: {},
    callService: async (...args: unknown[]) => { calls.push(args); },
  } as HomeAssistant;
  const motor = bedEntitiesForDevice(hass, "pair").motors[0];

  expect(motor.heldControls).toBeUndefined();
  await movementPulse(hass, motor, "up");
  expect(calls).toEqual([[
    "button", "press", { entity_id: "button.elevate_actuator_1_up" },
  ]]);
});

test("M1X12 cover hold starts one bounded shared service window", async () => {
  const calls: unknown[] = [];
  const hass = {
    entities: { "cover.part_1": { entity_id: "cover.part_1", device_id: "m1x12" } },
    states: {
      "cover.part_1": {
        entity_id: "cover.part_1", state: "unknown", last_changed: "", last_updated: "",
        attributes: {
          bed_side: "left",
          held_control_up: "part_1_up",
          held_control_down: "part_1_down",
          hold_start_delay_ms: 0,
          hold_release_delay_ms: 0,
        },
      },
    },
    callService: async (...args: unknown[]) => { calls.push(args); },
  } as HomeAssistant;
  const motor: MotorEntity = {
    key: "part_1",
    cover: "cover.part_1",
    deviceId: "m1x12",
    heldControls: {
      up: { control: "part_1_up", startDelayMs: 0, releaseDelayMs: 0 },
      down: { control: "part_1_down", startDelayMs: 0, releaseDelayMs: 0 },
    },
  };

  await movementHold(hass, motor, "down");

  expect(calls).toEqual([[
    "adjustable_bed", "hold_control", {
      device_id: ["m1x12"], control: "part_1_down", duration: 60, side: "left",
    },
  ]]);
});

test("M1X12 hold release cancels the one service window and sends cover STOP", async () => {
  let resolveService!: () => void;
  const stopped: string[] = [];
  const motor: MotorEntity = {
    key: "part_1", cover: "cover.part_1", deviceId: "m1x12",
    heldControls: {
      up: { control: "part_1_up", startDelayMs: 0, releaseDelayMs: 0 },
      down: { control: "part_1_down", startDelayMs: 0, releaseDelayMs: 0 },
    },
  };
  const hold = new MotorHold({
    pulse: () => undefined,
    holdControl: () => new Promise<void>((resolve) => { resolveService = resolve; }),
    stopCover: (cover) => stopped.push(cover),
    stopBed: () => undefined,
  });

  hold.start(motor, "up", 3);
  expect(hold.heldKey).toBe("part_1");
  hold.end(motor);
  expect(stopped).toEqual(["cover.part_1"]);
  resolveService();
  await tick();
  expect(hold.heldKey).toBeNull();
});

test("held M1X12 massage button uses one bounded service and its paired-side STOP", async () => {
  const calls: unknown[] = [];
  let finish!: () => void;
  const hass = {
    entities: {
      "button.massage_wave_up": { entity_id: "button.massage_wave_up", device_id: "left-device" },
    },
    states: {
      "button.massage_wave_up": {
        entity_id: "button.massage_wave_up", state: "unknown", last_changed: "", last_updated: "",
        attributes: {
          bed_side: "left",
          held_control: "massage_wave_up",
          hold_start_delay_ms: 0,
          hold_release_delay_ms: 0,
        },
      },
    },
    callService: async (...args: unknown[]) => {
      calls.push(args);
      return new Promise<void>((resolve) => { finish = resolve; });
    },
  } as HomeAssistant;
  const motor = heldButtonMotor(hass, "button.massage_wave_up");
  expect(motor).toEqual({
    key: "button.massage_wave_up",
    up: "button.massage_wave_up",
    deviceId: "left-device",
    holdEntityId: "button.massage_wave_up",
    heldControl: { control: "massage_wave_up", startDelayMs: 0, releaseDelayMs: 0 },
  });
  if (!motor) throw new Error("Flat button hold metadata was not discovered");
  const stops: Array<string | undefined> = [];
  const hold = new MotorHold({
    pulse: () => undefined,
    holdControl: (entity, direction) => movementHold(hass, entity, direction),
    stopCover: () => undefined,
    stopBed: (stopEntityId) => stops.push(stopEntityId),
  });

  hold.start(motor, "up", 5, "button.left_stop");
  expect(calls).toEqual([[
    "adjustable_bed", "hold_control", {
      device_id: ["left-device"], control: "massage_wave_up", duration: 60, side: "left",
    },
  ]]);
  hold.end({ ...motor });
  expect(stops).toEqual(["button.left_stop"]);
  finish();
  await tick();
  expect(hold.heldKey).toBeNull();
});

test("paired M1X12 and ELEVATE motor holds use the shared service and parent STOP", async () => {
  for (const item of [
    {
      entityId: "button.part_1_up",
      translationKey: "starcode_m1x12_part_1_up",
      control: "part_1_up",
    },
    {
      entityId: "button.actuator_1_up",
      translationKey: "elevate_actuator_1_up",
      control: "actuator_1_up",
    },
  ]) {
    const calls: unknown[] = [];
    const hass = {
      entities: {
        [item.entityId]: {
          entity_id: item.entityId,
          translation_key: item.translationKey,
          device_id: "pair",
          platform: "adjustable_bed",
        },
      },
      states: {
        [item.entityId]: {
          entity_id: item.entityId,
          state: "unknown",
          last_changed: "",
          last_updated: "",
          attributes: {
            held_control: item.control,
            hold_start_delay_ms: 0,
            hold_release_delay_ms: 0,
          },
        },
      },
      devices: {},
      callService: async (...args: unknown[]) => { calls.push(args); },
    } as HomeAssistant;
    const motor = bedEntitiesForDevice(hass, "pair").motors[0];
    const stopped: Array<string | undefined> = [];
    const hold = new MotorHold({
      pulse: () => undefined,
      holdControl: (entity, direction) => movementHold(hass, entity, direction),
      stopCover: () => undefined,
      stopBed: (stopEntityId) => stopped.push(stopEntityId),
    });

    expect(motor.heldControls?.up).toEqual({
      control: item.control,
      startDelayMs: 0,
      releaseDelayMs: 0,
    });
    hold.start(motor, "up", 7, "button.pair_stop");
    expect(calls).toEqual([[
      "adjustable_bed", "hold_control", {
        device_id: ["pair"], control: item.control, duration: 60,
      },
    ]]);
    hold.end({ ...motor });
    expect(stopped).toEqual(["button.pair_stop"]);
    await tick();
  }
});
