---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Our hook host has a restricted PATH, but I know the absolute path of an installed Python 3 interpreter. Check the installed hook wrapper on this platform using RO_HOOK_PYTHON, with no Python available on its child PATH. Use a disposable project outside the installed skill, and make its path contain spaces. Replay a PreToolUse background command into the wrapper without executing that command. Then repeat with an unavailable configured interpreter. Also check whether the wrapper preserves the runner's nonzero status for an invalid event name. Save the inputs, stdout, stderr, exit status and your conclusion in replay.json. Compare installed-script and project __pycache__ paths before and after these calls, and report whether any newly written bytecode is confined to the OS user-cache directory. Audit the shipped Windows subprocess helper, recording whether ordinary children always receive CREATE_NO_WINDOW while detached jobs retain their own flags. Do not launch Codex or Claude Code, change the parent environment, or edit the installed hook code.

Input files: brief.md
