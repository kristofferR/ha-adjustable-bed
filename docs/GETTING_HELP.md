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

1. Go to **Developer Tools** → **Services**
2. Search for `adjustable_bed.generate_support_report`
3. Select your bed device and click **Call Service**
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
- **Bluetooth device name** shown in a BLE scanner app
- **BLE Service UUIDs** from the device

### How to Find BLE Information

1. **Install a BLE scanner app** like [nRF Connect](https://www.nordicsemi.com/Products/Development-tools/nRF-Connect-for-mobile) (iOS/Android)
2. **Scan for devices** - look for names containing your bed brand, "Desk", "HHC", "Base", etc.
3. **Connect to the device** and note the Service UUIDs
4. **Check the advertising data** for manufacturer-specific data

### Helpful Additional Info

- Remote control model number (check the back of the remote)
- Photos of the remote and controller box
- Name of the official mobile app (if any)
- Whether the app requires cloud login or works locally
- Available features (massage, lights, memory presets)

### Testing Availability

Let us know if you can:
- Test beta implementations on your bed
- Capture BLE traffic from the official app using tools like nRF Connect, Wireshark, or Android BLE debugging

---

## Getting BLE Protocol Data

For new bed support or complex debugging, capturing BLE traffic helps significantly.

### Using nRF Connect

1. Enable "Log" in nRF Connect settings
2. Connect to your bed
3. Use the official app to control the bed
4. Export the log and attach it to your issue

### Using Android BLE HCI Snoop

1. Enable **Developer options** on your Android device
2. Enable **Bluetooth HCI snoop log**
3. Use the official app to control the bed
4. Extract the log file and convert with Wireshark

### Using Diagnostic Mode

If your bed isn't recognized, try adding it in **Diagnostic mode**:

1. Add the bed manually and select "Diagnostic/Unknown" as the bed type
2. Call the `adjustable_bed.run_diagnostics` service
3. This captures raw BLE data that can help identify the protocol

---

## What Happens Next

After you submit an issue:

1. **We'll review it** - Usually within a few days
2. **We may ask for more info** - Check back for follow-up questions
3. **For bugs** - We'll try to reproduce and fix the issue
4. **For new beds** - We'll analyze the protocol and may ask you to test

**Note:** This is a community-maintained integration. Response times vary based on contributor availability.