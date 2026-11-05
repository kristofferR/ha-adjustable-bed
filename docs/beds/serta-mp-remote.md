# Serta MP Remote

**Status:** ❓ Needs testing (APK-verified, hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Beds controlled by the Serta MP Remote Android app (`com.ore.serta330`)
- App layout: **standard** (the only layout)
- No Bluetooth name, service UUID or manufacturer data identifies this app

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Serta MP Remote 1.1](https://play.google.com/store/apps/details?id=com.ore.serta330) | `com.ore.serta330` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Head, Foot (Back and Legs covers); Tilt and Lumbar (unlabeled touch areas) |
| Position Feedback | ✅ (calibrated table estimates, head 0-60°, foot 0-45°) |
| Position Targets | ✅ (calibrated pulse targets) |
| Memory Presets | ✅ (4 local angle targets; no physical save) |
| Presets | ✅ Flat, ZERO-G, Lounge, TV, M4 icon |
| Massage | ✅ Head/foot increase and decrease, pattern (btnLevel), TIMER / ALL OFF |
| Lights | ❌ |
| Other App Keys | ✅ RESET-labeled remote action |
| Alarm Tables | ❌ (no alarm-table contract) |
| Wake Alarm Dismissal | ❌ |
| Clock Sync | ❌ (no clock writer) |
| Device Rename | ✅ (14 UTF-16 units, trimmed) |
| Timer Status | ✅ (**App timer status** sensor) |

## Protocol Details

**Service UUID:** None required; characteristics are matched across all services
**Write Characteristic:** `0000ffe9-0000-1000-8000-00805f9b34fb` (FFE9)
**Notify Characteristic:** `0000ffe4-0000-1000-8000-00805f9b34fb` (FFE4)
**Format:** 8-byte `E5 FE 16` key frames and `E5 FE 17` pulse-target frames, each with an inverted-sum checksum

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
| Pulse target | 8 | `E5 FE 17`, head pulse word, foot pulse word (16-bit little-endian each), checksum |
| Clock | 10 | `E7 80 01`, local year minus 1900 (low byte), zero-based month, day, hour, minute, second, checksum (no clock writer in this app) |
| Name | 18 | `EF 02`, a 15-byte zero-filled name region, checksum |

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

- Select **Serta MP Remote** explicitly in the bed-type list. Use the Bluetooth
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
  `E5 FE 16 00 00 00 00 06`, unless the STOP only acknowledges a cancelled local
  angle edit (see [Serta Local Angle Edits](#serta-local-angle-edits)).

### Motor Control

| App label | Key | Mask | Frame | Behavior |
|---|---|---|---|---|
| Head up (Back cover) | `head_up` | `0x1` | `E5 FE 16 01 00 00 00 05` | held |
| Head down (Back cover) | `head_down` | `0x2` | `E5 FE 16 02 00 00 00 04` | held |
| Foot up (Legs cover) | `foot_up` | `0x4` | `E5 FE 16 04 00 00 00 02` | held |
| Foot down (Legs cover) | `foot_down` | `0x8` | `E5 FE 16 08 00 00 00 FE` | held |
| Lumbar down (unlabeled touch area) | `lumbardown` | `0x80` | `E5 FE 16 80 00 00 00 86` | held |
| Lumbar up (unlabeled touch area) | `lumbarup` | `0x40` | `E5 FE 16 40 00 00 00 C6` | held |
| Tilt down (unlabeled touch area) | `tiltdown` | `0x20` | `E5 FE 16 20 00 00 00 E6` | held |
| Tilt up (unlabeled touch area) | `tiltup` | `0x10` | `E5 FE 16 10 00 00 00 F6` | held |

### Presets

| App label | Key | Mask | Frame | Behavior |
|---|---|---|---|---|
| Flat | `flat` | `0x8000000` | `E5 FE 16 00 00 00 08 FE` | single |
| Lounge preset icon | `lounge` | `0x2000` | `E5 FE 16 00 20 00 00 E6` | held |
| Preset M4 icon (distinct from local memory slot 4) | `m4` | `0x8000` | `E5 FE 16 00 80 00 00 86` | single |
| TV preset icon | `tv` | `0x4000` | `E5 FE 16 00 40 00 00 C6` | held |
| ZERO-G preset | `zg` | `0x1000` | `E5 FE 16 00 10 00 00 F6` | single |

### Massage and Timer

| App label | Key | Mask | Frame | Behavior |
|---|---|---|---|---|
| Massage pattern icon (btnLevel) | `level` | `0x100` | `E5 FE 16 00 01 00 00 05` | single |
| Foot massage increase | `masfootadd` | `0x400` | `E5 FE 16 00 04 00 00 02` | single |
| Foot massage decrease | `masfootmin` | `0x1000000` | `E5 FE 16 00 00 00 01 05` | single |
| Head massage increase | `masheadadd` | `0x800` | `E5 FE 16 00 08 00 00 FE` | single |
| Head massage decrease | `masheadmin` | `0x800000` | `E5 FE 16 00 00 80 00 86` | single |
| Massage TIMER / ALL OFF | `timer` | `0x200` | `E5 FE 16 00 02 00 00 04` | single |

### Other App Keys

| App label | Key | Mask | Frame | Behavior |
|---|---|---|---|---|
| RESET-labeled remote action | `reset` | `0x8001000` | `E5 FE 16 00 10 00 08 EE` | held |

### Position Targets

Pulse-target frames are `E5 FE 17`, a 16-bit little-endian head pulse word, a
16-bit little-endian foot pulse word and the checksum.

| Target | Head field | Foot field | Example |
|--------|------------|------------|---------|
| Back slider or `set_position` | Head table value | `0x8000` | Back 30°: `E5 FE 17 6F 1B 00 80 FB` |
| Legs slider or `set_position` | `0x8000` | Foot table value | Legs 15°: `E5 FE 17 00 80 0D 11 67` |
| Local memory recall | Head table value | Foot table value | Slot 1 default (15°/35°): `E5 FE 17 7D 0C A3 24 B5` |

Position sliders send a calibrated axis target with the other field `0x8000`;
no physical meaning for that other-axis field is assumed. Values come from the
[calibration tables](#calibration-tables).

### Local Angle Edits

| App label | Key | Behavior |
|-----------|-----|----------|
| Head Target Up | `head_target_up` | Local held edit, +1° every 200 ms |
| Head Target Down | `head_target_down` | Local held edit, -1° every 200 ms |
| Foot Target Up | `foot_target_up` | Local held edit, +1° every 200 ms |
| Foot Target Down | `foot_target_down` | Local held edit, -1° every 200 ms |

- Local angle up/down actions update a bounded target every 200 ms (head 0-60°,
  foot 0-45°, starting from the last reported angle) and send only one pulse
  frame on release.
- Local editing sends no intermediate movement or zero-key frame. The release
  pulse is written only to a current session.
- A button press holds for pulse count x 200 ms.

## Memory

| Slot | Default head | Default foot | Options |
|------|--------------|--------------|---------|
| 1 | 15° | 35° | `serta_mp_memory_1_head`, `serta_mp_memory_1_foot` |
| 2 | 15° | 35° | `serta_mp_memory_2_head`, `serta_mp_memory_2_foot` |
| 3 | 15° | 35° | `serta_mp_memory_3_head`, `serta_mp_memory_3_foot` |
| 4 | 15° | 0° | `serta_mp_memory_4_head`, `serta_mp_memory_4_foot` |

- Four local memory targets live in the integration configuration, defaulting to
  head/foot 15°/35°, 15°/35°, 15°/35°, 15°/0°. Configure each head 0..60° and
  foot 0..45° in options.
- The **M4 icon** is a remote key, separate from **local memory slot 4**.
- Recalling sends one `E5 FE 17` frame using the app's exact calibration tables.
  There is no physical save command.
- The app's request-progress state becomes active after 1500 ms, independently
  per recall; feedback target equality wins before flag checks. This is request
  UI state, not command acknowledgement or proof of movement. Disconnect cancels
  setters.

## Position Feedback

- Notifications are exactly 16 bytes and require byte 13 bit 5 clear.
- Pulse words at 3..4 (head) and 5..6 (foot) are little-endian; values >=32768
  are complemented (65535 minus the value).
- Conversion uses the nearest shipped table value, midpoint ties lower, head
  >15430 saturates at 60° and foot >11667 at 45°. The reported angles are table
  estimates.
- Byte 13 bit 0 and bit 1 are exposed as `app_head_flag` and `app_foot_flag`.
- The **App memory request** sensor (`active` or `inactive`) carries the app's
  request-progress state, with `app_memory_head_target`,
  `app_memory_foot_target`, `app_memory_progress_visible`, `app_head_flag` and
  `app_foot_flag` attributes. A request completes when the reported angles equal
  its target or neither flag is set.

### Calibration Tables

Pulse value per degree, used for targets and for feedback conversion.

| Head | +0 | +1 | +2 | +3 | +4 | +5 | +6 | +7 | +8 | +9 |
|---|---|---|---|---|---|---|---|---|---|---|
| 0° | 0 | 336 | 532 | 714 | 918 | 1108 | 1309 | 1508 | 1712 | 1915 |
| 10° | 2132 | 2324 | 2537 | 2748 | 2981 | 3197 | 3435 | 3663 | 3913 | 4151 |
| 20° | 4386 | 4649 | 4884 | 5158 | 5393 | 5669 | 5917 | 6192 | 6461 | 6748 |
| 30° | 7023 | 7296 | 7575 | 7851 | 8146 | 8409 | 8708 | 9018 | 9295 | 9591 |
| 40° | 9889 | 10173 | 10475 | 10772 | 11075 | 11357 | 11655 | 11940 | 12241 | 12520 |
| 50° | 12760 | 13116 | 13413 | 13701 | 14015 | 14286 | 14581 | 14859 | 15147 | 15430 |
| 60° | 15500 |  |  |  |  |  |  |  |  |  |

| Foot | +0 | +1 | +2 | +3 | +4 | +5 | +6 | +7 | +8 | +9 |
|---|---|---|---|---|---|---|---|---|---|---|
| 0° | 0 | 663 | 935 | 1206 | 1471 | 1730 | 1987 | 2260 | 2517 | 2767 |
| 10° | 3051 | 3329 | 3583 | 3843 | 4097 | 4365 | 4623 | 4895 | 5145 | 5425 |
| 20° | 5668 | 5938 | 6185 | 6455 | 6689 | 6951 | 7199 | 7443 | 7703 | 7943 |
| 30° | 8193 | 8435 | 8674 | 8918 | 9146 | 9379 | 9625 | 9859 | 10089 | 10304 |
| 40° | 10551 | 10774 | 11004 | 11211 | 11453 | 11667 |  |  |  |  |

## Actions

- The registered `set_position` and `set_positions` actions validate the fixed
  native ranges, back 0–60° and legs 0–45°, for every requested axis and
  physical target before scheduling movement. This also works from offline
  capabilities.
- Generic angle overrides do not change this app's calibration. A request for
  legs 35° followed by back 61° is rejected before either axis writes; other bed
  profiles retain their own limits.
- Covers use the already-declared 60° back and 45° legs calibration limits:
  their accepted endpoints show 100%, while 30° back and 15° legs show 50% and
  33%.

## Notifications / State

- The **App timer status** sensor reports only the accepted source statuses:
  -1=off, 1=10 minutes, 2=20 minutes, 3=30 minutes. Status byte `0xFF` is off.
  Unknown statuses leave the prior value unchanged.
- The parser does not infer acknowledgement, battery, physical motor count,
  light state or physical memory meaning.
- Incoming packets are not reassembled or given invented header/checksum guards.

| Length | Accepted when | Status from |
|--------|---------------|-------------|
| 16 | Byte 13 bit 5 clear | Byte 14 (signed) |

See the calibrated 16-byte parser in [Position Feedback](#position-feedback).
Timer status is signed byte 14. Other lengths are ignored.

## Command Timing

| Behavior | Sequence |
|----------|----------|
| `held` | Key frame at once, then every **100 ms** until bounded release; then the zero release frame |
| `pulse` | Key frame once, then the zero release frame after 300 ms (not used by this app) |
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
- Local angle edits change one degree every 200 ms and send only on release.
- This app has no clock writer or alarm-table contract.

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

### Serta Local Angle Edits

- Cancelling a local angle edit through Home Assistant sends the one calibrated
  target pulse that finishes the edit.
- A successful target write satisfies only the matching STOP cleanup, identified
  by its existing physical scheduler, STOP epoch and current BLE session. A
  normal completed edit, replacement, failed or interrupted write, or
  disconnected session cannot acknowledge a later STOP.
- Later genuine global STOPs retain the remote zero-key command. The card still
  sends its owning STOP immediately; it does not infer this protocol behavior.
- Local-edit cancellation acknowledgement also applies to this physical
  scheduler's paired GROUP reservation, including native Left/Right/Both
  targets. The same successful-write, STOP-epoch and current-session checks
  apply.

## Notes

### Home Assistant Adaptations

- The app-labelled buttons use the existing coordinator command scheduler and
  BLE lane.
- Disconnects invalidate handles, pending work and stale notifications. No
  Android mutable characteristic queue or stale-handle behavior is reproduced.

### Analysis Provenance

- Accepted artifact: `com.ore.serta330` version **1.1**.
- Artifact-set SHA-256:
  `dfef30206d9f0b61a56fbb74602c2a04bbbc388ab0eb933cd10084bfe5a65146`.
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
