# Troubleshooting Guide

This guide covers common issues and their solutions when using the Adjustable Bed integration.

## Table of Contents

- [Connection Issues](#connection-issues)
- [Dashboard Card Missing or Configuration Error](#dashboard-card-missing-or-configuration-error)
- [Commands Not Working](#commands-not-working)
- [Position Feedback Issues](#position-feedback-issues)
- [Physical Remote Conflicts](#physical-remote-conflicts)
- [Protocol/Variant Issues](#protocolvariant-issues)
- [Pairing Required Beds](#pairing-required-beds)
- [Classic Bluetooth Beds (Not Supported)](#classic-bluetooth-beds-not-supported)
- [Quick Reference: Service UUIDs](#quick-reference-service-uuids)
- [Debugging Tools](#debugging-tools)
- [Still Need Help?](#still-need-help)

---

## Dashboard Card Missing or Configuration Error

If the card is missing from the picker or says **Custom element doesn't exist:
adjustable-bed-card**, its JavaScript has not loaded. This is separate from an
unavailable bed or Bluetooth proxy, which should leave the card visible.

The integration automatically registers this **JavaScript module** resource:

```text
/adjustable_bed_frontend/adjustable-bed-card.js
```

This permanent URL is a small, uncached loader for the current versioned bundle.
It stays the same across integration updates. Previously registered versioned
URLs also load the current bundle if the old version is no longer installed.
Storage-mode setup consolidates old card resources into the permanent URL.
If you manage resources in YAML, you can explicitly add it under your existing
`lovelace:` configuration:

```yaml
lovelace:
  resources:
    - url: /adjustable_bed_frontend/adjustable-bed-card.js
      type: module
```

After updating the integration and restarting Home Assistant, reload the page
or fully close and reopen the Companion app. A page already running JavaScript
from an older version cannot replace its registered custom element in place.

If the problem persists:

1. Open the permanent URL on the **same Home Assistant address** used by the
   failing browser/app. It should return an `import` statement. Open the path in
   that statement too; it should return JavaScript, not a login page or a 404.
2. Check **Settings → Dashboards → Resources** (enable Advanced mode in your
   profile if needed). There should be one Adjustable Bed resource using the
   permanent URL above, with type **JavaScript module**.
3. Check **Settings → System → Logs** and the browser console. In particular,
   loading both Mushroom and Mushroom Better Sliders causes duplicate
   `mushroom-select` registration errors. The [Better Sliders author explicitly
   requires disabling the original Mushroom](https://github.com/RubenKremer/lovelace-mushroom-better-sliders#what-is-mushroom-better-sliders).
   Keep only the variant you use. This conflict is distinct from a failed
   Adjustable Bed module request.
4. If an old failed response is still cached, reset the Companion app's frontend
   cache once after correcting the resource. Repeated cache resets are not a
   lasting fix for a missing URL or a JavaScript exception.

When reporting a remaining failure, include the expanded configuration error,
Home Assistant and Companion app versions, resource URL, and any failed module
request's HTTP status or console exception. A BLE support bundle alone cannot
show why browser JavaScript failed to load.

### Related upstream reports

- [Home Assistant frontend #52570](https://github.com/home-assistant/frontend/issues/52570)
  documents custom-module loading races, especially panel views and custom
  dashboard strategies. Resource registration alone does not guarantee that
  every dashboard waits for the module.
- [Home Assistant core #181190](https://github.com/home-assistant/core/issues/181190)
  reports long-lived cached 404 responses in its static-file handler on
  2026.9.0. This is relevant when investigating a failed request, but does not
  establish the cause of earlier failures on 2026.8.2.

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
3. **Try manual configuration:** If auto-discovery doesn't find the bed, use **Settings** → **Devices & Services** → **Add Integration** → **Adjustable Bed** and choose **"Select by actuator brand"** or **"Show all BLE devices"**

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
2. **Update motor count:** Set the correct number of motors in options (2, 3, or 4; use 1 only for a one-motor Standard OCTO lift, with `RTV` detected automatically)
3. **Enable massage:** If bed has massage, enable it in integration options

### Commands are slow or delayed

**Possible Causes:**
1. Weak Bluetooth connection
2. Many commands queued
3. Bed controller processing

**Solutions:**
1. **Improve signal:** Move Bluetooth adapter/proxy closer to the bed
2. **Compare connected and cold commands:** A cold connection may need authentication and several proxy attempts. With Disconnect After Command enabled, commands within the one-second handoff window reuse the link.
3. **Use Stop All when movement must end:** STOP invalidates queued movement and interrupts active movement and position reads. A replacement movement for the same motor supersedes the older request; independent motor commands are serialized.
4. **Inspect connection diagnostics:** Repeated failures on the strongest proxy can delay access to a working alternative. Multiple paths receive a bounded extra retry budget; this cannot repair an unusable proxy or an unreachable bed.

Timed Move uses the requested elapsed movement limit. Connection preparation and
STOP cleanup can add to the service's total duration, but slow writes no longer
multiply the movement duration. A controller may finish earlier. Failed writes
and failed cleanup are still reported.

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

### BLE connection shows "Disconnected" shortly after adding the bed

**This is normal.** For most beds the integration deliberately drops the BLE
link after about 40 seconds of inactivity (the `idle_disconnect_seconds`
option) so the physical remote can take over. It reconnects automatically on
the next command from Home Assistant — no action is needed.

- The connection sensor reports `state_detail: idle` (and a `disconnect_reason`
  attribute) while it's intentionally disconnected, and the Lovelace card shows
  an "Idle — reconnects on demand" Bluetooth icon rather than an error.
- Routine idle disconnects and on-demand reconnects are logged at debug level,
  so they no longer fill the log. Enable debug logging if you need to see them.

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
1. **Manual configuration:** Remove and re-add the bed, choosing the bed type yourself via **"Select by actuator brand"** or **"Show all BLE devices"** instead of accepting the auto-detected type
2. **Try different types:** If one type doesn't work, try related types (e.g., Okimat ↔ Leggett Okin)

### Keeson Variant Selection

| Symptom | Try This Variant |
|---------|------------------|
| Member's Mark, Purple, ErgoMotion BaseI4/BaseI5 beds | Base (BaseI4/BaseI5) |
| Older Keeson beds or `KSBT03*` / `KSBT04*` Nordic UART beds | KSBT |
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

## Pairing Required Beds

Some beds (Okimat / OKIN, Okin CST, Leggett & Platt Okin variant, Logicdata, Vibradorm, Sleep Number Climate 360 / FlexFit Fuzion) require an OS-level Bluetooth **bond** before they can be controlled. The integration requests pairing automatically; the steps below are for putting the bed into pairing mode and recovering when a bond fails.

### Putting the bed in pairing mode

- **OKIN bases (Okimat, Okin CST, Nectar / Mattress Firm 900-O / Rize MF900, etc.):** Power-cycle the control box — **unplug it for ~30 seconds, then plug it back in**. The status light blinks blue, then turns green after ~20 seconds. That window is when the base accepts a new Bluetooth bond. Some models instead use the under-bed **lamp/light button** (hold until it blinks blue). There is **no dedicated Bluetooth pairing button** — any "Pair"/"Learn" button on the control box only syncs the RF remote, not Bluetooth.
- **Sleep Number Climate 360 / FlexFit Fuzion:** hold the side pairing button until the blue light blinks. (Older Sleep Number BAM/MCR i8 / 360 FlexFit 2 beds do **not** need OS-level pairing.)

### How the integration pairs

The integration connects with pairing enabled and, for OKIN-style beds, verifies the bond afterward by reading an encrypted characteristic. If the link connected but never bonded, it clears its cached bond state and re-pairs on the next attempt, and raises a **"Bluetooth pairing required"** repair with a **Fix** button that walks you through the power-cycle + pair.

**Bluetooth adapter notes:**
- ESPHome Bluetooth proxies **do** support OS-level pairing, but only on **ESPHome 2024.3.0 or newer**. Pairing over a proxy can be unreliable; if it keeps failing, put the bed in range of a **local Bluetooth adapter** (or the HA host's own adapter) for the initial bond.
- You can also pair manually from the device running HA's Bluetooth stack — **not your phone**:
  - **Linux / Raspberry Pi / HA OS (SSH):** `bluetoothctl` → `scan on` → `pair XX:XX:XX:XX:XX:XX` → `trust XX:XX:XX:XX:XX:XX`
  - **Windows / macOS (for testing):** Bluetooth settings → find the bed → "Pair"

### Which side stores the bond

A Bluetooth bond belongs to whichever transport created it. A bond made through
an adapter on the Home Assistant host lives in that host's BlueZ. A bond made
through an ESPHome proxy lives on the proxy, where Home Assistant can neither
read nor remove it. They are separate: pairing through one does nothing for the
other, and moving a bed to a different proxy means pairing again.

The setup and pairing screens say which path they expect to use, and warn before
a pairing-required bed would bond through a proxy. Diagnostics record the path
that was predicted, the path actually used, who owns the bond and what evidence
there is for it.

### When pairing seems to have worked but nothing responds

Connecting is not the same as bonding, and a bed can accept a connection while
leaving the link unauthenticated. The integration therefore proves a bond by
reading a characteristic that an unbonded link cannot read. If that read fails
with an authentication error, the bond did not form and setup says so. If it
times out or the characteristic is missing, the result is inconclusive rather
than assumed good — some receivers (OKIN CST in particular) never answer that
read even when perfectly bonded — and the integration will simply ask to pair
again on its next connection instead of claiming a bond it cannot prove.

### Removing a bond

Settings → Devices & Services → Adjustable Bed → Configure → **Remove the
Bluetooth bond**. Use it when a bond has gone stale, when you want to re-pair
from scratch, or to clean up after moving the bed to a different adapter. It
asks for confirmation, names the adapter the bond is on, and verifies the
removal before reporting success. It never deletes the device.

If Home Assistant cannot read the host's Bluetooth bonds at all (no local
adapter, or no access to the system D-Bus), the action refuses rather than
guessing. If two adapters on the host are both bonded to the bed, set the bed's
preferred adapter to the one you want cleared and try again.

For a bed combined from two entries, the action first asks which side you mean.
Each side keeps its own Bluetooth address and bond state, so only the selected
side is disconnected and updated.

### Signs Pairing is Needed
- Connection succeeds but no commands work
- Device info (manufacturer/model) is blank and reads fail with "insufficient authentication"
- "Bluetooth pairing required" repair / error message

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
| `0000ff12-0000-1000-8000-00805f9b34fb` | Comfort Motion / Jiecang (Lierda1) |
| `0000fe60-0000-1000-8000-00805f9b34fb` | Comfort Motion / Jiecang (Lierda3, LOGICDATA MOTIONrelax) |
| `0000ffb0-0000-1000-8000-00805f9b34fb` | Keeson Base (fallback) |
| `0000ffe0-0000-1000-8000-00805f9b34fb` | Solace, MotoSleep, Octo (standard), Limoss/Stawett (name-based) |
| `0000ffe5-0000-1000-8000-00805f9b34fb` | Keeson Base, Ergomotion, Malouf LEGACY_OKIN, OKIN FFE, Serta |
| `0000fff0-0000-1000-8000-00805f9b34fb` | Keeson Base (fallback), Richmat WiLinke (variant) |
| `01000001-0000-1000-8000-00805f9b34fb` | Malouf/Lucid family (usually NEW_OKIN; `OKIN-BLE` + `BTCB` uses LEGACY_OKIN/FFE5) |
| `1b1d9641-b942-4da8-89cc-98e6a58fbd93` | Reverie |
| `45e25100-3171-4cfc-ae89-1d83cf8d8071` | Leggett & Platt Gen2 |
| `09d23fae-90e6-44c2-95b6-0b3d0f1abf25` | Sleep Number Climate 360 / FlexFit |
| `ffffd1fd-388d-938b-344a-939d1f6efee0` | Sleep Number i8 / 360 FlexFit 2 (BAM/MCR) |
| `62741523-52f9-8864-b1ab-3b3a8d65950b` | Okimat, Leggett Okin, Nectar, Okin CST (MFirm 900-O / Rize MF900), OKIN 64-bit, Sleepy's BOX24 |
| `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | Richmat Nordic, Keeson KSBT, Mattress Firm 900 |
| `8ebd4f76-da9d-4b5a-a96e-8ebfbeb622e7` | Richmat WiLinke |
| `99fa0001-338a-1024-8a49-009c0215f78a` | Linak |
| `db801000-f324-29c3-38d1-85c0c2e86885` | Reverie Nightstand |

---

## Debugging Tools

### Debug Logging vs Support Bundle

There are two ways to gather diagnostic information:

| Feature | Debug Logging | Support Bundle |
|---------|---------------|----------------|
| **How to access** | Settings → Devices → ⋮ menu → Enable debug logging | Perform the `adjustable_bed.generate_support_bundle` action |
| **What it captures** | Real-time stream of all integration activity | Snapshot of device state at one moment |
| **Content** | Actual BLE commands sent (e.g., `e5fe16...`), connection events, errors with stack traces | Configuration, advertisements (per source), detection reasoning, GATT/descriptor details, notifications, buffered command trace, connection-attempt details |
| **Size** | Large, includes unrelated entries from other integrations | Focused JSON file for one device |
| **Best for** | "Why didn't this command work?" - seeing exact bytes sent | "What device do I have?" - sharing device info in bug reports |

**When to use Debug Logging:**
- Commands don't work and you need to see what's being sent
- Investigating connection failures or timeouts
- Comparing expected vs actual command bytes

**When to use Support Bundle:**
- Opening a new GitHub issue
- Sharing device information with developers
- Documenting your bed's GATT services for protocol analysis

---

## Still Need Help?

If you've tried the troubleshooting steps above and still have issues, see the **[Getting Help Guide](GETTING_HELP.md)** for:

- How to generate a support bundle with all the info we need
- Filing a bug report on GitHub
- Requesting support for a new bed
- Capturing BLE protocol data for debugging

## Support bundle download links

A generated support bundle's download link can be retried for **one hour**.
It expires sooner if Home Assistant restarts or enough newer bundles replace
it (only the 32 newest unexpired links are retained). Downloads are not cacheable.
Treat the URL as a bearer credential: anyone holding it can download that bundle
while the link is valid.

Expiry does not delete the JSON file. Use the file path shown in the persistent
notification to retrieve the existing capture, or generate another support
bundle for a new link. Bundles retain full device addresses and optional logs
for troubleshooting, so inspect their contents before sharing them publicly.

## Position commands and reported state

A successful direct-position command means that the command was accepted; it
is not evidence that the target was reached. Position entities keep their last
reported value, or remain unknown until the bed reports a position. Sending the
same target again is allowed when no fresh report verifies the target.

Feedback-driven seeks require a fresh measurement for the requested axis.
Reports must belong to the current connection and normally be at most three
seconds old, with controller-specific freshness limits taking precedence.
Notification-only controllers can use a recent report even when an active read
does not produce a new one. This fallback requires a new report after movement
and does not reuse a consumed report to confirm a stall or authorize another
burst. Explicit notification policies retain their controller-specific rules.
If feedback disappears, the integration performs the controller's existing
movement cleanup and reports a failure. Last-known values can remain visible
for reference, but do not authorize further movement.
