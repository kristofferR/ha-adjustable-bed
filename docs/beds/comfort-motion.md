# Comfort Motion

**Status:** ❓ Needs testing (APK-verified, hardware not yet verified by real users)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Beds controlled by the Comfort Motion Android app
- Physical layouts: back/legs, back/legs/neck, or back/legs/neck/lumbar
- The app has no model, Bluetooth name, manufacturer or RSSI filter (see
  [Detection / Setup](#detection--setup))

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Comfort Motion](https://play.google.com/store/apps/details?id=com.jiecang.app.android.jiecangbed) 2.2.1 (28) | `com.jiecang.app.android.jiecangbed` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (movement and release; 2/3/4-motor layouts; the two-motor layout also exposes combined back/legs) |
| Position Feedback | ❌ (no motor angle, percentage or movement completion) |
| Presets | ✅ Flat, Zero-G, Anti-Snore |
| Memory Presets | ✅ (two recalls, two saves) |
| Massage | ✅ (independent back and foot levels 0-3, mode cycling, stop; no massage mode number) |
| Lights | ✅ (toggle, with reported light state) |
| Bluetooth Rename | ✅ (G1 only) |
| Wake Sequence | ✅ (`adjustable_bed.jiecang_wake`) |
| Bed Clock / BLE Alarm | ❌ |

Enable massage and light controls only when fitted.

## Protocol Details

| Selection | Service | Write | Notification | Rename |
| --- | --- | --- | --- | --- |
| G1 | `0000ff12-0000-1000-8000-00805f9b34fb` | `0000ff01-0000-1000-8000-00805f9b34fb` | `0000ff02-0000-1000-8000-00805f9b34fb` | `0000ff06-0000-1000-8000-00805f9b34fb` |
| G2 | `88121427-11e2-52a2-4615-ff00dec16800` | `88121427-11e2-52a2-4615-ff00dec16801` | same as write | unavailable |

**Format:** fixed `F1 F1 ... 7E` framed literals. Only the 32 reachable literals
and raw rename are implemented. The observed sum relation across literals does
not establish an arbitrary-frame checksum builder, so no extra command is
synthesized.

### Transport Selection

- **Auto** uses the last complete matching transport in GATT enumeration order,
  retaining both notification subscriptions when both exist.
- Select G1/G2 to pin one. G3 is unsupported by this app.
- Writable name roles are rediscovered per connection; G2 alone cannot reuse an
  old G1 name handle.

### Write Mode

Write response mode comes from the discovered characteristic properties, since
the APK never fixes ATT mode.

### Connection Setup Queries

The app schedules these after service discovery. HA awaits subscription and
serializes the six query attempts.

| Offset | Action | Bytes (hex) |
|--------|--------|-------------|
| 100 ms | Subscribe to notifications | (no write) |
| 200 ms, 300 ms | Actuator query | `F1 F1 00 01 01 02 7E` |
| 400 ms, 500 ms | Hardware query | `F1 F1 00 01 40 41 7E` |
| 600 ms, 700 ms | Massage query | `F1 F1 00 01 08 09 7E` |

- Queries run without a layout or massage gate, including with massage disabled.
- These are scheduled duplicate writes, not ACK retries.
- HA cancels failed setup and cleans subscriptions instead of allowing old
  Android timers to write after a reconnect. The next connection gets a fresh
  batch.

## Detection / Setup

1. Select **Jiecang (ERGOBALANCE / Dream Motion / Comfort Motion apps)**, then
   **Comfort Motion**.
2. Choose the physical layout used in the app: back/legs, back/legs/neck, or
   back/legs/neck/lumbar.
3. Enable massage and light controls only when fitted.

- Shared Bluetooth UUIDs do not identify the app.
- Existing legacy Jiecang/Comfort Motion entries retain their original
  controller ([Jiecang](jiecang.md)); select this explicit profile in options to
  use the audited app behavior.
- These settings belong to one physical bed and remain independent across a
  two-address pair.
- The app scans only G1's service, with no name/manufacturer/RSSI restrictions.
  Its barcode and saved-address routes also reach G2.
- HA uses its own Bluetooth scanner and manual address selection; select this
  app explicitly, including for G2. No new automatic app identification is
  inferred.
- The login-named role has no authentication consumer. There is no PIN, bonding
  or login exchange.

## Commands

The [discovery ledger](../apk-analysis/dispositions/row115-comfort-motion.md)
accounts for every accepted command, unused literal, variant and state path.

### Motor Control

| Command | Bytes (hex) | Layouts |
|---------|-------------|---------|
| Back Up | `F1 F1 01 01 01 03 7E` | All |
| Back Down | `F1 F1 02 01 01 04 7E` | All |
| Legs Up | `F1 F1 03 01 01 05 7E` | All |
| Legs Down | `F1 F1 04 01 01 06 7E` | All |
| Back/Legs Up | `F1 F1 05 01 01 07 7E` | Two-motor |
| Back/Legs Down | `F1 F1 06 01 01 08 7E` | Two-motor |
| Neck Up (HA `head` axis) | `F1 F1 19 01 01 1B 7E` | Three- and four-motor |
| Neck Down (HA `head` axis) | `F1 F1 1A 01 01 1C 7E` | Three- and four-motor |
| Lumbar Up | `F1 F1 1B 01 01 1D 7E` | Four-motor |
| Lumbar Down | `F1 F1 1C 01 01 1E 7E` | Four-motor |
| Release / Stop | `F1 F1 4E 00 4E 7E` | All |

Motion and normal preset recall end with `F1F14E004E7E`, the observed release.

### Presets

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Flat | `F1 F1 08 01 01 0A 7E` | Sent once, release after 100 ms |
| Zero-G | `F1 F1 07 01 01 09 7E` | Sent once, release after 100 ms |
| Anti-Snore | `F1 F1 09 01 01 0B 7E` | Sent once, release after 100 ms |

### Memory

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Memory 1 Recall | `F1 F1 0B 01 01 0D 7E` | Sent once, release after 100 ms |
| Memory 2 Recall | `F1 F1 0D 01 01 0F 7E` | Sent once, release after 100 ms |
| Memory 1 Save | `F1 F1 0A 01 01 0C 7E` | Sent once, without release |
| Memory 2 Save | `F1 F1 0C 01 01 0E 7E` | Sent once, without release |

### Massage

| Command | Level 0 | Level 1 | Level 2 | Level 3 |
|---------|---------|---------|---------|---------|
| Back (HA `head` zone) | `F1 F1 12 02 08 00 1C 7E` | `F1 F1 12 02 08 02 1E 7E` | `F1 F1 12 02 08 03 1F 7E` | `F1 F1 12 02 08 04 20 7E` |
| Foot | `F1 F1 14 02 08 00 1E 7E` | `F1 F1 14 02 08 02 20 7E` | `F1 F1 14 02 08 03 21 7E` | `F1 F1 14 02 08 04 22 7E` |

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Massage Mode | `F1 F1 16 01 0A 21 7E` | One fixed command, without a release or an invented mode number |
| Massage Stop | `F1 F1 11 01 08 1A 7E` | Stop massage |

- Massage sliders use 0/1/2/3 for wire values 0/2/3/4.
- Up/down uses the last tag06 state; bounds do nothing. Unrecognized wire
  levels leave the slider unknown and make stepping a no-op.
- Writes do not optimistically change reported state.
- Massage stop (`F1F11101081A7E`) differs from movement release.

### Lights

| Command | Bytes (hex) | Description |
|---------|-------------|-------------|
| Light Toggle | `F1 F1 0F 00 0F 7E` | The only light command |

- On/off actions toggle only when the last reported state differs; they refuse
  unknown state.
- The native toggle remains available before feedback.
- Neither writes nor disconnects fabricate feedback.

### Rename

`adjustable_bed.rename` accepts 1..18 ASCII letters, digits, dots and
underscores and writes the bare bytes to the discovered G1 name role
(`0000ff06-...`). There is no name acknowledgment. This does not change HA's
local device name.

### Excluded Literals

The third memory, massage-start, timer/reset and extra intensity literals have
no reachable caller and are excluded.

## Notifications

Notifications are consumed per callback without frame validation or assembly:

| Tag at byte 2 | Minimum length | Consumed fields |
| --- | --- | --- |
| `0F` | 7 bytes | byte 4: layout 1..6, otherwise 0 |
| `05` | 9 bytes | byte 8, bit 6: light on |
| `06` | 9 bytes | byte 4: unsigned back massage; byte 6: unsigned foot massage; byte 8, bit 6: light on |

- Other/short/empty values are ignored safely. No motor positions are decoded.
- Layout 1/2 describes two motors, 3/4 three, and 5/6 four; even values
  initially show massage navigation. These are app UI layouts, not continuing
  write gates.
- The app retains motor selection, massage zone/intensity and active panels
  through repeated, changed or invalid layouts and same-instance reconnect.
- HA keeps explicitly selected axes stable, retains reported state across its
  controller replacement on reconnect, and never clears massage or light state
  on a layout reply.
- The latest reported layout and raw intensity values remain in protocol
  diagnostics.
- A user can change physical layout or massage presence in options without
  relying on the app's stale-selector behavior.

## Command Timing

| Action | Timing |
|--------|--------|
| Movement | Refreshes every 100 ms for HA's configured pulse count, then release 100 ms after the last frame |
| Explicit STOP | Release sent immediately |
| Presets and memory recall | Sent once, release after 100 ms |
| Memory save | Sent once, without release |

HA also releases on cancellation and exceptions. Physical emergency-stop
semantics are unproven.

## Automations and wake

Use `adjustable_bed.jiecang_wake` with `preset` set to `memory_1`, `memory_2`,
`zero_g`, `flat` or `anti_snore`, and optional `head_level`/`foot_level` 0..3.

| Offset | Action |
|--------|--------|
| 0 ms | Back massage at `head_level`, release 100 ms later (zero skips the zone) |
| 200 ms | Foot massage at `foot_level`, release 100 ms later (zero skips the zone) |
| 500 ms | Preset, without a subsequent release, as on the app's conditional alarm path |

- Cancellation always releases; stop the massage with
  `adjustable_bed.jiecang_stop_wake`.
- Massage must be enabled before using nonzero levels.
- Yoga is unsupported and rejected before writes.
- Schedule the service using HA automations. Android's alarm tab is unreachable
  in this version, while its exported start/stop broadcasts and possibly old
  WorkManager jobs can still execute the sequence.
- There is no BLE alarm programming or clock-setting command.

## Notes

### Safety Adaptations

- The app misses releases on touch cancel, keyboard release and teardown, and
  can emit a final movement after release. HA does not reproduce these unsafe
  lifecycle bugs.
- HA never allows old Android setup timers to write after a reconnect (see
  [Connection Setup Queries](#connection-setup-queries)).

### Exclusions

- Android notifications, weekday filtering, preferences, QR camera, Play updates
  and GIF rendering are companion-app infrastructure.
- Wi-Fi provisioning, cloud/accounts, networking and bed firmware updates are
  excluded product domains, with no reachable bed implementation found in this
  delivery.
- These exclusions are not feature debt.

### Analysis provenance

- This implementation uses the independently accepted row115 report and audit
  seals recorded in the committed
  [ledger](../apk-analysis/dispositions/row115-comfort-motion.md).
- Focused source-vector tests cover all 24 transport/layout/light variants, all
  33 actions, unsigned response values, query setup and cleanup, cancellation,
  state retention, actual HA entities, serialized service routes, and rejected
  settings.
- Physical actuator effects, ATT properties, release effects, mode names and
  rename persistence remain validation for real users after beta/release;
  maintainers need not acquire a bed.
