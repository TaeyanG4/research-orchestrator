---
tags: [skill-creator]
max_turns: 20
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Update the standing rules in agents.md for our changed workflow. We now want a recoverable snapshot before each schema change instead of the nightly snapshot policy. Add a separate rule that troubleshooting documentation is available offline. Preserve the existing retention policy and project settings. Keep the rules concise and make clear which old requirement each new rule supersedes. This is a policy edit only; do not create snapshots or run a migration.

Input files: agents.md
