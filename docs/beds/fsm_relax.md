# FSM Relax app profile

**Status:** ❓ Needs testing (APK-verified, hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Chairs and beds operated by the FSM Relax app, on Limoss-style FFE0 receivers
- Existing Limoss/Stawett entries keep their existing controller and settings.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [FSM Relax](https://play.google.com/store/apps/details?id=com.limoss.fsmrelax) 1.9 (20) | `com.limoss.fsmrelax` |

This profile is verified against the Android artifact, with physical hardware
unverified.

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (held app actions from the exact source tables) |
| Position Feedback | ⚠️ (raw signed motor values only; no unit, angle, percentage or slider) |
| Memory Presets | ✅ (up to 8 device-local slots, raw targets stored in HA) |
| Flat Preset | ❌ (no firmware Flat preset is inferred) |
| Massage | ⚠️ (held plus/minus actions in the bed layout; no six-zone toggle or measured state) |
| Under-bed Lights | ⚠️ (held control in the bed layout; no on/off state, RGB, brightness or timer) |
| Calibration | ✅ (`fsm_relax_calibrate`, confirmation required) |
| Pairing / bonding | ❌ (no OS bond or pairing step) |

## Protocol Details

**Service UUID:** `0000ffe0-0000-1000-8000-00805f9b34fb`
**Write Characteristic:** `0000ffe1-0000-1000-8000-00805f9b34fb` (single write/notify role)
**Notify Characteristic:** `0000ffe1-0000-1000-8000-00805f9b34fb`
**Format:** 10-byte frame: `DD` + 8 TEA-encrypted bytes + additive sum

### Packet Format

- A five-byte body is framed as AA/body/low-eight-bit counter/additive sum.
- That inner block is encrypted as two big-endian 32-bit words using 16 TEA rounds
  and embedded key `55551494 74385555 55551494 74385555`.
- The outer frame is DD/encrypted 8/additive sum.
- Pure encryption and decryption reuse the separately vector-proven existing
  codec; high-level Limoss timing, normalization, capabilities and memory behavior
  are not inherited.

### Counter

- Each attempted write gets a fresh counter, wrapping 255→0.
- Per-device process state retains the counter across controller
  replacement/reconnect; a cold HA process starts at zero.
- Devices have separate counters and memory-operation locks.

### Write Mode

- Every write uses `response=False`, even when the characteristic advertises only
  generic write properties.
- Source code does not inspect those property bits; HA reports actual transport
  failures instead of inventing a profile rejection.
- Subscription uses Bleak, without guessed descriptor UUIDs, GATT reads,
  MTU/priority changes, authentication or bond commands.

## Detection / Setup

Select **FSM Relax app (explicit chair/bed profile)** for devices operated by
`com.limoss.fsmrelax` 1.9 (20).

- Shared advertisements and FFE0 services cannot identify which app layout a
  device uses.
- The exact case-sensitive lowercase `limoss` name route adds an ambiguous
  candidate, requiring explicit selection. The focused chooser also applies when
  that candidate advertises FFE0.
- After profile selection, setup uses normal connection verification when
  available; it does not request an OS bond or enter a pairing step for this
  profile.
- The source also checks complete raw scan-record text at an index greater than
  zero and rejects null names; HA does not expose that complete Android record, so
  it is never reconstructed from unrelated advertisement fields.

### Configuration

- Choose the app's chair or bed layout explicitly. Chair is the app default.
- The bed layout has separate optional light and massage settings.
- Four reversal flags are local configuration and become four unchanged 0/1 bytes
  in held controls, release and calibration.
- Vibration count, versions and serial never select a layout or enable a feature.
- Layout labels describe the app's icons; physical wiring is unverified.

### Capabilities

| Capability byte | Meaning |
|-----------------|---------|
| Key count | 2/4/6/8 keys; any other byte falls back to 8 |
| Vibration count | Reported only; selects nothing |
| Memory count | Unsigned big-endian 16-bit; HA exposes up to eight device-local slots |

- Half the key count selects 1–4 raw memory motors.
- Valid capabilities enable controls immediately. Optional hardware/software
  queries cannot revoke those capabilities on timeout.

## Commands

Bodies are five bytes before framing. `r1 r2 r3 r4` are the four reversal flags.

### App actions

Held actions send `[opcode, r1, r2, r3, r4]`. Each appears as `command_XX` (for
example `command_12`) and as a native button.

| Opcode | Bed label | Chair label |
|--------|-----------|-------------|
| `12` / `13` | Back up / down | Footrest up / down |
| `22` / `23` | Legs up / down | Chair back up / down |
| `32` / `33` | Tilt up / down | |
| `50` / `51` | Combined up / down | Combined up / down |
| `52` / `53` | Elevation up / down | |
| `54` / `55` | All regions up / down | |
| `60` / `61` | Back massage plus / minus | |
| `62` / `63` | Legs massage plus / minus | |
| `64` / `65` | Both massage plus / minus | |
| `70` | Underbed light control | |

These are intended app labels, not verified hardware semantics. Light/massage
controls are held actions with no invented boolean or measured state.

### Layout tables

The exact source tables select the buttons, in this order, including asymmetric
tables where light replaces a combined direction.

| Layout | No options | Light | Massage | Light and massage |
|--------|------------|-------|---------|-------------------|
| Bed, 2 keys | `12 13` | `12 13 70` | `12 13 60 61 62 63` | `12 13 64 65 70` |
| Bed, 4 keys | `12 13 22 23 50 51` | `12 13 22 23 70 51` | `12 13 22 23 60 61 62 63` | `12 13 22 23 70 51 64 65` |
| Bed, 6 keys | `12 13 22 23 32 33 54 55` | `12 13 22 23 32 33 70 54` | `12 13 60 22 23 61 32 33 62 54 55 63` | `12 13 64 22 23 65 32 33 70 54 55` |
| Bed, 8 keys | `12 13 22 23 50 51 52 53` | `12 13 70 22 23 50 51 52 53` | `12 13 60 22 23 61 50 51 62 52 53 63` | `12 13 64 22 23 65 50 51 70 52 53` |
| Chair, 2 keys | `50 51` | | | |
| Chair, 4/6/8 keys | `22 23 12 13 50 51` | | | |

### Release

| Command | Body | Repeats |
|---------|------|---------|
| Held-control release | `FF r1 r2 r3 r4` | 5 |
| Memory-recall release | `03 00 00 00 00` | 5 |

### Memory and calibration

| Command | Body | Description |
|---------|------|-------------|
| Query motor 1/2/3/4 position | `10`/`20`/`30`/`40` `00 00 00 00` | One attempt per motor |
| Recall motor 1/2/3/4 | `11`/`21`/`31`/`41` + signed big-endian 32-bit target | Once per available motor |
| Calibrate | `05 r1 r2 r3 r4` | One frame, never retried |

### Information

| Command | Body |
|---------|------|
| Capabilities | `02 00 00 00 03` |
| Hardware version | `00 00 00 00 03` |
| Software version | `01 00 00 00 03` |

## Actions

- Each available app action has a native button and appears in the card's
  utility section.
- No firmware Flat preset, physical-axis slider, six-zone massage toggle, light
  on/off state, RGB, brightness, or timer is inferred.
- Use `adjustable_bed.hold_control` to specify a hold duration:

```yaml
action: adjustable_bed.hold_control
data:
  device_id: YOUR_DEVICE_ID
  control: command_12
  duration: 1.2
```

- Available `command_XX` names appear in protocol diagnostics as `held_controls`.
- All three FSM Relax action forms expose `side:both/left/right`. A child device
  retains its physical side; a paired parent defaults to both unless a side is
  selected.

### Calibration

- `adjustable_bed.fsm_relax_calibrate` requires `confirmed:true`.
- It sends one 05 frame with all four configured reversal flags and never
  automatically retries. A failed write does not prove hardware did nothing.
- Response 05 records an observed calibration notification, without claiming
  measured calibration success.

## Local memories

### Save

- Save Memory 1–8 reads each reported raw motor in index order, issuing a new
  query immediately after the preceding expected reply.
- It atomically stores the complete set in a physical-address-specific HA storage
  record, retained across combine and unpair ownership changes and removed only
  after its final entry is removed.
- Signed 32-bit values have no known physical units, scaling, angle or percentage.
- Slots map to local groups 0–7; the slot number is never sent over BLE.
- An unsolicited response updates raw diagnostics but never saves a slot.

### Recall

- Memory buttons and `goto_preset` recall stored targets once per available motor.
  Motor zero must exist; absent later motor rows are skipped.
- The default button hold is the configured motor pulse count multiplied by 60 ms.
  This is a local HA gesture policy, not an app-proven autonomous preset duration
  or arrival deadline.
- Use `adjustable_bed.goto_preset` with `preset:1..8` and an explicit `duration` in
  seconds to choose that policy.
- A normal release follows remaining queued targets. Cancellation preempts unsent
  targets and still attempts all five memory-release frames.
- `goto_preset`, with or without `duration`, validates every target's stored
  motor-zero row, signed raw values and quarantine before any bed moves.
- Valid persisted targets can be validated while offline; execution still
  requires a fresh live capability subscription. A connected controller without
  that readiness fails preflight.

### Reply correlation and quarantine

- There is no proven echoed request ID or counter correlation. Local
  expected-opcode and connection guards do **not** guarantee a reply is fresh.
- After timeout, cancellation or an uncertain memory write, HA retains prior slots
  and quarantines memory operations until the connection is replaced and a fresh
  subscription and capability response are obtained.
- Merely resubscribing on the same connection does not clear quarantine.
- A device-retained reply after reconnect, or a delayed byte-identical reply
  during a new same-opcode request, may still be indistinguishable.
- Acknowledgement 04 is observed only and cannot prove physical arrival.

### Names and persistence

- Options expose exactly eight local memory names. A blank field resets that slot
  to M1–M8. Editing/resetting names never writes BLE.
- Names are entry options and the capability snapshot is entry data; raw targets
  and the serial are app state for the physical bed.
- All survive HA restart/controller replacement, and removing the last entry that
  owns the bed removes its app state.
- Within one HA entry and physical address, live and cached offline controllers
  share current saved slots, names, capabilities and serial data. Reconnecting or
  replacing that target does not leave recall preflight with a stale slot
  snapshot.
- Different addresses and entry owners retain separate runtime models; profile
  settings remain controller-local. Ownership transfers load the retained physical
  store, and final removal clears its cached models as well as the stored record.
- Identical capability snapshots and serial observations skip storage writes.
- A memory save persists atomically; a failed write retains the previous value.
- Fresh live capability readiness is required on each connection.
- Unsolicited signed serial 06 is remembered, without inventing a serial query.

## Command Timing

| Operation | Timing |
|-----------|--------|
| Held controls | Start at 60 ms, repeat at nominal 60 ms offsets |
| Default button hold | Motor pulse count × 60 ms |
| Release | Five frames at 60 ms offsets from one monotonic release origin |
| Capability query | Retries at nominal 1000 ms offsets within a bounded four-second HA setup window |
| Optional hardware/software queries | Start 120 ms after the preceding response |
| Position-save query | One attempt per motor, bounded one-second HA response wait |

- Capability/HW/SW requests are 02/00/01 followed by `00 00 00 03`.
- Optional stages take the command lock only for each write and wait outside that
  lock.
- Position-save requests 10/20/30/40 have four zero bytes. The timeout is a safety
  bound, not an artifact-proven success/failure deadline.
- Release sends five FF frames with reversals; recall release sends five 03/zero
  frames. All cleanup attempts use fresh cancellation events and one monotonic
  release origin, survive repeated cancellation and attempt remaining frames after
  an earlier write failure.
- Writes remain serialized. Late BLE writes are attempted when possible, so
  nominal deadlines are not a promise of physical timing.

## Notifications / State

| Reply | Exposed as |
|-------|------------|
| `00` / `01` | Hardware / software version string |
| `02` | Capabilities (key count, vibration count, reported memory count) |
| `04` | Acknowledgement observed, not correlated to physical arrival |
| `05` | Calibration observed |
| `06` | Signed serial |
| `10` / `20` / `30` / `40` | Raw signed motor values |

- Notifications are buffered per controller with bounded storage,
  fragment/coalesced support, header and both checksum validation.
- Raw motor and serial fields are signed big-endian 32-bit.
- Version strings preserve signed-byte concatenation: nonnegative first byte,
  signed second byte, dot, optional nonnegative third/fourth bytes. `01 80 02 ff`
  therefore becomes `1-128.2`.
- Unknown opcodes are ignored.

## BLE and lifecycle

- A link drop fails pending queries with a connection error so initialization can
  use the coordinator's remaining retries. Explicit caller cancellation still
  propagates as cancellation.
- An offline controller without a capability snapshot has incomplete entity
  discovery.
- A loaded entry's first persisted capability response requests the existing
  deferred reload after link release, including the parent of a pair, so native
  actions and memories appear without a manual reload. Initial setup builds its
  platforms from that first response without scheduling an unnecessary reload.
- Old connection callbacks cannot overwrite the current session. Entry-owned
  background query/metadata tasks stop on teardown.

## Notes

- Physical GATT compatibility, wiring, raw units, calibration outcome, optional
  light/massage effects and real-device timing remain deferred validation for
  users after a beta or release.
- Static implementation is complete only after its independent implementation
  audit and integration PR converge; analysis acceptance alone does not mark
  implementation merged.

### Analysis provenance

[The complete 315-row disposition index](../apk-analysis/dispositions/075-fsm-relax.md)
records 164 implemented items, 5 already implemented pure codec items and 146
explicit exclusions. Tests cover all 43 frozen wire vectors, all 20 exact layout
tables, every key-count byte, signed/raw parsing, GATT role boundaries,
persistence, entity/action exposure, cancellation, timing and reply-correlation
limits.
