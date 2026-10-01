# Row048: Smart Move+ app dispositions

The accepted Android app `com.timotion.smartmove` 0.1.8 (7) controls height-adjustable desks. It has no reachable bed-control protocol. The comparison accounts for **87 discovery items: 1 IMPLEMENTED, 0 ALREADY_IMPLEMENTED, 86 EXCLUDED**. Rows overlap evidence coverage. Hardware is unverified.

The one implemented item protects users: these desks advertise the shared Nordic UART service, which the integration otherwise reads as a probable Richmat bed. Detection now rejects the app's `stand UP-` name before that fallback. This app is unrelated to the separately analyzed TiMOTION AHF bed app (row039); no behavior is shared between them.

## Exact accepted authority

| Identity or authority | SHA-256 / result |
|---|---|
| Frozen XAPK, 0.1.8 (7) | `75a078cf63cae25b48660004be5c4458a31ee9ab2b22f89cab81da5283205a99` |
| Signer certificate | `759d53d6b5833ab43fb14e852264f9e4ade87cbb28702673b5e33bb1b2495d6e` |
| Attempt 001 REPORT.SHA256, preserved | `f3abb3273f5fff1d53bb9cd18ab60b41ef36b7a0777fbf66b45de22a0a4bb10e` |
| Attempt 001 full independent audit (REPAIR_REQUIRED, IA001-IA003) | `ef9d07e077af6d7deec37b1155ad8f969b6de89aa74a1f39204ce443f82c0fec` |
| Accepted attempt 002 REPORT.SHA256 | `9ea7a415d67e404c13bfe38e32e63d3daed8923db2af27050d39e8e0fad5e9eb` |
| Accepted attempt 002 analysis.json | `4e694b837f91dc24a5675f9c39f577a66080fd46a91124eeb8c4ade3a82d6226` |
| Accepting affected-scope audit AUDIT.SHA256 | `251d802076f222ce00598b05c5701001cff60d446c1149f68e7b86a78d065f5c` |
| Effective decision | COMPLETE, 17 gates PASS, IA001-IA003 closed, 0 open material findings |

The first audit found three coverage gaps (cold transmit-buffer state, conditional dispatch and STOP paths, auto-connect/reconnect). An isolated repair closed them and the affected-scope audit accepted it. Raw artifacts, reports and decompiled sources remain machine-local.

## Ledger

| ID | Area | Item | Disposition | Evidence | Binding or exclusion reason |
|---|---|---|---|---|---|
| D001 | discovery | Desk scan filter: name starts with "stand UP-" on Nordic UART 6e400001 | IMPLEMENTED | Discovery matrix; C01 | detection.py EXCLUDED_DEVICE_PATTERNS "stand up-" stops the shared Nordic UART UUID from detecting these desks as Richmat beds; tests/test_detection.py test_timotion_smart_move_desk_is_not_a_bed |
| D002 | protocol | P1 packet format and checksum | EXCLUDED | P1 packet format | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D003 | command | P1 Initialize/request data | EXCLUDED | P1 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D004 | command | P1 Raise desk | EXCLUDED | P1 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D005 | command | P1 Lower desk | EXCLUDED | P1 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D006 | command | P1 Recall local memory M1 | EXCLUDED | P1 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D007 | command | P1 Recall local memory M2 | EXCLUDED | P1 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D008 | command | P1 Recall local memory M3 | EXCLUDED | P1 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D009 | command | P1 Recall local memory M4 | EXCLUDED | P1 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D010 | command | P1 Baseline STOP / manual release | EXCLUDED | P1 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D011 | command | P1 Release memory button | EXCLUDED | P1 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D012 | command | P1 Stop current motor action / lifecycle stop | EXCLUDED | P1 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D013 | command | P1 Reset actuators | EXCLUDED | P1 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D014 | parser | P1 notification P1 five-byte99 | EXCLUDED | P1 notification table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D015 | timing | P1 timing, release and automatic stop | EXCLUDED | P1 timing | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D016 | protocol | P2 packet format and checksum | EXCLUDED | P2 packet format | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D017 | command | P2 Initialize/request data | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D018 | command | P2 Raise desk | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D019 | command | P2 Lower desk | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D020 | command | P2 Recall local memory M1 | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D021 | command | P2 Recall local memory M2 | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D022 | command | P2 Recall local memory M3 | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D023 | command | P2 Recall local memory M4 | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D024 | command | P2 Baseline STOP / manual release | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D025 | command | P2 Release memory button | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D026 | command | P2 Stop current motor action / lifecycle stop | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D027 | command | P2 Reset actuators | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D028 | command | P2 Move to upper limit | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D029 | command | P2 Set upper limit | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D030 | command | P2 Cancel upper limit | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D031 | command | P2 Move to lower limit | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D032 | command | P2 Set lower limit | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D033 | command | P2 Cancel lower limit | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D034 | command | P2 Set anti-collision sensitivity | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D035 | command | P2 Enable automatic movement | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D036 | command | P2 Disable automatic movement | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D037 | command | P2 Automatic movement STOP selector 0 | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D038 | command | P2 Automatic movement STOP selector 1 | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D039 | command | P2 Automatic movement STOP selector 2 | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D040 | command | P2 Automatic movement STOP selector 3 | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D041 | command | P2 Automatic movement STOP selector 4 | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D042 | command | P2 Automatic movement STOP selector 11 | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D043 | command | P2 Automatic movement STOP selector 12 | EXCLUDED | P2 command table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D044 | parser | P2 notification Settings0 | EXCLUDED | P2 notification table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D045 | parser | P2 notification Status1 | EXCLUDED | P2 notification table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D046 | parser | P2 notification Status2 | EXCLUDED | P2 notification table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D047 | parser | P2 notification Common parser behavior | EXCLUDED | P2 notification table | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D048 | timing | P2 timing, release and automatic stop | EXCLUDED | P2 timing | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D049 | variant | Inventory entry C_AUTO | EXCLUDED | VARIANT_INVENTORY.json | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D050 | variant | Inventory entry C_AUTO_CONNECT | EXCLUDED | VARIANT_INVENTORY.json | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D051 | variant | Inventory entry C_BATTERY | EXCLUDED | VARIANT_INVENTORY.json | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D052 | variant | Inventory entry C_HEIGHT_RANGE | EXCLUDED | VARIANT_INVENTORY.json | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D053 | variant | Inventory entry C_LIMIT_LOWER | EXCLUDED | VARIANT_INVENTORY.json | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D054 | variant | Inventory entry C_LIMIT_UPPER | EXCLUDED | VARIANT_INVENTORY.json | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D055 | variant | Inventory entry C_MEMORIES | EXCLUDED | VARIANT_INVENTORY.json | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D056 | variant | Inventory entry C_MOTOR_COUNT | EXCLUDED | VARIANT_INVENTORY.json | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D057 | variant | Inventory entry C_PRODUCT | EXCLUDED | VARIANT_INVENTORY.json | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D058 | variant | Inventory entry C_SENSITIVITY | EXCLUDED | VARIANT_INVENTORY.json | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D059 | variant | Inventory entry C_SUPPORT | EXCLUDED | VARIANT_INVENTORY.json | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D060 | variant | Inventory entry V10 | EXCLUDED | VARIANT_INVENTORY.json | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D061 | variant | Inventory entry V20 | EXCLUDED | VARIANT_INVENTORY.json | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D062 | variant | Inventory entry V21 | EXCLUDED | VARIANT_INVENTORY.json | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D063 | candidate | C01 Scan with 6000 ms stop and RSSI > -90 acceptance | EXCLUDED | Candidate ledger C01 | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D064 | candidate | C02 Connection, discovery, read/notify and the single write callsite | EXCLUDED | Candidate ledger C02 | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D065 | candidate | C03 Initializer and P1/P2 selection from received frames | EXCLUDED | Candidate ledger C03 | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D066 | candidate | C04 P1 movement/reset/STOP/memory paths | EXCLUDED | Candidate ledger C04 | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D067 | candidate | C05 P2 height encodings, flags, memory, limits and automatic stop | EXCLUDED | Candidate ledger C05 | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D068 | candidate | C06 P1 5-byte validation and error bits | EXCLUDED | Candidate ledger C06 | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D069 | candidate | C07 P2 checksum over bytes 2..n-2, low 7 bits | EXCLUDED | Candidate ledger C07 | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D070 | candidate | C08 P2 settings/status parsing and readiness | EXCLUDED | Candidate ledger C08 | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D071 | candidate | C09 Local memory save to Android preferences and STOP-on-entry | EXCLUDED | Candidate ledger C09 | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D072 | candidate | C10 Settings and reset dialogs | EXCLUDED | Candidate ledger C10 | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D073 | candidate | C11 Error state, dialog and reset from notifications | EXCLUDED | Candidate ledger C11 | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D074 | candidate | C12 Error dialog reset streaming and startup frame | EXCLUDED | Candidate ledger C12 | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D075 | candidate | C13 Local device info/name/forget UI | EXCLUDED | Candidate ledger C13 | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D076 | candidate | C14 Uncalled P2 query methods | EXCLUDED | Candidate ledger C14 | Dead code: no caller in any DEX. |
| D077 | candidate | C15 Uncalled UUID setters | EXCLUDED | Candidate ledger C15 | Dead code: no caller. |
| D078 | candidate | C16 Uncalled P2 packet replacement | EXCLUDED | Candidate ledger C16 | Dead code: no shipped caller. |
| D079 | candidate | C17 Unused outer protocol-type constant 21 | EXCLUDED | Candidate ledger C17 | Dead code: never emitted. |
| D080 | candidate | C18 Uncalled private removeBond helper | EXCLUDED | Candidate ledger C18 | Dead code: uncalled (the reachable disconnect reflection is desk-session behavior). |
| D081 | candidate | C19 Play licensing check | EXCLUDED | Candidate ledger C19 | Unrelated: third-party licensing, no BLE control. |
| D082 | candidate | C20 Embedded coroutine debug-probe DEX | EXCLUDED | Candidate ledger C20 | Unrelated: instrumentation class. |
| D083 | candidate | C21 Bed-control candidate search across code/resources | EXCLUDED | Candidate ledger C21 | Unrelated: only desk controls found; generic password/brightness/pin/left/right hits are UI libraries. |
| D084 | candidate | C22 Unsigned/hex/7- and 8-bit encoding helpers | EXCLUDED | Candidate ledger C22 | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D085 | candidate | C23 Persisted auto-connect and Activity reconnect | EXCLUDED | Candidate ledger C23 | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D086 | session | No PIN, key exchange, bonding or BLE crypto; reflective removeBond on disconnect | EXCLUDED | Session sequence | Product boundary: height-adjustable desk control, unrelated to bed integration (accepted bed_control_result: no reachable bed protocol). |
| D087 | capability | No massage, light, bed-side or Wi-Fi/cloud/OTA path | EXCLUDED | Executive summary; C21 | Absence finding: nothing to implement for bed integration. |
