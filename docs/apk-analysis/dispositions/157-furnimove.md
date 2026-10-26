# Row 157: FurniMove implementation dispositions

Ref #633 and #556. Evidence was frozen and independently accepted before comparison.

**Scope:** `com.okin.okinsmartcomfort` 2.2.0 (19), 19 APK members; production API captures dated 2026-09-30.

Artifact SHA-256: `b1bc3e67399e560b204882c7076bc8f82a6abecbfb6b33f234edf7bd1453dc76`.
Accepted report index SHA-256: `73f8e70c91a22e6a410a8720178bcf7effd25128d32f051fa51233bef37ca457`.
Freeze attestation SHA-256: `41e982dabd678a7b4b8ec93dc1d0eada9e57ddb6c82b4c29ba0418704e75c750`.

Raw artifacts, API responses, decompilation, audit reports and per-observation ledgers remain machine-local and ignored. This document records integration decisions, not a replacement audit report.

**Behavior ledger: 60 items, 48 IMPLEMENTED, 0 ALREADY_IMPLEMENTED, 12 EXCLUDED; no undispositioned item.**

**Concrete inventory:** all 10,593 captured environment rows are dispositioned: 1,074 conditionally reachable production rows implemented; 9,519 rows excluded as dead payloads or alternate debug-environment observations. Production retains all 1,092 rows, including its 18 loaded but unused payload rows. All 87 production IDs, 39 tables, 1,092 ordered rows and 3,276 P1/P2/P3 production frames have independent replay proof. The three shipped local/offline profiles are also implemented.

Hardware behavior remains unverified. Physical checks are deferred to real users after beta/release, not an implementation blocker. #633 establishes FurniMove use; #556 establishes a shared receiver, not its app or handset ID.

## Startup compatibility follow-up

The 2026-10-06 retest in [issue #633](https://github.com/kristofferR/ha-adjustable-bed/issues/633)
still loses its link before controller setup and creates no entities. D029/D030's
controller-owned, subscription-first information reads now replace the generic
manufacturer/model pass for FurniMove. Individual subscription/read debug lines
identify the last operation attempted. This removes redundant startup work; it
does not establish which operation causes the physical disconnect.

A valid selected catalog layout can create entities after initial connection
failure or timeout, using the existing offline capability controller. It retries
on command/Connect, preserves entity identities when a live controller takes
over, and refuses unknown IDs or a half-initialized client left by failed cleanup.
`tests/test_furnimove_startup.py` covers these paths and subscription/read order.
The report's frames, timing, bond policy, catalog and original 60-item totals are
unchanged. RF ECO BT part 88802 does not identify handset 90167; the actual
FurniMove layout and receiver stability still require user evidence.

The issue's screenshots identify the app's handset as **82417**, while the
integration selected **90167**. Explicit FurniMove pickers now offer every
already captured handset, including 82417, without imposing the Okin UUID
route's mandatory bond gate. No catalog rows, command frames or app bond policy
change. Setup/options/repair tests cover the exact selection and correction.

The morning support bundle also shows cached services returned before BlueZ
published its live GATT objects: reads and subscriptions failed with
`UnknownObject` before `ServicesResolved=True`. FurniMove startup/setup and
standalone diagnostics disable the early service-cache shortcut. Diagnostic
reads and notification operations are bounded, retaining errors and service
structure when a read does not answer. The evening capture disconnects before
service resolution; its local connection abort remains unverified hardware
behavior, rather than evidence of an unsupported command.

## Behavior decisions

| ID | Behavior | Disposition and evidence |
|----|----------|--------------------------|
| D001 | Explicit application/product profile separate from shared UUID legacy families | IMPLEMENTED: [config_flow.py:922](../../../custom_components/adjustable_bed/config_flow.py), [controller_factory.py:665](../../../custom_components/adjustable_bed/controller_factory.py), [furnimove_repair.py:144](../../../custom_components/adjustable_bed/furnimove_repair.py), [test_furnimove_config.py:36](../../../tests/test_furnimove_config.py), [test_furnimove_repair.py:70](../../../tests/test_furnimove_repair.py) Standard handsets also listed under Okin UUID stay on that route for new setups (bond and FFE4 feedback); the RF1058 DOT handsets use this profile, with a repair for existing Okin DOT entries ([okin_uuid.py:213](../../../custom_components/adjustable_bed/beds/okin_uuid.py), [furnimove_repair.py:63](../../../custom_components/adjustable_bed/furnimove_repair.py), [test_furnimove_config.py:108](../../../tests/test_furnimove_config.py), [test_furnimove_repair.py:184](../../../tests/test_furnimove_repair.py)). |
| D002 | Production87parseable profile aliases/39semantic tables; all1092rows,18loaded-unselected preserved | IMPLEMENTED: [furnimove_profiles.py:37](../../../custom_components/adjustable_bed/furnimove_profiles.py), [test_furnimove_profiles.py:17](../../../tests/test_furnimove_profiles.py) |
| D003 | 280702/280703 local nine-row aliases before HTTP | IMPLEMENTED: [furnimove_profiles.py:1708](../../../custom_components/adjustable_bed/furnimove_profiles.py), [test_furnimove_profiles.py:62](../../../tests/test_furnimove_profiles.py) |
| D004 | 00000 offline five-row table without release row | IMPLEMENTED: [furnimove.py:463](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:143](../../../tests/test_furnimove.py) |
| D005 | Arbitrary typed table fields/defaults/categories/intensity carry/ordered duplicates | IMPLEMENTED: [furnimove_profiles.py:98](../../../custom_components/adjustable_bed/furnimove_profiles.py), [test_furnimove_profiles.py:78](../../../tests/test_furnimove_profiles.py) |
| D006 | Unknown action categories retain name-dispatched main/utility behavior | IMPLEMENTED: [furnimove.py:445](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:284](../../../tests/test_furnimove.py) |
| D007 | All ordered MEMORY rows, arbitrary MEMORY_PRESET labels | IMPLEMENTED: [furnimove.py:1162](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:486](../../../tests/test_furnimove.py) |
| D008 | CSV169unique IDs capability hints are unused by app | EXCLUDED: Dead/unused metadata is not command or capability authority Source: `work/jadx/sources/com/dewertokin/okinsmartcomfort/service/CSVReader.java` |
| D009 | Alternate env mappings cannot fill production gaps | EXCLUDED: Dead/debug-only alternate selection is outside ordinary app product boundary; reports retain exact observations Source: `work/jadx/sources/com/dewertokin/okinsmartcomfort/Application.java:43-48`, `work/jadx/sources/com/dewertokin/okinsmartcomfort/view/TestScreenActivity.java:144-487` |
| D010 | Future remoteID HTTP/QR/brand/promo acquisition | EXCLUDED: Live cloud/API acquisition and promotional account workflow are outside BLE-only integration; this does not exclude generic BLE formulas or captured production tables Source: `work/jadx/sources/com/dewertokin/okinsmartcomfort/presenter/pairing/EnterRemoteIdPresenter.java:89-174`, `work/jadx/sources/com/dewertokin/okinsmartcomfort/service/networkService/ApiService.java:43-68` |
| D011 | P1six-byte04 02+four-byteBE payload | IMPLEMENTED: [furnimove.py:84](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove_profiles.py:17](../../../tests/test_furnimove_profiles.py) |
| D012 | P2eight-bytee5fe16payload/complementchecksum, RF wins bothflags | IMPLEMENTED: [furnimove.py:84](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:102](../../../tests/test_furnimove.py) |
| D013 | P3seven-byte0502payload/trailingzero | IMPLEMENTED: [furnimove.py:84](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:78](../../../tests/test_furnimove.py) |
| D014 | Per-consumer DOT flag omission | IMPLEMENTED: [furnimove.py:440](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:230](../../../tests/test_furnimove.py) |
| D015 | Composite full-frame bitwiseOR and RF checksum recalculation | IMPLEMENTED: [furnimove.py:109](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:78](../../../tests/test_furnimove.py) |
| D016 | Malformed digit/prefix/odd/oversize string behavior | EXCLUDED: Safety constraint: unvalidated malformed custom data can emit unintended motor bits; app failure behavior remains documented, no fabricated commands. Valid observed data/formulas remain implemented Source: `work/jadx/sources/com/dewertokin/okinsmartcomfort/service/utils/HexValueConverter.java:36-109` |
| D017 | All-service characteristic scan, ordered last-match, selected field independent frame | IMPLEMENTED: [furnimove.py:240](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:120](../../../tests/test_furnimove.py) |
| D018 | No app writeType selection; use discovered characteristics | IMPLEMENTED: [furnimove.py:267](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:111](../../../tests/test_furnimove.py) |
| D019 | Initial write ignores nativeboolean; callback-success stream100ms and one callbackfalse retry | IMPLEMENTED: [furnimove.py:516](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:158](../../../tests/test_furnimove.py) |
| D020 | Subscribe all three feedbackrolefamilies and CCCD0100 | IMPLEMENTED: [furnimove.py:297](../../../custom_components/adjustable_bed/beds/furnimove.py), [furnimove.py:194](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:516](../../../tests/test_furnimove.py), [test_furnimove.py:540](../../../tests/test_furnimove.py) |
| D021 | CSSwrite getter has no reachable command; CSSnotify no-op | EXCLUDED: Dead/unused write field and no-op notify branch Source: `work/jadx/sources/com/dewertokin/okinsmartcomfort/service/bleModule/bluetooth/BluetoothLeService.java:175-204,616-779` |
| D022 | Ordered first advertUUID180a/firstmanufacturer1643/okinmatprefix/services acceptance | IMPLEMENTED: [detection.py:1124](../../../custom_components/adjustable_bed/detection.py), [config_flow.py:387](../../../custom_components/adjustable_bed/config_flow.py), [test_furnimove_config.py:174](../../../tests/test_furnimove_config.py), [test_furnimove_config.py:206](../../../tests/test_furnimove_config.py) Explicit app/handset selection plus conservative HA advertisement candidates replace the broad Android first-DIS/first-manufacturer predicate; no blanket DIS discovery or receiver-to-layout inference. |
| D023 | scanmode2/nullfilters/4sec with explicitstoppaths | EXCLUDED: App-local scanning lifecycle is replaced by Home Assistant managed Bluetooth discovery, not a bed wire requirement; retain acceptance predicates and manualselection Source: `work/jadx/sources/com/dewertokin/okinsmartcomfort/service/bleModule/bluetooth/BluetoothScanningModule.java:396-492` |
| D024 | Conditional named nonokinmat nonbonded createBond then immediateconnect | IMPLEMENTED: [coordinator.py:2516](../../../custom_components/adjustable_bed/coordinator.py), [coordinator.py:2506](../../../custom_components/adjustable_bed/coordinator.py), [test_furnimove_connection.py:58](../../../tests/test_furnimove_connection.py), [test_furnimove_connection.py:97](../../../tests/test_furnimove_connection.py) Bleak needs a live client: advisory owned bond request follows connect/GATT discovery without awaiting it or gating controller startup; 5-second bound is operational, not APK timing. |
| D025 | No PIN/no protectedread/awaitedbond gate | IMPLEMENTED: [coordinator.py:2516](../../../custom_components/adjustable_bed/coordinator.py), [const.py:2595](../../../custom_components/adjustable_bed/const.py), [test_furnimove_config.py:56](../../../tests/test_furnimove_config.py) No pair=True, protected read or persisted proof gate for this explicit app profile. |
| D026 | TrackedGatt same-address reconnect-only close; replacement oldGatt may remain | EXCLUDED: Safety constraint: leaked connections/stalecallback races conflict with serialized HA ownership; close owned oldclient while retaining actual reconnect behavior evidence Source: `work/jadx/sources/com/dewertokin/okinsmartcomfort/service/bleModule/bluetooth/BluetoothLeService.java:526-573` |
| D027 | CallbacknewState0/2 statusunused cleanup/broadcast2000/discovertrackedGatt | IMPLEMENTED: [coordinator.py:3791](../../../custom_components/adjustable_bed/coordinator.py), [coordinator.py:4504](../../../custom_components/adjustable_bed/coordinator.py), [test_furnimove_connection.py:80](../../../tests/test_furnimove_connection.py) Managed Bleak connection/disconnect handling and owned client teardown replace Android UI broadcasts and stale callback targets; no 2-second UI broadcast timer is a bed command. |
| D028 | Cleanup reset10refs/modelHE150/versions/DOT; retainlight/sync/lock/once/observer | IMPLEMENTED: [furnimove.py:227](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:380](../../../tests/test_furnimove.py) |
| D029 | Deviceinfo model/hardware/software/firmware reads and exactCU170 selector | IMPLEMENTED: [furnimove.py:346](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:516](../../../tests/test_furnimove.py) |
| D030 | DOTraw00b0 query400msinitial and200msrelease; nonDOTfeedbackread700ms | IMPLEMENTED: [furnimove.py:297](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:170](../../../tests/test_furnimove.py) DOT initial400ms query and UBL-only postrelease200ms query; generic axis/Flat release has no queryAction caller. |
| D031 | Outerlength>=10; generic08/09 0b ANDtwoBEwords masks/changedonly | IMPLEMENTED: [furnimove.py:379](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:328](../../../tests/test_furnimove.py) |
| D032 | RF fe/lownibble5or6 extraction/opcode6set7clear/edgeevents | IMPLEMENTED: [furnimove.py:379](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:366](../../../tests/test_furnimove.py) |
| D033 | CU170maskparser precedes RF/generic, syncbyte9==4retain/noemit | IMPLEMENTED: [furnimove.py:379](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:328](../../../tests/test_furnimove.py) |
| D034 | DOTlen>14preliminarybyte13UBL, fallthroughmayoverride | IMPLEMENTED: [furnimove.py:379](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:328](../../../tests/test_furnimove.py) |
| D035 | No position/angle/current/battery hardwaremeasurements | EXCLUDED: No reachable artifact behavior supports angle/current/battery telemetry; do not invent physical values Source: `work/jadx/sources/com/dewertokin/okinsmartcomfort/service/bleModule/bluetooth/BluetoothLeService.java:175-485` |
| D036 | Main M1head/M2back/M3leg/M4feet, ResetIn/Out all, Flat, UBL byfirstname | IMPLEMENTED: [furnimove.py:548](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:143](../../../tests/test_furnimove.py) |
| D037 | Actuatorcount//2; newUIselectedsumhead/back/legs/feet onlyifcount>2,max2 | IMPLEMENTED: [furnimove.py:590](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:78](../../../tests/test_furnimove.py) |
| D038 | Mainstreamfalse100ms success-drivenhold; optionalfirstreleaseonce + globalstop100ms | IMPLEMENTED: [furnimove.py:489](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:176](../../../tests/test_furnimove.py) |
| D039 | NonDOTseparate200ms optionalcurrentrowreleaseonce, noextra300msstop | IMPLEMENTED: [furnimove.py:463](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:143](../../../tests/test_furnimove.py) |
| D040 | Uncancelledhandler/callbackmode races and destroy/noSTOP | EXCLUDED: Safety constraint: stale delayed writes, oldUI CANCEL omission and orphaned held refresh are replaced with deterministic HA cleanup; no extra hardwareopcode invented Source: `work/jadx/sources/com/dewertokin/okinsmartcomfort/view/remoteControl/RemoteFragment.java`, `work/jadx/sources/com/dewertokin/okinsmartcomfort/view/TabBarActivity.java`, `work/jadx/sources/com/dewertokin/okinsmartcomfort/service/bleModule/bluetooth/BluetoothLeService$mGattCallback$1.java:100-131` |
| D041 | MEMORY/MEMORY_PRESET allorderedrows stream100ms, falsemoderelease+stop100ms | IMPLEMENTED: [furnimove.py:711](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:191](../../../tests/test_furnimove.py) |
| D042 | MemoSaveimmediate+rowduration/frequencytimer; stop+f/slot+2f/stop+3f | IMPLEMENTED: [furnimove.py:737](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:211](../../../tests/test_furnimove.py) |
| D043 | Sync/ChildLocknamegates repeatedoncetimer(rowduration/frequency) | IMPLEMENTED: [furnimove.py:714](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:284](../../../tests/test_furnimove.py) |
| D044 | Utilityfinish300ms checksSyncevenChildLock, firstSynccomparisonDOTfalse thenfinaltrue, optionalrelease+stop100 | IMPLEMENTED: [furnimove.py:767](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:310](../../../tests/test_furnimove.py) |
| D045 | SwitchToPHgate exposesmode; SwitchToPRalone nosection; timersDOTfalse | IMPLEMENTED: [furnimove.py:804](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:284](../../../tests/test_furnimove.py) |
| D046 | MaxintensityfirstHeadPlus else4; massage-functiontabgate | IMPLEMENTED: [furnimove_profiles.py:64](../../../custom_components/adjustable_bed/furnimove_profiles.py), [test_furnimove_profiles.py:78](../../../tests/test_furnimove_profiles.py) |
| D047 | Head/feet intensityfactory targets1plus,2three-minus,3two-minus,4one-minus; releasepairs | IMPLEMENTED: [furnimove.py:865](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:402](../../../tests/test_furnimove.py) |
| D048 | Incrementdirection1pluselseminus; headfeetordering; WAVEalwaysplus | IMPLEMENTED: [furnimove.py:980](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:451](../../../tests/test_furnimove.py) |
| D049 | Programs1/2/3/Wave +release; intensityWAVEplus/release1..4 | IMPLEMENTED: [furnimove.py:1012](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:427](../../../tests/test_furnimove.py) |
| D050 | Stopidle2immediate,busy1immediate+150,>maxstop250only; busyqueue/ui delays | IMPLEMENTED: [furnimove.py:936](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:427](../../../tests/test_furnimove.py) |
| D051 | Localduration10/15/20/30min countdown1ms, expirytextonly/noBLEstop | IMPLEMENTED: [furnimove.py:856](../../../custom_components/adjustable_bed/beds/furnimove.py), [services.py:1773](../../../custom_components/adjustable_bed/services.py), [test_furnimove.py:427](../../../tests/test_furnimove.py), [test_furnimove_services.py:63](../../../tests/test_furnimove_services.py) Dedicated local advisory duration and diagnostics; Android millisecond text countdown is presentation only. No hardware timer or expiry STOP. |
| D052 | UnknownMassagerHead/Feet/MassageAll rows are tabgates only/nopayloadconsumer | EXCLUDED: Dead/unused payload rows; preserve capability gating separately Source: `work/jadx/sources/com/dewertokin/okinsmartcomfort/service/MassageKeyCodeFactory.java`, `work/jadx/sources/com/dewertokin/okinsmartcomfort/presenter/massage/MassagePresenter.java` |
| D053 | Widgetwhitelist firstTV/UBL/Flat/Memo1..4/Snore/ZeroGravity/QuietSleep DOTfalse | IMPLEMENTED: [furnimove.py:1135](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:476](../../../tests/test_furnimove.py) |
| D054 | 20sec200ms once-mode timer; predispatch/toggle/UBL100msrelease; finishoptionalrelease no globalstop | IMPLEMENTED: [furnimove.py:1190](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:476](../../../tests/test_furnimove.py) |
| D055 | Androidhomescreen display/connection5sec/settings whitelist UI | EXCLUDED: App-local launcher presentation outside HA product. Actual widget-specific BLE encoder/timing remains separately dispositioned D053/D054 Source: `work/jadx/sources/com/dewertokin/okinsmartcomfort/widget/WidgetProvider.java` |
| D056 | RFnamechar elseGAPname Stringwriteonce; originaluntrimmedtext sent | IMPLEMENTED: [furnimove.py:1232](../../../custom_components/adjustable_bed/beds/furnimove.py), [services.py:1710](../../../custom_components/adjustable_bed/services.py), [test_furnimove.py:506](../../../tests/test_furnimove.py), [test_furnimove_services.py:71](../../../tests/test_furnimove_services.py) |
| D057 | ReportedUBLboolean with togglecommand, not discreteon/offsemantic | IMPLEMENTED: [furnimove.py:814](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:131](../../../tests/test_furnimove.py) |
| D058 | Sync/ChildLock are app booleans, not physicalsideaddressrouting | IMPLEMENTED: [furnimove.py:407](../../../custom_components/adjustable_bed/beds/furnimove.py), [test_furnimove.py:328](../../../tests/test_furnimove.py) |
| D059 | Roomselectedrows/customnames/massage/mode state persistence | IMPLEMENTED: [furnimove.py:1085](../../../custom_components/adjustable_bed/beds/furnimove.py), [coordinator.py:5811](../../../custom_components/adjustable_bed/coordinator.py), [coordinator.py:5833](../../../custom_components/adjustable_bed/coordinator.py), [test_furnimove.py:451](../../../tests/test_furnimove.py), [test_furnimove_connection.py:117](../../../tests/test_furnimove_connection.py) |
| D060 | Remoteclaims/promotions/themes/reminders/web/cloud/siri/brandfeatureflags | EXCLUDED: Cloud/UI workflow outside BLE integration; retainBLE capability rows independently Source: `work/jadx/sources/com/dewertokin/okinsmartcomfort/service/networkService/TransferService.java`, `work/jadx/sources/com/dewertokin/okinsmartcomfort/view/TestScreenActivity.java` |

## Migration and implementation adaptations

- Legacy RF ECO BT entries require explicit staircase confirmation or another app/layout choice, including one-motor entries and offline setup. Repairs preserve entry/device identity and matching entities; per-side repairs preserve the other side.
- Main/utility/massage/widget/programming consumers retain their distinct release formats. Cancellation completes the active consumer’s cleanup before the generic STOP path; it does not append a release from a different consumer.
- Characteristics with repeated UUIDs are written by the selected instance; managed Bluetooth subscriptions and write properties replace Android-specific GATT plumbing.
- Local massage state is stored by physical address and selected handset. Active zone/intensity/duration affect subsequent dispatch; program counters and reported booleans are retained only within the same coordinator. Stored local state is never hardware proof.
- Widget dispatch history stays in the coordinator across Bluetooth handoffs. Offline sides derive entities from the stored handset, including massage-state sensors only when that handset supports massage. Advisory duration updates use the command lock without connecting; unchanged feedback does not reschedule preference storage.
- The app’s broad DIS advertisement acceptance, Android UI broadcasts, callback races and millisecond countdown text are replaced by HA discovery/lifecycle or excluded presentation. No extra hardware command is inferred from them.

## Validation

Focused tests cover profile replay, all production row semantic/frame hashes, duplicate-UUID routing, RF/CU170/DOT parsing, release and cancellation, ordered memory save, massage queues, widget timing, reconnect/storage, services, offline repair and registry identity preservation. Integration-wide validation and review results are recorded with the implementation commit/PR.
