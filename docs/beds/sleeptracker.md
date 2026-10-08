# Sleeptracker Smart Bed processor

The **Tempur Sleeptracker-AI (ProSmart / ActiveBreeze processor)** selection
implements the direct BLE path in Tempur Sleeptracker-AI
`com.fullpower.applications.horizon` **3.6.2 (262)**. The complete Google Play
delivery was analyzed and independently accepted on 2026-10-08. Protocol and
app behavior are proven by that artifact; physical hardware remains unverified.
The [S02 discovery ledger](../apk-analysis/dispositions/S02-sleeptracker.md)
records every accepted discovery and implementation disposition.

## Select the processor

Choose **Tempur Sleeptracker-AI (ProSmart / ActiveBreeze processor)** for
TEMPUR-Ergo ProSmart Air / ActiveBreeze beds operated with that app. It provides
the app's TV and Anti-Snore presets, ActiveBreeze climate and premium massage
controls. Adjustable Lite was a compatibility selection for the reported bed;
its Tempur-specific massage and preset workarounds are removed.

Select the **Sleeptracker processor's actual Bluetooth endpoint**. The app
uses framed JSON there, while the reported KSSF05C / MC232SC entries expose
UART. Add the verified processor as a separate entry. Do not change those
UART addresses to this profile solely because they belong to the same bed.
A Bluetooth name does not identify the app protocol or a physical half.

Automatic discovery requires the unique service below. For manual setup,
select the processor's actual Bluetooth address and this app's bed type. The
standard Device Information service alone does not identify a bed. Verification
requires the hello and control characteristics inside the selected service,
including for the fallback service route. Authenticated sessions additionally
require the authentication characteristic.

| Role | UUID |
|------|------|
| Preferred service | `f6380280-6d90-442c-8feb-3aec76948f06` |
| Fallback service, manual verification only | `0000180a-0000-1000-8000-00805f9b34fb` |
| Hello, read/notify | `4bc4783d-64a3-45b0-9a4a-06cb7713e32b` |
| Authentication, write/read/notify | `a5a25fb5-500f-436b-8d36-447bc5f30a29` |
| Bed control, write/read/notify | `3d91d13b-2310-43d1-b991-9e915b047653` |
| Optional unframed firmware revision | `00002a26-0000-1000-8000-00805f9b34fb` |

The first present supported service wins. Missing characteristics there cause
verification to fail; the controller does not search a second service to make
an incomplete path appear valid. It never writes JSON to a UART characteristic.

## App layout and sides

| Layout | App ID | Axes offered | Presets | Massage and climate |
|--------|--------|--------------|---------|---------------------|
| Ergo / Slim | 17 / 22 | Back, legs, lumbar | Flat, Zero G, Anti-Snore, favorite 1 | Pattern massage |
| Ergo Smart / Slim Smart | 18 / 23 | Back, legs, lumbar | Add TV and favorite 2 | Pattern and head/foot step |
| Ergo ProSmart / ProSmart Air / Slim ProSmart | 19 / 24 | Back, legs, lumbar | Add TV and favorite 2 | Add 28/40 Hz, wave, wind-down and local animation |
| ActiveBreeze large / small | 20 / 21 | Back, legs, lumbar | Add TV and favorite 2 | Premium massage plus left/right climate |
| Generic app layout | Default | Back and legs | Flat, Zero G, Anti-Snore, TV, favorite 1 | Pattern and head/foot step |

These are app controls, not a measurement of physical motor count. Wire `head`
is exposed as HA **Back**, and wire `foot` as **Legs**. No position, angle,
percentage or height feedback is established. Raw motor/massager bitfields
remain diagnostic metadata and never create additional axes.

Select the persisted app layout explicitly. Hello names `SLIM_GOOD`,
`SLIM_BETTER` and `SLIM_BEST` alias 17, 18 and 19 in the app, while saved Slim
layouts use 22, 23 and 24. A hello alias does not overwrite the selected layout.

Setup also records these settings, independently for each physical processor:

| Setting | Meaning |
|---------|---------|
| Processor unit number | The signed integer the app sends as `position.side`. Examples 0, 1 and 2 do not prove physical left/right/all mapping. Use the recorded app value. |
| Status snapshot side | App `Sensor` ordinal: 0 left, 1 right, 2 entire bed, 3 other. This selects a two-snapshot massage pattern; it does not change the command unit number. |
| Restricted session | Explicit app route without authentication; commands use unit 0. It is never an automatic authentication fallback. |
| Processor type | Raw app type, 0 if unknown. Values 5, 6 and 7 disable preset saving. |
| Foundation size | App metadata such as Queen or SplitKing. It does not infer a command-side mapping. |

Two separate addresses can use HA's ordinary Left/Right children and service
targeting. One-address pairing is unavailable because the artifact does not
prove how unit numbers map to physical halves. ActiveBreeze `fan_side` selects
left/right fan fields inside a processor; it is independent of HA's paired
device `side` target.

## Controls and state

Premium layouts expose **Wind-down running (reported)** from the first parsed
status snapshot, independent of the configured snapshot side. A numeric mode
truncates toward zero and is running when the converted integer is nonzero;
missing or invalid mode values on a present snapshot mean idle. Missing/empty
snapshots retain the previous state. The sensor is unknown before observation
and after disconnect. Later ordinary scalar entries do not invalidate this
independent first-snapshot consumer or close its session. If those entries
cannot be interpreted by the remote/climate consumer, its last safe values
remain unchanged. Malformed consumed fields and nested-array shapes still
fail validation, including values that a later duplicate JSON key overwrites.
Only the reply envelope's `details.body.snapshots` is
consumed. There is no device countdown readback or new BLE polling interval: the
app's local countdown recheck uses cloud transport and is excluded.

Movement repeats an increment only after its reply, using `ticks: 4` and
`waitForResponse: false`. There is no invented refresh delay. HA bounds the
hold using its pulse/timed movement budget and always attempts the corresponding
axis stop in `finally`, with a fresh cancellation event. Transport loss can
prevent delivery; a sent stop is not proof of a physical stop.

Preset buttons recall the app names. Memory slots 1 and 2 mean `user_favorite`
and `favorite_2` where available. Save Zero G, Anti-Snore and TV buttons plus
`sleeptracker_preset` expose the supported save builders. Flat cannot be saved.
The existing generic memory actions also work within the selected capacity.

All layouts have pattern massage and local safety-light toggle. Lighting uses
the app-specific toggle button and reported-state sensor; an assumed-state light
and duplicate generic toggle button are not exposed. Controls removed by a layout,
processor type or restricted-session change are retired from the entity registry
for the affected physical bed. Supported
layouts add head/foot massage steps. Premium layouts add **28 Hz**, **40 Hz**,
wave frequency/duration selectors, wind-down 1/2 and local motor/massage
animation. Wave choices are 28, 40, 52, 68 and 88 Hz, with 5–105 minutes in
steps of five. The wire duration is minutes times 600; its physical tick unit
remains unverified. Wind-down uses modes 1 and 2; the app shows 16- and
10-minute countdowns, without sending those countdown lengths as parameters.
Use massage off to stop wave or wind-down, and Stop All to stop the local
motor/massage animation. The local animation retains the artifact's six
motor/massage statements, order and individual delays, omitting six speaker
statements. It makes no claim to reproduce media playback timing.

ActiveBreeze adds left/right **Off / Cool / Heat**, levels **0–3** and
**Constant / Curve** controls. The proven builder accepts levels 0–3; the
stock app's heat UI chooses off or level 3. Every heat command carries a
**3600-second timer** and every cooling command **36000 seconds**, including
level 0. Timers are fixed wire values, not adjustable countdowns. Last commanded
timer sensors and curve selections describe acknowledged commands, since the
status parser has no timer or curve readback.

The five [typed actions](../SERVICES.md#sleeptracker-smart-bed) expose presets,
climate, wave, massage and relaxation for automations. The dashboard card uses
its existing lighting, massage, climate and utility sections.

Refresh reads motor status. One snapshot reports pattern, raw head/foot massage
strength and safety light. Two snapshots report only the selected ordinal's
pattern and reset the other remote values, matching the app parser. Climate
updates only from a single snapshot's nested fan object, clamps levels to 0–3
and retains absent fields. There is no invented frequency, timer or axis
feedback. Disconnect clears remote state and authentication; local wave
preferences survive within the controller instance.

Identify split light sends the app's literal unit-1 light request at 1500 ms,
bounded to four cycles by HA, and sends explicit light off during cleanup.
Restricted sessions also expose response-driven local light identification
(four alternating toggle/off requests) and explicit local light off. Neither
identification route proves physical left/right mapping.

## Session and privacy

HA subscribes hello, authentication and control, reads hello, authenticates
using bcrypt `$2a$`, cost 10, a fresh salt and the uppercase configured MAC plus
hello challenge, then reads motor status. Tokens stay in memory and are cleared
on disconnect. Raw hello/auth/control reads, notifications and command traces
are redacted, including raw-address support captures.

Frames use a two-byte little-endian header: nine length bits, five sequence
bits, first `0x8000` and last `0x4000`. Outgoing sequence is zero. HA uses a
payload ceiling of `min(500, negotiated MTU - 5)`, further bounded by the
characteristic's no-response write limit. Replies reassemble per channel and
can continue by reading the same characteristic. Transactions are serialized
and replies bounded to 60 seconds. Every awaited exchange validates JSON before
acknowledgement, including identification's final light-off cleanup. Cancelled,
malformed or timed-out exchanges
invalidate the session, attempt cleanup and disconnect before reuse, since
there is no reply request ID.

Empty JSON objects cannot acknowledge a command or establish a session. Valid
nonempty replies without snapshots retain the applicable partial-state rules.
Climate timer and curve metadata publish only after a valid acknowledgement.
Continuation tasks register before execution, including with HA's eager task
scheduling. Movement's local hold deadline ends a normal hold; an earlier ATT
or reply timeout propagates after fresh axis cleanup and session closure.

HA owns adapters, standard notification descriptors, connection parameters and
bond lifecycle. The integration does not remove a host bond automatically,
force pairing, impose the app's RSSI thresholds or block commands on app firmware
UI gates. Reported model mismatch and numeric firmware thresholds remain
diagnostic information. Untrusted strings are JSON-escaped; the app's unsafe
formatter and truncation behavior are not reproduced.

## Product boundary and deferred hardware validation

Wi-Fi/AP/SSID/password provisioning, network configuration and reboot,
HTTP/WebSocket/cloud/account/sleep/alarm infrastructure, DFU/firmware updates,
help/media, speaker/audio and synchronization controls are excluded. This
includes speaker statements in the shipped animation and speaker state fields.
Dead enum mappings and unused UUID/read paths are excluded too. The ledger
contains the exact evidence and rationale for each exclusion.

After a beta or release, real users can validate the selected processor address,
negotiated transport and framing, unit/snapshot physical mapping, climate
heat/cool levels and timer expiry, massage frequencies/durations, local sequence
effects and stop delivery under release, cancel, timeout and disconnect. Captures
must redact challenges and tokens. These are external hardware checks, not
missing static evidence or a requirement for the maintainer to obtain a bed.
