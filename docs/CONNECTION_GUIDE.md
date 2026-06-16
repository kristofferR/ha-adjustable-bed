# Adjustable Bed Connection Guide

This guide explains how to connect your adjustable bed to Home Assistant.

## Understanding Bluetooth Connectivity

Most adjustable beds use Bluetooth Low Energy (BLE) to communicate with their remote controls and apps. This integration connects directly to your bed's BLE controller.

**Key Points:**
- **BLE Range**: Typically 10-30 meters, but walls and interference reduce this
- **Single Connection**: Most beds only accept ONE Bluetooth connection at a time - disconnect manufacturer apps first
- **Idle Disconnect**: The integration disconnects after 40 seconds of idle time to allow other devices to connect

### Does Your Bed Have Bluetooth?

Not all adjustable beds include Bluetooth — some use only radio frequency (RF) to communicate with their remote. If your bed doesn't have a companion app for your phone, or doesn't appear in any BLE scanner (like [nRF Connect](https://www.nordicsemi.com/Products/Development-tools/nRF-Connect-for-mobile)), it likely doesn't have Bluetooth at all. Check with your manufacturer to confirm. Known non-Bluetooth models include the GhostBed adjustable base with the Okin CB1522 controller ([discussion](https://github.com/kristofferR/ha-adjustable-bed/discussions/248)).

### Beds Requiring Bluetooth Pairing

Some beds require OS-level Bluetooth pairing before the integration can communicate:

> **Understanding the table below:** The entries mix brand names, protocol variants, and generation names because manufacturers often use different communication protocols across their product lines. For example:
>
> - **Okimat/Okin** refers to Okimat-branded beds that use the Okin protocol (requires pairing).
> - **Leggett & Platt** appears in multiple rows because different models use different protocols/generations (Gen2, Okin variant, MlRM/WiLinke).
> - **Sleep Number** includes both newer Climate 360 / FlexFit Fuzion bases and older BAM/MCR bases such as some i8 / 360 FlexFit 2 beds. Fuzion bases typically appear as `Smart bed *` in OS Bluetooth menus, but the integration itself identifies them by their GATT service UUID — the device name is only a human hint to help you pick the right row in this table during pairing.
>
> To determine which row applies to your bed, check the label on your bed frame or controller, look at your remote's branding, or consult your manufacturer's manual.

| Bed Type | Pairing Required |
|----------|-----------------|
| Okimat/Okin | ✅ Yes |
| Okin CST (incl. OKIN-* Nectar Motion / Mattress Firm 900-O / Rize MF900) | ✅ Yes |
| Leggett & Platt Okin variant | ✅ Yes |
| Logicdata SimplicityFrame | ✅ Yes |
| Vibradorm | ✅ Yes |
| Sleep Number Climate 360 / FlexFit (Fuzion) | ✅ Yes |
| Sleep Number i8 / 360 FlexFit 2 (BAM/MCR) | ❌ No |
| Leggett & Platt Gen2 | ❌ No |
| Leggett & Platt MlRM | ❌ No |
| Nectar (DewertOkin protocol) | ❌ No |
| DewertOkin | ❌ No |
| Most other beds | ❌ No |

*Note: the two Sleep Number entries are separate bed types, not variants of the same one — Sleep Number Fuzion always requires pairing, Sleep Number BAM/MCR never does. Leggett & Platt only requires pairing on its Okin variant.*

> **Nectar is split across two rows on purpose.** "Nectar" branding covers more than one protocol. Bases that advertise as `OKIN-XXXXXX` are detected as **Okin CST** and **do** require pairing; older Nectar bases that use the DewertOkin protocol do **not**. The integration picks the right one by GATT signature — the brand on the bed is only a hint.

**How to pair (if required):**
1. Put your bed in pairing mode. For **OKIN** bases (Okimat, Okin CST, Nectar OKIN-*, Mattress Firm 900-O, Rize MF900), **power-cycle the control box** — unplug it ~30 seconds, then plug it back in; the light blinks blue then turns green after ~20 s. There is **no Bluetooth pairing button**; any Pair/Learn button only syncs the RF remote. For **Sleep Number Climate 360 / FlexFit Fuzion**, hold the side pairing button until the blue light blinks.
2. On the device running Home Assistant's Bluetooth stack (HA host or proxy), let the integration pair, or pair manually in Bluetooth settings.
3. The bed may appear as `OKIN`, `OKIN-XXXXXX`, `OKIN-Receiver`, `Okimat`, `Smart bed 123456`, or similar.

Older Sleep Number BAM/MCR bases connect without OS-level pairing.

**Note:** Pair on the device running Home Assistant's Bluetooth stack, **not your phone**. ESPHome Bluetooth proxies support pairing only on **ESPHome 2024.3.0+**; if pairing keeps failing, use a local adapter near the bed. If a bed connects but stays unbonded, Home Assistant raises a **"Bluetooth pairing required"** repair with a **Fix** button that walks you through it.

---

## Connection Methods

This integration requires an **active BLE connection** to send commands to your bed. You need one of the following:

### *Method 1: ESPHome Bluetooth Proxy (Recommended)*

Use an ESP32 device running ESPHome as a Bluetooth proxy. This extends your Bluetooth range using WiFi.


**Pros:** Excellent range (place ESP32 near the bed), multiple proxies for whole-home coverage

**Cons:** Requires additional hardware (~$5-15)


### *Method 2: Local Bluetooth Adapter*

If your Home Assistant host has a Bluetooth adapter (built-in or USB dongle).


**Pros:** Simple setup, no additional hardware

**Cons:** Limited range, may not work if HA host is far from bed


### What Does NOT Work

**Shelly devices** (Pro 3 EM, Plus series, etc.) can act as passive BLE scanners for Home Assistant — they will discover nearby Bluetooth devices, so your bed may appear in the Bluetooth integration. However, Shelly devices **cannot establish active BLE connections**, which means the Adjustable Bed integration cannot use them to send commands. You need an ESPHome Bluetooth Proxy or a local Bluetooth adapter instead.

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

After setup, you can adjust additional settings via **Settings → Integrations → Adjustable Bed → Configure** (gear icon):

- **Protocol variant** - Override if auto-detection fails
- **Motor pulse settings** - Fine-tune movement behavior
- **Bluetooth adapter** - Choose a specific adapter or proxy
- **Angle sensing** - Disable to allow physical remote to work (recommended)

See the [Configuration Guide](CONFIGURATION.md) for detailed explanations of all options.

---

## Finding the Bluetooth Address

If your bed isn't auto-discovered:

**Using the Integration (Recommended):**
1. Go to Settings → Integrations → Add Integration → Adjustable Bed
2. Choose "Manual entry"
3. The integration displays all discovered Bluetooth devices with their MAC addresses
4. Find your bed in the list (look for names like "Desk XXXXX", "HHC...", your bed brand, etc.)

**Using ESPHome Logs:**
1. Open ESPHome dashboard → View logs for your proxy
2. Look for: `[bluetooth_proxy] Proxying packet from AA:BB:CC:DD:EE:FF...`

**Using nRF Connect (Fallback):**

If your bed doesn't appear in Home Assistant at all (not visible to any adapter or proxy), use [nRF Connect](https://www.nordicsemi.com/Products/Development-tools/nRF-Connect-for-mobile) on your phone to verify the device exists and check its range. If nRF Connect sees it but Home Assistant doesn't, the bed may be out of range of your HA Bluetooth adapter - consider adding an ESPHome proxy closer to the bed.

**Tip:** If your bed type isn't recognized, use **Browse unsupported BLE devices** to find the MAC address, then run `adjustable_bed.generate_support_bundle` with `target_address`. See [Getting Help](GETTING_HELP.md) for details.

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
