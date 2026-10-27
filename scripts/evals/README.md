# Behaviour evaluations (P5)

These development tools prepare and grade the case folders in
`skills/research-orchestrator/evals/`. They use Python's standard library.
The coordinator runs the paid Codex sessions outside the builder sandbox.
Both execution and judgement use the configured Codex model unless `--model` is
supplied; no Claude process is used.

The cases retain the exact skill-creator `prompt.md`, `case.yaml`, scaffold,
and `graders/NN-description.md` formats. Every grader file states one assertion
with the required `type: llm`, `focus: trace`, `weight: 1` header. The development
grader routes objective assertions through `checks.py` and its specialized helper
modules. Only assertions explicitly listed in `JUDGED_CHECKS` go to Codex for
source, trace or qualitative comparisons; a `90-` filename alone never selects a
judge. An unmapped assertion is an error, so new file and registry checks cannot
silently become model judgments.

Regenerate the inventory with `python -m scripts.evals.inventory`; paste its output
between the markers below. `python -m scripts.evals.inventory --check` and the test
suite reject stale counts or rows. Assertions and expected outcomes live in each case.

Post-snapshot additions and changed assertions are unexecuted. This inventory describes routing, not measured performance. Routing checks only load case schemas and render this inventory; they do not execute scenarios or graders.

<!-- generated case inventory -->
166 case folders; 891 assertions (522 scripted, 369 judged).
Counts and rows come from the case folders and explicit grader routing; direct artifact predicates are scripted, while judgments review qualitative or multi-step trace evidence.

| Case | Scripted | Judged | Input files |
| --- | ---: | ---: | ---: |
| active-record-history | 3 | 6 | 2 |
| active-setting-pointers | 6 | 0 | 1 |
| analytic-complete-coverage | 7 | 1 | 2 |
| ancestor-rename-protection | 5 | 0 | 4 |
| atomic-compute-reservation | 3 | 0 | 1 |
| automatic-session-registration | 6 | 0 | 1 |
| away-slot-default | 0 | 8 | 6 |
| brace-operand-boundary | 0 | 6 | 1 |
| checker-broken-install | 0 | 4 | 1 |
| checker-summary-integrity | 4 | 0 | 1 |
| claim-contention | 8 | 0 | 1 |
| cli-hook-literal | 5 | 0 | 2 |
| close-recorded-scope | 1 | 2 | 1 |
| codex-enforcement-evidence | 7 | 1 | 1 |
| codex-host-capabilities | 1 | 11 | 1 |
| codex-moved-registration | 0 | 4 | 1 |
| compact-checker-summary-cache | 0 | 3 | 1 |
| compact-preset-settings | 5 | 0 | 1 |
| compact-render-metadata | 3 | 2 | 1 |
| competition-direction-review | 4 | 3 | 6 |
| competition-external-pattern-setup | 0 | 3 | 1 |
| competition-platform-defaults | 0 | 4 | 1 |
| competition-preset-transition | 7 | 0 | 1 |
| competition-runtime-observations | 0 | 3 | 1 |
| conditional-project-hook-matchers | 4 | 1 | 1 |
| control-noise-floor | 4 | 1 | 1 |
| credential-storage-redaction | 8 | 0 | 9 |
| custom-work-defaults | 5 | 0 | 1 |
| dangling-instrument-evidence | 10 | 0 | 2 |
| decision-changing-draft | 0 | 3 | 1 |
| decision-class-integrity | 0 | 6 | 1 |
| default-cli-shim | 4 | 0 | 1 |
| direct-install-reviewer | 2 | 4 | 2 |
| direction-review-grace | 4 | 0 | 1 |
| directory-change-binding-certainty | 4 | 0 | 3 |
| evaluation-grade-integrity | 9 | 0 | 2 |
| evaluation-trace-audit | 5 | 1 | 1 |
| evaluation-trace-code-operands | 8 | 0 | 1 |
| evaluation-transport-evidence | 6 | 0 | 1 |
| exclusive-license-routing | 0 | 3 | 1 |
| explicit-multislot-selection | 4 | 0 | 1 |
| external-action-order | 4 | 1 | 7 |
| external-descendant-deadline | 5 | 0 | 7 |
| external-generated-prefix | 0 | 5 | 1 |
| external-historical-duplicate-id | 5 | 0 | 7 |
| external-malformed-ledger | 3 | 0 | 7 |
| external-result-reconciliation | 8 | 0 | 7 |
| external-retry-chain | 10 | 0 | 3 |
| external-withdrawn-history | 0 | 5 | 4 |
| external-wrapper-options | 4 | 1 | 1 |
| failed-runner-protection | 3 | 0 | 2 |
| failed-runner-slot-ownership | 0 | 4 | 1 |
| fenced-record-examples | 10 | 0 | 6 |
| foreground-job-wait | 0 | 4 | 1 |
| general-reference-vocabulary | 0 | 3 | 2 |
| hook-basename-dispatch | 0 | 3 | 1 |
| hook-edit-warning-fast-paths | 0 | 4 | 1 |
| hook-effective-working-directory | 7 | 0 | 4 |
| hook-interpreter-override | 6 | 0 | 1 |
| hook-latency-budget | 7 | 0 | 1 |
| hook-portability | 4 | 1 | 1 |
| hook-project-discovery | 0 | 4 | 1 |
| hook-root-probe-paths | 0 | 6 | 1 |
| hook-root-termination | 0 | 5 | 1 |
| hook-runtime-deadline | 3 | 0 | 1 |
| hook-runtime-shortcuts | 5 | 1 | 1 |
| hooks-clear-resume | 0 | 3 | 1 |
| hooks-post-cache | 0 | 4 | 1 |
| hooks-tool-dialect | 0 | 4 | 1 |
| host-detection-isolation | 0 | 6 | 1 |
| host-lifecycle-probe-evidence | 2 | 0 | 1 |
| host-name-detection | 0 | 3 | 1 |
| host-runner-diagnostics | 3 | 1 | 1 |
| host-scratch-inheritance | 0 | 4 | 3 |
| host-trust-scope-handoff | 0 | 5 | 1 |
| identifier-rollover | 4 | 0 | 6 |
| idle-direction-cadence | 0 | 5 | 1 |
| important-stage-review | 6 | 0 | 7 |
| installed-capability-matrix | 0 | 6 | 1 |
| installer-edit-policy-routing | 0 | 9 | 1 |
| installer-host-survival | 4 | 0 | 1 |
| installer-plugin-deduplication | 6 | 0 | 1 |
| installer-repository-root | 0 | 5 | 1 |
| installer-runtime-selection | 5 | 0 | 1 |
| job-monitor-recovery | 6 | 0 | 1 |
| launch-free-slot | 4 | 0 | 1 |
| launch-item-ownership | 0 | 8 | 4 |
| launch-root-binding | 6 | 0 | 2 |
| launch-target-validation | 1 | 4 | 7 |
| legacy-same-host-preservation | 0 | 7 | 4 |
| literal-cd-command-chain | 4 | 1 | 1 |
| local-single-host-first-session | 0 | 3 | 1 |
| milestone-state-validation | 3 | 0 | 1 |
| minimal-quick-self-guidance | 5 | 0 | 1 |
| native-session-slots | 10 | 0 | 2 |
| neutral-interface-and-hook-guide | 0 | 6 | 1 |
| neutral-new-decision-records | 6 | 0 | 2 |
| non-compute-exclusive-routing | 0 | 4 | 1 |
| non-ml-replication | 7 | 1 | 6 |
| note-id-kind | 1 | 1 | 1 |
| owned-job-monitor | 5 | 1 | 5 |
| owned-job-parent-exit | 5 | 0 | 1 |
| owned-job-supervisor-crash | 7 | 0 | 2 |
| phase-clock-scaffold | 0 | 4 | 1 |
| plugin-policy-subscription-notice | 0 | 4 | 1 |
| plugin-project-policy-supplements | 0 | 8 | 1 |
| plugin-shim-availability | 5 | 1 | 1 |
| post-close-review | 2 | 4 | 5 |
| posttool-unchanged-fast-path | 4 | 0 | 2 |
| pre-push-interpreter-recovery | 4 | 0 | 1 |
| project-language | 8 | 2 | 5 |
| public-snapshot-reconstruction | 3 | 2 | 1 |
| publication-archive-boundary | 5 | 2 | 3 |
| publication-destination-history | 1 | 4 | 1 |
| publication-receipt-gate | 0 | 4 | 2 |
| publish-deadline-recovery | 2 | 3 | 1 |
| publish-gate-startup-notice | 0 | 5 | 1 |
| publish-hook-timeout-recovery | 0 | 9 | 1 |
| queue-freeze-delivery | 4 | 0 | 1 |
| queue-ordering-validation | 3 | 0 | 1 |
| quick-detected-setup | 1 | 4 | 1 |
| quick-goal-routing | 5 | 0 | 1 |
| quick-to-solo-preserves-live-queue | 0 | 7 | 2 |
| read-hook-opt-in | 0 | 4 | 1 |
| receipt-policy-boundaries | 4 | 0 | 2 |
| record-clock-tolerance | 0 | 3 | 1 |
| release-ci-matrix | 5 | 3 | 1 |
| release-structural-mode | 0 | 7 | 4 |
| repair-missing-coordination | 12 | 0 | 1 |
| repair-snapshot-scope | 5 | 0 | 3 |
| replication-coherent-controls | 4 | 0 | 5 |
| research-direction-scope | 3 | 0 | 1 |
| research-queue-optional-summaries | 9 | 0 | 1 |
| retained-output-export | 3 | 0 | 4 |
| review-session-chronology | 5 | 1 | 3 |
| reviewer-identity-validation | 3 | 0 | 2 |
| reviewer-read-only | 1 | 5 | 4 |
| saved-policy-roundtrip | 9 | 0 | 1 |
| scoreless-cross-host-takeover | 0 | 7 | 1 |
| selection-family-source | 6 | 0 | 1 |
| session-resource-resume | 0 | 3 | 1 |
| session-slot-reminder | 0 | 4 | 1 |
| setup-json-answers | 0 | 6 | 1 |
| shared-git-hook-ownership | 0 | 4 | 1 |
| shared-resource-routing | 0 | 4 | 1 |
| shipped-example-health | 3 | 0 | 1 |
| slot-reclaim-choice | 0 | 4 | 6 |
| solo-queue-exclusive-resource | 3 | 1 | 1 |
| stage-decision-review | 5 | 1 | 6 |
| stale-slot-question | 0 | 7 | 6 |
| standing-rule-lineage | 0 | 5 | 1 |
| stop-absent-job-registry | 0 | 3 | 1 |
| stop-once-per-job | 5 | 0 | 1 |
| trigger-measurement-reasons | 9 | 0 | 1 |
| unicode-job-errors | 2 | 2 | 1 |
| unified-research-resume | 4 | 1 | 6 |
| uninstall-flag-conflict | 3 | 0 | 1 |
| unreadable-subdirectory | 7 | 0 | 3 |
| v2-rules-upgrade | 4 | 1 | 5 |
| v3-interface-scope | 2 | 1 | 1 |
| work-brief-references | 2 | 2 | 1 |
| work-migration-scheduling | 3 | 0 | 1 |
| work-multiple-stage-decisions | 0 | 8 | 6 |
| work-project-session-history | 6 | 0 | 2 |
| work-project-start | 8 | 1 | 1 |
| work-summary-omission | 4 | 0 | 1 |
<!-- end case inventory -->

`reviewer-read-only` supplies a copy of the root-level Claude reviewer as an input;
a regression check keeps it identical to the shipped agent. The skill-only Codex
runtime does not include plugin agents. This case permits read-only shell file
inspection in place of Claude's Read/Grep/Glob tools and tests verdicts and lack
of mutations; it does not establish live Claude tool enforcement.

## Run → grade → aggregate → view

Run these PowerShell commands from the repository. The paths below are only in
developer tooling: the runner injects the selected skill and Python paths into
each prompt, and case files contain no machine-specific paths.

```powershell
$python = '<path to python.exe>'
$workspace = Join-Path (Split-Path (Get-Location)) 'research-orchestrator-workspace'
$creator = Join-Path (Split-Path (Get-Location)) '_skill-creator'
$skill = (Resolve-Path 'skills/research-orchestrator').Path
$iteration = 1
$env:PYTHONUTF8 = '1'

# Optional local format check: no sessions and no workspace writes.
& $python scripts/evals/run_evals.py --iteration $iteration --validate-only

& $python scripts/evals/run_evals.py --iteration $iteration --workspace $workspace --skill-dir $skill --python $python --configs with_skill old_skill --jobs 4
& $python scripts/evals/grade_evals.py --iteration $iteration --workspace $workspace --skill-dir $skill --skill-creator-dir $creator --python $python --configs with_skill old_skill --jobs 4

$results = "$workspace/iteration-$iteration"
& $python scripts/evals/aggregate_evals.py $results --skill-name research-orchestrator --skill-path $skill
& $python "$creator/eval-viewer/generate_review.py" $results --skill-name research-orchestrator --benchmark "$results/benchmark.json" --static "$results/review.html"
```

Check each command's exit status before continuing. Execution returns nonzero for
failed sessions; their partial artifacts remain available for grading. Grading
returns nonzero for contamination and harness/judge errors; ordinary failed
assertions are valid evaluation results. Aggregation reports exclusions in
`benchmark.json` (`excluded_runs`), `benchmark.md`, and stdout, and exits nonzero
when any run is excluded. Contaminated runs and runs with an `error` or `excluded`
flag in `grading_status.json` never enter the statistics, even if `grading.json`
contains a numeric score. Judge timeouts and malformed responses are reported
with their reason and remain excluded until successfully regraded. Invalid status
JSON is also excluded; legacy grades without a status file remain supported.
Recorded launch and setup/copy failures are infrastructure exclusions even when
stale grades contain scores, because incomplete captured evidence cannot establish
the task outcome.
Use this local aggregator rather than the upstream aggregator, which does not
understand these exclusions.
Inspect `grading_status.json` before accepting a benchmark. Execution `run.json` and
`grading_status.json` record the requested model and the resolved model when
reported by Codex; unavailable resolution remains `null`. The local aggregator
uses the recorded model provenance.

Per-configuration summaries include all valid runs for that configuration.
`run_summary.delta` compares **with_skill minus old_skill** only for cases with
valid runs in both configurations. Coverage is reported as matched / total cases
in `metadata.comparison` (`matched_cases`, `total_cases`), benchmark notes (also
shown by the viewer), Markdown, and stdout. Total cases include all discovered
cases for either comparison configuration, including excluded or missing
counterparts. With no matched cases, all delta metrics are `null`. Each metric
uses only pairs where both measurements are known, so missing token counts cannot
create a comparison between different case subsets. Existing skill-creator run,
summary, and delta fields retain their viewer-compatible structure.

The runner pins release 5.1.0 (v2) at commit
`713088d79745589b053ae02996670dc7147a8ee1` and uses `git archive` with the
historical subtree in `baseline.py` to extract the released skill into
`<workspace>/old-skill-snapshot/skills/<historical-skill-name>`. It records the
commit and content digest in `old-skill-snapshot/snapshot.json`. Fresh snapshots,
reused snapshots, and snapshots selected with `--old-skill-dir <path>` must match
the pinned content digest; any mismatch stops the run.

`--case <case-name>` can be repeated to select cases. `--configs with_skill` or
`--configs old_skill` selects one configuration. `--jobs` limits concurrent
sessions (default 4). `--codex <native-executable>` overrides CLI discovery;
Windows npm shims are resolved to their bundled native executable so prompts are
not interpreted by a shell. `--model <name>` overrides the configured model;
omit it to leave model selection to Codex. When a comparison requires a particular
model, pass that option to both coordinator commands. `--timeout` overrides the
timeout per execution attempt or judgement; execution otherwise uses each case's
600-second setting. `max_turns` and
`allowed_tools` remain skill-creator CLI metadata, not unsupported Codex flags.

`--retries N` allows up to N fresh execution retries per case/configuration
(default 3, at most four attempts; 0 disables retries). Only failed
attempts with Codex transport diagnostics in `events.jsonl` or `stderr.txt` qualify:
`stream disconnected before completion`, `Upstream websocket closed before
response.completed`, an exhausted `Reconnecting... N/N` counter, or a terminal
429 / rate-limit / usage-limit error. Rate limits use `failure_category: rate_limit`;
disconnects retain `transport`. Event diagnostics
must be errors/warnings, not quoted agent text or command output. A reconnect still
in progress, timeouts, ordinary task failures, and
contaminated runs are never retried. Successful executions are not retried even
when they logged a disconnect. Each retry launches a new `codex exec` session with
a new temporary root, pristine input and runtime staging, and a new evidence broker;
it never resumes the disconnected session. The usual contamination audit runs
before the retry decision. Usage limits, 429, model-capacity and 503 failures allow
three fresh-session retries before waiting for the stated reset. Further launches
share the cooldown, using 60, 120, then 240 seconds of backoff when no reset is given.
A longer Retry-After delay takes precedence over that cap. Already running sessions may finish; `--jobs` still
bounds concurrency. The cooldown is shared within one runner process.

Every transport-failed attempt is retained under
`<run dir>/attempts/attempt-<n>/` (numbering starts at 1), including the terminal
attempt when retries are exhausted or disabled. Archives contain all attempt
artifacts, including `run.json`, events, stderr, transcript, timing, outputs, and
broker evidence. The run directory's ordinary artifacts and timing reflect only
the last attempt. `run.json` records the retry limit in `retries`, the current
attempt's `disconnect_evidence`, `rate_limit_evidence` (source file/line and diagnostic
message), `retry_delay_seconds`, and an
`attempts` list with each attempt's number, status, timestamps, error, disconnect
evidence, and artifact path relative to the run directory (`.` for an unarchived
last attempt). Grading and aggregation consume only the last attempt and ignore
the `attempts/` archives; prior attempts' time and tokens remain in their archives.

Source-repository audit findings distinguish successful reads from attempted,
failed, or missing-path reads. Only a successful read of a real source file is
contamination; failed guessed paths remain visible as noncontaminating findings.
Paths use component boundaries and the command's working directory, including
literal shell directory changes.

Choose a new iteration number for a rerun. The runner refuses to overwrite a run.
All selected case/configuration pairs enter the same worker pool, each with a
fresh temporary project copied from `files/` and stdin disconnected. Each run gets
a separate runtime skill copy with read-only attributes, excluding `evals/`, tests, fixtures, and
caches. Temporary roots are under `<workspace>/_runs`, outside the hidden Windows
user profile. Both the interpreter directory and `<run root>/skill` receive explicit
`--add-dir` grants so the separate Windows sandbox user can read them. These grants
are writable; the runtime keeps its read-only attributes as a first barrier. The
runner records its content digest before execution and verifies it before cleanup,
saving both digests in `run.json` under `isolation.runtime_integrity`. A changed,
missing, or unreadable runtime marks the run `contaminated` with reason
`runtime skill modified`, excluding it from grading and aggregation. Shared skill
directories receive no writable grants. Case helpers, temporary files, and both
sides of the evidence mailbox live inside the project. The executor inherits the
real `CODEX_HOME`, `HOME`, and `USERPROFILE`
without replacing them. The elevated Windows sandbox stores its one-time setup
in the Codex home's `.sandbox/`, `.sandbox-bin/`, and `.sandbox-secrets/` directories.
A fresh home forces another elevated setup, which fails non-interactively with
`ShellExecuteExW` error 1223 (elevation cancelled). `TMP`, `TEMP`, `TMPDIR`, and
`RESEARCH_ORCHESTRATOR_HOME` remain inside the temporary project. `--ignore-user-config`,
`--ignore-rules`, `--ephemeral`, and configuration overrides suppress inherited
instructions, skills, plugins, hooks, and memory. Only allowlisted model/provider
settings and `windows.sandbox` are retained from `config.toml`. Dropping the latter
makes the Windows CLI downgrade workspace-write to read-only and reject shell
commands with approval policy never. The runner never reads, copies, or moves
credential files. Existing Codex home state remains shared with the host, including
authentication and sandbox state. Installed skills are disabled by options and
detected by the audit, not removed. `run.json` records the isolation settings and
remaining host dependencies, including `isolation.host_context`: the real home,
effective Codex home, installed skill roots, and global `AGENTS.md` path,
`size_bytes`, and `empty` status captured before execution. Only the file size is
checked; its contents are never read or printed by the harness. A missing global
file has `exists: false`, `size_bytes: null`, and `empty: null`. The sandbox is
not a read jail: source/eval files remain readable if deliberately searched, though
they are excluded from the runtime copy and prompt. After every execution, an
audit checks command and file/tool-access events in `events.jsonl` and the event
sections of `transcript.md`. Confirmed source-file reads, and access attempts to
hidden `evals/` or `graders/` directories, another workspace run, or an unstaged
baseline snapshot mark `run.json` as `contaminated`. So do accesses to the real home's
`~/.codex/skills`, `~/.agents/skills`, or `~/.claude/skills` roots (and an overridden
Codex home's `skills` directory), or a global `AGENTS.md` that was non-empty at
launch. The audit resolves absolute and relative paths, tilde paths, and common
home environment-variable spellings using the recorded host paths. Prompt and final-message prose do not
count as access. Reserved directory names inside assigned roots are checked
relative to those roots; an `evals` ancestor outside the assigned root does not
make its ordinary runtime files forbidden. Grading and aggregation recheck the
saved trace using the original host paths and global file size. Previous
contamination flags remain unless every positive finding is reproduced and
disproved by the trace. Recoverable path errors include an assigned file under an
`evals` ancestor, an entire Python program argument mistaken for a path, and a
guarded search for absent ancestor `AGENTS.md` instructions with recorded output
confirming no read. Embedded protected path operands still count. Missing traces,
runtime mutations and independent exclusions remain excluded. Grading records
any recovery before computing fresh grades; an old exclusion placeholder never
becomes a passing score by itself.
Contaminated evidence receives no grade or benchmark score. The audit detects
visible accesses, including failed attempts; it cannot
rule out hidden reads by opaque programs or paths assembled entirely at runtime.
Temporary directories are removed after outputs are copied; cleanup clears
read-only attributes and retries. Cleanup
problems are recorded separately and do not turn a successful session into a
failed evaluation. The fixtures perform only local simulations and short jobs.

The same configuration isolation applies to the read-only judge; its diagnostics
and cleanup problems are recorded in `grading_status.json`. `codex exec --help`
documents `--add-dir` as a writable grant; only the executor uses it, for Python
and the staged runtime skill. The [Codex sandbox policy source](https://github.com/openai/codex/blob/main/codex-rs/protocol/src/protocol.rs)
describes full-disk reads, but the elevated Windows sandbox user's filesystem
permissions can still require explicit grants for paths outside the project.
The discovery overrides follow the [Codex configuration schema](https://github.com/openai/codex/blob/main/codex-rs/core/config.schema.json).

## Saved evidence and grading

```text
<workspace>/iteration-N/<case>/
  eval_metadata.json
  with_skill/                  # old_skill/ has the same layout
    outputs/                   # project files, hidden .ro/, final.md
    events.jsonl               # raw Codex JSON events
    transcript.md              # readable events and final response
    stderr.txt
    run.json
    evidence.jsonl             # harness-only execution log for evidence cases
    helper-executions.jsonl    # append-only invocation log, including denied attempts
    evidence/                 # canonical inputs, snapshots, results, receipts
    timing.json
    checker.txt
    judge-events.jsonl
    judge-stderr.txt
    judge-final.json
    grading_status.json
    grading.json
    attempts/                 # disconnected failures, excluded from grading/aggregation
      attempt-1/              # full artifacts from that attempt, same execution layout
```

`eval_metadata.json` sits beside the configuration directories and contains the
prompt without its settings block and the exact assertion sentences. The grader
uses the current branch's checker for **both** configurations: both must meet the
same v3 acceptance criteria. Missing v3 capabilities in the released skill are
expected to show up as failures. The copied input projects deliberately include
unified and guard records in cases that exercise those v3 behaviours.

For claim and external-action cases, the supplied helper requests a harness-side
execution through a project mailbox. The broker appends every invocation, including
denied `--capture` attempts, to `helper-executions.jsonl` outside the writable project
before dispatch. Fixed capture code and its per-run authorization capability stay
inside the broker process; executor helpers expose no capture implementation.
The broker appends completion evidence and saves canonical captures outside the
project, then publishes output copies to `.eval-evidence/responses/<request>/`
inside the project, with the receipt last. Helpers read only these mailbox copies;
grading compares project outputs against the protected originals. The evidence
directory and canonical helper sources need no executor grant.
The action simulator saves the ledger before producing a result; the grader
compares project outputs against the protected captures and requires a successful
helper execution and exactly one authorized invocation. Direct capture before a
ledger/claim followed by a normal request fails. Fabricated results and post-action
snapshots fail. The job
simulator samples active ownership during execution, and the grader also checks
the job registry and actual command events. A prompt or final message merely
mentioning a claim, monitor, or close is not execution evidence. The migration
check compares the raw bytes of the user-owned rules region.

The PostToolUse measurement case uses the same broker. Its supplied client requests
one fixed collector against the harness-selected runtime; the collector counts
coordination-file opens and child launches, then exercises changed-record and
pending-warning controls. The harness retains the runtime and collector identities,
results and fixture files outside the writable project. Every measurement assertion
requires that capture and matching output copies, so plausible JSON without an
execution receipt fails. These counts are local adapter evidence, not host trust or
latency measurements. The work setup brief has a separate raw-byte preservation
check: changing only its line endings fails that promise even though general helper
identity hashes remain checkout-independent.

The resume case records its discovery's `Finding` as structured JSON and compares
those values with the computed summary. Citing a correct summary while reporting
a different result does not pass.

The v2 input retains released structure and user policy, with generated example
identities anonymized. Its initial `agents.rules.edited` warning is intentional;
the prompt authorizes saving that guidance before regeneration. The competition
input intentionally starts with saturation and missing-direction warnings.

All scripted assertions run against the saved project. One read-only Codex
session per run receives the remaining assertions and the copied
`agents/grader.md` instructions. It returns JSON in its final message; the host
grader validates and writes `grading.json`. Every expectation uses exactly
`text`, boolean `passed`, and nonempty `evidence`. Missing or malformed evidence
fails closed. A failed executor cannot earn a passing run from unchanged inputs.

`timing.json` records executor wall time and tokens from `turn.completed` JSON
usage, or `null` when usage is unavailable. `grading.json` separately records
executor time, judge time, and their sum, which the supplied aggregator uses as
its time metric. The local aggregator excludes unknown token usage from token
statistics and preserves `null` when no measurement is available.
Its static viewer hides `.ro/` directories from file listings; those artifacts
remain on disk and their relevant evidence appears in grading results.

After aggregation, the coordinator should inspect per-assertion failures,
assertions that pass both configurations, timing/token tradeoffs, and the static
viewer before deciding whether to revise the skill. Give the benchmark and viewer
to both independent final Codex evaluators. This tooling does not perform
the final evaluations or trigger optimisation.

## Fast tests and release gates

### Trigger selection and installed-host probes

The coordinator-only [trigger runner](../trigger/README.md) stages only `SKILL.md`,
isolates installed copies with invocation-local selectors and an access audit, and
reports repeated 60/40 development/held-out precision and recall. Run
`& $python scripts/trigger/run_trigger_eval.py --output ../research-orchestrator-workspace/trigger/current --repeats 3 --jobs 4`;
add `--description candidate-description.txt` and a new output directory for a candidate.
The installed-hook probes are `& $python scripts/host/codex_hook_dryrun.py` and
`& $python scripts/host/claude_hook_dryrun.py`; add `--dry-print` to either for
commands only, with no writes or host launch. Each uses fresh synthetic fixtures
and invocation-only trust/plugin loading, then writes raw events and attributed
decisions to `docs/host-dry-runs/<host>-<UTC-date>.md`. Missing hook evidence stays
inconclusive; the report does not infer enforcement from a successful tool call.
Host scratch projects default to the sibling workspace's `_host-runs`; use
`--temp-parent <accessible-directory>` when the Windows sandbox needs another location.
Their tests (`tests/test_trigger_eval.py`, `tests/test_host_dryrun.py`) mock hosts;
the builder does not run model sessions or edit the skill/case folders.

```powershell
& $python -m pytest -q tests/test_eval_runner.py tests/test_eval_grader.py tests/test_eval_models.py tests/test_eval_aggregate.py
& $python -m pytest -q
& $python scripts/validate_release.py
```

The helper tests mock Codex subprocesses. Case-format validation, arithmetic,
raw-byte migration checks, and malformed-grading negative controls are local and
fast; none launches an evaluation session.

Aggregation matches verdicts to the frozen case assertions and, when available,
the source case. Each assertion needs one Boolean verdict and nonblank evidence;
counts and pass rates are recomputed and checked against the supplied summary.
Rates outside 0–1 and measurements that are not finite nonnegative numbers are
excluded with reasons. Missing measurements remain null; corrupt numeric values
cannot abort the benchmark or distort its means.
Missing, duplicate, unknown, or inconsistent verdicts are excluded. Archived cases
absent from the default source can use their frozen metadata; an explicit
`--skill-path` requires the matching source case. A missing legacy grading-status
file never bypasses these checks. The replication check also reruns independently
changed observations and critical values, so a correct constant output cannot
substitute for reading both inputs.
