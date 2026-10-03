# FurniMove / OKIN Smart Remote

**Status:** APK and production API behavior verified; hardware validation pending.

This explicit app profile comes from `com.okin.okinsmartcomfort` **2.2.0 (19)**,
including its complete 19-APK artifact set and production API tables captured
on 2026-09-30. The clean-room report passed independent acceptance before the
integration comparison. [The discovery ledger](../apk-analysis/dispositions/157-furnimove.md)
records every implemented behavior and exclusion. Ref [#633](https://github.com/kristofferR/ha-adjustable-bed/issues/633)
and [#556](https://github.com/kristofferR/ha-adjustable-bed/issues/556).

## Choosing the layout

Choose **FurniMove / OKIN Smart Remote** and select the exact handset ID used
in the FurniMove app, matching the physical remote. There is no automatic
handset choice. RF ECO BT, P1103 and shared OKIN UUIDs identify a receiver or
transport, not its number of motors or command layout. Issue #633 establishes
use of FurniMove; #556's receiver label alone does not establish its app.
For another app, select that app's documented integration profile.

The integration includes **87 production IDs, 39 distinct tables and 1,092
ordered rows**, plus the two shipped local aliases `280702`/`280703` and the
five-row offline table `00000`. All known IDs and metadata references were
queried in production and the four shipped alternate environments; filtered
brand/active queries found no further referenced production mappings.
Alternate debug-environment tables do not replace missing production IDs.
The captured catalog is finite, not a claim to enumerate every future API ID.

### One bed type per handset

This catalog is also the keycode source for the 86 handsets that the
[Okin UUID](okimat.md) and [Okin DOT](okin-dot.md) bed types list. Their
earlier backend capture matched it byte for byte, including memory-save
timing, so those bed types now derive the keycodes from here. New setups offer
each handset under one bed type only:

| Handsets | New setups use | Why |
|---|---|---|
| 83 standard handsets also listed under Okin UUID | Okin UUID | It adds the mandatory BLE bond and FFE4 position feedback that this app profile lacks, so FurniMove is not a superset there. |
| DOT handsets 90167, 91983, 93558 | FurniMove | Neither route bonds or reports positions. FurniMove adds the app's per-control frame format and reported light state. |
| 12234, `00000`, `280702`, `280703` | FurniMove | No other bed type lists them. |
| DOT handsets 97450, 97544, 98035 | Okin DOT | They are not in the FurniMove capture. |

Existing entries keep working unchanged. An Okin DOT entry using 90167, 91983
or 93558 receives the repair described below.

Discovery follows the same split. DewertOkin manufacturer data, the `1523`
service and the RF-Gateway service keep their confident DewertOkin route, with
FurniMove listed as an optional app candidate. The app's gateway service
`00001420-0000-1000-8000-00805f9b34fb` is its last acceptance rule, so it only
proposes FurniMove when nothing else matched; with another match it adds
FurniMove as a candidate without overriding it.

Motor count, massage availability and action ordering come from the selected
table. An unavailable ID requires a new verified table; the integration does
not contact the cloud or ship the app's API credential. Motor position and
angle sliders are absent because this app reports no motor positions.

## Repairing existing configurations

After upgrading, every legacy **RF ECO BT single actuator** entry without an
explicit staircase confirmation receives a fixable warning under **Settings →
System → Repairs**, even if connection fails. A saved count of one motor does
not establish the product. The repair offers these choices:

- **FurniMove adjustable bed:** choose the exact handset layout, restoring the
  selected axes. Handsets that stay on the Okin UUID route are not listed.
- **Single-actuator staircase:** retain its one Stair cover.
- **Keep current configuration:** dismiss the repair without changing any
  setting. A full OKIMAT bed saved as RF ECO BT is promoted at runtime (#406);
  set its printed handset code under Okin UUID in the integration options.

A FurniMove entry without a captured handset gets the first two choices.

An **Okin DOT** entry using handset 90167, 91983 or 93558 receives a separate
fixable warning offering **Switch to the FurniMove profile** or **Keep current
configuration**. Switching keeps the handset and derives the axes and massage
availability from its table.

Each repair updates the same config entry. Bluetooth address, device ownership,
entry identity and matching entity IDs remain intact. A retired Stair cover,
unsupported axes and obsolete app action/state entities are removed. A paired
repair changes only its selected physical side. FurniMove conversion clears
obsolete mandatory-pairing state and the old pairing repair; it never removes
an operating-system bond. Saving the matching profile in integration options
also clears the layout repair on the next setup.

## Controls and actions

Motor rows map `M1` to Head, `M2` to Back, `M3` to Legs and `M4` to Feet.
Only axes with their exact Out/In rows are exposed. Named presets and utility
buttons are selected by the first exact name, independently of category.
Memory slots preserve all ordered `memory` rows; arbitrary `memory-preset`
labels remain separate named buttons. QuietSleep and Snore are separate
commands. Save-memory uses the requested ordered slot.

All reachable non-actuator rows also have named buttons, with indexed keys
that distinguish duplicate labels. Diagnostics list every captured row and the
reachable row indexes. Actions use the shared command lock and all-target
validation; paired sides retain their own profiles.
An ordered row must have the same action name and category on every target.
If it differs, select one device or physical side instead.

| Action | Parameters | Behavior |
|--------|------------|----------|
| `adjustable_bed.furnimove_action` | `device_id`, `row_index`, optional `duration`, `consumer`, `side` | Dispatch an ordered row through its app consumer. Hold duration is seconds; only held consumers accept an override. `widget` retains its fixed whitelist and timing. |
| `adjustable_bed.furnimove_move_simultaneously` | `first_motor`, `second_motor`, their `*_direction`, `duration_ms`, target | Combine two supported axes with full-frame OR and the RF checksum rule. |
| `adjustable_bed.furnimove_massage_program` | `program` 1–4, target | Programs 1, 2, 3 and Wave (4), including the source queue and local repeated-click behavior. |
| `adjustable_bed.furnimove_massage_duration` | `minutes` 10, 15, 20 or 30, target | Local advisory preference, not a hardware timer. It sends no duration packet and expiry does not stop massage. |
| `adjustable_bed.rename` | `name`, one physical target | Unique name, at most 18 UTF-16 units after trimming. Writes the original untrimmed UTF-8 text, then saves the trimmed name. |

Massage intensity and zone controls use the exact app factory, including its
150 ms queues, Head/Feet ordering, Wave behavior and missing-key zero frames.
Those factory frames do not authorize a generic zero STOP. Massage running,
zone, intensity, program and duration sensors describe **local app state**,
not receiver acknowledgement. Active zone/intensity and duration survive HA
restarts; the program-click counter is retained across reconnects within one
coordinator, matching the app's separate in-process behavior.
Program selection accepts only programs present in the selected handset table;
the mode-step button cycles those programs and is hidden when none are available.
Wave intensity requires a `Massager3` row. The separate Wave program (4)
requires `MassagerWave`, so a handset can offer that program without wave intensity.

UBL is a toggle button plus reported binary state, rather than a fabricated
discrete on/off switch. Sync and Child Lock have exact command buttons and
reported booleans; Sync does not infer physical paired-side addressing.
Hardware booleans are retained across the same coordinator's reconnects, but
are not restored from storage as proof of current receiver state.
The first valid feedback publishes reported off values even when they match
the controller's defaults, so HA sensors leave unknown without needing an on transition.

## Transport and packet construction

GATT roles are selected across all discovered services, preserving ordered
last-match characteristic instances. RF rename presence selects the old frame;
CSS feedback can clear that flag. DOT selection is independent. A characteristic
instance is used for writes when UUIDs repeat. Bleak's write response mode follows
the discovered write properties; the APK sets no explicit Android write type.

| Role | UUID |
|------|------|
| Ordinary command | `62741525-52f9-8864-b1ab-3b3a8d65950b` |
| Ordinary feedback | `62741625-52f9-8864-b1ab-3b3a8d65950b` |
| DOT command | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` |
| DOT feedback | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` |
| CSS write / feedback | `90311625-25fa-3346-12ef-3cfb7a2556ac` / `90311725-25fa-3346-12ef-3cfb7a2556ac` |
| RF rename | `92111422-72ab-4564-62ef-2a881286a6b0` |
| GAP name | `00002a00-0000-1000-8000-00805f9b34fb` |

Valid four-byte keycodes produce these frames:

- P1: `04 02` followed by the big-endian payload.
- P2: `e5 fe 16`, four payload bytes and the complemented low byte of the sum
  of all initialized frame bytes. RF wins when RF and DOT flags are both set.
- P3: `05 02`, four payload bytes and `00`.

DOT is passed by main controls, favorites and Sync/Child Lock. Memory
programming, massage, functioning-mode controls and widgets omit DOT, so they
use P1 even on a DOT connection unless RF selects P2. Composite commands OR
complete frames; RF combinations recalculate the checksum over the first
seven bytes.

## Timing, release and connection

Held main/favorite commands refresh at **100 ms**. HA bounds and serializes
that refresh instead of reproducing Android callback races. Release uses the
first `DisobeyStandbyTime` row only when present, with an uncancelled cleanup
signal. Main release stops refresh at 100 ms and, for non-DOT, sends the optional
second release at 200 ms. DOT queries `00 b0` after 400 ms at startup and
200 ms after **UBL** release; ordinary axis release has no such query.
The offline table has no release row: ending refresh is its entire STOP.

Memory programming sends MemoSave, its row-duration/frequency repeats, ends
refresh after one frequency interval, sends the selected slot after two, then
ends refresh after three. It does not invent a release opcode. Functions use
their row timers and source-specific completion checks. Consumer cleanup is
completed inside the command lock; an explicit STOP after cancellation does
not append a release from a different consumer.

The app's `createBond()` request is advisory and immediately followed by
connection; it does not await or prove a bond. HA connects without `pair=True`
and does not gate FurniMove startup on an encrypted probe. For eligible named,
unbonded receivers it makes an owned background bond request after GATT discovery,
as a Bleak adaptation. Failure, unsupported backends or the operational five-second
bound leave ordinary control available. Client replacement, disconnect and unload
cancel and join that task. An existing OS bond or an `okinmat`-prefixed name skips
it; request completion never becomes a persisted bond-proof marker.

## Feedback

At least ten bytes are required. Ordinary `08/09 0b` frames AND the two big-endian
32-bit words at offsets 2 and 6. RF `*5/*6 fe` frames use the word at offset 3 or
4 and state selector `06`/`07`; RF and ordinary parsing are gated by the live
RF selection. UBL, Sync and Lock masks are respectively `0x00020000`,
`0x10000000` and `0x04000000`. Exact CU170 uses its separate byte masks and
retains Sync for byte 9 equal to 4. DOT's preliminary byte-13 UBL update can
then be overridden by the ordinary/CU170 path. CSS notifications have no payload
consumer. These paths report no motor angle, battery or current measurement.

## Captured layouts

The setup selector contains every row below. Axes reflect reachable named
commands; action and memory counts preserve captured ordering and aliases.

| ID | Description | Axes | Rows | Memory | Massage | Source |
|----|-------------|------|------|--------|---------|--------|
| `12234` | RF HS-Elegance T silver - black | Head, Back, Legs, Feet | 29 | 4 | Yes | production |
| `80599` | RFS-ELLIPSE/SW-SW-06-1844/-/-/-/02 GR/---/--/2 ... | Back, Legs | 9 | 0 | No | production |
| `80601` | RFS-ELLIPSE/SW-SW-09-1845/-/-/M/02 GR/UBB/--/2 ... | Back, Legs | 11 | 1 | No | production |
| `80602` | RFS-ELLIPSE/WA-SW-06-1902/-/-/-/02 SW/---/--/2 ... | Back, Legs | 9 | 0 | No | production |
| `80603` | RFS-ELLIPSE/WS-SW-09-1845/-/-/M/02 | Back, Legs | 11 | 1 | No | production |
| `80604` | RFS-ELLIPSE/WA-SW-09-1845/-/-/M/02 SW/UBB/--/2 ... | Back, Legs | 11 | 1 | No | production |
| `80608` | RFS-ELLIPSE/WA-SW-06-1844/-/-/-/02 SW/---/--/2 ... | Back, Legs | 9 | 0 | No | production |
| `80616` | RFS-ELLIPSE/WS-SW-06-1844/-/-/-/02 GR/---/--/2 ... | Back, Legs | 9 | 0 | No | production |
| `80673` | "REMOTE CONTROL 2,4GHz ECO 2MOT. SW/E.VP/m.BA." | Back, Legs | 9 | 0 | No | production |
| `80674` | "REMOTE CONTROL 2,4GHz ECO 2MOT. SW/E.VP/m.BA./ ..." | Back, Legs | 9 | 0 | No | production |
| `80675` | "REMOTE CONTROL 2,4GHz ECO 2MOT. WA/E.VP/m.BA." | Back, Legs | 9 | 0 | No | production |
| `80676` | "SET REMOTE CONTROL 2,4GHz ECO 2MOTORIG SENDER ..." | Back, Legs | 9 | 0 | No | production |
| `80683` | "SET REMOTE CONTROL 2,4GHz ECO 2MOTORIG SENDER ..." | Back, Legs | 9 | 0 | No | production |
| `80685` | "SET REMOTE CONTROL 2,4GHz ECO 2MOTORIG SENDER ..." | Back, Legs | 9 | 0 | No | production |
| `81619` | "REMOTE CONTROL 2,4GHz ECO 1MOTORIG" | Back | 5 | 0 | No | production |
| `81620` | "SET REMOTE CONTROL 2,4GHz ECO 1MOTORIG" | Head | 5 | 0 | No | production |
| `82292` | RF-TOUCH/BRW/BK/14/2006 | Back, Legs | 14 | 2 | No | production |
| `82295` | RF-TOUCH/BRW/BK/19/2004 | Head, Back, Legs, Feet | 18 | 3 | No | production |
| `82417` | RF-TOPLINE SI/BK/BK/07 | Back, Legs | 9 | 0 | No | production |
| `82418` | RF-TOPLINE SI/BK/BK/11 | Back, Legs | 12 | 2 | No | production |
| `82620` | RF-TOPLINE BK/BK/BK/07/H | Back, Legs | 9 | 0 | No | production |
| `82634` | RF-TOPLINE BK/BK/BK/11 | Head, Back, Legs | 12 | 0 | No | production |
| `82635` | RF-TOPLINE BK/BK/BK/11/H | Head, Back, Legs | 12 | 0 | No | production |
| `82755` | RF-TOPLINE SI/BK/BK/03 | Head | 5 | 0 | No | production |
| `82757` | RF-TOPLINE BK/BK/BK/07/L | Back, Legs | 9 | 0 | No | production |
| `82760` | RF-TOPLINE BK/BK/BK/07/L | Back, Legs | 9 | 0 | No | production |
| `82764` | RF-TOPLINE BK/BK/BK/07/L | Back, Legs | 9 | 0 | No | production |
| `82767` | RF-TOPLINE BK/BK/BK/07/L | Back, Legs | 9 | 0 | No | production |
| `82770` | RF-TOPLINE SI/BK/BK/07/L | Back, Legs | 9 | 0 | No | production |
| `82785` | RF-TOPLINE BK/BK/BK/11 | Head, Back, Legs | 12 | 0 | No | production |
| `82786` | RF-TOPLINE SI/BK/BK/11/L | Head, Back, Legs | 12 | 0 | No | production |
| `82790` | RF-TOPLINE BK/BK/BK/11 | Head, Back, Legs | 12 | 0 | No | production |
| `82794` | RF-TOPLINE BK/BK/BK/11/L | Head, Back, Legs, Feet | 14 | 0 | No | production |
| `82795` | RF-TOPLINE BK/BK/BK/11/L | Head, Back, Legs, Feet | 14 | 0 | No | production |
| `82796` | RF-TOPLINE SI/BK/BK/11/L | Head, Back, Legs, Feet | 14 | 0 | No | production |
| `82797` | RF-TOPLINE BK/BK/BK/11/L | Head, Back, Legs, Feet | 14 | 0 | No | production |
| `82799` | RF-TOPLINE SI/BK/BK/11 | Head, Back, Legs, Feet | 14 | 0 | No | production |
| `83060` | RF-TOUCH/BRW/BK/14/2182/L | Back, Legs | 14 | 2 | No | production |
| `83126` | RF-TOUCH/BRW/BK/19/2114 | Back, Legs | 27 | 3 | Yes | production |
| `83219` | RF-TOUCH/BRW/BK/24/2068/- | Head, Back, Legs, Feet | 30 | 3 | Yes | production |
| `83358` | RF-TOPLINE BK/BK/BK/07 | Back, Legs | 9 | 0 | No | production |
| `83462` | SET RF-TOPLINE SI/BK/BK/07/M2/ST/DP2/LI/FL | Back, Legs | 9 | 0 | No | production |
| `83489` | RF-TOPLINE SI/BK/BK/11/L | Back, Legs | 9 | 0 | No | production |
| `84148` | "REMOTE CONTROL 2,4GHz ECO 2MOTORIG" | Back, Legs | 9 | 0 | No | production |
| `84149` | "SET REMOTE CONTROL 2,4GHz ECO 2MOTORIG" | Back, Legs | 9 | 0 | No | production |
| `84150` | "REMOTE CONTROL 2,4GHz ECO 2MOTORIG" | Back, Legs | 9 | 0 | No | production |
| `84151` | "SET REMOTE CONTROL 2,4GHz ECO 2MOTORIG" | Back, Legs | 9 | 0 | No | production |
| `84562` | RF-ECO+/06/AL/BK/L | Back, Legs | 9 | 0 | No | production |
| `84563` | RF-ECO+/07/AL/BK/L | Back, Legs | 9 | 0 | No | production |
| `84564` | RF-ECO+/09/AL/BK/L | Head, Back, Legs | 11 | 0 | No | production |
| `84582` | RF-ECO+/05/AL/BK/L | Head | 7 | 0 | No | production |
| `84931` | RF-TOPLINE/07/AL/BK/L | Back, Legs | 9 | 0 | No | production |
| `84963` | RF-TOPLINE/07/BK/BK/L | Back, Legs | 8 | 0 | No | production |
| `85057` | RF-TOPLINE/11/AL/BK/L | Head, Back, Legs, Feet | 17 | 4 | No | production |
| `85058` | RF-TOPLINE/11/AL/BK/L | Back, Legs | 12 | 2 | No | production |
| `85124` | RF-LITE/06/BK/BK | Back, Legs | 9 | 0 | No | production |
| `85126` | SET RF-LITE/06/BK/BK/M2/S/IP20 | Back, Legs | 9 | 0 | No | production |
| `88875` | RF-LITELINE/07/ | Back, Legs | 9 | 0 | No | production |
| `88877` | RF-LITELINE/07/ | Back, Legs | 9 | 0 | No | production |
| `89137` | RF-LITELINE/07/ | Back, Legs | 9 | 0 | No | production |
| `89138` | RF-LITELINE/07/ | Back, Legs | 9 | 0 | No | production |
| `89139` | RF-LITELINE/07/ | Back, Legs | 9 | 0 | No | production |
| `89476` | RF-TOPLINE/11/AL/BK | Head, Back, Legs, Feet | 18 | 4 | No | production |
| `90167` | RF1058 | Head, Feet | 23 | 4 | Yes | production |
| `90269` | RF-STYLE/07/WH/WH | Back, Legs | 14 | 4 | No | production |
| `90354` | RF-STYLE/07/WH/WH | Head, Back, Legs | 14 | 2 | No | production |
| `90658` | RF-TOUCHLINE/15/BK/BK/KL | Head, Back | 16 | 4 | No | production |
| `90675` | RF-TOUCHLINE/15/AL/BK/KL | Head, Back | 16 | 4 | No | production |
| `90678` | RF-TOUCHLINE/19/AL/BK/KL | Head, Back, Legs, Feet | 20 | 4 | No | production |
| `90679` | RF-TOUCHLINE/19/BK/BK/KL | Head, Back, Legs, Feet | 20 | 4 | No | production |
| `90916` | RF-TOUCHLINE/21/AL/BK/KL | Head, Back, Legs, Feet | 29 | 2 | Yes | production |
| `90918` | RF-TOUCHLINE/21/AL/BK/KL | Back, Legs | 27 | 3 | Yes | production |
| `91244` | RF-FLASHLINE/07/WH/GY | Back, Legs | 8 | 0 | No | production |
| `91246` | RF-FLASHLINE/09/WH/GY | Back, Legs | 11 | 2 | No | production |
| `91914` | RF-TOUCH/23/WH/BK/KL | Head, Back, Legs, Feet | 30 | 3 | Yes | production |
| `91983` | RF1058 (91983) with CU458-2 (92264) and/or HE200 (90168 | Head, Feet | 21 | 3 | Yes | production |
| `92113` | RF-STYLE/BK/BK/14/2009 | Back, Legs | 14 | 4 | No | production |
| `92461` | \n  RF-TOPLINE\n  SI/BK/BK/07\n | Back, Legs | 9 | 0 | No | production |
| `92535` | RF-LITELINE/07/ | Back, Legs | 9 | 0 | No | production |
| `92591` | RF-FLASHLINE/09/WH/GY | Back, Legs | 11 | 2 | No | production |
| `93025` | RF-STYLE/07/WH/WH | Back, Legs | 9 | 0 | No | production |
| `93300` | RF-STYLE/07/WH/WH | Back, Legs | 14 | 4 | No | production |
| `93305` | RF-TOPLINE SI/BK/BK/07 | Back, Legs | 9 | 0 | No | production |
| `93306` | RF-TOPLINE SI/BK/BK/11 | Back, Legs | 12 | 2 | No | production |
| `93329` | RF-TOPLINE/15/AL/BK/M3/S/ST/IP20/BLI/FL/LED/M | Head, Back, Legs | 17 | 4 | No | production |
| `93332` | RF-TOPLINE/15/AL/BK/M4/S/ST/IP20/BLI/FL/LED/M | Head, Back, Legs, Feet | 17 | 2 | No | production |
| `93558` | RF1058 | Head, Feet | 21 | 3 | Yes | production |
| `00000` | Offline two-motor controls | Back, Legs | 5 | 0 | No | shipped-offline |
| `280702` | RF-TOPLINE SI/BK/BK/11 | Back, Legs | 9 | 0 | No | shipped-local |
| `280703` | RF-TOPLINE SI/BK/BK/11 | Back, Legs | 9 | 0 | No | shipped-local |
