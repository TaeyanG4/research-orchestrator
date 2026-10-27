# Supplemental project hook registrations

Create eight disposable projects: plugin inactive and active, each with these four policies in the Project settings section of agents.md:

| Policy | Autonomy | Brief requirements | Read bound |
|---|---|---|---|
| default | present | none | off |
| question | away | none | off |
| delegation | present | reviewer: Inspect evidence | off |
| all | away | reviewer: Inspect evidence | on |

Set enabledPlugins["research-orchestrator@local"] in each project's .claude/settings.json to its requested boolean. Add an unrelated PreToolUse entry with matcher Write and command unrelated-check in every project, then run the project installer for Claude Code. Count only research-orchestrator entries when reporting manual subscriptions. Generic plugin subscriptions are supplied by hooks/hooks.json and are not copied into the project settings when the plugin is active.

Keep the active/all installed settings snapshot before the repeated install and before disabling its policies. Disabling means Autonomy: present, Brief requirements: none, and Read bound: off; keep its plugin active.
