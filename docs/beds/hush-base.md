# Hush Base

**Status:** ❓ Needs testing (artifact verified; hardware unverified)

**Credit:** Reverse engineering by [kristofferR](https://github.com/kristofferR/ha-adjustable-bed)

## Known Models

- L200, L300, L300SH, L400, L400SH, L500, S175, S175SH, S375, S375SH, S575 and S575SH.
- Additional stored profiles are explicit restoration choices, not discoveries of Hush hardware.
- Separate RM-/MM and HJ-/SXB sleep modules, plus the RCRM handset finder.

## Apps

| Analyzed | App | Package ID |
|----------|-----|------------|
| ✅ | [Hush Base](https://play.google.com/store/apps/details?id=com.richmat.hushbase) 1.0.5 (10501) | `com.richmat.hushbase` |

## Features

| Feature | Supported |
|---------|-----------|
| Motor Control | ✅ Product-specific back, legs, pillow, lumbar, combined and third motor |
| Position Feedback | Raw index/angle/height events only, no inferred physical axis |
| Memory Presets | ✅ Product-specific recall and explicit save commands |
| Massage | ✅ Exact product zones, modes and timers |
| Lights | ✅ RGB strip for lighting-flag profiles; plain color/timer otherwise |
| Alarms | ✅ Single; repeating only on restored profiles with that capability |
| Fan and heating | ✅ Exact restored-profile memberships |
| Music | ✅ Restored music profiles and reported music capability |
| Sleep sensor | ✅ Independent BLE live data, parts, reports, information and SXB settings |
| Split sides | ✅ Explicit side-capable profile and verified non-Nordic transport |

## Protocol Details

Hush Base beds speak the [Richmat 6E](richmat.md) wire format. The
[Casper and Hush family](richmat.md#casper-and-hush-family) and its
[Hush Base profile](richmat.md#hush-base) give the transports, the session
setup, every frame and catalog code this route sends, the notifications and the
timing. Each model is a profile in
[`profiles/hush.py`](../../custom_components/adjustable_bed/profiles/hush.py).

### Sleep transport

Sleep service whitelist: `0000e0ff-3c17-d293-8e48-14fe2e4da212` and
`2320567c-05cf-6eb4-c341-772851827e1b`. MM selects write-without-response and notify properties; SXB uses write `00000002-3c17-d293-8e48-14fe2e4da212` and notify `00000003-3c17-d293-8e48-14fe2e4da212`.
Frames contain the 14-byte envelope, sequence and compact ordered JSON, built by Casper Base's sensor builders over `codec/sleep_envelope.py` and split at negotiated MTU minus three. Each HA entry owns one physical target, its parser, sequence, callbacks and live intent.

## Detection / Setup

1. Choose **Hush Base app (select product)** in the app list, then the exact model on the profile setup step; the app's own twelve come first. There is no automatic Hush profile selection from an app name or shared UUID.
2. The twelve models above are fresh Hush setup choices. Labels marked **restored profile** represent the app's wider saved-index domain, not additional fresh Hush setup models.
3. Enabling native Left/Right controls (Configure → Enable Left / Right / Both controls) connects to the bed to read its transport. Nordic has no side byte; one-address pairing is rejected there. Two-address pairs keep independent profile and connection ownership.
4. Add a separate **Hush Base sleep sensor** entry for each sensor. Choose RM/MM or HJ/SXB explicitly. Sensor partitions and actuator sides are different concepts.
5. Add **Hush Base remote finder (RCRM handset)** to connect to the handset (see [Remote finder](#remote-finder)).

### Remote finder

The **Hush Base remote finder (RCRM handset)** entry only connects to the
handset. There is no locator packet.

## Commands

The selected product gates its catalog actions; entries with the same label can
have different codes. Every motor operation finishes with STOP on the same side
and connection. The [Hush Base profile](richmat.md#hush-base) lists every code.

### Configuration actions

Use `adjustable_bed.hush_base` with a `device_id` and `operation`. All targets validate before writes. The standard covers/buttons and card expose product controls.

| Operation | Behavior |
|-----------|----------|
| `light_rgb` | Ordinary light colour, `rgb_color` |
| `light_seconds` | Ordinary light duration in seconds; zero is always on |
| `light_off` | Ordinary light off |
| `rgb_color`, `rgb_power` | RGB strip colour, or power |
| `rgb_timer` | RGB strip timer in minutes; choices 5,8,10,13,15,18,21,24,27,30,120,210,300,390,480 |
| `rgb_mode`, `rgb_groove`, `rgb_breathe` | RGB colour mode, groove mode, or breathe |
| `alarm`, `alarm_cancel` | Single alarm at the next local `hour`:`minute`, recalling `mode`; or cancel it |
| `repeat_alarm` | Repeating alarm `slot` with `hour`, `minute`, `mode`, `days` and `enabled` |
| `repeat_delete`, `repeat_query` | Delete a repeating alarm `slot`, or request the list |
| `time_sync` | Send Home Assistant's local calendar time |
| `sleep_name` | Request the sleep module's advertised name |
| `snore_detector` | Explicit external status source; five positive 3-second samples recall anti-snore on side 0; zero resets |

The [Casper and Hush family](richmat.md#casper-and-hush-family) lists the frame
each operation sends; Hush sends a single alarm's low frame first (see the
[Hush Base profile](richmat.md#hush-base)).

### Independent sleep actions

| Operation | JSON command / value |
|-----------|----------------------|
| `sensor_time` | `s_time`, timestamp plus MM timezone name or SXB whole-hour UTC offset |
| `sensor_query_time` | SXB `q_time`, null |
| `sensor_part`, `sensor_query_part` | `s_part` with MM 1/2 or SXB 11/12/13; MM query uses `s_part` null, SXB `q_part` null |
| `sensor_live`, `sensor_stop` | `q_realtime` `{type:0,time:1}`; stopping cancels local work, no invented bed STOP |
| `sensor_report` | `q_report` date/type/part, then report permission after one second; report parts MM 1/2/3, SXB 1/2 |
| `sensor_sensitivity` | SXB `q_sens` null; first value per side truncated minus one, without clamp |
| `sensor_query_anti_snore` | SXB `q_antiSnore` null |
| `sensor_anti_snore` | SXB `s_antiSnore` with both `L` and `R` `[enable,8,4]`; no angle semantics assigned |

The live request survives link loss/controller replacement through HA's per-address app-state store. Explicit stop/disconnect clears it. Reports accept the proven gzip/zlib wrappers and single/multi algorithm schemas. Values are device data, without medical interpretation.

## Position Feedback / Notifications

The diagnostic state retains capability events, alarms, RGB, music, raw motor/desk, lock, heating, fan, blanket and atomization values. Sleep entries expose left/right live values, report data, device time, sensitivity and anti-snore settings.

- No raw axis is assigned a physical motor or calibrated unit without evidence.
- The [Hush Base profile](richmat.md#hush-base) lists the bed notifications, their
  framing and checksums.

## Command Timing

The bed's write tick, motor hold, soundtrack switch and detector poll are in the
Richmat guide's [catalog app timing](richmat.md#catalog-app-timing).

| Timing | Value |
|--------|-------|
| Sensor live poll | Two seconds |
| HA query bound | Five seconds, an HA bound rather than a firmware acknowledgement |
| Report permission | One second |

HA operations retain their admitted target, cancel callbacks on connection teardown and do not reproduce the app's cross-target singleton races or unmounted UI callbacks. A local service call commits its supplied light value directly; it does not emulate the phone widget's 200 ms persistence callback or color-wheel gesture throttle.

## Notes

Hardware validation is deferred to real users after beta/release. No maintainer hardware acquisition is required.

### Analysis provenance

- `com.richmat.hushbase` 1.0.5 (10501), artifact set `d24ad2c95ea839969a5406fa8219f62048386598152608554641586041293cd7`.
- APK Protocol Audit row126 records the exact accepted source references, exhaustive dispositions and exclusions. Its item closure is the [ledger fixture](../../tests/fixtures/hush_ledger.json) that `tests/test_hush_dispositions.py` checks.
