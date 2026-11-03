# Eshine app (E6000)

Choose **Eshine app (E6000)** manually for `com.richmat.eshinesleep` 1.0.1
(code 10100). This explicit profile follows the independently accepted row106
APK Protocol Audit. **Static verified, hardware unverified.** Shared Bluetooth
names and services do not identify this app, and existing Richmat entries keep
their own behavior. The complete [discovery disposition ledger](../apk-analysis/dispositions/row106-eshine.md)
records the evidence, exclusions and safety differences.

## Controls

The app offers one product, E6000 (metadata H3RN), with these fixed controls:

- Head, feet, lumbar and pillow movement, with a global STOP on completion,
  cancellation or movement failure. All axes share a scheduling resource.
- Flat, Zero Gravity and Anti-Snore recall, each sent once.
- Separate **Save Zero Gravity** and **Save Anti-Snore** buttons, each sending
  its save opcode once. The phone app's three-second gesture chooses save;
  the bed does not receive a three-second stream. These are named presets,
  not numbered memory slots.
- Light toggle, head and foot massage strength actions, massage mode, massage
  off, and the app's 10/20/30-minute massage actions. Strength/mode labels do
  not establish physical cycle levels, persistence or discrete on/off values.

The dashboard card displays motors, presets, lighting, massage and save
buttons in its existing sections. The generic `hold_control` action accepts
`head_up`, `head_down`, `feet_up`, `feet_down`, `lumbar_up`, `lumbar_down`,
`pillow_up` and `pillow_down` for 1 to 60000 ms. Normal movement uses the
configured pulse count with a fixed 100 ms refresh; pulse count bounds the HA
operation and is not a hardware limit. Generic motor count, massage, angle and
protocol fields are hidden because this profile owns them.

HA actions start on invocation. Flutter pointer recognition, arena arbitration
and the first eligible 100 ms callback are phone UI behavior, not a requirement
for HA to wait for a physical touch. HA serializes commands and releases with a
fresh cancellation event, avoiding the app's queued stale movements and FIFO
STOP backlog. No physical STOP delivery or latency guarantee is inferred.

## Connection and packets

The controller requires exactly one complete supported service endpoint. Within
that service it selects the first matching WRITE characteristic and the first
NOTIFY characteristic, even if its UUID differs from the declared notify UUID.
WRITE is required; WRITE WITHOUT RESPONSE alone is insufficient. When both
write properties exist, writes use no response. Otherwise they use response.
Multiple complete endpoints are rejected rather than combining the first
write role with the last service's framing as the app can do.

| Service | Write | Declared notify | Format |
|---|---|---|---|
| `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | compact |
| `0000fee9-0000-1000-8000-00805f9b34fb` | `d44bc439-abfd-45a2-b575-925416129600` | `d44bc439-abfd-45a2-b575-925416129601` | framed |
| `0000fee9-0000-1000-8000-00805f9b34bb` | `d44bc439-abfd-45a2-b575-925416129622` | `d44bc439-abfd-45a2-b575-925416129611` | framed |
| `0000ffe0-0000-1000-8000-00805f9b34fb` | `0000ffe2-0000-1000-8000-00805f9b34fb` | `0000ffe1-0000-1000-8000-00805f9b34fb` | framed |
| `0000fff0-0000-1000-8000-00805f9b34fb` | `0000fff2-0000-1000-8000-00805f9b34fb` | `0000fff1-0000-1000-8000-00805f9b34fb` | framed |
| `0000e0ff-3c17-d293-8e48-14fe2e4da212` | `00000002-3c17-d293-8e48-14fe2e4da212` | `00000003-3c17-d293-8e48-14fe2e4da212` | framed |

Compact commands contain one opcode. Framed commands are
`6e 01 00 opcode checksum`, with an additive low-byte checksum. After subscribing,
setup sends `00` compact or `6e02010071` framed once (ExitLimit). No challenge,
PIN, cipher, heartbeat, state sync or outbound capability query exists in this
app. Notifications remain enabled with angle sensing disabled. Reconnect
clears partial receive data and observed state before repeating setup. HA owns
Bluetooth adapters/proxies, timeouts and reconnect policy; it does not reproduce
the phone's five-second scan, MTU request, dialog or local SQLite storage.

## Reported state

Eleven diagnostic sensors expose the most recent event name and a dictionary
of observed values: capabilities, motors, massage, light, RGB, alarm, anti-snore,
lock, music, mode and component checks. Attributes retain independent numbered
motors and component check frames. They remain unknown until notifications
arrive and are cleared on a new connection. Event-only acknowledgements are
recorded as `true`, meaning observed, not a new writable capability. No parsed
reply enables new commands: the app's E6000 layout is fixed and its own UI has
no subscribers for these parsed states.

Motor reports retain the artifact's numeric motor/type, status, angle, height
and monitor-height fields. Their mapping to physical head/feet/lumbar/pillow
axes is unproven, so they never populate position feedback or sliders. Alarm
reports contain six ordered opaque integers. Sleep advertisement names remain
byte lists. Received side modes never enable single-address pairing or send a
side selector. RGB, alarm, anti-snore configuration, lock and music state is
read-only; no outbound builder is inferred from a receive branch.

Type `20` frames accumulate across notifications and require exact length and
additive checksum. Common frames preserve the app's delimiter and notification
boundary behavior, including loss of partial common frames and splitting at
an embedded `6e`; they have no generic checksum rule. Malformed lengths and
short fields are rejected safely. In particular, the accepted audit corrections
show that `6e2007060302a0`, `6e2007060303a1`, `6e200806050200a3` and
`6e200806050300a4` cannot emit parsed anti-snore state. HA drops them rather
than reproducing Dart range errors. The receive buffer has a 65535-byte safety
bound; that is not a bed packet-size claim.

Desk data, firmware maintenance/OTA, empty pruned blanket/diagnostic models,
unused enums and unrelated phone infrastructure are excluded. No bed Wi-Fi,
provisioning, cloud or account path was found, and those features remain outside
the direct BLE product boundary.

After a beta or release, real users can provide full GATT and notification
captures to verify firmware acceptance, physical axis semantics, massage/light
cycles and STOP behavior. No maintainer hardware acquisition is required.
