# OKIN SleepEase (DoubleSleep)

**Status:** ❓ Needs testing (static BLE evidence; hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

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

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [OKIN SleepEase / DoubleSleep](https://play.google.com/store/apps/details?id=com.okin.doublesleep) 1.2.24 (code 109) | `com.okin.doublesleep` |

Select **OKIN SleepEase (DoubleSleep / XiaoBao)** for the `com.okin.doublesleep`
app. Support is based on the independently accepted 1.2.24 / code 109 artifact.
Hardware behavior has not been confirmed. This is a separate integration profile;
a Nordic UART service alone does not identify this app.

## Features

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

## Controls and state

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

## Protocol Details

**Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e`
**Write Characteristic:** `6e400002-b5a3-f393-e0a9-e50e24dcca9e`
**Notify Characteristic:** `6e400003-b5a3-f393-e0a9-e50e24dcca9e`
**Format:** Independent P1 raw arrays, P2 `AA` controls / `2A` queries, or P3 nested-header JSON

### Write Mode

Service `6e400001-b5a3-f393-e0a9-e50e24dcca9e` owns TX
`6e400002-b5a3-f393-e0a9-e50e24dcca9e` and RX
`6e400003-b5a3-f393-e0a9-e50e24dcca9e`. P1/P2 require write-without-response;
P3 requires write-with-response. RX supports notify or indicate through the
backend. No app PIN, bonding or authentication exchange is present.

### Packet Format

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

## Detection / Setup

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

## Commands

Tables are taken from
[`DoubleSleepController`](../../custom_components/adjustable_bed/beds/doublesleep.py)
and its [`protocol builders`](../../custom_components/adjustable_bed/doublesleep_protocol.py).
Indices identify builders, not a raw-packet service. UI model, child-lock and
reported capability gates still apply.

### Motor Control

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

### Presets

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

### Memory

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

### Massage

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

#### P2 relative builders

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

#### Sonic source and power

| Index | Command | P1 bytes | P2 bytes |
|---|---|---|---|
| 87 | Sonic normal source | Unavailable | `AA 00 00 06 05 02 00 00` |
| 88 | Sonic music source | Unavailable | `AA 00 00 06 05 02 00 01` |
| 89 | Sonic on | Unavailable | `AA 00 00 06 0C 02 00 01` |
| 90 | Sonic off | Unavailable | `AA 00 00 06 0C 02 00 00` |

Sonic controls require MFP function 7. Regular control actions are unavailable
while the sonic UI is selected.

### Lights

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

### Alarm, state, privacy and legacy queries

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

### Dynamic binary configuration

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

### P3 JSON commands

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

## Configuration and reports

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

## Position Feedback / Notifications

Notification parsers retain the source's branch ordering, P1 massage formulas,
P2 regular/sonic caches, header-selected report side/mode, empty-P2 completion,
monthly text dispatch, P3 char-code single-packet decoder and retained fragment
index. Callback/device ownership, timer cancellation and connection cleanup are
covered by focused tests. Caches survive reconnects for one physical target and
are cleared on profile/address removal by HA's app-session infrastructure.
They are not shared across beds. Numeric caches and sequence survive a logical
view reload; view capabilities and rolling histories survive reconnects but
start cold when their coordinator is recreated.

## Command Timing

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

## Wire and lifecycle reference

Writes are serialized and awaited, errors stop a fragment batch and each write
has the source plugin's 15-second completion bound. Report cancellation ends the
connection before another request can borrow a late response. RX callbacks from
an old client are ignored. A persistent connection supports sensor data and
report continuation; explicitly disconnect to hand the link to the phone app.
Unexpected link loss immediately invalidates connection timers and queued work.

## Notes

### Analysis provenance

See the [complete disposition ledger](../apk-analysis/dispositions/row107-doublesleep.md)
for accepted identities, exhaustive coverage, safety differences and exclusions.
Actual negotiation, ATT/firmware effects and physical movement/sensor meanings
remain checks for real users after a beta or release.
