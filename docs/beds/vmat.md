# VMAT (Vibradorm)

**Status:** ❓ Needs testing (app behavior artifact verified, physical operation unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Vibradorm receivers controlled with the VMAT app (`de.vibradorm.vmat`)
- The fourteen shipped VMAT remote selections in the
  [remote table](#setup-and-remote-selection). Resource names identify shipped
  images, not proven physical products.
- Generic [Vibradorm](vibradorm.md) entries keep their existing controller.
  [Caresse / Werkmeister](vibradorm_app.md) and [V-MAT Basic](vmatbasic.md) have
  their own independent feature gates, vectors and dispositions.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [VIBRADORM Remote](https://play.google.com/store/apps/details?id=de.vibradorm.vmat) (VMAT) 1.11 (49) | `de.vibradorm.vmat` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (logical groups per remote; All Up/All Down) |
| Position Feedback | ❌ (no live position parser proven) |
| Memory Presets | ✅ (six slots on remotes 07–11 and 13) |
| Sync | ✅ (remotes 07–11, reply-gated held action) |
| Floor light | ✅ (level 0–8 and timer on remotes 01, 04–10) |
| Mood light | ✅ (remotes 12/13: 18 palette choices, three effects, speed 0–8) |
| Massage | ✅ (remotes 12/13: automatic/individual modes, zones, waves, speed) |
| Named presets / Flat | ❌ (All Down is movement, not a timed flat preset) |
| Battery, firmware update, calibration | ❌ (not proven) |
| Hold until release | ✅ ([renewable](../SERVICES.md#renewable-holds) `timed_move` and `hold_control`, through the Vibradorm app profile) |

## Protocol Details

Vendor UUIDs use `0000XXXX-9f03-0de5-96c5-b8f4f3081186`; DIS uses standard
service `180a` and characteristics `2a24`, `2a26`, `2a28`.

| Role | UUID | Property | Required for |
|------|------|----------|--------------|
| Control service | `1525` | | Every remote (exact service) |
| CBI | `1550` | Write without response | Every remote |
| Response | `1551` | Notify | Every remote |
| COMMAND | `1526` | Write with response | Basic profiles |
| LIGHT | `1529` | Write with response | Basic profiles, even without floor UI |
| Management service / characteristic | `1527` / `1533` | Existence only | Setup |
| DIS model / firmware / software | `2a24` / `2a26` / `2a28` | Read | Setup |

Basic profiles are the control-type 2 remotes (00–06 and 12); the other remotes
move through CBI.

**Format:** P1 big-endian 16-bit CBI opcodes; one-byte COMMAND for basic movement

### Packet Format

- P1 uses big-endian 16-bit CBI opcodes without response. Basic movement uses
  one-byte COMMAND; basic floor uses three-byte LIGHT with response. Basic
  accessories still use CBI.
- A CBI header is the opcode OR the construction toggle, which alternates
  0/`8000`, including invisible basic motor flips. Held packets repeat unchanged.
  Floor actions retain their extra action/execution flips.
- Payloads are immutable snapshots, without guessed checksums, encryption or
  fragmentation. Unsafe Android shared static payload overwrites are excluded.
- The supported stack owns MTU negotiation and CCCD operations. Frames fit MTU 23.

## Detection / Setup

### Setup and remote selection

- Choose **Vibradorm: VMAT, Caresse Diamant, Werkmeister, V-MAT Basic** in the
  bed-type picker, then **VMAT** and the same zero-based remote ordinal used by
  the app.
- **Legacy setup** inside the family chooser retains the older generic
  controller for fresh setup. Existing entries change through the
  [guided migration](vibradorm.md#guided-setup-and-migration).
- The choices distinguish setup contracts; some command paths overlap. Controls
  and features follow this exact selection.
- Shared Bluetooth identifiers and device-information strings cannot select this
  app or its remote layout.
- Successfully reconfiguring to Caresse or Werkmeister removes the VMAT remote
  from the saved profile. Separate-address sides keep their own remote
  selections.

| Remote | Image | Logical groups | Memory | Sync | Floor | Mood / massage | Movement route |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 00 | sender_010 | Back, legs | No | No | No | No | Basic |
| 01 | sender_020 | Back, legs | No | No | Yes | No | Basic |
| 02 | sender_180 | Back, legs | No | No | No | No | Basic |
| 03 | sender_190 | Back, legs | No | No | No | No | Basic |
| 04 | sender_200 | Back, legs | No | No | Yes | No | Basic |
| 05 | sender_210 | Back, legs | No | No | Yes | No | Basic |
| 06 | sender_220 | Back, legs | No | No | Yes | No | Basic |
| 07 | sender_230 | Back, legs | 6 | Yes | Yes | No | CBI |
| 08 | sender_240 | Back, legs | 6 | Yes | Yes | No | CBI |
| 09 | sender_250 | Back, legs | 6 | Yes | Yes | No | CBI |
| 10 | sender_260 | Back, legs | 6 | Yes | Yes | No | CBI |
| 11 | sender_270 | Head, back, legs | 6 | Yes | No | No | CBI |
| 12 | sender_090 | Back, legs | No | No | No | Yes | Basic |
| 13 | sender_100 | Head, back, legs, feet | 6 | No | No | Yes | CBI |

- The app's neck/calf groups use HA's head/feet controls; physical actuator
  identity remains unverified.
- Remotes 12/13 set the extension flag but expose no floor route.
- Quick memory buttons are subsets of the six-slot contract.

### Bonding

- Setup requires positive native bond evidence for the exact address and actual
  host route. An unverified pairing RPC cannot finish setup or authorize control.
- Metadata does not identify a wire layout or prove a bond. No app PIN/key
  exchange is proven.
- Unsupported proxy pairing should use a supported host adapter; existing bonds
  are never silently removed.

### Onboarding

Initialization settles for 500 ms and subscribes for every remote. Setup reads
the three DIS fields, then serially issues seven CBI stages:

| Stage | Request | Response |
| --- | --- | --- |
| Status | `01 b3 4c 01` | `21 b3 value`, unsigned byte |
| Operating mode | `01 b3 f4 01` | `21 b3 value`, signed byte |
| Article | `01 a0 c8` | `21 a0 c8` plus UTF-8 |
| Name | `01 a0 c9` | `21 a0 c9` plus UTF-8 |
| Revision ID | `01 a0 ca 00` | `21 a0 ca` plus UTF-8 |
| Revision string | `01 a0 ca` | `21 a0 ca` plus UTF-8 |
| Variant | `01 a0 cc` | `21 a0 cc` plus UTF-8 |

- The first response timeout is 2 seconds and the others 1 second.
- Each notification can complete one current stage; the two CA stages stay
  separate. Missing replies advance after timeout without a fabricated
  acknowledgment.
- Transport write timeouts abort onboarding before native pairing.
- Short/mismatched replies are guarded. UTF-8 retains whitespace and NULs.
- After native pairing/proof, setup sends `01 a7` and disconnects. Runtime
  onboarding also closes its link before a separate control connection, whose
  actual route must prove the bond.
- Normal sessions issue no onboarding queries or position polls. Explicit
  information refresh reads only three DIS fields.
- An existing native bond skips onboarding and pairing, while setup still
  validates the selected remote's ordinary GATT roles before accepting the
  address.
- Onboarding connection timeout is 5 seconds. HA bounds the complete operation
  with a separate 45-second resource budget, not a device pairing timing claim.

### Setup link cleanup

- Disconnect still runs if setup close fails or is cancelled. Cancellation
  propagates, and a failed or interrupted disconnect retains the live client
  owner for cleanup rather than dropping its tracking or runtime pointer.
- An RPC error after observed native closure does not turn completed teardown
  into a failure. An earlier setup error or cancellation still propagates.
- Notification cleanup preserves an earlier setup error or cancellation. A
  cleanup failure after successful reads still fails setup before native pairing.
- The physical BLE connection remains visible until it actually closes.
- A failed config or runtime setup link stays owned by Home Assistant's exact
  address lock after the progress worker or flow ends, including local bond
  replacement. Retry, another flow, runtime and diagnostic capture cannot open a
  second link until native closure is observed.
- Cleanup retries only that retained client's disconnect; it supplies no bond
  proof and sends no additional protocol frame. Other addresses and ordinary
  setup flows retain their existing behavior.
- A retained setup or failed-startup link cannot serve commands or be replaced
  by retry/reconnect. Sequential paired verification must release it before
  opening the other side. Successful observed teardown restores normal
  connection admission.

### Discovery

- The bounded raw parser concatenates FF records in original AD order, including
  company IDs. It preserves company `03b0`, `ffff/BABE`, revisions 3/4/5, exact
  flags, GID, signed revision 4/5 SGID and customer metadata.
- Company `03b0` remains eligible even with an unknown revision.
- A complete raw record without a Flags field uses the shipped SDK's `-1`
  default; an available Flags field uses its first payload byte.
- Teach selection uses the current third eligible report, followed by owner
  teardown, rather than a cached strongest RSSI device.
- Exact-address reconnect bypasses manufacturer classification.
- HA's manufacturer mapping loses original AD order, duplicate records and raw
  advertising flags. Diagnostics leave these unavailable flags unknown, never
  replace them with zero or the raw-record default, and never infer the
  app/remote. Select the exact address explicitly.
- Malformed lengths that make Android hang, crash or pad missing bytes are
  rejected safely.

### Home Assistant setup

Choose **Vibradorm: VMAT, Caresse Diamant, Werkmeister, V-MAT Basic** in the
bed-type picker, then **VMAT** and the same remote ordinal as the app. Its fourteen
shipped selections derive the logical axes, memory, sync, floor, mood and
massage controls. Independent feature overrides
and inferred product identification are unavailable. Setup requires positive
native bond evidence for the exact address and actual host adapter; an
unverified proxy pairing request cannot finish setup. Ordinary sessions do not
send onboarding queries or position polls. Accessory state is assumed local
intent, preserved during the current HA process and rolled back on failed
writes. Configure each physical side separately before combining a two-address pair.

## Commands

Basic packets are written to COMMAND `1526`; CBI packets to `1550`. `T` is the
construction toggle (0 or `8000`) ORed into the 16-bit CBI header.

### Motor Control

| Command | `hold_control` | Basic (COMMAND) | CBI opcode |
|---------|----------------|-----------------|------------|
| Head up / down | `head_up`, `head_down` | n/a | `0003`, `0002` |
| Back up / down | `back_up`, `back_down` | `0b`, `0a` | `000b`, `000a` |
| Legs up / down | `legs_up`, `legs_down` | `09`, `08` | `0009`, `0008` |
| Feet up / down | `feet_up`, `feet_down` | n/a | `0005`, `0004` |
| All Up / All Down | `all_up`, `all_down` | `10`, `00` | `0010`, `0000` |
| STOP (release) | | `ff` | `00 ff` |

- Enabled motor directions, All Up/All Down and recall are held actions. All Down
  is movement, not a timed flat preset.
- Only directions in the selected remote's logical groups are offered: head on
  remotes 11 and 13, feet on remote 13.

### Memory

| Command | `hold_control` | CBI packets |
|---------|----------------|-------------|
| Recall slots 1–6 | `memory_1` … `memory_6` | Held opcode `0e,0f,0c,1a,1b,1c` |
| Program a slot | | Four alternating STORE `000d/800d` frames, an untoggled slot frame (`00` + slot opcode), then four `00ff` frames |

The program sequence is the nine-frame save handshake referenced in the
[issue #403 reconciliation](#issue-403-reconciliation).

### Sync

Sync on control 8/9 (remotes 07–11) queries `3d|T,3f` and is a reply-gated
held action:

| Step | Packet |
|------|--------|
| Query (CBI) | Header `003d`\|T followed by `3f` |
| Reply | `20 3f flags` or `3f flags extra` (minimum length 3) |
| Held action | Opcode 25 when reply bit `40` is set, otherwise 24 |

Late replies cannot restart released movement. No partner selector is proven.

### Floor light

| Route | Packet |
|-------|--------|
| Basic floor remotes (01, 04–06) | LIGHT `1529`: `level 00 timer` (three bytes, with response) |
| CBI floor remotes (07–10) | CBI: `0011`\|T + `level timer` |

- Floor levels 0–8 map to `0,32,64,96,128,160,192,224,250`. Off is 0;
  remembered default is 8 for selectable floor remotes.
- Timer minutes 1–60 and enabled state apply to the next floor packet;
  timer-only changes send nothing.
- Cold current level 0 is assumed local state, not measured physical off state.

### Mood light

| Command | Packet |
|---------|--------|
| Palette color | `0077` (basic) or `1077` (nonbasic)\|T + `01 00 R G B` |
| Effect 1–3 (sunrise, rainbow, disco) | `0077`/`1077`\|T + `08` + effect number |
| Speed 0–8 | `0077`/`1077`\|T + `09` + `18,16,…,2` |
| Toggle | `1077`\|T for both |

- Mood exposes 18 shipped palette choices with VMAT-specific conversion
  rounding, three effects, and speed 0–8 mapping `18,16,…,2`.
- Color/effects use `0077` basic or `1077` nonbasic; toggle uses `1077` for
  both. Arbitrary RGB and discrete physical on/off guarantees are absent.

### Massage

| Command | Packet |
|---------|--------|
| ON (full state) | `0030/1030`\|T + effect, speed, two zone intensities, four zero bytes (10 bytes total) |
| OFF | `0034/1034`\|T + `00` |

- Massage on remotes 12/13 exposes automatic/individual modes, two zone toggles
  and steps, four waves and speed 1–5.
- Complete current/saved settings and flags are retained. Intensity is 0–5,
  minimum 1 with nonzero effect; first automatic restore is effect 1/speed
  1/zones 3/3.
- ON is the full 10-byte `0030/1030` state; OFF is `0034/1034` plus `00`. Mode
  switching preserves off/restore order.
- Unreachable OFF `01` and the unexposed massage timer are disabled.

## State

- Floor/timer/mood/massage state is process-local intent. Reconnect and reload
  retain it for the exact address/app/remote; profile changes clear the holder.
- Failed/cancelled VMAT accessory writes roll back the requested state.
  Successful delivery remains assumed intent, not readback.
- Restart clears current intent while retaining the configured floor default.
- No live position parser, angle target, battery query, firmware update,
  calibration or named presets are proven.
- Diagnostics retain raw notifications; unsolicited EEPROM/log recognition does
  not enable dead collectors or queries.

## Command Timing

- First delivery is immediate on an idle lane; repeats/queued writes wait 100 ms
  after successful completion.
- Release, cancellation and failure use fresh STOP (`ff` basic, `00 ff` CBI),
  prioritizing cleanup over pending ordinary traffic. No hardware watchdog is
  claimed.

## Issue #403 reconciliation

The original [parity request](https://github.com/kristofferR/ha-adjustable-bed/issues/403)
predates the accepted independent app audits. Its assumption that Caresse,
Werkmeister, VMAT and V-MAT Basic expose one interchangeable contract is
superseded by their explicit profiles. The VMAT profile shipped in
[v4.1.0](https://github.com/kristofferR/ha-adjustable-bed/releases/tag/v4.1.0).
The outcomes below describe existing implementation and accepted exclusions;
they do not change the frozen audit ledger.

| Original request | Current outcome | Existing evidence |
| --- | --- | --- |
| Live positions, initialization flags and raw motor counts | EXCLUDED as a VMAT app feature: no reachable live position parser is proven. The generic controller retains its separate historical parser and angle estimates. | `VibradormAppController.supports_position_feedback`; `test_remote_contract_and_no_guessed_capabilities`; [generic controller](vibradorm.md#position-feedback) |
| Full EEPROM collection and diagnostic field sensors | EXCLUDED as a supported app operation: unsolicited EEPROM/log recognition does not establish a reachable collector or query. | Accepted VMAT notification/capability dispositions; Caresse dead parser routes `R031-0548`–`R031-0550` in the row031 audit |
| Memory recall M1–M6 and store handshake | ALREADY_IMPLEMENTED where the selected remote enables memory, with the exact nine-frame save sequence. | `hold_control`, `program_memory`; `test_every_reachable_held_control_releases`, `test_complete_nine_frame_save_sequence` |
| Status request and sync | ALREADY_IMPLEMENTED for the VMAT sync remotes as a reply-gated held action. The observed sync flag is exposed; it is not a position measurement. | `hold_control`, `_notification`, `controller_state_sensor_specs`; `test_sync_only_streams_while_response_is_pending_and_held`, `test_registered_notifications_are_bound_to_live_role_and_generation` |
| Floor light, level and timer | ALREADY_IMPLEMENTED for selectable floor remotes, with their exact LIGHT or CBI route and pending timer state. | `_floor`, `set_pending_floor_timer`; `test_floor_delivery_full_shipped_range` |
| Mood color, effects, speed and toggle | ALREADY_IMPLEMENTED for remotes 12/13, using the shipped palette and effect choices. | `_mood`, `set_mood_palette`, `set_mood_effect`, `set_mood_speed`; `test_all_shipped_palette_packets`, `test_all_mood_speed_positions` |
| Unrestricted RGB color | EXCLUDED from app parity: the shipped UI supplies palette choices, not an arbitrary RGB control. | Accepted VMAT light/profile contract and palette vectors |
| Massage modes, speed and two intensity zones | ALREADY_IMPLEMENTED for remotes 12/13, with full current/saved state and exact mode/off/restore ordering. | `_plan_massage_mode`, `_write_massage_packets`; `test_full_massage_state_packets_from_frozen_builder_vectors`, `test_automatic_individual_restore_clamps_and_exact_off_restore_order` |
| Massage timer and OFF-command payload `01` | EXCLUDED from app parity: neither is exposed by a reachable shipped control. | Accepted VMAT massage contract and disabled-action gates |
| Toggle, accessory bus selection, refresh and STOP | ALREADY_IMPLEMENTED per selected remote. Logical construction advances the toggle; held repeats reuse the packet. | `_header`, `_write`, `_release`; `test_every_reachable_held_control_releases`, `test_single_shots_wait_after_success_completion_and_stop_bypasses_delay` |
| Automatic generic layout from control-version metadata | EXCLUDED: shared metadata does not select the app's remote or establish physical actuator identity. All fourteen shipped VMAT selections are explicitly available. | `VMAT_REMOTES`; `test_remote_contract_and_no_guessed_capabilities`, `test_remote_flags_cannot_be_spoofed` |

Code references above are in
[`vibradorm_app.py`](../../custom_components/adjustable_bed/beds/vibradorm_app.py)
and [`vibradorm_vmat_profiles.py`](../../custom_components/adjustable_bed/vibradorm_vmat_profiles.py).
Test references are in
[`test_vibradorm_vmat.py`](../../tests/test_vibradorm_vmat.py); the
machine-local VMAT audit ledger retains the exact accepted source bindings.
[Caresse / Werkmeister](vibradorm_app.md) and [V-MAT Basic](vmatbasic.md)
have their own independent feature gates, vectors and dispositions.

The requested MC4-MD08 retest remains deferred physical validation for its
owner after release. The accepted app implementation does not prove that
[issue #162](https://github.com/kristofferR/ha-adjustable-bed/issues/162) is fixed
or that a particular controller reports positions. No in-scope implementation
item is deferred for lack of maintainer hardware.

## Notes

### Discovery ledger

- The machine-local VMAT audit ledger binds all 282 comparison items: 240 IMPLEMENTED, 0 ALREADY_IMPLEMENTED and 42 EXCLUDED.
- Its exact exclusions cover 26 unreachable selectors, Android
  scanner/permission/bond APIs, phone presentation and unsafe
  queue/parser/cancellation behavior.
- Hardware absence does not defer implementation. Focused tests exercise real
  controller/setup delivery, frozen vectors, native-proof gates, timing and
  failure cleanup. Physical validation remains for users after beta/release.

### Analysis provenance

- This explicit profile implements the accepted `de.vibradorm.vmat` 1.11 (49)
  application contract. App behavior is artifact verified; physical operation
  remains unverified.
