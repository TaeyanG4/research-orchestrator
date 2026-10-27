# Research guards

Read this when recording measured evidence or resolving a guard finding with `Guards: light` or `strict`. These guards check whether a decision's evidence was recorded, not its quality. They apply to all profiles and workflows. Projects without measurements can still use override, insight, direction, and external-action records.

## Settings, applicability, and output

`Guard set: auto` selects G5, G6, GD, E1 for `work`; G1, G5, G6, GD, E1 for `research`; and G1, G3, G5, G6, GD, G8, G11, E1 for `competition`. An explicit comma-separated list replaces these defaults. G12 is enabled only by an explicit list. `Guards: off` disables them all. `Phase clock` must also be set for G8.

Init/reconfigure writes `Guards: light since YYYY-MM-DD` or `strict since YYYY-MM-DD` when switching guards on. Records before that date are exempt from guard findings, including guard record schema and reference checks, with one INFO count; historical reviews still establish freshness, and historical actions still establish artifact identities. Each check produces at most one output line, with its count and at most three example IDs. Thresholds are any subset of `Guard thresholds: saturation=5, direction-review=7d, insight-due=48h, effort=55%, milestones=10/25/75`; omitted keys use these defaults.

Declare applicability once in `handoff.md` Shared state: `Not applicable: G3 — no comparable numerical series; G8 — no fixed window`. Each listed guard raises nothing. Name only enabled guards: an unused exemption produces INFO so the project does not accumulate misleading policy. Use a reason, and reconsider it when the project changes. Individual direction-review parts can say `not applicable — <reason>`; a current-best discovery may use `Consistency: not applicable — <reason>`.

Light guards emit WARN or INFO. Strict guards turn only the checks identified by each guard into ERROR. The core's checker section defines the separate command flag `--strict` and baseline behavior.

For active, applicable guard records, malformed or duplicate IDs and invalid references are structural ERRORs in either mode. Completeness findings follow the guard's severity; disabling a guard or declaring it inapplicable also disables its schema and reference checks. Cited discoveries and instruments must exist, including every instrument in `Instrument`, measurement `Result`, `Rejected on`, and `Saturation exit`. One valid citation cannot conceal a missing one. Historical evidence can still be cited.

## G1 — Instrument evidence

**Why:** a measurement may agree with its own construction while missing the final target. Its coverage and resolution can also make an apparent result misleading.

Register instruments in `handoff.md` under `## Instruments`:

```text
### I-A-01 — independent review set
- Provenance: independent
- Coverage: held-out
- Measures: error rate on cohort current
- Agreement: rank agreement 0.82 with final target (D-A-001)
- Resolution: ±0.01 (D-A-001)
- Not for: none
```

`Provenance` describes where the measurement comes from: `independent` (separate from the outcome definitions and approaches being assessed), `derived-from-targets` (built from those outcome definitions), `own-lineage` (produced by the approaches being assessed), or `external-feedback` (observed outside the project). Derived evidence puts `outcome-definition-change` in `Not for`; own-lineage evidence puts both `outcome-definition-change, method-change` there. These exclusions prevent a method from validating its own assumptions. `Not for` accepts decision classes or `none`, including the equivalent legacy names below.

`Coverage` is `held-out`, `in-sample`, `external`, or `complete`. Use `complete` for an exhaustive or analytic measurement of its stated scope, such as every inventory entry or a closed-form calculation. With `complete`, `Agreement: unmeasured` is eligible without inventing agreement or precision estimates; provenance exclusions still apply, and completeness does not establish population generalization. `Resolution` may also be `unmeasured`; external feedback still requires numeric resolution and `Dynamics: <warm-up, drift, refresh>`.

On a discovery, use `Decision class: outcome-definition-change`, `method-change`, `data-change`, `combined`, `operational`, or `other`. The legacy names `target-change`, `model-change`, `input-change`, and `combination` remain equivalent to the first four for compatibility with v2 projects; use neutral names in new records. Spelling and case are exact: unknown classes are structural ERRORs while guards are active and applicable and cannot establish eligible evidence. `Instrument` lists only the instruments that decided the finding; an `other` observation needs no invented instrument. `Result: error=0.04 on I-A-01 cohort current` supplies a comparable measurement. `Family` is a stable approach name. Record `Consistency: 4/5 sites` when declaring a new current best, or a reason it does not apply.

Before trusting a gain selected by search, compare it with a placebo or negative control using the same search budget and instrument. Add `Control: <artifact>; selection gain <number>` to a `method-change`, `data-change`, or `combined` discovery, and explain in Evidence whether the candidate beats that noise floor. The optional field makes selection effects inspectable without claiming the checker can judge the experiment. If a control is inappropriate, use `Control: not applicable — <reason>; alternative: <uncertainty check>`.

`guard.control.missing` is INFO in light mode and WARN in strict mode when such a decision lacks the control record or has no numeric selection gain. The applicability and activation-date rules also apply to this check.

- **Work control:** `Control: artifacts/shuffled-routing.csv; selection gain 0.003` compares a routing-policy search with shuffled tickets.
- **Research control:** `Control: artifacts/negative-control.json; selection gain 0.002` reruns the extraction-policy search on permuted outcomes.
- **Competition control:** `Control: artifacts/placebo-search.json; selection gain 0.001` repeats candidate selection on an unchanged predictor.

**Rules:** `guard.instrument.missing` warns about a non-operational decision without an instrument; `guard.instrument.circular` requires at least one cited, eligible instrument with measured agreement or complete coverage; `guard.instrument.schema` checks the instrument record. All three become ERROR in strict mode. `guard.instrument.insample` stays WARN when any deciding instrument has in-sample coverage. `guard.new-best.consistency` stays INFO for a new best without consistency evidence. G1 is inapplicable when no decision depends on measured evidence.

- **Work:** choose a parser change using an independently reviewed archive, with error agreement checked against incident outcomes.
- **Research:** change a coding policy using a held-out expert audit; a panel derived from existing targets cannot decide a target change.
- **Competition:** treat external scores as an instrument with measured resolution and recorded refresh dynamics; an own-lineage panel cannot decide a core approach change alone.

## G3 — Family saturation

**Why:** repeated ties can consume the remaining window while a different family remains unexplored.

Use `Family` on discoveries, queued plan items, and relevant external actions. Record results with the same metric, instrument ID, and cohort key only when they are comparable. The last N results are ordered by date, then file order; N defaults to five. External-action results participate in the same series. A changed cohort starts a different series.

**Rule:** `guard.family.saturated` warns when those results span no more than the instrument's numeric resolution and the family still has a queued item without `Saturation exit: instrument I-A-02` or `Saturation exit: structural: <what changes> (review D-A-002)`. It becomes ERROR in strict mode. Declare G3 inapplicable without comparable numerical series; an unmeasured resolution cannot establish a tie.

An instrument exit must name an existing instrument different from the saturated instruments. A structural exit needs a non-empty change and an existing discovery with `Kind: direction-review`.

- **Work:** five cache variants tie within timing resolution; queue a new storage design or name the new instrument that can separate them.
- **Research:** five extraction variants have indistinguishable agreement; a changed population is a new cohort, not evidence of saturation on the old one.
- **Competition:** five external results tie; further work in that family needs a more resolving instrument or a reviewed structural change.

Read [decision-guards.md](decision-guards.md) for G5, G6, GD, G8, G11 and G12, and [external-actions.md](external-actions.md) for E1. They share the activation, applicability and severity rules above.
