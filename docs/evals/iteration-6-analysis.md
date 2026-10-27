# Iteration 6 analyst pass

Release scope (owner decision, 2026-10-26): no further scenario runs or description optimisation for 6.0.0. The owner validates in real use. This adjudicated snapshot is the behaviour evidence. [Minimal original/adjudicated archive](evidence/iteration-6.zip) and [reconstruction procedure](evidence/regrade-procedure.md) now retain grades, benchmark tables and hashes; raw traces remain withheld. Historical references below to sibling workspaces describe the original analysis, not a dependency for reconstructing headline arithmetic.

After correcting proven evaluation defects, **40 v3 and 36 released-v2 runs are usable; 18 are excluded**. v3 passes **231/232 assertions**, and v2 **110/207**. On the **31 matched cases**, mean case pass rates are **99.71% versus 56.31%**, a **43.40 percentage-point difference**. These are retrospective grades of the supplied Codex executions, not a measurement of this patch.

The original benchmark included 75 runs and excluded 19, with unmatched means of 87.87% and 47.23%. Its 33 v3 failed assertions comprise **31 infrastructure-induced failures, one proven numerical-grader defect, and one real instruction weakness**. The original 92 v2 failures comprise seven infrastructure-induced failures, the same numerical-grader defect, and 84 baseline capability/output failures. Recovery of falsely excluded runs exposes 13 additional v2 failures; none is a new v3 weakness.

## Method and evidence boundaries

Applied skill-creator's benchmark analysis (per-assertion, cross-case, resource and discrimination patterns), grader evidence verification, post-hoc instruction-causation review, improvement, and generalization review. Independent analyst workers checked baseline outputs, terminal infrastructure errors and contamination findings; final decisions use artifacts and native event records. Compared the current v3 instructions with released v2 at `713088d79745589b053ae02996670dc7147a8ee1`, including saved skill reads. This was an unblinded review, so no blind winner or numerical instruction-following score is asserted.

Before each skill-text edit, reread **Writing Style**, **Progressive Disclosure**, and description guidance. Kept the core and accurate, actively scoped description unchanged. Moved existing repair guidance from the nearly full presets reference into the migration reference, leaving a link, and added the preservation-evidence clarification there. New cases use the exact skill-creator settings block, `case.yaml`, scaffold, `files/`, and one objective assertion per grader. All 47 original case definitions remain unchanged. README and builder coverage inventories list the new cases as unattempted, without pass credit.

Original `iteration-6/` artifacts remain unchanged. The sibling `iteration-6-analysis/` contains copied runs, the deterministic regrade procedure, inline recovered judgments, updated grades/benchmark, analyzer notes and generated static viewer. Deterministic checks were replayed; unaffected judged verdicts were retained. Recovered judged assertions were evaluated against saved artifacts and trace evidence, with durations left unmeasured. Source SHA256 inventory verifies preservation. The original supplied viewer was available for inspection; the corrected viewer uses skill-creator's `generate_review.py`.

Skipped a new capture-intent interview because the requested analysis, baseline and gates were already specified. Skipped a fresh executor A/B iteration and notification timing capture because this builder pass analyzes supplied executions; new behavior remains for the next executor iteration. Skipped new user-feedback collection and blind comparison because no feedback/blind comparison was supplied or requested. Skipped description optimization and packaging because this is an instruction/grader repair, not a triggering study or release. No commit was made.

All evidence paths below are relative to `iteration-6/<case>/<configuration>/`; repository paths are explicitly named. `v3` means `with_skill`, `v2` means `old_skill`. A1, A2, etc. refer to the ordered assertions in each original `grading.json` / case graders. Excluded runs have no behavioral score even when useful partial outputs survived. Local drive paths, usernames and staging identifiers are omitted.

## Per-case results after adjudication

| Case | v3 passed/total (rate) | v2 passed/total (rate) | Excluded |
| --- | ---: | ---: | --- |
| analytic-complete-coverage | 5/5 (100.0%) | 5/5 (100.0%) | none |
| ancestor-rename-protection | 5/5 (100.0%) | 1/5 (20.0%) | none |
| claim-contention | 5/5 (100.0%) | 0/5 (0.0%) | none |
| cli-hook-literal | 5/5 (100.0%) | excluded | v2 |
| close-recorded-scope | 3/3 (100.0%) | 2/3 (66.7%) | none |
| codex-enforcement-evidence | excluded | excluded | v3, v2 |
| codex-host-capabilities | 6/6 (100.0%) | excluded | v2 |
| competition-direction-review | excluded | 1/5 (20.0%) | v3 |
| competition-preset-transition | 7/7 (100.0%) | 0/7 (0.0%) | none |
| credential-storage-redaction | 7/7 (100.0%) | excluded | v2 |
| dangling-instrument-evidence | 5/5 (100.0%) | 2/5 (40.0%) | none |
| direct-install-reviewer | 5/5 (100.0%) | 4/5 (80.0%) | none |
| direction-review-grace | 4/4 (100.0%) | 2/4 (50.0%) | none |
| evaluation-grade-integrity | 9/9 (100.0%) | 9/9 (100.0%) | none |
| evaluation-trace-audit | 6/6 (100.0%) | 6/6 (100.0%) | none |
| external-action-order | 5/5 (100.0%) | 2/5 (40.0%) | none |
| external-malformed-ledger | 3/3 (100.0%) | 2/3 (66.7%) | none |
| external-result-reconciliation | 5/5 (100.0%) | excluded | v2 |
| external-retry-chain | 8/8 (100.0%) | 0/8 (0.0%) | none |
| fenced-record-examples | 10/10 (100.0%) | excluded | v2 |
| hook-effective-working-directory | 7/7 (100.0%) | 1/7 (14.3%) | none |
| hook-interpreter-override | excluded | excluded | v3, v2 |
| hook-portability | 4/4 (100.0%) | 1/4 (25.0%) | none |
| identifier-rollover | 4/4 (100.0%) | 2/4 (50.0%) | none |
| job-monitor-recovery | 6/6 (100.0%) | 6/6 (100.0%) | none |
| launch-root-binding | 5/5 (100.0%) | excluded | v2 |
| native-session-slots | 10/10 (100.0%) | excluded | v2 |
| non-ml-replication | 8/8 (100.0%) | 7/8 (87.5%) | none |
| note-id-kind | 2/2 (100.0%) | excluded | v2 |
| owned-job-monitor | 6/6 (100.0%) | excluded | v2 |
| owned-job-parent-exit | 5/5 (100.0%) | 5/5 (100.0%) | none |
| project-language | 8/8 (100.0%) | 8/8 (100.0%) | none |
| queue-freeze-delivery | 4/4 (100.0%) | 1/4 (25.0%) | none |
| quick-goal-routing | 3/3 (100.0%) | 2/3 (66.7%) | none |
| release-ci-matrix | 5/5 (100.0%) | 5/5 (100.0%) | none |
| repair-missing-coordination | 10/11 (90.9%) | 5/11 (45.5%) | none |
| reviewer-read-only | 5/5 (100.0%) | 5/5 (100.0%) | none |
| saved-policy-roundtrip | 9/9 (100.0%) | 0/9 (0.0%) | none |
| selection-family-source | 6/6 (100.0%) | 2/6 (33.3%) | none |
| trigger-measurement-reasons | 9/9 (100.0%) | 9/9 (100.0%) | none |
| unified-research-resume | excluded | 4/5 (80.0%) | v3 |
| unreadable-subdirectory | excluded | 0/6 (0.0%) | v3 |
| v2-rules-upgrade | 5/5 (100.0%) | 3/5 (60.0%) | none |
| v3-interface-scope | 3/3 (100.0%) | 0/3 (0.0%) | none |
| work-brief-references | 4/4 (100.0%) | 3/4 (75.0%) | none |
| work-project-session-history | excluded | 2/6 (33.3%) | v3 |
| work-project-start | excluded | 3/9 (33.3%) | v3 |

## v3 failure classification and instruction change

| Case / assertions | Classification | Evidence and disposition |
| --- | --- | --- |
| competition-direction-review / A1?A5 | Infrastructure exclusion; service interruption misclassified as executor failure | Events 87?88 end in HTTP 503, `session bridge cooling down after upstream timeouts`, and `turn.failed`, following reconnects. A1's own evidence says checker exit 0; A2?A5 describe the completed direction review and structural pivot. These contradictions disprove the blanket behavior-zero interpretation, but do not prove the interrupted run finished. Exclude all five. |
| unified-research-resume / A1?A5 | Infrastructure exclusion | Events 57?58 end with `Selected model is at capacity` and `turn.failed`. Claim and arithmetic artifacts survived, but discovery, follow-up and closure were not finished. Exclude; do not add instructions based on outage-truncated work. |
| unreadable-subdirectory / A1?A6 | Infrastructure exclusion | Events 23?24 terminate at model capacity. A1?A6's own evidence already records unchanged probe bytes, PermissionError refusals, identical ledger/receipt hashes and absent execution marker. Exclude despite those successful partial artifacts. |
| work-project-session-history / A1?A6 | Infrastructure exclusion | Events 49?50 terminate at capacity. Inventory/readiness and checker artifacts exist; work-snapshot does not. Missing later artifacts are not evidence of a skill instruction defect after that interruption. |
| work-project-start / A1?A9 | Infrastructure exclusion | Events 9?10 terminate at capacity; outputs contain only unchanged brief and empty final response. No planning result can be graded. |
| non-ml-replication / A3 | Proven grader bug | `outputs/replicate.py` validates `n - 1 == degrees_of_freedom`. The old perturbation appended a ninth pair while retaining `For 7 degrees of freedom`; the saved canonical calculation succeeds and its deliberate validation rejects the inconsistent probe. Correcting only the fixture's count metadata makes the changed-observation check pass; independent changed-multiplier and canonical checks also pass. Both v3 and v2 are affected. |
| repair-missing-coordination / A2 | Real instruction/evidence weakness | `outputs/run-repair-trials.py:17,35?39` defines a four-name FILES list and snapshot over only those names. Saved manifests/logs cannot establish the required absence of other new or changed project files. Refusals and survivor hashes are real; the all-project preservation claim exceeds their scope. Retain failure. |

The real weakness is a missing verification method, not evidence that the initializer damaged files. The prior presets reference promised conflicting flags fail before writes, but did not explain how to demonstrate that claim. It now links to **`references/migration-v2-to-v3.md#missing-file-repair`**, which explains recursive relative-path inventories and hashes immediately around the operation, including tool state and non-coordination files, evidence outside the observed tree, and claims limited to inspected scope. The rationale explains why fixed survivor lists miss side effects; it imposes no universal manifest format on ordinary research. Both versions used four-file manifests, which supports a general evidence-scope clarification but does not prove a post-edit success.

`repair-snapshot-scope` transfers the lesson to another disposable project containing nested user data and hidden state. It checks a real stored-workflow conflict, complete snapshots, unchanged bytes/path set, external evidence storage, and controls detecting an extra file or changed hash. It does not teach an archive-specific answer or weaken the original failed assertion.

## Proven evaluation bugs and corrections

| Defect | Contradicting evidence | General correction and coverage |
| --- | --- | --- |
| Capacity/bridge errors become zero behavior scores | The seven scored interrupted runs below have terminal host errors, while `run.json` says generic executor failure; several zeroed assertions cite their own passing artifacts. | `scripts/evals/run_evals.py` recognizes host model-capacity and transient HTTP 502/503/504 diagnostics. A shared saved-run check repairs stale classification in grading/aggregation. Quoted/tool text, recovered errors and later unrelated failures stay distinct. `evaluation-transport-evidence` plus retry/grade/aggregate regression tests cover both positive and negative controls. |
| Whole Python programs become file paths | v2 analytic-complete-coverage Events 35/61, quick-goal-routing Event 39, selection-family-source Event 56, work-project-start Event 44 read assigned runtime/project files; the exclusion resolves multiline code as an `evals` path. | `contamination.py` recognizes Python stdin with flags/implicit stdin and unparseable shell wrappers as code, while scanning embedded literal read operands. Foreign source, installed skill and hidden-grader controls remain excluding. |
| PowerShell array comma becomes part of ancestor path | v2 work-brief-references Event 12 completes a guarded ancestor-instruction probe with empty output; an outside-quote comma corrupts the relative parent resolution. | Normalize the proven array delimiter before resolving the relative path; preserve actual commas inside filenames and retain a present-ancestor countercontrol. |
| Data literals and name filters become protected reads | direct-install-reviewer v3 Event 19 compares `$_.Name -eq 'evals'` and reports zero copied eval directories; v2 Events 14/25 use ignore patterns/comparisons. evaluation-trace-audit v3 Event 29 changes the string `workspace/evals` inside synthetic fixture data and comments. No protected read is performed. | Narrow AST/token-context handling distinguishes comparisons, comments, prints, copy-ignore patterns and two-argument string replacements from path operands. Paired actual-read controls still exclude. `evaluation-trace-code-operands` covers these and the previous two parsing defects; all original trace-audit cases are retained. |
| Incoherent numerical perturbation rejects valid validation | Both non-ml-replication analyses calculate all requested numbers from inputs, but reject the nine-observation/seven-df fixture. | `replication_check.py` updates declared count/df alongside the changed observations, preserves canonical bytes and independent multiplier control, and marks perturbed inputs as synthetic arithmetic sensitivities with historical report text retained only for comparison. Hardcoded count, output and multiplier controls still fail. `replication-coherent-controls` uses different data and three candidate programs. |

The audit corrections recover **eight** original exclusions: analytic-complete-coverage/v2, quick-goal-routing/v2, selection-family-source/v2, work-brief-references/v2, work-project-start/v2, direct-install-reviewer/both, and evaluation-trace-audit/v3. Recovery requires reproducing and disproving every original positive finding; missing traces and runtime-integrity failures remain excluded. The parser is a conservative visible-trace audit, not proof against concealed accesses.

## Exclusion inventory

| Cases / configurations | Classification and evidence |
| --- | --- |
| competition-direction-review/v3 | Service infrastructure: terminal HTTP 503, Events 87?88. |
| unified-research-resume/v3; unreadable-subdirectory/v3; work-project-session-history/v3; work-project-start/v3 | Service infrastructure: terminal capacity, respectively Events 57?58, 23?24, 49?50, 9?10. |
| external-result-reconciliation/v2; note-id-kind/v2 | Service infrastructure: terminal capacity, Events 32?33 and 9?10. Their original A1?A5 and A1?A2 zeros are excluded. |
| codex-enforcement-evidence/both | Output-capture infrastructure: `run.json` reports setup/copy, WinError 5, executor exit 0. Also source contamination: v2 Event 37 reads source README/tests; v3 Event 44 reads source host evidence, and Event 47 accesses evaluator source. |
| hook-interpreter-override/v3 | Output-capture infrastructure: setup/copy with access denied after exit 0. Independently contaminated: Event 40 reads source hook wrappers. |
| hook-interpreter-override/v2 | Terminal capacity, Events 33?34; also installed-skill enumeration with actual FullName output, Event 26. |
| cli-hook-literal/v2 | Source contamination: Event 117 executes source `ro.py`, following source initializer/reference reads. |
| codex-host-capabilities/v2 | Source contamination: Event 21 reads source README; Events 25?30 read current hooks/reference/host evidence. |
| credential-storage-redaction/v2 | Source contamination: Event 47 reads source SKILL; later commands use current ro tools after installed-skill searches. |
| fenced-record-examples/v2 | Source contamination: Event 49 reads source hooks reference; Events 48/51/53 read current core/presets/operations. |
| launch-root-binding/v2 | Source contamination: Event 36 reads source README and later source runtime; Event 82 executes source `ro.py`. |
| native-session-slots/v2 | Source contamination: Event 47 reads source `ro.py` and job/state code after installed-skill searches. |
| owned-job-monitor/v2 | Source contamination: Event 33 reads source SKILL, followed by current references and `ro.py` execution. |

These are 18 distinct excluded runs. Some have multiple independent exclusion reasons. No excluded partial result is promoted to a behavioral pass, and a v2 missing capability in a completed run is not called infrastructure.

## Remaining v2 failure inventory

**B** means a released-v2 capability/schema/output gap, not a reason to add v3 instructions. Every original eligible failure is listed; conjunctions fail when a required part is absent. In particular, an uninvoked missing hook cannot earn a positive or exemption pass. Actual executed legacy checker negative controls can satisfy literal absence assertions, but provide no guard-capability evidence without their matching positive controls.

| Case | Failed assertions | Evidence and classification |
| --- | --- | --- |
| ancestor-rename-protection | A1,A2,A3,A5 | rename-probes.json records all hook probes `not_submitted_hook_unavailable`, response/decision null: neither ancestor denial nor sibling non-denial occurred. runs/job-a/job-result.json says `skill_owned_job: false`, so direct subprocess termination is not owned-monitor evidence. v2 lacks these tools; preserved inputs alone (A4) rightly pass. |
| claim-contention | A1-A5 | contention.json has `actual_operation: capability_preflight_only`, native_claim_invoked false, exit codes [2,2], owner null; the barrier coordinates unsupported preflights, not claims. plan.md has `Claim: unclaimed`, zero Claimed fields. v2 has no atomic operational claim mechanism. |
| close-recorded-scope | A1 | close.txt and transcript event 47 record CommandNotFoundException, not a ro close report. Handoff does record an explicit no-follow-up decision, so A2-A3 pass; the missing operational close is a capability gap. |
| competition-direction-review | A1-A4 | agents.md lacks Read bound and plan.md uses Agent A despite Workflow unified; A1's errors are real. discoveries.md D-A-006 records nested `Decision class: direction-review`, not a Kind direction-review record with required decision fields (A2). H-A-07 is a materially different count-distribution/linear family, but no recognized review/schema ties the exit to it (A3). The original five records were rewritten with metadata nested under Reviews; historical preservation fails A4 even though handoff has an H-A-06 event and New plan items H-A-07. This is v2 schema mismatch, not evidence of an absent substantive pivot. |
| competition-preset-transition | A1-A7 | resulting-settings and logs show unsupported preset/external-action flags and exit 2. Inherited/custom/opted-out/legacy settings lack required policy values (A1-A4); no inactive-gate diagnostics (A4-A5). Hook-evaluation files have evaluated false/decision null (A6-A7); absence of an outward action is not observed gating. |
| dangling-instrument-evidence | A1-A3 | results.md records 40 isolated runs. Active mixed Instrument I-A-99, active Result I-A-99 and Rejected on I-A-99 inputs are retained but checker output has generic discovery-format problems or CONSISTENCY OK, never evidence.instrument.dangling ERROR. No guard implementation in baseline. |
| direction-review-grace | A1,A4 | fresh-check.txt and resumed-check.txt both contain only legacy CONSISTENCY OK. No INFO first-review-due finding for fresh, no WARN stale finding after removing pause from the 2020 activation. cadence-audit.md candidly says guard support missing; manually derived due dates do not satisfy actual checker assertions. |
| external-action-order | A1,A2,A3 | Saved handoff uses EA-A-001 and Status accepted, with no canonical X-A-001. Current checker reports missing Read bound, unified/classic mismatch and invalid external ID/fields (A1). The simulator genuinely executed once, but snapshot/final expected X record is absent (A2-A3). Legacy custom reconciliation is not requested typed-ledger behavior. |
| external-malformed-ledger | A2 | validation-report.md says neither attempt produced a wrapper response; first capture itself failed, second got CommandNotFoundException. Duplicate Status is diagnosed manually, never by the absent wrapper. Input preservation and no execution pass separately. |
| external-retry-chain | A1-A8 | scenario-status.json marks every scenario NOT RUN, stub_invocations 0; no attempts.log, receipts or ledger. A1 chain, A2 valid-chain checker, A3 replay, A4 malformed immediate links, A5 invalid ancestry, A6 old prepared after done, A7 duplicated ancestor and A8 whitespace duplicates are all unexercised. Checker exit 2 is missing coordination files, not semantic retry rejection. |
| hook-effective-working-directory | A1-A5,A7 | probe-results.json has requested payloads but all hook_response null and `not_submitted_missing_handler`; denies, allowed scratch path and uncertain-directory warning are absent. Worker registered_as_skill_owned_job false, monitor is direct subprocess wait, and skill_monitor_outcome null. No hook/owned-job implementation in v2. |
| hook-portability | A2,A3,A4 | hook-setup.md describes a generic later authorized dry run, omits Claude Code and both-host trust/event test scope (A2). ro-brief.txt shows command unavailable, no `hooks never ran` status (A3). The supplied bundle has no hooks/ro-hook.sh or hooks/ro-hook.cmd (A4), confirmed by its inventory and saved report. |
| identifier-rollover | A1,A2 | checker-report.txt exits 1 with seven schema incompatibilities; supplemental 26/26 integrity checks cannot replace current checker acceptance. D-A-1001 links Sources D-A-1000/Follow-up H-A-100 but lacks `Status: planned H-A-100`. Wider IDs/data survive; missing typed insight linkage is real. |
| non-ml-replication | A1 | agents lacks Read bound and plan uses Agent A despite unified workflow; current checker has three errors and an instrument-schema warning. The numerical A3 failure is the proven grader fixture defect discussed above, not a second behavioral failure. |
| queue-freeze-delivery | A1,A2,A3 | plan.md retains H-A-01 but uses nested Due rather than Ready by. checks.md records actual legacy checker OK on both requested days; separate FREEZE EXPIRED text is executor arithmetic, not plan.freeze.expired WARN. Queue freeze is stored only in Shared state, not agents.md's required `until` setting. |
| repair-missing-coordination | A2,A3,A6,A8,A9,A10 | run-repair-trials.py inventories only four fixed coordination filenames, so A2 cannot show no other project writes. intake-b is a classic legacy substitute, not retained unified Queue (A3). Its zero-exit legacy checker does not validate the requested scenario (A6). 08-conflict-roster exits 0 and creates A-only plan despite saved roster conflict (A8); 08-recovery-no-agents exits 0 creating handoff rather than refusing missing complete roster (A9); 07-conflict-ordinary-no-settings exits 0 creating replacement agents and losing local rule (A10). These are real baseline repair hazards. |
| saved-policy-roundtrip | A1-A9 | setup-output.txt shows source flags, --save-preset and user:travel-policy unsupported; targets empty, saved-policy.json absent. A1-A3 cannot retain preferences/policies; A4 cannot omit project-specific state from absent preset; A5 no new identity/off/activation settings; A6 hook not evaluated; A7 before/after source hashes both empty, not proof of a successful save; A8 no override target; A9 shipped commands produced no settings provenance. Honest failure reports do not complete roundtrip. |
| unified-research-resume | A1 | Current checker reports missing Read bound plus malformed review metadata. Baseline preserved unified queue and correct result (all other assertions pass), but could not upgrade missing current setting with its legacy tools. |
| unreadable-subdirectory | A1-A6 | receipt-probe-run.txt/transcript event 19 raises ModuleNotFoundError ro_evidence before injected enumeration, ledger creation or receipts. No receipt-probe.json, handoff, receipts hashes exist (A1,A3,A5,A6); external path not reached (A2). Marker absence (A4) is vacuous because no enumeration attempt occurred. This is missing baseline implementation, not runtime infrastructure. |
| v2-rules-upgrade | A1,A3 | Saved agents says Workflow unified but plan remains Agent A, no Claimed; no v3 marker/Profile. Current checker reports settings.workflow.unmigrated. Executor's local adapter/validation passed claim does not establish actual migration; preservation assertions pass. |
| v3-interface-scope | A1-A3 | Actual YAML and final quote are `Orchestrate agent research` and `Initialize Research Orchestrator for this project and resume existing state when present.` They omit work/competition scope (A1-A2) and preset/workflow plus resume-before-initialize order (A3). Correctly quoted old interface is still functionally too narrow. |
| work-project-session-history | A2,A4,A5,A6 | Saved log has separate H-A-01/H-A-02 completions and separate none events, not the single session event with Completed list (A2). Custom Session S-A-001 metadata does not provide the required canonical historical block/Profile transition (A4). Current checker gives agents.rules.edited WARN (A5). queued-plan.md has 15 top-level fields per routine item (A6), consistent with baseline's heavy scored template. Inventory and rejection JSON assertions pass. |


The table above accounts for 84 substantive failures among originally included v2 runs. Recovered exclusions add these 13 failures:

| Case | Failed assertion files | Class and evidence |
| --- | --- | --- |
| direct-install-reviewer | `90-bundled-reference.md` (A1) | B: copied `local-skill/` has nine runtime files and no references/reviewer chain; `install-review.md` explicitly identifies the missing dependencies. Its evidence challenge and identity limits still pass. |
| quick-goal-routing | `90-checker-clean.md` | B: saved checker output rejects the compact Goal shape; the disclosed `rg` fallback genuinely identifies amber-crate and the requested compact item exists, so the other two assertions pass. |
| selection-family-source | `01-same-family.md`, `03-required-family.md`, `04-missing-action.md`, `05-inline-cannot-mask.md` | B: all eleven actual legacy checker executions report OK; none emits required rationale/family findings for active invalid selections. A2/A6 absence controls pass literally, without establishing guard support. |
| work-brief-references | `90-compact-queue.md` | B: each staged item has 15 top-level fields, despite useful brief references, dependency order, preserved scope and honest setup-only closure. |
| work-project-start | `01-checker-clean.md`, `02-work-preset.md`, `03-staged-queue.md`, `06-light-ordering.md`, `07-session-summary.md`, `09-compact-items.md` | B: `agents.md` records an invalid manual-adaptation Preset string, lacks Profile/Workflow/Item size; classic scored items lack unified Claimed shape, use excessive fields, and handoff has separate setup/close events. The brief is preserved, no routine discovery is invented, and the substantive proposed stages cover the three-day task, so those checks pass. |

## Patterns the aggregate hides

The 176 matched assertions contain **100 shared passes, 75 v3-only passes, one shared failure and no v2-only pass**. The sole shared failure is repair preservation evidence. Nine matched cases pass completely in both configurations: analytic-complete-coverage, evaluation-grade-integrity, evaluation-trace-audit, job-monitor-recovery, owned-job-parent-exit, project-language, release-ci-matrix, reviewer-read-only and trigger-measurement-reasons. Keep these as regression checks, but do not claim they demonstrate incremental value in this iteration.

Most positive separation concerns implemented v3 capabilities: atomic claims, typed selection/evidence guards, saved policies, hooks, operational commands and compact work records. Released v2's core describes agent-separated scored queues and full per-item bookkeeping, without the current operational tools. This experiment measures prose and bundled implementation together; it cannot attribute the improvement to prose alone. Baseline negative controls that merely observe no checker warning are less discriminating than controls requiring actual invalid input rejection.

There is one execution per case/configuration. Cross-case standard deviation is not repeated-run variance, and no reliability/confidence claim follows. On matched completed pairs, executor-only duration averages **263.09 s versus 322.80 s**, a **59.71 s** decrease for v3; reported CLI token counts average **44,073.94 fewer** for v3. These are descriptive retained measurements, not unique generated tokens or monetary cost. The benchmark's stored time field mixes original executor-plus-judge durations with executor-only fallback where retrospective grading time is unknown; it is not a homogeneous end-to-end timing comparison. Recovered judgments retain null review duration rather than inventing zero cost.

The original grader's non-ml-replication feedback says numeric, preservation and review-state assertions are absent, even though those scripted checks are present in the combined grade. That feedback came from a judge evaluating only its delegated subset; it is stale coverage commentary, not evidence to duplicate existing assertions. No change to the original case is justified by it.

## Validation

**Both required gates ran and failed only the existing hook-latency test.** `python -m pytest -q`: **2,039 passed, one failed**, 151.66 s; latency p95 **179.8 ms**. `python scripts/validate_release.py`: all release checks passed, with its embedded pytest reporting **2,039 passed, one failed**, 151.42 s; latency p95 **188.6 ms**. Logs and exit status are retained in the analysis workspace. The existing hook-latency test also fails on an unmodified branch-HEAD checkout on the same drive/interpreter: **186.8 ms p95 against 150 ms**; the patched isolated run measured **170.7 ms**. The hook implementation and latency threshold are unchanged. This is a reproduced pre-existing local performance failure; the requested gates are not green.

Four new cases add 22 assertions (51 cases / 297 assertions total). Their exact settings blocks and routing validate; the 547 tracked original case files are unchanged. All 6,303 retained original artifact hashes match. New cases have no post-edit model executions. The static viewer and derived benchmark describe the original executions after adjudication; they do not demonstrate the new preservation instruction's efficacy.
