# Cluster 011 convergence ledger

Issue: #551

Scope: the nine accepted Okin CST package reports in Phase 4 cluster 011

Status: implementation complete; physical hardware validation deferred

## Frozen evidence verification

Before comparison with integration code, each report was verified with its own
`REPORT.SHA256`; its manifest and `analysis.json` hashes were then matched to the
accepted reconciliation. The reconciliation and handoff manifests also verify.

| Package | `REPORT.SHA256` SHA-256 | `analysis.json` SHA-256 |
|---|---|---|
| `com.okin.bedding.rizeSanctuary` | `32cff0b9b97ce3b47405303e0dc608239c6cebb23484154fbe076e6b765fb88a` | `fe46db0e1475bdfe1bdf5adc5ecef90fb2e595a9e622efc9d3395c6b83fec627` |
| `com.okin.bedding.rizeResident` | `f7c7e6427be80318cf8e90dde842584013f2e578c87d77316c6da830ec698ef2` | `fa5c6e3a43e4891d21448408f87e5d25638e017da07de35efe5a7d70a1f4890a` |
| `com.okin.bedding.rizeaviada` | `042dc4b60732fe605b5863d3a31f0821605a16cf67942f1c81d9a6bdd6a3b31f` | `c1ac7fc8c10a27badb6239d6df4221acd82255a6764e6087622e602794f4fb15` |
| `com.okin.bedding.rizebob` | `8e8dd2296fa4c356b25271338b42da07fe2fe5e2383b7de9455e1acb66ab1a2e` | `cbc0cdbe81c6957dc625279b56cdb523f12994d1c85a602183febd598e854dfb` |
| `com.okin.bedding.rizecontempo` | `7cf48eac7a77bdebaa36a10a521a7a74a94fe67f7530587745b4d20dd99c1719` | `fe93b4453c75aa0a89bcb27c8648dd77ab25ed325d19370004caff0b63cabeb7` |
| `com.okin.bedding.rizeiicarefree` | `08fce9beb1a46fe10aea39fbf9acbdb752de2a13a416786a309ebfd9973f83c3` | `be6299807e4ea166e824d8be26c848aa88f16ee0bb49cebcc4237a1276847075` |
| `com.okin.bedding.rizeiiclarity` | `ab6d080d92ae972bc8367640f1a882ce8f7331af798caba883caf88e0b39131a` | `0c276a48fa2a9e2becf2963aa6809ad7d57d41054b2dfc3950a80775f19ddf5e` |
| `com.okin.bedding.rizemf900` | `9c8a3f0f0b705f2a2749b702a09a4dba1511cf4d6bf24c8d3227568f9d906319` | `0d1b302228c836cc8b305ab2c7d347a7d31fc7b131881a9d6c91bdaddc5fc147` |
| `com.okin.bedding.support` | `9057df5cc03bb6391d3439897925bb2553355de342747bb492f7b0d8724bf16c` | `4839d4d5255bba3f4600050b8b656b4a2d4d1a87472948a2dc883b27654243f6` |

Reconciliation `REPORT.SHA256`:
`85f619650542f8ec48f2b71851fe8466b8d9643f04b39e4fde5096c4bc54c6f4`.
Handoff manifest: `fc9744787b3eea3ef3fe4afad9aed32b9ef82b9dea85704362e65ea1bd7d0985`.

## Exact 99-area disposition

The accepted reconciliation contains eleven areas for each package. Every one
is represented below. `I` means IMPLEMENTED in this convergence change, `A`
means ALREADY IMPLEMENTED before it, and `X` means EXCLUDED with the reason in
the exclusion table.

| Package | Artifact | Discovery | GATT | Session | Packets | Actions | Timing | Parser | Model/auth | Reachability | Lifecycle |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Sanctuary | X | A | A | A | I | I | A | A | I | X | X |
| Resident | X | A | A | A | I | I | A | A | I | X | X |
| Aviada | X | A | A | A | A | A | A | A | I | X | X |
| Bob | X | A | A | A | I | I | A | A | I | X | X |
| Contempo | X | A | A | A | A | A | A | A | I | X | X |
| Carefree | X | A | A | A | A | I | A | A | I | X | X |
| Clarity II | X | A | A | A | A | I | A | A | I | X | X |
| MF900 | X | A | A | A | A | A | A | A | A | X | X |
| Support | X | A | A | A | I | I | A | A | I | X | X |

Totals: **18 IMPLEMENTED, 54 ALREADY IMPLEMENTED, 27 EXCLUDED**.

## Implemented

- Added nine explicit CST product profiles. `Auto` remains the established
  MF900 profile because the shared service UUID and `OKIN-*` name do not carry a
  product discriminator.
- Constrained motor entities to the accepted two-axis or three-axis product
  layout and remove stale lumbar entities when a two-axis profile is selected.
- Constrained lounge, incline, memory, light, and massage entities to each
  shipped app's reachable capability surface.
- Added Resident's fourth `M` recall/program pair and timer-step frame.
- Added Sanctuary and Bob's full-body massage start.
- Added zoned head/foot intensity controls. The Sanctuary/Resident primary-only,
  Bob dual-field, and Support asymmetric decrease frames remain distinct.
- Added profile diagnostics and configuration validation, including two- versus
  three-motor constraints.
- Added frozen artifact-derived vectors for the new field combinations and a
  complete nine-profile capability matrix.

## Already implemented

- Discovery already recognizes the common Okin service and name family while
  treating the shared UUID as ambiguous with other Okin protocols.
- The service, write, notify, and CCCD roles match the accepted cluster reports.
- The CST builder already preserves the 14-byte
  `0c 02 || primary_be32 || secondary_be32 || 00000000` format without checksum,
  sequence, encryption, or fragmentation.
- The app's 100 ms refresh cadence, bounded 500 ms one-shot actions, and two
  all-zero releases at +100/+200 ms were already present. Motor duration remains
  a user setting, as it was before convergence.
- Notifications are subscribed and forwarded to diagnostics without inventing
  position data. Every report found no position/angle parser.
- The integration already serializes commands, sends STOP with a fresh cancel
  event, and performs cleanup in `finally`, which is safer than the app lifecycle.
- MF900 packet routing and its full capability set were already implemented by
  the accepted-early partial PR.
- No application PIN, handshake, model query, remote code, capability bitmask,
  side addressing, or firmware selector was added because none exists in the
  accepted reachable paths. Existing OS-level bond handling is retained from
  receiver hardware evidence and is not an application protocol claim.

## Excluded

| Finding | Packages | Reason |
|---|---|---|
| Artifact delivery and archive identity | All | Provenance is frozen evidence, not runtime integration behavior. Identities are retained above and in protocol documentation. |
| Dead/unused protocol APIs, alarm builders, hidden motors, unreachable voice dispatchers, and dormant branches | All | The accepted reachability ledger marks these outside the shipped control surface. Exposing them would guess hardware semantics. |
| Android callback races, mutable-characteristic handoff, sticky callbacks, leaked repeat runnables, delayed STOP accumulation, and cross-device retargeting | All | These are app defects or platform implementation details. Home Assistant deliberately keeps serialized, target-stable commands with guaranteed cleanup. |
| Byte-10 save acknowledgement heuristic | All | It has no proven preset identity or durable state meaning. Raw notifications remain available for diagnostics. |
| Support's broadcast to every app-connected bed | Support | A Home Assistant config entry owns one explicit BLE target. Broadcasting a command to unrelated entries would be unsafe. |
| Support voice `Stop` massage-stop hold before global STOP | Support | The integration's stop action sends the proven all-zero global release immediately; delaying emergency stop to reproduce voice choreography would reduce safety. |
| Resident light commands | Resident | Present only in dead library surface and absent from the shipped UI. |
| Carefree massage, lounge, incline, lumbar, alarm, and extra-memory APIs | Carefree | Present only in dormant library surface, not reachable in the accepted app. |
| App-specific speech phrases and recognition aliases | All | Home Assistant exposes semantic entities and does not embed the apps' speech recognizers. The reachable BLE actions themselves are implemented. |
| Automatic product-profile inference | All | No report found a model, SKU, Device Information, manufacturer-data, service-data, remote-code, or capability selector that distinguishes the nine layouts. Manual profile selection is exact; automatic inference would be a guess. |

## Closure readiness

There is no remaining static-analysis blocker or unimplemented actionable
cluster finding. Hardware behavior is explicitly unverified, as allowed by the
Phase 4 completion policy. After this change is reviewed and merged, #551 can be
closed once the queue and discovery ledgers are synchronized.
