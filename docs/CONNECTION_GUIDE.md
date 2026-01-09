# Smart Bed Connection Guide

This guide explains how to connect your smart bed to Home Assistant using this integration.

## Table of Contents

- [Understanding Bluetooth Connectivity](#understanding-bluetooth-connectivity)
- [Supported Beds](#supported-beds)
- [Connection Methods](#connection-methods)
- [Setup Instructions](#setup-instructions)
- [Identifying Your Bed](#identifying-your-bed)
- [Motor Count Configuration](#motor-count-configuration)
- [Troubleshooting](#troubleshooting)
- [Technical Details](#technical-details)

---

## Understanding Bluetooth Connectivity

Most smart beds use Bluetooth Low Energy (BLE) to communicate with their remote controls and apps. This integration connects directly to your bed's BLE controller, giving you full control through Home Assistant.

### Key Points

1. **BLE Range**: Typical BLE range is 10-30 meters, but walls and interference can reduce this significantly
2. **Single Connection**: Most beds only accept ONE Bluetooth connection at a time. If the manufacturer's app is connected, Home Assistant won't be able to connect
3. **Connection Persistence**: The integration maintains a connection while in use and disconnects after 40 seconds of idle time to allow other devices to connect

---

## Supported Beds

### Currently Implemented

| Brand | BLE Service UUID | Notes |
|-------|------------------|-------|
| **Linak** | `99fa0001-338a-1024-8a49-009c0215f78a` | Full support with position feedback |

### Planned (Not Yet Implemented)

- Richmat
- Solace
- MotoSleep
- Reverie
- Leggett & Platt (Okin and Richmat variants)
- Okimat
- Keeson
- Octo
- Sleeptracker AI (cloud-based)

---

## Connection Methods

### Method 1: Local Bluetooth Adapter

If your Home Assistant host has a Bluetooth adapter (built-in or USB dongle):

**Pros:**
- Simple setup
- No additional hardware needed

**Cons:**
- Limited range (depends on adapter and obstacles)
- May not work if HA host is far from bed

**Requirements:**
- Home Assistant OS, Supervised, or Container with Bluetooth access
- Bluetooth adapter supported by BlueZ
- Bed within Bluetooth range of HA host

### Method 2: ESPHome Bluetooth Proxy (Recommended)

Use an ESP32 device running ESPHome as a Bluetooth proxy. This extends your Bluetooth range using WiFi.

**Pros:**
- Excellent range (place ESP32 near the bed)
- Works seamlessly with HA's Bluetooth stack
- Multiple proxies for whole-home coverage

**Cons:**
- Requires additional hardware (~$5-15)
- Initial ESP32 setup required

**Requirements:**
- ESP32 development board (ESP32-WROOM, M5Stack Atom, etc.)
- ESPHome addon or CLI
- WiFi network

---

## Setup Instructions

### Setting Up an ESPHome Bluetooth Proxy

1. **Get an ESP32 Board**

   Recommended boards:
   - M5Stack Atom Lite (~$8)
   - ESP32-WROOM-32 DevKit (~$5)
   - ESP32-C3 Mini (~$4)

2. **Flash ESPHome Bluetooth Proxy Firmware**

   **Option A: Web Installer (Easiest)**
   - Visit [ESPHome Bluetooth Proxy](https://esphome.github.io/bluetooth-proxies/)
   - Connect your ESP32 via USB
   - Click "Connect" and follow the prompts
   - Enter your WiFi credentials

   **Option B: ESPHome Dashboard**
   - Install ESPHome addon in Home Assistant
   - Create a new device with this configuration:

   ```yaml
   esphome:
     name: ble-proxy-bedroom
     friendly_name: Bedroom BLE Proxy

   esp32:
     board: esp32dev
     framework:
       type: esp-idf

   wifi:
     ssid: !secret wifi_ssid
     password: !secret wifi_password

   api:
     encryption:
       key: !secret api_encryption_key

   ota:
     platform: esphome

   logger:

   bluetooth_proxy:
     active: true

   esp32_ble_tracker:
     scan_parameters:
       active: true
   ```

3. **Place the ESP32 Near Your Bed**

   - Within 5-10 meters of the bed controller
   - Power via USB
   - Avoid metal obstructions between the proxy and bed

4. **Add to Home Assistant**

   - The ESP32 should be auto-discovered
   - Go to Settings → Devices & Services
   - Add the ESPHome device
   - **Important**: The ESPHome integration will now route Bluetooth traffic through the proxy

### Adding Your Smart Bed

1. **Power On Your Bed**

   - Ensure the bed controller has power
   - Disconnect any manufacturer apps (they may be holding the BLE connection)

2. **Add the Integration**

   - Go to Settings → Devices & Services
   - Click "+ Add Integration"
   - Search for "Smart Bed"

3. **Discovery or Manual Entry**

   **Automatic Discovery:**
   - If your bed is detected, you'll see it in the list
   - Select it and confirm

   **Manual Entry:**
   - Choose "Enter address manually"
   - Enter the Bluetooth MAC address (format: `AA:BB:CC:DD:EE:FF`)
   - Select the bed type

4. **Configure Settings**

   - **Name**: Friendly name for your bed
   - **Motor Count**: See [Motor Count Configuration](#motor-count-configuration)
   - **Has Massage**: Enable if your bed has massage functionality

---

## Identifying Your Bed

### Finding the Bluetooth Address

If your bed isn't auto-discovered, you need to find its BLE address.

**Method 1: nRF Connect App (Recommended)**

1. Install "nRF Connect" on your phone (iOS/Android)
2. Open the app and start scanning
3. Look for devices with names like:
   - `Desk XXXXX` (Linak beds)
   - `YOURBED` or similar
4. Note the MAC address

**Method 2: Home Assistant Bluetooth Scanner**

1. Go to Developer Tools → Services
2. Call `bluetooth.start_scan`
3. Check the logs for discovered devices

**Method 3: ESPHome Logs**

If you have an ESPHome proxy:

1. Open ESPHome dashboard
2. View logs for your proxy
3. Look for BLE advertisements:
   ```
   [bluetooth_proxy] Proxying packet from AA:BB:CC:DD:EE:FF...
   ```

### Identifying Linak Beds

Linak bed controllers typically:
- Have device names starting with "Desk" (e.g., "Desk 12345")
- Advertise service UUID: `99fa0001-338a-1024-8a49-009c0215f78a`
- May have a label on the controller showing "Linak" branding

---

## Motor Count Configuration

Different bed models have different numbers of motors:

### 2-Motor Beds (Most Common)
- **Back/Upper Body**: Raises the upper portion
- **Legs**: Raises the leg portion

### 3-Motor Beds
- **Head**: Independent head tilt
- **Back**: Upper body support
- **Legs**: Leg elevation

### 4-Motor Beds
- **Head**: Independent head tilt
- **Back**: Upper body support
- **Legs**: Knee/thigh elevation
- **Feet**: Foot elevation

### How to Determine Motor Count

1. **Count the moving sections**: Press your remote's buttons and count distinct movements
2. **Check your bed's manual**: Should specify the number of motors
3. **Look at the controller**: May have labels for each motor

---

## Troubleshooting

### Enable Debug Logging

Add to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.smartbed: debug
    homeassistant.components.bluetooth: debug
    bleak: debug
```

Restart Home Assistant and check the logs.

### Common Issues

#### "Device not found"

**Symptoms:**
- Integration can't find the bed
- Logs show "Device X not found in Bluetooth scanner"

**Solutions:**
1. Ensure bed is powered on
2. Disconnect manufacturer app
3. Check Bluetooth adapter/proxy is working
4. Move proxy closer to bed
5. Verify the MAC address is correct

#### "Failed to connect"

**Symptoms:**
- Device is found but connection fails
- Logs show BLE connection errors

**Solutions:**
1. Power cycle the bed controller
2. Restart Home Assistant
3. Check if another device is connected to the bed
4. Update ESPHome proxy firmware

#### "Commands not working"

**Symptoms:**
- Connected but bed doesn't respond
- Logs show commands being sent

**Solutions:**
1. Verify correct bed type is selected
2. Check motor count configuration
3. Try pressing physical remote to "wake" the bed
4. Check for firmware updates on bed controller

#### "Position sensors not updating"

**Symptoms:**
- Connected and commands work
- Angle sensors stay at 0 or unknown

**Cause:**
Not all beds support position feedback. This requires specific GATT characteristics that some controllers don't implement.

**Solutions:**
1. This may be normal for your bed model
2. Check logs for "Position notifications unavailable" messages

### ESPHome Proxy Issues

#### "Already connected to another client"

This was a major issue with the old smartbed-mqtt addon. This new integration uses Home Assistant's native Bluetooth stack, which handles ESPHome proxies correctly.

If you're still having issues:
1. Ensure you're using ESPHome 2024.1.0 or later
2. Update the Bluetooth Proxy to the latest version
3. Don't add multiple Bluetooth integrations for the same proxy

---

## Technical Details

### Linak Protocol

**Control Service:** `99fa0001-338a-1024-8a49-009c0215f78a`
- Write characteristic: `99fa0002-338a-1024-8a49-009c0215f78a`
- Commands are 2 bytes: `[command, 0x00]`

**Position Service:** `99fa0020-338a-1024-8a49-009c0215f78a`
- Back position: `99fa0028-...` (notify)
- Leg position: `99fa0027-...` (notify)
- Head position: `99fa0026-...` (notify, 3+ motors)
- Feet position: `99fa0025-...` (notify, 4 motors)

Position data is 2 bytes little-endian, converted to angle using calibration:
- Back: max 820 → 68°
- Leg: max 548 → 45°

### Command Reference (Linak)

| Command | Bytes | Description |
|---------|-------|-------------|
| Preset Memory 1 | `0x0E 0x00` | Go to memory position 1 |
| Preset Memory 2 | `0x0F 0x00` | Go to memory position 2 |
| Preset Memory 3 | `0x0C 0x00` | Go to memory position 3 |
| Preset Memory 4 | `0x44 0x00` | Go to memory position 4 |
| Program Memory 1 | `0x38 0x00` | Save current to memory 1 |
| Program Memory 2 | `0x39 0x00` | Save current to memory 2 |
| Program Memory 3 | `0x3A 0x00` | Save current to memory 3 |
| Program Memory 4 | `0x45 0x00` | Save current to memory 4 |
| Lights On | `0x92 0x00` | Turn on under-bed lights |
| Lights Off | `0x93 0x00` | Turn off under-bed lights |
| Lights Toggle | `0x94 0x00` | Toggle under-bed lights |
| Stop | `0x00 0x00` | Stop all motors |
| Head Up | `0x03 0x00` | Raise head |
| Head Down | `0x02 0x00` | Lower head |
| Back Up | `0x0B 0x00` | Raise back |
| Back Down | `0x0A 0x00` | Lower back |
| Legs Up | `0x09 0x00` | Raise legs |
| Legs Down | `0x08 0x00` | Lower legs |
| Feet Up | `0x05 0x00` | Raise feet |
| Feet Down | `0x04 0x00` | Lower feet |

---

## Getting Help

If you're still having issues:

1. **Check the logs** with debug logging enabled
2. **Open an issue** on GitHub with:
   - Your bed brand/model
   - Home Assistant version
   - Relevant log excerpts
   - ESPHome proxy version (if used)
3. **Community forums**: Search or ask on the Home Assistant Community

---

## Contributing

Found a bug or want to add support for a new bed type?

1. Fork the repository
2. Enable debug logging and capture the BLE traffic
3. Document the protocol (services, characteristics, commands)
4. Submit a pull request

We especially welcome contributions for:
- New bed types (Richmat, Reverie, etc.)
- Protocol documentation
- Bug fixes and improvements
