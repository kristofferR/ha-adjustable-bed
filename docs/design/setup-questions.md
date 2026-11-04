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
| `owns` | Each generic field the profile owns (`GENERIC_FIELDS`): a fixed value, applied when setup or Configure saves, or `SET_BY_PROFILE` when the profile derives it. No form shows an owned field. |
| `questions` | The `Question`s to ask, in order. |
| `validate` | Errors by field for the staged setup with the answers applied. |
| `title` | The name the step shows for the staged route. |

A `Question` stores its answer under `key`. Its `choices` are fixed labels or a
function of the staged setup, such as the layouts the chosen app supports;
without choices it is yes or no. Its `default` is a value, a function of the
staged setup, or `REQUIRED`. A staged answer the choices no longer offer falls
back to the default. An `advanced` question sits in a collapsed Advanced
section in setup.

Declarations are keyed like a [profile id](profile-id.md): `bed_type`,
`bed_type:variant`, `bed_type@app` or `bed_type:variant@app`, and the most
specific key that matches a route wins, so a variant entry replaces its bed
type's entry. `app_profiles.hidden_generic_fields` reads `owns`.

## Setup and Configure

- Setup asks every declared question. A family step (see
  [Guided setup changes](guided-setup-changes.md)) chooses the app first, then
  hands the staged route to `profile_questions`.
- Configure asks the questions that are not the managed family's route keys:
  the app, layout and route change only through the guided change.
- `tests/test_setup_questions.py` checks that each declared question has its
  `strings.json` label in the generic step (or its Advanced section) and in
  Configure, so a field cannot ship unlabelled.

## Dedicated steps

A dedicated step remains only for what data cannot express, with its reason
recorded here as each family converts:

| Step | Why it is not data |
|---|---|
| Family steps (`jiecang_family`, `okin_family`, `keeson_family`, `solace_family`, `leggett_family`, `vibradorm`) | They choose the profile itself, and Keep, before any profile's questions exist |

## Converted

| Profile | Questions |
|---|---|
| `jiecang_app` | Layout (the chosen app's), light, transport (Advanced). Owns motor count and pulse delay; fixes angle sensing off. |

The other profiles declare only the generic fields they own, converted from the
former side tables; their own steps follow in later changes.
