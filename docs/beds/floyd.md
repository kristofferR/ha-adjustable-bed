# Floyd Home

Select **Floyd Home app (product 139)**, or leave Kaidi on Auto when the bed
advertises product 139. This profile follows `com.kaidi_test4.floyd` 1.0.7 (7).
Its static protocol evidence is complete; physical effects remain unverified.
Other Kaidi profiles retain their existing behavior.

The profile exposes head/back and feet movement, Flat, Zero gravity, Anti-snore,
three memory recall/save slots, discrete under-bed lighting and a battery-mode
binary diagnostic. There are no position sliders, measured angles, massage,
extra axes or normal single-address Left/Right controls. A battery event can
arrive unsolicited; unknown battery mode is not interpreted as battery power.
A reported battery mode blocks raising, but never blocks lowering or release.

## Movement and presets

A hold sends one start, waits for the selected duration or cancellation, then
sends the matching release using the original node address. The app does not
refresh a held movement. HA always releases on cancellation, including abandoned
card holds, instead of reproducing the app's missing unmount/background release.
Authentication finishes before the timed-movement window starts. Known battery
mode is rejected during all-target preflight and rechecked before execution.
Generic movement pulse settings bound the HA hold duration, at most 30 seconds;
they do not introduce repeated hardware starts. Use `adjustable_bed.hold_control`
with `head_up`, `head_down`, `feet_up`, `feet_down`, `head_feet_up` or
`head_feet_down` for an explicit duration in seconds (maximum 30).

Flat is opcode `1c`, a preset, never the emergency release. The combined release
is `09`; head and feet release with `03` and `06`. Presets, memory writes and
lighting are single-shot. Memory slots 1 through 3 use the standard buttons and
`goto_preset` / `save_preset` actions. Lighting has no measured state feedback.

`adjustable_bed.floyd_action` adds these operations:

| Action | Parameters and behavior |
| --- | --- |
| `zero_g`, `flat`, `anti_snore`, `memory_1` to `memory_3` | `internal_side: first` is normal UI behavior. `both` and `second` are conditional preset selectors proven reachable through the installed Android alarm receiver, with hardware effects unverified. They do not imply internal-side movement capability. |
| `save_zero_g`, `save_anti_snore` | Requires `confirm: true`, `internal_side: first`. Overwrites the built-in preset with the current position. |
| `assign_room` | Requires `confirm: true`, a nonzero 32-bit `room_id`, and exactly one standalone bed with an advertisement proving unassigned membership (type `09` or explicit room zero). Assigns **local BLE room membership**, disconnects, authenticates again, pings that node and sends addition confirmation. |
| `confirm_add` | Requires `confirm: true`, `internal_side: first`. Retry addition confirmation if assignment succeeded but its reconnect was interrupted. |

`side` selects a physical child of a two-address paired HA device.
`internal_side` selects the separate conditional firmware preset opcode. Normal
controls use first-side commands for each physical address. Selected physical
beds all receive a confirmed preset overwrite; HA deliberately corrects the
app's bug that programs only the last selected address. Put each physical bed
in the intended position before confirming. Placement/room names and phone
alarms belong to HA devices and automations, not to extra bed commands.

## Transport and setup

Manufacturer data starts `ff ff c0 ff` including its company ID. Types `01`,
`02` and `09` carry product 139 at offsets 9, 17/25 and 15 respectively. Type
`09` requires company `4b44` at offset 11 (little endian). Floyd admission checks
the artifact's actuator fields and RSSI at least -92 dBm. HA rejects short data
rather than reproducing the app's out-of-bounds reads. Existing Kaidi discovery
rules continue to apply to its other profiles.

No service UUID is required by this app. It finds write characteristic
`9e5d1e47-5c13-43a0-8635-82adffc1386f` and subscribes to
`9e5d1e47-5c13-43a0-8635-82adffc2386f` across discovered services. HA/Bleak handles
the CCCD and chooses a supported write mode from discovered properties.
Physical GATT properties and actual write mode still need user captures.
No reachable read, MTU negotiation, Bluetooth bond, PIN exchange or encryption
protocol is added.

Existing rooms authenticate with `01 16 01 LE32(room) 31 31 32 32`. Controls are
blocked until authentication succeeds and a live ping matches the selected
node's MAC. Cached/advertised addresses alone never authorize controls. A ping's
zero address is the app's special `-2` sentinel, encoded as zero on the wire;
a cached zero remains offline. Ordinary controls retain signed 32-bit targets;
conditional alarm selectors require a positive target or the live zero sentinel. Own identity starts zero and an explicit zero
identity response remaps to `ffffffff`. Count updates invalidate the node cache;
the next action authenticates and pings again before issuing a new command.

The control frame is `03 LE32(target) 20 own_raw[4] 01 opcode parameter 00`.
Preset overwrite uses `a7` and parameter `01` (ZG) or `04` (snore). Subsequent
ordinary commands retain that parameter, including across connection renewal
within the loaded HA entry. A fresh integration load starts at zero. There is
no checksum, framing stream, fragmentation, sequence or invented position ACK.
Writes are awaited and separated by at least 50 ms, replacing the app's unsafe
callback queue without a timeout. Authentication failures and malformed
notifications cannot enable movement. Disconnect clears link/target and battery
state; it does not claim that a physical motor has stopped.

Unassigned membership assignment is `01 03 LE32(room) 31 31 32 32 00 00 00 00`.
An acknowledged room is persisted inside the assignment operation without
reloading the entry mid-service. Cancellation before acknowledgement cannot
persist a room or start addition confirmation. A
stale unassigned advertisement cannot undo that acknowledged room on reconnect.
After an intentional external room reset, reconfigure to refresh saved metadata.

Conflicting-room advertising reset is intentionally excluded for safety: HA
must not evict an existing room owner through an unauthenticated, unacknowledged
advertisement. Use the official app for an intentional room takeover, then let
HA adopt the resulting advertised room. This is local BLE administration, not
Wi-Fi provisioning. Bed Wi-Fi, cloud, accounts and network administration remain
outside this integration.

The exhaustive [row117 discovery ledger](../apk-analysis/dispositions/row117-floyd.md)
records evidence, every implemented/equivalent/excluded route and the focused
artifact tests. Deferred beta/release validation covers physical stopping,
firmware timeout, lighting and preset effects, internal-side selectors, room
assignment and optional battery events. Maintainer hardware is not required.
