# Upgrades, repairs and workflow changes

Use this procedure to keep an existing project's evidence and user-owned rules while upgrading its generated rules, repairing missing structure or changing workflows. Updating the installed skill alone does not rewrite project files.

Release 7.0 reads only the v3 layout, whose `agents.md` carries a `<!-- ro-template: ... -->` marker. A project from a release before 6.0 has no marker; the checker reports `agents.settings.unsupported` and `--reconfigure` refuses it. Upgrade such a project with research-orchestrator 6.0.x (`init_research_orchestrator.py . --reconfigure`), then return to this release.

## Missing-file repair

Missing-file repair preserves stored settings and name; conflicting flags fail before writes to prevent mismatched layouts. Repair without overrides, then `--reconfigure` (`--migrate` for workflow changes).

When demonstrating that a repair or refused operation preserved a project, compare recursive relative-path inventories and file hashes immediately before and after that operation, including tool state and non-coordination files. Keep the evidence outside the inspected tree. Hashing only the expected survivors cannot reveal newly created files or changes elsewhere; report preservation only for the scope actually checked.

## Missing Project settings

If `agents.md` has no `## Project settings`, recover it before using the ordinary upgrade steps below:

1. Save a recoverable copy of all four coordination files and any existing `.ro/` state. Keep existing instructions by moving them into `## Project rules`, creating that region if needed and preserving any rules already there; `--force` replaces the generated text above it.
2. Ask the [setup questions](../SKILL.md#setup): preset, user name, and that preset's remaining questions from [presets.md](presets.md), using answers already supplied.
3. Run the initializer with those answers as explicit flags:

   ```text
   python <skill-root>/scripts/init_research_orchestrator.py . --reconfigure --force --preset <preset> --user <user> --environment <os>/<shell> --platforms "<hosts>" --git <mode> --workflow classic
   ```

   Omit `--preset` for custom settings and add every remaining answer as its setting flag. The temporary `--workflow classic` keeps the per-slot layout during recovery; a workflow migration cannot pass preflight while settings are missing.
4. Run `python <skill-root>/scripts/check_project.py .` and repair the missing `handoff.md` fields it reports, including user records where needed.
5. Log the settings recovery as an event with heading `none` using [records.md](records.md), then rerun the checker and resolve remaining structural errors. If the chosen workflow is unified, follow [Change workflows](#change-workflows) after recovery passes the checker.

## Upgrade steps

1. Save a recoverable copy of all four coordination files and any existing `.ro/` state before changing settings. Quiesce active work before a workflow change; a coherent snapshot makes a later rollback possible.
2. Run `python <skill-root>/scripts/check_project.py .` and resolve structural errors. Read [presets.md](presets.md) to choose whether to keep the effective settings or apply a preset; `python <skill-root>/scripts/init_research_orchestrator.py --list-presets` lists the choices.
3. Move hand-written instructions from the generated part of `agents.md` into its `## Project rules` region. Preserve the existing region; [presets.md](presets.md) owns generated-part recognition and the deliberate `--force` escape hatch. Save the original before using that flag, because it replaces generated text.
4. To keep the existing workflow and settings while adopting the current template (for example v3.4 to v3.5, which adds `## Working rules`), run:

   ```bash
   python <skill-root>/scripts/init_research_orchestrator.py . --reconfigure
   ```

   To choose a preset, add `--preset <preset>` and answer its required flags. A preset that changes `Workflow` also needs `--migrate`; use the workflow procedure below.
5. Inspect the rendered settings and references, confirm `## Project rules` was preserved, and run the checker again. A settings-only reconfiguration asks you to log a handoff event with heading `none`; a workflow migration writes its own event.

## What changes

Reconfiguration updates the generated summary, settings, active reading pointers and working rules in `agents.md`, preserving the existing user-owned region, and adds the `@agents.md` line to `CLAUDE.md` described in [sessions.md](sessions.md). [presets.md](presets.md) defines template versioning and recognition; [project-rules.md](project-rules.md) describes the policy layout.

Guard activation, when requested, is dated and may add guard sections to `handoff.md`; [research-guards.md](research-guards.md) owns historical-record exemptions. Existing discovery evidence and reviews are preserved, and new timestamped reviews follow [verification.md](verification.md). With Git sync enabled, the initializer ignores `.ro/` in Git.

Every settings transition validates proposed records before writing, even when the workflow stays the same. Compatible goal fields and effective queue order carry over; a new review policy adds missing pending-review fields without inventing reviews. Incompatible records reject the transition without changing the project. Changed coordination files use the journal and `*.pre-migrate` backups below; a content-preserving reconfiguration needs neither. Keep the initial snapshot for a complete rollback.

## Change workflows

A `Workflow` change moves items and therefore requires both flags:

```bash
python <skill-root>/scripts/init_research_orchestrator.py . --reconfigure --workflow unified --migrate --user <user>
python <skill-root>/scripts/init_research_orchestrator.py . --reconfigure --workflow classic --migrate
```

- The source workflow comes from the generated template marker. Editing the setting by hand does not move items; the checker reports `settings.workflow.unmigrated` until migration.
- Release active slots first. Migration refuses any taken slot unless `--force` is supplied; use that override only when your own session is the sole taken slot. Other checker ERRORs still block migration; the workflow mismatch being repaired is exempt.
- Classic to unified moves every item into `## Queue` with `Claimed: none`. Work preserves file order, including mixed scored/unscored items. Research and competition sort by priority unless the plan header says `Ordering: queue`; preserving that explicit scheduling choice avoids changing dependencies during a layout migration.
- Unified to classic moves each item to its ID prefix's section and drops `Claimed:` lines. Missing plan and handoff sections and `Active agent(s)` entries are created. A round trip returns each item's other fields to its section.
- Both directions retain a valid plan-header `Ordering` and `Next:` pointing to an unfinished item. Other prose outside item blocks, including header notes and extra sections, is not carried over. The initializer prints each dropped line; the original remains in `plan.md.pre-migrate`.
- One handoff event with heading `none` records the migration under the first slot and first configured platform. Its user comes from `--user` or the first name in `Users`; provide the flag if none is recorded.

Run the checker after the migration and review reported dropped text before removing backups.

## Journal and interrupted recovery

The transaction writes changed coordination files to `<file>.migrate-tmp` and copies originals to `<file>.pre-migrate`. Workflow migration includes `agents.md`, `plan.md` and `handoff.md`, plus `discoveries.md` when its review fields change. Before replacing files, it durably writes `.ro/migration.json`. The journal contains a version, start time, source and target workflows, `phase: forward | rollback`, and each file's name, before/after SHA256 and status. Intent is journaled before each step; hashes, not a missing temporary file, prove completion.

A failure records rollback before restoring originals. An interruption leaves `migration.unfinished` in the checker. Run the initializer for that project again without new settings flags to recover first; it resumes the recorded direction before normal initialization. Forward files that are missing or mismatched trigger rollback, while a journal already in rollback always continues restoring. Legacy version-1 journals recover as rollback because they lack proof of a forward step.

The journal is removed only after every target matches the chosen direction. Recovery retains backups, and a failed restoration can be retried without consuming them. An unreadable or invalid journal is kept and reported rather than guessed at. Preserve it and its backups while resolving the problem; deleting the journal can hide a partial migration.

## Rollback after a completed change

For a workflow reversal, run the opposite workflow migration above; it preserves item fields but is a new transaction and replaces the `*.pre-migrate` files. Save any earlier backup you still need first.

For an exact return to an earlier state, stop active work and restore the complete pre-change snapshot together, including user rules and any tool state that changed. Use the matching released skill version if reverting the installed skill too, then run its checker. Do not mix old settings with a newer plan layout. After successful validation, the user decides when the saved snapshot and `*.pre-migrate` backups are no longer needed.
