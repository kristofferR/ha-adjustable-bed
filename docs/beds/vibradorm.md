# Vibradorm

**Status:** ✅ Tested (generic controller); the Caresse, Werkmeister, VMAT and V-MAT Basic app profiles have artifact-verified behavior and need testing (hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

> [!NOTE]
> Existing generic entries keep their controller unless you explicitly select an
> app profile. Shared Bluetooth identifiers, device names and model strings do not
> identify an app or its remote layout.

## Known Models

- Vibradorm VMAT series beds; device names starting with "VMAT" (e.g.,
  "VMATMEM047"); `VMAT-BASIC-RF-CBI` beds (some use the secondary service):
  [generic controller](#generic-controller)
- Vibradorm beds operated by Caresse Remote (Caresse Diamant) or Werkmeister
  Unterfederung; Werkmeister remote images `cdl_bf_11_21_374_vi` (control type 5)
  and `cdl_cf_17_21_382_vi` (control type 7):
  [Caresse and Werkmeister](#caresse-and-werkmeister)
- Vibradorm receivers controlled with the VMAT app (`de.vibradorm.vmat`), with the
  fourteen shipped VMAT remote selections in the
  [remote table](#vmat-remote-selection). Resource names identify shipped images,
  not proven physical products: [VMAT](#vmat)
- V-MAT-BASIC-RF (`basic` profile), V-MAT-BASIC-RF-CBI (`cbi` profile) and
  V-MAT-BASIC-RF-CBI with XT-Box (`xtbox` profile), controlled with the
  `com.vibradorm.vmatbasic` app: [V-MAT Basic](#v-mat-basic)
- Advertisement, DIS strings, service/characteristic presence and remote artwork
  cannot choose a profile or actuator layout.

## Apps

| Analyzed | App | Package ID | Profile |
|----------|-----|------------|---------|
| ✅ | [VIBRADORM Remote](https://play.google.com/store/apps/details?id=de.vibradorm.vra) | `de.vibradorm.vra` | [Generic controller](#generic-controller) |
| ✅ | [VIBRADORM Remote for Beds](https://play.google.com/store/apps/details?id=com.vibradorm.vmatbasic) (V-MAT Basic) 2.4.3 (code 14) | `com.vibradorm.vmatbasic` | [Generic controller](#generic-controller), [V-MAT Basic](#v-mat-basic) |
| ✅ | [Caresse Remote](https://play.google.com/store/apps/details?id=de.vibradorm.diamant) 0.3, code 3 | `de.vibradorm.diamant` | [Caresse and Werkmeister](#caresse-and-werkmeister) |
| ✅ | [Werkmeister Unterfederung](https://play.google.com/store/apps/details?id=de.vibradorm.werkmeister) 0.2, code 2 | `de.vibradorm.werkmeister` | [Caresse and Werkmeister](#caresse-and-werkmeister) |
| ✅ | [VIBRADORM Remote](https://play.google.com/store/apps/details?id=de.vibradorm.vmat) (VMAT) 1.11 (49) | `de.vibradorm.vmat` | [VMAT](#vmat) |

- The generic controller's protocol comes from the VIBRADORM Remote and
  VIBRADORM Remote for Beds apps.
- [v4.1.0](https://github.com/kristofferR/ha-adjustable-bed/releases/tag/v4.1.0)
  includes separate, explicitly selected app profiles. Follow the section for the
  app and remote you use; capabilities and packet behavior are profile-specific.
- Each app profile was verified independently. VMAT has its own remote table,
  setup stages, GATT rules and accessory conversion values, and does not inherit
  the Caresse and Werkmeister protocol defaults merely because transport
  identifiers match. Caresse / Werkmeister and V-MAT Basic have their own
  independent feature gates, vectors and dispositions.
- The [issue #403 reconciliation](#issue-403-reconciliation) explains which
  parts of the original parity request shipped and which were ruled out by the
  accepted app audits. Those audits do not establish live position or EEPROM
  support for the Caresse, Werkmeister or VMAT app profiles.
- APK hashes and seals are under [Analysis provenance](#analysis-provenance).

## Features

| Feature | Generic controller | Caresse / Werkmeister | VMAT | V-MAT Basic |
|---------|--------------------|-----------------------|------|-------------|
| Motor Control | ✅ (2, 3 or 4 configured motor groups) | ✅ (held app movement groups per profile; see [explicit profiles](#explicit-profiles-and-retained-state)) | ✅ (logical groups per remote; All Up/All Down) | ✅ (two named movement groups: back, legs; all up/down) |
| Position Feedback | ⚠️ (legacy notification handling on compatible variants; angle estimates) | ❌ (no live position, EEPROM or motor-status parser) | ❌ (no live position parser proven) | ❌ (no position slider; ED is not a position parser) |
| Memory Presets | ✅ (6 slots) | ⚠️ (6 programmable on CBI layouts; 3 recalls on the basic seat state; none on fresh Caresse) | ✅ (six slots on remotes 07–11 and 13) | ❌ |
| Flat Preset | ✅ | ❌ (All-down is held movement toward flat, not a self-completing preset) | ❌ (All Down is movement, not a timed flat preset) | ❌ (All-down is a direction, not a measured flat position) |
| Light Control / Floor light | ✅ | ✅ (Werkmeister; Caresse restored flag) | ✅ (level 0–8 and timer on remotes 01, 04–10) | ✅ CBI and XT-Box (see the product table below) |
| Mood light | ❌ | ✅ (Caresse restored RGB only: 18-color palette, three effects, speed) | ✅ (remotes 12/13: 18 palette choices, three effects, speed 0–8) | ✅ XT-Box only (palette choices; no arbitrary RGB) |
| Massage | ✅ (vibration toggle via CBI characteristic) | ✅ (Caresse restored massage only) | ✅ (remotes 12/13: automatic/individual modes, zones, waves, speed) | ✅ XT-Box only (six literal actions; no intensity or measured massage state) |
| Sync | ❌ | ✅ (Werkmeister type 7 only) | ✅ (remotes 07–11, reply-gated held action) | ❌ |
| Device information / diagnostics | ❌ | ✅ (DIS strings; article requests on types 5/6/7) | ✅ (DIS strings; onboarding stages) | ✅ (model, controller temperature, floor status, firmware, ED, signal) |
| Native bond | ❌ | ✅ (information-before-bond onboarding) | ✅ (positive native bond evidence required) | ❌ (bonded status is advisory) |
| Rename | ❌ | ❌ | ❌ | ✅ |
| Linked pair | ❌ | ❌ | ❌ | ⚠️ CBI and CBI with XT-Box at two addresses only |
| Battery, firmware update, calibration | ❌ | ❌ | ❌ (not proven) | ❌ |
| Hold until release | ❌ | ✅ ([renewable](../SERVICES.md#renewable-holds) `timed_move` and `hold_control`: 100 ms refresh, then STOP) | ✅ ([renewable](../SERVICES.md#renewable-holds) `timed_move` and `hold_control`, through the Vibradorm app profile) | ✅ ([renewable](../SERVICES.md#renewable-holds) `timed_move` and `hold_control`, then STOP) |

**Generic motor configurations:** the generic controller offers 2, 3, or 4
configured motor groups. The standard 2-motor configuration has back and legs
controls.

**V-MAT Basic products:**

| Profile | Movement | Floor lighting | XT accessories |
|---|---|---|---|
| Basic (`basic`) | Back, legs, all up/down | None | None |
| CBI (`cbi`) | Same single-byte movement | Fresh-read toggle, level 0–255, timer 0–1439 minutes | None |
| CBI with XT-Box (`xtbox`) | Same single-byte movement | Held floor action, level 1–6, timer 0–255 minutes | Twenty-color mood palette, brightness 0–100%, three effects, speed 0–255, toggle/nightlight, six massage actions |

- V-MAT Basic exposes two named movement groups, not proof of physical motor
  topology. No head/feet/extra-axis, position slider, automatic flat preset,
  memory, arbitrary RGB, massage intensity or measured massage state is exposed.
- Generic motor count, angle sensing and pulse settings do not override an app
  profile.

## Choosing a profile

Detection suggests the generic `vibradorm` bed type (see
[Generic controller](#generic-controller)). The app profiles are explicit
choices: the bed-type picker has one **Vibradorm: VMAT, Caresse Diamant,
Werkmeister, V-MAT Basic** entry. Choose the app you use on your phone, then its
remote or product, or **Legacy setup** for the generic controller. Each profile
keeps its own command table and timing; none reuses a sibling's.

<!-- generated:vibradorm-profiles -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Profile key | Bed type | Chosen by | Section |
|---|---|---|---|
| `legacy` | `vibradorm` | detection or **Legacy setup** | [Generic controller](#generic-controller) |
| `caresse` | `vibradorm_app` | `vibradorm_app_profile` = Caresse Diamant | [Caresse and Werkmeister](#caresse-and-werkmeister) |
| `werkmeister` | `vibradorm_app` | `vibradorm_app_profile` = Werkmeister | [Caresse and Werkmeister](#caresse-and-werkmeister) |
| `vmat` | `vibradorm_app` | `vibradorm_app_profile` = VMAT | [VMAT](#vmat) |
| `basic` | `vmatbasic` | `vmatbasic_profile` = V-MAT-BASIC-RF | [V-MAT Basic](#v-mat-basic) |
| `cbi` | `vmatbasic` | `vmatbasic_profile` = V-MAT-BASIC-RF-CBI | [V-MAT Basic](#v-mat-basic) |
| `xtbox` | `vmatbasic` | `vmatbasic_profile` = V-MAT-BASIC-RF-CBI with XT-Box | [V-MAT Basic](#v-mat-basic) |
<!-- /generated -->

### Guided setup and migration

The bed-type list has one **Vibradorm: VMAT, Caresse Diamant, Werkmeister,
V-MAT Basic** choice. Choose the app you use on your phone, then its remote or
product. **Legacy setup** remains available inside this choice for fresh setup,
and in Reconfigure an app or V-MAT Basic entry can move back to it.
The family choice shares setup navigation, while each selected app keeps its
existing controller, features and Bluetooth pairing requirements.

For an existing bed, open **Settings → Devices & services → Adjustable Bed**,
then the entry's three-dot menu and **Reconfigure** (see
[Changing the app or layout](../CONFIGURATION.md#changing-the-app-or-layout-of-an-existing-bed)).
The app review in Repairs opens the same wizard. Choose **Keep current setup**
to keep your working controls and answer the review, or choose your app and
remote/product.
Keeping the same app seeds the form with your saved settings.

The wizard temporarily releases Home Assistant's connection to check the chosen
setup. It checks the exact app's required Bluetooth roles and existing pairing
requirements, without moving the bed. A missing scanner, failed check or link
that cannot be closed cannot save the new selection. Retry or keep the current
setup. Closing the wizard leaves the saved configuration and pending review
unchanged. A failed connection remains owned until it is observed closed, so
another setup attempt cannot overlap it.

After a successful check, a final review shows the chosen app and
remote/product, and the controls it adds and removes. Saving keeps the entry,
address, device and unchanged entity IDs. Controls follow the selected profile;
obsolete controls and angle estimates may disappear. This check does not prove physical movement, lighting or massage
behavior. If settings changed in another window, the wizard refuses to overwrite
them. Routine brightness, timer and connection changes remain in **Configure**.

A paired bed must first be split explicitly, or have its standalone controls
restored for a one-address pair. The wizard offers the existing reversible split
action and preserves identities. Each receiver keeps its current connection
preferences and gets back its original bed settings. Afterwards,
reconfigure the intended receiver separately and combine compatible beds again
if needed. It never assigns one app/remote to both receivers or guesses from
Bluetooth identifiers or motor count.

### Aliases

None. Each bed type builds its own controller and profile.

## Wire codec

`codec/vibradorm.py` holds the GATT roles and frames every Vibradorm app shares.
Which commands, parameters, toggle rules and timing an app uses belongs to its
profile (`profiles/vibradorm.py` for the generic route and the Caresse,
Werkmeister and VMAT apps, `profiles/vmatbasic.py` for V-MAT Basic).

### Transports

Vendor UUIDs use `0000XXXX-9f03-0de5-96c5-b8f4f3081186`. Device Information uses
the standard service `180a` and characteristics `2a24`, `2a26` and `2a28`;
V-MAT Basic renames through GAP `1800` Device Name `2a00`.

<!-- generated:vibradorm-transports -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Role | UUID | Used by |
|---|---|---|
| Control service | `00001525-9f03-0de5-96c5-b8f4f3081186` | generic; VMAT (exact service); V-MAT Basic |
| Motor | `00001526-9f03-0de5-96c5-b8f4f3081186` | generic; basic app layouts; V-MAT Basic |
| Light | `00001529-9f03-0de5-96c5-b8f4f3081186` | generic; basic app layouts; V-MAT Basic CBI |
| CBI (V-MAT Basic: XT) | `00001550-9f03-0de5-96c5-b8f4f3081186` | every profile but V-MAT Basic `basic` and `cbi` |
| Response | `00001551-9f03-0de5-96c5-b8f4f3081186` | generic; nonbasic app layouts; VMAT |
| Status service | `00001527-9f03-0de5-96c5-b8f4f3081186` | generic (secondary service); VMAT; V-MAT Basic |
| ED | `00001531-9f03-0de5-96c5-b8f4f3081186` | V-MAT Basic |
| Temperature | `00001532-9f03-0de5-96c5-b8f4f3081186` | V-MAT Basic |
| Management | `00001533-9f03-0de5-96c5-b8f4f3081186` | VMAT setup |
<!-- /generated -->

How each profile resolves these roles, and its write mode, is in its Setup
section: the generic controller resolves aliases and fallbacks, while the app
profiles accept only exact roles.

### Framing and checksum

| Frame | Characteristic | Layout |
|-------|----------------|--------|
| Motor | Motor `1526` | One command byte; `FF` is STOP |
| Light | Light `1529` | `level minutes_hi minutes_lo`: a level byte and big-endian 16-bit timer minutes |
| Command (CBI) | CBI `1550` | Big-endian 16-bit command word ORed with the toggle bit `T` (0 or `8000`), then the parameter bytes |

- The generic controller and every app profile build these frames with the same
  encoders; the app-specific part is which word, parameters and toggle they pass.
- No profile adds a checksum, framing, encryption, MTU operation, side byte or
  fragmentation. Every shipped frame fits the mandatory BLE MTU of 23.
- The toggle bit is an app rule, not a codec one: the generic controller
  alternates it on each CBI send; the Caresse, Werkmeister and VMAT apps consume it
  per logical construction (see [Toggle bit T](#toggle-bit-t)); V-MAT Basic never
  sets it.

### Command encoders

Each profile's command table is generated from its profile data through these
encoders:

- [Generic controller commands](#generic-commands)
- [Caresse, Werkmeister and VMAT motor and memory frames](#motor-and-memory-opcode-index)
- [V-MAT Basic commands](#v-mat-basic-commands)

### Responses

| Response | Characteristic | Parsed by |
|----------|----------------|-----------|
| Motor status reply: `20 3f flags` or `3f flags`, then big-endian 16-bit motor counts | Response `1551` | Generic controller: raw positions ([position feedback](#position-feedback)); Werkmeister type 7 and VMAT sync remotes: flag `40` only ([sync replies](#sync-replies)) |
| Article reply, prefix `21a0c8` | Response `1551` | Caresse / Werkmeister information transaction |
| Onboarding stage replies | Response `1551` | VMAT setup ([onboarding](#vmat-onboarding)) |
| Light status (the light frame layout) | Light `1529`, read | V-MAT Basic diagnostics and CBI floor toggle |
| Temperature, ED | Status `1532`, `1531`, read | V-MAT Basic diagnostics |

Text replies and Device Information strings decode with Java's UTF-8
replacement rules, including encoded surrogates. Caresse and Werkmeister then trim
code units up to U+0020 from the edges of the standard information strings;
VMAT and V-MAT Basic keep whitespace and NULs.

### STOP and release behavior

| Profile | Release | Notes |
|---------|---------|-------|
| Generic controller | Motor `FF`, with a fresh cancel signal | Sent after every movement, flat and memory recall |
| Caresse / Werkmeister, VMAT | Motor `FF` on basic layouts; CBI `00 FF` otherwise | STOP never carries or advances `T` |
| V-MAT Basic | Motor `FF` | Sent after admitted movement; XT `floor_hold` has no release frame |

### Vectors

`tests/vibradorm_vectors.py` freezes every fixed frame each profile sends, by
characteristic, and the value frames from the artifact fixtures
(`tests/fixtures/vibradorm_vmat_vectors.json`,
`tests/fixtures/vmatbasic-vectors.json`). `tests/test_vibradorm_vectors.py`
checks that every literal round-trips through the codec and that each profile
sends exactly its frozen fixed frames.

## Profiles

### Generic controller

**Status:** ✅ Tested

This is the existing generic Vibradorm route (`legacy` profile, bed type
`vibradorm`). Existing entries keep that controller unless you explicitly select an
app profile.

#### Setup

Detection:

1. **Manufacturer ID:** 944 (0x03B0), highest priority
2. **Service UUID:** `00001525-...` or `00001527-...`
3. **Device name pattern:** names starting with "VMAT"

These are generic discovery hints, not proof of an app, remote layout or every
optional feature.

Choose **Legacy setup** inside the **Vibradorm: VMAT, Caresse Diamant,
Werkmeister, V-MAT Basic** entry for this controller, which then asks the motor
count, whether massage motors are fitted and whether to read positions before
pairing. Existing entries keep their saved controller until you explicitly
reconfigure them. See the [guided setup and migration](#guided-setup-and-migration).

Characteristics:

- **Primary service:** `00001525-9f03-0de5-96c5-b8f4f3081186`
- **Secondary service (some VMAT-BASIC-RF-CBI beds):** `00001527-9f03-0de5-96c5-b8f4f3081186`
- **Command characteristic:** `00001526-9f03-0de5-96c5-b8f4f3081186` (fallbacks: `00001528`, `00001534`)
- **Light, CBI and notify characteristics:** `1529`, `1550` and `1551`, as in [Transports](#transports)
- The controller also resolves these roles through proxy-normalized Bluetooth
  base UUID aliases of the same short UUIDs.

Write mode:

- The controller writes with response when the resolved characteristic advertises
  `write`, and without response when only `write-without-response` is advertised.
- When a proxy surfaces the exact VMAT UUID without usable property metadata, it
  prefers write with response, which the native apps use for these control paths.
- The `VMAT-BASIC-RF-CBI` model drives movement only through `0x1526`; the
  `00001528`/`00001534` fallbacks are not probed for it.

#### Controls

##### Generic commands

Motor names come from German: K = Kopf (head/back), OS = Oberschenkel
(thigh/legs), N = Nacken (neck), F = Fuß (foot), H = Hoch (up), R = Runter (down).

<!-- generated:vibradorm-generic-commands -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Command | Motor frame | Description |
|---|---|---|
| Stop | `FF` | Stops all motors |
| Head Up (KH) | `0B` | back; also head on 2-motor beds |
| Head Down (KR) | `0A` | back; also head on 2-motor beds |
| Legs Up (OSH) | `09` | also feet on 2/3-motor beds |
| Legs Down (OSR) | `08` | also feet on 2/3-motor beds |
| Neck Up (NH) | `03` | head on 3/4-motor beds |
| Neck Down (NR) | `02` | head on 3/4-motor beds |
| Foot Up (FH) | `05` | feet on 4-motor beds |
| Foot Down (FR) | `04` | feet on 4-motor beds |
| All Down/Flat (AR) | `00` | used as the flat preset |
| Memory 1 | `0E` | recall |
| Memory 2 | `0F` | recall |
| Memory 3 | `0C` | recall |
| Memory 4 | `1A` | recall |
| Memory 5 | `1B` | recall |
| Memory 6 | `1C` | recall |

| Command | CBI frame, T = 0 / T = 8000 |
|---|---|
| Store | `00 0D` / `80 0D` |
| Save memory 1 | `00 0E` / `80 0E` |
| Save memory 2 | `00 0F` / `80 0F` |
| Save memory 3 | `00 0C` / `80 0C` |
| Save memory 4 | `00 1A` / `80 1A` |
| Save memory 5 | `00 1B` / `80 1B` |
| Save memory 6 | `00 1C` / `80 1C` |
| Vibration on | `00 34 01` / `80 34 01` |
| Vibration off | `00 34 00` / `80 34 00` |
| CmdGetStatusMotMon | `00 3D 3F` / `80 3D 3F` |

| Command | Light frame |
|---|---|
| Light on | `FF 00 00` |
| Light off | `00 00 00` |
<!-- /generated -->

- Recall sends the memory byte to the motor characteristic. Saving follows the
  app's store sequence: STORE four times to the CBI characteristic, each with the
  toggle bit; the memory slot word to the CBI characteristic, with the toggle bit;
  then STOP (`0xFF`) four times to the motor characteristic.
- Light frames carry `[brightness, 0x00, timer]`: brightness 0 is off and 0xFF
  full brightness; the timer is an auto-off value (0 = no timer). The generic
  on/off actions send only levels 0/0xFF and timer 0. Adjustable brightness and
  timers belong to the app profiles that explicitly support them. The toggle
  follows the last on/off command HA sent.
- Vibration on/off is `[MSB(T | 0x34), LSB(T | 0x34), 01]` / `[..., 00]` on CBI.
  The vibration toggle alternates on and off from HA's last command.
- `T` is the CBI toggle bit, alternating between `0x0000` and `0x8000` on each
  CBI send.
- CmdGetStatusMotMon `[MSB(T | 0x3D), LSB(T | 0x3D), 0x3F]` on CBI mirrors the
  app's SYNC button and asks the bed to send a position notification. It is
  skipped for `VMAT-BASIC-RF-CBI`.

#### Timing

- Motor movement uses the configured pulse settings, by default 10 writes at
  100 ms, and always sends STOP (`0xFF`) at the end with a fresh cancel signal.
- Flat and memory recall are hold-to-run: the bed moves only while the command is
  sent. HA sends it up to 200 times at 100 ms (20 s), enough for the slowest
  motors (about 14 s of full travel), then sends STOP. The bed stops on its own at
  the stored position; a STOP request ends the command early.
- Movement-time position polling is disabled, because interleaving CBI status
  requests with hold-to-run commands can cause stutter or premature motor stops.

#### Notifications

##### Position feedback

The generic controller decodes raw encoder counts and scales them into angle
estimates using estimated raw travel limits and the configured maximum angles.
These are not measured degrees or device-reported percentages. This path is
disabled for the `VMAT-BASIC-RF-CBI` model. It is separate from the explicitly
selected app profiles.

The parser accepts the [motor status reply](#responses): `20 3f flags` followed
by big-endian 16-bit counts, or the short `3f flags` form:

| Axis | Long-form bytes | Short-form bytes |
|------|-----------------|------------------|
| Back | 3–4 | 2–3 |
| Legs | 5–6 | 4–5 |
| Head, when configured | 7–8 | 6–7 |
| Feet, when configured | 9–10 | 8–9 |

- Byte indices are zero-based.
- Higher counts mean more raised; 0 is flat.
- Each count becomes a percentage of the estimated raw travel for that axis, then
  an angle estimate. The initial travel estimates are 7000 (back, head) and 14000
  (legs, feet), raised whenever a larger count is observed.
- Other notifications (for example `20EF` or `21A0`) are logged for diagnostics
  but otherwise ignored.
- Earlier versions of this document described the counts as little-endian; the
  current parser reads them big-endian.

This describes the current implementation in
[`VibradormController`](../../custom_components/adjustable_bed/beds/vibradorm.py),
covered by `TestVibradormPositionFeedback` in
[`test_vibradorm.py`](../../tests/test_vibradorm.py). It does not establish a
calibrated physical angle, initialization-state handling or equivalent position
support in another app profile.

#### Evidence

The generic controller sends exactly the `legacy` frames in
`tests/vibradorm_vectors.py`, as the pre-v5 controller did. Its protocol comes
from the VIBRADORM Remote (`de.vibradorm.vra`) and V-MAT Basic apps; it is tested
on hardware.

### Caresse and Werkmeister

**App:** [Caresse Remote](https://play.google.com/store/apps/details?id=de.vibradorm.diamant) 0.3, code 3, `de.vibradorm.diamant`; [Werkmeister Unterfederung](https://play.google.com/store/apps/details?id=de.vibradorm.werkmeister) 0.2, code 2, `de.vibradorm.werkmeister`

**Status:** ❓ Needs testing (static artifact behavior verified; hardware unverified)

The bed type is `vibradorm_app` with app profile `caresse` or `werkmeister`. The
independently verified [VMAT](#vmat) profile shares the explicit app configuration
entry point, with its own remote table, setup stages, GATT rules and accessory
conversion values. Existing generic entries retain their current controller and
position behavior.

#### Setup

For fresh setup, choose **Vibradorm: VMAT, Caresse Diamant, Werkmeister,
V-MAT Basic**, then **Caresse Diamant** or **Werkmeister** and the matching
remote/settings. Existing entries use the
[guided reconfigure](#guided-setup-and-migration), which keeps the current
configuration saved until verification and confirmation. Detection: none; the
profile is an explicit choice.

##### Explicit profiles and retained state

Preserve generic Vibradorm behavior for existing entries. An explicit app/product
profile selects a separate `VibradormAppController`; advertisement, DIS strings,
service/characteristic presence and remote artwork cannot choose a profile or
actuator layout.

| App/state | Control | Named movement groups | Transport | Memory | Optional features |
|---|---:|---|---|---|---|
| Caresse fresh shipped selection |2|back,legs|COMMAND single byte|0|all false|
| Werkmeister remote image cdl_bf_11_21_374_vi |5|back,legs|CBI two bytes|6 programmable|floor light; sync inert; RGB/massage/extension false|
| Werkmeister remote image cdl_cf_17_21_382_vi |7|head/neck,back,legs,feet|CBI two bytes|6 programmable|floor light and sync; RGB/massage/extension false|
| Caresse explicit restored state |2|back,legs|COMMAND|0|independent persisted floor/RGB/massage/extension flags|
| Caresse explicit restored seat state |3|head/neck,back,legs|COMMAND|3 recalls; no save menu|same flags|
| Caresse explicit restored state |0 or 5|back,legs|CBI|6 programmable|same flags; article only 5|
| Caresse explicit restored state |4 or 6|head/neck,back,legs|CBI|6 programmable|same flags; article only 6|
| Caresse explicit restored state |-1, 1 or 7|head/neck,back,legs,feet|CBI|6 programmable|same flags; article only 7|
| Caresse explicit restored layout without motor controls |outside{-1,0,1,2,3,4,5,6,7}|none|CBI|6 programmable|same flags; no article transaction|

- The last row uses the explicit `other` sentinel for the source default switch
  branch. It has no motor controls; unknown numeric values are rejected.
- For Caresse restored type 2 is allowed: feature flags are independent persisted
  reads. Do not constrain restored states solely to non-normal control values.
- Fresh selection is type 2/all false.
- Werkmeister accepted own-selector scope is 5/7; its dead selectors/features are
  excluded and are not promoted into supported Werkmeister options by Caresse
  evidence.
- All counts above describe app movement groups. They do not prove physical motor
  topology.
- Hide conflicting generic motor-count/has-massage/angle/repeat-delay options for
  explicit profiles; derive exposed groups and limits from the chosen profile.
- Restore/profile changes must rebuild forms in every setup and options path
  while preserving entered suggestions, then persist the exact profile.
- Changing restored mode discards cached process intent for that physical
  address, so the rebuilt controller uses the selected mode's remembered-value
  defaults. Ordinary options edits preserve the same-address intent and
  diagnostic metadata.
- Explicit advanced restored settings must explain that they describe retained
  app paths rather than a verified hardware product.

##### Characteristic identities

These app paths use the COMMAND (motor `1526`), LIGHT (`1529`), CBI (`1550`) and
CBI response (`1551`) roles of the [transport table](#transports).

- These app paths select exact characteristics across services. No fixed parent
  service, guessed writable fallback or base-UUID alias is proven.
- COMMAND/LIGHT/CBI/CBI_RESPONSE are exact characteristic identities; service
  membership is not an app requirement.
- Select the first requested exact characteristic in native service order, and
  retain that selected object for the actual read/write/notification operation.
- No arbitrary writable/notifiable or `1528`/`1534`/proxy-base alias fallback is
  proven for these app profiles.
- Validate actual operation properties and use the selected host backend's write
  semantics.
- The application inherits runtime native write properties/type: the APK leaves
  Android native write type/property metadata at runtime, so it does not prove a
  universal response=False/True mode.
- Home Assistant's declared property-based transport policy is host behavior, not
  evidence of a fixed Android response mode.

##### Advertisement diagnostics and target selection

- The source SDK selects the first record in an ordered manufacturer list. It
  masks the company ID to 16 bits and accepts `03b0` or `ffff`; absent SDK
  company is -1 and becomes `ffff`. Payload excludes the little-endian company ID.
- Customer derivation is null → `fffe`, length ≤ 6 → `ffff`, length 7–9 →
  `fffe`, otherwise big-endian bytes 4–5. Identifier uses big-endian bytes 0–1;
  VibFlags combine the high nibble of byte 2 with the shifted high nibble of
  byte 3. These fields do not identify a product, motor layout or physical
  partner.
- Public discovery tests raw AD Flags bit `01`, independently of manufacturer
  sync/init bits. Werkmeister also admits only customer `ffff`, `0018` or `0012`;
  Caresse has no shipped customer gate.
- Configured discovery targets the exact MAC. The SDK applies the company filter
  to newly created discovered devices, while rediscovery of an already cached SDK
  device bypasses that new-device filter. Do not add an inferred company gate to
  the exact configured-target route.
- Home Assistant diagnostics derive each observed company/payload record without
  choosing an SDK-first record. The host manufacturer map does not preserve raw
  AD ordering, duplicate company records, raw Flags or advertising/scan-response
  grouping. Those limits remain explicit, including when only one record is
  present.
- The pure ordered-record helper preserves the exact source rule when ordered
  input is available; diagnostic verdicts from the map remain conditional.
- Automatic operation of the first broad public candidate is excluded for
  target/product safety. Setup requires an explicit physical target and app
  profile.

##### Home Assistant setup

Select **Vibradorm: VMAT, Caresse Diamant, Werkmeister, V-MAT Basic** in the
bed-type picker, then choose Caresse Diamant or Werkmeister. Existing generic
entries keep their legacy setup until explicitly reconfigured. Bluetooth identifiers do not select an app
or remote layout. Werkmeister offers its two proven remote
layouts. Fresh Caresse uses its basic two-axis layout; enable retained settings
only when you know the app's saved remote type and independent floor-light,
mood-light, massage and light-extension settings. The `other` retained type has
memory controls but no motor axes. No profile reports positions.

Retained Caresse settings also accept a remembered floor brightness from 1 to 8.
The light-extension slider stops at 6, but a previously remembered 7 or 8 remains
valid. Floor brightness and pending timer choices are local command intent,
not measured bed state. Reconnecting or reloading preserves that intent during
the same Home Assistant process; restarting clears current brightness and the
pending timer while retaining the remembered brightness.

Setup hides generic motor-count and pulse settings. Controls use the selected
profile's fixed refresh and release behavior. First onboarding shares one
10-second connection, information and native pairing deadline. Local stored
bonds require exact-adapter BlueZ evidence; a successful proxy pairing request
remains unverified. App metadata is diagnostic information, not bond proof.

##### Information, notification and bonding lifecycle

Reachable onboarding order is in scope, not excluded merely because Android
initiated it. For a new explicit-profile bond:

1. Issue ordinary unbonded connect/service discovery and start one source
   10,000 ms whole onboarding deadline, including connection/discovery; no
   per-field reset.
2. For nonbasic enable the exact response subscription; for basic do not
   subscribe. Nonbasic source queues subscription before initialized listener;
   actual acknowledgment failure must be exposed, not silently manufacture a
   different path.
3. Sequentially read DEVICE_NAME (`2a00`), MANUFACTURER (`2a29`), MODEL (`2a24`),
   FW (`2a26`), SW (`2a28`).
4. Only control types 5/6/7 then send exactly three separate `01 A0 C8` article
   requests, each reply-gated. No toggle, automatic STOP or inferred firmware
   transfer.
5. After information completion call native bond using existing typed host/proxy
   pairing, proof, cancellation and cleanup policy. Record a real native bond
   result. DIS/article bytes are metadata and never new bond proof, credentials,
   profile inference or connection-gated-by-bond evidence.
6. Complete/store the selected configuration and disconnect/transition. Later
   configured startup targets exact MAC and checks existing bond/recovery; avoid
   an unnecessary new first-bond transaction.

Reconnects and deadlines:

- An established exact-transport reconnect uses the selected Home Assistant
  connection-profile timeout.
- Readable native inventory proving that the exact host bond is absent
  invalidates the saved pairing context; unavailable or ambiguous inventory does
  not supply that proof.
- If fresh information and pairing are then required, their original onboarding
  deadline still includes time already spent connecting and is never restarted.
  The shared onboarding budget also applies to a new transport without saved
  context.
- A profile-aware pre-pair hook carries the selected client, cancellation state
  and shared deadline. The static pairing policy alone does not establish the
  required information-before-bond order.
- Existing generic Vibradorm route is preserved. The setup lifecycle owns the
  hook/order and host/proxy proof; the app controller owns its exact
  read/parser/transaction helper.
- Android activity dialogs, synchronous callback-before-post race and
  host-specific retry/unbond implementation details are separate
  process/safety/platform exclusions, without waiving this reachable workflow or
  the source deadline.

Native bond evidence and legacy boundary:

- The app checks exact-MAC native bonded inventory and native completion.
  Metadata reads and successful pair RPCs are not cryptographic authentication
  proof. Use typed native OS state evidence distinct from an authenticated
  protocol probe.
- Unsupported proxy confirmation remains unverified with an accurate
  pairing-attempted status.
- Readable host inventory proving no stored bond after pairing is a failed
  pairing outcome, even when the pairing RPC returned normally. The setup result
  names the host adapter with no stored bond; this observation does not measure
  link authentication. Setup cannot record it as established, and runtime
  preserves completed metadata without creating an established attempt marker.
- Unavailable or ambiguous inventory retains the existing inconclusive handling.
- Already-bonding/demo shortcuts and phone-specific destructive automatic unbond
  are explicit safety exclusions, while the information-before-native-bond
  workflow remains in scope.
- These profiles expose no live position, EEPROM or motor-status parser. Their
  orphan helpers are excluded by caller/selector closure. Generic Vibradorm
  position behavior remains available through the existing generic route.
- Historical reports about another app or physical controller do not identify
  either profile or prove that their hardware issues are fixed.

#### Controls

The profile matrix and the complete source-driven discovery dispositions
determine each reachable command and its preconditions. Eight normal
motor-direction opcodes, all-up/all-down, exact six memory opcode choices, fixed
save tails, dedicated light paths, mood group bit, massage group bit and article
literal requests require profile-specific vectors.

##### Packet format

- Use each accepted package's exact source/vector bindings.
- Basic iff control types 2/3.
- Caresse basic motor writes are single-byte commands; nonbasic and Werkmeister
  motor/recall writes are `BE16(opcode | T)` on CBI.
- STOP is literal `FF` on COMMAND for basic, literal `00 FF` on CBI for nonbasic.
  STOP does not advance T.
- The exact packet remains unchanged through the host BLE transport; no app
  checksum, framing, crypto, MTU operation, side byte or fragmentation is added.

##### Toggle bit T

T starts at 0 at MC construction. Logical command construction/enqueue consumes
the current T then advances it before a BLE result. Held repeats reuse the same
constructed header; they do not alternate per repeat. Article literals and STOP
do not advance it. Preserve caller and execution-stage differences:

- floor toggle performs a preadvance before writeFloorLight; CBI construction
  consumes/advances T again;
- CmdLightCBI.execute captures its header then advances global T before the
  write; level consumes 2 advances, toggle 3 in a serialized CBI action;
- direct basic LIGHT construction/execution consumes no T; direct floor-toggle
  only consumes its preadvance;
- Store consumes 5 logical advances (see [Memory store](#memory-store));
- immutable host command snapshots replace unsafe shared static argument
  aliasing; exact source alias counterexamples remain documented/excluded.
  Profile-local intent survives a failed/dropped write where the source
  constructs it first. The execution-only light advance occurs when execution
  begins, not merely when dropped queued work is removed.

##### Motor and memory opcode index

Basic controls 2/3 use the low command byte. Nonbasic controls use big-endian
words with the captured toggle bit, except literal release/save-tail frames. The
same table serves the [VMAT](#vmat) profile.

<!-- generated:vibradorm-app-commands -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| `hold_control` | Basic: motor frame | CBI frame, T = 0 |
|---|---|---|
| `head_up` | `03` | `00 03` |
| `head_down` | `02` | `00 02` |
| `back_up` | `0B` | `00 0B` |
| `back_down` | `0A` | `00 0A` |
| `legs_up` | `09` | `00 09` |
| `legs_down` | `08` | `00 08` |
| `feet_up` | n/a | `00 05` |
| `feet_down` | n/a | `00 04` |
| `all_up` | `10` | `00 10` |
| `all_down` | `00` | `00 00` |
| `memory_1` | `0E` | `00 0E` |
| `memory_2` | `0F` | `00 0F` |
| `memory_3` | `0C` | `00 0C` |
| `memory_4` | n/a | `00 1A` |
| `memory_5` | n/a | `00 1B` |
| `memory_6` | n/a | `00 1C` |
| Release | `FF` | `00 FF` |

A CBI frame ORs the toggle into its first byte (`80`); the release frame never
carries it.
<!-- /generated -->

- An opcode's existence does not expose its action in every profile. The selected
  app movement groups and exact memory gates above determine which actions are
  available.
- All-down is held movement toward flat, not a measured or self-completing flat
  preset.
- Basic seat recalls only 1–3; no basic programming or memory 6 inheritance.

##### Memory store

| Step | Characteristic | Frame |
|------|----------------|-------|
| 1–4 | CBI | Store headers `BE16(000d \| T)`: `T / T^8000 / T / T^8000` |
| 5 | CBI | Selected-slot literal `00<slot>` |
| 6–9 | CBI | Four literal `00 FF` STOP frames |

- Store consumes 5 logical advances. The source wrong receiver assignment
  preserves these bytes and a total of 5 advances.
- No invented long-press threshold or storage ACK.

##### Floor light frames

| Profile | Characteristic | Frame |
|---------|----------------|-------|
| Basic without extension | LIGHT | `[raw, 00, timer]` |
| Basic with extension, or nonbasic without extension | CBI | `BE16(0011 \| T)` + `raw timer` |
| Nonbasic with extension | CBI | `BE16(1011 \| T)` + `raw timer` |

- CBI opcode `0011` for basic or nonextended; `1011` only nonbasic+extension.
- `raw` is the logical level with extension, otherwise logical × 32; values > 255
  return 200.
- `timer` is the pending minute value when the timer is enabled, otherwise 0.

##### Mood light frames

Group header `BE16(0077 | T)` for basic, `BE16(1077 | T)` for nonbasic; mood
toggle is always `BE16(1077 | T)` with no parameters.

| Command | Parameters after the header |
|---------|-----------------------------|
| Palette color | `01 00 R G B` (see [Fixed mood palette](#fixed-mood-palette)) |
| Effect sunrise / rainbow / disco | `08`, then `01` / `02` / `03` |
| Speed 0–8 | `09` + `20 - 2 × (speed + 1)` |
| Toggle | none |

##### Massage frames

Group `0000` for basic, `1000` for nonbasic.

| Command | Frame |
|---------|-------|
| Massage update | `BE16(group \| 0030 \| T)` + `effect speed zone1 zone2 00 00 00 00` |
| Massage off | `BE16(group \| 0034 \| T)` + `00` |

##### Sync (Werkmeister type 7)

| Command | Frame |
|---------|-------|
| Sync query | `BE16(003d \| T)` + `3f` |
| Held sync, active | `BE16(0019 \| T)` |
| Held sync, inactive | `BE16(0018 \| T)` |
| Release | `00 FF` |

##### Information

| Command | Characteristic | Frame |
|---------|----------------|-------|
| Article request (types 5/6/7) | CBI | `01 A0 C8`, three separate reply-gated requests |
| Device name, manufacturer, model, firmware, software | `2a00`, `2a29`, `2a24`, `2a26`, `2a28` | GATT reads |

#### Timing

- Source DeviceComm is a FIFO with nominal 100 ms pump, 30 ms pending polling and
  SDK 100 ms task delay. It has no fixed repeat count, hold duration or on-air
  100 ms guarantee.
- Refresh only a successful prior held write; serialize commands through the
  coordinator. HA re-sends the held packet every 100 ms.
- Ordinary Home Assistant actions use a bounded one-second hold as host policy.
  That duration is not an APK interval, hardware travel time or automatic
  flat-position acknowledgment.
- The `adjustable_bed.hold_control` action exposes the exact profile control
  catalog and an explicit bounded duration (100 ms to 60 s), with paired side
  routing. Its catalog is validated for every selected physical target before
  writes, and release uses the controller STOP cleanup path.
- All-down means movement toward flat while held, not a proven self-completing
  preset.
- Release always ends refresh and attempts the exact profile STOP with a fresh
  cancellation signal, including cancellation/error/side-routed service cleanup.
- Do not copy source stranded-STOP, unhandled ACTION_CANCEL, queue
  clear/disconnect without STOP or indefinitely blocked write behavior. These are
  explicit safety exclusions with source evidence.
- Do not append STOP after a one-shot feature or information packet unless it is
  a separate requested navigation/motor release.
- Host serialization can safely replace shared unsent-command races, without
  changing normal ordered vectors.

#### Notifications

##### Information strings and articles

- Successful standard MODEL/FW/SW reads decode UTF-8 with Java edge trim of code
  units ≤ U+0020 (empty/null -> empty, embedded NUL/NBSP preserved).
- Each successful MODEL/FW/SW result and matching article reply is retained
  before the next read or request.
- Runtime refresh persists completed diagnostic deltas in one guarded terminal
  batch, including failure or cancellation, so reconstruction preserves
  successful fields while unread fields remain unknown or retain their prior
  value.
- A later read, article or bond failure must not discard earlier diagnostic
  strings; partial diagnostics do not make the transaction or bond successful.
- Information strings do not select capabilities.
- Article recognition requires length > 4 and prefix `21a0c8`; decode the
  remaining bytes as UTF-8 without trimming/NUL termination.
- Source advances the transaction on every successful notification, including
  unrelated data, and can leave `readingDeviceInfo` stale after fail; explicitly
  exclude these unsafe diversions. The host correlates relevant replies and
  clears transaction state on every exit.
- Preserve three requests and parser results, and test unrelated/late/malformed
  callbacks, missing notify, failed read/write, cancellation, bounded deadline and
  no writes after completion.
- No parser-reachable measured angle/motor position exists in row031.

##### Sync replies

- Only Werkmeister type 7 has live sync: query `003d | T` plus `3f`; recognize
  length ≥ 3 with `20`/`3f` flags at byte 2, or `3f` flags at byte 1; bit `40`
  indicates sync active. This is the [motor status reply](#responses) the generic
  controller also parses.
- Pending held intent chooses `0019` when active else `0018`, via the repeating
  motor builder. Release clears pending intent and sends `00 FF`; late reply after
  release must not restart a hold.
- Type 5 sync is inert; Caresse fixed-flavor sync/calibrate routes are dead even
  for restored type 7.
- Expose a user sync action and the `vibradorm_app_sync_observed` diagnostic
  sensor, without asserting a second BLE connection or a physical partner state.
- Raw other callbacks are diagnostic only.

#### Lighting and massage state

##### Floor light

- Exact helper logical level 0–8; shipped slider 1–6 with extension or 1–8
  without extension (off 0 is separate).
- Missing remembered-preference fallback 6 with extension, otherwise 8 (normal
  first-onboarding/reset remembers 6).
- Raw conversion extension=logical, nonextension=logical*32, values > 255 return
  200 (including the missing-preference getter boundary).
- Toggle remembers a nonzero default, zero default is normalized to 1.
- Timer enable/value is local pending state applied to the next floor write;
  provide the exact NumberPickerDialog domain 1–60 minutes, with enable/value
  changes pending until the next floor command.
- No automatic light/sensitivity/zone/RGB inference.
- Floor control remains separate from mood lighting.

##### Floor intent and host lifecycle

- Current floor level and remembered turn-on level are distinct local intent.
  Both APK Application initializers write current level 0.
- First unconfigured onboarding then calls `unconfigure()`, which writes current
  and remembered level 6 before remote selection; newly selected Werkmeister
  controls therefore begin from 6 in that same app process. A later configured
  process begins from current level 0 while preserving remembered level 6.
- Missing remembered preferences have a separate fallback: 6 with extension,
  otherwise 8. A getter fallback does not establish normal first-onboarding
  state.
- The Android reset/preferences screen is excluded as local application UI
  (`R031-0671`). Its downstream floor level/default effects are in scope because
  they change subsequent packets.
- Home Assistant represents this lifecycle with typed local floor and
  pending-timer intent: successful new selection seeds 6/6; a configured cold
  process begins at level 0 and timer off/0, retaining the stored turn-on
  preference.
- Local intent survives connection/controller reconstruction for the exact
  physical address and unchanged app/control selection. Changing that selection
  discards incompatible local intent.
- The source permits toggling the pending timer flag while its minute value is
  still zero. Home Assistant retains that raw pending state in diagnostics and
  sends the unchanged zero timer byte, while the public timer selector shows Off
  until the pending value is positive. Choosing 1–60 minutes then exposes the
  effective pending duration. These fields never prove that the peripheral is on
  or off.
- Home Assistant exposes floor lighting through the under-bed switch and a
  positive brightness number, separate from the bounded mood controls. The switch
  starts unknown with assumed state.
- OFF remembers a positive level before sending zero; ON restores the current
  positive or remembered level. Repeating an explicit ON/OFF action resends that
  requested branch while preserving source caller toggle consumption.
- Successful published level intent updates both controls. Failed delivery
  preserves their last publication while internal constructed intent advances;
  neither path is hardware readback.
- Controller recreation is a fresh MC/control-screen boundary: logical header
  toggle and screen-owned massage/mood state start from their source constructor
  state. Process-wide floor preference and pending timer use the separate shared
  holder. This host boundary does not claim to reproduce the SDK's reconnect
  while the original Android screen object survives.

##### Mood light

- Only Caresse restored RGB: all 18 shipped palette choices, fixed 100 brightness
  HSV transformation and retained toggle, effects sunrise/rainbow/disco 1–3,
  exact speed progress 0–8 conversion.
- `MoodLightFragment.java` lines 35–36 initializes `mCurrentBrightness = 100`;
  its constructor is the sole assignment and `setNewColor` lines 153–155 uses
  that fixed value. The shipped callbacks expose no adjustable mood brightness.
- Separate typed select/number specs expose palette/effects/speed.
- Do not advertise unrestricted arbitrary HA RGB, adjustable mood brightness,
  inferred color temperature, hardware state or unsupported effect names.
- Packet group `0077` basic / `1077` nonbasic except mood toggle is always `1077`.
- State is local intent/assumed; no live device status reconstructs it.

##### Fixed mood palette

The shipped order and fixed 100 HSV roundtrip produce the following packet RGB
values. Rounding can differ from the resource ARGB color by one unit. The palette
is discrete; it does not authorize arbitrary RGB or adjustable mood brightness.
VMAT's own floating-point conversion has its own truncation results, shown in
the last column.

<!-- generated:vibradorm-mood-palettes -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Palette index | HA option | Caresse packet RGB | VMAT packet RGB |
|---|---|---|---|
| 0 | `#008a00` | 0, 138, 0 | 0, 138, 0 |
| 1 | `#00aba9` | 0, 171, 169 | 0, 170, 168 |
| 2 | `#1ba1e2` | 26, 161, 226 | 26, 161, 226 |
| 3 | `#0050ef` | 0, 80, 239 | 0, 80, 238 |
| 4 | `#6a00ff` | 106, 0, 255 | 106, 0, 255 |
| 5 | `#aa00ff` | 170, 0, 255 | 170, 0, 255 |
| 6 | `#f472d0` | 244, 114, 208 | 244, 114, 208 |
| 7 | `#d80073` | 216, 0, 115 | 216, 0, 115 |
| 8 | `#a20025` | 162, 0, 36 | 162, 0, 36 |
| 9 | `#e51400` | 229, 19, 0 | 229, 19, 0 |
| 10 | `#fa6800` | 250, 104, 0 | 250, 104, 0 |
| 11 | `#f0a30a` | 240, 163, 9 | 239, 162, 9 |
| 12 | `#e3c800` | 227, 200, 0 | 227, 200, 0 |
| 13 | `#825a2c` | 130, 90, 44 | 130, 90, 44 |
| 14 | `#6d8764` | 109, 135, 100 | 109, 135, 100 |
| 15 | `#647687` | 100, 118, 135 | 100, 118, 135 |
| 16 | `#76708a` | 118, 112, 138 | 118, 112, 138 |
| 17 | `#ffffff` | 255, 255, 255 | 255, 255, 255 |
<!-- /generated -->

##### Massage

- Only Caresse restored massage: defaults effect 0, speed 1, zones 0/0 and timer
  0, saved intensity 3/3, effect 1 and speed 1, flags false.
- Auto and Individual on/off have different saved state and nested mode-switch
  off frames.
- Expose both modes, torso/leg toggles and guarded increase/decrease, waves 1–4
  and speed 1–5 with the exact listener/updateIndicators predicates.
- Do not collapse saved flags and saved intensities or automatically invent a
  fresh individual 3/3 fallback.
- Zone controls use the proven toggle/increment/decrement callbacks; no arbitrary
  direct intensity setter is implied.
- Preserve 72 accepted state vectors, complete Cartesian guard proof and exact
  nested off-then-restore sequences.
- Timer has no shipped setter; no new timer UI.
- Sensor/select state must distinguish intended/assumed state from a hardware
  acknowledgment.

##### Entities and paired beds

- Controller select/number descriptions are immutable for the chosen
  profile/flags; massage mode guards run in setters, not by changing loaded
  entity descriptions.
- Shared typed select/number descriptions provide the user interface while the
  app controller supplies exact options and guarded callbacks.
- Controller-held options, motor specs, ControllerButtonSpec and controller
  diagnostic sensor specs supply exact route/capability gates.
- Expose every in-scope action without requiring raw packet entry; paired child
  targeting must route to the same logical profile/controller.
- Separate-address pairs retain side-specific app/profile/retained-feature
  fields; differing sides prohibit global option propagation.
- Single-address pairing/addressing is not supported by these app profiles. This
  is a HA integration boundary, not an app-proven partner feature.

#### Evidence

- Accepted row031 audit: the static protocol/profile behavior is implemented with
  concrete code and executed-test bindings. The complete artifact sets,
  independent package audits and whole-cluster reconciliation are accepted static
  evidence; the row031 audit lists all 356 exact exclusions.
- Caresse and Werkmeister send only their frozen frames
  (`caresse` and `werkmeister` in `tests/vibradorm_vectors.py`).
- Hardware operation, on-air packet delivery, peripheral security and physical
  effects remain unverified. Real-user checks after beta/release are deferred
  external validation, not missing static implementation evidence.

### VMAT

**App:** [VIBRADORM Remote](https://play.google.com/store/apps/details?id=de.vibradorm.vmat) (VMAT) 1.11 (49), `de.vibradorm.vmat`

**Status:** ❓ Needs testing (app behavior artifact verified, physical operation unverified)

The bed type is `vibradorm_app` with app profile `vmat`. Generic entries keep
their existing controller. [Caresse / Werkmeister](#caresse-and-werkmeister) and
[V-MAT Basic](#v-mat-basic) have their own independent feature gates, vectors and
dispositions.

#### Setup

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
move through CBI. Detection: none; the profile is an explicit choice.

##### VMAT remote selection

- Choose **Vibradorm: VMAT, Caresse Diamant, Werkmeister, V-MAT Basic** in the
  bed-type picker, then **VMAT** and the same zero-based remote ordinal used by
  the app.
- **Legacy setup** inside the family chooser retains the older generic
  controller for fresh setup. Existing entries change through the
  [guided migration](#guided-setup-and-migration).
- The choices distinguish setup contracts; some command paths overlap. Controls
  and features follow this exact selection.
- Shared Bluetooth identifiers and device-information strings cannot select this
  app or its remote layout.
- Successfully reconfiguring to Caresse or Werkmeister removes the VMAT remote
  from the saved profile. Separate-address sides keep their own remote
  selections.

<!-- generated:vibradorm-vmat-remotes -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Remote | Image | Control | Logical groups | Memory | Sync | Floor | Mood / massage | Movement route |
|---|---|---|---|---|---|---|---|---|
| 00 | sender_010 | 2 | Back, legs | No | No | No | No | Basic |
| 01 | sender_020 | 2 | Back, legs | No | No | Yes | No | Basic |
| 02 | sender_180 | 2 | Back, legs | No | No | No | No | Basic |
| 03 | sender_190 | 2 | Back, legs | No | No | No | No | Basic |
| 04 | sender_200 | 2 | Back, legs | No | No | Yes | No | Basic |
| 05 | sender_210 | 2 | Back, legs | No | No | Yes | No | Basic |
| 06 | sender_220 | 2 | Back, legs | No | No | Yes | No | Basic |
| 07 | sender_230 | 8 | Back, legs | 6 | Yes | Yes | No | CBI |
| 08 | sender_240 | 8 | Back, legs | 6 | Yes | Yes | No | CBI |
| 09 | sender_250 | 8 | Back, legs | 6 | Yes | Yes | No | CBI |
| 10 | sender_260 | 8 | Back, legs | 6 | Yes | Yes | No | CBI |
| 11 | sender_270 | 9 | Head, back, legs | 6 | Yes | No | No | CBI |
| 12 | sender_090 | 2 | Back, legs | No | No | No | Yes | Basic |
| 13 | sender_100 | 1 | Head, back, legs, feet | 6 | No | No | Yes | CBI |
<!-- /generated -->

- The app's neck/calf groups use HA's head/feet controls; physical actuator
  identity remains unverified.
- Remotes 12/13 set the extension flag but expose no floor route.
- Quick memory buttons are subsets of the six-slot contract.

##### Bonding

- Setup requires positive native bond evidence for the exact address and actual
  host route. An unverified pairing RPC cannot finish setup or authorize control.
- Metadata does not identify a wire layout or prove a bond. No app PIN/key
  exchange is proven.
- Unsupported proxy pairing should use a supported host adapter; existing bonds
  are never silently removed.

##### VMAT onboarding

Initialization settles for 500 ms and subscribes for every remote. Setup reads
the three DIS fields, then serially issues seven CBI stages:

<!-- generated:vibradorm-vmat-stages -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Stage | CBI request | Reply prefix | Reply timeout |
|---|---|---|---|
| Status | `01 B3 4C 01` | `21b3` | 2 s |
| Operating mode | `01 B3 F4 01` | `21b3` | 1 s |
| Article | `01 A0 C8` | `21a0c8` | 1 s |
| Name | `01 A0 C9` | `21a0c9` | 1 s |
| Revision ID | `01 A0 CA 00` | `21a0ca` | 1 s |
| Revision string | `01 A0 CA` | `21a0ca` | 1 s |
| Variant | `01 A0 CC` | `21a0cc` | 1 s |

After native pairing, setup closes with `01 A7`.
<!-- /generated -->

- Status replies carry an unsigned byte and operating-mode replies a signed byte;
  the other stages reply with UTF-8 after their prefix.
- The first response timeout is 2 seconds and the others 1 second.
- Each notification can complete one current stage; the two CA stages stay
  separate. Missing replies advance after timeout without a fabricated
  acknowledgment.
- Transport write timeouts abort onboarding before native pairing.
- Short/mismatched replies are guarded. UTF-8 retains whitespace and NULs.
- After native pairing/proof, setup sends the close frame and disconnects.
  Runtime onboarding also closes its link before a separate control connection,
  whose actual route must prove the bond.
- Normal sessions issue no onboarding queries or position polls. Explicit
  information refresh reads only three DIS fields.
- An existing native bond skips onboarding and pairing, while setup still
  validates the selected remote's ordinary GATT roles before accepting the
  address.
- Onboarding connection timeout is 5 seconds. HA bounds the complete operation
  with a separate 45-second resource budget, not a device pairing timing claim.

##### Setup link cleanup

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

##### Discovery

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

##### Home Assistant setup

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

#### Controls

Basic packets are written to COMMAND `1526`; CBI packets to `1550`. `T` is the
construction toggle (0 or `8000`) ORed into the 16-bit CBI header.

- P1 uses big-endian 16-bit CBI opcodes without response. Basic movement uses
  one-byte COMMAND; basic floor uses three-byte LIGHT with response. Basic
  accessories still use CBI.
- A CBI header is the opcode OR the construction toggle, which alternates
  0/`8000`, including invisible basic motor flips. Held packets repeat unchanged.
  Floor actions retain their extra action/execution flips.
- Payloads are immutable snapshots, without guessed checksums, encryption or
  fragmentation. Unsafe Android shared static payload overwrites are excluded.
- The supported stack owns MTU negotiation and CCCD operations. Frames fit MTU 23.

##### Motor control

VMAT sends the opcodes of the
[motor and memory opcode index](#motor-and-memory-opcode-index), verified
independently from its own artifact: the basic motor frame on basic remotes, the
CBI frame on the others, and STOP (release) `FF` basic or `00 FF` CBI.

- Enabled motor directions, All Up/All Down and recall are held actions. All Down
  is movement, not a timed flat preset.
- Only directions in the selected remote's logical groups are offered: head on
  remotes 11 and 13, feet on remote 13.

##### Memory

| Command | `hold_control` | CBI packets |
|---------|----------------|-------------|
| Recall slots 1–6 | `memory_1` … `memory_6` | Held opcode `0e,0f,0c,1a,1b,1c` |
| Program a slot | | Four alternating STORE `000d/800d` frames, an untoggled slot frame (`00` + slot opcode), then four `00ff` frames |

The program sequence is the nine-frame save handshake referenced in the
[issue #403 reconciliation](#issue-403-reconciliation).

##### Sync

Sync on control 8/9 (remotes 07–11) queries `3d|T,3f` and is a reply-gated
held action:

| Step | Packet |
|------|--------|
| Query (CBI) | Header `003d`\|T followed by `3f` |
| Reply | `20 3f flags` or `3f flags extra` (minimum length 3) |
| Held action | Opcode 25 when reply bit `40` is set, otherwise 24 |

Late replies cannot restart released movement. No partner selector is proven.

##### Floor light

| Route | Packet |
|-------|--------|
| Basic floor remotes (01, 04–06) | LIGHT `1529`: `level 00 timer` (three bytes, with response) |
| CBI floor remotes (07–10) | CBI: `0011`\|T + `level timer` |

- Floor levels 0–8 map to `0,32,64,96,128,160,192,224,250`. Off is 0;
  remembered default is 8 for selectable floor remotes.
- Timer minutes 1–60 and enabled state apply to the next floor packet;
  timer-only changes send nothing.
- Cold current level 0 is assumed local state, not measured physical off state.

##### Mood light

| Command | Packet |
|---------|--------|
| Palette color | `0077` (basic) or `1077` (nonbasic)\|T + `01 00 R G B` |
| Effect 1–3 (sunrise, rainbow, disco) | `0077`/`1077`\|T + `08` + effect number |
| Speed 0–8 | `0077`/`1077`\|T + `09` + `18,16,…,2` |
| Toggle | `1077`\|T for both |

- Mood exposes 18 shipped palette choices with VMAT-specific conversion
  rounding (see the [fixed mood palette](#fixed-mood-palette)), three effects,
  and speed 0–8 mapping `18,16,…,2`.
- Color/effects use `0077` basic or `1077` nonbasic; toggle uses `1077` for
  both. Arbitrary RGB and discrete physical on/off guarantees are absent.

##### Massage

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

#### Timing

- First delivery is immediate on an idle lane; repeats/queued writes wait 100 ms
  after successful completion.
- Release, cancellation and failure use fresh STOP (`FF` basic, `00 FF` CBI),
  prioritizing cleanup over pending ordinary traffic. No hardware watchdog is
  claimed.

#### State

- Floor/timer/mood/massage state is process-local intent. Reconnect and reload
  retain it for the exact address/app/remote; profile changes clear the holder.
- Failed/cancelled VMAT accessory writes roll back the requested state.
  Successful delivery remains assumed intent, not readback.
- Restart clears current intent while retaining the configured floor default.
- No live position parser, angle target, battery query, firmware update,
  calibration or named presets are proven.
- Diagnostics retain raw notifications; unsolicited EEPROM/log recognition does
  not enable dead collectors or queries.

#### Evidence

This explicit profile implements the accepted `de.vibradorm.vmat` 1.11 (49)
application contract and sends only its frozen frames (`vmat` in
`tests/vibradorm_vectors.py`, with the artifact vectors in
`tests/fixtures/vibradorm_vmat_vectors.json`). App behavior is artifact verified;
physical operation remains unverified.

#### Issue #403 reconciliation

The original [parity request](https://github.com/kristofferR/ha-adjustable-bed/issues/403)
predates the accepted independent app audits. Its assumption that Caresse,
Werkmeister, VMAT and V-MAT Basic expose one interchangeable contract is
superseded by their explicit profiles. The VMAT profile shipped in
[v4.1.0](https://github.com/kristofferR/ha-adjustable-bed/releases/tag/v4.1.0).
The outcomes below describe existing implementation and accepted exclusions;
they do not change the frozen audit ledger.

| Original request | Current outcome | Existing evidence |
| --- | --- | --- |
| Live positions, initialization flags and raw motor counts | EXCLUDED as a VMAT app feature: no reachable live position parser is proven. The generic controller retains its separate historical parser and angle estimates. | `VibradormAppController.supports_position_feedback`; `test_remote_contract_and_no_guessed_capabilities`; [generic controller](#position-feedback) |
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
and [`profiles/vibradorm.py`](../../custom_components/adjustable_bed/profiles/vibradorm.py).
Test references are in
[`test_vibradorm_vmat.py`](../../tests/test_vibradorm_vmat.py); the
machine-local VMAT audit ledger retains the exact accepted source bindings.
[Caresse / Werkmeister](#caresse-and-werkmeister) and [V-MAT Basic](#v-mat-basic)
have their own independent feature gates, vectors and dispositions.

The requested MC4-MD08 retest remains deferred physical validation for its
owner after release. The accepted app implementation does not prove that
[issue #162](https://github.com/kristofferR/ha-adjustable-bed/issues/162) is fixed
or that a particular controller reports positions. No in-scope implementation
item is deferred for lack of maintainer hardware.

### V-MAT Basic

**App:** [VIBRADORM Remote for Beds](https://play.google.com/store/apps/details?id=com.vibradorm.vmatbasic) (V-MAT Basic) 2.4.3 (code 14), `com.vibradorm.vmatbasic`

**Status:** ❓ Needs testing (APK-verified, hardware **UNVERIFIED**)

The bed type is `vmatbasic` with profile `basic`, `cbi` or `xtbox` (see the
[product table](#features)). Sibling Vibradorm apps: [VMAT](#vmat) and
[Caresse / Werkmeister](#caresse-and-werkmeister).

#### Setup

- Select **Vibradorm: VMAT, Caresse Diamant, Werkmeister, V-MAT Basic**, then
  **V-MAT Basic** and the product explicitly: V-MAT-BASIC-RF,
  V-MAT-BASIC-RF-CBI, or V-MAT-BASIC-RF-CBI with XT-Box. Detection: none.
- Existing entries keep their controllers until a
  [guided reconfigure](#guided-setup-and-migration)
  succeeds and you confirm it.
- A shared Bluetooth identifier, device name or model string cannot choose one
  of these profiles.
- The dedicated app bed type keeps these accepted profiles separate from the
  existing generic and Caresse/Werkmeister routes; it is a Home Assistant
  configuration boundary, not an inferred protocol identity.

##### GATT roles

| Role | Service | Characteristic |
|---|---|---|
| Movement | `00001525` + vendor suffix | `00001526` + vendor suffix |
| CBI floor read/write | Same control service | `00001529` + vendor suffix |
| XT write | Same control service | `00001550` + vendor suffix |
| ED read | `00001527` + vendor suffix | `00001531` + vendor suffix |
| Controller temperature read | Same status service | `00001532` + vendor suffix |
| Rename | GAP `1800` | Device Name `2a00` |
| Model / firmware read | DIS `180a` | `2a24` / `2a26` |

Vendor UUIDs use suffix `-9f03-0de5-96c5-b8f4f3081186`. One-byte movement;
three-byte CBI floor; `0011` / `0077` prefixed XT frames.

- Every selected receiver must expose the control service, status service and
  GAP before control starts. DIS is optional: missing DIS fails only its
  diagnostic fields.
- The first exact service and then first exact characteristic within it are
  authoritative.
- Writes require the response-capable write property and use `response=True`. No
  arbitrary characteristic fallback, write-without-response downgrade,
  notification subscription, position request, checksum, crypto, fragmentation or
  MTU command is added.

##### Discovery

- The source scan predicate uses the first raw manufacturer AD record, ignores
  its company ID, and checks `babe` followed by low nibbles 1/1. The safe raw
  parser preserves that first-record rule.
- HA's manufacturer map loses AD order, duplicates and declared lengths, even
  with one company: diagnostics report conditional per-record matches and keep
  the exact source scan verdict unknown.
- A conditional candidate hint cannot infer a profile. Existing cached-address
  selection remains explicit; rename and optional model strings are not identity
  proof.

##### Pairing

Bonded status is advisory in this app. The integration does not invent native
bonding, a PIN, authentication exchange or authenticated-GATT proof.

##### Home Assistant setup

Choose **Vibradorm: VMAT, Caresse Diamant, Werkmeister, V-MAT Basic**, then
**V-MAT Basic** and the exact Basic, CBI or CBI with XT-Box product. Bluetooth
identifiers and diagnostic model strings do not choose this profile. CBI exposes
saved floor level 0–255 and timer 0–1439 minutes; XT exposes level 1–6 and timer
0–255 minutes. Leaving the optional level unset preserves the source distinction
between the ON-button default and settings-screen default. Timer defaults to zero.
Product changes use the guided reconfigure flow and discard incompatible floor
values. Ordinary brightness/timer changes remain in Configure. Product profiles
belong to one physical receiver; split a pair before changing them.

#### Controls

##### V-MAT Basic commands

Movement is written to `00001526` (Movement); XT-Box commands to `00001550`.

<!-- generated:vibradorm-vmatbasic-commands -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Command | `hold_control` | Motor frame |
|---|---|---|
| All up | `all_up` | `10` |
| All down | `all_down` | `00` |
| Back up | `back_up` | `0B` |
| Back down | `back_down` | `0A` |
| Legs up | `legs_up` | `09` |
| Legs down | `legs_down` | `08` |
| Release |  | `FF` |

| XT-Box command | CBI frame |
|---|---|
| Floor hold (`floor_hold`) | `00 11` |
| Mood toggle | `00 77` |
| Mood nightlight | `00 77 01 00 00 00 00` |
| Mood effect e1 | `00 77 08 01` |
| Mood effect e2 | `00 77 08 02` |
| Mood effect e3 | `00 77 08 03` |
| Massage back | `00 2C` |
| Massage legs | `00 2D` |
| Massage off | `00 34` |
| Massage program 1 | `00 31` |
| Massage program 2 | `00 28` |
| Massage program 3 | `00 29` |
<!-- /generated -->

##### Floor light

| Command | Characteristic | Bytes |
|---------|----------------|-------|
| CBI floor settings | `00001529` | Level U8 plus timer BE16 |
| CBI toggle OFF | `00001529` | `00 00 00` (all-zero OFF) |
| XT floor settings | `00001550` | `0011` + `level minutes` |
| XT floor hold (`floor_hold`) | `00001550` | `00 11`, repeated; no release frame |

##### Mood light (XT-Box)

XT mood uses group `0077`, written to `00001550`.

| Command | Bytes |
|---------|-------|
| Color | `0077` + `01 00 R G B` |
| Speed | `0077` + `09 ((progress + 1) & ff)` |

Effects 1–3, toggle and nightlight are fixed frames in the
[V-MAT Basic commands](#v-mat-basic-commands) table.

- Progress 255 deliberately encodes zero.
- The palette uses the APK's HSV conversion and truncation; the tests preserve
  all 2,020 palette/brightness outputs.

##### Massage (XT-Box)

The six massage actions (back, legs, off, programs 1–3) are single command words
without parameters, listed in the [V-MAT Basic commands](#v-mat-basic-commands)
table.

Motor STOP does not turn massage off. Power, effect, speed and massage feedback
are unknown; successful writes publish requested intent only.

##### Rename

`rename` writes UTF-8 to GAP Device Name `2a00`; see
[Separate receivers and rename](#separate-receivers-and-rename).

#### Timing

- Ordinary movement buttons hold for one second as a bounded Home Assistant
  policy.
- `hold_control` accepts `all_up`, `all_down`, `back_up`, `back_down`,
  `legs_up`, `legs_down`, and XT-only `floor_hold`, with 0.1–60 seconds in whole
  milliseconds.
- The source refreshes held movement at 30 ms scheduling attempts; this is not a
  guaranteed on-air cadence.
- A fresh `FF` release follows admitted movement on completion, cancellation or
  failure, with bounded cleanup. All-down is a direction, not a measured flat
  position.
- XT floor hold repeats `00 11` and stops by ending the stream; no separate
  release frame is proven.

#### Notifications

V-MAT Basic subscribes to no notifications; it reads its diagnostics.

##### Diagnostics

- Initial diagnostics and three-second refresh attempts read model, controller
  temperature, floor status, firmware, then ED.
- Each operation has an 800 ms host deadline; a failed field becomes unknown and
  later fields can still refresh.

| Field | Decoding |
|-------|----------|
| Temperature | Signed LE32 divided by four minus seven degrees Celsius |
| Floor | Level U8 and timer BE16 (the [light frame](#framing-and-checksum)); percent is level × 100 / 255 |
| ED | Bit zero of the first byte; not a position parser |
| Strings | Java UTF-8 replacement semantics without trimming |

- Background reads use an already live connection, yield to commands, preserve
  the existing idle disconnect deadline, and stop/invalidate on disconnect. They
  do not reconnect or keep an idle receiver awake.
- Immediate/two-second signal samples use HA advertisement history, with scanner
  source and observation timestamp attributes. They are not remote GATT RSSI
  reads; unavailable or invalidated signal remains unknown. Signal strength never
  chooses a receiver or adds a connection prerequisite.

#### Floor and mood state

##### Floor

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

##### Mood

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

#### Services

##### Separate receivers and rename

Linked pair:

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

Rename:

- `rename` trims code points up to U+0020, allows an empty name, and limits the
  result to ten UTF-16 units.
- UTF-8 is written without a terminator. A further host safety limit of 20
  encoded bytes avoids inventing fragmentation.
- Save the confirmed name only after the write succeeds; failed delivery leaves
  the stored name unchanged.

#### Evidence

The protocol comes from the accepted `com.vibradorm.vmatbasic` 2.4.3 APK,
version code 14. Each product sends only its frozen frames (`basic`, `cbi` and
`xtbox` in `tests/vibradorm_vectors.py`, which are its artifact vectors in
`tests/fixtures/vmatbasic-vectors.json`). Current code and focused executed tests
cover the accepted behavior. Hardware status: **UNVERIFIED**.

## Notes

### Troubleshooting

**Commands not working:**
- Ensure no other device (app, remote) is connected to the bed
- BLE beds only allow one connection at a time

**Position values seem incorrect (generic controller):**
- Position calibration may vary by bed model
- Open an issue with your bed's position values for calibration assistance

### Deferred validation

- Caresse and Werkmeister: hardware operation, on-air packet delivery, peripheral
  security and physical effects remain unverified.
- VMAT: hardware absence does not defer implementation. Focused tests exercise
  real controller/setup delivery, frozen vectors, native-proof gates, timing and
  failure cleanup. Physical validation remains for users after beta/release.
- V-MAT Basic: physical packet delivery, movement effects, floor timing/scales,
  mood and massage effects, rename persistence, temperature interpretation,
  optional read support, dual connection behavior and security remain deferred
  user validation after beta/release. Static acceptance does not claim those
  hardware outcomes.

### References

- [GitHub Issue #162](https://github.com/kristofferR/ha-adjustable-bed/issues/162)
- [GitHub Issue #403](https://github.com/kristofferR/ha-adjustable-bed/issues/403)
- Accepted Caresse / Werkmeister audit (row031), VMAT audit and V-MAT Basic audit
  (row037)

### Analysis provenance

Caresse and Werkmeister (row031):

| Accepted artifact | Version | APK SHA-256 |
|---|---|---|
| `de.vibradorm.diamant` (Caresse Remote) | 0.3, code 3 | `61073fa141df96bc40cbdd5820e64e2fb19c53cb88334baeaf6772493cfd97c2` |
| `de.vibradorm.werkmeister` (Werkmeister Unterfederung) | 0.2, code 2 | `36306b6ac6ee3fd66bef5a71e3626c44e2befccb3d2e135031747bcd5c7f9635` |

| Seal | SHA-256 |
|------|---------|
| Accepted representative report seal | `3a57621a4a4e689b06ec9bd6d471807d3b184c10520f129f342eebb442deae2c` |
| Accepted sibling report seal | `2c8b210bf8942c689bd62ae555557283298f895c75c246c5f00e57b755e97c9a` |
| Whole-cluster reconciliation seal | `fcdaaf8728e27bbd04b47849201ea46dea1cf790f93ac5ce01c2968c325bfffc` |
| Independent reconciliation audit seal (ACCEPT, zero material findings) | `f91c5b9efcf2eb85bdf0e80f81717ecd0b92d6059463b4a90ea4b807a3f5224d` |
| Post-freeze comparison seal | `a59b50bb11a14660b737482066f4b6609f9e775e0170e97248a394c821ca7fc2` |

The row031 audit lists all 356 exact exclusions. Raw artifacts, decompilation,
packet reproducers and independent audit reports remain machine-local.

VMAT (`de.vibradorm.vmat` 1.11 (49)):

- The machine-local VMAT audit ledger binds all 282 comparison items: 240
  IMPLEMENTED, 0 ALREADY_IMPLEMENTED and 42 EXCLUDED.
- Its exact exclusions cover 26 unreachable selectors, Android
  scanner/permission/bond APIs, phone presentation and unsafe
  queue/parser/cancellation behavior.

V-MAT Basic (`com.vibradorm.vmatbasic` 2.4.3, version code 14):

- Artifact-set SHA-256: `5d266015494edf9ad595c5b4c6d11fcde3ea53fc78e008b4990e4ce834a31980`
- Accepted repair report manifest: `5d73627f5b010b372b3cdec39091faa817a4a596ead49db9ec507ee6025a5d0d`
- Independent audit manifest: `7892663c50ea99a3174bfa1fd86cd27ed276ef4be1270bf256ac13133a0c155b`
- All package evidence stays machine-local, including the row037 disposition
  ledger that records the separate implementation comparison.
- Workflow progress is recorded in the canonical APK audit trackers and published
  queue plan.
