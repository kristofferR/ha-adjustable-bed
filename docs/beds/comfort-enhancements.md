# Comfort Enhancements

**Status:** ❓ Needs testing (artifact-vector and HA software validation only)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

| Layout | Third movement control | Memory slots | Massage and light |
| --- | --- | --- | --- |
| MC2: AC-1/BC3, Massage Plus / Comfort Position | Both (app union) | A, B | Yes |
| MC3: Comfort Position | Both (app union) | A, B | No |
| MC4: Lumbar Support / Massage Plus | Lumbar | Memory | Yes |
| MC5: Hi Lo Lift / Massage Plus | Bed height | Memory | Yes |

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Comfort Enhancements](https://play.google.com/store/apps/details?id=com.okin.enhancements) 1.0.3 (4) | `com.okin.enhancements` |

## Features

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

## Protocol Details

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

### Packet Format

- Control: `E5 FE 16` + four big-endian action bytes + complemented sum.
- Clock: `E2 FE 16 ss mm hh day checksum`, with Sunday = 0.
- Alarm: `EB FE 16 now_ss now_mm now_hh alarm_mm alarm_hh day mask massage0
  massage1 memory checksum`.
- Time is binary, not BCD. The final byte makes the unsigned sum equal FF
  modulo 256.

### Write Mode

Write response mode is selected from discovered metadata: write-without-response
when the characteristic offers it, otherwise write with response.

## Detection / Setup

1. Choose **Comfort Enhancements app (choose MC2/MC3/MC4/MC5)** manually.
2. Select the screen used in the Android app.

- Shared Bluetooth names and services do not identify this app or its layout.
  No automatic layout is available.
- The layout controls feature availability, independently of the generic motor
  count.
- A two-address pair keeps each physical bed's layout; unpair before changing
  those choices. This profile has no one-address Left/Right control.

## Commands

Every control frame carries a 32-bit action word. Movement uses `00000001/02` (Back), `00000004/08` (Legs), `00000010/20` (third
control), with release `00000000`. Presets use `01000001/02/04` (Zero G, Flat,
Quiet sleep), `01000003` (TV or single Memory), `01000008/09` (A/B), and STOP
`01000000`. Save uses `20000003/08/09`. Light uses `31000001/00`. Massage bases
are `10000010` (head), `11000010` (foot), `10000020` (wave), plus level 0..3;
timers are `10000030/31/32`.

### Motor Control

| Command | Action word | Bytes (hex) |
|---------|-------------|-------------|
| Back Up | `00000001` | `E5 FE 16 00 00 00 01 05` |
| Back Down | `00000002` | `E5 FE 16 00 00 00 02 04` |
| Legs Up | `00000004` | `E5 FE 16 00 00 00 04 02` |
| Legs Down | `00000008` | `E5 FE 16 00 00 00 08 FE` |
| Third control Up (Both / Lumbar / Bed height) | `00000010` | `E5 FE 16 00 00 00 10 F6` |
| Third control Down | `00000020` | `E5 FE 16 00 00 00 20 E6` |
| Movement STOP (release) | `00000000` | `E5 FE 16 00 00 00 00 06` |

### Presets

| Command | Action word | Bytes (hex) |
|---------|-------------|-------------|
| Zero G | `01000001` | `E5 FE 16 01 00 00 01 04` |
| Flat | `01000002` | `E5 FE 16 01 00 00 02 03` |
| TV (MC2/MC3) | `01000003` | `E5 FE 16 01 00 00 03 02` |
| Quiet sleep | `01000004` | `E5 FE 16 01 00 00 04 01` |
| Preset STOP | `01000000` | `E5 FE 16 01 00 00 00 05` |

A repeated tap of the same preset sends the preset STOP, as in the app.

### Memory

| Command | Action word | Bytes (hex) |
|---------|-------------|-------------|
| Memory A recall (MC2/MC3) | `01000008` | `E5 FE 16 01 00 00 08 FD` |
| Memory B recall (MC2/MC3) | `01000009` | `E5 FE 16 01 00 00 09 FC` |
| Memory recall (MC4/MC5) | `01000003` | `E5 FE 16 01 00 00 03 02` |
| Memory A save (MC2/MC3) | `20000008` | `E5 FE 16 20 00 00 08 DE` |
| Memory B save (MC2/MC3) | `20000009` | `E5 FE 16 20 00 00 09 DD` |
| Memory save (MC4/MC5) | `20000003` | `E5 FE 16 20 00 00 03 E3` |

### Massage

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

### Lights

| Command | Action word | Bytes (hex) |
|---------|-------------|-------------|
| Light On | `31000001` | `E5 FE 16 31 00 00 01 D4` |
| Light Off | `31000000` | `E5 FE 16 31 00 00 00 D5` |

## Clock and alarm

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

## Notifications / State

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

## Command Timing

| Action | Timing |
|--------|--------|
| Movement | Sends a frame immediately and refreshes every 200 ms for a bounded HA tap (five pulses by default) |
| Normal release | Movement STOP 100 ms later |
| Cancellation | Ends the refresh and sends cleanup with a fresh event |
| Explicit Stop | Sends both the movement and preset STOP forms |
| Massage zone start | 10-minute timer first when no local timer is set, intensity after 200 ms |

Once a multi-zone shutdown starts, its zone-off writes finish before a
replacement command, even if cancelled; delayed start writes remain cancellable.

## Notes

- The labels describe the app controls; physical semantics and stopping
  latency remain unverified on hardware.
- **Hardware status:** artifact-vector and HA software validation only. Real
  users can validate movement labels, release, massage and alarms after
  beta/release; maintainer access to a bed is not a prerequisite for this
  implementation.

### Analysis provenance

- Evidence: accepted independent audit of `com.okin.enhancements` **1.0.3 (4)**.
- Artifact set SHA-256:
  `bc76b08e593f42a3772385551553cb93345394639cfeb4d8e2cc61a99c28eab7`.
- See the [complete discovery dispositions](../apk-analysis/dispositions/row110-comfort-enhancements.md).
