# Guided setup changes

Issue #676 unifies setup around one question: which app or remote controls
this bed. An existing entry moves to another app or layout only through a
staged, explained and confirmed change. This note records the shared
transaction and the rules every family journey follows. It contains no
protocol values.

## The transaction

`profile_migration.py` holds the shared parts; each family supplies only its
own questions and checks.

1. **Snapshot.** Reconfigure copies the saved data and options
   (`MigrationSnapshot`). Every later step works on a staged copy.
2. **Choose.** The family's step asks for the app, then the layout or remote
   the app shows. Choosing a different app clears the previous app's profile
   metadata; keeping the same app keeps it.
3. **Verify.** A family with exact endpoint or bond requirements
   (`ManagedFamily.requires_check`) must pass a connection check. The old
   runtime's transport is reserved under its normal locks for the check. A
   link that cannot be observed closed fails the check and stays owned until
   it closes, so no second connection overlaps it.
4. **Review.** `async_control_changes` compares the entity set of the running
   route with the entity set the staged route declares offline, and names the
   automations and scripts that use a removed entity. Unique IDs are
   address-based, so a kept control keeps its entity ID and history. Listing
   the staged controls builds entities without saving the route and ignores
   every registry write meanwhile.
5. **Confirm.** Saving happens only against an unchanged snapshot.

Keep, cancel, a failed check or a concurrent edit leave the saved entry
unchanged and usable. An answer that resolves to the saved route (a label
change) aborts without a check or a save.

Families reuse the transaction, never another family's protocol checks.
Vibradorm's role checks and native bond rules stay Vibradorm's.

## Entry points

- **Reconfigure** opens the wizard for a family registered in
  `MANAGED_FAMILIES`.
- **Configure** shows one generic **Change app or layout** item for those
  families. Home Assistant cannot hand an options flow to a config flow, so
  the item points to Reconfigure.
- **Repairs** opens the wizard as its next flow, or Configure's settings form
  with the app selected for an app that needs its own settings.

## Repairs and Keep

A review completes only after a saved change of bed type or variant, or an
explicit Keep. Acknowledging instructions or closing a handed-off flow leaves
it pending. Keep is stored with the route signature and the apps shown
(`CONF_PROFILE_REVIEW_KEPT`). The review returns for that route only when a
later release offers it an app the user was not shown. In a fresh setup, Keep
saves the detected route; in Configure and Repairs it leaves the entry
untouched.

## Paired beds

An app belongs to one physical bed, so the wizard splits a pair first.
`standalone_config_after_split` restores each side's original configuration
except the connection preferences in `SPLIT_RETAINED_KEYS` (adapter, idle
disconnect, disconnect after each command), which keep the value the side used
while combined. Bed type, app profile and side settings revert to the
originals. An open review, or an earlier Keep, carries over to each standalone
bed.

## Connection check is not physical validation

A passed check proves only that the chosen endpoints exist and any required
bond holds. It does not prove the physical layout, preset meaning or movement.
The confirm step says so. Physical validation by affected users after a beta or
release is recorded per family below, separately from the code change.

| Family | Guided change | Connection check | Physical validation |
|--------|---------------|------------------|---------------------|
| Vibradorm, VMAT, Caresse Diamant, Werkmeister, V-MAT Basic | Yes | Endpoint roles, VMAT native bond | Pending user reports after release |
| Customatic Clarity, Jerome's C, Remedy | Yes | The one command characteristic | Pending user reports after release |
| Customatic Z-Series, Jordan's Serenity and Tranquil | Yes | The command and notification characteristics | Pending user reports after release |
| Malouf Base and Lucid Base apps, Nordic UART and FFE5 receivers | Yes | The app's transport, chosen as the runtime chooses it; the receiver routes need none, since they correct each other from the services | Pending user reports after release |
| Sleepy's Elite app, BOX15, BOX24, BOX25 | Yes | The control box's setup and response characteristics; each receiver route's command characteristic | Pending user reports after release |
