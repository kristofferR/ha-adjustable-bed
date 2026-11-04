# AdjustableM5X5 app

**Status:** ❓ Needs testing (artifact-verified, hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

Select **AdjustableM5X5 app** for the artifact-verified behavior of
`com.starcode.abm5_5` 1.2.3 (version code 6). The generic BOX25 route retains
its other app contracts. ELEVATE lifts use the [DewertOkin ELEVATE](okin-5a.md#dewertokin-elevate)
bed type, which joins this app's lift groups.

## Known Models

- StarCode `STAR25*` beds operated with AdjustableM5X5, in three bed classes:
  CB25, F23 and kneading (see [Detection and setup](#detection-and-setup))
- [DewertOkin ELEVATE](okin-5a.md#dewertokin-elevate) lifts, as members of this app's lift
  groups

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [AdjustableM5X5](https://play.google.com/store/apps/details?id=com.starcode.abm5_5) 1.2.3 (6) | `com.starcode.abm5_5` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Head, foot, lumbar and the exact head + foot union |
| Position Feedback | ✅ Head, foot and lumbar clamped percentages (sliders) |
| Presets | ✅ Flat, Ascent (TV), Zero Gravity, Anti-Snore, Lounge |
| Memory Presets | ✅ M1 / M2 recall and save; save Ascent / Zero Gravity / Lounge; reset saved positions |
| Massage | ✅ Head / foot / wave increase and decrease, toggle / off, 10/20/30-minute timer |
| Lights | ✅ Feedback light on/off, cycle, palette, brightness 1–6, **Light mode 1** |
| Alarm, EQ, sonic and kneading state | ⚠️ Read-only (no reachable setters were established) |
| Lift groups | ✅ One main plus three lifts |

## Protocol Details

**Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e` (Nordic UART)
**Write Characteristic:** `6e400002-…`
**Notify Characteristic:** `6e400003-…`
**Format:** Legacy `05 02 BE32(key) 00` or Star `5a 01 BE32(key) a5`, chosen by the manufacturer read

Required services/roles are Nordic UART `6e400001-b5a3-f393-e0a9-e50e24dcca9e`,
write `6e400002-…`, notify `6e400003-…`, Device Information
`0000180a-0000-1000-8000-00805f9b34fb`, and readable firmware `00002a28-…`.
Optional manufacturer is `00002a29-…`.

### Packet Format

| Builder | Legacy | Star |
|---|---|---|
| Normal key | `05 02 BE32(key) 00` | `5a 01 BE32(key) a5` |
| Extended value | `04 e0 key value 00 00` | `5a e0 04 key value 00 00 a5` |
| Query | `00 b0` | `5a b0 00 a5` |

- Legacy light on/off uses `08 02 00 00 00 00 BE32(key)`, with keys `40` and
  `80`.
- Star bedding keys have high bytes `03 10 30`.
- The delimiter is literal, with no inferred checksum, sequence, encryption or
  fragmentation.
- Dynamic extended fields retain their low eight bits; normal builders retain
  the low 32 bits.

### Write Mode

- RX subscribes before the sender initializes.
- Every write uses **without response**.
- Bleak selects notification/indication subscription from actual properties;
  the Android request for MTU 512 does not establish a mandatory peripheral MTU.

### Dialect selection

- Each manufacturer byte becomes a character, is lowercased and is compared
  **exactly** with `star`. Equal selects the Star dialect; empty, missing,
  failure or other strings select legacy. No substring match or whitespace
  stripping occurs.
- Firmware uses the same character-code concatenation; a failed five-second read
  is explicit diagnostic state. Manufacturer has a one-second read budget.
- No custom PIN or owned bonding call is inferred.

### Session

- Star CB25/F23/kneading enqueue one `5a0b00a5` initialization frame on the
  next 100 ms tick. Legacy CB25/F23/kneading do not unconditionally wake.
- F23/kneading then send local-clock correction.
- RGB query follows settled manufacturer selection.
- Every session owns its callbacks; old subscriptions cannot publish into a
  replacement session.

## Detection and setup

Enter the exact case-sensitive Bluetooth name separately from a friendly name:

| Prefix, in factory order | Profile |
|---|---|
| `STAR254205`, `STAR255401` | F23 |
| `STAR255402`, `STAR255403` | Kneading |
| Remaining `STAR25` | CB25 |

- These names and the shared transport cannot distinguish the app from other
  software. Discovery asks the user to choose the app.
- A name starting `ELEVATE` is rejected here with a pointer to the DewertOkin
  ELEVATE bed type.
- The three bed classes and ELEVATE entries may each occupy either the main or
  an independently addressed lift slot.
- Desk, TV, seating and unknown fallback classes fail the artifact's bedding
  feature guards.

### Home Assistant setup

Select **AdjustableM5X5** (`starcode_m5x5`) and enter the exact Bluetooth name, preserving case. Confirm CB25, F23 or kneading. ELEVATE lifts use the [DewertOkin ELEVATE](okin-5a.md#dewertokin-elevate) bed type instead. The specific F23/kneading prefixes take precedence over generic `STAR25`; shared Nordic UART identifiers alone cannot choose an app. The exact optional manufacturer read selects the command dialect when connecting.

On the main entry, select up to **three other configured AdjustableM5X5 or DewertOkin ELEVATE entries** as lifts. This supports four independent Bluetooth addresses: one main and three lifts. The three bed classes and ELEVATE can occupy either slot; an ELEVATE main selects its lifts in its own options. Duplicate addresses and unrelated products are rejected. This group keeps each device's existing coordinator and entities. It does not convert them into Left/Right paired devices.

Use `adjustable_bed.starcode_move_lifts` for native lift-union movement, STOP or composite flat. A profile or group-selection edit cancels retained delayed writes. Individual controls remain on each physical device.

## Commands

### Motor, presets, memory, massage and light keys

| Action | Legacy key | Star low byte |
|---|---|---|
| Head up/down | `1` / `2` | `00` / `01` |
| Foot up/down | `4` / `8` | `02` / `03` |
| Lumbar up/down | `10` / `20` | `04` / `05` |
| Head and foot union up/down | `5` / `a` | `0c` / `0d` |
| STOP/release | `0` | `0f` |
| Main interrupt | `0` | `1f` |
| Flat / Ascent (TV) / Zero Gravity | `08000000` / `4000` / `1000` | `10` / `11` / `13` |
| Anti-Snore / Lounge / M1 / M2 | `8000` / `2000` / `10000` / `40000` | `16` / `17` / `1a` / `1b` |
| Save Ascent / Zero Gravity / Lounge | `08004000` / `08001000` / `08002000` | `92` / `90` / `91` |
| Save M1 / M2 / reset saved positions | `08010000` / `08040000` / `88000000` | `94` / `95` / `96` |
| Head massage increase/decrease | `0800` / `00800000` | `66` / `67` |
| Foot massage increase/decrease | `0400` / `01000000` | `68` / `69` |
| Wave increase/decrease | `10000000` / `04000000` | `58` / `59` |
| Massage toggle/off | `0100` / `02000000` | `5a` / `6f` |
| Light cycle | `040000` | `70` |

Legacy keys use the normal legacy frame; Star low bytes follow the `03 10 30`
high bytes, for example Head up is `5a 01 03 10 30 00 a5`.

### Lights and settings

| Command | Legacy dialect | Star dialect | Notes |
|---|---|---|---|
| Light on / off | `08 02 00 00 00 00 00 00 00 40` / `08 02 00 00 00 00 00 00 00 80` | Low byte `73` / `74` | F23/kneading always Star |
| Light cycle | Key `040000` | Low byte `70` | F23/kneading always Star |
| Light mode 1, CB25 remotes `252201`, `254202`, `352201` | Key `00020004` | Low byte `7a` | 35 attempts, no extra neutral |
| Light mode 1, other names and F23/kneading | Star `8a` | Star `8a` | Followed by Star `0f` |
| Brightness 1–6 | `04 e0 00 value 00 00` | `5a e0 04 00 value 00 00 a5` | F23/kneading always Star |
| Palette index 0–7 | `04 e0 01 index 00 00` | `5a e0 04 01 index 00 00 a5` | F23/kneading always Star |
| Massage 10/20/30 minutes | `04 e0 07 n 00 00` | `5a e0 04 07 n 00 00 a5` | `n` = 1/2/3; manufacturer-selected framing |
| Status query | `00 b0` | `5a b0 00 a5` | F23/kneading always Star |

- Extended keys `0`, `1`, `7` select brightness 1–6, palette index 0–7 and
  massage 10/20/30-minute choices respectively. No arbitrary RGB or absolute
  massage-intensity setter is inferred.
- F23/kneading RGB on/off/cycle/mode use Star low bytes `73/74/70/8a`, and their
  brightness, palette and query always use Star framing. Other inherited
  controls keep manufacturer selection.
- For CB25, only names longer than 14 characters provide remote substring
  `[4:10]`. Remotes `252201`, `254202`, `352201` send mode 1 for 35 attempts,
  using legacy `00020004` or Star `7a`, without an extra neutral. Other names
  use Star `8a` followed by Star `0f`, including legacy sessions. F23/kneading
  always use that overridden mode path.

### ELEVATE class

The app's ELEVATE class uses Star low bytes `40/41` for actuator 1, `42/43` for
actuator 2, `44/45` for both, `46` for one-shot flat, `0f` STOP and `4f`
interrupt, the same table as the released [ELEVATE](okin-5a.md#dewertokin-elevate)
controller. That bed type now carries these vectors and the group behavior
below.

## Command Timing

- Commands run on the next available **100 ms** sender tick, with one write in
  flight. No configurable delay replaces the artifact's cadence.
- Held app actions become bounded HA pulses and remain cancellable. Movement
  always releases with a fresh STOP event; relative massage adds the
  manufacturer-selected **base** query after neutral, including on
  F23/kneading.

| Action | Repeats | Release |
|---|---|---|
| Recalls | Three copies | Neutral |
| Ordinary light/massage toggle/off | Two | Neutral |
| Timer, palette and brightness | One | Neutral |
| F23/kneading light overrides | One | **Star** neutral, independent of the movement dialect |
| Five named/memory saves and reset | 55 attempts after STOP | Safe release cleanup |

Completion means awaited transport delivery, never proof of physical motion or
retained memory.

## Feedback and public controls

Head, foot and lumbar reports are clamped percentages; the other three raw
progress slots remain diagnostics, not invented axes. HA exposes their confirmed
percentage sliders and exact union control. No dead direct-position packet is
enabled.

| Frame | Safe minimum | State |
|---|---:|---|
| `a5/0d` | 18 | Positions at 4/6/8; raw parts at 10/5/7; stopped when byte 17 is zero |
| `a5/0b` | 20 | Normal massage, RGB, and distinct sonic feedback |
| CB25 `a5/0c` | 17 | Main alarms, second slot only in Star dialect |
| F23/kneading `a5/0c` | 25 | Two advanced alarm records |
| F23/kneading `a5/0e` | 22 | EQ, volume/preset, frequency offsets and USB state |
| Kneading `a5/0f` | 8 | On/demo, mode clamped to 0–2, raw time |

### Massage, sonic and alarm state

- Normal massage active uses OR of the encoded level nibbles; sonic active uses
  AND.
- Sonic frequency labels are 30 for raw 5, 40 for 9, otherwise 50 when either
  level is nonzero, and zero when both are zero.
- Normal, sonic and kneading time values stay **raw**, without invented physical
  units. Alarm repeat and hour/minute values remain raw; typed alarm attributes
  retain the exact enums and slot layout.
- EQ magnitudes/signs, raw volume, USB bit and prior sonic fields are retained.
- These alarm/sound/sonic/kneading domains are read-only because no reachable
  setters were established.

### RGB state

- RGB palette values are white, red, orange, yellow, green, blue and purple.
- Wire indices 0–7 map through `max(index-1,0)`; larger nibbles use bytes 16–18
  as direct RGB and select the nearest palette by RGB distance.
- HA reports that nearest palette color in the same wire numbering the palette
  select writes (0 off, 1 white through 7 purple), so a direct white reads as
  `1`, not off.
- Diagnostics expose the original/direct branch, RGB value, light mode and raw
  index. The physical meaning of index 7 still requires real-user validation.

### Notification handling

- Changed notifications are processed even within 200 ms. Short frames cannot
  publish a partial domain or crash.
- F23 receives base motor/normal state and independently applies sonic,
  advanced alarm and EQ handlers; kneading adds its own handler. It does not
  inherit the sibling CB25 main-alarm layout.
- No optimistic requested setting replaces received state.

### Light control

- One feedback light owns on/off control, without a duplicate under-bed-light
  switch.
- Toggle uses the last observed state to choose the exact discrete on/off
  command; unknown or disconnected feedback requires an explicit turn-on or
  turn-off action. Native toggle packets from other app profiles retain their
  own behavior.
- The Flutter Home page's RGB listener can request mode 1 from the currently
  selected main controller. HA replaces that page-selection behavior with the
  explicit **Light mode 1** action, preserving its exact builders and repeat
  counts. Received light state remains feedback; an old emitter cannot retarget
  a replacement controller or trigger a write merely because a page used to be
  visible.

### Session ownership

- Startup checks session ownership after every read and initialization await,
  so a disposed or replaced session cannot revive the sender.
- Read results stay local until ownership is checked before publication.
- Queued writes retain their original client and generation through sender-tick
  and BLE-lock waits; superseded work cannot emit packets into a replacement
  session or overwrite its firmware diagnostics.

## One main plus three lifts

Configure up to three other AdjustableM5X5 or DewertOkin ELEVATE entries on the
main entry. An ELEVATE main selects its lifts in its own options. This supports
**four physical targets**, one main plus three lifts, each with its own BLE
coordinator.

- Use `adjustable_bed.starcode_move_lifts` with `up`, `down`, `flat` or `stop`.
- Each lift may be any of the three bed classes or an ELEVATE; lift fanout uses
  only native union movement, STOP/interrupt and flat. An ELEVATE main keeps its
  individual actuator controls.

### Readiness and interrupts

- All selected targets must be ready before group writes.
- Individual main movement interrupts reachable ready lifts; individual lift
  movement interrupts its reachable ready main.
- Unloaded, disconnected or unready peers, and peer write failures, do not block
  a healthy individual control. Related pending group admissions are cancelled
  before peer writes, without requiring an offline peer to reconnect.
- Dedicated group movement still requires every selected member to be ready.
  Movement admission still requires the complete selection to be ready.

### Composite flat and cleanup

- Composite flat interrupts the group, sends main flat, waits **1600 ms**, then
  sends lift flat.
- Every target's connection is held through dispatch, delay and cleanup,
  including with Disconnect After Command enabled.
- STOP, changed selection, lost transport, replacement
  coordinator/controller/client/session or unload cancels delayed writes.
- Failure/cancellation cleans every admitted target.
- Group STOP first cancels retained delayed operations and attempts STOP on
  every reachable configured member, even if the main or another lift is
  unavailable. It reports missing members or transport errors after attempting
  the remaining targets.
- Successful Elevate flat receives no invented immediate STOP.
- Grouping does not transfer entity/device ownership into the Left/Right paired
  registry, and never fans out RGB, massage, programming or firmware updates.

## Group ownership and profile changes

A configured main and its selected lifts retain their standalone entry IDs.
Remove the lift selection before combining any group member into a Dual Bed.
The pairing picker rechecks this ownership when a previous selection is submitted.

- A replacement group action waits for prior commands and their native STOP
  cleanup on every shared member before claiming its targets. Cancelling a
  waiting replacement leaves that cleanup running and admits no new writes.
- Explicit group or individual STOP also invalidates pending admission,
  including during connection preflight.
- Changed selection or unloaded members are rechecked before scheduled actions;
  internal cleanup STOP does not invalidate the intended replacement.

Group-command suppression applies only while the exact scheduled group action
runs.

- A later ordinary command on the same scheduler still interrupts the group,
  cancels its retained delayed movement and cleans up the admitted targets.
- An individual command waits for those STOPs before scheduler admission, so old
  cleanup cannot cancel its new movement.
- Caller cancellation leaves old cleanup running; explicit STOP, changed
  selection, unload or a newer individual request invalidates a waiting
  admission.
- Failed cleanup on an unavailable peer does not block the healthy individual
  target.

## Notes

### Evidence and deferred validation

The full [225-item disposition ledger](../apk-analysis/row005-dispositions.md)
binds implementation and exclusions to code and executed tests. All 111 owned
command rows, 138 inherited command routes, accepted packet/parser vectors and
exhaustive enum branches have focused tests. Raw APKs, decompilation and frozen
reports stay machine-local.

Real users after beta/release can validate five physical domains:

1. Movement/release and programming duration
2. Units/actuator mapping
3. Palette/brightness/modes
4. Manufacturer/GATT/session observations
5. Multiple-device interrupt/flat/feedback behavior

Hardware is not needed to complete the proven static implementation. Actual
peripheral write delivery, actuator cessation, negotiated MTU and the physical
meanings of raw fields remain separately unverified.
