# V-MAT Basic (Vibradorm)

**Status:** ❓ Needs testing (APK-verified, hardware **UNVERIFIED**)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- V-MAT-BASIC-RF (`basic` profile)
- V-MAT-BASIC-RF-CBI (`cbi` profile)
- V-MAT-BASIC-RF-CBI with XT-Box (`xtbox` profile)
- Controlled with the `com.vibradorm.vmatbasic` app. Sibling Vibradorm apps:
  [VMAT](vmat.md) and [Caresse / Werkmeister](vibradorm_app.md)

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [VIBRADORM Remote for Beds](https://play.google.com/store/apps/details?id=com.vibradorm.vmatbasic) (V-MAT Basic) 2.4.3 (code 14) | `com.vibradorm.vmatbasic` |

## Features

| Profile | Movement | Floor lighting | XT accessories |
|---|---|---|---|
| Basic (`basic`) | Back, legs, all up/down | None | None |
| CBI (`cbi`) | Same single-byte movement | Fresh-read toggle, level 0–255, timer 0–1439 minutes | None |
| CBI with XT-Box (`xtbox`) | Same single-byte movement | Held floor action, level 1–6, timer 0–255 minutes | Twenty-color mood palette, brightness 0–100%, three effects, speed 0–255, toggle/nightlight, six massage actions |

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (two named movement groups: back, legs; all up/down) |
| Position Feedback | ❌ (no position slider; ED is not a position parser) |
| Memory Presets | ❌ |
| Flat preset | ❌ (All-down is a direction, not a measured flat position) |
| Floor lighting | ✅ CBI and XT-Box (see table above) |
| Mood light | ✅ XT-Box only (palette choices; no arbitrary RGB) |
| Massage | ✅ XT-Box only (six literal actions; no intensity or measured massage state) |
| Diagnostics | ✅ (model, controller temperature, floor status, firmware, ED, signal) |
| Rename | ✅ |
| Linked pair | ⚠️ CBI and CBI with XT-Box at two addresses only |

- These are two named movement groups, not proof of physical motor topology. No
  head/feet/extra-axis, position slider, automatic flat preset, memory,
  arbitrary RGB, massage intensity or measured massage state is exposed.
- Generic motor count, angle sensing and pulse settings do not override the app
  profile.

## Protocol Details

Vendor UUIDs use suffix `-9f03-0de5-96c5-b8f4f3081186`.

| Role | Service | Characteristic |
|---|---|---|
| Movement | `00001525` + vendor suffix | `00001526` + vendor suffix |
| CBI floor read/write | Same control service | `00001529` + vendor suffix |
| XT write | Same control service | `00001550` + vendor suffix |
| ED read | `00001527` + vendor suffix | `00001531` + vendor suffix |
| Controller temperature read | Same status service | `00001532` + vendor suffix |
| Rename | GAP `1800` | Device Name `2a00` |
| Model / firmware read | DIS `180a` | `2a24` / `2a26` |

**Format:** One-byte movement; three-byte CBI floor; `00 11` / `00 77` prefixed XT frames

- Every selected receiver must expose the control service, status service and
  GAP before control starts. DIS is optional: missing DIS fails only its
  diagnostic fields.
- The first exact service and then first exact characteristic within it are
  authoritative.

### Write Mode

Writes require the response-capable write property and use `response=True`. No
arbitrary characteristic fallback, write-without-response downgrade,
notification subscription, position request, checksum, crypto, fragmentation or
MTU command is added.

## Detection / Setup

- Select **Vibradorm: VMAT, Caresse Diamant, Werkmeister, V-MAT Basic**, then
  **V-MAT Basic** and the product explicitly: V-MAT-BASIC-RF,
  V-MAT-BASIC-RF-CBI, or V-MAT-BASIC-RF-CBI with XT-Box.
- Existing entries keep their controllers until a
  [guided reconfigure](../CONFIGURATION.md#vibradorm-guided-setup-and-migration)
  succeeds and you confirm it.
- A shared Bluetooth identifier, device name or model string cannot choose one
  of these profiles.
- The dedicated app bed type keeps these accepted profiles separate from the
  existing generic and Caresse/Werkmeister routes; it is a Home Assistant
  configuration boundary, not an inferred protocol identity.

### Discovery

- The source scan predicate uses the first raw manufacturer AD record, ignores
  its company ID, and checks `ba be` followed by low nibbles 1/1. The safe raw
  parser preserves that first-record rule.
- HA's manufacturer map loses AD order, duplicates and declared lengths, even
  with one company: diagnostics report conditional per-record matches and keep
  the exact source scan verdict unknown.
- A conditional candidate hint cannot infer a profile. Existing cached-address
  selection remains explicit; rename and optional model strings are not identity
  proof.

### Pairing

Bonded status is advisory in this app. The integration does not invent native
bonding, a PIN, authentication exchange or authenticated-GATT proof.

## Commands

### Motor Control

Written to `00001526` (Movement).

| Command | `hold_control` | Byte |
|---------|----------------|------|
| All up | `all_up` | `10` |
| All down | `all_down` | `00` |
| Back up | `back_up` | `0b` |
| Back down | `back_down` | `0a` |
| Legs up | `legs_up` | `09` |
| Legs down | `legs_down` | `08` |
| Release | | `ff` |

### Floor light

| Command | Characteristic | Bytes |
|---------|----------------|-------|
| CBI floor settings | `00001529` | Level U8 plus timer BE16 |
| CBI toggle OFF | `00001529` | `00 00 00` (all-zero OFF) |
| XT floor settings | `00001550` | `00 11 level minutes` |
| XT floor hold (`floor_hold`) | `00001550` | `00 11`, repeated; no release frame |

### Mood light (XT-Box)

XT mood uses group `00 77`, written to `00001550`.

| Command | Bytes |
|---------|-------|
| Color | `00 77 01 00 R G B` |
| Effects 1–3 | `00 77 08 01` through `03` |
| Speed | `00 77 09 ((progress + 1) & ff)` |
| Toggle | `00 77` |
| Nightlight | `00 77 01 00 00 00 00` |

- Progress 255 deliberately encodes zero.
- The palette uses the APK's HSV conversion and truncation; the tests preserve
  all 2,020 palette/brightness outputs.

### Massage (XT-Box)

| Command | Bytes |
|---------|-------|
| Back | `00 2c` |
| Legs | `00 2d` |
| Off | `00 34` |
| Programs 1–3 | `00 31`, `00 28`, `00 29` |

Motor STOP does not turn massage off. Power, effect, speed and massage feedback
are unknown; successful writes publish requested intent only.

### Rename

`rename` writes UTF-8 to GAP Device Name `2a00`; see
[Separate receivers and rename](#separate-receivers-and-rename).

## Command Timing

- Ordinary movement buttons hold for one second as a bounded Home Assistant
  policy.
- `hold_control` accepts `all_up`, `all_down`, `back_up`, `back_down`,
  `legs_up`, `legs_down`, and XT-only `floor_hold`, with 0.1–60 seconds in whole
  milliseconds.
- The source refreshes held movement at 30 ms scheduling attempts; this is not a
  guaranteed on-air cadence.
- A fresh `ff` release follows admitted movement on completion, cancellation or
  failure, with bounded cleanup. All-down is a direction, not a measured flat
  position.
- XT floor hold repeats `00 11` and stops by ending the stream; no separate
  release frame is proven.

## Floor and mood state

### Floor

- CBI toggle reads the current three-byte floor status first. A positive level
  sends all-zero OFF; zero sends the saved level and timer.
- A missing ON-button level defaults to 255, whereas the settings screen's
  absent level is zero. An explicitly saved zero stays zero. A failed or short
  read cannot select a toggle branch from stale state.
- Floor settings are applied immediately, including timer changes.
- Requested settings persist per physical receiver through HA configuration;
  observed level, minutes and derived percent are separate read-backed
  diagnostic values.
- XT's public range stays within its shipped UI even though the raw builder has
  upper clamps. No measured ON/OFF state is inferred from a successful write.

### Mood

- Mood starts with white and 100% brightness in a cold control session.
- A typed exact-address process holder preserves the selected color/brightness
  across BLE reconstruction within HA's continuous control session. Profile
  changes reset that holder; another physical receiver cannot share it.
- Admitted color construction retains local intent even if delivery fails,
  while public requested state is published only after a successful write. This
  preserves the dependency of the next brightness/color command without claiming
  a hardware acknowledgment.
- The six massage buttons are separate literal actions, with no invented toggle
  state.

## Diagnostics

- Initial diagnostics and three-second refresh attempts read model, controller
  temperature, floor status, firmware, then ED.
- Each operation has an 800 ms host deadline; a failed field becomes unknown and
  later fields can still refresh.

| Field | Decoding |
|-------|----------|
| Temperature | Signed LE32 divided by four minus seven degrees Celsius |
| Floor | Level U8 and timer BE16; percent is level × 100 / 255 |
| ED | Bit zero of the first byte; not a position parser |
| Strings | Java UTF-8 replacement semantics without trimming |

- Background reads use an already live connection, yield to commands, preserve
  the existing idle disconnect deadline, and stop/invalidate on disconnect. They
  do not reconnect or keep an idle receiver awake.
- Immediate/two-second signal samples use HA advertisement history, with scanner
  source and observation timestamp attributes. They are not remote GATT RSSI
  reads; unavailable or invalidated signal remains unknown. Signal strength never
  chooses a receiver or adds a connection prerequisite.

## Separate receivers and rename

### Linked pair

- Combine two independently configured CBI or CBI with XT-Box receivers at
  distinct addresses only when linked movement is wanted. The Basic profile has
  no linked control. Each side retains its explicit profile and settings.
- Movement on both sides requires both concurrent physical GATT sessions
  validated before either starts. A failed receiver, cancellation, disconnect or
  sequential fallback cannot release a partial group. Separate-side commands
  remain independent. Single-address pairing is unsupported.
- Only movement and its release mirror across a linked pair. Floor, mood,
  massage, reads and rename belong to one physical child unless the user
  explicitly addresses another independently configured child.
- `floor_hold` and `rename` reject a multi-target request before writing.
- Split a pair to change its per-side profile, then combine it again.

### Rename

- `rename` trims code points up to U+0020, allows an empty name, and limits the
  result to ten UTF-16 units.
- UTF-8 is written without a terminator. A further host safety limit of 20
  encoded bytes avoids inventing fragmentation.
- Save the confirmed name only after the write succeeds; failed delivery leaves
  the stored name unchanged.

## Notes

### Deferred validation

Physical packet delivery, movement effects, floor timing/scales, mood and
massage effects, rename persistence, temperature interpretation, optional read
support, dual connection behavior and security remain deferred user validation
after beta/release. Static acceptance does not claim those hardware outcomes.

Hardware status: **UNVERIFIED**.

### Analysis provenance

- The protocol comes from the accepted `com.vibradorm.vmatbasic` 2.4.3 APK,
  version code 14.
- Artifact-set SHA-256: `5d266015494edf9ad595c5b4c6d11fcde3ea53fc78e008b4990e4ce834a31980`
- Accepted repair report manifest: `5d73627f5b010b372b3cdec39091faa817a4a596ead49db9ec507ee6025a5d0d`
- Independent audit manifest: `7892663c50ea99a3174bfa1fd86cd27ed276ef4be1270bf256ac13133a0c155b`
- All package evidence stays machine-local. The
  [row037 disposition ledger](../apk-analysis/row037-dispositions.md) records the
  separate implementation comparison.
- Current code and focused executed tests cover the accepted behavior. Workflow
  progress is recorded in the canonical APK audit trackers and published queue
  plan.
