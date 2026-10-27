---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Set up the isolated installations described in brief.md using the shipped installer. In the first, use the default options and invoke the resulting ro entry point with --help. In the second, opt out with --no-shim. Capture command arguments, exit codes, and whether the shim exists in install-results.json. Also check that --shim remains accepted and that uninstalling an older project does not alter a shim now belonging to another project. Keep this entirely within disposable homes.

Input files: brief.md
