# Supported Actuators

This guide maps actuator families and app profiles to detailed protocol references.
The [README Supported Beds table](../README.md#supported-beds) is the canonical
support index. Each linked guide records model-specific evidence and hardware
validation limits; the feature summaries below depend on the selected controller.

| Brand | Key Features |
|-------|--------------|
| [Linak](beds/linak.md) | Auto-detected models, up to 5 axes, 0/4 memories, speed/status/errors, massage, alarms, lights |
| [Keeson](beds/keeson.md) | Position feedback (Ergomotion), 4 presets, massage, lights |
| [Richmat](beds/richmat.md) | 1-5 memory presets, massage (discrete), RGB lights + timer, Controller Sync, motors 5-7 |
| [RMControl products](beds/rmcontrol.md) | Explicit product catalogs, reported state, alarms and snore intervention |
| [MotoSleep](beds/motosleep.md) | Model-dependent HHC/MOTO controls, memory, massage and lighting |
| [Octo](beds/octo.md) | Two protocol variants, optional PIN auth, RGBW lights. Sold as bett1.de, Dunlopillo, Hüsler Nest, Swiss Sense, Velda, Werkmeister, sleepling and more ([known brand list](beds/octo.md#bed-brands-that-ship-octo-actuators)) |
| [Solace](beds/solace.md) | Name-based profiles, named presets, optional massage/lights, exact S4-Y lift/tilt; explicit [Woosa Sleep](beds/woosa.md) profile with one Favourite memory |
| [Leggett & Platt](beds/leggett-platt.md) | Gen2: motor control + RGB lighting; Okin: tilt/lumbar, massage |
| [Prodigy / U Series app profiles](beds/leggett-okin.md) | Explicit layout, held controls, sleep/alarm timers |
| [L&P legacy app](beds/lp-legacy.md) | Explicit model, protocol mode and confirmed GATT characteristics |
| [Reverie](beds/reverie.md) | Position control (0-100%), 4 presets, wave massage |
| [Okimat/Okin](beds/okimat.md) | 4 memory presets, massage, lights (requires pairing) |
| [Okin 64-Bit](beds/okin-64bit.md) | 10-byte Nordic/custom OKIN protocol, lumbar, lights, massage |
| [Jiecang](beds/jiecang.md) | Motor control, 3 memory slots, massage, split bed support |
| [Jiecang app profiles](beds/jiecang-app.md) | ERGOBALANCE / Dream Motion layouts, alarms, wake routines, renaming |
| [Kaidi](beds/kaidi.md) | Mouselet-based beds, Flat/Zero-G/Anti-Snore, 4 memory slots |
| [Jensen](beds/jensen.md) | Go-to-position, variable massage (0-10), dynamic feature detection |
| [DewertOkin](beds/dewertokin.md) | 79 brands (many older Rize/Simmons models), multiple protocols |
| [Serta](beds/serta.md) | Massage intensity control, Zero-G/TV/Lounge |
| [Mattress Firm 900](beds/mattressfirm.md) | Older iFlex/Nordic UART bases, lumbar control, built-in presets |
| [Nectar](beds/nectar.md) | Lumbar control, massage, lights, Zero-G/Anti-Snore/Lounge |
| [Malouf/Lucid](beds/malouf.md) | Configurable 2/3/4-motor or Hi-Lo layout, 1-2 memory positions, massage, lights |
| [BedTech](beds/bedtech.md) | 5 presets, 4 massage modes, dual-base support |
| [Sleep Number](beds/sleep_number.md) | Fuzion and BAM/MCR: capability-dependent position, firmness, presets, lighting and thermal controls |
| [Sleepy's Elite](beds/sleepys.md) | BOX15/24/25 variants, presets, BOX25 position sliders including lumbar |
| [SleepSpa S9000AI](beds/sleepstar.md) | CB37 sleep monitor, five app-addressable actuators, position feedback, sonic massage, RGB lighting |
| [Svane](beds/svane.md) | LinonPI protocol, multi-service |
| [Vibradorm](beds/vibradorm.md) | Position feedback, 4 memory presets, lights |
| [SUTA Smart Home](beds/suta.md) | AT command protocol, 4 memory slots, discrete lights |
| [TiMOTION AHF](beds/timotion-ahf.md) | 5-motor bitmask protocol, toggle lights, AHF name detection |
| [Limoss](beds/limoss.md) | TEA-encrypted packets, position feedback, dynamic capability query |
| [Cool Base](beds/coolbase.md) | Keeson BaseI5 with fan control |
| [Scott Living](beds/scott-living.md) | 9-byte protocol |
| [SBI/Q-Plus](beds/sbi.md) | Position feedback via pulse lookup |
| [Rondure](beds/rondure.md) | 4 motors, split-king, massage, lights |
| [Remacro](beds/remacro.md) | 4 motors, 8 presets, RGB lights, heat |
| [Logicdata](beds/logicdata.md) | XXTEA encrypted, 2 memory slots, lights, massage |
| [LOGICDATA app profiles](beds/logicdata-app.md) | Phone/tablet layouts, standard/middle-motor controls, alarms and renaming |
| [Okin CB35](beds/okin-cb35.md) | 7-byte Nordic UART (Sealy Posturematic), 6 motors, massage, lights |
| [Okin CST](beds/okin-cst.md) | 14-byte dual-field protocol (Rize Sanctuary, Resident, Aviada, Bob, Contempo, II Carefree, II Clarity, MF900; Support; Mattress Firm 900-O / MFirm 900-O; Nectar Motion) |
| [OKIN Smart Remote / RF ECO BT](beds/okin-rf-eco-bt.md) | Single stair actuator for Elda BTH / MEGAMAT |
| [Okin DOT](beds/okin-dot.md) | Handset-specific motor, memory and light controls |
| [DewertOkin ELEVATE](beds/star-elevate.md) | Two-actuator lift accessory |

---

## Configuration

For detailed configuration options including motor pulse settings, protocol variants, and bed-specific settings, see the [Configuration Guide](CONFIGURATION.md).

---

## Okin Protocol Family

Retail brands and model numbers can appear in more than one row. Lucid L600,
for example, is confirmed with both OKIN CB24 7-byte controllers and legacy
Malouf/OKIN 9-byte controllers. Select or auto-detect the actuator protocol from
BLE evidence; never select a protocol from the retail model alone.

Several bed brands use Okin-based BLE controllers. While they share common roots, each uses a different command format or write method:

| Bed Type | Command Format | Write Method | Pairing Required | Detection |
|----------|---------------|--------------|------------------|-----------|
| [Okimat](beds/okimat.md) | 6-byte (32-bit cmd) | UUID `62741525-...` | ✅ Yes | Name patterns or fallback |
| [Okin 64-bit](beds/okin-64bit.md) | 10-byte (64-bit cmd) | Nordic UART or UUID | ❌ No | `NORA_CON` / `NORACON`, manual selection |
| [Leggett & Platt Okin](beds/leggett-platt.md) | 6-byte (32-bit cmd) | UUID `62741525-...` | ✅ Yes | `LP BED...` or Leggett name patterns |
| [Nectar](beds/nectar.md) | 7-byte (32-bit cmd) | UUID `62741525-...` without response | ❌ No | Name contains "nectar" or generic `OKIN-*` disambiguation |
| [DewertOkin](beds/dewertokin.md) | 6-byte (32-bit cmd) | UUID `62741525-...` | ❌ No | Name patterns |
| [Mattress Firm 900](beds/mattressfirm.md) | 7-byte (32-bit cmd) | Nordic UART | ❌ No | Name starts with "iflex" |
| [Malouf](beds/malouf.md) | 8-byte New OKIN / 9-byte Legacy OKIN | Nordic UART or FFE5 | ❌ No | Service UUID detection |
| [Keeson/Ergomotion](beds/keeson.md) | 8-byte (32-bit cmd) | Nordic UART | ❌ No | Name patterns |
| [Okin CB35](beds/okin-cb35.md) | 7-byte (1-byte cmd) | Nordic UART | ❌ No | Name starts with "Star35" |
| [Okin CST](beds/okin-cst.md) | 14-byte (dual 32-bit) | UUID `62741525-...` | ✅ Yes | Rize Sanctuary, Resident, Aviada, Bob, Contempo, II Carefree, II Clarity, MF900; Support; Mattress Firm 900-O / MFirm 900-O; Nectar Motion; some `OKIN-*` bases |
| [OKIN Smart Remote / RF ECO BT](beds/okin-rf-eco-bt.md) | 6-byte (32-bit cmd) | UUID `62741525-...` | Unknown | Manual selection; diagnostics can match CSS GATT signature |

**Key differences:**
- **6-byte vs 7-byte vs 8-byte vs 9-byte vs 10-byte vs 14-byte**: Different command structures - not interchangeable
- **32-bit vs 64-bit commands**: Okin 64-bit uses 8-byte command values instead of 4-byte
- **Characteristic handles vary**: Okin-family beds share stable UUIDs, but numeric
  handles differ by device/firmware and must not be hardcoded
- **Nordic UART**: Many newer beds use the Nordic UART service

**If auto-detection picks the wrong type:** Go to Settings → Devices & Services → Adjustable Bed → Configure and change the bed type.

**Shared identifiers:** Generic `OKIN-*` and receiver names can require a
protocol-selection prompt. An `OKIN-BLE` name alone does not distinguish
Malouf/Lucid from other OKIN controllers; service and manufacturer data matter.
Connected GATT and Device Information can further refine the result. For example,
the shared CSS endpoint can belong to a full bed or the single-actuator RF ECO BT
profile. Nordic DFU is only a hint, while model information can distinguish
`MEGAMAT MBZ` from `OKIMAT` hardware. See [Okimat detection](beds/okimat.md#detection)
for the current family-specific rules.

---

## Not Supported

### WiFi and Cloud-Based Beds

**[Won't be supported, read reasons here](https://github.com/kristofferR/ha-adjustable-bed/issues/167).** This is a Bluetooth-only integration. WiFi and cloud beds require fundamentally different architecture and would be better served by a separate integration.

Beds that won't be supported:
- **Sleeptracker AI** — Tempur-Pedic Ergo, BeautyRest SmartMotion, Serta Motion (cloud-connected models)
- **Logicdata eLift / desk controllers** — Uses local UDP/HTTP, not Bluetooth
- **ErgoWifi** — Uses Xlink cloud platform

LOGICDATA MOTIONrelax BLE app layouts have an explicit [LOGICDATA app profile](beds/logicdata-app.md). Existing legacy [Jiecang](beds/jiecang.md) entries retain their original protocol.

If you have one of these beds, consider running [smartbed-mqtt](https://github.com/richardhopton/smartbed-mqtt) as an add-on or make a separate integration for WiFi/Cloud adjustable beds.

### Other Integrations

These beds have their own dedicated integrations:
- **Eight Sleep** — Use the [Eight Sleep](https://github.com/lukas-clarke/eight_sleep) integration

---

## Identifying Your Bed Type

1. **Check if auto-discovery finds your bed**: Settings → Integrations → Add Integration → Adjustable Bed. If your bed appears in the list, the integration likely detected the correct type.

2. **Check the remote or controller** for brand markings.

3. **Look at the device name** (shown during manual setup or in diagnostics):
   - A name beginning with accepted `QMS-IQ`, `QMS-I06`, `QMS-LQ`, `QMS-L04`, `QMS-JQ-D`, `QMS4`, `QMS-NQ`, `QMS3`, `QMS-MQ`, `QMS2`, `My QMS2`, `SealyMF`, or exact `S4-Y-<digits>-<id>` → Solace/QMS 11-byte family
   - `HHC*` → MotoSleep
   - `DPG*` or `Desk*` → Linak
   - `Mouselet*` → Kaidi
   - `Nectar*` → Nectar
   - `Okimat*`, `Okin RF*` → Okimat/Okin candidates; verify the advertised services
   - `OKIN-Receiver`, `OKIN - Receiver` → prompted Okin-family protocol selection
   - `Leggett*`, `L&P*`, `Adjustable Base*` → Leggett & Platt
   - `Ergomotion*` or `Ergo*` → Keeson/Ergomotion
   - `KSBT03*` or `KSBT04*` → Keeson KSBT (includes some Ergomotion Sync beds such as Rio 6.0)
   - `Jiecang*`, `JC-*`, or `Glide*` → Jiecang
   - `Dewert*`, `A H Beard*`, `Hankook*` → DewertOkin
   - `Serta*` or `Motion Perfect*` → Serta
   - `Octo*` → Octo (Standard variant)
   - `iFlex*` → Mattress Firm 900
   - `OKIN-*` with service `62741523-...` plus CSS service `90311623-...` → [Okin CST](beds/okin-cst.md) or [OKIN Smart Remote / RF ECO BT](beds/okin-rf-eco-bt.md); Nordic DFU alone does not distinguish them
   - `Malouf*`, `Structures*` → Malouf
   - `Smart bed *` → [Sleep Number](beds/sleep_number.md) (Climate 360 / FlexFit, Fuzion)
   - MAC-address-like name such as `64:DB:A0:07:DD:02` + service `ffffd1fd-...` → [Sleep Number](beds/sleep_number.md) (i8 / 360 FlexFit 2, BAM/MCR)
   - `Sleepy*` → Sleepy's Elite (try BOX24 first, BOX15 if lumbar needed)
   - `SLEEPSTAR*` + Nordic UART → [SleepSpa S9000AI](beds/sleepstar.md); `SLEEPBT*` is intentionally rejected
   - `VMAT*` → Vibradorm
   - `SUTA-*` → SUTA Smart Home (bed-frame variants)
   - `AHF*` → TiMOTION AHF
   - `Limoss*`, `Stawett*` → Limoss
   - `OKIN-BLE*` → requires service/manufacturer data to distinguish [Malouf/Lucid](beds/malouf.md) from other OKIN-family profiles
   - `CheersSleep*`, `Jeromes*`, `Slumberland*`, `The Brick*` → Remacro
   - `Rize*` → Often [DewertOkin](beds/dewertokin.md), but `Mouselet*` devices are [Kaidi](beds/kaidi.md)
   - `Simmons*`, `Glory*`, `Symphony*` → See [DewertOkin](beds/dewertokin.md)
   - `Star35*` → [Okin CB35](beds/okin-cb35.md) (Sealy Posturematic)
   - `SILVERmotion*` or Logicdata manufacturer ID → [Logicdata](beds/logicdata.md)
   - `OKIN-*` with no advertised service UUIDs → manual setup; use diagnostics to check for [Okin CST](beds/okin-cst.md) or [OKIN Smart Remote / RF ECO BT](beds/okin-rf-eco-bt.md)

4. **Use the support bundle to find service UUIDs**: If unsure, use **Browse unsupported BLE devices** to find the MAC address, then run `adjustable_bed.generate_support_bundle` with `target_address`. The output includes service UUIDs:
   - Service `62741523-...` → Okin family (see [Okin Protocol Family](#okin-protocol-family))
   - Service `62741523-...` plus CSS service `90311623-...` and write characteristic `90311625-...` → [Okin CST](beds/okin-cst.md) or [OKIN Smart Remote / RF ECO BT](beds/okin-rf-eco-bt.md); Nordic DFU is only an initial CST hint. Device Information model `MEGAMAT MBZ` identifies RF ECO BT, while an `OKIMAT` model identifies a full bed. Otherwise the integration preserves an already configured CST or RF ECO BT profile.
   - Service `45e25100-...` → Leggett & Platt Gen2
   - Service `0000aa5c-...` → Octo Star2 variant
   - Service `01000001-...` → Malouf/Lucid family (usually New OKIN; `OKIN-BLE` + `BTCB` uses Legacy OKIN)
   - Service `0000ffe5-...` → Malouf (Legacy OKIN) or Keeson OKIN variant
   - Service `0000fff0-...` + name `SUTA-*` → SUTA Smart Home
   - Service `6e400001-...` + name `AHF*` → TiMOTION AHF
   - Service `0000fee9-...` → Richmat WiLinke or BedTech
   - Service `00001525-...` → Vibradorm
   - A name beginning with an accepted QMS or SealyMF prefix listed above, or exact `S4-Y-<digits>-<id>` → Solace/QMS; accepted apps discover FFE1 dynamically and do not require advertised FFE0
   - Service `6e403587-...` → Remacro
   - Service `09d23fae-...` → [Sleep Number](beds/sleep_number.md) (Climate 360 / FlexFit, Fuzion)
   - Service `ffffd1fd-...` → [Sleep Number](beds/sleep_number.md) (i8 / 360 FlexFit 2, BAM/MCR)
   - Service `0000ffc0-...` or `9e5d1e47-...` + name `Mouselet*` → Kaidi
   - Service `b9934c43-...` → Logicdata SimplicityFrame

5. **Fallback**: If the device isn't visible to Home Assistant at all, use [nRF Connect](https://www.nordicsemi.com/Products/Development-tools/nRF-Connect-for-mobile) on your phone to verify it exists and check the service UUIDs.

If your bed isn't auto-detected, use manual configuration with the matching protocol guide. Capture a support bundle when the controller is ambiguous.

---

## Credits

This integration relies heavily on protocol research from the [smartbed-mqtt](https://github.com/richardhopton/smartbed-mqtt) project by [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt), which documented BLE protocols for many adjustable bed brands.

Community contributors who helped reverse-engineer specific protocols:

| Protocol | Contributors |
|----------|-------------|
| Richmat | [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt), getrav, [kristofferR](https://github.com/kristofferR) |
| Linak | [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt), jascdk |
| Solace | [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt), Bonopaws, [kristofferR](https://github.com/kristofferR) |
| MotoSleep | [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt), waynebowie99 |
| Reverie | [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt), Vitaliy, [kristofferR](https://github.com/kristofferR) |
| Leggett & Platt | [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt), MarcusW |
| Okimat | [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt), david_nagy, corne, PT, [kristofferR](https://github.com/kristofferR) |
| Keeson/Ergomotion | [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt), [kristofferR](https://github.com/kristofferR) |
| Octo | [Richard Hopton](https://github.com/richardhopton/smartbed-mqtt), _pm, goedh452, Murp, Brokkert, [kristofferR](https://github.com/kristofferR) |
| Jiecang | [kristofferR](https://github.com/kristofferR) |
| Serta | [kristofferR](https://github.com/kristofferR) |
| Malouf | [kristofferR](https://github.com/kristofferR) |
| BedTech | [kristofferR](https://github.com/kristofferR) |
| Okin 64-bit | [kristofferR](https://github.com/kristofferR) |
| Sleepy's Elite | [kristofferR](https://github.com/kristofferR) |
| SleepSpa S9000AI | [kristofferR](https://github.com/kristofferR) |
| Jensen | [kristofferR](https://github.com/kristofferR) |
| Svane | [kristofferR](https://github.com/kristofferR) |
| Vibradorm | [kristofferR](https://github.com/kristofferR) |
| SUTA Smart Home | [kristofferR](https://github.com/kristofferR) |
| TiMOTION AHF | [kristofferR](https://github.com/kristofferR) |
| Mattress Firm 900 | [David Delahoz](https://github.com/daviddelahoz/BLEAdjustableBase) |
| Nectar | [MaximumWorf](https://github.com/MaximumWorf/homeassistant-nectar) |
