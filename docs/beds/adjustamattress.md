# AdjustaMattress app

**Status:** ❓ Needs testing (artifact behavior verified, hardware **unverified**)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Receivers driven by the AdjustaMattress app, in four BLE models (P1 to P4)
  and seven product layouts (L0 to L6). See [Setup and layout](#setup-and-layout).
- Selected only through the explicit **AdjustaMattress app (seven product
  layouts)** bed type. Shared services and a familiar name do not identify this
  app, so select it manually.
- Independent of the Adjustable bed (Lumbar), SmartBed and other OKIN app
  profiles.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [AdjustaMattress](https://play.google.com/store/apps/details?id=com.okin.adjustamattress) 1.6.0 (version code 10) | `com.okin.adjustamattress` |

- The bed type implements this artifact. Its artifact behavior is verified;
  physical hardware remains **unverified**.

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (head and foot; per layout also head + foot together, neck tilt, lumbar, lift) |
| Presets | ✅ (flat and zero gravity; TV, lounge and anti-snore on L0 to L5) |
| Memory Presets | ⚠️ (M1 recall on L0 only; no memory programming or additional slots) |
| Massage | ✅ (P2 L0/L1/L2/L3/L5: dedicated selectors and timers; others: four held steps) |
| Massage power/off, absolute intensity | ❌ (not in this artifact, not synthesized) |
| Lights | ✅ (underbed lighting on L0/L1/L3/L5/L6; ❌ on P2) |
| Alarm | ✅ (draft hour/minute/action, explicit On/Off commit) |
| Clock sync | ✅ (P1/P3/P4) |
| Intelligent anti-snore and sleep | ✅ (P4 L0/L3 only) |
| Position Feedback | ❌ (no motor angle, percentage, height or current telemetry) |
| Single-address Left/Right | ❌ |

## Setup and layout

Choose the matching product layout and BLE model in **Protocol variant**. The 28
explicit choices (`P1_L0` to `P4_L6`) combine two independent dimensions.

### Models

| Model | Artifact enum | GATT roles |
| --- | --- | --- |
| P1 | CB | Service FFE5 / write FFE9, service FFE0 / notify FFE4 |
| P2 | JLDP | Same roles; FFF0 is a model marker, never the writer |
| P3 | CB24 | Nordic UART service 6E400001 / write 002 / notify 003 |
| P4 | SleepSnore | Same Nordic UART roles, different frames and parser |

### Layouts

| Layout | Additional position controls beyond head, foot, flat and zero gravity |
| --- | --- |
| L0 AdjustaLumbarHeadTilt | Neck tilt, lumbar, M1, TV, lounge, anti-snore, lighting |
| L1 AdjustaBed | Head + foot together, TV, lounge, anti-snore, lighting |
| L2 AdjustaMattress | Head + foot together, TV, lounge, anti-snore |
| L3 AdjustaBedLumbar | Lumbar, head + foot together, TV, lounge, anti-snore, lighting |
| L4 FoldingBed | TV, lounge, anti-snore |
| L5 HilowBed | Neck tilt, TV, lounge, anti-snore, lighting |
| L6 Lolobed | Lift head, lift foot, lift up/down, lighting |

- Lift labels follow the app. They do not establish a measured height or a new
  motor position scale.
- L5 has no lift command merely because of its name.
- M1 exists only on L0; no memory programming or additional memory slots exist.
- Generic motor counts do not expand these layouts.

### Native controls

- Position covers, standard preset buttons, app-labelled M1/lift/light buttons,
  and the generic `adjustable_bed.hold_control` action use the selected layout.
- Held identifiers preserve the artifact's method names, such as `headUp`,
  `footDown`, `unionUp`, `neckTiltUp`, `lumbarDown`, `liftHead`, `flatPosition`,
  `zeroGravity`, `tv`, `lounge`, `anti` and `m1`. Only exposed controls are
  accepted.
- The native card groups massage, lighting, presets and utility settings.

| HA control | Artifact actions |
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

### Paired beds

- Profile/variant settings belong to each physical address. Configure each side
  separately before combining a two-address pair.
- A single-address side selector is unsupported.

## Protocol Details

| Role | P1 / P2 | P3 / P4 |
| --- | --- | --- |
| Write service | `0000ffe5-0000-1000-8000-00805f9b34fb` | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` |
| Write characteristic | `0000ffe9-0000-1000-8000-00805f9b34fb` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` |
| Notify service | `0000ffe0-0000-1000-8000-00805f9b34fb` | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` |
| Notify characteristic | `0000ffe4-0000-1000-8000-00805f9b34fb` | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` |
| Model marker | `0000fff0-0000-1000-8000-00805f9b34fb` (P2) | none |

**Format:** model-specific control frames; P1/P2 carry a one-byte checksum, P3/P4 do not

The P1 and P2 key frames are built by the [Keeson codec](keeson.md#e6-controller-profiles).

- Short UUIDs expand to the Bluetooth base UUID. Nordic UART's suffix is
  `-b5a3-f393-e0a9-e50e24dcca9e`.

### Packet Format

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
  including P3/P4 year/month and byte-order differences. See [Commands](#commands).

### Write Mode

- Writes require **write with response**.
- Notifications remain enabled even when angle sensing is disabled.
- Missing roles or an unsupported write mode fail setup rather than selecting
  another app's transport.
- The last matching GATT role wins in enumeration order.

## Detection / Setup

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

## Commands

Frames are `frame()` output from
[`adjustamattress_protocol.py`](../../custom_components/adjustable_bed/beds/adjustamattress_protocol.py).
Concrete tests cover all 180 accepted command/vector rows, including dormant
branches retained only as evidence.

### Motor Control

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

### Lift (L6)

The lift helpers send the same `05` frames on every model.

| Command | Bytes |
|---------|-------|
| `liftHead` | `05 02 00 00 00 10 00` |
| `liftFoot` | `05 02 00 00 00 20 00` |
| `liftUp` | `05 02 00 00 00 40 00` |
| `liftDown` | `05 02 00 00 00 80 00` |

### Presets

| Command | P1 | P2 | P3 | P4 |
|---------|----|----|----|----|
| `flatPosition` | `E6 FE 16 00 00 00 08 00 FD` | `E5 FE 16 01 00 00 02 03` | `05 02 08 00 00 00 00` | `06 02 08 00 00 00 00 00` |
| `zeroGravity` | `E6 FE 16 00 10 00 00 00 F5` | `E5 FE 16 01 00 00 01 04` | `05 02 00 00 10 00 00` | `06 02 00 00 10 00 00 00` |
| `tv` | `E6 FE 16 00 40 00 00 00 C5` | `E5 FE 16 01 00 00 04 01` | `05 02 00 00 40 00 00` | `06 02 00 00 40 00 00 00` |
| `lounge` | `E6 FE 16 00 20 00 00 00 E5` | `E5 FE 16 01 00 00 09 FC` | `05 02 00 00 20 00 00` | `06 02 00 00 20 00 00 00` |
| `anti` | `E6 FE 16 00 80 00 00 00 85` | `E5 FE 16 01 00 00 09 FC` | `05 02 00 00 80 00 00` | `06 02 00 00 80 00 00 00` |

- On P2, `lounge` and `anti` send the same code (`09`), as in the artifact vectors.

### Memory

| Command | P1 | P2 | P3 | P4 |
|---------|----|----|----|----|
| `m1` recall (L0) | `E6 FE 16 00 00 10 00 00 F5` | `E5 FE 16 01 00 00 08 FD` | `05 02 00 01 00 00 00` | `06 02 00 01 00 00 00 00` |

- No program/save command exists.

### Massage

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

- Three dedicated massage selection entities (head, foot, wave, each index
  0..3), written once per choice.
- 10/20/30-minute timer buttons, held like the ordinary steps.
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
  setter in this artifact, so those controls are not synthesized.
- Dormant timer branches on other models are not promoted.

### Lights

| Command | P1 | P2 | P3 | P4 |
|---------|----|----|----|----|
| `underbedLighting` | `E6 FE 16 00 00 02 00 00 03` | ❌ (no frame; see [Notes](#app-defects-and-safety-dispositions)) | `05 02 00 02 00 00 00` | `06 02 00 02 00 00 00 00` |

### Clock and queries

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

## Alarms

- Alarm hour/minute numbers and action select are **drafts**. Set the Alarm
  select to On or Off to commit. Editing an enabled alarm is rejected.
- On commits repeat 255; Off commits repeat 0 on P1/P3/P4, while P2 uses its
  all-255 disable sentinel (hour, minute, action and repeat all 255).
- Action codes are 0 (app default), 9 (massage), 17 (neutral action code) and 19
  (position). No weekday-bit interpretation or physical posture for action 17 is
  invented.
- The commit writes at +200 ms and refreshes the alarm at +600 ms.
- Reported alarm fields remain separate from the draft values and wait for
  replies.
- Local drafts and pending strength choices survive BLE reconnects through the
  per-address/profile app session. Hydration cannot erase uncommitted edits.
  Only the privacy agreement persists across Home Assistant restarts.

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

## Anti-snore and sleep (P4 L0/L3)

P4 L0/L3 additionally expose intelligent anti-snore On/Off, demonstration,
sleep, status refresh, local strength choice and the persisted privacy agreement.

| Command | Bytes |
| --- | --- |
| Anti-snore (`_sendAntiSnoreCommand`) | `05 0B` mode strength `01 23 00` |
| Sleep start / stop (`toggleSleeping`) | `01 B5 01` / `01 B5 00` |
| Status query (`queryControlBoxStatus`) | `00 B0` |

- Anti-snore mode byte: `02` when demonstration is set, otherwise `01` enabled
  or `00` disabled (wire mode 2 is demonstration).
- Strength index 0/1/2 sends `01`/`03`/`06`; `23` is threshold 35.
- Review the manufacturer's anti-snore privacy notice in its app before marking
  that local agreement Accepted.
- Enabling clears demonstration; disabling preserves it, so a retained
  demonstration can still select wire mode 2.
- Demonstration requires intelligent anti-snore to be disabled.
- Strength selection changes the next command, without an immediate write.

### Sleep action

- Before each Sleep action, HA queries and awaits a fresh P4 status report.
- A five-second HA readiness guard rejects a missing reply without sending a
  sleep command. This is an integration guard, not a discovered device timer;
  old replies or reconnect defaults cannot determine the direction.
- The following app sequence starts only after that fresh report.
- Sleep follows the app's separate path without the privacy gate.
- Starting while anti-snore is disabled enables it, forces strength index
  1/threshold 35, preserves demonstration, sends the anti-snore helper
  immediately and sleep at +200 ms. Otherwise sleep is immediate.
- Both query status at +500 ms. Reported sleeping changes only on notification.

## Position Feedback / Notifications

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

## Command Timing

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

## Notes

### App defects and safety dispositions

The following app defects have explicit safety dispositions in the
[discovery ledger](../apk-analysis/dispositions/row067-adjustamattress.md):

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
  status queries are explicit native refresh actions, with the evidenced query
  timing. They cannot overwrite an active held motor frame or its STOP.
- Invalid-length crashes, unknown-fragment resets to zero, and missed on-only
  callbacks are phone parser defects. HA guards complete indexed fields, retains
  known telemetry on unknown fragments and publishes valid on-only changes.

### Connection and scope boundaries

- Connection/adapter/proxy policy belongs to HA.
- The controller subscribes before clock/alarm hydration, retries the FFE notify
  subscription once after one second, and does not perform Android-specific
  MTU/PHY/permission/cache/bond operations.
- No app PIN/authentication command, Wi-Fi provisioning, network administration,
  cloud/account control, firmware upload or bed reset is recovered.
- Generic SDK networking and phone infrastructure are excluded from this
  BLE-only profile.

### Hardware validation

- Physical validation is deferred to real users after beta/release: confirm raw
  name/GATT selection, layout roles, held release/cancel, alarms, massage
  replies and P4 status meanings.
- No maintainer hardware acquisition or immediate physical operation is required
  to complete this static implementation.

### Analysis provenance

- Package `com.okin.adjustamattress` 1.6.0 (version code 10).
- Accepted standalone FULL APK audit row067, artifact-set SHA256
  `bff51c93b65b5236884608ceb941a6e0bb23ac36cb52f7e852c3d99d919822fb`.
- Report seal `69d851737cb7aa08716a98d594cdb8cf45bb20eb4a13d5a825835eb7486e7da4`.
- Independent round03 audit accepted all 17 gates, with no findings.
- The disclosed historical temporary-cache ownership deviation remains part of
  the accepted provenance; implementation does not retroactively waive it.
- Machine-local raw artifacts, audit reports and seals are preserved and
  excluded from Git.
- Discovery ledger: [row067-adjustamattress.md](../apk-analysis/dispositions/row067-adjustamattress.md).
