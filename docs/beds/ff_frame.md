# FFFF frame (Solace, Woosa Sleep, BedSense, Motion Bed)

**Status:** ⚠️ Partially tested (the Solace S4-Y layout and Woosa Sleep controls are user-confirmed; the other profiles are APK-verified with hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), Bonopaws and [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt)

One wire codec (`FF FF FF FF ...` frames on one FFE1 characteristic) serves four
apps and three bed types: the name-selected **Solace** routes and the explicit
**Woosa Sleep** variant (bed type `solace`), the **BedSense** app (`bedsense`)
and the **Motion Bed** app (`motion_bed`). This guide covers the codec first, then
one section per profile. See [Protocol codecs and app profiles](../design/protocol-codecs.md)
for the architecture.

The apps overlap but do not share one feature set. A shared name, UUID or frame
never selects another app's profile: each bed type and variant is chosen
explicitly or by its own name rules.

## Known Models

- Solace hospital/care beds and some medical adjustable beds
- Sealy adjustable bases (MotionFlex, `SealyMF*` names)
- QMS-series beds (QMS-IQ, QMS-I06, QMS-LQ, QMS-L04, QMS-JQ-D, QMS-NQ, QMS-MQ,
  QMS2, QMS3, QMS4, etc.) and S-series beds (S3-2, S3-3, S3-4, S4-N, S4-Y, S5-Y, S6-Y)
- Woosa Sleep adjustable bases controlled by the Woosa Sleep app (Android and iOS)
- BedSense app layouts: BEDSENSE-850, BEDSENSE-890, BEDSENSE-1150, BEDSENSE-1050,
  BEDSENSE-250, BEDSENSE-150, BEDSENSE-350, Resten Hi-Low and the app's Default layout
- Motion Bed modular products: TL-B motor module, TL-A air massage, TL-W thermal
  control and the TL-Q hub

Bluetooth names such as `QMS-MQ` and `QMS2` are shared across these apps and do
not identify which app's layout a bed implements.

## Apps

| Analyzed | App | Package ID | Profile |
|----------|-----|------------|---------|
| ✅ | [HomeKobo](https://play.google.com/store/apps/details?id=com.ly.homekobo) 1.4 | `com.ly.homekobo` | [Solace name routes](#solace-name-routes) (Home K1, Home K2, common) |
| ✅ | [Sealy MotionFlex](https://play.google.com/store/apps/details?id=com.sealy.motionflex) 1.0.3 | `com.sealy.motionflex` | [Solace name routes](#solace-name-routes) (MotionFlex) |
| ✅ | [Sweet Night](https://play.google.com/store/apps/details?id=com.sn.dianqi) 1.0.6 | `com.sn.dianqi` | [Solace name routes](#solace-name-routes) (common) |
| ✅ | [Woosa Sleep](https://play.google.com/store/apps/details?id=com.sn.woosa) 1.1.9 (13) | `com.sn.woosa` | [Woosa Sleep](#woosa-sleep) |
| ✅ | [BedSense](https://play.google.com/store/apps/details?id=com.fenmenbielei.bedsense) 1.8 (18) | `com.fenmenbielei.bedsense` | [BedSense](#bedsense) |
| ✅ | [Motion Bed](https://play.google.com/store/apps/details?id=com.sn.blackdianqi) 1.24 (34) | `com.sn.blackdianqi` | [Motion Bed](#motion-bed) |

- Bedsense Bases (`com.ore.bedsense`) is a different app and wire format; see its
  [profile](keeson.md#ore-comfort-bed-profiles).
- Motion Bed and Woosa Sleep share a developer (`com.sn` prefix). The Motion Bed
  report is used only by its own profile, never for Solace routing.

## Features

| Feature | Solace name routes | Woosa Sleep | BedSense | Motion Bed |
|---------|--------------------|-------------|----------|------------|
| Motor Control | ✅ Back and legs; head plus hip (K1) or lumbar (K2); bed height and tilt on exact S4-Y | ✅ Back and legs | ✅ Per layout: back, waist/hip, head, legs, back and leg, lift, rise and fall | ✅ The selected layout's exact control pairs, including split and coupled sides |
| Position Feedback | ❌ (preset-state replies are not positions) | ❌ | ❌ | ⚠️ Raw positions A–D only (unknown units) |
| Presets | ✅ Flat, Zero-G, Anti-Snore, TV on every identified route; relaxing bedtime on MotionFlex | ✅ Flat, Favourite, Anti-Snore, TV, Zero-G | ✅ Flat, TV, Zero Gravity, Anti Snore where the app exposes them | ✅ Named app presets with state-dependent recall and programming |
| Memory Presets | ✅ 2 numbered slots | ✅ 1 Favourite slot, saves for four stored presets | ✅ Five recalls and saves, explicit clear buttons | ✅ App-labelled |
| Massage | ⚠️ Home profiles only (zones, wave, K1 circulation, timers) | ✅ Back and leg levels 0–3, four modes, timers, steps, Off | ✅ Circulation (types 1–5), head/foot, wave, timers | ✅ Bed massage; TL-A air programs and pressure |
| Lights | ⚠️ MotionFlex levels 0–10 and timers; timers only on HomeKobo and Sweet Night routes | ✅ Levels 0–10, timed lighting, Off | ⚠️ Light-duration buttons only | ✅ |
| Audio, clock and alarm | ⚠️ MotionFlex | ⚠️ Alarm only | ❌ | ✅ |
| Sleep, thermal and hub controls | ❌ | ❌ | ❌ | ✅ Sleep angles, calibration, timers, reports; TL-W thermal; TL-Q modules |
| Wi-Fi provisioning and cloud | ❌ | ❌ | ❌ | ❌ Excluded (outside the product boundary) |
| Hold until release | ✅ ([renewable](../SERVICES.md#renewable-holds), latched: up to 10 s, then STOP); ❌ Legacy S4-Y and unidentified entries | ✅ ([renewable](../SERVICES.md#renewable-holds), latched: up to 10 s, then STOP) | ✅ ([renewable](../SERVICES.md#renewable-holds), latched: up to 10 s, then STOP) | ❌ (no renewable route) |

## Choosing a profile

- **Solace** (bed type `solace`, variant `auto`) picks the narrowest route its
  Bluetooth name proves (see [Solace name routes](#solace-name-routes)). Select
  protocol variant `woosa` for beds that use the Woosa Sleep app.
- **BedSense** (bed type `bedsense`) is an explicit choice; its layout comes from
  the Bluetooth name or a `bedsense_1` to `bedsense_9` variant.
- **Motion Bed** (bed type `motion_bed`) is an explicit choice that follows the
  app's ordered name routing.

<!-- generated:ff-frame-profiles -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

### Solace routes

| Route | Key | Axes | Presets | Memory | Status query | Massage | Lights | Extras |
|---|---|---|---|---|---|---|---|---|
| Common | `common` | back, legs | yes | 2 slots | Q2 | none | light timer | none |
| Home K1 | `home_k1` | back, legs, head, hip | yes | 2 slots | Q1 | massage, circulation | light timer | none |
| Home K2 | `home_k2` | back, legs, head, lumbar | yes | 2 slots | Q1 (Q2 for compound names) | massage | light timer | none |
| MotionFlex | `motion_flex` | back, legs | yes | 2 slots | Q2 | none | light levels, light timer | relaxing bedtime, audio, alarm, clock sync |
| Woosa Sleep | `woosa` | back, legs | yes | 1 slot | Woosa | massage | light levels, light timer | alarm |
| Legacy S4-Y | `legacy_s4_y` | back, legs, bed_height, tilt | yes | 2 slots | none, no notifications | none | none | none |
| Unverified | `unverified` | back, legs | no | 0 slots | none, no notifications | none | none | none |

### Timing

Offsets count from notification start. Movement and STOP timing are in [STOP and
release behavior](#stop-and-release-behavior).

| Profile | Startup | Other pacing |
|---|---|---|
| Common | +300 ms: Q2 queries, 500 ms apart | none |
| Home K1 | +300 ms: Q1 queries, 500 ms apart | none |
| Home K2 | +300 ms: Q1 (Q2 for compound names) queries, 500 ms apart | none |
| MotionFlex | +300 ms: clock, Q2 queries, light status, 500 ms apart | none |
| Legacy S4-Y | none | none |
| Unverified | none | none |
| Woosa Sleep | Woosa startup schedule | presets: STOP, 200 ms, preset; massage start steps 400 ms apart; after a save, each preset query 300 ms apart |
| BedSense | read every FFE1 characteristic after 200 ms; memory queries from +2000 ms, 200 ms apart | memory refresh: +2000 ms, then 200 ms apart |

### Woosa startup schedule

Both app startup workers, serialized; equal offsets keep their order.

| Offset | Bytes (hex) |
|---|---|
| 500 ms | `FF FF FF FF 02 00 0E 0B 00 17 04` |
| 600 ms | `FF FF FF FF 03 00 28 00 03 9F 09` |
| 900 ms | `FF FF FF FF 03 00 18 00 03 9F 06` |
| 1000 ms | clock |
| 1200 ms | `FF FF FF FF 03 00 20 00 03 1E CB` |
| 1500 ms | `FF FF FF FF 01 00 0A 0B 0F 21 04` |
| 1500 ms | `FF FF FF FF 03 00 38 00 03 9E CC` |
| 1500 ms | `FF FF FF FF 05 00 05 FF 23 C7 28` |

### BedSense layouts

| Type | Movement axes | App actions |
|---|---|---|
| 1 | back, waist, back_and_leg, legs | 51 |
| 2 | back, waist, head, legs | 51 |
| 3 | back, waist, head, legs | 51 |
| 4 | back, hip, head, legs | 53 |
| 5 | back, hip, head, legs | 53 |
| 6 | back | 39 |
| 7 | back, legs | 43 |
| 8 | back, rise_and_fall | 41 |
| 9 | back, hip, lift, legs | 49 |

### Motion Bed callsites

714 app callsites over 190 distinct frames, each gated by layout, module and
state.
<!-- /generated -->

## Wire codec

`codec/ff_frame.py` builds every frame the profiles send.

### Transports

<!-- generated:ff-frame-transports -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Service | Write and notify | Profiles |
|---|---|---|
| `0000ffe0-0000-1000-8000-00805f9b34fb` (advertised, not required) | `0000ffe1-0000-1000-8000-00805f9b34fb` | all |
<!-- /generated -->

- Every app traverses all discovered services; none requires the service UUID.
- No profile uses authentication, bonding, a PIN, MTU negotiation or encryption.
- Each profile's Setup says which FFE1 characteristic it subscribes to and
  writes when several exist.

### Framing and checksum

Every frame starts `FF FF FF FF`. The fifth byte (the kind) selects the trailer:

| Kind | Layout | Trailer |
|------|--------|---------|
| `05` | `FF FF FF FF 05 00 <group> <arg> <code>`, 11 bytes | CRC-16/MODBUS |
| `03` | `FF FF FF FF 03 00 <register> 00 <count>`, 11 bytes | CRC-16/MODBUS |
| `01`, `02` | `FF FF FF FF <kind> 00 <opcode> <length> <payload>`; `length` counts the whole frame | 16-bit sum |
| `FE`, `FF` | Motion Bed module frames (`FF` air, `FE` thermal) | CRC-16/MODBUS |

- **CRC-16/MODBUS**: initial value `FFFF`, reflected polynomial `A001`, over every
  preceding byte including the header, appended low byte first.
- **Sum**: the sum of every preceding byte, appended little-endian. The header
  alone sums to `03FC`, so every frame carries two trailer bytes.
- The apps ship most frames as fixed hex literals. They all follow these two
  rules except BedSense row C018 (`FF FF FF FF 05 00 00 00 00 D8 14`), whose
  trailer is not its CRC; the BedSense profile sends it verbatim.
- Motion Bed module builders keep the app's fixed length bytes, which do not
  always count the frame.

### Command encoders

| Encoder | Frame |
|---------|-------|
| `control(code, arg=0, group=0)` | Kind `05` control frame |
| `query(register, count)` | Kind `03` status query |
| `summed(kind, opcode, payload)` | Kind `01`/`02` frame with its length byte |
| `clock(now, weekday)` | `01 00 01 11` with BCD hour, minute, second, raw weekday 1-7, BCD year, month, day |
| `alarm(...)` | `01 00 02 13` with switch, BCD hour, BCD minute, `00`, weekday mask, repeat, mode, massage, sound |
| `with_crc(body)`, `with_sum(body)` | Trailers for module frames and fixed-length builders |

The tables below cover the Solace routes and Woosa. BedSense and Motion Bed have
their own tables in their sections.

#### Motion

<!-- generated:ff-frame-motion -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Axis | Up | Down | Routes |
|---|---|---|---|
| Back | `FF FF FF FF 05 00 00 00 03 97 01` | `FF FF FF FF 05 00 00 00 04 D6 C3` | Common, Home K1, Home K2, MotionFlex, Woosa Sleep, Legacy S4-Y, Unverified |
| Legs | `FF FF FF FF 05 00 00 00 06 57 02` | `FF FF FF FF 05 00 00 00 07 96 C2` | Common, Home K1, Home K2, MotionFlex, Woosa Sleep, Legacy S4-Y, Unverified |
| Head | `FF FF FF FF 05 00 00 00 01 16 C0` | `FF FF FF FF 05 00 00 00 02 56 C1` | Home K1, Home K2 |
| Hip | `FF FF FF FF 05 00 00 00 0D 16 C5` | `FF FF FF FF 05 00 00 00 0E 56 C4` | Home K1 |
| Lumbar | `FF FF FF FF 05 00 00 00 0D 16 C5` | `FF FF FF FF 05 00 00 00 0E 56 C4` | Home K2 |
| Bed height | `FF FF FF FF 05 00 00 00 21 17 18` | `FF FF FF FF 05 00 00 00 22 57 19` | Legacy S4-Y |
| Tilt | `FF FF FF FF 05 00 00 00 28 D7 1E` | `FF FF FF FF 05 00 00 00 29 16 DE` | Legacy S4-Y |

STOP is `FF FF FF FF 05 00 00 00 00 D7 00` on every route. Woosa's leg-down
control sends Flat.
<!-- /generated -->

#### Presets

<!-- generated:ff-frame-presets -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

Programming a named preset is Woosa only; the other routes recognize these program
frames in replies and echoes.

| Preset | Recall | Recall while selected | Program | Clear | Routes |
|---|---|---|---|---|---|
| Flat | `FF FF FF FF 05 00 00 00 08 D6 C6` | n/a | n/a | n/a | every route with presets except Legacy S4-Y |
| Flat (legacy all-flat) | `FF FF FF FF 05 00 00 00 2A 56 DF` | n/a | n/a | n/a | Legacy S4-Y |
| TV | `FF FF FF FF 05 00 00 00 05 17 03` | `FF FF FF FF 05 00 00 51 05 2A 93` | `FF FF FF FF 05 00 00 50 05 2B 03` | `FF FF FF FF 05 00 00 5F 05 2E F3` | Common, Home K1, Home K2, MotionFlex, Woosa Sleep, Legacy S4-Y |
| Zero-G | `FF FF FF FF 05 00 00 00 09 17 06` | `FF FF FF FF 05 00 00 91 09 7A 96` | `FF FF FF FF 05 00 00 90 09 7B 06` | `FF FF FF FF 05 00 00 9F 09 7E F6` | Common, Home K1, Home K2, MotionFlex, Woosa Sleep, Legacy S4-Y |
| Anti-Snore (Woosa: Love) | `FF FF FF FF 05 00 00 00 0F 97 04` | `FF FF FF FF 05 00 00 F1 0F D2 94` | `FF FF FF FF 05 00 00 F0 0F D3 04` | `FF FF FF FF 05 00 00 FF 0F D6 F4` | Common, Home K1, Home K2, MotionFlex, Woosa Sleep, Legacy S4-Y |
| Relaxing bedtime | `FF FF FF FF 05 00 00 00 6A 57 2F` | n/a | n/a | n/a | MotionFlex |
<!-- /generated -->

#### Memory

<!-- generated:ff-frame-memory -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Slot | Recall | Program | Program while selected | Routes |
|---|---|---|---|---|
| 1 | `FF FF FF FF 05 00 00 A1 0A 2E 97` | `FF FF FF FF 05 00 00 A0 0A 2F 07` | `FF FF FF FF 05 00 00 AF 0A 2A F7` | Common, Home K1, Home K2, MotionFlex, Woosa Sleep, Legacy S4-Y |
| 2 | `FF FF FF FF 05 00 00 B1 0B E2 97` | `FF FF FF FF 05 00 00 B0 0B E3 07` | `FF FF FF FF 05 00 00 BF 0B E6 F7` | Common, Home K1, Home K2, MotionFlex, Legacy S4-Y |

Woosa saves its Favourite slot with the program frame only.
<!-- /generated -->

#### Massage

<!-- generated:ff-frame-massage -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Command | Bytes (hex) | Routes |
|---|---|---|
| Head + | `FF FF FF FF 05 00 00 00 10 D6 CC` | Home K1, Home K2, Woosa Sleep |
| Head - | `FF FF FF FF 05 00 00 00 11 17 0C` | Home K1, Home K2, Woosa Sleep |
| Foot + | `FF FF FF FF 05 00 00 00 12 57 0D` | Home K1, Home K2, Woosa Sleep |
| Foot - | `FF FF FF FF 05 00 00 00 13 96 CD` | Home K1, Home K2, Woosa Sleep |
| Stop | `FF FF FF FF 05 00 00 00 1C D6 C9` | Home K1, Home K2, Woosa Sleep |
| Timer 10 min | `FF FF FF FF 05 00 00 00 16 56 CE` | Home K1, Home K2, Woosa Sleep |
| Timer 20 min | `FF FF FF FF 05 00 00 00 17 97 0E` | Home K1, Home K2, Woosa Sleep |
| Timer 30 min | `FF FF FF FF 05 00 00 00 18 D7 0A` | Home K1, Home K2, Woosa Sleep |
| Wave + | `FF FF FF FF 05 00 00 00 14 D7 0F` | Home K1, Home K2 |
| Wave - | `FF FF FF FF 05 00 00 00 15 16 CF` | Home K1, Home K2 |
| Cycle full body | `FF FF FF FF 05 00 05 00 E4 C7 4A` | Home K1 |
| Cycle head | `FF FF FF FF 05 00 05 00 E3 86 88` | Home K1 |
| Cycle leg | `FF FF FF FF 05 00 05 00 E5 06 8A` | Home K1 |
| Cycle hip | `FF FF FF FF 05 00 05 00 E6 46 8B` | Home K1 |

**Woosa massage levels and modes**

| Command | Bytes (hex) |
|---|---|
| Head level 0 | `FF FF FF FF 05 00 00 00 4F 96 F4` |
| Head level 1 | `FF FF FF FF 05 00 00 00 50 D7 3C` |
| Head level 2 | `FF FF FF FF 05 00 00 00 51 16 FC` |
| Head level 3 | `FF FF FF FF 05 00 00 00 52 56 FD` |
| Foot level 0 | `FF FF FF FF 05 00 00 00 53 97 3D` |
| Foot level 1 | `FF FF FF FF 05 00 00 00 54 D6 FF` |
| Foot level 2 | `FF FF FF FF 05 00 00 00 55 17 3F` |
| Foot level 3 | `FF FF FF FF 05 00 00 00 56 57 3E` |
| Mode 1 | `FF FF FF FF 05 00 00 00 57 96 FE` |
| Mode 2 | `FF FF FF FF 05 00 00 00 58 D6 FA` |
| Mode 3 | `FF FF FF FF 05 00 00 00 59 17 3A` |
| Mode 4 | `FF FF FF FF 05 00 00 00 5A 57 3B` |
| Mode step | `FF FF FF FF 05 00 05 00 14 C7 0E` |

##### Woosa massage replies

| Reply | Level or mode 0-3 (mode 1-4) |
|---|---|
| Head | `FF FF FF FF 05 00 00 01 00 D6 90`, `FF FF FF FF 05 00 00 01 1E 56 98`, `FF FF FF FF 05 00 00 01 1F 97 58`, `FF FF FF FF 05 00 00 01 20 D7 48` |
| Foot | `FF FF FF FF 05 00 00 02 00 D6 60`, `FF FF FF FF 05 00 00 02 21 16 78`, `FF FF FF FF 05 00 00 02 22 56 79`, `FF FF FF FF 05 00 00 02 23 97 B9` |
| Mode | `FF FF FF FF 05 00 00 03 24 D7 EB`, `FF FF FF FF 05 00 00 03 25 16 2B`, `FF FF FF FF 05 00 00 03 26 56 2A`, `FF FF FF FF 05 00 00 03 27 97 EA` |
<!-- /generated -->

#### Lights

<!-- generated:ff-frame-lights -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Command | Bytes (hex) | Routes |
|---|---|---|
| Level 0 | `FF FF FF FF 05 00 00 00 23 96 D9` | MotionFlex, Woosa Sleep |
| Level 1 | `FF FF FF FF 05 00 00 01 23 97 49` | MotionFlex, Woosa Sleep |
| Level 2 | `FF FF FF FF 05 00 00 02 23 97 B9` | MotionFlex, Woosa Sleep |
| Level 3 | `FF FF FF FF 05 00 00 03 23 96 29` | MotionFlex, Woosa Sleep |
| Level 4 | `FF FF FF FF 05 00 00 04 23 94 19` | MotionFlex, Woosa Sleep |
| Level 5 | `FF FF FF FF 05 00 00 05 23 95 89` | MotionFlex, Woosa Sleep |
| Level 6 | `FF FF FF FF 05 00 00 06 23 95 79` | MotionFlex, Woosa Sleep |
| Level 7 | `FF FF FF FF 05 00 00 07 23 94 E9` | MotionFlex, Woosa Sleep |
| Level 8 | `FF FF FF FF 05 00 00 08 23 91 19` | MotionFlex, Woosa Sleep |
| Level 9 | `FF FF FF FF 05 00 00 09 23 90 89` | MotionFlex, Woosa Sleep |
| Level 10 | `FF FF FF FF 05 00 00 0A 23 90 79` | MotionFlex, Woosa Sleep |
| Status query | `FF FF FF FF 05 00 05 FF 23 C7 28` | MotionFlex, Woosa Sleep |
| Timer 10 min | `FF FF FF FF 05 00 00 00 19 16 CA` | Common, Home K1, Home K2, MotionFlex, Woosa Sleep |
| Timer 8 hours | `FF FF FF FF 05 00 00 00 1A 56 CB` | Common, Home K1, Home K2, MotionFlex, Woosa Sleep |
| Timer 10 hours | `FF FF FF FF 05 00 00 00 1B 97 0B` | Common, Home K1, Home K2, MotionFlex, Woosa Sleep |
| Off | `FF FF FF FF 05 00 00 00 4B 97 37` | Woosa Sleep |

Routes with brightness offer an Off light timer, which sends level 0 (Woosa: Off).
<!-- /generated -->

#### Audio

<!-- generated:ff-frame-audio -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

Routes: MotionFlex.

| Command | Bytes (hex) |
|---|---|
| Music toggle | `FF FF FF FF 01 00 13 0B FF 1A 05` |
| Music off | `FF FF FF FF 01 00 13 0B 00 1B 04` |
| Volume query | `FF FF FF FF 01 00 15 0B 00 1D 04` |
| Track 1 | `FF FF FF FF 01 00 13 0B 01 1C 04` |
| Track 1 preview | `FF FF FF FF 01 00 13 0B 81 9C 04` |
| Track 2 | `FF FF FF FF 01 00 13 0B 02 1D 04` |
| Track 2 preview | `FF FF FF FF 01 00 13 0B 82 9D 04` |
| Track 3 | `FF FF FF FF 01 00 13 0B 03 1E 04` |
| Track 3 preview | `FF FF FF FF 01 00 13 0B 83 9E 04` |
| Track 4 | `FF FF FF FF 01 00 13 0B 04 1F 04` |
| Track 4 preview | `FF FF FF FF 01 00 13 0B 84 9F 04` |
| Track 5 | `FF FF FF FF 01 00 13 0B 05 20 04` |
| Track 5 preview | `FF FF FF FF 01 00 13 0B 85 A0 04` |
| Volume 1 | `FF FF FF FF 01 00 14 0B 01 1D 04` |
| Volume 2 | `FF FF FF FF 01 00 14 0B 02 1E 04` |
| Volume 3 | `FF FF FF FF 01 00 14 0B 03 1F 04` |
| Volume 4 | `FF FF FF FF 01 00 14 0B 04 20 04` |
| Volume 5 | `FF FF FF FF 01 00 14 0B 05 21 04` |
<!-- /generated -->

#### Queries

<!-- generated:ff-frame-queries -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

**Q1**

| Order | Bytes (hex) |
|---|---|
| 1 | `FF FF FF FF 03 00 28 00 09 1F 0E` |
| 2 | `FF FF FF FF 03 00 31 00 09 CE C9` |
| 3 | `FF FF FF FF 03 00 16 00 09 7E C2` |
| 4 | `FF FF FF FF 03 00 1F 00 09 AE C0` |
| 5 | `FF FF FF FF 03 00 3A 00 09 BF 0B` |

**Q2**

| Order | Bytes (hex) |
|---|---|
| 1 | `FF FF FF FF 03 00 28 00 03 9F 09` |
| 2 | `FF FF FF FF 03 00 30 00 03 1F 0E` |
| 3 | `FF FF FF FF 03 00 18 00 03 9F 06` |
| 4 | `FF FF FF FF 03 00 20 00 03 1E CB` |
| 5 | `FF FF FF FF 03 00 38 00 03 9E CC` |

**Woosa preset queries** (also re-sent after each save)

| Order | Bytes (hex) |
|---|---|
| 1 | `FF FF FF FF 03 00 28 00 03 9F 09` |
| 2 | `FF FF FF FF 03 00 18 00 03 9F 06` |
| 3 | `FF FF FF FF 03 00 20 00 03 1E CB` |
| 4 | `FF FF FF FF 03 00 38 00 03 9E CC` |

Woosa also sends init `FF FF FF FF 02 00 0E 0B 00 17 04` and alarm query
`FF FF FF FF 01 00 0A 0B 0F 21 04` at startup.

**BedSense Default (types 1-5, 9)**

| Order | Bytes (hex) |
|---|---|
| 1 | `FF FF FF FF 03 00 16 00 09 7E C2` |
| 2 | `FF FF FF FF 03 00 1F 00 09 AE C0` |
| 3 | `FF FF FF FF 03 00 28 00 09 1F 0E` |
| 4 | `FF FF FF FF 03 00 31 00 09 CE C9` |
| 5 | `FF FF FF FF 03 00 3A 00 09 BF 0B` |

**BedSense Types 6 and 8**

| Order | Bytes (hex) |
|---|---|
| 1 | `FF FF FF FF 03 00 14 00 03 5F 05` |
| 2 | `FF FF FF FF 03 00 1C 00 03 DE C7` |
| 3 | `FF FF FF FF 03 00 24 00 03 5F 0A` |
| 4 | `FF FF FF FF 03 00 2C 00 03 DE C8` |
| 5 | `FF FF FF FF 03 00 3A 00 09 BF 0B` |

**BedSense Type 7**

| Order | Bytes (hex) |
|---|---|
| 1 | `FF FF FF FF 03 00 18 00 03 9F 06` |
| 2 | `FF FF FF FF 03 00 20 00 03 1E CB` |
| 3 | `FF FF FF FF 03 00 28 00 03 9F 09` |
| 4 | `FF FF FF FF 03 00 30 00 03 1F 0E` |
| 5 | `FF FF FF FF 03 00 38 00 03 9E CC` |
<!-- /generated -->

#### Clock and alarm

- Clock: `clock(now, weekday)` with Home Assistant local time and the ISO weekday.
- Alarm switch byte: `01` enabled, `A1` disabled (Motion Bed modular alarms also
  `00` uninitialized). The weekday mask sets bit `1 << weekday` for weekdays 1-7;
  the repeat byte is `01` when any weekday map is present.

| Alarm field | Solace and Woosa values |
|-------------|-------------------------|
| Mode | `zero_g` `01`, `memory_1` `02`, `no_action` `03` |
| Sound | `none` `00`, `alarm` `01`, `music_1`-`music_5` `11`-`15` (MotionFlex only) |

### Responses

Replies arrive as notifications in the same framing. No app checks their
trailers. Each profile section names the replies it consumes:

- **Solace routes** and **Woosa**: substring parsers in `beds/solace.py` and
  `beds/woosa.py` (preset state `FF FF FF FF 03 06 00 <selector>`, program echoes,
  light, volume, alarm and Woosa massage replies).
- **BedSense**: the ordered memory-indicator rules in `profiles/ff_frame.py`.
- **Motion Bed**: the state parser in `motion_bed_state.py`.

### STOP and release behavior

- STOP is the kind `05` frame with code `00` (see [Motion](#motion)) on every
  profile. Motion Bed air and thermal surfaces stop with their module's own
  frames (see [Motion Bed](#motion-bed)).
- Movement sends one start frame and the controller latches until STOP. There is
  no refresh cadence. Home Assistant ends the move after a bounded window (Solace
  and Woosa 5 s, BedSense the motor pulse count times its delay, Motion Bed the
  action's duration) or on an explicit stop, and always sends STOP in cleanup
  with a fresh cancel event.
- These windows are integration safety caps, not firmware timeouts.

### Vectors

`tests/ff_frame_vectors.py` lists each profile's frozen frames: every complete
written frame in the accepted report (its command table and write-builder
vectors) for the app profiles, and the pre-v5 controller's frames for the
Legacy S4-Y and Unverified routes. `tests/test_ff_frame_vectors.py` proves that
every literal round-trips through the codec byte for byte (the BedSense C018
anomaly is listed separately and must not), and that every fixed frame a
profile can send is among its frozen literals.

## Profiles

### Solace name routes

**App:** [HomeKobo](https://play.google.com/store/apps/details?id=com.ly.homekobo) 1.4, `com.ly.homekobo`; [Sealy MotionFlex](https://play.google.com/store/apps/details?id=com.sealy.motionflex) 1.0.3, `com.sealy.motionflex`; [Sweet Night](https://play.google.com/store/apps/details?id=com.sn.dianqi) 1.0.6, `com.sn.dianqi`

**Status:** ⚠️ Partially tested (the legacy S4-Y layout is user-confirmed; the app routes are APK-verified)

#### Setup

Bed type `solace` with variant `auto` picks a route from the observed Bluetooth
name. Detection is limited to names beginning with the values below, plus
`My QMS2`; matching is case-folded. The route table in
[Choosing a profile](#choosing-a-profile) lists what each route exposes.

| Observed name | Route |
|---|---|
| `QMS-IQ`, `QMS-I06`, `QMS-LQ`, `QMS-L04`, then `QMS-NQ`, `QMS3` | Home K1 |
| `QMS-JQ-D`, `QMS4` | Home K2 |
| `QMS2`, `My QMS2`, `QMS-MQ` | Common |
| `SealyMF*` | MotionFlex |
| Exact `S4-Y-<digits>-<id>` | Legacy S4-Y |
| Any unidentified manual entry | Unverified |

- `QMS2` and `QMS-MQ` use the Common route unless protocol variant `woosa` is
  selected. HomeKobo and Sweet Night both route these names; only HomeKobo
  exposes massage, so the Common route does not assume it.
- A Home K2 name is a compound Q2 name when it also contains `qms-mq`, `qms2`,
  `qms3` or `s3-2`; it then uses the Q2 queries.
- Legacy S4-Y keeps a user-confirmed four-cover layout and the deployed legacy
  all-flat frame. Unverified entries keep back/legs movement and STOP only.
- A name merely containing `solace` is not detected. An FFE0 advertisement with
  an unmatched name defaults to Octo, with Solace, MotoSleep and (for its names)
  Motion Bed offered as alternatives.
- Woosa Sleep beds may also advertise an `ECBLE*` module that does not respond to
  bed commands; configure the `QMS-MQ-*` device.
- Routes with a status query subscribe to FFE1 even when angle sensing is
  disabled, because preset and accessory state arrive there.

#### Controls

- Movement covers follow the route's axes ([Motion](#motion)). K1's fourth axis
  is hip and K2's lumbar; both send the same frames.
- Flat, TV, Zero-G and Anti-Snore on every route with presets
  ([Presets](#presets)). TV, Zero-G and Anti-Snore send their "while selected"
  branch when the bed reports that preset selected.
- Two numbered memories ([Memory](#memory)). Programming sends the "while
  selected" branch when the slot is reported selected. Sweet Night's own Memory 2
  short press duplicates Memory 1; the integration sends the distinct Memory 2
  frame proven by HomeKobo and MotionFlex.
- Home routes: head, foot and wave massage steps, stop and timers; K1 also has the
  four cycle modes ([Massage](#massage)). K2 shares the hip cycle frame with
  lumbar, so the cycle buttons are withheld there.
- MotionFlex: brightness 0-10, where level 0 is off; every route with presets
  except Legacy S4-Y has the three light timers ([Lights](#lights)).
- MotionFlex: relaxing bedtime, music toggle and off buttons
  ([Audio](#audio)).

#### Timing

See [Timing](#timing). Presets are single writes without STOP.

#### Notifications

- Preset state: `FF FF FF FF 03 06 00` followed by selector `0A`, `0B`, `05`,
  `09` or `0F` marks Memory 1, Memory 2, TV, Zero-G or Anti-Snore selected.
  Program frames echoed back ([Presets](#presets), [Memory](#memory)) set or
  clear the same flags. These flags are not position feedback.
- MotionFlex: brightness (`FF FF FF FF 05 00 01`, level in the next byte),
  audio volume (`FF FF FF FF 01 00 15 0B`), no-alarm and audio availability
  (`FF FF FF FF 01 00 03 0B`) and alarm settings (`FF FF FF FF 01 00 04 13`)
  are decoded into controller state.

#### Services

- `adjustable_bed.solace_audio` (MotionFlex) selects or previews tracks 1-5,
  queries the volume and sets volume 1-5.
- `adjustable_bed.solace_set_alarm` (MotionFlex) programs enabled state, time,
  weekdays, bed action, massage and sound ([Clock and alarm](#clock-and-alarm)).

#### Evidence

MotionFlex, HomeKobo and Sweet Night send only their frozen frames; Legacy S4-Y
and Unverified send exactly the pre-v5 controller's frames. The
[MotionFlex ledger](solace-disposition.md) holds the dispositions. Useful
captures after release: one movement start and STOP per route, the five startup
status replies, Flat and one named preset per route, and Sweet Night's Memory 2
short press.

### Woosa Sleep

**App:** [Woosa Sleep](https://play.google.com/store/apps/details?id=com.sn.woosa) 1.1.9 (13), `com.sn.woosa`

**Status:** ⚠️ Partially tested ([the reporter confirmed working controls](https://github.com/kristofferR/ha-adjustable-bed/issues/606#issuecomment-5982450770) with v4.0.1 after selecting Woosa)

Behaves as the [Solace name routes](#solace-name-routes), except as below.

#### Setup

Detection: none. Use bed type **Solace** and select protocol variant **`woosa`**:

1. Update the integration and restart Home Assistant.
2. Open **Settings → Devices & Services → Adjustable Bed → Configure → Change settings**
   and change the protocol variant to **`woosa`**.
3. Submit so the integration reloads its entities.

- The app accepts names containing `QMS-MQ` or `QMS2`, which other apps share.
  Choose this profile from the app you use, not from the name.
- For a separate-address pair, unpair and configure each side first.
- Massage controls are enabled automatically.

#### Controls

- Back and legs. The leg-down arrow sends the Flat frame, as the app does.
- Favourite (Memory 1) recall is refused until the bed reports a saved
  Favourite. Saves exist for Favourite, Anti-Snore, TV and Zero-G.
- Anti-Snore is the app's **Love** preset; HA uses the reporter's iOS app and
  remote label.
- Lights: brightness 0-10, timers 10 min, 8 h and 10 h, and the dedicated Off
  frame ([Lights](#lights)). Turning the light on uses the last timer (10 min by
  default). Light state is optimistic and turns off when the timer elapses.
- Massage: back and leg levels 0-3, four modes, mode step, timers, steps and Off
  ([Massage](#massage)). Massage start sends Off, timer, back level, leg level and
  mode from the stored preferences (back 2, leg 2, mode 2, 10 min until set),
  and sends Off if interrupted. Steps stay within 0-3.
- No HomeKobo hip, lumbar or cycle controls, and no wave controls.

#### Timing

See [Timing](#timing) and [Woosa startup schedule](#woosa-startup-schedule).
Flat sends its frame alone; every other preset uses the STOP preamble.

#### Notifications

- Saved-preset replies start `FF FF FF FF 03 06 00` followed by `0A`
  (Favourite), `0F` (Love), `05` (TV) or `09` (Zero-G). They report that a
  saved position exists, not a measured angle.
- Massage replies set the back and leg levels and the mode
  ([Woosa massage replies](#woosa-massage-replies)).
- Byte 7 of any `FF FF FF FF 05 00` reply is kept as a diagnostic light
  candidate, never as light state.
- Alarm replies starting `FF FF FF FF 01 00 03 0B 00` report no alarm; replies
  starting `FF FF FF FF 01 00 04 13` carry enabled state, time, weekdays, action,
  massage and sound. The **Alarm Enabled** binary sensor shows them.

#### Services

`adjustable_bed.solace_set_alarm` programs the controller alarm, then sends the
alarm query. Modes are `memory_1` (Favourite), `zero_g` and `no_action`; sound
is `none` or `alarm`. Save the Favourite position before choosing `memory_1`.

```yaml
action: adjustable_bed.solace_set_alarm
data:
  device_id: YOUR_BED_DEVICE_ID
  enabled: true
  time: "07:30:00"
  weekdays: [monday, tuesday, wednesday, thursday, friday]
  mode: zero_g
  massage: false
  sound: alarm
```

Run it with `enabled: false` to disable the alarm. Saving an alarm does not
prove the hardware executed it.

#### Evidence

Woosa Sleep sends only its frozen frames. The [Woosa ledger](woosa-disposition.md)
holds the dispositions. Useful captures after release: leg down versus Flat, the
four preset save and recall paths, brightness, clock and alarm, and runtime GATT
properties.

### BedSense

**App:** [BedSense](https://play.google.com/store/apps/details?id=com.fenmenbielei.bedsense) 1.8 (18), `com.fenmenbielei.bedsense`

**Status:** ❓ Needs testing (APK-verified, hardware unverified)

#### Setup

Detection: none. Select **BedSense app (com.fenmenbielei.bedsense)** in manual
setup, then choose a layout or **BedSense layout from the Bluetooth name**. Auto
uses the original, case-sensitive name; a custom HA display name does not
select the layout. The first matching rule wins:

| Type | Name rule | App layout |
| --- | --- | --- |
| 2 | `JQ-D` | BEDSENSE-890 |
| 1 | `JQ` or `NQ` | BEDSENSE-850 |
| 4 | `IQ` | BEDSENSE-1150 |
| 5 | `LQ` | BEDSENSE-1050 |
| 6 | `KQ` without `H` | BEDSENSE-250 |
| 7 | `MQ` or `UPS` | BEDSENSE-150 |
| 9 | `S4-2` | Resten Hi-Low |
| 8 | `H` without `S4` | BEDSENSE-350 |
| 3 | anything else | Default |

- The movement axes per type are in [BedSense layouts](#bedsense-layouts).
- The controller subscribes to and reads every FFE1 characteristic, then writes
  to the last one. It writes without response when that property exists,
  otherwise with response.
- The type 3 waist label reads HIP while pressed in the app; HA keeps the idle
  label. Visible axes do not establish a physical motor count.

##### Home Assistant setup

Select **BedSense app (com.fenmenbielei.bedsense)** and a layout, or select its
case-sensitive Bluetooth-name layout rule. Layout owns the motion controls;
generic motor count, massage and angle-sensing choices are hidden. The original
Bluetooth name and layout belong to each side of a two-address pair. There is no
single-address left/right command. This profile section covers all nine
layouts, memory indicators and app-labelled massage/light actions.

#### Controls

Every action is a row of the command table at the end of this section; **Types**
lists the layouts that expose it.

- Covers send one movement frame and release with STOP after the motor pulse
  window. RISE and DECLINE (type 9) are single clicks without release.
- The **background tap** button sends row C018 verbatim; its physical effect is
  unverified, so it is neither STOP nor massage off.
- Memory: five recalls and saves with explicit clear buttons. Slots 1 and 2
  need a saved indicator; slots 3 to 5 recall the stored or the built-in TV,
  Zero Gravity and Anti Snore by the indicator. Types 6 and 8 replace slot 5
  with the special Flat Bed and have no slot-5 clear.
- Circulation buttons on types 1-5 (type 3 has its own whole-body frame).
- Massage steps and wave on every layout; selecting the active timer again
  cancels it, and a cancel button is provided. Step counters clamp at 0-3 (wave
  0-4) but every tap writes.
- Light-duration buttons only: there is no proven off, brightness or colour
  command.
- **Refresh memory indicators** repeats the memory queries.

<!-- generated:ff-frame-bedsense -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Row | Action | Bytes (hex) | Types |
|---|---|---|---|
| C001 | back up | `FF FF FF FF 05 00 00 00 03 97 01` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C002 | back down | `FF FF FF FF 05 00 00 00 04 D6 C3` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C003 | head up | `FF FF FF FF 05 00 00 00 01 16 C0` | 2, 3, 4, 5 |
| C004 | head down | `FF FF FF FF 05 00 00 00 02 56 C1` | 2, 3, 4, 5 |
| C005 | lift up | `FF FF FF FF 05 00 00 00 01 16 C0` | 9 |
| C006 | lift down | `FF FF FF FF 05 00 00 00 02 56 C1` | 9 |
| C007 | waist up (TYPE 3 pressed label HIP) | `FF FF FF FF 05 00 00 00 0D 16 C5` | 1, 2, 3 |
| C008 | waist down (TYPE 3 pressed label HIP) | `FF FF FF FF 05 00 00 00 0E 56 C4` | 1, 2, 3 |
| C009 | hip up | `FF FF FF FF 05 00 00 00 0D 16 C5` | 4, 5, 9 |
| C010 | hip down | `FF FF FF FF 05 00 00 00 0E 56 C4` | 4, 5, 9 |
| C011 | leg up | `FF FF FF FF 05 00 00 00 06 57 02` | 1, 2, 3, 4, 5, 7, 9 |
| C012 | leg down | `FF FF FF FF 05 00 00 00 07 96 C2` | 1, 2, 3, 4, 5, 7, 9 |
| C013 | rise and fall up | `FF FF FF FF 05 00 00 00 06 57 02` | 8 |
| C014 | rise and fall down | `FF FF FF FF 05 00 00 00 07 96 C2` | 8 |
| C015 | back and leg up | `FF FF FF FF 05 00 00 00 2B 97 1F` | 1 |
| C016 | back and leg down | `FF FF FF FF 05 00 00 00 2C D6 DD` | 1 |
| C017 | Release / quick-background or light-background tap | `FF FF FF FF 05 00 00 00 00 D7 00` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C018 | Movement or massage background tap (physical meaning unverified) | `FF FF FF FF 05 00 00 00 00 D8 14` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C019 | whole body circulation | `FF FF FF FF 05 00 05 00 E4 C7 4A` | 1, 2, 4, 5 |
| C020 | whole body circulation default | `FF FF FF FF 05 00 00 00 E7 97 4A` | 3 |
| C021 | back and leg circulation | `FF FF FF FF 05 00 05 00 E8 C7 4F` | 1 |
| C022 | head circulation | `FF FF FF FF 05 00 05 00 E3 86 88` | 2, 3, 4, 5 |
| C023 | waist circulation | `FF FF FF FF 05 00 05 00 E6 46 8B` | 1, 2, 3 |
| C024 | hip circulation | `FF FF FF FF 05 00 05 00 E6 46 8B` | 4, 5 |
| C025 | leg circulation | `FF FF FF FF 05 00 05 00 E5 06 8A` | 1, 2, 3, 4, 5 |
| C026 | Flat Bed / recovery | `FF FF FF FF 05 00 00 00 08 D6 C6` | 1, 2, 3, 4, 5, 7, 9 |
| C027 | Lumbar shortcut | `FF FF FF FF 05 00 00 00 2E 57 1C` | 6, 8 |
| C028 | Music shortcut | `FF FF FF FF 05 00 00 00 28 D7 1E` | 4, 5 |
| C029 | Leg Relax shortcut | `FF FF FF FF 05 00 00 00 29 16 DE` | 4, 5 |
| C030 | RISE click | `FF FF FF FF 05 00 00 00 01 16 C0` | 9 |
| C031 | DECLINE click | `FF FF FF FF 05 00 00 00 02 56 C1` | 9 |
| C032 | M1 save | `FF FF FF FF 05 00 00 A0 0A 2F 07` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C033 | M1 clear | `FF FF FF FF 05 00 00 AF 0A 2A F7` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C034 | M1 recall | `FF FF FF FF 05 00 00 A1 0A 2E 97` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C035 | M2 save | `FF FF FF FF 05 00 00 B0 0B E3 07` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C036 | M2 clear | `FF FF FF FF 05 00 00 BF 0B E6 F7` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C037 | M2 recall | `FF FF FF FF 05 00 00 B1 0B E2 97` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C038 | TV save | `FF FF FF FF 05 00 00 50 05 2B 03` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C039 | TV clear | `FF FF FF FF 05 00 00 5F 05 2E F3` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C040 | TV recall | `FF FF FF FF 05 00 00 51 05 2A 93` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C041 | TV built-in recall | `FF FF FF FF 05 00 00 00 05 17 03` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C042 | Zero Gravity save | `FF FF FF FF 05 00 00 90 09 7B 06` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C043 | Zero Gravity clear | `FF FF FF FF 05 00 00 9F 09 7E F6` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C044 | Zero Gravity recall | `FF FF FF FF 05 00 00 91 09 7A 96` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C045 | Zero Gravity built-in recall | `FF FF FF FF 05 00 00 00 09 17 06` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C046 | Anti Snore save | `FF FF FF FF 05 00 00 F0 0F D3 04` | 1, 2, 3, 4, 5, 7, 9 |
| C047 | Anti Snore clear | `FF FF FF FF 05 00 00 FF 0F D6 F4` | 1, 2, 3, 4, 5, 7, 9 |
| C048 | Anti Snore recall | `FF FF FF FF 05 00 00 F1 0F D2 94` | 1, 2, 3, 4, 5, 7, 9 |
| C049 | Anti Snore built-in recall | `FF FF FF FF 05 00 00 00 0F 97 04` | 1, 2, 3, 4, 5, 7, 9 |
| C050 | Special Flat Bed save (slot 5) | `FF FF FF FF 05 00 00 F0 0F D3 04` | 6, 8 |
| C051 | Special Flat Bed recall (slot 5) | `FF FF FF FF 05 00 00 F1 0F D2 94` | 6, 8 |
| C052 | Head massage increase | `FF FF FF FF 05 00 00 00 10 D6 CC` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C053 | Head massage decrease | `FF FF FF FF 05 00 00 00 11 17 0C` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C054 | Foot massage increase | `FF FF FF FF 05 00 00 00 12 57 0D` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C055 | Foot massage decrease | `FF FF FF FF 05 00 00 00 13 96 CD` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C056 | Wave/frequency increase | `FF FF FF FF 05 00 00 00 14 D7 0F` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C057 | Wave/frequency decrease | `FF FF FF FF 05 00 00 00 15 16 CF` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C058 | Massage 10-minute selection | `FF FF FF FF 05 00 00 00 16 56 CE` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C059 | Massage 20-minute selection | `FF FF FF FF 05 00 00 00 17 97 0E` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C060 | Massage 30-minute selection | `FF FF FF FF 05 00 00 00 18 D7 0A` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C061 | Cancel selected massage timer | `FF FF FF FF 05 00 00 00 1C D6 C9` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C062 | Light duration 10 min | `FF FF FF FF 05 00 00 00 19 16 CA` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C063 | Light duration 8 h | `FF FF FF FF 05 00 00 00 1A 56 CB` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C064 | Light duration 10 h | `FF FF FF FF 05 00 00 00 1B 97 0B` | 1, 2, 3, 4, 5, 6, 7, 8, 9 |
| C065 | Qdefault query 1 TV/M3 | `FF FF FF FF 03 00 16 00 09 7E C2` | 1, 2, 3, 4, 5, 9 |
| C066 | Qdefault query 2 Zero Gravity/M4 | `FF FF FF FF 03 00 1F 00 09 AE C0` | 1, 2, 3, 4, 5, 9 |
| C067 | Qdefault query 3 M1 | `FF FF FF FF 03 00 28 00 09 1F 0E` | 1, 2, 3, 4, 5, 9 |
| C068 | Qdefault query 4 M2 | `FF FF FF FF 03 00 31 00 09 CE C9` | 1, 2, 3, 4, 5, 9 |
| C069 | Qdefault query 5 Anti Snore/M5 | `FF FF FF FF 03 00 3A 00 09 BF 0B` | 1, 2, 3, 4, 5, 9 |
| C070 | Q68 query 1 TV/M3 | `FF FF FF FF 03 00 14 00 03 5F 05` | 6, 8 |
| C071 | Q68 query 2 Zero Gravity/M4 | `FF FF FF FF 03 00 1C 00 03 DE C7` | 6, 8 |
| C072 | Q68 query 3 M1 | `FF FF FF FF 03 00 24 00 03 5F 0A` | 6, 8 |
| C073 | Q68 query 4 M2 | `FF FF FF FF 03 00 2C 00 03 DE C8` | 6, 8 |
| C074 | Q68 query 5 Anti Snore/M5 | `FF FF FF FF 03 00 3A 00 09 BF 0B` | 6, 8 |
| C075 | Q7 query 1 TV/M3 | `FF FF FF FF 03 00 18 00 03 9F 06` | 7 |
| C076 | Q7 query 2 Zero Gravity/M4 | `FF FF FF FF 03 00 20 00 03 1E CB` | 7 |
| C077 | Q7 query 3 M1 | `FF FF FF FF 03 00 28 00 03 9F 09` | 7 |
| C078 | Q7 query 4 M2 | `FF FF FF FF 03 00 30 00 03 1F 0E` | 7 |
| C079 | Q7 query 5 Anti Snore/M5 | `FF FF FF FF 03 00 38 00 03 9E CC` | 7 |
<!-- /generated -->

#### Timing

See [Timing](#timing). Memory queries go in slot order 3, 4, 1, 2, 5
([Queries](#queries)).

#### Notifications

- Successful local writes and notifications both feed the app's ordered
  memory-indicator rules, as the app's write callbacks do. `bedsense_state_source`
  names the last source; failed writes do not.
- Memory indicators, massage bars, step counters, circulation and the selected
  durations are entities. They are app indicators, not measured positions.
  The app maps foot massage patterns to the head display bar; HA keeps that.
- Saved-memory flags persist per bed across restarts; the other indicators live
  in a per-address session.

#### Evidence

BedSense sends exactly its frozen command table, including the C018 anomaly. The
[row108 ledger](../apk-analysis/dispositions/row108-bedsense.md) holds the
dispositions. Useful captures after release: GATT roles and properties, memory
replies, lift hold versus click, background taps, massage and light durations.

### Motion Bed

**App:** [Motion Bed](https://play.google.com/store/apps/details?id=com.sn.blackdianqi) 1.24 (34), `com.sn.blackdianqi`

**Status:** ❓ Needs testing (APK-verified, hardware unverified)

#### Setup

Detection: none by itself. Select **Motion Bed app** and enter the original
Bluetooth name the app used, preserving case.

- Shared FFE1 or FFE0 transport never selects this app. Hardware-confirmed Solace
  names keep Solace preselected with Motion Bed as an alternative; other accepted
  names, including TL-Q, QMS-430 and S5-Y, offer Motion Bed in the app chooser.
- The controller binds to the **last** FFE1 characteristic object and its client;
  duplicate UUIDs cannot redirect an operation. It prefers the write property,
  otherwise write-without-response.
- Rules are checked in order against the saved title; the first match wins:

| Saved title contains | Surface | Preset layout | Movement layout |
|---|---|---|---|
| `TL-Q` / `TL-A` / `TL-B` / `TL-W` (in that order) | Hub / air / motor / thermal | modular | modular |
| `QMS-IQ`, `QMS-LQ`, `QMS-I06`-`QMS-I96`, `QMS-L04`-`QMS-L94` (or an empty restored title) | Home | K1 | W1 |
| `QMS-JQ-D`, `QMS4`, `S4-N` | Home | K2M | W2 |
| `QMS-NQ`, `QMS3` | Home | K2M (K2 for `QMS3-N93-327`) | W3 |
| `QMS-MQ`, `QMS2`, `SealyMF` | Home | K2M | W4 |
| `QMS-KQ-H`, `QMS-H02` | Home | K3 | W6 |
| `QMS-DFQ`, `QMS-430`, `QMS-444` | Home | K4 | W7 |
| `QMS-DQ`, `QMS-443` | Home | K5 | W8 |
| `S3-2` | Home | K2M | W10 |
| `S3-3` | Home | K8 | W11 |
| `S3-4` | Home | K9 | W11 |
| `S4-Y` | Home | K11 | W12 |
| `S5-Y` | Home | K11 | W13 |
| `S6-Y` | Home | K11 | W14 |
| `S4-4` | Home | K2M | W18 |
| Any other accepted marker | Home | K2M | W2 |

- Auto layout follows the app's saved-title character replacement (`<` → `C`,
  `:` → `A`, `;` → `B`, `=` → `D`, `>` → `E`, `?` → `F`).
- Retained preset and movement overrides apply only to the same physical target
  and cannot cross between ordinary beds and modular products. An empty or
  unknown restored title needs the explicit app-restored option.
- Each side of a paired bed keeps its own profile. Unpair before changing fields
  that differ between two addresses; a two-address pair cannot be converted into
  Motion Bed in shared options.
- **Modular hub**: TL-Q reports motor, air and thermal modules on the same
  address. The Active hub module select chooses which surface owns startup and
  thermal polling; all reported module controls stay available. Hub STOP uses the
  active module's STOP, air stop or thermal off, and rejects STOP when the module
  is unknown. Button identities survive temporarily unknown inventory; a
  process-local snapshot keeps validated controls for the same address and
  profile across reconnects.

##### Home Assistant setup

Select the explicit **Motion Bed app** route and the original case-sensitive Bluetooth name. Auto chooses the app’s ordered layout; retained overrides belong to the same physical target. FFE1 alone does not identify this app. Two-address pairs preserve each side’s settings and require unpairing before profile changes.

#### Controls

- Movement covers use only the selected layout's control pairs and app labels.
  Selectors per layout (up/down; the frames are in the table at the end of this
  section):

| Layout | Controls (app label, up/down selector) |
|--------|-----------------------------------------|
| W1 | BACK `03`/`04`, HIP `0D`/`0E`, HEAD `01`/`02`, LEG `06`/`07` |
| W2 | BACK `03`/`04`, LUMBAR `0D`/`0E`, HEAD `01`/`02`, LEG `06`/`07` |
| W3 | BACK `03`/`04`, BACK LEG `2B`/`2C`, LUMBAR `0D`/`0E`, LEG `06`/`07` |
| W4 | BACK `03`/`04`, LEG `06`/`07` |
| W6 | BACK `03`/`04`, LIFT `06`/`07` |
| W7 | Split: Left BACK `03`/`04`, Right BACK `0D`/`0E`, Split Legs Left `01`/`02`, Split Legs Right `06`/`07`; coupled: BACK `35`/`36`, LEG `37`/`38` |
| W8 | Split: Left BACK `03`/`04`, Right BACK `0D`/`0E`, LEG `06`/`07`; coupled: BACK `35`/`36`, LEG `06`/`07` |
| W10 | BACK `03`/`04`, HEAD `01`/`02`, LEG `06`/`07` |
| W11 | BACK `03`/`04`, LIFT `0D`/`0E`, LEG `06`/`07` |
| W12 | BACK `03`/`04`, LEG `06`/`07`, LIFT `21`/`22`, TILT `28`/`29` |
| W13, W14 | BACK `03`/`04`, LUMBAR `0D`/`0E`, HEAD `01`/`02`, LEG `06`/`07`, LIFT `21`/`22`, TILT `28`/`29` |
| W18 | BACK `03`/`04`, LUMBAR `0D`/`0E`, LIFT `01`/`02`, LEG `06`/`07` |
| Modular motor | **Back down** `04`, **Leg down** `07` only |

- Named presets, massage, lighting, sync, audio and sleep controls are buttons or
  validated actions; diagnostics list the available action keys. Entity
  identities follow the control's function, so a layout change keeps a shared
  control's name and settings. Screens that send identical frames share one
  button.
- Preset-selected flags describe app state, not a measured position. Recall and
  programming keep the app's state-dependent branches; persistent programming
  needs confirmation. K3's Flat sends the app's anti-snore custom recall, so it
  is not offered as a guaranteed flat.
- Audio availability follows the target's reported flag, remembered per target
  and profile; the exact `QMS3-N93-327` title overrides positive home audio
  feedback.
- State sensors: raw positions A-D (unknown units, no sliders), alarm fields,
  programmed presets, module presence, pressure (air lower pressure is readback
  only), sleep and calibration values, thermal state and passive bed faults.
  Thermal gears are cooling 4-1, off and heating 1-4, not setpoints.

<!-- generated:ff-frame-motion-bed -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

**Movement selectors**

| Selector (up / down) | Up | Down |
|---|---|---|
| `01` / `02` | `FF FF FF FF 05 00 00 00 01 16 C0` | `FF FF FF FF 05 00 00 00 02 56 C1` |
| `03` / `04` | `FF FF FF FF 05 00 00 00 03 97 01` | `FF FF FF FF 05 00 00 00 04 D6 C3` |
| `06` / `07` | `FF FF FF FF 05 00 00 00 06 57 02` | `FF FF FF FF 05 00 00 00 07 96 C2` |
| `0D` / `0E` | `FF FF FF FF 05 00 00 00 0D 16 C5` | `FF FF FF FF 05 00 00 00 0E 56 C4` |
| `21` / `22` | `FF FF FF FF 05 00 00 00 21 17 18` | `FF FF FF FF 05 00 00 00 22 57 19` |
| `28` / `29` | `FF FF FF FF 05 00 00 00 28 D7 1E` | `FF FF FF FF 05 00 00 00 29 16 DE` |
| `35` / `36` | `FF FF FF FF 05 00 00 00 35 17 17` | `FF FF FF FF 05 00 00 00 36 57 16` |
| `37` / `38` | `FF FF FF FF 05 00 00 00 37 96 D6` | `FF FF FF FF 05 00 00 00 38 D6 D2` |
| BACK LEG `2B` / `2C` | `FF FF FF FF 05 00 05 00 2B 87 1E` | `FF FF FF FF 05 00 05 00 2C C6 DC` |

**Sleep adjustment** (`arg` 02)

| Control | Up | Down |
|---|---|---|
| Head | `FF FF FF FF 05 00 00 02 03 96 61` | `FF FF FF FF 05 00 00 02 04 D7 A3` |
| Back | `FF FF FF FF 05 00 00 02 01 17 A0` | `FF FF FF FF 05 00 00 02 02 57 A1` |
| Legs | `FF FF FF FF 05 00 00 02 06 56 62` | `FF FF FF FF 05 00 00 02 07 97 A2` |
| Lumbar | `FF FF FF FF 05 00 00 02 0D 17 A5` | `FF FF FF FF 05 00 00 02 0E 57 A4` |

**Startup, status and stop frames**

| Frame | App callsite | Bytes (hex) |
|---|---|---|
| Home startup and sleep configuration | `HomeActivity:321` | `FF FF FF FF 02 00 0E 0B 00 17 04` |
| Bed status | `HomeActivity:311` | `FF FF FF FF 01 00 0A 0B 0F 21 04` |
| Hub module status | `MainMcuActivity:182` | `FF FF FF FF 01 00 26 14 0F 00 00 00 00 00 00 00 00 00 46 04` |
| Motor module startup | `DiandongFragment:319` | `FF FF FF FF 01 00 2A 14 00 00 00 00 00 00 00 00 00 00 3B 04` |
| Air module startup | `QinangFragment:133` | `FF FF FF FF FF 14 02 09 00 00 00 00 00 00 00 00 00 00 A6 40` |
| Thermal module startup and status | `LengnuanFragment:183` | `FF FF FF FF FE 10 00 00 00 00 00 00 00 AA 4D 8B` |
| Thermal status (timer on) | `LengnuanFragment:58` | `FF FF FF FF FE 10 00 01 00 00 00 00 00 AA 5D 4B` |
| Audio status | `KuaijieK2MFragment:466` | `FF FF FF FF 01 00 15 0B 00 1D 04` |
| Brightness status | `HomeActivity:455` | `FF FF FF FF 05 00 05 FF 23 C7 28` |
| Raw positions | `SleepAdjustActivity:255` | `FF FF FF FF 02 00 0F 0B 00 18 04` |
| Calibration, sleep configuration and exit status | `HomeActivity:463` | `FF FF FF FF 02 00 0A 0A 12 04` |
| Calibration debug sample | `SleepDataEntryActivity:293` | `FF FF FF FF 02 00 09 0F 03 00 00 00 00 19 04` |
| Capture flat calibration | `SleepDataEntryActivity:248` | `FF FF FF FF 02 00 09 0D 01 00 00 15 04` |
| Capture side calibration | `SleepDataEntryActivity:253` | `FF FF FF FF 02 00 09 0D 02 00 00 16 04` |
| Air status | `AnmoSetActivity:260` | `FF FF FF FF FF 0D 02 08 00 03 00 7F B2` |
| Pressure status | `PressSetActivity:224` | `FF FF FF FF FF 0B 02 04 00 AE 30` |
| Air stop | `QinangFragment:302` | `FF FF FF FF FF 0B 01 00 00 5C F0` |
<!-- /generated -->

#### Timing

| Operation | Timing |
|-----------|--------|
| Home startup | 500 ms, home startup frame; 500 ms, clock; 500 ms, bed status; 700 ms, the preset layout's status queries 500 ms apart |
| Hub startup | 300 ms, hub module status |
| Motor, air, thermal module startup | 200 ms, the module's startup frame; motor and thermal then send their clock after another 200 ms |
| Movement hold | Default 1 s, maximum 10 s, then STOP |
| Sleep adjustment | Positions every 500 ms while held, then STOP and a query after 100 ms |
| Calibration debug | Polls every 2 s, at most ten samples |
| Thermal status | First poll after 2 s, then every 5 s while the thermal surface is active |
| Pressure live edit | Waits 2.5 s |

Frames are in the table under Controls. Thermal polling holds the
connection across its waits and stops when the module changes, polling is
cancelled or the session drops.

#### Notifications

- Replies are parsed per active receiver. Malformed or short notifications leave
  state unchanged and record a diagnostic rejection; a complete shorter reply is
  kept while a longer receiver is active.
- Sleep day and window state separates decoded windows from the app's faulty
  historical-window assignment; a new report clears prior aggregation.
- Replies carry no request identifier, so a report's route flags belong to the
  current request.

#### Services

All actions accept `device_id` and optional `side`. Every target is validated
before any write; persistent changes need `confirmed: true`.

| Action | Main fields |
|---|---|
| `motion_bed_action` | `action` from diagnostics; `branch` app/save/clear; movement `duration` in seconds |
| `motion_bed_alarm` | `enabled`, `hour`, `minute`, weekdays 1-7, `repeat`, modes 1-6, `massage`, `sound`, the target's `audio`; modular initial `switch` 00/01/A1 |
| `motion_bed_clock` | ISO `timestamp`, `thermal` for the thermal clock |
| `motion_bed_sleep_angles` | page 2/3/4, four `flat` and four `side_positions` raw values |
| `motion_bed_calibration` | integer `flat`, `side_position`; odd-width encodings are rejected before I/O |
| `motion_bed_sleep_timer` | bedtime slot 0-8 or `fall: true` slot 0-4 |
| `motion_bed_sleep_report` | month/real/timer/day, historical day `offset` 0-29, graph `window_offset` 0-4 |
| `motion_bed_module` | query/bind/delete, module type 10/11/12 (motor/air/thermal), module MAC for bind |
| `motion_bed_air_setting` | mode 3/18/4/5/12, `query`, gear 1-8, optional timer 0/1/2 |
| `motion_bed_pressure` | live channel 0-11 and value 0-9, or save twelve `values` |
| `motion_bed_thermal_schedule` | `hour`, `minute`, mode 1 heat/2 cool, gear 1-4 |
| `motion_bed_audio` | track/volume, `value` 1-5, optional track `preview`; needs reported audio support |

| Field | Values |
|---|---|
| Alarm mode | 1 zero gravity, 2 memory 1, 3 no action, 4 left zero gravity, 5 right zero gravity, 6 coupled zero gravity |
| Alarm sound | 0 none, 1 buzzer, `0x11`-`0x15` music 1-5 |
| Modular alarm `switch` | `00` uninitialized (unavailable once alarm state arrives), `01` enabled, `A1` disabled |
| Air mode | 3 full, 18 back, 4 neck, 5 waist, 12 yoga |
| Air timer | 0 = 10 minutes, 1 = 20 minutes, 2 = 30 minutes |

- `repeat: true` with an empty weekday list keeps a present but empty weekday
  map, as the app can.
- Pressure live edits bind their channel explicitly; whole pressure save is one
  47-byte frame.

#### Evidence

Motion Bed sends only its frozen frames. The
[unit 032 dispositions](../apk-analysis/dispositions/032-motion-bed.md) hold the
dispositions, including the excluded Wi-Fi provisioning and cloud controls.

## Notes

### Analysis provenance

| Profile | Report | Ledger |
|---------|--------|--------|
| Solace MotionFlex, HomeKobo, Sweet Night | Accepted APK Protocol Audit reports, cluster 008 | [MotionFlex](solace-disposition.md) |
| Woosa Sleep | `com.sn.woosa` 1.1.9 (13), artifact-set SHA-256 `21778ac636d9fed83d7809d0dd47521deb2b2e25d24867bf3e2458740c47b217`, accepted `REPORT.SHA256` digest `995677ce2204b2f8255b5a47f9b7c597928255d636e2f50ba1aff3cdfcf70851` ([issue #606](https://github.com/kristofferR/ha-adjustable-bed/issues/606)) | [Woosa Sleep](woosa-disposition.md) |
| BedSense | `com.fenmenbielei.bedsense` 1.8 (18), row108 | [row108](../apk-analysis/dispositions/row108-bedsense.md) |
| Motion Bed | `com.sn.blackdianqi` 1.24 (34), XAPK SHA-256 `76449cb37440907b6933c5dfb36a1a5ec5b737756f44db5a9629a654f9f3e6a3` | [unit 032](../apk-analysis/dispositions/032-motion-bed.md) |

Raw APKs, decompilation and reports stay machine-local.
