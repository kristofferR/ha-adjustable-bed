// Unit tests for the press-and-hold state machine.
// Run with: bun test
//
// Every case here is a defect that was found in review while building this, so
// they are regression tests rather than illustrative examples.
import { expect, test } from "bun:test";
import { type Direction, type HoldActions, MotorHold, movementPulse } from "./hold";
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
      holdControl: () => undefined,
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

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

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
  expect(rec.bedStops).toBe(0); // No movement service started, so there is no cleanup owner.
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
    states: { "button.mx_memory1": { attributes: { held_control: "mx_memory1", hold_start_delay_ms: 0, hold_release_delay_ms: 300, bed_side: "right" } } },
    callService: async (domain: string, service: string, data: Record<string, unknown>) => {
      calls.push({ domain, service, data });
      if (service === "hold_control") await new Promise<void>((resolve) => { finish = resolve; });
    },
  } as unknown as HomeAssistant;
  const motor = heldButtonMotor(hass, "button.mx_memory1")!;
  expect(motor.heldControl).toEqual({ control: "mx_memory1", startDelayMs: 0, releaseDelayMs: 300 });
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
