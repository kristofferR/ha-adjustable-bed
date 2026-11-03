import assert from "node:assert/strict";
import { test } from "bun:test";
import { plugin } from "bun";

plugin({
  name: "card-hold-ownership-lit",
  setup(build) {
    build.onResolve({ filter: /^lit(?:\/decorators\.js)?$/ }, ({ path }) => ({
      path,
      namespace: "card-hold-ownership-lit",
    }));
    build.onLoad({ filter: /.*/, namespace: "card-hold-ownership-lit" }, ({ path }) => ({
      loader: "js",
      contents: path === "lit"
        ? `export class LitElement {
             requestUpdate() {}
             disconnectedCallback() {}
           }
           export const html = (strings, ...values) => ({ strings, values });
           export const css = html;
           export const nothing = Symbol("nothing");`
        : "export const property = () => () => {}; export const state = () => () => {};",
    }));
  },
});

const customElements = new Map();
globalThis.window = {
  customElements: {
    get: (name) => customElements.get(name),
    define: (name, value) => customElements.set(name, value),
    whenDefined: () => new Promise(() => {}),
  },
};
globalThis.KeyboardEvent = class {
  constructor(type, init = {}) {
    Object.assign(this, { type, key: "Enter", repeat: false }, init);
  }

  preventDefault() {}
};

const { AdjustableBedCard } = await import("./adjustable-bed-card.ts");
const { bedEntitiesForDevice } = await import("./discovery.ts");
const { heldButtonMotor, stopFromCard } = await import("./hold.ts");

class FakeClock {
  now = 0;
  nextId = 0;
  tasks = new Map();

  setTimeout = (callback, delay) => {
    const id = ++this.nextId;
    this.tasks.set(id, { at: this.now + delay, callback });
    return id;
  };

  clearTimeout = (id) => this.tasks.delete(id);

  advance(delay) {
    const end = this.now + delay;
    for (;;) {
      const next = [...this.tasks]
        .filter(([, task]) => task.at <= end)
        .sort((left, right) => left[1].at - right[1].at)[0];
      if (!next) break;
      this.tasks.delete(next[0]);
      this.now = next[1].at;
      next[1].callback();
    }
    this.now = end;
  }
}

const flushMicrotasks = async () => {
  for (let index = 0; index < 8; index++) await Promise.resolve();
};

function makeM1Fixture(mode, { combinedHold = true } = {}) {
  const root = "pair-root";
  const nativeTwoAddress = mode === "native-two-address";
  const legacyOneDevice = mode === "legacy-one-device";
  const sideAttributes = (side) => ({ bed_side: side });
  const stopAttributes = (side) => legacyOneDevice ? {} : sideAttributes(side);
  const devices = { [root]: { id: root } };
  const entities = {};
  const states = {};
  const calls = [];
  const pending = [];
  const ids = {
    bothStop: "button.parent_stop",
    leftStop: "button.left_stop",
    rightStop: "button.right_stop",
    bothUp: "button.both_part_1_up",
    leftPart1: "cover.left_part_1",
    rightPart1: "cover.right_part_1",
    leftPart2: "cover.left_part_2",
    rightPart2: "cover.right_part_2",
    rightWave: "button.right_wave_up",
  };
  const add = (entityId, deviceId, translationKey, attributes = {}) => {
    entities[entityId] = {
      entity_id: entityId,
      device_id: deviceId,
      platform: "adjustable_bed",
      translation_key: translationKey,
    };
    states[entityId] = {
      entity_id: entityId,
      state: "unknown",
      attributes,
    };
  };

  if (nativeTwoAddress) {
    devices["left-device"] = { id: "left-device", parent_device_id: root };
    devices["right-device"] = { id: "right-device", parent_device_id: root };
  }
  add(ids.bothStop, root, "stop_both", stopAttributes("both"));
  add(ids.leftStop, nativeTwoAddress ? "left-device" : root,
    nativeTwoAddress ? "stop" : "stop_left", stopAttributes("left"));
  add(ids.rightStop, nativeTwoAddress ? "right-device" : root,
    nativeTwoAddress ? "stop" : "stop_right", stopAttributes("right"));

  for (const side of ["left", "right"]) {
    const deviceId = nativeTwoAddress ? `${side}-device` : root;
    const sideSuffix = nativeTwoAddress ? "" : `_${side}`;
    for (const part of [1, 2, 4, 8, 16]) {
      const entityId = part === 1 ? ids[`${side}Part1`] :
        part === 2 ? ids[`${side}Part2`] : `cover.${side}_part_${part}`;
      add(entityId, deviceId, `starcode_m1x12_part_${part}${sideSuffix}`, {
        ...sideAttributes(side),
        held_control_up: `part_${part}_up`,
        held_control_down: `part_${part}_down`,
        hold_start_delay_ms: 100,
        hold_release_delay_ms: 0,
      });
    }
  }
  const bothButtonKey = nativeTwoAddress
    ? "starcode_m1x12_part_1_up"
    : "starcode_m1x12_part_1_up_both";
  add(ids.bothUp, root, bothButtonKey, {
    ...sideAttributes("both"),
    ...(combinedHold ? {
      held_control: "part_1_up",
      hold_start_delay_ms: 100,
      hold_release_delay_ms: 0,
    } : {}),
  });
  add(ids.rightWave, nativeTwoAddress ? "right-device" : root,
    nativeTwoAddress ? "starcode_m1x12_hold_massage_wave_up" :
      "starcode_m1x12_hold_massage_wave_up_right", {
      ...sideAttributes("right"),
      held_control: "massage_wave_up",
      hold_start_delay_ms: 100,
      hold_release_delay_ms: 0,
    });

  const clock = new FakeClock();
  const hass = {
    entities,
    states,
    devices,
    language: "en",
    locale: { language: "en" },
    callService(domain, service, data) {
      calls.push({ at: clock.now, domain, service, data });
      if (service === "hold_control" ||
          (service === "press" && data.entity_id === ids.bothUp)) {
        return new Promise((resolve) => pending.push(resolve));
      }
      return Promise.resolve();
    },
  };
  assert.ok(Object.values(entities).every((entry) => typeof entry.entity_id === "string"),
    JSON.stringify(Object.entries(entities).filter(([, entry]) => typeof entry.entity_id !== "string")));
  const sideBed = (side) => bedEntitiesForDevice(
    hass,
    nativeTwoAddress ? `${side}-device` : root,
    nativeTwoAddress ? undefined : side,
  );
  const beds = {
    both: bedEntitiesForDevice(hass, root, nativeTwoAddress ? undefined : "both"),
    left: sideBed("left"),
    right: sideBed("right"),
  };
  const card = new AdjustableBedCard();
  card.hass = hass;
  card._hold.timers = clock;

  const motorForCover = (side, entityId) => {
    const motor = sideBed(side).motors.find((item) => item.cover === entityId);
    assert.ok(motor, `Missing discovered cover ${entityId}`);
    return motor;
  };
  const motorForBoth = (key = "starcode_m1x12_part_1") => {
    const motor = beds.both.motors.find((item) => item.key === key);
    assert.ok(motor, `Missing combined motor ${key}`);
    return motor;
  };
  const startKey = (motor, stopId) => card._startHold(
    new KeyboardEvent("keydown"), motor, "up", stopId,
  );
  const endKey = (motor) => card._endKeyHold(new KeyboardEvent("keyup"), motor);
  const clickBottom = (side) => {
    const findStop = (template) => {
      if (!template || typeof template !== "object") return undefined;
      if (template.strings?.join("").includes('class="stop-all"')) {
        assert.equal(template.strings.join("").includes("disabled"), false);
        return template.values[0];
      }
      for (const value of (Array.isArray(template) ? template : template.values ?? [])) {
        const callback = findStop(value);
        if (callback) return callback;
      }
      return undefined;
    };
    const renderedBed = nativeTwoAddress
      ? bedEntitiesForDevice(hass, `${side}-device`)
      : bedEntitiesForDevice(hass, root, side);
    const callback = findStop(card._motors(renderedBed));
    assert.equal(typeof callback, "function", `Missing rendered ${side} STOP`);
    callback();
  };
  const clearDeviceStates = (deviceId) => {
    for (const entry of Object.values(entities)) {
      if (entry.device_id === deviceId) delete states[entry.entity_id];
    }
  };

  return {
    beds, calls, card, clearDeviceStates, clickBottom, clock, endKey, hass, ids,
    motorForBoth, motorForCover, pending, startKey,
  };
}

const modes = ["native-two-address", "native-single-address", "legacy-one-device"];

for (const mode of modes) {
  test(`${mode}: Left STOP preserves the Right keyboard hold and its own release target`, async () => {
    const fixture = makeM1Fixture(mode);
    if (mode === "legacy-one-device") {
      assert.equal(fixture.hass.states[fixture.ids.leftStop].attributes.bed_side, undefined);
      assert.equal(fixture.hass.entities[fixture.ids.leftStop].translation_key, "stop_left");
    }
    const right = fixture.motorForCover("right", fixture.ids.rightPart1);
    fixture.startKey(right, fixture.ids.rightStop);
    fixture.clock.advance(100);

    assert.equal(fixture.card._hold.heldKey, right.key);
    assert.equal(fixture.calls.filter((call) => call.service === "hold_control").length, 1);
    stopFromCard(fixture.card._hold, fixture.hass, fixture.ids.leftStop);
    assert.equal(fixture.card._hold.heldKey, right.key);
    fixture.endKey(right);
    fixture.clock.advance(100);
    await flushMicrotasks();

    assert.ok(fixture.calls.some((call) =>
      call.domain === "button" && call.service === "press" &&
      call.data.entity_id === fixture.ids.leftStop));
    assert.ok(fixture.calls.some((call) =>
      call.domain === "cover" && call.service === "stop_cover" &&
      call.data.entity_id === fixture.ids.rightPart1));
    fixture.pending.forEach((resolve) => resolve());
    await flushMicrotasks();
  });
}

for (const side of ["left", "right"]) {
  for (const stopKind of ["button", "cover"]) {
    test(`a ${stopKind} STOP on ${side} before a Both hold starts sends no opposite cleanup`, async () => {
      const fixture = makeM1Fixture("native-two-address");
      const both = fixture.motorForBoth();
      fixture.startKey(both, fixture.ids.bothStop);
      fixture.clock.advance(50);

      if (stopKind === "button") {
        fixture.clickBottom(side);
      } else {
        const cover = fixture.motorForCover(side, fixture.ids[`${side}Part1`]);
        fixture.card._motorStop(cover, fixture.ids[`${side}Stop`]);
      }
      fixture.clock.advance(1000);
      await flushMicrotasks();

      assert.equal(fixture.calls.some((call) => call.service === "hold_control"), false);
      const coverStops = fixture.calls.filter((call) => call.service === "stop_cover");
      assert.deepEqual(
        coverStops.map((call) => call.data.entity_id),
        stopKind === "cover" ? [fixture.ids[`${side}Part1`]] : [],
      );
      assert.ok(fixture.calls.some((call) => call.service === "press" &&
        call.data.entity_id === fixture.ids[`${side}Stop`]) || stopKind === "cover");
      assert.equal(fixture.card._hold.heldKey, null);
      fixture.pending.forEach((resolve) => resolve());
      await flushMicrotasks();
    });
  }
}

test("a same-device Both STOP still overlaps and cancels a started side hold", async () => {
  const fixture = makeM1Fixture("native-single-address");
  const right = fixture.motorForCover("right", fixture.ids.rightPart1);
  fixture.startKey(right, fixture.ids.rightStop);
  fixture.clock.advance(100);

  fixture.clickBottom("both");
  assert.equal(fixture.card._hold.heldKey, null);
  fixture.endKey(right);
  fixture.clock.advance(100);
  await flushMicrotasks();

  assert.ok(fixture.calls.some((call) => call.service === "press" &&
    call.data.entity_id === fixture.ids.bothStop));
  assert.equal(fixture.calls.some((call) => call.service === "stop_cover" &&
    call.data.entity_id === fixture.ids.rightPart1), false);
  fixture.pending.forEach((resolve) => resolve());
  await flushMicrotasks();
});

test("an explicit unsided STOP remains broad within its own device", async () => {
  const deviceId = "standalone-device";
  const hass = {
    entities: {
      "cover.raw_part": {
        entity_id: "cover.raw_part",
        device_id: deviceId,
        platform: "adjustable_bed",
        translation_key: "starcode_m1x12_part_1",
      },
      "button.stop": {
        entity_id: "button.stop",
        device_id: deviceId,
        platform: "adjustable_bed",
        translation_key: "stop",
      },
    },
    states: {
      "cover.raw_part": {
        entity_id: "cover.raw_part",
        state: "unknown",
        attributes: {
          held_control_up: "part_1_up",
          held_control_down: "part_1_down",
          hold_start_delay_ms: 100,
          hold_release_delay_ms: 0,
        },
      },
      "button.stop": {
        entity_id: "button.stop",
        state: "unknown",
        attributes: {},
      },
    },
    devices: { [deviceId]: { id: deviceId } },
    language: "en",
    locale: { language: "en" },
    callService(domain, service, data) {
      calls.push({ domain, service, data });
      return new Promise((resolve) => pending.push(resolve));
    },
  };
  const calls = [];
  const pending = [];
  const card = new AdjustableBedCard();
  card.hass = hass;
  const clock = new FakeClock();
  card._hold.timers = clock;
  const motor = bedEntitiesForDevice(hass, deviceId).motors[0];
  assert.ok(motor);

  card._startHold(new KeyboardEvent("keydown"), motor, "up", "button.stop");
  clock.advance(100);
  stopFromCard(card._hold, card.hass, "button.stop");
  assert.equal(card._hold.heldKey, null);
  card._endKeyHold(new KeyboardEvent("keyup"), motor);
  clock.advance(100);
  await flushMicrotasks();

  assert.ok(calls.some((call) => call.service === "press" &&
    call.data.entity_id === "button.stop"));
  assert.equal(calls.some((call) => call.service === "stop_cover" &&
    call.data.entity_id === "cover.raw_part"), false);
  pending.forEach((resolve) => resolve());
  await flushMicrotasks();
});

test("massage button hold keeps its Right button STOP through an unrelated Left STOP", async () => {
  const fixture = makeM1Fixture("native-two-address");
  const right = heldButtonMotor(fixture.hass, fixture.ids.rightWave);
  assert.ok(right);
  fixture.startKey(right, fixture.ids.rightStop);
  fixture.clock.advance(100);
  stopFromCard(fixture.card._hold, fixture.hass, fixture.ids.leftStop);
  fixture.card._endHold(right);
  fixture.clock.advance(100);
  await flushMicrotasks();

  assert.ok(fixture.calls.some((call) =>
    call.service === "press" && call.data.entity_id === fixture.ids.rightStop));
  assert.equal(fixture.calls.some((call) =>
    call.service === "press" && call.data.entity_id === fixture.ids.leftStop), true);
  fixture.pending.forEach((resolve) => resolve());
  await flushMicrotasks();
});

test("pointer release is owned by its pointer and keeps the Right STOP after Left STOP", async () => {
  const fixture = makeM1Fixture("native-single-address");
  const right = fixture.motorForCover("right", fixture.ids.rightPart1);
  const pointer = {
    button: 0,
    isPrimary: true,
    pointerId: 42,
    currentTarget: { setPointerCapture() {} },
    preventDefault() {},
  };
  fixture.card._startHold(pointer, right, "up", fixture.ids.rightStop);
  fixture.clock.advance(100);
  stopFromCard(fixture.card._hold, fixture.hass, fixture.ids.leftStop);
  fixture.card._endPointerHold({ type: "pointerup", pointerId: 41, button: 0 }, right);
  assert.equal(fixture.card._hold.heldKey, right.key);
  fixture.card._endPointerHold({ type: "pointerup", pointerId: 42, button: 0 }, right);
  fixture.clock.advance(100);
  await flushMicrotasks();

  assert.ok(fixture.calls.some((call) =>
    call.service === "stop_cover" && call.data.entity_id === fixture.ids.rightPart1));
  fixture.pending.forEach((resolve) => resolve());
  await flushMicrotasks();
});

test("blur and card teardown release the actual held cover target", async () => {
  const fixture = makeM1Fixture("native-two-address");
  const right = fixture.motorForCover("right", fixture.ids.rightPart1);
  fixture.startKey(right, fixture.ids.rightStop);
  fixture.clock.advance(100);
  fixture.card._endHold(right);
  fixture.clock.advance(100);
  await flushMicrotasks();
  fixture.pending.forEach((resolve) => resolve());

  const another = fixture.motorForCover("right", fixture.ids.rightPart2);
  fixture.startKey(another, fixture.ids.rightStop);
  fixture.clock.advance(100);
  fixture.card.disconnectedCallback();
  await flushMicrotasks();

  assert.deepEqual(
    fixture.calls.filter((call) => call.service === "stop_cover").map((call) => call.data.entity_id),
    [fixture.ids.rightPart1, fixture.ids.rightPart2],
  );
  fixture.pending.forEach((resolve) => resolve());
  await flushMicrotasks();
});
