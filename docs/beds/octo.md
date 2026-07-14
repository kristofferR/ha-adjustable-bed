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

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [OCTO Smart Control](https://play.google.com/store/apps/details?id=de.octoactuators.octosmartcontrolapp) | `de.octoactuators.octosmartcontrolapp` |

## PIN Configuration

Some Octo beds require a 4-digit PIN to maintain the Bluetooth connection. Without the PIN, the bed will disconnect after ~30 seconds.

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
| Both Up Preset | ✅ (Standard variant: moves head + legs together) |
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

Octo beds have at least two protocol variants. The integration auto-detects the variant based on the service UUID.

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
| `0x000003` | CAP_PIN | PIN requirement + lock state |
| `0x000101` | CAP_SYNCHRO | Synchro/linked mode support |
| `0x000102` | CAP_LIGHT | Under-bed light support (on/off) |
| `0x000104` | CAP_LIGHT_RGBWI | RGB + White + Intensity light control |
| `0xFFFFFF` | End sentinel | Marks end of feature list |

#### RGBWI Light Commands

Beds with the `CAP_LIGHT_RGBWI` feature support full RGBW color control. The integration exposes a **Light** entity with an RGBW color picker instead of a simple on/off switch.

Colors are set via `SYSTEM_SET_CAPS` packets targeting feature ID `0x000104`, with data `[R, G, B, W, I]` where each channel is 0-255. The intensity (I) channel is fixed at 255.

| Command | Command Bytes | Data | Description |
|---------|---------------|------|-------------|
| Set RGBWI | `[0x20, 0x73]` | `[valueType, 0x00, 0x01, 0x04, R, G, B, W, 0xFF]` | Set light color (R/G/B/W channels + full intensity) |

#### PIN Authentication

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

**Note:** Star2 variant does not support lights or PIN authentication.

## Detection

- **Standard variant:** Detected by an official OCTO device-name prefix. The
  shared `FFE0` service UUID alone is not sufficient because other protocol
  families also use it.
- **Star2 variant:** Auto-detected by service UUID `0000aa5c-0000-1000-8000-00805f9b34fb`

You can also manually select the variant in the integration options.

Recognized Standard-variant name prefixes are:

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

These names select the likely protocol implementation. Features are still
limited by the device capabilities and the support table above, and every OEM
combination is not necessarily hardware-tested.
