# Getting Help

Need help with the Adjustable Bed integration? This guide explains how to get support and what information we'll need.

> **For bugs and bed compatibility reports, include a support bundle if possible.** It includes your configuration, BLE details, connection state, and recent logs. If capture fails, describe what happened and submit the report anyway. Feature requests and general questions do not require a bundle.

## Quick Links

| I need to... | Go here |
|--------------|---------|
| Get help with setup | [Ask a Question](https://github.com/kristofferR/ha-adjustable-bed/discussions/new?category=help-questions) |
| Report a bug | [Bug Report](https://github.com/kristofferR/ha-adjustable-bed/issues/new?template=bug-report.yml) |
| Request support for a new bed | [New Bed Support Request](https://github.com/kristofferR/ha-adjustable-bed/issues/new?template=new-bed-support.yml) |
| Suggest a feature | [Feature Request](https://github.com/kristofferR/ha-adjustable-bed/issues/new?template=feature-request.yml) |
| Fix a common issue | [Troubleshooting Guide](TROUBLESHOOTING.md) |
| Set up Bluetooth | [Connection Guide](CONNECTION_GUIDE.md) |
| Find my bed's actuator brand | [Supported Actuators](SUPPORTED_ACTUATORS.md) |

---

## Need Help with Setup?

For configuration help or general "how do I..." questions, ask in **[Help & questions](https://github.com/kristofferR/ha-adjustable-bed/discussions/new?category=help-questions)**. The community can help with:

- Identifying which bed type or actuator brand to select
- Choosing a Bluetooth adapter or proxy
- ESPHome proxy configuration
- Automations and scripts using the integration
- General Home Assistant integration questions

**Tip:** Search [existing discussions](https://github.com/kristofferR/ha-adjustable-bed/discussions) first - someone may have already answered your question!

If connection, pairing, or controls fail, use a [Bug Report](https://github.com/kristofferR/ha-adjustable-bed/issues/new?template=bug-report.yml).
You do not need to know whether the cause is configuration or a software bug.

## Requesting a Feature

Use the [Feature Request](https://github.com/kristofferR/ha-adjustable-bed/issues/new?template=feature-request.yml)
form for missing controls, card improvements, and automation capabilities. Describe
what you want to do and any current workaround. A request does not need a technical
design or a support bundle to be tracked.

## How Reports Are Handled

Issues are the tracking queue for bugs, features, and bed compatibility. Discussions
are for help, shared dashboards and automations, experiences, and announcements.

If a discussion reveals work to do, a maintainer creates or links an issue,
preserving the report and diagnostic links. You do not need to submit it again.
Follow the linked issue for progress; a closed discussion does not mean the bug
was fixed or the feature shipped.

- **Answered:** a help question has a useful answer. Follow-up questions remain welcome.
- **Closed:** the topic is completed, declined, duplicated, or handed off to a linked issue. The thread should explain which.
- **Locked:** reserved for moderation or deliberately read-only announcements.
- **Waiting for information:** an issue remains open with the `needs-info` label and a specific request for the missing details. Asking for a bundle is not an answer or a fix.

We do not close reports just because they are old. An accepted answer should be
updated if later replies show it is wrong or the problem has returned.

---

## Before Opening an Issue

Please check these resources first:

1. **[Troubleshooting Guide](TROUBLESHOOTING.md)** - Covers most common issues with connection, commands, and position feedback
2. **[Supported Actuators](SUPPORTED_ACTUATORS.md)** - Your bed might already be supported under a different actuator brand
3. **[Existing Issues](https://github.com/kristofferR/ha-adjustable-bed/issues)** - Someone may have already reported the same issue

---

## Reporting a Bug

If you've found a bug, please file a [Bug Report](https://github.com/kristofferR/ha-adjustable-bed/issues/new?template=bug-report.yml).

Generate a support bundle if possible, then fill in the issue template with the
problem, steps to reproduce, and any other context. If capture fails, describe the
failure instead so the report can still be tracked.

For v4, include the exact beta version, Home Assistant version, whether this was
a v3 upgrade, and whether the bed is standalone or combined. For a combined bed,
name the affected side and whether the action targeted the parent or a child.

### Generating a Support Bundle

The support bundle includes everything we need in one file:

1. Go to **Developer Tools** → **Actions**
2. Search for `adjustable_bed.generate_support_bundle`
3. For a control problem, first try the failing Home Assistant command so it is present in the command trace.
4. Select that same bed device, or leave the device empty and enter `target_address` for an unconfigured device, then click **Perform action**.
5. (Optional) Adjust `capture_duration` to change how long notifications are captured (default: 120 seconds). Operate the physical remote during capture to generate useful traffic.
6. A notification will appear with a **download link** — click it to save the file.
7. Attach the JSON file to your GitHub issue. Check its `evidence.warnings` section for anything that could not be captured.

For a **two-address combined bed**, select the affected Left or Right child
device; the parent alone is ambiguous for a support capture. Generate one bundle
per side when both are involved. A single-address parent resolves to its shared
physical controller. The support action has no `side` field.

The support bundle includes:
- System info (HA version, Python version, platform)
- Integration configuration and detected bed type
- Connection status, BLE adapter/proxy health, and connection attempt details
- ESPHome proxy firmware, API version, pairing capability, availability, and free BLE connection slots when Home Assistant exposes them
- Live Bluetooth logs from ESPHome proxies that can see the bed, when their API and firmware logging settings allow capture
- BLE advertisements by source, detection reasoning, and GATT/descriptor details
- Up to 30 ranked nearby BLE devices, including their names and addresses
- A structured pairing assessment that detects stale saved bond state and adapter mismatches
- Captured notifications and buffered command trace
- Up to 500 recent in-memory integration/Bluetooth log entries from before capture and 500 from its end, including debug logs collected automatically during capture, plus evidence warnings when logs or a command reproduction are missing

Log capture works without a `home-assistant.log` file. Recent records are retained
from integration setup at the configured log levels; debug logging is enabled
temporarily during capture. For detailed logs of a failure before capture, enable
debug logging before reproducing it. Proxy logs cover the capture window only,
use a separate temporary API connection, and preserve the proxy's existing Home
Assistant connection. Unavailable, interrupted, or empty proxy captures are marked
in `bluetooth.proxy_logs`. Firmware that excludes debug messages cannot provide
them without a firmware configuration change. Set `include_logs: false` to omit
both HA and proxy logs.

**Privacy note:** PINs are redacted. MAC addresses, device names, and other BLE identifiers are preserved since they are essential for debugging.

Review the bundle before posting it publicly. The download link is usable for up
to one hour and expires on restart; the JSON file remains in the HA configuration
directory. See [download-link details](TROUBLESHOOTING.md#support-bundle-download-links).

### Alternative: Download Diagnostics

If you prefer to gather information separately:

1. Go to **Settings** → **Devices & Services** → **Adjustable Bed**
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

If your bed isn't supported yet, file a [New Bed Support Request](https://github.com/kristofferR/ha-adjustable-bed/issues/new?template=new-bed-support.yml).

Start by generating a support bundle if possible. It captures BLE details needed
to investigate compatibility. If capture fails, include the bed model, official
app, and capture error so we can track the request and identify what is missing.

You don't need to configure anything first — the support bundle action works directly on any BLE device your Home Assistant can see:

1. **Find your bed's MAC address:** go to **Settings** → **Devices & Services** → **Add Integration** → **Adjustable Bed**, choose **"Browse unsupported BLE devices"**, and select your bed from the list (or pick **"Enter address manually"** if you already know the address). The wizard shows the device's MAC address and scanner details — note the address. This step only inspects the device; it doesn't add anything.
2. Go to **Developer Tools** → **Actions** → `adjustable_bed.generate_support_bundle`
3. Leave the **Device** field empty and enter the MAC address in **Target Address**
4. Click **Perform action**, then operate your physical remote during the capture (120 seconds by default) so the bundle records useful traffic
5. A notification will appear with a **download link** — click it to save the file. The same JSON file is also written to your Home Assistant config folder as `adjustable_bed_support_bundle_*.json`.
6. Attach the JSON file to your issue

**Alternative — add the bed as a diagnostic device:** if you'd rather have a persistent entry (for example, to re-run captures easily), open the same wizard, choose **"Show all BLE devices"**, select your bed, and set **Bed type** to **"Diagnostic (unknown bed)"**. You can then run `generate_support_bundle` with that device selected in the **Device** field. "Diagnostic (unknown bed)" appears in every bed type dropdown, including the confirm dialog for an auto-detected bed; only the "Select by actuator brand" list does not offer it.

Then fill in the rest of the template with your bed manufacturer/model, remote model number, and any other details.

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
| Troubleshooting a configured bed | Support bundle or diagnostics download |
| Finding your bed's MAC address | **"Browse unsupported BLE devices"** in the add-integration wizard |
| Identifying bed type/service UUIDs | `generate_support_bundle` with `target_address` |
| New bed support - capture what app sends | Android Bluetooth HCI snoop log (see below) |
| Device not visible to HA at all | nRF Connect to verify it exists |

---

## Capturing BLE Data for Troubleshooting

For most troubleshooting, the **built-in diagnostics** provide everything needed:

### Using generate_support_bundle Action

The `generate_support_bundle` action captures GATT structure, device info, scanner state, and notifications from your bed:

1. Go to **Developer Tools** → **Actions**
2. Search for `adjustable_bed.generate_support_bundle`
3. Try the failing Home Assistant control once if you are troubleshooting commands.
4. Select that same bed device, or leave the device empty and enter `target_address` for an unconfigured device (provide exactly one of the two).
5. Click **Perform action**.
6. Optionally operate your physical remote during capture to record notifications.
7. A notification will appear with a **download link**; the JSON report is also saved in your Home Assistant config folder as `adjustable_bed_support_bundle_*.json`.

This captures:
- All GATT services and characteristics
- Device name and advertising data
- Notifications sent BY the device (e.g., position updates)
- Commands recently sent by this integration
- Adapter and ESPHome Bluetooth proxy health
- Pairing/authentication evidence and a completeness summary

**Limitation:** The command trace contains commands sent by this integration, not commands sent by the official mobile app. For capturing outgoing commands from an app, see [Capturing App Traffic](#capturing-app-traffic-for-new-bed-support).

---

## Capturing App Traffic for New Bed Support

When requesting support for a new bed, capturing what the official app sends to your bed is valuable. This data helps reverse-engineer the command protocol.

### Using Android Bluetooth HCI Snoop

Capture on the Android phone running the official bed app:

1. Enable **Developer options** and **Bluetooth HCI snoop log**.
2. Restart Bluetooth so logging takes effect, then connect with the official app.
3. Reproduce a short sequence and note the time and button used for each action.
4. Export the Bluetooth snoop log or extract it from an Android bug report. Availability and location vary by device; follow [Android's Bluetooth debugging instructions](https://source.android.com/docs/core/connect/bluetooth/verifying_debugging).
5. Disable snoop logging afterward. Share the relevant Bluetooth capture and action notes, rather than publishing the entire phone bug report.

### Using nRF Connect for Device Inspection

[nRF Connect](https://www.nordicsemi.com/Products/Development-tools/nRF-Connect-for-mobile)
scans advertisements, discovers services and characteristics, and logs its own
reads, writes, and received notifications. It does **not** capture another app's
outgoing commands. Its logs are useful for GATT inspection and notifications;
disconnect it before using the official app on a bed that accepts one BLE link.

---

## What Happens Next

After you submit an issue:

1. **We'll triage it** - Check for an existing issue and identify the next step
2. **We may ask for more info** - The issue stays open with `needs-info` while details are missing
3. **For bugs** - We'll try to reproduce and fix the issue
4. **For new beds** - We'll analyze the protocol and may ask you to test
5. **For features** - We'll assess the scope and record whether the request is planned or declined

**Note:** This is a community-maintained integration. Response times vary based on contributor availability.
