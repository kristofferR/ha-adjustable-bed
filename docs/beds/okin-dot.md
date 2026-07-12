# Okin DOT (DewertOkin "DOT PROTOCOL")

**Status:** ⚠️ Untested (protocol from APK + live handset backend, no hardware confirmation yet)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed) from the FurniMove app (`com.okin.okinsmartcomfort`) and the DewertOkin handset backend

## Overview

"DOT PROTOCOL" is DewertOkin's name (it appears verbatim in RF34 handset
descriptions) for receiver boxes that pair with the RF1058, RF34, and RF6707
RF handsets. The handset remote codes resolve through the same FurniMove
backend as the [Okimat](okimat.md) codes, but the box itself is a CB24-family
receiver: it exposes the Nordic UART service instead of the Okin `62741523`
service and takes CB24-style 7-byte frames.

If the code printed on your remote is one of **90167, 91983, 93558, 97450,
97544, 98035**, select the **Okin DOT** bed type and pick that code as the
protocol variant. Entries configured as Okimat/Okin UUID are also rescued
automatically: if the connected box has no Okin `62741525` characteristic but
does expose Nordic UART, the integration promotes the entry to the Okin DOT
bed type (persisted, which also drops the Okimat pairing requirement) and
falls back to the default DOT remote until a printed DOT code is selected —
standard Okimat keycodes are never wrapped in DOT frames.

## Remote codes

| Code | Handset | Motors | Extras |
|------|---------|--------|--------|
| 90167 | RF1058 | Head + Feet | 4 memories, zero-g, quiet sleep, head/foot massage |
| 91983 | RF1058 | Head + Feet | 3 memories, zero-g, anti-snore, head/foot massage |
| 93558 | RF1058 | Head + Feet | 3 memories, zero-g, anti-snore, head/foot massage |
| 97450 | RF34/09/WH/GY | Back + Legs | 2 memories |
| 97544 | RF34/09/BK/BK | Back + Legs | 2 memories |
| 98035 | RF6707 | Head + Back | Motors + light only |

Note the motor keycodes are **renumbered per handset**: whichever two motor
channels the handset drives, the first pair is `0x1`/`0x2` and the second is
`0x4`/`0x8` (unlike the fixed Okimat bit assignment). The channels keep their
section meaning (M1=Head, M2=Back, M3=Legs, M4=Feet in FurniMove), and the
integration exposes correspondingly named controls — an RF1058 bed gets Head
and Feet covers, an RF6707 bed gets Head and Back.

## BLE Protocol

**Service UUID:** `6e400001-b5a3-f393-e0a9-e50e24dcca9e` (Nordic UART)
**Write Characteristic:** `6e400002-b5a3-f393-e0a9-e50e24dcca9e` (write without response)

FurniMove calls this characteristic `CB24_WRITE_CHARACTERISTIC` and flags the
connection as DOT when it is present (`BluetoothLeService.setCharacteristics`).

### Handshake

On discovering the write characteristic, FurniMove immediately writes the
ASCII string `affirm` to it. The integration mirrors this once per connection
before the first command.

### Packet Format

7 bytes (`HexValueConverter.toByteArray` with `isDOTProtocol=true`):

```text
[0x05, 0x02, kc3, kc2, kc1, kc0, 0x00]
```

- Bytes 2–5: 32-bit keycode, big-endian
- No checksum
- Identical to the [Okin CB24](../SUPPORTED_ACTUATORS.md) frame with bed
  selection byte `0x00`

### Command Timing

- Held buttons are re-sent ~every 100ms (the app rewrites the characteristic
  on each write completion after a 100ms sleep)
- Release sends keycode `0x00000000` (`DisobeyStandbyTime`) as the stop
- Memory recall is a **short press** (one frame + STOP); save is the hold:
  5s @ 200ms on RF1058, 2s @ 200ms on RF34. On 97544 recall and save share
  keycode `0x10000` — only the press duration distinguishes them
- The light key is a hold too (5s @ 100ms per the backend)

## Commands (32-bit keycodes)

Shared across all six codes:

| Command | Value |
|---------|-------|
| Stop | `0x00000000` |
| First motor Up / Down | `0x00000001` / `0x00000002` — Head on RF1058/RF6707, Back on RF34 |
| Second motor Up / Down | `0x00000004` / `0x00000008` — Feet on RF1058, Legs on RF34, Back on RF6707 |
| Flat | `0x08000000` |
| Toggle Lights (UBL) | `0x00020000` |

Note the DOT Flat value `0x08000000` equals the standard Okimat child-lock
keycode — one of the reasons these codes must not be driven with the Okimat
profile.

Per-code extras (RF1058 family):

| Command | Value |
|---------|-------|
| Zero gravity | `0x00001000` |
| Quiet sleep (90167) / Anti-snore (91983, 93558) | `0x00004000` |
| Memory 1–4 (90167) | `0x3000`, `0x5000`, `0x6000`, `0x7000` |
| Memory 1–3 (91983, 93558) | `0x2000`, `0x8000`, `0x3000` |
| Memory save (hold 5s) | `0x00010000` |
| Massage head +/− | `0x00000800` / `0x00800000` |
| Massage feet +/− | `0x00000400` / `0x01000000` |
| Massage wave | `0x10000000` |
| Massage stop | `0x00000100` |

RF34 codes (97450, 97544):

| Command | Value |
|---------|-------|
| Memory 1 / Memory 2 | `0x00010000` / `0x00040000` |
| Memory save (hold 2s) | `0x0001f000` (97450), `0x00010000` (97544) |

All keycodes come live from the DewertOkin handset backend
(`GET /mobile-data/button/{code}`); the snapshot lives in
`tools/okin_remotes/master.json` with `protocol: "dot"`.

## Differences from Okimat

| | Okimat (okin_uuid) | Okin DOT |
|---|---|---|
| Service | `62741523-...` | Nordic UART `6e400001-...` |
| Frame | 6-byte `04 02 <kc BE>` | 7-byte `05 02 <kc BE> 00` |
| Write | With response | Without response |
| Pairing | Required | Not required |
| Position feedback | Yes (FFE4 notify) | None known |
| Handshake | None | `affirm` on connect |

## Source Code References

- `custom_components/adjustable_bed/beds/okin_dot.py` — controller
- `disassembly/output/com.okin.okinsmartcomfort/jadx/sources/com/dewertokin/okinsmartcomfort/service/utils/HexValueConverter.java` — DOT framing
- `disassembly/output/com.okin.okinsmartcomfort/jadx/sources/com/dewertokin/okinsmartcomfort/service/bleModule/bluetooth/BluetoothLeService.java` — DOT detection + `affirm` handshake

## Notes

- After releasing a button, FurniMove also writes a raw 2-byte `00 B0` packet
  ~400ms after the stop keycode. Its function is unknown (possibly re-arming
  the box's standby timer); the integration does not send it. If a tester
  reports motors that keep creeping after stop, this is the first thing to try.
- The RF34 97544 handset uses the same keycode (`0x00010000`) for Memory 1
  recall and memory save — on the physical remote, saving is holding the
  memory button. A short press recalls, the 2s hold stream saves.
