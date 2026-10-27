---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Use the supplied scenarios to check Research Orchestrator's shared CLI runtime in disposable homes and projects. One user upgraded Codex after a Claude-only installation; another installed globally, then in a project, then removed that project installation. Keep all changes inside the sandbox, and leave real host settings alone.

Save runtime-results.json with upgrade and fallback objects, each containing installer_arguments, shim_text, shim_help_exit_code, and surviving_runtime (the full scripts/ro.py path). For upgrade also save the project's pre-push registration runtime as pre_push_runtime. Capture the actual CLI output as upgrade-help.txt and fallback-help.txt. Print runtime-results.json from the harness that ran the installer and shims to the command output, and retain the harness source, so the report can be checked against those calls.

Input files: scenarios.json
