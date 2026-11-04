# Floyd Home

**Status:** ❓ Needs testing (static protocol evidence complete, physical effects unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- Floyd Home beds advertising Kaidi product 139 (`TRANQUILITY_II` in the
  [Kaidi product table](kaidi.md#apk-backed-product-ids))

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Floyd Home](https://play.google.com/store/apps/details?id=com.kaidi_test4.floyd) 1.0.7 (7) | `com.kaidi_test4.floyd` |

- This profile follows that app only. Other Kaidi profiles retain their
  existing behavior.

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (head/back and feet; start, timed hold, release) |
| Presets | ✅ (Flat, Zero gravity, Anti-snore) |
| Memory Presets | ✅ (three recall/save slots) |
| Preset Programming | ✅ (Zero gravity and Anti-snore overwrite, confirmed) |
| Under-bed Lights | ✅ (discrete on/off, no measured state feedback) |
| Battery Mode | ✅ (binary diagnostic) |
| Position Feedback | ❌ (no position sliders or measured angles) |
| Massage | ❌ |
| Extra axes | ❌ |
| Single-address Left/Right | ❌ (no normal single-address Left/Right controls) |

- A battery event can arrive unsolicited; unknown battery mode is not
  interpreted as battery power.
- A reported battery mode blocks raising, but never blocks lowering or release.

## Protocol Details

**Service UUID:** none required by this app (characteristics are found across discovered services)
**Write Characteristic:** `9e5d1e47-5c13-43a0-8635-82adffc1386f`
**Notify Characteristic:** `9e5d1e47-5c13-43a0-8635-82adffc2386f`
**Format:** Kaidi-style frames with a little-endian 32-bit target and own address

### Packet Format

| Packet | Bytes |
| --- | --- |
| Authentication (existing room) | `01 16 01 LE32(room) 31 31 32 32` |
| Ping all | `03 FF FF FF FF FE` + own address (LE32) |
| Control | `03 LE32(target) 20 own_raw[4] 01 opcode parameter 00` |
| Room assignment (unassigned bed) | `01 03 LE32(room) 31 31 32 32 00 00 00 00` |

- `31 31 32 32` is ASCII `1122`.
- Preset overwrite uses `a7` and parameter `01` (ZG) or `04` (snore).
- Subsequent ordinary commands retain that parameter, including across
  connection renewal within the loaded HA entry. A fresh integration load
  starts at zero.
- There is no checksum, framing stream, fragmentation, sequence or invented
  position ACK.

### Write Mode

- HA/Bleak handles the CCCD and chooses a supported write mode from discovered
  properties.
- Physical GATT properties and actual write mode still need user captures.
- Writes are awaited and separated by at least 50 ms, replacing the app's
  unsafe callback queue without a timeout.
- No reachable read, MTU negotiation, Bluetooth bond, PIN exchange or
  encryption protocol is added.

### Session Setup

- Existing rooms authenticate with the authentication packet above.
- Controls are blocked until authentication succeeds and a live ping matches
  the selected node's MAC. Cached/advertised addresses alone never authorize
  controls.
- A ping's zero address is the app's special `-2` sentinel, encoded as zero on
  the wire; a cached zero remains offline.
- Ordinary controls retain signed 32-bit targets; conditional alarm selectors
  require a positive target or the live zero sentinel.
- Own identity starts zero and an explicit zero identity response remaps to
  `ffffffff`.
- Count updates invalidate the node cache; the next action authenticates and
  pings again before issuing a new command.
- Authentication failures and malformed notifications cannot enable movement.
- Disconnect clears link/target and battery state; it does not claim that a
  physical motor has stopped.

## Detection / Setup

- Select **Floyd Home app (product 139)**, or leave Kaidi on Auto when the bed
  advertises product 139.
- Existing Kaidi discovery rules continue to apply to its other profiles.

| Signal | Value |
| --- | --- |
| Manufacturer data prefix | `ff ff c0 ff`, including its company ID |
| Product 139 offset, type `01` | 9 |
| Product 139 offset, type `02` | 17/25 |
| Product 139 offset, type `09` | 15 |
| Type `09` company | `4b44` at offset 11 (little endian) |
| Actuator fields | `(acu >> 8) & 7 <= 5`, `acu & 15 <= 5`, `acu & 0xF0 <= 5` (the artifact's checks) |
| RSSI | at least -92 dBm |

- HA rejects short data rather than reproducing the app's out-of-bounds reads.

### Room assignment

- Unassigned membership assignment uses the room assignment packet above.
- An acknowledged room is persisted inside the assignment operation without
  reloading the entry mid-service.
- Cancellation before acknowledgement cannot persist a room or start addition
  confirmation.
- A stale unassigned advertisement cannot undo that acknowledged room on
  reconnect.
- After an intentional external room reset, reconfigure to refresh saved
  metadata.
- Conflicting-room advertising reset is intentionally excluded for safety: HA
  must not evict an existing room owner through an unauthenticated,
  unacknowledged advertisement. Use the official app for an intentional room
  takeover, then let HA adopt the resulting advertised room.
- This is local BLE administration, not Wi-Fi provisioning.

### Home Assistant setup

Choose **Floyd Home app (product 139)** under the Kaidi transport. Auto selects
this profile for advertised product 139. It owns its two-axis layout and disables
unsupported massage/position controls. Pulse count and delay bound an HA hold,
not a hardware repeat loop. Each physical address keeps its own BLE room and
node metadata; do not copy those fields to another side. This guide
covers confirmation, conditional internal preset
selectors and explicit assignment of an unassigned BLE room.

## Movement and presets

### Movement

- A hold sends one start, waits for the selected duration or cancellation, then
  sends the matching release using the original node address.
- The app does not refresh a held movement. HA always releases on cancellation,
  including abandoned card holds, instead of reproducing the app's missing
  unmount/background release.
- Authentication finishes before the timed-movement window starts.
- Known battery mode is rejected during all-target preflight and rechecked
  before execution.
- Generic movement pulse settings bound the HA hold duration, at most 30
  seconds; they do not introduce repeated hardware starts.
- Use `adjustable_bed.hold_control` with `head_up`, `head_down`, `feet_up`,
  `feet_down`, `head_feet_up` or `head_feet_down` for an explicit duration in
  seconds (maximum 30).

### Presets

- Flat is opcode `1c`, a preset, never the emergency release.
- The combined release is `09`; head and feet release with `03` and `06`.
- Presets, memory writes and lighting are single-shot.
- Memory slots 1 through 3 use the standard buttons and `goto_preset` /
  `save_preset` actions.
- Lighting has no measured state feedback.

### Floyd action

`adjustable_bed.floyd_action` adds these operations:

| Action | Parameters and behavior |
| --- | --- |
| `zero_g`, `flat`, `anti_snore`, `memory_1` to `memory_3` | `internal_side: first` is normal UI behavior. `both` and `second` are conditional preset selectors proven reachable through the installed Android alarm receiver, with hardware effects unverified. They do not imply internal-side movement capability. |
| `save_zero_g`, `save_anti_snore` | Requires `confirm: true`, `internal_side: first`. Overwrites the built-in preset with the current position. |
| `assign_room` | Requires `confirm: true`, a nonzero 32-bit `room_id`, and exactly one standalone bed with an advertisement proving unassigned membership (type `09` or explicit room zero). Assigns **local BLE room membership**, disconnects, authenticates again, pings that node and sends addition confirmation. |
| `confirm_add` | Requires `confirm: true`, `internal_side: first`. Retry addition confirmation if assignment succeeded but its reconnect was interrupted. |

- `side` selects a physical child of a two-address paired HA device.
- `internal_side` selects the separate conditional firmware preset opcode.
- Normal controls use first-side commands for each physical address.
- Selected physical beds all receive a confirmed preset overwrite; HA
  deliberately corrects the app's bug that programs only the last selected
  address. Put each physical bed in the intended position before confirming.
- Placement/room names and phone alarms belong to HA devices and automations,
  not to extra bed commands.

## Commands

Values are the `opcode` byte of the control frame, from
[`beds/floyd.py`](../../custom_components/adjustable_bed/beds/floyd.py)
(`FLOYD_HOLDS`, `FLOYD_PRESETS`, `_FLOYD_PROFILE` and `floyd_action`). The
`parameter` byte is the retained parameter unless stated.

### Motor Control

| Command | Start | Release | Description |
| --- | --- | --- | --- |
| `head_up` / `head_down` | `0x01` / `0x02` | `0x03` | Head (HA back control) |
| `feet_up` / `feet_down` | `0x04` / `0x05` | `0x06` | Feet (HA legs control) |
| `head_feet_up` / `head_feet_down` | `0x07` / `0x08` | `0x09` | Head and feet together |
| Stop all | `0x09` | | Combined release |

### Presets

| Command | `first` | `both` | `second` |
| --- | --- | --- | --- |
| Flat | `0x1C` | `0x1E` | `0x1D` |
| Zero gravity | `0x62` | `0x64` | `0x63` |
| Anti-snore | `0x65` | `0x67` | `0x66` |

`first` is the normal UI; `both` and `second` are the conditional
`internal_side` selectors.

### Memory

| Command | `first` | `both` | `second` |
| --- | --- | --- | --- |
| Recall 1 / 2 / 3 | `0x29` / `0x2A` / `0x2B` | `0x39` / `0x3A` / `0x3B` | `0x31` / `0x32` / `0x33` |
| Save 1 / 2 / 3 | `0x25` / `0x26` / `0x27` | | |

### Preset Programming and Setup

| Command | Opcode | Parameter | Description |
| --- | --- | --- | --- |
| `save_zero_g` | `0xA7` | `0x01` | Overwrite Zero gravity with the current position |
| `save_anti_snore` | `0xA7` | `0x04` | Overwrite Anti-snore with the current position |
| `confirm_add` | `0x45` | retained | Addition confirmation |

### Lights

| Command | Opcode |
| --- | --- |
| Light on | `0x5C` |
| Light off | `0x5D` |

## Notifications / State

| Notification | Meaning |
| --- | --- |
| `02 16` + status | Authentication response; status `0` is accepted |
| `02 03` + status | Room assignment response; status `0` is accepted |
| `01 0A` + own address (LE32) | Own identity; zero remaps to `ffffffff` |
| `01 02` …, count at bytes 8-9 (LE) | Count update; invalidates the node cache |
| `03` …, channel `FF` at byte 5 | Ping reply: bytes 6-11 node MAC, bytes 12-15 signed target (zero becomes the `-2` sentinel); used only when the MAC matches |
| `03` …, channel `20` at byte 5, byte 11 `0xA6` | Battery mode event: byte 12 `1` means battery mode |

Other incoming routes have no bed-state consumer; raw diagnostics retain them.

## Command Timing

- Writes are separated by at least 50 ms.
- Authentication and ping waits time out after 5 seconds.
- A hold sends one start and one release; the duration is at most 30 seconds.

## Notes

- Bed Wi-Fi, cloud, accounts and network administration remain outside this
  integration.
- Deferred beta/release validation covers physical stopping, firmware timeout,
  lighting and preset effects, internal-side selectors, room assignment and
  optional battery events. Maintainer hardware is not required.

### Analysis provenance

| Seal | SHA-256 |
| --- | --- |
| Artifact set | `09001ded373f0b659c6645e7fd94aa963b2cc91a4eb3d2de22d1a0883f177c8f` |
| Accepted REPORT.SHA256 | `455f487d3987a5661124f4f565ae3a99dc29853678f78a6fa7d39baffe2565a4` |
| Independent AUDIT.SHA256 | `be869ca014a1e5cb3f7928d02a103cf1acabcd888f3c115e0ce015b93dab01cf` |

The exhaustive [row117 discovery ledger](../apk-analysis/dispositions/row117-floyd.md)
records evidence, every implemented/equivalent/excluded route and the focused
artifact tests.
