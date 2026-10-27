# Evidence index

Historical scores below describe saved executions. Deterministic tests validate implementation, formats and examples; further behaviour runs and trigger reruns were deferred for 6.0.0 by the recorded owner decision; persisted Codex `/hooks` trust remains unverified. New repair cases are unexecuted, and so are the cases added in 7.0.0 (`history-archive`, `tool-registry` and the new `brief-review-cache` variants).

| Measurement | Result | Runtime digest / identity | Grader / evidence |
|---|---|---|---|
| [Iteration 5](evidence/iteration-5.zip) | Earlier outputs retained | Historical snapshot; archive manifest hashes | Original and retrospective grades separately retained |
| [Targeted seven cases](evidence/final-benchmark.md) | v3 38/38 assertions | `46305f89dd84ccff3a7b94673da94894e1fdd7121f5b13d31d2f2f7d91b888c9`; baseline B | Builder; independent setup subset; [archive](evidence/final-paired.zip) |
| [Iteration 6 original](evidence/iteration-6.zip) | v3 case mean 87.87%; 43 included runs | Pre-final snapshot; no unified runtime digest | Original grades; 19 exclusions across configurations |
| [Iteration 6 adjudication](iteration-6-analysis.md) | v3 231/232 (99.57%); 40 included runs | Same saved executions | Unblinded builder and independent analyst checks; 18 exclusions |
| Common-output subset | v3 6/6; v2 6/6 | Same executions; baseline B | Six identical saved output-only assertions |
| [Native builder attempts](evidence/builder-coverage.md) | 0/47 valid paired cases at that inventory | Before/after digests in [coverage JSON](evidence/builder-coverage.json) | Independent exclusion audit |
| [Trigger measurements](../trigger/results.md) | Historical 15/20; current-2 20/20 majority queries, 59/60 attempts | Pre-rename skill; digests in source record | First-selection detector and retained audit |
| [Claude Code probes](../host-dry-runs/claude-code-2026-10-27.md) | 6/6 verified on 2026-10-27 | Claude Code 2.1.287, haiku; supplied candidate | Runner diagnostics, tool results and protected-file state |
| [Codex probes](../host-dry-runs/codex-2026-10-27.md) | 6/6 verified on 2026-10-27 with per-invocation trust | Codex CLI 0.154.0; supplied dated runtime | Runner diagnostics and side effects; `--dangerously-bypass-hook-trust` |
| [Windows hook latency](hook-runtime-cost-2026-10-27.md) | Historical 225 ms p95 budget | Windows Python 3.12; [earlier](evidence/hook-latency-2026-10-27.json) and [Round 7 samples](evidence/hook-latency-r7-2026-10-27.json) | Warmed batches, median of three nearest-rank p95s |
| CI hook p95 | Windows 57–60 ms, Ubuntu 45–47 ms, macOS 49–54 ms (batch p95 of 20 calls, three batches; 2026-10-27, release 6.0.1 CI) | Each CI checkout, Python 3.12 | Dedicated installed-hook test and per-OS artifact |

Iteration 5 preserves earlier outputs and verdicts; exported member hashes identify evidence, not an inferred current runtime. No new measurement is attributed to that archive.

The targeted seven-case comparison includes v3 capabilities absent from v2 and shared configuration sessions. It establishes historical outcomes, not an overall quality or isolation comparison. Baseline B is release 5.1.0, revision `713088d79745589b053ae02996670dc7147a8ee1`, content digest `b2c01f24428b04d8a31225e0f7a3aaed0cc819b52715292c165a264a943588c4`.

Iteration 6 original grades retain infrastructure and grader defects. The adjudication changes verdicts on the same executions; [regrade procedure](evidence/regrade-procedure.md) and [sanitized task outputs](evidence/iteration-6-outputs.json) make that distinction inspectable. Sum the 40 included v3 `summary.passed` and `summary.total` values to reconstruct 231/232 (99.57%); this assertion-weighted score differs from the earlier matched-case mean of 99.71%.

The only common-output comparison selects `analytic-complete-coverage` A3, `non-ml-replication` A2/A8, and `project-language` A5/A6/A8 (one-based positions). These check arithmetic, interpretation, input preservation, reusable code and reply language without requiring v3 records or tools. Read `adjudicated/<case>/<configuration>/grading.json` in iteration-6.zip and sum `passed` for those positions: both `with_skill` and `old_skill` pass 6/6. The identical assertion texts form a narrow, retrospective, non-discriminating subset; no task or grader was rerun.

Native builder attempts completed no valid paired tasks. Their exclusions preserve original errors, timings and runtime digests without pass credit or performance deltas. The [current inventory](../../scripts/evals/README.md) includes later, unexecuted cases and differs from the historical 47-case inventory.

Trigger results measure selection on one host/query set, not task completion or the renamed release. Later incomplete repeats remain exclusions.

Claude's six expected decisions come from the supplied diagnostics-based candidate record. Its prior inconclusive summary was moved intact to the owner-held archive (not part of the release) at `ro-evidence-archive/2026-10-27c/docs/host-dry-runs/claude-code-2026-10-27.md`. These results do not validate subsequent runtime repairs or every warning UI.

Codex's persisted `/hooks` trust route was not exercised. Ordinary `codex exec` must not be relied on for hook enforcement until trust is established; trusted invocations can enforce listed checks. Rely on `ro` commands and Git pre-push; see [capability evidence](../../skills/research-orchestrator/references/hooks-capabilities.md).

The current [local fast-path samples](evidence/hook-fast-paths.json) support the 150 ms p95 gate for installed wrappers and in-process checks. The direct subprocess check requires hook p95 minus bare-interpreter p95 < 150 ms and an absolute hook p95 < 300 ms, separating machine-dependent startup cost from hook work. Hook and baseline use `python -E -S`, two warm-ups and the median of three 20-sample nearest-rank p95s; the baseline runs `-c "pass"`. With `RO_LATENCY_REPORT`, the JSON retains installed-watchdog metrics at the top level and adds `subprocess` with hook p95, baseline p95, their difference, both budgets and batch values. [Measurement details](hook-latency-gatefix.md) distinguish these layers from checker-only cache timing.

Local latency records invoke wrappers and runner code without a host application. They establish only their recorded Windows layers and cache/load conditions; older measurements are not a controlled speedup baseline. The 6.0.1 CI artifacts record the installed-hook p95 on each runner; they are single runs on shared CI machines, not a controlled comparison.

Earlier superseded reports remain in owner-held archives, not part of the release, at `ro-evidence-archive/2026-10-27b`, with relative paths and pre-redaction hashes preserved. No report was deleted.

## Release repair provenance

The 6.0.0 changelog groups user-visible fixes by area. Review-round attribution and validation scope live here so release notes do not imply that a repaired runtime was measured again. Round-10 repairs from the Codex reviewer and the release review preceded the Claude reviewer's reconciliation; their unexecuted repair cases add coverage specifications, not behavioural pass credit.

Host harness repairs prepare fixtures before launch, inherit scratch-directory permissions and move completed runs to `done/`. Mocked regressions cover those changes; the dated Claude and Codex records above remain the host evidence, with no claim for later repairs. Windows wrapper timings and pending three-OS CI artifacts retain the separate scopes listed above.

The retained iteration-6 task-output export contains sanitized produced files, saved grades and timings, with source/export hashes. Original and adjudicated grades and the reconstruction procedure support the historical headline without publishing transcripts. Artifact assertions use scripted checks; qualitative judgments remain separate. Raw host reports, evidence archives and embedded viewers stay in the owner-held archives named above; public copies retain sanitized decisions, placeholder commands, grades and withheld-source hashes.

Publication validation inspects archive members and manifests for private paths, account names, native identifiers and raw event streams. `validate_release.py --skip-tests` establishes structural validation only, while the default command includes the full test gate; the release-candidate receipt row below records that gate. Receipt identities are session assertions, and a valid receipt does not prevent later artifact mutation.

## Release candidate test receipt

The coordinator fills this row after the final local run against the publication commit. Keep placeholders until that run; earlier candidate results do not establish this receipt. At publication, set `RO_RELEASE_RECEIPT_REQUIRED=1` when running `python scripts/validate_release.py`; the gate then requires all five fields without placeholders. Ordinary development validation permits the pending row.

| Date | Interpreter | Pytest summary | validate_release result | Commit |
|---|---|---|---|---|
| 2026-10-28 | CPython 3.12 on GitHub Actions (windows-latest 3.12.10, ubuntu-latest 3.12.15, macos-latest 3.12.10) | windows 3,931 passed; ubuntu 3,812 passed and 118 skipped; macOS 3,812 passed and 118 skipped; 2 `latency` tests deselected and passed in the separate CI step on each runner (CI run 40558638530); local Windows Python 3.12.6 3,931 passed and both `latency` tests passed | `VALIDATION: PASS` on all three runners and locally | commit `84b9178` (the 7.0.0 candidate; only this row differs) |

## Dated host scope and interpretation

Codex CLI 0.154.0, model `gpt-6.1-sol`, declared `windows/powershell`: all six supplied probes were verified on 2026-10-27 with **per-invocation hook trust**, using `--dangerously-bypass-hook-trust`. The persisted `/hooks` trust route was not exercised. Ordinary invocations without established hook trust are not an enforced safety layer; rely on `ro` commands and Git pre-push. The record is `docs/host-dry-runs/codex-2026-10-27.md`; it does not verify later runtime edits, Linux, other events or visible warning delivery in every host UI.

Claude Code 2.1.287, model `claude-haiku-5-5`, declared `windows/bash`: all six supplied probes were verified on 2026-10-27 using runner diagnostics plus tool execution and protected-file state. Background and bound-file deletion were denied, benign execution had no hook decision, and read-bound, unmonitored-stop and future-record warned. See `docs/host-dry-runs/claude-code-2026-10-27.md`. These dated candidate probes do not validate subsequent repairs. Antigravity has no hook adapter.

The maintained [capability matrix](../../skills/research-orchestrator/references/hooks-capabilities.md) separates adapter behavior from these dated observations. It is the single lookup for supported checks and host mappings.

Both hosts' benign probes recorded no hook decision and a successful foreground call. Claude maps Bash, PowerShell, Edit, Write, NotebookEdit, Glob, Grep, Read, AskUserQuestion and Agent. The Codex sample matches `Bash` and `apply_patch` only. Codex's `Bash` with `turn_id` uses the declared shell; Claude's stays Bash. PostToolUse cannot undo edits.

Set `RO_HOOK_DIAGNOSTICS=1` or create `.ro/hook-diagnostics.on` to log event, check IDs and decision in `.ro/hook-diagnostics.jsonl`; remove the marker to disable it. Logs omit command and environment values. Both host harnesses use runner diagnostics for warning/benign outcomes and retain host-output delivery evidence separately. Denials also need prevented execution and intact protected files. Missing diagnostics stay unknown; an assistant statement is not a runner record.
