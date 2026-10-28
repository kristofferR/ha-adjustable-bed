# Serta MP Remote

Select **Serta MP Remote** explicitly in the bed-type list. Use the Bluetooth
address of the bed and choose the layout shown by your app in **App controls**.
The layout is a UI choice, not proof of physical motor count or bed model.
Shared services, names and manufacturer data do not select this app automatically.
Generic SBI, Keeson and other app profiles keep their existing behavior.

Accepted artifact: `com.ore.serta330` version **1.1**.
Artifact-set SHA-256: `dfef30206d9f0b61a56fbb74602c2a04bbbc388ab0eb933cd10084bfe5a65146`.
Static app behavior is proven; actual bed effects, radio delivery and firmware
interpretation remain **UNVERIFIED**. Real users can validate these after a beta
or release; no immediate maintainer hardware test is required.

## Setup and controls

Layouts: **standard**. Each physical side of a two-address
pair retains its own app settings. Target the native child device, or choose the
paired service's `side`; conflicting child/side requests are rejected.
No app-specific physical left/right mapping or one-address pairing is inferred.

The app-labelled buttons use the existing coordinator command scheduler and BLE
lane. A button press provides a finite held adapter based on the configured
pulse count. A source held command repeats every **100 ms**, starting immediately.
All protocol-defined releases run with a fresh cancellation event. Disconnects
invalidate handles, pending work and stale notifications. No Android mutable
characteristic queue or stale-handle behavior is reproduced.

| Layout | App-labelled control | Control key | Mask | Event behavior |
|---|---|---|---|---|
| standard | Flat | `flat` | `0x8000000` | single |
| standard | Foot down | `foot_down` | `0x8` | held |
| standard | Foot up | `foot_up` | `0x4` | held |
| standard | Head down | `head_down` | `0x2` | held |
| standard | Head up | `head_up` | `0x1` | held |
| standard | Massage pattern icon (btnLevel) | `level` | `0x100` | single |
| standard | Lounge preset icon | `lounge` | `0x2000` | held |
| standard | Lumbar down (unlabeled touch area) | `lumbardown` | `0x80` | held |
| standard | Lumbar up (unlabeled touch area) | `lumbarup` | `0x40` | held |
| standard | Preset M4 icon (distinct from local memory slot 4) | `m4` | `0x8000` | single |
| standard | Foot massage increase | `masfootadd` | `0x400` | single |
| standard | Foot massage decrease | `masfootmin` | `0x1000000` | single |
| standard | Head massage increase | `masheadadd` | `0x800` | single |
| standard | Head massage decrease | `masheadmin` | `0x800000` | single |
| standard | RESET-labeled remote action | `reset` | `0x8001000` | held |
| standard | Tilt down (unlabeled touch area) | `tiltdown` | `0x20` | held |
| standard | Tilt up (unlabeled touch area) | `tiltup` | `0x10` | held |
| standard | Massage TIMER / ALL OFF | `timer` | `0x200` | single |
| standard | TV preset icon | `tv` | `0x4000` | held |
| standard | ZERO-G preset | `zg` | `0x1000` | single |

`held` repeats until bounded release; `pulse` sends once then releases after
300 ms; `single` sends once. `tap_zeros` sends once followed by zero frames at
+300/+400/+500 ms. `held_zeros` also schedules those three zero frames from the
start of the hold, retaining them after ordinary early release. Cancellation
and disconnect never leave background writers from an old operation.

The regular key frame is `E5 FE 16`, a low32 little-endian mask and one inverted
sum byte. Clock frames are `E7 80 01`, local year minus 1900 (low byte), zero-based
month, day, hour, minute, second and checksum. Name frames are `EF 02` with a
15-byte zero-filled region and checksum. The supported UI limit is 14 UTF-16
units. The source copies that many bytes from an unnamed default charset;
HA documents and uses the frozen UTF-8 model, including incomplete encoded
characters for some non-ASCII names. This does not establish firmware encoding.

The **M4 icon** is a remote key, separate from **local memory slot 4**.
Four local memory targets live in the integration configuration, defaulting to
head/foot 15°/35°, 15°/35°, 15°/35°, 15°/0°. Configure each head 0..60° and foot
0..45° in options. Recalling sends one `E5 FE 17` frame using the app's exact
calibration tables. There is no physical save command. Position sliders send
a calibrated axis target with the other field `0x8000`; no physical meaning for
that other-axis field is assumed. Local angle up/down actions update a bounded
target every 200 ms and send only one pulse frame on release.

Notifications are exactly 16 bytes and require byte13 bit5 clear. Pulse words
at 3..4 and 5..6 are little-endian; values >=32768 are complemented. Conversion
uses the nearest shipped table value, midpoint ties lower, head >15430 saturates
at 60° and foot >11667 at 45°. The reported angles are table estimates. The app's
request-progress state becomes active after 1500 ms, independently per recall;
feedback target equality wins before flag checks. This is request UI state,
not command acknowledgement or proof of movement. Disconnect cancels setters.
This app has no clock writer or alarm-table contract.

## Notifications and evidence

The **App timer status** sensor reports only the accepted source statuses:
-1=off, 1=10 minutes, 2=20 minutes, 3=30 minutes. Unknown statuses leave the
prior value unchanged. The parser does not infer acknowledgement, battery,
physical motor count, light state or physical memory meaning. Incoming packets
are not reassembled or given invented header/checksum guards.

See the calibrated16-byte parser above. Timer status is signed byte14.

The GATT selector independently retains the last matching notification and
write characteristics across all services. Both are required. FFE4/FFE9 are
used by these profiles; Q-Plus also accepts NUS read/write roles, independently
of UI style. HA subscribes through Bleak and chooses response mode from current
characteristic properties; the APK's unset Android write type does not prove
an on-air mode. No authentication, arbitrary-packet service or guessed firmware
operation is added.

The [durable disposition ledger](cluster033-dispositions.json) retains all 562
stable discoveries: 380 implementation dispositions, 12 narrowly credited
baseline behaviors, 170 exact evidence-backed exclusions. Its per-item symbols
and test cases accompany 413 frozen vector fixtures. The 16150 historical
owners, 3386 semantic occurrences, 10158 projections and 672 dependencies are
coverage metadata, not extra features or new audit credit. Raw APKs,
decompilation and full audit reports stay local and ignored.

## Native card holds

The native card uses each entity's flat declared hold metadata and calls the
registered bounded `hold_control` action once. Pointer release, Enter/Space
release, blur and page abandonment retain the owning side's STOP target.
A normal button press and accessibility click retain the finite action.
Combined parent motor buttons advertise a held direction only when every
eligible side declares the same control and start/release delays on a concurrent
pair. Mixed, unknown, legacy and sequential sides keep finite controls.

The scalar metadata is `held_control` on buttons, or `held_control_up` and
`held_control_down` on covers, plus `hold_start_delay_ms` and
`hold_release_delay_ms`. Source-held cluster033 controls start at0ms. Immediate
zero releases use0ms; Q-Plus MX uses300ms to its first query, followed by the
remaining600/900ms queries. These delays do not invent a physical STOP for MX.

Cancelling a local angle edit through Home Assistant sends the one calibrated
target pulse that finishes the edit. A successful target write satisfies only
the matching STOP cleanup, identified by its existing physical scheduler, STOP
epoch and current BLE session. A normal completed edit, replacement, failed or
interrupted write, or disconnected session cannot acknowledge a later STOP.
Later genuine global STOPs retain the remote zero-key command. The card still
sends its owning STOP immediately; it does not infer this protocol behavior.

The connected rename caller applies Java `String.trim` (outer code points
U+0000 through U+0020) before encoding and rejects an empty result. This is
package-specific caller handling, not Unicode whitespace normalization. The
conditional UTF-8/code-unit-copy model above remains qualified as documented.

Local-edit cancellation acknowledgement also applies to this physical
scheduler's paired GROUP reservation, including native Left/Right/Both targets.
The same successful-write, STOP-epoch and current-session checks apply. Covers
use the already-declared60° back and45° legs calibration limits: their accepted
endpoints show100%, while30° back and15° legs show50% and33%.

The registered `set_position` and `set_positions` actions validate the fixed
native ranges, back0–60° and legs0–45°, for every requested axis and physical
target before scheduling movement. This also works from offline capabilities.
Generic angle overrides do not change this app's calibration. A request for
legs35° followed by back61° is rejected before either axis writes; other bed
profiles retain their own limits.
