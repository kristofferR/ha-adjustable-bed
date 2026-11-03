# Comfort Enhancements

Choose **Comfort Enhancements app (choose MC2/MC3/MC4/MC5)** manually, then
select the screen used in the Android app. Shared Bluetooth names and services
do not identify this app or its layout. No automatic layout is available.

| Layout | Third movement control | Memory slots | Massage and light |
| --- | --- | --- | --- |
| MC2: AC-1/BC3, Massage Plus / Comfort Position | Both (app union) | A, B | Yes |
| MC3: Comfort Position | Both (app union) | A, B | No |
| MC4: Lumbar Support / Massage Plus | Lumbar | Memory | Yes |
| MC5: Hi Lo Lift / Massage Plus | Bed height | Memory | Yes |

All layouts expose Back, Legs, Flat, Zero G and Quiet sleep. MC2/MC3 also expose
TV. Memory recall and save are separate buttons. The layout controls feature
availability, independently of the generic motor count. A two-address pair keeps
each physical bed's layout; unpair before changing those choices. This profile
has no one-address Left/Right control.

Movement sends a frame immediately and refreshes every 200 ms for a bounded HA
tap (five pulses by default). Normal release sends the movement STOP 100 ms
later. Cancellation ends the refresh and sends cleanup with a fresh event;
explicit Stop sends both the movement and preset STOP forms. A repeated tap of
the same preset sends the preset STOP, as in the app. No position feedback or
travel angles are reported. The labels describe the app controls; physical
semantics and stopping latency remain unverified on hardware.

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

New entries keep the connection between commands by default so preset repeat-tap
and massage cycles retain their local state. Massage state is local assumed
state, reset on reconnect. External remote
changes and timer expiry cannot be observed. Light On/Off also has assumed
state. Stopping the final active zone clears the local timer. Once a multi-zone
shutdown starts, its zone-off writes finish before a replacement command, even
if cancelled; delayed start writes remain cancellable. No notification-derived
alarm, motor, sensor or massage state is exposed.

## Clock and alarm

`adjustable_bed.sync_clock` sends the local HA time and the app's alarm query.
`adjustable_bed.comfort_enhancements_set_alarm` programs or disables the BLE
alarm. It accepts the usual `device_id` and optional paired `side`, plus:

| Field | Meaning |
| --- | --- |
| `enabled` | Required boolean |
| `time` | Required when enabling, `HH:MM:00` with minute precision |
| `memory` | 0 = none (default); MC2/MC3: 1 = A, 2 = B; MC4/MC5: 1 = Memory |
| `massage` | Include the app's alarm massage fields, default false |

The app's alarm includes a current-day mask, even if the chosen time has
already passed today. HA preserves that packet behavior; it does not invent
weekly or next-day scheduling. MC3's alarm massage checkbox is independent of
its hidden massage control page. Hardware interpretation is unverified.
Disabling needs no time and sends the complete all-FF disable template.

HA requires an explicit settled time when enabling. The app instead retains
fields from 300 ms debounced wheel callbacks and 500 ms programmatic positioning,
which can send stale or FF time bytes. HA never reproduces those races, the
misleading initial enabled flag, phone ringtone playback or Android scheduling.
Successful writes establish no device acknowledgement of the alarm setting.

## Protocol

Evidence: accepted independent audit of `com.okin.enhancements` **1.0.3 (4)**.
Artifact set SHA-256:
`bc76b08e593f42a3772385551553cb93345394639cfeb4d8e2cc61a99c28eab7`.
See the [complete discovery dispositions](../apk-analysis/dispositions/row110-comfort-enhancements.md).

The app discovers the last writable `FFE9` characteristic and last notifiable
`FFE4` across all services. Parent service constants do not constrain selection.
The profile uses those exact characteristic objects, subscribes through HA's
BLE stack, and selects write response mode from discovered metadata. There is
no app authentication, initialization packet, ACK gate or position query.

Control frames are `E5 FE 16` + four big-endian action bytes + complemented sum.
Movement uses `00000001/02` (Back), `00000004/08` (Legs), `00000010/20` (third
control), with release `00000000`. Presets use `01000001/02/04` (Zero G, Flat,
Quiet sleep), `01000003` (TV or single Memory), `01000008/09` (A/B), and STOP
`01000000`. Save uses `20000003/08/09`. Light uses `31000001/00`.
Massage bases are `10000010` (head), `11000010` (foot), `10000020` (wave), plus
level 0..3; timers are `10000030/31/32`.

Clock frames are `E2 FE 16 ss mm hh day checksum`, with Sunday = 0. Alarm frames
are `EB FE 16 now_ss now_mm now_hh alarm_mm alarm_hh day mask massage0 massage1
memory checksum`. Enabled massage is `11 33`, disabled `00 00`; memory is
`F8/F9/F3/FF`. Disabling uses FF at alarm time, mask, massage and memory offsets.
Time is binary, not BCD. The final byte makes the unsigned sum equal FF modulo 256.

The app's live notify callback compares lowercase hex against uppercase
`E2FE16`, rejecting all inputs. Its unreachable parser lacks a proven reply
length/checksum and always marks massage enabled. HA retains raw notifications
for diagnostics and does not invent working feedback from that dead parser.

**Hardware status:** artifact-vector and HA software validation only. Real users
can validate movement labels, release, massage and alarms after beta/release;
maintainer access to a bed is not a prerequisite for this implementation.
