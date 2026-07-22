# Okimat/Okin

**Status:** ✅ Tested

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed), david_nagy, corne, PT, and [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt)

## Known Models
- Okimat beds
- Lucid L600
- Rize beds (II, Contempo, Bob, Sanctuary, Aviada, MF900, Resident)
- Customatic beds (Clarity, Demo, Remedy, Jerome's)
- Glory, Tranquil, Jobs 賈伯斯, Nectar Motion
- Other beds with Okin motors

## Apps

Several apps use this protocol:

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [OKIN ComfortBed II-N](https://play.google.com/store/apps/details?id=com.ore.jalon.neworebeding) | `com.ore.jalon.neworebeding` |
| ✅ | [OKIN Comfort Bed](https://play.google.com/store/apps/details?id=com.ore.okincomfortbed) | `com.ore.okincomfortbed` |
| ✅ | [OKIN Smart Bed](https://play.google.com/store/apps/details?id=com.okin.bedding.smartbedwifi) | `com.okin.bedding.smartbedwifi` |
| ✅ | Rize II | `com.okin.bedding.rizeii` |
| ✅ | Rize Resident | `com.okin.bedding.rizeResident` |
| ✅ | Customatic Clarity | `com.okin.bedding.customaticclarity` |
| ✅ | OkinSmartComfort | `com.okin.okinsmartcomfort` |
| ✅ | Glory | `com.okin.bedding.glory` |
| ✅ | Tranquil | `com.okin.bedding.tranquil` |
| ✅ | Jobs 賈伯斯 | `com.okin.bedding.jobs` |
| ✅ | Nectar Motion | `com.okin.bedding.nectarmotion` |
| ✅ | Support 挺你 | `com.okin.bedding.support` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ |
| Position Feedback | Some receivers (FFE4 characteristic required) |
| Memory Presets | ✅ (2-4 slots depending on remote) |
| Massage | ✅ |
| Under-bed Lights | ✅ |

> [!NOTE]
> **Okin Protocol Family**
>
> Okimat is part of a family of beds using Okin-based BLE protocols. While they share the same service UUID, they use different command formats:
>
> | Bed Type | Format | Key Difference |
> |----------|--------|----------------|
> | **Okimat** | 6-byte | UUID-based writes; some receivers also expose FFE4 position feedback |
> | [Leggett & Platt Okin](leggett-platt.md) | 6-byte | Same protocol, different name detection |
> | [Nectar](nectar.md) | 7-byte | Different command structure |
> | [DewertOkin](dewertokin.md) | 6-byte | Handle-based writes (not UUID) |
> | [Mattress Firm 900](mattressfirm.md) | 7-byte | Uses Nordic UART service |
> | [Okin CST](okin-cst.md) | 14-byte | MFirm 900-O / Rize MF900-style OKIN service devices |
> | [Okin 64-Bit](okin-64bit.md) | 10-byte | 64-bit commands, `0x08 0x02` header |
>
> See [Okin Protocol Family](../SUPPORTED_ACTUATORS.md#okin-protocol-family) for detection priority and troubleshooting.

## Detection

Okimat is the fallback for beds using the Okin service UUID. Some receiver modules only
advertise a local name such as `OKIN-Receiver` or `OKIN - Receiver` until paired; those are
shown as a pairing-required Okin-family protocol selection because the receiver name and
shared Okin service UUID do not identify the packet format by themselves.

Detection priority:
1. Device name contains "nectar" → Nectar
2. Device name contains "leggett", "l&p", or "adjustable base" → Leggett & Platt
3. Device name contains "okimat", "okin rf", or "okin ble" → Okimat/Okin UUID
4. Connected GATT has OKIN UUID + CSS + Nordic DFU → Okin CST
5. Device name is `OKIN-Receiver` / `OKIN - Receiver` → prompt for Okin-family protocol
6. Fallback → Okimat (with warning)

**If your bed is misidentified:** Change the bed type in integration settings.

## Protocol Details

**Service UUID:** `62741523-52f9-8864-b1ab-3b3a8d65950b`
**Format:** 6 bytes `[0x04, 0x02, ...int_bytes]` (big-endian)

**⚠️ Requires BLE pairing before use!**

## Supported Remote Codes

The integration ships **210 remote codes** covering the captured DewertOkin RF
handset range (RFS-ELLIPSE, RF-TOPLINE, RF-LITELINE, RF-FLASHLINE, RF-FREE-ELEC,
RF-TOUCH, RF-TOUCHLINE, RF-STYLE, RF-ECO and their memory/massage variants).
The remote code is printed on the back of the handset; select it under
**Protocol variant** in the integration options. The app accepts manually
entered IDs, but its backend has no endpoint that enumerates every valid ID, so
this table is a snapshot rather than a provably complete catalog. If an exact
code is not offered, use a captured code only when its button layout and
keycodes have been verified for that handset.

### Source of truth (important)

The remote table is **generated from the DewertOkin FurniMove handset backend**
(`GET /mobile-data/button/{code}`), which returns authoritative 32-bit keycodes
and timing metadata per remote code. For codes the backend no longer serves,
keycodes are taken from the bundled `handsetlist.csv` capability flags by
matching each pruned code to a live code with the identical capability
signature. See
`beds/okin_uuid_remotes.py` for the generated table (each entry is tagged
`backend`, `csv-inherit:<code>`, or `csv-reconstruct`) and
`tools/okin_remotes/` for the regeneration pipeline.

Because **Flat is a per-code property** (two codes in the same model family can
use different Flat values), the table stores each code's exact values rather
than lumping codes into shared family profiles. This corrected several Flat
values that earlier releases had wrong (e.g. 82620, 83489, 91246, 92591, 93306).

> [!NOTE]
> Six codes that share the handset backend use a different transport and
> command layout ("DOT PROTOCOL" / RF1058 / RF34 / RF6707: 90167, 91983, 93558,
> 97450, 97544, 98035). They are supported by the separate
> [**Okin DOT**](okin-dot.md) bed type — if that number is printed on your
> remote, select "Okin DOT" instead of Okimat during setup.

### Capability coverage

| Capability | Codes | Notes |
|------------|-------|-------|
| Back motor | 203 | Usually `0x01/0x02` (RF-FREE-ELEC shifts the bit assignment; each code stores its own) |
| Legs motor | 199 | Usually `0x04/0x08` |
| Head/tilt motor | 59 | `0x10/0x20` (7 codes are head-only handsets) |
| Feet motor | 38 | `0x40/0x80` (a few use `0x20` for feet-down) |
| Memory presets | 99 | 1–4 slots depending on code |
| Flat preset | 206 | A few basic RF-ECO remotes have no flat button |
| Under-bed light | 172 | `0x20000`; one write per HA button press; codes whose handset has no light key get no light entity |
| Memory save | 99 | Hold-to-save; per-code backend hold timing (2s/5s/8s @ 200ms) where the backend specifies it |
| Sync both sides | 69 | Split-base re-sync (`0x100`, long hold released with STOP) |
| Child lock | 53 | Handset lock toggle (`0x08000000`, long hold released with STOP) |
| Massage | 13 | Head/foot intensity, wave or program cycling, stop |
| Zero-gravity | 8 | Dedicated preset (`0x4000`) |

The exposed HA controls follow each code's handset layout: only motors the
handset actually drives get covers (head controls drive the dedicated
head/tilt motor when the remote has one, and stay a back synonym on 2-motor
remotes), and the light toggle only appears for codes with a light key. The
configured motor count still caps how many axes are shown.

## Commands (32-bit Values)

| Command | Value | Remotes | Description |
|---------|-------|---------|-------------|
| Stop | `0x00000000` | All | Stop all motors |
| Back Up | `0x00000001` | All | Raise back |
| Back Down | `0x00000002` | All | Lower back |
| Legs Up | `0x00000004` | All | Raise legs |
| Legs Down | `0x00000008` | All | Lower legs |
| Head Up | `0x00000010` | 93329, 93332 | Raise head (tilt) |
| Head Down | `0x00000020` | 93329, 93332 | Lower head (tilt) |
| Feet Up | `0x00000040` | 93332 | Raise feet |
| Feet Down | `0x00000020` | 93332 | Lower feet |
| Memory 1 | `0x00001000` | 82418, 85058, 91246, 92471, 92591, 93306, 93329, 93332, 94238 | Go to memory 1 |
| Memory 2 | `0x00002000` | 82418, 85058, 91246, 92471, 92591, 93306, 93329, 93332, 94238 | Go to memory 2 |
| Memory 3 | `0x00004000` | 93329 | Go to memory 3 |
| Memory 4 | `0x00008000` | 93329 | Go to memory 4 |
| Memory Save | `0x00010000` | 82418, 85058, 91246, 92471, 92591, 93306, 93329, 93332, 94238 | Save current position |
| Toggle Lights | `0x00020000` | All | Toggle under-bed lights |

**Note:** On remote 93332, Head Down and Feet Down share the same command value (`0x00000020`). This is intentional per the [smartbed-mqtt reference implementation](https://github.com/richardhopton/smartbed-mqtt) - the remote hardware maps this single command to different motor functions.

### Flat Command Values

Different remotes use different values for the Flat preset:

| Flat Value | Remotes |
|------------|---------|
| `0x000000aa` | 82417, 82418, 82620, 82757, 82760, 82764, 82767, 82770, 83358, 83462, 83489, 84931, 84963, 85058, 92461, 92471, 93305, 93306, 93332 |
| `0x0000002a` | 93329 |
| `0x10000000` | 91246, 92591, 94238 |
| `0x100000aa` | 76688, 78375, 78378, 78386, 80599, 80602, 80608, 80616, 88875, 88877, 89137, 89138, 89139, 91244, 92535 |

## Position Feedback

Some Okimat receivers support position feedback via BLE notifications. The
FFE4 characteristic must be present; it is not part of every controller's GATT
layout.

**Position Service UUID:** `0000ffe0-0000-1000-8000-00805f9b34fb`
**Notify Characteristic:** `0000ffe4-0000-1000-8000-00805f9b34fb`

### Data Format

Position notifications are 7+ bytes:
- Bytes 3-4: Head position (little-endian uint16)
- Bytes 5-6: Foot position (little-endian uint16)

### Angle Conversion

| Motor | Max Raw Value | Max Angle |
|-------|---------------|-----------|
| Head/Back | 16000 | 60° |
| Foot/Legs | 12000 | 45° |

Formula: `angle = (raw_value / max_raw) * max_angle`

FurniMove 2.2.0 does not expose an alternate position path for receivers
without FFE4. Its `62741625...` feedback parser reports only under-bed light,
sync, and child-lock state, while notifications on `90311725...` are ignored.
No reachable app path parses angle or current motor position from either
channel.

## Command Timing

From FurniMove 2.2.0 app analysis:

- **Repeat interval:** 100 ms after each successful write
- **Pattern:** Continuous only while the touchscreen button remains held
- **Release:** Send the zero/standby keycode and stop repeating
- **UBL metadata:** The app does not use the backend UBL `duration` or
  `frequency` fields to schedule writes; a light tap starts one press sequence

## Protocol Variants (from OKIN ComfortBed II-N app)

The app supports multiple protocol versions based on device name:

| Device Prefix | Protocol | Packet Format |
|---------------|----------|---------------|
| `okin-ble` | CB.13/CB.15 (FFE5) | 9-byte: `[0xE6, 0xFE, 0x16, cmd(4), side, checksum]` |
| `smartbed` | CB.24 (Nordic UART) | 7-byte: `[0x05, 0x02, cmd(4), 0x00]` (no checksum) |

### CB.24 Preset Safety

CB.24 preset recalls are sent as a single packet. The SmartBed app repeats the
same packet every 300 ms only while a touchscreen button remains held, and a
5.2-second hold is the controller's memory-save gesture. Fixed-duration or
automatically learned repeat streams can therefore overwrite the remote's
stored presets. All CB.24 profile variants, including the legacy `cb_old`
compatibility alias, use safe one-shot preset recall.

### Additional Motors Supported

| Motor | Up | Down |
|-------|-----|------|
| Neck | `0x00000010` | `0x00000020` |
| Lumbar | `0x00000040` | `0x00000080` |
| Hips (CB.24) | `0x40000000` | `0x80000000` |

---

## Related Okin 64-Bit Protocol

Some newer Okin controllers use the separate [Okin 64-Bit](okin-64bit.md)
protocol with 10-byte `0x08 0x02` frames. Select **Okin 64-Bit** instead of
Okimat if diagnostics show a `NORA_CON` / `NORACON` controller or the 64-bit
packet format from the `com.okin.bedding.adjustbed` app.
