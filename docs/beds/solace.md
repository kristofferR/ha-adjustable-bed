# Solace / QMS 11-byte protocol

**Static analysis:** Complete

**Hardware validation:** Partial (the legacy S4-Y motor layout is user-confirmed; accepted APK routes await post-release validation)

This controller covers a family of beds that write fixed 11-byte frames to FFE1. The apps overlap, but do not expose one universal feature set. The integration therefore selects a conservative capability profile from the observed BLE name.

## Evidence status

| App | Package and version | Phase 4 result |
|---|---|---|
| HomeKobo | `com.ly.homekobo` 1.4 | COMPLETE |
| Sealy MotionFlex | `com.sealy.motionflex` 1.0.3 | COMPLETE |
| Sweet Night | `com.sn.dianqi` 1.0.6 | COMPLETE, FULL comparison |
| Motion Bed | `com.sn.blackdianqi` 1.24 | Pending |
| Woosa Sleep | `com.sn.woosa` 1.1.6 | Pending |

The accepted reports prove application behavior exhaustively. Physical behavior that cannot be established statically remains explicitly hardware-unverified.

## Profile routing

| Observed name | Motors | Accessories | Status query |
|---|---|---|---|
| `QMS-IQ`, `QMS-I06`, `QMS-LQ`, `QMS-L04`, `QMS-NQ`, `QMS3` | Back, head, legs, hip | Two memories, TV/zero-G/anti-snore, massage, massage cycles/timers, light timers | Q1 |
| `QMS-JQ-D`, `QMS4` | Back, head, legs, lumbar | Two memories, TV/zero-G/anti-snore, massage/timers, light timers | Q1 (Q2 for compound Q2 names) |
| `QMS2`, `QMS-MQ` | Back, legs | Two memories, TV/zero-G/anti-snore, light timers | Q2 |
| `SealyMF*` | Back, legs | Two memories, TV/zero-G/anti-snore, light levels 0-10, light timers | Q2 |
| Exact `S4-Y-<digits>-<id>` | Back, legs, bed height, tilt | Two memories, TV/zero-G/anti-snore, deployed legacy flat | None |
| Any unidentified manual Solace route | Back, legs | No unverified presets or accessories | None |

`QMS2` and `QMS-MQ` deliberately use the common profile. HomeKobo and Sweet Night both route these names, but only HomeKobo exposes massage. The integration does not assume that optional hardware exists.

The exact S4-Y route preserves a real user's confirmed four-cover layout and the previously deployed legacy all-flat command. Auto-discovery is limited to names beginning with the accepted values in the table, plus the accepted `My QMS2` prefix. Broad `QMS*`, arbitrarily prefixed substring, and S3/S4/S5/S6 matching was removed because Home Assistant cannot safely index leading-wildcard discovery hints and the broader families include names sourced only from the still-pending Motion Bed APK. A name merely containing `solace` is not evidence and is not auto-detected. Existing manual entries with an unidentified name retain basic back/legs movement and STOP but do not receive guessed query, preset, massage, or lighting commands.

## BLE session

- Apps scan without a UUID filter and select devices by case-sensitive local-name substrings.
- No fixed service UUID is required. Every discovered service is traversed.
- Control and notifications use `0000ffe1-0000-1000-8000-00805f9b34fb`.
- CCCD `00002902-0000-1000-8000-00805f9b34fb` is enabled with `01 00`.
- There is no authentication, bonding requirement, MTU negotiation, encryption, retry loop, or protocol command queue in the accepted apps.
- Accepted profiles subscribe to FFE1 even when angle sensing is disabled because preset and accessory state arrive there. The exact S4-Y legacy profile is excluded because no accepted query family applies to it.

## Packet format

Control frames are fixed 11-byte values:

```text
FF FF FF FF 05 00 00 <mode> <selector> <crc-low> <crc-high>
```

The checksum is CRC-16/MODBUS over bytes 0-8, initial value `0xFFFF`, reflected polynomial `0xA001`, low byte first. The accepted apps decode fixed hexadecimal strings rather than constructing these CRCs at runtime.

The integration's accepted family command set is:

| Action | Frame |
|---|---|
| Stop | `FF FF FF FF 05 00 00 00 00 D7 00` |
| Back up/down | selector `03` / `04` |
| Legs up/down | selector `06` / `07` |
| Flat | `FF FF FF FF 05 00 00 00 08 D6 C6` |
| TV | `FF FF FF FF 05 00 00 00 05 17 03` |
| Zero-G | `FF FF FF FF 05 00 00 00 09 17 06` |
| Anti-snore | `FF FF FF FF 05 00 00 00 0F 97 04` |
| Memory 1 recall/save | mode `A1` / `A0`, selector `0A` |
| Memory 2 recall/save | mode `B1` / `B0`, selector `0B` |

Sweet Night's shipped Memory 2 short-press path duplicates Memory 1. The
distinct Memory 2 frame above is independently accepted from HomeKobo and
MotionFlex; Sweet Night runtime validation remains explicitly requested.

Flat and preset actions are single writes. The accepted apps do not send STOP or wait 200 ms before a preset. Movement sends one start frame and the global STOP on release. Home Assistant cover actions have no matching button-release event, so the integration retains a five-second integration safety cap and always sends STOP in cleanup; an explicit Stop cancels it immediately.

## Preset state

Q1 and Q2 use different five-command query sets. Queries start after notification setup, then use the app-proven pacing. Responses are substring-matched by the accepted apps and identify selected state for memory 1, memory 2, TV, zero-G, and anti-snore. The integration records the same controller state for diagnostics without treating it as position feedback.

There are two numbered memory slots. Historical “memory 3-5” frames are actually the selected/program branches for TV, zero-G, and anti-snore.

## Profile-specific features

Home profiles prove head/upper (app label “Back Mass”), foot/lower (app label “Leg Mass”), and wave massage step controls, massage stop, 10/20/30-minute timers, and cycle modes. Opcode direction is:

- Wave minus `15`, plus `14`
- Head/upper minus `11`, plus `10`
- Foot/lower minus `13`, plus `12`

The K1 fourth cycle zone is hip. K2 uses the same frame for lumbar, so the generic hip-labeled cycle button is withheld on K2 rather than mislabeled.

MotionFlex proves light brightness levels 0-10; level 0 is the accepted off command. HomeKobo and Sweet Night prove only the 10-minute, 8-hour, and 10-hour light timer frames, so brightness and an invented timer “Off” option are not exposed there.

## Intentionally withheld behavior

These historical commands remain out of accepted profiles until their own APKs pass Phase 4:

- Yoga selector `4E`
- Legacy all-flat selector `2A` outside the exact S4-Y compatibility profile
- Woosa absolute massage selectors `4F`-`56`
- Woosa light-off selector `4B`
- Five generic numbered memory slots
- Broad S3/S4/S5/S6 detection
- The historical STOP + 200 ms preset preamble

## MotionFlex audio, clock, and alarm

The MotionFlex profile exposes its relaxing-bedtime preset and music start/stop actions as buttons. The `adjustable_bed.solace_audio` service selects or previews tracks 1-5, queries the current volume, and sets volume levels 1-5. The `adjustable_bed.solace_set_alarm` service programs the enabled state, time, weekdays, bed action, massage flag, and alarm or music sound. These services reject non-MotionFlex targets.

On notification startup the controller first sends the app's local-time clock frame, then runs the Q2 preset queries and brightness query. MotionFlex brightness, audio-volume, and alarm replies are decoded into controller state.

## MotionFlex discovery ledger

Every behavior reachable in the frozen MotionFlex report has one disposition below. Grouped rows cover commands or notifications that share one reachable surface and implementation path.

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

Dead or unreachable artifact code is outside the reachable ledger: the hidden massage and fault surfaces, characteristic reads, RSSI reads, reliable writes, and the unused advertisement parser are not exposed by the MotionFlex application.

## Validation requests

After beta or release, useful captures are:

1. One movement start and STOP for each active profile.
2. All five startup status replies.
3. Flat and one named preset per profile.
4. The Sweet Night Memory 2 short-press behavior, whose shipped app duplicates Memory 1.
5. Runtime FFE1 properties/write type on each controller family.
