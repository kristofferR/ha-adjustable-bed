# Vibradorm app profiles: Caresse and Werkmeister

The accepted static protocol/profile behavior is implemented with concrete code and executed-test bindings in the [row031 disposition ledger](../apk-analysis/row031-dispositions.md). Existing generic Vibradorm entries retain their current controller and position behavior.

| Accepted artifact | Version | APK SHA-256 |
|---|---|---|
| `de.vibradorm.diamant` (Caresse Remote) | 0.3, code 3 | `61073fa141df96bc40cbdd5820e64e2fb19c53cb88334baeaf6772493cfd97c2` |
| `de.vibradorm.werkmeister` (Werkmeister Unterfederung) | 0.2, code 2 | `36306b6ac6ee3fd66bef5a71e3626c44e2befccb3d2e135031747bcd5c7f9635` |

The complete artifact sets, independent package audits and whole-cluster reconciliation are accepted static evidence. Hardware operation, on-air packet delivery, peripheral security and physical effects remain unverified. Real-user checks after beta/release are deferred external validation, not missing static implementation evidence.

## Explicit profiles and retained state

Preserve generic Vibradorm behavior for existing entries. An explicit app/product profile selects a separate `VibradormAppController`; advertisement, DIS strings, service/characteristic presence and remote artwork cannot choose a profile or actuator layout.

| App/state | Control | Named movement groups | Transport | Memory | Optional features |
|---|---:|---|---|---|---|
| Caresse fresh shipped selection |2|back,legs|COMMAND single byte|0|all false|
| Werkmeister remote image cdl_bf_11_21_374_vi |5|back,legs|CBI two bytes|6 programmable|floor light; sync inert; RGB/massage/extension false|
| Werkmeister remote image cdl_cf_17_21_382_vi |7|head/neck,back,legs,feet|CBI two bytes|6 programmable|floor light and sync; RGB/massage/extension false|
| Caresse explicit restored state |2|back,legs|COMMAND|0|independent persisted floor/RGB/massage/extension flags|
| Caresse explicit restored seat state |3|head/neck,back,legs|COMMAND|3 recalls; no save menu|same flags|
| Caresse explicit restored state |0 or 5|back,legs|CBI|6 programmable|same flags; article only 5|
| Caresse explicit restored state |4 or 6|head/neck,back,legs|CBI|6 programmable|same flags; article only 6|
| Caresse explicit restored state |-1, 1 or 7|head/neck,back,legs,feet|CBI|6 programmable|same flags; article only 7|
| Caresse explicit restored layout without motor controls |outside{-1,0,1,2,3,4,5,6,7}|none|CBI|6 programmable|same flags; no article transaction|

The last row uses the explicit `other` sentinel for the source default switch branch. It has no motor controls; unknown numeric values are rejected. For Caresse restored type 2 is allowed: feature flags are independent persisted reads. Do not constrain restored states solely to non-normal control values. Fresh selection is type 2/all false. Werkmeister accepted own-selector scope is 5/7; its dead selectors/features are excluded and are not promoted into supported Werkmeister options by Caresse evidence.

All counts above describe app movement groups. They do not prove physical motor topology. Hide conflicting generic motor-count/has-massage/angle/repeat-delay options for explicit profiles; derive exposed groups and limits from the chosen profile. Restore/profile changes must rebuild forms in every setup and options path while preserving entered suggestions, then persist the exact profile. Explicit advanced restored settings must explain that they describe retained app paths rather than a verified hardware product.


## Frame construction and local intent

Use each accepted package's exact source/vector bindings. Basic iff control types 2/3. COMMAND/LIGHT/CBI/CBI_RESPONSE are exact characteristic identities; service membership is not an app requirement. Select the first requested exact characteristic in native service order, and retain that selected object for the actual read/write/notification operation. No arbitrary writable/notifiable or `1528`/`1534`/proxy-base alias fallback is proven for these app profiles. Validate actual operation properties and use the selected host backend's write semantics; APK leaves Android native write type/property metadata at runtime, so it does not prove a universal response=False/True mode.

Caresse basic motor writes are single-byte commands; nonbasic and Werkmeister motor/recall writes are `BE16(opcode | T)` on CBI. STOP is literal `ff` on COMMAND for basic, literal `00ff` on CBI for nonbasic. STOP does not advance T. The exact packet remains unchanged through the host BLE transport; no app checksum, framing, crypto, MTU operation, side byte or fragmentation is added.

T starts at 0 at MC construction. Logical command construction/enqueue consumes the current T then advances it before a BLE result. Held repeats reuse the same constructed header; they do not alternate per repeat. Article literals and STOP do not advance it. Preserve caller and execution-stage differences:

- floor toggle performs a preadvance before writeFloorLight; CBI construction consumes/advances T again;
- CmdLightCBI.execute captures its header then advances global T before the write; level consumes 2 advances, toggle 3 in a serialized CBI action;
- direct basic LIGHT construction/execution consumes no T; direct floor-toggle only consumes its preadvance;
- Store consumes 5 logical advances. Four Store headers `T / T^8000 / T / T^8000`; selected-slot frame is literal `00<slot>`; then four literal `00ff` STOP frames, all CBI. The source wrong receiver assignment preserves these bytes and a total of 5 advances. No invented long-press threshold or storage ACK;
- immutable host command snapshots replace unsafe shared static argument aliasing; exact source alias counterexamples remain documented/excluded. Profile-local intent survives a failed/dropped write where the source constructs it first. The execution-only light advance occurs when execution begins, not merely when dropped queued work is removed.

The profile matrix and the complete source-driven discovery dispositions determine each reachable command and its preconditions. Eight normal motor-direction opcodes, all-up/all-down, exact six memory opcode choices, fixed save tails, dedicated light paths, mood group bit, massage group bit and article literal requests require profile-specific vectors. Basic seat recalls only 1–3; no basic programming or memory 6 inheritance.

## Held action timing and release

Source DeviceComm is a FIFO with nominal 100 ms pump, 30 ms pending polling and SDK 100 ms task delay. It has no fixed repeat count, hold duration or on-air 100 ms guarantee. Refresh only a successful prior held write; serialize commands through coordinator. Ordinary Home Assistant actions use a bounded one-second hold as host policy. That duration is not an APK interval, hardware travel time or automatic flat-position acknowledgment. The `adjustable_bed.vibradorm_hold_control` action exposes the exact profile control catalog and an explicit bounded duration, with paired side routing. Its catalog is validated for every selected physical target before writes, and release uses the controller STOP cleanup path. All-down means movement toward flat while held, not a proven self-completing preset.

Release always ends refresh and attempts the exact profile STOP with a fresh cancellation signal, including cancellation/error/side-routed service cleanup. Do not copy source stranded-STOP, unhandled ACTION_CANCEL, queue clear/disconnect without STOP or indefinitely blocked write behavior. These are explicit safety exclusions with source evidence. Do not append STOP after a one-shot feature or information packet unless it is a separate requested navigation/motor release. Host serialization can safely replace shared unsent-command races, without changing normal ordered vectors.

## Information, notification and bonding lifecycle

Reachable onboarding order is in scope, not excluded merely because Android initiated it. For a new explicit-profile bond:

1. Issue ordinary unbonded connect/service discovery and start one source 10,000 ms whole onboarding deadline, including connection/discovery; no per-field reset.
2. For nonbasic enable the exact response subscription; for basic do not subscribe. Nonbasic source queues subscription before initialized listener; actual acknowledgment failure must be exposed, not silently manufacture a different path.
3. Sequentially read DEVICE_NAME (`2a00`), MANUFACTURER (`2a29`), MODEL (`2a24`), FW (`2a26`), SW (`2a28`).
4. Only control types 5/6/7 then send exactly three separate `01a0c8` article requests, each reply-gated. No toggle, automatic STOP or inferred firmware transfer.
5. After information completion call native bond using existing typed host/proxy pairing, proof, cancellation and cleanup policy. Record a real native bond result. DIS/article bytes are metadata and never new bond proof, credentials, profile inference or connection-gated-by-bond evidence.
6. Complete/store the selected configuration and disconnect/transition. Later configured startup targets exact MAC and checks existing bond/recovery; avoid an unnecessary new first-bond transaction.

A profile-aware pre-pair hook carries the selected client, cancellation state and shared deadline. The static pairing policy alone does not establish the required information-before-bond order. Existing generic Vibradorm route is preserved. The setup lifecycle owns the hook/order and host/proxy proof; the app controller owns its exact read/parser/transaction helper. Android activity dialogs, synchronous callback-before-post race and host-specific retry/unbond implementation details are separate process/safety/platform exclusions, without waiving this reachable workflow or the source deadline.

Successful standard MODEL/FW/SW reads decode UTF-8 with Java edge trim of code units ≤ U+0020 (empty/null -> empty, embedded NUL/NBSP preserved). Each successful MODEL/FW/SW result and matching article reply is retained before the next read or request. Runtime refresh persists completed diagnostic deltas in one guarded terminal batch, including failure or cancellation, so reconstruction preserves successful fields while unread fields remain unknown or retain their prior value. A later read, article or bond failure must not discard earlier diagnostic strings; partial diagnostics do not make the transaction or bond successful. Information strings do not select capabilities. Article recognition requires length > 4 and prefix `21a0c8`; decode the remaining bytes as UTF-8 without trimming/NUL termination. Source advances the transaction on every successful notification, including unrelated data, and can leave `readingDeviceInfo` stale after fail; explicitly exclude these unsafe diversions. The host correlates relevant replies and clears transaction state on every exit. Preserve three requests and parser results, and test unrelated/late/malformed callbacks, missing notify, failed read/write, cancellation, bounded deadline and no writes after completion. No parser-reachable measured angle/motor position exists in row031.

Only Werkmeister type 7 has live sync: query `003d | T` plus `3f`; recognize length ≥ 3 with `20`/`3f` flags at byte 2, or `3f` flags at byte 1; bit `40` indicates sync active. Pending held intent chooses `0019` when active else `0018`, via the repeating motor builder. Release clears pending intent and sends `00ff`; late reply after release must not restart a hold. Type 5 sync is inert; Caresse fixed-flavor sync/calibrate routes are dead even for restored type 7. Expose a user sync action and the `vibradorm_app_sync_observed` diagnostic sensor, without asserting a second BLE connection or a physical partner state. Raw other callbacks are diagnostic only.

## Lighting and massage state/exposure

Floor light: exact helper logical level 0–8; shipped slider 1–6 with extension or 1–8 without extension (off 0 is separate), missing remembered-preference fallback 6 with extension, otherwise 8 (normal first-onboarding/reset remembers 6); raw conversion extension=logical, nonextension=logical*32, values > 255 return 200 (including the missing-preference getter boundary). Toggle remembers a nonzero default, zero default is normalized to 1. Timer enable/value is local pending state applied to the next floor write; provide the exact NumberPickerDialog domain 1–60 minutes, with enable/value changes pending until the next floor command. No automatic light/sensitivity/zone/RGB inference. CBI opcode `0011` for basic or nonextended ; `1011` only nonbasic+extension. Floor control remains separate from mood lighting.

Mood only Caresse restored RGB: all 18 shipped palette choices, fixed 100 brightness HSV transformation and retained toggle, effects sunrise/rainbow/disco 1–3, exact speed progress 0–8 conversion. `MoodLightFragment.java` lines 35–36 initializes `mCurrentBrightness = 100`; its constructor is the sole assignment and `setNewColor` lines 153–155 uses that fixed value. The shipped callbacks expose no adjustable mood brightness. Separate typed select/number specs expose palette/effects/speed. Do not advertise unrestricted arbitrary HA RGB, adjustable mood brightness, inferred color temperature, hardware state or unsupported effect names. Packet group `0077` basic / `1077` nonbasic except mood toggle is always `1077`. State is local intent/assumed; no live device status reconstructs it.

Massage only Caresse restored massage: defaults effect 0, speed 1, zones 0/0 and timer 0, saved intensity 3/3, effect 1 and speed 1, flags false. Auto and Individual on/off have different saved state and nested mode-switch off frames. Expose both modes, torso/leg toggles and guarded increase/decrease, waves 1–4 and speed 1–5 with the exact listener/updateIndicators predicates. Do not collapse saved flags and saved intensities or automatically invent a fresh individual 3/3 fallback. Zone controls use the proven toggle/increment/decrement callbacks; no arbitrary direct intensity setter is implied. Preserve 72 accepted state vectors, complete Cartesian guard proof and exact nested off-then-restore sequences. Timer has no shipped setter; no new timer UI. Sensor/select state must distinguish intended/assumed state from a hardware acknowledgment.

Controller select/number descriptions are immutable for the chosen profile/flags; massage mode guards run in setters, not by changing loaded entity descriptions. Shared typed select/number descriptions provide the user interface while the app controller supplies exact options and guarded callbacks. Controller-held options, motor specs, ControllerButtonSpec and controller diagnostic sensor specs supply exact route/capability gates. Expose every in-scope action without requiring raw packet entry; paired child targeting must route to the same logical profile/controller. Separate-address pairs retain side-specific app/profile/retained-feature fields; differing sides prohibit global option propagation. Single-address pairing/addressing is not supported by these app profiles. This is a HA integration boundary, not an app-proven partner feature.


## Characteristic identities

| Role | Exact UUID |
|---|---|
| COMMAND | `00001526-9f03-0de5-96c5-b8f4f3081186` |
| LIGHT | `00001529-9f03-0de5-96c5-b8f4f3081186` |
| CBI | `00001550-9f03-0de5-96c5-b8f4f3081186` |
| CBI response | `00001551-9f03-0de5-96c5-b8f4f3081186` |

These app paths select exact characteristics across services. No fixed parent service, guessed writable fallback or base-UUID alias is proven. The application inherits runtime native write properties/type. Home Assistant's declared property-based transport policy is host behavior, not evidence of a fixed Android response mode.

## Motor and memory opcode index

Basic controls 2/3 use the low command byte. Nonbasic controls use big-endian words with the captured toggle bit, except literal release/save-tail frames.

| Action | Opcode |
|---|---|
| All up / all down | `10` / `00` |
| Back up / down | `0b` / `0a` |
| Legs up / down | `09` / `08` |
| Head/neck up / down | `03` / `02` |
| Feet up / down | `05` / `04` |
| Memory slots 1–6 | `0e`, `0f`, `0c`, `1a`, `1b`, `1c` |
| Basic release | `ff` |
| Nonbasic release | `00 ff` |

An opcode's existence does not expose its action in every profile. The selected app movement groups and exact memory gates above determine which actions are available. All-down is held movement toward flat, not a measured or self-completing flat preset.

## Fixed mood palette

The shipped order and fixed 100 HSV roundtrip produce the following packet RGB values. Rounding can differ from the resource ARGB color by one unit. The palette is discrete; it does not authorize arbitrary RGB or adjustable mood brightness.

| Palette index | Packet RGB |
|---|---|
| 0 | `0, 138, 0` |
| 1 | `0, 171, 169` |
| 2 | `26, 161, 226` |
| 3 | `0, 80, 239` |
| 4 | `106, 0, 255` |
| 5 | `170, 0, 255` |
| 6 | `244, 114, 208` |
| 7 | `216, 0, 115` |
| 8 | `162, 0, 36` |
| 9 | `229, 19, 0` |
| 10 | `250, 104, 0` |
| 11 | `240, 163, 9` |
| 12 | `227, 200, 0` |
| 13 | `130, 90, 44` |
| 14 | `109, 135, 100` |
| 15 | `100, 118, 135` |
| 16 | `118, 112, 138` |
| 17 | `255, 255, 255` |


## Floor intent and host lifecycle

Current floor level and remembered turn-on level are distinct local intent. Both APK Application initializers write current level 0. First unconfigured onboarding then calls `unconfigure()`, which writes current and remembered level 6 before remote selection; newly selected Werkmeister controls therefore begin from 6 in that same app process. A later configured process begins from current level 0 while preserving remembered level 6. Missing remembered preferences have a separate fallback: 6 with extension, otherwise 8. A getter fallback does not establish normal first-onboarding state.

The Android reset/preferences screen is excluded as local application UI (`R031-0671`). Its downstream floor level/default effects are in scope because they change subsequent packets. Home Assistant represents this lifecycle with typed local floor and pending-timer intent: successful new selection seeds 6/6; a configured cold process begins at level 0 and timer off/0, retaining the stored turn-on preference. Local intent survives connection/controller reconstruction for the exact physical address and unchanged app/control selection. Changing that selection discards incompatible local intent. These fields never prove that the peripheral is on or off.

Home Assistant exposes floor lighting through the under-bed switch and a positive brightness number, separate from the bounded mood controls. The switch starts unknown with assumed state. OFF remembers a positive level before sending zero; ON restores the current positive or remembered level. Repeating an explicit ON/OFF action resends that requested branch while preserving source caller toggle consumption. Successful published level intent updates both controls. Failed delivery preserves their last publication while internal constructed intent advances; neither path is hardware readback.

Controller recreation is a fresh MC/control-screen boundary: logical header toggle and screen-owned massage/mood state start from their source constructor state. Process-wide floor preference and pending timer use the separate shared holder. This host boundary does not claim to reproduce the SDK's reconnect while the original Android screen object survives.

## Advertisement diagnostics and target selection

The source SDK selects the first record in an ordered manufacturer list. It masks the company ID to 16 bits and accepts `03b0` or `ffff`; absent SDK company is -1 and becomes `ffff`. Payload excludes the little-endian company ID. Customer derivation is null → `fffe`, length ≤ 6 → `ffff`, length 7–9 → `fffe`, otherwise big-endian bytes 4–5. Identifier uses big-endian bytes 0–1; VibFlags combine the high nibble of byte 2 with the shifted high nibble of byte 3. These fields do not identify a product, motor layout or physical partner.

Public discovery tests raw AD Flags bit `01`, independently of manufacturer sync/init bits. Werkmeister also admits only customer `ffff`, `0018` or `0012`; Caresse has no shipped customer gate. Configured discovery targets the exact MAC. The SDK applies the company filter to newly created discovered devices, while rediscovery of an already cached SDK device bypasses that new-device filter. Do not add an inferred company gate to the exact configured-target route.

Home Assistant diagnostics derive each observed company/payload record without choosing an SDK-first record. The host manufacturer map does not preserve raw AD ordering, duplicate company records, raw Flags or advertising/scan-response grouping. Those limits remain explicit, including when only one record is present. The pure ordered-record helper preserves the exact source rule when ordered input is available; diagnostic verdicts from the map remain conditional. Automatic operation of the first broad public candidate is excluded for target/product safety. Setup requires an explicit physical target and app profile.

## Native bond evidence and legacy boundary

The app checks exact-MAC native bonded inventory and native completion. Metadata reads and successful pair RPCs are not cryptographic authentication proof. Use typed native OS state evidence distinct from an authenticated protocol probe. Unsupported proxy confirmation remains unverified with an accurate pairing-attempted status. Already-bonding/demo shortcuts and phone-specific destructive automatic unbond are explicit safety exclusions, while the information-before-native-bond workflow remains in scope.

These profiles expose no live position, EEPROM or motor-status parser. Their orphan helpers are excluded by caller/selector closure. Generic Vibradorm position behavior remains available through the existing generic route. Historical reports about another app or physical controller do not identify either profile or prove that their hardware issues are fixed.

## Provenance and exclusions

Accepted representative report seal: `3a57621a4a4e689b06ec9bd6d471807d3b184c10520f129f342eebb442deae2c`.
Accepted sibling report seal: `2c8b210bf8942c689bd62ae555557283298f895c75c246c5f00e57b755e97c9a`.
Whole-cluster reconciliation seal: `fcdaaf8728e27bbd04b47849201ea46dea1cf790f93ac5ce01c2968c325bfffc`.
Independent reconciliation audit seal: `f91c5b9efcf2eb85bdf0e80f81717ecd0b92d6059463b4a90ea4b807a3f5224d` (ACCEPT, zero material findings).
Post-freeze comparison seal: `a59b50bb11a14660b737482066f4b6609f9e775e0170e97248a394c821ca7fc2`.

See [all 356 exact exclusions](../apk-analysis/row031-dispositions.md). Raw artifacts, decompilation, packet reproducers and independent audit reports remain machine-local.
