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
| `seed` | Fills setup's defaults from the bed's advertisement before the first form, such as the ISleep product and room or the Motion Bed name. It never replaces a chosen value, and Configure does not run it. |

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
fields the profile asks itself (motor count, variant), so neither the final
settings nor Configure asks them twice. A question with whole-number choices accepts the text a select
returns.

## Setup and Configure

- Setup asks every declared question. A family step (see
  [Guided setup changes](guided-setup-changes.md)) chooses the app first, then
  hands the staged route to `profile_questions`.
- The app question (`select_app`) and the brand list (`select_family`) offer
  rows of the bed-type list, and a row picked there stages its route: an app's
  own row answers the family question, so it is not asked again, and a family
  row, which names its apps, leads to the question. The
  brand list shows each brand group's family rows, or the group's own rows
  when it has no family question; protocol rows stay in the app question's
  full list.
- The final settings come after the app's questions, so every route the
  question can choose reaches the generic fields its profile does not set
  there: motor count when it offers several, massage when its controls depend
  on it, and angle sensing when it reports positions. A family step that sets
  one itself, such as an L&P app's motor count, settles it.
  `tests/test_family_setup_fields.py` runs every answer of every family row
  and of every route a journey can start on, and fails when such a field
  cannot be set. It also saves each answer's route as an entry and fails
  when that entry cannot reach another route of the question: through
  Reconfigure for a guided family, or Configure's list outside it.
- Configure asks the questions that are not the managed family's route keys:
  the app, layout and route change only through the guided change. An entry
  that Configure switches into a managed family from another bed type answers
  that family's route questions there, since it has no guided change yet.
- A two-address pair's shared Configure form asks no declared questions, since
  each receiver may run another profile. Each receiver's own step
  (`left_settings`, `right_settings`) asks its profile's questions instead and
  saves the answers to that receiver only.
- `tests/test_setup_questions.py` checks that each declared question has its
  `strings.json` label in `profile_questions` (or its Advanced section) and in
  Configure, so a field cannot ship unlabelled.

## The new-bed journey

A new bed is set up in one order (#676 direction A):

1. **The app.** A discovered bed's first question is its detected family's:
   the family step itself, with "Another app or remote" before its Keep, or,
   for a route without one, `bluetooth_confirm`, which lists that bed type's
   own rows. A family that settles the route from the receiver without asking
   is confirmed on `bluetooth_confirm` too, before its own questions. "Another
   app or remote" opens `select_app` for the same device. Every other route
   starts with `select_app`, and a typed address (`manual_entry`) follows it.
2. **The app's questions.** The family step and the profile's declared
   questions, exactly as Reconfigure asks them.
3. **The final settings** (`finish_settings`), drawn for the one route the
   journey staged: the name, the Bluetooth adapter and disconnect after each
   command; the generic fields the profile neither sets nor asks, and that no
   family step set itself (`_journey_set`); a bed type's own settings (Octo PIN
   and motor count, CB24 side); the route's labelled routes, when it has
   several, in a collapsed Advanced section; and the pulse count and delay and
   the idle timeout, collapsed under "Advanced connection and timing". A
   client that submits a field the form does not show cannot set it.
4. Pairing, then the connection check.

Defaults are the staged route's own: a family answer that changed the route
gave it Configure's defaults, and the final settings start from them.

**Disable angle sensing** shows only where a route of the staged bed type
reports positions, and starts off (positions are read): every such route's own
default. Turning it on is therefore always the user's change. A route without
position reports saves its own default. The controllers of some of those routes
can read positions, such as Octo, SBI and the Reverie models without position
reports, but the integration does not read them there, so an untouched setup
leaves them unread.

Configure conditions owned generic fields, and the L&P app field, on its route
field. It redraws after a bed-type change, and after a route change that alters
the motor count choices or position feedback: those change defaults and the
route list, which a field condition cannot.

## Dedicated steps

A dedicated step remains only for what data cannot express, with its reason
recorded here as each family converts. `tests/test_setup_questions.py` checks
this section and [Shared steps](#shared-steps) against the setup and Configure
flows, so a new step cannot appear unrecorded and a removed one cannot linger.

| Step | Why it is not data |
|---|---|
| Family steps (`jiecang_family`, `okin_family`, `keeson_family`, `solace_family`, `leggett_family`, `sleepys_family`, `malouf_family`, `customatic_family`, `jordans_family`, `starcode_family`, `remacro_family`, `logicdata_family`, `reverie_family`, `richmat_family`, `sleep_number_family`, `jensen_family`, `limoss_family`, `vibradorm`) | They choose the profile itself, and Keep, before any profile's questions exist |
| `keeson_app`, `keeson_restonic`, `keeson_route` | Each picks the Keeson variant, which is the profile, not one of its answers |
| `solace_woosa` | A note before choosing Woosa Sleep; it asks nothing |
| `jiecang_legacy` | Part of the Jiecang journey: a remote route chosen in place of an app needs the motor count and cadence the app had fixed |
| `verify_octo_pin` | Authentication: setup finishes only after the bed accepts the PIN, or the user corrects it |
| `starcode_app` | Probes the transport over a live connection when the Bluetooth name cannot settle it |
| `starcode_m5x5`, `starcode_m1x12` | Their lift groups name other config entries, which a declaration's checks cannot see |
| `cluster033_app` | A custom product picks its keys in multi-select lists, which a question cannot ask yet |
| `fsm_relax` | The eight memory names are one multi-value text field, which a question cannot ask yet |

## Shared steps

These steps serve every bed type or route, so no profile owns them.

| Step | Purpose |
|---|---|
| `user`, `scan`, `scan_result`, `manual`, `select_app`, `select_family`, `bluetooth`, `bluetooth_disambiguate` | Find the bed and pick its app or bed type: `select_app` lists the bed-type list's rows, and its last answer opens the brand list (`select_family`), whose rows are the family rows and the brands without one |
| `bluetooth_confirm` | A discovered bed's app question, from its bed type's own rows, when no family question asks it |
| `manual_entry` | The address of a bed that is not in range |
| `finish_settings` | The [final settings](#the-new-bed-journey) |
| `profile_questions` | The declared questions |
| `bluetooth_pairing`, `manual_pairing`, `pairing_replace_confirm`, `pairing_progress`, `pairing_result` | Bonding |
| `setup_progress`, `verify_connection` | Connection check and capability checklist |
| `pair_beds` | Combine two beds |
| `diagnostic`, `diagnostic_confirm`, `diagnostic_manual` | Browse an unsupported device |
| `reconfigure`, `migration_split`, `migration_keep`, `migration_confirm` | The [guided change](guided-setup-changes.md) |

### Configure

| Step | Purpose |
|---|---|
| `init`, `settings`, `left_settings`, `right_settings` | Settings; each receiver step also asks that receiver's declared questions |
| `change_app` | Points to Reconfigure |
| `pair_sides`, `revert_sides`, `unpair` | Side controls and splitting a pair |
| `remove_bond_side`, `remove_bond`, `remove_bond_progress`, `remove_bond_result` | Bond removal |
| `estimated_positions`, `left_estimated_positions`, `right_estimated_positions`, `estimate_top`, `estimate_bottom`, `estimate_raise`, `estimate_lower`, `estimate_lowering`, `estimate_lowered`, `estimate_flat`, `estimate_flat_lower`, `estimate_flat_confirm`, `estimate_review`, `estimate_retry`, `estimate_retry_again`, `estimate_cancel` | Measuring estimated positions |

## Converted

| Profile | Questions |
|---|---|
| `jiecang_app` | Layout (the chosen app's), light, transport (Advanced). Owns motor count and pulse delay; fixes angle sensing off. |
| `furnimove` | Handset ID; the handset table derives the motor count and massage, and angle sensing is off. |
| `okin_uuid`, `okimat`, `okin_dot` | Remote code (a saved code new setups no longer offer stays this entry's choice), motor count and massage motors; `okin_uuid` and `okimat` also angle sensing. The family row's form is drawn for FurniMove, which sets massage and angle sensing itself. |
| `keeson:` ORE apps and INNOVA | The app's 2M, 3M or 4M screen, which is the motor count. |
| `keeson:ergomotion` | Angle sensing: the one older Keeson remote route that reports positions. |
| `bedsense` | Layout, or the layout from the Bluetooth name. |
| `leggett_lp_legacy` | Model code, protocol mode and the confirmed write and notification characteristics (free text). Its `normalize` cleans the code and UUIDs before they are checked. |
| `vibradorm_app@werkmeister` | Remote (control type). |
| `vibradorm_app@vmat` | VMAT remote; `normalize` derives its control type and features. |
| `vibradorm_app@caresse` | Restored setup; when restored, its control type, floor light, RGB, massage, light extension and floor default. `normalize` clears retained settings an answer no longer allows. |
| `vmatbasic` | Product; for CBI and XT-Box, the floor light level and timer (the exact ranges are checked on save). |
| `sleepys_elite_app` | Control box selector; the BOX25 selectors derive massage and position feedback. |
| `sleepys_box15`, `sleepys_box24` | Motor count. |
| `sleepys_box25` | Motor count, massage, angle sensing, and the packet dialect (Advanced). The family row's form is drawn for the app, which sets the motors and angle sensing itself. |
| `gmmotor` | Catalog product, suggested from the raw Bluetooth name, and the app side the product must offer; angle sensing is off. |
| `isleep` | Product, room ID and actuator descriptor, seeded from the advertisement; the product's axes derive the motor count. A single-address pair keeps a product with separate side controls. |
| `doublesleep` | Saved app model, seeded from the platform name, and the BLE driver. |
| `sleeptracker` | Foundation, app layout, unit number, snapshot side, restricted session and processor type; a lumbar layout derives the third motor. |
| `motion_bed` | Exact Bluetooth name, seeded from the advertisement; restored profile and retained preset and movement layouts. `normalize` stores Auto as no retained layout. |
| `malouf_app@malouf`, `malouf_app@lucid` | Model (the chosen app's picker, plus a saved model it no longer lists), primary/secondary role and transport (Advanced). Fixes angle sensing off; `normalize` drops a model the picker did not offer. |
| `malouf_app` | The app too, with every app's models, for an entry switched in from another bed type with Configure's bed-type list; the app and model are checked together on save. |
| `malouf_new_okin`, `malouf_legacy_okin` | Motor count, layout and memory positions. |
| `logicdata_app@phone`, `logicdata_app@tablet` | Command family; the layout for P1 only, since P2 is the middle layout its `normalize` sets; light; transport (Advanced). Owns motor count and pulse delay; fixes angle sensing off. |
| `logicdata_app@sleep_smart` | Command family, the two-motor standard or split-series layout, light, transport (Advanced). |
| `logicdata_app` | The app too, for an entry switched in from another bed type with Configure's bed-type list; its combinations are checked on save. |
| `reverie`, `reverie_nightstand` | The model the app shows (the protocol variant), and angle sensing for a model whose app reads positions. The model is asked on the same form, so the question follows it; a model without position reports derives angle sensing disabled. |
| `richmat` | The RMControl product, or None for the remote controls; the RMControl side when a product is chosen; otherwise the Richmat remote code; the packet dialect (Advanced). An RMControl product with a Prefix55 or PrefixAA dialect is refused on save. |
| `richmat_revive`, `richmat_best_mattress`, `richmat_blvd_home`, `richmat_harmony`, `richmat_idealbed` | The app's model (the protocol variant), or Auto from the raw Bluetooth name; a name the app cannot resolve is refused on save. |
| `sleep_number` | The side this Fuzion entry controls (the protocol variant), and angle sensing. |
| `sleep_number_mcr` | Angle sensing only, since one entry exposes both sides. |
| `logicdata` | SimplicityFrame's motor count: the family row's form is drawn for the apps, whose layout sets it. |
| `vibradorm` | The legacy setup's motor count, massage motors and angle sensing: a form drawn for a detected app or V-MAT Basic sets these itself. |
| `jensen` | The JMC400 box's PIN (free text; empty uses the default), motor count, massage motors and angle sensing: the family row's form is drawn for Svane, which sets these itself. |
| `svane:jensen_linon` | Motor count. |
| `limoss_remote` | Bed or chair, light, massage, the four reversals and the optional artwork theme; the connected device supplies its key layout. |

The other profiles declare only the generic fields they own, converted from the
former side tables.
