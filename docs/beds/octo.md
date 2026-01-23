# Octo

**Status:** ✅ Tested

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), [_pm](https://community.home-assistant.io/t/how-to-setup-esphome-to-control-my-bluetooth-controlled-octocontrol-bed/540790), [goedh452](https://community.home-assistant.io/t/how-to-setup-esphome-to-control-my-bluetooth-controlled-octocontrol-bed/540790/10), Murp, and [Brokkert](https://github.com/Brokkert)

## Known Models
- Octo-branded adjustable beds
- Beka

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

The PIN is typically found in your Octo physical remote's settings menu, or in the documentation that came with your bed. If you don't know your PIN and the bed works without one, leave it empty.

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | ❌ |
| Memory Presets | ❌ |
| Under-bed Lights | ✅ (Standard variant only) |
| PIN Authentication | ✅ (Standard variant only) |

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

#### Motor Commands

Motors are controlled via bit masks:

- Head motor: `0x02`
- Legs motor: `0x04`
- Both motors: `0x06`

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

#### PIN Authentication

Some Octo beds require PIN authentication to control the bed. The integration automatically:
1. Detects if the bed requires PIN via feature discovery (`command=[0x20, 0x71]`)
2. Sends the configured PIN on connection (`command=[0x20, 0x43], data=[digit1, digit2, digit3, digit4]`)
3. Maintains the connection with periodic PIN keep-alive messages (every 25 seconds)

**Note:** Octo beds with PIN enabled will drop the BLE connection after ~30 seconds without re-authentication.

To configure PIN, enter your 4-digit PIN during setup or in the integration options.

### Star2 Variant (Octo Remote Star2)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed). Protocol reverse-engineered by [goedh452](https://community.home-assistant.io/t/how-to-setup-esphome-to-control-my-bluetooth-controlled-octocontrol-bed/540790/10)

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

- **Standard variant:** Detected by device name containing `octo`
- **Star2 variant:** Auto-detected by service UUID `0000aa5c-0000-1000-8000-00805f9b34fb`

You can also manually select the variant in the integration options.
