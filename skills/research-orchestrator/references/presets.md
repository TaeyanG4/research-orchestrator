# Presets and settings

Settings live under `## Project settings` in `agents.md`, with allowed values defined in `ro_settings.py`. A preset supplies a starting policy. A new project with no preset or `custom` starts with compact work items, self verification and blocking safety checks; its platforms use the detected host (or `local`). This keeps routine work from inheriting a research scoring workflow. Explicit flags override these defaults; existing projects keep their stored policy.

Default and inactive settings collapse to keep everyday reading short. Their explicit values still survive `--reconfigure`, so hiding them does not discard a preference. Reading pointers explain active choices that differ from defaults; use the core operation table for ordinary tasks.

## Built-in presets

| Preset | For | Profile | Workflow | Verification | Item size | Guards | Enforcement | Platform mode | Other asks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `quick` | short personal work | work | classic | self | short | off | block | single | platforms, git |
| `work-project` | multi-day migration, analysis or build | work | unified | independent-review | staged | light | block | single | platforms, git |
| `solo-research` (recommended) | long research by one agent | research | unified | independent-review | staged | light | block | single | platforms, git |
| `team-research` | parallel research (the v2 way) | research | classic | cross-host-once | short | light | block | multi | platforms, git |
| `competition-solo` | competition by one agent | competition | unified | independent-review | staged | light | block | single | platforms, competition, external actions if unmapped, phase clock, git |
| `competition-team` | parallel competition | competition | classic | hybrid | short | light | block | multi | platforms, competition, external actions if unmapped, phase clock, git |

Presets leave the collector and reviewer off until their extra coordination is useful. The collector pauses at 50 queued items and resumes at 5, leaving room to finish existing work. Single-host presets use `same-host` fallback; multi-host presets use `wait` to preserve the intended review separation. A mapped competition supplies commands from its [external-action adapter](adapters/external-actions.json). A suffix such as `--competition "hub/task deadline=2026-12-01"` defaults an unanswered phase clock to today through that deadline, so known choices need no extra answers. Explicit commands and explicit or stored phase clocks keep precedence; a past deadline needs an explicit clock with the actual start date.

Run init inside the host session so detection can name it. Multi-host presets supply hosts; single-host presets detect Claude, Codex, Antigravity or Gemini and fall back to `local`, with `--platforms` overriding detection. A single-host `local` project accepts later host records with a warning to update Platforms. Use the detected environment and infer Language from the request or conversation, passing `--language` when needed (`en` is the initializer default). Ask about either only when missing or ambiguous. An unsupported detected OS or explicit shell requires `--environment`. Use `--answers answers.json` for a JSON object of setting keys (`preset`, `user`, `platforms`, `environment`, `language`, and any competition answers); explicit flags override it. Flags, saved preset values and stored settings answer these choices; `Info:` reports implicit defaults. Git sync is asked only in a repository. Competition presets ask for external command patterns when the platform has no adapter; answer `none` explicitly if no outward action is planned.

Work uses compact items and optional scores to avoid maintaining numbers that do not guide a decision. New `solo-research` plans generate `Ordering: queue`, so scores are optional there too; other research and competition plans can use `--ordering queue` at initialization or select that header explicitly. All profiles default routing to `CPU` / `NO` / `NONE`. Supplied scores still need valid ranges and arithmetic. See [plan-items.md](plan-items.md) and [records.md](records.md). Direction reviews need Gap and Decisions; research also needs a first-review Data audit. Competition-shaped parts become requirements for competition or `direction-parts=full`, and otherwise remain INFO advice in research.

```bash
python <skill-root>/scripts/init_research_orchestrator.py --list-presets
python <skill-root>/scripts/init_research_orchestrator.py . -n "<project>" --preset work-project --user <user> --platforms "<host>"
python <skill-root>/scripts/init_research_orchestrator.py . --reconfigure --preset competition-team --competition <platform>/<slug> --phase-clock <start>,<deadline> --migrate
```

## The settings

Read [settings-values.md](settings-values.md) when changing an individual setting. The table gives allowed values, defaults and when edits take effect; keeping it separate makes preset selection quick.

Presets use `Block: shell.background, shell.heredoc, jobs.mutate-bound, publish.scan`; competition presets add `external.gate`. [hooks.md](hooks.md) owns enforcement and host limits. A `competition` profile with `Competition: off` is a warning. [research-guards.md](research-guards.md) owns guard applicability, severity, and record formats. Initializer `--help` lists the corresponding flags.

`--list-presets` shows preset languages; `ro brief` shows the project's. [records.md](records.md) defines which fields stay English.

During a queue freeze, finish or correct existing items and keep possible follow-ups in outcome records until it clears or expires. Expiry warns so a forgotten freeze does not stall planning; the checker does not infer additions or block edits. Optional item `Ready by: YYYY-MM-DD` records delivery timing.

## Precedence

- New project: flag > preset > default; without a preset, the work defaults above apply.
- `--reconfigure` without `--preset`: flag > value stored in `agents.md` > v2 default.
- `--reconfigure --preset X`: flag > X's values > stored values for omitted keys > v2 default. Built-ins omit language, environment, git and autonomy; saved presets include them.

The resolved values are stored in `agents.md`, so editing a preset later cannot silently change a project. Applying a different preset is an explicit reconfiguration.

For missing-file repair and preservation checks, follow [the recovery procedure](migration-v2-to-v3.md#missing-file-repair) before applying new settings.

`.ro/template-render.json` tracks default versus explicit `External actions`: inherited defaults follow profile changes; custom patterns and `--external-actions none` persist. Older files without provenance keep their value. Init/reconfigure reports gating inactive for `none`; the checker warns `settings.external.inactive` when `external.gate` is in `Block`. Configure outward command prefixes and `Enforcement: block` before treating that gate as active.

## User presets

`--save-preset <name>` saves reusable preferences during setup, reconfiguration, or on its own. They live in `~/.research-orchestrator/presets/<name>.json`; `RESEARCH_ORCHESTRATOR_HOME` changes that root. Load them with `--preset user:<name>` or inspect them with `--list-presets`. Saved values answer setup questions, while flags let the current project differ.

Preset JSON requires `ro_settings.REQUIRED_PRESET_FILE_KEYS`. Additional reusable keys in `PRESET_KEYS` remain optional so older saved presets keep loading. Only a requested `platforms` answer may be `null`.

Saving includes language, environment, autonomy, custom guard selection/thresholds, git, read and receipt policies, publication/brief checks and external commands with enforcement/block settings. External commands become explicit policy, including `none`, so profile changes do not silently replace a saved gate.

Project identity, competition, phase clock and queue freeze are excluded because each project needs its own bindings and dates. Saved guards retain their mode; setup assigns the activation date. Summaries omit the source project name.

## How `--reconfigure` treats `agents.md`

- **Generated** — title, `<!-- ro-template: v3.4 -->`, summary, settings and reading pointers. Release 6.0.0 uses template v3.4, a separate format version.
- **Project rules** — [project-rules.md](project-rules.md) describes its three scaffolded subsections; `--reconfigure` preserves this user-owned region verbatim, including legacy layouts.

`--reconfigure` checks generated rules against the version marker (absent means v2) and `.ro/template-render.json`. The sidecar records the render key without cluttering instructions; single-host settings use one `Platforms: single — <host>` line. Keep the sidecar when moving a project to preserve pending settings changes. Move hand edits to `## Project rules` or save them before `--force`; settings edits are accepted. The checker reports `agents.rules.edited` for changed rules and `agents.rules.stale` for unapplied settings.

Release changes freeze the old template in `templates/<version>/` and bump the version for upgrades without force. Tests render frozen versions. `templates/v2/` stays byte-identical; unreleased snapshots have no compatibility version.

Every settings transition checks the proposed records before writing, preserves effective ordering and translates compatible goal fields, so a compact queue can move into research without invented scores even when its layout stays the same. Moving from self verification to a review policy adds missing pending-review fields; measured evidence and existing reviews stay intact. Changed records receive `.pre-migrate` backups, and incompatible transitions leave the project unchanged. A `Workflow` change also needs `--migrate`: see [migration-v2-to-v3.md](migration-v2-to-v3.md). Log settings changes as handoff events with heading `none` (workflow migration writes its own).
