# Q-Plus Adjustable Remote

**Status:** ❓ Needs testing (APK-verified, hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Beds controlled by the Q-Plus Adjustable Remote Android app (`com.sbi.costco`)
- App layouts: **H**, **M1**, **M2**, **M3**, **MX** (default **M2**)
- Separate from the generic [SBI / Q-Plus](sbi.md) bed type
- No Bluetooth name, service UUID or manufacturer data identifies this app

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Q-Plus Adjustable Remote 1.8](https://play.google.com/store/apps/details?id=com.sbi.costco) | `com.sbi.costco` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Head, Foot (Back and Legs covers); Tilt (H, M2, MX); Lumbar (H) |
| Position Feedback | ❌ |
| Memory Presets | ❌ (MX Memory 1 is an opaque key, not a physical slot) |
| Presets | ✅ Flat (all); Zero_G, Read (H, M1, M2, M3); TV (H, M1, M2); Anti-snore (M2, MX) |
| Massage | ✅ Head, Foot (H, M1, M2, MX); Lumbar Massage (H, M1); Modes 1-3 (H); Massage timer (MX) |
| Lights | ✅ (H, M1, MX) |
| Other App Keys | ✅ Level, Reset (H, M1, M2, M3); Music (H, M1) |
| A/B/Both Selector | ✅ (P1 layouts) |
| Alarm Tables | ✅ (weekly and one-time) |
| Wake Alarm Dismissal | ✅ (**Dismiss wake vibration** button) |
| Clock Sync | ❌ (no accepted clock-sync writer) |
| Device Rename | ✅ (14 UTF-16 units, no outer whitespace) |
| Timer Status | ✅ (**App timer status** sensor) |

## Protocol Details

**Service UUID:** None required; characteristics are matched across all services
**Write Characteristic:** `0000ffe9-0000-1000-8000-00805f9b34fb` (FFE9)
**Notify Characteristic:** `0000ffe4-0000-1000-8000-00805f9b34fb` (FFE4)
**Alternate (Nordic UART):** write `6e400002-b5a3-f393-e0a9-e50e24dcca9e`, notify `6e400003-b5a3-f393-e0a9-e50e24dcca9e`
**Format:** 8-byte `E5 FE 16` key frames: low32 little-endian mask plus an inverted-sum checksum (P1, Both); A/B and MX frames below

### Characteristic Selection

- The GATT selector independently retains the last matching notification and
  write characteristics across all services. Both are required.
- Q-Plus also accepts the NUS read/write roles, independently of UI style. Each
  role is matched on its own, so write and notify can come from different
  services.
- HA subscribes through Bleak. No authentication, arbitrary-packet service or
  guessed firmware operation is added.

### Write Mode

HA chooses the response mode from the current characteristic properties: it
writes with response when the write characteristic has the `write` property,
otherwise without response. The APK's unset Android write type does not prove
an on-air mode.

### Packet Format

| Frame | Bytes | Layout |
|-------|-------|--------|
| Key (P1, Both) | 8 | `E5 FE 16`, low32 little-endian mask, checksum. The zero mask `E5 FE 16 00 00 00 00 06` is the release |
| Key (P1, Side A/B) | 9 | `E6 FE 16`, low32 little-endian mask, side byte `01` (A) or `02` (B), checksum |
| Key (MX) | 6 | `04 02`, 32-bit big-endian mask, no checksum |
| Status query (MX) | 2 | `00 B0` |
| Clock | 10 | `E7 80 01`, local year minus 1900 (low byte), zero-based month, day, hour, minute, second, checksum (no clock writer in this app) |
| Name | 18 | `EF 02`, a 15-byte zero-filled name region, checksum |
| Alarm table | 16 | `ED 80 03` (weekly) or `ED 80 02` (one-time); see [Alarm Tables](#alarm-tables) |
| Wake dismissal | 4 | `E1 80 04 9A` |

Checksum: one inverted-sum byte, `~sum(preceding bytes) & 0xFF`. Java's signed
and unsigned sums have the same low-byte complement.

### Wire Selector (P1)

Q-Plus **A/B/Both** is a separate app wire selector, not paired Left/Right.
P1 uses `E5` for Both or `E6 ... 01/02` for A/B.

| Selector | Head Up frame | Zero (release) frame |
|----------|---------------|----------------------|
| Both | `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` |
| Side A | `E6 FE 16 01 00 00 00 01 03` | `E6 FE 16 00 00 00 00 01 04` |
| Side B | `E6 FE 16 01 00 00 00 02 02` | `E6 FE 16 00 00 00 00 02 03` |

### MX Frames

- MX uses the sparse six-byte `04 02` builder with big-endian payload and no
  checksum.
- The builder is private and grants no arbitrary-mask API. Masks outside its
  source set (`0x1`, `0x2`, `0x4`, `0x8`, `0x10`, `0x20`, `0x200`, `0x400`,
  `0x800`, `0x2000`, `0x4000`, `0x8000`, `0x10000`, `0x20000`, `0x800000`,
  `0x1000000`, `0x2000000`, `0x4000000`, `0x8000000`, `0x40000000`) are sent as
  zero.
- `00 B0` is the MX status query. MX has no zero-key release.

### Device Name

- Use [`adjustable_bed.rename`](../SERVICES.md#rename). Rename keeps this app's
  14-unit editor domain: the supported UI limit is 14 UTF-16 units.
- The source copies that many bytes from an unnamed default charset. HA
  documents and uses the frozen UTF-8 model, including incomplete encoded
  characters for some non-ASCII names. This does not establish firmware
  encoding.
- HA rejects outer whitespace; it does not infer another package's trimmed
  caller semantics for Q-Plus.

## Detection / Setup

- Select **Q-Plus Adjustable Remote** explicitly in the bed-type list. Use the
  Bluetooth address of the bed.
- Choose the layout shown by your app in **App controls** (**App layout**). The
  layout is a UI choice, not proof of physical motor count or bed model.
- Shared services, names and manufacturer data do not select this app
  automatically.
- Generic SBI, Keeson and other app profiles keep their existing behavior.
- **Q-Plus bed selection** (Both, Side A or Side B) sets the P1 wire selector,
  stored as `protocol_variant` `both`, `side_a` or `side_b`. It is independent
  of a Home Assistant paired Left/Right target.

### Paired Beds

- Each physical side of a two-address pair retains its own app settings.
- Target the native child device, or choose the paired service's `side`;
  conflicting child/side requests are rejected.
- No app-specific physical left/right mapping or one-address pairing is
  inferred.

## Commands

- Labels, keys and masks are this app's own; repeated masks are separate package
  receipts, not inferred family equivalence. Groupings follow the app labels;
  physical effects are unverified.
- **Frame** shows the bytes HA writes: the P1 key frame with the Both selector,
  or the MX frame in the MX table. Behavior names are explained in [Command
  Timing](#command-timing).
- Head and foot keys drive the **Back** and **Legs** covers. Every other key is
  an app-labelled button; held keys also accept
  [`hold_control`](../SERVICES.md#hold_control).
- Cover stop and **Stop All** send the zero key frame for the selected selector
  (`E5 FE 16 00 00 00 00 06` for Both); MX sends its `00 B0` release queries
  instead.

### P1 Layouts (H, M1, M2, M3)

Frames below use the Both selector; Side A/B use the `E6` form in
[Wire Selector (P1)](#wire-selector-p1).

#### Motor Control

| App label | Key | Mask | Frame | Behavior | H | M1 | M2 | M3 |
|---|---|---|---|---|---|---|---|---|
| Head Up (Back cover) | `head_up` | `0x1` | `E5 FE 16 01 00 00 00 05` | held | ✅ | ✅ | ✅ | ✅ |
| Head Down (Back cover) | `head_down` | `0x2` | `E5 FE 16 02 00 00 00 04` | held | ✅ | ✅ | ✅ | ✅ |
| Foot Up (Legs cover) | `foot_up` | `0x4` | `E5 FE 16 04 00 00 00 02` | held | ✅ | ✅ | ✅ | ✅ |
| Foot Down (Legs cover) | `foot_down` | `0x8` | `E5 FE 16 08 00 00 00 FE` | held | ✅ | ✅ | ✅ | ✅ |
| Tilt Up | `tilt_up` | `0x10` | `E5 FE 16 10 00 00 00 F6` | held | ✅ | ❌ | ✅ | ❌ |
| Tilt Down | `tilt_down` | `0x20` | `E5 FE 16 20 00 00 00 E6` | held | ✅ | ❌ | ✅ | ❌ |
| Lumbar Up | `lumbar_up` | `0x40` | `E5 FE 16 40 00 00 00 C6` | held | ✅ | ❌ | ❌ | ❌ |
| Lumbar Down | `lumbar_down` | `0x80` | `E5 FE 16 80 00 00 00 86` | held | ✅ | ❌ | ❌ | ❌ |

#### Presets

| App label | Key | Mask | Frame | Behavior | H | M1 | M2 | M3 |
|---|---|---|---|---|---|---|---|---|
| Zero_G | `zero_g` | `0x1000` | `E5 FE 16 00 10 00 00 F6` | single | ✅ | ✅ | ✅ | ✅ |
| Read | `read` | `0x2000` | `E5 FE 16 00 20 00 00 E6` | held | ✅ | ✅ | ✅ | ✅ |
| Flat | `flat` | `0x8000000` | `E5 FE 16 00 00 00 08 FE` | single | ✅ | ✅ | ✅ | ✅ |
| TV | `tv` | `0x8000` | `E5 FE 16 00 80 00 00 86` | held | ✅ | ✅ | ❌ | ❌ |
| TV | `tv` | `0x4000` | `E5 FE 16 00 40 00 00 C6` | held | ❌ | ❌ | ✅ | ❌ |
| Anti-snore | `anti_snore` | `0x8000` | `E5 FE 16 00 80 00 00 86` | single | ❌ | ❌ | ✅ | ❌ |

#### Massage and Timer

| App label | Key | Mask | Frame | Behavior | H | M1 | M2 | M3 |
|---|---|---|---|---|---|---|---|---|
| Massage Head | `massage_head` | `0x800` | `E5 FE 16 00 08 00 00 FE` | single | ✅ | ✅ | ✅ | ❌ |
| Massage Foot | `massage_foot` | `0x400` | `E5 FE 16 00 04 00 00 02` | single | ✅ | ✅ | ✅ | ❌ |
| Lumbar Massage | `lumbar_massage` | `0x400000` | `E5 FE 16 00 00 40 00 C6` | single | ✅ | ✅ | ❌ | ❌ |
| Massage Mode 3 | `massage_mode_3` | `0x80000` | `E5 FE 16 00 00 08 00 FE` | single | ✅ | ❌ | ❌ | ❌ |
| Massage Mode 1 | `massage_mode_1` | `0x100000` | `E5 FE 16 00 00 10 00 F6` | single | ✅ | ❌ | ❌ | ❌ |
| Massage Mode 2 | `massage_mode_2` | `0x200000` | `E5 FE 16 00 00 20 00 E6` | single | ✅ | ❌ | ❌ | ❌ |

#### Lights

| App label | Key | Mask | Frame | Behavior | H | M1 | M2 | M3 |
|---|---|---|---|---|---|---|---|---|
| Light | `light` | `0x20000` | `E5 FE 16 00 00 02 00 04` | single | ✅ | ✅ | ❌ | ❌ |

#### Other App Keys

| App label | Key | Mask | Frame | Behavior | H | M1 | M2 | M3 |
|---|---|---|---|---|---|---|---|---|
| Level | `level` | `0x100` | `E5 FE 16 00 01 00 00 05` | single | ✅ | ✅ | ✅ | ✅ |
| Reset | `reset` | `0x8001000` | `E5 FE 16 00 10 00 08 EE` | held | ✅ | ✅ | ✅ | ✅ |
| Music | `music` | `0x4000` | `E5 FE 16 00 40 00 00 C6` | held | ✅ | ✅ | ❌ | ❌ |

### MX Layout

| App label | Key | Mask | Frame | Behavior |
|---|---|---|---|---|
| Head Up (Back cover) | `head_up` | `0x1` | `04 02 00 00 00 01` | held |
| Head Down (Back cover) | `head_down` | `0x2` | `04 02 00 00 00 02` | held |
| Foot Up (Legs cover) | `foot_up` | `0x4` | `04 02 00 00 00 04` | held |
| Foot Down (Legs cover) | `foot_down` | `0x8` | `04 02 00 00 00 08` | held |
| Tilt Up | `tilt_up` | `0x10` | `04 02 00 00 00 10` | held |
| Tilt Down | `tilt_down` | `0x20` | `04 02 00 00 00 20` | held |
| Anti-snore | `anti_snore` | `0x8000` | `04 02 00 00 80 00` | held |
| MX Memory 1 | `mx_memory1` | `0x10000` | `04 02 00 01 00 00` | held |
| Flat | `flat` | `0x8000000` | `04 02 08 00 00 00` | single |
| Light | `light` | `0x4000` | `04 02 00 00 40 00` | single |
| Massage head | `massage_head` | `0x800` | `04 02 00 00 08 00` | pulse |
| Massage foot | `massage_foot` | `0x400` | `04 02 00 00 04 00` | pulse |
| Massage timer | `massage_timer` | `0x200` | `04 02 00 00 02 00` | pulse |

- **MX Memory 1** is an opaque app-named held action, not an invented physical
  save or recall operation. It attempts `04 02 00 01 00 00` every 100 ms.
  Release stops repetition and, while connected, queries `00 B0` at
  +300/+600/+900 ms. It sends no STOP/zero/clear-key packet.
- Single MX actions query at +500/+800 ms; MX massage waits 300 ms before its
  release query triplet.

### Wake Alarm Dismissal

| Command | Bytes | Description |
|---------|-------|-------------|
| Dismiss wake vibration | `E1 80 04 9A` | Sent 4 times, 200 ms apart. Button key `dismiss_alarm`; it does not cancel movement |

## Alarm Tables

Use [`adjustable_bed.configure_alarm_schedule`](../SERVICES.md#configure_alarm_schedule).

| Field | Value |
|-------|-------|
| Weekly frame | `ED 80 03`, 16 bytes |
| One-time frame | `ED 80 02`, 16 bytes |
| Records | Three four-byte records (bytes 3-14) and an inverted-sum checksum at 15 |
| Weekly record | Hour, minute, weekday byte, wake byte |
| One-time record | Delay hours (low byte), minutes, seconds, wake byte |
| Weekday byte | Marker bit 7 plus weekday bits; Monday through Saturday use bits 1..6, Sunday bit 0 |
| Wake byte | **0x10** when `wake` is set, otherwise zero |
| Dispatch | `both` sends weekly, waits 500 ms, then one-time; selected single-table dispatch still waits 500 ms after the send |

### Validation

- Both `weekly` and `one_time` lists and `dispatch` are required.
- There are three enabled slots in each table. Disabled rows consume no slots;
  `wake: false` enabled rows still consume a slot.
- Both full tables and every physical target are checked before checksums or any
  sends, including an unselected table.
- A transport failure can leave only one table sent; there is no wire rollback.
- Empty-table bytes are attempted writes, not proof that the firmware clears a
  schedule.

### One-time Records

- An enabled one-time row is a future HH:MM on the same Home Assistant local
  date. One captured local `now` is shared by every target and serialization.
- Past/equal, nonexistent DST and ambiguous DST times are rejected before
  writes. No tomorrow rollover or Android date-parser behavior is invented.
- Absolute timestamps use Java Date millisecond precision before positive
  integer hour/minute/second decomposition; a positive subsecond remainder may
  serialize zero seconds, without asserting that zero clears firmware.
- Negative source deltas and fourth-row corruption are never sent. This applies
  even to Omazz/Ergomotion's source partial-overflow cases.
- Weekly and disabled zero fields are not blanket-rejected as zero delays.

### Snooze

- The source snooze path stores 55+10 as minute 65 without carrying. HA's public
  table input requires valid HH:MM; an automation must normalize date/time first
  and reject a cross-date result.
- Phone AlarmManager scheduling remains outside the integration. The BLE table
  writer preserves the original weekly versus one-time dispatch choice and has
  no next-day adjustment.

## Notifications / State

- The **App timer status** sensor reports only the accepted source statuses:
  -1=off, 1=10 minutes, 2=20 minutes, 3=30 minutes. Status byte `0xFF` is off.
  Unknown statuses leave the prior value unchanged.
- The parser does not infer acknowledgement, battery, physical motor count,
  light state or physical memory meaning.
- Incoming packets are not reassembled or given invented header/checksum guards.

| Length | Accepted when | Status from |
|--------|---------------|-------------|
| 16, starting `A5 0B 0D` | Checked before normal bit 5 suppression | Big-endian seconds word (bytes 3-4): 1..600/601..1200/1201..1800 map to 1/2/3; other values are off |
| 16 | Byte 13 bit 5 clear and bytes 7..9 zero | Byte 14 |
| 19 | Byte 16 second-side bit (`0x02`) clear, for every current A/B/Both selector, and bytes 7..9 zero | Byte 15 |
| 20 | Always | Byte 14 |
| 23 | Always | Byte 15 |

Other lengths are ignored. No physical side identity is assigned.

## Command Timing

| Behavior | Sequence |
|----------|----------|
| `held` | Key frame at once, then every **100 ms** until bounded release; then the release (P1 zero key frame; MX `00 B0` queries) |
| `pulse` | Key frame once, then the release (P1 zero key frame; MX `00 B0` queries) after 300 ms |
| `single` | Key frame once; MX then queries `00 B0` at +500/+800 ms |
| `tap_zeros` | Key frame once, followed by zero frames at +300/+400/+500 ms (not used by this app) |
| `held_zeros` | As `held`, and also schedules those three zero frames from the start of the hold, retaining them after ordinary early release (not used by this app) |

- A button press provides a finite held adapter based on the configured pulse
  count: pulse count x 100 ms, bounded to 1-60000 ms. The pulse count does not
  change the source 100 ms refresh, which starts immediately.
- `hold_control` accepts only the declared held keys, for 1-60000 ms.
- All protocol-defined releases run with a fresh cancellation event.
- Cancellation and disconnect never leave background writers from an old
  operation.
- MX initializes with `00 B0` at +300/+600/+900 ms after subscribing. P1 layouts
  instead send one zero key frame for the selected selector.
- The existing diagnostic query hook retains the first-five-second,
  then-thirty-second live-session status-query cadence, with command priority
  and without renewing the idle deadline.
- There is no accepted Q-Plus clock-sync writer and no reachable angle-target
  writer in this artifact.

## Native Card Holds

- The native card uses each entity's flat declared hold metadata and calls the
  registered bounded `hold_control` action once.
- Pointer release, Enter/Space release, blur and page abandonment retain the
  owning side's STOP target. A normal button press and accessibility click
  retain the finite action.
- Combined parent motor buttons advertise a held direction only when every
  eligible side declares the same control and start/release delays on a
  concurrent pair. Mixed, unknown, legacy and sequential sides keep finite
  controls.
- The scalar metadata is `held_control` on buttons, or `held_control_up` and
  `held_control_down` on covers, plus `hold_start_delay_ms` and
  `hold_release_delay_ms`.
- Source-held cluster033 controls declare 0 ms for both, so the card sends STOP
  as soon as the control is released: every source-held key stops refreshing on
  release.
- Q-Plus MX's release queries at 300, 600 and 900 ms come from the controller's
  release cleanup, not from a card delay. They do not invent a physical STOP for
  MX.

## Notes

### Home Assistant Adaptations

- The app-labelled buttons use the existing coordinator command scheduler and
  BLE lane.
- Disconnects invalidate handles, pending work and stale notifications. No
  Android mutable characteristic queue or stale-handle behavior is reproduced.

### Analysis Provenance

- Accepted artifact: `com.sbi.costco` version **1.8**.
- Artifact-set SHA-256:
  `0b1be16e910c944624a6a2991a23840e23dae88a8eba750a12f3c773ffd63803`.
- Static app behavior is proven; actual bed effects, radio delivery and firmware
  interpretation remain **UNVERIFIED**. Real users can validate these after a
  beta or release; no immediate maintainer hardware test is required.
- The [durable disposition ledger](cluster033-dispositions.json) retains all 562
  stable discoveries: 380 implementation dispositions, 12 narrowly credited
  baseline behaviors, 170 exact evidence-backed exclusions. Its per-item symbols
  and test cases accompany 413 frozen vector fixtures.
- The 16150 historical owners, 3386 semantic occurrences, 10158 projections and
  672 dependencies are coverage metadata, not extra features or new audit
  credit. Raw APKs, decompilation and full audit reports stay local and ignored.
