# Keeson

**Status:** ✅ Tested (Base, KSBT and Ergomotion routes; the app profiles are APK-verified with hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), [alanbixby](https://github.com/alanbixby), [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt) and [MangoScango](https://github.com/MangoScango)

One wire codec (the K1 `E5/E6 FE 16` frame and the other carriers of the Keeson
32-bit key word) serves every `keeson` protocol variant, the `ergomotion`,
`serta` and `okin_ffe` bed types and the audited Keeson, Okin and ORE app
profiles. This guide covers the codec first, then one section per profile. See
[Protocol codecs and app profiles](../design/protocol-codecs.md) for the
architecture.

## Known Models

Brands using Keeson/Ergomotion actuators:

- Serta, including Serta Motion Perfect III and other BLE-enabled, non-cloud Serta bases
- Ergomotion
- Ergomotion Rio 5.0 / Denver Mattress Hibernation Platinum (advertises as `KSBT03C...`; 3 motors: back, legs, lumbar — no head tilt)
- Ergomotion Rio 6.0 (advertises as `KSBT04...`, works with KSBT protocol)
- Tempur Zero G / Tempur Curve
- Beautyrest Black
- ENSO
- Dawn House
- Restonic
- Omazz Adjusto
- King Koil
- SomosBeds
- Purple adjustable bases
- GhostBed
- Member's Mark (Sam's Club) adjustable beds
- GlideAway ComfortBase Odessa with lift kit (BaseI4/I5 massage controls confirmed)
- South Bay International MMKD
- Sealy Ease
- Some Costco beds
- Bases controlled by MaxCoil Una, Dynasty Bases, Bedsense Bases, Avanti Bases
  and AMERICANSTAR (app screens 2M, 3M and 4M, chosen by hand in the app)

**Beautyrest BLACK app boundary:** The accepted Android app
`com.keeson.beautyrestblack` 1.2.1 (18) uses TCP and network services, with no
reachable Bluetooth bed-control transport in that exact artifact. BLE hardware
using independently identified Keeson protocols remains supported. See the
[complete app disposition](../apk-analysis/dispositions/row044-beautyrest-black.md).

**DewertOkin/ORE brands** also using FFE5 protocol (31 apps):
- Simon Li, Cherish Smart, Minghua, Heal Every Night (Simon Li, Heal Every Night and OKIN-Seating have [explicit profiles](#simon-li-heal-every-night-and-okin-seating-profiles))
- ORE: Dynasty, LevaSleep, American Star, Avanti, Comfort Furniture, Hestia Motion, Maxcoil, Power's Bedding, SFM, Ultramatic, Better Living, Koizumi
- See [DewertOkin](okin-nframe.md#dewertokin) for full list

## Apps

| Analyzed | App | Package ID | Profile |
|----------|-----|------------|---------|
| ✅ | [Ergomotion 4.0](https://play.google.com/store/apps/details?id=com.sfd.hump) | `com.sfd.hump` | [KSBT](#ksbt-family) |
| ✅ | [1500 Tilt Base Remote](https://play.google.com/store/apps/details?id=com.sfd.rondure_hump) | `com.sfd.rondure_hump` | [KSBT](#ksbt-family) |
| ✅ | [Q-Plus Adjustable Remote](https://play.google.com/store/apps/details?id=com.sbi.costco) | `com.sbi.costco` | [KSBT](#ksbt-family) |
| ✅ | [Ergomotion](https://play.google.com/store/apps/details?id=com.sfd.ergomotion) | `com.sfd.ergomotion` | [Ergomotion](#ergomotion) |
| ✅ | [Tempur Zero G Bed Base](https://play.google.com/store/apps/details?id=com.sfd.row) | `com.sfd.row` | [Ergomotion](#ergomotion) |
| ✅ | Tempur Curve | `com.ore.tempur` | [Base](#base-basei4i5) |
| ✅ | [Member's Mark Base Remote](https://play.google.com/store/apps/details?id=com.sfd.mm) | `com.sfd.mm` | [Base](#base-basei4i5) |
| ✅ | [Serta MP Remote](https://play.google.com/store/apps/details?id=com.ore.serta330) | `com.ore.serta330` | [Serta](#serta) |
| ✅ | [Sleep Harmony](https://play.google.com/store/apps/details?id=com.keeson.ssbaudio) | `com.keeson.ssbaudio` | [Sleep Harmony](#sleep-harmony-variant) |
| ✅ | Ergomotion Sync | `cn.com.mancini` | [KSBT03C](#ksbt-family) |
| ✅ | Linx | `com.keeson.connectedbed` | [JSON/A00A](#jsona00a-variant-juna-linx-ergo-health) |
| ✅ | Juna Sleep | `com.keeson.junasleep` | [JSON/A00A](#jsona00a-variant-juna-linx-ergo-health) |
| ✅ | [Purple Smart Base](https://play.google.com/store/apps/details?id=com.keeson.purpleBase) | `com.keeson.purpleBase` | [Purple](#purple-variant) |
| ✅ | [Adjustable Lite](https://play.google.com/store/apps/details?id=com.keeson.adjustablelite) | `com.keeson.adjustablelite` | [Adjustable Lite](#adjustable-lite-profile) |
| ✅ | Restonic BT Remote | `com.keeson.restonicBT` | [Restonic BT](#restonic-bt-profiles) |
| ✅ | INNOVA | `com.ore.sfm` | [INNOVA](#innova-profile) |
| ✅ | Simon Li, Heal Every Night, OKIN-Seating | `com.okin.simon`, `com.okin.healeverynight`, `com.okin.minghua.R` | [Okin apps](#simon-li-heal-every-night-and-okin-seating-profiles) |
| ✅ | [MaxCoil Una](https://play.google.com/store/apps/details?id=com.ore.maxcoil) 1.1.0 (5) | `com.ore.maxcoil` | [ORE comfort-bed](#ore-comfort-bed-profiles) |
| ✅ | [Dynasty Bases](https://play.google.com/store/apps/details?id=com.ore.Dynasty) 1.0.2 (3) | `com.ore.Dynasty` | [ORE comfort-bed](#ore-comfort-bed-profiles) |
| ✅ | [Bedsense Bases](https://play.google.com/store/apps/details?id=com.ore.sfmc2bedsence) 1.1 (3) | `com.ore.sfmc2bedsence` | [ORE comfort-bed](#ore-comfort-bed-profiles) |
| ✅ | [Avanti Bases](https://play.google.com/store/apps/details?id=com.ore.AvantiBases) 1.0.5 (7) | `com.ore.AvantiBases` | [ORE comfort-bed](#ore-comfort-bed-profiles) |
| ✅ | [AMERICANSTAR](https://play.google.com/store/apps/details?id=com.ore.americanstar) 1.0 (1), hardware unverified | `com.ore.americanstar` | [ORE comfort-bed](#ore-comfort-bed-profiles) |
| Separate processor | Tempur Sleeptracker-AI ([framed-JSON processor guide](sleeptracker.md)) | `com.fullpower.applications.horizon` | none |

The Serta MP Remote and Ergomotion apps also have their own calibrated app
profiles ([Serta MP Remote](serta-mp-remote.md), [Ergomotion app](ergomotion.md));
the profiles above are the uncalibrated Keeson routes.

## Features

| Feature | BaseI4/I5 | JSON/A00A | KSBT | Ergomotion | Okin | Serta | Sino | Purple (Premium) | Purple (Premium Plus) |
|---------|-----------|------------|------|------------|------|-------|------|------------------|-----------------------|
| Motor Control | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Position Feedback | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Memory Presets | ⚠️ 4 exposed (slot 3 app-confirmed) | ✅ (remote-dependent 0x2000/0x4000/0x8000/0x10000) | ✅ (slots 1-3: Read/TV/M) | ⚠️ 4 exposed (verification needed) | ✅ | ✅ | ✅ | ✅ (2 slots) | ✅ (3 slots) |
| TV Preset | ❌ | ✅ (remote-dependent) | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Anti-Snore Preset | ❌ | ✅ (remote-dependent) | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Lounge Preset | ❌ | ✅ (remote-dependent) | ✅ | ✅ | ❌ | ❌ | ❌ | ✅ | ❌ |
| Massage | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Safety Lights | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Zero-G | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

The Sino column's anti-snore is the BetterLiving table. The app profiles list
their controls in their sections.

## Choosing a profile

Choose **Keeson** and the protocol variant that matches the app, or a bed type
alias (`ergomotion`, `serta`, `okin_ffe`). Detection suggests the Base,
Ergomotion, Serta, OKIN FFE, JSON/A00A, KSBT and KSBT03CR routes; every app
profile is an explicit choice. The tables below are generated from the profile
data.

<!-- generated:keeson-profiles -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

### Profile summary

| Profile | Route | Frame | Transport | Lights | Massage |
|---|---|---|---|---|---|
| Base (BaseI4/I5) | `keeson` `base` (Auto default) | K1 `E5`, little-endian | BASE | toggle | step |
| Ergomotion | `keeson` `ergomotion`; bed type `ergomotion` | K1 `E5`, little-endian | BASE | toggle | step |
| Serta | `keeson` `serta`; bed type `serta` | K1 `E5`, little-endian | BASE | toggle | step |
| OKIN FFE | `keeson` `okin`; bed type `okin_ffe` | K1 `E6`, little-endian | BASE | toggle | step |
| BetterLiving CB1322 | `keeson` `okin`: Auto: as BetterLiving, with a `BLE-4.0 Module` or `DewertOKIN` manufacturer | K1 `E6`, little-endian | BASE | toggle | step |
| Sino | `keeson` `sino` | K1 `E5`, big-endian | BASE | discrete | absolute |
| BetterLiving | `keeson` `sino`: Auto: both fallback services, or an `OKIN-BLE` name with one | K1 `E5`, big-endian | BASE | discrete | absolute |
| JSON/A00A | `keeson` `json` | JSON | JSON | toggle | step |
| KSBT | `keeson` `ksbt` | P2 6-byte | KSBT | toggle | step |
| KSBT03C | `keeson` `ksbt`: name starts with `KSBT03C`, not `KSBT03CR` | P2 6-byte | KSBT | toggle | step |
| KSBT03CR | `keeson` `ksbt_cr` | P2 7-byte (`05`) | KSBT | toggle | step |
| KSBT04C | `keeson` `ksbt04c` | P2 7-byte, checksum end | KSBT | none | step |
| Sleep Harmony (KSBT04C) | `keeson` `sleep_harmony` | P2 7-byte, checksum end | KSBT | none | step |
| Sleep Harmony (base-i5) | `keeson` `sleep_harmony`: name starts with `base-i5.` | K1 `E6`, little-endian, side `00` | BASE | none | step |
| Purple Premium | `keeson` `purple` | K1 `E5`, little-endian | BASE | toggle | step |
| Purple Premium Plus | `keeson` `purple`: name starts with `KSBT04C`, or the Nordic UART service exists | P2 7-byte, `00` end | KSBT | toggle | step |
| Adjustable Lite (KSBT01C) | `keeson` `adjustable_lite` | P2 6-byte | KSBT (fixed) | toggle | none |
| Adjustable Lite (KSBT03C) | `keeson` `adjustable_lite`: name contains `KSBT03C` (case-sensitive) | P2 6-byte | KSBT (fixed) | toggle | zone_steps |
| Restonic BT remote A | `keeson` `restonic_a` | K1 `E5`, little-endian | BASE (fixed) | none | none |
| Restonic BT remote B | `keeson` `restonic_b` | K1 `E5`, little-endian | BASE (fixed) | toggle | none |
| INNOVA | `keeson` `innova` | K1 `E5`, little-endian | BASE (fixed) | app controller | app controller |
| Simon Li | `keeson` `simon_li` | K1 `E5`, big-endian | BASE (fixed) | app controller | app controller |
| OKIN-Seating | `keeson` `okin_seating` | K1 `E5`, big-endian | BASE (fixed) | app controller | app controller |
| Heal Every Night | `keeson` `heal_every_night` | K1 `E5`, big-endian | BASE (fixed) | app controller | app controller |
| AMERICANSTAR | `keeson` `americanstar` | K1 `E5`, big-endian | BASE (fixed) | app controller | app controller |
| Avanti Bases | `keeson` `avanti_bases` | K1 `E5`, big-endian | BASE (fixed) | app controller | app controller |
| Bedsense Bases | `keeson` `bedsense_bases` | K1 `E5`, big-endian | BASE (fixed) | app controller | app controller |
| Dynasty Bases | `keeson` `dynasty_bases` | K1 `E5`, big-endian | BASE (fixed) | app controller | app controller |
| MaxCoil Una | `keeson` `maxcoil_una` | K1 `E5`, big-endian | BASE (fixed) | app controller | app controller |

### Hold and release timing

A hold writes its frame the given number of times while the stored cadence is the
Keeson default; a customized cadence wins. Release waits count from the previous
write. An explicit stop sends the release without its waits.

| Profile | Hold | Three motors | Release after a hold | Explicit stop | Released after one-shots | Wait before one-shots |
|---|---|---|---|---|---|---|
| Base (BaseI4/I5) | 3 × 400 ms | same | +0 ms `E5 FE 16 00 00 00 00 06` | `E5 FE 16 00 00 00 00 06` | no | none |
| Ergomotion | 10 × 100 ms | same | +0 ms `E5 FE 16 00 00 00 00 06` | `E5 FE 16 00 00 00 00 06` | no | none |
| Serta | 10 × 100 ms | same | +0 ms `E5 FE 16 00 00 00 00 06` | `E5 FE 16 00 00 00 00 06` | no | none |
| OKIN FFE | 10 × 100 ms | 5 × 200 ms | +0 ms `E6 FE 16 00 00 00 00 05` | `E6 FE 16 00 00 00 00 05` | no | none |
| BetterLiving CB1322 | 10 × 100 ms | 5 × 200 ms | +0 ms `E6 FE 16 00 00 00 00 05` | `E6 FE 16 00 00 00 00 05` | no | none |
| Sino | 10 × 100 ms | 5 × 200 ms | +0 ms `E5 FE 16 00 00 00 00 06` | `E5 FE 16 00 00 00 00 06` | no | none |
| BetterLiving | 10 × 100 ms | 5 × 200 ms | +0 ms `E5 FE 16 00 00 00 00 06` | `E5 FE 16 00 00 00 00 06` | no | none |
| JSON/A00A | 10 × 100 ms | same | +0 ms JSON key `00000000`, `ctrm` 0 | JSON key `00000000`, `ctrm` 0 | no | none |
| KSBT | 10 × 100 ms | same | +300 ms `00 B0`, +300 ms `00 B0`, +300 ms `00 B0` | none | no | none |
| KSBT03C | 4 × 300 ms | same | none | none | no | none |
| KSBT03CR | 4 × 300 ms | same | +0 ms `05 02 00 00 00 00 00` | `05 02 00 00 00 00 00` | no | none |
| KSBT04C | 4 × 300 ms | same | +0 ms `04 02 00 00 00 00 F9` | `04 02 00 00 00 00 F9` | no | none |
| Sleep Harmony (KSBT04C) | 4 × 300 ms | same | +200 ms `04 02 00 00 00 00 F9` | `04 02 00 00 00 00 F9` | yes | none |
| Sleep Harmony (base-i5) | 4 × 300 ms | same | +200 ms `E6 FE 16 00 00 00 00 00 05` | `E6 FE 16 00 00 00 00 00 05` | yes | none |
| Purple Premium | 10 × 100 ms | same | +0 ms `04 02 00 00 00 00 00` | `04 02 00 00 00 00 00` | yes | none |
| Purple Premium Plus | 10 × 100 ms | same | +0 ms `04 02 00 00 00 00 00` | `04 02 00 00 00 00 00` | yes | none |
| Adjustable Lite (KSBT01C) | 4 × 300 ms | same | none | none | no | none |
| Adjustable Lite (KSBT03C) | 4 × 300 ms | same | none | none | no | none |
| Restonic BT remote A | 10 × 100 ms | same | +100 ms `E5 FE 16 00 00 00 00 06` (STOP ends the wait) | `E5 FE 16 00 00 00 00 06` | yes | none |
| Restonic BT remote B | 10 × 100 ms | same | +100 ms `E5 FE 16 00 00 00 00 06` (STOP ends the wait) | `E5 FE 16 00 00 00 00 06` | yes | none |
| INNOVA | pulse count × 100 ms | same | +100 ms `E5 FE 16 00 00 00 00 06` (STOP ends the wait) | `E5 FE 16 00 00 00 00 06` | no | 100 ms |
| Simon Li | pulse count × 100 ms | same | +10 ms `E5 FE 16 00 00 00 00 06` (STOP ends the wait) | `E5 FE 16 00 00 00 00 06` | no | none |
| OKIN-Seating | pulse count × 100 ms | same | +10 ms `E5 FE 16 00 00 00 00 06` (STOP ends the wait) | `E5 FE 16 00 00 00 00 06` | no | none |
| Heal Every Night | pulse count × 100 ms | same | +100 ms `E5 FE 16 00 00 00 00 06` (STOP ends the wait) | `E5 FE 16 00 00 00 00 06` | no | none |
| AMERICANSTAR | pulse count × 100 ms | same | +100 ms `E5 FE 16 00 00 00 00 06` | `E5 FE 16 00 00 00 00 06` | no | 100 ms |
| Avanti Bases | pulse count × 100 ms | same | +100 ms `E5 FE 16 00 00 00 00 06` | `E5 FE 16 00 00 00 00 06` | no | 100 ms |
| Bedsense Bases | pulse count × 100 ms | same | +100 ms `E5 FE 16 00 00 00 00 06` | `E5 FE 16 00 00 00 00 06` | no | 100 ms |
| Dynasty Bases | pulse count × 100 ms | same | +100 ms `E5 FE 16 00 00 00 00 06` | `E5 FE 16 00 00 00 00 06` | no | 100 ms |
| MaxCoil Una | pulse count × 100 ms | same | +100 ms `E5 FE 16 00 00 00 00 06` | `E5 FE 16 00 00 00 00 06` | no | 100 ms |

### Presets and memory

Words, encoded in the profile's frame. AMERICANSTAR, Avanti Bases, Bedsense Bases,
Dynasty Bases, Heal Every Night, INNOVA, MaxCoil Una, OKIN-Seating, Simon Li keep
their key tables with their app controllers; see their sections.

| Profile | Flat | Zero G | Lounge | TV | Anti-snore | Memory recall | Memory save |
|---|---|---|---|---|---|---|---|
| Base (BaseI4/I5) | `0x08000000` | `0x00001000` | no | no | no | 1: `0x00002000`<br>2: `0x00004000`<br>3: `0x00008000`<br>4: `0x00010000` | none |
| Ergomotion | `0x08000000` | `0x00001000` | `0x00002000` | `0x00004000` | `0x00008000` | 1: `0x00002000`<br>2: `0x00004000`<br>3: `0x00008000`<br>4: `0x00010000` | none |
| Serta | `0x08000000` | `0x00001000` | no | `0x00004000` (not listed) | no | 1: `0x00002000`<br>2: `0x00004000`<br>3: `0x00008000`<br>4: `0x00010000` | none |
| OKIN FFE | `0x08000000` | `0x00001000` | no | `0x00004000` (not listed) | no | 1: `0x00002000`<br>2: `0x00004000`<br>3: `0x00008000`<br>4: `0x00010000` | none |
| BetterLiving CB1322 | `0x08000000` | `0x00001000` | no | `0x00004000` (not listed) | no | 1: `0x00010000`<br>2: `0x00040000` | 1: `0x00010000`<br>2: `0x00040000`<br>30 × 100 ms |
| Sino | `0x08000000` | `0x00001000` | no | `0x00004000` (not listed) | no | 1: `0x00002000`<br>2: `0x00004000`<br>3: `0x00008000`<br>4: `0x00010000` | none |
| BetterLiving | `0x01000002` | `0x01000001` | no | `0x00004000` (not listed) | `0x01000004` | 1: `0x01000008`<br>2: `0x01000009` | 1: `0x20000008`<br>2: `0x20000009` |
| JSON/A00A | `0x08000000` | `0x00001000` | `0x00002000` | `0x00004000` | `0x00008000` | 1: `0x00002000`<br>2: `0x00004000`<br>3: `0x00008000`<br>4: `0x00010000` | none |
| KSBT | `0x08000000` | `0x00001000` | `0x00002000` | `0x00004000` | `0x00008000` | 1: `0x00002000`<br>2: `0x00004000`<br>3: `0x00010000` | none |
| KSBT03C | `0x08000000` | `0x00001000` | `0x00002000` | `0x00004000` | `0x00008000` | 1: `0x00002000`<br>2: `0x00004000`<br>3: `0x00010000` | none |
| KSBT03CR | `0x08000000` | `0x00001000` | `0x00002000` | `0x00004000` | `0x00008000` | 1: `0x00002000`<br>2: `0x00004000`<br>3: `0x00008000`<br>4: `0x00010000` | none |
| KSBT04C | `0x08000000` | `0x00001000` | `0x00002000` | `0x00004000` | `0x00008000` | 1: `0x00002000`<br>2: `0x00004000`<br>3: `0x00010000` | none |
| Sleep Harmony (KSBT04C) | `0x08000000` | `0x00001000` | `0x00002000` | `0x00004000` | `0x00008000` | 1: `0x00002000`<br>2: `0x00004000`<br>3: `0x00008000` | none |
| Sleep Harmony (base-i5) | `0x08000000` | `0x00001000` | `0x00002000` | `0x00004000` | `0x00008000` | 1: `0x00002000`<br>2: `0x00004000`<br>3: `0x00008000` | none |
| Purple Premium | `0x08000000` | `0x00001000` | `0x00002000` | no | `0x00008000` | 1: `0x00010000`<br>2: `0x00004000` | 1: `0x00010000`<br>2: `0x00004000`<br>26 × 200 ms, waiting first |
| Purple Premium Plus | `0x08000000` | `0x00001000` | no | no | `0x00008000` | 1: `0x00010000`<br>2: `0x00002000`<br>3: `0x00004000` | 1: `0x00010000`<br>2: `0x00002000`<br>3: `0x00004000`<br>26 × 200 ms, waiting first |
| Adjustable Lite (KSBT01C) | `0x08000000` | `0x00001000` | no | no | no | 1: `0x00010000`<br>2: `0x00002000`<br>3: `0x00004000` | none |
| Adjustable Lite (KSBT03C) | `0x08000000` | `0x00001000` | no | no | `0x00008000` | 1: `0x00010000`<br>2: `0x00002000`<br>3: `0x00004000` | none |
| Restonic BT remote A | `0x08000000` | `0x00001000` (held) | no | no | no | none | none |
| Restonic BT remote B | `0x08000000` | `0x00001000` | no | no | no | none | none |
<!-- /generated -->

### Detection

| Signal | Suggested route |
|--------|-----------------|
| `0000a00a-0000-1000-8000-00805f9b34fb` service | JSON/A00A |
| Name contains `ergomotion`, `ergo` or `serta-i` | bed type `ergomotion` |
| Name contains `serta` or `motion perfect`; or FFE5 with `serta`, `motion perfect`, `ergomotion` or `hump` | bed type `serta` |
| FFE5 with a name containing `okin`, `cb-` or `cb.` | bed type `okin_ffe` |
| Both FFF0 and FFB0 services, or an `OKIN-BLE` name with one of them | BetterLiving, or CB1322 by manufacturer |
| Other FFE5 devices | `keeson` Base |

| Device Name Prefix | Protocol |
|-------------------|----------|
| `base` / `base-i5` | Ambiguous: Auto keeps the Base profile; Purple Premium uses E5/8-byte and Sleep Harmony uses E6/9-byte, so select either profile explicitly. Restonic BT (`base-i4` / `base-i5`) users select their remote's profile |
| `KSBT01C` | Nordic UART with 6-byte packets; select the Adjustable Lite profile for that app |
| `KSBT03C` | Nordic UART with 6-byte packets (3 motors: no head tilt; e.g. Ergomotion Rio 5.0); Adjustable Lite users select its profile |
| `KSBT04` | Nordic UART with 6-byte packets (confirmed Rio 6.0 family) |
| `KSBT04C` | Ambiguous: Auto keeps the legacy generic checksum profile; Purple Plus uses a trailing zero and Sleep Harmony uses app-specific checksum/release behavior, so select either profile explicitly |
| `ksbt03cr` | Nordic UART with 7-byte packets (KSBT03CR variant) |
| `EH` | Mattress variant (E0FF service) |

Discovery also matches name-only `KSBT01C*` and `KSBT03C*` advertisements.
The Adjustable Lite app also accepts the identity in the middle of a name. Auto
stays prefix-based so existing entries keep their frames; such beds can be added
manually with the Adjustable Lite profile, which selects its remote the same way.

Discovery likewise matches name-only `base-i4*` and `base-i5*` advertisements,
the names the Restonic BT Remote app accepts. Any name starting with `base-i4`,
with or without the dot, is detected as Keeson (Auto keeps Base); any `base-i5`
name is still offered as Cool Base. See
[Restonic BT profiles](#restonic-bt-profiles) for switching to the profile.

## Wire codec

`custom_components/adjustable_bed/codec/keeson.py` owns the transports, the K1
frame and checksum, the other carriers of the key word, the `00 B0` status
query, the `EF 02` rename frame and the Ergomotion status parser.

### Transports

<!-- generated:keeson-transports -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Transport | Service | Write | Notify | Fallbacks (service / write) | Profiles |
|---|---|---|---|---|---|
| BASE | `0000ffe5-0000-1000-8000-00805f9b34fb` | `0000ffe9-0000-1000-8000-00805f9b34fb` | `0000ffe4-0000-1000-8000-00805f9b34fb` | `0000fff0-0000-1000-8000-00805f9b34fb` / `0000fff2-0000-1000-8000-00805f9b34fb`<br>`0000ffb0-0000-1000-8000-00805f9b34fb` / `0000ffb2-0000-1000-8000-00805f9b34fb` | Base (BaseI4/I5), Ergomotion, Serta, OKIN FFE, BetterLiving CB1322, Sino, BetterLiving, Sleep Harmony (base-i5), Purple Premium, Restonic BT remote A, Restonic BT remote B, INNOVA, Simon Li, OKIN-Seating, Heal Every Night, AMERICANSTAR, Avanti Bases, Bedsense Bases, Dynasty Bases, MaxCoil Una |
| KSBT | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | `6e400020-b5a3-f393-e0a9-e50e24dcca9e` / `6e400021-b5a3-f393-e0a9-e50e24dcca9e`<br>`0000ffe5-0000-1000-8000-00805f9b34fb` / `0000ffe9-0000-1000-8000-00805f9b34fb`<br>`0000ffe0-0000-1000-8000-00805f9b34fb` / `0000ffe1-0000-1000-8000-00805f9b34fb` | KSBT, KSBT03C, KSBT03CR, KSBT04C, Sleep Harmony (KSBT04C), Purple Premium Plus, Adjustable Lite (KSBT01C), Adjustable Lite (KSBT03C) |
| JSON | `0000a00a-0000-1000-8000-00805f9b34fb` | `0000b002-0000-1000-8000-00805f9b34fb` | `0000b004-0000-1000-8000-00805f9b34fb` | none | JSON/A00A |
<!-- /generated -->

Detected profiles try the primary write role, then each fallback pair, and use
the first one whose characteristic exists; "fixed" profiles write only to their
transport's write role. A profile writes with response when the characteristic
offers it, unless its app leaves Android's default write type, in which case it
writes without response when that is offered.

### Framing and checksum

The K1 frame is `header FE 16 w0 w1 w2 w3 checksum`. The header is `E5` or `E6`,
the 32-bit word is little- or big-endian per profile, and the checksum is the
complement of the byte sum (`(~sum(previous bytes)) & 0xFF`), so all bytes sum
to `0xFF`. A side byte between word and checksum makes a nine-byte frame. The
`p2` carriers are the Okin N-frame layout; they live in this codec until that
family's codec exists.

<!-- generated:keeson-carriers -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Frame | Layout | Head up | Profiles |
|---|---|---|---|
| K1 `E5`, little-endian | `header FE 16` + word + checksum | `E5 FE 16 01 00 00 00 05` | Base (BaseI4/I5), Ergomotion, Serta, Purple Premium, Restonic BT remote A, Restonic BT remote B, INNOVA |
| K1 `E6`, little-endian | `header FE 16` + word + checksum | `E6 FE 16 01 00 00 00 04` | OKIN FFE, BetterLiving CB1322 |
| K1 `E5`, big-endian | `header FE 16` + word + checksum | `E5 FE 16 00 00 00 01 05` | Sino, BetterLiving, Simon Li, OKIN-Seating, Heal Every Night, AMERICANSTAR, Avanti Bases, Bedsense Bases, Dynasty Bases, MaxCoil Una |
| JSON | JSON envelope, see below | see JSON envelope | JSON/A00A |
| P2 6-byte | `04 02` + big-endian word | `04 02 00 00 00 01` | KSBT, KSBT03C, Adjustable Lite (KSBT01C), Adjustable Lite (KSBT03C) |
| P2 7-byte (`05`) | `05 02` + big-endian word + `00` | `05 02 00 00 00 01 00` | KSBT03CR |
| P2 7-byte, checksum end | `04 02` + big-endian word + checksum | `04 02 00 00 00 01 F8` | KSBT04C, Sleep Harmony (KSBT04C) |
| K1 `E6`, little-endian, side `00` | `header FE 16` + word + checksum | `E6 FE 16 01 00 00 00 00 04` | Sleep Harmony (base-i5) |
| P2 7-byte, `00` end | `04 02` + big-endian word + `00` | `04 02 00 00 00 01 00` | Purple Premium Plus |
| K1 `E6`, little-endian, Left side `02` | `E6 FE 16` + word + side + checksum | `E6 FE 16 01 00 00 00 02 02` | Base (BaseI4/I5), Ergomotion |
| K1 `E6`, little-endian, Right side `01` | `E6 FE 16` + word + side + checksum | `E6 FE 16 01 00 00 00 01 03` | Base (BaseI4/I5), Ergomotion |
<!-- /generated -->

#### Split-bed side byte

The nine-byte frame carries a side byte. Sleep Harmony's base-i5 route sends
side `00`. With [side controls](#side-controls) enabled, the Base and Ergomotion
profiles address one half with Left `02` or Right `01`, the selectors of the
Ergomotion 4.0 3.7 app builder; Both keeps the eight-byte `E5` frame. Every
command, release and STOP included, keeps the selected side.

The older A/B aliases in this guide (`01` side A, `02` side B) do not establish
physical A/B orientation. Android 3.7's A/B settings strings actually produce
selector `00` because its builder expects Left/Right. HA uses the proven
Left/Right branches. Physical half mapping awaits real-user validation after
beta/release.

### Command encoders

#### Key words

<!-- generated:keeson-keys -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Key | Word | Example frame | Example profile |
|---|---|---|---|
| Release (all keys up) | `0x00000000` | `E5 FE 16 00 00 00 00 06` | Base (BaseI4/I5) |
| Head up / down | `0x00000001` | `E5 FE 16 01 00 00 00 05` | Base (BaseI4/I5) |
|  | `0x00000002` | `E5 FE 16 02 00 00 00 04` | Base (BaseI4/I5) |
| Feet up / down | `0x00000004` | `E5 FE 16 04 00 00 00 02` | Base (BaseI4/I5) |
|  | `0x00000008` | `E5 FE 16 08 00 00 00 FE` | Base (BaseI4/I5) |
| Tilt up / down | `0x00000010` | `E5 FE 16 10 00 00 00 F6` | Base (BaseI4/I5) |
|  | `0x00000020` | `E5 FE 16 20 00 00 00 E6` | Base (BaseI4/I5) |
| Lumbar up / down | `0x00000040` | `E5 FE 16 40 00 00 00 C6` | Base (BaseI4/I5) |
|  | `0x00000080` | `E5 FE 16 80 00 00 00 86` | Base (BaseI4/I5) |
| Massage step | `0x00000100` | `E5 FE 16 00 01 00 00 05` | Base (BaseI4/I5) |
| Massage timer step | `0x00000200` | `E5 FE 16 00 02 00 00 04` | Base (BaseI4/I5) |
| Foot massage + / - | `0x00000400` | `E5 FE 16 00 04 00 00 02` | Base (BaseI4/I5) |
|  | `0x01000000` | `E5 FE 16 00 00 00 01 05` | Base (BaseI4/I5) |
| Head massage + / - | `0x00000800` | `E5 FE 16 00 08 00 00 FE` | Base (BaseI4/I5) |
|  | `0x00800000` | `E5 FE 16 00 00 80 00 86` | Base (BaseI4/I5) |
| Zero G | `0x00001000` | `E5 FE 16 00 10 00 00 F6` | Base (BaseI4/I5) |
| `0x2000`: Read, Lounge or a memory | `0x00002000` | `E5 FE 16 00 20 00 00 E6` | Base (BaseI4/I5) |
| `0x4000`: TV or a memory | `0x00004000` | `E5 FE 16 00 40 00 00 C6` | Base (BaseI4/I5) |
| `0x8000`: Anti-snore or a memory | `0x00008000` | `E5 FE 16 00 80 00 00 86` | Base (BaseI4/I5) |
| `0x10000`: M or a memory | `0x00010000` | `E5 FE 16 00 00 01 00 05` | Base (BaseI4/I5) |
| Light toggle | `0x00020000` | `E5 FE 16 00 00 02 00 04` | Base (BaseI4/I5) |
| Flat | `0x08000000` | `E5 FE 16 00 00 00 08 FE` | Base (BaseI4/I5) |
| Wave next / previous (Base) | `0x10000000` | `E5 FE 16 00 00 00 10 F6` | Base (BaseI4/I5) |
|  | `0x04000000` | `E5 FE 16 00 00 00 04 02` | Base (BaseI4/I5) |
| Intensity 1 / 2 / 3 (Base) | `0x00080000` | `E5 FE 16 00 00 08 00 FE` | Base (BaseI4/I5) |
|  | `0x00100000` | `E5 FE 16 00 00 10 00 F6` | Base (BaseI4/I5) |
|  | `0x00200000` | `E5 FE 16 00 00 20 00 E6` | Base (BaseI4/I5) |
| All massage off (Sleep Harmony) | `0x02000000` | `E6 FE 16 00 00 00 02 00 03` | Sleep Harmony (base-i5) |

Which word a profile sends for a preset or memory slot is in [Presets and
memory](#presets-and-memory).
<!-- /generated -->

> **Note:** Command `0x00008000` has different meanings depending on the protocol variant:
> - On **BaseI4/I5**: This is Memory 3 preset
> - On **KSBT and Purple**: This is Anti-Snore preset
> - On **Juna/Linx JSON remotes**: It may be Memory 3, Sleep, or another remote-specific preset depending on the remote family
>
> The `0x00002000`, `0x00004000`, `0x00008000`, and `0x00010000` addresses are reused by multiple Keeson remote families. On Juna/Linx they can correspond to `M`, `Read`, `TV`, `Sleep`, or memory slots depending on the chosen remote.

#### Sino words

<!-- generated:keeson-sino -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Command | Word | Frames (Sino) |
|---|---|---|
| Light on / off | `0x31000001` / `0x31000000` | `E5 FE 16 31 00 00 01 D4` / `E5 FE 16 31 00 00 00 D5` |
| Head massage level 0-10 | `0x10000010` + level | `E5 FE 16 10 00 00 10 E6` … `E5 FE 16 10 00 00 1A DC` |
| Foot massage level 0-10 | `0x11000010` + level | `E5 FE 16 11 00 00 10 E5` … `E5 FE 16 11 00 00 1A DB` |
| Wave pattern 1-10 | `0x10000020` + pattern | `E5 FE 16 10 00 00 21 D5` … `E5 FE 16 10 00 00 2A CC` |
<!-- /generated -->

#### JSON envelope

The JSON/A00A family uses a JSON envelope instead of the binary packets:

```json
{"code":2,"dvid":"<ble name>","cmd":{"key":"00001000","ctrm":1,"km":1,"keykt":0}}
```

`dvid` is the configured name, then the address. One-shot buttons use
`ctrm=1, km=1, keykt=0`; the zero key uses `ctrm=0, km=1, keykt=0`. Held motion
uses `km=3, keykt=1`; see [JSON/A00A](#jsona00a-variant-juna-linx-ergo-health).

#### Status query and rename

`00 B0` is the two-byte status query of the direct P2 remotes. It is not a STOP.
`EF 02` + the name padded to 15 bytes + checksum is INNOVA's rename frame.

### Responses

- **Ergomotion:** `ED` (16 bytes), `F0` (19) and `F1` (20) status notifications
  from FFE4. Bytes 1-2 and 3-4 are the little-endian head and foot positions in
  percent (`FFFF` reads as 0), bytes 5 and 6 the head and foot massage levels
  (0-6). Byte 13's low nibble is motion (`F` is idle, bit 0 head, bit 1 foot)
  and bit 6 the LED; byte 14 selects the 10, 20 or 30 minute timer (1-3).
- **Adjustable Lite**, **INNOVA**: see their sections.
- **Okin apps:** subscribed, replies discarded.
- **ORE comfort-bed apps:** never subscribed; see their section.

Every other profile reads nothing.

### STOP and release behavior

There is no dedicated STOP frame. A profile's release is in
[Hold and release timing](#hold-and-release-timing). Every release write uses a
fresh cancel event, so a STOP cannot suppress it; a touch-up release ("STOP ends
the wait") runs in a shielded task. Profiles with no release stop by ending the
cancellable refresh: their apps have no release frame, and inventing one would be
unsafe.

### Vectors

`tests/keeson_vectors.py` lists each profile's frozen single-frame literals:
the test vectors of the accepted Adjustable Lite, Restonic BT, INNOVA, Simon Li,
Heal Every Night, OKIN-Seating, MaxCoil Una, Dynasty Bases, Bedsense Bases,
Avanti Bases and AMERICANSTAR reports, and for every other route (which has no
report) every frame the pre-v5 controller could send.
`tests/test_keeson_vectors.py` checks that every literal round-trips through the
codec byte for byte, that each app profile sends only its frozen frames, that each
other route sends exactly its frozen frames, and that every protocol variant is a
profile. `tests/test_codec_docs.py` checks that every frame spelled in this guide
is one of those vectors and that the generated tables are current.

## Profiles

### Base (BaseI4/I5)

**Status:** ✅ Tested

#### Setup

Detection: FFE5 devices without a more specific name (see [Detection](#detection)).

#### Controls

Head, feet, tilt and lumbar motors; Flat and Zero G; memory 1-4 (slot 3 is the
only app-confirmed memory); light toggle; massage step keys. The GlideAway
ComfortBase Odessa hardware report in
[issue #508](https://github.com/kristofferR/ha-adjustable-bed/issues/508)
confirms the wave and intensity keys in [Key words](#key-words). A 3.6.0
follow-up confirmed the wave controls, while its logs showed that the
dashboard's established `massage_intensity_level_*` entity IDs no longer existed,
so those button presses never reached BLE. The entity IDs are retained for
compatibility. Their meanings are variant-specific and must not be applied to the
KSBT, Sino, Purple, or Ergomotion profiles. The existing `0x00000200` timer-step
action is separate from wave selection and is displayed as **Massage: Timer**
while retaining its established entity identity.

#### Side controls

The explicit **BaseI4/BaseI5** and **Ergomotion** variants, and the Ergomotion
bed type, offer **Configure → Enable side controls** for a P1 receiver that
reaches both halves through one Bluetooth address. This creates native Left and
Right child devices and retains the parent's Both controls, sending the
[side frames](#split-bed-side-byte). Auto is not eligible because it may
resolve to P2 or JSON at connection time, and the auto-detected BetterLiving
and CB1322 tables have no side frame.

The side frame is proven by Ergomotion 4.0 3.7; its use on Member's Mark
hardware remains unverified. Choose it only for a receiver with compatible P1
side addressing. It does not change existing standalone frames, pulse timings,
profiles or entity identities. Two separately advertising receivers use the
existing two-address combined-bed workflow.

Legacy position feedback cannot identify which half reported it, so side-control
mode disables position sliders, sensors and seeking; restoring standalone
controls restores the stored preference. For the complete app-specific products,
commands, notifications, alarms and RGB, select the separate
[Ergomotion 4.0 app profile](ergomotion-4.md).

#### Timing

See [Hold and release timing](#hold-and-release-timing) (Member's Mark scheduler).

### Ergomotion

**Status:** ✅ Tested

Behaves as [Base](#base-basei4i5), except as below.

#### Setup

Bed type `ergomotion`, or `keeson` with the `ergomotion` variant. Detection: a
name containing `ergomotion`, `ergo` or `serta-i`.

#### Controls

Adds Lounge, TV and Anti-snore; no wave or intensity keys. Supports the Base
profile's [side controls](#side-controls).

#### Notifications

Subscribes to FFE4 and reports head and foot positions as percentage sliders
(the firmware's `back` and `legs` axes) and the massage state, from the
[Ergomotion status](#responses). Positions ignore the angle calibration.

### Serta

**Status:** ❓ Needs testing

Behaves as [Base](#base-basei4i5), except as below.

#### Setup

Bed type `serta`, or `keeson` with the `serta` variant. Detection: a name
containing `serta` or `motion perfect`, or FFE5 with a Serta name pattern.
The Serta MP Remote app also supports classic Bluetooth (SPP UUID
`00001101-0000-1000-8000-00805F9B34FB`); this profile uses BLE only.

#### Controls

No wave or intensity keys. The TV action sends `0x4000` but is not listed as an
entity.

#### Timing

The Serta MP Remote app repeats held keys from a handler loop; see
[Hold and release timing](#hold-and-release-timing).

### OKIN FFE

**Status:** ❓ Needs testing

Behaves as [Serta](#serta), except as below.

#### Setup

Bed type `okin_ffe` (OKIN 13/15 series), or `keeson` with the `okin` variant.
Detection: FFE5 with a name containing `okin`, `cb-` or `cb.`. The `okin_ffe`
bed type stores its own default cadence, which is kept as configured.

#### Controls

`E6` frames; the three-motor screen uses its own cadence.

### Sino and BetterLiving

**Status:** ❓ Needs testing

#### Setup

`keeson` with the `sino` variant. Auto picks BetterLiving for BetterLiving/OKIN-BLE
devices (see [Detection](#detection)), and the CB1322 table when the
manufacturer name is `BLE-4.0 Module` or `DewertOKIN`. Entries that stored the
older `ore` alias are migrated to `sino` when the integration loads.

#### Controls

Big-endian `E5` frames, standard motor naming (head is head, feet is feet),
discrete light on/off with the toggle emulated from tracked state, and absolute
massage levels 0-10 tracked here ([Sino words](#sino-words)). BetterLiving uses
its BED_DEFAULT presets and saves; CB1322 uses the OKIN `E6` frame with its own
memory words and saves by repeating the recall word. See
[Presets and memory](#presets-and-memory).

The current MaxCoil Una and Dynasty Bases apps use the same frame with different
preset, save and massage words and a 2M/3M/4M layout choice: select their
[ORE comfort-bed profiles](#ore-comfort-bed-profiles). `sino` is unchanged.

#### Timing

BetterLiving uses its two-motor cadence, and its three-motor cadence on a
three-motor screen; see [Hold and release timing](#hold-and-release-timing).

### JSON/A00A Variant (Juna, Linx, Ergo Health)

**Status:** ❓ Needs testing

#### Setup

Detection: the `0000a00a` service. This is also the `keeson` Auto route when that
service exists.

#### Controls

The shared key words in the [JSON envelope](#json-envelope). Known remote
families from the OEM apps: `Quest`, `Rewind`, `Restore` and `Relax`. Held motion
is not uniform: `Quest` uses `ctrm=0, km=3, keykt=1`; `Rewind`, `Restore` and
`Relax` use `ctrm=1, km=3, keykt=1`. Each refresh sends the `ctrm=1` form, then
the `ctrm=0` form, so one profile serves every known remote.

#### Timing

The apps request a write every 5 ms (Juna) or 3 ms (Linx), but their BLE layer
drops requests while a write-with-response is outstanding, so there is no fixed
on-air interval to copy. Copying it as a BLE delay would be misleading and could
shorten a movement burst substantially; the profile keeps the established safe
burst until an on-air capture provides a device-independent interval.

### KSBT family

**Status:** ✅ Tested (KSBT); ❓ Needs testing (KSBT03C, KSBT03CR, KSBT04C)

Profiles: KSBT, KSBT03C, KSBT03CR and KSBT04C.

#### Setup

Detection: the Nordic UART service, and the name for KSBT03CR (`ksbt03cr`) and
the generic KSBT04C route. A `KSBT03C` name selects KSBT03C inside the `ksbt`
variant. Some Ergomotion-branded beds also use this variant: a confirmed Rio 6.0
support bundle advertises as `KSBT04...` and works with the standard KSBT 6-byte
protocol. Juna's `LVrestore` and `LVrelax` remotes also use this direct 6-byte
framing rather than the JSON/A00A path.

#### Controls

Read, TV and M are memory slots 1-3 (KSBT03CR: slots 1-2). **Ergomotion Sync
remotes (from `cn.com.mancini` APK):** the app has three remote layouts — A and C
target `KSBT04C` devices, B targets `KSBT03C` (e.g. Rio 5.0). All three share the
same preset buttons: Read, TV, M, Zero-G, Flat, light toggle and the head, foot
and timer massage steps (no all-off command). The Anti-Snore button appears on
layouts B/C only; that describes the remote UIs, not command support — the
integration exposes anti-snore on all KSBT variants.

**KSBT03C motor layout:** the KSBT03C remote (layout B) drives only three motors —
head/back, feet/legs and lumbar. There are no head-tilt buttons, so KSBT03C beds
have no tilt motor and the integration maps the third configured motor to lumbar.
KSBT04C remotes (layouts A/C) additionally have the head-tilt buttons. That
three-motor rule belongs to the direct six-byte KSBT profile. Sleep Harmony also
accepts a `KSBT03C` name but uses its separate explicit profile and exposes head,
foot, tilt/EJ and lumbar controls.

KSBT04C light, sound, light+sound and therapy controls are not mapped: the guessed
mappings were unverified and field reports showed they were wrong or unsafe.

#### Timing

Ergomotion 4.0, Q-Plus and 1500 Tilt Base write held movement keys immediately
and refresh them; releasing a key cancels that refresh and polls the `00 B0`
status query. None of these P2 paths writes the zero-key packet on release, and
an explicit stop sends nothing.

Ergomotion Sync 1.0.5's KSBT03C layout B is distinct: it writes immediately and
uses a fixed-delay timer. Release only cancels that timer; its status queries run
in a separate background loop. The app leaves Android's characteristic write type
unchanged, so detected `KSBT03C` beds use unacknowledged writes when the
characteristic supports them. This prevents a BLE proxy acknowledgement round
trip from stretching every refresh interval. Explicit per-device pulse settings
remain authoritative. No KSBT03C release frame was found in the complete
clean-room analysis, so the integration does not guess or substitute a zero-key
frame. Sync's KSBT04C layouts use their separate profile, including its existing
zero-frame release. KSBT03CR (SomosBeds) keeps its independently derived release.
See [Hold and release timing](#hold-and-release-timing).

#### Evidence

The KSBT03C command values and 3-motor layout are APK-derived (Ergomotion Sync
1.0.2) and not yet confirmed on hardware; the Rio 5.0 report in issue #408
confirms the lumbar motor responds to `0x40`/`0x80` and that no tilt motor
exists. The cadence, unacknowledged write mode and timer-cessation release are
statically verified from Ergomotion Sync 1.0.5 but remain hardware-unverified. A
replacement STOP frame must not be guessed without new protocol evidence or a
hardware capture.

### Sleep Harmony Variant

**App:** [Sleep Harmony](https://play.google.com/store/apps/details?id=com.keeson.ssbaudio) 1.0.1, `com.keeson.ssbaudio`

**Status:** ❓ Needs testing (clean-room APK analysis complete; hardware untested)

#### Setup

Select `sleep_harmony` (`Sleep Harmony (KSBT04C / base-i5)`). The name selects the
frame: `KSBT04C` / `KSBT03C` use the Nordic UART checksum frame, `base-i5.` the
nine-byte `E6` frame on FFE5 / FFE9 (notify FFE4). These prefixes overlap Purple
Smart Base while the packet endings differ. Select the explicit Purple or Sleep
Harmony profile; a name alone cannot distinguish the ecosystems safely.

#### Controls

Popup M1/M2/M3 send Reading, TV and Snore; there is no memory save. Its dedicated
massage-off command is in [Key words](#key-words). Lights are not mapped.

#### Timing

Motor commands start immediately and repeat. Releasing a motor or one-shot button
waits and sends one zero command. The integration preserves that UI release delay
but keeps the safety `stop_all` service immediate.

### Purple Variant

**App:** [Purple Smart Base](https://play.google.com/store/apps/details?id=com.keeson.purpleBase) 1.0.8, `com.keeson.purpleBase`

**Status:** ❓ Needs testing

#### Setup

Select `purple`. A `KSBT04C` name or a Nordic UART service selects Premium Plus;
otherwise Premium (`base-i5` names). Select the explicit Purple profile because
`base-i5` and `KSBT04C` names are also used by other Keeson app families with
different packet endings.

#### Controls

Premium has lounge, anti-snore and two memory slots, and no lighting. Premium Plus
has pillow and lumbar motors, anti-snore, three memory slots, massage, underbed
and motion lighting, and no lounge action. Memory words differ per product; see
[Presets and memory](#presets-and-memory).

#### Timing

Both repeat movement on a fixed-delay scheduler. On release, and after every
one-shot action, the app writes the Premium Plus zero-mask frame
`04 02 00 00 00 00 00`, including when Premium's FFE9 target is selected. The
dedicated save flow waits before each write; see
[Presets and memory](#presets-and-memory).

#### Notifications

The app's notifications report massage time/strength, light state, motion-light
state/duration and version; it contains no bed-position feedback parser. The
profile does not subscribe.

### Adjustable Lite Profile

**App:** [Adjustable Lite](https://play.google.com/store/apps/details?id=com.keeson.adjustablelite) 1.0.2 (5), `com.keeson.adjustablelite`

**Status:** ❓ Needs testing (clean-room analysis complete; hardware unverified)

#### Setup

Select the `adjustable_lite` (`Adjustable Lite app (KSBT01C / KSBT03C)`) protocol
variant. Auto keeps the generic KSBT profile, because Ergomotion Sync and Sleep
Harmony also use `KSBT03C` names with different memory labels, cadence or release
behavior. The app has two remotes, chosen by the case-sensitive token `KSBT03C`
in the device name; any other name gets the KSBT01C remote.

The app writes the six-byte KSBT frame to Nordic UART `6e400002`, with no
checksum, and never sets a write type, so the integration writes without response
when the characteristic offers it, as Android does by default.

#### Controls

<!-- generated:keeson-adjustable-lite -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Control | Word | Frame | Remotes |
|---|---|---|---|
| Head/back up | `0x00000001` | `04 02 00 00 00 01` | both |
| Head/back down | `0x00000002` | `04 02 00 00 00 02` | both |
| Leg/foot up | `0x00000004` | `04 02 00 00 00 04` | both |
| Leg/foot down | `0x00000008` | `04 02 00 00 00 08` | both |
| Flat | `0x08000000` | `04 02 08 00 00 00` | both |
| Zero G | `0x00001000` | `04 02 00 00 10 00` | both |
| Memory 1 | `0x00010000` | `04 02 00 01 00 00` | both |
| Memory 2 | `0x00002000` | `04 02 00 00 20 00` | both |
| Memory 3 | `0x00004000` | `04 02 00 00 40 00` | both |
| Light | `0x00020000` | `04 02 00 02 00 00` | both |
| Anti Snore | `0x00008000` | `04 02 00 00 80 00` | KSBT03C |
| Massage timer | `0x00000200` | `04 02 00 00 02 00` | KSBT03C |
| Head massage + | `0x00000800` | `04 02 00 00 08 00` | KSBT03C |
| Head massage - | `0x00800000` | `04 02 00 80 00 00` | KSBT03C |
| Leg massage + | `0x00000400` | `04 02 00 00 04 00` | KSBT03C |
| Leg massage - | `0x01000000` | `04 02 01 00 00 00` | KSBT03C |

Status query: `00 B0`, both remotes.
<!-- /generated -->

The shipped MI/MII/MIII labels take precedence over the app's internal
`m`/`read`/`tv` names, so memory slots 1-3 differ from the generic KSBT mapping.
The app has no memory save, lounge, TV, tilt, lumbar, massage toggle or massage
off control, and the profile exposes none of them. Massage steps, timer and
Anti-Snore require the `KSBT03C` name token; **Has massage** does not override that
selection.

#### Timing

Movement repeats on a timer from 0 ms. Release only cancels that timer: no STOP or
release frame exists, so the integration sends none. One-shot controls are written
once. See [Hold and release timing](#hold-and-release-timing).

#### Notifications

While connected, the app polls the status query; the integration polls at the
same interval on a live connection, without keeping the link open. Notifications
from `6e400003` longer than 12 bytes are read without header or checksum checks:

| Byte(s) | Meaning | Entity |
|---------|---------|--------|
| 12 | `1` lights the bulb icon; anything else is off | **Light** binary sensor |
| 3-4 (KSBT03C) | Big-endian value; above 1200, 600 or 0 shows the 30, 20 or 10 minute timer image, otherwise none | **Massage timer** sensor (0/10/20/30 min, raw value as attribute) |

Both states exist only while Home Assistant holds the connection. With the
default **Disconnect After Command** handoff, the link closes about a second
after each command, so Light and Massage timer are usually unknown and update
only briefly after a command. Turn the handoff off to keep them current until
the idle timeout, at the cost of holding the bed's Bluetooth connection, which
keeps the phone app out meanwhile.

#### TEMPUR-Ergo ProSmart Air / ActiveBreeze

For beds operated with **Tempur Sleeptracker-AI**, select
[Tempur Sleeptracker-AI (ProSmart / ActiveBreeze processor)](sleeptracker.md).
That profile provides the app's named presets, ActiveBreeze heat/cool controls
and premium 28 Hz / 40 Hz massage. Adjustable Lite is not the Tempur app profile.

The Adjustable Lite massage override from
[PR #671](https://github.com/kristofferR/ha-adjustable-bed/pull/671) and the local
KSSF05C preset workaround are removed.

Select the Sleeptracker processor's actual Bluetooth endpoint when adding the
Tempur profile. A `KSSF05C` / MC232SC name identifies neither that endpoint nor
the app layout. Changing an existing UART entry's profile alone cannot turn it
into the framed-JSON processor. See the [processor setup guide](sleeptracker.md#select-the-processor)
and [S02 discovery ledger](../apk-analysis/dispositions/S02-sleeptracker.md).

#### Evidence

See the [app disposition](../apk-analysis/dispositions/row051-adjustable-lite.md).
The app does not decode whether the light button toggles, how the timer button
cycles, massage level limits, or the unit of the raw timer value; those remain to
be confirmed on hardware by real users after a beta or release.

### Simon Li, Heal Every Night and OKIN-Seating Profiles

**App:** Simon Li 1.0.1 (2), `com.okin.simon`; Heal Every Night 1.0 (1), `com.okin.healeverynight`; OKIN-Seating 1.0.1 (2), `com.okin.minghua.R`

**Status:** ❓ Needs testing (clean-room analysis complete; hardware unverified)

#### Setup

Select the `simon_li`, `heal_every_night` or `okin_seating` protocol variant.
Detection: none. None of the apps filters its scan or reads a model, so add the
seat or bed manually as a Keeson bed and pick the app. Each app controls one
address, so add one entry per seat or bed. Their frames carry no side field. In a
two-address pair, unpair the beds before changing to, from or between these
profiles, so each side keeps its own app, and before changing the motor count
while a side uses Heal Every Night, whose motor count picks that receiver's
product. Every control comes from the stored profile, so a side that is out of
range keeps its entities and the other side of the pair still loads.

All three write big-endian `E5` frames to the first FFE9 characteristic of the
last service, in Java UUID order, that has one. The SDK rejects a characteristic
without the write property, and the apps never set a write type, so the
integration writes without response when FFE9 offers it, as Android does. There
is no PIN, pairing or initialization frame.

#### Controls

<!-- generated:keeson-okin-apps -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

#### Simon Li and OKIN-Seating keys

| Control | Simon Li | OKIN-Seating |
|---|---|---|
| `foot_up` | `E5 FE 16 00 00 00 01 05` | `E5 FE 16 00 00 00 01 05` |
| `foot_down` | `E5 FE 16 00 00 00 02 04` | `E5 FE 16 00 00 00 02 04` |
| `back_up` | `E5 FE 16 00 00 00 04 02` | `E5 FE 16 00 00 00 04 02` |
| `back_down` | `E5 FE 16 00 00 00 08 FE` | `E5 FE 16 00 00 00 08 FE` |
| `lumbar_up` | `E5 FE 16 00 00 00 10 F6` | - |
| `lumbar_down` | `E5 FE 16 00 00 00 20 E6` | - |
| `home` | `E5 FE 16 00 00 00 16 F0` | `E5 FE 16 00 00 00 0A FC` |
| `memory_1` | `E5 FE 16 00 00 00 40 C6` | - |
| `memory_2` | `E5 FE 16 00 00 00 80 86` | - |

#### Heal Every Night keys

Movement keys before the settings below swap or reverse them.

| Control | Word | Frame |
|---|---|---|
| Head up | `0x00000001` | `E5 FE 16 00 00 00 01 05` |
| Foot up | `0x00000004` | `E5 FE 16 00 00 00 04 02` |
| Tilt up | `0x00000010` | `E5 FE 16 00 00 00 10 F6` |
| Lumbar up | `0x00000040` | `E5 FE 16 00 00 00 40 C6` |
| Head down | `0x00000002` | `E5 FE 16 00 00 00 02 04` |
| Foot down | `0x00000008` | `E5 FE 16 00 00 00 08 FE` |
| Tilt down | `0x00000020` | `E5 FE 16 00 00 00 20 E6` |
| Lumbar down | `0x00000080` | `E5 FE 16 00 00 00 80 86` |
| Zero G | `0x01000001` | `E5 FE 16 01 00 00 01 04` |
| Flat | `0x01000002` | `E5 FE 16 01 00 00 02 03` |
| Memory 1 | `0x01000008` | `E5 FE 16 01 00 00 08 FD` |
| Memory 2 | `0x01000009` | `E5 FE 16 01 00 00 09 FC` |
| Save memory 1 | `0x20000008` | `E5 FE 16 20 00 00 08 DE` |
| Save memory 2 | `0x20000009` | `E5 FE 16 20 00 00 09 DD` |
| Preset STOP | `0x01000000` | `E5 FE 16 01 00 00 00 05` |
| Head massage level 0-3 | `0x10000010` + level | `E5 FE 16 10 00 00 10 E6` … `E5 FE 16 10 00 00 13 E3` |
| Foot massage level 0-3 | `0x11000010` + level | `E5 FE 16 11 00 00 10 E5` … `E5 FE 16 11 00 00 13 E2` |
| Wave 1-4 | `0x10000020` + wave - 1 | `E5 FE 16 10 00 00 20 D6` … `E5 FE 16 10 00 00 23 D3` |
| Timer (every label) | `0x10000030` | `E5 FE 16 10 00 00 30 C6` |
| Light on / off | `0x31000001` / `0x31000000` | `E5 FE 16 31 00 00 01 D4` / `E5 FE 16 31 00 00 00 D5` |

Release: `E5 FE 16 00 00 00 00 06` for all three apps.
<!-- /generated -->

Every Simon Li and OKIN-Seating control, including Home and memory, is a held key.
Home keeps the app's neutral label: the apps do not show that it means flat. Simon
Li has no save command: holding a memory key for 2.1 seconds shows "Memory saved",
so **Save memory** holds the same key for 2.1 seconds. A memory recall ends after
at most 2 seconds of elapsed time, whatever the pulse settings or write latency,
so it stays below the app's 2.1 s save hold. Whether the seat stores the position,
and its own save threshold, are unverified. OKIN-Seating's foot buttons carry the
opposite "union" artwork; the integration follows the button identifiers. The
motor count does not change these fixed controls.

Heal Every Night picks Healing 6, 7 or 8 with the motor count (2, 3 or 4).
Healing 7 and 8 both show tilt, lumbar and the light; tilt, lumbar and light keys
are Healing 7/8 only. Presets are single writes. Pressing the selected preset
again sends Preset STOP instead, as the app does, and selecting another preset
moves the selection. **Stop All** also sends Preset STOP while a preset is
selected; a cover stop does not, as the app's movement release does not. Stop All
and massage Off attempt every cleanup frame even if one fails or the action is
cancelled, then report the first error.

The massage page stays disabled until a timer is chosen. A timer turns zero
levels into one, then writes the timer key, the wave, head and foot levels
100 ms apart. The level sliders (head and foot 0-3, wave 1-4) and the +/- buttons
then write one frame each; +/- clamp but still write. **Massage: Off** (or the
timer's Off) writes head 0 and foot 0 and disables the page again, keeping the
levels. The light switch writes the explicit on/off key. The bed reports no light
state, so the switch starts unknown and shows the commanded state as assumed.
Preset selection, light state and massage levels change only once their frames
are written, so a failed or cancelled write leaves the previous state for a
retry. They are kept across reconnects until the entry is removed or its profile
changes. Home Assistant allows massage Off and any timer at any time, while the
app disables Off before a timer starts and disables the running timer's button.

Three settings selects mirror the app's settings page. They send nothing and only
change which key the head and foot controls write. They are stored for the Heal
Every Night profile, so changing to another profile and back restores them:

| Setting | Effect |
|---------|--------|
| Installation mode: swapped | Head controls drive the foot actuator and foot controls the head actuator |
| Actuator 1 direction: reversed | The head actuator's up and down keys are exchanged |
| Actuator 2 direction: reversed | The foot actuator's up and down keys are exchanged |

#### Timing

Held keys write at 0 ms and then at the apps' fixed refresh. The motor pulse count
sets how many writes a press makes; the interval stays fixed whatever the pulse
delay. The release cancels the refresh and writes the zero key after each app's
delay ([Hold and release timing](#hold-and-release-timing)). A cover stop or the
end of a timed move writes it at once; **Stop All** does too.

#### Notifications

The apps enable notifications on every FFE4 characteristic and discard the bytes,
so the integration subscribes too and keeps the replies for diagnostics only.

#### Services

The `hold_control` action holds any streamed control for 0.1-60 s.

#### Evidence

See the [app disposition](../apk-analysis/dispositions/row060-okin-simon-cluster.md),
which lists the exclusions. Real users should confirm, after a beta or release,
which actuators each key moves, what Home does, whether memory saves persist, the
Heal massage and light semantics, and the GATT layout.

### INNOVA Profile

**App:** INNOVA 2.0 (3), `com.ore.sfm`

**Status:** ❓ Needs testing (clean-room analysis complete; hardware unverified)

#### Setup

Select the `innova` (`INNOVA app`) protocol variant. Detection: none. The app
scans without any name or service rule, so Auto never chooses it; `ORE-` names
stay on the Base profile. Set the motor count to the screen picked in the app:
2 (2M), 3 (3M) or 4 (4M). For a two-address pair, split the pair before changing
the profile: each receiver keeps its own app profile. A pair side that is out of
range keeps its controls, built from the stored profile.

The app writes little-endian `E5` frames to the last `0000ffe9` it finds. It
requires `0000ffe4` to exist and never sets a write type, so the integration
writes without response when the characteristic offers it, as Android does.

#### Controls

<!-- generated:keeson-innova -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Held control (`hold_control` name) | Word | Frame | Screens |
|---|---|---|---|
| `back_up` | `0x00000001` | `E5 FE 16 01 00 00 00 05` | all |
| `back_down` | `0x00000002` | `E5 FE 16 02 00 00 00 04` | all |
| `legs_up` | `0x00000004` | `E5 FE 16 04 00 00 00 02` | all |
| `legs_down` | `0x00000008` | `E5 FE 16 08 00 00 00 FE` | all |
| `memory_a` | `0x00002000` | `E5 FE 16 00 20 00 00 E6` | all |
| `memory_b` | `0x00004000` | `E5 FE 16 00 40 00 00 C6` | all |
| `memory_timer` | `0x00000200` | `E5 FE 16 00 02 00 00 04` | all |
| `combined_up` | `0x00000005` | `E5 FE 16 05 00 00 00 01` | 2M |
| `combined_down` | `0x0000000A` | `E5 FE 16 0A 00 00 00 FC` | 2M |
| `lumbar_up` | `0x00000040` | `E5 FE 16 40 00 00 00 C6` | 3M/4M |
| `lumbar_down` | `0x00000080` | `E5 FE 16 80 00 00 00 86` | 3M/4M |
| `waist_up` | `0x00000010` | `E5 FE 16 10 00 00 00 F6` | 4M |
| `waist_down` | `0x00000020` | `E5 FE 16 20 00 00 00 E6` | 4M |

| One-shot control | Word | Frame |
|---|---|---|
| Zero G | `0x00001000` | `E5 FE 16 00 10 00 00 F6` |
| Flat | `0x08000000` | `E5 FE 16 00 00 00 08 FE` |
| Light | `0x00020000` | `E5 FE 16 00 00 02 00 04` |
| Head massage + | `0x00000800` | `E5 FE 16 00 08 00 00 FE` |
| Head massage - | `0x00800000` | `E5 FE 16 00 00 80 00 86` |
| Foot massage + | `0x00000400` | `E5 FE 16 00 04 00 00 02` |
| Foot massage - | `0x01000000` | `E5 FE 16 00 00 00 01 05` |
| Massage level | `0x00000100` | `E5 FE 16 00 01 00 00 05` |
| Massage timer (massage page) | `0x00000200` | `E5 FE 16 00 02 00 00 04` |

Release and Stop: `E5 FE 16 00 00 00 00 06`. Rename example (`BED`):
`EF 02 42 45 44 00 00 00 00 00 00 00 00 00 00 00 00 43`.
<!-- /generated -->

Covers: Back and Legs on every screen, Back + Legs (2M), the third actuator with
lumbar IDs (3M), Waist and Lumbar (4M); Memory A/B are held buttons and Stop sends
the release. INNOVA has no memory programming, absolute massage level, massage off
or anti-snore control.

#### Timing

Held controls write at 0 ms and then at the fixed refresh. Releasing them writes
the zero key after the app's delay; a Stop, a cancelled hold or a replacement
writes it at once, on a fresh event, so it cannot be suppressed. One-shot controls
wait before their write, as the app does. A cover or held button press holds for
the motor pulse count. See [Hold and release timing](#hold-and-release-timing).

#### Notifications

INNOVA subscribes to `0000ffe4`. Only 16- and 19-byte notifications are read,
without header or checksum checks:

| Length | Flag byte | Timer byte |
|--------|-----------|------------|
| 16 | 13 | 14 |
| 19 | 14 | 15 |

Flag bit 5 (`0x20`) suppresses the update and bit 6 (`0x40`) is the lamp icon,
shown as the **Light** binary sensor. The signed timer byte `-1` clears the
**Massage timer** sensor and `1`/`2`/`3` show 10/20/30 minutes; other values
leave it unchanged. Both states clear when the connection ends. The app shows
the lamp only on its light page and the timer only on its other pages; Home
Assistant shows both. The app enables FFE4 locally without writing the CCCD,
so delivery after Home Assistant subscribes needs confirming on hardware.

#### Services

`hold_control` holds any streamed control for 0.1-60 s, by the names in the held
control table. The `rename` action writes the app's 18-byte `EF 02` name frame: at
most 14 characters as typed, then trimmed and non-empty.

#### Evidence

See the [cluster disposition](../apk-analysis/dispositions/row059-ore-bedsense-innova.md).
Its cluster sibling Bedsense Bases uses the
[ORE comfort-bed profiles](#ore-comfort-bed-profiles). Hardware still needs to
confirm the physical actuator behind each key (the 3M third motor uses lumbar IDs
beside head artwork), how long Memory A/B must be held, massage level limits and
timer cycling, and the lamp bit.

### Restonic BT Profiles

**App:** Restonic BT Remote 1.2.0 (3), `com.keeson.restonicBT`

**Status:** ❓ Needs testing (clean-room analysis complete; hardware unverified)

#### Setup

The app has two remote styles, chosen by the user in its settings (A is the
default). Select the matching protocol variant: `restonic_a` (`Restonic BT
app, remote A (6 buttons)`) or `restonic_b` (`Restonic BT app, remote B (10
buttons)`). Neither is ever chosen automatically: the app accepts any device
name that starts with `base-i4` or `base-i5` (case-sensitive), and those names
are shared with Member's Mark, Purple, Sleep Harmony and Cool Base, which use
different cadences, releases or frames. How discovery offers such a bed:

| Advertised name | Offered as | What a Restonic BT user does |
|-----------------|------------|------------------------------|
| `base-i4…` (with or without a dot) | Keeson, Auto (Base profile) | Choose the `restonic_a` or `restonic_b` protocol variant |
| `base-i5…` (any) | Cool Base | Change the bed type to Keeson, then choose `restonic_a` or `restonic_b` |

Both styles write little-endian `E5` frames to FFE5 / FFE9 only. The app never
sets a write type, so the integration writes without response when the
characteristic offers it, as Android does by default. There is no notification,
read, handshake, PIN or memory.

#### Controls

<!-- generated:keeson-restonic -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| `hold_control` name | Word | Frame | Remote A | Remote B |
|---|---|---|---|---|
| `head_up` | `0x00000001` | `E5 FE 16 01 00 00 00 05` | held | held |
| `head_down` | `0x00000002` | `E5 FE 16 02 00 00 00 04` | held | held |
| `feet_up` | `0x00000004` | `E5 FE 16 04 00 00 00 02` | held | held |
| `feet_down` | `0x00000008` | `E5 FE 16 08 00 00 00 FE` | held | held |
| `flat` | `0x08000000` | `E5 FE 16 00 00 00 08 FE` | once | once |
| `zero_g` | `0x00001000` | `E5 FE 16 00 10 00 00 F6` | held | once |
| `back_legs_up` | `0x00000005` | `E5 FE 16 05 00 00 00 01` | no | held |
| `back_legs_down` | `0x0000000A` | `E5 FE 16 0A 00 00 00 FC` | no | held |
| `light` | `0x00020000` | `E5 FE 16 00 00 02 00 04` | no | once |
| `zzz` | `0x00008000` | `E5 FE 16 00 80 00 00 86` | no | once |

Release: `E5 FE 16 00 00 00 00 06` after every control.
<!-- /generated -->

Remote B's back-up and back-down glyphs (head and foot together) appear as a
**Back + Legs** cover. The app sends the same light frame on every press and
tracks no state, so the light is a toggle button, not a light entity. ZZZ is
exposed as a **ZZZ** button: the app does not show what it does, so it is not
mapped to anti-snore or a memory.

#### Timing

Held controls write at once and then at the refresh interval. Once controls write
a single frame when the button is pressed. Releasing any control writes the zero
frame after the app's delay. In Home Assistant, a cover or held Zero G button
press holds for the motor pulse settings, one-shot buttons press once. A Stop, a
cover's stop, or a command that replaces a running hold writes the zero frame at
once instead, and a Stop during the wait ends it. The Back + Legs cover shares its
scheduler lane with the head and foot covers, so moving or stopping either of
them interrupts it.

#### Services

`hold_control` holds any control for a chosen duration.

#### Evidence

See the [app disposition](../apk-analysis/dispositions/row058-restonic-bt.md).
Deferred validation for real users: the actual write mode, whether the light
toggles, what ZZZ does, how many actuators move, and whether the zero frame
stops motion and presets.

### ORE comfort-bed profiles

**App:** MaxCoil Una 1.1.0 (5), `com.ore.maxcoil`; Dynasty Bases 1.0.2 (3), `com.ore.Dynasty`; Bedsense Bases 1.1 (3), `com.ore.sfmc2bedsence`; Avanti Bases 1.0.5 (7), `com.ore.AvantiBases`; AMERICANSTAR 1.0 (1), `com.ore.americanstar`

**Status:** ❓ Needs testing (artifact-verified, hardware unverified)

- MaxCoil Una and Dynasty Bases ship the same `com.ore.okincomfortbed` code base.
- Bedsense Bases is a separate package, but its accepted report proves the same
  frames, screens, timing, release, massage, light and reply handling.
- The separate Avanti artifact proves every command, layout, timing and reply
  behavior below as well, and so does AMERICANSTAR 1.0 (1).
- INNOVA (`com.ore.sfm`), Bedsense's cluster sibling, uses different frames and
  has its own [INNOVA profile](#innova-profile).

#### Setup

Choose the app by name in the bed-type list, or choose **Keeson**, then the
protocol variant for your app: `maxcoil_una`, `dynasty_bases`, `bedsense_bases`,
`avanti_bases` or `americanstar`. Set the **motor count** to the screen you pick
in the app:

| App screen | Motor count | Covers |
|------------|-------------|--------|
| 2M | 2 | Back, Feet, Back and legs (one combined key) |
| 3M | 3 | Back, Feet, Head |
| 4M | 4 | Back, Feet, Waist, Lumbar |

- Detection: none. The apps scan for every Bluetooth device and let you choose one
  by address. They have no name, service or manufacturer rule, so **Auto never
  selects this profile**.
- The older `sino` variant (Dynasty, BetterLiving) is unchanged; it sends
  different preset and massage values.
- For a two-address pair, split the pair before changing the profile. A pair
  side that is out of range keeps its controls, built from the stored profile.
- Avanti motor layout is a per-side setting too; split before changing it. Its
  massage page is always enabled, refresh timing is fixed, and angle sensing is
  absent. Those three generic options are hidden for Avanti.

The apps write big-endian `E5` frames to the last `0000ffe9-0000-1000-8000-00805f9b34fb`
found across all services (the service UUID is ignored). Controls stay unavailable
unless `0000ffe4-0000-1000-8000-00805f9b34fb` exists too. The apps never set a
write type, so Android's default applies: write without response when the
characteristic offers it, otherwise with response. There is no PIN, pairing,
handshake, MTU request or initialization packet.

#### Controls

<!-- generated:keeson-ore -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

#### Motion

| Axis | Up | Down |
|---|---|---|
| 2M back, 3M back, 4M back | `E5 FE 16 00 00 00 01 05` | `E5 FE 16 00 00 00 02 04` |
| 2M feet, 3M feet, 4M feet | `E5 FE 16 00 00 00 04 02` | `E5 FE 16 00 00 00 08 FE` |
| 2M both, 3M head, 4M waist | `E5 FE 16 00 00 00 10 F6` | `E5 FE 16 00 00 00 20 E6` |
| 4M lumbar | `E5 FE 16 00 00 00 40 C6` | `E5 FE 16 00 00 00 80 86` |

#### Presets and memory

| Preset | Recall | Save |
|---|---|---|
| Zero G | `E5 FE 16 01 00 00 01 04` | `E5 FE 16 20 00 00 01 E5` |
| Flat | `E5 FE 16 01 00 00 02 03` | `E5 FE 16 20 00 00 02 E4` |
| Memory A | `E5 FE 16 01 00 00 08 FD` | `E5 FE 16 20 00 00 08 DE` |
| Memory B | `E5 FE 16 01 00 00 09 FC` | `E5 FE 16 20 00 00 09 DD` |

#### Massage and lights

| Command | Word | Frames |
|---|---|---|
| Wave massage level 0-3 | `0x10000020` + level | `E5 FE 16 10 00 00 20 D6` … `E5 FE 16 10 00 00 23 D3` |
| Head massage level 0-3 | `0x10000010` + level | `E5 FE 16 10 00 00 10 E6` … `E5 FE 16 10 00 00 13 E3` |
| Foot massage level 0-3 | `0x11000010` + level | `E5 FE 16 11 00 00 10 E5` … `E5 FE 16 11 00 00 13 E2` |
| Massage timer 10 min | `0x10000030` | `E5 FE 16 10 00 00 30 C6` |
| Massage timer 20 min | `0x10000031` | `E5 FE 16 10 00 00 31 C5` |
| Massage timer 30 min | `0x10000032` | `E5 FE 16 10 00 00 32 C4` |
| Light on / off | `0x31000001` / `0x31000000` | `E5 FE 16 31 00 00 01 D4` / `E5 FE 16 31 00 00 00 D5` |
| Release / STOP | `0x00000000` | `E5 FE 16 00 00 00 00 06` |
<!-- /generated -->

Memory A and B are position slots, not bed sides. Flat and Zero G can be saved
like the memory slots. The app toggles a local flag and sends explicit light on and
off words, so the integration exposes an under-bed light switch with assumed state.

| Entity | Behavior |
|--------|----------|
| Head, Foot and Wave massage numbers (0-3) | A slider change sends that zone's level word. Levels persist across restarts like the app's preferences; a fresh install starts at level 1. |
| **Start massage** button | Sends the current wave, head and foot levels, in that order. |
| **Massage off** button | Sends head level 0, then foot level 0. The sliders keep their levels and the timer indicator resets. No wave-off frame exists. |
| **Massage timer** select | Sends the 10, 20 or 30 minute word. The app's timer button cycles through the same three words; it has no timer-off word. |

- **Second tap:** tapping the running preset again sends the zero word. The
  integration exposes the same frame as the **Stop** button; preset buttons
  always recall.
- **Long press** on a preset saves it. The integration uses Save buttons
  (**Save Memory A/B**, **Save Flat**, **Save Zero G**).

#### Timing

The key is written at 0 ms and again after each write while held; on release the
app sleeps and writes the zero word. The integration uses the configured repeat
count at the app's fixed interval, then sends the zero word with a fresh cancel
event so a STOP can never suppress it. The app has one global key, so any STOP
ends every motion. Every other action sleeps first and is written once. See
[Hold and release timing](#hold-and-release-timing).

#### Notifications

None. The app accepts any nine-byte FFE4 value, extracts bits from byte 7 and
discards them. No position, light, massage or acknowledgement state exists.

#### Evidence

The app's phone settings (haptic feedback, actuator 1/2, installation) change no
packet. Exclusions are in the [ledgers](#analysis-provenance). Real users should confirm after a beta or release:
the physical axis for each layout (especially 2M's combined key and 4M's waist),
hold and release behavior, preset save/recall, massage levels and timer
durations, and the actual write type.

## Notes

### Timing evidence

Cadence belongs to the app or protocol family, not to the shared 32-bit command
values. The values are in [Hold and release timing](#hold-and-release-timing).

| Profile | OEM app evidence |
|---------|------------------|
| Base | Member's Mark fixed-delay scheduler; Base-family zero frame on release |
| JSON/A00A | Juna / Linx request scheduler, gated by one outstanding acknowledged write |
| KSBT | Ergomotion 4.0 / Q-Plus / 1500 Tilt Base refresh loop |
| KSBT03C | Ergomotion Sync 1.0.5 (Rio 5 layout) `Timer.schedule`; release only cancels the timer |
| KSBT03CR | SomosBeds `Timer.schedule` |
| Sleep Harmony | Sleep Harmony handler loop |
| Adjustable Lite | Adjustable Lite `Timer.schedule`; release only cancels the timer |
| INNOVA | INNOVA refresh with a delayed zero key |
| Restonic BT | Restonic BT Remote `Timer.schedule` with a delayed zero frame |
| Ergomotion | Ergomotion / Ergomotion 4.0 / Tempur Zero G handler loop |
| Serta | Serta MP Remote handler loop |
| Sino / BetterLiving / OKIN | BetterLiving two-motor and three-motor screens |
| Purple | Purple Smart Base fixed-delay scheduler |

For existing Keeson entries, the integration translates only the stored generic
default cadence to the matching profile. Any pulse count or delay that a user
customized remains authoritative. Dedicated Ergomotion, Serta, and OKIN FFE bed
types store their own defaults and are left unchanged.

### Analysis provenance

- Adjustable Lite 1.0.2 (5): [row051](../apk-analysis/dispositions/row051-adjustable-lite.md).
- Restonic BT Remote 1.2.0 (3): [row058](../apk-analysis/dispositions/row058-restonic-bt.md).
- Simon Li, Heal Every Night and OKIN-Seating: [row060](../apk-analysis/dispositions/row060-okin-simon-cluster.md).
- MaxCoil Una 1.1.0 (5) (`com.ore.maxcoil`) and Dynasty Bases 1.0.2 (3)
  (`com.ore.Dynasty`): clean-room analysis complete and accepted (formal
  cluster-013). See the [MaxCoil Una / Dynasty Bases dispositions](../apk-analysis/dispositions/row056-ore-maxcoil-dynasty.md).
- Bedsense Bases 1.1 (3) (`com.ore.sfmc2bedsence`) and INNOVA 2.0 (3)
  (`com.ore.sfm`): complete and accepted (formal cluster-015). See the
  [Bedsense Bases / INNOVA dispositions](../apk-analysis/dispositions/row059-ore-bedsense-innova.md).
- Avanti Bases 1.0.5 (7) (`com.ore.AvantiBases`, standalone FULL row065):
  independently accepted. See its [discovery ledger](../apk-analysis/dispositions/row065-avanti-bases.md).
- AMERICANSTAR 1.0 (1) (`com.ore.americanstar`): independently accepted. See its
  [dispositions](../apk-analysis/dispositions/row062-americanstar.md).
- The other routes come from the smartbed-mqtt reverse engineering, fresh
  decompilation of the OEM apps listed above, and hardware reports.
