# Keeson

**Status:** Tested (Base, KSBT, KSBT03C, Ergomotion, Sino / BetterLiving and Cool Base routes; Adjustable Lite partly; the other app profiles need testing)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), [alanbixby](https://github.com/alanbixby), [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt) and [MangoScango](https://github.com/MangoScango)

One wire codec (the K1 `E5/E6 FE 16` frame and the other carriers of the Keeson
32-bit key word) serves every `keeson` protocol variant, the `ergomotion` and
`okin_ffe` bed types, the Keeson, Okin and ORE app
profiles, and the Keeson layout app bed types. This guide covers the codec first, then one section per profile. See
[Protocol codecs and app profiles](../design/protocol-codecs.md) for the
architecture.

## Known Models

BetterLiving2 has two- and three-motor layouts; pick yours in setup. The
Bluetooth name does not tell which one you have.

Symphony Sleep Sense beds with control box selector 4, and its split P1 beds,
also use this format; their controls are in the
[Symphony profile](okin-soundwave.md#symphony-sleep-sense). Choose that app in
setup; the Bluetooth name does not identify it.

OrmatekTechnoSmart has Techno Smart New and Techno Smart Lite layouts; pick yours
in setup. They are not yet tested on hardware.

Brands using Keeson/Ergomotion actuators:

- Serta, including Serta Motion Perfect III and other BLE-enabled, non-cloud Serta bases
- Ergomotion
- Ergomotion Rio 5.0 / Denver Mattress Hibernation Platinum (advertises as `KSBT03C...`; 3 motors: back, legs and lumbar, no head tilt)
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

**Beautyrest BLACK app:** the Android app `com.keeson.beautyrestblack` 1.2.1
(18) controls the bed over the network, not Bluetooth, so it is not supported.
Beautyrest bases that use one of the Keeson Bluetooth routes still work.

**DewertOkin/ORE brands** also using FFE5 protocol (31 apps):
- Simon Li, Cherish Smart, Minghua, Heal Every Night (Simon Li, Heal Every Night and OKIN-Seating have [their own profiles](#simon-li-heal-every-night-and-okin-seating-profiles))
- ORE: Dynasty, LevaSleep, American Star, Avanti, Comfort Furniture, Hestia Motion, Maxcoil, Power's Bedding, SFM, Ultramatic, Better Living, Koizumi
- See [DewertOkin](okin-nframe.md#dewertokin) for full list

## Apps

| Analyzed | App | Package ID | Profile |
|----------|-----|------------|---------|
| ✅ | [PowersBedding](https://play.google.com/store/apps/details?id=com.ore.powersbedding) 1.1.0 (2) | `com.ore.powersbedding` | [PowersBedding](#powersbedding) |
| ✅ | Hestia Motion 1.2 (3) | `com.ore.yorkfeng.hestiamotion` | [Hestia Motion](#hestia-motion) |
| ✅ | BetterLiving 1.3.0 (16) | `com.ore.betterliving2` | [BetterLiving2](#betterliving2) |
| ✅ | [OrmatekTechnoSmart](https://play.google.com/store/apps/details?id=com.okin.ormatek) | `com.okin.ormatek` | [Techno Smart New / Lite](#ormatek-technosmart) |
| ✅ | [Aging in Place / Dawn House](https://play.google.com/store/apps/details?id=com.keeson.agingplace) 1.1.0 (87) | `com.keeson.agingplace` | [Dawn House JSON](#aging-in-place--dawn-house) |
| ✅ | [Enso Remote](https://play.google.com/store/apps/details?id=com.ore.sfm2) 2.3 | `com.ore.sfm2` | [Enso Remote](#enso-remote) |
| ✅ | [アシステック](https://play.google.com/store/apps/details?id=com.okin.yamada) 1.0.1 (6) | `com.okin.yamada` | [P1/P2](#アシステック--yamada) |
| ✅ | King Koil Bed 1.0 (code 1) | `com.sfd.kingkoilbed` | [Two remote layouts](#king-koil-bed) |
| ✅ | Somos / SomosBeds 1.0.0 (code 1) | `cn.com.somos` | [Five products](#somos--somosbeds) |
| ✅ | [ComfortBaseForBluetooth](https://play.google.com/store/apps/details?id=com.ore.yorkfeng.comfortbaseble2) 1.1.2 (6) | `com.ore.yorkfeng.comfortbaseble2` | [ComfortBaseForBluetooth](#comfortbaseforbluetooth) |
| ✅ | [Ergomotion 4.0](https://play.google.com/store/apps/details?id=com.sfd.hump) | `com.sfd.hump` | [Ergomotion 4.0](#ergomotion-40); also [KSBT](#ksbt-family) |
| ✅ | [1500 Tilt Base Remote](https://play.google.com/store/apps/details?id=com.sfd.rondure_hump) | `com.sfd.rondure_hump` | [KSBT](#ksbt-family) |
| ✅ | [Q-Plus Adjustable Remote](https://play.google.com/store/apps/details?id=com.sbi.costco) | `com.sbi.costco` | [Q-Plus Adjustable Remote](#q-plus-adjustable-remote); also [KSBT](#ksbt-family) |
| ✅ | [Ergomotion](https://play.google.com/store/apps/details?id=com.sfd.ergomotion) | `com.sfd.ergomotion` | [Ergomotion app](#ergomotion-app); also [Ergomotion](#ergomotion) |
| ✅ | [Tempur Zero G Bed Base](https://play.google.com/store/apps/details?id=com.sfd.row) (ROW Control) | `com.sfd.row` | [ROW Control](#row-control); also [Ergomotion](#ergomotion) |
| ✅ | Tempur Curve | `com.ore.tempur` | [Tempur Curve](#tempur-curve); also [Base](#base-basei4i5) |
| ✅ | [Member's Mark Base Remote](https://play.google.com/store/apps/details?id=com.sfd.mm) | `com.sfd.mm` | [Base](#base-basei4i5) |
| ✅ | [Serta MP Remote](https://play.google.com/store/apps/details?id=com.ore.serta330) | `com.ore.serta330` | [Serta MP Remote](#serta-mp-remote) |
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
| ✅ | [AMERICANSTAR](https://play.google.com/store/apps/details?id=com.ore.americanstar) 1.0 (1), not yet tested on hardware | `com.ore.americanstar` | [ORE comfort-bed](#ore-comfort-bed-profiles) |
| ✅ | ComfortFurniture 2.3 (10) | `com.ore.comfortfurniture` | [ComfortFurniture](#comfortfurniture) |
| ✅ | [OKIN Comfort Bed](https://play.google.com/store/apps/details?id=com.ore.okincomfortbed) 1.1.6 (8), not yet tested on hardware | `com.ore.okincomfortbed` | [OKIN Comfort Bed](#okin-comfort-bed) |
| ✅ | [ORE Ultramatic](https://play.google.com/store/apps/details?id=com.ore.ultramatic) 1.0.5 (9), not yet tested on hardware | `com.ore.ultramatic` | [ORE Ultramatic](#ore-ultramatic) |
| ✅ | [Leva Sleep](https://play.google.com/store/apps/details?id=com.ore.LevaSleep) 1.0.2 (3), not yet tested on hardware | `com.ore.LevaSleep` | [Leva Sleep](#leva-sleep) |
| ✅ | [Glideaway Motion](https://play.google.com/store/apps/details?id=com.ore.bedding.glideawaymontion) 1.0.3 (11) | `com.ore.bedding.glideawaymontion` | [Glideaway Motion](#glideaway-motion) |
| ✅ | [AdjustaMattress](https://play.google.com/store/apps/details?id=com.okin.adjustamattress) 1.6.0 (10) | `com.okin.adjustamattress` | [AdjustaMattress](#adjustamattress) |
| ✅ | Scott Living | `com.keeson.scottlivingrelease` | [Scott Living](#scott-living) |
| ✅ | [OkinComfortBed Ⅱ](https://apkpure.com/okin-comfortbed-%E2%85%B1/com.ore.jalon.neworebeding_android) 1.4 (4) | `com.ore.jalon.neworebeding_android` | [Jalon](#okincomfortbed-ⅱ-jalon) |
| ✅ | [OkimattMotion](https://apkpure.com/okimattmotion/com.okin.jalon.okimatandroid) 1.1.1 (3) | `com.okin.jalon.okimatandroid` | [OkimattMotion](#okimattmotion) |
| Own guide | Tempur Sleeptracker-AI ([guide](sleeptracker.md)) | `com.fullpower.applications.horizon` | none |

**iDealBed 6i:** iDealBed 6i Adjustable (installed as iDealBed 6i Remote,
`com.keeson.idealbed6iremote` 1.2.0 (11)) controls beds over the local network
or the cloud, not Bluetooth, so it is not supported. This does not apply to every
iDealBed bed or to the [Idealbed Bluetooth app](richmat.md#richmat-mh-apps)
(`com.richmat.idealbed`). Choose a profile from your bed's app or controller, not
from the iDealBed brand.

**ComfortBaseForWifi:** ComfortBaseForWifi 3.7 (10)
(`com.ore.jalon.comfortwifiandroid`) controls beds over the network, not
Bluetooth, so it is not supported. It is a different app from ComfortBase II
(Bluetooth). Do not pick a Keeson profile from its name or product list. A bed
that uses Bluetooth follows its own route, such as [BaseI4/I5](#base-basei4i5)
for the GlideAway ComfortBase Odessa, which owners have confirmed.

The eight apps of the [Keeson layout app family](#keeson-layout-app-family) (Tempur
Curve, Q-Plus, Serta MP Remote, Omazz Adjusto III, Ergomotion, ROW Control, Ergo
Slim and TEMPUR AU) are also their own bed types with their app's own keys and
layouts; the "also" routes are the generic Keeson variants that drive the same beds.


## Features

| Feature | BaseI4/I5 | JSON/A00A | KSBT | Ergomotion | Okin | Sino | Purple (Premium) | Purple (Premium Plus) |
|---------|-----------|------------|------|------------|------|------|------------------|-----------------------|
| Motor Control | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Position Feedback | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Hold Until Release | ❌ | ❌ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Memory Presets | ⚠️ 4 shown; the app uses slot 3 | ✅ (depends on the remote) | ✅ (slots 1-3: Read/TV/M) | ⚠️ 4 shown; not yet tested on hardware | ✅ | ✅ | ✅ (2 slots) | ✅ (3 slots) |
| TV Preset | ❌ | ✅ (depends on the remote) | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Anti-Snore Preset | ❌ | ✅ (depends on the remote) | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ |
| Lounge Preset | ❌ | ✅ (depends on the remote) | ✅ | ✅ | ❌ | ❌ | ✅ | ❌ |
| Massage | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Safety Lights | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Zero-G | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

The Sino column's anti-snore comes from the BetterLiving app. The app profiles list
their controls in their sections.

Hold until release ([renewable holds](../SERVICES.md#renewable-holds)) is on
every profile whose app streams a held key until release; the
tables below mark each one. The Base, OKIN, Sino, JSON, KSBT CR, KSBT04C, Sleep
Harmony, Purple, OKIN FFE, Rondure and Sleepy's BOX15 routes move
in steps instead.

## Choosing a profile

Detection suggests the Base, Ergomotion, OKIN FFE, JSON/A00A, KSBT and
KSBT03CR routes, Cool Base for `base-i5` names and Serta MP Remote for Serta
names; every other app profile is an explicit choice. The Keeson layout apps are bed types of their own, listed in the
[Keeson layout app family](#keeson-layout-app-family). The tables below are generated
from the profile data.

### Home Assistant setup

Choosing **Member's Mark, Purple, Sleep Harmony and Juna Sleep apps, some
Ergomotion Sync beds · Keeson**, **Ergomotion remote · Keeson** or **Cool Base
app · Keeson**, an Okin 13 or 15 series
receiver, or a bed detected as one of them, asks which app or remote you use. Shared names and Bluetooth services never decide it.

| Answer | Then | Route |
|---|---|---|
| Sleep Harmony app | | [Sleep Harmony](#sleep-harmony-variant) |
| Restonic BT app | The remote style the app's settings chose | [Restonic BT](#restonic-bt-profiles) A or B |
| Ergomotion, Ergomotion 4.0 or Serta MP Remote app | The app, then its own app step | [Keeson layout apps](#keeson-layout-app-family), [Ergomotion 4.0](#ergomotion-40) |
| Avanti, AMERICANSTAR, Bedsense Bases, ComfortFurniture, INNOVA, MaxCoil Una or Dynasty app | The app, then its 2M, 3M or 4M screen, which sets the motor count | [ORE apps](#ore-comfort-bed-profiles), [INNOVA](#innova-profile) |
| Adjustable Lite, Simon Li, Heal Every Night or OKIN-Seating app | The app | [Adjustable Lite](#adjustable-lite-profile), [Simon Li, Heal Every Night and OKIN-Seating](#simon-li-heal-every-night-and-okin-seating-profiles) |
| Purple Smart Base, Member's Mark or Linx / Juna Sleep | Which of them | [Purple](#purple-variant), [Base](#base-basei4i5), [JSON/A00A](#jsona00a-variant-juna-linx-ergo-health) |
| Cool Base app (with fan) | | [Cool Base](#cool-base) |
| No app: another Keeson remote | The route and motor count; the Ergomotion route also asks whether to read positions | Any [Keeson route](#profile-summary), such as KSBT or KSBT03CR |
| Keep the detected or saved controls | | The detected or chosen route |

An app row in the bed-type list answers the question itself; the one
**Restonic BT app** row still asks the remote style. A Keeson brand list entry
that names an app, a remote route or a Restonic remote style answers both.

For an existing bed, open the entry's three-dot menu and **Reconfigure** (see
[Changing the app or layout](../CONFIGURATION.md#changing-the-bed-type-app-or-layout-of-an-existing-bed)).
The same question appears, with **Keep the detected or saved controls** leaving
the entry as it is. A Keeson
route has no endpoint or bond to check: the controllers fall back across their
write roles, as Configure's switch did. A review lists the added and removed
controls before **Apply this change** saves it, keeping stored app state for a
later change back. **Configure** keeps routine settings; the app and route change
only through **Reconfigure**, and the app review in Repairs opens it.

<!-- generated:keeson-profiles -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

### Profile summary

| Profile | Route | Frame | Transport | Lights | Massage | Hold until release |
|---|---|---|---|---|---|---|
| OkinComfortBed II P1 | bed type `jalon` | K1 `E6`, little-endian, side `00` | app controller | app controller | app controller | renewable lease |
| OkinComfortBed II P2 | bed type `jalon` | K1 `E6`, little-endian, side `00` | app controller | app controller | app controller | renewable lease |
| OkinComfortBed II P3 | bed type `jalon` | P2 7-byte (`05`) | app controller | app controller | app controller | renewable lease |
| Base (BaseI4/I5) | `keeson` `base` (Auto default) | K1 `E5`, little-endian | BASE | toggle | step | no |
| Ergomotion | `keeson` `ergomotion`; bed type `ergomotion` | K1 `E5`, little-endian | BASE | toggle | step | renewable lease |
| OKIN FFE | `keeson` `okin`; bed type `okin_ffe` | K1 `E6`, little-endian | BASE | toggle | step | no |
| BetterLiving CB1322 | `keeson` `okin`: Auto: as BetterLiving, with a `BLE-4.0 Module` or `DewertOKIN` manufacturer | K1 `E6`, little-endian | BASE | toggle | step | no |
| Sino | `keeson` `sino` | K1 `E5`, big-endian | BASE | discrete | absolute | no |
| BetterLiving | `keeson` `sino`: Auto: both fallback services, or an `OKIN-BLE` name with one | K1 `E5`, big-endian | BASE | discrete | absolute | no |
| JSON/A00A | `keeson` `json` | JSON | JSON | toggle | step | no |
| KSBT | `keeson` `ksbt` | P2 6-byte | KSBT | toggle | step | renewable lease |
| KSBT03C | `keeson` `ksbt`: name starts with `KSBT03C`, not `KSBT03CR` | P2 6-byte | KSBT | toggle | step | renewable lease |
| KSBT03CR | `keeson` `ksbt_cr` | P2 7-byte (`05`) | KSBT | toggle | step | no |
| KSBT04C | `keeson` `ksbt04c` | P2 7-byte, checksum end | KSBT | none | step | no |
| Sleep Harmony (KSBT04C) | `keeson` `sleep_harmony` | P2 7-byte, checksum end | KSBT | none | step | no |
| Sleep Harmony (base-i5) | `keeson` `sleep_harmony`: name starts with `base-i5.` | K1 `E6`, little-endian, side `00` | BASE | none | step | no |
| Purple Premium | `keeson` `purple` | K1 `E5`, little-endian | BASE | toggle | step | no |
| Purple Premium Plus | `keeson` `purple`: name starts with `KSBT04C`, or the Nordic UART service exists | P2 7-byte, `00` end | KSBT | toggle | step | no |
| Adjustable Lite (KSBT01C) | `keeson` `adjustable_lite` | P2 6-byte | KSBT (fixed) | toggle | none | renewable lease |
| Adjustable Lite (KSBT03C) | `keeson` `adjustable_lite`: name contains `KSBT03C` (case-sensitive) | P2 6-byte | KSBT (fixed) | toggle | zone_steps | renewable lease |
| Restonic BT remote A | `keeson` `restonic_a` | K1 `E5`, little-endian | BASE (fixed) | none | none | renewable lease |
| Restonic BT remote B | `keeson` `restonic_b` | K1 `E5`, little-endian | BASE (fixed) | toggle | none | renewable lease |
| INNOVA | `keeson` `innova` | K1 `E5`, little-endian | BASE (fixed) | app controller | app controller | renewable lease |
| Simon Li | `keeson` `simon_li` | K1 `E5`, big-endian | BASE (fixed) | app controller | app controller | renewable lease |
| OKIN-Seating | `keeson` `okin_seating` | K1 `E5`, big-endian | BASE (fixed) | app controller | app controller | renewable lease |
| Heal Every Night | `keeson` `heal_every_night` | K1 `E5`, big-endian | BASE (fixed) | app controller | app controller | renewable lease |
| OKIN Comfort Bed | `keeson` `okin_comfort_bed` | K1 `E5`, big-endian | live FFE9 / FFE4 | app controller | app controller | renewable lease |
| ComfortFurniture | bed type `keeson:comfortfurniture` | K1 `E5`, big-endian | app controller | app controller | app controller | renewable lease |
| ORE Ultramatic | bed type `keeson`, `ore_ultramatic` | K1 `E5`, big-endian | app controller | app controller | app controller | renewable lease |
| Leva Sleep | bed type `keeson`, `leva_sleep` | K1 `E5`, big-endian | app controller | app controller | app controller | renewable lease |
| AMERICANSTAR | `keeson` `americanstar` | K1 `E5`, big-endian | BASE (fixed) | app controller | app controller | renewable lease |
| Avanti Bases | `keeson` `avanti_bases` | K1 `E5`, big-endian | BASE (fixed) | app controller | app controller | renewable lease |
| Bedsense Bases | `keeson` `bedsense_bases` | K1 `E5`, big-endian | BASE (fixed) | app controller | app controller | renewable lease |
| Dynasty Bases | `keeson` `dynasty_bases` | K1 `E5`, big-endian | BASE (fixed) | app controller | app controller | renewable lease |
| MaxCoil Una | `keeson` `maxcoil_una` | K1 `E5`, big-endian | BASE (fixed) | app controller | app controller | renewable lease |
| Glideaway Motion | bed type `glideaway_motion` | K1 `E6`, little-endian, side `00` | app controller | app controller | app controller | renewable lease |
| Malouf legacy OKIN | bed type `malouf_legacy_okin` | K1 `E6`, little-endian, side `00` | app controller | app controller | app controller | renewable lease |
| Sleepy's BOX15 | bed type `sleepys_box15` | K1 `E6`, little-endian, side `00` | app controller | app controller | app controller | no |
| Scott Living | bed type `scott_living` | K1 `E6`, little-endian, side `01` | app controller | app controller | app controller | renewable lease |
| AdjustaMattress P1 | bed type `adjustamattress`, model P1 | K1 `E6`, little-endian, side `00` | app controller | app controller | app controller | renewable lease |
| AdjustaMattress P2 | bed type `adjustamattress`, model P2 | K1 `E5`, big-endian | app controller | app controller | app controller | renewable lease |
| Rondure | bed type `rondure` | K1 `E5`, little-endian | app controller | app controller | app controller | no |
| Cool Base | bed type `coolbase` | K1 `E5`, little-endian | app controller | app controller | app controller | renewable lease |
| BF | bed type `bf` | K1 `E5`, big-endian | app controller | app controller | app controller | renewable lease |
| Cherish | bed type `cherish` | K1 `E5`, big-endian | app controller | app controller | app controller | renewable lease |
| OkimattMotion | bed type `okimattmotion` | K1 `E5`, big-endian | app controller | app controller | app controller | renewable lease |
| Comfort Enhancements | bed type `comfort_enhancements` | K1 `E5`, big-endian | app controller | app controller | app controller | renewable lease |
| ComfortBaseForBluetooth | bed type `comfortbase` | K1 `E6`, little-endian, side `00` | app controller | app controller | app controller | renewable lease |
| OkinComfortBed Ⅱ (Jalon) | bed type `jalon_bed` | K1 `E6`, little-endian, model `00` | app controller | app controller | app controller | renewable lease |
| アシステック P1 | bed type `yamada`, P1 | K1 `E6`, little-endian, side `00` | app controller | app controller | app controller | renewable lease |
| アシステック P2 | bed type `yamada`, P2 | P2 7-byte (`05`) | app controller | app controller | app controller | renewable lease |
| BetterLiving2 P1, 2 motors | bed type `betterliving2`, P1, 2 motors | K1 `E5`, big-endian | app controller | app controller | app controller | renewable lease |
| BetterLiving2 P1, 3 motors | bed type `betterliving2`, P1, 3 motors | K1 `E5`, big-endian | app controller | app controller | app controller | renewable lease |
| BetterLiving2 P2, 2 motors | bed type `betterliving2`, P2, 2 motors | K1 `E6`, little-endian, side `00` | app controller | app controller | app controller | renewable lease |
| BetterLiving2 P2, 3 motors | bed type `betterliving2`, P2, 3 motors | K1 `E6`, little-endian, side `00` | app controller | app controller | app controller | renewable lease |
| BetterLiving2 P3, 2 motors | bed type `betterliving2`, P3, 2 motors | P2 7-byte (`05`) | app controller | app controller | app controller | renewable lease |
| BetterLiving2 P3, 3 motors | bed type `betterliving2`, P3, 3 motors | P2 7-byte (`05`) | app controller | app controller | app controller | renewable lease |

### Hold and release timing

A hold writes its frame the given number of times while the stored cadence is the
Keeson default; a customized cadence wins. Release waits count from the previous
write. An explicit stop sends the release without its waits. The [controller
profiles](#controller-profiles) keep their timing in their controllers. Under a
[renewable hold](../SERVICES.md#renewable-holds), a profile with hold until
release refreshes at its app interval until the lease ends or STOP arrives, up to
30 s, then sends its release.

| Profile | Hold | Three motors | Release after a hold | Explicit stop | Released after one-shots | Wait before one-shots |
|---|---|---|---|---|---|---|
| Base (BaseI4/I5) | 3 × 400 ms | same | +0 ms `E5 FE 16 00 00 00 00 06` | `E5 FE 16 00 00 00 00 06` | no | none |
| Ergomotion | 10 × 100 ms | same | +0 ms `E5 FE 16 00 00 00 00 06` | `E5 FE 16 00 00 00 00 06` | no | none |
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
| OKIN Comfort Bed | pulse count × 100 ms | same | +100 ms `E5 FE 16 00 00 00 00 06` | `E5 FE 16 00 00 00 00 06` | no | 100 ms |
| AMERICANSTAR | pulse count × 100 ms | same | +100 ms `E5 FE 16 00 00 00 00 06` | `E5 FE 16 00 00 00 00 06` | no | 100 ms |
| Avanti Bases | pulse count × 100 ms | same | +100 ms `E5 FE 16 00 00 00 00 06` | `E5 FE 16 00 00 00 00 06` | no | 100 ms |
| Bedsense Bases | pulse count × 100 ms | same | +100 ms `E5 FE 16 00 00 00 00 06` | `E5 FE 16 00 00 00 00 06` | no | 100 ms |
| Dynasty Bases | pulse count × 100 ms | same | +100 ms `E5 FE 16 00 00 00 00 06` | `E5 FE 16 00 00 00 00 06` | no | 100 ms |
| MaxCoil Una | pulse count × 100 ms | same | +100 ms `E5 FE 16 00 00 00 00 06` | `E5 FE 16 00 00 00 00 06` | no | 100 ms |

### Presets and memory

Words, encoded in the profile's frame. AdjustaMattress P1, AdjustaMattress P2,
AMERICANSTAR, Avanti Bases, Bedsense Bases, BetterLiving2 P1, 2 motors,
BetterLiving2 P1, 3 motors, BetterLiving2 P2, 2 motors, BetterLiving2 P2, 3
motors, BetterLiving2 P3, 2 motors, BetterLiving2 P3, 3 motors, BF, Cherish,
Comfort Enhancements, ComfortBaseForBluetooth, ComfortFurniture, Cool Base,
Dynasty Bases, Glideaway Motion, Heal Every Night, INNOVA, OkinComfortBed II P1,
OkinComfortBed II P2, OkinComfortBed II P3, OkinComfortBed Ⅱ (Jalon), Leva Sleep,
Malouf legacy OKIN, MaxCoil Una, OkimattMotion, OKIN Comfort Bed, OKIN-Seating,
ORE Ultramatic, Rondure, Scott Living, Simon Li, Sleepy's BOX15, アシステック P1, アシステック
P2 keep their key tables with their app controllers; see their sections.

| Profile | Flat | Zero G | Lounge | TV | Anti-snore | Memory recall | Memory save |
|---|---|---|---|---|---|---|---|
| Base (BaseI4/I5) | `0x08000000` | `0x00001000` | no | no | no | 1: `0x00002000`<br>2: `0x00004000`<br>3: `0x00008000`<br>4: `0x00010000` | none |
| Ergomotion | `0x08000000` | `0x00001000` | `0x00002000` | `0x00004000` | `0x00008000` | 1: `0x00002000`<br>2: `0x00004000`<br>3: `0x00008000`<br>4: `0x00010000` | none |
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
| Name contains `serta` or `motion perfect` | bed type `serta_mp_remote` ([Serta MP Remote](#serta-mp-remote)) |
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
wire snapshot (`tests/test_wire_snapshot.py`) proves the equality by capture.

| Bed type or route | Same as | Notes |
|-------------------|---------|-------|
| `ergomotion` | `keeson` variant `ergomotion` | See [Ergomotion](#ergomotion) |
| `keeson` variants `avanti_bases`, `bedsense_bases`, `dynasty_bases`, `maxcoil_una`, `okin_comfort_bed` | `keeson` variant `americanstar` | Identical profiles under each app's own key; see [ORE comfort-bed profiles](#ore-comfort-bed-profiles) |

`okin_ffe` and the `keeson` variant `okin` share the [OKIN FFE](#okin-ffe)
profile but not its timing: `okin_ffe` defaults to 7 pulses 150 ms apart and
the variant to 10 pulses 100 ms apart, so they are not aliases.

Each keeps its own [profile id](../design/profile-id.md#aliases). `ergomotion` creates its
entities before the first connection and the `keeson` variant does not, and the
device manufacturer differs. Among the ORE apps, Avanti Bases hides more generic
setup fields, and each app has its own setup label. Every ORE and INNOVA app
keeps its motor count (the app's 2M, 3M or 4M screen) per side of a pair.

## Wire codec

`custom_components/adjustable_bed/codec/keeson.py` owns the transports, the K1
frame and checksum, the other carriers of the key word, the `00 B0` status
query, the `EF 02` rename frame and the Ergomotion status parser.

### Transports

<!-- generated:keeson-transports -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Transport | Service | Write | Notify | Fallbacks (service / write) | Profiles |
|---|---|---|---|---|---|
| BASE | `0000ffe5-0000-1000-8000-00805f9b34fb` | `0000ffe9-0000-1000-8000-00805f9b34fb` | `0000ffe4-0000-1000-8000-00805f9b34fb` | `0000fff0-0000-1000-8000-00805f9b34fb` / `0000fff2-0000-1000-8000-00805f9b34fb`<br>`0000ffb0-0000-1000-8000-00805f9b34fb` / `0000ffb2-0000-1000-8000-00805f9b34fb` | Base (BaseI4/I5), Ergomotion, OKIN FFE, BetterLiving CB1322, Sino, BetterLiving, Sleep Harmony (base-i5), Purple Premium, Restonic BT remote A, Restonic BT remote B, INNOVA, Simon Li, OKIN-Seating, Heal Every Night, AMERICANSTAR, Avanti Bases, Bedsense Bases, Dynasty Bases, MaxCoil Una |
| KSBT | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | `6e400020-b5a3-f393-e0a9-e50e24dcca9e` / `6e400021-b5a3-f393-e0a9-e50e24dcca9e`<br>`0000ffe5-0000-1000-8000-00805f9b34fb` / `0000ffe9-0000-1000-8000-00805f9b34fb`<br>`0000ffe0-0000-1000-8000-00805f9b34fb` / `0000ffe1-0000-1000-8000-00805f9b34fb` | KSBT, KSBT03C, KSBT03CR, KSBT04C, Sleep Harmony (KSBT04C), Purple Premium Plus, Adjustable Lite (KSBT01C), Adjustable Lite (KSBT03C) |
| JSON | `0000a00a-0000-1000-8000-00805f9b34fb` | `0000b002-0000-1000-8000-00805f9b34fb` | `0000b004-0000-1000-8000-00805f9b34fb` | none | JSON/A00A |

| Profile | Service | Write | Notify role | Selection |
|---|---|---|---|---|
| OKIN Comfort Bed | any discovered service | `0000ffe9-0000-1000-8000-00805f9b34fb` | `0000ffe4-0000-1000-8000-00805f9b34fb` (no CCCD) | last matching characteristics; both required |
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
| K1 `E6`, little-endian, side `00` | `header FE 16` + word + checksum | `E6 FE 16 01 00 00 00 00 04` | OkinComfortBed II P1, OkinComfortBed II P2, Sleep Harmony (base-i5), Glideaway Motion, Malouf legacy OKIN, Sleepy's BOX15, AdjustaMattress P1, ComfortBaseForBluetooth, OkinComfortBed Ⅱ (Jalon), アシステック P1, BetterLiving2 P2, 2 motors, BetterLiving2 P2, 3 motors |
| P2 7-byte (`05`) | `05 02` + big-endian word + `00` | `05 02 00 00 00 01 00` | OkinComfortBed II P3, アシステック P2 |
| K1 `E5`, little-endian | `header FE 16` + word + checksum | `E5 FE 16 01 00 00 00 05` | Base (BaseI4/I5), Ergomotion, Purple Premium, Restonic BT remote A, Restonic BT remote B, INNOVA, Rondure, Cool Base |
| K1 `E6`, little-endian | `header FE 16` + word + checksum | `E6 FE 16 01 00 00 00 04` | OKIN FFE, BetterLiving CB1322 |
| K1 `E5`, big-endian | `header FE 16` + word + checksum | `E5 FE 16 00 00 00 01 05` | Sino, BetterLiving, Simon Li, OKIN-Seating, Heal Every Night, OKIN Comfort Bed, ComfortFurniture, ORE Ultramatic, Leva Sleep, AMERICANSTAR, Avanti Bases, Bedsense Bases, Dynasty Bases, MaxCoil Una, AdjustaMattress P2, BF, Cherish, OkimattMotion, Comfort Enhancements, BetterLiving2 P1, 2 motors, BetterLiving2 P1, 3 motors |
| JSON | JSON envelope, see below | see JSON envelope | JSON/A00A |
| P2 6-byte | `04 02` + big-endian word | `04 02 00 00 00 01` | KSBT, KSBT03C, Adjustable Lite (KSBT01C), Adjustable Lite (KSBT03C) |
| P2 7-byte (`05`) | `05 02` + big-endian word + `00` | `05 02 00 00 00 01 00` | KSBT03CR |
| P2 7-byte, checksum end | `04 02` + big-endian word + checksum | `04 02 00 00 00 01 F8` | KSBT04C, Sleep Harmony (KSBT04C) |
| P2 7-byte, `00` end | `04 02` + big-endian word + `00` | `04 02 00 00 00 01 00` | Purple Premium Plus |
| K1 `E6`, little-endian, side `01` | `header FE 16` + word + checksum | `E6 FE 16 01 00 00 00 01 03` | Scott Living |
| P2 7-byte (`05`) | `05 02` + big-endian word + `00` | `05 02 00 00 00 01 00` | BetterLiving2 P3, 2 motors, BetterLiving2 P3, 3 motors |
| K1 `E6`, little-endian, Left side `02` | `E6 FE 16` + word + side + checksum | `E6 FE 16 01 00 00 00 02 02` | Base (BaseI4/I5), Ergomotion |
| K1 `E6`, little-endian, Right side `01` | `E6 FE 16` + word + side + checksum | `E6 FE 16 01 00 00 00 01 03` | Base (BaseI4/I5), Ergomotion |
<!-- /generated -->

#### Split-bed side byte

The nine-byte frame carries a side byte. Sleep Harmony's base-i5 route sends
side `00`. With [side controls](#side-controls) enabled, the Base and Ergomotion
profiles address one half with Left `02` or Right `01`, the selectors of the
Ergomotion 4.0 3.7 app builder; Both keeps the eight-byte `E5` frame. Every
command, release and STOP included, keeps the selected side.

The older A/B aliases in this guide (`01` side A, `02` side B) do not tell
which physical side is A or B. Android 3.7's A/B settings strings actually produce
selector `00` because its builder expects Left/Right. HA uses the Left/Right branches. Which half is which still needs testing by
owners.

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
rename frame of INNOVA and the Keeson layout apps.

#### Setup frames

The Keeson layout apps also send these checked frames, built by the codec:
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
- **Keeson layout apps:** the massage timer, and Serta MP Remote positions; see
  the [Keeson layout app family](#keeson-layout-app-family).

Every other profile reads nothing.

### STOP and release behavior

There is no dedicated STOP frame. A profile's release is in
[Hold and release timing](#hold-and-release-timing). Every release write uses a
fresh cancel event, so a STOP cannot suppress it; a touch-up release ("STOP ends
the wait") runs in a shielded task. Profiles with no release stop by ending the
cancellable refresh: their apps have no release frame, and inventing one would be
unsafe.

A renewable hold refreshes the app's held key at the app's interval until the
lease ends or a STOP arrives, up to 30 s, then runs the same release. Cool Base
keeps refreshing at the entry's repeat interval, as its finite holds do.
Adjustable Lite, Ergomotion Sync (KSBT03C) and the direct KSBT remotes end a hold
only by ending the refresh, as their apps do; whether the hardware stops on its
own is unverified. A lease never holds a Simon Li memory key, which saves the slot
when held past 2100 ms.

### Vectors

`tests/keeson_vectors.py` lists each profile's frozen single-frame literals:
the test vectors of the accepted Adjustable Lite, Restonic BT, INNOVA, Simon Li,
Heal Every Night, OKIN-Seating, MaxCoil Una, Dynasty Bases, Bedsense Bases,
Avanti Bases and AMERICANSTAR reports, every codec frame the Keeson layout app, Glideaway Motion
and AdjustaMattress reports spell (plus the pre-v5 frame of any key a report lists without spelling it), and
for every other route (which has no report) every frame the pre-v5 controller
could send.
`tests/test_keeson_vectors.py` checks that every literal round-trips through the
codec byte for byte, that each app profile sends only its frozen frames, that each
other route sends exactly its frozen frames, and that every protocol variant is a
profile.

## Profiles

### Base (BaseI4/I5)

**Status:** Tested

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
action is separate from wave selection and is displayed as **Massage timer**
while retaining its established entity identity.

#### Side controls

The explicit **BaseI4/BaseI5** and **Ergomotion** variants, and the Ergomotion
bed type, offer **Add Left, Right and Both controls** in **Configure** for a P1 receiver that
reaches both halves through one Bluetooth address. This creates native Left and
Right child devices and retains the parent's Both controls, sending the
[side frames](#split-bed-side-byte). Auto is not eligible because it may
resolve to P2 or JSON at connection time, and the detected BetterLiving
and CB1322 tables have no side frame.

The side frame comes from Ergomotion 4.0 3.7; its use on Member's Mark
hardware remains unverified. Choose it only for a receiver with compatible P1
side addressing. It does not change existing standalone frames, pulse timings,
profiles or entity identities. Two separately advertising receivers use the
existing two-address combined-bed workflow.

Legacy position feedback cannot identify which half reported it, so side-control
mode disables position sliders, sensors and seeking; restoring standalone
controls restores the stored preference. For the complete app-specific products,
commands, notifications, alarms and RGB, select the separate
[Ergomotion 4.0 app profile](#ergomotion-40).

#### Timing

See [Hold and release timing](#hold-and-release-timing) (Member's Mark scheduler).

### Ergomotion

**Status:** Tested

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

### OKIN FFE

**Status:** Not yet tested

Behaves as [Base](#base-basei4i5), except as below.

#### Setup

Bed type `okin_ffe` (OKIN 13/15 series), or `keeson` with the `okin` variant.
Detection: FFE5 with a name containing `okin`, `cb-` or `cb.`. The `okin_ffe`
bed type stores its own default cadence, which is kept as configured.

#### Controls

`E6` frames. No wave or intensity keys. The TV action sends `0x4000` but is
not listed as an entity. The three-motor screen uses its own cadence.

### Sino and BetterLiving

**Status:** Tested (a BetterLiving bed in [#229](https://github.com/kristofferR/ha-adjustable-bed/issues/229); a Dynasty Bases DM9000 on the older `ore` alias in [#180](https://github.com/kristofferR/ha-adjustable-bed/issues/180))

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

For the independently verified Linx 1.0.7 app controls, select the explicit
[Linx profile](linx.md). This legacy JSON route remains unchanged for existing
entries and other remotes.

**Status:** Not yet tested

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

**Status:** Tested (KSBT on an Ergomotion Rio 6.0 in [#297](https://github.com/kristofferR/ha-adjustable-bed/issues/297); KSBT03C on an Ergomotion Rio 5.0 in [#408](https://github.com/kristofferR/ha-adjustable-bed/issues/408)); KSBT03CR and KSBT04C need testing

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
remotes (from `cn.com.mancini` APK):** the app has three remote layouts: A and C
target `KSBT04C` devices, B targets `KSBT03C` (e.g. Rio 5.0). All three share the
same preset buttons: Read, TV, M, Zero-G, Flat, light toggle and the head, foot
and timer massage steps (no all-off command). The Anti-Snore button appears on
layouts B/C only; that describes the remote UIs, not command support. The
integration exposes anti-snore on all KSBT variants.

**KSBT03C motor layout:** the KSBT03C remote (layout B) drives only three motors:
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
remain authoritative. No KSBT03C release frame was found in the app, so the integration does not guess or substitute a zero-key
frame. Sync's KSBT04C layouts use their separate profile, including its existing
zero-frame release. KSBT03CR (SomosBeds) keeps its independently derived release.
See [Hold and release timing](#hold-and-release-timing).

#### Evidence

The KSBT03C command values and 3-motor layout are APK-derived (Ergomotion Sync
1.0.2) and not yet confirmed on hardware; the Rio 5.0 report in issue #408
confirms the lumbar motor responds to `0x40`/`0x80` and that no tilt motor
exists. The cadence, unacknowledged write mode and timer-cessation release are
checked against the app from Ergomotion Sync 1.0.5 but remain hardware-unverified. A
replacement STOP frame must not be guessed without new protocol details or a
hardware capture.

### Sleep Harmony Variant

**App:** [Sleep Harmony](https://play.google.com/store/apps/details?id=com.keeson.ssbaudio) 1.0.1, `com.keeson.ssbaudio`

**Status:** Not yet tested

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

**Status:** Not yet tested

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

**Status:** Partly tested (two Keeson MC232SC / KSSF05C beds in [#669](https://github.com/kristofferR/ha-adjustable-bed/issues/669); their TV, Lounge and Anti-Snore presets are tracked in [#681](https://github.com/kristofferR/ha-adjustable-bed/issues/681))

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
| 12 | `1` lights the bulb icon; anything else is off | **Under-bed lights** light |
| 3-4 (KSBT03C) | Big-endian value; above 1200, 600 or 0 shows the 30, 20 or 10 minute timer image, otherwise none | **Massage timer** sensor (0/10/20/30 min, raw value as attribute) |

Both states exist only while Home Assistant holds the connection. With the
default **Release right after each command** setting, the link closes about a second
after each command, so the light and Massage timer are usually unknown and update
only briefly after a command. The light switches on or off by sending the toggle
when the reported state differs, so it needs a reported state first. Choose **Stay connected for a while** to keep them current until
the idle timeout, at the cost of holding the bed's Bluetooth connection, which
keeps the phone app out meanwhile.

#### TEMPUR-Ergo ProSmart Air / ActiveBreeze

For beds operated with the Tempur Sleeptracker-AI app, select
**Tempur Sleeptracker-AI (ProSmart, ActiveBreeze)** (see [its guide](sleeptracker.md)).
That profile provides the app's named presets, ActiveBreeze heat/cool controls
and premium 28 Hz / 40 Hz massage. Adjustable Lite is not the Tempur app profile.

The Adjustable Lite massage override from
[PR #671](https://github.com/kristofferR/ha-adjustable-bed/pull/671) and the local
KSSF05C preset workaround are removed.

Select the Sleeptracker processor's actual Bluetooth endpoint when adding the
Tempur profile. A `KSSF05C` / MC232SC name identifies neither that endpoint nor
the app layout. Changing an existing UART entry's profile alone cannot turn it
into the framed-JSON processor. See the [processor setup guide](sleeptracker.md#select-the-processor).

#### Evidence

The app does not decode whether the light button toggles, how the timer button
cycles, massage level limits, or the unit of the raw timer value; those remain to
be confirmed on hardware.

### Simon Li, Heal Every Night and OKIN-Seating Profiles

**App:** Simon Li 1.0.1 (2), `com.okin.simon`; Heal Every Night 1.0 (1), `com.okin.healeverynight`; OKIN-Seating 1.0.1 (2), `com.okin.minghua.R`

**Status:** Not yet tested

#### Setup

Answer **Adjustable Lite, Simon Li, Heal Every Night or OKIN-Seating app** in the
[Keeson question](#home-assistant-setup), then pick **Simon Li app**,
**Heal Every Night app** or **OKIN-Seating app**. The choice is
saved as protocol variant `simon_li`, `heal_every_night` or `okin_seating`.
Detection: none. None of the apps filters its scan or reads a model, so Home
Assistant never picks one for you. Each app controls one
address, so add one entry per seat or bed. Their frames carry no side field. In a
two-address pair, separate the combined bed before changing to, from or between these
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
moves the selection. **Stop all** also sends Preset STOP while a preset is
selected; a cover stop does not, as the app's movement release does not. Stop all
and massage Off attempt every cleanup frame even if one fails or the action is
cancelled, then report the first error.

The massage page stays disabled until a timer is chosen. A timer turns zero
levels into one, then writes the timer key, the wave, head and foot levels
100 ms apart. The level sliders (head and foot 0-3, wave 1-4) and the +/- buttons
then write one frame each; +/- clamp but still write. **Massage off** (or the
timer's Off) writes head 0 and foot 0 and disables the page again, keeping the
levels. The light writes the explicit on/off key. The bed reports no light
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
end of a timed move writes it at once; **Stop all** does too.

#### Notifications

The apps enable notifications on every FFE4 characteristic and discard the bytes,
so the integration subscribes too and keeps the replies for diagnostics only.

#### Services

The `hold_control` action holds any streamed control for 0.1-60 s.

#### Evidence

Owners can help confirm
which actuators each key moves, what Home does, whether memory saves persist, the
Heal massage and light semantics, and the GATT layout.

### INNOVA Profile

**App:** INNOVA 2.0 (3), `com.ore.sfm`

**Status:** Not yet tested

#### Setup

Answer **Avanti, AMERICANSTAR, Bedsense Bases, ComfortFurniture, INNOVA, MaxCoil
Una or Dynasty app** in the [Keeson question](#home-assistant-setup), then pick **INNOVA
app**; it is saved as protocol variant `innova`. Detection: none. The app
scans without any name or service rule, so Auto never chooses it; `ORE-` names
stay on the Base profile. Setup asks the screen picked in the app, which sets the
motor count: 2 (2M), 3 (3M) or 4 (4M). For a two-address pair, split the pair before changing
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
shown by the **Under-bed lights** light, which sends the toggle when the reported
state differs from the one asked for. The signed timer byte `-1` sets the
**Massage timer** sensor to 0 minutes and `1`/`2`/`3` show 10/20/30 minutes;
other values leave it unchanged. Both states clear when the connection ends. The app shows
the lamp only on its light page and the timer only on its other pages; Home
Assistant shows both. The app enables FFE4 locally without writing the CCCD,
so delivery after Home Assistant subscribes needs confirming on hardware.

#### Services

`hold_control` holds any streamed control for 0.1-60 s, by the names in the held
control table. The `rename` action writes the app's 18-byte `EF 02` name frame: at
most 14 characters as typed, then trimmed and non-empty.

#### Evidence

Its sibling app Bedsense Bases uses the
[ORE comfort-bed profiles](#ore-comfort-bed-profiles). Hardware still needs to
confirm the physical actuator behind each key (the 3M third motor uses lumbar IDs
beside head artwork), how long Memory A/B must be held, massage level limits and
timer cycling, and the lamp bit.

### Restonic BT Profiles

**App:** Restonic BT Remote 1.2.0 (3), `com.keeson.restonicBT`

**Status:** Not yet tested

#### Setup

The app has two remote styles, chosen by the user in its settings (A is the
default). Answer **Restonic BT app** in the [Keeson question](#home-assistant-setup),
then the remote style the app's settings show. It is saved as protocol variant `restonic_a` (remote A, 6
buttons) or `restonic_b` (remote B, 10 buttons). Neither is ever chosen
automatically: the app accepts any device
name that starts with `base-i4` or `base-i5` (case-sensitive), and those names
are shared with Member's Mark, Purple, Sleep Harmony and Cool Base, which use
different cadences, releases or frames. How discovery offers such a bed:

| Advertised name | Offered as | What a Restonic BT user does |
|-----------------|------------|------------------------------|
| `base-i4…` (with or without a dot) | Keeson, Auto (Base profile) | Answer **Restonic BT app** in the [Keeson question](#home-assistant-setup), then the style |
| `base-i5…` (any) | Cool Base | Answer **Restonic BT app** in the [Keeson question](#home-assistant-setup), then the style |

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
**Back + legs** cover. The app sends the same light frame on every press and
tracks no state, so the light is a toggle button, not a light entity. ZZZ is
exposed as a **ZZZ** button: the app does not show what it does, so it is not
mapped to anti-snore or a memory.

#### Timing

Held controls write at once and then at the refresh interval. Once controls write
a single frame when the button is pressed. Releasing any control writes the zero
frame after the app's delay. In Home Assistant, a cover or held Zero G button
press holds for **Movement per tap**, one-shot buttons press once. A Stop, a
cover's stop, or a command that replaces a running hold writes the zero frame at
once instead, and a Stop during the wait ends it. The Back + Legs cover shares its
scheduler lane with the head and foot covers, so moving or stopping either of
them interrupts it.

#### Services

`hold_control` holds any control for a chosen duration.

#### Evidence

Deferred validation for real users: the actual write mode, whether the light
toggles, what ZZZ does, how many actuators move, and whether the zero frame
stops motion and presets.

### ORE comfort-bed profiles

**App:** OKIN Comfort Bed 1.1.6 (8), `com.ore.okincomfortbed`; MaxCoil Una 1.1.0 (5), `com.ore.maxcoil`; Dynasty Bases 1.0.2 (3), `com.ore.Dynasty`; Bedsense Bases 1.1 (3), `com.ore.sfmc2bedsence`; Avanti Bases 1.0.5 (7), `com.ore.AvantiBases`; AMERICANSTAR 1.0 (1), `com.ore.americanstar`

**Status:** Not yet tested

- MaxCoil Una and Dynasty Bases ship the same `com.ore.okincomfortbed` code base.
- Bedsense Bases is a separate package, but its app has the same
  frames, screens, timing, release, massage, light and reply handling.
- The separate Avanti app confirms every command, layout, timing and reply
  behavior below as well, and so does AMERICANSTAR 1.0 (1).
- INNOVA (`com.ore.sfm`), Bedsense's sibling app, uses different frames and
  has its own [INNOVA profile](#innova-profile).

#### Setup

Choose the app by name in the bed-type list, or answer the
[Keeson question](#home-assistant-setup) with the app (`maxcoil_una`,
`dynasty_bases`, `bedsense_bases`, `avanti_bases`, `americanstar` or `okin_comfort_bed`). Setup then
asks the screen you pick in the app, which sets the **motor count**:

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
- Avanti and OKIN Comfort Bed motor layouts are per-side settings too; split
  before changing either. Their massage page is always enabled, refresh timing is fixed, and angle sensing is
  absent. Those three generic options are hidden for both apps.

The apps write big-endian `E5` frames to the last `0000ffe9-0000-1000-8000-00805f9b34fb`
found across all services (the service UUID is ignored). Controls stay unavailable
unless `0000ffe4-0000-1000-8000-00805f9b34fb` exists too. The apps never set a
write type. The effective mode is runtime data; the integration selects from
the live properties, preferring write without response when offered. There is no PIN, pairing,
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
off words, so the integration exposes an on/off under-bed light with assumed state.

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
packet. Owners can help confirm:
the physical axis for each layout (especially 2M's combined key and 4M's waist),
hold and release behavior, preset save/recall, massage levels and timer
durations, and the actual write type.


### ComfortFurniture

**App:** [ComfortFurniture](https://apkpure.com/comfortfurniture/com.ore.comfortfurniture) 2.3 (10), `com.ore.comfortfurniture`

**Status:** Not yet tested

#### Setup

Choose **ComfortFurniture app** explicitly. Detection: none.
The app lists every scanned LE device and selects an address without a name,
manufacturer or service rule. HA uses its ordinary Bluetooth setup and proxy
selection. This route fixes four axes, massage, binary light and no angle feedback.
Seating and accessory pages are separate products and do not add BED capabilities.

Both FFE9 (write) and FFE4 (notify) must exist. The last matching characteristic
of each UUID across all services wins, without assuming a parent service or
requiring the roles to share one. HA selects ATT write mode from live properties
and subscribes with its Bluetooth stack. The app leaves ATT mode at the Android
runtime default and enables notifications only locally, without writing a CCCD.
Actual properties, numeric ATT mode and peripheral subscription needs remain
unverified. There is no setup write, authentication or capability handshake.
Two separate receivers can use HA's paired infrastructure; there is no
single-address side selector.

#### Controls

Back, foot, head and waist retain the app's labels. Back+foot is the explicit
combined control. These controls share one stream and global release; there is
no arbitrary multi-axis composition. All five named presets support save and
recall. The indexed Memory action maps only to the named Memory target.
A second recall of the same selected preset sends preset stop, and so does Stop
while a preset started in the same BLE session runs; Stop preset sends it at any
time. Saves send once, without
an automatic recall. Reset keeps the app's label and asks for confirmation in the
native card. Its physical effect is unknown, so it is a diagnostic entity,
disabled by default: enable it before it appears. No factory-reset or
calibration meaning is claimed.

Massage wave and intensity are levels 1 to 3, one per bin of the app's 0-29
slider; the app's raw progress is still kept. Their physical strengths and
patterns are unknown. Level 1 is not massage off. The Massage switch's on sends
the initial command, then current wave, then current intensity; off sends its
own word and clears the timer selection. The bed never reports massage, so the
switch shows the last command it sent as assumed state until the link drops; it
cannot see the timer end the massage. The timer select offers the app's three durations
directly, so the app's timer-cycle key is not a separate button.
Light on/off is assumed from local commands, without peripheral feedback.

<!-- generated:keeson-comfortfurniture -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

#### Axis frames

| Control | Up | Down |
|---|---|---|
| back | `E5 FE 16 00 00 00 01 05` | `E5 FE 16 00 00 00 02 04` |
| feet | `E5 FE 16 00 00 00 04 02` | `E5 FE 16 00 00 00 08 FE` |
| both | `E5 FE 16 00 00 00 05 01` | `E5 FE 16 00 00 00 0A FC` |
| head | `E5 FE 16 00 00 00 10 F6` | `E5 FE 16 00 00 00 20 E6` |
| waist | `E5 FE 16 00 00 00 40 C6` | `E5 FE 16 00 00 00 80 86` |

#### Named target frames

| Target | Recall | Save |
|---|---|---|
| Zero G | `E5 FE 16 21 00 00 01 E4` | `E5 FE 16 21 00 00 11 D4` |
| Flat | `E5 FE 16 21 00 00 02 E3` | `E5 FE 16 21 00 00 12 D3` |
| AS | `E5 FE 16 21 00 00 03 E2` | `E5 FE 16 21 00 00 13 D2` |
| Reading | `E5 FE 16 21 00 00 04 E1` | `E5 FE 16 21 00 00 14 D1` |
| Memory | `E5 FE 16 21 00 00 06 DF` | `E5 FE 16 21 00 00 16 CF` |

#### Other frames

| Action | Frame |
|---|---|
| Movement release | `E5 FE 16 00 00 00 00 06` |
| Preset stop | `E5 FE 16 21 00 00 00 E5` |
| Reset label (physical effect unknown) | `E5 FE 16 FF FF FF FF 0A` |
| Massage start, initial | `E5 FE 16 10 00 00 11 E5` |
| Massage off | `E5 FE 16 10 00 00 10 E6` |
| wave bin 0 | `E5 FE 16 10 00 00 21 D5` |
| wave bin 1 | `E5 FE 16 10 00 00 22 D4` |
| wave bin 2 | `E5 FE 16 10 00 00 23 D3` |
| intensity bin 0 | `E5 FE 16 10 00 00 11 E5` |
| intensity bin 1 | `E5 FE 16 10 00 00 12 E4` |
| intensity bin 2 | `E5 FE 16 10 00 00 13 E3` |
| Timer 10 minutes | `E5 FE 16 10 00 00 30 C6` |
| Timer 20 minutes | `E5 FE 16 10 00 00 31 C5` |
| Timer 30 minutes | `E5 FE 16 10 00 00 32 C4` |
| Light off | `E5 FE 16 31 00 00 00 D5` |
| Light on | `E5 FE 16 31 00 00 01 D4` |

#### App parameters

| Parameter | Value |
|---|---|
| Held refresh | 100 ms, first write immediate |
| One-shot / release pre-send wait | 100 ms |
| Slider raw progress / default | 0..29 / 10 |
| Quantization | floor(progress / 10), bins 0..2 |
<!-- /generated -->

#### Timing

The generated app parameters apply to this route only. Finite HA holds use an
elapsed deadline; slow writes never accumulate catch-up refreshes. Leased holds
run until release or expiry. Movement always attempts the zero release
with cancellation-independent cleanup on the captured connection. Presets use a
distinct stop word. One-shots have no automatic trailing release.

HA serializes commands and keeps immutable payloads instead of reproducing the
app's mutable-characteristic queue, whose callbacks ignore failed status and
whose backlog can overwrite payloads. The app does not guarantee lifecycle STOP.
HA invalidates old commands and callbacks on disconnect; old cleanup never writes
to a replacement session. Slider preferences survive restart; timer/preset
selection is local session state, with no assertion that the bed acknowledged it.

#### Notifications

FFE4 messages are accepted only at exactly nine bytes, with no added header,
checksum, footer or fragment rules. Accessory lamp and F0 audio/fridge branches
take priority and are ignored safely rather than reproducing the app's invalid
BED-fragment casts. Remaining byte 7 values 07, 06 and 0A end held refresh.
The app sends no STOP on this incoming path; HA still performs the app's
movement release as command cleanup. No BED position, light or massage state
is decoded, and no query packet is added.

#### Services

Use the standard movement, timed movement, STOP, memory and save-memory actions.
The declared buttons and sliders expose the remaining named saves, preset stop,
qualified reset and massage actions. No raw-word or accessory action is added.

Physical reset effects, massage-bin meaning and disconnect safety need testing
on real beds.

Based on ComfortFurniture 2.3 (`com.ore.comfortfurniture`).

### OKIN Comfort Bed

**App:** [OKIN Comfort Bed](https://play.google.com/store/apps/details?id=com.ore.okincomfortbed) 1.1.6 (8), `com.ore.okincomfortbed`

**Status:** Not yet tested

Behaves as the [ORE comfort-bed profiles](#ore-comfort-bed-profiles), including
all three layouts, four recall/save destinations, massage and discrete light.

#### Setup

Choose **OKIN Comfort Bed app · Keeson** and the screen selected in the app.
The screen owns motor count independently of Bluetooth name. Massage is always
available, refresh timing is fixed and angle sensing is disabled. These fields
are set by the profile; its screen and app selection belong to each physical
receiver in a two-address pair.

Detection: none. The app accepts every nonempty named BLE device without an
advertisement filter. No new Home Assistant advertisement matcher is declared.
The last FFE9 and FFE4 characteristics across all services are required; there
is no fixed service UUID, authentication or initial command. Write mode is
selected from live GATT properties, not asserted from the APK.

#### Controls

See the generated ORE command tables above. The 2M union key, 3M head key and
4M waist key share bytes but retain different names; 4M also has lumbar keys.
Memory A/B are two slots on one receiver, not left/right selectors. There is
no single-address side control or concurrent-motor composition.

#### Timing

See [Hold and release timing](#hold-and-release-timing). Holds support a renewable
lease at the profile cadence and always attempt the zero-word release on
cancellation. The coordinator serializes immutable writes instead of reproducing
the Android mutable-characteristic FIFO bug. Save buttons replace long presses,
a Stop button replaces repeated preset taps, and the timer select directly
chooses the app's timer-cycle values. Android touch debounce, foreground and
screen-off teardown are phone UI behavior, not bed protocol requirements.

#### Notifications

The app locally registers FFE4 but writes no CCCD. It accepts only nine-byte
values, expands byte 7 to bits and discards the result. The integration performs
no subscription or state parsing for this profile, avoiding an invented CCCD
operation or unsupported positions, acknowledgements and device state. Light,
massage levels and timer indicators describe local commands only.

#### Evidence

The app's 104 command/variant vectors and 39 builder probes are in the tests, and
the shared Keeson codec reproduces every frame the app sends. Physical axes,
release behavior, memory, massage/light effects and actual GATT properties still
need testing by owners.

### Keeson layout app family

Eight apps share one controller (`beds/keeson/layout_app.py`) and the profile type
`AppProfile`. Each app is its own bed type, chosen by hand with the layout its
app shows; nothing in an advertisement selects one, except that a Serta name
suggests [Serta MP Remote](#serta-mp-remote). Each app has
its own key table: a repeated mask is a separate package receipt, not an inferred
equivalence between apps.

<!-- generated:keeson-apps -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Profile | Bed type | Layouts (default bold) | Frame | Write / notify | Rename | Clock | Wake dismissal | Alarm tables | Hold until release |
|---|---|---|---|---|---|---|---|---|---|
| [Tempur Curve](#tempur-curve) | `tempur_curve` | **standard** | K1 `E5`, little-endian | FFE9 / FFE4 | 14 UTF-16 units, trimmed | 2 s after connect, and on demand | 2 × `E1 80 04 9A`, 400 ms apart | wake byte `0x03`, marker `0x80`, 3 per table | renewable lease |
| [Q-Plus Adjustable Remote](#q-plus-adjustable-remote) | `qplus_app` | H, M1, **M2**, M3, MX | K1 `E5` (Both) or `E6` + side byte (A/B); MX: P2 6-byte | FFE9 / FFE4 / NUS TX / NUS RX | 14 UTF-16 units, outer spaces rejected | none | 4 × `E1 80 04 9A`, 200 ms apart | wake byte `0x10`, marker `0x80`, 3 per table | renewable lease |
| [Serta MP Remote](#serta-mp-remote) | `serta_mp_remote` | **standard** | K1 `E5`, little-endian | FFE9 / FFE4 | 14 UTF-16 units, trimmed | none | none | none | renewable lease |
| [Omazz Adjusto III](#omazz-adjusto-iii) | `omazz_adjusto_iii` | **RemoteB** | K1 `E5`, little-endian | FFE9 / FFE4 | none | on demand | none | wake byte `0x03`, no marker, 3 per table | renewable lease |
| [Ergomotion app](#ergomotion-app) | `ergomotion_app` | B1, **B2**, C1, D1 | K1 `E5`, little-endian | FFE9 / FFE4 | 15 UTF-16 units, trimmed | on demand | none | wake byte `0x03`, no marker, 3 per table | renewable lease |
| [ROW Control](#row-control) | `row_control` | **Elevate**, Lifestyle, Curve, Lifestyle Plus, Zero-G Box | K1 `E5`, little-endian | FFE9 / FFE4 | 15 UTF-16 units, trimmed | 2 s after connect, and on demand | 2 × `E1 80 04 9A`, 400 ms apart | wake byte `0x03`, marker `0x80`, 3 per table | renewable lease |
| [Ergo Slim](#ergo-slim) | `ergo_slim` | **A**, B, C | K1 `E5`, little-endian | FFE9 / FFE4 | 14 UTF-16 units, trimmed | at connect, and on demand | 4 × `E1 80 04 9A`, 200 ms apart | wake byte `0x03`, marker `0x80`, 3 per table | renewable lease |
| [TEMPUR AU](#tempur-au) | `tempur_au` | B1, **B2**, C1, D1, E1 | K1 `E5`, little-endian | FFE9 / FFE4 | 14 UTF-16 units, trimmed | 2 s after connect, and on demand | 2 × `E1 80 04 9A`, 400 ms apart | wake byte `0x03`, marker `0x80`, 3 per table | renewable lease |
<!-- /generated -->

#### Setup

- Select the app by name in the bed-type list and use the Bluetooth address of
  the bed. Shared services, names and manufacturer data never select an app;
  only a Serta name suggests one (see [Serta MP Remote](#serta-mp-remote)).
- Choose the layout your app shows in **App product, model or layout** (stored
  as `product_type`). A layout is a UI choice, not proof of motor count or model.
- Each side of a two-address pair keeps its own app settings. Target the native
  child device, or the paired action's `side`; conflicting child and side
  requests are rejected. Only Q-Plus offers one address as left and right
  sides, on its H, M1, M2 and M3 layouts.

##### Home Assistant setup

Choose the exact app in the bed-type picker: [Tempur Curve](#tempur-curve),
[Q-Plus Adjustable Remote](#q-plus-adjustable-remote),
[Serta MP Remote](#serta-mp-remote), [Omazz Adjusto III](#omazz-adjusto-iii),
[Ergomotion](#ergomotion-app), [ROW Control](#row-control),
[Ergo Slim](#ergo-slim), or [TEMPUR AU](#tempur-au).
Shared Bluetooth names, UUIDs and manufacturer data do not identify these apps.
Select the bed address manually when automatic discovery cannot disambiguate it.

**App product, model or layout** asks for the layout shown by the app. Q-Plus defaults to M2;
Ergomotion and TEMPUR AU default to B2; Omazz uses its RemoteB layout.
The layout fixes the available actions and source timing. It does not prove
physical motor count. The pulse count bounds a normal held-action button press;
it does not change the source 100 ms refresh interval. Serta's local angle-edit
controls instead change one degree every 200 ms and send only on release.

Q-Plus's **Both/Side A/Side B** setting controls its P1 packet selector. When
one address is shown as left and right sides, the left side sends A, the right
side B and the pair Both, whatever that setting says. MX Memory1 is an
opaque app-labelled action, with no invented physical save/recall meaning.
Serta MP's four configurable local head/foot memory targets are likewise
separate from the remote M4 key and from physical memory programming.

Each physical side owns its app layout and Serta local memory targets. Configure
a two-address pair's sides independently. Saving ordinary or shared settings retains
each declared app layout, Q-Plus A/B/Both wire selector and Serta local targets
through reload; unrelated settings from a previous protocol are removed.
Shared options do not overwrite side-owned settings. Native child-device
targeting and side conflicts follow the existing
paired rules. Only Q-Plus has a one-address left and right mapping; the app
itself gives A and B no physical side.

All eight profiles require both current-session write and notification roles.
The six profiles without position feedback keep angle sensing disabled and
still subscribe for the app's timer state. Q-Plus reports head and foot angles
on its P1 layouts, and Serta MP exposes calibrated angle feedback and direct
pulse targets. Hardware behavior remains unverified.

#### Controls

- Head and foot keys drive the **Back** and **Legs** covers. Every other key is
  an app-labelled button; held keys also accept
  [`hold_control`](../SERVICES.md#hold_control). Physical effects are unverified.
- Cover stop and **Stop all** send the zero key frame (MX: the release queries).
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

Use [`adjustable_bed.set_alarm`](../SERVICES.md#set_alarm).
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

The **Massage timer** sensor reports the app's timer in minutes: 0 when off,
else 10, 20 or 30 for timer 1, 2 or 3. Status byte `0xFF` is off; other values
leave the sensor unchanged. Packets are not reassembled, and nothing else (acknowledgement,
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

Actual bed effects and firmware interpretation are unverified.

| App | Package | Version |
|---|---|---|
| Tempur Curve | `com.ore.tempur` | 1.7 |
| Q-Plus Adjustable Remote | `com.sbi.costco` | 1.8 |
| Serta MP Remote | `com.ore.serta330` | 1.1 |
| Omazz Adjusto III | `com.sfd.Omazz` | 1.0.5 |
| Ergomotion | `com.sfd.ergomotion` | 1.6.4 |
| ROW Control | `com.sfd.row` | 2.0 |
| Ergo Slim | `com.sfd.slim` | 1.3 |
| TEMPUR AU | `com.sfd.tempur_au` | 1.6 |

### Tempur Curve

**App:** [Tempur Curve](https://play.google.com/store/apps/details?id=com.ore.tempur) 1.7, `com.ore.tempur`

**Status:** Not yet tested

Bed type `tempur_curve`, one layout. Shared behavior is in the
[Keeson layout app family](#keeson-layout-app-family).

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

**Status:** Not yet tested

Bed type `qplus_app`, for Q-Plus and SBI (South Bay International) bases sold
through Costco. Not detected automatically: these beds share their service
UUIDs with other Keeson beds, so choose the app during setup.

#### Setup

**Q-Plus bed selection** (Both, Side A or Side B, stored as `protocol_variant`
`both`, `side_a` or `side_b`) is the app's wire selector. P1 layouts (H, M1, M2,
M3) send it; MX ignores it.

A split bed on one address can get left and right sides on the P1 layouts:
choose **Add Left, Right and Both controls** in **Configure**. The left side
sends Side A, the right side Side B, and the pair's own Flat, Stop and movement
buttons send Both. The app gives A and B no physical side, so check which half
each one moves. Every other button is on each side only.

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

#### Beds set up as SBI/Q-Plus

Earlier versions saved these beds as the SBI/Q-Plus bed type. Upgrading moves
each one to this bed type:

- **Bed selection** stays: Both, Side A or Side B. A bed shown as left and
  right on one address keeps its sides, with left on A and right on B.
- **Layout** becomes H, the app layout with the keys that bed type sent: four
  motors, the light, the massage modes and TV. If the app shows another remote
  for your bed, pick it in **Configure**.
- **Back**, **Legs**, **Flat** and **Stop** are unchanged.
- **Zero gravity**, **TV**, **Toggle light** (now **Light**) and the head and
  foot massage up buttons send the same key and keep their entity IDs. TV is a
  key the app holds: a press now repeats it for the pulse count, then releases.
- **Tilt** and **Lumbar** were covers and are now up and down buttons, with the
  same keys.
- **Memory 2** is gone. Its key is the app's **Music** button on this layout,
  and TV on the M2 layout. **Massage toggle** is gone too: its key is the app's
  **Massage level** button.
- **Memory 1** is gone: the app has that key only on the MX layout, in another
  frame.
- The **Head** and **Feet** covers of a three or four motor setup repeated Back
  and Legs, the head and foot massage down buttons repeated the up buttons, and
  the under-bed light entity repeated Toggle light. They are gone.
- **Position feedback** stays, with **Read bed position** as it was saved. The
  back and legs position sliders keep their entity IDs.
- On a one-address pair, only Flat, Stop, the movement buttons and the position
  sliders remain on the pair itself. Each side keeps its own presets, light and
  massage buttons.
- New from the app: **Reading**, **Reset**, **Massage level**, the massage
  modes, **Lumbar massage**, **Dismiss wake vibration**, the massage timer
  sensor, rename and the alarm.

The bed now writes one zero key frame when it connects, as the app does, and
needs both its write and its notify characteristic.

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
- The app has no clock writer and no angle-target writer.

#### Position feedback

The P1 layouts (H, M1, M2, M3) report the head and foot positions as pulse
counts in their status notifications. **Read bed position** is on for a new
setup and adds the **Back position** (0 to 60°) and **Legs position** (0 to 32°)
sliders; [`set_position`](../SERVICES.md#movement-and-memory) accepts the same two
axes and ranges, and the Back and Legs covers travel that far. Tilt and lumbar
report nothing.

| Field | Bytes | Notes |
|-------|-------|-------|
| Head pulse count | 3-4, little-endian | 0 to 20413 for 0 to 60° |
| Foot pulse count | 5-6, little-endian | 0 to 8718 for 0 to 32° |

- A count of 32768 or more is inverted first: `65535 - count`.
- A count becomes the first degree whose table entry reaches it. The tables are
  the app's own, one entry per degree:

  ```text
  Head: 0, 327, 577, 855, 1148, 1676, 2083, 2401, 2711, 3020, 3402, 3679, 4019,
        4529, 4864, 5262, 5633, 6024, 6453, 6826, 7239, 7611, 8015, 8423, 8862,
        9240, 9632, 10029, 10404, 10840, 11245, 11640, 11976, 12351, 12752,
        13106, 13511, 13819, 14169, 14518, 14901, 15217, 15556, 15856, 16177,
        16530, 16788, 17118, 17389, 17700, 18000, 18268, 18481, 18767, 19035,
        19260, 19487, 19757, 19970, 20164, 20413
  Foot: 0, 570, 784, 968, 1150, 1372, 1653, 1837, 2062, 2283, 2494, 2755, 3015,
        3290, 3578, 3819, 4039, 4261, 4544, 4895, 5170, 5461, 5723, 6020, 6334,
        6631, 6922, 7243, 7546, 7810, 8174, 8546, 8718
  ```

- Frames shorter than seven bytes are ignored, and so is the 16-byte frame that
  starts `A5 0B 0D`: it carries the massage timer's seconds in bytes 3-4.
- MX reports no position. It is the app's P2 remote, and its status frames were
  never read for positions, so it has no sliders and `set_position` refuses it.
  Choosing MX saves **Read bed position** off.
- The app reads these counts but has no reachable screen that shows them, so
  the angles are untested on a real bed.
- A preset the app sends as one frame, such as Flat or Zero G, stays the running
  command until the reported angles have been unchanged for 2 seconds, so the
  connection is not handed back while the bed is still moving. Stop, a newer
  command or a lost link end it at once.
- With Left and Right controls on one address, the frames do not say which half
  they are from. Each side shows what was reported after its own last command.
- A Q-Plus app bed set up before this was added keeps positions unread until
  **Read bed position** is turned on in **Configure**.

#### Services

The app's snooze stores 55 + 10 as minute 65 without carrying. The alarm action
requires a valid HH:MM, so an automation must normalize the time first. Phone
alarm scheduling stays outside the integration.

### Serta MP Remote

**App:** [Serta MP Remote](https://play.google.com/store/apps/details?id=com.ore.serta330) 1.1, `com.ore.serta330`

**Status:** Not yet tested

Bed type `serta_mp_remote`, one layout. `SertaMPRemoteController` adds
calibrated position feedback, pulse targets and four local memories to the
shared controller. The app has no clock writer and no alarm tables.

#### Setup

Detection suggests this bed type for a name containing `serta` or `motion
perfect`. A name starting `serta-i` is an [Ergomotion](#ergomotion) bed. The app
also supports classic Bluetooth (SPP UUID
`00001101-0000-1000-8000-00805F9B34FB`); this profile uses BLE only, and needs
the app's write and notification characteristics (FFE9 and FFE4).

#### Beds set up as Serta Motion Perfect

Earlier versions saved these beds as the Serta Motion Perfect bed type, or as
a Keeson bed with the Serta remote. Upgrading moves each one to this bed type:

- **Back** and **Legs** replace the Head and Feet covers, with the same keys
  and entity IDs. **Flat** and **Stop all** are unchanged.
- **Zero gravity**, **Massage level** (was Massage toggle), **Massage timer**
  and the head and foot massage up and down buttons send the same key and keep
  their entity IDs.
- **Memory 1** to **Memory 4** keep their entity IDs and now recall the app's
  own memories: a head and a foot angle each, set in **Configure** if you
  changed them in the app. Before, Memory 1, 2 and 3 sent the keys of the
  app's **Lounge**, **TV** and **M4** buttons, which are buttons of their own
  now. Memory 4 sent a key the app does not have.
- **Tilt** and **Lumbar** were covers on a three or four motor setup and are
  now up and down buttons, with the same keys.
- **Toggle light** and the under-bed light entity are gone: the app has no
  light key. The head and foot massage toggle buttons repeated the up buttons,
  and **Massage intensity up** and **down** sent a head and a foot key each;
  they are gone too.
- **Position feedback** is new: the bed reports its back and legs angles, and
  has position sliders. The app's session needs the bed's notification
  characteristic, so a bed without it no longer connects. Such a bed is not a
  Serta MP Remote bed: pick its remote under **Keeson** in **Reconfigure**.
- New from the app: **Lounge**, **TV**, **M4**, the **Step head** and **Step
  foot** buttons, **Reset**, the massage timer sensor and rename.

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
- A recall, a position target or a one-frame preset stays the running command
  until the reported angles have been unchanged for 2 seconds, so the
  connection is not handed back while the bed is still moving. Stop, a newer
  command or a lost link end it at once.

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

**Status:** Not yet tested

Bed type `omazz_adjusto_iii`, one layout. The app has no name writer,
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

**Status:** Not yet tested

Bed type `ergomotion_app` (setup label **Ergomotion app**). It is separate from
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

**Status:** Not yet tested

Bed type `row_control`. The Zero-G Box layout has no **Massage timer** sensor.

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

**Status:** Not yet tested

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

**Status:** Not yet tested

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
documented below; Malouf legacy OKIN and Sleepy's BOX15 share a guide with
frames of other families and keep it.

<!-- generated:keeson-controllers -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Profile | Bed type | Frame | Word `0x1` | Zero word | Hold until release | Guide |
|---|---|---|---|---|---|---|
| BetterLiving2 P1, 2 motors | `betterliving2`, P1, 2 motors | K1 `E5`, big-endian | `E5 FE 16 00 00 00 01 05` | `E5 FE 16 00 00 00 00 06` | renewable lease | [BetterLiving2](#betterliving2) |
| BetterLiving2 P1, 3 motors | `betterliving2`, P1, 3 motors | K1 `E5`, big-endian | `E5 FE 16 00 00 00 01 05` | `E5 FE 16 00 00 00 00 06` | renewable lease | [BetterLiving2](#betterliving2) |
| BetterLiving2 P2, 2 motors | `betterliving2`, P2, 2 motors | K1 `E6`, little-endian, side `00` | `E6 FE 16 01 00 00 00 00 04` | `E6 FE 16 00 00 00 00 00 05` | renewable lease | [BetterLiving2](#betterliving2) |
| BetterLiving2 P2, 3 motors | `betterliving2`, P2, 3 motors | K1 `E6`, little-endian, side `00` | `E6 FE 16 01 00 00 00 00 04` | `E6 FE 16 00 00 00 00 00 05` | renewable lease | [BetterLiving2](#betterliving2) |
| BetterLiving2 P3, 2 motors | `betterliving2`, P3, 2 motors | P2 7-byte (`05`) | `05 02 00 00 00 01 00` | `05 02 00 00 00 00 00` | renewable lease | [BetterLiving2](#betterliving2) |
| BetterLiving2 P3, 3 motors | `betterliving2`, P3, 3 motors | P2 7-byte (`05`) | `05 02 00 00 00 01 00` | `05 02 00 00 00 00 00` | renewable lease | [BetterLiving2](#betterliving2) |
| ComfortFurniture | `keeson:comfortfurniture` | K1 `E5`, big-endian | `E5 FE 16 00 00 00 01 05` | `E5 FE 16 00 00 00 00 06` | renewable lease | [ComfortFurniture](#comfortfurniture) |
| ORE Ultramatic | `keeson`, `ore_ultramatic` | K1 `E5`, big-endian | `E5 FE 16 00 00 00 01 05` | `E5 FE 16 00 00 00 00 06` | renewable lease | [ORE Ultramatic](#ore-ultramatic) |
| Leva Sleep | `keeson`, `leva_sleep` | K1 `E5`, big-endian | `E5 FE 16 00 00 00 01 05` | `E5 FE 16 00 00 00 00 06` | renewable lease | [Leva Sleep](#leva-sleep) |
| アシステック P1 | `yamada`, P1 | K1 `E6`, little-endian, side `00` | `E6 FE 16 01 00 00 00 00 04` | `E6 FE 16 00 00 00 00 00 05` | renewable lease | [アシステック](#アシステック--yamada) |
| アシステック P2 | `yamada`, P2 | P2 7-byte (`05`) | `05 02 00 00 00 01 00` | `05 02 00 00 00 00 00` | renewable lease | [アシステック](#アシステック--yamada) |
| OkinComfortBed II P1 | `jalon` | K1 `E6`, little-endian, side `00` | `E6 FE 16 01 00 00 00 00 04` | `E6 FE 16 00 00 00 00 00 05` | renewable lease | [OkinComfortBed II](#okincomfortbed-ii) |
| OkinComfortBed II P2 | `jalon` | K1 `E6`, little-endian, side `00` | `E6 FE 16 01 00 00 00 00 04` | `E6 FE 16 00 00 00 00 00 05` | renewable lease | [OkinComfortBed II](#okincomfortbed-ii) |
| OkinComfortBed II P3 | `jalon` | P2 7-byte (`05`) | `05 02 00 00 00 01 00` | `05 02 00 00 00 00 00` | renewable lease | [OkinComfortBed II](#okincomfortbed-ii) |
| OkinComfortBed Ⅱ (Jalon) | `jalon_bed` | K1 `E6`, little-endian, model `00` | `E6 FE 16 01 00 00 00 00 04` | `E6 FE 16 00 00 00 00 00 05` | renewable lease | [OkinComfortBed Ⅱ (Jalon)](#okincomfortbed-ⅱ-jalon) |
| Glideaway Motion | `glideaway_motion` | K1 `E6`, little-endian, side `00` | `E6 FE 16 01 00 00 00 00 04` | `E6 FE 16 00 00 00 00 00 05` | renewable lease | [Glideaway Motion](#glideaway-motion) |
| Malouf legacy OKIN | `malouf_legacy_okin` | K1 `E6`, little-endian, side `00` | `E6 FE 16 01 00 00 00 00 04` | `E6 FE 16 00 00 00 00 00 05` | renewable lease | [Malouf](malouf.md) |
| Sleepy's BOX15 | `sleepys_box15` | K1 `E6`, little-endian, side `00` | `E6 FE 16 01 00 00 00 00 04` | `E6 FE 16 00 00 00 00 00 05` | no | [Sleepy's](sleepys.md) |
| Scott Living | `scott_living` | K1 `E6`, little-endian, side `01` | `E6 FE 16 01 00 00 00 01 03` | none (ends refresh) | renewable lease | [Scott Living](#scott-living) |
| AdjustaMattress P1 | `adjustamattress`, model P1 | K1 `E6`, little-endian, side `00` | `E6 FE 16 01 00 00 00 00 04` | `E6 FE 16 00 00 00 00 00 05` | renewable lease | [AdjustaMattress](#adjustamattress) |
| AdjustaMattress P2 | `adjustamattress`, model P2 | K1 `E5`, big-endian | `E5 FE 16 00 00 00 01 05` | `E5 FE 16 00 00 00 00 06` | renewable lease | [AdjustaMattress](#adjustamattress) |
| Rondure | `rondure` | K1 `E5`, little-endian (A/B: `E6`, side `01`/`02`) | `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` | no | [Rondure](#rondure) |
| Cool Base | `coolbase` | K1 `E5`, little-endian | `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` | renewable lease | [Cool Base](#cool-base) |
| BF | `bf` | K1 `E5`, big-endian | `E5 FE 16 00 00 00 01 05` | `E5 FE 16 00 00 00 00 06` | renewable lease | [BF and Cherish](#bf-and-cherish) |
| Cherish | `cherish` | K1 `E5`, big-endian | `E5 FE 16 00 00 00 01 05` | `E5 FE 16 00 00 00 00 06` | renewable lease | [BF and Cherish](#bf-and-cherish) |
| OkimattMotion | `okimattmotion` | K1 `E5`, big-endian | `E5 FE 16 00 00 00 01 05` | `E5 FE 16 00 00 00 00 06` | renewable lease | [OkimattMotion](#okimattmotion) |
| ComfortBaseForBluetooth | `comfortbase` | K1 `E6`, little-endian, side `00` | `E6 FE 16 01 00 00 00 00 04` | `E6 FE 16 00 00 00 00 00 05` | renewable lease | [ComfortBaseForBluetooth](#comfortbaseforbluetooth) |
| Comfort Enhancements | `comfort_enhancements` | K1 `E5`, big-endian | `E5 FE 16 00 00 00 01 05` | `E5 FE 16 00 00 00 00 06` | renewable lease | [Comfort Enhancements](#comfort-enhancements) |
<!-- /generated -->

### Glideaway Motion

**App:** [Glideaway Motion](https://play.google.com/store/apps/details?id=com.ore.bedding.glideawaymontion) 1.0.3 (code 11), `com.ore.bedding.glideawaymontion`

**Status:** Not yet tested

Choose the Glideaway Motion app row for the model selected in the Android
app, such as **Glideaway Motion app (MOTION 400, GM-A4Z)** (the archive label
misspells Motion as "Montion"). It is separate from the
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
  single-address side protocol in the app.
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

`adjustable_bed.set_alarm` takes `device_id`, `enabled`, optional
`side`, `time` (required when enabling) and `wake_action` (`none`, `memory_1`,
`memory_2`). Disabling needs no time, and every target must be this profile.
`adjustable_bed.sync_clock` sends only the clock.

```yaml
action: adjustable_bed.set_alarm
data:
  device_id: YOUR_DEVICE_ID
  enabled: true
  time: "06:30:00"
  wake_action: memory_1
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

The app leaves combined movement and the light without a release and lets streams
outlive the page; the integration bounds every hold and releases those too,
with the same zero frame.

### Scott Living

**App:** [Scott Living](https://play.google.com/store/apps/details?id=com.keeson.scottlivingrelease) 1.0.2, `com.keeson.scottlivingrelease`

**Status:** Not yet tested on hardware

#### Setup

Choose **Scott Living**, then the layout that matches the app: A (8 buttons),
B (13 buttons), or C (17 buttons). A is the default for existing entries.
Bluetooth names beginning with case-sensitive `base` are shared with other
apps, so they do not choose this app or a layout automatically.

The receiver must expose writable FFE9 under FFE5 and notifying FFE4 under FFE0.
The write mode follows the discovered characteristic properties: without response
when offered, otherwise with response. The receiver's actual properties and
firmware acceptance still need hardware confirmation. No pairing PIN is required
by the app. Home Assistant manages the Bluetooth connection and MTU.

#### Controls

All layouts have back and legs controls plus Flat, Zero G, Reading and TV.
B adds anti-snore, a light button, head/foot massage buttons and a massage timer
button. C adds head tilt and the raw M and star buttons. M and star are utility
buttons, disabled by default. Their meaning beyond a button press is unknown;
they are not memory slots or save actions. Massage cycle levels and light state
are not inferred from taps. There is no lumbar or position control.

<!-- generated:keeson-scott-living -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Layout | Control | Word | Frame | Execution |
|---|---|---|---|---|
| A | Back up | `0x00000001` | `E6 FE 16 01 00 00 00 01 03` | held |
| A | Back down | `0x00000002` | `E6 FE 16 02 00 00 00 01 02` | held |
| A | Legs up | `0x00000004` | `E6 FE 16 04 00 00 00 01 00` | held |
| A | Legs down | `0x00000008` | `E6 FE 16 08 00 00 00 01 FC` | held |
| A | Flat | `0x08000000` | `E6 FE 16 00 00 00 08 01 FC` | single |
| A | Zero G | `0x00001000` | `E6 FE 16 00 10 00 00 01 F4` | single |
| A | Reading | `0x00002000` | `E6 FE 16 00 20 00 00 01 E4` | single |
| A | TV | `0x00004000` | `E6 FE 16 00 40 00 00 01 C4` | single |
| B | Back up | `0x00000001` | `E6 FE 16 01 00 00 00 01 03` | held |
| B | Back down | `0x00000002` | `E6 FE 16 02 00 00 00 01 02` | held |
| B | Legs up | `0x00000004` | `E6 FE 16 04 00 00 00 01 00` | held |
| B | Legs down | `0x00000008` | `E6 FE 16 08 00 00 00 01 FC` | held |
| B | Flat | `0x08000000` | `E6 FE 16 00 00 00 08 01 FC` | single |
| B | Zero G | `0x00001000` | `E6 FE 16 00 10 00 00 01 F4` | single |
| B | Reading | `0x00002000` | `E6 FE 16 00 20 00 00 01 E4` | single |
| B | TV | `0x00004000` | `E6 FE 16 00 40 00 00 01 C4` | single |
| B | Anti-snore | `0x00008000` | `E6 FE 16 00 80 00 00 01 84` | single |
| B | Light | `0x00020000` | `E6 FE 16 00 00 02 00 01 02` | single |
| B | Head massage | `0x00000800` | `E6 FE 16 00 08 00 00 01 FC` | single |
| B | Foot massage | `0x00000400` | `E6 FE 16 00 04 00 00 01 00` | single |
| B | Massage timer | `0x00000200` | `E6 FE 16 00 02 00 00 01 02` | single |
| C | Back up | `0x00000001` | `E6 FE 16 01 00 00 00 01 03` | held |
| C | Back down | `0x00000002` | `E6 FE 16 02 00 00 00 01 02` | held |
| C | Legs up | `0x00000004` | `E6 FE 16 04 00 00 00 01 00` | held |
| C | Legs down | `0x00000008` | `E6 FE 16 08 00 00 00 01 FC` | held |
| C | Flat | `0x08000000` | `E6 FE 16 00 00 00 08 01 FC` | single |
| C | Zero G | `0x00001000` | `E6 FE 16 00 10 00 00 01 F4` | single |
| C | Reading | `0x00002000` | `E6 FE 16 00 20 00 00 01 E4` | single |
| C | TV | `0x00004000` | `E6 FE 16 00 40 00 00 01 C4` | single |
| C | Anti-snore | `0x00008000` | `E6 FE 16 00 80 00 00 01 84` | single |
| C | Light | `0x00020000` | `E6 FE 16 00 00 02 00 01 02` | single |
| C | Head massage | `0x00000800` | `E6 FE 16 00 08 00 00 01 FC` | single |
| C | Foot massage | `0x00000400` | `E6 FE 16 00 04 00 00 01 00` | single |
| C | Massage timer | `0x00000200` | `E6 FE 16 00 02 00 00 01 02` | single |
| C | Head tilt up | `0x00000010` | `E6 FE 16 10 00 00 00 01 F4` | held |
| C | Head tilt down | `0x00000020` | `E6 FE 16 20 00 00 00 01 E4` | held |
| C | M button | `0x40000000` | `E6 FE 16 00 00 00 40 01 C4` | single |
| C | Star button | `0x00010000` | `E6 FE 16 00 00 01 00 01 03` | single |

| Behavior | Timing |
|---|---|
| Held refresh / post-notify query wait | 100 ms |
| Clicks / release frames | 1 / none |

| Bluetooth name | UTF-8 query bytes |
|---|---|
| base00000000 | `37 44 30 45 30 30 30 30 30 30 30 30 30 30 41 42 35 34 37 35` |
| base12345678 | `37 44 30 45 30 30 31 32 33 34 35 36 37 38 41 42 35 34 66 66 66 66 66 66 36 31` |
| base00000070 | `37 44 30 45 30 30 30 30 30 30 30 30 37 30 41 42 35 34 35` |
| baseFFFFFFFF | `37 44 30 45 30 30 46 46 46 46 46 46 46 46 41 42 35 34 66 66 66 66 66 63 37 39` |
| base | `37 44 30 45 30 30 41 42 35 34 37 35` |
<!-- /generated -->

#### Timing

Movement refreshes immediately and then at the fixed interval in the generated
table. Releasing a hold, cancelling, or pressing Stop ends refresh and fences
pending work on the original connection. No release or STOP bytes are sent,
and Stop does not reconnect. The physical stopping delay and aborting an
already-triggered preset remain unverified. Presets and utility buttons each
send one frame.

After notification subscription, startup waits once and sends the generated
UTF-8 query. This is ASCII text, not hex-decoded bytes, including its unusual
unpadded checksum. A non-hex name suffix can fail startup; it is never replaced
with an invented device identifier. Query replies do not select a layout or
unlock commands.

#### Notifications

B and C accept complete checksum-valid timer notifications and display the app's
0/10/20/30 timer indicator. These labels are not countdown minutes: both layouts
compare signed little-endian milliseconds at offsets 9–12 against the same
60/120/180-second thresholds, within ten seconds. An unmatched value leaves the
last indicator unchanged. The light byte is discarded. A publishes no timer.
Malformed short packets are ignored, and old-link callbacks cannot update state.
No position, capability or acknowledgement parser is available.

#### Services

Use the cover entities for movement, the button entities for presets and utility
controls, and `adjustable_bed.hold_control` for a bounded held control. Memory,
clock, alarm and rename actions are unavailable for this app.

#### Evidence

Based on Scott Living 1.0.2 (25). Hardware behavior remains unverified.

### Malouf legacy OKIN, Sleepy's BOX15, AdjustaMattress P1 and P2

These routes build their E6 (AdjustaMattress P2: big-endian E5) frames through
this codec. Malouf legacy OKIN and Sleepy's BOX15 keep the rest of their guides;
AdjustaMattress has its own [section](#adjustamattress):

- [Malouf legacy OKIN](malouf.md) (`malouf_legacy_okin`): Malouf words, side
  byte `00`; the configured pulse settings, then the zero frame.
- [Sleepy's BOX15](sleepys.md) (`sleepys_box15`): the motor byte is the word's
  first byte, the preset bytes its second and fourth.
- [AdjustaMattress](#adjustamattress) (`adjustamattress`): models P1 (E6) and
  P2 (big-endian E5). Models P3 and P4 send Okin N-frames.

[SIMMONS](okin-nframe.md#simmons) names starting `okin` also send the E6 frame
through `codec.frame`; that bed type is a profile of the Okin N-frame family.

### FurniMove

FurniMove builds its gateway
(`E5 FE 16`), plain (`04 02`) and dot (`05 02`) frames through this codec too and
keeps its [own guide](furnimove.md), because its handset catalog is its profile.

### Rondure

**Status:** Not yet tested

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

Manual bed type selection required. The service UUID `0000ffe0-...` is shared with many other bed types (Solace, Octo, etc.), so it cannot be detected automatically.

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

For split-king beds, choose the side under **Bed model or remote**:

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

**Status:** Tested (a DewertOkin bed on this route in [discussion #341](https://github.com/kristofferR/ha-adjustable-bed/discussions/341))

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

#### Known Models

- Cool Base adjustable bed bases (Keeson BaseI5 with cooling fan)
- DewertOKIN `OKIN-BLE` / `BTCB` controllers that use the same 8-byte packet
  format without fan controls

#### Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | Cool Base 1.0.0 (3) | `com.keeson.coolbase` |

The Cool Base profile follows this app. Hardware behavior is unverified.

#### Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (2 motors: head, foot) |
| Position Feedback | ❌ |
| Memory Presets | Cool Base: ❌ (the app's star button is not known to be a memory; exposed as **Star**). DewertOKIN OKIN-BLE: 2 slots |
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

**Status:** Not yet tested

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

#### Known Models

- Beds controlled by the BF app (`com.BF`, three motors)
- Beds controlled by the Cherish app (`com.okin.ore.cherish`)

#### Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [BF](https://play.google.com/store/apps/details?id=com.BF) 1.2.3 (11) | `com.BF` |
| ✅ | [Cherish](https://play.google.com/store/apps/details?id=com.okin.ore.cherish) 1.0.4 (5) | `com.okin.ore.cherish` |

- Support comes from both apps (see [Analysis provenance](#bf-and-cherish-analysis-provenance)).
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

- Choose **BF app** (`com.BF`, three motors) or **Cherish app**
  (`com.okin.ore.cherish`) in manual setup.
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
[`beds/bf_cherish/controller.py`](../../custom_components/adjustable_bed/beds/bf_cherish/controller.py).

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
- The timer is the app's three buttons, 10, 20 and 30 minutes, with no off
  choice; massage is stopped with Off.
- Selecting a timer sends only its timer command and disables level changes
  until massage is started again; it does not prove that the receiver stopped
  massage.
- There is no massage feedback.
- HA serializes these sequences and finishes cancellation cleanup, so an
  Android delayed callback cannot restart massage after Off.

#### Alarm action

```yaml
action: adjustable_bed.set_alarm
data:
  device_id: YOUR_DEVICE_ID
  enabled: true
  time: "08:30:00"
  wake_action: memory_1
```

- `wake_action` is `none`, `memory_1` (A), or `memory_2` (B), never a bed side.
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

- The **Alarm** sensor exposes the last command or BF report, with time,
  memory, raw BF selector and source attributes.
- Cherish intent persists across HA restarts; expiry clears its local enabled
  indication. It does not restore phone alarms or infer receiver state.
- BF's **Refresh alarm** button sends the live E2 clock query.
- Cherish has no query or alarm notification handler in the app, so neither is
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
- No failure, disconnect or timeout alone means the bed stopped.

##### Scope

Wi-Fi provisioning, SSID/passwords, bed network administration, cloud/account
services and unrelated phone infrastructure are outside this BLE integration.

##### Hardware Status

**Hardware status:** needs testing.

- Physical posture, stopping distance, alarm recurrence and successful on-air
  delivery are not yet confirmed; captures from owners help.

##### BF and Cherish analysis provenance

Based on BF 1.2.3 (`com.BF`) and Cherish 1.0.4 (`com.okin.ore.cherish`).

### Comfort Enhancements

**Status:** Not yet tested

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
| Alarm | ✅ (`adjustable_bed.set_alarm`) |
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

1. Choose **Comfort Enhancements app** manually, then MC2, MC3, MC4 or MC5.
2. Select the screen used in the Android app.

- Shared Bluetooth names and services do not identify this app or its layout.
  No automatic layout is available.
- The layout controls feature availability, independently of the generic motor
  count.
- A two-address pair keeps each physical bed's layout; separate the combined bed before changing
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
`adjustable_bed.set_alarm` programs or disables the BLE
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
- A successful write is not an acknowledgement of the alarm setting from the bed.

#### Notifications / State

- The app's live notify callback compares lowercase hex against uppercase
  `E2FE16`, rejecting all inputs. Its unused parser lacks a known reply
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
- **Hardware status:** needs testing. Owners can help confirm movement labels,
  release, massage and alarms.

##### Comfort Enhancements analysis provenance

Based on Comfort Enhancements 1.0.3 (`com.okin.enhancements`).

### Ergomotion 4.0

**App:** [Ergomotion 4.0](https://play.google.com/store/apps/details?id=com.sfd.hump) 3.7 (65), `com.sfd.hump`

**Status:** Not yet tested

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

The `ergomotion_4` bed type is an app profile over this codec, like the
[Keeson layout apps](#keeson-layout-app-family). This codec builds every frame it
sends: the K1 and side frames for P1 products, the `04 02` frames and status
query for P2 products, and its custom massage and RGB frames. Its product
catalog, not the profile, picks the keys each product sends. Its test vectors
are the `ergomotion_4` entry of `tests/keeson_vectors.py`.

#### Setup

##### Ergomotion 4.0 known models

The app's built-in products H, M1–M22 and M30/EZI MAID, plus the 21 products
in the offline catalog acquired on 2026-11-03. The product table below gives
the exact choices. App labels do not tell how many motors the bed has.

This is the **Ergomotion 4.0** app (`com.sfd.hump`), distinct from the older
[Ergomotion app](#ergomotion-app) B1/B2/C1/D1 profiles. Existing
[Keeson and Ergomotion profiles](#keeson) keep their controls and entities.

##### Ergomotion 4.0 apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Ergomotion 4.0](https://play.google.com/store/apps/details?id=com.sfd.hump) 3.7 (65) | `com.sfd.hump` |

##### Ergomotion 4.0 protocol details

**Write characteristics:** FFE9, Nordic UART `6e400002-b5a3-f393-e0a9-e50e24dcca9e`,
`6e400021-b5a3-f393-e0a9-e50e24dcca9e`, or
`6e400002-b5a3-f393-e0a9-38534c454550`.

**Notify characteristics:** FFE4, Nordic UART `6e400003-b5a3-f393-e0a9-e50e24dcca9e`,
`6e400022-b5a3-f393-e0a9-e50e24dcca9e`,
`6e400027-b5a3-f393-e0a9-e50e24dcca9e`, or
`6e400003-b5a3-f393-e0a9-38534c454550`.
FFE4/FFE9 expand to `0000xxxx-0000-1000-8000-00805f9b34fb`.
No service UUID chooses a product. The last matching write characteristic across
all services is selected, and all matching notification characteristics are
subscribed. The `38534c454550` notification suffix is captured for diagnostics
but ignored by the app-state parser, as in the app.

###### Ergomotion 4.0 packet format

[`codec/keeson.py`](../../custom_components/adjustable_bed/codec/keeson.py)
builds every frame below as the `ergomotion_4` Keeson app profile; the product
catalog picks which keys each product sends.

| Route | Format |
|-------|--------|
| P1 Both | `E5 FE 16 key_le32 checksum` (8 bytes) |
| P1 Left | `E6 FE 16 key_le32 02 checksum` (9 bytes) |
| P1 Right | `E6 FE 16 key_le32 01 checksum` (9 bytes) |
| P2 | `04 02 key_be32` (6 bytes), only the finite shipped key switch |
| Status query | `00 B0`, distinct from the P2 zero-key builder |
| Custom massage | `07 D0` plus seven parameter bytes |
| RGB1 | `09 0A 00 02 00 00 01 R G B 00` |
| RGB2 | `0A 02 00 00 00 00 01 01 BB (255-R) (255-G) (255-B) 00` |

P1 uses the low 32 key bits. Its checksum is `(~sum(previous_bytes)) & 0xFF`.
P2 has no checksum, side field or trailing byte. Unsupported keys map to the
builder's zero frame; no arbitrary command service is exposed. Only generic
product names containing `4194` use inverted RGB2. Fixed M16/M19 callbacks
always use RGB1.

###### Ergomotion 4.0 write mode

The app leaves Android's characteristic write type unchanged. Home Assistant
writes with response when supported, otherwise without response. It serializes
immutable frames through the existing BLE command lane; it does not reproduce
the app's mutable-characteristic queue or its queue-overflow disconnect defect.
No normal-control PIN, bonding exchange, MTU request or authentication frame
was found.

##### Ergomotion 4.0 detection and setup

1. Answer **Ergomotion, Ergomotion 4.0 or Serta MP Remote app** in the
   [Keeson question](#home-assistant-setup), then pick **Ergomotion 4.0 app**.
2. Select the exact product/layout shown by the app. Shared UUIDs and names
   never pick this profile or its product automatically.
3. To control one P1 receiver's split sides, open **Configure** and choose
   **Add Left, Right and Both controls**. Use the native Left and Right child
   devices, or the parent's Both controls. Revert with **Remove Left, Right
   and Both controls** in Configure when needed. P2 products do not offer this option.
   Remove the Left, Right and Both controls before changing from P1 to P2.

For an existing Keeson entry, select **Member's Mark base (BaseI4 / BaseI5)** or
**Ergomotion base (reports positions)** before enabling side controls. Do this
through **Reconfigure** in the entry's three-dot menu, under the Keeson
question's **No app: another Keeson remote** answer; Configure refuses a
Keeson route change. An existing Ergomotion bed-type
entry also offers the option. Auto is excluded from the menu because it may
resolve to an incompatible JSON or P2 profile at connection time. Choose the
new explicit app profile to use the complete 3.7 controls instead.

Legacy Keeson/Ergomotion feedback has no side ownership, so side-control mode
disables position feedback and position seeking. Movement controls remain
available. Restoring standalone controls restores the saved feedback setting.

The Android 3.7 settings radio stores A/B, but its P1 builder only recognizes
Left/Right. Those A/B values incorrectly produce side byte `00`. HA deliberately
uses the app's Left=`02` and Right=`01` builder branches, never that app defect.
Confirm which physical half corresponds to Left/Right; the
reporter has not provided a support bundle or a confirmed receiver profile.
For two independently advertising receivers, use the existing two-address
combined-bed workflow instead.

**Other catalog product** accepts the exact product name, ordered model keys,
massage keys, light and RGB flags from that product's catalog record. It is an
explicit capability selection, not an online lookup. `k1/k2/k3` select simple
head/foot/flat; `o1/o2/o3/o4` select anti-snore/memory/relax/TV in incoming
order. Three preset slots are visible unless all `o1`–`o4` occur, which
selects four slots. `o5` consumes a slot but has no command. Simple layouts take precedence, then
`m10` dual-head, then `m7/m8/m9` head-tilt/waist/foot-tilt. Massage levels
`m3+m4` take precedence over two-zone `m5+m6` or either singleton zone.
`m1` shows timer and `m1+m2` also shows massage stop. Copy only the exact
product's keys, without combining products.

The built-in **M22** choice represents a persisted-only legacy layout; it is not
in the app's current popup. EZI MAID is an alias of M30. A trailing space in
`ErgoBalance100 ` is significant in the catalog.

###### Ergomotion 4.0 products

| Choice | App label | Frame family |
|--------|-----------|--------------|

| `H` | H (H) | P1 |
| `M10` | 4166 (M10) | P2 |
| `M11` | 8200 (M11) | P2 |
| `M13` | 8280 (M13) | P1 |
| `M14` | 822H (M14) | P2 |
| `M15` | Rio 2.0/3.0 (M15) | P2 |
| `M16` | M16 (M16) | P2 |
| `M17` | 5620 (M17) | P2 |
| `M18` | 567H Flex2 (M18) | P2 |
| `M19` | 4193 RGB (M19) | P2 |
| `M20` | 567H Flex1 (M20) | P2 |
| `M21` | Flex3 Lumbar (M21) | P2 |
| `M22` | M22 (legacy saved layout) | P2 |
| `M2` | M2 (M2) | P1 |
| `M12` | Euro Mattress (M12) | P1 |
| `M30` | EZI MAID (M30) | P2 |
| `M3` | M3 (M3) | P1 |
| `M4` | M4 (M4) | P1 |
| `M5` | M5 (M5) | P1 |
| `M6` | M6 (M6) | P1 |
| `M7` | Symbol Mattress (M7) | P1 |
| `M8` | 6910 (M8) | P2 |
| `M9` | 3350 (M9) | P2 |
| `M1` | M1 (M1) | P1 |
| `20th Anniversary` | 20th Anniversary | P2 |
| `4180` | 4180 | P2 |
| `4184` | 4184 | P2 |
| `4193` | 4193 | P2 |
| `4194RGB` | 4194RGB | P2 |
| `828` | 828 | P2 |
| `Aeroflex-4308` | Aeroflex-4308 | P2 |
| `Aeroflex-5623` | Aeroflex-5623 | P2 |
| `Chaide 4166` | Chaide 4166 | P2 |
| `EZI MAID` | EZI MAID | P2 |
| `ErgoBalance Pro-4168+` | ErgoBalance Pro-4168+ | P2 |
| `ErgoBalance-4168` | ErgoBalance-4168 | P2 |
| `ErgoBalance100 ` | ErgoBalance100 | P2 |
| `ErgoBasic-4087` | ErgoBasic-4087 | P2 |
| `ErgoDuetto-4367/4364` | ErgoDuetto-4367/4364 | P2 |
| `Ergocomfort 5680/568H` | Ergocomfort 5680/568H | P2 |
| `Flex3 Massage` | Flex3 Massage | P2 |
| `Ortobom 3350` | Ortobom 3350 | P2 |
| `Rosen 4165` | Rosen 4165 | P2 |
| `SIMONS SA 3410S` | SIMONS SA 3410S | P2 |
| `SMART TEC-4193` | SMART TEC-4193 | P2 |

###### Ergomotion 4.0 Home Assistant setup

Choose **Ergomotion 4.0 app** and the exact product shown in
the app. This is separate from the older Ergomotion app's B1/B2/C1/D1 layouts.
The [product guide](#ergomotion-40-products) lists all built-in choices and
the 21 catalog products. Other catalog product accepts that product's
exact name and ordered feature keys, without connecting to a vendor account.
Motor pulse count bounds each held action at the app's fixed 100 ms cadence.

For a P1 receiver with one address, **Add Left, Right and Both controls** in
**Configure** adds Left/Right child devices and native Both controls. Existing
Keeson entries can use this after selecting BaseI4/BaseI5 or Ergomotion through
**Reconfigure**; the Ergomotion bed type also supports it. Auto and
P2/JSON/OEM profiles are ineligible. Choose **Remove Left, Right and Both controls**
before changing to a profile without a side field. Existing
standalone profiles and entities retain their behavior.

Legacy Keeson/Ergomotion position feedback cannot identify a side. Side-control
mode disables position sliders, sensors and position seeking for these profiles;
movement controls remain available. Restoring standalone controls restores the
stored position-feedback preference.

HA uses the app builder's Left=`02` and Right=`01` branches. The Android app's
A/B radio labels do not tell which physical side is which and contain a selector
mismatch. Confirm the halves with the real bed. For two
separately advertising receivers, use the ordinary two-address combined bed.

#### Controls

##### Ergomotion 4.0 features

| Feature | Supported |
|---------|-----------|
| Motor control | ✅ Exact product-labelled held buttons, including dual-head and tilt/waist layouts |
| Hold until release | ✅ Every held button, as a [renewable hold](../SERVICES.md#renewable-holds) through `hold_control` |
| Split sides | ✅ Opt-in Left / Right / Both for P1 products, one Bluetooth address |
| P2 split sides | ❌ No side field in this six-byte protocol |
| Presets and memory | ✅ Product-labelled buttons; no invented memory slots or programming |
| Massage | ✅ Product-specific steps, modes, timer, stop and nine custom patterns |
| Lights | ✅ One light where the status reports it (RGB, M16, M19 and custom products), otherwise the product's toggle button; RGB and three brightness levels on eligible products |
| Position feedback | ❌ No measured motor positions in this app |
| Reported state | ✅ Massage timer, light state and RGB where reported |
| Local bed configuration | ✅ Rename, clock sync, two three-slot alarm tables and wake-vibration dismissal |
| Meditation | ✅ BLE start/stop on the four eligible product/name routes; repeat using HA automations |

##### Ergomotion 4.0 commands

Every control below is exposed as a named HA button and appears in the card's
Actions section. Held controls include hold metadata and work with
`adjustable_bed.hold_control`. The control key is shown for automation use.
The table contains exactly the frames and sequences shipped in the controller.
P1 examples show Both; a side-bound action replaces every P1 frame, including
release, with the nine-byte frame for that same side.

`query ×3` means `00 B0` at +300/+600/+900 ms. `hold` means write immediately,
then every 100 ms until the bounded hold ends. A regular button/cover-sized
burst uses motor pulse count ×100 ms; `hold_control` accepts 1–60000 ms.
A source reset chord is exposed as its own held **Reset chord** button.

| Source control | HA control key | Label | Press bytes / sequence | Release |
|----------------|----------------|-------|------------------------|---------|
| C001 | `c001` | Foot down | hold `04 02 00 00 00 08` | query ×3 |
| C002 | `c002` | Foot down double | hold `04 02 00 00 00 20` | query ×3 |
| C003 | `c003` | Foot down simple | hold `04 02 00 00 00 08` | query ×3 |
| C004 | `c004` | Foot tilt down | hold `04 02 00 00 00 A0` | query ×3 |
| C005 | `c005` | Foot tilt up | hold `04 02 00 00 00 50` | query ×3 |
| C006 | `c006` | Foot up | hold `04 02 00 00 00 04` | query ×3 |
| C007 | `c007` | Foot up double | hold `04 02 00 00 00 10` | query ×3 |
| C008 | `c008` | Foot up simple | hold `04 02 00 00 00 04` | query ×3 |
| C009 | `c009` | Head down | hold `04 02 00 00 00 02` | query ×3 |
| C010 | `c010` | Head down side1 | hold `04 02 00 00 00 02` | query ×3 |
| C011 | `c011` | Head down side2 | hold `04 02 00 00 00 08` | query ×3 |
| C012 | `c012` | Head down simple | hold `04 02 00 00 00 02` | query ×3 |
| C013 | `c013` | Head tilt down | hold `04 02 00 00 00 20` | query ×3 |
| C014 | `c014` | Head tilt up | hold `04 02 00 00 00 10` | query ×3 |
| C015 | `c015` | Head up | hold `04 02 00 00 00 01` | query ×3 |
| C016 | `c016` | Head up side1 | hold `04 02 00 00 00 01` | query ×3 |
| C017 | `c017` | Head up side2 | hold `04 02 00 00 00 04` | query ×3 |
| C018 | `c018` | Head up simple | hold `04 02 00 00 00 01` | query ×3 |
| C019 | `c019` | Waist down | hold `04 02 00 00 00 80` | query ×3 |
| C020 | `c020` | Waist head down | hold `04 02 00 00 00 02` | query ×3 |
| C021 | `c021` | Waist head up | hold `04 02 00 00 00 01` | query ×3 |
| C022 | `c022` | Waist up | hold `04 02 00 00 00 40` | query ×3 |
| C023 | `c023` | Foot massage down | `04 02 01 00 00 00`; wait 300 ms; query ×3 | none |
| C024 | `c024` | Foot massage up | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C025 | `c025` | Head massage down | `04 02 00 80 00 00`; wait 300 ms; query ×3 | none |
| C026 | `c026` | Head massage up | `04 02 00 00 08 00`; wait 300 ms; query ×3 | none |
| C027 | `c027` | Brightness high | RGB at 100% | none |
| C028 | `c028` | Brightness low | RGB at 20% | none |
| C029 | `c029` | Brightness medium | RGB at 60% | none |
| C030 | `c030` | Flat | `04 02 08 00 00 00`; wait 500 ms; query ×3 | none |
| C031 | `c031` | Flat double | `04 02 08 00 00 00`; wait 500 ms; query ×3 | none |
| C032 | `c032` | Flat simple | `04 02 08 00 00 00`; wait 500 ms; query ×3 | none |
| C033 | `c033` | Waist flat | `04 02 08 00 00 00`; wait 500 ms; query ×3 | none |
| C034 | `c034` | Waist Zero G | `04 02 00 00 10 00` | none |
| C035 | `c035` | Zero G | `04 02 00 00 10 00` | none |
| C036 | `c036` | Zero G double | `04 02 00 00 10 00` | none |
| C037 | `c037` | Light toggle | `04 02 00 02 00 00`; wait 300 ms; query ×3 | none |
| C038 | `c038` | Foot massage | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C039 | `c039` | Foot massage | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C040 | `c040` | Head massage | `04 02 00 00 08 00`; wait 300 ms; query ×3 | none |
| C041 | `c041` | Massage stop | `04 02 02 00 00 00`; wait 300 ms; query ×3 | none |
| C042 | `c042` | Massage timer | `04 02 00 00 02 00`; wait 300 ms; query ×3 | none |
| C043 | `c043` | Anti-snore | hold `04 02 00 00 80 00` | query ×3 |
| C044 | `c044` | Memory | hold `04 02 00 01 00 00` | query ×3 |
| C045 | `c045` | Relax | hold `04 02 00 00 20 00` | query ×3 |
| C046 | `c046` | TV | hold `04 02 00 00 40 00` | query ×3 |
| C047 | `c047` | Foot down | hold `04 02 00 00 00 08` | query ×3 |
| C048 | `c048` | Foot up | hold `04 02 00 00 00 04` | query ×3 |
| C049 | `c049` | Anti Snore | hold `E5 FE 16 00 80 00 00 86` | `E5 FE 16 00 00 00 00 06` |
| C050 | `c050` | Flat | `E5 FE 16 00 00 00 08 FE` | none |
| C051 | `c051` | Foot Down | hold `E5 FE 16 08 00 00 00 FE` | `E5 FE 16 00 00 00 00 06` |
| C052 | `c052` | Foot Up | hold `E5 FE 16 04 00 00 00 02` | `E5 FE 16 00 00 00 00 06` |
| C053 | `c053` | Head Down | hold `E5 FE 16 02 00 00 00 04` | `E5 FE 16 00 00 00 00 06` |
| C054 | `c054` | Head Up | hold `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` |
| C055 | `c055` | Level | `E5 FE 16 00 01 00 00 05` | none |
| C056 | `c056` | Light | `E5 FE 16 00 00 02 00 04` | none |
| C057 | `c057` | Lumbar Down | hold `E5 FE 16 80 00 00 00 86` | `E5 FE 16 00 00 00 00 06` |
| C058 | `c058` | Lumbar Up | hold `E5 FE 16 40 00 00 00 C6` | `E5 FE 16 00 00 00 00 06` |
| C059 | `c059` | Massage Foot Add | `E5 FE 16 00 04 00 00 02`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C060 | `c060` | Massage Head Add | `E5 FE 16 00 08 00 00 FE`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C061 | `c061` | Massage Lumbar Add | `E5 FE 16 00 00 40 00 C6`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C062 | `c062` | Massage Mode1 | wait 300 ms; `E5 FE 16 00 00 00 00 06`; `E5 FE 16 00 00 10 00 F6` | none |
| C063 | `c063` | Massage Mode2 | `E5 FE 16 00 00 20 00 E6`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C064 | `c064` | Massage Mode3 | `E5 FE 16 00 00 08 00 FE`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C065 | `c065` | Read | hold `E5 FE 16 00 20 00 00 E6` | `E5 FE 16 00 00 00 00 06` |
| C066 | `c066` | Reset | hold `E5 FE 16 00 10 00 08 EE` | `E5 FE 16 00 00 00 00 06` |
| C067 | `c067` | Tilt Down | hold `E5 FE 16 20 00 00 00 E6` | `E5 FE 16 00 00 00 00 06` |
| C068 | `c068` | Tilt Up | hold `E5 FE 16 10 00 00 00 F6` | `E5 FE 16 00 00 00 00 06` |
| C069 | `c069` | Tv | hold `E5 FE 16 00 40 00 00 C6` | `E5 FE 16 00 00 00 00 06` |
| C070 | `c070` | Zero G | `E5 FE 16 00 10 00 00 F6` | none |
| C071 | `c071` | Anti Snore | hold `04 02 00 00 80 00` | query ×3 |
| C072 | `c072` | Flat | `04 02 08 00 00 00` | none |
| C073 | `c073` | Foot Down | hold `04 02 00 00 00 08` | query ×3 |
| C074 | `c074` | Foot Up | hold `04 02 00 00 00 04` | query ×3 |
| C075 | `c075` | Head Down | hold `04 02 00 00 00 02` | query ×3 |
| C076 | `c076` | Head Up | hold `04 02 00 00 00 01` | query ×3 |
| C077 | `c077` | Light | `04 02 00 02 00 00` | none |
| C078 | `c078` | Lounge | hold `04 02 00 01 00 00` | query ×3 |
| C079 | `c079` | Massage Foot Add | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C080 | `c080` | Massage Head Add | `04 02 00 00 08 00`; wait 300 ms; query ×3 | none |
| C081 | `c081` | Reset | hold `04 02 08 00 10 00` | query ×3 |
| C082 | `c082` | Timer | `04 02 04 00 00 00`; wait 300 ms; query ×3 | none |
| C083 | `c083` | Tv | hold `04 02 00 00 40 00` | query ×3 |
| C084 | `c084` | Zero G | `04 02 00 00 10 00` | none |
| C085 | `c085` | Flat | `04 02 08 00 00 00` | none |
| C085_reset | `c085_reset` | Reset chord | hold `04 02 08 00 10 00` | query ×3 |
| C086 | `c086` | Foot Down | hold `04 02 00 00 00 08` | query ×3 |
| C087 | `c087` | Foot Up | hold `04 02 00 00 00 04` | query ×3 |
| C088 | `c088` | Head Down | hold `04 02 00 00 00 02` | query ×3 |
| C089 | `c089` | Head Up | hold `04 02 00 00 00 01` | query ×3 |
| C090 | `c090` | Light | `04 02 00 02 00 00` | none |
| C091 | `c091` | Lounge | hold `04 02 00 00 20 00` | query ×3 |
| C092 | `c092` | Massage Foot Add | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C093 | `c093` | Massage Head Add | `04 02 00 00 08 00`; wait 300 ms; query ×3 | none |
| C094 | `c094` | Massage Stop | `04 02 02 00 00 00` | none |
| C095 | `c095` | Music | hold `04 02 00 01 00 00` | query ×3 |
| C096 | `c096` | Zero G | `04 02 00 00 10 00` | none |
| C096_reset | `c096_reset` | Reset chord | hold `04 02 08 00 10 00` | query ×3 |
| C097 | `c097` | Flat | `E5 FE 16 00 00 00 08 FE` | none |
| C097_reset | `c097_reset` | Reset chord | hold `E5 FE 16 00 10 00 08 EE` | `E5 FE 16 00 00 00 00 06` |
| C098 | `c098` | Foot Down | hold `E5 FE 16 08 00 00 00 FE` | `E5 FE 16 00 00 00 00 06` |
| C099 | `c099` | Foot Up | hold `E5 FE 16 04 00 00 00 02` | `E5 FE 16 00 00 00 00 06` |
| C100 | `c100` | Head Down | hold `E5 FE 16 02 00 00 00 04` | `E5 FE 16 00 00 00 00 06` |
| C101 | `c101` | Head Up | hold `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` |
| C102 | `c102` | Light | `E5 FE 16 00 00 02 00 04` | none |
| C103 | `c103` | Lounge | hold `E5 FE 16 00 40 00 00 C6` | `E5 FE 16 00 00 00 00 06` |
| C104 | `c104` | Massage Foot Add | `E5 FE 16 00 04 00 00 02`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C105 | `c105` | Massage Head Add | `E5 FE 16 00 08 00 00 FE`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C106 | `c106` | Massage Stop | `E5 FE 16 00 00 00 02 04` | none |
| C107 | `c107` | Music | hold `E5 FE 16 00 20 00 00 E6` | `E5 FE 16 00 00 00 00 06` |
| C108 | `c108` | Zero G | `E5 FE 16 00 10 00 00 F6` | none |
| C108_reset | `c108_reset` | Reset chord | hold `E5 FE 16 00 10 00 08 EE` | `E5 FE 16 00 00 00 00 06` |
| C110 | `c110` | Flat | `04 02 08 00 00 00` | none |
| C111 | `c111` | Foot Up | hold `04 02 00 00 00 04` | query ×3 |
| C112 | `c112` | Head Down | hold `04 02 00 00 00 02` | query ×3 |
| C113 | `c113` | Head Up | hold `04 02 00 00 00 01` | query ×3 |
| C114 | `c114` | Light | `04 02 00 02 00 00` | none |
| C115 | `c115` | Massage Foot Add | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C116 | `c116` | Massage Head Add | `04 02 00 00 08 00`; wait 300 ms; query ×3 | none |
| C117 | `c117` | Read | hold `04 02 00 00 20 00` | query ×3 |
| C118 | `c118` | TV | hold `04 02 00 00 40 00` | query ×3 |
| C119 | `c119` | Timer | `04 02 00 00 02 00`; wait 300 ms; query ×3 | none |
| C120 | `c120` | Zero G | `04 02 00 00 10 00` | none |
| C121 | `c121` | Foot down | hold `04 02 00 00 00 08` | query ×3 |
| C122 | `c122` | Anti snore | hold `04 02 00 00 80 00` | query ×3 |
| C123 | `c123` | Flat | `04 02 08 00 00 00` | none |
| C124 | `c124` | Foot down | hold `04 02 00 00 00 08` | query ×3 |
| C125 | `c125` | Foot up | hold `04 02 00 00 00 04` | query ×3 |
| C126 | `c126` | Head down | hold `04 02 00 00 00 02` | query ×3 |
| C127 | `c127` | Head up | hold `04 02 00 00 00 01` | query ×3 |
| C128 | `c128` | Massage all | `04 02 00 00 01 00`; wait 300 ms; query ×3 | none |
| C129 | `c129` | Massage foot | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C130 | `c130` | Massage head | `04 02 00 00 08 00`; wait 300 ms; query ×3 | none |
| C131 | `c131` | Massage timer | `04 02 00 00 02 00`; wait 300 ms; query ×3 | none |
| C132 | `c132` | Tv | hold `04 02 00 00 40 00` | query ×3 |
| C133 | `c133` | Zero G | `04 02 00 00 10 00` | none |
| C134 | `c134` | Flat | `04 02 08 00 00 00` | none |
| C135 | `c135` | Foot Up | hold `04 02 00 00 00 04` | query ×3 |
| C136 | `c136` | Head Down | hold `04 02 00 00 00 02` | query ×3 |
| C137 | `c137` | Head Up | hold `04 02 00 00 00 01` | query ×3 |
| C138 | `c138` | Light | `04 02 00 02 00 00`; wait 300 ms; query ×3 | none |
| C139 | `c139` | Massage Foot Add | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C140 | `c140` | Massage Head Add | `04 02 00 00 08 00`; wait 300 ms; query ×3 | none |
| C141 | `c141` | Read | hold `04 02 00 00 20 00` | query ×3 |
| C142 | `c142` | TV | hold `04 02 00 00 40 00` | query ×3 |
| C143 | `c143` | Timer | `04 02 00 00 02 00`; wait 300 ms; query ×3 | none |
| C144 | `c144` | Brightness high | RGB at 100% | none |
| C145 | `c145` | Brightness low | RGB at 20% | none |
| C146 | `c146` | Brightness medium | RGB at 60% | none |
| C147 | `c147` | Foot down | hold `04 02 00 00 00 08` | query ×3 |
| C148 | `c148` | Anti Snore | hold `04 02 00 00 80 00` | query ×3 |
| C149 | `c149` | Flat | `04 02 08 00 00 00`; wait 300 ms; query ×3 | none |
| C150 | `c150` | Foot Up | hold `04 02 00 00 00 04` | query ×3 |
| C151 | `c151` | Head Down | hold `04 02 00 00 00 02` | query ×3 |
| C152 | `c152` | Head Up | hold `04 02 00 00 00 01` | query ×3 |
| C153 | `c153` | Light | `04 02 00 02 00 00` | none |
| C154 | `c154` | Lumbar Down | hold `04 02 00 00 00 80` | query ×3 |
| C155 | `c155` | Lumbar Up | hold `04 02 00 00 00 40` | query ×3 |
| C156 | `c156` | Massage Foot Add | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C157 | `c157` | Massage Head Add | `04 02 00 00 08 00`; wait 300 ms; query ×3 | none |
| C158 | `c158` | Read | hold `04 02 00 00 20 00` | query ×3 |
| C159 | `c159` | TV | hold `04 02 00 00 40 00` | query ×3 |
| C160 | `c160` | Timer | `04 02 00 00 02 00`; wait 300 ms; query ×3 | none |
| C161 | `c161` | Zero G | `04 02 00 00 10 00` | none |
| C162 | `c162` | Foot down | hold `04 02 00 00 00 08` | query ×3 |
| C163 | `c163` | Music | hold `04 02 00 01 00 00` | query ×3 |
| C164 | `c164` | Flat | `04 02 08 00 00 00`; wait 500 ms; query ×3 | none |
| C165 | `c165` | Foot down | hold `04 02 00 00 00 08` | query ×3 |
| C166 | `c166` | Foot up | hold `04 02 00 00 00 04` | query ×3 |
| C167 | `c167` | Head down | hold `04 02 00 00 00 02` | query ×3 |
| C168 | `c168` | Head up | hold `04 02 00 00 00 01` | query ×3 |
| C169 | `c169` | Light | `04 02 00 02 00 00` | none |
| C170 | `c170` | Massage foot | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C171 | `c171` | Read | hold `04 02 00 00 20 00` | query ×3 |
| C172 | `c172` | Tv | hold `04 02 00 00 40 00` | query ×3 |
| C173 | `c173` | Zero G | `04 02 00 00 10 00` | none |
| C174 | `c174` | Music | hold `04 02 00 00 80 00` | query ×3 |
| C175 | `c175` | Flat | `04 02 08 00 00 00`; wait 500 ms; query ×3 | none |
| C176 | `c176` | Foot down | hold `04 02 00 00 00 08` | query ×3 |
| C177 | `c177` | Foot up | hold `04 02 00 00 00 04` | query ×3 |
| C178 | `c178` | Head down | hold `04 02 00 00 00 02` | query ×3 |
| C179 | `c179` | Head up | hold `04 02 00 00 00 01` | query ×3 |
| C180 | `c180` | Light | `04 02 00 02 00 00`; wait 300 ms; query ×3 | none |
| C181 | `c181` | Read | hold `04 02 00 00 20 00` | query ×3 |
| C182 | `c182` | Tv | hold `04 02 00 00 40 00` | query ×3 |
| C183 | `c183` | Zero G | `04 02 00 00 10 00` | none |
| C184 | `c184` | Brightness high | RGB at 100% | none |
| C185 | `c185` | Brightness low | RGB at 20% | none |
| C186 | `c186` | Brightness medium | RGB at 60% | none |
| C187 | `c187` | Flat | `04 02 08 00 00 00`; wait 500 ms; query ×3 | none |
| C188 | `c188` | Foot down | hold `04 02 00 00 00 08` | query ×3 |
| C189 | `c189` | Foot up | hold `04 02 00 00 00 04` | query ×3 |
| C190 | `c190` | Head down | hold `04 02 00 00 00 02` | query ×3 |
| C191 | `c191` | Head up | hold `04 02 00 00 00 01` | query ×3 |
| C192 | `c192` | Zero G | `04 02 00 00 10 00` | none |
| C193 | `c193` | Music | hold `04 02 00 01 00 00` | query ×3 |
| C194 | `c194` | Anti snore | hold `04 02 00 00 80 00` | query ×3 |
| C195 | `c195` | Flat | `04 02 08 00 00 00`; wait 500 ms; query ×3 | none |
| C196 | `c196` | Foot down | hold `04 02 00 00 00 08` | query ×3 |
| C197 | `c197` | Foot tilt down | hold `04 02 00 00 00 80` | query ×3 |
| C198 | `c198` | Foot tilt up | hold `04 02 00 00 00 40` | query ×3 |
| C199 | `c199` | Foot up | hold `04 02 00 00 00 04` | query ×3 |
| C200 | `c200` | Head down | hold `04 02 00 00 00 02` | query ×3 |
| C201 | `c201` | Head up | hold `04 02 00 00 00 01` | query ×3 |
| C202 | `c202` | Light | `04 02 00 02 00 00` | none |
| C203 | `c203` | Massage foot | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C204 | `c204` | Read | hold `04 02 00 00 20 00` | query ×3 |
| C205 | `c205` | Tv | hold `04 02 00 00 40 00` | query ×3 |
| C206 | `c206` | Zero G | `04 02 00 00 10 00` | none |
| C207 | `c207` | Custom Massage0 | `07 D0 04 04 00 00 10 00 00` | none |
| C208 | `c208` | Custom Massage1 | `07 D0 02 06 00 00 09 00 01` | none |
| C209 | `c209` | Custom Massage2 | `07 D0 02 04 00 00 09 00 02` | none |
| C210 | `c210` | Custom Massage3 | `07 D0 02 04 00 00 09 00 03` | none |
| C211 | `c211` | Custom Massage4 | `07 D0 02 04 00 00 09 00 04` | none |
| C212 | `c212` | Custom Massage5 | `07 D0 04 06 00 00 09 00 05` | none |
| C213 | `c213` | Custom Massage6 | `07 D0 04 06 00 00 09 00 06` | none |
| C214 | `c214` | Custom Massage7 | `07 D0 04 06 00 00 09 00 07` | none |
| C215 | `c215` | Custom Massage8 | `07 D0 04 06 00 00 09 00 08` | none |
| C216 | `c216` | Flat | `04 02 08 00 00 00`; wait 500 ms; query ×3 | none |
| C217 | `c217` | Foot massage down | `04 02 01 00 00 00`; wait 300 ms; query ×3 | none |
| C218 | `c218` | Foot massage up | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C219 | `c219` | Head massage down | `04 02 00 80 00 00`; wait 300 ms; query ×3 | none |
| C220 | `c220` | Head massage up | `04 02 00 00 08 00`; wait 300 ms; query ×3 | none |
| C221 | `c221` | Lounge | hold `04 02 00 00 20 00` | query ×3 |
| C222 | `c222` | Massage all | `04 02 00 00 01 00`; wait 300 ms; query ×3 | none |
| C223 | `c223` | Massage all stop | `04 02 02 00 00 00`; wait 300 ms; query ×3 | none |
| C224 | `c224` | Zero G | `04 02 00 00 10 00` | none |
| C225 | `c225` | Anti Snore | hold `E5 FE 16 00 80 00 00 86` | `E5 FE 16 00 00 00 00 06` |
| C226 | `c226` | Flat | `E5 FE 16 00 00 00 08 FE` | none |
| C227 | `c227` | Foot Down | hold `E5 FE 16 08 00 00 00 FE` | `E5 FE 16 00 00 00 00 06` |
| C228 | `c228` | Foot Up | hold `E5 FE 16 04 00 00 00 02` | `E5 FE 16 00 00 00 00 06` |
| C229 | `c229` | Head Down | hold `E5 FE 16 02 00 00 00 04` | `E5 FE 16 00 00 00 00 06` |
| C230 | `c230` | Head Up | hold `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` |
| C231 | `c231` | Level | `E5 FE 16 00 01 00 00 05` | none |
| C232 | `c232` | Light | `E5 FE 16 00 00 02 00 04` | none |
| C233 | `c233` | Massage Foot Add | `E5 FE 16 00 04 00 00 02`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C234 | `c234` | Massage Head Add | `E5 FE 16 00 08 00 00 FE`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C235 | `c235` | Music | hold `E5 FE 16 00 00 01 00 05` | `E5 FE 16 00 00 00 00 06` |
| C236 | `c236` | Read | hold `E5 FE 16 00 20 00 00 E6` | `E5 FE 16 00 00 00 00 06` |
| C237 | `c237` | Reset | hold `E5 FE 16 00 10 00 08 EE` | `E5 FE 16 00 00 00 00 06` |
| C238 | `c238` | Tv | hold `E5 FE 16 00 40 00 00 C6` | `E5 FE 16 00 00 00 00 06` |
| C239 | `c239` | Zero G | `E5 FE 16 00 10 00 00 F6` | none |
| C240 | `c240` | Anti Snore | hold `E5 FE 16 00 80 00 00 86` | `E5 FE 16 00 00 00 00 06` |
| C241 | `c241` | Flat | `E5 FE 16 00 00 00 08 FE`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C242 | `c242` | Foot Down | hold `E5 FE 16 08 00 00 00 FE` | `E5 FE 16 00 00 00 00 06` |
| C243 | `c243` | Foot Up | hold `E5 FE 16 04 00 00 00 02` | `E5 FE 16 00 00 00 00 06` |
| C244 | `c244` | Head Down | hold `E5 FE 16 02 00 00 00 04` | `E5 FE 16 00 00 00 00 06` |
| C245 | `c245` | Head Up | hold `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` |
| C246 | `c246` | Level | `E5 FE 16 00 01 00 00 05` | none |
| C247 | `c247` | Light | `E5 FE 16 00 00 02 00 04` | none |
| C248 | `c248` | Massage Foot Add | `E5 FE 16 00 04 00 00 02`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C249 | `c249` | Massage Head Add | `E5 FE 16 00 08 00 00 FE`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C250 | `c250` | Music | hold `E5 FE 16 00 00 01 00 05` | `E5 FE 16 00 00 00 00 06` |
| C251 | `c251` | Read | hold `E5 FE 16 00 20 00 00 E6` | `E5 FE 16 00 00 00 00 06` |
| C252 | `c252` | Reset | hold `E5 FE 16 00 10 00 08 EE` | `E5 FE 16 00 00 00 00 06` |
| C253 | `c253` | Tv | hold `E5 FE 16 00 40 00 00 C6` | `E5 FE 16 00 00 00 00 06` |
| C254 | `c254` | Zero G | `E5 FE 16 00 10 00 00 F6` | none |
| C255 | `c255` | Head down | hold `04 02 00 00 00 02` | query ×3 |
| C256 | `c256` | Head up | hold `04 02 00 00 00 01` | query ×3 |
| C257 | `c257` | Flat | `E5 FE 16 00 00 00 08 FE` | none |
| C258 | `c258` | Foot Down | hold `E5 FE 16 08 00 00 00 FE` | `E5 FE 16 00 00 00 00 06` |
| C259 | `c259` | Foot Up | hold `E5 FE 16 04 00 00 00 02` | `E5 FE 16 00 00 00 00 06` |
| C260 | `c260` | Head Down | hold `E5 FE 16 02 00 00 00 04` | `E5 FE 16 00 00 00 00 06` |
| C261 | `c261` | Head Up | hold `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` |
| C262 | `c262` | Level | `E5 FE 16 00 01 00 00 05` | none |
| C263 | `c263` | Read | hold `E5 FE 16 00 20 00 00 E6` | `E5 FE 16 00 00 00 00 06` |
| C264 | `c264` | Reset | hold `E5 FE 16 00 10 00 08 EE` | `E5 FE 16 00 00 00 00 06` |
| C265 | `c265` | Zero G | `E5 FE 16 00 10 00 00 F6` | none |
| C266 | `c266` | Anti Snore | hold `E5 FE 16 00 80 00 00 86` | `E5 FE 16 00 00 00 00 06` |
| C267 | `c267` | Flat | `E5 FE 16 00 00 00 08 FE` | none |
| C268 | `c268` | Foot Down | hold `E5 FE 16 08 00 00 00 FE` | `E5 FE 16 00 00 00 00 06` |
| C269 | `c269` | Foot Up | hold `E5 FE 16 04 00 00 00 02` | `E5 FE 16 00 00 00 00 06` |
| C270 | `c270` | Head Down | hold `E5 FE 16 02 00 00 00 04` | `E5 FE 16 00 00 00 00 06` |
| C271 | `c271` | Head Up | hold `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` |
| C272 | `c272` | Level | `E5 FE 16 00 01 00 00 05` | none |
| C273 | `c273` | M | hold `E5 FE 16 00 00 00 40 C6` | `E5 FE 16 00 00 00 00 06` |
| C274 | `c274` | Massage Foot Add | `E5 FE 16 00 04 00 00 02`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C275 | `c275` | Massage Head Add | `E5 FE 16 00 08 00 00 FE`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C276 | `c276` | Music | hold `E5 FE 16 00 00 01 00 05` | `E5 FE 16 00 00 00 00 06` |
| C277 | `c277` | Read | hold `E5 FE 16 00 20 00 00 E6` | `E5 FE 16 00 00 00 00 06` |
| C278 | `c278` | Reset | hold `E5 FE 16 00 10 00 08 EE` | `E5 FE 16 00 00 00 00 06` |
| C279 | `c279` | Tv | hold `E5 FE 16 00 40 00 00 C6` | `E5 FE 16 00 00 00 00 06` |
| C280 | `c280` | Zero G | `E5 FE 16 00 10 00 00 F6` | none |
| C281 | `c281` | Anti Snore | hold `E5 FE 16 00 80 00 00 86` | `E5 FE 16 00 00 00 00 06` |
| C282 | `c282` | Flat | `E5 FE 16 00 00 00 08 FE` | none |
| C283 | `c283` | Foot Up | hold `E5 FE 16 04 00 00 00 02` | `E5 FE 16 00 00 00 00 06` |
| C284 | `c284` | Head Down | hold `E5 FE 16 02 00 00 00 04` | `E5 FE 16 00 00 00 00 06` |
| C285 | `c285` | Head Up | hold `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` |
| C286 | `c286` | Light | `E5 FE 16 00 00 02 00 04` | none |
| C287 | `c287` | Lumbar Down | hold `E5 FE 16 80 00 00 00 86` | `E5 FE 16 00 00 00 00 06` |
| C288 | `c288` | Lumbar Up | hold `E5 FE 16 40 00 00 00 C6` | `E5 FE 16 00 00 00 00 06` |
| C289 | `c289` | Massage Foot Add | `E5 FE 16 00 04 00 00 02`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C290 | `c290` | Massage Head Add | `E5 FE 16 00 08 00 00 FE`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C291 | `c291` | Music | hold `E5 FE 16 00 20 00 00 E6` | `E5 FE 16 00 00 00 00 06` |
| C292 | `c292` | Read | hold `E5 FE 16 00 40 00 00 C6` | `E5 FE 16 00 00 00 00 06` |
| C293 | `c293` | Timer | `E5 FE 16 00 02 00 00 04`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C294 | `c294` | Zero G | `E5 FE 16 00 10 00 00 F6` | none |
| C295 | `c295` | Foot down | hold `E5 FE 16 08 00 00 00 FE` | `E5 FE 16 00 00 00 00 06` |
| C296 | `c296` | Anti snore | hold `E5 FE 16 00 80 00 00 86` | `E5 FE 16 00 00 00 00 06` |
| C297 | `c297` | Flat | `E5 FE 16 00 00 00 08 FE` | none |
| C298 | `c298` | Foot down | hold `E5 FE 16 08 00 00 00 FE` | `E5 FE 16 00 00 00 00 06` |
| C299 | `c299` | Foot tilt down | hold `E5 FE 16 80 00 00 00 86` | `E5 FE 16 00 00 00 00 06` |
| C300 | `c300` | Foot tilt up | hold `E5 FE 16 40 00 00 00 C6` | `E5 FE 16 00 00 00 00 06` |
| C301 | `c301` | Foot up | hold `E5 FE 16 04 00 00 00 02` | `E5 FE 16 00 00 00 00 06` |
| C302 | `c302` | Head down | hold `E5 FE 16 02 00 00 00 04` | `E5 FE 16 00 00 00 00 06` |
| C303 | `c303` | Head foot down | hold `E5 FE 16 A0 00 00 00 66` | `E5 FE 16 00 00 00 00 06` |
| C304 | `c304` | Head foot up | hold `E5 FE 16 50 00 00 00 B6` | `E5 FE 16 00 00 00 00 06` |
| C305 | `c305` | Head tilt down | hold `E5 FE 16 20 00 00 00 E6` | `E5 FE 16 00 00 00 00 06` |
| C306 | `c306` | Head tilt up | hold `E5 FE 16 10 00 00 00 F6` | `E5 FE 16 00 00 00 00 06` |
| C307 | `c307` | Head up | hold `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` |
| C308 | `c308` | Light | `E5 FE 16 00 00 02 00 04` | none |
| C309 | `c309` | Massage foot | `E5 FE 16 00 04 00 00 02`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C310 | `c310` | Massage head | `E5 FE 16 00 08 00 00 FE`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C311 | `c311` | Massage timer | `E5 FE 16 00 02 00 00 04`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C312 | `c312` | Read | hold `E5 FE 16 00 20 00 00 E6` | `E5 FE 16 00 00 00 00 06` |
| C313 | `c313` | Tv | hold `E5 FE 16 00 40 00 00 C6` | `E5 FE 16 00 00 00 00 06` |
| C314 | `c314` | Zero G | `E5 FE 16 00 10 00 00 F6` | none |
| C315 | `c315` | All Massage | `E5 FE 16 00 01 00 00 05`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C316 | `c316` | Anti Snore | hold `E5 FE 16 00 80 00 00 86` | `E5 FE 16 00 00 00 00 06` |
| C317 | `c317` | Flat | `E5 FE 16 00 00 00 08 FE` | none |
| C318 | `c318` | Foot Up | hold `E5 FE 16 04 00 00 00 02` | `E5 FE 16 00 00 00 00 06` |
| C319 | `c319` | Head Down | hold `E5 FE 16 02 00 00 00 04` | `E5 FE 16 00 00 00 00 06` |
| C320 | `c320` | Head Up | hold `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` |
| C321 | `c321` | Light | `E5 FE 16 00 00 02 00 04` | none |
| C322 | `c322` | Massage Foot Add | `E5 FE 16 00 04 00 00 02`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C323 | `c323` | Massage Head Add | `E5 FE 16 00 08 00 00 FE`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C324 | `c324` | Music | hold `E5 FE 16 00 00 01 00 05` | `E5 FE 16 00 00 00 00 06` |
| C325 | `c325` | Read | hold `E5 FE 16 00 20 00 00 E6` | `E5 FE 16 00 00 00 00 06` |
| C326 | `c326` | TV | hold `E5 FE 16 00 40 00 00 C6` | `E5 FE 16 00 00 00 00 06` |
| C327 | `c327` | Timer | `E5 FE 16 00 02 00 00 04`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C328 | `c328` | Zero G | `E5 FE 16 00 10 00 00 F6` | none |
| C329 | `c329` | Foot down | hold `E5 FE 16 08 00 00 00 FE` | `E5 FE 16 00 00 00 00 06` |
| C330 | `c330` | Anti snore | hold `04 02 00 00 80 00` | query ×3 |
| C331 | `c331` | Flat | `04 02 08 00 00 00` | none |
| C332 | `c332` | Foot down | hold `04 02 00 00 00 08` | query ×3 |
| C333 | `c333` | Foot up | hold `04 02 00 00 00 04` | query ×3 |
| C334 | `c334` | Head down | hold `04 02 00 00 00 02` | query ×3 |
| C335 | `c335` | Head tilt down | hold `04 02 00 00 00 20` | query ×3 |
| C336 | `c336` | Head tilt up | hold `04 02 00 00 00 10` | query ×3 |
| C337 | `c337` | Head up | hold `04 02 00 00 00 01` | query ×3 |
| C338 | `c338` | Light | `04 02 00 02 00 00` | none |
| C339 | `c339` | M | hold `04 02 00 01 00 00` | query ×3 |
| C340 | `c340` | Massage foot | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C341 | `c341` | Massage head | `04 02 00 00 08 00`; wait 300 ms; query ×3 | none |
| C342 | `c342` | Massage timer | `04 02 00 00 02 00`; wait 300 ms; query ×3 | none |
| C343 | `c343` | Read | hold `04 02 00 00 20 00` | query ×3 |
| C344 | `c344` | Tv | hold `04 02 00 00 40 00` | query ×3 |
| C345 | `c345` | Zero G | `04 02 00 00 10 00` | none |
| C346 | `c346` | Demonstration | hold `04 02 40 00 00 00` | query ×3 |
| C348 | `c348` | Anti Snore | hold `04 02 00 00 80 00` | query ×3 |
| C349 | `c349` | Flat | `04 02 08 00 00 00` | none |
| C350 | `c350` | Foot Up | hold `04 02 00 00 00 04` | query ×3 |
| C351 | `c351` | Head Down | hold `04 02 00 00 00 02` | query ×3 |
| C352 | `c352` | Head Up | hold `04 02 00 00 00 01` | query ×3 |
| C353 | `c353` | Light | `04 02 00 02 00 00` | none |
| C354 | `c354` | Massage Foot Add | `04 02 00 00 04 00`; wait 300 ms; query ×3 | none |
| C355 | `c355` | Massage Head Add | `04 02 00 00 08 00`; wait 300 ms; query ×3 | none |
| C356 | `c356` | Read | hold `04 02 00 00 20 00` | query ×3 |
| C357 | `c357` | TV | hold `04 02 00 00 40 00` | query ×3 |
| C358 | `c358` | Timer | `04 02 00 00 02 00`; wait 300 ms; query ×3 | none |
| C359 | `c359` | Zero G | `04 02 00 00 10 00` | none |
| C360 | `c360` | Foot down | hold `04 02 00 00 00 08` | query ×3 |
| C361 | `c361` | Anti Snore | hold `E5 FE 16 00 80 00 00 86` | `E5 FE 16 00 00 00 00 06` |
| C362 | `c362` | Flat | `E5 FE 16 00 00 00 08 FE` | none |
| C363 | `c363` | Foot Down | hold `E5 FE 16 08 00 00 00 FE` | `E5 FE 16 00 00 00 00 06` |
| C364 | `c364` | Foot Up | hold `E5 FE 16 04 00 00 00 02` | `E5 FE 16 00 00 00 00 06` |
| C365 | `c365` | Head Down | hold `E5 FE 16 02 00 00 00 04` | `E5 FE 16 00 00 00 00 06` |
| C366 | `c366` | Head Up | hold `E5 FE 16 01 00 00 00 05` | `E5 FE 16 00 00 00 00 06` |
| C367 | `c367` | Level | `E5 FE 16 00 01 00 00 05` | none |
| C368 | `c368` | Light | `E5 FE 16 00 00 02 00 04` | none |
| C369 | `c369` | Massage Foot Add | `E5 FE 16 00 04 00 00 02`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C370 | `c370` | Massage Head Add | `E5 FE 16 00 08 00 00 FE`; wait 300 ms; `E5 FE 16 00 00 00 00 06` | none |
| C371 | `c371` | Massage Lumbar Add | `E5 FE 16 00 00 40 00 C6` | none |
| C372 | `c372` | Read | hold `E5 FE 16 00 20 00 00 E6` | `E5 FE 16 00 00 00 00 06` |
| C373 | `c373` | Reset | hold `E5 FE 16 00 10 00 08 EE` | `E5 FE 16 00 00 00 00 06` |
| C374 | `c374` | Tv | hold `E5 FE 16 00 40 00 00 C6` | `E5 FE 16 00 00 00 00 06` |
| C375 | `c375` | Zero G | `E5 FE 16 00 10 00 00 F6` | none |

###### Ergomotion 4.0 shared configuration and meditation

These actions remain available for P1 and P2 products. Rename, clock, alarms and
wake dismissal address the physical receiver, without a side field. Use a
physical/parent target once when configuring shared state.

| Action | Bytes | HA exposure |
|--------|-------|-------------|
| Rename | 18 bytes `EF 02` + 15 name bytes + complement checksum | `rename` action |
| Clock | `E7 80 01 year_minus_1900 month_minus_1 day hour24 minute second checksum` | `sync_clock` action |
| Weekly alarms | `ED 80 03` + 3 × `[hour minute weekday_bits wake]` + checksum | `set_alarm` |
| One-time alarms | `ED 80 02` + 3 × `[delta_hours delta_minutes delta_seconds wake]` + checksum | `set_alarm` |
| Wake vibration dismissal | `E1 80 04 9A`, once | Dismiss wake vibration button |
| Meditation start, M14 or Flex3 Massage | `04 02 48 00 00 00`, wait 200 ms, query ×3 | Start meditation button |
| Meditation start, M21 or 20th Anniversary | `04 02 00 01 10 00`, wait 200 ms, query ×3 | Start meditation button |
| Meditation stop | `04 02 08 00 00 00`, wait 200 ms, query ×3 | Stop meditation button |

Names are Java-trimmed and must contain 1–16 UTF-16 code units. The app copies
that many default-encoded bytes, modeled as UTF-8, and overwrites the sixteenth
copied byte with the checksum. Non-ASCII names can therefore end with a partial
UTF-8 character. Inputs longer than 16 units are rejected before BLE to avoid
the app's array overflow.

Clock sync waits 500 ms after its frame. Alarm tables compact enabled records,
zero-fill three slots and use the complemented byte sum. Recurring weekdays
use `80 | Monday<<1 | Tuesday<<2 | Wednesday<<3 | Thursday<<4 | Friday<<5 |
Saturday<<6 | Sunday`; wake vibration is `03`, otherwise `00`. Both tables are
validated before any frame is written. Dispatch writes weekly then one-time,
500 ms apart, or just the selected table. HA requires future same-day one-time
alarms and rejects nonexistent/ambiguous local times instead of reproducing
Android's ambiguous date parsing. Dismissal does not invent an alarm-enabled
readback. The profile has no memory-save command.

Meditation requires a connected, initialized receiver and a nonempty Bluetooth
name. M14/Flex3 Massage require name prefix `KSBT03CP`, M21 requires `KSBT03CW`
(case-insensitive); 20th Anniversary accepts any nonempty name. `GM_DFU` and
`SMART_DFU` require vendor firmware maintenance in the app; HA does not attempt
that update. Repeat the start action from an HA automation for a cycle routine.
The app's four-row cycle list has no BLE routine-selection action.

RGB buttons and color writes require reported light-on state. HA power actions
use that reported state to make toggles idempotent, then wait up to two seconds
for confirmation on the current connection. Cancellation or disconnection ends
that host-side wait without admitting an unconfirmed color write. The light toggle
remains accessible while off. Brightness buttons use source binary32 factors
1.0, 0.6 and 0.2 and truncate each scaled channel. HA's color picker supplies RGB
channels directly; no phone bitmap/density or out-of-bounds picker behavior is
required. On M19 and generic products, the first applicable report seeds the
brightness-button base color. M16 retains the picker-selected color.

#### Timing

##### Ergomotion 4.0 command timing

P1 session initialization writes one zero key. P2 initializes with query ×3;
M30/EZI MAID is the exception, initializing with a P1 zero before P2 controls.
P1 held controls release with a same-side zero frame. P2 releases cancel the
refresh and issue queries, without inventing a motor STOP frame. One-shot
buttons retain their individual waits and release sequences from the table.
H's mode 1 specifically waits 300 ms, writes zero, then writes the mode key.
M10's massage timer sends key `04000000`, not a substituted common timer key.

Cancellation and failed pulse writes still attempt the recovered cleanup with
a fresh cancellation event. Cleanup stays on its original session and side;
a reconnection never receives an older command's pending release or queries.
Normal command serialization, adapter/proxy selection, handoff and reconnect
remain owned by Home Assistant. No firmware watchdog timing is inferred.

#### Notifications

##### Ergomotion 4.0 notifications

| Length / prefix | Parsed state |
|-----------------|--------------|
| 11 bytes | No state update |
| 18 / `A5 0B 0F` | Timer seconds `[3:5]` big-endian, light byte 12 |
| 16 / `A5 0B 0D` | M10 signed timer byte 5; otherwise seconds `[3:5]`, with light byte 12 on M16/M19/generic |
| 16 / other | Ignore when byte 13 bit 5 is set; otherwise signed timer byte 14 |
| 19 / `A5 0D 10` | No state update |
| 19 / other, M19/generic | Seconds `[3:5]`, light byte 12, RGB bytes 15–17 |
| 19 / other, fixed layouts | Side-filter byte 16, then signed timer byte 14 when header `F1`, otherwise byte 15 |
| 20 / any | Signed timer byte 14 |
| 23 / any | Signed timer byte 15 |
| 31 / `1D 0B` | Timer -1, light byte 14 |
| 31 / `1C 0B` | Seconds `[3:5]`, light byte 10, RGB bytes 11–13 |
| 31 / other | Seconds `[2:4]` |
| Other lengths/prefixes | Ignored |

Seconds 1–600 map to timer status 1, 601–1200 to 2, 1201–1800 to 3,
otherwise -1. Raw signed byte values are retained. Side bit 1 selects Right;
bit 0 without bit 1 rejects Right; no side bits admit all sides. Side-bound
sensor keys keep reports separate, so one half does not overwrite the other.
HA exposes parsed timer and light state even where the app omits that product
from its visible icon-update overload. Fields discarded by the app are never
reported as measured positions. No receive checksum, acknowledgement,
fragmentation or buffering is invented.

#### Evidence

##### Ergomotion 4.0 notes

Owners can help confirm receiver selection, physical Left/Right mapping,
motor effects, release behavior, ATT write mode, notifications, RGB, rename and
alarm acceptance. These still need testing on hardware.

###### Ergomotion 4.0 analysis provenance

Based on Ergomotion 4.0 3.7 (`com.sfd.hump`). Ref [#558](https://github.com/kristofferR/ha-adjustable-bed/issues/558).

### AdjustaMattress

**App:** [AdjustaMattress](https://play.google.com/store/apps/details?id=com.okin.adjustamattress) 1.6.0 (version code 10), `com.okin.adjustamattress`

**Status:** Not yet tested

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

The `adjustamattress` bed type is a profile of this family. Models P1 and P2
build their key frames through this codec (see
[Malouf legacy OKIN, Sleepy's BOX15, AdjustaMattress P1 and P2](#malouf-legacy-okin-sleepys-box15-adjustamattress-p1-and-p2));
models P3 and P4 send [Okin N-frames](okin-nframe.md#framing-and-checksum), described below.

#### Setup

##### AdjustaMattress known models

- Receivers driven by the AdjustaMattress app, in four BLE models (P1 to P4)
  and seven product layouts (L0 to L6). See [Setup and layout](#adjustamattress-setup-and-layout).
- Selected only through the explicit **AdjustaMattress app** bed type, with
  seven product layouts. Shared services and a familiar name do not identify this
  app, so select it manually.
- Independent of the Adjustable bed (Lumbar), SmartBed and other OKIN app
  profiles.

##### AdjustaMattress apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [AdjustaMattress](https://play.google.com/store/apps/details?id=com.okin.adjustamattress) 1.6.0 (version code 10) | `com.okin.adjustamattress` |

- The bed type follows this app. It is **not yet tested** on hardware.

##### AdjustaMattress setup and layout

Choose the matching product layout and model under **Bed model or remote**. The 28
explicit choices (`P1_L0` to `P4_L6`) combine two independent dimensions.

###### AdjustaMattress models

| Model | App enum | GATT roles |
| --- | --- | --- |
| P1 | CB | Service FFE5 / write FFE9, service FFE0 / notify FFE4 |
| P2 | JLDP | Same roles; FFF0 is a model marker, never the writer |
| P3 | CB24 | Nordic UART service 6E400001 / write 002 / notify 003 |
| P4 | SleepSnore | Same Nordic UART roles, different frames and parser |

###### AdjustaMattress layouts

| Layout | Additional position controls beyond head, foot, flat and zero gravity |
| --- | --- |
| L0 AdjustaLumbarHeadTilt | Neck tilt, lumbar, M1, TV, lounge, anti-snore, lighting |
| L1 AdjustaBed | Head + foot together, TV, lounge, anti-snore, lighting |
| L2 AdjustaMattress | Head + foot together, TV, lounge, anti-snore |
| L3 AdjustaBedLumbar | Lumbar, head + foot together, TV, lounge, anti-snore, lighting |
| L4 FoldingBed | TV, lounge, anti-snore |
| L5 HilowBed | Neck tilt, TV, lounge, anti-snore, lighting |
| L6 Lolobed | Lift head, lift foot, lift up/down, lighting |

- Lift labels follow the app. They do not give a measured height or a new
  motor position scale.
- L5 has no lift command merely because of its name.
- M1 exists only on L0; no memory programming or additional memory slots exist.
- Generic motor counts do not expand these layouts.

###### AdjustaMattress native controls

- Position covers, standard preset buttons, app-labelled M1/lift/light buttons,
  and the generic `adjustable_bed.hold_control` action use the selected layout.
- Held identifiers keep the app's method names, such as `headUp`,
  `footDown`, `unionUp`, `neckTiltUp`, `lumbarDown`, `liftHead`, `flatPosition`,
  `zeroGravity`, `tv`, `lounge`, `anti` and `m1`. Only exposed controls are
  accepted.
- The native card groups massage, lighting, presets and utility settings.

| HA control | App actions |
| --- | --- |
| Back cover | `headUp` / `headDown` |
| Legs cover | `footUp` / `footDown` |
| Back + legs cover (L1/L2/L3) | `unionUp` / `unionDown` |
| Neck cover (L0/L5) | `neckTiltUp` / `neckTiltDown` |
| Lumbar cover (L0/L3) | `lumbarUp` / `lumbarDown` |
| Lift cover (L6) | `liftUp` / `liftDown` |
| Lift head / Lift foot buttons (L6) | `liftHead` / `liftFoot` |
| M1 button (L0) | `m1` |
| Underbed lighting button (not P2) | `underbedLighting` |

###### AdjustaMattress paired beds

- Profile/variant settings belong to each physical address. Configure each side
  separately before combining a two-address pair.
- A single-address side selector is unsupported.

##### AdjustaMattress protocol details

| Role | P1 / P2 | P3 / P4 |
| --- | --- | --- |
| Write service | `0000ffe5-0000-1000-8000-00805f9b34fb` | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` |
| Write characteristic | `0000ffe9-0000-1000-8000-00805f9b34fb` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` |
| Notify service | `0000ffe0-0000-1000-8000-00805f9b34fb` | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` |
| Notify characteristic | `0000ffe4-0000-1000-8000-00805f9b34fb` | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` |
| Model marker | `0000fff0-0000-1000-8000-00805f9b34fb` (P2) | none |

**Format:** model-specific control frames; P1/P2 carry a one-byte checksum, P3/P4 do not

The P1 and P2 key frames are built by the [Keeson codec](#controller-profiles).

- Short UUIDs expand to the Bluetooth base UUID. Nordic UART's suffix is
  `-b5a3-f393-e0a9-e50e24dcca9e`.

###### AdjustaMattress packet format

| Model | Control frame | Checksum |
| --- | --- | --- |
| P1 | `E6 FE 16` + five payload bytes + checksum | Complement of the whole source integer sum |
| P2 | `E5 FE 16` + four payload bytes + checksum | Same |
| P3 | `05 02` + five payload bytes | None |
| P4 | `06 02` + six payload bytes | None |

- The checksum is `~sum(values) & 0xFF`, computed over the source integers
  before byte truncation.
- Exceptions that keep the app's `05` frames: P4 wave step, all four L6 lift
  helpers (on every model) and the P2 held massage steps on L4/L6. Dedicated P2
  massage selectors use `E5 FE 16` frames. These exceptions are tested rather
  than inferred from a family.
- Clock/alarm, query, anti-snore and sleep builders have separate formats,
  including P3/P4 year/month and byte-order differences. See [Commands](#adjustamattress-commands).

###### AdjustaMattress write mode

- Writes require **write with response**.
- Notifications remain enabled even when angle sensing is disabled.
- Missing roles or an unsupported write mode fail setup rather than selecting
  another app's transport.
- The last matching GATT role wins in enumeration order.

##### AdjustaMattress detection and setup

`auto` uses the app's default **AdjustaBed** layout (L1) and picks the model from
the raw Bluetooth name and GATT:

| Signal | Model |
| --- | --- |
| Raw name starts with `SLEEP_V`, or reconnect name `SleepBT` | P4 |
| Raw name starts with `Smartbed` | P3 |
| Anything else | P1 |
| FFF0 service present on an automatic non-Nordic model | P2 |

- These name prefixes are case-sensitive.
- The app's separate scan admission lowercases `smartbed`/`okin` but requires
  case-sensitive `SLEEP_V`.
- HA owns scanning; these broad shared names do not change global detection.
- Use an explicit variant when the raw name/model cannot identify your receiver.

#### Controls

##### AdjustaMattress features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (head and foot; per layout also head + foot together, neck tilt, lumbar, lift) |
| Hold Until Release | ✅ Models P1 and P2 ([renewable hold](../SERVICES.md#renewable-holds)); ❌ P3 and P4 keep finite holds |
| Presets | ✅ (flat and zero gravity; TV, lounge and anti-snore on L0 to L5) |
| Memory Presets | ⚠️ (M1 recall on L0 only; no memory programming or additional slots) |
| Massage | ✅ (P2 L0/L1/L2/L3/L5: dedicated selectors and timers; others: four held steps) |
| Massage power/off, absolute intensity | ❌ (not in the app) |
| Lights | ✅ (underbed lighting on L0/L1/L3/L5/L6; ❌ on P2) |
| Alarm | ✅ (hour, minute and action settings, applied by the Alarm switch) |
| Clock sync | ✅ (P1/P3/P4) |
| Intelligent anti-snore and sleep | ✅ (P4 L0/L3 only) |
| Position Feedback | ❌ (no motor angle, percentage, height or current telemetry) |
| Single-address Left/Right | ❌ |

##### AdjustaMattress commands

Frames are `frame()` output from
[`adjustamattress_protocol.py`](../../custom_components/adjustable_bed/beds/adjustamattress/protocol.py),
which builds the P1 and P2 frames through this codec and the lift, P3 and P4
frames through the [Okin N-frame codec](okin-nframe.md#framing-and-checksum).
Tests cover all 180 command/vector rows, including app branches no control
uses.

###### AdjustaMattress motor control

| Command | P1 | P2 | P3 | P4 |
|---------|----|----|----|----|
| `headUp` | `E6 FE 16 01 00 00 00 00 04` | `E5 FE 16 00 00 00 01 05` | `05 02 00 00 00 01 00` | `06 02 00 00 00 01 00 00` |
| `headDown` | `E6 FE 16 02 00 00 00 00 03` | `E5 FE 16 00 00 00 02 04` | `05 02 00 00 00 02 00` | `06 02 00 00 00 02 00 00` |
| `footUp` | `E6 FE 16 04 00 00 00 00 01` | `E5 FE 16 00 00 00 04 02` | `05 02 00 00 00 04 00` | `06 02 00 00 00 04 00 00` |
| `footDown` | `E6 FE 16 08 00 00 00 00 FD` | `E5 FE 16 00 00 00 08 FE` | `05 02 00 00 00 08 00` | `06 02 00 00 00 08 00 00` |
| `unionUp` | `E6 FE 16 05 00 00 00 00 00` | `E5 FE 16 00 00 00 05 01` | `05 02 00 00 00 05 00` | `06 02 00 00 00 05 00 00` |
| `unionDown` | `E6 FE 16 0A 00 00 00 00 FB` | `E5 FE 16 00 00 00 0A FC` | `05 02 00 00 00 0A 00` | `06 02 00 00 00 0A 00 00` |
| `neckTiltUp` | `E6 FE 16 10 00 00 00 00 F5` | `E5 FE 16 00 00 00 10 F6` | `05 02 00 00 00 10 00` | `06 02 00 00 00 10 00 00` |
| `neckTiltDown` | `E6 FE 16 20 00 00 00 00 E5` | `E5 FE 16 00 00 00 20 E6` | `05 02 00 00 00 20 00` | `06 02 00 00 00 20 00 00` |
| `lumbarUp` | `E6 FE 16 40 00 00 00 00 C5` | `E5 FE 16 00 00 00 40 C6` | `05 02 00 00 00 40 00` | `06 02 00 00 00 40 00 00` |
| `lumbarDown` | `E6 FE 16 80 00 00 00 00 85` | `E5 FE 16 00 00 00 80 86` | `05 02 00 00 00 80 00` | `06 02 00 00 00 80 00 00` |
| STOP (`stop`) | `E6 FE 16 00 00 00 00 00 05` | `E5 FE 16 00 00 00 00 06` | `05 02 00 00 00 00 00` | `06 02 00 00 00 00 00 00` |

###### AdjustaMattress lift (L6)

The lift helpers send the same `05` frames on every model.

| Command | Bytes |
|---------|-------|
| `liftHead` | `05 02 00 00 00 10 00` |
| `liftFoot` | `05 02 00 00 00 20 00` |
| `liftUp` | `05 02 00 00 00 40 00` |
| `liftDown` | `05 02 00 00 00 80 00` |

###### AdjustaMattress presets

| Command | P1 | P2 | P3 | P4 |
|---------|----|----|----|----|
| `flatPosition` | `E6 FE 16 00 00 00 08 00 FD` | `E5 FE 16 01 00 00 02 03` | `05 02 08 00 00 00 00` | `06 02 08 00 00 00 00 00` |
| `zeroGravity` | `E6 FE 16 00 10 00 00 00 F5` | `E5 FE 16 01 00 00 01 04` | `05 02 00 00 10 00 00` | `06 02 00 00 10 00 00 00` |
| `tv` | `E6 FE 16 00 40 00 00 00 C5` | `E5 FE 16 01 00 00 04 01` | `05 02 00 00 40 00 00` | `06 02 00 00 40 00 00 00` |
| `lounge` | `E6 FE 16 00 20 00 00 00 E5` | `E5 FE 16 01 00 00 09 FC` | `05 02 00 00 20 00 00` | `06 02 00 00 20 00 00 00` |
| `anti` | `E6 FE 16 00 80 00 00 00 85` | `E5 FE 16 01 00 00 09 FC` | `05 02 00 00 80 00 00` | `06 02 00 00 80 00 00 00` |

- On P2, `lounge` and `anti` send the same code (`09`), as in the app's vectors.

###### AdjustaMattress memory

| Command | P1 | P2 | P3 | P4 |
|---------|----|----|----|----|
| `m1` recall (L0) | `E6 FE 16 00 00 10 00 00 F5` | `E5 FE 16 01 00 00 08 FD` | `05 02 00 01 00 00 00` | `06 02 00 01 00 00 00 00` |

- No program/save command exists.

###### AdjustaMattress massage

**Held steps** (P2 L4/L6 and all other models):

| Command | P1 | P2 | P3 | P4 |
|---------|----|----|----|----|
| `headStrengthAdd` | `E6 FE 16 00 08 00 00 00 FD` | `05 02 00 00 08 00 00` | `05 02 00 00 08 00 00` | `06 02 00 00 08 00 00 00` |
| `footStrengthAdd` | `E6 FE 16 00 04 00 00 00 01` | `05 02 00 00 04 00 00` | `05 02 00 00 04 00 00` | `06 02 00 00 04 00 00 00` |
| `waveAdd` | `E6 FE 16 00 00 00 10 00 F5` | `05 02 10 00 00 00 00` | `05 02 10 00 00 00 00` | `05 02 10 00 00 00 00` |
| `massageTimer` | `E6 FE 16 00 02 00 00 00 03` | `05 02 00 00 02 00 00` | `05 02 00 00 02 00 00` | `06 02 00 00 02 00 00 00` |

- The four ordinary held steps are head strength, foot strength, wave and massage
  timer.

**Dedicated P2 controls** (P2 L0/L1/L2/L3/L5):

- The **Massage head intensity**, **Massage foot intensity** and
  **Massage wave intensity** numbers (1–4, for selector index 0–3), written
  once per choice.
- The **Massage timer** select (10, 20 or 30 minutes; no off).
- Their bytes are the app's exact selector/timer commands.

| Selector index | Head | Foot | Wave |
| --- | --- | --- | --- |
| 0 | `headMassageOne` `E5 FE 16 10 00 00 10 E6` | `footMassageOne` `E5 FE 16 11 00 00 10 E5` | `WaveOne` `E5 FE 16 10 00 00 20 D6` |
| 1 | `headMassageTwo` `E5 FE 16 10 00 00 11 E5` | `footMassageTwo` `E5 FE 16 11 00 00 11 E4` | `waveTwo` `E5 FE 16 10 00 00 21 D5` |
| 2 | `headMassageThree` `E5 FE 16 10 00 00 12 E4` | `footMassageThree` `E5 FE 16 11 00 00 12 E3` | `waveThree` `E5 FE 16 10 00 00 22 D4` |
| 3 | `headMassageFour` `E5 FE 16 10 00 00 13 E3` | `footMassageFour` `E5 FE 16 11 00 00 13 E2` | `waveFour` `E5 FE 16 10 00 00 23 D3` |

| Timer | P2 bytes |
| --- | --- |
| `timer10` | `E5 FE 16 01 00 00 41 C4` |
| `timer20` | `E5 FE 16 01 00 00 42 C3` |
| `timer30` | `E5 FE 16 01 00 00 43 C2` |

- There is no generic massage power/off command or universal absolute intensity
  setter in this app, so those controls are not offered.
- Dormant timer branches on other models are not promoted.

###### AdjustaMattress lights

| Command | P1 | P2 | P3 | P4 |
|---------|----|----|----|----|
| `underbedLighting` | `E6 FE 16 00 00 02 00 00 03` | ❌ (no frame; see [Notes](#adjustamattress-app-defects)) | `05 02 00 02 00 00 00` | `06 02 00 02 00 00 00 00` |

###### AdjustaMattress clock and queries

Examples use local time 2026-11-03 05:34:12, a Tuesday (weekday `02`; Monday is
1, Sunday 7).

| Command | P1 | P2 | P3 | P4 |
|---------|----|----|----|----|
| Set clock (`setCurrentTime`) | `E7 80 01 7E 0B 03 05 22 0C D8` | ❌ | `07 04 1A 0B 03 02 05 22 0C` | `07 04 7E 0A 03 02 05 22 0C` |
| Query alarm (`queryAlarm`) | `E2 80 03 00 9A` | `E2 FE 16 0C 22 05 02 D4` | `00 C0` | `00 C0` |
| Query massage (`queryMassage`, `queryMassageOnce`) | `E6 FE 16 03 00 00 00 00 02` | ❌ | `00 B0` | `00 B0` |
| Query status (`queryControlBoxStatus`) | ❌ | ❌ | ❌ | `00 B0` |

| Clock layout | Fields |
| --- | --- |
| P1 | `E7 80 01`, year-1900, month, day, hour, minute, second, checksum |
| P3 | `07 04`, year-2000, month, day, weekday, hour, minute, second |
| P4 | `07 04`, year-1900, month-1, day, weekday, hour, minute, second |
| P2 query alarm | `E2 FE 16`, second, minute, hour, weekday, checksum |

#### Timing

##### AdjustaMattress command timing

| Item | Value |
| --- | --- |
| Refresh | 200 ms |
| First write, movement and lift | +200 ms |
| First write, presets and cyclic controls | Immediate |
| STOP after release | +200 ms, fresh cancellation event |
| Ordinary P3/P4 massage queries after release | +400 and +600 ms |
| Hold action duration | 1..60000 ms |
| Default pulse count / delay | 5 / 200 ms |

- Every bounded movement/preset/cyclic action finishes with the model's STOP at
  +200 ms after release, using a fresh cancellation event.
- A task cancellation finishes cleanup before the command lock is released.
- The card sends cancellation immediately on release; all start and cleanup
  delays belong to the backend.
- Awaited write time is subtracted from the refresh and cleanup waits.
- A normal button uses the configured pulse count at this cadence.

#### Notifications

##### AdjustaMattress notifications

No motor angle, percentage, height or current telemetry exists in the accepted
parser.

State sensors:

- Alarm fields (all models).
- Massage time/head/foot/wave (except P2).
- P4: sensitivity/strength, sleeping, enabled, demonstration, busy and the
  neutrally named **Auxiliary status bit 1**. It is not labelled occupancy or
  any other physical function.

| Model | Reply prefix | Content |
| --- | --- | --- |
| P1 | `ED 80` | Alarm hour, minute, repeat, action |
| P1 | `F4 FE 16` | Fragment buffered and joined with the next notification |
| P1 | 23-, 16- or 10-byte frames | Massage time, head, foot, wave |
| P2 | `E2 FE` (10+ bytes) | Alarm hour, minute, repeat, action |
| P3 / P4 | `A5 0C` | Alarm repeat, action, hour, minute, on |
| P3 / P4 | `A5 0B` | Massage time, head, foot, wave; P4 adds anti-snore and sleep status |
| P4 | `A6 40` | Busy |

- A6 40 busy status clears after 300 ms.
- Replies do not validate a checksum; truncated frames are rejected without
  partial mutation.

#### Services

##### AdjustaMattress alarms

- The Alarm hour/minute numbers and Alarm action select hold the alarm the
  **Alarm** switch sends; turning the switch on or off commits it. They start
  from the bed's reported alarm. Editing an enabled alarm is rejected.
- On commits repeat 255; Off commits repeat 0 on P1/P3/P4, while P2 uses its
  all-255 disable sentinel (hour, minute, action and repeat all 255).
- The Alarm action select offers the app's three choices, Memory A (17),
  Memory B (19) and Massage (9), and None (0), which the app stores when the
  selected choice is switched off. No weekday-bit interpretation is invented.
- The commit writes at +200 ms and refreshes the alarm at +600 ms.
- The Alarm switch shows the reported alarm state and waits for replies.
- Uncommitted alarm and strength edits survive BLE reconnects through the
  per-address/profile app session. Hydration cannot erase uncommitted edits.
  Nothing persists across Home Assistant restarts.

| Model | Set alarm frame | Action byte |
| --- | --- | --- |
| P1 | `ED 80 03` HH MM repeat action, eight `00`, checksum | Action code; 0 is sent as `13` (19) |
| P2 | `EB FE 16` ss mm hh MM HH weekday repeat, three action bytes, checksum | 9: `11 11 FF`; 17: `FF FF 08`; 19: `FF FF 09`; other: `FF FF FF` |
| P3 | `07 05` repeat action HH MM `00` enabled `01` | 9: `08`; 17: `05`; other: `06` |
| P4 | `08 05` repeat action HH MM `00` enabled `00 00` | 9: `08`; 19: `06`; other: `05` |

`enabled` is `01` when repeat is nonzero. Examples for 07:30, action 19, clock as
above:

| Commit | P1 | P2 | P3 | P4 |
| --- | --- | --- | --- | --- |
| On | `ED 80 03 07 1E FF 13 00 00 00 00 00 00 00 00 58` | `EB FE 16 0C 22 05 1E 07 02 FF FF FF 09 A0` | `07 05 FF 06 07 1E 00 01 01` | `08 05 FF 06 07 1E 00 01 00 00` |
| Off | `ED 80 03 07 1E 00 13 00 00 00 00 00 00 00 00 57` | `EB FE 16 0C 22 05 FF FF 02 FF FF FF FF D1` | `07 05 00 06 07 1E 00 00 01` | `08 05 00 06 07 1E 00 00 00 00` |

##### AdjustaMattress anti-snore and sleep (P4 L0/L3)

P4 L0/L3 additionally expose the **Intelligent anti-snore** and **Sleep mode**
switches, demonstration, a status refresh and the anti-snore strength.

| Command | Bytes |
| --- | --- |
| Anti-snore (`_sendAntiSnoreCommand`) | `05 0B` mode strength `01 23 00` |
| Sleep start / stop (`toggleSleeping`) | `01 B5 01` / `01 B5 00` |
| Status query (`queryControlBoxStatus`) | `00 B0` |

- Anti-snore mode byte: `02` when demonstration is set, otherwise `01` enabled
  or `00` disabled (wire mode 2 is demonstration).
- Strength index 0/1/2 sends `01`/`03`/`06`; `23` is threshold 35.
- The app shows a privacy notice before enabling anti-snore; turning the switch
  on in Home Assistant is that consent, so there is no separate entity.
- Enabling clears demonstration; disabling preserves it, so a retained
  demonstration can still select wire mode 2.
- Demonstration requires intelligent anti-snore to be disabled.
- The Anti-snore strength select applies with the next anti-snore command
  (switching it on, demonstration or sleep), without an immediate write.

###### AdjustaMattress sleep action

- Before each Sleep mode change, HA queries and awaits a fresh P4 status report.
  The switch sends the app's toggle only when that report differs from the
  requested state.
- A five-second HA readiness guard rejects a missing reply without sending a
  sleep command. This is an integration guard, not a discovered device timer;
  old replies or reconnect defaults cannot determine the direction.
- The following app sequence starts only after that fresh report.
- Starting while anti-snore is disabled enables it, forces strength index
  1/threshold 35, preserves demonstration, sends the anti-snore helper
  immediately and sleep at +200 ms. Otherwise sleep is immediate.
- Both query status at +500 ms. Reported sleeping changes only on notification.

#### Evidence

##### AdjustaMattress notes

###### AdjustaMattress app defects

HA deliberately does not reproduce these app defects:

- P2 lighting allocates no light frame. It resends the previous arbitrary frame,
  including a prior motor command, and starts refresh. This replay is excluded;
  P2 has no HA lighting action. No replacement opcode is guessed.
- P2 timer release starts unbounded refresh with no paired release STOP. HA
  exposes its exact timer bytes as a bounded action with STOP, excluding the
  orphaned timer. Dormant timer branches on other models are not promoted.
- App timers read one mutable buffer, so unrelated queries/settings can replace
  pending commands or a delayed STOP. HA holds the coordinator command lock for
  the whole operation and uses the operation's own bytes. Cross-operation frame
  substitution and orphaned refresh after disconnect are excluded.
- Phone UI tab/render timers, including the HomeBloc's movement-time
  shared-buffer polling, do not run in HA. Their underlying alarm, massage and
  status queries are explicit native refresh actions, with the app's query
  timing. They cannot overwrite an active held motor frame or its STOP.
- Invalid-length crashes, unknown-fragment resets to zero, and missed on-only
  callbacks are phone parser defects. HA guards complete indexed fields, retains
  known telemetry on unknown fragments and publishes valid on-only changes.

###### AdjustaMattress connection and scope boundaries

- Connection/adapter/proxy policy belongs to HA.
- The controller subscribes before clock/alarm hydration, retries the FFE notify
  subscription once after one second, and does not perform Android-specific
  MTU/PHY/permission/cache/bond operations.
- No app PIN/authentication command, Wi-Fi provisioning, network administration,
  cloud/account control, firmware upload or bed reset is recovered.
- Generic SDK networking and phone infrastructure are excluded from this
  BLE-only profile.

###### AdjustaMattress hardware validation

- Physical validation is deferred: confirm raw
  name/GATT selection, layout roles, held release/cancel, alarms, massage
  replies and P4 status meanings.


###### AdjustaMattress analysis provenance

Based on AdjustaMattress 1.6.0 (`com.okin.adjustamattress`).

### ComfortBaseForBluetooth

**App:** [ComfortBaseForBluetooth](https://play.google.com/store/apps/details?id=com.ore.yorkfeng.comfortbaseble2) 1.1.2 (6), `com.ore.yorkfeng.comfortbaseble2`

**Status:** Not yet tested

#### Setup

Choose **ComfortBaseForBluetooth app** (ComfortBase BLE), then the product shown in the app. Product selection sets the axes and massage controls; it is never a wire selector. Detection: none. The app scans all BLE devices without name, service or manufacturer filters, so shared Keeson discovery cannot identify this app. No PIN, authentication or initial command is required.

The write role is FFE9 under FFE5, and notification role FFE4 under FFE0. Home Assistant subscribes and waits for subscription success before admitting commands. The live characteristic properties determine the supported write mode. Android's writeType and CCCD enable fields are runtime platform values, not literals embedded in the APK.

#### Controls

All five presets support recall and the app's repeated-frame save gesture. Memory A/B are presets, not Left/Right controls. The elevation key is labelled height, not lumbar; back/neck tilt is a separate key. The combined control sends only its fixed head-and-foot command. Every product transmits selector zero; arbitrary selectors and concurrent independent motors are unavailable.

Massage exposes timer cycle, wave next/previous and overall intensity up/down. The light action toggles only. Freestyle has no massage or light controls. No absolute intensity, discrete light state or direct timer selection is inferred.

<!-- generated:keeson-comfortbase -->
| Product | App value | Controls | Massage / light |
|---|---|---|---|
| SS18X20 | 15 | head, feet, elevate | Yes |
| SS18X40 | 16 | head, feet, both, elevate, tilt | Yes |
| SSX25 | 17 | head, feet, elevate | Yes |
| SSX45 | 18 | head, feet, both, elevate, tilt | Yes |
| Freestyle 2.0 | 14 | head, feet | No |
| Accord | 11 | head, feet, elevate | Yes |
| Vesta | 12 | head, feet, elevate | Yes |
| Odessa | 13 | head, feet, both, elevate, tilt | Yes |
| Somerston | 19 | head, feet | Yes |
| Madrid | 20 | head, feet, tilt | Yes |

| Action | Frame |
|---|---|
| head up | `E6 FE 16 01 00 00 00 00 04` |
| head down | `E6 FE 16 02 00 00 00 00 03` |
| feet up | `E6 FE 16 04 00 00 00 00 01` |
| feet down | `E6 FE 16 08 00 00 00 00 FD` |
| both up | `E6 FE 16 05 00 00 00 00 00` |
| both down | `E6 FE 16 0A 00 00 00 00 FB` |
| tilt up | `E6 FE 16 10 00 00 00 00 F5` |
| tilt down | `E6 FE 16 20 00 00 00 00 E5` |
| elevate up | `E6 FE 16 40 00 00 00 00 C5` |
| elevate down | `E6 FE 16 80 00 00 00 00 85` |
| zero_g | `E6 FE 16 00 10 00 00 00 F5` |
| flat | `E6 FE 16 00 00 00 08 00 FD` |
| anti_snore | `E6 FE 16 00 80 00 00 00 85` |
| Memory 1 | `E6 FE 16 00 20 00 00 00 E5` |
| Memory 2 | `E6 FE 16 00 40 00 00 00 C5` |
| timer | `E6 FE 16 00 02 00 00 00 03` |
| wave_next | `E6 FE 16 00 00 00 10 00 F5` |
| wave_previous | `E6 FE 16 00 00 00 04 00 01` |
| intensity_up | `E6 FE 16 00 0C 00 00 00 F9` |
| intensity_down | `E6 FE 16 00 00 80 01 00 84` |
| Light toggle | `E6 FE 16 00 00 02 00 00 03` |
| STOP | `E6 FE 16 00 00 00 00 00 05` |

| Setting | Value |
|---|---|
| Write service / characteristic | `0000ffe5-0000-1000-8000-00805f9b34fb` / `0000ffe9-0000-1000-8000-00805f9b34fb` |
| Notify service / characteristic | `0000ffe0-0000-1000-8000-00805f9b34fb` / `0000ffe4-0000-1000-8000-00805f9b34fb` |
| Held refresh | 100 ms |
| Save all five presets | 6 s held recall, then STOP |
| Alarm sequence | Two clock writes, 150 ms wait, one alarm |
| Clock | E7 80 01, year minus 1900, zero-based month, day, hour, minute, second, checksum |
| Alarm | ED 80 03, hour, minute, opaque FF, Memory A 0E / B 0F, eight zeros, checksum |
| Alarm cancel | `ED 80 03 00 00 00 00 00 00 00 00 00 00 00 00 8F` |
<!-- /generated -->

#### Timing

The generated table gives the refresh and save duration. Movement refreshes while held and sends an immediate zero STOP on release or cancellation. A tap recall sends once without STOP. Each save owns its bounded gesture and completes STOP before another command runs; no delayed callback can stop a subsequent movement. A local completed save is not a firmware acknowledgement.

#### Notifications

The app's timer display uses the low nibble at offset 8 for length 10, 14 for length 16 and 19 for length 23. Values 1/2/3 show 10/20/30 minutes; other values show zero. Other lengths show zero, without header or checksum checks. No position, light state, wave, intensity, alarm or acknowledgement parser exists.

An F4 FE 16 prefix of 7 to 20 bytes begins a fragmented reply. Home Assistant bounds the assembled pair to 23 bytes, consumes its prefix once, ignores empty tails and clears partial state on reconnect or a direct reply. This prevents the app's indefinite stale-prefix replay. Timer state becomes unknown after disconnect.

#### Services

`adjustable_bed.set_alarm` enables a bed alarm for Memory A (1) or B (2), or cancels it. Enabling sends local wall-clock sync twice, waits, then writes the selected time and preset. The third alarm parameter stays opaque; no weekday controls are offered. `adjustable_bed.sync_clock` performs the two clock writes independently. The alarm is available on every product, including Freestyle. Two-address HA pairs preserve their physical target; this app provides no single-address side controls.

#### Evidence

Based on AdjustaMattress 1.6.0 (10): all ten product choices, 31 actions, 43
builders and 20 notification cases. The save gesture repeats the recall bytes;
whether the bed stores the position still needs testing by owners.


### OkimattMotion

**App:** [OkimattMotion](https://apkpure.com/okimattmotion/com.okin.jalon.okimatandroid) 1.1.1 (3), `com.okin.jalon.okimatandroid`

**Status:** Not yet tested on hardware.

#### Setup

Choose **OkimattMotion app** for the Bluetooth address you use with this app.
The scan prefixes below are shared across devices, so Home Assistant leaves
the profile choice to you. The extended layout covers
the app's fallback and adds combined movement and Book. Both layouts have
the same two independently controlled axes and expect the same writable
characteristic. Home Assistant chooses the write mode from its actual
properties, preferring write with response when available. The APK inherits
Android's write type. Its actual ATT mode remains unverified.

<!-- generated:keeson-okimattmotion-setup -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

Android scan prefixes: `okin`, `comfort`, `ble`.

| App layout | Available movement |
|---|---|
| 20 | Back and legs |
| 30 | Back and legs with combined movement and Book |

| GATT role | Service | Characteristic |
|---|---|---|
| Write | `0000ffe5-0000-1000-8000-00805f9b34fb` | `0000ffe9-0000-1000-8000-00805f9b34fb` |
| Android notification registration | `0000ffe0-0000-1000-8000-00805f9b34fb` | `0000ffe4-0000-1000-8000-00805f9b34fb` |
<!-- /generated -->

#### Controls

Flat, Zero Gravity, Quiet Sleep and the two memory slots each have recall and
save. Book recalls Quiet Sleep on the extended layout. The native preset
buttons always recall the selected position. Use **Stop all** to cancel a
recall. The motor controls' own Stop releases manual movement.

The massage power switch, overall intensity, wave, duration and light show
commanded state. Intensity and wave each retain the other level when changed.
You can set the duration with massage off. Power on always sends the 10-minute
timer, and power off clears the displayed choice. The timer select shows the
last duration sent. It does not count down.

<!-- generated:keeson-okimattmotion-controls -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Movement | Frame |
|---|---|
| Back up | `E5 FE 16 00 00 00 01 05` |
| Back down | `E5 FE 16 00 00 00 02 04` |
| Legs up | `E5 FE 16 00 00 00 04 02` |
| Legs down | `E5 FE 16 00 00 00 08 FE` |
| Back and legs up | `E5 FE 16 00 00 00 05 01` |
| Back and legs down | `E5 FE 16 00 00 00 0A FC` |
| Manual release | `E5 FE 16 00 00 00 00 06` |
| Preset STOP | `E5 FE 16 21 00 00 00 E5` |

| Position | Recall | Save |
|---|---|---|
| Zero Gravity | `E5 FE 16 21 00 00 01 E4` | `E5 FE 16 21 00 00 11 D4` |
| Flat | `E5 FE 16 21 00 00 02 E3` | `E5 FE 16 21 00 00 12 D3` |
| Quiet Sleep / Book | `E5 FE 16 21 00 00 03 E2` | `E5 FE 16 21 00 00 13 D2` |
| Memory A | `E5 FE 16 21 00 00 04 E1` | `E5 FE 16 21 00 00 14 D1` |
| Memory B | `E5 FE 16 21 00 00 06 DF` | `E5 FE 16 21 00 00 16 CF` |

| Massage level | Intensity frame | Wave frame |
|---|---|---|
| 0 | `E5 FE 16 10 00 00 10 E6` | `E5 FE 16 10 00 00 20 D6` |
| 1 | `E5 FE 16 10 00 00 11 E5` | `E5 FE 16 10 00 00 21 D5` |
| 2 | `E5 FE 16 10 00 00 12 E4` | `E5 FE 16 10 00 00 22 D4` |
| 3 | `E5 FE 16 10 00 00 13 E3` | `E5 FE 16 10 00 00 23 D3` |

| Control | Frame |
|---|---|
| Massage timer 10 min | `E5 FE 16 10 00 00 30 C6` |
| Massage timer 20 min | `E5 FE 16 10 00 00 31 C5` |
| Massage timer 30 min | `E5 FE 16 10 00 00 32 C4` |
| Light off | `E5 FE 16 30 00 00 00 D6` |
| Light on | `E5 FE 16 30 00 00 01 D5` |

Example clock writes at 12:34:56 for a 07:45 alarm.

| Sleep timer | Wake mode off | Wake mode on |
|---|---|---|
| Off | `EA FE 16 38 22 0C 2D 07 11 22 FF FF 36` | `EA FE 16 38 22 0C 2D 07 11 22 FF 04 31` |
| 10 min | `EA FE 16 38 22 0C 2D 07 11 22 30 FF 05` | `EA FE 16 38 22 0C 2D 07 11 22 30 04 00` |
| 20 min | `EA FE 16 38 22 0C 2D 07 11 22 31 FF 04` | `EA FE 16 38 22 0C 2D 07 11 22 31 04 FF` |
| 30 min | `EA FE 16 38 22 0C 2D 07 11 22 32 FF 03` | `EA FE 16 38 22 0C 2D 07 11 22 32 04 FE` |

Cancel frame in the same example: `EA FE 16 38 22 0C FF FF 11 22 FF FF 6C`.
<!-- /generated -->

#### Timing

Both layouts support renewable holds for their movement controls, including
combined movement when selected. Home Assistant serializes movement and sends
manual release on the same connection when a move completes or is interrupted.
A timed move uses its controller's completed release and retries an incomplete
one. **Stop all** also sends the preset STOP. A sequential pair reopens a
released target for **Stop all** while keeping one Bluetooth link open at a
time. Delivery and physical braking after a lost link need testing.

<!-- generated:keeson-okimattmotion-timing -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Operation | Writes |
|---|---|
| Movement | Immediate, then every 100 ms. Finite pulses or a renewable hold. |
| Manual release | 2 consecutive manual STOP writes. |
| Preset, save, light or timer | One write per action. |
| Massage power | Wave, 100 ms wait, then intensity. Power on then sends the 10 min timer. |
| Massage level change | Intensity then wave in immediate succession. |
| Set or cancel alarm | 2 consecutive writes, sampling local time for each. |
<!-- /generated -->

#### Notifications

The Android app registers the inbound characteristic locally and its receive
callback is empty. Home Assistant has no notification-dependent startup,
position feedback, alarm readback or accessory readback for this profile.

#### Services

Use [Set alarm](../SERVICES.md#set_alarm) with a local time and optionally
`wake_action: wake_mode_1` and `sleep_timer: 10`, `20` or `30`. Omit both
options for the clock-only setting. Set `enabled: false` to send the bed's
cancel frame. Matching hardware is needed to confirm the wake mode and sleep
timer effects. For recurring schedules, use a Home Assistant automation.

#### Evidence

Based on OkimattMotion 1.1.1 (3).

## Notes

### Timing sources

Cadence belongs to the app or protocol family, not to the shared 32-bit command
values. The values are in [Hold and release timing](#hold-and-release-timing).

| Profile | Timing source in the app |
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
| Sino / BetterLiving / OKIN | BetterLiving two-motor and three-motor screens |
| Purple | Purple Smart Base fixed-delay scheduler |

For existing Keeson entries, the integration translates only the stored generic
default cadence to the matching profile. Any pulse count or delay that a user
customized remains authoritative. Dedicated Ergomotion and OKIN FFE bed
types store their own defaults and are left unchanged.

### Analysis provenance

- Adjustable Lite 1.0.2, Restonic BT Remote 1.2.0, Simon Li, Heal Every Night
  and OKIN-Seating: based on their apps.
- MaxCoil Una 1.1.0 (`com.ore.maxcoil`), Dynasty Bases 1.0.2 (`com.ore.Dynasty`),
  Bedsense Bases 1.1 (`com.ore.sfmc2bedsence`), INNOVA 2.0 (`com.ore.sfm`),
  Avanti Bases 1.0.5 (`com.ore.AvantiBases`), AMERICANSTAR 1.0
  (`com.ore.americanstar`) and OKIN Comfort Bed 1.1.6.
- Keeson layout apps: see the [Keeson layout app family](#keeson-layout-app-family).
- The other routes come from the smartbed-mqtt reverse engineering, decompiled
  OEM apps and hardware reports.

### OkinComfortBed II

**App:** [Okin Comfortbed II N](https://play.google.com/store/apps/details?id=com.ore.jalon.neworebeding) 2.0.2 (9), `com.ore.jalon.neworebeding`

**Status:** Not yet tested

#### Setup

Choose **OkinComfortBed II N app** and the actuator layout
shown by the app. The two three-actuator layouts differ: one adds neck, the other
lumbar. This choice is independent of the transport. The light and massage controls
are always present; no position, battery, or capability feedback is reported.

Discovery admits names starting with `okin-ble` or `smartbed`, case insensitive.
These names are shared with other apps, so confirm this app in setup. On each live
connection, `smartbed` selects P3. For `okin-ble`, the presence of service `ff20`
selects P2; its absence selects P1. An edited HA display name never selects a
protocol. Notification registration precedes clock calibration. There is no PIN,
authentication command, pairing write, or keepalive. HA owns retries and idle
handoff, independently for each physical receiver. New setups keep the link
between commands because massage controls depend on its notification state.

The app normally connects to one receiver. It has no single-address side
selector, and it never combines separate motor commands. HA may combine two independently
configured addresses; each keeps its own layout, profile, parser and state.

#### Controls

Head/foot, optional neck/lumbar, Flat, Zero G, Lounge, TV, Anti-snore, and two
memory positions use the table below. The light is a toggle. Massage exposes
Toggle, Timer, Wave, Head intensity and Foot intensity buttons plus a refresh
button. Non-toggle massage controls require a fresh nonzero timer indicator.
No discrete massage on/off or intensity-down operation is inferred from unused
asset declarations.

Saving M1 or M2 holds the same recall command for the app's programming interval.
The app's success timer is not an acknowledgement. Recall taps use a short hold;
`hold_control` also exposes Flat and bounded memory recalls. Use `save_preset` for
programming. Every movement, recall, save, cancellation and explicit STOP awaits
the release pair before another command can use the receiver.

<!-- generated:keeson-jalon -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

#### Profiles and transport

| Profile | Write service | Write | Notify service | Notify | Response |
|---|---|---|---|---|---|
| jalon_13 | 0000ffe5-0000-1000-8000-00805f9b34fb | 0000ffe9-0000-1000-8000-00805f9b34fb | 0000ffe0-0000-1000-8000-00805f9b34fb | 0000ffe4-0000-1000-8000-00805f9b34fb | True |
| jalon_15 | 0000ffe5-0000-1000-8000-00805f9b34fb | 0000ffe9-0000-1000-8000-00805f9b34fb | 0000ffe0-0000-1000-8000-00805f9b34fb | 0000ffe4-0000-1000-8000-00805f9b34fb | False |
| jalon_24 | 6e400001-b5a3-f393-e0a9-e50e24dcca9e | 6e400002-b5a3-f393-e0a9-e50e24dcca9e | 6e400001-b5a3-f393-e0a9-e50e24dcca9e | 6e400003-b5a3-f393-e0a9-e50e24dcca9e | False |

#### Layouts

| App bedType | Actuators |
|---|---|
| 0 | head, feet |
| 10 | head, feet, tilt |
| 11 | head, feet, lumbar |
| 2 | head, feet, tilt, lumbar |

#### Commands

| Action | jalon_13 | jalon_15 | jalon_24 |
|---|---|---|---|
| stopCommand | `E6 FE 16 00 00 00 00 00 05` | `E6 FE 16 00 00 00 00 00 05` | `05 02 00 00 00 00 00` |
| headUp | `E6 FE 16 01 00 00 00 00 04` | `E6 FE 16 01 00 00 00 00 04` | `05 02 00 00 00 01 00` |
| headDown | `E6 FE 16 02 00 00 00 00 03` | `E6 FE 16 02 00 00 00 00 03` | `05 02 00 00 00 02 00` |
| footUp | `E6 FE 16 04 00 00 00 00 01` | `E6 FE 16 04 00 00 00 00 01` | `05 02 00 00 00 04 00` |
| footDown | `E6 FE 16 08 00 00 00 00 FD` | `E6 FE 16 08 00 00 00 00 FD` | `05 02 00 00 00 08 00` |
| neckUp | `E6 FE 16 10 00 00 00 00 F5` | `E6 FE 16 10 00 00 00 00 F5` | `05 02 00 00 00 10 00` |
| neckDown | `E6 FE 16 20 00 00 00 00 E5` | `E6 FE 16 20 00 00 00 00 E5` | `05 02 00 00 00 20 00` |
| lumbarUp | `E6 FE 16 40 00 00 00 00 C5` | `E6 FE 16 40 00 00 00 00 C5` | `05 02 00 00 00 40 00` |
| lumbarDown | `E6 FE 16 80 00 00 00 00 85` | `E6 FE 16 80 00 00 00 00 85` | `05 02 00 00 00 80 00` |
| memoryFlat | `E6 FE 16 00 00 00 08 00 FD` | `E6 FE 16 00 00 00 08 00 FD` | `05 02 08 00 00 00 00` |
| memoryZero | `E6 FE 16 00 10 00 00 00 F5` | `E6 FE 16 00 10 00 00 00 F5` | `05 02 00 00 10 00 00` |
| memoryLounge | `E6 FE 16 00 20 00 00 00 E5` | `E6 FE 16 00 20 00 00 00 E5` | `05 02 00 00 20 00 00` |
| memoryTvpc | `E6 FE 16 00 40 00 00 00 C5` | `E6 FE 16 00 40 00 00 00 C5` | `05 02 00 00 40 00 00` |
| memoryAntiSnore | `E6 FE 16 00 80 00 00 00 85` | `E6 FE 16 00 80 00 00 00 85` | `05 02 00 00 80 00 00` |
| memory1M5 | `E6 FE 16 00 00 01 00 00 04` | `E6 FE 16 00 00 01 00 00 04` | `05 02 00 01 00 00 00` |
| memory2M6 | `E6 FE 16 00 00 04 00 00 01` | `E6 FE 16 00 00 04 00 00 01` | `05 02 00 04 00 00 00` |
| lightSwitch | `E6 FE 16 00 00 02 00 00 03` | `E6 FE 16 00 00 02 00 00 03` | `05 02 00 02 00 00 00` |
| massageSwitch | `E6 FE 16 00 01 00 00 00 04` | `E6 FE 16 00 01 00 00 00 04` | `05 02 00 00 01 00 00` |
| massageTimeSwitch | `E6 FE 16 00 02 00 00 00 03` | `E6 FE 16 00 02 00 00 00 03` | `05 02 00 00 02 00 00` |
| strengthHeadUp | `E6 FE 16 00 08 00 00 00 FD` | `E6 FE 16 00 08 00 00 00 FD` | `05 02 00 00 08 00 00` |
| strengthFootUp | `E6 FE 16 00 04 00 00 00 01` | `E6 FE 16 00 04 00 00 00 01` | `05 02 00 00 04 00 00` |
| massageWaveSwitch | `E6 FE 16 00 00 00 10 00 F5` | `E6 FE 16 00 00 00 10 00 F5` | `05 02 10 00 00 00 00` |

#### Queries and clock

| Action | jalon_13 | jalon_15 | jalon_24 |
|---|---|---|---|
| Massage query | `00 00 00 00` | `00 00 00 00` | `00 B0` |
| Alarm query | Unavailable | `E2 80 03 00 9A` | `00 C0` |
| Clock (2026-11-10 Tue 13:14:15) | `07 04 1A 0B 0A 02 0D 0E 0F` | `E7 80 01 7E 0A 0A 0D 0E 0F DB` | `07 04 1A 0B 0A 02 0D 0E 0F` |

#### Wake types

| Action | P2 | P3 |
|---|---|---|
| flat | 28 | 9 |
| memory_1 | 17 | 5 |
| memory_2 | 19 | 6 |
| zero_g | 13 | 1 |
| anti_snore | 16 | 4 |
| tv | 15 | 3 |
| massage | 9 | 8 |

#### Timing

| Operation | Behavior |
|---|---|
| Held movement / Flat / M1 / M2 | Immediate; refresh every 300 ms |
| Release / explicit STOP | Immediate STOP and one more after 300 ms |
| Preset tap | Single write; release after 100 ms |
| Memory recall | One 300 ms hold then release |
| Memory programming | Same recall word held 6000 ms then release |
| Massage toggle | Single toggle; query after 100 ms |
| Clock sync | Two identical writes 300 ms apart, after connect |
| Alarm query | After 100 ms: P2 twice at 300 ms; P3 once |
| Alarm set | One write; query after 100 ms: P2 twice, P3 three times at 350 ms |
<!-- /generated -->

#### Timing

The generated timing table describes each sequence. HA retains its command lane
through both STOP writes, including repeated cancellation and a failed first
STOP. The app's global timer can cancel its second STOP or another receiver's
work; HA deliberately uses per-receiver state and awaited cleanup instead.
Massage toggle sends one effective toggle, matching the normal UI's query that
cancels the app's pending extra toggle. There is no periodic status query.

#### Notifications

Each notification is independent, without reassembly or an inferred checksum.
P1/P2 normal massage uses `ED FE`; only P2 consumes the long `F4 FE` form. P3
uses `A5 0B`. The sensor exposes the app's timer indicator (values above four
become zero), decoded wave, and head/foot strength as attributes. The indicator
has no asserted minute unit. Strength uses the app's nibble mapping on P1/P2 and
integer division on P3, including their zero-value distinctions.

Alarm dispatch accepts the app's hardcoded `A5 0C`, `A5 0D`, or `ED 80 03` headers
and interprets fields with the selected profile. Its sensor exposes enabled state,
weekday mask, raw wake type, hour, minute and first/second indicator. P1 can parse
alarm replies but has no setter or query. P3's declared two-byte minute
field still reads only the first byte, as the app does. HA rejects incomplete
records rather than converting missing fields to invented zero state, and clears
all reported state when the session ends.

#### Services

`set_alarm` supports P2 and P3: `device_id`, `enabled`, minute-precision
`time`, optional `weekdays` (`mon` through `sun`) and `wake_mode` from the generated
table. Empty weekdays means the next occurrence, as in the app. Sunday is bit 0,
Monday bit 1 through Saturday bit 6; bit 7 marks a recurring selection. P2 disables by zeroing its record; P3 retains
the fields and clears its enabled byte. No phone alarm, ringtone or audio is
configured. Use the generic `sync_clock` action to repeat calibration explicitly.

#### Evidence

Based on `com.ore.jalon.neworebeding` 2.0.2 (9).
The three profiles reproduce every ordinary, raw, clock and alarm vector;
notification vectors are synthetic inputs rather than captured hardware traffic.
Tests: `tests/test_jalon.py`, `tests/fixtures/jalon/vectors.json`.
Real-user testing by owners remains needed for STOP, programming, write mode,
P1 clock fallback, massage interpretation and bed-local alarms.

### OkinComfortBed Ⅱ (Jalon)

**App:** [OkinComfortBed Ⅱ](https://apkpure.com/okin-comfortbed-%E2%85%B1/com.ore.jalon.neworebeding_android) 1.4 (4), `com.ore.jalon.neworebeding_android`

**Status:** Not yet tested

#### Setup

Choose **OkinComfortBed II app** (`com.ore.jalon.neworebeding_android`).
Detection: none. The app scans all devices without a name, service or manufacturer
advertisement filter. Select the address manually, then the physical layout.
The similarly named ORE and Okin apps are separate setup choices.

The four layouts below own motor count, massage and the fixed refresh cadence.
Every layout uses wire model zero. There is no native side selector, angle
feedback, authentication, PIN, capability exchange or connect-time command.
Two separate receivers can use HA's ordinary paired-bed infrastructure.

TX is FFE9 under service FFE5; notifications are FFE4 under service FFE0
(all Bluetooth base UUIDs). Commands require the current session's writable TX
characteristic. ATT response mode follows live GATT properties: acknowledged
writes when available, otherwise write without response. The APK does not set
or require a fixed write type. HA serializes writes and subscribes through Bleak.

#### Controls

<!-- generated:keeson-jalon-bed -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Control | Word | Frame |
|---|---|---|
| back up | `0x00000001` | `E6 FE 16 01 00 00 00 00 04` |
| back down | `0x00000002` | `E6 FE 16 02 00 00 00 00 03` |
| feet up | `0x00000004` | `E6 FE 16 04 00 00 00 00 01` |
| feet down | `0x00000008` | `E6 FE 16 08 00 00 00 00 FD` |
| head up | `0x00000010` | `E6 FE 16 10 00 00 00 00 F5` |
| head down | `0x00000020` | `E6 FE 16 20 00 00 00 00 E5` |
| lumbar up | `0x00000040` | `E6 FE 16 40 00 00 00 00 C5` |
| lumbar down | `0x00000080` | `E6 FE 16 80 00 00 00 00 85` |
| flat | `0x08000000` | `E6 FE 16 00 00 00 08 00 FD` |
| zero_g | `0x00001000` | `E6 FE 16 00 10 00 00 00 F5` |
| lounge | `0x00002000` | `E6 FE 16 00 20 00 00 00 E5` |
| tv | `0x00004000` | `E6 FE 16 00 40 00 00 00 C5` |
| anti_snore | `0x00008000` | `E6 FE 16 00 80 00 00 00 85` |
| memory_1 | `0x00010000` | `E6 FE 16 00 00 01 00 00 04` |
| memory_2 | `0x00040000` | `E6 FE 16 00 00 04 00 00 01` |
| flat_zero_g | `0x08001000` | `E6 FE 16 00 10 00 08 00 ED` |
| massage head | `0x00000800` | `E6 FE 16 00 08 00 00 00 FD` |
| massage feet | `0x00000400` | `E6 FE 16 00 04 00 00 00 01` |
| massage all | `0x00000100` | `E6 FE 16 00 01 00 00 00 04` |
| massage timer | `0x00000200` | `E6 FE 16 00 02 00 00 00 03` |
| massage type | `0x10000000` | `E6 FE 16 00 00 00 10 00 F5` |
| light toggle | `0x00020000` | `E6 FE 16 00 00 02 00 00 03` |
| STOP/release | `0x00000000` | `E6 FE 16 00 00 00 00 00 05` |

| Layout | App layout | HA axes | Wire model |
|---|---|---|---|
| 20 | 2 motors: back and feet | back, feet | 0 |
| 30 | 3 motors: headrest, back and feet | head, back, feet | 0 |
| 31 | 3 motors: waist, back and feet | lumbar, back, feet | 0 |
| 40 | 4 motors: headrest, back, feet and waist | head, back, feet, lumbar | 0 |

| Timing / writes | Value |
|---|---|
| Motor refresh / releases before and after | 100 ms / 3 |
| Preset tap / position-page Flat / release | 3 / 2 / 1 |
| Held preset refresh / maximum / release | 100 ms / 8000 ms / none |
| Massage and light / releases | 3 / 2 |
| Time sync to alarm / disabled alarm / release | 100 ms / 2 / 1 |

| Wake action | Mode byte |
|---|---|
| none | `00` |
| memory_1 | `11` |
| memory_2 | `13` |
| massage | `09` |
<!-- /generated -->

Back is the app's head/back actuator; head is the separate headrest; lumbar is
labelled waist. Each layout exposes only its own axes. Presets and two memories
are recalls. The additional app-gesture buttons support held recall through
`hold_control`, including the combined Flat + Zero G gesture. An eight-second
"setting success" toast in the app does not prove physical memory programming
or factory reset. HA does not label these gestures Save or Reset.

Massage buttons send the app's head, feet, all, timer-cycle and type actions.
They do not promise numeric intensity, a particular timer transition or pattern.
The light has a native toggle; on/off uses known reported state and refuses an
unknown state. Commands do not manufacture feedback.

#### Timing

The generated table gives the app-specific refresh and burst counts. Motor
commands release before starting and in `finally` on cancellation, with fresh
cancel events for all release writes. The regular Flat action follows the
position-page two-write path; the app-gesture Flat button follows its three-write
memory-page path. All immediate bursts use serialized writes without invented
delays. Preset touch-up ends refresh without a release frame. An explicit HA
Stop still sends the motor release sequence. Renewable holds also stop when
the lease expires; preset gestures are capped at the app's eight seconds.

HA owns command admission and cancels work on disconnect/unload. It does not
reproduce Android's stale GATT pointers, uncancelled delayed handlers, old scan
callbacks stopping new scans, or timers continuing after the activity closes.

#### Notifications

The timer indicator is a 0/10/20/30-minute bucket, not a remaining-time countdown.
Standalone 10/16-byte replies use timer/light offsets 8/7 and 14/13. An F4 FE 16
prefix plus its next tail must total 23 bytes, with offsets 19/18. The signed
light byte shifted right by six is on only when positive: high-bit values
remain off, just as the app displays them. No position or massage-level state
is inferred.

HA consumes a fragment once and clears it on standalone replies, invalid tails
and disconnect. It refuses unrelated callbacks and unsupported lengths, instead
of repeating the Android parser's stale fragment or default-zero publication.
The app does not validate reply checksums or prove ACK correlation.

#### Services

`adjustable_bed.set_alarm` accepts `enabled`, minute-precision `time`,
`weekdays` (`monday` through `sunday`) and `wake_action` (`none`, `memory_1`,
`memory_2`, `massage`), plus the standard device/side target. Empty weekdays
chooses today if the selected hour/minute is later, otherwise tomorrow.
Repeating days set bit 7; Sunday is bit 0. Weekdays and all days yield BE and FF.

Enabling/updating first sends **current local time**, independently of the
selected alarm fields: E7 80 01, year minus 1900, zero-based month, day,
hour, minute, second, checksum. It then waits the generated delay and sends
one ED 80 03 record (selected hour, minute, day mask, wake mode), padded with
eight zeros and checksummed, followed by one release. Disabling sends the fixed
all-zero alarm twice and one release, with no clock sync. HA snapshots selected
fields and revalidates the live transport; an old delayed callback cannot write
into a newer session. The generic `sync_clock` action synchronizes only the bed
clock. Phone-local audio and scheduling are outside the integration.

#### Evidence

This app has one BLE protocol and four selectable layouts.
`tests/fixtures/jalon_bed/vectors.tsv` preserves all 393 Java cases, including
unused-builder and signed-parser boundaries; `tests/test_jalon_bed.py` compares
them through the shared codec and verifies gestures, layout gates and alarms.



### Symphony Sleep

**App:** [Symphony Sleep](https://play.google.com/store/apps/details?id=com.ore.bedding.symphony) 1.1.0 (14), `com.ore.bedding.symphony`

**Status:** Not yet tested

#### Setup

Detection: none. Choose **Symphony Sleep app**, then the exact model and
independent Box 1, Box 2 or fallback transport. The phone uses raw scan-record
offsets and case-sensitive platform names. HA does not reconstruct those offsets
from advertisement fields or identify this app from shared UUIDs or names.
A saved model and transport survive Configure, restore and two-address pairing;
configure each physical receiver separately. There is no native side selector.
Symphony Sleep Sense is a separate product.

The model chooses the app's controls, independently of a generic motor count.
400E is the B450 screen. The physical actuator count and anatomy still need
confirmation from owners. Neither memory A nor B denotes a bed side.

#### Controls

The generated tables list every model, transport, control and frame. Box 1 and
fallback use the Keeson E6 frame; Box 2 uses the byte-identical P2 / Okin frame 40
carrier. Its final zero byte is fixed auxiliary data, with no side selection.
The write mode follows the live characteristic properties, using acknowledged
writes when offered and otherwise write without response. Both the exact write
and notification roles must be usable; subscription failure aborts setup.

Presets are Flat, Zero G, Anti-snore and two named memories. Recall and save
use the same packet: **Save preset** holds A or B for the app's local success
interval. That interval is not a device acknowledgement or a known hardware
completion threshold. All four models above 400E have a toggle light and
relative total-body massage wave, intensity, timer-cycle and off controls.
They provide no absolute intensity, wave or light state.

<!-- generated:keeson-symphony-sleep -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

##### Models

| Model | App controls | Light / massage |
|---|---|---|
| 400E, Premier Series 400 | head, feet, bed_height | False |
| 500E, Premier Series 500 | head, feet, both, bed_height | True |
| 600E, Premier Series 600 | head, feet, neck, bed_height | True |
| SS300, Superior Sleep 300 | head, feet, both, bed_height | True |
| SS600, Superior Sleep 600 | head, feet, lumbar, bed_height | True |

##### Transports

| Selection | Write service / characteristic | Notify service / characteristic | Parser |
|---|---|---|---|
| box1 | 0000ffe5-0000-1000-8000-00805f9b34fb / 0000ffe9-0000-1000-8000-00805f9b34fb | 0000ffe0-0000-1000-8000-00805f9b34fb / 0000ffe4-0000-1000-8000-00805f9b34fb | P1 |
| box2 | 6e400001-b5a3-f393-e0a9-e50e24dcca9e / 6e400002-b5a3-f393-e0a9-e50e24dcca9e | 6e400001-b5a3-f393-e0a9-e50e24dcca9e / 6e400003-b5a3-f393-e0a9-e50e24dcca9e | P2 |
| fallback | 0000ffe5-0000-1000-8000-00805f9b34fb / 0000ffe9-0000-1000-8000-00805f9b34fb | 0000ffe0-0000-1000-8000-00805f9b34fb / 0000ffe4-0000-1000-8000-00805f9b34fb | disabled |

##### Normal controls

| Control | P1 | P2 |
|---|---|---|
| head_up | `E6 FE 16 01 00 00 00 00 04` | `05 02 00 00 00 01 00` |
| head_down | `E6 FE 16 02 00 00 00 00 03` | `05 02 00 00 00 02 00` |
| feet_up | `E6 FE 16 04 00 00 00 00 01` | `05 02 00 00 00 04 00` |
| feet_down | `E6 FE 16 08 00 00 00 00 FD` | `05 02 00 00 00 08 00` |
| both_up | `E6 FE 16 05 00 00 00 00 00` | `05 02 00 00 00 05 00` |
| both_down | `E6 FE 16 0A 00 00 00 00 FB` | `05 02 00 00 00 0A 00` |
| tilt_up | `E6 FE 16 10 00 00 00 00 F5` | `05 02 00 00 00 10 00` |
| tilt_down | `E6 FE 16 20 00 00 00 00 E5` | `05 02 00 00 00 20 00` |
| lumbar_up | `E6 FE 16 10 00 00 00 00 F5` | `05 02 00 00 00 10 00` |
| lumbar_down | `E6 FE 16 20 00 00 00 00 E5` | `05 02 00 00 00 20 00` |
| bed_height_up | `E6 FE 16 40 00 00 00 00 C5` | `05 02 00 00 00 40 00` |
| bed_height_down | `E6 FE 16 80 00 00 00 00 85` | `05 02 00 00 00 80 00` |
| flat | `E6 FE 16 00 00 00 08 00 FD` | `05 02 08 00 00 00 00` |
| zero_g | `E6 FE 16 00 10 00 00 00 F5` | `05 02 00 00 10 00 00` |
| anti_snore | `E6 FE 16 00 80 00 00 00 85` | `05 02 00 00 80 00 00` |
| memory_A_recall_and_hold_save | `E6 FE 16 00 20 00 00 00 E5` | `05 02 00 00 20 00 00` |
| memory_B_recall_and_hold_save | `E6 FE 16 00 40 00 00 00 C5` | `05 02 00 00 40 00 00` |
| stop | `E6 FE 16 00 00 00 00 00 05` | `05 02 00 00 00 00 00` |
| light_toggle | `E6 FE 16 00 00 02 00 00 03` | `05 02 00 02 00 00 00` |
| massage_wave_next | `E6 FE 16 00 00 00 10 00 F5` | `05 02 10 00 00 00 00` |
| massage_wave_previous | `E6 FE 16 00 00 00 04 00 01` | `05 02 04 00 00 00 00` |
| massage_intensity_up | `E6 FE 16 00 0C 00 00 00 F9` | `05 02 00 00 0C 00 00` |
| massage_intensity_down | `E6 FE 16 00 00 80 01 00 84` | `05 02 01 80 00 00 00` |
| massage_off | `E6 FE 16 00 00 00 02 00 03` | `05 02 02 00 00 00 00` |
| massage_timer | `E6 FE 16 00 02 00 00 00 03` | `05 02 00 00 02 00 00` |

##### Bed alarm and clock

| Action | P1 | P2 |
|---|---|---|
| Query alarm | `E2 80 03 00 9A` | `00 C0` |
| Clock, 2026-11-12 Thursday 06:45:59 | `E7 80 01 7E 0A 0C 06 2D 3B 95` | `07 04 26 11 12 04 06 45 59` |
| Disable | `ED 80 03 00 00 00 00 00 00 00 00 00 00 00 00 8F` | `07 05 00 00 00 00 00 00 00` |
| Enable 06:45, none | `ED 80 03 06 2D FF 00 00 00 00 00 00 00 00 00 5D` | `07 05 FF 00 06 45 00 01 00` |
| Enable 06:45, memory_1 | `ED 80 03 06 2D FF 11 00 00 00 00 00 00 00 00 4C` | `07 05 FF 02 06 45 00 01 00` |
| Enable 06:45, memory_2 | `ED 80 03 06 2D FF 13 00 00 00 00 00 00 00 00 4A` | `07 05 FF 03 06 45 00 01 00` |

##### Schedules

| Operation | Schedule |
|---|---|
| Held controls | Immediately, then every 300 ms; bounded HA presses use configured pulse count |
| Release / STOP | Immediately, +300 ms, +600 ms; awaited on the captured session |
| Memory A/B program | Same recall stream for 5200 ms, then release; no completion ACK |
| P2 massage query | 00 B0 at +300 ms and +600 ms, independent of release |
| Alarm enable or disable | RTC now, wait 300 ms, alarm; P2 query at +300 ms and +500 ms after alarm |
| Refresh alarm | Query now and +200 ms |
<!-- /generated -->

#### Timing

The schedules above apply only to this app. Timed movement uses elapsed time,
including slow acknowledged writes. Ordinary presses keep the configured pulse
count; renewable card leases continue the same stream until release or expiry.
All motor and utility gestures share one physical scheduling resource. Cleanup
captures the admitted frame, characteristic, client and session. STOPs are
awaited inside that lane and cannot migrate to a new target or later gesture.
P2 massage queries are serialized independently of release and fenced to the
same session. P1 never sends the dead massage-query branch.

#### Notifications

P1 consumes E7 FE, ED FE and F4 FE timer records at offsets 8, 14 and 19.
FF means off; otherwise the unsigned code is multiplied by ten, preserving the
source comparison with the current displayed minutes. F4 fragments use a
bounded, consumed buffer that resets with each connection. P1 ED 80 alarm
records use raw signed hour/minute and wake 11/13 for A/B. P2 timer byte 4 is
signed: positive values select 10, values above 2 select 20, and above 4 select
30 minutes. P2 alarm records use BCD time, wake 02/03 and enabled byte 9.

The integration rejects truncated, overflowing and invalid time/BCD records,
without inventing incoming checksum or ACK validation. Old callbacks and
fragments cannot publish after reconnect. Fallback ignores notifications.
Only massage minutes and bed alarm time, wake and enabled state are telemetry.
There is no motor-position, light, wave or intensity feedback. One observed
alarm does not show the bed's complete alarm capacity.

#### Services

`set_alarm` accepts `enabled`, minute-precision `time` when enabling,
and `wake_mode` of `none`, `memory_1` or `memory_2`. Every target is validated
and admitted before the first requested write, so STOP on a later target wins.
It sets a daily bed alarm, with fixed day FF. P1 clock fields use year since
1900 and zero-based month; P2 uses BCD year since 2000, one-based month and
Sunday-zero weekday. Disable clears the alarm fields. The refresh-alarm button
and the `adjustable_bed.sync_clock` action expose the other bed-local actions. No read-modify-write
uses default or stale observations. Android tone and phone scheduling are
outside this integration.

#### Evidence

Based on `com.ore.bedding.symphony` 1.1.0 (14).
All five models and fifteen dispatch outcomes are implemented; physical checks still need testing by owners. Its frames and crafted parser cases live in
`tests/fixtures/symphony_sleep/vectors.json`.


### BetterLiving2

**App:** [BetterLiving](https://play.google.com/store/apps/details?id=com.ore.betterliving2)
1.3.0 (16), `com.ore.betterliving2`

**Status:** Not yet tested (built from the app, all three control boxes)

#### Setup

Choose **BetterLiving / BetterLiving2 app**, then **P1 control box**, **P2 control
box** or **P3 control box** and **2 motors: back and feet** or **3 motors: back, feet and all
sections**, the app's two- or three-motor screen. Reconfigure asks the same
questions. These are independent choices, kept per side when combining two
physical beds.
An unknown route or layout has no offline controls. The names `okin*` and
`smartbed*` are shared scan hints, not a sign that a device uses this app.

The manufacturer read in the Android app can change its wire selector after
GATT binding. HA keeps the explicit route and its endpoint pair coherent.
P1/P2 use separate write and notification services; P3 uses Nordic UART. HA
validates their live properties and prefers write-with-response when supported.
No explicit Android write mode is known.

Only back and feet are known separate axes. The two-motor HF controls and
three-motor ALL controls use distinct words; the latter does not mean a
separately controllable third axis. Two-address native pairing is supported.
There is no one-address side selector, concurrent motor mask or speed
setting.

<!-- generated:keeson-betterliving2 -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

#### Controls

| Control | P1 | P2 | P3 |
|---|---|---|---|
| back up | `E5 FE 16 00 00 00 01 05` | `E6 FE 16 01 00 00 00 00 04` | `05 02 00 00 00 01 00` |
| back down | `E5 FE 16 00 00 00 02 04` | `E6 FE 16 02 00 00 00 00 03` | `05 02 00 00 00 02 00` |
| feet up | `E5 FE 16 00 00 00 04 02` | `E6 FE 16 04 00 00 00 00 01` | `05 02 00 00 00 04 00` |
| feet down | `E5 FE 16 00 00 00 08 FE` | `E6 FE 16 08 00 00 00 00 FD` | `05 02 00 00 00 08 00` |
| 2-motor back and feet up | `E5 FE 16 00 00 00 05 01` | `E6 FE 16 05 00 00 00 00 00` | `05 02 00 00 00 05 00` |
| 2-motor back and feet down | `E5 FE 16 00 00 00 0A FC` | `E6 FE 16 0A 00 00 00 00 FB` | `05 02 00 00 00 0A 00` |
| 3-motor all sections up | `E5 FE 16 00 00 00 10 F6` | `E6 FE 16 10 00 00 00 00 F5` | `05 02 00 00 00 10 00` |
| 3-motor all sections down | `E5 FE 16 00 00 00 20 E6` | `E6 FE 16 20 00 00 00 00 E5` | `05 02 00 00 00 20 00` |
| STOP | `E5 FE 16 00 00 00 00 06` | `E6 FE 16 00 00 00 00 00 05` | `05 02 00 00 00 00 00` |

| Preset | P1 | P2 | P3 |
|---|---|---|---|
| zero_g | `E5 FE 16 01 00 00 01 04` | `E6 FE 16 00 10 00 00 00 F5` | `05 02 00 00 10 00 00` |
| flat | `E5 FE 16 01 00 00 02 03` | `E6 FE 16 00 00 00 08 00 FD` | `05 02 08 00 00 00 00` |
| memory_1 | `E5 FE 16 01 00 00 08 FD` | `E6 FE 16 00 00 01 00 00 04` | `05 02 00 01 00 00 00` |
| memory_2 | `E5 FE 16 01 00 00 09 FC` | `E6 FE 16 00 00 04 00 00 01` | `05 02 00 04 00 00 00` |

| Program | P1 | P2 | P3 |
|---|---|---|---|
| zero_g | `E5 FE 16 20 00 00 01 E5` | `E6 FE 16 00 10 00 00 00 F5` | `05 02 00 00 10 00 00` |
| memory_1 | `E5 FE 16 20 00 00 08 DE` | `E6 FE 16 00 00 01 00 00 04` | `05 02 00 01 00 00 00` |
| memory_2 | `E5 FE 16 20 00 00 09 DD` | `E6 FE 16 00 00 04 00 00 01` | `05 02 00 04 00 00 00` |

| P1 absolute control | Values | Word base |
|---|---|---|
| head | 0..3 | `0x10000010` |
| feet | 0..3 | `0x11000010` |
| wave | 0..3 | `0x10000020` |
| Timer input | -1, 0, 1, 2 | `0x10000030` |
| Light | off / on | `0x31000000` / `0x31000001` |
| Second same preset tap | stop active preset | `0x01000000` |

| Step control | P2 | P3 |
|---|---|---|
| toggle | `E6 FE 16 00 01 00 00 00 04` | `05 02 00 00 01 00 00` |
| timer | `E6 FE 16 00 02 00 00 00 03` | `05 02 00 00 02 00 00` |
| feet_up | `E6 FE 16 00 04 00 00 00 01` | `05 02 00 00 04 00 00` |
| head_up | `E6 FE 16 00 08 00 00 00 FD` | `05 02 00 00 08 00 00` |
| feet_down | `E6 FE 16 00 00 00 01 00 04` | `05 02 01 00 00 00 00` |
| head_down | `E6 FE 16 00 00 80 00 00 85` | `05 02 00 80 00 00 00` |
| wave | `E6 FE 16 00 00 00 10 00 F5` | `05 02 10 00 00 00 00` |
| light | `E6 FE 16 00 00 02 00 00 03` | `05 02 00 02 00 00 00` |

| Wake action | P1 | P2 | P3 |
|---|---|---|---|
| memory_1 | 8 | 17 | 5 |
| memory_2 | 9 | 19 | 6 |
| massage | 15 | 9 | 8 |

| Role | P1 | P2 | P3 |
|---|---|---|---|
| Write service | `0000ffe5-0000-1000-8000-00805f9b34fb` | `0000ffe5-0000-1000-8000-00805f9b34fb` | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` |
| Write | `0000ffe9-0000-1000-8000-00805f9b34fb` | `0000ffe9-0000-1000-8000-00805f9b34fb` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` |
| Notify service | `0000ffe0-0000-1000-8000-00805f9b34fb` | `0000ffe0-0000-1000-8000-00805f9b34fb` | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` |
| Notify | `0000ffe4-0000-1000-8000-00805f9b34fb` | `0000ffe4-0000-1000-8000-00805f9b34fb` | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` |

#### Timing

| Operation | Schedule |
|---|---|
| 2 motors: back and feet | refresh every 100 ms |
| 3 motors: back, feet and all sections | refresh every 200 ms |
| Movement cleanup | 2 zero words, 100 ms apart |
| Recall | one key, owned zero release after 100 ms |
| Program P1 | 6000 ms, every 5000 ms |
| Program P2 | 6000 ms, every 100 ms |
| Program P3 | 6000 ms, every 100 ms |
| P1 zone pairs | two writes per zone; 100 ms between pairs |
| P3 massage follow-up | query at +150 ms |
| Set/cancel alarm | 2 immediate writes, sync at +100 ms, query at +400 ms |
| First connection | subscribe, time sync, query at +300 ms |
| Reconnect | subscribe, time sync, immediate sequential alarm read |
<!-- /generated -->

#### Notifications

Massage feedback exists on P2/P3. Their signed fields and raw timer indicators
are retained, with length guards. A recognizable alarm response goes to the
alarm consumer, preventing it from being interpreted as massage. Other
headerless massage responses are consumed only in the massage-query context.
No position feedback, incoming checksum, command ACK or fragment accumulator is
known.

The alarm sensor represents the app's selection, not physical confirmation.
P1's zero or FF week is stateful: a selected switch keeps its prior state;
an unselected switch restores independently saved actions and time. It never
means unconditionally disabled. The separate startup preference restoration
uses massage, then memory A, then memory B precedence. Raw P1 boundary values
24 hours and 60 minutes do not become invented valid HA times.

P2/P3 alarm callbacks attempt zero STOP before parsing, even for a truncated
record with a recognized prefix. HA binds that cleanup to its captured session
and operation, drains movement release first, coalesces pending notifications
to the latest state and rejects stale notifications. It cannot stop a later
operation or a reconnected bed.

#### Services

`set_alarm` takes `enabled`, minute-precision `time`, weekday names,
and `wake_action`: `memory_1`, `memory_2` or `massage`.
An empty day list chooses the strictly next occurrence. P1 masks its massage
field with 0x11; P3 compares the signed -128 sentinel before truncation.

`betterliving2_massage` sets explicit P1 `head` and `feet` levels from 0 to 3,
including zero to stop either zone. P1 exposes head/foot intensity and wave
numbers. P2/P3 expose named step/toggle actions
and head/foot intensity state. Both services accept native child
device targets and optional `side`, reject conflicts and validate every target
before the first change.

`betterliving2_diagnostic_action` replaces the ordinary status-refresh buttons.
Its fixed `action` choices are `refresh_alarm` and `refresh_massage` (P2/P3 only).
These call the existing query methods with the same owner, STOP and session checks.
The four raw P1 timer inputs are in the codec; their physical duration is
unknown, so they have no Home Assistant action. There is no
arbitrary packet action. The **Set bed clock** action
([`sync_clock`](../SERVICES.md#sync_clock)) sets the clock, as the connection
startup does.

Alarm selection/preferences are diagnostic data, not an alarm-state entity.
On P2 and P3, the head and foot massage levels the bed reports are dashboard
sensors in the card's massage section. Wave/timer response settings are
diagnostic sensors disabled by default and hidden from the card. Their values and the alarm details are included in
diagnostics/support bundles. Kept motion, preset, memory, lighting and massage
controls retain their existing entity identities.

The shared preset and memory actions expose Flat, Zero Gravity and two memories;
Zero Gravity and the memories can be programmed. Finite elapsed deadlines, captured
session writes and drained cleanup replace the Android app's shared untagged
timer and unowned delayed recall STOP. Ending refresh alone is not known to be a
physical STOP. Renewable holds are restricted to the six named movement
controls; they do not assert renewable generic timed movement.

#### Evidence

Based on BetterLiving2 1.3.0 (`com.ore.betterliving2`). Hardware is not yet
tested.

### アシステック / Yamada

**App:** [アシステック](https://play.google.com/store/apps/details?id=com.okin.yamada)
1.0.1 (6), `com.okin.yamada`

**Status:** Not yet tested (P1 and P2)

#### Setup

1. Choose **アシステック / ASSISTEC / Yamada app**.
2. Choose P1 or P2, the version the app connects with. The bed's name cannot
   tell them apart.

Both versions have two motors, no massage and no position reading. On a bed with
two receivers, choose the version for each side.

Choose **アシステック / ASSISTEC / Yamada app** and explicitly select **P1 control
box** or **P2 control box**. Setup, Configure and restored entries retain this choice independently
for each side of a two-address pair. There is no single-address side selector.

The app scans names starting with `okin-ble` or `smartbed`, ignoring case.
These shared names suggest the app without identifying it. `ASSISTEC` is a display
replacement, not a scan prefix. There are no other product aliases.
The app selects P2 when bytes 0/1/2/4 of the first manufacturer map **value** are
59/41/4D/02 (hex). Company ID and byte 3 do not participate. Android concatenates
manufacturer AD segments differently from HA's parsed map; do not concatenate
arbitrary HA records or infer a version from shared UUIDs. Use the explicit choice
when the original selector cannot be reconstructed.

Both GATT roles are required. Service and characteristic OR sets are independent;
the last matching write wins, and every matching notification role is subscribed.
HA requires the selected write role to support write with response, and each
notification role to support notify or indicate. No read, authentication, PIN,
bond, heartbeat or position query is added.

<!-- generated:keeson-yamada -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

#### Controls

| Control | P1 | P2 |
|---|---|---|
| head_up | `E6 FE 16 01 00 00 00 00 04` | `05 02 00 00 00 01 00` |
| head_down | `E6 FE 16 02 00 00 00 00 03` | `05 02 00 00 00 02 00` |
| foot_up | `E6 FE 16 04 00 00 00 00 01` | `05 02 00 00 00 04 00` |
| foot_down | `E6 FE 16 08 00 00 00 00 FD` | `05 02 00 00 00 08 00` |
| anti_snore | `E6 FE 16 00 80 00 00 00 85` | `05 02 00 00 80 00 00` |
| zero | `E6 FE 16 00 10 00 00 00 F5` | `05 02 00 00 10 00 00` |
| memory_m2 | `E6 FE 16 00 20 00 00 00 E5` | `05 02 00 00 20 00 00` |
| tvpc | `E6 FE 16 00 40 00 00 00 C5` | `05 02 00 00 40 00 00` |
| light | `E6 FE 16 00 00 02 00 00 03` | `05 02 00 02 00 00 00` |
| flat | `E6 FE 16 00 00 00 08 00 FD` | `05 02 08 00 00 00 00` |
| stop | `E6 FE 16 00 00 00 00 00 05` | `05 02 00 00 00 00 00` |

| Alarm position | P1 key | P2 key |
|---|---|---|
| memory_1 | 14 | 2 |
| anti_snore | 16 | 4 |
| zero_g | 13 | 1 |
| tv | 15 | 3 |
| flat | 28 | 9 |

| Role | Service OR set | Characteristic OR set |
|---|---|---|
| Write | `0000ffe5-0000-1000-8000-00805f9b34fb`, `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `0000ffe9-0000-1000-8000-00805f9b34fb`, `6e400002-b5a3-f393-e0a9-e50e24dcca9e` |
| Notify | `0000ffe0-0000-1000-8000-00805f9b34fb`, `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `0000ffe4-0000-1000-8000-00805f9b34fb`, `6e400003-b5a3-f393-e0a9-e50e24dcca9e` |

| Example | P1 | P2 |
|---|---|---|
| Clock: 2026-11-12 06:30:45 | `E7 80 01 7E 0A 0C 06 1E 2D B2` | `07 04 7E 0A 0C 04 06 1E 2D` |
| One query round | +0 ms: `E1 80 03 9B` | +0 ms: `00 C0`; +300 ms: `00 D0` |

#### Timing

| Operation | Policy |
|---|---|
| Ordinary configured pulses | Configured count × interval, bounded by elapsed time; defaults in Configuration |
| App holds and renewable card leases | Immediate, then every 300 ms until duration/release/expiry |
| Release/cancel | Captured zero word at +100/+400 ms, fresh cancellation event |
| Explicit STOP | Zero word at +100 ms; consumes this command's completed cleanup when preempting |
| Personal M gesture | Same recall word held 5200 ms; local UI confirmation only |
| Refresh alarms | +0 ms round, +300 ms round, +600 ms round |
| After alarm write | One manager round after 300 ms |
| Notification retry | Once after 1000 ms |
| Clock | Once on connection, overlapping asynchronous notification setup |
<!-- /generated -->

M is one personal-position gesture, exposed as Memory 1. Its short and held
forms send identical bytes. The app's save toast timer is not a SAVE opcode,
firmware threshold or completion acknowledgement. HA's save action performs the
held gesture; external users must confirm its physical effect. Lighting exposes
only the app's single light action, with no assumed on/off state or brightness.

P1 alarm writes use the shared checked table encoder with two four-byte records
(hour, minute, weekday, position) and four zero bytes. P2 writes one slot with
weekday, position, hour, minute, zero, enabled and zero. P2 clock fields are raw
year minus 1900, zero-based month and Sunday-zero weekday, never BCD.

The refresh button performs the page-entry burst. P1 sends three requests;
P2 sends C0 at 0/300/600 ms and D0 at 300/600/900 ms. The app gives equal
deadlines no order. A save schedules only one delayed round. HA keeps all
queries and release frames inside the captured session and command lane.

#### Notifications

P1 reads both slots at offsets 3–6 and 7–10 of ED 80 03; enabled means the
weekday is neither 0 nor 128. P2 consumes A5 0C/0D 0E, with weekday at 4,
position at 5, hour/minute at 6/7 and enabled marker at 9. Marker 0 or 128 means
disabled. A disabled record retains a previously observed weekday, or remains
unknown when none was observed on this connection. E7 and A5 0E have no consumed
hardware state. Trailing bytes do not imply another independently parsed frame.

The app recognizes both prefix families globally before choosing its current
version callback. Its P1 pending-confirmation check precedes the local header
check, and truncated input may throw or partially mutate cached alarms. HA
intentionally rejects short, wrong-profile, invalid-time and stale-session
messages safely, with no partial commits. These are integration safety guards,
not claims about Android behavior. Notification buffers and alarm observations
are per session and cleared on reconnect; no old observation authorizes a write.

#### Services

- `set_alarm`: explicit slot 1 or 2, enabled state, local time to minute
  precision, weekday mask and preset. Refresh alarms on each current connection
  first. P1 also requires the other slot's observed record so it can preserve it.
  It never allocates a first-free slot or infers a complete inventory.
- P1 rejects a queued save if its observed table has changed. A table write
  invalidates that snapshot until the written fields are observed; delayed
  older responses cannot authorize another table edit. Refresh or reconnect
  before retrying if the written table has not been observed.
- The weekday mask uses Sunday bit 0 through Saturday bit 6; 129–255 passes
  unchanged for recurring days. Values 0–128 choose the next occurrence of the
  local time, adding exactly 24 elapsed hours when that time has passed.
- Disabling P1 zeros the selected weekday and position while preserving its
  supplied time and the observed other slot. P2 zeros weekday/enabled and keeps
  the supplied position and time. Supply the observed values to preserve them.
- The two alarm sensors report observations only, with hour, minute, weekday
  and raw position attributes. Successful writes do not publish invented state.
- `timed_move`, `hold_control`, presets, memory, lighting and STOP use the
  coordinator's ordinary admission and cancellation paths. A release belongs
  to its captured client, address and frame, including under repeated cancellation.

#### Evidence

Based on `com.okin.yamada` 1.0.1 (6): the existing Keeson and Okin N-frame
codecs reproduce all 35 of its packets and all four valid parser fixtures. Not
yet tested on hardware.

### Ormatek TechnoSmart

**Status:** Not yet tested

#### Setup and models

Choose **OrmatekTechnoSmart app**, then **Techno Smart New** or **Techno Smart Lite**.
Choose **Bluetooth name starts with Okin** for the app's `okin` Bluetooth-name
prefix and **Bluetooth name starts with SmartBed** for its `smartbed` prefix
(case-insensitive). These are explicit app choices;
shared names and services do not select this app automatically. New and Lite
are independent of the Bluetooth services and packet format. These selector
combinations are not a list of confirmed hardware models.

New has head, feet and combined movement, flat, zero gravity, TV, anti-snore,
lounge, one memory recall, a light toggle and massage controls. Lite has head,
feet and combined movement, flat, zero gravity, TV and anti-snore. Neither
layout reports motor positions or has a memory-save command. Lite requires
an explicit alarm wake action; the app's unselectable initial massage choice
is not offered as a Lite wake action.

#### Commands

<!-- generated:keeson-ormatek -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Command | Okin | SmartBed |
|---|---|---|
| stop | `E6 FE 16 00 00 00 00 00 05` | `05 02 00 00 00 00 00` |
| lightSwitch | `E6 FE 16 00 00 02 00 00 03` | `05 02 00 02 00 00 00` |
| headUp | `E6 FE 16 01 00 00 00 00 04` | `05 02 00 00 00 01 00` |
| headDown | `E6 FE 16 02 00 00 00 00 03` | `05 02 00 00 00 02 00` |
| footUp | `E6 FE 16 04 00 00 00 00 01` | `05 02 00 00 00 04 00` |
| footDown | `E6 FE 16 08 00 00 00 00 FD` | `05 02 00 00 00 08 00` |
| hfUp | `E6 FE 16 05 00 00 00 00 00` | `05 02 00 00 00 05 00` |
| hfDown | `E6 FE 16 0A 00 00 00 00 FB` | `05 02 00 00 00 0A 00` |
| memoryAntiSnore | `E6 FE 16 00 80 00 00 00 85` | `05 02 00 00 80 00 00` |
| memoryLounge | `E6 FE 16 00 20 00 00 00 E5` | `05 02 00 00 20 00 00` |
| memory1M5 | `E6 FE 16 00 00 01 00 00 04` | `05 02 00 01 00 00 00` |
| memoryTvpc | `E6 FE 16 00 40 00 00 00 C5` | `05 02 00 00 40 00 00` |
| memoryZero | `E6 FE 16 00 10 00 00 00 F5` | `05 02 00 00 10 00 00` |
| memoryFlat | `E6 FE 16 00 00 00 08 00 FD` | `05 02 08 00 00 00 00` |
| massageSwitch | `E6 FE 16 00 01 00 00 00 04` | `05 02 00 00 01 00 00` |
| massageTimeSwitch | `E6 FE 16 00 02 00 00 00 03` | `05 02 00 00 02 00 00` |
| strengthHeadUp | `E6 FE 16 00 08 00 00 00 FD` | `05 02 00 00 08 00 00` |
| strengthFootUp | `E6 FE 16 00 04 00 00 00 01` | `05 02 00 00 04 00 00` |
| massageWaveSwitch | `E6 FE 16 00 00 00 10 00 F5` | `05 02 10 00 00 00 00` |

Both formats write without response. The last supported write service selects its
complete write/notify tuple: FFE5/FFE9 with FFE0/FFE4, or Nordic UART 6E400001
with 6E400002 write and 6E400003 notify. This does not select a layout or packet
format.

Clock sync uses local time. Okin carries year minus 1900 and zero-based month in
the checked E7 80 01 record. SmartBed carries year minus 2000, month, day, weekday
(Monday 1 through Sunday 7), hour, minute and second in the 07 04 record.

| Layout | Alarm wake choices |
|---|---|
| Techno Smart New | massage, memory_1, flat |
| Techno Smart Lite | zero_g, tv |

The shared set_alarm action configures one daily alarm, slot one only. Okin
encodes both record positions with the second disabled; it then queries
immediately and after 100 and 200 ms. SmartBed writes slot one and queries 00 C0
and 00 D0 after 100 ms. Weekly masks and the second-slot builder are not
selectable controls.
<!-- /generated -->

#### Notifications and state

Okin massage replies start `ED FE`; SmartBed replies start `A5 0B`. The app
reads timer, head strength, foot strength and wave at format-specific offsets.
The massage indicator and valid strengths are available in Home Assistant;
timer categories and out-of-range fields remain in diagnostics. Strength
controls cycle, with no absolute intensity setter.

Alarm replies start `ED 80` or `A5 0C` / `A5 0D`. Enabled is true only for the
app's parsed value 1. A disabled reply preserves the last known time. The app
ignores the reply's slot, week and wake type. Home Assistant retains the decoded
slot and publishes only slot one's alarm state. A reply does not confirm the
selected wake action. No notification is a command acknowledgement.

Twenty-byte chunks are retained for the next eligible chunk; short chunks do
not consume them, a second twenty-byte chunk replaces them, and duplicate
current chunks are ignored. Prefix selection uses the current chunk. These
buffers belong to one connection and are cleared when it ends.

#### Timing and release

Held movement, light and strength commands start immediately and refresh every
200 ms. Missed refresh ticks are skipped after slow writes. Motor release waits
100 ms before STOP, then repeats STOP after 200 ms.
Most presets send on release followed by the same 100 ms delay; memory 1 starts
on press. The app's six-second memory toast does not prove saving.

Massage release sends STOP immediately, with its 200 ms repeat. Timer and wave
use the massage-toggle frame while the current timer is zero. Massage actions
query current state before choosing a timer or wave command after reconnect,
and refuse to guess if no feedback arrives. They
query state after the UI's 200 ms delay plus the helper's 100 ms delay, nominally
300 ms from press. Home Assistant retains its required STOP repeat and captured
command ownership while querying. A delayed operation cannot stop a newer
command or move to a replacement connection.

#### Limitations

There is no native side byte, simultaneous command composition, motor-position
feedback, PIN exchange or app authentication. Two physical addresses use Home
Assistant's independent paired-bed routing. Notification and write properties
must actually be present; optimistic app readiness is not treated as proof.
Physical effects, firmware compatibility and stopping on disconnect still need
testing on hardware. Wi-Fi, cloud, account and firmware provisioning are outside this
integration.

#### Analysis provenance

Based on OrmatekTechnoSmart 1.2.0 (`com.okin.ormatek`).

## Somos / SomosBeds

**App:** Somos 1.0.0 (code 1), `cn.com.somos`

**Status:** Not yet tested

### Configuration

1. Choose **Somos / SomosBeds app**.
2. Choose the product the Somos app shows: Signature (A), Elite (B), Ultra (C),
   Signature Split Head (D) or Ultra Split Head (E). Setup never guesses it; use
   **Reconfigure** to change it later.

The product sets the motors, massage buttons and the 300 ms refresh. Names
containing `base-i5`, `KSBT03C3` or `KSBT03CR` suggest Somos but do not identify
the product. No QR code, phone ID or network setup is needed. Two receivers can
be combined, each with its own product. D and E do not support Left and Right
controls on one receiver.

### Capabilities

A/C expose head and feet. B additionally exposes the app's lumbar/tilt control.
D/E expose **Lift 1**, **Lift 2** and **Lift 3** (motors `axis_1`–`axis_3` in
`timed_move`, and `axis_1_up`/`axis_1_down` and so on in `hold_control`). These are neutral app control identities: physical
anatomy and side still need testing. Both first rockers use head artwork; the third
uses separate leg-arrow artwork. Neither the product name nor a Java field name
assigns an axis to a side or body part.

Native covers, bounded moves and renewable held controls use only the selected
product's axes. Preset and memory buttons are single writes; memory programming
is unavailable. D's star/M favorite is memory button 1. B's `iv_light` is memory
button 2, while B's bed light is `v_snore`. The **Head massage**, **Foot massage**,
**Cycle massage timer** and **Light** buttons are opaque app actions, with no
guessed levels, timer values, cycle order or light state. The **Massage timer**
sensor reports the app's 10/20/30-minute indicator and a remaining seconds
attribute. The bed reports no position or light state.

### Commands and timing

<!-- generated:keeson-somos -->
| Product | Control | Frame | Timing |
|---|---|---|---|
| Signature (A) | head up | `E6 FE 16 01 00 00 00 00 04` | held, 30 ms then 300 ms |
| Signature (A) | head down | `E6 FE 16 02 00 00 00 00 03` | held, 30 ms then 300 ms |
| Signature (A) | feet up | `E6 FE 16 04 00 00 00 00 01` | held, 30 ms then 300 ms |
| Signature (A) | feet down | `E6 FE 16 08 00 00 00 00 FD` | held, 30 ms then 300 ms |
| Signature (A) | flat | `E6 FE 16 00 00 00 08 00 FD` | once |
| Signature (A) | zero_g | `E6 FE 16 00 10 00 00 00 F5` | once |
| Elite (B) | head up | `04 02 00 00 00 01` | held, 0 ms then 300 ms |
| Elite (B) | head down | `04 02 00 00 00 02` | held, 0 ms then 300 ms |
| Elite (B) | feet up | `04 02 00 00 00 04` | held, 0 ms then 300 ms |
| Elite (B) | feet down | `04 02 00 00 00 08` | held, 0 ms then 300 ms |
| Elite (B) | lumbar_tilt up | `04 02 00 00 00 40` | held, 0 ms then 300 ms |
| Elite (B) | lumbar_tilt down | `04 02 00 00 00 80` | held, 0 ms then 300 ms |
| Elite (B) | flat | `04 02 08 00 00 00` | once |
| Elite (B) | zero_g | `04 02 00 00 10 00` | once |
| Elite (B) | anti_snore | `04 02 00 00 80 00` | once |
| Elite (B) | memory 1 | `04 02 00 01 00 00` | once |
| Elite (B) | memory 2 | `04 02 00 00 20 00` | once |
| Elite (B) | memory 3 | `04 02 00 00 40 00` | once |
| Elite (B) | head_massage | `04 02 00 00 08 00` | once |
| Elite (B) | foot_massage | `04 02 00 00 04 00` | once |
| Elite (B) | massage_timer_cycle | `04 02 00 00 02 00` | once |
| Elite (B) | light | `04 02 00 02 00 00` | once |
| Elite (B) | status query | `00 B0` | after 2 s, then 1 s |
| Ultra (C) | head up | `E6 FE 16 01 00 00 00 00 04` | held, 30 ms then 300 ms |
| Ultra (C) | head down | `E6 FE 16 02 00 00 00 00 03` | held, 30 ms then 300 ms |
| Ultra (C) | feet up | `E6 FE 16 04 00 00 00 00 01` | held, 30 ms then 300 ms |
| Ultra (C) | feet down | `E6 FE 16 08 00 00 00 00 FD` | held, 30 ms then 300 ms |
| Ultra (C) | flat | `E6 FE 16 00 00 00 08 00 FD` | once |
| Ultra (C) | zero_g | `E6 FE 16 00 10 00 00 00 F5` | once |
| Ultra (C) | anti_snore | `E6 FE 16 00 80 00 00 00 85` | once |
| Ultra (C) | memory 1 | `E6 FE 16 00 00 01 00 00 04` | once |
| Ultra (C) | memory 2 | `E6 FE 16 00 40 00 00 00 C5` | once |
| Ultra (C) | head_massage | `E6 FE 16 00 08 00 00 00 FD` | once |
| Ultra (C) | foot_massage | `E6 FE 16 00 04 00 00 00 01` | once |
| Ultra (C) | massage_timer_cycle | `E6 FE 16 00 02 00 00 00 03` | once |
| Ultra (C) | light | `E6 FE 16 00 00 02 00 00 03` | once |
| Ultra (C) | status query | `E6 FE 16 00 00 00 00 00 05` | after 2 s, then 1 s |
| Signature Split Head (D) | axis_1 up | `05 02 00 00 00 01 00` | held, 0 ms then 300 ms |
| Signature Split Head (D) | axis_1 down | `05 02 00 00 00 02 00` | held, 0 ms then 300 ms |
| Signature Split Head (D) | axis_2 up | `05 02 00 00 00 04 00` | held, 0 ms then 300 ms |
| Signature Split Head (D) | axis_2 down | `05 02 00 00 00 08 00` | held, 0 ms then 300 ms |
| Signature Split Head (D) | axis_3 up | `05 02 00 00 00 10 00` | held, 0 ms then 300 ms |
| Signature Split Head (D) | axis_3 down | `05 02 00 00 00 20 00` | held, 0 ms then 300 ms |
| Signature Split Head (D) | flat | `05 02 08 00 00 00 00` | once |
| Signature Split Head (D) | zero_g | `05 02 00 00 10 00 00` | once |
| Signature Split Head (D) | favorite M | `05 02 00 01 00 00 00` | once |
| Ultra Split Head (E) | axis_1 up | `05 02 00 00 00 01 00` | held, 0 ms then 300 ms |
| Ultra Split Head (E) | axis_1 down | `05 02 00 00 00 02 00` | held, 0 ms then 300 ms |
| Ultra Split Head (E) | axis_2 up | `05 02 00 00 00 04 00` | held, 0 ms then 300 ms |
| Ultra Split Head (E) | axis_2 down | `05 02 00 00 00 08 00` | held, 0 ms then 300 ms |
| Ultra Split Head (E) | axis_3 up | `05 02 00 00 00 10 00` | held, 0 ms then 300 ms |
| Ultra Split Head (E) | axis_3 down | `05 02 00 00 00 20 00` | held, 0 ms then 300 ms |
| Ultra Split Head (E) | flat | `05 02 08 00 00 00 00` | once |
| Ultra Split Head (E) | zero_g | `05 02 00 00 10 00 00` | once |
| Ultra Split Head (E) | anti_snore | `05 02 00 00 80 00 00` | once |
| Ultra Split Head (E) | head_massage | `05 02 00 00 08 00 00` | once |
| Ultra Split Head (E) | foot_massage | `05 02 00 00 04 00 00` | once |
| Ultra Split Head (E) | massage_timer_cycle | `05 02 00 00 02 00 00` | once |
| Ultra Split Head (E) | light | `05 02 00 02 00 00 00` | once |
| Ultra Split Head (E) | status query | `01 B0 00` | after 2 s, then 1 s |
<!-- /generated -->

Movement refreshes every 300 ms. A/C begin after 30 ms; B/D/E begin immediately.
Release, cancellation, lease expiry and STOP end refresh, sending **no packet**.
C's all-zero query is delayed by 2 seconds and is not a release command.
Hardware watchdog timing still needs testing. One-shot presets cannot be
physically stopped by an added packet.

B/C/E poll after 2 seconds, then every second while connected and idle. Movement
suspends polling and release restarts its initial delay. B's flat, head/foot
massage and timer actions additionally issue three queries 300 ms apart.
HA serializes these writes, binds them to their original receiver and clears
observations on disconnect. Polling never reconnects or extends the idle timer.

### Transport and responses

A/C require write FFE9 on FFE5 and notify FFE4 on FFE0. B/D/E require Nordic UART
write `6e400002-b5a3-f393-e0a9-e50e24dcca9e` and notify
`6e400003-b5a3-f393-e0a9-e50e24dcca9e` on service
`6e400001-b5a3-f393-e0a9-e50e24dcca9e`. There is no GATT fallback or authentication
handshake. HA negotiates Bluetooth MTU through its transport; the app requests
243, which none of these at-most-nine-byte frames requires. Notify subscriptions
use CCCD notifications, not indications. Live characteristic properties select
the supported write mode; hardware write properties still need testing.

B reads seconds big-endian at bytes 3–4, E at bytes 2–3. C reads signed little-endian
32-bit hundredths at bytes 9–12, dividing by 100 with truncation toward zero.
All three truncate seconds to minutes before choosing their indicator:
1–10 maps to 10, 11–20 to 20, above 20 to 30, otherwise 0. HA discards short
notifications rather than reproducing the app's indexing exception; it adds
no guessed header, checksum, position or acknowledgment interpretation.

### Actions

`adjustable_bed.somos_action` exposes each available preset, memory, massage,
light button and status query. It validates all selected targets before sending
anything and supports the normal paired `side` field. `hold_control` accepts
`head_up/down`, `feet_up/down`, B's `lumbar_tilt_up/down`, or D/E's
`axis_1_up/down`, `axis_2_up/down`, `axis_3_up/down`, as applicable.

### Analysis provenance

Based on Somos 1.0.0 (`cn.com.somos`).

### Leva Sleep

**App:** [Leva Sleep](https://play.google.com/store/apps/details?id=com.ore.LevaSleep) 1.0.2 (3), `com.ore.LevaSleep`

**Status:** Not yet tested

#### Setup

1. Choose **Leva Sleep app · Keeson** in manual setup.
2. Choose the 2-, 3- or 4-motor screen that matches your Leva Sleep app.

The Android app lists Bluetooth names containing `OKIN` or `COMFORT`. These
names are shared by other beds, so select the profile by app name. Beds using
[Leva Bed Remote (A62)](okin-nframe.md#leva-bed-remote) have a separate setup choice. Home Assistant
keeps the layout and the last live route with each physical receiver.

The first connection checks the live GATT table for FFF0. P1 has FFF0 and P2
does not. The link needs FFE9 and FFE4 anywhere in the GATT table. The last
FFE9 is the write target. Home Assistant uses the live write properties and
subscribes to matching FFE4 characteristics through its Bluetooth stack.
There is no startup command or app PIN.

If a receiver reports a different route later, Home Assistant finishes the
current operation before updating its controls. With **Always connected**,
the controls update on the existing Bluetooth connection.

#### Controls

Both routes move the back and feet. The 2-motor layout adds a combined
control, the 3-motor layout adds the head, and the 4-motor layout adds waist
and lumbar. Motor position feedback is unavailable.

P1 recalls and programs Flat, Zero Gravity, M1 and M2. A second press of the
same recalled preset sends STOP. P1 also provides separate head, foot and
wave massage levels, massage start and stop, three timer durations, and
light on and off with assumed state. P2 holds Flat, Zero Gravity, M1 and M2
and provides held massage toggle, timer, wave, head and foot controls. P2 has
a light toggle and no save control.

<!-- generated:keeson-leva-sleep -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Selector | Write | Notify |
|---|---|---|
| 0000fff0-0000-1000-8000-00805f9b34fb present: P1, absent: P2 | 0000ffe9-0000-1000-8000-00805f9b34fb | 0000ffe4-0000-1000-8000-00805f9b34fb |

| Route | Layout motors | Axis | Up | Down |
|---|---|---|---|---|
| P1 | 2 | back | `E5 FE 16 00 00 00 01 05` | `E5 FE 16 00 00 00 02 04` |
| P1 | 2 | feet | `E5 FE 16 00 00 00 04 02` | `E5 FE 16 00 00 00 08 FE` |
| P1 | 2 | both | `E5 FE 16 00 00 00 10 F6` | `E5 FE 16 00 00 00 20 E6` |
| P1 | 3 | back | `E5 FE 16 00 00 00 01 05` | `E5 FE 16 00 00 00 02 04` |
| P1 | 3 | feet | `E5 FE 16 00 00 00 04 02` | `E5 FE 16 00 00 00 08 FE` |
| P1 | 3 | head | `E5 FE 16 00 00 00 10 F6` | `E5 FE 16 00 00 00 20 E6` |
| P1 | 4 | back | `E5 FE 16 00 00 00 01 05` | `E5 FE 16 00 00 00 02 04` |
| P1 | 4 | feet | `E5 FE 16 00 00 00 04 02` | `E5 FE 16 00 00 00 08 FE` |
| P1 | 4 | waist | `E5 FE 16 00 00 00 10 F6` | `E5 FE 16 00 00 00 20 E6` |
| P1 | 4 | lumbar | `E5 FE 16 00 00 00 40 C6` | `E5 FE 16 00 00 00 80 86` |
| P2 | 2 | back | `E6 FE 16 01 00 00 00 00 04` | `E6 FE 16 02 00 00 00 00 03` |
| P2 | 2 | feet | `E6 FE 16 04 00 00 00 00 01` | `E6 FE 16 08 00 00 00 00 FD` |
| P2 | 2 | both | `E6 FE 16 05 00 00 00 00 00` | `E6 FE 16 0A 00 00 00 00 FB` |
| P2 | 3 | back | `E6 FE 16 01 00 00 00 00 04` | `E6 FE 16 02 00 00 00 00 03` |
| P2 | 3 | feet | `E6 FE 16 04 00 00 00 00 01` | `E6 FE 16 08 00 00 00 00 FD` |
| P2 | 3 | head | `E6 FE 16 10 00 00 00 00 F5` | `E6 FE 16 20 00 00 00 00 E5` |
| P2 | 4 | back | `E6 FE 16 01 00 00 00 00 04` | `E6 FE 16 02 00 00 00 00 03` |
| P2 | 4 | feet | `E6 FE 16 04 00 00 00 00 01` | `E6 FE 16 08 00 00 00 00 FD` |
| P2 | 4 | waist | `E6 FE 16 10 00 00 00 00 F5` | `E6 FE 16 20 00 00 00 00 E5` |
| P2 | 4 | lumbar | `E6 FE 16 40 00 00 00 00 C5` | `E6 FE 16 80 00 00 00 00 85` |

| Route | Preset | Recall | Program |
|---|---|---|---|
| P1 | memory_1 | `E5 FE 16 01 00 00 08 FD` | `E5 FE 16 20 00 00 08 DE` |
| P1 | memory_2 | `E5 FE 16 01 00 00 09 FC` | `E5 FE 16 20 00 00 09 DD` |
| P1 | zero_g | `E5 FE 16 01 00 00 01 04` | `E5 FE 16 20 00 00 01 E5` |
| P1 | flat | `E5 FE 16 01 00 00 02 03` | `E5 FE 16 20 00 00 02 E4` |
| P2 | flat | `E6 FE 16 00 00 00 08 00 FD` | none |
| P2 | zero_g | `E6 FE 16 00 10 00 00 00 F5` | none |
| P2 | memory_1 | `E6 FE 16 00 00 01 00 00 04` | none |
| P2 | memory_2 | `E6 FE 16 00 00 04 00 00 01` | none |

| Route | Control | Frame / sequence |
|---|---|---|
| P1 | wave level 0 | `E5 FE 16 10 00 00 20 D6` |
| P1 | wave level 1 | `E5 FE 16 10 00 00 21 D5` |
| P1 | wave level 2 | `E5 FE 16 10 00 00 22 D4` |
| P1 | wave level 3 | `E5 FE 16 10 00 00 23 D3` |
| P1 | head level 0 | `E5 FE 16 10 00 00 10 E6` |
| P1 | head level 1 | `E5 FE 16 10 00 00 11 E5` |
| P1 | head level 2 | `E5 FE 16 10 00 00 12 E4` |
| P1 | head level 3 | `E5 FE 16 10 00 00 13 E3` |
| P1 | foot level 0 | `E5 FE 16 11 00 00 10 E5` |
| P1 | foot level 1 | `E5 FE 16 11 00 00 11 E4` |
| P1 | foot level 2 | `E5 FE 16 11 00 00 12 E3` |
| P1 | foot level 3 | `E5 FE 16 11 00 00 13 E2` |
| P1 | timer 10 min | `E5 FE 16 10 00 00 30 C6` |
| P1 | timer 20 min | `E5 FE 16 10 00 00 31 C5` |
| P1 | timer 30 min | `E5 FE 16 10 00 00 32 C4` |
| P1 | light on | `E5 FE 16 31 00 00 01 D4` |
| P1 | light off | `E5 FE 16 31 00 00 00 D5` |
| P2 | light toggle | `E6 FE 16 00 00 02 00 00 03` |
| P2 | held massage head | `E6 FE 16 00 08 00 00 00 FD` |
| P2 | held massage foot | `E6 FE 16 00 04 00 00 00 01` |
| P2 | held massage timer | `E6 FE 16 00 02 00 00 00 03` |
| P2 | held massage toggle | `E6 FE 16 00 01 00 00 00 04` |
| P2 | held massage wave | `E6 FE 16 00 00 00 10 00 F5` |
| P1 | release / STOP | `E5 FE 16 00 00 00 00 06` |
| P2 | release / STOP | `E6 FE 16 00 00 00 00 00 05` |
| P1 | massage start (saved wave/head/foot, default1) | `E5 FE 16 10 00 00 21 D5`; `E5 FE 16 10 00 00 11 E5`; `E5 FE 16 11 00 00 11 E4` |
| P1 | massage stop | `E5 FE 16 10 00 00 10 E6`; `E5 FE 16 11 00 00 10 E5` |

Alarm examples use local2026-11-17 07:06:05, alarm07:30, repeat130.

| Route | Alarm control | Frame |
|---|---|---|
| P1 | query | `E2 FE 16 05 06 07 02 F5` |
| P2 | query | `E2 80 03 00 9A` |
| P2 | clock | `E7 80 01 7E 0A 11 07 06 05 EC` |
| P1 | disable | `EB FE 16 05 06 07 FF FF 02 FF FF FF FF F2` |
| P1 | enable type0 | `EB FE 16 05 06 07 1E 07 02 82 FF FF FF 48` |
| P1 | enable type1 | `EB FE 16 05 06 07 1E 07 02 82 11 11 FF 24` |
| P1 | enable type2 | `EB FE 16 05 06 07 1E 07 02 82 FF FF 08 3F` |
| P1 | enable type3 | `EB FE 16 05 06 07 1E 07 02 82 FF FF 09 3E` |
| P2 | disable | `ED 80 03 00 00 00 00 00 00 00 00 00 00 00 00 8F` |
| P2 | enable type0 | `ED 80 03 07 1E 82 00 00 00 00 00 00 00 00 00 E8` |
| P2 | enable type1 | `ED 80 03 07 1E 82 09 00 00 00 00 00 00 00 00 DF` |
| P2 | enable type2 | `ED 80 03 07 1E 82 11 00 00 00 00 00 00 00 00 D7` |
| P2 | enable type3 | `ED 80 03 07 1E 82 13 00 00 00 00 00 00 00 00 D5` |

| Lifecycle | Timing |
|---|---|
| Held refresh | immediate, then100ms after each write |
| Single, release and clock | 100ms before each write |
| Query | 200ms before write |
| Startup | subscribe only, no initialization/query/control write |
<!-- /generated -->

#### Responses

The **Refresh alarm** button queries the bed. When enabling an alarm with
`adjustable_bed.set_alarm`, choose None, Massage, M1 or M2. Both routes
accept a weekly schedule. On P2, a midnight alarm needs a wake action or a
repeat day because an all-zero record disables the alarm. P2 writes the
local clock before changing the alarm. Both routes query after the change.

The E2 FE query reply preserves the previous mode when the response supplies
neither a recognized memory value nor massage. The ED 80 status publishes all
four fields on the first complete status of a connection and when any field
changes. The signed repeat and action attributes
show the reported values. P2 reports raw action bytes separately from the
outgoing wake choices. The alarm sensor also exposes the reported enabled
state. Massage status exposes the intensity bucket, raw timer and reported
10, 20 or 30 minute selection. Fragment state belongs to the live BLE link.

#### Timing and STOP

Held commands refresh every 100 ms after each write and finish with a delayed
zero-word STOP on the same link. Home Assistant bounds a normal press and
owns the hold lease, cancellation and release. A lost connection retires
pending writes and notifications.

### ORE Ultramatic

**App:** [Ultramatic](https://play.google.com/store/apps/details?id=com.ore.ultramatic) 1.0.5 (9), `com.ore.ultramatic`

**Status:** Not yet tested

#### Setup

1. Choose **Ultramatic app · Keeson**. Setup never picks it automatically.
2. Choose the 2-, 3- or 4-motor screen your bed uses in the app.

The bed's connection decides between the two versions (P1 and P2) by itself.
Massage and light are part of the bed controls, and **Read bed position** stays
off. Configure keeps the layout with its bed side.

Choose **Ultramatic app · Keeson** and the actual 2-, 3- or 4-motor screen.
The layout belongs to each physical receiver in a paired bed. Detection: none;
this app accepts any nonempty device name and supplies no safe advertisement filter.
The live GATT table selects P1 if any FFF0 service exists, otherwise P2. FF20
is not a selection requirement. Both FFE9 and FFE4 must exist; the last instance
of each across all services wins. No PIN, authentication, capability query,
firmware read or motor-position query is used. Route capabilities are
captured after connection, including for offline paired-side entities.

#### Controls

Both routes expose back/feet plus the selected screen's combined, head, waist
or lumbar controls. The waist label uses head/neck artwork in the app; actual
linkage still needs testing. P1 recalls M1/M2/Zero G/Flat with one packet and
stops a repeated tap of the same target. Each can be programmed independently.
P2 holds TV/Anti Snore/Zero G/Flat and offers no programming. Its alarm label ZG
uses a different action from its Anti Snore preset, so the integration preserves
both paths.

P1 exposes explicit head/foot/wave levels, timer, massage start/stop and light
on/off. P2 exposes five held massage buttons and a light toggle. No physical
cycling algorithm, brightness, color or discrete P2 massage-off command is
guessed. Head/foot/wave preferences remain local and optimistic. The P2
buttons are **Head massage**, **Foot massage**, **Massage timer**, **Toggle
massage** and **Massage wave**. The **Massage intensity** sensor carries the
reported raw timer value as an attribute.

<!-- generated:keeson-ore-ultramatic -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Selector | Write | Notify |
|---|---|---|
| 0000fff0-0000-1000-8000-00805f9b34fb present: P1, absent: P2 | 0000ffe9-0000-1000-8000-00805f9b34fb | 0000ffe4-0000-1000-8000-00805f9b34fb |

| Route | Layout motors | Axis | Up | Down |
|---|---|---|---|---|
| P1 | 2 | back | `E5 FE 16 00 00 00 01 05` | `E5 FE 16 00 00 00 02 04` |
| P1 | 2 | feet | `E5 FE 16 00 00 00 04 02` | `E5 FE 16 00 00 00 08 FE` |
| P1 | 2 | both | `E5 FE 16 00 00 00 10 F6` | `E5 FE 16 00 00 00 20 E6` |
| P1 | 3 | back | `E5 FE 16 00 00 00 01 05` | `E5 FE 16 00 00 00 02 04` |
| P1 | 3 | feet | `E5 FE 16 00 00 00 04 02` | `E5 FE 16 00 00 00 08 FE` |
| P1 | 3 | head | `E5 FE 16 00 00 00 10 F6` | `E5 FE 16 00 00 00 20 E6` |
| P1 | 4 | back | `E5 FE 16 00 00 00 01 05` | `E5 FE 16 00 00 00 02 04` |
| P1 | 4 | feet | `E5 FE 16 00 00 00 04 02` | `E5 FE 16 00 00 00 08 FE` |
| P1 | 4 | waist | `E5 FE 16 00 00 00 10 F6` | `E5 FE 16 00 00 00 20 E6` |
| P1 | 4 | lumbar | `E5 FE 16 00 00 00 40 C6` | `E5 FE 16 00 00 00 80 86` |
| P2 | 2 | back | `E6 FE 16 01 00 00 00 00 04` | `E6 FE 16 02 00 00 00 00 03` |
| P2 | 2 | feet | `E6 FE 16 04 00 00 00 00 01` | `E6 FE 16 08 00 00 00 00 FD` |
| P2 | 2 | both | `E6 FE 16 05 00 00 00 00 00` | `E6 FE 16 0A 00 00 00 00 FB` |
| P2 | 3 | back | `E6 FE 16 01 00 00 00 00 04` | `E6 FE 16 02 00 00 00 00 03` |
| P2 | 3 | feet | `E6 FE 16 04 00 00 00 00 01` | `E6 FE 16 08 00 00 00 00 FD` |
| P2 | 3 | head | `E6 FE 16 10 00 00 00 00 F5` | `E6 FE 16 20 00 00 00 00 E5` |
| P2 | 4 | back | `E6 FE 16 01 00 00 00 00 04` | `E6 FE 16 02 00 00 00 00 03` |
| P2 | 4 | feet | `E6 FE 16 04 00 00 00 00 01` | `E6 FE 16 08 00 00 00 00 FD` |
| P2 | 4 | waist | `E6 FE 16 10 00 00 00 00 F5` | `E6 FE 16 20 00 00 00 00 E5` |
| P2 | 4 | lumbar | `E6 FE 16 40 00 00 00 00 C5` | `E6 FE 16 80 00 00 00 00 85` |

| Route | Preset | Recall | Program |
|---|---|---|---|
| P1 | memory_1 | `E5 FE 16 01 00 00 08 FD` | `E5 FE 16 20 00 00 08 DE` |
| P1 | memory_2 | `E5 FE 16 01 00 00 09 FC` | `E5 FE 16 20 00 00 09 DD` |
| P1 | zero_g | `E5 FE 16 01 00 00 01 04` | `E5 FE 16 20 00 00 01 E5` |
| P1 | flat | `E5 FE 16 01 00 00 02 03` | `E5 FE 16 20 00 00 02 E4` |
| P2 | tv | `E6 FE 16 00 40 00 00 00 C5` | none |
| P2 | anti_snore | `E6 FE 16 00 80 00 00 00 85` | none |
| P2 | zero_g | `E6 FE 16 00 10 00 00 00 F5` | none |
| P2 | flat | `E6 FE 16 00 00 00 08 00 FD` | none |

| Route | Control | Frame / sequence |
|---|---|---|
| P1 | wave level 0 | `E5 FE 16 10 00 00 20 D6` |
| P1 | wave level 1 | `E5 FE 16 10 00 00 21 D5` |
| P1 | wave level 2 | `E5 FE 16 10 00 00 22 D4` |
| P1 | wave level 3 | `E5 FE 16 10 00 00 23 D3` |
| P1 | head level 0 | `E5 FE 16 10 00 00 10 E6` |
| P1 | head level 1 | `E5 FE 16 10 00 00 11 E5` |
| P1 | head level 2 | `E5 FE 16 10 00 00 12 E4` |
| P1 | head level 3 | `E5 FE 16 10 00 00 13 E3` |
| P1 | foot level 0 | `E5 FE 16 11 00 00 10 E5` |
| P1 | foot level 1 | `E5 FE 16 11 00 00 11 E4` |
| P1 | foot level 2 | `E5 FE 16 11 00 00 12 E3` |
| P1 | foot level 3 | `E5 FE 16 11 00 00 13 E2` |
| P1 | timer 10 min | `E5 FE 16 10 00 00 30 C6` |
| P1 | timer 20 min | `E5 FE 16 10 00 00 31 C5` |
| P1 | timer 30 min | `E5 FE 16 10 00 00 32 C4` |
| P1 | light on | `E5 FE 16 31 00 00 01 D4` |
| P1 | light off | `E5 FE 16 31 00 00 00 D5` |
| P2 | light toggle | `E6 FE 16 00 00 02 00 00 03` |
| P2 | held massage head | `E6 FE 16 00 08 00 00 00 FD` |
| P2 | held massage foot | `E6 FE 16 00 04 00 00 00 01` |
| P2 | held massage timer | `E6 FE 16 00 02 00 00 00 03` |
| P2 | held massage toggle | `E6 FE 16 00 01 00 00 00 04` |
| P2 | held massage wave | `E6 FE 16 00 00 00 10 00 F5` |
| P1 | release / STOP | `E5 FE 16 00 00 00 00 06` |
| P2 | release / STOP | `E6 FE 16 00 00 00 00 00 05` |
| P1 | massage start (saved wave/head/foot, default1) | `E5 FE 16 10 00 00 21 D5`; `E5 FE 16 10 00 00 11 E5`; `E5 FE 16 11 00 00 11 E4` |
| P1 | massage stop | `E5 FE 16 10 00 00 10 E6`; `E5 FE 16 11 00 00 10 E5` |

Alarm examples use local2026-11-17 07:06:05, alarm07:30, repeat130.

| Route | Alarm control | Frame |
|---|---|---|
| P1 | query | `E2 FE 16 05 06 07 02 F5` |
| P2 | query | `E2 80 03 00 9A` |
| P2 | clock | `E7 80 01 7E 0A 11 07 06 05 EC` |
| P1 | disable | `EB FE 16 05 06 07 FF FF 02 FF FF FF FF F2` |
| P1 | enable type0 | `EB FE 16 05 06 07 1E 07 02 82 FF FF FF 48` |
| P1 | enable type1 | `EB FE 16 05 06 07 1E 07 02 82 11 11 FF 24` |
| P1 | enable type2 | `EB FE 16 05 06 07 1E 07 02 82 FF FF 08 3F` |
| P1 | enable type3 | `EB FE 16 05 06 07 1E 07 02 82 FF FF 09 3E` |
| P2 | disable | `ED 80 03 00 00 00 00 00 00 00 00 00 00 00 00 8F` |
| P2 | enable type0 | `ED 80 03 07 1E 82 0F 00 00 00 00 00 00 00 00 D9` |
| P2 | enable type1 | `ED 80 03 07 1E 82 09 00 00 00 00 00 00 00 00 DF` |
| P2 | enable type2 | `ED 80 03 07 1E 82 0F 00 00 00 00 00 00 00 00 D9` |
| P2 | enable type3 | `ED 80 03 07 1E 82 0D 00 00 00 00 00 00 00 00 DB` |

| Lifecycle | Timing |
|---|---|
| Held refresh | immediate, then100ms after each write |
| Single, release and clock | 100ms before each write |
| Query | 200ms before write |
| Startup | subscribe only, no initialization/query/control write |
<!-- /generated -->

#### Timing

The generated table gives app timing. Motor, P2 preset and P2 massage holds use
elapsed deadlines and renewable HA leases, up to 30 seconds. Cancellation drains
the zero-word release on the captured connection. A replacement session
never receives old movement, settings or release packets. P1 one-shot presets,
settings and sequences do not gain an added trailing STOP. HA supplies
serialization, bounded commands and cleanup for cancellation, including the
P2 massage cancellation case the app omits. Disconnect stopping remains unknown.

#### Notifications

`UltramaticParser` preserves the corrected fresh-fragment rule: a 4..20-byte
F4 prefix caches and returns without state changes or callback. Uncached short
non 10/non 16 inputs also return unchanged. Exact 10/16, >20 and cached continuation
paths retain their existing decoder differences; a continuation leaves the
cache intact. Unknown decoded lengths reset massage values, while an input
returned by the preflight does not. HA clears the activity-wide app cache and
reported state at the connection boundary, and ignores retired callbacks.

Alarm fields retain signed Java values and P2 raw actions. P2 repeat 80 is a
sentinel for the prior true repeat; P1 repeat 80 decodes to-128. Received-128
and positive UI 128 remain distinct when sent back. No checksum or strict
header validation is added to massage decoding. HA ignores truncated alarm
fields safely instead of reproducing out-of-bounds exceptions. Notifications
carry no positions or light state. Bleak manages the actual notification
subscription; the Android app only enables it locally and writes no CCCD.

#### Services

The bed alarm uses [`set_alarm`](../SERVICES.md#set_alarm) with `enabled`,
`time`, `weekdays` and `wake_action`. P1 offers `none`, `massage`, `memory_1`
and `memory_2`; P2 offers `tv`, `massage` and `zero_g` (the app's alarm types
0, 1 and 3; P2 type 2 sends the same TV record as 0). Turning the alarm on needs
an explicit wake action, and every bed's live route is checked before any bed is
written. Weekdays set repeat bits
0..6, Sunday..Saturday, plus bit 7, as the app does when days are edited. No
weekdays means once: today, or tomorrow when the requested hour/minute has
passed; seconds do not change that comparison. P1 carries current clock fields in its query/alarm;
P2 sends clock, alarm, then query. The bed reports its alarm only when
asked, so both routes expose **Refresh alarm**, a diagnostic button disabled
by default. The **Alarm time** sensor shows the reported time when it is a
valid time of day, with the signed repeat byte and raw action as attributes. P2 also
supports the **Set bed clock** action, held presets and held controls actions.
Whole-target acceptance captures STOP epochs and paired ownership before the
first import/connect wait. A child-device target retains its side.

#### Evidence

Based on Ultramatic 1.0.5 (`com.ore.ultramatic`). Both transport builders
reproduce every app frame through the Keeson codec. Physical layouts, stopping
and reply semantics still need testing on hardware.

### Aging in Place / Dawn House

**App:** [Aging in Place](https://play.google.com/store/apps/details?id=com.keeson.agingplace) 1.1.0 (87), `com.keeson.agingplace`. The installed app is named Dawn House.

**Status:** Not yet tested

#### Setup

Choose **Aging in Place / Dawn House app**. Discovery accepts case-sensitive names
containing `KSWF07S` or `KSWF19S`, without requiring an advertised service UUID.
The exact selected Bluetooth identity supplies JSON `dvid`; it is neither the
editable HA title, MAC address nor a side selector. A missing stored identity
falls back to the live advertisement name; an absent identity omits `dvid`.

Sensor display mode may follow an observed device-info sensor count (`dspsen`
at most 2 means mode 0, otherwise mode 1) or an explicitly retained mode 0, 1
or 2. The telemetry side choices are Left, Right or a separately selected side.
They affect incoming observations only. Two physical addresses can form an HA
pair. A single-address pair has no command selector and is refused.

No account, Wi-Fi setup, firmware check, PIN or application handshake is needed,
and every control is available regardless of firmware version.

#### Controls

Head, foot and aggregate bed-height covers, In/Out held buttons, Flat, Zero-G and
Anti snore presets, the three cycles, self check, massage cycling and underbed light
toggling are available. The app's Read button sends the Anti snore key, so it has no
separate entity; `agingplace_action` keeps `read`. Flat and STOP end a running cycle
or self check. No individual
lift, angle feedback, memory programming, RGB selection or command side is guessed.

<!-- generated:agingplace-controls -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Control | code | cmd (typed JSON) | Execution |
|---|---|---|---|
| Underbed light | 2 | `{"ctrm":1,"key":"00020000","keykt":0,"km":1}` | Single write |
| Massage cycle | 2 | `{"ctrm":1,"key":"00000100","keykt":0,"km":1}` | Single write |
| Zero gravity | 2 | `{"ctrm":1,"key":"00001000","keykt":0,"km":1}` | Single write |
| Anti snore | 2 | `{"ctrm":1,"key":"00008000","keykt":0,"km":1}` | Single write |
| Read | 2 | `{"ctrm":1,"key":"00008000","keykt":0,"km":1}` | Single write |
| Flat | 2 | `{"ctrm":1,"key":"08000000","keykt":0,"km":1}` | Single write |
| Head up | 2 | `{"ctrm":0,"key":"00000001","keykt":1,"km":5}` | Held |
| Head down | 2 | `{"ctrm":0,"key":"00000002","keykt":1,"km":5}` | Held |
| Foot up | 2 | `{"ctrm":0,"key":"00000004","keykt":1,"km":5}` | Held |
| Foot down | 2 | `{"ctrm":0,"key":"00000008","keykt":1,"km":5}` | Held |
| Bed height up | 2 | `{"ctrm":0,"key":"00000050","keykt":1,"km":5}` | Held |
| Bed height down | 2 | `{"ctrm":0,"key":"000000a0","keykt":1,"km":5}` | Held |
| In | 2 | `{"ctrm":1,"key":"40000000","keykt":0,"km":6}` | Held |
| Out | 2 | `{"ctrm":1,"key":"80000000","keykt":0,"km":6}` | Held |
| Release held control | 2 | `{"ctrm":0,"key":"00000000","keykt":0,"km":1}` | Single write |
| Circulation cycle | 2 | `{"key":"20000000","km":2}` | Single write |
| Sleep cycle | 2 | `{"key":"10000000","km":2}` | Single write |
| Relax cycle | 2 | `{"key":"08020000","km":2}` | Single write |
| Self check | 4 | `{"key":"00400000","km":2}` | Single write |
<!-- /generated -->

Brightness uses `255 - trunc(2.5 * progress)` with zero RGB integer defaults.
Massage duration and motion-light duration retain the field spelling `massagT`
and send seconds. Native numbers show successful local requests, not device
readback. Toggle buttons do not infer the light or massage state. The massage
cycle follows the app's Low, Medium, High, Off tutorial; no absolute-level command
is added. The tutorial's 10-minute description does not replace the duration
picker's 30-minute initial choice.

<!-- generated:agingplace-settings -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Setting | Range | Default picker | Wire example (dvid D) |
|---|---|---|---|
| Light brightness | 0–100 | 50 | `{"cmd":{"B":0,"G":0,"R":0,"bright":130,"cmd":187,"dummy":0,"key":"00000000"},"code":10,"dvid":"D"}` |
| Massage duration | 1–60 min | 30 min | `{"cmd":{"bright":0,"cmd":16,"dummy":0,"key":"00000000","massagT":1800},"code":8,"dvid":"D"}` |
| Motion light duration | 1–30 min | 15 min | `{"cmd":{"bright":0,"cmd":17,"dummy":0,"key":"00000000","massagT":900},"code":9,"dvid":"D"}` |
| Device information | Query | No startup write | `{"cmd":{"sw":1},"code":4,"dvid":"D"}` |

| Cycle | Display total (seconds) |
|---|---|
| circulation | 5400 |
| sleep | 930 |
| relax_cycle | 600 |
<!-- /generated -->

#### Timing

<!-- generated:agingplace-timing -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Role | UUID |
|---|---|
| Service | 0000a00a-0000-1000-8000-00805f9b34fb |
| Write | 0000b002-0000-1000-8000-00805f9b34fb |
| Indicate | 0000b004-0000-1000-8000-00805f9b34fb |

| Operation | Value |
|---|---|
| Post-connect wait | 300 ms |
| App requested MTU | 260 |
| Literal split size | 260 bytes |
| Indication ready wait | 100 ms |
| Held refresh | Immediate, then fixed 200 ms delays after completion |
| Release | One zero-key packet after the drained refresh |
| Self check timeout / quiet aggregation | 20 s / 2 s |
<!-- /generated -->

Indications must be available before commands. Bleak negotiates MTU through its
backend, rather than providing Android's portable `requestMtu(260)` operation.
B004 uses the indication channel, with CCCD handled by the Bluetooth backend;
WinRT receives an explicit indication preference. MTU acceptance, dual-property
subscription behavior and the app's 260-byte chunks still need testing on hardware. Chunks are contiguous and unframed; a failed chunk advances the
queue without retry and the failure remains visible to HA.

Holds use elapsed duration and the source's fixed-delay refresh. An accepted
write drains before its independent zero release, even on repeated cancellation.
Cleanup never migrates to a replacement session. Flat cancels cycles and self
check; it is distinct from the zero held-key release. No binary query is sent on
startup. HA owns bounded discovery/retry, selected-address reconnect and explicit
handoff instead of reproducing the app's unbounded retries and release race.

#### Notifications

Every indication is an independent UTF-8 JSON document. A fragment is refused;
no reassembly, ACK correlation, identity validation or deduplication is added.
Cycle displays subtract the received timer from totals of 5400, 930 and 600 seconds.

Realtime data carries `dt`, `di`, `ts`, `bm`, `br`, `hr`, `lb`, `si` and `sn`.
HA exposes **Occupancy**, **Heart rate** and **Breathing rate** from it. Modes 0
and 2 show every reading; mode 1 (two sensors) keeps only readings whose `si`
matches the telemetry side. `lb == 0` means occupied. Heart and breathing values
are shown directly while occupied and clear when the bed is empty or disconnects.
The other fields, including `bm` and `sn`, stay in the support bundle's raw
notifications; they have no confirmed meaning. Measurements still need testing.

Device info carries string `MAC`, `dspver`, `hardver`, `pcbver`, `wifiver`, envelope
`di`, integer `dspsen`/`bedmd`, and integer version divided by 100. HA shows the
version as the diagnostic **Firmware version** sensor (disabled by default) with the
other fields as attributes. The diagnostic **Refresh device information** button
(disabled by default) sends the query; nothing is queried at startup. MAC presence gates
the setup fields; it never substitutes for selected `dvid`. The observed Wi-Fi
module version does not expose Wi-Fi administration. A provisioning response
invalidates shared BED acceptance and the link, after which HA must subscribe again.
Provisioning payloads and credentials are neither generated nor published.

The **Self check** button and **Self check status** sensor are diagnostic and
disabled by default. The sensor shows waiting, running, observed, complete or
timeout. Its attributes hold the complete observed response, the maximum
head/foot/lift ripple values and the mask-derived head, foot, lift and massage
connectivity. Diagnostic ripple is not position feedback. The app's Random-generated current
displays are excluded from telemetry. Self check times out after 20 seconds and
aggregates observed results after 2 seconds without another diagnostic indication.

#### Services

`agingplace_action` exposes the tap commands, three cycles, Flat cancellation,
held-key release, self check and device-info query. `agingplace_set_setting` accepts
brightness 0–100, massage duration 1–60 minutes or motion-light duration 1–30 minutes.
Use generic `hold_control` for the eight held controls and generic `timed_move`
for a motor. Native controls and services use the coordinator's scheduler.

All physical targets and STOP generations are captured before imports or live
preflight; every target must validate before any writes. Native child devices keep
their physical side in concurrent or sequential two-link pairs. Single-link side
commands are rejected rather than converted into added wire selectors.

#### Analysis provenance

Based on Aging in Place 1.1.0 (87) (`com.keeson.agingplace`).

### Enso Remote

**App:** [Enso Remote](https://play.google.com/store/apps/details?id=com.ore.sfm2) 2.3, `com.ore.sfm2`

**Status:** Not yet tested

#### Setup

Detection: none. Choose **Enso Remote**, select the bed address, then choose
**2 motors: back and feet**, **3 motors: back, feet and lumbar** or **4 motors:
back, feet, waist and lumbar**, as in the app. The layout is also available through
Reconfigure. Advertisements do not identify a layout. Both characteristic roles
must exist; services are enumerated without a fixed service UUID. The last
matching handle for each role is selected independently.

Write mode follows live characteristic properties: acknowledged writes when
available, otherwise writes without response. The app does not set a write mode.
The app only registers for notifications locally; for Home Assistant, Bleak
handles the subscription and any required CCCD write. Actual properties and
notification delivery need hardware testing.

#### Controls

Back and foot controls are present on all layouts. The 2-motor layout also has
combined back/foot movement. The 3-motor layout adds the app's lumbar-labelled
controls; its artwork depicts head motion, so the physical actuator needs
confirmation. The 4-motor layout adds separately labelled waist and lumbar
controls. No position or angle readout is supported.

**Flat** and **Zero gravity** are single presses with release. Memory A/B use
held commands, exposed as **Memory 1** and **Memory 2**; no save/program command
is supported. The massage page has **Increase head massage**, **Decrease head
massage**, **Increase foot massage**, **Decrease foot massage**, **Cycle massage
intensity** and **Cycle massage timer** buttons, and the **Massage timer**
sensor shows the reported timer. The memory page's held timer gesture is
available through [`hold_control`](../SERVICES.md#hold_control). **Cycle
massage mode** is available only on the 3-motor layout. These cycle commands do
not set an absolute intensity or timer.

The light toggle is a single press, with no extra zero release. The **Under-bed
lights** light shows the reported light state and sends the toggle when it
differs from the one asked for; the physical toggle behavior needs confirmation.

<!-- generated:keeson-enso -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Layout | Controls | Refresh |
|---|---|---|
| 2 | back, foot, combined | 100 ms |
| 3 | back, foot, lumbar | 100 ms |
| 4 | back, foot, waist, lumbar | 100 ms |

| Control | Frame |
|---|---|
| Release | `E5 FE 16 00 00 00 00 06` |
| Flat | `E5 FE 16 00 00 00 08 FE` |
| Zero Gravity | `E5 FE 16 00 10 00 00 F6` |
| Light button | `E5 FE 16 00 00 02 00 04` |
| head_massage_increase | `E5 FE 16 00 08 00 00 FE` |
| head_massage_decrease | `E5 FE 16 00 00 80 00 86` |
| foot_massage_increase | `E5 FE 16 00 04 00 00 02` |
| foot_massage_decrease | `E5 FE 16 00 00 00 01 05` |
| massage_level | `E5 FE 16 00 01 00 00 05` |
| timer_massage_page | `E5 FE 16 00 02 00 00 04` |
| memory_A | `E5 FE 16 00 20 00 00 E6` |
| memory_B | `E5 FE 16 00 40 00 00 C6` |
| timer_memory_page | `E5 FE 16 00 02 00 00 04` |
| massage_mode | `E5 FE 16 00 00 00 04 02` |
| Back up | `E5 FE 16 01 00 00 00 05` |
| Back down | `E5 FE 16 02 00 00 00 04` |
| Foot up | `E5 FE 16 04 00 00 00 02` |
| Foot down | `E5 FE 16 08 00 00 00 FE` |
| Waist up | `E5 FE 16 10 00 00 00 F6` |
| Waist down | `E5 FE 16 20 00 00 00 E6` |
| Lumbar up | `E5 FE 16 40 00 00 00 C6` |
| Lumbar down | `E5 FE 16 80 00 00 00 86` |
| Back and foot up | `E5 FE 16 05 00 00 00 01` |
| Back and foot down | `E5 FE 16 0A 00 00 00 FC` |

| Role | Characteristic | Service |
|---|---|---|
| Write | 0000ffe9-0000-1000-8000-00805f9b34fb | Discovered at runtime |
| Notify | 0000ffe4-0000-1000-8000-00805f9b34fb | Discovered at runtime |
<!-- /generated -->

#### Timing

Ordinary taps use a bounded one-second window at the fixed refresh interval.
Movement per tap is not offered for this profile; use an explicit timed move or
held-control action for another duration. Held controls start immediately and
refresh at that interval until
release, cancellation or the bounded hold expires. Each sends the zero-key
release in `finally` using a fresh cancellation event. Flat/Zero Gravity send
one nonzero frame followed by release; massage-page and light actions send one
nonzero frame only. STOP sends the native zero-key release, not a separate
emergency-stop opcode. Cleanup stays bound to its original link and cannot be
sent through a reconnected bed. Physical stopping after link loss is unverified.

#### Notifications

Only complete 16- and 19-byte values are parsed. Bit 5 at offset 13 or 14
suppresses processing. The light page displays bit 6 at that offset; the
movement/massage pages display the next byte as 10/20/30 minutes for 1/2/3, or
off for 255. Home Assistant maintains both page projections. Other timer values
leave the previous value unchanged. There is no header/checksum check, fragment
assembly, position field or command acknowledgement. Session changes clear the
indicators and invalidate old notification callbacks.

#### Services

The shared [`rename`](../SERVICES.md#rename) action sends the Bluetooth name
frame. The name is trimmed of leading and trailing characters U+0000 to U+0020
and must then be 1 to 14 UTF-16 code units, so a character outside the basic
plane, such as an emoji, counts twice. Like the app, the integration sends only
as many UTF-8 bytes as the name has UTF-16 code units, so a non-ASCII name is
cut short (`é` is sent as the single byte `C3`). ASCII names are sent exactly;
how the bed handles other bytes needs hardware testing. Rename sends once, with
no release and no confirmation from the bed, and the bed may not advertise the
new name. Standard movement, memory and held-control actions are supported;
clock and alarm actions are unavailable.

#### Evidence

Based on Enso Remote 2.3 (`com.ore.sfm2`). Hardware is not yet tested.

### Alya Smart Furnishing (Sino P2)

**App:** [Alya Smart Furnishing](https://play.google.com/store/apps/details?id=com.okin.bedding.alya) 1.0.2, `com.okin.bedding.alya`

**Status:** ❓ Hardware unverified

#### Setup

Select the explicit Alya BLE type and motor layout. The [Alya app guide](alya.md) holds this app's generated layout, transport and command tables and its release/state rules. Shared frames do not select another app's capabilities or timings.

## King Koil Bed

**Status:** Not yet tested on hardware.

### Known Models

King Koil Bed's two remote layouts. Bluetooth names containing the exact,
case-sensitive `KSBT03CK` or `KSBT03CL` tokens are candidates, not proof of layout.

### Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | King Koil Bed 1.0 (code 1) | `com.sfd.kingkoilbed` |

### Features

| Feature | Supported |
|---------|-----------|
| Movement | Head/foot, or app-labelled Head A/Head B/foot |
| Presets | Flat, zero gravity and TV |
| Massage | Four button actions on the head/foot layout; cycles and levels unspecified |
| Light | Button action and reported light icon; transitions unspecified |
| Reported state | Light icon; head/foot layout also reports a 0/10/20/30 timer indicator |
| Position feedback / memory programming | None |

### Protocol Details

Nordic UART service `6e400001-b5a3-f393-e0a9-e50e24dcca9e`, write
`6e400002-b5a3-f393-e0a9-e50e24dcca9e`, notify
`6e400003-b5a3-f393-e0a9-e50e24dcca9e`. Both roles must belong to that
service. No fallback service, pairing exchange or startup control is used.
Control writes are six-byte P2 frames; `00 b0` is a separate status query.
The inherited characteristic write type is retained: response when writable,
otherwise without response when that is the only supported write mode.
HA manages the connection, MTU and CCCD subscription through its Bluetooth stack.

### Detection / Setup

Select **King Koil Bed app**, then choose the remote by its visible controls.
The saved app selectors and image filenames are inverted:

- Head/foot with massage is saved `KSBT03CK`, but its guide image is `KSBT03CL`.
- Head A/Head B/foot is saved `KSBT03CL`, but its guide image is `KSBT03CK`.

No layout is inferred from shared Nordic UUIDs or a discovered Bluetooth name.
A/B are app labels; their physical actuator anatomy and left/right relation are
unverified. No combined-side control is inferred.

### Commands

<!-- generated:keeson-kingkoil -->
| Saved app selector | Control | Frame | Timing |
|---|---|---|---|
| KSBT03CK | head up | `04 02 00 00 00 01` | held, 300 ms |
| KSBT03CK | head down | `04 02 00 00 00 02` | held, 300 ms |
| KSBT03CK | feet up | `04 02 00 00 00 04` | held, 300 ms |
| KSBT03CK | feet down | `04 02 00 00 00 08` | held, 300 ms |
| KSBT03CK | flat | `04 02 08 00 00 00` | once |
| KSBT03CK | zero_g | `04 02 00 00 10 00` | once |
| KSBT03CK | tv | `04 02 00 00 40 00` | once |
| KSBT03CK | light | `04 02 00 02 00 00` | held, 300 ms |
| KSBT03CK | massage_mode | `04 02 04 00 00 00` | once |
| KSBT03CK | massage_head | `04 02 00 00 08 00` | once |
| KSBT03CK | massage_foot | `04 02 00 00 04 00` | once |
| KSBT03CK | massage_timer | `04 02 00 00 02 00` | once |
| KSBT03CK | status query | `00 B0` | 500 ms live poll |
| KSBT03CL | head_a up | `04 02 00 00 00 01` | held, 300 ms |
| KSBT03CL | head_a down | `04 02 00 00 00 02` | held, 300 ms |
| KSBT03CL | head_b up | `04 02 00 00 00 04` | held, 300 ms |
| KSBT03CL | head_b down | `04 02 00 00 00 08` | held, 300 ms |
| KSBT03CL | feet up | `04 02 00 00 00 10` | held, 300 ms |
| KSBT03CL | feet down | `04 02 00 00 00 20` | held, 300 ms |
| KSBT03CL | flat | `04 02 08 00 00 00` | once |
| KSBT03CL | zero_g | `04 02 00 00 10 00` | once |
| KSBT03CL | tv | `04 02 00 00 40 00` | once |
| KSBT03CL | light | `04 02 00 02 00 00` | once |
| KSBT03CL | status query | `00 B0` | 500 ms live poll |
<!-- /generated -->

### Position Feedback / Notifications

Notifications of at least 13 bytes report the light icon from nonzero byte 12.
On saved `KSBT03CK`, the unsigned big-endian value at bytes 3/4 selects the app's
timer indicator: greater than 1200 means 30, greater than 600 means 20, positive
means 10, otherwise 0. These are UI indicators, not established timer wire units.
No header, checksum, motor position or command ACK is inferred. Short replies
are ignored. Reported values start unknown and clear on disconnect; local button
presses never predict them. The diagnostic status-refresh button is disabled by
default.

### Command Timing

Movement starts immediately and refreshes every 300 ms while admitted. The
`KSBT03CK` light is held with the same cadence; the `KSBT03CL` light writes once.
Other actions write once. Status polling runs every 500 ms on an already-live idle
connection, serialized and preemptible through HA. It never opens a connection.

Both live app release paths only cancel refresh and send no STOP/release packet.
HA STOP fences pending refreshes and waits for a submitted write to settle on
its original connection. It does not abort a recalled preset. Firmware watchdog
and physical stopping time remain unverified; keep the physical remote available
for initial testing. No neutral frame is invented.

### Notes

No massage cycle order, light transition, memory slot, device position or
physical multi-motor combination is inferred from sibling apps.

#### Analysis provenance

Based on the complete APK Protocol Audit of King Koil Bed 1.0 (`com.sfd.kingkoilbed`),
with its base APK and all four delivery splits. All 24 outbound action instances
reproduce through the existing Keeson P2 encoder and query literal. Seven parser
vectors are synthetic boundary inputs, not captured hardware replies.

### Hestia Motion

**App:** [Hestia Motion](https://play.google.com/store/apps/details?id=com.ore.yorkfeng.hestiamotion) 1.2 (3), `com.ore.yorkfeng.hestiamotion`

**Status:** Not yet tested on hardware.

#### Setup

Choose **Hestia Motion app** explicitly, then choose the bed's Bluetooth address.
There is no app-specific Bluetooth name filter. The controller searches all
services for the last FFE9 write characteristic and last FFE4 notification
characteristic. A particular service UUID is not required. Home Assistant
chooses a write mode from the live characteristic properties, preferring writes
without response when available. The app's effective write mode and the bed's
subscription requirements need hardware testing.

#### Controls

Head/back and foot/legs movement, combined movement, Zero G, Flat, Anti Snore,
Memory A/B recall and save, under-bed light on/off, aggregate massage and a bed
RTC wake alarm are available. No third actuator or position feedback is exposed.

The wave and intensity selectors change local choices. Turning massage on sends
wave then intensity; intensity zero turns it off. Selecting a timer sends its
command immediately, independently of the massage switch. No timer countdown or
actual massage state is reported.

Alarm hour, minute, wake position and enhancement are pending choices, applied
when the bed alarm switch is operated. Enhancement uses the same intensity, wave
and timer choices as massage. Memory A/B wake position is independent of massage
enhancement. Changing a choice while the alarm is enabled does not rewrite the
alarm until the switch is operated again. States show local choices or last-sent
intent, not confirmation from the bed. Local choices survive reconnects; last-sent
light, massage and alarm state becomes unknown on disconnect.

<!-- generated:keeson-hestia -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Control | Frame |
|---|---|
| back up | `E5 FE 16 00 00 00 01 05` |
| back down | `E5 FE 16 00 00 00 02 04` |
| legs up | `E5 FE 16 00 00 00 04 02` |
| legs down | `E5 FE 16 00 00 00 08 FE` |
| both up | `E5 FE 16 00 00 00 05 01` |
| both down | `E5 FE 16 00 00 00 0A FC` |
| Movement release | `E5 FE 16 00 00 00 00 06` |
| Preset cancel | `E5 FE 16 21 00 00 00 E5` |
| zero_g | `E5 FE 16 21 00 00 01 E4` |
| flat | `E5 FE 16 21 00 00 02 E3` |
| anti_snore | `E5 FE 16 21 00 00 03 E2` |
| Memory 1 recall | `E5 FE 16 21 00 00 04 E1` |
| Memory 2 recall | `E5 FE 16 21 00 00 06 DF` |
| Memory 1 save | `E5 FE 16 21 00 00 14 D1` |
| Memory 2 save | `E5 FE 16 21 00 00 16 CF` |
| Light off | `E5 FE 16 31 00 00 00 D5` |
| Light on | `E5 FE 16 31 00 00 01 D4` |
| Massage intensity 0 | `E5 FE 16 10 00 00 10 E6` |
| Massage intensity 1 | `E5 FE 16 10 00 00 11 E5` |
| Massage intensity 2 | `E5 FE 16 10 00 00 12 E4` |
| Massage intensity 3 | `E5 FE 16 10 00 00 13 E3` |
| Massage wave 0 | `E5 FE 16 10 00 00 20 D6` |
| Massage wave 1 | `E5 FE 16 10 00 00 21 D5` |
| Massage wave 2 | `E5 FE 16 10 00 00 22 D4` |
| Massage wave 3 | `E5 FE 16 10 00 00 23 D3` |
| Massage timer 10 min | `E5 FE 16 10 00 00 30 C6` |
| Massage timer 20 min | `E5 FE 16 10 00 00 31 C5` |
| Massage timer 30 min | `E5 FE 16 10 00 00 32 C4` |

| Operation | Schedule |
|---|---|
| Movement | Immediate, then 100 ms after each completed write |
| Movement release / explicit STOP | 100 ms delay; one zero key |
| Presets / save / light / massage | 100 ms before each key; one write |
| Massage On | Wave, then intensity; Off is a single intensity-zero key |
| Alarm enable / disable | One EA FE 16 frame, no added delay or release |

| Local setting | Choices | HA initial choice |
|---|---|---|
| intensity | 0, 1, 2, 3 | 0 |
| wave | 0, 1, 2, 3 | 0 |
| timer | 10, 20, 30 | 10 |
| hour | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23 | 0 |
| minute | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59 | 0 |
| memory | none, memory_1, memory_2 | none |
<!-- /generated -->

#### Timing

See the generated schedules above. Repeating the same preset sends the distinct
preset-cancel key. Movement and lighting preserve that preset selection. Explicit
STOP cancels a preset started in the current session; the separate Cancel preset
button sends that key unconditionally. Held movement always finishes with its
zero-key release, including cancellation and write failure, while that exact
connection is still current. Cleanup never transfers to a replacement connection.

#### Notifications

Nonempty FFE4 notifications go to raw diagnostics only. There is no semantic
parser, position sensing, acknowledgement, initialization or device-info query.

#### Services

Use the standard memory, hold and light actions and [`set_alarm`](../SERVICES.md#set_alarm).
The alarm accepts `wake_action: none`, `memory_1` or `memory_2`; optional `massage`,
`massage_intensity` and `massage_duration` select enhancement. Its wave comes from
the native wave selector. It has no weekday or ringtone field. Disabling it keeps
the current clock and clears the schedule and feature fields. The native controls
also allow intensity zero for enhancement, which encodes the app's FF sentinel.

#### Evidence

Based on Hestia Motion 1.2 (3). Frozen literals and finite alarm mappings are
covered in `tests/fixtures/hestia_vectors.json` and `tests/test_hestia.py`.

### PowersBedding

**App:** [PowersBedding](https://play.google.com/store/apps/details?id=com.ore.powersbedding) 1.1.0 (2), `com.ore.powersbedding`

**Status:** Not yet tested with hardware.

#### Setup

Select **PowersBedding app** manually. Its common `okin` and `smartbed` Bluetooth
prefixes do not identify an app. The fixed layout has head, feet and combined
head/feet controls. There is no third actuator or single-address side selector.
Two separate receivers can use Home Assistant's ordinary paired-bed controls;
each receiver retains its own name, capabilities and massage choices.

The Bluetooth name chooses GATT roles before the manufacturer read: `okin`
uses FFE5/FFE9 write and FFE0/FFE4 notifications; `smartbed` uses Nordic UART.
The exact manufacturer value `BLE-4.0 Module` selects P2 packets on either
transport. Another non-null value selects P1; an absent value leaves P1 for
`okin` and P3 for `smartbed`. Packet route never changes the selected GATT
roles. Home Assistant requires live writable and subscribable characteristics
and never retains a characteristic from an old connection. The app does not
set a write type; Home Assistant uses the live properties, preferring writes
without response when supported.

#### Controls

Every route has head/feet movement, combined movement, flat, zero gravity,
two memories, memory programming, lighting and two-zone massage. P1 has
independent head/foot/wave levels, start/stop and a shared 10/20/30 minute
massage timer select. P2/P3 have zone increments/decrements, massage toggle,
wave cycle and timer cycle buttons; these are steps, with no assumed absolute
level or wrap count. P1 lighting is on/off; P2/P3 lighting is a toggle.

<!-- generated:keeson-powersbedding -->
| Route | Control | Frame | Timing |
|---|---|---|---|
| p1 | head up | `E5 FE 16 00 00 00 01 05` | held, 100 ms |
| p1 | head down | `E5 FE 16 00 00 00 02 04` | held, 100 ms |
| p1 | feet up | `E5 FE 16 00 00 00 04 02` | held, 100 ms |
| p1 | feet down | `E5 FE 16 00 00 00 08 FE` | held, 100 ms |
| p1 | both up | `E5 FE 16 00 00 00 05 01` | held, 100 ms |
| p1 | both down | `E5 FE 16 00 00 00 0A FC` | held, 100 ms |
| p1 | driver STOP | `E5 FE 16 00 00 00 00 06` | twice, 100 ms apart |
| p1 | zero_g | `E5 FE 16 01 00 00 01 04` | once |
| p1 | flat | `E5 FE 16 01 00 00 02 03` | once |
| p1 | memory 1 | `E5 FE 16 01 00 00 08 FD` | once |
| p1 | save memory 1 | `E5 FE 16 20 00 00 08 DE` | 6 s hold, 5 s refresh |
| p1 | memory 2 | `E5 FE 16 01 00 00 09 FC` | once |
| p1 | save memory 2 | `E5 FE 16 20 00 00 09 DD` | 6 s hold, 5 s refresh |
| p1 | save zero gravity | `E5 FE 16 20 00 00 01 E5` | 6 s, no release packet |
| p1 | head massage 0 | `E5 FE 16 10 00 00 10 E6` | once |
| p1 | head massage 1 | `E5 FE 16 10 00 00 11 E5` | once |
| p1 | head massage 2 | `E5 FE 16 10 00 00 12 E4` | once |
| p1 | head massage 3 | `E5 FE 16 10 00 00 13 E3` | once |
| p1 | foot massage 0 | `E5 FE 16 11 00 00 10 E5` | once |
| p1 | foot massage 1 | `E5 FE 16 11 00 00 11 E4` | once |
| p1 | foot massage 2 | `E5 FE 16 11 00 00 12 E3` | once |
| p1 | foot massage 3 | `E5 FE 16 11 00 00 13 E2` | once |
| p1 | wave massage 0 | `E5 FE 16 10 00 00 20 D6` | once |
| p1 | wave massage 1 | `E5 FE 16 10 00 00 21 D5` | once |
| p1 | wave massage 2 | `E5 FE 16 10 00 00 22 D4` | once |
| p1 | wave massage 3 | `E5 FE 16 10 00 00 23 D3` | once |
| p1 | timer argument -1 | `E5 FE 16 10 00 00 2F C7` | once |
| p1 | timer argument 0 | `E5 FE 16 10 00 00 30 C6` | once |
| p1 | timer argument 1 | `E5 FE 16 10 00 00 31 C5` | once |
| p1 | timer argument 2 | `E5 FE 16 10 00 00 32 C4` | once |
| p1 | light off | `E5 FE 16 31 00 00 00 D5` | once |
| p1 | light on | `E5 FE 16 31 00 00 01 D4` | once |
| p1 | stop preset | `E5 FE 16 01 00 00 00 05` | same-preset second tap |
| p1 | clock example | `E2 FE 16 1E 2D 06 05 B3` | local 2026-11-27 06:45:30 |
| p1 | alarm example | `EB FE 16 1E 2D 06 1E 07 05 BE 11 11 F8 AD` | weekdays, memory A |
| p1 | cancel alarm example | `EB FE 16 1E 2D 06 FF FF FF FF FF FF 18 9D` | twice, then clock at 100 ms |
| p2 | head up | `E6 FE 16 01 00 00 00 00 04` | held, 100 ms |
| p2 | head down | `E6 FE 16 02 00 00 00 00 03` | held, 100 ms |
| p2 | feet up | `E6 FE 16 04 00 00 00 00 01` | held, 100 ms |
| p2 | feet down | `E6 FE 16 08 00 00 00 00 FD` | held, 100 ms |
| p2 | both up | `E6 FE 16 05 00 00 00 00 00` | held, 100 ms |
| p2 | both down | `E6 FE 16 0A 00 00 00 00 FB` | held, 100 ms |
| p2 | driver STOP | `E6 FE 16 00 00 00 00 00 05` | twice, 100 ms apart |
| p2 | zero_g | `E6 FE 16 00 10 00 00 00 F5` | once |
| p2 | flat | `E6 FE 16 00 00 00 08 00 FD` | once |
| p2 | memory 1 | `E6 FE 16 00 00 01 00 00 04` | once |
| p2 | save memory 1 | `E6 FE 16 00 00 01 00 00 04` | 6 s hold, 100 ms refresh |
| p2 | memory 2 | `E6 FE 16 00 00 04 00 00 01` | once |
| p2 | save memory 2 | `E6 FE 16 00 00 04 00 00 01` | 6 s hold, 100 ms refresh |
| p2 | save zero gravity | `E6 FE 16 00 10 00 00 00 F5` | 6 s, no release packet |
| p2 | massage toggle | `E6 FE 16 00 01 00 00 00 04` | once; P3 query after 150 ms |
| p2 | massage head_up | `E6 FE 16 00 08 00 00 00 FD` | once; P3 query after 150 ms |
| p2 | massage head_down | `E6 FE 16 00 00 80 00 00 85` | once; P3 query after 150 ms |
| p2 | massage foot_up | `E6 FE 16 00 04 00 00 00 01` | once; P3 query after 150 ms |
| p2 | massage foot_down | `E6 FE 16 00 00 00 01 00 04` | once; P3 query after 150 ms |
| p2 | massage wave | `E6 FE 16 00 00 00 10 00 F5` | once; P3 query after 150 ms |
| p2 | massage timer | `E6 FE 16 00 02 00 00 00 03` | once; P3 query after 150 ms |
| p2 | light toggle | `E6 FE 16 00 00 02 00 00 03` | once |
| p2 | read alarm | `E1 80 03 9B` | once |
| p2 | clock example | `E7 80 01 7E 0A 1B 06 2D 1E A3` | local 2026-11-27 06:45:30 |
| p2 | alarm example | `ED 80 03 07 1E BE 11 00 00 00 00 00 00 00 00 9B` | weekdays, memory A |
| p2 | cancel alarm example | `ED 80 03 00 00 00 00 00 00 00 00 00 00 00 00 8F` | twice, then clock at 100 ms |
| p3 | head up | `05 02 00 00 00 01 00` | held, 100 ms |
| p3 | head down | `05 02 00 00 00 02 00` | held, 100 ms |
| p3 | feet up | `05 02 00 00 00 04 00` | held, 100 ms |
| p3 | feet down | `05 02 00 00 00 08 00` | held, 100 ms |
| p3 | both up | `05 02 00 00 00 05 00` | held, 100 ms |
| p3 | both down | `05 02 00 00 00 0A 00` | held, 100 ms |
| p3 | driver STOP | `05 02 00 00 00 00 00` | twice, 100 ms apart |
| p3 | zero_g | `05 02 00 00 10 00 00` | once |
| p3 | flat | `05 02 08 00 00 00 00` | once |
| p3 | memory 1 | `05 02 00 01 00 00 00` | once |
| p3 | save memory 1 | `05 02 00 01 00 00 00` | 6 s hold, 100 ms refresh |
| p3 | memory 2 | `05 02 00 04 00 00 00` | once |
| p3 | save memory 2 | `05 02 00 04 00 00 00` | 6 s hold, 100 ms refresh |
| p3 | save zero gravity | `05 02 00 00 10 00 00` | 6 s, no release packet |
| p3 | massage toggle | `05 02 00 00 01 00 00` | once; P3 query after 150 ms |
| p3 | massage head_up | `05 02 00 00 08 00 00` | once; P3 query after 150 ms |
| p3 | massage head_down | `05 02 00 80 00 00 00` | once; P3 query after 150 ms |
| p3 | massage foot_up | `05 02 00 00 04 00 00` | once; P3 query after 150 ms |
| p3 | massage foot_down | `05 02 01 00 00 00 00` | once; P3 query after 150 ms |
| p3 | massage wave | `05 02 10 00 00 00 00` | once; P3 query after 150 ms |
| p3 | massage timer | `05 02 00 00 02 00 00` | once; P3 query after 150 ms |
| p3 | light toggle | `05 02 00 02 00 00 00` | once |
| p3 | read alarm | `00 C0` | once |
| p3 | clock example | `07 04 1A 0B 1B 05 06 2D 1E` | local 2026-11-27 06:45:30 |
| p3 | alarm example | `07 05 BE 05 07 1E 00 01 00` | weekdays, memory A |
| p3 | cancel alarm example | `07 05 00 00 00 00 00 00 00` | twice, then clock at 100 ms |
<!-- /generated -->

#### Timing

Movement refreshes at the cadence above and releases with two driver STOPs.
Home Assistant completes release after cancellation on the original link.
Preset taps send once. Repeating the same P1 preset tap sends its separate
preset-stop word. Saving zero gravity or memory holds the save word for six
seconds; release ends refresh without an additional STOP frame. No save ACK
or hardware completion is implied.

P1 massage start writes the timer when needed, waits 100 ms, then sends foot,
head and wave levels twice each, with 100 ms between zone groups. Stop sends
the same duplicate groups at zero, foot first. The first timer-cycle click
retains the app's initial negative argument. The shared timer select directly
sets a named duration without cycling. P3 queries massage state after a step.

Alarm set/cancel writes twice, syncs the local clock after 100 ms and requests
an alarm read after 400 ms when the route offers one. Clock sync also runs on
connect. Home Assistant bounds read ownership to one second; only a reply to
that active read may send the app's one driver STOP. An unsolicited delayed
alarm reply cannot stop a later movement.

#### Notifications

P1 alarm replies have no header test, require ten bytes, and use signed time
fields. Its `FF` weekday reply means disabled even though an all-days write
uses that value. P2 recognizes `ED 80 03` alarms and retains previously selected
wake modes; P3 recognizes `A5 0C` and clears old modes. Short replies are
ignored safely. P2/P3 massage parsers retain the source's signed arithmetic and
show level and timer indicators. Those indicators are not measured countdowns.
No route reports measured motor position, battery or other bed sensors.

Raw route and alarm fields stay in diagnostics. State set by P1 commands is
assumed state, cleared on disconnect. No checksum validation, receive
reassembly, command ACK, authentication or negotiated capability mask is added.

#### Services

Use the standard movement, memory, clock-sync and `set_alarm` actions. Alarms
accept weekdays (Monday first in HA), next occurrence with no weekdays,
Memory A, Memory B or massage. P1 can combine massage with a memory wake;
P2/P3 accept a single wake action. Saving zero gravity also has a confirmation
button. Refresh bed alarm is a diagnostic button on routes with a read command.

#### Evidence

Based on PowersBedding 1.1.0 (2), `com.ore.powersbedding`.
Frozen literals and safe parser cases: `tests/fixtures/powersbedding/vectors.json`
and `tests/test_powersbedding_vectors.py`. Physical command acceptance,
programming duration, massage indicators and alarm behavior remain unverified.
