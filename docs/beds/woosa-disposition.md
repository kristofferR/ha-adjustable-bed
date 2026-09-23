# Woosa Sleep implementation discovery ledger

This is the post-freeze comparison for the explicitly selected Woosa Sleep profile. Evidence identity and hardware limitations are in [the profile guide](woosa.md). The accepted `com.sn.woosa` 1.1.9 report contains 61 command rows (59 fixed frames and two builders), 92 vectors, 51 selector entries and 30 candidate paths. Those are evidence coverage counts, not four separate implementation backlogs.

Every discovery below has exactly one disposition. Rows group behaviors with the same integration decision; the following command, selector and candidate maps account for every source ID. `IMPLEMENTED` means added for Woosa, `ALREADY_IMPLEMENTED` means a concretely reused implementation verified against Woosa evidence, and `EXCLUDED` gives the boundary or safety reason. Physical validation remains deferred; it is not an exclusion reason.

## Discovery decisions

Implementation references below are relative to `custom_components/adjustable_bed/`; tests are repository-relative. Woosa controller tests are in `tests/test_woosa.py` and profile wiring tests in `tests/test_woosa_config.py`.

| ID | Reachable discovery | Disposition | Implementation or exact exclusion reason |
|---|---|---|---|
| W01 | Explicit Woosa app identity, shared `QMS-MQ`/`QMS2` aliases, only back/legs, one Favourite slot, profile-specific accessories | IMPLEMENTED | `controller_factory.py` selects `beds/woosa.py:WoosaController` only for `protocol_variant=woosa`; `config_flow.py`, `const.py`; `tests/test_woosa_config.py:test_factory_requires_explicit_woosa_selection`, `test_manual_setup_saves_woosa_profile`, `test_options_select_woosa_and_offline_reload`, and controller capability tests. Automatic names retain the common profile. |
| W02 | BLE connection/discovery, FFE1 write/notification subscription and disconnect | ALREADY_IMPLEMENTED | `coordinator.py` owns the connection; `beds/solace.py` supplies FFE1 transport and notification subscription; `tests/test_solace.py:TestSolaceController.test_control_characteristic_uuid`, `test_write_command`, `test_write_command_not_connected`, and Woosa session tests. No service UUID or authentication exchange is invented. |
| W03 | Literal fixed-frame encoding, including shared frame bytes inherited from Solace | IMPLEMENTED | `beds/woosa.py` command tables plus literal vectors in `tests/test_woosa.py`. All 59 distinct fixed frames are mapped below; shared bytes do not imply shared capabilities. |
| W04 | Back/legs start, global STOP and Woosa leg-down frame `08` | IMPLEMENTED | `beds/woosa.py:move_legs_down`, inherited `SolaceController._move_with_stop`, and movement/STOP tests. Frame `08` is retained for both leg down and Flat because the artifact proves both callsites. |
| W05 | Serialized commands, cancellation and STOP cleanup | ALREADY_IMPLEMENTED | `coordinator.py:async_execute_controller_command`, `async_stop_command`, inherited bounded movement lifecycle in `beds/solace.py`, Woosa cancellation tests. HA's movement ceiling is an integration safety policy, not a firmware timeout. |
| W06 | Flat and Favourite/Love/TV/Zero-G recall, built-in versus saved branches, STOP + 200 ms activation | IMPLEMENTED | `WoosaController._send_preset`, `preset_memory`, `preset_love`, inherited `preset_tv`/`preset_zero_g`, `controller_button_specs` and preset tests. `preset_flat` directly sends its frame without a preamble. Uses the Dashboard's saved-presence selection with explicit HA actions. |
| W07 | Save current position in all four app preset types and refresh presence | IMPLEMENTED | `WoosaController.program_memory`, `save_preset` and save/query tests. Favourite is numbered Memory 1; the other three remain named presets. |
| W08 | Four stored-preset queries and presence-only replies | IMPLEMENTED | `WoosaController._async_query_preset_states`, `_parse_notification`; startup and four-prefix tests. A reply records availability, never angle or selected position. |
| W09 | Initialization write, local clock and alarm query, startup pacing | IMPLEMENTED | `WoosaController._async_query_preset_states` and startup-order tests, plus clock vectors. The initial write's physical meaning remains unspecified. |
| W10 | Back/leg massage 0–3, increments/decrements, four modes, cycle, timers, Off | IMPLEMENTED | `WoosaController.set_massage_intensity`, `set_massage_mode`, `massage_mode_step`, `set_massage_timer`, inherited step methods, numbers/buttons/selects and command tests. Increment follows the artifact's direct Manual screen path. |
| W11 | Massage start with Off, timer, back, leg and mode at 400 ms intervals | IMPLEMENTED | `WoosaController.massage_toggle` and pacing/cancellation tests, following `MassageActivity` A07. |
| W12 | Massage back/leg level and mode notifications, active state | IMPLEMENTED | `WoosaController._parse_notification` and the twelve full-frame notification vectors. |
| W13 | Brightness levels 0–10, separate Off and on timers 10/480/600 minutes | IMPLEMENTED | `WoosaController.lights_on`, `lights_off`, `set_light_timer`, `set_light_level`, light/number/select entities and command/state tests. Requested state is optimistic. |
| W14 | Light query and loose brightness candidate extraction | IMPLEMENTED | `WoosaController._async_query_preset_states`, `_parse_notification` and diagnostic candidate tests. Accepted candidates remain diagnostic data. |
| W15 | Dynamic alarm builder: enable, BCD time, weekdays/repeat, modes and flags | IMPLEMENTED | `WoosaController.program_solace_alarm`, `beds/solace.py:build_solace_alarm_command`, `services.py:handle_solace_set_alarm` and alarm vectors/capability-gate tests; only the three proven UI modes and two sound choices are offered. |
| W16 | No-alarm and alarm replies, raw mode retained as diagnostic state | IMPLEMENTED | `WoosaController._parse_notification` and alarm reply tests; valid notifications update the controller alarm state. |
| W17 | Dynamic little-endian additive checksum and clock BCD encoding | ALREADY_IMPLEMENTED | `beds/solace.py:build_solace_clock_command`, `_with_additive_checksum`; `tests/test_woosa.py:test_startup_schedule_and_controller_replacement`, `test_alarm_packet_and_sound_gate` and `tests/test_solace.py:TestSolaceController.test_motionflex_variable_frame_vectors` verify equivalence. |
| W18 | Arbitrarily prefixed name substrings and Android scan batching/auto-reconnect screen behavior | EXCLUDED | Discovery safety/product boundary: shared names cannot establish a Woosa product; broad leading-wildcard automatic matching can capture unrelated FFE1 devices. Known-prefix discovery and manual explicit selection remain available. Android activity navigation, five-second scan UI and saved-address screen state do not define an HA protocol requirement. |
| W19 | Discovery-time characteristic write without `setValue` | EXCLUDED | T04 has no application-defined payload. Writing a runtime cached or unset characteristic value is nondeterministic and unsafe; no handshake bytes are invented. |
| W20 | Reads of every descriptor and discarded read callbacks | EXCLUDED | T06 results have no app consumer or device behavior. HA owns CCCD operations needed for notifications; unrelated descriptor reads add no bed capability. |
| W21 | Missing STOP on Android cancellation/lifecycle exit, uncancelled delayed writes and concurrent writes | EXCLUDED | Safety: reproducing these omissions would permit continued movement or stale commands after Stop/disconnect. HA retains cancellation, serialization and cleanup. |
| W22 | Contradictory editor preset predicates, switch-off/conflict navigation state | EXCLUDED | A03/A04 screen-local state is not a hardware model. The editor reverses saved predicates for Favourite/TV/Zero-G and ignores saved Love. These contradictory UI predicates introduce no additional wire commands; HA exposes all proven command paths through explicit actions and uses the Dashboard's presence semantics. Flat and STOP remain independently available. |
| W23 | Dashboard back massage chosen from leg preference and Android screen-specific preference coupling | EXCLUDED | App-local UI coupling is outside HA control semantics. HA retains independent back/leg settings with the proven editor start sequence and direct Manual increment path. Independently exposed level, mode, timer, step and Off controls compose every alternate wire sequence using the exact implemented frames: Manual start is back, leg, mode, timer with 400 ms gaps; the editor increment path is a step, the 10-minute timer at 400 ms, then the preferred timer at 800 ms. These wire operations remain implemented under W10/W11; only Android screen/preference coupling is excluded. |
| W24 | Promoting loose light candidates to confirmed state | EXCLUDED | Safety/state correctness: N05 accepts any matching control header and absolute byte 7; a legitimate leg-massage reply equals a brightness frame. The evidence cannot distinguish these as physical light feedback. Values remain diagnostic; HA write state stays optimistic. |
| W25 | Truncated or shifted alarm payloads and unchecked offsets | EXCLUDED | Safety: the app can throw or decode unrelated bytes because a header substring does not anchor its absolute offsets. HA validates the anchored packet and minimum length before changing alarm state. |
| W26 | Automatically re-emitting arbitrary received alarm modes `00`–`FF` | EXCLUDED | Safety: outside UI values `01`/`02`/`03`, the physical bed action is unspecified. Raw modes are preserved for diagnosis; HA never guesses an unknown movement action when writing an alarm. |
| W27 | Repeat enabled with a nonempty map containing no selected weekdays | EXCLUDED | Safety: the artifact emits repeat=1 with weekday mask=0 for stale all-false map entries, but defines no scheduling semantics for that combination. HA expresses recurrence using actual selected weekdays and does not schedule an ambiguous empty repeat. |
| W28 | Nicknames, preset names/icons, language, display-name substitutions and preferences with no wire behavior | EXCLUDED | App-local presentation/persistence is unrelated to BLE bed integration. Includes P04 substitutions after name filtering, local massage timer wheel/save behavior, mode-left no-op, wrong initial light checkbox from massage preference and the 300 ms Android button debounce. HA names and UI state belong to HA. |
| W29 | Uncalled read/RSSI/listener wrappers, advertisement parser, five-memory/sync preferences and unused transforms | EXCLUDED | Dead/unreachable artifact code: T07/T08/T10 and P03/P05/P06 have no live callers. These do not establish additional device operations or capabilities. Used encoding transforms remain covered by W03/W15/W17. |
| W30 | Terms-image WebView, third-party libraries, network checks and unrelated logging | EXCLUDED | P07/P08 are unrelated app/framework behavior. No additional bed transport, executable web bridge or protocol is present. |

Ledger totals: **IMPLEMENTED 14, ALREADY_IMPLEMENTED 3, EXCLUDED 13**. These 30 decisions cover the evidence maps below; the maps do not add dispositions or double-count findings.

## Complete command map

The accepted IDs are retained so the machine-local report can be reconciled without copying its raw output. Each range includes every integer ID between its endpoints.

| Accepted command IDs | Behavior | Decision | Code/test coverage |
|---|---|---|---|
| C01–C02 | Alarm/status query and initialization write | W09 | Woosa startup sequence/order tests |
| C03–C06 | Four preset-presence queries | W08 | Woosa query sequence and prefix tests |
| C07 | STOP | W04 | Movement cancellation and preset-preamble tests |
| C08–C09, C11–C12 | Back up/down, legs up/down; C12 also Flat | W04 | Four movement vectors, Flat test |
| C10, C13–C14 | Built-in TV, Zero-G, Love | W06 | Named preset branch tests |
| C15–C18 | Back/leg massage increment/decrement | W10 | Four step vectors |
| C19–C21 | Massage timers 10/20/30 | W10 | Timer vector tests |
| C22–C24 | Timed light on 10/480/600 | W13 | Light timer vector tests |
| C25 | Massage Off/reset | W10 | Massage Off and start-sequence tests |
| C26, C40–C49 | Brightness 0–10 | W13 | Eleven level vectors |
| C27 | Separate light Off | W13 | Dedicated Off vector |
| C28–C35 | Absolute back/leg massage 0–3 | W10 | Eight level vectors |
| C36–C39 | Four absolute massage modes | W10 | Four mode vectors |
| C50, C52, C54, C56 | Save TV, Zero-G, Favourite, Love | W07 | Four save vectors and query refresh |
| C51, C53, C55, C57 | Recall saved TV, Zero-G, Favourite, Love | W06 | Four saved-preset vectors |
| C58 | Cycle massage mode | W10 | Cycle vector |
| C59 | Light query | W14 | Startup/query vector |
| C60 | Clock builder | W09, W17 | `test_startup_schedule_and_controller_replacement`; inherited clock boundary vector |
| C61 | Alarm builder | W15 | UI-supported alarm vectors; W26/W27 explicitly bound unsafe raw-state branches |

## Complete selector map

| Accepted dimension | Values | Count | Decision |
|---|---|---:|---|
| discovery | `QMS-MQ`, `QMS2` | 2 | W01/W18 |
| preset_type | Favourite, Love, TV, Zero-G | 4 | W06/W07 |
| preset_has_memory | false, true | 2 | W06/W08; conflicting editor predicates W22 |
| preset_switch | false, true | 2 | W06; Android local conflict/deactivation state W22 |
| back_massage_level | 0, 1, 2, 3 | 4 | W10/W12 |
| leg_massage_level | 0, 1, 2, 3 | 4 | W10/W12 |
| massage_mode | 1, 2, 3, 4 | 4 | W10/W12 |
| massage_minutes | 10, 20, 30 | 3 | W10/W11 |
| light_level | 0–10 | 11 | W13/W14/W24 |
| light_minutes | 10, 480, 600 | 3 | W13 |
| alarm_enable | false, true | 2 | W15/W16 |
| alarm_map_nonempty | false, true | 2 | W15; ambiguous all-false map branch W27 |
| alarm_mode | `01`, `02`, `03` | 3 | W15 |
| alarm_received_mode | raw `00`–`FF` domain | 1 | W16 preserves; W26 excludes automatic replay |
| alarm_massage | false, true | 2 | W15/W16 |
| alarm_sound | false, true | 2 | W15/W16 |

Total: **51 selector entries**, including one raw-domain entry, not 256 independently advertised alarm actions.

## Complete candidate and parser map

| Accepted candidate IDs | Decision |
|---|---|
| T01 scan | W01/W18 |
| T02 connect/discover/disconnect | W02/W05 |
| T03 writes | W02/W03/W05 |
| T04 unset-value write | W19 |
| T05 notifications/CCCD | W02 |
| T06 descriptors | W20 |
| T07 characteristic read, T08 RSSI read, T10 listener | W29 |
| T09 callbacks/dispatch | W08/W12/W14/W16 |
| P01 fixed protocol | W03 |
| P02 dynamic checksum | W15/W17 |
| P03 advertisement parser, P05 memory/sync preferences, P06 unused transforms | W29 |
| P04 display conversion | W28 |
| P07 WebView, P08 library terms | W30 |
| A01 motion | W04/W05/W21 |
| A02 Flat | W04/W06 |
| A03 Dashboard presets, A04 editor presets | W06/W22 |
| A05 save | W07/W08/W28 |
| A06 Manual massage, A07 editor massage, A08 Dashboard massage | W10/W11/W23 |
| A09 massage adjustment | W10/W23/W28 |
| A10 light | W13/W14/W24/W28 |
| A11 startup/query | W08/W09/W17/W21 |
| A12 alarm | W15/W16/W25/W26/W27 |

All **30 candidates** (T01–T10, P01–P08, A01–A12) are mapped. Parser N01–N03 maps to W12; N04 to W08; N05 to W14/W24; N06–N07 to W16/W25/W26. Valid frozen vectors are retained; malformed/ambiguous behavior and unknown-mode replay have explicit exclusions instead of silent normalization.

The exhaustive artifact search found no OTA, firmware transport, PIN/authentication, capability negotiation, measured positions, extra motor axes, side-addressing, cloud/WiFi/classic bed transport or additional configuration/calibration commands. Absence is a profile boundary, not an unimplemented reachable feature.

## Durable verification index

The following focused tests are in [`tests/test_woosa.py`](../../tests/test_woosa.py) unless a different file is linked. This index supplies exact symbols for the implementation decisions above.

| Decisions | Focused tests |
|---|---|
| W01 | `test_capability_surface`, `test_woosa_setup_restores_light_and_exposes_profile_controls`; [`tests/test_woosa_config.py`](../../tests/test_woosa_config.py): `test_woosa_is_an_explicit_solace_variant`, `test_factory_requires_explicit_woosa_selection`, `test_manual_setup_saves_woosa_profile`, `test_options_select_woosa_and_offline_reload`, `test_paired_options_preserve_different_side_profiles` |
| W02 | [`tests/test_solace.py`](../../tests/test_solace.py): `TestSolaceController.test_control_characteristic_uuid`, `test_write_command`, `test_write_command_not_connected`; Woosa `test_startup_schedule_and_controller_replacement` |
| W03–W05 | `test_movement_vectors_and_stop_cleanup`, `test_preset_cancellation_during_preamble`, `test_massage_cancellation_stops_without_later_writes`; command vectors in the following rows |
| W06–W08 | `test_preset_presence_selects_dashboard_branch`, `test_favourite_requires_reported_memory_and_flat_is_direct`, `test_save_presets_queries_four_slots`, `test_notification_vectors`, `test_preset_reply_is_anchored_and_not_a_position` |
| W09, W17 | `test_startup_schedule_and_controller_replacement`, `test_clock_date_encoding`; [`tests/test_solace.py`](../../tests/test_solace.py): `TestSolaceController.test_motionflex_variable_frame_vectors`, `test_alarm_weekday_mask_ignores_duplicate_days` |
| W10–W12 | `test_absolute_massage_vectors`, `test_massage_modes_and_timer_vectors`, `test_massage_manual_steps_and_limits`, `test_massage_start_sequence_preserves_independent_zones`, `test_massage_cancellation_stops_without_later_writes`, `test_notification_vectors`, `test_custom_buttons_dispatch_to_live_controller`, `test_massage_restart_preserves_requested_levels`, `test_timer_off_and_late_cancellation_clear_active_state` |
| W13–W14, W24 | `test_light_level_vectors`, `test_light_timer_and_explicit_off`, `test_ambiguous_light_value_is_diagnostic_only`, `test_startup_schedule_and_controller_replacement`, `test_woosa_setup_restores_light_and_exposes_profile_controls` |
| W15–W16, W25–W27 | `test_alarm_packet_and_sound_gate`, `test_alarm_supported_selectors`, `test_alarm_sound_preflight_checks_all_targets`, `test_alarm_parser_raw_state_and_malformed_input`; inherited default alarm and weekday-mask vectors above. Unknown raw modes and empty-repeat UI maps remain explicitly excluded writes. |

Clock coverage uses the app's actual date-to-weekday derivation. The report's independently supplied `V-CLOCK2` weekday input is Monday (`1`) despite its date being 2000-01-01, a Saturday (`6`). `test_clock_date_encoding` checks the date-derived Saturday frame; this is a corrected input combination, not a change to the accepted packet layout or checksum.
