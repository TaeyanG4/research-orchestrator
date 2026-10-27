---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

The Claude Code plugin already provides the skill and hooks but ro is missing from PATH. Follow brief.md to add the CLI entry point in a disposable home without copying another skill or changing hook registration. Verify the shim responds to --help, and capture the guidance from the runtime brief when the shim is absent.

Save plugin-results.json with installer_arguments (an array), settings_before and settings_after (the exact text), help_exit_code, help_stdout, runtime_path, and copied_skills (an array of installed skill folders, empty if none). Save the missing-PATH runtime response as brief.txt.

Input files: brief.md
