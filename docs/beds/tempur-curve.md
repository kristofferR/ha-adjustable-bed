# Tempur Curve

**Status:** ❓ Needs testing (APK-verified, hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Beds controlled by the Tempur Curve Android app (`com.ore.tempur`)
- App layout: **standard** (the only layout)
- No Bluetooth name, service UUID or manufacturer data identifies this app

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Tempur Curve 1.7](https://play.google.com/store/apps/details?id=com.ore.tempur) | `com.ore.tempur` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Head, Foot (Back and Legs covers) |
| Position Feedback | ❌ |
| Memory Presets | ❌ (no physical memory slots) |
| Presets | ✅ Flat, Zero G, Lounge Ii, Tv Iii, Anti Snore I (app labels) |
| Massage | ✅ Head add, foot add, massage timer |
| Lights | ✅ (Light key) |
| Other App Keys | ✅ Reset |
| Alarm Tables | ✅ (weekly and one-time) |
| Wake Alarm Dismissal | ✅ (**Dismiss wake vibration** button) |
| Clock Sync | ✅ (2 seconds after connecting, and on demand) |
| Device Rename | ✅ (14 UTF-16 units, trimmed) |
| Timer Status | ✅ (**App timer status** sensor) |

## Protocol Details

**Service UUID:** None required; characteristics are matched across all services
**Write Characteristic:** `0000ffe9-0000-1000-8000-00805f9b34fb` (FFE9)
**Notify Characteristic:** `0000ffe4-0000-1000-8000-00805f9b34fb` (FFE4)
**Format:** 8-byte `E5 FE 16` key frames: low32 little-endian mask plus an inverted-sum checksum

### Characteristic Selection

- The GATT selector independently retains the last matching notification and
  write characteristics across all services. Both are required.
- FFE4/FFE9 are used by these profiles; only Q-Plus also accepts NUS read/write
  roles, independently of UI style.
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
| Key | 8 | `E5 FE 16`, low32 little-endian mask, checksum. The zero mask `E5 FE 16 00 00 00 00 06` is the release |
| Clock | 10 | `E7 80 01`, local year minus 1900 (low byte), zero-based month, day, hour, minute, second, checksum |
| Name | 18 | `EF 02`, a 15-byte zero-filled name region, checksum |
| Alarm table | 16 | `ED 80 03` (weekly) or `ED 80 02` (one-time); see [Alarm Tables](#alarm-tables) |
| Wake dismissal | 4 | `E1 80 04 9A` |

Checksum: one inverted-sum byte, `~sum(preceding bytes) & 0xFF`. Java's signed
and unsigned sums have the same low-byte complement.

### Device Name

- Use [`adjustable_bed.rename`](../SERVICES.md#rename). The supported UI limit
  is 14 UTF-16 units.
- The source copies that many bytes from an unnamed default charset. HA
  documents and uses the frozen UTF-8 model, including incomplete encoded
  characters for some non-ASCII names. This does not establish firmware
  encoding.
- The connected rename caller applies Java `String.trim` (outer code points
  U+0000 through U+0020) before encoding and rejects an empty result. This is
  package-specific caller handling, not Unicode whitespace normalization. The
  conditional UTF-8/code-unit-copy model above remains qualified as documented.

## Detection / Setup

- Select **Tempur Curve** explicitly in the bed-type list. Use the Bluetooth
  address of the bed.
- Choose the layout shown by your app in **App controls** (**App layout**). The
  layout is a UI choice, not proof of physical motor count or bed model.
- Shared services, names and manufacturer data do not select this app
  automatically.
- Generic SBI, Keeson and other app profiles keep their existing behavior.

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
- **Frame** shows the bytes HA writes: the 8-byte key frame. Behavior names are
  explained in [Command Timing](#command-timing).
- Head and foot keys drive the **Back** and **Legs** covers. Every other key is
  an app-labelled button; held keys also accept
  [`hold_control`](../SERVICES.md#hold_control).
- Cover stop and **Stop All** send the zero release frame
  `E5 FE 16 00 00 00 00 06`.

### Motor Control

| App label | Key | Mask | Frame | Behavior |
|---|---|---|---|---|
| Head Up (Back cover) | `head_up` | `0x1` | `E5 FE 16 01 00 00 00 05` | held |
| Head Down (Back cover) | `head_down` | `0x2` | `E5 FE 16 02 00 00 00 04` | held |
| Foot Up (Legs cover) | `foot_up` | `0x4` | `E5 FE 16 04 00 00 00 02` | held |
| Foot Down (Legs cover) | `foot_down` | `0x8` | `E5 FE 16 08 00 00 00 FE` | held |

### Presets

| App label | Key | Mask | Frame | Behavior |
|---|---|---|---|---|
| Zero G | `zero_g` | `0x1000` | `E5 FE 16 00 10 00 00 F6` | single |
| Tv Iii | `tv_III` | `0x4000` | `E5 FE 16 00 40 00 00 C6` | held |
| Anti Snore I | `anti_snore_I` | `0x8000` | `E5 FE 16 00 80 00 00 86` | held |
| Flat | `flat` | `0x8000000` | `E5 FE 16 00 00 00 08 FE` | single |
| Lounge Ii | `lounge_II` | `0x2000` | `E5 FE 16 00 20 00 00 E6` | held |

### Massage and Timer

| App label | Key | Mask | Frame | Behavior |
|---|---|---|---|---|
| Massage Timer | `massage_timer` | `0x200` | `E5 FE 16 00 02 00 00 04` | pulse |
| Massage Foot Add | `massage_foot_add` | `0x400` | `E5 FE 16 00 04 00 00 02` | pulse |
| Massage Head Add | `massage_head_add` | `0x800` | `E5 FE 16 00 08 00 00 FE` | pulse |

### Lights

| App label | Key | Mask | Frame | Behavior |
|---|---|---|---|---|
| Light | `light` | `0x20000` | `E5 FE 16 00 00 02 00 04` | single |

### Other App Keys

| App label | Key | Mask | Frame | Behavior |
|---|---|---|---|---|
| Reset | `reset` | `0x8001000` | `E5 FE 16 00 10 00 08 EE` | held |

### Wake Alarm Dismissal

| Command | Bytes | Description |
|---------|-------|-------------|
| Dismiss wake vibration | `E1 80 04 9A` | Sent 2 times, 400 ms apart. Button key `dismiss_alarm`; it does not cancel movement |

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
| Wake byte | **0x03** when `wake` is set, otherwise zero |
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

## Notifications / State

- The **App timer status** sensor reports only the accepted source statuses:
  -1=off, 1=10 minutes, 2=20 minutes, 3=30 minutes. Status byte `0xFF` is off.
  Unknown statuses leave the prior value unchanged.
- The parser does not infer acknowledgement, battery, physical motor count,
  light state or physical memory meaning.
- Incoming packets are not reassembled or given invented header/checksum guards.

| Length | Accepted when | Status from |
|--------|---------------|-------------|
| 16 | Byte 13 bit 5 clear | Byte 14 |
| 19 | Byte 14 bit 5 clear | Byte 15 |
| 20 | Always (no bit 5 gate) | Byte 14 |

Other lengths are ignored.

## Command Timing

| Behavior | Sequence |
|----------|----------|
| `held` | Key frame at once, then every **100 ms** until bounded release; then the zero release frame |
| `pulse` | Key frame once, then the zero release frame after 300 ms |
| `single` | Key frame once |
| `tap_zeros` | Key frame once, followed by zero frames at +300/+400/+500 ms (not used by this app) |
| `held_zeros` | As `held`, and also schedules those three zero frames from the start of the hold, retaining them after ordinary early release (not used by this app) |

- A button press provides a finite held adapter based on the configured pulse
  count: pulse count x 100 ms, bounded to 1-60000 ms. The pulse count does not
  change the source 100 ms refresh, which starts immediately.
- `hold_control` accepts only the declared held keys, for 1-60000 ms.
- All protocol-defined releases run with a fresh cancellation event.
- Cancellation and disconnect never leave background writers from an old
  operation.
- Clock: the app queues its initial clock after 2 seconds, with 500 ms
  post-write pacing. HA sends it 2 seconds after subscribing unless the session
  is cancelled; [`adjustable_bed.sync_clock`](../SERVICES.md#sync_clock) sends
  it on demand.

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

- Accepted artifact: `com.ore.tempur` version **1.7**.
- Artifact-set SHA-256:
  `f3c98817a94bf697fb02fe6850134cf6c248b2bb69f10a6943007d291487bb60`.
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
