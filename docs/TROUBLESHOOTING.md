# Troubleshooting Guide

This guide covers common issues and their solutions when using the Adjustable Bed integration.

## Table of Contents

- [Connection Issues](#connection-issues)
- [Commands Not Working](#commands-not-working)
- [Position Feedback Issues](#position-feedback-issues)
- [Physical Remote Conflicts](#physical-remote-conflicts)
- [Protocol/Variant Issues](#protocolvariant-issues)
- [Getting Help](#getting-help)

---

## Connection Issues

### "Failed to connect to bed"

**Possible Causes:**
1. Bed is powered off or in standby mode
2. Another device is already connected (phone app, another HA instance)
3. Bed is out of Bluetooth range
4. Bluetooth adapter issues

**Solutions:**
1. **Power cycle the bed:** Unplug the bed's power for 30 seconds, then plug it back in
2. **Close other apps:** Close any phone apps that might be connected to the bed
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
3. **Note:** Most beds except Linak don't support position feedback

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
   - Use the Bluetooth adapter's built-in pairing (if supported)
   - Or pair from another device first, then transfer

3. **On Windows/macOS (for testing):**
   - Go to Bluetooth settings
   - Find the bed and click "Pair"

### Signs Pairing is Needed
- Connection succeeds but no commands work
- Bed shows in BLE scan but won't connect
- "Pairing required" error message

---

## Getting Help

### Quick Method: Generate Support Report

The easiest way to collect all the information needed for a bug report:

1. **Go to Developer Tools → Services** in Home Assistant
2. **Search for** `adjustable_bed.generate_support_report`
3. **Select your bed device** and click "Call Service"
4. **A notification will appear** with the file location (in your `/config/` folder)
5. **Attach this file** to your GitHub issue

The support report includes:
- System info (HA version, Python version)
- Integration configuration
- Connection status and BLE info
- Recent logs (if available)
- All sensitive data (MAC address) is automatically redacted

### Manual Method: Download Diagnostics

If you prefer to gather information manually:

1. **Download diagnostics:**
   - Settings → Integrations → Adjustable Bed → ⋮ → Download diagnostics
   - This includes config and connection info (MAC address is redacted)

2. **Check logs:** Look at Home Assistant logs for error messages
   - Settings → System → Logs → Filter by "adjustable_bed"
   - **Tip:** If your bed isn't responding, the integration will log all discovered GATT services at INFO level.

3. **Enable debug logging** for detailed information:

   ```yaml
   logger:
     logs:
       custom_components.adjustable_bed: debug
   ```

4. **Test with BLE scanner:**
   - Use an app like "nRF Connect" to verify your bed is advertising
   - Note the service UUIDs - these help identify the correct bed type

### Submitting a Bug Report

1. **Go to:** [GitHub Issues - Bug Report](https://github.com/kristofferR/ha-adjustable-bed/issues/new?template=bug-report.yml)

2. **Fill out the form** with:
   - Description of the problem
   - Steps to reproduce
   - Your bed type and HA version

3. **Attach the diagnostics file** (from either method above)

4. **Include relevant log entries** if you have them

### Where to Get Help

- **Bug Reports:** [GitHub Issues](https://github.com/kristofferR/ha-adjustable-bed/issues/new?template=bug-report.yml)
- **New Bed Requests:** [Request New Bed Support](https://github.com/kristofferR/ha-adjustable-bed/issues/new?template=new-bed-support.yml)
- **Home Assistant Community:** Search for "adjustable bed" discussions

---

## Quick Reference: Service UUIDs

Use these to identify your bed type in a BLE scanner:

| UUID | Bed Type |
|------|----------|
| `99fa0001-338a-1024-8a49-009c0215f78a` | Linak |
| `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | Richmat Nordic / Keeson KSBT |
| `0000ffe5-0000-1000-8000-00805f9b34fb` | Keeson Base / Ergomotion |
| `0000fff0-0000-1000-8000-00805f9b34fb` | Keeson Base (fallback 1) |
| `0000ffb0-0000-1000-8000-00805f9b34fb` | Keeson Base (fallback 2) |
| `0000ffe0-0000-1000-8000-00805f9b34fb` | Solace / MotoSleep |
| `45e25100-3171-4cfc-ae89-1d83cf8d8071` | Leggett & Platt Gen2 |
| `62741523-52f9-8864-b1ab-3b3a8d65950b` | Okimat / Leggett Okin |
| `1b1d9641-b942-4da8-89cc-98e6a58fbd93` | Reverie |
| `8ebd4f76-da9d-4b5a-a96e-8ebfbeb622e7` | Richmat WiLinke |
