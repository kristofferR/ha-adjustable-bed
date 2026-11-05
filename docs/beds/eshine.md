# Eshine app (E6000)

**Status:** ❓ Needs testing (static verified, hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- E6000 (metadata H3RN), the only product the app offers

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Eshine](https://play.google.com/store/apps/details?id=com.richmat.eshinesleep) 1.0.1 (code 10100) | `com.richmat.eshinesleep` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Head, feet, lumbar and pillow; global STOP |
| Position Feedback | ❌ (motor reports never populate position feedback or sliders) |
| Presets | ✅ Flat, Zero Gravity and Anti-Snore recall, each sent once |
| Save Presets | ✅ **Save Zero Gravity** and **Save Anti-Snore** (named presets, not numbered memory slots) |
| Memory Presets | ❌ |
| Massage | ✅ Head and foot strength, mode, off, 10/20/30-minute actions |
| Lights | ✅ Toggle |
| Reported State | ⚠️ Eleven read-only diagnostic sensors |
| Hold until release | ✅ ([renewable](../SERVICES.md#renewable-holds) `timed_move` and `hold_control`: 100 ms refresh, then STOP) |

- Strength/mode labels do not establish physical cycle levels, persistence or
  discrete on/off values.
- The phone app's three-second gesture chooses save; the bed does not receive a
  three-second stream. Each save button sends its save opcode once.

## Protocol Details

**Format:** compact (one opcode byte) or framed (`6e 01 00 opcode checksum`), chosen by the service endpoint

| Service | Write | Declared notify | Format |
|---|---|---|---|
| `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | compact |
| `0000fee9-0000-1000-8000-00805f9b34fb` | `d44bc439-abfd-45a2-b575-925416129600` | `d44bc439-abfd-45a2-b575-925416129601` | framed |
| `0000fee9-0000-1000-8000-00805f9b34bb` | `d44bc439-abfd-45a2-b575-925416129622` | `d44bc439-abfd-45a2-b575-925416129611` | framed |
| `0000ffe0-0000-1000-8000-00805f9b34fb` | `0000ffe2-0000-1000-8000-00805f9b34fb` | `0000ffe1-0000-1000-8000-00805f9b34fb` | framed |
| `0000fff0-0000-1000-8000-00805f9b34fb` | `0000fff2-0000-1000-8000-00805f9b34fb` | `0000fff1-0000-1000-8000-00805f9b34fb` | framed |
| `0000e0ff-3c17-d293-8e48-14fe2e4da212` | `00000002-3c17-d293-8e48-14fe2e4da212` | `00000003-3c17-d293-8e48-14fe2e4da212` | framed |

### Endpoint Selection

- The controller requires exactly one complete supported service endpoint.
- Within that service it selects the first matching WRITE characteristic and
  the first NOTIFY characteristic, even if its UUID differs from the declared
  notify UUID.
- WRITE is required; WRITE WITHOUT RESPONSE alone is insufficient.
- When both write properties exist, writes use no response. Otherwise they use
  response.
- Multiple complete endpoints are rejected rather than combining the first
  write role with the last service's framing as the app can do.

### Packet Format

- Compact commands contain one opcode.
- Framed commands are `6e 01 00 opcode checksum`, with an additive low-byte
  checksum.

### Session Setup

- After subscribing, setup sends `00` compact or `6e02010071` framed once
  (ExitLimit).
- No challenge, PIN, cipher, heartbeat, state sync or outbound capability query
  exists in this app.
- Notifications remain enabled with angle sensing disabled.
- Reconnect clears partial receive data and observed state before repeating
  setup.
- HA owns Bluetooth adapters/proxies, timeouts and reconnect policy; it does not
  reproduce the phone's five-second scan, MTU request, dialog or local SQLite
  storage.

## Detection / Setup

- Choose **Eshine app (E6000)** manually for `com.richmat.eshinesleep` 1.0.1
  (code 10100).
- Shared Bluetooth names and services do not identify this app, and existing
  Richmat entries keep their own behavior.
- Generic motor count, massage, angle and protocol fields are hidden because
  this profile owns them.

### Home Assistant setup

Choose **Eshine app (E6000)** manually for `com.richmat.eshinesleep`. Its fixed head, feet, lumbar, pillow, massage and light layout does not depend on shared Bluetooth names or received capability flags. Only pulse count remains configurable for movement; refresh is fixed at 100 ms. Named preset saves are separate buttons. A two-address pair preserves this profile per physical bed; single-address side control is unsupported.

## Commands

Framed bytes are shown; compact endpoints send only the opcode.

### Motor Control

| Command | Opcode | Framed | Description |
|---------|--------|--------|-------------|
| Head up / down | `24` / `25` | `6e 01 00 24 93` / `6e 01 00 25 94` | |
| Feet up / down | `26` / `27` | `6e 01 00 26 95` / `6e 01 00 27 96` | |
| Lumbar up / down | `3f` / `40` | `6e 01 00 3f ae` / `6e 01 00 40 af` | |
| Pillow up / down | `41` / `42` | `6e 01 00 41 b0` / `6e 01 00 42 b1` | |
| STOP | `6e` | `6e 01 00 6e dd` | Global STOP for every axis |
| ExitLimit (setup) | `00` | `6e 02 01 00 71` | Sent once after subscribing |

### Presets

| Command | Opcode | Framed |
|---------|--------|--------|
| Flat | `31` | `6e 01 00 31 a0` |
| Zero Gravity | `45` | `6e 01 00 45 b4` |
| Anti-Snore | `46` | `6e 01 00 46 b5` |
| Save Zero Gravity | `66` | `6e 01 00 66 d5` |
| Save Anti-Snore | `69` | `6e 01 00 69 d8` |

### Massage

| Command | Opcode | Framed |
|---------|--------|--------|
| Head massage strength | `4c` | `6e 01 00 4c bb` |
| Foot massage strength | `4e` | `6e 01 00 4e bd` |
| Massage mode | `48` | `6e 01 00 48 b7` |
| Massage off | `5e` | `6e 01 00 5e cd` |
| Massage 10 / 20 / 30 minutes | `5f` / `63` / `61` | `6e 01 00 5f ce` / `6e 01 00 63 d2` / `6e 01 00 61 d0` |

### Lights

| Command | Opcode | Framed |
|---------|--------|--------|
| Light toggle | `3c` | `6e 01 00 3c ab` |

## Actions

- The dashboard card displays motors, presets, lighting, massage and save
  buttons in its existing sections.
- The generic `hold_control` action accepts `head_up`, `head_down`, `feet_up`,
  `feet_down`, `lumbar_up`, `lumbar_down`, `pillow_up` and `pillow_down` for 1
  to 60000 ms.

## Reported State

Eleven diagnostic sensors expose the most recent event name and a dictionary
of observed values: capabilities, motors, massage, light, RGB, alarm, anti-snore,
lock, music, mode and component checks.

- Attributes retain independent numbered motors and component check frames.
- They remain unknown until notifications arrive and are cleared on a new
  connection.
- Event-only acknowledgements are recorded as `true`, meaning observed, not a
  new writable capability.
- No parsed reply enables new commands: the app's E6000 layout is fixed and its
  own UI has no subscribers for these parsed states.
- Motor reports retain the artifact's numeric motor/type, status, angle, height
  and monitor-height fields. Their mapping to physical head/feet/lumbar/pillow
  axes is unproven, so they never populate position feedback or sliders.
- Alarm reports contain six ordered opaque integers. Sleep advertisement names
  remain byte lists.
- Received side modes never enable single-address pairing or send a side
  selector.
- RGB, alarm, anti-snore configuration, lock and music state is read-only; no
  outbound builder is inferred from a receive branch.

### Receive Framing

- Type `20` frames accumulate across notifications and require exact length and
  additive checksum.
- Common frames preserve the app's delimiter and notification boundary behavior,
  including loss of partial common frames and splitting at an embedded `6e`;
  they have no generic checksum rule.
- Malformed lengths and short fields are rejected safely. In particular, the
  accepted audit corrections show that `6e2007060302a0`, `6e2007060303a1`,
  `6e200806050200a3` and `6e200806050300a4` cannot emit parsed anti-snore state.
  HA drops them rather than reproducing Dart range errors.
- The receive buffer has a 65535-byte safety bound; that is not a bed
  packet-size claim.

## Command Timing

- Movement sends a global STOP on completion, cancellation or movement failure.
  All axes share a scheduling resource.
- Normal movement uses the configured pulse count with a fixed 100 ms refresh;
  pulse count bounds the HA operation and is not a hardware limit.
- Presets, saves, light and massage actions are each sent once.
- HA actions start on invocation. Flutter pointer recognition, arena arbitration
  and the first eligible 100 ms callback are phone UI behavior, not a
  requirement for HA to wait for a physical touch.
- HA serializes commands and releases with a fresh cancellation event, avoiding
  the app's queued stale movements and FIFO STOP backlog. No physical STOP
  delivery or latency guarantee is inferred.

## Notes

### Excluded

- Desk data, firmware maintenance/OTA, empty pruned blanket/diagnostic models,
  unused enums and unrelated phone infrastructure are excluded.
- No bed Wi-Fi, provisioning, cloud or account path was found, and those
  features remain outside the direct BLE product boundary.

### Hardware validation

After a beta or release, real users can provide full GATT and notification
captures to verify firmware acceptance, physical axis semantics, massage/light
cycles and STOP behavior. No maintainer hardware acquisition is required.

### Analysis provenance

- This explicit profile follows the independently accepted row106 APK Protocol
  Audit. Static verified, hardware unverified.
- The row106 audit records the evidence, exclusions and safety differences.
