# Okin N-frame (32-bit)

**Status:** ⚠️ Mixed: Okimat and the RF ECO BT stair lift are tested; Prodigy CE / CU170 is hardware-tested in [#368](https://github.com/kristofferR/ha-adjustable-bed/issues/368); DewertOkin, Customatic and the other Leggett profiles need testing. Each profile states its own status.

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), david_nagy, corne, PT, MarcusW and [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt)

This guide covers every bed that sends 32-bit Okin command words: Okimat handset
tables, DewertOkin, the OKIN Smart Remote stair lift, the Customatic apps and the
Leggett & Platt Okin apps. The 40-, 64- and 96-bit Okin formats have their own
guides until they move onto this codec: [Okin DOT](okin-dot.md),
[Okin 64-Bit](okin-64bit.md) and [Okin CST](okin-cst.md).

## Known Models

| Profile | Models |
|---|---|
| [Okimat](#okimat) | Okimat beds, Lucid L600, Rize beds (II, Contempo, Bob, Sanctuary, Aviada, MF900, Resident), Glory, Tranquil, Jobs 賈伯斯, Nectar Motion, Customatic Demo, RF ECO BT bed receivers, other beds with Okin motors |
| [DewertOkin](#dewertokin) | A H Beard, Hankook Gallery, beds with the DewertOkin HE150 controller, DewertOkin Bluetooth RF-Gateway receivers; see [DewertOkin brands](#dewertokin-brands) |
| [RF ECO BT stair lift](#rf-eco-bt-stair-lift) | Elda BTH / RF ECO BT / MEGAMAT staircase from [#344](https://github.com/kristofferR/ha-adjustable-bed/issues/344); Device Information model `MEGAMAT MBZ`, advertising as `OKIN-050226` |
| [Customatic](#customatic-family) | Customatic Clarity, Jerome's C and Remedy bases |
| [Leggett Okin](#leggett-okin-family) | Leggett & Platt Prodigy Comfort Elite and similar control boxes, marked `LP BED CONTROL`; confirmed hardware DewertOkin CU170 |

Customatic Z-Series beds use the separate [Customatic Z-Series](customatic-z-series.md)
profile; Okimat, DewertOkin and the other controllers stay separate from the
Customatic app profiles.

## Apps

| Analyzed | App | Package ID | Profile |
|---|---|---|---|
| ✅ | [OKIN ComfortBed II-N](https://play.google.com/store/apps/details?id=com.ore.jalon.neworebeding) | `com.ore.jalon.neworebeding` | [Okimat](#okimat) |
| ✅ | [OKIN Comfort Bed](https://play.google.com/store/apps/details?id=com.ore.okincomfortbed) | `com.ore.okincomfortbed` | [Okimat](#okimat) |
| ✅ | [OKIN Smart Bed](https://play.google.com/store/apps/details?id=com.okin.bedding.smartbedwifi) | `com.okin.bedding.smartbedwifi` | [Okimat](#okimat) |
| ✅ | Rize II | `com.okin.bedding.rizeii` | [Okimat](#okimat) |
| ✅ | Rize Resident | `com.okin.bedding.rizeResident` | [Okimat](#okimat) |
| ✅ | Glory | `com.okin.bedding.glory` | [Okimat](#okimat) |
| ✅ | Tranquil | `com.okin.bedding.tranquil` | [Okimat](#okimat) |
| ✅ | Jobs 賈伯斯 | `com.okin.bedding.jobs` | [Okimat](#okimat) |
| ✅ | Nectar Motion | `com.okin.bedding.nectarmotion` | [Okimat](#okimat) |
| ✅ | Support 挺你 | `com.okin.bedding.support` | [Okimat](#okimat) |
| ✅ | [OKIN Smart Remote / FurniMove](https://play.google.com/store/apps/details?id=com.okin.okinsmartcomfort) 2.2.0 (19) | `com.okin.okinsmartcomfort` | [Okimat](#okimat), [DewertOkin](#dewertokin), [RF ECO BT stair lift](#rf-eco-bt-stair-lift) |
| ✅ | [Customatic Clarity](https://play.google.com/store/apps/details?id=com.okin.bedding.customaticclarity) 1.0.1 | `com.okin.bedding.customaticclarity` | [Customatic Clarity](#customatic-clarity) |
| ✅ | [Customatic Jerome's](https://play.google.com/store/apps/details?id=com.okin.bedding.customaticjeromes) 1.0.1 | `com.okin.bedding.customaticjeromes` | [Customatic Jerome's](#customatic-jeromes) |
| ✅ | [Customatic Remedy](https://play.google.com/store/apps/details?id=com.okin.bedding.customaticremedy) 1.0.1 | `com.okin.bedding.customaticremedy` | [Customatic Remedy](#customatic-remedy) |
| ✅ | [Prodigy 2L](https://play.google.com/store/apps/details?id=com.leggett.prodigy2L) 1.2 (15) | `com.leggett.prodigy2L` | [Prodigy 2L](#prodigy-2l) |
| ✅ | [Prodigy 2](https://play.google.com/store/apps/details?id=com.leggett.prodigy2) 2.2.0 (44) | `com.leggett.prodigy2` | [Prodigy 2](#prodigy-2) |
| ✅ | [Prodigy CE / Prodigy 4](https://play.google.com/store/apps/details?id=com.leggett.prodigy4) 1.2.0 (18) | `com.leggett.prodigy4` | [Prodigy CE](#prodigy-ce-prodigy-4) |
| ✅ | [U / Ultra Series](https://play.google.com/store/apps/details?id=com.leggett.useries) 2.1 (16) | `com.leggett.useries` | [U Series](#u-series) |

Beds controlled with FurniMove handset IDs normally use the explicit
[FurniMove / OKIN Smart Remote](furnimove.md) app profile.

## Features

| Feature | Okimat | DewertOkin | RF ECO BT stair | Customatic | Leggett Okin |
|---|---|---|---|---|---|
| Motor control | ✅ Per handset | ✅ Head, feet | ✅ One stair actuator | ✅ Back, legs; Remedy adds lumbar | ✅ Head, feet, plus pillow and/or lumbar per app |
| Simultaneous movement | ✅ Held motors combine | ❌ | ❌ | ✅ (`customatic_move_simultaneously`) | ✅ Held motors combine |
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

## Choosing a profile

Detection suggests Okimat for the Okin service, DewertOkin by device name and
Leggett Okin by Leggett names; each profile's Setup lists its rules. The stair
lift and the Customatic apps are explicit choices, and Leggett Okin entries
choose their app.

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

Entry pulse settings are the configured motor pulse count and delay.

### One-shot timing

| Profile | Presets and recall | Memory save | Sync, child lock | Light, massage | Control mode |
|---|---|---|---|---|---|
| Okimat handset table | 100 × 300 ms, 1 STOP | 10 × 200 ms, no STOP (or the handset's hold) | 60 × 100 ms, 1 STOP | once, no STOP | n/a |
| DewertOkin | 100 × 300 ms, 1 STOP | n/a | n/a | once, no STOP | n/a |
| OKIN Smart Remote RF ECO BT stair lift | n/a | n/a | n/a | n/a | n/a |
| Customatic Clarity | once, no STOP | n/a | n/a | once, no STOP | n/a |
| Customatic Jerome's | 3 × 0 ms, no STOP | n/a | n/a | n/a | n/a |
| Customatic Remedy | once, no STOP | n/a | n/a | once, no STOP | n/a |
| Prodigy 2L | 10 × 100 ms, no STOP | n/a | n/a | once, then 100 ms, 4 STOP | 55 × 100 ms, 1 STOP |
| Prodigy 2 | 10 × 100 ms, no STOP | n/a | n/a | once, then 100 ms, 4 STOP | 55 × 100 ms, 1 STOP |
| Prodigy CE | 10 × 100 ms, no STOP | n/a | n/a | once, then 100 ms, 4 STOP | 55 × 100 ms, 1 STOP |
| U Series | 10 × 100 ms, no STOP | n/a | n/a | once, then 100 ms, 4 STOP | n/a |

Leggett Okin profiles also stream Flat for 30000 ms and program a favorite by
holding the store key 5000 ms, then the slot 2000 ms. Customatic named memory
controls hold 2700 ms with no STOP.
<!-- /generated -->

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

The settings channel opens with `01 02` after subscribing.
<!-- /generated -->

Numeric GATT handles vary by device and firmware, so every profile writes by
characteristic UUID. Issue [#394](https://github.com/kristofferR/ha-adjustable-bed/issues/394)
reported a bed whose write characteristic was handle `0x000d` while `0x0013`
belonged to another attribute.

### Framing and checksum

**Frame:** `N 02 <N-byte command word, big-endian>`, so a frame is `N + 2` bytes.
Every profile in this guide uses 32-bit words (`N = 4`), giving six bytes. The
codec also builds the 40-, 48-, 64- and 96-bit widths for the routes that move
onto it later. There is no checksum, sequence number or authentication payload.

**Command word:** a bit mask of held keys. Keys held together are one frame with
several bits set, and the zero word releases every key (STOP).

**RF-Gateway envelope (revision 0):** `E5 FE 16 <command word> <checksum>`, eight
bytes. The checksum is the inverted low byte of the sum of the first seven bytes,
so all eight bytes sum to `0xFF`. DewertOkin RF-Gateway receivers and Leggett
boxes without the revision selector take this envelope; the words are the same.

### Command encoders

The words below are profile data, framed by `codec.frame()` and, where a profile
can use it, `codec.gateway_frame()`. Okimat words come from the selected handset
table; see [Okimat handset keys](#okimat-handset-keys).

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
- Every cleanup runs with a fresh cancel event, so a stop request cannot
  suppress it.

The [hold and release timing](#hold-and-release-timing) table has the counts
and intervals.

### Vectors

`tests/okin_nframe_vectors.py` lists each profile's frozen frames: app profiles
take every 32-bit literal from their accepted report, and the Okimat, DewertOkin
and RF ECO BT routes take the frames the pre-v5 controllers sent, including the
RF-Gateway envelopes. `tests/test_okin_nframe_vectors.py` checks that every
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
  box, the entry uses the [Okin DOT](okin-dot.md) controller.

**Detection.** Okimat is the fallback for the Okin service UUID. Some receiver
modules only advertise a local name such as `OKIN-Receiver` or `OKIN - Receiver`
until paired; those are shown as a pairing-required Okin-family protocol
selection, because the receiver name and the shared service UUID do not identify
the packet format. Priority:

1. Device name contains "nectar" → [Nectar](nectar.md)
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
- Motors held together send the sum of their words in one frame.
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
> 98035). They are the separate [Okin DOT](okin-dot.md) bed type: if that number
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
  `com.okin.simmons` app use the explicit [SIMMONS app profile](simmons.md).
- **Customatic:** Customatic Demo; Clarity, Remedy and Jerome's C use the
  [Customatic app profiles](#customatic-family)
- **Mattress brands:** Mattress Firm (except Sleepy's Elite, see
  [Sleepy's Elite](sleepys.md)), Nectar Motion, Glory Furniture, Tranquil Sleep,
  Luxe, Ultra
- **ORE/Glideaway family:** Glideaway Motion (current app:
  [explicit MOTION 400/450/500/600 profile](glideaway-motion.md)), Symphony
  Sleep, Movita, Dynasty Bases (current app:
  [MaxCoil Una / Dynasty Bases / Bedsense Bases profile](ore-comfort-bed.md)),
  Better Living, LevaSleep, American Star, Avanti Bases (current app: explicit
  [Avanti Bases profile](ore-comfort-bed.md), `avanti_bases`), Comfort
  Furniture, Hestia Motion, Maxcoil Una (current app:
  [MaxCoil Una / Dynasty Bases / Bedsense Bases profile](ore-comfort-bed.md)),
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
| FFE0/Solace | 19 | `0000ffe0-...` | [Solace](solace.md) |
| Nordic UART | 5 | `6e400001-...` | [Mattress Firm 900](mattressfirm.md) |
| FFF0/WiLinke | 2 | `0000fff0-...` | [Leggett & Platt](leggett-platt.md) |

| App | Package ID | Protocol |
|---|---|---|
| MFRM Sleepy's Elite | `com.okin.bedding.sleepy` | Multi-protocol |
| Resident | `com.okin.resident.release` | Flutter |
| Rize II | `com.okin.bedding.rizeii` | OKIN UUID |
| Simmons | `com.okin.simmons` | Flutter; own frames, see [SIMMONS app](simmons.md) |
| Glideaway | `com.ore.bedding.glideawaymontion` | E6 FE 16 on FFE5/FFE9, [explicit Motion app profile](glideaway-motion.md) |
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
or a full bed using [Okin CST](okin-cst.md); it is not a safe discriminator, and
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

Other Okin formats, which share roots but not frames: [Nectar](nectar.md)
(7 bytes), [Mattress Firm 900](mattressfirm.md) (7 bytes over Nordic UART),
[Okin CST](okin-cst.md) (14 bytes) and [Okin 64-Bit](okin-64bit.md) (10-byte
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
