---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Investigate a hook launched from outside its project. In disposable directories, invoke the shipped wrapper with real Python, once using CLAUDE_PROJECT_DIR and once using CODEX_PROJECT_DIR. Exercise both POSIX sh and cmd.exe where available. Use scenario.md and retain each command, input payload, stdout, stderr and exit code in wrapper-evidence.json. Explain whether the configured policy and relative paths both survive in wrapper-notes.md. Do not start an agent host or execute the command under inspection.

Input files: scenario.md
