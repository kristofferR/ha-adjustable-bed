# Supported Actuators

This document provides an overview of supported bed brands. Click on a brand name for detailed protocol information and command references.

## Supported Beds

| Brand | Status | Key Features |
|-------|--------|--------------|
| [Linak](beds/linak.md) | ✅ Tested | Position feedback, 4 memory presets, massage, lights |
| [Richmat](beds/richmat.md) | ❓ Untested | 2 memory presets, massage, lights, Zero-G |
| [Keeson](beds/keeson.md) | ✅ Tested | Position feedback (Ergomotion), 4 presets, massage, lights |
| [Solace](beds/solace.md) | ❓ Untested | 5 memory presets, lift/tilt, Zero-G |
| [MotoSleep](beds/motosleep.md) | 🔄 Works | 2 memory presets, massage, lights, Zero-G |
| [Leggett & Platt](beds/leggett-platt.md) | ❓ Untested | 4 memory presets, massage (0-10), RGB lighting |
| [Reverie](beds/reverie.md) | ❓ Untested | Position control (0-100%), 4 presets, wave massage |
| [Okimat/Okin](beds/okimat.md) | ❓ Untested | 4 memory presets, massage, lights (requires pairing) |
| [Jiecang](beds/jiecang.md) | ❓ Untested | Presets only (no direct motor), 2 memory slots |
| [DewertOkin](beds/dewertokin.md) | ❓ Untested | 2 memory presets, wave massage, lights |
| [Serta](beds/serta.md) | ❓ Untested | Massage intensity control, Zero-G/TV/Lounge |
| [Octo](beds/octo.md) | ❓ Untested | Two protocol variants, optional PIN auth, lights |
| [Mattress Firm 900](beds/mattressfirm.md) | ❓ Untested | Lumbar control, 3-level massage, built-in presets |
| [Nectar](beds/nectar.md) | ❓ Untested | Lumbar control, massage, lights, Zero-G/Anti-Snore/Lounge |

### Status Legend

- ✅ **Tested** - Confirmed working by community members
- 🔄 **Works** - Working but may have improvements in progress
- ❓ **Untested** - Implemented based on protocol documentation, needs testing

---

## Configuration

For detailed configuration options including motor pulse settings, protocol variants, and bed-specific settings, see the [Configuration Guide](CONFIGURATION.md).

---

## Okin Protocol Family

Multiple bed brands use controllers based on OKIN technology (now part of DewertOkin GmbH). These beds share similar protocols and sometimes even the same BLE service UUID, which can cause detection ambiguity.

### Beds Using OKIN Service UUID (`62741523-...`)

| Bed Type | Command Format | Detection Method |
|----------|---------------|------------------|
| [Okimat](beds/okimat.md) | 6-byte binary | Name patterns or fallback |
| [Leggett & Platt Okin](beds/leggett-platt.md) | 6-byte binary | Name patterns |
| [Nectar](beds/nectar.md) | 7-byte binary | Name contains "nectar" |

### Beds Using OKIN Protocol with Different UUIDs

| Bed Type | Write Method | Detection Method |
|----------|-------------|------------------|
| [DewertOkin](beds/dewertokin.md) | Handle 0x0013 | Name patterns |
| [Leggett & Platt Gen2](beds/leggett-platt.md) | UUID `45e25100-...` | Service UUID |

**If auto-detection fails:** These beds can be manually configured. If your bed uses the OKIN service UUID but is detected as the wrong type, change the bed type in the integration settings.

---

## Not Yet Supported

### Sleeptracker AI (Cloud-based)
- Tempur-Pedic Ergo series (cloud-connected models)
- Beautyrest SmartMotion (cloud-connected models)
- Serta Motion series (cloud-connected models)

**Reason:** Requires cloud API, not local BLE control.

### Logicdata (Local Network)
- Tempur-Pedic beds with Logicdata controllers
- Uses local UDP/HTTP protocol, not BLE

### ErgoWifi (Cloud-based)
- Beds using Xlink cloud platform
- Requires Chinese cloud API authentication

### Eight Sleep
Will not be implemented. Use the [Eight Sleep](https://github.com/lukas-clarke/eight_sleep) integration instead.

### Sleep Number
Will not be implemented. Use the [SleepIQ](https://www.home-assistant.io/integrations/sleepiq/) integration instead.

---

## Identifying Your Bed Type

1. **Check the remote or controller** for brand markings
2. **Scan for BLE devices** using nRF Connect app
3. **Look at device names:**
   - `HHC*` → MotoSleep
   - `DPG*` or `Desk*` → Linak
   - `Nectar*` → Nectar
   - `Okimat*`, `Okin RF*`, `Okin BLE*` → Okimat
   - `Leggett*`, `L&P*`, `Adjustable Base*` → Leggett & Platt
   - `Ergomotion*` or `Ergo*` → Ergomotion (use Keeson)
   - `Jiecang*`, `JC-*`, or `Glide*` → Jiecang
   - `Dewert*`, `A H Beard*`, or `Hankook*` → DewertOkin
   - `Serta*` or `Motion Perfect*` → Serta
   - `Octo*` → Octo (Standard variant)
   - `iFlex*` → Mattress Firm 900
4. **Check service UUIDs** (using nRF Connect):
   - Service `62741523-...` → Okin family (see [Okin Protocol Family](#okin-protocol-family))
   - Service `45e25100-...` → Leggett & Platt Gen2
   - Service `0000aa5c-...` → Octo Star2 variant

If your bed isn't auto-detected, use manual configuration and try different bed types.
