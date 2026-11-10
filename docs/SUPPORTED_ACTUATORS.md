# Supported Actuators

Find your controller, compare its features, and follow the linked setup guide.
Related apps and remote layouts are grouped with their manufacturer.
The [README Supported Beds table](../README.md#supported-beds) is the canonical
support index. Each linked guide records model-specific evidence and hardware
validation limits; the feature summaries below depend on the selected controller.

| Brand | Key Features |
|-------|--------------|
| [Linak](beds/linak.md) | Auto-detected models, up to 5 axes, 0/4 memories, speed/status/errors, massage, alarms, lights |
| [Keeson](beds/keeson.md) | Position feedback (Ergomotion), presets, massage, lights; [Adjustable Lite](beds/keeson.md#adjustable-lite-profile), [Simon Li / Heal Every Night / OKIN-Seating](beds/keeson.md#simon-li-heal-every-night-and-okin-seating-profiles), [INNOVA](beds/keeson.md#innova-profile), [MaxCoil / Dynasty / Bedsense](beds/keeson.md#ore-comfort-bed-profiles), [Restonic BT](beds/keeson.md#restonic-bt-profiles) |
| [Richmat](beds/richmat.md) | Model-dependent motors, memory, massage, lighting, alarms and reported state; [RMControl](beds/richmat.md#rmcontrol), [Revive Control / Best Mattress / Blvd Home / HARMONY / Idealbed](beds/richmat.md#richmat-mh-apps) |
| [MotoSleep](beds/motomotion.md#motosleep-and-power-bob-family) | Model-dependent HHC/MOTO controls, memory, massage and lighting |
| [OCTO Smart Control](beds/octo.md) | Standard OCTO capability-advertised motor, memory, light and setting controls; separate Star2 variant. Hardware validation is deferred |
| [Solace](beds/ff_frame.md#solace-name-routes) | Name-based profiles, named presets, optional massage/lights, exact S4-Y lift/tilt; explicit [Woosa Sleep](beds/ff_frame.md#woosa-sleep) profile with one Favourite memory |
| [Leggett & Platt](beds/leggett-platt.md) | Gen2 motor control and RGB lighting; Okin tilt/lumbar and massage; [Prodigy / U Series](beds/okin-nframe.md#leggett-okin-family) layouts and timers, [L&P legacy](beds/richmat.md#lp-legacy-app) model settings |
| [Reverie](beds/reverie.md) | Position control (0-100%), 4 presets, wave massage |
| [Okimat/Okin](beds/okin-nframe.md#okimat) | 4 memory presets, massage, lights (requires pairing) |
| [Okin 64-Bit](beds/okin-nframe.md#okin-64-bit) | 10-byte Nordic/custom OKIN protocol, lumbar, lights, massage |
| [Glideaway Motion / Montion app](beds/keeson.md#glideaway-motion) | Manual 400/450/500/600 layouts, two memories, clock/alarm, model-gated massage/light; hardware unverified |
| [Jiecang](beds/jiecang.md) | Motor control, memory, massage, split beds; [ERGOBALANCE / Dream Motion](beds/jiecang.md#dream-app-family) layouts, alarms, wake routines and renaming; [Comfort Motion app](beds/jiecang.md#comfort-motion-app) |
| [Kaidi](beds/kaidi.md) | Mouselet-based beds, Flat/Zero-G/Anti-Snore, 4 memory slots |
| [Jensen](beds/jensen.md) | Go-to-position, massage/light/fan levels (0-10), app-stored memories, dynamic feature detection |
| [DewertOkin](beds/okin-nframe.md#dewertokin) | 79 brands (many older Rize/Simmons models), multiple protocols |
| [Serta](beds/keeson.md#serta) | Keeson Serta profile: Flat, Zero-G, memory slots, massage steps, lights |
| [Mattress Firm 900](beds/okin-5a.md#mattress-firm-900--iflex) | Older iFlex/Nordic UART bases, lumbar control, built-in presets |
| [Nectar](beds/okin-5a.md#nectar) | Lumbar control, massage, lights, Zero-G/Anti-Snore/Lounge |
| [Malouf/Lucid](beds/malouf.md) | Model-dependent motor layout, memory, massage and lights; [Malouf Base / Lucid Base](beds/malouf.md#malouf-base--lucid-base-family) model and transport selection |
| [BedTech](beds/richmat.md#bedtech) | 5 presets, 4 massage modes; the app's dual-base frames are documented, not sent |
| [Sleep Number](beds/sleep_number.md) | Fuzion and BAM/MCR: capability-dependent position, firmness, presets, lighting and thermal controls |
| [Sleepy's Elite](beds/sleepys.md) | BOX15/24/25 variants, presets, BOX25 position sliders including lumbar |
| [AdjustableM5X4](beds/okin-nframe.md#adjustablem5x4) / [AdjustableM5X5](beds/starcode-m5x5.md) apps | StarCode Star-name beds: M5X4 command and transport selectors; M5X5 CB25/F23/kneading layouts and up to three [ELEVATE](beds/okin-5a.md#dewertokin-elevate) lift entries |
| [Adjustable Comfort M1X12 app](beds/starcode-m1x12.md) | Explicit CB25/F23/kneading profile, opaque Part selectors with state feedback, and up to two separately configured M1X12 ELEVATE entries |
| [SleepSpa S9000AI](beds/sleepstar.md) | CB37 sleep monitor, five app-addressable actuators, position feedback, sonic massage, RGB lighting |
| [Svane](beds/svane.md) | Svane Remote multi-service / JMC400 profiles, opaque software memories, local lamp preference; separate Jensen LinOn |
| [Vibradorm](beds/vibradorm.md) | Position feedback, memory and lights; [Caresse / Werkmeister](beds/vibradorm.md#caresse-and-werkmeister), [VMAT](beds/vibradorm.md#vmat) and [V-MAT Basic](beds/vibradorm.md#v-mat-basic) remote-specific controls |
| [SUTA Smart Home](beds/suta.md) | AT command protocol, 4 memory slots, discrete lights |
| [TiMOTION AHF](beds/timotion-ahf.md) | Fixed app-labelled controls, raw lock/lamp diagnostics, AHF name detection; physical behavior unverified |
| [BedJet PowerLayer](beds/bedjet-powerlayer.md) | Head/foot movement, 4 presets, 3 memory recalls, calibrated degree feedback (frame only, not the BedJet climate unit) |
| [Limoss](beds/limoss.md) | TEA-encrypted packets, position feedback, dynamic capabilities; [Limoss Remote](beds/limoss.md#limoss-remote) and [FSM Relax](beds/limoss.md#fsm-relax) bed/chair layouts and local memories |
| [Motion Bed app](beds/ff_frame.md#motion-bed) | Layouts chosen by the app's Bluetooth name, named presets, massage, lighting, sync, audio and sleep controls, module selection |
| [Cool Base](beds/keeson.md#cool-base) | Keeson BaseI5 with fan control |
| [Scott Living](beds/keeson.md#scott-living) | 9-byte protocol |
| [SBI/Q-Plus](beds/keeson.md#sbi--q-plus-costco) | Position feedback via pulse lookup |
| [Rondure](beds/keeson.md#rondure) | 4 motors, split-king, massage, lights |
| [Remacro](beds/remacro.md) | Slumberland, The Brick and Jerome's app screens: up to 3 motors, split sides, presets, memory, massage, light |
| [Logicdata](beds/logicdata.md) | SILVERmotion / SimplicityFrame memory, lights and massage; [MOTIONrelax](beds/jiecang.md#motionrelax-phone-and-tablet) layouts and alarms; [Sleep Smart](beds/jiecang.md#sleep-smart-air-mattress-bed) bed controls and separate [air mattress pump](beds/logicdata-sleep-smart.md) |
| [Okin CB35](beds/okin-5a.md#sealy-posturematic-cb35) | 7-byte Nordic UART (Sealy Posturematic), 6 motors, massage, lights |
| [Customatic](beds/okin-nframe.md#customatic-family) | Clarity, Jerome's C and Remedy apps: back and legs (Remedy adds lumbar), memory page, light toggle |
| [Customatic Z-Series](beds/okin-nframe.md#customatic-z-series), [Jordan's Serenity](beds/okin-nframe.md#jordans-serenity), [Jordan's Tranquil](beds/okin-nframe.md#jordans-tranquil) | OKIN CST 14-byte apps: head/foot and selector controls, presets, saved positions, massage; Z-230/Z-280 pages |
| [SIMMONS](beds/okin-nframe.md#simmons) / [Adjustable bed (Lumbar)](beds/okin-nframe.md#adjustable-bed-lumbar) apps | OKIN apps whose command table follows the Bluetooth name: regular or inclined SIMMONS beds; head, foot and lumbar |
| [Okin CST](beds/okin-nframe.md#okin-cst) | 14-byte dual-field protocol (Rize Sanctuary, Resident, Aviada, Bob, Contempo, II Carefree, II Clarity, MF900; Support; Mattress Firm 900-O / MFirm 900-O; explicit Nectar Move app profile) |
| [FurniMove / OKIN Smart Remote app](beds/furnimove.md) | Explicit handset layouts from production API tables; RF, ordinary and DOT transports |
| [OKIN Smart Remote / RF ECO BT](beds/okin-nframe.md#rf-eco-bt-stair-lift) | Single stair actuator for Elda BTH / MEGAMAT |
| [Okin DOT](beds/okin-nframe.md#okin-dot) | Handset-specific motor, memory and light controls (RF34/RF6707; new RF1058 setups use FurniMove) |
| [DewertOkin ELEVATE](beds/okin-5a.md#dewertokin-elevate) | Two-actuator lift accessory |

---

## Configuration

For detailed configuration options including motor pulse settings, protocol variants, and bed-specific settings, see the [Configuration Guide](CONFIGURATION.md).

---

## Wire codecs

Many apps and brands send the same wire format. Each shared format is encoded
once, as a codec, and each app or legacy route is a profile over it. A codec
guide documents the format once, then has one section per profile. The
[codec and profile architecture](design/protocol-codecs.md) explains the split.

| Codec | Guide | Profiles for |
|-------|-------|--------------|
| Jiecang F1 | [Jiecang](beds/jiecang.md) | Jiecang legacy and Comfort Motion routes; ERGOBALANCE, Dream Motion, Dream Motion HD and Comfort Motion apps; LOGICDATA MOTIONrelax and Sleep Smart apps |
| Keeson E5/E6 | [Keeson](beds/keeson.md) | Keeson variants and the Ergomotion, Serta and OKIN FFE bed types; Tempur Curve, Q-Plus, Serta MP Remote, Omazz, Ergomotion, ROW Control, Ergo Slim, TEMPUR AU and [Ergomotion 4.0](beds/keeson.md#ergomotion-40) apps; Glideaway Motion, AdjustaMattress, Malouf legacy OKIN, Sleepy's BOX15, Scott Living, SBI, Rondure, Cool Base, BF, Cherish and Comfort Enhancements |
| Okin N-frame | [Okin N-frame](beds/okin-nframe.md) | Okimat, DewertOkin, Okin CB24, Okin CST, Okin DOT, RF ECO BT, Leggett & Platt Okin, Customatic, Jordan's, SIMMONS, OKIN SleepEase, Sleepy's BOX25 legacy, AdjustableM5X4, Okin 64-Bit and Adjustable bed (Lumbar) |
| Okin 5A | [Okin 5A](beds/okin-5a.md) | Nectar, Mattress Firm 900 / iFlex, Okin CB35, DewertOkin ELEVATE and the Sleepy's BOX25 Star route |
| Malouf | [Malouf](beds/malouf.md) | Malouf New OKIN and the Malouf Base / Lucid Base apps |
| Richmat 6E | [Richmat](beds/richmat.md) | Richmat remotes, RMControl, BedTech, L&P MlRM, the five Richmat MH apps and HJBed |
| Limoss DD | [Limoss](beds/limoss.md) | Limoss, Limoss Remote and FSM Relax |
| FFFF frame | [FFFF frame](beds/ff_frame.md) | Solace, Woosa Sleep, BedSense and Motion Bed |

Beds with a wire format of their own, such as Linak, OCTO, Reverie, Sleep Number
or Vibradorm, have their own guide, linked from the table above and from the
[README Supported Beds table](../README.md#supported-beds). FurniMove and GM
Control build their frames with the Keeson and Richmat codecs, but keep their
own guides because their controls come from runtime handset and product
catalogs.

---

## Okin Protocol Family

Retail brands and model numbers can appear in more than one row. Lucid L600,
for example, is confirmed with both OKIN CB24 7-byte controllers and legacy
Malouf/OKIN 9-byte controllers. Select or auto-detect the actuator protocol from
BLE evidence; never select a protocol from the retail model alone.

Several bed brands use Okin-based BLE controllers. While they share common roots, each uses a different command format or write method:

| Bed Type | Codec | Command Format | Write Method | Pairing Required | Detection |
|----------|-------|---------------|--------------|------------------|-----------|
| [Okimat](beds/okin-nframe.md#okimat) | Okin N-frame | 6-byte (32-bit cmd) | UUID `62741525-...` | ✅ Yes | Name patterns or fallback |
| [Okin 64-bit](beds/okin-nframe.md#okin-64-bit) | Okin N-frame | 10-byte (64-bit cmd) | Nordic UART or UUID | ❌ No | `NORA_CON` / `NORACON`, manual selection |
| [Leggett & Platt Okin](beds/leggett-platt.md) | Okin N-frame | 6-byte (32-bit cmd) | UUID `62741525-...` | ✅ Yes | `LP BED...` or Leggett name patterns |
| [Nectar](beds/okin-5a.md#nectar) | Okin 5A | 7-byte (32-bit cmd) | UUID `62741525-...` without response | ❌ No | Name contains "nectar" or generic `OKIN-*` disambiguation |
| [DewertOkin](beds/okin-nframe.md#dewertokin) | Okin N-frame | 6-byte (32-bit cmd) | UUID `62741525-...` | ❌ No | Name patterns |
| [Mattress Firm 900](beds/okin-5a.md#mattress-firm-900--iflex) | Okin 5A | 7-byte (32-bit cmd) | Nordic UART | ❌ No | Name starts with "iflex" |
| [Malouf](beds/malouf.md) | Malouf (New OKIN); Keeson E5/E6 (Legacy OKIN) | 8-byte New OKIN / 9-byte Legacy OKIN | Nordic UART or FFE5 | ❌ No | Service UUID detection |
| [Keeson/Ergomotion](beds/keeson.md) | Keeson E5/E6 | 8-byte (32-bit cmd) | Nordic UART | ❌ No | Name patterns |
| [Okin CB35](beds/okin-5a.md#sealy-posturematic-cb35) | Okin 5A | 7-byte (1-byte cmd) | Nordic UART | ❌ No | Name starts with "Star35" |
| [Okin CST](beds/okin-nframe.md#okin-cst) | Okin N-frame | 14-byte (dual 32-bit) | UUID `62741525-...` | Most profiles | Rize Sanctuary, Resident, Aviada, Bob, Contempo, II Carefree, II Clarity, MF900; Support; Mattress Firm 900-O / MFirm 900-O; explicit Nectar Move app profile; some `OKIN-*` bases |
| [OKIN Smart Remote / RF ECO BT](beds/okin-nframe.md#rf-eco-bt-stair-lift) | Okin N-frame | 6-byte (32-bit cmd) | UUID `62741525-...` | Unknown | Manual selection; diagnostics can match CSS GATT signature |

**Key differences:**
- **6-byte vs 7-byte vs 8-byte vs 9-byte vs 10-byte vs 14-byte**: Different command structures - not interchangeable
- **32-bit vs 64-bit commands**: Okin 64-bit uses 8-byte command values instead of 4-byte
- **Characteristic handles vary**: Okin-family beds share stable UUIDs, but numeric
  handles differ by device/firmware and must not be hardcoded
- **Nordic UART**: Many newer beds use the Nordic UART service

**If auto-detection picks the wrong type:** Go to Settings → Devices & Services → Adjustable Bed → Configure and change the bed type. To move between the Okin family's own routes (FurniMove, Okimat or Okin UUID, DOT and RF ECO BT), use **Reconfigure** in the entry's three-dot menu instead; Configure refuses that change (see [Okin setup](beds/okin-nframe.md#home-assistant-setup)).

**Shared identifiers:** Generic `OKIN-*` and receiver names can require a
protocol-selection prompt. An `OKIN-BLE` name alone does not distinguish
Malouf/Lucid from other OKIN controllers; service and manufacturer data matter.
Connected GATT and Device Information can further refine the result. For example,
the shared CSS endpoint can belong to a full bed or the single-actuator RF ECO BT
profile. Nordic DFU is only a hint, while model information can distinguish
`MEGAMAT MBZ` from `OKIMAT` hardware. See [Okimat detection](beds/okin-nframe.md#okimat)
for the current family-specific rules.

---

## Not Supported

### WiFi and Cloud-Based Beds

**[Won't be supported, read reasons here](https://github.com/kristofferR/ha-adjustable-bed/issues/167).** This is a Bluetooth-only integration. WiFi and cloud beds require fundamentally different architecture and would be better served by a separate integration.

Beds that won't be supported:
- **Sleeptracker-AI cloud features**: accounts, sleep data, Wi-Fi setup and other cloud services of Tempur-Pedic Ergo, BeautyRest SmartMotion and Serta Motion bases. The Tempur Sleeptracker-AI processor's direct Bluetooth controls on TEMPUR-Ergo ProSmart / ProSmart Air and ActiveBreeze beds are supported; see the [Sleeptracker processor guide](beds/sleeptracker.md)
- **Logicdata eLift / desk controllers** — Uses local UDP/HTTP, not Bluetooth
- **ErgoWifi** — Uses Xlink cloud platform
- **Layla Adjustable Base Remote** (`com.sbi.laylawf`, version 1.1.5): Bed
  controls use Xlink over local Wi-Fi (UDP) or cloud (TCP), outside this
  Bluetooth-only integration's scope. This exclusion is specific to this app
  version; other Layla controllers require separate Bluetooth evidence.

LOGICDATA MOTIONrelax BLE app layouts have an explicit [LOGICDATA app profile](beds/jiecang.md#motionrelax-phone-and-tablet) over the Jiecang codec; the Sleep Smart Air Mattress app has its own [bed profile](beds/jiecang.md#sleep-smart-air-mattress-bed) and [pump type](beds/logicdata-sleep-smart.md). Existing legacy [Jiecang](beds/jiecang.md#legacy-route) entries retain their original protocol.

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
   - `OKIN-*` with service `62741523-...` plus CSS service `90311623-...` → [Okin CST](beds/okin-nframe.md#okin-cst) or [OKIN Smart Remote / RF ECO BT](beds/okin-nframe.md#rf-eco-bt-stair-lift); Nordic DFU alone does not distinguish them
   - `Malouf*`, `Structures*` → Malouf
   - `Smart bed *` → [Sleep Number](beds/sleep_number.md) (Climate 360 / FlexFit, Fuzion)
   - MAC-address-like name such as `64:DB:A0:07:DD:02` + service `ffffd1fd-...` → [Sleep Number](beds/sleep_number.md) (i8 / 360 FlexFit 2, BAM/MCR)
   - `Sleepy*` or `MFRM*` → [Sleepy's Elite](beds/sleepys.md#home-assistant-setup); setup asks for the app or the receiver the bed advertises
   - `SLEEPSTAR*` + Nordic UART → [SleepSpa S9000AI](beds/sleepstar.md); `SLEEPBT*` is intentionally rejected
   - `VMAT*` → Vibradorm
   - `SUTA-*` → SUTA Smart Home (bed-frame variants)
   - `AHF*` → TiMOTION AHF
   - `Limoss*`, `Stawett*` → Limoss
   - `OKIN-BLE*` → requires service/manufacturer data to distinguish [Malouf/Lucid](beds/malouf.md) from other OKIN-family profiles
   - `Rize*` → Often [DewertOkin](beds/okin-nframe.md#dewertokin), but `Mouselet*` devices are [Kaidi](beds/kaidi.md)
   - `Simmons*`, `Glory*`, `Symphony*` → See [DewertOkin](beds/okin-nframe.md#dewertokin); beds using the `com.okin.simmons` app → [SIMMONS app](beds/okin-nframe.md#simmons)
   - `Star35*` → [Okin CB35](beds/okin-5a.md#sealy-posturematic-cb35) (Sealy Posturematic)
   - `SILVERmotion*` or Logicdata manufacturer ID → [Logicdata](beds/logicdata.md)
   - `OKIN-*` with no advertised service UUIDs → manual setup; use diagnostics to check for [Okin CST](beds/okin-nframe.md#okin-cst) or [OKIN Smart Remote / RF ECO BT](beds/okin-nframe.md#rf-eco-bt-stair-lift)

4. **Use the support bundle to find service UUIDs**: If unsure, use **Browse unsupported BLE devices** to find the MAC address, then run `adjustable_bed.generate_support_bundle` with `target_address`. The output includes service UUIDs:
   - Service `62741523-...` → Okin family (see [Okin Protocol Family](#okin-protocol-family))
   - Service `62741523-...` plus CSS service `90311623-...` and write characteristic `90311625-...` → [Okin CST](beds/okin-nframe.md#okin-cst) or [OKIN Smart Remote / RF ECO BT](beds/okin-nframe.md#rf-eco-bt-stair-lift); Nordic DFU is only a hint; CST is never selected automatically (#555). Device Information model `MEGAMAT MBZ` identifies RF ECO BT, while an `OKIMAT` model identifies a full bed. Shared receiver/GATT identity alone cannot select a handset. FurniMove beds use its [explicit app profile](beds/furnimove.md), and unconfirmed legacy RF ECO BT entries receive a layout repair.
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
| BedJet PowerLayer | [natekspencer](https://github.com/natekspencer/ha-bedjet) and [Tim-GitHub](https://github.com/Tim-GitHub) |
| Mattress Firm 900 | [David Delahoz](https://github.com/daviddelahoz/BLEAdjustableBase) |
| Nectar | [MaximumWorf](https://github.com/MaximumWorf/homeassistant-nectar) |
