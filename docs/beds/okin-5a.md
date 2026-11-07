# Okin 5A

**Status:** ✅ Tested on the Sealy Posturematic CB35 profile; the other profiles need testing

**Credit:** Reverse engineering by [MaximumWorf](https://github.com/MaximumWorf) ([homeassistant-nectar](https://github.com/MaximumWorf/homeassistant-nectar)), [David Delahoz](https://github.com/daviddelahoz) ([BLEAdjustableBase](https://github.com/daviddelahoz/BLEAdjustableBase)) and [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

One wire codec (`5A 01 03 10 page key A5` key frames over two GATT transports)
serves four profiles: legacy seven-byte Nectar beds, Mattress Firm 900 / iFlex
Nordic UART bases, Sealy Posturematic CB35 beds and the DewertOkin ELEVATE lift
accessory. The codec also builds the other StarCode frames that standalone
StarCode controllers send (see [StarCode frames](#starcode-frames)). This guide
covers the codec first, then one section per profile. See
[Protocol codecs and app profiles](../design/protocol-codecs.md) for the
architecture.

> [!NOTE]
> Two newer apps that share these names use a different wire format. The
> Nectar Motion app is the explicit **Nectar Move** profile of
> [Okin CST](okin-nframe.md#okin-cst), and beds using the official MFirm 900-O app
> (`com.okin.bedding.rizemf900`) and advertising as `OKIN-XXXXXX` are
> [Okin CST](okin-nframe.md#okin-cst) too. Neither is selected by an `OKIN-*` name, a
> shared OKIN UUID or a Device Information value.

## Known Models

- Nectar Split King Luxe Adjustable Foundation and other Nectar adjustable bases
- Other beds using Okin controllers with the seven-byte command format
- Mattress Firm 900 Adjustable Base (iFlex) and iFlex-branded adjustable beds
- Sealy Posturematic (Element, Ascent, Apex), Bluetooth name starting with
  `Star35` (for example `Star352201011800`); see [Name encoding](#name-encoding)
- DewertOkin ELEVATE two-actuator lift accessory, advertising as `ELEVATE*`,
  used with Adjustable Comfort M1X12 and [AdjustableM5X5](starcode-m5x5.md) systems
- DewertOkin BOX25 Star beds (Sleepy's Elite) send the same key frame; see
  [StarCode frames](#starcode-frames)

Some Nectar Motion bases use the [Okin CST](okin-nframe.md#okin-cst) 14-byte protocol instead
of this one (see [Nectar](#nectar)).

## Apps

| Analyzed | App | Package ID | Profile |
|----------|-----|------------|---------|
| ⬜ | Nectar Adjustable | (no longer available) | [Nectar](#nectar) |
| ✅ | Nectar Motion / Nectar Move | `com.okin.bedding.nectarmotion` | Not this codec: select [Nectar Move](okin-nframe.md#nectar-move-profile) under Okin CST |
| See [Okin CST](okin-nframe.md#okin-cst) | Mattress Firm 900 - O / MFirm 900-O | `com.okin.bedding.rizemf900` | Not this codec: [Okin CST](okin-nframe.md#okin-cst) |
| ✅ | [Sealy Posturematic](https://play.google.com/store/apps/details?id=com.okin.sealy) v1.1.1 | `com.okin.sealy` | [Sealy Posturematic (CB35)](#sealy-posturematic-cb35) |
| ✅ | [Adjustable Comfort M1X12](https://play.google.com/store/apps/details?id=com.starcode.adjustablem1x12) 1.1.3 | `com.starcode.adjustablem1x12` | [DewertOkin ELEVATE](#dewertokin-elevate) |
| ✅ | [AdjustableM5X5](https://play.google.com/store/apps/details?id=com.starcode.abm5_5) 1.2.3 | `com.starcode.abm5_5` | [DewertOkin ELEVATE](#dewertokin-elevate) |

## Features

| Feature | Nectar | Mattress Firm 900 / iFlex | Sealy Posturematic (CB35) | DewertOkin ELEVATE |
|---------|--------|---------------------------|---------------------------|--------------------|
| Motor Control | ✅ Head, Feet, Lumbar | ✅ Head, Foot, Lumbar | ✅ Head, Foot, Lumbar, Neck, Hips (Hips is the Head End Tilt cover) | ✅ Actuator 1, actuator 2 and both together |
| Position Feedback | ❌ | ❌ | ❌ | ❌ (no semantic notification parser in the apps) |
| Presets | ✅ Flat, Zero-G, Anti-Snore, Lounge; TV sends the Lounge key | ✅ Flat, Zero-G, Anti-Snore, Lounge, Incline; TV sends the Lounge key | ✅ Flat, Zero G, Anti-Snore, Lounge, Incline, TV | ✅ Flat (one-shot) |
| Memory Presets | ⚠️ Recall of slots 1-2 only, no programming | ❌ (built-in presets instead) | ⚠️ Recall of Memory 1 and 2; no programming over BLE | ❌ |
| Massage | ✅ Global on, wave and off; no intensity commands | ✅ On, toggle, wave, off, intensity up/down | ✅ Toggle, head/foot strength, mode step, stop | ❌ |
| Under-bed Lights | ✅ Separate on/off | ✅ On/off, light-cycle button | ✅ On/off, light-cycle button | ❌ |
| Group control with M5X5 / M1X12 mains | ❌ | ❌ | ❌ | ✅ (see [AdjustableM5X5 lifts](#adjustablem5x5-lifts)) |
| Hold until release | ❌ (finite pulses) | ❌ (finite pulses) | ❌ (finite pulses) | ✅ (renewable `timed_move`, both routes) |
| BLE Pairing / Authentication | ❌ Not required | ❌ Not required | ❌ Not required | ❌ Not required |
| Hardware-confirmed | No | No | Motors, Flat, Memory 1, Zero G, Stop and the under-bed light | No |

## Choosing a profile

Each profile is its own bed type; there is no app choice inside a bed type.
Detection suggests the profile from the name and service (see each profile's
Setup). `nectar` and `mattressfirm` are kept bed types that build the same
controller over the same profile as `okin_7byte` and `okin_nordic`; their
entries, entities and unique IDs are unchanged.

The tables below come from the profile data.

<!-- generated:okin-5a-profiles -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

### Profile summary

| Profile | Bed types | Transport | Writes | Wake, once per session |
|---|---|---|---|---|
| Nectar | `okin_7byte`, `nectar` | Okin | without response | none |
| Mattress Firm 900 / iFlex | `okin_nordic`, `mattressfirm` | Nordic UART | with response | `09 05 0A 23 05 00 00`, `5A 0B 00 A5` (with response) |
| Sealy Posturematic (CB35) | `okin_cb35` | Nordic UART | without response | `5A 0B 00 A5` |
| DewertOkin ELEVATE | `star_elevate` | Nordic UART | without response | `5A 0B 00 A5` |

### Timing

Motor movement repeats at the entry's motor pulse count and delay, then sends
STOP. Massage and light commands are single writes unless listed here.

| Profile | Presets and memory recall | STOP | Light off |
|---|---|---|---|
| Nectar | 100 × 300 ms | once | once |
| Mattress Firm 900 / iFlex | 100 × 300 ms | once | 3 × 100 ms |
| Sealy Posturematic (CB35) | 2 × 300 ms | 3 × 300 ms | 3 × 100 ms |
| DewertOkin ELEVATE | once | once | n/a |
<!-- /generated -->

### Aliases

Bed types that build the same controller over the same profile with the same
default timing, so they send identical bytes. They stay separate bed types so
existing entries keep their identities; the
[protocol inventory](../design/protocol-inventory.md) proves the equality by capture.

| Bed type | Same as | Profile |
|----------|---------|---------|
| `nectar` | `okin_7byte` | [Nectar](#nectar) |
| `mattressfirm` | `okin_nordic` | [Mattress Firm 900 / iFlex](#mattress-firm-900--iflex) |

`nectar` and `mattressfirm` are kept for existing entries and are not offered in
the bed-type list.

Each also keeps its own [profile id](../design/profile-id.md#aliases): besides
the bed-type list, the device manufacturer differs ("Nectar" and "MattressFirm"
against "Okin").

## Wire codec

Implemented once in `custom_components/adjustable_bed/codec/okin_5a.py`. Profiles
(`profiles/okin_5a.py`) decide which keys a bed sends, over which transport and
with which timing.

### Transports

<!-- generated:okin-5a-transports -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Transport | Service | Write | Notify | Profiles |
|---|---|---|---|---|
| Okin | `62741523-52f9-8864-b1ab-3b3a8d65950b` | `62741525-52f9-8864-b1ab-3b3a8d65950b` | `62741625-52f9-8864-b1ab-3b3a8d65950b` | Nectar |
| Nordic UART | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | Mattress Firm 900 / iFlex, Sealy Posturematic (CB35), DewertOkin ELEVATE |
<!-- /generated -->

The Okin transport's notify characteristic is unused: no profile on it
subscribes.

> [!NOTE]
> Nectar beds share the OKIN service UUID with Okimat but use this seven-byte
> format, not Okimat's six-byte format. The commands are not interchangeable: if
> your bed is detected as the wrong type, change it in integration settings.

### Framing and checksum

Every frame starts with `5A`, ends with `A5` and carries no checksum. Profiles
send one frame shape, the key frame:

```text
5A 01 03 10 [page] [key] A5
```

- Seven bytes. It is the normal frame `5A 01 [32-bit word] A5` of the word
  `03 10 [page] [key]`.
- Page `30` holds the normal keys. Page `40` carries the Mattress Firm 900
  massage intensity keys; the CB35 sends its intensity keys on page `30`.

Two connection frames do not follow the key frame. A profile sends its frames
once per session, before its first command:

<!-- generated:okin-5a-connection -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Frame | Bytes (hex) | Sent by |
|---|---|---|
| Mattress Firm handshake | `09 05 0A 23 05 00 00` | Mattress Firm 900 / iFlex (1 of 2) |
| Wake / keep connected | `5A 0B 00 A5` | Mattress Firm 900 / iFlex (2 of 2), Sealy Posturematic (CB35), DewertOkin ELEVATE |
<!-- /generated -->

### Command encoders

Every action is one key frame. `n/a` marks an action the profile never sends.

#### Motors and STOP

<!-- generated:okin-5a-motors -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Command | Nectar | Mattress Firm 900 / iFlex | Sealy Posturematic (CB35) | DewertOkin ELEVATE |
|---|---|---|---|---|
| Head up (ELEVATE actuator 1 up) | `5A 01 03 10 30 00 A5` | `5A 01 03 10 30 00 A5` | `5A 01 03 10 30 00 A5` | `5A 01 03 10 30 40 A5` |
| Head down (ELEVATE actuator 1 down) | `5A 01 03 10 30 01 A5` | `5A 01 03 10 30 01 A5` | `5A 01 03 10 30 01 A5` | `5A 01 03 10 30 41 A5` |
| Foot up (ELEVATE actuator 2 up) | `5A 01 03 10 30 02 A5` | `5A 01 03 10 30 02 A5` | `5A 01 03 10 30 02 A5` | `5A 01 03 10 30 42 A5` |
| Foot down (ELEVATE actuator 2 down) | `5A 01 03 10 30 03 A5` | `5A 01 03 10 30 03 A5` | `5A 01 03 10 30 03 A5` | `5A 01 03 10 30 43 A5` |
| Lumbar up | `5A 01 03 10 30 04 A5` | `5A 01 03 10 30 06 A5` | `5A 01 03 10 30 06 A5` | n/a |
| Lumbar down | `5A 01 03 10 30 07 A5` | `5A 01 03 10 30 07 A5` | `5A 01 03 10 30 07 A5` | n/a |
| Neck up | n/a | n/a | `5A 01 03 10 30 0A A5` | n/a |
| Neck down | n/a | n/a | `5A 01 03 10 30 0B A5` | n/a |
| Hips up (Head End Tilt cover) | n/a | n/a | `5A 01 03 10 30 08 A5` | n/a |
| Hips down (Head End Tilt cover) | n/a | n/a | `5A 01 03 10 30 09 A5` | n/a |
| Both actuators up | n/a | n/a | n/a | `5A 01 03 10 30 44 A5` |
| Both actuators down | n/a | n/a | n/a | `5A 01 03 10 30 45 A5` |
| STOP | `5A 01 03 10 30 0F A5` | `5A 01 03 10 30 0F A5` | `5A 01 03 10 30 0F A5` | `5A 01 03 10 30 0F A5` |
| Group interrupt | n/a | n/a | n/a | `5A 01 03 10 30 4F A5` |
<!-- /generated -->

#### Presets and memory

<!-- generated:okin-5a-presets -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Command | Nectar | Mattress Firm 900 / iFlex | Sealy Posturematic (CB35) | DewertOkin ELEVATE |
|---|---|---|---|---|
| Flat | `5A 01 03 10 30 10 A5` | `5A 01 03 10 30 10 A5` | `5A 01 03 10 30 10 A5` | `5A 01 03 10 30 46 A5` |
| Zero-G | `5A 01 03 10 30 13 A5` | `5A 01 03 10 30 13 A5` | `5A 01 03 10 30 13 A5` | n/a |
| Anti-Snore | `5A 01 03 10 30 16 A5` | `5A 01 03 10 30 16 A5` | `5A 01 03 10 30 16 A5` | n/a |
| Lounge | `5A 01 03 10 30 11 A5` | `5A 01 03 10 30 17 A5` | `5A 01 03 10 30 17 A5` | n/a |
| TV | `5A 01 03 10 30 11 A5` | `5A 01 03 10 30 17 A5` | `5A 01 03 10 30 11 A5` | n/a |
| Incline | n/a | `5A 01 03 10 30 18 A5` | `5A 01 03 10 30 18 A5` | n/a |
| Memory 1 recall | `5A 01 03 10 30 1A A5` | n/a | `5A 01 03 10 30 1A A5` | n/a |
| Memory 2 recall | `5A 01 03 10 30 1B A5` | n/a | `5A 01 03 10 30 1B A5` | n/a |
<!-- /generated -->

#### Massage

<!-- generated:okin-5a-massage -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Command | Nectar | Mattress Firm 900 / iFlex | Sealy Posturematic (CB35) | DewertOkin ELEVATE |
|---|---|---|---|---|
| Massage toggle (also head and foot toggles) | `5A 01 03 10 30 58 A5` | `5A 01 03 10 30 5A A5` | `5A 01 03 10 30 5A A5` | n/a |
| Massage on | `5A 01 03 10 30 58 A5` | `5A 01 03 10 30 52 A5` | `5A 01 03 10 30 52 A5` | n/a |
| Massage off | `5A 01 03 10 30 5A A5` | `5A 01 03 10 30 6F A5` | `5A 01 03 10 30 6F A5` | n/a |
| Massage mode step (wave) | `5A 01 03 10 30 59 A5` | `5A 01 03 10 30 59 A5` | `5A 01 03 10 30 59 A5` | n/a |
| Massage intensity up | n/a | `5A 01 03 10 40 60 A5` | `5A 01 03 10 30 60 A5` | n/a |
| Massage intensity down | n/a | `5A 01 03 10 40 63 A5` | `5A 01 03 10 30 61 A5` | n/a |
| Head massage strength up | n/a | n/a | `5A 01 03 10 30 60 A5` | n/a |
| Head massage strength down | n/a | n/a | `5A 01 03 10 30 61 A5` | n/a |
| Foot massage strength up | n/a | n/a | `5A 01 03 10 30 62 A5` | n/a |
| Foot massage strength down | n/a | n/a | `5A 01 03 10 30 63 A5` | n/a |
<!-- /generated -->

#### Lights

<!-- generated:okin-5a-lights -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Command | Nectar | Mattress Firm 900 / iFlex | Sealy Posturematic (CB35) | DewertOkin ELEVATE |
|---|---|---|---|---|
| Light on | `5A 01 03 10 30 73 A5` | `5A 01 03 10 30 73 A5` | `5A 01 03 10 30 73 A5` | n/a |
| Light off | `5A 01 03 10 30 74 A5` | `5A 01 03 10 30 74 A5` | `5A 01 03 10 30 74 A5` | n/a |
| Light toggle (controller method; HA hides the button) | `5A 01 03 10 30 71 A5` | `5A 01 03 10 30 71 A5` | `5A 01 03 10 30 71 A5` | n/a |
| Light brightness up (controller method, no entity) | n/a | n/a | `5A 01 03 10 30 80 A5` | n/a |
| Light brightness down (controller method, no entity) | n/a | n/a | `5A 01 03 10 30 81 A5` | n/a |
| Light color change (controller method, no entity) | n/a | n/a | `5A 01 03 10 30 70 A5` | n/a |
<!-- /generated -->

#### StarCode frames

Of these frames, profiles send only the key frame (a normal frame) and the wake
request. The codec builds all of them for the standalone StarCode controllers:

<!-- generated:okin-5a-starcode -->
<!-- Generated by scripts/generate_codec_docs.py from the codec and profile data. Edit those, not this block. -->

| Frame | Layout | Example |
|---|---|---|
| Normal | `5A 01 [32-bit word, big-endian] A5` | `5A 01 00 00 08 00 A5` |
| Setting | `5A E0 04 [parameter] [value] [value 2] [value 3] A5` | `5A E0 04 06 03 03 00 A5` |
| Position target | `5A F0 03 [axis] [target] 00 A5` | `5A F0 03 02 32 00 A5` |
| Request | `5A [code] 00 A5` | `5A B0 00 A5` |
| Clock | `5A 14 07 [seven field bytes] A5` | `5A 14 07 1A 07 10 0D 2D 1E 04 A5` |
<!-- /generated -->

- [SleepSpa S9000AI (SLEEPSTAR)](sleepstar.md) sends every StarCode frame inside
  its CB37 transparent envelope.
- [Adjustable Comfort M1X12](starcode-m1x12.md) and
  [AdjustableM5X5](starcode-m5x5.md) send them in their StarCode dialect, which
  the Device Information manufacturer selects. AdjustableM5X5 sends no position
  target.
- The `box25_star` route of `sleepys_box25` and the `BOX25_STAR` selector of the
  [Sleepy's Elite app profile](sleepys.md#explicit-sleepys-elite-app-profile)
  send all but the clock over Nordic UART; see the
  [BOX25 protocol](sleepys.md#box25-protocol-nordic-uart).

Which words, parameters, axes, request codes and clock field order each one
sends is in its own guide.

### Responses

| Profile | Parser |
|---------|--------|
| Nectar, Mattress Firm 900 / iFlex | None: no subscription |
| Sealy Posturematic (CB35) | Subscribes to the Nordic UART notify characteristic. Massage status frames start with `A5 0B` (8 bytes or longer); they are logged and captured for diagnostics but not parsed into entities |
| DewertOkin ELEVATE | Subscribes and forwards raw notifications; the analyzed apps assign them no semantic fields |

### STOP and release behavior

- Motor movement repeats its key, then sends STOP. The cleanup STOP uses a fresh
  cancel event so a pending stop request cannot suppress it.
- Presets and memory recall repeat their key, then send STOP; ELEVATE flat sends
  no STOP. Repeat counts are in the [timing table](#choosing-a-profile).
- The CB35 also releases presets with its STOP burst, and taps a motor key before
  STOP while a preset may still be moving; see
  [its Timing](#sealy-posturematic-cb35).

### Vectors

`tests/okin_5a_vectors.py` freezes every frame each profile sends, and
`tests/test_okin_5a_vectors.py` checks each literal against the codec and each
profile's frames against its vectors. `tests/test_codec_docs.py` checks every
frame spelled in this guide against the vectors and each bed type against the
factory. Each profile's vectors are
the frames its pre-v5 controller sent. No accepted APK report covers the Nectar,
Mattress Firm and CB35 key frames; ELEVATE's frames match its APK reports (see
its [Evidence](#dewertokin-elevate)). The same file freezes every StarCode frame
in the standalone StarCode controllers' artifact vectors, by encoder, and the
same test rebuilds each one from its fields.

## Profiles

### Nectar

**Status:** ❓ Needs testing (legacy seven-byte protocol)

These details apply only to the legacy seven-byte profile. The
[Nectar Move profile](okin-nframe.md#nectar-move-profile) uses the separate Okin CST
framing and actions. Do not interchange the command sets.

#### Setup

- The legacy protocol may be detected by a device name containing `nectar`
  (case-insensitive) with the Okin service UUID. That signal does not identify
  the Nectar Move app profile.
- Some Nectar bases advertise only as `OKIN-XXXXXX`. Those names are ambiguous
  with classic Okimat, seven-byte Nectar and newer CST controllers, so setup
  prompts for the Okin-family protocol. Choose `Nectar` only for the seven-byte
  protocol.
- Select **Nectar Move** explicitly when setting up that app profile; shared
  advertisements and Device Information are not sufficient to choose it.
- The `62741523-...` OKIN service, `90311623-...` CSS service, and Nordic DFU
  service `00001530-...` are not sufficient by themselves to identify CST
  because RF ECO BT stair actuators share that GATT inventory. Choose the
  **Okin CST** row, which names its apps, only when the known base or app
  identity also corroborates CST. Device Information model `MEGAMAT MBZ`
  identifies RF ECO BT instead.
- Or configure bed type `nectar` manually (a legacy alias of the `okin_7byte`
  profile).
- No Bluetooth pairing is required.

#### Controls

- Massage control is global (no separate head/foot control): the massage, head
  and foot toggles all send Massage on. There are no intensity commands.
- Lights have separate on/off commands; HA hides the toggle button because
  discrete on/off exists.
- Memory 1 and 2 recall only; memory programming is not supported.

> [!NOTE]
> Earlier versions of the Nectar page listed no memory presets, no TV preset and
> no light toggle. The controller sends Memory 1/2 recall (`1A`/`1B`), TV with the
> Lounge key (`11`) and a light toggle (`71`). Those keys were absent from the
> earlier documented command list and are unverified on hardware.

#### Timing

See the [timing table](#choosing-a-profile).

#### Evidence

No discovery ledger: no accepted APK report covers this profile. Nectar sends
only its frozen frames, the ones the pre-v5 controller sent, from MaximumWorf's
[homeassistant-nectar](https://github.com/MaximumWorf/homeassistant-nectar).

### Mattress Firm 900 / iFlex

**Status:** ❓ Needs testing

#### Setup

- Use this profile for iFlex / Nordic UART bases only. It uses the Nordic UART
  service rather than the OKIN service, so it is not confused with other Okin
  beds during auto-detection.
- Detection: a device name starting with `iflex` (case-insensitive), or
  configure bed type `mattressfirm` manually.
- Initialization: the two connection frames in the
  [connection table](#framing-and-checksum), in that order, each followed by
  100 ms; the [profile summary](#choosing-a-profile) gives the write mode.

#### Controls

- There are no user-programmable memory positions. Instead the bed has five
  built-in presets: Flat, Zero-G, Anti-Snore, Lounge and Incline. The TV preset
  sends the Lounge key.
- Massage on sends massage level 1 (`52`); the toggle sends `5A`.
- Lumbar control is exposed as a separate Cover entity.
- The light-cycle button sends Light on.

Earlier documentation listed keys this profile does not send: massage level 2
(`53`), massage level 3 (`54`) and a light cycle (`70`) described as stepping
through brightness levels.

#### Timing

See the [timing table](#choosing-a-profile). From the earlier app disassembly
analysis, the app repeats a held button every 100 ms and sends stop twice (at
100 ms and 200 ms) after release.

#### Evidence

No discovery ledger: the accepted MFirm 900 1.1.2 report
(`com.okin.bedding.rizemf900`) reaches only the Okin CST frame. That app uses a
14-byte CST format (`[0x0C, 0x02, motor_bytes(4), control_bytes(4), reserved(4)]`)
and detects devices by the name prefix `okin` (case-insensitive); see
[Okin CST](okin-nframe.md#okin-cst). This profile sends only its frozen frames, the ones the
pre-v5 controller sent. The protocol was manually reverse-engineered by David
Delahoz in 2020 from the M900 app, with discovery from Zrau5454 in
[#50](https://github.com/kristofferR/ha-adjustable-bed/issues/50).

### Sealy Posturematic (CB35)

**App:** [Sealy Posturematic](https://play.google.com/store/apps/details?id=com.okin.sealy) v1.1.1, `com.okin.sealy`

**Status:** ✅ Tested (Sealy Element, ESPHome Bluetooth proxy, 2026-09)

Protocol version CB.35.22.01 ("star code new protocol"). The Android app is a
Flutter app with the protocol defined in a JSON asset; it is also on iOS (App
Store), developed by Star Seeds Co LTD (DewertOkin).

#### Setup

- Detection: a `Star35*` name with Nordic UART; see [Name encoding](#name-encoding).
- Initialization: only the wake frame, followed by 100 ms; no Mattress Firm
  handshake. CB35 requires write without response (see the
  [profile summary](#choosing-a-profile)).
- The bed accepts only one BLE connection. While the Sealy app is open on a phone
  (including in the background) the bed stops advertising and the integration
  cannot connect.

##### Name encoding

| Signal | Value |
|--------|-------|
| Device name | Starts with `Star` (e.g., `Star352201011800`) |
| Name digits 4-5 | `35` distinguishes CB35 from BOX25 (`25`) |
| Service UUID | Nordic UART `6E400001-B5A3-F393-E0A9-E50E24DCCA9E` |
| Manufacturer ID | 89 (OKIN) |
| Manufacturer Name (2A29) | `STAR` selects StarCode framing but is shared with BOX25 |

DewertOkin Star device names encode the protocol version: `Star` +
`[protocol digits]` + `[serial]`.

| Name | Digits 4-5 | Protocol | Bed Type |
|------|-----------|----------|----------|
| `Star352201011800` | `35` | CB.35.22.01 | CB35 (this profile) |
| `Star254202079996` | `25` | 25_42_02 | BOX25 (Sleepy's Elite) |

Both confirmed `Star25...` BOX25 devices from issues #372 and #413 return `STAR`
from Device Information characteristic `2A29`. The Adjustable Comfort M1X12 app
uses this value to choose StarCode command framing within its CB25 device
implementation; it does not prove the device is CB35. The integration therefore
uses the `25`/`35` digits in the advertised name and never rewrites a
high-confidence `Star25...` detection from the manufacturer string alone.

#### Controls

- Extra motors: neck and hips (the Head End Tilt cover).
- Separate head and foot massage strength; overall intensity sends the head keys.
- Light brightness and color are controller methods without entities.
- Massage on (Massage Open) is a controller method without an HA entity; the
  massage, head and foot toggles send the toggle key.
- The light-cycle button sends Light on.
- App protocol keys this profile does not send: head+foot up/down (`0C`/`0D`),
  the Read, Inverse, Work and Extension presets (`12`, `14`, `15`, `19`), wave up
  (`58`) and massage time switch (`6D`).

#### Timing

App timing: motor commands repeat every 300 ms while held; stop and massage
commands send 3 times (initial + 2 repeats at 300 ms). The integration's preset
and STOP repeats are in the [timing table](#choosing-a-profile).

A preset key on its own only *arms* the bed. The STOP burst is what commits the
move:

| Sent | Result on the bed |
|------|-------------------|
| Preset key x100 at 300 ms, then one STOP (the Nectar and Mattress Firm timing) | Bed sits armed for ~20 s, then moves |
| Preset key once, no STOP | Bed sits armed until the link drops, then moves |
| The profile's preset and STOP repeats from the [timing table](#choosing-a-profile) | Bed starts within a second (implemented) |

A preset that is already driving **ignores STOP** (three STOP x3 bursts during a
Flat had no effect). Any motor key interrupts it, the same as pressing a button
on the handset, so `stop_all` sends one motor-key packet (Head up) before STOP
while a preset may still be in flight. Motor holds stop with STOP alone.

The interrupt window:

- Lasts 45 seconds after the last successfully transmitted preset packet, based
  on the reporter's approximately 30-second full travel.
- A successful motor-key write clears this window, even if later repeats are
  cancelled or fail. Cancellation during wake-up does not count as a
  transmitted movement command.
- The physical coordinator retains this window across BLE disconnects and
  controller recreation, including the default disconnect-after-command path.
  It is runtime state only, not persisted across integration reloads or Home
  Assistant restarts.
- The window estimates possible motion; it does not confirm that a preset is
  still running. Stop can therefore send the motor-key tap after an early
  completion, and sends STOP alone after the window expires.

The reporter observed no visible idle movement on their Sealy Element; this is
not a verified guarantee for every CB35 model. These timings and physical
observations come from that hardware report, not a newly verified APK analysis.

#### Notifications

See [Responses](#responses).

#### Evidence

No discovery ledger. The profile sends only its frozen frames, the ones the pre-v5
controller sent, from the `com.okin.sealy` v1.1.1 analysis in
[#310](https://github.com/kristofferR/ha-adjustable-bed/issues/310). Complete
protocol definition at
`disassembly/output/com.okin.sealy/extracted/assets/flutter_assets/assets/protocol/35_22_01.json`.

### DewertOkin ELEVATE

**App:** [Adjustable Comfort M1X12](https://play.google.com/store/apps/details?id=com.starcode.adjustablem1x12) 1.1.3, `com.starcode.adjustablem1x12`; [AdjustableM5X5](https://play.google.com/store/apps/details?id=com.starcode.abm5_5) 1.2.3, `com.starcode.abm5_5`

**Status:** ❓ Needs testing (implemented from complete APK evidence, hardware validation pending)

ELEVATE is a separate accessory, not a BOX25 bed variant, even though it uses the
same Nordic UART service and StarCode envelope. It always uses these Star frames;
there is no manufacturer-selected dialect.

#### Setup

- Detection: high-confidence automatic discovery requires the `ELEVATE*` name
  **plus** Nordic UART. Nordic UART by itself is intentionally not treated as a
  bed signature because many unrelated devices use it.
- Adjustable Comfort M1X12 lift groups require the explicit **Adjustable Comfort
  M1X12 ELEVATE** variant of `star_elevate`; see the
  [M1X12 guide](starcode-m1x12.md).
- Session: the analyzed apps enable RX notifications and then send the one-time
  keep-connected (wake) frame.
- Firmware characteristic check: the app's session also refuses a device without
  a readable firmware characteristic before it sends the wake frame. That check
  sends nothing to the device and released ELEVATE entries already work without
  it, so this controller does not add it as a new connection requirement.

#### Controls

- Actuator 1 and actuator 2 use the profile's head and foot rows, and both
  together the both-actuators row.
- Flat is a one-shot with no appended STOP.
- **Multiple devices:** the app uses one or two saved ELEVATE devices by sending
  the same command to each address. That is application-side fan-out, not a side
  selector or split-bed byte in this protocol.

#### Timing

The apps refresh a held command every 100 ms. Release cancels held repeats and
sends the shared STOP frame once.

A renewable hold (`timed_move` with `hold_owner` and `hold_generation`, see
[Renewable holds](../SERVICES.md#renewable-holds)) refreshes at the apps' 100 ms
on both routes, whatever the entry's motor pulse settings, until its lease runs
out. Then STOP follows. A finite move on the default route keeps the entry's
pulse settings; the M1X12 variant always holds at the 100 ms sender interval.

#### Notifications

The apps log and de-duplicate notifications but assign them no semantic ELEVATE
state, so the integration exposes no position feedback; see
[Responses](#responses).

#### Services

##### AdjustableM5X5 lifts

This bed type is the one route for ELEVATE devices, including those used with
the AdjustableM5X5 app. That app's ELEVATE class sends exactly the frames above
(its P3 vectors are tested against this controller), so it is not a separate
profile.

Its app-proven group behavior is carried over:

- Select an ELEVATE entry as a lift on an [AdjustableM5X5](starcode-m5x5.md)
  main. An ELEVATE can also be the main and select up to three lifts in its own
  options, matching the app's restored main slot.
- `adjustable_bed.starcode_move_lifts` drives ELEVATE lifts with both-actuator
  up/down, one-shot flat and STOP. Before a group moves, each member receives
  the group interrupt frame.
- Ordinary ELEVATE movement or flat interrupts the rest of its group first.

#### Evidence

The AdjustableM5X5 (row005) and M1X12 audits cover the frozen COMPLETE reports for `com.starcode.adjustablem1x12` 1.1.3 and
`com.starcode.abm5_5` 1.2.3. ELEVATE sends only its frozen frames. Command
direction and multi-device fan-out await real-hardware checks.

## Notes

- Nectar and Mattress Firm 900 are part of the
  [Okin Protocol Family](../SUPPORTED_ACTUATORS.md#okin-protocol-family).
- Generic `OKIN-XXXXXX` names require user confirmation because several Okin
  protocols share the same advertised UUID.

### Analysis provenance

- **Nectar:** MaximumWorf's
  [homeassistant-nectar](https://github.com/MaximumWorf/homeassistant-nectar).
- **Mattress Firm 900 / iFlex:** discovery from Zrau5454 in
  [#50](https://github.com/kristofferR/ha-adjustable-bed/issues/50), and David
  Delahoz's BLEAdjustableBase.
- **CB35:** [#310](https://github.com/kristofferR/ha-adjustable-bed/issues/310),
  extracted from `com.okin.sealy` v1.1.1.
- **ELEVATE:** the frozen COMPLETE APK Protocol Audit reports for
  `com.starcode.adjustablem1x12` 1.1.3 and `com.starcode.abm5_5` 1.2.3.
