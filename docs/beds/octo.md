# Octo

**Status:** ✅ Protocol tested for 2-4 motor bed receivers; one-motor RTV TV lift implementation is based on the official app and needs hardware validation

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), [_pm](https://community.home-assistant.io/t/how-to-setup-esphome-to-control-my-bluetooth-controlled-octocontrol-bed/540790), [goedh452](https://community.home-assistant.io/t/how-to-setup-esphome-to-control-my-bluetooth-controlled-octocontrol-bed/540790/10), Murp, and [Brokkert](https://github.com/Brokkert)

## Known Models

- Octo-branded adjustable beds
- Beka
- Cozyworld Cozy2Go

OCTO Smart Control also recognizes one-motor products that use the same
protocol family. The integration supports the official `RTV` **Lift 1M** as a
separate TV Lift device.

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

`00000000` is OCTO Actuators itself, `00000002` is a placeholder ("pink dummy"),
`FFFFFFFD`/`FFFFFFFE` are demo entries, and `FFFFFFFF` marks a receiver whose
customer ID is not app-enabled (the app then shows "This hardware does not
provide app support. Please contact your dealer"). That last one is a licensing
check and is unrelated to the PIN lock.

Brand names are taken from `brandinginfo.json` in OCTO Smart Control 1.03.01
and cross-checked against the bundled logo artwork, which is why two differ
from the raw JSON labels: `00000003` is styled *sleepling*, and `0000000F` is
RöWa's *selecta* line. This list is what the app knows and is not exhaustive:
an OEM absent here can still use OCTO hardware.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [OCTO Smart Control](https://play.google.com/store/apps/details?id=de.octoactuators.octosmartcontrolapp) | `de.octoactuators.octosmartcontrolapp` |

## PIN Configuration

Some Octo beds require a 4-digit PIN to maintain the Bluetooth connection. Without the PIN, the bed will disconnect after ~30 seconds.

### PIN verification during setup (v4)

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

The separate Star2 protocol has no application PIN exchange and retains its
existing setup behavior. Existing configured beds continue to use runtime PIN
authentication and the repair notification described below.

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

### Lost PIN: factory reset

There is **no factory-default PIN**. OCTO's recovery page
(<https://octo-customer.com/pinlost/>, linked from the app) publishes a reset
procedure per receiver instead of a default code. A factory-reset receiver has
no PIN set (`CAP_BLE_PIN` `value[0]` becomes 0), so it is no longer locked.

> ⚠️ Every one of these is a **factory reset**. OCTO's wording: "this resets
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

## Features

| Feature | Supported |
|---------|-----------|
| Bed Motor Control | ✅ (2-4 motors; configured during setup and checked against CAP_MOTORCOUNT) |
| One-motor TV/Bed Lift | ✅ (Standard variant; dedicated TV Lift entity, hardware validation pending) |
| Position Feedback | ❌ |
| Memory Presets | ✅ (dynamically detected, Standard variant only) |
| Combined Back + Legs Control | ✅ (two-motor Standard and Star2 variants; hold-capable in the bundled card) |
| Under-bed Lights | ✅ (Standard variant only; RGBW color picker on beds with CAP_LIGHT_RGBWI) |
| Synchro/Linked Mode | ✅ (Standard variant, split-king beds with CAP_SYNCHRO) |
| PIN Authentication | ✅ (Standard variant only) |

### One-motor TV lift

The official OCTO device list identifies `RTV` as **Lift 1M**, and the official
app controls it through Standard OCTO motor 1 (`0x02`). An automatically
discovered `RTV` defaults to one motor and exposes one **TV Lift** cover with
Raise, Lower, and Stop controls. You can also select one motor manually for a
Standard OCTO controller.

The lift is deliberately not presented as an adjustable bed. Bed-only controls
such as Flat, Back + Legs Up, memory positions, lights, and synchro mode are
suppressed even if a malformed or unexpected capability response advertises
them. Position feedback is not available. The packet implementation is derived
from the official OCTO app; physical RTV hardware testing is still required.

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

### Official app recheck (1.03.01)

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

The paired coordinator follows the stricter control-screen contract: a
disconnect error that still reports an active physical link is retained and
reported, and sequential switching stops before connecting the other address.
Unit tests cover left-then-right switching, abort-on-release-failure, PIN
re-authentication, memory streaming, cancellation, and STOP cleanup.

The APK proves the app uses one active GATT target, but it cannot prove whether
bed firmware permits two simultaneous central connections or whether two
Bluetooth proxies behave differently from one. Single-proxy and dual-proxy
operation therefore remain hardware-validation items; the integration makes no
concurrency claim and uses the conservative one-link-at-a-time profile.

In 4.0, two compatible bed-side receivers can be paired into one Home Assistant
device. OCTO pairs use conservative one-link switching: Left, Right, or Both
commands connect to one side at a time, and Both visits the two sides
sequentially. A separate one-motor `RTV` remains its own TV Lift device and must
not be added as a bed side. Pairing requires compatible bed-side actuator
layouts, so a one-motor RTV cannot be paired with a two-motor RC2.

This design matches three-device installations such as two `RC2` bed sides plus
one `RTV` TV lift. The 4.0 dual-bed implementation has extensive failure,
cancellation, and one-link ordering tests, but still needs validation on real
dual OCTO hardware. `Synchro Mode`, when advertised by a receiver, remains a
hardware capability and is not software grouping across arbitrary entries.

## Protocol Variants

Octo beds have at least two protocol variants. Standard OCTO requires a
recognized official device-name prefix because its `FFE0` service UUID is
shared with other protocols. Star2 is auto-detected when its dedicated
`0000aa5c-0000-1000-8000-00805f9b34fb` service contains the
`00005a55-0000-1000-8000-00805f9b34fb` write characteristic. Explicit variant
selections override this GATT-based detection.

### Standard Variant (Most Common)

**Service UUID:** `0000ffe0-0000-1000-8000-00805f9b34fb`
**Write Characteristic:** `0000ffe1-0000-1000-8000-00805f9b34fb`
**Format:** Packet-based with start/end markers and checksum

#### Packet Structure

```text
[0x40, cmd[0], cmd[1], len_hi, len_lo, checksum, ...data, 0x40]
```

**Checksum:** `((sum_of_all_bytes XOR 0xFF) + 1) & 0xFF`

Bytes `0x40`, `0x3C`, `0x4F`, and `0x41` inside the frame payload are escaped.
The delimiters themselves remain unescaped.

#### Notification framing

An OCTO packet and a BLE notification are not the same boundary. A complete
packet can span multiple notified characteristic values, and one notified value
can contain multiple packets. The integration keeps an incomplete response
between callbacks, extracts every complete `0x40 ... 0x40` frame, then verifies
its unescaped length and checksum before dispatching it. Malformed data is
discarded up to the next possible frame delimiter.

#### Motor Commands

Motors are controlled via bit masks (CAP_MOTORCOUNT determines how many are available):

- Motor 1 (Head/Back): `0x02`
- Motor 2 (Legs): `0x04`
- Motor 3: `0x08` (beds with CAP_MOTORCOUNT > 2)
- Motor 4: `0x10` (beds with CAP_MOTORCOUNT > 3)
- Both motors 1+2: `0x06`

| Command | Command Bytes | Data | Description |
|---------|---------------|------|-------------|
| Move Up | `[0x02, 0x70]` | `[motor_bits]` | Move motor(s) up |
| Move Down | `[0x02, 0x71]` | `[motor_bits]` | Move motor(s) down |
| Stop | `[0x02, 0x73]` | none | Stop all motors |

The official app builds its control layout from `CAP_MOTORCOUNT` alone, and the
combined steps it offers are:

| Motors | Steps offered |
|--------|---------------|
| 1 | M1 `0x02` |
| 2 | M1 `0x02`, M2 `0x04`, M1+2 `0x06` |
| 3 | M3 `0x08`, M1, M2, M1+2, then M1+2+3 `0x0E` **down only** |
| 4 | M1, M2, M3, M4 `0x10`, M1+2, M3+4 `0x18`, then M1+2+3+4 `0x1E` **down only** |

The all-motors step is down-only in the app, which is what "Flat" means for
this protocol: the integration's Flat control sends `0x06`, `0x0E` or `0x1E`
according to the configured motor count, so 3M and 4M receivers (`RC3`, `BM3`
and 4-motor bases) actually reach flat instead of leaving the extra actuators
parked. A motor count the app does not recognize renders no controls at all.

On a two-motor receiver, M1+2 is exposed as a **Back + Legs** motor control.
Its Up and Down actions replace the former tap-only Back + Legs Up and Flat
preset tiles, so the bundled card can repeat the command while the control is
held. Three- and four-motor receivers retain separate preset controls because
their all-motors-down command covers more actuators than Both Up.

#### Light Commands

| Command | Command Bytes | Data | Description |
|---------|---------------|------|-------------|
| Lights On | `[0x20, 0x72]` | `[0x00, 0x01, 0x02, 0x01, 0x01, 0x01, 0x01, 0x01]` | Turn on under-bed lights |
| Lights Off | `[0x20, 0x72]` | `[0x00, 0x01, 0x02, 0x01, 0x01, 0x01, 0x01, 0x00]` | Turn off under-bed lights |

#### Synchro/Linked Mode Commands

For split-king beds with CAP_SYNCHRO capability, the drive mode can be toggled between independent (single) and linked (sync) operation:

| Command | Command Bytes | Data | Description |
|---------|---------------|------|-------------|
| Set Single Mode | `[0x10, 0x71]` | `[0x00]` | Independent motor control |
| Set Sync Mode | `[0x10, 0x71]` | `[0x01]` | Linked/synchro motor control |
| Get Drive Mode | `[0x10, 0x72]` | none | Query current drive mode |

The Synchro Mode switch entity is disabled by default. Enable it in the entity registry if your bed supports linked mode.

#### Feature Discovery

The integration queries capabilities via `[0x20, 0x71]`. Known feature IDs:

| Feature ID | Name | Value |
|------------|------|-------|
| `0x000001` | CAP_MOTORCOUNT | Motor count reported by the device (1-4; Standard OCTO supports 1-4) |
| `0x000002` | CAP_MEMCOUNT | Memory preset count |
| `0x000003` | CAP_BLE_PIN | PIN state + lock state (see below) |
| `0x000004` | CAP_MEMINFO | Memory slot classes and per-slot names |
| `0x000101` | CAP_SYNCHRO | Synchro/linked mode support |
| `0x000102` | CAP_LIGHT | Under-bed light support (on/off) |
| `0x000104` | CAP_LIGHT_RGBWI | RGB + White + Intensity light control |
| `0xFFFFFF` | End sentinel | Marks end of feature list |

#### Memory slots (`CAP_MEMINFO`, `0x000004`)

Beds that report `CAP_MEMINFO` describe their memory slots in more detail than
the bare count in `CAP_MEMCOUNT`:

- `characteristic[]` is exactly three bytes, `[memCount, fixCount, lockCount]`.
  A record with any other length is ignored entirely.
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

The integration hides the Save button for locked slots. If the value block is
the wrong length the descriptions are dropped but the class protection is kept,
so a malformed response cannot silently turn a locked slot into a writable one.

Known description IDs are `0x01` Anti-Snore, `0x02` Zero-G, `0x03` Lordose and
`0x04` Flat (`0x00` means unnamed). A named slot is used as the entity name, so
you get a "Zero-G" button rather than "Memory 3". Unrecognized IDs fall back to
the generic name.

Recall and save differ by packet **type**, not just command byte:

| Action | Packet | Data | Notes |
|--------|--------|------|-------|
| Recall slot | `NORMAL` `[0x02, 0x72]` | `[slot]` | **Hold-to-run**, repeated every 350 ms and released with `[0x02, 0x73]` |
| Save slot | `CONFIG` `[0x10, 0x70]` | `[slot]` | One-shot |

`slot` is 0-based on the wire while the UI counts from 1. Recall being
hold-to-run matters: sending it once moves the bed a fraction of the way and
then stalls.

**There is no arrival signal.** In the official app, recall is a press-and-hold
control that streams for exactly as long as the user holds the button. The
protocol has no completion or position notification (the inbound `NORMAL`
branch is empty and no position capability exists) and no timeout, so a
headless client cannot know when the bed has reached the stored position.

The integration therefore streams the recall for a fixed 30 second window and
then releases the motors. That bound is **ours, not OCTO's**: it is chosen to
outlast a full-travel move rather than to match the ~1 second a button press
implies. The bed stops itself at its end stops, the STOP frame is always sent
afterwards, and pressing Stop cancels the recall immediately.

#### RGBWI Light Commands

Beds with the `CAP_LIGHT_RGBWI` feature support full RGBW color control. The integration exposes a **Light** entity with an RGBW color picker instead of a simple on/off switch.

Colors are set via `SYSTEM_SET_CAPS` packets targeting feature ID `0x000104`, with data `[R, G, B, W, I]` where each channel is 0-255. The intensity (I) channel is fixed at 255.

| Command | Command Bytes | Data | Description |
|---------|---------------|------|-------------|
| Set RGBWI | `[0x20, 0x73]` | `[valueType, 0x00, 0x01, 0x04, R, G, B, W, 0xFF]` | Set light color (R/G/B/W channels + full intensity) |

#### PIN Authentication

`CAP_BLE_PIN` (`0x000003`) carries three separate flags. Per a clean-room
analysis of OCTO Smart Control 1.03.01 (versionCode 10301):

| Field | Meaning |
|-------|---------|
| `characteristic[0]` | The device has the PIN feature at all |
| `value[0]` | A PIN is set on the device |
| `value[1]` | `0x01` unlocked, anything else locked |

The PIN digits are sent as **raw integers 0-9, one byte per digit** (not ASCII
and not BCD), four digits, as `[0x20, 0x43]` + the four bytes.

The app re-authenticates on an event, not on a timer: the device pushes a
`0x44` LOCK notification and the app answers by re-sending the stored PIN. A
`0x43` STATE response with `data[0] != 1` means the PIN was rejected. The
integration currently re-sends the PIN on a 25-second timer instead, which
covers the same ground more bluntly; handling the `0x44` push and surfacing a
rejected PIN are open improvements.

The PIN feature does not exist in OCTO Smart Control 1.1.57 (versionCode
10157); it was added by versionCode 10301.

Some Octo beds require PIN authentication to control the bed. The integration automatically:
1. Detects if the bed requires PIN via feature discovery (`command=[0x20, 0x71]`)
2. Sends the configured PIN on connection (`command=[0x20, 0x43], data=[digit1, digit2, digit3, digit4]`)
3. Maintains the connection with periodic PIN keep-alive messages (every 25 seconds)

**Note:** Octo beds with PIN enabled will drop the BLE connection after ~30 seconds without re-authentication.

To configure PIN, enter your 4-digit PIN during setup or in the integration options.

### Star2 Variant (Octo Remote Star2)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), [goedh452](https://community.home-assistant.io/t/how-to-setup-esphome-to-control-my-bluetooth-controlled-octocontrol-bed/540790/10)

**Service UUID:** `0000aa5c-0000-1000-8000-00805f9b34fb`
**Write Characteristic:** `00005a55-0000-1000-8000-00805f9b34fb`
**Write Type:** Write request (with response)
**Format:** Fixed 15-byte commands starting with `0x68`, ending with `0x16`

#### Motor Commands

| Action | Bytes (hex) |
|--------|-------------|
| Head Up | `68 30 31 30 30 30 30 30 30 31 30 36 31 38 16` |
| Head Down | `68 30 31 30 30 30 30 30 30 31 30 39 31 3B 16` |
| Feet Up | `68 30 31 30 30 30 30 30 30 31 30 34 31 36 16` |
| Feet Down | `68 30 31 30 30 30 30 30 30 31 30 37 31 39 16` |
| Both Up | `68 30 31 30 30 30 30 30 30 31 32 37 31 3B 16` |
| Both Down | `68 30 31 30 30 30 30 30 30 31 32 38 31 3C 16` |

Star2 defaults to 3 command pulses with a 50 ms delay. This cadence produced
smooth, jerk-free movement on a DA1458x receiver during the hardware testing
reported in [issue #510](https://github.com/kristofferR/ha-adjustable-bed/issues/510#issuecomment-5453581631).
Standard OCTO keeps its separate 350 ms default. Existing entries keep their
configured overrides; change Motor Pulse Count to `3` and Motor Pulse Delay to
`50` in the integration options if an older Star2 entry still has other values.

The Star2 Both Up and Both Down frames are exposed as the Up and Down actions
of the **Back + Legs** motor control. In the bundled card this makes the
combined movement hold-capable, like the individual Back and Legs controls.

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
