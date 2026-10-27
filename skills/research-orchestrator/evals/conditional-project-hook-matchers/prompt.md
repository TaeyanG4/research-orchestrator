---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Prepare local Claude Code hook settings for the disposable projects in scenario.md. Use the installer with a disposable home; do not start Claude Code or change real user settings. Save the resulting PreToolUse tool lists in matcher-results.json. Apply the requested policy change and refresh the installed settings, then explain when that refresh is needed. Also inspect the generic plugin configuration to distinguish its scope from a project installation.

Use matcher-results.json keys initial, refreshed and plugin, each containing the unique PreToolUse tool names as an array. Save the explanation as matcher-notes.md.

Input files: scenario.md
