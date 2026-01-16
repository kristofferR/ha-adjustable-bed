# Configuration Guide

This guide covers all configuration options available for the Adjustable Bed integration.

## Table of Contents

- [Accessing Configuration](#accessing-configuration)
- [Basic Settings](#basic-settings)
- [Advanced Settings](#advanced-settings)
- [Motor Pulse Settings](#motor-pulse-settings)
- [Protocol Variants](#protocol-variants)
- [Bed-Specific Settings](#bed-specific-settings)
- [Troubleshooting Tips](#troubleshooting-tips)

---

## Accessing Configuration

You can configure the integration in two places:

### Initial Setup

During initial setup, you'll configure basic options like bed type, motor count, and massage support.

### Options (After Setup)

To adjust settings after setup:

1. Go to **Settings** → **Devices & Services**
2. Find "Adjustable Bed" and click **Configure** (gear icon)
3. Adjust settings and click **Submit**

![Configuration options location](https://github.com/user-attachments/assets/8d6dc2b9-7df2-48dc-9ea5-61aaadce6c63)

---

## Basic Settings

| Setting | Options | Default | Description |
|---------|---------|---------|-------------|
| **Motor Count** | 2, 3, 4 | 2 | Number of controllable motor sections |
| **Has Massage** | On/Off | Off | Enable massage controls if your bed supports it |
| **Preferred Adapter** | Auto / Specific adapter | Auto | Which Bluetooth adapter or proxy to use |

### Motor Count Details

| Motors | Controllable Sections |
|--------|----------------------|
| 2 | Back + Legs |
| 3 | Head + Back + Legs |
| 4 | Head + Back + Legs + Feet |

**Tip:** Count the distinct moving sections when using your physical remote to determine the correct setting.

---

## Advanced Settings

| Setting | Range | Default | Description |
|---------|-------|---------|-------------|
| **Disable Angle Sensing** | On/Off | On | Disables position feedback to allow physical remote to work |
| **Position Mode** | Speed / Accuracy | Speed | How position updates after commands |
| **Disconnect After Command** | On/Off | Off | Disconnect immediately after each command |
| **Idle Disconnect Seconds** | 10-300 | 40 | Auto-disconnect timeout when idle |

### Setting Details

**Disable Angle Sensing** (Recommended: On)
- When enabled, the integration won't subscribe to position notifications
- This allows your physical remote to continue working alongside Home Assistant
- Only disable if you need position feedback and don't use a physical remote

**Position Mode**
- **Speed** (default): Faster button response, immediate UI feedback
- **Accuracy**: Reads actual position after each command, slightly slower

**Disconnect After Command**
- Enable for beds that only support one BLE connection at a time
- Frees up the connection immediately for your physical remote
- May cause slightly slower response on rapid consecutive commands

**Idle Disconnect Seconds**
- How long to wait before automatically disconnecting when idle
- Lower values free the connection faster for physical remotes
- Higher values reduce reconnection overhead for frequent Home Assistant use

---

## Motor Pulse Settings

These settings control how motor movement commands are sent. Adjusting them can help if motors move too briefly or commands are dropped.

| Setting | Range | Default | Description |
|---------|-------|---------|-------------|
| **Motor Pulse Count** | 1-100 | Bed-specific | Number of command repeats sent for motor movement |
| **Motor Pulse Delay (ms)** | 10-500 | Bed-specific | Delay between command pulses |

### Default Values by Bed Type

| Bed Type | Pulse Count | Pulse Delay |
|----------|-------------|-------------|
| Richmat | 30 | 50ms |
| Keeson | 25 | 200ms |
| All others | 25 | 50ms |

### When to Adjust

| Symptom | Solution |
|---------|----------|
| Motors stop moving too soon | Increase pulse count |
| Movement is choppy or jerky | Decrease pulse delay |
| Commands are getting dropped | Increase pulse delay |

---

## Protocol Variants

Some beds support multiple protocol variants. Auto-detection usually works, but you can override if needed.

### Keeson Variants

| Variant | Description | Use For |
|---------|-------------|---------|
| **Auto** | Auto-detect (recommended) | Most beds |
| **Base** | BaseI4/BaseI5 protocol | Member's Mark, Purple, some Ergomotion |
| **KSBT** | Nordic UART protocol | Older Keeson remotes |
| **Ergomotion** | Base protocol with position feedback | Ergomotion-branded beds |

### Leggett & Platt Variants

| Variant | Description | Use For |
|---------|-------------|---------|
| **Auto** | Auto-detect (recommended) | Most beds |
| **Gen2** | Richmat-based, ASCII commands | Most L&P beds, RGB lighting |
| **Okin** | Requires BLE pairing | Beds with Okin remotes |

### Richmat Variants

| Variant | Description | Use For |
|---------|-------------|---------|
| **Auto** | Auto-detect (recommended) | Most beds |
| **Nordic** | Single-byte commands | Simpler Richmat controllers |
| **WiLinke** | 5-byte commands with checksum | WiLinke-based controllers |

### Octo Variants

| Variant | Description | Use For |
|---------|-------------|---------|
| **Auto** | Auto-detect (recommended) | Most beds |
| **Standard** | Standard Octo protocol | Most Octo beds |
| **Star2** | Octo Remote Star2 | Star2 receivers |

### Okimat Variants

Okimat beds use different remote codes that determine available features and command values.

| Variant | Remote Model | Motors |
|---------|--------------|--------|
| **Auto** | Auto-detect (tries 82417 first) | Varies |
| **80608** | RFS ELLIPSE | Back, Legs |
| **82417** | RF TOPLINE | Back, Legs |
| **82418** | RF TOPLINE | Back, Legs, 2 Memory |
| **88875** | RF LITELINE | Back, Legs |
| **91244** | RF-FLASHLINE | Back, Legs |
| **93329** | RF TOPLINE | Head, Back, Legs, 4 Memory |
| **93332** | RF TOPLINE | Head, Back, Legs, Feet, 2 Memory |
| **94238** | RF FLASHLINE | Back, Legs, 2 Memory |

---

## Bed-Specific Settings

### Octo PIN

**Setting:** 4-digit PIN code

Some Octo beds require PIN authentication to maintain the BLE connection. The bed will disconnect after ~30 seconds without re-authentication.

- Find the PIN in your Octo remote's settings or documentation
- Leave empty if your bed doesn't require a PIN
- The integration automatically re-sends the PIN to maintain connection

### Richmat Remote

**Setting:** Remote model code

Richmat beds have different feature sets based on the remote model. Selecting your remote ensures only supported features are shown.

| Remote Code | Features |
|-------------|----------|
| **Auto** | All features enabled |
| **AZRN** | Head, Pillow, Feet |
| **BVRM** | Head, Feet, Massage |
| **VIRM** | Head, Feet, Pillow, Lumbar, Massage, Lights |
| **V1RM** | Head, Feet |
| **W6RM** | Head, Feet, Massage, Lights |
| **X1RM** | Head, Feet |
| **ZR10** | Head, Feet, Lights |
| **ZR60** | Head, Feet, Lights |
| **I7RM** | Head, Feet, Pillow, Lumbar, Massage, Lights |
| **190-0055** | Head, Pillow, Feet, Massage, Lights |

**Note:** The remote code is usually printed on the back of your physical remote.

---

## Troubleshooting Tips

### Physical Remote Stops Working

This is expected when Home Assistant is connected. Most beds only support one BLE connection.

**Solutions:**
1. Enable "Disable angle sensing" (recommended, on by default)
2. Reduce "Idle disconnect seconds" for faster automatic disconnection
3. Use the "Disconnect" button before using the physical remote

### Commands Are Slow or Unresponsive

1. Move your Bluetooth adapter or ESPHome proxy closer to the bed
2. Try a different protocol variant
3. Reduce interference from other 2.4GHz devices

### Motors Move Too Briefly

Increase the "Motor pulse count" setting. Start with +10 and test.

### Commands Are Being Dropped

Increase the "Motor pulse delay" setting. Try 100ms, then 150ms if needed.

### Wrong Features Showing

- **Richmat beds:** Select your specific remote code in options
- **Other beds:** Verify motor count matches your bed's actual motors
- **Massage not showing:** Enable "Has massage" in options

---

## Next Steps

- **Having connection issues?** See [Troubleshooting](TROUBLESHOOTING.md)
- **Want to learn about your bed's protocol?** See [Supported Actuators](SUPPORTED_ACTUATORS.md)
- **Setting up Bluetooth?** See [Connection Guide](CONNECTION_GUIDE.md)
