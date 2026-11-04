# Keeson

**Status:** ✅ Tested (Base, KSBT and Ergomotion routes; the app profiles are APK-verified with hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), [alanbixby](https://github.com/alanbixby), [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt) and [MangoScango](https://github.com/MangoScango)

One wire codec (the K1 `E5/E6 FE 16` frame and the other carriers of the Keeson
32-bit key word) serves every `keeson` protocol variant, the `ergomotion`,
`serta` and `okin_ffe` bed types, the audited Keeson, Okin and ORE app
profiles, and the cluster033 app bed types. This guide covers the codec first, then one section per profile. See
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
| ✅ | [Q-Plus Adjustable Remote](https://play.google.com/store/apps/details?id=com.sbi.costco) | `com.sbi.costco` | [Q-Plus Adjustable Remote](#q-plus-adjustable-remote); also [KSBT](#ksbt-family) |
| ✅ | [Ergomotion](https://play.google.com/store/apps/details?id=com.sfd.ergomotion) | `com.sfd.ergomotion` | [Ergomotion app](#ergomotion-app); also [Ergomotion](#ergomotion) |
| ✅ | [Tempur Zero G Bed Base](https://play.google.com/store/apps/details?id=com.sfd.row) (ROW Control) | `com.sfd.row` | [ROW Control](#row-control); also [Ergomotion](#ergomotion) |
| ✅ | Tempur Curve | `com.ore.tempur` | [Tempur Curve](#tempur-curve); also [Base](#base-basei4i5) |
| ✅ | [Member's Mark Base Remote](https://play.google.com/store/apps/details?id=com.sfd.mm) | `com.sfd.mm` | [Base](#base-basei4i5) |
| ✅ | [Serta MP Remote](https://play.google.com/store/apps/details?id=com.ore.serta330) | `com.ore.serta330` | [Serta MP Remote](#serta-mp-remote); also [Serta](#serta) |
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
| ✅ | [Glideaway Motion](https://play.google.com/store/apps/details?id=com.ore.bedding.glideawaymontion) 1.0.3 (11) | `com.ore.bedding.glideawaymontion` | [Glideaway Motion](#glideaway-motion) |
| ✅ | Scott Living | `com.keeson.scottlivingrelease` | [Scott Living](#scott-living) |
| Separate processor | Tempur Sleeptracker-AI ([framed-JSON processor guide](sleeptracker.md)) | `com.fullpower.applications.horizon` | none |

The eight apps of the [cluster033 app family](#cluster033-app-family) (Tempur
Curve, Q-Plus, Serta MP Remote, Omazz Adjusto III, Ergomotion, ROW Control, Ergo
Slim and TEMPUR AU) are also their own bed types with their app's exact keys and
layouts; the "also" routes are the generic Keeson variants that drive the same beds.

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
profile is an explicit choice. The cluster033 apps are bed types of their own,
listed in the [cluster033 app family](#cluster033-app-family). The tables below
are generated from the profile data.

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
| Glideaway Motion | bed type `glideaway_motion` | K1 `E6`, little-endian, side `00` | app controller | app controller | app controller |
| Malouf legacy OKIN | bed type `malouf_legacy_okin` | K1 `E6`, little-endian, side `00` | app controller | app controller | app controller |
| Sleepy's BOX15 | bed type `sleepys_box15` | K1 `E6`, little-endian, side `00` | app controller | app controller | app controller |
| Scott Living | bed type `scott_living` | K1 `E6`, little-endian, side `01` | app controller | app controller | app controller |
| AdjustaMattress P1 | bed type `adjustamattress`, model P1 | K1 `E6`, little-endian, side `00` | app controller | app controller | app controller |
| AdjustaMattress P2 | bed type `adjustamattress`, model P2 | K1 `E5`, big-endian | app controller | app controller | app controller |
| SBI | bed type `sbi` | K1 `E5`, little-endian | app controller | app controller | app controller |
| Rondure | bed type `rondure` | K1 `E5`, little-endian | app controller | app controller | app controller |
| Cool Base | bed type `coolbase` | K1 `E5`, little-endian | app controller | app controller | app controller |
| BF | bed type `bf` | K1 `E5`, big-endian | app controller | app controller | app controller |
| Cherish | bed type `cherish` | K1 `E5`, big-endian | app controller | app controller | app controller |
| Comfort Enhancements | bed type `comfort_enhancements` | K1 `E5`, big-endian | app controller | app controller | app controller |

### Hold and release timing

A hold writes its frame the given number of times while the stored cadence is the
Keeson default; a customized cadence wins. Release waits count from the previous
write. An explicit stop sends the release without its waits. The [controller
profiles](#controller-profiles) keep their timing in their controllers.

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

Words, encoded in the profile's frame. AdjustaMattress P1, AdjustaMattress P2,
AMERICANSTAR, Avanti Bases, Bedsense Bases, BF, Cherish, Comfort Enhancements,
Cool Base, Dynasty Bases, Glideaway Motion, Heal Every Night, INNOVA, Malouf
legacy OKIN, MaxCoil Una, OKIN-Seating, Rondure, SBI, Scott Living, Simon Li,
Sleepy's BOX15 keep their key tables with their app controllers; see their
sections.

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

### Aliases

Bed types and routes that build the same controller over the same profile with
the same default timing, so they send identical bytes. They stay separate so
existing entries keep their identities; the
[protocol inventory](../design/protocol-inventory.md) proves the equality by capture.

| Bed type or route | Same as | Notes |
|-------------------|---------|-------|
| `ergomotion` | `keeson` variant `ergomotion` | See [Ergomotion](#ergomotion) |
| `serta` | `keeson` variant `serta` | See [Serta](#serta) |
| `keeson` variants `avanti_bases`, `bedsense_bases`, `dynasty_bases`, `maxcoil_una` | `keeson` variant `americanstar` | Identical profiles under each app's own key; see [ORE comfort-bed profiles](#ore-comfort-bed-profiles) |

`okin_ffe` and the `keeson` variant `okin` share the [OKIN FFE](#okin-ffe)
profile but not its timing: `okin_ffe` defaults to 7 pulses 150 ms apart and
the variant to 10 pulses 100 ms apart, so they are not aliases.

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
| K1 `E5`, little-endian | `header FE 16` + word + checksum | `E5 FE 16 01 00 00 00 05` | Base (BaseI4/I5), Ergomotion, Serta, Purple Premium, Restonic BT remote A, Restonic BT remote B, INNOVA, SBI, Rondure, Cool Base |
| K1 `E6`, little-endian | `header FE 16` + word + checksum | `E6 FE 16 01 00 00 00 04` | OKIN FFE, BetterLiving CB1322 |
| K1 `E5`, big-endian | `header FE 16` + word + checksum | `E5 FE 16 00 00 00 01 05` | Sino, BetterLiving, Simon Li, OKIN-Seating, Heal Every Night, AMERICANSTAR, Avanti Bases, Bedsense Bases, Dynasty Bases, MaxCoil Una, AdjustaMattress P2, BF, Cherish, Comfort Enhancements |
| JSON | JSON envelope, see below | see JSON envelope | JSON/A00A |
| P2 6-byte | `04 02` + big-endian word | `04 02 00 00 00 01` | KSBT, KSBT03C, Adjustable Lite (KSBT01C), Adjustable Lite (KSBT03C) |
| P2 7-byte (`05`) | `05 02` + big-endian word + `00` | `05 02 00 00 00 01 00` | KSBT03CR |
| P2 7-byte, checksum end | `04 02` + big-endian word + checksum | `04 02 00 00 00 01 F8` | KSBT04C, Sleep Harmony (KSBT04C) |
| K1 `E6`, little-endian, side `00` | `header FE 16` + word + checksum | `E6 FE 16 01 00 00 00 00 04` | Sleep Harmony (base-i5), Glideaway Motion, Malouf legacy OKIN, Sleepy's BOX15, AdjustaMattress P1 |
| P2 7-byte, `00` end | `04 02` + big-endian word + `00` | `04 02 00 00 00 01 00` | Purple Premium Plus |
| K1 `E6`, little-endian, side `01` | `header FE 16` + word + checksum | `E6 FE 16 01 00 00 00 01 03` | Scott Living |
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

`00 B0` is the two-byte status query of the direct P2 remotes and Q-Plus MX. It
is not a STOP. `EF 02` + the name zero-filled to 15 bytes + checksum is the
rename frame of INNOVA and the cluster033 apps.

#### Setup frames

The cluster033 apps also send these checked frames, built by the codec:
`E7 80 01` + year minus 1900, zero-based month, day, hour, minute, second +
checksum (clock); `E1 80 04 9A` (wake alarm dismissal); and `E5 FE 17` + two
little-endian 16-bit pulse counts + checksum (Serta MP Remote position targets).
Their `ED 80` alarm tables come from `alarm_table.py`; see
[Alarm tables](#alarm-tables).

### Responses

- **Ergomotion:** `ED` (16 bytes), `F0` (19) and `F1` (20) status notifications
  from FFE4. Bytes 1-2 and 3-4 are the little-endian head and foot positions in
  percent (`FFFF` reads as 0), bytes 5 and 6 the head and foot massage levels
  (0-6). Byte 13's low nibble is motion (`F` is idle, bit 0 head, bit 1 foot)
  and bit 6 the LED; byte 14 selects the 10, 20 or 30 minute timer (1-3).
- **Adjustable Lite**, **INNOVA**: see their sections.
- **Okin apps:** subscribed, replies discarded.
- **ORE comfort-bed apps:** never subscribed; see their section.
- **Cluster033 apps:** the app timer status, and Serta MP Remote positions; see
  the [cluster033 app family](#cluster033-app-family).

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
Avanti Bases and AMERICANSTAR reports, every codec frame the cluster033, Glideaway Motion
and AdjustaMattress reports spell (plus the pre-v5 frame of any key a report lists without spelling it), and
for every other route (which has no report) every frame the pre-v5 controller
could send.
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

### Cluster033 app family

Eight apps share one controller (`beds/cluster033.py`) and the profile type
`AppProfile`. Each app is its own bed type, chosen by hand with the layout its
app shows; nothing in an advertisement selects one. Each accepted report proves
its own key table: a repeated mask is a separate package receipt, not an inferred
equivalence between apps.

<!-- generated:keeson-apps -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Profile | Bed type | Layouts (default bold) | Frame | Write / notify | Rename | Clock | Wake dismissal | Alarm tables |
|---|---|---|---|---|---|---|---|---|
| [Tempur Curve](#tempur-curve) | `tempur_curve` | **standard** | K1 `E5`, little-endian | FFE9 / FFE4 | 14 UTF-16 units, trimmed | 2 s after connect, and on demand | 2 × `E1 80 04 9A`, 400 ms apart | wake byte `0x03`, marker `0x80`, 3 per table |
| [Q-Plus Adjustable Remote](#q-plus-adjustable-remote) | `qplus_app` | H, M1, **M2**, M3, MX | K1 `E5` (Both) or `E6` + side byte (A/B); MX: P2 6-byte | FFE9 / FFE4 / NUS TX / NUS RX | 14 UTF-16 units, outer spaces rejected | none | 4 × `E1 80 04 9A`, 200 ms apart | wake byte `0x10`, marker `0x80`, 3 per table |
| [Serta MP Remote](#serta-mp-remote) | `serta_mp_remote` | **standard** | K1 `E5`, little-endian | FFE9 / FFE4 | 14 UTF-16 units, trimmed | none | none | none |
| [Omazz Adjusto III](#omazz-adjusto-iii) | `omazz_adjusto_iii` | **RemoteB** | K1 `E5`, little-endian | FFE9 / FFE4 | none | on demand | none | wake byte `0x03`, no marker, 3 per table |
| [Ergomotion app](#ergomotion-app) | `ergomotion_app` | B1, **B2**, C1, D1 | K1 `E5`, little-endian | FFE9 / FFE4 | 15 UTF-16 units, trimmed | on demand | none | wake byte `0x03`, no marker, 3 per table |
| [ROW Control](#row-control) | `row_control` | **Elevate**, Lifestyle, Curve, Lifestyle Plus, Zero-G Box | K1 `E5`, little-endian | FFE9 / FFE4 | 15 UTF-16 units, trimmed | 2 s after connect, and on demand | 2 × `E1 80 04 9A`, 400 ms apart | wake byte `0x03`, marker `0x80`, 3 per table |
| [Ergo Slim](#ergo-slim) | `ergo_slim` | **A**, B, C | K1 `E5`, little-endian | FFE9 / FFE4 | 14 UTF-16 units, trimmed | at connect, and on demand | 4 × `E1 80 04 9A`, 200 ms apart | wake byte `0x03`, marker `0x80`, 3 per table |
| [TEMPUR AU](#tempur-au) | `tempur_au` | B1, **B2**, C1, D1, E1 | K1 `E5`, little-endian | FFE9 / FFE4 | 14 UTF-16 units, trimmed | 2 s after connect, and on demand | 2 × `E1 80 04 9A`, 400 ms apart | wake byte `0x03`, marker `0x80`, 3 per table |
<!-- /generated -->

#### Setup

- Select the app by name in the bed-type list and use the Bluetooth address of
  the bed. Shared services, names and manufacturer data never select an app.
- Choose the layout your app shows in **App controls** (**App layout**, stored
  as `product_type`). A layout is a UI choice, not proof of motor count or model.
- Each side of a two-address pair keeps its own app settings. Target the native
  child device, or the paired action's `side`; conflicting child and side
  requests are rejected. No one-address pairing or left/right mapping is
  inferred.

##### Home Assistant setup

Choose the exact app in the bed-type picker: [Tempur Curve](#tempur-curve),
[Q-Plus Adjustable Remote](#q-plus-adjustable-remote),
[Serta MP Remote](#serta-mp-remote), [Omazz Adjusto III](#omazz-adjusto-iii),
[Ergomotion](#ergomotion-app), [ROW Control](#row-control),
[Ergo Slim](#ergo-slim), or [TEMPUR AU](#tempur-au).
Shared Bluetooth names, UUIDs and manufacturer data do not identify these apps.
Select the bed address manually when automatic discovery cannot disambiguate it.

**App controls** asks for the layout shown by the app. Q-Plus defaults to M2;
Ergomotion and TEMPUR AU default to B2; Omazz uses its reachable RemoteB layout.
The layout fixes the available actions and source timing. It does not prove
physical motor count. The pulse count bounds a normal held-action button press;
it does not change the source 100 ms refresh interval. Serta's local angle-edit
controls instead change one degree every 200 ms and send only on release.

Q-Plus's **Both/Side A/Side B** setting controls its P1 packet selector. It is
independent of a Home Assistant paired Left/Right target. MX Memory1 is an
opaque app-labelled action, with no invented physical save/recall meaning.
Serta MP's four configurable local head/foot memory targets are likewise
separate from the remote M4 key and from physical memory programming.

Each physical side owns its app layout and Serta local memory targets. Configure
a two-address pair's sides independently. Saving ordinary or shared settings retains
each declared app layout, Q-Plus A/B/Both wire selector and Serta local targets
through reload; unrelated settings from a previous protocol are removed.
Shared options do not overwrite side-owned settings. Native child-device
targeting and side conflicts follow the existing
paired rules. No unproven single-address physical side mapping is added.

All eight profiles require both current-session write and notification roles.
The seven profiles without position feedback keep angle sensing disabled and
still subscribe for their proven timer state. Serta MP exposes calibrated angle
feedback and direct pulse targets. Hardware behavior remains unverified.

#### Controls

- Head and foot keys drive the **Back** and **Legs** covers. Every other key is
  an app-labelled button; held keys also accept
  [`hold_control`](../SERVICES.md#hold_control). Physical effects are unverified.
- Cover stop and **Stop All** send the zero key frame (MX: the release queries).
- Opaque app keys such as *Memory Level 1* or *M4* are buttons, not memory slots:
  no app has a physical memory-save command.
- Each app's key table, generated from its profile, is in its section below.

#### Timing

| Behavior | Sequence |
|----------|----------|
| `held` | Key frame at once, then every 100 ms until release; then the release |
| `pulse` | Key frame once, then the release after 300 ms |
| `single` | Key frame once; Q-Plus MX then queries `00 B0` at +500 and +800 ms |
| `tap_zeros` | Key frame once, then zero frames at +300, +400 and +500 ms |
| `held_zeros` | As `held`, plus zero frames scheduled at +300, +400 and +500 ms from the start of the hold, kept after an early release |

- The release is the zero key frame; Q-Plus MX instead queries `00 B0` at +300,
  +600 and +900 ms. It runs with a fresh cancel event.
- A button press holds for the configured pulse count × 100 ms (1-60000 ms); the
  pulse count does not change the 100 ms refresh. `hold_control` accepts only
  the declared held keys, for 1-60000 ms.
- Cancellation and disconnect leave no writer from an old operation running.
- The clock frame is followed by 500 ms of pacing; when it is sent at connect is
  in the table above.

#### Transport and session

- The controller matches the write and notify characteristics across all
  services, keeping the last match of each; both are required. Q-Plus also
  accepts the Nordic UART roles.
- It writes with response when the write characteristic has the `write`
  property, otherwise without. The apps leave Android's write type unset, which
  does not prove an on-air mode.
- A disconnect invalidates the handles, pending work and stale notifications.

#### Alarm tables

Use [`adjustable_bed.configure_alarm_schedule`](../SERVICES.md#configure_alarm_schedule).
The encoder is `alarm_table.py`; its per-app wake byte, weekday marker and
capacity are in the table above.

| Field | Value |
|-------|-------|
| Weekly frame | `ED 80 03`, 16 bytes |
| One-time frame | `ED 80 02`, 16 bytes |
| Records | Three four-byte records (bytes 3-14) and the checksum at byte 15 |
| Weekly record | Hour, minute, weekday byte, wake byte |
| One-time record | Delay hours (low byte), minutes, seconds, wake byte |
| Weekday byte | The marker plus weekday bits: Monday through Saturday are bits 1-6, Sunday bit 0 |
| Dispatch | `both` sends weekly, waits 500 ms, then one-time; a single table also waits 500 ms after the send |

- `weekly`, `one_time` and `dispatch` are required. Disabled rows take no slot.
- Both full tables and every target are validated before any write, including
  an unselected table. A transport failure can leave only one table sent.
- An enabled one-time row is a future HH:MM on the same local date, measured from
  one captured `now` shared by every target. Past, nonexistent and ambiguous DST
  times are rejected; there is no next-day rollover. Delays use Java millisecond
  precision before the hour/minute/second split.
- An empty table is an attempted write, not proof that the firmware clears it.

#### Notifications

The **App timer status** sensor reports the app's timer: -1 off, 1, 2 or 3 for
10, 20 or 30 minutes. Status byte `0xFF` is off; other values leave the sensor
unchanged. Packets are not reassembled, and nothing else (acknowledgement,
battery, motor count, light state) is inferred.

| Length | Tempur Curve, ROW Control, TEMPUR AU | Ergomotion app | Omazz | Ergo Slim | Q-Plus | Serta MP Remote |
|---|---|---|---|---|---|---|
| 16 | byte 14 if byte 13 bit 5 is clear | same | same | byte 14 if byte 13 bit 5 is clear and bytes 7-9 are zero | as Ergo Slim; a frame starting `A5 0B 0D` first maps its big-endian seconds (bytes 3-4) 1-600/601-1200/1201-1800 to 1/2/3, else off | byte 14 if byte 13 bit 5 is clear |
| 19 | byte 15 if byte 14 bit 5 is clear | byte 14 when byte 0 is `F1`, else byte 15 | ignored | byte 14 (`F1`) or 15 (`F4`); other markers ignored | byte 15 if byte 16 bit 1 is clear and bytes 7-9 are zero | ignored |
| 20 | byte 14 | byte 14 | byte 14 | byte 14 | byte 14 | ignored |
| 23 | ignored | ignored | byte 15 | ignored | byte 15 | ignored |

ROW Control's Zero-G Box layout has an empty timer handler, so it has no sensor.

#### Services

- [`adjustable_bed.rename`](../SERVICES.md#rename) writes the `EF 02` name frame.
  The apps copy as many UTF-8 bytes as the name has UTF-16 units (Android's
  default charset), so a non-ASCII name can end with a partial character. The
  limit and trimming are in the table above; a name that does not fit is
  rejected before writing.
- [`adjustable_bed.sync_clock`](../SERVICES.md#sync_clock) writes the `E7 80 01`
  clock frame: year minus 1900, zero-based month, day, hour, minute, second.
- **Dismiss wake vibration** (`dismiss_alarm`) writes `E1 80 04 9A` as in the
  table above; it does not cancel movement.

#### Native card holds

- The card calls the bounded `hold_control` action once from each entity's hold
  metadata (`held_control`, or `held_control_up`/`held_control_down` on covers,
  plus `hold_start_delay_ms` and `hold_release_delay_ms`).
- These controls declare 0 ms for both delays, so the card sends STOP as soon as
  the control is released. Pointer and key release, blur and leaving the page all
  stop; a normal press keeps the finite action.
- Combined parent buttons offer a held direction only when every side declares
  the same control and delays on a concurrent pair.
- Q-Plus MX's release queries come from the controller's cleanup, not the card.

#### Evidence

The [disposition ledger](cluster033-dispositions.json) holds every discovery of
the accepted cluster033 reports and its disposition. Actual bed effects and
firmware interpretation are unverified.

| App | Package | Version | Artifact-set SHA-256 |
|---|---|---|---|
| Tempur Curve | `com.ore.tempur` | 1.7 | `f3c98817a94bf697fb02fe6850134cf6c248b2bb69f10a6943007d291487bb60` |
| Q-Plus Adjustable Remote | `com.sbi.costco` | 1.8 | `0b1be16e910c944624a6a2991a23840e23dae88a8eba750a12f3c773ffd63803` |
| Serta MP Remote | `com.ore.serta330` | 1.1 | `dfef30206d9f0b61a56fbb74602c2a04bbbc388ab0eb933cd10084bfe5a65146` |
| Omazz Adjusto III | `com.sfd.Omazz` | 1.0.5 | `bfb77d2660c8b7dd62472d063eed6e2b0c476dcfbce83edf956f54bec0130d87` |
| Ergomotion | `com.sfd.ergomotion` | 1.6.4 | `9b0f2fd91e57f64d8cb3da762896adb1c1410cfff82615e4c8051ac367c72dc6` |
| ROW Control | `com.sfd.row` | 2.0 | `eeb3fac46a412395cddd0986d85cf2d4b141880b068f4e4f81baac305e1d43ee` |
| Ergo Slim | `com.sfd.slim` | 1.3 | `57fc9f61148e8eefa885e006ab371de02f79ffb92d49677d306b1999007f7019` |
| TEMPUR AU | `com.sfd.tempur_au` | 1.6 | `f3c19632ce4da141f3fd4f46253a5bd511a28a680fd0b70a34db6a899c732c7b` |

### Tempur Curve

**App:** [Tempur Curve](https://play.google.com/store/apps/details?id=com.ore.tempur) 1.7, `com.ore.tempur`

Bed type `tempur_curve`, one layout. Shared behavior is in the
[cluster033 app family](#cluster033-app-family).

#### Controls

<!-- generated:keeson-app-tempur-curve -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| App label | Key | Mask | Frame | Behavior |
|---|---|---|---|---|
| Head Up (Back cover) | `head_up` | `0x1` | `E5 FE 16 01 00 00 00 05` | `held` |
| Head Down (Back cover) | `head_down` | `0x2` | `E5 FE 16 02 00 00 00 04` | `held` |
| Foot Up (Legs cover) | `foot_up` | `0x4` | `E5 FE 16 04 00 00 00 02` | `held` |
| Foot Down (Legs cover) | `foot_down` | `0x8` | `E5 FE 16 08 00 00 00 FE` | `held` |
| Massage Timer | `massage_timer` | `0x200` | `E5 FE 16 00 02 00 00 04` | `pulse` |
| Massage Foot Add | `massage_foot_add` | `0x400` | `E5 FE 16 00 04 00 00 02` | `pulse` |
| Massage Head Add | `massage_head_add` | `0x800` | `E5 FE 16 00 08 00 00 FE` | `pulse` |
| Zero G | `zero_g` | `0x1000` | `E5 FE 16 00 10 00 00 F6` | `single` |
| Tv Iii | `tv_III` | `0x4000` | `E5 FE 16 00 40 00 00 C6` | `held` |
| Anti Snore I | `anti_snore_I` | `0x8000` | `E5 FE 16 00 80 00 00 86` | `held` |
| Light | `light` | `0x20000` | `E5 FE 16 00 00 02 00 04` | `single` |
| Flat | `flat` | `0x8000000` | `E5 FE 16 00 00 00 08 FE` | `single` |
| Reset | `reset` | `0x8001000` | `E5 FE 16 00 10 00 08 EE` | `held` |
| Lounge Ii | `lounge_II` | `0x2000` | `E5 FE 16 00 20 00 00 E6` | `held` |
<!-- /generated -->

### Q-Plus Adjustable Remote

**App:** [Q-Plus Adjustable Remote](https://play.google.com/store/apps/details?id=com.sbi.costco) 1.8, `com.sbi.costco`

Bed type `qplus_app`. The generic `sbi` bed type is a separate route over the
same frame.

#### Setup

**Q-Plus bed selection** (Both, Side A or Side B, stored as `protocol_variant`
`both`, `side_a` or `side_b`) is the app's wire selector, not a paired Left/Right
target. P1 layouts (H, M1, M2, M3) send it; MX ignores it.

<!-- generated:keeson-qplus-sides -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Selector | Head up | Release |
|---|---|---|
| Both (`both`) | `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` |
| Side A (`side_a`) | `E6 FE 16 01 00 00 00 01 03` | `E6 FE 16 00 00 00 00 01 04` |
| Side B (`side_b`) | `E6 FE 16 01 00 00 00 02 02` | `E6 FE 16 00 00 00 00 02 03` |

MX keys the sparse builder accepts (any other key is sent as zero): `0x1`, `0x2`,
`0x4`, `0x8`, `0x10`, `0x20`, `0x200`, `0x400`, `0x800`, `0x2000`, `0x4000`,
`0x8000`, `0x10000`, `0x20000`, `0x800000`, `0x1000000`, `0x2000000`, `0x4000000`,
`0x8000000`, `0x40000000`.
<!-- /generated -->

#### Controls

<!-- generated:keeson-app-qplus-app -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| App label | Key | Mask | Frame | Behavior | Layouts |
|---|---|---|---|---|---|
| Head Up (Back cover) | `head_up` | `0x1` | `E5 FE 16 01 00 00 00 05` | `held` | H, M1, M2, M3 |
| Head Down (Back cover) | `head_down` | `0x2` | `E5 FE 16 02 00 00 00 04` | `held` | H, M1, M2, M3 |
| Foot Up (Legs cover) | `foot_up` | `0x4` | `E5 FE 16 04 00 00 00 02` | `held` | H, M1, M2, M3 |
| Foot Down (Legs cover) | `foot_down` | `0x8` | `E5 FE 16 08 00 00 00 FE` | `held` | H, M1, M2, M3 |
| Tilt Up | `tilt_up` | `0x10` | `E5 FE 16 10 00 00 00 F6` | `held` | H, M2 |
| Tilt Down | `tilt_down` | `0x20` | `E5 FE 16 20 00 00 00 E6` | `held` | H, M2 |
| Lumbar Up | `lumbar_up` | `0x40` | `E5 FE 16 40 00 00 00 C6` | `held` | H |
| Lumbar Down | `lumbar_down` | `0x80` | `E5 FE 16 80 00 00 00 86` | `held` | H |
| Level | `level` | `0x100` | `E5 FE 16 00 01 00 00 05` | `single` | H, M1, M2, M3 |
| Zero_G | `zero_g` | `0x1000` | `E5 FE 16 00 10 00 00 F6` | `single` | H, M1, M2, M3 |
| Read | `read` | `0x2000` | `E5 FE 16 00 20 00 00 E6` | `held` | H, M1, M2, M3 |
| Flat | `flat` | `0x8000000` | `E5 FE 16 00 00 00 08 FE` | `single` | H, M1, M2, M3 |
| Reset | `reset` | `0x8001000` | `E5 FE 16 00 10 00 08 EE` | `held` | H, M1, M2, M3 |
| Massage Head | `massage_head` | `0x800` | `E5 FE 16 00 08 00 00 FE` | `single` | H, M1, M2 |
| Massage Foot | `massage_foot` | `0x400` | `E5 FE 16 00 04 00 00 02` | `single` | H, M1, M2 |
| Music | `music` | `0x4000` | `E5 FE 16 00 40 00 00 C6` | `held` | H, M1 |
| TV | `tv` | `0x8000` | `E5 FE 16 00 80 00 00 86` | `held` | H, M1 |
| Light | `light` | `0x20000` | `E5 FE 16 00 00 02 00 04` | `single` | H, M1 |
| Lumbar Massage | `lumbar_massage` | `0x400000` | `E5 FE 16 00 00 40 00 C6` | `single` | H, M1 |
| Massage Mode 3 | `massage_mode_3` | `0x80000` | `E5 FE 16 00 00 08 00 FE` | `single` | H |
| Massage Mode 1 | `massage_mode_1` | `0x100000` | `E5 FE 16 00 00 10 00 F6` | `single` | H |
| Massage Mode 2 | `massage_mode_2` | `0x200000` | `E5 FE 16 00 00 20 00 E6` | `single` | H |
| TV | `tv` | `0x4000` | `E5 FE 16 00 40 00 00 C6` | `held` | M2 |
| Anti-snore | `anti_snore` | `0x8000` | `E5 FE 16 00 80 00 00 86` | `single` | M2 |
| Head Up (Back cover) | `head_up` | `0x1` | `04 02 00 00 00 01` | `held` | MX |
| Head Down (Back cover) | `head_down` | `0x2` | `04 02 00 00 00 02` | `held` | MX |
| Foot Up (Legs cover) | `foot_up` | `0x4` | `04 02 00 00 00 04` | `held` | MX |
| Foot Down (Legs cover) | `foot_down` | `0x8` | `04 02 00 00 00 08` | `held` | MX |
| Tilt Up | `tilt_up` | `0x10` | `04 02 00 00 00 10` | `held` | MX |
| Tilt Down | `tilt_down` | `0x20` | `04 02 00 00 00 20` | `held` | MX |
| Anti-snore | `anti_snore` | `0x8000` | `04 02 00 00 80 00` | `held` | MX |
| MX Memory 1 | `mx_memory1` | `0x10000` | `04 02 00 01 00 00` | `held` | MX |
| Flat | `flat` | `0x8000000` | `04 02 08 00 00 00` | `single` | MX |
| Light | `light` | `0x4000` | `04 02 00 00 40 00` | `single` | MX |
| Massage head | `massage_head` | `0x800` | `04 02 00 00 08 00` | `pulse` | MX |
| Massage foot | `massage_foot` | `0x400` | `04 02 00 00 04 00` | `pulse` | MX |
| Massage timer | `massage_timer` | `0x200` | `04 02 00 00 02 00` | `pulse` | MX |
<!-- /generated -->

- MX uses the six-byte P2 builder with no checksum and no zero-key release.
  **MX Memory 1** is an opaque held key, not a save or recall: it repeats every
  100 ms and its release only queries `00 B0`.
- Single MX keys query at +500 and +800 ms; MX massage waits 300 ms before its
  release queries.

#### Timing

- At connect, MX queries `00 B0` at +300, +600 and +900 ms; P1 layouts send one
  zero key frame for the selected selector.
- MX then polls `00 B0` five seconds after connect and every 30 seconds, through
  the diagnostic poll hook, with command priority and without renewing the idle
  timeout.
- The app has no clock writer and no reachable angle-target writer.

#### Services

The app's snooze stores 55 + 10 as minute 65 without carrying. The alarm action
requires a valid HH:MM, so an automation must normalize the time first. Phone
alarm scheduling stays outside the integration.

### Serta MP Remote

**App:** [Serta MP Remote](https://play.google.com/store/apps/details?id=com.ore.serta330) 1.1, `com.ore.serta330`

Bed type `serta_mp_remote`, one layout. `SertaMPRemoteController` adds
calibrated position feedback, pulse targets and four local memories to the
shared controller. The app has no clock writer and no alarm tables.

#### Controls

<!-- generated:keeson-app-serta-mp-remote -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| App label | Key | Mask | Frame | Behavior |
|---|---|---|---|---|
| Flat | `flat` | `0x8000000` | `E5 FE 16 00 00 00 08 FE` | `single` |
| Foot down (Legs cover) | `foot_down` | `0x8` | `E5 FE 16 08 00 00 00 FE` | `held` |
| Foot up (Legs cover) | `foot_up` | `0x4` | `E5 FE 16 04 00 00 00 02` | `held` |
| Head down (Back cover) | `head_down` | `0x2` | `E5 FE 16 02 00 00 00 04` | `held` |
| Head up (Back cover) | `head_up` | `0x1` | `E5 FE 16 01 00 00 00 05` | `held` |
| Massage pattern icon (btnLevel) | `level` | `0x100` | `E5 FE 16 00 01 00 00 05` | `single` |
| Lounge preset icon | `lounge` | `0x2000` | `E5 FE 16 00 20 00 00 E6` | `held` |
| Lumbar down (unlabeled touch area) | `lumbardown` | `0x80` | `E5 FE 16 80 00 00 00 86` | `held` |
| Lumbar up (unlabeled touch area) | `lumbarup` | `0x40` | `E5 FE 16 40 00 00 00 C6` | `held` |
| Preset M4 icon (distinct from local memory slot 4) | `m4` | `0x8000` | `E5 FE 16 00 80 00 00 86` | `single` |
| Foot massage increase | `masfootadd` | `0x400` | `E5 FE 16 00 04 00 00 02` | `single` |
| Foot massage decrease | `masfootmin` | `0x1000000` | `E5 FE 16 00 00 00 01 05` | `single` |
| Head massage increase | `masheadadd` | `0x800` | `E5 FE 16 00 08 00 00 FE` | `single` |
| Head massage decrease | `masheadmin` | `0x800000` | `E5 FE 16 00 00 80 00 86` | `single` |
| RESET-labeled remote action | `reset` | `0x8001000` | `E5 FE 16 00 10 00 08 EE` | `held` |
| Tilt down (unlabeled touch area) | `tiltdown` | `0x20` | `E5 FE 16 20 00 00 00 E6` | `held` |
| Tilt up (unlabeled touch area) | `tiltup` | `0x10` | `E5 FE 16 10 00 00 00 F6` | `held` |
| Massage TIMER / ALL OFF | `timer` | `0x200` | `E5 FE 16 00 02 00 00 04` | `single` |
| TV preset icon | `tv` | `0x4000` | `E5 FE 16 00 40 00 00 C6` | `held` |
| ZERO-G preset | `zg` | `0x1000` | `E5 FE 16 00 10 00 00 F6` | `single` |
<!-- /generated -->

The **M4** icon is a remote key, separate from local memory slot 4.

<!-- generated:keeson-serta-mp -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

#### Position targets

| Target | Head field | Foot field | Example |
|---|---|---|---|
| Back slider or `set_position` | head table value | `0x8000` | Back 30°: `E5 FE 17 6F 1B 00 80 FB` |
| Legs slider or `set_position` | `0x8000` | foot table value | Legs 15°: `E5 FE 17 00 80 0D 11 67` |
| Local memory recall | head table value | foot table value | Slot 1 default (15°/35°): `E5 FE 17 7D 0C A3 24 B5` |

#### Calibration tables

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
<!-- /generated -->

Pulse targets are `E5 FE 17`, a little-endian head pulse word, a little-endian
foot pulse word and the checksum. A slider sends `0x8000` in the other field; no
physical meaning is assumed for it.

| App label | Key | Behavior |
|-----------|-----|----------|
| Head Target Up / Down | `head_target_up`, `head_target_down` | Local held edit, ±1° every 200 ms |
| Foot Target Up / Down | `foot_target_up`, `foot_target_down` | Local held edit, ±1° every 200 ms |

- A local edit starts from the last reported angle, stays within head 0-60° and
  foot 0-45°, and writes one pulse target on release, to the current session
  only. It sends no movement or zero-key frame. A button press holds for the
  pulse count × 200 ms.
- Cancelling an edit through Home Assistant still writes its target. That write
  satisfies only the STOP that cancelled it (same scheduler, STOP epoch and
  session, including a paired group); a later genuine STOP still sends the zero
  key frame.

#### Memory

| Slot | Default head | Default foot | Options |
|------|--------------|--------------|---------|
| 1 | 15° | 35° | `serta_mp_memory_1_head`, `serta_mp_memory_1_foot` |
| 2 | 15° | 35° | `serta_mp_memory_2_head`, `serta_mp_memory_2_foot` |
| 3 | 15° | 35° | `serta_mp_memory_3_head`, `serta_mp_memory_3_foot` |
| 4 | 15° | 0° | `serta_mp_memory_4_head`, `serta_mp_memory_4_foot` |

- Memories are local targets (head 0-60°, foot 0-45°) in the options. Recall
  writes one pulse target; there is no physical save.
- The app's request state turns active 1500 ms after a recall. It completes when
  the reported angles equal the target or neither motion flag is set. It is UI
  state, not an acknowledgement; a disconnect cancels it.

#### Notifications

- Positions come from 16-byte notifications with byte 13 bit 5 clear: little-endian
  pulse words at bytes 3-4 (head) and 5-6 (foot), complemented when 32768 or
  more, converted to the nearest table degree (ties lower). Head above 15430
  reads 60° and foot above 11667 reads 45°.
- Byte 13 bits 0 and 1 are `app_head_flag` and `app_foot_flag`. The **App memory
  request** sensor (`active`/`inactive`) carries them with the memory target and
  progress attributes.
- `set_position` and `set_positions` validate back 0-60° and legs 0-45° for every
  axis and target before any write; generic angle overrides do not change this
  calibration. Covers use the same 60° and 45° limits.

### Omazz Adjusto III

**App:** [Omazz Adjusto III](https://play.google.com/store/apps/details?id=com.sfd.Omazz) 1.0.5, `com.sfd.Omazz`

Bed type `omazz_adjusto_iii`, one layout. The app has no reachable name writer,
so rename is unavailable.

#### Controls

<!-- generated:keeson-app-omazz-adjusto-iii -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| App label | Key | Mask | Frame | Behavior |
|---|---|---|---|---|
| Head Up (Back cover) | `head_up` | `0x1` | `E5 FE 16 01 00 00 00 05` | `held` |
| Head Down (Back cover) | `head_down` | `0x2` | `E5 FE 16 02 00 00 00 04` | `held` |
| Foot Up (Legs cover) | `foot_up` | `0x4` | `E5 FE 16 04 00 00 00 02` | `held` |
| Foot Down (Legs cover) | `foot_down` | `0x8` | `E5 FE 16 08 00 00 00 FE` | `held` |
| Lounge | `lounge` | `0x2000` | `E5 FE 16 00 20 00 00 E6` | `held` |
| Demonstration | `demonstration` | `0x40000000` | `E5 FE 16 00 00 00 40 C6` | `held` |
| Tv | `TV` | `0x4000` | `E5 FE 16 00 40 00 00 C6` | `held` |
| Music | `music` | `0x10000` | `E5 FE 16 00 00 01 00 05` | `held` |
| Flat | `flat` | `0x8000000` | `E5 FE 16 00 00 00 08 FE` | `single` |
| Zg | `zg` | `0x1000` | `E5 FE 16 00 10 00 00 F6` | `single` |
| Ubb | `ubb` | `0x20000` | `E5 FE 16 00 00 02 00 04` | `single` |
| Massage Head | `massage_head` | `0x800` | `E5 FE 16 00 08 00 00 FE` | `pulse` |
| Massage Timer | `massage_timer` | `0x200` | `E5 FE 16 00 02 00 00 04` | `pulse` |
| Massage Foot | `massage_foot` | `0x400` | `E5 FE 16 00 04 00 00 02` | `pulse` |
| Massage All | `massage_all` | `0x100` | `E5 FE 16 00 01 00 00 05` | `pulse` |
<!-- /generated -->

### Ergomotion app

**App:** [Ergomotion](https://play.google.com/store/apps/details?id=com.sfd.ergomotion) 1.6.4, `com.sfd.ergomotion`

Bed type `ergomotion_app` (setup label **Ergomotion (app)**). It is separate from
the `ergomotion` bed type, which uses the [Ergomotion](#ergomotion) profile.

#### Controls

<!-- generated:keeson-app-ergomotion-app -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| App label | Key | Mask | Frame | Behavior | Layouts |
|---|---|---|---|---|---|
| HeadUp (Back cover) | `head_up` | `0x1` | `E5 FE 16 01 00 00 00 05` | `held` | B1, B2, C1, D1 |
| HeadDown (Back cover) | `head_down` | `0x2` | `E5 FE 16 02 00 00 00 04` | `held` | B1, B2, C1, D1 |
| FootUp (Legs cover) | `foot_up` | `0x4` | `E5 FE 16 04 00 00 00 02` | `held` | B1, B2, C1, D1 |
| FootDown (Legs cover) | `foot_down` | `0x8` | `E5 FE 16 08 00 00 00 FE` | `held` | B1, B2, C1, D1 |
| Flat | `flat` | `0x8000000` | `E5 FE 16 00 00 00 08 FE` | `tap_zeros` | B1, B2, C1, D1 |
| Timer | `timer` | `0x200` | `E5 FE 16 00 02 00 00 04` | `tap_zeros` | B1, B2, C1, D1 |
| Zg | `zg` | `0x1000` | `E5 FE 16 00 10 00 00 F6` | `tap_zeros` | B1, B2, C1, D1 |
| MasHeadAdd | `masheadadd` | `0x800` | `E5 FE 16 00 08 00 00 FE` | `tap_zeros` | B1, B2, C1, D1 |
| MasFootAdd | `masfootadd` | `0x400` | `E5 FE 16 00 04 00 00 02` | `tap_zeros` | B1, B2, C1, D1 |
| Reset | `reset` | `0x8001000` | `E5 FE 16 00 10 00 08 EE` | `held_zeros` | B1, B2, C1, D1 |
| Level | `level` | `0x100` | `E5 FE 16 00 01 00 00 05` | `tap_zeros` | B1, C1, D1 |
| Lounge | `lounge` | `0x2000` | `E5 FE 16 00 20 00 00 E6` | `held_zeros` | B1, C1, D1 |
| Tv | `tv` | `0x4000` | `E5 FE 16 00 40 00 00 C6` | `held_zeros` | B1, C1, D1 |
| Level1 | `level1` | `0x80000` | `E5 FE 16 00 00 08 00 FE` | `tap_zeros` | B2 |
| Level2 | `level2` | `0x100000` | `E5 FE 16 00 00 10 00 F6` | `tap_zeros` | B2 |
| Level3 | `level3` | `0x200000` | `E5 FE 16 00 00 20 00 E6` | `tap_zeros` | B2 |
| Light | `light` | `0x20000` | `E5 FE 16 00 00 02 00 04` | `tap_zeros` | C1, D1 |
| MasFootMin | `masfootmin` | `0x1000000` | `E5 FE 16 00 00 00 01 05` | `tap_zeros` | C1, D1 |
| MasHeadMin | `masheadmin` | `0x800000` | `E5 FE 16 00 00 80 00 86` | `tap_zeros` | C1, D1 |
| TiltUp | `tiltup` | `0x10` | `E5 FE 16 10 00 00 00 F6` | `held_zeros` | D1 |
| TiltDown | `tiltdown` | `0x20` | `E5 FE 16 20 00 00 00 E6` | `held_zeros` | D1 |
| LumbarUp | `lumbarup` | `0x40` | `E5 FE 16 40 00 00 00 C6` | `held_zeros` | D1 |
| LumbarDown | `lumbardown` | `0x80` | `E5 FE 16 80 00 00 00 86` | `held_zeros` | D1 |
<!-- /generated -->

### ROW Control

**App:** [ROW Control](https://play.google.com/store/apps/details?id=com.sfd.row) 2.0, `com.sfd.row`

Bed type `row_control`. The Zero-G Box layout has no **App timer status** sensor.

#### Controls

<!-- generated:keeson-app-row-control -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| App label | Key | Mask | Frame | Behavior | Layouts |
|---|---|---|---|---|---|
| Reset | `reset` | `0x8001000` | `E5 FE 16 00 10 00 08 EE` | `held` | Elevate, Lifestyle, Curve |
| Head Up (Back cover) | `head_up` | `0x1` | `E5 FE 16 01 00 00 00 05` | `held` | Elevate, Lifestyle, Curve, Lifestyle Plus, Zero-G Box |
| Head Down (Back cover) | `head_down` | `0x2` | `E5 FE 16 02 00 00 00 04` | `held` | Elevate, Lifestyle, Curve, Lifestyle Plus, Zero-G Box |
| Foot Up (Legs cover) | `foot_up` | `0x4` | `E5 FE 16 04 00 00 00 02` | `held` | Elevate, Lifestyle, Curve, Lifestyle Plus, Zero-G Box |
| Foot Down (Legs cover) | `foot_down` | `0x8` | `E5 FE 16 08 00 00 00 FE` | `held` | Elevate, Lifestyle, Curve, Lifestyle Plus, Zero-G Box |
| Anti Snore | `anti_snore` | `0x8000` | `E5 FE 16 00 80 00 00 86` | `held` | Elevate, Lifestyle, Curve, Lifestyle Plus, Zero-G Box |
| Tv | `tv` | `0x4000` | `E5 FE 16 00 40 00 00 C6` | `held` | Elevate, Lifestyle, Curve, Lifestyle Plus, Zero-G Box |
| Lounge | `lounge` | `0x2000` | `E5 FE 16 00 20 00 00 E6` | `held` | Elevate, Lifestyle, Curve, Lifestyle Plus |
| Flat | `flat` | `0x8000000` | `E5 FE 16 00 00 00 08 FE` | `single` | Elevate, Lifestyle, Curve, Lifestyle Plus, Zero-G Box |
| Zero G | `zero_g` | `0x1000` | `E5 FE 16 00 10 00 00 F6` | `single` | Elevate, Lifestyle, Curve, Lifestyle Plus, Zero-G Box |
| Timer | `timer` | `0x200` | `E5 FE 16 00 02 00 00 04` | `pulse` | Elevate, Lifestyle, Curve, Lifestyle Plus, Zero-G Box |
| Massage Head | `massage_head` | `0x800` | `E5 FE 16 00 08 00 00 FE` | `pulse` | Elevate, Lifestyle, Curve, Lifestyle Plus |
| Massage Foot | `massage_foot` | `0x400` | `E5 FE 16 00 04 00 00 02` | `pulse` | Elevate, Lifestyle, Curve, Lifestyle Plus |
| Light | `light` | `0x20000` | `E5 FE 16 00 00 02 00 04` | `single` | Curve, Lifestyle Plus, Zero-G Box |
| Lounge | `lounge` | `0x10000` | `E5 FE 16 00 00 01 00 05` | `held` | Zero-G Box |
| Massage Head | `massage_head` | `0x50` | `E5 FE 16 50 00 00 00 B6` | `held` | Zero-G Box |
| Massage Foot | `massage_foot` | `0xa0` | `E5 FE 16 A0 00 00 00 66` | `held` | Zero-G Box |
<!-- /generated -->

### Ergo Slim

**App:** [Ergo Slim](https://play.google.com/store/apps/details?id=com.sfd.slim) 1.3, `com.sfd.slim`

Bed type `ergo_slim`. The report proves a clock write when the session starts but
no delay before it, so the clock is written at connect.

#### Controls

<!-- generated:keeson-app-ergo-slim -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| App label | Key | Mask | Frame | Behavior | Layouts |
|---|---|---|---|---|---|
| Reset | `reset` | `0x8001000` | `E5 FE 16 00 10 00 08 EE` | `held` | A |
| Head Up (Back cover) | `head_up` | `0x1` | `E5 FE 16 01 00 00 00 05` | `held` | A, B, C |
| Head Down (Back cover) | `head_down` | `0x2` | `E5 FE 16 02 00 00 00 04` | `held` | A, B, C |
| Foot Up (Legs cover) | `foot_up` | `0x4` | `E5 FE 16 04 00 00 00 02` | `held` | A, B, C |
| Foot Down (Legs cover) | `foot_down` | `0x8` | `E5 FE 16 08 00 00 00 FE` | `held` | A, B, C |
| Massage Head Min | `massage_head_min` | `0x800000` | `E5 FE 16 00 00 80 00 86` | `pulse` | A |
| Massage Foot Min | `massage_foot_min` | `0x1000000` | `E5 FE 16 00 00 00 01 05` | `pulse` | A |
| Level | `level` | `0x2000000` | `E5 FE 16 00 00 00 02 04` | `single` | A |
| Zero Gravity | `zero_gravity` | `0x1000` | `E5 FE 16 00 10 00 00 F6` | `single` | A, B, C |
| Flat | `flat` | `0x8000000` | `E5 FE 16 00 00 00 08 FE` | `pulse` | A, B, C |
| Tv | `tv` | `0x4000` | `E5 FE 16 00 40 00 00 C6` | `held` | A, B |
| Lounge | `lounge` | `0x2000` | `E5 FE 16 00 20 00 00 E6` | `held` | A, B |
| Light | `light` | `0x20000` | `E5 FE 16 00 00 02 00 04` | `single` | A |
| Massage Head | `massage_head` | `0x800` | `E5 FE 16 00 08 00 00 FE` | `pulse` | B, C |
| Massage Timer | `massage_timer` | `0x200` | `E5 FE 16 00 02 00 00 04` | `pulse` | B, C |
| Massage Foot | `massage_foot` | `0x400` | `E5 FE 16 00 04 00 00 02` | `pulse` | B, C |
| Ubb | `ubb` | `0x20000` | `E5 FE 16 00 00 02 00 04` | `single` | B, C |
| Massage All | `massage_all` | `0x100` | `E5 FE 16 00 01 00 00 05` | `pulse` | B |
| Music | `music` | `0x10000` | `E5 FE 16 00 00 01 00 05` | `held` | B |
| Anti Snore | `anti_snore` | `0x8000` | `E5 FE 16 00 80 00 00 86` | `held` | B |
| M3 Out | `m3_out` | `0x10` | `E5 FE 16 10 00 00 00 F6` | `held` | C |
| M3 In | `m3_in` | `0x20` | `E5 FE 16 20 00 00 00 E6` | `held` | C |
| Memory 4 | `memory_4` | `0x8000` | `E5 FE 16 00 80 00 00 86` | `held` | C |
| Memory 2 | `memory_2` | `0x2000` | `E5 FE 16 00 20 00 00 E6` | `held` | C |
| Memory 3 | `memory_3` | `0x4000` | `E5 FE 16 00 40 00 00 C6` | `held` | C |
<!-- /generated -->

### TEMPUR AU

**App:** [TEMPUR AU](https://play.google.com/store/apps/details?id=com.sfd.tempur_au) 1.6, `com.sfd.tempur_au`

Bed type `tempur_au`. Memory Level 1-3 on B2 are opaque keys.

#### Controls

<!-- generated:keeson-app-tempur-au -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| App label | Key | Mask | Frame | Behavior | Layouts |
|---|---|---|---|---|---|
| Head Up (Back cover) | `head_up` | `0x1` | `E5 FE 16 01 00 00 00 05` | `held` | B1, B2, C1, D1, E1 |
| Head Down (Back cover) | `head_down` | `0x2` | `E5 FE 16 02 00 00 00 04` | `held` | B1, B2, C1, D1, E1 |
| Foot Up (Legs cover) | `foot_up` | `0x4` | `E5 FE 16 04 00 00 00 02` | `held` | B1, B2, C1, D1, E1 |
| Foot Down (Legs cover) | `foot_down` | `0x8` | `E5 FE 16 08 00 00 00 FE` | `held` | B1, B2, C1, D1, E1 |
| Level | `level` | `0x100` | `E5 FE 16 00 01 00 00 05` | `single` | B1, C1, D1 |
| Timer | `timer` | `0x200` | `E5 FE 16 00 02 00 00 04` | `pulse` | B1, B2, C1, D1, E1 |
| Massage Foot Add | `massage_foot_add` | `0x400` | `E5 FE 16 00 04 00 00 02` | `pulse` | B1, B2, C1, D1, E1 |
| Massage Head Add | `massage_head_add` | `0x800` | `E5 FE 16 00 08 00 00 FE` | `pulse` | B1, B2, C1, D1, E1 |
| Zero G | `zero_g` | `0x1000` | `E5 FE 16 00 10 00 00 F6` | `single` | B1, B2, C1, D1, E1 |
| Lounge | `lounge` | `0x2000` | `E5 FE 16 00 20 00 00 E6` | `held` | B1, C1, D1, E1 |
| Tv | `tv` | `0x4000` | `E5 FE 16 00 40 00 00 C6` | `held` | B1, C1, D1, E1 |
| Flat | `flat` | `0x8000000` | `E5 FE 16 00 00 00 08 FE` | `single` | B1, B2, C1, D1, E1 |
| Reset | `reset` | `0x8001000` | `E5 FE 16 00 10 00 08 EE` | `held` | B1, B2, C1, D1, E1 |
| Memory Level 1 | `memory_level_1` | `0x80000` | `E5 FE 16 00 00 08 00 FE` | `single` | B2 |
| Memory Level 2 | `memory_level_2` | `0x100000` | `E5 FE 16 00 00 10 00 F6` | `single` | B2 |
| Memory Level 3 | `memory_level_3` | `0x200000` | `E5 FE 16 00 00 20 00 E6` | `single` | B2 |
| Light | `light` | `0x20000` | `E5 FE 16 00 00 02 00 04` | `single` | C1, D1, E1 |
| Massage Head Decrease | `massage_head_decrease` | `0x800000` | `E5 FE 16 00 00 80 00 86` | `pulse` | C1, D1 |
| Massage Foot Decrease | `massage_foot_decrease` | `0x1000000` | `E5 FE 16 00 00 00 01 05` | `pulse` | C1, D1 |
| Tilt Up | `tilt_up` | `0x10` | `E5 FE 16 10 00 00 00 F6` | `held` | D1 |
| Tilt Down | `tilt_down` | `0x20` | `E5 FE 16 20 00 00 00 E6` | `held` | D1 |
| Lumbar Up | `lumbar_up` | `0x40` | `E5 FE 16 40 00 00 00 C6` | `held` | D1, E1 |
| Lumbar Down | `lumbar_down` | `0x80` | `E5 FE 16 80 00 00 00 86` | `held` | D1, E1 |
| Anti Snooze | `anti_snooze` | `0x8000` | `E5 FE 16 00 80 00 00 86` | `single` | E1 |
| Music | `music` | `0x10000` | `E5 FE 16 00 00 01 00 05` | `single` | E1 |
<!-- /generated -->

### Controller profiles

These bed types keep their own key tables, sessions and timing in their
controllers; their profile holds only the frame, which the codec builds. Most are
documented below; Malouf legacy OKIN, Sleepy's BOX15 and AdjustaMattress share a
guide with frames of other families and keep it.

<!-- generated:keeson-controllers -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Profile | Bed type | Frame | Word `0x1` | Zero word | Guide |
|---|---|---|---|---|---|
| Glideaway Motion | `glideaway_motion` | K1 `E6`, little-endian, side `00` | `E6 FE 16 01 00 00 00 00 04` | `E6 FE 16 00 00 00 00 00 05` | [Glideaway Motion](#glideaway-motion) |
| Malouf legacy OKIN | `malouf_legacy_okin` | K1 `E6`, little-endian, side `00` | `E6 FE 16 01 00 00 00 00 04` | `E6 FE 16 00 00 00 00 00 05` | [Malouf](malouf.md) |
| Sleepy's BOX15 | `sleepys_box15` | K1 `E6`, little-endian, side `00` | `E6 FE 16 01 00 00 00 00 04` | `E6 FE 16 00 00 00 00 00 05` | [Sleepy's](sleepys.md) |
| Scott Living | `scott_living` | K1 `E6`, little-endian, side `01` | `E6 FE 16 01 00 00 00 01 03` | `E6 FE 16 00 00 00 00 01 04` | [Scott Living](#scott-living) |
| AdjustaMattress P1 | `adjustamattress`, model P1 | K1 `E6`, little-endian, side `00` | `E6 FE 16 01 00 00 00 00 04` | `E6 FE 16 00 00 00 00 00 05` | [AdjustaMattress](adjustamattress.md) |
| AdjustaMattress P2 | `adjustamattress`, model P2 | K1 `E5`, big-endian | `E5 FE 16 00 00 00 01 05` | `E5 FE 16 00 00 00 00 06` | [AdjustaMattress](adjustamattress.md) |
| SBI | `sbi` | K1 `E5`, little-endian (A/B: `E6`, side `01`/`02`) | `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` | [SBI / Q-Plus](#sbi--q-plus-costco) |
| Rondure | `rondure` | K1 `E5`, little-endian (A/B: `E6`, side `01`/`02`) | `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` | [Rondure](#rondure) |
| Cool Base | `coolbase` | K1 `E5`, little-endian | `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` | [Cool Base](#cool-base) |
| BF | `bf` | K1 `E5`, big-endian | `E5 FE 16 00 00 00 01 05` | `E5 FE 16 00 00 00 00 06` | [BF and Cherish](#bf-and-cherish) |
| Cherish | `cherish` | K1 `E5`, big-endian | `E5 FE 16 00 00 00 01 05` | `E5 FE 16 00 00 00 00 06` | [BF and Cherish](#bf-and-cherish) |
| Comfort Enhancements | `comfort_enhancements` | K1 `E5`, big-endian | `E5 FE 16 00 00 00 01 05` | `E5 FE 16 00 00 00 00 06` | [Comfort Enhancements](#comfort-enhancements) |
<!-- /generated -->

### Glideaway Motion

**App:** [Glideaway Motion](https://play.google.com/store/apps/details?id=com.ore.bedding.glideawaymontion) 1.0.3 (code 11), `com.ore.bedding.glideawaymontion`

Choose **Glideaway Motion / Montion app** and the model selected in the Android
app (the archive label misspells Motion as "Montion"). It is separate from the
legacy **Okin ORE (A5 5A)** profile; existing legacy entries are not migrated,
because the app uses different bytes and does not prove which hardware an
existing entry controls. Hardware is unverified.

#### Setup

- The app scans without a name or service filter and needs a manual model
  choice, so the integration is added manually with the model as the protocol
  variant. Shared FFE services, names and GM descriptions do not identify a
  model, and no pairing, PIN, status query or clock write is sent on connect.
- The model owns the layout and extras; generic motor count, massage, angle
  sensing and refresh settings are hidden. The motor pulse count still sets a
  cover movement's duration.
- Two physical addresses may use native paired-bed routing; there is no
  app-proven single-address side protocol.
- It writes to FFE9 in FFE5 and subscribes to FFE4 in FFE0, with response only
  when the characteristic offers `write` alone (the app leaves Android's write
  type unchanged).

| App model | Description | Covers | Extra controls |
| --- | --- | --- | --- |
| MOTION 400 | GM-A4Z | Back/head, feet, head + feet | None |
| MOTION 450 | GM-A450Z | Back/head, feet, bed height | None |
| MOTION 500 | GM-A5Z | Back/head, feet, head + feet, bed height | Light and massage |
| MOTION 600 | GM-A6Z | Back/head, feet, neck tilt, bed height | Light and massage |

Every model has Flat, Anti-snore, Zero gravity, Memory A/B recall and save, a
bed alarm sensor and a Refresh alarm button. Models 500 and 600 add a
toggle-only light button, massage intensity and wave up/down, timer cycle,
massage off and a massage timer sensor. There is no light-state feedback,
direct massage level, position feedback or angle slider.

#### Controls

<!-- generated:keeson-glideaway -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Control | Word | Frame |
|---|---|---|
| Back/head up | `0x00000001` | `E6 FE 16 01 00 00 00 00 04` |
| Back/head down | `0x00000002` | `E6 FE 16 02 00 00 00 00 03` |
| Feet up | `0x00000004` | `E6 FE 16 04 00 00 00 00 01` |
| Feet down | `0x00000008` | `E6 FE 16 08 00 00 00 00 FD` |
| Head + feet up | `0x00000005` | `E6 FE 16 05 00 00 00 00 00` |
| Head + feet down | `0x0000000A` | `E6 FE 16 0A 00 00 00 00 FB` |
| Neck tilt up | `0x00000010` | `E6 FE 16 10 00 00 00 00 F5` |
| Neck tilt down | `0x00000020` | `E6 FE 16 20 00 00 00 00 E5` |
| Bed height up | `0x00000040` | `E6 FE 16 40 00 00 00 00 C5` |
| Bed height down | `0x00000080` | `E6 FE 16 80 00 00 00 00 85` |
| Flat | `0x08000000` | `E6 FE 16 00 00 00 08 00 FD` |
| Anti snore | `0x00008000` | `E6 FE 16 00 80 00 00 00 85` |
| Zero g | `0x00001000` | `E6 FE 16 00 10 00 00 00 F5` |
| Memory 1 | `0x00002000` | `E6 FE 16 00 20 00 00 00 E5` |
| Memory 2 | `0x00004000` | `E6 FE 16 00 40 00 00 00 C5` |
| Light toggle (500/600) | `0x00020000` | `E6 FE 16 00 00 02 00 00 03` |
| Massage intensity up (500/600) | `0x00000C00` | `E6 FE 16 00 0C 00 00 00 F9` |
| Massage intensity down (500/600) | `0x01800000` | `E6 FE 16 00 00 80 01 00 84` |
| Massage wave up (500/600) | `0x10000000` | `E6 FE 16 00 00 00 10 00 F5` |
| Massage wave down (500/600) | `0x04000000` | `E6 FE 16 00 00 00 04 00 01` |
| Massage timer (500/600) | `0x00000200` | `E6 FE 16 00 02 00 00 00 03` |
| Massage off (500/600) | `0x00000100` | `E6 FE 16 00 01 00 00 00 04` |
| Release | `0x00000000` | `E6 FE 16 00 00 00 00 00 05` |
<!-- /generated -->

For longer holds use `adjustable_bed.hold_control` with `back_up/down`,
`feet_up/down`, `both_up/down`, `bed_height_up/down`, `tilt_up/down` (as the
model has them), `flat`, `anti_snore`, `zero_g`, `memory_1`, `memory_2`, and on
500/600 `light`, `massage_intensity_up/down`, `massage_wave_up/down`,
`massage_timer` and `massage_off`. Holds accept 0.1-30 seconds; a memory recall
must be shorter than five seconds. `save_preset` slot 1 or 2 (or the Save Memory
buttons) holds the recall frame for 5.2 seconds; the app's saved toast is local,
not an acknowledgement.

#### Timing

| Operation | Timing |
| --- | --- |
| Held refresh | Every 300 ms, counting the write time |
| Cover movement | Configured pulse count × 300 ms, as a monotonic deadline |
| Release | Zero frame at +300 and +600 ms, both attempted even if the first fails |
| Preset, recall, light and massage buttons | One 300 ms press |
| Memory save | 5.2 second hold |
| Alarm set | Clock, 300 ms wait, alarm |
| Refresh alarm | `E2 80 03 00 9A` twice, 200 ms apart |

No held write starts after the deadline. Cancellation sends the same release
pair with fresh cancel events and keeps the command lane until it finishes.

#### Alarm and clock

`adjustable_bed.glideaway_set_alarm` takes `device_id`, `enabled`, optional
`side`, `time` (required when enabling) and `wake_mode` (`none`, `memory_1`,
`memory_2`). Disabling needs no time, and every target must be this profile.
`adjustable_bed.sync_clock` sends only the clock.

```yaml
action: adjustable_bed.glideaway_set_alarm
data:
  device_id: YOUR_DEVICE_ID
  enabled: true
  time: "06:30:00"
  wake_mode: memory_1
```

The app's calendar encoding is kept as shipped:

- The clock frame carries year minus 1900, zero-based month, day minus one and
  hour minus one (midnight becomes `FF`), then minute and second.
- The alarm frame is `ED 80 03`, hour, minute, weekday bit, wake byte, eight
  zeros and the checksum. The public hour is the wire hour (0-23); the app's
  1-12 wheel sends its zero-based index plus AM/PM × 12.
- For weekday `d` (Sunday 1 to Saturday 7), a time at or before now uses bit
  `d-1` and a later time bit `d%7`. There is no weekday selector.
- Wake bytes are `00` (none), `11` (Memory A) and `13` (Memory B). Disabling
  writes zero fields.

Physical alarm and clock behavior, especially at midnight and weekday
boundaries, needs real-user confirmation.

#### Notifications

- The massage timer comes from byte 8 of `E7 FE` (length 10 or more), byte 14
  of `ED FE` (16 or more), byte 19 of `F4 FE` (more than 20), or byte 19 of a
  fragmented packet starting `F4`. Raw `FF` is zero; otherwise the value is
  multiplied by ten only when the previous displayed minutes differ from the raw
  byte, as the app does. The raw value is an attribute.
- `ED 80` alarm replies use bytes 3-6; the alarm sensor reports enabled, hour,
  minute and wake mode. Unknown wake values map to none.
- No incoming checksum is checked. Fragments are buffered per controller,
  cleared on a recognized frame or disconnect and expired after two seconds.

#### Evidence

Accepted report row068, XAPK set SHA-256
`7eb30a03349b9d9b9bffc43e2dafdb672c422fdd70e16b3e2c9ec2a55730c315`; see the
[discovery ledger](../apk-analysis/dispositions/row068-glideaway-motion.md). The
app leaves combined movement and the light without a release and lets streams
outlive the page; the integration bounds every hold and releases those too,
with the same zero frame.

### Scott Living

**App:** Scott Living, `com.keeson.scottlivingrelease`

Bed type `scott_living`, selected manually: it shares the FFE5 service with
other Keeson beds and has no distinct name. It writes FFE9 and subscribes to
FFE4. The side byte is always `01`. There is no accepted report; the frames are
the pre-v5 controller's.

#### Controls

<!-- generated:keeson-scott-living -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Command | Word | Frame |
|---|---|---|
| Motor Head Up | `0x00000001` | `E6 FE 16 01 00 00 00 01 03` |
| Motor Head Down | `0x00000002` | `E6 FE 16 02 00 00 00 01 02` |
| Motor Feet Up | `0x00000004` | `E6 FE 16 04 00 00 00 01 00` |
| Motor Feet Down | `0x00000008` | `E6 FE 16 08 00 00 00 01 FC` |
| Motor Tilt Up | `0x00000010` | `E6 FE 16 10 00 00 00 01 F4` |
| Motor Tilt Down | `0x00000020` | `E6 FE 16 20 00 00 00 01 E4` |
| Motor Lumbar Up | `0x00000040` | `E6 FE 16 40 00 00 00 01 C4` |
| Motor Lumbar Down | `0x00000080` | `E6 FE 16 80 00 00 00 01 84` |
| Memory 1 | `0x00000100` | `E6 FE 16 00 01 00 00 01 03` |
| Massage Timer | `0x00000200` | `E6 FE 16 00 02 00 00 01 02` |
| Massage Foot Up | `0x00000400` | `E6 FE 16 00 04 00 00 01 00` |
| Massage Head Up | `0x00000800` | `E6 FE 16 00 08 00 00 01 FC` |
| Zero G | `0x00001000` | `E6 FE 16 00 10 00 00 01 F4` |
| Memory 2 | `0x00002000` | `E6 FE 16 00 20 00 00 01 E4` |
| Memory 3 | `0x00004000` | `E6 FE 16 00 40 00 00 01 C4` |
| Anti Snore | `0x00008000` | `E6 FE 16 00 80 00 00 01 84` |
| Memory 4 | `0x00010000` | `E6 FE 16 00 00 01 00 01 03` |
| Light | `0x00020000` | `E6 FE 16 00 00 02 00 01 02` |
| Massage Head Down | `0x00800000` | `E6 FE 16 00 00 80 00 01 84` |
| Massage Foot Down | `0x01000000` | `E6 FE 16 00 00 00 01 01 03` |
| Preset Flat | `0x08000000` | `E6 FE 16 00 00 00 08 01 FC` |
| Stop | `0x00000000` | `E6 FE 16 00 00 00 00 01 04` |
<!-- /generated -->

Movement repeats at the configured pulse count and delay (default 10 × 100 ms)
and always ends with the zero frame. Presets, light and massage are single
frames. Memory 3 and TV share one word.

### Malouf legacy OKIN, Sleepy's BOX15, AdjustaMattress P1 and P2

These routes build their E6 (AdjustaMattress P2: big-endian E5) frames through
this codec and keep the rest of their guides:

- [Malouf legacy OKIN](malouf.md) (`malouf_legacy_okin`): Malouf words, side
  byte `00`; the configured pulse settings, then the zero frame.
- [Sleepy's BOX15](sleepys.md) (`sleepys_box15`): the motor byte is the word's
  first byte, the preset bytes its second and fourth.
- [AdjustaMattress](adjustamattress.md) (`adjustamattress`): models P1 (E6) and
  P2 (big-endian E5). Models P3 and P4 send Okin N-frames.

[SIMMONS](okin-nframe.md#simmons) names starting `okin` also send the E6 frame
through `codec.frame`; that bed type is a profile of the Okin N-frame family.

### FurniMove

FurniMove builds its gateway
(`E5 FE 16`), plain (`04 02`) and dot (`05 02`) frames through this codec too and
keeps its [own guide](furnimove.md), because its handset catalog is its profile.

### SBI / Q-Plus (Costco)

**Status:** ❓ Needs testing

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

#### Known Models

- Q-Plus adjustable bed bases (sold through Costco)
- SBI (South Bay International) branded beds

#### Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | Q-Plus | `com.sbi.costco` |

#### Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (4 motors: head, foot, tilt, lumbar) |
| Position Feedback | ✅ (head 0–60°, foot 0–32° via pulse lookup) |
| Memory Presets | ✅ (2 slots) |
| Factory Presets | ✅ (Flat, Zero-G, TV) |
| Massage | ✅ (3 modes, head/foot/lumbar zones) |
| Light Control | ✅ (toggle) |
| Dual Bed Control | ✅ (A/B/Both modes for split-king) |

#### Protocol Details

**Service UUID:** Uses discovery (typically FFE5)
**Write Characteristic:** `0000ffe9-0000-1000-8000-00805f9b34fb`
**Notify Characteristic:** `0000ffe4-0000-1000-8000-00805f9b34fb`
**Alternate (Nordic UART):** `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
**Format:** 8 or 9-byte packets with inverted sum checksum

#### Detection

No auto-detection - must be manually selected during setup.

Note: SBI shares service UUIDs with Keeson and other beds. Without a unique identifier, it cannot be automatically distinguished.

#### Protocol Variants

SBI supports split-king (dual bed) configurations with three modes:

| Variant | Format | Header | Side Byte | Description |
|---------|--------|--------|-----------|-------------|
| Both | 8 bytes | 0xE5 | N/A | Controls both sides simultaneously |
| Side A | 9 bytes | 0xE6 | 0x01 | Controls left/A side only |
| Side B | 9 bytes | 0xE6 | 0x02 | Controls right/B side only |

#### Packet Format

##### 8-byte format (Both mode)

```text
[0xE5, 0xFE, 0x16, cmd0, cmd1, cmd2, cmd3, checksum]
```

##### 9-byte format (A/B mode)

```text
[0xE6, 0xFE, 0x16, cmd0, cmd1, cmd2, cmd3, side, checksum]
```

Where:
- Bytes 0-2 = Header
- Bytes 3-6 = Command bytes (32-bit little-endian value)
- Byte 7 (9-byte only) = Side selector (1=A, 2=B)
- Last byte = Checksum: `(~sum(bytes 0 to n-1)) & 0xFF`

#### Commands

##### Motor Control (cmd0 byte)

| Action | Value | Notes |
|--------|-------|-------|
| Head Up | 0x01 | Hold to move |
| Head Down | 0x02 | Hold to move |
| Foot Up | 0x04 | Hold to move |
| Foot Down | 0x08 | Hold to move |
| Tilt Up | 0x10 | Hold to move |
| Tilt Down | 0x20 | Hold to move |
| Lumbar Up | 0x40 | Hold to move |
| Lumbar Down | 0x80 | Hold to move |
| Stop | 0x00 | All zeros |

##### Preset Commands

| Action | Full Value | cmd bytes |
|--------|------------|-----------|
| Flat | 0x08000000 | cmd3=0x08 |
| Zero-G | 0x00001000 | cmd1=0x10 |
| Reset | 0x08001000 | cmd1=0x10, cmd3=0x08 |
| Memory 1 | 0x00002000 | cmd1=0x20 |
| Memory 2 | 0x00004000 | cmd1=0x40 |
| TV | 0x00008000 | cmd1=0x80 |

##### Light Command

| Action | Full Value | cmd bytes |
|--------|------------|-----------|
| Light Toggle | 0x00020000 | cmd2=0x02 |

##### Massage Commands

| Action | Full Value | cmd bytes |
|--------|------------|-----------|
| Massage Level | 0x00000100 | cmd1=0x01 |
| Foot Massage | 0x00000400 | cmd1=0x04 |
| Head Massage | 0x00000800 | cmd1=0x08 |
| Mode 1 | 0x00100000 | cmd2=0x10 |
| Mode 2 | 0x00200000 | cmd2=0x20 |
| Mode 3 | 0x00080000 | cmd2=0x08 |
| Lumbar Massage | 0x00400000 | cmd2=0x40 |

#### Position Feedback

**Notify Characteristic:** `0000ffe4-0000-1000-8000-00805f9b34fb`

Notifications are 16+ byte packets. Position data is extracted from:
- **Bytes 3-4:** Head pulse count (little-endian 16-bit)
- **Bytes 5-6:** Foot pulse count (little-endian 16-bit)

Pulse values are converted to angles via calibrated lookup tables from the APK.

##### Head Angle (0-60 degrees)

Pulse values map to angles using a 61-entry lookup table:

```
[0, 327, 577, 855, 1148, 1676, 2083, 2401, 2711, 3020, 3402, 3679, 4019, 4529,
 4864, 5262, 5633, 6024, 6453, 6826, 7239, 7611, 8015, 8423, 8862, 9240, 9632,
 10029, 10404, 10840, 11245, 11640, 11976, 12351, 12752, 13106, 13511, 13819,
 14169, 14518, 14901, 15217, 15556, 15856, 16177, 16530, 16788, 17118, 17389,
 17700, 18000, 18268, 18481, 18767, 19035, 19260, 19487, 19757, 19970, 20164, 20413]
```

##### Foot Angle (0-32 degrees)

Pulse values map to angles using a 33-entry lookup table:

```
[0, 570, 784, 968, 1150, 1372, 1653, 1837, 2062, 2283, 2494, 2755, 3015, 3290,
 3578, 3819, 4039, 4261, 4544, 4895, 5170, 5461, 5723, 6020, 6334, 6631, 6922,
 7243, 7546, 7810, 8174, 8546, 8718]
```

##### Pulse Inversion

Pulse values >= 32768 are inverted: `pulse = 65535 - pulse`

#### Command Timing

| Operation | Repeat Count | Delay | Notes |
|-----------|-------------|-------|-------|
| Motor movement | 10 | 100ms | Continuous while held |
| Presets | 1 | - | Single command |
| Massage toggle | 1 | - | Single command |
| Light toggle | 1 | - | Single command |
| Stop | 1 | - | Always sent after movement |

#### Notes

1. SBI beds are sold through Costco under the Q-Plus brand name.

2. The app supports both BLE and Classic Bluetooth connections. This integration uses BLE only.

3. Split-king beds use the A/B/Both variant modes. Configure the appropriate variant during setup.

4. The position feedback feature requires enabling angle sensing in the integration options.

5. The app includes additional features (weather, alarms, sleep tracking) that are not relevant to bed control.

6. Multiple remote layouts are supported in the app (H, M, M2, M3, MX) with varying button counts.

### Rondure

**Status:** ❓ Needs testing

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

#### Known Models

- 1500 Tilt Base (internal name: Rondure Hump)

#### Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | 1500 Tilt Base Remote | `com.sfd.rondure_hump` |

#### Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (4 motors: head, foot, tilt, lumbar) |
| Split-King | ✅ (independent side control) |
| Position Feedback | ❌ |
| Memory Presets | ❌ |
| Factory Presets | ✅ (Flat, Zero-G, TV/Anti-Snore) |
| Massage | ✅ (head, foot, lumbar zones) |
| Lights | ✅ |

#### Protocol Details

**Service UUID:** `0000ffe0-0000-1000-8000-00805f9b34fb`
**Write Characteristic:** `0000ffe9-0000-1000-8000-00805f9b34fb`
**Read Characteristic:** `0000ffe4-0000-1000-8000-00805f9b34fb`
**Alternative:** Nordic UART Service (6e400001-...)
**Format:** 8-byte (both sides) or 9-byte (single side) packets with checksum

#### Detection

Manual bed type selection required. The service UUID `0000ffe0-...` is shared with many other bed types (Solace, Octo, etc.), so auto-detection is not possible.

#### Packet Format

##### Both Sides (8 bytes)

```text
[0xE5, 0xFE, 0x16, cmd[0], cmd[1], cmd[2], cmd[3], checksum]
```

##### Single Side (9 bytes)

```text
[0xE6, 0xFE, 0x16, cmd[0], cmd[1], cmd[2], cmd[3], side, checksum]
```

Where:
- `0xE5` header = both sides, `0xE6` header = single side
- `0xFE, 0x16` = fixed protocol bytes
- `cmd[0-3]` = 32-bit command in little-endian order
- `side` = `0x01` for Side A, `0x02` for Side B
- `checksum` = bitwise NOT of sum of all preceding bytes

##### Checksum Calculation

```python
checksum = (~sum(packet[:-1])) & 0xFF
```

#### Commands

Commands are 32-bit values sent in little-endian byte order.

##### Motor Control (Hold to move)

| Action | Command | Notes |
|--------|---------|-------|
| Head Up | `0x00000001` | Continuous while held |
| Head Down | `0x00000002` | Continuous while held |
| Foot Up | `0x00000004` | Continuous while held |
| Foot Down | `0x00000008` | Continuous while held |
| Tilt Up | `0x00000010` | Continuous while held |
| Tilt Down | `0x00000020` | Continuous while held |
| Lumbar Up | `0x00000040` | Continuous while held |
| Lumbar Down | `0x00000080` | Continuous while held |
| Stop | `0x00000000` | Stop all motors |

##### Presets (Single press)

| Action | Command | Notes |
|--------|---------|-------|
| Flat | `0x08000000` | Go to flat position |
| Zero-G | `0x00001000` | Zero gravity position |
| TV/Anti-Snore | `0x00008000` | TV or anti-snore position |
| Timer/Level | `0x00000100` | Timer toggle |
| Read Preset | `0x00002000` | Reading position |
| Music/Memory | `0x00004000` | Music or memory preset |

##### Massage Control

| Action | Command |
|--------|---------|
| Head Massage | `0x00000800` |
| Foot Massage | `0x00000400` |
| Lumbar Massage | `0x00400000` |
| Massage Mode 1 | `0x00100000` |
| Massage Mode 2 | `0x00200000` |
| Massage Mode 3 | `0x00080000` |

##### Light Control

| Action | Command |
|--------|---------|
| Light Toggle | `0x00020000` |

#### Configuration

##### Side Selection (Split-King)

For split-king beds, configure the protocol variant:

| Variant | Value | Description |
|---------|-------|-------------|
| Both | `both` | Control both sides (default) |
| Side A | `side_a` | Control left side only |
| Side B | `side_b` | Control right side only |

#### Command Timing

| Operation | Repeat Count | Delay | Notes |
|-----------|-------------|-------|-------|
| Motor movement | 25 | 50ms | Continuous while held |
| Presets | 1 | - | Single command |
| Massage toggle | 1 | - | Single command |
| Light toggle | 1 | - | Single command |
| Stop | 1 | - | Always sent after movement |

#### Notes

1. The app supports both BLE and Classic Bluetooth. This implementation uses BLE only.

2. For Classic Bluetooth, the protocol uses big-endian command encoding instead of little-endian.

3. Timer status can be read from notifications (byte values 1=10min, 2=20min, 3=30min).

### Cool Base

**Status:** ❓ Needs testing

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

#### Known Models

- Cool Base adjustable bed bases (Keeson BaseI5 with cooling fan)
- DewertOKIN `OKIN-BLE` / `BTCB` controllers that use the same 8-byte packet
  format without fan controls

#### Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | Cool Base 1.0.0 (3) | `com.keeson.coolbase` |

The Cool Base profile follows the independently accepted clean-room audit of
this app; see the [row047 dispositions](../apk-analysis/dispositions/row047-coolbase.md).
Hardware behavior is unverified.

#### Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (2 motors: head, foot) |
| Position Feedback | ❌ |
| Memory Presets | Cool Base: ❌ (the app's star button has no proven memory meaning; exposed as **Star button**). DewertOKIN OKIN-BLE: 2 slots |
| Factory Presets | ✅ (Flat, Zero-G, TV, Anti-Snore; Lounge only on DewertOKIN OKIN-BLE) |
| Massage | ✅ (Head massage, Foot massage, Massage mode buttons; mode sensor) |
| Light Control | ✅ (on/off from reported state; toggle) |
| Fan Control | ✅ (Left fan, Right fan, Fan sync buttons; level sensors 0-3) |

#### Protocol Details

**Service UUID:** `0000ffe5-0000-1000-8000-00805f9b34fb`
**Write Characteristic:** `0000ffe9-0000-1000-8000-00805f9b34fb`
**Notify Characteristic:** `0000ffe4-0000-1000-8000-00805f9b34fb`
**Format:** 8-byte packets with XOR checksum

#### Detection

Cool Base bed-type detection matches device names containing `base-i5`, the
app's own scan filter. For configured
Cool Base entries, the DewertOKIN profile is selected when the connected BLE name
matches `okin-ble*` / `btcb*` or the BLE manufacturer value is `DewertOKIN`.
`OKIN-BLE` / `DewertOKIN` devices may need manual Cool Base selection only when
they advertise overlapping OKIN UUIDs.

Note: Cool Base shares the same service UUID (FFE5) as Keeson and other beds, but is distinguished by the device name pattern.

#### Packet Format

All commands are 8 bytes:

```text
[0xE5, 0xFE, 0x16, cmd0, cmd1, cmd2, cmd3, checksum]
```

Where:
- Bytes 0-2 = Header `[0xE5, 0xFE, 0x16]`
- Bytes 3-6 = Command bytes (32-bit value in little-endian)
- Byte 7 = Trailer: `(sum(bytes 0-6) ^ 0xFF) & 0xFF`. The app writes literal
  trailers; this formula reproduces every one it ships.

#### Commands

##### Motor Control

| Action | Value | cmd0 | Notes |
|--------|-------|------|-------|
| Head Up | 0x01 | 0x01 | Hold to move |
| Head Down | 0x02 | 0x02 | Hold to move |
| Foot Up | 0x04 | 0x04 | Hold to move |
| Foot Down | 0x08 | 0x08 | Hold to move |
| Status query | 0x00 | 0x00 | All zeros; see below |

The app sends no distinct STOP: releasing a button ends the 100 ms refresh. The
integration then sends the all-zero frame, which is the app's own status query.

##### Factory Presets

| Action | Value | cmd bytes |
|--------|-------|-----------|
| Flat | 0x08000000 | cmd3=0x08 |
| Zero-G | 0x00001000 | cmd1=0x10 |
| TV | 0x00004000 | cmd1=0x40 |
| Anti-Snore | 0x00008000 | cmd1=0x80 |
| Star button / Memory 1 | 0x00010000 | cmd2=0x01; Memory 1 only on DewertOKIN OKIN-BLE |
| Memory 2 | 0x00040000 | cmd2=0x04, DewertOKIN OKIN-BLE profile only |

##### Light & Massage

| Action | Value | cmd bytes |
|--------|-------|-----------|
| Light Toggle | 0x00020000 | cmd2=0x02 |
| Massage Head | 0x00000800 | cmd1=0x08 |
| Massage Foot | 0x00000400 | cmd1=0x04 |
| Massage Level | 0x04000000 | cmd3=0x04 |

##### Fan Control (Unique to Cool Base)

| Action | Value | cmd bytes | Notes |
|--------|-------|-----------|-------|
| Left Fan | 0x00400000 | cmd2=0x40 | Device-side level change |
| Right Fan | 0x40000000 | cmd3=0x40 | Device-side level change |
| Fan Sync | 0x00040000 | cmd2=0x04 | Fan-labelled; not bed sync |

#### Notification Format

Only exact 28-byte replies to the status query are used. Any value outside the
listed range leaves that field unchanged:
- Byte 13: `(b & 0xF0) >> 6` is the light flag (0 off, 1 on)
- Byte 19: Massage mode (0-3)
- Byte 20: Left fan level (0-3)
- Byte 21: Right fan level (0-3)

The status query follows every tapped control three times, 200 ms apart, and
repeats every 3 s while connected. Polling never extends the idle disconnect.
Reported state clears when the connection ends. With the default
disconnect-after-command setting the light is usually unknown, so an on/off
request first sends a status query and waits up to 1 s for the reply.

The head massage, foot massage and massage mode buttons appear without the
massage option because the app always shows them.

#### Command Timing

| Operation | Repeat Count | Delay | Notes |
|-----------|-------------|-------|-------|
| Motor movement | 10 | 100ms | Continuous while held |
| Presets, fans, massage, light | 1 | - | Then three status queries, 200 ms apart |
| Status query | 1 | - | Sent after movement and every 3 s while connected |

#### Notes

1. Cool Base is a Keeson BaseI5 variant with additional fan/wind control features for cooling.

2. Fan, massage and light buttons send fixed frames. The app never computes the next level; how the device cycles levels is unverified.

3. Fan levels are reported in status replies and exposed as diagnostic sensors.

4. Fan sync is the app's fan-labelled button; its exact synchronization policy is unverified.

5. On DewertOKIN `OKIN-BLE` / `BTCB` devices, `0x00040000` is Memory 2 instead
   of sync fan. The integration exposes Memory 2 and suppresses fan controls for
   that profile to avoid showing both meanings for the same packet.

### BF and Cherish

**Status:** ❓ Needs testing (APK-verified, hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

#### Known Models

- Beds controlled by the BF app (`com.BF`, three motors)
- Beds controlled by the Cherish app (`com.okin.ore.cherish`)

#### Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [BF](https://play.google.com/store/apps/details?id=com.BF) 1.2.3 (11) | `com.BF` |
| ✅ | [Cherish](https://play.google.com/store/apps/details?id=com.okin.ore.cherish) 1.0.4 (5) | `com.okin.ore.cherish` |

- Support comes from accepted APK audits of both apps, reconciled together as
  row063/cluster-001 (see [Analysis provenance](#bf-and-cherish-analysis-provenance)).
- The apps share framing, not their command tables or alarm format.

#### Features

| Feature | BF | Cherish |
| --- | --- | --- |
| Motors | Back, legs, independent head | Back and legs, plus combined up/down buttons |
| Presets | Flat, Zero Gravity, Quiet Sleep (anti-snore) | Flat, Zero Gravity, Quiet Sleep (anti-snore) |
| Memory | A/B, recall and program | A/B, recall and program |
| Light | Omitted: both app light branches send the Zero Gravity command | Separate on/off commands, assumed state |
| Massage | None | On/off, intensity 1–3, wave 1–3, timer 10/20/30 minutes |
| Bed alarm | Clock query, setting, notification state | Setting, persisted command intent, no response parser |
| Position feedback | None | None |

The extra combined-motion buttons, massage numbers and alarm query are
available as entities in Home Assistant.

#### Protocol Details

**Service UUID:** none required (the parent service of the FFE9/FFE4 characteristics is used)
**Write Characteristic:** `0000ffe9-0000-1000-8000-00805f9b34fb`
**Notify Characteristic:** `0000ffe4-0000-1000-8000-00805f9b34fb`
**Format:** Fixed-length frames ending in a complement checksum

##### Packet Format

| Packet | Bytes |
| --- | --- |
| Control key | `E5 FE 16` + key (4, big-endian) + checksum |
| Clock/alarm query (BF) | `E2 FE 16` + second, minute, hour, weekday (Sunday = 0) + checksum |
| BF alarm setting | `EB FE 16` + clock second, minute, hour + alarm minute, hour + weekday + day mask + `00 00` + selector + checksum |
| Cherish alarm setting | `EA FE 16` + clock second, minute, hour + alarm minute, hour + `FF FF FF` + selector + checksum |

- Checksum: the complement of the sum of all preceding bytes, low byte
  (`~sum & 0xFF`).
- Alarm frames carry the current Home Assistant clock (second, minute, hour).

##### Write Mode

- Writes require the ordinary WRITE property and use GATT responses, without
  inferring an Android numeric write type.
- HA validates a connected writable role before submitting.

##### GATT Roles

- Both profiles discover the parent service of FFE9 writes and FFE4
  notifications; they do not require the unused fixed service UUID
  declarations.
- Each matching FFE4 attempts notification subscription; failed subscription
  does not block controls.
- The last matching role is used for payload consumption.
- There is no selected app read, authentication packet, MTU request,
  fragmentation, capability query or firmware update route.

#### Detection / Setup

- Choose **BF (com.BF app, three motors)** or **Cherish
  (com.okin.ore.cherish app)** in manual setup.
- Select the Bluetooth address used by that app.
- Neither app provides an advertisement signature that can safely select its
  profile. Shared FFE9/FFE4 characteristics do not identify either product.
- Existing beds using other profiles are unchanged.

##### Home Assistant setup

Select the exact BF or Cherish app in manual setup.
The app fixes its motor layout, capabilities and 200 ms movement refresh.
Only the bounded pulse count is configurable. A shared FFE9 service does not
select either app automatically. Each physical address keeps its own profile.

#### Commands

All frames below are exact `control_frame()` output from
[`beds/bf_cherish.py`](../../custom_components/adjustable_bed/beds/bf_cherish.py).

##### Motor Control

| Command | Key | Frame | Profile |
| --- | --- | --- | --- |
| Back up | `0x00000001` | `E5FE160000000105` | BF, Cherish |
| Back down | `0x00000002` | `E5FE160000000204` | BF, Cherish |
| Legs up | `0x00000004` | `E5FE160000000402` | BF, Cherish |
| Legs down | `0x00000008` | `E5FE1600000008FE` | BF, Cherish |
| Head up | `0x00000010` | `E5FE1600000010F6` | BF only |
| Head down | `0x00000020` | `E5FE1600000020E6` | BF only |
| Back and legs up | `0x00000005` | `E5FE160000000501` | Cherish only |
| Back and legs down | `0x0000000A` | `E5FE160000000AFC` | Cherish only |
| Movement release | `0x00000000` | `E5FE160000000006` | BF, Cherish |

##### Presets

| Command | BF key / frame | Cherish key / frame |
| --- | --- | --- |
| Zero Gravity | `0x01000001` / `E5FE160100000104` | `0x21000001` / `E5FE1621000001E4` |
| Flat | `0x01000002` / `E5FE160100000203` | `0x21000002` / `E5FE1621000002E3` |
| Quiet Sleep (anti-snore) | `0x01000004` / `E5FE160100000401` | `0x21000003` / `E5FE1621000003E2` |
| Preset STOP | `0x01000000` / `E5FE160100000005` | `0x21000000` / `E5FE1621000000E5` |

##### Memory

| Command | BF key / frame | Cherish key / frame |
| --- | --- | --- |
| Recall A (memory 1) | `0x01000008` / `E5FE1601000008FD` | `0x21000004` / `E5FE1621000004E1` |
| Recall B (memory 2) | `0x01000009` / `E5FE1601000009FC` | `0x21000006` / `E5FE1621000006DF` |
| Program A (memory 1) | `0x20000008` / `E5FE1620000008DE` | `0x21000014` / `E5FE1621000014D1` |
| Program B (memory 2) | `0x20000009` / `E5FE1620000009DD` | `0x21000016` / `E5FE1621000016CF` |

##### Lights (Cherish)

| Command | Key | Frame |
| --- | --- | --- |
| Light on | `0x31000001` | `E5FE1631000001D4` |
| Light off | `0x31000000` | `E5FE1631000000D5` |

BF has no light entity: both of its app light branches send the Zero Gravity
command.

##### Massage (Cherish)

| Command | Key | Frame |
| --- | --- | --- |
| Timer 10 / 20 / 30 min | `0x10000030` / `0x10000031` / `0x10000032` | `E5FE1610000030C6` / `E5FE1610000031C5` / `E5FE1610000032C4` |
| Wave 1 / 2 / 3 | `0x10000021` / `0x10000022` / `0x10000023` | `E5FE1610000021D5` / `E5FE1610000022D4` / `E5FE1610000023D3` |
| Wave 0 (off) | `0x10000020` | `E5FE1610000020D6` |
| Intensity 1 / 2 / 3 | `0x10000011` / `0x10000012` / `0x10000013` | `E5FE1610000011E5` / `E5FE1610000012E4` / `E5FE1610000013E3` |
| Intensity 0 (off) | `0x10000010` | `E5FE1610000010E6` |

##### Preset and Memory Selection State

- A second press of the same preset sends that profile's preset STOP.
- Preset and memory taps share the app's selection state.
- Programming a memory preserves the shared count: programming as the first
  action suppresses a subsequent tap of that same memory until another preset
  or movement changes the selection.
- Programming after a running preset makes the next same-memory tap send STOP.
- This state survives reconnects but is not a hardware acknowledgement.

##### Massage Sequences (Cherish)

- Start: timer, wave after 100 ms, then intensity after another 200 ms.
- Off: intensity 0, then wave 0 after 100 ms, keeping the selected levels and
  timer.
- At the bounds, +/- does not write.
- Selecting a timer sends only its timer command and disables level changes
  until massage is started again; it does not prove that the receiver stopped
  massage.
- There is no massage feedback.
- HA serializes these sequences and finishes cancellation cleanup, so an
  Android delayed callback cannot restart massage after Off.

#### Alarm action

```yaml
action: adjustable_bed.bf_cherish_set_alarm
data:
  device_id: YOUR_DEVICE_ID
  enabled: true
  time: "08:30:00"
  memory: memory_1
```

- `memory` is `none`, `memory_1` (A), or `memory_2` (B), never a bed side.
- Use `enabled: false` to disable; the previous selected schedule remains in
  local intent.
- Enabling always supplies a complete, valid time and explicit memory.
- The clock comes from Home Assistant's configured local timezone.

##### Alarm Frames

| Field | BF (EB) | Cherish (EA) |
| --- | --- | --- |
| Selector: none / A / B | `255` / `248` / `249` | `255` / `4` / `6` |
| Schedule | Sunday-zero weekday and a day mask for the next occurrence; an equal hour/minute remains today | Three FF fields unchanged |
| Disable | EB then EA | EA twice |

- These bytes do not prove any further recurrence semantics.
- The two disable packets sample the current clock independently.
- Disabled fields (alarm minute/hour, day mask and selector; BF's two zero
  bytes) are sent as `FF`.
- There is no application alarm ACK.

Example frames from `alarm_frame()` with an HA clock of Tuesday 07:15:30:

| Request | Frame |
| --- | --- |
| BF, enable 08:30, `memory_1` | `EBFE161E0F071E0802040000F8A8` |
| BF, disable (first frame) | `EBFE161E0F07FFFF02FFFFFFFFD0` |
| Cherish, enable 08:30, `memory_1` | `EAFE161E0F071E08FFFFFF04A6` |
| Cherish (and BF second frame), disable | `EAFE161E0F07FFFFFFFFFFFFD3` |
| BF clock query | `E2FE161E0F0702D3` |

##### Alarm State

- The **Bed alarm** sensor exposes the last command or BF report, with time,
  memory, raw BF selector and source attributes.
- Cherish intent persists across HA restarts; expiry clears its local enabled
  indication. It does not restore phone alarms or infer receiver state.
- BF's **Query bed alarm** button sends the live E2 clock query.
- Cherish has no reachable query or alarm notification consumer, so neither is
  synthesized for it.

##### Deliberate App Differences

- HA requires explicit valid alarm fields instead of reproducing the apps'
  unset FF time fields, BF's untouched 88 selector, delayed wheel races, or
  Cherish's A-while-B branch that displays A while sending B.
- Selection and persisted intent use the actual memory requested by the HA
  caller.
- No extra bed command is invented to correct these phone defects.

#### Notifications / State

BF alarm report on FFE4:

| Field | Value |
| --- | --- |
| Prefix | E2FE16 |
| Minute / hour / selector | Unsigned offsets 3/4/9 |
| Disabled | minute > 59 **and** hour > 24 (the app's condition, preserved exactly) |
| Selector | `248` A, `249` B, `255` none; unknown selectors preserve the prior memory |

- HA safely ignores short packets rather than reproducing the app's
  substring/index exceptions.
- Reports may contain invalid times; they are diagnostic values, never
  automatically programmed.
- Cherish registers the notification but has no consuming alarm parser.

#### Command Timing

- Movement refreshes use the app's 200 ms interval with a bounded HA pulse
  count.
- Movement release uses `E5FE160000000006`; preset STOP is profile-specific.
- HA attempts release on cancellation and errors, and explicit STOP attempts
  both families. It cannot guarantee delivery on a failed Bluetooth link.
- Presets and saves are single writes, without an automatic touch-release STOP.

#### Notes

##### BLE Transport and Failures

- Cancelled operations can perform no write; write errors propagate and do not
  advance local preset state.
- Transport submission, GATT completion and reported bed state are distinct.
- HA's coordinator owns adapter/proxy selection, connection recovery, bounded
  retry, command serialization and STOP preemption.
- It does not recreate Android's 100-pending FIFO, 10/100 ms queue scheduling,
  numeric errors or reflection-based cache refresh.
- The apps themselves can reject an incoming STOP at queue capacity; that
  defect is not copied into HA.
- No failure, disconnect or timeout alone establishes physical stopping.

##### Scope

Wi-Fi provisioning, SSID/passwords, bed network administration, cloud/account
services and unrelated phone infrastructure are outside this BLE integration.

##### Hardware Status

**Hardware status: UNVERIFIED.**

- Real-user captures after beta/release are deferred external validation, not
  a prerequisite for implementing the proven app behavior.
- Physical posture, stopping distance, alarm recurrence and successful on-air
  delivery have not been established.

##### BF and Cherish analysis provenance

| Package | Version | Artifact SHA-256 |
| --- | --- | --- |
| `com.BF` | 1.2.3 (11) | `64982c7a35fed0c902061b7b0f732b15798a38688119c1d92d343052781a83d1` |
| `com.okin.ore.cherish` | 1.0.4 (5) | `2f32624027a0f3a950f796f87c18feda2eafad1fa253927751a02426824b8520` |

The exhaustive [disposition ledger](../apk-analysis/dispositions/row063-cluster001.md)
records the evidence and implementation treatment, including report, audit and
reconciliation seals.

### Comfort Enhancements

**Status:** ❓ Needs testing (artifact-vector and HA software validation only)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

#### Known Models

| Layout | Third movement control | Memory slots | Massage and light |
| --- | --- | --- | --- |
| MC2: AC-1/BC3, Massage Plus / Comfort Position | Both (app union) | A, B | Yes |
| MC3: Comfort Position | Both (app union) | A, B | No |
| MC4: Lumbar Support / Massage Plus | Lumbar | Memory | Yes |
| MC5: Hi Lo Lift / Massage Plus | Bed height | Memory | Yes |

#### Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Comfort Enhancements](https://play.google.com/store/apps/details?id=com.okin.enhancements) 1.0.3 (4) | `com.okin.enhancements` |

#### Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Back, Legs and the layout's third control |
| Position Feedback | ❌ (no position feedback or travel angles) |
| Presets | ✅ Flat, Zero G, Quiet sleep on all layouts; TV on MC2/MC3 |
| Memory Presets | ✅ A/B on MC2/MC3, single Memory on MC4/MC5; separate recall and save buttons |
| Massage | ✅ MC2/MC4/MC5 (head, foot, wave/mode, timer; local assumed state) |
| Lights | ✅ MC2/MC4/MC5 On/Off (assumed state) |
| Clock Sync | ✅ (`adjustable_bed.sync_clock`) |
| Alarm | ✅ (`adjustable_bed.comfort_enhancements_set_alarm`) |
| One-address Left/Right | ❌ |

#### Protocol Details

**Write Characteristic:** `0000ffe9-0000-1000-8000-00805f9b34fb` (`FFE9`)
**Notify Characteristic:** `0000ffe4-0000-1000-8000-00805f9b34fb` (`FFE4`)
**Format:** 8-byte control frames `E5 FE 16` + four big-endian action bytes +
complemented sum

- The app discovers the last writable `FFE9` characteristic and last notifiable
  `FFE4` across all services. Parent service constants do not constrain
  selection.
- The profile uses those exact characteristic objects and subscribes through
  HA's BLE stack.
- There is no app authentication, initialization packet, ACK gate or position
  query.

##### Packet Format

- Control: `E5 FE 16` + four big-endian action bytes + complemented sum.
- Clock: `E2 FE 16 ss mm hh day checksum`, with Sunday = 0.
- Alarm: `EB FE 16 now_ss now_mm now_hh alarm_mm alarm_hh day mask massage0
  massage1 memory checksum`.
- Time is binary, not BCD. The final byte makes the unsigned sum equal FF
  modulo 256.

##### Write Mode

Write response mode is selected from discovered metadata: write-without-response
when the characteristic offers it, otherwise write with response.

#### Detection / Setup

1. Choose **Comfort Enhancements app (choose MC2/MC3/MC4/MC5)** manually.
2. Select the screen used in the Android app.

- Shared Bluetooth names and services do not identify this app or its layout.
  No automatic layout is available.
- The layout controls feature availability, independently of the generic motor
  count.
- A two-address pair keeps each physical bed's layout; unpair before changing
  those choices. This profile has no one-address Left/Right control.

#### Commands

Every control frame carries a 32-bit action word. Movement uses `00000001/02` (Back), `00000004/08` (Legs), `00000010/20` (third
control), with release `00000000`. Presets use `01000001/02/04` (Zero G, Flat,
Quiet sleep), `01000003` (TV or single Memory), `01000008/09` (A/B), and STOP
`01000000`. Save uses `20000003/08/09`. Light uses `31000001/00`. Massage bases
are `10000010` (head), `11000010` (foot), `10000020` (wave), plus level 0..3;
timers are `10000030/31/32`.

##### Motor Control

| Command | Action word | Bytes (hex) |
|---------|-------------|-------------|
| Back Up | `00000001` | `E5 FE 16 00 00 00 01 05` |
| Back Down | `00000002` | `E5 FE 16 00 00 00 02 04` |
| Legs Up | `00000004` | `E5 FE 16 00 00 00 04 02` |
| Legs Down | `00000008` | `E5 FE 16 00 00 00 08 FE` |
| Third control Up (Both / Lumbar / Bed height) | `00000010` | `E5 FE 16 00 00 00 10 F6` |
| Third control Down | `00000020` | `E5 FE 16 00 00 00 20 E6` |
| Movement STOP (release) | `00000000` | `E5 FE 16 00 00 00 00 06` |

##### Presets

| Command | Action word | Bytes (hex) |
|---------|-------------|-------------|
| Zero G | `01000001` | `E5 FE 16 01 00 00 01 04` |
| Flat | `01000002` | `E5 FE 16 01 00 00 02 03` |
| TV (MC2/MC3) | `01000003` | `E5 FE 16 01 00 00 03 02` |
| Quiet sleep | `01000004` | `E5 FE 16 01 00 00 04 01` |
| Preset STOP | `01000000` | `E5 FE 16 01 00 00 00 05` |

A repeated tap of the same preset sends the preset STOP, as in the app.

##### Memory

| Command | Action word | Bytes (hex) |
|---------|-------------|-------------|
| Memory A recall (MC2/MC3) | `01000008` | `E5 FE 16 01 00 00 08 FD` |
| Memory B recall (MC2/MC3) | `01000009` | `E5 FE 16 01 00 00 09 FC` |
| Memory recall (MC4/MC5) | `01000003` | `E5 FE 16 01 00 00 03 02` |
| Memory A save (MC2/MC3) | `20000008` | `E5 FE 16 20 00 00 08 DE` |
| Memory B save (MC2/MC3) | `20000009` | `E5 FE 16 20 00 00 09 DD` |
| Memory save (MC4/MC5) | `20000003` | `E5 FE 16 20 00 00 03 E3` |

##### Massage

| Zone | Level 0 | Level 1 | Level 2 | Level 3 |
|------|---------|---------|---------|---------|
| Head (`10000010` + level) | `E5 FE 16 10 00 00 10 E6` | `E5 FE 16 10 00 00 11 E5` | `E5 FE 16 10 00 00 12 E4` | `E5 FE 16 10 00 00 13 E3` |
| Foot (`11000010` + level) | `E5 FE 16 11 00 00 10 E5` | `E5 FE 16 11 00 00 11 E4` | `E5 FE 16 11 00 00 12 E3` | `E5 FE 16 11 00 00 13 E2` |
| Wave (`10000020` + level) | `E5 FE 16 10 00 00 20 D6` | `E5 FE 16 10 00 00 21 D5` | `E5 FE 16 10 00 00 22 D4` | `E5 FE 16 10 00 00 23 D3` |

| Timer | Action word | Bytes (hex) |
|-------|-------------|-------------|
| 10 minutes | `10000030` | `E5 FE 16 10 00 00 30 C6` |
| 20 minutes | `10000031` | `E5 FE 16 10 00 00 31 C5` |
| 30 minutes | `10000032` | `E5 FE 16 10 00 00 32 C4` |

The massage controls match the app:

- Head/foot toggle starts at level 3 or stops that zone. Intensity clicks cycle
  0 → 3 → 2 → 1 → 0. Starting a zone with no local timer sends 10 minutes first,
  then the intensity after 200 ms.
- Wave/mode with both zones off starts head and foot at level 3, at 200 and
  300 ms. Otherwise it cycles wave 1, 2, 3, 0. Wave 0 then stops foot and head
  after 200 and 300 ms.
- Timer / stop cycles 10, 20, 30 minutes when both zones are off; with a zone
  active it stops head immediately and foot after 200 ms. The timer selector
  also provides explicit 10/20/30 choices and Off.

##### Lights

| Command | Action word | Bytes (hex) |
|---------|-------------|-------------|
| Light On | `31000001` | `E5 FE 16 31 00 00 01 D4` |
| Light Off | `31000000` | `E5 FE 16 31 00 00 00 D5` |

#### Clock and alarm

`adjustable_bed.sync_clock` sends the local HA time and the app's alarm query
(one `E2 FE 16` clock/query frame).
`adjustable_bed.comfort_enhancements_set_alarm` programs or disables the BLE
alarm. It accepts the usual `device_id` and optional paired `side`, plus:

| Field | Meaning |
| --- | --- |
| `enabled` | Required boolean |
| `time` | Required when enabling, `HH:MM:00` with minute precision |
| `memory` | 0 = none (default); MC2/MC3: 1 = A, 2 = B; MC4/MC5: 1 = Memory |
| `massage` | Include the app's alarm massage fields, default false |

| Alarm field | Values |
|-------------|--------|
| `day` | Current weekday, Sunday = 0 |
| `mask` | Current-day bit (`1 << day`) |
| `massage0 massage1` | Enabled `11 33`, disabled `00 00` |
| `memory` | `F8/F9/F3/FF`: A, B, single Memory, none |

- The app's alarm includes a current-day mask, even if the chosen time has
  already passed today. HA preserves that packet behavior; it does not invent
  weekly or next-day scheduling.
- MC3's alarm massage checkbox is independent of its hidden massage control
  page. Hardware interpretation is unverified.
- Disabling needs no time and sends the complete all-FF disable template: FF at
  the alarm time, mask, massage and memory offsets.
- HA requires an explicit settled time when enabling. The app instead retains
  fields from 300 ms debounced wheel callbacks and 500 ms programmatic
  positioning, which can send stale or FF time bytes. HA never reproduces those
  races, the misleading initial enabled flag, phone ringtone playback or Android
  scheduling.
- Successful writes establish no device acknowledgement of the alarm setting.

#### Notifications / State

- The app's live notify callback compares lowercase hex against uppercase
  `E2FE16`, rejecting all inputs. Its unreachable parser lacks a proven reply
  length/checksum and always marks massage enabled.
- HA retains raw notifications for diagnostics and does not invent working
  feedback from that dead parser. No notification-derived alarm, motor, sensor
  or massage state is exposed.
- Massage state is local assumed state, reset on reconnect. External remote
  changes and timer expiry cannot be observed. Light On/Off also has assumed
  state. Stopping the final active zone clears the local timer.
- New entries keep the connection between commands by default so preset
  repeat-tap and massage cycles retain their local state.

#### Command Timing

| Action | Timing |
|--------|--------|
| Movement | Sends a frame immediately and refreshes every 200 ms for a bounded HA tap (five pulses by default) |
| Normal release | Movement STOP 100 ms later |
| Cancellation | Ends the refresh and sends cleanup with a fresh event |
| Explicit Stop | Sends both the movement and preset STOP forms |
| Massage zone start | 10-minute timer first when no local timer is set, intensity after 200 ms |

Once a multi-zone shutdown starts, its zone-off writes finish before a
replacement command, even if cancelled; delayed start writes remain cancellable.

#### Notes

- The labels describe the app controls; physical semantics and stopping
  latency remain unverified on hardware.
- **Hardware status:** artifact-vector and HA software validation only. Real
  users can validate movement labels, release, massage and alarms after
  beta/release; maintainer access to a bed is not a prerequisite for this
  implementation.

##### Comfort Enhancements analysis provenance

- Evidence: accepted independent audit of `com.okin.enhancements` **1.0.3 (4)**.
- Artifact set SHA-256:
  `bc76b08e593f42a3772385551553cb93345394639cfeb4d8e2cc61a99c28eab7`.
- See the [complete discovery dispositions](../apk-analysis/dispositions/row110-comfort-enhancements.md).

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
- Cluster033 apps: see the [cluster033 app family](#cluster033-app-family) and its
  [disposition ledger](cluster033-dispositions.json).
- The other routes come from the smartbed-mqtt reverse engineering, fresh
  decompilation of the OEM apps listed above, and hardware reports.
