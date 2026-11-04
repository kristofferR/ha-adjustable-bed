# Okin N-frame

**Status:** ⚠️ Mixed: Okimat and the RF ECO BT stair lift are tested; Prodigy CE / CU170 is hardware-tested in [#368](https://github.com/kristofferR/ha-adjustable-bed/issues/368); DewertOkin, Customatic, the other Leggett profiles and the 40-bit profiles need testing. Each profile states its own status.

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), david_nagy, corne, PT, MarcusW and [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt)

This guide covers every bed that sends Okin N-frame command words. The 32-bit
profiles are Okimat handset tables, DewertOkin, the OKIN Smart Remote stair lift,
the Customatic apps and the Leggett & Platt Okin apps. The 40-bit profiles are
OKIN SmartBed CB24, Okin DOT, SIMMONS, OKIN SleepEase, the Sleepy's Elite legacy
CB25 dialect and the AdjustableM5X4 key selectors. The 96-bit profiles are the
Okin CST (CSTProtocol) products and the OKIN Bedding apps: Jordan's Serenity,
Jordan's Tranquil and Customatic Z-Series. The 64-bit format has its own guide
until it moves onto this codec: [Okin 64-Bit](okin-64bit.md).

## Known Models

| Profile | Models |
|---|---|
| [Okimat](#okimat) | Okimat beds, Lucid L600, Rize beds (II, Contempo, Bob, Sanctuary, Aviada, MF900, Resident), Glory, Tranquil, Jobs 賈伯斯, Nectar Motion, Customatic Demo, RF ECO BT bed receivers, other beds with Okin motors |
| [DewertOkin](#dewertokin) | A H Beard, Hankook Gallery, beds with the DewertOkin HE150 controller, DewertOkin Bluetooth RF-Gateway receivers; see [DewertOkin brands](#dewertokin-brands) |
| [RF ECO BT stair lift](#rf-eco-bt-stair-lift) | Elda BTH / RF ECO BT / MEGAMAT staircase from [#344](https://github.com/kristofferR/ha-adjustable-bed/issues/344); Device Information model `MEGAMAT MBZ`, advertising as `OKIN-050226` |
| [Customatic](#customatic-family) | Customatic Clarity, Jerome's C and Remedy bases |
| [Leggett Okin](#leggett-okin-family) | Leggett & Platt Prodigy Comfort Elite and similar control boxes, marked `LP BED CONTROL`; confirmed hardware DewertOkin CU170 |
| [OKIN SmartBed CB24](#okin-smartbed-cb24) | SmartBed by Okin receivers (Amada and other OKIN beds) with the CB24, CB24AB, CB27, CB27New, CB1221 or Dacheng profile |
| [Okin DOT](#okin-dot) | DewertOkin "DOT PROTOCOL" receivers for the RF1058, RF34 and RF6707 handsets |
| [SIMMONS](#simmons) | Beds controlled with the SIMMONS app, regular and inclined |
| [OKIN SleepEase](#okin-sleepease) | OKIN SleepEase / DoubleSleep / XiaoBao app models |
| [Sleepy's legacy CB25](#sleepys-legacy-cb25) | Sleepy's Elite BOX25 receivers whose Device Information manufacturer is not `star` |
| [AdjustableM5X4](#adjustablem5x4) | StarCode beds operated with the AdjustableM5X4 app |
| [Okin CST](#okin-cst) | Mattress Firm 900-O / Rize MF900, Rize Sanctuary, Resident, Aviada, Bob, Contempo, Rize II Carefree and Clarity, Support, Nectar Motion (Nectar Move) |
| [Jordan's Serenity](#jordans-serenity) | Beds controlled with the Jordan's Serenity app |
| [Jordan's Tranquil](#jordans-tranquil) | Beds controlled with the Jordan's Tranquil app |
| [Customatic Z-Series](#customatic-z-series) | Customatic Z-230 and Z-280 bases with the Z-Series app |

Customatic Z-Series beds use the separate [Customatic Z-Series](#customatic-z-series)
profile; Okimat, DewertOkin and the other controllers stay separate from the
Customatic app profiles.

## Apps

| Analyzed | App | Package ID | Profile |
|---|---|---|---|
| ✅ | [OKIN ComfortBed II-N](https://play.google.com/store/apps/details?id=com.ore.jalon.neworebeding) | `com.ore.jalon.neworebeding` | [Okimat](#okimat) |
| ✅ | [OKIN Comfort Bed](https://play.google.com/store/apps/details?id=com.ore.okincomfortbed) | `com.ore.okincomfortbed` | [Okimat](#okimat) |
| ✅ | [OKIN Smart Bed](https://play.google.com/store/apps/details?id=com.okin.bedding.smartbedwifi) | `com.okin.bedding.smartbedwifi` | [Okimat](#okimat), [OKIN SmartBed CB24](#okin-smartbed-cb24) |
| ✅ | Rize II | `com.okin.bedding.rizeii` | [Okimat](#okimat) |
| ✅ | Rize Resident | `com.okin.bedding.rizeResident` | [Okimat](#okimat), [Okin CST](#okin-cst) |
| ✅ | Glory | `com.okin.bedding.glory` | [Okimat](#okimat), [Customatic Z-Series](#customatic-z-series) |
| ✅ | Tranquil | `com.okin.bedding.tranquil` | [Okimat](#okimat), [Jordan's Tranquil](#jordans-tranquil) |
| ✅ | Jobs 賈伯斯 | `com.okin.bedding.jobs` | [Okimat](#okimat) |
| ✅ | Nectar Motion | `com.okin.bedding.nectarmotion` | [Okimat](#okimat) |
| ✅ | Support 挺你 | `com.okin.bedding.support` | [Okimat](#okimat) |
| ✅ | [OKIN Smart Remote / FurniMove](https://play.google.com/store/apps/details?id=com.okin.okinsmartcomfort) 2.2.0 (19) | `com.okin.okinsmartcomfort` | [Okimat](#okimat), [DewertOkin](#dewertokin), [RF ECO BT stair lift](#rf-eco-bt-stair-lift), [Okin DOT](#okin-dot) |
| ✅ | [Customatic Clarity](https://play.google.com/store/apps/details?id=com.okin.bedding.customaticclarity) 1.0.1 | `com.okin.bedding.customaticclarity` | [Customatic Clarity](#customatic-clarity) |
| ✅ | [Customatic Jerome's](https://play.google.com/store/apps/details?id=com.okin.bedding.customaticjeromes) 1.0.1 | `com.okin.bedding.customaticjeromes` | [Customatic Jerome's](#customatic-jeromes) |
| ✅ | [Customatic Remedy](https://play.google.com/store/apps/details?id=com.okin.bedding.customaticremedy) 1.0.1 | `com.okin.bedding.customaticremedy` | [Customatic Remedy](#customatic-remedy) |
| ✅ | [Prodigy 2L](https://play.google.com/store/apps/details?id=com.leggett.prodigy2L) 1.2 (15) | `com.leggett.prodigy2L` | [Prodigy 2L](#prodigy-2l) |
| ✅ | [Prodigy 2](https://play.google.com/store/apps/details?id=com.leggett.prodigy2) 2.2.0 (44) | `com.leggett.prodigy2` | [Prodigy 2](#prodigy-2) |
| ✅ | [Prodigy CE / Prodigy 4](https://play.google.com/store/apps/details?id=com.leggett.prodigy4) 1.2.0 (18) | `com.leggett.prodigy4` | [Prodigy CE](#prodigy-ce-prodigy-4) |
| ✅ | [U / Ultra Series](https://play.google.com/store/apps/details?id=com.leggett.useries) 2.1 (16) | `com.leggett.useries` | [U Series](#u-series) |
| ✅ | [SIMMONS](https://play.google.com/store/apps/details?id=com.okin.simmons) 1.12.9 (code 99) | `com.okin.simmons` | [SIMMONS](#simmons) |
| ✅ | [OKIN SleepEase / DoubleSleep](https://play.google.com/store/apps/details?id=com.okin.doublesleep) 1.2.24 (code 109) | `com.okin.doublesleep` | [OKIN SleepEase](#okin-sleepease) |
| ✅ | [MFRM Sleepy's Elite](https://play.google.com/store/apps/details?id=com.okin.bedding.sleepy) | `com.okin.bedding.sleepy` | [Sleepy's legacy CB25](#sleepys-legacy-cb25) |
| ✅ | [AdjustableM5X4](https://play.google.com/store/apps/details?id=com.starcode.abm5_4) 1.0.1 (3) | `com.starcode.abm5_4` | [AdjustableM5X4](#adjustablem5x4) |
| ✅ | [Rize Sanctuary](https://play.google.com/store/apps/details?id=com.okin.bedding.rizeSanctuary) 1.0.1 (2) | `com.okin.bedding.rizeSanctuary` | [Okin CST](#okin-cst) |
| ✅ | [Rize Aviada](https://play.google.com/store/apps/details?id=com.okin.bedding.rizeaviada) 1.0.1 (2) | `com.okin.bedding.rizeaviada` | [Okin CST](#okin-cst) |
| ✅ | [Rize Bob](https://play.google.com/store/apps/details?id=com.okin.bedding.rizebob) 1.0.1 (2) | `com.okin.bedding.rizebob` | [Okin CST](#okin-cst) |
| ✅ | [Rize Contempo](https://play.google.com/store/apps/details?id=com.okin.bedding.rizecontempo) 1.0.2 (3) | `com.okin.bedding.rizecontempo` | [Okin CST](#okin-cst) |
| ✅ | [Rize II Carefree](https://play.google.com/store/apps/details?id=com.okin.bedding.rizeiicarefree) 1.0.1 (2) | `com.okin.bedding.rizeiicarefree` | [Okin CST](#okin-cst) |
| ✅ | [Rize II Clarity](https://play.google.com/store/apps/details?id=com.okin.bedding.rizeiiclarity) 1.0.1 (2) | `com.okin.bedding.rizeiiclarity` | [Okin CST](#okin-cst) |
| ✅ | [Mattress Firm 900 - O / MFirm 900-O](https://play.google.com/store/apps/details?id=com.okin.bedding.rizemf900) 1.1.2 (4) | `com.okin.bedding.rizemf900` | [Okin CST](#okin-cst) |
| ✅ | [Support](https://play.google.com/store/apps/details?id=com.okin.bedding.support) 1.0.4 (5) | `com.okin.bedding.support` | [Okin CST](#okin-cst) |
| ✅ | [Nectar Motion](https://play.google.com/store/apps/details?id=com.okin.bedding.nectarmotion) 1.0.1 (2), Nectar Move profile | `com.okin.bedding.nectarmotion` | [Okin CST](#okin-cst) |
| ✅ | [Jordan's Serenity](https://play.google.com/store/apps/details?id=com.okin.bedding.serenity) 1.0.1 (code 2) | `com.okin.bedding.serenity` | [Jordan's Serenity](#jordans-serenity) |

Beds controlled with FurniMove handset IDs normally use the explicit
[FurniMove / OKIN Smart Remote](furnimove.md) app profile.

## Features

| Feature | Okimat | DewertOkin | RF ECO BT stair | Customatic | Leggett Okin |
|---|---|---|---|---|---|
| Motor control | ✅ Per handset | ✅ Head, feet | ✅ One stair actuator | ✅ Back, legs; Remedy adds lumbar | ✅ Head, feet, plus pillow and/or lumbar per app |
| Simultaneous movement | ⚠️ Integration only: held motors combine (see [Controls](#okimat)) | ❌ | ❌ | ✅ (`customatic_move_simultaneously`) | ✅ Held motors combine |
| Position feedback | Some receivers (FFE4 required) | ❌ | ❌ | ❌ | ❌ |
| Flat | ✅ Most handsets | ✅ | ❌ | ✅ (Jerome's also Restored Flat) | ✅ Held button |
| Other presets | Zero-G, anti-snore / quiet sleep where the handset has them | Zero-G, TV, Quiet Sleep | ❌ | Named memory-page controls | Snore |
| Memory presets | ✅ 1-4 slots per handset, save key | ✅ 2 slots, no save | ❌ | ❌ Numbered slots; ✅ named held controls | ✅ Prodigy: four favorites incl. fixed Snore; U Series: two held memory controls and SET |
| Massage | ✅ Handsets with massage keys | ✅ Wave, head, foot, off | ❌ | ❌ | ✅ Head/foot up/down, on/off toggle, wave step |
| Under-bed lights | ✅ Toggle, handsets with a light key | ✅ Toggle | ❌ | ✅ Clarity/Remedy toggle; ❌ Jerome's | ✅ Toggle; Prodigy CE adds a notification-backed light entity |
| Sync, child lock | ✅ Handsets with those keys | ❌ | ❌ | ❌ | ❌ |
| Sleep and alarm timers | ❌ | ❌ | ❌ | ❌ | ✅ Native timers |
| Control mode | ❌ | ❌ | ❌ | ❌ | ⚠️ Prodigy profiles; press-and-hold refused on Prodigy CE |
| Device Information | ❌ | ❌ | ❌ | ✅ Five diagnostic sensors | ✅ Diagnostics |
| BLE pairing | ✅ Required | ❌ | ✅ Requested | ❌ | ✅ Required |

The 40-bit profiles:

| Feature | CB24 | DOT | SIMMONS | SleepEase | Sleepy's legacy CB25 | AdjustableM5X4 |
|---|---|---|---|---|---|---|
| Motor control | ✅ Head, feet | ✅ Two motors per handset | ✅ Back, legs | ✅ Head, foot, lumbar, headrest, hips (P1, P2) | ✅ Head, foot, lumbar, neck | ✅ Head, foot, union |
| Position feedback | ❌ | ❌ | ❌ | ❌ | ✅ 0-100 % | ❌ |
| Presets | ✅ Flat, Zero-G, Lounge, TV, Anti-snore | ✅ Flat; Zero-G, Quiet Sleep, Anti-snore on RF1058 | ✅ Flat; Zero-G, TV/PC, Anti-snore on a regular bed | ✅ Held (P1) or one-shot (P2) recalls | ✅ Flat, TV, Zero-G, Anti-snore, Lounge | ✅ Flat, TV, Lounge, Zero-G, Anti-snore |
| Memory presets | ✅ 3 slots, no save | ✅ RF1058 and RF34 codes, tap to recall | ✅ Custom Mode, saved by a 5.5 s hold | ✅ Two recalls | ✅ 2 slots with save | ✅ Memory A, named saves and reset |
| Massage | ✅ | ✅ RF1058 codes | ❌ | ✅ | ✅ | ✅ Behind the massage-on gate |
| Under-bed lights | ✅ Toggle (CBNew: on/off) | ✅ Toggle | ✅ | ✅ Toggle | ✅ | ✅ Per selector |
| Alarms and clock | ❌ | ❌ | ✅ Two slots, clock sync | ✅ | ❌ | ❌ |
| Single-address sides | ✅ Legacy CB24 selector | ❌ | ❌ | ❌ | ❌ | ❌ |
| BLE pairing | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

The 96-bit profiles:

| Feature | Okin CST | Jordan's Serenity | Jordan's Tranquil | Customatic Z-Series |
|---|---|---|---|---|
| Motor control | ✅ Head, foot; lumbar on Aviada, Contempo, MF900 and Support | ✅ Head, foot, remote selectors 4 and 5 | ✅ Head, foot, remote selectors 4 and 5 | ✅ Head, foot; Z-230 head and foot together, Z-280 selector 5 |
| Presets | ✅ Flat, Zero-G, Anti-snore; Lounge, Incline, Reading per product | ✅ Flat, Zero-G, TV, Leisure, Anti-snore | ✅ Flat, Zero-G, Lounge, Anti-snore | ✅ Flat, Zero-G, TV, Anti-snore |
| Memory presets | ✅ One to four per product, with save | ✅ M1, M2 with save | ✅ M1, M2 with save | ✅ M1 (Z-230) or M1, M2 (Z-280), with save |
| Massage | ⚠️ Per product | ✅ Head, foot, mode, timer, waves, off | ✅ Head, foot, mode, timer, waves, off | ✅ Toggle, mode, timer; zones or intensity per page |
| Under-bed lights | ✅ Every product except Resident | ✅ Toggle, on, off | ✅ Toggle, on, off | ✅ Toggle |
| Alarm and clock | ❌ | ❌ | ❌ | ✅ CST13/CST14 receivers |
| BLE pairing | ⚠️ Most products | ❌ | ❌ | ❌ |

## Choosing a profile

Detection suggests Okimat for the Okin service, DewertOkin by device name and
Leggett Okin by Leggett names; each profile's Setup lists its rules. The stair
lift and the Customatic apps are explicit choices, and Leggett Okin entries
choose their app. CB24 is detected from the OKIN manufacturer ID, DOT from the
Nordic UART write characteristic on an Okin handset entry; SIMMONS, SleepEase,
Sleepy's Elite and AdjustableM5X4 are explicit app choices.

<!-- generated:okin-nframe-profiles -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

### Profile summary

| Profile | Key | Bed types | Word | Frame | Write | Axes | Memory |
|---|---|---|---|---|---|---|---|
| Okimat handset table | `okimat` | `okimat`, `okin_uuid` | 32-bit | plain; RF-Gateway envelope when detected | with response | handset table | handset table |
| DewertOkin | `dewertokin` | `dewertokin`, `okin_handle` | 32-bit | plain; RF-Gateway envelope when detected | with response | head, feet | 2 |
| OKIN Smart Remote RF ECO BT stair lift | `okin_rf_eco_bt` | `okin_rf_eco_bt` | 32-bit | plain frame | with response | stair | 0 |
| Customatic Clarity | `clarity` | `customatic_clarity` | 32-bit | plain frame | from the characteristic's properties | back, legs | 0 |
| Customatic Jerome's | `jeromes` | `customatic_jeromes` | 32-bit | plain frame | from the characteristic's properties | back, legs | 0 |
| Customatic Remedy | `remedy` | `customatic_remedy` | 32-bit | plain frame | from the characteristic's properties | back, legs, lumbar | 0 |
| Prodigy 2L | `prodigy2l` | `leggett_okin`, `leggett_platt` | 32-bit | plain (R1) or envelope (R0), by selector characteristic | without response | head, feet, lumbar | 4 |
| Prodigy 2 | `prodigy2` | `leggett_okin`, `leggett_platt` | 32-bit | plain (R1) or envelope (R0), by selector characteristic | without response | head, feet, pillow | 4 |
| Prodigy CE | `prodigy4` | `leggett_okin`, `leggett_platt` | 32-bit | plain (R1) or envelope (R0), by selector characteristic | without response | head, feet, pillow, lumbar | 4 |
| U Series | `useries` | `leggett_okin`, `leggett_platt` | 32-bit | plain (R1) or envelope (R0), by selector characteristic | without response | head, feet, pillow | 2 |
| OKIN SmartBed CB24 | `okin_cb24` | `okin_cb24` | 40-bit | plain frame | without response | head, feet | 3 |
| DewertOkin DOT handset table | `okin_dot` | `okin_dot` | 40-bit | plain frame | without response | handset table | handset table |
| SIMMONS SmartBed names | `simmons_smartbed` | `simmons` | 40-bit | plain frame | without response | back, legs | 1 |
| SIMMONS OKIN names | `simmons_okin` | `simmons` | 40-bit | Keeson E6 frame; inclined keys plain | with response | back, legs | 1 |
| OKIN SleepEase | `doublesleep` | `doublesleep` | 40-bit | plain frame | without response | head, feet, lumbar, pillow, hip | 2 |
| Sleepy's Elite legacy CB25 | `sleepys_box25` | `sleepys_box25` | 40-bit | plain frame | without response | head, foot, lumbar, neck | 2 |
| AdjustableM5X4 none, BOX24, BOX1221, BOX2422, BOX2442 | `starcode_abm5_4` | `starcode_abm5_4` | 40-bit | plain frame | without response | head, foot | 1 |
| AdjustableM5X4 BOX3633 | `starcode_abm5_4_box3633` | `starcode_abm5_4` | 40-bit | plain frame | without response | head, foot | 1 |
| AdjustableM5X4 BOX25 | `starcode_abm5_4_box25` | `starcode_abm5_4` | 40-bit | plain frame | without response | head, foot | 1 |
| AdjustableM5X4 BOX15 | `starcode_abm5_4_box15` | `starcode_abm5_4` | 40-bit | plain frame | without response | head, foot | 1 |
| AdjustableM5X4 BOX1220 | `starcode_abm5_4_box1220` | `starcode_abm5_4` | 40-bit | plain frame | without response | head, foot | 1 |
| Rize Sanctuary | `cst_sanctuary` | `okin_cst` | 96-bit | plain frame | with response | head, feet | 2 |
| Rize Resident | `cst_resident` | `okin_cst` | 96-bit | plain frame | with response | head, feet | 4 |
| Rize Aviada | `cst_aviada` | `okin_cst` | 96-bit | plain frame | with response | head, feet, lumbar | 3 |
| Rize Bob | `cst_bob` | `okin_cst` | 96-bit | plain frame | with response | head, feet | 2 |
| Rize Contempo | `cst_contempo` | `okin_cst` | 96-bit | plain frame | with response | head, feet, lumbar | 3 |
| Rize II Carefree | `cst_carefree` | `okin_cst` | 96-bit | plain frame | with response | head, feet | 1 |
| Rize II Clarity | `cst_clarity` | `okin_cst` | 96-bit | plain frame | with response | head, feet | 3 |
| Rize MF900 | `cst_mf900` | `okin_cst` | 96-bit | plain frame | with response | head, feet, lumbar | 3 |
| Support | `cst_support` | `okin_cst` | 96-bit | plain frame | with response | head, feet, lumbar | 3 |
| Nectar Move | `cst_nectar_move` | `okin_cst` | 96-bit | plain frame | with response | head, feet | 2 |
| Jordan's Serenity | `serenity` | `serenity` | 96-bit | plain frame | from the characteristic's properties | head, feet | 2 |
| Jordan's Tranquil | `tranquil` | `tranquil` | 96-bit | plain frame | from the characteristic's properties | head, feet | 2 |
| Customatic Z-230 | `zseries_z230` | `customatic_zseries` | 96-bit | plain frame | from the characteristic's properties | head, feet | 1 |
| Customatic Z-280 | `zseries_z280` | `customatic_zseries` | 96-bit | plain frame | from the characteristic's properties | head, feet | 2 |

### Hold and release timing

| Profile | Hold refresh | Repeats | Release |
|---|---|---|---|
| Okimat handset table | entry pulse delay | entry pulse count | 1 STOP |
| DewertOkin | entry pulse delay | entry pulse count | 1 STOP |
| OKIN Smart Remote RF ECO BT stair lift | 100 ms | entry pulse count | none (refresh ends) |
| Customatic Clarity | 120 ms | entry pulse count | 1 STOP, 100 ms after the last write |
| Customatic Jerome's | 120 ms | entry pulse count | 1 STOP, 100 ms after the last write |
| Customatic Remedy | 120 ms | entry pulse count | 1 STOP, 100 ms after the last write |
| Prodigy 2L | 100 ms | entry pulse count | 4 STOP at 100 ms |
| Prodigy 2 | 100 ms | entry pulse count | 4 STOP at 100 ms |
| Prodigy CE | 100 ms | entry pulse count | 4 STOP at 100 ms |
| U Series | 100 ms | entry pulse count | 4 STOP at 100 ms |
| OKIN SmartBed CB24 | entry pulse delay | entry pulse count | 1 STOP |
| DewertOkin DOT handset table | entry pulse delay | entry pulse count | 1 STOP |
| SIMMONS SmartBed names | 300 ms | entry pulse count | 2 STOP at 300 ms, 100 ms after the last write |
| SIMMONS OKIN names | 300 ms | entry pulse count | 2 STOP at 300 ms, 100 ms after the last write |
| OKIN SleepEase | 300 ms | entry pulse count | 1 STOP |
| Sleepy's Elite legacy CB25 | entry pulse delay | entry pulse count | 1 STOP |
| AdjustableM5X4 none, BOX24, BOX1221, BOX2422, BOX2442 | 100 ms | entry pulse count | 1 STOP |
| AdjustableM5X4 BOX3633 | 100 ms | entry pulse count | 1 STOP |
| AdjustableM5X4 BOX25 | 100 ms | entry pulse count | 1 STOP |
| AdjustableM5X4 BOX15 | n/a | n/a | moves with its own frames |
| AdjustableM5X4 BOX1220 | n/a | n/a | moves with its own frames |
| Rize Sanctuary | entry pulse delay | entry pulse count | 2 STOP at 100 ms, 100 ms after the last write |
| Rize Resident | entry pulse delay | entry pulse count | 2 STOP at 100 ms, 100 ms after the last write |
| Rize Aviada | entry pulse delay | entry pulse count | 2 STOP at 100 ms, 100 ms after the last write |
| Rize Bob | entry pulse delay | entry pulse count | 2 STOP at 100 ms, 100 ms after the last write |
| Rize Contempo | entry pulse delay | entry pulse count | 2 STOP at 100 ms, 100 ms after the last write |
| Rize II Carefree | entry pulse delay | entry pulse count | 2 STOP at 100 ms, 100 ms after the last write |
| Rize II Clarity | entry pulse delay | entry pulse count | 2 STOP at 100 ms, 100 ms after the last write |
| Rize MF900 | entry pulse delay | entry pulse count | 2 STOP at 100 ms, 100 ms after the last write |
| Support | entry pulse delay | entry pulse count | 2 STOP at 100 ms, 100 ms after the last write |
| Nectar Move | 100 ms | entry pulse count | 2 STOP at 100 ms, 100 ms after the last write |
| Jordan's Serenity | 100 ms | entry pulse count | 2 STOP at 100 ms, 100 ms after the last write |
| Jordan's Tranquil | 100 ms | entry pulse count | 2 STOP at 100 ms, 100 ms after the last write |
| Customatic Z-230 | 100 ms | entry pulse count | 2 STOP at 100 ms, 100 ms after the last write |
| Customatic Z-280 | 100 ms | entry pulse count | 2 STOP at 100 ms, 100 ms after the last write |

Entry pulse settings are the configured motor pulse count and delay.

### One-shot timing

| Profile | Presets and recall | Memory recall | Memory save | Sync, child lock | Light, massage | Control mode |
|---|---|---|---|---|---|---|
| Okimat handset table | 100 × 300 ms, 1 STOP | 100 × 300 ms, 1 STOP | 10 × 200 ms, no STOP (or the handset's hold) | 60 × 100 ms, 1 STOP | once, no STOP | n/a |
| DewertOkin | 100 × 300 ms, 1 STOP | 100 × 300 ms, 1 STOP | n/a | n/a | once, no STOP | n/a |
| OKIN Smart Remote RF ECO BT stair lift | n/a | n/a | n/a | n/a | n/a | n/a |
| Customatic Clarity | once, no STOP | once, no STOP | n/a | n/a | once, no STOP | n/a |
| Customatic Jerome's | 3 × 0 ms, no STOP | 3 × 0 ms, no STOP | n/a | n/a | n/a | n/a |
| Customatic Remedy | once, no STOP | once, no STOP | n/a | n/a | once, no STOP | n/a |
| Prodigy 2L | 10 × 100 ms, no STOP | 10 × 100 ms, no STOP | n/a | n/a | once, then 100 ms, 4 STOP | 55 × 100 ms, 1 STOP |
| Prodigy 2 | 10 × 100 ms, no STOP | 10 × 100 ms, no STOP | n/a | n/a | once, then 100 ms, 4 STOP | 55 × 100 ms, 1 STOP |
| Prodigy CE | 10 × 100 ms, no STOP | 10 × 100 ms, no STOP | n/a | n/a | once, then 100 ms, 4 STOP | 55 × 100 ms, 1 STOP |
| U Series | 10 × 100 ms, no STOP | 10 × 100 ms, no STOP | n/a | n/a | once, then 100 ms, 4 STOP | n/a |
| OKIN SmartBed CB24 | once, no STOP | once, no STOP | n/a | n/a | once, no STOP | n/a |
| DewertOkin DOT handset table | 100 × 300 ms, 1 STOP | once, 1 STOP | 10 × 200 ms, no STOP (or the handset's hold) | 60 × 100 ms, 1 STOP | once, no STOP | n/a |
| SIMMONS SmartBed names | once, 2 STOP | once, 2 STOP | n/a | n/a | once, 2 STOP | n/a |
| SIMMONS OKIN names | once, 2 STOP | once, 2 STOP | n/a | n/a | once, 2 STOP | n/a |
| OKIN SleepEase | n/a | n/a | n/a | n/a | n/a | n/a |
| Sleepy's Elite legacy CB25 | 3 × 100 ms, 1 STOP | 3 × 100 ms, 1 STOP | 110 × 100 ms, no STOP | n/a | n/a | n/a |
| AdjustableM5X4 none, BOX24, BOX1221, BOX2422, BOX2442 | n/a | n/a | n/a | n/a | n/a | n/a |
| AdjustableM5X4 BOX3633 | n/a | n/a | n/a | n/a | n/a | n/a |
| AdjustableM5X4 BOX25 | n/a | n/a | n/a | n/a | n/a | n/a |
| AdjustableM5X4 BOX15 | n/a | n/a | n/a | n/a | n/a | n/a |
| AdjustableM5X4 BOX1220 | n/a | n/a | n/a | n/a | n/a | n/a |
| Rize Sanctuary | 6 × 100 ms, 2 STOP | 6 × 100 ms, 2 STOP | n/a | n/a | 6 × 100 ms, 2 STOP | n/a |
| Rize Resident | 6 × 100 ms, 2 STOP | 6 × 100 ms, 2 STOP | n/a | n/a | 6 × 100 ms, 2 STOP | n/a |
| Rize Aviada | 6 × 100 ms, 2 STOP | 6 × 100 ms, 2 STOP | n/a | n/a | 6 × 100 ms, 2 STOP | n/a |
| Rize Bob | 6 × 100 ms, 2 STOP | 6 × 100 ms, 2 STOP | n/a | n/a | 6 × 100 ms, 2 STOP | n/a |
| Rize Contempo | 6 × 100 ms, 2 STOP | 6 × 100 ms, 2 STOP | n/a | n/a | 6 × 100 ms, 2 STOP | n/a |
| Rize II Carefree | 6 × 100 ms, 2 STOP | 6 × 100 ms, 2 STOP | n/a | n/a | n/a | n/a |
| Rize II Clarity | 6 × 100 ms, 2 STOP | 6 × 100 ms, 2 STOP | n/a | n/a | 6 × 100 ms, 2 STOP | n/a |
| Rize MF900 | 6 × 100 ms, 2 STOP | 6 × 100 ms, 2 STOP | n/a | n/a | 6 × 100 ms, 2 STOP | n/a |
| Support | 6 × 100 ms, 2 STOP | 6 × 100 ms, 2 STOP | n/a | n/a | 6 × 100 ms, 2 STOP | n/a |
| Nectar Move | once, 2 STOP | once, 2 STOP | n/a | n/a | n/a | n/a |
| Jordan's Serenity | held to its deadline, 2 STOP | held to its deadline, 2 STOP | held to its deadline, 2 STOP | n/a | held to its deadline, 2 STOP | n/a |
| Jordan's Tranquil | held to its deadline, 2 STOP | held to its deadline, 2 STOP | held to its deadline, 2 STOP | n/a | held to its deadline, 2 STOP | n/a |
| Customatic Z-230 | held to its deadline, 2 STOP | held to its deadline, 2 STOP | held to its deadline, 2 STOP | n/a | held to its deadline, 2 STOP | n/a |
| Customatic Z-280 | held to its deadline, 2 STOP | held to its deadline, 2 STOP | held to its deadline, 2 STOP | n/a | held to its deadline, 2 STOP | n/a |

Leggett Okin profiles also stream Flat for 30000 ms and program a favorite by
holding the store key 5000 ms, then the slot 2000 ms. Customatic named memory
controls hold 2700 ms with no STOP. SIMMONS saves Custom Mode by holding its
recall key 5500 ms. AdjustableM5X4 presets and recalls are held keys on its
refresh; it streams Flat for 600 ms and saves or resets for 6000 ms. SleepEase P1
presets are held keys on its refresh too. The OKIN Bedding apps hold every action
to its own deadline, saves for 5000 ms; see their profiles.
<!-- /generated -->

### Aliases

Bed types that build the same controller over the same profile with the same
default timing, so they send identical bytes. They stay separate bed types so
existing entries keep their identities; the
[protocol inventory](../design/protocol-inventory.md) proves the equality by capture.

| Bed type | Same as | Profile |
|----------|---------|---------|
| `okimat` | `okin_uuid` | [Okimat](#okimat) |
| `dewertokin` | `okin_handle` | [DewertOkin](#dewertokin) |
| `leggett_platt` with variant `okin` | `leggett_okin` | [Leggett Okin family](#leggett-okin-family) |

`okimat`, `dewertokin` and `leggett_platt` are kept for existing entries and
are not offered in the bed-type list.

## Wire codec

Implemented once in `custom_components/adjustable_bed/codec/okin_nframe.py`.
Profiles (`profiles/okin_nframe.py`) decide which words an app sends and how it
times them. Every frame table in this section is generated from the codec.

### Transports

<!-- generated:okin-nframe-transports -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Role | UUID | Used by |
|---|---|---|
| Service | `62741523-52f9-8864-b1ab-3b3a8d65950b` | All profiles |
| Write | `62741525-52f9-8864-b1ab-3b3a8d65950b` | All profiles |
| Position notify | `0000ffe4-0000-1000-8000-00805f9b34fb` | Okimat (receivers that expose it) |
| Status notify | `62741625-52f9-8864-b1ab-3b3a8d65950b` | Leggett Okin |
| Revision selector | `00001721-0000-1000-8000-00805f9b34fb` | Leggett Okin (presence selects R1) |
| Settings write | `90311625-25fa-3346-12ef-3cfb7a2556ac` | Leggett Okin Prodigy profiles |
| Settings notify | `90311725-25fa-3346-12ef-3cfb7a2556ac` | Leggett Okin Prodigy profiles |
| Service | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | 40-bit profiles |
| Write | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | 40-bit profiles |
| Notify | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | SIMMONS, SleepEase, Sleepy's, AdjustableM5X4 |

The settings channel opens with `01 02` after subscribing. SIMMONS also accepts
FFE5/FFE9 with FFE0/FFE4, and AdjustableM5X4 two more transports; see their
profiles.
<!-- /generated -->

Numeric GATT handles vary by device and firmware, so every profile writes by
characteristic UUID. Issue [#394](https://github.com/kristofferR/ha-adjustable-bed/issues/394)
reported a bed whose write characteristic was handle `0x000d` while `0x0013`
belonged to another attribute.

### Framing and checksum

**Frame:** `N 02 <N-byte command word, big-endian>`, so a frame is `N + 2` bytes.
The 32-bit profiles use `N = 4`, giving six bytes. The 96-bit CST profiles use
`N = 12`: two independently routed 32-bit fields, primary then secondary, and 32
zero bits, fourteen bytes in all (`codec.frame96()`). The app chooses the field
per action, so a key's word records its field. The 40-bit profiles use
`N = 5`: the 32-bit key word, then one selector byte, seven bytes in all
(`codec.frame40()`). The selector picks a legacy CB24 bed side (`AA` for A,
`BB` for B) and is `00` everywhere else. The codec also builds the 48-, 64- and
96-bit widths; Sleepy's legacy CB25 and AdjustableM5X4 send a few 64-bit
`08 02` frames. There is no checksum, sequence number or authentication payload.

**Other frames of the 40-bit routes:** two-byte `00 <code>` requests
(`codec.request()`), 6-byte `04 E0 <parameter> <value> <value2> 00` setting
frames (`codec.extended()`) and 5-byte `03 F0 <axis> <target> 00` position
targets (`codec.position_target()`). What each one asks for is profile data.
SIMMONS OKIN names carry the same 32-bit masks in a Keeson E6 frame,
`E6 FE 16 <word, little-endian> 00 <checksum>`, built by `codec/keeson.py`.

**Command word:** a bit mask of held keys. Keys held together are one frame with
several bits set, and the zero word releases every key (STOP).

**RF-Gateway envelope (revision 0):** `E5 FE 16 <command word> <checksum>`, eight
bytes. The checksum is the inverted low byte of the sum of the first seven bytes,
so all eight bytes sum to `0xFF`. DewertOkin RF-Gateway receivers and Leggett
boxes without the revision selector take this envelope; the words are the same.

### Command encoders

The words below are profile data, framed by `codec.frame()` or `codec.frame40()`
and, where a profile can use it, `codec.gateway_frame()`. Okimat and DOT words
come from the selected handset table; see
[Okimat handset keys](#okimat-handset-keys).

<!-- generated:okin-nframe-keys -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

#### DewertOkin keys

| Command | Word | Frame | Envelope (R0) |
|---|---|---|---|
| Head up | `0x00000001` | `04 02 00 00 00 01` | `E5 FE 16 00 00 00 01 05` |
| Head down | `0x00000002` | `04 02 00 00 00 02` | `E5 FE 16 00 00 00 02 04` |
| Feet up | `0x00000004` | `04 02 00 00 00 04` | `E5 FE 16 00 00 00 04 02` |
| Feet down | `0x00000008` | `04 02 00 00 00 08` | `E5 FE 16 00 00 00 08 FE` |
| Flat | `0x10000000` | `04 02 10 00 00 00` | `E5 FE 16 10 00 00 00 F6` |
| Zero-G | `0x00004000` | `04 02 00 00 40 00` | `E5 FE 16 00 00 40 00 C6` |
| TV | `0x00003000` | `04 02 00 00 30 00` | `E5 FE 16 00 00 30 00 D6` |
| Anti-snore / Snore | `0x00008000` | `04 02 00 00 80 00` | `E5 FE 16 00 00 80 00 86` |
| Memory 1 | `0x00001000` | `04 02 00 00 10 00` | `E5 FE 16 00 00 10 00 F6` |
| Memory 2 | `0x00002000` | `04 02 00 00 20 00` | `E5 FE 16 00 00 20 00 E6` |
| Wave massage | `0x80000000` | `04 02 80 00 00 00` | `E5 FE 16 80 00 00 00 86` |
| Head massage | `0x00000800` | `04 02 00 00 08 00` | `E5 FE 16 00 00 08 00 FE` |
| Foot massage | `0x00000400` | `04 02 00 00 04 00` | `E5 FE 16 00 00 04 00 02` |
| Massage off | `0x02000000` | `04 02 02 00 00 00` | `E5 FE 16 02 00 00 00 04` |
| Under-bed light toggle | `0x00020000` | `04 02 00 02 00 00` | `E5 FE 16 00 02 00 00 04` |
| STOP / release | `0x00000000` | `04 02 00 00 00 00` | `E5 FE 16 00 00 00 00 06` |

#### RF ECO BT keys

| Command | Word | Frame |
|---|---|---|
| Stair out (open) | `0x00000001` | `04 02 00 00 00 01` |
| Stair in (close) | `0x00000002` | `04 02 00 00 00 02` |

The stair profile has no STOP: release ends the refresh.

#### Customatic keys

| Command | Word | Profiles | Frame |
|---|---|---|---|
| Back up | `0x00000001` | all | `04 02 00 00 00 01` |
| Back down | `0x00000002` | all | `04 02 00 00 00 02` |
| Legs up | `0x00000004` | all | `04 02 00 00 00 04` |
| Legs down | `0x00000008` | all | `04 02 00 00 00 08` |
| Lumbar up | `0x00000010` | Customatic Remedy | `04 02 00 00 00 10` |
| Lumbar down | `0x00000020` | Customatic Remedy | `04 02 00 00 00 20` |
| Memory page: Flat | `0x08000000` | Customatic Clarity, Customatic Remedy | `04 02 08 00 00 00` |
| Memory page: ZG | `0x00001000` | Customatic Clarity, Customatic Remedy | `04 02 00 00 10 00` |
| Memory page: ANTI | `0x00008000` | Customatic Clarity, Customatic Remedy | `04 02 00 00 80 00` |
| Memory page: Program | `0x80000000` | Customatic Clarity, Customatic Remedy | `04 02 80 00 00 00` |
| Memory page: Incline | `0x00004000` | Customatic Clarity, Customatic Remedy | `04 02 00 00 40 00` |
| Under-bed light toggle | `0x00020000` | Customatic Clarity, Customatic Remedy | `04 02 00 02 00 00` |
| Flat | `0x08000000` | Customatic Clarity, Customatic Remedy | `04 02 08 00 00 00` |
| Flat | `0x10000000` | Customatic Jerome's | `04 02 10 00 00 00` |
| Restored Flat | `0x08000000` | Customatic Jerome's | `04 02 08 00 00 00` |
| STOP / release | `0x00000000` | all | `04 02 00 00 00 00` |

#### Leggett Okin keys

| Command | Word | Profiles | Frame | Envelope (R0) |
|---|---|---|---|---|
| Head up | `0x00000001` | all | `04 02 00 00 00 01` | `E5 FE 16 00 00 00 01 05` |
| Head down | `0x00000002` | all | `04 02 00 00 00 02` | `E5 FE 16 00 00 00 02 04` |
| Feet up | `0x00000004` | all | `04 02 00 00 00 04` | `E5 FE 16 00 00 00 04 02` |
| Feet down | `0x00000008` | all | `04 02 00 00 00 08` | `E5 FE 16 00 00 00 08 FE` |
| Pillow up | `0x00000010` | Prodigy 2, Prodigy CE, U Series | `04 02 00 00 00 10` | `E5 FE 16 00 00 00 10 F6` |
| Pillow down | `0x00000020` | Prodigy 2, Prodigy CE, U Series | `04 02 00 00 00 20` | `E5 FE 16 00 00 00 20 E6` |
| Lumbar up | `0x00000040` | Prodigy 2L, Prodigy CE | `04 02 00 00 00 40` | `E5 FE 16 00 00 00 40 C6` |
| Lumbar down | `0x00000080` | Prodigy 2L, Prodigy CE | `04 02 00 00 00 80` | `E5 FE 16 00 00 00 80 86` |
| Flat | `0x08000000` | all | `04 02 08 00 00 00` | `E5 FE 16 08 00 00 00 FE` |
| Memory 1 | `0x00001000` | all | `04 02 00 00 10 00` | `E5 FE 16 00 00 10 00 F6` |
| Memory 2 | `0x00002000` | all | `04 02 00 00 20 00` | `E5 FE 16 00 00 20 00 E6` |
| Memory 3 | `0x00004000` | Prodigy 2L, Prodigy 2, Prodigy CE | `04 02 00 00 40 00` | `E5 FE 16 00 00 40 00 C6` |
| Memory 4 | `0x00008000` | Prodigy 2L, Prodigy 2, Prodigy CE | `04 02 00 00 80 00` | `E5 FE 16 00 00 80 00 86` |
| Anti-snore / Snore | `0x00004000` | all | `04 02 00 00 40 00` | `E5 FE 16 00 00 40 00 C6` |
| Memory store (arm) | `0x00010000` | all | `04 02 00 01 00 00` | `E5 FE 16 00 01 00 00 05` |
| Head massage up | `0x00000800` | all | `04 02 00 00 08 00` | `E5 FE 16 00 00 08 00 FE` |
| Head massage down | `0x00800000` | all | `04 02 00 80 00 00` | `E5 FE 16 00 80 00 00 86` |
| Foot massage up | `0x00000400` | all | `04 02 00 00 04 00` | `E5 FE 16 00 00 04 00 02` |
| Foot massage down | `0x01000000` | all | `04 02 01 00 00 00` | `E5 FE 16 01 00 00 00 05` |
| Massage on/off | `0x00000100` | all | `04 02 00 00 01 00` | `E5 FE 16 00 00 01 00 05` |
| Massage wave mode step | `0x10000000` | all | `04 02 10 00 00 00` | `E5 FE 16 10 00 00 00 F6` |
| Under-bed light toggle | `0x00020000` | all | `04 02 00 02 00 00` | `E5 FE 16 00 02 00 00 04` |
| Control mode: press-and-hold | `0x08010000` | Prodigy 2L, Prodigy 2, Prodigy CE | `04 02 08 01 00 00` | `E5 FE 16 08 01 00 00 FD` |
| Control mode: press-and-release | `0x01800000` | Prodigy 2L, Prodigy 2, Prodigy CE | `04 02 01 80 00 00` | `E5 FE 16 01 80 00 00 85` |
| Sleep timer cancel | `0xFF200000` | all | `04 02 FF 20 00 00` | `E5 FE 16 FF 20 00 00 E7` |
| Alarm cancel / stop | `0xFD000000` | U Series | `04 02 FD 00 00 00` | `E5 FE 16 FD 00 00 00 09` |
| Alarm cancel / stop | `0xFD200000` | Prodigy 2L, Prodigy 2, Prodigy CE | `04 02 FD 20 00 00` | `E5 FE 16 FD 20 00 00 E9` |
| CU170 stop (DUMMY) | `0x00040000` | Prodigy CE | `04 02 00 04 00 00` | `E5 FE 16 00 04 00 00 02` |
| STOP / release | `0x00000000` | all | `04 02 00 00 00 00` | `E5 FE 16 00 00 00 00 06` |

#### CB24 keys

| Command | Word | Frame |
|---|---|---|
| Head up | `0x0000000001` | `05 02 00 00 00 01 00` |
| Head down | `0x0000000002` | `05 02 00 00 00 02 00` |
| Feet up | `0x0000000004` | `05 02 00 00 00 04 00` |
| Feet down | `0x0000000008` | `05 02 00 00 00 08 00` |
| Flat | `0x0008000000` | `05 02 08 00 00 00 00` |
| Zero-G | `0x0000001000` | `05 02 00 00 10 00 00` |
| Memory 1 | `0x0000002000` | `05 02 00 00 20 00 00` |
| Memory 2 | `0x0000004000` | `05 02 00 00 40 00 00` |
| Anti-snore / Snore | `0x0000008000` | `05 02 00 00 80 00 00` |
| Memory 3 | `0x0000010000` | `05 02 00 01 00 00 00` |
| Under-bed light toggle | `0x0000020000` | `05 02 00 02 00 00 00` |
| Head massage up | `0x0000000800` | `05 02 00 00 08 00 00` |
| Head massage down | `0x0000800000` | `05 02 00 80 00 00 00` |
| Foot massage up | `0x0000000400` | `05 02 00 00 04 00 00` |
| Foot massage down | `0x0001000000` | `05 02 01 00 00 00 00` |
| Massage toggle | `0x0000000100` | `05 02 00 00 01 00 00` |
| Massage off | `0x0002000000` | `05 02 02 00 00 00 00` |
| Massage wave mode step | `0x0010000000` | `05 02 10 00 00 00 00` |
| Massage intensity up | `0x0000000C00` | `05 02 00 00 0C 00 00` |
| Massage intensity down | `0x0001800000` | `05 02 01 80 00 00 00` |
| STOP / release | `0x00000000` | `05 02 00 00 00 00 00` |

Legacy CB24 replaces the last byte with `AA` (Side A) or `BB` (Side B) for one
side; held motors send the sum of their words.

#### SIMMONS keys

| Command | Word | Profiles | Frame |
|---|---|---|---|
| Head up | `0x0000000001` | all | `05 02 00 00 00 01 00` or `E6 FE 16 01 00 00 00 00 04` |
| Head down | `0x0000000002` | all | `05 02 00 00 00 02 00` or `E6 FE 16 02 00 00 00 00 03` |
| Legs up | `0x0000000004` | all | `05 02 00 00 00 04 00` or `E6 FE 16 04 00 00 00 00 01` |
| Legs down | `0x0000000008` | all | `05 02 00 00 00 08 00` or `E6 FE 16 08 00 00 00 00 FD` |
| Flat | `0x0008000000` | all | `05 02 08 00 00 00 00` or `E6 FE 16 00 00 00 08 00 FD` |
| Zero-G | `0x0000001000` | all | `05 02 00 00 10 00 00` or `E6 FE 16 00 10 00 00 00 F5` |
| TV | `0x0000004000` | all | `05 02 00 00 40 00 00` or `E6 FE 16 00 40 00 00 00 C5` |
| Anti-snore / Snore | `0x0000008000` | all | `05 02 00 00 80 00 00` or `E6 FE 16 00 80 00 00 00 85` |
| Custom Mode (memory) | `0x0000010000` | all | `05 02 00 01 00 00 00` or `E6 FE 16 00 00 01 00 00 04` |
| Under-bed light toggle | `0x0000020000` | all | `05 02 00 02 00 00 00` or `E6 FE 16 00 00 02 00 00 03` |
| Inclined Left | `0x0000000010` | all | `05 02 00 00 00 10 00` |
| Inclined Middle | `0x0000001000` | all | `05 02 00 00 10 00 00` |
| Inclined Right | `0x0000000020` | all | `05 02 00 00 00 20 00` |
| STOP / release | `0x00000000` | all | `05 02 00 00 00 00 00` or `E6 FE 16 00 00 00 00 00 05` |

SmartBed and unmatched names send the 40-bit frame, OKIN names the Keeson E6
frame. The inclined keys keep the 40-bit frame on both.

#### SleepEase keys

| Command | Word | Frame |
|---|---|---|
| Index 1 | `0x0000000000` | `05 02 00 00 00 00 00` |
| Index 2 | `0x0000000001` | `05 02 00 00 00 01 00` |
| Index 3 | `0x0000000002` | `05 02 00 00 00 02 00` |
| Index 4 | `0x0000000004` | `05 02 00 00 00 04 00` |
| Index 5 | `0x0000000008` | `05 02 00 00 00 08 00` |
| Index 8 | `0x0000000040` | `05 02 00 00 00 40 00` |
| Index 9 | `0x0000000080` | `05 02 00 00 00 80 00` |
| Index 10 | `0x0000000010` | `05 02 00 00 00 10 00` |
| Index 11 | `0x0000000020` | `05 02 00 00 00 20 00` |
| Index 12 | `0x0040000000` | `05 02 40 00 00 00 00` |
| Index 13 | `0x0080000000` | `05 02 80 00 00 00 00` |
| Index 14 | `0x0000010000` | `05 02 00 01 00 00 00` |
| Index 15 | `0x0000040000` | `05 02 00 04 00 00 00` |
| Index 16 | `0x0000008000` | `05 02 00 00 80 00 00` |
| Index 17 | `0x0000002000` | `05 02 00 00 20 00 00` |
| Index 18 | `0x0000004000` | `05 02 00 00 40 00 00` |
| Index 19 | `0x0000001000` | `05 02 00 00 10 00 00` |
| Index 26 | `0x0008000000` | `05 02 08 00 00 00 00` |
| Index 28 | `0x0000000100` | `05 02 00 00 01 00 00` |
| Index 29 | `0x0000000100` | `05 02 00 00 01 00 00` |
| Index 31 | `0x0000000200` | `05 02 00 00 02 00 00` |
| Index 35 | `0x0000000800` | `05 02 00 00 08 00 00` |
| Index 36 | `0x0000800000` | `05 02 00 80 00 00 00` |
| Index 37 | `0x0000000400` | `05 02 00 00 04 00 00` |
| Index 38 | `0x0010000000` | `05 02 10 00 00 00 00` |
| Index 40 | `0x0010000000` | `05 02 10 00 00 00 00` |
| Index 41 | `0x0004000000` | `05 02 04 00 00 00 00` |
| Index 58 | `0x0000020000` | `05 02 00 02 00 00 00` |

SleepDriver (P1) words by the app's command index; index 1 is STOP. The profile's
other static frames and the XiaoBao (P2) and P3 packets are listed in its section.

#### Sleepy's legacy CB25 keys

| Command | Word | Frame |
|---|---|---|
| Head up | `0x0000000001` | `05 02 00 00 00 01 00` |
| Head down | `0x0000000002` | `05 02 00 00 00 02 00` |
| Foot up | `0x0000000004` | `05 02 00 00 00 04 00` |
| Foot down | `0x0000000008` | `05 02 00 00 00 08 00` |
| Lumbar up | `0x0000000010` | `05 02 00 00 00 10 00` |
| Lumbar down | `0x0000000020` | `05 02 00 00 00 20 00` |
| Neck tilt up | `0x0000000040` | `05 02 00 00 00 40 00` |
| Neck tilt down | `0x0000000080` | `05 02 00 00 00 80 00` |
| STOP / release | `0x0000000000` | `05 02 00 00 00 00 00` |
| Flat | `0x0008000000` | `05 02 08 00 00 00 00` |
| TV | `0x0000004000` | `05 02 00 00 40 00 00` |
| Zero-G | `0x0000001000` | `05 02 00 00 10 00 00` |
| Anti-snore | `0x0000008000` | `05 02 00 00 80 00 00` |
| Lounge | `0x0000002000` | `05 02 00 00 20 00 00` |
| Memory 1 | `0x0000010000` | `05 02 00 01 00 00 00` |
| Memory 2 | `0x0000040000` | `05 02 00 04 00 00 00` |
| Store memory 1 | `0x0008010000` | `05 02 08 01 00 00 00` |
| Store memory 2 | `0x0008040000` | `05 02 08 04 00 00 00` |
| Massage toggle | `0x0000080000` | `05 02 00 08 00 00 00` |
| Massage exit | `0x0002000000` | `05 02 02 00 00 00 00` |
| Head massage up | `0x0000000800` | `05 02 00 00 08 00 00` |
| Head massage down | `0x0000800000` | `05 02 00 80 00 00 00` |
| Foot massage up | `0x0000000400` | `05 02 00 00 04 00 00` |
| Foot massage down | `0x0001000000` | `05 02 01 00 00 00 00` |
| Massage intensity up | `0x0000000C00` | `05 02 00 00 0C 00 00` |
| Massage intensity down | `0x0001800000` | `05 02 01 80 00 00 00` |
| Under-bed light toggle | `0x0002000000000000` | `08 02 00 02 00 00 00 00 00 00` |
| Massage wave 1 | `0x0000000000080000` | `08 02 00 00 00 00 00 08 00 00` |
| Massage wave 2 | `0x0000000000100000` | `08 02 00 00 00 00 00 10 00 00` |
| Massage wave 3 | `0x0000000000200000` | `08 02 00 00 00 00 00 20 00 00` |

#### AdjustableM5X4 keys

| Command | Word | Profiles | Frame |
|---|---|---|---|
| `headUp` | `0x0000000001` | AdjustableM5X4 none, BOX24, BOX1221, BOX2422, BOX2442, AdjustableM5X4 BOX3633, AdjustableM5X4 BOX25 | `05 02 00 00 00 01 00` |
| `headDown` | `0x0000000002` | AdjustableM5X4 none, BOX24, BOX1221, BOX2422, BOX2442, AdjustableM5X4 BOX3633, AdjustableM5X4 BOX25 | `05 02 00 00 00 02 00` |
| `footUp` | `0x0000000004` | AdjustableM5X4 none, BOX24, BOX1221, BOX2422, BOX2442, AdjustableM5X4 BOX3633, AdjustableM5X4 BOX25 | `05 02 00 00 00 04 00` |
| `footDown` | `0x0000000008` | AdjustableM5X4 none, BOX24, BOX1221, BOX2422, BOX2442, AdjustableM5X4 BOX3633, AdjustableM5X4 BOX25 | `05 02 00 00 00 08 00` |
| `unionUp` | `0x0000000005` | AdjustableM5X4 none, BOX24, BOX1221, BOX2422, BOX2442, AdjustableM5X4 BOX3633, AdjustableM5X4 BOX25 | `05 02 00 00 00 05 00` |
| `unionDown` | `0x000000000A` | AdjustableM5X4 none, BOX24, BOX1221, BOX2422, BOX2442, AdjustableM5X4 BOX3633, AdjustableM5X4 BOX25 | `05 02 00 00 00 0A 00` |
| STOP / release | `0x0000000000` | AdjustableM5X4 none, BOX24, BOX1221, BOX2422, BOX2442, AdjustableM5X4 BOX3633, AdjustableM5X4 BOX25 | `05 02 00 00 00 00 00` |
| `flatPosition` | `0x0008000000` | AdjustableM5X4 none, BOX24, BOX1221, BOX2422, BOX2442, AdjustableM5X4 BOX3633, AdjustableM5X4 BOX25 | `05 02 08 00 00 00 00` |
| TV | `0x0000004000` | AdjustableM5X4 none, BOX24, BOX1221, BOX2422, BOX2442, AdjustableM5X4 BOX3633, AdjustableM5X4 BOX25 | `05 02 00 00 40 00 00` |
| Lounge / Reading | `0x0000002000` | AdjustableM5X4 none, BOX24, BOX1221, BOX2422, BOX2442, AdjustableM5X4 BOX3633, AdjustableM5X4 BOX25 | `05 02 00 00 20 00 00` |
| `zeroGravity` | `0x0000001000` | AdjustableM5X4 none, BOX24, BOX1221, BOX2422, BOX2442, AdjustableM5X4 BOX3633, AdjustableM5X4 BOX25 | `05 02 00 00 10 00 00` |
| `anti` | `0x0000008000` | AdjustableM5X4 none, BOX24, BOX1221, BOX2422, BOX2442, AdjustableM5X4 BOX3633, AdjustableM5X4 BOX25 | `05 02 00 00 80 00 00` |
| `m1` | `0x0000010000` | AdjustableM5X4 none, BOX24, BOX1221, BOX2422, BOX2442, AdjustableM5X4 BOX3633, AdjustableM5X4 BOX25 | `05 02 00 01 00 00 00` |
| `saveM1` | `0x0000010000` | AdjustableM5X4 none, BOX24, BOX1221, BOX2422, BOX2442, AdjustableM5X4 BOX3633, AdjustableM5X4 BOX25 | `05 02 00 01 00 00 00` |
| `saveTv` | `0x0080004000` | AdjustableM5X4 none, BOX24, BOX1221, BOX2422, BOX2442, AdjustableM5X4 BOX3633, AdjustableM5X4 BOX25 | `05 02 80 00 40 00 00` |
| `saveLounge` | `0x0080002000` | AdjustableM5X4 none, BOX24, BOX1221, BOX2422, BOX2442, AdjustableM5X4 BOX3633, AdjustableM5X4 BOX25 | `05 02 80 00 20 00 00` |
| `saveZeroGravity` | `0x0080001000` | AdjustableM5X4 none, BOX24, BOX1221, BOX2422, BOX2442, AdjustableM5X4 BOX3633, AdjustableM5X4 BOX25 | `05 02 80 00 10 00 00` |
| `resetMemory` | `0x0088000000` | all | `05 02 88 00 00 00 00` |
| `massageOnOff` | `0x0000080000` | all | `05 02 00 08 00 00 00` |
| `headStrengthAdd` | `0x0000000800` | AdjustableM5X4 BOX3633, AdjustableM5X4 BOX25, AdjustableM5X4 BOX1220 | `05 02 00 00 08 00 00` |
| `headStrengthReduce` | `0x0000800000` | AdjustableM5X4 BOX3633, AdjustableM5X4 BOX25, AdjustableM5X4 BOX1220 | `05 02 00 80 00 00 00` |
| `footStrengthAdd` | `0x0000000400` | AdjustableM5X4 BOX3633, AdjustableM5X4 BOX25, AdjustableM5X4 BOX1220 | `05 02 00 00 04 00 00` |
| `footStrengthReduce` | `0x0001000000` | AdjustableM5X4 BOX3633, AdjustableM5X4 BOX25, AdjustableM5X4 BOX1220 | `05 02 01 00 00 00 00` |
| `waveAdd` | `0x0010000000` | AdjustableM5X4 BOX3633, AdjustableM5X4 BOX25, AdjustableM5X4 BOX1220 | `05 02 10 00 00 00 00` |
| `waveReduce` | `0x0004000000` | AdjustableM5X4 BOX3633, AdjustableM5X4 BOX25, AdjustableM5X4 BOX1220 | `05 02 04 00 00 00 00` |
| `underbedLighting` | `0x0000020000` | AdjustableM5X4 BOX3633 | `05 02 00 02 00 00 00` |
| `change2White` | `0x0000020004` | AdjustableM5X4 BOX25 | `05 02 00 02 00 04 00` |
| `turnonUnderbedLighting` | `0x0000020000` | AdjustableM5X4 none, BOX24, BOX1221, BOX2422, BOX2442, AdjustableM5X4 BOX15, AdjustableM5X4 BOX1220 | `05 02 00 02 00 00 00` |
| `turnoffUnderbedLighting` | `0x0000020000` | AdjustableM5X4 none, BOX24, BOX1221, BOX2422, BOX2442, AdjustableM5X4 BOX15, AdjustableM5X4 BOX1220 | `05 02 00 02 00 00 00` |
| `underbedLighting` | `0x0002000000000000` | AdjustableM5X4 none, BOX24, BOX1221, BOX2422, BOX2442, AdjustableM5X4 BOX25 | `08 02 00 02 00 00 00 00 00 00` |
| `turnonUnderbedLighting` | `0x0000000000000040` | AdjustableM5X4 BOX3633 | `08 02 00 00 00 00 00 00 00 40` |
| `turnoffUnderbedLighting` | `0x0000000000000080` | AdjustableM5X4 BOX3633 | `08 02 00 00 00 00 00 00 00 80` |

Keyed by the app's action names. BOX15 and BOX1220 move with their own frames, so
their profiles hold only the shared keys; BOX25_STAR sends StarCode only.

#### Okin CST keys

| Command | Word | Profiles | Frame |
|---|---|---|---|
| Head up | `00000001 00000000` | all | `0C 02 00 00 00 01 00 00 00 00 00 00 00 00` |
| Head down | `00000002 00000000` | all | `0C 02 00 00 00 02 00 00 00 00 00 00 00 00` |
| Foot up | `00000004 00000000` | all | `0C 02 00 00 00 04 00 00 00 00 00 00 00 00` |
| Foot down | `00000008 00000000` | all | `0C 02 00 00 00 08 00 00 00 00 00 00 00 00` |
| Flat | `08000000 00000000` | all | `0C 02 08 00 00 00 00 00 00 00 00 00 00 00` |
| Zero-G | `00001000 00000000` | all | `0C 02 00 00 10 00 00 00 00 00 00 00 00 00` |
| Anti-snore / Snore | `00008000 00000000` | all | `0C 02 00 00 80 00 00 00 00 00 00 00 00 00` |
| Lumbar up | `00000010 00000000` | Rize Aviada, Rize Contempo, Rize MF900, Support | `0C 02 00 00 00 10 00 00 00 00 00 00 00 00` |
| Lumbar down | `00000020 00000000` | Rize Aviada, Rize Contempo, Rize MF900, Support | `0C 02 00 00 00 20 00 00 00 00 00 00 00 00` |
| Lounge / Reading | `00002000 00000000` | Rize Sanctuary, Rize Resident, Rize Aviada, Rize Bob, Rize Contempo, Rize II Clarity, Rize MF900, Support, Nectar Move | `0C 02 00 00 20 00 00 00 00 00 00 00 00 00` |
| Incline | `00004000 00000000` | Rize Resident, Rize Aviada, Rize Contempo, Rize II Clarity, Rize MF900, Support | `0C 02 00 00 40 00 00 00 00 00 00 00 00 00` |
| Memory 1 | `00001000 00000000` | all | `0C 02 00 00 10 00 00 00 00 00 00 00 00 00` |
| Save memory 1 | `08001000 00000000` | all | `0C 02 08 00 10 00 00 00 00 00 00 00 00 00` |
| Memory 2 | `00002000 00000000` | Rize Sanctuary, Rize Bob, Nectar Move | `0C 02 00 00 20 00 00 00 00 00 00 00 00 00` |
| Memory 2 | `00004000 00000000` | Rize Resident, Rize Aviada, Rize Contempo, Rize II Clarity, Rize MF900, Support | `0C 02 00 00 40 00 00 00 00 00 00 00 00 00` |
| Save memory 2 | `08002000 00000000` | Rize Sanctuary, Rize Bob, Nectar Move | `0C 02 08 00 20 00 00 00 00 00 00 00 00 00` |
| Save memory 2 | `08004000 00000000` | Rize Resident, Rize Aviada, Rize Contempo, Rize II Clarity, Rize MF900, Support | `0C 02 08 00 40 00 00 00 00 00 00 00 00 00` |
| Memory 3 | `00002000 00000000` | Rize Resident, Rize Aviada, Rize Contempo, Rize II Clarity, Rize MF900, Support | `0C 02 00 00 20 00 00 00 00 00 00 00 00 00` |
| Save memory 3 | `08002000 00000000` | Rize Resident, Rize Aviada, Rize Contempo, Rize II Clarity, Rize MF900, Support | `0C 02 08 00 20 00 00 00 00 00 00 00 00 00` |
| Under-bed light toggle | `00020000 00000000` | Rize Sanctuary, Rize Aviada, Rize Bob, Rize Contempo, Rize II Carefree, Rize II Clarity, Rize MF900, Support, Nectar Move | `0C 02 00 02 00 00 00 00 00 00 00 00 00 00` |
| Light on | `00000000 00000040` | Rize Sanctuary, Rize Aviada, Rize Bob, Rize Contempo, Rize II Carefree, Rize II Clarity, Rize MF900, Support | `0C 02 00 00 00 00 00 00 00 40 00 00 00 00` |
| Light off | `00000000 00000080` | Rize Sanctuary, Rize Aviada, Rize Bob, Rize Contempo, Rize II Carefree, Rize II Clarity, Rize MF900, Support | `0C 02 00 00 00 00 00 00 00 80 00 00 00 00` |
| Massage wave 1 | `00000000 00080000` | Rize Sanctuary, Rize Resident, Rize Aviada, Rize Bob, Rize Contempo, Rize II Clarity, Rize MF900, Support | `0C 02 00 00 00 00 00 08 00 00 00 00 00 00` |
| Massage wave 2 | `00000000 00100000` | Rize Sanctuary, Rize Resident, Rize Aviada, Rize Bob, Rize Contempo, Rize II Clarity, Rize MF900, Support | `0C 02 00 00 00 00 00 10 00 00 00 00 00 00` |
| Massage wave 3 | `00000000 00200000` | Rize Sanctuary, Rize Resident, Rize Aviada, Rize Bob, Rize Contempo, Rize II Clarity, Rize MF900, Support | `0C 02 00 00 00 00 00 20 00 00 00 00 00 00` |
| Massage off | `02000000 00000000` | Rize Sanctuary, Rize Resident, Rize Aviada, Rize Bob, Rize Contempo, Rize II Clarity, Rize MF900, Support | `0C 02 02 00 00 00 00 00 00 00 00 00 00 00` |
| Head massage up | `00000800 00000000` | Rize Sanctuary, Rize Resident, Rize Bob, Support | `0C 02 00 00 08 00 00 00 00 00 00 00 00 00` |
| Head massage down | `00800000 00000000` | Rize Sanctuary, Rize Resident | `0C 02 00 80 00 00 00 00 00 00 00 00 00 00` |
| Head massage down | `00800000 00800000` | Rize Bob, Support | `0C 02 00 80 00 00 00 80 00 00 00 00 00 00` |
| Foot massage up | `00000400 00000000` | Rize Sanctuary, Rize Resident, Rize Bob, Support | `0C 02 00 00 04 00 00 00 00 00 00 00 00 00` |
| Foot massage down | `00000000 01000000` | Support | `0C 02 00 00 00 00 01 00 00 00 00 00 00 00` |
| Foot massage down | `01000000 00000000` | Rize Sanctuary, Rize Resident | `0C 02 01 00 00 00 00 00 00 00 00 00 00 00` |
| Foot massage down | `01000000 01000000` | Rize Bob | `0C 02 01 00 00 00 01 00 00 00 00 00 00 00` |
| Memory 4 | `00010000 00000000` | Rize Resident | `0C 02 00 01 00 00 00 00 00 00 00 00 00 00` |
| Save memory 4 | `08010000 00000000` | Rize Resident | `0C 02 08 01 00 00 00 00 00 00 00 00 00 00` |
| Massage timer step | `00000200 00000000` | Rize Resident | `0C 02 00 00 02 00 00 00 00 00 00 00 00 00` |
| Massage intensity up | `00000C00 00000000` | Rize Aviada, Rize Contempo, Rize II Clarity, Rize MF900, Nectar Move | `0C 02 00 00 0C 00 00 00 00 00 00 00 00 00` |
| Massage intensity down | `01800000 00000000` | Rize Aviada, Rize Contempo, Rize II Clarity, Rize MF900 | `0C 02 01 80 00 00 00 00 00 00 00 00 00 00` |
| Massage toggle | `00000000 00000100` | Rize Sanctuary, Rize Bob | `0C 02 00 00 00 00 00 00 01 00 00 00 00 00` |
| STOP / release | `00000000 00000000` | all | `0C 02 00 00 00 00 00 00 00 00 00 00 00 00` |

The word column shows the primary and secondary fields. Each product lists the
controls it supports; held motors send the OR of their primary words.

#### OKIN Bedding app keys

| Command | Word | Profiles | Frame |
|---|---|---|---|
| Head up | `00000001 00000000` | all | `0C 02 00 00 00 01 00 00 00 00 00 00 00 00` |
| Head down | `00000002 00000000` | all | `0C 02 00 00 00 02 00 00 00 00 00 00 00 00` |
| Foot up | `00000004 00000000` | all | `0C 02 00 00 00 04 00 00 00 00 00 00 00 00` |
| Foot down | `00000008 00000000` | all | `0C 02 00 00 00 08 00 00 00 00 00 00 00 00` |
| `selector_4_up` | `00000010 00000000` | Jordan's Serenity, Jordan's Tranquil | `0C 02 00 00 00 10 00 00 00 00 00 00 00 00` |
| `selector_4_down` | `00000020 00000000` | Jordan's Serenity, Jordan's Tranquil | `0C 02 00 00 00 20 00 00 00 00 00 00 00 00` |
| `selector_5_up` | `00000010 00000000` | Customatic Z-280 | `0C 02 00 00 00 10 00 00 00 00 00 00 00 00` |
| `selector_5_up` | `00000040 00000000` | Jordan's Serenity, Jordan's Tranquil | `0C 02 00 00 00 40 00 00 00 00 00 00 00 00` |
| `selector_5_down` | `00000020 00000000` | Customatic Z-280 | `0C 02 00 00 00 20 00 00 00 00 00 00 00 00` |
| `selector_5_down` | `00000080 00000000` | Jordan's Serenity, Jordan's Tranquil | `0C 02 00 00 00 80 00 00 00 00 00 00 00 00` |
| Flat | `08000000 00000000` | all | `0C 02 08 00 00 00 00 00 00 00 00 00 00 00` |
| Zero-G | `00001000 00000000` | all | `0C 02 00 00 10 00 00 00 00 00 00 00 00 00` |
| Memory 1 | `00010000 00000000` | all | `0C 02 00 01 00 00 00 00 00 00 00 00 00 00` |
| TV | `00004000 00000000` | Jordan's Serenity, Customatic Z-230, Customatic Z-280 | `0C 02 00 00 40 00 00 00 00 00 00 00 00 00` |
| Memory 2 | `00040000 00000000` | Jordan's Serenity, Jordan's Tranquil, Customatic Z-280 | `0C 02 00 04 00 00 00 00 00 00 00 00 00 00` |
| `save_zero_g` | `08001000 00000000` | all | `0C 02 08 00 10 00 00 00 00 00 00 00 00 00` |
| Save memory 1 | `08010000 00000000` | all | `0C 02 08 01 00 00 00 00 00 00 00 00 00 00` |
| `save_tv` | `08004000 00000000` | Jordan's Serenity, Customatic Z-230, Customatic Z-280 | `0C 02 08 00 40 00 00 00 00 00 00 00 00 00` |
| Save memory 2 | `08040000 00000000` | Jordan's Serenity, Jordan's Tranquil, Customatic Z-280 | `0C 02 08 04 00 00 00 00 00 00 00 00 00 00` |
| `massage_head_cycle` | `00000800 00000000` | Jordan's Serenity, Jordan's Tranquil, Customatic Z-280 | `0C 02 00 00 08 00 00 00 00 00 00 00 00 00` |
| `massage_foot_cycle` | `00000400 00000000` | Jordan's Serenity, Jordan's Tranquil, Customatic Z-280 | `0C 02 00 00 04 00 00 00 00 00 00 00 00 00` |
| `massage_mode_cycle` | `10000000 00000000` | all | `0C 02 10 00 00 00 00 00 00 00 00 00 00 00` |
| `massage_timer_cycle` | `00000200 00000000` | all | `0C 02 00 00 02 00 00 00 00 00 00 00 00 00` |
| Massage toggle | `00000100 00000000` | all | `0C 02 00 00 01 00 00 00 00 00 00 00 00 00` |
| Under-bed light toggle | `00020000 00000000` | all | `0C 02 00 02 00 00 00 00 00 00 00 00 00 00` |
| `leisure` | `00002000 00000000` | Jordan's Serenity | `0C 02 00 00 20 00 00 00 00 00 00 00 00 00` |
| Anti-snore / Snore | `00008000 00000000` | all | `0C 02 00 00 80 00 00 00 00 00 00 00 00 00` |
| Massage wave 1 | `00000000 00080000` | Jordan's Serenity, Jordan's Tranquil | `0C 02 00 00 00 00 00 08 00 00 00 00 00 00` |
| Massage wave 2 | `00000000 00100000` | Jordan's Serenity, Jordan's Tranquil | `0C 02 00 00 00 00 00 10 00 00 00 00 00 00` |
| Massage wave 3 | `00000000 00200000` | Jordan's Serenity, Jordan's Tranquil | `0C 02 00 00 00 00 00 20 00 00 00 00 00 00` |
| Massage off | `02000000 00000000` | Jordan's Serenity, Jordan's Tranquil | `0C 02 02 00 00 00 00 00 00 00 00 00 00 00` |
| Light on | `00000000 00000040` | Jordan's Serenity, Jordan's Tranquil | `0C 02 00 00 00 00 00 00 00 40 00 00 00 00` |
| Light off | `00000000 00000080` | Jordan's Serenity, Jordan's Tranquil | `0C 02 00 00 00 00 00 00 00 80 00 00 00 00` |
| Lounge / Reading | `00002000 00000000` | Jordan's Tranquil | `0C 02 00 00 20 00 00 00 00 00 00 00 00 00` |
| `save_lounge` | `08002000 00000000` | Jordan's Tranquil | `0C 02 08 00 20 00 00 00 00 00 00 00 00 00` |
| `head_foot_up` | `00000005 00000000` | Customatic Z-230 | `0C 02 00 00 00 05 00 00 00 00 00 00 00 00` |
| `head_foot_down` | `0000000A 00000000` | Customatic Z-230 | `0C 02 00 00 00 0A 00 00 00 00 00 00 00 00` |
| `massage_intensity_cycle` | `00000C00 00000000` | Customatic Z-230 | `0C 02 00 00 0C 00 00 00 00 00 00 00 00 00` |
| STOP / release | `00000000 00000000` | all | `0C 02 00 00 00 00 00 00 00 00 00 00 00 00` |

Each app's literal action table, by the app's action names.
<!-- /generated -->

### Responses

| Parser | Profiles | Input |
|---|---|---|
| `parse_position` | Okimat | Position notification on the position characteristic, 7+ bytes: head raw at bytes 3-4 and foot raw at bytes 5-6, little-endian |
| `parse_status` | Leggett Okin | Status notification: the app's LED mask (operations 6, 7, 8, 9 and 11) and signed status byte |
| `parse_receipt` | Prodigy CE | 20-byte CU170 status frame: `09 0B`, two identical big-endian status dwords, ten trailing bytes |

Okimat angles are `raw / max_raw × max_angle`, clamped:

| Motor | Max raw value | Max angle |
|---|---|---|
| Head/back | 16000 | 60° |
| Foot/legs | 12000 | 45° |

### STOP and release behavior

- Okimat and DewertOkin release a held key with one STOP frame. Okimat sends it
  only when no other motor is still held, so other held motors keep moving.
- Customatic sends one fresh STOP 100 ms after the last motor write; memory-page
  holds end without one.
- Leggett Okin ends every held key with four zero frames (the app's
  `MaxZeroCount = 3` loop). There is no distinct stop opcode. Recalls send no
  terminator at all.
- The RF ECO BT stair lift has no STOP: release ends the refresh.
- CST products and the OKIN Bedding apps release with two STOPs, 100 and 200 ms
  after the release.
- CB24, DOT and Sleepy's legacy CB25 release with one STOP; a CB24 or Sleepy's
  preset STOP commits the recall. SIMMONS sends two STOPs 100 and 400 ms after
  every release. SleepEase P1 sends its index 1 STOP after every hold.
- Every cleanup runs with a fresh cancel event, so a stop request cannot
  suppress it.

The [hold and release timing](#hold-and-release-timing) table has the counts
and intervals.

### Vectors

`tests/okin_nframe_vectors.py` lists each profile's frozen frames: app profiles
take every N-frame literal from their accepted report (SIMMONS also its Keeson
E6 frames, SleepEase its pinned P1 vectors), and the Okimat, DewertOkin, RF ECO
BT, CB24, DOT, Sleepy's legacy CB25 and AdjustableM5X4 routes take the frames
the pre-v5 controllers sent, including the RF-Gateway envelopes. `tests/test_okin_nframe_vectors.py` checks that every
literal round-trips through the codec and that every fixed frame a profile can
send is frozen.

## Profiles

### Okimat

**Status:** ✅ Tested

#### Setup

- Bed types `okimat` and `okin_uuid` select this profile; they are aliases with
  identical frames.
- Choose the handset's remote code under **Protocol variant**. The code is
  printed on the back of the handset. If an exact code is not offered, use a
  captured code only when its button layout and keycodes have been verified for
  that handset.
- **Requires BLE pairing before use.**
- When the connected device is a DewertOkin RF-Gateway, the same handset table
  is sent in the [RF-Gateway envelope](#framing-and-checksum). When it is a DOT
  box, the entry uses the [Okin DOT](#okin-dot) controller.

**Detection.** Okimat is the fallback for the Okin service UUID. Some receiver
modules only advertise a local name such as `OKIN-Receiver` or `OKIN - Receiver`
until paired; those are shown as a pairing-required Okin-family protocol
selection, because the receiver name and the shared service UUID do not identify
the packet format. Priority:

1. Device name contains "nectar" → [Nectar](okin-5a.md#nectar)
2. Device name contains "leggett", "l&p", or "adjustable base" → [Leggett & Platt](leggett-platt.md)
3. Device name contains "okimat", "okin rf", or "okin ble" → Okimat/Okin UUID
4. Connected GATT has the Okin service plus CSS → OKIN Smart Remote /
   [RF ECO BT](#rf-eco-bt-stair-lift) when no stronger signal exists. Nordic DFU
   is only a CST hint and never selects Okin CST, which stays an explicit choice
   ([#555](https://github.com/kristofferR/ha-adjustable-bed/issues/555)). Device
   Information model `MEGAMAT MBZ` identifies the confirmed staircase, while an
   `OKIMAT` model identifies a full bed. The generic model `RF eco BT` is also
   used by full beds, so an explicitly selected valid handset code preserves the
   Okin UUID profile. With ambiguous shared GATT signals and no stronger model
   evidence, an already configured CST or RF ECO BT profile is preserved. A CST
   entry on an `OKIMAT` drive gets a [repair](furnimove.md#repairing-existing-configurations)
   instead of a silent switch.
5. Device name is `OKIN-Receiver` / `OKIN - Receiver` → prompt for an Okin-family protocol
6. Fallback → Okimat (with warning)

If your bed is misidentified, change the bed type in the integration settings.

#### Controls

The integration ships 210 handset codes covering the captured DewertOkin RF
handset range (RFS-ELLIPSE, RF-TOPLINE, RF-LITELINE, RF-FLASHLINE, RF-FREE-ELEC,
RF-TOUCH, RF-TOUCHLINE, RF-STYLE, RF-ECO and their memory and massage
variants). The app accepts manually entered IDs, but its backend has no endpoint
that enumerates every valid ID, so this table is a snapshot rather than a
provably complete catalog.

- Only motors the handset drives get covers. Head controls drive a dedicated
  head/tilt motor when the handset has one and stay a back synonym on 2-motor
  handsets; feet falls back to legs the same way. The configured motor count
  still caps how many axes are shown.
- Motors held together send the sum of their words in one frame. This is
  integration behavior carried over from
  [smartbed-mqtt #66](https://github.com/richardhopton/smartbed-mqtt/pull/66),
  not app evidence: the Okimat route has no accepted app report (its frozen
  vectors are the pre-v5 controller's frames), and the
  [FurniMove ledger](../apk-analysis/dispositions/157-furnimove.md) describes
  only a single held key's refresh (D038), with no combined held keys.
  FurniMove's two-axis movement is its explicit
  [`furnimove_move_simultaneously`](furnimove.md) action.
- Flat, memory recall, zero-gravity and anti-snore stream their key, then STOP.
  Anti-snore falls back to the quiet-sleep key: RF1058 handsets carry the same
  `0x4000` preset as either "Snore" or "QuietSleep".
- Memory save sends the handset's single save key; the handset decides the slot.
- The light toggle appears only for handsets with a light key and sends one
  press per button press: repeating it flashes the light and can end in "off".
- Sync both sides (split bases) and child lock stream their key like any held
  key, then STOP.
- Massage keys are single presses. Handsets with a wave key step modes with it;
  handsets with only discrete program keys cycle through them.

##### Okimat handset keys

<!-- generated:okin-nframe-okimat -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

210 selectable handset codes. Each row counts the codes that define the key and
lists every command word they use for it.

| Key | Codes | Command words |
|---|---|---|
| Back up / down | 203 | `0x00000001`, `0x00000002`, `0x00000004`, `0x00000008` |
| Legs up / down | 199 | `0x00000004`, `0x00000008`, `0x00000010`, `0x00000020` |
| Head (tilt) up / down | 59 | `0x00000001`, `0x00000002`, `0x00000010`, `0x00000020` |
| Feet up / down | 38 | `0x00000020`, `0x00000040`, `0x00000080` |
| Flat | 206 | `0x0000000A`, `0x0000002A`, `0x000000AA`, `0x10000000`, `0x100000AA` |
| Memory 1-4 | 99 | `0x00001000`, `0x00002000`, `0x00003000`, `0x00004000`, `0x00008000` |
| Memory save | 99 | `0x00010000` |
| Under-bed light | 172 | `0x00020000` |
| Sync both sides | 69 | `0x00000100` |
| Child lock | 53 | `0x08000000` |
| Zero-gravity | 8 | `0x00004000` |
| Massage | 13 | per handset |

Handset memory-save holds: 10 × 200 ms, 25 × 200 ms, 40 × 200 ms. Other handsets
use the profile's default memory save.

Flat words per handset:

| Flat word | Codes |
|---|---|
| `0x0000000A` | 86432, 93055 |
| `0x0000002A` | 93329 |
| `0x000000AA` | 82417, 82418, 93332, 94428, 94429, 94430, 94495, 94500 |
| `0x10000000` | 65433, 84762, 85281, 89441, 89448, 89746, 89803, 90392, 90882, 90928, 91334, 91616, 91751, 92063, 92129, 92428, 92471, 94238, 94239, 94369, 96312, 96313, 96314, 96315, 97134, 97135 |
| `0x100000AA` | 62211, 62612, 63293, 63338, 63365, 65418, 65567, 68036, 71852, 71853, 73591, 73593, 74130, 74131, 75225, 75267, 75268, 76208, 76688, 76691, 77008, 77010, 77011, 77560, 77561, 77839, 77991, 77994, 77995, 77996, 78031, 78033, 78080, 78081, 78102, 78103, 78105, 78109, 78110, 78111, 78237, 78238, 78281, 78283, 78375, 78378, 78379, 78381, 78386, 78737, 78773, 78785, 78791, 78847, 78854, 78860, 80027, 80035, 80036, 80354, 80355, 80358, 80360, 80593, 80595, 80597, 80599, 80601, 80602, 80603, 80604, 80608, 80616, 80673, 80674, 80675, 80676, 80683, 80685, 80714, 80716, 80903, 81183, 81185, 81186, 81187, 81191, 81192, 81193, 81194, 81196, 81197, 81202, 81204, 81205, 81611, 81613, 81619, 81620, 82292, 82295, 82620, 82634, 82635, 82755, 82757, 82760, 82764, 82767, 82770, 82785, 82786, 82790, 82794, 82795, 82796, 82797, 82799, 83060, 83126, 83219, 83358, 83462, 83489, 83603, 84148, 84149, 84150, 84151, 84173, 84562, 84563, 84564, 84582, 84931, 84963, 85057, 85058, 85124, 85126, 88875, 88877, 89137, 89138, 89139, 89476, 89837, 90269, 90354, 90658, 90675, 90678, 90679, 90916, 90918, 91050, 91244, 91246, 91914, 92113, 92461, 92535, 92591, 93025, 93300, 93305, 93306, 93339, 94186 |

Memory slots per handset (the highest slot each code defines):

| Memory slots | Codes |
|---|---|
| 1 | 76691, 78379, 78381, 80601, 80603, 80604 |
| 2 | 78847, 78854, 78860, 80027, 80903, 82292, 82418, 83060, 85058, 86432, 89545, 89746, 90199, 90354, 90882, 90916, 90928, 91246, 91334, 92129, 92428, 92471, 92591, 93055, 93306, 93332, 93339, 94186, 94238, 94430, 94500, 97134, 97135 |
| 3 | 78773, 78785, 78791, 80035, 80036, 82295, 83126, 83219, 84173, 89837, 90918, 91050, 91914 |
| 4 | 62211, 62612, 63365, 65418, 65433, 65567, 76208, 77839, 77991, 77994, 77995, 77996, 78080, 78081, 78102, 78103, 78105, 78109, 78110, 78111, 78737, 81185, 81187, 81191, 81192, 81193, 81196, 81197, 81202, 81204, 81205, 85057, 85281, 89441, 89448, 89476, 90269, 90658, 90675, 90678, 90679, 92113, 93300, 93329, 94369, 94428, 94429 |
<!-- /generated -->

**Flat is a per-code property**: two codes in the same model family can use
different Flat words, so each code stores its own values instead of sharing a
family profile. This corrected several Flat values earlier releases had wrong
(for example 82620, 83489, 91246, 92591, 93306). Handset 93332's head-down and
feet-down keys share one word, `0x00000020`, as in the
[smartbed-mqtt reference](https://github.com/richardhopton/smartbed-mqtt); the
handset maps that word to both motors.

**Source of truth.** The handset table is generated from the DewertOkin
FurniMove handset backend (`GET /mobile-data/button/{code}`), which returns
authoritative 32-bit keycodes and timing per code. For codes the backend no
longer serves, keycodes are inherited from a live code with the identical
`handsetlist.csv` capability signature when one exists (`csv-inherit:<code>`).
When no live sibling exists they are rebuilt from the universal and modal
keycode maps according to the CSV flags (`csv-reconstruct`); these entries have
lower assurance, and Flat may be approximate. `beds/okin_uuid_remotes.py` tags
each entry `backend`, `csv-inherit:<code>` or `csv-reconstruct`;
`tools/okin_remotes/` regenerates it.

The 83 codes that also appear in the pinned [FurniMove](furnimove.md) production
catalog take their keycodes and memory-save timing from that catalog; they
matched the backend capture byte for byte. Okin UUID remains their bed type in
new setups, because it adds the mandatory bond and position feedback that the
FurniMove app profile lacks.

> [!NOTE]
> Six codes that share the handset backend use a different transport and frame
> ("DOT PROTOCOL" / RF1058 / RF34 / RF6707: 90167, 91983, 93558, 97450, 97544,
> 98035). They are the separate [Okin DOT](#okin-dot) bed type: if that number
> is printed on your remote, select "Okin DOT" instead of Okimat.

#### Timing

See the [hold and release](#hold-and-release-timing) and
[one-shot](#one-shot-timing) tables. FurniMove 2.2.0 repeats a held key every
100 ms after each successful write while the touchscreen button is held, then
sends the zero/standby keycode. It does not use the backend UBL `duration` or
`frequency` fields to schedule writes; a light tap starts one press sequence.

#### Notifications

Some receivers report positions on the position characteristic (service
`0000ffe0-0000-1000-8000-00805f9b34fb`); it is not part of every controller's
GATT layout. See [Responses](#responses). FurniMove 2.2.0 exposes no alternate
position path for receivers without it: its `62741625...` parser reports only
under-bed light, sync and child-lock state, and it ignores notifications on
`90311725...`. No reachable app path parses angle or motor position from either
channel.

#### Evidence

Okimat sends only its frozen frames. FurniMove handset evidence is in the
[FurniMove ledger](../apk-analysis/dispositions/157-furnimove.md).

### DewertOkin

**Status:** ❓ Needs testing

#### Setup

- Bed types `dewertokin` and `okin_handle` select this profile; they are aliases
  with identical frames.
- **Detection:** device name contains `dewertokin`, `dewert`, `a h beard`, or
  `hankook`, not a service UUID.
- Address type: random.
- Earlier notes described these writes as handle-based, but the numeric handle
  is not stable, so the profile writes to the Okin write characteristic UUID.
- **RF-Gateway:** devices whose Device Information reports manufacturer
  `DewertOkin GmbH`, model `Bluetooth RF-Gateway`, can expose the normal Okin
  service plus an RF-Gateway settings service
  `92111420-72ab-4564-62ef-2a881286a6b0` with device-name characteristic
  `92111422-72ab-4564-62ef-2a881286a6b0`. FurniMove 2.0.1 uses that
  characteristic's presence to detect a gateway and writes it only to rename the
  gateway; every command still goes to the Okin write characteristic, in the
  [RF-Gateway envelope](#framing-and-checksum). The integration selects the
  envelope when the BLE model is `Bluetooth RF-Gateway` or when that
  service and characteristic pair is present. The same applies to Okimat entries.

#### Controls

Head and feet motors (back and legs are synonyms), Flat, Zero-G, TV, Quiet
Sleep, memory 1 and 2 (no programming), wave, head and foot massage toggles,
massage off and the light toggle. See the [DewertOkin table](#dewertokin-keys). The
light is a toggle: on and off each send it.

#### Timing

Motors and presets stream their key, then STOP; light and massage keys are one
write. See the [timing tables](#hold-and-release-timing). FurniMove repeats held
keys every 100 ms (`Thread.sleep(100L)`) and sends an explicit stop after motor
release.

#### Evidence

DewertOkin sends only its frozen frames, the pre-v5 controller's.

#### DewertOkin brands

Brands using DewertOkin/ORE actuators, from 79 analyzed apps:

- **Rize family:** Rize (Home, II, II Carefree, II Clarity, Contemporary, Bob,
  Sanctuary, Aviada, MF900), Resident Adjustable Base
- **Simmons:** SIMMONS (US), Simmons Korea (시몬스). Beds controlled with the
  `com.okin.simmons` app use the explicit [SIMMONS app profile](#simmons).
- **Customatic:** Customatic Demo; Clarity, Remedy and Jerome's C use the
  [Customatic app profiles](#customatic-family)
- **Mattress brands:** Mattress Firm (except Sleepy's Elite, see
  [Sleepy's Elite](sleepys.md)), Nectar Motion, Glory Furniture, Tranquil Sleep,
  Luxe, Ultra
- **ORE/Glideaway family:** Glideaway Motion (current app:
  [explicit MOTION 400/450/500/600 profile](keeson.md#glideaway-motion)), Symphony
  Sleep, Movita, Dynasty Bases (current app:
  [MaxCoil Una / Dynasty Bases / Bedsense Bases profile](keeson.md#ore-comfort-bed-profiles)),
  Better Living, LevaSleep, American Star, Avanti Bases (current app: explicit
  [Avanti Bases profile](keeson.md#ore-comfort-bed-profiles), `avanti_bases`), Comfort
  Furniture, Hestia Motion, Maxcoil Una (current app:
  [MaxCoil Una / Dynasty Bases / Bedsense Bases profile](keeson.md#ore-comfort-bed-profiles)),
  Power's Bedding, Ultramatic Smart Bed
- **Asian markets:** Jobs 賈伯斯 (Taiwan), Koizumi (Japan), Minamoto Bed (Japan),
  M line, Berun, Alya, Nerum, IST
- **Other brands:** Simon Li (see the
  [Keeson app profiles](keeson.md#simon-li-heal-every-night-and-okin-seating-profiles),
  which also cover Heal Every Night and OKIN-Seating), Cherish Smart, Support
  挺你, Apex, Doublesleep, OkinSmartComfort, OrmatekTechnoSmart, INNOVA (SFM)
  (current app: [INNOVA profile](keeson.md#innova-profile)), RÖWA, Flexsteel
  Pulse, A H Beard, Hankook Gallery, beds with the DewertOkin HE150 controller

The 79 apps use one of these protocols:

| Protocol | Apps | Service UUID | Guide |
|---|---|---|---|
| FFE5/Keeson | 31 | `0000ffe5-...` | [Keeson](keeson.md) |
| OKIN UUID | 19 | `62741523-...` | this guide |
| FFE0/Solace | 19 | `0000ffe0-...` | [Solace](ff_frame.md#solace-name-routes) |
| Nordic UART | 5 | `6e400001-...` | [Mattress Firm 900](okin-5a.md#mattress-firm-900--iflex) |
| FFF0/WiLinke | 2 | `0000fff0-...` | [Leggett & Platt](leggett-platt.md) |

| App | Package ID | Protocol |
|---|---|---|
| MFRM Sleepy's Elite | `com.okin.bedding.sleepy` | Multi-protocol |
| Resident | `com.okin.resident.release` | Flutter |
| Rize II | `com.okin.bedding.rizeii` | OKIN UUID |
| Simmons | `com.okin.simmons` | Flutter; own frames, see [SIMMONS app](#simmons) |
| Glideaway | `com.ore.bedding.glideawaymontion` | E6 FE 16 on FFE5/FFE9, [explicit Motion app profile](keeson.md#glideaway-motion) |
| Symphony | `com.ore.bedding.symphony` | FFE5 + Nordic |
| INNOVA/SFM | `com.ore.sfm` | FFE9/FFE4, little-endian E5 FE 16; see the [INNOVA profile](keeson.md#innova-profile) |
| OkinSmartComfort | `com.okin.okinsmartcomfort` | OKIN UUID + Nordic |

The complete app listing was `disassembly/output/OKIN_MASTER_ANALYSIS.md`.

### RF ECO BT stair lift

**App:** [OKIN Smart Remote / FurniMove](https://play.google.com/store/apps/details?id=com.okin.okinsmartcomfort) 2.2.0 (19), `com.okin.okinsmartcomfort`

**Status:** ✅ Tested (reporter hardware in [#344](https://github.com/kristofferR/ha-adjustable-bed/issues/344))

> [!WARNING]
> This controls a moving staircase, not a bed. It exposes one cover entity named
> `Stair` for a moving staircase actuator. Automations should only run where
> motion is safe, visible and supervised.

The [ELDA-BTH product page](https://elda-treppen.de/produkt/bth/) describes the
system as a semi-automatic loft stair with a quiet maintenance-free spindle
motor, gas spring support, switch and/or radio remote control, and electrical
emergency lowering.

#### Setup

Use manual setup and choose **OKIN Smart Remote / RF ECO BT single actuator**
(bed type `okin_rf_eco_bt`). Detection: none from advertisements.

- Choose it only for a single moving actuator. RF ECO BT is also the receiver
  for adjustable beds; for a bed controlled by the FurniMove app choose
  **[FurniMove / OKIN Smart Remote](furnimove.md)** and its exact handset ID, and
  for another app that app's profile.
- Legacy RF ECO BT entries receive an offline layout repair, including entries
  with a configured count of one. Explicit staircase confirmation prevents the
  repair from returning while preserving the existing Stair entity.
- The integration requests a Bluetooth bond, as it does for Okimat beds.

**Device identification.** The reported device advertises as `OKIN-050226` with
no service UUIDs, so it cannot be auto-detected safely from advertisements.
Diagnostics can identify it after connecting from the Okin service and write
characteristic plus CSS service `90311623-25fa-3346-12ef-3cfb7a2556ac` and CSS
write characteristic `90311625-25fa-3346-12ef-3cfb7a2556ac`. Nordic DFU service
`00001530-1212-efde-1523-785feabcd123` on the same device may mean this profile
or a full bed using [Okin CST](#okin-cst); it is not a safe discriminator, and
an already configured RF ECO BT or CST profile is preserved when these signals
disagree with it. Full OKIMAT beds and RF ECO BT bed receivers expose the same
GATT signature, so it cannot choose a topology alone:

| Model | Device |
|---|---|
| `MEGAMAT MBZ` | The single-actuator ELDA staircase from #344 |
| `OKIMAT 4 IPS/M` | The multi-motor Lattoflex bed from [#406](https://github.com/kristofferR/ha-adjustable-bed/issues/406) |
| `RF eco BT` | A two-motor bed receiver using RF-TOPLINE handset `82620`, also reported in #344 |

- The exact `MEGAMAT MBZ` model remains the stronger staircase signal.
- For other shared-GATT receivers, explicitly selecting a valid handset code
  under the Okin UUID profile is stronger evidence than the generic receiver
  identity and keeps the multi-motor controller active.
- Generic `OKIN-*` devices remain ambiguous because several unrelated OKIN
  protocols use that naming pattern.

#### Controls

Open and close send the M2 out and in keys from the
[RF ECO BT table](#rf-eco-bt-keys); stop ends the held refresh. No presets, memory,
lights, massage or position feedback. The generic zero frame is not a valid
staircase STOP: the reporter found it switched a light on, while ending the
refresh stopped motion, so the integration never sends it here.

#### Timing

The direction refresh uses the app's interval with the configured, bounded
pulse count (see the [timing table](#hold-and-release-timing)). Cancellation
always clears the held motor state.

**Connection.** Home Assistant keeps this profile's BLE connection open,
including when **Disconnect After Command** is enabled.

- In the reporter's [4.1.1 test](https://github.com/kristofferR/ha-adjustable-bed/issues/344#issuecomment-6036101893),
  the normal 40-second idle disconnect left the receiver advertising but unable
  to reconnect, with GATT timeouts. Retaining the connection worked reliably,
  including after a Home Assistant restart.
- The FurniMove profile applies the same policy when the receiver reports the
  `RF eco BT` model and a connect to it has timed out or aborted, after a bed
  receiver showed the same reconnect failures
  ([#633](https://github.com/kristofferR/ha-adjustable-bed/issues/633)). Other
  profiles are unchanged.
- Keeping the link open occupies a Bluetooth connection slot and may prevent a
  companion app from connecting.
- After an unexpected drop, Home Assistant schedules one automatic reconnect
  using the connection profile's bounded retry budget. Recovery sends no
  movement command. If it fails, the next command or **Connect** action can try
  again; no background retry loop runs.
- Manual Disconnect remains available and cancels both scheduled and in-progress
  automatic recovery.
- The receiver may still need a power cycle if GATT timeouts recur; keeping the
  link open is a tested workaround, not an explanation of those timeouts.

#### Evidence

The accepted audit of `com.okin.okinsmartcomfort` 2.2.0 (19) proves the shipped
offline two-axis fallback table's M2 keys and the six-byte frame; the M2
staircase mapping comes from #344. If M2 is not the right channel for another
installation, mapping it needs that owner's OKIN Smart Remote ID or QR contents;
do not add M3, reversed, DOT or RF-Gateway variants to this profile without new
evidence. See the [FurniMove ledger](../apk-analysis/dispositions/157-furnimove.md).

### Customatic family

**Status:** ❓ Needs testing (APK-verified, physical operation unverified)

The three apps share one frame, transport and timing; each is its own bed type.

| Profile | Package | Motors | Memory page | Light |
|---|---|---|---|---|
| Clarity | `com.okin.bedding.customaticclarity` | Back, legs | Yes | Toggle |
| Jerome's | `com.okin.bedding.customaticjeromes` | Back, legs | No | None |
| Remedy | `com.okin.bedding.customaticremedy` | Back, legs, lumbar | Yes | Toggle |

#### Setup

Select **Customatic Clarity app**, **Customatic Jerome's C app** or **Customatic
Remedy app** (or **Customatic apps** → Clarity / Jerome's C / Remedy) to match
the Android app supplied with the bed. Detection: none.

- The apps scan for the case-sensitive name prefixes `OKIN` and `iFlex_Bed`,
  which identify candidates, not the app. They share their service, command
  characteristic and names, and Device Information strings do not select
  capabilities either, so the profile is a manual choice.
- Each package hard-codes its app layout; unreachable product selectors create
  no extra variants.
- Clarity and Remedy can reconnect to a saved address. Jerome's reconnect
  branch is unreachable; selecting a physical bed slot directly remains
  reachable.
- **Write mode:** the apps leave the Android write type unchanged, so the
  runtime value is unknown. HA validates the exact command service and
  characteristic, and writes with response when it advertises `write`, otherwise
  without response when it advertises only `write-without-response`. This is an
  implementation choice, not a claim about the app or every physical bed.
- No notification subscription, position read, massage, pairing or
  authentication, custom settings write, firmware update or MTU negotiation.

#### Controls

See the [Customatic table](#customatic-keys).

- **Motors:** back and legs, plus lumbar on Remedy. Motors held together OR their
  bits, so `back_up+legs_up` sends `04 02 00 00 00 05`.
- **Flat:** see each profile.
- **Memory page** (Clarity and Remedy): five independently held controls, Flat,
  ZG, ANTI, Program and Incline. HA keeps their literal names instead of giving
  ZG or ANTI a physical meaning, and they are not numbered memory slots. The
  **ZG**, **ANTI**, **Incline**, **Program**, **Save ZG** (Program + ZG), **Save
  Incline** (Program + Incline) and **Reset** (Flat + Program) buttons hold their
  mask for the app's confirmation threshold (see the
  [one-shot timing](#one-shot-timing) note); it is not a hardware
  acknowledgement or proof of storage. Flat + ZG and Flat + ANTI remain literal
  combinations; the app's unused `resetMemory()` helper does not make Flat + ZG
  a reset.
- **Light** (Clarity and Remedy): one toggle frame, no release. Its state and
  brightness are unknown; HA exposes no inferred state or discrete on/off.
- **Device Information** (service `0000180a-0000-1000-8000-00805f9b34fb`),
  read in this order: manufacturer `2a29`, hardware revision `2a27`, software
  revision `2a28`, firmware revision `2a26`, model `2a24`. The app schedules them
  at 0/120/240/360/480 ms after connecting and retries the whole batch from its
  information screen if a cached field is null. HA reads all five at connection
  discovery and offers **Refresh Device Information** for a whole-batch retry,
  serialized with at least 120 ms spacing and a two-second bound per read.
  Missing characteristics or failed reads keep cached values and never block
  controls. Values decode UTF-8 with replacement, like Java; empty strings are
  values, not missing fields. The sensors are `customatic_manufacturer`,
  `customatic_hardware_revision`, `customatic_software_revision`,
  `customatic_firmware_revision` and `customatic_model`; diagnostics include them.
  No field selects frames, the app or capabilities, and none needs a
  notification channel or angle sensing.

#### Timing

See the [timing tables](#hold-and-release-timing). Explicit Stop sends the zero
mask immediately.

- Cleanup runs after cancellation and outside the requested movement deadline.
  HA's duration is an elapsed-time ceiling for the refresh, so no extra refresh
  follows the deadline.
- The configured pulse count applies to ordinary cover actions; the interval
  stays the app's.
- All motor covers of one physical bed share the global scheduler resource,
  because zero releases every motor: a Stop from any axis preempts movement on
  another. Two-address paired children keep separate physical-side resources.

#### Services

**Move motors together:** `adjustable_bed.customatic_move_simultaneously` takes
an `actions` mapping of `back`, `legs` and, for Remedy, `lumbar` to `up` or
`down`, plus a duration in seconds.

- Different motors may run in opposite directions: all eight safe states for two
  motors and all 26 for three.
- Axes are ordered back, legs, lumbar, with equivalent held-control strings such
  as `back_up+legs_down+lumbar_up`.
- Opposite directions on one motor are rejected before any write.

**Hold memory controls:** `adjustable_bed.customatic_hold_memory` takes any
nonempty subset of `flat`, `zg`, `anti`, `program` and `incline` in `actions`;
all 31 subsets OR their bits. The duration accepts 0.1-60 seconds in whole
milliseconds.

```yaml
action: adjustable_bed.customatic_hold_memory
data:
  device_id: YOUR_BED_DEVICE_ID
  actions: [program, zg]
  duration: 2.7
```

- Duplicate or unknown controls, empty selections and mixed motor and memory
  selections are rejected before writing.
- HA starts the selected composite mask immediately on one refresh lane. It does
  not replay Android touch-down sequences or their phase-dependent first tick,
  which keeps the reachable masks while giving the action a deterministic
  duration.

**Paired beds:** Jerome's app can send the same frame to two selected beds. Use
an explicit two-address HA pair or target both devices. These profiles have no
frame-side selector and no single-address logical pair. HA supplies connection
checks, command serialization, cancellation and reconnects instead of the app's
constant-true connection check.

#### Evidence

Each Customatic profile sends only its frozen frames. Exclusions and app
behaviors HA does not replay are in the
[Customatic ledger](../apk-analysis/dispositions/row028-customatic.md). Physical
verification of movement labels, save and reset effects, light behavior and
write-property compatibility is deferred to users after release.

### Customatic Clarity

**App:** [Customatic Clarity](https://play.google.com/store/apps/details?id=com.okin.bedding.customaticclarity) 1.0.1, `com.okin.bedding.customaticclarity`

**Status:** ❓ Needs testing

Behaves as the [Customatic family](#customatic-family), except as below.

#### Controls

Flat sends the Flat word once.

### Customatic Jerome's

**App:** [Customatic Jerome's](https://play.google.com/store/apps/details?id=com.okin.bedding.customaticjeromes) 1.0.1, `com.okin.bedding.customaticjeromes`

**Status:** ❓ Needs testing

Behaves as the [Customatic family](#customatic-family), except as below.

#### Controls

- No memory page, no light and no lumbar.
- Flat (the fresh screen) sends its alternate Flat word three times in a row,
  with no interval or release.
- Its restored fragment has a separately reachable generic Flat: the
  **Restored Flat** button sends the restored word once. That persisted route
  does not justify switching every Flat to it.

### Customatic Remedy

**App:** [Customatic Remedy](https://play.google.com/store/apps/details?id=com.okin.bedding.customaticremedy) 1.0.1, `com.okin.bedding.customaticremedy`

**Status:** ❓ Needs testing

Behaves as the [Customatic family](#customatic-family), except as below.

#### Controls

Adds the lumbar motor. Flat sends the Flat word once.

### Leggett Okin family

**Status:** ⚠️ Partially tested (Prodigy CE / CU170 hardware-tested in #368; the other app profiles are statically verified, hardware unverified)

#### Setup

- Bed type `leggett_okin`, or `leggett_platt` with its `okin` variant (see
  [Leggett & Platt](leggett-platt.md)). **Detection:** device names containing
  "leggett", "l&p" or "lp bed" tell these beds from Okimat and Nectar beds on the
  same service UUID.
- Choose the app profile matching the bed's remote app. The default remains
  **Prodigy CE / Prodigy 4**, preserving existing configurations. Device names
  and shared service UUIDs cannot establish the physical actuator layout.
- App profile and wire revision are independent. The app picks the frame once
  per connection: the plain frame (revision 1) when the revision selector
  characteristic exists under the service, the
  [envelope](#framing-and-checksum) (revision 0) when it does not. The
  integration applies the same check after service discovery, records the
  revision in diagnostics, and refuses to guess when service discovery is
  unavailable.
- Configure each side before combining two separately addressed beds; shared
  paired options keep each side's app profile. Unpair temporarily to change it.
- **Pairing** is required. Neither app calls `createBond`, but the write
  characteristic needs an encrypted link, so Android bonds reactively on the
  resulting ATT error 5. An authentication failure while connecting clears the
  cached bond marker and allows automatic pairing retries; a verified retry
  suppresses the pairing repair. Failed, inconclusive or cancelled recovery still
  raises it, and command-time authentication errors stay visible.
- **Write mode:** CU170 hardware testing measured a 217-218 ms motion watchdog,
  so the integration writes without response and measures the interval from the
  start of each write. Awaiting a confirmed write and then sleeping adds the BLE
  round trip to every gap, which repeatedly crossed the watchdog over a WiFi
  Bluetooth proxy and made the motor stop and restart. The pairing and write
  policies come from hardware testing, not from APK calls.
- BLE only: Classic RFCOMM paths in Prodigy 2 and U Series are outside this
  integration's transports.

#### Controls

See the [Leggett Okin table](#leggett-okin-keys). Held keys combine into one frame.

> [!WARNING]
> **Do not trust the `FBP_KEYCODE_*` constant names in decompiled output.**
> Several are wrong for this hardware: `0x00800000` is declared
> `LIGHT_INTENSITY_DOWN`, but the shipped massage screen binds it to head massage
> **down**. The layout binding and the write boundary are the authority; both
> independent analyses of Prodigy CE reached this separately.

- **Flat** is a held button, not a recall.
- **Memory store** (`0x00010000`) arms the box to overwrite a slot and must never
  appear in the recall ladder. Earlier releases used a ladder shifted one step up
  (`0x2000`…`0x10000`), so every memory button recalled its neighbour and
  "Memory 4" streamed the store-arm key for 30 seconds, which could reprogram a
  slot with whatever position the bed was in.
- **Massage** power is a toggle with no discrete off, so there is no massage-off
  button; the wave key is the mode-step button. There is no massage timer:
  `0x00000200` is an app constant (`FBP_KEYCODE_M5_IN`, a fifth actuator
  channel) never bound to a control or written.
- **Light and massage** keys are held keys: a tap leaves one command interval
  before the release burst. Previously the first zero could follow the press
  immediately, making the light toggle too short to register. The precise
  minimum hardware debounce is not established.

**Hold control:** `adjustable_bed.hold_control` exposes bounded holds for flat,
Snore, lighting and massage; U Series also permits memory 1, memory 2 and SET.
The released `leggett_hold_control` name still works with the same list. The
movement services cover motor holds.

#### Timing

See the [timing tables](#hold-and-release-timing).

| Command family | Lifecycle |
|---|---|
| Held keys (motors, flat, light, massage) | Stream while held; on release exactly four zero frames, then silence |
| Recalls (memory slots, Snore) | A fixed burst with no terminator: the box drives the move to completion itself, and a release could cancel it |
| Flat | No app-defined duration: the integration streams it for the Flat hold at the configured pulse delay, never faster than the profile's interval, then releases |
| Control mode | The settings dialog's attempts, then one zero frame |

- A recall interrupted by cancellation or a write failure ends with the zero
  release.
- LP Control 2.9.0 uses a 200 ms cadence where Prodigy CE uses 100 ms; the
  integration uses the accepted Prodigy/U Series cadence and the recorded CU170
  policy.

#### Notifications

The status characteristic acknowledges accepted writes and also reports
physical-remote actions. The app reconstructs an LED/status mask (see
[Responses](#responses)) but only gives meaning to sleep timer (`0x8000`) and
alarm (`0x4000`). No parsed value influences a later command. There is **no
position, angle, percentage or motor-state feedback**.

The integration retains raw LED-mask and signed-status sensors and reads the
standard Device Information strings for diagnostics. U Series applies its app's
low-byte suppression to the indicators while keeping the raw mask.

#### Services

`adjustable_bed.leggett_sleep_timer` and `adjustable_bed.leggett_alarm_timer`
start or cancel native timers. The services validate the profile's actions and
ranges before writing; see their action descriptions for fields.

| Command | Profiles | Word | Range |
|---|---|---|---|
| Sleep timer | Prodigy | Plain frame `04 02 FF <favorite - 1> <minutes, 16-bit big-endian>` under either revision | Favorite 1-4, 1-1439 minutes |
| Sleep timer | U Series | `0xFF000000` with the action bits and minutes OR'd in; follows the selected revision | Flat `0x00100000`, memory 1 `0x00000000`, memory 2 `0x00010000`, memory 3 `0x00020000`; 15-90 minutes in 15-minute steps |
| Sleep cancel | All | `0xFF200000` | |
| Alarm | All | `0xFD000000` + minutes | 1-1440 minutes |
| Alarm cancel / stop | Prodigy | `0xFD200000` | |
| Alarm cancel / stop | U Series | `0xFD000000` | |

- All three Prodigy apps disable 00:00 in their sleep picker; their zero-to-1440
  branch is not a selectable duration. U Series' third sleep memory is distinct
  from a direct recall button.
- Timer commands, including the Prodigy plain sleep frame, use the recall burst.
  A successful timer has no zero tail; an interrupted one ends with the release.

#### Evidence

Each Leggett profile sends only its frozen frames, plus the CU170 stop on Prodigy
CE. The [Leggett app ledger](leggett-app-disposition.md) records the four
accepted reports, app differences and transport exclusions.

### Prodigy 2L

**App:** [Prodigy 2L](https://play.google.com/store/apps/details?id=com.leggett.prodigy2L) 1.2 (15), `com.leggett.prodigy2L`

**Status:** ❓ Needs testing (statically verified)

Behaves as the [Leggett Okin family](#leggett-okin-family), except as below.

#### Controls

Head, feet and lumbar. Four favorites: Favorite 1, Favorite 2, the fixed Snore
entry (wire slot 3, which has no save and no separate Zero-G action) and
Favorite 3. Programming holds the store key, switches directly to the slot, then
sends the ordinary release (see the [one-shot timing](#one-shot-timing) note).
The app's reset and slot assignment are consecutive calls in one callback, so the
integration inserts no zero gap between the stages. The shipped user guide
agrees: "Touch Save… the massage motors will buzz once. Within 5 seconds, touch
the Favorite Position being edited."

**Control mode:** press-and-hold and press-and-release buttons rather than a
select, because no notification reports the active mode. On boxes with the
optional Smart Remote settings service, notification setup also sends the
settings initialization write.

### Prodigy 2

**App:** [Prodigy 2](https://play.google.com/store/apps/details?id=com.leggett.prodigy2) 2.2.0 (44), `com.leggett.prodigy2`

**Status:** ❓ Needs testing (statically verified)

Behaves as [Prodigy 2L](#prodigy-2l), except that the third motor is the pillow
instead of lumbar.

### Prodigy CE (Prodigy 4)

**App:** [Prodigy CE / Prodigy 4](https://play.google.com/store/apps/details?id=com.leggett.prodigy4) 1.2.0 (18), `com.leggett.prodigy4`

**Status:** ⚠️ Hardware-tested on CU170 in [#368](https://github.com/kristofferR/ha-adjustable-bed/issues/368)

Behaves as [Prodigy 2L](#prodigy-2l), with head, feet, pillow and lumbar, except
as below.

#### Controls

- **Stop all** first sends the reporter's hardware-tested DUMMY key (CU170 stop
  in the table), then the ordinary release. It interrupts a latched preset or
  preset-save sequence, which zero alone does not, uses the selected revision
  (`E5 FE 16 00 04 00 00 02` / `04 02 00 04 00 00`) and ignores the cancelled
  movement's cancel event. Ordinary end-of-hold cleanup still sends only zero.
  This comes from the
  [September hardware report](https://github.com/kristofferR/ha-adjustable-bed/issues/368#issuecomment-5747783066),
  not an app command.
- **Control mode:** #368 reports that SET+FLAT (press-and-hold) factory-resets the
  CU170 and wipes its presets, so HA removes the press-and-hold button and refuses
  the command even from an old entity. Use the physical remote's procedure.
  Press-and-release stays available.
- Successful recalls keep the app's burst; explicit interruption needs the DUMMY
  key, while cancellation or a write failure uses the zero cleanup.

#### Notifications

The [CU170 hardware report](https://github.com/kristofferR/ha-adjustable-bed/issues/368#issuecomment-5481326088)
gives the physical meaning absent from the app.

- A 20-byte status frame on the status characteristic (see
  [Responses](#responses)) carries the CU170 status mask. The first trailing byte
  reads `01` while massage wave mode runs and `FF` in every other frame observed
  (owner captures and debug log, 2026-07 to 2026-10). Frames of another length or
  with mismatched dwords are ignored.

| CU170 status mask | Meaning |
|---|---|
| `0x00020000` | Under-bed light on |
| `0x00400000` | Alarm armed |
| `0x00800000` | Sleep timer armed |

- A toggle's receipt holds the **old** light state; a separate spontaneous
  notification holds the **new** state, including physical-remote changes. Every
  valid notification is processed, not one receipt per write.
- Alarm and sleep indicators use these masks once a CU170 frame is recognized,
  instead of the app's labels, and settings notifications cannot overwrite them.
  CU170 frames have no signed-status field.

**Light entity:** on and off toggle only when the known state differs, then wait
up to three seconds for confirmation; a missing confirmation leaves the light
unknown and reports an error without retrying. State is not restored across Home
Assistant sessions and clears on disconnect. After subscribing, startup sends the
app's four idle zero frames, which request live status without toggling the
light (the September report confirms a key write refreshes status); without a
valid reply the state stays unknown. The redundant **Toggle Light** button is
removed; `light.toggle` stays available, as does the physical remote.

**Remaining hardware observations:**

- The reporter measured one light pulse when memory storage arms and three when a
  preset is saved; those pulses also change the real light state.
- Programming keeps the app's bounded arm-then-slot sequence. An
  acknowledgement-driven version needs paired raw traces of both initial light
  states, and must never combine SET with FLAT. The store path sends each key
  separately.
- The CU170 can be set for latched or hold-required presets. Recalls use the
  app's burst; `adjustable_bed.hold_control` gives an explicit held duration for
  hold-required boxes. Flat keeps its bounded hold.
- Worth a capture if you have the equipment: which revision real units use,
  whether recall truly ends without a terminator, whether changing control mode
  resets editable favorites on all firmware, and whether the tap interval
  registers reliably on local adapters and wireless proxies.

### U Series

**App:** [U / Ultra Series](https://play.google.com/store/apps/details?id=com.leggett.useries) 2.1 (16), `com.leggett.useries`

**Status:** ❓ Needs testing (statically verified)

Behaves as the [Leggett Okin family](#leggett-okin-family), except as below.

#### Controls

- Head, feet and pillow.
- Two held memory keys, a held Snore control and a held SET key, all through
  `adjustable_bed.hold_control` with an explicit duration. There are no one-shot
  Memory 1, Memory 2 or Snore buttons, no four direct favorites and no composite
  favorite programming.
- No control-mode settings and no settings-channel initialization.
- Its alarm-stop key differs from the Prodigy profiles; see
  [Services](#services-1).

### OKIN SmartBed CB24

**App:** [OKIN Smart Bed](https://play.google.com/store/apps/details?id=com.okin.bedding.smartbedwifi), `com.okin.bedding.smartbedwifi`

**Status:** ❓ Needs testing

#### Setup

- Detection: the OKIN manufacturer ID (89) on a Nordic UART receiver. The
  SmartBed app's product profile picks the variant: CB24, CB24AB, CB27, CB1221
  and Dacheng (and the `cb_old` alias) send the legacy 40-bit frames; CB27New
  (and `cb_new`) send CBNew packets.
- Transport: the Nordic UART write characteristic, written without response.
- Legacy CB24 has one-address side selectors: both sides `00`, Side A / Left
  `AA`, Side B / Right `BB` (see
  [single-address side controls](../CONFIGURATION.md#single-address-left--right-controls)).
  CBNew packets have no selector.

#### Controls

Legacy variants send the [CB24 keys](#cb24-keys) with the selector byte last.
Held motors combine in one word. The CBNew variants send their own packets for
motion, presets, lights and massage: `2A 00 00 01 01 04 <word, little-endian>`
for motion, `2A 00 00 01 03 01 <index>` for presets, `AA 00 00 01 02 00` for
STOP, `2A 00 00 02 01 01 <code>` for massage and a discrete
`AA 00 00 04 01 05 00 <on> 00 00 00 00` light switch. Both families set an exact
massage level with `03 03 <zone> <level> <selector>`.

> [!WARNING]
> On the CBNew variants, overall massage intensity up and down still send the
> legacy [CB24 keys](#cb24-keys), and the exact massage level sends the legacy
> `03 03` frame. Every other CBNew control uses CBNew packets. No accepted report
> covers this app (the SmartBed 2.4.2 analysis is PARTIAL), so whether CBNew
> receivers accept these frames is unproven.

#### Timing

Motors refresh at the entry's pulse settings, then one STOP. Presets and memory
recalls are one packet; see [CB.24 Preset Safety](#cb24-preset-safety).

#### Evidence

Frames are the pre-v5 controller's, frozen in `tests/okin_nframe_vectors.py`;
`tests/test_okin_cb24.py` covers both packet families.

### Okin DOT

**App:** [FurniMove](https://play.google.com/store/apps/details?id=com.okin.okinsmartcomfort) (earlier analysis; accepted 2.2.0 audit), `com.okin.okinsmartcomfort`

**Status:** ❓ Needs testing (untested: protocol from APK + live handset backend, no hardware confirmation yet)

All keycodes come live from the DewertOkin handset backend
(`GET /mobile-data/button/{code}`); the snapshot lives in
`tools/okin_remotes/master.json` with `protocol: "dot"`.

#### Setup

##### Known models

"DOT PROTOCOL" is DewertOkin's name (it appears verbatim in RF34 handset
descriptions) for receiver boxes that pair with the RF1058, RF34, and RF6707
RF handsets.

- The handset remote codes resolve through the same FurniMove backend as the
  [Okimat](okin-nframe.md#okimat) codes.
- The box itself is a CB24-family receiver: it exposes the Nordic UART service
  instead of the Okin `62741523` service and takes CB24-style 7-byte frames.

###### Remote codes

| Code | Handset | Motors | Extras |
|------|---------|--------|--------|
| 90167 | RF1058 | Head + Feet | 4 memories, zero-g, quiet sleep, head/foot massage |
| 91983 | RF1058 | Head + Feet | 3 memories, zero-g, anti-snore, head/foot massage |
| 93558 | RF1058 | Head + Feet | 3 memories, zero-g, anti-snore, head/foot massage |
| 97450 | RF34/09/WH/GY | Back + Legs | 2 memories |
| 97544 | RF34/09/BK/BK | Back + Legs | 2 memories |
| 98035 | RF6707 | Head + Back | Motors + light only |

The motor keycodes are **renumbered per handset**: whichever two motor channels
the handset drives, the first pair is `0x1`/`0x2` and the second is `0x4`/`0x8`
(unlike the fixed Okimat bit assignment). The channels keep their section
meaning (M1=Head, M2=Back, M3=Legs, M4=Feet in FurniMove), and the integration
exposes correspondingly named controls: an RF1058 bed gets Head and Feet
covers, an RF6707 bed gets Head and Back.

##### Protocol Details

**Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e` (Nordic UART)
**Write Characteristic:** `6e400002-b5a3-f393-e0a9-e50e24dcca9e` (write without response)
**Format:** 7 bytes, `[0x05, 0x02, kc3, kc2, kc1, kc0, 0x00]`

FurniMove calls this characteristic `CB24_WRITE_CHARACTERISTIC` and flags the
connection as DOT when it is present (`BluetoothLeService.setCharacteristics`).

###### Packet Format

7 bytes (`HexValueConverter.toByteArray` with `isDOTProtocol=true`):

```text
[0x05, 0x02, kc3, kc2, kc1, kc0, 0x00]
```

- Bytes 2–5: 32-bit keycode, big-endian
- No checksum
- Identical to the [Okin CB24](../SUPPORTED_ACTUATORS.md) frame with bed
  selection byte `0x00`

###### Handshake

- The earlier FurniMove analysis this bed type came from recorded an ASCII
  `affirm` write to the write characteristic on discovery. The integration
  mirrors it once per connection before the first command.
- The accepted FurniMove 2.2.0 audit has no such write, and it also sends
  memory save, massage and some utility controls in the six-byte `04 02` format
  even on a DOT receiver.
- Okin DOT keeps its released behavior for existing entries; the FurniMove
  profile follows 2.2.0 exactly.

##### Detection / Setup

- If the code printed on your remote is **97450, 97544 or 98035**, select the
  **Okin DOT** bed type and pick that code as the protocol variant.
- For **90167, 91983 or 93558**, new setups use the [FurniMove](furnimove.md)
  app profile instead: its pinned catalog covers those handsets and follows the
  app's per-control frame format. Existing Okin DOT entries with those codes
  keep working and receive a repair offering the switch. Their keycodes come
  from the FurniMove catalog either way.
- Entries configured as Okimat/Okin UUID are also rescued automatically: if the
  connected box has no Okin `62741525` characteristic but does expose Nordic
  UART, the integration promotes the entry to the Okin DOT bed type (persisted,
  which also drops the Okimat pairing requirement) and falls back to the default
  DOT remote (`97450`) until a printed DOT code is selected. Standard Okimat
  keycodes are never wrapped in DOT frames.

#### Controls

##### Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Two motors per handset (Head + Feet, Back + Legs, or Head + Back) |
| Position Feedback | ❌ (none known) |
| Memory Presets | ✅ RF1058 and RF34 codes (recall is a short press, save is a hold) |
| Massage | ✅ RF1058 codes (head/feet +/−, wave, stop) |
| Under-bed Lights | ✅ Toggle |
| Flat | ✅ |
| Zero-G / Quiet Sleep / Anti-Snore | ✅ RF1058 codes |
| BLE Pairing | ❌ Not required |

##### Commands

Values are 32-bit keycodes placed in the DOT frame.

###### Shared (all six codes)

| Command | Value |
|---------|-------|
| Stop | `0x00000000` |
| First motor Up / Down | `0x00000001` / `0x00000002` — Head on RF1058/RF6707, Back on RF34 |
| Second motor Up / Down | `0x00000004` / `0x00000008` — Feet on RF1058, Legs on RF34, Back on RF6707 |
| Flat | `0x08000000` |
| Toggle Lights (UBL) | `0x00020000` |

The DOT Flat value `0x08000000` equals the standard Okimat child-lock keycode,
one of the reasons these codes must not be driven with the Okimat profile.

###### RF1058 extras

| Command | Value |
|---------|-------|
| Zero gravity | `0x00001000` |
| Quiet sleep (90167) / Anti-snore (91983, 93558) | `0x00004000` |
| Memory 1–4 (90167) | `0x3000`, `0x5000`, `0x6000`, `0x7000` |
| Memory 1–3 (91983, 93558) | `0x2000`, `0x8000`, `0x3000` |
| Memory save (hold 5s) | `0x00010000` |
| Massage head +/− | `0x00000800` / `0x00800000` |
| Massage feet +/− | `0x00000400` / `0x01000000` |
| Massage wave | `0x10000000` |
| Massage stop | `0x00000100` |

###### RF34 extras (97450, 97544)

| Command | Value |
|---------|-------|
| Memory 1 / Memory 2 | `0x00010000` / `0x00040000` |
| Memory save (hold 2s) | `0x0001f000` (97450), `0x00010000` (97544) |

#### Timing

##### DOT command timing

- Held buttons are re-sent ~every 100ms (the app rewrites the characteristic
  on each write completion after a 100ms sleep).
- Release sends keycode `0x00000000` (`DisobeyStandbyTime`) as the stop.
- Memory recall is a **short press** (one frame + STOP); save is the hold:
  5s @ 200ms on RF1058, 2s @ 200ms on RF34. On 97544 recall and save share
  keycode `0x10000`; only the press duration distinguishes them.
- The light key is a hold too (5s @ 100ms per the backend).

#### Evidence

##### Notes

- After releasing a button, FurniMove also writes a raw 2-byte `00 B0` packet
  ~400ms after the stop keycode. Its function is unknown (possibly re-arming
  the box's standby timer); the integration does not send it. If a tester
  reports motors that keep creeping after stop, this is the first thing to try.
- The RF34 97544 handset uses the same keycode (`0x00010000`) for Memory 1
  recall and memory save. On the physical remote, saving is holding the
  memory button. A short press recalls, the 2s hold stream saves.

###### Differences from Okimat

| | Okimat (okin_uuid) | Okin DOT |
|---|---|---|
| Service | `62741523-...` | Nordic UART `6e400001-...` |
| Frame | 6-byte `04 02 <kc BE>` | 7-byte `05 02 <kc BE> 00` |
| Write | With response | Without response |
| Pairing | Required | Not required |
| Position feedback | Yes (FFE4 notify) | None known |
| Handshake | None | `affirm` on connect |

###### Source Code References

- `custom_components/adjustable_bed/beds/okin_dot.py` — controller
- `disassembly/output/com.okin.okinsmartcomfort/jadx/sources/com/dewertokin/okinsmartcomfort/service/utils/HexValueConverter.java` — DOT framing
- `disassembly/output/com.okin.okinsmartcomfort/jadx/sources/com/dewertokin/okinsmartcomfort/service/bleModule/bluetooth/BluetoothLeService.java` — DOT detection + `affirm` handshake

### SIMMONS

**App:** [SIMMONS](https://play.google.com/store/apps/details?id=com.okin.simmons) 1.12.9 (code 99), `com.okin.simmons`

**Status:** ❓ Needs testing (static-verified only, **hardware unverified**)

#### Setup

##### Known models

- Beds controlled with the SIMMONS app (Android package `com.okin.simmons`), regular and inclined bed types
- OKIN- and SmartBed-named receivers; these names are shared with other apps
- Other `Simmons*` beds without this app follow [DewertOkin](okin-nframe.md#dewertokin)

##### Protocol Details

| Role | Service | Characteristic |
|---|---|---|
| Write | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` |
| Notify | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` |
| Write | `0000ffe5-0000-1000-8000-00805f9b34fb` | `0000ffe9-0000-1000-8000-00805f9b34fb` |
| Notify | `0000ffe0-0000-1000-8000-00805f9b34fb` | `0000ffe4-0000-1000-8000-00805f9b34fb` |

**Format:** Two packet formats (OKIN and SmartBed) sharing one 32-bit control mask

- Services are matched in discovery order and the last match of each role wins,
  independent of the packet format.
- A connection without both a write and a notify role fails, as the app
  disconnects.
- Notifications stay subscribed with angle sensing off.

###### Packet Format

| Format | Frame | Checksum |
|--------|-------|----------|
| OKIN | `E6 FE 16` + mask little-endian + `00` + checksum | (255 − sum of the preceding bytes) & 255 |
| SmartBed | `05 02` + mask big-endian + `00` | None |

###### Write Mode

- OKIN-format frames are written with response (Android's default write type).
- SmartBed-format frames are written without response.

##### Detection / Setup

Select **SIMMONS app** manually. OKIN and SmartBed Bluetooth names and the
Nordic UART or FFE5 services are shared with other apps, so they never select
this profile. Existing entries keep their bed type until you change it.

###### Configuration

The protocol variant carries two independent choices from the app:

| Variant | Bed type | Packet format |
|---|---|---|
| `auto` (default) | Regular | From the Bluetooth name |
| `simmons_okin` / `simmons_smartbed` | Regular | Fixed |
| `simmons_inclined` | Inclined | From the Bluetooth name |
| `simmons_inclined_okin` / `simmons_inclined_smartbed` | Inclined | Fixed |

Name rule:

- The rule is the app's, which reads Android's device (GAP) name; HA sees the
  advertised name or BlueZ alias instead.
- HA keeps the raw Bluetooth name from setup and from later real (non-address)
  observations, never the entry's display name. An address-like live name
  (BlueZ uses the address when a bed sends no name) falls back to that stored
  raw name.
- The lowercased name is checked for a `smartbed` prefix, then an `okin` prefix,
  with no trimming. Any other name, including a missing one, uses the SmartBed
  format, as the app does for a reconnect to a saved bed whose name matches
  neither prefix.
- Use a fixed variant if Home Assistant sees a different name than the phone.
- In a two-address pair the variant belongs to each physical bed, so the
  combined options form refuses variant changes: unpair, set each bed, then
  combine them again.

Bed type and motors:

- The app offers the inclined bed type only in its Japanese language setting;
  the profile offers it regardless of language.
- Motor count is fixed at two (back, legs).
- Position feedback, massage and pairing do not exist in the app.

##### Home Assistant setup

Choose **SIMMONS app** manually. OKIN and SmartBed names and the shared Bluetooth services do not identify this app. The protocol variant selects the app's bed type (regular or inclined) and, optionally, the packet format. `auto` keeps a regular bed and applies the app's name rule: a name starting with `smartbed` or any unmatched name uses SmartBed frames, a name starting with `okin` uses OKIN frames. Motor count is fixed at two and the 300 ms refresh is fixed. The variant belongs to each physical bed: split a two-address pair before changing it.

#### Controls

##### Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (fixed at two motors: back, legs) |
| Position Feedback | ❌ (does not exist in the app) |
| Memory Presets | ✅ (Custom Mode recall; **Save Custom Mode** by a 5.5 s hold) |
| Presets | ✅ Flat; Zero gravity, TV/PC and Anti-snore on a regular bed |
| Inclined controls | ✅ **Inclined Left/Middle/Right** on an inclined bed |
| Massage | ❌ (does not exist in the app) |
| Under-bed Light | ✅ |
| Alarms and clock | ✅ (two alarm slots, clock sync) |
| Pairing | ❌ (does not exist in the app) |

##### Commands

The 32-bit control mask is shared by both formats.

###### Motor Control

| Control | Mask | OKIN frame | SmartBed frame |
|---|---|---|---|
| Back up | `0x1` | `E6 FE 16 01 00 00 00 00 04` | `05 02 00 00 00 01 00` |
| Back down | `0x2` | `E6 FE 16 02 00 00 00 00 03` | `05 02 00 00 00 02 00` |
| Legs up | `0x4` | `E6 FE 16 04 00 00 00 00 01` | `05 02 00 00 00 04 00` |
| Legs down | `0x8` | `E6 FE 16 08 00 00 00 00 FD` | `05 02 00 00 00 08 00` |
| STOP | `0` | `E6 FE 16 00 00 00 00 00 05` | `05 02 00 00 00 00 00` |

###### Presets

| Control | Mask | OKIN frame | SmartBed frame |
|---|---|---|---|
| Flat | `0x08000000` | `E6 FE 16 00 00 00 08 00 FD` | `05 02 08 00 00 00 00` |
| Zero gravity (regular) | `0x1000` | `E6 FE 16 00 10 00 00 00 F5` | `05 02 00 00 10 00 00` |
| TV/PC (regular) | `0x4000` | `E6 FE 16 00 40 00 00 00 C5` | `05 02 00 00 40 00 00` |
| Anti-snore (regular) | `0x8000` | `E6 FE 16 00 80 00 00 00 85` | `05 02 00 00 80 00 00` |

###### Memory

| Control | Mask | OKIN frame | SmartBed frame |
|---|---|---|---|
| Custom Mode memory | `0x10000` | `E6 FE 16 00 00 01 00 00 04` | `05 02 00 01 00 00 00` |

There is no separate save frame; **Save Custom Mode** holds the recall frame
(see [Command Timing](#simmons-command-timing)).

###### Lights

| Control | Mask | OKIN frame | SmartBed frame |
|---|---|---|---|
| Under-bed light | `0x20000` | `E6 FE 16 00 00 02 00 00 03` | `05 02 00 02 00 00 00` |

###### Inclined controls

| Control | Mask | OKIN frame | SmartBed frame |
|---|---|---|---|
| Inclined left / middle / right | `0x10` / `0x1000` / `0x20` | SmartBed frame, written with response | `05 02 00 00 00 10 00` / `05 02 00 00 10 00 00` / `05 02 00 00 00 20 00` |

The inclined controls always send the SmartBed frame, even with the OKIN format
selected; the profile reproduces this. Their physical roles are unknown, so they
are exposed as **Inclined Left/Middle/Right** buttons. The middle mask equals
zero gravity.

#### Timing

##### SIMMONS command timing

| Operation | Behavior |
|-----------|----------|
| Every held control | Repeats every 300 ms |
| Release | Two STOP frames, at +100 ms and +400 ms |
| Covers | Configured pulse count at the fixed 300 ms interval |
| Preset, Custom Mode recall, light and inclined buttons | App taps: the button-down frame once, no 300 ms refresh, then the two release STOPs |
| **Save Custom Mode** | Holds the recall frame for 5.5 s |
| Longer holds | Use `hold_control` |

- On release the app schedules two STOP frames, at +100 ms and +400 ms. HA sends
  both from one release origin with fresh cancellation events, even if the
  movement was cancelled or a write failed.
- Every release is global, so all axes share one command resource.
- App taps have no 300 ms refresh because the press is already released. The app
  enforces no minimum preset hold. Whether a tap completes a preset on the bed,
  or the bed needs a hold, is unverified.
- **Save Custom Mode** timing: the app's help says to hold M for 5 seconds and
  its "Custom Mode has been set" notice appears at 5.5 s. There is no separate
  save frame, and whether the bed stores the position is unverified.
- The app's own races (a new press replacing a pending STOP, repeat revival, no
  STOP on page dispose or disconnect) are not reproduced: HA serializes commands
  and always finishes the release.

#### Services

##### Alarms and clock

During connection setup, after notifications start and before any command runs,
HA writes the local clock and repeats the alarm page's queries at 0, 300 and
600 ms, so even a quick-disconnect session gets them. If that clock write fails,
`simmons_set_alarm` writes the clock first, because the alarm fires on the bed's
clock. **Sync Clock** and **Refresh Alarms** buttons repeat these.

###### Alarm frames

| | OKIN | SmartBed |
|---|---|---|
| Clock | `E7 80 01`, year−1900, month−1, day, hour, minute, second, checksum | `07 04`, year−1900, month−1, day, hour, minute, second, ISO weekday (Mon 1…Sun 7) |
| Query | `E1 80 03 9B` (both alarms) | `00 C0`, then `00 D0` 300 ms later |
| Program | `ED 80 03` + slot 1 and slot 2 records (hour, minute, weekday, type) + `00 00 00 00` + checksum | `07 05` (slot 1) or `07 06` (slot 2), weekday, type, hour, minute, `00 01 01` |
| Disable | Same frame; selected weekday and type 0, hours/minutes kept | `07 05` or `07 06` + seven zero bytes |
| Reply | `ED 80 03`: records at offsets 3 and 7; enabled unless weekday is 0 or 128 | `A5 0C 0E` / `A5 0D 0E`: weekday 4, type 5, hour 6, minute 7, open 9 |

| Alarm mode | OKIN wire type | SmartBed wire type |
|------------|---------------:|-------------------:|
| Custom Mode | 17 | 5 |
| Flat | 28 | 9 |
| Anti-snore (regular bed only) | 16 | 4 |

- These writes are not press/hold commands: a movement STOP never cancels them,
  and local records change only after the write is sent.
- Each integer is masked to one byte.

###### Weekday encoding

- The weekday is a bitmask with Sunday as bit 0 and bit 7 marking a repeat. A
  repeat mask passes through.
- A one-off alarm (mask 128) is sent as the bit of the next occurrence: today if
  the time, truncated to whole milliseconds, is not yet past, otherwise after an
  absolute 24 hours, so a DST change can shift the day.

###### Two-slot programming

- OKIN programming rewrites both slots, so the other slot's record is re-sent
  (its weekday is sent as 0 when that alarm is disabled).
- The app takes those bytes from its own local record, which carries its display
  overlay and, for a one-off alarm, the editor mask 128 that its own reply parser
  reads as disabled.
- HA instead re-sends exactly what the bed reported for that slot on the current
  connection, which is safer than the app: it preserves the bed's current state,
  including changes made by another app while HA was away.
- The slot being programmed uses the requested values; a disabled slot keeps the
  hour and minute the bed reported.
- The written record is remembered as pending until an exactly matching reply
  arrives. After a write, HA queries again 300 ms later.
- The written slot shows the requested values at once but counts as unreported
  until the bed confirms it, so a later write on the same connection queries
  first and never resends an unconfirmed value.

###### `simmons_set_alarm` rules

- Follows the app's rules: Custom Mode needs `confirm_custom_mode` (the app warns
  that extreme custom angles can cause injury), and an enabled alarm cannot share
  its time or mode with the other enabled alarm.
- Every check or write needs both records as reported on the current connection.
  Otherwise HA sends the alarm query and waits up to 2 s (an integration-side
  guard, not an app value), then refuses with nothing written.
- Records kept from an earlier connection stay visible in the sensors but never
  feed a conflict check or the other slot's record, so an alarm changed in the
  app while HA was away is not undone.

###### Replies

- Reply overlays match the app: an enabled OKIN record keeps the locally known
  weekday, and a disabled SmartBed record keeps the local hour, minute and
  weekday; a SmartBed record with open=1 and all fields zero counts as disabled.
- A 20-byte notification whose bytes 1–2 are `FE 16` is joined with the next one.
- Records too short for their header are ignored whole.

###### Differences from the app

- Alarm records belong to each physical bed rather than one global phone
  setting; they live in memory, so after an HA restart the first reply is taken
  as reported.
- Local records change only after a successful write.
- HA never enables an alarm with wire type 0, which the app can do by
  re-enabling a disabled slot.
- The display overlay is kept for the sensors only; every write uses the bed's
  raw report from the current connection.

###### Alarm sensors

**Alarm 1** and **Alarm 2** sensors show the time, with attributes for enabled,
mode, wire type, weekday mask and whether a reply is awaited.

#### Evidence

##### Notes

###### Validation requests

For real users after a beta or release:

- Whether each name prefix matches the bed's actual protocol
- Which GATT roles the bed exposes
- Whether a preset tap completes the motion or needs a hold
- What the inclined controls move
- Whether the bed accepts SmartBed inclined frames in OKIN mode
- How the light responds to a hold
- How alarm replies report one-off alarms (HA re-sends the reported weekday for
  the other slot, where the app would send mask 128)

###### Analysis provenance

- Accepted APK Protocol Audit of `com.okin.simmons` version 1.12.9 (code 99), a
  20-APK XAPK.
- Artifact-set SHA-256: `b5ef1222e24ad9bdf5b2d513fbc7a9aece2b63269c0e8d9632e2596837ffc70f`
- Behavior is static-verified only: **hardware unverified**.
- Comparison ledger: [row049](../apk-analysis/dispositions/row049-simmons.md)

### OKIN SleepEase

**App:** [OKIN SleepEase / DoubleSleep](https://play.google.com/store/apps/details?id=com.okin.doublesleep) 1.2.24 (code 109), `com.okin.doublesleep`

**Status:** ❓ Needs testing (static BLE evidence; hardware unverified)

Select **OKIN SleepEase (DoubleSleep / XiaoBao)** for the `com.okin.doublesleep`
app. Support is based on the independently accepted 1.2.24 / code 109 artifact.
Hardware behavior has not been confirmed. This is a separate integration profile;
a Nordic UART service alone does not identify this app.

#### Setup

##### Known models

- OKIN SleepEase / DoubleSleep / XiaoBao app profiles below.
- Physical actuator count, sensor accuracy and independent motor-side addressing
  are unverified; use the saved app model rather than inferring them from its name.

| Model code | App label | App double predicate | Sensor/report UI |
|---|---|---|---|
| 0 | Unknown | No | Legacy |
| 2 | Single | No | Legacy |
| 3 | Double | Yes | Legacy |
| 4 | Meise | No | Legacy |
| 5 | Dormimundo | No | Legacy |
| 10135 | Sleep XiaoBao | Yes | XiaoBao |
| 10137 | Sleep XiaoBao Single | No | XiaoBao |
| 67 | Milliwave Double | No | Legacy, 18-byte records |
| 11135 | Sleep XiaoBao Only | Yes | Sensor only |
| 11136 | Sleep XiaoBao Only Single | No | Sensor only |

The source calls model 67 single even though its name contains “Double”. This
implementation follows its predicates and record layout. Model labels do not
prove physical actuator count, sensor accuracy or independently addressed motors.

##### Protocol Details

**Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
**Write Characteristic:** `6e400002-b5a3-f393-e0a9-e50e24dcca9e`
**Notify Characteristic:** `6e400003-b5a3-f393-e0a9-e50e24dcca9e`
**Format:** Independent P1 raw arrays, P2 `AA` controls / `2A` queries, or P3 nested-header JSON

###### Write Mode

Service `6e400001-b5a3-f393-e0a9-e50e24dcca9e` owns TX
`6e400002-b5a3-f393-e0a9-e50e24dcca9e` and RX
`6e400003-b5a3-f393-e0a9-e50e24dcca9e`. P1/P2 require write-without-response;
P3 requires write-with-response. RX supports notify or indicate through the
backend. No app PIN, bonding or authentication exchange is present.

###### Packet Format

P1 uses its own `05 02` / raw-array builders. P2 uses its separate `aa` command
families and `2a` query families. They must not be interchanged. P3 uses compact
ordered UTF-8 JSON (`id`, `cmd`, `val`), a sequence advancing for both JSON and
fragments, and a 14-byte nested header. Fragments fit negotiated ATT MTU minus 3
and the one-byte inner-body length. No fixed MTU is requested or assumed.

| P3 component | Exact layout |
|---|---|
| Outer header | `type sequence count index body_length 00 00` |
| Inner header | `11 03 59 44 59 chunk_length_low chunk_length_high` |
| JSON | Compact UTF-8 `{"id":sequence,"cmd":command,"val":value}` |
| Outer type | `02` for setters / initialization, `00` for queries |
| Sequence | Increments modulo 256 once for JSON ID and again for each fragment |
| Fragment payload | `min(MTU - 3, 497, 262) - 14` bytes; at most 255 fragments |

Values in binary templates below are bytes unless stated otherwise. `LE16` means
two little-endian bytes. Integer fields use the controller's byte coercion.

##### Detection / Setup

Setup asks for the saved app model and the BLE driver separately. Automatic driver
selection uses the advertisement name and company 89 payload. It waits for an
advertisement rather than guessing an offline driver's controls. An explicit P1,
P2 or P3 selection is available when the advertisement cannot be recovered.
Changing a saved UI model does not change the driver inferred from an advertisement.

| Selection | Rule in the shipped selector |
|---|---|
| Discovery | Platform name begins with `sleepbt`, `osleepbt` or `osleepbts`, case-insensitive; company 89 must supply an app identity |
| P3 driver | Advertisement name begins with `osleepbt`, case-insensitive |
| P2 driver | Otherwise company 89 has at least 7 bytes and payload byte 6 plus 1 is 135 or 137 |
| P1 driver | Remaining advertisements after the P3/P2 checks |
| Saved model | Separate platform-name / company-data selector; user confirms the model independently |

#### Controls

##### Features

| Feature | P1 | P2 | P3 |
|---------|----|----|----|
| Motor Control | ✅ Head, foot, lumbar, headrest, hips | ✅ Same axes | ❌ |
| Position Feedback | ❌ | ❌ | ❌ |
| Presets | ✅ Held recalls | ✅ One-shot recalls | ❌ |
| Memory Presets | ✅ Two numbered recalls | ✅ Two numbered recalls, six named save targets | ❌ |
| Massage | ✅ Regular | ✅ Regular or capability-gated sonic | ❌ |
| Lights | ✅ Toggle | ✅ Toggle using reported settings | ❌ |
| Alarm | ✅ | ✅ | ❌ |
| Anti-snore configuration | ✅ | ✅ Slow settings require MFP capability | ❌ Query only |
| Sensitivity configuration | ❌ | ✅ Binary builder | ✅ JSON builder |
| Privacy and live sensor state | ✅ | ✅ | ✅ |
| Reports | ✅ Legacy | ✅ Day/month or saved legacy UI | ✅ Day/month |
| Local child lock | ✅ | ✅ | ✅ |
| Single-address motor-side pairing | ❌ | ❌ | ❌ |

Capabilities also depend on the independently saved UI model. A sensor-only
saved model has no bed controls even if its selected driver is P1 or P2;
an action whose driver builder is unavailable fails before writing.

##### Controls and state

P1 and P2 expose the app's five labelled axes: head, foot, lumbar, headrest and
hips. The headrest uses HA's pillow control and hips use its hip control. Presets
include Flat, Zero gravity, Anti-snore, Lounge/Reading, TV and two numbered recalls.
P1 recall is held; P2 recall is one-shot. P2 can save all six non-Flat targets.
All movement uses the protocol's STOP on release and cancellation. The native
card receives held-control metadata for the axes and P1 presets.
The app shares one held-movement stream across motor controls. A card Stop
cancels that shared software stream; hardware effects across axes remain unverified.

Controller buttons expose regular massage, P2 sonic massage when its MFP function
list contains 7, light toggle, privacy, explicit state/version queries and legacy
history retrieval. P1 massage on/off share the same toggle packet and P1 time down
has no packet. These aliases are preserved. P2 relative commands use notification
state without optimistic increments. Light toggle replays its reported mode and
four settings; no unsupported color or brightness writes are invented.

The child lock is a local, persisted HA preference with the app's exact command
filter. It does not program a handset lock. STOP remains available. Sensor-only
P3 has no movement, presets or massage controls. Sensor sides are fields in one
physical device's data, not a way to route movement to one half. Single-address
motor pairing is therefore unavailable. Two physical entries retain their own
model, driver and cached settings when combined.

Sensors expose left/right heart and breath values, status, two raw sensor flags,
rolling eight-value history, sensitivity, privacy, alarm, capabilities, firmware
and sensor versions, massage state and report results. Units follow the app's
bpm/brpm labels, with physical accuracy unverified. No measured motor position,
angle, battery or current is inferred.

##### Commands

Tables are taken from
[`DoubleSleepController`](../../custom_components/adjustable_bed/beds/doublesleep.py)
and its [`protocol builders`](../../custom_components/adjustable_bed/doublesleep_protocol.py).
Indices identify builders, not a raw-packet service. UI model, child-lock and
reported capability gates still apply.

###### Motor Control

| Index | Command | P1 bytes | P2 bytes |
|---|---|---|---|
| 1 | STOP / release | `05 02 00 00 00 00 00` | `AA 00 00 01 01 04 00 00 00 00` |
| 2 | Head up | `05 02 00 00 00 01 00` | `AA 00 00 01 01 04 01 00 00 00` |
| 3 | Head down | `05 02 00 00 00 02 00` | `AA 00 00 01 01 04 02 00 00 00` |
| 4 | Foot up | `05 02 00 00 00 04 00` | `AA 00 00 01 01 04 04 00 00 00` |
| 5 | Foot down | `05 02 00 00 00 08 00` | `AA 00 00 01 01 04 08 00 00 00` |
| 8 | Lumbar up | `05 02 00 00 00 40 00` | `AA 00 00 01 01 04 10 00 00 00` |
| 9 | Lumbar down | `05 02 00 00 00 80 00` | `AA 00 00 01 01 04 20 00 00 00` |
| 10 | Headrest up | `05 02 00 00 00 10 00` | `AA 00 00 01 01 04 40 00 00 00` |
| 11 | Headrest down | `05 02 00 00 00 20 00` | `AA 00 00 01 01 04 80 00 00 00` |
| 12 | Hips up | `05 02 40 00 00 00 00` | `AA 00 00 01 01 04 00 01 00 00` |
| 13 | Hips down | `05 02 80 00 00 00 00` | `AA 00 00 01 01 04 00 02 00 00` |
| 27 | App all stop | `05 02 00` | `AA 00 00 01 02 00` |

STOP index 1 is the release frame. Index 27 is the distinct app all-stop frame;
P1's three-byte `05 02 00` is not padded into its seven-byte STOP packet.

###### Presets

| Index | Command | P1 bytes | P2 bytes |
|---|---|---|---|
| 14 | Memory 1 recall | `05 02 00 01 00 00 00` | `AA 00 00 01 03 01 05` |
| 15 | Memory 2 recall | `05 02 00 04 00 00 00` | `AA 00 00 01 03 01 06` |
| 16 | Anti-snore recall | `05 02 00 00 80 00 00` | `AA 00 00 01 03 01 04` |
| 17 | Lounge / Reading recall | `05 02 00 00 20 00 00` | `AA 00 00 01 03 01 02` |
| 18 | TV recall | `05 02 00 00 40 00 00` | `AA 00 00 01 03 01 03` |
| 19 | Zero gravity recall | `05 02 00 00 10 00 00` | `AA 00 00 01 03 01 01` |
| 26 | Flat recall | `05 02 08 00 00 00 00` | `AA 00 00 01 03 01 09` |

P1 recalls use held motion; P2 recalls are one-shot. Both finish with index 1
using a fresh cancellation event.

###### Memory

| Index | Command | P1 bytes | P2 bytes |
|---|---|---|---|
| 20 | Save Memory 1 | Unavailable | `AA 00 00 01 05 01 25` |
| 21 | Save Memory 2 | Unavailable | `AA 00 00 01 05 01 26` |
| 22 | Save Anti-snore | Unavailable | `AA 00 00 01 05 01 24` |
| 23 | Save Lounge | Unavailable | `AA 00 00 01 05 01 22` |
| 24 | Save TV | Unavailable | `AA 00 00 01 05 01 23` |
| 25 | Save Zero gravity | Unavailable | `AA 00 00 01 05 01 21` |

Each supported save is followed by release index 1. These actions program the
corresponding physical preset; Flat has no save action.

###### Massage

| Index | Command | P1 bytes | P2 bytes |
|---|---|---|---|
| 28 | Massage on / toggle | `05 02 00 00 01 00 00` | `AA 00 00 02 01 01 40` |
| 29 | Massage off / toggle | `05 02 00 00 01 00 00` | `AA 00 00 02 01 01 41` |
| 31 | Massage time up | `05 02 00 00 02 00 00` | See dynamic table |
| 32 | Massage time down | See dynamic table | See dynamic table |
| 35 | Head massage up | `05 02 00 00 08 00 00` | See dynamic table |
| 36 | Head massage down | `05 02 00 80 00 00 00` | See dynamic table |
| 37 | Foot massage up | `05 02 00 00 04 00 00` | See dynamic table |
| 38 | Foot massage down | `05 02 10 00 00 00 00` | See dynamic table |
| 40 | Massage mode up | `05 02 10 00 00 00 00` | See dynamic table |
| 41 | Massage mode down | `05 02 04 00 00 00 00` | See dynamic table |
| 50 | Query massage | `00 B0` | `2A 00 00 02 81 01 03` |
| 51 | Query sonic massage | Unavailable | `2A 00 00 06 81 00` |

P1 index 32 has an empty builder and sends no bytes. P1 on/off share a toggle;
P1 foot-down and mode-up also share their exact packet. P2 uses the notification
cache, not optimistic increments.

**P2 relative builders**

The following are **cold-cache examples**, not fixed packets. Regular cache
starts with running/mode/head/foot/time all 0. Sonic starts with source/mode 1
and head/foot/time 0. Notifications determine later writes.

| Index | Command | Cold-cache P2 bytes |
|---|---|---|
| 31 | Massage time up | `AA 00 00 02 01 01 49` |
| 32 | Massage time down | `AA 00 00 02 01 01 4B` |
| 35 | Head massage up | `AA 00 00 02 01 01 50` |
| 36 | Head massage down | `AA 00 00 02 01 01 52` |
| 37 | Foot massage up | `AA 00 00 02 01 01 54` |
| 38 | Foot massage down | `AA 00 00 02 01 01 56` |
| 40 | Massage mode up | `AA 00 00 02 01 01 42` |
| 41 | Massage mode down | `AA 00 00 02 01 01 45` |
| 79 | Sonic head up | `AA 00 00 06 02 03 00 01 04` |
| 80 | Sonic head down | `AA 00 00 06 02 03 00 01 08` |
| 81 | Sonic foot up | `AA 00 00 06 02 03 00 02 04` |
| 82 | Sonic foot down | `AA 00 00 06 02 03 00 02 08` |
| 83 | Sonic mode up | `AA 00 00 06 03 02 00 02` |
| 84 | Sonic mode down | `AA 00 00 06 03 02 00 06` |
| 85 | Sonic time up | `AA 00 00 06 0B 06 00 03 57 02 57 02` |
| 86 | Sonic time down | `AA 00 00 06 0B 06 00 03 07 07 07 07` |

| Relative family | Encoding after computing notification-relative `r` |
|---|---|
| Regular time/head/foot/mode | `AA 00 00 02 01 01 (base+r)`, bases `48` / `4F` / `53` / `41` respectively |
| Sonic mode | `AA 00 00 06 03 02 00 r` |
| Sonic head/foot | `AA 00 00 06 02 03 00 zone level`, zone `01` / `02`; level is 0 when `r=0`, otherwise `2*(r+1)` |
| Sonic time | `AA 00 00 06 0B 06 00 03 LE16(600*r-1) LE16(600*r-1)` |

`r` follows `relative()` exactly: time cycles 1–3, regular mode 1–4, sonic mode
1–6, sonic head/foot 0–3 and regular head/foot 0–4. Regular head/foot down uses
the separate branch `1 -> 4`, below 1 `-> 3`, otherwise `value - 1`.

**Sonic source and power**

| Index | Command | P1 bytes | P2 bytes |
|---|---|---|---|
| 87 | Sonic normal source | Unavailable | `AA 00 00 06 05 02 00 00` |
| 88 | Sonic music source | Unavailable | `AA 00 00 06 05 02 00 01` |
| 89 | Sonic on | Unavailable | `AA 00 00 06 0C 02 00 01` |
| 90 | Sonic off | Unavailable | `AA 00 00 06 0C 02 00 00` |

Sonic controls require MFP function 7. Regular control actions are unavailable
while the sonic UI is selected.

###### Lights

| Index | Command | P1 bytes | P2 bytes |
|---|---|---|---|
| 54 | Query light | Unavailable | `2A 00 00 04 81 00` |
| 58 | Toggle light | `05 02 00 02 00 00 00` | See dynamic table |

| Dynamic command | P2 bytes |
|---|---|
| Toggle light (58) | `AA 00 00 04 01 06 mode toggle c1 c2 c3 c4` |

The light cache starts with six zeros. `toggle` is 1 only when reported on/off
is 0; mode and all four settings are replayed without inventing brightness or
color commands.

###### Alarm, state, privacy and legacy queries

| Index | Command | P1 bytes | P2 bytes |
|---|---|---|---|
| 48 | Disable alarm | `07 05 00 00 00 00 00 00 00 00` | `AA 00 00 03 02 08 01 00 00 00 00 00 00 00` |
| 52 | Query alarm | `00 C0` | `2A 00 00 03 81 01 01` |
| 53 | Query state | `00 B0` | `2A 00 00 07 81 00` |
| 59 | Privacy on | `01 B2 01` | `AA 00 00 07 02 01 01` |
| 60 | Privacy off | `01 B2 00` | `AA 00 00 07 02 01 00` |
| 63 | Disable anti-snore | `02 0B 00 00 01` | `AA 00 00 07 01 08 00 02 01 01 00 00 00 00` |
| 64 | Confirm legacy history (internal) | `01 B3 01` | `01 B3 01` |
| 66 | Download legacy history | `01 B1 02` | `01 B1 02` |
| 73 | Read sensor version / initialize P3 | Unavailable | `2A 00 00 08 81 00` |

###### Dynamic binary configuration

| Index | Command | P1 bytes | P2 bytes |
|---|---|---|---|
| 47 | Clock | `07 04 (year-1900) (month-1) day (ISO_weekday-1) hour minute second` | `AA 00 00 03 01 08 (year-2000) month day ISO_weekday hour minute second UTC_hours` |
| 49 | Alarm | `07 05 massage preset hour minute 00 01 01 days` | `AA 00 00 03 02 08 01 days preset 01 hour minute 00 massage` |
| 57 | MFP capabilities | Unavailable | `2A 00 00 05 81 09 page FF FF 00 00 22 25 12 4B` |
| 62 | Anti-snore | `02 0B operation strength_code 01` | `AA 00 00 07 01 08 operation 02 mode 01 pwm timer 00 00` |
| 67 | Sensitivities | Unavailable | `AA 00 00 07 04 03 side left right` |
| 72 | Daily report | Unavailable | `2A 00 00 07 opcode 03 (year%2000) month day`, opcode `84` left / `85` right |
| 72 | Monthly report | Unavailable | `2A 00 00 07 opcode 02 (year%2000) month`, opcode `86` left / `87` right |

- P2/P3 clock UTC hours truncate the local offset toward zero. Binary fields wrap
  through the builder's byte conversion; report service years are restricted to
  2000–2255 before writing.
- Alarm `days` uses Sunday-first day bits `01 02 04 08 10 20 40`; repeat sets
  `80`. Preset values are Zero gravity `01`, Flat `09`, Memory 1 `05`,
  Memory 2 `06`, Vibration `08`. Massage is `00` or `01`.
- Anti-snore operation is `01` apply or `02` demo. P1 strength code is `01`
  for mode 1, `03` for mode 2, `06` for mode 3. P2 sends mode 1–3 directly.

###### P3 JSON commands

All values below use the nested P3 envelope above. The JSON object is always
ordered `id`, `cmd`, `val`; report `part=side+1` and `type=kind+1` with
left/day 0 and right/month 1 in the service request.

| Index | Command | `cmd` | `val` | Outer type |
|---|---|---|---|---|
| 47 | Synchronize clock | `s_time` | `{"ts":integer_epoch_seconds,"utc":integer_UTC_hours}` | `02` |
| 53 | Query anti-snore state | `q_antiSnore` | `{}` | `00` |
| 55 | Query clock | `q_time` | `{}` | `00` |
| 59 | Privacy on | `q_realtime` | `{"time":1}` | `00` |
| 60 | Privacy off | `q_realtime` | `{"time":65535}` | `00` |
| 68 | Set sensitivities | `s_sens` | `{"L":[left],"R":[right],"ret":0}` | `02` |
| 69 | Query sensitivities | `q_sens` | `{}` | `00` |
| 71 | Query sensor sides | `q_part` | `{}` | `00` |
| 72 | Query report | `q_report` | `{"part":part,"type":type,"y":year,"m":month,"d":day}` | `00` |
| 73 | Initialize sensor | `s_init` | `0` | `02` |
| 77 | Refresh realtime | `q_realtime` | `{"time":65535}` | `00` |
| 78 | Allow report (internal) | `q_report` | `{"allow":1}` | `00` |

#### Timing

##### SleepEase command timing

| Operation | Timing / cleanup |
|---|---|
| Held card controls and P1 held presets | 300 ms start-based refresh; finite HA hold of 100–60000 ms; fresh STOP in `finally` |
| Motor pulse helper | 300 ms cancellable wait between writes, then fresh STOP |
| Regular massage; sonic level/mode/time/on/off | Query corresponding state after 200 ms |
| Sonic source (87/88) | Command only; no followup state query |
| Alarm set / disable | Query alarm after 300 ms |
| Sensitivity update | Query state / sensitivities after 200 ms |
| Anti-snore apply / demo | Immediate close / distinct app all-stop cleanup |
| P2 report header timer | 5 seconds, retaining the source's cancellation and decode-error ordering |
| Owned report exchange | 5 seconds without report progress; progressing transfers may continue longer |
| Legacy transfer | 500 ms quiet interval, then internal confirmation 64; no overlap through confirmation |
| GATT write completion | 15-second bound per write |

##### Wire and lifecycle reference

Writes are serialized and awaited, errors stop a fragment batch and each write
has the source plugin's 15-second completion bound. Report cancellation ends the
connection before another request can borrow a late response. RX callbacks from
an old client are ignored. A persistent connection supports sensor data and
report continuation; explicitly disconnect to hand the link to the phone app.
Unexpected link loss immediately invalidates connection timers and queued work.

#### Notifications

##### Position Feedback / Notifications

Notification parsers retain the source's branch ordering, P1 massage formulas,
P2 regular/sonic caches, header-selected report side/mode, empty-P2 completion,
monthly text dispatch, P3 char-code single-packet decoder and retained fragment
index. Callback/device ownership, timer cancellation and connection cleanup are
covered by focused tests. Caches survive reconnects for one physical target and
are cleared on profile/address removal by HA's app-session infrastructure.
They are not shared across beds. Numeric caches and sequence survive a logical
view reload; view capabilities and rolling histories survive reconnects but
start cold when their coordinator is recreated.

#### Services

##### Configuration and reports

Use `adjustable_bed.doublesleep_configure` with a physical bed device target.
The action selector offers:

- `alarm`: hour, minute, optional repeating weekdays, an app alarm action and
  massage. Empty weekdays schedule the next occurrence once. The app's Sunday
  day-bit overflow is corrected using its proven Sunday-first weekday layout.
  Clock calibration precedes setup; the alarm is queried after 300 ms. The Disable
  alarm button uses the separate close command and subsequent query.
- `anti_snore` and `anti_snore_demo`: app strength/mode 1–3. The operation byte is
  selected by the action. Apply sends the source's immediate close command;
  demo sends its distinct app all-stop command. Optional slow PWM/timer byte
  settings require the reported slow-anti-snore MFP capability. Omitted values
  use its reported/default settings (PWM 30 when supported, timer 10).
- `sensitivities`: optional P2 sensor-side value 1–3 and left/right Low, Medium or
  High values (1–3). Omitted fields retain reported values, defaulting to both
  sensors and Low on a cold view. P3 can read sensor sides but has no reachable
  side-setting action.
  The saved sensor-only UI uses P3's JSON command; the other UI uses P2's binary command. An unavailable
  builder fails before writing. State is queried after 200 ms.
- `report`: left/right sensor side, day/month and date. P2 and P3 report profiles
  expose this action. The binary year must fit its 2000-based byte. A request owns
  the connection until a result. Five seconds without report progress ends the
  exchange; a progressing transfer can continue longer. The app's five-second
  indication does not abort its transfer. P3's allow-report continuation runs
  inside the owned operation.
- `save_preset`: P2 Memory 1/2, Anti-snore, Lounge, TV or Zero gravity, followed by
  release. This changes the corresponding physical bed preset.
- `capabilities`: the app's MFP page byte. The app uses page 0 during connection and
  page 1 for slow-anti-snore settings. The resulting function/capability state is
  available in the configuration sensor attributes.

Report status 0 means data, 1 means empty and 2 means the app's busy/timeout result.
Report sensor attributes preserve the original daily map or monthly JSON text,
all returned fields, the selected side and the app consumer's typed/defaulted
records. Missing and null fields receive the app's defaults. Scalars and array
members require integers; text fields require strings. Unknown wire keys remain
in the raw data. A malformed report is recorded as a parser error, without publishing a
successful decoded report. No local health score or month-chart aggregation is
calculated. The app's page navigation, SQL cache and cloud fallback are not HA
report triggers; report retrieval is explicit here.

Legacy UI models use the Download legacy history button. The controller captures
12/16/18-byte records, waits for the source's 500 ms quiet interval, retains raw and
normalized record fields, then confirms completion. It does not send a speculative
all-history command. P2 with a saved legacy UI model uses the legacy request too.
Overlapping downloads are rejected until the first transfer and its completion
confirmation finish.

#### Evidence

##### Notes

###### Analysis provenance

See the [complete disposition ledger](../apk-analysis/dispositions/row107-doublesleep.md)
for accepted identities, exhaustive coverage, safety differences and exclusions.
Actual negotiation, ATT/firmware effects and physical movement/sensor meanings
remain checks for real users after a beta or release.

### Sleepy's legacy CB25

**App:** [MFRM Sleepy's Elite](https://play.google.com/store/apps/details?id=com.okin.bedding.sleepy), `com.okin.bedding.sleepy`

**Status:** ❓ Needs testing

#### Setup

The Sleepy's Elite app speaks two dialects to its BOX25 receivers over Nordic
UART, chosen by the Device Information manufacturer: `star` selects StarCode
(`5A` frames, the [Okin 5A](okin-5a.md) layout), anything else, or nothing,
selects this legacy CB25 dialect. Setup, sessions and feedback are shared and
described in the [Sleepy's guide](sleepys.md).

#### Controls

The controller keeps the StarCode action surface and frames each action as the
[Sleepy's legacy CB25 keys](#sleepys-legacy-cb25-keys): 40-bit key frames, a
few 64-bit `08 02` frames for the light toggle and massage waves, `04 E0`
setting frames for light on/off, massage level and timer, `03 F0` position
targets and the `00 D0` position request.

#### Timing

The app's one sender drives both dialects, so the timing is this profile's data
for both: see the [one-shot timing](#one-shot-timing) table. A preset's trailing
STOP commits it (#372).

#### Evidence

Frames are the pre-v5 translation table's, frozen in
`tests/okin_nframe_vectors.py`. The app ledger is in the [Sleepy's guide](sleepys.md).

### AdjustableM5X4

**App:** [AdjustableM5X4](https://play.google.com/store/apps/details?id=com.starcode.abm5_4) 1.0.1 (3), `com.starcode.abm5_4`

**Status:** ❓ Needs testing (implemented profile covered by artifact vectors and focused tests; hardware operation is unverified)

This profile belongs to `com.starcode.abm5_4` 1.0.1 (3), delivered as five APK
members. It preserves this app's commands and state rules separately from other
StarCode, Sleepys and shared-UART applications. A brand, device-name prefix or
service UUID alone does not identify the app profile. See the
[row004 disposition](../apk-analysis/row004-dispositions.md) for accepted identity,
required work and every exclusion.

#### Setup

##### Known models

- StarCode beds operated with the AdjustableM5X4 app. The app's ten command
  enums (`none`, `BOX15`, `BOX24`, `BOX1220`, `BOX1221`, `BOX2422`, `BOX2442`,
  `BOX3633`, `BOX25`, `BOX25_STAR`) are application enums, not ten verified
  hardware models.
- Three live transports: the `BOX1220` service (names starting `BLE`), the
  `BOX3633` service, and Nordic UART (names starting `Star`). See
  [GATT and connection](#gatt-and-connection).

##### Protocol Details

**Service UUID:** per live transport (D route), see the table below
**Format:** Action-specific frames for each command selector (C); see [Frame matrix](#frame-matrix)

###### GATT and connection

| Live D route | Service | Write | Receive | Normal writes | App subscription |
|---|---|---|---|---|---|
| D3, `BOX1220` | `00001000-0000-1000-8000-00805f9b34fb` | `00001001-0000-1000-8000-00805f9b34fb` | `00001002-0000-1000-8000-00805f9b34fb` | Without response | Enabled |
| D7, `BOX3633` | `62741523-52f9-8864-b1ab-3b3a8d65950b` | `62741525-52f9-8864-b1ab-3b3a8d65950b` | `62741625-52f9-8864-b1ab-3b3a8d65950b` | With response | Role assigned, not subscribed |
| D8/9, UART | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | Without response | Enabled |

- The D1 FFE9/FFE4 branch has no current writer and is excluded. Restoring C1
  does not make D1 reachable: its packet/parser can operate over an independent
  live D route.
- Actual characteristic properties come from the peripheral. Notification versus
  indication and CCCD writes are host transport responsibilities.
- Device Information service `180a` contains manufacturer `2a29` and firmware
  `2a28` roles, expanded to standard Bluetooth UUIDs.

###### Write Mode

- UART initialization sends the common wake packet **with response**, with one
  immediate retry on failure; normal UART command writes remain without
  response.
- D7 (`BOX3633`) normal writes use write with response; D3 and UART use
  without response.

###### Frame structure

- Frames are action-specific for each C.
- BOX15's selected frames append the complement of bytes 0–7; BOX1220's
  selected seven-byte frames place the complement of bytes 2–6, with
  destination byte 2 zeroed, in byte 2.
- Other groups do not acquire a checksum through family resemblance. There is no
  proved additional encryption, sequence number or nonce.
- Native vector tables cover all exact action arrays and fallbacks; equal on/off
  frames in some variants remain distinct app actions.

##### Independent selectors

The app has three selectors. **C** chooses command bytes and the parser; **D**
chooses GATT roles and normal write mode; **U** determines which parsed fields the
UI consumes, its positive control gates and preset release behavior. They can
diverge. A restored C value remains usable before, or without, an optional
manufacturer result; C is not a transport-readiness barrier.

| C ordinal | Exact enum | Parser | Positive controls |
|---|---|---|---|
| 0 | `none` | Legacy BOX24 formulas | Restoration-only gate |
| 1 | `BOX15` | BOX15 length/header branches | Restoration-only gate |
| 2 | `BOX24` | Legacy BOX24 formulas | Restoration-only gate |
| 3 | `BOX1220` | Legacy BOX24 formulas | Conditional retained state |
| 4 | `BOX1221` | Legacy BOX24 formulas | Restoration-only gate |
| 5 | `BOX2422` | Legacy BOX24 formulas | Restoration-only gate |
| 6 | `BOX2442` | Legacy BOX24 formulas | Restoration-only gate |
| 7 | `BOX3633` | Legacy BOX24 formulas | Conditional retained state |
| 8 | `BOX25` | Modern BOX25 formulas | Modern parsed-state gate |
| 9 | `BOX25_STAR` | Modern BOX25 formulas | Modern parsed-state gate |

- These are application enums, not ten verified hardware models. All ten C
  values have conditional live routes.
- Five enums share a tested packet matrix without becoming one selector.
- The app restores a missing preference as C0 and accepts ordinals 0–9; invalid
  stored values throw in the app. HA must reject invalid configuration safely.

###### Detection and transport classification

- Scanning applies `platformName.toLowerCase().startsWith("star")`.
  Constructors instead use case-sensitive `Star` for D8, `BLE` for D3 and
  otherwise D7. Thus a lowercase `star` name can scan successfully and construct
  D7.
- The manufacturer characteristic's exact string `star` selects C/D9; another
  result selects C/D8 in the UART classification path. Both D choices retain the
  same UART role pair and write mode, so the callback changes D without
  reopening a different channel. This callback does not update U.
- No service or manufacturer-data acceptance filter is supplied to scanning;
  company key 89 is printed as a diagnostic.
- Remembered reconnection uses the stored identity/name.

###### Persisted fields and options

- The integration's persisted fields are `starcode_abm5_4_command_selector`,
  `starcode_abm5_4_transport_selector` and `starcode_abm5_4_ui_selector`. Their
  configuration and public runtime have focused test coverage; the UI selector
  is retained/internal rather than an additional ordinary user picker.
- Automatic transport selection may use the original Bluetooth name; explicit
  app selection supplies the application contract.
- Each physical address owns its selectors, observed state and operation
  generation.
- Options transport changes check the exact selected service and write/receive
  roles when the receiver is already connected and its GATT tree is available.
  A mismatch leaves the saved settings unchanged.
- Disconnected receivers, including those still advertising, remain unverified
  until startup; options do not open another connection.
- Auto uses the retained original BLE name and requires an explicit transport
  when that identity is unavailable.

##### Home Assistant setup

Choose the AdjustableM5X4 app profile explicitly. Star names offer this app as a candidate, while existing receiver detection remains available. The original Bluetooth name chooses transport independently of the saved command/parser selector. Manufacturer classification can update the command selector without changing the retained UI selector. “Use detected transport profile” copies the current transport into both app selectors while retaining this physical bed’s observed timer/light/massage state. Single-address side control is unsupported; two-address pairs retain each child’s settings.

#### Controls

##### Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Head/back and foot/legs up/down, native union up/down, STOP |
| Position Feedback | ❌ (raw parsed fields are diagnostics, not calibrated positions) |
| Presets | ✅ Flat, TV, Lounge, Zero Gravity, Anti-Snore |
| Memory Presets | ✅ Memory A only (recall/save); named TV/Lounge/Zero Gravity saves and reset |
| Massage | ✅ Toggle; relative head/foot intensity, wave and 10/20/30-minute timer behind the observed massage-on gate |
| Floor light | ✅ Toggle, plus/minus, raw 1–6 brightness where reachable; feedback light and stateless on/off buttons per selector |
| Automatic white | ✅ (U8/9-consumed field 47 while connected) |
| Paired beds | ✅ Two-address pairs; no one-address left/right selector |

##### Commands

The required public controls are head/back and foot/legs up/down, native union
up/down, STOP, Flat, TV, Lounge, Zero Gravity, Anti-Snore, Memory A recall/save,
named TV/Lounge/Zero Gravity saves and reset. Both visual M1 and M2 in the app
invoke Memory A. No independent second memory slot is supported by this evidence.

###### Frame matrix

Exact hex frames per command selector. `none`, `BOX24`, `BOX1221`, `BOX2422`
and `BOX2442` share one table. A dash means the action is unreachable for that
selector.

| App action | C0/C2/C4/C5/C6 | C1 `BOX15` | C3 `BOX1220` | C7 `BOX3633` | C8 `BOX25` | C9 `BOX25_STAR` |
|---|---|---|---|---|---|---|
| `headUp` | `05020000000100` | `e6fe16010000000004` | `a55ade00002001` | `05020000000100` | `05020000000100` | `5a0103103000a5` |
| `headDown` | `05020000000200` | `e6fe16020000000003` | `a55add00002002` | `05020000000200` | `05020000000200` | `5a0103103001a5` |
| `footUp` | `05020000000400` | `e6fe16040000000001` | `a55adc00002003` | `05020000000400` | `05020000000400` | `5a0103103002a5` |
| `footDown` | `05020000000800` | `e6fe160800000000fd` | `a55adb00002004` | `05020000000800` | `05020000000800` | `5a0103103003a5` |
| `unionUp` | `05020000000500` | `e6fe16050000000000` | `a55adb00002004` | `05020000000500` | `05020000000500` | `5a010310300ca5` |
| `unionDown` | `05020000000a00` | `e6fe160a00000000fb` | `a55adb00002004` | `05020000000a00` | `05020000000a00` | `5a010310300da5` |
| `stop` | `05020000000000` | `e6fe16000000000005` | `a55adf00002000` | `05020000000000` | `05020000000000` | `5a010310300fa5` |
| `flatPosition` | `05020800000000` | `e6fe160000000800fd` | `a55a7900002066` | `05020800000000` | `05020800000000` | `5a0103103010a5` |
| `tv` | `05020000400000` | `e6fe160040000000c5` | `a55a7d00002062` | `05020000400000` | `05020000400000` | `5a0103103011a5` |
| `lounge` | `05020000200000` | `e6fe160020000000e5` | `a55a7e00002061` | `05020000200000` | `05020000200000` | `5a0103103017a5` |
| `zeroGravity` | `05020000100000` | `e6fe160010000000f5` | `a55a7f00002060` | `05020000100000` | `05020000100000` | `5a0103103013a5` |
| `anti` | `05020000800000` | `e6fe16008000000085` | `a55a7c00002063` | `05020000800000` | `05020000800000` | `5a0103103016a5` |
| `m1` (Memory A) | `05020001000000` | `e6fe16000001000004` | `a55a7b00002064` | `05020001000000` | `05020001000000` | `5a010310301aa5` |
| `saveM1` | `05020001000000` | `e6fe16000001000004` | `a55a7b00002064` | `05020001000000` | `05020001000000` | `5a0103103094a5` |
| `saveTv` | `05028000400000` | `e6fe160040000000c5` | `a55a7d00002062` | `05028000400000` | `05028000400000` | `5a0103103021a5` |
| `saveLounge` | `05028000200000` | `e6fe160020000000e5` | `a55a7e00002061` | `05028000200000` | `05028000200000` | `5a0103103027a5` |
| `saveZeroGravity` | `05028000100000` | `e6fe160010000000f5` | `a55a7f00002060` | `05028000100000` | `05028000100000` | `5a0103103023a5` |
| `resetMemory` | `05028800000000` | `05028800000000` | `05028800000000` | `05028800000000` | `05028800000000` | `5a0103103037a5` |
| `massageOnOff` | `05020008000000` | `05020008000000` | `05020008000000` | `05020008000000` | `05020008000000` | `5a010310305aa5` |
| `headStrengthAdd` | — | — | `05020000080000` | `05020000080000` | `05020000080000` | `5a0103103060a5` |
| `headStrengthReduce` | — | — | `05020080000000` | `05020080000000` | `05020080000000` | `5a0103103061a5` |
| `footStrengthAdd` | — | — | `05020000040000` | `05020000040000` | `05020000040000` | `5a0103103062a5` |
| `footStrengthReduce` | — | — | `05020100000000` | `05020100000000` | `05020100000000` | `5a0103103063a5` |
| `waveAdd` | — | — | `05021000000000` | `05021000000000` | `05021000000000` | `5a0103103058a5` |
| `waveReduce` | — | — | `05020400000000` | `05020400000000` | `05020400000000` | `5a0103103059a5` |
| `underbedLighting` (toggle) | `08020002000000000000` | `e6fe16000002000003` | `a55a5f00002080` | `05020002000000` | `08020002000000000000` | `5a0103103071a5` |
| `turnonUnderbedLighting` | `05020002000000` | `05020002000000` | `05020002000000` | `08020000000000000040` | `04e001010000` | `5a0103103073a5` |
| `turnoffUnderbedLighting` | `05020002000000` | `05020002000000` | `05020002000000` | `08020000000000000080` | `04e001000000` | `5a0103103074a5` |
| `change2White` (automatic white) | — | — | — | — | `05020002000400` | `5a0103103079a5` |
| `keepConnect` (wake) | `5a0b00a5` | `5a0b00a5` | `5a0b00a5` | `5a0b00a5` | `5a0b00a5` | `5a0b00a5` |
| `queryMassage` | `00b0` | `00b0` | `00b0` | `00b0` | `00b0` | `5ab000a5` |

###### Extended builders

| App action | C9 `BOX25_STAR` | Other selectors |
|---|---|---|
| `changeMassageTime` | `5a e0 04 07 value 00 00 a5` | `04 e0 07 value 00 00` |
| `changeLightBrightness` | `5a e0 04 00 value 00 00 a5` | `04 e0 00 value 00 00` |

The private builder accepts one byte (0–255); public controls use the narrower
domains below.

###### Actions and timing

| Operation | Exact app behavior | Required HA behavior |
|---|---|---|
| Movement and Memory A recall | Immediate frame, repeat every 100 ms while held; immediate STOP on up/cancel | Bounded cancellable held action; fresh-event STOP |
| Other preset hold | 100 ms stream; release STOP only for U8/9 | Preserve U-dependent release, serialized by target |
| Flat | Starts on release, runs 600 ms; cleanup follows U; save/reset combination suppresses Flat | Expose the complete release-triggered operation |
| Save/reset combination | Exact C frame starts immediately and streams through the 6 s local confirmation interval | Await bounded writes; preserve safety cleanup without claiming a device ACK |
| Massage strength step | Single shot | Relative head/foot increase/decrease only |
| Massage wave step | 100 ms stream while held | Bounded directional operation |
| Massage release | STOP at 100 ms, query at 300 ms | Same-owner delayed cleanup; obsolete callbacks cannot stop a new action |
| Automatic white | Changed U8/9-consumed field 47=true while connected starts captured C frames every 100 ms, ceasing after 5 s without STOP | Queue behind active user commands without preemption; invalidate replacement-owner callbacks |

- The six-second success toast does not prove EEPROM persistence or delivery.
- Three-packet commitment, 110-packet storage and arbitrary generic program
  frames from another app must not be imported.
- The shared app debounce accepts only elapsed sampled integer milliseconds
  **strictly greater than 500 ms** across floor-light plus/minus, brightness,
  and native on/off/toggle actions. A suppressed brightness change does not
  update local state; a rejected value does not consume the shared gate.
- Plus/minus computes a bounded request from the observed or retained level and
  does not advance that level locally, including on the non-subscribing BOX3633
  route. Native feedback or the separate slider change updates local level; a
  successful write does not prove physical brightness.

###### Held control keys

The `adjustable_bed.hold_control` action accepts `device_id`, profile-specific
`control`, `duration` in seconds (0.1–60), and an optional `side`, with
whole-target preflight before writes. The controller's internal duration is
milliseconds. Its exact 23 control keys are `head_up`, `head_down`, `foot_up`,
`foot_down`, `union_up`, `union_down`, `memory_1`, `flat`, `tv`, `lounge`,
`zero_g`, `anti_snore`, `save_memory_1`, `save_tv`, `save_lounge`,
`save_zero_g`, `save_reset`, `head_strength_up`, `head_strength_down`,
`foot_strength_up`, `foot_strength_down`, `wave_up` and `wave_down`.
Do not use another application's held-command catalog.

Standard preset buttons expose Flat, Zero G, Anti-snore, TV, Lounge and Memory A.
The `goto_preset` action accepts only slot 1; the named presets also remain
available through the profile-specific held action. Native C/U release gates apply
to every route.

##### Massage and floor light gates

###### Massage

- Massage toggle is independently reachable.
- Positive relative intensity, wave and timer requests require the observed
  massage-on gate.
- The timer's live raw inputs are 1, 2 and 3, displayed as 10, 20 and 30
  minutes. A timer select must offer only those choices; the app's `massageOff`
  path is dead, so no generic Off timer command is inferred.
- Absolute intensity, absolute modes and sonic setters are not proved controls.

###### Floor light

- Floor on/off/toggle and plus/minus are independent actions.
- The HA feedback light exists only when U8/9 consumes state and the physical
  transport subscribes. It remains unknown until a valid native callback (or
  same-address retained Home state), and commands do not optimistically change
  it.
- Other profiles expose the native toggle button. Non-feedback C7/8/9
  additionally expose stateless native on/off buttons with distinct accepted
  frames. C0/1/2/3/4/5/6 on/off builders coincide, so no discrete power switch
  or assumed on/off state is inferred.
- Brightness is a raw integer, not measured percent, lux or a calibrated
  hardware level. Zero selects the off action rather than a raw-zero slider
  frame.

| Capability gate | Exact reachable behavior |
|---|---|
| C0/1/2/4/5/6, restoration only | Positive massage gate has no enabling writer. Fresh light level 1 yields plus raw2 or minus off. No full 1–6 slider or newly built automatic-white operation. Toggle and required release/query remain reachable. |
| C3/7 | Own-address state retained from a valid modern route can keep massage/light on and timer/level values, making conditional positive controls and raw 1–6 brightness reachable. Newly consumed legacy feedback remains UI-suppressed. |
| C8/9 | Modern U8/9 feedback can enable positive massage, timer and light-level controls. A stale legacy U can still suppress updates; each command checks current observed gates. |

##### Entities and diagnostics

- The controller-specific entities include a 10/20/30 timer select, raw 1–6
  light-level number where reachable, union and light-step buttons, named
  save/reset actions, wake/query/read actions and selector/raw-state
  diagnostics.
- Their semantic keys use `starcode_abm5_4_*` for platform, translation and card
  discovery.
- Custom controls stay owned by their physical child when using a two-address
  paired entry. This app has no encoded one-address left/right selector.
- The `starcode_abm5_4_use_detected_profile` button cancels and cleans up the
  current owner's work before adopting D into C/U. It retains own-address state
  and invalidates old callbacks.
- Changing positive controls, the feedback light or the stateless native
  power-button catalog defers a capability reload until the owned connection is
  released; unchanged catalogs do not trigger reload loops.
- Each paired child persists its own selectors and rebuilds under the parent
  registry guard.
- Consumed-state diagnostics include `starcode_abm5_4_massage_on`,
  `starcode_abm5_4_light_on`, `starcode_abm5_4_wave`,
  `starcode_abm5_4_head_intensity`, `starcode_abm5_4_low_4b` and
  `starcode_abm5_4_automatic_white_flag`, alongside the 16 raw fields (`b`,
  `13`, `1b`, `23`, `2b`, `33`, `3b`, `43`, `47`, `4b`, `53`, `5f`, `67`, `6f`,
  `77`, `7f`), selectors, manufacturer, firmware, timer and light level. These
  describe parsed/application state and add no hardware units or ACK.

#### Timing

##### AdjustableM5X4 command timing

| Item | Timing |
|---|---|
| Repeated control writes | Exact 100 ms cadence |
| Manufacturer read retry | 200 ms |
| Notification retry | 2 s |
| Connected query delay | 500 ms |
| Firmware read | 1 s after the query callback |
| Normal connection timeout (explicitly selected profile) | 8 s |
| Flat | 600 ms, starting on release |
| Save / reset | 6 s confirmation interval |
| Massage release | STOP at 100 ms, query at 300 ms |
| Automatic white | Every 100 ms, ceasing after 5 s |

- Failed or absent optional classification preserves the current selector.
  Reads, query and their diagnostic results require exposure.
- The explicitly selected profile uses the app's 8 s normal connection timeout,
  including initial setup, capability probes and HA host/proxy connect attempts.
  HA connection-profile retries and backoff still apply.
- The shipped Android library defaults to an MTU 512 request; the app does not
  select it. HA/Bleak and Bluetooth proxies own MTU negotiation, so this profile
  neither requests nor claims negotiated MTU 512.
- An already-notifying app toggle-off quirk must not leave HA without a required
  live subscription.
- The app's 30 s reboot wait belongs only to the Nordic firmware updater
  completion flow, which this BLE bed-control integration does not expose.
- HA awaits the required wake and notification setup before reporting the
  session ready. A terminal failure, cancellation or change of the original
  physical target clears readiness and notification resources so a later
  connection can retry. The optional manufacturer/query tasks retain their
  separate native delays and are cancelled with a failed session.
- Repeated control writes keep the exact 100 ms cadence after a platform write
  failure, with a logged failure and no immediate retry or acknowledgement
  claim.
- The `timed_move` action plans the held duration on that same 100 ms cadence,
  rounding up to whole intervals without adding a second immediate-write
  interval. Its service deadline bounds nonmultiples of 100 ms, and the
  60-second limit remains valid. Stored pulse count and delay options remain
  unchanged.
- STOP cleanup and the massage release query retain their deadlines. A completed
  service call does not prove that an unacknowledged write reached the bed.

#### Notifications

##### Feedback interpretation

The parsers assign raw model fields. They do not prove calibrated motor positions,
angles, percent, fault codes or physical actuator count. The app proves two control
axes; no extra neck/lumbar/motion/voice/alarm/RGB control follows from raw slots.
Initial fields 47 and 5f are true in the app model, separately from physical state.

| Parser | Recognition and sufficient length | Important formulas |
|---|---|---|
| Modern C8/9 | `a5/0b`, at least 16 bytes | Time `(b[4]<<8)\|b[5]` maps 1–600→1, 601–1200→2, 1201–1800→3, otherwise 0. Wave is byte 6 low nibble; both intensity slots use byte 7 low nibble. Brightness/index are byte 14 high/low nibble; light on is low nibble>0; field 47 is byte 15 high nibble==1. |
| Modern C8/9 | `a5/0d`, at least 19 bytes | Fields 2b/33/3b clamp bytes 4/6/8 to 100; field 5f is byte 17==0. These remain raw diagnostics. |
| All non-BOX15 C | `a5/0c`, at least 8 bytes | Fields 67/7f/6f use bytes 6/4/7. Field 77 maps byte 5=5→17,6→19,otherwise 9. No alarm interpretation is inferred. |
| Legacy BOX24 formulas | `a5/0b`, byte 2=14, at least 9 bytes | Timer index multiplied by 10; wave=byte 6−1, including −1. Intensity scale is `v//3 + v%3 + int(v>1)` on byte 7 low nibble and byte 8. |
| BOX15 special | `ed/80`, at least 7 bytes | Fields 67/7f/6f/77 use bytes 3/5/4/6. |
| BOX15 fallback | Non-special length 23 | Timer `b[19]&15`, head `remap(b[11]&7)`, foot `remap(b[12])`, wave `b[21]`. |
| BOX15 fallback | Non-special length 16 | Timer `b[14]&15`, head `remap(b[7])`, foot `remap(b[8])`, wave `b[14]>>4`. |
| BOX15 fallback | Non-special length 10 | Timer `b[8]&15`, head/foot 0, wave 1. |
| BOX15 fallback | Other non-special length | Timer/head/foot 0, wave 1. |

- Here `remap` maps 3→2 and 6→3, passing other values through. BOX15 fallback
  overwrites those four fields without adding header/checksum validation. A
  short recognized special `ed/80` frame of 4–6 bytes is rejected safely rather
  than falling through and overwriting fallback state.
- Short-frame guards prevent out-of-bounds updates without inventing checksum
  validation. The unreachable D1 fragment accumulator is not enabled by
  selecting C1.
- Identical parsed model updates preserve the artifact's equality suppression;
  valid changed updates must retain exact formulas.

###### UI-consumed state

Only U8/9 consumes modern parsed state for its positive gates and public light/
massage state.

| UI field | Source |
|---|---|
| Head intensity | `max(field13−1,0)` |
| Timer | `field_b` |
| Wave | `field23` |
| Massage-on | **timer>0** |
| Light-on | `field43` |
| Level | `field53` |
| Low 4b | `field4b` |
| Automatic-white flag | `field 47` |

- The flag starts white only while connected.
- Raw 67/6f/77/7f have no other app consumer or proved error/model mapping; raw
  2b/33/3b have no measurement UI or unit conversion.
- Field 5f supplies diagnostic stopped text, not STOP or a control gate. All
  assigned raw fields remain diagnostic.

##### State retention and offline restoration

###### Same-address state

- C/D/U transitions may preserve observed state on the **same address**. State
  from another physical bed cannot authorize controls.
- Actual reconnects retain the eight observed Home UI fields and the shared
  light timestamp in the coordinator's process-local state. Reconstructed raw
  models keep fresh parser defaults; raw diagnostics stay unknown until a valid
  callback. The retained head intensity, wave, low4b and white flag remain
  last-observed UI values, separate from the new raw parser model.
- Internal capability reloads hand this state to the matching entry and
  physical address, including a controller built later. Fresh consumed native
  state or a newly accepted light intent takes precedence over the old
  snapshot.
- Rehydration does not replay callbacks or restart automatic white lighting.
- A changed notification with a modern U runs the native whole-model Home
  consumer, even for a partial diagnostic frame, so fresh model defaults can
  replace retained UI fields. An unchanged frame or legacy U does not run that
  consumer.
- A native test across all C/U combinations is a branch probe, not proof that
  every combination has a live application writer. An old modern
  automatic-white stream retargeted to another bed is a safety exclusion, not a
  fresh C3/7 automatic-white control.

###### Offline paired-side restoration

Offline paired-side restoration is limited to stored selectors that prove a
fixed entity catalog.

- An omitted transport selector requires the stored original BLE name; a
  display alias cannot supply that identity.
- BOX1220/BOX3633 transports do not reclassify C.
- UART transports can restore offline when either possible manufacturer result
  keeps the same complete catalog: positive controls, feedback light and
  stateless power buttons. C7/8/9 qualify; C3 qualifies only with a consuming
  U8/9. A nonconsuming U with C3 must finish live classification because C8/9
  would add power buttons.
- UART with another C must connect and finish classification before its
  complete catalog is known. U remains independent.
- Offline capabilities do not create observed feedback or permission for
  state-gated timer/light/massage commands.

###### Command admission

- UART command admission waits for optional manufacturer classification to
  finish (or prove unavailable), alongside required wake/subscription
  initialization. Its query/read cadence stays parallel, and stale sessions
  cannot publish readiness.
- Delayed queries and automatic-white callbacks use their own queued command
  reservation, preserving the current HA and tracing context while detaching the
  movement reservation.
- Native lighting buttons queue without cancelling movement.

#### Evidence

##### Notes

###### Brightness binding

Twelve frozen brightness probes using 15, 30 or 255 establish the private
one-byte builder domain, not additional public brightness levels. Public
brightness remains integral 1–6 with off as a separate action. The owner has
flagged this binding distinction for independent review and requires explicit
public-domain rejection tests; no accepted evidence or exclusion is rewritten.

###### Ownership, boundaries and validation

- Operations, subscriptions, reads and delayed callbacks must remain bound to
  the original address and connection/profile generation. Teardown, disconnect
  and selection changes cancel owned work and attempt required cleanup while the
  original connection is available.
- The app's stale callback/state-transfer bugs are not implementation targets;
  their reachable bed controls remain required.
- Nordic DFU payload/catalog/download/bond handling, Wi-Fi, handset
  permissions, licensing and navigation are product/host boundaries.
  Firmware-update activity still invalidates normal roles and control
  admission. No PIN, bond removal, unproved capability query or OTA retry is
  introduced.

###### Analysis provenance

- Package `com.starcode.abm5_4` 1.0.1 (3), delivered as five APK members. See
  the [row004 disposition](../apk-analysis/row004-dispositions.md).
- The implemented profile has the fixed selector schema, paired dispatch, owned
  cancellation and public entities covered by artifact vectors and focused
  tests. The README remains the supported-bed status index.
- The accepted evidence is complete. Final integration acceptance is pending:
  every required row needs actual code and passing focused test references, all
  platform exposure and ownership tests must pass, and the complete standalone
  PR must finish its review/CI/merge gates.
- Hardware checks HW01–HW06 remain deferred to real users after beta/release;
  they do not defer artifact-backed implementation.

### Okin CST

**Apps:** the Rize, MFirm 900, Support and Nectar Motion apps in [Apps](#apps)

**Status:** ❓ Needs testing (static analysis complete; hardware validation pending)

**Android:** all ten analyzed packages are Android apps. The nine cluster 011
artifact hashes are listed under [Analysis provenance](#cst-analysis-provenance).

#### Setup

##### Known models

- Mattress Firm 900-O / MFirm 900-O and Rize MF900
- Rize Sanctuary, Resident, Aviada, Bob, and Contempo
- Rize II Carefree and Rize II Clarity
- Support
- Nectar Motion using the Nectar Move app profile
- Bluetooth names vary; some report as `OKIN-XXXXXX`

##### Protocol Details

**Service UUID:** `62741523-52f9-8864-b1ab-3b3a8d65950b` (standard OKIN)
**Write Characteristic:** `62741525-...`
**Notify Characteristic:** `62741625-...`
**Format:** 14-byte command with two separate 32-bit fields

###### Packet Format

```text
[0x0C, 0x02, primary[4], secondary[4], 0x00, 0x00, 0x00, 0x00]
```

- **Primary field** (bytes 2-5): Head, foot, and lumbar motor control plus
  presets, memory-save chords, light toggle, massage stop, and intensity
- **Secondary field** (bytes 6-9): Discrete light on/off and massage wave modes
- Each field is a big-endian 32-bit value; unused fields are zero.

Field placement is app-specific. Do not assume all presets, lights, or massage
commands use the secondary field.

###### Write Mode

The accepted Android app does not set a numeric write type; it leaves the write
characteristic at its runtime default. Home Assistant retains its existing
write-with-response integration policy. The accepted artifacts do not establish
the receiver's effective write mode or required characteristic properties, so
the effective hardware behavior is deferred for real-user validation.

##### Pairing

The captured MFirm receiver gates its reads and notification characteristics
(including Device Information) behind an OS-level Bluetooth **bond**. The OS
negotiates the bond automatically when a client accesses one of those encrypted
characteristics.

- Pairing is "Just Works": **no PIN** and **no dedicated Bluetooth pairing button**.
- Before bonding, those characteristics return GATT `error=5` "Insufficient
  authentication". The command characteristic (`62741525-...`) itself was
  readable unbonded, but the integration still establishes the bond so the
  connection matches the official app's full GATT session.

**To enter pairing mode, power-cycle the control box:** unplug it for ~30 seconds,
then plug it back in. The status light blinks blue, then turns green after ~20 s;
that window is when the base accepts a new bond. Some models instead use the
under-bed lamp/light button (hold until it blinks blue). The physical "Pair"/"Learn"
button found on some OKIN control boxes only syncs the **RF remote**, not Bluetooth.

The integration requests `pair=True` automatically and verifies the bond after
connecting. If the link connected but did not bond, it clears its cached bond
state, re-pairs on the next attempt, and surfaces a **"Bluetooth pairing required"**
repair with a guided **Fix** button. ESPHome Bluetooth proxies can pair only on
ESPHome ≥ 2024.3.0; a local adapter near the bed is the most reliable for the
first bond.

Nectar Move's accepted app has no app-issued bond request or authentication
gate, so its profile skips proactive pairing. Home Assistant still routes an
actual GATT authentication failure through the existing bond-recovery repair.
That repair, with its **Pair Now** action, stays until a later connection
succeeds. This does not change pairing policy for other CST profiles.

##### Detection / Setup

| Signal | Value |
|--------|-------|
| Service UUID | `62741523-52f9-8864-b1ab-3b3a8d65950b` (standard OKIN) |
| Name patterns | Varies (shared UUID requires disambiguation; some report as `OKIN-XXXXXX`) |
| Connected GATT hint | CSS `90311623-...` plus Nordic DFU `00001530-...` is ambiguous and requires another identity signal |
| BLE Pairing | Required for most profiles; Nectar Move does not proactively request a bond |

- Manual selection may be needed since the service UUID is shared with other Okin protocols.
- The shared UUID and the official apps' common `OKIN-*` name filter do not
  distinguish the nine product layouts. Select the matching **Protocol variant**
  in the integration options. `Auto` preserves the MF900 profile for existing
  entries.
- Do not choose CST solely because diagnostics show both the CSS and Nordic DFU
  services. That connected GATT signature is also exposed by RF ECO BT stair
  actuators and by OKIMAT drives used with FurniMove (#555). Device Information
  model `MEGAMAT MBZ` identifies RF ECO BT. Choose CST only when the known base
  or app identity corroborates the CST protocol. The integration never selects
  CST automatically from GATT; a CST entry whose drive reports an `OKIMAT` model
  is offered a [repair](furnimove.md#repairing-existing-configurations).
- Do not select CST for `LP BED...` receivers. LP Control 2.9.0 identifies those
  as its Okin profile and sends 6-byte commands, even when the receiver also
  exposes CSS and Nordic DFU services. See [Leggett & Platt](leggett-platt.md).
- **Nectar Move** is opt-in; see [Nectar Move profile](#nectar-move-profile).

##### Product Profiles

| Variant | Motors | Presets beyond Flat | Programmable memories | Massage | Light |
|---|---|---|---:|---|---|
| Sanctuary | Head, foot | Anti-snore, lounge, Zero-G | 2 | Head/foot intensity, 3 waves, full-body start, off | Toggle and discrete on/off |
| Resident | Head, foot | Anti-snore, lounge, Zero-G, incline | 4, including `M` | Head/foot intensity, 3 waves, timer step, off | None in the shipped UI |
| Aviada | Head, foot, lumbar | Anti-snore, lounge, Zero-G, incline | 3 | Global intensity, 3 waves, off | Toggle and discrete on/off |
| Bob | Head, foot | Anti-snore, lounge, Zero-G | 2 | Head/foot intensity, 3 waves, full-body start, off | Toggle and discrete on/off |
| Contempo | Head, foot, lumbar | Anti-snore, lounge, Zero-G, incline | 3 | Global intensity, 3 waves, off | Toggle and discrete on/off |
| Carefree | Head, foot | Anti-snore, Zero-G | 1 | None | Toggle and discrete on/off |
| Clarity II | Head, foot | Anti-snore, lounge, Zero-G, incline | 3 | Global intensity, 3 waves, off | Toggle and discrete on/off |
| MF900 | Head, foot, lumbar | Anti-snore, lounge, Zero-G, incline | 3 | Global intensity, 3 waves, off | Toggle and discrete on/off |
| Support | Head, foot, lumbar | Anti-snore, lounge, Zero-G, incline | 3 | Head/foot intensity, 3 waves, off | Toggle and discrete on/off |
| Nectar Move | Head, feet (app axes; physical semantics unverified) | Anti, Zero Gravity, Reading | 2: Zero Gravity, Reading | Increase only | Toggle only |

The zoned decrease frames are not interchangeable. Bob routes both zone-down
commands through both CST fields, Support routes foot-down through only the
secondary field, and Sanctuary/Resident use only the primary field. Selecting
the product profile is therefore required for safe zoned massage controls.

###### Nectar Move profile

Choose **Nectar Move** in setup or the Protocol variant options. No shared OKIN
name, UUID, or Device Information result selects it. The profile is opt-in and
keeps the other CST application profiles unchanged.

- **Axes:** two, labelled Head and Feet. Those are app-control labels; the
  receiver's physical actuator semantics have not been verified. Position
  feedback is not supported.
- **Presets:** Flat, Anti, Zero Gravity, and Reading. The two saveable slots are
  Zero Gravity and Reading. Reading has its own stable entity name and does not
  rename Lounge in other profiles.
- **Light:** under-bed lighting is an assumed-state toggle only.
- **Massage:** one combined intensity-increase button. It has no decrease, off,
  start/toggle, head/foot, wave, timer, level, or state action.
- **Save response:** see [Notifications](#notifications-6).
- **Write mode:** the Android app leaves the write characteristic's write type at
  its runtime default; the integration keeps its write-with-response policy
  (see [Write Mode](#write-mode-3)).

Hardware checks remain deferred for real users after a beta or release:
effective write behavior, physical axis and preset meaning, notification byte
meaning, and receiver repeat/STOP semantics. They are not implementation work.

#### Controls

##### Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Head and foot; lumbar on Aviada, Contempo, MF900 and Support |
| Position Feedback | ❌ (no decoded motor positions) |
| Memory Presets | ✅ (one to four programmable preset memories, per profile) |
| Massage | ⚠️ Per profile: global or head/foot intensity, three wave modes, off; increase only on Nectar Move; none on Carefree |
| Under-bed Lights | ✅ Every profile except Resident (toggle only on Nectar Move) |
| Flat / Zero-G / Anti-Snore | ✅ |
| Lounge / Incline (TV) / Reading | ⚠️ Per profile |
| BLE Pairing | ⚠️ Required for most profiles; Nectar Move does not proactively request a bond |

##### Commands

###### Motor Control (primary field)

| Command | Value | Description |
|---------|-------|-------------|
| Stop | `0x00000000` | All-zero frame (also the release) |
| Head Up | `0x00000001` | Raise head |
| Head Down | `0x00000002` | Lower head |
| Foot Up | `0x00000004` | Raise foot |
| Foot Down | `0x00000008` | Lower foot |
| Lumbar Up | `0x00000010` | Raise lumbar (lumbar profiles only) |
| Lumbar Down | `0x00000020` | Lower lumbar (lumbar profiles only) |

Multiple motor bits can be OR'd together for simultaneous movement.

###### Presets and Memory (primary field)

| Command | Value | Description |
|---------|-------|-------------|
| Flat | `0x08000000` | Flat |
| Zero-G | `0x00001000` | Zero-G recall |
| Lounge | `0x00002000` | Lounge recall (Reading on Nectar Move) |
| Incline / TV | `0x00004000` | Incline recall |
| Anti-snore | `0x00008000` | Anti-snore |
| Memory `M` | `0x00010000` | Resident's fourth memory recall |
| Save Zero-G | `0x08001000` | Flat + Zero-G chord |
| Save Lounge | `0x08002000` | Flat + Lounge chord (Save Reading on Nectar Move) |
| Save Incline | `0x08004000` | Flat + Incline chord |
| Save `M` | `0x08010000` | Flat + `M` chord (Resident) |

###### Memory Slots

The MFirm app treats Zero-G, Incline, and Lounge as user-programmable preset
memories. Home Assistant exposes those as numbered memory slots:

| HA Memory Slot | MFirm App Memory |
|----------------|------------------|
| Memory 1 | Zero-G |
| Memory 2 | Incline |
| Memory 3 | Lounge |

Other product variants expose only the accepted app's reachable slots. Resident
adds a fourth `M` slot; Sanctuary and Bob expose Zero-G and Lounge; Carefree
exposes only Zero-G. The other profiles use the three MF900 mappings above.

###### Lights

| Command | Field | Value | Description |
|---------|-------|-------|-------------|
| Light Toggle | Primary | `0x00020000` | Toggle under-bed light |
| Light On | Secondary | `0x00000040` | Discrete on |
| Light Off | Secondary | `0x00000080` | Discrete off |

###### Massage

| Command | Field | Value | Description |
|---------|-------|-------|-------------|
| Massage Off | Primary | `0x02000000` | Stop massage |
| Massage All + | Primary | `0x00000C00` | Global intensity up |
| Massage All - | Primary | `0x01800000` | Global intensity down |
| Massage Wave 1 | Secondary | `0x00080000` | Wave mode 1 |
| Massage Wave 2 | Secondary | `0x00100000` | Wave mode 2 |
| Massage Wave 3 | Secondary | `0x00200000` | Wave mode 3 |

###### Product-specific massage fields

| Product | Action | Primary | Secondary |
|---|---|---:|---:|
| Sanctuary, Resident | Head + | `0x00000800` | `0x00000000` |
| Sanctuary, Resident | Head - | `0x00800000` | `0x00000000` |
| Sanctuary, Resident | Foot + | `0x00000400` | `0x00000000` |
| Sanctuary, Resident | Foot - | `0x01000000` | `0x00000000` |
| Bob | Head - | `0x00800000` | `0x00800000` |
| Bob | Foot - | `0x01000000` | `0x01000000` |
| Support | Head - | `0x00800000` | `0x00800000` |
| Support | Foot - | `0x00000000` | `0x01000000` |
| Sanctuary, Bob | Full-body massage | `0x00000000` | `0x00000100` |
| Resident | Timer step | `0x00000200` | `0x00000000` |

Bob and Support use the same primary-only zone-increase fields as Sanctuary and
Resident. Every product with massage uses the shared wave and massage-off
fields above.

#### Timing

##### CST command timing

###### Cluster 011 profiles

- The Android app sends the active command immediately and every 100 ms while a
  button is held.
- On release it sends the all-zero STOP frame twice, at +100 ms and +200 ms.
- For one-shot voice actions such as presets, lights, and massage, the app
  streams for 500 ms before the same delayed STOP cleanup. Home Assistant uses
  that fixed one-shot cadence for button entities and keeps motor movement
  duration configurable.

###### Nectar Move

- Nectar Move uses the same 100 ms held-command refresh and delayed STOP pair,
  but its app also repeats every other reachable action only while held.
- Home Assistant movement commands are finite, so each one refreshes the axis
  at the app's 100 ms interval for the configured **Motor pulse count**
  (default 10, about one second), then sends the STOP pair.
- The card's hold loop re-issues movements while a control stays pressed, and a
  STOP or replacement command ends the refresh early with the same release.
- Stateless preset, save, light, and massage buttons send one selected frame,
  then STOP at +100 ms and +200 ms as a bounded Home Assistant tap mapping.

#### Notifications

##### Notifications

- The app subscribes to the notify characteristic (`62741625-...`) but only
  watches byte 10 for a generic change; it does not decode motor positions.
- **Nectar Move:** notification byte 10 is tracked only while a memory save is
  pending. A changed signed byte emits the `Memory save response observed`
  diagnostic. That signal is not proof that a physical memory was stored, and
  no position or device state is inferred from the byte.

#### Evidence

##### Notes

###### Relationship to Other Okin Protocols

Many command values match Okimat/Okin UUID values. CST differs in packet framing
and in which 32-bit field carries each remote action.

> [!WARNING]
> Earlier versions of this page listed Head Tilt `0x00000010`/`0x00000020`,
> Lumbar `0x00000040`/`0x00000080`, a Massage Toggle `0x04000000`, a position
> notify characteristic `62741524-...` and Okimat-style position feedback. The
> accepted cluster 011 reports and the current controller use Lumbar
> `0x00000010`/`0x00000020`, have no tilt axis or `0x04000000` command, and
> decode no positions.

###### CST analysis provenance

**Ref:** Nine frozen APK Protocol Audit cluster 011 clean-room reports and
accepted cluster reconciliation. The protocol was first reverse-engineered from
`CSTProtocol.java` in the Rize MF900 and Nectar Motion APKs.

The command table, product profiles, and timing come from nine COMPLETE, frozen
APK Protocol Audit cluster 011 reports. Their accepted artifact-set SHA-256
identities are:

| Package | Version | Artifact-set SHA-256 |
|---|---|---|
| `com.okin.bedding.rizeSanctuary` | 1.0.1 (2) | `90b494007dd120b4da9498c8d259411bb2a8f2e643a22433792486d896f535d0` |
| `com.okin.bedding.rizeResident` | 1.0.1 (2) | `26a33ef79aa50f0b899d934c01aad8641b97da58bd9b78134122ac56d33eeaa9` |
| `com.okin.bedding.rizeaviada` | 1.0.1 (2) | `fc1cbef8715de115455a4931264941bf44ad10adc819811496a82221e85b6241` |
| `com.okin.bedding.rizebob` | 1.0.1 (2) | `237ffd39af4e8179a1c83f07cfd53364d66d127f3ccdd7ea1394ea3c6bfca437` |
| `com.okin.bedding.rizecontempo` | 1.0.2 (3) | `9c8ef59a2addb92c9b81c330d629d495c606e6b0d06f67e31c19e7cd8e112ea9` |
| `com.okin.bedding.rizeiicarefree` | 1.0.1 (2) | `204617a5b4b60247478125dd6cfdfaadf769581fe77b874b3f9fc47ff271234f` |
| `com.okin.bedding.rizeiiclarity` | 1.0.1 (2) | `998bcd5962de74c85d3ebf36778007f6cbe11b4c1992477a454fca1a3ab80c1a` |
| `com.okin.bedding.rizemf900` | 1.1.2 (4) | `a4f5ae67b2b9b870e6413d08597364041ac6947c7ba5445eb1979498895ff46f` |
| `com.okin.bedding.support` | 1.0.4 (5) | `c2e01cdc9727f3608bcbd58076fecfa9c84176b343750079284b246e6aba2e00` |

The cluster reconciliation closed all 99 package/domain comparisons with no
blocker. The Nectar Move profile comes from the row042 accepted audit and
convergence proof for `com.okin.bedding.nectarmotion` 1.0.1 (2). Physical
behavior remains unverified on target hardware.

### Jordan's Serenity

**App:** [Jordan's Serenity](https://play.google.com/store/apps/details?id=com.okin.bedding.serenity) 1.0.1 (code 2), `com.okin.bedding.serenity`

**Status:** ❓ Needs testing (APK-verified, physical operation unverified)

#### Setup

##### Known models

- Beds controlled with the Jordan's Serenity app (Android package `com.okin.bedding.serenity`)
- OKIN receivers; their Bluetooth names (lowercase form starting with `okin`) are shared with other apps
- Sibling apps on the same controller core, each with its own action table:
  [Jordan's Tranquil](#jordans-tranquil) and the [Customatic Z-Series](#customatic-z-series)

##### Protocol Details

**Service UUID:** `62741523-52f9-8864-b1ab-3b3a8d65950b`
**Write Characteristic:** `62741525-52f9-8864-b1ab-3b3a8d65950b`
**Notify Characteristic:** `62741625-52f9-8864-b1ab-3b3a8d65950b`
**Manufacturer Read:** service `0000180a-0000-1000-8000-00805f9b34fb`, characteristic `00002a29-0000-1000-8000-00805f9b34fb`
**Format:** 14-byte CST frame: `0c 02`, a 32-bit primary field and a 32-bit
secondary field (both big-endian), then four zero bytes

###### Packet Format

```text
[0x0C, 0x02, primary(4, big-endian), secondary(4, big-endian), 0x00, 0x00, 0x00, 0x00]
```

- No normal checksum, encryption, side selector, or authentication packet.
- The existing CST builder is reused because its bytes are equivalent; another
  product's capabilities are not inherited.
- Examples: Head up `0c 02 00 00 00 01 00 00 00 00 00 00 00 00`, Wave 1
  `0c 02 00 00 00 00 00 08 00 00 00 00 00 00`, Release/Stop is `0c 02` plus
  twelve zero bytes.

###### Write Mode

- The Android app leaves its characteristic write type unchanged, so the runtime
  ATT mode is unknown.
- HA validates the command role and prefers acknowledged writes when `write` is
  advertised, otherwise using `write-without-response`. This is a host policy,
  not a recovered fixed Android write mode.
- Notifications require the exact notify role and remain subscribed with angle
  sensing disabled. Bleak handles the notification CCCD.

##### Detection / Setup

- Select **Jordan's Serenity** manually. Shared OKIN advertisements or GATT UUIDs
  do not identify this app.
- Initial app discovery scans without a service filter and accepts names whose
  lowercase form starts with `okin`. This shared prefix cannot select Serenity.
- The app always selects CSTProtocol and the Z280 remote/massage screen pair.
  Persisted bed-type settings do not change that selection.
- Manufacturer values, including CST13/CST14, never select a protocol and always
  leave alarm controls disabled. Existing CST product profiles are separate.
- There is no PIN, bonding, or pairing gate established by the artifact.

##### Home Assistant setup

Select **Jordan's Serenity app** explicitly for the accepted `com.okin.bedding.serenity` 1.0.1 (2) application profile. Shared OKIN discovery and GATT UUIDs do not identify this app profile. The two named main axes use Head and Feet; additional actuator controls retain literal selector 4/5 names because app touch and voice labels disagree. Setup hides motor-count and pulse-delay fields: the app proves two named axes, additional literal selectors, and a fixed 100 ms refresh interval. The internal named-axis count does not claim a physical actuator count. Status notifications remain active when angle sensing is disabled; this profile reports no motor position.

#### Controls

##### Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Head/back and foot/legs covers; Remote Selector 4/5 as literal buttons |
| Position Feedback | ❌ |
| Memory Presets | ✅ (M1, M2; plus Save Zero Gravity and Save TV) |
| Presets | ✅ Flat, Zero Gravity, TV, Leisure (exposed through Lounge), Anti-Snore |
| Massage | ✅ (head/foot/mode/timer cycles, toggle, off, Wave 1-3) |
| Lights | ✅ (native toggle, assumed-state on/off switch; no RGB or brightness) |
| Alarms | ❌ (alarm replies are parsed as diagnostic state only) |
| Diagnostic state | ✅ (manufacturer, status code, massage timer, save event, alarm reply) |

##### Reachable commands

Values occupy the primary field unless a secondary value is listed. The
held-control service (`hold_control`) uses these exact `control` values.

###### Motor Control

| Command | `control` | Primary | Secondary |
|---------|-----------|--------:|----------:|
| Head/back up, down | `head_up`, `head_down` | `0x1`, `0x2` | 0 |
| Foot/legs up, down | `foot_up`, `foot_down` | `0x4`, `0x8` | 0 |
| Remote Selector 4 up, down | `selector_4_up`, `selector_4_down` | `0x10`, `0x20` | 0 |
| Remote Selector 5 up, down | `selector_5_up`, `selector_5_down` | `0x40`, `0x80` | 0 |
| Release/Stop | | 0 | 0 |

Touch labels and voice labels conflict for the extra selectors:

- Remote lumbar controls send selector 4, while the presenter calls that tilt.
- Remote tilt controls send selector 5, while its presenter calls that lumbar.
- Voice lumbar selects 4 and headtilt selects 5.

HA therefore exposes literal **Remote Selector 4/5 Up/Down** buttons rather than
assigning unverified physical lumbar/headtilt axes. Only the proven head/feet
controls create covers. All covers share the global scheduler resource because
every release zeros the whole command.

###### Presets

| Command | `control` | Primary | Secondary |
|---------|-----------|--------:|----------:|
| Flat | `flat` | `0x08000000` | 0 |
| Zero Gravity | `zero_g` | `0x1000` | 0 |
| TV | `tv` | `0x4000` | 0 |
| Leisure, exposed through Lounge | `leisure` | `0x2000` | 0 |
| Anti-Snore | `anti_snore` | `0x8000` | 0 |

###### Memory

| Command | `control` | Primary | Secondary |
|---------|-----------|--------:|----------:|
| M1, M2 | `memory_1`, `memory_2` | `0x10000`, `0x40000` | 0 |
| Save Zero Gravity | `save_zero_g` | `0x08001000` | 0 |
| Save M1, Save M2 | `save_memory_1`, `save_memory_2` | `0x08010000`, `0x08040000` | 0 |
| Save TV | `save_tv` | `0x08004000` | 0 |

- Only M1 and M2 are numbered memory slots. Separate Save Zero Gravity and Save
  TV buttons preserve the reachable Flat+preset chords.
- Save buttons hold for five seconds, matching the bound app help gesture.
  Frames begin immediately; the app has no five-second command gate or storage
  acknowledgement.
- The held action service permits longer holds without assuming a storage
  acknowledgement.

###### Massage

| Command | `control` | Primary | Secondary |
|---------|-----------|--------:|----------:|
| Head massage cycle | `massage_head_cycle` | `0x800` | 0 |
| Foot massage cycle | `massage_foot_cycle` | `0x400` | 0 |
| Massage mode cycle | `massage_mode_cycle` | `0x10000000` | 0 |
| Massage timer cycle | `massage_timer_cycle` | `0x200` | 0 |
| Massage toggle | `massage_toggle` | `0x100` | 0 |
| Massage off | `massage_off` | `0x02000000` | 0 |
| Wave 1, 2, 3 | `wave_1`, `wave_2`, `wave_3` | 0 | `0x80000`, `0x100000`, `0x200000` |

###### Lights

| Command | `control` | Primary | Secondary |
|---------|-----------|--------:|----------:|
| Light toggle | `light_toggle` | `0x20000` | 0 |
| Light on, off | `light_on`, `light_off` | 0 | `0x40`, `0x80` |

Light on/off is exposed as a switch that starts unknown and marks commanded
values as assumed. The separate **Toggle Light** button preserves the app's
native toggle/cycle. Neither control has physical state feedback, RGB
selection, or brightness selection.

#### Timing

##### Serenity command timing

| Operation | Hold | Source |
|-----------|------|--------|
| Every reachable touch action | Immediate stream repeated every 100 ms | App |
| Ordinary cover pulses | Configured count at the app's fixed 100 ms interval | HA setting |
| Save buttons | Five seconds | App help gesture |
| Flat | 1500 ms | Reachable voice path |
| Voice presets, light commands, direct massage commands | Stop requested after 500 ms | Voice path |
| Other ordinary button actions | Bounded 500 ms | HA policy |
| `hold_control` | 0.1–60 seconds, any literal control including saves and both extra selectors | HA service |

Release and cleanup:

- Handled release/cancel ends the stream and attempts zero packets at +100 and
  +200 ms from one release timestamp. This applies to motor, preset, save,
  massage, and light controls.
- HA preserves those nominal offsets while serializing writes. If the first
  write finishes after the second deadline, HA attempts the second immediately
  afterward.
- HA attempts both cleanup writes even if the first fails, and uses a fresh
  cancellation event so task cancellation cannot suppress either attempt.
- A requested elapsed duration ends refresh before cleanup begins.
- Exact Android repeat counts at the deadline depend on handler scheduling; HA
  uses an elapsed ceiling instead of reproducing the boundary race.
- The app does not establish valid combined-motor packets. Its shared touch mask
  is interpreted through exact switch cases; unknown combinations can leave a
  prior stream running. HA rejects unknown or combined held controls before
  writing.

#### Notifications

##### Notifications and diagnostic state

The parser accepts each notification independently:

- Inputs of ten bytes or fewer are ignored. The app does not validate the first
  byte, header, checksum, or frame length beyond that guard; HA preserves these
  recognition rules and signed byte values.
- **Alarm reply** (byte 1 is 12): signed repeat/hour/minute from bytes 4/6/7,
  subtype byte 5 mapped to alarm type, enabled when byte 9 equals 1. Subtypes
  1–9 map to types 9/17/18/16/20/19/18/9/21; unknown subtypes retain the
  previous type. Alarm replies are reachable even though alarm commands/UI are
  dead. HA exposes diagnostic alarm state and adds no alarm-writing action.
- **Status code** (other notifications): signed byte 10 is a change-only status
  code.
  - With a pending save, the next changed code reports the source's local save
    event and clears that pending code; it does not update the timer.
  - Release, movement, massage, light controls, duplicate status codes, and
    alarm replies preserve a pending save. Any preset recall clears it.
  - Local save event codes: 5 for Zero Gravity, 4 for M1, 6 for TV, and 8 for M2.
  - Otherwise the changed code updates the massage timer code. Codes 1/2/3
    select 10/20/30 minutes in the app; other signed values remain raw and have
    unknown duration. This is a selected timer, not remaining time.

| State | Keys |
|-------|------|
| Diagnostic state | `serenity_manufacturer`, `serenity_status_code`, `serenity_massage_timer_code`, `serenity_massage_timer_minutes`, `serenity_save_event_code`, `serenity_alarm_type` |
| Alarm sensor attributes | `serenity_alarm_repeat`, `serenity_alarm_hour`, `serenity_alarm_minute`, `serenity_alarm_on` |
| Controller diagnostics | Also include the pending save code (`save_pending_code`) |

HA-specific handling:

- HA supplies the active callback equivalent, copies notification bytes
  immediately, and scopes state to one controller. It does not reproduce null
  callback crashes, mutable-buffer callback races, or app-global state leaking
  between selected devices.
- The diagnostic save event is not proof of successful physical storage. The app
  records intent before transmission, so a failed or cancelled save write can
  still produce this local event on a later changed status.

###### Manufacturer

- Read one second after subscription, with the exact Information service/read
  property required. Missing information or read failures do not block control.
- **Refresh Manufacturer** repeats the reachable on-resume read.
- Text decodes using UTF-8 with replacement, the modern Android default charset.
- Manufacturer never enables alarms or changes capabilities.

#### Evidence

##### Notes

###### Safety adaptations

- The app's voice Stop briefly emits head-up before scheduling Stop. HA excludes
  that unsafe branch and sends the two zero frames only.
- HA also excludes indefinite voice motion, delayed stops interrupting
  replacement commands, stale callbacks writing to a newly selected bed, and
  command callbacks surviving disconnect/background/destruction.
- HA serializes commands per physical bed and finishes cleanup before
  replacement.

###### Exclusions

- Excluded dead artifact paths: Z230 and legacy remote screens,
  alarm/current-time/query/clock-adjustment builders, combined selector-3
  helpers, direct massage level/timer/query helpers without callers, the unused
  presenter speech map, unused save timer/checksum helpers, and child-lock
  artwork without a command.
- Android speech recognition, help graphics, localization, framework code,
  connector-map/UI plumbing, and BLE library internals are outside BLE protocol
  implementation.
- Unsafe callback and voice behavior is excluded as described above.

###### Validation

- Focused vectors in `tests/test_serenity.py` account for all 45 reachable action
  rows, with CMD32 explicitly mapped to safe Stop rather than head-up.
- They cover signed parser branches, unknown alarm types, save-event persistence
  and diversion, deadlines, cancellation-safe double release, independent
  release attempts after a write failure, button routing, exact GATT
  role/property validation, subscription/read ordering, and optional
  manufacturer failures.
- Physical actuator mapping, save outcomes, ATT compatibility, and notification
  meanings remain deferred external validation.

###### Serenity analysis provenance

- Independently accepted S01 FULL analysis of `com.okin.bedding.serenity`
  version 1.0.1/code 2, with four verified APK/split members.
- Artifact-set SHA-256: `b0729dc3a4eae2644cc5035b984a05ac116a658b79c886ab1b02eebdea584cc6`
- Discovery ledger: [S01 dispositions](../apk-analysis/dispositions/S01-serenity.md)

### Jordan's Tranquil

**App:** [Jordan's Tranquil](https://play.google.com/store/apps/details?id=com.okin.bedding.tranquil) 1.0.2 (code 3), `com.okin.bedding.tranquil`

**Status:** ❓ Needs testing (APK-verified, physical operation unverified)

#### Setup

##### Known models

- Beds controlled with the Jordan's Tranquil app (Android package `com.okin.bedding.tranquil`)
- OKIN receivers; their names and GATT UUIDs are shared with other apps
- Reuses the [Serenity](#jordans-serenity) controller core: the same transport, 14-byte
  frame, refresh/release lifecycle and notification parser. Its action table,
  save codes and buttons are its own.

##### Protocol Details

**Service UUID:** `62741523-52f9-8864-b1ab-3b3a8d65950b`
**Write Characteristic:** `62741525-52f9-8864-b1ab-3b3a8d65950b`
**Notify Characteristic:** `62741625-52f9-8864-b1ab-3b3a8d65950b`
**Manufacturer Read:** service `0000180a-0000-1000-8000-00805f9b34fb`, characteristic `00002a29-0000-1000-8000-00805f9b34fb`
**Format:** 14-byte CST frame: `0c 02`, a big-endian 32-bit primary field, a
big-endian 32-bit secondary field, then four zero bytes

###### Packet Format

```text
[0x0C, 0x02, primary(4, big-endian), secondary(4, big-endian), 0x00, 0x00, 0x00, 0x00]
```

- There is no checksum, encryption, side selector, PIN or bonding.
- Example: Lounge `0c 02 00 00 20 00 00 00 00 00 00 00 00 00`; Release/Stop is
  `0c 02` plus twelve zero bytes.

###### Write Mode

The app leaves the Android write type unchanged; HA prefers acknowledged writes
when `write` is advertised, otherwise `write-without-response`. This is a host
policy.

##### Detection / Setup

- Select **Jordan's Tranquil app** manually. Shared OKIN names and GATT UUIDs do
  not identify this app.
- The app always shows its Z280 remote and massage pages; the stored model
  choice is ignored.
- Manufacturer strings, including CST13/CST14, never enable alarm controls in
  this app.

##### Home Assistant setup

Select **Jordan's Tranquil app** for `com.okin.bedding.tranquil` 1.0.2 (3). The app shares OKIN discovery names and GATT UUIDs with other products, so it is not detected automatically. As with Serenity, setup hides motor-count and pulse-delay fields; the pulse count stays editable. A two-address pair must be split before either side changes to, from or between this profile and another. Notifications stay active when angle sensing is disabled; this profile reports no motor position.

#### Controls

##### Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Head and Feet covers; Remote Selector 4/5 as literal buttons |
| Position Feedback | ❌ |
| Memory Presets | ✅ (M1, M2; plus Save Zero Gravity and Save Lounge) |
| Presets | ✅ Flat, Zero Gravity, Lounge, Anti-Snore (voice only); no TV |
| Massage | ✅ (head/foot/mode/timer cycles, toggle; voice-only off and Wave 1-3) |
| Lights | ✅ (native toggle, assumed-state on/off switch; no RGB or brightness) |
| Alarms | ❌ (no alarm page; alarm replies are parsed as diagnostic state only) |
| Diagnostic state | ✅ (manufacturer, status code, massage timer, save event, alarm reply) |

##### Reachable commands

Values occupy the primary field unless a secondary value is listed. The
`hold_control` name is the service's `control` value.

###### Motor Control

| Command (`hold_control` name) | Primary | Secondary | Source |
|---|---:|---:|---|
| Head up/down (`head_up`, `head_down`) | `0x1`, `0x2` | 0 | Touch and voice |
| Foot up/down (`foot_up`, `foot_down`) | `0x4`, `0x8` | 0 | Touch and voice |
| Remote Selector 4 up/down (`selector_4_up`, `selector_4_down`) | `0x10`, `0x20` | 0 | Lumbar-icon touch, voice "lumbar" |
| Remote Selector 5 up/down (`selector_5_up`, `selector_5_down`) | `0x40`, `0x80` | 0 | H TILT touch, voice "head tilt" |
| Release/Stop | 0 | 0 | Release, cancel and timed stops |

The lumbar-icon and H TILT buttons send builder operations 4 and 5, while the
app's presenter method names are swapped. Voice labels agree with the touch
labels. As with Serenity, HA exposes literal **Remote Selector 4/5 Up/Down**
buttons and creates covers only for Head and Feet. The physical actuator behind
each selector is unverified.

###### Presets

| Command (`hold_control` name) | Primary | Secondary | Source |
|---|---:|---:|---|
| Flat (`flat`) | `0x08000000` | 0 | Touch and voice |
| Zero Gravity (`zero_g`) | `0x1000` | 0 | Touch and voice |
| Lounge (`lounge`) | `0x2000` | 0 | Touch, voice "lounge"/"leisure" |
| Anti-Snore (`anti_snore`) | `0x8000` | 0 | Voice only (the touch button is hidden) |

###### Memory

| Command (`hold_control` name) | Primary | Secondary | Source |
|---|---:|---:|---|
| M1, M2 (`memory_1`, `memory_2`) | `0x10000`, `0x40000` | 0 | Touch |
| Save Zero Gravity, Save Lounge (`save_zero_g`, `save_lounge`) | `0x08001000`, `0x08002000` | 0 | Flat + preset chord |
| Save M1, Save M2 (`save_memory_1`, `save_memory_2`) | `0x08010000`, `0x08040000` | 0 | Flat + preset chord |

Only M1 and M2 are numbered memory slots. **Save Zero Gravity** and **Save
Lounge** buttons cover the other chords.

###### Massage

| Command (`hold_control` name) | Primary | Secondary | Source |
|---|---:|---:|---|
| Head/foot massage cycle (`massage_head_cycle`, `massage_foot_cycle`) | `0x800`, `0x400` | 0 | Massage page |
| Massage mode, timer cycle (`massage_mode_cycle`, `massage_timer_cycle`) | `0x10000000`, `0x200` | 0 | Massage page |
| Massage toggle (`massage_toggle`) | `0x100` | 0 | Massage page |
| Massage off (`massage_off`) | `0x02000000` | 0 | Voice only |
| Wave 1, 2, 3 (`wave_1`..`wave_3`) | 0 | `0x80000`, `0x100000`, `0x200000` | Voice only |

###### Lights

| Command (`hold_control` name) | Primary | Secondary | Source |
|---|---:|---:|---|
| Light toggle (`light_toggle`) | `0x20000` | 0 | Massage page and voice |
| Light on, off (`light_on`, `light_off`) | 0 | `0x40`, `0x80` | Voice only |

Light on/off is an assumed-state switch; **Toggle Light** sends the native
toggle. There is no RGB or brightness command, although the app help mentions
color cycling.

#### Timing

##### Tranquil command timing

| Operation | Hold | Source |
|-----------|------|--------|
| Held controls | Repeat every 100 ms | App |
| Ordinary cover pulses | Configured count at the 100 ms interval | HA setting |
| Flat | 1500 ms | App voice deadline |
| Lounge, Zero Gravity, Anti-Snore, waves, massage off and light commands | 500 ms | App voice deadlines |
| Save buttons | Five seconds | App help; the app has no hold timer or storage acknowledgement |
| M1/M2 recall, selectors and massage-page buttons | Same 500 ms bound | HA policy |
| `hold_control` | Any literal action for 0.1 to 60 seconds | HA service |

Release attempts two zero frames at +100 and +200 ms from one origin, with a
fresh cancellation event so cancellation cannot suppress either. Every release
is global, so all covers share one scheduler resource.

#### Notifications

##### Notifications and diagnostic state

The parser is shared with [Serenity](#notifications-and-diagnostic-state):

- Inputs of ten bytes or fewer are ignored.
- Byte 1 equal to 12 is an alarm reply: signed repeat/hour/minute at 4/6/7,
  subtype at 5, enabled at 9. Alarm replies are parsed even though this app has
  no alarm page.
- Otherwise signed byte 10 is a change-only status code. A changed status during
  a pending save reports the app's local save code (Zero Gravity 5, Lounge 3,
  M1 4, M2 8). Any recall clears it.
- Otherwise it updates the massage timer code; 1/2/3 mean 10/20/30 minutes in
  the app.

| State | Keys |
|-------|------|
| Diagnostic state | `tranquil_manufacturer`, `tranquil_status_code`, `tranquil_massage_timer_code`, `tranquil_massage_timer_minutes`, `tranquil_save_event_code`, `tranquil_alarm_type` |
| Alarm attributes | `tranquil_alarm_repeat`, `tranquil_alarm_hour`, `tranquil_alarm_minute`, `tranquil_alarm_on` |

The manufacturer is read one second after subscribing; **Refresh Manufacturer**
repeats the app's on-resume read.

#### Evidence

##### Notes

###### Safety adaptations

Excluded app behavior:

- The voice "stop" branch sends Head Up before scheduling STOP, so HA sends STOP
  only.
- Unbounded voice motion, remote touch-mask replay, delayed stops that overlap
  newer commands, and streams that survive disconnect or device changes.

###### Deferred validation

For real users after a release: actuator mapping of selectors 4 and 5, ATT write
mode, repeat and STOP arrival, save persistence and minimum hold time, massage
and light semantics, and notification contents.

###### Tranquil analysis provenance

- Independently accepted APK Protocol Audit of `com.okin.bedding.tranquil`
  version 1.0.2/code 3, and the cluster 010 reconciliation with the
  [Customatic Z-Series](#customatic-z-series) app.
- Artifact SHA-256: `595749e9f8eb2b654d88ad477fa80e4dfe5849335889b8c241fbd22faf3f5bda`
- Discovery ledger: [row052 dispositions](../apk-analysis/dispositions/row052-okin-zseries-tranquil.md)

### Customatic Z-Series

**App:** [Customatic Z-Series](https://play.google.com/store/apps/details?id=com.okin.bedding.glory) 1.0.4 (code 5), `com.okin.bedding.glory`

**Status:** ❓ Needs testing (APK-verified, physical operation unverified)

#### Setup

##### Known models

- Customatic Z-230 and Z-280, as chosen on the app's model selection screen
- Beds controlled with the Customatic Technologies Z-Series app (Android package `com.okin.bedding.glory`)
- OKIN receivers; their names and GATT UUIDs are shared with other apps
- Reuses the [Serenity](#jordans-serenity) controller core: transport, 14-byte frame,
  refresh/release lifecycle and notification parser. Action tables, save codes,
  buttons, timing and the alarm page are this app's own.
- Separate from the six-byte [Customatic Clarity/Jerome's/Remedy](okin-nframe.md#customatic-family) apps

##### Protocol Details

**Service UUID:** `62741523-52f9-8864-b1ab-3b3a8d65950b`
**Write Characteristic:** `62741525-52f9-8864-b1ab-3b3a8d65950b` (also used for alarm frames)
**Notify Characteristic:** `62741625-52f9-8864-b1ab-3b3a8d65950b`
**Manufacturer Read:** service `0000180a-0000-1000-8000-00805f9b34fb`, characteristic `00002a29-0000-1000-8000-00805f9b34fb`
**Format:** 14-byte CST frame: `0c 02`, two big-endian 32-bit fields and four zero bytes

These are the same service, command, notify and manufacturer roles as
[Tranquil](#protocol-details-6).

###### Packet Format

```text
[0x0C, 0x02, primary(4, big-endian), secondary(4, big-endian), 0x00, 0x00, 0x00, 0x00]
```

- The secondary field is always zero.
- There is no checksum, encryption, PIN or bonding.
- Example: Head and Foot up `0c 02 00 00 00 05 00 00 00 00 00 00 00 00`;
  Release/Stop is `0c 02` plus twelve zero bytes.

###### Write Mode

Shared with the Serenity core: the app leaves the Android write type unchanged;
HA prefers acknowledged writes when `write` is advertised, otherwise
`write-without-response`.

##### Detection / Setup

- Select **Customatic Z-Series app (Z-230)** or **Customatic Z-Series app
  (Z-280)** manually.
- Pick the model you chose on the app's selection screen; it is stored as
  protocol variant `z230` or `z280`, which has no automatic choice.
- Shared OKIN names and GATT UUIDs do not identify the app or the model.
- Setup accepts 1 to 600 motor pulses for these profiles; a stored value outside
  that range is clamped.

##### Home Assistant setup

For `com.okin.bedding.glory` 1.0.4 (5), select **Customatic Z-Series app (Z-230)** or **(Z-280)** to match the model chosen on the app's selection screen (protocol variant `z230` or `z280`). The app shares OKIN discovery names and GATT UUIDs with other products, so it is not detected automatically. As with Serenity, setup hides motor-count and pulse-delay fields. The pulse count stays editable and also bounds an ordinary button press, because the app streams a touched control until release and defines no deadline of its own. Z-Series setup accepts 1 to 600 pulses (0.1 to 60 s). A two-address pair must be split before either side changes to, from or between these profiles. Notifications stay active when angle sensing is disabled; these profiles report no motor position.

#### Controls

##### Features

| Feature | Z-230 | Z-280 |
|---------|-------|-------|
| Motor Control | ✅ Head, Foot, Head and Foot together | ✅ Head, Foot; Remote Selector 5 as literal buttons |
| Position Feedback | ❌ | ❌ |
| Memory Presets | ✅ (M1; plus Save Zero Gravity and Save TV) | ✅ (M1, M2; plus Save Zero Gravity and Save TV) |
| Presets | ✅ Flat, Anti-Snore, Zero Gravity, TV | ✅ Flat, Anti-Snore, Zero Gravity, TV |
| Massage | ✅ (toggle, mode/timer cycles, intensity) | ✅ (toggle, mode/timer cycles, head/foot cycles) |
| Lights | ✅ (toggle only) | ✅ (toggle only) |
| Alarm and clock | ⚠️ Only for manufacturer `CST13`/`CST14` | ⚠️ Only for manufacturer `CST13`/`CST14` |
| Diagnostic state | ✅ | ✅ |

The app has no voice control, waves, massage off or discrete light on/off, so
those are not exposed.

##### Reachable commands

Values occupy the primary field; the secondary field is always zero. The
`hold_control` name is the service's `control` value.

###### Motor Control

| Command (`hold_control` name) | Primary | Z-230 | Z-280 |
|---|---:|:---:|:---:|
| Head up/down (`head_up`, `head_down`) | `0x1`, `0x2` | yes | yes |
| Foot up/down (`foot_up`, `foot_down`) | `0x4`, `0x8` | yes | yes |
| Head and Foot up/down (`head_foot_up`, `head_foot_down`) | `0x05`, `0x0a` | yes | |
| Remote Selector 5 up/down (`selector_5_up`, `selector_5_down`) | `0x10`, `0x20` | | yes |
| Release/Stop | 0 | yes | yes |

The Z-280 extra control shows neck artwork, while the presenter calls it lumbar
and this app's builder operation 5 emits `0x10`/`0x20`. HA exposes literal
**Remote Selector 5 Up/Down** buttons; the physical actuator is unverified.

###### Presets

| Command (`hold_control` name) | Primary | Z-230 | Z-280 |
|---|---:|:---:|:---:|
| Flat (`flat`) | `0x08000000` | yes | yes |
| Anti-Snore (`anti_snore`) | `0x8000` | yes | yes |
| Zero Gravity (`zero_g`) | `0x1000` | yes | yes |
| TV (`tv`) | `0x4000` | yes | yes |

###### Memory

| Command (`hold_control` name) | Primary | Z-230 | Z-280 |
|---|---:|:---:|:---:|
| M1 (`memory_1`) | `0x10000` | yes | yes |
| M2 (`memory_2`) | `0x40000` | | yes |
| Save Zero Gravity, Save TV, Save M1 (`save_zero_g`, `save_tv`, `save_memory_1`) | `0x08001000`, `0x08004000`, `0x08010000` | yes | yes |
| Save M2 (`save_memory_2`) | `0x08040000` | | yes |

Numbered memory: Z-230 has M1, Z-280 has M1 and M2. **Save Zero Gravity** and
**Save TV** buttons cover the named chords.

###### Massage

| Command (`hold_control` name) | Primary | Z-230 | Z-280 |
|---|---:|:---:|:---:|
| Massage toggle (`massage_toggle`) | `0x100` | yes | yes |
| Massage mode, timer cycle (`massage_mode_cycle`, `massage_timer_cycle`) | `0x10000000`, `0x200` | yes | yes |
| Massage intensity (`massage_intensity_cycle`) | `0x0c00` | yes | |
| Head/foot massage cycle (`massage_head_cycle`, `massage_foot_cycle`) | `0x800`, `0x400` | | yes |

###### Lights

| Command (`hold_control` name) | Primary | Z-230 | Z-280 |
|---|---:|:---:|:---:|
| Light toggle (`light_toggle`) | `0x20000` | yes | yes |

#### Timing

##### Z-Series command timing

| Operation | Hold | Source |
|-----------|------|--------|
| Touch controls | Repeat every 100 ms until release | App |
| Ordinary buttons and presets | Configured motor pulse count at the app's 100 ms cadence (default 10, so one second) | HA bound; the app defines no deadline for a touched button |
| Save buttons | Five seconds | App help; the app has no save timer or storage acknowledgement |
| `hold_control` | Any literal action for 0.1 to 60 seconds | HA service |

After release, two zero frames are attempted at +100 and +200 ms. Remote and
massage releases both end in that global STOP in HA.

#### Notifications

##### Notifications and diagnostic state

- Same parser as [Tranquil](#notifications-and-diagnostic-state-1), with
  keys prefixed `zseries_`.
- Local save codes: Zero Gravity 5, M1 4, TV 6, M2 8.
- Alarm replies populate **App alarm state** with repeat, hour, minute and on
  attributes.

#### Services

##### Alarm

- The app shows its alarm page only when the Device Information manufacturer
  string is exactly `CST13` or `CST14` (case-sensitive), for either model.
- HA reads it one second after subscribing and on **Refresh Manufacturer**, and
  stores the last successful result with the entry so it survives disconnects
  and restarts.
- A failed read changes nothing: while the result is unknown, an alarm action
  reconnects and reads it again before writing. A confirmed other string makes
  the alarm actions unavailable.

###### Alarm frames

| Frame | Bytes |
|---|---|
| Alarm on | `07 05 repeat wake hour minute 00 01 01` |
| Alarm off | `07 05 00 00 00 00 00 00 01` |
| Clock | `07 06 (year-2000) month day weekday hour minute second` (binary, Sunday = 0) |
| Status query | `00 c0` |

- `repeat` is today's weekday bit (Sunday = bit 0). If the time is earlier than
  the current hour and minute, the next day's bit is used, wrapping Saturday to
  Sunday.
- `wake` is 1 for massage and 2 for M1.
- The final byte is the app's stored bed selection, which defaults to 1 and has
  no setter.

###### Alarm actions

- `zseries_set_alarm` mirrors opening the alarm page and tapping its switch:
  clock frame, alarm frame, then two queries at +500 and +800 ms. Enabling
  requires both a time and a wake mode.
- In the app the clock is sent when the page opens and the alarm only after a
  later user tap; HA sends the two frames back-to-back, a host choice that
  hardware validation should confirm.
- `sync_clock` sends the clock frame and the same queries.
- Times use Home Assistant's time zone.
- The app's other wake-type mappings, the `-128` repeat sentinel and the
  checksum clock-adjust builder are unreachable and are not implemented.

#### Evidence

##### Notes

###### Exclusions

Excluded: remote touch-mask replay, delayed stops overlapping newer commands,
streams surviving disconnect or device changes, the dead voice handler
(including its head-up-before-stop branch), unused legacy pages and helpers,
and alarm writes queued while disconnected.

###### Deferred validation

For real users after a release: selector and combined-motor mapping, ATT write
mode, STOP arrival, save persistence, alarm behavior (including acceptance of
the back-to-back clock and alarm frames) and notification contents.

###### Z-Series analysis provenance

- Independently accepted APK Protocol Audit of `com.okin.bedding.glory`
  version 1.0.4/code 5, and the cluster 010 reconciliation with
  [Jordan's Tranquil](#jordans-tranquil).
- XAPK SHA-256: `3a700cc4869080ec570c2e8653601b2755c08c7d3e3b13fa6a233e2af2bce7a8`
- Discovery ledger: [row052 dispositions](../apk-analysis/dispositions/row052-okin-zseries-tranquil.md)

## Notes

### Related Okin formats

The OKIN ComfortBed II-N app picks a protocol by device name:

| Device prefix | Protocol | Frame |
|---|---|---|
| `okin-ble` | CB.13/CB.15 (FFE5) | 9 bytes: `[0xE6, 0xFE, 0x16, cmd(4), side, checksum]` |
| `smartbed` | CB.24 (Nordic UART) | 7 bytes: `[0x05, 0x02, cmd(4), 0x00]` (no checksum) |

Extra motors in those apps: neck `0x00000010`/`0x00000020`, lumbar
`0x00000040`/`0x00000080`, hips (CB.24) `0x40000000`/`0x80000000`.

#### CB.24 Preset Safety

CB.24 preset recalls are sent as a single frame. The SmartBed app repeats the
same frame every 300 ms only while a touchscreen button remains held, and a
5.2-second hold is the controller's memory-save gesture. Fixed-duration or
automatically learned repeat streams can therefore overwrite the remote's stored
presets. All CB.24 profile variants, including the legacy `cb_old` alias, use
safe one-shot preset recall.

Other Okin formats, which share roots but not frames: [Nectar](okin-5a.md#nectar)
(7 bytes), [Mattress Firm 900](okin-5a.md#mattress-firm-900--iflex) (7 bytes over Nordic UART),
[Okin CST](#okin-cst) (14 bytes) and [Okin 64-Bit](okin-64bit.md) (10-byte
`08 02` frames; select it for a `NORA_CON` / `NORACON` controller or the
`com.okin.bedding.adjustbed` app). See
[Okin Protocol Family](../SUPPORTED_ACTUATORS.md#okin-protocol-family) for
detection priority and troubleshooting.

### Analysis provenance

- **Customatic:** accepted, frozen COMPLETE/FULL analyses of the three 1.0.1
  packages, cluster 009 reconciliation and an independent acceptance check.
  Artifact-set SHA-256: Clarity
  `1b1aeb6dc79d51b0b0ff4cce9fcb1e3fc0c1a99bc9fab12df683860d6e881c0d`, Jerome's
  `056431dcd500bbf02f3279d052e66f8f59ca5cd30bd51d1aab18c23a1782f268`, Remedy
  `382e76adcf0750d937b9f84669db0100111ba95ad92122b45a8547be6d609c57`. Focused
  tests are in `tests/test_customatic.py`.
- **Leggett Okin:** command values, framing, timing, notification parsing and
  release semantics come from the accepted clean-room analysis of
  `com.leggett.prodigy4` 1.2.0 (versionCode 18, artifact SHA-256
  `45922c518c9e8070…`), traced from layout binding to the GATT boundary and
  independently audited; the CU170 status mapping supplements it. The
  [Leggett app ledger](leggett-app-disposition.md) records all four report
  identities.
- **FurniMove:** `com.okin.okinsmartcomfort` 2.2.0 (19), see the
  [FurniMove ledger](../apk-analysis/dispositions/157-furnimove.md).

Raw APKs, decompilation output and frozen reports stay machine-local.
