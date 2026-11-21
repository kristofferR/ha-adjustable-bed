# Scheduling, cancellation and connection ownership

How a command travels from a control or an action to the bed, how STOP gets
ahead of it, and what happens when the bed cannot be reached.

## Connecting

- A command connects on demand, inside its own turn, so it never starts on a
  half-open link. A connect makes three attempts; when several adapters or
  proxies can reach the bed it makes at least five, with capped backoff, so a
  strong but unusable path does not use up every attempt. Some beds and app
  profiles use a shorter connect timeout.
- The **Bluetooth connection** setting decides how long the link stays open
  after a command:
  - **Release right after each command** keeps it for one second, so rapid
    taps share one link, then gives it back to the remote and the phone app.
    Periodic position reconciliation is off in this mode.
  - **Stay connected for a while** keeps it for **Seconds to stay connected**
    (40 by default). The idle timer stops while a command runs and starts
    again when the last one ends.
  - **Always stay connected** has no idle timer.
  Beds that need a persistent connection always keep the link.
- Concurrent pairs hold both links until a combined command and its cleanup
  finish on both sides. Sequential pairs disconnect one side before switching
  to the other.

## One writer at a time

- Every command for the bed goes through the device's command scheduler. A
  command is admitted for the resources it controls: a motor, a side or the
  whole bed. A command that cancels running work, as movements and presets
  do, replaces running or queued commands whose resources overlap its own;
  others queue behind it. Exactly one operation holds the writer at a time. The
  Connect and Disconnect buttons act on the link directly, outside the queue.
- The scheduler treats controller operations as opaque and never retries one
  after a transport error.
- Position and light reads yield to commands and STOP. A seek finishes the
  controller's read preparation before its feedback timeout starts, and stale
  feedback never stands in for a failed read.
- A timed movement starts its budget after connecting and after the
  controller's movement preparation. STOP and cleanup can extend the total
  time of the action.

## STOP

- A STOP is admitted at once, outside the queue. It raises the STOP epoch, so
  commands admitted before it and still waiting never start.
- It cancels the motion holding the writer on its bed or side, whichever motor
  that is. The write in flight and that command's own cleanup finish first:
  the controller sends its protocol STOP or release with a fresh cancel event.
  Then the STOP's own frames go out, ahead of anything queued. A bed-wide
  STOP covers every resource; a motor or side STOP spares running work whose
  declared resources do not overlap it. A command declared for the whole bed
  overlaps every STOP.
- When the command holding the writer is still connecting, the STOP waits for
  that connect. Nothing moves meanwhile, and the STOP then uses the new link.
- An admitted STOP outlives its caller: cancelling the action does not cancel
  it, and unloading the entry waits for it.
- Movement helpers report a failed STOP or release, keeping the movement's own
  error as its context.

## Renewable hold leases

A renewable hold (#483) is a `CommandKind.HOLD` intent with a lease: an owner,
a generation and a deadline on the event loop's monotonic clock. A controller
opts in through `ExecutionCapabilities.hold`, or per held control through its
`hold_controls` scope; every other controller and control keeps finite pulses.

- A request naming a live lease's owner, resources, generation and action moves
  its deadline and returns. It writes nothing.
- The first request of a generation reserves it before its checks. Requests
  that arrive while it connects renew the reservation, and a STOP before
  admission ends it.
- At the deadline the scheduler sets the hold's own cancel event, the signal a
  STOP or a replacement uses, and the controller runs its release cleanup.
  Unlike STOP, expiry does not cancel the operation, so delayed release frames
  still go out.
- While leased, a controller refreshes its held frame at its app's interval
  (`BedController.leased_hold_refreshes`), not at **Movement per tap**.
- STOP, replacement, a dropped link, disconnect and unload end the generation.
  An ended or superseded generation is refused, including a late renewal, so a
  stale request can never start motion. Leases live only in memory.
- A hold runs for at most its ceiling: 30 seconds for a stream hold, 10 seconds
  for a latched one (`ExecutionCapabilities.hold_ceiling_ms`), and every
  renewal is clamped to it. For a serial hold the clock starts when the
  controller operation begins, after connecting, and at the ceiling the hold
  ends as at expiry, after any write already in flight. A merged-stream
  member's ceiling counts from its request.
- The dashboard card holds through `timed_move` or `hold_control`, renewing
  every 250 ms with a 750 ms lease. Releasing the control, leaving the page or
  hiding it stops the renewals and sends the usual STOP.
- A `hold_control` request on a control without a declared hold is no
  scheduler lease. The action runs the control's ordinary bounded hold, at most
  30 seconds, so the bed gets the frames it always got; a renewal only moves
  the action's own deadline. When that deadline passes with the hold still
  running, the action cancels its own command as a STOP does, so the controller
  runs its release, and no other command is touched. A press keeps the route it
  started with, so its renewals never become a scheduler lease if the
  controller's capabilities change mid-press. A renewal of an ended press moves
  nothing, and an older generation is refused.

## Merged stream for concurrent motors

A controller whose app holds independent motors together (#516) lists them in
`ExecutionCapabilities.concurrent`. On a standalone bed, a `timed_move` on one
of those motors joins a merged stream instead of running as a serial command.
Paired beds stay serial.

- One streamer per device owns the writer as a single `CommandKind.STREAM`
  intent. Each tick the controller composes every live member into its frames.
- A member on a motor that already streams replaces it. A member that ends,
  expires or is replaced gets its own cleanup while the others keep moving; the
  last one out runs the release.
- A motor's own Stop ends only its member. A side or bed-wide STOP, a
  disconnect or an unload ends every member, and the next member waits for
  that STOP before a new streamer starts.
- An ordinary command on a streamed motor, such as a preset, replaces the whole
  stream.
- A cleanup or release failure ends the stream and is reported to every member
  it ended.

## Checked actions and STOP

`set_alarm`, `set_position` and `set_positions` capture each selected bed's
STOP epoch before their checks. A STOP while the action still connects or
checks ends it with nothing written; a STOP after the first write skips the
remaining targets. A position seek plans each motor again on the live
controller, and a changed plan raises `bed_changed`. `goto_preset`,
`save_preset`, `rename`, `sync_clock` and `hold_control` check again on the
controller that writes when it is not the one checked first.

## Shown state

Entities show what reached the bed. Each GATT write declares whether it is one
of the running command's frames; connecting, authentication and session setup
never are. Nothing sent keeps the previous state, everything sent shows the new
one, and a command cut off between frames shows unknown.

## Dropped links

- **Release right after each command** and **Always stay connected** do not
  reconnect on a timer: the next command connects.
- **Stay connected for a while** recovers a dropped link once, five seconds
  after the drop, and only inside the window the last command opened. The
  recovered link keeps that window's end. While a command needs the link, it
  reconnects for that command.
- A few persistent connections (such as LP Comfort Connect) reconnect once,
  five seconds after a drop.
- Beds that ask for recovery (Good Vibe with monitoring, Hush sleep sensors)
  retry five seconds after a drop and keep retrying while the bed stays away.
  The first retries come five seconds apart, then the wait doubles after each
  failure, up to five minutes. A successful connect or a new command sets the
  next wait back to five seconds; a retry already scheduled keeps its time.
- A drop ends every hold lease. What the bed itself does when its link drops is
  up to the bed.
- Occupancy polls read only over an open, ready link and never connect.

## When the bed cannot be reached

- A control, or an action past its checks, fails with "The bed is not
  connected. Check that it is powered on and in range, then try again." An
  action's checks report instead that they could not connect to the bed. A
  Bluetooth error that ends a command reads "Bluetooth could not send the
  command to the bed", followed by the error. For dashboard controls and
  automations, Home Assistant logs these as one line, without a traceback.
- The failed connect is logged as one warning per outage, naming the attempts
  and the last error. Repeats go to debug until the bed connects again,
  including the setup retries after a restart.
- After a restart with the bed unreachable, the entry keeps retrying setup and
  has no entities until the bed answers.
