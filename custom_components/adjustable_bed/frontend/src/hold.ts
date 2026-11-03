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
}

export type CoverStopScope = "motor" | "side";

export function holdTargetForEntity(
  hass: HomeAssistant | undefined,
  entityId?: string,
): HoldTarget | undefined {
  if (!hass || !entityId) return undefined;
  const deviceId = hass.entities[entityId]?.device_id;
  if (!deviceId) return undefined;

  const devices = hass.devices ?? {};
  const device = devices[deviceId];
  const declaredSide = hass.states[entityId]?.attributes.bed_side ??
    hass.states[entityId]?.attributes.side;
  const side: HoldTargetSide | undefined =
    declaredSide === "left" || declaredSide === "right" || declaredSide === "both"
      ? declaredSide
      : Object.values(devices).some((candidate) => candidate.parent_device_id === deviceId)
        ? "both"
        : undefined;

  return {
    deviceId: device?.parent_device_id ?? deviceId,
    side,
  };
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
  hold.stopAll(stopEntityId, coversAllTargets, target);
}

export class MotorHold {
  // Ownership is tracked by MotorEntity.key rather than object identity: the
  // first pulse completing updates that entity, which re-renders the card and
  // rebuilds every MotorEntity, so a release handler would otherwise hold a
  // different object for the same motor and never stop the loop.
  private _key: string | null = null;
  private _motor: MotorEntity | null = null;
  private _scopeStops: string[] = [];
  private _remainingStops: string[] = [];
  private readonly _stopTargetGenerations = new Map<string, number>();
  private _keyboardKey: string | null = null;
  private _pulseInFlight: Promise<unknown> | undefined;
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
    return sides.map((side) => `target:${target.deviceId}:${side}`);
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
    if (generation !== this._generation || this._key !== motor.key) return;
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

  private _release(target: Pick<PendingRelease, "cover" | "stopEntityId">): void {
    if (target.cover) this.actions.stopCover(target.cover, target.stopEntityId);
    else this.actions.stopBed(target.stopEntityId);
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

  private _runRelease(release: PendingRelease): void {
    if (!this._pendingReleases.delete(release.id)) return;
    if (release.timer !== undefined) this.timers.clearTimeout(release.timer);
    if ([...release.scopeGenerations].every(([key, generation]) =>
      this._stopTargetGenerations.get(key) === generation
    )) this._release(release);
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
    if (!target || !stopTarget || target.deviceId !== stopTarget.deviceId) return false;
    return !target.side || !stopTarget.side ||
      target.side === "both" || stopTarget.side === "both" ||
      target.side === stopTarget.side;
  }

  private _discardReleasesOverlapping(
    stopEntityId: string,
    stopTarget: HoldTarget | undefined,
  ): void {
    for (const release of [...this._pendingReleases.values()]) {
      if (!release.scopeGenerations.has(stopEntityId) && !this._targetsOverlap(
        release.targetKey,
        release.target,
        stopEntityId,
        stopTarget,
      )) continue;
      this._pendingReleases.delete(release.id);
      if (release.timer !== undefined) this.timers.clearTimeout(release.timer);
    }
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
    if (motor && motor.key !== this._key) return;
    if (stopEntityId !== undefined && this._stop !== stopEntityId) return;
    if (keyboardKey !== undefined && this._keyboardKey !== null &&
        this._keyboardKey !== keyboardKey) return;
    this.end(this._motor);
  }

  // End a hold and stop the motor. Releasing one control must not end a hold
  // another control owns: a blur on some other motor's button would otherwise
  // stop the motor that is running.
  end(motor: MotorEntity, stopEntityId?: string): void {
    if (stopEntityId !== undefined && this._stop !== stopEntityId) return;
    if (this._key !== motor.key) return;
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
  stopCover(
    motor: MotorEntity,
    target: HoldTarget | undefined,
    scope: CoverStopScope,
    stopEntityId?: string,
  ): void {
    const coverId = motor.cover;
    if (!coverId) return;
    let remaining: string[] = [];
    let pending: Promise<unknown> | undefined;
    let generations = new Map<string, number>();
    if (
      this._key !== null &&
      (scope === "side" || this._key === motor.key) &&
      (coverId === this._cover ||
        (stopEntityId !== undefined && this._scopeStops.includes(stopEntityId)) ||
        this._targetsOverlap(this._targetKey(), this._target, coverId, target))
    ) {
      const sideOnlyStopOfBoth =
        this._target?.side === "both" &&
        this._target.deviceId === target?.deviceId &&
        (target?.side === "left" || target?.side === "right") ||
        (stopEntityId !== undefined && this._remainingStops.includes(stopEntityId));
      remaining = this._started && sideOnlyStopOfBoth && stopEntityId
        ? this._remainingStops.filter((key) => key !== stopEntityId) : [];
      pending = this._pulseInFlight;
      generations = new Map(remaining.map((key) => [key, this._stopTargetGenerations.get(key) ?? 0]));
      if (sideOnlyStopOfBoth && !this._heldControl && remaining.length === 0) {
        // A finite combined button can have work left on its other child. Stop
        // reissuing Both commands, but keep its original release owner alive.
        this._repeatBlocked = true;
      } else {
        this._reset();
      }
    }

    if (remaining.length > 0) {
      const releaseRemaining = (): void => {
        for (const key of remaining) {
          if (this._stopTargetGenerations.get(key) === generations.get(key)) this.actions.stopBed(key);
        }
      };
      if (pending) void pending.then(releaseRemaining, releaseRemaining);
      else releaseRemaining();
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
    }
  }

  // A stop button. Invalidating first matters: otherwise the in-flight pulse
  // resolves after the stop lands and the loop issues another pulse, so the bed
  // starts moving again right after the user asked it to stop. It also has to
  // invalidate *any* hold, not just one motor's, because this stop halts
  // whatever is moving. `stopEntityId` is the pressed button's own stop; it
  // wins over the held motor's, which may belong to a different side.
  stopAll(
    stopEntityId?: string,
    scopeOrAll?: readonly string[] | boolean,
    motorOrTarget?: string | HoldTarget,
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
    if (stopEntityId !== undefined) {
      if (broad) this._discardAllReleases();
      else this._discardReleasesOverlapping(stopEntityId, stopTarget);
    }
    const remaining = overlaps && this._started
      ? this._remainingStops.filter((key) => !scope.includes(key)) : [];
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
          if (this._stopTargetGenerations.get(key) === generations.get(key)) this.actions.stopBed(key);
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
  // or more and longer still with customised pulse settings.
  abandon(): void {
    const active = this._key === null ? null : {
      cover: this._cover ?? undefined,
      stopEntityId: this._stop ?? undefined,
    };
    const activeStarted = this._started;
    this._reset();
    if (active && activeStarted) this._release(active);
    this._flushAllReleases();
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
  const abandon = (): void => hold.abandon();
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
): void {
  hold.stopAll(
    stopEntityId,
    scopeStopEntityIds ?? (stopEntityId ? [stopEntityId] : undefined),
    motorKey,
  );
}
