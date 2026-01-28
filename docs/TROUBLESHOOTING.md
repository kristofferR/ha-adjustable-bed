# Troubleshooting Guide

This guide covers common issues and their solutions when using the Adjustable Bed integration.

## Table of Contents

- [Connection Issues](#connection-issues)
- [Commands Not Working](#commands-not-working)
- [Position Feedback Issues](#position-feedback-issues)
- [Physical Remote Conflicts](#physical-remote-conflicts)
- [Protocol/Variant Issues](#protocolvariant-issues)
- [Pairing Required (Okimat/Leggett Okin)](#pairing-required-okimatleggett-okin)
- [Classic Bluetooth Beds (Not Supported)](#classic-bluetooth-beds-not-supported)
- [Quick Reference: Service UUIDs](#quick-reference-service-uuids)
- [Still Need Help?](#still-need-help)

---

## Connection Issues

### "Failed to connect to bed"

**Possible Causes:**
1. Bed is powered off or in standby mode
2. Another device is already connected (phone app, remote, another HA instance)
3. Bed is out of Bluetooth range
4. Bluetooth adapter issues

**Solutions:**
1. **Power cycle the bed:** Unplug the bed's power for 30 seconds, then plug it back in
2. **Close other apps and kill remotes:** Close any phone apps that might be connected to the bed and remove batteries from remotes
3. **Move adapter closer:** If using a USB Bluetooth adapter, try moving it closer to the bed
4. **Use a Bluetooth proxy:** Consider using an ESPHome Bluetooth proxy placed near the bed
5. **Check Bluetooth adapter:** Verify your Bluetooth adapter is working with other devices

### "Connection timed out"

**Possible Causes:**
1. Weak Bluetooth signal
2. Interference from other devices
3. Bed controller is busy

**Solutions:**
1. **Reduce distance:** Move Bluetooth adapter or proxy closer to the bed
2. **Remove interference:** Move away from WiFi routers, microwaves, or other 2.4GHz devices
3. **Wait and retry:** Wait a minute and try again - the bed may have been processing a command

### Bed is discovered but won't connect

**Possible Causes:**
1. Physical remote is connected to the bed
2. Bed controller is not in pairing mode
3. Previous connection attempt left the bed in a bad state

**Solutions:**
1. **Put the bed in pairing mode:**
   - Remove the batteries from the physical remote (or move it out of Bluetooth range)
   - Unplug the bed from power
   - Wait 30 seconds
   - Plug the bed back in
   - Wait 15 seconds for the controller to initialize
   - Then add the bed in Home Assistant
2. **After successful setup:** The remote can be used normally again - this procedure is typically only needed for initial setup

### "Device not found"

**Possible Causes:**
1. Bed is not advertising BLE services
2. Wrong MAC address configured
3. Bed type not supported

**Solutions:**
1. **Verify BLE advertising:** Use a BLE scanner app to confirm the bed is visible
2. **Check MAC address:** Verify the MAC address matches what's shown in your BLE scanner
3. **Try manual configuration:** Use manual setup if auto-discovery doesn't find the bed

---

## Commands Not Working

### Bed doesn't respond to commands

**Possible Causes:**
1. Wrong protocol variant selected
2. Connection was silently dropped
3. Command format incompatible with your bed

**Solutions:**
1. **Try a different variant:** Go to integration options and try a different protocol variant
   - Keeson: Try "base" vs "ksbt"
   - Leggett & Platt: Try "gen2" vs "okin"
   - Richmat: Try "nordic" vs "wilinke"
2. **Reconnect:** Press the "Connect" button or restart the integration
3. **Check diagnostics:** Download diagnostics and verify the controller type matches your bed

### Some commands work, others don't

**Possible Causes:**
1. Feature not supported by your bed model
2. Wrong motor count configured
3. Massage not enabled in config

**Solutions:**
1. **Verify features:** Check if your bed actually has the feature (massage, lights, etc.)
2. **Update motor count:** Set correct number of motors in options (2, 3, or 4)
3. **Enable massage:** If bed has massage, enable it in integration options

### Commands are slow or delayed

**Possible Causes:**
1. Weak Bluetooth connection
2. Many commands queued
3. Bed controller processing

**Solutions:**
1. **Improve signal:** Move Bluetooth adapter/proxy closer to the bed
2. **Use stop button:** Press "Stop All" before sending new commands
3. **Wait between commands:** Allow a few seconds between commands

---

## Position Feedback Issues

### Position sensors show "Unknown" or don't update

**Possible Causes:**
1. Angle sensing is disabled (recommended setting)
2. Bed doesn't support position feedback
3. Notification subscription failed

**Solutions:**
1. **Check settings:** Position feedback is disabled by default to prevent remote conflicts
2. **Enable angle sensing:** If you want position data, disable "Disable angle sensing" in options
3. **Note:** Only Linak, Okimat, Reverie, and some Keeson/Ergomotion variants support position feedback

### Position values seem incorrect

**Possible Causes:**
1. Calibration differences between beds
2. Position data interpretation varies by model

**Solutions:**
1. **Use as relative indicators:** Position values are most useful for relative positioning
2. **Note:** Exact angles may vary between bed models

---

## Physical Remote Conflicts

### Physical remote stops working when HA is connected

**This is expected behavior.** Most BLE beds only support one connection at a time.

**Solutions:**
1. **Enable "Disable angle sensing":** This is the default and recommended setting
2. **Use HA controls:** Use Home Assistant instead of the physical remote
3. **Press "Disconnect" button:** Manually disconnect HA to use the physical remote
4. **Idle timeout:** HA automatically disconnects after 40 seconds of inactivity

### Remote works but bed doesn't respond to HA afterward

**Possible Causes:**
1. Remote took over the connection
2. Connection state is stale

**Solutions:**
1. **Press "Connect" button:** Force a reconnection from Home Assistant
2. **Restart integration:** Reload the integration from Settings > Integrations

---

## Protocol/Variant Issues

### Wrong bed type detected

**Possible Causes:**
1. Bed shares UUIDs with another type
2. OEM bed using different manufacturer's controller

**Solutions:**
1. **Manual configuration:** Remove and re-add the bed using manual setup
2. **Try different types:** If one type doesn't work, try related types (e.g., Okimat ↔ Leggett Okin)

### Keeson Variant Selection

| Symptom | Try This Variant |
|---------|------------------|
| Member's Mark, Purple, ErgoMotion beds | Base (BaseI4/BaseI5) |
| Older Keeson beds, Nordic UART | KSBT |
| Commands partially work | Try the other variant |

### Leggett & Platt Variant Selection

| Symptom | Try This Variant |
|---------|------------------|
| Most L&P beds, text-based commands | Gen2 |
| Pairing required, Okin remote | Okin |
| RGB lighting available | Gen2 (only one with RGB) |

### Richmat Variant Selection

| Symptom | Try This Variant |
|---------|------------------|
| Simple single-byte commands | Nordic |
| 5-byte commands with checksum | WiLinke |
| Auto-detect fails | Try Nordic first, then WiLinke |

### Motor Movement Issues

If motors move too briefly or movement is choppy, adjust **Motor Pulse Settings**:

| Symptom | Solution |
|---------|----------|
| Motors stop too soon | Increase pulse count |
| Movement is choppy | Decrease pulse delay |
| Commands get dropped | Increase pulse delay |

See [Motor Pulse Settings](CONFIGURATION.md#motor-pulse-settings) for default values by bed type.

---

## Pairing Required (Okimat/Leggett Okin)

Some beds require Bluetooth pairing before they can be controlled.

### How to Pair

1. **On Linux/Raspberry Pi:**
   ```bash
   bluetoothctl
   scan on
   # Find your bed's MAC address
   pair XX:XX:XX:XX:XX:XX
   trust XX:XX:XX:XX:XX:XX
   ```

2. **On Home Assistant OS:**
   - SSH into your Home Assistant OS and use `bluetoothctl` (same as Linux)
   - Note: ESPHome Bluetooth proxies don't support OS-level pairing - use a local Bluetooth adapter for beds that require pairing

3. **On Windows/macOS (for testing):**
   - Go to Bluetooth settings
   - Find the bed and click "Pair"

### Signs Pairing is Needed
- Connection succeeds but no commands work
- Bed specifically requires PIN entry or pairing confirmation
- "Pairing required" error message

**Note:** If discovery works but connection fails, first try the [pairing mode procedure](#bed-is-discovered-but-wont-connect) above. OS-level Bluetooth pairing is only needed for specific beds (Okimat, Leggett Okin).

---

## Classic Bluetooth Beds (Not Supported)

Some older beds use **Classic Bluetooth** instead of **Bluetooth Low Energy (BLE)**. This integration only supports BLE.

**Affected beds:**
- **OKIN-i** devices (name contains "OKIN-i") - Leggett & Platt Prodigy 2.0
- **OKIN CU258-4** controller - older Serta and Tempur beds

**Why not supported:** Classic Bluetooth and BLE are completely different technologies that happen to share a name. Home Assistant's `bluetooth` integration is BLE-only, ESPHome proxies don't support classic BT, and there are no plans to add support.

**Hardware fix:** Purchase a **BT40SA** or **BT01D** BLE dongle ($65-110 on eBay). Both use the standard DIN connector and are interchangeable - buy whichever is available. It plugs into the motor controller's DIN port and converts the bed to BLE.

---

## Quick Reference: Service UUIDs

Use these to identify your bed type in a BLE scanner:

| UUID | Bed Type(s) |
|------|-------------|
| `00001234-0000-1000-8000-00805f9b34fb` | Jensen JMC400 |
| `00001523-0000-1000-8000-00805f9b34fb` | DewertOkin |
| `0000aa5c-0000-1000-8000-00805f9b34fb` | Octo Star2 |
| `0000abcb-0000-1000-8000-00805f9b34fb` | Svane |
| `0000fee9-0000-1000-8000-00805f9b34fb` | BedTech, Richmat WiLinke (variant) |
| `0000ff12-0000-1000-8000-00805f9b34fb` | Comfort Motion / Jiecang |
| `0000ffb0-0000-1000-8000-00805f9b34fb` | Keeson Base (fallback) |
| `0000ffe0-0000-1000-8000-00805f9b34fb` | Solace, MotoSleep, Octo (standard) |
| `0000ffe5-0000-1000-8000-00805f9b34fb` | Keeson Base, Ergomotion, Malouf LEGACY_OKIN, OKIN FFE, Serta |
| `0000fff0-0000-1000-8000-00805f9b34fb` | Keeson Base (fallback), Richmat WiLinke (variant) |
| `01000001-0000-1000-8000-00805f9b34fb` | Malouf NEW_OKIN |
| `1b1d9641-b942-4da8-89cc-98e6a58fbd93` | Reverie |
| `45e25100-3171-4cfc-ae89-1d83cf8d8071` | Leggett & Platt Gen2 |
| `62741523-52f9-8864-b1ab-3b3a8d65950b` | Okimat, Leggett Okin, Nectar, OKIN 64-bit, Sleepy's BOX24 |
| `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | Richmat Nordic, Keeson KSBT, Mattress Firm 900 |
| `8ebd4f76-da9d-4b5a-a96e-8ebfbeb622e7` | Richmat WiLinke |
| `99fa0001-338a-1024-8a49-009c0215f78a` | Linak |
| `db801000-f324-29c3-38d1-85c0c2e86885` | Reverie Nightstand |

---

## Still Need Help?

If you've tried the troubleshooting steps above and still have issues, see the **[Getting Help Guide](GETTING_HELP.md)** for:

- How to generate a support report with all the info we need
- Filing a bug report on GitHub
- Requesting support for a new bed
- Capturing BLE protocol data for debugging
