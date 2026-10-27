# v3 — P2 specification: research guards and the competition profile

**Version 1.2** (2026-10-25). v1.0 was reviewed independently by a Codex reviewer and a Claude reviewer (both GO WITH CHANGES); their points
are folded in and listed in §9. Parent plan: [v3-plan.md](v3-plan.md) §5–6; builds on [P1](v3-p1-spec.md). Branch `v3`.

## 1. Principles

- **Four files only.** Instruments and submissions are sections of `handoff.md`; research records are discoveries;
  tool state stays in `.ro/`. All new record IDs embed the slot (`I-A-01`, `X-A-001`), like every other ID.
- **The checker verifies that the evidence a guard asks for is recorded; it never judges science.**
- **No flood.** `Guards: light since YYYY-MM-DD` (written by init/reconfigure when guards are switched on): records dated
  before that day are exempt and reported as one INFO count. Guard output is one line per check id with the count and
  at most three example IDs.
- **Applicability in one place:** Shared state line `Not applicable: G3 — <reason>; G8 — <reason>`. A guard listed
  there raises nothing.
- **Severity and precedence:** guard rules emit WARN or INFO. `Guards: strict` raises the rules marked "strict → ERROR"
  in §4 to ERROR. The run flag `--strict` (P1) makes every WARN fail, guard or not, including "new since baseline".

## 2. Guards in v3 (renumbered from the plan, plan ids in brackets)

| Guard | Covers | `research` auto | `competition` auto |
|---|---|---|---|
| **G1 Instrument evidence** [G1, G13, F12] | provenance, coverage, agreement, resolution, external dynamics | on | on |
| **G3 Family saturation** [G3] | ties within measured resolution | off | on |
| **G5 Overrides and rejections** [G5] | registered rule overridden; rejections with evidence; reopen | on | on |
| **G6 Insights** [G6] | diagnoses that must end in action or evidence-based rejection | on | on |
| **GD Direction review** [G2, G4, G7, G9, G10] | one periodic record: gap, decomposition, core families, data audit, intake, rejected consistent gains, decisions | on | on |
| **G8 Phase clock** [G8] | milestones; only with `Phase clock` set | off | on |
| **G11 Selection** [G11] | final picks rationale | off | on |
| **G12 Effort** [G12] | coarse session-level share; **opt-in only** | off | off |
| **E1 External actions** | expected-before-result, identity, duplicates for any hard-to-reverse outward action | on | on |

`work` (alias `normal`) → G5, G6, GD and E1 (a work project's direction review uses only the parts that apply: gap to
the target metric, decisions; the rest may be `not applicable`). `Guard set: auto | <list>` overrides the defaults.
Every guard's section in `references/research-guards.md` shows one work, one research and one competition example.

## 3. Records

### 3.1 Instruments — `handoff.md` `## Instruments`

```markdown
### I-A-01 — <name>
- Provenance: independent | derived-from-targets | own-lineage | external-feedback
- Coverage: held-out | in-sample | external
- Measures: <metric and cohort>
- Agreement: <measured agreement with the final target, evidence ID> | unmeasured
- Resolution: ±<number> (<evidence ID>) | unmeasured
- Not for: <decision classes> | none
- Dynamics: <warm-up, drift, refresh>        (required for external-feedback)
```

Definitions: **independent** — not built from the training targets and not produced by our own models (expert labels,
held-out ground truth, external benchmark). **derived-from-targets** — built from the same source as the training
targets. **own-lineage** — produced by our own models or candidates (self-play panels, own teachers). **external-
feedback** — scores returned by an outside system (leaderboard, live rating). `Not for` uses the Decision class
vocabulary only; `derived-from-targets` must list `target-change`; `own-lineage` must list `target-change, model-change`.

### 3.2 Discovery fields (optional; required only where a rule says so)

| Field | Values |
|---|---|
| `Decision class` | `target-change`, `model-change`, `input-change`, `combination`, `operational`, `other` |
| `Instrument` | the instruments **that decided** the finding (not every one mentioned) |
| `Family` | stable name (also allowed on plan items) |
| `Result` | `<metric>=<value> on I-A-01 cohort <key>` (one or more) |
| `Override` | `<rule> said <verdict>; decided <verdict> because …; re-check: <trigger>; expires YYYY-MM-DD` |
| `Override resolved` | `<D-id>` (on a later discovery) |
| `Rejected on` | `I-A-01; fired: <evidence the change executed>` (for findings that do not hold) |
| `Consistency` | `k/n <units>` |
| `Kind` | `finding` (default), `insight`, `direction-review` |
| `Status`, `Due` | insights only (§3.3) |

### 3.3 Insights (G6) — discoveries with `Kind: insight`

Same ID space and format as discoveries, plus `Status: open | planned H-A-07 | rejected — <evidence D-id and reason>` and
`Due: YYYY-MM-DD HH:MM` (written by the author; at most `Date` + the `insight-due` threshold).

### 3.4 Direction review (GD) — discoveries with `Kind: direction-review`

Required parts (each may be `not applicable — <reason>`):
`Gap:` ours vs reference on an instrument (observed date) · `Decomposition:` lost score by component ·
`Core families:` each family strong approaches use — built standalone (D-id) / not built · `Data audit:` how the targets
were produced, source/site/annotator effects, shortcuts, train vs evaluation definitions (required in the **first**
review) · `Intake:` methods and score levels seen since the last review (not assets) · `Rejected consistent gains:` list
or none · `Decisions:` plan items created/removed or "no change — reason".
Shared state: `Last direction review: D-A-012 (YYYY-MM-DD)`.

### 3.5 External actions (E1) — `handoff.md` `## External actions`

```markdown
### X-A-001 — <external ref or short name>
- Kind: submission | deploy | release | publish | message | other
- Candidate: <name>, hash <artifact hash>
- Destination: <where it goes>
- Family: <family>            (optional)
- Expected: <expected outcome or range> (written YYYY-MM-DD HH:MM)
- Result: <observed outcome> (observed YYYY-MM-DD HH:MM) | pending
- Final: <final outcome> | pending        (e.g. a hidden score revealed later)
- Status: prepared | done | complete | error | withdrawn
- Retry of: X-A-000        (optional)
```

Work example: a production deploy with "error rate stays below 0.5 %" as Expected. Research example: a preprint posted
with "replicates effect size within CI" as Expected. Competition example (`references/competition.md`): a leaderboard
submission with an expected score range; the Kaggle adapter maps submission refs into `Candidate`/`Result`.
Shared state when final selection applies: `Final picks: X-A-012, X-A-019 (families: …; rationale: …)`.

## 4. Checker rules

| Id | Rule | light | strict |
|---|---|---|---|
| `guard.instrument.missing` | a dated-after-since discovery with Decision class ∉ {operational, other} and no `Instrument` | WARN | ERROR |
| `guard.instrument.circular` | no cited instrument is both eligible for the class (class ∉ `Not for`) **and** has measured `Agreement` | WARN | ERROR |
| `guard.instrument.insample` | a cited instrument has `Coverage: in-sample` | WARN | WARN |
| `guard.instrument.schema` | instrument violates §3.1 (missing `Not for` entries required by provenance; external-feedback without `Dynamics`/numeric `Resolution`) | WARN | ERROR |
| `guard.family.saturated` | the last N `Result`s (discoveries and submissions, ordered by date then file order) with the same metric, instrument and cohort lie within that instrument's numeric `Resolution`, **and** a queued plan item of that family has no `Saturation exit: instrument I-… \| structural: <what> (review <D-id>)` | WARN | ERROR |
| `guard.override.open` | each open override listed (open until `Override resolved`) | INFO | INFO |
| `guard.override.recheck` | override without `re-check` or past `expires` | WARN | ERROR |
| `guard.rejection.evidence` | `Finding: … does not hold` with Decision class ∉ {operational, other} and no `Rejected on` | WARN | ERROR |
| `guard.insight.overdue` | insight `open` past `Due`, or `planned H-…` whose item is neither in plan.md nor completed | WARN | ERROR |
| `guard.insight.rejection` | insight rejected on a discovery that itself fails `guard.instrument.circular` | WARN | WARN |
| `guard.direction.stale` | no direction review, or the last is older than the threshold | WARN | ERROR |
| `guard.direction.incomplete` | a direction review missing a required part (first review: missing `Data audit`) | WARN | ERROR |
| `guard.phase.milestone` | a milestone past its share of the window still pending (only with `Phase clock`) | WARN | WARN |
| `guard.selection.rationale` | two or more final picks from one family without `rationale:` | WARN | ERROR |
| `guard.effort.share` (opt-in) | session-level share of events tagged infra/process over the threshold; untagged events reported as "unknown" | INFO | WARN |
| `ext.expected` | `Expected` missing or written at/after the `Result` time | WARN | ERROR |
| `ext.duplicate` | two actions with the same hash and destination and no `Retry of` | WARN | ERROR |
| `guard.new-best.consistency` | a discovery that sets a new current best without `Consistency` or `not applicable` | INFO | INFO |

`Guard thresholds` grammar: `saturation=5, direction-review=7d, insight-due=48h, effort=55%, milestones=10/25/75` (any
subset; defaults as shown).

## 5. Documentation

- `references/research-guards.md`: each guard — why (failure mode, any domain), record, rule, applicability, example.
- `references/competition.md`: external feedback as an instrument, the external-actions ledger used for submissions, expected scores, per-column
  probes as an explicit setting, final selection rationale.
- `references/adapters/kaggle.md`: working Kaggle CLI/API commands and known quirks; quota re-read before decisions.
- `references/postmortem.md`: post-close procedure (top write-ups → fixed-template summaries → compare with records via
  independent investigators → independent fact-check → post-mortem with counterfactual ranks).
- SKILL.md: a short paragraph and a pointer per module.

## 6. Tests

1. Each rule: a minimal fixture fires it; a counter-fixture and a `Not applicable` declaration silence it.
2. Severity: `light` gives WARN/INFO only; `Guards: strict` turns exactly the "ERROR" cells into ERROR; `--strict` fails
   on any WARN.
3. Profiles: `work` → only G5/G6/GD/E1; `research` → none of G3/G8/G11 unless listed; G12 only when listed; the same
   guard fixtures pass in a work, a research and a competition wording.
4. Flood control: a v2-sized fixture (≥ 200 discoveries) switched to `Guards: light since <today>` → one INFO line; the
   whole guard output stays ≤ 1 line per check id.
5. **Replays from anonymised real-record excerpts** (structure and numbers only; fixtures and tests are named after
   failure modes, never after projects — no project, dataset or model names anywhere outside docs/plans/):
   - `replay-derived-instruments`: mixed panel (derived instruments plus one unmeasured eligible instrument) deciding a
     target change → `guard.instrument.circular`; external-score ties from the external-actions ledger plus a queued
     same-family item → `guard.family.saturated`; an override without re-check → `guard.override.recheck`; a
     strategy insight left open → `guard.insight.overdue`; a direction review with an unbuilt core family and no
     intake → `guard.direction.incomplete`; two picks from one family → `guard.selection.rationale`.
   - `replay-own-lineage-panel`: own-lineage panel deciding a model change → `guard.instrument.circular`; rejections
     without evidence the change fired → `guard.rejection.evidence`.
   - `replay-in-sample-validation`: in-sample validation instrument → `guard.instrument.insample`.
   - Provenance rule (v1.2, after re-review): replays are built from anonymised **real records** wherever a past
     project kept records in this skill's format — derived instruments, saturation, overrides, insights, the
     direction review (core families, intake read for assets) and final selection. The own-lineage-panel and
     in-sample-validation cases come from projects that kept no such records; they are **post-mortem-derived**
     reconstructions and say so in their fixture README.
   - Counter-replays (zero guard WARNs): changed cohorts (no false saturation); same-family picks with a rationale; both
     workflows; a non-ML project with no labels and no clock where every guard is declared not applicable.
6. Burden check: the replay fixtures report the number of fields added per discovery and the warning volume; both are
   recorded in the test output.

Known false negative (documented, not tested): an override that nobody declares cannot be detected.

## 7. Out of scope

Hooks and the `ro` CLI (P3); per-preset examples, READMEs, release (P4).

## 8. Settings added

`Guard set: auto | <list of G1, G3, G5, G6, GD, G8, G11, G12, E1>`; `Guard thresholds: <key=value list>`;
`Guards` gains the `since YYYY-MM-DD` suffix; P1's stored-only `Guards`, `Phase clock`, `Competition` become active.

## 9. Review changes from v1.0

- Codex reviewer: canonical decision taxonomy and decision-bearing evidence; comparable measurement keys for saturation; overrides
  and insights integrated with discoveries (no separate lifecycle); one direction-review record replacing several
  Shared-state checks and covering rejected consistent gains; G12 opt-in and honest about unknowns; selection rationale
  instead of a blanket failure; explicit severity precedence; one applicability declaration; timestamps and hashes for
  submissions; replays from real excerpts plus counter-replays; measure warning volume and recording burden.
- Claude reviewer: `Not for` from the class vocabulary and circularity requiring a measured eligible instrument; `since` date and
  output cap against floods; rejection evidence only for non-operational negatives; numeric resolution, `Family` on plan
  items, `Saturation exit`, ordering, submissions read by G3; `Coverage` for in-sample validation; trimmed `research` set;
  exact `Due`/`Override resolved`/thresholds grammar; slot-prefixed `I-`/`S-` ids; expanded replay fixtures; the
  undeclared-override false negative stated.
