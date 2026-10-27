# research-orchestrator v3 — plan

**Status:** approved 2026-10-25 by the owner (all recommendations accepted). Branch `v3`. Nothing in `main` changes until
the release step.

## 1. Why v3

Three past projects run with this skill failed in the same way: good execution, weak strategy. One of them also logged 28
operational mistakes, several repeated three or four times, and its checker stopped being useful once the project's
workflow outgrew the skill (issues grew from 234 to 452 and were ignored).

| # | Failure mode (general) | Seen in (of 3 projects) |
|---|---|---|
| F1 | Evaluation instrument could not see the target (in-sample, saturated, own-lineage, derived from the training targets) | 3 |
| F2 | Core family never built standalone; early frame fixed | 3 |
| F3 | Effort not sized to the gap; final stretch on micro-gains | 3 |
| F4 | Diagnosis recorded but not acted on; closures inherited or overridden | 3 |
| F5 | Public knowledge read for assets, not methods; read late | 3 |
| F6 | Known data-generation confounder not addressed | 2 + 1 partial |
| F7 | Process overhead; drift to easy-to-verify work | 3 |
| F8 | Late start | 3 |
| F9 | Final picks from one family | 2 + 1 partial |
| F10 | Small consistent gains rejected | 2 |
| F11 | No loss decomposition | 1 + 1 partial |
| F12 | No placebo / noise-floor control | 1 + 1 partial |
| F13 | External metric dynamics misread | 1 + 1 partial |

The three projects were competitions, so v3 deliberately checks every lesson against work and research settings (§2
principle 0) to avoid carrying a competition bias into the skill. Sources: each project's own post-mortem and mistake
log (kept with that project, not in this repository).

## 2. Principles

0. **Generality first (owner, 2026-10-25):** the skill must serve everyday work projects, research and competitions
   equally. Shipped files use neutral words; competition-specific material lives only in the competition reference and
   its platform adapters; every guard documents how it applies in work, research and competition settings; examples
   cover all three; a release check enforces the vocabulary rule.
1. **Domain-general words:** instrument, family, core model/policy, target metric, external feedback, deliverable,
   external action.
2. **Short core:** SKILL.md ≤ 12 KB; everything else in `references/*.md`, loaded only when its setting is on. The
   generated `agents.md` holds settings, pointers and project rules — not copied skill text.
3. **Enforcement ladder:** guidance → checker (host-independent source of truth) → advisory hooks → blocking hooks only
   for deterministic, costly, repeated mistakes. Too much enforcement repeats the overhead seen in a past project.
4. **No rule bloat:** a byte budget for standing rules; `Active overrides` carry `Expires:`; a new rule names the rule it
   replaces; lessons are one line each, "mistake → enforced by <check/hook id>".

## 3. Settings: presets → two axes → individual settings

### 3.1 Axes

| Axis | Values | Meaning |
|---|---|---|
| **Profile** (what kind of work) | `work` (alias `normal`) · `research` · `competition` (alias `kaggle`; Kaggle adapter by default) | selects modules and default values |
| **Workflow** (how agents coordinate) | `classic` · `unified` | per-agent plan sections + take-over / one shared queue with `Claimed:` lines |

### 3.2 Individual settings (all visible and editable in agents.md)

| Setting | Values |
|---|---|
| `Verification` | `cross-host-once` · `independent-review` · `hybrid` · `self` |
| `Item size` | `short` · `staged` (stage events `H-B-12/s3`; one discovery per decision-changing stage) |
| `Enforcement` | `off` · `warn` · `block` (default `warn`; deterministic patterns block) |
| `Autonomy` | `present` · `away` (away: never block on a question) |
| ~~`Review cadence`~~ | Retracted: use GD `direction-review` and Shared state `Paused:`. |
| `Queue freeze` | `off` · `until <date or condition>` (expiry required; important follow-ups exempt) |
| ~~`Discovery read`~~ | Retracted: startup is index-first with `ro index`. |
| ~~`Deliverable field`~~ | Retracted: optional item `Ready by:` replaces the setting. |
| `Guards` | `light` (default: records only) · `strict` (records + gating verdicts) · `off` |
| `Phase clock` | `off` · `start <date>, deadline <date>` |
| existing: `Platform mode`, `Platforms`, `Git sync`, `Plan collector`, `Plan queue limits`, `Reviewer`, `Cross-check fallback` | unchanged |

### 3.3 Presets

The table retains the original proposal beside the shipped default. **Reconciled 2026-10-27 for 6.0.0:** all six shipped presets use `Enforcement: block` with `Block: shell.background, shell.heredoc, jobs.mutate-bound, publish.scan`; competition presets also list `external.gate`. New custom projects use the same four-check default. This confines blocking to explicit, deterministic protections while leaving ordinary work and advisory findings unrestricted. Existing projects retain their recorded settings.

| Preset | For | Profile | Workflow | Verification | Item size | Guards | Original enforcement proposal | Shipped enforcement (6.0.0) |
|---|---|---|---|---|---|---|---|---|
| `quick` | personal or short work | work | classic, one agent | self | short | off | warn (safety only) | block |
| `work-project` | a multi-day work project (migration, analysis, build) run mainly by one agent | work | unified | independent-review | staged | light | warn | block |
| **`solo-research`** (recommended default) | one agent running long research | research | unified | independent-review | staged | light | warn | block |
| `team-research` | several sessions/hosts in parallel (the v2 way) | research | classic | cross-host-once | short | light | warn | block |
| `competition-solo` | a competition run mainly by one agent | competition | unified | independent-review | staged | light (+ phase clock, saturation, selection) | warn; external actions block | block |
| `competition-team` | a competition with parallel sessions/hosts | competition | classic | hybrid | short | light (+ phase clock, saturation, selection) | warn; external actions block | block |
| `custom` | any combination | | | | | | | block (new projects) |

User presets: save any combination under a name (user settings folder) and reuse it, e.g. `my-competition`.

### 3.4 Setup flow (replaces the six questions)

1. Choose a preset (table shown; `solo-research` recommended).
2. User name.
3. Only what the preset needs: hosts (team presets); competition slug and deadline (competition); git sync (only when a
   repository exists).
4. The generated agents.md starts with a summary: preset, axes, modules on.

`init --reconfigure --preset <name>` switches presets and keeps the four files; the checker reads both workflows.

## 4. Workflows

- **classic** — current v2 behaviour: per-agent sections, take-over rules, cross-host cross-check once.
- **unified** — one queue: items carry `Claimed: <slot> since <time>`; anyone edits unclaimed items; no take-over
  procedure; staged items with stage events; independent review before and after important stages (review receipts).
- **Single-agent fix:** with `independent-review`, a sub-agent reviewer distinct from the source session counts as
  verification (v2 left a lone slot's discoveries PENDING forever).
- ~~Separate `Provenance:` / `Verified by:` fields instead of overloading `Host`.~~ Retracted in the round-6 reconciliation below; source identity and dated Reviews remain authoritative.

## 5. Research guards (references/research-guards.md)

| Guard | Rule | Fails it prevents |
|---|---|---|
| G1 Instrument registry and validity | Each instrument records provenance (independent / derived from training targets / own lineage), coverage, agreement with the target, resolution and noise floor. An instrument derived from X cannot decide changes to X; without an independent instrument or a target probe the verdict is HOLD. Placebo control before trusting search gains. | F1, F12 |
| G2 Gap and loss decomposition | Shared state holds the gap to the target and a loss decomposition. When the gap ≫ a typical candidate's gain, the top of the queue must contain structural items. The automatic micro-variant cap is retracted in the round-6 reconciliation; direction reviews retain a reasoned budget. | F3, F11 |
| G3 Family saturation | When the last N measured candidates of a family tie within resolution, the family is SATURATED; new variants need a new instrument or a structural change. | F3 |
| G4 Core family check | At start and in every direction review: which core families do strong approaches use, and have we built each one standalone end to end? First experiments test a family end to end, not a sub-task. | F2 |
| G5 Overrides and closures | A decision against a registered rule is an Override (who, why, expiry, re-check trigger). A closure records the instrument and evidence that the change fired; it reopens when a better instrument exists or the implementation was broken. | F4 |
| G6 Insight follow-through | Reviewer and strategy diagnoses become Insight records that must end in a plan item or an evidence-based rejection within a set time. | F4 |
| G7 Data-generation audit (start) | How targets were produced; source/site/annotator effects; shortcuts; training vs evaluation label definitions. | F6 |
| G8 Phase clock | Baseline by 10 % of the window, core family by 25 %, big changes frozen at 70–80 %; shown at every session start. | F8 |
| G9 External intake log | Original proposal: methods and score levels, not only assets; a full screen by 20 % of the window, then weekly. Superseded by the [GD reconciliation](#reconciliation-after-round-10-2026-10-27). | F5 |
| G10 Adoption rule | Original proposal: small gains with consistent direction across seeds/sets are adopted and stacked, subject to G3. Superseded by the [GD reconciliation](#reconciliation-after-round-10-2026-10-27). | F10 |
| G11 Selection diversity | Final picks from different families unless evidence says otherwise. | F9 |
| G12 Effort monitor | Events tagged science / infra / process; share reported; warning above a threshold; drift to easy-to-verify work flagged. | F7 |
| G13 External metric dynamics | Record warm-up, drift and resolution of external feedback before using it as evidence. | F13 |

`light` = the records exist and the checker reports gaps; `strict` = the checker also turns missing or circular evidence
into HOLD verdicts.

Applicability (design review, Codex reviewer): every guard can be marked `not applicable — <reason>` (e.g. no leaderboard, no
labels, no deadline); thresholds (N for saturation, phase percentages, effort share) are settings, not constants;
comparisons need comparable measurement cohorts; adoption weighs cost. Scientific judgements stay review findings —
the checker only verifies that the explicit evidence each guard asks for is recorded.

## 6. External actions and the competition profile

**External actions ledger (all profiles).** Hard-to-reverse outward actions — a competition submission, a deployment or
release, a paper or report submission, a message sent to people — share one ledger: identity and artifact hash, the
expected outcome written before acting, the observed result after, status, duplicates refused. The competition profile
is this ledger specialised for leaderboards (see P2 spec, C1 → E1).

### Competition specifics (references/competition.md + adapters/kaggle.md)

- External feedback as an instrument (resolution, noise, public vs private); expected score written before each
  submission; ties treated as noise.
- Per-target / per-column leaderboard probes as an explicit allowed-or-not setting.
- Submission ledger: submit once, no duplicates, quota and limits re-read right before use, runtime limit check.
- Phase clock required; saturation and selection guards on.
- Forum and write-up intake (G9) for methods and score levels.
- After the close: collect top write-ups → fixed-template summaries → compare with our records → independent fact-check
  → post-mortem (the procedure first used on 2026-10-24/25).
- Kaggle CLI/API usage lives in an adapter so other platforms can be added later.

## 7. Operational safety (references/operations-safety.md) and enforcement

**Reconciled 2026-10-27:** the mechanism proposals are retained below; the annotated monitoring, ID and away-mode rows give their shipped defaults; earlier block-once proposals for monitoring and blocking proposals for ID collisions and away-mode questions were not adopted as defaults. `jobs.unmonitored`, `records.id`, and `ask.away` are **warn-only by default**. Explicit project policy can opt supported pre-event checks into `Block`; PostToolUse ID checks remain advisory. A capable agent can reconcile records or continue useful work without a notification becoming a mandatory stop. The fixed preset Block lists are recorded in §3.3 above.

| Repeated mistake (past project) | Mechanism | Level |
|---|---|---|
| `&` / `disown` in a foreground shell call (4×) | PreToolUse(Bash) `shell_guard` | block |
| Unquoted heredoc with backticks; scripts written through heredocs | PreToolUse(Bash) | block |
| Touching a running job's directory or files it binds; editing a script in use (3×) | job registry + PreToolUse(Bash/Edit/Write) | block |
| Bare `cd` changing the session directory (3×+) | PreToolUse(Bash) | warn |
| Waiters that only watched for completion (2×) | `ro launch` registers expected duration and error signatures; monitor template stops on error or 2× duration; Stop hook warns on jobs without a monitor | warn (`jobs.unmonitored`) |
| Timers not re-armed; scheduled checks skipped | Stop hook warns about registered jobs without a live monitor; SessionStart lists overdue items | warn (`jobs.unmonitored`) |
| Timestamps ahead of the clock (5×) | PostToolUse on coordination files + checker | warn |
| ID collisions | `ro next-id` + checker | warn (`records.id`); structural checker errors remain |
| "Launched" recorded before verified | `ro launch` writes the event only after a status check | by construction |
| Stale volatile facts (quota) | `Observed at` fields; checker ages them | warn |
| Review FAIL overridden; requirements relaxed in fix prompts | review receipts bound to the artifact hash; launch/submit wrappers need a PASS; override register | block |
| Review checklists from memory (4×); missing required lines in sub-agent briefs | Original contract-file (file:line) prompt proposal retracted in the [reconciliation](#reconciliation-after-round-10-2026-10-27); PreToolUse(Agent) checks configured required lines | warn |
| Findings left only in chat or a sub-agent report | SubagentStop: no referencing event/discovery → warn | warn |
| Secrets or data in a public push | PreToolUse(git push) `publish_guard` | block |
| Blocking question while the user is away | PreToolUse(AskUserQuestion) when `Autonomy: away` | warn (`ask.away`) |
| Context lost at compaction | PreCompact re-injects current item, claims, triggers | assist |
| Format drift disabling the checker | mode-aware checker; zero-issue baseline; warn when the count grows | warn |

Hosts: Claude Code via plugin `hooks/hooks.json` (and SKILL.md `hooks` where useful); Codex via its hooks config as
best effort (undocumented behaviours exist). The checker and the `ro` CLI remain the source of truth on every host.

## 8. Deliverables

- SKILL.md core rewrite (≤ 12 KB) and `references/`: `workflow-classic.md`, `workflow-unified.md`, `verification.md`,
  `staged-items.md`, `research-guards.md`, `competition.md`, `adapters/kaggle.md`, `operations-safety.md`, `hooks.md`,
  `compute.md`, `git-sync.md`.
- `presets/*.json` (six built-in presets) and user preset save/load.
- Templates: agents.md (settings summary, pointers, `Standing rules` with budget, `Active overrides` with `Expires:`,
  `Lessons` one line → enforcer id); plan.md (classic and unified); discoveries.md (index; optional Instrument / Decision
  class / Override fields); handoff.md (Shared state: target gap, phase clock, last round, effort share).
- Scripts: `check_project.py` v3 (workflow-aware, guard and safety checks); `init_research_orchestrator.py` v3 (presets,
  setup flow, migration); `ro.py` (next-id, dupcheck, launch/monitor registry, brief, observe, review-receipt).
- Hook scripts: `shell_guard`, `edit_guard`, `stop_check`, `session_brief`, `subagent_check`, `publish_guard`; plugin
  `hooks/hooks.json`; Codex sample config; optional git pre-commit.
- Examples: one project per preset, covering work, research (including a non-ML one) and competition;
  `scripts/validate_release.py` update with a vocabulary check (competition terms only in competition files);
  READMEs in four languages; version 6.0.0 (major bump from 5.1.0) with a changelog. v2 projects stay readable.

## 9. Verification

- Unit tests for the checker, `ro` and every guard, with fixtures for both workflows (the repo has no tests today).
- Replay tests on anonymised excerpts of past records: the checker must flag a saturated family (21 tied results), a
  GO→DROP override without re-check, an unresolved strategy insight and a circular instrument deciding target
  changes; similar checks for an own-lineage evaluation panel and an in-sample validation.
- Every preset generates an example project that passes the checker with zero issues.
- Hook dry-runs on a sandbox project to measure false positives; the original `warn` proposal was superseded by the dated §3.3/§7 reconciliation.
- Independent review of the final diff before release.

## 10. Phases

1. **P1** — settings, axes, presets and setup flow; checker that understands both workflows (fixes the past project's checker
   noise first); tests for both.
2. **P2** — research guards: record formats and checker rules.
3. **P3** — `ro` CLI and advisory hooks.
4. **P4** — blocking hooks for deterministic patterns; SKILL.md/references rewrite finalised; examples, READMEs, release
   validation, version 6.0.0. Then update the installed copy.

## 11. Decisions (2026-10-25)

- Owner decision, 2026-10-26: no further scenario runs or description optimisation for 6.0.0. The owner validates in real use. Behaviour evidence is the adjudicated iteration-6 snapshot; it does not measure the exact final runtime. Regression tests and release gates still apply.

- Profile name `competition` (alias `kaggle`), Kaggle adapter by default.
- Generality first: profile `work` (alias `normal`), preset `work-project`, one external-actions ledger for all
  profiles, vocabulary check in release validation, examples for work, research and competition; project names
  anonymised in these design records.
- Presets as listed in 3.3; recommended default `solo-research`; user presets supported.
- Enforcement: `warn` overall; block only deterministic patterns (foreground `&`/`disown`, edits to files bound by
  running jobs, secret/data scan before a public push) and external actions in competition presets. Refined after the
  design review: `warn` never blocks; every blocking check is listed explicitly in a `Block:` setting (the competition
  presets list `external-actions` there, so nothing blocks by hidden exception); P1 labels stored-but-unimplemented
  settings inactive; a host/shell capability matrix (P4) states what each host can enforce.
- Design reviews: [P1 spec v1.1 §11](v3-p1-spec.md) records the Codex reviewer and Claude reviewer changes.
- Guards `light` by default; `strict` optional.
- Work on branch `v3` in this repository, then update the installed copy. Past project records are used only as anonymised replay fixtures.

## Decisions after P1 (2026-10-26, eval-r1)

These decisions reconcile §3.2 and §7 with the shipped P1 settings table ([P1 spec](v3-p1-spec.md)) and supersede the earlier proposals without rewriting their history.

- **Review cadence:** use the existing GD `direction-review` guard threshold; another setting would create competing clocks. First review is due from guard activation/project start; Shared state `Paused: YYYY-MM-DD` suspends cadence.
- **Queue freeze:** implement optional `Queue freeze: off | until YYYY-MM-DD`, default off. During the freeze, finish or correct existing items and hold new scope in outcome records. Warn after expiry; historical edit detection and blocking are outside this small setting's contract.
- **Discovery read:** drop the switch. Startup is index-first by design; full entries are read when relevant, which preserves duplicate awareness without loading every evidence trail.
- **Deliverable field:** drop a project-wide field selector. An optional item `Ready by: YYYY-MM-DD` supplies useful delivery timing without adding a domain-specific schema or requiring deadlines on routine work.
- **Chat-only findings:** withdraw §7's SubagentStop detection claim and the later P3 transfer of that claim to `ro close`. No hook stores a complete agent invocation/result ledger, so the CLI cannot infer an unrecorded chat result. Close checks recorded discoveries/follow-ups and registered jobs; agents retain responsibility for writing reusable findings. The dead `subagent` filter is removed.
- **Host verification:** installed-host trust/event delivery dry-runs remain an owner-approved later step. Repository subprocess tests do not establish installed host enforcement; Antigravity remains command-only.

## Reconciliation after round 6 (2026-10-27)

- **Verification fields:** retract the proposed separate `Provenance:` / `Verified by:` pair in §4. `Host`, `User` and `Session` identify the source; dated `Reviews` identify reviewers and verdicts under the configured verification policy. A second summary field would duplicate that evidence and could disagree with it. Instrument provenance remains in the instrument record.
- **Important stages:** implemented through `Important stages: s2 | s3`, naming stages in `Stages:`. Designated launches require an independent, artifact-bound receipt scoped to the item/stage and `before`; decision-changing results require a new `after` receipt before continuation. Routine stages retain their lighter path. See [staged items](../../skills/research-orchestrator/references/staged-items.md).
- **Micro-variant budget:** retract §5 G2's automatic cap and the proposed GD `Budget:` / `guard.direction.budget` check. Records do not reliably identify which candidates are micro-variants, so a numeric check would invite arbitrary classification and false precision. Direction reviews still record the remaining budget and structural alternative; G3 checks measured family saturation. No automatic variant-count enforcement is claimed for 6.0.0.

## Reconciliation after round 10 (2026-10-27)

- **Contract-file review prompts:** retract §7's proposal to generate prompts from contract files with file:line citations. The shipped `brief.requirements` check validates configured required lines; reviewers read the linked verification instructions and relevant artifacts. Automatic prompt construction and `ro brief --contract` are not implemented. Requiring a second contract format would duplicate the existing review instructions without establishing that the review was performed.
- **G9 intake and G10 adoption:** fold these proposals into GD's `Intake`, `Rejected consistent gains` and `Decisions` records. Retract G9's fixed 20 % intake deadline and separate weekly schedule; the configurable `direction-review` cadence (seven days by default) governs review, with applicability and pause support. Retract G10's automatic adopt-and-stack rule: consistent gains inform an evidence- and cost-aware decision, subject to G3 saturation, rather than forcing adoption. The checker checks recorded review completeness and cadence, not the quality of intake or the scientific merit of adopting a gain; see [decision guards](../../skills/research-orchestrator/references/decision-guards.md).

## Reconciliation after round 11 (2026-10-27)

- Reduce ?2.4's proposed standing-rule replacement declaration and `mistake ? enforced by <check/hook id>` lesson syntax to writing guidance. Semantic replacement and useful lessons cannot be established from a marker alone; no `rules.standing.replaces` or `rules.lesson.format` finding is shipped. Existing Project rules budgets and override validation remain.
- Reduce ?6's per-column-probe setting to task-specific Project rules prose; `Per-column probes:` is not a validated setting. Record the actual scope and limits when a task needs probes. Code-competition runtime checks remain an operator decision from dated source limits and measured runtime, now explicit in the adapter; no live platform request or runtime-limit checker is added.

Reconciled 2026-10-27: the shipped initializer has six built-in presets; future timestamps share a five-minute tolerance. The current local wrapper fast-path measurement restores 150 ms p95; historical timings remain scoped to their recorded runtimes.
