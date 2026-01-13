# Adjustable Bed Connection Guide

This guide explains how to connect your adjustable bed to Home Assistant.

## Understanding Bluetooth Connectivity

Most adjustable beds use Bluetooth Low Energy (BLE) to communicate with their remote controls and apps. This integration connects directly to your bed's BLE controller.

**Key Points:**
- **BLE Range**: Typically 10-30 meters, but walls and interference reduce this
- **Single Connection**: Most beds only accept ONE Bluetooth connection at a time - disconnect manufacturer apps first
- **Idle Disconnect**: The integration disconnects after 40 seconds of idle time to allow other devices to connect

---

## Connection Methods

### *Method 1: ESPHome Bluetooth Proxy (Recommended)*

Use an ESP32 device running ESPHome as a Bluetooth proxy. This extends your Bluetooth range using WiFi.


**Pros:** Excellent range (place ESP32 near the bed), multiple proxies for whole-home coverage

**Cons:** Requires additional hardware (~$5-15)


### *Method 2: Local Bluetooth Adapter*

If your Home Assistant host has a Bluetooth adapter (built-in or USB dongle).


**Pros:** Simple setup, no additional hardware

**Cons:** Limited range, may not work if HA host is far from bed

---

## Setting Up an ESPHome Bluetooth Proxy

1. **Get an ESP32 Board**
   - M5Stack Atom Lite (~$8)
   - ESP32-WROOM-32 DevKit (~$5)
   - ESP32-C3 Mini (~$4)

2. **Flash ESPHome Bluetooth Proxy Firmware**

   **Easy way:** Visit [ESPHome Bluetooth Proxy](https://esphome.github.io/bluetooth-proxies/), connect your ESP32 via USB, and follow the prompts.

   **Or use ESPHome Dashboard** with this configuration:

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
     - platform: esphome

   bluetooth_proxy:
     active: true

   esp32_ble_tracker:
     scan_parameters:
       active: true
   ```

3. **Place Near Your Bed** (within 5-10 meters, avoid metal obstructions)

4. **Add to Home Assistant** - The ESP32 should be auto-discovered in Settings → Devices & Services

---

## Adding Your Adjustable Bed

1. **Power on your bed** and disconnect any manufacturer apps or remove batteries from remotes

2. **Add the integration**: Settings → Devices & Services → Add Integration → "Adjustable Bed"

3. **Discovery or Manual Entry**
   - **Automatic:** Select your bed from the discovered list
   - **Manual:** Enter the Bluetooth MAC address (format: `AA:BB:CC:DD:EE:FF`) and select bed type

4. **Configure Settings**
   - **Name**: Friendly name for your bed
   - **Motor Count**: See below
   - **Has Massage**: Enable if your bed has massage
   - **Protocol Variant** (if available): Usually leave as "auto"
   - **Command Protocol** (Richmat only): Try different protocols if bed doesn't respond

---

## Advanced Options

After setup, you can adjust additional settings via **Settings → Integrations → Adjustable Bed → Configure**:

| Setting | Description |
|---------|-------------|
| Protocol Variant | Override auto-detected variant (Keeson: base/ksbt, Richmat: nordic/wilinke) |
| Command Protocol | Richmat only: Override command byte encoding |
| Motor Pulse Count | Fine-tune motor movement duration (1-100) |
| Motor Pulse Delay | Fine-tune motor smoothness (10-500ms) |
| Bluetooth Adapter | Choose specific adapter or proxy |

See [Motor Pulse Settings](SUPPORTED_ACTUATORS.md#motor-pulse-settings) for details on pulse configuration.

---

## Finding the Bluetooth Address

If your bed isn't auto-discovered:

**Using nRF Connect App (Recommended):**
1. Install "nRF Connect" on your phone
2. Start scanning
3. Look for your bed (often named "Desk XXXXX" for Linak, "HHC..." for MotoSleep, etc.)
4. Note the MAC address

**Using ESPHome Logs:**
1. Open ESPHome dashboard → View logs for your proxy
2. Look for: `[bluetooth_proxy] Proxying packet from AA:BB:CC:DD:EE:FF...`

---

## Motor Count Configuration

| Motors | Sections |
|--------|----------|
| 2 (most common) | Back + Legs |
| 3 | Head + Back + Legs |
| 4 | Head + Back + Legs + Feet |

**How to determine:** Count the distinct moving sections when using your remote, or check your bed's manual.

---

## Next Steps

- **Having issues?** See [Troubleshooting](TROUBLESHOOTING.md)
- **Want to know more about your bed?** See [Supported Actuators](SUPPORTED_ACTUATORS.md)
