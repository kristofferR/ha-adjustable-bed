# Legacy L&P 2.2.1 implementation disposition

This explicit L&P Adjustable Base (legacy app) controller represents the control
surfaces shipped in `com.richmat.lp` 2.2.1 (13). It is separate from newer
Richmat profiles because the same visible model code and opcode can have
different meanings across app generations. Existing configurations and the
L&P QRRM profile delivered by PR #509 retain their current behavior.

## Evidence identity

The accepted standalone FULL report for queue row019 is recorded in
[issue #443](https://github.com/kristofferR/ha-adjustable-bed/issues/443).
The implementation catalog was derived only from that frozen report, with no
new APK acquisition or decompilation and no changes to the original analysis.

| Identity | SHA-256 |
|---|---|
| APK `com.richmat.lp` 2.2.1 (13) | `7a8016ce13fc2bd0c3e227db98ee7455861fa529c8e9c7d924858edeaa2f5ea3` |
| Frozen `REPORT.SHA256` | `7f8cba0f7121b205d3d9f8d2c00ae53a7f96c82d4d86d7353d6d90843915f8e0` |
| Frozen `analysis.json` | `e69613a435f4c0cc6ec2c28c24430938ed21f9e78452510c325315cb632162a4` |

The machine-local source is
`disassembly/output/phase4-early/com.richmat.lp-2.2.1-20260827/report/`.
Every catalog event retains its `CMD-####` identifier from
`analysis.json.protocols[0].commands`. Form membership, label confidence, and
per-button pairing come from `ledgers/control-actions.json` and
`ledgers/variant-inventory.json`. The committed JSON contains only the durable
integration control table, not raw resources, decompilation, images, or reports.

## Finding dispositions

The 14 finding groups reconcile as **11 IMPLEMENTED, 1 ALREADY IMPLEMENTED,
and 2 EXCLUDED**, with no undispositioned group. The excluded groups below
cover unproven protocol features and 596 application-only events, respectively.

| Finding | Disposition |
|---|---|
| Per-form control surface | Implemented as 122 explicit profiles with 1,715 paired controls and all 3,430 transport events. I0RM has no proven transport controls and remains empty. |
| Two packet modes | Implemented separately per event. Legacy sends the token's first character; framed uses the token's final four hex digits with the additive checksum. Undefined framed encodings stay unavailable. |
| Mode-dependent opcode differences | Implemented without normalizing to generic Richmat opcodes, including 6BRM's `40024` and V8RM's `X0053` and `a0062`. |
| Held and one-shot actions | Implemented with the app's 100 ms tick and exact per-control state. Presets are not universally assumed to be one-shot. |
| Release | Implemented per control: 1,375 explicit releases and 340 state-4 completions. Cancellation must not suppress an explicit paired release. No substitute STOP opcode is invented. |
| Long and short gestures | Implemented as distinct state-3/state-4 behavior; long dispatch occurs after 30 ticks, and short completion only at 30 ticks or fewer. A long press never implies an unrelated memory-programming opcode. |
| Empty-token edge | Implemented: ten controls send no legacy characteristic write, or the framed `6E 01 00 00 6F` frame. Their paired release remains intact. |
| Physical control meanings | App labels and their uncertainty are preserved. Pictograms are not silently converted into verified motor axes, programmable memories, or factory-reset semantics. |
| Discovery/model identity | Explicit device and four-character profile selection. The report contains no fixed advertised-name, service-data, manufacturer-data, or UUID filter suitable for passive discovery. |
| GATT selection | Explicit runtime characteristic selection is required. No UUID or fallback is borrowed from a different app or inferred from the model code. |
| Notification meanings | Exact three report frames are documented below; no position, battery, or alarm meaning is invented. |
| RGB, split synchronization, authentication, firmware update, position sensing | Excluded: this artifact proves no corresponding reachable protocol. Generic Richmat capability defaults do not apply to these profiles. |
| LP-QRRM support | Already implemented by PR #509; this is a separate profile and remains unchanged. QRRM is absent from this artifact's 122-form catalog. |
| Phone flashlight, local/UI actions and lifecycle | Excluded from bed command catalog with exact counts below. Home Assistant owns application lifecycle and BLE connection management. |

The 4,026 serialized events reconcile as follows:

| Disposition | Events |
|---|---:|
| Normal press commands | 1,705 |
| Conditional state-4 commands | 340 |
| Empty-token transport edge | 10 |
| Explicit releases | 1,375 |
| Phone flashlight | 179 |
| Local-only, no transport | 28 |
| BLE lifecycle/state | 4 |
| Application lifecycle/state | 51 |
| UI/navigation | 334 |

The 1,715 command pairs are: 1,245 hold/release pairs (state 1/2),
250 hold/conditional-completion pairs (1/4), 90 long/short pairs (3/4), and
130 one-shot/release pairs (5/2). The catalog exposes exact app control names;
all transport labels are marked INFERRED, TENTATIVE, or UNKNOWN by the report.
None is promoted to a physically verified claim.

### Frozen-report timing detail

The ten empty-token command rows omit `timing.state` in `analysis.json`.
Their state was recovered during this comparison from the already-frozen
`ledgers/app-control-disassembly.txt`, without changing the accepted report:

| Controls | State evidence |
|---|---|
| I4RM, I5RM, UARM, UJRM, V7RM, ZRI0 empty MASSAGE controls | State 5: `r1 = 5` immediately before `e3bc3c`, at `e5aab6`, `e5aee6`, `e68306`, `e6a42a`, `e6da42`, `e76d22`. |
| I6RM UP/DOWN | State 1: `r1 = 1` before `e3b97c` at `e5b1a6`. |
| U3RM UP/DOWN | State 1: `r1 = 1` before `e3b97c` at `e6622c` and `e66460`. |

The states match the setter/dispatch logic already frozen in
`ledgers/property-and-send-disassembly.txt`. This is a narrow interpretation of
existing evidence, not a new clean-room analysis or an amendment to its claims.

### Runtime and hardware boundaries

The GATT callback `e46e2c` chooses service/characteristic list entries and branches
on properties. The report provides no fixed UUID and does not explicitly choose
ATT write-with-response versus write-without-response. A real runtime GATT table
and write opcode remain external validation. Configuration therefore requires
the actual write characteristic and packet mode for the selected device.

The exact notification frames are `6E 09 01 00 78` (sets an app status field to 5),
`6E 07 01 01 77`, and `6E 07 01 02 78` (two unnamed app alarm/state routines).
Other frames are ignored by the app. These are not motor position measurements.
Physical meanings, representative gestures, and real QR/device routing remain
validation requests for users with hardware after a beta or release.

## Complete form disposition

Every nonempty row is represented in the durable catalog with its exact controls.
The counts include empty-token controls. A framed count includes only controls
whose press and completion both have defined framed encodings. A zero framed
count never causes an automatic fallback to legacy mode.

| Form code | Controls | Framed controls | Disposition |
|---|---:|---:|---|
| `6BRM` | 6 | 6 | Implemented |
| `A2RM` | 18 | 0 | Implemented |
| `A3RM` | 20 | 0 | Implemented |
| `A6RM` | 6 | 0 | Implemented |
| `A7RM` | 6 | 6 | Implemented |
| `B1RM` | 11 | 0 | Implemented |
| `B2RM` | 2 | 0 | Implemented |
| `B6RM` | 6 | 0 | Implemented |
| `B6RU` | 6 | 0 | Implemented |
| `B7RM` | 7 | 0 | Implemented |
| `B8RM` | 8 | 0 | Implemented |
| `B8TT` | 8 | 8 | Implemented |
| `B9TT` | 11 | 11 | Implemented |
| `BERM` | 23 | 0 | Implemented |
| `BZRM` | 20 | 0 | Implemented |
| `D2RM` | 16 | 0 | Implemented |
| `D4RM` | 19 | 19 | Implemented |
| `GMRM` | 6 | 0 | Implemented |
| `GVRM` | 11 | 0 | Implemented |
| `I0RM` | 0 | 0 | Excluded: no proven transport |
| `I1RM` | 18 | 0 | Implemented |
| `I2RM` | 17 | 17 | Implemented |
| `I3RM` | 13 | 13 | Implemented |
| `I4RM` | 18 | 18 | Implemented |
| `I5RM` | 21 | 21 | Implemented |
| `I6RM` | 4 | 2 | Implemented |
| `I7RM` | 13 | 13 | Implemented |
| `I8RM` | 14 | 0 | Implemented |
| `I9RM` | 8 | 8 | Implemented |
| `IARM` | 16 | 16 | Implemented |
| `IBRM` | 17 | 0 | Implemented |
| `ICRM` | 15 | 0 | Implemented |
| `IDRM` | 11 | 0 | Implemented |
| `IERM` | 14 | 0 | Implemented |
| `IFRM` | 8 | 8 | Implemented |
| `M3RM` | 20 | 2 | Implemented |
| `M5RM` | 17 | 0 | Implemented |
| `M9RM` | 8 | 8 | Implemented |
| `MLRM` | 18 | 17 | Implemented |
| `MMRM` | 22 | 0 | Implemented |
| `MRRM` | 20 | 0 | Implemented |
| `O1RM` | 20 | 0 | Implemented |
| `O2RM` | 20 | 0 | Implemented |
| `O3RM` | 20 | 0 | Implemented |
| `O4RM` | 19 | 2 | Implemented |
| `OMRM` | 20 | 0 | Implemented |
| `ONRM` | 20 | 0 | Implemented |
| `OORM` | 19 | 16 | Implemented |
| `OPRM` | 20 | 20 | Implemented |
| `P9RM` | 7 | 0 | Implemented |
| `R2RM` | 23 | 0 | Implemented |
| `R5RM` | 20 | 20 | Implemented |
| `R6RM` | 19 | 0 | Implemented |
| `S9RM` | 8 | 8 | Implemented |
| `SARM` | 7 | 7 | Implemented |
| `T1RM` | 11 | 0 | Implemented |
| `THRM` | 20 | 0 | Implemented |
| `TLRM` | 7 | 7 | Implemented |
| `TWRM` | 8 | 0 | Implemented |
| `TZRM` | 7 | 0 | Implemented |
| `U1RM` | 20 | 20 | Implemented |
| `U2RM` | 20 | 0 | Implemented |
| `U3RM` | 21 | 2 | Implemented |
| `U4RM` | 20 | 20 | Implemented |
| `U5RM` | 22 | 22 | Implemented |
| `U7RM` | 10 | 10 | Implemented |
| `U8RM` | 11 | 11 | Implemented |
| `U9RM` | 18 | 17 | Implemented |
| `UARM` | 19 | 19 | Implemented |
| `UBRM` | 19 | 18 | Implemented |
| `UCRM` | 11 | 0 | Implemented |
| `UERM` | 20 | 0 | Implemented |
| `UFRM` | 20 | 20 | Implemented |
| `UGRM` | 20 | 0 | Implemented |
| `UHRM` | 20 | 0 | Implemented |
| `UIRM` | 11 | 11 | Implemented |
| `UJRM` | 19 | 1 | Implemented |
| `UKRM` | 20 | 0 | Implemented |
| `ULRM` | 17 | 1 | Implemented |
| `UMRM` | 11 | 11 | Implemented |
| `UNRM` | 21 | 21 | Implemented |
| `UORM` | 11 | 11 | Implemented |
| `UPRM` | 11 | 11 | Implemented |
| `V1RM` | 8 | 8 | Implemented |
| `V2RM` | 20 | 0 | Implemented |
| `V3RM` | 8 | 0 | Implemented |
| `V4RM` | 21 | 21 | Implemented |
| `V5RM` | 7 | 0 | Implemented |
| `V6RM` | 13 | 0 | Implemented |
| `V7RM` | 20 | 1 | Implemented |
| `V8RM` | 20 | 20 | Implemented |
| `V9RM` | 17 | 0 | Implemented |
| `VARM` | 10 | 0 | Implemented |
| `VBRM` | 16 | 16 | Implemented |
| `VCRM` | 20 | 20 | Implemented |
| `VDRM` | 16 | 0 | Implemented |
| `VERM` | 19 | 19 | Implemented |
| `VFRM` | 20 | 20 | Implemented |
| `VGRM` | 8 | 0 | Implemented |
| `VHRM` | 9 | 0 | Implemented |
| `VIRM` | 17 | 17 | Implemented |
| `VJRM` | 6 | 6 | Implemented |
| `VKRM` | 16 | 0 | Implemented |
| `VLRM` | 16 | 0 | Implemented |
| `VMRM` | 13 | 0 | Implemented |
| `VNRM` | 16 | 1 | Implemented |
| `W2RM` | 20 | 0 | Implemented |
| `X1RM` | 7 | 7 | Implemented |
| `Y2RM` | 8 | 0 | Implemented |
| `Y3RM` | 17 | 0 | Implemented |
| `ZR00` | 4 | 4 | Implemented |
| `ZR01` | 2 | 2 | Implemented |
| `ZR10` | 11 | 11 | Implemented |
| `ZR11` | 11 | 11 | Implemented |
| `ZR20` | 6 | 6 | Implemented |
| `ZR30` | 6 | 6 | Implemented |
| `ZR40` | 7 | 7 | Implemented |
| `ZR50` | 23 | 23 | Implemented |
| `ZR60` | 8 | 8 | Implemented |
| `ZR70` | 10 | 10 | Implemented |
| `ZR80` | 12 | 12 | Implemented |
| `ZRI0` | 18 | 18 | Implemented |
