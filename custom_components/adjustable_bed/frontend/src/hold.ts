// Press-and-hold state machine for the motor controls.
//
// Kept free of DOM and Home Assistant dependencies so it can be unit tested:
// the card owns the event wiring and the service calls, this owns the rules
// about who holds what and when a hold ends. Nearly every defect found while
// building press-and-hold lived in these rules rather than in the wiring.
import type { HomeAssistant, MotorEntity } from "./types";

export type Direction = "up" | "down";

export function heldButtonMotor(
  hass: HomeAssistant | undefined,
  entityId: string,
): MotorEntity | undefined {
  const deviceId = hass?.entities[entityId]?.device_id;
  const attributes = hass?.states[entityId]?.attributes;
  const control = attributes?.held_control;
  const startDelayMs = attributes?.hold_start_delay_ms;
  const releaseDelayMs = attributes?.hold_release_delay_ms;
  if (
    !deviceId || typeof control !== "string" ||
    typeof startDelayMs !== "number" || !Number.isFinite(startDelayMs) ||
    startDelayMs < 0 || typeof releaseDelayMs !== "number" ||
    !Number.isFinite(releaseDelayMs) || releaseDelayMs < 0
  ) return undefined;
  return {
    key: entityId,
    up: entityId,
    deviceId,
    holdEntityId: entityId,
    heldControl: { control, startDelayMs, releaseDelayMs },
  };
}

export function movementPulse(
  hass: HomeAssistant | undefined,
  motor: MotorEntity,
  direction: Direction,
): Promise<unknown> | undefined {
  if (motor.timedMove) {
    // A shared movement window preserves each receiver's cadence without
    // making the faster side wait out its partner's configured finite pulse.
    return hass?.callService("adjustable_bed", "timed_move", {
      device_id: motor.timedMove.deviceId,
      ...(motor.timedMove.side ? { side: motor.timedMove.side } : {}),
      motor: motor.timedMove.motor,
      direction,
      duration_ms: 1000,
    });
  }
  if (motor.cover) {
    return hass?.callService("cover", direction === "up" ? "open_cover" : "close_cover", {
      entity_id: motor.cover,
    });
  }
  const entityId = direction === "up" ? motor.up : motor.down;
  return entityId ? hass?.callService("button", "press", { entity_id: entityId }) : undefined;
}

// Controller-declared refresh holds use the shared bounded service. The
// release entity remains the owner of STOP and side routing.
export function movementHold(
  hass: HomeAssistant | undefined,
  motor: MotorEntity,
  direction: Direction,
): Promise<unknown> | undefined {
  const spec = motor.heldControls?.[direction] ?? motor.heldControl;
  if (!spec || !motor.deviceId) return undefined;
  const side = hass?.states[motor.holdEntityId ?? motor.cover ?? ""]?.attributes.bed_side;
  const serviceData: Record<string, unknown> = {
    device_id: [motor.deviceId],
    control: spec.control,
    duration: 60,
  };
  if (side === "left" || side === "right" || side === "both") {
    serviceData.side = side;
  }
  return hass?.callService("adjustable_bed", "hold_control", serviceData);
}

export function activateWithoutPointer(
  hass: HomeAssistant | undefined,
  motor: MotorEntity,
  direction: Direction,
): void {
  // Assistive activation has no pointer/key lifetime, so issue one finite
  // pulse through the same controller-declared bounded service route.
  void movementPulse(hass, motor, direction)?.catch(() => undefined);
}

interface EventListenerTarget {
  addEventListener(type: string, listener: EventListener): void;
  removeEventListener(type: string, listener: EventListener): void;
}

export function registerHoldFocusLoss(
  windowTarget: EventListenerTarget,
  documentTarget: EventListenerTarget,
  isDocumentHidden: () => boolean,
  release: () => void,
): () => void {
  const onWindowBlur: EventListener = () => release();
  const onVisibilityChange: EventListener = () => {
    if (isDocumentHidden()) release();
  };
  windowTarget.addEventListener("blur", onWindowBlur);
  documentTarget.addEventListener("visibilitychange", onVisibilityChange);
  let registered = true;
  return () => {
    if (!registered) return;
    registered = false;
    windowTarget.removeEventListener("blur", onWindowBlur);
    documentTarget.removeEventListener("visibilitychange", onVisibilityChange);
  };
}

export interface HoldActions {
  // Runs one finite movement pulse and resolves when the bed has finished it.
  // Resolving is what paces the repeat loop; rejecting stops it.
  pulse: (motor: MotorEntity, dir: Direction) => Promise<unknown> | undefined;
  holdControl?: (motor: MotorEntity, dir: Direction) => Promise<unknown> | undefined;
  // Stops a cover-backed motor, which is the only kind with its own stop. The
  // bed stop identifies the compact target retained when the hold began.
  stopCover: (coverEntityId: string, stopEntityId?: string) => void;
  // The stop that covers the held motor. Cancels the command in flight.
  // `stopEntityId` is the stop belonging to the bed the motor is on, which on a
  // paired bed is the side's own stop rather than the parent's; omitted falls
  // back to the single bed's stop.
  stopBed: (stopEntityId?: string) => void;
}

export interface HoldTimers {
  setTimeout: (callback: () => void, delayMs: number) => ReturnType<typeof setTimeout>;
  clearTimeout: (timer: ReturnType<typeof setTimeout>) => void;
}

export interface HoldLifecycleTarget {
  addEventListener(
    type: "visibilitychange" | "pagehide",
    listener: () => void,
  ): void;
  removeEventListener(
    type: "visibilitychange" | "pagehide",
    listener: () => void,
  ): void;
}

interface PendingRelease {
  id: number;
  motorKey: string;
  targetKey: string;
  target?: HoldTarget;
  cover?: string;
  stopEntityId?: string;
  timer?: ReturnType<typeof setTimeout>;
  scopeGenerations: ReadonlyMap<string, number>;
}

export type HoldTargetSide = "left" | "right" | "both";

export interface HoldTarget {
  deviceId: string;
  side?: HoldTargetSide;
  // The registry device that owns the entity, and its paired parent. A
  // two-address child publishes no logical side, so its physical device is
  // what keeps it distinct from its sibling.
  physicalDeviceId?: string;
  parentDeviceId?: string;
  // Capture the graph while it exists so a newer child claim can fence an old
  // Both release even after Home Assistant drops the parent metadata.
  physicalChildIds?: readonly string[];
}

export type CoverStopScope = "motor" | "side";

function deviceParentId(
  deviceId: string,
  devices: HomeAssistant["devices"],
): string | undefined {
  const parentId = devices[deviceId]?.parent_device_id ?? devices[deviceId]?.via_device_id;
  return parentId && devices[parentId] ? parentId : undefined;
}

function deviceHasChildren(deviceId: string, devices: HomeAssistant["devices"]): boolean {
  return Object.values(devices).some(
    (candidate) => (candidate.parent_device_id ?? candidate.via_device_id) === deviceId,
  );
}

const STOP_TRANSLATION_SIDES: Record<string, HoldTargetSide> = {
  stop_left: "left",
  stop_right: "right",
  stop_both: "both",
};

// State attributes can be missing while HA restores an entity; the registry's
// sided Stop translation key still names its side. Conflicting sources are
// ambiguous and claim no side.
function sideForEntity(hass: HomeAssistant, entityId: string): HoldTargetSide | undefined {
  const attributes = hass.states[entityId]?.attributes;
  const declared = attributes?.bed_side ?? attributes?.side;
  const stateSide = declared === "left" || declared === "right" || declared === "both"
    ? declared
    : undefined;
  const translationKey = hass.entities[entityId]?.translation_key;
  const registrySide = translationKey ? STOP_TRANSLATION_SIDES[translationKey] : undefined;
  if (stateSide && registrySide && stateSide !== registrySide) return undefined;
  return stateSide ?? registrySide;
}

function isStopEntity(hass: HomeAssistant, entityId: string): boolean {
  const entry = hass.entities[entityId];
  return entry?.platform === "adjustable_bed" &&
    entityId.startsWith("button.") &&
    (entry.translation_key === "stop" ||
      (entry.translation_key !== undefined && entry.translation_key in STOP_TRANSLATION_SIDES));
}

export function holdTargetForEntity(
  hass: HomeAssistant | undefined,
  entityId?: string,
): HoldTarget | undefined {
  if (!hass || !entityId) return undefined;
  const deviceId = hass.entities[entityId]?.device_id;
  if (!deviceId) return undefined;

  const devices = hass.devices ?? {};
  const parentId = deviceParentId(deviceId, devices);
  const side = sideForEntity(hass, entityId) ??
    (!parentId && deviceHasChildren(deviceId, devices) ? "both" : undefined);

  return {
    // A side-less child is not proof that its Stop owns the parent and the
    // sibling, so it keeps its own device until HA publishes a logical side.
    deviceId: parentId && side ? parentId : deviceId,
    side,
    physicalDeviceId: deviceId,
    ...(parentId ? { parentDeviceId: parentId } : {}),
    ...(side === "both" ? {
      physicalChildIds: Object.entries(devices)
        .filter(([, device]) => (device.parent_device_id ?? device.via_device_id) === deviceId)
        .map(([id]) => id),
    } : {}),
  };
}

function holdTargetsOverlap(first: HoldTarget, second: HoldTarget): boolean {
  if ((first.parentDeviceId ?? first.deviceId) !== (second.parentDeviceId ?? second.deviceId)) {
    return false;
  }
  if (first.side === "both" || second.side === "both") return true;
  if (first.side && second.side) return first.side === second.side;
  // A child without a logical side stays distinct from its sibling.
  return !first.physicalDeviceId || !second.physicalDeviceId ||
    first.physicalDeviceId === second.physicalDeviceId;
}

// A side Stop halts only its own receiver. A started held Both operation also
// needs the other side's Stop, or that side keeps moving until the host bound.
export function pairedPeerStopEntityIds(
  hass: HomeAssistant | undefined,
  stopEntityId: string | undefined,
): string[] {
  if (!hass || !stopEntityId) return [];
  const deviceId = hass.entities[stopEntityId]?.device_id;
  if (!deviceId) return [];
  const side = sideForEntity(hass, stopEntityId);
  if (side === "left" || side === "right") {
    // One-address pairs keep both side Stops on one device.
    const peerSide = side === "left" ? "right" : "left";
    const sameDevice = Object.values(hass.entities).filter(
      (entry) =>
        entry.entity_id !== stopEntityId &&
        entry.device_id === deviceId &&
        isStopEntity(hass, entry.entity_id) &&
        sideForEntity(hass, entry.entity_id) === peerSide,
    );
    if (sameDevice.length === 1) return [sameDevice[0].entity_id];
  }
  const devices = hass.devices ?? {};
  const parentId = deviceParentId(deviceId, devices);
  if (!parentId) return [];
  const childIds = Object.entries(devices)
    .filter(([, device]) => (device.parent_device_id ?? device.via_device_id) === parentId)
    .map(([id]) => id);
  // An incomplete pair graph cannot prove which Stop owns the other side.
  if (childIds.length !== 2 || !childIds.includes(deviceId)) return [];
  const peerId = childIds.find((id) => id !== deviceId);
  // Two-address children publish a plain "stop"; single-address children
  // carry a side-suffixed key. Either way the peer's Stop must not claim Both
  // or this Stop's own side.
  const stops = Object.values(hass.entities).filter((entry) => {
    if (entry.device_id !== peerId || !isStopEntity(hass, entry.entity_id)) return false;
    const peerSide = sideForEntity(hass, entry.entity_id);
    return peerSide !== "both" && (peerSide === undefined || peerSide !== side);
  });
  return stops.length === 1 ? [stops[0].entity_id] : [];
}

// This is the callback used by both Stop buttons rendered by the card. Keep
// target resolution here so the state-machine tests exercise the same path as
// the DOM handlers without needing a browser runtime.
export function stopFromCard(
  hold: MotorHold,
  hass: HomeAssistant | undefined,
  stopEntityId?: string,
): void {
  const target = holdTargetForEntity(hass, stopEntityId);
  const coversAllTargets = target?.side !== "left" && target?.side !== "right";
  hold.stopAll(
    stopEntityId,
    coversAllTargets,
    target,
    pairedPeerStopEntityIds(hass, stopEntityId),
  );
}

// Ownership is tracked by the motor's key and the entity it drives rather than
// object identity: the first pulse completing updates that entity, which
// re-renders the card and rebuilds every MotorEntity, so a release handler
// would otherwise hold a different object for the same motor and never stop
// the loop. The key alone is not enough: a paired bed renders one section per
// side, each with its own "back" motor, and a blur on one side's button must
// not end the other side's hold. Stops still match by key: a motor-scoped
// cover stop deliberately reaches the same motor across the Both and side
// sections, and target overlap keeps the two sides apart there.
function motorIdentity(motor: MotorEntity): string {
  const entity = motor.holdEntityId ?? motor.cover ?? motor.up ?? motor.down ?? "";
  return `${motor.key}\u0000${entity}`;
}

export class MotorHold {
  private _key: string | null = null;
  private _motor: MotorEntity | null = null;
  private _scopeStops: string[] = [];
  private _remainingStops: string[] = [];
  private readonly _stopTargetGenerations = new Map<string, number>();
  private _keyboardKey: string | null = null;
  private _pulseInFlight: Promise<unknown> | undefined;
  private _motorId: string | null = null;
  private _cover: string | null = null;
  // The stop entity that covers the held motor. Tracked per hold because a
  // paired bed renders one section per side, each with its own stop, so there
  // is no single bed-wide stop to fall back on.
  private _stop: string | null = null;
  private _target?: HoldTarget;
  // The pointer that owns the hold. Pointer-end events from any other pointer
  // must be ignored: a second touch on the same control would otherwise cancel
  // the primary hold and stop the motor early.
  private _pointerId: number | null = null;
  // Bumping this is what stops an in-flight repeat loop: the loop's next
  // iteration sees a stale value and exits.
  private _generation = 0;
  private _repeatBlocked = false;
  private _startTimer?: ReturnType<typeof setTimeout>;
  private _started = false;
  private _heldControl?: MotorEntity["heldControl"];
  private _releaseId = 0;
  private readonly _pendingReleases = new Map<number, PendingRelease>();

  constructor(
    private readonly actions: HoldActions,
    private readonly timers: HoldTimers = {
      setTimeout: (callback, delayMs) => globalThis.setTimeout(callback, delayMs),
      clearTimeout: (timer) => globalThis.clearTimeout(timer),
    },
  ) {}

  get heldKey(): string | null {
    return this._key;
  }

  // Begin a hold. `pointerId` is null for keyboard activation, which has no
  // owning pointer. `stopEntityId` is the stop for the bed this motor belongs
  // to. Ignored when another motor already holds.
  start(
    motor: MotorEntity,
    dir: Direction,
    pointerId: number | null,
    stopEntityId?: string,
    scopeOrTarget: readonly string[] | HoldTarget = stopEntityId ? [stopEntityId] : [],
    remainingStopEntityIds: readonly string[] = [],
    keyboardKey: string | null = null,
    target?: HoldTarget,
  ): void {
    if (this._key !== null) return;
    const scope = Array.isArray(scopeOrTarget) ? scopeOrTarget as readonly string[] : [];
    this._target = Array.isArray(scopeOrTarget) ? target : scopeOrTarget as HoldTarget;
    this._flushPendingForTarget(stopEntityId ?? motor.cover ?? motor.key);
    this._key = motor.key;
    this._motor = Object.freeze({
      ...motor,
      ...(motor.timedMove ? { timedMove: Object.freeze({ ...motor.timedMove }) } : {}),
    });
    this._motorId = motorIdentity(motor);
    this._cover = motor.cover ?? null;
    this._stop = stopEntityId ?? null;
    this._scopeStops = [...new Set([
      ...scope,
      ...(stopEntityId ? [stopEntityId] : []),
      ...(motor.cover ? [motor.cover] : []),
      ...this._targetScope(this._target),
    ])];
    this._remainingStops = [...new Set(remainingStopEntityIds)];
    this.claimStopScope(this._scopeStops);
    this._pointerId = pointerId;
    this._keyboardKey = keyboardKey;
    const generation = ++this._generation;
    this._heldControl = motor.heldControls?.[dir] ?? motor.heldControl;
    if (this._heldControl) {
      const delay = this._heldControl.startDelayMs;
      if (delay <= 0) this._startHeldControl(this._motor, dir, generation);
      else this._startTimer = this.timers.setTimeout(
        () => this._startHeldControl(this._motor ?? motor, dir, generation), delay,
      );
      return;
    }
    this._started = true;
    void this._repeat(this._motor, dir, generation);
  }

  private _targetScope(target: HoldTarget | undefined): string[] {
    if (!target) return [];
    const sides = target.side === "left" || target.side === "right"
      ? [target.side] : ["left", "right"];
    const devices = new Set([
      target.deviceId,
      ...(target.physicalDeviceId ? [target.physicalDeviceId] : []),
      ...(target.physicalChildIds ?? []),
    ]);
    return [...devices].flatMap((device) => sides.map((side) => `target:${device}:${side}`));
  }

  claimStopScope(scopeStopEntityIds: readonly string[], target?: HoldTarget): void {
    for (const key of new Set([...scopeStopEntityIds, ...this._targetScope(target)])) {
      this._stopTargetGenerations.set(key, (this._stopTargetGenerations.get(key) ?? 0) + 1);
    }
  }

  private _startHeldControl(
    motor: MotorEntity,
    dir: Direction,
    generation: number,
  ): void {
    this._startTimer = undefined;
    if (generation !== this._generation || this._motorId !== motorIdentity(motor)) return;
    this._started = true;
    void this._holdControl(motor, dir, generation);
  }

  private async _holdControl(
    motor: MotorEntity,
    dir: Direction,
    generation: number,
  ): Promise<void> {
    try {
      const pending = this.actions.holdControl?.(motor, dir);
      if (pending) await pending;
    } catch {
      // Home Assistant reports service errors; forget the hold so it can retry.
    } finally {
      if (generation === this._generation) this._reset();
    }
  }

  // One iteration moves the bed for a single configured pulse and then stops,
  // for cover-backed motors too: cover.py runs open_cover/close_cover as one
  // finite controller command that performs its own STOP/release cleanup rather
  // than running until stop_cover. So both kinds of motor need re-issuing.
  private async _repeat(
    _motor: MotorEntity,
    dir: Direction,
    generation: number,
  ): Promise<void> {
    const motor = this._motor;
    if (!motor) return;
    // Plain controls repeat one finite movement at a time. Controllers with
    // declared start/release timing use the separate held-control path.
    while (generation === this._generation && !this._repeatBlocked) {
      try {
        const pending = this.actions.pulse(motor, dir);
        if (!pending) return;
        this._pulseInFlight = pending;
        try { await pending; } finally {
          if (this._pulseInFlight === pending) this._pulseInFlight = undefined;
        }
      } catch {
        // The bed rejected the command (usually a dropped BLE link). Stop
        // hammering it; the user can press again.
        return;
      }
    }
  }

  private _targetKey(
    stopEntityId = this._stop ?? undefined,
    cover = this._cover ?? undefined,
  ): string {
    return stopEntityId ?? cover ?? this._key ?? "";
  }

  // Returns the entity whose stop was requested, if any.
  private _release(
    target: Pick<PendingRelease, "cover" | "stopEntityId">,
  ): string | undefined {
    if (target.cover) {
      this.actions.stopCover(target.cover, target.stopEntityId);
      return target.cover;
    }
    this.actions.stopBed(target.stopEntityId);
    return target.stopEntityId;
  }

  private _scheduleRelease(): void {
    const release: PendingRelease = {
      id: ++this._releaseId,
      motorKey: this._key ?? "",
      targetKey: this._targetKey(),
      target: this._target,
      cover: this._cover ?? undefined,
      stopEntityId: this._stop ?? undefined,
      scopeGenerations: new Map(this._scopeStops.map((key) => [key, this._stopTargetGenerations.get(key) ?? 0])),
    };
    this._pendingReleases.set(release.id, release);
    const delay = this._heldControl?.releaseDelayMs ?? 0;
    if (delay <= 0) {
      this._runRelease(release);
      return;
    }
    release.timer = this.timers.setTimeout(() => this._runRelease(release), delay);
  }

  private _runRelease(release: PendingRelease): string | undefined {
    if (!this._pendingReleases.delete(release.id)) return undefined;
    if (release.timer !== undefined) this.timers.clearTimeout(release.timer);
    if ([...release.scopeGenerations].every(([key, generation]) =>
      this._stopTargetGenerations.get(key) === generation
    )) return this._release(release);
  }

  private _flushPendingForTarget(targetKey: string): Set<string> {
    const released = new Set<string>();
    for (const release of [...this._pendingReleases.values()]) {
      const key = release.targetKey;
      if (key !== targetKey) continue;
      this._runRelease(release);
      released.add(key);
    }
    return released;
  }

  private _flushAllReleases(skipTarget?: string): Set<string> {
    const released = new Set<string>();
    for (const release of [...this._pendingReleases.values()]) {
      const key = release.targetKey;
      if (key === skipTarget) {
        this._pendingReleases.delete(release.id);
        if (release.timer !== undefined) this.timers.clearTimeout(release.timer);
      } else {
        this._runRelease(release);
        released.add(key);
      }
    }
    return released;
  }

  private _targetsOverlap(
    targetKey: string,
    target: HoldTarget | undefined,
    stopEntityId: string | undefined,
    stopTarget: HoldTarget | undefined,
  ): boolean {
    if (stopEntityId !== undefined && targetKey === stopEntityId) return true;
    return !!target && !!stopTarget && holdTargetsOverlap(target, stopTarget);
  }

  // Returns whether a discarded release belonged to a Both hold.
  private _discardReleasesOverlapping(
    stopEntityId: string,
    stopTarget: HoldTarget | undefined,
  ): boolean {
    let discardedBoth = false;
    for (const release of [...this._pendingReleases.values()]) {
      if (!release.scopeGenerations.has(stopEntityId) && !this._targetsOverlap(
        release.targetKey,
        release.target,
        stopEntityId,
        stopTarget,
      )) continue;
      this._pendingReleases.delete(release.id);
      if (release.timer !== undefined) this.timers.clearTimeout(release.timer);
      if (release.target?.side === "both" && [...release.scopeGenerations].every(
        ([key, generation]) => this._stopTargetGenerations.get(key) === generation,
      )) discardedBoth = true;
    }
    return discardedBoth;
  }

  private _discardAllReleases(): void {
    for (const release of this._pendingReleases.values()) {
      if (release.timer !== undefined) this.timers.clearTimeout(release.timer);
    }
    this._pendingReleases.clear();
  }

  // A pointer-driven release. Only the pointer that started the hold may end
  // it, and a non-primary button release must not.
  endFromPointer(
    motor: MotorEntity,
    pointerId: number,
    isPrimaryButtonRelease: boolean,
    stopEntityId?: string,
  ): void {
    if (this._pointerId === null || pointerId !== this._pointerId) return;
    if (!isPrimaryButtonRelease) return;
    if (stopEntityId !== undefined && this._stop !== stopEntityId) return;
    this.end(motor, stopEntityId);
  }

  endActiveFromPointer(pointerId: number, isPrimaryButtonRelease: boolean): void {
    if (!this._motor || this._pointerId === null) return;
    this.endFromPointer(this._motor, pointerId, isPrimaryButtonRelease);
  }

  endKeyboard(
    motor?: MotorEntity,
    stopEntityId?: string,
    keyboardKey?: string,
  ): void {
    if (this._pointerId !== null || !this._motor) return;
    if (motor && !this._ownsRelease(motor, stopEntityId)) return;
    if (stopEntityId !== undefined && this._stop !== stopEntityId) return;
    if (keyboardKey !== undefined && this._keyboardKey !== null &&
        this._keyboardKey !== keyboardKey) return;
    this.end(this._motor);
  }

  // End a hold and stop the motor. Releasing one control must not end a hold
  // another control owns: a blur on some other motor's button would otherwise
  // stop the motor that is running.
  end(motor: MotorEntity, stopEntityId?: string): void {
    if (!this._ownsRelease(motor, stopEntityId)) return;
    const started = this._started;
    const hasMetadata = this._heldControl !== undefined;
    const releaseTarget = {
      cover: this._cover ?? undefined,
      stopEntityId: this._stop ?? undefined,
    };
    if (started && hasMetadata) this._scheduleRelease();
    this._reset();
    if (!started || hasMetadata) return;
    this._release(releaseTarget);
  }

  private _ownsRelease(motor: MotorEntity, stopEntityId?: string): boolean {
    if (this._key !== motor.key) return false;
    // A render can change the motor projection, but its retained STOP still
    // proves ownership. Without that proof require the original entity.
    return stopEntityId === undefined
      ? this._motorId === motorIdentity(motor)
      : this._stop === stopEntityId;
  }

  // Stop re-issuing pulses for this motor without sending anything to the bed.
  // Returns whether there was a matching hold to cancel.
  cancel(motor: MotorEntity | null, explicitStopFollows = false): boolean {
    if (!motor) return false;
    const matchedActive = this._key === motor.key;
    if (matchedActive) this._reset();
    let matchedRelease = false;
    if (explicitStopFollows) {
      for (const release of [...this._pendingReleases.values()]) {
        if (release.motorKey !== motor.key) continue;
        this._pendingReleases.delete(release.id);
        if (release.timer !== undefined) this.timers.clearTimeout(release.timer);
        matchedRelease = true;
      }
    }
    return matchedActive || matchedRelease;
  }

  // Cover stop behavior is supplied per motor by the backend. Keep ordinary
  // motor-specific stops on their motor key; a caller with an explicit
  // side-wide stop contract may invalidate any overlapping operation on that
  // physical side. The clicked cover service call remains the card's job.
  //
  // `peerStopEntityIds` are the other side's Stops. A one-side cover stop of a
  // started held Both operation presses them, as a side Stop does in
  // stopAll(): otherwise the other side keeps holding until the host bound.
  stopCover(
    motor: MotorEntity,
    target: HoldTarget | undefined,
    scope: CoverStopScope,
    stopEntityId?: string,
    peerStopEntityIds: readonly string[] = [],
  ): void {
    const coverId = motor.cover;
    if (!coverId) return;
    const stopIsOneSide = target !== undefined && target.side !== "both";
    const remaining = new Set<string>();
    const generations = new Map<string, number>();
    let pending: Promise<unknown> | undefined;
    const retainRemaining = (ids: readonly string[]): void => {
      for (const key of ids) {
        if (key === stopEntityId) continue;
        remaining.add(key);
        generations.set(key, this._stopTargetGenerations.get(key) ?? 0);
      }
    };
    if (
      this._key !== null &&
      (scope === "side" || this._key === motor.key) &&
      (coverId === this._cover ||
        (stopEntityId !== undefined && this._scopeStops.includes(stopEntityId)) ||
        this._targetsOverlap(this._targetKey(), this._target, coverId, target))
    ) {
      const sideOnlyStopOfBoth =
        (this._target?.side === "both" && stopIsOneSide) ||
        (stopEntityId !== undefined && this._remainingStops.includes(stopEntityId));
      if (this._started && sideOnlyStopOfBoth) {
        if (stopEntityId) retainRemaining(this._remainingStops);
        if (this._heldControl) retainRemaining(peerStopEntityIds);
      }
      pending = this._pulseInFlight;
      if (sideOnlyStopOfBoth && !this._heldControl && remaining.size === 0) {
        // A finite combined button can have work left on its other child. Stop
        // reissuing Both commands, but keep its original release owner alive.
        this._repeatBlocked = true;
      } else {
        this._reset();
      }
    }

    for (const release of [...this._pendingReleases.values()]) {
      const partialBothRelease =
        release.target?.side === "both" &&
        release.target.deviceId === target?.deviceId &&
        (target?.side === "left" || target?.side === "right");
      if (
        (scope !== "side" && partialBothRelease) ||
        (scope !== "side" && release.motorKey !== motor.key) ||
        !(release.cover === coverId ||
          (stopEntityId !== undefined && release.scopeGenerations.has(stopEntityId)) ||
          this._targetsOverlap(release.targetKey, release.target, coverId, target))
      ) continue;
      this._pendingReleases.delete(release.id);
      if (release.timer !== undefined) this.timers.clearTimeout(release.timer);
      // A superseded Both release cannot clean up a side now owned by newer work.
      if (stopIsOneSide && release.target?.side === "both" && [...release.scopeGenerations].every(
        ([key, generation]) => this._stopTargetGenerations.get(key) === generation,
      )) retainRemaining(peerStopEntityIds);
    }

    const activeStop = this._key !== null ? this._stop : null;
    const releaseRemaining = (): void => {
      for (const key of remaining) {
        if (key !== activeStop &&
            (this._stopTargetGenerations.get(key) ?? 0) === generations.get(key)) {
          this.actions.stopBed(key);
        }
      }
    };
    if (pending) void pending.then(releaseRemaining, releaseRemaining);
    else releaseRemaining();
  }

  // A stop button. Invalidating first matters: otherwise the in-flight pulse
  // resolves after the stop lands and the loop issues another pulse, so the bed
  // starts moving again right after the user asked it to stop. It also has to
  // invalidate *any* hold, not just one motor's, because this stop halts
  // whatever is moving. `stopEntityId` is the pressed button's own stop; it
  // wins over the held motor's, which may belong to a different side.
  // `peerStopEntityIds` are the other side's Stops, pressed only when this
  // side Stop ends a started held Both operation.
  stopAll(
    stopEntityId?: string,
    scopeOrAll?: readonly string[] | boolean,
    motorOrTarget?: string | HoldTarget,
    peerStopEntityIds: readonly string[] = [],
  ): void {
    const stop = stopEntityId ?? this._stop ?? undefined;
    const active = this._key !== null && this._started
      ? { cover: this._cover ?? undefined, stopEntityId: this._stop ?? undefined } : undefined;
    const stopTarget = typeof motorOrTarget === "object" ? motorOrTarget : undefined;
    const motorKey = typeof motorOrTarget === "string" ? motorOrTarget : undefined;
    const scope = [...new Set([
      ...(Array.isArray(scopeOrAll) ? scopeOrAll : stop ? [stop] : this._scopeStops),
      ...this._targetScope(stopTarget),
      ...(stop ? [stop] : []),
    ])];
    const broad = scopeOrAll === true && !stopTarget;
    const matchesAxis = motorKey === undefined || motorKey === this._key || stop === this._cover;
    const overlaps = this._key !== null && matchesAxis && (
      broad || scope.length === 0 || this._scopeStops.some((key) => scope.includes(key)) ||
      this._targetsOverlap(this._targetKey(), this._target, stop, stopTarget)
    );
    let endedHeldBoth = false;
    if (stopEntityId !== undefined) {
      if (broad) this._discardAllReleases();
      else endedHeldBoth = this._discardReleasesOverlapping(stopEntityId, stopTarget);
    }
    endedHeldBoth ||= overlaps && this._started && this._heldControl !== undefined &&
      this._target?.side === "both";
    const remaining = [...new Set([
      ...(overlaps && this._started ? this._remainingStops : []),
      ...(endedHeldBoth ? peerStopEntityIds : []),
    ])].filter((key) => !scope.includes(key) && key !== this._stop);
    const pending = overlaps ? this._pulseInFlight : undefined;
    const generations = new Map(remaining.map((key) => [key, this._stopTargetGenerations.get(key) ?? 0]));
    if (overlaps) this._reset();
    if (stopEntityId === undefined) {
      const released = this._flushAllReleases();
      const activeKey = active?.stopEntityId ?? active?.cover;
      if (active && (activeKey === undefined || !released.has(activeKey))) this._release(active);
      else if (!active && released.size === 0) this.actions.stopBed(stop);
    } else this.actions.stopBed(stopEntityId);
    if (remaining.length > 0) {
      const releaseRemaining = (): void => {
        for (const key of remaining) {
          if ((this._stopTargetGenerations.get(key) ?? 0) === generations.get(key)) this.actions.stopBed(key);
        }
      };
      if (pending) void pending.then(releaseRemaining, releaseRemaining);
      else releaseRemaining();
    }
  }

  // The card left the DOM mid-hold, so no pointer release will ever arrive.
  // Stops the loop and the bed: a cover would otherwise keep running with
  // nothing left to stop it, and the pulse already in flight on a button-backed
  // motor keeps moving the bed for the rest of its duration, which is a second
  // or more and longer still with customised pulse settings. Returns the
  // entities it stopped so the card does not stop them a second time.
  abandon(): string[] {
    const active = this._key === null ? null : {
      cover: this._cover ?? undefined,
      stopEntityId: this._stop ?? undefined,
    };
    const activeStarted = this._started;
    this._reset();
    const stopped = new Set<string>();
    const record = (id: string | undefined): void => {
      if (id !== undefined) stopped.add(id);
    };
    if (active && activeStarted) record(this._release(active));
    for (const release of [...this._pendingReleases.values()]) {
      record(this._runRelease(release));
    }
    return [...stopped];
  }

  releaseOnFocusLoss(): void { this.abandon(); }

  cancelForStopScope(scopeStopEntityIds: readonly string[]): boolean {
    let matched = false;
    for (const release of [...this._pendingReleases.values()]) {
      if (!scopeStopEntityIds.includes(release.targetKey)) continue;
      this._pendingReleases.delete(release.id);
      if (release.timer !== undefined) this.timers.clearTimeout(release.timer);
      matched = true;
    }
    if (this._key !== null && this._scopeStops.some((key) => scopeStopEntityIds.includes(key))) {
      this._reset();
      matched = true;
    }
    return matched;
  }

  private _reset(): void {
    if (this._startTimer !== undefined) this.timers.clearTimeout(this._startTimer);
    this._startTimer = undefined;
    this._key = null;
    this._motor = null;
    this._scopeStops = [];
    this._remainingStops = [];
    this._keyboardKey = null;
    this._pulseInFlight = undefined;
    this._motorId = null;
    this._cover = null;
    this._stop = null;
    this._target = undefined;
    this._pointerId = null;
    this._repeatBlocked = false;
    this._started = false;
    this._heldControl = undefined;
    this._generation++;
  }
}

export function attachHoldLifecycle(
  hold: MotorHold,
  documentTarget: HoldLifecycleTarget & { visibilityState: string },
  windowTarget: HoldLifecycleTarget,
): () => void {
  const abandon = (): void => {
    hold.abandon();
  };
  const onVisibilityChange = (): void => {
    if (documentTarget.visibilityState === "hidden") abandon();
  };
  documentTarget.addEventListener("visibilitychange", onVisibilityChange);
  windowTarget.addEventListener("pagehide", abandon);
  return () => {
    documentTarget.removeEventListener("visibilitychange", onVisibilityChange);
    windowTarget.removeEventListener("pagehide", abandon);
  };
}

export function stopCardMotorHold(
  hold: MotorHold,
  stopEntityId?: string,
  scopeStopEntityIds?: readonly string[],
  motorKey?: string,
  hass?: HomeAssistant,
): void {
  hold.stopAll(
    stopEntityId,
    scopeStopEntityIds ?? (stopEntityId ? [stopEntityId] : undefined),
    motorKey ?? holdTargetForEntity(hass, stopEntityId),
    pairedPeerStopEntityIds(hass, stopEntityId),
  );
}
