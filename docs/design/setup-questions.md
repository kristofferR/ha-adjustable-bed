# Setup questions declared by profiles

Ref [#779](https://github.com/kristofferR/ha-adjustable-bed/issues/779). Part of
the setup design chosen in [#676](https://github.com/kristofferR/ha-adjustable-bed/issues/676).

A profile declares what setup and Configure ask for it, and which generic fields
it sets itself, in `custom_components/adjustable_bed/setup_questions.py`. One
generic config-flow step, `profile_questions`, renders the declared questions;
Configure renders the same declarations in its settings form.

## Declarations

A `SetupProfile` has:

| Field | Meaning |
|---|---|
| `owns` | Each generic field the profile owns (`GENERIC_FIELDS`): a fixed value, applied when setup or Configure saves, or `SET_BY_PROFILE` when the profile derives it. No form shows an owned field while that profile is chosen. |
| `questions` | The `Question`s to ask, in order. |
| `normalize` | Builds the staged setup from the previous one and the submitted answers, for answers that need cleaning or that clear other settings. |
| `validate` | Errors by field for the staged setup with the answers applied. |
| `derive` | The owned fields the profile computes from its answers, such as a FurniMove handset table's motor count and massage. |
| `title` | The name the step shows for the staged route. |

A `Question` stores its answer under `key`. Its `choices` are fixed labels or a
function of the staged setup, such as the layouts the chosen app supports;
without choices it is yes or no, or free `text`. Its `default` is a value, a
function of the staged setup, `REQUIRED`, or `OPTIONAL` (no default, may stay
unanswered). A staged answer the choices no longer offer falls back to the
default, and `staged_when` limits when a staged answer is the default at all,
for a value the profile stored itself. `validator` replaces the one the choices
imply, for a range or a format. An `advanced` question sits in a collapsed
Advanced section in setup.

`when` is the condition for asking a question: a Home Assistant field condition
on another answer of the same form (`{"field": ..., "value": ...}`, or an
operator such as `in`). It renders as a native conditional field
(`data_entry_flow.Required/Optional(..., visible=...)`, Home Assistant 2026.11),
so the form never redraws: a hidden question is neither required nor saved.
When the form does not ask the condition's field, such as a route Configure
leaves to the guided change, the saved setup settles the condition instead.

Declarations are keyed like a [profile id](profile-id.md): `bed_type`,
`bed_type:variant`, `bed_type@app` or `bed_type:variant@app`, and the most
specific key that matches a route wins, so a variant entry replaces its bed
type's entry. `app_profiles.hidden_generic_fields` reads `owns` plus the generic
fields the profile asks itself (motor count, variant), so no generic form asks
them twice. A question with whole-number choices accepts the text a select
returns.

## Setup and Configure

- Setup asks every declared question. A family step (see
  [Guided setup changes](guided-setup-changes.md)) chooses the app first, then
  hands the staged route to `profile_questions`.
- Configure asks the questions that are not the managed family's route keys:
  the app, layout and route change only through the guided change. An entry
  that Configure switches into a managed family from another bed type answers
  that family's route questions there, since it has no guided change yet.
- `tests/test_setup_questions.py` checks that each declared question has its
  `strings.json` label in the generic step (or its Advanced section) and in
  Configure, so a field cannot ship unlabelled.

## Generic forms

The generic setup forms (`bluetooth_confirm`, `manual_config`, `manual_entry`)
are drawn once for every bed-type row. Each field that belongs to some rows is
a native conditional field on the bed-type field, listing both each row's label
(what the picker submits) and its choice (what the API may submit):

- a bed type's own settings (Octo PIN and motor count, Jensen PIN, Richmat
  remote and RMControl product, Malouf layout and memory slots, CB24 side) show
  only for its rows;
- a generic field shows except for the rows whose profile owns it, and a
  field every row owns is left out;
- the Advanced route section shows only for the drawn bed type's generic rows.
  Another bed type with several routes asks for them in the `route` step;
- Svane's app profiles are asked on the form for its generic row. For that
  row, a generic field hinges on the route field instead, which reads as
  absent for other rows. A Svane app row sets its own route.

Defaults cannot follow a changed row. A field whose default depends on the bed
type (motor count, angle sensing, pulse count and delay) that is left at the
default it was drawn with saves the chosen profile's default instead; a value
the user changed is kept. Disconnect after each command asks again instead
when the two defaults differ.

Configure conditions owned generic fields, and the L&P app field, on its route
field the same way. It still redraws after a bed-type change, and after a route
change that alters the motor count choices or position feedback: those change
defaults and the route list, which a field condition cannot.

## Dedicated steps

A dedicated step remains only for what data cannot express, with its reason
recorded here as each family converts. `tests/test_setup_questions.py` checks
this section and [Shared steps](#shared-steps) against the setup and Configure
flows, so a new step cannot appear unrecorded and a removed one cannot linger.

| Step | Why it is not data |
|---|---|
| Family steps (`jiecang_family`, `okin_family`, `keeson_family`, `solace_family`, `leggett_family`, `sleepys_family`, `customatic_family`, `jordans_family`, `starcode_family`, `remacro_family`, `vibradorm`) | They choose the profile itself, and Keep, before any profile's questions exist |
| `keeson_app`, `keeson_restonic`, `keeson_route` | Each picks the Keeson variant, which is the profile, not one of its answers |
| `solace_woosa` | A note before choosing Woosa Sleep; it asks nothing |
| `jiecang_legacy` | Part of the Jiecang journey: a remote route chosen in place of an app needs the motor count and cadence the app had fixed |
| `verify_octo_pin` | Authentication: setup finishes only after the bed accepts the PIN, or the user corrects it |
| `starcode_app` | Probes the transport over a live connection when the Bluetooth name cannot settle it |
| `starcode_m5x5`, `starcode_m1x12` | Their lift groups name other config entries, which a declaration's checks cannot see |
| `cluster033_app` | A custom product picks its keys in multi-select lists, which a question cannot ask yet |
| `fsm_relax` | The eight memory names are one multi-value text field, which a question cannot ask yet |
| `route` | The routes of a bed type other than the one the form was drawn for; a section's choices cannot change with the row |

### Not converted yet

These app steps ask plain questions a declaration could express. They stay
listed so the gap is visible until each converts.

| Step | Questions |
|---|---|
| `logicdata_app` | App, command family, layout, transport and light |
| `malouf_app` | App, model, transport and primary controller |
| `limoss_remote` | Product, light, massage, reversals and remote theme |
| `gmmotor` | Catalog product, suggested from the Bluetooth name, and side |
| `isleep` | Product, room and sofa numbers, after reading the advertised metadata |
| `doublesleep` | Model and variant, with the model default from the advertisement |
| `sleeptracker` | Foundation, model, unit, snapshot side, restriction and processor |
| `motion_bed` | Advertised name, restored setup, preset and movement |

## Shared steps

These steps serve every bed type or route, so no profile owns them.

| Step | Purpose |
|---|---|
| `user`, `scan`, `scan_result`, `manual`, `select_actuator`, `select_variant`, `bluetooth`, `bluetooth_disambiguate` | Find the bed and pick its bed type |
| `bluetooth_confirm`, `manual_config`, `manual_entry` | The generic setup forms |
| `disconnect_after_command` | The connection-lifetime choice |
| `profile_questions` | The declared questions |
| `bluetooth_pairing`, `manual_pairing`, `pairing_replace_confirm`, `pairing_progress`, `pairing_result` | Bonding |
| `setup_progress`, `verify_connection` | Connection check and capability checklist |
| `pair_beds` | Combine two beds |
| `diagnostic`, `diagnostic_confirm`, `diagnostic_manual` | Browse an unsupported device |
| `reconfigure`, `migration_split`, `migration_keep`, `migration_confirm` | The [guided change](guided-setup-changes.md) |

### Configure

| Step | Purpose |
|---|---|
| `init`, `settings`, `left_settings`, `right_settings` | Settings |
| `change_app` | Points to Reconfigure |
| `pair_sides`, `revert_sides`, `unpair` | Side controls and splitting a pair |
| `remove_bond_side`, `remove_bond`, `remove_bond_progress`, `remove_bond_result` | Bond removal |
| `estimated_positions`, `left_estimated_positions`, `right_estimated_positions`, `estimate_top`, `estimate_bottom`, `estimate_raise`, `estimate_lower`, `estimate_lowering`, `estimate_lowered`, `estimate_flat`, `estimate_flat_lower`, `estimate_flat_confirm`, `estimate_review`, `estimate_retry`, `estimate_retry_again`, `estimate_cancel` | Measuring estimated positions |

## Converted

| Profile | Questions |
|---|---|
| `jiecang_app` | Layout (the chosen app's), light, transport (Advanced). Owns motor count and pulse delay; fixes angle sensing off. |
| `furnimove` | Handset ID; the handset table derives the motor count and massage, and angle sensing is off. |
| `okin_uuid`, `okimat`, `okin_dot` | Remote code (a saved code new setups no longer offer stays this entry's choice) and motor count. |
| `keeson:` ORE apps and INNOVA | The app's 2M, 3M or 4M screen, which is the motor count. |
| `bedsense` | Layout, or the layout from the Bluetooth name. |
| `leggett_lp_legacy` | Model code, protocol mode and the confirmed write and notification characteristics (free text). Its `normalize` cleans the code and UUIDs before they are checked. |

| `vibradorm_app@werkmeister` | Remote (control type). |
| `vibradorm_app@vmat` | VMAT remote; `normalize` derives its control type and features. |
| `vibradorm_app@caresse` | Restored setup; when restored, its control type, floor light, RGB, massage, light extension and floor default. `normalize` clears retained settings an answer no longer allows. |
| `vmatbasic` | Product; for CBI and XT-Box, the floor light level and timer (the exact ranges are checked on save). |
| `sleepys_elite_app` | Control box selector; the BOX25 selectors derive massage and position feedback. |
| `sleepys_box15`, `sleepys_box24` | Motor count. |
| `sleepys_box25` | Massage, and the packet dialect (Advanced). |

The other profiles declare only the generic fields they own, converted from the
former side tables.
