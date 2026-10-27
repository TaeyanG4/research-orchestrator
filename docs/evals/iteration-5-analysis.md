# Iteration 5 analyst pass

The supplied benchmark cannot support its apparent comparison: it reports **0 included / 64 excluded**, and every saved `grading.json` has an empty expectations array. There were no recorded assertion failures to diagnose. This pass first corrected the audit, then reconstructed grades from the saved executor traces and outputs. Original iteration artifacts remain unchanged; derived grades, audit reports, benchmark and static viewer live in the sibling evaluation workspace's `iteration-5-analysis/` directory.

After conservative exclusions, **29 v3 and 23 released-v2 runs** are usable, with **23 matched cases**. v3 passes **160/161 assertions**; v2 passes **63/134**. On matched cases, the mean case pass rate is **99.52% versus 47.93%**, a **51.59 percentage-point difference**. This is a retrospective regrade of the original executions, not a measurement of the edits made here.

## Method and evidence boundaries

Applied skill-creator's benchmark analyzer, per-assertion grader, causal instruction review, generalization review, and improvement steps. Reviewed the two configurations' transcripts, artifact contents and recorded capability differences; reran deterministic graders against saved artifacts. Independent analyst workers reviewed guard and runtime cases. The current v3 skill and released-v2 behavior documented in the saved skill reads were compared; v2's missing `ro`, presets, hooks and guard features are baseline capability gaps, not v3 regressions.

Before skill edits, reread skill-creator's **Writing Style**, **Progressive Disclosure**, and description guidance. Kept the core and accurate, actively scoped description unchanged; put the one instruction refinement in the existing operation reference. Added a strict-format case with the unchanged prompt settings block, `case.yaml`, one assertion per grader file, scaffold script and input fixture. Existing case prompts and graders are unchanged.

The original and reconstructed static review viewers are available; the reconstructed viewer was refreshed using skill-creator's `generate_review.py` and includes prior outputs. No user review feedback was supplied. Skipped a new executor A/B iteration, description optimization, blind preference comparison and packaging: this builder pass analyzes supplied executions and validates the patch locally; it does not establish post-edit behavior, trigger accuracy, a blind preference winner or a release. The new behavioral case remains for the next executor iteration. No commit was made.

All evidence paths below are relative to `iteration-5/<case>/<configuration>/` unless explicitly marked as repository paths. Local usernames, drive paths and staging directory identifiers are omitted. `v3` means `with_skill`; `v2` means `old_skill`. A percentage is the reconstructed passed/total assertion rate for one run. Excluded runs have no numeric rate, even when useful diagnostic artifacts survived.

## Per-case results

| Case | v3 passed/total (rate) | v2 passed/total (rate) | Excluded |
| --- | ---: | ---: | --- |
| analytic-complete-coverage | 5/5 (100.0%) | 5/5 (100.0%) | none |
| cli-hook-literal | excluded | excluded | v3, v2 |
| close-recorded-scope | 3/3 (100.0%) | 2/3 (66.7%) | none |
| codex-enforcement-evidence | excluded | excluded | v3, v2 |
| codex-host-capabilities | 6/6 (100.0%) | excluded | v2 |
| competition-direction-review | 5/5 (100.0%) | 1/5 (20.0%) | none |
| competition-preset-transition | 7/7 (100.0%) | 0/7 (0.0%) | none |
| dangling-instrument-evidence | 5/5 (100.0%) | 0/5 (0.0%) | none |
| direction-review-grace | 4/4 (100.0%) | 1/4 (25.0%) | none |
| external-action-order | 5/5 (100.0%) | excluded | v2 |
| external-retry-chain | 8/8 (100.0%) | 0/8 (0.0%) | none |
| hook-effective-working-directory | 7/7 (100.0%) | 1/7 (14.3%) | none |
| hook-interpreter-override | excluded | excluded | v3, v2 |
| hook-portability | 4/4 (100.0%) | 2/4 (50.0%) | none |
| job-monitor-recovery | 6/6 (100.0%) | 6/6 (100.0%) | none |
| launch-root-binding | 5/5 (100.0%) | excluded | v2 |
| non-ml-replication | 8/8 (100.0%) | 7/8 (87.5%) | none |
| note-id-kind | 2/2 (100.0%) | excluded | v2 |
| owned-job-monitor | 6/6 (100.0%) | excluded | v2 |
| owned-job-parent-exit | 5/5 (100.0%) | 4/5 (80.0%) | none |
| project-language | 8/8 (100.0%) | 8/8 (100.0%) | none |
| queue-freeze-delivery | 4/4 (100.0%) | 1/4 (25.0%) | none |
| quick-goal-routing | 3/3 (100.0%) | excluded | v2 |
| release-ci-matrix | 5/5 (100.0%) | 5/5 (100.0%) | none |
| repair-missing-coordination | 11/11 (100.0%) | 3/11 (27.3%) | none |
| reviewer-read-only | 5/5 (100.0%) | 5/5 (100.0%) | none |
| selection-family-source | 6/6 (100.0%) | 0/6 (0.0%) | none |
| unified-research-resume | 5/5 (100.0%) | 4/5 (80.0%) | none |
| v2-rules-upgrade | 5/5 (100.0%) | 3/5 (60.0%) | none |
| v3-interface-scope | 3/3 (100.0%) | 0/3 (0.0%) | none |
| work-project-session-history | 6/6 (100.0%) | 2/6 (33.3%) | none |
| work-project-start | 8/9 (88.9%) | 3/9 (33.3%) | none |

## Proven grader and harness bugs

| Bug | Evidence contradicting the old check | Correction and regression coverage |
| --- | --- | --- |
| Allowed runtime inherits an `evals` ancestor | `analytic-complete-coverage/with_skill/run.json` classifies the assigned `skill/SKILL.md` read at transcript Event 6 and ordinary project files as `eval_or_grader_path`. The same ancestry mistake excluded every run before grading. | `scripts/evals/contamination.py` checks reserved components relative to the most specific assigned root. Nested grader/eval material, other runs and source access remain protected. Saved flags are recoverable only when the old findings are reproduced and proven allowable; missing traces and independent exclusions stay excluded. |
| Shell path tokens become fictitious paths | `launch-root-binding/with_skill` supplied comma-separated absolute paths; `project-language/old_skill` supplied a Python raw-string path. The audit combined them or retained the raw prefix, inventing an out-of-root path. | Normalize literal path operands without executing shell text. Tests retain forbidden members and real foreign accesses as negative controls. |
| Fenced samples treated as live records | `work-project-start/with_skill/outputs/discoveries.md` contains only a fenced D-A-001 format example, yet `08-no-routine-discovery` failed. `work-project-session-history/with_skill/outputs/work-snapshot/discoveries.md` contains the real suffix-selection finding citing `trial.md` and `bravo.log`, followed by a fenced example with the same ID; the parser replaced the finding with `...` and failed `03-reusable-discovery`. | Shared eval record parsers ignore fenced examples, including tilde fences. Positive tests preserve the real finding; a real routine discovery still fails. |
| Explained absence treated as an empty field | `work-project-session-history/with_skill` records `New plan items: none — the two preparation tasks exhaust this session's authorized scope; the converter investigation is deferred to the next-session action.` The grader discarded the reason and failed `06-compact-bookkeeping`. | Only blank or bare `none` counts as empty. Reasoned absence passes; bare empty follow-up still fails. This matches `references/plan-items.md`'s existing follow-up guidance. |
| Instrument exclusion treated as a performed experiment | `non-ml-replication/with_skill/outputs/handoff.md` says `Not for: target-change, model-change`. `04-domain-appropriate` rejected that forbidden-use list even though the run only replicated eight archived pairs. | Ignore fenced examples and the instrument's `Not for` line in this lexical check. A live predictive-model hypothesis still fails. |
| Launch confirmation required an absent trailing semicolon | `owned-job-monitor/with_skill/events.jsonl` records `J-A-0001 launched; confirmed alive`; `.ro/jobs.json` contains confirmed identity, finished status and exit 0, and `runs/owned/job-result.json` reports completion. `02-owned-job` could not associate the job because its regex required `alive;`. | Accept the observed complete confirmation line with or without the optional hint. Wrong job IDs, near-matching words, missing confirmation and unexecuted commands remain rejected. The same diagnostic bug occurs in the excluded v2 run; that does not make its contaminated score eligible. |
| Infrastructure failure could become a task failure | Both configurations of `codex-enforcement-evidence` and `hook-interpreter-override` have `failure_category: setup/copy`, an access-denied artifact-copy error and executor return code 0. After audit correction, the generic error path would mark every assertion false. | Grading and aggregation exclude recorded setup/copy or launch failures instead of scoring incomplete captured evidence. Tests cover stale passing and failing grades, no judge invocation, and recovery after a transient disconnect followed by a copy failure. |

The reconstructed graders repair these errors without changing the original case assertions or awarding credit to unsupported outputs. The shell audit remains conservative: attempted access to restricted evaluation material can exclude a run even without proof of a successful read. No claim of perfect isolation is made.

Follow-up review found a regression in the initial fenced-example correction: returning sanitized records made an unchanged event with embedded fenced evidence fail history preservation, while edits inside fenced discovery evidence became invisible to comparison. Record discovery now masks fences without changing source offsets and returns the original record text; field parsing still ignores example fields. Four new controls cover unchanged and edited fenced evidence, both fence styles, and LF/CRLF record boundaries. They failed before the fix and pass afterward. Replaying all 63 eligible non-writing scripted checks against the saved runs produced no differences from the reconstructed grades.

## Real v3 instruction weakness and change

`work-project-start`, assertion `09-compact-items.md`, is the sole eligible v3 failure. Its three routine staged items each have six top-level fields: `Claimed`, `Goal`, `Evidence`, `Next test`, **`Deliverables`**, and `Stages`. The extra field repeats extensive acceptance criteria already held in the agreed brief. This is not a parser error: the six fields are real, outside fences.

The prior `references/plan-items.md` presented a compact shape but also allowed extra fields generally, without explaining how to retain detailed acceptance criteria while keeping the queue small. That ambiguity supports a narrow instruction refinement. The reference now explains why acceptance criteria and deliverables stay in the agreed brief and are linked from `Evidence` or `Next test`; additional fields are useful when they change selection, ownership or execution. It preserves legitimate dates, resource differences and dependencies rather than imposing a universal five-field schema.

Added `evals/work-brief-references/`, using workshop preparation instead of archive conversion. Its assertions check compact staged items, links to the agreed acceptance criteria, preserved scope/dependency order, and honest setup-only closure. The original failing case remains unchanged. This tests transfer of the principle, rather than adding archive-specific instructions. The new case has format/registration validation but no post-edit model execution yet.

## Exclusions

| Cases and configurations | Classification | Saved evidence |
| --- | --- | --- |
| `codex-enforcement-evidence` and `hook-interpreter-override`, both configurations (4 runs) | Infrastructure exclusion; some also have foreign-source access | `run.json` reports `setup/copy` with access-denied capture errors. Partial outputs cannot support complete grades. The former v3 trace also reads source host scripts/tests and `scripts/evals/run_evals.py` (Events 37–40); the latter reads installed/source material (Events 29, 35–36). These are additional reasons not to claim clean behavior. |
| `cli-hook-literal`, v3 | Conservative isolation exclusion; no successful foreign read established | Event 22 probes ancestor `AGENTS.md` paths including the workspace and `_runs`; the completed command has empty output. The audit treats those restricted ancestor probes as attempted access. This is not evidence of a v3 instruction failure or a confirmed leaked answer. |
| `quick-goal-routing`, v2 | Conservative isolation exclusion; no successful foreign read established | Event 14 probes ancestor `AGENTS.md` paths outside the assigned temporary root. Later synthetic Python-expression path findings are not used as evidence of successful foreign access. |
| `cli-hook-literal`, v2 | Actual foreign-source contamination | Installed/source searches are followed by main-checkout `ro.py` execution, including Event 113. It is no longer an isolated released-v2 execution. |
| `codex-host-capabilities`, v2 | Actual foreign-runtime contamination | Events 27 and 30–31 read another staged run's v3 hooks and operations references; the final report describes a recovered local reference. |
| `external-action-order`, v2 | Actual foreign-source contamination | Events 54 and 62 read the main checkout's v3 skill and references; `handoff.md` explicitly says it used an existing local v3 installation. |
| `launch-root-binding`, v2 | Actual foreign-source contamination | Events 39–41, 52, 60, 94 and 103 read/execute the main checkout's v3 CLI, initializer and references. |
| `note-id-kind`, v2 | Actual foreign-source contamination | `outputs/notes.md` admits fallback to the source checkout; Events 33, 48, 54, 56 and 64 execute its v3 CLI. |
| `owned-job-monitor`, v2 | Actual foreign-source contamination | Events 49 and 55–59 read the main checkout's v3 core and operations/workflow/session references; its successful job is not a clean v2 baseline. |

## Assertion failure inventory

Every eligible reconstructed failure is listed below. **S** means the real v3 skill weakness described above. **B** means released-v2 capability or output-format gap, not a reason to add v3 instructions. Baseline failures are evaluated against the same requested outcomes as v3; a missing guard does not earn a negative-control pass merely by producing no warning. Evidence of a real exercised exemption is required by skill-creator's substantive-completion criterion.

| Case / configuration | Assertion file | Class | Evidence |
| --- | --- | --- | --- |
| close-recorded-scope / v2 | `90-followup.md` | B | close.txt records actual ro close CommandNotFoundException, exit 1. The v2 distribution has only initializer/checker scripts; no ro close implementation exists. |
| competition-direction-review / v2 | `01-checker-clean.md` | B | Current checker reports missing Read bound, classic sections under Workflow unified, and missing staged-item structure; the baseline used its legacy checker. |
| competition-direction-review / v2 | `02-direction-review.md` | B | D-A-006 lacks Kind: direction-review and its required structured fields; handoff uses Direction review instead of Last direction review. |
| competition-direction-review / v2 | `03-saturation-response.md` | B | Remaining H-A-07 puts Family and Stages in nested lines, so no top-level family or recognized structural exit exists in the required queue schema. |
| competition-direction-review / v2 | `04-decision-follow-up.md` | B | The event cites D-A-006/H-A-07, but the original five discoveries were reformatted with nested evidence fields, violating unchanged history. |
| competition-preset-transition / v2 | `90-01-inherited-default.md` | B | Inherited requested initializer/reconfiguration exit 2 for unsupported --preset; resulting baseline agents.md contains no External actions or external.gate setting. |
| competition-preset-transition / v2 | `90-02-custom-preserved.md` | B | Custom initialization rejects --external-actions; requested custom string is preserved only in diagnostic evidence, absent from resulting project settings. |
| competition-preset-transition / v2 | `90-03-opt-out-preserved.md` | B | Opted-out initialization rejects unsupported flags; project agents.md contains no External actions setting, so none was not retained through a transition. |
| competition-preset-transition / v2 | `90-04-legacy-conservative.md` | B | Legacy initializer rejects --preset; no transition, External actions field, or inactive-gate diagnostic exists. |
| competition-preset-transition / v2 | `90-05-explicit-inactive.md` | B | Opted-out stderr is an unsupported-option error, not the required inactive-gate configuration diagnostic. |
| competition-preset-transition / v2 | `90-06-matching-hook-block.md` | B | All hook-probe.json records say status UNAVAILABLE, hook_invoked false, decision null; no installed hook exists. |
| competition-preset-transition / v2 | `90-07-opt-out-hook.md` | B | No hook ran (hook_invoked false); missing implementation is not a saved no-denial hook result. |
| dangling-instrument-evidence / v2 | `01-mixed-reference.md` | B | Raw s1-light-active and s1-strict-active outputs report generic discovery-format problems, not evidence.instrument.dangling or missing I-A-99. The supplied checker has no evidence guards. |
| dangling-instrument-evidence / v2 | `02-measurement-reference.md` | B | Discovery/external Result scenarios produce no evidence.instrument.dangling; the checker does not parse the requested measurement evidence schema. |
| dangling-instrument-evidence / v2 | `03-rejection-reference.md` | B | Rejection-only outputs contain no missing-instrument check; v2 cannot validate that reference. |
| dangling-instrument-evidence / v2 | `04-exemptions.md` | B | Literal target-code absence holds, but active and exempt cases alike lack all evidence-guard checks. Unsupported off/inapplicable metadata cannot demonstrate exemption behavior; no substantive guard control was exercised. |
| dangling-instrument-evidence / v2 | `05-valid-history.md` | B | Literal target-code absence holds, but the historical-instrument scenario receives generic discovery-format problems and no instrument-reference evaluation. This is incidental absence, not valid-instrument acceptance. |
| direction-review-grace / v2 | `90-fresh-grace.md` | B | fresh-check.txt is only CONSISTENCY: OK; no INFO guard.direction.stale or first review due date is emitted because v2 lacks cadence guards. |
| direction-review-grace / v2 | `90-paused-cadence.md` | B | Paused line is preserved and target warning is literally absent, but resumed/fresh outputs are identical because v2 has no cadence logic. This does not demonstrate the requested pause exemption. |
| direction-review-grace / v2 | `90-resumed-due.md` | B | resumed-check.txt is CONSISTENCY: OK, with no WARN guard.direction.stale; v2 does not implement this check. |
| external-retry-chain / v2 | `01-third-executes.md` | B | attempts.log has four lines: X-A-001, X-A-002, X-A-003, X-A-003. Direct replay appended the third ID again. |
| external-retry-chain / v2 | `02-chain-accepted.md` | B | Main checker emits neither code only because v2 ignores manual X action records and implements no retry validator; no substantive valid-chain check occurs. |
| external-retry-chain / v2 | `03-replay-refused.md` | B | Direct replay returns 0 and appends X-A-003 a second time; no installed execution wrapper is available. |
| external-retry-chain / v2 | `04-invalid-links-refused.md` | B | No wrapper exists or is invoked for malformed chains; saved cases were checked only by a checker that ignores action records. |
| external-retry-chain / v2 | `05-ancestor-refused.md` | B | Broken-ancestor record receives an inert checker pass; no guarded execution/refusal is demonstrated. |
| external-retry-chain / v2 | `06-earlier-record-refused.md` | B | old-prepared-after-done direct stub returns 0 and appends one log entry, with no gate. |
| external-retry-chain / v2 | `07-ambiguous-ancestor.md` | B | duplicated-ancestor-id checker returns 0; no wrapper executes or refuses the record. |
| external-retry-chain / v2 | `08-padded-duplicate-refused.md` | B | Both trailing-whitespace direct stub probes return 0 and append an entry; no installed duplicate gate exists. |
| hook-effective-working-directory / v2 | `01-envelope-cwd.md` | B | probe-results.json envelope_cwd_bound has submitted false and hook_response null; no hook denial was captured. |
| hook-effective-working-directory / v2 | `02-tool-workdir.md` | B | tool_workdir_bound has submitted false and hook_response null; no hook denial was captured. |
| hook-effective-working-directory / v2 | `03-unrelated-sibling.md` | B | envelope_cwd_scratch has submitted false and hook_response null. Absence of a hook invocation cannot satisfy an assertion about a captured non-denying response. |
| hook-effective-working-directory / v2 | `04-parent-relative-target.md` | B | parent_path_from_scratch has submitted false and hook_response null; no hook denial was captured. |
| hook-effective-working-directory / v2 | `05-unknown-directory.md` | B | unknown_directory has submitted false and hook_response null; the report explicitly says no actual uncertain-directory response was obtained. |
| hook-effective-working-directory / v2 | `07-worker-cleanup.md` | B | worker.skill_owned_job_registered is false; only local subprocess termination evidence is present, with no final owned-job registry. |
| hook-portability / v2 | `90-missing-hook-record.md` | B | ro brief failed with CommandNotFoundException; the note explicitly says CLI-generated hook status is unavailable, so no required hooks never ran output was captured. |
| hook-portability / v2 | `90-portable-entry-points.md` | B | The note correctly says this released bundle ships no Linux wrapper or .cmd wrapper; it never identifies the requested shipped entry points. |
| non-ml-replication / v2 | `01-checker-clean.md` | B | Current checker reports missing Read bound and classic plan section under saved unified workflow; successful arithmetic does not repair the coordination schema. |
| owned-job-parent-exit / v2 | `05-terminal-monitor-outcome.md` | B | Final .ro/jobs.json records status stopped, stop_requested, tree_empty true and only a monitor PID. monitor-result.json is a local status command, not a recorded terminal monitor outcome; no monitor outcome field/Job outcome is preserved before release. |
| queue-freeze-delivery / v2 | `90-delivery.md` | B | plan.md keeps the archive item; v3 uses Ready by: 2099-01-02, v2 uses nested Due without Ready by. |
| queue-freeze-delivery / v2 | `90-expiry.md` | B | checks.md and check_dates.py execute the supplied checker at both noon dates in v3; v2 check_delivery.py adds a separate local adapter warning, not WARN plan.freeze.expired from the supplied checker. |
| queue-freeze-delivery / v2 | `90-freeze.md` | B | agents.md has Queue freeze: until 2099-01-01 in v3; v2 places an on/until value in handoff.md instead. |
| repair-missing-coordination / v2 | `01-conflict-refused.md` | B | Archive conflicting Workflow refuses, but the required unified intake-b project was never initialized. The verification refusal is exercised only on a classic substitute or absent target, so both requested repair scenarios were not completed. |
| repair-missing-coordination / v2 | `02-no-refusal-writes.md` | B | Classic substitute refusal snapshots preserve bytes, but no unified intake-b existing project exists to establish the required two-project refusal inventory. This is incomplete requested coverage. |
| repair-missing-coordination / v2 | `03-stored-layout.md` | B | archive-a is classic, but requested intake-b remains uninitialized; only classic-diagnostics/intake-b was recovered, with no unified Queue. |
| repair-missing-coordination / v2 | `05-project-names.md` | B | Ordinary archive recovery generates title archive-a and roster A. Intake substitute recovery generates title intake-b. Correct final titles require additional explicit --name arguments, so stored project-name recovery failed. |
| repair-missing-coordination / v2 | `06-checker-clean.md` | B | Requested intake-b/settings-c check outputs exit 2 with all four coordination files missing. Three substitute/recovered classic fixtures pass, which is not every requested recovered project. |
| repair-missing-coordination / v2 | `08-conflicting-roster.md` | B | archive-a --agents A invocation exits 0 and creates plan.md with Agent A, rather than refusing before mutation. |
| repair-missing-coordination / v2 | `09-unknown-roster.md` | B | No unified intake-b exists; the classic substitute without --agents exits 0 and creates default A. Required refusal is absent. |
| repair-missing-coordination / v2 | `10-missing-settings.md` | B | Requested unified settings-c is unavailable; classic settings diagnostic exits 0 and regenerates defaults after agents.md loss, losing the local rule until backup restoration. |
| selection-family-source / v2 | `01-same-family.md` | B | A_light/A_strict both return CONSISTENCY: OK; no guard.selection.rationale or mode-dependent severity exists in v2. |
| selection-family-source / v2 | `02-valid-choices.md` | B | B and C literally lack the warning, but A also passes with no rationale because v2 has no G11. These outputs do not substantively demonstrate valid diverse/rationale selection handling. |
| selection-family-source / v2 | `03-required-family.md` | B | D_strict returns OK even though X-A-002 lacks Family; no guard.selection.family check exists. |
| selection-family-source / v2 | `04-missing-action.md` | B | E_strict returns OK despite missing selected X-A-099; no family-reference validation exists. |
| selection-family-source / v2 | `05-inline-cannot-mask.md` | B | F_strict returns OK for misleading inline families and equal action families; no rationale check exists. |
| selection-family-source / v2 | `06-exemptions.md` | B | Historical/inapplicable outputs lack selection codes only because all cases bypass unsupported G11; no guard exemption behavior is established. |
| unified-research-resume / v2 | `01-checker-clean.md` | B | Current checker reports settings.missing for Read bound; all arithmetic, claim receipt and follow-up assertions pass. |
| v2-rules-upgrade / v2 | `01-checker-clean.md` | B | Current checker reports settings.workflow.unmigrated: settings say unified while files retain classic sections. |
| v2-rules-upgrade / v2 | `03-unified-upgrade.md` | B | Output lacks the v3 template marker and real unified Queue migration; compatibility guidance was added instead. |
| v3-interface-scope / v2 | `01-short-scope.md` | B | Exact quote is Orchestrate agent research; it does not cover work projects or competitions. Transcript event 14 confirms this is the actual v2 interface. |
| v3-interface-scope / v2 | `02-prompt-scope.md` | B | Exact prompt is Initialize Research Orchestrator for this project and resume existing state when present. It lacks explicit work/research/competition breadth. |
| v3-interface-scope / v2 | `03-resume-first.md` | B | v2 prompt says initialize and resume, without resume-first ordering or preset/workflow choice. Executor correctly identifies this limitation. |
| work-project-session-history / v2 | `02-session-completions.md` | B | work-snapshot/handoff.md has no consolidated session event with the two Completed IDs. |
| work-project-session-history / v2 | `04-history-preserved.md` | B | No original work session event exists to retain during the change to solo-research. |
| work-project-session-history / v2 | `05-checker-clean.md` | B | Strict checker reports agents.rules.edited for manually applied profile settings; no clean generated configuration. |
| work-project-session-history / v2 | `06-compact-bookkeeping.md` | B | queued-plan.md has 15 fields per routine item and no shared work-session event. |
| work-project-start / v3 | `09-compact-items.md` | S | outputs/plan.md has six fields on each live staged item, including repeated Deliverables in addition to Claimed, Goal, Evidence, Next test and Stages. |
| work-project-start / v2 | `01-checker-clean.md` | B | agents.md embeds explanatory text inside Preset instead of a supported preset value; current checker rejects it. |
| work-project-start / v2 | `02-work-preset.md` | B | Preset contains a compatibility explanation; Profile, Workflow and Item size are absent. |
| work-project-start / v2 | `03-staged-queue.md` | B | Four full legacy items lack the required unclaimed staged-work structure. |
| work-project-start / v2 | `06-light-ordering.md` | B | The queue carries all scoring fields and calculated priorities instead of compact work ordering. |
| work-project-start / v2 | `07-session-summary.md` | B | Setup and close are separate none events instead of one work session event with Completed. |
| work-project-start / v2 | `09-compact-items.md` | B | plan.md retains the 15-field research shape on each routine work item, exceeding the compact work contract. |

## Patterns the aggregate hides

- Both versions pass all assertions for analytic coverage, job-monitor recovery, project language, CI inspection and read-only review. These provide regression coverage but do not demonstrate a v3 gain. Several prompts and fixtures already specify much of the successful behavior.
- v2's successful job-monitor recovery builds a project-local substitute. Its parent-exit case similarly implements local supervision but fails to preserve a distinct terminal monitor outcome in the registry. These are baseline execution strategies, not evidence that v2 shipped the new runtime.
- Guard cases discriminate strongly, but successful negative controls must exercise an available implementation. Otherwise missing functionality looks like permissive behavior. The reconstruction explicitly rejects those accidental passes; baseline details remain visible in the derived grading files.
- The CI assertion saying “uses no secrets” is imprecise: checkout can use the implicit platform token while declaring no custom secrets. Both reports correctly distinguish this and disable persisted credentials. There is no observed failed assertion to repair here, so the case is unchanged; future wording should clarify explicit secrets rather than penalize that accurate caveat.
- Across the 23 matched cases, v3 takes **241.87 seconds** versus **258.71 seconds** for v2 on average (16.84 seconds less). Saved token totals average **100,435 higher** for v3 on these pairs. These are executor accounting totals, not billing estimates. `external-retry-chain/v3` (515.29 seconds) and `competition-direction-review/v3` (454.42 seconds) are the longest eligible runs, so one overall cost number conceals case mix.
- There is one run per case/configuration. Cross-case dispersion is not stochastic repeat variance; no flakiness rate or statistical significance can be inferred. Six v3-only eligible cases cannot enter the matched delta. Excluded outputs never become numeric successes.

## Validation and delivery

The changes are limited to the plan-items reference, one new strict-format behavior case, eval inventory, eval harness/graders, targeted regression tests and this report. Existing behavior cases are unchanged: harness fixes restore their original assertion semantics, with positive and negative unit controls for grading changes. Source iteration-5 artifacts are preserved. Skill-creator's template/schema validation is exercised by the repository tests. The new instruction's behavioral improvement remains unmeasured until the next isolated A/B run.

- `python -m pytest -q`: **PASS, 1,609 tests** (93.21 seconds).
- `python scripts/validate_release.py`: **VALIDATION: PASS**, including its own **1,609 passing tests** (93.04 seconds).
- `git diff --check`: **PASS**. Report scan found no local absolute paths. The new case loads with four registered assertions.
- Earlier validation exposed stale infrastructure-exclusion test expectations and the report's restricted vocabulary; both were corrected before these final passing gates.
