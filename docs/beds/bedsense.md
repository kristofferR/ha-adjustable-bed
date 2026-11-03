# BedSense app

Select **BedSense app (com.fenmenbielei.bedsense)** during manual setup for beds
controlled by Android BedSense 1.8 (18). This is separate from **Bedsense Bases**
(`com.ore.bedsense`), which has its own [profile](ore-comfort-bed.md).
The implementation is artifact-proven; physical hardware is unverified.

## Setup and layouts

Choose a layout explicitly, or use **BedSense layout from the Bluetooth name**.
Auto uses the original, case-sensitive Bluetooth name with the following ordered
rules. A custom HA display name does not select the layout.

| Type | Name rule, first match wins | App layout | Movement controls |
| --- | --- | --- | --- |
| 1 | `JQ` or `NQ`, after type 2 | BEDSENSE-850 | Back, waist, back and leg, legs |
| 2 | `JQ-D`, checked first | BEDSENSE-890 | Back, waist, head, legs |
| 3 | Unmatched or absent name | Default | Back, waist, head, legs |
| 4 | `IQ` | BEDSENSE-1150 | Back, hip, head, legs |
| 5 | `LQ` | BEDSENSE-1050 | Back, hip, head, legs |
| 6 | `KQ` without `H` | BEDSENSE-250 | Back |
| 7 | `MQ` or `UPS` | BEDSENSE-150 | Back, legs |
| 8 | `H` without `S4`, after type 9 | BEDSENSE-350 | Back, rise and fall |
| 9 | `S4-2`, after type 7 | Resten Hi-Low | Back, hip, lift, legs |

The app's type 3 idle WAIST label changes to HIP while pressed. HA keeps the
idle waist label; physical actuator identity is unverified. Type 9 has separate
HIP and LIFT controls. Visible axes do not establish a physical motor count.
There is no automatic discovery signature: the app accepts any named device and
iterates all services for characteristic `0000ffe1-0000-1000-8000-00805f9b34fb`.
These short name substrings and this shared characteristic cannot safely
identify a BedSense bed. No service UUID is inferred. No PIN, bonding handshake,
side selection, authentication, or capability query is defined by the app.

## Controls and state

- Covers provide each layout's movement controls. One press sends one movement
  frame. HA holds for the configured finite movement window, then sends release
  `FF FF FF FF 05 00 00 00 00 D7 00`. STOP, cancellation and dashboard release
  also end movement. The app has no movement refresh cadence.
- Flat, TV, Zero Gravity and Anti Snore presets, five memory recalls and saves,
  and explicit clear buttons are available where the app exposes them. Slots
  1/2 require a saved indicator. Slots 3/4/5 select stored or built-in TV/Zero
  Gravity/Anti Snore according to the indicator. Types 6/8 replace slot 5 with
  a Flat Bed save/recall, regardless of the flag, and have no slot-5 clear.
- Types 1–5 have their app-labelled circulation buttons. Type 3 uses a different
  whole-body literal. The app's two-second circulation UI unlock sends no BLE
  packet; HA exposes the resulting actions directly.
- Types 4/5 add Music and Leg Relax; types 6/8 add Lumbar. Type 9 also has
  single-shot RISE/DECLINE buttons. These send the same literals as lift
  up/down, but append no release, matching the app's distinct click behavior.
- Every layout has head/foot massage increase/decrease, wave frequency
  increase/decrease, and 10/20/30-minute timer selections. Selecting the same
  timer twice cancels it; an explicit cancel button is also provided. Step
  counters clamp at 0–3 (head/foot) and 0–4 (wave), but every tap still writes.
- Every layout has light-duration buttons labelled **10 min**, **8 h**, and
  **10 h**. Hardware timing is unverified. There is no proven dedicated light
  off, brightness, RGB, or channel command.
- A separate movement/massage **background tap** action preserves the app's
  distinct `D8 14` trailer. Its physical effect is unverified; it is not labelled
  as STOP or massage off. Quick/light background taps use the normal release.

Memory indicators, massage bars, local step counters, circulation and selected
light/massage durations are exposed as entities. They are **app indicators**,
not measured positions or device acknowledgments. Local successful writes feed
the app parser, just as Android write callbacks feed its shared receive path.
`bedsense_state_source` identifies the last published source. Failed HA writes
do not fabricate success. Memory flags persist per physical bed and app profile,
instead of sharing the phone app's global flags between unrelated beds.
A per-address BedSense app session shares the current flags, timer selection,
step counters and indicators across live/offline controller recreation. Only
the saved-memory flags persist across Home Assistant restarts, matching the
app's saved flags versus process-local selections.

The parser preserves all 41 ordered memory predicates, exact-versus-substring
matches, the M1-clear exception, association state and unmatched reset to 10.
The default M1 query has no association rule. Foot massage patterns update the
**head** display bar in the app; HA preserves and labels this as a display width,
not foot intensity or physical percent. Notifications do not update local step
counters or selected timers. No angles, battery, model or physical position
feedback is claimed.

## Transport and safety adaptations

All fixed packets are 11-byte literals. Their trailers, including anomalies,
are preserved without inventing a checksum. Every matching FFE1 characteristic
is subscribed and read after 200 ms; the last is the write target. The discovered
write-without-response property selects that write mode, otherwise writes use a
response. Bleak owns CCCD setup. The five memory queries run at 200 ms spacing,
after a nominal 2-second setup delay, in slot order 3, 4, 1, 2, 5. Types 6/8 and
7 use their own query tables. The **Refresh memory indicators** button repeats
this sequence.

HA serializes commands and reads. Movement always attempts release in cleanup,
including task cancellation. Explicit memory save/clear actions replace the
phone app's two-second long press and buggy uncancelled timers. HA does not
replay its unassigned/stale initialization write or read arbitrary unrelated
GATT descriptors. BLE failures remain visible. HA's normal adapter/proxy,
connection freshness, idle handoff and reconnection policies apply.

The [discovery ledger](../apk-analysis/dispositions/row108-bedsense.md) accounts
for all command, parser, transport and excluded behavior. Real users can validate
GATT roles/properties, memory replies, held versus single-shot lift behavior,
background taps, massage and actual light durations after beta/release.
