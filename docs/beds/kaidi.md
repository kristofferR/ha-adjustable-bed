# Kaidi

**Status:** ❓ Needs testing

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

> [!NOTE]
> For **ISleep com.kaidi_test4**, choose the explicit [ISleep profile](isleep.md).
> Its accepted row064 audit corrects movement lifecycle, side routing, massage
> strengths and memory capacity independently of this legacy Kaidi route.
> Existing entries do not change automatically. Reconfigure or add the explicit
> ISleep profile and confirm product, actuator descriptor and room ID.

## Known Models

- Rize Beds, Floyd Home and ISleep bases (Kaidi OEM)
- Product names from the OEM apps: Remedy 3, Remedy 4, Contemporary 4,
  Contemporary 5, Tranquility II and the generic single/double layouts (see
  [APK-backed product IDs](#apk-backed-product-ids))
- Common Bluetooth name: `Mouselet`

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Rize](https://play.google.com/store/apps/details?id=com.kaidi_test4.rize) 1.3.0 | `com.kaidi_test4.rize` |
| ✅ | [Floyd Home](https://play.google.com/store/apps/details?id=com.kaidi_test4.floyd) 1.0.7 | `com.kaidi_test4.floyd` |
| ✅ | [ISleep](https://play.google.com/store/apps/details?id=com.kaidi_test4) 1.6.3 | `com.kaidi_test4` |

Floyd Home now has a separately audited [product 139 profile](floyd.md).
Its capabilities and control behavior come from its accepted artifact, not from
other apps sharing this transport. The remaining sections describe the legacy
Seat profiles unless stated otherwise. All three apps use only the Seat command
values; the legacy Bed values in the shared library are not used by any of them.

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ (head and foot on every variant; back, waist/lumbar per product) |
| Position Feedback | ❌ (direct targets are commands, not measured feedback) |
| Direct Position Targets | ✅ (back/legs 0-100%, Seat 1, Seat 2, Seat 1+2) |
| Memory Presets | ✅ (4 recall/save slots on the Seat variants; Floyd has 3) |
| Flat / Zero G / Anti-Snore | ✅ (Seat 1, Seat 2, Seat 1+2) |
| Book (TV) / Leisure (Lounge) | ⚠️ (product-gated) |
| Massage | ⚠️ (start/stop and 15/30/45-minute timers on Seat 1, Seat 2, Seat 1+2; requires **Has massage**) |
| Lights | ⚠️ (on/off, product-gated) |
| Single-address Left/Right | ✅ (`seat_1_2` only) |
| Hold until release | ✅ ([renewable](../SERVICES.md#renewable-holds), latched: up to 10 s, then STOP); ❌ Floyd Home |

## Protocol Details

**Service UUID:** `9e5d1e47-5c13-43a0-8635-82adffc0386f` (connected GATT service)
**Write Characteristic:** `9e5d1e47-5c13-43a0-8635-82adffc1386f`
**Notify Characteristic:** `9e5d1e47-5c13-43a0-8635-82adffc2386f`
**Format:** 4-byte control payloads wrapped in Kaidi's mesh-style GATT frame

### Packet Format

All multi-byte addresses are little-endian.

| Packet | Bytes |
|--------|-------|
| Join | `01 16 01` + room ID (4) + ASCII `1122` |
| Ping all (find target `vAddr`) | `03 FF FF FF FF FE` + source `vAddr` (4) |
| Control | `03` + target `vAddr` (4) + `20` + source `vAddr` (4) + `01 cmd param 00` |

The source `vAddr` is the bed-assigned own address, or `FF FF FF FF` when none
was reported. `param` is `00` except for direct position targets.

### Write Mode

Writes use response when the write characteristic reports the `write`
property, otherwise write without response.

## Detection / Setup

Kaidi beds are identified primarily by manufacturer data, not by advertised
service UUIDs.

> [!WARNING]
> **PairLink caveat:** the `0xFFFF`/`0xC0FF` manufacturer blob is the PairLink
> mesh SDK transport (`com.pairlink.mesh_lib` in the OEM APKs), which non-bed
> products, notably BLE mesh LED controllers, also emit. An ESPHome ESP32-C6
> LED controller advertising a structurally valid PairLink payload was
> misdetected as a Kaidi bed (issue #417); the OEM app's own scan validation
> accepts that payload too and filters on mesh room-ID membership, which the
> integration cannot replicate. Detection therefore requires a corroborating
> Kaidi signal (the `Mouselet` name, the FFC0/mesh service UUID, or a known
> Kaidi MAC OUI) alongside a parseable payload. The separately audited Floyd
> product 139 signature can also admit a bed without those shared signals.

| Signal | Value |
|--------|-------|
| Manufacturer data company ID | `0xFFFF` in Home Assistant advertisements |
| Manufacturer data marker | `0xC0FF` |
| Common device name | `Mouselet` |
| Known MAC OUIs in OEM app | `00:95:69`, `F0:AC:D7` |
| Advertised discovery service | `0000ffc0-0000-1000-8000-00805f9b34fb` |
| Connected GATT service | `9e5d1e47-5c13-43a0-8635-82adffc0386f` |
| Write characteristic | `9e5d1e47-5c13-43a0-8635-82adffc1386f` |
| Notify characteristic | `9e5d1e47-5c13-43a0-8635-82adffc2386f` |

Detection confidence is 0.95 with a Kaidi service UUID, otherwise 0.9.

### Advertisement layouts

Offsets count from the start of the payload including the `FF FF` company ID
(Home Assistant strips it; the parser accepts both forms).

| Type | Layout | Fields |
|------|--------|--------|
| `0x01` | Single-bed payload with `room_id` | room ID bytes 5-8; `sofaType` byte 9; `sofaAcuNo` bytes 10-11 (big-endian) |
| `0x02` | Broadcast payload with `room_id` and `vAddr` | room ID bytes 5-8; `vAddr` bytes 21-24; `sofaType`/`sofaAcuNo` at 17/18-19 when byte 20 is `A0` or `A1`, else at 25/26-27 |
| `0x09` | Discoverable/add-device payload | company ID bytes 11-12; `sofaType` byte 15; `sofaAcuNo` bytes 16-17 |

The integration caches the following Kaidi metadata in the config entry when it
can see a valid advertisement:

- `room_id`
- `vaddr`
- `product_id` (from advertised `sofaType`)
- `sofa_acu_no`
- advertisement type
- resolved Kaidi variant and the source used to resolve it

### APK-backed product IDs

The resolver recognizes these product IDs from Rize 1.3.0, ISleep 1.6.3,
and Floyd 1.0.7:

| Product IDs | Auto family |
|-------------|-------------|
| `129`, `131`, `132`, `135`, `136`, `137`, `138`, `142` | `seat_1` |
| `130`, `133`, `134`, `143` | `seat_1_2` |
| `139` | `floyd` |

Per-product capability gates (from the apps' `bedUI` mapping):

| ID | App name | Apps | bedUI | Extra controls |
|----|----------|------|-------|----------------|
| 129 | `BED_TYPE_SINGLE` | All | 2 | None (head + foot) |
| 130 | `BED_TYPE_DOUBLE2_4` | All | 2 | None |
| 131 | `BED_TYPE_SINGLE3` | All | 3 | Back |
| 132 | `BED_TYPE_SINGLE4` | All | 4 | Back, waist |
| 133 | `BED_TYPE_DOUBLE3` | All | 3 | Back |
| 134 | `BED_TYPE_DOUBLE4` | All | 4 | Back, waist |
| 135 | `REMEDY_3` | Rize/Floyd | 5 | Back, waist, lights, Book, Leisure |
| 136 | `REMEDY_4` | Rize/Floyd | 6 | Back, waist, lights, Book, Leisure |
| 137 | `CONTEMPORARY_4` | Rize/Floyd | 7 | Back, waist, lights, Leisure |
| 138 | `CONTEMPORARY_5` | Rize/Floyd | 8 | Back, waist, lights, Leisure |
| 139 | `TRANQUILITY_II` | Floyd | n/a | See the [Floyd guide](floyd.md) |
| 142 | `BED_TYPE_SINGLE5` | ISleep | 5 | Back, waist, lights, Book, Leisure |
| 143 | `BED_TYPE_DOUBLE_NEW` | ISleep | n/a (basic) | None |

IDs `140` and `141` are not in those app versions and are not inferred from
neighboring values. Other IDs use the narrow fallback below or require an
explicit variant. Unknown products retain the basic head + foot layout.

### `sofa_acu_no` heuristic

`sofaAcuNo` holds seat-bar counts: Seat 1 in bits 0-3, Seat 2 in bits 4-7,
Seat 3 in bits 8-11, and a store flag in bits 12-15.

When the product ID is not one of the OEM `BED_TYPE` values, the integration
uses `sofa_acu_no` only for the narrow case the APK data supports cleanly:

- exactly one populated seat bar resolves to `seat_1`, `seat_2`, or `seat_3`

Product `136` (Remedy 4, including the issue #247 report) now resolves directly
from its recognized product ID, rather than relying on this fallback.

If Kaidi metadata is present but does not map cleanly, `auto` refuses to guess
and a manual Kaidi variant override is required.

### Session Setup

Home Assistant follows the same bootstrap flow as the OEM apps:

1. Parse manufacturer data to recover the room/home ID and any advertised `vAddr`
2. Send the Kaidi join packet with ASCII password `"1122"`
3. Use the advertised `vAddr`, or ping to discover it if only a single-bed advertisement is visible
4. Send 4-byte control payloads wrapped in Kaidi's mesh-style GATT frame

If no room ID is in the stored or constructor data, the controller tries Home
Assistant's Bluetooth scanner before failing.

## Command Families

The integration exposes the Floyd app profile and four legacy Seat variants
under the shared `kaidi` bed type.
The current implementation uses the OEM apps' Seat commands; the old `bed_1`,
`bed_2`, and `bed_12` choices are not current variants.

| Variant | Use |
|---------|-----|
| `floyd` | Floyd Home product 139, see [dedicated guide](floyd.md) |
| `seat_1` | Single-base / lane 1 commands |
| `seat_2` | Lane 2 commands |
| `seat_3` | Lane 3 commands |
| `seat_1_2` | Dual base, sends the matching Seat 1 and Seat 2 commands |

### Features By Family

- The legacy Seat variants expose core movement and four memory recall/save slots.
- Floyd exposes three slots, a corrected Flat/release mapping, light controls and
  confirmed built-in preset programming. It has no direct position or massage controls.
- Seat 1, Seat 2, and Seat 1+2 expose Flat, Zero G, Anti-Snore, direct back/legs
  percentage targets, and massage start/stop and 15/30/45-minute timers. Massage
  entities also require **Has massage** in configuration.
- Product metadata gates extra axes, lights, and Book/Leisure presets. Unknown
  products retain the basic layout rather than gaining every optional feature.
- Seat 3 has a more limited command set, including lumbar movement, without
  direct position targets or the Seat 1/2 named presets and massage controls.
- Direct targets are commands, not measured position feedback; an accepted target
  must not be interpreted as confirmation that the bed reached it.

The current mappings and capability gates are in
[`kaidi_variants.py`](../../custom_components/adjustable_bed/kaidi_variants.py) and
[`beds/kaidi.py`](../../custom_components/adjustable_bed/beds/kaidi.py), with
[focused tests](../../tests/test_kaidi.py). This documents the shipped
implementation, not new physical validation.

### Single-address paired controls

Only `seat_1_2` can opt into **Enable Left / Right / Both controls** in the entry's
options. Left binds Seat 1, Right binds Seat 2, and Both retains the dual-command
behavior over the same Bluetooth connection. Other Kaidi variants remain
standalone. See [paired-side configuration](../CONFIGURATION.md#single-address-left--right-controls).

## Commands

Values are the `cmd` byte of the control payload `01 cmd param 00`. `seat_1_2`
sends the Seat 1 value, then the matching Seat 2 value (unless a Left or Right
side control is bound to one seat).

### Motor Control

| Command | Seat 1 | Seat 2 | Seat 3 | Notes |
|---------|--------|--------|--------|-------|
| Head up / down / stop | `0x01` / `0x02` / `0x03` | `0x0A` / `0x0B` / `0x0C` | `0x13` / `0x14` / `0x15` | |
| Foot up / down / stop | `0x04` / `0x05` / `0x06` | `0x0D` / `0x0E` / `0x0F` | `0x16` / `0x17` / `0x18` | |
| Back up / down / stop | `0x7A` / `0x7B` / `0x7C` | `0x7D` / `0x7E` / `0x7F` | none | Back products only; otherwise back uses the head commands |
| Waist (lumbar) up / down / stop | `0x83` / `0x84` / `0x85` | `0x86` / `0x87` / `0x88` | `0x19` / `0x1A` / `0x1B` | Waist products; always on Seat 3 |
| Stop all | `0x1C` | `0x1D` | none | Seat 3 sends each motor's stop instead |

### Direct Position Targets

| Command | Seat 1 | Seat 2 | `param` |
|---------|--------|--------|---------|
| Head (back) setting | `0x4D` | `0x4E` | Target 0-100 |
| Leg setting | `0x4F` | `0x50` | Target 0-100 |

### Presets

| Command | Seat 1 | Seat 2 | Seat 3 | Notes |
|---------|--------|--------|--------|-------|
| Flat | `0x68` | `0x69` | none | |
| Zero G | `0x62` | `0x63` | none | |
| Anti-Snore | `0x65` | `0x66` | none | |
| Book (TV preset) | `0x9E` | `0x9F` | `0xA0` | Book products only |
| Leisure (Lounge preset) | `0xA1` | `0xA2` | `0xA3` | Leisure products only |

### Memory

| Command | Seat 1 | Seat 2 | Seat 3 |
|---------|--------|--------|--------|
| Save 1 / 2 / 3 / 4 | `0x25` / `0x26` / `0x27` / `0x28` | `0x2D` / `0x2E` / `0x2F` / `0x30` | `0x35` / `0x36` / `0x37` / `0x38` |
| Recall 1 / 2 / 3 / 4 | `0x29` / `0x2A` / `0x2B` / `0x2C` | `0x31` / `0x32` / `0x33` / `0x34` | `0x39` / `0x3A` / `0x3B` / `0x3C` |

### Lights

| Command | Seat 1 | Seat 2 | Seat 3 | Notes |
|---------|--------|--------|--------|-------|
| Light on / off | `0x5C` / `0x5D` | `0x5E` / `0x5F` | `0x60` / `0x61` | Light products only |

### Massage

| Command | Seat 1 | Seat 2 | Notes |
|---------|--------|--------|-------|
| Massage start / stop | `0x47` / `0x48` | `0x49` / `0x4A` | Toggle sends start or stop from local state |
| Massage timer 15 / 30 / 45 min | `0x53` / `0x54` / `0x55` | `0x56` / `0x57` / `0x58` | |

The command profiles also carry Neck, All and New All values from the app
tables; no entity sends them.

## Notifications

| Notification | Meaning |
|--------------|---------|
| `02 16 status` | Join response; status `0` is accepted, anything else fails setup |
| `01 0A` + `vAddr` (4) | The bed's own address for this session |
| `03 …` with channel `FF` at byte 5 | Ping reply: bytes 6-11 are the node MAC (reversed), bytes 12-15 its `vAddr`; used only when the MAC matches the configured bed |

## Command Timing

- Join and target-address waits time out after 5 seconds; the own-address wait
  after 1 second.
- Movement repeats the move command at the configured pulse count and delay,
  then sends that motor's stop command with a fresh cancel event.
- Presets, memory, lights, position targets and massage are sent once.

## Notes

1. The bed must already be provisioned in the official app. Home Assistant does not implement the add-device/reset workflow.
2. Kaidi devices named `Mouselet` are valid beds when the manufacturer payload matches Kaidi; the generic `"mouse"` exclusion no longer applies in that case.
3. If `auto` reports unresolved Kaidi metadata, switch the integration option to the verified layout: `seat_1`, `seat_2`, `seat_3`, or `seat_1_2`.
