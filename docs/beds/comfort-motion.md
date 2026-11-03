# Comfort Motion

Select **Jiecang (ERGOBALANCE / Dream Motion / Comfort Motion apps)**, then
**Comfort Motion**. This profile implements `com.jiecang.app.android.jiecangbed`
2.2.1 (28). Shared Bluetooth UUIDs do not identify the app. Existing legacy
Jiecang/Comfort Motion entries retain their original controller; select this
explicit profile in options to use the audited app behavior.

Choose the physical layout in the app: back/legs, back/legs/neck, or
back/legs/neck/lumbar. The two-motor layout also exposes combined back/legs.
Enable massage and light controls only when fitted. These settings belong to
one physical bed and remain independent across a two-address pair.

The profile provides movement and release, flat/zero-gravity/anti-snore,
two memory recalls and two memory saves, independent back and foot massage,
massage mode cycling and stop, reported light state and toggle, Bluetooth
rename, and a wake sequence. It reports no motor angle, percentage, movement
completion, massage mode number, or bed clock. Hardware operation has not yet
been verified by real users.

## Transport and setup

| Selection | Service | Write | Notification | Rename |
| --- | --- | --- | --- | --- |
| G1 | `0000ff12-0000-1000-8000-00805f9b34fb` | `0000ff01-0000-1000-8000-00805f9b34fb` | `0000ff02-0000-1000-8000-00805f9b34fb` | `0000ff06-0000-1000-8000-00805f9b34fb` |
| G2 | `88121427-11e2-52a2-4615-ff00dec16800` | `88121427-11e2-52a2-4615-ff00dec16801` | same as write | unavailable |

Auto uses the last complete matching transport in GATT enumeration order,
retaining both notification subscriptions when both exist. Select G1/G2 to pin
one. G3 is unsupported by this app. Writable name roles are rediscovered per
connection; G2 alone cannot reuse an old G1 name handle.

The app scans only G1's service, with no name/manufacturer/RSSI restrictions.
Its barcode and saved-address routes also reach G2. HA uses its own Bluetooth
scanner and manual address selection; select this app explicitly, including
for G2. No new automatic app identification is inferred. The login-named role
has no authentication consumer. There is no PIN, bonding or login exchange.

The app schedules subscription at 100 ms, then actuator queries at 200/300 ms,
hardware queries at 400/500 ms, and massage queries at 600/700 ms after service
discovery. HA awaits subscription and serializes these six attempts. Queries
run without a layout or massage gate, including with massage disabled. These
are scheduled duplicate writes, not ACK retries. HA cancels failed setup and
cleans subscriptions instead of allowing old Android timers to write after a
reconnect. The next connection gets a fresh batch. Write response mode comes
from discovered characteristic properties, since the APK never fixes ATT mode.

## Commands and state

Only the 32 reachable fixed framed literals and raw rename are implemented.
The [discovery ledger](../apk-analysis/dispositions/row115-comfort-motion.md)
accounts for every accepted command, unused literal, variant and state path.
The observed sum relation across literals does not establish an arbitrary-frame
checksum builder. No extra command is synthesized.

Movement refreshes every 100 ms for HA's configured pulse count. Motion and
normal preset recall end with `F1F14E004E7E`, the observed release. HA also
releases on cancellation and exceptions. The app misses releases on touch
cancel, keyboard release and teardown and can emit a final movement after
release; HA does not reproduce these unsafe lifecycle bugs. An explicit STOP
sends release immediately. Physical emergency-stop semantics are unproven.
Presets send once and release after 100 ms. Saves send once without release.
The third memory, massage-start, timer/reset and extra intensity literals have
no reachable caller and are excluded.

Massage sliders use 0/1/2/3 for wire values 0/2/3/4. Up/down uses the last tag06
state, bounds do nothing, and unrecognized wire levels leave the slider unknown
and make stepping a no-op. Writes do not optimistically change reported state.
Massage stop (`F1F11101081A7E`) differs from movement release. Mode cycling sends
one fixed command without a release or an invented mode number.

Notifications are consumed per callback without frame validation or assembly:

| Tag at byte 2 | Minimum length | Consumed fields |
| --- | --- | --- |
| `0F` | 7 bytes | byte 4: layout 1..6, otherwise 0 |
| `05` | 9 bytes | byte 8, bit 6: light on |
| `06` | 9 bytes | byte 4: unsigned back massage; byte 6: unsigned foot massage; byte 8, bit 6: light on |

Other/short/empty values are ignored safely. No motor positions are decoded.
Layout 1/2 describes two motors, 3/4 three, and 5/6 four; even values initially
show massage navigation. These are app UI layouts, not continuing write gates.
The app retains motor selection, massage zone/intensity and active panels
through repeated, changed or invalid layouts and same-instance reconnect.
HA keeps explicitly selected axes stable, retains reported state across its
controller replacement on reconnect, and never clears massage or light state
on a layout reply. The latest reported layout and raw intensity values remain
in protocol diagnostics. A user can change physical layout or massage presence
in options without relying on the app's stale-selector behavior.

The light has one toggle command. On/off actions toggle only when the last
reported state differs; they refuse unknown state. The native toggle remains
available before feedback. Neither writes nor disconnects fabricate feedback.

`adjustable_bed.rename` accepts 1..18 ASCII letters, digits, dots and underscores
and writes the bare bytes to the discovered G1 name role. There is no name
acknowledgment. This does not change HA's local device name.

## Automations and wake

Use `adjustable_bed.jiecang_wake` with `preset` set to `memory_1`, `memory_2`,
`zero_g`, `flat` or `anti_snore`, and optional `head_level`/`foot_level` 0..3.
Zero skips that zone. Enabled zones send at 0/200 ms, each followed by release
100 ms later. The preset is sent at 500 ms without a subsequent release, as
on the app's conditional alarm path. Cancellation always releases; stop the
massage with `adjustable_bed.jiecang_stop_wake`. Massage must be enabled before
using nonzero levels. Yoga is unsupported and rejected before writes.

Schedule the service using HA automations. Android's alarm tab is unreachable
in this version, while its exported start/stop broadcasts and possibly old
WorkManager jobs can still execute the sequence. There is no BLE alarm
programming or clock-setting command. Android notifications, weekday filtering,
preferences, QR camera, Play updates and GIF rendering are companion-app
infrastructure. Wi-Fi provisioning, cloud/accounts, networking and bed firmware
updates are excluded product domains, with no reachable bed implementation
found in this delivery. These exclusions are not feature debt.

## Evidence and validation

This implementation uses the independently accepted row115 report and audit
seals recorded in the committed ledger. Focused source-vector tests cover all
24 transport/layout/light variants, all 33 actions, unsigned response values,
query setup and cleanup, cancellation, state retention, actual HA entities,
serialized service routes, and rejected settings. Physical actuator effects,
ATT properties, release effects, mode names and rename persistence remain
validation for real users after beta/release; maintainers need not acquire a bed.
