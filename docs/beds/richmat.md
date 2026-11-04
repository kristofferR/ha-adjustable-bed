# Richmat

**Status:** ✅ Tested (Richmat and BedTech routes); ❓ the RMControl, Richmat MH and HJBed app profiles are APK-verified with hardware unverified

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), getrav, [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt) and [Josh Pearce](https://github.com/joshpearce) (L&P MlRM)

One wire codec (`6E` frames ending in an additive `sum8`, over seven GATT
transports) serves the Richmat remote routes, BedTech, Leggett & Platt MlRM
beds and three families of catalog apps. This guide covers the codec first, then
one section per profile. See [Protocol codecs and app profiles](../design/protocol-codecs.md)
for the architecture.

## Known Models

Brands using Richmat actuators:

- L&P Adjustable Base (Leggett & Platt), including MlRM bases
- SVEN & SON
- Casper Base
- Galaxy (e.g., Galaxy 26W-N)
- MLILY
- Luuna / Luuna Rise
- BedTech adjustable bases, Dreams Sleepmotion 200i
- Jerome's
- Revive
- Idealbed
- Maxprime
- Milemont
- Hush Base
- FLEXX MOTION
- Likimio
- Lunio Smart+
- Good Vibe Sleep
- Best Mattress Power Base
- Easy Rest
- Coaster Sleep
- Avocado Eco Base
- ENSO Sleep
- Dynasty DM9000
- Thomas Cole Sleep
- Forty Winks ActivFlex
- Richmat HJA5 series
- Saatva
- Lucid L300
- Classic Brands

The catalog apps name their layouts themselves: an RMControl product code, a
Richmat MH model (the first four characters of the Bluetooth name) or an HJBed
product. Shared services and Bluetooth names do not identify a layout, so each
is an explicit choice (see [Choosing a profile](#choosing-a-profile)).

## Apps

| Analyzed | App | Package ID | Profile |
|----------|-----|------------|---------|
| ✅ | [RMControl](https://play.google.com/store/apps/details?id=com.richmat.rmcontrol2) 21.3.7 | `com.richmat.rmcontrol2` | [RMControl](#rmcontrol); the [Richmat remotes](#richmat-remotes) cover the same beds |
| ✅ | [BedTech](https://play.google.com/store/apps/details?id=com.bedtech) | `com.bedtech` | [BedTech](#bedtech) |
| ✅ | [SleepFunction Bed Control](https://play.google.com/store/apps/details?id=com.richmat.sleepfunction) | `com.richmat.sleepfunction` | [Richmat remotes](#richmat-remotes) |
| ✅ | [L&P Adjustable Base](https://play.google.com/store/apps/details?id=com.richmat.lp2) 2.3.25 | `com.richmat.lp2` | [L&P MlRM](#lp-mlrm), [Richmat remotes](#richmat-remotes) (QRRM) |
| ✅ | L&P Adjustable Base 2.2.1 (legacy) | `com.richmat.lp` | [Leggett & Platt](leggett-platt.md) |
| ✅ | [LP Control](https://play.google.com/store/apps/details?id=com.leggett.android.universal) 2.9.0 | `com.leggett.android.universal` | [Leggett & Platt](leggett-platt.md) |
| ✅ | [SVEN & SON](https://play.google.com/store/apps/details?id=com.richmat.svenson) | `com.richmat.svenson` | [Richmat remotes](#richmat-remotes) |
| ✅ | [Revive Control](https://play.google.com/store/apps/details?id=com.richmat.revive3) 1.0.26 | `com.richmat.revive3` | [Richmat MH](#richmat-mh-apps), bed type `richmat_revive` |
| ✅ | [Best Mattress](https://play.google.com/store/apps/details?id=com.richmat.best_mattress) 1.1.1 | `com.richmat.best_mattress` | [Richmat MH](#richmat-mh-apps), bed type `richmat_best_mattress` |
| ✅ | [Blvd Home](https://play.google.com/store/apps/details?id=com.richmat.blvd_home) 1.0.1 | `com.richmat.blvd_home` | [Richmat MH](#richmat-mh-apps), bed type `richmat_blvd_home` |
| ✅ | [HARMONY](https://play.google.com/store/apps/details?id=com.richmat.harmony) 1.0.0 | `com.richmat.harmony` | [Richmat MH](#richmat-mh-apps), bed type `richmat_harmony` |
| ✅ | [Idealbed](https://play.google.com/store/apps/details?id=com.richmat.idealbed) 2.4.2 | `com.richmat.idealbed` | [Richmat MH](#richmat-mh-apps), bed type `richmat_idealbed` |
| ✅ | [HJBed](https://play.google.com/store/apps/details?id=com.richmat.hjbed) 2.1.2 (code 21200) | `com.richmat.hjbed` | [HJBed](#hjbed) |

## Features

| Feature | Richmat remotes | BedTech | L&P MlRM | RMControl | Richmat MH | HJBed |
|---------|-----------------|---------|----------|-----------|------------|-------|
| Motor Control | ✅ (up to 7 motors) | ✅ Head, Foot, Leg/Pillow | ✅ Head, Feet | ✅ Catalog movement with cancellable repeats and release cleanup | ✅ Two motors; the model decides which exist (KEEP then STOP) | ✅ Selected head, foot, combined, pillow, lumbar, tilt, foot-box and sofa routes, depending on product |
| Position Feedback | ❌ | ❌ | ❌ | ❌ (numbered motor reports are not relabeled as physical axes) | ⚠️ VER1 angle replies update the angle numbers; **Reached position** reports memory arrival | Raw observed travel, angle and height data; no inferred position seeking or units |
| Memory Presets | ✅ (1-5 slots, varies by model) | ✅ (2 slots) | ✅ (2 slots, held recall) | ✅ Where the selected catalog supports them | ✅ Memory slots from the model's catalog | ✅ Product-specific named recall/save buttons, including memory 1–4 where selected |
| Presets | ✅ Zero-G / Anti-Snore / TV / Lounge; Yoga / Read on some models | ✅ Zero-G / Anti-Snore / TV / Lounge | ✅ Zero-G / Anti-Snore / TV / Lounge | ✅ Where the catalog has them | ✅ Standard presets from the model's catalog | ✅ Product-specific |
| Massage | ✅ | ✅ (5 modes, timer) | ✅ Discrete head/foot up and down, timers | ✅ Including head/foot intensity up/down where both directions exist | ✅ App-labelled buttons; VER1 head/foot intensity numbers | ✅ Product-specific mode, intensity and timer buttons |
| Under-bed Lights | ✅ (toggle; RGB color picker + timer on select models) | ✅ (toggle and off) | ✅ (toggle) | ⚠️ RGB, **Always On** or **1 through 15 minutes** timer; gated on the light acknowledgment and strip flag | ✅ RGB light or colour action, light timeout, button-light page | ✅ Selected lamp buttons; advanced timeout/RGB require product flag and acknowledgement |
| Split-King Sync | ✅ (controller-level on/off; assumed state) | ❌ | ❌ | ✅ Where the catalog has it | ❌ | ✅ Sync buttons where selected |
| Alarms | ❌ | ❌ | ❌ | ⚠️ `adjustable_bed.rmcontrol_alarm`, product-gated | ✅ Actions and entities where the model's pages exist | ✅ Single or repeat alarms where the product flag and clock acknowledgement permit |
| Other | | | | ✅ Disabled-by-default catalog buttons; ⚠️ `adjustable_bed.rmcontrol_anti_snore` on six products | ✅ Smart set lock, snore intervention, detection, aroma, waist mattress | ✅ Music, clock synchronization, local layout, single-address paired sides |

## Choosing a profile

Detection suggests the [Richmat remotes](#richmat-remotes) route for Richmat
services and names, and [BedTech](#bedtech) or [L&P MlRM](#lp-mlrm) where their
signals are present. The catalog apps are opt-in: choose RMControl with its
product code, a Richmat MH app bed type, or HJBed with its product.

<!-- generated:richmat-profiles -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

### Fixed-table routes

Movement repeats the code at the entry's pulse count and delay, whose defaults are
listed, then always sends STOP with a fresh cancel event. Every other button is
one write.

| Profile | Bed type | Framing | STOP | Default pulses | Presets and recall | Memory |
|---|---|---|---|---|---|---|
| Richmat WiLinke | `richmat` | wilinke | `6E 01 00 6E DD` | 7 × 150 ms | once | 5 slots |
| Richmat Nordic | `richmat` | nordic | `6E` | 7 × 150 ms | once | 5 slots |
| Richmat Prefix55 | `richmat` | prefix55 | `55 01 00 6E C4` | 7 × 150 ms | once | 5 slots |
| Richmat PrefixAA | `richmat` | prefixaa | `AA 01 00 6E 19` | 7 × 150 ms | once | 5 slots |
| BedTech | `bedtech` | wilinke | `6E 01 00 5E CD` | 10 × 100 ms | once | 2 slots |
| L&P MlRM | `leggett_wilinke` | wilinke | `6E 01 00 6E DD` | 10 × 110 ms | 100 × 300 ms, then STOP | 2 slots |

### Catalog apps

| Profile | Bed type | Transport order | Commands |
|---|---|---|---|
| HJBed | `hjbed` | W1, N1, W5, W4, W3, W2 | per-product catalog |
| Richmat MH Revive Control | `richmat_revive` | N1, W1, W2, W3, W4 | per-model catalog |
| Richmat MH Best Mattress | `richmat_best_mattress` | N1, W1, W2, W3, W4 | per-model catalog |
| Richmat MH Blvd Home | `richmat_blvd_home` | N1, W1, W2, W3, W4 | per-model catalog |
| Richmat MH HARMONY | `richmat_harmony` | N1, W1, W2, W3, W4 | per-model catalog |
| Richmat MH Idealbed | `richmat_idealbed` | N1, W1, W2, W3, W4 | per-model catalog |
<!-- /generated -->

### Catalog app timing

<!-- generated:richmat-catalog-timing -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Profile | Operation | Timing |
|---|---|---|
| RMControl | Write queue, including release | at least 100 ms apart |
| RMControl | Sustain press | entry pulse count at 100 ms, then STOP |
| RMControl | Short and long press | one write |
| Richmat MH | Version query after subscribing | 300 ms |
| Richmat MH | Initialization tasks | 300 ms apart, the first 300 ms after the version query |
| Richmat MH | STOP after a release or a single tap | 120 ms |
| Richmat MH | VER1 angle target | 100 ms after the slider release |
| Richmat MH | Alarm frames | 300 ms apart (150 ms for three-slot save/delete) |
| Richmat MH | Aroma frames | 150 ms apart |
| HJBed | Sustained refresh | every 100 ms from the first tick |
| HJBed | Write spacing | at least 100 ms between attempts |
| HJBed | Menu probes at connect | 300 ms apart |
| HJBed | BJRN preset save | waits 3 s |
<!-- /generated -->

## Wire codec

`codec/richmat.py` holds the transports, framing, checksum and every command
encoder below. Profiles in `profiles/richmat.py` hold the codes, transport order
and timing.

### Transports

<!-- generated:richmat-transports -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Key | Service | Write | Notify | Commands | Profiles |
|---|---|---|---|---|---|
| N1 | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | bare code | Richmat WiLinke, Richmat Nordic, Richmat Prefix55, Richmat PrefixAA, HJBed, Richmat MH Revive Control, Richmat MH Best Mattress, Richmat MH Blvd Home, Richmat MH HARMONY, Richmat MH Idealbed |
| W0 | `8ebd4f76-da9d-4b5a-a96e-8ebfbeb622e7` | `d44bc439-abfd-45a2-b575-925416129600` | `d44bc439-abfd-45a2-b575-925416129601` | framed | Richmat WiLinke, Richmat Nordic, Richmat Prefix55, Richmat PrefixAA |
| W1 | `0000fee9-0000-1000-8000-00805f9b34fb` | `d44bc439-abfd-45a2-b575-925416129600` | `d44bc439-abfd-45a2-b575-925416129601` | framed | Richmat WiLinke, Richmat Nordic, Richmat Prefix55, Richmat PrefixAA, BedTech, L&P MlRM, HJBed, Richmat MH Revive Control, Richmat MH Best Mattress, Richmat MH Blvd Home, Richmat MH HARMONY, Richmat MH Idealbed |
| W2 | `0000fee9-0000-1000-8000-00805f9b34bb` | `d44bc439-abfd-45a2-b575-925416129622` | `d44bc439-abfd-45a2-b575-925416129611` | framed | Richmat WiLinke, Richmat Nordic, Richmat Prefix55, Richmat PrefixAA, HJBed, Richmat MH Revive Control, Richmat MH Best Mattress, Richmat MH Blvd Home, Richmat MH HARMONY, Richmat MH Idealbed |
| W3 | `0000ffe0-0000-1000-8000-00805f9b34fb` | `0000ffe2-0000-1000-8000-00805f9b34fb` | `0000ffe1-0000-1000-8000-00805f9b34fb` | framed | Richmat WiLinke, Richmat Nordic, Richmat Prefix55, Richmat PrefixAA, HJBed, Richmat MH Revive Control, Richmat MH Best Mattress, Richmat MH Blvd Home, Richmat MH HARMONY, Richmat MH Idealbed |
| W4 | `0000fff0-0000-1000-8000-00805f9b34fb` | `0000fff2-0000-1000-8000-00805f9b34fb` | `0000fff1-0000-1000-8000-00805f9b34fb` | framed | Richmat WiLinke, Richmat Nordic, Richmat Prefix55, Richmat PrefixAA, HJBed, Richmat MH Revive Control, Richmat MH Best Mattress, Richmat MH Blvd Home, Richmat MH HARMONY, Richmat MH Idealbed |
| W5 | `0000e0ff-3c17-d293-8e48-14fe2e4da212` | `00000002-3c17-d293-8e48-14fe2e4da212` | `00000003-3c17-d293-8e48-14fe2e4da212` | framed | Richmat WiLinke, Richmat Nordic, Richmat Prefix55, Richmat PrefixAA, HJBed |

W0 is the legacy custom service, W4 and W5 are name-guarded (see the Richmat
profile's Setup). The Richmat routes try W0 to W5, then N1, then fall back to W1.
<!-- /generated -->

### Framing and checksum

- `sum8` is the low byte of the sum of every byte before it. Values are masked to
  eight bits, as the apps do.
- A **command** is `6E 01 side code sum8`. `side` is `00` for a single bed;
  RMControl uses `01` for right and `02` for both; HJBed sends both sides as
  separate `00` and `01` frames; the Richmat MH apps put their `txMode` byte
  there (`00` in the single-device group).
- Nordic UART transports take the bare code. The legacy Richmat routes also frame
  the code behind a `55` or `AA` header:

<!-- generated:richmat-framing -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Framing | Layout | Flat |
|---|---|---|
| wilinke | `6E 01 00 code sum8` | `6E 01 00 31 A0` |
| nordic | bare code | `31` |
| prefix55 | `55 01 00 code sum8` | `55 01 00 31 87` |
| prefixaa | `AA 01 00 code sum8` | `AA 01 00 31 DC` |
<!-- /generated -->

- **Extended records** are `6E len 20 domain command operation data sum8`, where
  `len` counts the whole frame. Notifications place the length after `20`.
- Richmat MH **mattress** frames use the `5E` header with the same checksum and
  no side byte.

### Command encoders

#### Fixed-table buttons

Codes are the profile's; frames are built by the codec with WiLinke framing.

<!-- generated:richmat-commands -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Command | Richmat (WiLinke) | BedTech | L&P MlRM |
|---|---|---|---|
| Head up | `6E 01 00 24 93` | `6E 01 00 24 93` | `6E 01 00 24 93` |
| Head down | `6E 01 00 25 94` | `6E 01 00 25 94` | `6E 01 00 25 94` |
| Feet up | `6E 01 00 26 95` | `6E 01 00 26 95` | `6E 01 00 26 95` |
| Feet down | `6E 01 00 27 96` | `6E 01 00 27 96` | `6E 01 00 27 96` |
| Head and feet up | `6E 01 00 29 98` | n/a | n/a |
| Head and feet down | `6E 01 00 2A 99` | n/a | n/a |
| Pillow up | `6E 01 00 3F AE` | `6E 01 00 29 98` | n/a |
| Pillow down | `6E 01 00 40 AF` | `6E 01 00 2A 99` | n/a |
| Lumbar up | `6E 01 00 41 B0` | n/a | n/a |
| Lumbar down | `6E 01 00 42 B1` | n/a | n/a |
| Flat | `6E 01 00 31 A0` | `6E 01 00 31 A0` | `6E 01 00 31 A0` |
| Zero-G | `6E 01 00 45 B4` | `6E 01 00 45 B4` | `6E 01 00 45 B4` |
| Anti-Snore | `6E 01 00 46 B5` | `6E 01 00 46 B5` | `6E 01 00 46 B5` |
| TV | `6E 01 00 58 C7` | `6E 01 00 58 C7` | `6E 01 00 58 C7` |
| Lounge | `6E 01 00 59 C8` | `6E 01 00 65 D4` | `6E 01 00 59 C8` |
| Save lounge | `6E 01 00 65 D4` | n/a | n/a |
| Light toggle | `6E 01 00 3C AB` | `6E 01 00 3C AB` | `6E 01 00 3C AB` |
| Light off | n/a | `6E 01 00 75 E4` | n/a |
| Massage toggle | `6E 01 00 5D CC` | `6E 01 00 5D CC` | `6E 01 00 32 A1` |
| Massage off | `6E 01 00 5E CD` | n/a | `6E 01 00 47 B6` |
| Head massage step | `6E 01 00 4C BB` | `6E 01 00 4C BB` | `6E 01 00 32 A1` |
| Foot massage step | `6E 01 00 4E BD` | `6E 01 00 4E BD` | `6E 01 00 33 A2` |
| Massage mode step | `6E 01 00 48 B7` | `6E 01 00 48 B7` | `6E 01 00 38 A7` |
| Head massage up | n/a | n/a | `6E 01 00 4C BB` |
| Head massage down | n/a | n/a | `6E 01 00 4D BC` |
| Foot massage up | n/a | n/a | `6E 01 00 4E BD` |
| Foot massage down | n/a | n/a | `6E 01 00 4F BE` |
| Massage intensity up | n/a | n/a | `6E 01 00 34 A3` |
| Massage intensity down | n/a | n/a | `6E 01 00 35 A4` |
| Wave massage | n/a | n/a | `6E 01 00 39 A8` |
| Massage timer 10 min | n/a | n/a | `6E 01 00 5F CE` |
| Massage timer 20 min | n/a | n/a | `6E 01 00 63 D2` |
| Massage timer 30 min | n/a | n/a | `6E 01 00 61 D0` |
| Controller sync on | `6E 01 00 BC 2B` | n/a | n/a |
| Controller sync off | `6E 01 00 BD 2C` | n/a | n/a |
| STOP | `6E 01 00 6E DD` | `6E 01 00 5E CD` | `6E 01 00 6E DD` |
| Compatibility STOP (QRRM, BT6500 remotes) | `6E 01 00 5E CD` | n/a | n/a |
<!-- /generated -->

#### Memory

<!-- generated:richmat-memory -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Command | Richmat (WiLinke) | BedTech | L&P MlRM |
|---|---|---|---|
| Memory 1 recall | `6E 01 00 2E 9D` | `6E 01 00 2E 9D` | `6E 01 00 2E 9D` |
| Memory 2 recall | `6E 01 00 2F 9E` | `6E 01 00 2F 9E` | `6E 01 00 2F 9E` |
| Memory 3 recall | `6E 01 00 30 9F` | n/a | n/a |
| Memory 4 recall | `6E 01 00 B2 21` | n/a | n/a |
| Memory 5 recall | `6E 01 00 F4 63` | n/a | n/a |
| Memory 1 save | `6E 01 00 2B 9A` | `6E 01 00 2B 9A` | `6E 01 00 2B 9A` |
| Memory 2 save | `6E 01 00 2C 9B` | `6E 01 00 2C 9B` | `6E 01 00 2C 9B` |
| Memory 3 save | `6E 01 00 2D 9C` | n/a | n/a |
| Memory 4 save | `6E 01 00 B3 22` | n/a | n/a |
| Memory 5 save | `6E 01 00 F5 64` | n/a | n/a |

The Richmat remote code decides how many slots appear (up to three); recall and
save accept every listed slot.
<!-- /generated -->

#### Lights

<!-- generated:richmat-lights -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Command | RGB strip (QRRM family) | Legacy RGB |
|---|---|---|
| On | `04 09 04 01 00 02 00 00 14` | `6E 0A 00 01 79` |
| Off | `04 09 04 01 00 00 00 00 12` | light toggle |
| Colour | `04 0B 01 01 00 R G B 00 00 sum8` | `6E 0C FF R sum8 6E 0D G B sum8` (one write) |
| Timer | minutes, for example 5 min `04 0A 02 01 00 00 05 00 00 16` | seconds, for example 5 min `6E 0B 01 2C A6` |
| Always On | `04 0A 02 01 00 00 00 00 00 11` | `6E 0B 00 00 79` |
<!-- /generated -->

#### Function selectors

The catalog apps send a few actions behind their own prefix instead of
`6E 01 side`:

<!-- generated:richmat-functions -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Catalog action | Prefix |
|---|---|
| `ItemExitLimit` | `6E 02 01` |
| `ItemCheckClock` | `6E 08 01` |
| `ItemCheckLight` | `6E 0A 00` |
| `ItemCheckMusic` | `6E 15 01` |
| `ItemCheckAroma` | `6E 1A 00` |
| `ItemCheckMattress` | `5E 1A 00` |
| `ItemCheckSnore` | `6E 21 00` |
| `ItemCheckSpeech` | `6E 22 00` |
| `ItemCheckDetection` | `6E 9A C0` |
| `ItemSendStartDetection` | `6E 88 C2` |
| `ItemQueryVersion` | `6E 9A 00` |
| `VersionOneBedCurrentMode` | `6E 9A 10` |
| `VersionOneMotor1CurrentAngle` | `6E 9A 30` |
| `VersionOneMotor2CurrentAngle` | `6E 9A 30` |
| `VersionOneMotor3CurrentAngle` | `6E 9A 30` |
| `VersionOneMotor4CurrentAngle` | `6E 9A 30` |
| `VersionOneCurrentMassageMode` | `6E 9A A0` |
| `VersionOneCurrentBedLightStatus` | `6E 9A B0` |

Every other catalog action uses `6E 01 side`. HJBed sends only the first four.
<!-- /generated -->

#### Variable frames

| Frame | Layout |
|-------|--------|
| Light timer | `6E 0B high low sum8`; each app chooses its always-on value |
| Light colour | `6E 0C FF R sum8` + `6E 0D G B sum8`, one write |
| Countdown alarm | `6E 05 low slot sum8`, then `6E 06 high action sum8`; zero minutes and action cancel |
| Repeating alarm | Extended `05 01 01` (create), `05 02 01` (delete), `05 01 00` (query) |
| Time sync | Extended `08 02 01`: Unix time (4 bytes, big-endian) + whole-hour offset; `08 03 01`: `year−1970 month day hour minute second` |
| Snore intervention | Extended `06 01 01` (switch), `06 05 01` (configure), `06 03 00` (sleep-advertisement query) |
| Control mode (HJBed) | Extended `0B 02 00` (query) and `0B 02 01` (set) |
| RGB strip (QRRM family) | `04 len command 01 00 payload 00 00 sum8` |

### Responses

The fixed-table routes read no responses. Each catalog app keeps its own
parser: RMControl's `NotificationBuffer`, the Richmat MH `Classifier` (two app
groups) and HJBed's stream splitter. All check the additive checksum. See each
profile's Notifications.

### STOP and release behavior

- STOP is the command with code `6E`. QRRM and BT6500 Richmat remotes, and every
  BedTech bed, stop with `5E` instead.
- Movement always ends with STOP, sent with a fresh cancel event, so a cancelled
  hold still releases the motors. The BedTech route reports a failed STOP; the
  others log it and keep the original error.
- The catalog apps release per catalog entry: some actions are followed by STOP,
  others are not (see each profile's Controls).

### Vectors

`tests/richmat_vectors.py` freezes each profile's frames: the accepted reports'
literals for the catalog apps, and the pre-v5 controllers' frames for the
fixed-table routes. `tests/test_richmat_vectors.py` checks that every literal
round-trips through the codec and that each profile sends only frozen frames.
For the fixed-table routes the two sets are equal.

## Profiles

### Richmat remotes

**Status:** ✅ Tested

The `richmat` bed type. Its protocol variant picks the framing (one
[profile](#choosing-a-profile) each); its Richmat remote code picks the motors,
presets, memory slots, light packets and STOP.

#### Setup

- **Variant:** `auto` detects the transport. It tries the WiLinke services W0 to
  W5, using the write characteristic or, on single-characteristic beds such as
  Germany Motions `DHN-*`, a writable notify characteristic (without response).
  Then Nordic UART selects the Nordic variant, and otherwise W1 is used.
  `wilinke`, `prefix55` and `prefixaa` still detect the characteristic.
- **Remote code:** `richmat_remote` names the physical remote; `auto` keeps a
  generic layout. Features come from the 456-code generated mapping plus manual
  overrides.

FEE9/QRRM advertisements are shared with BedTech. A confirmed BedTech-specific
manufacturer field (`0x4C57`) selects the BedTech protocol; QRRM devices without
that field retain Richmat behavior, including the confirmed Casper RGB-light model.

QRRM is a generic controller name, not a single physical remote layout. For the
L&P surface reported in issue #504, with Flat, Zero G, Custom 1, and Custom 2,
choose **L&P QRRM** under the integration options. It remains an explicit profile
because the BLE name and GATT layout do not distinguish it from other QRRM
surfaces.
The current L&P and Richmat apps make the same explicit product-profile choice;
their generic QRRM profiles contain no controls. On the hardware from
issue #504, Flat is confirmed. The other command frames are statically verified
across the apps but have not yet been validated on that physical bed.

The QRRM receiver in issue #695 (Sven & Son, `WLT825X_H35_S`) is paired with an
HJH89 remote whose label prints, and QR-encodes, `GGRM`. Choose **GGRM / HJH89**
for that handset: head, feet, pillow (head tilt) and lumbar motors, Flat, Zero G,
Anti-snore, one memory, massage and a white light toggle. The Revive Control,
Blvd Home and HARMONY catalogs define the same GGRM controls and release with
`0x6E`, so this profile does not use the `0x5E` compatibility stop, which those
catalogs send as massage All Off. Hardware validation is pending.
With massage enabled, GGRM exposes All Off (`0x5E`), head/foot intensity steps
and mode stepping. It does not expose the generic all-massage toggle (`0x5D`),
which is absent from those GGRM catalogs.
The WiLinke GGRM profile also exposes Save Zero G and Save Anti-snore, plus
10, 20 and 30 minute massage buttons when massage is enabled. These are
one-shot catalog actions followed by the standard release after 120 ms.
Timer buttons do not claim to report the bed's current timer setting.
The commands are proven by the accepted row055 Revive Control, Blvd Home and
HARMONY GGRM tables; physical behavior on the issue #695 bed remains unverified.

The app tries BLE services in this order:

1. **WiLinke 1**: `0000FEE9-0000-1000-8000-00805F9B34FB`
2. **WiLinke 2**: `0000FEE9-0000-1000-8000-00805F9B34BB`
3. **Nordic UART**: `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
4. **FFF0**: `0000FFF0-0000-1000-8000-00805F9B34FB`
5. **FFE0**: `0000FFE0-0000-1000-8000-00805F9B34FB`

> **W5 (`0000E0FF-3C17-D293-8E48-14FE2E4DA212`) caveat:** the Germany Motions app
> also lists a sixth "W5" service on a Telink-style custom 128-bit base (`0xE0FF`
> is just the little-endian form of the generic `0xFFE0`). That base is shared by
> non-bed Telink-chip devices, so a "Nokia-*" headset was misdetected as a Richmat
> bed (issue #382). W5 is therefore **not** used for passive discovery and only
> detects as a bed when the device name also matches a Richmat pattern.

> **W4 (`0000FFF0-...`) caveat:** FFF0 is a fully generic short UUID that many
> non-bed devices advertise — a "NO_DVR-*" camera system was misdetected as a
> Richmat bed (issue #418). All known W4 beds are Germany Motions units named
> `DHN-*` (the GM Bed Control app scans unfiltered and identifies beds by
> name/remote code, never by bare FFF0), so W4 likewise only detects as a bed
> when the device name also matches a Richmat pattern. FFF0 stays in
> `manifest.json` for passive discovery because SUTA and the Keeson Sino
> fallback also rely on it (both name-guarded as well).

Device name hints:

| Device Name Prefix | Features |
|-------------------|----------|
| `WFRM`, `FWRM` | Table/Lift with height control |
| `6BRM` | Nordic variant (170ms timing) |
| `TWRM`, `MLRM` | Fast timing (110ms) |
| `YGRM`, `BRRM` | Extended presets |

#### Controls

- Motors follow the remote code: head and feet always, pillow and lumbar when
  the remote has them. Back and legs are aliases of head and feet.
- `0x29`/`0x2A` are exposed as the `head_feet` cover, but only for remotes listed
  in `RICHMAT_COMBINED_HEAD_FEET_REMOTE_CODES`. Confirmed on hardware (#552): on
  two `twrm` beds (`WLT` / `WLT825X_H35_S`) the command raises head and feet at
  the same time, which two sequential cover commands cannot do because each
  Richmat motor command ends with its own STOP frame. Not every Richmat remote
  surface has this button, and the head and feet motor flags do not say which
  ones do, so the entity stays opt-in per remote code. Add a code to the set when
  a bed on that profile is confirmed. `auto` is excluded on purpose: it is the
  fallback whenever detection cannot name the remote.

> [!NOTE]
> The BedTech app calls the same byte pair `bothHeads`, which would mean two head
> sections rather than head plus feet. The naming across apps is not settled here;
> the per-remote allow list is what keeps the control off unconfirmed beds.

- Massage toggle (`5D`) is offered except on GGRM, which gets All Off (`5E`).
- **Lights:** most Richmat beds have a simple white under-bed light controlled
  via toggle. Some models (Casper, certain QRRM/I7RM remotes) have RGB light
  strips with full color control. BT6500 uses the plain white toggle light
  command. RGB is available on WiLinke-variant beds when a specific remote code
  is configured (not "Auto").
  - **RGB strip** (Casper, QRRM, I7RM with Casper/SleepFunction in the name):
    explicit on/off, color and timer. Timer range: 1-30 minutes or "Always On".
  - **Legacy RGB** (other WiLinke remotes with the lights feature flag): power-on,
    color and timer. Timer range: 1-5 minutes or "Always On". Off is the toggle.
  - RGB-capable beds expose a **Light** entity with a color wheel instead of a
    simple on/off switch. See [Lights](#lights) for the frames.
- **Controller Sync** sends `BC` (on) or `BD` (off).

**Controller Sync** (previously **Synchro Mode**) sends the selected controller's
sync command. It does not mirror commands between two Home Assistant entries.
The displayed switch state records requested changes, not confirmed movement or
sync status from the bed. In the HJC9 report, enabling it on both frames did not
make them move together.

For independently controllable frames, use the **Combine two beds into one
(Dual Bed)** flow, or keep standalone entries and control both with a script.
See [Controller Sync and two-frame setup](../CONFIGURATION.md#split-king--controller-sync)
for the distinction, setup guidance, and a script example.

**GGRM catalog actions** (WiLinke only; the massage timers need massage enabled):

<!-- generated:richmat-ggrm -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| GGRM action | WiLinke frame |
|---|---|
| Save Zero G | `6E 01 00 66 D5` |
| Save Anti-snore | `6E 01 00 69 D8` |
| Massage 10 min | `6E 01 00 5F CE` |
| Massage 20 min | `6E 01 00 63 D2` |
| Massage 30 min | `6E 01 00 61 D0` |
<!-- /generated -->

Codes listed by the apps that this route does not send:

| Group | Codes |
|-------|-------|
| Motors 5-7 (select table/lift actuators) | `71`/`72`, `73`/`74`, `D0`/`D1` |
| Combined movements | All `56`/`57`, Lumbar+Pillow `43`/`44`, Lumbar+Pillow Tilt `5B`/`5C`, Feet+Lumbar `96`/`97`, Head up + Feet down `21`, Head down + Feet up `22` |
| Presets | Yoga `F0`, Read `F2`, Side Sleeper `BA`, Sleep `8E`, Wakeup `93`, Flat Sleep `F6` |
| Save presets | Zero-G `66`, Anti-Snore `69`, TV `64`, Yoga `F1`, Side Sleeper `BB`, Sleep `8F`, Wakeup `94`, Flat Sleep `F7` (GGRM sends `66` and `69` as catalog actions) |
| Preset resets | Motor `BE`, TV `CA`, Snore `CB`, Zero-G `CC` |
| Discrete massage | Head off/1/2/3 `98`-`9B`, Foot off/1/2/3 `9C`-`9F`, Third motor increment `E0` |

#### Timing

Pulse defaults are in [Fixed-table routes](#fixed-table-routes). From app
disassembly analysis (SleepFunction):

| Device Name Prefix | Interval | Notes |
|-------------------|----------|-------|
| `6BRM` (Nordic) | 170ms | Nordic vendor |
| `TWRM`, `MLRM` | 110ms | Faster repeat |
| Default | **150ms** | Most devices |

Motor commands are sent continuously while the button is held. STOP is sent on
release.

#### Evidence

The Richmat remotes send only their frozen frames. The GGRM catalog actions are
proven by the [row055 accepted authority](../apk-analysis/dispositions/row055-richmat-cluster.md#accepted-authority)
(Revive Control, Blvd Home and HARMONY GGRM tables, with the `main_6e` release and
its 120 ms delay); the other frames are the pre-v5 controller's.

### BedTech

**App:** [BedTech](https://play.google.com/store/apps/details?id=com.bedtech), `com.bedtech`

**Status:** ✅ Tested

Behaves as the Richmat remotes route with WiLinke framing on W1, except as below.

#### Setup

The `bedtech` bed type, on the W1 service and write characteristic.

> [!NOTE]
> BedTech shares the FEE9 service UUID and characteristic with Richmat WiLinke.
> QRRM controllers that advertise manufacturer ID `0x4C57` are identified as
> BedTech. Because ESPHome proxy snapshots can omit that field, the integration
> also checks the connected controller's vendor model: the confirmed BedTech
> BT3000 reports `WLT825X_H35`, while the confirmed Casper/Richmat HJC27 reports
> `WLT825X_H35_S`. Unknown QRRM models are left unchanged rather than guessed.

The official app (react-native-ble-manager) uses **write-with-response**
(`BleManager.write`) for every command; its `writeWithoutResponse` wrapper is
never called. An earlier claim that the app used write-without-response (and
that write-with-response made lights/lounge fail) came from an experiment for
issue #243, not from the official app's implementation. Verified against
BedTech 7.1.3 Hermes bytecode (2026-07-10, issue #410).

#### Controls

Codes are ASCII characters of the BedTech app: Head `$`/`%`, Foot `&`/`'`,
Leg/Pillow `)`/`*`, Flat `1`, Zero-G `E`, Anti-Snore `F`, TV `X`, Lounge `e`,
memory `.`/`/` (save `+`/`,`), Light toggle `<`, Light off `u`, Massage on `]`,
Massage switch `H`, Head/Foot massage up `L`/`N`, and STOP `^`. See
[Fixed-table buttons](#fixed-table-buttons) for the frames.

- The light has no discrete ON: the integration's on and toggle both send `<`.
  `.` and `+` belong to memory slot 1.
- Pillow and leg use `)`/`*`.

> [!WARNING]
> Earlier versions of this document labeled `)`/`*` as "leg/pillow" and
> `?`/`@`/`A`/`B` as "both heads"/"both feet". The BedTech 7.1.3 command
> table maps `)`/`*` to `bothHeads`, `?`/`@` to `pillow`, and `A`/`B` to
> `lumbar` (pillow/lumbar exist only on BT6500). The integration's entity
> mapping still follows the old labels and needs a separate verification
> pass before being changed.

App codes the integration does not send:

| Group | Codes |
|-------|-------|
| Pillow (BT6500) | `?` `3F` / `@` `40` |
| Lumbar (BT6500) | `A` `41` / `B` `42` |
| Flat (alt, app `flat2`) | `l` `6C` |
| Massage off | `^` `5E` (the integration sends it as STOP) |
| Head / foot massage down | `M` `4D` / `O` `4F` |
| Massage modes | Constant `:` `3A`, Pulse `8` `38`, Wave 1-3 `I`/`J`/`K` `49`-`4B` |
| Massage timer | 10 min `_` `5F`, 20 min `c` `63`, 30 min `a` `61` |

The app gates features per user-selected model; command bytes are shared.

| Model | Light | Massage | Pillow/Lumbar | Dual (head2) | Presets |
|-------|-------|---------|---------------|--------------|---------|
| BT2000 | ❌ | ❌ | ❌ | ❌ | flat, zero-g, anti-snore |
| BT2500 | ❌ | head only | ❌ | ❌ | flat, zero-g, anti-snore |
| BT3000 | ✅ | head+foot | ❌ | ❌ | + TV |
| BT3000FH | ✅ | head+foot | ❌ | ✅ | + TV |
| BT6500 | ✅ | head+foot | ✅ | ❌ | flat, zero-g, anti-snore |
| BTX4 | ❌ | ❌ | ❌ | ❌ | flat, zero-g |
| BTX4FH | ❌ | ❌ | ❌ | ✅ | flat, zero-g |
| BTX5 | ✅ | head+foot | ❌ | ❌ | flat, zero-g, anti-snore |
| BTX5FH | ✅ | head+foot | ❌ | ✅ | flat, zero-g, anti-snore |

BT2000/BT2500/BTX4/BTX4FH owners have no BLE light command at all — the
app hides the button. `light2` (`_u`/`_<`) is only offered on BT3000FH.

**Dual base.** For dual-base (King/Split King) beds the app sends secondary
controls with `_` prefixed (Head2 `_$`/`_%`, Preset2 Flat `_1`, Light2 Toggle
`_<`, Memory2 `_/`), framed as `6E 01 01 code sum8`. The integration does not
send them.

#### Timing

The app repeats only motor position commands (`repeat: 1` in its command
table), re-sending every `repeat_ms` while the button is held. Presets,
memory, massage, and light commands are sent once. The app sends no stop
command on button release (BT6500 field reports still show `^` acting as
stop, so the integration keeps sending it).

#### Evidence

BedTech sends only its frozen frames, the pre-v5 controller's, checked against
BedTech 7.1.3 Hermes bytecode (issue #410).

### L&P MlRM

**App:** [L&P Adjustable Base](https://play.google.com/store/apps/details?id=com.richmat.lp2) 2.3.25, `com.richmat.lp2`

**Status:** ✅ Tested

Behaves as the Richmat remotes route with WiLinke framing on W1, except as below.

#### Setup

The `leggett_wilinke` bed type, and the `mlrm` app profile of `leggett_platt`.
Detection: name prefix `MlRM` with a WiLinke service. Writes use the W1 write
characteristic `d44bc439-abfd-45a2-b575-925416129600` with response. See
[Leggett & Platt](leggett-platt.md) for the other Leggett variants.

#### Controls

- Discrete massage: head and foot up/down, overall intensity up/down, wave and
  pattern step, head/foot toggles and Stop Massage, instead of the Richmat step
  commands. See [Fixed-table buttons](#fixed-table-buttons).
- Massage timer select: 10, 20 or 30 minutes; 0 sends Stop Massage. The timer
  state is optimistic: the bed reports nothing, so the physical remote can make
  it stale.
- Lights are toggle-only.
- Motor buttons instead of covers (`has_discrete_motor_control`).
- The app also has save codes for Zero-G `66`, Anti-Snore `69`, TV `64` and
  Lounge `65`; the integration does not send them.

#### Timing

Presets and memory recall are held, then released with STOP; the repeat count and
interval are in [Fixed-table routes](#fixed-table-routes).

#### Evidence

L&P MlRM sends only its frozen frames, the pre-v5 controller's.

### RMControl

**App:** [RMControl](https://play.google.com/store/apps/details?id=com.richmat.rmcontrol2) 21.3.7, `com.richmat.rmcontrol2`

**Status:** ❓ Needs testing (source-verified against RMControl 21.3.7, hardware unverified)

These opt-in profiles preserve the app's exact product choices and individual
button commands. Movement, preset, memory, massage, light and extra-action
opcodes are per product: they come from the RMControl catalog in
[`richmat_profiles.py`](../../custom_components/adjustable_bed/richmat_profiles.py),
with separate short, long-press and Nordic short opcodes. An action absent from,
or ambiguous in, the selected catalog is rejected.

#### Setup

- Beds whose RMControl product code is in the app's catalog. An app product
  code identifies a remote layout, not a guarantee that every bed using the same
  Bluetooth service supports the same controls.
- BLE sleep products: the ten source-listed products get the sleep-discovery
  query; HNRN, HQRN, HSRN, HURN, M7RN and MJRN support automatic snore
  intervention.
- Standing-desk-only products (FWRM, WFRM) use a separate desk protocol and are
  rejected.

In the integration's Richmat setup/options:

- Leave **RMControl product** (`rmcontrol_product`) empty to retain the existing
  Richmat behavior. Existing entries are not automatically migrated.
- To opt in, choose the exact product code used in RMControl. Do not select a
  similar-looking product to unlock unsupported controls. Empty catalogs remain
  empty, and standing-desk-only products are rejected.
- Set **RMControl side** (`rmcontrol_side`) to `left`, `right` or `both`. The
  default is `left`. This selects the app's command side, not a new Bluetooth
  address. A paired-bed service's optional `side` selects which paired controller
  receives the operation; it does not add a side byte to specialized packets.

- The controller discovers the selected transport's actual service, writable
  characteristic and notification role. Exactly one known writable transport
  must be present (W1, W2, W3, W4, W5, then N1, which is unframed).
- Writes use response unless the characteristic offers write without response.
- It does not broaden automatic discovery to every device advertising a shared
  Bluetooth service.

Connection setup subscribes to the notification role, then sends:

<!-- generated:rmcontrol-startup -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Step | Sent when | Frames |
|---|---|---|
| Exit limit | always | `6E 02 01 00 71` (Nordic `00`) |
| Time sync | the product has an alarm catalog | extended `08 02 01` then `08 03 01` |
| Sleep-advertisement query | a BLE sleep product | extended `06 03 00`: `00` |
| Check clock | always | `6E 08 01 01 78` (Nordic `01`) |
| Check light | always | `6E 0A 00 01 79` (Nordic `01`) |
<!-- /generated -->

It then waits up to 5 seconds (an integration readiness budget, not an on-wire
interval) for the light, alarm and sleep-advertisement replies the product
expects. Some beds omit optional
replies; basic controls stay usable and late replies are accepted.

#### Controls

Standard movement, presets, memory programming, massage and lighting appear
where the selected catalog supports them. Additional catalog actions are exposed
as **disabled-by-default buttons**. Enable the relevant entities in the device's
entity list.

- Button names retain the app getter/context and occurrence number where needed
  to distinguish variants. Long-press actions have separate buttons; held
  movement uses cancellable repeats and protocol-specific release cleanup.
- This includes supported combined/extra motor commands and less common heating,
  fan, airbag, anti-pinch, aroma, music and sleep actions. It does not invent
  parameterized controls merely because the shared library can parse a report.
- Phone flashlight, menus, headings, desk-only and sofa-specific controls are
  excluded.
- Head and foot massage strength actions appear as intensity up/down controls
  when the selected product provides both directions. A product with only a
  strength-increase action retains its named product button; it does not expose
  that action as a zone on/off toggle.

Sensors and binary sensors are added when their corresponding state is first
reported, rather than creating permanently unknown entities for every catalog.
Diagnostics retain the selected product, transport, capability replies, decoded
state, supported alarm action names and all received alarm records. Reported
numeric values without proven units are deliberately unitless. A numbered motor
is not silently relabeled as a particular physical axis.

##### Lighting

- RGB starts unknown until a color report arrives.
- Where supported, the light timer offers **Always On** and **1 through 15
  minutes**. Always On uses the app's `ff ff` timeout representation.
- A generic light capability alone is not a promise of RGB support. Color and
  timer controls require the app's light acknowledgment and selected strip flag.
- PARN accepts only its eight source-defined colors, listed as exact RGB tuples
  in diagnostics; other colors are rejected.

| Command | Frame | Description |
|---------|-------|-------------|
| Action (framed) | `6e 01 side cmd SUM` | Short or long-press opcode |
| Action (Nordic) | `cmd` | Nordic short opcode, or the long-press opcode |
| STOP / release | `6e 01 side 6e SUM` (Nordic: `6e`) | Sent after every sustain press with a fresh cancel event |

Light timer: seconds, 0 sends `ff ff` (Always On). See
[Variable frames](#variable-frames) for alarms, time sync and snore intervention;
`repeat_mask` uses bit 7 for Monday through bit 1 for Sunday.

#### Timing

See [Catalog app timing](#catalog-app-timing).

#### Notifications

Frames must start with `6e` and carry a valid additive checksum; unknown or
malformed frames have no effect.

| Frame | Meaning |
|-------|---------|
| `6e09010078`, `6e0e00037f`, `6e1a000189`, `6e16010186`, `6e90c101c0`, `6e2100008f` | Alarm, light, aroma, music, detection and anti-snore capability |
| `6e07010177` / `6e07010278` | Single alarm added / cancelled |
| `6e23018416` / `6e23008415` | Locked / unlocked |
| `6e23a06e9f` | Anti-snore stop music |
| `6e 90 selector value SUM` | Protocol version, bed mode, motor (number, status, angle), massage mode/strengths, music, detection status, component diagnostics |
| `6e 20 len …` | Extended reports: diagnostics, sleep advertisement, RGB, light timer, white light, lock, press mode, fan, aroma, heating, massage, motor travel, motor angle, alarm records |

The receive buffer assembles fragmented or coalesced notifications and discards
a partial frame after 500 ms without new data, as the app's timer does.

#### Services

##### Alarm service

Use `adjustable_bed.rmcontrol_alarm`, selecting the device and operation. It
requires an explicitly selected RMControl profile and the appropriate supported
alarm capability. Action names must come from that device's diagnostics
`alarm_actions` list, not raw bytes or another product's catalog. Ambiguous or
absent actions are rejected before writing.

| Operation | Additional fields | Effect |
| --- | --- | --- |
| `single` | `minutes` (1..65535), `action` | Run the selected action after a countdown measured in minutes. |
| `cancel_single` | None | Cancel the countdown alarm. |
| `repeat` | `alarm_id` (1..7), `time`, `weekdays`, `action` | Create or replace the selected repeating-alarm slot at local time, with minute precision. |
| `delete` | `alarm_id` (1..7) | Delete that repeating-alarm slot. |
| `query` | None | Request repeating-alarm records; received records appear in state/diagnostics. |
| `sync` | None | Send current Home Assistant time, timezone and local calendar values to the supported alarm subsystem. |

- `weekdays` uses `monday` through `sunday`; it is not a raw bit mask.
- An optional `side` accepts `left`, `right` or `both` for paired-bed targeting.
- Replacing a slot changes the alarm stored on the bed, not merely a Home
  Assistant automation.
- A **single alarm is a countdown**, not a wall-clock alarm or time-sync
  operation.
- The separate synchronization protocol encodes timezone offsets in whole hours,
  truncated toward zero. Half-hour and quarter-hour offsets cannot be represented
  fully; this is a source-proven limitation, not an automatic adjustment by HA.
- New alarm creation resolves the current selected product's effective command,
  including its override. It does not reproduce the app's separate restoration
  path that can discard an override.

The app's single and repeating alarm pages are distinct. An alarm acknowledgment
and nonempty selected `alarmList` normally enable the menu; PNRN has the app's
explicit initial-menu exception. The exact product flag then chooses single or
repeating operations. An empty action list never permits arbitrary alarm actions.
Time synchronization has its own condition, a nonempty `alarmList`, and is also
performed during connection setup independently of the repeating-alarm flag.

##### Automatic snore intervention

Use `adjustable_bed.rmcontrol_anti_snore`. This is separate from moving to the
anti-snore preset position.

| Operation | Additional fields | Effect |
| --- | --- | --- |
| `switch` | `enabled` (boolean) | Enable or disable supported automatic snore detection/intervention. |
| `configure` | `mode` (`count` or `time`), `value` (0..255) | Set the app's intervention count or time value. |
| `query` | None | Request the enable state and intervention configuration. |

- The service also accepts the paired-bed `side` field.
- The time mode deliberately does not claim seconds or minutes where the
  artifact does not establish that unit.
- Configuring count/time is not equivalent to enabling the feature.

This service requires the app's BLE sleep-monitoring metadata, a received sleep
advertisement event and one of its six supported selectors: HNRN, HQRN, HSRN,
HURN, M7RN or MJRN. The connection setup queries sleep discovery only for the
ten source-listed BLE sleep products. A generic snore state report is not enough
to activate automatic intervention.

#### Evidence

RMControl sends the frames of the selected product's catalog, source-verified
against RMControl 21.3.7 and hardware unverified. The service list is not a
promise that every product supports those features; a rejected operation must not
be worked around by choosing an unrelated product. See the
[implementation ledger](../apk-analysis/row018-rmcontrol-implementation.md) and the
[specialized evidence record](../apk-analysis/row018-rmcontrol-specialized-evidence.md).

### Richmat MH apps

**App:** Revive Control 1.0.26, Best Mattress 1.1.1, Blvd Home 1.0.1, HARMONY 1.0.0 and Idealbed 2.4.2 (see [Apps](#apps))

**Status:** ❓ Needs testing (artifact-verified, hardware unverified)

#### Setup

Revive Control, Best Mattress, Blvd Home, HARMONY and Idealbed share one BLE
library. Their model catalogs, page gates and a few callbacks differ, so each
app is its own explicit bed type and profile. Motor, preset, memory, massage and
page-button opcodes are per model: they come from the generated catalog
[`richmat_mh_catalog.py`](../../custom_components/adjustable_bed/richmat_mh_catalog.py)
(app route, kind, page, app label, opcode, and KEEP interval or 0 for a single
tap). Each is sent as `6e 01 M C SUM`.

These profiles are opt-in: the shared Richmat services and names never select
them automatically, and existing Richmat remote or RMControl entries are not
changed.

1. Add the bed manually and choose the app your phone uses (for example
   **Revive Control app (Richmat)**). Motor count is fixed at two; the model
   decides which motors exist.
2. Leave the protocol variant on `auto` to apply the app's name rule: the first
   four characters of the raw Bluetooth name, lowercased, name the model
   (`7IRM…` selects `7irm`). The raw name is stored at setup.
3. Choose an explicit model variant (`model_<id>`) when the app would ask:
   names starting with `QRRM`, Idealbed names starting with `Cool Touch`, or a
   name with no live model. The variants list exactly the app's picker, setup
   wizard and manual model routes; Idealbed's manual dialog accepts any valid
   model identifier, so every Idealbed model is offered. Labels are the app's
   where the analysis recorded them, otherwise the model identifier.

- The setup and options forms report a name the app cannot resolve on the
  protocol variant field.
- Each side of a two-address pair keeps its own app and model; unpair before
  changing them.

The controller follows the app's GATT selection (Nordic UART, then the fee9 and
ffe0/fff0 maps, then a fallback service; see [Transports](#transports)) and keeps
the characteristic's write type. The fallback skips the generic access and
attribute services (`00001800`, `00001801`).

After subscribing it sends the version query, then the version's initialization
list (timing in [Catalog app timing](#catalog-app-timing)):

<!-- generated:richmat-mh-setup -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Step | VER0 | VER1 |
|---|---|---|
| Version query | `6E 9A 00 00 08` | `6E 9A 00 00 08` |
| Exit one-minute | `6E 02 01 00 71` | `6E 02 01 00 71` |
| Alarm | `6E 08 01 01 78` | `6E 08 01 01 78` |
| LED | `6E 0A 00 01 79` | `6E 0A 00 01 79` |
| Aroma | `6E 1A 00 00 88` | `6E 1A 00 00 88` |
| Mattress | `5E 1A 00 01 79` | `5E 1A 00 01 79` |
| Waist mattress | `5E 1B 00 01 7A` | `5E 1B 00 01 7A` |
| Snore | `6E 21 00 00 8F` | `6E 21 00 00 8F` |
| Speech | `6E 22 00 00 90` | `6E 22 00 00 90` |
| Detection | `6E 9A C0 00 C8` | none |
| Motor mode | none | `6E 9A 10 00 18` |
| Motor 1 angle | none | `6E 9A 30 01 39` |
| Motor 2 angle | none | `6E 9A 30 02 3A` |
| Motor 3 angle | none | `6E 9A 30 03 3B` |
| Motor 4 angle | none | `6E 9A 30 04 3C` |
| Massage query | none | `6E 9A A0 00 A8` |
| Button-light lock query | none | `6E 9A B0 00 B8` |

The app's mattress literal ends in checksum `90`; the sender recomputes its
checksum, so the bed receives the frame above.
<!-- /generated -->

When a VER1 reply mounts the alarm call page during setup, the phone clock is
sent once (as the app's alarm call page does on creation).

- **VER0** (no `6e900001ff` reply) shows the legacy pages built from the model's
  function list, plus pages added by replies: alarm, LED or button-light,
  aroma, snore and detection.
- **VER1** shows the model's entity pages (motors with angle sliders, massage
  with intensity sliders, memories), the alarm call page and the LED page.
  VER1 keeps only the flags of the most recent reply, as the app does.
- The **waist mattress** page appears after a powered `5e1b` table reply.

The replies are stored as a capability snapshot; a change reloads the entities
after the link is released. Revive Control, Blvd Home and HARMONY switch to the
VER1 pages on the first initialization reply; Best Mattress and Idealbed switch
on the version reply.

#### Controls

| Surface | Entities | Frames |
|---------|----------|--------|
| Motors | Covers (KEEP at the control's interval, then STOP 120 ms after release) | `6e 01 M C SUM`, STOP `6e 01 M 6e SUM` |
| Presets, memories, massage, motor-page buttons | Standard presets and memory slots, app-labelled buttons | Tap: one frame, STOP 120 ms later |
| LED page | Colour (RGB light when the motor page has the light toggle, else the colour action), light timeout 0–300 s (0 = always on) | `6e0c ff R s 6e0d G B s`, `6e 0b HH LL` |
| Button-light page | Colour as above, timeout (Blvd Home: 0–15 min); **Button light off** only in Revive Control and Best Mattress, the apps with an emitting OFF button | as above, OFF `75` |
| Smart set lock | **Toggle smart set lock** button, **Smart set lock** state | `6e 01 M 84` once |
| Snore intervention | Select: off, anti-snore, zero gravity (the model's list) | `6e 13 M code` |
| Detection | Start/stop buttons, **Detection** sensor with per-device results | `6e88c210c8`, `6e88c220d8` |
| VER1 angles | Back/foot/pillow angle numbers in the model's range | `6e 88 (30\|bits<<2) angle`, 100 ms after release |
| VER1 massage intensity | Head/foot intensity numbers (both zones sent) | `6e 88 a0 ((foot<<3)\|head)` |
| VER1 motor mode | Select (left/right or mode 1–3) | `6e 88 (10\|bits<<2) 00` |
| VER1 memory arrival | **Reached position** sensor | `6e904` reply |
| Waist mattress | Mode select, per-side heat, pressure and duration selects, per-side alarm sensors | `5e 03 cmd value SUM` |

- The light pages write only colour and timeout. The motor page's light toggle
  is the only on/off the apps send, so a model with it gets an RGB light (on/off
  is the toggle) and a model without it sets the colour with
  `richmat_mh_light_color` instead of a light that could not turn off.
- The light-page lock switch state is shown as **Smart light lock**; these apps
  never send its command.
- Alarm, aroma, waist alarms and light colour are actions (below).

<!-- generated:richmat-mh-fixed -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Command | Frame (single-device group) |
|---|---|
| STOP | `6E 01 00 6E DD` |
| Button light off (Revive Control, Best Mattress) | `6E 01 00 75 E4` |
| Smart set lock toggle, once | `6E 01 00 84 F3` |
| Start detection | `6E 88 C2 10 C8` |
| Stop detection | `6E 88 C2 20 D8` |
| Cancel alarm (single-slot models) | `6E 05 00 00 73` then `6E 06 00 00 74` |
<!-- /generated -->

| Command | Frame | Values |
|---------|-------|--------|
| Motor angle target | `6e 88 (30\|bits<<2) angle SUM` | Absolute angle |
| Massage intensity | `6e 88 a0 ((foot&7)<<3 \| head&7) SUM` | Both zones at once |
| Motor mode | `6e 88 (10\|bits<<2) 00 SUM` | LEFT 1, RIGHT 2, Mode1 1, Mode2 2, Mode3 3 |

| Command | Frame | Values |
|---------|-------|--------|
| Colour | `6e 0c ff R s1` + `6e 0d G B s2` | One 10-byte write, RGB 0-255 |
| Light timeout | `6e 0b HH LL SUM` | Seconds; zero or less sends `ff ff` (always on). The entity-page variant replaces `HH` with `txMode` |

| Command | Frame |
|---------|-------|
| Snore intervention | `6e 13 M code SUM` (code 0 turns it off) |
| Start detection | `6e88c210c8` |
| Stop detection | `6e88c220d8` |

| Command | Frames |
|---------|--------|
| Countdown alarm | `6e 05 lo slot SUM`, then `6e 06 hi action SUM` (minutes, low and high byte) |
| Cancel alarm (single-slot models) | `6e05000073`, then `6e06000074` |
| Delete slot (three-slot models) | `6e 05 00 slot SUM`, then `6e 06 00 00 SUM` |
| Clock (three-slot models) | `6e 13 H M SUM`, then `6e 14 S ff SUM` |

The countdown is `(target − now) mod 1440` minutes; zero becomes 1440.
Three-slot alarms recall M1/M2/M3 with `2e`/`2f`/`30`.

| Alarm massage choice | Opcode |
|----------------------|--------|
| Head | `4c` |
| Foot | `4e` |
| Head and foot (two choices) | `5d` |
| Head and foot intensity increase | `34` |

| Position | Opcode | With head | With foot | With head and foot |
|----------|--------|-----------|-----------|--------------------|
| TV | `58` | `7a` | `7d` | `77` |
| Zero gravity | `45` | `7c` | `7f` | `79` |
| Anti-snore | `46` | `7b` | `7e` | `78` |
| Lounge | `59` | `ad` | `ae` | `ac` |
| M1 | `2e` | `82` | `83` | `81` |
| M2 | `2f` | `a7` | `a8` | `a6` |
| M3 | `30` | `aa` | `ab` | `a9` |

`6e fn (b0+b1) (b2+b3) SUM` over the value's little-endian 32-bit bytes, with
`fn` `1b` (mode 2 startup, minutes), `1c` (mode 3 startup, minutes) and `1d`
(mode 3 pause, hours).

| Command | Frame |
|---------|-------|
| Control | `5e 03 cmd value SUM` |
| Mode | cmd `01`, value 0-9: off, left/right/both relax, wake, decompress |
| Alarm save | `5e 03 0b repeat side intensity H M nowH nowM SUM` |

| Side | Heat | Pressure | Duration | Alarm cancel | Side byte |
|------|------|----------|----------|--------------|-----------|
| Left | `02` | `05` | `08` | `10` | `01` |
| Right | `03` | `06` | `09` | `11` | `02` |
| Both | `04` | `07` | `0a` | `12` | `03` |

| Setting | Values |
|---------|--------|
| Heat | off 0, 2 hours 1, 4 hours 2, 8 hours 3 |
| Pressure | level 1-3 = 1-3 (no off) |
| Duration | 15 / 20 / 30 minutes = 1 / 2 / 3 (no off) |
| Alarm repeat | once `01`, daily `02` |

#### Timing

See [Catalog app timing](#catalog-app-timing). KEEP intervals are per control, in
the catalog.

#### Notifications

| Reply | Meaning |
|-------|---------|
| `6e900001ff` | VER1 |
| `6e09010078` / `6e09010179` | Alarm page / multi-slot alarm page |
| `6e0e00037f` | LED page |
| `6e1a000189` | Aroma page |
| `6e90c101c0` | Detection page |
| `6e90c210d0` / `6e90c220e0` | Detection started / stopped |
| `6e07010177` / `6e07010278` | Alarm set / deleted |
| `6e23a06e9f` | Stop music (classified by Revive Control, Blvd Home and HARMONY only) |
| Prefix `6e901` / `6e903` / `6e90a` | Motor mode / motor angle / massage (the button-light lock prefix is identical and shadowed) |
| Prefix `6e904` / `6e905` | Memory arrival / error |
| Prefix `6e90c` | Detection result |
| Prefix `6e21` | Snore |
| `6e 23 value function SUM` | Callback: function `84` is the smart set lock (`00` locked, `01` unlocked); `21` is snore |
| `5e1b…` (powered 31-byte table) | Waist mattress state |

- Detection results name the device type (`3` motor, `4` massager, `5` UBL, `6`
  USB) and status (`0` error, `1` pass, `2` control box error, `3`
  unplugged).
- VER1 motor-angle replies set the matching angle number, clamped to its
  slider range; massage replies set the head/foot intensity numbers.
- Replies are matched in a shared lowercase-hex buffer, reset when a new `6e` or
  `5e` frame starts and the buffer exceeds 100 characters.

#### Services

- `adjustable_bed.richmat_mh_alarm`: `enabled`, `time` (local, minute
  precision), `position` and `massage` choices from the model's alarm page,
  `slot` (1–3) for three-slot models. The bed receives the minutes until the
  next occurrence. A position with a massage uses the app's combined opcode;
  two massages become head-and-foot; a pair the app cannot express is rejected.
  Three-slot models recall M1/M2/M3 per slot.
- `adjustable_bed.richmat_mh_aroma`: mode 2 startup (1–60 min), mode 3 startup
  (1–60 min) and mode 3 pause (1–12 h), sent as the app's three frames.
- `adjustable_bed.richmat_mh_waist_alarm`: `waist_side`, `enabled`, `time`,
  `repeat` (once/daily), `intensity` (1–3). Saving includes Home Assistant's
  current local time, as the app does.
- `adjustable_bed.richmat_mh_light_color`: `rgb_color`, written as the light
  page's 10-byte colour frame. Available when the LED or button-light page is
  shown.

Alarm countdowns and the waist alarm's current time are read per bed, right
before its frames are built. Connection setup (version query and initialization
list) finishes before any command runs or a sequential pair releases the link.

See [Actions](../SERVICES.md).

#### Evidence

The Richmat MH apps send only frames frozen from their accepted row055 reports;
see the [disposition ledger](../apk-analysis/dispositions/row055-richmat-cluster.md)
for the evidence and every exclusion. Real users should confirm model selection by
name, KEEP/STOP behavior, alarm countdown semantics, LED timeout units and the
waist mattress controls after a beta or release.

`tools/generate_richmat_mh_catalog.py` builds `richmat_mh_catalog.py` from the
machine-local frozen reports (hash-pinned). It reads them from `--phase4-dir`,
`$ADJUSTABLE_BED_PHASE4_DIR`, `disassembly/output/phase4-early` in the checkout,
or the main checkout of a linked worktree; `--check` verifies the committed file
and reports missing inputs instead of failing with a traceback.

### HJBed

**App:** [HJBed](https://play.google.com/store/apps/details?id=com.richmat.hjbed) 2.1.2 (code 21200), `com.richmat.hjbed`

**Status:** ❓ Needs testing (static app evidence; physical behavior, ATT and firmware acceptance unverified)

#### Setup

Choose **HJBed app** and the exact product shown in HJBed. The picker includes all
19 current products and 24 conditionally restored products. Shared services and
Bluetooth names do not identify the layout.

| HA product profile | App label | Remote code | App selector |
| --- | --- | --- | --- |
| `aw_motionhc800` | HC800 | `LTRM` | Conditional |
| `aw_motionsn300` | SN300 | `B3RN` | Conditional |
| `aw_motionsn500` | SN500 | `LTRM` | Conditional |
| `dream_blue` | blue | `LTRM` | Conditional |
| `dream_green` | green | `HARM` | Conditional |
| `dream_orange` | orange | `JMRM` | Conditional |
| `dream_yellow` | yellow | `HBRM` | Conditional |
| `flexxafeg300` | AFEG300 | `L5RN` | Conditional |
| `flexxafeg300sh` | AFEG300-SH | `LPRN` | Conditional |
| `flexx_linkrfrn` | FlexxLink | `RFRN` | Conditional |
| `flexxpb250` | PB250 | `VJRM` | Conditional |
| `flexxpb300` | PB300 | `FARM` | Conditional |
| `flexxpb325` | PB325 | `FARM` | Conditional |
| `flexxpb450` | PB450 | `MPRM` | Conditional |
| `flexxpb450sh` | PB450-SH | `LVRN` | Conditional |
| `hj_bedbjrn` | BJRN | `BJRN` | Current |
| `hj_bedbyrn` | BYRN | `BYRN` | Current |
| `hj_bedd4rn` | D4RN | `D4RN` | Current |
| `hj_bedd5rn` | D5RN | `D5RN` | Current |
| `hj_bedd6rn` | D6RN | `D6RN` | Current |
| `hj_bedd7rn` | D7RN | `D7RN` | Current |
| `hj_bede3rm` | E3RM | `E3RM` | Current |
| `hj_bedfarm` | FARM | `FARM` | Current |
| `hj_bedhzrm` | HZRM | `HZRM` | Current |
| `hj_bedjgrm` | JGRM | `JGRM` | Current |
| `hj_bedjhrm` | JHRM | `JHRM` | Current |
| `hj_bedjjrm` | JJRM | `JJRM` | Current |
| `hj_bedkzrm` | KZRM | `KZRM` | Current |
| `hj_bedl2rm` | L2RM | `L2RM` | Current |
| `hj_bedrern` | RERN | `RERN` | Current |
| `hj_bedtyrn` | TYRN | `TYRN` | Current |
| `hj_bedtzrn` | TZRN | `TZRN` | Current |
| `hj_beduurn` | UURN | `UURN` | Current |
| `hj_bedvjrm` | VJRM | `VJRM` | Current |
| `likomioabm10` | ABM10 | `UTRM` | Conditional |
| `motionnxca200` | Series 1 | `GURN` | Conditional |
| `motionnxca300` | Series 2 | `GVRN` | Conditional |
| `motion_opus` | Series 3 | `GWRN` | Conditional |
| `muuegmabf03` | ABF03 | `BNRN` | Conditional |
| `muuegmabf07` | ABF07 | `DNRN` | Conditional |
| `muuegmnupg400` | NUPG400 | `BVRN` | Conditional |
| `velocityvip3` | VIP 3.0 | `` | Conditional |
| `velocityvip3sh` | VIP 3.0-SH | `` | Conditional |

- Choose the explicit app and product profile; configure two-address sides separately.
- Bluetooth scan candidates contain case-sensitive `QRRM`, `COOL`, `MPE_`, `209A` or `ZRA1`.
- HA's indexed name hints match those prefixes. Service/manual detection still accepts the keywords anywhere in a name.
- Names with an earlier prefix and no eligible advertised service use manual device selection. HA rejects leading-wildcard manifest matchers.
- E0FF uses name hints or manual selection because non-bed devices share it; all six listed transports work after explicit selection.
- HA provides discovery and an explicit device/product picker. Names are scan hints, not capability evidence.
- Phone text/QR input searches the current 19 remote codes; persisted display keys use exact case-sensitive first-match selection.
- HA stores an explicit profile per physical device, so ambiguous remote codes cannot change its layout.
- The two later FlexxLink objects are shadowed by the first RFRN display-key match and are not independent selectable profiles. `None` is unused as a control profile.
- No layout or feature is inferred from a generic Richmat remote table.

Write selection requires `write`. A selected `write-without-response` property
uses writes without response; otherwise writes use response. Selection retains
the first eligible write and first notify, while the last matched service decides
the generic packet mode. HA/Bleak handles MTU negotiation without an arbitrary override.

#### Controls

Covers represent actual selected up/down pairs. A lone combined-up action remains
a button, without inventing combined-down. Named buttons retain each product's
preset, save, massage, light, sync and sofa controls. All eight independent
MusicPage actions are available, including next/previous, even when the
profile has no music tab. Music packets always use left 0, as configured.

The pulse count bounds a normal HA action. The card uses a bounded held action;
its release button cancels refresh and runs that action's own cleanup. Motors,
normal reset, bed light and massage send their configured STOP where applicable.
Presets and sofa reset end refresh without an extra STOP. Sofa lamp and music
send once without STOP. BJRN preset programming waits three seconds; other
programming sends its long code once. Explicit Stop remains available separately.
Native cover Stop uses the selected side's shared Stop action, so card ownership
is cleared across that side's motor controls. Cross-axis firmware effects remain
unverified.
The **HJBed layout** local select chooses Normal or the conditionally named Motion
layout; Motion reset is a short action and its mode query has a narrower gate.

Short controls with a release callback send once on down, wait for release, then
perform cleanup; holding them does not turn them into repeated commands. Native
single-address paired side controls are offered only by the four coupled profiles.

The `hold_control` action accepts a listed `hjbed_*` control and a finite duration
up to 60 seconds. Sub-100 ms sustained actions send nothing. Save and recall are
separate actions, so holding recall never overwrites a memory.
Finite pulse actions share a deadline allowing one 100 ms pacing slot per
selected side after the final nominal tick. Explicit held durations keep their
requested end. Card release works for standalone,
single-address side controls and two-address pairs.

Values below come from the shipped `beds/hjbed.py` controller and its imported
catalog/packet builders. Detail IDs distinguish product-specific variants. Each
product exposes only its selected controls. The full profile bindings are in the
[discovery ledger](../apk-analysis/dispositions/row121-hjbed.json). Exit limit
and the clock, light and music menu probes use [function selectors](#function-selectors);
in single-code mode they send `00` and `01`.

<!-- generated:hjbed-commands -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

##### Motor Control

| Command (detail) | Single code | Framed left | Framed right | Gesture / release |
|---|---|---|---|---|
| Foot Box Down (`975861`) | `25` | `6E 01 00 25 94` | `6E 01 01 25 95` | Refresh 100 ms; STOP |
| Foot Box Up (`9758e1`) | `24` | `6E 01 00 24 93` | `6E 01 01 24 94` | Refresh 100 ms; STOP |
| Foot Down (`9740e1`) | `27` | `6E 01 00 27 96` | `6E 01 01 27 97` | Refresh 100 ms; STOP |
| Foot Up (`974161`) | `26` | `6E 01 00 26 95` | `6E 01 01 26 96` | Refresh 100 ms; STOP |
| Head And Foot Down (`9743e1`) | `2A` | `6E 01 00 2A 99` | `6E 01 01 2A 9A` | Refresh 100 ms; STOP |
| Head And Foot Up (`974461`) | `29` | `6E 01 00 29 98` | `6E 01 01 29 99` | Refresh 100 ms; STOP |
| Head Down (`9741e1`) | `25` | `6E 01 00 25 94` | `6E 01 01 25 95` | Refresh 100 ms; STOP |
| Head Up (`974261`) | `24` | `6E 01 00 24 93` | `6E 01 01 24 94` | Refresh 100 ms; STOP |
| Lumbar Down (`973fe1`) | `40` | `6E 01 00 40 AF` | `6E 01 01 40 B0` | Refresh 100 ms; STOP |
| Lumbar Down (`974be1`) | `42` | `6E 01 00 42 B1` | `6E 01 01 42 B2` | Refresh 100 ms; STOP |
| Lumbar Up (`974061`) | `3F` | `6E 01 00 3F AE` | `6E 01 01 3F AF` | Refresh 100 ms; STOP |
| Lumbar Up (`974c61`) | `41` | `6E 01 00 41 B0` | `6E 01 01 41 B1` | Refresh 100 ms; STOP |
| Pillow Down (`973ee1`) | `42` | `6E 01 00 42 B1` | `6E 01 01 42 B2` | Refresh 100 ms; STOP |
| Pillow Down (`974a61`) | `40` | `6E 01 00 40 AF` | `6E 01 01 40 B0` | Refresh 100 ms; STOP |
| Pillow Up (`973f61`) | `41` | `6E 01 00 41 B0` | `6E 01 01 41 B1` | Refresh 100 ms; STOP |
| Pillow Up (`974ae1`) | `3F` | `6E 01 00 3F AE` | `6E 01 01 3F AF` | Refresh 100 ms; STOP |
| Tilt Down (`974fe1`) | `5C` | `6E 01 00 5C CB` | `6E 01 01 5C CC` | Refresh 100 ms; STOP |
| Tilt Up (`975061`) | `5B` | `6E 01 00 5B CA` | `6E 01 01 5B CB` | Refresh 100 ms; STOP |
| Backward (`975461`) | `5C` | `6E 01 00 5C CB` | `6E 01 01 5C CC` | Refresh 100 ms; STOP |
| Forword (`9754e1`) | `5B` | `6E 01 00 5B CA` | `6E 01 01 5B CB` | Refresh 100 ms; STOP |
| Head Down (`975561`) | `25` | `6E 01 00 25 94` | `6E 01 01 25 95` | Refresh 100 ms; STOP |
| Head Up (`9755e1`) | `24` | `6E 01 00 24 93` | `6E 01 01 24 94` | Refresh 100 ms; STOP |
| Lumbar Down (`975661`) | `40` | `6E 01 00 40 AF` | `6E 01 01 40 B0` | Refresh 100 ms; STOP |
| Lumbar Up (`9756e1`) | `3F` | `6E 01 00 3F AE` | `6E 01 01 3F AF` | Refresh 100 ms; STOP |
| Pillow Down (`975761`) | `42` | `6E 01 00 42 B1` | `6E 01 01 42 B2` | Refresh 100 ms; STOP |
| Pillow Up (`9757e1`) | `41` | `6E 01 00 41 B0` | `6E 01 01 41 B1` | Refresh 100 ms; STOP |

##### Presets

| Command (detail) | Single code | Framed left | Framed right | Gesture / release |
|---|---|---|---|---|
| Anti Snoring (`9738e1`) | `46` | `6E 01 00 46 B5` | `6E 01 01 46 B6` | Once; no extra STOP |
| Anti Snoring (`975961`) | `46` | `6E 01 00 46 B5` | `6E 01 01 46 B6` | Refresh 100 ms; no extra STOP |
| Coaxing Sleep Mode (`9744e1`) | `86` | `6E 01 00 86 F5` | `6E 01 01 86 F6` | Once; no extra STOP |
| Lounge Position (`973961`) | `59` | `6E 01 00 59 C8` | `6E 01 01 59 C9` | Once; no extra STOP |
| Memory Position1 (`973861`) | `2E` | `6E 01 00 2E 9D` | `6E 01 01 2E 9E` | Once; no extra STOP |
| Memory Position1 (`974e61`) | `2E` | `6E 01 00 2E 9D` | `6E 01 01 2E 9E` | Refresh 100 ms; no extra STOP |
| Memory Position2 (`9737e1`) | `2F` | `6E 01 00 2F 9E` | `6E 01 01 2F 9F` | Once; no extra STOP |
| Memory Position2 (`974de1`) | `2F` | `6E 01 00 2F 9E` | `6E 01 01 2F 9F` | Refresh 100 ms; no extra STOP |
| Memory Position3 (`9751e1`) | `30` | `6E 01 00 30 9F` | `6E 01 01 30 A0` | Refresh 100 ms; no extra STOP |
| Memory Position4 (`975261`) | `B2` | `6E 01 00 B2 21` | `6E 01 01 B2 22` | Refresh 100 ms; no extra STOP |
| T V Position (`973a61`) | `58` | `6E 01 00 58 C7` | `6E 01 01 58 C8` | Once; no extra STOP |
| T V Position (`974d61`) | `58` | `6E 01 00 58 C7` | `6E 01 01 58 C8` | Refresh 100 ms; no extra STOP |
| T V Position (`975161`) | `58` | `6E 01 00 58 C7` | `6E 01 01 58 C8` | Refresh 100 ms; no extra STOP |
| Zero Gravity (`9739e1`) | `45` | `6E 01 00 45 B4` | `6E 01 01 45 B5` | Once; no extra STOP |
| Zero Gravity (`974ce1`) | `45` | `6E 01 00 45 B4` | `6E 01 01 45 B5` | Refresh 100 ms; no extra STOP |
| Zero Gravity (`9750e1`) | `45` | `6E 01 00 45 B4` | `6E 01 01 45 B5` | Refresh 100 ms; no extra STOP |

##### Massage

| Command (detail) | Single code | Framed left | Framed right | Gesture / release |
|---|---|---|---|---|
| Massage10 Minute Timer (`973be1`) | `5F` | `6E 01 00 5F CE` | `6E 01 01 5F CF` | Once; STOP |
| Massage20 Minute Timer (`973b61`) | `63` | `6E 01 00 63 D2` | `6E 01 01 63 D3` | Once; STOP |
| Massage30 Minute Timer (`973ae1`) | `61` | `6E 01 00 61 D0` | `6E 01 01 61 D1` | Once; STOP |
| Massage Foot Instensity Strengthen (`973d61`) | `4E` | `6E 01 00 4E BD` | `6E 01 01 4E BE` | Once; STOP |
| Massage Head Instensity Strengthen (`973de1`) | `4C` | `6E 01 00 4C BB` | `6E 01 01 4C BC` | Once; STOP |
| Massage Instensity Strengthen (`974361`) | `34` | `6E 01 00 34 A3` | `6E 01 01 34 A4` | Once; STOP |
| Massage Mode All Off (`973c61`) | `5E` | `6E 01 00 5E CD` | `6E 01 01 5E CE` | Once; STOP |
| Massage Mode Change (`973ce1`) | `48` | `6E 01 00 48 B7` | `6E 01 01 48 B8` | Once; STOP |
| Massage Switch (`9742e1`) | `6F` | `6E 01 00 6F DE` | `6E 01 01 6F DF` | Once; STOP |

##### Lights

| Command (detail) | Single code | Framed left | Framed right | Gesture / release |
|---|---|---|---|---|
| Bed Light (`974961`) | `3C` | `6E 01 00 3C AB` | `6E 01 01 3C AC` | Once; STOP |
| Bed Light Close (`9759e1`) | `75` | `6E 01 00 75 E4` | `6E 01 01 75 E5` | Once; no extra STOP |
| Light Board (`9749e1`) | `50` | `6E 01 00 50 BF` | `6E 01 01 50 C0` | Once; STOP |
| Light (`975361`) | `3C` | `6E 01 00 3C AB` | `6E 01 01 3C AC` | Once; no extra STOP |

##### Music

| Command (detail) | Single code | Framed left | Framed right | Gesture / release |
|---|---|---|---|---|
| Music Blue Tooth Switch (`9748e1`) | `D8` | `6E 01 00 D8 47` | `6E 01 00 D8 47` | Once; no extra STOP |
| Music Next Song (`974661`) | `D3` | `6E 01 00 D3 42` | `6E 01 00 D3 42` | Once; no extra STOP |
| Music Pause Play (`9745e1`) | `D7` | `6E 01 00 D7 46` | `6E 01 00 D7 46` | Once; no extra STOP |
| Music Previous Song (`9746e1`) | `D2` | `6E 01 00 D2 41` | `6E 01 00 D2 41` | Once; no extra STOP |
| Music Shake Mode (`974861`) | `D6` | `6E 01 00 D6 45` | `6E 01 00 D6 45` | Once; no extra STOP |
| Music Switch Sound Track (`975ae1`) | `C4` | `6E 01 00 C4 33` | `6E 01 00 C4 33` | Once; no extra STOP |
| Music Volumu Down (`974761`) | `D5` | `6E 01 00 D5 44` | `6E 01 00 D5 44` | Once; no extra STOP |
| Music Volumu Up (`9747e1`) | `D4` | `6E 01 00 D4 43` | `6E 01 00 D4 43` | Once; no extra STOP |

##### Reset, stop and sync

| Command (detail) | Single code | Framed left | Framed right | Gesture / release |
|---|---|---|---|---|
| Exit Limit (`973761`) | `00` | `6E 02 01 00 71` | `6E 02 01 00 71` | Once; no extra STOP |
| Motor Reset (`973e61`) | `31` | `6E 01 00 31 A0` | `6E 01 01 31 A1` | Once; STOP; Motion once |
| Motor Reset (`974f61`) | `31` | `6E 01 00 31 A0` | `6E 01 01 31 A1` | Refresh 100 ms; STOP; Motion once |
| Stop (`975a61`) | `6E` | `6E 01 00 6E DD` | `6E 01 01 6E DE` | Once; no extra STOP |
| Sync Off (`9752e1`) | `BD` | `6E 01 00 BD 2C` | `6E 01 01 BD 2D` | Once; no extra STOP |
| Sync On (`974b61`) | `BC` | `6E 01 00 BC 2B` | `6E 01 01 BC 2C` | Once; no extra STOP |
| Sit Position (`9753e1`) | `E5` | `6E 01 00 E5 54` | `6E 01 01 E5 55` | Refresh 100 ms; no extra STOP |

##### Memory

Save is available only for selected preset details with a long code. BJRN waits
three seconds; other product saves send once immediately. Recall and save remain
separate actions.

| Save command (detail) | Single code | Framed left | Framed right |
|---|---|---|---|
| Anti Snoring (`9738e1`) | `69` | `6E 01 00 69 D8` | `6E 01 01 69 D9` |
| Anti Snoring (`975961`) | `69` | `6E 01 00 69 D8` | `6E 01 01 69 D9` |
| Coaxing Sleep Mode (`9744e1`) | `89` | `6E 01 00 89 F8` | `6E 01 01 89 F9` |
| Lounge Position (`973961`) | `65` | `6E 01 00 65 D4` | `6E 01 01 65 D5` |
| Memory Position1 (`973861`) | `2B` | `6E 01 00 2B 9A` | `6E 01 01 2B 9B` |
| Memory Position1 (`974e61`) | `2B` | `6E 01 00 2B 9A` | `6E 01 01 2B 9B` |
| Memory Position2 (`9737e1`) | `2C` | `6E 01 00 2C 9B` | `6E 01 01 2C 9C` |
| Memory Position2 (`974de1`) | `2C` | `6E 01 00 2C 9B` | `6E 01 01 2C 9C` |
| Memory Position3 (`9751e1`) | `2D` | `6E 01 00 2D 9C` | `6E 01 01 2D 9D` |
| Memory Position4 (`975261`) | `B3` | `6E 01 00 B3 22` | `6E 01 01 B3 23` |
| T V Position (`973a61`) | `64` | `6E 01 00 64 D3` | `6E 01 01 64 D4` |
| T V Position (`974d61`) | `64` | `6E 01 00 64 D3` | `6E 01 01 64 D4` |
| T V Position (`975161`) | `64` | `6E 01 00 64 D3` | `6E 01 01 64 D4` |
| Zero Gravity (`9739e1`) | `66` | `6E 01 00 66 D5` | `6E 01 01 66 D6` |
| Zero Gravity (`974ce1`) | `66` | `6E 01 00 66 D5` | `6E 01 01 66 D6` |
| Zero Gravity (`9750e1`) | `66` | `6E 01 00 66 D5` | `6E 01 01 66 D6` |
<!-- /generated -->

#### Timing

See [Catalog app timing](#catalog-app-timing).

- Sustained controls start at the first refresh tick and use monotonic tick deadlines.
- Writes are serialized with the minimum spacing; write latency does not accumulate in the refresh interval.
- Both-side frames share one bounded hold window. Stale refreshes are dropped; an in-flight write and required cleanup may finish after the window.
- Every attempted side retains its own release, including when another side's release fails.
- Startup follows [HJBed startup](#hjbed-startup).

##### HJBed startup

<!-- generated:hjbed-startup -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Step | When | Framed | Single-code |
|---|---|---|---|
| Exit limit | first | `6E 02 01 00 71` | `00` |
| Time sync | next, two frames | extended `08 02 01` then `08 03 01` | same |
| Control mode query | blue, green and orange; green and orange only in the Motion layout | `6E 08 20 0B 02 00 00 A3` | same |
| Clock menu probe | +300 ms | `6E 08 01 01 78` | `01` |
| Light menu probe | +600 ms | `6E 0A 00 01 79` | `01` |
| Music menu probe | +900 ms | `6E 15 01 01 85` | `01` |

Probe offsets count from the start of the menu request, after the exit frame.
<!-- /generated -->

#### Notifications

**HJBed status** exposes the last event, structured `hjbed_events`, complete
`hjbed_alarms`, `hjbed_saved_alarm`, host-only `hjbed_available_alarm_slots` and
parser rejection information. Bed
observations include motor travel/angles/height, version/control modes, massage,
white/RGB lighting, music, snore/off-bed/name/locks, coaxing, aroma, heating, fan,
blanket and detection data. These passive readings do not enable an outbound
command. Raw values are retained where physical units or motor mappings are not
proven. Position seeking is not inferred from those observations.

The six service/write pairs are in `beds/hjbed.py:GATT`. The first
eligible write and first notify characteristic are retained in returned order;
the last matched service decides single-code versus framed generic commands.
Write selection requires `write`, notification selection requires `notify`.
The response policy follows that characteristic's write-without-response flag.
HA/Bleak owns connection setup, adapters, proxies and MTU negotiation. There is
no app-owned PIN, challenge, authentication or bonding exchange to reproduce.

Generic packets are one command byte on the selected Nordic mode, otherwise
`6e 01 side code sum8`. Exit and three menu probes have exact separate prefixes.
Variable outbound frames are `6e length 20 ... sum8`; inbound extended frames
place length after `20` or `21`. Every final integer is masked to eight bits.
Clock synchronization uses timestamp/calendar from one snapshot and timezone
from a second snapshot, with whole-hour offset truncation.

Complete inbound frames are destructively split before dispatch. Earlier emitted
state survives a later parser/callback failure; failing and later local frames
are not replayed. Retained incomplete bytes receive a 500 ms timer only after
successful dispatch. Common frames retain their individual checksum and
chunk behavior. Zero-length nonprogress input is rejected safely.

#### Services

Variable builders below always retain their full frames, including in single-code mode.
These are exact examples from the shipped builders; fields vary with the requested values.

| Operation and example input | Exact GATT write(s) |
| --- | --- |
| Single alarm: 1440 minutes, code `45` | `6e05a00013`; `6e060545be` |
| Cancel single alarm | `6e05000073`; `6e06000074` |
| Light timeout: 600 seconds | `6e0b0258d3` |
| Light always on: 0 seconds | `6e0bffff77` |
| RGB: 11, 22, 33; one combined write | `6e0cff0b846e0d1621b2` |
| Repeat alarm: slot1, kind0, 07:30, code45, Monday enabled | `6e0d200501010100071e45818e` |
| Delete repeat slot1 | `6e0820050201019f` |
| Query repeat list | `6e0820050100009c` |
| Clock sync: 2026-11-03 12:00:00 +01:00 | `6e0c200802016ae9beb00167`; `6e0d20080301380b030c0000f9` |
| Query control mode | `6e08200b020000a3` |
| Split-head mode0 | `6e09200b02010000a5` |
| Standard mode2 | `6e09200b02010002a7` |


Use `adjustable_bed.hjbed` with `device_id` and `operation`. All selected physical
targets are validated before any configuration write. Generic `side` routing
remains supported; direct variable builders configure the current physical
receiver, while generic motion frames select left 0 or right 1. Music stays left.

| Operation | Fields | Eligibility |
| --- | --- | --- |
| `single` | `time`, `action` | Single-alarm product flag and clock acknowledgement |
| `cancel_single` | none | Same single-alarm gate |
| `repeat` | `time`, `action`, `alarm_id` unless a slot is known free, `weekdays`, `enabled` | Repeat-alarm flag and clock acknowledgement |
| `query`, `delete` | `alarm_id` for delete | Repeat-alarm gate |
| `toggle` | observed `alarm_id`, `enabled` | Repeat-alarm gate |
| `sync` | none | Clock synchronization used by the app's product menu |
| `light_timeout` | `seconds` | Light-page flag and light acknowledgement |
| `light_color` | `rgb_color` | Same light-page gate |
| `mode` | `mode: split_head` or `standard` | Normal layout, blue/green/orange only |

Alarm time uses minute precision. Empty weekdays means once; Monday is bit 7,
Sunday bit 1, enabled bit 0. Use an explicit `alarm_id` from 1 through 7 when
occupancy is unknown. Automatic allocation chooses the smallest slot freed by a
delete in the current connection, provided no later reply reports it occupied.
Availability is rechecked after pacing; a late occupied-slot reply rejects the
automatic create. The slot is reserved before writing, including when write success is uncertain.
Query, reconnect and disconnect clear this knowledge. A full table is rejected rather than sending
an invalid slot. Imported custom alarm data is retained when toggling a record.
Single-alarm preferences are persisted only after the bed's success reply and
removed on cancellation success. The saved selected date/time, function identity,
label and nullable repeat metadata remain available after restart. An unsolicited
add-success event cannot replace that metadata with a guessed selection. Repeat-list observations preserve full bean
equality; an escalation replaces only the first matching number. Query clears the
observed list before replies; deletion removes the first selected full bean.
Single-alarm countdowns subtract epoch seconds across DST changes and retain the
86400-second fallback when the target is not later.

Light timeout is 0 to 900 seconds (0 means always on), except blue, which offers
1800 to 28800 seconds. Color sends one 10-byte GATT write containing both
checksummed RGB pieces. No brightness or extra lighting command is invented.

The current 19 profiles have all advanced music/alarm/repeat/light-page flags
false. A feature reply cannot override that static gate. Simple lamp buttons,
selected massage lists, and independently named music routes remain independent.
The full per-product action and flag inventory is in the
[durable disposition ledger](../apk-analysis/dispositions/row121-hjbed.json).
Alarm action keys are snake-case names such as `zero_gravity`, `anti_snoring`,
`memory_position1`, `tv_position`, or `lounge_position`, and must belong to the
selected product's alarm list.

#### Evidence

HJBed sends only frames frozen from its accepted row121 evidence (artifact set
`bd3a5e96393fb32be9059fbb9a0eae5639deb7f0d761b4a27b3b382433c4d291`). Physical
effects, ATT behavior and firmware acceptance are for real users to validate after
a beta or release. See the [disposition summary](../apk-analysis/dispositions/row121-hjbed.md)
and [complete ledger](../apk-analysis/dispositions/row121-hjbed.json).

## Notes

### Profile ids and aliases

`richmat_best_mattress:model_bfrm` and `richmat_blvd_home:model_bfrm` send the
same bytes but keep separate [profile id](../design/profile-id.md#aliases)s: they are one model in two apps,
each its own bed type with its own setup label.

### Analysis provenance

- RMControl: [implementation ledger](../apk-analysis/row018-rmcontrol-implementation.md)
  and [specialized evidence record](../apk-analysis/row018-rmcontrol-specialized-evidence.md).
- Richmat MH: [row055 disposition ledger](../apk-analysis/dispositions/row055-richmat-cluster.md).
- HJBed: [row121 disposition summary](../apk-analysis/dispositions/row121-hjbed.md).
- The Richmat remotes, BedTech and L&P MlRM routes have no accepted report of
  their own; their frames are the pre-v5 controllers'.
