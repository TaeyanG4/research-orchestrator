# Codex description experiments

The coordinator runs this tool outside the builder sandbox. It measures selection
of a skill, not completion of the queried task: the temporary skill contains only
`SKILL.md`, so its referenced scripts and documents are intentionally absent.
No Claude CLI or skill-creator installation is required at runtime.
The runner stops its own CLI process at the first completed selection event, so
missing downstream runtime files cannot turn a measured selection into a failure.

## Discovery and isolation

Checked on 2026-10-26 with installed `codex-cli 0.153.4`: `codex --help`,
`codex exec --help`, local `scripts/evals/isolation.py`, and the current official
[discovery documentation](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)
and [configuration schema](https://learn.chatgpt.com/docs/config-schema.json).
On Windows the npm PowerShell shim may be blocked by execution policy; the
existing `resolve_codex` helper selects the native executable without changing policy.
If PATH resolves to an app bridge that waits for an interactive client, pass
`--codex <path to the standalone npm codex.cmd>` explicitly; its native CLI is
resolved without changing PATH or installed applications.

Each query/repeat/attempt gets a fresh project with a `.git` discovery boundary and
`.agents/skills/research-orchestrator/SKILL.md`. Codex discovers project
skills through `.agents/skills`, normally walking from CWD to the repository root,
then exposes name/description/path metadata. The prompt contains only the query;
it neither names the skill nor injects its instructions. `skills.include_instructions=true`
keeps the native catalog enabled; `features.skip_host_skill_discovery=false`
avoids suppressing discovery. There is no invented skill-root allowlist.

Home discovery is separate from project discovery. Before each invocation the
runner inventories user `.agents/skills`, legacy `.codex/skills`, `.claude/skills`,
the effective `CODEX_HOME/skills`, `/etc/codex/skills`, and ancestor skill roots.
It follows linked directories with cycle detection and passes every external
manifest's lexical and canonical path as `skills.config` disabled selectors.
Same-name copies are explicitly listed in `isolation.installed.same_name_copies`;
they are expected on an installed host, not silently treated as the candidate.
An inventory failure prevents the attempt from launching. Bundled/cloud skills,
plugins, skill search, hooks, memory and multi-agent features are disabled for the
invocation. `--ignore-user-config`, `--ignore-rules`, `--ephemeral`,
`project_doc_max_bytes=0`, and per-command overrides suppress inherited instructions
and config. `--strict-config` rejects unsupported keys rather than silently losing
isolation on an incompatible host. Only the existing eval runner's allowlisted model/provider and Windows
sandbox settings survive. No settings or installed files are changed.

The actual command is `codex exec --json --skip-git-repo-check -s read-only -C <tmp>`
plus those isolation options and the literal query as an argv argument, with stdin
closed. Real home/authentication and existing Windows sandbox setup remain in
place; credential files are never read or copied by this tool. Default scratch
projects live beside this checkout under `research-orchestrator-workspace/_trigger-runs`
because Windows sandbox accounts may not be able to read the real user's temp
directory. `--temp-parent` can select another accessible location outside this repo.

An event audit flags visible reads of installed skills, source files, evals or
other runs; a changed candidate or a successful read of a real outside same-name skill also invalidates
the attempt. This prevents an observed home-copy read from earning a trigger.
Codex JSONL does not expose its complete initial skill catalog. Isolation therefore
depends on the documented disable selectors and the host honoring them; a clean
trace alone cannot prove that no hidden context or concealed read occurred. Retain
the recorded host version when comparing descriptions and inspect contamination
evidence before using scores. System-managed host configuration remains a dependency.
Failed guesses at nonexistent source files remain findings without contaminating
the attempt. Source reads require successful completion and a real file; path
comparisons use components and resolve relative paths against the command's CWD.

## Detection and scoring

Only completed Codex items count. A trigger requires either:

- A successful read of the exact staged `SKILL.md` in `command_execution`,
  `file_read`, or `read_file`. Shell detection handles literal paths in common
  read commands (`Get-Content`, `cat`, `head`, `sed`, `rg`, etc.), including shell
  wrappers; it does not infer reads inside arbitrary interpreter programs.
- An `agent_message` sentence starting with a first-person use announcement or
  `Using`/`Applying`/`Consulting`/`Following`/`Reading`, containing the exact skill
  name, without a negated announcement or conditional selection. This is an
  auditable announcement heuristic, not a semantic
  judge. It can miss unusual wording; retained evidence permits manual review.

User prompts, reasoning, tool-output echoes, unfinished/failed reads, plain name
mentions and negative use announcements do not count. Raw events, stderr, command,
evidence, tokens when present, duration, and isolation metadata are saved for every
attempt before temporary-project cleanup. Protocol `first-selection-v1` records
the stopping event in `selection_boundary` and audits the complete prefix through
that event; earlier contamination still invalidates the attempt. Any bytes received
after the stopping boundary remain in `events-after-selection.jsonl` for inspection,
separate from the measured prefix in `events.jsonl`. A selected run need not finish
the queried task; a nonselection still requires a clean `turn.completed` and exit 0.
This applies only to new runs, never to retrospective trimming of old traces.
All repeats must reach one of those clean endpoints before
a query is scored; errors/timeouts/contamination are `inconclusive`, never false
negatives or true negatives. Null precision/recall means a zero denominator.
Each attempt and final run carries `inconclusive_reason`; query summaries identify
the repeat and its reason in `inconclusive_reasons`. Contamination takes precedence
over a simultaneous timeout, and successful retries use the final attempt. A
selection observed during an old full-task timeout remains unknown: changing the
endpoint after seeing the trace would change the experiment.

Explain existing results without launching models or replacing their evidence:

```powershell
python scripts/trigger/explain_results.py saved-results.json --output explained-results.json
```

The output is a new file containing the original attempts and measurement protocol
alongside reasoned summaries; an existing output file is refused.

The frozen 20-query set has 10 positives and 10 near-miss negatives. Skill-creator's
seeded, stratified 60/40 split gives 6+6 development and 4+4 held-out queries.
Default three repeats and threshold 0.5 produce a majority decision per query.
`results.json` records precision, recall, accuracy, coverage and confusion counts
separately for development, held-out and combined queries, plus description/skill/query
digests. Keep the set, seed, model, repeats and threshold fixed across candidates.
Use development failures to write concise descriptions that generalize; compare
held-out results after selecting candidates, rather than copying test wording.

Only failed attempts with terminal rate-limit or transport-disconnect evidence receive
up to `--retries` fresh sessions (default 3), using the existing eval runner's
diagnostic parser. Successful recovered sessions, ordinary errors, incomplete
reconnects and contamination are not retried. Every attempt remains in its own
directory. `--jobs` bounds parallel sessions; result order stays deterministic.
Usage limits, 429, model-capacity and 503 failures are classified as `rate_limit`.
Try three fresh sessions before waiting for the stated reset; further launches
use 60, 120, then 240 seconds of backoff when no reset is given.
The cooldown is shared within one runner process; already running sessions may
finish. `rate_limit_evidence` and `retry_delay_seconds` are retained per attempt.
As before, a timeout with terminal disconnect evidence may retry; rate-limit
diagnostics do not turn timeouts into retries.

## Coordinator commands

Run from the repository root in PowerShell:

```powershell
$python = '<path to python.exe>'
& $python scripts/trigger/run_trigger_eval.py --output ../research-orchestrator-workspace/trigger/current --repeats 3 --jobs 4
& $python scripts/trigger/run_trigger_eval.py --description candidate-description.txt --output ../research-orchestrator-workspace/trigger/candidate --repeats 3 --jobs 4
```

The override file is UTF-8 description text only; source `SKILL.md` is unchanged.
Use `--split train` during development and `--split test` for held-out confirmation,
with new output directories. Pass the same `--model <model-id>` to both commands
to pin a model; otherwise the configured host model is retained. Existing output
directories are refused. Exit 0 means all queries were measurable, not that every
prediction was correct; exit 1 means inconclusive queries, exit 2 setup failure.

The skill-creator method applied here is intent/coverage analysis, Description
Optimization query generation, repeated stratified evaluation, objective negative
controls and an analyst review of evidence quality. The builder does not run live
models, optimize/apply a description, generate a model-output review viewer or
package a skill. Those steps require coordinator-run results; this tooling changes
no skill behavior, so existing skill-creator case folders remain unchanged.
