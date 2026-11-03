# Limoss Remote app profile

**Status:** ❓ Needs testing (APK-verified, hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Limoss bed and chair receivers operated by the Limoss Remote app
- Bed layouts with 2, 4, 6, 8, 10 or 12 keys; chair layouts with 2, 4, 6 or 8 keys

The existing generic [Limoss](limoss.md) selection retains its previous behavior.
A shared FFE0 service or device name cannot identify this app profile.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Limoss Remote](https://play.google.com/store/apps/details?id=com.limoss.limossremote) 7.1.8 (44) | `com.limoss.limossremote` |

This profile comes from the independently accepted `com.limoss.limossremote`
7.1.8 (44) artifact. Hardware behavior remains unverified.

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (literal motor channels 1–4, combined, lift and shift, per rendered layout) |
| Position Feedback | ⚠️ (raw signed values only; no unit, angle or slider) |
| Memory Presets | ✅ (up to 8 app-local raw-position slots, device-reported capacity) |
| Factory Presets | ❌ (no named flat, zero-gravity or TV preset) |
| Massage | ✅ (held plus/minus controls when selected; no intensity feedback) |
| Under-bed Lights | ✅ (held light control when selected; no ON/OFF feedback) |
| Calibration | ✅ (confirmed, memory-capable receivers only) |
| Sync, PIN or native bond | ❌ |

## Protocol Details

**Service UUID:** `0000ffe0-0000-1000-8000-00805f9b34fb`
**Write Characteristic:** `0000ffe1-0000-1000-8000-00805f9b34fb`
**Notify Characteristic:** `0000ffe1-0000-1000-8000-00805f9b34fb`
**Format:** 10-byte frame with a TEA-encrypted 8-byte payload

### Packet Format

- The native frame is ten bytes: `DD`, eight encrypted bytes and an outer sum.
- Plaintext is `AA`, five command bytes, one low sequence byte and an inner sum.
- The accepted native library proves 16-round, big-endian TEA arithmetic.

### Sequence

- The source global sequence advances at logical construction, including packets
  whose later write fails; every repeated command and release has a fresh
  sequence.
- Logical batches are constructed together to preserve cross-receiver sequence
  ordering.
- The Java signed-int wrap and low-byte behavior are retained.

### GATT selection and Write Mode

- The source selects the first exact service
  `0000ffe0-0000-1000-8000-00805f9b34fb`, then its first exact characteristic
  `0000ffe1-0000-1000-8000-00805f9b34fb`.
- The selected characteristic must support notification and a write property.
- Each actual write binds that selected object, including after reconnect;
  unsubscribe uses the same object and owning client.
- The app inherits the Android write mode without a proven override. This
  controller uses acknowledged writes when `write` is available, otherwise the
  explicitly advertised `write-without-response` property. This is a host
  transport policy, not a claim about the artifact's inherited mode.

## Detection / Setup

Select **Limoss Remote app** explicitly under Limoss, then choose bed or chair and
its local lamp/massage controls.

### Layout selection

- The receiver supplies key count, system/motor count, configuration and memory
  capacity.
- Recognized system ranges select the app's bed/chair layout; the chosen product
  supplies the fallback for an unknown system code.
- Unsupported key counts use the source's eight-key fallback.
- Configuration 1 selects the eight-key chair's custom Alpha ordering.
- Every rendered lamp/massage combination is retained, including blank cells and
  omitted combined/shift directions.
- Controls use literal motor channels rather than assigning unproven physical
  axes or angle units.

| Product | Layout | Selection |
|---------|--------|-----------|
| Chair | `cKey2`, `cKey4`, `cKey6`, `cKey8` | Key count |
| Chair | `cKey8_customAlpha` | Eight keys and configuration 1 |
| Bed | `gKey2` through `gKey12` | Key count, no optional features |
| Bed | `gKey<n>UnderBedLight` | Lamp selected |
| Bed | `gKey<n>Vibrate` | Massage selected |
| Bed | `gKey<n>BothUnderBedLightVibrate` | Lamp and massage selected |

### Local settings

- Four reversal flags are independent local settings.
- Lamp and massage selections change the available controls, not measured
  hardware state. Enabling a feature changes the local layout without opening a
  Bluetooth link.
- Disabling a previously selected lamp or massage feature first sends ten source
  OFF commands, then saves the selection. Switching a standalone entry away from
  Limoss Remote also turns off its selected optional features before saving the
  new profile. Failed OFF writes leave the saved selection unchanged.
- The settings action supports the same transaction. For paired or multi-target
  service calls, every selected OFF burst must finish before any feature
  selections are saved. A failure or cancellation retains the previous local
  selections even if some hardware writes succeeded.
- Replacing a queued or active OFF transaction also keeps its previous selection;
  a normal scheduler return alone does not establish burst completion.
- Fresh capability updates defer entity reloads through every selected service
  phase, including preflight and terminal persistence. BLE links still release
  between sequential sides. Reloads resume only after the transaction and any
  active sibling command have released their command lanes.
- App artwork themes are retained as a local preference in diagnostics; Home
  Assistant continues to use its own theme and does not copy app artwork.

### Paired beds

- Two-address pairs retain independent profiles, reversal flags, features and
  memories per child.
- Select each receiver’s profile before pairing; unpair first to change those
  profiles or convert the pair to another protocol. Shared paired options do not
  replace child settings.
- This profile has no single-address side selector.

## Commands

Every command body is five bytes before framing. `r1 r2 r3 r4` are the four
reversal flags as 0/1 bytes.

### Held controls

Body: `[opcode, r1, r2, r3, r4]`.

| Control | Opcode | Description |
|---------|--------|-------------|
| `motor_1_up` / `motor_1_down` | `12` / `13` | Motor channel 1 |
| `motor_2_up` / `motor_2_down` | `22` / `23` | Motor channel 2 |
| `motor_3_up` / `motor_3_down` | `32` / `33` | Motor channel 3 |
| `motor_4_up` / `motor_4_down` | `42` / `43` | Motor channel 4 |
| `combined_up` / `combined_down` | `50` / `51` | Combined; down is held, not a flat preset |
| `lift_up` / `lift_down` | `52` / `53` | Lift |
| `shift_up` / `shift_down` | `54` / `55` | Shift |
| `massage_back_plus` / `massage_back_minus` | `60` / `61` | Back massage |
| `massage_foot_plus` / `massage_foot_minus` | `62` / `63` | Foot massage |
| `massage_both_plus` / `massage_both_minus` | `64` / `65` | Both zones |
| `light` | `70` | Under-bed light |

### Release and feature OFF

| Command | Body | Repeats |
|---------|------|---------|
| Movement/recall release | `FF r1 r2 r3 r4` | 5 |
| Calibration release | `03 00 00 00 00` | 5 |
| Lamp OFF | `71 00 00 00 00` | 10, no STOP tail |
| Massage OFF | `66 00 00 00 00` | 10, no STOP tail |

### Memory and calibration

| Command | Body | Description |
|---------|------|-------------|
| Query motor 1/2/3/4 position | `10`/`20`/`30`/`40` `00 00 00 00` | Save capture, one motor at a time |
| Recall motor 1/2/3/4 | `11`/`21`/`31`/`41` + signed big-endian 32-bit value | Held memory batch |
| Calibrate | `05 r1 r2 r3 r4` | Held calibration |

### Information

| Command | Body | Description |
|---------|------|-------------|
| Capabilities | `02 00 00 00 03` | Retried at one-second intervals |
| Hardware version | `00 00 00 00 03` | Optional |
| Software version | `01 00 00 00 03` | Optional |

## Actions

- Motor channels have up/down/stop covers where both directions occur in the
  selected rendered table. Named buttons expose every rendered app action.
- A button or cover activation holds its action for **one second**, a Home
  Assistant policy separate from the app's refresh cadence.
- All actions on a physical receiver share the global motor resource. STOP
  releases that receiver's active control.
- The live layout allowlist gates each action. A combined-down control is a held
  command, not a flat preset.
- The app has no named flat, zero-gravity or TV preset, position slider, massage
  intensity feedback, lamp ON/OFF feedback, synchronization, PIN or native bond
  workflow.
- Light/massage OFF utility buttons send their source ten-frame burst without an
  additional motor release.

### `hold_control`

`adjustable_bed.hold_control` accepts one currently rendered control and a
duration from 0.1 to 60 seconds, with millisecond precision. Available names are:

- `motor_1_up`, `motor_1_down` through `motor_4_up`, `motor_4_down`;
- `combined_up`, `combined_down`, `lift_up`, `lift_down`, `shift_up`, `shift_down`;
- `massage_back_plus`, `massage_back_minus`, `massage_foot_plus`,
  `massage_foot_minus`, `massage_both_plus`, `massage_both_minus`;
- `light`.

Example:

```yaml
action: adjustable_bed.hold_control
data:
  device_id: YOUR_DEVICE_ID
  control: motor_1_up
  duration: 0.5
```

### Calibration and features

- `limoss_remote_calibrate` requires `confirmed: true`, a duration, and a
  memory-capable receiver. It holds the source calibration operation and always
  attempts its five calibration release frames once a command has been
  constructed.
- A calibration reply is reported as **reply received**, not proof of physical
  completion.
- `limoss_remote_features` accepts both `underbed_light` and `massage` booleans.

### Readiness and targeting

- Before held movement, calibration or memory execution, services refresh
  receiver startup and validate every selected physical target before moving any.
- A physical BLE connection does not establish readiness until that session's
  fresh capability query completes; concurrent callers share the same startup
  completion without repeating queries in an already-ready session.
- Sequential pairs release each validation link before opening the next.
- Cached capacities remain available for offline local editing, but cannot admit
  a new movement session. Each execution also rechecks its live receiver layout.
- Target a paired child device or supply `side: left`, `right` or `both` normally.

## Eight local memories

- The device-reported capacity limits slots 1–8. These are app-local captured raw
  positions, not firmware preset writes.
- Save buttons and `save_preset` query each reported motor sequentially, then
  atomically persist the complete captured slot for that physical address. The
  supported capture domain is one to four motors. A failure, timeout or
  cancellation preserves the previous complete slot.
- Unsupported capacity above eight or motor count above four is rejected before
  sending a save/recall command, avoiding source array crashes and an unparsed
  fifth-motor query.
- Recall buttons and `goto_preset` hold a stored memory for one second. For an
  explicit duration, give `goto_preset` a `duration` as well as the `preset`.
- Recall requires a stored motor-1 row. Sparse retained rows for the other
  reported motors are allowed and sent in motor order. Raw signed 32-bit values
  are preserved bit for bit without inventing distance or angle units.
- `limoss_remote_rename_memory` accepts `preset` and `name`. Names are local and
  may be empty. Rename retains all captured positions and updates button labels
  without reconnecting.
- Memory names and positions, and the reported versions and serial, survive
  controller recreation, entry reload, unpair/re-pair and integration restart as
  the physical target's app state, until no entry owns the bed.
- The reported capabilities stay in the config entry because they decide the
  entities.
- Changing the selected protocol preserves the stored app memory data; other
  protocols do not use it. No source-backed clear-memory action exists.

## Command Timing

| Operation | Start | Refresh | Cleanup |
|-----------|-------|---------|---------|
| Ordinary held controls | First poll at 80 ms | 80 ms | Five `FF` releases |
| Memory recall batch | Immediately | Nominally 300 ms | Five `FF` releases |
| Calibration | Immediately | 100 ms | Five `03` releases |
| Lamp/massage OFF | Immediately | Ten frames | None |

- The source's write pump is nominally 80 ms. The controller serializes ATT calls
  and enforces at least 80 ms between write starts, waiting for each call to
  complete.
- Each ATT call has a two-second host deadline; this is not an artifact timing
  claim.
- Ordinary controls ending before the first poll construct no command and send no
  release.
- Memory batches' individual packets use the same 80 ms transport lane.
- A requested duration limits refreshes; cleanup occurs outside that deadline.
- Cleanup uses fresh cancellation events, bounded writes and shielding against
  repeated task cancellation, and attempts all five frames even when an earlier
  release fails. The first command error remains the reported error.

### Information transaction

- After notification subscription, the information transaction requests `02`,
  retries that capability query at one-second intervals, then requests hardware
  `00` and software `01` in reply order.
- The host bounds this transaction to ten seconds, including lane, pacing and
  write waits.
- A fresh `02` reply is required even when capabilities are cached. Restored
  capability values populate offline diagnostic sensors, but do not establish a
  live notification session.
- The app opens controls on that reply, so missing optional hardware/software
  replies may exhaust the remaining host budget without blocking startup.
- A write failure or timeout, cancellation or disconnect still fails the
  transaction; cached capabilities never substitute for a missing fresh reply.
- An explicit information refresh remains strict and reports incomplete metadata.
  Completed diagnostic fields survive later failures and reconstruction.
- Changed capability snapshots refresh the offline layout and request an entity
  reload after the link and paired command lanes are released.
- There are no live Device Information Service reads or idle position queries in
  this profile.

## Notifications / State

| Reply | Parameters | Exposed as |
|-------|------------|------------|
| `00` / `01` | Four bytes | Hardware / software version string |
| `02` | Key count, system, vibration, configuration (high nibble) + memory count (low nibble) | Capability diagnostics |
| `05` | | Calibration **reply received** |
| `06` | Signed big-endian 32-bit | Serial |
| `10` / `20` / `30` / `40` | Signed big-endian 32-bit | Raw motor 1–4 position |

- Notifications may be fragmented or contain multiple frames. The receive path
  finds `DD`, waits for ten bytes and decrypts the inner payload.
- The artifact does not validate either checksum or the decrypted `AA`; the
  admitted parsing domain preserves that behavior.
- The host keeps a bounded buffer per physical receiver, clears it on reconnect,
  and never combines bytes from different receivers.
- Hardware/software versions use the source signed-byte string concatenation.
- Position replies and serial `06` retain signed big-endian 32-bit values.
  Position sensors are explicitly **raw**, have no physical unit, and do not
  create angle sliders or estimated bed positions.
- An unsolicited `06` reply retains its signed serial value; there is no reachable
  serial-query sender.
- A save query accepts matching replies only after its write reaches ATT, after
  waiting for the BLE lane and 80 ms spacing. Pre-query and idle replies can
  update raw diagnostics but cannot contribute to memory capture or issue queries.
- There is no native request ID: a delayed same-opcode reply arriving after
  emission is indistinguishable from the current query’s reply.
- Diagnostics expose raw capability fields, chosen product, exact layout, visible
  opcodes, reversal flags, theme preference, local memories and the app sequence.
- Reported information and acknowledgments never establish authentication,
  measured lamp state, measured massage state or physical motion completion.

## Chair artwork interpretation

The frozen resource images show the following pictured changes. These are source artwork descriptions, not verified actuator assignments. Channel labels remain literal across themes, and custom Alpha changes the rendered order of `12/13` and `42/43`.

| Artwork theme | Command pair | Pictured change (inferred) |
|---|---|---|
| chairs_hc338 / chairs_clear | 12/13 | extended raised leg section / vertical lowered leg section |
| chairs_hc338 / chairs_clear | 22/23 | reclined back / upright back |
| chairs_hc338 / chairs_clear | 32/33 | top headrest segment changes shape/orientation; physical direction uncertain |
| chairs_hc338 / chairs_clear | 42/43 | raised/tilted seat-base / lowered level seat-base |
| chairs_hc314 | 12/13 | vertical lower leg / extended diagonal lower leg; opposite pictured order from hc338 |
| chairs_hc314 | 22/23 | reclined back / upright back |
| chairs_hc314 | 32/33 | inner vertical back segment higher / lower; exact actuator uncertain |
| chairs_hc314 | 42/43 | small headrest cap upright / angled; exact actuator uncertain |
| chairs_legacy | 12/13 | footrest up arrow / footrest down arrow |
| chairs_legacy | 22/23 | back recline arrow / back upright arrow |
| chairs_legacy | 32/33 | whole seat/back assembly tilt up arrow / return down arrow |
| chairs_legacy | 42/43 | seat tilt up arrow / return down arrow |
| all four chair themes | 50/51 and type2_12/type2_13 | combined reclined back and raised footrest / upright back and lowered footrest; type2 filenames selected only by cKey2 |

## Notes

- Physical actuator assignment, hardware timing and real receiver behavior remain
  external validation items after release. They do not defer any statically
  proven reachable control or memory operation.

### Analysis provenance

- The artifact-set hash is
  `5914bd873c4a5911575f85623125ab67c4fc6e34577e0be4359041d26bf88d06`.
- The accepted repair-004 report manifest is
  `1f595cb461818dd4a4661b827a78078c70b040fd7fa62b5a93b58f91945ea16c`;
  accepting independent-audit-004 manifest is
  `9e02c4dbe33ff65c65a3fb8b17ce184aed047a660f4ea284aed86bf0a303f061`.
- Raw artifacts and frozen audit reports remain machine-local.
- The unit040 ledger has 801 rows: 585 implementation rows, 27 already
  implemented pure-cipher rows, and 189 exclusions. The
  [disposition ledger](../apk-analysis/row040-dispositions.md) records each
  exclusion and final code/test binding.

### Exclusions

Excluded behavior includes dead transports/commands, nonrendered cells, Android
OS/UI operations, blind non-CCCD descriptor writes, false readiness, overlapping
ATT/backlog races, multitouch STOP inhibition, surviving producers,
cross-device/unbounded/overread buffers, unsolicited or partial memory mutation,
unsupported array domains, unsynchronized sequence races, cross-device global
preferences, unproven physical state/units and numeric-version UI errors. These
boundaries retain useful commands and raw state while using Home Assistant's
serialized, cancellable lifecycle.
