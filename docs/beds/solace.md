# Solace / QMS 11-byte protocol

**Status:** ⚠️ Partially tested (static analysis complete; the legacy S4-Y motor layout is user-confirmed; accepted APK routes await post-release validation)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), Bonopaws and [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt)

This controller covers a family of beds that write fixed 11-byte frames to FFE1.
The apps overlap but do not expose one universal feature set, so the integration
selects a conservative capability profile from the observed BLE name. Protocol
variant `woosa` is the explicit Woosa Sleep app profile; the
[Woosa profile](woosa.md) documents its distinct commands and behavior.

## Known Models

- Solace hospital/care beds and some medical adjustable beds
- Sealy adjustable bases (MotionFlex, `SealyMF*` names)
- Woosa Sleep adjustable bases (explicit [Woosa profile](woosa.md))
- QMS-series beds (QMS-IQ, QMS-I06, QMS-LQ, QMS-L04, QMS-JQ-D, QMS-NQ, QMS-MQ, QMS2, QMS3, QMS4, etc.)
- S-series beds (S3-2, S3-3, S3-4, S4-N, S4-Y, S5-Y, S6-Y)
- Names documented before the profile split but no longer auto-detected as
  Solace: QMS-I16, QMS-I26, QMS-KQ-H, QMS-DFQ, QMS-DQ and every S-series name
  except the exact `S4-Y-<digits>-<id>` form. The separate
  [Motion Bed app](motion_bed.md) profile accepts these names.

## Apps

| Analyzed | App | Package ID | APK Protocol Audit result |
|----------|-----|------------|---------------------------|
| ✅ | [HomeKobo](https://play.google.com/store/apps/details?id=com.ly.homekobo) 1.4 | `com.ly.homekobo` | COMPLETE |
| ✅ | [Sealy MotionFlex](https://play.google.com/store/apps/details?id=com.sealy.motionflex) 1.0.3 | `com.sealy.motionflex` | COMPLETE |
| ✅ | [Sweet Night](https://play.google.com/store/apps/details?id=com.sn.dianqi) 1.0.6 | `com.sn.dianqi` | COMPLETE, FULL comparison |
| ✅ | [Motion Bed](https://play.google.com/store/apps/details?id=com.sn.blackdianqi) 1.24 | `com.sn.blackdianqi` | Pending for Solace routing; accepted separately for the [Motion Bed app](motion_bed.md) profile |
| ✅ | [Woosa Sleep](https://play.google.com/store/apps/details?id=com.sn.woosa) 1.1.9 | `com.sn.woosa` | COMPLETE, explicit [Woosa profile](woosa.md) |

- **Static analysis:** Complete. **Hardware validation:** Partial (see Status).
- The accepted reports prove application behavior exhaustively. Physical
  behavior that cannot be established statically remains explicitly
  hardware-unverified.
- Motion Bed and Woosa Sleep are by the same developer (Zhejiang Tri Mix
  Technology / `com.sn` prefix) and share this 11-byte frame family.
- The Motion Bed report has since been accepted for the separate
  [Motion Bed app](motion_bed.md) profile. Solace routing does not use it.

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Back and legs on every route; head plus hip (K1) or lumbar (K2) on Home profiles; bed height and tilt on exact S4-Y |
| Hip Motor | ⚠️ Model-specific (not all beds have this; Home K1 only) |
| Position Feedback | ❌ (preset-state replies are not positions) |
| Memory Presets | ✅ (2 numbered slots; Woosa has 1 Favourite slot) |
| Flat / Zero-G / Anti-Snore / TV | ✅ (every identified route) |
| Relaxing bedtime | ✅ (MotionFlex only) |
| Yoga | ❌ (withheld) |
| Massage | ⚠️ Home profiles only (zones, wave, circulation modes on K1, timers) |
| Lights | ⚠️ MotionFlex: 11 brightness levels (0-10) + timers; HomeKobo/Sweet Night: timers only |
| Audio, clock and alarm | ⚠️ MotionFlex (alarm also on Woosa) |

## Protocol Details

**Service UUID:** `0000ffe0-0000-1000-8000-00805f9b34fb` (commonly advertised, but not required: the apps traverse every discovered service)
**Write/Notify Characteristic:** `0000ffe1-0000-1000-8000-00805f9b34fb`
**CCCD:** `00002902-0000-1000-8000-00805f9b34fb`, enabled with `01 00`
**Format:** 11-byte fixed packets with CRC-16/MODBUS (bytes 9-10, little-endian, computed over bytes 0-8)

### BLE session

- Apps scan without a UUID filter and select devices by case-sensitive
  local-name substrings.
- No fixed service UUID is required. Every discovered service is traversed.
- Control and notifications use FFE1.
- There is no authentication, bonding requirement, MTU negotiation,
  encryption, retry loop, or protocol command queue in the accepted apps.
- Accepted profiles subscribe to FFE1 even when angle sensing is disabled,
  because preset and accessory state arrive there. The exact S4-Y legacy
  profile is excluded because no accepted query family applies to it.

### Packet Format

```text
FF FF FF FF 05 00 00 <mode> <selector> <crc-low> <crc-high>
```

- The checksum is CRC-16/MODBUS over bytes 0-8: initial value `0xFFFF`,
  reflected polynomial `0xA001`, low byte first.
- The accepted apps decode fixed hexadecimal strings rather than constructing
  these CRCs at runtime.
- Auxiliary frames (sync, clock, alarm, audio; type `01`) use an additive
  checksum instead: the unpadded little-endian byte sum is appended.
- Query frames use type `03`.

## Detection / Setup

Auto-discovery is limited to names beginning with the accepted values below,
plus the accepted `My QMS2` prefix. Matching is case-folded.

| Observed name | Profile | Motors | Accessories | Status query |
|---|---|---|---|---|
| `QMS-IQ`, `QMS-I06`, `QMS-LQ`, `QMS-L04`, `QMS-NQ`, `QMS3` | Home K1 | Back, head, legs, hip | Two memories, TV/zero-G/anti-snore, massage, massage cycles/timers, light timers | Q1 |
| `QMS-JQ-D`, `QMS4` | Home K2 | Back, head, legs, lumbar | Two memories, TV/zero-G/anti-snore, massage/timers, light timers | Q1 (Q2 for compound Q2 names) |
| `QMS2`, `QMS-MQ` | Common | Back, legs | Two memories, TV/zero-G/anti-snore, light timers | Q2 |
| `SealyMF*` | MotionFlex | Back, legs | Two memories, TV/zero-G/anti-snore, light levels 0-10, light timers | Q2 |
| Exact `S4-Y-<digits>-<id>` | Legacy S4-Y | Back, legs, bed height, tilt | Two memories, TV/zero-G/anti-snore, deployed legacy flat | None |
| Any unidentified manual Solace route | Unverified | Back, legs | No unverified presets or accessories | None |

- `QMS2` and `QMS-MQ` deliberately use the common profile unless the user
  explicitly selects protocol variant `woosa` (Woosa Sleep). HomeKobo and Sweet
  Night both route these names, but only HomeKobo exposes massage. The
  integration does not assume that optional hardware exists.
- A Home K2 name is a compound Q2 name when it also contains `qms-mq`, `qms2`,
  `qms3` or `s3-2`.
- The exact S4-Y route preserves a real user's confirmed four-cover layout and
  the previously deployed legacy all-flat command.
- Broad `QMS*`, arbitrarily prefixed substring, and S3/S4/S5/S6 matching was
  removed. Home Assistant cannot safely index leading-wildcard discovery hints,
  and the broader families include names sourced only from the still-pending
  Motion Bed APK.
- A name merely containing `solace` is not evidence and is not auto-detected.
- An FFE0 advertisement with an unmatched name defaults to Octo, with Solace
  (and MotoSleep, plus Motion Bed for its names) offered as alternatives.
- Existing manual entries with an unidentified name retain basic back/legs
  movement and STOP but do not receive guessed query, preset, massage, or
  lighting commands.

## Commands

Name-selected profiles use the commands below. The explicit
[Woosa profile](woosa.md) differs, including leg down, Love, one numbered
Favourite slot and preset activation timing.

### Motor Control

| Command | Bytes (hex) | Profiles |
|---------|-------------|----------|
| Stop | `FF FF FF FF 05 00 00 00 00 D7 00` | All |
| Back Up | `FF FF FF FF 05 00 00 00 03 97 01` | All |
| Back Down | `FF FF FF FF 05 00 00 00 04 D6 C3` | All |
| Legs Up | `FF FF FF FF 05 00 00 00 06 57 02` | All |
| Legs Down | `FF FF FF FF 05 00 00 00 07 96 C2` | All |
| Head Up | `FF FF FF FF 05 00 00 00 01 16 C0` | Home K1, K2 |
| Head Down | `FF FF FF FF 05 00 00 00 02 56 C1` | Home K1, K2 |
| Hip (K1) / Lumbar (K2) Up | `FF FF FF FF 05 00 00 00 0D 16 C5` | Home K1, K2 |
| Hip (K1) / Lumbar (K2) Down | `FF FF FF FF 05 00 00 00 0E 56 C4` | Home K1, K2 |
| Bed height (Lift) Up | `FF FF FF FF 05 00 00 00 21 17 18` | Legacy S4-Y |
| Bed height (Lift) Down | `FF FF FF FF 05 00 00 00 22 57 19` | Legacy S4-Y |
| Tilt Up | `FF FF FF FF 05 00 00 00 28 D7 1E` | Legacy S4-Y |
| Tilt Down | `FF FF FF FF 05 00 00 00 29 16 DE` | Legacy S4-Y |

### Presets

| Command | Bytes (hex) | Notes |
|---------|-------------|-------|
| Flat | `FF FF FF FF 05 00 00 00 08 D6 C6` | Every identified route except legacy S4-Y |
| All Flat (legacy) | `FF FF FF FF 05 00 00 00 2A 56 DF` | Flat on the exact S4-Y route only |
| TV | `FF FF FF FF 05 00 00 00 05 17 03` | Sent when TV is not reported selected |
| TV (selected branch) | `FF FF FF FF 05 00 00 51 05 2A 93` | Sent when TV is reported selected |
| Zero-G | `FF FF FF FF 05 00 00 00 09 17 06` | Not selected |
| Zero-G (selected branch) | `FF FF FF FF 05 00 00 91 09 7A 96` | Selected |
| Anti-Snore | `FF FF FF FF 05 00 00 00 0F 97 04` | Not selected |
| Anti-Snore (selected branch) | `FF FF FF FF 05 00 00 F1 0F D2 94` | Selected |
| Relaxing bedtime | `FF FF FF FF 05 00 00 00 6A 57 2F` | MotionFlex only |

### Memory

Memory frames use mode `A1`/`A0` (slot 1, selector `0A`) and `B1`/`B0` (slot 2,
selector `0B`).

| Command | Bytes (hex) | Notes |
|---------|-------------|-------|
| Memory 1 recall | `FF FF FF FF 05 00 00 A1 0A 2E 97` | |
| Memory 2 recall | `FF FF FF FF 05 00 00 B1 0B E2 97` | |
| Memory 1 save | `FF FF FF FF 05 00 00 A0 0A 2F 07` | Sent when slot 1 is not reported selected |
| Memory 1 save (selected branch) | `FF FF FF FF 05 00 00 AF 0A 2A F7` | Sent when slot 1 is reported selected |
| Memory 2 save | `FF FF FF FF 05 00 00 B0 0B E3 07` | Not selected |
| Memory 2 save (selected branch) | `FF FF FF FF 05 00 00 BF 0B E6 F7` | Selected |

Program frames for the named presets are recognized in replies and command
echoes (see [Preset state](#preset-state)):

| Preset | Program (selected) | Program branch (deselected) |
|--------|--------------------|-----------------------------|
| TV | `FF FF FF FF 05 00 00 50 05 2B 03` | `FF FF FF FF 05 00 00 5F 05 2E F3` |
| Zero-G | `FF FF FF FF 05 00 00 90 09 7B 06` | `FF FF FF FF 05 00 00 9F 09 7E F6` |
| Anti-Snore | `FF FF FF FF 05 00 00 F0 0F D3 04` | `FF FF FF FF 05 00 00 FF 0F D6 F4` |

> [!NOTE]
> Older documentation listed five numbered memory slots and labelled the
> `AF`/`BF` frames "delete". Historical “memory 3-5” frames are actually the
> selected/program branches for TV, zero-G, and anti-snore. The name-selected
> profiles have two numbered memory slots; the explicit Woosa profile has one
> Favourite slot.

Sweet Night's shipped Memory 2 short-press path duplicates Memory 1. The
distinct Memory 2 frame above is independently accepted from HomeKobo and
MotionFlex; Sweet Night runtime validation remains explicitly requested.

### Massage (Home profiles)

Home profiles prove head/upper (app label “Back Mass”), foot/lower (app label
“Leg Mass”), and wave massage step controls, massage stop, 10/20/30-minute
timers, and cycle modes. Opcode direction is:

- Wave minus `15`, plus `14`
- Head/upper minus `11`, plus `10`
- Foot/lower minus `13`, plus `12`

| Command | Bytes (hex) |
|---------|-------------|
| Head Massage + | `FF FF FF FF 05 00 00 00 10 D6 CC` |
| Head Massage - | `FF FF FF FF 05 00 00 00 11 17 0C` |
| Foot Massage + | `FF FF FF FF 05 00 00 00 12 57 0D` |
| Foot Massage - | `FF FF FF FF 05 00 00 00 13 96 CD` |
| Wave (Frequency) + | `FF FF FF FF 05 00 00 00 14 D7 0F` |
| Wave (Frequency) - | `FF FF FF FF 05 00 00 00 15 16 CF` |
| Timer 10 min | `FF FF FF FF 05 00 00 00 16 56 CE` |
| Timer 20 min | `FF FF FF FF 05 00 00 00 17 97 0E` |
| Timer 30 min | `FF FF FF FF 05 00 00 00 18 D7 0A` |
| Stop Massage | `FF FF FF FF 05 00 00 00 1C D6 C9` |

#### Circulation/Loop Modes (Home K1)

| Command | Bytes (hex) |
|---------|-------------|
| Full Body | `FF FF FF FF 05 00 05 00 E4 C7 4A` |
| Head | `FF FF FF FF 05 00 05 00 E3 86 88` |
| Leg | `FF FF FF FF 05 00 05 00 E5 06 8A` |
| Hip | `FF FF FF FF 05 00 05 00 E6 46 8B` |

The K1 fourth cycle zone is hip. K2 uses the same frame for lumbar, so the
generic hip-labeled cycle button is withheld on K2 rather than mislabeled.

### Lights

MotionFlex proves light brightness levels 0-10; level 0 is the accepted off
command. HomeKobo and Sweet Night prove only the 10-minute, 8-hour, and 10-hour
light timer frames, so brightness and an invented timer “Off” option are not
exposed there.

| Command | Bytes (hex) | Profiles |
|---------|-------------|----------|
| Light Level 0 (Off) | `FF FF FF FF 05 00 00 00 23 96 D9` | MotionFlex |
| Light Level 1 | `FF FF FF FF 05 00 00 01 23 97 49` | MotionFlex |
| Light Level 2 | `FF FF FF FF 05 00 00 02 23 97 B9` | MotionFlex |
| Light Level 3 | `FF FF FF FF 05 00 00 03 23 96 29` | MotionFlex |
| Light Level 4 | `FF FF FF FF 05 00 00 04 23 94 19` | MotionFlex |
| Light Level 5 | `FF FF FF FF 05 00 00 05 23 95 89` | MotionFlex |
| Light Level 6 | `FF FF FF FF 05 00 00 06 23 95 79` | MotionFlex |
| Light Level 7 | `FF FF FF FF 05 00 00 07 23 94 E9` | MotionFlex |
| Light Level 8 | `FF FF FF FF 05 00 00 08 23 91 19` | MotionFlex |
| Light Level 9 | `FF FF FF FF 05 00 00 09 23 90 89` | MotionFlex |
| Light Level 10 | `FF FF FF FF 05 00 00 0A 23 90 79` | MotionFlex |
| Light Timer 10 min | `FF FF FF FF 05 00 00 00 19 16 CA` | All except legacy S4-Y and unverified |
| Light Timer 8 hours | `FF FF FF FF 05 00 00 00 1A 56 CB` | All except legacy S4-Y and unverified |
| Light Timer 10 hours | `FF FF FF FF 05 00 00 00 1B 97 0B` | All except legacy S4-Y and unverified |
| Query Light Status | `FF FF FF FF 05 00 05 FF 23 C7 28` | MotionFlex |

### Status queries

| Family | Frames, in send order |
|--------|-----------------------|
| Q1 | `FF FF FF FF 03 00 28 00 09 1F 0E`, `FF FF FF FF 03 00 31 00 09 CE C9`, `FF FF FF FF 03 00 16 00 09 7E C2`, `FF FF FF FF 03 00 1F 00 09 AE C0`, `FF FF FF FF 03 00 3A 00 09 BF 0B` |
| Q2 | `FF FF FF FF 03 00 28 00 03 9F 09`, `FF FF FF FF 03 00 30 00 03 1F 0E`, `FF FF FF FF 03 00 18 00 03 9F 06`, `FF FF FF FF 03 00 20 00 03 1E CB`, `FF FF FF FF 03 00 38 00 03 9E CC` |

### MotionFlex audio, clock, and alarm

The MotionFlex profile exposes its relaxing-bedtime preset and music start/stop
actions as buttons.

- `adjustable_bed.solace_audio` selects or previews tracks 1-5, queries the
  current volume, and sets volume levels 1-5. Audio actions require MotionFlex.
- `adjustable_bed.solace_set_alarm` programs the enabled state, time, weekdays,
  bed action, massage flag, and alarm or music sound. The alarm action also
  supports the explicit [Woosa profile](woosa.md), restricted to its proven
  modes and alarm sound choices.

| Command | Bytes (hex) / builder |
|---------|-----------------------|
| Music toggle (short press) | `FF FF FF FF 01 00 13 0B FF 1A 05` |
| Music off (long press / dialog save) | `FF FF FF FF 01 00 13 0B 00 1B 04` |
| Select track 1-5 | `FF FF FF FF 01 00 13 0B <track>` + additive checksum; preview sets bit `0x80` |
| Set volume 1-5 | `FF FF FF FF 01 00 14 0B <level>` + additive checksum |
| Query volume | `FF FF FF FF 01 00 15 0B 00 1D 04` |
| Clock sync | `FF FF FF FF 01 00 01 11` + BCD hour, minute, second, ISO weekday, year (2 digits), month, day + additive checksum |
| Alarm | `FF FF FF FF 01 00 02 13` + enabled (`01`, or `A1` when disabled), BCD hour, BCD minute, `00`, weekday bit mask, repeat flag, mode, massage flag, sound + additive checksum |

| Alarm field | Values |
|-------------|--------|
| Mode | `zero_g` `01`, `memory_1` `02`, `no_action` `03` |
| Sound | `none` `00`, `alarm` `01`, `music_1`-`music_5` `11`-`15` |

## Preset state

- Q1 and Q2 use different five-command query sets. Queries start after
  notification setup, then use the app-proven pacing: the integration waits
  300 ms, then sends each query 500 ms apart.
- Responses are substring-matched by the accepted apps and identify selected
  state for memory 1, memory 2, TV, zero-G, and anti-snore (reply prefix
  `FF FF FF FF 03 06 00` followed by selector `0A`, `0B`, `05`, `09` or `0F`).
  Program-frame echoes set or clear the same flags.
- The integration records the same controller state for diagnostics without
  treating it as position feedback.
- On MotionFlex notification startup the controller first sends the app's
  local-time clock frame, then runs the Q2 preset queries and brightness query.
  MotionFlex brightness, audio-volume, and alarm replies are decoded into
  controller state.

## Command Timing

- **Motor commands:** one start frame per press; the controller latches the
  motor until STOP. There is no held-command repetition.
- **Stop required:** yes, the global STOP on release.
- Home Assistant cover actions have no matching button-release event, so the
  integration retains a five-second integration safety cap and always sends
  STOP in cleanup; an explicit Stop cancels it immediately.
- For name-selected profiles, Flat and preset actions are single writes without
  a STOP or 200 ms preamble. The explicit Woosa profile follows its separately
  proven STOP and 200 ms preset sequence.

## Notes

### Intentionally withheld behavior

These historical commands remain outside the name-selected profiles. Woosa's
absolute massage selectors `4F`–`56` and light-off selector `4B` are now
supported only by its explicitly selected, independently audited profile:

- Yoga selector `4E` (historical frame `FF FF FF FF 05 00 00 00 4E 57 34`); it
  belongs to an app whose audit is still pending
- Legacy all-flat selector `2A` outside the exact S4-Y compatibility profile
- Five generic numbered memory slots
- Broad S3/S4/S5/S6 detection
- Applying Woosa's STOP + 200 ms preset preamble to other profiles

### Woosa Sleep dual-device detection

A historical user report found that Woosa Sleep beds may advertise **two** BLE
devices:

- `QMS-MQ-*`: the actual bed controller (use this one)
- `ECBLE*`: a secondary BLE module that does not respond to bed commands (at
  the time it was detected as Remacro)

### MotionFlex discovery ledger

Every behavior reachable in the frozen MotionFlex report has one disposition
below. Grouped rows cover commands or notifications that share one reachable
surface and implementation path.

| Reachable discovery | Disposition | Integration reference |
|---|---|---|
| Accepted local-name prefix discovery, including `My QMS2`, and conservative profile routing | IMPLEMENTED | `manifest.json`, `detection.py`, and `resolve_solace_profile()` |
| FFE1 connection, notification/CCCD setup, writes, clean disconnect, and the absence of authentication or bonding | ALREADY_IMPLEMENTED | Coordinator BLE lifecycle plus `SolaceController` transport tests |
| Fixed CRC frames and additive-checksum variable frames | IMPLEMENTED | `SolaceCommands`, `_with_additive_checksum()`, and artifact-vector tests |
| Back/legs movement with STOP cleanup | ALREADY_IMPLEMENTED | Solace movement methods and cancellation tests |
| Flat, relaxing-bedtime, memory, TV, zero-G, and anti-snore actions | IMPLEMENTED | Preset buttons/methods and Solace command tests |
| Five startup preset queries and selected-state notification parsing | ALREADY_IMPLEMENTED | `_async_query_preset_states()` and notification tests |
| Music start/stop, track selection, previews, volume query/set, and volume reply | IMPLEMENTED | Music buttons, `solace_audio`, audio-volume sensor, and service-to-entity test |
| Startup local-time clock synchronization | IMPLEMENTED | `build_solace_clock_command()` and startup-query tests |
| Alarm programming and alarm/audio-availability replies | IMPLEMENTED | `solace_set_alarm`, `build_solace_alarm_command()`, and parser tests |
| Brightness writes 0-10, brightness query/reply, and three timer toggles | IMPLEMENTED | Solace light, number, and select entities plus command, parser, and entity-state tests |
| Model-setting identifiers whose predicate has no visible effect | EXCLUDED | Reachable app settings are behaviorally inert, so there is no state or command to reproduce |
| Sync notifications with empty EventBus consumers | EXCLUDED | The app records a switch, but no reachable behavior consumes or changes it |
| Arbitrarily prefixed or broad case-sensitive `QMS` substring discovery | EXCLUDED | Home Assistant rejects leading-wildcard discovery hints as too broad; accepted prefixes remain reachable, while auto-configuring unknown FFE1 families would be unsafe |
| Initial FFE1 write without an initialized application value | EXCLUDED | The artifact does not assign command bytes before this write, so reproducing an unknown cached characteristic value would be nondeterministic and unsafe |
| Reads of every GATT descriptor and their passive callbacks | EXCLUDED | The app has no consumer for the returned values; Home Assistant's Bluetooth stack owns the CCCD operation needed for notifications |

Ledger totals: **IMPLEMENTED 7, ALREADY_IMPLEMENTED 3, EXCLUDED 5**.

Dead or unreachable artifact code is outside the reachable ledger: the hidden
massage and fault surfaces, characteristic reads, RSSI reads, reliable writes,
and the unused advertisement parser are not exposed by the MotionFlex
application.

### Validation requests

After beta or release, useful captures are:

1. One movement start and STOP for each active profile.
2. All five startup status replies.
3. Flat and one named preset per profile.
4. The Sweet Night Memory 2 short-press behavior, whose shipped app duplicates Memory 1.
5. Runtime FFE1 properties/write type on each controller family.
