---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Check that the installed hook wrapper stays cheap outside an orchestrated project. Use the disposable layouts in brief.md and the shipped wrapper for each shell available on this machine. Replace RO_HOOK_PYTHON with a harmless local sentinel that records invocation and echoes its arguments and stdin; do not launch a real host. Capture each wrapper's exit code, stdout, stderr, sentinel invocation count and input before/after in wrapper-results.json, and explain the local scope in wrapper-report.md. Include nested project directories and both host project-directory hints so the optimization cannot disable hooks just because a host starts elsewhere.

Input files: brief.md
