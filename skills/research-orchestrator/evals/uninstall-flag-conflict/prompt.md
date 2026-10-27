---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Check an installer flag conflict in a disposable project. Follow brief.md, install the shipped runtime, record a complete file digest inventory, then attempt --uninstall --no-hooks. Keep the command result and the after inventory in uninstall-results.json. Finally perform ordinary uninstall and show that unrelated host hooks survive. Use a disposable --home and --project; do not touch real host configuration.

Input files: brief.md
