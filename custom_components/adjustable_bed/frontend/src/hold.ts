// Press-and-hold state machine for the motor controls.
//
// Kept free of DOM and Home Assistant dependencies so it can be unit tested:
// the card owns the event wiring and the service calls, this owns the rules
// about who holds what and when a hold ends. Nearly every defect found while
// building press-and-hold lived in these rules rather than in the wiring.
import type { MotorEntity } from "./types";

export type Direction = "up" | "down";

export interface HoldActions {
  // Runs one finite movement pulse and resolves when the bed has finished it.
  // Resolving is what paces the repeat loop; rejecting stops it.
  pulse: (motor: MotorEntity, dir: Direction) => Promise<void> | undefined;
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
    if (this._key !== null) return;
    this._key = motor.key;
    this._cover = motor.cover ?? null;
    this._stop = stopEntityId ?? null;
    this._pointerId = pointerId;
    void this._repeat(motor, dir, ++this._generation);
  }

  // One iteration moves the bed for a single configured pulse and then stops,
  // for cover-backed motors too: cover.py runs open_cover/close_cover as one
  // finite controller command that performs its own STOP/release cleanup rather
  // than running until stop_cover. So both kinds of motor need re-issuing.
  private async _repeat(
    motor: MotorEntity,
    dir: Direction,
    generation: number,
  ): Promise<void> {
    // Awaiting each call before issuing the next keeps commands from queueing
    // up behind each other, so the integration never has to cancel one
    // mid-flight. It does not make the motion continuous: each backend command
    // is finite and ends with the protocol's release burst, so a hold is a
    // train of pulses with a short stop between them. Making it continuous
    // needs a hold-until-released primitive in the integration, which does not
    // exist yet: see issue #483.
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
    if (!this.cancel(motor)) return;
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
    const stop = stopEntityId ?? this._stop ?? undefined;
    this._reset();
    this.actions.stopBed(stop);
  }

  // The card left the DOM mid-hold, so no pointer release will ever arrive.
  // Stops the loop and the bed: a cover would otherwise keep running with
  // nothing left to stop it, and the pulse already in flight on a button-backed
  // motor keeps moving the bed for the rest of its duration, which is a second
  // or more and longer still with customised pulse settings.
  abandon(): void {
    const cover = this._cover;
    const stop = this._stop ?? undefined;
    const wasHolding = this._key !== null;
    this._reset();
    if (!wasHolding) return;
    if (cover) this.actions.stopCover(cover, stop);
    else this.actions.stopBed(stop);
  }

  private _reset(): void {
    this._key = null;
    this._cover = null;
    this._stop = null;
    this._pointerId = null;
    this._generation++;
  }
}
