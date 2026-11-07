# Config keys

Ref [#779](https://github.com/kristofferR/ha-adjustable-bed/issues/779). This is
the audit of every `CONF_*` key a config entry stores: who sets it, who reads
it, and whether it still matters. It contains no protocol values.

`tests/test_config_keys.py` checks that every `CONF_*` constant in the
integration has a row here, and that the keys schema 5.2 drops are exactly the
ones listed under [Dropped by schema 5.2](#dropped-by-schema-52). A new key
needs a row before it ships. [Schema 5.3](#massage-off-in-schema-53) corrects
one setting and drops no key.

## Classes

| Class | Meaning |
|---|---|
| Profile | Selects the profile (a field the [profile id](profile-id.md) is derived from) or answers a question a profile declares in `setup_questions.py`. |
| User | Asked by a setup, Configure or app form outside the declarations. A generic field a profile owns (`owns` in [Setup questions](setup-questions.md)) is fixed or derived for that profile and asked for the others. |
| Internal | Written by the integration: detection, runtime state, bonding, pairing, repairs or migration. Never asked in a settings form. |
| Obsolete | No reader on v5. Schema 5.2 drops it. |

A key with any live reader is not obsolete, and a meaningful user setting is
never dropped to tidy a form: a LOGICDATA app entry keeps its pulse count
([#676](https://github.com/kristofferR/ha-adjustable-bed/issues/676)) even though
the app fixes its layout and refresh interval.

## Keys

"Set by" names the form or module that writes the key. "Read by" names the
modules that act on it; diagnostics and support bundles also show most keys. "Bed builders" are the controller builders in `beds/` that
`controller_factory.py` routes each bed type to.
Paired sides store the same keys in their descriptors, and an absorbed entry's
original data and options keep them under `origin_data` and `origin_options`.

### Route

| Key | Class | Set by | Read by |
|---|---|---|---|
| `bed_type` | Profile | Bed-type list in setup, a family step, Configure, Reconfigure | `profile_id.py`, `controller_factory.py`, entity platforms |
| `protocol_variant` | Profile | Route choice in setup (`route` step), a family step, Configure; a question of `bedsense`, `okin_uuid`, `okimat`, `okin_dot`, `sleepys_box25`, `doublesleep`, `richmat`, the Richmat MH apps and `hush_base`; owned by the declarations that fix it | `profile_id.py`, controllers |
| `jiecang_app_profile` | Profile | `jiecang_family` | `profile_id.py`, `beds/jiecang/app.py` |
| `leggett_app_profile` | Profile | `leggett_family`, Configure | `profile_id.py`, bed builders |
| `logicdata_app_profile` | Profile | `logicdata_family`; a question of `logicdata_app` for an entry Configure switches in | `profile_id.py`, bed builders |
| `malouf_app_profile` | Profile | `malouf_family`; a question of `malouf_app` for an entry Configure switches in | `profile_id.py`, bed builders |
| `vibradorm_app_profile` | Profile | `vibradorm` family step | `profile_id.py`, bed builders, `coordinator_bonds.py`, `coordinator_connection.py` |
| `profile_id` | Internal | `profile_id.with_profile_ids` at migration and every setup | `coordinator.py`, diagnostics |
| `address` (Home Assistant's `CONF_ADDRESS`) | Internal | Discovery or the typed address | Coordinator, device registry |
| `name` (Home Assistant's `CONF_NAME`) | User | Setup; the FurniMove rename action and a confirmed V-MAT Basic name write | `coordinator.py` |

### Generic settings

| Key | Class | Set by | Read by |
|---|---|---|---|
| `motor_count` | User | Setup and Configure; a question of the Keeson ORE apps and INNOVA, the Okin remotes and Sleepy's BOX15 and BOX24; owned by the declarations that fix it | `coordinator.py`, controllers, entity platforms |
| `has_massage` | User | Setup and Configure; a question of `vibradorm_app@caresse` and `sleepys_box25`; owned by the declarations that fix or derive it; turned off by [schema 5.3](#massage-off-in-schema-53) where the profile has no massage | Controllers, entity platforms |
| `has_light` | User | A question of `jiecang_app`, `logicdata_app`, `limoss_remote`, `fsm_relax` and `ergomotion_4` | bed builders, `coordinator.py` |
| `disable_angle_sensing` | User | Setup and Configure; owned by the declarations that fix it | `coordinator.py` |
| `motor_pulse_count` | User | Setup and Configure; owned by the declarations that fix it | `coordinator.py`, `beds/richmat_classic/controller.py` |
| `motor_pulse_delay_ms` | User | Setup and Configure; owned by the declarations that fix it | `coordinator.py` |
| `motor_pulse_user_set` | Internal | Setup and Configure record whether the user changed the pulse fields | `coordinator.py` (a profile default applies otherwise) |
| `product_type` | User | A question of `limoss_remote`, `fsm_relax`, the Keeson app layouts and `ergomotion_4`, `richmat_classic_apps`, `gmmotor`, `isleep`, `doublesleep` and `sleeptracker` | bed builders, `pairing.py` |
| `reverse_motor_1`, `reverse_motor_2`, `reverse_motor_3`, `reverse_motor_4` | User | A question of `limoss_remote` and `fsm_relax` | bed builders |
| `ble_device_name` | User | Setup stores the advertised name; the StarCode steps and Configure ask it; a question of `motion_bed` and `motomotion` | Name rules in controllers, `coordinator.py` |
| `preferred_adapter` | User | Setup and Configure | `coordinator.py`, repairs |
| `connection_profile` | User | Configure | `coordinator.py` |
| `disconnect_after_command` | User | `disconnect_after_command` step, Configure | `coordinator.py` |
| `idle_disconnect_seconds` | User | Configure | `coordinator.py` |
| `position_mode` | User | Configure, for beds with position feedback | `coordinator.py` |
| `passive_position_reconciliation` | User | Configure | `coordinator.py` |
| `back_max_angle` | User | Configure | `coordinator.py`, estimated positions |
| `legs_max_angle` | User | Configure | `coordinator.py`, estimated positions |
| `disable_discovery` | User | Configure; saved integration-wide in `discovery_settings.py`, never in the entry | `discovery_settings.py` (a per-entry copy is dropped by schema 5.2) |

### App and product settings

| Key | Class | Set by | Read by |
|---|---|---|---|
| `jiecang_app_layout` | Profile | A question of `jiecang_app` | `beds/jiecang/app.py` |
| `jiecang_app_transport` | Profile | An Advanced question of `jiecang_app` | `beds/jiecang/app.py` |
| `furnimove_remote` | Profile | A question of `furnimove` | bed builders, `beds/furnimove/repair.py` |
| `lp_legacy_model` | Profile | A question of `leggett_lp_legacy` | bed builders |
| `lp_legacy_mode` | Profile | A question of `leggett_lp_legacy` | bed builders |
| `lp_legacy_write_uuid` | Profile | A question of `leggett_lp_legacy` | bed builders |
| `lp_legacy_read_uuid` | Profile | A question of `leggett_lp_legacy` | bed builders |
| `richmat_classic_third_service` | Profile | An Advanced question of `richmat_classic_apps` | `beds/richmat_classic/controller.py` |
| `sleepys_elite_selector` | Profile | A question of `sleepys_elite_app` | bed builders |
| `vibradorm_control_type` | Profile | A question of `vibradorm_app@werkmeister` and `vibradorm_app@caresse`; derived for `vibradorm_app@vmat` | bed builders, `coordinator_bonds.py` |
| `vibradorm_vmat_remote` | Profile | A question of `vibradorm_app@vmat` | bed builders, `coordinator_bonds.py` |
| `vibradorm_restored` | Profile | A question of `vibradorm_app@caresse` | bed builders, `coordinator.py` |
| `vibradorm_floor_light` | Profile | A question of `vibradorm_app@caresse` | bed builders |
| `vibradorm_floor_default` | Profile | A question of `vibradorm_app@caresse` | bed builders, `coordinator.py` |
| `vibradorm_rgb` | Profile | A question of `vibradorm_app@caresse` | bed builders |
| `vibradorm_light_extension` | Profile | A question of `vibradorm_app@caresse` | bed builders, `coordinator.py` |
| `vibradorm_app_metadata` | Internal | Vibradorm app setup and bonding keep the identity the bed reported | `coordinator.py`, `coordinator_bonds.py` |
| `vmatbasic_profile` | Profile | A question of `vmatbasic` | bed builders, `coordinator.py` |
| `vmatbasic_floor_level` | Profile | A question of `vmatbasic`; `coordinator.py` saves a level set on the bed's controls | bed builders |
| `vmatbasic_floor_minutes` | Profile | A question of `vmatbasic`; `coordinator.py` saves a timer set on the bed's controls | bed builders |
| `logicdata_app_family` | Profile | A question of `logicdata_app` | bed builders |
| `logicdata_app_layout` | Profile | A question of `logicdata_app@phone` and `logicdata_app@tablet` for P1, and of `logicdata_app@sleep_smart`; `normalize` sets the MOTIONrelax P2 middle layout | bed builders |
| `logicdata_app_transport` | Profile | An Advanced question of `logicdata_app` | bed builders |
| `malouf_app_model` | User | `malouf_app` profile questions, Configure | bed builders |
| `malouf_app_transport` | User | `malouf_app` profile questions, Configure | bed builders |
| `malouf_app_primary` | User | `malouf_app` profile questions, Configure | bed builders |
| `malouf_layout` | User | Malouf receiver profile questions, Configure | `beds/malouf/controller.py` |
| `malouf_memory_slots` | User | Malouf receiver profile questions, Configure | `beds/malouf/controller.py` |
| `octo_pin` | User | A question of `octo`, `verify_octo_pin`, the Octo PIN action | `beds/octo/controller.py`, `beds/octo/runtime.py`, `beds/octo/services.py` |
| `octo_motor_count_override` | User | A question of `octo`; written by [schema 5.5](#octo-motor-layout-in-schema-55) where an Octo setup lacks it | `beds/octo/controller.py`, `config_flow.py` |
| `jensen_pin` | User | A question of `jensen`, Configure | `beds/jensen/controller.py` |
| `richmat_remote` | Profile | A question of `richmat` without an RMControl product; the Richmat question stages the code the Bluetooth name carries | `beds/richmat/controller.py`, `coordinator.py`, `profile_recommendations.py` |
| `rmcontrol_product` | Profile | A question of `richmat`; the Richmat question's RMControl answer requires one | `beds/richmat/controller.py` |
| `rmcontrol_side` | Profile | A question of `richmat` with an RMControl product | `beds/richmat/controller.py` |
| `cb24_bed_selection` | User | A question of `okin_cb24` | `beds/okin_cb24.py` |
| `gmmotor_side` | Profile | A question of `gmmotor` | bed builders |
| `starcode_abm5_4_command_selector` | User | A question of `starcode_abm5_4` | bed builders |
| `starcode_abm5_4_ui_selector` | Internal | `starcode_abm5_4` copies a changed command selector | bed builders |
| `starcode_abm5_4_transport_selector` | User | A question of `starcode_abm5_4`, or the setup connection probe | bed builders |
| `starcode_m5x5_profile` | User | A question of `starcode_m5x5` | bed builders, `beds/starcode/accessory_group.py` |
| `starcode_m1x12_profile` | User | A question of `starcode_m1x12` | bed builders, `beds/starcode/accessory_group.py` |
| `starcode_lift_entries` | User | A question of `starcode_m5x5`, `starcode_m1x12` and `star_elevate` | `beds/starcode/accessory_group.py`, `pairing_candidates.py` |
| `motion_bed_restored` | Profile | A question of `motion_bed` | bed builders |
| `motion_bed_preset` | Profile | A question of `motion_bed` | bed builders |
| `motion_bed_movement` | Profile | A question of `motion_bed` | bed builders |
| `sleeptracker_foundation` | Profile | A question of `sleeptracker` | bed builders |
| `sleeptracker_unit_number` | Profile | A question of `sleeptracker` | bed builders |
| `sleeptracker_snapshot_side` | Profile | A question of `sleeptracker` | bed builders |
| `sleeptracker_restricted` | Profile | A question of `sleeptracker` | bed builders |
| `sleeptracker_processor_type` | Profile | A question of `sleeptracker` | bed builders |
| `limoss_remote_theme` | User | `limoss_remote` step, Configure | bed builders |
| `limoss_remote_state` | Internal | `coordinator.py` keeps the remote's state | bed builders |
| `fsm_relax_memory_names` | User | A question of `fsm_relax` | bed builders |
| `serta_mp_memory_1_head`, `serta_mp_memory_1_foot`, `serta_mp_memory_2_head`, `serta_mp_memory_2_foot`, `serta_mp_memory_3_head`, `serta_mp_memory_3_foot`, `serta_mp_memory_4_head`, `serta_mp_memory_4_foot` | User | A question of `serta_mp_remote` | `beds/serta_mp_remote.py` |
| `ergomotion4_model_keys` | User | A question of `ergomotion_4`, for an Other product | `beds/ergomotion4/controller.py` |
| `ergomotion4_massage_keys` | User | A question of `ergomotion_4`, for an Other product | `beds/ergomotion4/controller.py` |
| `ergomotion4_product_name` | User | A question of `ergomotion_4`, for an Other product | `beds/ergomotion4/controller.py` |
| `ergomotion4_rgb` | User | A question of `ergomotion_4`, for an Other product | `beds/ergomotion4/controller.py` |
| `pairlink_role` | User | Configure, for Reverie Pairlink | `beds/reverie/pairlink_runtime.py`, `coordinator_connection.py` |
| `pairlink_host_source` | User | Configure, for Reverie Pairlink | `__init__.py` |
| `pairlink_home_id` | User | Configure, for Reverie Pairlink | `beds/reverie/pairlink_runtime.py` |
| `pairlink_password_text` | User | Configure, for Reverie Pairlink | `beds/reverie/pairlink_runtime.py` |
| `pairlink_password_hex` | User | Configure, for Reverie Pairlink | `beds/reverie/pairlink_runtime.py` |
| `kaidi_room_id` | Profile | A question of `isleep`; `beds/kaidi/metadata.py` reads it from a Kaidi bed's advertisement | `beds/kaidi/controller.py`, `beds/kaidi/floyd.py`, `profiles/kaidi.py` |
| `kaidi_sofa_acu_no` | Profile | A question of `isleep`; `beds/kaidi/metadata.py` reads it from a Kaidi bed's advertisement | `beds/kaidi/controller.py`, bed builders, `profiles/kaidi.py` |
| `kaidi_target_vaddr` | Internal | `beds/kaidi/metadata.py` from the advertisement | `beds/kaidi/controller.py` |
| `kaidi_product_id` | Internal | `beds/kaidi/metadata.py` from the advertisement | `beds/kaidi/controller.py`, bed builders, `profiles/kaidi.py` |
| `kaidi_adv_type` | Internal | `beds/kaidi/metadata.py` from the advertisement | Setup log, diagnostics |
| `kaidi_resolved_variant` | Internal | `beds/kaidi/metadata.py` from the advertisement | `pairing.py`, `config_flow.py` |
| `kaidi_variant_source` | Internal | `beds/kaidi/metadata.py` from the advertisement | Setup log, diagnostics |
| `remacro_model` | Internal | `beds/remacro/protocol.py` caches the advertised model | bed builders, `beds/remacro/discovery.py` |
| `remacro_led_level` | Internal | `coordinator.py` keeps the LED levels | `beds/remacro/protocol.py` |
| `zseries_alarm_available` | Internal | `beds/serenity/controller.py` records whether the alarm exists | `beds/serenity/controller.py` |
| `sleep_number_mcr_client_id` | Internal | `beds/sleep_number/mcr.py` keeps the MCR client id | `beds/sleep_number/mcr.py` |
| `okimat_model_on_cst` | Internal | `beds/okin_cst.py` records an Okimat model seen on an Okin CST route | `beds/furnimove/repair.py` |
| `rf_eco_staircase_confirmed` | Internal | The FurniMove layout repair records the answer | `beds/furnimove/repair.py` |
| `furnimove_route_kept` | Internal | The FurniMove route repair records Keep | `beds/furnimove/repair.py` |
| `okin_cst_kept` | Internal | The Okin CST route repair records Keep | `beds/furnimove/repair.py` |

### Bonding

| Key | Class | Set by | Read by |
|---|---|---|---|
| `ble_bond_established` | Internal | Setup pairing, `coordinator_bonds.py`, repairs | `coordinator.py`, `coordinator_bonds.py`, repairs |
| `ble_bond_marker_unreliable` | Internal | `coordinator_bonds.py` | `coordinator.py`, repairs |
| `ble_bond_context` | Internal | `coordinator_bonds.py`, repairs | `bond_verification.py`, `coordinator_bonds.py`, repairs |
| `ble_bond_attempted_source` | Internal | `coordinator_bonds.py` | `coordinator_bonds.py` |

### Pairing

| Key | Class | Set by | Read by |
|---|---|---|---|
| `pair_id` | Internal | `pairing.py` when beds are combined | `pairing.is_paired`, paired setup and registry |
| `pair_mode` | Internal | `pairing.py` | Paired setup, `coordinator.py`, `paired_devices.py` |
| `pair_children` | Internal | `pairing.py` | `pairing.py`, `profile_id.py`, migration |
| `pair_member_addresses` | Internal | `pairing.py` | `pairing.pair_member_addresses` (discovery deduplication) |
| `pair_connection_mode` | Internal | `pairing.py`, from the combine step | `paired_coordinator.py` |
| `side` | Internal | `pairing.py`, per side descriptor | Paired setup, registry, repairs |
| `pair_schema_version` | Obsolete | Nothing since schema 5.2 | Nothing; see below |

### Review and migration

| Key | Class | Set by | Read by |
|---|---|---|---|
| `profile_review_pending` | Internal | Schema 4.3 migration, `profile_review.py` | `profile_review.py` |
| `profile_review_kept` | Internal | `profile_review.py` on Keep | `profile_review.py` |
| `profile_migration` | Internal | Schema 5.1, 5.2, 5.3 and 5.5 migrations | Diagnostics, support bundles |

## Flow inputs

These keys name form fields that a flow reads and never stores.

| Key | Step |
|---|---|
| `acknowledge` | Estimated positions (`position_estimate_flow.py`) |
| `measure` | Estimated positions (`position_estimate_flow.py`) |
| `pair_selection` | `pair_beds` (`pairing_candidates.py`) |

## Dropped by schema 5.2

`async_migrate_entry` drops these keys from entry data and options, from each
paired side, and from each side's `origin_data` and `origin_options`
(`V5_2_OBSOLETE_KEYS` in `__init__.py`). The migration record
(`profile_migration`, shown in diagnostics and support bundles) lists each
dropped key under `dropped_keys`, by where it was stored (`data`, `options`,
`data.left`, `data.left.origin_options` and so on). Keys this audit does not
list stay untouched.

| Key | Evidence |
|---|---|
| `pair_schema_version` | Written on every pair since 4.0.0 ([#384](https://github.com/kristofferR/ha-adjustable-bed/pull/384)) and never read in any release. The entry's schema version is what versions pair data: schema 4.2 and 5.1 migrated pair data without it. Schema 5.2 removes the constant and its writers. |
| `disable_discovery` | Integration-wide since it was added in 2.9.11 ([discussion #342](https://github.com/kristofferR/ha-adjustable-bed/discussions/342)): Configure saves it in `discovery_settings.py`, whose Store is its only reader. Configure has removed a per-entry copy on save since 3.4.0, so a stored copy is never read. The form field keeps its key. |

## Massage off in schema 5.3

`has_massage` stays a user setting, but three layouts have no massage: a
FurniMove handset without massage rows, `comfort_enhancements:mc3` and a
`sleepys_elite_app` control box other than BOX25. Their profiles own the field
and set it off: FurniMove and Sleepy's derive it from the handset or control
box, and MC3 fixes it. Saved entries could still have it on, which showed
massage buttons that raise errors or do nothing
([#787](https://github.com/kristofferR/ha-adjustable-bed/issues/787)).

The 5.3 step (`migrate_v5_3_data` in `__init__.py`) sets it to false wherever
`profile_massage` in `setup_questions.py` reads off from the saved route: entry
data, each paired side's effective settings and each side's `origin_data`. That
is the value setup and Configure save for the same route, so the two cannot
disagree. The layout, handset or control box decides one side's massage, so
these profiles own `has_massage` per side of a pair (`app_profiles.py`). A
paired entry with one of them first moves an old shared `has_massage` option
into the sides it reached and drops it, so it cannot override a corrected side
and every other side keeps its value. The record lists each corrected place
under `massage_off`. The step deletes
the massage buttons those runtimes had from the entity registry, and leaves
every other layout and key alone.

## Octo motor layout in schema 5.5

Before Octo had its own motor layout selector (`octo_motor_count_override`),
a stored `motor_count` other than 2 was the user's explicit layout and 2
followed the advertised count. The controller, Configure and the pairing check
each kept a fallback for entries without the selector. The 5.5 step
(`migrate_v5_5_data` in `__init__.py`) writes the selector instead: the stored
count when it is 1, 3 or 4, otherwise `auto`. It covers entry data, each paired
side's effective settings and each side's `origin_data`, leaves a saved
selector alone, and lists each place under `octo_motor_count_override` in the
migration record. The fallbacks are gone.

Schema 5 is one way: an entry at 5.2 or 5.3 cannot load on 4.x, and restoring a
Home Assistant backup is the only way back.
