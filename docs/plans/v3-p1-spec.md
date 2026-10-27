# v3 — P1 specification: presets, two workflows, workflow-aware checker

**Version 1.1** (2026-10-25). v1.0 was reviewed independently by a Codex reviewer and a Claude reviewer; both said GO WITH CHANGES.
Their points are folded in below and listed in §11. Parent plan: [v3-plan.md](v3-plan.md). Branch `v3`.

P1 must leave every v2 project readable, upgrade an untouched v2 project without `--force`, and keep the project-specific
rules users wrote by hand.

## 1. One settings module

`scripts/ro_settings.py` is the single table of settings: name, allowed values, v2 default, help text, which preset keys
it covers, and whether it is *active* in this release. argparse flags, validation, preset schema, template conditions
and the checker all import it (hard import; an import failure is a structural error, never swallowed).

| Line in `## Project settings` | Values | v2 file without the line reads as | Active in P1 |
|---|---|---|---|
| `Preset` | `quick`, `solo-research`, `team-research`, `competition-solo`, `competition-team`, `custom`, `user:<name>` | `custom` | yes |
| `Profile` | `work` (input alias `normal`), `research`, `competition` (input alias `kaggle`) | `research` | stored only |
| `Workflow` | `classic`, `unified` | `classic` | yes |
| `Verification` | `cross-host-once`, `independent-review`, `hybrid`, `self` | `cross-host-once` | yes |
| `Item size` | `short`, `staged` | `short` | yes |
| `Guards` | `off`, `light`, `strict` | `off` | stored only (P2) |
| `Enforcement` | `off`, `warn`, `block` | `off` | stored only (P3) |
| `Autonomy` | `present`, `away` | `present` | stored only (P3) |
| `Phase clock` | `off`, or `start YYYY-MM-DD, deadline YYYY-MM-DD` | `off` | stored only (P2) |
| `Competition` | `off`, or `<platform>/<slug>` | `off` | stored only (P2) |
| v2 lines (`Platform mode`, `Platforms`, `Git sync`, `Plan collector`, `Plan queue limits`, `Reviewer`, `Cross-check fallback`) | unchanged | — | yes |

Settings marked "stored only" are written and validated, and the generated agents.md says they are not active yet. A
`competition` profile with `Competition: off` is a WARN.

## 2. Presets

- Built-in presets: `presets/<name>.json` at the skill root. Every preset lists **every** preset-covered key, including
  `platform_mode`, `platforms`, `collector`, `queue_limits`, `reviewer`, `fallback`, and `asks` (the setup questions it
  needs: subset of `platforms`, `competition`, `phase_clock`, `git`). There is no `custom.json`: custom is the absence of
  a preset.

| Preset | profile | workflow | verification | item_size | guards | enforcement | platform_mode | asks |
|---|---|---|---|---|---|---|---|---|
| quick | work | classic | self | short | off | warn | single | platforms |
| work-project | work | unified | independent-review | staged | light | warn | single | platforms |
| solo-research | research | unified | independent-review | staged | light | warn | single | platforms |
| team-research | research | classic | cross-host-once | short | light | warn | multi | platforms |
| competition-solo | competition | unified | independent-review | staged | light | warn | single | platforms, competition, phase_clock |
| competition-team | competition | classic | hybrid | short | light | warn | multi | platforms, competition, phase_clock |

  Single-platform presets ask for exactly one host. Collector `off`, reviewer `off`, queue limits `stop at 50, resume at
  5` and fallback per the v2 rule unless a preset says otherwise.
- User presets: `<home>/.research-orchestrator/presets/<name>.json`, same schema, loaded only as `user:<name>`.
  `--save-preset <name>` writes every preset-covered key of the effective settings.
- **Resolved values are persisted** in agents.md; later edits to a preset file never change existing projects.

## 3. Precedence

- New project: flag > preset > v2 default.
- `--reconfigure` without `--preset`: flag > value stored in agents.md > v2 default.
- `--reconfigure --preset X`: flag > X's keys > stored values for keys X does not cover > v2 default.

## 4. init (`init_research_orchestrator.py`)

- New flags: `--preset`, `--list-presets`, `--save-preset`, `--profile`, `--workflow`, `--verification`, `--item-size`,
  `--guards`, `--enforcement`, `--autonomy`, `--phase-clock`, `--competition`, `--migrate`. Flags come from
  `ro_settings.py`.
- `--list-presets` prints name, summary, profile, workflow, verification; exit 0.
- Template grammar: the `{{#if key=values}}` conditions accept hyphenated values (`verification=independent-review`).
  P1 adds conditions for `workflow`, `verification`, `itemsize`; none for `profile` (no content yet). The cross-check
  rules shown are chosen by `Verification` first; `Platform mode` only matters inside `cross-host-once`/`hybrid`, and
  `single` + `independent-review` never renders "different host" rules.
- agents.md settings block starts with one summary line: preset, workflow, verification, active modules.
- **Preserved region:** everything from the `## Project rules` heading to the end of agents.md is user-owned. Init
  creates the heading empty; `--reconfigure` regenerates only the part above it and copies the region verbatim.
  Hand-edit detection covers only the generated part: re-render it from the file's own stored settings with the
  template version recorded in the file (`<!-- ro-template: v2 | v3 -->`; absent = v2), and compare. An untouched v2
  file therefore upgrades without `--force`.
- `unified` generates plan.md with one `## Queue` section; handoff.md keeps per-slot sections in both workflows.
- `--migrate` (required when `Workflow` changes):
  - Preflight: refuse when any slot is taken (`Current host` not `released`/`unassigned`) unless `--force`, and when the
    checker reports ERRORs.
  - classic → unified: items move into `## Queue` in priority order; `Claimed: none` for all (the project is quiescent).
  - unified → classic: each item returns to the section named by its **ID prefix** (`H-B-07` → `## Agent: B`); missing
    sections are created; `Claimed:` lines are dropped.
  - Atomic: write every new file to a temp name, keep `<file>.pre-migrate` backups, then rename all; on any failure
    restore the backups. A migration writes one handoff event (heading `none`, Action names the migration).
  - Round-trip equality is defined over parsed records (ID → field dict), not text order.

## 5. Unified plan format and lifecycle

```markdown
## Queue

### H-A-01 — Short title
- Claimed: none | <slot> since YYYY-MM-DD HH:MM
- Sources: …
(v2 fields)
- Next test: …
- Stages: s1 <name> | s2 <name> | …        (staged items only; optional)
```

- Field rule (both workflows): required fields must all be present and in their relative order; unknown `- Field:`
  lines (e.g. `Status:`) are INFO, not an error. In unified `Claimed:` is the first field.
- Claims: claim by editing the line after re-reading plan.md (v2 shared-file safety rule). **Closing a session releases
  its claims** (`Claimed: none`) except for items whose job is still running; those keep the slot taken, as in v2.
- Stage events: heading `### YYYY-MM-DD HH:MM — <slot> — H-A-01/s2`. `/sN` records stage progress only; only the bare ID
  completes the item. Stage numbers must exist in the item's `Stages:`; a stage event for an item without `Stages:` or
  beyond its list is a WARN. A stage event may carry `Decision: changed` when it produced a discovery; otherwise it is
  operational.

## 6. Verification

- `cross-host-once`: v2 rules.
- `independent-review`: the review line keeps the v2 shape and adds a reviewer token:
  `<Host> (<slot>): <VERDICT> — reviewer <id> — <reason>`. `<id>` is a session identity (e.g. `subagent:claude-reviewer@2026-10-25T14:10`,
  `codex:reviewer-2@…`). Discoveries gain an optional `Session:` field with the source session identity. A review counts
  when `<id>` is present and differs from the discovery's `Session:`; same host and slot are allowed. A legacy
  discovery without `Session:` cannot be verified by a same-slot review (INFO). A host without sub-agents leaves the
  state PENDING with INFO, never an error.
- `hybrid`: either form counts. `self`: no review needed; PENDING raises nothing.
- CHALLENGED: a later review on the same discovery that names the challenge and resolves it (`VERIFIED after challenge
  — …` or `CLOSED after challenge — …`) supersedes it; the checker treats the latest review as the state.

## 7. Checker (`check_project.py` v3)

- Severity: **ERROR** = the files contradict each other or a required structure is missing (missing section, duplicate
  or dangling ID, completed item still queued, missing `Claimed:` in unified, two `## Queue` sections, settings outside
  the allowed values); **WARN** = stale or non-canonical (stale claim, stage beyond `Stages:`, rules out of sync,
  timestamps ahead of the clock); **INFO** = v2 compatibility and advice. Exit 1 only for ERROR, 2 for a parse failure;
  `--strict` makes WARN fail.
- Every issue has a stable check id (`plan.claim.stale`) and a fingerprint `check id + record id + field`.
- Baseline: tool state lives in `.ro/` (not a coordination file). `--baseline-update` writes
  `.ro/checker-baseline.json` with the current fingerprints; a normal run compares against it when present and reports
  "N new issues since the baseline" as WARN. A baseline never hides or downgrades a finding.
- Stale claim: a claim by a slot that is `released` or `unassigned` → WARN. A claim older than 7 days with no event by
  that slot naming the item (with or without `/sN`) after the claim time → INFO.
- v2 agents.md without v3 lines → INFO ("v2 settings; run --reconfigure to add v3 lines").

## 8. Documentation in P1 (start the core split now)

- New `references/`: `presets.md`, `workflow-classic.md` (v2 per-agent sections, take-over), `workflow-unified.md`
  (queue, claims, stages, migration), `verification.md` (cross-host-once, independent-review, hybrid, self),
  `compute.md` (moved from SKILL.md §7).
- SKILL.md: §0 setup becomes the preset flow (choose preset → user name → only what the preset asks); §3, §4 take-over,
  §5 and §7 shrink to the shared core plus "read `references/<file>` when `<setting>` is `<value>`". Rules that differ
  by setting live only in references, so no two instruction sets compete. The AGENTS template generates pointers, not
  copied text. Target this phase: SKILL.md ≤ 20 KB (P4 reaches ≤ 12 KB).

## 9. Tests (`tests/`, pytest, no network; run by `scripts/validate_release.py`)

1. Every preset generates a project (answers for `asks` given in the test) → 0 ERROR, 0 WARN.
2. A frozen v2 fixture (`tests/fixtures/v2/`, copied from the current `examples/cv-leakage-study`) → 0 ERROR, INFO only;
   `--reconfigure` upgrades it without `--force` and keeps a hand-written `## Project rules` region verbatim.
3. Unified: claim by a released slot → `plan.claim.stale` WARN; missing `Claimed:` → ERROR; two `## Queue` → ERROR;
   unknown `Status:` field → INFO; stage beyond `Stages:` → WARN; `/sN` event does not complete the item.
4. Migration classic → unified → classic: parsed records equal; IDs back in their prefix sections; interrupted migration
   (simulated failure) restores the backups; preflight refuses with a taken slot.
5. Verification: same-slot review with a distinct reviewer id counts; one equal to `Session:` does not; legacy
   discovery without `Session:` stays PENDING (INFO); a resolved challenge supersedes CHALLENGED.
6. Precedence: all three cases in §3; `user:<name>` round trip via `--save-preset`.
7. Baseline: new fingerprint → WARN; same fingerprints → none; the baseline never removes a finding.
8. `--list-presets` lists the six presets; template conditions with hyphenated values render.
9. Replay: an anonymised unified plan taken from a real project (`tests/fixtures/unified-plan-sample/`, structure only,
   no project names or data) parses under `unified` with no ERROR from fields such as `Status:`/`Candidate:`.
   Fixtures and tests are named after failure modes, never after projects.

## 10. Out of scope for P1

Guard behaviour (P2), the `ro` CLI, job registry, claims locking and hooks (P3), the ≤ 12 KB core, READMEs, per-preset
examples (including a non-ML one), the host/shell capability matrix and release (P4).

## 11. Review changes from v1.0

- Codex reviewer: migration by ID prefix with preflight, atomic writes and recovery; reviewer/session identity; stage lifecycle;
  remove competing instruction sets during P1; versioned template recognition; exact precedence; fingerprinted baseline
  that never suppresses; hyphenated template values; inactive settings labelled; enforcement explicit (see plan).
- Claude reviewer: required-field set with relative order and INFO for unknown fields; preserved `## Project rules` region; claims
  released at close; keep the v2 review shape with a reviewer token; one settings module as a hard import; `asks`
  includes platforms for single presets; frozen v2 fixture; tests wired into `validate_release.py`; no `custom.json`;
  start the core/references split in P1; anonymised replay fixture.
