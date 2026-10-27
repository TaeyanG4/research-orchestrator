# Edit shortcuts alongside project policies

Use a disposable checkout, home and project directory for each configuration. Exercise all combinations of plugin active/inactive, Autonomy present/away, Brief requirements none/reviewer: Inspect evidence, and Read bound off/on. Repeat the matrix with the shipped PreToolUse declarations in reverse order in the disposable checkout, to check that ordering does not change routing.

Write those policies in the Project settings section of agents.md and set enabledPlugins["research-orchestrator@local"] in .claude/settings.json. Seed an unrelated PreToolUse Write hook with command unrelated-check. Count only research-orchestrator hooks when computing tool coverage, but retain the unrelated hook in settings snapshots.

Run the project installer for Claude Code. Record PreToolUse and PostToolUse registrations separately, including each hook's complete command. For an active plugin, the effective registrations include the disposable checkout's hooks/hooks.json plus the installed manual entries.

Rerun each installation unchanged, recording whether the settings bytes differ. Then set Autonomy to present, Brief requirements to none and Read bound to off, rerun, and save the refreshed settings. Keep plugin enablement unchanged.

For a separate partial-coverage check, add AskUserQuestion and Read to the ordinary PreToolUse matcher in a disposable copy of hooks/hooks.json. Enable all optional project policies with the plugin active and inspect the manual subscriptions returned by the installer.

For a separate overlap check, keep the original plugin active and call Installer.hook_template with a manual template containing ordinary PreToolUse entries for AskUserQuestion|Read and Read|Agent|Agent|AskUserQuestion, plus a PostToolUse entry for NotebookEdit|Read. Save the input template and returned supplements. This checks that filtering removes duplicates within and across entries without dropping the same tool's subscription to a different event.
