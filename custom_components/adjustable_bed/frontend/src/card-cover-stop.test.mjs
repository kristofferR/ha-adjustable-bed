import assert from "node:assert/strict";
import { afterAll, test } from "bun:test";
import { plugin } from "bun";
import { placed } from "./test-placements";

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

// This file's globals must not leak into other test files sharing the process.
const previousGlobals = Object.fromEntries(
  ["window", "KeyboardEvent"].map((name) => [name, Object.getOwnPropertyDescriptor(globalThis, name)]),
);
afterAll(() => {
  for (const [name, descriptor] of Object.entries(previousGlobals)) {
    if (descriptor) Object.defineProperty(globalThis, name, descriptor);
    else Reflect.deleteProperty(globalThis, name);
  }
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
  stopPropagation() {}
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
  const hass = placed({
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
  });

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
    "stop_both",
    singleAddress ? { bed_side: "both" } : {},
  );
  add(ids.leftStop, left, "stop", { bed_side: "left" });
  add(ids.rightStop, right, "stop", { bed_side: "right" });
  add(
    ids.bothHeadUp,
    root,
    "head_up",
    singleAddress ? { bed_side: "both" } : {},
  );

  const coverAttributes = (side) => ({
    bed_side: side,
    ...(coverHoldMetadata
      ? {
          held_stop_scope: "side",
          held_control_up: "opaqueUp",
          held_control_down: "opaqueDown",
          hold_start_delay_ms: 0,
          hold_release_delay_ms: 100,
        }
      : {}),
  });
  add(ids.leftHead, left, "head", coverAttributes("left"));
  add(ids.rightHead, right, "head", coverAttributes("right"));
  add(ids.leftFeet, left, "feet", coverAttributes("left"));

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

function compactPairedFixture(singleAddress = false, { leased = true, stopButtons = true, sideAttributes = true, startDelayMs = 0 } = {}) {
  const root = "compact-pair";
  const devices = { [root]: { id: root } };
  const entities = {};
  const states = {};
  const calls = [];
  const movementFinishes = [];
  const stopFinishes = [];
  const owner = (side) => singleAddress || side === "both" ? root : `compact-${side}`;
  for (const side of ["left", "right"]) {
    if (!singleAddress) devices[owner(side)] = { id: owner(side), parent_device_id: root };
  }
  const add = (id, side, key, attributes = {}) => {
    entities[id] = { entity_id: id, device_id: owner(side), platform: "adjustable_bed", translation_key: key };
    states[id] = { entity_id: id, state: "unknown", attributes: {
      ...(sideAttributes || side === "both" ? { bed_side: side } : {}), ...attributes,
    } };
  };
  for (const side of ["both", "left", "right"]) {
    if (stopButtons) add(`button.${side}_stop`, side, side === "both" ? "stop_both" : "stop");
    add(`button.${side}_flat`, side, "preset_flat");
    add(`cover.${side}_pillow`, side, "pillow", leased
      ? { hold_lease_mode: "stream", hold_lease_motor: "pillow", ...(startDelayMs ? {
          held_control_up: "pillow_up", held_control_down: "pillow_down",
          held_stop_scope: "side",
          hold_start_delay_ms: startDelayMs, hold_release_delay_ms: 0,
        } : {}) } : {});
  }
  const hass = placed({
    entities, states, devices, language: "en", locale: { language: "en" },
    formatEntityName: (state) => state.entity_id,
    callService(domain, service, data) {
      calls.push({ domain, service, data });
      if (service === "timed_move" || service === "hold_control" || service === "open_cover") {
        return new Promise((resolve) => movementFinishes.push(resolve));
      }
      if (service === "stop_cover" || (service === "press" && data.entity_id.endsWith("_stop"))) {
        return new Promise((resolve) => stopFinishes.push(resolve));
      }
      return Promise.resolve();
    },
  });
  const card = new AdjustableBedCard();
  card.hass = hass;
  const clock = new FakeClock();
  card._hold.timers = clock;
  const config = { type: "custom:adjustable-bed-card", device_id: root, layout: "compact",
    show_motors: true, show_graphic: false, show_header: false, compact_labels: "none" };
  card.setConfig(config);
  const panes = ["both", "left", "right"].map((key) => ({
    key, label: key,
    bed: bedEntitiesForDevice(hass, owner(key), singleAddress ? key : undefined),
  }));
  function* templates(value) {
    if (Array.isArray(value)) {
      for (const child of value) yield* templates(child);
    } else if (value && typeof value === "object" && "strings" in value) {
      yield value;
      for (const child of value.values) yield* templates(child);
    }
  }
  const render = () => [...templates(card._renderCompact(root, panes, true))];
  const event = (template, name) => {
    assert.ok(template, `Missing compact template for ${name}`);
    const index = template.strings.findIndex((part) => part.endsWith(`@${name}=`));
    assert.equal(typeof template.values[index], "function", `Missing compact ${name} handler`);
    return template.values[index];
  };
  const switchSide = (side) => event(render().find((t) =>
    t.strings.join("").includes('<button class="pane-tab') && t.values.includes(side)), "click")();
  const recall = (side) => {
    switchSide(side);
    event(render().find((t) => t.strings.join("").includes('<button class="tile"') &&
      t.values.includes(`button.${side}_flat`)), "click")();
  };
  const start = (side, init = {}) => {
    switchSide(side);
    const directions = render().filter((t) => t.strings.join("").includes('<button class="cg-btn"'));
    assert.equal(directions.length, 2);
    const up = directions[1];
    event(up, "keydown")(new KeyboardEvent("keydown", init));
    return () => event(up, "keyup")(new KeyboardEvent("keyup"));
  };
  const stop = (side) => {
    switchSide(side);
    event(render().find((t) => t.strings.join("").includes('<button class="tile compact-stop"')), "click")();
  };
  return { card, calls, config, recall, start, stop, clock, movementFinishes, stopFinishes };
}

for (const singleAddress of [false, true]) {
  for (const ending of ["keyup-before-start", "abandon-before-start", "ignored-repeat", "ignored-second-press"]) {
    test(`compact ${singleAddress ? "logical" : "physical"} pair ${ending} preserves Both preset cleanup until a lease dispatches`, async () => {
      const f = compactPairedFixture(singleAddress, { startDelayMs: 100 });
      f.recall("both");
      if (ending === "ignored-second-press") f.start("right");
      const releaseKey = f.start("left", { repeat: ending === "ignored-repeat" });
      f.clock.advance(99);
      assert.equal(f.calls.filter((call) => call.service === "hold_control" || call.service === "timed_move").length, 0);
      if (ending === "keyup-before-start") releaseKey();
      f.card.setConfig({ ...f.config, device_id: "replacement" });
      f.clock.advance(100);
      assert.deepEqual(f.calls.map((call) => call.data.entity_id), ["button.both_flat", "button.both_stop"]);
      f.stopFinishes.forEach((finish) => finish());
      await flushMicrotasks();
    });
  }

  test(`compact ${singleAddress ? "logical" : "physical"} pair retires Both only at the delayed first lease dispatch`, async () => {
    const f = compactPairedFixture(singleAddress, { startDelayMs: 100 });
    f.recall("both");
    const releaseKey = f.start("left");
    f.clock.advance(99);
    assert.deepEqual([...f.card._compactStopTargets.keys()], ["button.both_stop"]);
    f.clock.advance(1);
    assert.equal(f.calls.filter((call) => call.service === "hold_control").length, 1);
    assert.deepEqual([...f.card._compactStopTargets.keys()], ["button.right_stop"]);
    releaseKey();
    f.card.setConfig({ ...f.config, device_id: "replacement" });
    f.movementFinishes.forEach((finish) => finish());
    f.stopFinishes.forEach((finish) => finish());
    await flushMicrotasks();
  });

  for (const lease of ["left", "right"]) {
    test(`compact ${singleAddress ? "logical" : "physical"} Both preset without Stop buttons retains the peer cover after expired ${lease} lease`, async () => {
      const f = compactPairedFixture(singleAddress, { stopButtons: false });
      f.recall("both");
      const releaseKey = f.start(lease);
      f.movementFinishes.shift()();
      await flushMicrotasks();
      releaseKey();
      f.card.setConfig({ ...f.config, device_id: "replacement" });
      f.card.setConfig({ ...f.config, device_id: "another-replacement" });
      assert.deepEqual(f.calls.filter((call) => call.service === "stop_cover"), [{
        domain: "cover", service: "stop_cover", data: {
          entity_id: `cover.${lease === "left" ? "right" : "left"}_pillow`,
        },
      }]);
      assert.equal(f.calls.filter((call) => call.service === "stop_all").length, 1);
      f.stopFinishes.forEach((finish) => finish());
      await flushMicrotasks();
    });
  }
}

test("compact explicit bed Stop still dispatches while automatic finite cover cleanup is pending", async () => {
  const f = compactPairedFixture(false, { leased: false });
  f.start("left")();
  assert.equal(f.stopFinishes.length, 1);
  f.stop("left");
  assert.deepEqual(f.calls.filter((call) => call.service !== "open_cover"), [
    { domain: "cover", service: "stop_cover", data: { entity_id: "cover.left_pillow" } },
    { domain: "button", service: "press", data: { entity_id: "button.left_stop" } },
  ]);
  f.card.setConfig({ ...f.config, device_id: "replacement" });
  assert.equal(f.stopFinishes.length, 2);
  f.stopFinishes.forEach((finish) => finish());
  f.movementFinishes.forEach((finish) => finish());
  await flushMicrotasks();
});

for (const [mode, singleAddress, sideAttributes] of [
  ["two-address", false, true], ["two-address registry only", false, false], ["one-address", true, true],
]) {
  for (const [preset, lease, remaining] of [
    ["both", "left", "right"], ["both", "right", "left"], ["both", "both", undefined],
    ["left", "left", undefined], ["left", "right", "left"], ["left", "both", undefined],
    ["right", "right", undefined], ["right", "left", "right"], ["right", "both", undefined],
  ]) {
    test(`compact ${mode} ${preset} preset then ${lease} expired pillow lease retains only ${remaining ?? "no"} finite cleanup`, async () => {
      const f = compactPairedFixture(singleAddress, { sideAttributes });
      f.recall(preset);
      const releaseKey = f.start(lease);
      const request = f.calls.find((call) => call.service === "timed_move");
      assert.ok(request);
      f.movementFinishes.shift()(); // The backend expires the lease before the key is released.
      await flushMicrotasks();
      releaseKey();
      f.card.setConfig({ ...f.config, device_id: "replacement" });
      f.card.setConfig({ ...f.config, device_id: "another-replacement" });
      await flushMicrotasks();
      const bareStops = f.calls.filter((call) => call.service === "press" && call.data.entity_id.endsWith("_stop"));
      assert.deepEqual(bareStops.map((call) => call.data.entity_id), remaining ? [`button.${remaining}_stop`] : []);
      assert.deepEqual(f.calls.filter((call) => call.service === "stop_all"), [{
        domain: "adjustable_bed", service: "stop_all", data: {
          device_id: request.data.device_id,
          ...(request.data.side ? { side: request.data.side } : {}),
          hold_owner: request.data.hold_owner, hold_generation: request.data.hold_generation,
        },
      }]);
      f.stopFinishes.forEach((finish) => finish());
      await flushMicrotasks();
    });
  }
}

for (const stopButtons of [false, true]) {
  for (const release of ["keyup", "setConfig"]) {
    test(`compact finite cover ${release}, stop buttons ${stopButtons}: repeated reconfiguration sends each in-flight cleanup once`, async () => {
      const f = compactPairedFixture(false, { leased: false, stopButtons });
      const releaseKey = f.start("left");
      if (release === "keyup") releaseKey();
      f.card.setConfig({ ...f.config, device_id: "replacement" });
      f.card.setConfig({ ...f.config, device_id: "another-replacement" });
      assert.deepEqual(f.calls.filter((call) => call.service !== "open_cover"), [{
        domain: "cover", service: "stop_cover", data: { entity_id: "cover.left_pillow" },
      }]);
      f.stopFinishes.shift()();
      f.movementFinishes.shift()();
      await flushMicrotasks();
      assert.equal(f.card._compactStopTargets.size, 0);
    });
  }
}

test("compact old finite Stop completion preserves a new movement's cleanup ownership", async () => {
  const f = compactPairedFixture(false, { leased: false });
  f.start("left")();
  f.start("left");
  f.stopFinishes.shift()();
  await flushMicrotasks();
  assert.equal(f.card._compactStopTargets.size, 1);
  f.card.setConfig({ ...f.config, device_id: "replacement" });
  assert.equal(f.calls.filter((call) => call.service === "stop_cover").length, 2);
  assert.equal(f.calls.filter((call) => call.service === "press").length, 0);
  f.stopFinishes.forEach((finish) => finish());
  f.movementFinishes.forEach((finish) => finish());
  await flushMicrotasks();
  assert.equal(f.card._compactStopTargets.size, 0);
});

for (const ending of ["active-config", "expired-config", "keyup-config", "expired-keyup-config"]) {
  test(`compact leased pillow ${ending} never retains an unscoped automatic Stop`, async () => {
    const calls = [];
    let finish;
    const cover = "cover.pillow";
    const hass = placed({
      entities: { [cover]: { entity_id: cover, device_id: "bed", platform: "adjustable_bed", translation_key: "pillow" } },
      states: { [cover]: { entity_id: cover, state: "unknown", attributes: {
        hold_lease_mode: "stream", hold_lease_motor: "pillow",
      } } },
      devices: { bed: { id: "bed" } }, language: "en", locale: { language: "en" },
      callService(domain, service, data) {
        calls.push({ domain, service, data });
        return service === "timed_move" ? new Promise((resolve) => { finish = resolve; }) : Promise.resolve();
      },
    });
    const card = new AdjustableBedCard();
    card.hass = hass;
    card._hold.timers = new FakeClock();
    card.setConfig({ type: "custom:adjustable-bed-card", device_id: "bed", layout: "compact" });
    const motor = bedEntitiesForDevice(hass, "bed").motors.find((m) => m.cover === cover);
    assert.ok(motor?.holdLease);
    card._startHold(new KeyboardEvent("keydown"), motor, "up");
    assert.equal(calls[0]?.service, "timed_move");
    if (ending.includes("expired")) {
      finish();
      await flushMicrotasks();
    }
    if (ending.includes("keyup")) card._endKeyHold(new KeyboardEvent("keyup"), motor);
    card.setConfig({ type: "custom:adjustable-bed-card", device_id: "replacement", layout: "compact" });
    await flushMicrotasks();
    assert.equal(card._compactStopTargets.size, 0);
    assert.equal(calls.length, 2);
    assert.deepEqual(calls[1], { domain: "adjustable_bed", service: "stop_all", data: {
      device_id: "bed", hold_owner: calls[0].data.hold_owner, hold_generation: calls[0].data.hold_generation,
      ...(!ending.includes("keyup") ? { hold_cancelled: true } : {}),
    } });
    // Explicit Stop still goes to the receiver through the public cover action.
    card._motorStop(motor);
    assert.deepEqual(calls.at(-1), { domain: "cover", service: "stop_cover", data: { entity_id: cover } });
    finish();
    await flushMicrotasks();
  });
}

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

// Checked against real Python entity builders by the Smart Sleep controller tests.
const smartSleepRoutes = (await import("../../../../tests/fixtures/smart_sleep_button_holds.json")).default;

function smartSleepCard(format, key) {
  const entityId = `button.${key}`;
  const stopId = "button.smart_sleep_stop";
  const calls = [];
  let finishHold;
  const hass = placed({
    entities: {
      [entityId]: { entity_id: entityId, device_id: "bed", platform: "adjustable_bed", translation_key: key },
      [stopId]: { entity_id: stopId, device_id: "bed", platform: "adjustable_bed", translation_key: "stop" },
    },
    states: {
      [entityId]: { entity_id: entityId, state: "unknown", attributes: smartSleepRoutes[format][key] },
      [stopId]: { entity_id: stopId, state: "unknown", attributes: {} },
    },
    devices: { bed: { id: "bed" } },
    formatEntityName: () => key,
    callService(domain, service, data) {
      calls.push({ domain, service, data });
      return service === "hold_control"
        ? new Promise((resolve) => { finishHold = resolve; })
        : Promise.resolve();
    },
  });
  const card = new AdjustableBedCard();
  card.hass = hass;
  card._hold.timers = new FakeClock();
  const tile = card._actionTile(entityId, stopId);
  const handler = (name) => tile.values[tile.strings.findIndex((part) => part.endsWith(`${name}=`))];
  return { calls, handler, tile, entityId, stopId, finish: () => finishHold?.() };
}

for (const key of Object.keys(smartSleepRoutes.p2)) {
  test(`Smart Sleep P2 ${key}: the real tile recalls on click without a held-service window`, async () => {
    const fixture = smartSleepCard("p2", key);
    assert.equal(fixture.handler("@pointerdown"), undefined);
    assert.equal(fixture.handler("@pointerup"), undefined);
    fixture.handler("@click")();
    await flushMicrotasks();
    assert.deepEqual(fixture.calls, [{ domain: "button", service: "press", data: { entity_id: fixture.entityId } }]);
  });
}

for (const key of Object.keys(smartSleepRoutes.p1)) {
  test(`Smart Sleep P1 ${key}: the real memory tile leases refresh and releases through STOP`, async () => {
    const fixture = smartSleepCard("p1", key);
    fixture.handler("@keydown")(new KeyboardEvent("keydown"));
    await flushMicrotasks();
    assert.equal(fixture.calls[0]?.service, "hold_control");
    assert.equal(fixture.calls[0].data.control, smartSleepRoutes.p1[key].held_control);
    assert.equal(fixture.calls[0].data.duration, 0.75);
    assert.equal(typeof fixture.calls[0].data.hold_owner, "string");
    fixture.handler("@keyup")(new KeyboardEvent("keyup"));
    await flushMicrotasks();
    assert.deepEqual(fixture.calls[1], { domain: "adjustable_bed", service: "stop_all", data: {
      device_id: fixture.calls[0].data.device_id[0],
      ...(fixture.calls[0].data.side ? { side: fixture.calls[0].data.side } : {}),
      hold_owner: fixture.calls[0].data.hold_owner, hold_generation: fixture.calls[0].data.hold_generation,
    } });
    fixture.finish();
    await flushMicrotasks();
  });
}

test("combined light of unconfirmed switches offers On and Off instead of a toggle", () => {
  const calls = [];
  const card = new AdjustableBedCard();
  card.hass = {
    states: {
      "switch.left_light": { entity_id: "switch.left_light", state: "unknown", attributes: { assumed_state: true } },
      "switch.right_light": { entity_id: "switch.right_light", state: "on", attributes: {} },
    },
    entities: {}, devices: {}, locale: { language: "en" }, language: "en",
    callService(domain, service, data) { calls.push({ domain, service, data }); return Promise.resolve(); },
  };
  const pane = (id) => ({ bed: { lights: { switch: id } } });
  const parent = { lights: {} };
  const template = card._combinedLighting(parent, [pane("switch.left_light"), pane("switch.right_light")]);
  assert.ok(template.strings.join("").includes('role="group"'), "expected an On/Off group");
  assert.ok(!template.strings.join("").includes('role="switch"'), "no toggle for unsure lights");
  const handlers = template.values.filter((value) => typeof value === "function");
  handlers.at(-2)();
  handlers.at(-1)();
  const both = { entity_id: ["switch.left_light", "switch.right_light"] };
  assert.deepEqual(calls, [
    { domain: "homeassistant", service: "turn_off", data: both },
    { domain: "homeassistant", service: "turn_on", data: both },
  ]);
});
