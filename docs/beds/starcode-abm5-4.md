# AdjustableM5X4 app profile

**Status:** Implemented profile with the fixed selector schema, paired dispatch,
owned cancellation and public entities covered by artifact vectors and focused tests. Hardware operation is
unverified. The README remains the supported-bed status index.

This profile belongs to `com.starcode.abm5_4` 1.0.1 (3), delivered as five APK
members. It preserves this app's commands and state rules separately from other
StarCode, Sleepys and shared-UART applications. A brand, device-name prefix or
service UUID alone does not identify the app profile. See the
[row004 disposition](../apk-analysis/row004-dispositions.md) for accepted identity,
required work and every exclusion.

## Independent selectors

The app has three selectors. **C** chooses command bytes and the parser; **D**
chooses GATT roles and normal write mode; **U** determines which parsed fields the
UI consumes, its positive control gates and preset release behavior. They can
diverge. A restored C value remains usable before, or without, an optional
manufacturer result; C is not a transport-readiness barrier.

| C ordinal | Exact enum | Parser | Positive controls |
|---|---|---|---|
| 0 | `none` | Legacy BOX24 formulas | Restoration-only gate |
| 1 | `BOX15` | BOX15 length/header branches | Restoration-only gate |
| 2 | `BOX24` | Legacy BOX24 formulas | Restoration-only gate |
| 3 | `BOX1220` | Legacy BOX24 formulas | Conditional retained state |
| 4 | `BOX1221` | Legacy BOX24 formulas | Restoration-only gate |
| 5 | `BOX2422` | Legacy BOX24 formulas | Restoration-only gate |
| 6 | `BOX2442` | Legacy BOX24 formulas | Restoration-only gate |
| 7 | `BOX3633` | Legacy BOX24 formulas | Conditional retained state |
| 8 | `BOX25` | Modern BOX25 formulas | Modern parsed-state gate |
| 9 | `BOX25_STAR` | Modern BOX25 formulas | Modern parsed-state gate |

These are application enums, not ten verified hardware models. All ten C values
have conditional live routes. Five enums share a tested packet matrix without
becoming one selector. The app restores a missing preference as C0 and accepts
ordinals 0–9; invalid stored values throw in the app. HA must reject invalid
configuration safely.

Scanning applies `platformName.toLowerCase().startsWith("star")`. Constructors
instead use case-sensitive `Star` for D8, `BLE` for D3 and otherwise D7. Thus a
lowercase `star` name can scan successfully and construct D7. The manufacturer
characteristic's exact string `star` selects C/D9; another result selects C/D8 in
the UART classification path. This callback does not update U. No service or
manufacturer-data acceptance filter is supplied to scanning; company key 89 is
printed as a diagnostic. Remembered reconnection uses the stored identity/name.

The integration's persisted fields are
`starcode_abm5_4_command_selector`, `starcode_abm5_4_transport_selector` and
`starcode_abm5_4_ui_selector`. Their configuration and public runtime have focused test coverage;
the UI selector is retained/internal rather than an additional ordinary
user picker. Automatic transport selection may use the original Bluetooth name;
explicit app selection supplies the application contract. Each physical address
owns its selectors, observed state and operation generation.

## GATT and connection

| Live D route | Service | Write | Receive | Normal writes | App subscription |
|---|---|---|---|---|---|
| D3, `BOX1220` | `00001000-0000-1000-8000-00805f9b34fb` | `00001001-0000-1000-8000-00805f9b34fb` | `00001002-0000-1000-8000-00805f9b34fb` | Without response | Enabled |
| D7, `BOX3633` | `62741523-52f9-8864-b1ab-3b3a8d65950b` | `62741525-52f9-8864-b1ab-3b3a8d65950b` | `62741625-52f9-8864-b1ab-3b3a8d65950b` | With response | Role assigned, not subscribed |
| D8/9, UART | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | Without response | Enabled |

The D1 FFE9/FFE4 branch has no current writer and is excluded. Restoring C1
does not make D1 reachable: its packet/parser can operate over an independent
live D route. Actual characteristic properties come from the peripheral.
Notification versus indication and CCCD writes are host transport responsibilities.

Device Information service `180a` contains manufacturer `2a29` and firmware
`2a28` roles, expanded to standard Bluetooth UUIDs. UART initialization sends the
common wake packet **with response**, with one immediate retry on failure;
normal UART command writes remain without response. Manufacturer read retry is
200 ms, notification retry 2 s, connected query delay 500 ms and firmware read
1 s after the query callback. Failed or absent optional classification preserves
the current selector. Reads, query and their diagnostic results require exposure.

The explicitly selected profile uses the app's 8 s normal connection timeout,
including initial setup, capability probes and HA host/proxy connect attempts.
HA connection-profile retries and
backoff still apply. The shipped Android library defaults to an MTU 512 request;
the app does not select it. HA/Bleak and Bluetooth proxies own MTU negotiation,
so this profile neither requests nor claims negotiated MTU 512. An
already-notifying app toggle-off quirk must not leave HA without a required live
subscription. The app's 30 s reboot wait belongs only to the Nordic firmware
updater completion flow, which this BLE bed-control integration does not expose.

Repeated control writes keep the exact 100 ms cadence after a platform write
failure, with a logged failure and no immediate retry or acknowledgement claim.
STOP cleanup and the massage release query retain their deadlines. A completed
service call does not prove that an unacknowledged write reached the bed.

## Actions and timing

The required public controls are head/back and foot/legs up/down, native union
up/down, STOP, Flat, TV, Lounge, Zero Gravity, Anti-Snore, Memory A recall/save,
named TV/Lounge/Zero Gravity saves and reset. Both visual M1 and M2 in the app
invoke Memory A. No independent second memory slot is supported by this evidence.

Frames are action-specific for each C. BOX15's selected frames append the
complement of bytes 0–7; BOX1220's selected seven-byte frames place the complement
of bytes 2–6, with destination byte 2 zeroed, in byte 2. Other groups do not acquire
a checksum through family resemblance. There is no proved additional encryption,
sequence number or nonce. Native vector tables cover all exact action arrays and
fallbacks; equal on/off frames in some variants remain distinct app actions.

| Operation | Exact app behavior | Required HA behavior |
|---|---|---|
| Movement and Memory A recall | Immediate frame, repeat every 100 ms while held; immediate STOP on up/cancel | Bounded cancellable held action; fresh-event STOP |
| Other preset hold | 100 ms stream; release STOP only for U8/9 | Preserve U-dependent release, serialized by target |
| Flat | Starts on release, runs 600 ms; cleanup follows U; save/reset combination suppresses Flat | Expose the complete release-triggered operation |
| Save/reset combination | Exact C frame starts immediately and streams through the 6 s local confirmation interval | Await bounded writes; preserve safety cleanup without claiming a device ACK |
| Massage strength step | Single shot | Relative head/foot increase/decrease only |
| Massage wave step | 100 ms stream while held | Bounded directional operation |
| Massage release | STOP at 100 ms, query at 300 ms | Same-owner delayed cleanup; obsolete callbacks cannot stop a new action |
| Automatic white | Changed U8/9-consumed field47=true while connected starts captured C frames every 100 ms, ceasing after 5 s without STOP | Keep valid same-owner behavior; invalidate replacement-owner callbacks |

The six-second success toast does not prove EEPROM persistence or delivery.
Three-packet commitment, 110-packet storage and arbitrary generic program frames
from another app must not be imported. The shared app debounce accepts only
elapsed sampled integer milliseconds **strictly greater than 500 ms** across floor-light plus/minus,
brightness, and native on/off/toggle actions. A suppressed brightness change
does not update local state; a rejected value does not consume the shared gate.

## Massage and floor light gates

Massage toggle is independently reachable. Positive relative intensity, wave
and timer requests require the observed massage-on gate. The timer's live raw
inputs are 1, 2 and 3, displayed as 10, 20 and 30 minutes. A timer select must
offer only those choices; the app's `massageOff` path is dead, so no generic Off
timer command is inferred. Absolute intensity, absolute modes and sonic setters
are not proved controls.

Floor on/off/toggle and plus/minus are independent actions. Brightness is a raw
integer, not measured percent, lux or a calibrated hardware level. Zero selects
the off action rather than a raw-zero slider frame.

| Capability gate | Exact reachable behavior |
|---|---|
| C0/1/2/4/5/6, restoration only | Positive massage gate has no enabling writer. Fresh light level 1 yields plus raw2 or minus off. No full 1–6 slider or newly built automatic-white operation. Toggle and required release/query remain reachable. |
| C3/7 | Own-address state retained from a valid modern route can keep massage/light on and timer/level values, making conditional positive controls and raw 1–6 brightness reachable. Newly consumed legacy feedback remains UI-suppressed. |
| C8/9 | Modern U8/9 feedback can enable positive massage, timer and light-level controls. A stale legacy U can still suppress updates; each command checks current observed gates. |

C/D/U transitions may preserve observed state on the **same address**. State
from another physical bed cannot authorize controls. Actual reconnects retain
the eight observed Home UI fields and the shared light timestamp in the
coordinator's process-local state. Reconstructed raw models keep fresh parser
defaults; raw diagnostics stay unknown until a valid callback. The retained
head intensity, wave, low4b and white flag remain last-observed UI values,
separate from the new raw parser model.
Rehydration does not replay callbacks or restart automatic white lighting.
A native test across all
C/U combinations is a branch probe, not proof that every combination has a live
application writer. An old modern automatic-white stream retargeted to another
bed is a safety exclusion, not a fresh C3/7 automatic-white control.

The controller-specific entities include a 10/20/30 timer select,
raw 1–6 light-level number where reachable, union and light-step buttons, named
save/reset actions, wake/query/read actions and selector/raw-state diagnostics.
Their semantic keys use `starcode_abm5_4_*` for platform, translation and card
discovery. Custom controls stay owned by their physical child
when using a two-address paired entry. This app has no encoded one-address
left/right selector.

The `adjustable_bed.starcode_abm5_4_hold_control` action accepts
`device_id`, profile-specific `control`, `duration` in seconds (0.1–60), and an
optional `side`, with whole-target preflight before writes. The controller's
internal duration is milliseconds. Its exact 23 control keys are `head_up`,
`head_down`, `foot_up`, `foot_down`, `union_up`, `union_down`, `memory_1`, `flat`,
`tv`, `lounge`, `zero_g`, `anti_snore`, `save_memory_1`, `save_tv`, `save_lounge`,
`save_zero_g`, `save_reset`, `head_strength_up`, `head_strength_down`,
`foot_strength_up`, `foot_strength_down`, `wave_up` and `wave_down`.
Do not use another application's held-command catalog.

The `starcode_abm5_4_use_detected_profile` button cancels and cleans up
the current owner's work before adopting D into C/U. It retains own-address
state and invalidates old callbacks. Consumed-state diagnostics include
`starcode_abm5_4_massage_on`, `starcode_abm5_4_light_on`,
`starcode_abm5_4_wave`, `starcode_abm5_4_head_intensity`,
`starcode_abm5_4_low_4b` and `starcode_abm5_4_automatic_white_flag`, alongside
the 16 raw fields (`b`, `13`, `1b`, `23`, `2b`, `33`, `3b`, `43`, `47`, `4b`,
`53`, `5f`, `67`, `6f`, `77`, `7f`), selectors, manufacturer, firmware, timer
and light level.
These describe parsed/application state and add no hardware units or ACK.

Twelve frozen brightness probes using 15, 30 or 255 establish the private
one-byte builder domain, not additional public brightness levels. Public
brightness remains integral 1–6 with off as a separate action. The owner has
flagged this binding distinction for independent review and requires explicit
public-domain rejection tests; no accepted evidence or exclusion is rewritten.

## Feedback interpretation

The parsers assign raw model fields. They do not prove calibrated motor positions,
angles, percent, fault codes or physical actuator count. The app proves two control
axes; no extra neck/lumbar/motion/voice/alarm/RGB control follows from raw slots.
Initial fields47 and5f are true in the app model, separately from physical state.

| Parser | Recognition and sufficient length | Important formulas |
|---|---|---|
| Modern C8/9 | `a5/0b`, at least 16 bytes | Time `(b[4]<<8)\|b[5]` maps 1–600→1, 601–1200→2, 1201–1800→3, otherwise0. Wave is byte6 low nibble; both intensity slots use byte7 low nibble. Brightness/index are byte14 high/low nibble; light on is low nibble>0; field47 is byte15 high nibble==1. |
| Modern C8/9 | `a5/0d`, at least 19 bytes | Fields2b/33/3b clamp bytes4/6/8 to100; field5f is byte17==0. These remain raw diagnostics. |
| All non-BOX15 C | `a5/0c`, at least 8 bytes | Fields67/7f/6f use bytes6/4/7. Field77 maps byte5=5→17,6→19,otherwise9. No alarm interpretation is inferred. |
| Legacy BOX24 formulas | `a5/0b`, byte2=14, at least 9 bytes | Timer index multiplied by10; wave=byte6−1, including−1. Intensity scale is `v//3 + v%3 + int(v>1)` on byte7 low nibble and byte8. |
| BOX15 special | `ed/80`, at least 7 bytes | Fields67/7f/6f/77 use bytes3/5/4/6. |
| BOX15 fallback | Non-special length23 | Timer `b[19]&15`, head `remap(b[11]&7)`, foot `remap(b[12])`, wave `b[21]`. |
| BOX15 fallback | Non-special length16 | Timer `b[14]&15`, head `remap(b[7])`, foot `remap(b[8])`, wave `b[14]>>4`. |
| BOX15 fallback | Non-special length10 | Timer `b[8]&15`, head/foot0, wave1. |
| BOX15 fallback | Other non-special length | Timer/head/foot0, wave1. |

Here `remap` maps3→2 and6→3, passing other values through. BOX15 fallback
overwrites those four fields without adding header/checksum validation. A short
recognized special `ed/80` frame of 4–6 bytes is rejected safely rather than falling through and
overwriting fallback state.

Only U8/9 consumes modern parsed state for its positive gates and public light/
massage state. Its head intensity is `max(field13−1,0)`, timer is `field_b`,
wave is `field23`, and massage-on is **timer>0**. Light-on is `field43`, level
is `field53`, low 4b is `field4b`, and automatic-white flag is `field47`.
The flag starts white only while connected. Raw67/6f/77/7f have no other app
consumer or proved error/model mapping; raw2b/33/3b have no measurement UI or
unit conversion. Field5f supplies diagnostic stopped text, not STOP or a control
gate. All assigned raw fields remain diagnostic. Identical parsed
model updates preserve the artifact's equality suppression; valid changed
updates must retain exact formulas. The unreachable D1 fragment accumulator is
not enabled by selecting C1. Short-frame guards prevent out-of-bounds updates
without inventing checksum validation.

## Ownership, boundaries and validation

Operations, subscriptions, reads and delayed callbacks must remain bound to the
original address and connection/profile generation. Teardown, disconnect and
selection changes cancel owned work and attempt required cleanup while the
original connection is available. The app's stale callback/state-transfer bugs
are not implementation targets; their reachable bed controls remain required.

Nordic DFU payload/catalog/download/bond handling, Wi-Fi, handset permissions,
licensing and navigation are product/host boundaries. Firmware-update activity
still invalidates normal roles and control admission. No PIN, bond removal,
unproved capability query or OTA retry is introduced.

The accepted evidence is complete. Final integration acceptance is pending:
every required row needs actual code and passing focused test references, all
platform exposure and ownership tests must pass, and the complete standalone PR
must finish its review/CI/merge gates. Hardware checks HW01–HW06 remain deferred
to real users after beta/release; they do not defer artifact-backed implementation.
