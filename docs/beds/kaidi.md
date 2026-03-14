# Kaidi

**Status:** ❓ Needs testing

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Brands / Apps

- Rize Beds
- Floyd Home
- ISleep

These apps share the same Kaidi OEM protocol family.

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (head/back + legs/feet) |
| Position Feedback | ❌ |
| Memory Presets | ✅ (4 slots) |
| Factory Presets | ✅ (Flat, Zero-G, Anti-Snore) |
| Massage | ❌ Not wired yet |

## Protocol Details

**Advertised Service UUID:** `0000ffc0-0000-1000-8000-00805f9b34fb`  
**Connected Service UUID:** `9e5d1e47-5c13-43a0-8635-82adffc0386f`  
**Write Characteristic:** `9e5d1e47-5c13-43a0-8635-82adffc1386f`  
**Notify Characteristic:** `9e5d1e47-5c13-43a0-8635-82adffc2386f`

## How It Works

Kaidi beds use normal BLE GATT, but the app wraps commands in a custom
"mesh-style" packet format.

Home Assistant reproduces the app's startup flow:

1. Parse the manufacturer data payload to recover the room/home ID
2. Send the join packet with the Kaidi password (`"1122"`)
3. Resolve the bed's target virtual address (`vAddr`) from advertisement data or ping
4. Send control packets on channel `0x20`

## Notes

1. The bed must already be provisioned in the official app. Home Assistant does not currently implement the add-device/reset workflow.
2. The current controller targets the single-bed command set used by standard head/foot bases.
3. If your bed exposes different Kaidi behavior, open an issue and attach a support report plus any nRF Connect logs you can capture.
