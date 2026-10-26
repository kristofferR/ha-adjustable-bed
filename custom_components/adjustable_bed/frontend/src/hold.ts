// Press-and-hold state machine for the motor controls.
//
// Kept free of DOM and Home Assistant dependencies so it can be unit tested:
// the card owns the event wiring and the service calls, this owns the rules
// about who holds what and when a hold ends. Nearly every defect found while
// building press-and-hold lived in these rules rather than in the wiring.
import type { HomeAssistant, MotorEntity } from "./types";

export type Direction = "up" | "down";

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
  // The pointer that owns the hold. Pointer-end events from any other pointer
  // must be ignored: a second touch on the same control would otherwise cancel
  // the primary hold and stop the motor early.
  private _pointerId: number | null = null;
  // Bumping this is what stops an in-flight repeat loop: the loop's next
  // iteration sees a stale value and exits.
  private _generation = 0;
  private _activeHeldControl: { startDelayMs: number; releaseDelayMs: number } | null = null;
  private _releaseTimer: ReturnType<typeof setTimeout> | null = null;
  private _pendingRelease: { generation: number; stop?: string } | null = null;

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
  ): void {
    this._begin(motor, dir, pointerId, stopEntityId);
  }

  // A semantic click has no down/up interval. Start the same held service and
  // release it just after its controller-declared start guard.
  activateForTap(motor: MotorEntity, dir: Direction, stopEntityId?: string): void {
    const generation = this._begin(motor, dir, null, stopEntityId);
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
  ): number | null {
    if (this._key !== null) return null;
    // Finish a prior delayed release before starting a new hold. The next
    // controller-declared start guard keeps that STOP ahead of its first write.
    this._flushPendingRelease();
    this._key = motor.key;
    this._cover = motor.cover ?? null;
    this._stop = stopEntityId ?? null;
    this._pointerId = pointerId;
    this._activeHeldControl = motor.heldControls?.[dir] ?? null;
    if (this._releaseTimer !== null) clearTimeout(this._releaseTimer);
    this._releaseTimer = null;
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
    if (!this.cancel(motor)) return;
    if (heldControl) {
      const pendingRelease = { generation: this._generation, stop };
      this._pendingRelease = pendingRelease;
      this._releaseTimer = setTimeout(() => {
        if (this._pendingRelease !== pendingRelease) return;
        this._pendingRelease = null;
        this._releaseTimer = null;
        if (this._generation === pendingRelease.generation && this._key === null) {
          this.actions.stopBed(stop);
        }
      }, heldControl.releaseDelayMs);
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
  cancel(motor: MotorEntity | null): boolean {
    if (!motor || this._key !== motor.key) return false;
    this._reset();
    return true;
  }

  // A stop button. Invalidating first matters: otherwise the in-flight pulse
  // resolves after the stop lands and the loop issues another pulse, so the bed
  // starts moving again right after the user asked it to stop. It also has to
  // invalidate *any* hold, not just one motor's, because this stop halts
  // whatever is moving. `stopEntityId` is the pressed button's own stop; it
  // wins over the held motor's, which may belong to a different side.
  stopAll(stopEntityId?: string): void {
    const stop = stopEntityId ?? this._stop ?? this._pendingRelease?.stop;
    this._discardPendingRelease();
    this._reset();
    this.actions.stopBed(stop);
  }

  // The card left the DOM mid-hold, so no pointer release will ever arrive.
  // Stops the loop and the bed: a cover would otherwise keep running with
  // nothing left to stop it, and the pulse already in flight on a button-backed
  // motor keeps moving the bed for the rest of its duration, which is a second
  // or more and longer still with customised pulse settings.
  abandon(): string | undefined {
    const cover = this._cover;
    const stop = this._stop ?? undefined;
    const heldControl = this._activeHeldControl;
    const wasHolding = this._key !== null;
    const pendingStop = this._flushPendingRelease();
    this._reset();
    if (!wasHolding) return pendingStop;
    if (heldControl) {
      this.actions.stopBed(stop);
      return stop;
    }
    if (cover) {
      this.actions.stopCover(cover, stop);
      return cover;
    }
    this.actions.stopBed(stop);
    return stop;
  }

  private _reset(): void {
    if (this._releaseTimer !== null) clearTimeout(this._releaseTimer);
    this._releaseTimer = null;
    this._key = null;
    this._cover = null;
    this._stop = null;
    this._pointerId = null;
    this._activeHeldControl = null;
    this._generation++;
  }

  private _flushPendingRelease(): string | undefined {
    const pending = this._pendingRelease;
    if (!pending) return undefined;
    if (this._releaseTimer !== null) clearTimeout(this._releaseTimer);
    this._releaseTimer = null;
    this._pendingRelease = null;
    this.actions.stopBed(pending.stop);
    return pending.stop;
  }

  private _discardPendingRelease(): void {
    if (this._releaseTimer !== null) clearTimeout(this._releaseTimer);
    this._releaseTimer = null;
    this._pendingRelease = null;
  }
}
