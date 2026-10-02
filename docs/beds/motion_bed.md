# Motion Bed app

**Status: artifact behavior verified; hardware operation remains unverified.**

This explicit app route comes from `com.sn.blackdianqi` 1.24 (34). Its complete
XAPK artifact has SHA256 `76449cb37440907b6933c5dfb36a1a5ec5b737756f44db5a9629a654f9f3e6a3`.
The frozen report passed independent acceptance with 17 passing gates before
implementation. See the [unit 032 dispositions](../apk-analysis/dispositions/032-motion-bed.md).
Existing Solace and other app profiles remain separate.

## Choosing the profile

Select **Motion Bed app** in setup and enter the original Bluetooth name used
by that app, preserving case. Shared FFE1 transport does not select this app.
When an advertised name matches both the existing Solace detector and the
Motion Bed app's exact case-sensitive whitelist, setup asks which app profile
to use. Neither the discovery chooser nor manual Auto-detect silently chooses
Solace for that overlap. Explicit Solace and Motion Bed choices retain their
separate factories; legacy names outside the Motion whitelist keep their route.
Other accepted names, including TL-Q, QMS-430 and S5-Y, also offer Motion Bed
in the explicit app chooser. A shared FFE0 advertisement alone does not select
Motion Bed. Name-only candidates require an explicit choice, while an
incompatible unique service keeps its existing detection priority.
The source uses 48 case-sensitive substring markers. Ordinary QMS, SealyMF and
S-series names select their ordered preset and movement layouts. TL-B selects
the motor module, TL-A air massage, TL-W thermal control, and TL-Q one hub.
The hub discovers motor, air and thermal modules through the same BLE address.
Binding a module does not open another connection. The Active hub module select
chooses among reported modules and controls which surface owns startup and
thermal polling. All reported module controls remain available.
Thermal polling holds the current connection across its native two-second initial
wait and five-second query spacing, including quick-disconnect mode. It releases
that hold when the selected module changes, polling is cancelled or the session
drops; other commands can still run between queries.
The native card exposes this select in its utility section, including paired
side views. Open its normal Home Assistant entity row to choose the module.
Hub button registry identities survive unknown and temporarily absent inventory,
preserving custom names and disabled settings. Capability checks still prevent
absent-module actions. Changing away from the hub profile prunes stale identities.

Idle disconnect clears live module observations, while a separate process-local
capability snapshot keeps the last validated hub controls available for
preflight and reconnection to the same address and exact profile. It is neither
persisted nor published as fresh inventory. A new definite absence overrides
the snapshot; deletion clears it pending the inventory reply, and changing the
physical target discards it. An unknown hub with no validated inventory still
rejects module controls, including all-target preflight before any write.

Switching modules retires the prior thermal poller and pending startup work.
A failed module initialization can retry on the next inventory reply. Deletion
acknowledgements refresh the hub inventory; existing buttons publish changes to
their reported module/audio availability. The hub Stop action uses its active
module's proven motor STOP, air-stop or thermal-off command.

Auto layout follows the original app name, including its saved-title character
replacement. Advanced retained preset/movement choices apply only to the same
physical target and cannot cross between ordinary beds and modular products.
An empty or unknown restored title requires the explicit app-restored option.
Each physical side of a paired bed retains its own profile; unpair before
changing profile fields that differ between two addresses.

## Controls and state

Named app presets, massage, lighting, synchronization, audio and sleep controls
are exposed as buttons or validated actions. Diagnostics list available action
keys and labels. Movement covers use only the selected layout's exact control
pairs and names. Modular motor buttons expose **Back down** and **Leg down**:
the shipped upper-arrow callbacks are dead and do not establish an up command.

Motion sends one start frame, holds for a bounded duration, and releases with
the protocol STOP even on cancellation or failure. The hold captures its original
client and characteristic, so a still-live old target is released during rebind
without sending cleanup or position requests to its replacement. Unexpected
and intentional disconnect callbacks synchronously invalidate owned timers;
queued callbacks also check session ownership before reconnect admission. The default one-second hold
and maximum ten-second bound are integration safety limits, not app repeat
intervals. Presets and accessories do not acquire an invented motor STOP.
App preset-selected flags describe programming/parser state, not a measured
motor position. Memory recall preserves the source's selected-state conditions.
Programming supports the app's state-dependent toggle or explicit save/clear,
with confirmation before persistent changes.

K4 split preset recall preserves its unusual cross-field selection reads;
long programming uses each preset's own field. K5 preserves split and coupled
memory flags. K3's app-labelled Flat action sends the shipped anti-snore custom
recall, so it is not advertised as a generic guaranteed-flat preset.

The QMS-MQ, QMS2, S3-2 and QMS3 preset-query identity is independent of audio
capability. Only the exact QMS3-N93-327 substring, compared in uppercase as in
the app, overrides positive Home audio feedback. Modular receivers retain
their own flag-based audio decision.

Audio availability is remembered per physical target and explicit app profile,
as in the app. Fresh feedback overrides the preference; restored preferences
never turn unknown live sensors into reported feedback.

State sensors include raw positions A–D, alarm fields, programmed presets,
module presence/features, pressure, sleep/calibration/report values, network
state, thermal state/water and passive bed faults. Raw positions have unknown
physical units and do not become degree or percentage sliders. Air lower
pressure is readback only. Thermal gears are cooling 4–1, off, and heating 1–4;
the app's slider labels do not establish thermostat setpoints. Temperature and
water values retain their source decimal interpretation. A schedule receipt
acknowledges the write without proving that heating is active.

Sleep day/window state separates trustworthy decoded windows from the app's
faulty historical-window assignment. A new report clears prior aggregation.
Only the newest report receiver context remains active. Provisioning retries
retire the previous polling task and deadline before sending the new sequence.
The artifact supplies no request identifier for these replies: host ownership
prevents superseded work and overlapping report receivers, but cannot identify
a delayed reply that has the same wire shape as the latest request. Report
route flags and provisioning feedback therefore belong to the current request;
they do not prove which indistinguishable attempt produced a reply.
Malformed or short notifications leave state unchanged and record a diagnostic
rejection. Fault replies are parsed passively; hidden fault-request controls
remain excluded.

## Actions

All actions accept `device_id` and optional `side`. Paired child targets retain
their side. Every selected target is validated before any write. Persistent
changes require `confirmed: true`.

| Action | Main fields |
|---|---|
| `motion_bed_action` | `action` from diagnostics; `branch` app/save/clear; bounded movement `duration` in seconds |
| `motion_bed_alarm` | `enabled`, `hour`, `minute`, weekdays 1–7, `repeat`, modes 1–6, `massage`, `sound`, current target's `audio`; modular initial `switch` 00/01/A1 |
| `motion_bed_clock` | ISO `timestamp`, `thermal` to select the thermal clock |
| `motion_bed_sleep_angles` | page 2/3/4, four `flat` and four `side_positions` raw values |
| `motion_bed_calibration` | integer `flat`, `side_position`; the serializer retains source scaling and rejects invalid encodings. The flat editor accepts the proven nonnegative Java-int domain, with odd-width encodings still rejected before I/O |
| `motion_bed_sleep_timer` | bedtime slot 0–8 or `fall: true` slot 0–4 |
| `motion_bed_sleep_report` | month/real/timer/day, historical day `offset` 0–29, separate graph `window_offset` 0–4 |
| `motion_bed_module` | query/bind/delete, module type 10/11/12 (motor/air/thermal), colon-separated module MAC for bind |
| `motion_bed_air_setting` | mode 3/18/4/5/12, `query`, gear 1–8, optional timer 0/1/2; an unset timer stays unset |
| `motion_bed_pressure` | live channel 0–11 and value 0–9, or save twelve `values` |
| `motion_bed_thermal_schedule` | `hour`, `minute`, mode 1 heat/2 cool, gear 1–4 |
| `motion_bed_audio` | track/volume, `value` 1–5, optional track `preview`; requires reported audio support |
| `motion_bed_provision_wifi` | SSID, password, longitude, latitude; seven BLE frames and finite status polling |

A nonempty saved weekday map can enable repetition even when no day is selected;
use `repeat: true` with an empty weekday list to preserve that source state.
The modular uninitialized alarm switch is unavailable after alarm state arrives.
Audio/song versus buzzer handling follows the current target's reported flag.

Pressure live edits bind the channel explicitly in the HA action, rather than
letting another UI selection redirect the write. The source's strict greater
than two-second quiet check occurs on a 500 ms tick, so the action waits 2.5
seconds. Cancellation or a target/session change prevents the pending write.
Whole pressure save is a single unsplit 47-byte frame.

The calibration debug action polls at two-second intervals for at most ten
samples. Sleep adjustment polls positions every 500 ms while held, then sends
STOP and queries after 100 ms. Thermal status polls first after two seconds,
then every five seconds while its thermal surface is active and present;
changing the active hub module or tearing down the session cancels polling.

Wi-Fi provisioning uses Android UTF-8 encoding, source truncation/padding to
32 SSID bytes and 16 password bytes, and big-endian coordinate floats. Seven
frames are spaced by 300 ms. Status polling shares one budget of at most ten
queries six seconds apart. A typed command-connection hold spans the complete
provisioning attempt, including poll sleeps, so a one-second handoff cannot
interrupt it. Completion, cancellation, write/query failure and session
replacement release that hold; a new attempt retires the old hold and poll
before acquiring its own. Credentials are redacted from integration command
traces and never saved in entry data, local preferences or diagnostics.
Home Assistant core can log the original action data, including SSID and
password, before the integration handler runs when `homeassistant.core` DEBUG
logging is enabled. Keep that core logger's DEBUG logging off while provisioning;
the integration cannot redact these upstream service-event logs.
Cloud WebView content is outside this BLE integration.

## Transport and encoding

The app scans every GATT service and uses the **last**
`0000ffe1-0000-1000-8000-00805f9b34fb` characteristic. Writes and notifications
bind to that exact characteristic object and client. Duplicate UUIDs cannot
redirect an old operation. A missing write or notification capability is an
explicit failure. The APK never sets a write type; HA prefers its current
write property, otherwise write-without-response, as a documented host policy.
No app PIN, bonding gate, encryption, nonce or session counter was found.
HA owns MTU and CCCD operations. Frames are not split or padded by this route.

P1 uses the four-FF prefix, P2 five FF bytes, and P3 four FF plus FE. CRC is
reflected MODBUS, initialized FFFF, polynomial A001, little-endian two bytes,
covering the entire prefix. Additive checksums sum unsigned bytes and retain
minimal little-endian width, including an empty suffix for zero. Numeric fields
use source-specific validated domains without masking widened values into a
plausible one-byte payload.

Physical users can validate behavior after a beta or release. Lack of maintainer
hardware does not defer statically proved controls or configuration writes.

Shared status replies are delivered to each active receiver whose own frame is
complete: calibration requires 12 bytes, network 15 and smart sleep 19. A complete
shorter receiver is retained even while a longer receiver is active. A truncated
standalone reply still rejects atomically without updating state.

A two-address pair cannot be converted from another bed type into Motion Bed in
shared options. Unpair first and configure each physical name/profile independently.
Existing valid Motion Bed pairs retain their side names when changing common options.
