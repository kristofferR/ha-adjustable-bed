# Svane Remote

**Status:** ❓ Needs testing (Svane Remote 1.8 profiles are artifact-verified; physical hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Svane adjustable beds with the "Svane Bed" BLE name (LinonPI controller)
- JMC400 beds (also in the Svane app), through the explicit P2 JMC400 profile
- Jensen LinOn beds ("Adjustable Bed"/"Jensen Bed") share these services but use
  the Jensen app's own frames: protocol variant `jensen_linon`, described in the
  [Jensen guide](jensen.md#linon). The separate [Jensen](jensen.md) and
  [Jensen LinOn](jensen.md#linon) profiles retain their own behavior.
- Svane is a Norwegian bed manufacturer; its beds are primarily sold in
  Scandinavia. "LinON" appears to be Svane's internal name for its bed
  controller; it is not related to Linak despite the similar-sounding name.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Svane Remote](https://play.google.com/store/apps/details?id=com.svane.svaneremote) **Version 1.8 (8)** | `com.svane.svaneremote` |

The app has two explicit BLE profiles. Earlier pre-audit analysis of this protocol
used the package `com.produktide.svane.svaneremote`.

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (2 app axes: head/backrest and feet/seat+footrest) |
| Combined movement | ✅ (four head/feet combinations; separate `timed_move` calls on head and feet run together) |
| Hold until release | ✅ (renewable `timed_move`) |
| Position Feedback | ❌ (opaque raw bytes as diagnostics only; no angles or sliders) |
| Memory Presets | ✅ (2 host slots: Read and TV) |
| Svane Position | ✅ (one-shot; Flat, Zero-G or Anti-Snore meaning unproven) |
| Flat Preset | ❌ (dormant firmware command, not reachable) |
| Under-bed Lights | ✅ (on/off, 5-100 intensity, held adjust; assumed state) |
| Massage | ❌ |
| Device information | ✅ (firmware, hardware, manufacturer diagnostics) |

- The two axes keep the integration's existing `back` and `legs` cover keys.
- Physical actuator count and numeric position units are unknown.
- There are no measured-angle sensors or position sliders.

## Protocol Details

**Service UUIDs:** `abcb` (head), `c258` (feet), `d07b` (lamp), `1234` (P2/old), `180a` (DIS), `f92a` (software)
**Write Characteristic:** P1 role per service (table below); P2 `1234/1111`
**Notify Characteristic:** `1234/1111` (old role, subscribed on both profiles)
**Format:** P1 2-byte writes to direction-specific characteristics; P2 6-byte frames on `1111`

All short UUIDs expand to `0000xxxx-0000-1000-8000-00805f9b34fb`.

P1 uses a **multi-service architecture**: each motor has its own BLE service with
direction-specific characteristics, unlike most beds, which use a single service
with command bytes. Roles are resolved by **service and characteristic**, because
direction and position UUIDs occur in both axis services. The controller must
write to the correct service to control the intended motor.

### GATT roles

| Service | Characteristic | Role |
| --- | --- | --- |
| `abcb` | `01ac`, `bae9`, `143d`, `fb6e` | Head up, down, opaque position, Svane position |
| `c258` | `01ac`, `bae9`, `143d` | Feet up, down, opaque position |
| `d07b` | `a8e0`, `b5e9`, `3fb2` | Lamp intensity/on/off, increase, decrease |
| `1234` | `1111` | P2 commands and opaque position; normal initialization also uses this role on P1 |
| `180a` | `2a26`, `2a27`, `2a29` | Firmware, hardware, manufacturer observations |
| `f92a` | `a592` | Normal software query `040000000000` |

### Write Mode

- Writes require an advertised write property.
- HA prefers write without response when advertised, otherwise uses the
  advertised write-with-response mode. This is a host delivery policy; the APK
  inherits Android's characteristic write type.
- Missing, ambiguous or nonwritable command roles fail before a guessed fallback
  write.

### Initialization

1. The app waits 100 ms after its connection callback before discovery. Bleak
   owns service resolution during connection; the controller retains a 100 ms
   initialization pause before its application reads.
2. Normal initialization subscribes to old `1234/1111`, even on P1, then submits
   the software query to `f92a/a592`. Host subscription completion precedes the
   query. Supported notification roles use the backend subscription API, which
   owns CCCD writes.
3. Initial descriptor state advances to the feet position read, followed by the
   old role read.
4. In the background, the controller reads firmware, waits one second, reads
   hardware, waits one second, reads manufacturer and waits one second.

- The paced reads run after the subscription, so they do not delay the first
  command, and a failed read never fails the connection. Completed fields survive
  a later read failure within the physical target's process session.
- Missing old notification support is reported as unavailable, rather than
  reproducing the app's null dereference. A failed subscription (for example a
  proxy without a free notification slot) is reported as failed and keeps motor
  control.
- Explicit refresh/save reads head then old, followed by feet then old. Every
  present pair is attempted in order even if an earlier read succeeds or fails.
- Connection, metadata and successful submissions do not prove authentication or
  hardware acknowledgement. The query has no inferred response decoder.
  **Refresh Device Information** exposes the normal reads again.

## Detection / Setup

| Configuration | App route | Endpoint |
| --- | --- | --- |
| `auto` (shown as **Svane Remote app (multi-service)**), or an older Svane entry without a variant | P1 multi-service | Exact head, feet and lamp roles above |
| `svane_remote_jmc` | P2 JMC400 | `1234` / `1111` |
| `jensen_linon` | Jensen Adjustable Sleep | Separate one-byte controller |

- Bed-type detection uses the head service `0000abcb-0000-1000-8000-00805f9b34fb`
  or a name containing `Svane Bed` or `Jensen Bed` (case-insensitive), so renamed
  beds such as "Svane Bed 2" still detect.
- Choose **Jensen / Svane** in the bed-type list and answer the
  [app and bed question](jensen.md#home-assistant-setup). For a scanned name
  containing case-sensitive `JMC`, the question suggests the JMC400 profile,
  following the app's own name rule, in Bluetooth and manual setup alike.
  Existing entries retain their stored variant; **Reconfigure** changes it.
- The source's individual discovery names are exactly case-sensitive `Svane Bed`
  and `JMC400`; its selected-name rule uses case-sensitive `JMC` to choose P2.
- The shared JMC name and service also occur in the Jensen route and do not prove
  this app's features.
- HA accepts a known address with an explicit profile, including a changed
  advertising name.
- No PIN, pairing, model inference or manufacturer filter is introduced for
  Svane Remote.
- Motor-count, angle sensing, massage and repeat-count settings are hidden for
  these app profiles.

## Commands

### Motor Control (P1)

Written to the direction characteristic in the axis's own service.

| Command | Service | Characteristic | Bytes |
|---------|---------|----------------|-------|
| Head up | `abcb` | `01ac` | `0100` |
| Head down | `abcb` | `bae9` | `0100` |
| Feet up | `c258` | `01ac` | `0100` |
| Feet down | `c258` | `bae9` | `0100` |
| Release | same started role | same started role | `0000` |

### Motor Control (P2)

Written to `1234/1111` as `10 MASK 00 00 00 00`.

| Command | Mask | Frame |
|---------|------|-------|
| Head up / down | `01` / `02` | `100100000000` / `100200000000` |
| Feet up / down | `10` / `20` | `101000000000` / `102000000000` |
| Head up + feet up / down | `11` / `21` | `101100000000` / `102100000000` |
| Head down + feet up / down | `12` / `22` | `101200000000` / `102200000000` |
| Release and global STOP | none | `100000000000` |

### Presets

| Command | Profile | Destination | Bytes |
|---------|---------|-------------|-------|
| Svane position | P1 | `abcb/fb6e` | `0300` |
| Svane position | P2 | `1234/1111` | `108100000000` |

### Memory

| Command | Profile | Destination | Bytes |
|---------|---------|-------------|-------|
| Recall | P1 | `abcb/143d`, then `c258/143d` after one second | Stored opaque head, then feet arrays |
| Recall | P2 | `1234/1111` | `1004` + stored four bytes (defaults: Read `81388113`, TV `82738204`) |

Save sends no firmware save opcode; it copies bytes from successful reads.

### Lights

| Command | Destination | Bytes |
|---------|-------------|-------|
| On / set intensity | P1 `d07b/a8e0`; P2 `1234/1111` | `13 02 (JavaInt & ff) 01 00 64` |
| Off | P1 `d07b/a8e0`; P2 `1234/1111` | `130200000000` |
| Held increase / decrease | P1 `d07b/b5e9` / `d07b/3fb2`; P2 `1234/1111` | Intensity builder with the new level |

The builder is not clamped to 100.

### Information

| Command | Destination | Bytes |
|---------|-------------|-------|
| Software query | `f92a/a592` | `040000000000` |

### Dormant commands

The old dormant `3fff`, `3f40`, `3f80` and `3f81` writes are not reachable
controls in this profile. Earlier versions of this guide described them as read
position, save position, recall position and flatten.

## Command Timing

- Head and P2 combined actions start immediately and schedule the next pass
  100 ms after work.
- Feet-only and P1 separate-axis fallback wait 100 ms before feet, then schedule
  another 100 ms after work.
- These are held refreshes, not a source fixed repeat count.
- Ordinary cover actions use a bounded one-second host duration.
- Generic `timed_move` streams the selected axis (#516) for the caller's
  elapsed ceiling, with the same native cadence and cleanup. Calls on head and
  feet run together: P1 refreshes head at the start of each 100 ms pass and feet
  100 ms into it; P2 sends one mask carrying both. A renewable hold lease
  ([Renewable holds](../SERVICES.md#renewable-holds)) keeps an axis moving until
  the lease runs out. A new head press is written at once and never delays
  feet's next refresh, so pressing head again and again cannot stall feet.
- All selected targets validate before dispatch, including the existing
  delayed-feet minimum; the explicit service accepts 0.1–60 seconds. Feet-only
  actions and P1 combinations require more than 0.1 seconds.
- If awaited writes or scheduling consume that remaining budget before the
  selected feet axis starts, the action reports an error and releases any started
  head role instead of reporting a successful incomplete combination.

### Release

- P1 releases with `0000` to the same started role. Host STOP attempts every
  started direction, including downward movement. There is no invented global P1
  destination.
- P2 final held-motion release and explicit global STOP use `100000000000` on
  `1234/1111`. Explicit STOP sends this frame even when no held role is tracked,
  including during or after a memory recall.
- Releasing one axis while the other remains active removes its mask and
  continues the remaining refresh without an immediate global STOP. When two
  `timed_move` calls stream together, the axis that ends first gets its own
  release: P1 sends `0000` to its started role, P2 sends the mask without it.
  The last axis out gets the normal release: P1 its role's `0000`, P2 the
  global STOP. `svane_release_axis` and a cover's own Stop end only that axis.
- Cancellation and an explicit axis release remain normal exit paths.
- Cancellation, failed writes and controller detach attempt the actual movement
  releases independently of the cancelled event.
- P2: failed or cancelled delivery retains that role for retry.
- A failed or cancelled release keeps its started role pending for the next
  serialized STOP; a successfully released role is retired.

## Actions

- `adjustable_bed.hold_control` offers `head_up`, `head_down`, `feet_up`,
  `feet_down`, the four corresponding `head_*_feet_*` combinations, and
  `light_adjust`.
- All selected profiles and live roles are validated before the first motion.
  Paired physical sides retain their own P1/P2 routes.
- `adjustable_bed.svane_release_axis` signals the active writer to release `head`
  or `feet`; it performs no separate BLE write outside command serialization.
  Global STOP still cancels and releases the whole action.
- A public hold captures each physical session's release boundary before
  connection preflight and scheduler admission; a later acknowledged axis release
  survives those waits and controller reconstruction. Earlier idle releases do
  not cancel a new hold.
- Generic timed movement validates static duration/profile constraints on
  disconnected capability controllers, then reconnects and validates every
  selected live GATT role before any movement.

## Memory and presets

- The **Svane position** action keeps the `preset_zero_g` button ID that existing
  entries use. The artifact does not prove a Flat, Zero-G or Anti-Snore meaning.
- Preset, lamp and memory actions do not append movement STOP.
- The two source-labelled positions are **Read** and **TV** (public numbered
  memory slots 1 and 2).
- Save copies valid bytes from successful reads in its own head/old/feet/old
  refresh sequence. Missing, failed, empty or cancelled required reads leave the
  old slot intact instead of copying an earlier observation. Completed diagnostic
  observations remain available even when save fails.

### P1 slots

- P1 copies the entire opaque head and feet arrays. Recall writes head bytes to
  `abcb/143d`, waits a cancellable second, then writes feet bytes to `c258/143d`.
- Length and endian interpretation are not invented.
- The app keeps these slots only in process memory; HA persists the saved bytes in
  the entry's Svane preferences, so they also survive a restart. Each app profile
  keeps its own stored preferences, so changing profile and back restores them.

### P2 slots

- P2 copies bytes 2–5 of a valid target position record.
- Slots persist per physical target, with source defaults Read `81388113` and TV
  `82738204`. Recall sends `1004` plus the stored four bytes.
- Missing observations and malformed preferences produce an unavailable/validation
  error, never a null overwrite or dormant command fallback.

### Validation and STOP

- Generic memory services and the paired parent's combined Memory button validate
  every selected target before dispatch. An unsaved P1 slot or malformed stored
  payload rejects the whole call before an earlier target can move; the
  controller still checks the slot during locked execution.
- A mixed P1/P2 pair recalls each physical target's own saved bytes after both
  slots pass validation.
- Normal recall still appends no STOP. P2's explicit global STOP can interrupt
  recall independently of held-motion tracking.
- P1's opaque absolute-position recall has no proven STOP on its position
  characteristic and supplies no direction to select a directional release. Host
  STOP cancels a pending feet write during the one-second gap, but does not claim
  to halt a head recall already delivered. The integration does not guess a
  direction or write a fabricated STOP to the position characteristic.
- Idle notification teardown does not append a global STOP; started held-motion
  roles still receive their proven cleanup.

## Lamp

- Cold app-local lamp intent is off, remembered intensity is 90 and adjustment
  direction starts +5.
- The literal toggle sends remembered intensity on, or `130200000000` off.
  Explicit HA ON/OFF resends its requested branch.
- The switch remains unknown until an explicit lamp command, including attempted
  failed or cancelled delivery; that knowledge is process-local and survives
  same-target/profile reloads, while cold restart or profile reset loses it.
  Subsequent optimistic values are assumed; there is no native physical
  lamp-state feedback.
- Lamp intensity is a persisted local preference, exposed through the established
  0-100 light level slider so existing entries keep their entity. Setting 0 turns
  the lamp off; other values snap to the app's 5-100 steps of five and command the
  lamp on.
- Action buttons, the light level number and the assumed-state switch share that
  local intent. Intent is published before delivery and remains local command
  intent after a failed or cancelled write, not physical readback.
- Full signed-32-bit boundary vectors test the intensity builder, while the public
  control accepts the source user-step domain.

### Held adjustment

- The frozen app's held adjustment begins after more than 200 ms while local
  intent is on. It unconditionally reverses step at current intensity >=100 or
  <=6 before adding five: 90→95→100→95, and 10→5→10.
- The held HA control accepts the same 5–100, step-five range as the intensity
  number. At 5 or 100 it reverses only an outward step; an inward retained step
  continues toward the interior. This preserves valid HA local preferences after
  direct selections without broadening native builder inputs.
- It refreshes every 100 ms after work. Release ends the refresh without OFF or
  STOP.
- Local intent changes before each attempted delivery and survives write failure.
  Held adjustment persists changed final preferences once on exit, including
  failure or cancellation; neither is a hardware observation.

## Notifications / State

- Diagnostic sensors expose completed firmware/hardware/manufacturer and opaque
  head, feet and P2 position bytes with separate observation timestamps.
- DIS has dispatch precedence.
- Exact axis `143d` responses preserve whole nonempty buffers.
- Exact old `1111` records require at least six bytes and first byte `10`,
  preserve bytes 2–5 and ignore byte 1.
- Unknown roles, empty and short records are rejected.
- Raw records, stored slots and successful writes do not become angles,
  percentages, capability flags or hardware state.

## Paired beds and profile changes

- Physical-side caches survive paired parent ownership migration and separation.
- A profile change starts a new session for the changed physical target. The
  persisted preferences of every profile are kept, so switching back restores
  that profile's slots and intensity.
- A shared options form cannot change a Svane profile across two separate
  addresses: unpair and configure each side separately first.
- Common options and an unchanged rendered profile preserve mixed P1/P2 routes
  and target-local caches.

## Notes

- Earlier versions of this guide marked the previous LinonPI implementation
  ✅ Tested; the current app profiles have not been validated on physical
  hardware. Physical captures are deferred to real users after beta/release.
- Classic RFCOMM, firmware updates, dead builders, phone-only functions and
  precise unsafe source fragments remain excluded. Earlier analysis identified
  the app's Classic Bluetooth route as OKIN-i devices, which this BLE integration
  does not support.

### Analysis provenance

See the [complete disposition ledger](../apk-analysis/dispositions/row130-svane.md)
for all 663 rows and every exclusion.
