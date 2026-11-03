# OKIN SleepEase (DoubleSleep)

Select **OKIN SleepEase (DoubleSleep / XiaoBao)** for the `com.okin.doublesleep`
app. Support is based on the independently accepted 1.2.24 / code 109 artifact.
Hardware behavior has not been confirmed. This is a separate integration profile;
a Nordic UART service alone does not identify this app.

Setup asks for the saved app model and the BLE driver separately. Automatic driver
selection uses the advertisement name and company 89 payload. It waits for an
advertisement rather than guessing an offline driver's controls. An explicit P1,
P2 or P3 selection is available when the advertisement cannot be recovered.
Changing a saved UI model does not change the driver inferred from an advertisement.

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

## Controls and state

P1 and P2 expose the app's five labelled axes: head, foot, lumbar, headrest and
hips. The headrest uses HA's pillow control and hips use its hip control. Presets
include Flat, Zero gravity, Anti-snore, Lounge/Reading, TV and two numbered recalls.
P1 recall is held; P2 recall is one-shot. P2 can save all six non-Flat targets.
All movement uses the protocol's STOP on release and cancellation. The native
card receives held-control metadata for the axes and P1 presets.

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
  The saved sensor-only
  UI uses P3's JSON command; the other UI uses P2's binary command. An unavailable
  builder fails before writing. State is queried after 200 ms.
- `report`: left/right sensor side, day/month and date. P2 and P3 report profiles
  expose this action. The binary year must fit its2000-based byte. A request owns
  the connection until a result. Five seconds without report progress ends the
  exchange; a progressing transfer can continue longer. The app's five-second
  indication does not abort its transfer. P3's allow-report continuation runs
  inside the owned operation.
- `save_preset`: P2 Memory 1/2, Anti-snore, Lounge, TV or Zero gravity, followed by
  release. This changes the corresponding physical bed preset.
- `capabilities`: the app's MFP page byte. The app uses page 0 during connection and
  page 1 for slow-anti-snore settings. The resulting function/capability state is
  available in the configuration sensor attributes.

Report status 0 means data,1 means empty and2 means the app's busy/timeout result.
Report sensor attributes preserve the original daily map or monthly JSON text,
all returned fields, the selected side and the app consumer's typed/defaulted
records. Missing and null fields receive the app's defaults. Scalars and array
members require integers; text fields require strings. Unknown wire keys remain
in the raw data. A malformed report is recorded as a parser error, without publishing a
successful decoded report. No local health score or month-chart aggregation is
calculated. The app's page navigation, SQL cache and cloud fallback are not HA
report triggers; report retrieval is explicit here.

Legacy UI models use the Download legacy history button. The controller captures
12/16/18-byte records, waits for the source's500 ms quiet interval, retains raw and
normalized record fields, then confirms completion. It does not send a speculative
all-history command. P2 with a saved legacy UI model uses the legacy request too.
Overlapping downloads are rejected until the first transfer and its completion
confirmation finish.

## Wire and lifecycle reference

Service `6e400001-b5a3-f393-e0a9-e50e24dcca9e` owns TX
`6e400002-b5a3-f393-e0a9-e50e24dcca9e` and RX
`6e400003-b5a3-f393-e0a9-e50e24dcca9e`. P1/P2 require write-without-response;
P3 requires write-with-response. RX supports notify or indicate through the
backend. No app PIN, bonding or authentication exchange is present.

P1 uses its own `05 02` / raw-array builders. P2 uses its separate `aa` command
families and `2a` query families. They must not be interchanged. P3 uses compact
ordered UTF-8 JSON (`id`, `cmd`, `val`), a sequence advancing for both JSON and
fragments, and a14-byte nested header. Fragments fit negotiated ATT MTU minus3
and the one-byte inner-body length. No fixed MTU is requested or assumed.

Notification parsers retain the source's branch ordering, P1 massage formulas,
P2 regular/sonic caches, header-selected report side/mode, empty-P2 completion,
monthly text dispatch, P3 char-code single-packet decoder and retained fragment
index. Callback/device ownership, timer cancellation and connection cleanup are
covered by focused tests. Caches survive reconnects for one physical target and
are cleared on profile/address removal by HA's app-session infrastructure.
They are not shared across beds. Numeric caches and sequence survive a logical
view reload; view capabilities and rolling histories survive reconnects but
start cold when their coordinator is recreated.

Writes are serialized and awaited, errors stop a fragment batch and each write
has the source plugin's15-second completion bound. Report cancellation ends the
connection before another request can borrow a late response. RX callbacks from
an old client are ignored. A persistent connection supports sensor data and
report continuation; explicitly disconnect to hand the link to the phone app.
Unexpected link loss immediately invalidates connection timers and queued work.

See the [complete disposition ledger](../apk-analysis/dispositions/row107-doublesleep.md)
for accepted identities, exhaustive coverage, safety differences and exclusions.
Actual negotiation, ATT/firmware effects and physical movement/sensor meanings
remain checks for real users after a beta or release.
