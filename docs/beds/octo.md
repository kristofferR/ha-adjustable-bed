# OCTO Smart Control

**Status:** ⚠️ Partially tested (Standard 2-4 motor receivers work in [#73](https://github.com/kristofferR/ha-adjustable-bed/issues/73), [#440](https://github.com/kristofferR/ha-adjustable-bed/issues/440) and [#499](https://github.com/kristofferR/ha-adjustable-bed/issues/499), and a Star2 DA1458X in [#510](https://github.com/kristofferR/ha-adjustable-bed/issues/510); an RTV TV lift was reported working in [#440](https://github.com/kristofferR/ha-adjustable-bed/issues/440); OCTO Smart Control 1.03.02 behavior is APK-verified, hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), [_pm](https://community.home-assistant.io/t/how-to-setup-esphome-to-control-my-bluetooth-controlled-octocontrol-bed/540790), [goedh452](https://community.home-assistant.io/t/how-to-setup-esphome-to-control-my-bluetooth-controlled-octocontrol-bed/540790/10), Murp, and [Brokkert](https://github.com/Brokkert)

**Integration profile:** Standard OCTO Smart Control uses the existing OCTO bed type. Star2 remains a separate protocol variant.

## Known Models

- Octo-branded adjustable beds
- Beka
- Cozyworld Cozy2Go
- One-motor products of the same protocol family: the official `RTV` **Lift 1M**
  is supported as a separate TV Lift device
- Octo Remote Star2 receivers (separate [Star2 variant](#star2-variant-octo-remote-star2))

### Bed brands that ship OCTO actuators

OCTO Smart Control re-brands itself per OEM: the receiver reports a customer ID
in `SYSTEM_DEVICEINFO`, and the app looks that up in a bundled `brandinginfo.json`
to pick a logo and colour scheme. That table is effectively OCTO's OEM customer
list, so a bed sold under any of these brands is very likely an OCTO base and
should work with this integration:

| Customer ID | Brand |
|-------------|-------|
| `00000001` | EcoBed |
| `00000003` | sleepling |
| `00000004` | sleepwell |
| `0000000A` | bett1.de |
| `0000000B` | Hüsler Nest |
| `0000000C` | SWISSpur Schlafkomfort |
| `0000000D` | BW (member of the JAB Anstoetz Group) |
| `0000000E` | Dunlopillo |
| `0000000F` | selecta by RöWa |
| `00000010` | spirit by Hilding Anders |
| `00000011` | Dorsal |
| `00000012` | Werkmeister |
| `00000013` | Inarredo |
| `00000014` | Velda |
| `00000100`, `00000101` | Swiss Sense |
| `0000C054` | cosyworld |

- `00000000` is OCTO Actuators itself, `00000002` is a placeholder ("pink
  dummy"), and `FFFFFFFD`/`FFFFFFFE` are demo entries.
- `FFFFFFFF` marks a receiver whose customer ID is not app-enabled (the app then
  shows "This hardware does not provide app support. Please contact your
  dealer"). That is a licensing check and is unrelated to the PIN lock.
- Brand names are taken from `brandinginfo.json` in OCTO Smart Control 1.03.01
  and cross-checked against the bundled logo artwork, which is why two differ
  from the raw JSON labels: `00000003` is styled *sleepling*, and `0000000F` is
  RöWa's *selecta* line.
- This list is what the app knows and is not exhaustive: an OEM absent here can
  still use OCTO hardware.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [OCTO Smart Control](https://play.google.com/store/apps/details?id=de.octoactuators.octosmartcontrolapp) 1.03.02 (10302) | `de.octoactuators.octosmartcontrolapp` |

Earlier builds 1.03.01 (10301), 1.03.00 and the older `1.1.57` (10157) were also
checked; see [Analysis provenance](#analysis-provenance).

## Features

| Feature | Supported |
|---------|-----------|
| Bed Motor Control | ✅ (1-4 motors from `CAP_MOTORCOUNT`; explicit 1-4 override) |
| One-motor TV/Bed Lift | ✅ (Standard variant; dedicated TV Lift entity, hardware validation pending) |
| Position Feedback | ❌ |
| [Estimated Positions](../ESTIMATED_POSITIONS.md) | ✅ (opt-in, Standard variant; back, legs, head and feet, hardware validation pending) |
| Memory Presets | ✅ (dynamically detected, Standard variant only) |
| Combined Back + Legs Control | ✅ (two-motor Standard and Star2 variants; hold-capable in the bundled card) |
| Under-bed Lights | ✅ (Standard variant only; on/off switch, RGB / RGBW light entity on `CAP_LIGHT_RGB` / `CAP_LIGHT_RGBWI`) |
| Light duration, automatic light, light sensitivity | ✅ (Standard variant, when advertised) |
| Synchro/Linked Mode | ✅ (Standard variant, split-king beds with `CAP_SYNCHRO`) |
| Remote-control lock / Remote teach | ✅ (Standard variant, when advertised) |
| PIN Authentication | ✅ (Standard variant only; PIN enrollment action) |
| Receiver reset | ✅ (confirmed, destructive action) |
| Massage, battery, alarm, motor status | ❌ (not exposed by this app protocol) |
| Hold until release | ✅ Standard ([renewable](../SERVICES.md#renewable-holds) `timed_move` and `hold_control`: 350 ms refresh, then STOP); ❌ Star2 |

## Protocol Details

Octo beds have at least two protocol variants: Standard (most common) and Star2.

### Standard Variant (Most Common)

**Service UUID:** `0000ffe0-0000-1000-8000-00805f9b34fb` (`FFE0`)
**Write Characteristic:** `0000ffe1-0000-1000-8000-00805f9b34fb` (`FFE1`)
**Notify Characteristic:** `0000ffe1-0000-1000-8000-00805f9b34fb` (`FFE1`)
**Format:** Packet-based with start/end markers and checksum

#### Packet Structure

```text
[0x40, cmd[0], cmd[1], len_hi, len_lo, checksum, ...data, 0x40]
```

**Checksum:** `((sum_of_all_bytes XOR 0xFF) + 1) & 0xFF`

- P1 frames use `40` delimiters, an unsigned big-endian length, a
  two's-complement checksum and byte escaping.
- The checksum is calculated on the unescaped packet, delimiters included.
  Response packets use `0x80` as the first byte for checksum calculation.
- Bytes `0x40`, `0x3C`, `0x4F`, and `0x41` inside the frame payload are escaped
  as `0x3C` followed by `0x01`, `0x02`, `0x03` or `0x04` respectively. The
  delimiters themselves remain unescaped.
- Valid flagged source and destination addresses are six bytes and are removed
  before dispatch.
- The parser requires the declared frame length and checksum to match exactly.
  Malformed flagged addresses and undeclared trailing data are rejected.

#### Notification framing

An OCTO packet and a BLE notification are not the same boundary. A complete
packet can span multiple notified characteristic values, and one notified value
can contain multiple packets. The integration keeps an incomplete response
between callbacks, extracts every complete `0x40 ... 0x40` frame, then verifies
its unescaped length and checksum before dispatching it. Malformed data is
discarded up to the next possible frame delimiter.

#### Session handshake

When a receiver answers, the controller follows the app's order:

1. P1 ping
2. Ten-byte device information
3. Capability request

A complete advertised list ends with `FFFFFF` and is the only source of
authoritative capability records. Malformed replies remain strict failures.

- **Omitted ping or device-info reply** (established receivers): the integration
  continues to the next ordered request.
- **Absent or incomplete capability list:** it keeps any previous complete
  snapshot and uses the integration's field-compatible legacy defaults,
  including the historical assume-lights path. These defaults are not reported
  as complete discovery and cannot retire known entities or be persisted as a
  capability snapshot.
- This absence fallback preserves the behavior used by field-reported receivers;
  it does not change the accepted app behavior when valid replies arrive.
- Star2 does not use this P1 handshake.

#### Capability records

Capabilities are retained as typed records containing the feature ID, read-only
flag, characteristic bytes, value type and value bytes. Writes replace only the
value bytes and preserve the advertised metadata. Device information and
capabilities are stored per physical receiver when a pair is configured.

The integration queries capabilities via `[0x20, 0x71]`. Known feature IDs:

| Feature ID | Name | Value |
|------------|------|-------|
| `0x000001` | CAP_MOTORCOUNT | Motor count reported by the device (1-4; Standard OCTO supports 1-4) |
| `0x000002` | CAP_MEMCOUNT | Memory preset count |
| `0x000003` | CAP_BLE_PIN | PIN state + lock state (see [PIN protocol](#pin-protocol)) |
| `0x000004` | CAP_MEMINFO | Memory slot classes and per-slot names |
| `0x000010` | Remote teach | Remote-teach action |
| `0x000011` | Remote-control lock | Lock state, 1 byte |
| `0x000101` | CAP_SYNCHRO | Synchro/linked mode support |
| `0x000102` | CAP_LIGHT | Under-bed light support (on/off) |
| `0x000103` | Light duration | Minutes, 2 bytes big-endian |
| `0x000104` | CAP_LIGHT_RGBWI | RGB + White + Intensity light control |
| `0x000105` | Automatic light | Motion-triggered lighting, 1 byte |
| `0x000106` | Light sensitivity | 2 bytes big-endian |
| `0x000107` | CAP_LIGHT_RGB | RGB light control, 3 bytes |
| `0xFFFFFF` | End sentinel | Marks end of feature list |

A capability write (`[0x20, 0x72]`, `SYSTEM_SET_CAPS`) carries
`[feature_id (3 bytes), readonly, char_len, ...characteristic, value_type, ...value]`,
copying the advertised record and replacing only the value.

### Star2 Variant (Octo Remote Star2)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), [goedh452](https://community.home-assistant.io/t/how-to-setup-esphome-to-control-my-bluetooth-controlled-octocontrol-bed/540790/10)

**Service UUID:** `0000aa5c-0000-1000-8000-00805f9b34fb`
**Write Characteristic:** `00005a55-0000-1000-8000-00805f9b34fb`
**Write Type:** Write request (with response)
**Format:** Fixed 15-byte commands starting with `0x68`, ending with `0x16`

Star2 uses a distinct GATT endpoint and its own fixed command protocol. It does
not declare the Standard P1 session requirement, PIN workflow, dynamic lights or
memory features. The Standard-only session gate does not apply to Star2.

**Note:** Star2 variant does not support lights or PIN authentication.

## Detection

- **Standard variant:** Detected by an official OCTO device-name prefix. The
  shared `FFE0` service UUID alone is not sufficient because other protocol
  families also use it.
- **Star2 variant:** Auto-detected after connection when the
  `0000aa5c-0000-1000-8000-00805f9b34fb` service contains the
  `00005a55-0000-1000-8000-00805f9b34fb` write characteristic. Explicit
  variant selections override this GATT-based detection.

You can also manually select the variant in the integration options.

Recognized Octo device-name prefixes are:

| Prefix | OCTO description |
|--------|------------------|
| `RTV` | Lift 1M (defaults to the dedicated one-motor TV Lift layout) |
| `RC2` | Receiver II |
| `MC2` | Micro 2 |
| `OCTOBrick` | Brick 1 (`OCTOBrick2` is covered by the same prefix) |
| `MC1` | Micro 1 |
| `L2M` | Lift 2M |
| `CLI` | Cosy Lift |
| `OCTOIQ` | IQ Redesign |
| `RC3` | Receiver II 3M |
| `BMB` | BrickMini Basic |
| `BMS` | BrickMini Memo |
| `BM3` | BrickMini Basic 3M |
| `DA1458x` | Legacy receiver/SoC name |

These names identify the Octo protocol family. The connected GATT table selects
the Standard or Star2 implementation when the variant is left on Auto. Features
are still limited by the device capabilities and the support table above, and
every OEM combination is not necessarily hardware-tested.

The accepted 1.03.02 artifact defines no separate protocol profile selected by
OEM branding, CID, PID, hardware, firmware, locale or device name. Standard P1
remains the existing OCTO bed type; Star2 remains separate.

## Commands

### Motor Control

Motors are controlled via bit masks (`CAP_MOTORCOUNT` determines how many are available):

| Motor | Bits |
|-------|------|
| Motor 1 (Head/Back) | `0x02` |
| Motor 2 (Legs) | `0x04` |
| Motor 3 (beds with `CAP_MOTORCOUNT` > 2) | `0x08` |
| Motor 4 (beds with `CAP_MOTORCOUNT` > 3) | `0x10` |
| Both motors 1+2 | `0x06` |
| Motors 3+4 | `0x18` |

| Command | Command Bytes | Data | Description |
|---------|---------------|------|-------------|
| Move Up | `[0x02, 0x70]` | `[motor_bits]` | Move motor(s) up |
| Move Down | `[0x02, 0x71]` | `[motor_bits]` | Move motor(s) down |
| Stop | `[0x02, 0x73]` | none | Stop all motors (`NORMAL_MOTORS_STOP`) |

The official app builds its control layout from `CAP_MOTORCOUNT` alone, and the
combined steps it offers are:

| Motors | Steps offered |
|--------|---------------|
| 1 | M1 `0x02` |
| 2 | M1 `0x02`, M2 `0x04`, M1+2 `0x06` |
| 3 | M3 `0x08`, M1, M2, M1+2, then M1+2+3 `0x0E` **down only** |
| 4 | M1, M2, M3, M4 `0x10`, M1+2, M3+4 `0x18`, then M1+2+3+4 `0x1E` **down only** |

- **Flat:** the all-motors step is down-only in the app, which is what "Flat"
  means for this protocol. The integration's Flat control sends `0x06`, `0x0E`
  or `0x1E` according to the configured motor count, so 3M and 4M receivers
  (`RC3`, `BM3` and 4-motor bases) actually reach flat instead of leaving the
  extra actuators parked.
- A motor count the app does not recognize renders no controls at all.
- **Back + Legs:** on a two-motor receiver, M1+2 is exposed as a **Back + Legs**
  motor control. Its Up and Down actions replace the former tap-only Back + Legs
  Up and Flat preset tiles, so the bundled card can repeat the command while the
  control is held. Three- and four-motor receivers retain separate preset
  controls because their all-motors-down command covers more actuators than Both
  Up.

### Memory

| Action | Packet | Data | Notes |
|--------|--------|------|-------|
| Recall slot | `NORMAL` `[0x02, 0x72]` | `[slot]` | **Hold-to-run**, repeated every 350 ms and released with `[0x02, 0x73]` |
| Save slot | `CONFIG` `[0x10, 0x70]` | `[slot]` | One-shot (`SAVE_MOTORPOS`) |

Recall and save differ by packet **type**, not just command byte. `slot` is
0-based on the wire while the UI counts from 1. See
[Memory positions](#memory-positions) for slot classes and timing.

### Lights

| Command | Command Bytes | Data | Description |
|---------|---------------|------|-------------|
| Lights On (legacy assumed-light path) | `[0x20, 0x72]` | `[0x00, 0x01, 0x02, 0x00, 0x01, 0x01, 0x01, 0x01]` | Turn on under-bed lights |
| Lights Off (legacy assumed-light path) | `[0x20, 0x72]` | `[0x00, 0x01, 0x02, 0x00, 0x01, 0x01, 0x01, 0x00]` | Turn off under-bed lights |
| Light on/off (advertised) | `[0x20, 0x72]` | `CAP_LIGHT` record, value `0x01` / `0x00` | Preserves the advertised record metadata |
| Set RGB | `[0x20, 0x72]` | `CAP_LIGHT_RGB` record, value `[R, G, B]` | Three-byte color, each 0-255 |
| Set RGBWI | `[0x20, 0x72]` | `CAP_LIGHT_RGBWI` record, value `[R, G, B, W, I]` | Each channel 0-255; omitted intensity keeps the bed's current byte |

> [!NOTE]
> Earlier versions of this document listed the light frames with `0x01` in the
> fourth data byte and RGBWI as `[0x20, 0x73]` with intensity fixed at `0xFF`.
> The controller sends read-only byte `0x00` for the legacy light frames and
> writes RGBWI through `SYSTEM_SET_CAPS` `[0x20, 0x72]` with independent
> intensity.

When `CAP_LIGHT` exists and reports off, the controller turns the light on
before a color write, matching the app's ordering.

### Settings

All settings are written through `SYSTEM_SET_CAPS` `[0x20, 0x72]` on the
advertised record:

| Setting | Feature ID | Value |
|---------|------------|-------|
| Synchro / linked mode | `0x000101` | `0x00` single (independent), `0x01` sync (linked) |
| Remote-control lock | `0x000011` | `0x00` / `0x01` |
| Automatic light | `0x000105` | `0x00` / `0x01` |
| Light duration | `0x000103` | Minutes 0-60, 2 bytes big-endian |
| Light sensitivity | `0x000106` | 6, 35 or 85, 2 bytes big-endian |
| Remote teach | `0x000010` | Fixed app payload `[0x00, 0x00, 0x10, 0x01, 0x01, 0x01, 0x01, 0x01]` |

> [!NOTE]
> Earlier releases toggled synchro with `CONFIG` `[0x10, 0x71]` (data `[0x00]`
> single / `[0x01]` sync) and queried it with `[0x10, 0x72]`. The current
> controller writes the advertised `CAP_SYNCHRO` record instead.

### System and session

| Command | Command Bytes | Data | Description |
|---------|---------------|------|-------------|
| Ping | `[0x20, 0x7F]` | none | First step of the session handshake |
| Get device info | `[0x20, 0x70]` | none | `SYSTEM_DEVICEINFO` |
| Get capabilities | `[0x20, 0x71]` | none | Feature discovery |
| Set capability | `[0x20, 0x72]` | record | `SYSTEM_SET_CAPS` |
| PIN authentication | `[0x20, 0x43]` | `[d1, d2, d3, d4]` | Raw digits 0-9 |
| PIN enrollment | `[0x20, 0x41]` | `[d1, d2, d3, d4]` | Set a PIN on a receiver without one |
| Reset defaults | `[0x20, 0xAE]` | none | Destructive receiver reset |

### Star2 Motor Commands

| Action | Bytes (hex) |
|--------|-------------|
| Head Up | `68 30 31 30 30 30 30 30 30 31 30 36 31 38 16` |
| Head Down | `68 30 31 30 30 30 30 30 30 31 30 39 31 3B 16` |
| Feet Up | `68 30 31 30 30 30 30 30 30 31 30 34 31 36 16` |
| Feet Down | `68 30 31 30 30 30 30 30 30 31 30 37 31 39 16` |
| Both Up | `68 30 31 30 30 30 30 30 30 31 32 37 31 3B 16` |
| Both Down | `68 30 31 30 30 30 30 30 30 31 32 38 31 3C 16` |

- Star2 has no STOP frame: its motors stop when the held-command refresh ends.
- The Star2 Both Up and Both Down frames are exposed as the Up and Down actions
  of the **Back + Legs** motor control. In the bundled card this makes the
  combined movement hold-capable, like the individual Back and Legs controls.

## Motor layout and motion

The active `CAP_MOTORCOUNT` record advertises one through four motors.

- Auto layout follows the advertised count; the OCTO-only motor-count option can
  set an explicit one-to-four override.
- If no motor count is discovered, the existing RTV-name setup fallback selects
  one motor; a valid advertised count or explicit override takes precedence.
- A one-motor Standard receiver is shown as a TV Lift. This is a layout default
  only and does not select a different protocol.

After a session accepts an absent capability-list fallback, Standard OCTO keeps
motor covers for that known effective layout, including configured and RTV
defaults. The fallback remains non-authoritative: it creates no capability
records or persisted snapshot. Stable cover IDs remain available to the paired
child while its link is released; movement still requires a ready session, and a
later complete list reconciles the registry to its advertised layout. Malformed
replies do not activate this fallback.

Motor commands use the advertised layout, and movement cleanup sends the
receiver's global STOP with a fresh cancellation event.

Position feedback, angle sensing, massage, battery, alarm and motor-status
reporting are not exposed by this app protocol. The integration does not create
those states from command timing.

### One-motor TV lift

- The official OCTO device list identifies `RTV` as **Lift 1M**, and the
  official app controls it through Standard OCTO motor 1 (`0x02`).
- An automatically discovered `RTV` defaults to one motor and exposes one **TV
  Lift** cover with Raise, Lower, and Stop controls. You can also select one
  motor manually for a Standard OCTO controller.
- The lift is deliberately not presented as an adjustable bed. Bed-only controls
  such as Flat, Back + Legs Up, memory positions, lights, and synchro mode are
  suppressed even if a malformed or unexpected capability response advertises
  them. Position feedback is not available.
- The packet implementation is derived from the official OCTO app; physical RTV
  hardware testing is still required.

## Memory positions

`CAP_MEMCOUNT` supplies the advertised slot count. Each memory action is created
only when the current complete capability set advertises that slot.

### Slot classes (`CAP_MEMINFO`, `0x000004`)

Beds that report `CAP_MEMINFO` describe their memory slots in more detail than
the bare count in `CAP_MEMCOUNT`:

- `characteristic[]` is exactly three bytes, `[memCount, fixCount, lockCount]`:
  the display count, then the fixed and locked slots. A record with any other
  length is ignored entirely.
- `value[]` holds one description ID per slot. It is used only when there is
  exactly one entry per slot.

The three classes partition the slot range contiguously, standard first:

```text
lockStart = memCount - lockCount
fixStart  = lockStart - fixCount

slot index <  fixStart   -> standard   (recall + save)
fixStart <= index < lockStart -> fix   (recall + save, fixed name)
index >= lockStart       -> lock       (recall only)
```

- Locked slots cannot be overwritten; the integration hides their Save button.
- Fixed slots remain savable but are not presented as editable.
- If the value block is the wrong length the descriptions are dropped but the
  class protection is kept, so a malformed response cannot silently turn a
  locked slot into a writable one.
- Known description IDs are `0x01` Anti-Snore, `0x02` Zero-G, `0x03` Lordose
  and `0x04` Flat (`0x00` means unnamed). A named slot is used as the entity
  name, so you get a "Zero-G" button rather than "Memory 3". Unrecognized IDs
  fall back to the generic name.
- Home Assistant numbers slots from one, and the wire protocol numbers them from
  zero.

### Recall and save

- Memory recall uses the same bounded held-control path as motor movement.
  Recall being hold-to-run matters: sending it once moves the bed a fraction of
  the way and then stalls.
- Saving a slot sends the direct save command once.

**There is no arrival signal.** In the official app, recall is a press-and-hold
control that streams for exactly as long as the user holds the button. The
protocol has no completion or position notification (the inbound `NORMAL`
branch is empty and no position capability exists) and no timeout, so a
headless client cannot know when the bed has reached the stored position.

A standalone memory button or service call therefore streams the recall for a
fixed 30 second window and then releases the motors. That bound is **ours, not
OCTO's**: it is chosen to outlast a full-travel move rather than to match the ~1
second a button press implies. The bed stops itself at its end stops, the STOP
frame is always sent afterwards, and pressing Stop cancels the recall
immediately. The bundled card instead holds the recall while the control is
held (see [Command Timing](#command-timing)).

## PIN control

The PIN capability separates whether PIN control is enabled, whether a PIN is
configured and whether the receiver is unlocked.

- Normal motor, memory and settings controls are unavailable while a configured
  PIN is locked or its live state is unknown. Stop and PIN recovery remain
  available.
- PIN digits are never included in command traces or support diagnostics.
- Some Octo beds require a 4-digit PIN to maintain the Bluetooth connection.
  Without the PIN, the bed will disconnect after ~30 seconds.
- PIN entry and enrollment require exactly four ASCII digits.

### PIN verification during setup

Standard Octo setup checks the bed's PIN requirements before saving the entry.
If a PIN is set, Home Assistant sends the entered PIN and waits for the bed's
acceptance response. Connecting successfully or writing the PIN is not enough
to confirm it. The check sends no movement commands and does not set or change
the bed's PIN.

- **Accepted:** finish setup with the verified PIN.
- **PIN not required:** finish setup after capability discovery confirms this.
- **Required or rejected:** enter or correct the PIN and retry without losing
  the other settings.
- **Could not verify:** the entry remains unsaved. Wake the bed, close other
  connected apps, check the selected Bluetooth adapter or proxy, and retry.
  A timeout or connection failure does not mean the PIN is wrong.

Further setup rules:

- Initial setup uses the same absence-only path as runtime to reach capability
  verification when ping or device-info replies are omitted.
- Setup still needs a complete valid `FFFFFF` capability list and, when PIN
  capability requires it, a current PIN-state reply. A malformed or partial
  reply remains inconclusive and cannot be treated as an absent optional
  response.
- The separate Star2 protocol has no application PIN exchange and retains its
  existing setup behavior.
- Existing configured beds continue to use runtime PIN authentication and the
  repair notification described below.

### Keepalive and re-authentication

- The integration keeps the established periodic PIN keepalive (every 25
  seconds) while a configured-PIN link is held, serialized through the
  coordinator command lane. The keepalive interval is host behavior, not an app
  timing claim.
- Like earlier releases, it runs only for a receiver that reports a PIN or never
  reports its PIN state, and a receiver without a complete capability list also
  gets the configured PIN at connect.
- During a long held motor or memory operation, the controller tracks the
  existing monotonic refresh deadline from the last successful PIN write and
  refreshes within that admitted lane. Movement-write transport time counts
  toward each pulse interval. A due refresh is sent as soon as an in-flight
  movement write completes; its own write consumes the remaining pulse gap and
  can delay the next pulse if still in flight. The requested hold deadline
  remains finite.
- It also retries a stored PIN once after the app's one-second lock challenge.

### PIN enrollment

To enroll a PIN, call `adjustable_bed.octo_enroll_pin` for one Standard
receiver, enter the PIN twice, and target a single side when the bed is paired.
Home Assistant stores the PIN for reconnects after sending the enrollment
command.

### PIN protocol

`CAP_BLE_PIN` (`0x000003`) carries three separate flags. Per a clean-room
analysis of OCTO Smart Control 1.03.01 (versionCode 10301):

| Field | Meaning |
|-------|---------|
| `characteristic[0]` | The device has the PIN feature at all |
| `value[0]` | A PIN is set on the device |
| `value[1]` | `0x01` unlocked, anything else locked |

- The PIN digits are sent as **raw integers 0-9, one byte per digit** (not ASCII
  and not BCD), four digits, as `[0x20, 0x43]` + the four bytes.
- The app re-authenticates on an event, not on a timer: the device pushes a
  `0x44` LOCK notification and the app answers by re-sending the stored PIN.
- A `0x43` STATE response with `data[0] != 1` means the PIN was rejected.
- The integration handles the LOCK push, tracks STATE responses, and retains the
  25-second keepalive fallback when authentication requires it.
- Standard Octo setup reports rejected or inconclusive PIN checks before saving
  the entry; see [PIN verification](#pin-verification-during-setup).
- The PIN feature does not exist in OCTO Smart Control 1.1.57 (versionCode
  10157); it was added by versionCode 10301.

Some Octo beds require PIN authentication to control the bed. The integration automatically:

1. Detects if the bed requires PIN via feature discovery (`command=[0x20, 0x71]`)
2. Sends the configured PIN on connection (`command=[0x20, 0x43], data=[digit1, digit2, digit3, digit4]`)
3. Responds to PIN-lock notifications, tracks acceptance, and retains periodic PIN keepalive fallback (every 25 seconds when needed)

**Note:** Octo beds with PIN enabled will drop the BLE connection after ~30 seconds without re-authentication.

### Symptom: the bed connects but nothing moves

A PIN-locked receiver does **not** reject the connection. It connects and
answers the capability query, but will not act on commands until it is
authenticated, so a locked receiver with no PIN configured looks like a working
integration whose controls do nothing.

The official app hides *every* control while locked (motors, light and presets
alike), so the app itself does not distinguish between them. Users have reported
the under-bed light still responding while the motors do not, which is how this
usually presents in the field, but that asymmetry is a field observation and is
not established by the app.

The integration raises a repair notification when capability discovery reports
`CAP_BLE_PIN` locked while no PIN is configured. Enter the PIN in the
integration options to fix it.

If a support bundle is needed, `controller.protocol_state` in the bundle records
what discovery resolved: `has_pin`, `pin_locked`, `pin_configured`, `pin_sent`,
and whether `feature_discovery_complete` was reached at all. `null` means the
capability was never reported (usually a discovery timeout) rather than absent,
and the repair is left untouched in that case rather than being retracted. The
PIN value is never included.

### How to Configure Your PIN

**During initial setup:** If your bed is detected as Octo, you'll see an "Octo PIN" field in the setup wizard.

**After setup:**
1. Go to **Settings** → **Devices & Services**
2. Find your Adjustable Bed and click **Configure** (gear icon)
3. Enter your 4-digit PIN in the "Octo PIN" field
4. Click **Submit**

### Finding Your PIN

This is the receiver's OCTO app PIN, not a Bluetooth pairing code. If you set a
four-digit PIN in OCTO Smart Control, enter the same code here. If the receiver
works without a PIN, leave this field empty. Follow the manufacturer's reset
instructions if a configured PIN has been lost.

### Lost PIN: factory reset

There is **no factory-default PIN**. OCTO's recovery page
(<https://octo-customer.com/pinlost/>, linked from the app) publishes a reset
procedure per receiver instead of a default code. A factory-reset receiver has
no PIN set (`CAP_BLE_PIN` `value[0]` becomes 0), so it is no longer locked.

> [!WARNING]
> Every one of these is a **factory reset**. OCTO's wording: "this resets
> your controller to the factory settings! After this procedure, all data is
> irrevocably deleted and remotes must be reteached!" For Brick 2 that also
> includes "other connected peripherals (base station, cable remote control)".
>
> Find the PIN in the OCTO Smart Control app first. Treat the reset as the
> fallback.

| OCTO product | Likely BLE name | Procedure | Confirmation |
|--------------|-----------------|-----------|--------------|
| `CTL_RCV2` (Receiver II) | `RC2` | Button on the controller **10x in quick succession** | Light flashes 1x |
| `CTL_BMB` (BrickMini Basic) | `BMB` | Button on the controller **10x in quick succession** | Light flashes 1x |
| `CTL_BRICK2` (Brick 2) | `OCTOBrick2` | Button **1x briefly, then 1x long (approx. 10 s)** | Beeps 3x briefly |
| `9021` | not established | Button **1x briefly, then 1x long (approx. 10 s)** | Light flashes 1x |
| `1001` | not established | Button **1x briefly, then 1x long (approx. 10 s)** | Beeps 3x briefly |
| `CTL_LIFT_MICRO` | not established | Reset from the **remote**, not the controller (below) | See below |

The BLE-name column is a best-effort match against the official name prefixes;
only the first three are confident. If your receiver is not one of those, pick
it by its photo on the recovery page.

`CTL_LIFT_MICRO` is reset from the remote instead. All four hold for approx.
10 s, and the status LED starts flashing after 3 s then goes out at 10 s to
confirm:

| Remote | Keys to hold |
|--------|--------------|
| `2002` | `1` + `2` together. The remote must be in **SD mode** first (blue ring flashing; press `D` to activate it) |
| `2003` | Both side buttons together |
| `2007` | **Back up** + **Back down** together |
| `2008` | **Back up** + **Back down** together |

Procedures transcribed from <https://octo-customer.com/pinlost/> (retrieved
2026-07-25).

## Lights and settings

For complete app-authoritative capability lists, light and setting entities
follow the latest records and retire only after a later complete list proves a
capability is gone. An incomplete discovery preserves prior known surfaces. If
discovery replies are absent, the separate field-compatibility path may expose
the legacy assumed-light switch without declaring capability records
authoritative. The app exposes these direct BLE controls:

| Capability | Home Assistant surface |
| --- | --- |
| Synchro / linked mode | Switch (disabled by default; enable it in the entity registry if your bed supports linked mode) |
| Remote-control lock | Switch, hidden while PIN-locked |
| Under-bed light power | Existing switch for on/off-only records; light entity for color/intensity records |
| RGB (`CAP_LIGHT_RGB`) | RGB color mode |
| RGBWI (`CAP_LIGHT_RGBWI`) | RGBW color mode with independent intensity/brightness |
| RGB and RGBWI together | Both RGB and RGBW modes; each writes its own record |
| Light duration, 0 to 60 minutes | Number |
| Automatic light | Switch |
| Light sensitivity, 6 / 35 / 85 | Select |
| Remote teach | Button, only when active and PIN-unlocked |

- Read-only and inactive records do not create writable controls.
- The RGB and RGBWI records keep their own metadata and values. Switching color
  modes writes only the requested record; the RGBWI intensity remains unchanged
  unless an RGBW brightness value is sent.

### Light duration and expiry

- For complete advertised capabilities, a valid positive light-duration record
  gives its advertised minutes, while an explicit zero means permanent lighting.
- If duration is absent, the integration retains the established five-minute
  state-expiry fallback. An active malformed duration is not replaced with that
  fallback.
- For both switch and color-light surfaces, a deliberate ON command restarts the
  host expiry; identical on-state updates and an equivalent reconnect keep the
  existing deadline. Expiration updates the current controller without a BLE
  write.
- Explicit off, duration changes, authoritative capability loss and entity
  removal cancel or replace the deadline.

### Existing light entities

- For an on/off-only receiver, the existing `switch.*_under_bed_lights` entity
  and unique ID remain in place so existing automations continue to target the
  same entity.
- Newly discovered color or intensity capabilities may create a light entity
  without migrating or deleting that switch.
- When no capability list arrives, the legacy assumed-light command path uses
  the established on/off switch and does not invent a writable capability
  record.

## Receiver reset

`adjustable_bed.octo_reset_defaults` sends the receiver's reset-default command
only after the user supplies `confirmed: true` and the Standard receiver is in an
unlocked session.

- The controller disconnects five seconds after the command.
- This action is destructive and targets one physical receiver; paired beds
  require selecting one side.
- Tests mock the command and do not connect to physical hardware.

## Split Beds

Some Octo split beds expose one BLE controller per side, often under the same
advertised name such as `RC2` or `OCTOBrick`.

If one configured Octo entry only moves one side of the bed:

1. Add the other Octo BLE address as a second Adjustable Bed device.
2. Rename the two entries during setup so they are clearly left/right.
3. Use the `Synchro Mode` switch if your hardware supports linked movement.

The official Octo app handles this by storing separate left/right device
addresses and switching between them. Also note that the `Back + Legs Up`
preset only moves both motors on the currently connected controller; it does
not mean both bed sides.

### Paired receivers

Two compatible bed-side receivers can be paired into one Home Assistant
device.

- **Automatic connection mode** preserves each receiver's standalone connection
  policy and runs Both commands concurrently. The previous bed-type-based
  default forced a disconnect after every command, overriding each side's idle
  settings and repeating connection setup even for successive commands to the
  same side (Ref #612). Existing automatic pairs adopt the corrected policy on
  reload.
- Automatic mode falls back to sequential switching if the adapter reports that
  the second link exhausted its connection slots, and **explicit sequential
  mode** still visits the two sides in turn. This changes integration
  scheduling, not controller commands, authentication, or timing.
- When explicitly configured for sequential switching, the paired coordinator
  follows the stricter control-screen contract: a disconnect error that still
  reports an active physical link is retained and reported, and sequential
  switching stops before connecting the other address.
- A separate one-motor `RTV` remains its own TV Lift device and must not be
  added as a bed side. Pairing requires compatible bed-side actuator layouts, so
  a one-motor RTV cannot be paired with a two-motor RC2.
- This design matches three-device installations such as two `RC2` bed sides
  plus one `RTV` TV lift.
- `Synchro Mode`, when advertised by a receiver, remains a hardware capability
  and is not software grouping across arbitrary entries.

Unit tests cover left-then-right switching, abort-on-release-failure, PIN
re-authentication, memory streaming, cancellation, and STOP cleanup. The
dual-bed implementation has extensive failure, cancellation, and one-link
ordering tests, but still needs validation on real dual OCTO hardware.

The APK proves the app uses one active GATT target, but it cannot prove whether
bed firmware permits two simultaneous central connections or whether two
Bluetooth proxies behave differently from one. It also does not establish a
shared connection limit across two independent receivers. Single-proxy and
dual-proxy operation remain hardware-validation items.

## Command Timing

| Item | Value | Source |
|------|-------|--------|
| Standard motor / memory streaming | Immediately, then every 350 ms while held | App (the OCTO controller owns this cadence) |
| Standard default motor pulses | 3 pulses, 350 ms delay | Integration default |
| Card motor start / release delay | 100 ms / 100 ms | Bundled card |
| Card memory start / release delay | 100 ms / 200 ms | Bundled card |
| `hold_control` maximum | 60 seconds | Home Assistant safety bound, not an app timing value |
| Standalone memory recall window | 30 seconds | Integration safety bound |
| PIN keepalive | 25 seconds | Integration (host behavior) |
| PIN retry after lock challenge | 1 second, once | App lock challenge |
| Reset-defaults disconnect | 5 seconds after the command | Integration |
| Star2 pulses | 3 pulses, 50 ms delay | Field-verified |

- The bundled card uses the existing bounded `hold_control` service for held
  motor and memory actions, then sends STOP to the selected side when the hold
  ends.
- Star2 defaults to 3 command pulses with a 50 ms delay. This cadence produced
  smooth, jerk-free movement on a DA1458x receiver during the hardware testing
  reported in [issue #510](https://github.com/kristofferR/ha-adjustable-bed/issues/510#issuecomment-5453581631).
  Standard OCTO keeps its separate 350 ms default. Existing entries keep their
  configured overrides; change Motor Pulse Count to `3` and Motor Pulse Delay to
  `50` in the integration options if an older Star2 entry still has other
  values.

## Notes

### Analysis provenance

- **OCTO Smart Control 1.03.02 (version code 10302):** the protocol
  implementation follows the accepted clean-room analysis of
  `de.octoactuators.octosmartcontrolapp` version 1.03.02, acquired as a complete
  19 APK / 21 member set. The evidence establishes app behavior for that
  delivered artifact. It does not establish that the delivery contains every
  Play Store variant or all 57 optional locale splits. No physical bed was
  available for validation, so hardware behavior remains unverified and is
  deferred for real users after beta or release.
- The row030 audit holds the complete finding ledger, including already-covered
  behavior and explicit exclusions.

#### Official app recheck (1.03.01)

The June 16, 2026 `OCTO Smart Control` 1.03.01 XAPK (version code 10301) was
freshly decompiled and traced from its React UI through the Cordova BLE plugin.
The relevant connection, movement, memory, STOP, and PIN paths match 1.03.00.

The `1.1.57` label is not a separate app or a SemVer successor: it uses the same
package ID and signing certificate, and its Android version code is 10157 versus
10300 and 10301 for the two current builds. The numbering is consistent with
an older `1.01.57`-style build whose display label omitted zero padding. Its
source map contains the same Octo control, pairing, and packet modules. It uses
the same one-target disconnect/close switching and 350 ms movement/memory
streaming model, but predates the newer PIN-lock handling.

The current app confirms these lifecycle details:

- It has one `connectedDevice` and sends every write to that device address.
- A normal device switch runs BLE `disconnect`, then `close`, waits 300 ms, and
  only then connects the selected address. The control-screen switch aborts if
  that chain rejects. The pairing screen catches two disconnect errors and may
  continue, so it is not a safe model for error handling.
- Motor movement is sent immediately and then every 350 ms while held. Releasing
  the control clears the interval and sends `NORMAL_MOTORS_STOP` (`0x73`).
- Memory recall sends `NORMAL_MOTOR_MEMPOS` immediately and every 350 ms until
  release/cancellation, followed by the same global STOP.
- A pushed `SYSTEM_BLE_PIN_LOCK` notification immediately retransmits the saved
  four-digit PIN. `SYSTEM_BLE_PIN_STATE` reports whether the link is unlocked.
  (The accepted 1.03.02 analysis places the PIN retry one second after the lock
  challenge.)
