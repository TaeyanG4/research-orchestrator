---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Prepare Claude Code hook settings for the disposable projects described in scenario.md. Use a disposable home and the installer; do not start a host or change real user settings. Save each installed settings file and a registrations.json table of the research-orchestrator PreToolUse tool names, with one row per project. Include plugin enablement and policy values in each row so I can compare the combinations.

For the project with the plugin active and all optional policies enabled, rerun the same installation and record whether settings changed. Then turn all optional policies off, rerun the installer, and save its refreshed settings and registrations. Explain how project settings and the generic plugin's registrations combine in registration-notes.md.

Input files: scenario.md
