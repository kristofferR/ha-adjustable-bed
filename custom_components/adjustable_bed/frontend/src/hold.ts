// Press-and-hold state machine for the motor controls.
//
// Kept free of DOM and Home Assistant dependencies so it can be unit tested:
// the card owns the event wiring and the service calls, this owns the rules
// about who holds what and when a hold ends. Nearly every defect found while
// building press-and-hold lived in these rules rather than in the wiring.
import type { HomeAssistant, MotorEntity } from "./types";

export type Direction = "up" | "down";

export type HoldTargetSide = "left" | "right" | "both";

export interface HoldTarget {
  deviceId: string;
  side?: HoldTargetSide;
  // Preserve the registry's physical owner when a native child loses its
  // state attributes. The parent identifies the pair, while the child still
  // distinguishes one side from its sibling.
  physicalDeviceId?: string;
  parentDeviceId?: string;
}

function deviceParentId(
  deviceId: string,
  devices: HomeAssistant["devices"],
): string | undefined {
  const parentId = devices[deviceId]?.parent_device_id ?? devices[deviceId]?.via_device_id;
  return parentId && devices[parentId] ? parentId : undefined;
}

function deviceHasChildren(deviceId: string, devices: HomeAssistant["devices"]): boolean {
  return Object.values(devices).some(
    (candidate) =>
      (candidate.parent_device_id ?? candidate.via_device_id) === deviceId,
  );
}

function sideFromStopEntity(
  hass: HomeAssistant,
  entityId: string,
): HoldTargetSide | undefined {
  const stateSide = hass.states[entityId]?.attributes.bed_side ??
    hass.states[entityId]?.attributes.side;
  const translationKey = hass.entities[entityId]?.translation_key;
  const registrySide = translationKey === "stop_left"
    ? "left"
    : translationKey === "stop_right"
      ? "right"
      : translationKey === "stop_both"
        ? "both"
        : undefined;
  const stateIsSide = stateSide === "left" || stateSide === "right" || stateSide === "both";
  if (stateIsSide && registrySide && stateSide !== registrySide) return undefined;
  if (stateIsSide) return stateSide;
  return registrySide;
}

function isRegisteredStopEntity(entityId: string, hass: HomeAssistant): boolean {
  const entry = hass.entities[entityId];
  return entry?.platform === "adjustable_bed" &&
    entry.entity_id.startsWith("button.") &&
    (entry.translation_key === "stop" ||
      entry.translation_key === "stop_left" ||
      entry.translation_key === "stop_right" ||
      entry.translation_key === "stop_both");
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
  const declaredSide = sideFromStopEntity(hass, entityId);
  const side: HoldTargetSide | undefined =
    declaredSide === "left" || declaredSide === "right" || declaredSide === "both"
      ? declaredSide
      : !parentId && deviceHasChildren(deviceId, devices)
        ? "both"
        : undefined;

  return {
    // A side-less child is not proof that the stop owns its parent and sibling.
    // Keep its physical ID until HA publishes a logical side.
    deviceId: parentId && side ? parentId : deviceId,
    side,
    physicalDeviceId: deviceId,
    ...(parentId ? { parentDeviceId: parentId } : {}),
  };
}

function holdTargetsOverlap(
  first: HoldTarget | undefined,
  second: HoldTarget | undefined,
): boolean {
  // Missing registry ownership is ambiguous, so keep the established broad-stop
  // behavior instead of risking a hold surviving a STOP that may own it.
  if (!first || !second) return true;
  const firstOwner = first.parentDeviceId ?? first.deviceId;
  const secondOwner = second.parentDeviceId ?? second.deviceId;
  if (firstOwner !== secondOwner) return false;
  // An explicitly known Both target overlaps either child even if HA has
  // temporarily omitted that child's logical-side state attributes.
  if (first.side === "both" || second.side === "both") return true;
  if (first.side && second.side) {
    return first.side === second.side;
  }
  // A child with missing state attributes remains distinct from a sibling.
  // Same-device unsided controls retain the existing broad-stop behavior.
  return !first.physicalDeviceId || !second.physicalDeviceId ||
    first.physicalDeviceId === second.physicalDeviceId;
}

function sameStopIdentity(
  retainedStop: string | null | undefined,
  currentStop: string | undefined,
): boolean {
  return currentStop !== undefined && retainedStop === currentStop;
}

function pairedPeerStopEntityIds(
  hass: HomeAssistant | undefined,
  stopEntityId: string | undefined,
): string[] {
  if (!hass || !stopEntityId) return [];
  const deviceId = hass.entities[stopEntityId]?.device_id;
  if (!deviceId) return [];
  const side = sideFromStopEntity(hass, stopEntityId);
  if (side === "left" || side === "right") {
    const peerSide = side === "left" ? "right" : "left";
    const sameDeviceStops = Object.values(hass.entities).filter(
      (entry) =>
        entry.entity_id !== stopEntityId &&
        entry.device_id === deviceId &&
        isRegisteredStopEntity(entry.entity_id, hass) &&
        sideFromStopEntity(hass, entry.entity_id) === peerSide,
    );
    if (sameDeviceStops.length === 1) return [sameDeviceStops[0].entity_id];
  }
  const devices = hass.devices ?? {};
  const parentId = deviceParentId(deviceId, devices);
  if (!parentId) return [];
  const childIds = Object.entries(devices)
    .filter(([, device]) => (device.parent_device_id ?? device.via_device_id) === parentId)
    .map(([id]) => id);
  // Paired entries have two physical children. Ambiguous or incomplete graphs
  // cannot prove which registry stop owns the remaining side.
  if (childIds.length !== 2 || !childIds.includes(deviceId)) return [];
  const peerId = childIds.find((id) => id !== deviceId);
  if (!peerId) return [];
  const stops = Object.values(hass.entities).filter(
    (entry) =>
      entry.device_id === peerId &&
      isRegisteredStopEntity(entry.entity_id, hass) &&
      entry.translation_key === "stop",
  );
  return stops.length === 1 ? [stops[0].entity_id] : [];
}

export function movementPulse(
  hass: HomeAssistant | undefined,
  motor: MotorEntity,
  direction: Direction,
): Promise<unknown> | undefined {
  const heldControl = motor.heldControls?.[direction];
  if (heldControl) {
    const entityId = motor.cover ?? motor[direction];
    const deviceId = entityId ? hass?.entities[entityId]?.device_id : undefined;
    if (!deviceId) return undefined;
    const side = entityId ? hass?.states[entityId]?.attributes.bed_side : undefined;
    return hass?.callService("adjustable_bed", "hold_control", {
      device_id: [deviceId],
      control: heldControl.control,
      // Each operation is host-bounded and cleans up with STOP. The card can
      // safely start another bounded operation if the user is still holding.
      duration: 60,
      ...(side === "left" || side === "right" || side === "both" ? { side } : {}),
    });
  }
  if (motor.timedMove) {
    // A shared movement window preserves each receiver's cadence without
    // making the faster side wait out its partner's configured finite pulse.
    return hass?.callService("adjustable_bed", "timed_move", {
      device_id: motor.timedMove.deviceId,
      side: "both",
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

export interface HoldActions {
  // Runs one finite movement pulse and resolves when the bed has finished it.
  // Resolving is what paces the repeat loop; rejecting stops it.
  pulse: (motor: MotorEntity, dir: Direction) => Promise<unknown> | undefined;
  // Stops a cover-backed motor, which is the only kind with its own stop. The
  // bed stop identifies the compact target retained when the hold began.
  stopCover: (coverEntityId: string, stopEntityId?: string) => void;
  // The stop that covers the held motor. Cancels the command in flight.
  // `stopEntityId` is the stop belonging to the bed the motor is on, which on a
  // paired bed is the side's own stop rather than the parent's; omitted falls
  // back to the single bed's stop.
  stopBed: (stopEntityId?: string) => void;
}

interface PendingRelease {
  id: number;
  stop?: string;
  target?: HoldTarget;
  started: boolean;
  timer: ReturnType<typeof setTimeout>;
}

export class MotorHold {
  // Ownership is tracked by MotorEntity.key rather than object identity: the
  // first pulse completing updates that entity, which re-renders the card and
  // rebuilds every MotorEntity, so a release handler would otherwise hold a
  // different object for the same motor and never stop the loop.
  private _key: string | null = null;
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
  private _started = false;
  private _activeHeldControl: { startDelayMs: number; releaseDelayMs: number } | null = null;
  private _releaseId = 0;
  private readonly _pendingReleases = new Map<number, PendingRelease>();

  constructor(private readonly actions: HoldActions) {}

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
    target?: HoldTarget,
  ): void {
    this._begin(motor, dir, pointerId, stopEntityId, target);
  }

  // A semantic click has no down/up interval. Start the same held service and
  // release it just after its controller-declared start guard.
  activateForTap(
    motor: MotorEntity,
    dir: Direction,
    stopEntityId?: string,
    target?: HoldTarget,
  ): void {
    const generation = this._begin(motor, dir, null, stopEntityId, target);
    if (generation === null) return;
    const startDelayMs = this._activeHeldControl?.startDelayMs ?? 0;
    setTimeout(() => {
      if (generation === this._generation && this._key === motor.key) {
        this.end(motor);
      }
    }, startDelayMs + 1);
  }

  private _begin(
    motor: MotorEntity,
    dir: Direction,
    pointerId: number | null,
    stopEntityId?: string,
    target?: HoldTarget,
  ): number | null {
    if (this._key !== null) return null;
    // Finish only delayed STOPs that overlap this physical target. An unrelated
    // side can continue its own release while this hold starts.
    this._flushPendingReleases(target, stopEntityId);
    this._key = motor.key;
    this._cover = motor.cover ?? null;
    this._stop = stopEntityId ?? null;
    this._target = target;
    this._pointerId = pointerId;
    this._activeHeldControl = motor.heldControls?.[dir] ?? null;
    const generation = ++this._generation;
    void this._repeat(motor, dir, generation);
    return generation;
  }

  // Each iteration is one bounded backend operation. Most controls run one
  // configured pulse; controllers with a held service run until their declared
  // safety bound. Both paths clean up, and the card repeats only while held.
  private async _repeat(
    motor: MotorEntity,
    dir: Direction,
    generation: number,
  ): Promise<void> {
    const startDelayMs = this._activeHeldControl?.startDelayMs ?? 0;
    if (startDelayMs > 0) {
      await new Promise<void>((resolve) => setTimeout(resolve, startDelayMs));
      if (generation !== this._generation) return;
    }
    // Awaiting each operation before starting the next prevents commands from
    // queueing. If the user releases or the card disappears, the current call
    // still ends at its controller-declared bound and performs its cleanup.
    while (generation === this._generation) {
      try {
        const pending = this.actions.pulse(motor, dir);
        this._started = !!pending;
        if (!pending) return;
        await pending;
      } catch {
        // The bed rejected the command (usually a dropped BLE link). Stop
        // hammering it; the user can press again.
        return;
      }
    }
  }

  // A pointer-driven release. Only the pointer that started the hold may end
  // it, and a non-primary button release must not.
  endFromPointer(
    motor: MotorEntity,
    pointerId: number,
    isPrimaryButtonRelease: boolean,
  ): void {
    if (this._pointerId !== null && pointerId !== this._pointerId) return;
    if (!isPrimaryButtonRelease) return;
    this.end(motor);
  }

  // End a hold and stop the motor. Releasing one control must not end a hold
  // another control owns: a blur on some other motor's button would otherwise
  // stop the motor that is running.
  end(motor: MotorEntity): void {
    const stop = this._stop ?? undefined;
    const heldControl = this._activeHeldControl;
    const target = this._target;
    const started = this._started;
    if (!this.cancel(motor)) return;
    if (heldControl) {
      this._scheduleRelease(stop, target, heldControl.releaseDelayMs, started);
      return;
    }
    if (motor.cover) {
      this.actions.stopCover(motor.cover, stop);
      return;
    }
    // Cancelling the loop does not touch the pulse already in flight, and each
    // pulse is a second or more, so without this the bed keeps moving well
    // after the control is released. The stop cancels the running command,
    // which is also what makes a short tap move the bed briefly rather than
    // for a full pulse.
    this.actions.stopBed(stop);
  }

  // Stop re-issuing pulses for this motor without sending anything to the bed.
  // Returns whether there was a matching hold to cancel.
  cancel(motor: MotorEntity | null, target?: HoldTarget): boolean {
    if (
      !motor ||
      this._key !== motor.key ||
      (target !== undefined && !holdTargetsOverlap(this._target, target))
    ) return false;
    this._reset();
    return true;
  }

  // A stop button. Invalidating first matters: otherwise the in-flight pulse
  // resolves after the stop lands and the loop issues another pulse, so the bed
  // starts moving again right after the user asked it to stop. It also has to
  // invalidate *any* hold, not just one motor's, because this stop halts
  // whatever is moving. `stopEntityId` is the pressed button's own stop; it
  // wins over the held motor's, which may belong to a different side.
  stopAll(
    stopEntityId?: string,
    target?: HoldTarget,
    peerStopEntityIds: readonly string[] = [],
  ): void {
    const matchingPending = [...this._pendingReleases.values()].filter((pending) =>
      sameStopIdentity(pending.stop, stopEntityId) ||
      holdTargetsOverlap(pending.target, target),
    );
    const pendingStop = matchingPending[0]?.stop;
    const stop = stopEntityId ?? this._stop ?? pendingStop;
    const activeMatches = this._key !== null && (
      sameStopIdentity(this._stop, stopEntityId) ||
      holdTargetsOverlap(this._target, target)
    );
    const startedBothHold =
      (activeMatches && this._started && this._activeHeldControl !== null &&
        this._target?.side === "both") ||
      matchingPending.some((pending) => pending.started && pending.target?.side === "both");
    const remainingStops = startedBothHold
      ? peerStopEntityIds.filter((id) => id !== stopEntityId)
      : [];
    this._discardPendingReleases(target, stopEntityId);
    if (activeMatches) this._reset();
    this.actions.stopBed(stop);
    for (const peerStop of remainingStops) this.actions.stopBed(peerStop);
  }

  // The card left the DOM mid-hold, so no pointer release will ever arrive.
  // Stops the loop and the bed: a cover would otherwise keep running with
  // nothing left to stop it, and the pulse already in flight on a button-backed
  // motor keeps moving the bed for the rest of its duration, which is a second
  // or more and longer still with customised pulse settings.
  abandon(): string[] {
    const cover = this._cover;
    const stop = this._stop ?? undefined;
    const heldControl = this._activeHeldControl;
    const wasHolding = this._key !== null;
    const stopped = new Set(this._flushPendingReleases());
    this._reset();
    if (!wasHolding) return [...stopped];
    if (heldControl) {
      if (!stop || !stopped.has(stop)) this.actions.stopBed(stop);
      if (stop) stopped.add(stop);
      return [...stopped];
    }
    if (cover) {
      this.actions.stopCover(cover, stop);
      stopped.add(cover);
      return [...stopped];
    }
    if (!stop || !stopped.has(stop)) this.actions.stopBed(stop);
    if (stop) stopped.add(stop);
    return [...stopped];
  }

  private _reset(): void {
    this._key = null;
    this._cover = null;
    this._stop = null;
    this._target = undefined;
    this._pointerId = null;
    this._started = false;
    this._activeHeldControl = null;
    this._generation++;
  }

  private _scheduleRelease(
    stop: string | undefined,
    target: HoldTarget | undefined,
    delayMs: number,
    started: boolean,
  ): void {
    const pending: PendingRelease = {
      id: ++this._releaseId,
      stop,
      target,
      started,
      timer: setTimeout(() => this._runPendingRelease(pending), delayMs),
    };
    this._pendingReleases.set(pending.id, pending);
  }

  private _runPendingRelease(pending: PendingRelease): void {
    if (!this._pendingReleases.delete(pending.id)) return;
    this.actions.stopBed(pending.stop);
  }

  private _flushPendingReleases(
    target?: HoldTarget,
    stopEntityId?: string,
  ): Set<string> {
    const stopped = new Set<string>();
    for (const pending of [...this._pendingReleases.values()]) {
      if (
        !sameStopIdentity(pending.stop, stopEntityId) &&
        !holdTargetsOverlap(pending.target, target)
      ) continue;
      clearTimeout(pending.timer);
      this._runPendingRelease(pending);
      if (pending.stop) stopped.add(pending.stop);
    }
    return stopped;
  }

  private _discardPendingReleases(
    target?: HoldTarget,
    stopEntityId?: string,
  ): void {
    for (const pending of [...this._pendingReleases.values()]) {
      if (
        !sameStopIdentity(pending.stop, stopEntityId) &&
        !holdTargetsOverlap(pending.target, target)
      ) continue;
      clearTimeout(pending.timer);
      this._pendingReleases.delete(pending.id);
    }
  }
}

export function stopFromCard(
  hold: MotorHold,
  hass: HomeAssistant | undefined,
  stopEntityId?: string,
): void {
  hold.stopAll(
    stopEntityId,
    holdTargetForEntity(hass, stopEntityId),
    pairedPeerStopEntityIds(hass, stopEntityId),
  );
}
