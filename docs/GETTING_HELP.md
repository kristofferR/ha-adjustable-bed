# Getting Help

Need help with the Adjustable Bed integration? This guide explains how to get support and what information we'll need.

## Quick Links

| I need to... | Go here |
|--------------|---------|
| Get help with setup | [Ask a Question](https://github.com/kristofferR/ha-adjustable-bed/discussions/new?category=q-a) |
| Report a bug | [Bug Report](https://github.com/kristofferR/ha-adjustable-bed/issues/new?template=bug-report.yml) |
| Request support for a new bed | [New Bed Support Request](https://github.com/kristofferR/ha-adjustable-bed/issues/new?template=new-bed-support.yml) |
| Suggest a feature | [Ideas & Suggestions](https://github.com/kristofferR/ha-adjustable-bed/discussions/new?category=ideas) |
| Fix a common issue | [Troubleshooting Guide](TROUBLESHOOTING.md) |
| Set up Bluetooth | [Connection Guide](CONNECTION_GUIDE.md) |
| Find my bed's actuator brand | [Supported Actuators](SUPPORTED_ACTUATORS.md) |

---

## Need Help with Setup?

For setup questions, configuration help, or general "how do I..." questions, the best place to ask is the **[Q&A Discussions](https://github.com/kristofferR/ha-adjustable-bed/discussions/new?category=q-a)**. The community can help with:

- Identifying which bed type or actuator brand to select
- Bluetooth connection and pairing issues
- ESPHome proxy configuration
- Automations and scripts using the integration
- General Home Assistant integration questions

**Tip:** Search [existing discussions](https://github.com/kristofferR/ha-adjustable-bed/discussions) first - someone may have already answered your question!

---

## Before Opening an Issue

Please check these resources first:

1. **[Troubleshooting Guide](TROUBLESHOOTING.md)** - Covers most common issues with connection, commands, and position feedback
2. **[Supported Actuators](SUPPORTED_ACTUATORS.md)** - Your bed might already be supported under a different actuator brand
3. **[Existing Issues](https://github.com/kristofferR/ha-adjustable-bed/issues)** - Someone may have already reported the same issue

---

## Reporting a Bug

If you've found a bug, please file a [Bug Report](https://github.com/kristofferR/ha-adjustable-bed/issues/new?template=bug-report.yml). To help us fix the issue quickly, you'll need to provide:

### Required Information

- **Description** of the problem and expected behavior
- **Steps to reproduce** the issue
- **Bed type** configured in the integration
- **Home Assistant version**
- **Connection method** (built-in Bluetooth, USB adapter, or ESPHome proxy)
- **Diagnostics file** (see below)

### Generating a Support Report (Recommended)

The support report includes everything we need in one file:

1. Go to **Developer Tools** → **Actions**
2. Search for `adjustable_bed.generate_support_report`
3. Select your bed device and click **Perform action**
4. A notification will show the file location (in your `/config/` folder)
5. Attach the JSON file to your GitHub issue

The support report includes:
- System info (HA version, Python version, platform)
- Integration configuration and detected bed type
- Connection status and BLE adapter info
- Recent error logs

**Privacy note:** MAC addresses are partially redacted (manufacturer prefix kept), PINs and names are masked.

### Alternative: Download Diagnostics

If you prefer to gather information separately:

1. Go to **Settings** → **Integrations** → **Adjustable Bed**
2. Click the **⋮** menu → **Download diagnostics**
3. Attach the downloaded JSON file to your issue

### Debug Logging

1. Go to **Settings** → **Devices & Services** → **Adjustable Bed**
2. Click the **⋮** menu → **Enable debug logging**
3. Reproduce the issue (use the bed controls, trigger the problem)
4. Return to the same menu → **Disable debug logging**
5. Your browser will automatically download the log file

This captures only the relevant logs for this integration, making it easier to diagnose issues.

---

## Requesting Support for a New Bed

If your bed isn't supported yet, file a [New Bed Support Request](https://github.com/kristofferR/ha-adjustable-bed/issues/new?template=new-bed-support.yml). We'll need:

### Required Information

- **Bed manufacturer and model** (e.g., "Tempur-Pedic Ergo Extend")
- **Bluetooth device name** shown when adding the device
- **BLE Service UUIDs** from diagnostics output

### How to Find BLE Information

The easiest way is to use the integration's built-in tools:

1. **Add the device in Diagnostic mode**: Settings → Integrations → Add Integration → Adjustable Bed → Manual entry → Select "Diagnostic/Unknown" as bed type
2. **Run diagnostics**: Developer Tools → Actions → `adjustable_bed.run_diagnostics` → Select your device
3. **Check the output file** in your `/config/` folder for service UUIDs and device info

If your bed doesn't appear in Home Assistant at all (not visible to any Bluetooth adapter), use [nRF Connect](https://www.nordicsemi.com/Products/Development-tools/nRF-Connect-for-mobile) on your phone to verify the device exists and is advertising.

### Helpful Additional Info

- Remote control model number (check the back of the remote)
- Photos of the remote and controller box
- Name of the official mobile app (if any)
- Whether the app requires cloud login or works locally
- Available features (massage, lights, memory presets)

### Testing Availability

Let us know if you can:
- Test beta implementations on your bed
- Capture BLE traffic from the official app (see [Capturing App Traffic](#capturing-app-traffic-for-new-bed-support) below)

---

## Which Diagnostic Tool Should I Use?

| Scenario | Recommended Tool |
|----------|------------------|
| Troubleshooting a configured bed | Support report or diagnostics download |
| Finding your bed's MAC address | Integration shows discovered MACs when manually adding |
| Identifying bed type/service UUIDs | `run_diagnostics` in Diagnostic mode |
| New bed support - capture what app sends | nRF Connect logging (see below) |
| Device not visible to HA at all | nRF Connect to verify it exists |

---

## Capturing BLE Data for Troubleshooting

For most troubleshooting, the **built-in diagnostics** provide everything needed:

### Using run_diagnostics Action

The `run_diagnostics` action captures GATT structure, device info, and notifications from your bed:

1. Go to **Developer Tools** → **Actions**
2. Search for `adjustable_bed.run_diagnostics`
3. Select your bed device (or enter a MAC address for unconfigured devices)
4. Click **Perform action**
5. Optionally operate your physical remote during capture to record notifications
6. Find the JSON report in your `/config/` folder

This captures:
- All GATT services and characteristics
- Device name and advertising data
- Notifications sent BY the device (e.g., position updates)

**Limitation:** This captures what the device *sends*, not commands sent *to* the device. For capturing outgoing commands from an app, see [Capturing App Traffic](#capturing-app-traffic-for-new-bed-support).

---

## Capturing App Traffic for New Bed Support

When requesting support for a new bed, capturing what the official app sends to your bed is valuable. This data helps reverse-engineer the command protocol.

### Using nRF Connect (Recommended)

[nRF Connect](https://www.nordicsemi.com/Products/Development-tools/nRF-Connect-for-mobile) can log all BLE traffic while you use the official app:

1. Install nRF Connect on your phone
2. Enable **Log** in nRF Connect settings
3. Connect to your bed in nRF Connect
4. Open the official bed app on another device (or disconnect from nRF Connect first)
5. Use the app to control the bed - move motors, activate presets, etc.
6. Export the log and attach it to your GitHub issue

The log shows the exact bytes the app sends for each command, which is essential for implementing new protocols.

### Using Android BLE HCI Snoop (Advanced)

For more detailed captures:

1. Enable **Developer options** on your Android device
2. Enable **Bluetooth HCI snoop log**
3. Use the official app to control the bed
4. Extract the log file (location varies by Android version)
5. Open in Wireshark and filter by your bed's MAC address

---

## What Happens Next

After you submit an issue:

1. **We'll review it** - Usually within a few days
2. **We may ask for more info** - Check back for follow-up questions
3. **For bugs** - We'll try to reproduce and fix the issue
4. **For new beds** - We'll analyze the protocol and may ask you to test

**Note:** This is a community-maintained integration. Response times vary based on contributor availability.