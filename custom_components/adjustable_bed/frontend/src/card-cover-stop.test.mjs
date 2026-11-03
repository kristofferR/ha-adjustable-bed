import assert from "node:assert/strict";
import { test } from "bun:test";
import { plugin } from "bun";

plugin({
  name: "card-cover-stop-test-lit",
  setup(build) {
    build.onResolve({ filter: /^lit(?:\/decorators\.js)?$/ }, ({ path }) => ({
      path,
      namespace: "card-cover-stop-test-lit",
    }));
    build.onLoad({ filter: /.*/, namespace: "card-cover-stop-test-lit" }, ({ path }) => ({
      loader: "js",
      contents: path === "lit"
        ? `export class LitElement { requestUpdate() {} }
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

function makeFixture(mode, { coverHoldMetadata = true } = {}) {
  const root = "device-root";
  const separateAddresses = mode === "native-two-address";
  const left = separateAddresses ? "opaque-left-device" : root;
  const right = separateAddresses ? "opaque-right-device" : root;
  const ids = {
    bothStop: "button.parent-stop",
    leftStop: "button.left-stop",
    rightStop: "button.right-stop",
    bothHeadUp: "button.both-head-up",
    leftHead: "cover.left-head",
    rightHead: "cover.right-head",
    leftFeet: "cover.left-feet",
  };
  const calls = [];
  const pending = [];
  const clock = new FakeClock();
  const hass = {
    entities: {},
    states: {},
    devices: { [root]: { id: root } },
    language: "en",
    locale: { language: "en" },
    callService(domain, service, data) {
      calls.push({ domain, service, data });
      if (
        (service === "press" && data.entity_id === ids.bothHeadUp) ||
        service === "hold_control" ||
        service === "open_cover"
      ) {
        return new Promise((resolve) => pending.push(resolve));
      }
      return Promise.resolve();
    },
  };

  if (separateAddresses) {
    hass.devices[left] = { id: left, parent_device_id: root };
    hass.devices[right] = { id: right, parent_device_id: root };
  }

  const add = (entityId, deviceId, key, attributes = {}) => {
    hass.entities[entityId] = {
      entity_id: entityId,
      device_id: deviceId,
      platform: "adjustable_bed",
      translation_key: key,
    };
    hass.states[entityId] = {
      entity_id: entityId,
      state: "unknown",
      attributes,
    };
  };

  const singleAddress = mode !== "native-two-address";
  add(
    ids.bothStop,
    root,
    singleAddress ? "stop_both" : "stop_both",
    singleAddress ? { bed_side: "both" } : {},
  );
  add(ids.leftStop, left, singleAddress ? "stop_left" : "stop", { bed_side: "left" });
  add(ids.rightStop, right, singleAddress ? "stop_right" : "stop", { bed_side: "right" });
  add(
    ids.bothHeadUp,
    root,
    singleAddress ? "head_up_both" : "head_up",
    singleAddress ? { bed_side: "both" } : {},
  );

  const coverAttributes = (side) => ({
    bed_side: side,
    ...(coverHoldMetadata
      ? {
          held_control_up: "opaqueUp",
          held_control_down: "opaqueDown",
          hold_start_delay_ms: 0,
          hold_release_delay_ms: 100,
        }
      : {}),
  });
  add(ids.leftHead, left, singleAddress ? "head_left" : "head", coverAttributes("left"));
  add(ids.rightHead, right, singleAddress ? "head_right" : "head", coverAttributes("right"));
  add(ids.leftFeet, left, singleAddress ? "feet_left" : "feet", coverAttributes("left"));

  const side = (deviceId, name) => bedEntitiesForDevice(
    hass,
    deviceId,
    singleAddress ? name : undefined,
  );
  const beds = {
    both: side(root, "both"),
    left: side(left, "left"),
    right: side(right, "right"),
  };
  const card = new AdjustableBedCard();
  card.hass = hass;
  card._hold.timers = clock;

  const motorForCover = (section, coverId) => {
    const motor = beds[section].motors.find((item) => item.cover === coverId);
    assert.ok(motor, `Missing discovered motor for ${coverId}`);
    return motor;
  };
  const bothHead = beds.both.motors.find((item) => item.up === ids.bothHeadUp);
  assert.ok(
    bothHead,
    `Missing discovered combined head button in ${mode}: ${JSON.stringify(beds.both.motors)}`,
  );

  const start = (motor, stopEntityId) => {
    card._startHold(new KeyboardEvent("keydown"), motor, "up", stopEntityId);
  };
  const end = (motor) => card._endKeyHold(new KeyboardEvent("keyup"), motor);
  const stopCoverRow = (section, coverId) => {
    const motor = motorForCover(section, coverId);
    card._motorStop(motor, beds[section].stop);
    return motor;
  };

  return {
    beds,
    calls,
    card,
    clock,
    end,
    bothHead,
    ids,
    motorForCover,
    pending,
    start,
    stopCoverRow,
  };
}

const modes = ["native-two-address", "native-single-address", "legacy-one-device"];

for (const mode of modes) {
  test(`${mode}: Left cover Stop preserves Right head release ownership`, async () => {
    const fixture = makeFixture(mode);
    const rightHead = fixture.motorForCover("right", fixture.ids.rightHead);
    fixture.start(rightHead, fixture.beds.right.stop);
    await flushMicrotasks();

    fixture.stopCoverRow("left", fixture.ids.leftHead);
    fixture.end(rightHead);
    fixture.clock.advance(100);

    assert.deepEqual(
      fixture.calls.filter((call) => call.service === "stop_cover").map((call) => call.data.entity_id),
      [fixture.ids.leftHead, fixture.ids.rightHead],
    );
    fixture.pending.forEach((resolve) => resolve());
    await flushMicrotasks();
  });

  test(`${mode}: Sleepy's different-axis cover Stop blocks repeat and retains Both release`, async () => {
    const fixture = makeFixture(mode);
    fixture.start(fixture.bothHead, fixture.beds.both.stop);
    await flushMicrotasks();
    assert.equal(
      fixture.calls.filter((call) => call.data.entity_id === fixture.ids.bothHeadUp).length,
      1,
    );

    fixture.stopCoverRow("left", fixture.ids.leftFeet);
    fixture.pending.shift()();
    await flushMicrotasks();

    assert.deepEqual(
      fixture.calls.filter((call) => call.service === "stop_cover").map((call) => call.data.entity_id),
      [fixture.ids.leftFeet],
    );
    assert.equal(
      fixture.calls.filter((call) => call.data.entity_id === fixture.ids.bothHeadUp).length,
      1,
    );
    assert.equal(fixture.card._hold.heldKey, fixture.bothHead.key);
    fixture.end(fixture.bothHead);
    assert.deepEqual(
      fixture.calls.filter((call) => call.data.entity_id === fixture.ids.bothStop)
        .map((call) => call.data.entity_id),
      [fixture.ids.bothStop],
    );
    fixture.pending.forEach((resolve) => resolve());
    await flushMicrotasks();
  });

  test(`${mode}: side cover Stop drops stale Both release but preserves newer opposite release`, async () => {
    const fixture = makeFixture(mode);
    Object.assign(fixture.card.hass.states[fixture.ids.bothHeadUp].attributes, {
      held_control: "opaqueBoth",
      hold_start_delay_ms: 0,
      hold_release_delay_ms: 100,
    });
    const bothHead = bedEntitiesForDevice(
      fixture.card.hass,
      "device-root",
      mode === "native-two-address" ? undefined : "both",
    ).motors.find((item) => item.up === fixture.ids.bothHeadUp);
    assert.ok(bothHead);

    fixture.start(bothHead, fixture.beds.both.stop);
    await flushMicrotasks();
    fixture.end(bothHead);
    const rightHead = fixture.motorForCover("right", fixture.ids.rightHead);
    fixture.start(rightHead, fixture.beds.right.stop);
    await flushMicrotasks();

    fixture.stopCoverRow("left", fixture.ids.leftFeet);
    fixture.clock.advance(100);
    assert.equal(
      fixture.calls.filter((call) => call.data.entity_id === fixture.ids.bothStop).length,
      0,
    );
    fixture.end(rightHead);
    fixture.clock.advance(100);

    assert.deepEqual(
      fixture.calls.filter((call) => call.service === "stop_cover").map((call) => call.data.entity_id),
      [fixture.ids.leftFeet, fixture.ids.rightHead],
    );
    fixture.pending.forEach((resolve) => resolve());
    await flushMicrotasks();
  });

  test(`${mode}: idle cover Stop sends only the selected cover target`, () => {
    const fixture = makeFixture(mode);
    fixture.stopCoverRow("left", fixture.ids.leftHead);
    assert.deepEqual(fixture.calls, [
      {
        domain: "cover",
        service: "stop_cover",
        data: { entity_id: fixture.ids.leftHead },
      },
    ]);
  });
}

test("motor-specific cover Stop leaves a different-axis Both hold running", async () => {
  const fixture = makeFixture("native-two-address", { coverHoldMetadata: false });
  fixture.start(fixture.bothHead, fixture.beds.both.stop);
  await flushMicrotasks();
  fixture.stopCoverRow("left", fixture.ids.leftFeet);
  fixture.pending.shift()();
  await flushMicrotasks();

  assert.equal(
    fixture.calls.filter((call) => call.data.entity_id === fixture.ids.bothHeadUp).length,
    2,
  );
  assert.equal(fixture.card._hold.heldKey, fixture.bothHead.key);
  fixture.card._hold.abandon();
  fixture.pending.forEach((resolve) => resolve());
  await flushMicrotasks();
});
