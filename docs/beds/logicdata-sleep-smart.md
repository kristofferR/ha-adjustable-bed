# LOGICDATA Sleep Smart Air Mattress app

This page covers the Android app `com.logicdata.app.mattress.bed` **1.0.0 (1)**,
"Sleep Smart Air Mattress". It controls two separate Bluetooth devices, the
adjustable bed base and the air mattress pump, so Home Assistant configures them
as two entries:

| Device | Bed type | Setup choice |
|---|---|---|
| Bed base | `logicdata_app`, app profile `sleep_smart` | **Logicdata → MotionRelax / Sleep Smart bed apps**, then **Sleep Smart Air Mattress app (bed)** |
| Air pump | `logicdata_air_pump` | **Logicdata → Sleep Smart air mattress pump** |

Both follow the accepted APK Protocol Audit report for this version.
**Static verified, hardware unverified.** The comparison ledger is
[row053](../apk-analysis/dispositions/row053-logicdata-sleep-smart.md).

Neither device can be identified from its advertisement. The bed's `ff12` and
`fe60` services are shared with other Jiecang/Lierda-based apps, and the pump's
`ffe0` service is a common serial-bridge service. Select both types manually;
existing entries keep their bed type.

## Bed base

The bed uses the same three GATT transports and `F1 F1 | opcode | length |
payload | checksum | 7E` framing as the [MOTIONrelax profiles](logicdata-app-disposition.md#transport-framing-and-initialization),
but its controls, startup and rename differ.

### Configuration

| Setting | Choices |
|---|---|
| Command family | `p1` for the Vienna and Toronto beds; `p2` for the Middle Rail bed |
| Layout | `standard_2` (standard series) or `split_series` (split series) |
| Massage | Enable when the bed has massage. The app's massage tab is reachable for every bed profile |
| Light | Enable for under-bed lighting |
| Transport | `auto`, `t1`, `t2` or `t3`, as for MOTIONrelax |

The app always ends with a two-motor movement layout: back, legs and both
together. Its three- and four-motor and split-movement handlers are hidden
before they can be used, so they are not exposed. The series only chooses the
massage zones: standard has back and foot, split has left back and right back.

The Middle Rail family changes only back and legs movement to the two-byte zero
payload. Combined movement, presets, memory, light and massage keep their P1
frames.

### Controls

| Control | Behavior |
|---|---|
| Back, legs, both | Repeat every 100 ms; on release one final movement frame, then `F1 F1 4E 00 4E 7E` after 100 ms |
| Flat, Zero Gravity, Anti-Snore, Memory 1 recall | Hold-only in the app: a tap sends nothing. A button holds the preset for the motor pulse count × 200 ms, refreshing every 200 ms, then releases 100 ms later |
| `logicdata_hold_preset` | The same hold for an explicit 0.2–60 s duration |
| Memory 1 save | One `F1 F1 0A 00 0A 7E`, without a release. The app has one memory slot |
| Under-bed light | Toggle, then releases at +80 ms (both forms) and +100 ms |
| Massage intensity | Off and levels 1–3 per zone (wire values 0/2/3/4) |
| Massage stop / mode | Massage stop only stops massage. Mode sends its fixed frame, a two-byte release at +1000 ms and a short release at +1100 ms |
| Refresh massage state | The massage tab's parameter query, sent at 100, 250 and 450 ms |
| Factory reset | Disabled by default. One reset frame; the app warns that it deletes stored memories and that a later held DOWN performs a reference drive |
| `rename` | `01 FC 07`, byte length and UTF-8 name on the name characteristic, once |

Cancellation and failures always finish with the release frame, even though the
app's key-release and cancel paths do not.

### Startup and state

Only a T3 connection becomes ready in the app: both T3 subscriptions (data and
name) must succeed. A T3 service next to a selected T1 or T2 transport also
makes the bed ready, and startup queries then use the selected write role. When
ready, the integration sends the app's two startup schedules: software,
vibration, hardware, actuator, light and device-status queries between 300 and
2700 ms, merged with the actuator, hardware (or Middle Rail software) and
vibration pairs at 1000–1500 ms. T1 or T2 alone stays silent until a control is
used. A failed name subscription leaves controls available without queries.

Replies set the under-bed light state, massage levels and a **Massage mode**
sensor (long interval, short interval, wave or continuous; unknown for other
values). A clock request (`F2 F2 50`) is answered with the current local time.
No positions, firmware, model or calibration are reported.

### Rename

Names are 1–20 characters from `0-9`, `a-z`, `A-Z`, `ä`, `ö`, `ü`, `Ä`, `Ö`, `Ü`
and `ß`, the app's edit-field alphabet. T1 writes to `ff06` and T3 to `fe63`.
T2 has no name characteristic of its own; when T3 or T1 is also present, the
app keeps that name role, and so does the integration (T3 first).

## Air pump

The pump uses service `0000ffe0-0000-1000-8000-00805f9b34fb`, writes LF-terminated
text to `ffe1` with response, and notifies on `ffe2`. There is no pairing,
authentication or initialization frame.

| Button | Text |
|---|---|
| Inflate (also the app's "60" mode) | `C>FILL>0` |
| Deflate | `C>EXCAPE>0` |
| Firmness 30 | `C>SETP>0>30` |
| Recall pressure memory | `C>MEMORY>0` |
| Save pressure memory | `C>STOPN`, then `C>MEM_S>0` |
| Stop | `C>STOPN` |

A tap sends one command; the pump keeps running until its own logic or a stop.
The app accepts a tap at most every 500 ms. The integration waits out the rest
of that interval instead of dropping the tap, so a save always follows its stop
by at least 500 ms. Stop is never delayed.

While connected, **Air pressure** is queried with `R>SP>0` 800 ms after setup
and then every 500 ms, like the app's pump tab. A reply starting `RET>SP>` with
at least 15 characters is decoded from characters 13–14 as signed hexadecimal.
The value is shown as received; the app defines no unit. The reading clears when
the link closes. New pump entries keep the link between commands for the idle
timeout so the reading stays current.

`rename` renames the pump with `AT+ENAT`, `AT+LENA<name>` after 50 ms
and `AT+REST` after 100 ms, each ending in CR LF. The pump restarts afterwards.
Names follow the same alphabet with at most 20 characters.

## Not implemented

- The app's alarm scheduler, alternative Bluetooth manager, connection pool,
  pump copy service and old layouts have no live caller.
- The login characteristic is looked up but never used.
- Reconnect dialogs, QR-code address entry, scan lists and Android permission
  flows belong to the phone app; Home Assistant connects to the configured
  address.
- No Wi-Fi, cloud, firmware update, position feedback, child lock or advanced
  lighting exists in the app.

Later hardware checks should confirm motor stopping, pressure units and scale,
the pump's response to rapid taps and the three rename phases, and which
services real beds expose.
