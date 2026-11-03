# Reverie

**Status:** ❓ Needs testing (protocol implementation candidate; hardware behavior unverified on a bed)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), Vitaliy and [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt)

## Known Models

- Reverie 9T / 8Q / 7S and other Reverie adjustable bases.
- Protocol 110 exposes an explicit app-model option
  with 44 selectable rows: 3E, 5D, 7S, 8Q, 3E Low Pro, 3ET, 3EW, 3EM, 3EMT, 4M,
  4M Low Pro, 4MM, 6S, 7T, 7HT, 8X, 8T, 9T, STK, O300, O300T, O350LP, O400,
  R350LP, R400, R450, Harmoniq Upgrade, R450HT, R550, R510L, R550L, R650,
  Skye 300, Skye 500, Skye 800, Oasis 2.0, Purple Power Base, Other, R310,
  R310LP, R310T, R310TLP, R410, and R410LP. `Other` is the explicit fallback.
  O450 and Base occur in the app enum but are not selectable there and are not
  offered as setup choices.

## Apps

| Analyzed | App | Package ID |
| --- | --- | --- |
| ✅ | [Reverie Nightstand](https://play.google.com/store/apps/details?id=com.reverie.reverie) 3.3.3.8 | `com.reverie.reverie` |

## Features

| Feature | Protocol 108 | Protocol 110 / STK | Pairlink |
| --- | --- | --- | --- |
| Motor Control | ✅ (head/back, foot/legs) | ✅ (head, foot; lumbar/body tilt by model) | ✅ (back, legs; lumbar on R510L) |
| Position Feedback | ✅ (nine-byte notifications, 0–100%) | ✅ (characteristic / selected-side feedback, 0–100%) | ✅ (current authenticated peer) |
| Memory Presets | ✅ (recall/save 1–4, model-gated) | ✅ (recall/save 1–4, model-gated) | ✅ (recall 1–4; save unavailable) |
| Massage | ✅ (head/foot 0–10, wave compatibility control) | ✅ (model-gated head/foot 0–10, wave controls) | ✅ (head/foot 0–10, mode/rhythm, raw timer code) |
| Wave Massage | ✅ (decimal-text builder; no inferred protocol range/cycle) | ✅ (raw characteristic / STK side-specific controls) | See mode/rhythm controls |
| Under-bed Lights | ✅ (toggle, model-gated) | ✅ (brightness/RGB, model-gated) | ✅ (on/off, level, RGB feedback) |
| Zero-G / Anti-Snore / Flat | ✅ (model-gated) | ✅ (model-specific preset route) | ✅ |
| Composer routines / diagnostics | ✅ (per-address lifecycle) | ✅ (model-gated per-address lifecycle) | ✅ (central or explicit local role) |
| Local BlueZ peripheral role | Not used | Not used | ✅ (explicit setup; active authenticated subscribed peer required) |

Capabilities describe implementation, not hardware confirmation. The selected
app model remains the source of feature gates.

## Protocol Details

| Route | Service UUID | Write / control | Notify |
| --- | --- | --- | --- |
| Protocol 108 | `1b1d9641-b942-4da8-89cc-98e6a58fbd93` | `6af87926-dc79-412e-a3e0-5f85c2d55de2` | Same characteristic |
| Protocol 110 / STK | `db801000-f324-29c3-38d1-85c0c2e86885` | Separate characteristics in the command table | Per-characteristic feedback |
| Pairlink | Primary / low-power profiles in [Pairlink central route](#pairlink-central-route) | Target-bound framed payload | Central notification or verified local `WriteValue` |

### Packet Format

| Route | Format |
| --- | --- |
| Protocol 108 | `55 payload checksum`; checksum is `55 XOR all payload bytes` |
| Protocol 110 | Characteristic-specific values; STK side-prefixed routes remain separate |
| Pairlink | Type `03`, destination[4], channel, own virtual address[4], four-byte payload blocks; encrypted native frame uses type `06` |

### Write Mode

| Route | GATT write mode |
| --- | --- |
| Protocol 108 / 110 / STK | Write with response |
| Pairlink central | Write without response; the exact target session determines fragmentation |
| Pairlink local | Verified peer `AcquireNotify` socket, separate from central GATT writes |

## Detection / Setup

### Setup and model selection

The integration discovers Protocol 108 from its GATT service and Protocol 110
from the Nightstand service.

The selected profile controls which movement, position, massage, memory,
preset, lumbar, and body-tilt entities are created. A model capability flag for
the Pillow surface has no matching reachable direct BLE command in the accepted
evidence, so this integration does not create a Pillow control.

## Commands

### Protocol 108

#### Packet format and release

Protocol 108 uses service `1b1d9641-b942-4da8-89cc-98e6a58fbd93` and its
command characteristic. Each packet starts with `55`, contains the command
bytes, and ends with the XOR of `55` and each command byte. A physical press
sends one movement command. Releasing a movement sends the accepted STOP frame
`55 FF AA` through the coordinator's serialized cleanup path.

#### Protocol 108 command bytes

Command bytes below are wrapped by the Protocol 108 packet builder.

#### Preset Commands

| Command | Payload | Full Packet |
|---------|---------|-------------|
| Flat | `0x05` | `55 05 50` |
| Zero-G | `0x15` | `55 15 40` |
| Anti-Snore | `0x16` | `55 16 43` |
| Memory 1 | `0x11` | `55 11 44` |
| Memory 2 | `0x12` | `55 12 47` |
| Memory 3 | `0x13` | `55 13 46` |
| Memory 4 | `0x14` | `55 14 41` |
| Save Memory 1 | `0x21` | `55 21 74` |
| Save Memory 2 | `0x22` | `55 22 77` |
| Save Memory 3 | `0x23` | `55 23 76` |
| Save Memory 4 | `0x24` | `55 24 71` |
| Stop | `0xFF` | `55 FF AA` |

#### Linear Motor Commands

| Command | Payload | Full Packet |
|---------|---------|-------------|
| Head Up | `0x01` | `55 01 54` |
| Foot Up | `0x02` | `55 02 57` |
| Head Down | `0x03` | `55 03 56` |
| Foot Down | `0x04` | `55 04 51` |
| Stop | `0xFF` | `55 FF AA` |

#### Position Motor Commands

| Command | Payload | Description |
|---------|---------|-------------|
| Head Position | `0x51 {pos}` | Move head to position (0-100) |
| Feet Position | `0x52 {pos}` | Move feet to position (0-100) |

#### Massage Commands

| Command | Payload | Description |
|---------|---------|-------------|
| Head Massage | `0x53 {level×4}` | Set head massage level (0–10) |
| Foot Massage | `0x54 {level×4}` | Set foot massage level (0–10) |
| Wave Massage | Decimal text `4n` through `BLE108CRC` / `hex2Byte` | Source integer input; no inferred protocol range or cycle |
| Stop Massage | `0x35` | Stop all massage |

#### Other Commands

| Command | Payload |
|---------|---------|
| Lights Toggle | `0x5B 0x00` |

The existing HA wave slider retains its compatibility range, but that UI
limit is not a source-proven Protocol 108 input domain. The packet builder
appends the supplied decimal integer to the text `4`, then applies the source
checksum and complete-hex-pair decoder. For example, the existing slider's
level 10 emits `55 41 04 45`, rather than treating 10 as a single nibble or
adding it to `40`. This preserves the compatibility UI range without claiming
that range is a protocol limit. The builder does not clamp or cycle the value.

### Protocol 110 and STK

#### Protocol 110 (Characteristic-Based)

#### Characteristic commands

UUIDs below share suffix `-f324-29c3-38d1-85c0c2e86885`.
Values come from [`reverie_nightstand.py`](../../custom_components/adjustable_bed/beds/reverie_nightstand.py).
Model capability gates apply to every row.

| Command | Characteristic prefix | Value / bytes |
| --- | --- | --- |
| Head / foot / lumbar position | `db801041` / `db801042` / `db801040` | Integer `00`–`64` (0–100%) |
| Linear head / foot / lumbar | `db801021` / `db801022` / `db801020` | Up `01`, down `02`, release `00` |
| Zero-G / Anti-Snore / Flat | `db8010d0` | `01` / `02` / `03` (ordinary profiles) |
| Recall memory slot `n` (1–4) | `db8010d0` | `n + 3`, so `04`–`07` |
| Save memory slot `n` (1–4) | `db8010d0` | `n + 83`, so `54`–`57` |
| Head / foot massage intensity | `db801061` / `db801060` | `level × 4`, level 0–10 |
| Global massage wave | `db801080` | Raw byte 0–255; compatibility slider retains its own UI range |
| Nightlight on / off | `db8010a0` | `40` / `00`; on uses retained nonzero brightness when available |
| RGB color / brightness | `db8010a7` | `01 brightness red green blue`; brightness 0–100 and RGB channels 0–255, preserving the known values not being changed |
| R650 Zero-G / Anti-Snore / Flat | `db8010d0` | `00 20 47 24 00 00 00 00 00 00` / `00 0C 00 24 00 00 00 00 00 00` / `00 00 00 24 00 00 00 00 00 00` |
| STK side 2/3 head up / down | `db8010a5` | `side 01` / `side 03` |
| STK side 2/3 head release | `db8010a6` | `side FF` |
| STK side 2/3 Zero-G / Anti-Snore / Flat | `db8010a5` | `side 21` / `side 22` / `side 05` |
| STK side 2/3 head strength | `db8010a5` | `side 53 (level × 4)` |
| STK side 2/3 head wave | `db8010a5` | `side 40 (level × 4)` |
| STK side 2/3 memory recall / save | `db8010a5` | `side (n + 16)` / `side (n + 32)` |

STK uses numeric side bytes `01`, `02`, `03`; side 1 uses the ordinary
characteristic route. The `db8010a6` no-data route and R650 body-tilt preset
payloads remain distinct. Their exact builders are `hold_control()`,
`_write_stk_axis()` and `_write_preset_mode()` in the controller; no generic
preset byte is substituted for those model-specific frames.

Protocol 110 uses service `db801000-f324-29c3-38d1-85c0c2e86885` and separate
characteristics for linear movement, position, massage, presets, light, and
RGB. Movement sends one `01` press to the selected axis and `00` to that same
axis on release. Position setters write the selected axis value directly.
Nightlight and RGB writes, preset modes, memory recall/save, massage levels,
position reads, lumbar, and R650 body tilt are exposed only when the selected
model supports them. Existing default/auto Nightstand entries retain their
legacy lumbar control. An explicit app-model selection uses the source
capability table, including the `Other` profile.

### STK side selection

STK exposes a numeric `reverie_stk_side` selector with the app's side values
`1`, `2`, and `3`. This is deliberately separate from Home Assistant paired
bed left/right routing. The integration does not infer a left/right mapping.
The controller follows the accepted data-bearing and no-data characteristic
routes, preserves side-specific feedback, and uses the V1 Composer route for
routines. The STK V2 comfort method is empty in the app and is excluded.
Head massage step buttons follow the same selected numeric side as the head
strength slider.
The back position follows the selected head. Selecting Both reports an unknown
back position until both heads report the same value; the two raw head readings
remain separate for Composer routines.

A failed or canceled press still releases the side that started the hold,
even if the local side selector changes before cleanup.

### Paired local Pairlink setup

Paired local Pairlink entries reserve each selected adapter separately. Combining
existing singles validates their exact config-entry and physical-address ownership
before changing leases, stops the old backend before starting its replacement,
and preserves side device and entity IDs. A failed takeover restores each surviving
single's lease and server, with a fresh unauthenticated runtime and no carried
position feedback. A registered server can finish setup before a peer joins;
commands still require a current authenticated, subscribed physical peer.

### Pairlink central route

#### Discovery and GATT profiles

Pairlink discovery recognizes the accepted manufacturer prefix `C0` under
Home Assistant company identifiers `0xFFFF` or `0x05B9`. Android's raw blocks
start with `FF FF C0` or `B9 05 C0`; Home Assistant separates the first two
bytes into the little-endian company ID. Parsing reconstructs that raw block
before applying its length and field offsets. The accepted profiles include R510L and
Harmoniq Upgrade advertisement variants and the documented app-model fallback. The
host manifest uses the same separated company IDs. Manufacturer data refines
an identified Pairlink model; it does not independently claim a bed protocol
from a generic mesh record.
The central GATT profiles are:

| Profile | Service | Write | Notify |
| --- | --- | --- | --- |
| Primary | `9e5d1e47-5c13-43a0-8635-82adffc0386f` | `9e5d1e47-5c13-43a0-8635-82adffc1386f` | `9e5d1e47-5c13-43a0-8635-82adffc2386f` |
| Low power | `0000ffd0-0000-1000-8000-00805f9b34fb` | `0000ffd1-0000-1000-8000-00805f9b34fb` | `0000ffd2-0000-1000-8000-00805f9b34fb` |

#### Dashboard and setting payloads

Values below come from `dashboard_payload()` / `a7_payload()` and
[`reverie_pairlink.py`](../../custom_components/adjustable_bed/beds/reverie_pairlink.py).
Dashboard payloads are `01 command value 00`; settings are
`01 A7 selector value`. Command numbers are hexadecimal; `value` is one byte.
These four-byte application payloads are inside the authenticated Pairlink
frame, not complete plaintext GATT writes.

| Command | Application payload | Meaning |
|---------|---------------------|---------|
| Back up / down / release | `01 01 FF 00` / `01 02 FF 00` / `01 03 00 00` | Back axis |
| Legs up / down / release | `01 04 FF 00` / `01 05 FF 00` / `01 06 00 00` | Legs axis |
| Lumbar up / down / release | `01 07 FF 00` / `01 08 FF 00` / `01 09 00 00` | R510L only |
| Back / legs / lumbar absolute position | `01 01 value 00` / `01 04 value 00` / `01 07 value 00` | 0–100; lumbar uses `100 − position` |
| Flat / Zero-G / Anti-Snore | `01 1C 00 00` / `01 62 00 00` / `01 65 00 00` | Presets |
| Recall memory 1–4 | `01 29 00 00`–`01 2C 00 00` | No reachable memory-save action |
| Head / foot massage | `01 4D value 00` / `01 4F value 00` | 0 for off; otherwise `5 × level + 15`, levels 1–10 |
| Stop massage | `01 48 00 00` | Massage off |
| Light on / off | `01 5C 00 00` / `01 5D 00 00` | Discrete light commands |
| Brightness / red / green / blue | `01 A7 10 value` / `01 A7 11 value` / `01 A7 12 value` / `01 A7 13 value` | Level 0–100; RGB channels 0–255 |
| Rhythm / mode / timer | `01 A7 14 value` / `01 A7 15 value` / `01 A7 16 value` | Boolean 0/1; mode 0–4; raw timer 0–255 |
| Comfort/alarm prefix | `01 A7 17 01` | Followed by supported fields in source order |
| State request | `01 A7 20 type` | Types and order below |
| Active status sync | `01 A8 00 00` / `01 A9 00 00` | Separate requests |
| Backup exit | `01 15 55` | Private session exit command |

### Packet format and timing

The central codec builds the accepted type-3 frame, encrypts it, applies the
target's four-byte native device key, and fragments central writes using the
ATT-derived fragment size and 15 ms delay after every fragment. The ordinary
dashboard route requests channel 32 and sends wire channel 32; the separate
appearance flag increments the channel only when explicitly set. The sign gate
controls broadcast sends and tracks per-MAC status. GATT write completion is
not bed acknowledgement.

The app's ready-status callback requests the source broadcast ping over the
existing selected BLE session and clears its per-entry discovered-device list.
Ping replies repopulate that list. RTT starts from this request's send time;
local notification completion also refreshes it for the source channel `FE`
guard. Both use the same clock as the receive-side RTT calculation.

### Model controls and value bounds

Pairlink's raw integer position, light-level, and RGB setters retain integer
validation and clamp their channel values to the wire range. The Home Assistant
position sliders and position conversion keep their declared 0–100 bounds.
Lumbar movement and its held-control metadata are exposed for the R510L profile;
Harmoniq Upgrade exposes only back and legs, reports no lumbar support, and
rejects comfort requests that specify a lumbar position. Forced comfort calls
require every field supported by the selected profile, while all-target
validation still completes before any target writes.

### HomeID, credentials and session identity

The selected-device central route is the default. It uses an explicit
configured HomeID first, then the accepted HomeID from the bed's current
manufacturer data, then the source-known app default `5566` when neither
caller input nor advertisement supplies one. The default is decimal 5566 and
normalizes to little-endian bytes `BE 15 00 00`; its provenance remains distinct
from an explicit value or advertisement. It also uses Home Assistant's declared
password policy: the known default text `1122` and
explicit text are UTF-8 encoded and must produce exactly four bytes. An
optional eight-digit hex value replaces those bytes only while the text remains
at the default. This is an integration policy, not a claim about Android's
unspecified charset. The target BLE MAC is kept with its session key, learned
from an accepted login on that exact central connection. Own virtual address
starts at the accepted zero value and changes only after the source `010A`
message. Native login, join, connection, and sign-gate state are separate
requirements; a stale or incomplete session cannot send an action.

### Notifications and status queries

Raw central notifications enter the accepted native decoder before app event
dispatch. This handles login replies, mesh decryption, event-key seed
replacement, own-address changes, fragmented packets, registered channel-32
state, and eligible SDK status consumers. The accepted state request order is
`01 A7 20` with types `01,02,03,05,06,11,07,08,09,0A,0B,0C,0D,0E`; active
status sync uses separate `01 A8 00 00` and `01 A9 00 00` requests. Generated
queries use existing coordinator serialization. Central status polling and clock
queries preserve the current idle-disconnect deadline and never reconnect an idle-disconnected
receiver. Central frames use the
accepted target/MAC session key and actual ATT MTU. A GATT write completion is
transport acceptance, not confirmation that the bed moved.

Initial dashboard reads accept position, massage, and light feedback between
queries while retaining the captured physical session and authentication guards.

### Local peripheral role

The separate local peripheral role is an explicit setup choice that makes this
Home Assistant host join the Pairlink network. It uses the integration-owned
Linux BlueZ D-Bus backend at `beds/reverie_pairlink_transport.py`. It is outside
Home Assistant's public server-transport API and never substitutes a central
write for a local write. Setup selects one active local HA scanner source and
binds only to its uniquely verified `/org/bluez/hciN` adapter. The integration
does not power or reset the adapter, alter OS permissions, or stop Home
Assistant scanners.

The accepted BlueZ profile uses FFD0, FFD1 (`read`, `write`) and FFD2 (`read`,
`notify`). Reads return the immutable source values `44` and `66` respectively.
The local advertisement is connectable peripheral mode with company ID `0000`
and payload `C0 FF 05`, the accepted HomeID in little-endian order, and six
generated octets. The generated join address is distinct from the selected
BlueZ adapter address. It has no local name, service UUID, service data, scan
response, or includes. The source's Android advertise-mode integer is retained
as evidence but is not treated as a BlueZ interval. HA requests a 100 ms host
interval and requests +1 dBm only when BlueZ reports `CanSetTxPower`. These are
declared host preferences, not measurements from the source phone. The source
TxPowerLevel enum is not serialized as dBm, and `tx-power` is not requested as
an advertisement include.

### BlueZ descriptor and notification mapping

BlueZ owns each peer's standard CCCD and exposes subscription through
`AcquireNotify`. The Android descriptor callback is not recreated: its
`01 00` read and echo behavior have no equivalent server callback in the public
BlueZ API. Android's separate GATT permission metadata also has no matching
field in `GattCharacteristic1.Flags`; the effective BlueZ flags remain the
source-required FFD2 `read|notify`. This platform difference is documented and
does not block the accepted service from starting.

The backend uses
`GattCharacteristic1.AcquireNotify` for per-peer notification delivery. It
verifies the current BlueZ producer and `device` option, then binds the acquired
file descriptor to that peer's verified Device1 path, adapter, address, and
connection generation. Outbound values use that peer's socket. Identity-free
`StartNotify`, `StopNotify`, and `async_notify(bytes)` calls fail closed. It
does not change a shared `Value` property or emit a characteristic-wide value
update, which would notify every subscribed peer. FFD2's `Value` property and
`ReadValue` method always return the immutable profile byte `66`, including
after either peer receives a notification; peer response bytes are never used
as the characteristic read value. FFD1 reads stay at the immutable profile
byte `44`.

The local FFD1 `WriteValue` handler returns BlueZ's ordinary successful GATT
write response after the private session processor accepts the request. That
empty ATT response is not a custom echoed mesh packet. Source-generated Pairlink
replies are separate peer-targeted notifications and are sent only when the
current session requires one. BlueZ also owns CCCD reads and state: Android's
source callback reads `01 00` and echoes descriptor writes, while a standard
BlueZ client may observe its daemon-managed CCCD state instead. The integration
does not add a duplicate `2902` descriptor or claim byte-for-byte Android
descriptor behavior.

Android's backup-peer branch processes an eligible write without calling its
common `sendResponse`. BlueZ's public `WriteValue` contract instead maps method
completion to ATT success and D-Bus errors to ATT errors, with no per-write
silent-response disposition. The integration retains BlueZ completion rather
than leave a D-Bus request hanging. This platform qualification affects ATT
acknowledgement only; source reply payloads, peer gates and processing remain
separate. See the [BlueZ GATT API](https://bluez.readthedocs.io/en/latest/gatt-api/).

### Malformed input

Malformed six-byte built-in-channel frames are safely dropped at the receive
boundary. The source channel-12 callback instead reads a missing subtype byte
after its outer six-byte guard. The host retains this bounded safe-drop behavior
without changing well-formed dispatch, state, or packets.

### Startup requirements

Startup requires the actual selected adapter, GATT and advertising managers,
permission to register, an available advertised-instance slot, and every
capability the chosen profile truly requires. Missing optional TX-power
support leaves BlueZ's host power unchanged. A permission or registration
failure is reported as a setup failure; no radio setting or global policy is
changed to work around it.

### Peer identity and lifecycle

Each WriteValue callback requires BlueZ's `device` object-path option. The
backend checks the current Device1 address, adapter, connection state, and
BlueZ message producer before it passes an immutable peer identity and the
unchanged byte payload separately to the private Pairlink session processor.
The identity carries the selected adapter path, current device path and address,
and a connection generation, so auth/session state cannot be reused for a
different peer or a rejoined connection. Invalid or stale identity and missing
session readiness fail closed. No MAC/key association or payload is logged.

The local processor keeps each verified peer's physical connection,
notification subscription, login key, source device type, and session state
separate. A peer's `WriteValue` identity includes the selected adapter, current
BlueZ Device1 object path and verified address, and connection generation. The
processor rejects absent, malformed, stale, or mismatched identity; it does
not infer a MAC from payload bytes or a path alone. Notification-FD hangup
removes only that subscription. Device1 disconnect or BlueZ owner loss ends the
physical generation and clears its source-owned state. Unload awaits backend
cleanup even when there is no central Bleak client, and a rejoin gets a fresh
generation. Known-peer connection observations emit their source status
without repeating admission or provisioning. Identity lookups for ordinary
writes stay deduplicated. Queued writes retain that generation and cannot recreate an ended
peer. Exit is latched before status persistence awaits, so new connections and
payloads cannot enter the runtime during teardown.

Both roles are owned by one config-entry runtime. Local peer credentials and
state are not shared across separate beds or paired sides. A narrow in-memory
lease prevents two entries from registering the same FFD0 server on one BlueZ
adapter; it is released with the entry lifecycle. Actions require the selected
role's current session, authentication, signing permission, and exact target
before writing. The local role sends only through the currently verified peer
notification FD; a type-0 source route stays clear and does not require a key.
No peer identity, MAC/key association, credentials, or payload is logged.

### Backup cleanup timing

After an accepted local welcome, the default-true backup-cleanup flag starts a
one-second check. While that flag remains enabled and subscribed backup peers
remain, HA sends the source exit command and rearms the check after 800 ms.
Primary physical disconnect separately attempts the exit command for current
backup peers, cancels the periodic check, and clears native session keys,
virtual-address state, and provisioning transcripts. Remaining peers retain
their physical connection and subscription state; notification unsubscribe
alone does not run physical-disconnect cleanup.

## Home Assistant actions and automation

`reverie_set_comfort` accepts typed position, massage, mode, and raw timer-byte
fields. Pairlink exposes that value as a timer code and does not claim a
minute conversion. Every selected physical target validates the request before any target
writes. Protocol 110 Composer requests require its five accepted values.
Protocol 108 applies changed values after notification feedback. Pairlink
ordinary requests send only changed values. Its alarm route starts alarm mode
and writes every field supported by the selected profile, even when values
match current state. Lumbar is required for R510L and must be omitted for
Harmoniq Upgrade.
An admitted Pairlink comfort burst accepts ordinary telemetry between writes,
but a changed peer, physical session, authentication, or STOP aborts the remaining
writes. Removing a backup peer clears only that peer's cached telemetry and
preserves the primary peer's exposed state.

`reverie_run_routine` replaces the selected physical target's protocol queue.
Routine capability is independent of standalone comfort capability: `3EMT`
and `O300T` accept routine steps while `reverie_set_comfort` remains unavailable.
It does not add a general-purpose scheduler. Use Home Assistant automations to
schedule `reverie_set_comfort`, `reverie_run_routine`, `goto_preset`, or
`save_preset` at the desired time. Phone-local alarm storage, Android
notifications, and its scheduler are outside this integration's scope.

`reverie_test` sends the accepted Protocol 108 or 110 direct diagnostic and
its matching stop writes. Pairlink diagnostics use the current central or local
session and the same authentication, sign, target, and readiness checks as
ordinary actions. The diagnostic retains the command connection until its timed
cleanup completes, including with Disconnect After Command enabled. Pairlink's
massage mode and rhythm selects display receiver feedback; the mode sensor
retains its numeric value for automations. Pairlink RGB light color follows
receiver feedback once all three channels are known for the current peer.
A successful GATT write only shows transport acceptance, not physical bed behavior.

See [Actions and Automations](../SERVICES.md) for action schemas and examples.

## Position Feedback / Notifications

### Position Notifications (9 bytes)

| Protocol 108 notification byte | Content |
| --- | --- |
| 0–1 | Header |
| 2 / 3 | Head / foot position (0–100%) |
| 4 / 5 | Head / foot raw massage feedback |
| 6–8 | Unknown; no additional state inferred |

### Protocol 108 feedback and Composer timing

The nine-byte position notification reports head and foot position plus
massage values. Duplicate notifications do not repeat state updates. The
comfort action waits for stable repeated notification values before sending
only still-pending changed axes, in head, foot, head massage, foot massage
order. Elapsed time must be strictly greater than zero initially and 2000 ms
after the first eligible callback. A changed sample resets that time origin.
Equal unsent fields are skipped within the same callback to reach the first
unequal field; they remain eligible if later feedback changes. Massage equality
uses the raw notification byte, independently of the visible level conversion.
Errors stop the progression and remain
visible to the command caller. Feedback is checked again after waiting for the
coordinator command lane; changed feedback leaves the field pending until a
fresh eligible repeated notification. If that eligible notification arrives
while an older sample is still queued, the current sample is retained and
consumed inside the existing command lane; it is not replaced with a timed
write during silence.

The BLE connection remains held until all pending comfort fields are consumed,
cancelled, or fail, including with Disconnect After Command enabled. Cancelling
a routine also discards its pending comfort progression.

### Command timing and routines

Each physical address owns a separate Composer routine queue and timer. The
first complete routine item runs immediately. A missing setting aborts queue
construction and leaves any already-built prefix unscheduled. A replacement
cancels that address's pending timer and queue without sending a bed STOP. Each
valid step schedules its exact minute duration before sending comfort, and the
final step still schedules the empty-queue poll. Durations are not clamped to a
minimum.

## Command Timing

| Route | Timing / cleanup |
| --- | --- |
| Protocol 108 / 110 movement | One press; protocol-specific serialized release |
| Protocol 108 comfort | Stable repeated feedback; strictly positive initial elapsed time, then greater than 2000 ms |
| Protocol 108 / 110 routines | Schedule the exact minute duration before each write, including the final empty-queue poll |
| Pairlink central fragments | ATT-derived fragment size, 15 ms after every fragment |
| Pairlink clock query | First query after five seconds; next query five seconds after a time response; preserves the idle deadline |
| Pairlink backup cleanup | First check after one second, then 800 ms while applicable |
| Diagnostic | Protocol 108/110 ten seconds; Pairlink two seconds; connection held through cleanup |

## Notes

### Pairlink source scope and implementation status

The implementation covers central and explicit local runtime consumers.
Hardware delivery remains unverified and is deferred to real-user validation
after beta/release. Audit evidence, overlay identities, exact exclusions and
acceptance history are in the
[disposition crosswalk](../apk-analysis/dispositions/row041-reverie.md#guide-evidence-and-scope-notes).
The [SDK implementation notes](reverie-pairlink-sdk.md) describe private receive
and metadata consumers. They do not create an arbitrary-packet action.

### Analysis provenance

- Package `com.reverie.reverie`, version 3.3.3.8; row041 and comparison seal amendment 007.
- [Accepted evidence and disposition crosswalk](../apk-analysis/dispositions/row041-reverie.md).
