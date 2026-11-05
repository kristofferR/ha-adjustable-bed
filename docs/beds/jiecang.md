# Jiecang

**Status:** ❓ Needs testing (the app profiles are APK-verified with hardware unverified; the legacy route is unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

One wire codec (`F1 F1 ... 7E` frames over three GATT transports) serves a legacy
route, four audited Jiecang app profiles and three audited LOGICDATA app profiles.
This guide covers the codec first, then one section per profile. See
[Protocol codecs and app profiles](../design/protocol-codecs.md) for the architecture.

The accepted MOTIONrelax phone and tablet apps and the bed side of the Sleep Smart
Air Mattress app use the `logicdata_app` bed type
([LOGICDATA app family](#logicdata-app-family)). Existing working Jiecang
configurations keep the legacy route.

## Known Models

Brands using Jiecang actuators:

- Comfort Motion
- Dream Motion / Dreamotion Smart
- Dream Motion HD tablet app beds
- ERGOBALANCE beds (app package name: Dreamask)
- Glide adjustable beds
- LOGICDATA MOTIONrelax beds, standard (P1) and middle-motor (P2) families
- LOGICDATA Vienna and Toronto (two-motor beds, P1) and Middle Rail (P2), also with
  the Sleep Smart Air Mattress app
- Jiecang-branded controllers

The Comfort Motion app has no model, Bluetooth name, manufacturer or RSSI filter.
The ERGOBALANCE, Dream Motion and Dream Motion HD apps share Bluetooth services,
so a service UUID cannot say which app's layout or release behavior applies
(see [Choosing a profile](#choosing-a-profile)).

## Apps

| Analyzed | App | Package ID | Profile |
|----------|-----|------------|---------|
| ✅ | [Jiecang Bed / Comfort Motion](https://play.google.com/store/apps/details?id=com.jiecang.app.android.jiecangbed) 2.2.1 (28) | `com.jiecang.app.android.jiecangbed` | [Comfort Motion](#comfort-motion-app); the legacy route covers the same beds |
| ✅ | LOGICDATA MOTIONrelax | `com.logicdata.motionrelax` | [Legacy route](#legacy-route); app profiles in the [LOGICDATA app family](#logicdata-app-family) |
| ✅ | [MOTIONrelax phone](https://play.google.com/store/apps/details?id=com.logicdata.app.android.bed) 1.0.6 (7) | `com.logicdata.app.android.bed` | [MOTIONrelax phone and tablet](#motionrelax-phone-and-tablet) |
| ✅ | [MOTIONrelax tablet](https://play.google.com/store/apps/details?id=com.logicdata.app.android.pad.bed) 1.0.4 (5) | `com.logicdata.app.android.pad.bed` | [MOTIONrelax phone and tablet](#motionrelax-phone-and-tablet) |
| ✅ | [Sleep Smart Air Mattress](https://play.google.com/store/apps/details?id=com.logicdata.app.mattress.bed) 1.0.0 (1) | `com.logicdata.app.mattress.bed` | [Sleep Smart Air Mattress (bed)](#sleep-smart-air-mattress-bed); the pump is a [separate bed type](logicdata-sleep-smart.md) |
| ✅ | [ERGOBALANCE](https://play.google.com/store/apps/details?id=com.jiecang.dreamask.app.android.bed) 1.0.8 (8) | `com.jiecang.dreamask.app.android.bed` | [ERGOBALANCE (Dreamask)](#ergobalance-dreamask) |
| ✅ | [Dream Motion](https://play.google.com/store/apps/details?id=com.jiecang.dreamotion.app.android.bed) 1.0.5 (11) | `com.jiecang.dreamotion.app.android.bed` | [Dream Motion (Dreamotion)](#dream-motion-dreamotion) |
| ✅ | [Dream Motion HD](https://play.google.com/store/apps/details?id=com.dreamhd.jiecang.android.pad.bed) 1.0.4 (4) | `com.dreamhd.jiecang.android.pad.bed` | [Dream Motion HD](#dream-motion-hd) |

## Features

| Feature | Legacy route | Comfort Motion | ERGOBALANCE / Dream Motion | Dream Motion HD |
|---------|--------------|----------------|----------------------------|-----------------|
| Motor Control | ✅ (back and legs) | ✅ (movement and release; 2/3/4-motor layouts; the two-motor layout also exposes combined back/legs) | ✅ (determined by the selected layout) | ✅ (determined by the selected layout) |
| Hold Until Release | ❌ (finite pulses) | ❌ (finite pulses; report PARTIAL) | ✅ ([renewable hold](../SERVICES.md#renewable-holds)) | ✅ (renewable hold) |
| Position Feedback | ❌ | ❌ (no motor angle, percentage or movement completion) | ❌ (actuator-status packets are not motor position feedback; no position sliders or angle sensors) | ❌ (same) |
| Presets | ✅ Flat, Zero-G, Anti-Snore | ✅ Flat, Zero-G, Anti-Snore | ✅ Flat, Zero-G, Anti-Snore; Yoga when the bed reports it | ✅ same |
| Memory Presets | ✅ (3 slots, recall and program) | ✅ (two recalls, two saves) | ✅ (2 slots, separate recall and save) | ✅ (2 slots, different payload) |
| Massage | ✅ (back/leg, 0-10 levels) | ✅ (independent back and foot levels 0-3, mode cycling, stop; no massage mode number) | ✅ (Off and levels 1-3 per layout zone, mode, stop) | ✅ (same) |
| Lights | ✅ (toggle) | ✅ (toggle, with reported light state) | ✅ (toggle; RGB, brightness, timeout and automatic under-bed lighting when reported) | ✅ (same, with its own capability gates) |
| Alarm | ❌ | ❌ (no BLE alarm programming) | ✅ (`adjustable_bed.jiecang_set_alarm`) | ✅ |
| Wake Routine | ❌ | ✅ (`adjustable_bed.jiecang_wake`) | ✅ (`adjustable_bed.jiecang_wake`) | ✅ |
| Clock | ❌ | ❌ (no clock-setting command) | ✅ (answered on the bed's clock request) | ✅ |
| Bluetooth Rename | ❌ | ✅ (G1 only) | ✅ (G1 or G3) | ✅ (G1 or G3) |

The LOGICDATA app profiles:

| Feature | MOTIONrelax phone / tablet | Sleep Smart (bed) |
|---------|----------------------------|-------------------|
| Motor Control | ✅ (per layout) | ✅ Back, legs, both |
| Hold Until Release | ✅ ([renewable hold](../SERVICES.md#renewable-holds)) | ✅ (renewable hold) |
| Position Feedback | ❌ (neither app reports motor positions) | ❌ |
| Presets | ✅ P1: Flat, Zero-G, Anti-Snore. P2: Flat | ✅ Flat, Zero Gravity, Anti-Snore (hold-only) |
| Memory Presets | ✅ (2 slots, recall and save, both families) | ✅ (1 slot) |
| Held Presets | ✅ P2: `adjustable_bed.logicdata_hold_preset` | ✅ Every preset and memory 1 |
| Massage | ✅ P1 only: Off and levels 1–3 per zone, mode, stop | ✅ (Off and levels 1–3 per zone, stop, mode, **Massage mode** sensor) |
| Lights | ✅ (toggle with notification readback; no brightness or RGB) | ✅ (under-bed toggle) |
| Clock | ✅ Phone app (both families); ❌ tablet | ✅ (answers clock requests) |
| Alarm | ✅ Phone app with P1; ❌ tablet | ❌ |
| Factory Reset | ❌ | ⚠️ (disabled by default) |
| Bluetooth Rename | ✅ (T1 or T3) | ✅ (T1 or T3 name role) |

Enable massage and light controls only when fitted.

## Choosing a profile

Detection suggests the legacy route (see its [Setup](#legacy-route)); the app
profiles are explicit choices.

### Home Assistant setup

The bed-type list has one **Jiecang: ERGOBALANCE, Dream Motion, Dream Motion HD
and Comfort Motion apps, Glide and Lierda remotes** choice. Setup then asks which
app or remote you use; the bed's name and services never decide it.

1. Choose the app on your phone: **ERGOBALANCE app (Dreamask)**, **Dream Motion
   app**, **Dream Motion HD app** or **Comfort Motion app**. Then choose the layout
   the app shows and whether the bed has a light. The transport stays **Auto**
   unless you open **Advanced**.
2. Without an app, choose the remote's legacy controls: **No app: Glide or Comfort
   Motion remote** (`jiecang`) or **No app: Comfort Motion / Lierda remote**
   (`comfort_motion`), then the motor count. See the [legacy route](#legacy-route).
3. When detection found a legacy bed, **I don't know: keep the current controls**
   saves the detected legacy route.

For an existing bed, open the entry's three-dot menu and **Reconfigure** (see
[Changing the app or layout](../CONFIGURATION.md#changing-the-app-or-layout-of-an-existing-bed)).
The same question appears, with **Keep** leaving the entry as it is. Choosing an
app checks the bed's Bluetooth services with the app's own transport selection
before anything is saved; a bed without that app's services keeps its setup.
Choosing a legacy route needs no check. A review lists the added and removed
controls before **Apply this change** saves it, with the same entry, address,
device and unchanged entity IDs.

Existing legacy Jiecang and Comfort Motion entries keep their original behavior
until you change them. **Configure** keeps routine settings, such as the light,
massage and connection options; the app, layout, transport and legacy-or-app
route change only through **Reconfigure**. Settings belong to one physical bed and
remain independent across a two-address pair.

LOGICDATA beds use their own bed type, `logicdata_app`; detection never selects it
(see the [LOGICDATA app family](#logicdata-app-family), which has its own
generated tables).

The tables below come from the profile data.

<!-- generated:jiecang-profiles -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

### Profile summary

| Profile | Bed type | Transports | Memory | Massage levels | Name rule | Startup |
|---|---|---|---|---|---|---|
| Legacy route | `comfort_motion`, `jiecang` | G3, G1 | 3 slots, payload `01` | 0-10 (wire equals level) | none | none |
| Comfort Motion | `jiecang_app` | G1, G2 | 2 slots, payload `01` | 0-3 (wire 00 02 03 04) | `[._0-9A-Za-z]{1,18}` | 6 queries, last at +700 ms |
| ERGOBALANCE (Dreamask) | `jiecang_app` | G3, G1, G2 | 2 slots, payload `00 00` | 0-3 (wire 00 02 03 04) | `[0-9A-Za-z]{1,20}` | 14 queries, last at +1900 ms |
| Dream Motion | `jiecang_app` | G3, G1, G2 | 2 slots, payload `00 00` | 0-3 (wire 00 02 03 04) | `[0-9A-Za-z]{1,20}` | 14 queries, last at +1900 ms |
| Dream Motion HD | `jiecang_app` | G3, G1, G2 | 2 slots, payload `01` | 0-3 (wire 00 02 03 04) | `[ -~]{1,20}` | 12 queries, last at +1900 ms |

### Hold and release timing

Release offsets count from the last hold frame.

| Profile | Hold refresh | Repeats | Hold until release | Final frame | Release after hold | Explicit stop |
|---|---|---|---|---|---|---|
| Legacy route | 50 ms (after each write) | 25 | no | no | +0 ms short release | +0 ms short release |
| Comfort Motion | 100 ms (after each write) | motor pulse count | no | no | +100 ms short release | +0 ms short release |
| ERGOBALANCE (Dreamask) | 100 ms (fixed rate) | motor pulse count | renewable lease | no | +50 ms long release, +150 ms long release | +0 ms long release, +100 ms long release |
| Dream Motion | 100 ms (fixed rate) | motor pulse count | renewable lease | yes | +100 ms short release, +800 ms long release | +0 ms short release, +700 ms long release |
| Dream Motion HD | 100 ms (fixed rate) | motor pulse count | renewable lease | yes | +100 ms short release | +0 ms short release |

### One-shot timing

| Profile | Presets and memory recall | Memory save |
|---|---|---|
| Legacy route | 3 × 100 ms, no release | once, no release |
| Comfort Motion | once, short release after 100 ms | once, no release |
| ERGOBALANCE (Dreamask) | once, long release after 800 ms | 3 × 30 ms, no release |
| Dream Motion | once, long release after 800 ms | 3 × 30 ms, no release |
| Dream Motion HD | once, short release after 100 ms | 3 × 30 ms, no release |

### Layouts and axes

| Layout | Axes | Motion payload | Bilateral presets and massage | Massage zones | Profiles |
|---|---|---|---|---|---|
| `standard_2` (Back and legs (2 motors)) | back, both, legs | `01` | no | back, legs | Comfort Motion |
| `standard_2` (Back and legs (2 motors)) | back, legs, both | `01` | no | back, legs | ERGOBALANCE (Dreamask), Dream Motion, Dream Motion HD |
| `standard_3_neck` (Back, legs and neck) | head, back, legs | `01` | no | back, legs | Comfort Motion |
| `standard_3_neck` (Back, legs and neck) | back, legs, head | `01` | no | back, legs | ERGOBALANCE (Dreamask), Dream Motion, Dream Motion HD |
| `standard_3_lumbar` (Back, legs and lumbar) | back, legs, lumbar | `01` | no | back, legs | ERGOBALANCE (Dreamask), Dream Motion, Dream Motion HD |
| `standard_3_hi_low` (Back, legs and height) | back, legs, bed_height | `01` | no | back, legs | ERGOBALANCE (Dreamask), Dream Motion, Dream Motion HD |
| `standard_3_split_upper` (Split upper (3 motors)) | back, legs, right_back, both_backs | `01` | no | back, right, legs | ERGOBALANCE (Dreamask), Dream Motion, Dream Motion HD |
| `standard_4_legacy` (Back, legs, neck and lumbar (legacy)) | head, back, lumbar, legs | `01` | no | back, legs | Comfort Motion, ERGOBALANCE (Dreamask), Dream Motion, Dream Motion HD |
| `standard_4_bilateral` (Bilateral (4 motors)) | back, both_backs, right_back, legs, both_legs, right_legs | `00 00` | yes | back, right | ERGOBALANCE (Dreamask), Dream Motion |
| `split_series` (Split series) | back, legs, right_back, both_backs | `01` | no | back, right, legs | ERGOBALANCE (Dreamask), Dream Motion, Dream Motion HD |
| `split_after_bilateral` (Split after bilateral) | back, legs, right_back, both_backs | `01` | yes | back, right | ERGOBALANCE (Dreamask), Dream Motion |

Legacy route has no selectable layouts: it uses the entry's motor count.

### Startup queries

Offsets count from the start of the profile's startup sequence (see its Timing).
Each query is listed with every offset it is sent at.

**Comfort Motion**

| Offset | Query | Bytes (hex) |
|---|---|---|
| 200 ms, 300 ms | Actuator status (selector `01`) | `F1 F1 00 01 01 02 7E` |
| 400 ms, 500 ms | Hardware | `F1 F1 00 01 40 41 7E` |
| 600 ms, 700 ms | Vibration (massage) | `F1 F1 00 01 08 09 7E` |

**ERGOBALANCE (Dreamask), Dream Motion**

| Offset | Query | Bytes (hex) |
|---|---|---|
| 0 ms, 100 ms | Software | `F1 F1 00 02 40 00 42 7E` |
| 800 ms, 900 ms | Light | `F1 F1 00 02 01 00 03 7E` |
| 1000 ms, 1100 ms | Actuator status (selector `50`) | `F1 F1 00 01 50 51 7E` |
| 1200 ms, 1300 ms | Hardware | `F1 F1 00 01 40 41 7E` |
| 1400 ms, 1500 ms | Vibration (massage) | `F1 F1 00 01 08 09 7E` |
| 1600 ms, 1700 ms | Alarm | `F1 F1 00 01 10 11 7E` |
| 1800 ms, 1900 ms | Software | `F1 F1 00 02 40 00 42 7E` |

**Dream Motion HD**

| Offset | Query | Bytes (hex) |
|---|---|---|
| 0 ms, 100 ms | Initial status | `F1 F1 00 00 00 7E` |
| 1000 ms, 1100 ms | Actuator status (selector `01`) | `F1 F1 00 01 01 02 7E` |
| 1200 ms, 1300 ms | Hardware | `F1 F1 00 01 40 41 7E` |
| 1400 ms, 1500 ms | Vibration (massage) | `F1 F1 00 01 08 09 7E` |
| 1600 ms, 1700 ms | Alarm | `F1 F1 00 01 10 11 7E` |
| 1800 ms, 1900 ms | Software | `F1 F1 00 02 40 00 42 7E` |
<!-- /generated -->

### Aliases

Bed types that build the same controller over the same profile with the same
default timing, so they send identical bytes. They stay separate bed types so
existing entries keep their identities; the
[protocol inventory](../design/protocol-inventory.md) proves the equality by capture.

| Bed type | Same as | Differs only in |
|----------|---------|-----------------|
| `comfort_motion` | `jiecang` | Detection signal, setup label and profile-review suggestions; both select the [legacy route](#legacy-route) |

Those differences, plus the device manufacturer, keep separate
[profile ids](../design/profile-id.md#aliases): the profile review is a Repairs issue.

## Wire codec

Implemented once in `custom_components/adjustable_bed/codec/jiecang.py`. Profiles
(`profiles/jiecang.py`) decide which of the frames below an app sends and how it
times them. Every frame table in this section is generated from the codec.

### Transports

<!-- generated:jiecang-transports -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Selection | Service | Write | Notify | Name | Profiles |
|---|---|---|---|---|---|
| G1 (Lierda1 / Comfort Motion) | `0000ff12-0000-1000-8000-00805f9b34fb` | `0000ff01-0000-1000-8000-00805f9b34fb` | `0000ff02-0000-1000-8000-00805f9b34fb` | `0000ff06-0000-1000-8000-00805f9b34fb` | Legacy route, Comfort Motion, ERGOBALANCE (Dreamask), Dream Motion, Dream Motion HD |
| G2 | `88121427-11e2-52a2-4615-ff00dec16800` | `88121427-11e2-52a2-4615-ff00dec16801` | same as write | none | Comfort Motion, ERGOBALANCE (Dreamask), Dream Motion, Dream Motion HD |
| G3 (Lierda3 / LOGICDATA) | `0000fe60-0000-1000-8000-00805f9b34fb` | `0000fe61-0000-1000-8000-00805f9b34fb` | `0000fe62-0000-1000-8000-00805f9b34fb` | `0000fe63-0000-1000-8000-00805f9b34fb` | Legacy route, ERGOBALANCE (Dreamask), Dream Motion, Dream Motion HD |
<!-- /generated -->

The LOGICDATA profiles drive all three, which their apps call T1, T2 and T3. Each
profile chooses among its transports as described in its Setup. Writes use
a response when the write characteristic advertises `write`, otherwise
write-without-response, except where a profile states otherwise.

### Framing and checksum

**Request:** `F1 F1 | opcode | length | payload | checksum | 7E`. The checksum is
the low byte of the sum of opcode, length and payload. Variable-length packets;
common single-byte commands occupy 7 bytes.

**Payload shapes:** controllers take either `01` (standard) or `00 00`
(bilateral). Which shape a command uses is a layout and profile rule.

**Response:** the same layout behind an `F2 F2` header (see [Responses](#responses)).

### Command encoders

Values below are what `codec/jiecang.py` builds.

#### Motion

Each down opcode is the up opcode plus one. Head and bed height share an opcode.
Only the `standard_4_bilateral` layout moves motors with the `00 00` payload.
`split_after_bilateral` moves with `01` and keeps `00 00` for presets and massage;
every other layout uses `01` throughout. The
[layout table](#layouts-and-axes) lists each layout's payloads.

<!-- generated:jiecang-motion -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Axis | Up | Down | Bilateral up / down |
|---|---|---|---|
| Back | `F1 F1 01 01 01 03 7E` | `F1 F1 02 01 01 04 7E` | `F1 F1 01 02 00 00 03 7E` / `F1 F1 02 02 00 00 04 7E` |
| Legs | `F1 F1 03 01 01 05 7E` | `F1 F1 04 01 01 06 7E` | `F1 F1 03 02 00 00 05 7E` / `F1 F1 04 02 00 00 06 7E` |
| Both (back and legs) | `F1 F1 05 01 01 07 7E` | `F1 F1 06 01 01 08 7E` | n/a |
| Head / neck, bed height | `F1 F1 19 01 01 1B 7E` | `F1 F1 1A 01 01 1C 7E` | n/a |
| Lumbar | `F1 F1 1B 01 01 1D 7E` | `F1 F1 1C 01 01 1E 7E` | n/a |
| Right back | `F1 F1 20 01 01 22 7E` | `F1 F1 21 01 01 23 7E` | `F1 F1 20 02 00 00 22 7E` / `F1 F1 21 02 00 00 23 7E` |
| Both backs | `F1 F1 23 01 01 25 7E` | `F1 F1 24 01 01 26 7E` | `F1 F1 23 02 00 00 25 7E` / `F1 F1 24 02 00 00 26 7E` |
| Right legs | n/a | n/a | `F1 F1 2A 02 00 00 2C 7E` / `F1 F1 2B 02 00 00 2D 7E` |
| Both legs | n/a | n/a | `F1 F1 2C 02 00 00 2E 7E` / `F1 F1 2D 02 00 00 2F 7E` |

| Release | Bytes (hex) | Description |
|---|---|---|
| Short release | `F1 F1 4E 00 4E 7E` | Button release / stop all |
| Long release | `F1 F1 4E 02 00 00 50 7E` | Bilateral release |
<!-- /generated -->

#### Presets

Preset frames use payload `01`, or `00 00` in bilateral layouts
(`standard_4_bilateral`, `split_after_bilateral`) and for Yoga.

<!-- generated:jiecang-presets -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Command | Standard | Bilateral layouts |
|---|---|---|
| Flat | `F1 F1 08 01 01 0A 7E` | `F1 F1 08 02 00 00 0A 7E` |
| Zero-G | `F1 F1 07 01 01 09 7E` | `F1 F1 07 02 00 00 09 7E` |
| Anti-Snore | `F1 F1 09 01 01 0B 7E` | `F1 F1 09 02 00 00 0B 7E` |
| Yoga (only when the bed reports it) | `F1 F1 28 02 00 00 2A 7E` | `F1 F1 28 02 00 00 2A 7E` |
<!-- /generated -->

#### Memory

Each profile fixes the payload shape and slot count (see the
[profile summary](#profile-summary)). The LOGICDATA apps use `01` for P1 and, in
MOTIONrelax, `00 00` for P2; Sleep Smart saves its one slot with the payload-less
`F1 F1 0A 00 0A 7E`.

<!-- generated:jiecang-memory -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Command | Payload `01` | Payload `00 00` |
|---|---|---|
| Memory 1 recall | `F1 F1 0B 01 01 0D 7E` | `F1 F1 0B 02 00 00 0D 7E` |
| Memory 2 recall | `F1 F1 0D 01 01 0F 7E` | `F1 F1 0D 02 00 00 0F 7E` |
| Memory 3 recall | `F1 F1 18 01 01 1A 7E` | n/a |
| Memory 1 save | `F1 F1 0A 01 01 0C 7E` | `F1 F1 0A 02 00 00 0C 7E` |
| Memory 2 save | `F1 F1 0C 01 01 0E 7E` | `F1 F1 0C 02 00 00 0E 7E` |
| Memory 3 save | `F1 F1 17 01 01 19 7E` | n/a |
<!-- /generated -->

#### Massage

Zone frames are `F1 F1 | zone | 02 | 08 | level | checksum | 7E`, with `00`
instead of `08` in bilateral layouts. `level` is the wire byte, which each
profile maps from its user-facing levels.

<!-- generated:jiecang-massage -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Zone | Zone byte | Off | Level 1 | Level 2 | Level 3 |
|---|---|---|---|---|---|
| Head (back) | `12` | `F1 F1 12 02 08 00 1C 7E` | `F1 F1 12 02 08 02 1E 7E` | `F1 F1 12 02 08 03 1F 7E` | `F1 F1 12 02 08 04 20 7E` |
| Foot (legs) | `14` | `F1 F1 14 02 08 00 1E 7E` | `F1 F1 14 02 08 02 20 7E` | `F1 F1 14 02 08 03 21 7E` | `F1 F1 14 02 08 04 22 7E` |
| Right | `22` | `F1 F1 22 02 08 00 2C 7E` | `F1 F1 22 02 08 02 2E 7E` | `F1 F1 22 02 08 03 2F 7E` | `F1 F1 22 02 08 04 30 7E` |

Level columns show the app levels 0-3 (wire `00`/`02`/`03`/`04`). The legacy route
sends wire levels 0-10 directly for the back and foot zones, for example
`F1 F1 12 02 08 05 21 7E`.

| Command | Standard | Bilateral layouts |
|---|---|---|
| Massage start | `F1 F1 10 01 08 19 7E` | n/a |
| Massage stop | `F1 F1 11 01 08 1A 7E` | `F1 F1 11 02 00 00 13 7E` |
| Massage mode | `F1 F1 16 01 0A 21 7E` | `F1 F1 16 02 00 00 18 7E` |
<!-- /generated -->

Massage stop differs from movement release.

#### Lights

<!-- generated:jiecang-lights -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Command | Bytes (hex) | Description |
|---|---|---|
| Light toggle: Legacy route, Comfort Motion, Dream Motion HD | `F1 F1 0F 00 0F 7E` | Sent alone on routes without RGB lighting, otherwise after the RGB state write |
| Light toggle: ERGOBALANCE (Dreamask), Dream Motion | `F1 F1 0F 02 00 00 11 7E` | Sent after the RGB state write |
| Automatic light toggle | `F1 F1 29 02 00 00 2B 7E` | Sent only when the reported state differs. Written once, except by Dream Motion HD, which sends it as a tap with a short release 100 ms later |
| RGB state | `F1 F1 52 07 BB GG RR brightness time_hi time_lo on checksum 7E` | Blue, green, red 0-255; brightness 0-100; big-endian timeout seconds; on `00`/`01` |

Timeouts: 0, 60, 120, 180, 240, 300, 600, 900, 1200, 1500 or 1800 seconds.
<!-- /generated -->

#### Queries

Status and configuration queries share opcode `00`; the payload selects one.
Each profile's startup order is in [Startup queries](#startup-queries).

<!-- generated:jiecang-queries -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Query | Bytes (hex) | Startup query of |
|---|---|---|
| Initial status | `F1 F1 00 00 00 7E` | Dream Motion HD |
| Actuator status (selector `01`) | `F1 F1 00 01 01 02 7E` | Comfort Motion, Dream Motion HD |
| Vibration (massage) | `F1 F1 00 01 08 09 7E` | Comfort Motion, ERGOBALANCE (Dreamask), Dream Motion, Dream Motion HD |
| Alarm | `F1 F1 00 01 10 11 7E` | ERGOBALANCE (Dreamask), Dream Motion, Dream Motion HD |
| Hardware | `F1 F1 00 01 40 41 7E` | Comfort Motion, ERGOBALANCE (Dreamask), Dream Motion, Dream Motion HD |
| Actuator status (selector `50`) | `F1 F1 00 01 50 51 7E` | ERGOBALANCE (Dreamask), Dream Motion |
| Light | `F1 F1 00 02 01 00 03 7E` | ERGOBALANCE (Dreamask), Dream Motion |
| Software | `F1 F1 00 02 40 00 42 7E` | ERGOBALANCE (Dreamask), Dream Motion, Dream Motion HD |
<!-- /generated -->

#### Alarm and clock

| Command | Bytes (hex) |
|---------|-------------|
| Alarm | `F1 F1 51 08 enabled any_day mask hour minute wake back leg checksum 7E` |
| Clock | `F1 F1 50 07 year-1970 month day weekday hour minute second checksum 7E` |

- Alarm `mask` sets bit 1 for Monday through bit 7 for Sunday; `any_day` is `01`
  when any weekday is selected. Massage levels are 0-3.
- Alarm wake codes: flat `0`, anti-snore `1`, zero-g `2`, memory 1 `3`,
  memory 2 `4`, yoga `6`. Yoga requires the bed's reported capability.
- Clock weekday uses Sunday = 0. HA sends it when the bed requests the clock.
  The MOTIONrelax phone always builds this P1 clock, including for the P2 family.

#### Rename

| Transport | Payload on the name characteristic |
|-----------|------------------------------------|
| G1 | Bare ASCII name |
| G3 | `01 FC 07`, name length, ASCII name |

The Dream apps write the name twice, 500 ms apart. Each profile has its own name
rule (see the [profile summary](#profile-summary)). Sleep Smart wraps its UTF-8
name on G1 too.

#### Other frames

No profile sends the timer frame (`F1 F1 0E 00 0E 7E`, timer function).

| Command | Bytes (hex) | Profiles |
|---------|-------------|----------|
| Factory reset | `F1 F1 1D 02 00 00 1F 7E` | Sleep Smart only; deletes stored memories |
| Massage parameters query | `F1 F1 00 02 08 00 0A 7E` | Sleep Smart's massage tab |
| LOGICDATA light toggle | P1 `F1 F1 0F 00 0F 7E`, MOTIONrelax P2 `F1 F1 0F 02 00 00 11 7E` | Sleep Smart sends the P1 toggle for every family |

The legacy route does not send the both-motors, neck/height, lumbar and split
frames in the motion table above, though the bed may accept them: its former
definitions called them "Head Up/Down (Alt)" (4-motor beds), "Waist" (lumbar) and
"Back Right" / "Back Top Split" (split beds).

### Responses

Responses use the request layout behind an `F2 F2` header. Each route parses
them its own way:

- **ERGOBALANCE, Dream Motion and Dream Motion HD** use the codec's
  `parse_notification()`, below.
- **Comfort Motion** uses its own handler (see its
  [Notifications](#comfort-motion-app)).
- **The legacy route** does not subscribe to notifications.
- **The LOGICDATA profiles** use `parse_notification()` in `profiles/logicdata.py`:
  the codec parser below for clock, alarm and status replies, gated per app, plus
  two app replies. Their profile sections list what each reads.

| Prefix | Minimum length | Meaning |
|--------|----------------|---------|
| `F2 F2 11` | 5 bytes | MOTIONrelax packet family: byte 4 = `01` is the middle (P2) family |
| `F2 F2 0D` | 5 bytes | Sleep Smart massage mode from byte 4, read as two hex digits parsed as decimal: `01` long interval, `02` short interval, `03` wave, `04` continuous; non-decimal text is ignored |

#### Dream app parser

`parse_notification()` returns raw values where the apps disagree, such as the
automatic-light byte. No response checksum is required: the apps accept bad
trailers. Malformed fields are ignored instead of overwriting state, and
notifications are consumed per callback without frame assembly.

| Prefix | Minimum length | Meaning |
|--------|----------------|---------|
| `F2 F2 50` | 6 bytes | Clock request; HA replies with the clock frame |
| `F2 F2 0E` | 7 bytes | Capabilities: Yoga from byte 4 bit 1. Light configuration from a binary-string test of byte 4 (its binary digits padded with zeros to eight, reversed, character 5), not a bit mask |
| `F2 F2 0F` | 7 bytes | Layout re-apply request. Only Dream Motion HD consumes it, for light-control visibility |
| `F2 F2 51` | 7 bytes | Alarm page visible; with 14+ valid bytes: enabled (byte 4), weekday bits (byte 6), hour, minute, wake code, back and leg levels (bytes 7-11) |
| `F2 F2 52 07` | 13 bytes | RGB: blue, green, red (bytes 4-6), brightness (byte 7, at most 100), timeout (bytes 8-9), on (byte 10) |
| `F2 F2 53` | 7 bytes | Automatic light state from byte 4. ERGOBALANCE and Dream Motion treat zero as on; Dream Motion HD treats non-zero as on |
| Byte 2 `05`/`06` | 9 bytes | Light on from byte 8 bit 6; `06` also reports back (byte 4) and legs (byte 6) massage. Byte 6 is the right zone in bilateral layouts |

This parser dispatches status replies `05`/`06` on byte 2 under any header and
drops massage values outside the profile's levels. Actuator-status packets are
not motor position feedback, and no motor positions are decoded.

### STOP and release behavior

- Held movement writes the motion frame at the profile's refresh interval, then
  runs the profile's release schedule (see
  [Hold and release timing](#hold-and-release-timing)). The schedule always runs
  with a fresh event, so a cancelled action still releases the motors.
- An explicit STOP sends the same release frames with the first at offset 0.
- With a [renewable hold](../SERVICES.md#renewable-holds), ERGOBALANCE, Dream
  Motion and Dream Motion HD refresh the motion frame at their own interval
  until the lease ends or a STOP arrives, as the apps do while a button is held,
  up to the 30 s ceiling. Lease expiry runs the release schedule above. A leased
  hold never sends the final frame, so motion never restarts after it ends. The
  legacy route and Comfort Motion keep finite pulses.
- A stop during a hold ends the refresh immediately, then runs the release
  schedule from its first offset. The coordinator's STOP then sends the explicit
  stop schedule.
- Presets and memory recall are sent once or repeated, then released as the
  profile specifies. Memory save is never followed by a release.
- Massage stop is a separate frame and is not a movement release.
- Physical emergency-stop semantics are unproven.

### Vectors

`tests/jiecang_vectors.py` lists each profile's frozen single-frame literals:
the test vectors of the accepted Comfort Motion 2.2.1, ERGOBALANCE 1.0.8, Dream
Motion 1.0.5 and Dream Motion HD 1.0.4 reports, and for the legacy route (which
has no report) the frames the pre-v5 controller sent.
`tests/test_jiecang_vectors.py` checks that every literal round-trips through
`codec.frame()` byte for byte and that each profile sends only its frozen frames.
`tests/logicdata_vectors.py` and `tests/test_logicdata_vectors.py` do the same for
the LOGICDATA profiles, from the accepted MOTIONrelax phone 1.0.6, tablet 1.0.4
and Sleep Smart 1.0.0 reports. The phone report states its massage-level rows as
a template, which the vector file expands.
`tests/test_codec_docs.py` checks that every frame spelled in this guide is one
of those vectors and that the generated tables are current.
Profile behavior is covered by `tests/test_jiecang.py`,
`tests/test_jiecang_app_controller.py`, `tests/test_jiecang_app_entities.py`,
`tests/test_jiecang_app_config.py` and `tests/test_dreamhd.py`; LOGICDATA behavior
by the `tests/test_logicdata_app_*.py` and `tests/test_logicdata_sleep_smart*.py`
tests.

## Profiles

Each profile section uses the fixed headings of the
[codec guide format](../BED_GUIDE_FORMAT.md#profile-sections), omitting any that
do not apply. Timing values live in the generated tables under
[Choosing a profile](#choosing-a-profile); the sections describe only what the
data cannot express.

### Legacy route

**Status:** ❓ Needs testing. No accepted APK report. The frames are those the
original controller sent, taken from pre-audit decompiles of Comfort Motion 2.1.6
([#127](https://github.com/kristofferR/ha-adjustable-bed/issues/127)) and
`com.logicdata.motionrelax` ([#260](https://github.com/kristofferR/ha-adjustable-bed/issues/260)).
smartbed-mqtt has no Jiecang implementation.

#### Setup

- Bed types `jiecang` ("Jiecang (legacy Glide / Comfort Motion)") and
  `comfort_motion` ("Comfort Motion / Lierda (legacy controls)") both select this
  profile. They differ only in detection signal, label and profile-review
  suggestions.
- Detection: the G1 or G3 service UUID yields `comfort_motion`. A device name
  containing `jiecang`, `jc-`, `dream motion`, `glide`, `comfort motion` or
  `lierda` yields `jiecang`.
- Transport: G3, then G1, otherwise the generic write characteristic
  `0000ff01-0000-1000-8000-00805f9b34fb`. Always written with response.
- Motor count selects the motors. The head and feet controls drive the back and
  legs motors.
- Only the back and legs motors are controlled. The route sends no head, lumbar,
  neck, height or right-side split frames, because no issue, capture or report
  shows a legacy bed accepting them. For a 3 or 4-motor or split bed, select the
  app profile for the bed's app instead: [Comfort Motion](#comfort-motion-app),
  [ERGOBALANCE](#ergobalance-dreamask), [Dream Motion](#dream-motion-dreamotion),
  [Dream Motion HD](#dream-motion-hd), or the
  [LOGICDATA app family](#logicdata-app-family) for MOTIONrelax and Sleep Smart beds.
- Existing legacy entries stay on this route: it keeps three memory slots, 0-10
  massage and G3 support, which the Comfort Motion app profile does not, so
  migrating them would drop entities and break G3 beds.

#### Controls

| Control | Frames |
|---------|--------|
| Back / head and legs | Motion table, standard payload |
| Flat, Zero-G, Anti-Snore | Preset table, standard payload |
| Memory 1-3 recall and program | Memory table, payload `01`; others warn and do nothing |
| Massage back and foot, 0-10 | Massage zones `12` and `14`; levels step 0-10, off writes level 0 to both |
| Massage toggle | Massage start when both levels are 0, otherwise massage stop |
| Massage mode cycle | Massage mode, standard |
| Light toggle | Light toggle without payload |

#### Timing

See the [generated tables](#hold-and-release-timing).

#### Notifications

None: the legacy route does not subscribe.

#### Evidence

None beyond the controller's own tests.

#### MOTIONrelax beds on this route

The accepted MOTIONrelax 1.0.6 and 1.0.4 apps find a bed only by scanning for
the G1 (T1) and G3 (T3) services; neither app has a name, manufacturer-data or
service-data filter. Detection turns either service into `comfort_motion`, whose
profile review and Jiecang question offer the
[LOGICDATA app](#logicdata-app-family). A bed that lands on `jiecang` by its name
alone has no evidence of being a MOTIONrelax bed.

A MOTIONrelax bed that still runs this route, for example one whose services were
missing from the advertisement, differs from the apps. This route:

- sends P1 frames only, so a P2 (middle-motor) bed gets frames from the other
  packet family;
- refreshes movement every 50 ms for 25 frames and releases at once, where the
  apps refresh every 100 ms, add one final movement frame and release 100 ms later;
- offers memory slot 3 and massage levels 1 and 5-10, which the apps never send;
- prefers G3, then G1, and never writes T2, where the apps write to whichever
  transport service enumerates last, which can be T2;
- subscribes to no notifications.

Set such a bed up with the LOGICDATA row, or choose the LOGICDATA app in
Configure's bed-type list, which then asks the app, packet family and layout.

### Comfort Motion app

**App:** [Comfort Motion](https://play.google.com/store/apps/details?id=com.jiecang.app.android.jiecangbed)
2.2.1 (28), `com.jiecang.app.android.jiecangbed`.

**Status:** ❓ Needs testing (APK-verified, hardware not yet verified by real users)

#### Setup

1. Select the Jiecang bed type, then **Comfort Motion app**.
2. Choose the physical layout used in the app: back/legs, back/legs/neck, or
   back/legs/neck/lumbar.
3. Enable massage and light controls only when fitted.

- Detection: none. Shared Bluetooth UUIDs do not identify the app. The app scans
  only G1's service, with no name, manufacturer or RSSI restrictions, and its
  barcode and saved-address routes also reach G2. HA uses its own Bluetooth
  scanner and manual address selection; select this app explicitly, including
  for G2.
- There is no PIN, bonding or login exchange.
- Transport **Auto** uses the last complete matching transport in GATT
  enumeration order, retaining both notification subscriptions when both exist.
  Select G1 or G2 to pin one. G3 is unsupported by this app.
- Writable name roles are rediscovered per connection; G2 alone cannot reuse an
  old G1 name handle.
- Write response mode comes from the discovered characteristic properties.
- Comfort Motion sends only its frozen frames and the raw rename (APK Protocol
  Audit row115).

#### Controls

| Control | Frames and layouts |
|---------|--------------------|
| Back, legs | Motion table, all layouts |
| Back/legs together | Two-motor layout |
| Neck (HA `head` axis) | Three- and four-motor layouts |
| Lumbar | Four-motor layout |
| Flat, Zero-G, Anti-Snore | Preset table |
| Memory 1-2 recall and save | Memory table |
| Massage back (HA `head` zone) and foot, 0-3 | Massage zones `12` and `14` |
| Massage mode | Massage mode, standard, without a release or an invented mode number |
| Massage stop | Massage stop, standard |
| Light | Light toggle without payload |

- Massage up/down uses the last tag-06 state; bounds do nothing. Unrecognized wire
  levels leave the slider unknown and make stepping a no-op. Writes do not
  optimistically change reported state.
- Light on/off actions toggle only when the last reported state differs and refuse
  unknown state. The native toggle remains available before feedback. Neither
  writes nor disconnects fabricate feedback.
- Every hold ends with its release, including on cancellation and exceptions, and
  no movement frame follows a release.

#### Timing

- Hold, release and one-shot timing: see the
  [generated tables](#hold-and-release-timing).
- Connection setup: HA subscribes to notifications 100 ms after setup starts,
  then sends the [startup queries](#startup-queries) at their offsets from setup
  start, serialized. Queries run without a layout or massage gate, including with
  massage disabled. They are scheduled duplicate writes, not ACK retries.
- HA cancels a failed setup and removes its subscriptions instead of letting old
  timers write after a reconnect. The next connection gets a fresh batch.

#### Notifications

`ComfortMotionController._handle_notification` reads the tag at byte 2 under any
header, without frame validation or assembly:

| Tag at byte 2 | Minimum length | Consumed fields |
|---------------|----------------|-----------------|
| `0F` | 7 bytes | byte 4: layout 1..6, otherwise 0 |
| `05` | 9 bytes | byte 8, bit 6: light on |
| `06` | 9 bytes | byte 4: unsigned back massage; byte 6: unsigned foot massage; byte 8, bit 6: light on |

- Raw massage values outside the profile's levels are kept and shown as unknown.
- Other, short or empty values are ignored safely.
- Layout 1/2 describes two motors, 3/4 three, and 5/6 four; even values
  initially show massage navigation. These are app UI layouts, not continuing
  write gates.
- The app retains motor selection, massage zone and intensity and active panels
  through repeated, changed or invalid layouts and same-instance reconnect.
- HA keeps explicitly selected axes stable, retains reported state across its
  controller replacement on reconnect, and never clears massage or light state on
  a layout reply.
- The latest reported layout and raw intensity values remain in protocol
  diagnostics.
- A user can change physical layout or massage presence in options without
  relying on the app's stale-selector behavior.

#### Services

**Wake routine:** `adjustable_bed.jiecang_wake` with `preset` set to `memory_1`,
`memory_2`, `zero_g`, `flat` or `anti_snore`, and optional
`head_level`/`foot_level` 0..3.

| Offset | Action |
|--------|--------|
| 0 ms | Back massage at `head_level`, release 100 ms later (zero skips the zone) |
| 200 ms | Foot massage at `foot_level`, release 100 ms later (zero skips the zone) |
| 500 ms | Preset, without a subsequent release, as on the app's conditional alarm path |

- Cancellation always releases; stop the massage with `adjustable_bed.jiecang_stop_wake`.
- Massage must be enabled before using nonzero levels. Yoga is unsupported and
  rejected before writes.
- Schedule the service with Home Assistant automations. There is no BLE alarm
  programming or clock-setting command.

**Rename:** `adjustable_bed.rename` writes the name bare to the discovered G1
name role, following the profile's name rule (see the
[profile summary](#profile-summary)). There is no name acknowledgment. This does
not change HA's local device name.

#### Evidence

APK Protocol Audit row115 holds the accepted report, every disposition and
exclusion. Physical actuator effects, ATT properties, release effects, mode
names and rename persistence remain validation for real users after beta or
release; maintainers need not acquire a bed.

### Dream app family

**Status:** ❓ Needs testing. Static verified, hardware unverified for all three.

ERGOBALANCE, Dream Motion and Dream Motion HD share the behavior below. Their own
sections list what differs.

#### Setup

- Detection: none. The apps use the same Bluetooth services, so a service UUID
  cannot determine which app's release behavior or layout applies. No pairing,
  PIN or device-name pattern is inferred from these apps. Layout, massage and
  light are user choices, never inferred from the name or a shared service.
- Automatic transport selection uses a coherent GATT service and its
  corresponding write, notification and name channels, trying G3, then G1, then
  G2. Explicit G1/G2/G3 overrides are available.
- Layouts are listed in the [layout table](#layouts-and-axes). The separate
  split-after-bilateral option keeps the app's combination of standard split
  movement with bilateral presets and massage. It does not rely on accidentally
  retained Android settings.

#### Controls

- Movement, presets and memory follow the command tables and the layout's
  payloads. Yoga appears only when the bed reports it.
- Massage level writes one frame. In bilateral layouts it is followed by the
  profile's recall release (see [One-shot timing](#one-shot-timing)).
- Massage mode writes one frame, then a long release after 1000 ms.
- Lights: on, off, color, brightness and timer write the full RGB state. When no
  light state has been received, HA first sends the light query twice (100 ms
  apart) and waits up to 1 s; without a reply it refuses the change, preserving
  unknown color and timer settings.
- Light toggle: RGB state write, the toggle after 150 ms, then short and long
  release 80 ms later.
- Automatic light: the toggle frame is written once, only when the reported state
  differs.
- Color, brightness, timeout and automatic lighting require the light option, a
  non-bilateral layout and the bed's reported light-configuration capability.
  Dream Motion HD has its own visibility rules (see its Notifications).
- Cleanup also runs when Home Assistant cancels a command; a cancelled hold never
  sends the final movement packet. Presets, save operations, massage and lighting
  keep their own command sequences instead of sharing a universal repeat/stop
  schedule.

#### Timing

- Hold, release and one-shot timing: see the
  [generated tables](#hold-and-release-timing).
- Startup: when the selected transport has a complete G1 or G3 profile (or G2 next
  to one), HA waits 1 s after subscribing, then sends the
  [startup queries](#startup-queries) at their offsets. It then waits up to 0.5 s
  for the capability reply. On G3, the name characteristic is subscribed 3 s after
  the queries start when it supports notifications.
- HA subscribes before the first query and sends the startup sequence once per
  connection, with each query twice as the apps do.

#### Notifications

The [Dream app parser](#dream-app-parser). Capability replies gate Yoga and the
light controls; HA answers clock requests with the clock frame.

#### Services

- `adjustable_bed.jiecang_set_alarm` writes the app's weekly alarm configuration.
  It accepts a time, weekdays, wake preset and massage levels. Storing that
  configuration is separate from executing the Android app's local wake routine.
- `adjustable_bed.jiecang_wake` executes the proven wake packet sequence. Use a
  Home Assistant time trigger when local scheduling is required. Yoga can be
  encoded in the alarm configuration but is not an implemented wake choice in any
  app's executor.
- `adjustable_bed.jiecang_stop_wake` stops active wake massage without changing
  the saved alarm schedule. It sends the standard massage stop, even on bilateral
  layouts.
- `adjustable_bed.rename` (or the older `jiecang_rename`) writes a Bluetooth name
  that matches the profile's name rule (see the
  [profile summary](#profile-summary)). This changes the advertised device name,
  separately from its friendly name in Home Assistant.
- The normal cover, button, light, number and select actions remain available for
  individual movement, presets, massage and lighting.

**Wake sequence.** Alarm massage uses standard-payload frames on every layout,
including bilateral ones. ERGOBALANCE and Dream Motion send a long release when
the routine is cancelled; [Dream Motion HD](#dream-motion-hd) handles completion
and cancellation itself.

<!-- generated:jiecang-wake -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

Offsets count from the start of the routine. A zone at level 0 is skipped, and a
preset replaces the memory recall.

**ERGOBALANCE (Dreamask), Dream Motion**, every other layout

| Step | Offsets | Frame at level 1, memory 2 |
|---|---|---|
| Back massage | 0 ms, 30 ms, 60 ms | `F1 F1 12 02 08 02 1E 7E` |
| Short release | 90 ms, 120 ms, 150 ms | short release |
| Leg massage | 300 ms, 330 ms, 360 ms | `F1 F1 14 02 08 02 20 7E` |
| Short release | 390 ms, 420 ms, 450 ms | short release |
| Preset or memory recall | 800 ms, 830 ms, 860 ms, 890 ms, 920 ms | `F1 F1 0D 02 00 00 0F 7E` |
| Long release, memory 2 only | 1600 ms | long release |
| Long release | 1690 ms, 1720 ms | long release |

**ERGOBALANCE (Dreamask), Dream Motion**, `split_series`, `split_after_bilateral`

| Step | Offsets | Frame at level 1, memory 2 |
|---|---|---|
| Back massage | 0 ms, 30 ms, 60 ms | `F1 F1 12 02 08 02 1E 7E` |
| Short release | 90 ms, 120 ms, 150 ms | short release |
| Right massage, at the back level | 180 ms, 210 ms, 240 ms | `F1 F1 22 02 08 02 2E 7E` |
| Short release | 270 ms, 300 ms, 330 ms | short release |
| Leg massage | 500 ms, 530 ms, 560 ms | `F1 F1 14 02 08 02 20 7E` |
| Short release | 590 ms, 620 ms, 650 ms | short release |
| Preset or memory recall | 800 ms, 830 ms, 860 ms, 890 ms, 920 ms | `F1 F1 0D 02 00 00 0F 7E` |
| Long release | 1690 ms, 1720 ms | long release |

**Dream Motion HD**, every other layout

| Step | Offsets | Frame at level 1, memory 2 |
|---|---|---|
| Back massage | 0 ms, 30 ms, 60 ms | `F1 F1 12 02 08 02 1E 7E` |
| Short release | 90 ms, 120 ms, 150 ms | short release |
| Leg massage | 500 ms, 530 ms, 560 ms | `F1 F1 14 02 08 02 20 7E` |
| Short release | 590 ms, 620 ms, 650 ms | short release |
| Preset or memory recall | 800 ms, 830 ms, 860 ms, 890 ms, 920 ms | `F1 F1 0D 01 01 0F 7E` |

**Dream Motion HD**, `standard_3_split_upper`, `split_series`

| Step | Offsets | Frame at level 1, memory 2 |
|---|---|---|
| Back massage | 0 ms, 30 ms, 60 ms | `F1 F1 12 02 08 02 1E 7E` |
| Short release | 90 ms, 120 ms, 150 ms | short release |
| Right massage, at the back level | 180 ms, 210 ms, 240 ms | `F1 F1 22 02 08 02 2E 7E` |
| Short release | 270 ms, 300 ms, 330 ms | short release |
| Leg massage | 500 ms, 530 ms, 560 ms | `F1 F1 14 02 08 02 20 7E` |
| Short release | 590 ms, 620 ms, 650 ms | short release |
| Preset or memory recall | 800 ms, 830 ms, 860 ms, 890 ms, 920 ms | `F1 F1 0D 01 01 0F 7E` |
<!-- /generated -->

#### Evidence

- ERGOBALANCE and Dream Motion: APK Protocol Audit cluster-004.
- Dream Motion HD: APK Protocol Audit row105.

### ERGOBALANCE (Dreamask)

**App:** [ERGOBALANCE](https://play.google.com/store/apps/details?id=com.jiecang.dreamask.app.android.bed)
1.0.8 (8), `com.jiecang.dreamask.app.android.bed`.

**Status:** ❓ Needs testing. Static verified, hardware unverified.

Behaves as the [Dream app family](#dream-app-family), except as below.

#### Setup

- Selecting G2 requires G1 or G3 to be present as well.

#### Timing

See the [generated tables](#hold-and-release-timing).

#### Evidence

APK Protocol Audit cluster-004.

### Dream Motion (Dreamotion)

**App:** [Dream Motion](https://play.google.com/store/apps/details?id=com.jiecang.dreamotion.app.android.bed)
1.0.5 (11), `com.jiecang.dreamotion.app.android.bed`.

**Status:** ❓ Needs testing. Static verified, hardware unverified.

Behaves as the [Dream app family](#dream-app-family), except as below.

#### Setup

- Standalone G2 is supported through the manual connection route.

#### Timing

See the [generated tables](#hold-and-release-timing).

#### Evidence

APK Protocol Audit cluster-004.

### Dream Motion HD

**App:** [Dream Motion HD](https://play.google.com/store/apps/details?id=com.dreamhd.jiecang.android.pad.bed)
1.0.4 (4), `com.dreamhd.jiecang.android.pad.bed`.

**Status:** ❓ Needs testing. Static behavior is verified; physical effects
remain unverified.

Behaves as the [Dream app family](#dream-app-family), except as below.

#### Setup

- An explicit tablet profile. It does not migrate existing phone-app or legacy
  entries.
- Layouts: the standard layouts with independent massage and light choices, plus
  the split-series layout (see the [layout table](#layouts-and-axes)).
  Bilateral and split-after-bilateral belong to other profiles and are rejected
  for HD.
- The existing setup massage option and **Enable light controls** apply.
- Standalone G2 is supported through the manual connection route. G2 has no name
  channel and no startup queries when selected alone; standalone setup completion
  is not a hardware claim.

#### Controls

- Massage is Off and levels 1-3; normal steps, mode changes and stop write once.
  Intensity changes await notification feedback.
- Lights: RGB color, brightness and timeout use the app's BGR packet. When no
  light state has been received, HA sends the initial status query instead of the
  light query.
- Light toggle: the RGB state at 0 ms, a short release at +100 ms, the light
  toggle without payload at +200 ms and a final short release at +300 ms. A
  cancelled toggle still ends with the short release.
- Automatic light: the toggle frame is sent as a tap with a short release (see
  the [lights table](#lights)), not written once.
- HA always honors **Enable light controls**, even where the Android UI would
  reveal a picker despite that preference.

#### Timing

See the [generated tables](#hold-and-release-timing). HD has its own startup
queries, without a light-status query.

#### Notifications

- Right-back and leg feedback share byte 6 on split layouts, so both sliders
  report that value rather than inventing a third feedback field.
- A negative light-configuration reply hides the picker and persists
  suppression. A later positive reply reveals it without clearing suppression. A
  light-status reply reveals only the picker when suppression is clear, never the
  automatic-light switch.
- A layout re-apply request hides the light controls when light is disabled and
  the layout is not split series.
- Connection resets light visibility and cached color.
- Automatic-light status treats zero as off and any nonzero value as on. Its
  physical sensor meaning has not been established.
- Late capability and RGB replies add the corresponding controls without
  reloading HA. Repeated negative and positive feature replies retire and
  recreate the RGB, brightness, timer, automatic-light and Yoga controls as their
  gates change.
- For paired HD beds, each side's Yoga button follows that side's reported
  capability. The combined Yoga button appears only when both sides support it,
  and follows later withdrawals and replies without reloading the pair.

#### Services

- The weekly-alarm and wake services of the [Dream app family](#dream-app-family)
  work for HD.
- Wake routine: see the [wake sequence](#dream-app-family); it has none of the
  phone apps' long releases. HA sends a short release on completion and stops
  wake massage on cancellation or failure, including a failed release write.
- `adjustable_bed.rename` accepts printable ASCII names, including spaces. G1
  writes the bare name; G3 prefixes the name's byte length, correct for every
  length. Non-ASCII names are rejected. The older `jiecang_rename` alias keeps its
  narrower released schema.

#### Evidence

APK Protocol Audit row105.

### LOGICDATA app family

**Status:** ❓ Needs testing. Static verified, hardware unverified for all three.

The `logicdata_app` bed type selects one of three app profiles in
`profiles/logicdata.py`: `phone`, `tablet` or `sleep_smart`. Each drives two packet
families, chosen independently of the GATT transport: P1 sends the standard `01`
payload and P2 the `00 00` payload. Their own sections list what differs. Existing
[Jiecang legacy](#legacy-route) and [SILVERmotion/SimplicityFrame](logicdata.md)
configurations retain their previous behavior.

#### Setup

1. Select **LOGICDATA: SILVERmotion (SimplicityFrame), MOTIONrelax phone and
   tablet, and Sleep Smart Air Mattress apps** in the bed-type list, or
   **LOGICDATA** under the brands. Searching for SILVERmotion, MOTIONrelax or Sleep
   Smart finds the same row.
2. Choose the app: the MOTIONrelax phone or tablet app, or the Sleep Smart Air
   Mattress app's bed base. SILVERmotion runs the [SimplicityFrame](logicdata.md)
   protocol and the Sleep Smart air mattress pump is
   [its own device](logicdata-sleep-smart.md), so both are answers of the same
   question.
3. Answer the app's own questions: the packet family, then the physical layout
   the app offers (see each profile below), the light and, under Advanced, the
   transport.

- Configure keeps the light setting. Another app, family, layout or transport
  goes through **Reconfigure**, which checks that the link has the chosen app's
  transport before it saves and lists the controls that change. A bed entry
  never changes into the pump.
- A Comfort Motion entry's profile review suggests this family. Its Repairs
  issue opens the Reconfigure question with **LOGICDATA app: MOTIONrelax, or the
  Sleep Smart Air Mattress bed base** as one more answer; that answer continues
  with these questions and the LOGICDATA transport check. The issue stays open
  until a change is saved or you choose **Keep**.

- Detection: none. The Bluetooth service alone cannot identify those choices; the
  `ff12` and `fe60` services are shared with other Jiecang/Lierda-based apps, and
  existing entries keep their bed type.
- Automatic transport selection keeps each service's write, notification and
  name characteristics together. It needs exactly one complete transport; when
  GATT is ambiguous, select one explicitly. Explicit T1, T2 and T3 choices are
  available.
- Writes use a response when the characteristic advertises `write`, otherwise
  write-without-response. No PIN or pairing flow is inferred from these artifacts.
- For two separately addressed beds, configure each side before combining them.
  Shared paired-bed options preserve each side's app, packet family, layout and
  transport. Unpair temporarily to change those per-side settings.

#### Controls

- Every axis uses the global short release, so all motor controls on one bed
  share one scheduler resource. An explicit stop sends the short release
  immediately.
- Massage levels are Off and levels 1–3, wire values `00`/`02`/`03`/`04`. HA's
  head zone is the back (left back in `split_series`), the foot zone the legs,
  and the right zone the right back in `split_series`. Massage level and massage
  stop are single frames.
- When lighting is enabled, the Under Bed Lights binary sensor exposes the
  latest notification state. The light button remains toggle-only; pressing it
  does not optimistically replace the reported state.
- Neither app reports motor positions, brightness or RGB color, so the
  integration does not create those controls.

#### Timing

Every LOGICDATA profile supports a
[renewable hold](../SERVICES.md#renewable-holds): movement refreshes at the
movement interval until the lease ends or a STOP arrives, up to the 30 s
ceiling, then sends the touch release. A leased hold sends no final frame.

The tables below come from the profile data.

<!-- generated:logicdata-profiles -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

**LOGICDATA profile summary**

| Profile | P2 payload `00 00` on | Presets (P1 / P2) | Memory | Massage | Clock request | Alarm | Name rule | Name writes |
|---|---|---|---|---|---|---|---|---|
| MOTIONrelax phone app | back and legs movement, presets, memory, light | flat, zero_g, anti_snore / flat | 2 slots | P1 | 6+ bytes | P1 | `[ -~]{1,255}` (ascii) | +0 ms; T1 bare |
| MOTIONrelax tablet app | back and legs movement, presets, memory, light | flat, zero_g, anti_snore / flat | 2 slots | P1 | none | none | `[ -~]{1,255}` (ascii) | +0 ms, +500 ms; T1 bare |
| Sleep Smart Air Mattress app (bed base) | back and legs movement | flat, zero_g, anti_snore / flat, zero_g, anti_snore | 1 slot | P1, P2 | 3+ bytes | none | `[0-9a-zA-ZäöüÄÖÜß]{1,20}` (utf-8) | +0 ms; always wrapped |

**LOGICDATA timing**

| Profile | Movement refresh | Hold until release | Touch release | Held presets (P1 / P2) | Hold refresh | Memory save | Light | Massage mode | Massage query |
|---|---|---|---|---|---|---|---|---|---|
| MOTIONrelax phone app | 100 ms, final frame | renewable lease | +100 ms short release | none / flat, memory_1, memory_2 | flat 100 ms + final frame, memory_1 200 ms, memory_2 200 ms | +0 ms, +30 ms, +60 ms | +80 ms short release, +80 ms long release, +100 ms short release | +1000 ms long release, +1100 ms short release | none |
| MOTIONrelax tablet app | 100 ms, final frame | renewable lease | +100 ms short release | none / flat, memory_1, memory_2 | flat 100 ms + final frame, memory_1 200 ms, memory_2 200 ms | +0 ms, +30 ms, +60 ms | +80 ms short release, +80 ms long release, +100 ms short release | none | none |
| Sleep Smart Air Mattress app (bed base) | 100 ms, final frame | renewable lease | +100 ms short release | flat, zero_g, anti_snore, memory_1 / flat, zero_g, anti_snore, memory_1 (buttons hold) | flat 200 ms, zero_g 200 ms, anti_snore 200 ms, memory_1 200 ms | +0 ms, no payload | +80 ms short release, +80 ms long release, +100 ms short release | +1000 ms long release, +1100 ms short release | +100 ms, +250 ms, +450 ms |

**LOGICDATA startup**

| Profile | Wait, then subscribe | T3 name subscription | Clock |
|---|---|---|---|
| MOTIONrelax phone app | 1000 ms | at +3000 ms | at +3000 ms, +3100 ms |
| MOTIONrelax tablet app | 1000 ms | at +3000 ms | none |
| Sleep Smart Air Mattress app (bed base) | 300 ms | 100 ms after T3 data; queries only once both succeed | on request |

**MOTIONrelax phone app P1**

| Offsets | Query | Bytes (hex) |
|---|---|---|
| 1000 ms, 1100 ms | Actuator status (selector `50`) | `F1 F1 00 01 50 51 7E` |
| 1200 ms, 1300 ms | Hardware | `F1 F1 00 01 40 41 7E` |
| 1400 ms, 1500 ms | Vibration (massage) | `F1 F1 00 01 08 09 7E` |

**MOTIONrelax phone app P2**

| Offsets | Query | Bytes (hex) |
|---|---|---|
| 1000 ms, 1100 ms | Actuator status (selector `50`) | `F1 F1 00 01 50 51 7E` |
| 1200 ms, 1300 ms | Software | `F1 F1 00 02 40 00 42 7E` |
| 1400 ms, 1500 ms | Vibration (massage) | `F1 F1 00 01 08 09 7E` |

**MOTIONrelax tablet app P1**

| Offsets | Query | Bytes (hex) |
|---|---|---|
| 1000 ms, 1100 ms | Actuator status (selector `01`) | `F1 F1 00 01 01 02 7E` |
| 1200 ms, 1300 ms | Hardware | `F1 F1 00 01 40 41 7E` |
| 1400 ms, 1500 ms | Vibration (massage) | `F1 F1 00 01 08 09 7E` |

**MOTIONrelax tablet app P2**

| Offsets | Query | Bytes (hex) |
|---|---|---|
| 1000 ms, 1100 ms | Actuator status (selector `01`) | `F1 F1 00 01 01 02 7E` |
| 1200 ms, 1300 ms | Software | `F1 F1 00 02 40 00 42 7E` |
| 1400 ms, 1500 ms | Vibration (massage) | `F1 F1 00 01 08 09 7E` |

**Sleep Smart Air Mattress app (bed base) P1**

| Offsets | Query | Bytes (hex) |
|---|---|---|
| 300 ms | Software | `F1 F1 00 02 40 00 42 7E` |
| 600 ms, 1400 ms, 1500 ms | Vibration (massage) | `F1 F1 00 01 08 09 7E` |
| 900 ms, 1200 ms, 1300 ms | Hardware | `F1 F1 00 01 40 41 7E` |
| 1000 ms, 1100 ms, 1200 ms, 1500 ms | Actuator status (selector `50`) | `F1 F1 00 01 50 51 7E` |
| 1800 ms, 2100 ms | Light | `F1 F1 00 02 01 00 03 7E` |
| 2400 ms, 2700 ms | Device status | `F1 F1 00 00 00 7E` |

**Sleep Smart Air Mattress app (bed base) P2**

| Offsets | Query | Bytes (hex) |
|---|---|---|
| 300 ms, 1200 ms, 1300 ms | Software | `F1 F1 00 02 40 00 42 7E` |
| 600 ms, 1400 ms, 1500 ms | Vibration (massage) | `F1 F1 00 01 08 09 7E` |
| 900 ms | Hardware | `F1 F1 00 01 40 41 7E` |
| 1000 ms, 1100 ms, 1200 ms, 1500 ms | Actuator status (selector `50`) | `F1 F1 00 01 50 51 7E` |
| 1800 ms, 2100 ms | Light | `F1 F1 00 02 01 00 03 7E` |
| 2400 ms, 2700 ms | Device status | `F1 F1 00 00 00 7E` |

**LOGICDATA layouts and axes**

| Layout | Axes | Massage zones | Profiles |
|---|---|---|---|
| `standard_2` (Back and legs (2 motors)) | back, legs, both | back, legs | MOTIONrelax phone app, MOTIONrelax tablet app, Sleep Smart Air Mattress app (bed base) |
| `standard_3_neck` (Back, legs and neck) | back, legs, head | back, legs | MOTIONrelax phone app, MOTIONrelax tablet app |
| `standard_3_lumbar` (Back, legs and lumbar) | back, legs, lumbar | back, legs | MOTIONrelax phone app, MOTIONrelax tablet app |
| `standard_3_hi_low` (Back, legs and height) | back, legs, bed_height | back, legs | MOTIONrelax phone app, MOTIONrelax tablet app |
| `standard_3_split_upper` (Split upper (3 motors)) | back, right_back, both_backs, legs | back, legs | MOTIONrelax phone app, MOTIONrelax tablet app |
| `standard_4` (Back, legs, neck and lumbar) | head, back, lumbar, legs | back, legs | MOTIONrelax phone app, MOTIONrelax tablet app |
| `split_series` (Split series) | back, right_back, legs | back, right | MOTIONrelax phone app, MOTIONrelax tablet app |
| `split_series` (Split series) | back, legs, both | back, right | Sleep Smart Air Mattress app (bed base) |
| `middle` (Middle layout) | back, legs | none | MOTIONrelax phone app, MOTIONrelax tablet app |
<!-- /generated -->

- Movement repeats at the refresh interval for the motor pulse count; on normal
  completion the app's final movement write, then the touch release. A cancelled
  movement sends the release without another movement write.
- Timed moves include the terminal write and release delay in the requested
  duration, rounded up to the next refresh interval, so the release lands at the
  requested duration.
- Startup offsets count from the start of the query sequence: after the data
  subscription for MOTIONrelax, after readiness for Sleep Smart.

#### Notifications

The apps do not validate checksum/trailer or declared payload lengths; HA
preserves that and only guards field bounds. Status replies `05`/`06` (any header,
9+ bytes) report the light and massage levels, the right zone in `split_series`.

#### Evidence

Every LOGICDATA profile sends only its frozen frames
(`tests/test_logicdata_vectors.py`).

### MOTIONrelax phone and tablet

**App:** [MOTIONrelax phone](https://play.google.com/store/apps/details?id=com.logicdata.app.android.bed)
1.0.6 (7), `com.logicdata.app.android.bed`, and
[MOTIONrelax tablet](https://play.google.com/store/apps/details?id=com.logicdata.app.android.pad.bed)
1.0.4 (5), `com.logicdata.app.android.pad.bed`.

**Status:** ❓ Needs testing. Static verified, hardware unverified.

Behaves as the [LOGICDATA app family](#logicdata-app-family), except as below.

#### Setup

- P2 is the dedicated middle layout, so setup asks no layout for it; the
  remaining layouts use P1.
- The standard family supports two motors; three motors with neck, lumbar, height
  or split-upper controls; four motors; and split-series controls. Standard
  layouts have independent massage and under-bed light settings. The middle-motor
  family provides back, legs, flat, two memory slots and lighting.
- Vienna and Toronto are aliases for two-motor layouts with different massage
  settings.
- If the bed's family reply contradicts the configured family, controls other
  than release are refused until the bed is reconfigured. The disabled-by-default
  `logicdata_app_family_match` sensor shows the result.
- When a T1 or T3 transport is present, HA sends the startup queries after
  subscribing. T2 can be used through a known address, but its standalone route
  has no startup query burst in either app. On T3 the name characteristic is
  subscribed too. The phone writes the clock during startup; the tablet has no
  clock writer.

#### Controls

| Action | Sequence |
|--------|----------|
| Presets and memory recall | One frame, then the touch release |
| Memory save | The save frame at the memory-save offsets |
| Light toggle | Toggle, then the light releases |
| Massage mode | Phone: two releases. Tablet: none |
| Held flat or memory (P2) | `adjustable_bed.logicdata_hold_preset`: refresh, then the touch release |

- P1 exposes Flat, Zero-G and Anti-Snore; P2 only Flat. Both families have two
  memory slots. Massage is P1 only.
- For the middle family, `adjustable_bed.logicdata_hold_preset` holds flat,
  memory 1 or memory 2 for a chosen duration and releases on completion or
  cancellation. Ordinary one-shot preset buttons remain available.

> [!NOTE]
> A P2 flat tap is followed by the short release, as a held flat is, so movement
> always ends with cleanup.

#### Timing

See the [LOGICDATA tables](#logicdata-app-family) for every interval and offset.

#### Notifications

| Prefix | Minimum length | Meaning |
|--------|----------------|---------|
| `F2 F2 11` | 5 bytes | Packet family (see [Responses](#responses)) |
| `F2 F2 0F` | 7 bytes | Hardware acknowledgment; no state |
| `F2 F2 50` (phone) | 6 bytes | Clock request; HA answers with the clock frame |
| `F2 F2 51` (phone) | 14 bytes | Alarm: enabled (byte 4), weekday bits (byte 6), hour, minute, wake code, back and leg levels (bytes 7–11) |
| Byte 2 `05`/`06`, any header | 9 bytes | Light and massage status |

MOTIONrelax drops a clock request that arrives while an earlier request is still
being answered. The tablet decodes neither clock nor alarm replies.

#### Services

- The phone profile synchronizes the clock and supports weekly native alarm
  configuration through `adjustable_bed.logicdata_set_alarm` when the standard
  family is selected: weekdays, time, a supported preset (wake codes flat `0`,
  anti-snore `1`, zero-g `2`, memory 1 `3`, memory 2 `4`) and back/leg massage
  levels. The alarm state is exposed as the `logicdata_app_alarm` sensor. The
  tablet profile has no clock or alarm BLE implementation.
- `adjustable_bed.rename` changes the Bluetooth device name when the chosen
  transport provides a name characteristic (T1 bare, T3 wrapped). This is
  separate from the Home Assistant friendly name; the older `logicdata_rename`
  name still works. The controller accepts 1–255 printable ASCII characters, a
  deliberate input policy that avoids the tablet app's malformed Unicode name
  encoding.

#### Evidence

Both profiles send only their frozen frames. APK Protocol Audit cluster-006
records the dispositions, phone/tablet differences, report hashes and
exclusions.

### Sleep Smart Air Mattress (bed)

**App:** [Sleep Smart Air Mattress](https://play.google.com/store/apps/details?id=com.logicdata.app.mattress.bed)
1.0.0 (1), `com.logicdata.app.mattress.bed`, app profile `sleep_smart`. The app
also drives a separate air mattress pump, configured as its own
[`logicdata_air_pump` entry](logicdata-sleep-smart.md).

**Status:** ❓ Needs testing. Static verified, hardware unverified.

Behaves as the [LOGICDATA app family](#logicdata-app-family), except as below.

#### Setup

| Setting | Choices |
|---|---|
| Command family | `p1` for the Vienna and Toronto beds; `p2` for the Middle Rail bed |
| Layout | `standard_2` (standard series) or `split_series` (split series) |
| Massage | Enable when the bed has massage. The app's massage tab is reachable for every bed profile |
| Light | Enable for under-bed lighting |
| Transport | `auto`, `t1`, `t2` or `t3`, as for MOTIONrelax |

- The bed always uses a two-motor movement layout: back, legs and both together.
- The series only chooses the massage zones: standard has back and foot, split
  has left back and right back.
- The Middle Rail family changes only back and legs movement to the two-byte
  zero payload. Combined movement (`F1 F1 05 01 01 07 7E` / `F1 F1 06 01 01 08 7E`),
  presets, memory, light and massage keep their P1 frames.
- Only a T3 connection becomes ready in the app: both T3 subscriptions (data and
  name) must succeed. Every other data notify role the app finds is subscribed
  too. A T3 service next to a selected T1 or T2 transport also makes the bed
  ready, and startup queries then use the selected write role. T1 or T2 alone
  stays silent until a control is used. A failed name subscription leaves
  controls available without queries.

#### Controls

| Control | Behavior |
|---|---|
| Flat, Zero Gravity, Anti-Snore, Memory 1 recall | Hold-only in the app: a tap sends nothing. A button holds the preset for the motor pulse count × the hold refresh, then releases |
| `logicdata_hold_preset` | The same hold for an explicit 0.2–60 s duration |
| Memory 1 save | One `F1 F1 0A 00 0A 7E`, without a release. The app has one memory slot |
| Under-bed light | Toggle, then the light releases |
| Massage stop / mode | Massage stop only stops massage. Mode sends its fixed frame, then the two releases |
| Refresh massage state | The massage tab's parameter query (`F1 F1 00 02 08 00 0A 7E`), at the massage-query offsets |
| Factory reset | Disabled by default. One reset frame; the app warns that it deletes stored memories and that a later held DOWN performs a reference drive |
| `rename` | `01 FC 07`, byte length and UTF-8 name on the name characteristic, once |

Cancellation and failures always finish with the release frame.

#### Timing

See the [LOGICDATA tables](#logicdata-app-family). When ready, the integration
merges the app's two startup schedules: software, vibration, hardware, actuator,
light and device-status queries, with the actuator, hardware (Middle Rail:
software) and vibration pairs between them.

#### Notifications

| Notification | Meaning |
|--------------|---------|
| `F2 F2 50`, any length | Clock request; every request is answered with the current local time |
| `F2 F2 0D`, 5+ bytes | Massage mode (see [Responses](#responses)), shown by the **Massage mode** sensor; unknown for other values |
| Byte 2 `05`/`06`, 9+ bytes | Light and massage status |

No positions, firmware, model or calibration are reported.

#### Services

- Names are 1–20 characters from `0-9`, `a-z`, `A-Z`, `ä`, `ö`, `ü`, `Ä`, `Ö`,
  `Ü` and `ß`, the app's edit-field alphabet, and at most 100 UTF-8 bytes.
- T1 writes to `ff06` and T3 to `fe63`. T2 has no name characteristic of its
  own; when T3 or T1 is also present, the app keeps that name role, and so does
  the integration (T3 first).

#### Evidence

Sleep Smart sends only its frozen frames. APK Protocol Audit row053 records the
dispositions, exclusions and deferred hardware checks.

## Notes

### Analysis provenance

- The machine-local audit ledgers hold the evidence and dispositions; this guide
  holds the results in reference form: Comfort Motion (row115), ERGOBALANCE and
  Dream Motion (cluster-004), Dream Motion HD (row105), MOTIONrelax phone and
  tablet (cluster-006) and Sleep Smart (row053).
- Packages: `com.jiecang.app.android.jiecangbed` 2.2.1 (28),
  `com.jiecang.dreamask.app.android.bed` 1.0.8 (8),
  `com.jiecang.dreamotion.app.android.bed` 1.0.5 (11) and
  `com.dreamhd.jiecang.android.pad.bed` 1.0.4 (4); LOGICDATA
  `com.logicdata.app.android.bed` 1.0.6 (7), `com.logicdata.app.android.pad.bed`
  1.0.4 (5) and `com.logicdata.app.mattress.bed` 1.0.0 (1). No raw APK or frozen
  analysis is shipped with the integration; accepted frozen reports remain
  unchanged.
- Physical actuator mapping, GATT properties and behavior on real firmware remain
  deferred validation for users after a beta or release.
