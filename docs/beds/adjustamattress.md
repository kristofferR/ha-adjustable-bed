# AdjustaMattress app

The explicit **AdjustaMattress app (seven product layouts)** bed type implements
`com.okin.adjustamattress` 1.6.0 (version code 10). Its artifact behavior is
verified; physical hardware remains **unverified**. It is independent of the
Adjustable bed (Lumbar), SmartBed and other OKIN app profiles. Shared services
and a familiar name do not identify this app, so select it manually.

## Setup and layout

Choose the matching product layout and BLE model in **Protocol variant**.
The 28 explicit choices combine these independent dimensions:

| Model | Artifact enum | GATT roles |
| --- | --- | --- |
| P1 | CB | Service FFE5 / write FFE9, service FFE0 / notify FFE4 |
| P2 | JLDP | Same roles; FFF0 is a model marker, never the writer |
| P3 | CB24 | Nordic UART service 6E400001 / write 002 / notify 003 |
| P4 | SleepSnore | Same Nordic UART roles, different frames and parser |

Short UUIDs expand to the Bluetooth base UUID. Nordic UART's suffix is
`-b5a3-f393-e0a9-e50e24dcca9e`. Writes require **write with response**, and
notifications remain enabled even when angle sensing is disabled. Missing
roles or an unsupported write mode fail setup rather than selecting another
app's transport. The last matching GATT role wins in enumeration order.

`auto` uses the app's default **AdjustaBed** layout. The case-sensitive raw name
selects `SLEEP_V` or reconnect name `SleepBT` as P4, `Smartbed` as P3, otherwise
P1; FFF0 refines an automatic non-Nordic model to P2. The app's separate scan
admission lowercases `smartbed`/`okin` but requires case-sensitive `SLEEP_V`.
HA owns scanning; these broad shared names do not change global detection.
Use an explicit variant when the raw name/model cannot identify your receiver.

| Layout | Additional position controls beyond head, foot, flat and zero gravity |
| --- | --- |
| L0 AdjustaLumbarHeadTilt | Neck tilt, lumbar, M1, TV, lounge, anti-snore, lighting |
| L1 AdjustaBed | Head + foot together, TV, lounge, anti-snore, lighting |
| L2 AdjustaMattress | Head + foot together, TV, lounge, anti-snore |
| L3 AdjustaBedLumbar | Lumbar, head + foot together, TV, lounge, anti-snore, lighting |
| L4 FoldingBed | TV, lounge, anti-snore |
| L5 HilowBed | Neck tilt, TV, lounge, anti-snore, lighting |
| L6 Lolobed | Lift head, lift foot, lift up/down, lighting |

Lift labels follow the app. They do not establish a measured height or a new
motor position scale. L5 has no lift command merely because of its name. M1
exists only on L0; no memory programming or additional memory slots exist.
Generic motor counts do not expand these layouts. Profile/variant settings
belong to each physical address; configure each side separately before combining
a two-address pair. A single-address side selector is unsupported.

## Native controls and state

Position covers, standard preset buttons, app-labelled M1/lift/light buttons,
and the generic `adjustable_bed.hold_control` action use the selected layout.
Held identifiers preserve the artifact's method names, such as `headUp`,
`footDown`, `unionUp`, `neckTiltUp`, `lumbarDown`, `liftHead`, `flatPosition`,
`zeroGravity`, `tv`, `lounge`, `anti` and `m1`. Only exposed controls are accepted.
The native card groups massage, lighting, presets and utility settings.

P2 L0/L1/L2/L3/L5 have three dedicated massage selection entities (head, foot,
wave, each index 0..3) and 10/20/30-minute timer buttons. Their bytes are the
app's exact selector/timer commands. P2 L4/L6 and all other models have four
ordinary held steps: head strength, foot strength, wave and massage timer.
There is no generic massage power/off command or universal absolute intensity
setter in this artifact, so those controls are not synthesized.

Alarm hour/minute numbers and action select are **drafts**. Set the Alarm select
to On or Off to commit. Editing an enabled alarm is rejected. On commits repeat
255; Off commits repeat 0 on P1/P3/P4, while P2 uses its all-255 disable sentinel.
Action codes are 0 (app default), 9 (massage), 17 (neutral action code) and 19
(position). No weekday-bit interpretation or physical posture for action 17 is
invented. The commit writes at +200 ms and refreshes the alarm at +600 ms.
Reported alarm fields remain separate from the draft values and wait for replies.
Local drafts and pending strength choices survive BLE reconnects through the
per-address/profile app session. Hydration cannot erase uncommitted edits. Only
the privacy agreement persists across Home Assistant restarts.

P4 L0/L3 additionally expose intelligent anti-snore On/Off, demonstration, sleep,
status refresh, local strength choice and the persisted privacy agreement.
Review the manufacturer's anti-snore privacy notice in its app before marking
that local agreement Accepted. Enabling clears demonstration; disabling preserves
it, so a retained demonstration can still select wire mode 2. Demonstration
requires intelligent anti-snore to be disabled. Strength selection changes the
next command, without an immediate write.

Sleep follows the app's separate path without the privacy gate. Starting while
anti-snore is disabled enables it, forces strength index 1/threshold 35, preserves
demonstration, sends the anti-snore helper immediately and sleep at +200 ms.
Otherwise sleep is immediate. Both query status at +500 ms. Reported sleeping
changes only on notification.

State sensors expose alarm fields, massage time/head/foot/wave (except P2),
and P4 sensitivity/strength, sleeping, enabled, demonstration, busy and the
neutrally named **Auxiliary status bit 1**. It is not labelled occupancy or any
other physical function. No motor angle, percentage, height or current telemetry
exists in the accepted parser. A6 40 busy status clears after 300 ms. Replies do
not validate a checksum; truncated frames are rejected without partial mutation.

## Packets, timing and safety

P1 controls use `E6 FE 16` plus five payload bytes and the complement of the
whole source integer sum. P2 uses `E5 FE 16` plus four payload bytes and that
checksum. P3 uses `05 02` plus five payload bytes. P4 normally uses `06 02` plus
six payload bytes. P4 wave-step and all four L6 lift helpers retain the app's
`05` frames. These exceptions are tested rather than inferred from a family.
Clock/alarm, query, anti-snore and sleep builders have separate formats, including
P3/P4 year/month and byte-order differences. Concrete tests cover all 180 accepted
command/vector rows, including dormant branches retained only as evidence.

Movement and lift first write at +200 ms; presets and cyclic controls write
immediately. Refresh is 200 ms. Every bounded movement/preset/cyclic action
finishes with the model's STOP at +200 ms after release, using a fresh cancellation
event. Ordinary P3/P4 massage then queries at +400 and +600 ms. A task cancellation
finishes cleanup before the command lock is released. The hold action accepts
1..60000 ms. The card sends cancellation immediately on release; all start and
cleanup delays belong to the backend. Awaited write time is subtracted from the
refresh and cleanup waits. A normal button uses the configured pulse count at this cadence.

The following app defects have explicit safety dispositions in the
[discovery ledger](../apk-analysis/dispositions/row067-adjustamattress.md):

- P2 lighting allocates no light frame. It resends the previous arbitrary frame,
  including a prior motor command, and starts refresh. This replay is excluded;
  P2 has no HA lighting action. No replacement opcode is guessed.
- P2 timer release starts unbounded refresh with no paired release STOP. HA
  exposes its exact timer bytes as a bounded action with STOP, excluding the
  orphaned timer. Dormant timer branches on other models are not promoted.
- App timers read one mutable buffer, so unrelated queries/settings can replace
  pending commands or a delayed STOP. HA holds the coordinator command lock for
  the whole operation and uses the operation's own bytes. Cross-operation frame
  substitution and orphaned refresh after disconnect are excluded.
- Phone UI tab/render timers, including the HomeBloc's movement-time shared-buffer
  polling, do not run in HA. Their underlying alarm, massage and status queries
  are explicit native refresh actions, with the evidenced query timing. They
  cannot overwrite an active held motor frame or its STOP.
- Invalid-length crashes, unknown-fragment resets to zero, and missed on-only
  callbacks are phone parser defects. HA guards complete indexed fields, retains
  known telemetry on unknown fragments and publishes valid on-only changes.

Connection/adapter/proxy policy belongs to HA. The controller subscribes before
clock/alarm hydration, retries the FFE notify subscription once after one second,
and does not perform Android-specific MTU/PHY/permission/cache/bond operations.
No app PIN/authentication command, Wi-Fi provisioning, network administration,
cloud/account control, firmware upload or bed reset is recovered. Generic
SDK networking and phone infrastructure are excluded from this BLE-only profile.

## Evidence and hardware validation

Accepted standalone FULL APK audit row067, artifact-set SHA256
`bff51c93b65b5236884608ceb941a6e0bb23ac36cb52f7e852c3d99d919822fb`.
Report seal `69d851737cb7aa08716a98d594cdb8cf45bb20eb4a13d5a825835eb7486e7da4`.
Independent round03 audit accepted all 17 gates, with no findings. The disclosed
historical temporary-cache ownership deviation remains part of the accepted
provenance; implementation does not retroactively waive it. Machine-local raw
artifacts, audit reports and seals are preserved and excluded from Git.

Physical validation is deferred to real users after beta/release: confirm raw
name/GATT selection, layout roles, held release/cancel, alarms, massage replies
and P4 status meanings. No maintainer hardware acquisition or immediate physical
operation is required to complete this static implementation.
