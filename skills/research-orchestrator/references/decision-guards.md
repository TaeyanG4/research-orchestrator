# Decision guards

Read this when recording an override, insight, direction review, phase milestone, selection, or effort review. It covers G5, G6, GD, G8, G11 and G12; [research-guards.md](research-guards.md) defines activation, applicability and severity.

## G5 — Overrides and rejections

**Why:** a registered decision rule can be bypassed indefinitely, or a change rejected before confirming that it actually executed.

Add `Override: <rule> said <verdict>; decided <verdict> because <reason>; re-check: <trigger>; expires YYYY-MM-DD` to the discovery that overrides a rule. Close it on a later discovery with `Override resolved: D-A-003`. For applicable non-operational decisions, record `Outcome: supported | rejected | inconclusive`. A `rejected` outcome needs `Rejected on: I-A-01; fired: <evidence the change executed>`. A concrete trace such as `trace.log confirms execution` is sufficient; a discovery citation is optional, but must resolve when present. Empty evidence and placeholders such as `n/a` or `yes` do not establish execution.

Localized findings use the structural Outcome so their language cannot bypass rejection checks. Missing or invalid outcomes warn (ERROR in strict mode); legacy English `does not hold` findings still receive rejection checks.

**Rules:** `guard.override.open` lists unresolved overrides as INFO; `guard.override.recheck` warns when an override lacks a re-check trigger or has expired; `guard.rejection.evidence` warns when the required rejection evidence is absent. The last two become ERROR in strict mode. G5 can be inapplicable where there are no registered rules or experimental rejections. An override nobody declares is a known false negative: the checker cannot detect it.

- **Work:** bypass a latency gate temporarily, with a traffic threshold for re-check and an expiry date.
- **Research:** reject a method only after the trace shows its intended intervention ran on the stated instrument.
- **Competition:** keep a candidate despite a registered cutoff, explain the discrepancy, and schedule a re-check before the window closes.

## G6 — Insights

**Why:** a useful diagnosis can remain in prose without ever changing the plan.

An insight is an ordinary discovery with `Kind: insight`, `Status: open`, and `Due: YYYY-MM-DD HH:MM`. Its author chooses a due time no later than `Date` plus `insight-due` (48 hours by default). Replace the status with `planned H-A-07` or `rejected — <evidence D-id and reason>` when it is acted on. A planned item must still be queued or have a completion event.

A rejected status must name an existing discovery and give a reason. Missing or unrecognised statuses receive `guard.insight.overdue`, WARN in light mode and ERROR in strict mode; dangling evidence citations remain structural ERRORs on active records.

**Rules:** `guard.insight.overdue` warns for an overdue open insight or a missing planned item and becomes ERROR in strict mode. `guard.insight.rejection` stays WARN when its rejecting discovery fails the circular-instrument check. Declare G6 inapplicable if the project produces no diagnoses needing follow-up.

- **Work:** a diagnosis of slow imports becomes a queued profiling item by its due time.
- **Research:** a source effect becomes a planned stratified audit, or is rejected on eligible measured evidence.
- **Competition:** a diagnosis of a missing core family becomes a standalone build, rather than another small variant.

## GD — Direction review

**Why:** good execution can preserve a weak initial frame, omit a core family, or ignore relevant public methods.

Create a discovery with `Kind: direction-review`. For Profile `work`, only `Gap` and `Decisions` are required: compare the target with current evidence, then record what to change or keep and why. The other fields remain allowed when useful.

Research requires `Gap`, `Decisions`, and a `Data audit` in the first review: establish the question, the evidence's origin and limits, and the next decision. Competition also requires `Decomposition`, `Core families`, `Intake`, and `Rejected consistent gains`. Those four parts are INFO advice for research unless `Guard thresholds` includes `direction-parts=full`; the default `direction-parts=profile` follows the profile. This lets an arithmetic replication review its evidence without pretending to run a competitive search.

When relevant, record the gap on an instrument and its observation date; component losses; standalone families built or missing; target production and source effects; methods and score levels seen since the last review; rejected gains or `none`; and created/removed plan IDs or `no change — <reason>`. Each part may say `not applicable — <reason>`. Intake is about methods and score levels, not collecting assets.

When the remaining gap is much larger than typical reproducible gains, prioritize a missing standalone family or structural change. Before trying more micro-variants, set a small explicit variant budget in `Decisions`, tied to expected gain and remaining time; once exhausted, change direction or document evidence for extending it. Record reasoned applicability exceptions rather than treating a fixed ratio or count as universal.

Update Shared state with `Last direction review: D-A-012 (YYYY-MM-DD)`.

**Rules:** `guard.direction.stale` is INFO before the first review is due, counted from `Guards: ... since YYYY-MM-DD` plus `direction-review` (seven days). Without an activation date, use Shared state `Started: YYYY-MM-DD`, the earliest record, or the legacy rules date. Once due, it is WARN (strict: ERROR); work/research stay INFO until a dated item event after activation. `guard.direction.incomplete` warns for missing required parts and becomes ERROR in strict mode.

For paused or archived work, add `Paused: YYYY-MM-DD` in Shared state to suspend cadence without skipping review checks. Remove it when work resumes and review the direction if due; a pause does not restart the clock. Invalid or future pause dates warn and do not suspend cadence. Reserve `Not applicable: GD — <reason>` for work with no strategic choices or continuing review cycle, rather than using it to silence a new or paused project.

- **Work:** compare import p95 against the service target, then choose a bulk rewrite or incremental changes with a reason.
- **Research:** audit source and annotator effects and compare standalone families before continuing refinements.
- **Competition:** compare the external target gap and component losses, review newly described methods, and act on an unbuilt core family.

## G8 — Phase clock

**Why:** important exploration and selection steps can begin too late.

Set `Phase clock: start YYYY-MM-DD, deadline YYYY-MM-DD` and record `Milestones: 10 complete; 25 pending; 75 pending` in Shared state. The default shares are 10/25/75 percent of that window: baseline, core families, and freeze. Keep pending milestones explicit; change their shares through `milestones=10/25/75` when needed.

**Rule:** milestone states are `pending`, `blocked`, `incomplete`, or `complete`; only `complete` satisfies a milestone. Unknown or malformed states receive `guard.phase.state`. A missing or unfinished milestone past its share receives `guard.phase.milestone`, WARN in either mode, so a spelling error cannot hide a missed checkpoint. These checks run only with a clock. Declare G8 inapplicable for open-ended work.

- **Work:** finish a migration baseline, design comparison, and cut-over choice before their window shares.
- **Research:** finish the baseline, standalone families, and final evidence selection before a review deadline.
- **Competition:** reserve enough of the fixed window for a core-family comparison and final candidate choice.

## G11 — Selection

**Why:** superficially different final picks may expose the same failure mode.

In Shared state use `Final picks: X-A-012, X-A-019 (rationale: <why these>)`. Each selected action needs a `Family`; these action fields are the authoritative family source, so a second list cannot mask shared risks. Same-family choices are valid when the rationale explains the tradeoff.

**Rules:** `guard.selection.family` reports a structural ERROR for a missing selected action or its `Family`. `guard.selection.rationale` warns when two or more final picks share a family without `rationale:` and becomes ERROR in strict mode. Historical actions retain their exemption. Declare G11 inapplicable when there is no final selection.

- **Work:** select two rollback candidates from one implementation family because both passed separate operational constraints.
- **Research:** choose two reports using the same method because they cover distinct populations, stating that reason.
- **Competition:** choose same-family candidates only with a recorded reason for their shared risk and useful differences.

## G12 — Effort (explicit opt-in)

**Why:** easy process work can displace work that could change the outcome, but incomplete tagging cannot justify a precise estimate.

Tag events with `Effort: infra | process | science | research | work` (choose one), and optionally `Session: <identity>`. Without a session identity, events are grouped by slot and day. The checker reports the coarse session share of infra/process and counts untagged events as `unknown`, never silently treating them as substantive. Enable G12 explicitly through `Guard set`; its default threshold is `effort=55%`.

**Rule:** `guard.effort.share` is INFO in light mode and WARN in strict mode when the infrastructure/process share exceeds the threshold; unknowns are reported. Declare G12 inapplicable when this estimate would not inform a decision.

- **Work:** repeated tooling changes take most tagged events while the migration stays blocked.
- **Research:** bookkeeping dominates a session whose main uncertainty still lacks an experiment.
- **Competition:** repeated packaging work dominates a session while the target gap remains unchanged.
