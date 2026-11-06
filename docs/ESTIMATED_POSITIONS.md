# Estimated Positions and Saved Positions

Some beds cannot report where their motors are. For a few of them the
integration can estimate a motor's position from how long it has moved, and
save named positions that you can recall later. This is opt-in per motor and
never replaces real position feedback.

## Estimated Versus Measured

A **measured** position comes from the bed. Beds with position feedback report
angles or percentages, and the integration shows them as they are.

An **estimated** position is a calculation. You time how long each motor takes
to travel fully up and fully down. Starting from flat, the integration adds up
every movement it sends and converts the time into a percentage of full travel.
50% means "moved for half of the full raising time", not half of the maximum
angle. The estimate is always labelled: entity names end in "(estimated)", and
the card shows "≈ 42%".

Estimates drift. Motor speed changes with direction, position and load, and
many short taps add small timing errors. Expect a few percent difference when
you recall a saved position. Set the reference again from time to time, for
example when the bed is flat at night.

## Supported Beds

| Bed | Estimated motors |
|-----|------------------|
| [OCTO Smart Control](beds/octo.md) (Standard variant) | TV lift, back, legs, head and feet; the combined steps update every motor they move |
| [Richmat](beds/richmat.md) remote-code profiles | Head and feet; the combined head and feet step updates both |

A motor qualifies only when its protocol has reliable directional movement and
its own STOP. Other beds may follow once that is established for their
protocol. Where motors run together (concurrent `timed_move` calls), each
motor's estimate counts from the first frame that moves it to the frame that
stops it, so motors that stop at different moments each get their own time.
Beds with position feedback do not need it.

A paired bed with two Bluetooth addresses is supported, and each side is
calibrated on its own. No single-address paired bed (one controller with Left
and Right sides behind one address) supports estimates yet. Only the OCTO
Standard and Richmat remote-code controllers declare estimated motors, and
neither forms a single-address pair. A single-address family becomes eligible
only after accepted protocol audit evidence proves its STOP and release
behavior.

## Setting Up

For a TV lift, the zero reference is fully lowered, and 100% is fully raised.
Calibrate its raising and lowering times separately. The lift has no measured
height feedback: remote movement and restarts require the same reference
confirmation as bed motors. It remains a standalone device. Saved positions
can be named, for example, **TV open** or **TV closed**.

Open **Settings > Devices & services > Adjustable Bed**, select **Configure**,
then **Estimated positions**. A paired bed with two addresses has one entry per
side, and each side is calibrated on its own.

1. **Choose motors.** Tick the motors to estimate and confirm that you
   understand positions are estimated. Motors whose protocol has no proven stop
   are listed as not offered.
2. **Bring the motor to flat.** Lower it with the card or the remote, or choose
   **Lower it for me** and select **It is flat now** once it stops. Only you can
   confirm flat.
3. **Raise.** The motor moves up from flat. Select **Reached the top** the moment
   it stops moving.
4. **Lower.** The motor moves down. Select **Reached the bottom** the moment it
   stops.
5. Steps 2 to 4 repeat for every chosen motor.
6. **Review.** The measured seconds are editable. Tapping adds a small delay, so
   fine tune them here, or type times you measured with a stopwatch.

Each time runs from the motor's first movement command. Every calibration
movement stops by itself after 60 seconds, **Stop, something is wrong** stops
it at once, and closing the dialog stops it too. Cancelling keeps your previous
motors and times, but a motor you started measuring needs its reference set
again, because it may have moved. Motors you just measured end flat, so their
reference is set and they start at 0%, unless something moved them before you
saved. Typed times alone set no reference: set it when the bed is flat.

To recalibrate, open **Estimated positions** again and keep **Measure travel
times now** ticked. Saved positions keep their percentages. To turn the feature
off, clear every motor.

## Physical Validation

Hardware status: unverified. Proven offline: tests cover the timing arithmetic
in both directions, STOP and cancellation, failed writes and lost links,
invalidation by presets and **I used the remote**, restoring after a restart or reload,
saved positions, recall, lowering to flat, independent paired sides and every
calibration step, including a real OCTO Standard entry. Needs real-bed reports
on OCTO Standard and Richmat beds: how close a recall lands to the saved
position, how fast the estimate drifts over many short moves, and whether
calibrating by tapping is accurate enough. Report the target, what the bed
actually did and your calibrated times in the v5 beta feedback issue.

## States

| State | Meaning | Entity state | Saved positions and sliders |
|-------|---------|--------------|-----------------------------|
| Tracking | Calibrated, the reference is set, and every move since went through the integration and finished | The percentage | Work |
| Unconfirmed | An estimate restored after Home Assistant restarted. Nothing proves the bed is still there | `unknown`, with `last_estimate` | Paused |
| Unknown | No trustworthy estimate | `unknown` | Paused |
| Not calibrated | Enabled, but a travel time is missing. Finish the calibration in Settings | `unavailable` | Paused |

Hold-to-move up and down always works, in every state. It moves relative to
where the bed is and needs no estimate. Pressing STOP during a move keeps the
estimate tracking, because the integration knows when the move ended.

These make an estimate unknown, because the integration cannot tell where the
bed stopped:

- a movement write that fails, or a connection that drops mid-move;
- a hardware preset or a memory recall, including the bed's Flat preset;
- any movement the integration does not time;
- pressing **I used the remote**.

The integration never sees the physical remote or the bed's own app. If you use
them, press **I used the remote** so nothing acts on an outdated estimate.

## Recovering the Reference

Flat is the only reference. To recover:

- **After a restart**, if the bed has not moved, use **It hasn't moved**
  (the `confirm_position_unchanged` action). The restored estimate becomes
  tracking again. It is never trusted on its own.
- **When the bed is flat**, press **Set back reference** (one button per
  motor), or use `set_position_reference`. The estimate starts again at 0%.
- **When you are not sure**, use **Lower to flat, then I confirm**
  (`lower_to_flat`). The motors lower for their full travel time plus a margin.
  Check that the bed is flat, then set the reference. The bed only lowers when
  you ask, and it never confirms flat by itself.

Reloading the integration, for example after changing options, keeps tracking
estimates tracking. A Home Assistant restart does not.

## In the Card

The Adjustable Bed card shows estimates in its **Position** rows as "≈ 42%", with
an **Estimated** chip on the section heading. When you have set a maximum angle
for the back or legs in the options, the bed graphic draws the estimate dashed
and translucent, so it never looks like measured feedback. With the card's
[percentage graphic](CONFIGURATION.md#dashboard-card-graphics-and-dialog) on,
it draws every estimate as a percentage pose: "≈ 42%" while tracking, grey with
"Was ≈ 42%" when unconfirmed, and faint, flat and "?" when unknown. A compact
card's readouts label estimates the same way, with or without the graphic.

An alert at the top of the card explains when an estimate cannot be trusted:

- **Calibrate now**, when estimated positions are on but not calibrated. It
  opens Settings, where the calibration runs.
- **Position unconfirmed after restart**, with the last estimate, plus **It
  hasn't moved** and **Set reference…**.
- **Position unknown**, with the reason and **Set reference…**.

**Set reference…** opens a dialog: the bed is flat now, lower to flat and then
confirm, or one motor only. The bed only moves when you choose to lower it, and
you confirm flat afterwards.

The **Saved positions** section lists your saved positions. Tap one to recall
it. Tiles are disabled while a side they cover is not tracking. **Save…** names
the current position and offers the optional button entity. **Edit** lets you
rename, update to the current position, show or hide the button, or delete.
On a paired bed, the **Both** tab saves both sides and lists every position
with "Both sides", "Left only" or "Right only"; the **Left** and **Right** tabs
save, list and edit only the positions saved for their side. You can hide the section in the card editor.

## Entities

For every estimated motor:

| Entity | Purpose |
|--------|---------|
| `number.<bed>_back_position_estimated` ("Back position (estimated)") | The estimate as 0-100%. Setting it moves the motor for the calculated time. Attributes include `estimate_state`, `estimate_reason`, `last_estimate`, `reference_at`, `full_travel_up_s`, `full_travel_down_s` and `moves_since_reference` |
| `button.<bed>_set_back_reference` | Confirms the motor is flat now |

For every estimated bed, or each side of a paired bed:

| Entity | Purpose |
|--------|---------|
| `button.<bed>_i_used_the_remote` | Marks every estimate of that bed or side unknown |

For the whole bed:

| Entity | Purpose |
|--------|---------|
| `sensor.<bed>_saved_positions` | The number of saved positions, listed in its `positions` attribute |
| `button.<bed>_<saved position>` | Recalls one saved position. Created only when you choose to |

## Saved Positions

A saved position stores the current estimate of every calibrated motor. Saving
requires every included motor to be tracking. Recalling one moves each motor,
one after the other, for the calculated time. It needs every motor it covers to
be tracking and the bed to be still, and it reports an error when STOP or a
failure left a motor short of its target. On a paired bed, a failure on one
side stops the other side too.

Saved positions are not the bed's hardware memory, and saving one does not
change anything on the bed.

On a paired bed, a position saved for both sides stores both sides and needs
both sides tracking to recall. A position saved for the left or right side
stores and moves only that side. Each side has its own calibration and estimate.

## Actions

Every action takes `device_id`, and `side` where it applies to a paired bed. See
[Targeting a Bed or Side](SERVICES.md#targeting-a-bed-or-side).

| Action | Fields | Behavior |
|--------|--------|----------|
| `save_position` | `name`, optional `create_button` (default on) | Save the current estimates. Returns `position_id` |
| `rename_position` | `position`, `name`, optional `create_button` | Rename, and show or hide the button entity |
| `update_position` | `position` | Replace with the current estimates of the sides it covers |
| `delete_position` | `position` | Delete it and its button |
| `recall_position` | `position` | Move to it |
| `set_position_reference` | optional `motors` | Confirm flat now |
| `confirm_position_unchanged` | None | Trust a restored estimate |
| `mark_position_unknown` | None | Same as **I used the remote** |
| `lower_to_flat` | optional `motors` | Lower past full travel; confirm flat afterwards |

`position` accepts a saved position's name or its ID. Selecting one side of a
paired bed limits the position actions to positions saved for that side.

```yaml
action: adjustable_bed.recall_position
data:
  device_id: 0123456789abcdef0123456789abcdef
  position: Reading
```
